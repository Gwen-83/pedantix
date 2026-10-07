import os
import sys
import json
import socket
import time
import datetime
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import random

from app.database import (
    init_db,
    get_stats,
    get_player_score,
    increment_player_score,
    get_top_player_scores,
    get_db_status,
)
from app.game import GameManager
from app.room import room_manager
from app.network import get_primary_lan_ip, get_all_lan_ips
from app.tunnel import tunnel_manager

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"https://.*\.netlify\.app|http://localhost(:\d+)?|http://127\.0\.0\.1(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize database on startup
init_db()

# Game manager instance
game_manager = GameManager()

# Static files directory
STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if not os.path.exists(STATIC_DIR):
    os.makedirs(STATIC_DIR)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def detect_lan_ip() -> str:
    return get_primary_lan_ip()


# Pydantic schemas
class GuessRequest(BaseModel):
    session_id: str
    word: str

class HintRequest(BaseModel):
    session_id: str
    hint_type: str = "shortest"

class RoomCreateRequest(BaseModel):
    host_player_id: str
    room_id: Optional[str] = None

class RoomJoinRequest(BaseModel):
    room_id: str = "default"
    player_id: str
    player_name: str

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

class RoomGuessRequest(BaseModel):
    room_id: str = "default"
    player_id: str
    word: str

class RoomNewRoundRequest(BaseModel):
    room_id: str = "default"

class RoomUnmaskRequest(BaseModel):
    room_id: str = "default"
    player_id: str

class GameUnmaskRequest(BaseModel):
    session_id: str

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


@app.get("/")
async def root():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Pédantix Local API opérationnelle."}


@app.get("/health")
async def health_check():
    db_status = get_db_status()
    return {
        "status": "ok",
        "timestamp": time.time(),
        "database": db_status["active_type"],
        "database_details": db_status,
    }


@app.get("/api/rooms")
async def list_active_rooms():
    return {"rooms": room_manager.list_active_rooms()}


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
    room = room_manager.create_new_room(req.host_player_id, req.room_id)
    return {
        "room_id": room.room_id,
        "host_player_id": room.host_player_id,
        "status": room.status,
        "seed": room.seed
    }


@app.post("/api/room/join")
async def join_room(req: RoomJoinRequest):
    room = room_manager.get_or_create_room(req.room_id)
    player = room.get_or_create_player(req.player_id, req.player_name)

    # Broadcast player joined to all active websockets in this room
    await room.broadcast({
        "type": "player_joined",
        "player": player.to_dict(),
        "game_mode": room.game_mode,
        "teams": room.get_teams_data(),
        "leaderboard": room.get_leaderboard(),
        "activity": room.recent_activity,
        "status": room.status,
        "host_player_id": room.host_player_id,
        "can_start": room.can_start()
    })

    active_session = room.team_sessions.get(player.team, player.session) if room.game_mode == "team" and room.team_sessions else player.session
    return {
        "room_id": room.room_id,
        "seed": room.seed,
        "game_mode": room.game_mode,
        "player": player.to_dict(),
        "teams": room.get_teams_data(),
        "leaderboard": room.get_leaderboard(),
        "session": active_session.get_public_state(revealed_letters=room.revealed_letters),
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
        "revealed_letters": room.revealed_letters,
        "next_letter_hint_time": room.next_letter_hint_time
    }


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


@app.post("/api/room/next-round")
async def next_round_room(req: RoomNextRoundRequest):
    room = room_manager.get_or_create_room(req.room_id)
    new_article = room_manager._fetch_random_article()
    seed_num = random.randint(1000, 9999)
    new_seed = f"P-{seed_num}"
    res = await room.start_new_round(req.player_id, new_article, new_seed)
    if "error" in res:
        raise HTTPException(status_code=400, detail=res["error"])
    return res


@app.post("/api/room/guess")
async def room_guess(req: RoomGuessRequest):
    room = room_manager.get_or_create_room(req.room_id)
    player = room.players.get(req.player_id)
    if not player:
        raise HTTPException(status_code=404, detail="Joueur introuvable dans la salle.")

    res = room.process_guess(req.player_id, req.word)
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
        } if room.game_mode == "team" else None
    })

    return res


@app.post("/api/room/unmask")
async def unmask_room(req: RoomUnmaskRequest):
    room = room_manager.get_or_create_room(req.room_id)
    res = room.unmask_player(req.player_id)
    if "error" in res:
        raise HTTPException(status_code=404, detail=res["error"])
    return res


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
    if player_id and player_id in room.players:
        p = room.players[player_id]
        player_data = p.to_dict()
        if room.game_mode == "team":
            team_sess = room.team_sessions.get(p.team, p.session)
            session_data = team_sess.get_public_state(revealed_letters=room.revealed_letters)
        else:
            session_data = p.session.get_public_state(revealed_letters=room.revealed_letters)

    return {
        "room_id": room.room_id,
        "seed": room.seed,
        "status": room.status,
        "game_mode": room.game_mode,
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
        "revealed_letters": room.revealed_letters,
        "next_letter_hint_time": room.next_letter_hint_time
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
            "revealed_letters": room.revealed_letters,
            "next_letter_hint_time": room.next_letter_hint_time
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
            except Exception:
                pass

    except WebSocketDisconnect:
        room.remove_websocket(websocket)
    except Exception:
        room.remove_websocket(websocket)


# ============================================================================
# SOLO / STANDARD GAME ENDPOINTS
# ============================================================================

@app.get("/api/game/new")
async def new_game(
    mode: str = Query("random"),
    query: Optional[str] = Query(None)
):
    session = game_manager.create_game(mode=mode, query=query)
    return session.get_public_state()


@app.get("/api/game/state")
async def get_game_state(session_id: str = Query(...)):
    session = game_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Partie introuvable.")
    return session.get_public_state()


@app.post("/api/game/guess")
async def submit_guess(req: GuessRequest):
    session = game_manager.get_session(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Partie introuvable.")

    if session.is_won:
        return {"status": "already_won", "message": "Partie déjà gagnée !"}

    result = session.submit_guess(req.word)
    return result


@app.post("/api/game/hint")
async def give_hint(req: HintRequest):
    raise HTTPException(status_code=403, detail="Les indices sont désactivés.")


@app.get("/api/stats")
async def player_stats():
    return get_stats()


@app.get("/api/scores")
async def leaderboard_scores():
    return get_top_player_scores()


@app.post("/api/game/unmask")
async def unmask_game(req: GameUnmaskRequest):
    session = game_manager.get_session(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Partie introuvable.")
    return session.unmask_all()
