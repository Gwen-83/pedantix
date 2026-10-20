import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import app.database as database
from app.fermeture_express import FermetureExpressManager, PENALTY_MS, TASKS
from app.main import app


class FermetureExpressManagerTests(unittest.TestCase):
    def test_fixed_tour_applies_server_side_penalty_and_finishes(self):
        manager = FermetureExpressManager()
        initial = manager.start("Alice")
        self.assertEqual(initial["task_count"], 12)
        self.assertNotIn("answer", initial["task"])

        state = manager.submit("Alice", initial["session_id"], (TASKS[0]["answer"] + 1) % 3)
        self.assertEqual(state["mistakes"], 1)
        self.assertEqual(state["penalty_ms"], PENALTY_MS)

        for task in TASKS[1:]:
            state = manager.submit("Alice", initial["session_id"], task["answer"])

        self.assertTrue(state["finished"])
        self.assertEqual(state["completed"], 12)
        self.assertEqual(state["penalty_ms"], PENALTY_MS)
        self.assertGreaterEqual(state["elapsed_ms"], PENALTY_MS)
        retry = manager.submit("Alice", initial["session_id"], 0)
        self.assertEqual(retry["elapsed_ms"], state["elapsed_ms"])
        self.assertEqual(retry["mistakes"], 1)

    def test_session_cannot_be_read_or_submitted_by_another_player(self):
        manager = FermetureExpressManager()
        game = manager.start("Alice")

        with self.assertRaises(KeyError):
            manager.get("Bob", game["session_id"])
        with self.assertRaises(KeyError):
            manager.submit("Bob", game["session_id"], TASKS[0]["answer"])


class FermetureExpressApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path_patch = patch.object(
            database, "DB_PATH", str(Path(self.temp_dir.name) / "fermeture.sqlite3")
        )
        self.db_path_patch.start()
        self.pg_disabled_patch = patch.object(database, "_pg_disabled", True)
        self.pg_disabled_patch.start()
        self.assertTrue(database.init_db())
        alice = database.create_user("ExpressAlice", "password")
        bob = database.create_user("ExpressBob", "password")
        self.alice_headers = {
            "X-Auth-User": alice["username"],
            "X-Auth-Token": alice["token"],
        }
        self.bob_headers = {
            "X-Auth-User": bob["username"],
            "X-Auth-Token": bob["token"],
        }
        self.client = TestClient(app)

    def tearDown(self):
        database._write_q.join()
        self.pg_disabled_patch.stop()
        self.db_path_patch.stop()
        self.temp_dir.cleanup()

    def test_authenticated_run_saves_best_time_and_publishes_leaderboard(self):
        response = self.client.post("/api/fermeture-express/solo/new")
        self.assertEqual(response.status_code, 401)

        response = self.client.post(
            "/api/fermeture-express/solo/new", headers=self.alice_headers
        )
        self.assertEqual(response.status_code, 200)
        game = response.json()
        session_id = game["session_id"]

        self.assertEqual(
            self.client.get(
                f"/api/fermeture-express/solo/{session_id}",
                headers=self.bob_headers,
            ).status_code,
            404,
        )

        for index, task in enumerate(TASKS):
            answer = task["answer"]
            if index == 0:
                answer = (answer + 1) % 3
            response = self.client.post(
                "/api/fermeture-express/solo/submit",
                headers=self.alice_headers,
                json={"session_id": session_id, "answer": answer},
            )
            self.assertEqual(response.status_code, 200)

        result = response.json()
        self.assertTrue(result["finished"])
        self.assertEqual(result["mistakes"], 1)
        self.assertEqual(result["penalty_ms"], PENALTY_MS)
        self.assertTrue(result["record"]["is_record"])

        leaderboard = self.client.get("/api/fermeture-express/leaderboard")
        self.assertEqual(leaderboard.status_code, 200)
        self.assertEqual(leaderboard.json()["records"][0]["username"], "ExpressAlice")

        personal_record = self.client.get(
            "/api/fermeture-express/record", headers=self.alice_headers
        )
        self.assertEqual(personal_record.status_code, 200)
        self.assertEqual(
            personal_record.json()["record"]["elapsed_ms"], result["elapsed_ms"]
        )

    def test_leaderboard_returns_only_top_five_and_refreshes_after_a_new_record(self):
        for index in range(7):
            username = f"ExpressPlayer{index}"
            database.create_user(username, "password")
            database.record_fermeture_express_time(
                username,
                f"existing-session-{index}",
                7000 + index * 1000,
                0,
                0,
            )

        before = self.client.get("/api/fermeture-express/leaderboard").json()["records"]
        self.assertEqual(len(before), 5)
        self.assertEqual(
            [record["elapsed_ms"] for record in before],
            [7000, 8000, 9000, 10000, 11000],
        )

        response = self.client.post(
            "/api/fermeture-express/solo/new", headers=self.alice_headers
        )
        session_id = response.json()["session_id"]
        for task in TASKS:
            response = self.client.post(
                "/api/fermeture-express/solo/submit",
                headers=self.alice_headers,
                json={"session_id": session_id, "answer": task["answer"]},
            )

        after = self.client.get("/api/fermeture-express/leaderboard").json()["records"]
        self.assertEqual(len(after), 5)
        self.assertEqual(after[0]["username"], "ExpressAlice")
        self.assertEqual(
            [record["elapsed_ms"] for record in after],
            sorted(record["elapsed_ms"] for record in after),
        )


if __name__ == "__main__":
    unittest.main()
