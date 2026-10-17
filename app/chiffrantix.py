import json
import os
import random
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

import regex as re

from app.cemantix import calculate_cemantix_proximity
from app.nlp import (
    calculate_proximity,
    check_match,
    clean_guess,
    is_valid_french_word,
    normalize_text,
)
from app.synonyms_dict import EXPANDED_STOPWORDS
from app.tokenizer import TOKEN_PATTERN

CHIFFRANTIX_DATA_PATH = os.path.join(
    os.path.dirname(__file__), "data", "chiffrantix_questions.json"
)
CHIFFRANTIX_DIFFICULTIES = {"toutes", "facile", "moyen", "difficile"}
CHIFFRANTIX_CATEGORIES = {
    "toutes",
    "histoire",
    "geographie",
    "sciences",
    "arts_culture",
    "sport",
    "nature",
    "monuments",
    "societe",
    "tech_jeux",
    "astronomie",
}
CHIFFRANTIX_MAX_PLAYERS = 8

# Stopwords that are not required to trigger the win condition when all key words are found
QUESTION_MINOR_WORDS = {
    "le", "la", "les", "un", "une", "des", "du", "de", "d", "l", "a", "au",
    "aux", "en", "et", "ou", "par", "pour", "sur", "dans", "avec", "sans",
    "sous", "vers", "chez", "entre", "contre", "ce", "cet", "cette", "ces",
    "mon", "ton", "son", "ma", "ta", "sa", "mes", "tes", "ses", "notre",
    "votre", "leur", "nos", "vos", "leurs", "je", "tu", "il", "elle", "on",
    "nous", "vous", "ils", "elles", "me", "te", "se", "y", "ne", "n", "pas",
    "plus", "moins", "tres", "tout", "tous", "toute", "toutes", "meme",
    "autre", "autres", "quel", "quelle", "quels", "quelles", "lequel",
    "laquelle", "lesquels", "lesquelles", "duquel", "desquels", "desquelles",
    "auquel", "auxquels", "auxquelles", "qui", "que", "qu", "quoi", "dont",
    "ou", "comment", "pourquoi", "quand", "combien", "est", "sont", "etait",
    "etaient", "fut", "furent", "ete", "etre", "a", "ont", "avait", "avaient",
    "eu", "avoir", "fait", "faire", "il", "elle", "t", "c", "s", "j", "m",
}


def load_chiffrantix_questions(path: str = CHIFFRANTIX_DATA_PATH) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and "questions" in data:
        return data["questions"]
    if isinstance(data, list):
        return data
    return []


def tokenize_question(question_text: str) -> Tuple[List[Dict[str, Any]], List[int], List[int], int]:
    tokens: List[Dict[str, Any]] = []
    raw_chunks = TOKEN_PATTERN.findall(question_text)
    current_id = 0

    for chunk in raw_chunks:
        if not chunk:
            continue
        if chunk.isspace():
            token_type = "space"
            is_word = False
        elif any(c.isalnum() for c in chunk):
            token_type = "word"
            is_word = True
        else:
            token_type = "punct"
            is_word = False

        norm = normalize_text(chunk) if is_word else ""
        tokens.append(
            {
                "id": current_id,
                "text": chunk,
                "type": token_type,
                "is_word": is_word,
                "length": len(chunk) if is_word else 0,
                "revealed": not is_word,
                "normalized": norm,
            }
        )
        current_id += 1

    word_ids = [t["id"] for t in tokens if t["is_word"]]
    significant_ids = [
        t["id"]
        for t in tokens
        if t["is_word"] and t["normalized"] not in QUESTION_MINOR_WORDS and len(t["normalized"]) > 1
    ]
    if not significant_ids:
        significant_ids = word_ids

    return tokens, word_ids, significant_ids, len(word_ids)


