import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

import app.database as database
from app import main
from app.memories import MemoriesManager


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

    async def test_active_room_directory_includes_joinable_rooms_and_excludes_finished_or_full(self):
        class RoomDirectory:
            def __init__(self, rooms):
                self._rooms = rooms

            def list_rooms(self):
                return self._rooms

        motus_rooms = RoomDirectory([
            {
                "room_id": "WAIT1",
                "status": "lobby",
                "player_count": 1,
                "spectator_count": 0,
                "host_name": "Alice",
            },
            {
                "room_id": "FULL1",
                "status": "lobby",
                "player_count": 8,
                "spectator_count": 0,
                "host_name": "Alice",
            },
            {
                "room_id": "DONE1",
                "status": "finished",
                "player_count": 2,
                "spectator_count": 0,
                "host_name": "Alice",
            },
            {
                "room_id": "PLAY1",
                "status": "playing",
                "player_count": 3,
                "spectator_count": 1,
                "host_name": "Alice",
            },
        ])
        plongee_rooms = RoomDirectory([
            {
                "room_id": "DIVE1",
                "status": "playing",
                "player_count": 2,
                "spectator_count": 0,
            },
        ])
        with (
            patch.dict(
                main.STORE_ACTIVE_ROOM_GAMES,
                {
                    "motus": ("Motus", motus_rooms, "motus_player_id"),
                    "plongee": ("Plongée", plongee_rooms, "plongee_player_id"),
                },
                clear=True,
            ),
            patch.dict(
                main.STORE_ROOM_PLAYER_LIMITS,
                {"motus": 8, "plongee": 8},
                clear=True,
            ),
            patch.object(main.room_manager, "list_active_rooms", return_value=[]),
        ):
            result = await main.get_store_social_rooms()

        self.assertEqual(
            [(room["game_id"], room["room_id"]) for room in result["rooms"]],
            [("motus", "PLAY1"), ("motus", "WAIT1")],
        )
        self.assertEqual(result["rooms"][0]["spectator_count"], 1)

    async def test_invitation_creates_private_battleship_room_when_accepted(self):
        class FakeBattleshipManager:
            def __init__(self):
                self.rooms = {}

            def create_room(self, player_id, player_name, difficulty):
                room = SimpleNamespace(room_id="ROOM42", players={})
                room.players[player_id] = SimpleNamespace(name=player_name)
                self.rooms[room.room_id] = room
                return room

            def join_room(self, room_id, player_id, player_name):
                room = self.rooms[room_id]
                room.players[player_id] = SimpleNamespace(name=player_name)
                return room

        manager = FakeBattleshipManager()
        with patch.dict(
            main.STORE_INVITATION_GAMES,
            {"battleship": ("Bataille navale", manager, "battleship_player_id")},
        ):
            with main.online_presence_lock:
                main.online_presence["bob-tab"] = {
                    "username": "Bob",
                    "game_id": "store",
                    "last_seen": main.time.time(),
                }
            invitation = await main.post_store_invitation(
                main.StoreInvitationRequest(
                    recipient_username="Bob",
                    game_id="battleship",
                ),
                "Alice",
                self.alice["token"],
            )

            received = await main.get_store_social_invitations("Bob", self.bob["token"])
            self.assertEqual(received["invitations"], [invitation])
            self.assertEqual(invitation["status"], "pending")
            self.assertGreater(invitation["expires_at"], main.time.time())
            self.assertLessEqual(invitation["expires_at"], main.time.time() + 300)

            accepted = await main.update_store_social_invitation(
                invitation["id"],
                main.StoreInvitationActionRequest(action="accepted"),
                "Bob",
                self.bob["token"],
            )

        self.assertEqual(accepted["status"], "accepted")
        self.assertEqual(accepted["room_id"], "ROOM42")
        self.assertEqual(accepted["player_id"], "Bob")
        room = manager.rooms["ROOM42"]
        self.assertEqual(set(room.players), {"Alice", "Bob"})
        sent = await main.get_store_sent_social_invitations("Alice", self.alice["token"])
        self.assertEqual(sent["invitations"][0]["status"], "accepted")
        self.assertEqual(sent["invitations"][0]["room_id"], "ROOM42")
        with self.assertRaises(HTTPException) as duplicate_accept:
            await main.update_store_social_invitation(
                invitation["id"],
                main.StoreInvitationActionRequest(action="accepted"),
                "Bob",
                self.bob["token"],
            )
        self.assertEqual(duplicate_accept.exception.status_code, 410)
        self.assertEqual(
            (await main.get_store_social_invitations("Bob", self.bob["token"]))["invitations"],
            [],
        )

    async def test_declining_invitation_does_not_create_a_room(self):
        manager = SimpleNamespace(create_room=lambda *_args: self.fail("room should not be created"))
        with patch.dict(
            main.STORE_INVITATION_GAMES,
            {"battleship": ("Bataille navale", manager, "battleship_player_id")},
        ):
            with main.online_presence_lock:
                main.online_presence["bob-tab"] = {
                    "username": "Bob",
                    "game_id": "store",
                    "last_seen": main.time.time(),
                }
            invitation = await main.post_store_invitation(
                main.StoreInvitationRequest(recipient_username="Bob", game_id="battleship"),
                "Alice",
                self.alice["token"],
            )
            declined = await main.update_store_social_invitation(
                invitation["id"],
                main.StoreInvitationActionRequest(action="declined"),
                "Bob",
                self.bob["token"],
            )

        self.assertEqual(declined, {"status": "declined"})
        self.assertEqual(
            (await main.get_store_sent_social_invitations("Alice", self.alice["token"]))[
                "invitations"
            ][0]["status"],
            "declined",
        )

    async def test_sender_can_cancel_invitation_and_recipient_can_no_longer_accept_it(self):
        with main.online_presence_lock:
            main.online_presence["bob-tab"] = {
                "username": "Bob",
                "game_id": "store",
                "last_seen": main.time.time(),
            }
        invitation = await main.post_store_invitation(
            main.StoreInvitationRequest(recipient_username="Bob", game_id="memories"),
            "Alice",
            self.alice["token"],
        )

        with self.assertRaises(HTTPException) as recipient_cannot_cancel:
            await main.update_store_social_invitation(
                invitation["id"],
                main.StoreInvitationActionRequest(action="cancelled"),
                "Bob",
                self.bob["token"],
            )
        self.assertEqual(recipient_cannot_cancel.exception.status_code, 410)
        self.assertEqual(
            len((await main.get_store_social_invitations("Bob", self.bob["token"]))["invitations"]),
            1,
        )

        cancelled = await main.update_store_social_invitation(
            invitation["id"],
            main.StoreInvitationActionRequest(action="cancelled"),
            "Alice",
            self.alice["token"],
        )
        self.assertEqual(cancelled, {"status": "cancelled"})
        self.assertEqual(
            (await main.get_store_social_invitations("Bob", self.bob["token"]))["invitations"],
            [],
        )
        sent = await main.get_store_sent_social_invitations("Alice", self.alice["token"])
        self.assertEqual(sent["invitations"][0]["status"], "cancelled")
        with self.assertRaises(HTTPException) as cannot_accept_cancelled:
            await main.update_store_social_invitation(
                invitation["id"],
                main.StoreInvitationActionRequest(action="accepted"),
                "Bob",
                self.bob["token"],
            )
        self.assertEqual(cannot_accept_cancelled.exception.status_code, 410)

    async def test_memories_invitation_creates_a_joined_multiplayer_room(self):
        manager = MemoriesManager()
        with patch.dict(
            main.STORE_INVITATION_GAMES,
            {"memories": ("Memory", manager, "memories_player_id")},
        ):
            with main.online_presence_lock:
                main.online_presence["bob-tab"] = {
                    "username": "Bob",
                    "game_id": "store",
                    "last_seen": main.time.time(),
                }
            invitation = await main.post_store_invitation(
                main.StoreInvitationRequest(
                    recipient_username="Bob",
                    game_id="memories",
                ),
                "Alice",
                self.alice["token"],
            )
            accepted = await main.update_store_social_invitation(
                invitation["id"],
                main.StoreInvitationActionRequest(action="accepted"),
                "Bob",
                self.bob["token"],
            )

        room = manager.get_room(accepted["room_id"], accepted["player_id"])
        self.assertEqual(room.status, "lobby")
        self.assertEqual(set(room.players), {"Alice", "Bob"})
        self.assertEqual(accepted["game_id"], "memories")

    async def test_invitation_expires_after_five_minutes(self):
        with main.online_presence_lock:
            main.online_presence["bob-tab"] = {
                "username": "Bob",
                "game_id": "store",
                "last_seen": 1000,
            }
        with patch.object(main.time, "time", return_value=1000):
            invitation = await main.post_store_invitation(
                main.StoreInvitationRequest(recipient_username="Bob", game_id="motus"),
                "Alice",
                self.alice["token"],
            )
            self.assertEqual(invitation["expires_at"], 1300)
            self.assertEqual(
                len((await main.get_store_social_invitations("Bob", self.bob["token"]))["invitations"]),
                1,
            )

        with patch.object(main.time, "time", return_value=1301):
            self.assertEqual(
                (await main.get_store_social_invitations("Bob", self.bob["token"]))["invitations"],
                [],
            )
            sent = await main.get_store_sent_social_invitations("Alice", self.alice["token"])
        self.assertEqual(sent["invitations"][0]["status"], "expired")

    async def test_invitation_requires_an_online_recipient_and_cannot_target_self(self):
        with self.assertRaises(HTTPException) as offline:
            await main.post_store_invitation(
                main.StoreInvitationRequest(recipient_username="Bob", game_id="motus"),
                "Alice",
                self.alice["token"],
            )
        self.assertEqual(offline.exception.status_code, 409)

        with self.assertRaises(HTTPException) as self_invite:
            await main.post_store_invitation(
                main.StoreInvitationRequest(recipient_username="Alice", game_id="motus"),
                "Alice",
                self.alice["token"],
            )
        self.assertEqual(self_invite.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
