import asyncio
import json
import math
import random
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()

MAX_PLAYERS = 40
ROOM_SIZE = 10
TICK_SECONDS = 0.1
PLAYER_SPEED = 5.2
PLAYER_RADIUS = 0.22
WEAPON_RANGE = 18.0
TEAM_SCORE_LIMIT = 25

ARENA = (
    "################",
    "#......#.......#",
    "#.##...#..##...#",
    "#......#.......#",
    "###.####.###.###",
    "#..............#",
    "#.##..##..##...#",
    "#......##......#",
    "#......##......#",
    "#...##..##..##.#",
    "#..............#",
    "###.###.####.###",
    "#.......#......#",
    "#...##..#...##.#",
    "#..............#",
    "################",
)

SPAWNS = {
    "blue": ((1.5, 1.5), (2.5, 3.5), (5.5, 1.5), (1.5, 5.5)),
    "red": ((14.5, 14.5), (13.5, 12.5), (10.5, 14.5), (14.5, 10.5)),
}


def is_wall(x: float, z: float) -> bool:
    column, row = math.floor(x), math.floor(z)
    return (
        row < 0
        or row >= len(ARENA)
        or column < 0
        or column >= len(ARENA[row])
        or ARENA[row][column] == "#"
    )


def can_move(x: float, z: float) -> bool:
    for offset_x in (-PLAYER_RADIUS, PLAYER_RADIUS):
        for offset_z in (-PLAYER_RADIUS, PLAYER_RADIUS):
            if is_wall(x + offset_x, z + offset_z):
                return False
    return True


def _normalise_angle(angle: float) -> float:
    return (angle + math.pi) % (2 * math.pi) - math.pi


@dataclass
class Player:
    player_id: str
    username: str
    team: str
    websocket: WebSocket
    x: float
    z: float
    yaw: float = 0.0
    hp: int = 100
    kills: int = 0
    deaths: int = 0
    alive: bool = True
    last_input: float = field(default_factory=time.monotonic)
    last_shot: float = 0.0
    respawn_at: float = 0.0
    hit_marker_until: float = 0.0

    def snapshot(self, now: float, local_player_id: str) -> dict[str, Any]:
        return {
            "id": self.player_id,
            "name": self.username,
            "team": self.team,
            "x": round(self.x, 2),
            "z": round(self.z, 2),
            "yaw": round(self.yaw, 3),
            "hp": self.hp,
            "kills": self.kills,
            "deaths": self.deaths,
            "alive": self.alive,
            "hit": self.player_id == local_player_id and now < self.hit_marker_until,
        }


@dataclass
class Room:
    room_id: str
    players: dict[str, Player] = field(default_factory=dict)
    scores: dict[str, int] = field(default_factory=lambda: {"blue": 0, "red": 0})
    winner: str | None = None
    reset_at: float = 0.0
    task: asyncio.Task[None] | None = None

    def spawn(self, team: str) -> tuple[float, float]:
        for x, z in SPAWNS[team]:
            if all(math.hypot(p.x - x, p.z - z) > 0.65 for p in self.players.values()):
                return x, z
        return random.choice(SPAWNS[team])