class ChiffrantixBoard:
    """Tracks the Pédantix-style masked question board for a single player."""

    def __init__(self, question_item: Dict[str, Any]):
        self.question_item = question_item
        self.question_text: str = question_item["question"]
        (
            self.tokens,
            self.word_ids,
            self.significant_ids,
            self.total_words,
        ) = tokenize_question(self.question_text)
        self.tokens_by_id: Dict[int, Dict[str, Any]] = {t["id"]: t for t in self.tokens}

        self.attempts: int = 0
        self.guesses_history: List[Dict[str, Any]] = []
        self.guessed_words: Set[str] = set()
        self.revealed_word_ids: Set[int] = set()
        self.token_heat: Dict[int, float] = {}
        self.token_close_words: Dict[int, Dict[str, Any]] = {}

        self.word_to_token_ids: Dict[str, List[int]] = {}
        self.context_words: Set[str] = set()
        for t in self.tokens:
            if t["is_word"]:
                norm = t["normalized"]
                if norm:
                    self.word_to_token_ids.setdefault(norm, []).append(t["id"])
                    self.context_words.add(norm)
                cleaned = clean_guess(t["text"]).lower()
                if cleaned:
                    self.context_words.add(cleaned)

        self.unrevealed_unique_words: Set[str] = set(self.word_to_token_ids.keys())
        self.solved: bool = False
        self.solved_at: Optional[float] = None

    @property
    def revealed_count(self) -> int:
        return len(self.revealed_word_ids)

    @property
    def progress_pct(self) -> int:
        if self.total_words <= 0:
            return 100
        return round(100 * len(self.revealed_word_ids) / self.total_words)

    def submit_guess(self, raw_word: str, now: Optional[float] = None) -> Dict[str, Any]:
        if self.solved:
            raise ValueError("Vous avez déjà trouvé la question !")

        clean_word = clean_guess(raw_word)
        if not clean_word:
            raise ValueError("Veuillez saisir un mot.")
        if " " in clean_word:
            raise ValueError("Saisissez un seul mot à la fois.")

        if not is_valid_french_word(clean_word, self.context_words):
            raise ValueError(
                f"Le mot « {clean_word} » n'est pas reconnu dans le dictionnaire français."
            )

        norm_guess = normalize_text(clean_word)
        if norm_guess in self.guessed_words:
            raise ValueError(f"Vous avez déjà proposé le mot « {clean_word} ».")

        all_matched_ids: List[int] = []
        newly_revealed: Dict[str, str] = {}
        matched_norms: List[str] = []

        for target_norm, tids in self.word_to_token_ids.items():
            if check_match(clean_word, target_norm):
                matched_norms.append(target_norm)
                all_matched_ids.extend(tids)
                for tid in tids:
                    tok = self.tokens_by_id[tid]
                    if not tok["revealed"]:
                        tok["revealed"] = True
                        self.revealed_word_ids.add(tid)
                        self.token_heat.pop(tid, None)
                        self.token_close_words.pop(tid, None)
                        newly_revealed[str(tid)] = tok["text"]

        for mn in matched_norms:
            self.unrevealed_unique_words.discard(mn)

        self.attempts += 1
        self.guessed_words.add(norm_guess)

        close_tokens: List[Dict[str, Any]] = []
        max_score: float = 0.0
        is_guess_digit = clean_word.isdigit()

        # Calculate proximity against all unrevealed significant words in the question
        for target_norm in self.unrevealed_unique_words:
            if is_guess_digit != target_norm.isdigit():
                continue
            if not is_guess_digit and (
                target_norm in EXPANDED_STOPWORDS
                or target_norm in QUESTION_MINOR_WORDS
                or len(target_norm) <= 1
            ):
                continue

            prox = calculate_proximity(clean_word, target_norm)
            if prox > max_score:
                max_score = round(prox, 1)

            if prox >= 48.0:
                score_val = round(prox, 1)
                for tid in self.word_to_token_ids.get(target_norm, []):
                    tok = self.tokens_by_id[tid]
                    if not tok["revealed"]:
                        current_heat = self.token_heat.get(tid, 0.0)
                        if score_val > current_heat:
                            self.token_heat[tid] = score_val
                            self.token_close_words[tid] = {
                                "score": score_val,
                                "word": clean_word,
                            }
                            close_tokens.append(
                                {
                                    "id": tid,
                                    "score": score_val,
                                    "word": clean_word,
                                }
                            )

        if all_matched_ids:
            status = "match"
            display_score = 100.0
        elif max_score >= 48.0:
            status = "close"
            display_score = max_score
        else:
            status = "miss"
            fallback_max = max_score
            if fallback_max <= 0.0 and not is_guess_digit:
                for target_norm in self.unrevealed_unique_words:
                    if (
                        target_norm.isdigit()
                        or target_norm in EXPANDED_STOPWORDS
                        or target_norm in QUESTION_MINOR_WORDS
                        or len(target_norm) <= 1
                    ):
                        continue
                    c_prox = calculate_cemantix_proximity(clean_word, target_norm)
                    if c_prox > fallback_max:
                        fallback_max = round(min(47.8, c_prox), 1)
            display_score = fallback_max

        # Check win condition: all significant words revealed
        sig_unrevealed = [
            tid for tid in self.significant_ids if tid not in self.revealed_word_ids
        ]
        if len(sig_unrevealed) == 0:
            self.solved = True
            self.solved_at = now if now is not None else time.time()
            for tid in self.word_ids:
                tok = self.tokens_by_id[tid]
                self.token_heat.pop(tid, None)
                self.token_close_words.pop(tid, None)
                if not tok["revealed"]:
                    tok["revealed"] = True
                    self.revealed_word_ids.add(tid)
                    newly_revealed[str(tid)] = tok["text"]
            self.unrevealed_unique_words.clear()

        record = {
            "attempt": self.attempts,
            "word": clean_word,
            "status": status,
            "count": len(all_matched_ids),
            "score": display_score,
            "solved": self.solved,
        }
        self.guesses_history.append(record)

        return {
            "attempt": self.attempts,
            "word": clean_word,
            "status": status,
            "matches_count": len(all_matched_ids),
            "score": display_score,
            "newly_revealed": newly_revealed,
            "close_tokens": close_tokens,
            "solved": self.solved,
            "revealed_words_count": self.revealed_count,
            "total_words": self.total_words,
            "progress_pct": self.progress_pct,
        }

    def reveal_hint_word(self) -> Optional[Dict[str, Any]]:
        """Reveals one unrevealed word (preferring minor/context words before key nouns)."""
        if self.solved:
            return None
        unrevealed_minor = [
            tid
            for tid in self.word_ids
            if tid not in self.revealed_word_ids and tid not in self.significant_ids
        ]
        unrevealed_sig = [
            tid for tid in self.significant_ids if tid not in self.revealed_word_ids
        ]
        # Only allow revealing a significant word if at least 2 significant words remain
        candidates = unrevealed_minor if unrevealed_minor else (
            unrevealed_sig if len(unrevealed_sig) > 1 else []
        )
        if not candidates:
            return None

        chosen_tid = candidates[0]
        tok = self.tokens_by_id[chosen_tid]
        norm = tok["normalized"]
        revealed_ids = self.word_to_token_ids.get(norm, [chosen_tid])
        for tid in revealed_ids:
            t = self.tokens_by_id[tid]
            t["revealed"] = True
            self.revealed_word_ids.add(tid)
            self.token_heat.pop(tid, None)
            self.token_close_words.pop(tid, None)
        if norm:
            self.unrevealed_unique_words.discard(norm)
        return {"word": tok["text"], "ids": revealed_ids}

    def get_public_tokens(self, reveal_all: bool = False) -> List[Dict[str, Any]]:
        client_tokens: List[Dict[str, Any]] = []
        for t in self.tokens:
            if t["type"] in ("space", "punct") or t["revealed"] or reveal_all:
                client_tokens.append(
                    {
                        "id": t["id"],
                        "type": t["type"],
                        "text": t["text"],
                        "revealed": True,
                        "is_word": t["is_word"],
                    }
                )
            else:
                tok_dict: Dict[str, Any] = {
                    "id": t["id"],
                    "type": "word",
                    "length": t["length"],
                    "revealed": False,
                    "is_word": True,
                }
                if t["id"] in self.token_close_words:
                    tok_dict["heat"] = self.token_close_words[t["id"]]["score"]
                    tok_dict["close_word"] = self.token_close_words[t["id"]]["word"]
                elif t["id"] in self.token_heat:
                    tok_dict["heat"] = self.token_heat[t["id"]]
                client_tokens.append(tok_dict)
        return client_tokens


