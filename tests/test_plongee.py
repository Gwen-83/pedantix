import random
import unittest

from app.plongee import (
    MAX_PLAYERS,
    ROUND_COUNT,
    UNKNOWN_ANSWER_SCORE,
    PlongeeManager,
    normalize_answer,
)


class PlongeeTests(unittest.TestCase):
    def setUp(self):
        self.now = 1_000.0
        self.manager = PlongeeManager(
            clock=lambda: self.now,
            rng=random.Random(14),
        )

    def test_normalization_ignores_case_accents_and_punctuation(self):
        self.assertEqual(normalize_answer("  Poisson-Lune! "), "poisson lune")
        self.assertEqual(normalize_answer("ÉTATS fédérés de Micronésie"), "etats federes de micronesie")
        self.assertEqual(normalize_answer("東京"), "東京")

    def test_unlisted_answers_are_accepted_at_neutral_rarity(self):
        game = self.manager.create_solo("player-1", "Joueur")

        game, result = self.manager.guess_solo(game.game_id, "player-1", "gloubi-boulga")

        self.assertEqual(result["score"], UNKNOWN_ANSWER_SCORE)
        self.assertFalse(result["known_answer"])
        self.assertEqual(game.player.score, UNKNOWN_ANSWER_SCORE)

    def test_known_alias_uses_same_barometer_entry(self):
        prompt_index = next(index for index, prompt in enumerate(self.manager.prompts) if prompt["id"] == "fruit")
        answer_index = self.manager.answer_indexes[prompt_index]

        self.assertEqual(self.manager._score("MANGUES!", answer_index), ("mangue", 39, True))

    def test_answer_validation_rejects_empty_or_oversized_values(self):
        game = self.manager.create_solo("player-1", "Joueur")

        with self.assertRaisesRegex(ValueError, "Saisissez une réponse"):
            self.manager.guess_solo(game.game_id, "player-1", "  ")
        with self.assertRaisesRegex(ValueError, "80 caractères"):
            self.manager.guess_solo(game.game_id, "player-1", "x" * 81)

    def test_solo_rounds_accumulate_points_and_finish_after_seven_rounds(self):
        game = self.manager.create_solo("player-1", "Joueur")
        self.assertEqual(self.manager.solo_state(game)["round_count"], ROUND_COUNT)

        for round_index in range(ROUND_COUNT):
            self.manager.guess_solo(game.game_id, "player-1", f"réponse libre {round_index}")
            if round_index < ROUND_COUNT - 1:
                game = self.manager.next_solo(game.game_id, "player-1")

        game = self.manager.next_solo(game.game_id, "player-1")

        self.assertEqual(game.status, "finished")
        self.assertEqual(game.player.score, ROUND_COUNT * UNKNOWN_ANSWER_SCORE)
        self.assertEqual(len(game.player.results), ROUND_COUNT)

    def test_solo_timeout_marks_one_round_and_allows_play_to_continue(self):
        game = self.manager.create_solo("player-1", "Joueur")
        self.now += 26

        state = self.manager.solo_state(self.manager.get_solo(game.game_id, "player-1"))
        self.manager.get_solo(game.game_id, "player-1")

        self.assertEqual(state["round_number"], 2)
        self.assertEqual(len(game.player.results), 1)
        self.assertTrue(game.player.results[0]["timed_out"])
        self.assertEqual(game.player.score, 0)
        self.manager.guess_solo(game.game_id, "player-1", "réponse libre")

    def test_solo_state_is_private_to_the_creating_player(self):
        game = self.manager.create_solo("player-1", "Joueur")
        with self.assertRaises(KeyError):
            self.manager.get_solo(game.game_id, "other-player")

    def create_started_room(self):
        room = self.manager.create_room("host", "Hôte")
        self.manager.join_room(room.room_id, "guest", "Invité")
        self.manager.start_room(room.room_id, "host")
        return room

    def test_multiplayer_reveals_results_after_everyone_answers_and_penalizes_duplicates(self):
        room = self.create_started_room()
        self.manager.guess_room(room.room_id, "host", "poisson lune")
        state = self.manager.room_state(room, "host")
        self.assertIsNone(state["last_round"])
        self.manager.guess_room(room.room_id, "guest", "POISSON-LUNE!")

        state = self.manager.room_state(room, "guest")
        self.assertEqual(state["last_round"]["round_number"], 1)
        self.assertEqual([result["score"] for result in state["last_round"]["results"]], [35, 35])
        self.assertEqual(room.players["host"].score, 35)
        self.assertEqual(room.players["guest"].score, 35)

    def test_room_timeout_marks_missing_players_as_passed(self):
        room = self.create_started_room()
        self.manager.guess_room(room.room_id, "host", "réponse libre")
        self.now += 26

        state = self.manager.room_state(self.manager.get_room(room.room_id, "guest"), "guest")

        self.assertEqual(state["last_round"]["results"][0]["score"], UNKNOWN_ANSWER_SCORE)
        self.assertTrue(state["last_round"]["results"][1]["timed_out"])
        self.assertEqual(state["last_round"]["results"][1]["score"], 0)

    def test_room_requires_two_players_and_only_host_can_start_or_advance(self):
        room = self.manager.create_room("host", "Hôte")
        with self.assertRaisesRegex(ValueError, "au moins deux"):
            self.manager.start_room(room.room_id, "host")
        self.manager.join_room(room.room_id, "guest", "Invité")
        with self.assertRaises(PermissionError):
            self.manager.start_room(room.room_id, "guest")
        self.manager.start_room(room.room_id, "host")
        self.manager.guess_room(room.room_id, "host", "une réponse")
        self.manager.guess_room(room.room_id, "guest", "une autre réponse")
        with self.assertRaises(PermissionError):
            self.manager.next_room(room.room_id, "guest")

    def test_room_directory_only_exposes_lobbies_and_member_games(self):
        room = self.manager.create_room("host", "Hôte")
        self.assertEqual(self.manager.list_rooms()[0]["room_id"], room.room_id)
        self.manager.join_room(room.room_id, "guest", "Invité")
        self.manager.start_room(room.room_id, "host")
        self.assertEqual(self.manager.list_rooms(), [])
        self.assertTrue(self.manager.list_rooms("guest")[0]["is_member"])

    def test_room_enforces_player_limit(self):
        room = self.manager.create_room("host", "Hôte")
        for player_number in range(1, MAX_PLAYERS):
            self.manager.join_room(room.room_id, f"player-{player_number}", f"Joueur {player_number}")
        with self.assertRaisesRegex(ValueError, "complet"):
            self.manager.join_room(room.room_id, "overflow", "De trop")


if __name__ == "__main__":
    unittest.main()
