import random
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional

from app.nlp import (
    CONCEPT_LOOKUP,
    FRENCH_DICTIONARY,
    HARDCODED_SYNONYMS,
    PROPER_NOUNS,
    STOPWORDS_EXACT,
    THEMATIC_CLUSTERS,
    WORD_ASSOCIATIONS,
    calculate_proximity,
    clean_guess,
    normalize_text,
)

CEMANTIX_ROUND_SECONDS = 60
CEMANTIX_MAX_PLAYERS = 8


def _default_answers() -> List[str]:
    semantic_words = (
        set(HARDCODED_SYNONYMS)
        | set(WORD_ASSOCIATIONS)
        | set(CONCEPT_LOOKUP)
        | set().union(*THEMATIC_CLUSTERS.values())
    )
    return sorted(
        word
        for word in semantic_words
        if word in FRENCH_DICTIONARY
        and word not in STOPWORDS_EXACT
        and word not in PROPER_NOUNS
        and 3 <= len(word) <= 14
        and re.fullmatch(r"[a-z]+", word)
    )


@dataclass
class CemantixGame:
    game_id: str
    target: str
    player_id: str
    player_name: str
    guesses: List[Dict[str, Any]] = field(default_factory=list)
    guessed_words: set[str] = field(default_factory=set)
    status: str = "playing"
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "game_id": self.game_id,
            "status": self.status,
            "player": {
                "player_id": self.player_id,
                "name": self.player_name,
                "guesses": self.guesses,
                "attempts": len(self.guesses),
                "solved": self.status == "finished",
            },
            "target": self.target if self.status == "finished" else None,
        }


@dataclass
class CemantixPlayer:
    player_id: str
    name: str
    guesses: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class CemantixSubmission:
    word: str
    score: float
    solved: bool
    submitted_at: float


@dataclass
class CemantixRoom:
    room_id: str
    target: str
    host_player_id: str
    players: Dict[str, CemantixPlayer] = field(default_factory=dict)
    status: str = "lobby"
    round_number: int = 0
    deadline_at: Optional[float] = None
    pending: Dict[str, CemantixSubmission] = field(default_factory=dict)
    winner_player_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)

    def to_dict(self, player_id: str, now: float) -> Dict[str, Any]:
        player = self.players[player_id]
        return {
            "room_id": self.room_id,
            "status": self.status,
            "host_player_id": self.host_player_id,
            "round_number": self.round_number,
            "round_seconds": CEMANTIX_ROUND_SECONDS,
            "deadline_at": self.deadline_at,
            "time_left": max(0, int(self.deadline_at - now)) if self.deadline_at else 0,
            "player_id": player_id,
            "player": {
                "player_id": player.player_id,
                "name": player.name,
                "guesses": player.guesses,
                "has_submitted": player_id in self.pending,
            },
            "players": [
                {
                    "player_id": item.player_id,
                    "name": item.name,
                    "guesses": item.guesses,
                    "has_submitted": item.player_id in self.pending,
                }
                for item in self.players.values()
            ],
            "submitted_count": len(self.pending),
            "player_count": len(self.players),
            "can_start": self.status == "lobby" and len(self.players) >= 2,
            "winner_player_id": self.winner_player_id,
            "target": self.target if self.status == "finished" else None,
        }


