"""
Couche base de données de Pédantix.

- Supabase (PostgreSQL) si DATABASE_URL / SUPABASE_DB_URL est défini, sinon SQLite local.
- game_sessions décrit les sessions communes; user_game_stats conserve un résultat par joueur et par jeu.
- Les anciennes lignes restent en place et sont migrées vers game_id='pedantix'.
- Pool de connexions PostgreSQL (évite une connexion TCP+SSL par requête).
- Les écritures "non critiques" (historique, stats) passent par une file d'attente
  traitée par un thread : elles ne bloquent JAMAIS la boucle asynchrone du jeu.
- Aucune fonction publique ne lève d'exception : une panne de base ne doit pas
  casser une partie en cours.
"""

import json
import logging
import os
import queue
import sqlite3
import threading
import time
import datetime as _dt
import hashlib
import secrets
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple

from app.nlp import normalize_wiki_title

logger = logging.getLogger("pedantix.database")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

IS_POSTGRES = bool(DATABASE_URL and DATABASE_URL.startswith("postgresql://"))

# SQLite : fichier dans un dossier inscriptible (Render : /tmp est toujours inscriptible)
DB_PATH = os.environ.get("PEDANTIX_SQLITE_PATH") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pedantix.db"
)

try:
    import psycopg2
    import psycopg2.extras
    import psycopg2.pool
except ImportError:  # pragma: no cover
    psycopg2 = None

_pool = None
_pool_lock = threading.Lock()
_pg_disabled = False  # passe à True si Supabase est injoignable -> repli SQLite


def _get_pool():
    global _pool, _pg_disabled
    if _pool is not None:
        return _pool
    with _pool_lock:
        if _pool is not None:
            return _pool
        try:
            url = DATABASE_URL
            # Supabase exige SSL
            if "sslmode=" not in url:
                url += ("&" if "?" in url else "?") + "sslmode=require"
            _pool = psycopg2.pool.ThreadedConnectionPool(
                1, int(os.environ.get("PEDANTIX_DB_POOL_MAX", "5")), url,
                cursor_factory=psycopg2.extras.RealDictCursor,
                connect_timeout=8,
                keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=3,
            )
            logger.info("Pool PostgreSQL / Supabase initialisé")
        except Exception as e:
            logger.error(f"Connexion PostgreSQL impossible, repli sur SQLite : {e}")
            _pg_disabled = True
            _pool = None
        return _pool


def _use_pg() -> bool:
    return IS_POSTGRES and psycopg2 is not None and not _pg_disabled


class DatabaseContext:
    """Gestionnaire de contexte unifié SQLite / PostgreSQL."""

    def __init__(self):
        self.is_pg = False
        self.conn = None
        self.cursor = None
        self._pooled = False

    def __enter__(self):
        if _use_pg():
            pool = _get_pool()
            if pool is not None:
                try:
                    self.conn = pool.getconn()
                    self.conn.autocommit = False
                    self.cursor = self.conn.cursor()
                    self.is_pg = True
                    self._pooled = True
                    return self
                except Exception as e:
                    logger.error(f"getconn a échoué : {e}")
                    self._discard()
        # SQLite
        self.is_pg = False
        os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
        self.conn = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA cache_size=-16000")
        self.cursor = self.conn.cursor()
        return self

    def _discard(self):
        if self.conn is not None and self._pooled and _pool is not None:
            try:
                _pool.putconn(self.conn, close=True)
            except Exception:
                pass
        self.conn = None
        self.cursor = None
        self._pooled = False

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self.conn:
            return False
        broken = False
        try:
            if exc_type is None:
                self.conn.commit()
            else:
                self.conn.rollback()
        except Exception:
            broken = True
        try:
            if self.cursor:
                self.cursor.close()
        except Exception:
            pass
        if self._pooled and _pool is not None:
            try:
                _pool.putconn(self.conn, close=broken or exc_type is not None)
            except Exception:
                pass
        else:
            try:
                self.conn.close()
            except Exception:
                pass
        return False

    def execute(self, sql: str, params: tuple = ()):
        if self.is_pg:
            self.cursor.execute(sql.replace("?", "%s"), params)
        else:
            self.cursor.execute(sql, params)
        return self.cursor

    def fetchone(self):
        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()


# ---------------------------------------------------------------------------
# File d'écriture asynchrone (thread dédié)
# ---------------------------------------------------------------------------
_write_q: "queue.Queue" = queue.Queue(maxsize=5000)
_writer_started = False
_writer_lock = threading.Lock()


def _writer_loop():
    while True:
        fn, args, kwargs = _write_q.get()
        try:
            fn(*args, **kwargs)
        except Exception as e:
            logger.warning(f"Écriture DB ignorée ({fn.__name__}) : {e}")
        finally:
            _write_q.task_done()


def _enqueue(fn, *args, **kwargs):
    global _writer_started
    if not _writer_started:
        with _writer_lock:
            if not _writer_started:
                threading.Thread(target=_writer_loop, daemon=True, name="pedantix-db-writer").start()
                _writer_started = True
    try:
        _write_q.put_nowait((fn, args, kwargs))
    except queue.Full:
        logger.warning("File d'écriture DB pleine : écriture abandonnée")


def _jsonable(row: Dict[str, Any]) -> Dict[str, Any]:
    """Convertit datetimes -> ISO 8601 pour que FastAPI/json puisse sérialiser."""
    out = {}
    for k, v in dict(row).items():
        out[k] = v.isoformat() if isinstance(v, (_dt.datetime, _dt.date)) else v
    return out


def _user_game_row(row: Dict[str, Any]) -> Dict[str, Any]:
    result = _jsonable(row)
    try:
        result["metrics"] = json.loads(result.pop("metrics_json", "{}"))
    except (TypeError, json.JSONDecodeError):
        result["metrics"] = {}
    return result


