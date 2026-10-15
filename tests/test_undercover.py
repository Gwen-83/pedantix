import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import main
from app.main import app, undercover_manager
from app.undercover import WORD_PAIRS, UndercoverManager, role_counts


class UndercoverTests(unittest.TestCase):
    def setUp(self):
        self.manager = UndercoverManager()

    def add_players(self, count):
        room = self.manager.create_room("p0", "Joueur 0")
        for index in range(1, count):
            self.manager.join_room(room.room_id, f"p{index}", f"Joueur {index}")
        return room

    def submit_votes(self, room, target_id):
        self.manager.start_voting(room.room_id, room.host_player_id)
        active_players = [
            player
            for player in room.players.values()
            if not player.is_spectator and player.alive
        ]
        for player in active_players:
            if player.player_id == target_id:
                continue
            self.manager.vote(room.room_id, player.player_id, target_id)
        other = next(
            player
            for player in active_players
            if player.player_id != target_id
        )
        self.manager.vote(room.room_id, target_id, other.player_id)

    def test_word_pair_dictionary_has_more_than_ten_thousand_unique_pairs(self):
        self.assertGreater(len(WORD_PAIRS), 10_000)
        self.assertEqual(len(set(tuple(sorted(pair)) for pair in WORD_PAIRS)), len(WORD_PAIRS))
        self.assertTrue(all(first != second for first, second in WORD_PAIRS))

    def test_role_counts_scale_with_active_player_count(self):
        self.assertEqual(role_counts(2), {"civilian": 0, "undercover": 0, "mr_white": 0})
        self.assertEqual(role_counts(3), {"civilian": 2, "undercover": 1, "mr_white": 0})
        self.assertEqual(role_counts(6), {"civilian": 4, "undercover": 1, "mr_white": 1})
        self.assertEqual(role_counts(7), {"civilian": 4, "undercover": 2, "mr_white": 1})
        self.assertEqual(role_counts(13), {"civilian": 8, "undercover": 3, "mr_white": 2})

    def test_start_assigns_roles_and_keeps_other_players_secrets_hidden(self):
        room = self.add_players(1)
        with self.assertRaisesRegex(ValueError, "au moins 3 joueurs"):
            self.manager.start_room(room.room_id, "p0")
        self.manager.join_room(room.room_id, "p1", "Joueur 1")
        self.manager.join_room(room.room_id, "p2", "Joueur 2")
        for index in range(3, 7):
            self.manager.join_room(room.room_id, f"p{index}", f"Joueur {index}")
        self.manager.start_room(room.room_id, "p0")

        roles = [player.role for player in room.players.values()]
        self.assertEqual(roles.count("undercover"), 2)
        self.assertEqual(roles.count("mr_white"), 1)
        self.assertEqual(roles.count("civilian"), 4)
        for viewer_id in room.players:
            state = room.to_dict(viewer_id)
            self.assertIsNone(state["words"])
            self.assertTrue(all(item["role"] is None for item in state["players"]))
            self.assertEqual(state["player"]["role"], room.players[viewer_id].role)
            self.assertEqual(
                state["player"]["word"], room.players[viewer_id].word
            )

    def test_voting_eliminates_undercover_and_ends_with_civilian_victory(self):
        room = self.add_players(4)
        self.manager.start_room(room.room_id, "p0")
        undercover = next(
            player for player in room.players.values() if player.role == "undercover"
        )
        self.submit_votes(room, undercover.player_id)
        self.assertEqual(room.status, "finished")
        self.assertEqual(room.winner, "civilians")
        self.assertFalse(undercover.alive)
        self.assertEqual(room.to_dict("p0")["words"]["civilian"], room.civilian_word)

    def test_undercover_team_wins_when_it_reaches_civilian_parity(self):
        room = self.add_players(4)
        self.manager.start_room(room.room_id, "p0")
        room.players["p0"].role = "undercover"
        room.players["p0"].word = room.undercover_word
        for player_id in ("p1", "p2", "p3"):
            room.players[player_id].role = "civilian"
            room.players[player_id].word = room.civilian_word

        self.submit_votes(room, "p1")
        self.assertEqual(room.phase, "discussion")
        self.submit_votes(room, "p2")

        self.assertEqual(room.status, "finished")
        self.assertEqual(room.winner, "undercover")

    def test_tied_vote_starts_a_fresh_discussion_round(self):
        room = self.add_players(4)
        self.manager.start_room(room.room_id, "p0")
        self.manager.start_voting(room.room_id, "p0")
        for voter, target in (("p0", "p1"), ("p1", "p0"), ("p2", "p3"), ("p3", "p2")):
            self.manager.vote(room.room_id, voter, target)

        self.assertEqual(room.phase, "discussion")
        self.assertEqual(room.round_number, 2)
        self.assertEqual(room.last_result["type"], "tie")

    def test_each_player_can_confirm_their_clue_to_advance_to_voting(self):
        room = self.add_players(3)
        self.manager.start_room(room.room_id, "p0")
        self.manager.mark_spoken(room.room_id, "p0")
        self.manager.mark_spoken(room.room_id, "p1")
        self.assertEqual(room.phase, "discussion")
        self.manager.mark_spoken(room.room_id, "p2")
        self.assertEqual(room.phase, "voting")

    def test_mr_white_can_guess_the_civilian_word_after_elimination(self):
        room = self.add_players(6)
        self.manager.start_room(room.room_id, "p0")
        mr_white = next(
            player for player in room.players.values() if player.role == "mr_white"
        )
        self.submit_votes(room, mr_white.player_id)

        self.assertEqual(room.phase, "mr_white_guess")
        self.manager.guess_word(room.room_id, mr_white.player_id, room.civilian_word)
        self.assertEqual(room.status, "finished")
        self.assertEqual(room.winner, "mr_white")

    def test_failed_mr_white_guess_starts_next_discussion(self):
        room = self.add_players(6)
        self.manager.start_room(room.room_id, "p0")
        mr_white = next(
            player for player in room.players.values() if player.role == "mr_white"
        )
        self.submit_votes(room, mr_white.player_id)

        self.manager.guess_word(room.room_id, mr_white.player_id, "mot impossible")

        self.assertEqual(room.status, "playing")
        self.assertEqual(room.phase, "discussion")
        self.assertEqual(room.round_number, 2)
        self.assertFalse(mr_white.alive)

    def test_late_joiner_is_a_secret_free_spectator_until_host_restart(self):
        room = self.add_players(3)
        self.manager.start_room(room.room_id, "p0")
        self.manager.join_room(room.room_id, "observer", "Observateur")
        observer = room.players["observer"]

        state = room.to_dict("observer")
        self.assertTrue(state["player"]["is_spectator"])
        self.assertIsNone(state["player"]["role"])
        self.assertTrue(all(item["role"] is None for item in state["players"]))
        with self.assertRaisesRegex(ValueError, "spectateurs"):
            self.manager.mark_spoken(room.room_id, "observer")

        undercover = next(
            player for player in room.players.values() if player.role == "undercover"
        )
        self.submit_votes(room, undercover.player_id)
        self.manager.restart_room(room.room_id, "p0")
        self.assertEqual(room.status, "lobby")
        self.assertFalse(observer.is_spectator)
        self.assertIsNone(observer.role)
        self.assertEqual(room.match_number, 2)


