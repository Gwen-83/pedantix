import functools
import random
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

import numpy as np
from rapidfuzz import fuzz

from app.nlp import (
    CONCEPT_LOOKUP,
    FRENCH_DICTIONARY,
    FRENCH_SYNONYMS,
    FRENCH_WORDNET_SYNSETS,
    FRENCH_VERB_LEMMA_CANDIDATES,
    FRENCH_VERB_LEMMAS,
    HARDCODED_SYNONYMS,
    NON_FLEXIBLE_WORDS,
    STOPWORDS_EXACT,
    THEMATIC_CLUSTERS,
    WORD_ASSOCIATIONS,
    WORD_EMBEDDING_INDEX,
    WORD_EMBEDDING_NORMS,
    WORD_EMBEDDINGS,
    WORD2VEC_RANKING_VOCAB_SIZE,
    _get_embedding_index,
    calculate_proximity,
    calculate_word2vec_cosine,
    calculate_word2vec_rank,
    check_match,
    clean_guess,
    get_word2vec_nearest_words,
    get_singular_forms,
    is_valid_french_word,
    normalize_text,
    stem_french,
)

CEMANTIX_ROUND_SECONDS = 60
CEMANTIX_MAX_PLAYERS = 8
CEMANTIX_DIFFICULTIES = {
    "facile": (0, 3, 6, 10, 15, 20, 26, 32),
    "moyen": (2, 6, 10, 15, 20, 26, 32),
    "difficile": (5, 10, 16, 22, 28, 35),
}

# Meaningful French nouns that happen to share spelling with stopwords
CEMANTIX_ALLOWED_NOUN_HOMOGRAPHS = {
    "son",
    "or",
    "pas",
    "vers",
    "bien",
    "ete",
    "cours",
    "point",
    "ton",
    "air",
    "fer",
}

_NOUN_HOMOGRAPH_ANCHORS: Dict[str, Tuple[str, ...]] = {
    "son": ("bruit", "voix", "musique", "acoustique", "onde", "ecoute"),
    "or": ("argent", "metal", "bijou", "tresor", "richesse", "monnaie"),
    "pas": ("marche", "pied", "chemin", "danse", "mouvement"),
    "vers": ("poeme", "poesie", "rime", "strophe", "litterature"),
    "bien": ("bon", "valeur", "morale", "bonheur", "avantage"),
    "ton": ("voix", "musique", "note", "couleur", "style"),
}


def _visible_hint_count(difficulty: str, attempts: int) -> int:
    return sum(threshold <= attempts for threshold in CEMANTIX_DIFFICULTIES[difficulty])


def _is_canonical_target_word(word: str, max_embedding_index: int = 25000) -> bool:
    if (
        word not in FRENCH_DICTIONARY
        or word in STOPWORDS_EXACT
        or not (3 <= len(word) <= 14 and re.fullmatch(r"[a-z]+", word))
    ):
        return False
    emb_idx = WORD_EMBEDDING_INDEX.get(word)
    if emb_idx is None or emb_idx > max_embedding_index:
        return False
    # Exclude plural forms when their singular exists in the dictionary
    if word not in NON_FLEXIBLE_WORDS and word.endswith(("s", "x")):
        singulars = get_singular_forms(word) - {word}
        if any(sing in FRENCH_DICTIONARY for sing in singulars):
            return False
    # Exclude conjugated verb forms that are neither infinitives nor core nouns
    lemma = FRENCH_VERB_LEMMAS.get(word)
    if lemma and lemma != word and not word.endswith(("er", "ir", "re", "oir")):
        if word not in CONCEPT_LOOKUP and word not in WORD_ASSOCIATIONS:
            return False
    return True


def _default_answers() -> List[str]:
    semantic_words = (
        set(HARDCODED_SYNONYMS)
        | set(WORD_ASSOCIATIONS)
        | set(CONCEPT_LOOKUP)
        | set().union(*THEMATIC_CLUSTERS.values())
    )
    candidates = semantic_words | {
        word
        for word, index in WORD_EMBEDDING_INDEX.items()
        if index < 25000
        and any(
            synset.rsplit("-", 1)[-1] in {"n", "a", "s"}
            for synset in FRENCH_WORDNET_SYNSETS.get(word, ())
        )
    }
    return sorted(
        word
        for word in candidates
        if _is_canonical_target_word(word)
        and (
            not FRENCH_WORDNET_SYNSETS.get(word)
            or any(
                synset.rsplit("-", 1)[-1] in {"n", "a", "s"}
                for synset in FRENCH_WORDNET_SYNSETS[word]
            )
        )
    )


