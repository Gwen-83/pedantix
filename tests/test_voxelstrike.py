import math
import time
import unittest

from fastapi.testclient import TestClient

from app.main import app
from app.voxelstrike import Player, Room, VoxelStrikeManager, can_move


class FakeWebSocket:
    async def send_json(self, payload):
        return None


class VoxelStrikeTests(unittest.IsolatedAsyncioTestCase):
    async def test_server_caps_concurrent_players_and_splits_rooms(self):
        manager = VoxelStrikeManager()
        connections = []
        for index in range(40):
            connection = await manager.join(FakeWebSocket(), f"Player{index}")
            self.assertIsNotNone(connection)
            connections.append(connection)

        self.assertIsNone(await manager.join(FakeWebSocket(), "Extra"))
        self.assertEqual(manager.status(), {"players": 40, "capacity": 40, "rooms": 4})
        for room, player in connections:
            await manager.leave(room, player.player_id)

    async def test_movement_is_server_limited_and_cannot_cross_walls(self):
        manager = VoxelStrikeManager()
        room = Room("test")
        player = Player(
            player_id="p1",
            username="Player",
            team="blue",
            websocket=FakeWebSocket(),
            x=6.5,
            z=1.5,
            yaw=math.pi / 2,
        )
        room.players[player.player_id] = player
        player.last_input = time.monotonic() - 0.1

        await manager.handle_input(
            room,
            player.player_id,
            {"yaw": math.pi / 2, "keys": {"forward": True}},
        )

        self.assertEqual(player.x, 6.5)
        self.assertTrue(can_move(player.x, player.z))

    async def test_shots_damage_nearest_enemy_in_line_of_sight(self):
        manager = VoxelStrikeManager()
        room = Room("test")
        shooter = Player(
            player_id="blue",
            username="Blue",
            team="blue",
            websocket=FakeWebSocket(),
            x=1.5,
            z=5.5,
            yaw=math.pi / 2,
        )
        target = Player(
            player_id="red",
            username="Red",
            team="red",
            websocket=FakeWebSocket(),
            x=4.0,
            z=5.5,
        )
        behind = Player(
            player_id="red-behind",
            username="Red2",
            team="red",
            websocket=FakeWebSocket(),
            x=6.0,
            z=5.5,
        )
        room.players = {shooter.player_id: shooter, target.player_id: target, behind.player_id: behind}

        manager._fire(room, shooter, time.monotonic())

        self.assertEqual(target.hp, 66)
        self.assertEqual(behind.hp, 100)
        self.assertTrue(shooter.hit_marker_until > 0)

    async def test_walls_block_shots(self):
        manager = VoxelStrikeManager()
        room = Room("test")
        shooter = Player(
            player_id="blue",
            username="Blue",
            team="blue",
            websocket=FakeWebSocket(),
            x=5.5,
            z=1.5,
            yaw=math.pi / 2,
        )
        target = Player(
            player_id="red",
            username="Red",
            team="red",
            websocket=FakeWebSocket(),
            x=8.5,
            z=1.5,
        )
        room.players = {shooter.player_id: shooter, target.player_id: target}

        manager._fire(room, shooter, time.monotonic())

        self.assertEqual(target.hp, 100)


class VoxelStrikeRouteTests(unittest.TestCase):
    def test_game_page_and_live_status_are_served(self):
        with TestClient(app) as client:
            page = client.get("/games/voxelstrike/")
            status = client.get("/api/voxelstrike/status")

        self.assertEqual(page.status_code, 200)
        self.assertIn("BLOCKFIRE", page.text)
        self.assertNotIn("location.replace", page.text)
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["capacity"], 40)

    def test_websocket_sends_welcome_and_live_state(self):
        with TestClient(app) as client:
            with client.websocket_connect("/ws/voxelstrike?name=Alice") as websocket:
                welcome = websocket.receive_json()
                self.assertEqual(welcome["type"], "welcome")
                self.assertEqual(welcome["arena"][0], "################")
                state = websocket.receive_json()
                self.assertEqual(state["type"], "state")
                self.assertEqual(state["players"][0]["name"], "Alice")


if __name__ == "__main__":
    unittest.main()