class UndercoverRouteTests(unittest.TestCase):
    def test_undercover_page_and_room_api_work(self):
        with TestClient(app) as client:
            page = client.get("/games/undercover/")
            created = client.post(
                "/api/undercover/room/create",
                json={"player_id": "route-host", "player_name": "Hôte"},
            )
            presence = client.post(
                "/api/presence",
                json={
                    "session_id": "undercover-route-test",
                    "username": "Hôte",
                    "game_id": "undercover",
                },
            )

        self.assertEqual(page.status_code, 200)
        self.assertIn("Undercover", page.text)
        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.json()["status"], "lobby")
        self.assertEqual(presence.status_code, 200)
        undercover_manager.rooms.pop(created.json()["room_id"], None)
        with main.online_presence_lock:
            main.online_presence.pop("undercover-route-test", None)

    def test_multiplayer_routes_start_and_advance_a_lobby_round(self):
        with TestClient(app) as client:
            created = client.post(
                "/api/undercover/room/create",
                json={"player_id": "api-host", "player_name": "Hôte"},
            ).json()
            room_id = created["room_id"]
            for player_id in ("api-guest-1", "api-guest-2"):
                joined = client.post(
                    "/api/undercover/room/join",
                    json={
                        "room_id": room_id,
                        "player_id": player_id,
                        "player_name": player_id,
                    },
                )
                self.assertEqual(joined.status_code, 200)

            with patch("app.database._enqueue") as enqueue:
                started = client.post(
                    "/api/undercover/room/start",
                    json={
                        "room_id": room_id,
                        "player_id": "api-host",
                        "player_name": "Hôte",
                    },
                )
            self.assertEqual(started.status_code, 200)
            self.assertEqual(started.json()["phase"], "discussion")
            enqueue.assert_called_once()

            for player_id in ("api-host", "api-guest-1", "api-guest-2"):
                response = client.post(
                    "/api/undercover/room/spoken",
                    json={
                        "room_id": room_id,
                        "player_id": player_id,
                        "player_name": player_id,
                    },
                )
                self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["phase"], "voting")
            undercover_manager.rooms.pop(room_id, None)


if __name__ == "__main__":
    unittest.main()
