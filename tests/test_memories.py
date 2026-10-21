import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import app.database as database
from app import main as main_app
from app.main import app
from app.memories import CARD_SYMBOLS, MISMATCH_REVEAL_SECONDS, MemoriesManager


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

    def test_solo_elapsed_time_is_captured_when_the_last_pair_is_found(self):
        with patch("app.memories.time.time", return_value=100):
            game = self.manager.create_solo("alice", "Alice", 4)
        game.started_at = 100
        with patch("app.memories.time.time", return_value=102.345):
            for left in range(len(game.cards)):
                if left in game.matched:
                    continue
                right = next(
                    index for index in range(left + 1, len(game.cards))
                    if game.cards[index] == game.cards[left]
                )
                self.manager.flip_solo(game.game_id, "alice", left)
                self.manager.flip_solo(game.game_id, "alice", right)

        state = game.to_dict()
        self.assertEqual(state["status"], "finished")
        self.assertEqual(state["elapsed_ms"], 2345)
        self.assertEqual(state["elapsed_seconds"], 2)

    def test_solo_mismatch_stays_visible_then_turns_back_after_delay(self):
        game = self.manager.create_solo("alice", "Alice", 4)
        first = 0
        second = next(index for index, face in enumerate(game.cards) if face != game.cards[first])
        with patch("app.memories.time.time", return_value=100):
            self.manager.flip_solo(game.game_id, "alice", first)
            self.manager.flip_solo(game.game_id, "alice", second)
            state = game.to_dict()
        self.assertEqual(game.pending_mismatch_until, 100 + MISMATCH_REVEAL_SECONDS)
        self.assertEqual(state["pending_mismatch_remaining_ms"], 1200)
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

    def test_solo_click_on_another_card_cancels_pending_mismatch(self):
        game = self.manager.create_solo("alice", "Alice", 4)
        first = 0
        second = next(
            index for index, face in enumerate(game.cards) if face != game.cards[first]
        )
        third = next(index for index in range(len(game.cards)) if index not in (first, second))
        with patch("app.memories.time.time", return_value=100):
            self.manager.flip_solo(game.game_id, "alice", first)
            self.manager.flip_solo(game.game_id, "alice", second)
        self.assertEqual(game.moves, 1)
        self.assertIsNotNone(game.pending_mismatch_until)

        with patch("app.memories.time.time", return_value=100.5):
            self.manager.flip_solo(game.game_id, "alice", third)
            state = game.to_dict()
            self.assertIsNone(game.pending_mismatch_until)
            self.assertEqual(game.opened, [third])
            self.assertIsNone(state["cards"][first]["face"])
            self.assertIsNone(state["cards"][second]["face"])
            self.assertEqual(state["cards"][third]["face"], game.cards[third])
        self.assertEqual(game.moves, 1)

    def test_solo_click_on_pending_mismatch_card_does_not_cancel_it(self):
        game = self.manager.create_solo("alice", "Alice", 4)
        first = 0
        second = next(
            index for index, face in enumerate(game.cards) if face != game.cards[first]
        )
        with patch("app.memories.time.time", return_value=100):
            self.manager.flip_solo(game.game_id, "alice", first)
            self.manager.flip_solo(game.game_id, "alice", second)

        with patch("app.memories.time.time", return_value=100.5):
            with self.assertRaisesRegex(ValueError, "déjà retournée"):
                self.manager.flip_solo(game.game_id, "alice", first)

        self.assertEqual(game.opened, [first, second])
        self.assertIsNotNone(game.pending_mismatch_until)

    def test_solo_finishes_from_a_valid_local_flip_sequence(self):
        game = self.manager.create_solo("alice", "Alice", 4)
        flips = []
        flipped = set()
        for left in range(len(game.cards)):
            if left in flipped:
                continue
            right = next(
                index for index in range(left + 1, len(game.cards))
                if game.cards[index] == game.cards[left]
            )
            flips.extend((left, right))
            flipped.update((left, right))

        finished = self.manager.finish_solo(
            game.game_id, "alice", flips, elapsed_ms=15_281
        )

        self.assertEqual(finished.status, "finished")
        self.assertEqual(finished.moves, 8)
        self.assertEqual(finished.points, 800)
        self.assertEqual(finished.matched, set(range(16)))
        self.assertEqual(finished.to_dict()["elapsed_ms"], 15_281)

    def test_solo_can_finish_a_client_generated_deck_without_creating_server_game(self):
        deck = list(CARD_SYMBOLS[:8]) * 2
        flips = []
        for symbol in CARD_SYMBOLS[:8]:
            flips.extend(index for index, face in enumerate(deck) if face == symbol)

        finished = self.manager.finish_local_solo(
            "local-game", "alice", "Alice", 4, deck, flips, elapsed_ms=9000
        )

        self.assertEqual(finished.status, "finished")
        self.assertEqual(finished.moves, 8)
        self.assertEqual(finished.to_dict()["elapsed_ms"], 9000)
        self.assertIs(self.manager.get_solo("local-game", "alice"), finished)
        with self.assertRaisesRegex(ValueError, "paires valides"):
            self.manager.finish_local_solo(
                "invalid-game", "alice", "Alice", 4, [CARD_SYMBOLS[0]] * 16,
                flips, elapsed_ms=9000,
            )

    def test_solo_rejects_incomplete_local_flip_sequence_without_mutating_game(self):
        game = self.manager.create_solo("alice", "Alice", 4)

        with self.assertRaisesRegex(ValueError, "ne termine pas"):
            self.manager.finish_solo(game.game_id, "alice", [0, 1], 1000)

        self.assertEqual(game.status, "playing")
        self.assertEqual(game.matched, set())
        self.assertEqual(game.moves, 0)

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
        self.assertEqual(room.to_dict("guest")["status"], "lobby")


