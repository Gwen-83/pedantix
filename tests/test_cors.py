import asyncio
import unittest

from fastapi.middleware.cors import CORSMiddleware

from app.main import allowed_origin_regex


class CorsTests(unittest.TestCase):
    def _preflight(self, origin):
        async def app(scope, receive, send):
            raise AssertionError("A valid preflight should be handled by CORS middleware.")

        middleware = CORSMiddleware(
            app,
            allow_origins=[],
            allow_origin_regex=allowed_origin_regex,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        sent = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            sent.append(message)

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "OPTIONS",
            "scheme": "https",
            "path": "/api/auth/check-username",
            "raw_path": b"/api/auth/check-username",
            "query_string": b"",
            "root_path": "",
            "headers": [
                (b"origin", origin.encode()),
                (b"access-control-request-method", b"POST"),
                (b"access-control-request-headers", b"content-type"),
            ],
            "client": ("127.0.0.1", 12345),
            "server": ("api.example.test", 443),
        }
        asyncio.run(middleware(scope, receive, send))
        response = next(message for message in sent if message["type"] == "http.response.start")
        return response["status"], dict(response["headers"])

    def test_custom_frontend_origins_pass_preflight(self):
        for origin in (
            "https://enacgames.studio4242.fr",
            "https://pedantixenac.studio4242.fr",
        ):
            with self.subTest(origin=origin):
                status, headers = self._preflight(origin)
                self.assertEqual(status, 200)
                self.assertEqual(headers[b"access-control-allow-origin"].decode(), origin)

    def test_unregistered_custom_origin_fails_preflight(self):
        status, headers = self._preflight("https://other.studio4242.fr")
        self.assertEqual(status, 400)
        self.assertNotIn(b"access-control-allow-origin", headers)


if __name__ == "__main__":
    unittest.main()
