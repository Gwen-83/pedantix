import asyncio
import json
import threading
import logging
import random
import time
import math
import uuid
from typing import Dict, List, Optional, Set, Any
from fastapi import WebSocket

from app.game import GameSession, GameManager
from app.wiki import (
    ALL_CURATED_TITLES,
    CURATED_BY_DIFFICULTY,
    WikipediaClient,
    article_matches_difficulty,
)
from app.database import (
    get_player_score, increment_player_score, record_game_finish, record_user_game_finish, record_user_guess_word,
    record_played_article, get_recently_played_articles, is_valid_user_identifier,
    get_random_cached_article, cache_article
)
from app.nlp import normalize_wiki_title

logger = logging.getLogger("pedantix.room")

TEAM_METADATA = {
    "blue": {"name": "Équipe Bleue", "short": "Bleue", "icon": "🔵", "color": "#3b82f6"},
    "red": {"name": "Équipe Rouge", "short": "Rouge", "icon": "🔴", "color": "#ef4444"},
    "green": {"name": "Équipe Verte", "short": "Verte", "icon": "🟢", "color": "#10b981"},
    "yellow": {"name": "Équipe Jaune", "short": "Jaune", "icon": "🟡", "color": "#eab308"},
}
ALL_TEAMS = ["blue", "red", "green", "yellow"]
PLAYER_DISCONNECT_GRACE_SECONDS = 60.0

class RoomPlayer:
    def __init__(self, player_id: str, name: str, session: GameSession, is_host: bool = False, team: str = "blue"):
        self.player_id = player_id
        self.name = name
        self.session = session
        self.is_host = is_host
        self.team = team  # "blue", "red", "green", or "yellow"
        self.is_ready = False
        self.score = get_player_score(name)
        self.attempts = 0
        self.revealed_words_count = 0
        self.total_words = session.total_words
        self.pct = 0
        self.is_won = False
        self.won_at: Optional[float] = None
        self.last_word: Optional[str] = None
        self.last_status: Optional[str] = None
        self.last_count: int = 0
        self.last_score: int = 0
        self.connected = True
        self.disconnected_at: Optional[float] = None
        self.is_spectator = False
        self.waiting_for_next_round = False

    def refresh_score(self):
        self.score = get_player_score(self.name)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "player_id": self.player_id,
            "name": self.name,
            "is_host": self.is_host,
            "team": self.team,
            "is_ready": self.is_ready,
            "is_spectator": self.is_spectator,
            "waiting_for_next_round": self.waiting_for_next_round,
            "score": self.score,
            "attempts": self.attempts,
            "revealed_words_count": self.revealed_words_count,
            "total_words": self.total_words,
            "pct": self.pct,
            "is_won": self.is_won,
            "won_at": self.won_at,
            "last_status": self.last_status,
            "last_count": self.last_count,
            "last_score": self.last_score,
            "connected": self.connected,
            "disconnected_at": self.disconnected_at
        }