# ---------------------------------------------------------------------------
# Schéma
# ---------------------------------------------------------------------------
_SCHEMA_PG = [
    """CREATE TABLE IF NOT EXISTS game_catalog (
        game_id TEXT PRIMARY KEY, display_name TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1)""",
    """CREATE TABLE IF NOT EXISTS game_sessions (
        session_id TEXT PRIMARY KEY, game_id TEXT NOT NULL, mode TEXT NOT NULL,
        title TEXT NOT NULL DEFAULT '', difficulty TEXT,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        finished_at TIMESTAMPTZ)""",
    """CREATE TABLE IF NOT EXISTS article_cache (
        title TEXT PRIMARY KEY, url TEXT, image TEXT, paragraphs_json TEXT, category TEXT,
        cached_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS games (
        session_id TEXT PRIMARY KEY, seed TEXT, title TEXT, url TEXT, image TEXT, mode TEXT, category TEXT,
        won INTEGER DEFAULT 0, surrendered INTEGER DEFAULT 0, attempts_count INTEGER DEFAULT 0,
        revealed_words INTEGER DEFAULT 0, total_words INTEGER DEFAULT 0, time_seconds INTEGER DEFAULT 0,
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP, finished_at TIMESTAMPTZ)""",
    """CREATE TABLE IF NOT EXISTS guesses (
        id BIGSERIAL PRIMARY KEY,
        session_id TEXT REFERENCES games(session_id) ON DELETE CASCADE,
        attempt_num INTEGER, word TEXT, status TEXT, matches_count INTEGER,
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS player_scores (
        player_name TEXT PRIMARY KEY, score INTEGER DEFAULT 0, wins INTEGER DEFAULT 0,
        games_played INTEGER DEFAULT 0, last_played TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS player_game_scores (
        player_name TEXT NOT NULL, game_id TEXT NOT NULL, score INTEGER NOT NULL DEFAULT 0,
        last_played TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (player_name, game_id))""",
    """CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY, password_hash TEXT NOT NULL,
        score INTEGER DEFAULT 0, wins INTEGER DEFAULT 0,
        games_played INTEGER DEFAULT 0, best_attempts INTEGER,
        total_attempts INTEGER DEFAULT 0,
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        last_login TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS user_game_stats (
        id BIGSERIAL PRIMARY KEY,
        username TEXT NOT NULL, session_id TEXT NOT NULL, game_id TEXT NOT NULL DEFAULT 'pedantix',
        mode TEXT NOT NULL, difficulty TEXT, metrics_json TEXT NOT NULL DEFAULT '{}',
        title TEXT NOT NULL, won INTEGER NOT NULL DEFAULT 0, surrendered INTEGER NOT NULL DEFAULT 0,
        attempts INTEGER NOT NULL DEFAULT 0, duration_seconds INTEGER NOT NULL DEFAULT 0,
        points INTEGER NOT NULL DEFAULT 0, revealed_words INTEGER NOT NULL DEFAULT 0,
        total_words INTEGER NOT NULL DEFAULT 0, finished_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (username, session_id))""",
    """CREATE TABLE IF NOT EXISTS user_words (
        username TEXT NOT NULL, word TEXT NOT NULL, count INTEGER DEFAULT 1,
        PRIMARY KEY (username, word))""",
    """CREATE TABLE IF NOT EXISTS user_played_articles (
        id BIGSERIAL PRIMARY KEY,
        user_identifier TEXT NOT NULL,
        article_title TEXT NOT NULL,
        played_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS geoguessr_google_usage (
        month TEXT PRIMARY KEY, event_count INTEGER NOT NULL DEFAULT 0)""",
    """CREATE TABLE IF NOT EXISTS secret_gate_progress (
        player_id TEXT PRIMARY KEY,
        current_step INTEGER NOT NULL DEFAULT 1,
        completed INTEGER NOT NULL DEFAULT 0,
        attempts INTEGER NOT NULL DEFAULT 0,
        last_attempt_at DOUBLE PRECISION NOT NULL DEFAULT 0,
        unlocked_at DOUBLE PRECISION NOT NULL DEFAULT 0,
        username TEXT)""",
    "CREATE INDEX IF NOT EXISTS idx_guesses_session ON guesses(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_games_finished ON games(finished_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_article_category ON article_cache(category)",
    "CREATE INDEX IF NOT EXISTS idx_user_words_user ON user_words(username)",
    "CREATE INDEX IF NOT EXISTS idx_user_game_stats_user_finished ON user_game_stats(username, finished_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_player_game_scores_game_score ON player_game_scores(game_id, score DESC)",
    "CREATE INDEX IF NOT EXISTS idx_user_played_lookup ON user_played_articles(user_identifier, played_at)",
    "CREATE INDEX IF NOT EXISTS idx_user_played_title ON user_played_articles(article_title)",
]

_SCHEMA_SQLITE = [
    """CREATE TABLE IF NOT EXISTS game_catalog (
        game_id TEXT PRIMARY KEY, display_name TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1)""",
    """CREATE TABLE IF NOT EXISTS game_sessions (
        session_id TEXT PRIMARY KEY, game_id TEXT NOT NULL, mode TEXT NOT NULL,
        title TEXT NOT NULL DEFAULT '', difficulty TEXT,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        finished_at TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS article_cache (
        title TEXT PRIMARY KEY, url TEXT, image TEXT, paragraphs_json TEXT, category TEXT,
        cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS games (
        session_id TEXT PRIMARY KEY, seed TEXT, title TEXT, url TEXT, image TEXT, mode TEXT, category TEXT,
        won INTEGER DEFAULT 0, surrendered INTEGER DEFAULT 0, attempts_count INTEGER DEFAULT 0,
        revealed_words INTEGER DEFAULT 0, total_words INTEGER DEFAULT 0, time_seconds INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, finished_at TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS guesses (
        id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, attempt_num INTEGER, word TEXT,
        status TEXT, matches_count INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS player_scores (
        player_name TEXT PRIMARY KEY, score INTEGER DEFAULT 0, wins INTEGER DEFAULT 0,
        games_played INTEGER DEFAULT 0, last_played TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS player_game_scores (
        player_name TEXT NOT NULL, game_id TEXT NOT NULL, score INTEGER NOT NULL DEFAULT 0,
        last_played TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (player_name, game_id))""",
    """CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY, password_hash TEXT NOT NULL,
        score INTEGER DEFAULT 0, wins INTEGER DEFAULT 0,
        games_played INTEGER DEFAULT 0, best_attempts INTEGER,
        total_attempts INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_login TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS user_game_stats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL, session_id TEXT NOT NULL, game_id TEXT NOT NULL DEFAULT 'pedantix',
        mode TEXT NOT NULL, difficulty TEXT, metrics_json TEXT NOT NULL DEFAULT '{}',
        title TEXT NOT NULL, won INTEGER NOT NULL DEFAULT 0, surrendered INTEGER NOT NULL DEFAULT 0,
        attempts INTEGER NOT NULL DEFAULT 0, duration_seconds INTEGER NOT NULL DEFAULT 0,
        points INTEGER NOT NULL DEFAULT 0, revealed_words INTEGER NOT NULL DEFAULT 0,
        total_words INTEGER NOT NULL DEFAULT 0, finished_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (username, session_id))""",
    """CREATE TABLE IF NOT EXISTS user_words (
        username TEXT NOT NULL, word TEXT NOT NULL, count INTEGER DEFAULT 1,
        PRIMARY KEY (username, word))""",
    """CREATE TABLE IF NOT EXISTS user_played_articles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_identifier TEXT NOT NULL,
        article_title TEXT NOT NULL,
        played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS geoguessr_google_usage (
        month TEXT PRIMARY KEY, event_count INTEGER NOT NULL DEFAULT 0)""",
    """CREATE TABLE IF NOT EXISTS secret_gate_progress (
        player_id TEXT PRIMARY KEY,
        current_step INTEGER NOT NULL DEFAULT 1,
        completed INTEGER NOT NULL DEFAULT 0,
        attempts INTEGER NOT NULL DEFAULT 0,
        last_attempt_at REAL NOT NULL DEFAULT 0,
        unlocked_at REAL NOT NULL DEFAULT 0,
        username TEXT)""",
    "CREATE INDEX IF NOT EXISTS idx_guesses_session ON guesses(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_user_words_user ON user_words(username)",
    "CREATE INDEX IF NOT EXISTS idx_user_game_stats_user_finished ON user_game_stats(username, finished_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_player_game_scores_game_score ON player_game_scores(game_id, score DESC)",
    "CREATE INDEX IF NOT EXISTS idx_user_played_lookup ON user_played_articles(user_identifier, played_at)",
    "CREATE INDEX IF NOT EXISTS idx_user_played_title ON user_played_articles(article_title)",
]

_GAME_CATALOG = (
    ("pedantix", "Pédantix"),
    ("motus", "Motus"),
    ("cemantix", "Cémantix"),
    ("chiffrantix", "Chiffrantix"),
    ("sudoku", "Sudoku"),
    ("battleship", "Bataille navale"),
    ("geoguessr", "GeoGuessr"),
    ("undercover", "Undercover"),
    ("bitoguessr", "Bitoguessr"),
)


