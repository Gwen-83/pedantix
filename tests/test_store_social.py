import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

import app.database as database
from app import main


class StoreSocialTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path_patch = patch.object(
            database, "DB_PATH", str(Path(self.temp_dir.name) / "social.sqlite3")
        )
        self.db_path_patch.start()
        self.pg_disabled_patch = patch.object(database, "_pg_disabled", True)
        self.pg_disabled_patch.start()
        self.assertTrue(database.init_db())
        self.alice = database.create_user("Alice", "secret")
        self.bob = database.create_user("Bob", "secret")
        with main.online_presence_lock:
            main.online_presence.clear()

    async def asyncTearDown(self):
        with main.online_presence_lock:
            main.online_presence.clear()
        self.pg_disabled_patch.stop()
        self.db_path_patch.stop()
        self.temp_dir.cleanup()

    async def test_chat_messages_are_saved_and_returned_in_order(self):
        first = await main.post_store_chat(
            main.StoreChatMessageRequest(message=" Bonjour tout le monde "),
            "Alice",
            self.alice["token"],
        )
        second = await main.post_store_chat(
            main.StoreChatMessageRequest(message="Salut !"),
            "Bob",
            self.bob["token"],
        )

        history = await main.get_store_chat(after_id=0)
        updates = await main.get_store_chat(after_id=first["id"])
        self.assertEqual([item["id"] for item in history["messages"]], [first["id"], second["id"]])
        self.assertEqual([item["id"] for item in updates["messages"]], [second["id"]])
        self.assertEqual(first["message"], "Bonjour tout le monde")

    async def test_chat_requires_a_valid_login_and_nonblank_message(self):
        with self.assertRaises(HTTPException) as unauthenticated:
            await main.post_store_chat(
                main.StoreChatMessageRequest(message="Bonjour"), "Alice", "invalid"
            )
        self.assertEqual(unauthenticated.exception.status_code, 401)

        with self.assertRaises(HTTPException) as blank:
            await main.post_store_chat(
                main.StoreChatMessageRequest(message="   "),
                "Alice",
                self.alice["token"],
            )
        self.assertEqual(blank.exception.status_code, 400)

    async def test_online_player_can_be_invited_to_the_senders_active_room(self):
        room = SimpleNamespace(
            room_id="ROOM42",
            status="lobby",
            players={
                "alice-id": SimpleNamespace(name="Alice", is_spectator=False),
                "bob-id": SimpleNamespace(name="Bob", is_spectator=False),
            },
        )
        manager = SimpleNamespace(rooms={"ROOM42": room})
        managers = (("motus", "Motus", manager),)
        with patch.object(main, "_store_room_managers", return_value=managers):
            rooms = await main.get_store_social_rooms("Alice", self.alice["token"])
            self.assertEqual(
                rooms["rooms"],
                [{
                    "game_id": "motus",
                    "game_name": "Motus",
                    "room_id": "ROOM42",
                    "status": "lobby",
                }],
            )
            with main.online_presence_lock:
                main.online_presence["bob-tab"] = {
                    "username": "Bob",
                    "game_id": "store",
                    "last_seen": main.time.time(),
                }
            invitation = await main.post_store_invitation(
                main.StoreInvitationRequest(
                    recipient_username="Bob",
                    game_id="motus",
                    room_id="ROOM42",
                ),
                "Alice",
                self.alice["token"],
            )

        received = await main.get_store_social_invitations("Bob", self.bob["token"])
        self.assertEqual(received["invitations"], [invitation])
        updated = await main.update_store_social_invitation(
            invitation["id"],
            main.StoreInvitationActionRequest(action="accepted"),
            "Bob",
            self.bob["token"],
        )
        self.assertEqual(updated["status"], "accepted")
        self.assertEqual((await main.get_store_social_invitations("Bob", self.bob["token"]))["invitations"], [])

    async def test_invitation_rejects_offline_recipients_and_nonmember_senders(self):
        room = SimpleNamespace(
            room_id="ROOM42",
            status="playing",
            players={"other-id": SimpleNamespace(name="Eve", is_spectator=False)},
        )
        managers = (("motus", "Motus", SimpleNamespace(rooms={"ROOM42": room})),)
        with patch.object(main, "_store_room_managers", return_value=managers):
            with self.assertRaises(HTTPException) as offline:
                await main.post_store_invitation(
                    main.StoreInvitationRequest(
                        recipient_username="Bob",
                        game_id="motus",
                        room_id="ROOM42",
                    ),
                    "Alice",
                    self.alice["token"],
                )
            self.assertEqual(offline.exception.status_code, 409)

            with main.online_presence_lock:
                main.online_presence["bob-tab"] = {
                    "username": "Bob",
                    "game_id": "store",
                    "last_seen": main.time.time(),
                }
            with self.assertRaises(HTTPException) as not_member:
                await main.post_store_invitation(
                    main.StoreInvitationRequest(
                        recipient_username="Bob",
                        game_id="motus",
                        room_id="ROOM42",
                    ),
                    "Alice",
                    self.alice["token"],
                )
            self.assertEqual(not_member.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
