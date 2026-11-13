import random
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


GAME_ID = "tarot-africain"
MIN_PLAYERS = 2
MAX_PLAYERS = 6
DECK_SIZE = 22
EXCUSE = 0
EXCUSE_VALUES = {"min": 0, "max": 22}
CARDS_PER_PLAYER = {2: 11, 3: 7, 4: 5, 5: 4, 6: 3}
ACTION_SECONDS = 60
BOT_DELAY_SECONDS = 1.2
TRICK_PAUSE_SECONDS = 2.5
ROUND_SUMMARY_SECONDS = 8
MAX_BID = 99
MAX_LOG_ENTRIES = 40

ROUND_NORMAL = "normal"
ROUND_SINGLE_VISIBLE = "single_visible"
ROUND_SINGLE_HIDDEN = "single_hidden"


def _clean_name(name: str) -> str:
    return re.sub(r"[\x00-\x1f\x7f<>]", "", name).strip()[:24] or "Joueur"


def card_label(card: int, excuse_mode: str | None = None) -> str:
    if card != EXCUSE:
        return str(card)
    if excuse_mode is None:
        return "l’Excuse"
    return f"l’Excuse en {excuse_mode.upper()} ({EXCUSE_VALUES[excuse_mode]})"


def build_schedule(player_count: int, first_dealer: int) -> list[tuple[int, int, str]]:
    max_cards = CARDS_PER_PLAYER[player_count]
    schedule = []
    for offset in range(player_count):
        dealer = (first_dealer + offset) % player_count
        for cards in range(max_cards, 1, -1):
            schedule.append((dealer, cards, ROUND_NORMAL))
        schedule.append((dealer, 1, ROUND_SINGLE_VISIBLE))
        schedule.append((dealer, 1, ROUND_SINGLE_HIDDEN))
    return schedule


@dataclass
class TarotSeat:
    player_id: str
    name: str
    is_bot: bool = False
    penalties: int = 0
    hand: list[int] = field(default_factory=list)
    bid: int | None = None
    tricks: int = 0
    exact_bids: int = 0


