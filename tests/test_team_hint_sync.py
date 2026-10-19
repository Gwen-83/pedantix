import asyncio
import json
import unittest
from unittest.mock import patch

from app.game import GameSession
from app.room import Room, RoomPlayer


class CapturingWebSocket:
    def __init__(self):
        self.messages = []

    async def send_text(self, message):
        self.messages.append(message)


class TeamHintSyncTests(unittest.TestCase):
    def setUp(self):
        self.score_patcher = patch("app.room.get_player_score", return_value=0)
        self.guess_record_patcher = patch("app.game.record_guess")
        self.start_record_patcher = patch("app.game.record_game_start")
        self.user_guess_patcher = patch("app.room.record_user_guess_word")
        self.valid_word_patcher = patch("app.game.is_valid_french_word", return_value=True)
        self.proximity_patcher = patch(
            "app.game.calculate_proximity",
            side_effect=lambda guess, target: 60.0 if guess == "autre" else 0.0,
        )
        for patcher in (
            self.score_patcher,
            self.guess_record_patcher,
            self.start_record_patcher,
            self.user_guess_patcher,
            self.valid_word_patcher,
            self.proximity_patcher,
        ):
            patcher.start()

        self.room = Room(
            room_id="team-hint-sync",
            article_data={"title": "Titre Secret", "paragraphs": ["Un texte cible."]},
            seed="P-1234",
        )
        self.room.status = "playing"
        self.room.game_mode = "team"
        self.room.team_sessions = {
            team: GameSession(
                session_id=f"{team}-session",
                seed="P-1234",
                title="Titre Secret",
                url="",
                image="",
                paragraphs=["Un texte cible."],
                mode="team",
                category="general",
            )
            for team in ("blue", "red")
        }
        self.room.players = {}
        for player_id, team in (
            ("blue-one", "blue"),
            ("blue-two", "blue"),
            ("red-one", "red"),
        ):
            self.room.players[player_id] = RoomPlayer(
                player_id,
                player_id,
                self.room.team_sessions[team],
                team=team,
            )

    def tearDown(self):
        self.room.cleanup()
        for patcher in (
            self.score_patcher,
            self.guess_record_patcher,
            self.start_record_patcher,
            self.user_guess_patcher,
            self.valid_word_patcher,
            self.proximity_patcher,
        ):
            patcher.stop()

    def test_team_guess_broadcasts_complete_grey_hints_to_every_teammate(self):
        blue_one = CapturingWebSocket()
        blue_two = CapturingWebSocket()
        red_one = CapturingWebSocket()
        for websocket, player_id in (
            (blue_one, "blue-one"),
            (blue_two, "blue-two"),
            (red_one, "red-one"),
        ):
            self.room.add_websocket(websocket, player_id)

        from types import SimpleNamespace
        from app import main

        async def submit_guess(player_id, word):
            with (
                patch.object(main.room_manager, "get_or_create_room", return_value=self.room),
                patch.object(main.anti_bot_guard, "check_rate_limit", return_value=(True, "", {})),
                patch.object(main.anti_bot_guard, "verify_token", return_value=(True, "", "next-token")),
            ):
                return await main.room_guess(
                    main.RoomGuessRequest(
                        room_id=self.room.room_id,
                        player_id=player_id,
                        word=word,
                        guess_token="current-token",
                    ),
                    SimpleNamespace(
                        headers={"user-agent": "team hint test"},
                        client=SimpleNamespace(host="127.0.0.1"),
                    ),
                )

        result = asyncio.run(submit_guess("blue-one", "autre"))
        self.assertTrue(result["team_close_tokens"])
        self.assertEqual(
            self.room.team_sessions["blue"].get_close_tokens(),
            result["team_close_tokens"],
        )
        public_tokens = {
            token["id"]: token
            for token in self.room.team_sessions["blue"].get_public_state()["tokens"]
        }
        for teammate_id in ("blue-one", "blue-two"):
            self.assertIs(
                self.room.players[teammate_id].session,
                self.room.team_sessions["blue"],
            )
            for hint in result["team_close_tokens"]:
                self.assertEqual(public_tokens[hint["id"]]["heat"], hint["score"])
                self.assertEqual(public_tokens[hint["id"]]["close_word"], hint["word"])

        next_result = asyncio.run(submit_guess("blue-two", "sans-proximite"))
        self.assertEqual(next_result["close_tokens"], [])
        self.assertEqual(next_result["team_close_tokens"], result["team_close_tokens"])

        blue_one_message = json.loads(blue_one.messages[0])
        blue_two_message = json.loads(blue_two.messages[0])
        self.assertEqual(blue_one_message, blue_two_message)
        self.assertTrue(blue_one_message["team_guess"]["close_tokens"])

        red_message = json.loads(red_one.messages[0])
        self.assertEqual(red_message["team_guess"]["close_tokens"], [])
        self.assertEqual(red_message["team_guess"]["word"], "••••")
        self.assertTrue(red_message["team_guess"]["redacted"])

        blue_one_second = json.loads(blue_one.messages[1])
        blue_two_second = json.loads(blue_two.messages[1])
        self.assertEqual(blue_one_second, blue_two_second)
        self.assertEqual(
            blue_one_second["team_guess"]["close_tokens"],
            result["team_close_tokens"],
        )
        self.assertTrue(json.loads(red_one.messages[1])["team_guess"]["redacted"])


if __name__ == "__main__":
    unittest.main()
