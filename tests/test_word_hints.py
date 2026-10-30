import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.game import GameSession
from app.nlp import check_match
from app.room import Room, RoomPlayer


def make_session(session_id, revealed_ids=()):
    tokens = [
        {"id": 1, "is_word": True, "is_title": True, "revealed": 1 in revealed_ids},
        {"id": 2, "is_word": True, "is_title": False, "revealed": 2 in revealed_ids},
    ]
    return SimpleNamespace(
        session_id=session_id,
        total_words=2,
        tokens=tokens,
        tokens_by_id={token["id"]: token for token in tokens},
    )


class WordHintTests(unittest.TestCase):
    def setUp(self):
        self.score_patcher = patch("app.room.get_player_score", return_value=0)
        self.score_patcher.start()
        self.room = Room(
            room_id="hint-test",
            article_data={"title": "Article", "paragraphs": []},
            seed="P-1234",
        )

    def tearDown(self):
        self.room.cleanup()
        self.score_patcher.stop()

    def test_multiplayer_hint_is_hidden_from_every_player(self):
        first_session = make_session("first", revealed_ids={1})
        second_session = make_session("second")
        self.room.players = {
            "first": RoomPlayer("first", "Joueur 1", first_session),
            "second": RoomPlayer("second", "Joueur 2", second_session),
        }

        self.assertEqual(self.room._pick_next_hint_word_id(), 2)

    def test_team_hint_is_hidden_from_every_active_team(self):
        self.room.game_mode = "team"
        self.room.team_sessions = {
            "blue": make_session("blue", revealed_ids={1}),
            "red": make_session("red"),
            "green": make_session("green", revealed_ids={1, 2}),
        }
        self.room.players = {
            "blue": RoomPlayer("blue", "Bleue", self.room.team_sessions["blue"], team="blue"),
            "red": RoomPlayer("red", "Rouge", self.room.team_sessions["red"], team="red"),
            "spectator": RoomPlayer(
                "spectator",
                "Spectateur",
                self.room.team_sessions["green"],
                team="green",
            ),
        }
        self.room.players["spectator"].is_spectator = True

        self.assertEqual(self.room._pick_next_hint_word_id(), 2)

    def test_hint_never_reveals_a_title_word(self):
        session = make_session("title-only")
        session.tokens = [session.tokens[0]]
        session.tokens_by_id = {1: session.tokens[0]}
        self.room.players = {
            "first": RoomPlayer("first", "Joueur", session),
        }

        self.assertIsNone(self.room._pick_next_hint_word_id())

    def test_hint_never_reveals_a_body_word_repeated_from_the_title(self):
        with patch("app.game.record_game_start"):
            session = GameSession(
                session_id="repeated-title-word",
                seed="P-1234",
                title="Mars rouge",
                url="",
                image="",
                paragraphs=["Mars est une planète rouge."],
                mode="multiplayer",
                category="general",
            )
        self.room.players = {
            "first": RoomPlayer("first", "Joueur", session),
        }

        for _ in range(20):
            token_id = self.room._pick_next_hint_word_id()
            self.assertIsNotNone(token_id)
            self.assertNotIn(
                session.tokens_by_id[token_id]["normalized"],
                {"mars", "rouge"},
            )

    def test_hint_word_is_visible_but_does_not_count_as_discovered(self):
        with patch("app.game.record_game_start"):
            session = GameSession(
                session_id="hinted-session",
                seed="P-1234",
                title="Titre Secret",
                url="",
                image="",
                paragraphs=["Un texte de test."],
                mode="solo",
                category="general",
                difficulty="moyen",
            )

        token = next(token for token in session.tokens if token["is_word"])
        public_token = next(
            item for item in session.get_public_state({token["id"]})["tokens"]
            if item["id"] == token["id"]
        )

        self.assertEqual(public_token["text"], token["text"])
        self.assertTrue(public_token["hint_revealed"])
        self.assertFalse(public_token["revealed"])
        self.assertFalse(session.is_won)
        self.assertEqual(session.revealed_word_ids, set())

    def test_hint_schedule_uses_five_minutes_then_ninety_seconds(self):
        self.assertEqual(self.room.word_hint_initial_delay, 300.0)
        self.assertEqual(self.room.word_hint_interval, 90.0)


