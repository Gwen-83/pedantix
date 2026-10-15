import unittest

from app.bitoguessr import (
    COUNTRY_AVERAGES_CM,
    ROUND_COUNT,
    BitoguessrManager,
    _make_question,
)


class BitoguessrTests(unittest.TestCase):
    def setUp(self):
        self.manager = BitoguessrManager()

    def test_country_dataset_is_unique_and_questions_hide_answers(self):
        countries = [country for country, _ in COUNTRY_AVERAGES_CM]
        self.assertEqual(len(countries), 20)
        self.assertEqual(len(countries), len(set(countries)))

        game = self.manager.create_solo("alice", "Alice", "normal")
        state = game.to_dict()
        self.assertEqual(state["round_count"], ROUND_COUNT)
        self.assertIsNone(state["result"])
        self.assertNotIn("answer", state)
        self.assertNotIn("accepted", state)
        self.assertEqual(
            len({question["answer"] for question in game.questions}),
            ROUND_COUNT,
        )

    def test_normal_questions_accept_every_country_with_the_rounded_value(self):
        for _ in range(100):
            question = _make_question("normal")
            self.assertIsInstance(question["prompt_cm"], int)
            self.assertTrue(set(question["accepted"]).issubset(question["options"]))
            matching = {
                country for country, value in COUNTRY_AVERAGES_CM
                if int(value + 0.5) == question["prompt_cm"]
            }
            self.assertEqual(set(question["accepted"]), matching)
            self.assertEqual(len(question["options"]), max(4, len(question["accepted"])))

    def test_hard_question_has_one_correct_country_and_two_decimal_prompt(self):
        for _ in range(25):
            question = _make_question("difficile")
            self.assertEqual(len(question["accepted"]), 1)
            self.assertEqual(question["prompt_cm"], round(
                next(value for country, value in COUNTRY_AVERAGES_CM if country == question["answer"]),
                2,
            ))
            self.assertIn(question["answer"], question["options"])

    def test_solo_game_scores_answers_and_advances_until_completion(self):
        game = self.manager.create_solo("alice", "Alice", "difficile")
        for index in range(ROUND_COUNT):
            question = game.questions[game.round_index]
            game, result = self.manager.guess_solo(
                game.game_id, "alice", question["answer"]
            )
            self.assertTrue(result["correct"])
            self.assertEqual(result["round_number"], index + 1)
            if index < ROUND_COUNT - 1:
                game = self.manager.next_solo(game.game_id, "alice")

        self.assertEqual(game.score, ROUND_COUNT)
        self.assertEqual(game.status, "finished")
        self.assertEqual(game.to_dict()["results"][-1]["answer"], game.results[-1]["answer"])
        with self.assertRaisesRegex(ValueError, "terminée"):
            self.manager.guess_solo(game.game_id, "alice", game.questions[-1]["answer"])
        with self.assertRaises(KeyError):
            self.manager.get_solo(game.game_id, "bob")

    def test_room_shares_questions_hides_answer_and_waits_for_every_player(self):
        room = self.manager.create_room("host", "Hôte", "normal", round_count=2)
        self.assertIsNone(room.to_dict("host")["prompt_cm"])
        with self.assertRaisesRegex(ValueError, "deux joueurs"):
            self.manager.start_room(room.room_id, "host")

        self.manager.join_room(room.room_id, "guest", "Invité")
        self.manager.start_room(room.room_id, "host")
        host_state = room.to_dict("host")
        guest_state = room.to_dict("guest")
        self.assertEqual(host_state["prompt_cm"], guest_state["prompt_cm"])
        self.assertEqual(host_state["options"], guest_state["options"])
        self.assertNotIn("answer", host_state)

        answer = room.current_round.question["accepted"][0]
        _, pending = self.manager.guess_room(room.room_id, "host", answer)
        self.assertIsNone(pending)
        self.assertIsNone(room.to_dict("host")["last_round"])
        self.assertTrue(room.to_dict("host")["player"]["submitted"])

        room, completed = self.manager.guess_room(room.room_id, "guest", answer)
        self.assertEqual(completed["answer"], room.current_round.question["answer"])
        self.assertEqual(len(completed["guesses"]), 2)
        self.assertEqual(room.to_dict("host")["last_round"], room.to_dict("guest")["last_round"])

        with self.assertRaises(PermissionError):
            self.manager.next_room(room.room_id, "guest")
        room = self.manager.next_room(room.room_id, "host")
        self.assertEqual(room.to_dict("guest")["round_number"], 2)

    def test_room_rejects_invalid_and_duplicate_guesses(self):
        room = self.manager.create_room("host", "Hôte", "difficile", round_count=1)
        self.manager.join_room(room.room_id, "guest", "Invité")
        self.manager.start_room(room.room_id, "host")
        with self.assertRaisesRegex(ValueError, "pays proposé"):
            self.manager.guess_room(room.room_id, "host", "Atlantide")
        option = room.current_round.question["options"][0]
        self.manager.guess_room(room.room_id, "host", option)
        with self.assertRaisesRegex(ValueError, "déjà été validée"):
            self.manager.guess_room(room.room_id, "host", option)


if __name__ == "__main__":
    unittest.main()
