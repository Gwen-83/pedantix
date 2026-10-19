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
        self.proximity_patcher = patch("app.game.calculate_proximity", return_value=60.0)
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
        session = GameSession(
            session_id="team-session",
            seed="P-1234",
            title="Titre Secret",
            url="",
            image="",
            paragraphs=["Un texte cible."],
            mode="team",
            category="general",
        )
        self.room.team_sessions["blue"] = session
        self.room.players = {
            player_id: RoomPlayer(player_id, player_id, session, team=team)
            for player_id, team in (
                ("blue-one", "blue"),
                ("blue-two", "blue"),
                ("red-one", "red"),
            )
        }

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
        result = self.room.process_guess("blue-one", "autre")
        self.assertTrue(result["team_close_tokens"])

        blue_one = CapturingWebSocket()
        blue_two = CapturingWebSocket()
        red_one = CapturingWebSocket()
        for websocket, player_id in (
            (blue_one, "blue-one"),
            (blue_two, "blue-two"),
            (red_one, "red-one"),
        ):
            self.room.add_websocket(websocket, player_id)

        asyncio.run(self.room.broadcast({
            "type": "progress_update",
            "game_mode": "team",
            "team": "blue",
            "team_guess": {
                "player_id": "blue-one",
                "player_name": "blue-one",
                "team": "blue",
                "word": "autre",
                "status": result["status"],
                "close_tokens": result["team_close_tokens"],
            },
        }))

        blue_one_message = json.loads(blue_one.messages[0])
        blue_two_message = json.loads(blue_two.messages[0])
        self.assertEqual(blue_one_message, blue_two_message)
        self.assertTrue(blue_one_message["team_guess"]["close_tokens"])

        red_message = json.loads(red_one.messages[0])
        self.assertEqual(red_message["team_guess"]["close_tokens"], [])
        self.assertEqual(red_message["team_guess"]["word"], "••••")


if __name__ == "__main__":
    unittest.main()
