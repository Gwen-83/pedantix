import asyncio
import json
import threading
import logging
import random
import time
import uuid
from collections import Counter
from typing import Dict, List, Optional, Set, Any
from fastapi import WebSocket

from app.game import GameSession, GameManager
from app.wiki import ALL_CURATED_TITLES, WikipediaClient
from app.database import get_player_score, increment_player_score
from app.nlp import normalize_letter, is_letter_revealed

logger = logging.getLogger("pedantix.room")

TEAM_METADATA = {
    "blue": {"name": "Équipe Bleue", "short": "Bleue", "icon": "🔵", "color": "#3b82f6"},
    "red": {"name": "Équipe Rouge", "short": "Rouge", "icon": "🔴", "color": "#ef4444"},
    "green": {"name": "Équipe Verte", "short": "Verte", "icon": "🟢", "color": "#10b981"},
    "yellow": {"name": "Équipe Jaune", "short": "Jaune", "icon": "🟡", "color": "#eab308"},
}
ALL_TEAMS = ["blue", "red", "green", "yellow"]

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

    def refresh_score(self):
        self.score = get_player_score(self.name)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "player_id": self.player_id,
            "name": self.name,
            "is_host": self.is_host,
            "team": self.team,
            "is_ready": self.is_ready,
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
            "connected": self.connected
        }