class CemantixManager:
    def __init__(
        self,
        words: Optional[Iterable[str]] = None,
        answers: Optional[Iterable[str]] = None,
        clock: Callable[[], float] = time.time,
    ):
        self.dictionary = {
            normalize_text(word)
            for word in (words if words is not None else FRENCH_DICTIONARY)
            if re.fullmatch(r"[a-z]+", normalize_text(word))
        }
        candidates = answers if answers is not None else _default_answers()
        self.answers = sorted(
            {
                normalize_text(word)
                for word in candidates
                if normalize_text(word) in self.dictionary
                and normalize_text(word) not in STOPWORDS_EXACT
                and re.fullmatch(r"[a-z]+", normalize_text(word))
            }
        )
        if not self.answers:
            raise ValueError("La liste de mots Cémantix ne contient aucun mot reconnu.")
        self._clock = clock
        self.solo_games: Dict[str, CemantixGame] = {}
        self.rooms: Dict[str, CemantixRoom] = {}
        self._lock = threading.RLock()

    def _pick_target(self) -> str:
        return random.choice(self.answers)

    def _normalize_valid_guess(self, raw_guess: str) -> str:
        word = normalize_text(clean_guess(raw_guess))
        if not word or not re.fullmatch(r"[a-z]+", word):
            raise ValueError("Saisissez un seul mot composé de lettres.")
        if word not in self.dictionary:
            raise ValueError("Ce mot n'est pas reconnu dans le dictionnaire français.")
        if word in STOPWORDS_EXACT:
            raise ValueError("Les mots outils ne peuvent pas être proposés.")
        return word

    def _score(self, word: str, target: str) -> tuple[float, bool]:
        solved = word == target
        score = calculate_proximity(word, target)
        if not solved:
            score = min(score, 99.9)
        return round(score, 1), solved

    def create_solo(self, player_id: str, player_name: str) -> CemantixGame:
        with self._lock:
            game = CemantixGame(
                game_id=uuid.uuid4().hex,
                target=self._pick_target(),
                player_id=player_id,
                player_name=player_name,
            )
            self.solo_games[game.game_id] = game
            return game

    def get_solo(self, game_id: str, player_id: str) -> CemantixGame:
        with self._lock:
            game = self.solo_games.get(game_id)
            if not game or game.player_id != player_id:
                raise KeyError("Cette partie solo est introuvable.")
            return game

    def guess_solo(
        self, game_id: str, player_id: str, raw_guess: str
    ) -> tuple[CemantixGame, Dict[str, Any]]:
        with self._lock:
            game = self.get_solo(game_id, player_id)
            if game.status == "finished":
                raise ValueError("Cette partie est déjà terminée.")
            word = self._normalize_valid_guess(raw_guess)
            if word in game.guessed_words:
                raise ValueError("Vous avez déjà proposé ce mot.")

            score, solved = self._score(word, game.target)
            game.guessed_words.add(word)
            result = {
                "word": word,
                "score": score,
                "solved": solved,
                "attempt": len(game.guesses) + 1,
            }
            game.guesses.append(result)
            if solved:
                game.status = "finished"
            return game, result

    def create_room(self, player_id: str, player_name: str) -> CemantixRoom:
        with self._lock:
            room_id = uuid.uuid4().hex[:6].upper()
            while room_id in self.rooms:
                room_id = uuid.uuid4().hex[:6].upper()
            room = CemantixRoom(
                room_id=room_id,
                target=self._pick_target(),
                host_player_id=player_id,
            )
            room.players[player_id] = CemantixPlayer(player_id, player_name)
            self.rooms[room_id] = room
            return room

    def _advance_room(self, room: CemantixRoom, now: float) -> None:
        if room.status != "playing" or room.deadline_at is None:
            return
        if len(room.pending) < len(room.players) and now < room.deadline_at:
            return

        for player_id, player in room.players.items():
            submission = room.pending.get(player_id)
            if submission:
                player.guesses.append(
                    {
                        "round": room.round_number,
                        "word": submission.word,
                        "score": submission.score,
                        "solved": submission.solved,
                        "passed": False,
                    }
                )
            else:
                player.guesses.append(
                    {
                        "round": room.round_number,
                        "word": None,
                        "score": None,
                        "solved": False,
                        "passed": True,
                    }
                )

        winners = [
            (submission.submitted_at, player_id)
            for player_id, submission in room.pending.items()
            if submission.solved
        ]
        if winners:
            _, room.winner_player_id = min(winners)
            room.status = "finished"
            room.deadline_at = None
            room.pending.clear()
            return

        room.round_number += 1
        room.deadline_at = now + CEMANTIX_ROUND_SECONDS
        room.pending.clear()

    def join_room(
        self, room_id: str, player_id: str, player_name: str
    ) -> CemantixRoom:
        with self._lock:
            room = self.rooms.get(room_id.upper())
            if not room:
                raise KeyError("Salon introuvable ou expiré.")
            self._advance_room(room, self._clock())
            if player_id in room.players:
                room.players[player_id].name = player_name
                return room
            if room.status != "lobby":
                raise ValueError("La partie a commencé. Seuls les joueurs déjà inscrits peuvent revenir.")
            if len(room.players) >= CEMANTIX_MAX_PLAYERS:
                raise ValueError(f"Ce salon est complet ({CEMANTIX_MAX_PLAYERS} joueurs maximum).")
            room.players[player_id] = CemantixPlayer(player_id, player_name)
            return room

    def get_room(self, room_id: str, player_id: str) -> CemantixRoom:
        with self._lock:
            room = self.rooms.get(room_id.upper())
            if not room or player_id not in room.players:
                raise KeyError("Salon ou joueur introuvable.")
            self._advance_room(room, self._clock())
            return room

    def start_room(self, room_id: str, player_id: str) -> CemantixRoom:
        with self._lock:
            room = self.get_room(room_id, player_id)
            if room.host_player_id != player_id:
                raise PermissionError("Seul l'hôte peut démarrer la partie.")
            if room.status != "lobby":
                raise ValueError("Cette partie a déjà démarré.")
            if len(room.players) < 2:
                raise ValueError("Il faut au moins deux joueurs pour démarrer.")
            now = self._clock()
            room.status = "playing"
            room.round_number = 1
            room.deadline_at = now + CEMANTIX_ROUND_SECONDS
            return room

    def submit_room_guess(
        self, room_id: str, player_id: str, raw_guess: str
    ) -> tuple[CemantixRoom, Dict[str, Any]]:
        with self._lock:
            room = self.get_room(room_id, player_id)
            if room.status != "playing":
                raise ValueError("La partie n'est pas en cours.")
            if player_id in room.pending:
                raise ValueError("Votre proposition pour cette manche a déjà été envoyée.")

            word = self._normalize_valid_guess(raw_guess)
            if word in {
                guess["word"]
                for guess in room.players[player_id].guesses
                if guess["word"] is not None
            }:
                raise ValueError("Vous avez déjà proposé ce mot.")

            score, solved = self._score(word, room.target)
            submission = CemantixSubmission(
                word=word,
                score=score,
                solved=solved,
                submitted_at=self._clock(),
            )
            submitted_round = room.round_number
            room.pending[player_id] = submission
            self._advance_room(room, self._clock())
            return room, {
                "submitted": True,
                "round_number": submitted_round,
            }


cemantix_manager = CemantixManager()