_ASSOC_REVERSE: Dict[str, set[str]] = {}
for _src, _assocs in WORD_ASSOCIATIONS.items():
    for _dst in _assocs:
        _ASSOC_REVERSE.setdefault(_dst, set()).add(_src)

_HARDCODED_SYN_REVERSE: Dict[str, set[str]] = {}
for _src, _syns in HARDCODED_SYNONYMS.items():
    for _dst in _syns:
        _HARDCODED_SYN_REVERSE.setdefault(_dst, set()).add(_src)


@functools.lru_cache(maxsize=16384)
def _normalized_embedding_vector(word: str) -> Optional[np.ndarray]:
    idx = _get_embedding_index(word)
    if idx is None:
        idx = WORD_EMBEDDING_INDEX.get(stem_french(word))
    if idx is not None and WORD_EMBEDDING_NORMS[idx] > 0:
        return WORD_EMBEDDINGS[idx].astype(np.float32) / WORD_EMBEDDING_NORMS[idx]

    # Fallback: average normalized vectors of up to 8 direct semantic neighbors
    neighbors: List[str] = []
    for source in (
        HARDCODED_SYNONYMS.get(word, ()),
        _HARDCODED_SYN_REVERSE.get(word, ()),
        WORD_ASSOCIATIONS.get(word, ()),
        _ASSOC_REVERSE.get(word, ()),
        FRENCH_SYNONYMS.get(word, ()),
    ):
        for cand in source:
            if cand not in neighbors:
                neighbors.append(cand)
            if len(neighbors) >= 12:
                break
        if len(neighbors) >= 12:
            break

    vecs = []
    for cand in neighbors:
        c_idx = _get_embedding_index(cand)
        if c_idx is not None and WORD_EMBEDDING_NORMS[c_idx] > 0:
            vecs.append(WORD_EMBEDDINGS[c_idx].astype(np.float32) / WORD_EMBEDDING_NORMS[c_idx])
            if len(vecs) >= 8:
                break
    if not vecs:
        return None
    mean_vec = np.mean(vecs, axis=0)
    norm = float(np.linalg.norm(mean_vec))
    if norm <= 0:
        return None
    return mean_vec / norm


@functools.lru_cache(maxsize=8192)
def _target_anchors(target: str) -> Tuple[str, ...]:
    candidates = (
        set(HARDCODED_SYNONYMS.get(target, ()))
        | _HARDCODED_SYN_REVERSE.get(target, set())
        | set(WORD_ASSOCIATIONS.get(target, ()))
        | _ASSOC_REVERSE.get(target, set())
    )
    for concept, _role in CONCEPT_LOOKUP.get(target, ()):
        candidates.update(concept["core"])
    candidates.discard(target)
    scored: List[Tuple[float, str]] = []
    for cand in candidates:
        if cand not in STOPWORDS_EXACT:
            prox = calculate_proximity(cand, target)
            if prox >= 52.0:
                scored.append((prox, cand))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return tuple(word for _, word in scored[:16])


