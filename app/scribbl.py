import random
import re
import math
import threading
import time
import unicodedata
import uuid
from dataclasses import dataclass, field
from typing import Any


MIN_PLAYERS = 2
MAX_PLAYERS = 8
TURN_SECONDS = 80
CHOICE_SECONDS = 15
REVEAL_SECONDS = 3
MAX_STROKE_POINTS = 4_000
MAX_CHAT_MESSAGES = 40

WORD_BANK = (
    "ananas", "avion", "baleine", "ballon", "banane", "bateau", "biberon",
    "bicyclette", "boussole", "canard", "carotte", "cerf-volant", "chapeau",
    "chocolat", "ciseaux", "citrouille", "clé", "cochon", "couronne",
    "crayon", "dinosaure", "dragon", "éclair", "éléphant", "escargot",
    "étoile", "fantôme", "fenêtre", "flamant rose", "fleur", "fromage",
    "girafe", "glace", "guitare", "hibou", "horloge", "île", "igloo",
    "koala", "lampadaire", "lapin", "lune", "maison", "marteau", "méduse",
    "montagne", "moustache", "nuage", "ordinateur", "ours", "papillon",
    "parapluie", "pastèque", "piano", "pieuvre", "pingouin", "pizza",
    "poisson", "pomme", "pyramide", "requin", "robot", "rose", "saxophone",
    "serpent", "soleil", "sorcière", "sous-marin", "tasse", "téléphone",
    "tigre", "tortue", "train", "trompette", "valise", "vélo", "voiture",
    "volcan", "zèbre", "bonhomme de neige", "château", "fusée", "arc-en-ciel",
    "brosse à dents", "cactus", "camion", "cascade", "champignon", "coccinelle",
    "feu de camp", "fourmi", "grenouille", "montgolfière", "raquette", "toboggan",
)

DRAW_COLORS = {
    "#172033", "#ffffff", "#f43f5e", "#f97316", "#facc15", "#22c55e",
    "#14b8a6", "#0ea5e9", "#6366f1", "#a855f7", "#ec4899", "#92400e",
}


def _clean_name(name: str) -> str:
    return re.sub(r"[\x00-\x1f\x7f<>]", "", name).strip()[:24] or "Joueur"


def _normalize_word(word: str) -> str:
    decomposed = unicodedata.normalize("NFKD", word.casefold())
    return "".join(
        character for character in decomposed
        if not unicodedata.combining(character) and character.isalnum()
    )


@dataclass
class ScribblPlayer:
    player_id: str
    name: str
    score: int = 0
    correct_guesses: int = 0
    guesses: int = 0
    turns_drawn: int = 0
    guessed_this_turn: bool = False
    last_message_at: float = 0


@dataclass
class ScribblRoom:
    room_id: str
    host_player_id: str
    rounds_per_player: int = 2
    players: dict[str, ScribblPlayer] = field(default_factory=dict)
    status: str = "lobby"
    phase: str = "lobby"
    match_number: int = 1
    turn_index: int = 0
    artist_player_id: str | None = None
    word_choices: list[str] = field(default_factory=list)
    word: str | None = None
    revealed_word: str | None = None
    started_at: float | None = None
    turn_ends_at: float | None = None
    strokes: list[dict[str, Any]] = field(default_factory=list)
    stroke_points: int = 0
    guessed_player_ids: set[str] = field(default_factory=set)
    chat: list[dict[str, Any]] = field(default_factory=list)
    stats_recorded: bool = False
    created_at: float = field(default_factory=time.time)

    @property
    def turn_count(self) -> int:
        return len(self.players) * self.rounds_per_player

    @property
    def round_number(self) -> int:
        return self.turn_index // max(1, len(self.players)) + 1

    def to_dict(self, player_id: str) -> dict[str, Any]:
        if player_id not in self.players:
            raise KeyError("Salon ou joueur introuvable.")
        player = self.players[player_id]
        is_artist = player_id == self.artist_player_id
        return {
            "room_id": self.room_id,
            "host_player_id": self.host_player_id,
            "status": self.status,
            "phase": self.phase,
            "match_number": self.match_number,
            "round_number": (
                min(self.round_number, self.rounds_per_player)
                if self.status in {"playing", "finished"} else 0
            ),
            "rounds_per_player": self.rounds_per_player,
            "turn_index": self.turn_index,
            "turn_count": self.turn_count,
            "artist_player_id": self.artist_player_id,
            "is_artist": is_artist,
            "players": [
                {
                    "player_id": item.player_id,
                    "name": item.name,
                    "score": item.score,
                    "correct_guesses": item.correct_guesses,
                    "guesses": item.guesses,
                    "turns_drawn": item.turns_drawn,
                    "guessed": item.guessed_this_turn,
                    "is_artist": item.player_id == self.artist_player_id,
                }
                for item in self.players.values()
            ],
            "player_count": len(self.players),
            "can_start": (
                self.status == "lobby" and len(self.players) >= MIN_PLAYERS
                and player_id == self.host_player_id
            ),
            "can_restart": self.status == "finished" and player_id == self.host_player_id,
            "word_choices": self.word_choices.copy()
            if is_artist and self.phase == "choosing" else [],
            "word_hint": self._word_hint() if self.phase == "drawing" else "",
            "word": (
                self.word if is_artist and self.phase == "drawing"
                else self.revealed_word if self.phase == "reveal"
                else None
            ),
            "seconds_remaining": max(
                0, int((self.turn_ends_at or time.time()) - time.time() + 0.999)
            ),
            "strokes": self.strokes,
            "chat": self.chat[-MAX_CHAT_MESSAGES:],
            "winner_ids": self._winner_ids() if self.status == "finished" else [],
        }

    def _word_hint(self) -> str:
        return " ".join(
            " " if character.isspace() else "_" for character in (self.word or "")
        )

    def _winner_ids(self) -> list[str]:
        if not self.players:
            return []
        highest_score = max(player.score for player in self.players.values())
        return [
            player.player_id for player in self.players.values()
            if player.score == highest_score
        ]


