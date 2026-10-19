from html.parser import HTMLParser
from pathlib import Path
import unittest


STATIC_DIR = Path(__file__).resolve().parents[1] / "static"

GAME_SETTINGS = {
    "battleship": {
        "naval-difficulty": "difficulty",
    },
    "bitoguessr": {
        "bito-solo-difficulty": "solo-difficulty",
        "bito-room-difficulty": "room-difficulty",
        "bito-room-round-count": "room-round-count",
    },
    "cemantix": {
        "cemantix-difficulty": "difficulty",
    },
    "chiffrantix": {
        "chiffrantix-difficulty": "difficulty",
        "chiffrantix-category": "category",
    },
    "geoguessr": {
        "geo-variant": "solo-variant",
        "geo-region": "solo-region",
        "geo-room-variant": "room-variant",
        "geo-room-region": "room-region",
        "geo-room-round-count": "room-round-count",
    },
    "motus": {
        "motus-difficulty": "difficulty",
    },
    "sudoku": {
        "sudoku-difficulty": "solo-difficulty",
        "sudoku-room-difficulty": "room-difficulty",
    },
    "plongee": {},
    "undercover": {},
}


class SettingsParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.game_id = ""
        self.settings = {}
        self.labels = set()
        self.shared_ui_loaded = False

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "html":
            self.game_id = attributes.get("data-presence-game", "")
        if tag == "label" and attributes.get("for"):
            self.labels.add(attributes["for"])
        if tag in {"input", "select"} and attributes.get("data-game-setting"):
            self.settings[attributes.get("id", "")] = attributes["data-game-setting"]
        if tag == "script" and attributes.get("src") == "/static/shared/game-ui.js":
            self.shared_ui_loaded = True


class GameUiPreferencesTests(unittest.TestCase):
    def test_every_non_pedantix_game_declares_its_user_configurable_settings(self):
        for game_id, expected_settings in GAME_SETTINGS.items():
            with self.subTest(game=game_id):
                html = (STATIC_DIR / "games" / game_id / "index.html").read_text(
                    encoding="utf-8"
                )
                page = SettingsParser()
                page.feed(html)

                self.assertEqual(page.game_id, game_id)
                self.assertEqual(page.settings, expected_settings)
                self.assertTrue(page.shared_ui_loaded)
                self.assertTrue(set(expected_settings).issubset(page.labels))

    def test_shared_game_ui_restores_and_validates_settings_and_traps_dialog_focus(self):
        script = (STATIC_DIR / "shared" / "game-ui.js").read_text(encoding="utf-8")

        self.assertIn("game_settings_v1:", script)
        self.assertIn("control.checkValidity()", script)
        self.assertIn("control.addEventListener('change', saveGameSettings)", script)
        self.assertIn("function trapDialogFocus(event, activeDialog)", script)
        self.assertIn("focusable[focusable.length - 1].focus()", script)
        self.assertIn("roomsOverlay.addEventListener('keydown'", script)
        self.assertIn("lobby.addEventListener('keydown'", script)


if __name__ == "__main__":
    unittest.main()