@dataclass
class TarotRoom:
    room_id: str
    host_player_id: str
    seats: list[TarotSeat] = field(default_factory=list)
    status: str = "lobby"
    phase: str = "lobby"
    match_number: int = 1
    schedule: list[tuple[int, int, str]] = field(default_factory=list)
    round_index: int = -1
    current_seat: int | None = None
    leader_seat: int | None = None
    trick: list[dict[str, Any]] = field(default_factory=list)
    trick_number: int = 0
    trick_winner_seat: int | None = None
    deadline: float | None = None
    turn_started_at: float | None = None
    history: list[dict[str, Any]] = field(default_factory=list)
    log: list[dict[str, Any]] = field(default_factory=list)
    started_at: float | None = None
    created_at: float = field(default_factory=time.time)
    stats_recorded: bool = False

    @property
    def players(self) -> dict[str, TarotSeat]:
        return {seat.player_id: seat for seat in self.seats if not seat.is_bot}

    @property
    def round_spec(self) -> tuple[int, int, str] | None:
        if 0 <= self.round_index < len(self.schedule):
            return self.schedule[self.round_index]
        return None

    def seat_index(self, player_id: str) -> int | None:
        return next(
            (index for index, seat in enumerate(self.seats) if seat.player_id == player_id),
            None,
        )

    def winner_ids(self) -> list[str]:
        if self.status != "finished" or not self.seats:
            return []
        lowest = min(seat.penalties for seat in self.seats)
        return [seat.player_id for seat in self.seats if seat.penalties == lowest]

    def forbidden_dealer_bid(self) -> int | None:
        spec = self.round_spec
        if spec is None or self.phase != "bidding" or self.current_seat != spec[0]:
            return None
        others = sum(
            seat.bid for index, seat in enumerate(self.seats)
            if index != spec[0] and seat.bid is not None
        )
        forbidden = spec[1] - others
        return forbidden if forbidden >= 0 else None

    def _hand_visible(self, viewer: int | None, owner: int) -> bool:
        spec = self.round_spec
        if viewer is None or spec is None or self.status != "playing":
            return False
        if spec[2] == ROUND_SINGLE_HIDDEN:
            return owner != viewer or self.phase != "bidding"
        return owner == viewer

    def to_dict(self, player_id: str) -> dict[str, Any]:
        viewer = self.seat_index(player_id)
        if viewer is None:
            raise KeyError("Salon ou joueur introuvable.")
        spec = self.round_spec
        now = time.time()
        seats = []
        for index, seat in enumerate(self.seats):
            visible = self._hand_visible(viewer, index)
            seats.append({
                "player_id": seat.player_id,
                "name": seat.name,
                "is_bot": seat.is_bot,
                "is_host": seat.player_id == self.host_player_id,
                "is_self": index == viewer,
                "penalties": seat.penalties,
                "bid": seat.bid,
                "tricks": seat.tricks,
                "hand_count": len(seat.hand),
                "hand": sorted(seat.hand) if visible else None,
                "is_dealer": spec is not None and spec[0] == index,
                "is_current": self.current_seat == index,
            })
        round_info = None
        if spec is not None and self.status == "playing":
            dealer, cards, kind = spec
            rounds_per_cycle = CARDS_PER_PLAYER[len(self.seats)] + 1
            round_info = {
                "number": self.round_index + 1,
                "total": len(self.schedule),
                "dealer_seat": dealer,
                "cards_per_player": cards,
                "kind": kind,
                "set_aside_count": DECK_SIZE - cards * len(self.seats),
                "cycle_number": self.round_index // rounds_per_cycle + 1,
                "cycle_count": len(self.seats),
                "round_in_cycle": self.round_index % rounds_per_cycle + 1,
                "rounds_per_cycle": rounds_per_cycle,
                "bids_total": sum(seat.bid or 0 for seat in self.seats),
            }
        return {
            "room_id": self.room_id,
            "host_player_id": self.host_player_id,
            "status": self.status,
            "phase": self.phase,
            "match_number": self.match_number,
            "my_seat": viewer,
            "seats": seats,
            "player_count": len(self.seats),
            "min_players": MIN_PLAYERS,
            "max_players": MAX_PLAYERS,
            "can_start": (
                self.status == "lobby"
                and MIN_PLAYERS <= len(self.seats) <= MAX_PLAYERS
                and player_id == self.host_player_id
            ),
            "can_restart": self.status == "finished" and player_id == self.host_player_id,
            "round": round_info,
            "current_seat": self.current_seat,
            "leader_seat": self.leader_seat,
            "is_my_turn": (
                self.status == "playing"
                and self.phase in {"bidding", "playing"}
                and self.current_seat == viewer
            ),
            "forbidden_bid": (
                self.forbidden_dealer_bid() if self.current_seat == viewer else None
            ),
            "max_bid": MAX_BID,
            "trick": [dict(entry) for entry in self.trick],
            "trick_number": self.trick_number,
            "trick_winner_seat": self.trick_winner_seat,
            "seconds_remaining": (
                max(0, int(self.deadline - now + 0.999)) if self.deadline else 0
            ),
            "action_seconds": ACTION_SECONDS,
            "history": [dict(item) for item in self.history],
            "log": self.log[-MAX_LOG_ENTRIES:],
            "winner_ids": self.winner_ids(),
        }