@functools.lru_cache(maxsize=65536)
def calculate_cemantix_proximity(word: str, target: str) -> float:
    """
    Calculates a continuous, non-zero semantic proximity score in [2.0, 100.0]
    for Cémantix so every valid French guess gives meaningful graduated feedback.
    Preserves exact >= 48.0 scores from `calculate_proximity(word, target)`.
    """
    if not word or not target:
        return 0.0
    if word == target:
        return 100.0

    base = calculate_proximity(word, target)
    if base >= 48.0:
        return round(min(base, 99.9), 1)

    # Check morphological variants (singulars, verb lemmas) and homograph anchors
    variant_candidates = set(get_singular_forms(word) - {word})
    variant_candidates.update(FRENCH_VERB_LEMMA_CANDIDATES.get(word, ()))
    if word in _NOUN_HOMOGRAPH_ANCHORS:
        for anchor in _NOUN_HOMOGRAPH_ANCHORS[word]:
            if anchor == target:
                return 88.0
            base = max(base, calculate_proximity(anchor, target) * 0.92)
    for variant in variant_candidates:
        if variant == target:
            return 99.5
        v_prox = calculate_proximity(variant, target)
        if v_prox >= 48.0:
            base = max(base, max(48.0, v_prox - 0.4))
    if base >= 48.0:
        return round(min(base, 99.9), 1)

    # 2-hop semantic bridge via target's core anchors
    anchors = _target_anchors(target)
    best_bridge = 0.0
    probe_words = (word, * _NOUN_HOMOGRAPH_ANCHORS.get(word, ()))
    for probe in probe_words:
        for anchor in anchors:
            if probe == anchor:
                best_bridge = max(best_bridge, 62.0)
                continue
            p = calculate_proximity(probe, anchor)
            if p >= 54.0:
                best_bridge = max(best_bridge, p * 0.68)

    if best_bridge >= 48.0:
        return round(min(best_bridge, 64.0), 1)

    # Continuous neural embedding cosine mapping across [-1.0, 0.15] -> [2.0, 47.8]
    w_vec = _normalized_embedding_vector(word)
    t_vec = _normalized_embedding_vector(target)
    if w_vec is not None and t_vec is not None:
        cos = float(np.dot(w_vec, t_vec))
        for anchor in anchors[:5]:
            a_vec = _normalized_embedding_vector(anchor)
            if a_vec is not None:
                cos = max(cos, float(np.dot(w_vec, a_vec)) * 0.78)
        if cos <= -0.20:
            emb_score = 2.5 + max(0.0, (cos + 0.50) / 0.30) * 2.5
        elif cos <= -0.05:
            emb_score = 5.0 + (cos - (-0.20)) / 0.15 * 9.0
        elif cos <= 0.05:
            emb_score = 14.0 + (cos - (-0.05)) / 0.10 * 13.0
        elif cos <= 0.12:
            emb_score = 27.0 + (cos - 0.05) / 0.07 * 13.0
        else:
            emb_score = 40.0 + min(1.0, (cos - 0.12) / 0.04) * 7.8
        return round(max(best_bridge, emb_score), 1)

    # Deterministic lexical fallback when embeddings are unavailable
    lex_ratio = fuzz.ratio(word, target) / 100.0
    fallback = 4.0 + lex_ratio * 18.0
    return round(max(best_bridge, min(47.5, fallback)), 1)


def calculate_cemantix_temperature(word: str, target: str) -> float:
    """Return the Word2Vec cosine as a Celsius-like temperature, without heuristics."""
    normalized_word = normalize_text(clean_guess(word))
    normalized_target = normalize_text(target)
    if not normalized_word or not normalized_target:
        return 0.0
    if normalized_word == normalized_target:
        return 100.0
    cosine = calculate_word2vec_cosine(word, target)
    return round(cosine * 100.0, 2) if cosine is not None else 0.0


@dataclass
class CemantixGame:
    game_id: str
    target: str
    player_id: str
    player_name: str
    difficulty: str = "moyen"
    hint_words: List[str] = field(default_factory=list)
    hint_scores: Dict[str, float] = field(default_factory=dict)
    guesses: List[Dict[str, Any]] = field(default_factory=list)
    guessed_words: set[str] = field(default_factory=set)
    extra_hints: int = 0
    gave_up: bool = False
    status: str = "playing"
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        visible_count = min(
            len(self.hint_words),
            _visible_hint_count(self.difficulty, len(self.guesses)) + self.extra_hints,
        )
        visible_hints = self.hint_words[:visible_count]
        return {
            "game_id": self.game_id,
            "status": self.status,
            "difficulty": self.difficulty,
            "gave_up": self.gave_up,
            "hints": visible_hints,
            "hint_details": [
                {"word": w, "score": self.hint_scores.get(w)}
                for w in visible_hints
            ],
            "has_more_hints": self.status == "playing" and visible_count < len(self.hint_words),
            "player": {
                "player_id": self.player_id,
                "name": self.player_name,
                "guesses": self.guesses,
                "attempts": len(self.guesses),
                "solved": self.status == "finished" and not self.gave_up,
                "gave_up": self.gave_up,
            },
            "target": self.target if self.status == "finished" else None,
        }


