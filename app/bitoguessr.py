"""Quiz de pays fondé sur une compilation publique d'estimations corporelles."""

import random
import string
import time
import uuid
from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Dict, List, Optional, Tuple

ROUND_COUNT = 10
MAX_PLAYERS = 8
DIFFICULTIES = {"normal", "difficile"}
DATA_SOURCE_URL = "https://www.worlddata.info/average-penissize.php"

# Petit échantillon de faits numériques d'une compilation d'études hétérogènes.
# La source indique qu'ils ne constituent pas un échantillon représentatif.
COUNTRY_AVERAGES_CM: Tuple[Tuple[str, float], ...] = (
    ("Bolivie", 16.51), ("Soudan", 16.47), ("Haïti", 16.01),
    ("Sénégal", 15.89), ("Pays-Bas", 15.87), ("France", 15.74),
    ("Canada", 15.71), ("Italie", 15.35), ("Colombie", 15.26),
    ("Suède", 15.08), ("Honduras", 15.00), ("Argentine", 14.88),
    ("Belgique", 14.77), ("Chili", 14.59), ("Allemagne", 14.52),
    ("Australie", 14.46), ("Espagne", 13.85), ("États-Unis", 13.58),
    ("Japon", 13.56), ("Thaïlande", 11.45),
)


def _make_question(
    difficulty: str,
    country_average: Optional[Tuple[str, float]] = None,
) -> Dict[str, Any]:
    country, average = country_average or random.choice(COUNTRY_AVERAGES_CM)
    if difficulty == "normal":
        prompt = int(average + 0.5)
        accepted = [
            name for name, value in COUNTRY_AVERAGES_CM
            if int(value + 0.5) == prompt
        ]
    else:
        prompt = round(average, 2)
        accepted = [country]

    distractors = [
        name for name, _ in COUNTRY_AVERAGES_CM if name not in accepted
    ]
    options = list(accepted)
    option_count = min(max(0, 4 - len(options)), len(distractors))
    options.extend(random.sample(distractors, k=option_count))
    random.shuffle(options)
    return {
        "prompt_cm": prompt,
        "options": options,
        "accepted": accepted,
        "answer": country,
    }


def _make_questions(difficulty: str, count: int) -> List[Dict[str, Any]]:
    return [
        _make_question(difficulty, country_average)
        for country_average in random.sample(COUNTRY_AVERAGES_CM, k=count)
    ]


@dataclass
class BitoguessrRound:
    question: Dict[str, Any]
    guesses: Dict[str, str] = field(default_factory=dict)


@dataclass
class BitoguessrSoloGame:
    game_id: str
    player_id: str
    player_name: str
    difficulty: str
    questions: List[Dict[str, Any]]
    created_at: float = field(default_factory=time.time)
    round_index: int = 0
    score: int = 0
    results: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "playing"

    def to_dict(self) -> Dict[str, Any]:
        current = self.questions[self.round_index] if self.status == "playing" else None
        result = self.results[-1] if self.results and self.results[-1]["round_number"] == self.round_index + 1 else None
        return {
            "game_id": self.game_id,
            "status": self.status,
            "difficulty": self.difficulty,
            "round_number": min(self.round_index + 1, len(self.questions)),
            "round_count": len(self.questions),
            "score": self.score,
            "player_name": self.player_name,
            "prompt_cm": current["prompt_cm"] if current else None,
            "options": current["options"] if current else [],
            "result": result,
            "results": self.results,
        }


