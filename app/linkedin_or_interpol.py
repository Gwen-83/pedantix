import json
import random
import uuid
from pathlib import Path
from typing import Any, Dict, List

DATA_PATH = Path(__file__).resolve().parent / "data" / "linkedin_or_interpol" / "metadata.json"
VALID_MODES = {"solo", "multiplayer", "solo-infinite"}


class LinkedinOrInterpolManager:
    def __init__(self) -> None:
        self.dataset: List[Dict[str, Any]] = self._load_dataset()
        self.games: Dict[str, Dict[str, Any]] = {}
        self.leaderboard: List[Dict[str, Any]] = []

    @staticmethod
    def _load_dataset() -> List[Dict[str, Any]]:
        if not DATA_PATH.exists():
            return []
        with DATA_PATH.open(encoding="utf-8") as handle:
            try:
                data = json.load(handle)
            except json.JSONDecodeError:
                return []
        return data if isinstance(data, list) else []

    @staticmethod
    def _image_url(image_path: str) -> str:
        return f"/api/linkedin-or-interpol/image/{Path(image_path).name}"

    def _sanitize_person(self, person: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": person["id"],
            "name": person.get("name", ""),
            "surname": person.get("surname", ""),
            "description": person.get("description", ""),
            "source_url": person.get("source_url"),
            "special_case": person.get("special_case"),
            "image_url": self._image_url(person["image_path"]),
        }

    def _build_rounds(self, rounds: int = 10) -> List[Dict[str, Any]]:
        if not self.dataset:
            raise ValueError("Le jeu LinkedIn ou Interpol n’a pas de données disponibles.")
        sample_size = max(1, min(int(rounds or 10), len(self.dataset)))
        return random.sample(self.dataset, k=sample_size)

    def _record_leaderboard_entry(self, player_id: str, best_streak: int) -> None:
        player_name = (player_id or "guest").strip() or "guest"
        normalized = player_name.casefold()
        best_streak = max(0, int(best_streak))

        existing = next((entry for entry in self.leaderboard if entry["player_id"].casefold() == normalized), None)
        if existing is None:
            self.leaderboard.append({"player_id": player_name, "best_streak": best_streak})
        else:
            existing["best_streak"] = max(existing["best_streak"], best_streak)

        self.leaderboard = sorted(
            self.leaderboard,
            key=lambda entry: (-int(entry["best_streak"]), entry["player_id"].lower()),
        )[:10]

    def get_leaderboard(self, limit: int = 10) -> List[Dict[str, Any]]:
        items = sorted(
            self.leaderboard,
            key=lambda entry: (-int(entry["best_streak"]), entry["player_id"].lower()),
        )[: max(1, min(int(limit), 20))]
        return [
            {"rank": index + 1, "player_id": entry["player_id"], "best_streak": entry["best_streak"]}
            for index, entry in enumerate(items)
        ]

    def create_game(self, player_id: str, rounds: int = 10, mode: str = "solo") -> Dict[str, Any]:
        player_id = (player_id or "anon").strip() or "anon"
        mode = (mode or "solo").strip().lower()
        if mode not in VALID_MODES:
            raise ValueError("Mode de jeu invalide.")

        chosen = self._build_rounds(rounds) if mode != "solo-infinite" else self._build_rounds(rounds or 10)
        game_id = uuid.uuid4().hex
        game = {
            "game_id": game_id,
            "player_id": player_id,
            "mode": mode,
            "rounds": chosen,
            "status": "playing",
            "round_index": 0,
            "score": 0,
            "streak": 0,
            "best_streak": 0,
            "history": [],
        }
        self.games[game_id] = game
        return self.get_state(game_id, player_id)

    def get_state(self, game_id: str, player_id: str) -> Dict[str, Any]:
        game = self.games.get(game_id)
        if not game:
            raise KeyError("Partie introuvable.")
        if player_id and game["player_id"] != player_id:
            raise PermissionError("Cette partie ne vous appartient pas.")

        current = game["rounds"][game["round_index"]] if game["status"] == "playing" else None
        round_count = len(game["rounds"]) if game["mode"] != "solo-infinite" else None
        round_number = game["round_index"] + 1 if game["mode"] == "solo-infinite" else min(game["round_index"] + 1, len(game["rounds"]))

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
        game = self.games.get(game_id)
        if not game:
            raise KeyError("Partie introuvable.")
        if player_id and game["player_id"] != player_id:
            raise PermissionError("Cette partie ne vous appartient pas.")
        if game["status"] != "playing":
            raise ValueError("Cette partie est terminée.")

        guess = guess.strip().lower()
        if guess not in {"linkedin", "interpol"}:
            raise ValueError("Choix invalide. Répondez par linkedin ou interpol.")

        current = game["rounds"][game["round_index"]]
        is_friend_case = current.get("special_case") == "friend"
        if is_friend_case:
            correct = guess in {"linkedin", "interpol"}
            if guess == "linkedin":
                message = "Oui, mais bientôt ça sera interpol."
            else:
                message = "C’était linkedin, mais interpol accepté, c’est un malade."
        else:
            correct = guess == current["label"]
            message = None

        if correct:
            game["streak"] += 1
            game["best_streak"] = max(game["best_streak"], game["streak"])
            game["score"] = game["best_streak"] if game["mode"] == "solo-infinite" else game["score"] + 1
        else:
            game["status"] = "finished"
            game["streak"] = 0
            if game["mode"] == "solo-infinite":
                self._record_leaderboard_entry(game["player_id"], game["best_streak"])

        result = {
            "round_number": game["round_index"] + 1,
            "person_id": current["id"],
            "guess": guess,
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
                    game["rounds"] = self._build_rounds(max(10, len(game["rounds"])))
                    game["round_index"] = 0
                state = self.get_state(game_id, player_id)
                state["result"] = result
                return state
            state = self.get_state(game_id, player_id)
            state["result"] = result
            return state

        if game["round_index"] >= len(game["rounds"]) - 1:
            game["status"] = "finished"
            state = self.get_state(game_id, player_id)
            state["result"] = result
            return state

        game["round_index"] += 1
        state = self.get_state(game_id, player_id)
        state["result"] = result
        return state


linkedin_or_interpol_manager = LinkedinOrInterpolManager()
