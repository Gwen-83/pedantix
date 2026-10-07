"""
Couche base de données de Pédantix.

- Supabase (PostgreSQL) si DATABASE_URL / SUPABASE_DB_URL est défini, sinon SQLite local.
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
import datetime as _dt
import hashlib
import secrets
from typing import Any, Dict, List, Optional

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


# ---------------------------------------------------------------------------
# Schéma
# ---------------------------------------------------------------------------
_SCHEMA_PG = [
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
    """CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY, password_hash TEXT NOT NULL,
        score INTEGER DEFAULT 0, wins INTEGER DEFAULT 0,
        games_played INTEGER DEFAULT 0, best_attempts INTEGER,
        total_attempts INTEGER DEFAULT 0,
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        last_login TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS user_words (
        username TEXT NOT NULL, word TEXT NOT NULL, count INTEGER DEFAULT 1,
        PRIMARY KEY (username, word))""",
    "CREATE INDEX IF NOT EXISTS idx_guesses_session ON guesses(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_games_finished ON games(finished_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_article_category ON article_cache(category)",
    "CREATE INDEX IF NOT EXISTS idx_user_words_user ON user_words(username)",
]

_SCHEMA_SQLITE = [
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
    """CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY, password_hash TEXT NOT NULL,
        score INTEGER DEFAULT 0, wins INTEGER DEFAULT 0,
        games_played INTEGER DEFAULT 0, best_attempts INTEGER,
        total_attempts INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_login TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS user_words (
        username TEXT NOT NULL, word TEXT NOT NULL, count INTEGER DEFAULT 1,
        PRIMARY KEY (username, word))""",
    "CREATE INDEX IF NOT EXISTS idx_guesses_session ON guesses(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_user_words_user ON user_words(username)",
]


def init_db() -> bool:
    """Crée les tables. Retourne True si OK. Ne lève jamais d'exception."""
    try:
        with DatabaseContext() as db:
            for stmt in (_SCHEMA_PG if db.is_pg else _SCHEMA_SQLITE):
                db.execute(stmt)
            logger.info(f"Base de données prête ({'Supabase/PostgreSQL' if db.is_pg else 'SQLite'})")
        return True
    except Exception as e:
        logger.error(f"init_db a échoué : {e}")
        return False


def db_backend() -> str:
    return "postgres" if _use_pg() else "sqlite"


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


def get_random_cached_article(category: Optional[str] = None) -> Optional[Dict[str, Any]]:
    try:
        with DatabaseContext() as db:
            if category:
                db.execute("SELECT * FROM article_cache WHERE category = ? ORDER BY RANDOM() LIMIT 1", (category,))
            else:
                db.execute("SELECT * FROM article_cache ORDER BY RANDOM() LIMIT 1")
            row = db.fetchone()
            return _row_to_article(row) if row else None
    except Exception as e:
        logger.warning(f"get_random_cached_article: {e}")
        return None


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


def record_game_finish(session_id: str, won: bool, surrendered: bool, attempts: int,
                       revealed_words: int, elapsed_time: int):
    _enqueue(_record_game_finish_sync, session_id, won, surrendered, attempts, revealed_words, elapsed_time)


def get_stats() -> Dict[str, Any]:
    empty = {"total_games": 0, "won_games": 0, "win_rate": 0, "avg_attempts": 0, "best_score": 0, "recent_games": []}
    try:
        with DatabaseContext() as db:
            db.execute("SELECT COUNT(*) AS total_games FROM games")
            total_games = (db.fetchone() or {"total_games": 0})["total_games"]

            db.execute("SELECT COUNT(*) AS won_games FROM games WHERE won = 1")
            won_games = (db.fetchone() or {"won_games": 0})["won_games"]

            db.execute("SELECT AVG(attempts_count) AS avg_attempts FROM games WHERE won = 1")
            r = db.fetchone()
            avg = r["avg_attempts"] if r else None
            avg_attempts = round(float(avg), 1) if avg else 0

            db.execute("SELECT MIN(attempts_count) AS best_score FROM games WHERE won = 1")
            r = db.fetchone()
            best_score = r["best_score"] if r and r["best_score"] is not None else 0

            db.execute(
                """SELECT title, mode, category, won, surrendered, attempts_count, time_seconds, finished_at
                   FROM games WHERE finished_at IS NOT NULL ORDER BY finished_at DESC LIMIT 10"""
            )
            recent = [_jsonable(row) for row in db.fetchall()]

            return {
                "total_games": total_games,
                "won_games": won_games,
                "win_rate": round(won_games / total_games * 100, 1) if total_games else 0,
                "avg_attempts": avg_attempts,
                "best_score": best_score,
                "recent_games": recent,
            }
    except Exception as e:
        logger.warning(f"get_stats: {e}")
        return empty


# ---------------------------------------------------------------------------
# Scores des joueurs
# ---------------------------------------------------------------------------
# Petit cache mémoire : évite un aller-retour réseau vers Supabase à chaque
# création de joueur / rafraîchissement de score pendant une partie.
_score_cache: Dict[str, int] = {}
_score_lock = threading.Lock()


