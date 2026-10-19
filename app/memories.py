import random
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional


MIN_PLAYERS = 2
MAX_PLAYERS = 8
MISMATCH_REVEAL_SECONDS = 1.2
CARD_SYMBOLS = (
    "🍎", "🚀", "🌈", "🐳", "🎸", "🌻", "🦊", "⚽",
    "🍉", "🦋", "🎈", "🌙", "🐙", "🍄", "🎁", "🧩",
    "🦁", "🍩", "🚲", "⭐️", "🐢", "🎨", "🌵", "🍓",
    "🛸", "🐼", "🎲", "🌺", "🦉", "🍋", "🏀", "🎧",
    "🐸", "🍪", "⛵", "💎",
)
VALID_GRID_SIZES = {4, 6}


def _new_deck(grid_size: int) -> list[str]:
    if grid_size not in VALID_GRID_SIZES:
        raise ValueError("Choisissez une grille de 4 × 4 ou de 6 × 6.")
    pairs = grid_size * grid_size // 2
    symbols = random.sample(CARD_SYMBOLS, pairs)
    deck = symbols * 2
    random.shuffle(deck)
    return deck


def _clean_name(name: str) -> str:
    cleaned = "".join(char for char in name if char >= " " and char != "\x7f")
    return cleaned.strip()[:24] or "Joueur"


@dataclass
class MemoryPlayer:
    player_id: str
    name: str
    ready: bool = False
    pairs: int = 0
    moves: int = 0


@dataclass
class MemoryGame:
    game_id: str
    player_id: str
    player_name: str
    grid_size: int
    cards: list[str]
    started_at: float = field(default_factory=time.time)
    opened: list[int] = field(default_factory=list)
    matched: set[int] = field(default_factory=set)
    moves: int = 0
    points: int = 0
    status: str = "playing"
    pending_mismatch_until: Optional[float] = None
    stats_recorded: bool = False

    def to_dict(self) -> dict[str, Any]:
        _resolve_mismatch(self)
        return {
            "game_id": self.game_id,
            "status": self.status,
            "grid_size": self.grid_size,
            "cards": [
                {
                    "index": index,
                    "face": card if index in self.matched or index in self.opened else None,
                    "matched": index in self.matched,
                    "opened": index in self.opened,
                }
                for index, card in enumerate(self.cards)
            ],
            "matched_pairs": len(self.matched) // 2,
            "total_pairs": len(self.cards) // 2,
            "moves": self.moves,
            "points": self.points,
            "elapsed_seconds": max(0, int(time.time() - self.started_at)),
            "pending_mismatch_until": self.pending_mismatch_until,
        }


@dataclass
class MemoryRoom:
    room_id: str
    host_player_id: str
    grid_size: int
    cards: list[str]
    players: dict[str, MemoryPlayer] = field(default_factory=dict)
    status: str = "lobby"
    match_number: int = 1
    started_at: Optional[float] = None
    turn_index: int = 0
    opened: list[int] = field(default_factory=list)
    matched: set[int] = field(default_factory=set)
    moves: int = 0
    pending_mismatch_until: Optional[float] = None
    winner_ids: list[str] = field(default_factory=list)
    stats_recorded: bool = False

    @property
    def active_players(self) -> list[MemoryPlayer]:
        return list(self.players.values())

    @property
    def current_player(self) -> Optional[MemoryPlayer]:
        players = self.active_players
        if self.status != "playing" or not players:
            return None
        return players[self.turn_index % len(players)]

    def to_dict(self, player_id: str) -> dict[str, Any]:
        if player_id not in self.players:
            raise KeyError("Salon ou joueur introuvable.")
        _resolve_mismatch(self)
        ready_count = sum(player.ready for player in self.players.values())
        all_ready = len(self.players) >= MIN_PLAYERS and ready_count == len(self.players)
        current = self.current_player
        return {
            "room_id": self.room_id,
            "match_number": self.match_number,
            "host_player_id": self.host_player_id,
            "status": self.status,
            "grid_size": self.grid_size,
            "players": [
                {
                    "player_id": player.player_id,
                    "name": player.name,
                    "ready": player.ready,
                    "pairs": player.pairs,
                    "moves": player.moves,
                }
                for player in self.players.values()
            ],
            "player_count": len(self.players),
            "player": {
                "player_id": self.players[player_id].player_id,
                "ready": self.players[player_id].ready,
                "pairs": self.players[player_id].pairs,
                "moves": self.players[player_id].moves,
            },
            "ready_count": ready_count,
            "all_ready": all_ready,
            "can_start": (
                self.status == "lobby"
                and len(self.players) >= MIN_PLAYERS
                and all_ready
            ),
            "turn_player_id": current.player_id if current else None,
            "turn_player_name": current.name if current else None,
            "cards": [
                {
                    "index": index,
                    "face": card if index in self.matched or index in self.opened else None,
                    "matched": index in self.matched,
                    "opened": index in self.opened,
                }
                for index, card in enumerate(self.cards)
            ],
            "matched_pairs": len(self.matched) // 2,
            "total_pairs": len(self.cards) // 2,
            "moves": self.moves,
            "elapsed_seconds": max(
                0, int(time.time() - (self.started_at or time.time()))
            ),
            "pending_mismatch_until": self.pending_mismatch_until,
            "winner_ids": self.winner_ids,
            "scores": sorted(
                [
                    {
                        "player_id": player.player_id,
                        "name": player.name,
                        "pairs": player.pairs,
                        "moves": player.moves,
                        "points": player.pairs * 100,
                    }
                    for player in self.players.values()
                ],
                key=lambda score: (-score["pairs"], score["moves"], score["name"].casefold()),
            ),
        }


