import uuid
import time
import random
import os
import json
from typing import Dict, Any, List, Optional, Set

from app.nlp import normalize_text, check_match, calculate_proximity, is_valid_french_word, normalize_letter, is_letter_revealed
from app.synonym_api import SYNONYM_API
from app.tokenizer import ArticleTokenizer
from app.wiki import WikipediaClient, ALL_CURATED_TITLES
from app.database import (
    record_game_start, record_guess, record_game_finish,
    get_cached_article, get_random_cached_article, cache_article
)

class GameSession:
    def __init__(
        self,
        session_id: str,
        seed: str,
        title: str,
        url: str,
        image: str,
        paragraphs: List[str],
        mode: str,
        category: str,
        difficulty: str = "moyen",
        lang_count: int = 0,
        pageviews_90d: int = 0
    ):
        self.session_id = session_id
        self.seed = seed
        self.title = title
        self.url = url
        self.image = image
        self.paragraphs = paragraphs
        self.mode = mode
        self.category = category
        self.difficulty = difficulty
        self.lang_count = lang_count
        self.pageviews_90d = pageviews_90d
        self.created_at = time.time()

        # Tokenize article
        token_data = ArticleTokenizer.process_article(title, paragraphs)
        self.tokens: List[Dict[str, Any]] = token_data["tokens"]
        self.title_word_ids: List[int] = token_data["title_word_ids"]
        self.significant_title_ids: List[int] = token_data["significant_title_ids"]
        self.body_word_ids: List[int] = token_data["body_word_ids"]
        self.total_words: int = token_data["total_words"]

        # Tokens mapping by ID
        self.tokens_by_id: Dict[int, Dict[str, Any]] = {t["id"]: t for t in self.tokens}

        # Guesses tracking
        self.attempts: int = 0
        self.guesses_history: List[Dict[str, Any]] = []
        self.guessed_words: Set[str] = set()
        self.revealed_word_ids: Set[int] = set()
        self.token_heat: Dict[int, int] = {}  # token_id -> highest proximity score (48-100)
        self.token_close_words: Dict[int, Dict[str, Any]] = {}  # token_id -> {"score": score_int, "word": clean_word}

        # Precompute context vocabulary for semantic warmth
        self.context_words: Set[str] = set()
        for t in self.tokens:
            if t["is_word"] and t["normalized"]:
                self.context_words.add(t["normalized"])

        # Background prefetching of significant title words
        title_words = [
            t["normalized"] for t in self.tokens
            if t["is_title"] and t["is_word"] and t["normalized"] and len(t["normalized"]) > 2
        ]
        if title_words:
            SYNONYM_API.prefetch_words(title_words)

        self.is_won: bool = False
        self.is_surrendered: bool = False

        # Save game start to DB
        record_game_start(
            session_id=self.session_id,
            seed=self.seed,
            title=self.title,
            url=self.url,
            image=self.image,
            mode=self.mode,
            category=self.category,
            total_words=self.total_words
        )

    def submit_guess(self, word: str) -> Dict[str, Any]:
        """Processes a player guess word."""
        clean_word = word.strip()
        if not clean_word:
            return {"error": "Mot vide."}

        if not is_valid_french_word(clean_word, self.context_words):
            return {
                "error": f"Le mot « {clean_word} » n'est pas français ou n'existe pas dans le dictionnaire.",
                "status": "invalid_word",
                "word": clean_word
            }

        norm_guess = normalize_text(clean_word)
        is_repeat = norm_guess in self.guessed_words

        newly_revealed: Dict[int, str] = {}
        all_matched_ids: List[int] = []

        # Find exact or morphological matches
        for t in self.tokens:
            if t["is_word"]:
                if check_match(clean_word, t["text"]):
                    all_matched_ids.append(t["id"])
                    if not t["revealed"]:
                        t["revealed"] = True
                        self.revealed_word_ids.add(t["id"])
                        self.token_heat.pop(t["id"], None)
                        self.token_close_words.pop(t["id"], None)
                        newly_revealed[t["id"]] = t["text"]

        # If already written or all occurrences were already found
        if is_repeat or (len(all_matched_ids) > 0 and len(newly_revealed) == 0):
            self.guessed_words.add(norm_guess)
            return {
                "status": "already_guessed",
                "is_repeat": True,
                "message": "Déjà écrit",
                "word": clean_word,
                "attempt_number": self.attempts,
                "matches_count": 0,
                "score": 0,
                "newly_revealed": {},
                "close_tokens": [],
                "is_won": self.is_won,
                "is_surrendered": self.is_surrendered,
                "revealed_words_count": len(self.revealed_word_ids),
                "total_words": self.total_words,
                "history": self.guesses_history
            }

        self.attempts += 1
        self.guessed_words.add(norm_guess)
        if len(norm_guess) > 2:
            SYNONYM_API.prefetch_words([norm_guess])

        close_tokens: List[Dict[str, Any]] = []
        max_score = 0
        for t in self.tokens:
            if t["is_word"] and not t["revealed"]:
                prox = calculate_proximity(clean_word, t["text"], self.context_words)
                if prox >= 48.0:
                    score_int = round(prox)
                    if score_int > max_score:
                        max_score = score_int
                    current_heat = self.token_heat.get(t["id"], 0)
                    if score_int > current_heat:
                        self.token_heat[t["id"]] = score_int
                        self.token_close_words[t["id"]] = {
                            "score": score_int,
                            "word": clean_word
                        }
                        close_tokens.append({
                            "id": t["id"],
                            "score": score_int,
                            "word": clean_word
                        })

        if all_matched_ids:
            status = "match"
        elif max_score >= 48:
            status = "close"
        else:
            status = "miss"

        # Record guess in history
        matches_count = len(all_matched_ids)
        if not is_repeat:
            guess_record = {
                "attempt": self.attempts,
                "word": clean_word,
                "status": status,
                "count": matches_count,
                "score": max_score if status == "close" else (100 if status == "match" else 0),
                "timestamp": round(time.time() - self.created_at)
            }
            self.guesses_history.append(guess_record)
            record_guess(
                session_id=self.session_id,
                attempt_num=self.attempts,
                word=clean_word,
                status=status,
                matches_count=matches_count
            )

        # Check win condition (all significant title words revealed)
        if not self.is_won and not self.is_surrendered:
            sig_unrevealed = [tid for tid in self.significant_title_ids if tid not in self.revealed_word_ids]
            if len(sig_unrevealed) == 0:
                self.is_won = True
                # Automatically reveal all title tokens
                for tid in self.title_word_ids:
                    t = self.tokens_by_id[tid]
                    self.token_heat.pop(tid, None)
                    self.token_close_words.pop(tid, None)
                    if not t["revealed"]:
                        t["revealed"] = True
                        self.revealed_word_ids.add(tid)
                        newly_revealed[tid] = t["text"]

                elapsed = int(time.time() - self.created_at)
                record_game_finish(
                    session_id=self.session_id,
                    won=True,
                    surrendered=False,
                    attempts=self.attempts,
                    revealed_words=len(self.revealed_word_ids),
                    elapsed_time=elapsed
                )

        return {
            "status": status,
            "word": clean_word,
            "attempt_number": self.attempts,
            "matches_count": matches_count,
            "score": max_score if status == "close" else (100 if status == "match" else 0),
            "newly_revealed": {str(k): v for k, v in newly_revealed.items()},
            "close_tokens": close_tokens,
            "is_won": self.is_won,
            "is_surrendered": self.is_surrendered,
            "revealed_words_count": len(self.revealed_word_ids),
            "total_words": self.total_words,
            "history": self.guesses_history
        }

    def surrender(self) -> Dict[str, Any]:
        """L'abandon est désactivé : il faut trouver le titre !"""
        return {"error": "L'abandon et la révélation du mot secret sont désactivés."}

    def unmask_all(self) -> Dict[str, Any]:
        """Démasque entièrement tous les mots de l'article pour le joueur."""
        if not (self.is_won or self.is_surrendered):
            return {"error": "L'article ne peut être démasqué qu'une fois la manche terminée."}

        tokens_map: Dict[str, str] = {}
        for t in self.tokens:
            t["revealed"] = True
            if t.get("is_word") or t.get("type") == "word":
                self.revealed_word_ids.add(t["id"])
                tokens_map[str(t["id"])] = t["text"]

        return {
            "status": "ok",
            "message": "Article entièrement démasqué.",
            "tokens": tokens_map,
            "total_revealed": len(self.revealed_word_ids),
            "total_words": self.total_words
        }

    def get_public_state(self, revealed_letters: Optional[List[str]] = None) -> Dict[str, Any]:
        """Returns the masked board representation safe for the client."""
        client_tokens = []
        rev_set = set(revealed_letters or [])

        for t in self.tokens:
            if t["type"] in ("space", "punct") or t["revealed"]:
                client_tokens.append({
                    "id": t["id"],
                    "type": t["type"],
                    "text": t["text"],
                    "revealed": True,
                    "is_word": t.get("is_word", False),
                    "is_title": t["is_title"],
                    "paragraph_idx": t["paragraph_idx"]
                })
            else:
                tok_dict = {
                    "id": t["id"],
                    "type": "word",
                    "length": t["length"],
                    "revealed": False,
                    "is_word": True,
                    "is_title": t["is_title"],
                    "paragraph_idx": t["paragraph_idx"]
                }
                if rev_set:
                    tok_text = t.get("text", "")
                    tok_dict["hint_pattern"] = "".join(
                        ch if is_letter_revealed(ch, rev_set) else "_"
                        for ch in tok_text
                    )
                if t["id"] in self.token_close_words:
                    tok_dict["heat"] = self.token_close_words[t["id"]]["score"]
                    tok_dict["close_word"] = self.token_close_words[t["id"]]["word"]
                elif t["id"] in self.token_heat:
                    tok_dict["heat"] = self.token_heat[t["id"]]
                client_tokens.append(tok_dict)

        return {
            "session_id": self.session_id,
            "seed": self.seed,
            "mode": self.mode,
            "category": self.category,
            "difficulty": self.difficulty,
            "lang_count": self.lang_count,
            "pageviews_90d": self.pageviews_90d,
            "tokens": client_tokens,
            "attempts": self.attempts,
            "revealed_words_count": len(self.revealed_word_ids),
            "total_words": self.total_words,
            "is_won": self.is_won,
            "is_surrendered": self.is_surrendered,
            "history": self.guesses_history,
            "solution": {
                "title": self.title,
                "url": self.url,
                "image": self.image
            } if (self.is_won or self.is_surrendered) else None
        }


