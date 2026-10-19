import os
import sys
import json
import socket
import time
import math
import hmac
import hashlib
import datetime
import asyncio
import threading
from typing import Optional, Dict, Any, List, Literal
from fastapi import FastAPI, HTTPException, Query, Header, WebSocket, WebSocketDisconnect, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import random
import uuid

from app.database import (
    init_db,
    get_stats,
    get_player_score,
    increment_player_score,
    get_top_player_scores,
    get_db_status,
    get_game_catalog,
    user_exists,
    create_user,
    authenticate_user,
    record_user_guess_word,
    record_user_game_finish,
    record_multigame_session_start,
    reset_user_password,
    get_user_stats,
    get_all_usernames,
    record_played_article,
    get_recently_played_articles,
    is_valid_user_identifier,
    is_gate_unlocked,
)
from app.secret_gate import (
    secret_gate_manager,
    generate_gate_token,
    verify_gate_token,
)
from app.nlp import normalize_wiki_title
from app.motus import MOTUS_DIFFICULTIES, motus_manager
from app.cemantix import cemantix_manager
from app.chiffrantix import ChiffrantixManager
from app.battleship import battleship_manager
from app.sudoku import sudoku_manager
from app.undercover import undercover_manager
from app.geoguessr import (
    MAX_SCORE_PER_ROUND as GEOGUESSR_MAX_SCORE_PER_ROUND,
    ROUND_COUNT as GEOGUESSR_ROUND_COUNT,
    GOOGLE_STREETVIEW_MONTHLY_LIMIT,
    geoguessr_manager,
)
from app.bitoguessr import (
    DATA_SOURCE_URL as BITOGUESSR_DATA_SOURCE_URL,
    bitoguessr_manager,
)
from app.plongee import plongee_manager
from app.game import GameManager, GameSession
from app.room import room_manager
from app.network import get_primary_lan_ip, get_all_lan_ips
from app.tunnel import tunnel_manager
from app.antibot import anti_bot_guard

app = FastAPI(title="Pédantix Local - Concours Multijoueur", version="2.0.0")

# Enable CORS (support PEDANTIX_ALLOWED_ORIGINS or default to allow all)
allowed_origins_env = os.environ.get("PEDANTIX_ALLOWED_ORIGINS", "*")
if allowed_origins_env and allowed_origins_env.strip() != "*":
    allowed_origins = []
    for o in allowed_origins_env.split(","):
        cleaned = o.strip()
        if cleaned:
            # Browsers send Origin headers without a trailing slash (RFC 6454).
            # Always ensure the slash-stripped version is allowed to prevent CORS failures.
            no_slash = cleaned.rstrip("/")
            if no_slash and no_slash not in allowed_origins:
                allowed_origins.append(no_slash)
            if cleaned not in allowed_origins:
                allowed_origins.append(cleaned)
else:
    allowed_origins = ["*"]

