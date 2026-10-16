import os
import time
import unittest
from fastapi.testclient import TestClient

from app.database import (
    init_db,
    DatabaseContext,
    is_gate_unlocked,
    get_gate_progress,
    save_gate_progress,
    reset_gate_progress,
)
from app.secret_gate import (
    SecretGateManager,
    _GATE_RIDDLES,
    normalize_answer,
    generate_gate_token,
    verify_gate_token,
)
from app.main import app


class SecretGateUnitTests(unittest.TestCase):
    def setUp(self):
        init_db()
        self.manager = SecretGateManager()
        self.test_player_id = f"test-p-{int(time.time()*1000)}"
        reset_gate_progress(self.test_player_id)

    def tearDown(self):
        reset_gate_progress(self.test_player_id)

    def test_normalize_answer(self):
        self.assertEqual(normalize_answer("  Incunable  "), "incunable")
        self.assertEqual(normalize_answer("L'incunable"), "l incunable")
        self.assertEqual(normalize_answer("BÊTA"), "beta")
        self.assertEqual(normalize_answer("Gödelisation"), "godelisation")
        self.assertEqual(normalize_answer("6-EQUJ-5"), "6 equj 5")
        self.assertEqual(normalize_answer("Pater   Noster"), "pater noster")
        self.assertEqual(normalize_answer(""), "")
        self.assertEqual(normalize_answer(None), "")

    def test_gate_token_generation_and_tamper_resistance(self):
        token = generate_gate_token("alice-player")
        self.assertTrue(verify_gate_token(token, "alice-player"))
        self.assertTrue(verify_gate_token(token))  # without explicit player_id check

        # Reject wrong player
        self.assertFalse(verify_gate_token(token, "bob-player"))

        # Reject tampered payload
        tampered = token.replace("alice-player", "hacker-user")
        self.assertFalse(verify_gate_token(tampered, "hacker-user"))

        # Reject invalid signatures or garbage
        self.assertFalse(verify_gate_token("garbage:token:here"))
        self.assertFalse(verify_gate_token("not:enough:parts"))
        self.assertFalse(verify_gate_token(""))
        self.assertFalse(verify_gate_token(None))

    def test_riddle_public_state_never_exposes_solutions_or_hashes(self):
        state = self.manager.get_current_state(self.test_player_id)
        self.assertFalse(state["completed"])
        self.assertEqual(state["step"], 1)
        self.assertIn("riddle", state)
        riddle = state["riddle"]

        self.assertIn("title", riddle)
        self.assertIn("category", riddle)
        self.assertIn("prompt", riddle)
        self.assertNotIn("accepted_hashes", riddle)
        self.assertNotIn("hashes", riddle)
        self.assertNotIn("solution", riddle)
        self.assertNotIn("answer", riddle)

    def test_all_ten_riddles_progression(self):
        solutions = [
            "incunable",
            "omega",
            "6EQUJ5",
            "beta",
            "labyrinthe",
            "godelisation",
            "enheduanna",
            "saros",
            "effacement",
            "pater noster",
        ]

        self.assertEqual(len(solutions), len(_GATE_RIDDLES))

        for idx, sol in enumerate(solutions):
            step_num = idx + 1
            curr = self.manager.get_current_state(self.test_player_id)
            self.assertEqual(curr["step"], step_num)
            self.assertFalse(curr["completed"])

            # Wrong guess test
            # Bypass rate limit by manipulating session timestamp
            sess = self.manager.get_player_session(self.test_player_id)
            sess["last_attempt"] = 0

            is_ok, is_done, res = self.manager.verify_guess(self.test_player_id, "mauvaise reponse")
            self.assertFalse(is_ok)
            self.assertFalse(is_done)
            self.assertFalse(res.get("correct", True))

            # Correct guess
            sess["last_attempt"] = 0
            is_ok, is_done, res = self.manager.verify_guess(self.test_player_id, sol)
            self.assertTrue(is_ok)

            if step_num < 10:
                self.assertFalse(is_done)
                self.assertEqual(res["step"], step_num + 1)
            else:
                self.assertTrue(is_done)
                self.assertTrue(res["completed"])
                self.assertIn("token", res)
                token = res["token"]
                self.assertTrue(verify_gate_token(token, self.test_player_id))

        # Check DB reflects completion
        self.assertTrue(is_gate_unlocked(self.test_player_id))
        final_state = self.manager.get_current_state(self.test_player_id)
        self.assertTrue(final_state["completed"])
        self.assertTrue(verify_gate_token(final_state["token"], self.test_player_id))

    def test_rate_limiting_and_lockout(self):
        sess = self.manager.get_player_session(self.test_player_id)
        sess["last_attempt"] = time.time()  # just made an attempt

        # Second attempt immediately should be rate limited
        is_ok, is_done, res = self.manager.verify_guess(self.test_player_id, "test")
        self.assertFalse(is_ok)
        self.assertIn("error", res)
        self.assertIn("retry_after", res)
        self.assertGreater(res["retry_after"], 0)

        # Trigger consecutive failures lockout
        sess["last_attempt"] = 0
        sess["rapid_fails"] = 4  # one more makes 5 = MAX_RAPID_FAILS
        is_ok, is_done, res = self.manager.verify_guess(self.test_player_id, "wrong")
        self.assertFalse(is_ok)
        self.assertIn("retry_after", res)
        self.assertEqual(res["retry_after"], 15.0)

    def test_reset_progress(self):
        # advance to step 2
        sess = self.manager.get_player_session(self.test_player_id)
        sess["last_attempt"] = 0
        self.manager.verify_guess(self.test_player_id, "incunable")

        state = self.manager.get_current_state(self.test_player_id)
        self.assertEqual(state["step"], 2)

        # Reset
        self.manager.reset_progress(self.test_player_id)
        state_after = self.manager.get_current_state(self.test_player_id)
        self.assertEqual(state_after["step"], 1)