class Room:
    def __init__(self, room_id: str, article_data: Dict[str, Any], seed: str, difficulty: str = "moyen"):
        self.room_id = room_id
        self.session_mode = "solo" if room_id.startswith("solo-") else "multiplayer"
        self.article_data = article_data
        self.seed = seed
        self.difficulty: str = difficulty or article_data.get("difficulty", "moyen")
        self.created_at = time.time()
        self.players: Dict[str, RoomPlayer] = {}
        self.websockets: Set[WebSocket] = set()
        self.ws_player_map: Dict[WebSocket, str] = {}
        self.host_player_id: Optional[str] = None
        self.status: str = "playing" if room_id.startswith("solo-") else "lobby"  # "lobby", "starting", "playing", "ending"
        self.countdown_end: Optional[float] = None
        self.timer_30s_end: Optional[float] = None
        self.first_winner_id: Optional[str] = None
        self.first_winner_name: Optional[str] = None
        self.first_winner_attempts: Optional[int] = None
        self.winners: List[str] = []
        self.rounds_played: int = 0
        self.last_round_results: Optional[Dict[str, Any]] = None
        self.recent_activity: List[Dict[str, Any]] = []
        self.chat_messages: List[Dict[str, Any]] = []
        self.game_mode: str = "individual"  # "individual" or "team"
        self.team_sessions: Dict[str, GameSession] = {}
        self.assist_token = uuid.uuid4().hex
        self.assisting_player_id: Optional[str] = None
        self.winning_team: Optional[str] = None
        self._countdown_task: Optional[asyncio.Task] = None
        self._timer_30s_task: Optional[asyncio.Task] = None
        self.hinted_word_ids: Set[int] = set()
        self._word_hint_task: Optional[asyncio.Task] = None
        self.word_hint_initial_delay: float = 300.0
        self.word_hint_interval: float = 90.0
        self.next_word_hint_time: Optional[float] = None
        self.surrender_in_progress: bool = False
        self.surrender_initiator_id: Optional[str] = None
        self.surrender_initiator_name: Optional[str] = None
        self.surrender_votes: Set[str] = set()
        self.surrender_cooldowns: Dict[str, float] = {}
        self._disconnect_tasks: Dict[str, asyncio.Task] = {}

    @property
    def is_cooperative_solo(self) -> bool:
        return self.room_id.startswith("solo-") and self.assisting_player_id is not None

    def get_all_player_identifiers(self) -> List[str]:
        """Collecte tous les identifiants uniques des joueurs de la salle (player_id et pseudonymes valides)."""
        idents: Set[str] = set()
        for p in self.players.values():
            if p.player_id:
                idents.add(p.player_id.strip().lower())
            if p.name:
                clean_name = p.name.strip().lower()
                if clean_name and not clean_name.startswith("joueur ") and clean_name not in ("host", "anonyme", "spectateur"):
                    idents.add(clean_name)
        if not idents and self.room_id.startswith("solo-"):
            idents.add(self.room_id[5:].strip().lower())
        return list(idents)

    def get_recently_played_titles(self, days: int = 21) -> Set[str]:
        """Retourne les articles apparus à l'un des joueurs du salon durant la période donnée."""
        idents = self.get_all_player_identifiers()
        return get_recently_played_articles(idents, days=days)

    def record_current_article_for_players(self, player_ids: Optional[List[str]] = None):
        """Enregistre l'article actuel pour tous les joueurs du salon (ou les IDs spécifiés)."""
        title = self.article_data.get("title")
        if not title:
            return
        if player_ids:
            idents = list({pid.strip().lower() for pid in player_ids if is_valid_user_identifier(pid)})
        else:
            idents = self.get_all_player_identifiers()
        if idents:
            record_played_article(idents, title)

    def _get_word_hint_sessions(self) -> List[GameSession]:
        if self.game_mode == "team":
            active_teams = {
                player.team for player in self.players.values()
                if not player.is_spectator
            }
            sessions = [
                self.team_sessions[team]
                for team in active_teams
                if team in self.team_sessions
            ]
        else:
            sessions = [
                player.session for player in self.players.values()
                if not player.is_spectator
            ]
        return list({session.session_id: session for session in sessions}.values())

    def _pick_next_hint_word_id(self) -> Optional[int]:
        sessions = self._get_word_hint_sessions()
        if not sessions:
            return None

        available_ids: Optional[Set[int]] = None
        for session in sessions:
            title_word_ids = set(getattr(session, "title_word_ids", ()))
            title_words = set()
            for token in session.tokens:
                if token.get("is_word") and (
                    token.get("is_title") or token.get("id") in title_word_ids
                ):
                    title_word = normalize_wiki_title(
                        token.get("normalized") or token.get("text", "")
                    )
                    if title_word:
                        title_words.add(title_word)
            hidden_word_ids = {
                token["id"] for token in session.tokens
                if token.get("is_word")
                and not token.get("is_title")
                and not token.get("revealed")
                and token["id"] not in self.hinted_word_ids
                and normalize_wiki_title(token.get("normalized") or token.get("text", "")) not in title_words
            }
            available_ids = (
                hidden_word_ids if available_ids is None
                else available_ids & hidden_word_ids
            )

        candidates = sorted(available_ids or set())
        return random.choice(candidates) if candidates else None

    def start_word_hint_timer(self):
        if self.status != "playing":
            return
        if self._word_hint_task and not self._word_hint_task.done():
            if not self._word_hint_task.cancelling():
                return
        if self.next_word_hint_time is None:
            self.next_word_hint_time = time.time() + self.word_hint_initial_delay
        self._word_hint_task = asyncio.create_task(self._run_word_hint_loop())

    async def _run_word_hint_loop(self):
        try:
            while self.status == "playing" and not self.first_winner_id:
                delay = max(0.0, (self.next_word_hint_time or time.time()) - time.time())
                await asyncio.sleep(delay)
                if self.status != "playing" or self.first_winner_id:
                    break

                token_id = self._pick_next_hint_word_id()
                if token_id is None:
                    self.next_word_hint_time = None
                    await self.broadcast({"type": "word_hint_unavailable"})
                    break

                sessions = self._get_word_hint_sessions()
                if not sessions:
                    self.next_word_hint_time = None
                    await self.broadcast({"type": "word_hint_unavailable"})
                    break
                word = sessions[0].tokens_by_id[token_id].get("text", "")
                self.hinted_word_ids.add(token_id)
                self.next_word_hint_time = time.time() + self.word_hint_interval
                hint_msg = f"💡 Indice : le mot « {word} » a été dévoilé !"
                self.add_activity(hint_msg, "hint")

                await self.broadcast({
                    "type": "word_hint",
                    "token_id": token_id,
                    "word": word,
                    "next_word_hint_time": self.next_word_hint_time,
                    "message": hint_msg
                })
        except asyncio.CancelledError:
            pass

    def _init_team_sessions(self):
        """Initializes separate shared sessions for blue, red, green, and yellow teams."""
        for team in ALL_TEAMS:
            session_id = str(uuid.uuid4())
            self.team_sessions[team] = GameSession(
                session_id=session_id,
                seed=self.seed,
                title=self.article_data["title"],
                url=self.article_data.get("url", f"https://fr.wikipedia.org/wiki/{self.article_data['title']}"),
                image=self.article_data.get("image", ""),
                paragraphs=self.article_data["paragraphs"],
                mode="team",
                category=self.article_data.get("category", "general"),
                difficulty=self.difficulty,
                lang_count=self.article_data.get("lang_count", 0),
                pageviews_90d=self.article_data.get("pageviews_90d", int(self.article_data.get("pageviews_60d", 0) * 1.5))
            )

    def get_teams_data(self) -> Dict[str, Any]:
        """Returns stats and rosters for all 4 teams (blue, red, green, yellow)."""
        first_p = next(iter(self.players.values()), None)
        default_tot = first_p.total_words if first_p else 1

        teams_dict = {}
        for team_key in ALL_TEAMS:
            team_meta = TEAM_METADATA[team_key]
            team_players = [p.to_dict() for p in self.players.values() if p.team == team_key]
            sess = self.team_sessions.get(team_key)

            revealed = len(sess.revealed_word_ids) if sess else 0
            total = sess.total_words if sess else default_tot
            pct = round((revealed / max(1, total)) * 100)
            attempts = sess.attempts if sess else 0
            won = sess.is_won if sess else False

            teams_dict[team_key] = {
                "name": team_meta["name"],
                "color": team_meta["color"],
                "icon": team_meta["icon"],
                "players": team_players,
                "players_count": len(team_players),
                "attempts": attempts,
                "revealed_words_count": revealed,
                "total_words": total,
                "pct": pct,
                "is_won": won
            }
        return teams_dict

    def set_game_mode(self, mode: str) -> bool:
        if mode not in ("individual", "team"):
            return False
        if self.status != "lobby":
            return False
        self.game_mode = mode
        if mode == "team":
            if not self.team_sessions:
                self._init_team_sessions()
            for p in self.players.values():
                if p.team in self.team_sessions:
                    p.session = self.team_sessions[p.team]
        mode_str = "Par Équipes (Bleu, Rouge, Vert, Jaune) 👥" if mode == "team" else "Chacun pour soi (Individuel) 👤"
        self.add_activity(f"🎮 Mode de jeu configuré : {mode_str}", "mode_change")
        return True

    def set_player_team(self, player_id: str, team: str) -> bool:
        if player_id not in self.players:
            return False
        if team not in ALL_TEAMS:
            return False
        player = self.players[player_id]
        if player.team == team:
            if self.game_mode == "team" and team in self.team_sessions:
                player.session = self.team_sessions[team]
            return True
        player.team = team
        if self.game_mode == "team" and team in self.team_sessions:
            player.session = self.team_sessions[team]
        meta = TEAM_METADATA.get(team, {})
        team_name = f"{meta.get('name', team)} {meta.get('icon', '')}"
        self.add_activity(f"👕 {player.name} a rejoint l'{team_name}", "team_change")
        return True

    def set_difficulty(self, difficulty: str, new_article: Optional[Dict[str, Any]] = None) -> bool:
        if difficulty not in ("facile", "moyen", "difficile"):
            return False

        # In multiplayer, cannot change difficulty once game has started
        if not self.room_id.startswith("solo-") and self.status != "lobby":
            return False

        # In multiplayer lobby, if difficulty is already set to this and article matches, nothing to do
        if not self.room_id.startswith("solo-") and self.difficulty == difficulty and self.article_data.get("difficulty") == difficulty:
            return True

        self.difficulty = difficulty

        if self.room_id.startswith("solo-"):
            # Solo mode: immediately load a fresh article with the requested difficulty
            try:
                excluded = self.get_recently_played_titles(days=21)
                new_art = new_article or room_manager._fetch_random_article(difficulty=difficulty, exclude_titles=excluded)
                if new_art:
                    new_art["difficulty"] = difficulty
                    self.article_data = new_art
                    self.seed = f"P-{random.randint(1000, 9999)}"
                    self.status = "playing"
                    self.winners = []
                    self.first_winner_id = None
                    self.first_winner_name = None
                    self.first_winner_attempts = None
                    self.surrender_in_progress = False
                    self.surrender_initiator_id = None
                    self.surrender_initiator_name = None
                    self.surrender_votes = set()
                    self.surrender_cooldowns.clear()
                    self.hinted_word_ids.clear()
                    self.next_word_hint_time = None
                    if self._word_hint_task and not self._word_hint_task.done():
                        self._word_hint_task.cancel()

                    for p in self.players.values():
                        session_id = str(uuid.uuid4())
                        p.session = GameSession(
                            session_id=session_id,
                            seed=self.seed,
                            title=self.article_data["title"],
                            url=self.article_data.get("url", ""),
                            image=self.article_data.get("image", ""),
                            paragraphs=self.article_data["paragraphs"],
                            mode=self.session_mode,
                            category=self.article_data.get("category", "general"),
                            difficulty=self.difficulty,
                            lang_count=self.article_data.get("lang_count", 0),
                            pageviews_90d=self.article_data.get("pageviews_90d", int(self.article_data.get("pageviews_60d", 0) * 1.5))
                        )
                        p.attempts = 0
                        p.revealed_words_count = 0
                        p.total_words = p.session.total_words
                        p.pct = 0
                        p.is_won = False
                        p.won_at = None
                        p.last_word = None
                        p.last_status = None
                        p.last_count = 0
                        p.is_ready = True
                    self.record_current_article_for_players()
            except Exception as e:
                logger.error(f"Error updating solo article on difficulty change: {e}")

        elif self.status == "lobby":
            # Multiplayer lobby: pre-fetch/update article for the new difficulty
            try:
                excluded = self.get_recently_played_titles(days=21)
                new_art = new_article or room_manager._fetch_random_article(difficulty=difficulty, exclude_titles=excluded)
                if new_art:
                    new_art["difficulty"] = difficulty
                    self.article_data = new_art
                    self.seed = f"P-{random.randint(1000, 9999)}"
                    if self.game_mode == "team":
                        self._init_team_sessions()
                        for p in self.players.values():
                            p.session = self.team_sessions.get(p.team)
                            p.attempts = 0
                            p.revealed_words_count = 0
                            p.total_words = p.session.total_words if p.session else 0
                            p.pct = 0
                            p.is_won = False
                            p.won_at = None
                            p.last_word = None
                            p.last_status = None
                            p.last_count = 0
                    else:
                        for p in self.players.values():
                            session_id = str(uuid.uuid4())
                            p.session = GameSession(
                                session_id=session_id,
                                seed=self.seed,
                                title=self.article_data["title"],
                                url=self.article_data.get("url", ""),
                                image=self.article_data.get("image", ""),
                                paragraphs=self.article_data["paragraphs"],
                                mode=self.session_mode,
                                category=self.article_data.get("category", "general"),
                                difficulty=self.difficulty,
                                lang_count=self.article_data.get("lang_count", 0),
                                pageviews_90d=self.article_data.get("pageviews_90d", int(self.article_data.get("pageviews_60d", 0) * 1.5))
                            )
                            p.attempts = 0
                            p.revealed_words_count = 0
                            p.total_words = p.session.total_words
                            p.pct = 0
                            p.is_won = False
                            p.won_at = None
                            p.last_word = None
                            p.last_status = None
                            p.last_count = 0
            except Exception as e:
                logger.error(f"Error updating lobby article on difficulty change: {e}")

        diff_label = {"facile": "🟢 Facile", "moyen": "🟡 Moyen", "difficile": "🔴 Difficile"}.get(difficulty, difficulty.capitalize())
        self.add_activity(f"🎯 Difficulté configurée : {diff_label}", "difficulty")
        return True

    def get_leaderboard(self) -> List[Dict[str, Any]]:
        """Returns players sorted by victory status, then highest percentage, then lowest attempts, then DB score.
        Ensures any player with an active websocket is marked as connected."""
        active_ws_pids = set(self.ws_player_map.values())
        for p in self.players.values():
            if p.player_id in active_ws_pids:
                p.connected = True

        player_list = [p.to_dict() for p in self.players.values()]

        def sort_key(p):
            is_active_player = 0 if p.get("is_spectator") else 1
            is_won = 1 if p["is_won"] else 0
            pct = p["pct"]
            attempts = -p["attempts"] if p["attempts"] > 0 else -9999
            score = p["score"]
            return (is_active_player, is_won, pct, attempts, score)

        player_list.sort(key=sort_key, reverse=True)
        return player_list

    def can_start(self) -> bool:
        """Returns True if there is at least one active player and all active players are ready."""
        if self.room_id.startswith("solo-"):
            return True
        active_players = [p for p in self.players.values() if not p.is_spectator and p.connected]
        if not active_players:
            return False
        if not all(p.is_ready for p in active_players):
            return False
        if self.game_mode == "team" and len(active_players) >= 2:
            occupied_teams = set(p.team for p in active_players)
            if len(occupied_teams) < 2:
                return False
        return True

    def toggle_spectator(self, player_id: str, is_spectator: Optional[bool] = None) -> bool:
        """Toggles or sets the spectator mode for a player."""
        if player_id not in self.players:
            return False
        player = self.players[player_id]
        if player.waiting_for_next_round and self.status != "lobby":
            return True
        if is_spectator is None:
            player.is_spectator = not player.is_spectator
        else:
            player.is_spectator = bool(is_spectator)
        if player.is_spectator:
            player.is_ready = False
            self.add_activity(f"👁️ {player.name} est passé en mode Spectateur (en pause)", "spectator")
            if self.surrender_in_progress:
                connected_pids = {p.player_id for p in self.players.values() if p.connected and not p.is_spectator}
                if connected_pids and self.surrender_votes >= connected_pids:
                    asyncio.create_task(self.execute_surrender())
        else:
            self.add_activity(f"🎮 {player.name} a repris sa place de joueur !", "spectator")
        return player.is_spectator

    def activate_waiting_players(self) -> List[str]:
        """Promote players who joined during a round once the room returns to its lobby."""
        promoted = []
        for player in self.players.values():
            if getattr(player, "waiting_for_next_round", False):
                player.waiting_for_next_round = False
                player.is_spectator = False
                player.is_ready = False
                promoted.append(player.player_id)
                self.add_activity(
                    f"🎮 {player.name} peut rejoindre la prochaine partie !",
                    "spectator",
                )
        return promoted

    def add_activity(self, text: str, event_type: str = "info"):
        event = {
            "id": str(uuid.uuid4())[:8],
            "text": text,
            "type": event_type,
            "timestamp": time.strftime("%H:%M:%S")
        }
        self.recent_activity.insert(0, event)
        if len(self.recent_activity) > 25:
            self.recent_activity.pop()

    def add_chat_message(self, player_id: str, sender_name: str, text: str) -> Dict[str, Any]:
        clean_text = text.strip() if text else ""
        if not clean_text:
            return {}
        if len(clean_text) > 400:
            clean_text = clean_text[:400]
        msg = {
            "id": str(uuid.uuid4())[:8],
            "player_id": player_id,
            "sender_name": sender_name or "Joueur",
            "text": clean_text,
            "timestamp": time.strftime("%H:%M"),
            "type": "chat"
        }
        self.chat_messages.append(msg)
        if len(self.chat_messages) > 100:
            self.chat_messages.pop(0)
        return msg

    def get_or_create_player(self, player_id: str, player_name: str) -> RoomPlayer:
        if player_id in self.players:
            player = self.players[player_id]
            if player_name and player.name != player_name:
                old_name = player.name
                player.name = player_name
                player.refresh_score()
                self.add_activity(f"✏️ {old_name} s'appelle maintenant {player_name}", "rename")
            player.refresh_score()
            # If no host exists, assign this player as host
            if not self.host_player_id or self.host_player_id not in self.players:
                self.host_player_id = player_id
                player.is_host = True
            return player

        # First player becomes host
        is_first = len(self.players) == 0 or not self.host_player_id
        if is_first:
            self.host_player_id = player_id

        # Balance teams across blue, red, green, yellow
        team_counts = {t: sum(1 for p in self.players.values() if p.team == t) for t in ALL_TEAMS}
        default_team = min(ALL_TEAMS, key=lambda t: team_counts[t])

        if self.game_mode == "team":
            if not self.team_sessions:
                self._init_team_sessions()
            session = self.team_sessions[default_team]
        else:
            session_id = str(uuid.uuid4())
            session = GameSession(
                session_id=session_id,
                seed=self.seed,
                title=self.article_data["title"],
                url=self.article_data.get("url", f"https://fr.wikipedia.org/wiki/{self.article_data['title']}"),
                image=self.article_data.get("image", ""),
                paragraphs=self.article_data["paragraphs"],
                mode=self.session_mode,
                category=self.article_data.get("category", "general"),
                difficulty=self.difficulty,
                lang_count=self.article_data.get("lang_count", 0),
                pageviews_90d=self.article_data.get("pageviews_90d", int(self.article_data.get("pageviews_60d", 0) * 1.5))
            )

        player = RoomPlayer(player_id=player_id, name=player_name, session=session, is_host=is_first, team=default_team)
        if not self.room_id.startswith("solo-") and self.status in ("starting", "playing", "ending"):
            player.is_spectator = True
            player.waiting_for_next_round = True
        if self.room_id.startswith("solo-"):
            player.is_ready = True
            player.is_host = is_first
            if is_first:
                self.host_player_id = player_id
            self.status = "playing"
        self.players[player_id] = player
        if (self.status in ("playing", "starting", "ending") and not player.is_spectator) or self.room_id.startswith("solo-"):
            self.record_current_article_for_players([player_id, player_name])
        team_meta = TEAM_METADATA.get(default_team, {})
        team_tag = f" ({team_meta.get('icon', '')} {team_meta.get('short', '')})" if self.game_mode == "team" else ""
        self.add_activity(f"👋 {player_name} a rejoint la salle{' (Host 👑)' if is_first else ''}{team_tag}", "join")
        return player

    def toggle_ready(self, player_id: str, ready: Optional[bool] = None) -> bool:
        if player_id not in self.players:
            return False
        player = self.players[player_id]
        if player.waiting_for_next_round and self.status != "lobby":
            return False
        if player.is_spectator:
            player.is_spectator = False
            self.add_activity(f"🎮 {player.name} a repris sa place de joueur !", "spectator")
        if ready is None:
            player.is_ready = not player.is_ready
        else:
            player.is_ready = ready

        state_str = "est prêt ! 🟢" if player.is_ready else "n'est plus prêt ⏳"
        self.add_activity(f"{player.name} {state_str}", "ready")
        return player.is_ready

    async def start_game(self, player_id: str) -> Dict[str, Any]:
        """Host initiates game start: triggers 5-second countdown."""
        if player_id not in self.players:
            return {"error": "Joueur non trouvé"}
        player = self.players[player_id]
        if not player.is_host:
            return {"error": "Seul l'Host peut lancer la partie."}
        if not self.can_start():
            not_ready_count = sum(1 for p in self.players.values() if not p.is_spectator and not p.is_ready and p.connected)
            return {"error": f"Impossible de lancer : {not_ready_count} joueur(s) ne sont pas encore prêts."}

        # If a previous round was already finished, launch a new round with a fresh article
        if self.rounds_played > 0:
            return await self.start_new_round(player_id)

        # Collect 15-day played articles for ALL players in the room
        excluded_titles = self.get_recently_played_titles(days=21)
        exclude_norm = {normalize_wiki_title(t) for t in excluded_titles if t}
        curr_title = self.article_data.get("title", "")

        # Guarantee the article corresponds to the lobby difficulty and has not appeared to ANY player in the room
        if (
            curr_title in excluded_titles or
            normalize_wiki_title(curr_title) in exclude_norm or
            self.article_data.get("difficulty") != self.difficulty
        ):
            try:
                new_art = await asyncio.to_thread(
                    room_manager._fetch_random_article,
                    self.difficulty,
                    exclude_titles=excluded_titles
                )
                if new_art:
                    new_art["difficulty"] = self.difficulty
                    self.article_data = new_art
                    self.seed = f"P-{random.randint(1000, 9999)}"
            except Exception as e:
                logger.error(f"Error fetching difficulty article before start: {e}")

        if self.game_mode == "team":
            self._init_team_sessions()
            for p in self.players.values():
                if p.team in self.team_sessions:
                    p.session = self.team_sessions[p.team]
        else:
            for p in self.players.values():
                session_id = str(uuid.uuid4())
                p.session = GameSession(
                    session_id=session_id,
                    seed=self.seed,
                    title=self.article_data["title"],
                    url=self.article_data.get("url", ""),
                    image=self.article_data.get("image", ""),
                    paragraphs=self.article_data["paragraphs"],
                    mode=self.session_mode,
                    category=self.article_data.get("category", "general"),
                    difficulty=self.difficulty,
                    lang_count=self.article_data.get("lang_count", 0),
                    pageviews_90d=self.article_data.get("pageviews_90d", int(self.article_data.get("pageviews_60d", 0) * 1.5))
                )

        # Enregistrer l'article comme apparu pour tous les joueurs du salon
        self.record_current_article_for_players()

        self.winners = []
        self.first_winner_id = None
        self.first_winner_name = None
        self.first_winner_attempts = None
        self.surrender_in_progress = False
        self.surrender_initiator_id = None
        self.surrender_initiator_name = None
        self.surrender_votes = set()
        self.surrender_cooldowns.clear()
        self.status = "starting"
        self.countdown_end = time.time() + 5.0
        self.add_activity("⏳ Compte à rebours de 5 secondes lancé !", "countdown")

        # Broadcast countdown to all players
        await self.broadcast({
            "type": "countdown_started",
            "seconds": 5,
            "end_time": self.countdown_end,
            "status": self.status,
            "difficulty": self.difficulty,
            "article_difficulty": self.article_data.get("difficulty", self.difficulty),
            "article_lang_count": self.article_data.get("lang_count", 0),
            "article_pageviews_90d": self.article_data.get("pageviews_90d", int(self.article_data.get("pageviews_60d", 0) * 1.5)),
            "leaderboard": self.get_leaderboard(),
            "activity": self.recent_activity
        })

        # Run background async task for the 5-second countdown
        if self._countdown_task and not self._countdown_task.done():
            self._countdown_task.cancel()
        self._countdown_task = asyncio.create_task(self._run_5s_countdown())

        return {"status": "starting", "seconds": 5, "end_time": self.countdown_end}

    async def _run_5s_countdown(self):
        try:
            await asyncio.sleep(5.0)
            self.status = "playing"
            self.countdown_end = None
            self.hinted_word_ids.clear()
            self.next_word_hint_time = time.time() + self.word_hint_initial_delay
            self.add_activity("🚀 La partie a commencé ! Bonne chance à tous !", "start")

            if self._word_hint_task and not self._word_hint_task.done():
                self._word_hint_task.cancel()
            self._word_hint_task = asyncio.create_task(self._run_word_hint_loop())

            await self.broadcast({
                "type": "game_started",
                "status": "playing",
                "leaderboard": self.get_leaderboard(),
                "activity": self.recent_activity,
                "next_word_hint_time": self.next_word_hint_time
            })
        except asyncio.CancelledError:
            pass

    def process_guess(self, player_id: str, word: str) -> Dict[str, Any]:
        if player_id not in self.players:
            return {"error": "Joueur non trouvé dans la salle."}

        player = self.players[player_id]

        if player.is_spectator:
            return {"error": "Vous êtes en mode spectateur (en pause). Reprenez votre place de joueur pour proposer des mots."}

        if self.status not in ("playing", "ending"):
            if self.status == "lobby":
                return {"error": "La partie n'a pas encore été lancée par l'Host."}
            elif self.status == "starting":
                return {"error": "La partie démarre dans quelques secondes..."}
            elif self.status == "round_over":
                return {"error": "Cette manche est terminée. Attendez la suivante !"}

        # Use team session if in team mode, else player session
        if self.game_mode == "team":
            if not self.team_sessions:
                self._init_team_sessions()
            session = self.team_sessions.get(player.team)
            if not session:
                session = player.session
        elif self.is_cooperative_solo:
            owner_id = self.room_id.removeprefix("solo-")
            owner = self.players.get(owner_id)
            session = owner.session if owner else player.session
        else:
            session = player.session

        if self.is_cooperative_solo and session.is_won:
            return {"status": "already_won", "message": "Cette page a déjà été trouvée ensemble."}

        guess_res = session.submit_guess(word)

        if "error" in guess_res or guess_res.get("is_repeat") or guess_res.get("status") == "already_guessed":
            return guess_res
        if self.game_mode == "team":
            guess_res["team_close_tokens"] = session.get_close_tokens()

        # Update progress
        attempts = guess_res["attempt_number"]
        revealed_count = guess_res["revealed_words_count"]
        total_words = guess_res["total_words"]
        pct = round((revealed_count / max(1, total_words)) * 100)
        status = guess_res["status"]
        matches_count = guess_res["matches_count"]
        score = guess_res.get("score", 0)

        if self.is_cooperative_solo:
            for p in self.players.values():
                p.attempts = attempts
                p.revealed_words_count = revealed_count
                p.total_words = total_words
                p.pct = pct
                p.last_word = word
                p.last_status = status
                p.last_count = matches_count
                p.last_score = score
        elif self.game_mode == "team":
            # Cooperative: sync all teammates
            for p in self.players.values():
                if p.team == player.team:
                    p.attempts = attempts
                    p.revealed_words_count = revealed_count
                    p.total_words = total_words
                    p.pct = pct
                    p.last_word = word
                    p.last_status = status
                    p.last_count = matches_count
                    p.last_score = score
        else:
            player.attempts = attempts
            player.revealed_words_count = revealed_count
            player.total_words = total_words
            player.pct = pct
            player.last_word = word
            player.last_status = status
            player.last_count = matches_count
            player.last_score = score

        # Record guessed word for player stats
        record_user_guess_word(player.name, word)

        # Check win
        if guess_res["is_won"]:
            if self.is_cooperative_solo:
                owner_id = self.room_id.removeprefix("solo-")
                owner = self.players.get(owner_id)
                self.status = "ending"
                self.first_winner_id = owner_id
                self.first_winner_name = owner.name if owner else player.name
                self.first_winner_attempts = attempts
                self.winners = [owner_id]
                for p in self.players.values():
                    p.is_won = True
                    p.won_at = time.time()
                self.add_activity(f"🤝 {player.name} et {owner.name if owner else 'le propriétaire'} ont trouvé le titre ensemble !", "win")
                if self._word_hint_task and not self._word_hint_task.done():
                    self._word_hint_task.cancel()
                self.next_word_hint_time = None
                if self._timer_30s_task and not self._timer_30s_task.done():
                    self._timer_30s_task.cancel()
            elif self.game_mode == "team":
                if not self.winning_team:
                    self.winning_team = player.team
                    team_meta = TEAM_METADATA.get(player.team, {})
                    team_name = f"{team_meta.get('name', player.team)} {team_meta.get('icon', '')}"
                    self.first_winner_id = player.player_id
                    self.first_winner_name = f"{team_name} (menée par {player.name})"
                    self.first_winner_attempts = attempts
                    self.status = "ending"
                    self.timer_30s_end = time.time() + 30.0

                    for p in self.players.values():
                        if p.team == player.team:
                            p.is_won = True
                            p.won_at = time.time()
                            if p.player_id not in self.winners:
                                self.winners.append(p.player_id)

                    self.add_activity(f"🏆 {team_name} a découvert le titre en {attempts} coups ! 30s pour les autres équipes !", "win")

                    if self._word_hint_task and not self._word_hint_task.done():
                        self._word_hint_task.cancel()
                    self.next_word_hint_time = None

                    if self._timer_30s_task and not self._timer_30s_task.done():
                        self._timer_30s_task.cancel()
                    self._timer_30s_task = asyncio.create_task(self._run_30s_timer())
                else:
                    # Another team also found it during 30s sprint!
                    team_meta = TEAM_METADATA.get(player.team, {})
                    team_name = f"{team_meta.get('name', player.team)} {team_meta.get('icon', '')}"
                    for p in self.players.values():
                        if p.team == player.team:
                            p.is_won = True
                            p.won_at = time.time()
                            if p.player_id not in self.winners:
                                self.winners.append(p.player_id)
                    self.add_activity(f"🎯 {team_name} a également découvert le titre !", "win_also")

                    # Check if all active teams have won
                    active_teams = set(p.team for p in self.players.values() if p.connected and not p.is_spectator)
                    won_teams = set(p.team for p in self.players.values() if p.is_won)
                    if won_teams >= active_teams:
                        if self._timer_30s_task and not self._timer_30s_task.done():
                            self._timer_30s_task.cancel()
                        self._timer_30s_task = asyncio.create_task(self._finish_round())

            else:
                # Individual mode win check
                if not player.is_won:
                    player.is_won = True
                    player.won_at = time.time()

                    if player.player_id not in self.winners:
                        self.winners.append(player.player_id)

                    rank = len(self.winners)
                    connected_players = [p for p in self.players.values() if p.connected and not p.is_spectator]
                    if rank == 1:
                        self.first_winner_id = player.player_id
                        self.first_winner_name = player.name
                        self.first_winner_attempts = player.attempts
                        self.status = "ending"

                        if self._word_hint_task and not self._word_hint_task.done():
                            self._word_hint_task.cancel()
                        self.next_word_hint_time = None
                        if self._timer_30s_task and not self._timer_30s_task.done():
                            self._timer_30s_task.cancel()

                        if len(connected_players) <= 1:
                            # Solo or only 1 player in room: finish immediately
                            self.add_activity(f"🏆 {player.name} a découvert le titre en {player.attempts} coups !", "win")
                            self._timer_30s_task = asyncio.create_task(self._finish_round())
                        else:
                            self.timer_30s_end = time.time() + 30.0
                            self.add_activity(f"🏆 {player.name} a découvert le titre en {player.attempts} coups ! 30s restantes pour les autres !", "win")
                            self._timer_30s_task = asyncio.create_task(self._run_30s_timer())
                    else:
                        pts_bonus = "+2 pt" if rank == 2 else ("+1 pt" if rank == 3 else "0 pt")
                        self.add_activity(f"🎯 {player.name} a également découvert le titre ({rank}e place, {pts_bonus}) !", "win_also")

                        if len(self.winners) >= len(connected_players):
                            if self._timer_30s_task and not self._timer_30s_task.done():
                                self._timer_30s_task.cancel()
                            self._timer_30s_task = asyncio.create_task(self._finish_round())
        else:
            team_meta = TEAM_METADATA.get(player.team, {})
            team_prefix = f"[{team_meta.get('icon', '')} {team_meta.get('short', '')}] " if self.game_mode == "team" else ""
            if status == "match":
                self.add_activity(f"{team_prefix}🟩 Mot trouvé par {player.name} ({matches_count} occurrence{'s' if matches_count > 1 else ''})", "match")
            elif status == "close":
                score_str = f" ({score}%)" if score else ""
                self.add_activity(f"{team_prefix}🟧 Mot proche trouvé par {player.name}{score_str} !", "close")

        return guess_res

    async def _run_30s_timer(self):
        try:
            # Broadcast the start of the 30s timer
            await self.broadcast({
                "type": "first_winner",
                "winner_name": self.first_winner_name,
                "winner_attempts": self.first_winner_attempts,
                "seconds": 30,
                "end_time": self.timer_30s_end,
                "status": "ending",
                "leaderboard": self.get_leaderboard(),
                "activity": self.recent_activity
            })

            await asyncio.sleep(30.0)
            await self._finish_round()
        except asyncio.CancelledError:
            pass

    async def _finish_round(self):
        """Timer expired or all players found: award points (+3 for 1st, +2 for 2nd, +1 for 3rd) and return to lobby."""
        if self.status == "lobby":
            return
        self.status = "lobby"
        self.rounds_played += 1
        self.timer_30s_end = None

        if self._word_hint_task and not self._word_hint_task.done():
            self._word_hint_task.cancel()
        self.next_word_hint_time = None

        round_podium = []
        if self.game_mode == "team":
            if self.winning_team:
                win_meta = TEAM_METADATA.get(self.winning_team, {})
                win_team_name = f"{win_meta.get('name', self.winning_team)} {win_meta.get('icon', '')}"
                self.add_activity(f"🏆 Victoire de l'{win_team_name} ! (+3 pts pour tous les équipiers)", "score")
                for p in self.players.values():
                    if p.team == self.winning_team and not p.is_spectator:
                        new_score = increment_player_score(p.name, 3)
                        p.refresh_score()
                        round_podium.append({
                            "rank": 1,
                            "player_id": p.player_id,
                            "name": p.name,
                            "team": p.team,
                            "points": 3,
                            "score": p.score,
                            "attempts": p.attempts
                        })

                # Check if other teams also found it during 30s (+1 pt)
                for other_team in ALL_TEAMS:
                    if other_team != self.winning_team:
                        other_sess = self.team_sessions.get(other_team)
                        if other_sess and other_sess.is_won:
                            for p in self.players.values():
                                if p.team == other_team and not p.is_spectator:
                                    new_score = increment_player_score(p.name, 1)
                                    p.refresh_score()
                                    round_podium.append({
                                        "rank": 2,
                                        "player_id": p.player_id,
                                        "name": p.name,
                                        "team": p.team,
                                        "points": 1,
                                        "score": p.score,
                                        "attempts": p.attempts
                                    })
        else:
            # Individual mode: 3 pt for 1st, 2 pt for 2nd, 1 pt for 3rd
            pts_map = [3, 2, 1]
            for rank, pid in enumerate(self.winners):
                pts = pts_map[rank] if rank < len(pts_map) else 0
                p = self.players.get(pid)
                if p:
                    if pts > 0:
                        new_score = increment_player_score(p.name, pts)
                        p.refresh_score()
                        self.add_activity(f"🎉 {p.name} ({rank+1}e) gagne +{pts} pt{'s' if pts > 1 else ''} ! (Score: {new_score})", "score")
                    round_podium.append({
                        "rank": rank + 1,
                        "player_id": pid,
                        "name": p.name,
                        "team": p.team,
                        "points": pts,
                        "score": p.score,
                        "attempts": p.attempts
                    })

        # Refresh all player scores from DB, record game finish stats, and reset ready status
        finished_sessions = set()
        for p in self.players.values():
            if not p.is_spectator:
                stats_session = (
                    self.team_sessions.get(p.team, p.session)
                    if self.game_mode == "team" else p.session
                )
                if stats_session and stats_session.session_id not in finished_sessions:
                    record_game_finish(
                        stats_session.session_id,
                        won=stats_session.is_won,
                        surrendered=False,
                        attempts=stats_session.attempts,
                        revealed_words=len(stats_session.revealed_word_ids),
                        elapsed_time=int(time.time() - stats_session.created_at),
                    )
                    finished_sessions.add(stats_session.session_id)
                pts = next(
                    (item["points"] for item in round_podium if item.get("player_id") == p.player_id),
                    0,
                )
                if stats_session:
                    record_user_game_finish(
                        p.name,
                        won=p.is_won,
                        attempts=p.attempts,
                        points=pts,
                        session_id=stats_session.session_id,
                        mode=(
                            "solo" if self.room_id.startswith("solo-")
                            else "team" if self.game_mode == "team"
                            else "multiplayer"
                        ),
                        title=self.article_data["title"],
                        duration_seconds=int(time.time() - stats_session.created_at),
                        revealed_words=len(stats_session.revealed_word_ids),
                        total_words=stats_session.total_words,
                        difficulty=getattr(stats_session, "difficulty", None),
                        metrics={"category": getattr(stats_session, "category", None)},
                    )
            p.refresh_score()
            p.is_ready = True if self.room_id.startswith("solo-") else False
            if p.session:
                p.session.is_surrendered = True
        if self.game_mode == "team" and self.team_sessions:
            for s in self.team_sessions.values():
                s.is_surrendered = True

        self.last_round_results = {
            "title": self.article_data["title"],
            "url": self.article_data.get("url", ""),
            "image": self.article_data.get("image", ""),
            "podium": round_podium,
            "winners_count": len(self.winners),
            "game_mode": self.game_mode,
            "winning_team": self.winning_team
        }
        if self.is_cooperative_solo:
            self.assisting_player_id = None

        promoted_player_ids = self.activate_waiting_players()

        # Broadcast round over and return to lobby
        await self.broadcast({
            "type": "round_over_to_lobby",
            "status": "lobby",
            "winner_name": self.first_winner_name,
            "winner_attempts": self.first_winner_attempts,
            "game_mode": self.game_mode,
            "winning_team": self.winning_team,
            "difficulty": self.difficulty,
            "article_difficulty": self.article_data.get("difficulty", self.difficulty),
            "article_lang_count": self.article_data.get("lang_count", 0),
            "article_pageviews_90d": self.article_data.get("pageviews_90d", int(self.article_data.get("pageviews_60d", 0) * 1.5)),
            "teams": self.get_teams_data(),
            "title": self.article_data["title"],
            "url": self.article_data.get("url", ""),
            "image": self.article_data.get("image", ""),
            "solution": {
                "title": self.article_data["title"],
                "url": self.article_data.get("url", ""),
                "image": self.article_data.get("image", "")
            },
            "last_round": self.last_round_results,
            "leaderboard": self.get_leaderboard(),
            "activity": self.recent_activity,
            "can_start": self.can_start(),
            "promoted_player_ids": promoted_player_ids,
        })

    async def start_new_round(self, player_id: str, new_article: Optional[Dict[str, Any]] = None, new_seed: Optional[str] = None) -> Dict[str, Any]:
        """Host launches a new round: verifies host and that everyone clicked ready."""
        if player_id not in self.players:
            return {"error": "Joueur non trouvé"}
        player = self.players[player_id]
        if self.room_id.startswith("solo-"):
            player.is_host = True
            player.is_ready = True
        else:
            if not player.is_host:
                return {"error": "Seul l'Host peut lancer la partie."}
            if not self.can_start():
                not_ready = [p.name for p in self.players.values() if not p.is_spectator and not p.is_ready and p.connected]
                return {"error": f"En attente que tous les joueurs soient prêts : {', '.join(not_ready)}"}

        if self._timer_30s_task and not self._timer_30s_task.done():
            self._timer_30s_task.cancel()
        if self._countdown_task and not self._countdown_task.done():
            self._countdown_task.cancel()
        if self._word_hint_task and not self._word_hint_task.done():
            self._word_hint_task.cancel()
        self.hinted_word_ids.clear()
        self.next_word_hint_time = None

        excluded_titles = self.get_recently_played_titles(days=21)
        exclude_norm = {normalize_wiki_title(t) for t in excluded_titles if t}

        if (
            not new_article or
            new_article.get("title", "") in excluded_titles or
            normalize_wiki_title(new_article.get("title", "")) in exclude_norm or
            not article_matches_difficulty(new_article, self.difficulty)
        ):
            new_article = await asyncio.to_thread(
                room_manager._fetch_notable_article,
                self.difficulty,
                exclude_titles=excluded_titles
            )
        if not new_article:
            new_article = room_manager._fetch_random_article(self.difficulty, exclude_titles=excluded_titles)
        if (
            not new_article
            or normalize_wiki_title(new_article.get("title", "")) in exclude_norm
            or not article_matches_difficulty(new_article, self.difficulty)
        ):
            raise RuntimeError("Aucun nouvel article correspondant à la difficulté et à l'historique des joueurs.")
        if not new_seed:
            new_seed = f"P-{random.randint(1000, 9999)}"

        new_article["difficulty"] = self.difficulty
        self.article_data = new_article
        self.seed = new_seed
        self.record_current_article_for_players()
        self.status = "starting"
        self.countdown_end = time.time() + 5.0
        self.timer_30s_end = None
        self.first_winner_id = None
        self.first_winner_name = None
        self.first_winner_attempts = None
        self.winners = []
        self.winning_team = None
        self.surrender_in_progress = False
        self.surrender_initiator_id = None
        self.surrender_initiator_name = None
        self.surrender_votes = set()
        self.surrender_cooldowns.clear()
        self.created_at = time.time()
        self.last_round_results = None

        # Re-initialize sessions with the new article
        if self.game_mode == "team":
            self._init_team_sessions()
            for p in self.players.values():
                p.session = self.team_sessions.get(p.team)
                p.attempts = 0
                p.revealed_words_count = 0
                p.total_words = p.session.total_words if p.session else 0
                p.pct = 0
                p.is_won = False
                p.won_at = None
                p.last_word = None
                p.last_status = None
                p.last_count = 0
                p.refresh_score()
        else:
            for p in self.players.values():
                session_id = str(uuid.uuid4())
                p.session = GameSession(
                    session_id=session_id,
                    seed=self.seed,
                    title=self.article_data["title"],
                    url=self.article_data.get("url", ""),
                    image=self.article_data.get("image", ""),
                    paragraphs=self.article_data["paragraphs"],
                    mode=self.session_mode,
                    category=self.article_data.get("category", "general"),
                    difficulty=self.difficulty,
                    lang_count=self.article_data.get("lang_count", 0),
                    pageviews_90d=self.article_data.get("pageviews_90d", int(self.article_data.get("pageviews_60d", 0) * 1.5))
                )
                p.attempts = 0
                p.revealed_words_count = 0
                p.total_words = p.session.total_words
                p.pct = 0
                p.is_won = False
                p.won_at = None
                p.last_word = None
                p.last_status = None
                p.last_count = 0
                p.refresh_score()

        if self.room_id.startswith("solo-"):
            self.status = "playing"
            self.countdown_end = None
            for p in self.players.values():
                p.is_ready = True
            self.add_activity("🎲 Nouvelle partie solo lancée !", "new_round")
            self.next_word_hint_time = time.time() + self.word_hint_initial_delay
            self.start_word_hint_timer()
            await self.broadcast({
                "type": "new_round",
                "status": "playing",
                "seed": self.seed,
                "difficulty": self.difficulty,
                "article_difficulty": self.article_data.get("difficulty", self.difficulty),
                "article_lang_count": self.article_data.get("lang_count", 0),
                "article_pageviews_90d": self.article_data.get("pageviews_90d", int(self.article_data.get("pageviews_60d", 0) * 1.5)),
                "game_mode": self.game_mode,
                "teams": self.get_teams_data(),
                "leaderboard": self.get_leaderboard(),
                "activity": self.recent_activity,
                "next_word_hint_time": self.next_word_hint_time
            })
            return {"status": "playing", "seed": self.seed, "difficulty": self.difficulty}

        self.add_activity("🎲 Nouvelle partie lancée ! Compte à rebours de 5 secondes...", "new_round")

        await self.broadcast({
            "type": "countdown_started",
            "seconds": 5,
            "end_time": self.countdown_end,
            "status": "starting",
            "seed": self.seed,
            "difficulty": self.difficulty,
            "article_difficulty": self.article_data.get("difficulty", self.difficulty),
            "article_lang_count": self.article_data.get("lang_count", 0),
            "article_pageviews_90d": self.article_data.get("pageviews_90d", int(self.article_data.get("pageviews_60d", 0) * 1.5)),
            "game_mode": self.game_mode,
            "teams": self.get_teams_data(),
            "leaderboard": self.get_leaderboard(),
            "activity": self.recent_activity
        })

        self._countdown_task = asyncio.create_task(self._run_5s_countdown())
        return {"status": "starting", "seconds": 5, "seed": self.seed}

    def unmask_player(self, player_id: str) -> Dict[str, Any]:
        """Démasque entièrement tous les mots de l'article pour le joueur spécifié."""
        if player_id not in self.players:
            return {"error": "Joueur introuvable dans la salle."}
        player = self.players[player_id]
        if self.game_mode == "team":
            session = self.team_sessions.get(player.team, player.session)
        else:
            session = player.session
        if not (player.is_won or session.is_won or session.is_surrendered or (self.status in ("lobby", "round_over") and self.rounds_played > 0)):
            return {"error": "L'article ne peut être démasqué qu'une fois la manche terminée."}
        session.is_surrendered = True
        return session.unmask_all()

    async def propose_or_vote_surrender(self, player_id: str, vote: str = "yes") -> Dict[str, Any]:
        """Gère la proposition ou le vote d'abandon unanime de la partie."""
        if player_id not in self.players:
            return {"error": "Joueur non trouvé dans la salle."}
        if self.status not in ("playing", "ending", "starting"):
            return {"error": "Aucune partie en cours à abandonner."}

        player = self.players[player_id]
        if player.is_spectator:
            return {"error": "Les spectateurs en pause ne peuvent pas proposer ou voter l'abandon."}

        if vote == "cancel":
            if self.surrender_in_progress and self.surrender_initiator_id == player_id:
                self.surrender_in_progress = False
                self.surrender_initiator_id = None
                self.surrender_initiator_name = None
                self.surrender_votes.clear()
                self.add_activity(f"↩️ {player.name} a annulé sa demande d'abandon.", "surrender")
                await self.broadcast({
                    "type": "surrender_cancelled",
                    "initiator_name": player.name,
                    "activity": self.recent_activity
                })
                return {"status": "cancelled"}
            return {"error": "Impossible d'annuler cette demande."}

        if vote == "no":
            refused_initiator_id = self.surrender_initiator_id
            if refused_initiator_id:
                self.surrender_cooldowns[refused_initiator_id] = time.time() + 30.0

            self.surrender_in_progress = False
            self.surrender_initiator_id = None
            self.surrender_initiator_name = None
            self.surrender_votes.clear()
            self.add_activity(f"❌ L'abandon a été refusé par {player.name}. La partie continue !", "surrender")
            await self.broadcast({
                "type": "surrender_rejected",
                "refuser_name": player.name,
                "initiator_id": refused_initiator_id,
                "cooldown_seconds": 30,
                "activity": self.recent_activity
            })
            return {
                "status": "rejected",
                "refuser_name": player.name,
                "initiator_id": refused_initiator_id,
                "cooldown_seconds": 30
            }

        # vote == "yes"
        if player.is_spectator:
            return {"error": "Les spectateurs en pause ne peuvent pas proposer l'abandon."}

        if not self.surrender_in_progress:
            now = time.time()
            cd_until = self.surrender_cooldowns.get(player_id, 0.0)
            if cd_until > now:
                remaining = int(math.ceil(cd_until - now))
                return {
                    "error": f"Votre demande d'abandon a été refusée. Veuillez patienter encore {remaining} s avant de pouvoir refaire une demande.",
                    "cooldown_remaining": remaining
                }

            self.surrender_in_progress = True
            self.surrender_initiator_id = player_id
            self.surrender_initiator_name = player.name
            self.surrender_votes = {player_id}
            self.add_activity(f"🏳️ {player.name} propose d'abandonner la partie.", "surrender")
        else:
            self.surrender_votes.add(player_id)

        connected_pids = {p.player_id for p in self.players.values() if p.connected and not p.is_spectator}
        if not connected_pids:
            connected_pids = {player_id}

        # Check if 100% of connected players agreed
        if self.surrender_votes >= connected_pids:
            await self.execute_surrender()
            return {"status": "passed"}
        else:
            await self.broadcast({
                "type": "surrender_update",
                "in_progress": True,
                "initiator_id": self.surrender_initiator_id,
                "initiator_name": self.surrender_initiator_name,
                "votes_count": len(self.surrender_votes & connected_pids),
                "total_required": len(connected_pids),
                "voted_player_ids": list(self.surrender_votes & connected_pids),
                "activity": self.recent_activity
            })
            return {
                "status": "voting",
                "votes_count": len(self.surrender_votes & connected_pids),
                "total_required": len(connected_pids)
            }

    async def execute_surrender(self):
        """Valide l'abandon unanime : révèle tout l'article, termine la partie, aucun point attribué."""
        self.surrender_in_progress = False
        self.surrender_initiator_id = None
        self.surrender_initiator_name = None
        self.surrender_votes.clear()

        self.status = "lobby"
        self.rounds_played += 1
        self.timer_30s_end = None
        self.countdown_end = None

        if self._countdown_task and not self._countdown_task.done():
            self._countdown_task.cancel()
        if self._timer_30s_task and not self._timer_30s_task.done():
            self._timer_30s_task.cancel()
        if self._word_hint_task and not self._word_hint_task.done():
            self._word_hint_task.cancel()
        self.hinted_word_ids.clear()
        self.next_word_hint_time = None

        # Reset ready status for active players and ensure NO points are awarded
        finished_sessions = set()
        for p in self.players.values():
            if not p.is_spectator:
                stats_session = (
                    self.team_sessions.get(p.team, p.session)
                    if self.game_mode == "team" else p.session
                )
                if stats_session:
                    if stats_session.session_id not in finished_sessions:
                        record_game_finish(
                            stats_session.session_id,
                            won=False,
                            surrendered=True,
                            attempts=stats_session.attempts,
                            revealed_words=len(stats_session.revealed_word_ids),
                            elapsed_time=int(time.time() - stats_session.created_at),
                        )
                        finished_sessions.add(stats_session.session_id)
                    record_user_game_finish(
                        p.name,
                        won=False,
                        attempts=p.attempts,
                        points=0,
                        session_id=stats_session.session_id,
                        mode=(
                            "solo" if self.room_id.startswith("solo-")
                            else "team" if self.game_mode == "team"
                            else "multiplayer"
                        ),
                        title=self.article_data["title"],
                        surrendered=True,
                        duration_seconds=int(time.time() - stats_session.created_at),
                        revealed_words=len(stats_session.revealed_word_ids),
                        total_words=stats_session.total_words,
                        difficulty=getattr(stats_session, "difficulty", None),
                        metrics={"category": getattr(stats_session, "category", None)},
                    )
            p.refresh_score()
            p.is_ready = True if self.room_id.startswith("solo-") else False

        # Unmask all tokens across sessions
        unmasked_tokens: Dict[str, str] = {}
        if self.game_mode == "team" and self.team_sessions:
            for s in self.team_sessions.values():
                s.is_surrendered = True
                res = s.unmask_all()
                unmasked_tokens.update(res.get("tokens", {}))
        else:
            for p in self.players.values():
                if p.session:
                    p.session.is_surrendered = True
                    res = p.session.unmask_all()
                    unmasked_tokens.update(res.get("tokens", {}))

        self.last_round_results = {
            "title": self.article_data["title"],
            "url": self.article_data.get("url", ""),
            "image": self.article_data.get("image", ""),
            "podium": [],
            "abandoned": True,
            "winners_count": 0,
            "game_mode": self.game_mode,
            "winning_team": None
        }
        if self.is_cooperative_solo:
            self.assisting_player_id = None

        self.add_activity("🏳️ La partie a été abandonnée à l'unanimité. L'article est révélé ! (0 point)", "surrender")
        promoted_player_ids = self.activate_waiting_players()

        await self.broadcast({
            "type": "surrender_passed",
            "status": "lobby",
            "title": self.article_data["title"],
            "url": self.article_data.get("url", ""),
            "image": self.article_data.get("image", ""),
            "solution": {
                "title": self.article_data["title"],
                "url": self.article_data.get("url", ""),
                "image": self.article_data.get("image", "")
            },
            "tokens": unmasked_tokens,
            "last_round": self.last_round_results,
            "leaderboard": self.get_leaderboard(),
            "teams": self.get_teams_data(),
            "activity": self.recent_activity,
            "can_start": self.can_start(),
            "promoted_player_ids": promoted_player_ids,
        })

    start_next_round = start_new_round

    def cleanup(self):
        """Cancels all background tasks and clears websockets."""
        if self._countdown_task and not self._countdown_task.done():
            self._countdown_task.cancel()
        if self._timer_30s_task and not self._timer_30s_task.done():
            self._timer_30s_task.cancel()
        if self._word_hint_task and not self._word_hint_task.done():
            self._word_hint_task.cancel()
        for task in self._disconnect_tasks.values():
            if not task.done():
                task.cancel()
        self._disconnect_tasks.clear()
        self.surrender_in_progress = False
        self.surrender_initiator_id = None
        self.surrender_initiator_name = None
        self.surrender_votes.clear()
        self.websockets.clear()
        self.ws_player_map.clear()

    def add_websocket(self, ws: WebSocket, player_id: Optional[str] = None) -> bool:
        reconnected = False
        self.websockets.add(ws)
        if player_id:
            self.ws_player_map[ws] = player_id
            if player_id in self.players:
                player = self.players[player_id]
                reconnected = not player.connected or player.disconnected_at is not None
                player.connected = True
                player.disconnected_at = None
                task = self._disconnect_tasks.pop(player_id, None)
                if task and not task.done():
                    task.cancel()
        return reconnected

    def mark_player_disconnected(self, player_id: str):
        player = self.players.get(player_id)
        if not player:
            return
        player.connected = False
        if player.disconnected_at is None:
            player.disconnected_at = time.time()
        existing_task = self._disconnect_tasks.get(player_id)
        if existing_task and not existing_task.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._disconnect_tasks[player_id] = loop.create_task(
            self._delayed_remove_player(
                player_id,
                delay=PLAYER_DISCONNECT_GRACE_SECONDS,
            )
        )

    def remove_websocket(self, ws: WebSocket):
        self.websockets.discard(ws)
        self.ws_player_map.pop(ws, None)

    async def handle_websocket_disconnect(self, ws: WebSocket):
        pid = self.ws_player_map.pop(ws, None)
        self.websockets.discard(ws)

        if pid and pid in self.players:
            has_other_ws = any(p_id == pid for p_id in self.ws_player_map.values())
            if not has_other_ws:
                player = self.players[pid]
                # Preserve the player state while a page reload or reconnect is in progress.
                self.mark_player_disconnected(pid)
                await self.broadcast({
                    "type": "player_disconnected",
                    "player_id": pid,
                    "player_name": player.name,
                    "host_player_id": self.host_player_id,
                    "leaderboard": self.get_leaderboard(),
                    "teams": self.get_teams_data(),
                    "can_start": self.can_start(),
                    "activity": self.recent_activity,
                })

    async def _delayed_remove_player(self, player_id: str, delay: float = 4.0):
        try:
            await asyncio.sleep(delay)
            has_active_ws = any(p_id == player_id for p_id in self.ws_player_map.values())
            if not has_active_ws and player_id in self.players:
                player = self.players[player_id]
                player.connected = False
                player.disconnected_at = time.time()
                logger.info(f"Joueur « {player.name} » ({player_id}) déconnecté depuis {delay}s du salon {self.room_id} -> Retrait définitif.")
                await self.remove_player(player_id, reason="disconnect")
        except asyncio.CancelledError:
            pass
        finally:
            if self._disconnect_tasks.get(player_id) is asyncio.current_task():
                self._disconnect_tasks.pop(player_id, None)

    async def remove_player(self, player_id: str, reason: str = "leave") -> bool:
        # Cancel any pending disconnect task
        task = self._disconnect_tasks.pop(player_id, None)
        if task and task is not asyncio.current_task() and not task.done():
            task.cancel()

        if player_id not in self.players:
            return False

        player = self.players.pop(player_id)
        player_name = player.name
        if self.assisting_player_id == player_id:
            self.assisting_player_id = None

        for ws, pid in list(self.ws_player_map.items()):
            if pid == player_id:
                self.ws_player_map.pop(ws, None)
                self.websockets.discard(ws)

        # Keep disconnected players in the room during their reconnect grace period.
        if len(self.players) == 0:
            if self.room_id != "default":
                room_manager.delete_room(self.room_id)
            else:
                self.players.clear()
                self.websockets.clear()
                self.ws_player_map.clear()
            return True

        self.surrender_cooldowns.pop(player_id, None)

        if self.surrender_in_progress:
            self.surrender_votes.discard(player_id)
            if self.surrender_initiator_id == player_id:
                if self.surrender_votes:
                    first_voter = next(iter(self.surrender_votes))
                    self.surrender_initiator_id = first_voter
                    if first_voter in self.players:
                        self.surrender_initiator_name = self.players[first_voter].name
                else:
                    self.surrender_in_progress = False
                    self.surrender_initiator_id = None
                    self.surrender_initiator_name = None

            connected_pids = {p.player_id for p in self.players.values() if p.connected}
            if connected_pids and self.surrender_votes >= connected_pids:
                await self.execute_surrender()
                return True
            elif self.surrender_in_progress:
                await self.broadcast({
                    "type": "surrender_update",
                    "in_progress": True,
                    "initiator_id": self.surrender_initiator_id,
                    "initiator_name": self.surrender_initiator_name,
                    "votes_count": len(self.surrender_votes & connected_pids),
                    "total_required": len(connected_pids),
                    "voted_player_ids": list(self.surrender_votes & connected_pids),
                    "activity": self.recent_activity
                })

        new_host_name = None
        if self.host_player_id == player_id:
            self.host_player_id = None
            for p in self.players.values():
                if p.connected:
                    self.host_player_id = p.player_id
                    p.is_host = True
                    new_host_name = p.name
                    break
            if not self.host_player_id and self.players:
                first_pid = next(iter(self.players))
                self.host_player_id = first_pid
                self.players[first_pid].is_host = True
                new_host_name = self.players[first_pid].name

        leave_msg = f"👋 {player_name} a quitté le salon"
        if new_host_name:
            leave_msg += f" (👑 {new_host_name} est le nouvel Host)"
        self.add_activity(leave_msg, "leave")

        await self.broadcast({
            "type": "player_left",
            "player_id": player_id,
            "player_name": player_name,
            "host_player_id": self.host_player_id,
            "assisting_player_id": self.assisting_player_id,
            "leaderboard": self.get_leaderboard(),
            "teams": self.get_teams_data(),
            "can_start": self.can_start(),
            "activity": self.recent_activity
        })
        return True

    def identify_websocket(self, ws: WebSocket, player_id: str):
        if player_id:
            self.ws_player_map[ws] = player_id
            if player_id in self.players:
                self.players[player_id].connected = True
                self.players[player_id].disconnected_at = None
                task = self._disconnect_tasks.pop(player_id, None)
                if task and not task.done():
                    task.cancel()

    async def broadcast(self, message: Dict[str, Any]):
        to_remove = set()
        is_team_guess = "team_guess" in message and message.get("game_mode") == "team"
        connections = list(self.websockets)
        full_payload = json.dumps(message)
        sanitized_payload = full_payload
        if is_team_guess:
            sanitized_msg = dict(message)
            sanitized_msg["title"] = None
            raw_team_guess = message.get("team_guess", {})
            sanitized_msg["team_guess"] = {
                "player_id": raw_team_guess.get("player_id"),
                "player_name": raw_team_guess.get("player_name"),
                "team": raw_team_guess.get("team"),
                "redacted": True,
                "word": "••••",
                "status": raw_team_guess.get("status"),
                "matches_count": raw_team_guess.get("matches_count", 0),
                "score": raw_team_guess.get("score", 0),
                "newly_revealed": {},
                "close_tokens": [],
                "history_entry": None
            }
            sanitized_payload = json.dumps(sanitized_msg)

        payloads = []
        for ws in connections:
            payload = full_payload
            if is_team_guess:
                recipient_pid = self.ws_player_map.get(ws)
                recipient_player = self.players.get(recipient_pid) if recipient_pid else None
                if not recipient_player or recipient_player.team != message.get("team"):
                    payload = sanitized_payload
            payloads.append(payload)

        results = await asyncio.gather(
            *(ws.send_text(payload) for ws, payload in zip(connections, payloads)),
            return_exceptions=True,
        )
        for ws, result in zip(connections, results):
            if isinstance(result, Exception):
                to_remove.add(ws)

        for dead_ws in to_remove:
            logger.warning("Socket WebSocket inaccessible dans le salon %s.", self.room_id)
            await self.handle_websocket_disconnect(dead_ws)


