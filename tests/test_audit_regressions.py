import time
import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app import main
from app.battleship import BattleshipManager
from app.bitoguessr import BitoguessrManager
from app.cemantix import CemantixManager
from app.geoguessr import GeoGuessrManager
from app.memories import MemoriesManager
from app.motus import MotusManager
from app.plongee import PlongeeManager
from app.scribbl import ScribblManager
from app.sudoku import SudokuManager
from app.undercover import UndercoverManager


@contextmanager
def store_game(game_id, manager):
    finish = MagicMock()
    score = MagicMock()
    with (
        patch.dict(
            main.STORE_ACTIVE_ROOM_GAMES,
            {game_id: (game_id, manager, f"{game_id}_player_id")},
            clear=True,
        ),
        patch.object(main, "private_store_invitation_rooms", set()),
        patch.object(main, "record_user_game_finish", finish),
        patch.object(main, "increment_player_score", score),
    ):
        yield SimpleNamespace(finish=finish, score=score)


def leave(game_id, room, player_id):
    return main._leave_store_multiplayer_room(game_id, room.room_id, player_id)


class UndercoverRegressionTests(unittest.TestCase):
    def setUp(self):
        self.manager = UndercoverManager()

    def start_room(self, roles):
        room = self.manager.create_room("p0", "Joueur 0")
        for index in range(1, len(roles)):
            self.manager.join_room(room.room_id, f"p{index}", f"Joueur {index}")
        self.manager.start_room(room.room_id, "p0")
        for index, role in enumerate(roles):
            player = room.players[f"p{index}"]
            player.role = role
            player.word = {
                "civilian": room.civilian_word,
                "undercover": room.undercover_word,
            }.get(role)
        return room

    def vote_out(self, room, target_id):
        self.manager.start_voting(room.room_id, room.host_player_id)
        voters = [
            player.player_id for player in room.players.values()
            if player.alive and not player.is_spectator
        ]
        fallback = next(voter for voter in voters if voter != target_id)
        for voter in voters:
            self.manager.vote(
                room.room_id, voter, fallback if voter == target_id else target_id
            )

    def test_mr_white_wins_when_only_one_civilian_remains(self):
        room = self.start_room(["civilian", "civilian", "mr_white"])

        self.vote_out(room, "p1")

        self.assertEqual(room.status, "finished")
        self.assertEqual(room.winner, "mr_white")

    def test_only_the_mr_white_just_eliminated_can_guess(self):
        room = self.start_room(
            ["civilian", "civilian", "civilian", "civilian", "mr_white", "mr_white", "undercover"]
        )
        self.vote_out(room, "p4")
        self.manager.guess_word(room.room_id, "p4", "mauvaise-reponse")
        self.assertEqual(room.phase, "discussion")
        self.vote_out(room, "p5")
        self.assertEqual(room.phase, "mr_white_guess")

        with self.assertRaisesRegex(ValueError, "ne pouvez pas proposer"):
            self.manager.guess_word(room.room_id, "p4", room.civilian_word)
        self.manager.guess_word(room.room_id, "p5", room.civilian_word)

        self.assertEqual(room.winner, "mr_white")

    def test_leaving_voter_or_target_does_not_block_or_crash_the_vote(self):
        room = self.start_room(["civilian", "civilian", "civilian", "civilian", "undercover"])
        self.manager.start_voting(room.room_id, "p0")
        self.manager.vote(room.room_id, "p0", "p4")
        self.manager.vote(room.room_id, "p1", "p3")
        self.manager.vote(room.room_id, "p2", "p4")
        self.manager.vote(room.room_id, "p4", "p3")

        with store_game("undercover", self.manager):
            self.assertEqual(leave("undercover", room, "p3"), {"status": "left"})

        self.assertNotIn("p3", room.players)
        self.assertEqual(room.phase, "voting")
        self.assertIsNone(room.players["p1"].vote)
        self.assertIsNone(room.players["p4"].vote)
        self.manager.vote(room.room_id, "p1", "p4")
        self.manager.vote(room.room_id, "p4", "p0")
        self.assertEqual(room.status, "finished")
        self.assertEqual(room.winner, "civilians")

    def test_leaving_mr_white_during_his_guess_resumes_the_game(self):
        room = self.start_room(
            ["civilian", "civilian", "civilian", "civilian", "mr_white", "undercover"]
        )
        self.vote_out(room, "p4")
        self.assertEqual(room.phase, "mr_white_guess")

        self.manager.leave_room(room.room_id, "p4")

        self.assertEqual(room.status, "playing")
        self.assertEqual(room.phase, "discussion")

    def test_results_credit_the_winning_roles(self):
        room = self.start_room(["civilian", "civilian", "undercover"])
        self.vote_out(room, "p2")
        self.assertEqual(room.winner, "civilians")

        with store_game("undercover", self.manager) as recorded:
            main._record_undercover_room_results(room)

        winners = {
            call.args[0]: call.kwargs["won"]
            for call in recorded.finish.call_args_list
        }
        self.assertEqual(
            winners, {"Joueur 0": True, "Joueur 1": True, "Joueur 2": False}
        )
        self.assertEqual(recorded.score.call_count, 2)


