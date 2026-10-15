import math
import logging
import os
import random
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import requests

from app.database import get_geoguessr_google_usage, reserve_geoguessr_google_usage

ROUND_COUNT = 5
MAX_PLAYERS = 8
MAX_SCORE_PER_ROUND = 5_000
EARTH_RADIUS_KM = 6_371.0088
GEOGUESSR_REGIONS = {"france", "europe", "world"}
GEOGUESSR_VARIANTS = {"cities", "panorama"}
MAPILLARY_API_URL = "https://graph.mapillary.com/images"
GOOGLE_STREETVIEW_METADATA_URL = "https://maps.googleapis.com/maps/api/streetview/metadata"
GOOGLE_STREETVIEW_MONTHLY_LIMIT = 4_000
logger = logging.getLogger("pedantix.geoguessr")

# Curated city coordinates keep rounds deterministic in format and avoid geocoding
# dependencies; the answer is only exposed after a guess is locked.
CITY_LOCATIONS = (
    ("Paris", "France", "france", 48.8566, 2.3522),
    ("Lyon", "France", "france", 45.7640, 4.8357),
    ("Marseille", "France", "france", 43.2965, 5.3698),
    ("Toulouse", "France", "france", 43.6047, 1.4442),
    ("Bordeaux", "France", "france", 44.8378, -0.5792),
    ("Lille", "France", "france", 50.6292, 3.0573),
    ("Nantes", "France", "france", 47.2184, -1.5536),
    ("Strasbourg", "France", "france", 48.5734, 7.7521),
    ("Nice", "France", "france", 43.7102, 7.2620),
    ("Rennes", "France", "france", 48.1173, -1.6778),
    ("Montpellier", "France", "france", 43.6119, 3.8772),
    ("Grenoble", "France", "france", 45.1885, 5.7245),
    ("Dijon", "France", "france", 47.3220, 5.0415),
    ("Reims", "France", "france", 49.2583, 4.0317),
    ("Clermont-Ferrand", "France", "france", 45.7772, 3.0870),
    ("Brest", "France", "france", 48.3904, -4.4861),
    ("Ajaccio", "France", "france", 41.9192, 8.7386),
    ("Amsterdam", "Pays-Bas", "europe", 52.3676, 4.9041),
    ("Bruxelles", "Belgique", "europe", 50.8503, 4.3517),
    ("Londres", "Royaume-Uni", "europe", 51.5072, -0.1276),
    ("Dublin", "Irlande", "europe", 53.3498, -6.2603),
    ("Lisbonne", "Portugal", "europe", 38.7223, -9.1393),
    ("Madrid", "Espagne", "europe", 40.4168, -3.7038),
    ("Barcelone", "Espagne", "europe", 41.3874, 2.1686),
    ("Rome", "Italie", "europe", 41.9028, 12.4964),
    ("Milan", "Italie", "europe", 45.4642, 9.1900),
    ("Berlin", "Allemagne", "europe", 52.5200, 13.4050),
    ("Munich", "Allemagne", "europe", 48.1351, 11.5820),
    ("Vienne", "Autriche", "europe", 48.2082, 16.3738),
    ("Prague", "Tchéquie", "europe", 50.0755, 14.4378),
    ("Varsovie", "Pologne", "europe", 52.2297, 21.0122),
    ("Budapest", "Hongrie", "europe", 47.4979, 19.0402),
    ("Athènes", "Grèce", "europe", 37.9838, 23.7275),
    ("Stockholm", "Suède", "europe", 59.3293, 18.0686),
    ("Oslo", "Norvège", "europe", 59.9139, 10.7522),
    ("Helsinki", "Finlande", "europe", 60.1699, 24.9384),
    ("Copenhague", "Danemark", "europe", 55.6761, 12.5683),
    ("Bucarest", "Roumanie", "europe", 44.4268, 26.1025),
    ("Istanbul", "Turquie", "europe", 41.0082, 28.9784),
    ("Reykjavik", "Islande", "europe", 64.1466, -21.9426),
    ("New York", "États-Unis", "world", 40.7128, -74.0060),
    ("Los Angeles", "États-Unis", "world", 34.0522, -118.2437),
    ("Chicago", "États-Unis", "world", 41.8781, -87.6298),
    ("Mexico", "Mexique", "world", 19.4326, -99.1332),
    ("La Havane", "Cuba", "world", 23.1136, -82.3666),
    ("Bogotá", "Colombie", "world", 4.7110, -74.0721),
    ("Lima", "Pérou", "world", -12.0464, -77.0428),
    ("Rio de Janeiro", "Brésil", "world", -22.9068, -43.1729),
    ("Buenos Aires", "Argentine", "world", -34.6037, -58.3816),
    ("Santiago", "Chili", "world", -33.4489, -70.6693),
    ("Tokyo", "Japon", "world", 35.6762, 139.6503),
    ("Osaka", "Japon", "world", 34.6937, 135.5023),
    ("Séoul", "Corée du Sud", "world", 37.5665, 126.9780),
    ("Pékin", "Chine", "world", 39.9042, 116.4074),
    ("Shanghai", "Chine", "world", 31.2304, 121.4737),
    ("Bangkok", "Thaïlande", "world", 13.7563, 100.5018),
    ("Hanoï", "Vietnam", "world", 21.0278, 105.8342),
    ("Singapour", "Singapour", "world", 1.3521, 103.8198),
    ("Jakarta", "Indonésie", "world", -6.2088, 106.8456),
    ("Delhi", "Inde", "world", 28.6139, 77.2090),
    ("Mumbai", "Inde", "world", 19.0760, 72.8777),
    ("Katmandou", "Népal", "world", 27.7172, 85.3240),
    ("Dubaï", "Émirats arabes unis", "world", 25.2048, 55.2708),
    ("Le Caire", "Égypte", "world", 30.0444, 31.2357),
    ("Nairobi", "Kenya", "world", -1.2921, 36.8219),
    ("Johannesburg", "Afrique du Sud", "world", -26.2041, 28.0473),
    ("Le Cap", "Afrique du Sud", "world", -33.9249, 18.4241),
    ("Casablanca", "Maroc", "world", 33.5731, -7.5898),
    ("Sydney", "Australie", "world", -33.8688, 151.2093),
    ("Melbourne", "Australie", "world", -37.8136, 144.9631),
    ("Auckland", "Nouvelle-Zélande", "world", -36.8509, 174.7645),
)


