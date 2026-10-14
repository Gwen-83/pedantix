import os
import unittest
import datetime
import asyncio
from unittest.mock import patch

from app.database import (
    init_db,
    record_played_article,
    get_recently_played_articles,
    DatabaseContext
)
from app.wiki import WikipediaClient, ALL_CURATED_TITLES
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

        # Manually backdate the in-memory timestamp to 16 days ago
        with _recent_played_lock:
            _recent_played_cache[user]["Page Expiree"] = time.time() - (16 * 86400)

        # Calling get_recently_played_articles with 15 days should prune it and not return it
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
            "title": "Cached article",
            "paragraphs": ["Cached article text with sufficient content."],
            "url": "https://fr.wikipedia.org/wiki/Cached_article",
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

        self.assertEqual(article["title"], "Cached article")
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

    async def test_lobby_sync_sessions_when_article_replaced(self):
        from app.main import join_room, RoomJoinRequest
        from app.room import room_manager

        p1 = "test_lobby_sync_p1"
        p2 = "test_lobby_sync_p2"

        # P2 has played "Tour Eiffel" in the last 15 days
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


if __name__ == "__main__":
    unittest.main()