class SecretGateApiTests(unittest.TestCase):
    def setUp(self):
        init_db()
        self.client = TestClient(app)
        self.test_player_id = f"test-client-{int(time.time()*1000)}"
        reset_gate_progress(self.test_player_id)

    def tearDown(self):
        reset_gate_progress(self.test_player_id)

    def test_unauthorized_page_serves_gate_html(self):
        # A fresh visitor to /games/bitoguessr/ without token or completion sees gate.html
        res = self.client.get("/games/bitoguessr/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Le Défi des Dix Sceaux", res.text)
        self.assertIn("LE GARDIEN DU SEUIL", res.text)
        self.assertNotIn("Devine le pays grâce à sa moyenne", res.text)

    def test_unauthorized_api_calls_return_403(self):
        # Attempting to start a solo game without gate completion or token
        res = self.client.post("/api/bitoguessr/solo/new", json={
            "player_id": self.test_player_id,
            "player_name": "Cheater",
            "difficulty": "normal"
        })
        self.assertEqual(res.status_code, 403)
        self.assertIn("Le Gardien interdit l'accès", res.json()["detail"])

        # Attempting to fetch config without token
        res_cfg = self.client.get("/api/bitoguessr/config")
        self.assertEqual(res_cfg.status_code, 403)

    def test_secret_gate_api_current_and_guess_endpoints(self):
        # Get current riddle
        res = self.client.get(f"/api/secret-gate/current?player_id={self.test_player_id}")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertFalse(data["completed"])
        self.assertEqual(data["step"], 1)
        self.assertIn("riddle", data)
        self.assertIn("I. Le Berceau de Plomb", data["riddle"]["title"])

        # Wrong guess
        res_wrong = self.client.post("/api/secret-gate/guess", json={
            "player_id": self.test_player_id,
            "guess": "gutenberg"
        })
        self.assertEqual(res_wrong.status_code, 200)
        self.assertFalse(res_wrong.json().get("correct", False))

        # Wait for 1 second rate limit cooldown
        time.sleep(1.05)

        # Correct guess for step 1
        res_correct = self.client.post("/api/secret-gate/guess", json={
            "player_id": self.test_player_id,
            "guess": "incunable"
        })
        self.assertEqual(res_correct.status_code, 200)
        self.assertTrue(res_correct.json()["correct"])
        self.assertEqual(res_correct.json()["step"], 2)

    def test_authorized_visitor_accesses_game(self):
        # Complete all 10 steps in DB
        save_gate_progress(
            player_id=self.test_player_id,
            step=11,
            completed=True,
            attempts=10,
            last_attempt=time.time(),
        )

        valid_token = generate_gate_token(self.test_player_id)

        # 1. Via cookie (raw and urlencoded)
        res_cookie = self.client.get("/games/bitoguessr/", cookies={"bitoguessr_access_token": valid_token})
        self.assertEqual(res_cookie.status_code, 200)
        self.assertIn("BITOGUESSR", res_cookie.text)
        self.assertIn("Une moyenne, un pays", res_cookie.text)

        import urllib.parse
        encoded_token = urllib.parse.quote(valid_token)
        res_cookie_enc = self.client.get("/games/bitoguessr/", cookies={"bitoguessr_access_token": encoded_token})
        self.assertEqual(res_cookie_enc.status_code, 200)
        self.assertIn("BITOGUESSR", res_cookie_enc.text)

        # 2. Via header
        res_header = self.client.get("/games/bitoguessr/", headers={"x-gate-token": valid_token})
        self.assertEqual(res_header.status_code, 200)
        self.assertIn("BITOGUESSR", res_header.text)

        # 3. Via query param gate_token
        res_query = self.client.get(f"/games/bitoguessr/?gate_token={encoded_token}")
        self.assertEqual(res_query.status_code, 200)
        self.assertIn("BITOGUESSR", res_query.text)

        # 4. Via query param with player_id registered in DB
        res_db = self.client.get(f"/games/bitoguessr/?player_id={self.test_player_id}")
        self.assertEqual(res_db.status_code, 200)
        self.assertIn("BITOGUESSR", res_db.text)

        # 5. Via player_id in cookie with DB completed
        res_cookie_pid = self.client.get("/games/bitoguessr/", cookies={"bitoguessr_player_id": self.test_player_id})
        self.assertEqual(res_cookie_pid.status_code, 200)
        self.assertIn("BITOGUESSR", res_cookie_pid.text)

        # 6. API access allowed with token
        res_api = self.client.post(
            "/api/bitoguessr/solo/new",
            json={
                "player_id": self.test_player_id,
                "player_name": "Champion",
                "difficulty": "normal"
            },
            headers={"x-gate-token": valid_token}
        )
        self.assertEqual(res_api.status_code, 200)
        self.assertIn("game_id", res_api.json())


if __name__ == "__main__":
    unittest.main()
