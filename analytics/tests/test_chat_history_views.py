"""Chat-history endpoints.

CI runs with SUPABASE_URL/KEY blanked (`prepwise.ci_settings`), so the
unconfigured path is the default here; the configured paths are exercised by
patching the two module-level readers rather than by touching any live project.
"""

from unittest.mock import patch

from django.core.cache import cache
from django.urls import reverse
from rest_framework.test import APITestCase

from users.models import User

LIST_PAYLOAD = {
    "sessions": [
        {
            "session_id": "s-1",
            "session_type": "tutoring",
            "started_at": "2026-09-17T10:00:00+00:00",
            "ended_at": None,
            "duration_seconds": 620,
            "concepts_touched": ["torque"],
            "summary": "Worked through torque",
            "last_decision": "TEACH",
            "turn_count": 7,
        }
    ],
    "total": 1,
    "page": 1,
    "page_size": 20,
    "has_next": False,
}

DETAIL_PAYLOAD = {
    "session_id": "s-1",
    "session_type": "tutoring",
    "started_at": "2026-09-17T10:00:00+00:00",
    "ended_at": None,
    "duration_seconds": 620,
    "summary": "Worked through torque",
    "last_decision": "TEACH",
    "concepts_touched": ["torque"],
    "turns": [
        {
            "turn_id": "t-1",
            "role": "student",
            "content": "explain torque",
            "turn_index": 0,
            "is_summarized": False,
            "concepts_referenced": [],
            "agent_used": None,
            "created_at": "2026-09-17T10:00:01+00:00",
            "decision": None,
            "content_ids_served": [],
            "presentation": None,
            "student_feedback": None,
        }
    ],
}


class ChatHistoryViewTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(email="hist@example.com", password="pw12345!")
        self.client.force_authenticate(self.user)
        self.list_url = reverse("analytics-chat-history")
        self.detail_url = reverse(
            "analytics-chat-history-detail", kwargs={"session_id": "s-1"}
        )

    def tearDown(self):
        cache.clear()

    # --- unconfigured Supabase (the CI default) ---------------------------

    def test_list_requires_authentication(self):
        self.client.force_authenticate(None)
        self.assertIn(self.client.get(self.list_url).status_code, (401, 403))

    def test_list_reports_503_when_supabase_unconfigured(self):
        res = self.client.get(self.list_url)
        self.assertEqual(res.status_code, 503)
        self.assertIn("Supabase", res.json()["detail"])

    def test_detail_reports_503_when_supabase_unconfigured(self):
        res = self.client.get(self.detail_url)
        self.assertEqual(res.status_code, 503)
        self.assertIn("Supabase", res.json()["detail"])

    # --- configured Supabase ---------------------------------------------

    def _configured(self):
        return (
            patch("analytics.views.is_supabase_configured", return_value=True),
            patch("analytics.views.ensure_supabase_user", return_value="sb-user-1"),
        )

    def test_list_returns_payload_and_passes_pagination_through(self):
        cfg, usr = self._configured()
        with cfg, usr, patch(
            "analytics.views.build_chat_history_list", return_value=LIST_PAYLOAD
        ) as reader:
            res = self.client.get(self.list_url, {"page": "2", "page_size": "5"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), LIST_PAYLOAD)
        reader.assert_called_once_with(
            "sb-user-1", page=2, page_size=5, subject_filter=None
        )

    def test_list_clamps_page_size_and_ignores_garbage_params(self):
        cfg, usr = self._configured()
        with cfg, usr, patch(
            "analytics.views.build_chat_history_list", return_value=LIST_PAYLOAD
        ) as reader:
            res = self.client.get(self.list_url, {"page": "abc", "page_size": "9999"})
        self.assertEqual(res.status_code, 200)
        _, kwargs = reader.call_args
        self.assertEqual(kwargs["page"], 1)
        self.assertEqual(kwargs["page_size"], 100)  # MAX_PAGE_SIZE

    def test_list_surfaces_reader_failure_as_503_not_500(self):
        cfg, usr = self._configured()
        with cfg, usr, patch("analytics.views.build_chat_history_list", return_value=None):
            res = self.client.get(self.list_url)
        self.assertEqual(res.status_code, 503)

    def test_list_response_is_cached_per_page(self):
        cfg, usr = self._configured()
        with cfg, usr, patch(
            "analytics.views.build_chat_history_list", return_value=LIST_PAYLOAD
        ) as reader:
            self.client.get(self.list_url)
            self.client.get(self.list_url)
            self.assertEqual(reader.call_count, 1)
            self.client.get(self.list_url, {"page": "2"})
            self.assertEqual(reader.call_count, 2)

    def test_detail_returns_transcript(self):
        cfg, usr = self._configured()
        with cfg, usr, patch(
            "analytics.views.build_chat_history_detail", return_value=DETAIL_PAYLOAD
        ) as reader:
            res = self.client.get(self.detail_url)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json()["turns"]), 1)
        reader.assert_called_once_with("sb-user-1", "s-1")

    def test_detail_404s_for_unknown_or_foreign_session(self):
        cfg, usr = self._configured()
        with cfg, usr, patch("analytics.views.build_chat_history_detail", return_value=None):
            res = self.client.get(self.detail_url)
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json()["detail"], "Session not found.")
