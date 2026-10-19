import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import app.database as database
from app import main as main_app
from app.main import app
from app.memories import MISMATCH_REVEAL_SECONDS, MemoriesManager


class MemoriesManagerTests(unittest.TestCase):
    def setUp(self):
        self.manager = MemoriesManager()

    def test_solo_game_hides_unseen_cards_and_finishes_with_pair_score(self):
        game = self.manager.create_solo("alice", "Alice", 4)
        public_state = game.to_dict()
        self.assertEqual(len(public_state["cards"]), 16)
        self.assertEqual(public_state["total_pairs"], 8)
        self.assertTrue(all(card["face"] is None for card in public_state["cards"]))

        pair = next(
            (left, right)
            for left in range(len(game.cards))
            for right in range(left + 1, len(game.cards))
            if game.cards[left] == game.cards[right]
        )
        self.manager.flip_solo(game.game_id, "alice", pair[0])
        self.assertEqual(game.to_dict()["cards"][pair[0]]["face"], game.cards[pair[0]])
        self.manager.flip_solo(game.game_id, "alice", pair[1])
        self.assertEqual(game.to_dict()["matched_pairs"], 1)
        self.assertEqual(game.moves, 1)
        self.assertEqual(game.points, 100)
        self.assertEqual(len(game.matched), 2)

    def test_solo_mismatch_stays_visible_then_turns_back_after_delay(self):
        game = self.manager.create_solo("alice", "Alice", 4)
        first = 0
        second = next(index for index, face in enumerate(game.cards) if face != game.cards[first])
        with patch("app.memories.time.time", return_value=100):
            self.manager.flip_solo(game.game_id, "alice", first)
            self.manager.flip_solo(game.game_id, "alice", second)
            state = game.to_dict()
        self.assertEqual(game.pending_mismatch_until, 100 + MISMATCH_REVEAL_SECONDS)
        self.assertEqual(len(state["cards"]), 16)
        self.assertEqual(state["cards"][first]["face"], game.cards[first])
        with patch("app.memories.time.time", return_value=101.0):
            self.assertIsNotNone(game.to_dict()["cards"][first]["face"])
        with patch(
            "app.memories.time.time",
            return_value=100 + MISMATCH_REVEAL_SECONDS + 0.01,
        ):
            self.assertIsNone(game.to_dict()["cards"][first]["face"])
        self.assertEqual(game.moves, 1)

    def test_solo_rejects_invalid_grid_and_duplicate_card_flips(self):
        with self.assertRaises(ValueError):
            self.manager.create_solo("alice", "Alice", 5)
        game = self.manager.create_solo("alice", "Alice", 4)
        self.manager.flip_solo(game.game_id, "alice", 0)
        with self.assertRaisesRegex(ValueError, "déjà retournée"):
            self.manager.flip_solo(game.game_id, "alice", 0)

    def test_multiplayer_requires_every_player_ready_before_start(self):
        room = self.manager.create_room("host", "Hôte", 4)
        with self.assertRaisesRegex(ValueError, "au moins deux joueurs"):
            self.manager.start_room(room.room_id, "host")
        self.manager.join_room(room.room_id, "guest", "Invité")
        self.assertFalse(room.to_dict("host")["can_start"])
        with self.assertRaisesRegex(ValueError, "Tous les joueurs"):
            self.manager.start_room(room.room_id, "host")
        self.manager.set_ready(room.room_id, "host")
        with self.assertRaisesRegex(ValueError, "Tous les joueurs"):
            self.manager.start_room(room.room_id, "host")
        self.manager.set_ready(room.room_id, "guest")
        self.assertTrue(room.to_dict("host")["can_start"])
        self.manager.start_room(room.room_id, "host")
        self.assertEqual(room.status, "playing")
        self.assertEqual(room.turn_index, 0)

    def test_multiplayer_turns_reward_pairs_and_pass_after_a_mismatch(self):
        room = self.manager.create_room("host", "Hôte", 4)
        self.manager.join_room(room.room_id, "guest", "Invité")
        self.manager.set_ready(room.room_id, "host")
        self.manager.set_ready(room.room_id, "guest")
        self.manager.start_room(room.room_id, "host")
        pair = next(
            (left, right)
            for left in range(len(room.cards))
            for right in range(left + 1, len(room.cards))
            if room.cards[left] == room.cards[right]
        )
        self.manager.flip_room(room.room_id, "host", pair[0])
        self.manager.flip_room(room.room_id, "host", pair[1])
        self.assertEqual(room.players["host"].pairs, 1)
        self.assertEqual(room.current_player.player_id, "host")
        self.assertEqual(room.to_dict("guest")["scores"][0]["points"], 100)
        with self.assertRaisesRegex(ValueError, "pas votre tour"):
            self.manager.flip_room(room.room_id, "guest", 0)

        first = next(index for index in range(len(room.cards)) if index not in room.matched)
        first_face = room.cards[first]
        mismatched = next(
            index for index, face in enumerate(room.cards)
            if index not in room.matched and index != first and face != first_face
        )
        wrong_player = "host"
        with patch("app.memories.time.time", return_value=200):
            self.manager.flip_room(room.room_id, wrong_player, first)
            self.manager.flip_room(room.room_id, wrong_player, mismatched)
        self.assertEqual(room.current_player.player_id, "host")
        with patch(
            "app.memories.time.time",
            return_value=200 + MISMATCH_REVEAL_SECONDS + 0.01,
        ):
            self.manager.get_room(room.room_id, "guest")
        self.assertEqual(room.current_player.player_id, "guest")
        self.assertEqual(room.opened, [])

    def test_room_restart_returns_to_lobby_and_requires_fresh_readiness(self):
        room = self.manager.create_room("host", "Hôte", 4)
        self.manager.join_room(room.room_id, "guest", "Invité")
        self.manager.set_ready(room.room_id, "host")
        self.manager.set_ready(room.room_id, "guest")
        self.manager.start_room(room.room_id, "host")
        room.matched.update(range(len(room.cards)))
        room.players["host"].pairs = 8
        room.status = "finished"
        room.winner_ids = ["host"]
        self.manager.restart_room(room.room_id, "host")
        self.assertEqual(room.status, "lobby")
        self.assertEqual(room.match_number, 2)
        self.assertFalse(room.to_dict("host")["can_start"])
        self.assertEqual(len(room.matched), 0)
        self.assertEqual(room.players["host"].pairs, 0)