class MemoriesApiTests(unittest.TestCase):
    def test_local_solo_result_is_validated_and_saved_without_a_start_request(self):
        manager = MemoriesManager()
        deck = list(CARD_SYMBOLS[:8]) * 2
        flips = [
            index
            for symbol in CARD_SYMBOLS[:8]
            for index, face in enumerate(deck)
            if face == symbol
        ]
        with (
            patch.object(main_app, "memories_manager", manager),
            patch.object(main_app, "record_multigame_session_start"),
            patch.object(main_app, "record_memory_solo_time", return_value={
                "username": "Solo", "elapsed_ms": 9000, "moves": 8,
                "is_record": True,
            }) as save_record,
            patch.object(main_app, "record_user_game_finish"),
            patch.object(main_app, "increment_player_score"),
        ):
            client = TestClient(app)
            result = client.post("/api/memories/solo/finish", json={
                "game_id": "local-game",
                "player_id": "solo",
                "player_name": "Solo",
                "grid_size": 4,
                "deck": deck,
                "flips": flips,
                "elapsed_ms": 9000,
            })
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json()["status"], "finished")
            self.assertTrue(result.json()["result_saved"])
            save_record.assert_called_once_with(
                "Solo", 4, "memories:local-game", 9000, 8
            )
            invalid = client.post("/api/memories/solo/finish", json={
                "game_id": "invalid-game",
                "player_id": "solo",
                "player_name": "Solo",
                "grid_size": 4,
                "deck": [CARD_SYMBOLS[0]] * 16,
                "flips": flips,
                "elapsed_ms": 9000,
            })
            self.assertEqual(invalid.status_code, 400)

    def test_solo_and_multiplayer_routes_expose_memories_game(self):
        manager = MemoriesManager()
        with (
            patch.object(main_app, "memories_manager", manager),
            patch.object(main_app, "record_multigame_session_start"),
            patch.object(main_app, "record_memory_solo_time", return_value={
                "username": "Solo", "elapsed_ms": 15_281, "moves": 8,
                "is_record": True,
            }) as save_record,
            patch.object(main_app, "record_user_game_finish"),
            patch.object(main_app, "increment_player_score"),
        ):
            client = TestClient(app)
            page = client.get("/games/memories/")
            self.assertEqual(page.status_code, 200)
            self.assertIn("Concours solo chronométré", page.text)
            self.assertIn("Meilleurs temps", page.text)
            with patch.object(
                main_app,
                "get_memory_solo_leaderboard",
                return_value=[{"username": "Alice", "elapsed_ms": 12345, "moves": 8}],
            ):
                leaderboard = client.get("/api/memories/solo/leaderboard?grid_size=4")
            self.assertEqual(leaderboard.status_code, 200)
            self.assertEqual(leaderboard.json()["records"][0]["elapsed_ms"], 12345)
            invalid_grid = client.get("/api/memories/solo/leaderboard?grid_size=5")
            self.assertEqual(invalid_grid.status_code, 400)

            solo = client.post("/api/memories/solo/new", json={
                "player_id": "solo", "player_name": "Solo", "grid_size": 4,
            })
            self.assertEqual(solo.status_code, 200)
            self.assertEqual(solo.json()["total_pairs"], 8)
            self.assertTrue(all(card["face"] is None for card in solo.json()["cards"]))
            self.assertEqual(len(solo.json()["deck"]), 16)
            solo_game = manager.get_solo(solo.json()["game_id"], "solo")
            flips = []
            for face in dict.fromkeys(solo_game.cards):
                flips.extend(
                    index for index, card in enumerate(solo_game.cards)
                    if card == face
                )
            result = client.post("/api/memories/solo/finish", json={
                "game_id": solo_game.game_id,
                "player_id": "solo",
                "player_name": "Solo",
                "flips": flips,
                "elapsed_ms": 15_281,
            })
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json()["status"], "finished")
            self.assertEqual(result.json()["elapsed_ms"], 15_281)
            self.assertTrue(result.json()["result_saved"])
            save_record.assert_called_once_with(
                "Solo", 4, f"memories:{solo_game.game_id}", 15_281, 8
            )
            retry = client.post("/api/memories/solo/finish", json={
                "game_id": solo_game.game_id,
                "player_id": "solo",
                "player_name": "Solo",
                "flips": [],
                "elapsed_ms": 15_281,
            })
            self.assertEqual(retry.status_code, 200)
            self.assertTrue(retry.json()["result_saved"])
            save_record.assert_called_once()

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

    def test_finished_solo_game_saves_and_returns_its_timed_record(self):
        manager = MemoriesManager()
        game = manager.create_solo("solo", "Solo", 4)
        game.status = "finished"
        game.started_at = 100
        game.finished_at = 102.345
        game.matched.update(range(len(game.cards)))
        game.moves = 8
        record = {
            "username": "Solo",
            "elapsed_ms": 2345,
            "moves": 8,
            "is_record": True,
        }
        with (
            patch.object(main_app, "memories_manager", manager),
            patch.object(main_app, "record_memory_solo_time", return_value=record) as save_record,
            patch.object(main_app, "record_user_game_finish"),
            patch.object(main_app, "increment_player_score"),
        ):
            response = TestClient(app).get(
                f"/api/memories/solo/{game.game_id}?player_id=solo"
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["record"]["is_record"])
        self.assertEqual(response.json()["elapsed_ms"], 2345)
        self.assertEqual(len(response.json()["deck"]), 16)
        self.assertEqual(save_record.call_args.args[3:], (2345, 8))

    def test_finished_solo_game_remains_resumable_if_record_save_fails(self):
        manager = MemoriesManager()
        game = manager.create_solo("solo", "Solo", 4)
        game.status = "finished"
        game.finished_at = game.started_at + 15.281
        game.matched.update(range(len(game.cards)))
        game.moves = 8
        with (
            patch.object(main_app, "memories_manager", manager),
            patch.object(
                main_app,
                "record_memory_solo_time",
                side_effect=RuntimeError("database unavailable"),
            ),
        ):
            response = TestClient(app).get(
                f"/api/memories/solo/{game.game_id}?player_id=solo"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "finished")
        self.assertEqual(response.json()["record_save_error"], "database unavailable")
        self.assertEqual(len(response.json()["deck"]), 16)
        self.assertFalse(response.json()["result_saved"])


class MemorySoloRecordTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path_patch = patch.object(
            database, "DB_PATH", str(Path(self.temp_dir.name) / "memory.sqlite3")
        )
        self.db_path_patch.start()
        self.pg_disabled_patch = patch.object(database, "_pg_disabled", True)
        self.pg_disabled_patch.start()
        self.assertTrue(database.init_db())

    def tearDown(self):
        self.pg_disabled_patch.stop()
        self.db_path_patch.stop()
        self.temp_dir.cleanup()

    def test_leaderboard_ranks_each_attempt_even_when_one_player_repeats(self):
        first = database.record_memory_solo_time("Alice", 4, "session-1", 12000, 10)
        slower = database.record_memory_solo_time("ALICE", 4, "session-2", 15000, 8)
        tie_break = database.record_memory_solo_time("alice", 4, "session-3", 12000, 9)
        other_grid = database.record_memory_solo_time("Alice", 6, "session-4", 45000, 25)
        database.record_memory_solo_time("Alice", 4, "session-5", 10000, 12)
        database.record_memory_solo_time("Alice", 4, "session-6", 14000, 11)
        database.record_memory_solo_time("Bob", 4, "session-7", 13000, 10)

        self.assertTrue(first["is_record"])
        self.assertFalse(slower["is_record"])
        self.assertTrue(tie_break["is_record"])
        self.assertEqual(tie_break["moves"], 9)
        self.assertTrue(other_grid["is_record"])
        top_five = database.get_memory_solo_leaderboard(4)
        self.assertEqual(len(top_five), 5)
        self.assertEqual(
            [record["elapsed_ms"] for record in top_five],
            [10000, 12000, 12000, 13000, 14000],
        )
        self.assertEqual(
            sum(record["username"].casefold() == "alice" for record in top_five),
            4,
        )
        self.assertEqual(top_five[1]["moves"], 9)
        self.assertEqual(len(database.get_memory_solo_leaderboard(6)), 1)

    def test_existing_personal_records_are_kept_in_the_attempt_leaderboard(self):
        with database.DatabaseContext() as db:
            db.execute(
                """INSERT INTO memory_solo_records
                   (grid_size, username, normalized_username, elapsed_ms, moves, session_id)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (4, "Alice", "alice", 12000, 10, "legacy-session"),
            )
            database._migrate_multigame_schema(db)

        leaderboard = database.get_memory_solo_leaderboard(4)
        self.assertEqual(len(leaderboard), 1)
        self.assertEqual(leaderboard[0]["username"], "Alice")
        self.assertEqual(leaderboard[0]["elapsed_ms"], 12000)

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