class RoomManager:
    def __init__(self):
        self.rooms: Dict[str, Room] = {}
        self.wiki_client = WikipediaClient()
        self.game_manager = GameManager()
        self._article_pools: Dict[str, List[Dict[str, Any]]] = {
            "facile": [],
            "moyen": [],
            "difficile": []
        }
        self._pool_lock = threading.Lock()
        self._refilling = False
        self.prefetch_articles(target_per_diff=3)

    # -- Pool d'articles préchargés par niveau de difficulté
    def prefetch_articles(self, target_per_diff: int = 3):
        """Remplit le pool pour chaque difficulté en arrière-plan sans bloquer la boucle asyncio."""
        with self._pool_lock:
            if self._refilling:
                return
            needs_refill = any(len(self._article_pools.get(d, [])) < target_per_diff for d in ("facile", "moyen", "difficile"))
            if not needs_refill:
                return
            self._refilling = True

        def _worker():
            try:
                for d in ("facile", "moyen", "difficile"):
                    with self._pool_lock:
                        curr_len = len(self._article_pools.get(d, []))
                    while curr_len < target_per_diff:
                        try:
                            art = self.wiki_client.fetch_random_wikipedia_article(difficulty=d)
                        except Exception as e:
                            logger.warning(f"prefetch article {d}: {e}")
                            art = None
                        if not art and self.game_manager.offline_curated:
                            candidates = [
                                dict(a) for a in self.game_manager.offline_curated.values()
                                if article_matches_difficulty(a, d)
                            ]
                            if candidates:
                                art = random.choice(candidates)
                        if art and article_matches_difficulty(art, d):
                            art["difficulty"] = d
                            with self._pool_lock:
                                self._article_pools[d].append(art)
                                curr_len = len(self._article_pools[d])
                        else:
                            break
            finally:
                with self._pool_lock:
                    self._refilling = False

        threading.Thread(target=_worker, daemon=True, name="pedantix-article-prefetch").start()

    def _pop_pooled_article(self, difficulty: str = "moyen", exclude_titles: Optional[Set[str]] = None) -> Optional[Dict[str, Any]]:
        diff_key = difficulty.lower() if difficulty and difficulty.lower() in ("facile", "moyen", "difficile") else "moyen"
        exclude_set = set(exclude_titles) if exclude_titles else set()
        exclude_norm = {normalize_wiki_title(t) for t in exclude_set if t}
        with self._pool_lock:
            pool = self._article_pools.get(diff_key, [])
            art = None
            for i, cand in enumerate(pool):
                cand_title = cand.get("title", "")
                if (
                    normalize_wiki_title(cand_title) not in exclude_norm
                    and article_matches_difficulty(cand, diff_key)
                ):
                    art = pool.pop(i)
                    break
        self.prefetch_articles()
        return art

    async def get_or_create_room_async(
        self,
        room_id: str = "default",
        difficulty: str = "moyen",
        player_id: Optional[str] = None,
        player_name: Optional[str] = None,
        exclude_titles: Optional[Set[str]] = None
    ) -> "Room":
        """Version non bloquante : à utiliser dans les handlers async (WebSocket / routes)."""
        clean_id = (room_id or "").strip() or "default"
        if clean_id in self.rooms:
            return self.rooms[clean_id]
        await asyncio.to_thread(self._ensure_article_ready, difficulty)
        return self.get_or_create_room(
            clean_id,
            difficulty=difficulty,
            player_id=player_id,
            player_name=player_name,
            exclude_titles=exclude_titles
        )

    async def create_new_room_async(
        self,
        host_player_id: str,
        host_name: str = "Host",
        custom_id: Optional[str] = None,
        difficulty: str = "moyen",
        exclude_titles: Optional[Set[str]] = None
    ) -> "Room":
        await asyncio.to_thread(self._ensure_article_ready, difficulty)
        return self.create_new_room(
            host_player_id,
            host_name=host_name,
            custom_id=custom_id,
            difficulty=difficulty,
            exclude_titles=exclude_titles
        )

    def _ensure_article_ready(self, difficulty: str = "moyen"):
        """Garantit qu'un article est disponible dans le pool pour la difficulté demandée."""
        diff_key = difficulty.lower() if difficulty and difficulty.lower() in ("facile", "moyen", "difficile") else "moyen"
        with self._pool_lock:
            ready = bool(self._article_pools.get(diff_key))
        if not ready:
            art = None
            try:
                art = self.wiki_client.fetch_random_wikipedia_article(difficulty=diff_key)
            except Exception as e:
                logger.warning(f"fetch article in _ensure_article_ready: {e}")
            if not art and self.game_manager.offline_curated:
                candidates = [
                    dict(a) for a in self.game_manager.offline_curated.values()
                    if article_matches_difficulty(a, diff_key)
                ]
                if candidates:
                    art = random.choice(candidates)
            if art and article_matches_difficulty(art, diff_key):
                art["difficulty"] = diff_key
                with self._pool_lock:
                    self._article_pools[diff_key].append(art)

    def _fetch_random_article(self, difficulty: str = "moyen", exclude_titles: Optional[Set[str]] = None) -> Dict[str, Any]:
        """Fetches a random notable article from French Wikipedia for the given difficulty, excluding recently played titles."""
        diff_key = difficulty.lower() if difficulty and difficulty.lower() in ("facile", "moyen", "difficile") else "moyen"
        exclude_set = set(exclude_titles) if exclude_titles else set()
        exclude_norm = {normalize_wiki_title(t) for t in exclude_set if t}

        article = None
        # Check if pooled article matches requested difficulty and is not in excluded list
        with self._pool_lock:
            pool = self._article_pools.get(diff_key, [])
            for i, cand in enumerate(pool):
                cand_title = cand.get("title", "")
                if (
                    normalize_wiki_title(cand_title) not in exclude_norm
                    and article_matches_difficulty(cand, diff_key)
                ):
                    article = pool.pop(i)
                    break

        self.prefetch_articles()

        if article is None:
            try:
                article = self.wiki_client.fetch_random_wikipedia_article(difficulty=diff_key, exclude_titles=exclude_set)
            except Exception as e:
                logger.error(f"Error fetching random article: {e}")
        if article and not article_matches_difficulty(article, diff_key):
            article = None

        if not article:
            article = self.wiki_client.fetch_curated_article(difficulty=diff_key, exclude_titles=exclude_set)
        if article and not article_matches_difficulty(article, diff_key):
            article = None

        if not article and self.game_manager.offline_curated:
            candidates = [
                dict(c) for c in self.game_manager.offline_curated.values()
                if article_matches_difficulty(c, diff_key)
                and c.get("title", "") not in exclude_set
                and normalize_wiki_title(c.get("title", "")) not in exclude_norm
            ]
            if candidates:
                article = random.choice(candidates)

        if not article:
            cached_article = get_random_cached_article(exclude_titles=exclude_set)
            if cached_article and article_matches_difficulty(cached_article, diff_key):
                article = cached_article

        cacheable_article = bool(article)
        if not article:
            fallback_candidates = CURATED_BY_DIFFICULTY.get(diff_key, [])
            valid_fallbacks = [
                title for title in fallback_candidates
                if normalize_wiki_title(title) not in exclude_norm
            ]
            if not valid_fallbacks:
                raise RuntimeError(
                    f"Aucun article {diff_key} disponible hors des articles joués récemment."
                )
            cand_title = random.choice(valid_fallbacks)
            article = {
                "title": cand_title,
                "paragraphs": [
                    f"Article sur {cand_title} sur Wikipédia en français.",
                    "Découvrez son histoire, ses caractéristiques et ses éléments majeurs dans cette manche de Pédantix.",
                    "Proposez des mots pour dévoiler le texte secret et trouver le titre de la page !"
                ],
                "image": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/85/Tour_Eiffel_Wikimedia_Commons_%28cropped%29.jpg/500px-Tour_Eiffel_Wikimedia_Commons_%28cropped%29.jpg",
                "url": f"https://fr.wikipedia.org/wiki/{cand_title}",
                "category": "culture",
                "difficulty": diff_key,
                "lang_count": 80 if diff_key == "facile" else (35 if diff_key == "moyen" else 20),
                "pageviews_90d": 40000 if diff_key == "facile" else (8000 if diff_key == "moyen" else 1500)
            }
        if normalize_wiki_title(article.get("title", "")) in exclude_norm:
            raise RuntimeError("La sélection d'article a réintroduit un article déjà joué.")
        if not article_matches_difficulty(article, diff_key):
            raise RuntimeError("La sélection d'article ne correspond pas à la difficulté demandée.")
        article["difficulty"] = diff_key
        if cacheable_article:
            cache_article(
                title=article["title"],
                url=article.get("url", ""),
                image=article.get("image", ""),
                paragraphs=article.get("paragraphs", []),
                category=article.get("category", "general")
            )
        return article

    _fetch_notable_article = _fetch_random_article

    def get_or_create_room(
        self,
        room_id: str = "default",
        difficulty: str = "moyen",
        player_id: Optional[str] = None,
        player_name: Optional[str] = None,
        exclude_titles: Optional[Set[str]] = None
    ) -> Room:
        clean_id = room_id.strip() or "default"
        if clean_id not in self.rooms:
            if exclude_titles is None:
                idents = []
                if player_id:
                    idents.append(player_id.strip().lower())
                elif clean_id.startswith("solo-"):
                    idents.append(clean_id[5:].strip().lower())
                if player_name:
                    cn = player_name.strip().lower()
                    if cn and not cn.startswith("joueur ") and cn != "host":
                        idents.append(cn)
                if idents:
                    exclude_titles = get_recently_played_articles(idents, days=21)

            article = self._fetch_notable_article(difficulty=difficulty, exclude_titles=exclude_titles)
            seed_num = random.randint(1000, 9999)
            seed = f"P-{seed_num}"
            room = Room(room_id=clean_id, article_data=article, seed=seed, difficulty=difficulty)
            if clean_id.startswith("solo-"):
                pid = player_id or clean_id[5:]
                pname = player_name or "Joueur 1"
                room.get_or_create_player(pid, pname)
                room.record_current_article_for_players([pid, pname])
            self.rooms[clean_id] = room
        return self.rooms[clean_id]

    def create_new_room(
        self,
        host_player_id: str,
        host_name: str = "Host",
        custom_id: Optional[str] = None,
        difficulty: str = "moyen",
        exclude_titles: Optional[Set[str]] = None
    ) -> Room:
        if custom_id and custom_id.strip():
            clean_custom = custom_id.strip()
            if clean_custom.startswith("solo-"):
                clean_custom = clean_custom[5:] or f"salon-{random.randint(100, 999)}"
            room_id = clean_custom
        else:
            for _ in range(100):
                cand = f"salon-{random.randint(100, 999)}"
                if cand not in self.rooms:
                    room_id = cand
                    break
            else:
                room_id = f"salon-{random.randint(1000, 9999)}"

        if exclude_titles is None:
            host_idents = [host_player_id.strip().lower()]
            if host_name:
                hn = host_name.strip().lower()
                if hn and not hn.startswith("joueur ") and hn != "host":
                    host_idents.append(hn)
            exclude_titles = get_recently_played_articles(host_idents, days=21)

        article = self._fetch_notable_article(difficulty=difficulty, exclude_titles=exclude_titles)
        seed_num = random.randint(1000, 9999)
        seed = f"P-{seed_num}"
        room = Room(room_id=room_id, article_data=article, seed=seed, difficulty=difficulty)
        room.host_player_id = host_player_id
        # Automatically register the host player so the room is never created empty
        room.get_or_create_player(host_player_id, host_name or "Host")
        self.rooms[room_id] = room
        return room

    def get_room(self, room_id: str) -> Optional[Room]:
        clean_id = (room_id or "").strip()
        return self.rooms.get(clean_id)

    def delete_room(self, room_id: str):
        """Immediately cleans up and deletes a room."""
        clean_id = (room_id or "").strip()
        room = self.rooms.pop(clean_id, None)
        if room:
            room.cleanup()
            logger.info(f"Room « {clean_id} » supprimée car vide.")

    def cleanup_abandoned_rooms(self):
        """Cleans up inactive rooms safely without dropping rooms during temporary disconnects/refreshes."""
        now = time.time()
        to_delete = []
        for rid, r in list(self.rooms.items()):
            if rid == "default":
                continue
            # Solo rooms: delete after 30 min of total inactivity
            if rid.startswith("solo-"):
                if len(r.players) == 0 and (now - r.created_at > 1800):
                    to_delete.append(rid)
                elif len(r.players) > 0 and all(
                    not p.connected and p.disconnected_at and (now - p.disconnected_at > 1800)
                    for p in r.players.values()
                ):
                    to_delete.append(rid)
                continue

            # Keep multiplayer rooms available throughout the WebSocket reconnect grace period.
            if len(r.players) == 0:
                to_delete.append(rid)
            elif all(
                not p.connected
                and p.disconnected_at is not None
                and now - p.disconnected_at > PLAYER_DISCONNECT_GRACE_SECONDS
                for p in r.players.values()
            ):
                to_delete.append(rid)

        for rid in to_delete:
            self.delete_room(rid)

    def list_active_rooms(self) -> List[Dict[str, Any]]:
        """Returns a list of all active public rooms with player counts and statuses."""
        self.cleanup_abandoned_rooms()

        active = []
        for r in list(self.rooms.values()):
            if r.room_id.startswith("solo-"):
                continue  # Never expose private solo rooms
            active_ws_pids = set(r.ws_player_map.values())
            for player in r.players.values():
                if player.player_id in active_ws_pids:
                    player.connected = True
                    player.disconnected_at = None
                    task = r._disconnect_tasks.pop(player.player_id, None)
                    if task and not task.done():
                        task.cancel()
                elif player.connected or player.disconnected_at is None:
                    r.mark_player_disconnected(player.player_id)
            connected_names = [
                p.name for p in r.players.values()
                if p.player_id in active_ws_pids
            ]
            active_count = len(connected_names)
            if not r.players:
                continue
            active.append({
                "room_id": r.room_id,
                "players_count": active_count,
                "reconnecting_players_count": len(r.players) - active_count,
                "players": connected_names[:6],
                "status": r.status,
                "game_mode": r.game_mode,
                "difficulty": r.difficulty,
                "host_name": r.players.get(r.host_player_id).name if r.host_player_id and r.host_player_id in r.players else "Anonyme",
                "created_at": r.created_at,
                "rounds_played": r.rounds_played
            })
        active.sort(key=lambda x: (x["players_count"] > 0, x["players_count"], x["created_at"]), reverse=True)
        return active

# Global RoomManager instance
room_manager = RoomManager()