def _ensure_column(db: DatabaseContext, table: str, column: str, definition: str) -> None:
    if db.is_pg:
        db.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {definition}")
        return

    db.execute(f"PRAGMA table_info({table})")
    if column not in {row["name"] for row in db.fetchall()}:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _migrate_multigame_schema(db: DatabaseContext) -> None:
    _ensure_column(db, "games", "game_id", "TEXT NOT NULL DEFAULT 'pedantix'")
    _ensure_column(db, "user_game_stats", "game_id", "TEXT NOT NULL DEFAULT 'pedantix'")
    _ensure_column(db, "user_game_stats", "difficulty", "TEXT")
    _ensure_column(db, "user_game_stats", "metrics_json", "TEXT NOT NULL DEFAULT '{}'")

    db.execute(
        """INSERT INTO player_game_scores (player_name, game_id, score, last_played)
           SELECT ps.player_name, 'pedantix',
                  CASE WHEN ps.score - COALESCE(SUM(
                      CASE WHEN ugs.game_id <> 'pedantix' THEN ugs.points ELSE 0 END
                  ), 0) > 0
                  THEN ps.score - COALESCE(SUM(
                      CASE WHEN ugs.game_id <> 'pedantix' THEN ugs.points ELSE 0 END
                  ), 0)
                  ELSE 0 END,
                  ps.last_played
           FROM player_scores ps
           LEFT JOIN user_game_stats ugs
             ON LOWER(ugs.username) = LOWER(ps.player_name)
           GROUP BY ps.player_name, ps.score, ps.last_played
           ON CONFLICT (player_name, game_id) DO NOTHING"""
    )
    db.execute(
        """INSERT INTO player_game_scores (player_name, game_id, score, last_played)
           SELECT COALESCE(u.username, ugs.username), ugs.game_id,
                  SUM(ugs.points), MAX(ugs.finished_at)
           FROM user_game_stats ugs
           LEFT JOIN users u ON LOWER(u.username) = LOWER(ugs.username)
           GROUP BY COALESCE(u.username, ugs.username), ugs.game_id
           ON CONFLICT (player_name, game_id) DO NOTHING"""
    )

    for game_id, display_name in _GAME_CATALOG:
        db.execute(
            """INSERT INTO game_catalog (game_id, display_name, enabled)
               VALUES (?, ?, 1) ON CONFLICT (game_id) DO NOTHING""",
            (game_id, display_name),
        )

    db.execute(
        """INSERT INTO game_sessions
               (session_id, game_id, mode, title, created_at, finished_at)
           SELECT session_id, 'pedantix', COALESCE(mode, 'solo'), COALESCE(title, ''),
                  created_at, finished_at
           FROM games
           WHERE session_id NOT IN (SELECT session_id FROM game_sessions)"""
    )
    db.execute(
        """INSERT INTO game_sessions
               (session_id, game_id, mode, title, difficulty, created_at, finished_at)
           SELECT ugs.session_id, ugs.game_id, ugs.mode, ugs.title, ugs.difficulty,
                  MIN(ugs.finished_at), MAX(ugs.finished_at)
           FROM user_game_stats ugs
           WHERE ugs.session_id NOT IN (SELECT session_id FROM game_sessions)
           GROUP BY ugs.session_id, ugs.game_id, ugs.mode, ugs.title, ugs.difficulty"""
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_game_stats_game_user_finished "
        "ON user_game_stats(game_id, username, finished_at DESC)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_game_sessions_game_finished "
        "ON game_sessions(game_id, finished_at DESC)"
    )


def init_db() -> bool:
    """Crée les tables. Retourne True si OK. Ne lève jamais d'exception."""
    try:
        with DatabaseContext() as db:
            for stmt in (_SCHEMA_PG if db.is_pg else _SCHEMA_SQLITE):
                db.execute(stmt)
            _migrate_multigame_schema(db)
            logger.info(f"Base de données prête ({'Supabase/PostgreSQL' if db.is_pg else 'SQLite'})")
        return True
    except Exception as e:
        logger.error(f"init_db a échoué : {e}")
        return False


def db_backend() -> str:
    return "postgres" if _use_pg() else "sqlite"


def _geoguessr_google_usage_month() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m")


def get_geoguessr_google_usage() -> int:
    if IS_POSTGRES and not _use_pg():
        raise RuntimeError("La base PostgreSQL GeoGuessr est indisponible.")
    try:
        with DatabaseContext() as db:
            db.execute(
                "SELECT event_count FROM geoguessr_google_usage WHERE month = ?",
                (_geoguessr_google_usage_month(),),
            )
            row = db.fetchone()
            return int(row["event_count"]) if row else 0
    except Exception as exc:
        logger.error("Lecture du compteur Google Street View impossible : %s", exc)
        raise RuntimeError("Impossible de vérifier le quota Google Street View.") from exc


def reserve_geoguessr_google_usage(event_count: int, monthly_limit: int) -> bool:
    if event_count <= 0 or monthly_limit <= 0:
        raise ValueError("Le nombre d'événements et la limite doivent être positifs.")
    if event_count > monthly_limit:
        return False
    if IS_POSTGRES and not _use_pg():
        raise RuntimeError("La base PostgreSQL GeoGuessr est indisponible.")

    try:
        with DatabaseContext() as db:
            db.execute(
                """INSERT INTO geoguessr_google_usage (month, event_count)
                   VALUES (?, ?)
                   ON CONFLICT (month) DO UPDATE
                   SET event_count = geoguessr_google_usage.event_count + ?
                   WHERE geoguessr_google_usage.event_count + ? <= ?
                   RETURNING event_count""",
                (
                    _geoguessr_google_usage_month(),
                    event_count,
                    event_count,
                    event_count,
                    monthly_limit,
                ),
            )
            return db.fetchone() is not None
    except Exception as exc:
        logger.error("Réservation du quota Google Street View impossible : %s", exc)
        raise RuntimeError("Impossible de réserver le quota Google Street View.") from exc


def get_game_catalog() -> List[Dict[str, Any]]:
    try:
        with DatabaseContext() as db:
            db.execute(
                "SELECT game_id, display_name, enabled FROM game_catalog ORDER BY game_id"
            )
            return [_jsonable(row) for row in db.fetchall()]
    except Exception as e:
        logger.warning(f"get_game_catalog: {e}")
        raise RuntimeError("Impossible de charger le catalogue des jeux.") from e


def ping_db() -> bool:
    try:
        with DatabaseContext() as db:
            db.execute("SELECT 1")
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Cache d'articles
# ---------------------------------------------------------------------------
def _cache_article_sync(title, url, image, paragraphs, category):
    with DatabaseContext() as db:
        db.execute(
            """INSERT INTO article_cache (title, url, image, paragraphs_json, category)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT (title) DO UPDATE SET
                   url = EXCLUDED.url, image = EXCLUDED.image,
                   paragraphs_json = EXCLUDED.paragraphs_json, category = EXCLUDED.category""",
            (title, url, image, json.dumps(paragraphs, ensure_ascii=False), category),
        )


def cache_article(title: str, url: str, image: str, paragraphs: List[str], category: str = ""):
    _enqueue(_cache_article_sync, title, url or "", image or "", paragraphs, category or "")


def _row_to_article(row) -> Dict[str, Any]:
    return {
        "title": row["title"], "url": row["url"], "image": row["image"],
        "paragraphs": json.loads(row["paragraphs_json"]), "category": row["category"],
    }


def get_cached_article(title: str) -> Optional[Dict[str, Any]]:
    try:
        with DatabaseContext() as db:
            db.execute("SELECT * FROM article_cache WHERE title = ?", (title,))
            row = db.fetchone()
            return _row_to_article(row) if row else None
    except Exception as e:
        logger.warning(f"get_cached_article: {e}")
        return None


def get_random_cached_article(category: Optional[str] = None, exclude_titles: Optional[Set[str]] = None) -> Optional[Dict[str, Any]]:
    exclude_set = set(exclude_titles) if exclude_titles else set()
    exclude_norm = {normalize_wiki_title(t) for t in exclude_set if t}
    try:
        with DatabaseContext() as db:
            if category:
                db.execute("SELECT * FROM article_cache WHERE category = ? ORDER BY RANDOM() LIMIT 25", (category,))
            else:
                db.execute("SELECT * FROM article_cache ORDER BY RANDOM() LIMIT 25")
            rows = db.fetchall()
            for row in rows:
                art = _row_to_article(row)
                if art:
                    if any(
                        "dans cette manche de Pédantix." in paragraph
                        for paragraph in art.get("paragraphs", [])
                    ):
                        continue
                    title = art.get("title", "")
                    if title not in exclude_set and normalize_wiki_title(title) not in exclude_norm:
                        return art
            return None
    except Exception as e:
        logger.warning(f"get_random_cached_article: {e}")
        return None