class LeaveRoomRegressionTests(unittest.TestCase):
    def test_battleship_survivor_wins_instead_of_targeting_own_board(self):
        manager = BattleshipManager()
        room = manager.create_room("alice", "Alice")
        manager.join_room(room.room_id, "bob", "Bob")
        for player_id in ("alice", "bob"):
            manager.set_ready(room.room_id, player_id, True)
        manager.start_room(room.room_id, "alice")

        with store_game("battleship", manager) as recorded:
            leave("battleship", room, "bob")

        self.assertEqual(room.status, "finished")
        self.assertEqual(room.winner_player_id, "alice")
        self.assertIsNone(room.to_dict("alice")["target_player_id"])
        self.assertTrue(recorded.finish.call_args.kwargs["won"])

    def test_battleship_turn_passes_to_the_next_player_in_order(self):
        manager = BattleshipManager()
        room = manager.create_room("alice", "Alice")
        for player_id in ("bob", "chloe", "david"):
            manager.join_room(room.room_id, player_id, player_id.title())
        for player_id in room.players:
            manager.set_ready(room.room_id, player_id, True)
        manager.start_room(room.room_id, "alice")
        room.current_player_id = "bob"

        with store_game("battleship", manager):
            leave("battleship", room, "bob")

        self.assertEqual(room.status, "playing")
        self.assertEqual(room.current_player_id, "chloe")

    def test_battleship_solo_games_are_not_listed_as_rooms(self):
        manager = BattleshipManager()
        manager.create_solo("alice", "Alice")

        self.assertEqual(manager.list_rooms("alice"), [])

    def test_motus_room_finishes_when_the_last_unfinished_player_leaves(self):
        manager = MotusManager(
            words={"talent", "tartes", "tanner", "tonton"}, answers={"talent"}
        )
        room = manager.create_room("alice", "Alice")
        manager.join_room(room.room_id, "bob", "Bob")
        manager.start_room(room.room_id, "alice")
        manager.guess_room(room.room_id, "alice", "talent")
        self.assertEqual(room.status, "playing")

        with store_game("motus", manager) as recorded:
            leave("motus", room, "bob")

        self.assertEqual(room.status, "finished")
        self.assertEqual(recorded.finish.call_count, 1)
        self.assertTrue(recorded.finish.call_args.kwargs["won"])

    def test_cemantix_round_resolves_without_the_departed_player(self):
        now = [1_000.0]
        manager = CemantixManager(
            words={"chat", "chien", "animal", "maison", "voiture"},
            answers={"chat"},
            clock=lambda: now[0],
        )
        room = manager.create_room("alice", "Alice")
        manager.join_room(room.room_id, "bob", "Bob")
        manager.join_room(room.room_id, "chloe", "Chloé")
        manager.start_room(room.room_id, "alice")
        manager.submit_room_guess(room.room_id, "bob", "chat")
        manager.submit_room_guess(room.room_id, "alice", "chien")

        with store_game("cemantix", manager):
            leave("cemantix", room, "bob")
            self.assertNotIn("bob", room.pending)
            self.assertEqual(room.status, "playing")
            self.assertEqual(room.round_number, 1)
            leave("cemantix", room, "chloe")

        self.assertEqual(room.round_number, 2)
        self.assertIsNone(room.winner_player_id)

    def test_sudoku_room_finishes_when_remaining_players_are_done(self):
        manager = SudokuManager()
        room = manager.create_room("alice", "Alice", "facile")
        manager.join_room(room.room_id, "bob", "Bob")
        manager.start_room(room.room_id, "alice")
        room.players["alice"].lives = 0

        with store_game("sudoku", manager):
            leave("sudoku", room, "bob")

        self.assertEqual(room.status, "finished")
        self.assertEqual(room.finish_reason, "all_finished")

    def test_geoguessr_next_round_starts_when_the_unready_player_leaves(self):
        manager = GeoGuessrManager()
        room = manager.create_room("alice", "Alice", "world", "cities", 2)
        manager.join_room(room.room_id, "bob", "Bob")
        for player_id in ("alice", "bob"):
            manager.confirm_room_ready(room.room_id, player_id)
        manager.start_room(room.room_id, "alice")
        for player_id in ("alice", "bob"):
            manager.guess_room(room.room_id, player_id, 48.85, 2.35)
        self.assertTrue(room.awaiting_next_round)
        manager.confirm_room_ready(room.room_id, "alice")

        with store_game("geoguessr", manager):
            leave("geoguessr", room, "bob")

        self.assertFalse(room.awaiting_next_round)
        self.assertEqual(room.round_index, 1)

    def test_geoguessr_results_survive_a_room_without_scored_players(self):
        manager = GeoGuessrManager()
        room = manager.create_room("alice", "Alice", "world", "cities", 1)
        room.status = "finished"

        with store_game("geoguessr", manager) as recorded:
            main._record_geoguessr_room_results(room)

        self.assertTrue(room.stats_recorded)
        recorded.finish.assert_not_called()

    def test_bitoguessr_last_round_finishes_when_the_missing_player_leaves(self):
        manager = BitoguessrManager()
        room = manager.create_room("alice", "Alice", "normal", 1)
        manager.join_room(room.room_id, "bob", "Bob")
        manager.start_room(room.room_id, "alice")
        country = room.current_round.question["countries"][0]
        manager.guess_room(room.room_id, "alice", country)

        with store_game("bitoguessr", manager):
            leave("bitoguessr", room, "bob")

        self.assertEqual(room.status, "finished")

    def test_plongee_round_ends_when_the_missing_player_leaves(self):
        manager = PlongeeManager()
        room = manager.create_room("alice", "Alice")
        manager.join_room(room.room_id, "bob", "Bob")
        manager.start_room(room.room_id, "alice")
        answer = room.prompts[0]["answers"][0]["answer"]
        manager.guess_room(room.room_id, "alice", answer)
        self.assertIsNone(room.last_round)

        with store_game("plongee", manager):
            leave("plongee", room, "bob")

        self.assertIsNotNone(room.last_round)

    def test_memory_turn_is_released_when_the_current_player_leaves(self):
        manager = MemoriesManager()
        room = manager.create_room("alice", "Alice")
        for player_id in ("bob", "chloe"):
            manager.join_room(room.room_id, player_id, player_id.title())
        for player_id in room.players:
            manager.set_ready(room.room_id, player_id)
        manager.start_room(room.room_id, "alice")
        manager.flip_room(room.room_id, "alice", 0)

        with store_game("memories", manager):
            leave("memories", room, "alice")

        self.assertEqual(room.opened, [])
        self.assertEqual(room.current_player.player_id, "bob")


