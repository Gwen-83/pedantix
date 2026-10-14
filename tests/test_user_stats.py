import unittest
import uuid

from app.database import (
    DatabaseContext,
    _increment_sync,
    _record_user_game_finish_sync,
    get_stats,
    get_user_stats,
    init_db,
)


class UserGameStatsTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(init_db())
        self.username = f"test_stats_{uuid.uuid4().hex}"
        self.game_session_ids = []
        with DatabaseContext() as db:
            db.execute("DELETE FROM user_game_stats WHERE username = ?", (self.username,))
            db.execute("DELETE FROM player_scores WHERE player_name = ?", (self.username,))

    def tearDown(self):
        with DatabaseContext() as db:
            db.execute("DELETE FROM user_game_stats WHERE username = ?", (self.username,))
            db.execute("DELETE FROM player_scores WHERE player_name = ?", (self.username,))
            if self.game_session_ids:
                placeholders = ", ".join("?" for _ in self.game_session_ids)
                db.execute(
                    f"DELETE FROM games WHERE session_id IN ({placeholders})",
                    tuple(self.game_session_ids),
                )

    def test_stats_are_split_by_mode_and_calculated_from_finished_rounds(self):
        _increment_sync(self.username, 3)
        _record_user_game_finish_sync(
            self.username,
            True,
            5,
            3,
            "solo-session-1",
            "solo",
            "Article solo",
            False,
            100,
            8,
            10,
        )
        _record_user_game_finish_sync(
            self.username,
            False,
            12,
            0,
            "multi-session-1",
            "multiplayer",
            "Article multi",
            False,
            80,
            9,
            10,
        )

        stats = get_user_stats(self.username)

        self.assertEqual(stats["games_played"], 2)
        self.assertEqual(stats["wins"], 1)
        self.assertEqual(stats["win_rate"], 50.0)
        self.assertEqual(stats["avg_attempts"], 8.5)
        self.assertEqual(stats["avg_winning_attempts"], 5.0)
        self.assertEqual(stats["best_attempts"], 5)
        self.assertEqual(stats["score"], 3)
        self.assertEqual(stats["solo"]["games_played"], 1)
        self.assertEqual(stats["solo"]["win_rate"], 100.0)
        self.assertEqual(stats["solo"]["avg_time_seconds"], 100.0)
        self.assertEqual(stats["solo"]["avg_revealed_pct"], 80.0)
        self.assertEqual(stats["solo"]["points"], 3)
        self.assertEqual(stats["multiplayer"]["games_played"], 1)
        self.assertEqual(stats["multiplayer"]["wins"], 0)
        self.assertEqual(stats["multiplayer"]["win_rate"], 0.0)
        self.assertEqual(stats["multiplayer"]["avg_attempts"], 12.0)
        self.assertEqual(stats["multiplayer"]["avg_revealed_pct"], 90.0)
        self.assertEqual(len(stats["recent_games"]), 2)

    def test_duplicate_finish_does_not_increment_game_or_win_totals_again(self):
        finish = (
            self.username,
            True,
            4,
            3,
            "same-session",
            "multiplayer",
            "Article",
            False,
            50,
            10,
            10,
        )
        _record_user_game_finish_sync(*finish)
        _record_user_game_finish_sync(*finish)

        stats = get_user_stats(self.username)

        self.assertEqual(stats["games_played"], 1)
        self.assertEqual(stats["wins"], 1)
        self.assertEqual(stats["multiplayer"]["points"], 3)
        with DatabaseContext() as db:
            db.execute("SELECT wins, games_played FROM player_scores WHERE player_name = ?", (self.username,))
            score_row = db.fetchone()
        self.assertEqual(score_row["wins"], 1)
        self.assertEqual(score_row["games_played"], 1)

    def test_adding_points_does_not_count_as_an_extra_win_or_game(self):
        _increment_sync(self.username, 3)

        with DatabaseContext() as db:
            db.execute("SELECT score, wins, games_played FROM player_scores WHERE player_name = ?", (self.username,))
            score_row = db.fetchone()

        self.assertEqual(score_row["score"], 3)
        self.assertEqual(score_row["wins"], 0)
        self.assertEqual(score_row["games_played"], 0)

    def test_global_stats_separate_modes_and_exclude_unfinished_sessions_from_rate(self):
        baseline = get_stats()
        self.game_session_ids = [
            f"{self.username}_{mode}" for mode in ("solo", "multiplayer", "unfinished")
        ]
        with DatabaseContext() as db:
            db.execute(
                """INSERT INTO games
                       (session_id, title, mode, category, won, attempts_count, revealed_words,
                        total_words, time_seconds, finished_at)
                   VALUES (?, ?, ?, ?, 1, 4, 8, 10, 60, CURRENT_TIMESTAMP)""",
                (self.game_session_ids[0], "Global solo", "solo", "test"),
            )
            db.execute(
                """INSERT INTO games
                       (session_id, title, mode, category, won, attempts_count, revealed_words,
                        total_words, time_seconds, finished_at)
                   VALUES (?, ?, ?, ?, 0, 8, 5, 10, 90, CURRENT_TIMESTAMP)""",
                (self.game_session_ids[1], "Global multi", "multiplayer", "test"),
            )
            db.execute(
                """INSERT INTO games
                       (session_id, title, mode, category, won, attempts_count, finished_at)
                   VALUES (?, ?, ?, ?, 0, 0, NULL)""",
                (self.game_session_ids[2], "Ongoing", "solo", "test"),
            )

        stats = get_stats()

        self.assertEqual(stats["total_games"], baseline["total_games"] + 3)
        self.assertEqual(stats["finished_games"], baseline["finished_games"] + 2)
        self.assertEqual(stats["won_games"], baseline["won_games"] + 1)
        self.assertEqual(stats["win_rate"], round(stats["won_games"] / stats["finished_games"] * 100, 1))
        self.assertEqual(stats["modes"]["solo"]["games_played"], baseline["modes"].get("solo", {}).get("games_played", 0) + 1)
        self.assertEqual(
            stats["modes"]["multiplayer"]["games_played"],
            baseline["modes"].get("multiplayer", {}).get("games_played", 0) + 1,
        )

if __name__ == "__main__":
    unittest.main()
