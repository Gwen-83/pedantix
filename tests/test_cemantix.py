import unittest

from app.cemantix import CemantixManager, _visible_hint_count


class CemantixTests(unittest.TestCase):
    def setUp(self):
        self.now = 1_000.0
        self.manager = CemantixManager(
            words={"chat", "chien", "animal", "maison", "voiture"},
            answers={"chat"},
            clock=lambda: self.now,
        )

    def test_solo_guess_records_proximity_and_reveals_answer_only_when_solved(self):
        game = self.manager.create_solo("player-1", "Joueur")
        self.assertIsNone(game.to_dict()["target"])

        game, result = self.manager.guess_solo(game.game_id, "player-1", "chien")
        self.assertEqual(result["score"], 89.4)
        self.assertFalse(result["solved"])
        self.assertIsNone(game.to_dict()["target"])

        game, result = self.manager.guess_solo(game.game_id, "player-1", "chat")
        self.assertEqual(result["score"], 100.0)
        self.assertTrue(result["solved"])
        self.assertEqual(game.to_dict()["target"], "chat")

    def test_default_answer_pool_has_a_broad_set_of_supported_words(self):
        manager = CemantixManager()
        self.assertGreaterEqual(len(manager.answers), 1_000)
        self.assertIn("arbre", manager.answers)
        self.assertNotIn("zzqxxyz", manager.answers)
        self.assertGreaterEqual(
            sum(bool(manager._hint_words(target)) for target in manager.answers),
            len(manager.answers) * 0.99,
        )

    def test_difficulty_controls_hint_reveal_schedule(self):
        self.assertEqual(_visible_hint_count("facile", 0), 1)
        self.assertEqual(_visible_hint_count("facile", 2), 1)
        self.assertEqual(_visible_hint_count("facile", 3), 2)
        self.assertEqual(_visible_hint_count("moyen", 1), 0)
        self.assertEqual(_visible_hint_count("moyen", 2), 1)
        self.assertEqual(_visible_hint_count("difficile", 5), 1)

    def test_room_directory_lists_lobbies_and_active_games_for_members(self):
        room = self.create_started_room()
        rooms = self.manager.list_rooms("host")
        self.assertEqual(len(rooms), 1)
        self.assertEqual(rooms[0]["room_id"], room.room_id)
        self.assertTrue(rooms[0]["is_member"])
        self.assertEqual(rooms[0]["difficulty"], "moyen")

    def test_solo_game_can_be_resumed_and_rejects_invalid_or_repeated_words(self):
        game = self.manager.create_solo("player-1", "Joueur")
        self.manager.guess_solo(game.game_id, "player-1", "chien")

        self.assertEqual(len(self.manager.get_solo(game.game_id, "player-1").guesses), 1)
        with self.assertRaises(KeyError):
            self.manager.get_solo(game.game_id, "other-player")
        with self.assertRaisesRegex(ValueError, "déjà proposé"):
            self.manager.guess_solo(game.game_id, "player-1", "chien")
        with self.assertRaisesRegex(ValueError, "un seul mot"):
            self.manager.guess_solo(game.game_id, "player-1", "chat chien")
        with self.assertRaisesRegex(ValueError, "pas reconnu"):
            self.manager.guess_solo(game.game_id, "player-1", "zzqxxyz")

    def create_started_room(self):
        room = self.manager.create_room("host", "Hôte")
        self.manager.join_room(room.room_id, "guest", "Invité")
        self.manager.start_room(room.room_id, "host")
        return room

    def test_room_hides_guesses_until_every_player_submits(self):
        room = self.create_started_room()
        self.manager.submit_room_guess(room.room_id, "host", "chien")

        state = self.manager.get_room(room.room_id, "host").to_dict("host", self.now)
        self.assertEqual(state["round_number"], 1)
        self.assertEqual(state["submitted_count"], 1)
        self.assertTrue(state["player"]["has_submitted"])
        self.assertEqual(state["player"]["guesses"], [])
        self.assertIsNone(state["target"])

        self.manager.submit_room_guess(room.room_id, "guest", "maison")
        state = self.manager.get_room(room.room_id, "host").to_dict("host", self.now)
        self.assertEqual(state["round_number"], 2)
        self.assertEqual(state["submitted_count"], 0)
        self.assertEqual(state["players"][0]["guesses"][0]["word"], "chien")
        self.assertEqual(state["players"][1]["guesses"][0]["word"], "maison")

    def test_timeout_reveals_submissions_and_marks_missing_players_as_passed(self):
        room = self.create_started_room()
        self.manager.submit_room_guess(room.room_id, "host", "chien")
        self.now += 60

        state = self.manager.get_room(room.room_id, "guest").to_dict("guest", self.now)

        self.assertEqual(state["round_number"], 2)
        self.assertEqual(state["submitted_count"], 0)
        self.assertEqual(state["players"][0]["guesses"][0]["score"], 89.4)
        self.assertTrue(state["players"][1]["guesses"][0]["passed"])
        self.assertEqual(state["time_left"], 60)

    def test_first_correct_submission_wins_after_round_results_are_revealed(self):
        room = self.create_started_room()
        self.manager.submit_room_guess(room.room_id, "host", "chat")
        self.now += 0.25
        self.manager.submit_room_guess(room.room_id, "guest", "chat")

        state = self.manager.get_room(room.room_id, "guest").to_dict("guest", self.now)
        self.assertEqual(state["status"], "finished")
        self.assertEqual(state["winner_player_id"], "host")
        self.assertEqual(state["target"], "chat")
        self.assertTrue(state["players"][0]["guesses"][0]["solved"])
        self.assertTrue(state["players"][1]["guesses"][0]["solved"])

    def test_only_host_can_start_and_only_enrolled_players_can_rejoin(self):
        room = self.manager.create_room("host", "Hôte")
        with self.assertRaisesRegex(ValueError, "deux joueurs"):
            self.manager.start_room(room.room_id, "host")
        self.manager.join_room(room.room_id, "guest", "Invité")
        with self.assertRaises(PermissionError):
            self.manager.start_room(room.room_id, "guest")
        self.manager.start_room(room.room_id, "host")
        with self.assertRaisesRegex(ValueError, "a commencé"):
            self.manager.join_room(room.room_id, "new-player", "Nouveau")
        self.assertIs(self.manager.join_room(room.room_id, "guest", "Invité"), room)


if __name__ == "__main__":
    unittest.main()