def get_player_score(player_name: str) -> int:
    if not player_name:
        return 0
    name = player_name.strip()
    with _score_lock:
        if name in _score_cache:
            return _score_cache[name]
    score = 0
    try:
        with DatabaseContext() as db:
            db.execute("SELECT score FROM player_scores WHERE player_name = ?", (name,))
            row = db.fetchone()
            score = int(row["score"]) if row else 0
    except Exception as e:
        logger.warning(f"get_player_score: {e}")
    with _score_lock:
        _score_cache[name] = score
    return score


def _increment_sync(name: str, points: int):
    with DatabaseContext() as db:
        db.execute(
            """INSERT INTO player_scores (player_name, score, wins, games_played, last_played)
               VALUES (?, ?, 1, 1, CURRENT_TIMESTAMP)
               ON CONFLICT (player_name) DO UPDATE SET
                   score = player_scores.score + EXCLUDED.score,
                   wins = player_scores.wins + 1,
                   games_played = player_scores.games_played + 1,
                   last_played = CURRENT_TIMESTAMP""",
            (name, points),
        )


def increment_player_score(player_name: str, points: int = 1) -> int:
    """Met à jour le cache immédiatement et persiste en arrière-plan."""
    if not player_name:
        return 0
    name = player_name.strip()
    base = get_player_score(name)  # charge la valeur persistée si absente du cache
    with _score_lock:
        new_score = base + points
        _score_cache[name] = new_score
    _enqueue(_increment_sync, name, points)
    return new_score


def get_top_player_scores(limit: int = 20) -> List[Dict[str, Any]]:
    try:
        with DatabaseContext() as db:
            db.execute(
                """SELECT player_name, score, wins, games_played, last_played
                   FROM player_scores ORDER BY score DESC, wins DESC LIMIT ?""",
                (int(limit),),
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


def _record_user_game_finish_sync(username: str, won: bool, attempts: int, points: int):
    if not username:
        return
    name = username.strip()
    try:
        with DatabaseContext() as db:
            db.execute("SELECT * FROM users WHERE LOWER(username) = LOWER(?)", (name,))
            row = db.fetchone()
            if not row:
                return
            row_dict = dict(row)
            actual_name = row_dict["username"]
            cur_best = row_dict.get("best_attempts")
            new_best = cur_best
            if won and attempts > 0:
                new_best = min(cur_best, attempts) if cur_best is not None else attempts

            db.execute(
                """UPDATE users SET
                       games_played = games_played + 1,
                       wins = wins + ?,
                       best_attempts = ?,
                       total_attempts = total_attempts + ?,
                       score = score + ?,
                       last_login = CURRENT_TIMESTAMP
                   WHERE username = ?""",
                (1 if won else 0, new_best, attempts, points, actual_name),
            )
    except Exception as e:
        logger.warning(f"_record_user_game_finish_sync: {e}")


def record_user_game_finish(username: str, won: bool, attempts: int, points: int = 0):
    if username:
        _enqueue(_record_user_game_finish_sync, username, won, attempts, points)


def get_user_stats(username: str) -> Dict[str, Any]:
    empty = {
        "username": username or "",
        "games_played": 0,
        "wins": 0,
        "win_rate": 0.0,
        "score": 0,
        "best_attempts": None,
        "avg_attempts": 0.0,
        "favorite_words": [],
        "created_at": None,
    }
    if not username:
        return empty
    name = username.strip()
    try:
        with DatabaseContext() as db:
            db.execute("SELECT * FROM users WHERE LOWER(username) = LOWER(?)", (name,))
            user_row = db.fetchone()
            if not user_row:
                score = get_player_score(name)
                empty["score"] = score
                return empty

            user_dict = _jsonable(user_row)
            games_played = int(user_dict.get("games_played") or 0)
            wins = int(user_dict.get("wins") or 0)
            score = int(user_dict.get("score") or 0)
            best_attempts = user_dict.get("best_attempts")
            total_attempts = int(user_dict.get("total_attempts") or 0)
            avg_attempts = round(total_attempts / max(1, games_played), 1) if games_played > 0 else 0.0
            win_rate = round((wins / max(1, games_played)) * 100, 1) if games_played > 0 else 0.0

            db.execute(
                "SELECT word, count FROM user_words WHERE LOWER(username) = LOWER(?) ORDER BY count DESC, word ASC LIMIT 8",
                (name,),
            )
            fav_words = [{"word": r["word"], "count": int(r["count"])} for r in db.fetchall()]

            return {
                "username": user_dict["username"],
                "games_played": games_played,
                "wins": wins,
                "win_rate": win_rate,
                "score": score,
                "best_attempts": best_attempts,
                "avg_attempts": avg_attempts,
                "favorite_words": fav_words,
                "created_at": user_dict.get("created_at"),
            }
    except Exception as e:
        logger.warning(f"get_user_stats: {e}")
        return empty