allowed_origin_regex = (
    r"https://(?:pedantixenac|enacgames)\.studio4242\.fr"
    r"|https://.*\.netlify\.app"
    r"|http://localhost(:\d+)?"
    r"|http://127\.0\.0\.1(:\d+)?"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=allowed_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Enforce security headers against clickjacking, overlay iframes and sniffing."""
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "frame-ancestors 'self'; "
        "object-src 'none'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://unpkg.com https://*.googleapis.com "
        "https://*.gstatic.com https://*.google.com https://*.ggpht.com "
        "https://*.googleusercontent.com blob:; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://unpkg.com; "
        "font-src 'self' https://fonts.gstatic.com data:; "
        "img-src 'self' data: https://tile.openstreetmap.org https://*.tile.openstreetmap.org "
        "https://*.basemaps.cartocdn.com https://server.arcgisonline.com "
        "https://*.mapillary.com https://*.fbcdn.net https://upload.wikimedia.org "
        "https://*.wikimedia.org https://*.wikipedia.org https://*.googleapis.com "
        "https://*.gstatic.com https://*.google.com https://*.googleusercontent.com; "
        "worker-src 'self' blob:; "
        "connect-src 'self' https://pedantix-api.onrender.com https://unpkg.com https://graph.mapillary.com "
        "https://*.mapillary.com https://*.fbcdn.net https://*.googleapis.com "
        "https://*.gstatic.com https://*.google.com data: blob: ws: wss:; "
        "frame-src https://*.google.com;"
    )
    return response

@app.middleware("http")
async def device_tracker_middleware(request: Request, call_next):
    """Intercepte chaque requête HTTP et affiche l'IP réelle et le User-Agent exact pour différencier les appareils."""
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    client_ip = get_client_ip(request)
    user_agent = request.headers.get("user-agent", "Inconnu / Aucun")
    method = request.method
    path = request.url.path

    # Marqueur visuel [DEVICE-TRACKER] et flush=True pour affichage temps réel dans les logs Render
    print(
        f"[DEVICE-TRACKER] {timestamp} | {method} {path} | IP: {client_ip} | UA: {user_agent}",
        flush=True
    )
    return await call_next(request)

# Initialize database on startup
init_db()

# Game manager instance
game_manager = GameManager()
chiffrantix_manager = ChiffrantixManager()
online_presence: Dict[str, Dict[str, Any]] = {}
online_presence_lock = threading.Lock()
ONLINE_PRESENCE_TTL_SECONDS = 90

# Static files directory
STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if not os.path.exists(STATIC_DIR):
    os.makedirs(STATIC_DIR)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def detect_lan_ip() -> str:
    return get_primary_lan_ip()


def get_client_ip(request: Request) -> str:
    """Extrait l'adresse IP client pour le suivi de cadence anti-bot."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "127.0.0.1"


# Pydantic schemas
class GuessRequest(BaseModel):
    session_id: str
    word: str
    player_name: Optional[str] = None
    guess_token: Optional[str] = None

class CheckUsernameRequest(BaseModel):
    username: str

class PresenceRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=80)
    username: str = Field(min_length=1, max_length=24)
    game_id: Literal[
        "pedantix", "motus", "cemantix", "chiffrantix", "sudoku", "battleship", "geoguessr",
        "undercover", "bitoguessr", "plongee", "store"
    ]

class AuthRegisterRequest(BaseModel):
    username: str
    password: str

class AuthLoginRequest(BaseModel):
    username: str
    password: str

class AdminUsersRequest(BaseModel):
    admin_username: str
    admin_password: str

class AdminPasswordResetRequest(AdminUsersRequest):
    target_username: str
    new_password: str

class HintRequest(BaseModel):
    session_id: str
    hint_type: str = "shortest"

class RoomCreateRequest(BaseModel):
    host_player_id: str
    host_name: Optional[str] = None
    player_name: Optional[str] = None
    room_id: Optional[str] = None
    difficulty: Optional[str] = "moyen"

class RoomJoinRequest(BaseModel):
    room_id: str = "default"
    player_id: str
    player_name: str
    difficulty: Optional[str] = None
    assist_token: Optional[str] = None

class RoomReadyRequest(BaseModel):
    room_id: str = "default"
    player_id: str
    ready: Optional[bool] = None

class RoomStartRequest(BaseModel):
    room_id: str = "default"
    player_id: str

class RoomNextRoundRequest(BaseModel):
    room_id: str = "default"
    player_id: str
    difficulty: Optional[str] = None

class RoomDifficultyRequest(BaseModel):
    room_id: str = "default"
    player_id: str
    difficulty: str

class RoomGuessRequest(BaseModel):
    room_id: str = "default"
    player_id: str
    word: str
    guess_token: Optional[str] = None

class RoomNewRoundRequest(BaseModel):
    room_id: str = "default"

class RoomUnmaskRequest(BaseModel):
    room_id: str = "default"
    player_id: str

class GameUnmaskRequest(BaseModel):
    session_id: str

class MotusPlayerRequest(BaseModel):
    player_id: str
    player_name: str
    difficulty: str = "moyen"

class MotusSoloGuessRequest(MotusPlayerRequest):
    game_id: str
    guess: str

class MotusRoomPlayerRequest(MotusPlayerRequest):
    room_id: str

class MotusRoomGuessRequest(MotusRoomPlayerRequest):
    guess: str

class CemantixPlayerRequest(BaseModel):
    player_id: str
    player_name: str
    difficulty: str = "moyen"

class CemantixSoloGuessRequest(CemantixPlayerRequest):
    game_id: str
    guess: str

class CemantixSoloActionRequest(CemantixPlayerRequest):
    game_id: str

class CemantixRoomPlayerRequest(CemantixPlayerRequest):
    room_id: str

class CemantixRoomGuessRequest(CemantixRoomPlayerRequest):
    guess: str

class ChiffrantixPlayerRequest(BaseModel):
    player_id: str
    player_name: str
    difficulty: str = "moyen"
    category: str = "toutes"

class ChiffrantixSoloGuessRequest(ChiffrantixPlayerRequest):
    game_id: str
    guess: str

class ChiffrantixSoloHintRequest(ChiffrantixPlayerRequest):
    game_id: str

class ChiffrantixRoomPlayerRequest(ChiffrantixPlayerRequest):
    room_id: str

class ChiffrantixRoomGuessRequest(ChiffrantixRoomPlayerRequest):
    guess: str

class BattleshipPlayerRequest(BaseModel):
    player_id: str
    player_name: str
    difficulty: str = "moyen"

class BattleshipRoomPlayerRequest(BattleshipPlayerRequest):
    room_id: str

class BattleshipFleetRequest(BattleshipRoomPlayerRequest):
    fleet: Dict[str, List[str]]

class BattleshipReadyRequest(BattleshipRoomPlayerRequest):
    ready: bool

class BattleshipFireRequest(BattleshipRoomPlayerRequest):
    coordinate: str

class SudokuPlayerRequest(BaseModel):
    player_id: str
    player_name: str

class SudokuSoloCreateRequest(SudokuPlayerRequest):
    difficulty: str

class SudokuSoloCellRequest(SudokuPlayerRequest):
    game_id: str
    row: int
    column: int
    value: int

class SudokuRoomCreateRequest(SudokuPlayerRequest):
    difficulty: str

class SudokuRoomPlayerRequest(SudokuPlayerRequest):
    room_id: str

class SudokuRoomCellRequest(SudokuRoomPlayerRequest):
    row: int
    column: int
    value: int

class UndercoverPlayerRequest(BaseModel):
    player_id: str
    player_name: str

class UndercoverRoomPlayerRequest(UndercoverPlayerRequest):
    room_id: str

class UndercoverVoteRequest(UndercoverRoomPlayerRequest):
    target_player_id: str

class UndercoverGuessRequest(UndercoverRoomPlayerRequest):
    guess: str

class GeoGuessrPlayerRequest(BaseModel):
    player_id: str
    player_name: str
    region: Literal["france", "europe", "world"] = "world"
    variant: Literal["cities", "panorama"] = "cities"

class GeoGuessrRoomPlayerRequest(BaseModel):
    room_id: str
    player_id: str
    player_name: str

class GeoGuessrRoomCreateRequest(GeoGuessrPlayerRequest):
    round_count: int = Field(default=5, ge=1, le=20)

class GeoGuessrSoloGuessRequest(GeoGuessrPlayerRequest):
    game_id: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)

class GeoGuessrRoomGuessRequest(GeoGuessrRoomPlayerRequest):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)

class GeoGuessrPanoramaViewRequest(BaseModel):
    player_id: str
    game_id: Optional[str] = None
    room_id: Optional[str] = None
    navigation: bool = False

class BitoguessrPlayerRequest(BaseModel):
    player_id: str = Field(min_length=1, max_length=100)
    player_name: str = Field(min_length=1, max_length=40)

class BitoguessrSoloCreateRequest(BitoguessrPlayerRequest):
    difficulty: Literal["normal", "difficile"] = "normal"

class BitoguessrRoomCreateRequest(BitoguessrSoloCreateRequest):
    round_count: int = Field(default=10, ge=1, le=20)

class BitoguessrRoomPlayerRequest(BitoguessrPlayerRequest):
    room_id: str = Field(min_length=1, max_length=6)

class BitoguessrSoloGuessRequest(BitoguessrPlayerRequest):
    game_id: str = Field(min_length=1, max_length=64)
    guess: str = Field(min_length=1, max_length=48)

class BitoguessrSoloNextRequest(BitoguessrPlayerRequest):
    game_id: str = Field(min_length=1, max_length=64)

class BitoguessrRoomGuessRequest(BitoguessrRoomPlayerRequest):
    guess: str = Field(min_length=1, max_length=48)

class PlongeePlayerRequest(BaseModel):
    player_id: str = Field(min_length=1, max_length=100)
    player_name: str = Field(min_length=1, max_length=24)

class PlongeeSoloGuessRequest(PlongeePlayerRequest):
    game_id: str = Field(min_length=1, max_length=64)
    answer: str = Field(min_length=1, max_length=160)

class PlongeeSoloActionRequest(PlongeePlayerRequest):
    game_id: str = Field(min_length=1, max_length=64)

class PlongeeRoomRequest(PlongeePlayerRequest):
    room_id: str = Field(min_length=1, max_length=5)

class PlongeeRoomGuessRequest(PlongeeRoomRequest):
    answer: str = Field(min_length=1, max_length=160)

class GateGuessRequest(BaseModel):
    player_id: str = Field(min_length=1, max_length=100)
    guess: str = Field(min_length=1, max_length=120)

class GateResetRequest(BaseModel):
    player_id: str = Field(min_length=1, max_length=100)


class RoomChatRequest(BaseModel):
    room_id: str = "default"
    player_id: str
    sender_name: str
    text: str

class RoomModeRequest(BaseModel):
    room_id: str = "default"
    player_id: str
    game_mode: str

class RoomTeamRequest(BaseModel):
    room_id: str = "default"
    player_id: str
    team: str

class RoomLeaveRequest(BaseModel):
    room_id: str
    player_id: str

class RoomSurrenderRequest(BaseModel):
    room_id: str = "default"
    player_id: str
    vote: str = "yes"

class RoomSpectatorRequest(BaseModel):
    room_id: str = "default"
    player_id: str
    is_spectator: Optional[bool] = None

class RoomCheatReportRequest(BaseModel):
    room_id: str = "default"
    player_id: str
    reason: str = "overlay_detected"



@app.get("/")
async def root():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Pédantix Local API opérationnelle."}

@app.get("/games/pedantix/")
async def pedantix_page():
    index_path = os.path.join(STATIC_DIR, "games", "pedantix", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    raise HTTPException(status_code=404, detail="La page Pédantix est introuvable.")

@app.get("/games/motus/")
async def motus_page():
    index_path = os.path.join(STATIC_DIR, "games", "motus", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    raise HTTPException(status_code=404, detail="La page Motus est introuvable.")

@app.get("/games/cemantix/")
async def cemantix_page():
    index_path = os.path.join(STATIC_DIR, "games", "cemantix", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    raise HTTPException(status_code=404, detail="La page Cémantix est introuvable.")

@app.get("/games/chiffrantix/")
async def chiffrantix_page():
    index_path = os.path.join(STATIC_DIR, "games", "chiffrantix", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    raise HTTPException(status_code=404, detail="La page Chiffrantix est introuvable.")

@app.get("/games/battleship/")
async def battleship_page():
    index_path = os.path.join(STATIC_DIR, "games", "battleship", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    raise HTTPException(status_code=404, detail="La page Bataille navale est introuvable.")

@app.get("/games/sudoku/")
async def sudoku_page():
    index_path = os.path.join(STATIC_DIR, "games", "sudoku", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    raise HTTPException(status_code=404, detail="La page Sudoku est introuvable.")

@app.get("/games/geoguessr/")
async def geoguessr_page():
    index_path = os.path.join(STATIC_DIR, "games", "geoguessr", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    raise HTTPException(status_code=404, detail="La page GeoGuessr est introuvable.")

@app.get("/games/undercover/")
async def undercover_page():
    index_path = os.path.join(STATIC_DIR, "games", "undercover", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    raise HTTPException(status_code=404, detail="La page Undercover est introuvable.")

@app.get("/games/plongee/")
async def plongee_page():
    index_path = os.path.join(STATIC_DIR, "games", "plongee", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    raise HTTPException(status_code=404, detail="La page Plongée est introuvable.")

def _is_bitoguessr_authorized(request: Request, player_id: Optional[str] = None) -> bool:
    token = (
        request.cookies.get("bitoguessr_access_token")
        or request.headers.get("x-gate-token")
        or request.query_params.get("gate_token")
    )
    if token and verify_gate_token(token):
        return True

    pid = (
        player_id
        or request.headers.get("x-player-id")
        or request.query_params.get("player_id")
        or request.cookies.get("bitoguessr_player_id")
    )
    user = (
        request.headers.get("x-auth-user")
        or request.cookies.get("bitoguessr_auth_user")
    )
    if pid or user:
        if is_gate_unlocked(pid, user):
            return True

    return False


def _require_bitoguessr_access(request: Request, player_id: Optional[str] = None) -> None:
    if not _is_bitoguessr_authorized(request, player_id):
        raise HTTPException(
            status_code=403,
            detail="Le Gardien interdit l'accès : les 10 sceaux doivent être brisés.",
        )


@app.get("/static/games/bitoguessr/index.html")
async def bitoguessr_static_index(request: Request):
    if _is_bitoguessr_authorized(request):
        index_path = os.path.join(STATIC_DIR, "games", "bitoguessr", "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/games/bitoguessr/")


@app.get("/games/bitoguessr/")
@app.get("/games/bitoguessr")
async def bitoguessr_page(request: Request, player_id: Optional[str] = Query(None)):
    gate_path = os.path.join(STATIC_DIR, "games", "bitoguessr", "gate.html")
    index_path = os.path.join(STATIC_DIR, "games", "bitoguessr", "index.html")

    if _is_bitoguessr_authorized(request, player_id):
        if os.path.exists(index_path):
            return FileResponse(index_path)
        raise HTTPException(status_code=404, detail="La page Bitoguessr est introuvable.")

    if os.path.exists(gate_path):
        return FileResponse(gate_path)
    raise HTTPException(status_code=404, detail="Le Gardien du Seuil est introuvable.")


@app.get("/health")
async def health_check():
    db_status = get_db_status()
    return {
        "status": "ok",
        "timestamp": time.time(),
        "database": db_status["active_type"],
        "database_details": db_status,
    }


@app.post("/api/webhooks/github")
async def github_push_webhook(request: Request):
    secret = os.environ.get("GITHUB_WEBHOOK_SECRET", "").strip()
    if not secret:
        raise HTTPException(status_code=503, detail="GitHub webhook is not configured.")

    body = await request.body()
    signature = request.headers.get("x-hub-signature-256", "")
    if not signature.startswith("sha256="):
        raise HTTPException(status_code=401, detail="Invalid webhook signature.")
    expected_signature = "sha256=" + hmac.new(
        secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature.")

    if request.headers.get("x-github-event") != "push":
        return {"status": "ignored"}

    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid webhook payload.") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid webhook payload.")

    repository = payload.get("repository")
    repository_name = repository.get("full_name", "") if isinstance(repository, dict) else ""
    ref = payload.get("ref", "")
    branch = ref.removeprefix("refs/heads/") if isinstance(ref, str) else ""
    commits = payload.get("commits", [])
    message = {
        "type": "github_push_notice",
        "repository": repository_name[:120] if isinstance(repository_name, str) else "",
        "branch": branch[:120],
        "commit_count": len(commits) if isinstance(commits, list) else 0,
    }
    for room in list(room_manager.rooms.values()):
        if room.websockets:
            await room.broadcast(message)
    return {"status": "broadcast"}


@app.get("/api/rooms")
async def list_active_rooms():
    return {"rooms": room_manager.list_active_rooms()}

@app.post("/api/presence")
async def update_presence(req: PresenceRequest):
    session_id = req.session_id.strip()[:80]
    username = req.username.strip()[:24]
    if not session_id or not username:
        raise HTTPException(status_code=400, detail="Une session et un nom sont requis.")

    now = time.time()
    with online_presence_lock:
        expired = [
            key for key, presence in online_presence.items()
            if now - presence["last_seen"] > ONLINE_PRESENCE_TTL_SECONDS
        ]
        for key in expired:
            del online_presence[key]
        online_presence[session_id] = {
            "username": username,
            "game_id": req.game_id,
            "last_seen": now,
        }
    return {"status": "ok"}

@app.get("/api/presence")
async def list_online_presence():
    now = time.time()
    with online_presence_lock:
        expired = [
            key for key, presence in online_presence.items()
            if now - presence["last_seen"] > ONLINE_PRESENCE_TTL_SECONDS
        ]
        for key in expired:
            del online_presence[key]

        latest_by_username: Dict[str, Dict[str, Any]] = {}
        for presence in online_presence.values():
            key = presence["username"].casefold()
            current = latest_by_username.get(key)
            if current is None or presence["last_seen"] > current["last_seen"]:
                latest_by_username[key] = presence

        players = [
            {
                "username": presence["username"],
                "game_id": presence["game_id"],
            }
            for presence in latest_by_username.values()
        ]
    players.sort(key=lambda player: player["username"].casefold())
    return {"players": players}

@app.get("/api/network-info")
async def get_network_info():
    lan_ip = detect_lan_ip()
    all_ips = get_all_lan_ips()
    port = os.environ.get("PEDANTIX_PORT", "8088")
    tunnel_info = tunnel_manager.get_info()
    return {
        "lan_ip": lan_ip,
        "all_ips": all_ips,
        "port": port,
        "local_url": f"http://localhost:{port}",
        "lan_url": f"http://{lan_ip}:{port}",
        "join_url": f"http://{lan_ip}:{port}",
        "tunnel_url": tunnel_info.get("url"),
        "tunnel_status": tunnel_info.get("status"),
        "tunnel_error": tunnel_info.get("error")
    }


@app.post("/api/tunnel/start")
async def start_tunnel():
    port = int(os.environ.get("PEDANTIX_PORT", 8088))
    tunnel_manager.start(port=port)
    return tunnel_manager.get_info()


@app.post("/api/tunnel/stop")
async def stop_tunnel():
    tunnel_manager.stop()
    return tunnel_manager.get_info()


# ============================================================================
# MULTIPLAYER ROOM & COMPETITION ENDPOINTS
# ============================================================================

@app.post("/api/room/create")
async def create_room(req: RoomCreateRequest):
    host_name = req.host_name or req.player_name or "Host"
    host_idents = [req.host_player_id.strip().lower()]
    if is_valid_user_identifier(host_name):
        host_idents.append(host_name.strip().lower())
    excluded = get_recently_played_articles(host_idents, days=15)

    room = await room_manager.create_new_room_async(
        req.host_player_id,
        host_name=host_name,
        custom_id=req.room_id,
        difficulty=req.difficulty or "moyen",
        exclude_titles=excluded
    )
    return {
        "room_id": room.room_id,
        "host_player_id": room.host_player_id,
        "status": room.status,
        "seed": room.seed,
        "difficulty": room.difficulty
    }


@app.post("/api/room/join")
async def join_room(req: RoomJoinRequest):
    diff = req.difficulty if req.difficulty in ("facile", "moyen", "difficile") else "moyen"
    if req.assist_token:
        room = room_manager.get_room(req.room_id)
        if (
            not room
            or not room.room_id.startswith("solo-")
            or not hmac.compare_digest(room.assist_token, req.assist_token)
        ):
            raise HTTPException(status_code=404, detail="Lien d'aide invalide ou expiré.")
        owner_id = room.room_id.removeprefix("solo-")
        owner = room.players.get(owner_id)
        if not owner or room.status != "playing":
            raise HTTPException(status_code=409, detail="Cette partie solo n'est plus disponible pour l'aide.")
        if req.player_id == owner_id:
            raise HTTPException(status_code=400, detail="Vous ne pouvez pas rejoindre votre propre partie comme aide.")
        if room.assisting_player_id and room.assisting_player_id != req.player_id:
            raise HTTPException(status_code=409, detail="Un autre joueur aide déjà sur cette page.")
    else:
        room = room_manager.get_or_create_room(
            req.room_id,
            difficulty=diff,
            player_id=req.player_id,
            player_name=req.player_name
        )
    is_reconnect = req.player_id in room.players
    if not req.assist_token and not is_reconnect and req.room_id.startswith("solo-") and req.difficulty and req.difficulty != room.difficulty:
        excluded = room.get_recently_played_titles(days=15)
        new_art = await asyncio.to_thread(room_manager._fetch_random_article, req.difficulty, exclude_titles=excluded)
        room.set_difficulty(req.difficulty, new_article=new_art)
    player = room.get_or_create_player(req.player_id, req.player_name)
    if req.assist_token:
        owner_id = room.room_id.removeprefix("solo-")
        player.session = room.players[owner_id].session
        player.is_host = False
        player.is_ready = True
        room.assisting_player_id = player.player_id
    if room.room_id.startswith("solo-"):
        room.start_word_hint_timer()

    # In multiplayer lobby, verify if current article was played in last 15 days by any player in room
    if not is_reconnect and not room.room_id.startswith("solo-") and room.status == "lobby":
        excluded_titles = room.get_recently_played_titles(days=15)
        exclude_norm = {normalize_wiki_title(t) for t in excluded_titles if t}
        curr_title = room.article_data.get("title", "")
        if curr_title in excluded_titles or normalize_wiki_title(curr_title) in exclude_norm:
            new_art = await asyncio.to_thread(room_manager._fetch_random_article, room.difficulty, exclude_titles=excluded_titles)
            if new_art:
                room.article_data = new_art
                room.seed = f"P-{random.randint(1000, 9999)}"
                # Synchronize sessions for all players and teams in room
                if room.game_mode == "team":
                    room._init_team_sessions()
                    for p in room.players.values():
                        if p.team in room.team_sessions:
                            p.session = room.team_sessions[p.team]
                else:
                    for p in room.players.values():
                        session_id = str(uuid.uuid4())
                        p.session = GameSession(
                            session_id=session_id,
                            seed=room.seed,
                            title=room.article_data["title"],
                            url=room.article_data.get("url", ""),
                            image=room.article_data.get("image", ""),
                            paragraphs=room.article_data["paragraphs"],
                            mode=room.session_mode,
                            category=room.article_data.get("category", "general"),
                            difficulty=room.difficulty,
                            lang_count=room.article_data.get("lang_count", 0),
                            pageviews_90d=room.article_data.get("pageviews_90d", int(room.article_data.get("pageviews_60d", 0) * 1.5))
                        )

    # Broadcast player joined to all active websockets in this room
    await room.broadcast({
        "type": "player_joined",
        "is_reconnect": is_reconnect,
        "player": player.to_dict(),
        "game_mode": room.game_mode,
        "difficulty": room.difficulty,
        "teams": room.get_teams_data(),
        "leaderboard": room.get_leaderboard(),
        "activity": room.recent_activity,
        "status": room.status,
        "host_player_id": room.host_player_id,
        "assisting_player_id": room.assisting_player_id,
        "can_start": room.can_start()
    })

    active_session = room.team_sessions.get(player.team, player.session) if room.game_mode == "team" and room.team_sessions else player.session
    guess_token = anti_bot_guard.get_or_issue_token(f"{room.room_id}:{player.player_id}")
    return {
        "room_id": room.room_id,
        "seed": room.seed,
        "guess_token": guess_token,
        "assist_token": room.assist_token if player.player_id == room.room_id.removeprefix("solo-") else None,
        "assisting_player_id": room.assisting_player_id,
        "game_mode": room.game_mode,
        "difficulty": room.difficulty,
        "article_difficulty": room.article_data.get("difficulty", room.difficulty),
        "article_lang_count": room.article_data.get("lang_count", 0),
        "article_pageviews_90d": room.article_data.get("pageviews_90d", int(room.article_data.get("pageviews_60d", 0) * 1.5)),
        "player": player.to_dict(),
        "teams": room.get_teams_data(),
        "leaderboard": room.get_leaderboard(),
        "session": active_session.get_public_state(hinted_word_ids=room.hinted_word_ids),
        "next_word_hint_time": room.next_word_hint_time,
        "activity": room.recent_activity,
        "status": room.status,
        "host_player_id": room.host_player_id,
        "can_start": room.can_start(),
        "countdown_end": room.countdown_end,
        "timer_30s_end": room.timer_30s_end,
        "first_winner_name": room.first_winner_name,
        "first_winner_attempts": room.first_winner_attempts,
        "last_round": room.last_round_results,
        "rounds_played": room.rounds_played,
        "next_word_hint_time": room.next_word_hint_time,
        "surrender_in_progress": room.surrender_in_progress,
        "surrender_initiator_id": room.surrender_initiator_id,
        "surrender_initiator_name": room.surrender_initiator_name,
        "surrender_votes_count": len(room.surrender_votes),
        "surrender_cooldowns": {
            pid: max(0, int(math.ceil(until - time.time())))
            for pid, until in room.surrender_cooldowns.items()
            if until > time.time()
        }
    }


@app.post("/api/room/leave")
async def leave_room(req: RoomLeaveRequest):
    room = room_manager.get_room(req.room_id)
    if room:
        await room.remove_player(req.player_id)
    return {"status": "ok"}


@app.post("/api/room/ready")
async def ready_room(req: RoomReadyRequest):
    room = room_manager.get_or_create_room(req.room_id)
    is_ready = room.toggle_ready(req.player_id, req.ready)
    player = room.players.get(req.player_id)

    # Broadcast ready update to all clients
    await room.broadcast({
        "type": "player_ready_changed",
        "player_id": req.player_id,
        "player_name": player.name if player else "",
        "is_ready": is_ready,
        "can_start": room.can_start(),
        "game_mode": room.game_mode,
        "teams": room.get_teams_data(),
        "leaderboard": room.get_leaderboard(),
        "activity": room.recent_activity
    })

    return {
        "player_id": req.player_id,
        "is_ready": is_ready,
        "can_start": room.can_start(),
        "game_mode": room.game_mode,
        "teams": room.get_teams_data(),
        "leaderboard": room.get_leaderboard()
    }


@app.post("/api/room/spectator")
async def toggle_room_spectator(req: RoomSpectatorRequest):
    room = room_manager.get_or_create_room(req.room_id)
    if req.player_id not in room.players:
        raise HTTPException(status_code=404, detail="Joueur introuvable dans la salle.")
    is_spectator = room.toggle_spectator(req.player_id, req.is_spectator)
    player = room.players[req.player_id]

    await room.broadcast({
        "type": "player_spectator_changed",
        "player_id": req.player_id,
        "player_name": player.name,
        "is_spectator": is_spectator,
        "is_ready": player.is_ready,
        "can_start": room.can_start(),
        "game_mode": room.game_mode,
        "teams": room.get_teams_data(),
        "leaderboard": room.get_leaderboard(),
        "activity": room.recent_activity
    })

    return {
        "status": "ok",
        "player_id": req.player_id,
        "is_spectator": is_spectator,
        "is_ready": player.is_ready,
        "can_start": room.can_start(),
        "leaderboard": room.get_leaderboard()
    }


@app.post("/api/room/mode")
async def set_room_mode(req: RoomModeRequest):
    room = room_manager.get_or_create_room(req.room_id)
    player = room.players.get(req.player_id)
    if not player or not player.is_host:
        raise HTTPException(status_code=403, detail="Seul l'Host peut changer le mode de jeu.")
    success = room.set_game_mode(req.game_mode)
    if not success:
        raise HTTPException(status_code=400, detail="Impossible de changer le mode de jeu actuellement.")
    await room.broadcast({
        "type": "mode_changed",
        "game_mode": room.game_mode,
        "teams": room.get_teams_data(),
        "leaderboard": room.get_leaderboard(),
        "can_start": room.can_start(),
        "activity": room.recent_activity
    })
    return {
        "status": "ok",
        "game_mode": room.game_mode,
        "teams": room.get_teams_data(),
        "can_start": room.can_start()
    }


@app.post("/api/room/team")
async def set_room_team(req: RoomTeamRequest):
    room = room_manager.get_or_create_room(req.room_id)
    if req.player_id not in room.players:
        raise HTTPException(status_code=404, detail="Joueur introuvable dans la salle.")
    success = room.set_player_team(req.player_id, req.team)
    if not success:
        raise HTTPException(status_code=400, detail="Impossible de changer d'équipe.")
    player = room.players[req.player_id]
    await room.broadcast({
        "type": "team_changed",
        "player_id": req.player_id,
        "team": req.team,
        "teams": room.get_teams_data(),
        "leaderboard": room.get_leaderboard(),
        "can_start": room.can_start(),
        "activity": room.recent_activity
    })
    return {
        "status": "ok",
        "team": req.team,
        "teams": room.get_teams_data(),
        "can_start": room.can_start()
    }


@app.post("/api/room/start")
async def start_room(req: RoomStartRequest):
    room = room_manager.get_or_create_room(req.room_id)
    res = await room.start_game(req.player_id)
    if "error" in res:
        raise HTTPException(status_code=400, detail=res["error"])
    return res


@app.post("/api/room/difficulty")
async def set_room_difficulty(req: RoomDifficultyRequest):
    room = room_manager.get_or_create_room(req.room_id)
    player = room.players.get(req.player_id)
    if not player:
        raise HTTPException(status_code=404, detail="Joueur introuvable dans la salle.")
    if not player.is_host:
        raise HTTPException(status_code=403, detail="Seul l'Host peut modifier la difficulté.")
    if room.assisting_player_id:
        raise HTTPException(status_code=409, detail="La difficulté ne peut pas changer pendant qu'un joueur aide sur cette page.")
    if req.difficulty not in ("facile", "moyen", "difficile"):
        raise HTTPException(status_code=400, detail="Difficulté invalide.")

    # Strictly disallow changing difficulty in multiplayer once game has started
    if not room.room_id.startswith("solo-") and room.status != "lobby":
        raise HTTPException(status_code=400, detail="Impossible de modifier la difficulté en cours de partie.")

    excluded_titles = room.get_recently_played_titles(days=15)
    new_art = await asyncio.to_thread(room_manager._fetch_random_article, req.difficulty, exclude_titles=excluded_titles)
    success = room.set_difficulty(req.difficulty, new_article=new_art)
    if not success:
        raise HTTPException(status_code=400, detail="Impossible de modifier la difficulté.")

    active_session = room.team_sessions.get(player.team, player.session) if room.game_mode == "team" and room.team_sessions else player.session
    public_session = active_session.get_public_state(hinted_word_ids=room.hinted_word_ids) if active_session else None

    if room.room_id.startswith("solo-"):
        room.start_word_hint_timer()
        await room.broadcast({
            "type": "new_round",
            "status": "playing",
            "seed": room.seed,
            "difficulty": room.difficulty,
            "article_difficulty": room.article_data.get("difficulty", room.difficulty),
            "article_lang_count": room.article_data.get("lang_count", 0),
            "article_pageviews_90d": room.article_data.get("pageviews_90d", int(room.article_data.get("pageviews_60d", 0) * 1.5)),
            "game_mode": room.game_mode,
            "leaderboard": room.get_leaderboard(),
            "activity": room.recent_activity,
            "next_word_hint_time": room.next_word_hint_time
        })
    else:
        await room.broadcast({
            "type": "difficulty_changed",
            "difficulty": room.difficulty,
            "article_difficulty": room.article_data.get("difficulty", room.difficulty),
            "article_lang_count": room.article_data.get("lang_count", 0),
            "article_pageviews_90d": room.article_data.get("pageviews_90d", int(room.article_data.get("pageviews_60d", 0) * 1.5)),
            "can_start": room.can_start(),
            "activity": room.recent_activity
        })

    return {
        "status": "ok",
        "difficulty": room.difficulty,
        "article_difficulty": room.article_data.get("difficulty", room.difficulty),
        "article_lang_count": room.article_data.get("lang_count", 0),
        "article_pageviews_90d": room.article_data.get("pageviews_90d", int(room.article_data.get("pageviews_60d", 0) * 1.5)),
        "seed": room.seed,
        "next_word_hint_time": room.next_word_hint_time,
        "session": public_session
    }


@app.post("/api/room/next-round")
async def next_round_room(req: RoomNextRoundRequest):
    room = room_manager.get_or_create_room(req.room_id)
    if room.assisting_player_id:
        raise HTTPException(status_code=409, detail="La page ne peut pas être remplacée pendant qu'un joueur aide.")
    if not room.room_id.startswith("solo-") and room.status not in ("lobby", "round_over"):
        raise HTTPException(status_code=400, detail="Impossible de lancer une nouvelle manche pendant une partie en cours.")
    player = room.players.get(req.player_id)
    if not room.room_id.startswith("solo-") and player and not player.is_host:
        raise HTTPException(status_code=403, detail="Seul l'Host peut lancer la manche suivante.")
    diff = req.difficulty if req.difficulty in ("facile", "moyen", "difficile") else room.difficulty
    room.difficulty = diff
    excluded_titles = room.get_recently_played_titles(days=15)
    new_article = await asyncio.to_thread(room_manager._fetch_random_article, diff, exclude_titles=excluded_titles)
    seed_num = random.randint(1000, 9999)
    new_seed = f"P-{seed_num}"
    res = await room.start_new_round(req.player_id, new_article, new_seed)
    if "error" in res:
        raise HTTPException(status_code=400, detail=res["error"])
    return res


@app.post("/api/room/guess")
async def room_guess(req: RoomGuessRequest, request: Request):
    room = room_manager.get_or_create_room(req.room_id)
    player = room.players.get(req.player_id)
    if not player:
        raise HTTPException(status_code=404, detail="Joueur introuvable dans la salle.")

    if player.is_spectator:
        return {"error": "Vous êtes en mode spectateur (en pause). Reprenez votre place de joueur pour proposer des mots."}

    client_ip = get_client_ip(request)
    identifier = f"{room.room_id}:{req.player_id}"

    # Log détaillé de l'appareil pour différencier les joueurs sous même IP
    now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    ua_str = request.headers.get("user-agent", "Inconnu")
    p_name = player.name if player else "Anonyme"
    print(
        f"[DEVICE-TRACKER][GUESS] {now_str} | Salon: {req.room_id} | Joueur: {p_name} ({req.player_id}) | "
        f"IP: {client_ip} | Mot: '{req.word}' | UA: {ua_str}",
        flush=True
    )

    # 0. Détection des pièges canaris (honeypots DOM anti-scraping / anti-extension)
    if anti_bot_guard.is_honeypot_word(req.word):
        anti_bot_guard.trigger_cheat_penalty(identifier, duration=30.0)
        p_name = player.name if player else "Un joueur"
        await room.broadcast({
            "type": "anti_cheat_alert",
            "message": f"🤖 Détection formelle d'un scraper DOM / extension de triche pour {p_name} ! Suspension immédiate de 30s.",
            "player_id": req.player_id,
            "player_name": p_name,
            "penalty_seconds": 30
        })
        return {
            "status": "bot_blocked",
            "error": "Piège anti-triche activé : extraction/scraping automatisé de la page détecté.",
            "cooldown_seconds": 30,
            "penalty": True,
            "next_token": anti_bot_guard.rotate_token(identifier)
        }

    # 1. Validation de la saisie (longueur, caractères suspects, injections de code)
    is_valid_word, err_msg = anti_bot_guard.validate_word(req.word)
    if not is_valid_word:
        return {
            "status": "bot_blocked",
            "error": err_msg,
            "cooldown_seconds": 1,
            "next_token": anti_bot_guard.rotate_token(identifier)
        }

    # 2. Contrôle de cadence anti-bot / anti-spam
    allowed, err_msg, meta = anti_bot_guard.check_rate_limit(identifier, ip=client_ip)
    if not allowed:
        if meta.get("penalty"):
            p_name = player.name if player else "Un joueur"
            await room.broadcast({
                "type": "anti_cheat_alert",
                "message": f"🤖 Comportement automatisé / bot détecté pour {p_name} ! Suspension temporaire de {meta.get('remaining', 15)}s.",
                "player_id": req.player_id,
                "player_name": p_name,
                "penalty_seconds": meta.get("remaining", 15)
            })
        return {
            "status": "bot_blocked",
            "error": err_msg,
            "cooldown_seconds": meta.get("remaining", 1),
            "penalty": meta.get("penalty", False),
            "next_token": anti_bot_guard.rotate_token(identifier)
        }

    # 3. Contrôle du jeton cryptographique séquentiel (protection contre scripts externes sans handshake)
    valid_token, tok_err, next_token = anti_bot_guard.verify_token(identifier, req.guess_token)
    if not valid_token:
        return {
            "status": "bot_blocked",
            "error": tok_err,
            "cooldown_seconds": 1,
            "next_token": next_token
        }

    res = room.process_guess(req.player_id, req.word)
    res["next_token"] = next_token

    if "error" in res or res.get("is_repeat") or res.get("status") == "already_guessed":
        return res

    # Broadcast updated progress to everyone
    await room.broadcast({
        "type": "progress_update",
        "player": player.to_dict(),
        "leaderboard": room.get_leaderboard(),
        "activity": room.recent_activity,
        "status": room.status,
        "game_mode": room.game_mode,
        "team": player.team,
        "teams": room.get_teams_data(),
        "first_winner_name": room.first_winner_name,
        "first_winner_attempts": room.first_winner_attempts,
        "is_game_won": player.is_won,
        "title": None,
        "team_guess": {
            "player_id": player.player_id,
            "player_name": player.name,
            "team": player.team,
            "word": req.word,
            "status": res.get("status"),
            "matches_count": res.get("matches_count", 0),
            "score": res.get("score", 0),
            "newly_revealed": res.get("newly_revealed", {}) if room.game_mode == "team" else {},
            "close_tokens": res.get("close_tokens", []) if room.game_mode == "team" else [],
            "attempt_number": res.get("attempt_number", player.attempts)
        } if room.game_mode == "team" else None,
        "cooperative_solo": room.is_cooperative_solo,
        "assisted_guess": {
            "player_id": player.player_id,
            "player_name": player.name,
            "word": req.word,
            "status": res.get("status"),
            "matches_count": res.get("matches_count", 0),
            "score": res.get("score", 0),
            "newly_revealed": res.get("newly_revealed", {}),
            "close_tokens": res.get("close_tokens", []),
            "attempt_number": res.get("attempt_number", player.attempts),
            "revealed_words_count": res.get("revealed_words_count", player.revealed_words_count),
            "history": res.get("history", []),
            "is_won": res.get("is_won", False)
        } if room.is_cooperative_solo else None
    })
    if room.is_cooperative_solo and res.get("is_won"):
        await room._finish_round()

    return res


@app.post("/api/room/unmask")
async def unmask_room(req: RoomUnmaskRequest):
    room = room_manager.get_or_create_room(req.room_id)
    res = room.unmask_player(req.player_id)
    if "error" in res:
        status_code = 403 if "manche terminée" in res["error"] else 404
        raise HTTPException(status_code=status_code, detail=res["error"])
    await room.broadcast({
        "type": "article_unmasked",
        "player_id": req.player_id,
        "player_name": room.players[req.player_id].name,
        "tokens": res.get("tokens", {}),
    })
    return res


@app.post("/api/room/surrender")
async def surrender_room(req: RoomSurrenderRequest):
    room = room_manager.get_or_create_room(req.room_id)
    res = await room.propose_or_vote_surrender(req.player_id, req.vote)
    if "error" in res:
        raise HTTPException(status_code=400, detail=res["error"])
    return res

@app.post("/api/room/cheat-report")
async def report_cheat(req: RoomCheatReportRequest):
    """Point de terminaison télémétrie client (sans fausse pénalité automatique)."""
    return {"status": "reported", "cooldown_seconds": 0}


@app.post("/api/room/chat")
async def room_chat(req: RoomChatRequest):
    room = room_manager.get_or_create_room(req.room_id)
    if not req.text or not req.text.strip():
        raise HTTPException(status_code=400, detail="Message vide.")
    msg_obj = room.add_chat_message(req.player_id, req.sender_name, req.text)
    await room.broadcast({
        "type": "chat_message",
        "message": msg_obj
    })
    return {"status": "ok", "message": msg_obj}


@app.get("/api/room/{room_id}/state")
async def get_room_state(room_id: str, player_id: Optional[str] = None):
    room = room_manager.get_or_create_room(room_id)
    player_data = None
    session_data = None
    guess_token = None
    if player_id and player_id in room.players:
        p = room.players[player_id]
        player_data = p.to_dict()
        guess_token = anti_bot_guard.get_or_issue_token(f"{room.room_id}:{player_id}")
        if room.game_mode == "team":
            team_sess = room.team_sessions.get(p.team, p.session)
            session_data = team_sess.get_public_state(hinted_word_ids=room.hinted_word_ids)
        else:
            session_data = p.session.get_public_state(hinted_word_ids=room.hinted_word_ids)

    return {
        "room_id": room.room_id,
        "seed": room.seed,
        "guess_token": guess_token,
        "status": room.status,
        "game_mode": room.game_mode,
        "difficulty": room.difficulty,
        "article_difficulty": room.article_data.get("difficulty", room.difficulty),
        "article_lang_count": room.article_data.get("lang_count", 0),
        "article_pageviews_90d": room.article_data.get("pageviews_90d", int(room.article_data.get("pageviews_60d", 0) * 1.5)),
        "teams": room.get_teams_data(),
        "host_player_id": room.host_player_id,
        "can_start": room.can_start(),
        "countdown_end": room.countdown_end,
        "timer_30s_end": room.timer_30s_end,
        "first_winner_name": room.first_winner_name,
        "first_winner_attempts": room.first_winner_attempts,
        "leaderboard": room.get_leaderboard(),
        "activity": room.recent_activity,
        "chat_messages": room.chat_messages,
        "player": player_data,
        "session": session_data,
        "last_round": room.last_round_results,
        "rounds_played": room.rounds_played,
        "next_word_hint_time": room.next_word_hint_time,
        "surrender_in_progress": room.surrender_in_progress,
        "surrender_initiator_id": room.surrender_initiator_id,
        "surrender_initiator_name": room.surrender_initiator_name,
        "surrender_votes_count": len(room.surrender_votes),
        "surrender_cooldowns": {
            pid: max(0, int(math.ceil(until - time.time())))
            for pid, until in room.surrender_cooldowns.items()
            if until > time.time()
        }
    }


@app.websocket("/ws/room/{room_id}")
async def room_ws(websocket: WebSocket, room_id: str, player_id: Optional[str] = Query(None)):
    await websocket.accept()
    room = room_manager.get_or_create_room(room_id)
    room.add_websocket(websocket, player_id)

    try:
        # Send initial room state
        await websocket.send_text(json.dumps({
            "type": "init",
            "seed": room.seed,
            "game_mode": room.game_mode,
            "difficulty": room.difficulty,
            "article_difficulty": room.article_data.get("difficulty", room.difficulty),
            "article_lang_count": room.article_data.get("lang_count", 0),
            "article_pageviews_90d": room.article_data.get("pageviews_90d", int(room.article_data.get("pageviews_60d", 0) * 1.5)),
            "teams": room.get_teams_data(),
            "leaderboard": room.get_leaderboard(),
            "activity": room.recent_activity,
            "chat_messages": room.chat_messages,
            "status": room.status,
            "host_player_id": room.host_player_id,
            "can_start": room.can_start(),
            "countdown_end": room.countdown_end,
            "timer_30s_end": room.timer_30s_end,
            "first_winner_name": room.first_winner_name,
            "first_winner_attempts": room.first_winner_attempts,
            "last_round": room.last_round_results,
            "rounds_played": room.rounds_played,
            "next_word_hint_time": room.next_word_hint_time
        }))

        while True:
            raw_msg = await websocket.receive_text()
            try:
                data = json.loads(raw_msg)
                msg_type = data.get("type")
                if msg_type == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
                elif msg_type == "identify":
                    pid = data.get("player_id")
                    if pid:
                        room.identify_websocket(websocket, pid)
                elif msg_type == "chat":
                    player_id_val = data.get("player_id", "")
                    sender_name = data.get("sender_name", "Joueur")
                    text = data.get("text", "")
                    if text and text.strip():
                        msg_obj = room.add_chat_message(player_id_val, sender_name, text)
                        await room.broadcast({
                            "type": "chat_message",
                            "message": msg_obj
                        })
                elif msg_type == "spectator":
                    pid = data.get("player_id")
                    if pid and pid in room.players:
                        is_spec = data.get("is_spectator")
                        new_spec_val = room.toggle_spectator(pid, is_spec)
                        p_obj = room.players[pid]
                        await room.broadcast({
                            "type": "player_spectator_changed",
                            "player_id": pid,
                            "player_name": p_obj.name,
                            "is_spectator": new_spec_val,
                            "is_ready": p_obj.is_ready,
                            "can_start": room.can_start(),
                            "game_mode": room.game_mode,
                            "teams": room.get_teams_data(),
                            "leaderboard": room.get_leaderboard(),
                            "activity": room.recent_activity
                        })
            except Exception:
                pass

    except WebSocketDisconnect:
        await room.handle_websocket_disconnect(websocket)
    except Exception:
        await room.handle_websocket_disconnect(websocket)


# ============================================================================
# SOLO / STANDARD GAME ENDPOINTS
# ============================================================================

@app.post("/api/motus/solo/new")
async def new_motus_solo(req: MotusPlayerRequest):
    try:
        game = motus_manager.create_solo(
            req.player_id, req.player_name, req.difficulty
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record_multigame_session_start(
        f"motus:{game.game_id}", "motus", "solo", "Motus", game.difficulty
    )
    return game.to_dict()


@app.get("/api/motus/rooms")
async def list_motus_rooms(player_id: Optional[str] = Query(None)):
    return {"rooms": motus_manager.list_rooms(player_id)}


@app.get("/api/motus/solo/{game_id}")
async def get_motus_solo(game_id: str, player_id: str = Query(...)):
    try:
        return motus_manager.get_solo(game_id, player_id).to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/motus/solo/guess")
async def guess_motus_solo(req: MotusSoloGuessRequest):
    try:
        game, result = motus_manager.guess_solo(req.game_id, req.player_id, req.guess)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if game.status == "finished":
        player = game.player
        if player.score:
            increment_player_score(player.name, player.score, "motus")
        record_user_game_finish(
            player.name,
            won=player.solved,
            attempts=len(player.guesses),
            points=player.score,
            session_id=f"motus:{game.game_id}",
            mode="solo",
            title="Motus",
            duration_seconds=max(0, int(time.time() - game.created_at)),
            game_id="motus",
            difficulty=game.difficulty,
            metrics={
                "score": player.score,
                "max_attempts": MOTUS_DIFFICULTIES[game.difficulty],
            },
        )
    return {"result": result, **game.to_dict()}


@app.post("/api/motus/room/create")
async def create_motus_room(req: MotusPlayerRequest):
    try:
        room = motus_manager.create_room(
            req.player_id, req.player_name, req.difficulty
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return room.to_dict(req.player_id)


@app.post("/api/motus/room/join")
async def join_motus_room(req: MotusRoomPlayerRequest):
    try:
        room = motus_manager.join_room(req.room_id, req.player_id, req.player_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return room.to_dict(req.player_id)


@app.post("/api/motus/room/start")
async def start_motus_room(req: MotusRoomPlayerRequest):
    try:
        room = motus_manager.start_room(req.room_id, req.player_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record_multigame_session_start(
        f"motus:{room.room_id}:{room.match_number}",
        "motus",
        "multiplayer",
        "Motus",
        room.difficulty,
    )
    return room.to_dict(req.player_id)


@app.post("/api/motus/room/restart")
async def restart_motus_room(req: MotusRoomPlayerRequest):
    try:
        room = motus_manager.restart_room(req.room_id, req.player_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record_multigame_session_start(
        f"motus:{room.room_id}:{room.match_number}",
        "motus",
        "multiplayer",
        "Motus",
        room.difficulty,
    )
    return room.to_dict(req.player_id)


@app.post("/api/motus/room/guess")
async def guess_motus_room(req: MotusRoomGuessRequest):
    try:
        room, result = motus_manager.guess_room(req.room_id, req.player_id, req.guess)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if room.status == "finished" and not room.stats_recorded:
        room.stats_recorded = True
        for player in room.players.values():
            if player.is_spectator:
                continue
            if player.score:
                increment_player_score(player.name, player.score, "motus")
            record_user_game_finish(
                player.name,
                won=player.solved,
                attempts=len(player.guesses),
                points=player.score,
                session_id=f"motus:{room.room_id}:{room.match_number}",
                mode="multiplayer",
                title="Motus",
                duration_seconds=max(0, int(time.time() - (room.started_at or time.time()))),
                game_id="motus",
                difficulty=room.difficulty,
                metrics={
                    "score": player.score,
                    "max_attempts": MOTUS_DIFFICULTIES[room.difficulty],
                },
            )
    return {"result": result, **room.to_dict(req.player_id)}


@app.get("/api/motus/room/{room_id}")
async def get_motus_room(room_id: str, player_id: str = Query(...)):
    try:
        room = motus_manager.get_room(room_id, player_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return room.to_dict(player_id)


def _record_undercover_room_results(room) -> None:
    if room.status != "finished" or room.stats_recorded:
        return
    room.stats_recorded = True
    duration = max(0, int(time.time() - (room.started_at or room.created_at)))
    for player in room.players.values():
        if player.is_spectator:
            continue
        won = (
            (room.winner == "citizens" and player.role == "citizen")
            or (room.winner == "impostors" and player.role in ("undercover", "mr_white"))
            or (room.winner == "mr_white" and player.role == "mr_white")
        )
        points = 3 if won else 0
        if points:
            increment_player_score(player.name, points, "undercover")
        record_user_game_finish(
            player.name,
            won=won,
            attempts=room.round_number,
            points=points,
            session_id=f"undercover:{room.room_id}:{room.match_number}",
            mode="multiplayer",
            title="Undercover",
            duration_seconds=duration,
            game_id="undercover",
            difficulty="classique",
            metrics={
                "role": player.role or "citizen",
                "winner": room.winner or "",
                "rounds": room.round_number,
            },
        )


@app.get("/api/undercover/rooms")
async def list_undercover_rooms(player_id: Optional[str] = Query(None)):
    return {"rooms": undercover_manager.list_rooms(player_id)}


@app.post("/api/undercover/room/create")
async def create_undercover_room(req: UndercoverPlayerRequest):
    room = undercover_manager.create_room(req.player_id, req.player_name)
    return room.to_dict(req.player_id)


@app.post("/api/undercover/room/join")
async def join_undercover_room(req: UndercoverRoomPlayerRequest):
    try:
        room = undercover_manager.join_room(req.room_id, req.player_id, req.player_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return room.to_dict(req.player_id)


@app.get("/api/undercover/room/{room_id}")
async def get_undercover_room(room_id: str, player_id: str = Query(...)):
    try:
        room = undercover_manager.get_room(room_id, player_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _record_undercover_room_results(room)
    return room.to_dict(player_id)


@app.post("/api/undercover/room/start")
async def start_undercover_room(req: UndercoverRoomPlayerRequest):
    try:
        room = undercover_manager.start_room(req.room_id, req.player_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record_multigame_session_start(
        f"undercover:{room.room_id}:{room.match_number}",
        "undercover",
        "multiplayer",
        "Undercover",
        "classique",
    )
    return room.to_dict(req.player_id)


@app.post("/api/undercover/room/spoken")
async def undercover_player_spoken(req: UndercoverRoomPlayerRequest):
    try:
        room = undercover_manager.mark_spoken(req.room_id, req.player_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return room.to_dict(req.player_id)


@app.post("/api/undercover/room/voting")
async def start_undercover_voting(req: UndercoverRoomPlayerRequest):
    try:
        room = undercover_manager.start_voting(req.room_id, req.player_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return room.to_dict(req.player_id)


@app.post("/api/undercover/room/vote")
async def undercover_vote(req: UndercoverVoteRequest):
    try:
        room = undercover_manager.vote(
            req.room_id, req.player_id, req.target_player_id
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _record_undercover_room_results(room)
    return room.to_dict(req.player_id)


@app.post("/api/undercover/room/guess")
async def undercover_guess(req: UndercoverGuessRequest):
    try:
        room = undercover_manager.guess_word(req.room_id, req.player_id, req.guess)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _record_undercover_room_results(room)
    return room.to_dict(req.player_id)


@app.post("/api/undercover/room/restart")
async def restart_undercover_room(req: UndercoverRoomPlayerRequest):
    try:
        room = undercover_manager.restart_room(req.room_id, req.player_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record_multigame_session_start(
        f"undercover:{room.room_id}:{room.match_number}",
        "undercover",
        "multiplayer",
        "Undercover",
        "classique",
    )
    return room.to_dict(req.player_id)


@app.get("/api/cemantix/rooms")
async def list_cemantix_rooms(player_id: Optional[str] = Query(None)):
    return {"rooms": cemantix_manager.list_rooms(player_id)}


@app.post("/api/cemantix/solo/new")
async def new_cemantix_solo(req: CemantixPlayerRequest):
    try:
        game = cemantix_manager.create_solo(
            req.player_id, req.player_name, req.difficulty
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record_multigame_session_start(
        f"cemantix:{game.game_id}", "cemantix", "solo", "Cémantix", game.difficulty
    )
    return game.to_dict()


@app.get("/api/cemantix/solo/{game_id}")
async def get_cemantix_solo(game_id: str, player_id: str = Query(...)):
    try:
        return cemantix_manager.get_solo(game_id, player_id).to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/cemantix/solo/guess")
async def guess_cemantix_solo(req: CemantixSoloGuessRequest):
    try:
        game, result = cemantix_manager.guess_solo(req.game_id, req.player_id, req.guess)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if game.status == "finished":
        record_user_game_finish(
            game.player_name,
            won=True,
            attempts=len(game.guesses),
            session_id=f"cemantix:{game.game_id}",
            mode="solo",
            title="Cémantix",
            duration_seconds=max(0, int(time.time() - game.created_at)),
            game_id="cemantix",
            difficulty=game.difficulty,
            metrics={
                "best_similarity": max((guess["score"] for guess in game.guesses), default=0),
            },
        )
    return {"result": result, **game.to_dict()}


@app.post("/api/cemantix/solo/hint")
async def hint_cemantix_solo(req: CemantixSoloActionRequest):
    try:
        game = cemantix_manager.request_solo_hint(req.game_id, req.player_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return game.to_dict()


@app.post("/api/cemantix/solo/giveup")
async def giveup_cemantix_solo(req: CemantixSoloActionRequest):
    try:
        game = cemantix_manager.give_up_solo(req.game_id, req.player_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record_user_game_finish(
        game.player_name,
        won=False,
        attempts=len(game.guesses),
        session_id=f"cemantix:{game.game_id}",
        mode="solo",
        title="Cémantix",
        duration_seconds=max(0, int(time.time() - game.created_at)),
        game_id="cemantix",
        difficulty=game.difficulty,
        metrics={
            "best_similarity": max((guess["score"] for guess in game.guesses), default=0),
        },
    )
    return game.to_dict()


@app.post("/api/cemantix/room/create")
async def create_cemantix_room(req: CemantixPlayerRequest):
    try:
        room = cemantix_manager.create_room(
            req.player_id, req.player_name, req.difficulty
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return room.to_dict(req.player_id, time.time())


@app.post("/api/cemantix/room/join")
async def join_cemantix_room(req: CemantixRoomPlayerRequest):
    try:
        room = cemantix_manager.join_room(req.room_id, req.player_id, req.player_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return room.to_dict(req.player_id, time.time())


@app.post("/api/cemantix/room/start")
async def start_cemantix_room(req: CemantixRoomPlayerRequest):
    try:
        room = cemantix_manager.start_room(req.room_id, req.player_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record_multigame_session_start(
        f"cemantix:{room.room_id}:{room.match_number}",
        "cemantix",
        "multiplayer",
        "Cémantix",
        room.difficulty,
    )
    return room.to_dict(req.player_id, time.time())


@app.post("/api/cemantix/room/restart")
async def restart_cemantix_room(req: CemantixRoomPlayerRequest):
    try:
        room = cemantix_manager.restart_room(req.room_id, req.player_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record_multigame_session_start(
        f"cemantix:{room.room_id}:{room.match_number}",
        "cemantix",
        "multiplayer",
        "Cémantix",
        room.difficulty,
    )
    return room.to_dict(req.player_id, time.time())


def _record_cemantix_room_results(room) -> None:
    if room.status != "finished" or room.stats_recorded:
        return
    room.stats_recorded = True
    duration = max(0, int(time.time() - (room.started_at or time.time())))
    for player in room.players.values():
        if player.is_spectator:
            continue
        best_similarity = max(
            (guess["score"] for guess in player.guesses if guess.get("score") is not None),
            default=0,
        )
        record_user_game_finish(
            player.name,
            won=player.player_id == room.winner_player_id,
            attempts=len(player.guesses),
            points=0,
            session_id=f"cemantix:{room.room_id}:{room.match_number}",
            mode="multiplayer",
            title="Cémantix",
            duration_seconds=duration,
            difficulty=room.difficulty,
            metrics={"best_similarity": best_similarity, "rounds": len(player.guesses)},
            game_id="cemantix",
        )


@app.post("/api/cemantix/room/guess")
async def guess_cemantix_room(req: CemantixRoomGuessRequest):
    try:
        room, result = cemantix_manager.submit_room_guess(
            req.room_id, req.player_id, req.guess
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _record_cemantix_room_results(room)
    return {"result": result, **room.to_dict(req.player_id, time.time())}


@app.get("/api/cemantix/room/{room_id}")
async def get_cemantix_room(room_id: str, player_id: str = Query(...)):
    try:
        room = cemantix_manager.get_room(room_id, player_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _record_cemantix_room_results(room)
    return room.to_dict(player_id, time.time())


@app.get("/api/chiffrantix/rooms")
async def list_chiffrantix_rooms(player_id: Optional[str] = Query(None)):
    return {"rooms": chiffrantix_manager.list_rooms(player_id)}


@app.post("/api/chiffrantix/solo/new")
async def new_chiffrantix_solo(req: ChiffrantixPlayerRequest):
    try:
        game = chiffrantix_manager.create_solo(
            req.player_id, req.player_name, req.difficulty, req.category
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record_multigame_session_start(
        f"chiffrantix:{game.game_id}",
        "chiffrantix",
        "solo",
        game.question_item.get("answer", "Chiffrantix"),
        game.difficulty,
    )
    return game.to_dict()


@app.get("/api/chiffrantix/solo/{game_id}")
async def get_chiffrantix_solo(game_id: str, player_id: str = Query(...)):
    try:
        return chiffrantix_manager.get_solo(game_id, player_id).to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/chiffrantix/solo/guess")
async def guess_chiffrantix_solo(req: ChiffrantixSoloGuessRequest):
    try:
        game, result = chiffrantix_manager.guess_solo(
            req.game_id, req.player_id, req.guess
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if game.status == "finished":
        record_user_game_finish(
            game.player_name,
            won=True,
            attempts=game.board.attempts,
            points=1,
            session_id=f"chiffrantix:{game.game_id}",
            mode="solo",
            title=f"{game.question_item['answer']} — {game.question_item['question']}",
            duration_seconds=max(0, int(time.time() - game.created_at)),
            revealed_words=game.board.revealed_count,
            total_words=game.board.total_words,
            game_id="chiffrantix",
            difficulty=game.difficulty,
            metrics={
                "best_similarity": max(
                    (g["score"] for g in game.board.guesses_history), default=0
                ),
                "category": game.question_item.get("category", "toutes"),
            },
        )
    return {"result": result, **game.to_dict()}


@app.post("/api/chiffrantix/solo/hint")
async def hint_chiffrantix_solo(req: ChiffrantixSoloHintRequest):
    try:
        game, hint_info = chiffrantix_manager.hint_solo(req.game_id, req.player_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"hint": hint_info, **game.to_dict()}


@app.post("/api/chiffrantix/room/create")
async def create_chiffrantix_room(req: ChiffrantixPlayerRequest):
    try:
        room = chiffrantix_manager.create_room(
            req.player_id, req.player_name, req.difficulty, req.category
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return room.to_dict(req.player_id)


@app.post("/api/chiffrantix/room/join")
async def join_chiffrantix_room(req: ChiffrantixRoomPlayerRequest):
    try:
        room = chiffrantix_manager.join_room(
            req.room_id, req.player_id, req.player_name
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return room.to_dict(req.player_id)


@app.post("/api/chiffrantix/room/start")
async def start_chiffrantix_room(req: ChiffrantixRoomPlayerRequest):
    try:
        room = chiffrantix_manager.start_room(req.room_id, req.player_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record_multigame_session_start(
        f"chiffrantix:{room.room_id}:{room.match_number}",
        "chiffrantix",
        "multiplayer",
        room.question_item.get("answer", "Chiffrantix"),
        room.difficulty,
    )
    return room.to_dict(req.player_id)


@app.post("/api/chiffrantix/room/restart")
async def restart_chiffrantix_room(req: ChiffrantixRoomPlayerRequest):
    try:
        room = chiffrantix_manager.restart_room(req.room_id, req.player_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record_multigame_session_start(
        f"chiffrantix:{room.room_id}:{room.match_number}",
        "chiffrantix",
        "multiplayer",
        room.question_item.get("answer", "Chiffrantix"),
        room.difficulty,
    )
    return room.to_dict(req.player_id)


def _record_chiffrantix_room_results(room) -> None:
    if room.status != "finished" or room.stats_recorded:
        return
    room.stats_recorded = True
    duration = max(0, int(time.time() - (room.started_at or time.time())))
    for player in room.players.values():
        if player.is_spectator:
            continue
        won = player.player_id == room.winner_player_id
        best_sim = max(
            (g["score"] for g in player.board.guesses_history), default=0
        )
        record_user_game_finish(
            player.name,
            won=won,
            attempts=player.board.attempts,
            points=3 if won else 0,
            session_id=f"chiffrantix:{room.room_id}:{room.match_number}",
            mode="multiplayer",
            title=f"{room.question_item['answer']} — {room.question_item['question']}",
            duration_seconds=duration,
            revealed_words=player.board.revealed_count,
            total_words=player.board.total_words,
            difficulty=room.difficulty,
            metrics={
                "best_similarity": best_sim,
                "category": room.question_item.get("category", "toutes"),
            },
            game_id="chiffrantix",
        )


@app.post("/api/chiffrantix/room/guess")
async def guess_chiffrantix_room(req: ChiffrantixRoomGuessRequest):
    try:
        room, result = chiffrantix_manager.guess_room(
            req.room_id, req.player_id, req.guess
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _record_chiffrantix_room_results(room)
    return {"result": result, **room.to_dict(req.player_id)}


@app.get("/api/chiffrantix/room/{room_id}")
async def get_chiffrantix_room(room_id: str, player_id: str = Query(...)):
    try:
        room = chiffrantix_manager.get_room(room_id, player_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _record_chiffrantix_room_results(room)
    return room.to_dict(player_id)


@app.get("/api/battleship/rooms")
async def list_battleship_rooms(player_id: Optional[str] = Query(None)):
    return {"rooms": battleship_manager.list_rooms(player_id)}


@app.post("/api/battleship/room/create")
async def create_battleship_room(req: BattleshipPlayerRequest):
    try:
        room = battleship_manager.create_room(
            req.player_id, req.player_name, req.difficulty
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return room.to_dict(req.player_id)


@app.post("/api/battleship/room/join")
async def join_battleship_room(req: BattleshipRoomPlayerRequest):
    try:
        room = battleship_manager.join_room(req.room_id, req.player_id, req.player_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return room.to_dict(req.player_id)


@app.get("/api/battleship/room/{room_id}")
async def get_battleship_room(room_id: str, player_id: str = Query(...)):
    try:
        room = battleship_manager.get_room(room_id, player_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return room.to_dict(player_id)


def _record_sudoku_solo_result(game) -> None:
    player = game.player
    if game.status != "finished":
        return
    mistakes = 3 - player.lives
    record_user_game_finish(
        player.name,
        won=game.finish_reason == "solved",
        attempts=mistakes,
        points=player.points,
        session_id=f"sudoku:{game.game_id}",
        mode="solo",
        title="Sudoku",
        duration_seconds=max(0, int(time.time() - game.created_at)),
        game_id="sudoku",
        difficulty=game.difficulty,
        metrics={
            "mistakes": mistakes,
            "finish_reason": game.finish_reason,
            "filled_cells": sum(value != 0 for row in player.board for value in row),
        },
    )


def _record_sudoku_room_results(room) -> None:
    room.advance(time.time())
    if room.status != "finished" or room.stats_recorded:
        return
    room.stats_recorded = True
    duration = max(0, int(time.time() - (room.started_at or time.time())))
    for player in room.players.values():
        if player.is_spectator:
            continue
        mistakes = 3 - player.lives
        record_user_game_finish(
            player.name,
            won=player.rank is not None,
            attempts=mistakes,
            points=player.points,
            session_id=f"sudoku:{room.room_id}:{room.match_number}",
            mode="multiplayer",
            title="Sudoku",
            duration_seconds=duration,
            game_id="sudoku",
            difficulty=room.difficulty,
            metrics={
                "mistakes": mistakes,
                "finish_reason": room.finish_reason,
                "rank": player.rank,
            },
        )


@app.post("/api/sudoku/solo/new")
async def new_sudoku_solo(req: SudokuSoloCreateRequest):
    try:
        game = sudoku_manager.create_solo(req.player_id, req.player_name, req.difficulty)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    record_multigame_session_start(
        f"sudoku:{game.game_id}", "sudoku", "solo", "Sudoku", game.difficulty
    )
    return game.to_dict()


@app.get("/api/sudoku/solo/{game_id}")
async def get_sudoku_solo(game_id: str, player_id: str = Query(...)):
    try:
        return sudoku_manager.get_solo(game_id, player_id).to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/sudoku/solo/cell")
async def set_sudoku_solo_cell(req: SudokuSoloCellRequest):
    try:
        game = sudoku_manager.set_solo_cell(
            req.game_id, req.player_id, req.row, req.column, req.value
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _record_sudoku_solo_result(game)
    return game.to_dict()


@app.get("/api/sudoku/rooms")
async def list_sudoku_rooms(player_id: Optional[str] = Query(None)):
    return {"rooms": sudoku_manager.list_rooms(player_id)}


@app.post("/api/sudoku/room/create")
async def create_sudoku_room(req: SudokuRoomCreateRequest):
    try:
        room = sudoku_manager.create_room(req.player_id, req.player_name, req.difficulty)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return room.to_dict(req.player_id, time.time())


@app.post("/api/sudoku/room/join")
async def join_sudoku_room(req: SudokuRoomPlayerRequest):
    try:
        room = sudoku_manager.join_room(req.room_id, req.player_id, req.player_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return room.to_dict(req.player_id, time.time())


@app.post("/api/sudoku/room/start")
async def start_sudoku_room(req: SudokuRoomPlayerRequest):
    try:
        room = sudoku_manager.start_room(req.room_id, req.player_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record_multigame_session_start(
        f"sudoku:{room.room_id}:{room.match_number}",
        "sudoku",
        "multiplayer",
        "Sudoku",
        room.difficulty,
    )
    return room.to_dict(req.player_id, time.time())


@app.post("/api/sudoku/room/restart")
async def restart_sudoku_room(req: SudokuRoomPlayerRequest):
    try:
        room = sudoku_manager.restart_room(req.room_id, req.player_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return room.to_dict(req.player_id, time.time())


@app.post("/api/sudoku/room/cell")
async def set_sudoku_room_cell(req: SudokuRoomCellRequest):
    try:
        room, awarded = sudoku_manager.set_room_cell(
            req.room_id, req.player_id, req.row, req.column, req.value
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if awarded:
        increment_player_score(req.player_name, awarded, "sudoku")
    _record_sudoku_room_results(room)
    return room.to_dict(req.player_id, time.time())


@app.get("/api/sudoku/room/{room_id}")
async def get_sudoku_room(room_id: str, player_id: str = Query(...)):
    try:
        room = sudoku_manager.get_room(room_id, player_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _record_sudoku_room_results(room)
    return room.to_dict(player_id, time.time())


def _geoguessr_metrics(
    results: List[Dict[str, Any]], total_score: int, region: str, variant: str,
) -> Dict[str, Any]:
    distances = [float(result["distance_km"]) for result in results]
    return {
        "score": total_score,
        "average_distance_km": round(sum(distances) / len(distances), 1) if distances else 0,
        "best_distance_km": min(distances) if distances else None,
        "rounds": len(results),
        "perfect_rounds": sum(result["score"] == GEOGUESSR_MAX_SCORE_PER_ROUND for result in results),
        "region": region,
        "variant": variant,
    }


def _record_geoguessr_solo_result(game) -> None:
    if game.status != "finished":
        return
    duration = max(0, int(time.time() - game.created_at))
    metrics = _geoguessr_metrics(game.results, game.total_score, game.region, game.variant)
    increment_player_score(game.player_name, game.total_score, "geoguessr")
    record_user_game_finish(
        game.player_name,
        won=game.total_score >= GEOGUESSR_ROUND_COUNT * GEOGUESSR_MAX_SCORE_PER_ROUND // 2,
        attempts=len(game.results),
        points=game.total_score,
        session_id=f"geoguessr:{game.game_id}",
        mode="solo",
        title="GeoGuessr — Photos immersives" if game.variant == "panorama" else "GeoGuessr",
        duration_seconds=duration,
        game_id="geoguessr",
        difficulty=game.region,
        metrics=metrics,
    )


def _record_geoguessr_room_results(room) -> None:
    if room.status != "finished" or room.stats_recorded:
        return
    duration = max(0, int(time.time() - (room.started_at or room.created_at)))
    participants = [player for player in room.players.values() if player.results]
    best_score = max(player.total_score for player in participants)
    for player in participants:
        metrics = _geoguessr_metrics(player.results, player.total_score, room.region, room.variant)
        increment_player_score(player.name, player.total_score, "geoguessr")
        record_user_game_finish(
            player.name,
            won=player.total_score == best_score,
            attempts=len(player.results),
            points=player.total_score,
            session_id=f"geoguessr:{room.room_id}:{room.match_number}",
            mode="multiplayer",
            title="GeoGuessr — Photos immersives" if room.variant == "panorama" else "GeoGuessr",
            duration_seconds=duration,
            game_id="geoguessr",
            difficulty=room.region,
            metrics=metrics,
        )
    room.stats_recorded = True


@app.get("/api/geoguessr/config")
async def get_geoguessr_config():
    token = geoguessr_manager.mapillary_access_token
    google_browser_key = geoguessr_manager.google_maps_browser_api_key
    google_configured = bool(
        google_browser_key and geoguessr_manager.google_maps_server_api_key
    )
    try:
        google_usage = geoguessr_manager.google_usage()
    except RuntimeError:
        google_usage = GOOGLE_STREETVIEW_MONTHLY_LIMIT
    google_has_capacity = (
        google_configured
        and google_usage + GEOGUESSR_ROUND_COUNT <= GOOGLE_STREETVIEW_MONTHLY_LIMIT
    )
    return {
        "panorama_available": google_has_capacity or bool(token),
        "google_streetview_configured": google_configured,
        "google_streetview_available": google_has_capacity,
        "google_maps_browser_api_key": google_browser_key or None,
        "google_monthly_event_limit": GOOGLE_STREETVIEW_MONTHLY_LIMIT,
        "google_monthly_events_reserved": google_usage,
        "mapillary_access_token": token or None,
    }


@app.post("/api/geoguessr/panorama/authorize")
async def authorize_geoguessr_panorama_view(req: GeoGuessrPanoramaViewRequest):
    try:
        allowed = geoguessr_manager.authorize_google_view(
            req.player_id,
            game_id=req.game_id,
            room_id=req.room_id,
            navigation=req.navigation,
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "allowed": allowed,
        "google_monthly_event_limit": GOOGLE_STREETVIEW_MONTHLY_LIMIT,
    }


@app.post("/api/geoguessr/solo/new")
async def create_geoguessr_solo(req: GeoGuessrPlayerRequest):
    try:
        game = await asyncio.to_thread(
            geoguessr_manager.create_solo,
            req.player_id,
            req.player_name,
            req.region,
            req.variant,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record_multigame_session_start(
        f"geoguessr:{game.game_id}",
        "geoguessr",
        "solo",
        "GeoGuessr — Photos immersives" if game.variant == "panorama" else "GeoGuessr",
        game.region,
    )
    return game.to_dict()


@app.get("/api/geoguessr/solo/{game_id}")
async def get_geoguessr_solo(game_id: str, player_id: str = Query(...)):
    try:
        game = geoguessr_manager.get_solo(game_id, player_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return game.to_dict()


@app.post("/api/geoguessr/solo/guess")
async def guess_geoguessr_solo(req: GeoGuessrSoloGuessRequest):
    try:
        game, result = geoguessr_manager.guess_solo(
            req.game_id, req.player_id, req.latitude, req.longitude
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _record_geoguessr_solo_result(game)
    return {"result": result, **game.to_dict()}


@app.get("/api/geoguessr/rooms")
async def list_geoguessr_rooms(player_id: Optional[str] = Query(None)):
    return {"rooms": geoguessr_manager.list_rooms(player_id)}


@app.post("/api/geoguessr/room/create")
async def create_geoguessr_room(req: GeoGuessrRoomCreateRequest):
    try:
        room = await asyncio.to_thread(
            geoguessr_manager.create_room,
            req.player_id,
            req.player_name,
            req.region,
            req.variant,
            req.round_count,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return room.to_dict(req.player_id)


@app.post("/api/geoguessr/room/join")
async def join_geoguessr_room(req: GeoGuessrRoomPlayerRequest):
    try:
        room = geoguessr_manager.join_room(req.room_id, req.player_id, req.player_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return room.to_dict(req.player_id)


@app.post("/api/geoguessr/room/start")
async def start_geoguessr_room(req: GeoGuessrRoomPlayerRequest):
    try:
        room = await asyncio.to_thread(
            geoguessr_manager.start_room,
            req.room_id,
            req.player_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record_multigame_session_start(
        f"geoguessr:{room.room_id}:{room.match_number}",
        "geoguessr",
        "multiplayer",
        "GeoGuessr — Photos immersives" if room.variant == "panorama" else "GeoGuessr",
        room.region,
    )
    return room.to_dict(req.player_id)


@app.post("/api/geoguessr/room/restart")
async def restart_geoguessr_room(req: GeoGuessrRoomPlayerRequest):
    try:
        room = await asyncio.to_thread(
            geoguessr_manager.restart_room,
            req.room_id,
            req.player_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record_multigame_session_start(
        f"geoguessr:{room.room_id}:{room.match_number}",
        "geoguessr",
        "multiplayer",
        "GeoGuessr — Photos immersives" if room.variant == "panorama" else "GeoGuessr",
        room.region,
    )
    return room.to_dict(req.player_id)


@app.post("/api/geoguessr/room/guess")
async def guess_geoguessr_room(req: GeoGuessrRoomGuessRequest):
    try:
        room, result = geoguessr_manager.guess_room(
            req.room_id, req.player_id, req.latitude, req.longitude
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _record_geoguessr_room_results(room)
    return {"result": result, **room.to_dict(req.player_id)}


@app.get("/api/geoguessr/room/{room_id}")
async def get_geoguessr_room(room_id: str, player_id: str = Query(...)):
    try:
        room = geoguessr_manager.get_room(room_id, player_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _record_geoguessr_room_results(room)
    return room.to_dict(player_id)


def _record_bitoguessr_solo_result(game) -> None:
    if game.status != "finished":
        return
    correct_answers = sum(result["correct"] for result in game.results)
    increment_player_score(game.player_name, game.score, "bitoguessr")
    record_user_game_finish(
        game.player_name,
        won=correct_answers >= (len(game.results) + 1) // 2,
        attempts=len(game.results),
        points=game.score,
        session_id=f"bitoguessr:{game.game_id}",
        mode="solo",
        title="Bitoguessr",
        duration_seconds=max(0, int(time.time() - game.created_at)),
        game_id="bitoguessr",
        difficulty=game.difficulty,
        metrics={
            "score": game.score,
            "correct_answers": correct_answers,
            "rounds": len(game.results),
        },
    )


def _record_bitoguessr_room_results(room) -> None:
    if room.status != "finished" or room.stats_recorded:
        return
    best_score = max(player.score for player in room.players.values())
    duration = max(0, int(time.time() - room.created_at))
    for player in room.players.values():
        correct_answers = sum(result["correct"] for result in player.results)
        increment_player_score(player.name, player.score, "bitoguessr")
        record_user_game_finish(
            player.name,
            won=player.score == best_score,
            attempts=len(player.results),
            points=player.score,
            session_id=f"bitoguessr:{room.room_id}",
            mode="multiplayer",
            title="Bitoguessr",
            duration_seconds=duration,
            game_id="bitoguessr",
            difficulty=room.difficulty,
            metrics={
                "score": player.score,
                "correct_answers": correct_answers,
                "rounds": len(player.results),
                "players": len(room.players),
            },
        )
    room.stats_recorded = True


# ---------------------------------------------------------------------------
# Gardien du Seuil — Épreuve des 10 Sceaux (Secret Gate)
# ---------------------------------------------------------------------------

@app.get("/api/secret-gate/current")
async def get_secret_gate_current(
    player_id: str = Query(...),
    request: Request = None,
    x_auth_user: Optional[str] = Header(None),
):
    """Renvoie l'énigme active du joueur sans jamais divulguer les solutions."""
    return secret_gate_manager.get_current_state(player_id=player_id, username=x_auth_user)


@app.post("/api/secret-gate/guess")
async def post_secret_gate_guess(
    req: GateGuessRequest,
    response: Response,
    x_auth_user: Optional[str] = Header(None),
):
    """Vérifie la réponse proposée à l'énigme active."""
    is_correct, is_completed, payload = secret_gate_manager.verify_guess(
        player_id=req.player_id,
        guess=req.guess,
        username=x_auth_user,
    )
    if is_completed and payload.get("token"):
        response.set_cookie(
            key="bitoguessr_access_token",
            value=payload["token"],
            max_age=31536000,
            path="/",
            samesite="lax",
            httponly=False,
        )
    return payload


@app.post("/api/secret-gate/reset")
async def post_secret_gate_reset(
    req: GateResetRequest,
    x_auth_user: Optional[str] = Header(None),
):
    """Permet de réinitialiser la progression d'un joueur."""
    secret_gate_manager.reset_progress(player_id=req.player_id, username=x_auth_user)
    return {"status": "ok", "message": "Progression réinitialisée."}


# ---------------------------------------------------------------------------
# Bitoguessr
# ---------------------------------------------------------------------------

@app.get("/api/bitoguessr/config")
async def get_bitoguessr_config(request: Request):
    _require_bitoguessr_access(request)
    return {
        "round_count": 10,
        "max_players": 8,
        "data_source_url": BITOGUESSR_DATA_SOURCE_URL,
        "data_limitations": (
            "Compilation d'études hétérogènes, parfois avec peu de participants par pays ; "
            "les valeurs ne sont pas représentatives."
        ),
    }


@app.post("/api/bitoguessr/solo/new")
async def create_bitoguessr_solo(req: BitoguessrSoloCreateRequest, request: Request):
    _require_bitoguessr_access(request, req.player_id)
    try:
        game = bitoguessr_manager.create_solo(
            req.player_id, req.player_name, req.difficulty
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record_multigame_session_start(
        f"bitoguessr:{game.game_id}",
        "bitoguessr",
        "solo",
        "Bitoguessr",
        game.difficulty,
    )
    return game.to_dict()


@app.get("/api/bitoguessr/solo/{game_id}")
async def get_bitoguessr_solo(game_id: str, request: Request, player_id: str = Query(...)):
    _require_bitoguessr_access(request, player_id)
    try:
        game = bitoguessr_manager.get_solo(game_id, player_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return game.to_dict()


@app.post("/api/bitoguessr/solo/guess")
async def guess_bitoguessr_solo(req: BitoguessrSoloGuessRequest, request: Request):
    _require_bitoguessr_access(request, req.player_id)
    try:
        game, result = bitoguessr_manager.guess_solo(
            req.game_id, req.player_id, req.guess
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _record_bitoguessr_solo_result(game)
    return {"result": result, **game.to_dict()}


@app.post("/api/bitoguessr/solo/next")
async def next_bitoguessr_solo(req: BitoguessrSoloNextRequest, request: Request):
    _require_bitoguessr_access(request, req.player_id)
    try:
        game = bitoguessr_manager.next_solo(req.game_id, req.player_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return game.to_dict()


@app.get("/api/bitoguessr/rooms")
async def list_bitoguessr_rooms(request: Request, player_id: Optional[str] = Query(None)):
    _require_bitoguessr_access(request, player_id)
    return {"rooms": bitoguessr_manager.list_rooms(player_id)}


@app.post("/api/bitoguessr/room/create")
async def create_bitoguessr_room(req: BitoguessrRoomCreateRequest, request: Request):
    _require_bitoguessr_access(request, req.player_id)
    try:
        room = bitoguessr_manager.create_room(
            req.player_id, req.player_name, req.difficulty, req.round_count
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return room.to_dict(req.player_id)


@app.post("/api/bitoguessr/room/join")
async def join_bitoguessr_room(req: BitoguessrRoomPlayerRequest, request: Request):
    _require_bitoguessr_access(request, req.player_id)
    try:
        room = bitoguessr_manager.join_room(
            req.room_id, req.player_id, req.player_name
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return room.to_dict(req.player_id)


@app.post("/api/bitoguessr/room/start")
async def start_bitoguessr_room(req: BitoguessrRoomPlayerRequest, request: Request):
    _require_bitoguessr_access(request, req.player_id)
    try:
        room = bitoguessr_manager.start_room(req.room_id, req.player_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record_multigame_session_start(
        f"bitoguessr:{room.room_id}",
        "bitoguessr",
        "multiplayer",
        "Bitoguessr",
        room.difficulty,
    )
    return room.to_dict(req.player_id)


@app.post("/api/bitoguessr/room/guess")
async def guess_bitoguessr_room(req: BitoguessrRoomGuessRequest, request: Request):
    _require_bitoguessr_access(request, req.player_id)
    try:
        room, result = bitoguessr_manager.guess_room(
            req.room_id, req.player_id, req.guess
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _record_bitoguessr_room_results(room)
    return {"result": result, **room.to_dict(req.player_id)}


@app.post("/api/bitoguessr/room/next")
async def next_bitoguessr_room(req: BitoguessrRoomPlayerRequest, request: Request):
    _require_bitoguessr_access(request, req.player_id)
    try:
        room = bitoguessr_manager.next_room(req.room_id, req.player_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return room.to_dict(req.player_id)


@app.get("/api/bitoguessr/room/{room_id}")
async def get_bitoguessr_room(room_id: str, request: Request, player_id: str = Query(...)):
    _require_bitoguessr_access(request, player_id)
    try:
        room = bitoguessr_manager.get_room(room_id, player_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _record_bitoguessr_room_results(room)
    return room.to_dict(player_id)


@app.post("/api/battleship/room/fleet")
async def set_battleship_fleet(req: BattleshipFleetRequest):
    try:
        room = battleship_manager.set_fleet(req.room_id, req.player_id, req.fleet)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return room.to_dict(req.player_id)


@app.post("/api/battleship/room/randomize")
async def randomize_battleship_fleet(req: BattleshipRoomPlayerRequest):
    try:
        room = battleship_manager.randomize_fleet(req.room_id, req.player_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return room.to_dict(req.player_id)


@app.post("/api/battleship/room/ready")
async def ready_battleship_player(req: BattleshipReadyRequest):
    try:
        room = battleship_manager.set_ready(req.room_id, req.player_id, req.ready)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return room.to_dict(req.player_id)


@app.post("/api/battleship/room/start")
async def start_battleship_room(req: BattleshipRoomPlayerRequest):
    try:
        room = battleship_manager.start_room(req.room_id, req.player_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record_multigame_session_start(
        f"battleship:{room.room_id}:{room.match_number}",
        "battleship",
        "multiplayer",
        "Bataille navale",
        room.difficulty,
    )
    return room.to_dict(req.player_id)


@app.post("/api/battleship/room/restart")
async def restart_battleship_room(req: BattleshipRoomPlayerRequest):
    try:
        room = battleship_manager.restart_room(req.room_id, req.player_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return room.to_dict(req.player_id)


@app.post("/api/battleship/room/fire")
async def fire_battleship_shot(req: BattleshipFireRequest):
    try:
        room, result = battleship_manager.fire(req.room_id, req.player_id, req.coordinate)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if room.status == "finished" and not room.stats_recorded:
        room.stats_recorded = True
        duration = max(0, int(time.time() - (room.started_at or time.time())))
        for player in room.players.values():
            if player.is_spectator:
                continue
            attacks = player.attacks
            record_user_game_finish(
                player.name,
                won=player.player_id == room.winner_player_id,
                attempts=len(attacks),
                session_id=f"battleship:{room.room_id}:{room.match_number}",
                mode="multiplayer",
                title="Bataille navale",
                duration_seconds=duration,
                game_id="battleship",
                difficulty=room.difficulty,
                metrics={
                    "attacks": len(attacks),
                    "hits": sum(attack["hit"] for attack in attacks),
                    "ships_sunk": sum(bool(attack["sunk_ship"]) for attack in attacks),
                    "turns": room.turn_number,
                },
            )
    return {"result": result, **room.to_dict(req.player_id)}


@app.get("/api/game/new")
async def new_game(
    mode: str = Query("random"),
    query: Optional[str] = Query(None),
    difficulty: str = Query("moyen"),
    player_id: Optional[str] = Query(None),
    player_name: Optional[str] = Query(None)
):
    idents = []
    if player_id and is_valid_user_identifier(player_id):
        idents.append(player_id.strip().lower())
    if player_name and is_valid_user_identifier(player_name):
        idents.append(player_name.strip().lower())
    excluded = get_recently_played_articles(idents, days=15) if idents else None
    session = game_manager.create_game(mode=mode, query=query, difficulty=difficulty, exclude_titles=excluded)
    if idents:
        record_played_article(idents, session.title)
    state = session.get_public_state()
    state["guess_token"] = anti_bot_guard.get_or_issue_token(session.session_id)
    return state


@app.get("/api/game/state")
async def get_game_state(session_id: str = Query(...)):
    session = game_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Partie introuvable.")
    state = session.get_public_state()
    state["guess_token"] = anti_bot_guard.get_or_issue_token(session_id)
    return state


@app.post("/api/game/guess")
async def submit_guess(req: GuessRequest, request: Request):
    session = game_manager.get_session(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Partie introuvable.")

    if session.is_won:
        return {"status": "already_won", "message": "Partie déjà gagnée !"}

    client_ip = get_client_ip(request)
    identifier = req.session_id

    # 0. Détection des pièges canaris (honeypots DOM)
    if anti_bot_guard.is_honeypot_word(req.word):
        anti_bot_guard.trigger_cheat_penalty(identifier, duration=30.0)
        return {
            "status": "bot_blocked",
            "error": "Piège anti-triche activé : extraction/scraping automatisé de la page détecté.",
            "cooldown_seconds": 30,
            "penalty": True,
            "next_token": anti_bot_guard.rotate_token(identifier)
        }

    # 1. Validation de la saisie
    is_valid_word, err_msg = anti_bot_guard.validate_word(req.word)
    if not is_valid_word:
        return {
            "status": "bot_blocked",
            "error": err_msg,
            "cooldown_seconds": 1,
            "next_token": anti_bot_guard.rotate_token(identifier)
        }

    # 2. Contrôle de cadence anti-bot
    allowed, err_msg, meta = anti_bot_guard.check_rate_limit(identifier, ip=client_ip)
    if not allowed:
        return {
            "status": "bot_blocked",
            "error": err_msg,
            "cooldown_seconds": meta.get("remaining", 1),
            "penalty": meta.get("penalty", False),
            "next_token": anti_bot_guard.rotate_token(identifier)
        }

    # 3. Contrôle du jeton de sécurité séquentiel
    valid_token, tok_err, next_token = anti_bot_guard.verify_token(identifier, req.guess_token)
    if not valid_token:
        return {
            "status": "bot_blocked",
            "error": tok_err,
            "cooldown_seconds": 1,
            "next_token": next_token
        }

    result = session.submit_guess(req.word)
    result["next_token"] = next_token

    if req.player_name:
        record_user_guess_word(req.player_name, req.word)
        if result.get("is_won"):
            increment_player_score(req.player_name, 1)
            record_user_game_finish(
                req.player_name,
                won=True,
                attempts=result.get("attempt_number", 1),
                points=1,
                session_id=session.session_id,
                mode="solo",
                title=session.title,
                duration_seconds=int(time.time() - session.created_at),
                revealed_words=len(session.revealed_word_ids),
                total_words=session.total_words,
                difficulty=session.difficulty,
                metrics={"category": session.category},
            )
    return result


@app.post("/api/game/hint")
async def give_hint(req: HintRequest):
    raise HTTPException(status_code=403, detail="Les indices sont désactivés.")


# ============================================================================
# COMPTES UTILISATEURS & AUTHENTIFICATION
# ============================================================================

@app.post("/api/auth/check-username")
async def check_user_exists(req: CheckUsernameRequest):
    uname = req.username.strip()
    exists = user_exists(uname)
    return {"exists": exists, "username": uname}


@app.post("/api/auth/register")
async def register_account(req: AuthRegisterRequest):
    if req.username.strip().casefold() == "gwen" and not user_exists("Gwen"):
        raise HTTPException(status_code=403, detail="Le compte administrateur Gwen est réservé.")
    res = create_user(req.username, req.password)
    if "error" in res:
        raise HTTPException(status_code=400, detail=res["error"])
    return res


@app.post("/api/auth/login")
async def login_account(req: AuthLoginRequest):
    res = authenticate_user(req.username, req.password)
    if "error" in res:
        raise HTTPException(status_code=401, detail=res["error"])
    return res


def _verify_admin_credentials(username: str, password: str) -> bool:
    if username.strip() != "Gwen":
        return False
    result = authenticate_user(username, password)
    return result.get("status") == "ok" and result.get("username") == "Gwen"


@app.post("/api/admin/users")
async def list_users_for_admin(req: AdminUsersRequest):
    if not _verify_admin_credentials(req.admin_username, req.admin_password):
        raise HTTPException(status_code=403, detail="Accès réservé au compte administrateur Gwen.")
    try:
        return {"users": get_all_usernames()}
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/admin/reset-password")
async def admin_reset_password(req: AdminPasswordResetRequest):
    if not _verify_admin_credentials(req.admin_username, req.admin_password):
        raise HTTPException(status_code=403, detail="Accès réservé au compte administrateur Gwen.")
    if not req.target_username.strip():
        raise HTTPException(status_code=400, detail="Sélectionnez un compte utilisateur.")
    if len(req.new_password) < 3:
        raise HTTPException(status_code=400, detail="Le nouveau mot de passe doit contenir au moins 3 caractères.")
    try:
        if not reset_user_password(req.target_username, req.new_password):
            raise HTTPException(status_code=404, detail="Compte utilisateur introuvable.")
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return {"status": "ok", "username": req.target_username.strip()}


@app.get("/api/user/stats")
async def get_stats_for_user(
    username: str = Query(...),
    game_id: str = Query("pedantix"),
):
    try:
        return get_user_stats(username, game_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/stats")
async def player_stats(game_id: str = Query("pedantix")):
    try:
        return get_stats(game_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/stats/games")
async def stats_game_catalog():
    try:
        return {"games": get_game_catalog()}
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/scores")
async def leaderboard_scores(game_id: str = Query("pedantix")):
    try:
        return get_top_player_scores(game_id=game_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/game/unmask")
async def unmask_game(req: GameUnmaskRequest):
    session = game_manager.get_session(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Partie introuvable.")
    if not (session.is_won or session.is_surrendered):
        raise HTTPException(status_code=403, detail="L'article ne peut être démasqué qu'une fois la manche terminée.")
    res = session.unmask_all()
    if "error" in res:
        raise HTTPException(status_code=403, detail=res["error"])
    return res


def _record_plongee_solo_result(game) -> None:
    if game.status != "finished" or game.stats_recorded:
        return
    game.stats_recorded = True
    player = game.player
    if player.score:
        increment_player_score(player.name, player.score, "plongee")
    record_user_game_finish(
        player.name,
        won=player.score > 0,
        attempts=len(player.results),
        points=player.score,
        session_id=f"plongee:solo:{game.game_id}",
        mode="solo",
        title="Plongée",
        duration_seconds=max(0, int(time.time() - game.created_at)),
        game_id="plongee",
        difficulty="classique",
        metrics={"score": player.score, "rounds": len(player.results)},
    )


def _record_plongee_room_result(room) -> None:
    if room.status != "finished" or room.stats_recorded:
        return
    room.stats_recorded = True
    top_score = max((player.score for player in room.players.values()), default=0)
    duration = max(0, int(time.time() - room.created_at))
    for player in room.players.values():
        if player.score:
            increment_player_score(player.name, player.score, "plongee")
        record_user_game_finish(
            player.name,
            won=player.score == top_score,
            attempts=len(player.results),
            points=player.score,
            session_id=f"plongee:room:{room.room_id}",
            mode="multiplayer",
            title="Plongée",
            duration_seconds=duration,
            game_id="plongee",
            difficulty="classique",
            metrics={"score": player.score, "rounds": len(player.results)},
        )


@app.post("/api/plongee/solo/new")
async def new_plongee_solo(req: PlongeePlayerRequest):
    try:
        game = plongee_manager.create_solo(req.player_id, req.player_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record_multigame_session_start(
        f"plongee:solo:{game.game_id}", "plongee", "solo", "Plongée", "classique"
    )
    return plongee_manager.solo_state(game)


@app.get("/api/plongee/solo/{game_id}")
async def get_plongee_solo(game_id: str, player_id: str = Query(...)):
    try:
        game = plongee_manager.get_solo(game_id, player_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _record_plongee_solo_result(game)
    return plongee_manager.solo_state(game)


@app.post("/api/plongee/solo/guess")
async def guess_plongee_solo(req: PlongeeSoloGuessRequest):
    try:
        game, result = plongee_manager.guess_solo(req.game_id, req.player_id, req.answer)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"result": result, **plongee_manager.solo_state(game)}


@app.post("/api/plongee/solo/next")
async def next_plongee_solo(req: PlongeeSoloActionRequest):
    try:
        game = plongee_manager.next_solo(req.game_id, req.player_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _record_plongee_solo_result(game)
    return plongee_manager.solo_state(game)


@app.get("/api/plongee/rooms")
async def list_plongee_rooms(player_id: Optional[str] = Query(None)):
    return {"rooms": plongee_manager.list_rooms(player_id)}


@app.post("/api/plongee/room/create")
async def create_plongee_room(req: PlongeePlayerRequest):
    try:
        room = plongee_manager.create_room(req.player_id, req.player_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return plongee_manager.room_state(room, req.player_id)


@app.post("/api/plongee/room/join")
async def join_plongee_room(req: PlongeeRoomRequest):
    try:
        room = plongee_manager.join_room(req.room_id, req.player_id, req.player_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return plongee_manager.room_state(room, req.player_id)


@app.post("/api/plongee/room/start")
async def start_plongee_room(req: PlongeeRoomRequest):
    try:
        room = plongee_manager.start_room(req.room_id, req.player_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record_multigame_session_start(
        f"plongee:room:{room.room_id}", "plongee", "multiplayer", "Plongée", "classique"
    )
    return plongee_manager.room_state(room, req.player_id)


@app.post("/api/plongee/room/guess")
async def guess_plongee_room(req: PlongeeRoomGuessRequest):
    try:
        room = plongee_manager.guess_room(req.room_id, req.player_id, req.answer)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return plongee_manager.room_state(room, req.player_id)


@app.post("/api/plongee/room/next")
async def next_plongee_room(req: PlongeeRoomRequest):
    try:
        room = plongee_manager.next_room(req.room_id, req.player_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _record_plongee_room_result(room)
    return plongee_manager.room_state(room, req.player_id)


@app.get("/api/plongee/room/{room_id}")
async def get_plongee_room(room_id: str, player_id: str = Query(...)):
    try:
        room = plongee_manager.get_room(room_id, player_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return plongee_manager.room_state(room, player_id)