def _resolve_mismatch(game: MemoryGame | MemoryRoom, now: Optional[float] = None) -> None:
    current_time = time.time() if now is None else now
    deadline = game.pending_mismatch_until
    if deadline is None or current_time < deadline:
        return
    game.opened.clear()
    game.pending_mismatch_until = None
    if isinstance(game, MemoryRoom) and game.status == "playing" and game.players:
        game.turn_index = (game.turn_index + 1) % len(game.players)


class MemoriesManager:
    def __init__(self) -> None:
        self.solo_games: dict[str, MemoryGame] = {}
        self.rooms: dict[str, MemoryRoom] = {}
        self.lock = threading.RLock()

    def create_solo(self, player_id: str, player_name: str, grid_size: int = 4) -> MemoryGame:
        deck = _new_deck(grid_size)
        with self.lock:
            game = MemoryGame(
                str(uuid.uuid4()), player_id, _clean_name(player_name), grid_size, deck
            )
            self.solo_games[game.game_id] = game
            return game

    def get_solo(self, game_id: str, player_id: str) -> MemoryGame:
        with self.lock:
            game = self.solo_games.get(game_id)
            if not game or game.player_id != player_id:
                raise KeyError("Partie introuvable.")
            return game

    def flip_solo(self, game_id: str, player_id: str, index: int) -> MemoryGame:
        with self.lock:
            game = self.get_solo(game_id, player_id)
            _resolve_mismatch(game)
            if game.status != "playing":
                raise ValueError("Cette partie est terminée.")
            if game.pending_mismatch_until is not None:
                raise ValueError("Patientez le temps de retourner les cartes.")
            self._validate_flip(game.cards, game.opened, game.matched, index)
            game.opened.append(index)
            if len(game.opened) == 2:
                game.moves += 1
                self._resolve_pair(game)
            return game

    def create_room(
        self, player_id: str, player_name: str, grid_size: int = 4,
    ) -> MemoryRoom:
        deck = _new_deck(grid_size)
        with self.lock:
            room_id = uuid.uuid4().hex[:6].upper()
            while room_id in self.rooms:
                room_id = uuid.uuid4().hex[:6].upper()
            room = MemoryRoom(room_id, player_id, grid_size, deck)
            room.players[player_id] = MemoryPlayer(player_id, _clean_name(player_name))
            self.rooms[room_id] = room
            return room

    def join_room(self, room_id: str, player_id: str, player_name: str) -> MemoryRoom:
        with self.lock:
            room = self._get_room(room_id)
            if player_id in room.players:
                room.players[player_id].name = _clean_name(player_name)
                return room
            if room.status != "lobby":
                raise ValueError("Cette partie a déjà commencé.")
            if len(room.players) >= MAX_PLAYERS:
                raise ValueError(f"Ce salon est complet ({MAX_PLAYERS} joueurs maximum).")
            for player in room.players.values():
                player.ready = False
            room.players[player_id] = MemoryPlayer(player_id, _clean_name(player_name))
            return room

    def get_room(self, room_id: str, player_id: str) -> MemoryRoom:
        with self.lock:
            room = self._get_room(room_id)
            if player_id not in room.players:
                raise KeyError("Salon ou joueur introuvable.")
            _resolve_mismatch(room)
            return room

    def list_rooms(self, player_id: Optional[str] = None) -> list[dict[str, Any]]:
        with self.lock:
            return [
                {
                    "room_id": room.room_id,
                    "status": room.status,
                    "player_count": len(room.players),
                    "max_players": MAX_PLAYERS,
                    "grid_size": room.grid_size,
                    "host_name": room.players[room.host_player_id].name,
                    "is_member": player_id in room.players if player_id else False,
                }
                for room in self.rooms.values()
                if room.status != "finished"
            ]

    def set_ready(self, room_id: str, player_id: str, ready: bool = True) -> MemoryRoom:
        with self.lock:
            room = self.get_room(room_id, player_id)
            if room.status != "lobby":
                raise ValueError("Le salon n'attend plus de confirmations.")
            room.players[player_id].ready = ready
            return room

    def start_room(self, room_id: str, player_id: str) -> MemoryRoom:
        with self.lock:
            room = self.get_room(room_id, player_id)
            if room.host_player_id != player_id:
                raise PermissionError("Seul l'hôte peut démarrer la partie.")
            if room.status != "lobby":
                raise ValueError("Cette partie a déjà commencé.")
            if len(room.players) < MIN_PLAYERS:
                raise ValueError("Il faut au moins deux joueurs pour démarrer.")
            if not all(player.ready for player in room.players.values()):
                raise ValueError("Tous les joueurs doivent confirmer qu'ils sont prêts.")
            room.status = "playing"
            room.started_at = time.time()
            return room

    def restart_room(self, room_id: str, player_id: str) -> MemoryRoom:
        with self.lock:
            room = self.get_room(room_id, player_id)
            if room.host_player_id != player_id:
                raise PermissionError("Seul l'hôte peut relancer la partie.")
            if room.status != "finished":
                raise ValueError("La partie doit être terminée pour être relancée.")
            room.cards = _new_deck(room.grid_size)
            room.status = "lobby"
            room.match_number += 1
            room.started_at = None
            room.turn_index = 0
            room.opened.clear()
            room.matched.clear()
            room.moves = 0
            room.pending_mismatch_until = None
            room.winner_ids.clear()
            room.stats_recorded = False
            for player in room.players.values():
                player.ready = False
                player.pairs = 0
                player.moves = 0
            return room

    def flip_room(self, room_id: str, player_id: str, index: int) -> MemoryRoom:
        with self.lock:
            room = self.get_room(room_id, player_id)
            if room.status != "playing":
                raise ValueError("La partie n'accepte pas de cartes pour le moment.")
            if room.pending_mismatch_until is not None:
                raise ValueError("Patientez le temps de retourner les cartes.")
            if room.current_player is None or room.current_player.player_id != player_id:
                raise ValueError("Ce n'est pas votre tour.")
            self._validate_flip(room.cards, room.opened, room.matched, index)
            room.opened.append(index)
            if len(room.opened) == 2:
                room.moves += 1
                room.players[player_id].moves += 1
                self._resolve_pair(room)
            return room

    @staticmethod
    def _validate_flip(
        cards: list[str], opened: list[int], matched: set[int], index: int,
    ) -> None:
        if index < 0 or index >= len(cards):
            raise ValueError("Cette carte n'existe pas.")
        if index in matched or index in opened:
            raise ValueError("Cette carte est déjà retournée.")
        if len(opened) >= 2:
            raise ValueError("Retournez les cartes déjà visibles avant de continuer.")

    @staticmethod
    def _resolve_pair(game: MemoryGame | MemoryRoom) -> None:
        first, second = game.opened
        if game.cards[first] == game.cards[second]:
            game.matched.update((first, second))
            game.opened.clear()
            game.pending_mismatch_until = None
            if isinstance(game, MemoryRoom):
                current = game.current_player
                if current:
                    current.pairs += 1
            else:
                game.points += 100
            if len(game.matched) == len(game.cards):
                game.status = "finished"
                if isinstance(game, MemoryRoom):
                    top_pairs = max(player.pairs for player in game.players.values())
                    game.winner_ids = [
                        player.player_id for player in game.players.values()
                        if player.pairs == top_pairs
                    ]
            return
        game.pending_mismatch_until = time.time() + MISMATCH_REVEAL_SECONDS

    def _get_room(self, room_id: str) -> MemoryRoom:
        room = self.rooms.get(room_id.strip().upper())
        if room is None:
            raise KeyError("Salon introuvable ou expiré.")
        return room


memories_manager = MemoriesManager()
