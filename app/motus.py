import random
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from app.nlp import FRENCH_DICTIONARY, normalize_text

MOTUS_WORD_LENGTH = 6
MOTUS_MAX_ATTEMPTS = 6
MOTUS_DIFFICULTIES = {"facile": 8, "moyen": 6, "difficile": 4}

# Keep answer selection to familiar words; the larger dictionary is used for guesses.
MOTUS_ANSWERS = frozenset(
    normalize_text(word)
    for word in (
        "abattu", "abimer", "aborde", "abrite", "abuser", "acteur", "active", "actuel",
        "ajoute", "alerte", "aligné", "allume", "amener", "amitié", "ancien", "animal",
        "annule", "apport", "argent", "arrive", "assure", "attaque", "attend", "aucune",
        "avance", "avaler", "baisser", "balade", "banque", "barrer", "bassin", "battre",
        "beauté", "besoin", "blague", "blanch", "blonde", "bonheur", "boucle", "bouger",
        "bourse", "bouton", "bureau", "brille", "briser", "bronze", "budget", "cabine",
        "cacher", "calmer", "camion", "canard", "capote", "captif", "caract", "carton",
        "centre", "cerise", "chaise", "chasse", "chante", "charge", "charme", "chasse",
        "chemin", "chemise", "cheval", "chiffre", "choisi", "chose", "ciment", "ciseau",
        "claire", "client", "climat", "coffre", "combat", "comble", "comité", "compte",
        "conduit", "confié", "congés", "conseil", "contact", "contre", "copain", "corail",
        "cordon", "corps", "couleur", "coupure", "courant", "course", "cousin", "crayon",
        "crédit", "croire", "cuivre", "danger", "danser", "débuté", "défaut", "défini",
        "délice", "demain", "demande", "dernier", "dessin", "devant", "devoir", "diffus",
        "dimanche", "direct", "disque", "docteur", "donnée", "dormir", "douane", "douter",
        "draper", "durant", "écrire", "effort", "église", "équipe", "espace", "espoir",
        "essais", "étable", "étaler", "étendu", "étoile", "étrange", "étroit", "étude",
        "examen", "exemple", "facile", "faible", "famille", "farine", "faute", "février",
        "fichier", "figure", "fille", "filmer", "flamme", "fleur", "flemme", "foyer",
        "france", "frappe", "frères", "fromage", "fuyant", "garage", "garder", "gâteau",
        "gauche", "géant", "génial", "génome", "geste", "glacer", "gloire", "gouver",
        "grandir", "grande", "groupe", "habile", "hasard", "herbe", "histoire", "hiver",
        "hommes", "honneur", "image", "immense", "indice", "instant", "intérêt", "jardin",
        "jaune", "joindre", "journal", "joueur", "justice", "laisser", "lampe", "langue",
        "large", "lecture", "légume", "liberté", "limite", "liquide", "livrer", "maison",
        "maître", "malade", "manège", "manger", "manque", "marche", "marque", "masque",
        "matière", "médias", "membre", "message", "méthode", "minute", "miroir", "modèle",
        "moment", "monde", "monter", "moteur", "musique", "nature", "navire", "niveau",
        "nombre", "normal", "nuance", "objet", "obtenir", "offrir", "orange", "ordonner",
        "organe", "ouvert", "papier", "parfum", "parler", "partie", "passer", "patient",
        "patron", "pauvre", "paysan", "peindre", "penser", "perdre", "person", "phrase",
        "placer", "plaine", "plante", "plaque", "pluie", "poésie", "poivre", "police",
        "porter", "position", "poudre", "pouvoir", "premier", "preuve", "prison", "produit",
        "projet", "propre", "public", "quartier", "question", "ranger", "rapide", "rapport",
        "rayons", "réalité", "recevoir", "récolte", "reflet", "regard", "régime", "règles",
        "relation", "relever", "remède", "rendre", "réponse", "retour", "réunion", "réussir",
        "revient", "riches", "rideau", "rivière", "robot", "roman", "rouge", "saison",
        "salade", "savoir", "science", "secret", "sécurité", "semaine", "simple", "sourire",
        "spectacle", "station", "stocker", "surface", "tableau", "tâcher", "talent", "tenter",
        "terrain", "théâtre", "ticket", "tirage", "tomber", "tourner", "travail", "travers",
        "trésor", "trouver", "unique", "usager", "valeur", "vendre", "venise", "verger",
        "vérité", "village", "visage", "visite", "vitesse", "vivant", "voyage",
    )
    if len(normalize_text(word)) == MOTUS_WORD_LENGTH
    and re.fullmatch(r"[a-z]+", normalize_text(word))
)