class GameManager:
    def __init__(self):
        self.sessions: Dict[str, GameSession] = {}
        self.wiki_client = WikipediaClient()
        self.offline_curated: Dict[str, Any] = {}
        self._load_offline_curated()

    def _load_offline_curated(self):
        json_path = os.path.join(os.path.dirname(__file__), "curated_articles.json")
        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    self.offline_curated = json.load(f)
            except Exception:
                pass

    def create_game(
        self,
        mode: str = "curated",
        category: Optional[str] = None,
        query: Optional[str] = None,
        date_str: Optional[str] = None,
        difficulty: str = "moyen"
    ) -> GameSession:
        session_id = str(uuid.uuid4())
        seed_num = random.randint(1000, 9999)
        seed = f"P-{seed_num}"

        article_data = None

        # 1. Custom query or URL
        if query:
            article_data = self.wiki_client.search_and_fetch(query)

        # 2. Daily mode
        elif mode == "daily" and date_str:
            article_data = self.wiki_client.get_daily_article(date_str)
            seed = f"D-{date_str}"

        # 3. By specific category/theme
        elif category and category in ("histoire", "geographie", "sciences", "monuments", "biographies", "arts_culture", "nature", "tech_jeux", "litterature"):
            article_data = self.wiki_client.fetch_curated_article(category, difficulty=difficulty)
            if not article_data:
                article_data = get_random_cached_article(category)

        # 4. Random French Wikipedia article meeting difficulty criteria
        if not article_data:
            article_data = self.wiki_client.fetch_random_wikipedia_article(difficulty=difficulty)
            if not article_data and self.offline_curated:
                article_data = random.choice(list(self.offline_curated.values()))
            if not article_data:
                article_data = get_random_cached_article()

        # Ultimate fallback
        if not article_data:
            article_data = {
                "title": "Tour Eiffel",
                "paragraphs": [
                    "La tour Eiffel est une tour autoportante de fer puddlé de 330 m de hauteur située à Paris, à l’extrémité nord-ouest du parc du Champ-de-Mars en bordure de la Seine dans le 7e arrondissement.",
                    "Construite en deux ans par Gustave Eiffel et ses collaborateurs pour l'Exposition universelle de Paris de 1889, célébrant le centenaire de la Révolution française, elle est devenue le symbole emblématique de la capitale française et de la France entière.",
                    "D’une hauteur de 312 mètres à l’origine, la tour Eiffel est restée le monument le plus élevé du monde pendant quarante ans. Elle accueille chaque année plus de six millions de visiteurs du monde entier."
                ],
                "image": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/85/Tour_Eiffel_Wikimedia_Commons_%28cropped%29.jpg/500px-Tour_Eiffel_Wikimedia_Commons_%28cropped%29.jpg",
                "url": "https://fr.wikipedia.org/wiki/Tour_Eiffel",
                "category": "monuments",
                "difficulty": "facile",
                "lang_count": 130,
                "pageviews_90d": 75000
            }

        # Cache in DB for future offline use
        cache_article(
            title=article_data["title"],
            url=article_data.get("url", ""),
            image=article_data.get("image", ""),
            paragraphs=article_data["paragraphs"],
            category=category or article_data.get("category", "")
        )

        session = GameSession(
            session_id=session_id,
            seed=seed,
            title=article_data["title"],
            url=article_data.get("url", f"https://fr.wikipedia.org/wiki/{article_data['title']}"),
            image=article_data.get("image", ""),
            paragraphs=article_data["paragraphs"],
            mode=mode,
            category=category or article_data.get("category", "general"),
            difficulty=article_data.get("difficulty", difficulty),
            lang_count=article_data.get("lang_count", 0),
            pageviews_90d=article_data.get("pageviews_90d", int(article_data.get("pageviews_60d", 0) * 1.5))
        )

        self._purge_old_sessions()
        self.sessions[session_id] = session
        return session

    def _purge_old_sessions(self, max_age: float = 3 * 3600, max_sessions: int = 500):
        """Évite que la mémoire (Render free = 512 Mo) grossisse indéfiniment."""
        now = time.time()
        stale = [sid for sid, s in self.sessions.items() if now - s.created_at > max_age]
        for sid in stale:
            self.sessions.pop(sid, None)
        if len(self.sessions) > max_sessions:
            oldest = sorted(self.sessions.items(), key=lambda kv: kv[1].created_at)
            for sid, _ in oldest[: len(self.sessions) - max_sessions]:
                self.sessions.pop(sid, None)

    def get_session(self, session_id: str) -> Optional[GameSession]:
        session = self.sessions.get(session_id)
        if session:
            return session
        # Also check player sessions in active multiplayer rooms
        try:
            from app.room import room_manager
            for room in room_manager.rooms.values():
                for player in room.players.values():
                    if player.session and player.session.session_id == session_id:
                        return player.session
        except Exception:
            pass
        return None
