import random
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set

BOARD_SIZE = 10
SHIP_LENGTHS = {
    "carrier": 5,
    "battleship": 4,
    "cruiser": 3,
    "submarine": 3,
    "destroyer": 2,
}
SHIP_NAMES = {
    "carrier": "Porte-avions",
    "battleship": "Cuirassé",
    "cruiser": "Croiseur",
    "submarine": "Sous-marin",
    "destroyer": "Torpilleur",
    "frigate": "Frégate",
}
ROWS = "ABCDEFGHIJ"
BATTLESHIP_DIFFICULTIES = {
    "facile": {
        "carrier": 4,
        "battleship": 3,
        "cruiser": 2,
        "submarine": 2,
        "destroyer": 1,
    },
    "moyen": SHIP_LENGTHS,
    "difficile": {**SHIP_LENGTHS, "frigate": 2},
}


def parse_coordinate(value: str) -> str:
    coordinate = value.strip().upper()
    if len(coordinate) < 2 or coordinate[0] not in ROWS:
        raise ValueError("Coordonnée invalide. Utilisez une case de A1 à J10.")
    try:
        column = int(coordinate[1:])
    except ValueError as exc:
        raise ValueError("Coordonnée invalide. Utilisez une case de A1 à J10.") from exc
    if not 1 <= column <= BOARD_SIZE:
        raise ValueError("Coordonnée invalide. Utilisez une case de A1 à J10.")
    return f"{coordinate[0]}{column}"


def _coordinate_parts(coordinate: str) -> tuple[int, int]:
    return ROWS.index(coordinate[0]), int(coordinate[1:]) - 1


def _adjacent_coordinates(coordinate: str) -> Set[str]:
    row, column = _coordinate_parts(coordinate)
    adjacent = set()
    for row_offset in (-1, 0, 1):
        for column_offset in (-1, 0, 1):
            next_row, next_column = row + row_offset, column + column_offset
            if 0 <= next_row < BOARD_SIZE and 0 <= next_column < BOARD_SIZE:
                adjacent.add(f"{ROWS[next_row]}{next_column + 1}")
    return adjacent


def _generate_fleet(
    ship_lengths: Dict[str, int] = SHIP_LENGTHS,
) -> Dict[str, List[str]]:
    occupied: Set[str] = set()
    fleet: Dict[str, List[str]] = {}
    for ship_id, length in ship_lengths.items():
        while True:
            vertical = bool(random.getrandbits(1))
            row = random.randrange(BOARD_SIZE)
            column = random.randrange(BOARD_SIZE)
            end_row = row + (length - 1 if vertical else 0)
            end_column = column + (0 if vertical else length - 1)
            if end_row >= BOARD_SIZE or end_column >= BOARD_SIZE:
                continue
            cells = [
                f"{ROWS[row + (offset if vertical else 0)]}{column + (offset if not vertical else 0) + 1}"
                for offset in range(length)
            ]
            neighborhood = set().union(*(_adjacent_coordinates(cell) for cell in cells))
            if neighborhood & occupied:
                continue
            fleet[ship_id] = cells
            occupied.update(cells)
            break
    return fleet


@dataclass
class BattleshipPlayer:
    player_id: str
    name: str
    fleet: Dict[str, List[str]] = field(default_factory=_generate_fleet)
    ready: bool = False
    incoming_shots: Dict[str, str] = field(default_factory=dict)
    attacks: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def ship_cells(self) -> Dict[str, str]:
        return {
            coordinate: ship_id
            for ship_id, cells in self.fleet.items()
            for coordinate in cells
        }

    @property
    def sunk_ships(self) -> Set[str]:
        hits = set(self.incoming_shots)
        return {
            ship_id
            for ship_id, cells in self.fleet.items()
            if set(cells) <= hits
        }

    @property
    def eliminated(self) -> bool:
        return len(self.sunk_ships) == len(self.fleet)

    def public_state(self) -> Dict[str, Any]:
        return {
            "player_id": self.player_id,
            "name": self.name,
            "ready": self.ready,
            "eliminated": self.eliminated,
            "ships_remaining": len(self.fleet) - len(self.sunk_ships),
            "ships_sunk": len(self.sunk_ships),
        }


