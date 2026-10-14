import random
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

SUDOKU_SIZE = 9
SUDOKU_DIFFICULTIES = {
    "facile": 40,
    "moyen": 32,
    "difficile": 26,
}
SUDOKU_RANKING_POINTS = (3, 2, 1)
SUDOKU_AFTER_FIRST_SECONDS = 180
SUDOKU_GENERATION_ATTEMPTS = 64


def _pattern(row: int, column: int) -> int:
    return (row * 3 + row // 3 + column) % SUDOKU_SIZE


def _shuffle_groups(rng: random.Random) -> List[int]:
    groups = list(range(3))
    rng.shuffle(groups)
    return [group * 3 + offset for group in groups for offset in rng.sample(range(3), 3)]


def _generate_solution(rng: random.Random) -> List[List[int]]:
    rows = _shuffle_groups(rng)
    columns = _shuffle_groups(rng)
    digits = rng.sample(range(1, SUDOKU_SIZE + 1), SUDOKU_SIZE)
    return [[digits[_pattern(row, column)] for column in columns] for row in rows]


def _count_solutions(board: List[List[int]], limit: int = 2) -> int:
    row_used = [set() for _ in range(SUDOKU_SIZE)]
    column_used = [set() for _ in range(SUDOKU_SIZE)]
    box_used = [set() for _ in range(SUDOKU_SIZE)]
    empty = []

    for row in range(SUDOKU_SIZE):
        for column in range(SUDOKU_SIZE):
            value = board[row][column]
            if not value:
                empty.append((row, column))
                continue
            box = row // 3 * 3 + column // 3
            if value in row_used[row] or value in column_used[column] or value in box_used[box]:
                return 0
            row_used[row].add(value)
            column_used[column].add(value)
            box_used[box].add(value)

    solutions = 0

    def solve() -> None:
        nonlocal solutions
        if solutions >= limit:
            return
        best_index = -1
        candidates = None
        for index, (row, column) in enumerate(empty):
            if board[row][column]:
                continue
            box = row // 3 * 3 + column // 3
            available = set(range(1, SUDOKU_SIZE + 1)) - row_used[row] - column_used[column] - box_used[box]
            if candidates is None or len(available) < len(candidates):
                best_index = index
                candidates = available
                if len(available) <= 1:
                    break
        if best_index == -1:
            solutions += 1
            return
        if not candidates:
            return
        row, column = empty[best_index]
        box = row // 3 * 3 + column // 3
        empty[best_index], empty[-1] = empty[-1], empty[best_index]
        empty.pop()
        for value in candidates:
            board[row][column] = value
            row_used[row].add(value)
            column_used[column].add(value)
            box_used[box].add(value)
            solve()
            row_used[row].remove(value)
            column_used[column].remove(value)
            box_used[box].remove(value)
            board[row][column] = 0
            if solutions >= limit:
                break
        empty.append((row, column))
        empty[best_index], empty[-1] = empty[-1], empty[best_index]

    solve()
    return solutions


def generate_puzzle(difficulty: str) -> tuple[List[List[int]], List[List[int]]]:
    clues = SUDOKU_DIFFICULTIES.get(difficulty)
    if clues is None:
        raise ValueError("Difficulté invalide. Choisissez facile, moyen ou difficile.")
    for _ in range(SUDOKU_GENERATION_ATTEMPTS):
        rng = random.Random()
        solution = _generate_solution(rng)
        puzzle = [row[:] for row in solution]
        cells = [(row, column) for row in range(9) for column in range(9)]
        rng.shuffle(cells)
        remaining = SUDOKU_SIZE * SUDOKU_SIZE
        for row, column in cells:
            if remaining <= clues:
                break
            value = puzzle[row][column]
            puzzle[row][column] = 0
            if _count_solutions(puzzle) == 1:
                remaining -= 1
            else:
                puzzle[row][column] = value
        if remaining == clues:
            return puzzle, solution
    raise RuntimeError("Impossible de générer une grille Sudoku de cette difficulté. Réessayez.")


def _empty_board(puzzle: List[List[int]]) -> List[List[int]]:
    return [row[:] for row in puzzle]


def _valid_cell(row: int, column: int, value: int) -> None:
    if not 0 <= row < SUDOKU_SIZE or not 0 <= column < SUDOKU_SIZE:
        raise ValueError("Case invalide.")
    if not 0 <= value <= SUDOKU_SIZE:
        raise ValueError("La valeur doit être comprise entre 1 et 9, ou 0 pour effacer.")


def _is_solved(board: List[List[int]], solution: List[List[int]]) -> bool:
    return board == solution


@dataclass
class SudokuPlayer:
    player_id: str
    name: str
    board: List[List[int]]
    solved_at: Optional[float] = None
    rank: Optional[int] = None
    points: int = 0


@dataclass
class SudokuGame:
    game_id: str
    difficulty: str
    puzzle: List[List[int]]
    solution: List[List[int]]
    player: SudokuPlayer
    status: str = "playing"
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict:
        return {
            "game_id": self.game_id,
            "status": self.status,
            "difficulty": self.difficulty,
            "puzzle": self.puzzle,
            "board": self.player.board,
            "solved": self.status == "finished",
            "elapsed_seconds": max(0, int(time.time() - self.created_at)),
            "solution": self.solution if self.status == "finished" else None,
        }


@dataclass
class SudokuRoom:
    room_id: str
    difficulty: str
    puzzle: List[List[int]]
    solution: List[List[int]]
    host_player_id: str
    players: Dict[str, SudokuPlayer] = field(default_factory=dict)
    status: str = "lobby"
    first_solved_at: Optional[float] = None
    deadline_at: Optional[float] = None
    finish_reason: Optional[str] = None

    def advance(self, now: float) -> None:
        if self.status == "playing" and self.deadline_at is not None and now >= self.deadline_at:
            self.status = "finished"
            self.finish_reason = "time"

    def to_dict(self, player_id: str, now: float) -> Dict:
        self.advance(now)
        player = self.players[player_id]
        solved_players = sorted(
            (item for item in self.players.values() if item.rank is not None),
            key=lambda item: item.rank or 0,
        )
        return {
            "room_id": self.room_id,
            "status": self.status,
            "difficulty": self.difficulty,
            "host_player_id": self.host_player_id,
            "player_id": player_id,
            "puzzle": self.puzzle,
            "board": player.board,
            "player": {
                "player_id": player.player_id,
                "name": player.name,
                "solved": player.rank is not None,
                "rank": player.rank,
                "points": player.points,
                "filled_cells": sum(value != 0 for row in player.board for value in row)
                - sum(value != 0 for row in self.puzzle for value in row),
            },
            "players": [
                {
                    "player_id": item.player_id,
                    "name": item.name,
                    "solved": item.rank is not None,
                    "rank": item.rank,
                    "points": item.points,
                }
                for item in self.players.values()
            ],
            "solved_count": len(solved_players),
            "can_start": self.status == "lobby" and len(self.players) >= 2,
            "first_solved_at": self.first_solved_at,
            "deadline_at": self.deadline_at,
            "seconds_after_first": SUDOKU_AFTER_FIRST_SECONDS,
            "finish_reason": self.finish_reason,
            "solution": self.solution if self.status == "finished" else None,
            "ranking": [
                {
                    "player_id": item.player_id,
                    "name": item.name,
                    "rank": item.rank,
                    "points": item.points,
                }
                for item in solved_players
            ],
        }


class SudokuManager:
    def __init__(self, clock: Callable[[], float] = time.time):
        self.solo_games: Dict[str, SudokuGame] = {}
        self.rooms: Dict[str, SudokuRoom] = {}
        self._clock = clock
        self._lock = threading.RLock()

    @staticmethod
    def _validate_difficulty(difficulty: str) -> str:
        if difficulty not in SUDOKU_DIFFICULTIES:
            raise ValueError("Difficulté invalide. Choisissez facile, moyen ou difficile.")
        return difficulty

    def create_solo(self, player_id: str, player_name: str, difficulty: str) -> SudokuGame:
        with self._lock:
            difficulty = self._validate_difficulty(difficulty)
            puzzle, solution = generate_puzzle(difficulty)
            game_id = uuid.uuid4().hex
            game = SudokuGame(
                game_id=game_id,
                difficulty=difficulty,
                puzzle=puzzle,
                solution=solution,
                player=SudokuPlayer(player_id, player_name, _empty_board(puzzle)),
                created_at=self._clock(),
            )
            self.solo_games[game_id] = game
            return game

    def get_solo(self, game_id: str, player_id: str) -> SudokuGame:
        with self._lock:
            game = self.solo_games.get(game_id)
            if game is None or game.player.player_id != player_id:
                raise KeyError("Cette partie Sudoku est introuvable.")
            return game

    def set_solo_cell(self, game_id: str, player_id: str, row: int, column: int, value: int) -> SudokuGame:
        with self._lock:
            game = self.get_solo(game_id, player_id)
            if game.status != "playing":
                raise ValueError("Cette partie est déjà terminée.")
            _valid_cell(row, column, value)
            if game.puzzle[row][column]:
                raise ValueError("Cette case fait partie de la grille de départ.")
            game.player.board[row][column] = value
            if _is_solved(game.player.board, game.solution):
                game.status = "finished"
            return game

    def create_room(self, player_id: str, player_name: str, difficulty: str) -> SudokuRoom:
        with self._lock:
            difficulty = self._validate_difficulty(difficulty)
            puzzle, solution = generate_puzzle(difficulty)
            room_id = uuid.uuid4().hex[:6].upper()
            while room_id in self.rooms:
                room_id = uuid.uuid4().hex[:6].upper()
            room = SudokuRoom(room_id, difficulty, puzzle, solution, player_id)
            room.players[player_id] = SudokuPlayer(player_id, player_name, _empty_board(puzzle))
            self.rooms[room_id] = room
            return room

    def join_room(self, room_id: str, player_id: str, player_name: str) -> SudokuRoom:
        with self._lock:
            room = self.rooms.get(room_id.upper())
            if room is None:
                raise KeyError("Salon introuvable ou expiré.")
            if player_id in room.players:
                room.players[player_id].name = player_name
                return room
            if room.status != "lobby":
                raise ValueError("La partie a commencé. Seuls les joueurs déjà inscrits peuvent revenir.")
            room.players[player_id] = SudokuPlayer(player_id, player_name, _empty_board(room.puzzle))
            return room

    def get_room(self, room_id: str, player_id: str) -> SudokuRoom:
        with self._lock:
            room = self.rooms.get(room_id.upper())
            if room is None or player_id not in room.players:
                raise KeyError("Salon ou joueur introuvable.")
            room.advance(self._clock())
            return room

    def start_room(self, room_id: str, player_id: str) -> SudokuRoom:
        with self._lock:
            room = self.get_room(room_id, player_id)
            if player_id != room.host_player_id:
                raise PermissionError("Seul l'hôte peut démarrer la partie.")
            if room.status != "lobby":
                raise ValueError("Cette partie a déjà démarré.")
            if len(room.players) < 2:
                raise ValueError("Il faut au moins deux joueurs pour démarrer.")
            room.status = "playing"
            return room

    def set_room_cell(
        self, room_id: str, player_id: str, row: int, column: int, value: int
    ) -> tuple[SudokuRoom, int]:
        with self._lock:
            room = self.get_room(room_id, player_id)
            if room.status != "playing":
                raise ValueError("La manche n'est pas en cours.")
            _valid_cell(row, column, value)
            if room.puzzle[row][column]:
                raise ValueError("Cette case fait partie de la grille de départ.")
            player = room.players[player_id]
            if player.rank is not None:
                raise ValueError("Vous avez déjà terminé cette grille.")
            player.board[row][column] = value
            awarded = 0
            if _is_solved(player.board, room.solution):
                solved_count = sum(item.rank is not None for item in room.players.values())
                player.rank = solved_count + 1
                player.solved_at = self._clock()
                player.points = SUDOKU_RANKING_POINTS[player.rank - 1] if player.rank <= 3 else 0
                awarded = player.points
                if room.first_solved_at is None:
                    room.first_solved_at = player.solved_at
                    room.deadline_at = player.solved_at + SUDOKU_AFTER_FIRST_SECONDS
                if player.rank >= 3:
                    room.status = "finished"
                    room.finish_reason = "podium"
                elif all(item.rank is not None for item in room.players.values()):
                    room.status = "finished"
                    room.finish_reason = "all_solved"
            return room, awarded


sudoku_manager = SudokuManager()
