import math
import time
import unittest

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import app
from app.database import generate_user_token
from app.voxelstrike import CITY_SPAWNS, Player, Room, VoxelStrikeManager, can_move


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
        room.status = "playing"

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

    async def test_lobby_requires_two_players_and_host_starts_match(self):
        manager = VoxelStrikeManager()
        first = await manager.join(FakeWebSocket(), "Host")
        self.assertIsNotNone(first)
        room, host = first
        self.assertEqual(room.status, "lobby")
        self.assertFalse(await manager.start_match(room, host.player_id))

        second = await manager.join(FakeWebSocket(), "Guest")
        self.assertIsNotNone(second)
        self.assertIs(room, second[0])
        guest = second[1]
        self.assertFalse(await manager.start_match(room, guest.player_id))
        self.assertTrue(await manager.start_match(room, host.player_id))
        self.assertEqual(room.status, "playing")

        late_joiner = await manager.join(FakeWebSocket(), "Late")
        self.assertIsNotNone(late_joiner)
        self.assertIs(late_joiner[0], room)
        self.assertTrue(late_joiner[1].spectator)
        self.assertFalse(late_joiner[1].alive)
        await manager.leave(room, late_joiner[1].player_id)
        await manager.leave(room, guest.player_id)
        await manager.leave(room, host.player_id)

    async def test_join_prefers_playing_room_and_admits_as_spectator(self):
        manager = VoxelStrikeManager()
        lobby = Room("lobby", status="lobby")
        playing = Room("playing", status="playing")
        host = Player("host", "Host", "blue", FakeWebSocket(), 1.5, 1.5)
        lobby.players[host.player_id] = host
        lobby.host_id = host.player_id
        lobby_observer = Player(
            "lobby-observer", "Observer", "red", FakeWebSocket(), 2.5, 3.5,
            alive=False, spectator=True,
        )
        lobby.players[lobby_observer.player_id] = lobby_observer
        blue = Player("blue", "Blue", "blue", FakeWebSocket(), 1.5, 1.5)
        red = Player("red", "Red", "red", FakeWebSocket(), 25.5, 25.5)
        playing.players = {blue.player_id: blue, red.player_id: red}
        manager.rooms = {lobby.room_id: lobby, playing.room_id: playing}

        joined = await manager.join(FakeWebSocket(), "Observer")

        self.assertIsNotNone(joined)
        room, observer = joined
        self.assertIs(room, playing)
        self.assertEqual(room.status, "playing")
        self.assertTrue(observer.spectator)
        self.assertFalse(observer.alive)
        self.assertEqual(observer.snapshot(time.monotonic(), observer.player_id)["spectator"], True)
        self.assertFalse(await manager.start_match(lobby, host.player_id))
        await manager.leave(room, observer.player_id)
        await manager.leave(room, blue.player_id)
        await manager.leave(room, red.player_id)

    async def test_spectator_input_cannot_move_or_fire(self):
        manager = VoxelStrikeManager()
        room = Room("playing", status="playing")
        spectator = Player(
            "observer", "Observer", "blue", FakeWebSocket(), 1.5, 5.5,
            yaw=0, alive=False, spectator=True,
            last_input=time.monotonic() - 1,
        )
        target = Player("target", "Target", "red", FakeWebSocket(), 1.5, 3.0)
        room.players = {spectator.player_id: spectator, target.player_id: target}

        await manager.handle_input(
            room,
            spectator.player_id,
            {"yaw": math.pi / 2, "keys": {"forward": True, "fire": True}},
        )

        self.assertEqual((spectator.x, spectator.z, spectator.yaw), (1.5, 5.5, 0))
        self.assertEqual(target.hp, 100)
        self.assertEqual(room.scores, {"blue": 0, "red": 0})

    async def test_spectators_are_promoted_when_winner_reset_starts_next_match(self):
        manager = VoxelStrikeManager()
        room = Room("playing", status="playing", scores={"blue": 25, "red": 8}, winner="blue")
        room.players = {
            "blue-1": Player("blue-1", "Blue 1", "blue", FakeWebSocket(), 1.5, 1.5, kills=25),
            "blue-2": Player("blue-2", "Blue 2", "blue", FakeWebSocket(), 9.5, 1.5),
            "red": Player("red", "Red", "red", FakeWebSocket(), 25.5, 25.5),
            "observer": Player(
                "observer", "Observer", "blue", FakeWebSocket(), 17.5, 17.5,
                hp=0, alive=False, spectator=True,
            ),
        }

        manager._reset_match(room)

        observer = room.players["observer"]
        self.assertFalse(observer.spectator)
        self.assertTrue(observer.alive)
        self.assertEqual(observer.team, "red")
        self.assertEqual(observer.hp, 100)
        self.assertEqual(room.scores, {"blue": 0, "red": 0})
        self.assertIsNone(room.winner)
        self.assertEqual(room.players["blue-1"].kills, 0)

    async def test_rooms_get_random_city_maps_with_open_team_spawns(self):
        manager = VoxelStrikeManager()
        first = await manager.join(FakeWebSocket(), "First")
        second_manager = VoxelStrikeManager()
        second = await second_manager.join(FakeWebSocket(), "Second")
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)

        first_arena = first[0].arena
        second_arena = second[0].arena
        self.assertEqual(len(first_arena), 32)
        self.assertTrue(all(len(row) == 32 for row in first_arena))
        self.assertNotEqual(first_arena, second_arena)
        for team_spawns in CITY_SPAWNS.values():
            for x, z in team_spawns:
                self.assertTrue(can_move(x, z, first_arena))

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
        self.assertIn("pedantix_auth_token", page.text)
        self.assertIn("<kbd>Z</kbd>", page.text)
        self.assertNotIn("player-name-input", page.text)
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["capacity"], 40)

    def test_websocket_sends_welcome_and_live_state(self):
        with TestClient(app) as client:
            token = generate_user_token("Alice")
            with client.websocket_connect(f"/ws/voxelstrike?name=Alice&token={token}") as websocket:
                welcome = websocket.receive_json()
                self.assertEqual(welcome["type"], "welcome")
                self.assertEqual(len(welcome["arena"][0]), 32)
                self.assertEqual(len(welcome["arena"]), 32)
                self.assertEqual(welcome["status"], "lobby")
                state = websocket.receive_json()
                self.assertEqual(state["type"], "state")
                self.assertEqual(state["players"][0]["name"], "Alice")

    def test_websocket_rejects_missing_authentication(self):
        with TestClient(app) as client:
            with client.websocket_connect("/ws/voxelstrike?name=Alice") as websocket:
                with self.assertRaises(WebSocketDisconnect):
                    websocket.receive_json()


if __name__ == "__main__":
    unittest.main()