@dataclass
class BattleshipRoom:
    room_id: str
    host_player_id: str
    difficulty: str = "moyen"
    ship_lengths: Dict[str, int] = field(default_factory=lambda: dict(SHIP_LENGTHS))
    players: Dict[str, BattleshipPlayer] = field(default_factory=dict)
    status: str = "lobby"
    current_player_id: Optional[str] = None
    turn_number: int = 0
    winner_player_id: Optional[str] = None

    def _alive_ids(self) -> List[str]:
        return [player_id for player_id, player in self.players.items() if not player.eliminated]

    def next_alive(self, after_player_id: str) -> Optional[str]:
        player_ids = list(self.players)
        if after_player_id not in self.players or not player_ids:
            return None
        start = player_ids.index(after_player_id)
        for offset in range(1, len(player_ids) + 1):
            candidate = player_ids[(start + offset) % len(player_ids)]
            if not self.players[candidate].eliminated:
                return candidate
        return None

    def target_for(self, player_id: str) -> Optional[str]:
        if player_id not in self.players or self.players[player_id].eliminated:
            return None
        return self.next_alive(player_id)

    def to_dict(self, player_id: str) -> Dict[str, Any]:
        player = self.players[player_id]
        target_id = self.target_for(player_id) if self.status == "playing" else None
        own_fleet = [
            {
                "ship_id": ship_id,
                "name": SHIP_NAMES[ship_id],
                "length": self.ship_lengths[ship_id],
                "cells": cells,
                "sunk": ship_id in player.sunk_ships,
            }
            for ship_id, cells in player.fleet.items()
        ]
        return {
            "room_id": self.room_id,
            "status": self.status,
            "difficulty": self.difficulty,
            "ship_lengths": self.ship_lengths,
            "host_player_id": self.host_player_id,
            "player_id": player_id,
            "players": [item.public_state() for item in self.players.values()],
            "can_start": (
                self.status == "lobby"
                and len(self.players) >= 2
                and all(item.ready for item in self.players.values())
            ),
            "current_player_id": self.current_player_id,
            "target_player_id": target_id,
            "turn_number": self.turn_number,
            "winner_player_id": self.winner_player_id,
            "own_fleet": own_fleet,
            "incoming_shots": [
                {
                    "coordinate": coordinate,
                    "hit": coordinate in player.ship_cells,
                    "shooter_id": shooter_id,
                    "sunk_ship": (
                        player.ship_cells[coordinate]
                        if coordinate in player.ship_cells
                        and player.ship_cells[coordinate] in player.sunk_ships
                        else None
                    ),
                }
                for coordinate, shooter_id in player.incoming_shots.items()
            ],
            "attacks": player.attacks,
            "target_shots": [
                {
                    "coordinate": attack["coordinate"],
                    "hit": attack["hit"],
                    "sunk_ship": attack["sunk_ship"],
                    "eliminated": attack["eliminated"],
                }
                for attack in player.attacks
                if attack["target_id"] == target_id
            ],
        }


