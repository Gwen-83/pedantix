"""Free-answer rarity game inspired by the social format of short trivia dives."""

import json
import random
import time
import unicodedata
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Dict, List, Optional, Tuple

ROUND_COUNT = 7
ROUND_SECONDS = 25
MAX_PLAYERS = 8
ROOM_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
PROMPTS_PATH = Path(__file__).resolve().parent / "data" / "plongee_prompts.json"


def normalize_answer(answer: str) -> str:
    decomposed = unicodedata.normalize("NFKD", answer.casefold())
    unaccented = "".join(char for char in decomposed if not unicodedata.combining(char))
    normalized = "".join(char if char.isalnum() else " " for char in unaccented)
    return " ".join(normalized.split())


def _load_prompts() -> List[Dict[str, Any]]:
    with PROMPTS_PATH.open(encoding="utf-8") as prompts_file:
        prompts = json.load(prompts_file)
    if not isinstance(prompts, list) or len(prompts) < ROUND_COUNT:
        raise ValueError("Le jeu de données de Plongée doit contenir au moins sept questions.")
    prompt_ids = set()
    for prompt in prompts:
        if not isinstance(prompt, dict) or not prompt.get("id") or not prompt.get("prompt"):
            raise ValueError("Chaque question de Plongée doit avoir un identifiant et un énoncé.")
        if prompt["id"] in prompt_ids:
            raise ValueError(f"Identifiant de question en double : {prompt['id']}.")
        prompt_ids.add(prompt["id"])
        answers = prompt.get("answers")
        if not isinstance(answers, list) or not answers:
            raise ValueError(f"La question {prompt['id']} doit proposer des réponses.")
        answer_count = sum(isinstance(answer, str) for answer in answers)
        answer_index = 0
        normalized_answers = []
        for answer in answers:
            if isinstance(answer, str):
                normalized_answers.append({
                    "answer": answer,
                    "score": round(
                        25 + 70 * answer_index / max(1, answer_count - 1)
                    ),
                })
                answer_index += 1
            else:
                normalized_answers.append(answer)
        prompt["answers"] = normalized_answers
    return prompts


PROMPTS = _load_prompts()


def _build_answer_index(prompt: Dict[str, Any]) -> Dict[str, Tuple[str, int]]:
    canonical_answers: Dict[str, Tuple[str, int]] = {}
    for item in prompt["answers"]:
        canonical = normalize_answer(item["answer"])
        score = int(item["score"])
        if not canonical or not 0 <= score <= 100:
            raise ValueError(f"Barème invalide pour la question {prompt['id']}.")
        canonical_answers[canonical] = (canonical, score)

    answer_index = canonical_answers.copy()
    for item in prompt["answers"]:
        canonical = normalize_answer(item["answer"])
        score = int(item["score"])
        aliases = [*item.get("aliases", []), *_simple_plural_variants(item["answer"])]
        for variant in aliases:
            normalized = normalize_answer(variant)
            if normalized and normalized not in answer_index:
                answer_index[normalized] = (canonical, score)
    return answer_index


def _simple_plural_variants(answer: str) -> List[str]:
    words = normalize_answer(answer).split()
    if not words:
        return []

    def pluralize(word: str) -> str:
        if len(word) < 3 or word.endswith(("s", "x", "z")):
            return word
        if word.endswith("al"):
            return f"{word[:-2]}aux"
        if word.endswith("eau"):
            return f"{word}x"
        return f"{word}s"

    variants = set()
    plural_first = pluralize(words[0])
    plural_last = pluralize(words[-1])
    if plural_last != words[-1]:
        variants.add(" ".join([*words[:-1], plural_last]))
    if len(words) > 1 and plural_first != words[0]:
        variants.add(" ".join([plural_first, *words[1:]]))
        if plural_last != words[-1]:
            variants.add(" ".join([plural_first, *words[1:-1], plural_last]))
    return sorted(variants)


@dataclass
class PlongeePlayer:
    player_id: str
    name: str
    score: int = 0
    results: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class PlongeeGame:
    game_id: str
    player: PlongeePlayer
    prompts: List[Dict[str, Any]]
    answer_indexes: List[Dict[str, Tuple[str, int]]]
    created_at: float
    round_index: int = 0
    deadline: float = 0
    status: str = "playing"
    stats_recorded: bool = False