class GameRuleRegressionTests(unittest.TestCase):
    def test_bitoguessr_solo_round_cannot_be_answered_twice(self):
        manager = BitoguessrManager()
        game = manager.create_solo("alice", "Alice", "normal")
        accepted = game.questions[0]["accepted"][0]
        manager.guess_solo(game.game_id, "alice", accepted)

        with self.assertRaisesRegex(ValueError, "déjà répondu"):
            manager.guess_solo(game.game_id, "alice", accepted)

        self.assertEqual(game.score, 1)
        self.assertEqual(len(game.results), 1)

    def test_plongee_rejects_answers_after_the_round_is_over(self):
        now = [1_000.0]
        manager = PlongeeManager(clock=lambda: now[0])
        room = manager.create_room("alice", "Alice")
        manager.join_room(room.room_id, "bob", "Bob")
        manager.start_room(room.room_id, "alice")
        now[0] += 60
        manager.get_room(room.room_id, "alice")
        self.assertIsNotNone(room.last_round)

        with self.assertRaisesRegex(ValueError, "manche est terminée"):
            manager.guess_room(
                room.room_id, "bob", room.prompts[0]["answers"][0]["answer"]
            )

        self.assertNotIn("bob", room.answers)

    def test_memory_replay_accepts_reflipping_a_card_after_a_mismatch(self):
        manager = MemoriesManager()
        game = manager.create_solo("alice", "Alice", 4)
        positions = {}
        for index, card in enumerate(game.cards):
            positions.setdefault(card, []).append(index)
        symbols = list(positions)
        first, second = positions[symbols[0]][0], positions[symbols[1]][0]
        flips = [first, second, first, positions[symbols[0]][1]]
        for symbol in symbols[1:]:
            flips.extend(positions[symbol])

        finished = manager.finish_solo(game.game_id, "alice", flips, 20_000)

        self.assertEqual(finished.status, "finished")
        self.assertEqual(finished.moves, 9)

    def test_sudoku_solo_timer_stops_when_the_grid_is_solved(self):
        now = [time.time()]
        manager = SudokuManager(clock=lambda: now[0])
        game = manager.create_solo("alice", "Alice", "facile")
        now[0] += 42
        for row in range(9):
            for column in range(9):
                if not game.puzzle[row][column]:
                    manager.set_solo_cell(
                        game.game_id, "alice", row, column, game.solution[row][column]
                    )
        self.assertEqual(game.status, "finished")

        with patch("app.sudoku.time.time", return_value=now[0] + 3_600):
            self.assertEqual(game.to_dict()["elapsed_seconds"], 42)

    def test_geoguessr_hides_other_guesses_until_the_round_is_resolved(self):
        manager = GeoGuessrManager()
        room = manager.create_room("alice", "Alice", "world", "cities", 2)
        manager.join_room(room.room_id, "bob", "Bob")
        for player_id in ("alice", "bob"):
            manager.confirm_room_ready(room.room_id, player_id)
        manager.start_room(room.room_id, "alice")
        manager.guess_room(room.room_id, "alice", 48.85, 2.35)

        bob_view = {
            player["player_id"]: player for player in room.to_dict("bob")["players"]
        }
        self.assertTrue(bob_view["alice"]["submitted"])
        self.assertIsNone(bob_view["alice"]["guess"])
        self.assertIsNotNone(room.to_dict("alice")["player"]["guess"])

        manager.guess_room(room.room_id, "bob", 40.0, -3.0)
        resolved = {
            player["player_id"]: player for player in room.to_dict("bob")["players"]
        }
        self.assertIsNotNone(resolved["alice"]["guess"])