def evaluate_guess(guess: str, target: str) -> List[str]:
    """Return Wordle-style letter marks, accounting for repeated letters."""
    feedback = ["absent"] * len(target)
    remaining: Dict[str, int] = {}

    for index, (letter, answer_letter) in enumerate(zip(guess, target)):
        if letter == answer_letter:
            feedback[index] = "correct"
        else:
            remaining[answer_letter] = remaining.get(answer_letter, 0) + 1

    for index, letter in enumerate(guess):
        if feedback[index] == "correct":
            continue
        if remaining.get(letter, 0):
            feedback[index] = "present"
            remaining[letter] -= 1

    return feedback


@dataclass
class MotusPlayer:
    player_id: str
    name: str
    guesses: List[Dict[str, Any]] = field(default_factory=list)
    solved: bool = False
    finished: bool = False
    score: int = 0
    connected: bool = True

    def submit(
        self,
        raw_guess: str,
        target: str,
        dictionary: set[str],
        max_attempts: int = MOTUS_MAX_ATTEMPTS,
    ) -> Dict[str, Any]:
        guess = normalize_text(raw_guess.strip())
        if not re.fullmatch(r"[a-z]+", guess):
            raise ValueError("Utilisez uniquement des lettres.")
        if len(guess) != len(target):
            raise ValueError(f"Le mot doit contenir {len(target)} lettres.")
        if guess[0] != target[0]:
            raise ValueError(f"Le mot doit commencer par la lettre « {target[0].upper()} ».")
        if guess not in dictionary:
            raise ValueError("Ce mot n'est pas reconnu dans le dictionnaire français.")
        if self.finished:
            raise ValueError("Vous avez déjà terminé cette partie.")
        if guess in {item["word"] for item in self.guesses}:
            raise ValueError("Vous avez déjà proposé ce mot.")

        feedback = evaluate_guess(guess, target)
        self.guesses.append({"word": guess, "feedback": feedback})
        self.solved = guess == target
        self.finished = self.solved or len(self.guesses) >= max_attempts
        if self.solved:
            self.score = (max_attempts - len(self.guesses) + 1) * 100

        return {
            "word": guess,
            "feedback": feedback,
            "solved": self.solved,
            "finished": self.finished,
            "score": self.score,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "player_id": self.player_id,
            "name": self.name,
            "guesses": self.guesses,
            "solved": self.solved,
            "finished": self.finished,
            "score": self.score,
            "attempts": len(self.guesses),
            "connected": self.connected,
        }


@dataclass
class MotusGame:
    game_id: str
    target: str
    player: MotusPlayer
    difficulty: str = "moyen"
    status: str = "playing"
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "game_id": self.game_id,
            "status": self.status,
            "word_length": len(self.target),
            "max_attempts": MOTUS_DIFFICULTIES[self.difficulty],
            "difficulty": self.difficulty,
            "first_letter": self.target[0].upper(),
            "target": self.target.upper() if self.player.finished else None,
            "player": self.player.to_dict(),
        }


@dataclass
class MotusRoom:
    room_id: str
    target: str
    host_player_id: str
    difficulty: str = "moyen"
    players: Dict[str, MotusPlayer] = field(default_factory=dict)
    status: str = "lobby"
    created_at: float = field(default_factory=time.time)

    def to_dict(self, player_id: str) -> Dict[str, Any]:
        player = self.players[player_id]
        players = []
        for item in self.players.values():
            player_state = item.to_dict()
            if item.player_id != player_id:
                player_state["guesses"] = []
            players.append(player_state)
        return {
            "room_id": self.room_id,
            "status": self.status,
            "host_player_id": self.host_player_id,
            "word_length": len(self.target),
            "max_attempts": MOTUS_DIFFICULTIES[self.difficulty],
            "difficulty": self.difficulty,
            "first_letter": self.target[0].upper(),
            "target": self.target.upper() if self.status == "finished" else None,
            "player": player.to_dict(),
            "players": players,
            "can_start": self.status == "lobby" and len(self.players) >= 2,
        }


