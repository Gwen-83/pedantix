import unittest

from app.motus import MotusManager, evaluate_guess


class MotusTests(unittest.TestCase):
    def setUp(self):
        self.manager = MotusManager(
            words={"talent", "tartes", "tanner", "tonton"},
            answers={"talent"},
        )

    def test_feedback_marks_exact_and_misplaced_letters(self):
        self.assertEqual(
            evaluate_guess("telnat", "talent"),
            ["correct", "present", "correct", "present", "present", "correct"],
        )
        self.assertEqual(
            evaluate_guess("baaaax", "banane"),
            ["correct", "correct", "absent", "correct", "absent", "absent"],
        )

    def test_solo_round_persists_feedback_and_reveals_answer_when_finished(self):
        game = self.manager.create_solo("player-1", "Joueur")
        self.assertEqual(game.target, "talent")
        self.assertIsNone(game.to_dict()["target"])

        game, result = self.manager.guess_solo(game.game_id, "player-1", "tartes")
        self.assertFalse(result["solved"])
        self.assertEqual(len(game.player.guesses), 1)

        game, result = self.manager.guess_solo(game.game_id, "player-1", "talent")
        self.assertTrue(result["solved"])
        self.assertEqual(result["score"], 500)
        self.assertEqual(game.status, "finished")
        self.assertEqual(game.to_dict()["target"], "TALENT")

    def test_revealed_letters_are_hints_and_do_not_restrict_later_guesses(self):
        game = self.manager.create_solo("player-1", "Joueur")

        game, _ = self.manager.guess_solo(game.game_id, "player-1", "tartes")
        self.assertEqual(game.player.guesses[0]["feedback"][1], "correct")

        game, result = self.manager.guess_solo(game.game_id, "player-1", "tonton")

        self.assertFalse(result["solved"])
        self.assertEqual(game.player.guesses[1]["word"], "tonton")
        self.assertEqual(game.player.guesses[1]["word"][1], "o")

    def test_difficulty_controls_attempts_and_room_directory(self):
        game = self.manager.create_solo("player-1", "Joueur", "facile")
        self.assertEqual(game.to_dict()["max_attempts"], 8)

        room = self.manager.create_room("host", "Hôte", "difficile")
        public_room = self.manager.list_rooms("visitor")[0]
        member_room = self.manager.list_rooms("host")[0]
        self.assertEqual(public_room["room_id"], room.room_id)
        self.assertFalse(public_room["is_member"])
        self.assertTrue(member_room["is_member"])
        self.assertEqual(member_room["difficulty"], "difficile")

    def test_solo_game_can_be_resumed_by_the_same_player_only(self):
        game = self.manager.create_solo("player-1", "Joueur")
        self.manager.guess_solo(game.game_id, "player-1", "tartes")
        resumed = self.manager.get_solo(game.game_id, "player-1")
        self.assertEqual(len(resumed.player.guesses), 1)
        with self.assertRaises(KeyError):
            self.manager.get_solo(game.game_id, "another-player")

    def test_solo_game_ends_after_six_unsuccessful_guesses(self):
        manager = MotusManager(
            words={"talent", "tartes", "tanner", "tonton", "tenors", "tissus", "tremor"},
            answers={"talent"},
        )
        game = manager.create_solo("player-1", "Joueur")
        for guess in ("tartes", "tanner", "tonton", "tenors", "tissus", "tremor"):
            game, result = manager.guess_solo(game.game_id, "player-1", guess)

        self.assertTrue(result["finished"])
        self.assertEqual(game.status, "finished")
        self.assertEqual(game.player.score, 0)
        self.assertEqual(game.to_dict()["target"], "TALENT")

    def test_guesses_require_word_length_start_letter_and_dictionary_membership(self):
        game = self.manager.create_solo("player-1", "Joueur")
        for guess, message in (
            ("tarte", "6 lettres"),
            ("papier", "commencer"),
            ("tartin", "dictionnaire"),
        ):
            with self.subTest(guess=guess), self.assertRaisesRegex(ValueError, message):
                self.manager.guess_solo(game.game_id, "player-1", guess)
        self.assertEqual(game.player.guesses, [])

    def test_multiplayer_room_uses_one_target_and_keeps_player_grids_separate(self):
        room = self.manager.create_room("host", "Hôte")
        self.assertEqual(room.target, "talent")
        with self.assertRaisesRegex(ValueError, "deux joueurs"):
            self.manager.start_room(room.room_id, "host")

        self.manager.join_room(room.room_id, "guest", "Invité")
        with self.assertRaises(PermissionError):
            self.manager.start_room(room.room_id, "guest")
        self.manager.start_room(room.room_id, "host")

        self.manager.guess_room(room.room_id, "host", "tartes")
        self.manager.guess_room(room.room_id, "guest", "talent")
        self.assertEqual(len(room.players["host"].guesses), 1)
        self.assertEqual(len(room.players["guest"].guesses), 1)
        self.assertFalse(room.players["host"].solved)
        self.assertTrue(room.players["guest"].solved)
        self.assertEqual(room.status, "playing")
        host_view = room.to_dict("host")
        guest_view = room.to_dict("guest")
        self.assertIsNone(host_view["target"])
        self.assertEqual(host_view["player"]["guesses"][0]["word"], "tartes")
        self.assertEqual(host_view["players"][1]["guesses"], [])
        self.assertEqual(guest_view["players"][0]["guesses"], [])

        self.manager.guess_room(room.room_id, "host", "talent")
        self.assertEqual(room.status, "finished")
        self.assertEqual(room.to_dict("host")["target"], "TALENT")

    def test_rejoining_a_room_preserves_player_progress(self):
        room = self.manager.create_room("host", "Hôte")
        self.manager.join_room(room.room_id, "guest", "Invité")
        self.manager.start_room(room.room_id, "host")
        self.manager.guess_room(room.room_id, "guest", "tartes")

        resumed = self.manager.join_room(room.room_id, "guest", "Invité")

        self.assertIs(resumed, room)
        self.assertEqual(len(resumed.players["guest"].guesses), 1)

    def test_spectator_cannot_guess_and_is_promoted_with_reset_on_host_restart(self):
        room = self.manager.create_room("host", "Hôte")
        self.manager.join_room(room.room_id, "guest", "Invité")
        self.manager.start_room(room.room_id, "host")
        with self.assertRaisesRegex(ValueError, "terminée"):
            self.manager.restart_room(room.room_id, "host")
        self.manager.join_room(room.room_id, "observer", "Observateur")

        state = room.to_dict("observer")
        self.assertTrue(state["player"]["is_spectator"])
        self.assertEqual(state["player_count"], 2)
        self.assertEqual(state["spectator_count"], 1)
        self.assertTrue(state["players"][2]["is_spectator"])
        with self.assertRaisesRegex(ValueError, "spectateurs"):
            self.manager.guess_room(room.room_id, "observer", "tartes")
        self.assertEqual(room.players["observer"].guesses, [])

        self.manager.guess_room(room.room_id, "host", "talent")
        self.assertEqual(room.status, "playing")
        self.assertEqual(self.manager.list_rooms()[0]["player_count"], 2)
        self.manager.guess_room(room.room_id, "guest", "talent")
        self.assertEqual(room.status, "finished")
        self.assertTrue(room.to_dict("host")["can_restart"])
        self.assertFalse(room.to_dict("guest")["can_restart"])
        with self.assertRaises(PermissionError):
            self.manager.restart_room(room.room_id, "guest")

        restarted = self.manager.restart_room(room.room_id, "host")

        self.assertIs(restarted, room)
        self.assertEqual(room.status, "playing")
        self.assertFalse(room.players["observer"].is_spectator)
        self.assertEqual(room.to_dict("observer")["player_count"], 3)
        for player in room.players.values():
            self.assertEqual(player.guesses, [])
            self.assertFalse(player.solved)
            self.assertFalse(player.finished)
            self.assertEqual(player.score, 0)
        self.manager.guess_room(room.room_id, "observer", "tartes")
        self.assertEqual(len(room.players["observer"].guesses), 1)


if __name__ == "__main__":
    unittest.main()
