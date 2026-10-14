import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from fastapi import HTTPException

from app.main import RoomUnmaskRequest, unmask_room


class RoomUnmaskTests(unittest.IsolatedAsyncioTestCase):
    async def test_unmask_broadcasts_revealed_tokens_to_room(self):
        room = SimpleNamespace(
            players={"player-1": SimpleNamespace(name="Alice")},
            unmask_player=Mock(return_value={
                "status": "ok",
                "tokens": {"1": "Bonjour"},
            }),
            broadcast=AsyncMock(),
        )
        request = RoomUnmaskRequest(room_id="room-1", player_id="player-1")

        with patch("app.main.room_manager.get_or_create_room", return_value=room):
            response = await unmask_room(request)

        self.assertEqual(response["tokens"], {"1": "Bonjour"})
        room.broadcast.assert_awaited_once_with({
            "type": "article_unmasked",
            "player_id": "player-1",
            "player_name": "Alice",
            "tokens": {"1": "Bonjour"},
        })

    async def test_failed_unmask_is_not_broadcast(self):
        room = SimpleNamespace(
            unmask_player=Mock(return_value={
                "error": "L'article ne peut être démasqué qu'une fois la manche terminée.",
            }),
            broadcast=AsyncMock(),
        )
        request = RoomUnmaskRequest(room_id="room-1", player_id="player-1")

        with patch("app.main.room_manager.get_or_create_room", return_value=room):
            with self.assertRaises(HTTPException) as error:
                await unmask_room(request)

        self.assertEqual(error.exception.status_code, 403)
        room.broadcast.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