@dataclass
class BitoguessrRoomPlayer:
    player_id: str
    name: str
    score: int = 0
    guess: Optional[str] = None
    results: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class BitoguessrRoom:
    room_id: str
    host_player_id: str
    difficulty: str
    round_count: int
    players: Dict[str, BitoguessrRoomPlayer]
    rounds: List[BitoguessrRound]
    created_at: float = field(default_factory=time.time)
    round_index: int = 0
    status: str = "lobby"
    stats_recorded: bool = False

    @property
    def current_round(self) -> BitoguessrRound:
        return self.rounds[self.round_index]

    def to_dict(self, player_id: str) -> Dict[str, Any]:
        current = (
            self.current_round
            if self.status == "playing" and self.round_index < self.round_count
            else None
        )
        completed = bool(current and len(current.guesses) == len(self.players))
        last_round = None
        if completed or self.status == "finished":
            revealed_round = self.round_index if completed else self.round_count - 1
            revealed = self.rounds[revealed_round]
            last_round = {
                "round_number": revealed_round + 1,
                "prompt_cm": revealed.question["prompt_cm"],
                "answer": revealed.question["answer"],
                "guesses": [
                    {
                        "player_id": player.player_id,
                        "name": player.name,
                        "guess": revealed.guesses.get(player.player_id),
                        "correct": revealed.guesses.get(player.player_id) in revealed.question["accepted"],
                        "score": player.results[revealed_round]["score"]
                        if len(player.results) > revealed_round else 0,
                    }
                    for player in self.players.values()
                ],
            }
        player = self.players[player_id]
        return {
            "room_id": self.room_id,
            "status": self.status,
            "host_player_id": self.host_player_id,
            "difficulty": self.difficulty,
            "round_number": min(self.round_index + 1, self.round_count),
            "round_count": self.round_count,
            "max_players": MAX_PLAYERS,
            "player_count": len(self.players),
            "players": [
                {
                    "player_id": item.player_id,
                    "name": item.name,
                    "score": item.score,
                    "submitted": item.player_id in current.guesses if current else False,
                }
                for item in self.players.values()
            ],
            "can_start": len(self.players) >= 2,
            "player": {
                "player_id": player.player_id,
                "name": player.name,
                "score": player.score,
                "submitted": bool(current and player_id in current.guesses),
            },
            "prompt_cm": current.question["prompt_cm"] if current and not completed else None,
            "options": current.question["options"] if current and not completed else [],
            "last_round": last_round,
        }


