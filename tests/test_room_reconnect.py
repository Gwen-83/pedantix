import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.room import PLAYER_DISCONNECT_GRACE_SECONDS, Room, RoomPlayer


class FakeWebSocket:
    async def send_text(self, message):
        pass


class RoomReconnectTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.score_patcher = patch("app.room.get_player_score", return_value=0)
        self.score_patcher.start()
        self.room = Room(
            room_id="test-reconnect",
            article_data={"title": "Article", "paragraphs": []},
            seed="P-1234",
        )
        self.player = RoomPlayer(
            "player-1",
            "Joueur test",
            SimpleNamespace(total_words=10),
            is_host=True,
        )
        self.player.is_ready = True
        self.room.players[self.player.player_id] = self.player
        self.room.host_player_id = self.player.player_id
        self.original_socket = FakeWebSocket()
        self.room.add_websocket(self.original_socket, self.player.player_id)

    async def asyncTearDown(self):
        self.room.cleanup()
        self.score_patcher.stop()

    async def test_disconnect_and_reconnect_preserve_lobby_player_state(self):
        before = self.room.get_leaderboard()

        await self.room.handle_websocket_disconnect(self.original_socket)

        self.assertEqual(self.room.get_leaderboard(), before)
        self.assertTrue(self.player.connected)
        self.assertTrue(self.player.is_ready)

        reconnected_player = self.room.get_or_create_player(
            self.player.player_id,
            self.player.name,
        )
        reconnect_socket = FakeWebSocket()
        self.room.add_websocket(reconnect_socket, self.player.player_id)

        self.assertIs(reconnected_player, self.player)
        self.assertEqual(self.room.get_leaderboard(), before)
        self.assertNotIn(self.player.player_id, self.room._disconnect_tasks)

    async def test_player_is_removed_only_after_reconnect_grace_expires(self):
        with patch("app.room.PLAYER_DISCONNECT_GRACE_SECONDS", 0.01):
            await self.room.handle_websocket_disconnect(self.original_socket)
            self.assertIn(self.player.player_id, self.room.players)
            await asyncio.sleep(0.03)

        self.assertNotIn(self.player.player_id, self.room.players)

    def test_disconnect_grace_is_long_enough_for_a_page_reload(self):
        self.assertGreaterEqual(PLAYER_DISCONNECT_GRACE_SECONDS, 30.0)

    async def test_solo_rejoin_preserves_revealed_words_when_saved_difficulty_is_stale(self):
        from app.game import GameSession
        from app.main import RoomJoinRequest, join_room
        from app.room import room_manager

        room = Room(
            room_id="solo-player-1",
            article_data={"title": "Article", "paragraphs": ["Un texte pour le test."]},
            seed="P-1234",
            difficulty="moyen",
        )
        session = GameSession(
            session_id="session-with-progress",
            seed=room.seed,
            title="Article",
            url="",
            image="",
            paragraphs=["Un texte pour le test."],
            mode="multiplayer",
            category="general",
            difficulty="moyen",
        )
        revealed_token = next(token for token in session.tokens if token["is_word"])
        revealed_token["revealed"] = True
        session.revealed_word_ids.add(revealed_token["id"])
        session.guesses_history.append({"word": revealed_token["text"], "status": "found"})
        player = RoomPlayer("player-1", "Joueur test", session, is_host=True)
        room.players[player.player_id] = player
        room.host_player_id = player.player_id

        request = RoomJoinRequest(
            room_id=room.room_id,
            player_id=player.player_id,
            player_name=player.name,
            difficulty="difficile",
        )
        with (
            patch.object(room_manager, "get_or_create_room", return_value=room),
            patch.object(room_manager, "_fetch_random_article") as fetch_article,
        ):
            response = await join_room(request)

        fetch_article.assert_not_called()
        self.assertIs(player.session, session)
        self.assertEqual(room.difficulty, "moyen")
        self.assertEqual(response["difficulty"], "moyen")
        self.assertEqual(response["session"]["session_id"], "session-with-progress")
        self.assertEqual(response["session"]["revealed_words_count"], 1)
        self.assertEqual(response["session"]["history"], session.guesses_history)
        response_token = next(
            token for token in response["session"]["tokens"]
            if token["id"] == revealed_token["id"]
        )
        self.assertTrue(response_token["revealed"])


if __name__ == "__main__":
    unittest.main()
