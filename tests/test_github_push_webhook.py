import hashlib
import hmac
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app, room_manager


class GithubPushWebhookTests(unittest.TestCase):
    secret = "test-webhook-secret"

    def signed_headers(self, body, event="push"):
        signature = hmac.new(
            self.secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()
        return {
            "X-GitHub-Event": event,
            "X-Hub-Signature-256": f"sha256={signature}",
        }

    def test_webhook_is_disabled_without_a_configured_secret(self):
        with patch.dict(os.environ, {"GITHUB_WEBHOOK_SECRET": ""}), TestClient(app) as client:
            response = client.post("/api/webhooks/github", content=b"{}")

        self.assertEqual(response.status_code, 503)

    def test_webhook_rejects_invalid_signature(self):
        with patch.dict(os.environ, {"GITHUB_WEBHOOK_SECRET": self.secret}), TestClient(app) as client:
            response = client.post(
                "/api/webhooks/github",
                content=b"{}",
                headers={
                    "X-GitHub-Event": "push",
                    "X-Hub-Signature-256": "sha256=invalid",
                },
            )

        self.assertEqual(response.status_code, 401)

    def test_signed_non_push_event_is_ignored(self):
        body = b"{}"
        with patch.dict(os.environ, {"GITHUB_WEBHOOK_SECRET": self.secret}), TestClient(app) as client:
            response = client.post(
                "/api/webhooks/github",
                content=body,
                headers=self.signed_headers(body, event="issues"),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ignored"})

    def test_signed_push_is_broadcast_only_to_connected_rooms(self):
        payload = {
            "repository": {"full_name": "Gwen-83/pedantix"},
            "ref": "refs/heads/main",
            "commits": [{"id": "abc"}, {"id": "def"}],
        }
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        connected_room = SimpleNamespace(
            websockets={object()},
            broadcast=AsyncMock(),
        )
        disconnected_room = SimpleNamespace(
            websockets=set(),
            broadcast=AsyncMock(),
        )
        with (
            patch.dict(os.environ, {"GITHUB_WEBHOOK_SECRET": self.secret}),
            patch.object(
                room_manager,
                "rooms",
                {"connected": connected_room, "disconnected": disconnected_room},
            ),
            TestClient(app) as client,
        ):
            response = client.post(
                "/api/webhooks/github",
                content=body,
                headers=self.signed_headers(body),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "broadcast"})
        connected_room.broadcast.assert_awaited_once_with({
            "type": "github_push_notice",
            "repository": "Gwen-83/pedantix",
            "branch": "main",
            "commit_count": 2,
        })
        disconnected_room.broadcast.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