def validate_region(region: str) -> str:
    normalized = region.strip().lower()
    if normalized not in GEOGUESSR_REGIONS:
        raise ValueError("Choisissez une zone valide : France, Europe ou Monde.")
    return normalized


def _city_pool(region: str) -> List[tuple[str, str, str, float, float]]:
    selected = [
        city for city in CITY_LOCATIONS
        if region == "world"
        or (region == "france" and city[2] == "france")
        or (region == "europe" and city[2] in {"france", "europe"})
    ]
    if not selected:
        raise ValueError("Aucune ville n'est disponible pour cette zone.")
    return selected


def distance_km(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    lat1, lat2 = math.radians(lat_a), math.radians(lat_b)
    delta_lat = lat2 - lat1
    delta_lon = math.radians(lon_b - lon_a)
    haversine = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    )
    return EARTH_RADIUS_KM * 2 * math.asin(math.sqrt(min(1.0, haversine)))


def score_distance_km(distance: float) -> int:
    return max(0, min(MAX_SCORE_PER_ROUND, round(MAX_SCORE_PER_ROUND * math.exp(-distance / 2_000))))


def _choose_city(region: str, previous: set[str]) -> tuple[str, str, str, float, float]:
    pool = _city_pool(region)
    choices = [city for city in pool if city[0] not in previous] or pool
    return random.choice(choices)


def _public_city(city: tuple[str, str, str, float, float]) -> Dict[str, Any]:
    return {
        "city": city[0],
        "country": city[1],
        "latitude": city[3],
        "longitude": city[4],
    }


