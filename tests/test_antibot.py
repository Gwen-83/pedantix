from collections import deque
import unittest
from unittest.mock import patch

from app.antibot import AntiBotGuard


class TestAntiBotGuard(unittest.TestCase):
    def test_allows_fast_human_burst(self):
        guard = AntiBotGuard()
        timestamps = [100.0 + i * 0.15 for i in range(10)]
        with patch("app.antibot.time.time", side_effect=[t for t in timestamps for _ in range(2)]):
            results = [guard.check_rate_limit("fast-player") for _ in range(10)]

        self.assertTrue(all(allowed for allowed, _, _ in results))

    def test_throttles_sustained_automated_burst(self):
        guard = AntiBotGuard()
        timestamps = [100.0 + i * 0.11 for i in range(20)]
        with patch("app.antibot.time.time", side_effect=[t for t in timestamps for _ in range(2)]):
            results = [guard.check_rate_limit("automated-player") for _ in timestamps]

        self.assertTrue(all(allowed for allowed, _, _ in results[:12]))
        self.assertTrue(all(not allowed for allowed, _, _ in results[12:]))

    def test_successful_guesses_reduce_rapid_strikes(self):
        guard = AntiBotGuard()
        guard.players["recovering-player"] = {
            "last_guess_time": 0.0,
            "history": deque(maxlen=40),
            "rapid_strikes": 3,
            "penalty_until": 0.0,
            "token": "token",
            "token_issued_at": 100.0,
        }
        with patch("app.antibot.time.time", return_value=100.0):
            allowed, _, _ = guard.check_rate_limit("recovering-player")

        self.assertTrue(allowed)
        self.assertEqual(guard.players["recovering-player"]["rapid_strikes"], 2)

    def test_stale_guess_token_does_not_invalidate_the_current_token(self):
        guard = AntiBotGuard()
        stale_token = guard.get_or_issue_token("shared-player")
        valid, _, current_token = guard.verify_token("shared-player", stale_token)

        self.assertTrue(valid)
        self.assertNotEqual(current_token, stale_token)

        valid, error, refreshed_token = guard.verify_token("shared-player", stale_token)

        self.assertFalse(valid)
        self.assertIn("invalide", error)
        self.assertEqual(refreshed_token, current_token)
        self.assertEqual(guard.players["shared-player"]["token"], current_token)

        valid, _, next_token = guard.verify_token("shared-player", refreshed_token)
        self.assertTrue(valid)
        self.assertNotEqual(next_token, current_token)


if __name__ == "__main__":
    unittest.main()