class BattleshipManager:
    def __init__(self):
        self.rooms: Dict[str, BattleshipRoom] = {}
        self._lock = threading.RLock()

    @staticmethod
    def validate_fleet(
        fleet: Dict[str, Iterable[str]],
        ship_lengths: Dict[str, int] = SHIP_LENGTHS,
    ) -> Dict[str, List[str]]:
        if set(fleet) != set(ship_lengths):
            raise ValueError("La flotte doit contenir exactement les navires de cette difficulté.")
        normalized: Dict[str, List[str]] = {}
        occupied: Dict[str, str] = {}
        for ship_id, length in ship_lengths.items():
            cells = [parse_coordinate(value) for value in fleet[ship_id]]
            if len(cells) != length or len(set(cells)) != length:
                raise ValueError(f"{SHIP_NAMES[ship_id]} : placez exactement {length} cases.")
            parts = [_coordinate_parts(cell) for cell in cells]
            rows = {row for row, _ in parts}
            columns = {column for _, column in parts}
            straight = len(rows) == 1 or len(columns) == 1
            varying = sorted(columns if len(rows) == 1 else rows)
            if not straight or varying != list(range(varying[0], varying[0] + length)):
                raise ValueError(f"{SHIP_NAMES[ship_id]} doit être placé en ligne droite.")
            if occupied.keys() & set(cells):
                raise ValueError("Deux navires ne peuvent pas occuper la même case.")
            normalized[ship_id] = cells
            occupied.update({cell: ship_id for cell in cells})

        for cell, ship_id in occupied.items():
            adjacent = _adjacent_coordinates(cell) - {cell}
            if any(occupied.get(neighbor) not in (None, ship_id) for neighbor in adjacent):
                raise ValueError("Les navires ne peuvent pas se toucher, même en diagonale.")
        return normalized

    @staticmethod
    def _validate_difficulty(difficulty: str) -> str:
        if difficulty not in BATTLESHIP_DIFFICULTIES:
            raise ValueError("Difficulté invalide. Choisissez facile, moyen ou difficile.")
        return difficulty

    def create_room(
        self, player_id: str, player_name: str, difficulty: str = "moyen"
    ) -> BattleshipRoom:
        with self._lock:
            difficulty = self._validate_difficulty(difficulty)
            ship_lengths = dict(BATTLESHIP_DIFFICULTIES[difficulty])
            room_id = uuid.uuid4().hex[:6].upper()
            while room_id in self.rooms:
                room_id = uuid.uuid4().hex[:6].upper()
            room = BattleshipRoom(
                room_id=room_id,
                host_player_id=player_id,
                difficulty=difficulty,
                ship_lengths=ship_lengths,
            )
            room.players[player_id] = BattleshipPlayer(
                player_id, player_name, fleet=_generate_fleet(ship_lengths)
            )
            self.rooms[room_id] = room
            return room

    def join_room(self, room_id: str, player_id: str, player_name: str) -> BattleshipRoom:
        with self._lock:
            room = self.rooms.get(room_id.upper())
            if not room:
                raise KeyError("Salon introuvable ou expiré.")
            if player_id in room.players:
                room.players[player_id].name = player_name
                return room
            if room.status != "lobby":
                raise ValueError("La partie a commencé. Seuls les joueurs déjà inscrits peuvent revenir.")
            room.players[player_id] = BattleshipPlayer(
                player_id,
                player_name,
                fleet=_generate_fleet(room.ship_lengths),
            )
            return room

    def get_room(self, room_id: str, player_id: str) -> BattleshipRoom:
        with self._lock:
            room = self.rooms.get(room_id.upper())
            if not room or player_id not in room.players:
                raise KeyError("Salon ou joueur introuvable.")
            return room

    def list_rooms(self, player_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                {
                    "room_id": room.room_id,
                    "status": room.status,
                    "player_count": len(room.players),
                    "host_name": room.players[room.host_player_id].name,
                    "difficulty": room.difficulty,
                    "is_member": player_id in room.players if player_id else False,
                }
                for room in self.rooms.values()
                if room.status != "finished"
            ]

    def set_fleet(
        self, room_id: str, player_id: str, fleet: Dict[str, Iterable[str]]
    ) -> BattleshipRoom:
        with self._lock:
            room = self.get_room(room_id, player_id)
            if room.status != "lobby":
                raise ValueError("La flotte ne peut plus être modifiée après le départ.")
            room.players[player_id].fleet = self.validate_fleet(
                fleet, room.ship_lengths
            )
            room.players[player_id].ready = False
            return room

    def randomize_fleet(self, room_id: str, player_id: str) -> BattleshipRoom:
        with self._lock:
            room = self.get_room(room_id, player_id)
            if room.status != "lobby":
                raise ValueError("La flotte ne peut plus être modifiée après le départ.")
            room.players[player_id].fleet = _generate_fleet(room.ship_lengths)
            room.players[player_id].ready = False
            return room

    def set_ready(self, room_id: str, player_id: str, ready: bool) -> BattleshipRoom:
        with self._lock:
            room = self.get_room(room_id, player_id)
            if room.status != "lobby":
                raise ValueError("La préparation est terminée, la partie a commencé.")
            room.players[player_id].ready = ready
            return room

    def start_room(self, room_id: str, player_id: str) -> BattleshipRoom:
        with self._lock:
            room = self.get_room(room_id, player_id)
            if player_id != room.host_player_id:
                raise PermissionError("Seul l'hôte peut démarrer la partie.")
            if room.status != "lobby":
                raise ValueError("Cette partie a déjà démarré.")
            if len(room.players) < 2:
                raise ValueError("Il faut au moins deux joueurs pour démarrer.")
            if not all(player.ready for player in room.players.values()):
                raise ValueError("Tous les joueurs doivent confirmer leur flotte avant le départ.")
            room.status = "playing"
            room.current_player_id = next(iter(room.players))
            room.turn_number = 1
            return room

    def fire(
        self, room_id: str, player_id: str, coordinate: str
    ) -> tuple[BattleshipRoom, Dict[str, Any]]:
        with self._lock:
            room = self.get_room(room_id, player_id)
            if room.status != "playing":
                raise ValueError("La partie n'est pas en cours.")
            if room.current_player_id != player_id:
                raise ValueError("Ce n'est pas votre tour.")
            target_id = room.target_for(player_id)
            if target_id is None:
                raise ValueError("Aucun adversaire ne peut être ciblé.")
            shot = parse_coordinate(coordinate)
            if shot in room.players[target_id].incoming_shots:
                raise ValueError("Cette case a déjà été visée sur ce plateau.")

            target = room.players[target_id]
            target.incoming_shots[shot] = player_id
            ship_id = target.ship_cells.get(shot)
            hit = ship_id is not None
            sunk_ship = ship_id if ship_id in target.sunk_ships else None
            eliminated = target.eliminated
            attack = {
                "turn": room.turn_number,
                "target_id": target_id,
                "coordinate": shot,
                "hit": hit,
                "sunk_ship": sunk_ship,
                "eliminated": eliminated,
            }
            room.players[player_id].attacks.append(attack)

            alive = room._alive_ids()
            if len(alive) <= 1:
                room.status = "finished"
                room.winner_player_id = alive[0] if alive else None
                room.current_player_id = None
            elif hit:
                room.current_player_id = player_id
                room.turn_number += 1
            else:
                room.current_player_id = room.next_alive(player_id)
                room.turn_number += 1

            return room, {
                "target_id": target_id,
                "coordinate": shot,
                "hit": hit,
                "sunk_ship": sunk_ship,
                "eliminated": eliminated,
                "winner_player_id": room.winner_player_id,
                "next_player_id": room.current_player_id,
            }


battleship_manager = BattleshipManager()