def _score_guess(city: tuple[str, str, str, float, float], latitude: float, longitude: float) -> Dict[str, Any]:
    distance = distance_km(latitude, longitude, city[3], city[4])
    return {
        "latitude": latitude,
        "longitude": longitude,
        "distance_km": round(distance, 1),
        "score": score_distance_km(distance),
    }


@dataclass
class GeoGuessrGame:
    game_id: str
    player_id: str
    player_name: str
    region: str
    cities: List[tuple[str, str, str, float, float]]
    variant: str = "cities"
    image_ids: List[str] = field(default_factory=list)
    panorama_provider: Optional[str] = None
    google_viewed_rounds: Set[Tuple[str, int]] = field(default_factory=set)
    created_at: float = field(default_factory=time.time)
    round_index: int = 0
    total_score: int = 0
    results: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "playing"

    @property
    def target(self) -> tuple[str, str, str, float, float]:
        return self.cities[min(self.round_index, len(self.cities) - 1)]

    def to_dict(self) -> Dict[str, Any]:
        last_result = self.results[-1] if self.results else None
        prompt = self.cities[self.round_index] if self.status == "playing" else None
        return {
            "game_id": self.game_id,
            "status": self.status,
            "mode": "solo",
            "variant": self.variant,
            "panorama_provider": self.panorama_provider,
            "region": self.region,
            "round_number": min(self.round_index + 1, ROUND_COUNT),
            "round_count": ROUND_COUNT,
            "total_score": self.total_score,
            "max_total_score": ROUND_COUNT * MAX_SCORE_PER_ROUND,
            "round_results": self.results,
            "last_result": last_result,
            "prompt": {"city": prompt[0], "country": prompt[1]} if prompt else None,
            "image_id": (
                self.image_ids[min(self.round_index, len(self.image_ids) - 1)]
                if self.variant == "panorama" and self.image_ids
                else None
            ),
            "target": _public_city(self.cities[-1]) if self.status == "finished" else None,
        }


@dataclass
class GeoGuessrRoomPlayer:
    player_id: str
    name: str
    total_score: int = 0
    guess: Optional[Dict[str, Any]] = None
    results: List[Dict[str, Any]] = field(default_factory=list)
    connected: bool = True

    def public_state(self) -> Dict[str, Any]:
        return {
            "player_id": self.player_id,
            "name": self.name,
            "total_score": self.total_score,
            "submitted": self.guess is not None,
            "guess": (
                {"latitude": self.guess["latitude"], "longitude": self.guess["longitude"]}
                if self.guess else None
            ),
            "round_results": self.results,
            "connected": self.connected,
        }


@dataclass
class GeoGuessrRoom:
    room_id: str
    host_player_id: str
    region: str
    cities: List[tuple[str, str, str, float, float]]
    variant: str = "cities"
    image_ids: List[str] = field(default_factory=list)
    panorama_provider: Optional[str] = None
    google_viewed_rounds: Set[Tuple[str, int]] = field(default_factory=set)
    players: Dict[str, GeoGuessrRoomPlayer] = field(default_factory=dict)
    status: str = "lobby"
    round_index: int = 0
    last_round: Optional[Dict[str, Any]] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    stats_recorded: bool = False

    @property
    def target(self) -> tuple[str, str, str, float, float]:
        return self.cities[min(self.round_index, len(self.cities) - 1)]

    def to_dict(self, player_id: str) -> Dict[str, Any]:
        player = self.players[player_id]
        prompt = self.cities[self.round_index] if self.status == "playing" else None
        return {
            "room_id": self.room_id,
            "host_player_id": self.host_player_id,
            "status": self.status,
            "variant": self.variant,
            "panorama_provider": self.panorama_provider,
            "region": self.region,
            "round_number": min(self.round_index + 1, ROUND_COUNT),
            "round_count": ROUND_COUNT,
            "max_players": MAX_PLAYERS,
            "can_start": len(self.players) >= 2,
            "players": [item.public_state() for item in self.players.values()],
            "player": player.public_state(),
            "last_round": self.last_round,
            "prompt": {"city": prompt[0], "country": prompt[1]} if prompt else None,
            "image_id": (
                self.image_ids[min(self.round_index, len(self.image_ids) - 1)]
                if self.variant == "panorama" and self.image_ids and self.status != "lobby"
                else None
            ),
            "target": self.last_round["target"] if self.status == "finished" and self.last_round else None,
        }


