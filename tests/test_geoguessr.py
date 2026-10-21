import os
import tempfile
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

import app.database as database
from app import main as main_app
from app.geoguessr import (
    CITY_ADDITIONS,
    CITY_LOCATIONS,
    GOOGLE_STREETVIEW_MONTHLY_LIMIT,
    MAX_SCORE_PER_ROUND,
    ROUND_COUNT,
    ROOM_ROUND_TIME_LIMIT_SECONDS,
    GeoGuessrManager,
    _city_pool,
    _diverse_city_order,
    _sample_city_round,
    distance_km,
    score_distance_km,
)
from app.main import app


class GeoGuessrTests(unittest.TestCase):
    def setUp(self):
        self.manager = GeoGuessrManager()

    def _ready_and_start(self, manager, room):
        for player_id, player in room.players.items():
            if not player.is_spectator:
                manager.confirm_room_ready(room.room_id, player_id)
        manager.start_room(room.room_id, room.host_player_id)

    def _confirm_next_round(self, manager, room):
        active_players = [
            player_id for player_id, player in room.players.items()
            if not player.is_spectator
        ]
        for player_id in active_players[:-1]:
            manager.confirm_room_ready(room.room_id, player_id)
            self.assertTrue(room.awaiting_next_round)
        manager.confirm_room_ready(room.room_id, active_players[-1])

    def test_distance_scoring_rewards_closer_guesses(self):
        self.assertEqual(distance_km(48.8566, 2.3522, 48.8566, 2.3522), 0)
        self.assertEqual(score_distance_km(0), MAX_SCORE_PER_ROUND)
        self.assertGreater(score_distance_km(100), score_distance_km(1_000))
        self.assertGreaterEqual(score_distance_km(50_000), 0)

    def test_city_pools_cover_many_city_sizes_and_regions(self):
        self.assertGreaterEqual(len(_city_pool("france")), 90)
        self.assertGreaterEqual(len(_city_pool("europe")), 200)
        self.assertGreaterEqual(len(_city_pool("world")), 350)
        self.assertEqual(len(CITY_LOCATIONS), len(set(CITY_LOCATIONS)))

    def test_city_rounds_spread_targets_across_countries(self):
        for region in ("europe", "world"):
            cities = _sample_city_round(region, ROUND_COUNT)
            self.assertEqual(len(cities), ROUND_COUNT)
            self.assertEqual(len({city[1] for city in cities}), ROUND_COUNT)
        french_cities = _sample_city_round("france", ROUND_COUNT)
        self.assertEqual(len(french_cities), ROUND_COUNT)
        self.assertEqual(len({(city[0], city[1]) for city in french_cities}), ROUND_COUNT)

    def test_solo_games_do_not_repeat_cities_until_the_player_pool_is_used(self):
        first_game = self.manager.create_solo("alice", "Alice", "world")
        second_game = self.manager.create_solo("alice", "Alice", "world")

        first_cities = {(city[0], city[1]) for city in first_game.cities}
        second_cities = {(city[0], city[1]) for city in second_game.cities}
        self.assertFalse(first_cities & second_cities)

    def test_added_city_pools_respect_population_thresholds(self):
        thresholds = {"france": 50_000, "europe": 200_000, "world": 1_000_000}
        for region, threshold in thresholds.items():
            eligible = [
                city for city in CITY_ADDITIONS
                if (region == "world" or city[2] == region
                    or (region == "europe" and city[2] == "france"))
                and city[5] >= threshold
                and (
                    region != "europe"
                    or city[2] != "france"
                    or (41 <= city[3] <= 52 and -6 <= city[4] <= 10)
                )
            ]
            pool = {(city[0], city[1]) for city in _city_pool(region)}
            self.assertTrue(eligible, region)
            self.assertTrue(all((city[0], city[1]) in pool for city in eligible))
        european_cities = {city[0] for city in _city_pool("europe")}
        self.assertNotIn("Cayenne", european_cities)
        self.assertNotIn("Saint-Denis (La Réunion)", european_cities)

    def test_panorama_city_order_avoids_repeats_and_spreads_countries(self):
        for region in ("france", "europe", "world"):
            ordered = _diverse_city_order(region)
            unique_countries = len({city[1] for city in ordered})
            first_batch_size = min(20, unique_countries)
            self.assertEqual(
                len({city[1] for city in ordered[:first_batch_size]}),
                first_batch_size,
                region,
            )
            city_keys = [(city[0], city[1]) for city in ordered]
            self.assertEqual(len(city_keys), len(set(city_keys)), region)
        world_opening = _diverse_city_order("world")[:5]
        self.assertEqual(len({city[1] for city in world_opening}), 5)
        self.assertGreater(
            min(
                distance_km(first[3], first[4], second[3], second[4])
                for index, first in enumerate(world_opening)
                for second in world_opening[index + 1:]
            ),
            1_000,
        )

    def test_solo_rounds_hide_coordinates_until_guess_and_can_be_resumed(self):
        game = self.manager.create_solo("alice", "Alice", "france")
        self.assertEqual(game.region, "france")
        self.assertIsNone(game.to_dict()["target"])
        self.assertIsNotNone(game.to_dict()["prompt"])

        first_target = game.target
        resumed = self.manager.get_solo(game.game_id, "alice")
        self.assertEqual(resumed.to_dict()["round_number"], 1)
        self.assertEqual(resumed.to_dict()["target"], None)

        for round_number in range(ROUND_COUNT):
            target = game.target
            guess_latitude = target[3] + 0.01
            guess_longitude = target[4] + 0.01
            game, result = self.manager.guess_solo(
                game.game_id, "alice", guess_latitude, guess_longitude
            )
            self.assertLess(result["score"], MAX_SCORE_PER_ROUND)
            self.assertEqual(result["guess_latitude"], guess_latitude)
            self.assertEqual(result["guess_longitude"], guess_longitude)
            self.assertEqual(result["round_number"], round_number + 1)
            self.assertEqual(result["city"], target[0])
            self.assertEqual(game.to_dict()["last_result"]["city"], target[0])
            if round_number < ROUND_COUNT - 1:
                self.assertEqual(game.status, "playing")
                self.assertTrue(game.to_dict()["awaiting_next_round"])
                self.assertIsNone(game.to_dict()["target"])
                self.assertIsNone(game.to_dict()["prompt"])
                self.assertEqual(game.to_dict()["round_number"], round_number + 1)
                with self.assertRaisesRegex(ValueError, "résultat"):
                    self.manager.guess_solo(game.game_id, "alice", 0, 0)
                game = self.manager.next_solo_round(game.game_id, "alice")
                next_city = game.cities[game.round_index]
                self.assertFalse(game.to_dict()["awaiting_next_round"])
                self.assertEqual(
                    game.to_dict()["prompt"],
                    {"city": next_city[0], "country": next_city[1]},
                )
            else:
                self.assertEqual(game.status, "finished")
                self.assertEqual(game.to_dict()["target"]["city"], target[0])

        self.assertGreater(game.total_score, 0)
        self.assertLess(game.total_score, ROUND_COUNT * MAX_SCORE_PER_ROUND)
        self.assertEqual(game.results[0]["city"], first_target[0])
        with self.assertRaisesRegex(ValueError, "terminée"):
            self.manager.guess_solo(game.game_id, "alice", 0, 0)
        with self.assertRaises(KeyError):
            self.manager.get_solo(game.game_id, "bob")

    def test_multiplayer_rounds_share_target_and_reveal_only_after_all_guesses(self):
        room = self.manager.create_room("host", "Hôte", "europe")
        self.assertEqual(room.round_count, ROUND_COUNT)
        self.assertEqual(
            room.to_dict("host")["round_time_limit_seconds"],
            ROOM_ROUND_TIME_LIMIT_SECONDS,
        )
        self.assertIsNone(room.to_dict("host")["prompt"])
        with self.assertRaisesRegex(ValueError, "deux joueurs"):
            self.manager.start_room(room.room_id, "host")
        self.manager.join_room(room.room_id, "guest", "Invité")
        self.assertFalse(room.to_dict("host")["can_start"])
        with self.assertRaisesRegex(ValueError, "prêts"):
            self.manager.start_room(room.room_id, "host")
        self.manager.confirm_room_ready(room.room_id, "host")
        self.assertFalse(room.to_dict("host")["can_start"])
        self.manager.confirm_room_ready(room.room_id, "guest")
        self.assertTrue(room.to_dict("host")["can_start"])
        self.manager.start_room(room.room_id, "host")

        for round_number in range(ROUND_COUNT):
            target = room.target
            room, partial_result = self.manager.guess_room(
                room.room_id, "host", target[3], target[4]
            )
            self.assertIsNone(partial_result)
            self.assertIsNone(room.to_dict("host")["last_round"])
            self.assertTrue(room.to_dict("host")["player"]["submitted"])
            room, completed_result = self.manager.guess_room(
                room.room_id, "guest", target[3], target[4]
            )
            self.assertEqual(completed_result["target"]["city"], target[0])
            self.assertEqual(completed_result["round_number"], round_number + 1)
            self.assertEqual(len(completed_result["guesses"]), 2)
            self.assertIsNone(room.round_deadline)
            self.assertEqual(room.awaiting_next_round, round_number < ROUND_COUNT - 1)
            if round_number < ROUND_COUNT - 1:
                self.assertEqual(room.round_index, round_number)
                with self.assertRaisesRegex(ValueError, "manche précédente"):
                    self.manager.guess_room(
                        room.room_id, "host", target[3], target[4]
                    )
                self._confirm_next_round(self.manager, room)

        self.assertEqual(room.status, "finished")
        self.assertEqual(room.players["host"].total_score, ROUND_COUNT * MAX_SCORE_PER_ROUND)
        self.assertEqual(room.to_dict("guest")["round_number"], ROUND_COUNT)
        with self.assertRaisesRegex(ValueError, "n'accepte pas"):
            self.manager.guess_room(room.room_id, "host", 0, 0)

    def test_multiplayer_readiness_and_round_confirmation_api(self):
        with (
            patch.object(main_app, "geoguessr_manager", self.manager),
            patch.object(main_app, "record_multigame_session_start"),
        ):
            client = TestClient(app)
            created = client.post("/api/geoguessr/room/create", json={
                "player_id": "host",
                "player_name": "Hôte",
                "region": "france",
                "variant": "cities",
                "round_count": 2,
            })
            self.assertEqual(created.status_code, 200)
            room_id = created.json()["room_id"]
            joined = client.post("/api/geoguessr/room/join", json={
                "room_id": room_id,
                "player_id": "guest",
                "player_name": "Invité",
            })
            self.assertEqual(joined.status_code, 200)

            start = client.post("/api/geoguessr/room/start", json={
                "room_id": room_id, "player_id": "host", "player_name": "Hôte",
            })
            self.assertEqual(start.status_code, 400)

            ready_path = "/api/geoguessr/room/ready"
            for player_id, player_name in (("host", "Hôte"), ("guest", "Invité")):
                ready = client.post(ready_path, json={
                    "room_id": room_id, "player_id": player_id,
                    "player_name": player_name,
                })
                self.assertEqual(ready.status_code, 200)
            started = client.post("/api/geoguessr/room/start", json={
                "room_id": room_id, "player_id": "host", "player_name": "Hôte",
            })
            self.assertEqual(started.status_code, 200)

            target = self.manager.rooms[room_id].target
            for player_id, player_name in (("host", "Hôte"), ("guest", "Invité")):
                guess = client.post("/api/geoguessr/room/guess", json={
                    "room_id": room_id,
                    "player_id": player_id,
                    "player_name": player_name,
                    "latitude": target[3],
                    "longitude": target[4],
                })
                self.assertEqual(guess.status_code, 200)
            result = guess.json()
            self.assertTrue(result["awaiting_next_round"])
            self.assertEqual(len(result["last_round"]["guesses"]), 2)
            self.assertTrue(all("distance_km" in item for item in result["last_round"]["guesses"]))

            first_ready = client.post(ready_path, json={
                "room_id": room_id, "player_id": "host", "player_name": "Hôte",
            })
            self.assertTrue(first_ready.json()["awaiting_next_round"])
            second_ready = client.post(ready_path, json={
                "room_id": room_id, "player_id": "guest", "player_name": "Invité",
            })
            self.assertFalse(second_ready.json()["awaiting_next_round"])
            self.assertEqual(second_ready.json()["round_number"], 2)

    def test_solo_round_confirmation_api_reveals_result_before_advancing(self):
        with (
            patch.object(main_app, "geoguessr_manager", self.manager),
            patch.object(main_app, "record_multigame_session_start"),
            patch.object(main_app, "record_user_game_finish"),
            patch.object(main_app, "increment_player_score"),
        ):
            client = TestClient(app)
            created = client.post("/api/geoguessr/solo/new", json={
                "player_id": "alice",
                "player_name": "Alice",
                "region": "france",
                "variant": "cities",
            })
            self.assertEqual(created.status_code, 200)
            game_id = created.json()["game_id"]
            target = self.manager.get_solo(game_id, "alice").target
            guessed = client.post("/api/geoguessr/solo/guess", json={
                "game_id": game_id,
                "player_id": "alice",
                "player_name": "Alice",
                "region": "france",
                "latitude": target[3] + 1,
                "longitude": target[4] + 1,
            })
            self.assertEqual(guessed.status_code, 200)
            self.assertTrue(guessed.json()["awaiting_next_round"])
            self.assertEqual(guessed.json()["last_result"]["city"], target[0])
            self.assertEqual(guessed.json()["last_result"]["round_number"], 1)
            self.assertEqual(guessed.json()["round_number"], 1)

            next_round = client.post("/api/geoguessr/solo/next", json={
                "game_id": game_id,
                "player_id": "alice",
            })
            self.assertEqual(next_round.status_code, 200)
            self.assertFalse(next_round.json()["awaiting_next_round"])
            self.assertEqual(next_round.json()["round_number"], 2)

    def test_google_config_reports_key_presence_without_exposing_server_key(self):
        manager = GeoGuessrManager(
            google_maps_browser_api_key="test-browser-key",
            google_maps_server_api_key="test-server-key",
            google_usage_reader=Mock(return_value=0),
        )
        with patch.object(main_app, "geoguessr_manager", manager):
            response = TestClient(app).get("/api/geoguessr/config")

        self.assertEqual(response.status_code, 200)
        config = response.json()
        self.assertTrue(config["google_maps_browser_key_configured"])
        self.assertTrue(config["google_maps_server_key_configured"])
        self.assertEqual(config["google_maps_browser_api_key"], "test-browser-key")
        self.assertNotIn("test-server-key", response.text)

    def test_joining_during_a_round_spectates_until_the_next_round(self):
        room = self.manager.create_room("host", "Hôte", "france", round_count=2)
        self.manager.join_room(room.room_id, "guest", "Invité")
        self._ready_and_start(self.manager, room)
        spectator = self.manager.join_room(room.room_id, "viewer", "Observateur")

        state = spectator.to_dict("viewer")
        self.assertTrue(state["player"]["is_spectator"])
        self.assertEqual(state["player_count"], 2)
        self.assertEqual(state["spectator_count"], 1)
        with self.assertRaisesRegex(ValueError, "spectateur"):
            self.manager.guess_room(room.room_id, "viewer", 0, 0)

        target = room.target
        for player_id in ("host", "guest"):
            self.manager.guess_room(room.room_id, player_id, target[3], target[4])

        self.assertTrue(room.awaiting_next_round)
        self.assertTrue(room.players["viewer"].is_spectator)
        self._confirm_next_round(self.manager, room)
        self.assertFalse(room.players["viewer"].is_spectator)
        self.assertEqual(room.round_index, 1)
        self.assertIsNone(room.players["viewer"].guess)
        self.manager.guess_room(room.room_id, "viewer", room.target[3], room.target[4])

    def test_active_panorama_room_does_not_expose_its_city_prompt(self):
        room = self.manager.create_room("host", "Hôte", "france")
        room.variant = "panorama"
        room.status = "playing"

        self.assertIsNone(room.to_dict("host")["prompt"])

    def test_spectator_in_final_round_is_promoted_when_host_restarts(self):
        room = self.manager.create_room("host", "Hôte", "france", round_count=1)
        self.manager.join_room(room.room_id, "guest", "Invité")
        self._ready_and_start(self.manager, room)
        self.manager.join_room(room.room_id, "viewer", "Observateur")
        target = room.target
        for player_id in ("host", "guest"):
            self.manager.guess_room(room.room_id, player_id, target[3], target[4])

        self.assertEqual(room.status, "finished")
        self.assertTrue(room.players["viewer"].is_spectator)
        room = self.manager.restart_room(room.room_id, "host")
        self.assertFalse(room.players["viewer"].is_spectator)
        self.assertEqual(room.to_dict("viewer")["player_count"], 3)

    def test_multiplayer_room_round_count_is_configurable_and_bounded(self):
        room = self.manager.create_room("host", "Hôte", "france", round_count=1)
        self.assertEqual(room.round_count, 1)
        self.assertEqual(room.to_dict("host")["round_count"], 1)
        self.assertEqual(
            self.manager.list_rooms("host")[0]["round_count"],
            1,
        )
        for round_count in (0, 21, True):
            with self.subTest(round_count=round_count), self.assertRaises(ValueError):
                self.manager.create_room(
                    "host", "Hôte", "france", round_count=round_count
                )

    def test_multiplayer_round_timeout_starts_on_first_guess_and_marks_missed_players(self):
        with patch("app.geoguessr.time.time", return_value=100):
            room = self.manager.create_room("host", "Hôte", "france", round_count=2)
            self.manager.join_room(room.room_id, "guest", "Invité")
            self._ready_and_start(self.manager, room)
            target = room.target
            room, result = self.manager.guess_room(
                room.room_id, "host", target[3], target[4]
            )

        self.assertIsNone(result)
        self.assertEqual(room.round_deadline, 100 + ROOM_ROUND_TIME_LIMIT_SECONDS)
        self.assertEqual(
            room.to_dict("guest")["round_deadline"],
            100 + ROOM_ROUND_TIME_LIMIT_SECONDS,
        )
        with patch("app.geoguessr.time.time", return_value=119):
            self.manager.get_room(room.room_id, "guest")
        self.assertEqual(room.round_index, 0)

        with patch("app.geoguessr.time.time", return_value=121):
            self.manager.get_room(room.room_id, "guest")
        self.assertEqual(room.round_index, 0)
        self.assertTrue(room.awaiting_next_round)
        self.assertEqual(room.status, "playing")
        self.assertIsNone(room.round_deadline)
        self.assertEqual(room.last_round["missed_players"], ["Invité"])
        self.assertEqual([guess["name"] for guess in room.last_round["guesses"]], ["Hôte"])
        self.assertEqual(room.players["host"].results[0]["score"], MAX_SCORE_PER_ROUND)
        self.assertEqual(room.players["guest"].total_score, 0)
        self._confirm_next_round(self.manager, room)
        self.assertEqual(room.round_index, 1)

    def test_finished_room_can_be_replayed_by_host_with_a_fresh_scoreboard(self):
        room = self.manager.create_room("host", "Hôte", "france")
        self.manager.join_room(room.room_id, "guest", "Invité")
        self._ready_and_start(self.manager, room)
        for round_index in range(ROUND_COUNT):
            target = room.target
            for player_id in ("host", "guest"):
                room, _ = self.manager.guess_room(
                    room.room_id, player_id, target[3], target[4]
                )
            if round_index < ROUND_COUNT - 1:
                self._confirm_next_round(self.manager, room)

        self.assertEqual(room.status, "finished")
        with self.assertRaises(PermissionError):
            self.manager.restart_room(room.room_id, "guest")

        room = self.manager.restart_room(room.room_id, "host")
        self.assertEqual(room.status, "playing")
        self.assertEqual(room.round_index, 0)
        self.assertEqual(room.match_number, 2)
        self.assertIsNone(room.last_round)
        self.assertEqual(room.to_dict("host")["round_number"], 1)
        for player in room.players.values():
            self.assertEqual(player.total_score, 0)
            self.assertEqual(player.results, [])
            self.assertIsNone(player.guess)

    def test_rooms_are_independent_and_invalid_region_is_rejected(self):
        first = self.manager.create_room("alice", "Alice", "france")
        second = self.manager.create_room("bob", "Bob", "world")
        self.assertNotEqual(first.room_id, second.room_id)
        self.assertEqual(
            {room["region"] for room in self.manager.list_rooms("visitor")},
            {"france", "world"},
        )
        with self.assertRaisesRegex(ValueError, "zone valide"):
            self.manager.create_solo("alice", "Alice", "north-america")

    def test_panorama_mode_uses_navigable_mapillary_images_and_hides_target(self):
        responses = []
        for index in range(ROUND_COUNT):
            response = Mock()
            response.ok = True
            response.status_code = 200
            response.json.return_value = {
                "data": [{
                    "id": f"image-{index}",
                    "sequence_id": f"sequence-{index}",
                    "geometry": {"coordinates": [-73.9 + index * 0.01, 40.7]},
                    "is_pano": True,
                }]
            }
            responses.append(response)
        manager = GeoGuessrManager(mapillary_access_token="test-token")
        with patch("app.geoguessr.requests.get", side_effect=responses) as get_images:
            game = manager.create_solo("alice", "Alice", "world", "panorama")

        self.assertEqual(get_images.call_count, ROUND_COUNT)
        selected_images = manager.photo_cache["world"]
        self.assertEqual(
            len({image["source_city_name"] for image in selected_images}),
            ROUND_COUNT,
        )
        self.assertEqual(
            len({image["source_country"] for image in selected_images}),
            ROUND_COUNT,
        )
        self.assertEqual(game.to_dict()["variant"], "panorama")
        self.assertIn(game.to_dict()["image_id"], {f"image-{index}" for index in range(ROUND_COUNT)})
        self.assertIsNone(game.to_dict()["target"])
        self.assertNotIn("latitude", game.to_dict())
        self.assertTrue(all(game.image_ids))

        for _ in range(ROUND_COUNT):
            target = game.target
            game, result = manager.guess_solo(game.game_id, "alice", target[3], target[4])
            self.assertEqual(result["score"], MAX_SCORE_PER_ROUND)
            if result["round_number"] < ROUND_COUNT:
                self.assertTrue(game.to_dict()["awaiting_next_round"])
                self.assertEqual(game.to_dict()["image_id"], game.image_ids[game.round_index])
                game = manager.next_solo_round(game.game_id, "alice")

        self.assertEqual(game.status, "finished")
        self.assertEqual(game.to_dict()["image_id"], game.image_ids[-1])
        self.assertEqual(game.to_dict()["target"]["latitude"], game.cities[-1][3])

    def test_panorama_room_reuses_same_images_and_requires_mapillary_token(self):
        manager = GeoGuessrManager(mapillary_access_token="test-token")
        cities = _city_pool("france")[:ROUND_COUNT]
        images = [
            {
                "image_id": f"image-{index}",
                "sequence_id": f"sequence-{index}",
                "latitude": 48.0 + index / 10,
                "longitude": 2.0 + index / 10,
                "source_city_name": cities[index][0],
                "source_country": cities[index][1],
            }
            for index in range(ROUND_COUNT)
        ]
        manager.photo_cache["france"] = images
        room = manager.create_room("host", "Hôte", "france", "panorama")
        self.assertEqual(room.to_dict("host")["variant"], "panorama")
        self.assertIsNone(room.to_dict("host")["image_id"])
        manager.join_room(room.room_id, "guest", "Invité")
        self._ready_and_start(manager, room)
        self.assertIn(room.to_dict("host")["image_id"], room.image_ids)
        self.assertEqual(room.to_dict("host")["image_id"], room.to_dict("guest")["image_id"])

        with self.assertRaisesRegex(ValueError, "MAPILLARY_ACCESS_TOKEN"):
            GeoGuessrManager().create_solo("alice", "Alice", "france", "panorama")

    def test_mapillary_does_not_reuse_cached_photos_in_the_next_game(self):
        responses = []
        for index in range(ROUND_COUNT * 2):
            response = Mock()
            response.ok = True
            response.status_code = 200
            response.json.return_value = {
                "data": [{
                    "id": f"image-{index}",
                    "sequence_id": f"sequence-{index}",
                    "geometry": {"coordinates": [-73.9 + index * 0.01, 40.7]},
                    "is_pano": True,
                }]
            }
            responses.append(response)
        manager = GeoGuessrManager(mapillary_access_token="test-token")
        with patch("app.geoguessr.requests.get", side_effect=responses):
            first_game = manager.create_solo("alice", "Alice", "world", "panorama")
            first_image_ids = set(first_game.image_ids)
            second_game = manager.create_solo("alice", "Alice", "world", "panorama")

        self.assertTrue(first_image_ids.isdisjoint(second_game.image_ids))

    def test_google_street_view_is_selected_and_monthly_views_are_reserved(self):
        responses = []
        for index in range(ROUND_COUNT):
            response = Mock()
            response.ok = True
            response.json.return_value = {
                "status": "OK",
                "pano_id": f"google-pano-{index}",
                "location": {"lat": 48.0 + index / 10, "lng": 2.0 + index / 10},
            }
            responses.append(response)
        reserve = Mock(return_value=True)
        manager = GeoGuessrManager(
            google_maps_server_api_key="test-server-key",
            google_maps_browser_api_key="test-browser-key",
            google_usage_reader=Mock(return_value=0),
            google_usage_reserver=reserve,
        )
        with patch("app.geoguessr.requests.get", side_effect=responses) as get_metadata:
            game = manager.create_solo("alice", "Alice", "france", "panorama")

        self.assertEqual(game.panorama_provider, "google")
        self.assertIn(game.to_dict()["image_id"], {f"google-pano-{i}" for i in range(ROUND_COUNT)})
        self.assertNotIn("latitude", game.to_dict())
        self.assertEqual(get_metadata.call_count, ROUND_COUNT)
        self.assertTrue(all(
            call.kwargs["params"]["source"] == "outdoor"
            for call in get_metadata.call_args_list
        ))
        reserve.assert_called_once_with(ROUND_COUNT, GOOGLE_STREETVIEW_MONTHLY_LIMIT)
        self.assertTrue(manager.authorize_google_view("alice", game_id=game.game_id))
        reserve.assert_called_once_with(ROUND_COUNT, GOOGLE_STREETVIEW_MONTHLY_LIMIT)
        self.assertTrue(manager.authorize_google_view("alice", game_id=game.game_id))
        self.assertEqual(
            reserve.call_args_list[-1].args,
            (1, GOOGLE_STREETVIEW_MONTHLY_LIMIT),
        )

    def test_google_quota_near_limit_falls_back_to_mapillary(self):
        manager = GeoGuessrManager(
            mapillary_access_token="test-mapillary-token",
            google_maps_server_api_key="test-server-key",
            google_maps_browser_api_key="test-browser-key",
            google_usage_reader=Mock(return_value=GOOGLE_STREETVIEW_MONTHLY_LIMIT - 4),
        )
        cities = _city_pool("france")[:ROUND_COUNT]
        manager.photo_cache["france"] = [
            {
                "image_id": f"mapillary-{index}",
                "sequence_id": f"sequence-{index}",
                "latitude": 48.0 + index / 10,
                "longitude": 2.0 + index / 10,
                "source_city_name": cities[index][0],
                "source_country": cities[index][1],
            }
            for index in range(ROUND_COUNT)
        ]
        with patch("app.geoguessr.requests.get") as get_metadata:
            game = manager.create_solo("alice", "Alice", "france", "panorama")

        get_metadata.assert_not_called()
        self.assertEqual(game.panorama_provider, "mapillary")
        self.assertTrue(game.to_dict()["image_id"].startswith("mapillary-"))

    def test_google_key_rejection_is_reported_when_no_mapillary_fallback_exists(self):
        response = Mock()
        response.ok = True
        response.json.return_value = {
            "status": "REQUEST_DENIED",
            "error_message": "The provided API key is invalid.",
        }
        manager = GeoGuessrManager(
            google_maps_server_api_key="test-server-key",
            google_maps_browser_api_key="test-browser-key",
            google_usage_reader=Mock(return_value=0),
        )
        with (
            patch("app.geoguessr.requests.get", return_value=response),
            self.assertRaisesRegex(ValueError, "Street View a refusé la clé serveur"),
        ):
            manager.create_solo("alice", "Alice", "france", "panorama")

    def test_google_multiplayer_room_reserves_for_all_players_or_uses_mapillary(self):
        manager = GeoGuessrManager(
            mapillary_access_token="test-mapillary-token",
            google_maps_server_api_key="test-server-key",
            google_maps_browser_api_key="test-browser-key",
            google_usage_reader=Mock(return_value=0),
            google_usage_reserver=Mock(return_value=False),
        )
        manager._get_google_targets = Mock(return_value=(
            [
                ("Lieu de la photo", "", "france", 48.0 + index / 10, 2.0)
                for index in range(ROUND_COUNT)
            ],
            [f"google-{index}" for index in range(ROUND_COUNT)],
        ))
        cities = _city_pool("france")[:ROUND_COUNT]
        manager.photo_cache["france"] = [
            {
                "image_id": f"mapillary-{index}",
                "sequence_id": f"sequence-{index}",
                "latitude": 48.0 + index / 10,
                "longitude": 2.0 + index / 10,
                "source_city_name": cities[index][0],
                "source_country": cities[index][1],
            }
            for index in range(ROUND_COUNT)
        ]
        room = manager.create_room("host", "Hôte", "france", "panorama")
        manager.join_room(room.room_id, "guest", "Invité")
        self._ready_and_start(manager, room)

        self.assertEqual(
            manager.google_usage_reserver.call_args.args,
            (ROUND_COUNT * 2, GOOGLE_STREETVIEW_MONTHLY_LIMIT),
        )
        self.assertEqual(room.panorama_provider, "mapillary")
        self.assertTrue(room.to_dict("guest")["image_id"].startswith("mapillary-"))

    def test_google_panorama_navigation_is_metered_and_rejects_the_monthly_limit(self):
        reserve = Mock(side_effect=[True, False])
        responses = []
        for index in range(ROUND_COUNT):
            response = Mock()
            response.ok = True
            response.json.return_value = {
                "status": "OK",
                "pano_id": f"google-pano-{index}",
                "location": {"lat": 48.0 + index / 10, "lng": 2.0 + index / 10},
            }
            responses.append(response)
        manager = GeoGuessrManager(
            google_maps_server_api_key="test-server-key",
            google_maps_browser_api_key="test-browser-key",
            google_usage_reader=Mock(return_value=0),
            google_usage_reserver=reserve,
        )
        with patch("app.geoguessr.requests.get", side_effect=responses):
            game = manager.create_solo("alice", "Alice", "france", "panorama")

        self.assertTrue(manager.authorize_google_view("alice", game_id=game.game_id))
        self.assertFalse(manager.authorize_google_view(
            "alice", game_id=game.game_id, navigation=True
        ))
        self.assertEqual(reserve.call_args_list[-1].args, (1, GOOGLE_STREETVIEW_MONTHLY_LIMIT))

    def test_google_usage_reservations_are_atomic_and_capped(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = os.path.join(temporary_directory, "usage.sqlite")
            with (
                patch.object(database, "DB_PATH", database_path),
                patch.object(database, "IS_POSTGRES", False),
            ):
                self.assertTrue(database.init_db())
                self.assertTrue(database.reserve_geoguessr_google_usage(3, 5))
                self.assertTrue(database.reserve_geoguessr_google_usage(2, 5))
                self.assertFalse(database.reserve_geoguessr_google_usage(1, 5))
                self.assertEqual(database.get_geoguessr_google_usage(), 5)


if __name__ == "__main__":
    unittest.main()
