import threading
import time
import uuid
from typing import Any, Dict


PENALTY_MS = 2000
TASKS = (
    {
        "prompt": "Un visiteur a oublié son parapluie. Où le déposer ?",
        "options": ("Objets trouvés", "Billetterie", "Atelier"),
        "answer": 0,
    },
    {
        "prompt": "Une salle est vide. Que faites-vous en premier ?",
        "options": ("Ouvrir les fenêtres", "Éteindre les lumières", "Déplacer les œuvres"),
        "answer": 1,
    },
    {
        "prompt": "Une étiquette est tombée près d'un tableau.",
        "options": ("La jeter", "La poser à l'entrée", "La remettre sous le bon tableau"),
        "answer": 2,
    },
    {
        "prompt": "Une chaise gêne le passage de sortie.",
        "options": ("La ranger contre le mur", "La laisser là", "La mettre devant l'œuvre"),
        "answer": 0,
    },
    {
        "prompt": "Un livre de l'espace lecture est resté ouvert.",
        "options": ("Le laisser au sol", "Le refermer et le ranger", "Le déposer dehors"),
        "answer": 1,
    },
    {
        "prompt": "Une fenêtre de la galerie est entrouverte.",
        "options": ("L'ouvrir davantage", "Y accrocher un panneau", "La fermer"),
        "answer": 2,
    },
    {
        "prompt": "Une poubelle de la salle est pleine.",
        "options": ("La vider dans le local prévu", "La cacher derrière une œuvre", "La laisser"),
        "answer": 0,
    },
    {
        "prompt": "Un panneau d'information a été déplacé.",
        "options": ("Le poser au sol", "Le remettre à son emplacement marqué", "Le sortir du musée"),
        "answer": 1,
    },
    {
        "prompt": "Une lampe d'exposition est restée allumée.",
        "options": ("La déplacer", "La débrancher en tirant le câble", "L'éteindre"),
        "answer": 2,
    },
    {
        "prompt": "Un visiteur a laissé un gobelet sur un banc.",
        "options": ("Le jeter dans la poubelle", "Le poser sur une vitrine", "Le laisser"),
        "answer": 0,
    },
    {
        "prompt": "Le registre de fermeture doit être complété.",
        "options": ("Le laisser vide", "Cocher la salle vérifiée", "L'emporter chez soi"),
        "answer": 1,
    },
    {
        "prompt": "La dernière salle est vérifiée. Que faites-vous ?",
        "options": ("Recommencer la tournée", "Quitter sans valider", "Valider la fermeture"),
        "answer": 2,
    },
)


class FermetureExpressManager:
    def __init__(self) -> None:
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _public_state(session: Dict[str, Any]) -> Dict[str, Any]:
        index = session["index"]
        finished = index >= len(TASKS)
        result: Dict[str, Any] = {
            "session_id": session["session_id"],
            "task_count": len(TASKS),
            "completed": index,
            "mistakes": session["mistakes"],
            "penalty_ms": session["mistakes"] * PENALTY_MS,
            "finished": finished,
        }
        if finished:
            result["elapsed_ms"] = session["elapsed_ms"]
        else:
            task = TASKS[index]
            result["task"] = {
                "prompt": task["prompt"],
                "options": task["options"],
            }
        return result

    def start(self, username: str) -> Dict[str, Any]:
        session = {
            "session_id": str(uuid.uuid4()),
            "username": username,
            "started_at": time.monotonic(),
            "index": 0,
            "mistakes": 0,
            "elapsed_ms": None,
        }
        with self._lock:
            self._sessions[username.casefold()] = session
        return self._public_state(session)

    def get(self, username: str, session_id: str) -> Dict[str, Any]:
        with self._lock:
            session = self._sessions.get(username.casefold())
            if session is None or session["session_id"] != session_id:
                raise KeyError("Partie introuvable ou expirée.")
            return self._public_state(session)

    def submit(self, username: str, session_id: str, answer: int) -> Dict[str, Any]:
        with self._lock:
            session = self._sessions.get(username.casefold())
            if session is None or session["session_id"] != session_id:
                raise KeyError("Partie introuvable ou expirée.")
            if session["index"] >= len(TASKS):
                return self._public_state(session)

            task = TASKS[session["index"]]
            if answer != task["answer"]:
                session["mistakes"] += 1
            session["index"] += 1
            if session["index"] == len(TASKS):
                session["elapsed_ms"] = max(
                    1,
                    round((time.monotonic() - session["started_at"]) * 1000)
                    + session["mistakes"] * PENALTY_MS,
                )
            return self._public_state(session)


fermeture_express_manager = FermetureExpressManager()
