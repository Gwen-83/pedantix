import unittest

from app.linkedin_or_interpol import LinkedinOrInterpolManager


class LinkedinOrInterpolTests(unittest.TestCase):
    def setUp(self):
        self.manager = LinkedinOrInterpolManager()

    def test_dataset_is_loaded_and_has_valid_labels(self):
        dataset = self.manager.dataset
        self.assertGreater(len(dataset), 0)
        self.assertTrue({entry["label"] for entry in dataset}.issubset({"linkedin", "interpol"}))
        for entry in dataset:
            self.assertIn("image_path", entry)
            self.assertIn("source_url", entry)

    def test_create_game_builds_rounds_and_hides_answer(self):
        state = self.manager.create_game("alice", rounds=3)
        self.assertEqual(state["status"], "playing")
        self.assertEqual(state["round_count"], 3)
        self.assertIsNotNone(state["current_person"])
        self.assertNotIn("label", state["current_person"])
        self.assertNotIn("answer", state["current_person"])

        internal = self.manager.games[state["game_id"]]
        self.assertEqual(len(internal["rounds"]), 3)
        self.assertIn("label", internal["rounds"][0])

    def test_submit_guess_evaluates_correct_answer(self):
        state = self.manager.create_game("alice", rounds=2)
        internal = self.manager.games[state["game_id"]]
        guess = internal["rounds"][internal["round_index"]]["label"]
        result = self.manager.submit_guess(state["game_id"], "alice", guess)
        self.assertTrue(result["result"]["correct"])
        self.assertEqual(result["score"], 1)
        self.assertEqual(result["round_index"], 1)

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
        self.assertEqual(internal["rounds"][0]["label"], internal["rounds"][0]["label"])

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


if __name__ == "__main__":
    unittest.main()
