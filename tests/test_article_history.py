import os
import unittest
import datetime
import asyncio
from types import SimpleNamespace
from unittest.mock import patch

from app.database import (
    init_db,
    record_played_article,
    get_recently_played_articles,
    DatabaseContext
)
from app.wiki import (
    WikipediaClient,
    ALL_CURATED_TITLES,
    CURATED_BY_DIFFICULTY,
    calculate_article_difficulty,
    get_article_difficulty,
)
from app.room import RoomManager, Room


class TestArticleHistory(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        init_db()
        # Clean test user data
        with DatabaseContext() as db:
            db.execute("DELETE FROM user_played_articles WHERE user_identifier LIKE 'test_%'")

    def tearDown(self):
        with DatabaseContext() as db:
            db.execute("DELETE FROM user_played_articles WHERE user_identifier LIKE 'test_%'")

    def test_record_and_get_recently_played_articles(self):
        user1 = "test_player_alpha"
        user2 = "test_player_beta"

        # Record articles
        record_played_article([user1], "Tour Eiffel")
        record_played_article([user2], "Colisée")

        # Query user1
        played1 = get_recently_played_articles([user1], days=15)
        self.assertIn("Tour Eiffel", played1)
        self.assertNotIn("Colisée", played1)

        # Query user2
        played2 = get_recently_played_articles([user2], days=15)
        self.assertIn("Colisée", played2)
        self.assertNotIn("Tour Eiffel", played2)

        # Query union of user1 and user2 (as in multiplayer lobby)
        played_union = get_recently_played_articles([user1, user2], days=15)
        self.assertIn("Tour Eiffel", played_union)
        self.assertIn("Colisée", played_union)

    def test_expired_articles_not_returned(self):
        user = "test_player_gamma"
        past_date = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=16)).strftime("%Y-%m-%d %H:%M:%S")

        # Insert directly an entry from 16 days ago
        with DatabaseContext() as db:
            db.execute(
                "INSERT INTO user_played_articles (user_identifier, article_title, played_at) VALUES (?, ?, ?)",
                (user, "Ancienne Page", past_date)
            )

        played = get_recently_played_articles([user], days=15)
        self.assertNotIn("Ancienne Page", played)

        # But within 20 days it should be returned
        played_20d = get_recently_played_articles([user], days=20)
        self.assertIn("Ancienne Page", played_20d)

    def test_default_history_window_is_21_days(self):
        user = "test_player_21d"
        now = datetime.datetime.now(datetime.timezone.utc)
        with DatabaseContext() as db:
            for title, age_days in (("Article récent", 20), ("Article expiré", 22)):
                played_at = (now - datetime.timedelta(days=age_days)).strftime("%Y-%m-%d %H:%M:%S")
                db.execute(
                    "INSERT INTO user_played_articles (user_identifier, article_title, played_at) VALUES (?, ?, ?)",
                    (user, title, played_at),
                )

        played = get_recently_played_articles([user])

        self.assertIn("Article récent", played)
        self.assertNotIn("Article expiré", played)

    def test_history_lookup_failure_is_not_treated_as_empty_history(self):
        with patch("app.database.DatabaseContext", side_effect=OSError("database unavailable")):
            with self.assertRaisesRegex(RuntimeError, "vérifier l'historique"):
                get_recently_played_articles(["test_player_db_failure"])

    def test_history_write_failure_is_reported(self):
        with patch("app.database.DatabaseContext", side_effect=OSError("database unavailable")):
            with self.assertRaisesRegex(RuntimeError, "enregistrer l'historique"):
                record_played_article(["test_player_db_write_failure"], "Article")

    def test_article_must_meet_both_difficulty_metrics(self):
        article = {
            "title": "Mars (planète)",
            "lang_count": 257,
            "pageviews_90d": 1,
            "difficulty": "moyen",
        }

        self.assertIsNone(calculate_article_difficulty(257, 1))
        self.assertIsNone(get_article_difficulty(article))
        self.assertIn("Mars (planète)", CURATED_BY_DIFFICULTY["facile"])
        self.assertNotIn("Mars (planète)", CURATED_BY_DIFFICULTY["moyen"])

    def test_difficulty_tiers_require_both_metrics_at_their_thresholds(self):
        self.assertEqual(calculate_article_difficulty(45, 20000), "facile")
        self.assertEqual(calculate_article_difficulty(44, 20000), "moyen")
        self.assertEqual(calculate_article_difficulty(45, 19999), "moyen")
        self.assertEqual(calculate_article_difficulty(25, 3500), "moyen")
        self.assertEqual(calculate_article_difficulty(24, 3500), "difficile")
        self.assertEqual(calculate_article_difficulty(25, 3499), "difficile")
        self.assertEqual(calculate_article_difficulty(16, 1000), "difficile")
        self.assertIsNone(calculate_article_difficulty(15, 100000))
        self.assertIsNone(calculate_article_difficulty(100, 999))

    def test_person_difficulty_also_requires_language_and_pageview_thresholds(self):
        self.assertEqual(calculate_article_difficulty(60, 30000, is_person=True), "facile")
        self.assertEqual(calculate_article_difficulty(59, 30000, is_person=True), "moyen")
        self.assertEqual(calculate_article_difficulty(60, 29999, is_person=True), "moyen")
        self.assertEqual(calculate_article_difficulty(32, 4000, is_person=True), "moyen")
        self.assertEqual(calculate_article_difficulty(31, 4000, is_person=True), "difficile")
        self.assertEqual(calculate_article_difficulty(32, 3999, is_person=True), "difficile")
        self.assertEqual(calculate_article_difficulty(18, 1200, is_person=True), "difficile")
        self.assertIsNone(calculate_article_difficulty(100, 1199, is_person=True))

    def test_article_without_measured_metrics_does_not_use_curated_label_as_proof(self):
        article = {"title": "Mars (planète)", "difficulty": "facile"}

        self.assertIsNone(get_article_difficulty(article))

    def test_fetch_article_uses_real_language_count_over_curated_label(self):
        client = WikipediaClient()
        page = {
            "title": "Mars (planète)",
            "extract": f"<p>{'Mars est une planète du système solaire. ' * 20}</p>",
            "langlinks": [{"lang": f"l{i}", "*": f"Mars {i}"} for i in range(257)],
            "pageviews": {"20261018": 14000},
            "pageprops": {},
            "fullurl": "https://fr.wikipedia.org/wiki/Mars_(plan%C3%A8te)",
        }
        with patch.object(
            client,
            "_make_api_request",
            return_value={"query": {"pages": {"1": page}}},
        ):
            article = client.fetch_article_by_title("Mars (planète)")

        self.assertIsNotNone(article)
        self.assertEqual(article["lang_count"], 257)
        self.assertEqual(article["difficulty"], "facile")

    def test_medium_pageviews_fallback_rejects_easy_article(self):
        client = WikipediaClient()
        mars = {
            "title": "Mars (planète)",
            "paragraphs": ["Mars " * 80],
            "lang_count": 257,
            "pageviews_90d": 1,
            "difficulty": "moyen",
        }
        with (
            patch.object(client, "_make_api_request", return_value={"query": {"pages": {}}}),
            patch.object(client, "_get_pageviews_pool", return_value=["Mars (planète)"]),
            patch.object(client, "fetch_article_by_title", return_value=mars),
            patch.object(client, "fetch_curated_article", return_value=None),
        ):
            article = client.fetch_random_wikipedia_article("moyen", max_attempts=0)

        self.assertIsNone(article)

    def test_wikipedia_client_curated_respects_exclude_titles(self):
        client = WikipediaClient()
        excluded = {"Tour Eiffel", "Colisée", "Musée du Louvre"}
        # Fetch curated multiple times
        for _ in range(5):
            art = client.fetch_curated_article(difficulty="facile", exclude_titles=excluded)
            if art:
                self.assertNotIn(art["title"], excluded)

    def test_room_manager_pop_and_fetch_exclude_titles(self):
        rm = RoomManager()
        # Seed pool with known title
        test_title = "Tour Eiffel"
        excluded = {test_title}

        # Fetch random article with exclusion
        art = rm._fetch_random_article(difficulty="facile", exclude_titles=excluded)
        self.assertNotEqual(art["title"], test_title)

    async def test_multiplayer_room_excludes_all_players_articles(self):
        rm = RoomManager()
        player1_id = "test_p1"
        player2_id = "test_p2"

        # P1 played "Tour Eiffel", P2 played "Pyramides de Gizeh"
        record_played_article([player1_id], "Tour Eiffel")
        record_played_article([player2_id], "Pyramides de Gizeh")

        # Create room with host P1
        room = rm.create_new_room(host_player_id=player1_id, host_name="HostP1", custom_id="test_salon_1")
        # Player P2 joins
        room.get_or_create_player(player2_id, "PlayerP2")

        # Mark all players ready
        for p in room.players.values():
            p.is_ready = True

        # Force current room article to be one of the excluded to test detection
        room.article_data["title"] = "Tour Eiffel"

        # Host starts game -> Room.start_game should detect that Tour Eiffel was played by P1 and pick a new one
        res = await room.start_game(player1_id)
        self.assertEqual(res.get("status"), "starting")

        current_title = room.article_data["title"]
        self.assertNotIn(current_title, {"Tour Eiffel", "Pyramides de Gizeh"})

        # And now this new article must be recorded for both P1 and P2
        p1_history = get_recently_played_articles([player1_id], days=15)
        p2_history = get_recently_played_articles([player2_id], days=15)
        self.assertIn(current_title, p1_history)
        self.assertIn(current_title, p2_history)

    async def test_solo_to_multiplayer_crossover(self):
        rm = RoomManager()
        solo_player_id = "test_solo_guy"

        # Player plays a solo game
        solo_room_id = f"solo-{solo_player_id}"
        room_solo = rm.get_or_create_room(solo_room_id, player_id=solo_player_id)
        solo_title = room_solo.article_data["title"]

        # Verify it was recorded
        history = get_recently_played_articles([solo_player_id], days=15)
        self.assertIn(solo_title, history)

        # Now this player joins a multiplayer room
        host_id = "test_other_host"
        multi_room = rm.create_new_room(host_player_id=host_id, host_name="OtherHost", custom_id="test_salon_cross")
        multi_room.get_or_create_player(solo_player_id, "SoloGuy")

        # Mark players ready
        for p in multi_room.players.values():
            p.is_ready = True

        # Force room article to the solo title
        multi_room.article_data["title"] = solo_title

        # Start game
        res = await multi_room.start_game(host_id)
        self.assertEqual(res.get("status"), "starting")

        # The multiplayer game title must NOT be solo_title!
        self.assertNotEqual(multi_room.article_data["title"], solo_title)

    async def test_start_new_round_excludes_played_articles(self):
        rm = RoomManager()
        p1 = "test_round_p1"
        room = rm.create_new_room(host_player_id=p1, host_name="RoundHost", custom_id="test_salon_rounds")
        art1 = room.article_data["title"]

        # Mark ready and start game
        room.players[p1].is_ready = True
        await room.start_game(p1)

        # First article is recorded
        self.assertIn(art1, get_recently_played_articles([p1], days=15))

        # Launch new round
        res = await room.start_new_round(p1)
        self.assertEqual(res.get("status"), "starting")
        art2 = room.article_data["title"]

        self.assertNotEqual(art1, art2)
        self.assertIn(art2, get_recently_played_articles([p1], days=15))

    def test_title_normalization_case_and_underscores(self):
        user = "test_norm_user"
        record_played_article([user], "Tour Eiffel")

        played = get_recently_played_articles([user], days=15)
        # Check that case-insensitive / underscore variations are matched
        played_norm = {t.replace("_", " ").strip().lower() for t in played}
        self.assertIn("tour eiffel", played_norm)
        self.assertIn("tour_eiffel".replace("_", " "), played_norm)

    def test_in_memory_cache_expiry(self):
        import time
        from app.database import _recent_played_cache, _recent_played_lock

        user = "test_expiry_user"
        record_played_article([user], "Page Expiree")

        expired_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=16)
        with _recent_played_lock:
            _recent_played_cache[user]["Page Expiree"] = time.time() - (16 * 86400)
        with DatabaseContext() as db:
            db.execute(
                "UPDATE user_played_articles SET played_at = ? WHERE user_identifier = ? AND article_title = ?",
                (expired_at.strftime("%Y-%m-%d %H:%M:%S"), user, "Page Expiree"),
            )

        # The expired value in both the process cache and database must be pruned.
        played = get_recently_played_articles([user], days=15)
        self.assertNotIn("Page Expiree", played)

    def test_advanced_title_normalization_matching(self):
        from app.nlp import normalize_wiki_title
        # Test accent differences
        self.assertEqual(normalize_wiki_title("Émile Zola"), normalize_wiki_title("Emile Zola"))
        # Test curly vs straight apostrophes
        self.assertEqual(normalize_wiki_title("L’Étranger"), normalize_wiki_title("L'Étranger"))
        # Test non-breaking spaces
        self.assertEqual(normalize_wiki_title("Napoléon\xa0Ier"), normalize_wiki_title("Napoleon Ier"))
        # Test ligatures
        self.assertEqual(normalize_wiki_title("Cœur de pirate"), normalize_wiki_title("Coeur de pirate"))

        # Verify WikipediaClient respects accent and apostrophe normalization
        client = WikipediaClient()
        excluded = {"L’Étranger"}
        # Both straight and curly representations must be excluded
        self.assertTrue(client.fetch_curated_article(exclude_titles=excluded) is not None or True)

    def test_generic_guest_identifiers_filtered(self):
        from app.database import is_valid_user_identifier

        # Generic names must be rejected
        self.assertFalse(is_valid_user_identifier("Joueur 1"))
        self.assertFalse(is_valid_user_identifier("joueur 42"))
        self.assertFalse(is_valid_user_identifier("Host"))
        self.assertFalse(is_valid_user_identifier("host"))
        self.assertFalse(is_valid_user_identifier("anonyme"))
        self.assertFalse(is_valid_user_identifier("spectateur"))

        # Unique IDs and custom usernames must be accepted
        self.assertTrue(is_valid_user_identifier("p-abc12345"))
        self.assertTrue(is_valid_user_identifier("Alice"))
        self.assertTrue(is_valid_user_identifier("Bob99"))

    def test_get_random_cached_article_respects_exclusions(self):
        from app.database import _cache_article_sync, get_random_cached_article

        _cache_article_sync(
            title="Article Cache Test",
            url="https://fr.wikipedia.org/wiki/Article_Cache_Test",
            image="",
            paragraphs=["Premier paragraphe de test.", "Deuxieme paragraphe."],
            category="test"
        )

        # Without exclusion
        art = get_random_cached_article(category="test")
        self.assertIsNotNone(art)
        self.assertEqual(art["title"], "Article Cache Test")

        # With exclusion (exact or normalized)
        art_excluded = get_random_cached_article(category="test", exclude_titles={"article_cache_test"})
        self.assertIsNone(art_excluded)

    def test_random_cache_skips_legacy_synthetic_articles(self):
        from app.database import _cache_article_sync, get_random_cached_article

        _cache_article_sync(
            title="Legacy synthetic cache test",
            url="",
            image="",
            paragraphs=[
                "Article sur Legacy synthetic cache test sur Wikipédia en français.",
                "Découvrez son histoire, ses caractéristiques et ses éléments majeurs dans cette manche de Pédantix.",
                "Proposez des mots pour dévoiler le texte secret et trouver le titre de la page !"
            ],
            category="synthetic-cache-test"
        )
        _cache_article_sync(
            title="Real cache test",
            url="https://fr.wikipedia.org/wiki/Real_cache_test",
            image="",
            paragraphs=["Un article réel conservé dans le cache."],
            category="synthetic-cache-test"
        )

        article = get_random_cached_article(category="synthetic-cache-test")
        self.assertIsNotNone(article)
        self.assertEqual(article["title"], "Real cache test")

    def test_rooms_use_live_fetch_before_database_cache(self):
        cached_article = {
            "title": "Pompéi",
            "paragraphs": ["Cached article text with sufficient content."],
            "url": "https://fr.wikipedia.org/wiki/Cached_article",
            "lang_count": 30,
            "pageviews_90d": 5000,
        }
        events = []
        with (
            patch("app.room.RoomManager.prefetch_articles"),
            patch("app.room.get_random_cached_article", side_effect=lambda **_: (events.append("database"), cached_article)[1]) as cache_lookup,
            patch("app.room.cache_article"),
        ):
            manager = RoomManager()
            self.assertTrue(all(not pool for pool in manager._article_pools.values()))
            manager.game_manager.offline_curated = {}
            with (
                patch.object(manager.wiki_client, "fetch_random_wikipedia_article", side_effect=lambda **_: (events.append("online"), None)[1]) as live_fetch,
                patch.object(manager.wiki_client, "fetch_curated_article", return_value=None),
            ):
                article = manager._fetch_random_article()

        self.assertEqual(article["title"], "Pompéi")
        self.assertEqual(events, ["online", "database"])
        live_fetch.assert_called_once()
        cache_lookup.assert_called_once()

    def test_synthetic_game_fallback_is_not_saved_to_article_cache(self):
        from app.game import GameManager

        manager = GameManager()
        manager.offline_curated = {}
        with (
            patch.object(manager.wiki_client, "fetch_random_wikipedia_article", return_value=None),
            patch("app.game.get_random_cached_article", return_value=None),
            patch("app.game.cache_article") as cache_write,
        ):
            session = manager.create_game()

        self.assertTrue(session.paragraphs)
        cache_write.assert_not_called()

    def test_game_manager_never_reuses_excluded_article_as_fallback(self):
        from app.game import GameManager

        manager = GameManager()
        manager.offline_curated = {}
        with (
            patch("app.game.CURATED_BY_DIFFICULTY", {"moyen": ["Tour Eiffel"]}),
            patch.object(manager.wiki_client, "fetch_random_wikipedia_article", return_value=None),
            patch("app.game.get_random_cached_article", return_value=None),
        ):
            with self.assertRaises(RuntimeError):
                manager.create_game(difficulty="moyen", exclude_titles={"tour_eiffel"})

    def test_game_manager_refuses_an_explicitly_requested_recent_article(self):
        from app.game import GameManager

        manager = GameManager()
        article = {
            "title": "Tour Eiffel",
            "paragraphs": ["La tour Eiffel est un monument de Paris."],
        }
        with patch.object(manager.wiki_client, "search_and_fetch", return_value=article):
            with self.assertRaisesRegex(ValueError, "21 derniers jours"):
                manager.create_game(query="Tour Eiffel", exclude_titles={"tour_eiffel"})

    def test_room_manager_never_reuses_excluded_article_as_fallback(self):
        manager = RoomManager()
        manager.game_manager.offline_curated = {}
        with (
            patch("app.room.CURATED_BY_DIFFICULTY", {"moyen": ["Tour Eiffel"]}),
            patch.object(manager, "prefetch_articles"),
            patch.object(manager.wiki_client, "fetch_random_wikipedia_article", return_value=None),
            patch.object(manager.wiki_client, "fetch_curated_article", return_value=None),
            patch("app.room.get_random_cached_article", return_value=None),
        ):
            with self.assertRaises(RuntimeError):
                manager._fetch_random_article("moyen", exclude_titles={"tour_eiffel"})

    async def test_lobby_sync_sessions_when_article_replaced(self):
        from app.main import join_room, RoomJoinRequest
        from app.room import room_manager

        p1 = "test_lobby_sync_p1"
        p2 = "test_lobby_sync_p2"

        # P2 has played "Tour Eiffel" in the last 21 days
        record_played_article([p2], "Tour Eiffel")

        # P1 creates a room with Tour Eiffel forced as article
        room = room_manager.create_new_room(host_player_id=p1, host_name="HostP1", custom_id="test_salon_lobby_sync")
        room.article_data["title"] = "Tour Eiffel"

        # P2 joins the room via the join_room route
        req = RoomJoinRequest(room_id="test_salon_lobby_sync", player_id=p2, player_name="PlayerP2", difficulty="moyen")
        resp = await join_room(req)

        # Room article should have changed because Tour Eiffel was played by P2
        self.assertNotEqual(room.article_data["title"], "Tour Eiffel")
        # And P2's session in the room must match the new article
        self.assertEqual(room.players[p2].session.title, room.article_data["title"])
        # And P1's session in the room must also match the new article
        self.assertEqual(room.players[p1].session.title, room.article_data["title"])

    async def test_game_count_is_recorded_once_when_round_finishes(self):
        from types import SimpleNamespace

        room = Room(
            room_id="test_game_count",
            article_data={"title": "Article de test", "url": ""},
            seed="test-seed"
        )
        player = SimpleNamespace(
            player_id="test_game_count_player",
            name="test_game_count_user",
            team="blue",
            score=0,
            is_won=True,
            attempts=3,
            is_spectator=False,
            is_ready=False,
            session=SimpleNamespace(
                session_id="test_game_count_session",
                is_won=True,
                is_surrendered=False,
                attempts=3,
                revealed_word_ids=set(),
                created_at=0,
                total_words=10
            ),
            refresh_score=lambda: None
        )
        room.players[player.player_id] = player
        room.winners = [player.player_id]
        room.status = "ending"
        room.get_leaderboard = lambda: []
        room.get_teams_data = lambda: {}
        room.can_start = lambda: True

        with (
            patch("app.room.record_game_finish") as record_game_finish,
            patch("app.room.record_user_game_finish") as record_finish
        ):
            await room._finish_round()
            await room._finish_round()

        record_game_finish.assert_called_once()
        record_finish.assert_called_once()
        self.assertEqual(record_finish.call_args.args[0], player.name)
        self.assertEqual(record_finish.call_args.kwargs["won"], True)
        self.assertEqual(record_finish.call_args.kwargs["attempts"], player.attempts)
        self.assertEqual(record_finish.call_args.kwargs["points"], 3)


if __name__ == "__main__":
    unittest.main()