@dataclass
class ChiffrantixSoloGame:
    game_id: str
    player_id: str
    player_name: str
    question_item: Dict[str, Any]
    board: ChiffrantixBoard
    difficulty: str = "moyen"
    category: str = "toutes"
    status: str = "playing"
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        is_finished = self.status == "finished" or self.board.solved
        return {
            "game_id": self.game_id,
            "status": "finished" if is_finished else "playing",
            "difficulty": self.difficulty,
            "category": self.question_item.get("category", self.category),
            "question_difficulty": self.question_item.get("difficulty", "moyen"),
            "answer": self.question_item["answer"],
            "tokens": self.board.get_public_tokens(reveal_all=is_finished),
            "player": {
                "player_id": self.player_id,
                "name": self.player_name,
                "attempts": self.board.attempts,
                "revealed_words_count": self.board.revealed_count,
                "total_words": self.board.total_words,
                "progress_pct": 100 if is_finished else self.board.progress_pct,
                "solved": self.board.solved,
                "guesses": list(reversed(self.board.guesses_history)),
            },
            "solution": {
                "question": self.question_item["question"],
                "answer": self.question_item["answer"],
                "explanation": self.question_item.get("explanation", ""),
                "source_title": self.question_item.get("source_title", "Wikipédia"),
                "source_url": self.question_item.get("source_url", ""),
                "category": self.question_item.get("category", ""),
            }
            if is_finished
            else None,
        }