class BitoguessrManager:
    def __init__(self) -> None:
        self.solo_games: Dict[str, BitoguessrSoloGame] = {}
        self.rooms: Dict[str, BitoguessrRoom] = {}
        self._lock = RLock()

    @staticmethod
    def _validate_player(player_id: str, player_name: str) -> None:
        if not player_id or len(player_id) > 100:
            raise ValueError("Identifiant de joueur invalide.")
        if not player_name or not player_name.strip():
            raise ValueError("Un nom de joueur est requis.")

    @staticmethod
    def _validate_difficulty(difficulty: str) -> None:
        if difficulty not in DIFFICULTIES:
            raise ValueError("Choisissez le mode normal ou difficile.")

    def create_solo(self, player_id: str, player_name: str, difficulty: str) -> BitoguessrSoloGame:
        self._validate_player(player_id, player_name)
        self._validate_difficulty(difficulty)
        with self._lock:
            game_id = uuid.uuid4().hex
            game = BitoguessrSoloGame(
                game_id, player_id, player_name.strip()[:24], difficulty,
                _make_questions(difficulty, ROUND_COUNT),
            )
            self.solo_games[game_id] = game
            return game

    def get_solo(self, game_id: str, player_id: str) -> BitoguessrSoloGame:
        game = self.solo_games.get(game_id)
        if not game or game.player_id != player_id:
            raise KeyError("Partie introuvable.")
        return game

    def guess_solo(self, game_id: str, player_id: str, guess: str) -> Tuple[BitoguessrSoloGame, Dict[str, Any]]:
        with self._lock:
            game = self.get_solo(game_id, player_id)
            if game.status != "playing":
                raise ValueError("Cette partie est terminée.")
            question = game.questions[game.round_index]
            if guess not in question["options"]:
                raise ValueError("Choisissez un pays proposé.")
            correct = guess in question["accepted"]
            points = int(correct)
            game.score += points
            result = {
                "round_number": game.round_index + 1,
                "prompt_cm": question["prompt_cm"],
                "guess": guess,
                "answer": question["answer"],
                "accepted_answers": question["accepted"],
                "correct": correct,
                "score": points,
                "total_score": game.score,
            }
            game.results.append(result)
            if game.round_index == len(game.questions) - 1:
                game.status = "finished"
            return game, result

    def next_solo(self, game_id: str, player_id: str) -> BitoguessrSoloGame:
        with self._lock:
            game = self.get_solo(game_id, player_id)
            if game.status != "playing" or len(game.results) != game.round_index + 1:
                raise ValueError("Répondez à la manche en cours avant de continuer.")
            game.round_index += 1
            return game

    def create_room(
        self, player_id: str, player_name: str, difficulty: str, round_count: int = ROUND_COUNT,
    ) -> BitoguessrRoom:
        self._validate_player(player_id, player_name)
        self._validate_difficulty(difficulty)
        if type(round_count) is not int or not 1 <= round_count <= 20:
            raise ValueError("Le nombre de manches doit être compris entre 1 et 20.")
        with self._lock:
            room_id = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
            while room_id in self.rooms:
                room_id = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
            room = BitoguessrRoom(
                room_id, player_id, difficulty, round_count,
                {player_id: BitoguessrRoomPlayer(player_id, player_name.strip()[:24])},
                [BitoguessrRound(question) for question in _make_questions(difficulty, round_count)],
            )
            self.rooms[room_id] = room
            return room

    def get_room(self, room_id: str, player_id: str) -> BitoguessrRoom:
        room = self.rooms.get(room_id.upper())
        if not room or player_id not in room.players:
            raise KeyError("Salon introuvable.")
        return room

    def join_room(self, room_id: str, player_id: str, player_name: str) -> BitoguessrRoom:
        self._validate_player(player_id, player_name)
        with self._lock:
            room = self.rooms.get(room_id.upper())
            if not room:
                raise KeyError("Salon introuvable.")
            if player_id in room.players:
                return room
            if room.status != "lobby":
                raise ValueError("Cette partie a déjà commencé.")
            if len(room.players) >= MAX_PLAYERS:
                raise ValueError("Ce salon est complet.")
            room.players[player_id] = BitoguessrRoomPlayer(
                player_id, player_name.strip()[:24],
            )
            return room

    def start_room(self, room_id: str, player_id: str) -> BitoguessrRoom:
        with self._lock:
            room = self.get_room(room_id, player_id)
            if room.host_player_id != player_id:
                raise PermissionError("Seul l’hôte peut lancer la partie.")
            if room.status != "lobby":
                raise ValueError("Cette partie a déjà commencé.")
            if len(room.players) < 2:
                raise ValueError("Il faut au moins deux joueurs pour démarrer.")
            room.status = "playing"
            return room

    def guess_room(self, room_id: str, player_id: str, guess: str) -> Tuple[BitoguessrRoom, Optional[Dict[str, Any]]]:
        with self._lock:
            room = self.get_room(room_id, player_id)
            if room.status != "playing":
                raise ValueError("La partie n’accepte pas de réponse maintenant.")
            current = room.current_round
            if len(current.guesses) == len(room.players):
                raise ValueError("L’hôte doit passer à la manche suivante.")
            if player_id in current.guesses:
                raise ValueError("Votre réponse a déjà été validée.")
            if guess not in current.question["options"]:
                raise ValueError("Choisissez un pays proposé.")
            current.guesses[player_id] = guess
            correct = guess in current.question["accepted"]
            score = int(correct)
            player = room.players[player_id]
            player.score += score
            player.results.append({
                "round_number": room.round_index + 1,
                "prompt_cm": current.question["prompt_cm"],
                "guess": guess,
                "answer": current.question["answer"],
                "correct": correct,
                "score": score,
            })
            if len(current.guesses) != len(room.players):
                return room, None
            if room.round_index == room.round_count - 1:
                room.status = "finished"
            return room, room.to_dict(player_id)["last_round"]

    def next_room(self, room_id: str, player_id: str) -> BitoguessrRoom:
        with self._lock:
            room = self.get_room(room_id, player_id)
            if room.host_player_id != player_id:
                raise PermissionError("Seul l’hôte peut passer à la manche suivante.")
            if room.status != "playing":
                raise ValueError("La partie ne peut pas continuer.")
            if len(room.current_round.guesses) != len(room.players):
                raise ValueError("Tous les joueurs doivent répondre avant de continuer.")
            if room.round_index >= room.round_count - 1:
                raise ValueError("La partie est terminée.")
            room.round_index += 1
            return room

    def list_rooms(self, player_id: Optional[str] = None) -> List[Dict[str, Any]]:
        return [
            {
                "room_id": room.room_id,
                "status": room.status,
                "difficulty": room.difficulty,
                "round_count": room.round_count,
                "player_count": len(room.players),
                "max_players": MAX_PLAYERS,
                "is_member": player_id in room.players if player_id else False,
            }
            for room in self.rooms.values()
            if room.status != "finished"
            and (room.status == "lobby" or player_id in room.players)
        ]


bitoguessr_manager = BitoguessrManager()