class MotusManager:
    def __init__(
        self,
        words: Optional[Iterable[str]] = None,
        answers: Optional[Iterable[str]] = None,
    ):
        self.dictionary = {
            normalize_text(word)
            for word in (words if words is not None else FRENCH_DICTIONARY)
            if re.fullmatch(r"[a-z]{6}", normalize_text(word))
        }
        self.answers = sorted(
            {
                normalize_text(word)
                for word in (answers if answers is not None else MOTUS_ANSWERS)
                if normalize_text(word) in self.dictionary
            }
        )
        if not self.answers:
            raise ValueError("La liste de réponses Motus ne contient aucun mot reconnu.")
        self.solo_games: Dict[str, MotusGame] = {}
        self.rooms: Dict[str, MotusRoom] = {}
        self._lock = threading.RLock()

    def _pick_target(self) -> str:
        return random.choice(self.answers)

    @staticmethod
    def _validate_difficulty(difficulty: str) -> str:
        if difficulty not in MOTUS_DIFFICULTIES:
            raise ValueError("Difficulté invalide. Choisissez facile, moyen ou difficile.")
        return difficulty

    def create_solo(
        self, player_id: str, player_name: str, difficulty: str = "moyen"
    ) -> MotusGame:
        with self._lock:
            difficulty = self._validate_difficulty(difficulty)
            player = MotusPlayer(player_id=player_id, name=player_name)
            game = MotusGame(
                game_id=uuid.uuid4().hex,
                target=self._pick_target(),
                player=player,
                difficulty=difficulty,
            )
            self.solo_games[game.game_id] = game
            return game

    def get_solo(self, game_id: str, player_id: str) -> MotusGame:
        with self._lock:
            game = self.solo_games.get(game_id)
            if not game or game.player.player_id != player_id:
                raise KeyError("Cette partie solo est introuvable.")
            return game

    def guess_solo(self, game_id: str, player_id: str, guess: str) -> tuple[MotusGame, Dict[str, Any]]:
        with self._lock:
            game = self.get_solo(game_id, player_id)
            result = game.player.submit(
                guess,
                game.target,
                self.dictionary,
                MOTUS_DIFFICULTIES[game.difficulty],
            )
            if game.player.finished:
                game.status = "finished"
            return game, result

    def create_room(
        self, player_id: str, player_name: str, difficulty: str = "moyen"
    ) -> MotusRoom:
        with self._lock:
            difficulty = self._validate_difficulty(difficulty)
            room_id = uuid.uuid4().hex[:6].upper()
            while room_id in self.rooms:
                room_id = uuid.uuid4().hex[:6].upper()
            room = MotusRoom(
                room_id=room_id,
                target=self._pick_target(),
                host_player_id=player_id,
                difficulty=difficulty,
            )
            room.players[player_id] = MotusPlayer(player_id=player_id, name=player_name)
            self.rooms[room_id] = room
            return room

    def join_room(self, room_id: str, player_id: str, player_name: str) -> MotusRoom:
        with self._lock:
            room = self.rooms.get(room_id.upper())
            if not room:
                raise KeyError("Salon introuvable ou expiré.")
            if player_id in room.players:
                room.players[player_id].connected = True
                room.players[player_id].name = player_name
                return room
            if room.status != "lobby":
                raise ValueError("Cette partie a déjà commencé. Seuls les joueurs déjà inscrits peuvent revenir.")
            if len(room.players) >= 8:
                raise ValueError("Ce salon est complet (8 joueurs maximum).")
            room.players[player_id] = MotusPlayer(player_id=player_id, name=player_name)
            return room

    def get_room(self, room_id: str, player_id: str) -> MotusRoom:
        with self._lock:
            room = self.rooms.get(room_id.upper())
            if not room or player_id not in room.players:
                raise KeyError("Salon ou joueur introuvable.")
            return room

    def list_rooms(self, player_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                {
                    "room_id": room.room_id,
                    "status": room.status,
                    "player_count": len(room.players),
                    "host_name": room.players[room.host_player_id].name,
                    "difficulty": room.difficulty,
                    "is_member": player_id in room.players if player_id else False,
                }
                for room in self.rooms.values()
                if room.status != "finished"
            ]

    def start_room(self, room_id: str, player_id: str) -> MotusRoom:
        with self._lock:
            room = self.get_room(room_id, player_id)
            if room.host_player_id != player_id:
                raise PermissionError("Seul l'hôte peut démarrer la partie.")
            if room.status != "lobby":
                raise ValueError("Cette partie a déjà démarré.")
            if len(room.players) < 2:
                raise ValueError("Il faut au moins deux joueurs pour démarrer.")
            room.status = "playing"
            return room

    def guess_room(self, room_id: str, player_id: str, guess: str) -> tuple[MotusRoom, Dict[str, Any]]:
        with self._lock:
            room = self.get_room(room_id, player_id)
            if room.status != "playing":
                raise ValueError("La partie n'est pas en cours.")
            result = room.players[player_id].submit(
                guess,
                room.target,
                self.dictionary,
                MOTUS_DIFFICULTIES[room.difficulty],
            )
            if all(player.finished for player in room.players.values()):
                room.status = "finished"
            return room, result


motus_manager = MotusManager()