@dataclass
class PlongeeRoom:
    room_id: str
    host_player_id: str
    players: Dict[str, PlongeePlayer]
    prompts: List[Dict[str, Any]]
    answer_indexes: List[Dict[str, Tuple[str, int]]]
    created_at: float
    round_index: int = 0
    deadline: float = 0
    status: str = "lobby"
    answers: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    last_round: Optional[Dict[str, Any]] = None
    stats_recorded: bool = False


class PlongeeManager:
    def __init__(
        self,
        prompts: Optional[List[Dict[str, Any]]] = None,
        clock: Callable[[], float] = time.time,
        rng: Optional[random.Random] = None,
    ):
        self.prompts = prompts or PROMPTS
        self.answer_indexes = [_build_answer_index(prompt) for prompt in self.prompts]
        self.clock = clock
        self.rng = rng or random.Random()
        self.solo_games: Dict[str, PlongeeGame] = {}
        self.rooms: Dict[str, PlongeeRoom] = {}
        self._solo_prompt_bags: Dict[str, List[int]] = {}
        self._last_solo_prompt_indexes: Dict[str, set[int]] = {}
        self._lock = RLock()

    def _validate_player(self, player_id: str, player_name: str) -> Tuple[str, str]:
        clean_id = player_id.strip()
        clean_name = player_name.strip()
        if not clean_id or len(clean_id) > 100:
            raise ValueError("Identifiant de joueur invalide.")
        if not clean_name or len(clean_name) > 24:
            raise ValueError("Le pseudo doit contenir de 1 à 24 caractères.")
        return clean_id, clean_name

    def _new_round_set(
        self, player_id: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Tuple[str, int]]]]:
        with self._lock:
            if player_id is None:
                indexes = self.rng.sample(range(len(self.prompts)), k=ROUND_COUNT)
            else:
                bag = self._solo_prompt_bags.setdefault(player_id, [])
                if len(bag) < ROUND_COUNT:
                    excluded = self._last_solo_prompt_indexes.get(player_id, set()) | set(bag)
                    refill = [
                        index for index in range(len(self.prompts))
                        if index not in excluded
                    ]
                    if len(bag) + len(refill) < ROUND_COUNT:
                        refill = [
                            index for index in range(len(self.prompts))
                            if index not in bag
                        ]
                    self.rng.shuffle(refill)
                    bag.extend(refill)
                indexes = bag[:ROUND_COUNT]
                del bag[:ROUND_COUNT]
                self._last_solo_prompt_indexes[player_id] = set(indexes)
        return [self.prompts[index] for index in indexes], [self.answer_indexes[index] for index in indexes]

    def create_solo(self, player_id: str, player_name: str) -> PlongeeGame:
        clean_id, clean_name = self._validate_player(player_id, player_name)
        prompts, indexes = self._new_round_set(clean_id)
        now = self.clock()
        game = PlongeeGame(
            game_id=uuid.uuid4().hex,
            player=PlongeePlayer(clean_id, clean_name),
            prompts=prompts,
            answer_indexes=indexes,
            created_at=now,
            deadline=now + ROUND_SECONDS,
        )
        with self._lock:
            self.solo_games[game.game_id] = game
        return game

    def get_solo(self, game_id: str, player_id: str) -> PlongeeGame:
        with self._lock:
            game = self.solo_games.get(game_id)
            if not game or game.player.player_id != player_id:
                raise KeyError("Partie solo introuvable.")
            self._expire_solo_round(game)
            return game

    def _score(self, answer: str, answer_index: Dict[str, Tuple[str, int]]) -> Tuple[str, int, bool]:
        normalized = normalize_answer(answer)
        if not normalized:
            raise ValueError("Saisissez une réponse avant de valider.")
        if len(normalized) > 80:
            raise ValueError("La réponse ne peut pas dépasser 80 caractères.")
        benchmark = answer_index.get(normalized)
        if benchmark is None:
            raise ValueError(
                "Réponse hors sujet ou absente du barème. Proposez une réponse qui correspond à la question."
            )
        return benchmark[0], benchmark[1], True

    def _expire_solo_round(self, game: PlongeeGame) -> None:
        if (
            game.status == "playing"
            and len(game.player.results) <= game.round_index
            and self.clock() >= game.deadline
        ):
            game.player.results.append({
                "round_number": game.round_index + 1,
                "answer": None,
                "score": 0,
                "known_answer": False,
                "timed_out": True,
            })
            if game.round_index == ROUND_COUNT - 1:
                game.status = "finished"
            else:
                game.round_index += 1
                game.deadline = self.clock() + ROUND_SECONDS

    def guess_solo(self, game_id: str, player_id: str, answer: str) -> Tuple[PlongeeGame, Dict[str, Any]]:
        with self._lock:
            game = self.get_solo(game_id, player_id)
            if game.status != "playing":
                raise ValueError("Cette partie est terminée.")
            if len(game.player.results) > game.round_index:
                raise ValueError("Vous avez déjà répondu à cette manche.")
            canonical, score, known = self._score(answer, game.answer_indexes[game.round_index])
            result = {
                "round_number": game.round_index + 1,
                "answer": answer.strip(),
                "canonical_answer": canonical,
                "score": score,
                "known_answer": known,
                "timed_out": False,
            }
            game.player.score += score
            game.player.results.append(result)
            return game, result

    def next_solo(self, game_id: str, player_id: str) -> PlongeeGame:
        with self._lock:
            game = self.get_solo(game_id, player_id)
            if game.status == "finished":
                raise ValueError("Cette partie est terminée.")
            if len(game.player.results) <= game.round_index:
                raise ValueError("Répondez avant de passer à la manche suivante.")
            if game.round_index == ROUND_COUNT - 1:
                game.status = "finished"
                return game
            game.round_index += 1
            game.deadline = self.clock() + ROUND_SECONDS
            return game

    def create_room(self, player_id: str, player_name: str) -> PlongeeRoom:
        clean_id, clean_name = self._validate_player(player_id, player_name)
        with self._lock:
            while True:
                room_id = "".join(self.rng.choice(ROOM_CODE_ALPHABET) for _ in range(5))
                if room_id not in self.rooms:
                    break
            prompts, indexes = self._new_round_set(clean_id)
            room = PlongeeRoom(
                room_id=room_id,
                host_player_id=clean_id,
                players={clean_id: PlongeePlayer(clean_id, clean_name)},
                prompts=prompts,
                answer_indexes=indexes,
                created_at=self.clock(),
            )
            self.rooms[room_id] = room
            return room

    def get_room(self, room_id: str, player_id: str) -> PlongeeRoom:
        with self._lock:
            room = self.rooms.get(room_id.strip().upper())
            if not room or player_id not in room.players:
                raise KeyError("Salon introuvable.")
            if room.status == "playing" and self.clock() >= room.deadline:
                self._finish_room_round(room)
            return room

    def join_room(self, room_id: str, player_id: str, player_name: str) -> PlongeeRoom:
        clean_id, clean_name = self._validate_player(player_id, player_name)
        with self._lock:
            room = self.rooms.get(room_id.strip().upper())
            if not room:
                raise KeyError("Salon introuvable.")
            if clean_id in room.players:
                return room
            if room.status != "lobby":
                raise ValueError("Cette partie a déjà commencé.")
            if len(room.players) >= MAX_PLAYERS:
                raise ValueError("Ce salon est complet.")
            room.players[clean_id] = PlongeePlayer(clean_id, clean_name)
            return room

    def start_room(self, room_id: str, player_id: str) -> PlongeeRoom:
        with self._lock:
            room = self.get_room(room_id, player_id)
            if room.host_player_id != player_id:
                raise PermissionError("Seul l’hôte peut démarrer le salon.")
            if room.status != "lobby":
                raise ValueError("Cette partie a déjà commencé.")
            if len(room.players) < 2:
                raise ValueError("Il faut au moins deux joueurs pour démarrer.")
            room.status = "playing"
            room.deadline = self.clock() + ROUND_SECONDS
            return room

    def guess_room(self, room_id: str, player_id: str, answer: str) -> PlongeeRoom:
        with self._lock:
            room = self.get_room(room_id, player_id)
            if room.status != "playing":
                raise ValueError("Cette partie n’accepte pas de réponse maintenant.")
            if player_id in room.answers:
                raise ValueError("Vous avez déjà répondu à cette manche.")
            canonical, score, known = self._score(answer, room.answer_indexes[room.round_index])
            room.answers[player_id] = {
                "answer": answer.strip(),
                "canonical_answer": canonical,
                "base_score": score,
                "known_answer": known,
            }
            if len(room.answers) == len(room.players):
                self._finish_room_round(room)
            return room

    def next_room(self, room_id: str, player_id: str) -> PlongeeRoom:
        with self._lock:
            room = self.get_room(room_id, player_id)
            if room.host_player_id != player_id:
                raise PermissionError("Seul l’hôte peut passer à la manche suivante.")
            if room.status != "playing" or not room.last_round:
                raise ValueError("La manche actuelle doit être terminée.")
            if room.round_index == ROUND_COUNT - 1:
                room.status = "finished"
                return room
            room.round_index += 1
            room.answers = {}
            room.last_round = None
            room.deadline = self.clock() + ROUND_SECONDS
            return room

    def list_rooms(self, player_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                {
                    "room_id": room.room_id,
                    "status": room.status,
                    "player_count": len(room.players),
                    "is_member": player_id in room.players if player_id else False,
                }
                for room in self.rooms.values()
                if room.status != "finished"
                and (room.status == "lobby" or (player_id and player_id in room.players))
            ]

    def _finish_room_round(self, room: PlongeeRoom) -> None:
        if room.last_round is not None:
            return
        answer_counts: Dict[str, int] = {}
        for answer in room.answers.values():
            key = answer["canonical_answer"]
            answer_counts[key] = answer_counts.get(key, 0) + 1
        round_results = []
        for player in room.players.values():
            answer = room.answers.get(player.player_id)
            score = 0
            if answer:
                score = max(0, answer["base_score"] - 15 * (answer_counts[answer["canonical_answer"]] - 1))
            result = {
                "round_number": room.round_index + 1,
                "answer": answer["answer"] if answer else None,
                "canonical_answer": answer["canonical_answer"] if answer else None,
                "score": score,
                "known_answer": answer["known_answer"] if answer else False,
                "timed_out": answer is None,
            }
            player.score += score
            player.results.append(result)
            round_results.append({
                "player_id": player.player_id,
                "name": player.name,
                "answer": result["answer"],
                "score": score,
                "known_answer": result["known_answer"],
                "timed_out": result["timed_out"],
            })
        room.last_round = {
            "round_number": room.round_index + 1,
            "prompt": room.prompts[room.round_index]["prompt"],
            "results": round_results,
        }

    def solo_state(self, game: PlongeeGame) -> Dict[str, Any]:
        current = game.prompts[game.round_index] if game.status == "playing" else None
        return {
            "game_id": game.game_id,
            "status": game.status,
            "round_number": min(game.round_index + 1, ROUND_COUNT),
            "round_count": ROUND_COUNT,
            "time_left": max(0, int(game.deadline - self.clock() + 0.999)) if current else 0,
            "prompt": current["prompt"] if current else None,
            "score": game.player.score,
            "result": game.player.results[-1] if game.player.results else None,
            "results": game.player.results,
        }

    def room_state(self, room: PlongeeRoom, player_id: str) -> Dict[str, Any]:
        current = room.prompts[room.round_index] if room.status == "playing" else None
        return {
            "room_id": room.room_id,
            "status": room.status,
            "host_player_id": room.host_player_id,
            "player_id": player_id,
            "round_number": min(room.round_index + 1, ROUND_COUNT),
            "round_count": ROUND_COUNT,
            "time_left": max(0, int(room.deadline - self.clock() + 0.999)) if current else 0,
            "prompt": current["prompt"] if current else None,
            "players": [
                {
                    "player_id": player.player_id,
                    "name": player.name,
                    "score": player.score,
                    "has_answered": player.player_id in room.answers,
                }
                for player in room.players.values()
            ],
            "has_answered": player_id in room.answers,
            "answer_count": len(room.answers),
            "last_round": room.last_round,
            "score": room.players[player_id].score,
            "results": room.players[player_id].results,
        }


plongee_manager = PlongeeManager()