class VoxelStrikeManager:
    def __init__(self) -> None:
        self.rooms: dict[str, Room] = {}
        self.lock = asyncio.Lock()

    @property
    def player_count(self) -> int:
        return sum(len(room.players) for room in self.rooms.values())

    async def join(self, websocket: WebSocket, username: str) -> tuple[Room, Player] | None:
        async with self.lock:
            if self.player_count >= MAX_PLAYERS:
                return None
            room = next(
                (candidate for candidate in self.rooms.values() if len(candidate.players) < ROOM_SIZE),
                None,
            )
            if room is None:
                room = Room(room_id=uuid.uuid4().hex[:6].upper())
                self.rooms[room.room_id] = room
            team_counts = {
                team: sum(player.team == team for player in room.players.values())
                for team in ("blue", "red")
            }
            team = "blue" if team_counts["blue"] <= team_counts["red"] else "red"
            player_id = uuid.uuid4().hex
            x, z = room.spawn(team)
            player = Player(
                player_id=player_id,
                username=username,
                team=team,
                websocket=websocket,
                x=x,
                z=z,
            )
            room.players[player_id] = player
            if room.task is None or room.task.done():
                room.task = asyncio.create_task(self._broadcast_loop(room))
            return room, player

    async def leave(self, room: Room, player_id: str) -> None:
        async with self.lock:
            room.players.pop(player_id, None)
            if not room.players:
                self.rooms.pop(room.room_id, None)
                if room.task and not room.task.done():
                    room.task.cancel()

    async def handle_input(self, room: Room, player_id: str, message: dict[str, Any]) -> None:
        async with self.lock:
            player = room.players.get(player_id)
            if player is None:
                return
            now = time.monotonic()
            if now - player.last_input < 0.025:
                return
            elapsed = min(max(now - player.last_input, 0.0), 0.1)
            player.last_input = now

            yaw = message.get("yaw")
            if isinstance(yaw, (float, int)) and math.isfinite(yaw):
                player.yaw = _normalise_angle(float(yaw))

            if player.alive:
                keys = message.get("keys", {})
                if not isinstance(keys, dict):
                    keys = {}
                forward = int(bool(keys.get("forward"))) - int(bool(keys.get("back")))
                strafe = int(bool(keys.get("right"))) - int(bool(keys.get("left")))
                length = math.hypot(forward, strafe)
                if length:
                    forward /= length
                    strafe /= length
                    dx = (
                        math.sin(player.yaw) * forward + math.cos(player.yaw) * strafe
                    ) * PLAYER_SPEED * elapsed
                    dz = (
                        math.cos(player.yaw) * forward - math.sin(player.yaw) * strafe
                    ) * PLAYER_SPEED * elapsed
                    if can_move(player.x + dx, player.z):
                        player.x += dx
                    if can_move(player.x, player.z + dz):
                        player.z += dz

                if keys.get("fire") and now - player.last_shot >= 0.22:
                    player.last_shot = now
                    self._fire(room, player, now)

    def _fire(self, room: Room, shooter: Player, now: float) -> None:
        max_distance = WEAPON_RANGE
        steps = max(1, math.ceil(max_distance / 0.08))
        for step in range(1, steps + 1):
            distance = step * 0.08
            if is_wall(
                shooter.x + math.sin(shooter.yaw) * distance,
                shooter.z + math.cos(shooter.yaw) * distance,
            ):
                max_distance = distance
                break

        target: Player | None = None
        target_distance = max_distance
        direction_x, direction_z = math.sin(shooter.yaw), math.cos(shooter.yaw)
        for candidate in room.players.values():
            if candidate.team == shooter.team or not candidate.alive:
                continue
            relative_x, relative_z = candidate.x - shooter.x, candidate.z - shooter.z
            along = relative_x * direction_x + relative_z * direction_z
            across = abs(relative_x * direction_z - relative_z * direction_x)
            if 0 < along < target_distance and across < 0.34:
                target = candidate
                target_distance = along

        if target is None:
            return
        target.hp = max(0, target.hp - 34)
        shooter.hit_marker_until = now + 0.16
        if target.hp == 0:
            target.alive = False
            target.deaths += 1
            target.respawn_at = now + 2.2
            shooter.kills += 1
            room.scores[shooter.team] += 1
            if room.scores[shooter.team] >= TEAM_SCORE_LIMIT and room.winner is None:
                room.winner = shooter.team
                room.reset_at = now + 5.0

    async def _broadcast_loop(self, room: Room) -> None:
        try:
            while True:
                await asyncio.sleep(TICK_SECONDS)
                now = time.monotonic()
                async with self.lock:
                    if not room.players:
                        return
                    if room.winner and now >= room.reset_at:
                        room.scores = {"blue": 0, "red": 0}
                        room.winner = None
                        for player in room.players.values():
                            player.kills = 0
                            player.deaths = 0
                            player.hp = 100
                            player.alive = True
                            player.x, player.z = room.spawn(player.team)
                    for player in room.players.values():
                        if not player.alive and now >= player.respawn_at:
                            player.x, player.z = room.spawn(player.team)
                            player.hp = 100
                            player.alive = True
                    players = tuple(room.players.values())
                    scores = dict(room.scores)
                    winner = room.winner

                dead: list[str] = []
                for recipient in players:
                    payload = {
                        "type": "state",
                        "players": [player.snapshot(now, recipient.player_id) for player in players],
                        "scores": scores,
                        "winner": winner,
                    }
                    try:
                        await asyncio.wait_for(recipient.websocket.send_json(payload), timeout=1.0)
                    except (WebSocketDisconnect, RuntimeError, asyncio.TimeoutError):
                        dead.append(recipient.player_id)
                for player_id in dead:
                    await self.leave(room, player_id)
        except asyncio.CancelledError:
            return

    def status(self) -> dict[str, int]:
        return {
            "players": self.player_count,
            "capacity": MAX_PLAYERS,
            "rooms": len(self.rooms),
        }


manager = VoxelStrikeManager()


@router.get("/games/voxelstrike/")
async def voxelstrike_page():
    from fastapi.responses import FileResponse
    from pathlib import Path

    page = Path(__file__).resolve().parent.parent / "static" / "games" / "voxelstrike" / "index.html"
    return FileResponse(page)


@router.get("/api/voxelstrike/status")
async def voxelstrike_status() -> dict[str, int]:
    return manager.status()


@router.websocket("/ws/voxelstrike")
async def voxelstrike_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    raw_name = websocket.query_params.get("name", "Joueur")
    username = re.sub(r"[\x00-\x1f\x7f<>]", "", raw_name).strip()[:24] or "Joueur"
    joined = await manager.join(websocket, username)
    if joined is None:
        await websocket.send_json(
            {"type": "full", "message": "Le serveur est complet. Réessayez dans quelques instants."}
        )
        await websocket.close(code=1013)
        return
    room, player = joined
    try:
        await websocket.send_json(
            {
                "type": "welcome",
                "id": player.player_id,
                "room": room.room_id,
                "team": player.team,
                "arena": ARENA,
            }
        )
        while True:
            raw_message = await websocket.receive_text()
            if len(raw_message) > 2048:
                await websocket.close(code=1009)
                break
            try:
                message = json.loads(raw_message)
            except json.JSONDecodeError:
                continue
            if isinstance(message, dict) and message.get("type") == "input":
                await manager.handle_input(room, player.player_id, message)
    except WebSocketDisconnect:
        pass
    finally:
        await manager.leave(room, player.player_id)
