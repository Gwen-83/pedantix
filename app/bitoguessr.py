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

# Valeurs compilées par WorldData ; elles ne constituent pas un échantillon
# représentatif. Les codes ISO-3 relient les réponses aux frontières de la carte.
COUNTRY_AVERAGES_CM: Tuple[Tuple[str, float], ...] = (
    ("ECU", 17.61), ("CMR", 16.67), ("BOL", 16.51), ("SDN", 16.47),
    ("HTI", 16.01), ("SEN", 15.89), ("GMB", 15.88), ("CUB", 15.87),
    ("NLD", 15.87), ("ZMB", 15.78), ("FRA", 15.74), ("AGO", 15.73),
    ("CAN", 15.71), ("EGY", 15.69), ("ZWE", 15.68), ("GEO", 15.61),
    ("PRY", 15.53), ("TCD", 15.39), ("ITA", 15.35), ("CAF", 15.33),
    ("COL", 15.26), ("CIV", 15.22), ("BRA", 15.22), ("SWE", 15.08),
    ("BGR", 15.02), ("CRI", 15.01), ("HND", 15.00), ("HUN", 14.99),
    ("MEX", 14.92), ("DNK", 14.88), ("ARG", 14.88), ("SLV", 14.88),
    ("SRB", 14.87), ("BEL", 14.77), ("HRV", 14.77), ("LVA", 14.69),
    ("BLR", 14.63), ("CHL", 14.59), ("IRN", 14.55), ("AUT", 14.53),
    ("DEU", 14.52), ("DZA", 14.49), ("COD", 14.48), ("AUS", 14.46),
    ("NGA", 14.38), ("CHE", 14.35), ("NOR", 14.34), ("POL", 14.29),
    ("ALB", 14.19), ("CPV", 14.05), ("NZL", 13.99), ("MKD", 13.98),
    ("UKR", 13.97), ("ESP", 13.85), ("FIN", 13.77), ("LBY", 13.74),
    ("IND", 13.72), ("AZE", 13.72), ("AFG", 13.69), ("ISR", 13.60),
    ("USA", 13.58), ("JPN", 13.56), ("TKM", 13.48), ("VEN", 13.33),
    ("GRC", 13.30), ("VNM", 13.22), ("RUS", 13.21), ("ARM", 13.14),
    ("GBR", 13.13), ("TUR", 12.99), ("IRL", 12.78), ("MNG", 12.77),
    ("ROU", 12.73), ("YEM", 12.72), ("KOR", 12.64), ("TWN", 12.60),
    ("CHN", 12.43), ("PAK", 12.20), ("IDN", 11.67), ("SGP", 11.53),
    ("MYS", 11.49), ("THA", 11.45), ("BGD", 11.20), ("HKG", 11.19),
    ("LKA", 10.89), ("PHL", 10.85), ("MMR", 10.70), ("KHM", 10.04),
)


def _make_question(
    difficulty: str,
    country_average: Optional[Tuple[str, float]] = None,
) -> Dict[str, Any]:
    country_code, average = country_average or random.choice(COUNTRY_AVERAGES_CM)
    if difficulty == "normal":
        prompt = int(average + 0.5)
        accepted = [
            code for code, value in COUNTRY_AVERAGES_CM
            if int(value + 0.5) == prompt
        ]
    else:
        prompt = round(average, 2)
        accepted = [
            code for code, value in COUNTRY_AVERAGES_CM
            if round(value, 2) == prompt
        ]
    return {
        "prompt_cm": prompt,
        "countries": [code for code, _ in COUNTRY_AVERAGES_CM],
        "accepted": accepted,
        "answer": country_code,
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
            "countries": current["countries"] if current else [],
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
                "correct_countries": revealed.question["accepted"],
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
                "guess": current.guesses.get(player_id) if current else None,
            },
            "prompt_cm": current.question["prompt_cm"] if current and not completed else None,
            "countries": current.question["countries"] if current and not completed else [],
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
            if guess not in question["countries"]:
                raise ValueError("Ce pays n’a pas de données pour cette partie.")
            correct = guess in question["accepted"]
            points = int(correct)
            game.score += points
            result = {
                "round_number": game.round_index + 1,
                "prompt_cm": question["prompt_cm"],
                "guess": guess,
                "answer": question["answer"],
                "correct_countries": question["accepted"],
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
            if guess not in current.question["countries"]:
                raise ValueError("Ce pays n’a pas de données pour cette partie.")
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
                "correct_countries": current.question["accepted"],
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