@dataclass
class ChiffrantixRoomPlayer:
    player_id: str
    name: str
    board: ChiffrantixBoard
    is_spectator: bool = False
    connected: bool = True

    def to_public_summary(self) -> Dict[str, Any]:
        last_guess = self.board.guesses_history[-1] if self.board.guesses_history else None
        return {
            "player_id": self.player_id,
            "name": self.name,
            "is_spectator": self.is_spectator,
            "attempts": self.board.attempts,
            "revealed_words_count": self.board.revealed_count,
            "total_words": self.board.total_words,
            "progress_pct": self.board.progress_pct,
            "solved": self.board.solved,
            "solved_at": self.board.solved_at,
            "last_status": last_guess["status"] if last_guess else None,
            "last_score": last_guess["score"] if last_guess else 0,
        }


@dataclass
class ChiffrantixRoom:
    room_id: str
    host_player_id: str
    question_item: Dict[str, Any]
    difficulty: str = "moyen"
    category: str = "toutes"
    players: Dict[str, ChiffrantixRoomPlayer] = field(default_factory=dict)
    status: str = "lobby"
    winner_player_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    match_number: int = 1
    stats_recorded: bool = False

    def to_dict(self, player_id: str) -> Dict[str, Any]:
        player = self.players[player_id]
        is_finished = self.status == "finished" or player.board.solved
        active_players = [p for p in self.players.values() if not p.is_spectator]
        spectators = [p for p in self.players.values() if p.is_spectator]

        sorted_players = sorted(
            self.players.values(),
            key=lambda p: (
                p.is_spectator,
                not p.board.solved,
                p.board.solved_at or float("inf"),
                -p.board.progress_pct,
                p.board.attempts,
            ),
        )

        return {
            "room_id": self.room_id,
            "status": self.status,
            "match_number": self.match_number,
            "host_player_id": self.host_player_id,
            "difficulty": self.difficulty,
            "category": self.question_item.get("category", self.category),
            "question_difficulty": self.question_item.get("difficulty", "moyen"),
            "answer": self.question_item["answer"],
            "tokens": player.board.get_public_tokens(reveal_all=is_finished),
            "player_id": player_id,
            "player": {
                **player.to_public_summary(),
                "guesses": list(reversed(player.board.guesses_history)),
            },
            "players": [p.to_public_summary() for p in sorted_players],
            "player_count": len(active_players),
            "spectator_count": len(spectators),
            "can_start": self.status == "lobby" and len(active_players) >= 2,
            "can_restart": self.status == "finished" and player_id == self.host_player_id,
            "restart_available": self.status == "finished",
            "winner_player_id": self.winner_player_id,
            "winner_name": (
                self.players[self.winner_player_id].name
                if self.winner_player_id and self.winner_player_id in self.players
                else None
            ),
            "solution": {
                "question": self.question_item["question"],
                "answer": self.question_item["answer"],
                "explanation": self.question_item.get("explanation", ""),
                "source_title": self.question_item.get("source_title", "Wikipédia"),
                "source_url": self.question_item.get("source_url", ""),
                "category": self.question_item.get("category", ""),
            }
            if is_finished
            else None,
        }


