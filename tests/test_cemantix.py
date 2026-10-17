import unittest

from app.cemantix import CemantixManager, _visible_hint_count, calculate_cemantix_proximity


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

    def test_continuous_proximity_never_returns_zero_and_orders_semantic_closeness(self):
        # Distant words still receive a positive graduated score instead of 0.0
        distant_score = calculate_cemantix_proximity("voiture", "chat")
        self.assertGreater(distant_score, 0.0)
        self.assertLess(distant_score, 48.0)

        # Related words against the same target ("chat") are ordered by semantic closeness
        warm_score = calculate_cemantix_proximity("animal", "chat")
        hot_score = calculate_cemantix_proximity("chien", "chat")
        self.assertGreaterEqual(warm_score, 55.0)
        self.assertGreater(hot_score, warm_score)

    def test_solo_manual_hint_and_give_up(self):
        game = self.manager.create_solo("player-1", "Joueur", difficulty="moyen")
        self.assertEqual(len(game.to_dict()["hints"]), 0)

        game = self.manager.request_solo_hint(game.game_id, "player-1")
        state_with_hint = game.to_dict()
        self.assertEqual(len(state_with_hint["hints"]), 1)
        self.assertEqual(len(state_with_hint["hint_details"]), 1)
        self.assertIn("word", state_with_hint["hint_details"][0])
        self.assertIn("score", state_with_hint["hint_details"][0])

        game = self.manager.give_up_solo(game.game_id, "player-1")
        state = game.to_dict()
        self.assertEqual(state["status"], "finished")
        self.assertTrue(state["gave_up"])
        self.assertEqual(state["target"], "chat")

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

    def test_only_host_can_start_and_enrolled_players_can_rejoin(self):
        room = self.manager.create_room("host", "Hôte")
        with self.assertRaisesRegex(ValueError, "deux joueurs"):
            self.manager.start_room(room.room_id, "host")
        self.manager.join_room(room.room_id, "guest", "Invité")
        with self.assertRaises(PermissionError):
            self.manager.start_room(room.room_id, "guest")
        self.manager.start_room(room.room_id, "host")
        self.manager.join_room(room.room_id, "new-player", "Nouveau")
        self.assertTrue(room.players["new-player"].is_spectator)
        self.assertIs(self.manager.join_room(room.room_id, "guest", "Invité"), room)

    def test_spectator_cannot_submit_and_joins_only_after_round_boundary(self):
        room = self.create_started_room()
        self.manager.join_room(room.room_id, "observer", "Observateur")
        self.assertTrue(room.players["observer"].is_spectator)

        state = self.manager.get_room(room.room_id, "observer").to_dict("observer", self.now)
        self.assertTrue(state["player"]["is_spectator"])
        self.assertEqual(state["player_count"], 2)
        self.assertEqual(state["spectator_count"], 1)
        self.assertEqual(state["submitted_count"], 0)
        with self.assertRaisesRegex(ValueError, "spectateurs"):
            self.manager.submit_room_guess(room.room_id, "observer", "animal")
        self.assertNotIn("observer", room.pending)
        self.assertEqual(room.players["observer"].guesses, [])

        self.manager.submit_room_guess(room.room_id, "host", "chien")
        self.manager.submit_room_guess(room.room_id, "guest", "maison")

        self.assertEqual(room.round_number, 2)
        self.assertFalse(room.players["observer"].is_spectator)
        self.assertEqual(room.players["observer"].guesses, [])
        state = self.manager.get_room(room.room_id, "observer").to_dict("observer", self.now)
        self.assertFalse(state["player"]["is_spectator"])
        self.assertEqual(state["player_count"], 3)
        self.manager.submit_room_guess(room.room_id, "observer", "animal")
        self.assertIn("observer", room.pending)

    def test_spectators_remain_unpromoted_when_a_correct_guess_ends_the_match(self):
        room = self.create_started_room()
        self.manager.join_room(room.room_id, "observer", "Observateur")
        self.manager.submit_room_guess(room.room_id, "host", "chat")
        self.manager.submit_room_guess(room.room_id, "guest", "chat")

        self.assertEqual(room.status, "finished")
        self.assertTrue(room.players["observer"].is_spectator)
        self.assertEqual(room.players["observer"].guesses, [])

    def test_host_restart_resets_match_and_promotes_queued_spectators(self):
        room = self.create_started_room()
        with self.assertRaisesRegex(ValueError, "terminée"):
            self.manager.restart_room(room.room_id, "host")
        self.manager.join_room(room.room_id, "observer", "Observateur")
        self.manager.submit_room_guess(room.room_id, "host", "chat")
        self.manager.submit_room_guess(room.room_id, "guest", "chat")

        self.assertTrue(room.to_dict("host", self.now)["can_restart"])
        self.assertFalse(room.to_dict("guest", self.now)["can_restart"])
        with self.assertRaises(PermissionError):
            self.manager.restart_room(room.room_id, "guest")
        restarted = self.manager.restart_room(room.room_id, "host")

        self.assertIs(restarted, room)
        self.assertEqual(room.status, "playing")
        self.assertEqual(room.round_number, 1)
        self.assertEqual(room.deadline_at, self.now + 60)
        self.assertIsNone(room.winner_player_id)
        self.assertEqual(room.pending, {})
        self.assertFalse(room.players["observer"].is_spectator)
        self.assertEqual(room.players["host"].guesses, [])
        self.assertEqual(room.players["guest"].guesses, [])
        self.assertEqual(room.players["observer"].guesses, [])
        state = room.to_dict("observer", self.now)
        self.assertFalse(state["player"]["is_spectator"])
        self.assertEqual(state["player_count"], 3)
        self.assertFalse(state["restart_available"])


if __name__ == "__main__":
    unittest.main()