@dataclass
class CemantixPlayer:
    player_id: str
    name: str
    guesses: List[Dict[str, Any]] = field(default_factory=list)
    is_spectator: bool = False


@dataclass
class CemantixSubmission:
    word: str
    score: float
    rank: int
    solved: bool
    submitted_at: float


@dataclass
class CemantixRoom:
    room_id: str
    target: str
    host_player_id: str
    difficulty: str = "moyen"
    hint_words: List[str] = field(default_factory=list)
    hint_scores: Dict[str, float] = field(default_factory=dict)
    players: Dict[str, CemantixPlayer] = field(default_factory=dict)
    status: str = "lobby"
    round_number: int = 0
    deadline_at: Optional[float] = None
    pending: Dict[str, CemantixSubmission] = field(default_factory=dict)
    winner_player_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    match_number: int = 1
    stats_recorded: bool = False

    def to_dict(self, player_id: str, now: float) -> Dict[str, Any]:
        player = self.players[player_id]
        visible_hints = self.hint_words[
            :_visible_hint_count(self.difficulty, len(player.guesses))
        ]
        return {
            "room_id": self.room_id,
            "status": self.status,
            "match_number": self.match_number,
            "host_player_id": self.host_player_id,
            "difficulty": self.difficulty,
            "round_number": self.round_number,
            "round_seconds": CEMANTIX_ROUND_SECONDS,
            "deadline_at": self.deadline_at,
            "time_left": max(0, int(self.deadline_at - now)) if self.deadline_at else 0,
            "player_id": player_id,
            "player": {
                "player_id": player.player_id,
                "name": player.name,
                "guesses": player.guesses,
                "has_submitted": player_id in self.pending,
                "is_spectator": player.is_spectator,
                "hints": visible_hints,
                "hint_details": [
                    {"word": w, "score": self.hint_scores.get(w)}
                    for w in visible_hints
                ],
            },
            "players": [
                {
                    "player_id": item.player_id,
                    "name": item.name,
                    "guesses": item.guesses,
                    "has_submitted": item.player_id in self.pending,
                    "is_spectator": item.is_spectator,
                }
                for item in self.players.values()
            ],
            "submitted_count": len(self.pending),
            "player_count": sum(not item.is_spectator for item in self.players.values()),
            "spectator_count": sum(item.is_spectator for item in self.players.values()),
            "can_start": self.status == "lobby"
            and sum(not item.is_spectator for item in self.players.values()) >= 2,
            "can_restart": self.status == "finished" and player_id == self.host_player_id,
            "restart_available": self.status == "finished",
            "winner_player_id": self.winner_player_id,
            "target": self.target if self.status == "finished" else None,
        }


