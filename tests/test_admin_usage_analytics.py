import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import app.database as database
from app.database import generate_user_token
from app.main import app


class AdminUsageAnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "usage-analytics-test.db"
        self.database_path_patch = patch.object(database, "DB_PATH", str(self.database_path))
        self.database_path_patch.start()
        self.assertTrue(database.init_db())
        self.assertEqual(database.create_user("Gwen", "gwen-password")["status"], "ok")
        self.assertEqual(database.create_user("Alice", "alice-password")["status"], "ok")
        self.client = TestClient(app)
        self.gwen_headers = {
            "X-Auth-User": "Gwen",
            "X-Auth-Token": generate_user_token("Gwen"),
        }
        self.alice_headers = {
            "X-Auth-User": "Alice",
            "X-Auth-Token": generate_user_token("Alice"),
        }
        self._insert_sample_sessions()

    def tearDown(self):
        self.database_path_patch.stop()
        self.temp_dir.cleanup()

    def _insert_sample_sessions(self):
        now = datetime.now(timezone.utc).replace(microsecond=0)
        started = now - timedelta(days=1, hours=3)
        ended = started + timedelta(seconds=300)
        active_started = now - timedelta(days=2, hours=1)
        with database.DatabaseContext() as db:
            db.execute(
                """INSERT INTO game_sessions
                   (session_id, game_id, mode, title, difficulty, created_at, finished_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                ("session-finished", "battleship", "multiplayer", "Naval", "medium",
                 started.isoformat(), ended.isoformat()),
            )
            db.execute(
                """INSERT INTO game_sessions
                   (session_id, game_id, mode, title, difficulty, created_at, finished_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                ("session-active", "geoguessr", "solo", "GeoGuessr", "hard",
                 active_started.isoformat(), None),
            )
            for username, won, seconds in (("Gwen", 1, 180), ("Alice", 0, 200)):
                db.execute(
                    """INSERT INTO user_game_stats
                       (username, session_id, game_id, mode, difficulty, title, won,
                        surrendered, attempts, duration_seconds, points, finished_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (username, "session-finished", "battleship", "multiplayer", "medium",
                     "Naval", won, 0, 12, seconds, 50 if won else 20, ended.isoformat()),
                )

    def test_analytics_aggregates_player_time_and_wall_time_separately(self):
        response = self.client.get(
            "/api/admin/usage-analytics?period=30", headers=self.gwen_headers
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["summary"]["sessions_started"], 2)
        self.assertEqual(data["summary"]["sessions_finished"], 1)
        self.assertEqual(data["summary"]["sessions_active"], 1)
        self.assertEqual(data["summary"]["unique_players"], 2)
        self.assertEqual(data["summary"]["participant_results"], 2)
        self.assertEqual(data["summary"]["player_seconds"], 380)
        self.assertEqual(data["summary"]["player_hours"], 0.11)
        self.assertEqual(data["summary"]["wall_seconds"], 300)
        self.assertEqual(data["summary"]["wins"], 1)
        self.assertEqual(data["summary"]["win_rate_pct"], 50)
        self.assertEqual(data["summary"]["total_attempts"], 24)
        self.assertEqual(data["summary"]["avg_attempts"], 12)
        self.assertEqual(data["summary"]["surrenders"], 0)
        self.assertFalse(data["data_scope"]["page_views_tracked"])

        battleship = next(game for game in data["games"] if game["game_id"] == "battleship")
        self.assertEqual(battleship["sessions_started"], 1)
        self.assertEqual(battleship["sessions_finished"], 1)
        self.assertEqual(battleship["unique_players"], 2)
        self.assertEqual(battleship["player_seconds"], 380)
        self.assertEqual(battleship["player_hours"], 0.11)
        self.assertEqual(battleship["wall_seconds"], 300)
        self.assertEqual(battleship["player_time_share_pct"], 100)
        self.assertEqual(battleship["avg_attempts"], 12)
        self.assertEqual(len(data["recent_sessions"]), 2)
        finished_session = next(
            session for session in data["recent_sessions"]
            if session["session_id"] == "session-finished"
        )
        self.assertEqual(finished_session["players"], ["Alice", "Gwen"])
        self.assertEqual(finished_session["player_seconds"], 380)

    def test_analytics_reports_current_google_street_view_quota_usage(self):
        self.assertTrue(database.reserve_geoguessr_google_usage(123, 4_000))

        response = self.client.get(
            "/api/admin/usage-analytics?period=30", headers=self.gwen_headers
        )

        self.assertEqual(response.status_code, 200)
        usage = response.json()["google_maps_usage"]
        self.assertEqual(usage["month"], datetime.now(timezone.utc).strftime("%Y-%m"))
        self.assertEqual(usage["events_reserved"], 123)
        self.assertEqual(usage["monthly_limit"], 4_000)
        self.assertEqual(usage["remaining"], 3_877)
        self.assertEqual(usage["usage_pct"], 3.1)

    def test_analytics_api_is_gwen_only_and_validates_period(self):
        self.assertEqual(
            self.client.get("/api/admin/usage-analytics").status_code, 403
        )
        self.assertEqual(
            self.client.get(
                "/api/admin/usage-analytics", headers=self.alice_headers
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(
                "/api/admin/usage-analytics?period=14", headers=self.gwen_headers
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.get(
                "/api/admin/usage-analytics?period=7", headers=self.gwen_headers
            ).status_code,
            200,
        )

    def test_dashboard_route_serves_the_admin_page(self):
        response = self.client.get("/admin/usage/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Statistiques d’utilisation", response.text)


if __name__ == "__main__":
    unittest.main()
