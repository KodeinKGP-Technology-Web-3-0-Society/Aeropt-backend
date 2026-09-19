"""Sandbox queue mutation endpoints.

The queue itself is recomputed from roadmap state on every read, so these tests
build a real LearningPath and then assert that the student's decisions change
what a subsequent GET returns.
"""

from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APITestCase

from roadmap.models import LearningPath, NodeStatus, NodeType, PathNode
from sandbox.models import SandboxActionEvent, SandboxActionStatus
from sandbox.orchestrator import build_action_queue, build_queue_meta
from users.models import User


class SandboxActionEndpointTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(email="deck@example.com", password="pw12345!")
        self.client.force_authenticate(self.user)
        self.path = LearningPath.objects.create(user=self.user, subject="Physics", daily_goal_minutes=45)
        self.nodes = [
            PathNode.objects.create(
                learning_path=self.path,
                sequence_index=i,
                concept_id=f"concept_{i}",
                concept_name=f"Concept {i}",
                chapter="Rotational Motion",
                node_type=NodeType.LEARN,
                estimated_minutes=10,
                proficiency_pct=40,
                status=NodeStatus.IN_PROGRESS if i == 0 else NodeStatus.PENDING,
            )
            for i in range(3)
        ]
        self.path.total_nodes = 3
        self.path.active_nodes = 3
        self.path.save()

    def tearDown(self):
        cache.clear()

    def _queue_ids(self):
        res = self.client.get("/api/v1/sandbox/queue/")
        self.assertEqual(res.status_code, 200)
        return [item["id"] for item in res.json()["queue"]]

    def _focus_id(self):
        return f"focus-{self.nodes[0].id}"

    # --- success ----------------------------------------------------------

    def test_queue_lists_focus_card_before_any_decision(self):
        self.assertIn(self._focus_id(), self._queue_ids())

    def test_complete_records_event_and_removes_card_from_next_get(self):
        action_id = self._focus_id()
        res = self.client.post(
            f"/api/v1/sandbox/queue/{action_id}/complete/",
            {"action": "LEARN", "concept_id": "concept_0"},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["event"]["action_id"], action_id)
        self.assertEqual(body["event"]["status"], "completed")
        self.assertEqual(body["event"]["concept_id"], "concept_0")
        self.assertFalse(body["already_recorded"])
        # The response carries the recomputed queue, already without the card.
        self.assertNotIn(action_id, [i["id"] for i in body["queue"]["queue"]])
        self.assertEqual(body["queue"]["completed_today"], 1)
        # And the cached GET reflects it too.
        self.assertNotIn(action_id, self._queue_ids())

    def test_dismiss_records_a_dismissed_event(self):
        action_id = self._focus_id()
        res = self.client.post(f"/api/v1/sandbox/queue/{action_id}/dismiss/", {}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["event"]["status"], "dismissed")
        self.assertEqual(res.json()["queue"]["dismissed_today"], 1)
        self.assertNotIn(action_id, self._queue_ids())

    def test_unknown_action_id_is_accepted_and_recorded(self):
        # Ids are computed client-side from the queue payload; recording an id
        # that is no longer in today's queue is harmless, not an error.
        res = self.client.post("/api/v1/sandbox/queue/practice-slice/complete/", {}, format="json")
        self.assertEqual(res.status_code, 200)

    def test_requires_authentication(self):
        self.client.force_authenticate(None)
        res = self.client.post(f"/api/v1/sandbox/queue/{self._focus_id()}/complete/", {}, format="json")
        self.assertIn(res.status_code, (401, 403))

    # --- idempotency ------------------------------------------------------

    def test_completing_twice_does_not_error_or_double_count(self):
        action_id = self._focus_id()
        url = f"/api/v1/sandbox/queue/{action_id}/complete/"
        first = self.client.post(url, {}, format="json")
        second = self.client.post(url, {}, format="json")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertFalse(first.json()["already_recorded"])
        self.assertTrue(second.json()["already_recorded"])
        self.assertEqual(
            SandboxActionEvent.objects.filter(user=self.user, action_id=action_id).count(), 1
        )
        self.assertEqual(second.json()["queue"]["completed_today"], 1)

    def test_dismiss_after_complete_updates_the_same_row(self):
        action_id = self._focus_id()
        self.client.post(f"/api/v1/sandbox/queue/{action_id}/complete/", {}, format="json")
        res = self.client.post(f"/api/v1/sandbox/queue/{action_id}/dismiss/", {}, format="json")
        self.assertTrue(res.json()["already_recorded"])
        events = SandboxActionEvent.objects.filter(user=self.user, action_id=action_id)
        self.assertEqual(events.count(), 1)
        self.assertEqual(events.first().status, SandboxActionStatus.DISMISSED)
        self.assertEqual(res.json()["queue"]["completed_today"], 0)
        self.assertEqual(res.json()["queue"]["dismissed_today"], 1)

    def test_context_snapshot_is_not_erased_by_a_later_bare_post(self):
        action_id = self._focus_id()
        self.client.post(
            f"/api/v1/sandbox/queue/{action_id}/complete/",
            {"concept_id": "concept_0", "roadmap_node_id": str(self.nodes[0].id)},
            format="json",
        )
        res = self.client.post(f"/api/v1/sandbox/queue/{action_id}/dismiss/", {}, format="json")
        self.assertEqual(res.json()["event"]["concept_id"], "concept_0")

    # --- scoping ----------------------------------------------------------

    def test_decisions_are_scoped_per_user(self):
        action_id = self._focus_id()
        self.client.post(f"/api/v1/sandbox/queue/{action_id}/complete/", {}, format="json")
        other = User.objects.create_user(email="other@example.com", password="pw12345!")
        SandboxActionEvent.objects.create(
            user=other, action_id=action_id, status=SandboxActionStatus.COMPLETED
        )
        self.assertEqual(build_queue_meta(other)["completed_today"], 1)
        self.assertEqual(build_queue_meta(self.user)["completed_today"], 1)
        self.assertEqual(SandboxActionEvent.objects.count(), 2)

    def test_yesterdays_decision_does_not_hide_todays_card(self):
        action_id = self._focus_id()
        SandboxActionEvent.objects.create(
            user=self.user,
            action_id=action_id,
            status=SandboxActionStatus.COMPLETED,
            for_date=timezone.localdate() - timezone.timedelta(days=1),
        )
        self.assertIn(action_id, [item["id"] for item in build_action_queue(self.user)])
        self.assertEqual(build_queue_meta(self.user)["completed_today"], 0)

    def test_queue_empties_once_every_card_is_decided(self):
        # Completing the focus card promotes the next one, so drain in a loop —
        # it must terminate, i.e. a decided card must never come back under a
        # different position prefix.
        for _ in range(10):
            ids = self._queue_ids()
            if not ids:
                break
            for action_id in ids:
                self.client.post(f"/api/v1/sandbox/queue/{action_id}/complete/", {}, format="json")
        res = self.client.get("/api/v1/sandbox/queue/")
        self.assertEqual(res.json()["count"], 0)
        self.assertEqual(res.json()["queue"], [])

    def test_a_card_decided_as_next_does_not_return_as_focus(self):
        # The position prefix moves as the student advances; the decision must
        # follow the card, not the slot it happened to be in.
        next_id = f"next-{self.nodes[1].id}"
        self.assertIn(next_id, self._queue_ids())
        self.client.post(f"/api/v1/sandbox/queue/{next_id}/complete/", {}, format="json")
        self.client.post(f"/api/v1/sandbox/queue/{self._focus_id()}/complete/", {}, format="json")
        ids = self._queue_ids()
        self.assertNotIn(f"focus-{self.nodes[1].id}", ids)
        self.assertNotIn(next_id, ids)

    def test_reposted_under_a_different_prefix_updates_the_same_row(self):
        node_id = str(self.nodes[1].id)
        self.client.post(f"/api/v1/sandbox/queue/next-{node_id}/complete/", {}, format="json")
        res = self.client.post(f"/api/v1/sandbox/queue/focus-{node_id}/dismiss/", {}, format="json")
        self.assertTrue(res.json()["already_recorded"])
        self.assertEqual(SandboxActionEvent.objects.filter(user=self.user).count(), 1)
        event = SandboxActionEvent.objects.get(user=self.user)
        self.assertEqual(event.target_key, node_id)
        self.assertEqual(event.action_id, f"focus-{node_id}")

    # --- degrades without Supabase ---------------------------------------

    def test_endpoints_work_with_supabase_unconfigured(self):
        # CI always runs unconfigured; the whole queue path is Django-only, so
        # this must be a plain 200 rather than a 503 or a 500.
        self.assertEqual(self.client.get("/api/v1/sandbox/queue/").status_code, 200)
        self.assertEqual(
            self.client.post(
                f"/api/v1/sandbox/queue/{self._focus_id()}/complete/", {}, format="json"
            ).status_code,
            200,
        )