# ---------------------------------------------------------------------------
# Suivi des pages apparues / jouées (règle des 15 jours sans répétition)
# ---------------------------------------------------------------------------
_recent_played_cache: Dict[str, Dict[str, float]] = {}
_recent_played_lock = threading.Lock()


def is_valid_user_identifier(ident: str) -> bool:
    """Valide qu'un identifiant n'est pas un nom d'invité générique (ex: 'Joueur 1', 'Host')."""
    if not ident:
        return False
    ci = ident.strip().lower()
    if not ci or len(ci) < 2:
        return False
    if ci.startswith("joueur ") or ci in ("host", "anonyme", "spectateur", "undefined", "null"):
        return False
    return True


def _record_played_article_sync(identifiers: List[str], article_title: str):
    if not identifiers or not article_title:
        return
    clean_title = article_title.strip()
    clean_ids = list({ident.strip().lower() for ident in identifiers if is_valid_user_identifier(ident)})
    if not clean_ids or not clean_title:
        return
    try:
        with DatabaseContext() as db:
            for ident in clean_ids:
                db.execute(
                    "INSERT INTO user_played_articles (user_identifier, article_title) VALUES (?, ?)",
                    (ident, clean_title),
                )
    except Exception as e:
        logger.warning(f"_record_played_article_sync: {e}")


def record_played_article(identifiers: List[str], article_title: str):
    """Enregistre qu'une page Wikipedia est apparue pour un ou plusieurs utilisateurs."""
    if not identifiers or not article_title:
        return
    clean_title = article_title.strip()
    clean_ids = list({ident.strip().lower() for ident in identifiers if is_valid_user_identifier(ident)})
    if not clean_ids or not clean_title:
        return
    now_ts = time.time()
    with _recent_played_lock:
        for ident in clean_ids:
            if ident not in _recent_played_cache:
                _recent_played_cache[ident] = {}
            _recent_played_cache[ident][clean_title] = now_ts
    _enqueue(_record_played_article_sync, clean_ids, clean_title)


def get_recently_played_articles(identifiers: List[str], days: int = 15) -> Set[str]:
    """Retourne l'ensemble des titres d'articles apparus pour ces identifiants durant les X derniers jours."""
    if not identifiers:
        return set()
    clean_ids = list({ident.strip().lower() for ident in identifiers if is_valid_user_identifier(ident)})
    if not clean_ids:
        return set()

    titles: Set[str] = set()
    now_ts = time.time()
    cutoff_ts = now_ts - (days * 86400)

    with _recent_played_lock:
        for ident in clean_ids:
            cached_entries = _recent_played_cache.get(ident)
            if cached_entries:
                for t, ts in list(cached_entries.items()):
                    if ts >= cutoff_ts:
                        titles.add(t)
                    else:
                        cached_entries.pop(t, None)

    cutoff = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=days)
    cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")

    try:
        with DatabaseContext() as db:
            placeholders = ", ".join(["?"] * len(clean_ids))
            query = (
                f"SELECT DISTINCT article_title FROM user_played_articles "
                f"WHERE user_identifier IN ({placeholders}) AND played_at >= ?"
            )
            params = tuple(clean_ids) + (cutoff if db.is_pg else cutoff_str,)
            db.execute(query, params)
            for row in db.fetchall():
                t = row["article_title"] if isinstance(row, dict) or hasattr(row, "__getitem__") else row[0]
                if t:
                    titles.add(t)
    except Exception as e:
        logger.warning(f"get_recently_played_articles: {e}")

    return titles



# ---------------------------------------------------------------------------
# Historique des parties (écritures en arrière-plan)
# ---------------------------------------------------------------------------
def _record_game_start_sync(session_id, seed, title, url, image, mode, category, total_words):
    with DatabaseContext() as db:
        db.execute(
            """INSERT INTO games (session_id, seed, title, url, image, mode, category, total_words)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT (session_id) DO UPDATE SET
                   seed = EXCLUDED.seed, title = EXCLUDED.title, url = EXCLUDED.url,
                   image = EXCLUDED.image, mode = EXCLUDED.mode, category = EXCLUDED.category,
                   total_words = EXCLUDED.total_words""",
            (session_id, seed, title, url, image, mode, category, total_words),
        )
        db.execute(
                   """INSERT INTO game_sessions (session_id, game_id, mode, title, metadata_json)
                      VALUES (?, 'pedantix', ?, ?, ?)
                      ON CONFLICT (session_id) DO UPDATE SET
                          mode = EXCLUDED.mode, title = EXCLUDED.title,
                          metadata_json = EXCLUDED.metadata_json""",
                   (session_id, mode, title, json.dumps({"category": category}, ensure_ascii=False)),
        )


def _record_multigame_session_start_sync(
    session_id: str,
    game_id: str,
    mode: str,
    title: str,
    difficulty: Optional[str],
):
    with DatabaseContext() as db:
        db.execute(
            """INSERT INTO game_sessions
                   (session_id, game_id, mode, title, difficulty)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT (session_id) DO UPDATE SET
                   game_id = EXCLUDED.game_id, mode = EXCLUDED.mode,
                   title = EXCLUDED.title, difficulty = EXCLUDED.difficulty""",
            (session_id, game_id, mode, title, difficulty),
        )


def record_multigame_session_start(
    session_id: str,
    game_id: str,
    mode: str,
    title: str,
    difficulty: Optional[str] = None,
):
    if game_id not in {item[0] for item in _GAME_CATALOG} - {"pedantix"}:
        raise ValueError("Jeu inconnu ou non pris en charge.")
    _enqueue(
        _record_multigame_session_start_sync,
        session_id,
        game_id,
        mode if mode in ("solo", "multiplayer", "team") else "solo",
        title,
        difficulty,
    )


def record_game_start(session_id: str, seed: str, title: str, url: str, image: str,
                      mode: str, category: str, total_words: int):
    _enqueue(_record_game_start_sync, session_id, seed, title, url or "", image or "", mode, category, total_words)


def _record_guess_sync(session_id, attempt_num, word, status, matches_count):
    with DatabaseContext() as db:
        db.execute(
            "INSERT INTO guesses (session_id, attempt_num, word, status, matches_count) VALUES (?, ?, ?, ?, ?)",
            (session_id, attempt_num, word, status, matches_count),
        )
        db.execute("UPDATE games SET attempts_count = ? WHERE session_id = ?", (attempt_num, session_id))


def record_guess(session_id: str, attempt_num: int, word: str, status: str, matches_count: int):
    _enqueue(_record_guess_sync, session_id, attempt_num, word, status, matches_count)


def _record_game_finish_sync(session_id, won, surrendered, attempts, revealed_words, elapsed_time):
    with DatabaseContext() as db:
        db.execute(
            """UPDATE games SET won = ?, surrendered = ?, attempts_count = ?, revealed_words = ?,
                   time_seconds = ?, finished_at = CURRENT_TIMESTAMP WHERE session_id = ?""",
            (1 if won else 0, 1 if surrendered else 0, attempts, revealed_words, elapsed_time, session_id),
        )
        db.execute(
            """UPDATE game_sessions SET finished_at = CURRENT_TIMESTAMP
               WHERE session_id = ?""",
            (session_id,),
        )


def record_game_finish(session_id: str, won: bool, surrendered: bool, attempts: int,
                       revealed_words: int, elapsed_time: int):
    _enqueue(_record_game_finish_sync, session_id, won, surrendered, attempts, revealed_words, elapsed_time)