class ScribblRegressionTests(unittest.TestCase):
    def setUp(self):
        self.manager = ScribblManager()
        self.room = self.manager.create_room("a", "Alice", 2)
        for player_id, name in (("b", "Bob"), ("c", "Chloé")):
            self.manager.join_room(self.room.room_id, player_id, name)
        self.manager.start_room(self.room.room_id, "a")

    def finish_turn(self):
        for _ in range(3):
            if self.room.status != "playing":
                return
            self.room.turn_ends_at = time.time() - 1
            self.manager.advance_timers(self.room.room_id)
            if self.room.phase == "choosing":
                return

    def test_turn_order_is_preserved_when_an_earlier_player_leaves(self):
        self.finish_turn()
        self.assertEqual(self.room.artist_player_id, "b")

        self.manager.leave_room(self.room.room_id, "a")
        self.assertEqual(self.room.artist_player_id, "b")
        self.finish_turn()

        self.assertEqual(self.room.artist_player_id, "c")
        self.assertEqual(self.room.round_number, 1)

    def test_next_player_draws_when_the_artist_leaves(self):
        self.manager.leave_room(self.room.room_id, "a")
        self.assertEqual(self.room.phase, "reveal")

        self.finish_turn()

        self.assertEqual(self.room.artist_player_id, "b")
        self.assertEqual(self.room.round_number, 1)
        self.assertEqual(self.room.turn_count, 4)

    def test_artist_cannot_reveal_the_word_in_chat(self):
        self.manager.choose_word(self.room.room_id, "a", 0)
        word = self.room.word

        with self.assertRaisesRegex(ValueError, "Ne révélez pas"):
            self.manager.send_message(self.room.room_id, "a", f"c'est {word.upper()} !")

        self.room.players["a"].last_message_at = 0
        self.manager.send_message(self.room.room_id, "a", "Bon courage")
        self.assertEqual(self.room.chat[-1]["text"], "Bon courage")


