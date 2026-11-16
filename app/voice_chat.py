from typing import Any

VOICE_SIGNAL_KINDS = frozenset({"ready", "offer", "answer"})
VOICE_SIGNAL_MAX_SDP_LENGTH = 20_000
VOICE_SIGNAL_MAX_SESSION_LENGTH = 64


def default_voice_chat_state() -> dict[str, Any]:
    return {"enabled": False, "members": [], "muted": {}, "host_id": None}


class VoiceChatMixin:
    """Salon vocal d'une room : `voice_chat`, `players`, `host_player_id` et `room_id` sont requis."""

    voice_chat: dict[str, Any]
    host_player_id: Any
    room_id: str

    def _sanitize_voice_chat_members(self) -> None:
        participants = self.players
        members = []
        for player_id in self.voice_chat.get("members", []):
            if player_id in participants and player_id not in members:
                members.append(player_id)
        muted = self.voice_chat.get("muted", {})
        self.voice_chat["members"] = members
        self.voice_chat["muted"] = {
            player_id: bool(muted.get(player_id, False)) for player_id in members
        }
        self.voice_chat["host_id"] = self.host_player_id

    def get_voice_chat_state(self) -> dict[str, Any]:
        self._sanitize_voice_chat_members()
        return {
            "enabled": bool(self.voice_chat.get("enabled", False)),
            "members": list(self.voice_chat["members"]),
            "muted": dict(self.voice_chat["muted"]),
            "host_id": self.host_player_id,
            "room_id": self.room_id,
        }

    def toggle_voice_chat(self, player_id: str, enabled: bool | None = None) -> dict[str, Any]:
        if player_id != self.host_player_id:
            return self.get_voice_chat_state()
        if enabled is None:
            enabled = not bool(self.voice_chat.get("enabled", False))
        self.voice_chat["enabled"] = bool(enabled)
        if not self.voice_chat["enabled"]:
            self.voice_chat["members"] = []
            self.voice_chat["muted"] = {}
        return self.get_voice_chat_state()

    def join_voice_chat(self, player_id: str) -> dict[str, Any]:
        if player_id in self.players and self.voice_chat.get("enabled", False):
            members = self.voice_chat.setdefault("members", [])
            if player_id not in members:
                members.append(player_id)
            self.voice_chat.setdefault("muted", {}).setdefault(player_id, False)
        return self.get_voice_chat_state()

    def leave_voice_chat(self, player_id: str) -> dict[str, Any]:
        members = self.voice_chat.setdefault("members", [])
        if player_id in members:
            members.remove(player_id)
        self.voice_chat.setdefault("muted", {}).pop(player_id, None)
        return self.get_voice_chat_state()

    def set_voice_chat_muted(self, player_id: str, muted: bool) -> dict[str, Any]:
        if player_id in self.voice_chat.get("members", []) and player_id in self.players:
            self.voice_chat.setdefault("muted", {})[player_id] = bool(muted)
        return self.get_voice_chat_state()

    def build_voice_signal(self, sender_id: Any, target_id: Any, signal: Any) -> dict[str, Any]:
        state = self.get_voice_chat_state()
        members = state["members"]
        if (
            not state["enabled"]
            or sender_id not in members
            or target_id not in members
            or sender_id == target_id
        ):
            raise ValueError("Les deux joueurs doivent être dans le salon vocal.")
        if not isinstance(signal, dict) or signal.get("kind") not in VOICE_SIGNAL_KINDS:
            raise ValueError("Signal vocal invalide.")
        session = signal.get("session")
        if not isinstance(session, str) or not 0 < len(session) <= VOICE_SIGNAL_MAX_SESSION_LENGTH:
            raise ValueError("Session vocale invalide.")
        clean = {"kind": signal["kind"], "session": session}
        if signal["kind"] != "ready":
            sdp = signal.get("sdp")
            if not isinstance(sdp, str) or not 0 < len(sdp) <= VOICE_SIGNAL_MAX_SDP_LENGTH:
                raise ValueError("Description de session vocale invalide.")
            clean["sdp"] = sdp
        return {"type": "voice_chat_signal", "from_player_id": sender_id, "signal": clean}