def get_stats(game_id: str = "pedantix") -> Dict[str, Any]:
    empty = {
        "total_games": 0, "finished_games": 0, "won_games": 0, "win_rate": 0,
        "avg_attempts": 0, "best_score": 0, "recent_games": [],
        "modes": {"solo": _empty_mode_stats(), "multiplayer": _empty_mode_stats()},
    }
    if game_id not in {item[0] for item in _GAME_CATALOG}:
        raise ValueError("Jeu inconnu.")
    try:
        with DatabaseContext() as db:
            if game_id != "pedantix":
                db.execute(
                    "SELECT COUNT(*) AS total_games FROM game_sessions WHERE game_id = ?",
                    (game_id,),
                )
                total_games = int(db.fetchone()["total_games"] or 0)
                db.execute(
                    """SELECT COUNT(DISTINCT session_id) AS finished_games,
                              COUNT(DISTINCT CASE WHEN won = 1 THEN session_id END) AS won_games,
                              AVG(attempts) AS avg_attempts,
                              AVG(CASE WHEN won = 1 THEN attempts END) AS avg_winning_attempts,
                              MIN(CASE WHEN won = 1 AND attempts > 0 THEN attempts END) AS best_score,
                              AVG(duration_seconds) AS avg_time_seconds,
                              AVG(CASE WHEN total_words > 0
                                       THEN 100.0 * revealed_words / total_words END) AS avg_revealed_pct,
                              SUM(points) AS points
                       FROM user_game_stats
                       WHERE game_id = ?""",
                    (game_id,),
                )
                overall = _format_mode_stats(db.fetchone())
                db.execute(
                    """SELECT CASE WHEN mode IN ('multiplayer', 'team') THEN 'multiplayer'
                                   ELSE 'solo' END AS game_type,
                              COUNT(DISTINCT session_id) AS finished_games,
                              COUNT(DISTINCT CASE WHEN won = 1 THEN session_id END) AS won_games,
                              AVG(attempts) AS avg_attempts,
                              AVG(CASE WHEN won = 1 THEN attempts END) AS avg_winning_attempts,
                              MIN(CASE WHEN won = 1 AND attempts > 0 THEN attempts END) AS best_score,
                              AVG(duration_seconds) AS avg_time_seconds,
                              AVG(CASE WHEN total_words > 0
                                       THEN 100.0 * revealed_words / total_words END) AS avg_revealed_pct,
                              SUM(points) AS points
                       FROM user_game_stats
                       WHERE game_id = ?
                       GROUP BY game_type""",
                    (game_id,),
                )
                mode_stats = {"solo": _empty_mode_stats(), "multiplayer": _empty_mode_stats()}
                for row in db.fetchall():
                    mode_stats[row["game_type"]] = _format_mode_stats(row)
                db.execute(
                    """SELECT difficulty, COUNT(DISTINCT session_id) AS games_played,
                              COUNT(DISTINCT CASE WHEN won = 1 THEN session_id END) AS wins
                       FROM user_game_stats WHERE game_id = ?
                       GROUP BY difficulty ORDER BY difficulty""",
                    (game_id,),
                )
                difficulty_breakdown = {
                    row["difficulty"] or "non précisée": {
                        "games_played": int(row["games_played"] or 0),
                        "wins": int(row["wins"] or 0),
                    }
                    for row in db.fetchall()
                }
                db.execute(
                    """SELECT game_id, session_id, title, mode, difficulty, won, surrendered,
                              attempts, duration_seconds, points, metrics_json, finished_at
                       FROM user_game_stats WHERE game_id = ?
                       ORDER BY finished_at DESC, id DESC LIMIT 10""",
                    (game_id,),
                )
                recent = [_user_game_row(row) for row in db.fetchall()]
                return {
                    "game_id": game_id,
                    "total_games": total_games,
                    "finished_games": overall["games_played"],
                    "won_games": overall["wins"],
                    "win_rate": overall["win_rate"],
                    "avg_attempts": overall["avg_attempts"] or 0,
                    "best_score": overall["best_attempts"] or 0,
                    "recent_games": recent,
                    "modes": mode_stats,
                    "difficulty_breakdown": difficulty_breakdown,
                }

            db.execute("SELECT COUNT(*) AS total_games FROM games WHERE game_id = ?", (game_id,))
            total_games = (db.fetchone() or {"total_games": 0})["total_games"]

            db.execute(
                """SELECT
                       COUNT(*) AS finished_games,
                       SUM(won) AS won_games,
                       AVG(attempts_count) AS avg_attempts,
                       AVG(CASE WHEN won = 1 THEN attempts_count END) AS avg_winning_attempts,
                       MIN(CASE WHEN won = 1 AND attempts_count > 0 THEN attempts_count END) AS best_score,
                       AVG(time_seconds) AS avg_time_seconds,
                       AVG(CASE WHEN total_words > 0 THEN 100.0 * revealed_words / total_words END) AS avg_revealed_pct
                   FROM games WHERE game_id = ? AND finished_at IS NOT NULL""",
                (game_id,),
            )
            overall = _format_mode_stats(db.fetchone())

            db.execute(
                """SELECT
                       CASE WHEN mode IN ('multiplayer', 'team') THEN 'multiplayer' ELSE 'solo' END AS game_type,
                       COUNT(*) AS finished_games,
                       SUM(won) AS won_games,
                       AVG(attempts_count) AS avg_attempts,
                       AVG(CASE WHEN won = 1 THEN attempts_count END) AS avg_winning_attempts,
                       MIN(CASE WHEN won = 1 AND attempts_count > 0 THEN attempts_count END) AS best_score,
                       AVG(time_seconds) AS avg_time_seconds,
                       AVG(CASE WHEN total_words > 0 THEN 100.0 * revealed_words / total_words END) AS avg_revealed_pct
                   FROM games WHERE game_id = ? AND finished_at IS NOT NULL GROUP BY game_type""",
                (game_id,),
            )
            mode_stats = {"solo": _empty_mode_stats(), "multiplayer": _empty_mode_stats()}
            for row in db.fetchall():
                mode_stats[row["game_type"]] = _format_mode_stats(row)

            db.execute(
                """SELECT game_id, title, mode, category, won, surrendered, attempts_count,
                          time_seconds, finished_at
                   FROM games WHERE game_id = ? AND finished_at IS NOT NULL
                   ORDER BY finished_at DESC LIMIT 10""",
                (game_id,),
            )
            recent = [_jsonable(row) for row in db.fetchall()]

            return {
                "game_id": game_id,
                "total_games": total_games,
                "finished_games": overall["games_played"],
                "won_games": overall["wins"],
                "win_rate": overall["win_rate"],
                "avg_attempts": overall["avg_attempts"] or 0,
                "best_score": overall["best_attempts"] or 0,
                "recent_games": recent,
                "modes": mode_stats,
            }
    except Exception as e:
        logger.warning(f"get_stats: {e}")
        return empty


# ---------------------------------------------------------------------------
# Scores des joueurs
# ---------------------------------------------------------------------------
# Petit cache mémoire : évite un aller-retour réseau vers Supabase à chaque
# création de joueur / rafraîchissement de score pendant une partie.
_score_cache: Dict[Tuple[str, str], int] = {}
_score_lock = threading.Lock()


def get_player_score(player_name: str, game_id: str = "pedantix") -> int:
    if not player_name:
        return 0
    name = player_name.strip()
    cache_key = (game_id, name)
    with _score_lock:
        if cache_key in _score_cache:
            return _score_cache[cache_key]
    score = 0
    try:
        with DatabaseContext() as db:
            db.execute(
                "SELECT score FROM player_game_scores WHERE player_name = ? AND game_id = ?",
                (name, game_id),
            )
            row = db.fetchone()
            score = int(row["score"]) if row else 0
    except Exception as e:
        logger.warning(f"get_player_score: {e}")
    with _score_lock:
        _score_cache[cache_key] = score
    return score


def _increment_sync(name: str, points: int, game_id: str = "pedantix"):
    with DatabaseContext() as db:
        db.execute(
            """INSERT INTO player_game_scores (player_name, game_id, score, last_played)
               VALUES (?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT (player_name, game_id) DO UPDATE SET
                   score = player_game_scores.score + EXCLUDED.score,
                   last_played = CURRENT_TIMESTAMP""",
            (name, game_id, points),
        )