class IdleRoomCleanupTests(unittest.TestCase):
    def test_rooms_nobody_polls_are_removed_after_the_idle_delay(self):
        manager = MotusManager(
            words={"talent", "tartes", "tanner", "tonton"}, answers={"talent"}
        )
        idle_room = manager.create_room("alice", "Alice")
        active_room = manager.create_room("bob", "Bob")
        old_solo = manager.create_solo("alice", "Alice")
        old_solo.created_at -= main.SOLO_GAME_TTL_SECONDS + 1
        recent_solo = manager.create_solo("bob", "Bob")

        with (
            store_game("motus", manager),
            patch.dict(main._room_activity, {}, clear=True),
        ):
            main._prune_idle_rooms(["motus"])
            self.assertEqual(len(manager.rooms), 2)
            stale = time.time() - main.ROOM_IDLE_TTL_SECONDS - 1
            main._room_activity[("motus", idle_room.room_id)] = stale
            main._room_activity[("motus", active_room.room_id)] = stale
            main._touch_room_activity("motus", active_room.room_id.lower())

            main._prune_idle_rooms(["motus"])

        self.assertEqual(list(manager.rooms), [active_room.room_id])
        self.assertEqual(list(manager.solo_games), [recent_solo.game_id])


class AbsentPlayerEvictionTests(unittest.TestCase):
    @contextmanager
    def tracked(self, game_id, manager):
        with (
            store_game(game_id, manager) as recorded,
            patch.dict(main._player_activity, {}, clear=True),
            patch.dict(main._room_absence_checks, {}, clear=True),
            patch.dict(main._room_activity, {}, clear=True),
        ):
            yield recorded

    def expire(self, game_id, room, player_id):
        ttl = main.PLAYER_ABSENCE_TTL_BY_GAME.get(
            game_id, main.PLAYER_ABSENCE_TTL_SECONDS
        )
        main._player_activity[(game_id, room.room_id, player_id)] = (
            time.time() - ttl - 1
        )

    def test_player_who_stops_polling_is_removed_and_the_game_recovers(self):
        manager = MotusManager(
            words={"talent", "tartes", "tanner", "tonton"}, answers={"talent"}
        )
        room = manager.create_room("alice", "Alice")
        manager.join_room(room.room_id, "bob", "Bob")
        manager.start_room(room.room_id, "alice")
        manager.guess_room(room.room_id, "alice", "talent")

        with self.tracked("motus", manager):
            self.assertEqual(main._evict_absent_players("motus", room.room_id), [])
            main._touch_room_activity("motus", room.room_id.lower(), "alice")
            self.expire("motus", room, "bob")

            evicted = main._evict_absent_players("motus", room.room_id, force=True)

            self.assertEqual(evicted, ["bob"])
            self.assertEqual(list(room.players), ["alice"])
            self.assertEqual(room.status, "finished")
            self.assertNotIn(("motus", room.room_id, "bob"), main._player_activity)

    def test_absent_host_is_replaced_and_empty_rooms_disappear(self):
        manager = MemoriesManager()
        room = manager.create_room("alice", "Alice")
        manager.join_room(room.room_id, "bob", "Bob")

        with self.tracked("memories", manager):
            main._touch_room_activity("memories", room.room_id, "bob")
            self.expire("memories", room, "alice")
            main._evict_absent_players("memories", room.room_id, force=True)
            self.assertEqual(room.host_player_id, "bob")

            self.expire("memories", room, "bob")
            main._prune_idle_rooms(["memories"])

        self.assertEqual(manager.rooms, {})

    def test_checks_are_throttled_and_rejoining_resets_the_absence_timer(self):
        manager = MemoriesManager()
        room = manager.create_room("alice", "Alice")
        manager.join_room(room.room_id, "bob", "Bob")

        with self.tracked("memories", manager):
            main._evict_absent_players("memories", room.room_id)
            self.expire("memories", room, "bob")
            self.assertEqual(main._evict_absent_players("memories", room.room_id), [])
            main._touch_room_activity("memories", room.room_id, "bob")
            self.assertEqual(
                main._evict_absent_players("memories", room.room_id, force=True), []
            )

        self.assertIn("bob", room.players)

    def test_solo_battleship_bot_is_never_evicted(self):
        manager = BattleshipManager()
        room = manager.create_solo("alice", "Alice")
        bot_id = next(player_id for player_id in room.players if player_id != "alice")

        with self.tracked("battleship", manager):
            self.expire("battleship", room, bot_id)
            self.assertEqual(
                main._evict_absent_players("battleship", room.room_id, force=True), []
            )

        self.assertIn(bot_id, room.players)

    def test_scribbl_artist_with_a_closed_tab_loses_the_turn_quickly(self):
        manager = ScribblManager()
        room = manager.create_room("a", "Alice", 1)
        for player_id, name in (("b", "Bob"), ("c", "Chloé")):
            manager.join_room(room.room_id, player_id, name)
        manager.start_room(room.room_id, "a")

        with self.tracked("scribbl", manager):
            for player_id in ("b", "c"):
                main._touch_room_activity("scribbl", room.room_id, player_id)
            self.expire("scribbl", room, "a")

            evicted = main._evict_absent_players("scribbl", room.room_id, force=True)

        self.assertEqual(evicted, ["a"])
        self.assertEqual(room.phase, "reveal")
        self.assertEqual(room.host_player_id, "b")
        self.assertLess(
            main.PLAYER_ABSENCE_TTL_BY_GAME["scribbl"], main.PLAYER_ABSENCE_TTL_SECONDS
        )

    def test_room_polling_over_http_marks_the_player_present(self):
        from fastapi.testclient import TestClient

        manager = MemoriesManager()
        room = manager.create_room("alice", "Alice")
        manager.join_room(room.room_id, "bob", "Bob")

        with (
            self.tracked("memories", manager),
            patch.object(main, "memories_manager", manager),
        ):
            self.expire("memories", room, "alice")
            self.expire("memories", room, "bob")
            response = TestClient(main.app).get(
                f"/api/memories/room/{room.room_id}", params={"player_id": "alice"}
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(list(room.players), ["alice"])
            self.assertEqual(response.json()["player_count"], 1)


if __name__ == "__main__":
    unittest.main()
