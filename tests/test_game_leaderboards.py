import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import app.database as database
from app import main as main_app
from app.main import app


class SoloGameLeaderboardTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path_patch = patch.object(
            database, "DB_PATH", str(Path(self.temp_dir.name) / "leaderboards.sqlite3")
        )
        self.database_path_patch.start()
        self.pg_disabled_patch = patch.object(database, "_pg_disabled", True)
        self.pg_disabled_patch.start()
        self.assertTrue(database.init_db())
        self.client = TestClient(app)

    def tearDown(self):
        self.pg_disabled_patch.stop()
        self.database_path_patch.stop()
        self.temp_dir.cleanup()

    def add_result(
        self,
        username,
        game_id,
        session_id,
        difficulty,
        *,
        won=True,
        mode="solo",
        points=1,
        attempts=1,
        duration=10,
    ):
        with database.DatabaseContext() as db:
            db.execute(
                """INSERT INTO user_game_stats
                   (username, session_id, game_id, mode, difficulty, title, won,
                    attempts, duration_seconds, points)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    username, session_id, game_id, mode, difficulty, game_id,
                    int(won), attempts, duration, points,
                ),
            )

    def test_plongee_ranks_highest_score_and_ignores_unfinished_qualifiers(self):
        self.add_result("Alice", "plongee", "dive-1", "classique", points=900)
        self.add_result("ALICE", "plongee", "dive-2", "classique", points=1300)
        self.add_result("Bob", "plongee", "dive-3", "classique", points=1100)
        self.add_result("Carol", "plongee", "dive-4", "classique", points=2000, won=False)
        self.add_result("Dave", "plongee", "dive-5", "classique", points=2500, mode="multiplayer")

        records = database.get_solo_game_leaderboard("plongee", "classique")

        self.assertEqual([record["player_name"] for record in records], ["ALICE", "Bob"])
        self.assertEqual([record["points"] for record in records], [1300, 1100])

    def test_sudoku_ranks_each_difficulty_by_fastest_solved_game(self):
        self.add_result("Alice", "sudoku", "sudoku-1", "moyen", duration=301, attempts=1)
        self.add_result("Alice", "sudoku", "sudoku-2", "moyen", duration=280, attempts=2)
        self.add_result("Bob", "sudoku", "sudoku-3", "moyen", duration=290, attempts=0)
        self.add_result("Carol", "sudoku", "sudoku-4", "moyen", duration=100, won=False)
        self.add_result("Alice", "sudoku", "sudoku-5", "facile", duration=150)

        medium = database.get_solo_game_leaderboard("sudoku", "moyen")
        easy = database.get_solo_game_leaderboard("sudoku", "facile")

        self.assertEqual([record["player_name"] for record in medium], ["Alice", "Bob"])
        self.assertEqual(medium[0]["duration_seconds"], 280)
        self.assertEqual([record["player_name"] for record in easy], ["Alice"])

    def test_word_games_rank_only_wins_within_the_selected_difficulty(self):
        self.add_result("Alice", "chiffrantix", "cipher-1", "difficile", attempts=8, duration=20)
        self.add_result("Alice", "chiffrantix", "cipher-2", "difficile", attempts=6, duration=30)
        self.add_result("Bob", "chiffrantix", "cipher-3", "difficile", attempts=7, duration=10)
        self.add_result("Carol", "chiffrantix", "cipher-4", "difficile", attempts=1, won=False)
        self.add_result("Alice", "pedantix", "pedia-1", "facile", attempts=4, duration=40)
        self.add_result("Alice", "pedantix", "pedia-2", "difficile", attempts=2, duration=20)

        cipher = database.get_solo_game_leaderboard("chiffrantix", "difficile")
        pedantix = database.get_solo_game_leaderboard("pedantix", "difficile")

        self.assertEqual([record["player_name"] for record in cipher], ["Alice", "Bob"])
        self.assertEqual(cipher[0]["attempts"], 6)
        self.assertEqual([record["player_name"] for record in pedantix], ["Alice"])
        self.assertEqual(pedantix[0]["attempts"], 2)

    def test_leaderboard_api_validates_game_and_difficulty(self):
        response = self.client.get("/api/game-leaderboard?game_id=plongee")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"records": []})

        invalid_game = self.client.get("/api/game-leaderboard?game_id=memory")
        self.assertEqual(invalid_game.status_code, 400)
        invalid_difficulty = self.client.get(
            "/api/game-leaderboard?game_id=sudoku&difficulty=toutes"
        )
        self.assertEqual(invalid_difficulty.status_code, 400)
        missing_difficulty = self.client.get("/api/game-leaderboard?game_id=sudoku")
        self.assertEqual(missing_difficulty.status_code, 400)

    def test_leaderboard_api_reports_database_errors(self):
        with patch.object(
            main_app,
            "get_solo_game_leaderboard",
            side_effect=RuntimeError("Impossible de charger le classement."),
        ):
            response = self.client.get(
                "/api/game-leaderboard?game_id=pedantix&difficulty=moyen"
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "Impossible de charger le classement.")

    def test_featured_home_ranks_one_solo_result_per_difficulty(self):
        self.add_result("Alice", "sudoku", "sudoku-1", "facile", duration=90)
        self.add_result("Bob", "sudoku", "sudoku-2", "facile", duration=70)
        self.add_result("Alice", "sudoku", "sudoku-3", "difficile", duration=300)
        self.add_result(
            "Multi", "sudoku", "sudoku-4", "facile", duration=10, mode="multiplayer"
        )
        self.add_result("Noah", "geoguessr", "geo-1", "world", points=12000, mode="solo")
        self.add_result(
            "Room", "geoguessr", "geo-2", "world", points=50000, mode="multiplayer"
        )
        database.record_memory_solo_time("Mina", 4, "memory-1", 1200, 10)

        response = self.client.get("/api/leaderboards/featured")

        self.assertEqual(response.status_code, 200)
        games = {game["game_id"]: game for game in response.json()["games"]}
        self.assertEqual(len(games), 6)
        sudoku = games["sudoku"]["leaders"]
        easy = next(item for item in sudoku if item["difficulty"] == "facile")
        hard = next(item for item in sudoku if item["difficulty"] == "difficile")
        self.assertEqual(easy["leader"]["player_name"], "Bob")
        self.assertEqual(hard["leader"]["player_name"], "Alice")
        self.assertEqual(games["geoguessr"]["leaders"][0]["leader"]["player_name"], "Noah")
        self.assertEqual(games["memories"]["leaders"][0]["leader"]["player_name"], "Mina")
