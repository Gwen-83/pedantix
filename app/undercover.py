import json
import random
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.nlp import normalize_text


MIN_PLAYERS = 3
MAX_PLAYERS = 20
WORD_PAIRS_PATH = Path(__file__).resolve().parent / "data" / "undercover_word_pairs.json"


def _load_word_pairs() -> tuple[tuple[str, str], ...]:
    with WORD_PAIRS_PATH.open(encoding="utf-8") as pairs_file:
        data = json.load(pairs_file)
    if not isinstance(data, list):
        raise ValueError(f"Invalid Undercover word-pair data in {WORD_PAIRS_PATH}")

    pairs = []
    seen = set()
    for pair in data:
        if (
            not isinstance(pair, list)
            or len(pair) != 2
            or not all(
                isinstance(word, str)
                and re.fullmatch(r"[a-z]{3,18}", normalize_text(word))
                for word in pair
            )
        ):
            raise ValueError(f"Invalid Undercover word pair: {pair!r}")
        normalized = tuple(normalize_text(word) for word in pair)
        key = tuple(sorted(normalized))
        if normalized[0] == normalized[1] or key in seen:
            raise ValueError(f"Duplicate Undercover word pair: {pair!r}")
        seen.add(key)
        pairs.append(normalized)

    if len(pairs) <= 10_000:
        raise ValueError(
            f"Undercover requires more than 10,000 distinct word pairs; found {len(pairs)}."
        )
    return tuple(pairs)


WORD_PAIRS = _load_word_pairs()


