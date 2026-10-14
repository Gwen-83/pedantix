import unittest

from app.sudoku import (
    SUDOKU_AFTER_FIRST_SECONDS,
    SUDOKU_DIFFICULTIES,
    SudokuManager,
    _count_solutions,
    generate_puzzle,
)


class SudokuTests(unittest.TestCase):
    def setUp(self):
        self.now = 1_000.0
        self.manager = SudokuManager(clock=lambda: self.now)

    def solve_player(self, room, player_id):
        player = room.players[player_id]
        awarded = 0
        for row in range(9):
            for column in range(9):
                if room.puzzle[row][column]:
                    continue
                room, awarded = self.manager.set_room_cell(
                    room.room_id,
                    player_id,
                    row,
                    column,
                    room.solution[row][column],
                )
        return room, awarded

    def test_generated_puzzles_match_difficulty_and_have_one_solution(self):
        for difficulty, clue_count in SUDOKU_DIFFICULTIES.items():
            puzzle, solution = generate_puzzle(difficulty)
            self.assertEqual(sum(value != 0 for row in puzzle for value in row), clue_count)
            self.assertEqual(sum(value != 0 for row in solution for value in row), 81)
            for row in range(9):
                self.assertEqual(set(solution[row]), set(range(1, 10)))
                self.assertEqual(
                    {solution[index][row] for index in range(9)},
                    set(range(1, 10)),
                )
            for box_row in range(0, 9, 3):
                for box_column in range(0, 9, 3):
                    box = {
                        solution[row][column]
                        for row in range(box_row, box_row + 3)
                        for column in range(box_column, box_column + 3)
                    }
                    self.assertEqual(box, set(range(1, 10)))
            self.assertEqual(_count_solutions([row[:] for row in puzzle]), 1)
            self.assertTrue(
                all(
                    not value or value == solution[row][column]
                    for row, line in enumerate(puzzle)
                    for column, value in enumerate(line)
                )
            )

    def test_hard_generation_always_reaches_its_exact_clue_count(self):
        for _ in range(30):
            puzzle, _ = generate_puzzle("difficile")
            self.assertEqual(
                sum(value != 0 for row in puzzle for value in row),
                SUDOKU_DIFFICULTIES["difficile"],
            )

    def test_solo_rejects_clue_edits_and_hides_solution_until_solved(self):
        game = self.manager.create_solo("solo", "Solo", "facile")
        original = game.to_dict()
        self.assertIsNone(original["solution"])
        fixed = next(
            (row, column)
            for row in range(9)
            for column in range(9)
            if game.puzzle[row][column]
        )
        with self.assertRaisesRegex(ValueError, "grille de départ"):
            self.manager.set_solo_cell(game.game_id, "solo", *fixed, 0)
        for row in range(9):
            for column in range(9):
                if not game.puzzle[row][column]:
                    game = self.manager.set_solo_cell(
                        game.game_id, "solo", row, column, game.solution[row][column]
                    )
        self.assertEqual(game.status, "finished")
        self.assertEqual(game.to_dict()["solution"], game.solution)

    def test_solo_marks_wrong_entries_and_eliminates_after_three_errors(self):
        game = self.manager.create_solo("solo", "Solo", "facile")
        empty_cells = [
            (row, column)
            for row in range(9)
            for column in range(9)
            if game.puzzle[row][column] == 0
        ]

        row, column = empty_cells[0]
        wrong_value = game.solution[row][column] % 9 + 1
        game = self.manager.set_solo_cell(game.game_id, "solo", row, column, wrong_value)
        self.assertEqual(game.player.lives, 2)
        self.assertEqual(game.to_dict()["incorrect_cells"], [[row, column]])

        game = self.manager.set_solo_cell(game.game_id, "solo", row, column, wrong_value)
        self.assertEqual(game.player.lives, 2)
        game = self.manager.set_solo_cell(game.game_id, "solo", row, column, 0)
        self.assertEqual(game.player.lives, 2)
        self.assertEqual(game.to_dict()["incorrect_cells"], [])

        for row, column in empty_cells[:2]:
            wrong_value = game.solution[row][column] % 9 + 1
            game = self.manager.set_solo_cell(game.game_id, "solo", row, column, wrong_value)

        self.assertEqual(game.player.lives, 0)
        self.assertTrue(game.player.eliminated)
        self.assertFalse(game.to_dict()["solved"])
        self.assertEqual(game.finish_reason, "eliminated")
        self.assertEqual(len(game.to_dict()["incorrect_cells"]), 2)
        with self.assertRaisesRegex(ValueError, "terminée"):
            self.manager.set_solo_cell(game.game_id, "solo", *empty_cells[3], 1)

    def test_multiplayer_elimination_is_individual_and_other_players_can_finish(self):
        room = self.manager.create_room("p1", "Joueur 1", "facile")
        self.manager.join_room(room.room_id, "p2", "Joueur 2")
        self.manager.start_room(room.room_id, "p1")
        empty_cells = [
            (row, column)
            for row in range(9)
            for column in range(9)
            if room.puzzle[row][column] == 0
        ]

        for row, column in empty_cells[:3]:
            wrong_value = room.solution[row][column] % 9 + 1
            room, points = self.manager.set_room_cell(
                room.room_id, "p1", row, column, wrong_value
            )
            self.assertEqual(points, 0)

        self.assertTrue(room.players["p1"].eliminated)
        self.assertEqual(room.status, "playing")
        with self.assertRaisesRegex(ValueError, "éliminé"):
            self.manager.set_room_cell(room.room_id, "p1", *empty_cells[3], 1)

        room, points = self.solve_player(room, "p2")
        self.assertEqual(points, 3)
        self.assertEqual(room.status, "finished")
        self.assertEqual(room.finish_reason, "all_finished")

    def test_multiplayer_awards_three_two_one_and_stops_after_third_solver(self):
        room = self.manager.create_room("p1", "Joueur 1", "moyen")
        self.manager.join_room(room.room_id, "p2", "Joueur 2")
        self.manager.join_room(room.room_id, "p3", "Joueur 3")
        self.manager.start_room(room.room_id, "p1")

        room, points = self.solve_player(room, "p1")
        self.assertEqual(points, 3)
        self.assertEqual(room.deadline_at, self.now + SUDOKU_AFTER_FIRST_SECONDS)

        self.now += 10
        room, points = self.solve_player(room, "p2")
        self.assertEqual(points, 2)
        self.now += 10
        room, points = self.solve_player(room, "p3")
        self.assertEqual(points, 1)
        self.assertEqual(room.status, "finished")
        self.assertEqual(room.finish_reason, "podium")
        self.assertEqual(
            [item["points"] for item in room.to_dict("p1", self.now)["ranking"]],
            [3, 2, 1],
        )

    def test_multiplayer_closes_three_minutes_after_first_solve(self):
        room = self.manager.create_room("p1", "Joueur 1", "facile")
        self.manager.join_room(room.room_id, "p2", "Joueur 2")
        self.manager.start_room(room.room_id, "p1")
        room, points = self.solve_player(room, "p1")
        self.assertEqual(points, 3)

        self.now += SUDOKU_AFTER_FIRST_SECONDS
        room = self.manager.get_room(room.room_id, "p2")
        self.assertEqual(room.status, "finished")
        self.assertEqual(room.finish_reason, "time")
        self.assertEqual(room.to_dict("p2", self.now)["solution"], room.solution)

    def test_only_host_can_start_and_rooms_allow_unlimited_players(self):
        room = self.manager.create_room("p1", "Joueur 1", "difficile")
        for index in range(2, 31):
            self.manager.join_room(room.room_id, f"p{index}", f"Joueur {index}")
        with self.assertRaises(PermissionError):
            self.manager.start_room(room.room_id, "p2")
        self.assertEqual(len(room.players), 30)
        self.assertEqual(self.manager.start_room(room.room_id, "p1").status, "playing")

    def test_room_directory_lists_open_rooms_and_rejoining_preserves_progress(self):
        room = self.manager.create_room("host", "Hôte", "facile")
        self.manager.join_room(room.room_id, "guest", "Invité")
        self.manager.start_room(room.room_id, "host")
        row, column = next(
            (row, column)
            for row in range(9)
            for column in range(9)
            if room.puzzle[row][column] == 0
        )
        self.manager.set_room_cell(
            room.room_id, "guest", row, column, room.solution[row][column]
        )

        public_room = self.manager.list_rooms("visitor")[0]
        member_room = self.manager.list_rooms("guest")[0]
        resumed = self.manager.join_room(room.room_id, "guest", "Invité")

        self.assertEqual(public_room["room_id"], room.room_id)
        self.assertFalse(public_room["is_member"])
        self.assertTrue(member_room["is_member"])
        self.assertEqual(member_room["difficulty"], "facile")
        self.assertEqual(resumed.players["guest"].board[row][column], room.solution[row][column])


if __name__ == "__main__":
    unittest.main()