class ScribblManager:
    def __init__(self) -> None:
        self.rooms: dict[str, ScribblRoom] = {}
        self._lock = threading.RLock()

    def create_room(
        self, player_id: str, player_name: str, rounds_per_player: int = 2,
    ) -> ScribblRoom:
        if rounds_per_player not in (1, 2, 3):
            raise ValueError("Choisissez une partie de 1, 2 ou 3 manches par joueur.")
        with self._lock:
            room_id = uuid.uuid4().hex[:6].upper()
            while room_id in self.rooms:
                room_id = uuid.uuid4().hex[:6].upper()
            room = ScribblRoom(room_id, player_id, rounds_per_player)
            room.players[player_id] = ScribblPlayer(player_id, _clean_name(player_name))
            self.rooms[room_id] = room
            return room

    def join_room(
        self, room_id: str, player_id: str, player_name: str,
    ) -> ScribblRoom:
        with self._lock:
            room = self._get_room(room_id)
            existing = room.players.get(player_id)
            if existing:
                existing.name = _clean_name(player_name)
                return room
            if room.status != "lobby":
                raise ValueError("Cette partie a déjà commencé.")
            if len(room.players) >= MAX_PLAYERS:
                raise ValueError(f"Ce salon est complet ({MAX_PLAYERS} joueurs maximum).")
            room.players[player_id] = ScribblPlayer(player_id, _clean_name(player_name))
            return room

    def get_room(self, room_id: str, player_id: str) -> ScribblRoom:
        with self._lock:
            room = self._get_room(room_id)
            if player_id not in room.players:
                raise KeyError("Salon ou joueur introuvable.")
            self._advance(room)
            return room

    def list_rooms(self, player_id: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            for room in self.rooms.values():
                self._advance(room)
            return [
                {
                    "room_id": room.room_id,
                    "status": room.status,
                    "player_count": len(room.players),
                    "max_players": MAX_PLAYERS,
                    "host_name": room.players[room.host_player_id].name,
                    "is_member": player_id in room.players if player_id else False,
                }
                for room in self.rooms.values()
                if room.status != "finished"
            ]

    def start_room(self, room_id: str, player_id: str) -> ScribblRoom:
        with self._lock:
            room = self.get_room(room_id, player_id)
            if room.host_player_id != player_id:
                raise PermissionError("Seul l’hôte peut démarrer la partie.")
            if room.status != "lobby":
                raise ValueError("Cette partie a déjà démarré.")
            if len(room.players) < MIN_PLAYERS:
                raise ValueError(f"Il faut au moins {MIN_PLAYERS} joueurs pour démarrer.")
            room.status = "playing"
            room.started_at = time.time()
            room.turn_index = 0
            self._begin_turn(room)
            return room

    def choose_word(
        self, room_id: str, player_id: str, word_index: int,
    ) -> ScribblRoom:
        with self._lock:
            room = self.get_room(room_id, player_id)
            self._require_artist(room, player_id, "choosing")
            if not 0 <= word_index < len(room.word_choices):
                raise ValueError("Choisissez l’un des mots proposés.")
            self._start_drawing(room, room.word_choices[word_index])
            return room

    def add_stroke(
        self,
        room_id: str,
        player_id: str,
        points: list[list[float]],
        color: str,
        width: float,
        start: bool,
    ) -> dict[str, Any]:
        with self._lock:
            room = self.get_room(room_id, player_id)
            self._require_artist(room, player_id, "drawing")
            if color not in DRAW_COLORS:
                raise ValueError("Cette couleur n’est pas autorisée.")
            if not math.isfinite(width) or not 2 <= width <= 40:
                raise ValueError("Épaisseur de trait invalide.")
            if not points or len(points) > 32:
                raise ValueError("Un tracé doit contenir de 1 à 32 points.")
            clean_points: list[list[float]] = []
            for point in points:
                if (
                    not isinstance(point, list)
                    or len(point) != 2
                    or any(
                        not isinstance(value, (int, float))
                        or isinstance(value, bool)
                        or not math.isfinite(value)
                        or value < 0
                        or value > 1
                        for value in point
                    )
                ):
                    raise ValueError("Coordonnée de dessin invalide.")
                clean_points.append([float(point[0]), float(point[1])])
            if room.stroke_points + len(clean_points) > MAX_STROKE_POINTS:
                raise ValueError("Limite de dessin atteinte pour ce tour.")
            if start:
                room.strokes.append({
                    "color": color,
                    "width": float(width),
                    "points": [],
                })
            if not room.strokes:
                raise ValueError("Commencez le tracé avant d’envoyer des points.")
            room.strokes[-1]["points"].extend(clean_points)
            room.stroke_points += len(clean_points)
            return {
                "type": "draw",
                "player_id": player_id,
                "color": color,
                "width": float(width),
                "start": start,
                "points": clean_points,
            }

    def clear_canvas(self, room_id: str, player_id: str) -> ScribblRoom:
        with self._lock:
            room = self.get_room(room_id, player_id)
            self._require_artist(room, player_id, "drawing")
            room.strokes.clear()
            room.stroke_points = 0
            return room

    def submit_guess(
        self, room_id: str, player_id: str, guess: str,
    ) -> tuple[ScribblRoom, dict[str, Any]]:
        with self._lock:
            room = self.get_room(room_id, player_id)
            player = room.players[player_id]
            if player.guessed_this_turn:
                raise ValueError("Vous avez déjà trouvé le mot.")
            if room.status != "playing" or room.phase != "drawing":
                raise ValueError("Il n’y a pas de mot à deviner maintenant.")
            if player_id == room.artist_player_id:
                raise ValueError("Le dessinateur ne peut pas proposer de réponse.")
            clean_guess = re.sub(r"[\x00-\x1f\x7f]", "", guess).strip()[:80]
            if not clean_guess:
                raise ValueError("Écrivez une proposition.")
            now = time.time()
            correct = _normalize_word(clean_guess) == _normalize_word(room.word or "")
            if not correct and now - player.last_message_at < 0.2:
                raise ValueError("Patientez un instant avant de proposer une réponse.")
            player.last_message_at = now
            player.guesses += 1
            if correct:
                player.guessed_this_turn = True
                player.correct_guesses += 1
                remaining = max(0, (room.turn_ends_at or now) - now)
                points = max(100, round(100 + 900 * remaining / TURN_SECONDS))
                player.score += points
                artist = room.players[room.artist_player_id or ""]
                artist.score += round(points / 2)
                room.guessed_player_ids.add(player_id)
                room.chat.append({
                    "kind": "correct",
                    "player_id": player_id,
                    "player_name": player.name,
                    "text": f"{player.name} a trouvé le mot ! (+{points} pts)",
                })
                non_artists = {
                    item.player_id for item in room.players.values()
                    if item.player_id != room.artist_player_id
                }
                if non_artists.issubset(room.guessed_player_ids):
                    self._reveal_turn(room, now)
            else:
                room.chat.append({
                    "kind": "guess",
                    "player_id": player_id,
                    "player_name": player.name,
                    "text": clean_guess,
                })
            room.chat = room.chat[-MAX_CHAT_MESSAGES:]
            return room, {"correct": correct, "points": points if correct else 0}

    def send_message(
        self, room_id: str, player_id: str, text: str,
    ) -> tuple[ScribblRoom, dict[str, Any]]:
        with self._lock:
            room = self.get_room(room_id, player_id)
            player = room.players[player_id]
            now = time.time()
            if now - player.last_message_at < 0.35:
                raise ValueError("Patientez un instant avant d’envoyer un autre message.")
            clean_text = re.sub(r"[\x00-\x1f\x7f<>]", "", text).strip()[:180]
            if not clean_text:
                raise ValueError("Écrivez un message.")
            player.last_message_at = now
            room.chat.append({
                "kind": "message",
                "player_id": player_id,
                "player_name": player.name,
                "text": clean_text,
            })
            room.chat = room.chat[-MAX_CHAT_MESSAGES:]
            return room, {"type": "message"}

    def leave_room(self, room_id: str, player_id: str) -> ScribblRoom | None:
        with self._lock:
            room = self.rooms.get(room_id.upper())
            if room is None:
                return None
            room.players.pop(player_id, None)
            room.guessed_player_ids.discard(player_id)
            if not room.players:
                self.rooms.pop(room.room_id, None)
                return None
            if room.host_player_id == player_id:
                room.host_player_id = next(iter(room.players))
            if room.status == "playing":
                if len(room.players) < MIN_PLAYERS:
                    room.status = "finished"
                    room.phase = "finished"
                    room.turn_ends_at = None
                elif room.artist_player_id == player_id:
                    self._reveal_turn(room, time.time())
                elif room.phase == "drawing":
                    remaining_guessers = {
                        item.player_id for item in room.players.values()
                        if item.player_id != room.artist_player_id
                    }
                    if remaining_guessers.issubset(room.guessed_player_ids):
                        self._reveal_turn(room, time.time())
            return room

    def restart_room(self, room_id: str, player_id: str) -> ScribblRoom:
        with self._lock:
            room = self.get_room(room_id, player_id)
            if room.host_player_id != player_id:
                raise PermissionError("Seul l’hôte peut relancer la partie.")
            if room.status != "finished":
                raise ValueError("La partie doit être terminée pour être relancée.")
            room.match_number += 1
            room.status = "lobby"
            room.phase = "lobby"
            room.turn_index = 0
            room.artist_player_id = None
            room.word_choices.clear()
            room.word = None
            room.revealed_word = None
            room.started_at = None
            room.turn_ends_at = None
            room.strokes.clear()
            room.stroke_points = 0
            room.guessed_player_ids.clear()
            room.chat.clear()
            room.stats_recorded = False
            for player in room.players.values():
                player.score = 0
                player.correct_guesses = 0
                player.guesses = 0
                player.turns_drawn = 0
                player.guessed_this_turn = False
            return room

    def advance_timers(self, room_id: str) -> bool:
        with self._lock:
            room = self.rooms.get(room_id.upper())
            if room is None:
                return False
            return self._advance(room)

    def _advance(self, room: ScribblRoom) -> bool:
        if room.status != "playing" or room.turn_ends_at is None:
            return False
        now = time.time()
        if now < room.turn_ends_at:
            return False
        if room.phase == "choosing":
            self._start_drawing(room, random.choice(room.word_choices), now)
        elif room.phase == "drawing":
            self._reveal_turn(room, now)
        elif room.phase == "reveal":
            room.turn_index += 1
            if room.turn_index >= room.turn_count:
                room.status = "finished"
                room.phase = "finished"
                room.turn_ends_at = None
            else:
                self._begin_turn(room, now)
        return True

    def _begin_turn(self, room: ScribblRoom, now: float | None = None) -> None:
        current_time = time.time() if now is None else now
        player_ids = list(room.players)
        room.artist_player_id = player_ids[room.turn_index % len(player_ids)]
        room.phase = "choosing"
        room.word_choices = random.sample(WORD_BANK, 3)
        room.word = None
        room.revealed_word = None
        room.turn_ends_at = current_time + CHOICE_SECONDS
        room.strokes.clear()
        room.stroke_points = 0
        room.guessed_player_ids.clear()
        for player in room.players.values():
            player.guessed_this_turn = False

    def _start_drawing(
        self, room: ScribblRoom, word: str, now: float | None = None,
    ) -> None:
        current_time = time.time() if now is None else now
        if word not in room.word_choices:
            raise ValueError("Choisissez l’un des mots proposés.")
        room.word = word
        room.phase = "drawing"
        room.turn_ends_at = current_time + TURN_SECONDS
        room.players[room.artist_player_id or ""].turns_drawn += 1
        room.chat.append({
            "kind": "system",
            "text": f"{room.players[room.artist_player_id or ''].name} commence à dessiner.",
        })
        room.chat = room.chat[-MAX_CHAT_MESSAGES:]

    def _reveal_turn(self, room: ScribblRoom, now: float) -> None:
        room.revealed_word = room.word
        room.phase = "reveal"
        room.turn_ends_at = now + REVEAL_SECONDS
        if room.word:
            room.chat.append({
                "kind": "system",
                "text": f"Le mot était : {room.word}",
            })
            room.chat = room.chat[-MAX_CHAT_MESSAGES:]

    @staticmethod
    def _require_artist(room: ScribblRoom, player_id: str, phase: str) -> None:
        if room.status != "playing" or room.phase != phase:
            raise ValueError("Cette action n’est pas disponible maintenant.")
        if room.artist_player_id != player_id:
            raise ValueError("Seul le dessinateur peut effectuer cette action.")

    def _get_room(self, room_id: str) -> ScribblRoom:
        room = self.rooms.get(room_id.upper())
        if room is None:
            raise KeyError("Salon introuvable ou expiré.")
        self._advance(room)
        return room


scribbl_manager = ScribblManager()
