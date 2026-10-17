import unittest

from app.chiffrantix import (
    CHIFFRANTIX_CATEGORIES,
    CHIFFRANTIX_DIFFICULTIES,
    ChiffrantixManager,
    load_chiffrantix_questions,
)


class ChiffrantixTests(unittest.TestCase):
    def setUp(self):
        self.now = 1_000.0
        self.sample_questions = [
            {
                "question": "En quelle année a eu lieu la prise de la Bastille ?",
                "answer": "1789",
                "category": "histoire",
                "difficulty": "facile",
                "source_title": "Prise de la Bastille — Wikipédia",
                "source_url": "https://fr.wikipedia.org/wiki/Prise_de_la_Bastille",
                "explanation": "La prise de la Bastille survient le 14 juillet 1789 à Paris.",
            },
            {
                "question": "Combien de touches comporte un piano moderne standard ?",
                "answer": "88",
                "category": "arts_culture",
                "difficulty": "moyen",
                "source_title": "Piano — Wikipédia",
                "source_url": "https://fr.wikipedia.org/wiki/Piano",
                "explanation": "Un piano standard possède 88 touches (52 blanches et 36 noires).",
            },
        ]
        self.manager = ChiffrantixManager(
            questions=self.sample_questions,
            clock=lambda: self.now,
        )

    def test_bundled_dataset_has_at_least_1000_sourced_questions(self):
        questions = load_chiffrantix_questions()
        self.assertGreaterEqual(len(questions), 1000)
        seen_questions = set()
        categories_found = set()
        for item in questions:
            self.assertTrue(item.get("question", "").endswith("?"))
            self.assertTrue(item.get("answer"))
            self.assertIn(item.get("category"), CHIFFRANTIX_CATEGORIES - {"toutes"})
            self.assertIn(item.get("difficulty"), CHIFFRANTIX_DIFFICULTIES - {"toutes"})
            self.assertTrue(item.get("source_title"))
            self.assertTrue(item.get("source_url", "").startswith("http"))
            self.assertTrue(item.get("explanation"))
            seen_questions.add(item["question"])
            categories_found.add(item["category"])

        self.assertGreaterEqual(len(seen_questions), 1000)
        self.assertGreaterEqual(len(categories_found), 8)

    def test_solo_game_masks_question_and_scores_semantic_proximity_until_solved(self):
        game = self.manager.create_solo(
            "player-1", "Alice", difficulty="facile", category="histoire"
        )
        state = game.to_dict()
        self.assertEqual(state["answer"], "1789")
        self.assertIsNone(state["solution"])
        word_tokens = [t for t in state["tokens"] if t["is_word"]]
        self.assertTrue(all(not t["revealed"] for t in word_tokens))

        # Related word ("révolution" is semantically close to "Bastille")
        game, res = self.manager.guess_solo(game.game_id, "player-1", "révolution")
        self.assertIn(res["status"], ("close", "miss"))
        self.assertGreaterEqual(res["score"], 48.0)
        self.assertFalse(res["solved"])

        # Exact words in question ("année", "lieu", "prise", "bastille")
        for word in ("année", "lieu", "prise"):
            game, res = self.manager.guess_solo(game.game_id, "player-1", word)
            self.assertEqual(res["status"], "match")
            self.assertFalse(res["solved"])

        # Final significant word triggers full reveal & win
        game, res = self.manager.guess_solo(game.game_id, "player-1", "bastille")
        self.assertTrue(res["solved"])
        final_state = game.to_dict()
        self.assertEqual(final_state["status"], "finished")
        self.assertIsNotNone(final_state["solution"])
        self.assertEqual(
            final_state["solution"]["question"],
            "En quelle année a eu lieu la prise de la Bastille ?",
        )
        self.assertEqual(
            final_state["solution"]["source_url"],
            "https://fr.wikipedia.org/wiki/Prise_de_la_Bastille",
        )

    def test_solo_hint_reveals_a_word_without_finishing_game(self):
        game = self.manager.create_solo(
            "player-1", "Alice", difficulty="facile", category="histoire"
        )
        game, hint = self.manager.hint_solo(game.game_id, "player-1")
        self.assertIn("word", hint)
        self.assertGreater(game.board.revealed_count, 0)
        self.assertEqual(game.status, "playing")

    def test_multiplayer_room_race_and_restart(self):
        room = self.manager.create_room(
            "host", "Hôte", difficulty="facile", category="histoire"
        )
        self.manager.join_room(room.room_id, "guest", "Invité")
        self.manager.start_room(room.room_id, "host")

        for word in ("année", "lieu", "prise", "bastille"):
            room, _ = self.manager.guess_room(room.room_id, "guest", word)

        state = room.to_dict("host")
        self.assertEqual(state["status"], "finished")
        self.assertEqual(state["winner_player_id"], "guest")
        self.assertEqual(state["winner_name"], "Invité")
        self.assertIsNotNone(state["solution"])
        self.assertTrue(state["can_restart"])

        restarted = self.manager.restart_room(room.room_id, "host")
        self.assertEqual(restarted.status, "playing")
        self.assertEqual(restarted.match_number, 2)
        self.assertIsNone(restarted.winner_player_id)


if __name__ == "__main__":
    unittest.main()
