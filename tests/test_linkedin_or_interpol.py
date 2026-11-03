import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.linkedin_or_interpol import LinkedinOrInterpolManager
from app.main import app


class LinkedinOrInterpolTests(unittest.TestCase):
    def setUp(self):
        self.manager = LinkedinOrInterpolManager()
        self.client = TestClient(app)

    def test_dataset_is_loaded_and_has_valid_labels(self):
        dataset = self.manager.dataset
        self.assertGreater(len(dataset), 0)
        self.assertTrue({entry["label"] for entry in dataset}.issubset({"linkedin", "interpol"}))
        for entry in dataset:
            self.assertIn("image_path", entry)
            self.assertIn("source_url", entry)

    def test_dataset_matches_available_portrait_assets(self):
        images_dir = Path(__file__).resolve().parent.parent / "app" / "data" / "linkedin_or_interpol" / "images"
        available = sorted(images_dir.glob("*.webp"))
        self.assertGreaterEqual(len(available), 500)
        self.assertGreaterEqual(len(self.manager.dataset), len(available) * 0.95)
        self.assertGreaterEqual(len(self.manager.dataset), 500)

    def test_linkedin_catalog_exposes_rarity_and_repeat_cache_metadata(self):
        catalog = self.manager.get_catalog(limit=5)
        self.assertGreater(len(catalog), 0)
        first = catalog[0]
        self.assertIn("rarity_label", first)
        self.assertIn("rarity_rank", first)
        self.assertIn("seen_total", first)
        self.assertIn("draw_weight", first)

    def test_rarity_is_stable_by_profile_and_manual_profiles_are_top_rarity(self):
        self.manager._draw_history = {entry["id"]: (index % 5) + 1 for index, entry in enumerate(self.manager.dataset)}
        manual_profiles = [entry for entry in self.manager.dataset if entry.get("source") == "local-fallback"]
        self.assertGreater(len(manual_profiles), 0)

        for person in manual_profiles:
            profile = self.manager._profile_rarity(person)
            self.assertEqual(profile["rarity_rank"], 1)
            self.assertEqual(profile["rarity_label"], "Très rare")

        public_profiles = [entry for entry in self.manager.dataset if entry.get("source") != "local-fallback"]
        self.assertGreater(len(public_profiles), 0)
        for person in public_profiles[:20]:
            profile = self.manager._profile_rarity(person)
            self.assertGreaterEqual(profile["rarity_rank"], 2)

    def test_create_game_builds_rounds_and_hides_identity_and_activities_before_guess(self):
        state = self.manager.create_game("alice", rounds=3)
        self.assertEqual(state["status"], "playing")
        self.assertEqual(state["round_count"], 3)
        self.assertIsNotNone(state["current_person"])
        self.assertEqual(set(state["current_person"].keys()), {"id", "image_url"})
        self.assertNotIn("name", state["current_person"])
        self.assertNotIn("surname", state["current_person"])
        self.assertNotIn("description", state["current_person"])
        self.assertNotIn("source_url", state["current_person"])
        self.assertNotIn("label", state["current_person"])
        self.assertNotIn("answer", state["current_person"])

        internal = self.manager.games[state["game_id"]]
        self.assertEqual(len(internal["rounds"]), 3)
        self.assertIn("label", internal["rounds"][0])

    def test_submit_guess_evaluates_correct_answer_and_reveals_identity(self):
        state = self.manager.create_game("alice", rounds=2)
        internal = self.manager.games[state["game_id"]]
        guess = internal["rounds"][internal["round_index"]]["label"]
        result = self.manager.submit_guess(state["game_id"], "alice", guess)
        self.assertTrue(result["result"]["correct"])
        self.assertEqual(result["score"], 1)
        self.assertEqual(result["round_index"], 1)
        self.assertIn("name", result["result"])
        self.assertIn("description", result["result"])
        self.assertEqual(result["result"]["answer"], guess)

    def test_create_game_supports_solo_and_multiplayer_modes(self):
        solo = self.manager.create_game("alice", rounds=10, mode="solo")
        multi = self.manager.create_game("alice", rounds=10, mode="multiplayer")

        self.assertEqual(solo["mode"], "solo")
        self.assertEqual(multi["mode"], "multiplayer")
        self.assertEqual(solo["round_count"], 10)
        self.assertEqual(multi["round_count"], 10)
        self.assertEqual(solo["status"], "playing")
        self.assertEqual(multi["status"], "playing")

    def test_create_infinite_game_tracks_streak_and_best_record(self):
        state = self.manager.create_game("alice", rounds=1, mode="solo-infinite")
        internal = self.manager.games[state["game_id"]]
        self.assertEqual(state["mode"], "solo-infinite")
        self.assertEqual(state["streak"], 0)
        self.assertEqual(state["best_streak"], 0)

        correct_guess = internal["rounds"][internal["round_index"]]["label"]
        result = self.manager.submit_guess(state["game_id"], "alice", correct_guess)
        self.assertTrue(result["result"]["correct"])
        self.assertEqual(result["streak"], 1)
        self.assertEqual(result["best_streak"], 1)
        self.assertEqual(result["status"], "playing")

        internal = self.manager.games[state["game_id"]]
        current_label = internal["rounds"][internal["round_index"]]["label"]
        wrong_guess = "linkedin" if current_label == "interpol" else "interpol"
        failed = self.manager.submit_guess(state["game_id"], "alice", wrong_guess)
        self.assertFalse(failed["result"]["correct"])
        self.assertEqual(failed["streak"], 0)
        self.assertEqual(failed["best_streak"], 1)
        self.assertEqual(failed["status"], "finished")

    def test_special_friend_case_accepts_both_answers_with_custom_message(self):
        state = self.manager.create_game("alice", rounds=1)
        game_id = state["game_id"]
        self.manager.games[game_id]["rounds"][0] = {
            "id": "friend-ami",
            "name": "Ami",
            "surname": "",
            "description": "Un ami qui va bientôt basculer côté Interpol.",
            "label": "linkedin",
            "special_case": "friend",
            "image_path": "images/friend-ami.webp",
            "source_url": "https://example.com/ami",
        }

        linked_in_result = self.manager.submit_guess(game_id, "alice", "linkedin")
        self.assertTrue(linked_in_result["result"]["correct"])
        self.assertEqual(
            linked_in_result["result"]["message"],
            "Oui, mais bientôt ça sera interpol.",
        )

        state = self.manager.create_game("bob", rounds=1)
        game_id = state["game_id"]
        self.manager.games[game_id]["rounds"][0] = {
            "id": "friend-ami",
            "name": "Ami",
            "surname": "",
            "description": "Un ami qui va bientôt basculer côté Interpol.",
            "label": "linkedin",
            "special_case": "friend",
            "image_path": "images/friend-ami.webp",
            "source_url": "https://example.com/ami",
        }

        interpol_result = self.manager.submit_guess(game_id, "bob", "interpol")
        self.assertTrue(interpol_result["result"]["correct"])
        self.assertEqual(
            interpol_result["result"]["message"],
            "C’était linkedin, mais interpol accepté, c’est un malade.",
        )

    def test_solo_step_by_step_hides_identity_before_guess_and_reveals_after_guess(self):
        game = self.manager.create_solo("p1", "Alice", mode="solo", round_count=2)
        initial_state = self.manager.solo_state(game)
        self.assertEqual(set(initial_state["current_person"].keys()), {"id", "image_url"})
        self.assertIsNone(initial_state["result"])
        self.assertFalse(initial_state["awaiting_next"])

        first_label = game.rounds[0]["label"]
        game, round1_result = self.manager.guess_solo(game.game_id, "p1", first_label)
        after_guess = self.manager.solo_state(game)
        self.assertTrue(after_guess["awaiting_next"])
        self.assertEqual(after_guess["status"], "playing")
        self.assertTrue(round1_result["correct"])
        self.assertTrue(round1_result["full_name"])
        self.assertIn("description", round1_result)
        self.assertNotIn("source_url", round1_result)
        self.assertNotIn("source_url", after_guess["current_person"])
        self.assertEqual(after_guess["current_person"]["answer"], first_label)

        # Advance to round 2: identity must be hidden again for the new person
        game = self.manager.next_solo(game.game_id, "p1")
        round2_state = self.manager.solo_state(game)
        self.assertFalse(round2_state["awaiting_next"])
        self.assertIsNone(round2_state["result"])
        self.assertEqual(round2_state["round_number"], 2)
        self.assertEqual(set(round2_state["current_person"].keys()), {"id", "image_url"})

        second_label = game.rounds[1]["label"]
        game, round2_result = self.manager.guess_solo(game.game_id, "p1", second_label)
        final_state = self.manager.solo_state(game)
        self.assertEqual(final_state["status"], "finished")
        self.assertEqual(final_state["score"], 2)
        self.assertEqual(round2_result["round_number"], 2)
        self.assertIn("description", final_state["result"])

    def test_multiplayer_room_lifecycle_hides_person_until_all_active_players_guess(self):
        room = self.manager.create_room("host-1", "Alice", round_count=2)
        self.manager.join_room(room.room_id, "guest-2", "Bob")
        self.manager.start_room(room.room_id, "host-1")

        # Late joiner becomes spectator during active match
        self.manager.join_room(room.room_id, "spec-3", "Charlie")
        spec_state = self.manager.room_state(room, "spec-3")
        self.assertTrue(spec_state["is_spectator"])

        host_state = self.manager.room_state(room, "host-1")
        self.assertEqual(set(host_state["current_person"].keys()), {"id", "image_url"})
        self.assertIsNone(host_state["last_round"])

        # Host answers round 1; Bob hasn't answered yet -> identity still hidden!
        round1_answer = room.rounds[0].person["label"]
        room, partial = self.manager.guess_room(room.room_id, "host-1", round1_answer)
        self.assertIsNone(partial)
        mid_state = self.manager.room_state(room, "host-1")
        self.assertIsNone(mid_state["last_round"])
        self.assertEqual(set(mid_state["current_person"].keys()), {"id", "image_url"})
        self.assertTrue(mid_state["player"]["submitted"])

        # Bob answers round 1 -> round completes and identity/activities are revealed!
        wrong_answer = "interpol" if round1_answer == "linkedin" else "linkedin"
        room, revealed = self.manager.guess_room(room.room_id, "guest-2", wrong_answer)
        self.assertIsNotNone(revealed)
        self.assertEqual(revealed["answer"], round1_answer)
        self.assertTrue(revealed["full_name"])
        self.assertIn("description", revealed)
        completed_state = self.manager.room_state(room, "host-1")
        self.assertTrue(completed_state["awaiting_next_round"])

        # Host advances to round 2 -> identity hidden again
        self.manager.next_room(room.room_id, "host-1")
        round2_state = self.manager.room_state(room, "host-1")
        self.assertFalse(round2_state["awaiting_next_round"])
        self.assertIsNone(round2_state["last_round"])
        self.assertEqual(set(round2_state["current_person"].keys()), {"id", "image_url"})

        # Both answer round 2 -> match finishes
        round2_answer = room.rounds[1].person["label"]
        self.manager.guess_room(room.room_id, "host-1", round2_answer)
        self.manager.guess_room(room.room_id, "guest-2", round2_answer)
        finished_state = self.manager.room_state(room, "host-1")
        self.assertEqual(finished_state["status"], "finished")
        self.assertIsNotNone(finished_state["last_round"])

        # Restart promotes spectator Charlie to active player
        self.manager.restart_room(room.room_id, "host-1")
        restarted_state = self.manager.room_state(room, "spec-3")
        self.assertEqual(restarted_state["status"], "playing")
        self.assertEqual(restarted_state["match_number"], 2)
        self.assertFalse(restarted_state["is_spectator"])
        self.assertEqual(restarted_state["player_count"], 3)

    def test_api_endpoints_for_solo_and_multiplayer_rooms(self):
        solo_res = self.client.post(
            "/api/linkedin-or-interpol/solo/new",
            json={
                "player_id": "api-solo-1",
                "player_name": "Alice",
                "mode": "solo",
                "round_count": 2,
            },
        )
        self.assertEqual(solo_res.status_code, 200)
        solo_data = solo_res.json()
        self.assertEqual(set(solo_data["current_person"].keys()), {"id", "image_url"})

        guess_res = self.client.post(
            "/api/linkedin-or-interpol/solo/guess",
            json={
                "player_id": "api-solo-1",
                "player_name": "Alice",
                "game_id": solo_data["game_id"],
                "guess": "linkedin",
            },
        )
        self.assertEqual(guess_res.status_code, 200)
        guess_data = guess_res.json()
        self.assertIsNotNone(guess_data["result"])
        self.assertIn("description", guess_data["result"])
        self.assertIn("full_name", guess_data["result"])

        next_res = self.client.post(
            "/api/linkedin-or-interpol/solo/next",
            json={
                "player_id": "api-solo-1",
                "player_name": "Alice",
                "game_id": solo_data["game_id"],
            },
        )
        self.assertEqual(next_res.status_code, 200)
        self.assertEqual(next_res.json()["round_number"], 2)
        self.assertEqual(set(next_res.json()["current_person"].keys()), {"id", "image_url"})

        finish_res = self.client.post(
            "/api/linkedin-or-interpol/solo/guess",
            json={
                "player_id": "api-solo-1",
                "player_name": "Alice",
                "game_id": solo_data["game_id"],
                "guess": "interpol",
            },
        )
        self.assertEqual(finish_res.status_code, 200)
        self.assertEqual(finish_res.json()["status"], "finished")

        get_finished_res = self.client.get(
            f"/api/linkedin-or-interpol/solo/{solo_data['game_id']}?player_id=api-solo-1"
        )
        self.assertEqual(get_finished_res.status_code, 200)
        self.assertEqual(get_finished_res.json()["status"], "finished")

        # Solo infinite mode continues after a wrong answer
        inf_res = self.client.post(
            "/api/linkedin-or-interpol/solo/new",
            json={
                "player_id": "api-solo-inf",
                "player_name": "Alice",
                "mode": "solo-infinite",
                "round_count": 10,
            },
        )
        self.assertEqual(inf_res.status_code, 200)
        inf_id = inf_res.json()["game_id"]
        for guess in ("linkedin", "interpol"):
            step = self.client.post(
                "/api/linkedin-or-interpol/solo/guess",
                json={
                    "player_id": "api-solo-inf",
                    "player_name": "Alice",
                    "game_id": inf_id,
                    "guess": guess,
                },
            )
            self.assertEqual(step.status_code, 200)
            self.assertEqual(step.json()["status"], "playing")
            self.assertTrue(step.json()["awaiting_next"])
            adv = self.client.post(
                "/api/linkedin-or-interpol/solo/next",
                json={
                    "player_id": "api-solo-inf",
                    "player_name": "Alice",
                    "game_id": inf_id,
                },
            )
            self.assertEqual(adv.status_code, 200)
            self.assertEqual(adv.json()["status"], "playing")

        # Room endpoints
        room_res = self.client.post(
            "/api/linkedin-or-interpol/room/create",
            json={"player_id": "room-host", "player_name": "Alice", "round_count": 5},
        )
        self.assertEqual(room_res.status_code, 200)
        room_id = room_res.json()["room_id"]

        join_res = self.client.post(
            "/api/linkedin-or-interpol/room/join",
            json={"room_id": room_id, "player_id": "room-guest", "player_name": "Bob"},
        )
        self.assertEqual(join_res.status_code, 200)
        self.assertTrue(join_res.json()["can_start"])

        start_res = self.client.post(
            "/api/linkedin-or-interpol/room/start",
            json={"room_id": room_id, "player_id": "room-host", "player_name": "Alice"},
        )
        self.assertEqual(start_res.status_code, 200)
        self.assertEqual(start_res.json()["status"], "playing")
        self.assertEqual(set(start_res.json()["current_person"].keys()), {"id", "image_url"})

        leave_res = self.client.post(
            "/api/linkedin-or-interpol/room/leave",
            json={"room_id": room_id, "player_id": "room-guest"},
        )
        self.assertEqual(leave_res.status_code, 200)
        self.assertEqual(leave_res.json()["status"], "left")

    def test_linkedin_leaderboard_endpoint_queries_database(self):
        res_classique = self.client.get("/api/linkedin-or-interpol/leaderboard?difficulty=classique")
        self.assertEqual(res_classique.status_code, 200)
        self.assertIn("records", res_classique.json())

        res_infini = self.client.get("/api/linkedin-or-interpol/leaderboard?difficulty=infini")
        self.assertEqual(res_infini.status_code, 200)
        self.assertIn("records", res_infini.json())

    def test_catalog_returns_all_profiles_with_rarity(self):
        res = self.client.get("/api/linkedin-or-interpol/catalog")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("catalog", data)
        self.assertGreaterEqual(data["count"], 150)
        first = data["catalog"][0]
        self.assertIn("id", first)
        self.assertIn("image_url", first)
        self.assertIn("rarity_label", first)
        self.assertIn("rarity_rank", first)

    def test_solo_game_completion_records_leaderboard(self):
        import time
        from app.database import get_solo_game_leaderboard
        from app import main as main_app

        new_res = self.client.post(
            "/api/linkedin-or-interpol/solo/new",
            json={
                "player_id": "test-save-p1",
                "player_name": "SauvegardeTest",
                "mode": "solo",
                "round_count": 2,
            },
        )
        self.assertEqual(new_res.status_code, 200)
        game_id = new_res.json()["game_id"]
        game = main_app.linkedin_or_interpol_manager.get_solo(game_id, "test-save-p1")
        first_label = game.rounds[0]["label"]

        # Guess round 1 correctly
        g1 = self.client.post(
            "/api/linkedin-or-interpol/solo/guess",
            json={
                "player_id": "test-save-p1",
                "player_name": "SauvegardeTest",
                "game_id": game_id,
                "guess": first_label,
            },
        )
        self.assertEqual(g1.status_code, 200)

        # Advance to round 2
        n1 = self.client.post(
            "/api/linkedin-or-interpol/solo/next",
            json={
                "player_id": "test-save-p1",
                "player_name": "SauvegardeTest",
                "game_id": game_id,
            },
        )
        self.assertEqual(n1.status_code, 200)

        # Guess round 2 correctly (finishes the game)
        second_label = game.rounds[1]["label"]
        g2 = self.client.post(
            "/api/linkedin-or-interpol/solo/guess",
            json={
                "player_id": "test-save-p1",
                "player_name": "SauvegardeTest",
                "game_id": game_id,
                "guess": second_label,
            },
        )
        self.assertEqual(g2.status_code, 200)
        self.assertEqual(g2.json()["status"], "finished")

        # Give async writer a brief moment
        time.sleep(0.3)
        records = get_solo_game_leaderboard("linkedin-or-interpol", "classique")
        matching = [r for r in records if r["player_name"] == "SauvegardeTest"]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["points"], 2)
        self.assertEqual(matching[0]["attempts"], 2)
        self.assertEqual(matching[0]["metrics"]["best_streak"], 2)

    def test_infinite_game_records_best_streak_in_leaderboard(self):
        import time
        from app.database import get_solo_game_leaderboard
        from app import main as main_app

        inf_res = self.client.post(
            "/api/linkedin-or-interpol/solo/new",
            json={
                "player_id": "test-inf-p1",
                "player_name": "InfiniLeader",
                "mode": "solo-infinite",
                "round_count": 10,
            },
        )
        self.assertEqual(inf_res.status_code, 200)
        game_id = inf_res.json()["game_id"]
        game = main_app.linkedin_or_interpol_manager.get_solo(game_id, "test-inf-p1")
        first_label = game.rounds[0]["label"]

        # Correct guess creates streak 1 and persists to DB
        g1 = self.client.post(
            "/api/linkedin-or-interpol/solo/guess",
            json={
                "player_id": "test-inf-p1",
                "player_name": "InfiniLeader",
                "game_id": game_id,
                "guess": first_label,
            },
        )
        self.assertEqual(g1.status_code, 200)
        self.assertEqual(g1.json()["streak"], 1)

        time.sleep(0.3)
        records = get_solo_game_leaderboard("linkedin-or-interpol", "infini")
        matching = [r for r in records if r["player_name"] == "InfiniLeader"]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["points"], 1)
        self.assertEqual(matching[0]["difficulty"], "infini")


if __name__ == "__main__":
    unittest.main()
