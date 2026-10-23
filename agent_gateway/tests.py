"""The agent gateway: auth, allowlist, identity pinning, streaming and failure modes.

The agent is replaced by an httpx MockTransport, so nothing leaves the process.
"""

from __future__ import annotations

import json
import uuid

import httpx
from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from agent_gateway import views

User = get_user_model()
AGENT = "http://agent.internal:8001"


@override_settings(AGENT_API_BASE_URL=AGENT)
class AgentGatewayTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.uid = str(uuid.uuid4())
        cls.user = User.objects.create_user(
            email="s@example.com", password="pw-123456-x", full_name="S", supabase_user_id=cls.uid
        )

    def setUp(self):
        self.seen: list[httpx.Request] = []
        self.reply = lambda request: httpx.Response(200, json={"ok": True})
        self._old = views._client

        def handler(request: httpx.Request) -> httpx.Response:
            self.seen.append(request)
            return self.reply(request)

        views._client = httpx.Client(transport=httpx.MockTransport(handler))
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def tearDown(self):
        views._client.close()
        views._client = self._old

    def test_forwards_to_the_agent_path_and_returns_its_reply(self):
        r = self.client.get(f"/api/v1/agent/progress/{self.uid}?days=7")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(json.loads(r.content), {"ok": True})
        sent = self.seen[0]
        self.assertEqual(sent.url.path, f"/api/v1/progress/{self.uid}")
        self.assertEqual(sent.url.params["days"], "7")
        self.assertEqual(sent.url.params["user_id"], self.uid)

    def test_trailing_slash_from_the_dev_rewrite_is_accepted(self):
        r = self.client.get(f"/api/v1/agent/plan/{self.uid}/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.seen[0].url.path, f"/api/v1/plan/{self.uid}")

    def test_requires_sign_in(self):
        r = APIClient().post("/api/v1/agent/study/start", {"concept_id": "x"}, format="json")
        self.assertEqual(r.status_code, 401)
        self.assertEqual(self.seen, [])

    def test_unknown_and_server_only_routes_are_not_reachable(self):
        for method, path in (
            ("post", "classroom/plan"),
            ("post", "classroom/daily"),
            ("post", "coach/run"),
            ("get", "admin/traces"),
            ("get", "study/start"),  # right path, wrong method
        ):
            with self.subTest(path=path):
                r = getattr(self.client, method)(f"/api/v1/agent/{path}")
                self.assertEqual(r.status_code, 404)
        self.assertEqual(self.seen, [])

    def test_another_learners_data_is_refused(self):
        other = str(uuid.uuid4())
        self.assertEqual(self.client.get(f"/api/v1/agent/progress/{other}").status_code, 403)
        self.assertEqual(self.client.get(f"/api/v1/agent/chat/sessions?user_id={other}").status_code, 403)
        r = self.client.post("/api/v1/agent/study/start", {"user_id": other}, format="json")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.seen, [])

    def test_body_user_id_is_pinned_to_the_caller(self):
        self.client.post("/api/v1/agent/study/answer", {"question_id": "q1"}, format="json")
        self.assertEqual(json.loads(self.seen[0].content), {"question_id": "q1", "user_id": self.uid})

    def test_event_stream_is_relayed_unbuffered(self):
        self.reply = lambda request: httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=b"data: one\n\ndata: two\n\n",
        )
        r = self.client.post("/api/v1/agent/chat/message", {"query": "hi"}, format="json")
        self.assertTrue(r.streaming)
        self.assertEqual(r["X-Accel-Buffering"], "no")
        self.assertEqual(b"".join(r.streaming_content), b"data: one\n\ndata: two\n\n")

    def test_public_diagram_needs_no_token_and_keeps_its_cache_header(self):
        self.reply = lambda request: httpx.Response(
            200, headers={"content-type": "image/svg+xml", "cache-control": "public, max-age=31536000"}, content=b"<svg/>"
        )
        r = APIClient(HTTP_AUTHORIZATION="Bearer stale").get("/api/v1/agent/diagrams/0123456789abcdef0123.svg")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Cache-Control"], "public, max-age=31536000")
        self.assertNotIn("user_id", self.seen[0].url.params)

    def test_agent_down_is_a_clean_502(self):
        def down(request):
            raise httpx.ConnectError("refused")

        self.reply = down
        r = self.client.post("/api/v1/agent/study/next", {}, format="json")
        self.assertEqual(r.status_code, 502)
        self.assertIn("unavailable", r.json()["detail"])

    def test_agent_timeout_is_a_504(self):
        def slow(request):
            raise httpx.ReadTimeout("slow")

        self.reply = slow
        self.assertEqual(self.client.post("/api/v1/agent/study/next", {}, format="json").status_code, 504)

    def test_agent_errors_pass_through_with_retry_after(self):
        self.reply = lambda request: httpx.Response(429, headers={"retry-after": "30"}, json={"detail": "slow down"})
        r = self.client.post("/api/v1/agent/chat/message", {"query": "hi"}, format="json")
        self.assertEqual(r.status_code, 429)
        self.assertEqual(r["Retry-After"], "30")

    @override_settings(AGENT_API_BASE_URL="")
    def test_unconfigured_agent_is_a_503(self):
        self.assertEqual(self.client.get(f"/api/v1/agent/progress/{self.uid}").status_code, 503)

    def test_account_without_agent_identity_is_told_to_sign_in_again(self):
        user = User.objects.create_user(email="n@example.com", password="pw-123456-x", full_name="N")
        c = APIClient()
        c.force_authenticate(user)
        self.assertEqual(c.post("/api/v1/agent/study/next", {}, format="json").status_code, 409)
