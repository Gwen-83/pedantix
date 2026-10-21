import json
import random
import unicodedata
import unittest

from app.plongee import (
    MAX_PLAYERS,
    PROMPTS,
    PROMPTS_PATH,
    ROUND_COUNT,
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

    def test_unrelated_answer_is_rejected_without_consuming_solo_round(self):
        game = self.manager.create_solo("player-1", "Joueur")

        with self.assertRaisesRegex(ValueError, "hors sujet ou absente du barème"):
            self.manager.guess_solo(game.game_id, "player-1", "table")
        with self.assertRaisesRegex(ValueError, "hors sujet ou absente du barème"):
            self.manager.guess_solo(game.game_id, "player-1", "gloubi-boulga")

        self.assertEqual(game.player.score, 0)
        self.assertEqual(game.player.results, [])

    def test_extended_barometer_accepts_curated_answers_and_aliases(self):
        prompt_indexes = {
            prompt["id"]: self.manager.answer_indexes[index]
            for index, prompt in enumerate(self.manager.prompts)
        }

        self.assertEqual(
            self.manager._score("POULPES!", prompt_indexes["animal"]),
            ("pieuvre", 20, True),
        )
        self.assertEqual(
            self.manager._score("MALAISIE", prompt_indexes["pays"]),
            ("malaisie", 26, True),
        )
        self.assertEqual(
            self.manager._score("violoncelles", prompt_indexes["instrument"]),
            ("violoncelle", 7, True),
        )

    def test_question_bank_has_many_topics_and_plausible_answers(self):
        self.assertGreaterEqual(len(PROMPTS), 25)
        self.assertGreaterEqual(
            min(len(prompt["answers"]) for prompt in PROMPTS),
            4,
        )
        prompt_indexes = {
            prompt["id"]: self.manager.answer_indexes[index]
            for index, prompt in enumerate(self.manager.prompts)
        }
        self.assertTrue(self.manager._score("panais", prompt_indexes["legume"])[2])
        self.assertTrue(self.manager._score("termite", prompt_indexes["insecte"])[2])
        with self.assertRaisesRegex(ValueError, "hors sujet ou absente du barème"):
            self.manager._score("Leeds", prompt_indexes["capitale_europe"])

    def test_new_bounded_topics_have_complete_answer_counts(self):
        expected_counts = {
            "mois_annee": 12,
            "jour_semaine": 7,
            "saison": 4,
            "continent": 7,
            "ocean": 5,
            "planete": 8,
            "planete_naine": 5,
            "signe_zodiaque": 12,
            "direction": 8,
            "note_musique": 7,
            "lettre_alphabet": 26,
            "chiffre_romain": 7,
            "nombre_premier": 25,
            "couleur_arc_en_ciel": 7,
            "jour_ferie_france": 11,
            "langue_officielle_onu": 6,
            "province_territoire_canada": 13,
            "etat_etats_unis": 50,
            "departement_francais": 101,
        }
        prompt_counts = {
            prompt["id"]: len(prompt["answers"])
            for prompt in PROMPTS
        }

        for prompt_id, expected_count in expected_counts.items():
            with self.subTest(prompt=prompt_id):
                self.assertEqual(prompt_counts[prompt_id], expected_count)

    def test_all_answers_have_explicit_originality_scores_from_zero_to_100(self):
        with PROMPTS_PATH.open(encoding="utf-8") as prompts_file:
            stored_prompts = json.load(prompts_file)

        self.assertTrue(
            all(
                isinstance(answer, dict) and "score" in answer
                for prompt in stored_prompts
                for answer in prompt["answers"]
            )
        )
        for prompt in PROMPTS:
            for answer in prompt["answers"]:
                with self.subTest(prompt=prompt["id"], answer=answer):
                    self.assertIsInstance(answer, dict)
                    self.assertIsInstance(answer.get("score"), int)
                    self.assertGreaterEqual(answer["score"], 0)
                    self.assertLessEqual(answer["score"], 100)

        animal_index = next(
            index for index, prompt in enumerate(self.manager.prompts)
            if prompt["id"] == "animal"
        )
        self.assertEqual(
            self.manager._score(
                "poisson", self.manager.answer_indexes[animal_index]
            ),
            ("poisson", 0, True),
        )
        self.assertEqual(
            self.manager._score(
                "rémora", self.manager.answer_indexes[animal_index]
            ),
            ("remora", 90, True),
        )

        prompt_indexes = {
            prompt["id"]: self.manager.answer_indexes[index]
            for index, prompt in enumerate(self.manager.prompts)
        }
        self.assertEqual(
            self.manager._score("Europe", prompt_indexes["continent"])[1],
            0,
        )
        self.assertEqual(
            self.manager._score("Antarctique", prompt_indexes["continent"])[1],
            100,
        )
        self.assertEqual(
            self.manager._score("Californie", prompt_indexes["etat_etats_unis"])[1],
            0,
        )
        self.assertEqual(
            self.manager._score("Rhode Island", prompt_indexes["etat_etats_unis"])[1],
            80,
        )

    def test_short_answers_and_common_variants_match_their_full_answers(self):
        prompt_indexes = {
            prompt["id"]: self.manager.answer_indexes[index]
            for index, prompt in enumerate(self.manager.prompts)
        }

        self.assertEqual(
            self.manager._score("Travail", prompt_indexes["jour_ferie_france"]),
            ("fete du travail", 20, True),
        )
        self.assertEqual(
            self.manager._score("1er mai", prompt_indexes["jour_ferie_france"]),
            ("fete du travail", 20, True),
        )
        self.assertEqual(
            self.manager._score("vésicule", prompt_indexes["partie_corps"]),
            ("vesicule biliaire", 23, True),
        )
        self.assertEqual(
            self.manager._score(
                "vésiculte biliaire", prompt_indexes["partie_corps"]
            ),
            ("vesicule biliaire", 23, True),
        )

    def test_question_bank_accepts_more_valid_answers_for_each_topic(self):
        prompt_indexes = {
            prompt["id"]: self.manager.answer_indexes[index]
            for index, prompt in enumerate(self.manager.prompts)
        }
        expected_answers = {
            "animal": "murène",
            "fruit": "citron",
            "espace": "Io",
            "oiseau": "cagou",
            "legume": "gombo",
            "sport": "pétanque",
            "langue": "bengali",
            "couleur": "fuchsia",
            "insecte": "forficule",
            "fleur": "pâquerette",
            "arbre": "ginkgo",
            "race_chien": "shih tzu",
            "instrument_musique": "harmonica",
            "element_chimique": "oganesson",
            "capitale_europe": "Luxembourg",
            "ville_france": "Toulon",
            "plat": "pad thaï",
            "dessert": "kouign-amann",
            "metier_sante": "orthoptiste",
            "animal_ferme": "agneau",
            "matiere_scolaire": "robotique",
            "transport": "funiculaire",
            "partie_corps": "pancréas",
            "jeu_societe": "Azul",
            "montagne": "Piton de la Fournaise",
        }
        for prompt_id, answer in expected_answers.items():
            with self.subTest(prompt=prompt_id, answer=answer):
                self.assertTrue(
                    self.manager._score(answer, prompt_indexes[prompt_id])[2]
                )
        chemical_question = next(
            prompt for prompt in self.manager.prompts
            if prompt["id"] == "element_chimique"
        )
        self.assertEqual(len(chemical_question["answers"]), 118)

    def test_position_derived_sports_do_not_receive_the_maximum_score(self):
        sport_index = next(
            index for index, prompt in enumerate(self.manager.prompts)
            if prompt["id"] == "sport"
        )

        self.assertEqual(
            self.manager._score("curling", self.manager.answer_indexes[sport_index]),
            ("curling", 55, True),
        )

    def test_question_bank_has_no_duplicate_normalized_answers(self):
        def normalize(value):
            decomposed = unicodedata.normalize("NFKD", value.casefold())
            unaccented = "".join(
                char for char in decomposed if not unicodedata.combining(char)
            )
            return " ".join(
                "".join(char if char.isalnum() else " " for char in unaccented).split()
            )

        for prompt in PROMPTS:
            answers = [
                answer["answer"] if isinstance(answer, dict) else answer
                for answer in prompt["answers"]
            ]
            with self.subTest(prompt=prompt["id"]):
                self.assertEqual(
                    len(answers),
                    len({normalize(answer) for answer in answers}),
                )

    def test_generated_plural_forms_are_accepted_but_unrelated_answers_are_not(self):
        prompt_index = next(
            index for index, prompt in enumerate(self.manager.prompts)
            if prompt["id"] == "legume"
        )
        answer_index = self.manager.answer_indexes[prompt_index]

        self.assertTrue(self.manager._score("carottes", answer_index)[2])
        self.assertTrue(self.manager._score("pommes de terre", answer_index)[2])
        with self.assertRaisesRegex(ValueError, "hors sujet ou absente du barème"):
            self.manager._score("table", answer_index)

    def test_solo_question_draws_do_not_repeat_until_the_bank_is_nearly_exhausted(self):
        games = [
            self.manager.create_solo("player-1", "Joueur")
            for _ in range(len(PROMPTS) // ROUND_COUNT)
        ]
        prompt_ids = [
            prompt["id"] for game in games for prompt in game.prompts
        ]

        self.assertEqual(len(prompt_ids), len(set(prompt_ids)))

    def test_known_alias_uses_same_barometer_entry(self):
        prompt_index = next(index for index, prompt in enumerate(self.manager.prompts) if prompt["id"] == "fruit")
        answer_index = self.manager.answer_indexes[prompt_index]

        self.assertEqual(self.manager._score("MANGUES!", answer_index), ("mangue", 20, True))

    def test_answer_validation_rejects_empty_or_oversized_values(self):
        game = self.manager.create_solo("player-1", "Joueur")

        with self.assertRaisesRegex(ValueError, "Saisissez une réponse"):
            self.manager.guess_solo(game.game_id, "player-1", "  ")
        with self.assertRaisesRegex(ValueError, "80 caractères"):
            self.manager.guess_solo(game.game_id, "player-1", "x" * 81)

    def test_solo_rounds_accumulate_points_and_finish_after_seven_rounds(self):
        game = self.manager.create_solo("player-1", "Joueur")
        self.assertEqual(self.manager.solo_state(game)["round_count"], ROUND_COUNT)
        expected_score = 0

        for round_index in range(ROUND_COUNT):
            answer = game.prompts[round_index]["answers"][0]
            game, result = self.manager.guess_solo(
                game.game_id, "player-1", answer["answer"]
            )
            expected_score += answer["score"]
            self.assertEqual(result["score"], answer["score"])
            if round_index < ROUND_COUNT - 1:
                game = self.manager.next_solo(game.game_id, "player-1")

        game = self.manager.next_solo(game.game_id, "player-1")

        self.assertEqual(game.status, "finished")
        self.assertEqual(game.player.score, expected_score)
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
        self.manager.guess_solo(
            game.game_id,
            "player-1",
            game.prompts[game.round_index]["answers"][0]["answer"],
        )

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
        answer = room.prompts[0]["answers"][0]
        self.manager.guess_room(room.room_id, "host", answer["answer"])
        state = self.manager.room_state(room, "host")
        self.assertIsNone(state["last_round"])
        self.manager.guess_room(room.room_id, "guest", answer["answer"].upper())

        state = self.manager.room_state(room, "guest")
        self.assertEqual(state["last_round"]["round_number"], 1)
        duplicate_score = max(0, answer["score"] - 15)
        self.assertEqual(
            [result["score"] for result in state["last_round"]["results"]],
            [duplicate_score, duplicate_score],
        )
        self.assertEqual(room.players["host"].score, duplicate_score)
        self.assertEqual(room.players["guest"].score, duplicate_score)

    def test_unrelated_multiplayer_answer_does_not_lock_the_player_out(self):
        room = self.create_started_room()

        with self.assertRaisesRegex(ValueError, "hors sujet ou absente du barème"):
            self.manager.guess_room(room.room_id, "host", "chaise")

        self.assertNotIn("host", room.answers)
        self.manager.guess_room(
            room.room_id, "host", room.prompts[0]["answers"][0]["answer"]
        )
        self.assertIn("host", room.answers)

    def test_room_timeout_marks_missing_players_as_passed(self):
        room = self.create_started_room()
        answer = room.prompts[0]["answers"][0]
        self.manager.guess_room(room.room_id, "host", answer["answer"])
        self.now += 26

        state = self.manager.room_state(self.manager.get_room(room.room_id, "guest"), "guest")

        self.assertEqual(state["last_round"]["results"][0]["score"], answer["score"])
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
        answer = room.prompts[0]["answers"][0]["answer"]
        self.manager.guess_room(room.room_id, "host", answer)
        self.manager.guess_room(room.room_id, "guest", answer)
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