class GameProximityDisplayTests(unittest.TestCase):
    def test_morphological_index_matches_the_full_article_scan(self):
        with patch("app.game.record_game_start"):
            session = GameSession(
                session_id="morphological-index-test",
                seed="P-1234",
                title="Cheval et port",
                url="",
                image="",
                paragraphs=["Les chevaux galopent près des navires."],
                mode="solo",
                category="general",
            )

        for word in ("cheval", "chevaux", "galoper", "galopent", "navire", "ports"):
            expected = {
                target
                for target in session.word_to_token_ids
                if check_match(word, target)
            }
            with self.subTest(word=word):
                self.assertEqual(
                    set(session._find_matching_target_words(word)),
                    expected,
                )

    def _submit_proximity_guess(self, proximity):
        with (
            patch("app.game.record_game_start"),
            patch("app.game.record_guess"),
            patch("app.game.is_valid_french_word", return_value=True),
            patch("app.game.calculate_proximity", return_value=proximity),
        ):
            session = GameSession(
                session_id="proximity-test",
                seed="P-1234",
                title="Cible",
                url="",
                image="",
                paragraphs=["Un texte de test."],
                mode="solo",
                category="general",
            )
            token = next(token for token in session.tokens if token["is_word"])
            session.unrevealed_unique_words = {"cible"}
            session.word_to_token_ids = {"cible": [token["id"]]}
            result = session.submit_guess("autre")
        return result, session

    def test_semantic_link_below_threshold_does_not_grey_a_token(self):
        result, session = self._submit_proximity_guess(47.9)

        self.assertEqual(result["status"], "miss")
        self.assertEqual(result["score"], 0)
        self.assertEqual(result["close_tokens"], [])
        self.assertEqual(session.token_heat, {})

    def test_semantic_link_at_threshold_greys_the_matching_token(self):
        result, session = self._submit_proximity_guess(48.0)

        self.assertEqual(result["status"], "close")
        self.assertEqual(result["close_tokens"][0]["score"], 48)
        self.assertEqual(session.token_heat[next(iter(session.token_heat))], 48)

    def test_related_words_are_greyed_using_semantic_proximity(self):
        with (
            patch("app.game.record_game_start"),
            patch("app.game.record_guess"),
            patch("app.game.is_valid_french_word", return_value=True),
        ):
            session = GameSession(
                session_id="semantic-proximity-test",
                seed="P-1234",
                title="Océan",
                url="",
                image="",
                paragraphs=["L'eau couvre les mers."],
                mode="solo",
                category="general",
            )
            result = session.submit_guess("eau")

        ocean_tokens = [
            token_id
            for token_id, token in session.tokens_by_id.items()
            if token.get("normalized") == "ocean"
        ]
        self.assertTrue(ocean_tokens)
        self.assertTrue(
            any(
                item["id"] in ocean_tokens and item["score"] >= 48
                for item in result["close_tokens"]
            )
        )

    def test_numeric_token_is_revealed_when_guess_is_within_ten(self):
        with (
            patch("app.game.record_game_start"),
            patch("app.game.record_guess"),
            patch("app.game.is_valid_french_word", return_value=True),
        ):
            session = GameSession(
                session_id="numeric-proximity-test",
                seed="P-1234",
                title="Événement 1985",
                url="",
                image="",
                paragraphs=["Cet événement a eu lieu en 1985."],
                mode="solo",
                category="general",
            )
            year_token = next(
                token for token in session.tokens
                if token.get("normalized") == "1985"
            )
            year_token_id = year_token["id"]
            session.unrevealed_unique_words = {"1985"}
            session.word_to_token_ids = {"1985": [year_token_id]}

            outside_reveal_range = session.submit_guess("1975")
            revealed = session.submit_guess("1976")

        self.assertEqual(outside_reveal_range["status"], "close")
        self.assertEqual(outside_reveal_range["newly_revealed"], {})
        self.assertEqual(revealed["status"], "match")
        self.assertEqual(revealed["newly_revealed"][str(year_token_id)], "1985")
        self.assertTrue(session.tokens_by_id[year_token_id]["revealed"])


if __name__ == "__main__":
    unittest.main()