def role_counts(player_count: int) -> dict[str, int]:
    if player_count < MIN_PLAYERS:
        return {"civilian": 0, "undercover": 0, "mr_white": 0}
    undercovers = max(1, (player_count - 3) // 4 + 1)
    mr_whites = int(player_count >= 6) + int(player_count >= 13)
    while undercovers + mr_whites >= player_count:
        mr_whites -= 1
    return {
        "civilian": player_count - undercovers - mr_whites,
        "undercover": undercovers,
        "mr_white": mr_whites,
    }


@dataclass
class UndercoverPlayer:
    player_id: str
    name: str
    is_spectator: bool = False
    role: str | None = None
    word: str | None = None
    alive: bool = True
    spoken: bool = False
    vote: str | None = None


@dataclass
class UndercoverRoom:
    room_id: str
    host_player_id: str
    players: dict[str, UndercoverPlayer] = field(default_factory=dict)
    status: str = "lobby"
    phase: str = "lobby"
    match_number: int = 1
    round_number: int = 0
    winner: str | None = None
    civilian_word: str | None = None
    undercover_word: str | None = None
    last_result: dict[str, Any] | None = None
    started_at: float | None = None
    stats_recorded: bool = False

    def to_dict(self, player_id: str) -> dict[str, Any]:
        player = self.players[player_id]
        reveal_all = self.status == "finished"
        public_players = []
        for item in self.players.values():
            public_players.append(
                {
                    "player_id": item.player_id,
                    "name": item.name,
                    "is_spectator": item.is_spectator,
                    "alive": item.alive,
                    "spoken": item.spoken,
                    "has_voted": item.vote is not None,
                    "role": item.role if reveal_all or not item.alive else None,
                }
            )

        active_players = [
            item for item in self.players.values() if not item.is_spectator
        ]
        return {
            "room_id": self.room_id,
            "status": self.status,
            "phase": self.phase,
            "match_number": self.match_number,
            "round_number": self.round_number,
            "host_player_id": self.host_player_id,
            "players": public_players,
            "player": {
                "player_id": player.player_id,
                "role": player.role,
                "word": player.word,
                "is_spectator": player.is_spectator,
                "alive": player.alive,
                "spoken": player.spoken,
                "has_voted": player.vote is not None,
            },
            "role_counts": role_counts(len(active_players)),
            "player_count": len(active_players),
            "spectator_count": len(self.players) - len(active_players),
            "can_start": self.status == "lobby"
            and len(active_players) >= MIN_PLAYERS,
            "can_restart": self.status == "finished"
            and player_id == self.host_player_id,
            "votes": (
                self._vote_summary()
                if self.phase != "voting" and self.last_result
                else None
            ),
            "last_result": self.last_result,
            "winner": self.winner,
            "words": (
                {"civilian": self.civilian_word, "undercover": self.undercover_word}
                if reveal_all
                else None
            ),
        }

    def _vote_summary(self) -> list[dict[str, Any]] | None:
        if not self.last_result or "vote_counts" not in self.last_result:
            return None
        return list(self.last_result["vote_counts"])


class UndercoverManager:
    def __init__(self) -> None:
        self.rooms: dict[str, UndercoverRoom] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _clean_name(name: str) -> str:
        return re.sub(r"[\x00-\x1f\x7f<>]", "", name).strip()[:24] or "Joueur"

    def create_room(self, player_id: str, player_name: str) -> UndercoverRoom:
        with self._lock:
            room_id = uuid.uuid4().hex[:6].upper()
            while room_id in self.rooms:
                room_id = uuid.uuid4().hex[:6].upper()
            room = UndercoverRoom(room_id=room_id, host_player_id=player_id)
            room.players[player_id] = UndercoverPlayer(
                player_id=player_id, name=self._clean_name(player_name)
            )
            self.rooms[room_id] = room
            return room

    def join_room(
        self, room_id: str, player_id: str, player_name: str
    ) -> UndercoverRoom:
        with self._lock:
            room = self.rooms.get(room_id.upper())
            if room is None:
                raise KeyError("Salon introuvable ou expiré.")
            existing = room.players.get(player_id)
            if existing:
                existing.name = self._clean_name(player_name)
                return room
            if room.status == "finished":
                raise ValueError("Cette partie est terminée.")
            if len(room.players) >= MAX_PLAYERS:
                raise ValueError(f"Ce salon est complet ({MAX_PLAYERS} joueurs maximum).")
            room.players[player_id] = UndercoverPlayer(
                player_id=player_id,
                name=self._clean_name(player_name),
                is_spectator=room.status == "playing",
            )
            return room

    def get_room(self, room_id: str, player_id: str) -> UndercoverRoom:
        with self._lock:
            room = self.rooms.get(room_id.upper())
            if room is None or player_id not in room.players:
                raise KeyError("Salon ou joueur introuvable.")
            return room

    def list_rooms(self, player_id: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {
                    "room_id": room.room_id,
                    "status": room.status,
                    "player_count": sum(
                        not item.is_spectator for item in room.players.values()
                    ),
                    "spectator_count": sum(
                        item.is_spectator for item in room.players.values()
                    ),
                    "host_name": room.players[room.host_player_id].name,
                    "is_member": player_id in room.players if player_id else False,
                }
                for room in self.rooms.values()
                if room.status != "finished"
            ]

    def start_room(self, room_id: str, player_id: str) -> UndercoverRoom:
        with self._lock:
            room = self.get_room(room_id, player_id)
            if room.host_player_id != player_id:
                raise PermissionError("Seul l'hôte peut démarrer la partie.")
            if room.status != "lobby":
                raise ValueError("Cette partie a déjà démarré.")
            active_players = [
                item for item in room.players.values() if not item.is_spectator
            ]
            if len(active_players) < MIN_PLAYERS:
                raise ValueError(f"Il faut au moins {MIN_PLAYERS} joueurs pour démarrer.")
            self._deal_roles(room, active_players)
            room.status = "playing"
            room.phase = "discussion"
            room.round_number = 1
            room.last_result = None
            room.started_at = time.time()
            room.stats_recorded = False
            return room

    def _deal_roles(
        self, room: UndercoverRoom, active_players: list[UndercoverPlayer]
    ) -> None:
        pair = random.choice(WORD_PAIRS)
        civilian_word, undercover_word = pair
        if random.choice((False, True)):
            civilian_word, undercover_word = undercover_word, civilian_word
        counts = role_counts(len(active_players))
        roles = (
            ["civilian"] * counts["civilian"]
            + ["undercover"] * counts["undercover"]
            + ["mr_white"] * counts["mr_white"]
        )
        random.shuffle(roles)
        room.civilian_word = civilian_word
        room.undercover_word = undercover_word
        for player, role in zip(active_players, roles):
            player.role = role
            player.word = (
                civilian_word if role == "civilian"
                else undercover_word if role == "undercover"
                else None
            )
            player.alive = True
            player.spoken = False
            player.vote = None
        for player in room.players.values():
            if player.is_spectator:
                player.role = None
                player.word = None
                player.alive = False
                player.spoken = False
                player.vote = None

    def mark_spoken(self, room_id: str, player_id: str) -> UndercoverRoom:
        with self._lock:
            room = self.get_room(room_id, player_id)
            player = room.players[player_id]
            self._require_active(room, player, "discussion")
            player.spoken = True
            if all(item.spoken for item in self._alive_players(room)):
                self._begin_voting(room)
            return room

    def start_voting(self, room_id: str, player_id: str) -> UndercoverRoom:
        with self._lock:
            room = self.get_room(room_id, player_id)
            if room.host_player_id != player_id:
                raise PermissionError("Seul l'hôte peut lancer le vote.")
            if room.status != "playing" or room.phase != "discussion":
                raise ValueError("Le vote ne peut pas être lancé maintenant.")
            self._begin_voting(room)
            return room

    def vote(
        self, room_id: str, player_id: str, target_player_id: str
    ) -> UndercoverRoom:
        with self._lock:
            room = self.get_room(room_id, player_id)
            player = room.players[player_id]
            self._require_active(room, player, "voting")
            target = room.players.get(target_player_id)
            if target is None or target.is_spectator or not target.alive:
                raise ValueError("Cette cible ne peut pas recevoir de vote.")
            if target_player_id == player_id:
                raise ValueError("Vous ne pouvez pas voter contre vous-même.")
            if player.vote is not None:
                raise ValueError("Vous avez déjà voté.")
            player.vote = target_player_id
            alive = self._alive_players(room)
            if all(item.vote is not None for item in alive):
                self._resolve_vote(room, alive)
            return room

    def guess_word(
        self, room_id: str, player_id: str, guess: str
    ) -> UndercoverRoom:
        with self._lock:
            room = self.get_room(room_id, player_id)
            player = room.players[player_id]
            if (
                room.status != "playing"
                or room.phase != "mr_white_guess"
                or player.role != "mr_white"
                or player.alive
            ):
                raise ValueError("Vous ne pouvez pas proposer de mot maintenant.")
            if normalize_text(guess.strip()) == normalize_text(room.civilian_word or ""):
                room.winner = "mr_white"
                room.status = "finished"
                room.phase = "finished"
                room.last_result = {
                    "type": "mr_white_won",
                    "player_id": player_id,
                    "player_name": player.name,
                }
            else:
                room.last_result = {
                    "type": "mr_white_failed",
                    "player_id": player_id,
                    "player_name": player.name,
                }
                self._finish_or_continue(room)
            return room

    def restart_room(self, room_id: str, player_id: str) -> UndercoverRoom:
        with self._lock:
            room = self.get_room(room_id, player_id)
            if room.host_player_id != player_id:
                raise PermissionError("Seul l'hôte peut relancer la partie.")
            if room.status != "finished":
                raise ValueError("La partie doit être terminée pour être relancée.")
            room.match_number += 1
            room.status = "lobby"
            room.phase = "lobby"
            room.round_number = 0
            room.winner = None
            room.civilian_word = None
            room.undercover_word = None
            room.last_result = None
            room.started_at = None
            room.stats_recorded = False
            for player in room.players.values():
                player.is_spectator = False
                player.role = None
                player.word = None
                player.alive = True
                player.spoken = False
                player.vote = None
            return room

    @staticmethod
    def _require_active(
        room: UndercoverRoom, player: UndercoverPlayer, phase: str
    ) -> None:
        if player.is_spectator:
            raise ValueError("Les spectateurs ne peuvent pas jouer.")
        if not player.alive:
            raise ValueError("Vous avez été éliminé.")
        if room.status != "playing" or room.phase != phase:
            raise ValueError("Cette action n'est pas disponible maintenant.")

    @staticmethod
    def _alive_players(room: UndercoverRoom) -> list[UndercoverPlayer]:
        return [
            player
            for player in room.players.values()
            if not player.is_spectator and player.alive
        ]

    @staticmethod
    def _begin_voting(room: UndercoverRoom) -> None:
        room.phase = "voting"
        for player in room.players.values():
            player.vote = None

    def _resolve_vote(
        self, room: UndercoverRoom, alive_players: list[UndercoverPlayer]
    ) -> None:
        votes: dict[str, int] = {}
        for player in alive_players:
            if player.vote:
                votes[player.vote] = votes.get(player.vote, 0) + 1
        max_votes = max(votes.values(), default=0)
        leaders = [player_id for player_id, count in votes.items() if count == max_votes]
        if len(leaders) != 1:
            room.last_result = {
                "type": "tie",
                "vote_counts": self._format_vote_counts(room, votes),
            }
            self._next_round(room)
            return

        eliminated = room.players[leaders[0]]
        eliminated.alive = False
        room.last_result = {
            "type": "elimination",
            "player_id": eliminated.player_id,
            "player_name": eliminated.name,
            "role": eliminated.role,
            "vote_counts": self._format_vote_counts(room, votes),
        }
        if eliminated.role == "mr_white":
            room.phase = "mr_white_guess"
            return
        self._finish_or_continue(room)

    def _finish_or_continue(self, room: UndercoverRoom) -> None:
        alive = self._alive_players(room)
        undercovers = sum(player.role == "undercover" for player in alive)
        civilians = sum(player.role == "civilian" for player in alive)
        mr_whites = sum(player.role == "mr_white" for player in alive)
        if undercovers == 0 and not any(player.role == "mr_white" for player in alive):
            room.winner = "civilians"
            room.status = "finished"
            room.phase = "finished"
            return
        if undercovers and undercovers >= civilians:
            room.winner = "undercover"
            room.status = "finished"
            room.phase = "finished"
            return
        if civilians == 0 and undercovers == 0 and mr_whites:
            room.winner = "mr_white"
            room.status = "finished"
            room.phase = "finished"
            return
        self._next_round(room)

    @staticmethod
    def _format_vote_counts(
        room: UndercoverRoom, votes: dict[str, int]
    ) -> list[dict[str, Any]]:
        return [
            {
                "player_id": player_id,
                "player_name": room.players[player_id].name,
                "count": count,
            }
            for player_id, count in votes.items()
        ]

    @staticmethod
    def _next_round(room: UndercoverRoom) -> None:
        room.round_number += 1
        room.phase = "discussion"
        for player in room.players.values():
            player.spoken = False
            player.vote = None


undercover_manager = UndercoverManager()