class ChiffrantixManager:
    def __init__(
        self,
        questions: Optional[Iterable[Dict[str, Any]]] = None,
        clock: Callable[[], float] = time.time,
    ):
        raw_questions = (
            list(questions) if questions is not None else load_chiffrantix_questions()
        )
        self.questions: List[Dict[str, Any]] = [
            q
            for q in raw_questions
            if isinstance(q, dict)
            and q.get("question")
            and q.get("answer")
            and q.get("source_url")
        ]
        self._clock = clock
        self.solo_games: Dict[str, ChiffrantixSoloGame] = {}
        self.rooms: Dict[str, ChiffrantixRoom] = {}
        self._recent_by_player: Dict[str, List[int]] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _validate_difficulty(difficulty: str) -> str:
        diff = (difficulty or "moyen").strip().lower()
        if diff not in CHIFFRANTIX_DIFFICULTIES:
            raise ValueError(
                "Difficulté invalide. Choisissez facile, moyen, difficile ou toutes."
            )
        return diff

    @staticmethod
    def _validate_category(category: str) -> str:
        cat = (category or "toutes").strip().lower()
        if cat not in CHIFFRANTIX_CATEGORIES:
            raise ValueError("Catégorie invalide.")
        return cat

    def _pick_question(
        self,
        difficulty: str = "moyen",
        category: str = "toutes",
        player_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self.questions:
            raise ValueError("Aucune question Chiffrantix n'est chargée.")

        candidates = list(enumerate(self.questions))
        if category and category != "toutes":
            cat_filtered = [
                (i, q) for i, q in candidates if q.get("category") == category
            ]
            if cat_filtered:
                candidates = cat_filtered

        if difficulty and difficulty != "toutes":
            diff_filtered = [
                (i, q) for i, q in candidates if q.get("difficulty") == difficulty
            ]
            if diff_filtered:
                candidates = diff_filtered

        if player_id:
            recent = set(self._recent_by_player.get(player_id, [])[-200:])
            fresh = [(i, q) for i, q in candidates if i not in recent]
            if fresh:
                candidates = fresh

        chosen_idx, chosen_q = random.choice(candidates)
        if player_id:
            history = self._recent_by_player.setdefault(player_id, [])
            history.append(chosen_idx)
            if len(history) > 500:
                del history[:-300]
        return chosen_q

    def create_solo(
        self,
        player_id: str,
        player_name: str,
        difficulty: str = "moyen",
        category: str = "toutes",
    ) -> ChiffrantixSoloGame:
        with self._lock:
            difficulty = self._validate_difficulty(difficulty)
            category = self._validate_category(category)
            question_item = self._pick_question(
                difficulty=difficulty, category=category, player_id=player_id
            )
            game = ChiffrantixSoloGame(
                game_id=uuid.uuid4().hex,
                player_id=player_id,
                player_name=player_name,
                question_item=question_item,
                board=ChiffrantixBoard(question_item),
                difficulty=difficulty,
                category=category,
                created_at=self._clock(),
            )
            self.solo_games[game.game_id] = game
            return game

    def get_solo(self, game_id: str, player_id: str) -> ChiffrantixSoloGame:
        with self._lock:
            game = self.solo_games.get(game_id)
            if not game or game.player_id != player_id:
                raise KeyError("Cette partie solo est introuvable.")
            return game

    def guess_solo(
        self, game_id: str, player_id: str, raw_guess: str
    ) -> Tuple[ChiffrantixSoloGame, Dict[str, Any]]:
        with self._lock:
            game = self.get_solo(game_id, player_id)
            if game.status == "finished":
                raise ValueError("Cette partie est déjà terminée.")
            result = game.board.submit_guess(raw_guess, now=self._clock())
            if game.board.solved:
                game.status = "finished"
            return game, result

    def hint_solo(self, game_id: str, player_id: str) -> Tuple[ChiffrantixSoloGame, Dict[str, Any]]:
        with self._lock:
            game = self.get_solo(game_id, player_id)
            if game.status == "finished":
                raise ValueError("Cette partie est déjà terminée.")
            hint_info = game.board.reveal_hint_word()
            if not hint_info:
                raise ValueError("Aucun indice supplémentaire n'est disponible pour cette question.")
            return game, hint_info

    def create_room(
        self,
        player_id: str,
        player_name: str,
        difficulty: str = "moyen",
        category: str = "toutes",
    ) -> ChiffrantixRoom:
        with self._lock:
            difficulty = self._validate_difficulty(difficulty)
            category = self._validate_category(category)
            room_id = uuid.uuid4().hex[:6].upper()
            while room_id in self.rooms:
                room_id = uuid.uuid4().hex[:6].upper()
            question_item = self._pick_question(
                difficulty=difficulty, category=category, player_id=player_id
            )
            room = ChiffrantixRoom(
                room_id=room_id,
                host_player_id=player_id,
                question_item=question_item,
                difficulty=difficulty,
                category=category,
                created_at=self._clock(),
            )
            room.players[player_id] = ChiffrantixRoomPlayer(
                player_id=player_id,
                name=player_name,
                board=ChiffrantixBoard(question_item),
            )
            self.rooms[room_id] = room
            return room

    def list_rooms(self, player_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            rooms = []
            for room in self.rooms.values():
                if room.status == "finished":
                    continue
                rooms.append(
                    {
                        "room_id": room.room_id,
                        "status": room.status,
                        "player_count": sum(
                            not p.is_spectator for p in room.players.values()
                        ),
                        "spectator_count": sum(
                            p.is_spectator for p in room.players.values()
                        ),
                        "host_name": room.players[room.host_player_id].name,
                        "difficulty": room.difficulty,
                        "category": room.category,
                        "is_member": player_id in room.players if player_id else False,
                    }
                )
            return rooms

    def join_room(
        self, room_id: str, player_id: str, player_name: str
    ) -> ChiffrantixRoom:
        with self._lock:
            room = self.rooms.get(room_id.upper())
            if not room:
                raise KeyError("Salon introuvable ou expiré.")
            if player_id in room.players:
                room.players[player_id].name = player_name
                room.players[player_id].connected = True
                return room
            if len(room.players) >= CHIFFRANTIX_MAX_PLAYERS:
                raise ValueError(
                    f"Ce salon est complet ({CHIFFRANTIX_MAX_PLAYERS} joueurs maximum)."
                )
            is_spec = room.status == "playing"
            if room.status not in ("lobby", "playing"):
                raise ValueError("Cette partie est terminée.")
            room.players[player_id] = ChiffrantixRoomPlayer(
                player_id=player_id,
                name=player_name,
                board=ChiffrantixBoard(room.question_item),
                is_spectator=is_spec,
            )
            return room

    def get_room(self, room_id: str, player_id: str) -> ChiffrantixRoom:
        with self._lock:
            room = self.rooms.get(room_id.upper())
            if not room or player_id not in room.players:
                raise KeyError("Salon ou joueur introuvable.")
            return room

    def start_room(self, room_id: str, player_id: str) -> ChiffrantixRoom:
        with self._lock:
            room = self.get_room(room_id, player_id)
            if room.host_player_id != player_id:
                raise PermissionError("Seul l'hôte peut démarrer la partie.")
            if room.status != "lobby":
                raise ValueError("Cette partie a déjà démarré.")
            if sum(not p.is_spectator for p in room.players.values()) < 2:
                raise ValueError("Il faut au moins deux joueurs pour démarrer.")
            room.status = "playing"
            room.started_at = self._clock()
            return room

    def restart_room(self, room_id: str, player_id: str) -> ChiffrantixRoom:
        with self._lock:
            room = self.get_room(room_id, player_id)
            if room.host_player_id != player_id:
                raise PermissionError("Seul l'hôte peut relancer une manche.")
            if room.status != "finished":
                raise ValueError("La manche doit être terminée pour être relancée.")
            question_item = self._pick_question(
                difficulty=room.difficulty,
                category=room.category,
                player_id=player_id,
            )
            room.question_item = question_item
            room.match_number += 1
            room.winner_player_id = None
            room.started_at = self._clock()
            room.status = "playing"
            room.stats_recorded = False
            for player in room.players.values():
                player.board = ChiffrantixBoard(question_item)
                player.is_spectator = False
            return room

    def guess_room(
        self, room_id: str, player_id: str, raw_guess: str
    ) -> Tuple[ChiffrantixRoom, Dict[str, Any]]:
        with self._lock:
            room = self.get_room(room_id, player_id)
            if room.status != "playing":
                raise ValueError("La partie n'est pas en cours.")
            player = room.players[player_id]
            if player.is_spectator:
                raise ValueError("Les spectateurs ne peuvent pas proposer de mot.")
            result = player.board.submit_guess(raw_guess, now=self._clock())
            if player.board.solved and room.winner_player_id is None:
                room.winner_player_id = player_id
                room.status = "finished"
            return room, result
