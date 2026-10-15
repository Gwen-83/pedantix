import unittest
from unittest.mock import patch

from app import main


class PresenceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        with main.online_presence_lock:
            main.online_presence.clear()

    async def asyncTearDown(self):
        with main.online_presence_lock:
            main.online_presence.clear()

    async def test_online_list_deduplicates_players_and_expires_stale_sessions(self):
        with patch("app.main.time.time", return_value=100.0):
            await main.update_presence(
                main.PresenceRequest(
                    session_id="tab-one",
                    username="Alice",
                    game_id="motus",
                )
            )
        with patch("app.main.time.time", return_value=110.0):
            await main.update_presence(
                main.PresenceRequest(
                    session_id="tab-two",
                    username="alice",
                    game_id="sudoku",
                )
            )

        with patch("app.main.time.time", return_value=111.0):
            response = await main.list_online_presence()
        self.assertEqual(
            response["players"],
            [{"username": "alice", "game_id": "sudoku"}],
        )

        with patch("app.main.time.time", return_value=201.0):
            response = await main.list_online_presence()
        self.assertEqual(response["players"], [])


if __name__ == "__main__":
    unittest.main()