class MemoriesApiTests(unittest.TestCase):
    def test_solo_and_multiplayer_routes_expose_memories_game(self):
        manager = MemoriesManager()
        with (
            patch.object(main_app, "memories_manager", manager),
            patch.object(main_app, "record_multigame_session_start"),
            patch.object(main_app, "record_user_game_finish"),
            patch.object(main_app, "increment_player_score"),
        ):
            client = TestClient(app)
            page = client.get("/games/memories/")
            self.assertEqual(page.status_code, 200)
            self.assertIn("Jouer en solo", page.text)

            solo = client.post("/api/memories/solo/new", json={
                "player_id": "solo", "player_name": "Solo", "grid_size": 4,
            })
            self.assertEqual(solo.status_code, 200)
            self.assertEqual(solo.json()["total_pairs"], 8)
            self.assertTrue(all(card["face"] is None for card in solo.json()["cards"]))

            room = client.post("/api/memories/room/create", json={
                "player_id": "host", "player_name": "Hôte", "grid_size": 6,
            })
            self.assertEqual(room.status_code, 200)
            room_id = room.json()["room_id"]
            joined = client.post("/api/memories/room/join", json={
                "room_id": room_id, "player_id": "guest", "player_name": "Invité",
            })
            self.assertEqual(joined.status_code, 200)
            for player_id, player_name in (("host", "Hôte"), ("guest", "Invité")):
                ready = client.post("/api/memories/room/ready", json={
                    "room_id": room_id, "player_id": player_id,
                    "player_name": player_name, "ready": True,
                })
                self.assertEqual(ready.status_code, 200)
            started = client.post("/api/memories/room/start", json={
                "room_id": room_id, "player_id": "host", "player_name": "Hôte",
            })
            self.assertEqual(started.status_code, 200)
            self.assertEqual(started.json()["status"], "playing")
            self.assertEqual(started.json()["total_pairs"], 18)

    def test_multiplayer_flips_are_turn_based_and_reject_out_of_turn_calls(self):
        manager = MemoriesManager()
        room = manager.create_room("host", "Hôte", 4)
        manager.join_room(room.room_id, "guest", "Invité")
        manager.set_ready(room.room_id, "host")
        manager.set_ready(room.room_id, "guest")
        manager.start_room(room.room_id, "host")
        with (
            patch.object(main_app, "memories_manager", manager),
            patch.object(main_app, "record_user_game_finish"),
            patch.object(main_app, "increment_player_score"),
        ):
            client = TestClient(app)
            denied = client.post("/api/memories/room/flip", json={
                "room_id": room.room_id, "player_id": "guest",
                "player_name": "Invité", "index": 0,
            })
            self.assertEqual(denied.status_code, 400)
            accepted = client.post("/api/memories/room/flip", json={
                "room_id": room.room_id, "player_id": "host",
                "player_name": "Hôte", "index": 0,
            })
            self.assertEqual(accepted.status_code, 200)
            self.assertEqual(accepted.json()["cards"][0]["face"], room.cards[0])


if __name__ == "__main__":
    unittest.main()
