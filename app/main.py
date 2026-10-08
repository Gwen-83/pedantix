import os
import sys
import json
import socket
import time
import math
import datetime
import asyncio
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect, Request
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
    user_exists,
    create_user,
    authenticate_user,
    record_user_guess_word,
    record_user_game_finish,
    get_user_stats,
)
from app.game import GameManager
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"https://.*\.netlify\.app|http://localhost(:\d+)?|http://127\.0\.0\.1(:\d+)?",
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
        "frame-src 'none'; "
        "object-src 'none'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com data:; "
        "img-src 'self' data: https://upload.wikimedia.org https://*.wikimedia.org https://*.wikipedia.org; "
        "connect-src 'self' ws: wss:;"
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

class AuthRegisterRequest(BaseModel):
    username: str
    password: str

class AuthLoginRequest(BaseModel):
    username: str
    password: str

class HintRequest(BaseModel):
    session_id: str
    hint_type: str = "shortest"

class RoomCreateRequest(BaseModel):
    host_player_id: str
    room_id: Optional[str] = None
    difficulty: Optional[str] = "moyen"

class RoomJoinRequest(BaseModel):
    room_id: str = "default"
    player_id: str
    player_name: str
    difficulty: Optional[str] = None

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
    room = await room_manager.create_new_room_async(req.host_player_id, req.room_id, difficulty=req.difficulty or "moyen")
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
    room = room_manager.get_or_create_room(req.room_id, difficulty=diff)
    if req.room_id.startswith("solo-") and req.difficulty and req.difficulty != room.difficulty:
        room.set_difficulty(req.difficulty)
    player = room.get_or_create_player(req.player_id, req.player_name)

    # Broadcast player joined to all active websockets in this room
    await room.broadcast({
        "type": "player_joined",
        "player": player.to_dict(),
        "game_mode": room.game_mode,
        "difficulty": room.difficulty,
        "teams": room.get_teams_data(),
        "leaderboard": room.get_leaderboard(),
        "activity": room.recent_activity,
        "status": room.status,
        "host_player_id": room.host_player_id,
        "can_start": room.can_start()
    })

    active_session = room.team_sessions.get(player.team, player.session) if room.game_mode == "team" and room.team_sessions else player.session
    guess_token = anti_bot_guard.get_or_issue_token(f"{room.room_id}:{player.player_id}")
    return {
        "room_id": room.room_id,
        "seed": room.seed,
        "guess_token": guess_token,
        "game_mode": room.game_mode,
        "difficulty": room.difficulty,
        "article_difficulty": room.article_data.get("difficulty", room.difficulty),
        "article_lang_count": room.article_data.get("lang_count", 0),
        "article_pageviews_90d": room.article_data.get("pageviews_90d", int(room.article_data.get("pageviews_60d", 0) * 1.5)),
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
        "next_letter_hint_time": room.next_letter_hint_time,
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
    if req.difficulty not in ("facile", "moyen", "difficile"):
        raise HTTPException(status_code=400, detail="Difficulté invalide.")
    success = room.set_difficulty(req.difficulty)
    if not success:
        raise HTTPException(status_code=400, detail="Impossible de modifier la difficulté.")
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
        "article_difficulty": room.article_data.get("difficulty", room.difficulty)
    }


@app.post("/api/room/next-round")
async def next_round_room(req: RoomNextRoundRequest):
    room = room_manager.get_or_create_room(req.room_id)
    if req.difficulty and req.difficulty in ("facile", "moyen", "difficile"):
        room.set_difficulty(req.difficulty)
    new_article = await asyncio.to_thread(room_manager._fetch_random_article, room.difficulty)
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

    if player and player.name and res.get("is_won"):
        record_user_game_finish(player.name, won=True, attempts=res.get("attempt_number", player.attempts))

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
        status_code = 403 if "manche terminée" in res["error"] else 404
        raise HTTPException(status_code=status_code, detail=res["error"])
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
            session_data = team_sess.get_public_state(revealed_letters=room.revealed_letters)
        else:
            session_data = p.session.get_public_state(revealed_letters=room.revealed_letters)

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
        "revealed_letters": room.revealed_letters,
        "next_letter_hint_time": room.next_letter_hint_time,
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

@app.get("/api/game/new")
async def new_game(
    mode: str = Query("random"),
    query: Optional[str] = Query(None),
    difficulty: str = Query("moyen")
):
    session = game_manager.create_game(mode=mode, query=query, difficulty=difficulty)
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
            record_user_game_finish(req.player_name, won=True, attempts=result.get("attempt_number", 1), points=1)
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


@app.get("/api/user/stats")
async def get_stats_for_user(username: str = Query(...)):
    return get_user_stats(username)


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
    if not (session.is_won or session.is_surrendered):
        raise HTTPException(status_code=403, detail="L'article ne peut être démasqué qu'une fois la manche terminée.")
    res = session.unmask_all()
    if "error" in res:
        raise HTTPException(status_code=403, detail=res["error"])
    return res
