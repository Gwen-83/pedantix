import ast
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

import unittest
from fastapi.testclient import TestClient

from app.main import app


GAME_PAGES = (
    "/games/pedantix/",
    "/games/motus/",
    "/games/cemantix/",
    "/games/chiffrantix/",
    "/games/battleship/",
    "/games/sudoku/",
    "/games/geoguessr/",
    "/games/undercover/",
    "/games/plongee/",
    "/games/bitoguessr/",
    "/games/memories/",
)


class PageContractParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.assets = []
        self.cards = []
        self._current_card = None
        self._reading_count = False
        self.count_text = ""

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        classes = set(attributes.get("class", "").split())

        if tag == "script" and attributes.get("src"):
            self.assets.append(attributes["src"])
        elif tag == "link" and "stylesheet" in attributes.get("rel", "").split():
            self.assets.append(attributes.get("href", ""))

        if tag == "a" and "store-game-card-available" in classes:
            self._current_card = {
                "href": attributes.get("href", ""),
                "text": "",
            }
        if attributes.get("id") == "store-game-count":
            self._reading_count = True

    def handle_data(self, data):
        if self._current_card is not None:
            self._current_card["text"] += data
        if self._reading_count:
            self.count_text += data

    def handle_endtag(self, tag):
        if tag == "a" and self._current_card is not None:
            self.cards.append(self._current_card)
            self._current_card = None
        if tag == "span" and self._reading_count:
            self._reading_count = False


class FrontendContractTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_store_game_count_matches_available_cards(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

        page = PageContractParser()
        page.feed(response.text)

        self.assertEqual(len(page.cards), 10)
        self.assertEqual(page.count_text.strip(), "10 jeux")
        self.assertEqual(len({card["href"] for card in page.cards}), len(page.cards))

    def test_every_game_page_and_its_local_scripts_and_stylesheets_load(self):
        for path in GAME_PAGES:
            with self.subTest(game_page=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)

                page = PageContractParser()
                page.feed(response.text)
                self.assertIn('name="viewport"', response.text)
                self.assertIn('lang="fr"', response.text)
                self.assertTrue(page.assets)

                for asset in page.assets:
                    with self.subTest(asset=asset):
                        url = urlsplit(asset)
                        if url.scheme or url.netloc or not url.path.startswith("/"):
                            continue
                        asset_response = self.client.get(url.path)
                        self.assertEqual(asset_response.status_code, 200)

    def test_global_chat_notifications_are_shared_across_game_pages(self):
        root_page = self.client.get("/")
        self.assertIn('/static/shared/presence.js', root_page.text)
        for path in GAME_PAGES:
            with self.subTest(game_page=path):
                self.assertIn('/static/shared/presence.js', self.client.get(path).text)
        admin_page = (
            Path(__file__).resolve().parents[1] / "static" / "admin" / "usage.html"
        ).read_text()
        self.assertIn('/static/shared/presence.js', admin_page)

        presence_script = (
            Path(__file__).resolve().parents[1] / "static" / "shared" / "presence.js"
        ).read_text()
        self.assertIn("refreshGeneralChatNotifications", presence_script)
        self.assertIn("window.setInterval(refreshGeneralChatNotifications, 3_000)", presence_script)
        self.assertIn("window.Notification.requestPermission()", presence_script)
        self.assertIn("new window.Notification(", presence_script)
        self.assertIn("message.username} · Chat général", presence_script)

    def test_battleship_catalog_promises_its_available_solo_and_multiplayer_modes(self):
        response = self.client.get("/")
        page = PageContractParser()
        page.feed(response.text)
        battleship = next(
            card for card in page.cards if card["href"] == "/games/battleship/"
        )

        self.assertIn("Solo & multijoueur", battleship["text"])

        game_page = self.client.get("/games/battleship/")
        self.assertEqual(game_page.status_code, 200)
        self.assertIn("Solo contre le bot", game_page.text)
        self.assertIn("Multijoueur", game_page.text)

    def test_battleship_solo_can_configure_fleet_before_starting(self):
        static_dir = Path(__file__).resolve().parents[1] / "static" / "games" / "battleship"
        source = (static_dir / "app.js").read_text()

        self.assertIn("solo ? 'Placez vos navires'", source)
        self.assertIn("startButton.textContent = solo ? 'Lancer la bataille'", source)
        self.assertIn("state = await post('/api/battleship/room/fleet'", source)

    def test_store_invitation_game_selector_includes_memories(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn('<option value="memories">Memory</option>', response.text)

    def test_store_hides_login_button_when_authenticated(self):
        static_dir = Path(__file__).resolve().parents[1] / "static"
        script = (static_dir / "store" / "store.js").read_text()
        stylesheet = (static_dir / "store" / "store.css").read_text()

        self.assertIn("accountButton.hidden = authenticated;", script)
        self.assertIn("logoutButton.hidden = !authenticated;", script)
        self.assertIn(
            ".store-account-button[hidden],\n.store-logout-button[hidden] {\n  display: none;",
            stylesheet,
        )

    def test_dropdown_options_use_the_active_theme_colors(self):
        shared_stylesheet = (
            Path(__file__).resolve().parents[1] / "static" / "shared" / "game-ui.css"
        ).read_text()

        self.assertIn(":where(select) {\n  color-scheme: inherit;", shared_stylesheet)
        self.assertIn("background-color: var(--game-input);", shared_stylesheet)
        self.assertIn("color: var(--game-text);", shared_stylesheet)
        self.assertIn("background-color: var(--game-accent);", shared_stylesheet)
        self.assertIn("color: var(--game-accent-contrast);", shared_stylesheet)

    def test_memory_solo_does_not_poll_and_uses_card_flip_feedback(self):
        games_dir = Path(__file__).resolve().parents[1] / "static" / "games" / "memories"
        script = (games_dir / "app.js").read_text()
        stylesheet = (games_dir / "style.css").read_text()

        self.assertNotIn("setInterval(refreshSolo", script)
        self.assertIn("scheduleSoloMismatchRefresh", script)
        self.assertIn("setInterval(updateSoloClock, 100)", script)
        self.assertIn("memory-card-reveal", stylesheet)
        self.assertIn("memory-card-loading", stylesheet)

    def test_admin_usage_dashboard_displays_google_street_view_monthly_usage(self):
        static_dir = Path(__file__).resolve().parents[1] / "static" / "admin"
        page = (static_dir / "usage.html").read_text()
        script = (static_dir / "usage.js").read_text()

        self.assertIn('id="usage-google-percent"', page)
        self.assertIn('id="usage-google-progress"', page)
        self.assertIn("renderGoogleUsage(data.google_maps_usage)", script)
        self.assertIn("report.google_maps_usage.events_reserved", script)

    def test_fermeture_express_is_removed(self):
        response = self.client.get("/")
        self.assertNotIn("Fermeture express", response.text)
        self.assertEqual(self.client.get("/games/fermeture-express/").status_code, 404)
        self.assertEqual(
            self.client.post("/api/fermeture-express/solo/new").status_code,
            404,
        )

    def test_geoguessr_solo_shows_the_next_city_without_waiting_for_room_readiness(self):
        static_dir = Path(__file__).resolve().parents[1] / "static" / "games" / "geoguessr"
        source = (static_dir / "app.js").read_text()

        self.assertIn("if (gameType !== 'room') return false;", source)
        self.assertIn("`${state.prompt.city}, ${state.prompt.country}`", source)
        self.assertIn(": 'Ville à trouver';", source)

    def test_geoguessr_home_displays_persistent_player_leaderboard(self):
        static_dir = Path(__file__).resolve().parents[1] / "static" / "games" / "geoguessr"
        page = (static_dir / "index.html").read_text()
        source = (static_dir / "app.js").read_text()

        self.assertIn('id="geo-leaderboard-title"', page)
        self.assertIn('id="geo-leaderboard"', page)
        self.assertIn("Top 5 des meilleurs scores sur une partie.", page)
        self.assertIn("request('/api/geoguessr/leaderboard')", source)
        self.assertIn("refreshLeaderboardAfterFinishedGame();", source)

    def test_guess_routes_run_synchronous_game_processing_off_the_event_loop(self):
        source = (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text()
        tree = ast.parse(source)
        routes = {
            node.name: node
            for node in tree.body
            if isinstance(node, ast.AsyncFunctionDef)
        }
        guess_routes = (
            "guess_motus_solo",
            "guess_motus_room",
            "undercover_guess",
            "guess_cemantix_solo",
            "guess_cemantix_room",
            "guess_chiffrantix_solo",
            "guess_chiffrantix_room",
            "guess_geoguessr_solo",
            "guess_geoguessr_room",
            "guess_bitoguessr_solo",
            "guess_bitoguessr_room",
            "guess_plongee_solo",
            "guess_plongee_room",
        )

        for route_name in guess_routes:
            with self.subTest(route=route_name):
                calls = [
                    node
                    for node in ast.walk(routes[route_name])
                    if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "to_thread"
                ]
                self.assertTrue(calls, f"{route_name} must offload synchronous game processing")

    def test_geoguessr_map_overzooms_and_shows_keyless_physical_features(self):
        static_dir = Path(__file__).resolve().parents[1] / "static" / "games" / "geoguessr"
        source = (static_dir / "app.js").read_text()
        detailed_boundaries = self.client.get(
            "/static/games/geoguessr/data/countries_50m.geojson"
        )
        rivers = self.client.get("/static/games/geoguessr/data/rivers_50m.geojson")
        mountain_ranges = self.client.get(
            "/static/games/geoguessr/data/mountain_ranges_50m.geojson"
        )

        self.assertIn("World_Terrain_Base/MapServer/tile/{z}/{y}/{x}", source)
        self.assertIn("maxNativeZoom: 9", source)
        self.assertIn("maxZoom: 19", source)
        self.assertIn("const maxZoom = 19", source)
        self.assertIn("tile.openstreetmap.org/{z}/{x}/{y}.png", source)
        self.assertIn("data/countries_50m.geojson", source)
        self.assertIn("rivers_50m.geojson", source)
        self.assertIn("mountain_ranges_50m.geojson", source)
        self.assertIn("fillColor: '#65a84a'", source)
        self.assertIn("name_fr", source)
        self.assertIn("smoothFactor: 0.5", source)
        self.assertNotIn("basemaps.cartocdn.com", source)
        self.assertEqual(detailed_boundaries.status_code, 200)
        self.assertIn('"name":"ne_50m_admin_0_countries"', detailed_boundaries.text)
        self.assertEqual(rivers.status_code, 200)
        self.assertGreater(len(rivers.json()["features"]), 200)
        self.assertEqual(mountain_ranges.status_code, 200)
        self.assertGreater(len(mountain_ranges.json()["features"]), 100)

    def test_geoguessr_solo_keeps_answer_map_framed_until_next_round(self):
        static_dir = Path(__file__).resolve().parents[1] / "static" / "games" / "geoguessr"
        source = (static_dir / "app.js").read_text()
        submit_guess = source.split("async function submitGuess()", 1)[1].split(
            "async function advanceSoloRound()", 1
        )[0]
        advance_round = source.split("async function advanceSoloRound()", 1)[1].split(
            "async function createRoom()", 1
        )[0]

        self.assertNotIn("map.setView", submit_guess)
        self.assertIn("showRoundAnswer(", source)
        self.assertIn("if (renderedResultRound === resultKey) return;", source)
        self.assertIn("map.setView(view.center, view.zoom)", advance_round)

    def test_geoguessr_room_result_updates_do_not_reset_map_or_rebuild_result(self):
        static_dir = Path(__file__).resolve().parents[1] / "static" / "games" / "geoguessr"
        source = (static_dir / "app.js").read_text()
        result_renderer = source.split("function renderRoundResult(", 1)[1].split(
            "function renderFinalScoreboard(", 1
        )[0]
        guess_lock = source.split("function guessLocked()", 1)[1].split(
            "function startPolling()", 1
        )[0]

        self.assertIn("if (renderSignature === lastResultSignature) return;", result_renderer)
        self.assertIn("state.awaiting_next_round === true", guess_lock)

    def test_geoguessr_solo_reenables_next_round_after_guess_request_finishes(self):
        static_dir = Path(__file__).resolve().parents[1] / "static" / "games" / "geoguessr"
        source = (static_dir / "app.js").read_text()
        submit_guess = source.split("async function submitGuess()", 1)[1].split(
            "async function advanceSoloRound()", 1
        )[0]

        self.assertIn(
            "else if (gameType === 'solo' && isWaitingForNextRound()) renderView();",
            submit_guess,
        )
        result_renderer = source.split("function renderRoundResult(", 1)[1].split(
            "function renderFinalScoreboard(", 1
        )[0]
        self.assertIn("roomBusy,", result_renderer)

    def test_geoguessr_immersive_map_falls_back_when_cartography_tiles_fail(self):
        static_dir = Path(__file__).resolve().parents[1] / "static" / "games" / "geoguessr"
        source = (static_dir / "app.js").read_text()

        self.assertIn("function createPanoramaLabelsLayer(useFallback = false)", source)
        self.assertIn("layer.on('tileerror'", source)
        self.assertIn("World_Topo_Map/MapServer/tile/{z}/{y}/{x}", source)
        self.assertIn("Impossible de charger le fond de carte.", source)

    def test_multiplayer_exit_controls_call_the_server_leave_endpoint(self):
        static_dir = Path(__file__).resolve().parents[1] / "static" / "games"
        game_ids = (
            "motus",
            "cemantix",
            "chiffrantix",
            "battleship",
            "sudoku",
            "geoguessr",
            "memories",
            "plongee",
            "undercover",
            "bitoguessr",
        )
        for game_id in game_ids:
            with self.subTest(game_id=game_id):
                source = (static_dir / game_id / "app.js").read_text()
                self.assertIn(f"/api/{game_id}/room/leave", source)
        self.assertIn(
            "/api/{game_id}/room/leave",
            {route.path for route in app.routes},
        )


if __name__ == "__main__":
    unittest.main()
