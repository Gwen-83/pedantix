import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import app.database as database
from app import main
from app.database import generate_user_token
from app.main import app


class GlobalGamePauseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "pause-test.db"
        self.database_path_patch = patch.object(database, "DB_PATH", str(self.database_path))
        self.database_path_patch.start()
        self.assertTrue(database.init_db())
        self.gwen_account = database.create_user("Gwen", "gwen-password")
        self.alice_account = database.create_user("Alice", "alice-password")
        self.bob_account = database.create_user("Bob", "bob-password")
        self.assertEqual(self.gwen_account["status"], "ok")
        self.assertEqual(self.alice_account["status"], "ok")
        self.assertEqual(self.bob_account["status"], "ok")
        self.client = TestClient(app)
        self.gwen_headers = {
            "X-Auth-User": "Gwen",
            "X-Auth-Token": generate_user_token("Gwen"),
        }
        self.other_headers = {
            "X-Auth-User": "Alice",
            "X-Auth-Token": generate_user_token("Alice"),
        }

    def tearDown(self):
        self.database_path_patch.stop()
        self.temp_dir.cleanup()

    def test_only_authenticated_gwen_can_change_global_pause(self):
        self.assertFalse(self.client.get("/api/games/pause").json()["can_control"])
        self.assertTrue(
            self.client.get("/api/games/pause", headers=self.gwen_headers).json()["can_control"]
        )

        denied = self.client.post(
            "/api/admin/game-pause",
            headers=self.other_headers,
            json={"paused": True, "admin_password": "alice-password"},
        )
        self.assertEqual(denied.status_code, 403)

        wrong_password = self.client.post(
            "/api/admin/game-pause",
            headers=self.gwen_headers,
            json={"paused": True, "admin_password": "wrong"},
        )
        self.assertEqual(wrong_password.status_code, 403)

        paused = self.client.post(
            "/api/admin/game-pause",
            headers=self.gwen_headers,
            json={"paused": True, "admin_password": "gwen-password"},
        )
        self.assertEqual(paused.status_code, 200)
        self.assertTrue(paused.json()["paused"])
        self.assertTrue(self.client.get("/api/games/pause").json()["paused"])

        resumed = self.client.post(
            "/api/admin/game-pause",
            headers=self.gwen_headers,
            json={"paused": False, "admin_password": "gwen-password"},
        )
        self.assertEqual(resumed.status_code, 200)
        self.assertFalse(resumed.json()["paused"])

    def test_pause_blocks_new_games_and_restarts_across_every_game(self):
        self.assertEqual(
            self.client.post(
                "/api/admin/game-pause",
                headers=self.gwen_headers,
                json={"paused": True, "admin_password": "gwen-password"},
            ).status_code,
            200,
        )
        launch_requests = [
            ("GET", "/api/game/new"),
            ("POST", "/api/room/create"),
            ("POST", "/api/room/start"),
            ("POST", "/api/room/next-round"),
            ("POST", "/api/room/difficulty"),
            ("POST", "/api/social/invitations"),
        ]
        for game in (
            "motus", "undercover", "cemantix", "chiffrantix", "battleship",
            "sudoku", "geoguessr", "bitoguessr", "plongee", "memories",
        ):
            launch_requests.extend([
                ("POST", f"/api/{game}/solo/new"),
                ("POST", f"/api/{game}/room/create"),
                ("POST", f"/api/{game}/room/start"),
                ("POST", f"/api/{game}/room/restart"),
            ])

        for method, path in launch_requests:
            with self.subTest(method=method, path=path):
                response = self.client.request(method, path, json={})
                self.assertEqual(response.status_code, 423)
                self.assertTrue(response.json()["games_paused"])
                self.assertIn("pause pour cause de maintenance", response.json()["detail"])

    def test_pause_does_not_interrupt_in_progress_game_actions(self):
        self.client.post(
            "/api/admin/game-pause",
            headers=self.gwen_headers,
            json={"paused": True, "admin_password": "gwen-password"},
        )
        response = self.client.post("/api/motus/solo/guess", json={})
        self.assertEqual(response.status_code, 422)

    def test_pause_rejects_invitation_acceptance_but_still_allows_declining(self):
        with main.online_presence_lock:
            main.online_presence["pause-test-bob"] = {
                "username": "Bob",
                "game_id": "store",
                "last_seen": main.time.time(),
            }
        invitation = self.client.post(
            "/api/social/invitations",
            headers={
                "X-Auth-User": "Alice",
                "X-Auth-Token": self.alice_account["token"],
            },
            json={"recipient_username": "Bob", "game_id": "battleship"},
        )
        self.assertEqual(invitation.status_code, 200)
        invitation_id = invitation.json()["id"]
        self.client.post(
            "/api/admin/game-pause",
            headers=self.gwen_headers,
            json={"paused": True, "admin_password": "gwen-password"},
        )
        bob_headers = {
            "X-Auth-User": "Bob",
            "X-Auth-Token": self.bob_account["token"],
        }

        accepted = self.client.post(
            f"/api/social/invitations/{invitation_id}",
            headers=bob_headers,
            json={"action": "accepted"},
        )
        self.assertEqual(accepted.status_code, 423)
        self.assertIn("pause pour cause de maintenance", accepted.json()["detail"])

        declined = self.client.post(
            f"/api/social/invitations/{invitation_id}",
            headers=bob_headers,
            json={"action": "declined"},
        )
        self.assertEqual(declined.status_code, 200)


if __name__ == "__main__":
    unittest.main()
