import unittest
import random

from app.battleship import BattleshipManager, SHIP_LENGTHS


def simple_fleet(offset=0):
    rows = ["A", "C", "E", "G", "I"]
    fleet = {}
    for (ship_id, length), row in zip(SHIP_LENGTHS.items(), rows):
        start = offset + 1
        fleet[ship_id] = [f"{row}{start + index}" for index in range(length)]
    return fleet


class BattleshipTests(unittest.TestCase):
    def setUp(self):
        self.manager = BattleshipManager()

    def create_room(self, count=2):
        room = self.manager.create_room("p1", "Joueur 1")
        for index in range(2, count + 1):
            self.manager.join_room(room.room_id, f"p{index}", f"Joueur {index}")
        return room

    def ready_room(self, room):
        for player_id in room.players:
            self.manager.set_ready(room.room_id, player_id, True)
        return self.manager.start_room(room.room_id, "p1")

    def test_random_fleets_are_complete_valid_and_hidden_from_other_players(self):
        room = self.create_room()
        first_state = room.to_dict("p1")
        second_state = room.to_dict("p2")
        self.assertEqual(len(first_state["own_fleet"]), 5)
        self.assertEqual(
            {ship["ship_id"]: ship["length"] for ship in first_state["own_fleet"]},
            SHIP_LENGTHS,
        )
        self.assertNotIn("own_fleet", second_state["players"][0])
        self.assertEqual(sum(ship["length"] for ship in first_state["own_fleet"]), 17)

    def test_difficulty_presets_change_the_fleet_for_every_player(self):
        easy = self.manager.create_room("easy", "Facile", "facile")
        self.assertEqual(easy.difficulty, "facile")
        self.assertEqual(easy.to_dict("easy")["ship_lengths"], {
            "carrier": 4,
            "battleship": 3,
            "cruiser": 2,
            "submarine": 2,
            "destroyer": 1,
        })
        hard = self.manager.create_room("hard", "Difficile", "difficile")
        self.assertEqual(len(hard.to_dict("hard")["own_fleet"]), 6)
        self.assertEqual(hard.to_dict("hard")["ship_lengths"]["frigate"], 2)
        self.assertEqual(hard.to_dict("hard")["players"][0]["ships_remaining"], 6)
        self.manager.join_room(hard.room_id, "guest", "Invité")
        self.assertEqual(len(hard.players["guest"].fleet), 6)

    def test_room_directory_lists_open_rooms_and_marks_membership(self):
        room = self.manager.create_room("host", "Hôte", "facile")

        public_room = self.manager.list_rooms("visitor")[0]
        member_room = self.manager.list_rooms("host")[0]

        self.assertEqual(public_room["room_id"], room.room_id)
        self.assertFalse(public_room["is_member"])
        self.assertTrue(member_room["is_member"])
        self.assertEqual(member_room["difficulty"], "facile")

    def test_manual_fleet_validation_rejects_overlap_touching_and_invalid_ships(self):
        room = self.create_room()
        invalid = simple_fleet()
        invalid["battleship"] = ["A5", "A6", "A7", "A8"]
        with self.assertRaisesRegex(ValueError, "même case"):
            self.manager.set_fleet(room.room_id, "p1", invalid)

        invalid = simple_fleet()
        invalid["battleship"] = ["B1", "B2", "B3", "B4"]
        with self.assertRaisesRegex(ValueError, "toucher"):
            self.manager.set_fleet(room.room_id, "p1", invalid)

        invalid = simple_fleet()
        invalid["carrier"] = ["A1", "A2", "A3", "A4", "B5"]
        with self.assertRaisesRegex(ValueError, "ligne droite"):
            self.manager.set_fleet(room.room_id, "p1", invalid)

    def test_players_may_edit_or_randomize_fleet_until_marking_ready(self):
        room = self.create_room()
        self.manager.set_fleet(room.room_id, "p1", simple_fleet())
        self.manager.set_ready(room.room_id, "p1", True)
        self.manager.set_fleet(room.room_id, "p1", simple_fleet(1))
        self.assertFalse(room.players["p1"].ready)
        self.manager.randomize_fleet(room.room_id, "p1")
        self.assertEqual(len(room.players["p1"].fleet), 5)

    def test_only_host_starts_after_two_or_more_players_are_ready(self):
        room = self.manager.create_room("p1", "Joueur 1")
        self.manager.set_ready(room.room_id, "p1", True)
        with self.assertRaisesRegex(ValueError, "deux joueurs"):
            self.manager.start_room(room.room_id, "p1")
        room = self.create_room(3)
        self.manager.set_ready(room.room_id, "p1", True)
        self.manager.set_ready(room.room_id, "p2", True)
        self.manager.set_ready(room.room_id, "p3", True)
        with self.assertRaises(PermissionError):
            self.manager.start_room(room.room_id, "p2")
        self.manager.start_room(room.room_id, "p1")

    def test_hits_grant_extra_shots_and_miss_passes_the_turn(self):
        room = self.create_room()
        self.ready_room(room)
        room.players["p2"].fleet = simple_fleet()

        room, result = self.manager.fire(room.room_id, "p1", "A1")
        self.assertTrue(result["hit"])
        self.assertEqual(room.current_player_id, "p1")
        room, result = self.manager.fire(room.room_id, "p1", "A2")
        self.assertTrue(result["hit"])
        self.assertEqual(room.current_player_id, "p1")
        room, result = self.manager.fire(room.room_id, "p1", "B10")
        self.assertFalse(result["hit"])
        self.assertEqual(room.current_player_id, "p2")
        self.assertEqual(room.target_for("p2"), "p1")
        with self.assertRaisesRegex(ValueError, "pas votre tour"):
            self.manager.fire(room.room_id, "p1", "B9")

    def test_sinking_a_ship_is_reported_and_keeps_the_shooters_turn(self):
        room = self.create_room()
        self.ready_room(room)
        room.players["p2"].fleet = simple_fleet()

        for coordinate in ("A1", "A2", "A3", "A4"):
            room, result = self.manager.fire(room.room_id, "p1", coordinate)
            self.assertTrue(result["hit"])
            self.assertIsNone(result["sunk_ship"])
            target_shots = room.to_dict("p1")["target_shots"]
            self.assertTrue(all(shot["sunk_ship"] is None for shot in target_shots))
            self.assertTrue(all(not shot["sunk_ship_cells"] for shot in target_shots))

        room, result = self.manager.fire(room.room_id, "p1", "A5")

        self.assertEqual(result["sunk_ship"], "carrier")
        self.assertTrue(result["hit"])
        self.assertEqual(room.current_player_id, "p1")
        self.assertEqual(room.to_dict("p1")["players"][1]["ships_remaining"], 4)
        final_shot = room.to_dict("p1")["target_shots"][-1]
        self.assertEqual(final_shot["sunk_ship"], "carrier")
        self.assertEqual(final_shot["sunk_ship_cells"], ["A1", "A2", "A3", "A4", "A5"])

    def test_n_player_turn_order_skips_eliminated_players(self):
        room = self.create_room(4)
        self.ready_room(room)
        room.players["p2"].incoming_shots = {
            cell: "p1"
            for cells in room.players["p2"].fleet.values()
            for cell in cells
        }
        room.current_player_id = "p1"

        self.assertEqual(room.target_for("p1"), "p3")
        room.current_player_id = "p3"
        self.assertEqual(room.target_for("p3"), "p4")
        self.assertEqual(room.next_alive("p1"), "p3")

    def test_sinking_last_opponent_ship_ends_game_with_attacker_as_winner(self):
        room = self.create_room()
        self.ready_room(room)
        target = room.players["p2"]
        target.fleet = {
            "carrier": ["A1", "A2", "A3", "A4", "A5"],
            "battleship": ["C1", "C2", "C3", "C4"],
            "cruiser": ["E1", "E2", "E3"],
            "submarine": ["G1", "G2", "G3"],
            "destroyer": ["I1", "I2"],
        }
        all_cells = [cell for cells in target.fleet.values() for cell in cells]
        for cell in all_cells[:-1]:
            room.current_player_id = "p1"
            self.manager.fire(room.room_id, "p1", cell)
            if room.status != "playing":
                break

        room.current_player_id = "p1"
        room, result = self.manager.fire(room.room_id, "p1", all_cells[-1])
        self.assertEqual(room.status, "finished")
        self.assertEqual(room.winner_player_id, "p1")
        self.assertTrue(result["eliminated"])

    def test_room_reconnection_preserves_fleet_and_progress(self):
        room = self.create_room()
        fleet = room.players["p2"].fleet
        rejoined = self.manager.join_room(room.room_id, "p2", "Joueur 2")
        self.assertIs(rejoined, room)
        self.assertEqual(rejoined.players["p2"].fleet, fleet)

    def test_joining_a_running_room_adds_a_blocked_live_spectator(self):
        room = self.create_room()
        self.ready_room(room)
        shot = room.players["p2"].fleet["carrier"][0]
        self.manager.fire(room.room_id, "p1", shot)
        spectator_room = self.manager.join_room(room.room_id, "observer", "Observateur")

        spectator = spectator_room.players["observer"]
        state = spectator_room.to_dict("observer")
        self.assertTrue(spectator.is_spectator)
        self.assertTrue(state["is_spectator"])
        self.assertEqual(state["observed_player_id"], "p1")
        self.assertEqual(state["own_fleet"], [])
        self.assertEqual(state["target_shots"][0]["coordinate"], shot)
        self.assertTrue(state["target_shots"][0]["hit"])
        self.assertEqual(len(spectator_room._alive_ids()), 2)
        self.assertEqual(self.manager.list_rooms("observer")[0]["player_count"], 2)
        with self.assertRaisesRegex(ValueError, "spectateurs"):
            self.manager.fire(room.room_id, "observer", "A1")

    def test_host_restart_resets_match_and_promotes_queued_spectators(self):
        room = self.create_room()
        self.ready_room(room)
        self.manager.join_room(room.room_id, "observer", "Observateur")
        room.players["p1"].incoming_shots["A1"] = "p2"
        room.players["p1"].attacks.append({"coordinate": "A1"})
        with self.assertRaisesRegex(ValueError, "terminée"):
            self.manager.restart_room(room.room_id, "p1")
        room.status = "finished"

        with self.assertRaises(PermissionError):
            self.manager.restart_room(room.room_id, "p2")
        restarted = self.manager.restart_room(room.room_id, "p1")

        self.assertIs(restarted, room)
        self.assertEqual(room.status, "lobby")
        self.assertEqual(room.turn_number, 0)
        self.assertIsNone(room.current_player_id)
        self.assertIsNone(room.winner_player_id)
        self.assertFalse(room.players["observer"].is_spectator)
        self.assertTrue(all(not player.ready for player in room.players.values()))
        self.assertTrue(all(not player.incoming_shots for player in room.players.values()))
        self.assertTrue(all(not player.attacks for player in room.players.values()))
        for player_id in room.players:
            self.manager.set_ready(room.room_id, player_id, True)
        self.assertEqual(self.manager.start_room(room.room_id, "p1").status, "playing")

    def test_solo_fleet_can_be_placed_before_starting_and_bot_fleet_stays_hidden(self):
        room = self.manager.create_solo("human", "Capitaine", "difficile")
        state = room.to_dict("human")

        self.assertTrue(room.is_solo)
        self.assertEqual(room.bot_difficulty, "difficile")
        self.assertEqual(room.status, "lobby")
        self.assertIsNone(room.current_player_id)
        self.assertTrue(state["can_start"])
        self.assertEqual(room.ship_lengths, SHIP_LENGTHS)
        self.assertEqual(len(room.players), 2)
        self.assertNotIn("fleet", state["players"][1])
        self.assertEqual(len(state["own_fleet"]), len(SHIP_LENGTHS))

        fleet = simple_fleet()
        self.manager.set_fleet(room.room_id, "human", fleet)
        self.assertEqual(room.players["human"].fleet, fleet)
        self.assertEqual(room.status, "lobby")

        started = self.manager.start_room(room.room_id, "human")
        self.assertEqual(started.status, "playing")
        self.assertEqual(started.current_player_id, "human")
        self.assertEqual(started.players["human"].fleet, fleet)

    def test_solo_rooms_cannot_be_joined_by_another_player(self):
        room = self.manager.create_solo("human", "Capitaine")

        with self.assertRaisesRegex(ValueError, "ne peuvent pas être rejointes"):
            self.manager.join_room(room.room_id, "intruder", "Visiteur")

    def test_solo_bot_takes_a_turn_after_a_miss_and_never_repeats_a_shot(self):
        room = self.manager.create_solo("human", "Capitaine", "moyen")
        self.manager.start_room(room.room_id, "human")
        bot_id = next(player_id for player_id in room.players if player_id != "human")
        room.players[bot_id].fleet = simple_fleet()
        room, hit = self.manager.fire(room.room_id, "human", "A1")
        self.assertTrue(hit["hit"])
        self.assertEqual(hit["bot_shots"], [])
        self.assertEqual(room.current_player_id, "human")

        room, miss = self.manager.fire(room.room_id, "human", "B10")

        self.assertFalse(miss["hit"])
        self.assertTrue(miss["bot_shots"])
        self.assertEqual(room.current_player_id, "human")
        bot_shots = [shot["coordinate"] for shot in room.players[bot_id].attacks]
        self.assertEqual(len(bot_shots), len(set(bot_shots)))
        self.assertTrue(set(bot_shots) <= set(room.players["human"].incoming_shots))

    def test_bot_difficulty_selects_only_unshot_cells(self):
        for difficulty in ("facile", "moyen", "difficile"):
            room = self.manager.create_solo("human", "Capitaine", difficulty)
            bot_id = next(player_id for player_id in room.players if player_id != "human")
            bot = room.players[bot_id]
            bot.attacks.append({
                "coordinate": "A1",
                "hit": False,
                "sunk_ship": None,
                "sunk_ship_cells": [],
            })

            shot = self.manager.choose_bot_shot(room)

            self.assertNotEqual(shot, "A1")
            self.assertEqual(len(shot), 2)

    def test_hard_bot_uses_only_public_shot_history_not_hidden_fleet_layout(self):
        first_manager = BattleshipManager(rng=random.Random(31))
        second_manager = BattleshipManager(rng=random.Random(31))
        first = first_manager.create_solo("human", "Capitaine", "difficile")
        second = second_manager.create_solo("human", "Capitaine", "difficile")
        first_bot_id = next(player_id for player_id in first.players if player_id != "human")
        second_bot_id = next(player_id for player_id in second.players if player_id != "human")
        first_bot = first.players[first_bot_id]
        second_bot = second.players[second_bot_id]
        history = [
            {"coordinate": "A1", "hit": False, "sunk_ship": None, "sunk_ship_cells": []},
            {"coordinate": "B2", "hit": True, "sunk_ship": None, "sunk_ship_cells": []},
        ]
        first_bot.attacks = [dict(attack) for attack in history]
        second_bot.attacks = [dict(attack) for attack in history]
        first.players["human"].fleet = simple_fleet()
        second.players["human"].fleet = {
            "carrier": ["B1", "B2", "B3", "B4", "B5"],
            "battleship": ["D1", "D2", "D3", "D4"],
            "cruiser": ["F1", "F2", "F3"],
            "submarine": ["H1", "H2", "H3"],
            "destroyer": ["J1", "J2"],
        }

        first_shot = first_manager.choose_bot_shot(first)
        second_shot = second_manager.choose_bot_shot(second)

        self.assertEqual(first_shot, second_shot)
        self.assertNotIn(first_shot, {attack["coordinate"] for attack in history})

    def test_solo_restart_starts_a_fresh_game_against_the_same_bot_level(self):
        room = self.manager.create_solo("human", "Capitaine", "difficile")
        room.status = "finished"
        room.winner_player_id = "human"
        room.players["human"].attacks.append({"coordinate": "A1"})

        restarted = self.manager.restart_room(room.room_id, "human")

        self.assertIs(restarted, room)
        self.assertTrue(room.is_solo)
        self.assertEqual(room.bot_difficulty, "difficile")
        self.assertEqual(room.status, "lobby")
        self.assertIsNone(room.current_player_id)
        self.assertEqual(room.turn_number, 0)
        self.assertIsNone(room.winner_player_id)
        self.assertEqual(room.players["human"].attacks, [])
        self.assertEqual(room.match_number, 2)
        self.assertTrue(room.players[f"bot-{room.room_id}"].ready)

        self.manager.start_room(room.room_id, "human")
        self.assertEqual(room.status, "playing")
        self.assertEqual(room.current_player_id, "human")


if __name__ == "__main__":
    unittest.main()
