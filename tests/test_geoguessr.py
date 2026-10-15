import os
import tempfile
import unittest
from unittest.mock import Mock, patch

import app.database as database
from app.geoguessr import (
    GOOGLE_STREETVIEW_MONTHLY_LIMIT,
    MAX_SCORE_PER_ROUND,
    ROUND_COUNT,
    GeoGuessrManager,
    distance_km,
    score_distance_km,
)


class GeoGuessrTests(unittest.TestCase):
    def setUp(self):
        self.manager = GeoGuessrManager()

    def test_distance_scoring_rewards_closer_guesses(self):
        self.assertEqual(distance_km(48.8566, 2.3522, 48.8566, 2.3522), 0)
        self.assertEqual(score_distance_km(0), MAX_SCORE_PER_ROUND)
        self.assertGreater(score_distance_km(100), score_distance_km(1_000))
        self.assertGreaterEqual(score_distance_km(50_000), 0)

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
                self.assertIsNone(game.to_dict()["target"])
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
        self.assertIsNone(room.to_dict("host")["prompt"])
        with self.assertRaisesRegex(ValueError, "deux joueurs"):
            self.manager.start_room(room.room_id, "host")
        self.manager.join_room(room.room_id, "guest", "Invité")
        self.manager.start_room(room.room_id, "host")

        previous_round_number = 0
        for _ in range(ROUND_COUNT):
            target = room.target
            room, partial_result = self.manager.guess_room(
                room.room_id, "host", target[3], target[4]
            )
            self.assertIsNone(partial_result)
            last_round = room.to_dict("host")["last_round"]
            self.assertEqual(
                last_round["round_number"] if last_round else 0,
                previous_round_number,
            )
            self.assertTrue(room.to_dict("host")["player"]["submitted"])
            room, completed_result = self.manager.guess_room(
                room.room_id, "guest", target[3], target[4]
            )
            self.assertEqual(completed_result["target"]["city"], target[0])
            self.assertEqual(len(completed_result["guesses"]), 2)
            previous_round_number += 1

        self.assertEqual(room.status, "finished")
        self.assertEqual(room.players["host"].total_score, ROUND_COUNT * MAX_SCORE_PER_ROUND)
        self.assertEqual(room.to_dict("guest")["round_number"], ROUND_COUNT)
        with self.assertRaisesRegex(ValueError, "n'accepte pas"):
            self.manager.guess_room(room.room_id, "host", 0, 0)

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
        response = Mock()
        response.ok = True
        response.status_code = 200
        response.json.return_value = {
            "data": [
                {
                    "id": f"image-{index}",
                    "sequence_id": f"sequence-{index}",
                    "geometry": {"coordinates": [-73.9 + index * 0.01, 40.7]},
                    "is_pano": True,
                }
                for index in range(ROUND_COUNT)
            ]
        }
        manager = GeoGuessrManager(mapillary_access_token="test-token")
        with patch("app.geoguessr.requests.get", return_value=response) as get_images:
            game = manager.create_solo("alice", "Alice", "world", "panorama")

        get_images.assert_called_once()
        self.assertEqual(game.to_dict()["variant"], "panorama")
        self.assertIn(game.to_dict()["image_id"], {f"image-{index}" for index in range(ROUND_COUNT)})
        self.assertIsNone(game.to_dict()["target"])
        self.assertNotIn("latitude", game.to_dict())
        self.assertTrue(all(game.image_ids))

        for _ in range(ROUND_COUNT):
            target = game.target
            game, result = manager.guess_solo(game.game_id, "alice", target[3], target[4])
            self.assertEqual(result["score"], MAX_SCORE_PER_ROUND)

        self.assertEqual(game.status, "finished")
        self.assertEqual(game.to_dict()["image_id"], game.image_ids[-1])
        self.assertEqual(game.to_dict()["target"]["latitude"], game.cities[-1][3])

    def test_panorama_room_reuses_same_images_and_requires_mapillary_token(self):
        manager = GeoGuessrManager(mapillary_access_token="test-token")
        images = [
            {
                "image_id": f"image-{index}",
                "sequence_id": f"sequence-{index}",
                "latitude": 48.0 + index / 10,
                "longitude": 2.0 + index / 10,
            }
            for index in range(ROUND_COUNT)
        ]
        manager.photo_cache["france"] = images
        room = manager.create_room("host", "Hôte", "france", "panorama")
        self.assertEqual(room.to_dict("host")["variant"], "panorama")
        self.assertIsNone(room.to_dict("host")["image_id"])
        manager.join_room(room.room_id, "guest", "Invité")
        manager.start_room(room.room_id, "host")
        self.assertIn(room.to_dict("host")["image_id"], room.image_ids)
        self.assertEqual(room.to_dict("host")["image_id"], room.to_dict("guest")["image_id"])

        with self.assertRaisesRegex(ValueError, "MAPILLARY_ACCESS_TOKEN"):
            GeoGuessrManager().create_solo("alice", "Alice", "france", "panorama")

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
        manager.photo_cache["france"] = [
            {
                "image_id": f"mapillary-{index}",
                "sequence_id": f"sequence-{index}",
                "latitude": 48.0 + index / 10,
                "longitude": 2.0 + index / 10,
            }
            for index in range(ROUND_COUNT)
        ]
        with patch("app.geoguessr.requests.get") as get_metadata:
            game = manager.create_solo("alice", "Alice", "france", "panorama")

        get_metadata.assert_not_called()
        self.assertEqual(game.panorama_provider, "mapillary")
        self.assertTrue(game.to_dict()["image_id"].startswith("mapillary-"))

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
        manager.photo_cache["france"] = [
            {
                "image_id": f"mapillary-{index}",
                "sequence_id": f"sequence-{index}",
                "latitude": 48.0 + index / 10,
                "longitude": 2.0 + index / 10,
            }
            for index in range(ROUND_COUNT)
        ]
        room = manager.create_room("host", "Hôte", "france", "panorama")
        manager.join_room(room.room_id, "guest", "Invité")
        manager.start_room(room.room_id, "host")

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