class Room:
    def __init__(self, room_id: str, article_data: Dict[str, Any], seed: str):
        self.room_id = room_id
        self.article_data = article_data
        self.seed = seed
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
        self.winning_team: Optional[str] = None
        self._countdown_task: Optional[asyncio.Task] = None
        self._timer_30s_task: Optional[asyncio.Task] = None
        self.revealed_letters: List[str] = []
        self._letter_hint_task: Optional[asyncio.Task] = None
        self.letter_hint_interval: float = 300.0  # 5 minutes = 300 seconds
        self.next_letter_hint_time: Optional[float] = None

    def _pick_next_hint_letter(self) -> Optional[str]:
        """
        Picks an unrevealed letter from the secret article.
        Prioritizes letters appearing in the title, ordered by overall frequency in the text.
        """
        rev_set = set(self.revealed_letters)
        title = self.article_data.get("title", "")
        paragraphs = self.article_data.get("paragraphs", [])
        full_text = title + " " + " ".join(paragraphs)

        letter_counts = Counter()
        for ch in full_text:
            norm = normalize_letter(ch)
            for single_char in norm:
                if single_char and single_char not in rev_set:
                    letter_counts[single_char] += 1

        if not letter_counts:
            return None

        # Check unrevealed title letters
        title_letters = set()
        for ch in title:
            norm = normalize_letter(ch)
            for single_char in norm:
                if single_char and single_char not in rev_set:
                    title_letters.add(single_char)

        if title_letters:
            return max(title_letters, key=lambda l: letter_counts[l])

        # Otherwise pick the most common letter remaining in the body
        return letter_counts.most_common(1)[0][0]

    def get_tokens_hint_patterns(self) -> Dict[str, str]:
        """
        Returns a mapping of token_id (str) -> hint_pattern for all unrevealed tokens,
        based on currently revealed letters (self.revealed_letters).
        """
        if not self.revealed_letters:
            return {}

        rev_set = set(self.revealed_letters)
        sess = None
        if self.game_mode == "team" and self.team_sessions:
            sess = next(iter(self.team_sessions.values()), None)
        elif self.players:
            sess = next(iter(self.players.values())).session

        if not sess:
            return {}

        hints = {}
        for t in sess.tokens:
            if t.get("is_word") and not t.get("revealed"):
                tok_text = t.get("text", "")
                pat = "".join(
                    ch if is_letter_revealed(ch, rev_set) else "_"
                    for ch in tok_text
                )
                if any(c != "_" for c in pat):
                    hints[str(t["id"])] = pat
        return hints

    async def _run_letter_hint_loop(self):
        try:
            while self.status == "playing" and not self.first_winner_id:
                await asyncio.sleep(self.letter_hint_interval)
                if self.status != "playing" or self.first_winner_id:
                    break

                next_letter = self._pick_next_hint_letter()
                if not next_letter:
                    break

                self.revealed_letters.append(next_letter)
                self.next_letter_hint_time = time.time() + self.letter_hint_interval
                mins = len(self.revealed_letters) * 5
                hint_msg = f"💡 Indice des {mins} min : la lettre « {next_letter.upper()} » a été dévoilée partout !"
                self.add_activity(hint_msg, "hint")

                token_hints = self.get_tokens_hint_patterns()
                await self.broadcast({
                    "type": "letter_hint",
                    "letter": next_letter.upper(),
                    "revealed_letters": self.revealed_letters,
                    "token_hints": token_hints,
                    "token_patterns": token_hints,
                    "next_letter_hint_time": self.next_letter_hint_time,
                    "next_hint_time": self.next_letter_hint_time,
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
                category=self.article_data.get("category", "general")
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

    def get_leaderboard(self) -> List[Dict[str, Any]]:
        """Returns players sorted by victory status, then highest percentage, then lowest attempts, then DB score."""
        player_list = [p.to_dict() for p in self.players.values()]

        def sort_key(p):
            is_won = 1 if p["is_won"] else 0
            pct = p["pct"]
            attempts = -p["attempts"] if p["attempts"] > 0 else -9999
            score = p["score"]
            return (is_won, pct, attempts, score)

        player_list.sort(key=sort_key, reverse=True)
        return player_list

    def can_start(self) -> bool:
        """Returns True if there is at least one player and all players are ready."""
        if not self.players:
            return False
        if not all(p.is_ready for p in self.players.values()):
            return False
        if self.game_mode == "team" and len(self.players) >= 2:
            occupied_teams = set(p.team for p in self.players.values())
            if len(occupied_teams) < 2:
                return False
        return True

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
            player.connected = True
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
                mode="multiplayer",
                category=self.article_data.get("category", "general")
            )

        player = RoomPlayer(player_id=player_id, name=player_name, session=session, is_host=is_first, team=default_team)
        if self.room_id.startswith("solo-"):
            player.is_ready = True
            player.is_host = True
            self.status = "playing"
        self.players[player_id] = player
        team_meta = TEAM_METADATA.get(default_team, {})
        team_tag = f" ({team_meta.get('icon', '')} {team_meta.get('short', '')})" if self.game_mode == "team" else ""
        self.add_activity(f"👋 {player_name} a rejoint la salle{' (Host 👑)' if is_first else ''}{team_tag}", "join")
        return player

    def toggle_ready(self, player_id: str, ready: Optional[bool] = None) -> bool:
        if player_id not in self.players:
            return False
        player = self.players[player_id]
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
            not_ready_count = sum(1 for p in self.players.values() if not p.is_ready)
            return {"error": f"Impossible de lancer : {not_ready_count} joueur(s) ne sont pas encore prêts."}

        # If a previous round was already finished, launch a new round with a fresh article
        if self.rounds_played > 0:
            return await self.start_new_round(player_id)

        if self.game_mode == "team":
            if not self.team_sessions:
                self._init_team_sessions()
            for p in self.players.values():
                if p.team in self.team_sessions:
                    p.session = self.team_sessions[p.team]

        self.winners = []
        self.first_winner_id = None
        self.first_winner_name = None
        self.first_winner_attempts = None
        self.status = "starting"
        self.countdown_end = time.time() + 5.0
        self.add_activity("⏳ Compte à rebours de 5 secondes lancé !", "countdown")

        # Broadcast countdown to all players
        await self.broadcast({
            "type": "countdown_started",
            "seconds": 5,
            "end_time": self.countdown_end,
            "status": self.status,
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
            self.revealed_letters = []
            self.next_letter_hint_time = time.time() + self.letter_hint_interval
            self.add_activity("🚀 La partie a commencé ! Bonne chance à tous !", "start")

            if self._letter_hint_task and not self._letter_hint_task.done():
                self._letter_hint_task.cancel()
            self._letter_hint_task = asyncio.create_task(self._run_letter_hint_loop())

            await self.broadcast({
                "type": "game_started",
                "status": "playing",
                "leaderboard": self.get_leaderboard(),
                "activity": self.recent_activity,
                "next_letter_hint_time": self.next_letter_hint_time,
                "revealed_letters": self.revealed_letters
            })
        except asyncio.CancelledError:
            pass

    def process_guess(self, player_id: str, word: str) -> Dict[str, Any]:
        if player_id not in self.players:
            return {"error": "Joueur non trouvé dans la salle."}

        if self.status not in ("playing", "ending"):
            if self.status == "lobby":
                return {"error": "La partie n'a pas encore été lancée par l'Host."}
            elif self.status == "starting":
                return {"error": "La partie démarre dans quelques secondes..."}
            elif self.status == "round_over":
                return {"error": "Cette manche est terminée. Attendez la suivante !"}

        player = self.players[player_id]

        # Use team session if in team mode, else player session
        if self.game_mode == "team":
            if not self.team_sessions:
                self._init_team_sessions()
            session = self.team_sessions.get(player.team)
            if not session:
                session = player.session
        else:
            session = player.session

        guess_res = session.submit_guess(word)

        if "error" in guess_res or guess_res.get("is_repeat") or guess_res.get("status") == "already_guessed":
            return guess_res

        # Update progress
        attempts = guess_res["attempt_number"]
        revealed_count = guess_res["revealed_words_count"]
        total_words = guess_res["total_words"]
        pct = round((revealed_count / max(1, total_words)) * 100)
        status = guess_res["status"]
        matches_count = guess_res["matches_count"]
        score = guess_res.get("score", 0)

        if self.game_mode == "team":
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

        # Check win
        if guess_res["is_won"]:
            if self.game_mode == "team":
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

                    if self._letter_hint_task and not self._letter_hint_task.done():
                        self._letter_hint_task.cancel()
                    self.next_letter_hint_time = None

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
                    active_teams = set(p.team for p in self.players.values() if p.connected)
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
                    if rank == 1:
                        self.first_winner_id = player.player_id
                        self.first_winner_name = player.name
                        self.first_winner_attempts = player.attempts
                        self.status = "ending"
                        self.timer_30s_end = time.time() + 30.0
                        self.add_activity(f"🏆 {player.name} a découvert le titre en {player.attempts} coups ! 30s restantes pour les autres !", "win")
                        if self._letter_hint_task and not self._letter_hint_task.done():
                            self._letter_hint_task.cancel()
                        self.next_letter_hint_time = None
                        if self._timer_30s_task and not self._timer_30s_task.done():
                            self._timer_30s_task.cancel()
                        self._timer_30s_task = asyncio.create_task(self._run_30s_timer())
                    else:
                        pts_bonus = "+2 pt" if rank == 2 else ("+1 pt" if rank == 3 else "0 pt")
                        self.add_activity(f"🎯 {player.name} a également découvert le titre ({rank}e place, {pts_bonus}) !", "win_also")

                        connected_players = [p for p in self.players.values() if p.connected]
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
        self.status = "lobby"
        self.rounds_played += 1
        self.timer_30s_end = None

        if self._letter_hint_task and not self._letter_hint_task.done():
            self._letter_hint_task.cancel()
        self.revealed_letters = []
        self.next_letter_hint_time = None

        round_podium = []
        if self.game_mode == "team":
            if self.winning_team:
                win_meta = TEAM_METADATA.get(self.winning_team, {})
                win_team_name = f"{win_meta.get('name', self.winning_team)} {win_meta.get('icon', '')}"
                self.add_activity(f"🏆 Victoire de l'{win_team_name} ! (+3 pts pour tous les équipiers)", "score")
                for p in self.players.values():
                    if p.team == self.winning_team:
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
                                if p.team == other_team:
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

        # Refresh all player scores from DB and reset ready status for next round
        for p in self.players.values():
            p.refresh_score()
            p.is_ready = False

        self.last_round_results = {
            "title": self.article_data["title"],
            "url": self.article_data.get("url", ""),
            "image": self.article_data.get("image", ""),
            "podium": round_podium,
            "winners_count": len(self.winners),
            "game_mode": self.game_mode,
            "winning_team": self.winning_team
        }

        # Broadcast round over and return to lobby
        await self.broadcast({
            "type": "round_over_to_lobby",
            "status": "lobby",
            "winner_name": self.first_winner_name,
            "winner_attempts": self.first_winner_attempts,
            "game_mode": self.game_mode,
            "winning_team": self.winning_team,
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
            "can_start": self.can_start()
        })

    async def start_new_round(self, player_id: str, new_article: Optional[Dict[str, Any]] = None, new_seed: Optional[str] = None) -> Dict[str, Any]:
        """Host launches a new round: verifies host and that everyone clicked ready."""
        if player_id not in self.players:
            return {"error": "Joueur non trouvé"}
        player = self.players[player_id]
        if not player.is_host:
            return {"error": "Seul l'Host peut lancer la partie."}
        if not self.can_start():
            not_ready = [p.name for p in self.players.values() if not p.is_ready]
            return {"error": f"En attente que tous les joueurs soient prêts : {', '.join(not_ready)}"}

        if self._timer_30s_task and not self._timer_30s_task.done():
            self._timer_30s_task.cancel()
        if self._countdown_task and not self._countdown_task.done():
            self._countdown_task.cancel()
        if self._letter_hint_task and not self._letter_hint_task.done():
            self._letter_hint_task.cancel()
        self.revealed_letters = []
        self.next_letter_hint_time = None

        if not new_article:
            new_article = room_manager._fetch_notable_article()
        if not new_seed:
            new_seed = f"P-{random.randint(1000, 9999)}"

        self.article_data = new_article
        self.seed = new_seed
        self.status = "starting"
        self.countdown_end = time.time() + 5.0
        self.timer_30s_end = None
        self.first_winner_id = None
        self.first_winner_name = None
        self.first_winner_attempts = None
        self.winners = []
        self.winning_team = None
        self.created_at = time.time()

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
                    mode="multiplayer",
                    category=self.article_data.get("category", "general")
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
            await self.broadcast({
                "type": "new_round",
                "status": "playing",
                "seed": self.seed,
                "game_mode": self.game_mode,
                "teams": self.get_teams_data(),
                "leaderboard": self.get_leaderboard(),
                "activity": self.recent_activity
            })
            return {"status": "playing", "seed": self.seed}

        self.add_activity("🎲 Nouvelle partie lancée ! Compte à rebours de 5 secondes...", "new_round")

        await self.broadcast({
            "type": "countdown_started",
            "seconds": 5,
            "end_time": self.countdown_end,
            "status": "starting",
            "seed": self.seed,
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
        return session.unmask_all()

    start_next_round = start_new_round

    def cleanup(self):
        """Cancels all background tasks and clears websockets."""
        if self._countdown_task and not self._countdown_task.done():
            self._countdown_task.cancel()
        if self._timer_30s_task and not self._timer_30s_task.done():
            self._timer_30s_task.cancel()
        if self._letter_hint_task and not self._letter_hint_task.done():
            self._letter_hint_task.cancel()
        self.websockets.clear()
        self.ws_player_map.clear()

    def add_websocket(self, ws: WebSocket, player_id: Optional[str] = None):
        self.websockets.add(ws)
        if player_id:
            self.ws_player_map[ws] = player_id

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
                player.connected = False
                if self.status == "lobby":
                    await self.remove_player(pid, reason="disconnect")
                else:
                    # In game: check if ALL players are disconnected
                    any_connected = any(p.connected for p in self.players.values())
                    if not any_connected and self.room_id != "default":
                        room_manager.delete_room(self.room_id)
                        return

                    await self.broadcast({
                        "type": "player_disconnected",
                        "player_id": pid,
                        "player_name": player.name,
                        "leaderboard": self.get_leaderboard(),
                        "teams": self.get_teams_data(),
                        "can_start": self.can_start()
                    })

    async def remove_player(self, player_id: str, reason: str = "leave") -> bool:
        if player_id not in self.players:
            return False

        player = self.players.pop(player_id)
        player_name = player.name

        for ws, pid in list(self.ws_player_map.items()):
            if pid == player_id:
                self.ws_player_map.pop(ws, None)
                self.websockets.discard(ws)

        # Si le salon n'a plus aucun membre, le salon est immédiatement supprimé
        if len(self.players) == 0:
            if self.room_id != "default":
                room_manager.delete_room(self.room_id)
            return True

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
            "leaderboard": self.get_leaderboard(),
            "teams": self.get_teams_data(),
            "can_start": self.can_start(),
            "activity": self.recent_activity
        })
        return True

    def identify_websocket(self, ws: WebSocket, player_id: str):
        if player_id:
            self.ws_player_map[ws] = player_id

    async def broadcast(self, message: Dict[str, Any]):
        to_remove = set()
        is_team_guess = "team_guess" in message and message.get("game_mode") == "team"

        for ws in list(self.websockets):
            try:
                if is_team_guess:
                    recipient_pid = self.ws_player_map.get(ws)
                    recipient_player = self.players.get(recipient_pid) if recipient_pid else None
                    guess_team = message.get("team")

                    if recipient_player and recipient_player.team == guess_team:
                        # Full message for teammates
                        await ws.send_text(json.dumps(message))
                    else:
                        # Redacted message for opposing team / spectators
                        sanitized_msg = dict(message)
                        sanitized_msg["title"] = None
                        raw_team_guess = message.get("team_guess", {})
                        sanitized_msg["team_guess"] = {
                            "player_id": raw_team_guess.get("player_id"),
                            "player_name": raw_team_guess.get("player_name"),
                            "team": raw_team_guess.get("team"),
                            "word": "••••",
                            "status": raw_team_guess.get("status"),
                            "matches_count": raw_team_guess.get("matches_count", 0),
                            "score": raw_team_guess.get("score", 0),
                            "newly_revealed": {},
                            "close_tokens": [],
                            "history_entry": None
                        }
                        await ws.send_text(json.dumps(sanitized_msg))
                else:
                    await ws.send_text(json.dumps(message))
            except Exception:
                to_remove.add(ws)

        for dead_ws in to_remove:
            self.remove_websocket(dead_ws)


class RoomManager:
    def __init__(self):
        self.rooms: Dict[str, Room] = {}
        self.wiki_client = WikipediaClient()
        self.game_manager = GameManager()
        self._article_pool: List[Dict[str, Any]] = []
        self._pool_lock = threading.Lock()
        self._refilling = False

    # -- Pool d'articles préchargés : la création d'un salon devient instantanée
    def prefetch_articles(self, target: int = 3):
        """Remplit le pool en arrière-plan (thread) sans jamais bloquer la boucle asyncio."""
        with self._pool_lock:
            if self._refilling or len(self._article_pool) >= target:
                return
            self._refilling = True

        def _worker():
            try:
                for _ in range(target * 2):
                    with self._pool_lock:
                        if len(self._article_pool) >= target:
                            break
                    try:
                        art = self.wiki_client.fetch_random_wikipedia_article()
                    except Exception as e:
                        logger.warning(f"prefetch article: {e}")
                        art = None
                    if art:
                        with self._pool_lock:
                            self._article_pool.append(art)
            finally:
                with self._pool_lock:
                    self._refilling = False

        threading.Thread(target=_worker, daemon=True, name="pedantix-article-prefetch").start()

    def _pop_pooled_article(self) -> Optional[Dict[str, Any]]:
        with self._pool_lock:
            art = self._article_pool.pop(0) if self._article_pool else None
        self.prefetch_articles()
        return art

    async def get_or_create_room_async(self, room_id: str = "default") -> "Room":
        """Version non bloquante : à utiliser dans les handlers async (WebSocket / routes)."""
        clean_id = (room_id or "").strip() or "default"
        if clean_id in self.rooms:
            return self.rooms[clean_id]
        await asyncio.to_thread(self._ensure_article_ready)
        return self.get_or_create_room(clean_id)

    async def create_new_room_async(self, host_player_id: str, custom_id: Optional[str] = None) -> "Room":
        await asyncio.to_thread(self._ensure_article_ready)
        return self.create_new_room(host_player_id, custom_id)

    def _ensure_article_ready(self):
        """Garantit qu'un article est disponible dans le pool (appelé hors boucle asyncio)."""
        with self._pool_lock:
            ready = bool(self._article_pool)
        if not ready:
            try:
                art = self.wiki_client.fetch_random_wikipedia_article()
            except Exception as e:
                logger.error(f"fetch article: {e}")
                art = None
            if art:
                with self._pool_lock:
                    self._article_pool.append(art)

    def _fetch_random_article(self) -> Dict[str, Any]:
        """Fetches a random notable article from French Wikipedia (satisfying language count criteria)."""
        article = self._pop_pooled_article()
        if article is None:
            try:
                article = self.wiki_client.fetch_random_wikipedia_article()
            except Exception as e:
                logger.error(f"Error fetching random article: {e}")

        if not article and self.game_manager.offline_curated:
            article = random.choice(list(self.game_manager.offline_curated.values()))

        if not article:
            article = {
                "title": "Tour Eiffel",
                "paragraphs": [
                    "La tour Eiffel est une tour autoportante de fer puddlé de 330 m de hauteur située à Paris, à l’extrémité nord-ouest du parc du Champ-de-Mars en bordure de la Seine dans le 7e arrondissement.",
                    "Construite en deux ans par Gustave Eiffel et ses collaborateurs pour l'Exposition universelle de Paris de 1889, célébrant le centenaire de la Révolution française, elle est devenue le symbole emblématique de la capitale française et de la France entière.",
                    "D’une hauteur de 312 mètres à l’origine, la tour Eiffel est restée le monument le plus élevé du monde pendant quarante ans. Elle accueille chaque année plus de six millions de visiteurs du monde entier."
                ],
                "image": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/85/Tour_Eiffel_Wikimedia_Commons_%28cropped%29.jpg/500px-Tour_Eiffel_Wikimedia_Commons_%28cropped%29.jpg",
                "url": "https://fr.wikipedia.org/wiki/Tour_Eiffel",
                "category": "monuments"
            }
        return article

    _fetch_notable_article = _fetch_random_article

    def get_or_create_room(self, room_id: str = "default") -> Room:
        clean_id = room_id.strip() or "default"
        if clean_id not in self.rooms:
            article = self._fetch_notable_article()
            seed_num = random.randint(1000, 9999)
            seed = f"P-{seed_num}"
            self.rooms[clean_id] = Room(room_id=clean_id, article_data=article, seed=seed)
        return self.rooms[clean_id]

    def create_new_room(self, host_player_id: str, custom_id: Optional[str] = None) -> Room:
        room_id = custom_id.strip() if custom_id else f"salon-{random.randint(100, 999)}"
        article = self._fetch_notable_article()
        seed_num = random.randint(1000, 9999)
        seed = f"P-{seed_num}"
        room = Room(room_id=room_id, article_data=article, seed=seed)
        room.host_player_id = host_player_id
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

    def list_active_rooms(self) -> List[Dict[str, Any]]:
        """Returns a list of all active public rooms with player counts and statuses."""
        # Clean up any empty rooms
        empty_ids = [
            rid for rid, r in list(self.rooms.items())
            if rid != "default" and (len(r.players) == 0 or not any(p.connected for p in r.players.values()))
        ]
        for rid in empty_ids:
            self.delete_room(rid)

        active = []
        for r in list(self.rooms.values()):
            if r.room_id.startswith("solo-"):
                continue  # Never expose private solo rooms
            connected_names = [p.name for p in r.players.values() if p.connected]
            active_count = len(connected_names)
            if active_count == 0 and r.room_id != "default":
                continue
            active.append({
                "room_id": r.room_id,
                "players_count": active_count,
                "players": connected_names[:6],
                "status": r.status,
                "game_mode": r.game_mode,
                "host_name": r.players.get(r.host_player_id).name if r.host_player_id and r.host_player_id in r.players else "Anonyme",
                "created_at": r.created_at,
                "rounds_played": r.rounds_played
            })
        active.sort(key=lambda x: (x["players_count"] > 0, x["players_count"], x["created_at"]), reverse=True)
        return active

# Global RoomManager instance
room_manager = RoomManager()