class TarotAfricainManager:
    def __init__(self, rng: random.Random | None = None) -> None:
        self.rooms: dict[str, TarotRoom] = {}
        self._lock = threading.RLock()
        self._rng = rng or random.SystemRandom()

    def create_room(self, player_id: str, player_name: str) -> TarotRoom:
        with self._lock:
            room_id = uuid.uuid4().hex[:6].upper()
            while room_id in self.rooms:
                room_id = uuid.uuid4().hex[:6].upper()
            room = TarotRoom(room_id=room_id, host_player_id=player_id)
            room.seats.append(TarotSeat(player_id, _clean_name(player_name)))
            self.rooms[room_id] = room
            return room

    def join_room(self, room_id: str, player_id: str, player_name: str) -> TarotRoom:
        with self._lock:
            room = self._get_room(room_id)
            index = room.seat_index(player_id)
            if index is not None:
                seat = room.seats[index]
                seat.name = _clean_name(player_name)
                if seat.is_bot:
                    seat.is_bot = False
                    self._log(room, f"👋 {seat.name} reprend sa place à la table.")
                    if room.host_player_id not in room.players:
                        room.host_player_id = player_id
                return room
            if room.status != "lobby":
                raise ValueError("Cette partie a déjà commencé.")
            if len(room.seats) >= MAX_PLAYERS:
                raise ValueError(f"Ce salon est complet ({MAX_PLAYERS} joueurs maximum).")
            room.seats.append(TarotSeat(player_id, _clean_name(player_name)))
            return room

    def get_room(self, room_id: str, player_id: str) -> TarotRoom:
        with self._lock:
            room = self._get_room(room_id)
            if room.seat_index(player_id) is None:
                raise KeyError("Salon ou joueur introuvable.")
            return room

    def list_rooms(self, player_id: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            for room in self.rooms.values():
                self._advance(room)
            return [
                {
                    "room_id": room.room_id,
                    "status": room.status,
                    "player_count": len(room.seats),
                    "max_players": MAX_PLAYERS,
                    "host_name": next(
                        (seat.name for seat in room.seats
                         if seat.player_id == room.host_player_id),
                        "Joueur",
                    ),
                    "is_member": bool(player_id) and room.seat_index(player_id) is not None,
                }
                for room in self.rooms.values()
                if room.status != "finished"
            ]

    def start_room(self, room_id: str, player_id: str) -> TarotRoom:
        with self._lock:
            room = self.get_room(room_id, player_id)
            if room.host_player_id != player_id:
                raise PermissionError("Seul l’hôte peut démarrer la partie.")
            if room.status != "lobby":
                raise ValueError("Cette partie a déjà démarré.")
            if not MIN_PLAYERS <= len(room.seats) <= MAX_PLAYERS:
                raise ValueError(
                    f"Il faut entre {MIN_PLAYERS} et {MAX_PLAYERS} joueurs pour démarrer."
                )
            for seat in room.seats:
                seat.penalties = 0
                seat.exact_bids = 0
            first_dealer = self._rng.randrange(len(room.seats))
            room.schedule = build_schedule(len(room.seats), first_dealer)
            room.history.clear()
            room.log.clear()
            room.status = "playing"
            room.started_at = time.time()
            room.stats_recorded = False
            room.round_index = -1
            self._log(room, f"🎲 Tirage au sort : {room.seats[first_dealer].name} distribue en premier.")
            self._begin_round(room, 0, time.time())
            return room

    def place_bid(self, room_id: str, player_id: str, bid: Any) -> TarotRoom:
        with self._lock:
            room = self.get_room(room_id, player_id)
            index = room.seat_index(player_id)
            self._require_turn(room, index, "bidding")
            if isinstance(bid, bool) or not isinstance(bid, int):
                raise ValueError("L’annonce doit être un nombre entier de plis.")
            self._apply_bid(room, index, bid, time.time())
            return room

    def play_card(
        self, room_id: str, player_id: str, card: Any, excuse_mode: Any = None,
    ) -> TarotRoom:
        with self._lock:
            room = self.get_room(room_id, player_id)
            index = room.seat_index(player_id)
            self._require_turn(room, index, "playing")
            if isinstance(card, bool) or not isinstance(card, int):
                raise ValueError("Carte invalide.")
            self._apply_play(room, index, card, excuse_mode, time.time())
            return room

    def leave_room(self, room_id: str, player_id: str) -> TarotRoom | None:
        with self._lock:
            room = self.rooms.get(room_id.strip().upper())
            if room is None:
                return None
            index = room.seat_index(player_id)
            if index is None:
                return room
            seat = room.seats[index]
            if room.status == "lobby":
                room.seats.pop(index)
            elif not seat.is_bot:
                seat.is_bot = True
                self._log(room, f"🤖 {seat.name} a quitté la table : un bot joue à sa place.")
            humans = room.players
            if not humans:
                self.rooms.pop(room.room_id, None)
                return None
            if room.host_player_id not in humans:
                room.host_player_id = next(iter(humans))
            return room

    def restart_room(self, room_id: str, player_id: str) -> TarotRoom:
        with self._lock:
            room = self.get_room(room_id, player_id)
            if room.host_player_id != player_id:
                raise PermissionError("Seul l’hôte peut relancer la partie.")
            if room.status != "finished":
                raise ValueError("La partie doit être terminée pour être relancée.")
            room.seats = [
                TarotSeat(seat.player_id, seat.name)
                for seat in room.seats if not seat.is_bot
            ]
            room.match_number += 1
            room.status = "lobby"
            room.phase = "lobby"
            room.schedule = []
            room.round_index = -1
            room.current_seat = None
            room.leader_seat = None
            room.trick = []
            room.trick_number = 0
            room.trick_winner_seat = None
            room.deadline = None
            room.turn_started_at = None
            room.history.clear()
            room.log.clear()
            room.started_at = None
            room.stats_recorded = False
            return room

    def advance_timers(self, room_id: str) -> bool:
        with self._lock:
            room = self.rooms.get(room_id.strip().upper())
            if room is None:
                return False
            return self._advance(room)

    def _get_room(self, room_id: str) -> TarotRoom:
        room = self.rooms.get(room_id.strip().upper())
        if room is None:
            raise KeyError("Salon introuvable ou expiré.")
        self._advance(room)
        return room

    @staticmethod
    def _require_turn(room: TarotRoom, index: int | None, phase: str) -> None:
        if room.status != "playing" or room.phase != phase:
            raise ValueError("Cette action n’est pas disponible maintenant.")
        if index is None or room.current_seat != index:
            raise ValueError("Ce n’est pas votre tour.")

    @staticmethod
    def _log(room: TarotRoom, text: str) -> None:
        room.log.append({"id": uuid.uuid4().hex[:8], "text": text})
        del room.log[:-MAX_LOG_ENTRIES]

    def _start_turn(self, room: TarotRoom, seat_index: int, now: float) -> None:
        room.current_seat = seat_index
        room.turn_started_at = now
        room.deadline = now + ACTION_SECONDS

    def _begin_round(self, room: TarotRoom, round_index: int, now: float) -> None:
        room.round_index = round_index
        dealer, cards, kind = room.schedule[round_index]
        count = len(room.seats)
        deck = list(range(DECK_SIZE))
        self._rng.shuffle(deck)
        for seat in room.seats:
            seat.hand = []
            seat.bid = None
            seat.tricks = 0
        for position in range(cards * count):
            room.seats[(dealer + 1 + position) % count].hand.append(deck[position])
        room.trick = []
        room.trick_number = 1
        room.trick_winner_seat = None
        room.leader_seat = (dealer + 1) % count
        room.phase = "bidding"
        set_aside = DECK_SIZE - cards * count
        special = {
            ROUND_SINGLE_VISIBLE: " · carte personnelle visible",
            ROUND_SINGLE_HIDDEN: " · carte personnelle cachée, cartes des autres visibles",
        }.get(kind, "")
        self._log(
            room,
            f"🃏 Manche {round_index + 1}/{len(room.schedule)} : {room.seats[dealer].name} "
            f"distribue {cards} carte{'s' if cards > 1 else ''}{special}"
            f" ({set_aside} mise{'s' if set_aside > 1 else ''} de côté).",
        )
        self._start_turn(room, (dealer + 1) % count, now)

    def _apply_bid(self, room: TarotRoom, index: int, bid: int, now: float) -> None:
        if not 0 <= bid <= MAX_BID:
            raise ValueError(f"L’annonce doit être comprise entre 0 et {MAX_BID} plis.")
        dealer, cards, _kind = room.schedule[room.round_index]
        forbidden = room.forbidden_dealer_bid()
        if index == dealer and forbidden is not None and bid == forbidden:
            raise ValueError(
                f"Annonce impossible : avec {bid}, la somme des annonces serait égale à "
                f"{cards}, le nombre de cartes distribuées. En tant que distributeur, "
                "vous devez annoncer un autre nombre."
            )
        seat = room.seats[index]
        seat.bid = bid
        self._log(room, f"📣 {seat.name} annonce {bid} pli{'s' if bid > 1 else ''}.")
        if index != dealer:
            self._start_turn(room, (index + 1) % len(room.seats), now)
            return
        if room.schedule[room.round_index][2] == ROUND_SINGLE_HIDDEN:
            self._log(room, "🔓 Toutes les annonces sont faites : les cartes sont révélées.")
        room.phase = "playing"
        self._start_turn(room, room.leader_seat, now)

    def _apply_play(
        self, room: TarotRoom, index: int, card: int, excuse_mode: Any, now: float,
    ) -> None:
        seat = room.seats[index]
        if card not in seat.hand:
            raise ValueError("Cette carte n’est pas dans votre main.")
        if card == EXCUSE:
            if excuse_mode not in EXCUSE_VALUES:
                raise ValueError("Choisissez la valeur de l’Excuse : MIN (0) ou MAX (22).")
            value = EXCUSE_VALUES[excuse_mode]
        else:
            if excuse_mode is not None:
                raise ValueError("Seule l’Excuse se joue en MIN ou en MAX.")
            value = card
        seat.hand.remove(card)
        room.trick.append({
            "seat": index,
            "card": card,
            "value": value,
            "excuse_mode": excuse_mode if card == EXCUSE else None,
        })
        if card == EXCUSE:
            self._log(room, f"🎭 {seat.name} joue {card_label(card, excuse_mode)}.")
        if len(room.trick) < len(room.seats):
            self._start_turn(room, (index + 1) % len(room.seats), now)
            return
        winner_entry = max(room.trick, key=lambda entry: entry["value"])
        winner = winner_entry["seat"]
        room.seats[winner].tricks += 1
        room.trick_winner_seat = winner
        room.phase = "trick_end"
        room.current_seat = None
        room.turn_started_at = None
        room.deadline = now + TRICK_PAUSE_SECONDS
        winning_card = (
            card_label(winner_entry["card"], winner_entry["excuse_mode"])
            if winner_entry["card"] == EXCUSE
            else f"le {winner_entry['card']}"
        )
        self._log(
            room,
            f"🏆 {room.seats[winner].name} remporte le pli {room.trick_number} avec {winning_card}.",
        )

    def _finish_trick(self, room: TarotRoom, now: float) -> None:
        winner = room.trick_winner_seat
        room.trick = []
        room.trick_winner_seat = None
        if any(seat.hand for seat in room.seats):
            room.trick_number += 1
            room.leader_seat = winner
            room.phase = "playing"
            self._start_turn(room, winner, now)
            return
        dealer, cards, kind = room.schedule[room.round_index]
        results = []
        for index, seat in enumerate(room.seats):
            penalty = abs((seat.bid or 0) - seat.tricks)
            seat.penalties += penalty
            if penalty == 0:
                seat.exact_bids += 1
            results.append({
                "seat": index,
                "bid": seat.bid,
                "tricks": seat.tricks,
                "penalty": penalty,
                "total": seat.penalties,
            })
        room.history.append({
            "number": room.round_index + 1,
            "dealer_seat": dealer,
            "cards_per_player": cards,
            "kind": kind,
            "results": results,
        })
        room.phase = "round_end"
        room.current_seat = None
        room.leader_seat = None
        room.deadline = now + ROUND_SUMMARY_SECONDS
        self._log(room, f"📊 Fin de la manche {room.round_index + 1} : pénalités comptées.")

    def _finish_round(self, room: TarotRoom, now: float) -> None:
        if room.round_index + 1 < len(room.schedule):
            self._begin_round(room, room.round_index + 1, now)
            return
        room.status = "finished"
        room.phase = "finished"
        room.round_index = len(room.schedule)
        room.current_seat = None
        room.deadline = None
        room.turn_started_at = None
        for seat in room.seats:
            seat.hand = []
        winners = [seat.name for seat in room.seats if seat.player_id in room.winner_ids()]
        self._log(room, f"🏁 Partie terminée ! Victoire de {', '.join(winners)}.")

    def _advance(self, room: TarotRoom, now: float | None = None) -> bool:
        changed = False
        for _ in range(DECK_SIZE * 2):
            if not self._step(room, time.time() if now is None else now):
                break
            changed = True
        return changed

    def _step(self, room: TarotRoom, now: float) -> bool:
        if room.status != "playing":
            return False
        if room.phase in {"trick_end", "round_end"}:
            if room.deadline is None or now < room.deadline:
                return False
            if room.phase == "trick_end":
                self._finish_trick(room, now)
            else:
                self._finish_round(room, now)
            return True
        if room.phase not in {"bidding", "playing"} or room.current_seat is None:
            return False
        seat = room.seats[room.current_seat]
        if seat.is_bot:
            if now < (room.turn_started_at or now) + BOT_DELAY_SECONDS:
                return False
        elif room.deadline is None or now < room.deadline:
            return False
        else:
            action = "annonce" if room.phase == "bidding" else "joue"
            self._log(room, f"⏱️ Temps écoulé : le jeu {action} automatiquement pour {seat.name}.")
        index = room.current_seat
        if room.phase == "bidding":
            self._apply_bid(room, index, choose_bot_bid(room, index), now)
        else:
            card, mode = choose_bot_card(room, index)
            self._apply_play(room, index, card, mode, now)
        return True


def _win_probability(card: int, hand: list[int], opponents: int) -> float:
    if card == EXCUSE:
        return 1.0
    unknown = [candidate for candidate in range(DECK_SIZE) if candidate not in hand]
    if not unknown:
        return 1.0
    lower = sum(1 for candidate in unknown if candidate != EXCUSE and candidate < card)
    return (lower / len(unknown)) ** opponents


def _respect_dealer_rule(room: TarotRoom, index: int, bid: int, estimate: float) -> int:
    forbidden = room.forbidden_dealer_bid()
    if room.schedule[room.round_index][0] != index or forbidden is None or bid != forbidden:
        return bid
    if bid == 0:
        return 1
    return bid - 1 if estimate < bid else bid + 1


def choose_bot_bid(room: TarotRoom, index: int) -> int:
    _dealer, _cards, kind = room.schedule[room.round_index]
    seat = room.seats[index]
    opponents = len(room.seats) - 1
    if kind == ROUND_SINGLE_HIDDEN:
        visible = [card for other, item in enumerate(room.seats) if other != index for card in item.hand]
        unseen = [card for card in range(DECK_SIZE) if card not in visible]
        if EXCUSE in visible:
            estimate = 0.0
        else:
            best = max(visible, default=0)
            winners = sum(1 for card in unseen if card == EXCUSE or card > best)
            estimate = winners / len(unseen) if unseen else 0.0
    else:
        estimate = sum(_win_probability(card, seat.hand, opponents) for card in seat.hand)
    bid = int(estimate + 0.5)
    return _respect_dealer_rule(room, index, bid, estimate)


def choose_bot_card(room: TarotRoom, index: int) -> tuple[int, str | None]:
    seat = room.seats[index]
    hand = sorted(seat.hand)
    numbers = [card for card in hand if card != EXCUSE]
    has_excuse = EXCUSE in hand
    wants_tricks = (seat.bid or 0) > seat.tricks
    best = max((entry["value"] for entry in room.trick), default=None)
    is_last = len(room.trick) == len(room.seats) - 1

    if wants_tricks:
        if best is None:
            return (numbers[-1], None) if numbers else (EXCUSE, "max")
        winners = [card for card in numbers if card > best]
        if winners:
            return (winners[0] if is_last else winners[-1], None)
        if has_excuse:
            return EXCUSE, "max"
        return numbers[0], None

    if best is None:
        return (EXCUSE, "min") if has_excuse else (numbers[0], None)
    losers = [card for card in numbers if card < best]
    if losers:
        return losers[-1], None
    if has_excuse:
        return EXCUSE, "min"
    return (numbers[-1] if is_last else numbers[0]), None


tarot_africain_manager = TarotAfricainManager()