def increment_player_score(
    player_name: str, points: int = 1, game_id: str = "pedantix",
) -> int:
    """Met à jour le cache immédiatement et persiste en arrière-plan."""
    if not player_name:
        return 0
    name = player_name.strip()
    cache_key = (game_id, name)
    base = get_player_score(name, game_id)  # charge la valeur persistée si absente du cache
    with _score_lock:
        new_score = base + points
        _score_cache[cache_key] = new_score
    _enqueue(_increment_sync, name, points, game_id)
    return new_score


def get_top_player_scores(
    limit: int = 20, game_id: str = "pedantix",
) -> List[Dict[str, Any]]:
    if game_id not in {item[0] for item in _GAME_CATALOG}:
        raise ValueError("Jeu inconnu.")
    try:
        with DatabaseContext() as db:
            db.execute(
                """SELECT ps.player_name, ps.score,
                          COALESCE(SUM(ugs.won), 0) AS wins,
                          COUNT(ugs.session_id) AS games_played,
                          ps.last_played
                   FROM player_game_scores ps
                   LEFT JOIN user_game_stats ugs
                     ON LOWER(ugs.username) = LOWER(ps.player_name)
                    AND ugs.game_id = ps.game_id
                   WHERE ps.game_id = ?
                   GROUP BY ps.player_name, ps.score, ps.last_played
                   ORDER BY ps.score DESC, wins DESC LIMIT ?""",
                (game_id, int(limit)),
            )
            return [_jsonable(row) for row in db.fetchall()]
    except Exception as e:
        logger.warning(f"get_top_player_scores: {e}")
        return []


def get_db_status() -> Dict[str, Any]:
    return {
        "configured_type": "postgresql" if IS_POSTGRES else "sqlite",
        "active_type": "postgresql" if _use_pg() else "sqlite",
        "pg_disabled": _pg_disabled,
        "is_postgres": IS_POSTGRES,
    }


# ---------------------------------------------------------------------------
# Comptes Utilisateurs & Statistiques
# ---------------------------------------------------------------------------
def hash_password(password: str, salt: Optional[str] = None) -> str:
    if not salt:
        salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000)
    return f"{salt}:{key.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt, key = stored_hash.split(":", 1)
        computed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000)
        return secrets.compare_digest(computed.hex(), key)
    except Exception:
        return False


def generate_user_token(username: str) -> str:
    salt = secrets.token_hex(16)
    sig = hashlib.sha256(f"{username}:{salt}:pedantix-auth".encode()).hexdigest()
    return f"{username}.{salt}.{sig}"


def verify_user_token(username: str, token: str) -> bool:
    if not username or not token:
        return False
    try:
        tok_user, salt, sig = token.split(".", 2)
        if tok_user.lower() != username.strip().lower():
            return False
        expected = hashlib.sha256(f"{tok_user}:{salt}:pedantix-auth".encode()).hexdigest()
        return secrets.compare_digest(expected, sig)
    except Exception:
        return False


def user_exists(username: str) -> bool:
    if not username:
        return False
    name = username.strip()
    try:
        with DatabaseContext() as db:
            db.execute("SELECT username FROM users WHERE LOWER(username) = LOWER(?)", (name,))
            return db.fetchone() is not None
    except Exception as e:
        logger.warning(f"user_exists: {e}")
        return False


def create_user(username: str, password: str) -> Dict[str, Any]:
    if not username or not password:
        return {"error": "Nom d'utilisateur et mot de passe requis."}
    name = username.strip()
    if len(name) < 2 or len(name) > 30:
        return {"error": "Le nom d'utilisateur doit contenir entre 2 et 30 caractères."}
    if len(password) < 3:
        return {"error": "Le mot de passe doit contenir au moins 3 caractères."}

    if user_exists(name):
        return {"error": "Ce nom d'utilisateur est déjà utilisé."}

    pwd_hash = hash_password(password)
    try:
        with DatabaseContext() as db:
            db.execute(
                """INSERT INTO users (username, password_hash, score, wins, games_played)
                   VALUES (?, ?, 0, 0, 0)""",
                (name, pwd_hash),
            )
            try:
                db.execute(
                    """INSERT INTO player_scores (player_name, score, wins, games_played, last_played)
                       VALUES (?, 0, 0, 0, CURRENT_TIMESTAMP)
                       ON CONFLICT (player_name) DO NOTHING""",
                    (name,),
                )
                db.execute(
                    """INSERT INTO player_game_scores (player_name, game_id, score, last_played)
                       VALUES (?, 'pedantix', 0, CURRENT_TIMESTAMP)
                       ON CONFLICT (player_name, game_id) DO NOTHING""",
                    (name,),
                )
            except Exception:
                pass

        token = generate_user_token(name)
        stats = get_user_stats(name)
        return {"status": "ok", "username": name, "token": token, "stats": stats}
    except Exception as e:
        logger.error(f"create_user: {e}")
        return {"error": "Erreur lors de la création du compte."}


def authenticate_user(username: str, password: str) -> Dict[str, Any]:
    if not username or not password:
        return {"error": "Identifiants requis."}
    name = username.strip()
    try:
        with DatabaseContext() as db:
            db.execute("SELECT * FROM users WHERE LOWER(username) = LOWER(?)", (name,))
            row = db.fetchone()
            if not row:
                return {"error": "Compte introuvable."}
            actual_username = row["username"]
            stored_hash = row["password_hash"]
            if not verify_password(password, stored_hash):
                return {"error": "Mot de passe incorrect."}

            try:
                db.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE username = ?", (actual_username,))
            except Exception:
                pass

        token = generate_user_token(actual_username)
        stats = get_user_stats(actual_username)
        return {"status": "ok", "username": actual_username, "token": token, "stats": stats}
    except Exception as e:
        logger.error(f"authenticate_user: {e}")
        return {"error": "Erreur de connexion."}


def get_all_usernames() -> List[str]:
    try:
        with DatabaseContext() as db:
            db.execute("SELECT username FROM users ORDER BY LOWER(username)")
            return [row["username"] for row in db.fetchall()]
    except Exception as e:
        logger.error(f"get_all_usernames: {e}")
        raise RuntimeError("Impossible de charger les comptes utilisateurs.") from e


def reset_user_password(username: str, password: str) -> bool:
    name = username.strip()
    try:
        with DatabaseContext() as db:
            db.execute("SELECT username FROM users WHERE LOWER(username) = LOWER(?)", (name,))
            row = db.fetchone()
            if not row:
                return False
            db.execute(
                "UPDATE users SET password_hash = ? WHERE username = ?",
                (hash_password(password), row["username"]),
            )
        return True
    except Exception as e:
        logger.error(f"reset_user_password: {e}")
        raise RuntimeError("Impossible de réinitialiser le mot de passe.") from e


def get_gate_progress(player_id: str) -> Dict[str, Any]:
    if not player_id:
        return {"step": 1, "completed": False, "attempts": 0, "last_attempt": 0}
    try:
        with DatabaseContext() as db:
            db.execute(
                "SELECT current_step, completed, attempts, last_attempt_at FROM secret_gate_progress WHERE player_id = ?",
                (player_id,),
            )
            row = db.fetchone()
            if row:
                return {
                    "step": row["current_step"],
                    "completed": bool(row["completed"]),
                    "attempts": row["attempts"],
                    "last_attempt": row["last_attempt_at"],
                }
    except Exception as e:
        logger.warning(f"get_gate_progress: {e}")
    return {"step": 1, "completed": False, "attempts": 0, "last_attempt": 0}


