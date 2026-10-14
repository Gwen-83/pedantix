import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.game import GameSession
from app.room import Room, RoomPlayer


def make_session(session_id, revealed_ids=()):
    tokens = [
        {"id": 1, "is_word": True, "revealed": 1 in revealed_ids},
        {"id": 2, "is_word": True, "revealed": 2 in revealed_ids},
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
        first_session = make_session("first", revealed_ids={2})
        second_session = make_session("second")
        self.room.players = {
            "first": RoomPlayer("first", "Joueur 1", first_session),
            "second": RoomPlayer("second", "Joueur 2", second_session),
        }

        self.assertEqual(self.room._pick_next_hint_word_id(), 1)

    def test_team_hint_is_hidden_from_every_active_team(self):
        self.room.game_mode = "team"
        self.room.team_sessions = {
            "blue": make_session("blue", revealed_ids={2}),
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

        self.assertEqual(self.room._pick_next_hint_word_id(), 1)

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


if __name__ == "__main__":
    unittest.main()
