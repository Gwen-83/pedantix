import random
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import main
from app.main import app
from app.tarot_africain import (
    ACTION_SECONDS,
    BOT_DELAY_SECONDS,
    EXCUSE,
    ROUND_NORMAL,
    ROUND_SINGLE_HIDDEN,
    ROUND_SINGLE_VISIBLE,
    TRICK_PAUSE_SECONDS,
    TarotAfricainManager,
    build_schedule,
)


class FixedRandom(random.Random):
    def shuffle(self, x):
        return None

    def randrange(self, *args, **kwargs):
        return 0


class TarotAfricainRulesTests(unittest.TestCase):
    def setUp(self):
        self.manager = TarotAfricainManager(rng=FixedRandom())

    def make_room(self, count=4, start=True):
        room = self.manager.create_room("p0", "Alice")
        for index in range(1, count):
            self.manager.join_room(room.room_id, f"p{index}", f"Joueur {index}")
        if start:
            self.manager.start_room(room.room_id, "p0")
        return room

    def set_round(self, room, dealer, cards, kind, hands):
        room.schedule = [(dealer, cards, kind), (dealer, cards, kind)]
        room.round_index = 0
        for seat, hand in zip(room.seats, hands):
            seat.hand = list(hand)
            seat.bid = None
            seat.tricks = 0
        room.trick = []
        room.trick_number = 1
        room.phase = "bidding"
        room.status = "playing"
        room.leader_seat = (dealer + 1) % len(room.seats)
        self.manager._start_turn(room, room.leader_seat, time.time())

    def bid_all(self, room, bids):
        for index in bids:
            self.manager.place_bid(room.room_id, f"p{index}", bids[index])

    def test_schedule_decreases_to_one_card_then_two_special_rounds_per_dealer(self):
        schedule = build_schedule(4, 2)
        self.assertEqual(len(schedule), 24)
        self.assertEqual(
            schedule[:6],
            [
                (2, 5, ROUND_NORMAL), (2, 4, ROUND_NORMAL), (2, 3, ROUND_NORMAL),
                (2, 2, ROUND_NORMAL), (2, 1, ROUND_SINGLE_VISIBLE), (2, 1, ROUND_SINGLE_HIDDEN),
            ],
        )
        self.assertEqual([spec[0] for spec in schedule[::6]], [2, 3, 0, 1])
        expected = {2: (11, 24), 3: (7, 24), 4: (5, 24), 5: (4, 25), 6: (3, 24)}
        for players, (cards, rounds) in expected.items():
            with self.subTest(players=players):
                schedule = build_schedule(players, 0)
                self.assertEqual(schedule[0][1], cards)
                self.assertEqual(len(schedule), rounds)
                self.assertEqual({spec[0] for spec in schedule}, set(range(players)))

    def test_deal_starts_left_of_dealer_and_keeps_set_aside_cards_secret(self):
        room = self.make_room(3)
        dealer, cards, kind = room.round_spec
        self.assertEqual((dealer, cards, kind), (0, 7, ROUND_NORMAL))
        self.assertEqual(room.seats[1].hand, [0, 3, 6, 9, 12, 15, 18])
        self.assertEqual(room.seats[2].hand, [1, 4, 7, 10, 13, 16, 19])
        self.assertEqual(room.seats[0].hand, [2, 5, 8, 11, 14, 17, 20])
        state = room.to_dict("p1")
        self.assertEqual(state["round"]["set_aside_count"], 1)
        for viewer in ("p0", "p1", "p2"):
            visible = [
                card for item in room.to_dict(viewer)["seats"] for card in (item["hand"] or [])
            ]
            self.assertNotIn(21, visible)
        self.assertEqual(state["current_seat"], 1)
        self.assertEqual(state["seats"][1]["hand"], [0, 3, 6, 9, 12, 15, 18])
        self.assertIsNone(state["seats"][0]["hand"])
        self.assertEqual(state["seats"][0]["hand_count"], 7)

    def test_every_player_count_deals_equal_hands_from_the_22_card_deck(self):
        for players, cards in {2: 11, 3: 7, 4: 5, 5: 4, 6: 3}.items():
            with self.subTest(players=players):
                manager = TarotAfricainManager()
                room = manager.create_room("p0", "A")
                for index in range(1, players):
                    manager.join_room(room.room_id, f"p{index}", f"J{index}")
                manager.start_room(room.room_id, "p0")
                dealt = [card for seat in room.seats for card in seat.hand]
                self.assertTrue(all(len(seat.hand) == cards for seat in room.seats))
                self.assertEqual(len(set(dealt)), len(dealt))
                self.assertTrue(set(dealt) <= set(range(22)))

    def test_bidding_order_runs_clockwise_and_the_dealer_speaks_last(self):
        room = self.make_room(4)
        self.set_round(room, 2, 5, ROUND_NORMAL, [[1, 2, 3, 4, 5]] * 4)
        with self.assertRaisesRegex(ValueError, "pas votre tour"):
            self.manager.place_bid(room.room_id, "p2", 1)
        order = []
        for index in (3, 0, 1):
            order.append(room.current_seat)
            self.manager.place_bid(room.room_id, f"p{index}", 0)
        order.append(room.current_seat)
        self.assertEqual(order, [3, 0, 1, 2])
        self.assertEqual(room.phase, "bidding")

    def test_non_dealers_bid_freely_even_above_their_card_count(self):
        room = self.make_room(4)
        self.set_round(room, 0, 1, ROUND_SINGLE_VISIBLE, [[1], [2], [3], [4]])
        self.manager.place_bid(room.room_id, "p1", 3)
        self.assertEqual(room.seats[1].bid, 3)
        for invalid in (-1, 1.5, True, "2", None):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    self.manager.place_bid(room.room_id, "p2", invalid)

    def test_dealer_cannot_make_the_bid_total_equal_to_cards_dealt(self):
        room = self.make_room(4)
        self.set_round(room, 3, 5, ROUND_NORMAL, [[1, 2, 3, 4, 5]] * 4)
        self.bid_all(room, {0: 2, 1: 1, 2: 0})
        self.assertEqual(room.to_dict("p3")["forbidden_bid"], 2)
        self.assertIsNone(room.to_dict("p0")["forbidden_bid"])
        with self.assertRaisesRegex(ValueError, "somme des annonces serait égale à 5"):
            self.manager.place_bid(room.room_id, "p3", 2)
        self.assertIsNone(room.seats[3].bid)
        self.manager.place_bid(room.room_id, "p3", 4)
        self.assertEqual(room.phase, "playing")
        self.assertEqual(room.current_seat, 0)

    def test_dealer_is_unrestricted_when_others_already_exceed_the_card_count(self):
        room = self.make_room(2)
        self.set_round(room, 1, 2, ROUND_NORMAL, [[1, 2], [3, 4]])
        self.manager.place_bid(room.room_id, "p0", 3)
        self.assertIsNone(room.forbidden_dealer_bid())
        self.manager.place_bid(room.room_id, "p1", 0)
        self.assertEqual(room.phase, "playing")

    def test_hidden_round_shows_other_cards_only_until_all_bids_are_confirmed(self):
        room = self.make_room(3)
        self.set_round(room, 2, 1, ROUND_SINGLE_HIDDEN, [[5], [17], [EXCUSE]])
        state = room.to_dict("p0")
        self.assertIsNone(state["seats"][0]["hand"])
        self.assertEqual(state["seats"][0]["hand_count"], 1)
        self.assertEqual(state["seats"][1]["hand"], [17])
        self.assertEqual(state["seats"][2]["hand"], [EXCUSE])
        self.bid_all(room, {0: 0, 1: 0})
        self.assertIsNone(room.to_dict("p2")["seats"][2]["hand"])
        self.manager.place_bid(room.room_id, "p2", 0)
        for viewer in ("p0", "p1", "p2"):
            state = room.to_dict(viewer)
            self.assertEqual([seat["hand"] for seat in state["seats"]], [[5], [17], [EXCUSE]])

    def test_visible_single_card_round_hides_other_players_cards(self):
        room = self.make_room(3)
        self.set_round(room, 0, 1, ROUND_SINGLE_VISIBLE, [[5], [17], [8]])
        state = room.to_dict("p0")
        self.assertEqual(state["seats"][0]["hand"], [5])
        self.assertIsNone(state["seats"][1]["hand"])
        self.assertIsNone(state["seats"][2]["hand"])

    def test_highest_card_wins_and_the_winner_leads_the_next_trick(self):
        room = self.make_room(4)
        self.set_round(room, 3, 2, ROUND_NORMAL, [[4, 1], [17, 2], [9, 3], [12, 5]])
        self.bid_all(room, {0: 1, 1: 1, 2: 0, 3: 1})
        with self.assertRaisesRegex(ValueError, "pas dans votre main"):
            self.manager.play_card(room.room_id, "p0", 17)
        for index, card in ((0, 4), (1, 17), (2, 9), (3, 12)):
            self.manager.play_card(room.room_id, f"p{index}", card)
        self.assertEqual(room.phase, "trick_end")
        self.assertEqual(room.trick_winner_seat, 1)
        self.assertEqual(room.seats[1].tricks, 1)
        with self.assertRaises(ValueError):
            self.manager.play_card(room.room_id, "p0", 1)
        self.manager._advance(room, time.time() + TRICK_PAUSE_SECONDS + 0.1)
        self.assertEqual(room.phase, "playing")
        self.assertEqual(room.current_seat, 1)
        self.assertEqual(room.trick, [])
        self.assertEqual(room.trick_number, 2)

    def test_excuse_value_is_chosen_when_played_and_announced(self):
        room = self.make_room(3)
        self.set_round(room, 2, 1, ROUND_SINGLE_VISIBLE, [[EXCUSE], [21], [1]])
        self.bid_all(room, {0: 1, 1: 1, 2: 1})
        with self.assertRaisesRegex(ValueError, "MIN \\(0\\) ou MAX \\(22\\)"):
            self.manager.play_card(room.room_id, "p0", EXCUSE)
        self.manager.play_card(room.room_id, "p0", EXCUSE, "max")
        with self.assertRaisesRegex(ValueError, "Seule l’Excuse"):
            self.manager.play_card(room.room_id, "p1", 21, "min")
        self.manager.play_card(room.room_id, "p1", 21)
        self.manager.play_card(room.room_id, "p2", 1)
        self.assertEqual(room.trick_winner_seat, 0)
        self.assertEqual(room.trick[0], {"seat": 0, "card": EXCUSE, "value": 22, "excuse_mode": "max"})
        self.assertTrue(any("l’Excuse en MAX (22)" in entry["text"] for entry in room.log))

        self.set_round(room, 2, 1, ROUND_SINGLE_VISIBLE, [[EXCUSE], [2], [1]])
        self.bid_all(room, {0: 0, 1: 1, 2: 1})
        self.manager.play_card(room.room_id, "p0", EXCUSE, "min")
        self.manager.play_card(room.room_id, "p1", 2)
        self.manager.play_card(room.room_id, "p2", 1)
        self.assertEqual(room.trick_winner_seat, 1)

    def test_penalties_are_absolute_differences_and_accumulate(self):
        room = self.make_room(2)
        self.set_round(room, 1, 2, ROUND_NORMAL, [[20, 19], [1, 2]])
        room.seats[0].penalties = 4
        self.bid_all(room, {0: 1, 1: 2})
        for _ in range(2):
            self.manager.play_card(room.room_id, f"p{room.current_seat}", max(room.seats[room.current_seat].hand))
            self.manager.play_card(room.room_id, f"p{room.current_seat}", max(room.seats[room.current_seat].hand))
            self.manager._advance(room, time.time() + TRICK_PAUSE_SECONDS + 0.1)
        self.assertEqual(room.phase, "round_end")
        self.assertEqual([seat.penalties for seat in room.seats], [5, 2])
        self.assertEqual(
            [(item["bid"], item["tricks"], item["penalty"]) for item in room.history[-1]["results"]],
            [(1, 2, 1), (2, 0, 2)],
        )

    def test_full_game_ends_after_every_player_dealt_with_tied_winners_allowed(self):
        manager = TarotAfricainManager(rng=random.Random(7))
        room = manager.create_room("p0", "A")
        for index in range(1, 4):
            manager.join_room(room.room_id, f"p{index}", f"J{index}")
        manager.start_room(room.room_id, "p0")
        for seat in room.seats:
            seat.is_bot = True
        now = time.time()
        for _ in range(5000):
            if room.status == "finished":
                break
            now += 3
            manager._advance(room, now)
        self.assertEqual(room.status, "finished")
        self.assertEqual(len(room.history), 24)
        first_dealer = room.history[0]["dealer_seat"]
        self.assertEqual(
            [entry["dealer_seat"] for entry in room.history[::6]],
            [(first_dealer + offset) % 4 for offset in range(4)],
        )
        for entry in room.history:
            self.assertNotEqual(
                sum(result["bid"] for result in entry["results"]), entry["cards_per_player"]
            )
            self.assertEqual(
                sum(result["tricks"] for result in entry["results"]), entry["cards_per_player"]
            )
        for index, seat in enumerate(room.seats):
            self.assertEqual(
                seat.penalties,
                sum(entry["results"][index]["penalty"] for entry in room.history),
            )
        lowest = min(seat.penalties for seat in room.seats)
        self.assertEqual(
            set(room.winner_ids()),
            {seat.player_id for seat in room.seats if seat.penalties == lowest},
        )

    def test_timeout_plays_automatically_without_turning_the_player_into_a_bot(self):
        room = self.make_room(2)
        self.set_round(room, 1, 2, ROUND_NORMAL, [[3, 4], [5, 6]])
        self.manager._advance(room, time.time() + ACTION_SECONDS - 1)
        self.assertIsNone(room.seats[0].bid)
        self.manager._advance(room, time.time() + ACTION_SECONDS + 0.5)
        self.assertIsNotNone(room.seats[0].bid)
        self.assertFalse(room.seats[0].is_bot)
        self.assertEqual(room.current_seat, 1)
        self.assertTrue(any("Temps écoulé" in entry["text"] for entry in room.log))

    def test_a_bot_replaces_a_leaving_player_until_they_come_back(self):
        room = self.make_room(3)
        self.set_round(room, 2, 1, ROUND_SINGLE_VISIBLE, [[5], [9], [12]])
        self.manager.leave_room(room.room_id, "p0")
        self.assertTrue(room.seats[0].is_bot)
        self.assertEqual(room.host_player_id, "p1")
        self.assertNotIn("p0", room.players)
        self.assertTrue(self.manager.list_rooms("p0")[0]["is_member"])
        self.manager._advance(room, time.time() + BOT_DELAY_SECONDS + 0.1)
        self.assertIsNotNone(room.seats[0].bid)

        with self.assertRaisesRegex(ValueError, "déjà commencé"):
            self.manager.join_room(room.room_id, "stranger", "Intrus")
        self.manager.join_room(room.room_id, "p0", "Alice")
        self.assertFalse(room.seats[0].is_bot)
        self.assertIn("p0", room.players)

        self.manager.leave_room(room.room_id, "p0")
        self.manager.leave_room(room.room_id, "p1")
        self.manager.leave_room(room.room_id, "p2")
        self.assertNotIn(room.room_id, self.manager.rooms)

    def test_lobby_limits_and_restart_drops_seats_held_by_bots(self):
        room = self.make_room(6, start=False)
        with self.assertRaisesRegex(ValueError, "complet"):
            self.manager.join_room(room.room_id, "p6", "Septième")
        with self.assertRaises(PermissionError):
            self.manager.start_room(room.room_id, "p1")
        solo = self.manager.create_room("solo", "Seul")
        with self.assertRaisesRegex(ValueError, "entre 2 et 6"):
            self.manager.start_room(solo.room_id, "solo")

        self.manager.start_room(room.room_id, "p0")
        self.manager.leave_room(room.room_id, "p5")
        room.status = "finished"
        room.phase = "finished"
        self.manager.restart_room(room.room_id, "p0")
        self.assertEqual(room.status, "lobby")
        self.assertEqual([seat.player_id for seat in room.seats], [f"p{i}" for i in range(5)])
        self.assertTrue(all(seat.penalties == 0 for seat in room.seats))


class TarotAfricainApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        main.tarot_africain_manager.rooms.clear()

    def tearDown(self):
        main.tarot_africain_manager.rooms.clear()

    def test_page_and_room_routes(self):
        page = self.client.get("/games/tarot-africain/")
        self.assertEqual(page.status_code, 200)
        self.assertIn('data-presence-game="tarot-africain"', page.text)

        created = self.client.post(
            "/api/tarot-africain/room/create",
            json={"player_id": "host-id", "player_name": "Hôte"},
        )
        self.assertEqual(created.status_code, 200)
        room_id = created.json()["room_id"]
        joined = self.client.post(
            "/api/tarot-africain/room/join",
            json={"room_id": room_id, "player_id": "guest-id", "player_name": "Invité"},
        )
        self.assertEqual(joined.status_code, 200)
        self.assertEqual(joined.json()["player_count"], 2)
        rooms = self.client.get("/api/tarot-africain/rooms", params={"player_id": "guest-id"})
        self.assertTrue(rooms.json()["rooms"][0]["is_member"])
        missing = self.client.post(
            "/api/tarot-africain/room/join",
            json={"room_id": "ZZZZZZ", "player_id": "x", "player_name": "X"},
        )
        self.assertEqual(missing.status_code, 404)

    def test_websocket_runs_bids_and_plays_and_rejects_invalid_actions(self):
        room = main.tarot_africain_manager.create_room("host-id", "Hôte")
        main.tarot_africain_manager.join_room(room.room_id, "guest-id", "Invité")
        with self.client.websocket_connect(
            f"/ws/tarot-africain/{room.room_id}?player_id=host-id"
        ) as socket:
            self.assertEqual(socket.receive_json()["state"]["status"], "lobby")
            socket.send_json({"type": "start"})
            state = socket.receive_json()["state"]
            self.assertEqual(state["phase"], "bidding")
            current = state["seats"][state["current_seat"]]["player_id"]
            if current != "host-id":
                socket.send_json({"type": "bid", "bid": 1})
                self.assertEqual(socket.receive_json()["type"], "error")
                main.tarot_africain_manager.place_bid(room.room_id, current, 1)
            socket.send_json({"type": "bid", "bid": 1})
            state = socket.receive_json()["state"]
            self.assertEqual(state["seats"][state["my_seat"]]["bid"], 1)
            socket.send_json({"type": "dance"})
            self.assertEqual(socket.receive_json()["type"], "error")

    def test_leaving_or_being_evicted_mid_game_hands_the_seat_to_a_bot(self):
        room = main.tarot_africain_manager.create_room("host-id", "Hôte")
        main.tarot_africain_manager.join_room(room.room_id, "guest-id", "Invité")
        main.tarot_africain_manager.join_room(room.room_id, "third-id", "Tiers")
        main.tarot_africain_manager.start_room(room.room_id, "host-id")

        response = self.client.post(
            "/api/tarot-africain/room/leave",
            json={"room_id": room.room_id, "player_id": "guest-id"},
        )
        self.assertEqual(response.json(), {"status": "left"})
        self.assertTrue(room.seats[1].is_bot)

        for player_id in ("host-id", "third-id"):
            main._touch_room_activity("tarot-africain", room.room_id, player_id)
        key = ("tarot-africain", room.room_id, "third-id")
        main._player_activity[key] = time.time() - 120
        evicted = main._evict_absent_players("tarot-africain", room.room_id, force=True)
        self.assertEqual(evicted, ["third-id"])
        self.assertTrue(room.seats[2].is_bot)
        self.assertFalse(room.seats[0].is_bot)

        rejoined = self.client.post(
            "/api/tarot-africain/room/join",
            json={"room_id": room.room_id, "player_id": "guest-id", "player_name": "Invité"},
        )
        self.assertEqual(rejoined.status_code, 200)
        self.assertFalse(room.seats[1].is_bot)

    def test_finished_game_awards_three_points_to_each_human_winner(self):
        room = main.tarot_africain_manager.create_room("host-id", "Hôte")
        main.tarot_africain_manager.join_room(room.room_id, "guest-id", "Invité")
        main.tarot_africain_manager.join_room(room.room_id, "bot-id", "Parti")
        main.tarot_africain_manager.start_room(room.room_id, "host-id")
        main.tarot_africain_manager.leave_room(room.room_id, "bot-id")
        room.status = "finished"
        room.phase = "finished"
        for seat in room.seats:
            seat.penalties = 2
        with patch.object(main, "increment_player_score") as score, patch.object(
            main, "record_user_game_finish"
        ) as finish:
            main._record_tarot_room_results(room)
            main._record_tarot_room_results(room)
        self.assertEqual(
            sorted(call.args for call in score.call_args_list),
            [("Hôte", 3, "tarot-africain"), ("Invité", 3, "tarot-africain")],
        )
        self.assertEqual(finish.call_count, 2)
        self.assertTrue(all(call.kwargs["game_id"] == "tarot-africain" for call in finish.call_args_list))


if __name__ == "__main__":
    unittest.main()