def save_gate_progress(
    player_id: str,
    step: int,
    completed: bool,
    attempts: int,
    last_attempt: float,
    username: Optional[str] = None,
):
    if not player_id:
        return
    try:
        with DatabaseContext() as db:
            db.execute(
                """INSERT INTO secret_gate_progress (player_id, current_step, completed, attempts, last_attempt_at, unlocked_at, username)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(player_id) DO UPDATE SET
                       current_step = excluded.current_step,
                       completed = excluded.completed,
                       attempts = excluded.attempts,
                       last_attempt_at = excluded.last_attempt_at,
                       unlocked_at = CASE WHEN excluded.completed = 1 AND secret_gate_progress.completed = 0 THEN excluded.unlocked_at ELSE secret_gate_progress.unlocked_at END,
                       username = COALESCE(excluded.username, secret_gate_progress.username)""",
                (
                    player_id,
                    step,
                    1 if completed else 0,
                    attempts,
                    last_attempt,
                    time.time() if completed else 0,
                    username,
                ),
            )
    except Exception as e:
        logger.warning(f"save_gate_progress: {e}")


def is_gate_unlocked(player_id: Optional[str] = None, username: Optional[str] = None) -> bool:
    try:
        with DatabaseContext() as db:
            if player_id:
                db.execute("SELECT completed FROM secret_gate_progress WHERE player_id = ? AND completed = 1", (player_id,))
                row = db.fetchone()
                if row:
                    return True
            if username:
                db.execute("SELECT completed FROM secret_gate_progress WHERE LOWER(username) = LOWER(?) AND completed = 1", (username,))
                row = db.fetchone()
                if row:
                    return True
    except Exception as e:
        logger.warning(f"is_gate_unlocked: {e}")
    return False


def reset_gate_progress(player_id: Optional[str] = None, username: Optional[str] = None) -> None:
    try:
        with DatabaseContext() as db:
            if player_id:
                db.execute("DELETE FROM secret_gate_progress WHERE player_id = ?", (player_id,))
            if username:
                db.execute("DELETE FROM secret_gate_progress WHERE LOWER(username) = LOWER(?)", (username,))
    except Exception as e:
        logger.warning(f"reset_gate_progress: {e}")



def _record_user_guess_word_sync(username: str, word: str):
    if not username or not word:
        return
    clean_word = word.strip().lower()
    if len(clean_word) < 2:
        return
    try:
        with DatabaseContext() as db:
            db.execute(
                """INSERT INTO user_words (username, word, count) VALUES (?, ?, 1)
                   ON CONFLICT (username, word) DO UPDATE SET count = user_words.count + 1""",
                (username.strip(), clean_word),
            )
    except Exception as e:
        logger.warning(f"_record_user_guess_word_sync: {e}")


def record_user_guess_word(username: str, word: str):
    if username and word:
        _enqueue(_record_user_guess_word_sync, username, word)


def _record_user_game_finish_sync(
    username: str,
    won: bool,
    attempts: int,
    points: int,
    session_id: str,
    mode: str,
    title: str,
    surrendered: bool,
    duration_seconds: int,
    revealed_words: int,
    total_words: int,
    game_id: str = "pedantix",
    difficulty: Optional[str] = None,
    metrics: Optional[Dict[str, Any]] = None,
):
    if not username:
        return
    name = username.strip()
    try:
        with DatabaseContext() as db:
            db.execute("SELECT username FROM users WHERE LOWER(username) = LOWER(?)", (name,))
            row = db.fetchone()
            actual_name = row["username"] if row else name
            metrics_json = json.dumps(metrics or {}, ensure_ascii=False)
            db.execute(
                """INSERT INTO game_sessions
                       (session_id, game_id, mode, title, difficulty, metadata_json, finished_at)
                   VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT (session_id) DO UPDATE SET
                       game_id = EXCLUDED.game_id, mode = EXCLUDED.mode,
                       title = EXCLUDED.title, difficulty = EXCLUDED.difficulty,
                       finished_at = COALESCE(game_sessions.finished_at, EXCLUDED.finished_at)""",
                (
                    session_id, game_id, mode, title, difficulty,
                    "{}",
                ),
            )
            cursor = db.execute(
                """INSERT INTO user_game_stats
                       (username, session_id, game_id, mode, difficulty, metrics_json,
                        title, won, surrendered, attempts, duration_seconds, points,
                        revealed_words, total_words)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT (username, session_id) DO NOTHING""",
                (
                    actual_name, session_id, game_id, mode, difficulty, metrics_json,
                    title, int(won), int(surrendered), max(0, attempts),
                    max(0, duration_seconds), max(0, points),
                    max(0, revealed_words), max(0, total_words),
                ),
            )
            if cursor.rowcount == 0:
                return

            db.execute(
                """INSERT INTO player_game_scores (player_name, game_id, score, last_played)
                   VALUES (?, ?, 0, CURRENT_TIMESTAMP)
                   ON CONFLICT (player_name, game_id) DO UPDATE SET
                       last_played = CURRENT_TIMESTAMP""",
                (actual_name, game_id),
            )
            if row and game_id == "pedantix":
                db.execute(
                    """UPDATE users SET
                           games_played = games_played + 1,
                           wins = wins + ?,
                           best_attempts = CASE
                               WHEN ? = 1 AND ? > 0
                                   THEN CASE
                                       WHEN best_attempts IS NULL OR best_attempts > ? THEN ?
                                       ELSE best_attempts
                                   END
                               ELSE best_attempts
                           END,
                           total_attempts = total_attempts + ?,
                           score = score + ?,
                           last_login = CURRENT_TIMESTAMP
                       WHERE username = ?""",
                    (
                        int(won), int(won), attempts, attempts, attempts,
                        max(0, attempts), max(0, points), actual_name,
                    ),
                )
    except Exception as e:
        logger.warning(f"_record_user_game_finish_sync: {e}")


def record_user_game_finish(
    username: str,
    won: bool,
    attempts: int,
    points: int = 0,
    *,
    session_id: Optional[str] = None,
    mode: str = "solo",
    title: str = "",
    surrendered: bool = False,
    duration_seconds: int = 0,
    revealed_words: int = 0,
    total_words: int = 0,
    game_id: str = "pedantix",
    difficulty: Optional[str] = None,
    metrics: Optional[Dict[str, Any]] = None,
):
    if not username:
        return
    if game_id not in {item[0] for item in _GAME_CATALOG}:
        raise ValueError("Jeu inconnu.")
    _enqueue(
        _record_user_game_finish_sync,
        username.strip(),
        won,
        attempts,
        points,
        session_id or str(uuid.uuid4()),
        mode if mode in ("solo", "multiplayer", "team") else "solo",
        title,
        surrendered,
        duration_seconds,
        revealed_words,
        total_words,
        game_id,
        difficulty,
        metrics,
    )


def _format_mode_stats(row: Dict[str, Any]) -> Dict[str, Any]:
    games_played = int(row["finished_games"] or 0)
    wins = int(row["won_games"] or 0)
    return {
        "games_played": games_played,
        "wins": wins,
        "win_rate": round(wins / games_played * 100, 1) if games_played else 0.0,
        "avg_attempts": round(float(row["avg_attempts"]), 1) if row["avg_attempts"] is not None else None,
        "avg_winning_attempts": (
            round(float(row["avg_winning_attempts"]), 1)
            if row["avg_winning_attempts"] is not None else None
        ),
        "best_attempts": int(row["best_score"]) if row["best_score"] is not None else None,
        "avg_time_seconds": round(float(row["avg_time_seconds"]), 1) if row["avg_time_seconds"] is not None else None,
        "avg_revealed_pct": (
            round(float(row["avg_revealed_pct"]), 1)
            if row["avg_revealed_pct"] is not None else None
        ),
        "points": int(row["points"] or 0) if "points" in row.keys() else 0,
    }


def _empty_mode_stats() -> Dict[str, Any]:
    return {
        "games_played": 0,
        "wins": 0,
        "win_rate": 0.0,
        "avg_attempts": None,
        "avg_winning_attempts": None,
        "best_attempts": None,
        "avg_time_seconds": None,
        "avg_revealed_pct": None,
        "points": 0,
    }


