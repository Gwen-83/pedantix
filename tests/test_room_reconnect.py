import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.room import PLAYER_DISCONNECT_GRACE_SECONDS, Room, RoomPlayer


class FakeWebSocket:
    async def send_text(self, message):
        pass


class FakeSoloSession:
    def __init__(self):
        self.session_id = "shared-solo-session"
        self.total_words = 10
        self.tokens = []
        self.history = []
        self.is_won = False

    def submit_guess(self, word):
        self.history.append({"word": word, "status": "miss"})
        return {
            "status": "miss",
            "attempt_number": len(self.history),
            "matches_count": 0,
            "score": 0,
            "newly_revealed": {},
            "close_tokens": [],
            "is_won": False,
            "revealed_words_count": 0,
            "total_words": self.total_words,
            "history": self.history,
        }

    def get_public_state(self, hinted_word_ids=None):
        return {
            "session_id": self.session_id,
            "tokens": self.tokens,
            "history": self.history,
            "total_words": self.total_words,
            "revealed_words_count": 0,
            "solution": None,
        }


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

    async def test_assistant_joins_owner_solo_session_and_shares_guesses(self):
        from app.main import RoomJoinRequest, join_room

        room = Room(
            room_id="solo-owner-1",
            article_data={"title": "Article", "paragraphs": ["Texte de test."]},
            seed="P-1234",
        )
        shared_session = FakeSoloSession()
        owner = RoomPlayer("owner-1", "Propriétaire", shared_session, is_host=True)
        room.players[owner.player_id] = owner
        room.host_player_id = owner.player_id

        def add_helper(player_id, name):
            helper = RoomPlayer(player_id, name, FakeSoloSession())
            room.players[player_id] = helper
            return helper

        request = RoomJoinRequest(
            room_id=room.room_id,
            player_id="helper-1",
            player_name="Aide",
            difficulty="difficile",
            assist_token=room.assist_token,
        )
        with (
            patch("app.main.room_manager.get_room", return_value=room),
            patch("app.main.room_manager.get_or_create_room") as create_room,
            patch.object(room, "get_or_create_player", side_effect=add_helper),
            patch.object(room, "broadcast", new_callable=AsyncMock),
            patch("app.main.anti_bot_guard.get_or_issue_token", return_value="guess-token"),
            patch("app.room.record_user_guess_word"),
        ):
            response = await join_room(request)
            helper = room.players["helper-1"]
            self.assertIs(helper.session, shared_session)
            self.assertFalse(helper.is_host)

            result = room.process_guess(helper.player_id, "proposition")

        create_room.assert_not_called()
        self.assertEqual(response["session"]["session_id"], "shared-solo-session")
        self.assertEqual(result["attempt_number"], 1)
        self.assertEqual(owner.attempts, helper.attempts)
        self.assertEqual(owner.last_word, "proposition")

    async def test_assistant_can_reload_and_reuse_the_same_link_after_leaving(self):
        from app.main import RoomJoinRequest, RoomLeaveRequest, join_room, leave_room

        room = Room(
            room_id="solo-owner-1",
            article_data={"title": "Article", "paragraphs": ["Texte de test."]},
            seed="P-1234",
        )
        owner = RoomPlayer("owner-1", "Propriétaire", FakeSoloSession(), is_host=True)
        room.players[owner.player_id] = owner
        room.host_player_id = owner.player_id
        assist_token = room.assist_token
        request = RoomJoinRequest(
            room_id=room.room_id,
            player_id="helper-1",
            player_name="Aide",
            assist_token=room.assist_token,
        )

        with (
            patch("app.main.room_manager.get_room", return_value=room),
            patch.object(room, "broadcast", new_callable=AsyncMock),
            patch("app.main.anti_bot_guard.get_or_issue_token", return_value="guess-token"),
        ):
            first_join = await join_room(request)
            helper = room.players["helper-1"]
            helper_session = owner.session

            old_socket = FakeWebSocket()
            room.add_websocket(old_socket, helper.player_id)
            await room.handle_websocket_disconnect(old_socket)
            reloaded_join = await join_room(request)
            self.assertIs(room.players["helper-1"], helper)
            self.assertIs(helper.session, helper_session)
            self.assertEqual(reloaded_join["session"]["session_id"], helper_session.session_id)
            self.assertNotIn("helper-1", room._disconnect_tasks)

            await leave_room(RoomLeaveRequest(room_id=room.room_id, player_id="helper-1"))
            self.assertIsNone(room.assisting_player_id)

            rejoined = await join_room(request)

        self.assertEqual(assist_token, room.assist_token)
        self.assertEqual(first_join["room_id"], room.room_id)
        self.assertEqual(rejoined["session"]["session_id"], helper_session.session_id)
        self.assertEqual(room.assisting_player_id, "helper-1")

    async def test_invalid_assistance_link_does_not_create_a_solo_room(self):
        from fastapi import HTTPException
        from app.main import RoomJoinRequest, join_room

        request = RoomJoinRequest(
            room_id="solo-owner-1",
            player_id="helper-1",
            player_name="Aide",
            assist_token="invalid",
        )
        with (
            patch("app.main.room_manager.get_room", return_value=None),
            patch("app.main.room_manager.get_or_create_room") as create_room,
        ):
            with self.assertRaises(HTTPException) as error:
                await join_room(request)

        self.assertEqual(error.exception.status_code, 404)
        create_room.assert_not_called()

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
