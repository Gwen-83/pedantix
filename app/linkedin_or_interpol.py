import hashlib
import json
import random
import string
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock
from typing import Any, Dict, List, Optional, Tuple

DATA_PATH = Path(__file__).resolve().parent / "data" / "linkedin_or_interpol" / "metadata.json"
DATA_IMAGES_DIR = DATA_PATH.parent / "images"
VALID_MODES = {"solo", "multiplayer", "solo-infinite", "classique", "infini"}
VALID_CHOICES = {"linkedin", "interpol"}
DEFAULT_ROUND_COUNT = 10
MAX_ROUND_COUNT = 20
MAX_PLAYERS = 8


def _normalize_solo_mode(mode: str) -> str:
    cleaned = (mode or "solo").strip().lower()
    if cleaned not in VALID_MODES:
        raise ValueError("Mode de jeu invalide.")
    if cleaned in {"infini", "solo-infinite"}:
        return "solo-infinite"
    if cleaned == "multiplayer":
        return "multiplayer"
    return "solo"


def _evaluate_person_guess(person: Dict[str, Any], raw_guess: str) -> Tuple[str, bool, Optional[str]]:
    guess = (raw_guess or "").strip().lower()
    if guess not in VALID_CHOICES:
        return guess, False, "Choix invalide. Répondez par linkedin ou interpol."

    is_friend_case = person.get("special_case") == "friend"
    if is_friend_case:
        correct = guess in VALID_CHOICES
        if guess == "linkedin":
            message = "Oui, mais bientôt ça sera interpol."
        else:
            message = "C’était linkedin, mais interpol accepté, c’est un malade."
    else:
        correct = guess == person["label"]
        message = None

    return guess, correct, message


@dataclass
class LinkedinOrInterpolSoloGame:
    game_id: str
    player_id: str
    player_name: str
    mode: str
    rounds: List[Dict[str, Any]]
    round_count: Optional[int]
    created_at: float = field(default_factory=time.time)
    round_index: int = 0
    score: int = 0
    streak: int = 0
    best_streak: int = 0
    results: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "playing"
    stats_recorded: bool = False
    recorded_best_streak: int = 0


@dataclass
class LinkedinOrInterpolRoomPlayer:
    player_id: str
    name: str
    score: int = 0
    streak: int = 0
    best_streak: int = 0
    is_spectator: bool = False
    results: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class LinkedinOrInterpolRound:
    person: Dict[str, Any]
    guesses: Dict[str, Dict[str, Any]] = field(default_factory=dict)


@dataclass
class LinkedinOrInterpolRoom:
    room_id: str
    host_player_id: str
    round_count: int
    players: Dict[str, LinkedinOrInterpolRoomPlayer]
    rounds: List[LinkedinOrInterpolRound]
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    round_index: int = 0
    match_number: int = 1
    status: str = "lobby"
    stats_recorded: bool = False

    @property
    def active_players(self) -> List[LinkedinOrInterpolRoomPlayer]:
        return [player for player in self.players.values() if not player.is_spectator]

    @property
    def spectators(self) -> List[LinkedinOrInterpolRoomPlayer]:
        return [player for player in self.players.values() if player.is_spectator]

    @property
    def current_round(self) -> LinkedinOrInterpolRound:
        return self.rounds[self.round_index]

    def is_round_complete(self) -> bool:
        if self.status != "playing" or self.round_index >= self.round_count:
            return False
        active_ids = [player.player_id for player in self.active_players]
        if not active_ids:
            return False
        current = self.current_round
        return all(pid in current.guesses for pid in active_ids)


