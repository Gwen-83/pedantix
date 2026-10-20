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

    def test_store_invitation_game_selector_includes_memories(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn('<option value="memories">Memory</option>', response.text)

    def test_memory_solo_does_not_poll_and_uses_card_flip_feedback(self):
        games_dir = Path(__file__).resolve().parents[1] / "static" / "games" / "memories"
        script = (games_dir / "app.js").read_text()
        stylesheet = (games_dir / "style.css").read_text()

        self.assertNotIn("setInterval(refreshSolo", script)
        self.assertIn("scheduleSoloMismatchRefresh", script)
        self.assertIn("setInterval(updateSoloClock, 100)", script)
        self.assertIn("memory-card-reveal", stylesheet)
        self.assertIn("memory-card-loading", stylesheet)

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