class CemantixManager:
    def __init__(
        self,
        words: Optional[Iterable[str]] = None,
        answers: Optional[Iterable[str]] = None,
        clock: Callable[[], float] = time.time,
    ):
        self._uses_default_dictionary = words is None
        self.dictionary = {
            normalize_text(word)
            for word in (words if words is not None else FRENCH_DICTIONARY)
            if re.fullmatch(r"[a-z]+", normalize_text(word))
        }
        candidates = answers if answers is not None else _default_answers()
        self.answers = sorted(
            {
                normalize_text(word)
                for word in candidates
                if normalize_text(word) in self.dictionary
                and normalize_text(word) not in STOPWORDS_EXACT
                and re.fullmatch(r"[a-z]+", normalize_text(word))
            }
        )
        if not self.answers:
            raise ValueError("La liste de mots Cémantix ne contient aucun mot reconnu.")
        self._clock = clock
        self.solo_games: Dict[str, CemantixGame] = {}
        self.rooms: Dict[str, CemantixRoom] = {}
        self._lock = threading.RLock()

    def _pick_target(self) -> str:
        return random.choice(self.answers)

    @staticmethod
    def _validate_difficulty(difficulty: str) -> str:
        if difficulty not in CEMANTIX_DIFFICULTIES:
            raise ValueError("Difficulté invalide. Choisissez facile, moyen ou difficile.")
        return difficulty

    def _hint_words_with_scores(self, target: str) -> List[Tuple[str, float]]:
        scored = []
        for candidate, cosine in get_word2vec_nearest_words(target):
            if (
                candidate == target
                or candidate not in self.dictionary
                or candidate in STOPWORDS_EXACT
                or not _is_canonical_target_word(
                    candidate, max_embedding_index=WORD2VEC_RANKING_VOCAB_SIZE
                )
                or not any(
                    synset.rsplit("-", 1)[-1] in {"n", "a", "s"}
                    for synset in FRENCH_WORDNET_SYNSETS.get(candidate, ())
                )
                or check_match(candidate, target)
            ):
                continue
            scored.append((round(cosine * 100.0, 2), candidate))

        scored.sort(key=lambda item: (-item[0], item[1]))
        if len(scored) <= 8:
            # Order progressively from warm to hot so early hints guide without spoiling
            progressive = list(reversed(scored))
            return [(word, score) for score, word in progressive]

        # Select up to 8 graduated hints spanning from moderate warm (~55-70) to very hot (~85-95)
        pool = scored[:24]
        pool_asc = list(reversed(pool))
        indices = [
            int(round(i * (len(pool_asc) - 1) / 7))
            for i in range(8)
        ]
        selected: List[Tuple[str, float]] = []
        seen: set[str] = set()
        for idx in indices:
            score, word = pool_asc[idx]
            if word not in seen:
                seen.add(word)
                selected.append((word, score))
        return selected

    def _hint_words(self, target: str) -> List[str]:
        return [word for word, _ in self._hint_words_with_scores(target)]

    def _normalize_valid_guess(self, raw_guess: str) -> str:
        word = normalize_text(clean_guess(raw_guess))
        if not word or not re.fullmatch(r"[a-z]+", word):
            raise ValueError("Saisissez un seul mot composé de lettres.")
        if word not in self.dictionary:
            if self._uses_default_dictionary and is_valid_french_word(word):
                pass
            else:
                singulars = get_singular_forms(word) - {word}
                lemmas = FRENCH_VERB_LEMMA_CANDIDATES.get(word, set())
                if not any(cand in self.dictionary for cand in singulars | lemmas):
                    raise ValueError("Ce mot n'est pas reconnu dans le dictionnaire français.")
        if word in STOPWORDS_EXACT and word not in CEMANTIX_ALLOWED_NOUN_HOMOGRAPHS:
            raise ValueError("Les mots outils ne peuvent pas être proposés.")
        if _get_embedding_index(word) is None:
            raise ValueError("Ce mot n'est pas présent dans le modèle sémantique.")
        return word

    def _score(self, word: str, target: str) -> tuple[float, bool, int]:
        solved = word == target
        if solved:
            return 100.0, True, 1000
        score = calculate_cemantix_temperature(word, target)
        rank = calculate_word2vec_rank(word, target)
        return score, False, rank

    def create_solo(
        self, player_id: str, player_name: str, difficulty: str = "moyen"
    ) -> CemantixGame:
        with self._lock:
            difficulty = self._validate_difficulty(difficulty)
            target = self._pick_target()
            hints_with_scores = self._hint_words_with_scores(target)
            game = CemantixGame(
                game_id=uuid.uuid4().hex,
                target=target,
                player_id=player_id,
                player_name=player_name,
                difficulty=difficulty,
                hint_words=[w for w, _ in hints_with_scores],
                hint_scores={w: s for w, s in hints_with_scores},
            )
            self.solo_games[game.game_id] = game
            return game

    def get_solo(self, game_id: str, player_id: str) -> CemantixGame:
        with self._lock:
            game = self.solo_games.get(game_id)
            if not game or game.player_id != player_id:
                raise KeyError("Cette partie solo est introuvable.")
            return game

    def guess_solo(
        self, game_id: str, player_id: str, raw_guess: str
    ) -> tuple[CemantixGame, Dict[str, Any]]:
        with self._lock:
            game = self.get_solo(game_id, player_id)
            if game.status == "finished":
                raise ValueError("Cette partie est déjà terminée.")
            word = self._normalize_valid_guess(raw_guess)
            if word in game.guessed_words:
                raise ValueError("Vous avez déjà proposé ce mot.")

            score, solved, rank = self._score(word, game.target)
            game.guessed_words.add(word)
            result = {
                "word": word,
                "score": score,
                "rank": rank,
                "solved": solved,
                "attempt": len(game.guesses) + 1,
            }
            game.guesses.append(result)
            if solved:
                game.status = "finished"
            return game, result

    def request_solo_hint(self, game_id: str, player_id: str) -> CemantixGame:
        with self._lock:
            game = self.get_solo(game_id, player_id)
            if game.status == "finished":
                raise ValueError("Cette partie est déjà terminée.")
            auto_count = _visible_hint_count(game.difficulty, len(game.guesses))
            if auto_count + game.extra_hints < len(game.hint_words):
                game.extra_hints += 1
            return game

    def give_up_solo(self, game_id: str, player_id: str) -> CemantixGame:
        with self._lock:
            game = self.get_solo(game_id, player_id)
            if game.status == "finished":
                return game
            game.gave_up = True
            game.status = "finished"
            return game

    def create_room(
        self, player_id: str, player_name: str, difficulty: str = "moyen"
    ) -> CemantixRoom:
        with self._lock:
            difficulty = self._validate_difficulty(difficulty)
            room_id = uuid.uuid4().hex[:6].upper()
            while room_id in self.rooms:
                room_id = uuid.uuid4().hex[:6].upper()
            target = self._pick_target()
            hints_with_scores = self._hint_words_with_scores(target)
            room = CemantixRoom(
                room_id=room_id,
                target=target,
                host_player_id=player_id,
                difficulty=difficulty,
                hint_words=[w for w, _ in hints_with_scores],
                hint_scores={w: s for w, s in hints_with_scores},
            )
            room.players[player_id] = CemantixPlayer(player_id, player_name)
            self.rooms[room_id] = room
            return room

    def list_rooms(
        self, player_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        with self._lock:
            now = self._clock()
            rooms = []
            for room in self.rooms.values():
                self._advance_room(room, now)
                if room.status == "finished":
                    continue
                rooms.append({
                    "room_id": room.room_id,
                    "status": room.status,
                    "player_count": sum(
                        not player.is_spectator for player in room.players.values()
                    ),
                    "spectator_count": sum(
                        player.is_spectator for player in room.players.values()
                    ),
                    "host_name": room.players[room.host_player_id].name,
                    "difficulty": room.difficulty,
                    "is_member": player_id in room.players if player_id else False,
                })
            return rooms

    def _advance_room(self, room: CemantixRoom, now: float) -> None:
        if room.status != "playing" or room.deadline_at is None:
            return
        active_players = [
            player for player in room.players.values() if not player.is_spectator
        ]
        if len(room.pending) < len(active_players) and now < room.deadline_at:
            return

        for player in active_players:
            player_id = player.player_id
            submission = room.pending.get(player_id)
            if submission:
                player.guesses.append(
                    {
                        "round": room.round_number,
                        "word": submission.word,
                        "score": submission.score,
                        "rank": submission.rank,
                        "solved": submission.solved,
                        "passed": False,
                    }
                )
            else:
                player.guesses.append(
                    {
                        "round": room.round_number,
                        "word": None,
                        "score": None,
                        "solved": False,
                        "passed": True,
                    }
                )

        winners = [
            (submission.submitted_at, player_id)
            for player_id, submission in room.pending.items()
            if submission.solved
        ]
        if winners:
            _, room.winner_player_id = min(winners)
            room.status = "finished"
            room.deadline_at = None
            room.pending.clear()
            return

        room.round_number += 1
        room.deadline_at = now + CEMANTIX_ROUND_SECONDS
        room.pending.clear()
        for player in room.players.values():
            if player.is_spectator:
                player.is_spectator = False

    def join_room(
        self, room_id: str, player_id: str, player_name: str
    ) -> CemantixRoom:
        with self._lock:
            room = self.rooms.get(room_id.upper())
            if not room:
                raise KeyError("Salon introuvable ou expiré.")
            self._advance_room(room, self._clock())
            if player_id in room.players:
                room.players[player_id].name = player_name
                return room
            if room.status == "playing":
                if len(room.players) >= CEMANTIX_MAX_PLAYERS:
                    raise ValueError(f"Ce salon est complet ({CEMANTIX_MAX_PLAYERS} joueurs maximum).")
                room.players[player_id] = CemantixPlayer(
                    player_id, player_name, is_spectator=True
                )
                return room
            if room.status != "lobby":
                raise ValueError("La partie a commencé. Seuls les joueurs déjà inscrits peuvent revenir.")
            if len(room.players) >= CEMANTIX_MAX_PLAYERS:
                raise ValueError(f"Ce salon est complet ({CEMANTIX_MAX_PLAYERS} joueurs maximum).")
            room.players[player_id] = CemantixPlayer(player_id, player_name)
            return room

    def get_room(self, room_id: str, player_id: str) -> CemantixRoom:
        with self._lock:
            room = self.rooms.get(room_id.upper())
            if not room or player_id not in room.players:
                raise KeyError("Salon ou joueur introuvable.")
            self._advance_room(room, self._clock())
            return room

    def start_room(self, room_id: str, player_id: str) -> CemantixRoom:
        with self._lock:
            room = self.get_room(room_id, player_id)
            if room.host_player_id != player_id:
                raise PermissionError("Seul l'hôte peut démarrer la partie.")
            if room.status != "lobby":
                raise ValueError("Cette partie a déjà démarré.")
            if sum(not player.is_spectator for player in room.players.values()) < 2:
                raise ValueError("Il faut au moins deux joueurs pour démarrer.")
            now = self._clock()
            room.status = "playing"
            room.round_number = 1
            room.deadline_at = now + CEMANTIX_ROUND_SECONDS
            room.started_at = now
            room.stats_recorded = False
            return room

    def restart_room(self, room_id: str, player_id: str) -> CemantixRoom:
        with self._lock:
            room = self.get_room(room_id, player_id)
            if room.host_player_id != player_id:
                raise PermissionError("Seul l'hôte peut redémarrer la partie.")
            if room.status != "finished":
                raise ValueError("La partie doit être terminée pour être redémarrée.")
            now = self._clock()
            room.target = self._pick_target()
            room.match_number += 1
            hints_with_scores = self._hint_words_with_scores(room.target)
            room.hint_words = [w for w, _ in hints_with_scores]
            room.hint_scores = {w: s for w, s in hints_with_scores}
            for player in room.players.values():
                player.guesses.clear()
                player.is_spectator = False
            room.status = "playing"
            room.round_number = 1
            room.deadline_at = now + CEMANTIX_ROUND_SECONDS
            room.pending.clear()
            room.winner_player_id = None
            room.started_at = now
            room.stats_recorded = False
            return room

    def submit_room_guess(
        self, room_id: str, player_id: str, raw_guess: str
    ) -> tuple[CemantixRoom, Dict[str, Any]]:
        with self._lock:
            room = self.get_room(room_id, player_id)
            if room.status != "playing":
                raise ValueError("La partie n'est pas en cours.")
            if room.players[player_id].is_spectator:
                raise ValueError("Les spectateurs ne peuvent pas proposer de mot.")
            if player_id in room.pending:
                raise ValueError("Votre proposition pour cette manche a déjà été envoyée.")

            word = self._normalize_valid_guess(raw_guess)
            if word in {
                guess["word"]
                for guess in room.players[player_id].guesses
                if guess["word"] is not None
            }:
                raise ValueError("Vous avez déjà proposé ce mot.")

            score, solved, rank = self._score(word, room.target)
            submission = CemantixSubmission(
                word=word,
                score=score,
                rank=rank,
                solved=solved,
                submitted_at=self._clock(),
            )
            submitted_round = room.round_number
            room.pending[player_id] = submission
            self._advance_room(room, self._clock())
            return room, {
                "submitted": True,
                "round_number": submitted_round,
            }


cemantix_manager = CemantixManager()