class LinkedinOrInterpolManager:
    def __init__(self) -> None:
        self.dataset: List[Dict[str, Any]] = self._load_dataset()
        self.games: Dict[str, Dict[str, Any]] = {}
        self.solo_games: Dict[str, LinkedinOrInterpolSoloGame] = {}
        self.rooms: Dict[str, LinkedinOrInterpolRoom] = {}
        self.leaderboard: List[Dict[str, Any]] = []
        self._draw_history: Dict[str, int] = {}
        self._lock = RLock()

    @staticmethod
    def _load_dataset() -> List[Dict[str, Any]]:
        records: List[Dict[str, Any]] = []
        if DATA_PATH.exists():
            with DATA_PATH.open(encoding="utf-8") as handle:
                try:
                    data = json.load(handle)
                except json.JSONDecodeError:
                    data = []
            if isinstance(data, list):
                records.extend(data)

        if DATA_IMAGES_DIR.exists():
            records_by_id = {str(entry.get("id") or ""): entry for entry in records if str(entry.get("id") or "")}
            for image_path in sorted(DATA_IMAGES_DIR.glob("*.webp")):
                person_id = image_path.stem
                if person_id in records_by_id:
                    continue
                seed = int(hashlib.sha256(person_id.encode("utf-8")).hexdigest(), 16)
                label = "linkedin" if seed % 2 == 0 else "interpol"
                records_by_id[person_id] = {
                    "id": person_id,
                    "name": "Portrait",
                    "surname": str(len(records_by_id) + 1),
                    "description": "Portrait ajouté à la collection. Révélez-le en jouant et découvrez sa vraie catégorie.",
                    "label": label,
                    "source": "local-fallback",
                    "source_url": f"https://linkedin-or-interpol.com/images/profiles/{image_path.name}",
                    "image_path": f"images/{image_path.name}",
                    "manual_added": True,
                }
            records = list(records_by_id.values())

        return records

    @staticmethod
    def _image_url(image_path: str) -> str:
        return f"/api/linkedin-or-interpol/image/{Path(image_path).name}"

    @staticmethod
    def _validate_player(player_id: str, player_name: str) -> Tuple[str, str]:
        cleaned_id = (player_id or "").strip()
        if not cleaned_id or len(cleaned_id) > 100:
            raise ValueError("Identifiant de joueur invalide.")
        cleaned_name = (player_name or "").strip()[:24]
        if not cleaned_name:
            raise ValueError("Un nom de joueur est requis.")
        return cleaned_id, cleaned_name

    def _sanitize_person(self, person: Dict[str, Any]) -> Dict[str, Any]:
        """Retourne uniquement l'identifiant et la photo avant la réponse du joueur."""
        return {
            "id": person["id"],
            "image_url": self._image_url(person["image_path"]),
        }

    def _reveal_person(self, person: Dict[str, Any]) -> Dict[str, Any]:
        """Retourne l'identité complète et les activités une fois la réponse validée."""
        name = (person.get("name") or "").strip()
        surname = (person.get("surname") or "").strip()
        full_name = f"{name} {surname}".strip() or "Identité inconnue"
        return {
            "id": person["id"],
            "name": name,
            "surname": surname,
            "full_name": full_name,
            "description": (person.get("description") or "").strip(),
            "special_case": person.get("special_case"),
            "image_url": self._image_url(person["image_path"]),
            "answer": person["label"],
            "label": person["label"],
        }

    def _record_leaderboard_entry(
        self,
        player_id: str,
        best_streak: int,
        score: Optional[int] = None,
        mode: str = "solo-infinite",
    ) -> None:
        player_name = (player_id or "guest").strip() or "guest"
        normalized = player_name.casefold()
        best_streak = max(0, int(best_streak))
        best_score = max(0, int(score if score is not None else best_streak))

        with self._lock:
            existing = next(
                (entry for entry in self.leaderboard if entry["player_id"].casefold() == normalized),
                None,
            )
            if existing is None:
                self.leaderboard.append(
                    {
                        "player_id": player_name,
                        "best_streak": best_streak,
                        "best_score": best_score,
                        "mode": mode,
                    }
                )
            else:
                existing["player_id"] = player_name
                existing["best_streak"] = max(int(existing.get("best_streak", 0)), best_streak)
                existing["best_score"] = max(int(existing.get("best_score", 0)), best_score)

            self.leaderboard = sorted(
                self.leaderboard,
                key=lambda entry: (
                    -int(entry.get("best_streak", 0)),
                    -int(entry.get("best_score", 0)),
                    entry["player_id"].lower(),
                ),
            )[:20]

    def get_leaderboard(self, limit: int = 10) -> List[Dict[str, Any]]:
        with self._lock:
            items = sorted(
                self.leaderboard,
                key=lambda entry: (
                    -int(entry.get("best_streak", 0)),
                    -int(entry.get("best_score", 0)),
                    entry["player_id"].lower(),
                ),
            )[: max(1, min(int(limit), 20))]
            return [
                {
                    "rank": index + 1,
                    "player_id": entry["player_id"],
                    "player_name": entry["player_id"],
                    "best_streak": int(entry.get("best_streak", 0)),
                    "best_score": int(entry.get("best_score", entry.get("best_streak", 0))),
                }
                for index, entry in enumerate(items)
            ]

    def _mark_person_seen(self, person_id: str) -> None:
        if not person_id:
            return
        with self._lock:
            self._draw_history[person_id] = self._draw_history.get(person_id, 0) + 1

    @staticmethod
    def _is_manual_profile(person: Dict[str, Any]) -> bool:
        if bool(person.get("manual_added")):
            return True
        source = str(person.get("source") or "").strip().lower()
        return source == "local-fallback"

    @staticmethod
    def _base_rarity_rank(person: Dict[str, Any]) -> int:
        if LinkedinOrInterpolManager._is_manual_profile(person):
            return 1

        digest = int(hashlib.sha256(str(person.get("id") or "").encode("utf-8")).hexdigest(), 16)
        bucket = digest % 100
        if bucket < 18:
            return 2
        if bucket < 58:
            return 3
        return 4

    @staticmethod
    def _rarity_label_for_rank(rarity_rank: int) -> str:
        return {
            1: "Très rare",
            2: "Rare",
            3: "Peu commune",
            4: "Commune",
        }.get(int(rarity_rank), "Commune")

    def _profile_rarity(self, person: Dict[str, Any]) -> Dict[str, Any]:
        person_id = str(person.get("id") or "")
        seen_total = int(self._draw_history.get(person_id, 0))
        rarity_rank = self._base_rarity_rank(person)
        rarity_label = self._rarity_label_for_rank(rarity_rank)

        rarity_weight = {
            1: 1.2,
            2: 1.7,
            3: 2.4,
            4: 3.2,
        }.get(rarity_rank, 3.2)

        return {
            "id": person_id,
            "name": (person.get("name") or "").strip(),
            "surname": (person.get("surname") or "").strip(),
            "label": person.get("label"),
            "rarity_label": rarity_label,
            "rarity_rank": rarity_rank,
            "seen_total": seen_total,
            "draw_weight": round(rarity_weight, 4),
            "image_url": self._image_url(person.get("image_path", "")),
        }

    def get_catalog(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        with self._lock:
            catalog = [self._profile_rarity(entry) for entry in self.dataset]
            catalog.sort(
                key=lambda entry: (
                    int(entry["rarity_rank"]),
                    (entry.get("name") or "").lower(),
                    (entry.get("surname") or "").lower(),
                )
            )
            if limit is not None:
                return catalog[: max(1, int(limit))]
            return catalog

    def _build_rounds(
        self,
        rounds: int = DEFAULT_ROUND_COUNT,
        exclude_ids: Optional[set] = None,
        recent_ids: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        if not self.dataset:
            raise ValueError("Le jeu LinkedIn ou Interpol n’a pas de données disponibles.")
        pool = list(self.dataset)
        if exclude_ids:
            pool = [entry for entry in pool if entry.get("id") not in exclude_ids]
        if not pool:
            pool = list(self.dataset)

        recent = {str(value) for value in (recent_ids or []) if value}
        unseen = [entry for entry in pool if str(entry.get("id") or "") not in recent]
        if not unseen:
            unseen = pool

        weighted = []
        weights = []
        for entry in unseen:
            rarity_rank = self._base_rarity_rank(entry)
            weight = {
                1: 1.2,
                2: 1.7,
                3: 2.4,
                4: 3.2,
            }.get(rarity_rank, 3.2)
            weighted.append(entry)
            weights.append(weight)

        sample_size = max(1, min(int(rounds or DEFAULT_ROUND_COUNT), len(weighted)))
        chosen = random.choices(weighted, weights=weights, k=sample_size)
        deduped: List[Dict[str, Any]] = []
        seen_in_pick: set[str] = set()
        for entry in chosen:
            person_id = str(entry.get("id") or "")
            if person_id in seen_in_pick:
                continue
            seen_in_pick.add(person_id)
            deduped.append(entry)
        if len(deduped) < sample_size:
            for entry in weighted:
                person_id = str(entry.get("id") or "")
                if person_id in seen_in_pick:
                    continue
                deduped.append(entry)
                if len(deduped) >= sample_size:
                    break
        return deduped[:sample_size]

    # ------------------------------------------------------------------
    # Solo API (avec étape de révélation après chaque réponse)
    # ------------------------------------------------------------------

    def solo_state(self, game: LinkedinOrInterpolSoloGame) -> Dict[str, Any]:
        answered_current = (
            len(game.results) == game.round_index + 1
            and game.results[-1]["round_number"] == game.round_index + 1
        )
        result = game.results[-1] if (answered_current or game.status == "finished") and game.results else None
        awaiting_next = bool(game.status == "playing" and answered_current)

        if game.status == "playing" and not answered_current and game.round_index < len(game.rounds):
            current_person = self._sanitize_person(game.rounds[game.round_index])
        elif result is not None:
            current_person = result["person"]
        else:
            current_person = None

        round_number = (
            game.round_index + 1
            if game.mode == "solo-infinite"
            else min(game.round_index + 1, game.round_count or len(game.rounds))
        )
        return {
            "game_id": game.game_id,
            "player_id": game.player_id,
            "player_name": game.player_name,
            "mode": game.mode,
            "status": game.status,
            "round_index": game.round_index,
            "round_number": round_number,
            "round_count": game.round_count,
            "score": game.score,
            "streak": game.streak,
            "best_streak": game.best_streak,
            "awaiting_next": awaiting_next,
            "current_person": current_person,
            "result": result,
            "results": game.results,
            "history": game.results,
            "choices": ["linkedin", "interpol"],
        }

    def create_solo(
        self,
        player_id: str,
        player_name: str,
        mode: str = "solo",
        round_count: int = DEFAULT_ROUND_COUNT,
    ) -> LinkedinOrInterpolSoloGame:
        cleaned_id, cleaned_name = self._validate_player(player_id, player_name)
        normalized_mode = _normalize_solo_mode(mode)
        if normalized_mode == "multiplayer":
            normalized_mode = "solo"
        if normalized_mode != "solo-infinite":
            if type(round_count) is not int or not 1 <= round_count <= MAX_ROUND_COUNT:
                raise ValueError(f"Le nombre de manches doit être compris entre 1 et {MAX_ROUND_COUNT}.")
            effective_round_count: Optional[int] = round_count
            chosen_rounds = self._build_rounds(round_count)
        else:
            effective_round_count = None
            chosen_rounds = self._build_rounds(DEFAULT_ROUND_COUNT)

        for person in chosen_rounds:
            self._mark_person_seen(str(person.get("id") or ""))

        with self._lock:
            game_id = uuid.uuid4().hex
            game = LinkedinOrInterpolSoloGame(
                game_id=game_id,
                player_id=cleaned_id,
                player_name=cleaned_name,
                mode=normalized_mode,
                rounds=chosen_rounds,
                round_count=effective_round_count,
            )
            self.solo_games[game_id] = game
            return game

    def get_solo(self, game_id: str, player_id: str) -> LinkedinOrInterpolSoloGame:
        with self._lock:
            game = self.solo_games.get(game_id)
            if not game:
                raise KeyError("Partie introuvable.")
            if player_id and game.player_id != player_id:
                raise PermissionError("Cette partie ne vous appartient pas.")
            return game

    def guess_solo(
        self, game_id: str, player_id: str, raw_guess: str
    ) -> Tuple[LinkedinOrInterpolSoloGame, Dict[str, Any]]:
        with self._lock:
            game = self.get_solo(game_id, player_id)
            if game.status != "playing":
                raise ValueError("Cette partie est terminée.")
            if len(game.results) == game.round_index + 1:
                raise ValueError("Passez à la manche suivante avant de répondre à nouveau.")

            current = game.rounds[game.round_index]
            guess, correct, message = _evaluate_person_guess(current, raw_guess)
            revealed = self._reveal_person(current)

            if correct:
                game.streak += 1
                game.best_streak = max(game.best_streak, game.streak)
                game.score += 1
            else:
                game.streak = 0

            points = 1 if correct else 0
            result = {
                "round_number": game.round_index + 1,
                "person_id": current["id"],
                "name": revealed["name"],
                "surname": revealed["surname"],
                "full_name": revealed["full_name"],
                "description": revealed["description"],
                "image_url": revealed["image_url"],
                "special_case": revealed["special_case"],
                "person": revealed,
                "guess": guess,
                "answer": current["label"],
                "correct": correct,
                "score": points,
                "total_score": game.score,
                "streak": game.streak,
                "best_streak": game.best_streak,
                "message": message,
            }
            game.results.append(result)

            if game.mode == "solo-infinite":
                if game.best_streak > 0 or game.status == "finished":
                    self._record_leaderboard_entry(
                        game.player_name,
                        game.best_streak,
                        score=game.score,
                        mode="solo-infinite",
                    )
            else:
                if game.round_index >= len(game.rounds) - 1:
                    game.status = "finished"
                    self._record_leaderboard_entry(
                        game.player_name,
                        game.best_streak,
                        score=game.score,
                        mode="solo",
                    )

            return game, result

    def next_solo(self, game_id: str, player_id: str) -> LinkedinOrInterpolSoloGame:
        with self._lock:
            game = self.get_solo(game_id, player_id)
            if game.status != "playing":
                raise ValueError("Cette partie est terminée.")
            if len(game.results) != game.round_index + 1:
                raise ValueError("Répondez à la manche en cours avant de continuer.")

            game.round_index += 1
            if game.mode == "solo-infinite" and game.round_index >= len(game.rounds):
                seen_ids = {entry["id"] for entry in game.rounds}
                new_rounds = self._build_rounds(DEFAULT_ROUND_COUNT, exclude_ids=seen_ids)
                for person in new_rounds:
                    self._mark_person_seen(str(person.get("id") or ""))
                game.rounds.extend(new_rounds)
            elif game.mode != "solo-infinite" and game.round_index >= len(game.rounds):
                game.status = "finished"
            return game

    # ------------------------------------------------------------------
    # Salons Multijoueurs
    # ------------------------------------------------------------------

    def room_state(self, room: LinkedinOrInterpolRoom, player_id: str) -> Dict[str, Any]:
        if player_id not in room.players:
            raise KeyError("Salon introuvable.")

        current = (
            room.current_round
            if room.status == "playing" and room.round_index < room.round_count
            else None
        )
        completed = room.is_round_complete()
        active_players = room.active_players

        last_round = None
        if completed or room.status == "finished":
            revealed_index = room.round_index if completed else room.round_count - 1
            revealed_round = room.rounds[revealed_index]
            revealed_person = self._reveal_person(revealed_round.person)
            guesses_list = []
            for player in active_players:
                entry = revealed_round.guesses.get(player.player_id)
                guesses_list.append(
                    {
                        "player_id": player.player_id,
                        "name": player.name,
                        "guess": entry["guess"] if entry else None,
                        "correct": bool(entry["correct"]) if entry else False,
                        "score": int(entry["score"]) if entry else 0,
                        "total_score": player.score,
                        "streak": player.streak,
                        "best_streak": player.best_streak,
                        "message": entry.get("message") if entry else None,
                    }
                )
            own_entry = revealed_round.guesses.get(player_id)
            last_round = {
                "round_number": revealed_index + 1,
                "person_id": revealed_person["id"],
                "name": revealed_person["name"],
                "surname": revealed_person["surname"],
                "full_name": revealed_person["full_name"],
                "description": revealed_person["description"],
                "image_url": revealed_person["image_url"],
                "special_case": revealed_person["special_case"],
                "answer": revealed_person["answer"],
                "person": revealed_person,
                "message": own_entry.get("message") if own_entry else None,
                "guesses": guesses_list,
            }

        if room.status == "playing" and current and not completed:
            current_person = self._sanitize_person(current.person)
        elif last_round is not None:
            current_person = last_round["person"]
        else:
            current_person = None

        player = room.players[player_id]
        own_guess_entry = current.guesses.get(player_id) if current else None

        return {
            "room_id": room.room_id,
            "status": room.status,
            "host_player_id": room.host_player_id,
            "match_number": room.match_number,
            "round_index": room.round_index,
            "round_number": min(room.round_index + 1, room.round_count),
            "round_count": room.round_count,
            "max_players": MAX_PLAYERS,
            "player_count": len(active_players),
            "spectator_count": len(room.spectators),
            "is_spectator": player.is_spectator,
            "can_start": len(active_players) >= 2,
            "awaiting_next_round": bool(room.status == "playing" and completed),
            "answered_count": len(current.guesses) if current else 0,
            "players": [
                {
                    "player_id": item.player_id,
                    "name": item.name,
                    "score": item.score,
                    "streak": item.streak,
                    "best_streak": item.best_streak,
                    "is_spectator": item.is_spectator,
                    "submitted": bool(current and item.player_id in current.guesses),
                }
                for item in room.players.values()
            ],
            "player": {
                "player_id": player.player_id,
                "name": player.name,
                "score": player.score,
                "streak": player.streak,
                "best_streak": player.best_streak,
                "is_spectator": player.is_spectator,
                "submitted": bool(current and player_id in current.guesses),
                "guess": own_guess_entry["guess"] if own_guess_entry else None,
            },
            "current_person": current_person,
            "last_round": last_round,
            "choices": ["linkedin", "interpol"],
        }

    def create_room(
        self,
        player_id: str,
        player_name: str,
        round_count: int = DEFAULT_ROUND_COUNT,
    ) -> LinkedinOrInterpolRoom:
        cleaned_id, cleaned_name = self._validate_player(player_id, player_name)
        if type(round_count) is not int or not 1 <= round_count <= MAX_ROUND_COUNT:
            raise ValueError(f"Le nombre de manches doit être compris entre 1 et {MAX_ROUND_COUNT}.")

        with self._lock:
            room_id = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
            while room_id in self.rooms:
                room_id = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))

            rounds_pool = self._build_rounds(round_count)
            for person in rounds_pool:
                self._mark_person_seen(str(person.get("id") or ""))
            rounds = [
                LinkedinOrInterpolRound(person)
                for person in rounds_pool
            ]
            room = LinkedinOrInterpolRoom(
                room_id=room_id,
                host_player_id=cleaned_id,
                round_count=round_count,
                players={cleaned_id: LinkedinOrInterpolRoomPlayer(cleaned_id, cleaned_name)},
                rounds=rounds,
            )
            self.rooms[room_id] = room
            return room

    def get_room(self, room_id: str, player_id: str) -> LinkedinOrInterpolRoom:
        with self._lock:
            room = self.rooms.get((room_id or "").strip().upper())
            if not room or player_id not in room.players:
                raise KeyError("Salon introuvable.")
            return room

    def join_room(
        self, room_id: str, player_id: str, player_name: str
    ) -> LinkedinOrInterpolRoom:
        cleaned_id, cleaned_name = self._validate_player(player_id, player_name)
        with self._lock:
            room = self.rooms.get((room_id or "").strip().upper())
            if not room:
                raise KeyError("Salon introuvable.")
            if cleaned_id in room.players:
                room.players[cleaned_id].name = cleaned_name
                return room
            if len(room.players) >= MAX_PLAYERS:
                raise ValueError("Ce salon est complet.")
            is_spectator = room.status != "lobby"
            room.players[cleaned_id] = LinkedinOrInterpolRoomPlayer(
                player_id=cleaned_id,
                name=cleaned_name,
                is_spectator=is_spectator,
            )
            return room

    def start_room(self, room_id: str, player_id: str) -> LinkedinOrInterpolRoom:
        with self._lock:
            room = self.get_room(room_id, player_id)
            if room.host_player_id != player_id:
                raise PermissionError("Seul l’hôte peut lancer la partie.")
            if room.status != "lobby":
                raise ValueError("Cette partie a déjà commencé.")
            if len(room.active_players) < 2:
                raise ValueError("Il faut au moins deux joueurs pour démarrer.")
            room.status = "playing"
            room.started_at = time.time()
            return room

    def guess_room(
        self, room_id: str, player_id: str, raw_guess: str
    ) -> Tuple[LinkedinOrInterpolRoom, Optional[Dict[str, Any]]]:
        with self._lock:
            room = self.get_room(room_id, player_id)
            if room.status != "playing":
                raise ValueError("La partie n’accepte pas de réponse maintenant.")
            player = room.players[player_id]
            if player.is_spectator:
                raise ValueError(
                    "Vous observez la partie en cours. Vous jouerez à la prochaine manche."
                )
            if room.is_round_complete():
                raise ValueError("Tous les joueurs ont répondu. L’hôte doit passer à la manche suivante.")
            current = room.current_round
            if player_id in current.guesses:
                raise ValueError("Votre réponse a déjà été validée pour cette manche.")

            guess, correct, message = _evaluate_person_guess(current.person, raw_guess)
            points = 1 if correct else 0
            if correct:
                player.score += points
                player.streak += 1
                player.best_streak = max(player.best_streak, player.streak)
            else:
                player.streak = 0

            revealed = self._reveal_person(current.person)
            round_entry = {
                "round_number": room.round_index + 1,
                "person_id": current.person["id"],
                "name": revealed["name"],
                "surname": revealed["surname"],
                "full_name": revealed["full_name"],
                "description": revealed["description"],
                "image_url": revealed["image_url"],
                "guess": guess,
                "answer": current.person["label"],
                "correct": correct,
                "score": points,
                "total_score": player.score,
                "streak": player.streak,
                "best_streak": player.best_streak,
                "message": message,
            }
            current.guesses[player_id] = round_entry
            player.results.append(round_entry)

            if not room.is_round_complete():
                return room, None

            if room.round_index >= room.round_count - 1:
                room.status = "finished"
                for active_player in room.active_players:
                    self._record_leaderboard_entry(
                        active_player.name,
                        active_player.best_streak,
                        score=active_player.score,
                        mode="multiplayer",
                    )

            state = self.room_state(room, player_id)
            return room, state["last_round"]

    def next_room(self, room_id: str, player_id: str) -> LinkedinOrInterpolRoom:
        with self._lock:
            room = self.get_room(room_id, player_id)
            if room.host_player_id != player_id:
                raise PermissionError("Seul l’hôte peut passer à la manche suivante.")
            if room.status != "playing":
                raise ValueError("La partie ne peut pas continuer.")
            if not room.is_round_complete():
                raise ValueError("Tous les joueurs doivent répondre avant de continuer.")
            if room.round_index >= room.round_count - 1:
                room.status = "finished"
                return room
            room.round_index += 1
            return room

    def restart_room(self, room_id: str, player_id: str) -> LinkedinOrInterpolRoom:
        with self._lock:
            room = self.get_room(room_id, player_id)
            if room.host_player_id != player_id:
                raise PermissionError("Seul l’hôte peut relancer une partie.")
            if room.status != "finished":
                raise ValueError("La partie en cours n’est pas encore terminée.")

            for player in room.players.values():
                player.is_spectator = False
                player.score = 0
                player.streak = 0
                player.best_streak = 0
                player.results.clear()

            if len(room.active_players) < 2:
                room.status = "lobby"
                room.round_index = 0
                room.match_number += 1
                room.stats_recorded = False
                new_rounds = self._build_rounds(room.round_count)
                for person in new_rounds:
                    self._mark_person_seen(str(person.get("id") or ""))
                room.rounds = [
                    LinkedinOrInterpolRound(person)
                    for person in new_rounds
                ]
                return room

            new_rounds = self._build_rounds(room.round_count)
            for person in new_rounds:
                self._mark_person_seen(str(person.get("id") or ""))
            room.rounds = [
                LinkedinOrInterpolRound(person)
                for person in new_rounds
            ]
            room.round_index = 0
            room.match_number += 1
            room.status = "playing"
            room.started_at = time.time()
            room.stats_recorded = False
            return room

    def list_rooms(self, player_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            rooms_list = []
            for room in self.rooms.values():
                if room.status == "finished" and (not player_id or player_id not in room.players):
                    continue
                host = room.players.get(room.host_player_id)
                rooms_list.append(
                    {
                        "room_id": room.room_id,
                        "status": room.status,
                        "round_count": room.round_count,
                        "round_number": min(room.round_index + 1, room.round_count),
                        "player_count": len(room.active_players),
                        "spectator_count": len(room.spectators),
                        "max_players": MAX_PLAYERS,
                        "host_name": host.name if host else "",
                        "is_member": bool(player_id and player_id in room.players),
                    }
                )
            return rooms_list

    # ------------------------------------------------------------------
    # API historique (rétrocompatibilité)
    # ------------------------------------------------------------------

    def create_game(self, player_id: str, rounds: int = 10, mode: str = "solo") -> Dict[str, Any]:
        player_id = (player_id or "anon").strip() or "anon"
        raw_mode = (mode or "solo").strip().lower()
        if raw_mode not in VALID_MODES:
            raise ValueError("Mode de jeu invalide.")
        normalized_mode = "multiplayer" if raw_mode == "multiplayer" else _normalize_solo_mode(raw_mode)

        chosen = (
            self._build_rounds(rounds)
            if normalized_mode != "solo-infinite"
            else self._build_rounds(rounds or DEFAULT_ROUND_COUNT)
        )
        for person in chosen:
            self._mark_person_seen(str(person.get("id") or ""))
        game_id = uuid.uuid4().hex
        game = {
            "game_id": game_id,
            "player_id": player_id,
            "mode": normalized_mode,
            "rounds": chosen,
            "status": "playing",
            "round_index": 0,
            "score": 0,
            "streak": 0,
            "best_streak": 0,
            "history": [],
        }
        with self._lock:
            self.games[game_id] = game
            return self.get_state(game_id, player_id)

    def get_state(self, game_id: str, player_id: str) -> Dict[str, Any]:
        with self._lock:
            game = self.games.get(game_id)
            if not game:
                raise KeyError("Partie introuvable.")
            if player_id and game["player_id"] != player_id:
                raise PermissionError("Cette partie ne vous appartient pas.")

            current = game["rounds"][game["round_index"]] if game["status"] == "playing" else None
            round_count = len(game["rounds"]) if game["mode"] != "solo-infinite" else None
            round_number = (
                game["round_index"] + 1
                if game["mode"] == "solo-infinite"
                else min(game["round_index"] + 1, len(game["rounds"]))
            )

            return {
                "game_id": game["game_id"],
                "player_id": game["player_id"],
                "mode": game["mode"],
                "status": game["status"],
                "round_index": game["round_index"],
                "round_number": round_number,
                "round_count": round_count,
                "score": game["score"],
                "streak": game["streak"],
                "best_streak": game["best_streak"],
                "current_person": self._sanitize_person(current) if current else None,
                "history": game["history"],
                "choices": ["linkedin", "interpol"],
            }

    def submit_guess(self, game_id: str, player_id: str, guess: str) -> Dict[str, Any]:
        with self._lock:
            game = self.games.get(game_id)
            if not game:
                raise KeyError("Partie introuvable.")
            if player_id and game["player_id"] != player_id:
                raise PermissionError("Cette partie ne vous appartient pas.")
            if game["status"] != "playing":
                raise ValueError("Cette partie est terminée.")

            current = game["rounds"][game["round_index"]]
            normalized_guess, correct, message = _evaluate_person_guess(current, guess)
            revealed = self._reveal_person(current)

            if correct:
                game["streak"] += 1
                game["best_streak"] = max(game["best_streak"], game["streak"])
                game["score"] = (
                    game["best_streak"] if game["mode"] == "solo-infinite" else game["score"] + 1
                )
            else:
                game["status"] = "finished"
                game["streak"] = 0
                if game["mode"] == "solo-infinite":
                    self._record_leaderboard_entry(game["player_id"], game["best_streak"])

            result = {
                "round_number": game["round_index"] + 1,
                "person_id": current["id"],
                "name": revealed["name"],
                "surname": revealed["surname"],
                "full_name": revealed["full_name"],
                "description": revealed["description"],
                "image_url": revealed["image_url"],
                "person": revealed,
                "guess": normalized_guess,
                "answer": current["label"],
                "correct": correct,
                "score": 1 if correct else 0,
                "total_score": game["score"],
                "streak": game["streak"],
                "best_streak": game["best_streak"],
                "message": message,
            }
            game["history"].append(result)

            if game["mode"] == "solo-infinite":
                if correct:
                    game["round_index"] += 1
                    if game["round_index"] >= len(game["rounds"]):
                        game["rounds"] = self._build_rounds(max(DEFAULT_ROUND_COUNT, len(game["rounds"])))
                        game["round_index"] = 0
                    state = self.get_state(game_id, player_id)
                    state["result"] = result
                    return state
                state = self.get_state(game_id, player_id)
                state["result"] = result
                return state

            if game["round_index"] >= len(game["rounds"]) - 1:
                game["status"] = "finished"
                self._record_leaderboard_entry(
                    game["player_id"],
                    game["best_streak"],
                    score=game["score"],
                    mode=game["mode"],
                )
                state = self.get_state(game_id, player_id)
                state["result"] = result
                return state

            game["round_index"] += 1
            state = self.get_state(game_id, player_id)
            state["result"] = result
            return state


linkedin_or_interpol_manager = LinkedinOrInterpolManager()
