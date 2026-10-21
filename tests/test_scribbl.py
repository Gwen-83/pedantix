import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import main
from app.main import app
from app.scribbl import ScribblManager, TURN_SECONDS, WORD_BANK


class ScribblManagerTests(unittest.TestCase):
    def setUp(self):
        self.manager = ScribblManager()

    def make_room(self, rounds=1):
        room = self.manager.create_room("host", "Hôte", rounds)
        self.manager.join_room(room.room_id, "guest", "Invité")
        return room

    def start_drawing(self, room):
        self.manager.start_room(room.room_id, room.host_player_id)
        self.manager.choose_word(room.room_id, room.host_player_id, 0)
        return room.word

    def test_lobby_requires_two_players_and_hides_word_choices_from_other_players(self):
        room = self.manager.create_room("host", "Hôte")
        with self.assertRaisesRegex(ValueError, "au moins 2"):
            self.manager.start_room(room.room_id, "host")
        self.manager.join_room(room.room_id, "guest", "Invité")
        self.manager.start_room(room.room_id, "host")

        host_state = room.to_dict("host")
        guest_state = room.to_dict("guest")
        self.assertEqual(host_state["phase"], "choosing")
        self.assertEqual(len(host_state["word_choices"]), 3)
        self.assertEqual(guest_state["word_choices"], [])
        self.assertIsNone(guest_state["word"])

    def test_drawing_is_validated_and_broadcast_state_stays_private(self):
        room = self.make_room()
        word = self.start_drawing(room)
        event = self.manager.add_stroke(
            room.room_id, "host", [[0.1, 0.2], [0.3, 0.4]], "#172033", 7, True
        )
        self.assertEqual(event["type"], "draw")
        self.assertEqual(room.to_dict("guest")["word_hint"], " ".join(
            " " if char.isspace() else "_" for char in word
        ))
        self.assertIsNone(room.to_dict("guest")["word"])
        self.assertEqual(len(room.to_dict("guest")["strokes"]), 1)

        with self.assertRaisesRegex(ValueError, "Coordonnée"):
            self.manager.add_stroke(
                room.room_id, "host", [[float("nan"), 0.2]], "#172033", 7, False
            )
        with self.assertRaisesRegex(ValueError, "dessinateur"):
            self.manager.add_stroke(
                room.room_id, "guest", [[0.1, 0.2]], "#172033", 7, True
            )

    def test_correct_guess_awards_more_points_earlier_and_reveals_word(self):
        room = self.make_room()
        word = self.start_drawing(room)
        with patch("app.scribbl.time.time", return_value=room.turn_ends_at - TURN_SECONDS / 2):
            updated, result = self.manager.submit_guess(room.room_id, "guest", word.upper())

        self.assertIs(updated, room)
        self.assertTrue(result["correct"])
        self.assertGreater(result["points"], 100)
        self.assertEqual(room.players["host"].score, round(result["points"] / 2))
        self.assertEqual(room.phase, "reveal")
        self.assertEqual(room.to_dict("guest")["word"], word)

    def test_incorrect_guess_is_visible_and_a_player_cannot_score_twice_in_a_turn(self):
        room = self.make_room()
        word = self.start_drawing(room)
        wrong = next(candidate for candidate in WORD_BANK if candidate != word)
        _, result = self.manager.submit_guess(room.room_id, "guest", wrong)
        self.assertFalse(result["correct"])
        self.assertEqual(room.chat[-1]["text"], wrong)
        self.manager.submit_guess(room.room_id, "guest", word)
        with self.assertRaisesRegex(ValueError, "déjà trouvé"):
            self.manager.submit_guess(room.room_id, "guest", word)

    def test_turn_timeout_reveals_word_then_advances_and_finishes_game(self):
        room = self.make_room(rounds=1)
        self.manager.start_room(room.room_id, "host")
        with patch("app.scribbl.time.time", return_value=room.turn_ends_at + 1):
            self.assertTrue(self.manager.advance_timers(room.room_id))
        self.assertEqual(room.phase, "drawing")
        self.assertIsNotNone(room.word)
        with patch("app.scribbl.time.time", return_value=room.turn_ends_at + 1):
            self.manager.advance_timers(room.room_id)
        self.assertEqual(room.phase, "reveal")
        with patch("app.scribbl.time.time", return_value=room.turn_ends_at + 1):
            self.manager.advance_timers(room.room_id)
        self.assertEqual(room.phase, "choosing")
        self.assertEqual(room.artist_player_id, "guest")
        with patch("app.scribbl.time.time", return_value=room.turn_ends_at + 1):
            self.manager.advance_timers(room.room_id)
        with patch("app.scribbl.time.time", return_value=room.turn_ends_at + 1):
            self.manager.advance_timers(room.room_id)
        with patch("app.scribbl.time.time", return_value=room.turn_ends_at + 1):
            self.manager.advance_timers(room.room_id)
        self.assertEqual(room.status, "finished")

    def test_leaving_host_transfers_host_and_restart_resets_match_scores(self):
        room = self.make_room()
        self.manager.leave_room(room.room_id, "host")
        self.assertEqual(room.host_player_id, "guest")
        room.status = "finished"
        room.phase = "finished"
        room.players["guest"].score = 700
        restarted = self.manager.restart_room(room.room_id, "guest")
        self.assertIs(restarted, room)
        self.assertEqual(room.players["guest"].score, 0)
        self.assertEqual(room.status, "lobby")


