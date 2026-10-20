import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app.database as database


class MultiGameStatsMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "legacy.sqlite3"
        self._create_legacy_database()
        self.db_path_patch = patch.object(database, "DB_PATH", str(self.db_path))
        self.db_path_patch.start()
        self.pg_disabled_patch = patch.object(database, "_pg_disabled", True)
        self.pg_disabled_patch.start()
        self.assertTrue(database.init_db())

    def tearDown(self):
        self.pg_disabled_patch.stop()
        self.db_path_patch.stop()
        self.temp_dir.cleanup()

    def _create_legacy_database(self):
        connection = sqlite3.connect(self.db_path)
        connection.executescript(
            """
            CREATE TABLE users (
                username TEXT PRIMARY KEY, password_hash TEXT NOT NULL,
                score INTEGER DEFAULT 0, wins INTEGER DEFAULT 0,
                games_played INTEGER DEFAULT 0, best_attempts INTEGER,
                total_attempts INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE games (
                session_id TEXT PRIMARY KEY, seed TEXT, title TEXT, url TEXT, image TEXT,
                mode TEXT, category TEXT, won INTEGER DEFAULT 0, surrendered INTEGER DEFAULT 0,
                attempts_count INTEGER DEFAULT 0, revealed_words INTEGER DEFAULT 0,
                total_words INTEGER DEFAULT 0, time_seconds INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, finished_at TIMESTAMP
            );
            CREATE TABLE user_game_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL,
                session_id TEXT NOT NULL, mode TEXT NOT NULL, title TEXT NOT NULL,
                won INTEGER NOT NULL DEFAULT 0, surrendered INTEGER NOT NULL DEFAULT 0,
                attempts INTEGER NOT NULL DEFAULT 0, duration_seconds INTEGER NOT NULL DEFAULT 0,
                points INTEGER NOT NULL DEFAULT 0, revealed_words INTEGER NOT NULL DEFAULT 0,
                total_words INTEGER NOT NULL DEFAULT 0,
                finished_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (username, session_id)
            );
            INSERT INTO users (username, password_hash, score) VALUES ('Alice', 'kept-hash', 7);
            INSERT INTO games (session_id, title, mode, won, attempts_count, finished_at)
                VALUES ('old-pedantix-session', 'Ancien article', 'solo', 1, 4, CURRENT_TIMESTAMP);
            INSERT INTO user_game_stats
                (username, session_id, mode, title, won, attempts, points)
                VALUES ('Alice', 'old-pedantix-session', 'solo', 'Ancien article', 1, 4, 2);
            """
        )
        connection.commit()
        connection.close()

    def test_migration_preserves_accounts_and_attributes_old_stats_to_pedantix(self):
        with database.DatabaseContext() as db:
            db.execute("SELECT username, password_hash, score FROM users WHERE username = ?", ("Alice",))
            user = db.fetchone()
            db.execute(
                "SELECT game_id FROM user_game_stats WHERE session_id = ?",
                ("old-pedantix-session",),
            )
            old_stats = db.fetchone()
            db.execute(
                "SELECT game_id FROM game_sessions WHERE session_id = ?",
                ("old-pedantix-session",),
            )
            old_session = db.fetchone()

        self.assertEqual(user["password_hash"], "kept-hash")
        self.assertEqual(user["score"], 7)
        self.assertEqual(old_stats["game_id"], "pedantix")
        self.assertEqual(old_session["game_id"], "pedantix")
        self.assertEqual(database.get_user_stats("Alice")["games_played"], 1)

    def test_migration_removes_retired_game_from_catalog(self):
        with database.DatabaseContext() as db:
            db.execute(
                "INSERT INTO game_catalog (game_id, display_name, enabled) VALUES (?, ?, 1)",
                ("fermeture-express", "Fermeture express"),
            )
            database._migrate_multigame_schema(db)

        self.assertNotIn(
            "fermeture-express",
            {item["game_id"] for item in database.get_game_catalog()},
        )

    def test_migration_splits_existing_cross_game_score_without_losing_pedantix_points(self):
        with database.DatabaseContext() as db:
            db.execute(
                """INSERT INTO player_scores (player_name, score, wins, games_played)
                   VALUES (?, 20407, 2, 3)
                   ON CONFLICT (player_name) DO UPDATE SET score = EXCLUDED.score""",
                ("Alice",),
            )
            db.execute(
                """INSERT INTO user_game_stats
                       (username, session_id, game_id, mode, title, points)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                ("Alice", "geoguessr:old-game", "geoguessr", "solo", "GeoGuessr", 20_000),
            )
            db.execute(
                """INSERT INTO user_game_stats
                       (username, session_id, game_id, mode, title, points)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                ("Alice", "motus:old-game", "motus", "solo", "Motus", 400),
            )
            db.execute("DELETE FROM player_game_scores WHERE player_name = ?", ("Alice",))
            database._migrate_multigame_schema(db)

        self.assertEqual(database.get_player_score("Alice", "pedantix"), 7)
        self.assertEqual(database.get_player_score("Alice", "geoguessr"), 20_000)
        self.assertEqual(database.get_player_score("Alice", "motus"), 400)
        self.assertEqual(database.get_user_stats("Alice", "pedantix")["score"], 7)
        self.assertEqual(database.get_user_stats("Alice", "geoguessr")["score"], 20_000)
        self.assertEqual(database.get_top_player_scores(game_id="pedantix")[0]["score"], 7)
        self.assertEqual(database.get_top_player_scores(game_id="geoguessr")[0]["score"], 20_000)

    def test_game_results_and_stats_are_isolated_by_game(self):
        database._record_user_game_finish_sync(
            "Alice",
            True,
            3,
            0,
            "motus:solo-session",
            "solo",
            "Motus",
            False,
            45,
            0,
            0,
            "motus",
            "difficile",
            {"score": 400, "max_attempts": 4},
        )

        motus_stats = database.get_user_stats("Alice", "motus")
        pedantix_stats = database.get_user_stats("Alice", "pedantix")
        global_motus_stats = database.get_stats("motus")

        self.assertEqual(motus_stats["games_played"], 1)
        self.assertEqual(motus_stats["wins"], 1)
        self.assertEqual(motus_stats["difficulty_breakdown"]["difficile"]["games_played"], 1)
        self.assertEqual(motus_stats["game_metrics"]["avg_score"], 400)
        self.assertEqual(motus_stats["recent_games"][0]["metrics"]["score"], 400)
        self.assertEqual(pedantix_stats["games_played"], 1)
        self.assertEqual(global_motus_stats["total_games"], 1)
        self.assertEqual(global_motus_stats["finished_games"], 1)
        self.assertEqual(
            global_motus_stats["difficulty_breakdown"]["difficile"]["games_played"],
            1,
        )

    def test_geoguessr_leaderboard_uses_each_players_best_single_game_and_limits_to_five(self):
        results = [
            ("Alice", "game-1", 18_000),
            ("Alice", "game-2", 22_000),
            ("Bob", "game-1", 19_000),
            ("Chloe", "game-1", 25_000),
            ("David", "game-1", 17_000),
            ("Emma", "game-1", 20_000),
            ("Farid", "game-1", 15_000),
        ]
        for username, game_id, points in results:
            database._record_user_game_finish_sync(
                username,
                False,
                5,
                points,
                f"geoguessr:{username}:{game_id}",
                "solo",
                "GeoGuessr",
                False,
                120,
                0,
                0,
                "geoguessr",
            )

        leaderboard = database.get_top_geoguessr_scores()

        self.assertEqual(
            [(entry["player_name"], entry["score"]) for entry in leaderboard],
            [
                ("Chloe", 25_000),
                ("Alice", 22_000),
                ("Emma", 20_000),
                ("Bob", 19_000),
                ("David", 17_000),
            ],
        )

    def test_global_results_count_a_multiplayer_session_once(self):
        database._record_multigame_session_start_sync(
            "sudoku:room-1", "sudoku", "multiplayer", "Sudoku", "moyen"
        )
        for username, won, rank in (("Alice", True, 1), ("Bob", True, 2)):
            database._record_user_game_finish_sync(
                username,
                won,
                2,
                2 if won else 1,
                "sudoku:room-1",
                "multiplayer",
                "Sudoku",
                False,
                120,
                0,
                0,
                "sudoku",
                "moyen",
                {"mistakes": 2, "rank": rank, "finish_reason": "podium"},
            )

        stats = database.get_stats("sudoku")

        self.assertEqual(stats["total_games"], 1)
        self.assertEqual(stats["finished_games"], 1)
        self.assertEqual(stats["won_games"], 1)
        self.assertEqual(stats["win_rate"], 100.0)

    def test_geoguessr_metrics_are_summarized_per_game(self):
        database._record_user_game_finish_sync(
            "Alice",
            True,
            5,
            18_500,
            "geoguessr:solo-session",
            "solo",
            "GeoGuessr",
            False,
            180,
            0,
            0,
            "geoguessr",
            "europe",
            {
                "score": 18_500,
                "average_distance_km": 1_250.0,
                "best_distance_km": 0.0,
                "rounds": 5,
                "perfect_rounds": 1,
                "region": "europe",
            },
        )

        stats = database.get_user_stats("Alice", "geoguessr")
        self.assertEqual(stats["games_played"], 1)
        self.assertEqual(stats["game_metrics"]["avg_score"], 18_500)
        self.assertEqual(stats["game_metrics"]["best_score"], 18_500)
        self.assertEqual(stats["game_metrics"]["avg_distance_km"], 1_250.0)
        self.assertEqual(stats["recent_games"][0]["difficulty"], "europe")

    def test_bitoguessr_metrics_are_summarized_per_game(self):
        database._record_user_game_finish_sync(
            "Alice",
            True,
            10,
            7,
            "bitoguessr:solo-session",
            "solo",
            "Bitoguessr",
            False,
            120,
            0,
            0,
            "bitoguessr",
            "normal",
            {"score": 7, "correct_answers": 7, "rounds": 10},
        )

        stats = database.get_user_stats("Alice", "bitoguessr")
        self.assertEqual(stats["games_played"], 1)
        self.assertEqual(stats["game_metrics"]["avg_score"], 7)
        self.assertEqual(stats["game_metrics"]["best_score"], 7)
        self.assertEqual(stats["game_metrics"]["avg_accuracy"], 70.0)

    def test_catalog_lists_enabled_games(self):
        catalog = database.get_game_catalog()
        self.assertEqual(
            {item["game_id"] for item in catalog},
            {
                "pedantix", "motus", "cemantix", "chiffrantix", "sudoku", "battleship",
                "geoguessr", "undercover", "bitoguessr", "plongee", "memories",
            },
        )

    def test_stats_overview_counts_started_and_finished_sessions_once(self):
        baseline = database.get_stats_overview()
        database._record_multigame_session_start_sync(
            "sudoku:overview-room", "sudoku", "multiplayer", "Sudoku", "moyen"
        )
        for username, won in (("Alice", True), ("Bob", False)):
            database._record_user_game_finish_sync(
                username,
                won,
                2,
                1,
                "sudoku:overview-room",
                "multiplayer",
                "Sudoku",
                False,
                120,
                0,
                0,
                "sudoku",
                "moyen",
                {"mistakes": 2},
            )
        database._record_multigame_session_start_sync(
            "sudoku:overview-unfinished", "sudoku", "solo", "Sudoku", "facile"
        )

        overview = database.get_stats_overview()
        sudoku = next(game for game in overview["games"] if game["game_id"] == "sudoku")

        self.assertEqual(sudoku["started_games"], 2)
        self.assertEqual(sudoku["finished_games"], 1)
        self.assertEqual(overview["started_games"], baseline["started_games"] + 2)
        self.assertEqual(overview["finished_games"], baseline["finished_games"] + 1)

    def test_started_but_unfinished_session_is_counted_separately(self):
        database._record_multigame_session_start_sync(
            "sudoku:unfinished", "sudoku", "solo", "Sudoku", "facile"
        )

        stats = database.get_stats("sudoku")

        self.assertEqual(stats["total_games"], 1)
        self.assertEqual(stats["finished_games"], 0)
        self.assertEqual(stats["win_rate"], 0.0)


if __name__ == "__main__":
    unittest.main()