def _summarize_game_metrics(game_id: str, metric_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    metrics = []
    for row in metric_rows:
        try:
            value = row["metrics_json"]
            metrics.append(json.loads(value) if value else {})
        except (TypeError, json.JSONDecodeError):
            metrics.append({})

    def numbers(key: str) -> List[float]:
        return [
            float(value[key])
            for value in metrics
            if isinstance(value.get(key), (int, float))
        ]

    if game_id in ("cemantix", "chiffrantix"):
        similarity = numbers("best_similarity")
        return {
            "avg_best_similarity": round(sum(similarity) / len(similarity), 1) if similarity else None,
            "best_similarity": round(max(similarity), 1) if similarity else None,
        }
    if game_id == "sudoku":
        mistakes = numbers("mistakes")
        return {
            "avg_mistakes": round(sum(mistakes) / len(mistakes), 1) if mistakes else None,
            "solved_games": sum(value.get("finish_reason") == "solved" for value in metrics),
        }
    if game_id == "battleship":
        attacks = numbers("attacks")
        hits = numbers("hits")
        sunk = numbers("ships_sunk")
        total_attacks = sum(attacks)
        return {
            "avg_attacks": round(total_attacks / len(attacks), 1) if attacks else None,
            "hit_rate": round(sum(hits) / total_attacks * 100, 1) if total_attacks else 0.0,
            "avg_ships_sunk": round(sum(sunk) / len(sunk), 1) if sunk else None,
        }
    if game_id == "motus":
        scores = numbers("score")
        return {
            "avg_score": round(sum(scores) / len(scores), 1) if scores else None,
            "best_score": max(scores) if scores else None,
        }
    if game_id == "geoguessr":
        scores = numbers("score")
        distances = numbers("average_distance_km")
        return {
            "avg_score": round(sum(scores) / len(scores), 1) if scores else None,
            "best_score": max(scores) if scores else None,
            "avg_distance_km": round(sum(distances) / len(distances), 1) if distances else None,
        }
    if game_id == "bitoguessr":
        scores = numbers("score")
        correct = numbers("correct_answers")
        rounds = numbers("rounds")
        total_rounds = sum(rounds)
        return {
            "avg_score": round(sum(scores) / len(scores), 1) if scores else None,
            "best_score": max(scores) if scores else None,
            "avg_accuracy": round(sum(correct) / total_rounds * 100, 1) if total_rounds else None,
        }
    return {}


def get_user_stats(username: str, game_id: str = "pedantix") -> Dict[str, Any]:
    empty = {
        "username": username or "",
        "game_id": game_id,
        "games_played": 0,
        "wins": 0,
        "win_rate": 0.0,
        "score": 0,
        "best_attempts": None,
        "avg_attempts": None,
        "avg_winning_attempts": None,
        "avg_time_seconds": None,
        "avg_revealed_pct": None,
        "solo": _empty_mode_stats(),
        "multiplayer": _empty_mode_stats(),
        "difficulty_breakdown": {},
        "game_metrics": {},
        "favorite_words": [],
        "recent_games": [],
        "created_at": None,
    }
    if not username:
        return empty
    if game_id not in {item[0] for item in _GAME_CATALOG}:
        raise ValueError("Jeu inconnu.")
    name = username.strip()
    try:
        with DatabaseContext() as db:
            db.execute("SELECT * FROM users WHERE LOWER(username) = LOWER(?)", (name,))
            user_row = db.fetchone()
            actual_name = user_row["username"] if user_row else name
            user_dict = _jsonable(user_row) if user_row else {}

            db.execute(
                """SELECT
                       COUNT(*) AS finished_games,
                       SUM(won) AS won_games,
                       SUM(points) AS points,
                       AVG(attempts) AS avg_attempts,
                       AVG(CASE WHEN won = 1 THEN attempts END) AS avg_winning_attempts,
                       MIN(CASE WHEN won = 1 AND attempts > 0 THEN attempts END) AS best_score,
                       AVG(duration_seconds) AS avg_time_seconds,
                       AVG(CASE WHEN total_words > 0 THEN 100.0 * revealed_words / total_words END) AS avg_revealed_pct
                   FROM user_game_stats
                   WHERE LOWER(username) = LOWER(?) AND game_id = ?""",
                (actual_name, game_id),
            )
            totals = _format_mode_stats(db.fetchone())

            db.execute(
                """SELECT
                       CASE WHEN mode = 'solo' THEN 'solo' ELSE 'multiplayer' END AS game_type,
                       COUNT(*) AS finished_games,
                       SUM(won) AS won_games,
                       SUM(points) AS points,
                       AVG(attempts) AS avg_attempts,
                       AVG(CASE WHEN won = 1 THEN attempts END) AS avg_winning_attempts,
                       MIN(CASE WHEN won = 1 AND attempts > 0 THEN attempts END) AS best_score,
                       AVG(duration_seconds) AS avg_time_seconds,
                       AVG(CASE WHEN total_words > 0 THEN 100.0 * revealed_words / total_words END) AS avg_revealed_pct
                   FROM user_game_stats
                   WHERE LOWER(username) = LOWER(?)
                     AND game_id = ?
                   GROUP BY game_type""",
                (actual_name, game_id),
            )
            mode_stats = {"solo": _empty_mode_stats(), "multiplayer": _empty_mode_stats()}
            for stats_row in db.fetchall():
                mode_stats[stats_row["game_type"]] = _format_mode_stats(stats_row)

            db.execute(
                """SELECT word, count FROM user_words
                   WHERE LOWER(username) = LOWER(?) AND ? = 'pedantix'
                   ORDER BY count DESC, word ASC LIMIT 8""",
                (actual_name, game_id),
            )
            fav_words = [{"word": r["word"], "count": int(r["count"])} for r in db.fetchall()]
            db.execute(
                """SELECT game_id, mode, difficulty, title, won, surrendered, attempts,
                          duration_seconds, points, metrics_json, finished_at
                   FROM user_game_stats
                   WHERE LOWER(username) = LOWER(?) AND game_id = ?
                   ORDER BY finished_at DESC, id DESC LIMIT 15""",
                (actual_name, game_id),
            )
            recent_games = [_user_game_row(row) for row in db.fetchall()]
            db.execute(
                """SELECT difficulty, COUNT(*) AS games_played, SUM(won) AS wins
                   FROM user_game_stats
                   WHERE LOWER(username) = LOWER(?) AND game_id = ?
                   GROUP BY difficulty ORDER BY difficulty""",
                (actual_name, game_id),
            )
            difficulty_breakdown = {
                row["difficulty"] or "non précisée": {
                    "games_played": int(row["games_played"] or 0),
                    "wins": int(row["wins"] or 0),
                }
                for row in db.fetchall()
            }
            db.execute(
                """SELECT metrics_json FROM user_game_stats
                   WHERE LOWER(username) = LOWER(?) AND game_id = ?""",
                (actual_name, game_id),
            )
            game_metrics = _summarize_game_metrics(game_id, db.fetchall())
            db.execute(
                """SELECT score FROM player_game_scores
                   WHERE LOWER(player_name) = LOWER(?) AND game_id = ?""",
                (actual_name, game_id),
            )
            score_row = db.fetchone()
            if game_id == "pedantix":
                score = int(score_row["score"]) if score_row else int(user_dict.get("score") or 0)
            else:
                score = totals["points"]

            return {
                "username": user_dict.get("username", actual_name),
                "game_id": game_id,
                **totals,
                "score": score,
                "solo": mode_stats["solo"],
                "multiplayer": mode_stats["multiplayer"],
                "difficulty_breakdown": difficulty_breakdown,
                "game_metrics": game_metrics,
                "favorite_words": fav_words,
                "recent_games": recent_games,
                "created_at": user_dict.get("created_at"),
            }
    except Exception as e:
        logger.warning(f"get_user_stats: {e}")
        return empty