class GeoGuessrManager:
    def __init__(
        self,
        mapillary_access_token: Optional[str] = None,
        google_maps_server_api_key: Optional[str] = None,
        google_maps_browser_api_key: Optional[str] = None,
        google_usage_reader: Callable[[], int] = get_geoguessr_google_usage,
        google_usage_reserver: Callable[[int, int], bool] = reserve_geoguessr_google_usage,
    ) -> None:
        self.solo_games: Dict[str, GeoGuessrGame] = {}
        self.rooms: Dict[str, GeoGuessrRoom] = {}
        self.mapillary_access_token = (
            mapillary_access_token or os.environ.get("MAPILLARY_ACCESS_TOKEN", "")
        ).strip()
        self.google_maps_server_api_key = (
            google_maps_server_api_key or os.environ.get("GOOGLE_MAPS_SERVER_API_KEY", "")
        ).strip()
        self.google_maps_browser_api_key = (
            google_maps_browser_api_key or os.environ.get("GOOGLE_MAPS_BROWSER_API_KEY", "")
        ).strip()
        self.google_usage_reader = google_usage_reader
        self.google_usage_reserver = google_usage_reserver
        self.photo_cache: Dict[str, List[Dict[str, Any]]] = {}
        self.lock = threading.RLock()

    def google_usage(self) -> int:
        return self.google_usage_reader()

    def _get_google_targets(
        self, region: str,
    ) -> tuple[List[tuple[str, str, str, float, float]], List[str]]:
        if not self.google_maps_server_api_key:
            raise ValueError("La clé Google Maps n’est pas configurée.")

        targets: List[tuple[str, str, str, float, float]] = []
        image_ids: List[str] = []
        seen_panorama_ids: Set[str] = set()
        candidates = _city_pool(region)
        attempts = 0
        while len(targets) < ROUND_COUNT and attempts < 40:
            attempts += 1
            city = random.choice(candidates)
            latitude = city[3] + random.uniform(-0.025, 0.025)
            longitude = city[4] + random.uniform(-0.025, 0.025)
            try:
                response = requests.get(
                    GOOGLE_STREETVIEW_METADATA_URL,
                    params={
                        "location": f"{latitude:.6f},{longitude:.6f}",
                        "radius": 1_000,
                        "key": self.google_maps_server_api_key,
                    },
                    timeout=(3.05, 8),
                )
                response.raise_for_status()
                metadata = response.json()
            except (requests.RequestException, ValueError) as exc:
                raise ValueError(
                    "Impossible de joindre Google Street View. Vérifiez la clé API et la facturation."
                ) from exc

            if metadata.get("status") == "ZERO_RESULTS":
                continue
            if metadata.get("status") != "OK":
                raise ValueError(
                    "Google Street View n’a pas fourni de photo "
                    f"({metadata.get('status', 'réponse invalide')})."
                )

            panorama_id = str(metadata.get("pano_id") or "")
            location = metadata.get("location") or {}
            if (
                not panorama_id
                or panorama_id in seen_panorama_ids
                or "lat" not in location
                or "lng" not in location
            ):
                continue
            targets.append((
                "Lieu de la photo",
                "",
                region,
                float(location["lat"]),
                float(location["lng"]),
            ))
            image_ids.append(panorama_id)
            seen_panorama_ids.add(panorama_id)

        if len(targets) < ROUND_COUNT:
            raise ValueError("Google Street View n’a pas trouvé assez de photos dans cette zone.")
        return targets, image_ids

    def _get_panorama_targets(
        self,
        region: str,
        *,
        reserve_google_views: bool,
        google_viewer_count: int = 1,
    ) -> tuple[List[tuple[str, str, str, float, float]], List[str], str]:
        if self.google_maps_server_api_key and self.google_maps_browser_api_key:
            try:
                reserved_usage = ROUND_COUNT * google_viewer_count
                if (
                    self.google_usage() + reserved_usage
                    <= GOOGLE_STREETVIEW_MONTHLY_LIMIT
                ):
                    targets, image_ids = self._get_google_targets(region)
                    if not reserve_google_views or self.google_usage_reserver(
                        reserved_usage, GOOGLE_STREETVIEW_MONTHLY_LIMIT
                    ):
                        return targets, image_ids, "google"
            except Exception as exc:
                logger.warning(
                    "Google Street View indisponible, repli sur Mapillary : %s",
                    exc,
                )

        targets, image_ids = self._get_mapillary_targets(region)
        return targets, image_ids, "mapillary"

    def _get_mapillary_targets(self, region: str) -> tuple[List[tuple[str, str, str, float, float]], List[str]]:
        if not self.mapillary_access_token:
            raise ValueError(
                "Aucun fournisseur photo n’est disponible : configurez "
                "GOOGLE_MAPS_BROWSER_API_KEY et GOOGLE_MAPS_SERVER_API_KEY, "
                "ou MAPILLARY_ACCESS_TOKEN sur le serveur."
            )

        cached = self.photo_cache.setdefault(region, [])
        selected: List[Dict[str, Any]] = []
        seen_sequences: set[str] = set()
        for image in random.sample(cached, len(cached)):
            sequence_id = image["sequence_id"]
            if sequence_id not in seen_sequences:
                selected.append(image)
                seen_sequences.add(sequence_id)
            if len(selected) == ROUND_COUNT:
                break

        candidates = _city_pool(region)
        attempts = 0
        while len(selected) < ROUND_COUNT and attempts < 20:
            attempts += 1
            city = random.choice(candidates)
            latitude = city[3] + random.uniform(-0.025, 0.025)
            longitude = city[4] + random.uniform(-0.025, 0.025)
            delta = 0.0045
            bbox = (
                max(-180, longitude - delta),
                max(-90, latitude - delta),
                min(180, longitude + delta),
                min(90, latitude + delta),
            )
            try:
                response = requests.get(
                    MAPILLARY_API_URL,
                    params={
                        "bbox": ",".join(f"{coordinate:.6f}" for coordinate in bbox),
                        "fields": "id,geometry,sequence_id,is_pano",
                        "limit": 100,
                    },
                    headers={"Authorization": f"OAuth {self.mapillary_access_token}"},
                    timeout=(3.05, 8),
                )
            except requests.RequestException as exc:
                raise ValueError("Impossible de joindre Mapillary. Réessayez dans un instant.") from exc
            if response.status_code == 429:
                raise ValueError("Mapillary limite temporairement les requêtes. Réessayez dans un instant.")
            if not response.ok:
                raise ValueError(
                    f"Mapillary a refusé la requête (HTTP {response.status_code}). Vérifiez le jeton configuré."
                )
            try:
                images = response.json().get("data", [])
            except ValueError as exc:
                raise ValueError("Mapillary a renvoyé une réponse invalide.") from exc
            for image in images:
                sequence_id = image.get("sequence_id")
                coordinates = (image.get("geometry") or {}).get("coordinates")
                if (
                    not sequence_id
                    or not isinstance(coordinates, list)
                    or len(coordinates) < 2
                    or sequence_id in seen_sequences
                ):
                    continue
                image_id = str(image.get("id", ""))
                if not image_id:
                    continue
                target = {
                    "image_id": image_id,
                    "sequence_id": str(sequence_id),
                    "latitude": float(coordinates[1]),
                    "longitude": float(coordinates[0]),
                }
                if not any(item["image_id"] == image_id for item in cached):
                    cached.append(target)
                selected.append(target)
                seen_sequences.add(str(sequence_id))
                if len(selected) == ROUND_COUNT:
                    break

        if len(selected) < ROUND_COUNT:
            raise ValueError(
                "Mapillary n’a pas trouvé assez de séquences navigables dans cette zone. Réessayez."
            )

        targets = [
            ("Lieu de la photo", "", region, item["latitude"], item["longitude"])
            for item in selected
        ]
        return targets, [item["image_id"] for item in selected]

    def create_solo(
        self, player_id: str, player_name: str, region: str = "world", variant: str = "cities",
    ) -> GeoGuessrGame:
        region = validate_region(region)
        if variant not in GEOGUESSR_VARIANTS:
            raise ValueError("Choisissez un mode GeoGuessr valide.")
        image_ids: List[str] = []
        panorama_provider: Optional[str] = None
        if variant == "panorama":
            cities, image_ids, panorama_provider = self._get_panorama_targets(
                region,
                reserve_google_views=True,
            )
        else:
            pool = _city_pool(region)
            cities = random.sample(pool, k=min(ROUND_COUNT, len(pool)))
        with self.lock:
            game = GeoGuessrGame(
                str(uuid.uuid4()), player_id, player_name.strip()[:24], region,
                cities, variant, image_ids, panorama_provider,
            )
            self.solo_games[game.game_id] = game
            return game

    def get_solo(self, game_id: str, player_id: str) -> GeoGuessrGame:
        with self.lock:
            game = self.solo_games.get(game_id)
            if not game or game.player_id != player_id:
                raise KeyError("Partie introuvable.")
            return game

    def guess_solo(
        self, game_id: str, player_id: str, latitude: float, longitude: float,
    ) -> tuple[GeoGuessrGame, Dict[str, Any]]:
        with self.lock:
            game = self.get_solo(game_id, player_id)
            if game.status != "playing":
                raise ValueError("Cette partie est déjà terminée.")
            result = _score_guess(game.target, latitude, longitude)
            result["guess_latitude"] = latitude
            result["guess_longitude"] = longitude
            result.update(_public_city(game.target))
            result["round_number"] = game.round_index + 1
            game.results.append(result)
            game.total_score += result["score"]
            game.round_index += 1
            if game.round_index == ROUND_COUNT:
                game.status = "finished"
            return game, result

    def create_room(
        self, player_id: str, player_name: str, region: str = "world", variant: str = "cities",
    ) -> GeoGuessrRoom:
        region = validate_region(region)
        if variant not in GEOGUESSR_VARIANTS:
            raise ValueError("Choisissez un mode GeoGuessr valide.")
        image_ids: List[str] = []
        panorama_provider: Optional[str] = None
        if variant == "panorama":
            cities, image_ids, panorama_provider = self._get_panorama_targets(
                region,
                reserve_google_views=False,
            )
        else:
            pool = _city_pool(region)
            cities = random.sample(pool, k=min(ROUND_COUNT, len(pool)))
        with self.lock:
            room_id = uuid.uuid4().hex[:6].upper()
            room = GeoGuessrRoom(
                room_id,
                player_id,
                region,
                cities,
                variant,
                image_ids,
                panorama_provider,
            )
            room.players[player_id] = GeoGuessrRoomPlayer(player_id, player_name.strip()[:24])
            self.rooms[room_id] = room
            return room

    def join_room(self, room_id: str, player_id: str, player_name: str) -> GeoGuessrRoom:
        with self.lock:
            room = self.rooms.get(room_id.strip().upper())
            if not room:
                raise KeyError("Salon introuvable.")
            if player_id in room.players:
                room.players[player_id].connected = True
                return room
            if room.status != "lobby":
                raise ValueError("Cette partie a déjà commencé.")
            if len(room.players) >= MAX_PLAYERS:
                raise ValueError("Ce salon est complet.")
            room.players[player_id] = GeoGuessrRoomPlayer(player_id, player_name.strip()[:24])
            return room

    def start_room(self, room_id: str, player_id: str) -> GeoGuessrRoom:
        with self.lock:
            room = self._get_room(room_id, player_id)
            if room.host_player_id != player_id:
                raise PermissionError("Seul l'hôte peut démarrer la partie.")
            if room.status != "lobby":
                raise ValueError("Cette partie a déjà commencé.")
            if len(room.players) < 2:
                raise ValueError("Il faut au moins deux joueurs pour démarrer.")
            if room.variant == "panorama" and room.panorama_provider == "google":
                required_views = ROUND_COUNT * len(room.players)
                try:
                    reserved = self.google_usage_reserver(
                        required_views,
                        GOOGLE_STREETVIEW_MONTHLY_LIMIT,
                    )
                except Exception as exc:
                    logger.warning(
                        "Réservation Google impossible, repli sur Mapillary : %s",
                        exc,
                    )
                    reserved = False
                if not reserved:
                    room.cities, room.image_ids = self._get_mapillary_targets(room.region)
                    room.panorama_provider = "mapillary"
            room.status = "playing"
            room.started_at = time.time()
            return room

    def authorize_google_view(
        self,
        player_id: str,
        *,
        game_id: Optional[str] = None,
        room_id: Optional[str] = None,
        navigation: bool = False,
    ) -> bool:
        with self.lock:
            if game_id:
                game = self.get_solo(game_id, player_id)
                if (
                    game.status != "playing"
                    or game.variant != "panorama"
                    or game.panorama_provider != "google"
                ):
                    raise ValueError("Cette partie n’utilise pas Google Street View.")
                viewed_rounds = game.google_viewed_rounds
                round_index = game.round_index
            elif room_id:
                room = self._get_room(room_id, player_id)
                if (
                    room.status != "playing"
                    or room.variant != "panorama"
                    or room.panorama_provider != "google"
                ):
                    raise ValueError("Ce salon n’utilise pas Google Street View.")
                viewed_rounds = room.google_viewed_rounds
                round_index = room.round_index
            else:
                raise ValueError("Une partie solo ou un salon est requis.")

            round_key = (player_id, round_index)
            if navigation or round_key in viewed_rounds:
                return self.google_usage_reserver(
                    1,
                    GOOGLE_STREETVIEW_MONTHLY_LIMIT,
                )
            viewed_rounds.add(round_key)
            return True

    def guess_room(
        self, room_id: str, player_id: str, latitude: float, longitude: float,
    ) -> tuple[GeoGuessrRoom, Optional[Dict[str, Any]]]:
        with self.lock:
            room = self._get_room(room_id, player_id)
            if room.status != "playing":
                raise ValueError("La partie n'accepte pas de réponse pour le moment.")
            player = room.players[player_id]
            if player.guess is not None:
                raise ValueError("Votre position est déjà validée pour cette manche.")
            player.guess = _score_guess(room.target, latitude, longitude)
            if not all(item.guess is not None for item in room.players.values()):
                return room, None

            scores = []
            for item in room.players.values():
                assert item.guess is not None
                item.total_score += item.guess["score"]
                round_result = {
                    "player_id": item.player_id,
                    "name": item.name,
                    **item.guess,
                }
                item.results.append(round_result)
                scores.append(round_result)
            room.last_round = {
                "round_number": room.round_index + 1,
                "target": _public_city(room.target),
                "guesses": scores,
            }
            room.round_index += 1
            if room.round_index == ROUND_COUNT:
                room.status = "finished"
            else:
                for item in room.players.values():
                    item.guess = None
            return room, room.last_round

    def get_room(self, room_id: str, player_id: str) -> GeoGuessrRoom:
        with self.lock:
            return self._get_room(room_id, player_id)

    def list_rooms(self, player_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self.lock:
            result = []
            for room in self.rooms.values():
                if room.status == "finished":
                    continue
                result.append({
                    "room_id": room.room_id,
                    "player_count": len(room.players),
                    "max_players": MAX_PLAYERS,
                    "status": room.status,
                    "region": room.region,
                    "is_member": player_id in room.players if player_id else False,
                })
            return result

    def _get_room(self, room_id: str, player_id: str) -> GeoGuessrRoom:
        room = self.rooms.get(room_id.strip().upper())
        if not room or player_id not in room.players:
            raise KeyError("Salon introuvable.")
        room.players[player_id].connected = True
        return room


geoguessr_manager = GeoGuessrManager()
