import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import main


class RoomRestartRouteTests(unittest.TestCase):
    def test_motus_restart_route_promotes_spectators(self):
        room = main.motus_manager.create_room("motus-host", "Hôte")
        room.status = "playing"
        main.motus_manager.join_room(room.room_id, "motus-viewer", "Observateur")
        room.status = "finished"

        with patch("app.main.record_multigame_session_start") as record:
            with TestClient(main.app) as client:
                response = client.post(
                    "/api/motus/room/restart",
                    json={
                        "room_id": room.room_id,
                        "player_id": "motus-host",
                        "player_name": "Hôte",
                    },
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["match_number"], 2)
        self.assertFalse(response.json()["players"][1]["is_spectator"])
        record.assert_called_once_with(
            f"motus:{room.room_id}:2",
            "motus",
            "multiplayer",
            "Motus",
            room.difficulty,
        )

    def test_cemantix_restart_route_promotes_spectators(self):
        room = main.cemantix_manager.create_room("cemantix-host", "Hôte")
        room.status = "playing"
        main.cemantix_manager.join_room(
            room.room_id, "cemantix-viewer", "Observateur"
        )
        room.status = "finished"

        with patch("app.main.record_multigame_session_start") as record:
            with TestClient(main.app) as client:
                response = client.post(
                    "/api/cemantix/room/restart",
                    json={
                        "room_id": room.room_id,
                        "player_id": "cemantix-host",
                        "player_name": "Hôte",
                    },
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["match_number"], 2)
        self.assertFalse(response.json()["player"]["is_spectator"])
        record.assert_called_once_with(
            f"cemantix:{room.room_id}:2",
            "cemantix",
            "multiplayer",
            "Cémantix",
            room.difficulty,
        )

    def test_battleship_restart_route_promotes_spectators_into_lobby(self):
        room = main.battleship_manager.create_room("naval-host", "Hôte")
        room.status = "playing"
        main.battleship_manager.join_room(
            room.room_id, "naval-viewer", "Observateur"
        )
        room.status = "finished"

        with TestClient(main.app) as client:
            response = client.post(
                "/api/battleship/room/restart",
                json={
                    "room_id": room.room_id,
                    "player_id": "naval-host",
                    "player_name": "Hôte",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "lobby")
        self.assertEqual(response.json()["match_number"], 2)
        self.assertFalse(response.json()["is_spectator"])
        self.assertFalse(response.json()["players"][1]["is_spectator"])

    def test_sudoku_restart_route_promotes_spectators_into_lobby(self):
        room = main.sudoku_manager.create_room("sudoku-host", "Hôte", "facile")
        room.status = "playing"
        main.sudoku_manager.join_room(
            room.room_id, "sudoku-viewer", "Observateur"
        )
        room.status = "finished"

        with TestClient(main.app) as client:
            response = client.post(
                "/api/sudoku/room/restart",
                json={
                    "room_id": room.room_id,
                    "player_id": "sudoku-host",
                    "player_name": "Hôte",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "lobby")
        self.assertEqual(response.json()["match_number"], 2)
        self.assertFalse(response.json()["player"]["is_spectator"])
        self.assertFalse(response.json()["players"][1]["is_spectator"])


if __name__ == "__main__":
    unittest.main()