class ScribblApiTests(unittest.TestCase):
    def test_page_room_routes_and_websocket_share_realtime_game_state(self):
        manager = ScribblManager()
        with (
            patch.object(main, "scribbl_manager", manager),
            patch.object(main, "record_multigame_session_start"),
            patch.object(main, "record_user_game_finish"),
            patch.object(main, "increment_player_score"),
            TestClient(app) as client,
        ):
            page = client.get("/games/scribbl/")
            self.assertEqual(page.status_code, 200)
            self.assertIn("À vos crayons", page.text)

            created = client.post("/api/scribbl/room/create", json={
                "player_id": "host",
                "player_name": "Hôte",
                "rounds_per_player": 1,
            })
            self.assertEqual(created.status_code, 200)
            room_id = created.json()["room_id"]
            joined = client.post("/api/scribbl/room/join", json={
                "room_id": room_id,
                "player_id": "guest",
                "player_name": "Invité",
            })
            self.assertEqual(joined.status_code, 200)
            self.assertEqual(len(client.get("/api/scribbl/rooms").json()["rooms"]), 1)

            with (
                client.websocket_connect(
                    f"/ws/scribbl/{room_id}?player_id=host"
                ) as host_socket,
                client.websocket_connect(
                    f"/ws/scribbl/{room_id}?player_id=guest"
                ) as guest_socket,
            ):
                self.assertEqual(host_socket.receive_json()["type"], "state")
                self.assertEqual(guest_socket.receive_json()["type"], "state")
                host_socket.send_json({"type": "start"})
                host_state = host_socket.receive_json()["state"]
                guest_socket.receive_json()
                self.assertEqual(host_state["phase"], "choosing")
                host_socket.send_json({"type": "choose", "index": 0})
                host_state = host_socket.receive_json()["state"]
                guest_socket.receive_json()
                self.assertEqual(host_state["phase"], "drawing")
                self.assertIsNotNone(host_state["word"])
                self.assertIsNone(manager.get_room(room_id, "guest").to_dict("guest")["word"])
                host_socket.send_json({
                    "type": "stroke",
                    "start": True,
                    "points": [[0.2, 0.3]],
                    "color": "#172033",
                    "width": 7,
                })
                draw_event = guest_socket.receive_json()
                self.assertEqual(draw_event["type"], "draw")
                self.assertEqual(draw_event["points"], [[0.2, 0.3]])

    def test_store_invitation_creates_a_private_scribbl_room_and_leave_transfers_host(self):
        manager = ScribblManager()
        invitation = {
            "game_id": "scribbl",
            "sender_player_id": "alice-id",
            "recipient_player_id": "bob-id",
            "sender_username": "Alice",
            "recipient_username": "Bob",
        }
        with (
            patch.object(main, "scribbl_manager", manager),
            patch.object(main, "private_store_invitation_rooms", set()),
            patch.dict(
                main.STORE_INVITATION_GAMES,
                {"scribbl": ("Scribbl", manager, "scribbl_player_id")},
            ),
            patch.dict(
                main.STORE_ACTIVE_ROOM_GAMES,
                {"scribbl": ("Scribbl", manager, "scribbl_player_id")},
                clear=True,
            ),
            patch.dict(main.STORE_ROOM_PLAYER_LIMITS, {"scribbl": 8}, clear=True),
        ):
            created = main._create_invitation_room(invitation)
            room = manager.rooms[created["room_id"]]
            self.assertEqual(set(room.players), {"alice-id", "bob-id"})
            self.assertFalse(manager.list_rooms("mallory")[0]["is_member"])
            result = main._leave_store_multiplayer_room(
                "scribbl", room.room_id, "alice-id"
            )
            self.assertEqual(result, {"status": "left"})
            self.assertEqual(room.host_player_id, "bob-id")

    def test_finished_scribbl_match_records_multiplayer_stats(self):
        manager = ScribblManager()
        room = manager.create_room("host", "Hôte")
        manager.join_room(room.room_id, "guest", "Invité")
        room.status = "finished"
        room.phase = "finished"
        room.started_at = main.time.time() - 42
        room.players["host"].score = 800
        room.players["host"].correct_guesses = 2
        room.players["guest"].guesses = 5
        with (
            patch.object(main, "record_user_game_finish") as record_finish,
            patch.object(main, "increment_player_score") as increment_score,
        ):
            main._record_scribbl_room_results(room)

        self.assertEqual(record_finish.call_count, 2)
        self.assertEqual(increment_score.call_count, 1)
        self.assertEqual(
            record_finish.call_args_list[0].kwargs["game_id"], "scribbl"
        )
        self.assertEqual(
            record_finish.call_args_list[0].kwargs["metrics"]["correct_guesses"], 2
        )
        self.assertTrue(room.stats_recorded)


if __name__ == "__main__":
    unittest.main()
