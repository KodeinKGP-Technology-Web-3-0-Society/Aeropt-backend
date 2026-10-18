from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APITestCase

from analytics.models import ConceptMastery
from classroom.models import ConceptTracker, EvidenceEvent
from classroom.tracker import seed_from_paths
from roadmap.models import LearningPath, PathNode
from users.models import User


def _path(user, concept_id="torque", proficiency=80, name="Torque"):
    path = LearningPath.objects.create(user=user, subject="Physics", is_active=True)
    PathNode.objects.create(
        learning_path=path,
        sequence_index=0,
        concept_id=concept_id,
        concept_name=name,
        chapter="Rotation",
        proficiency_pct=proficiency,
    )
    return path


class SeedTests(TestCase):
    def test_seed_copies_path_once_and_does_not_overwrite(self):
        user = User.objects.create_user(email="seed@example.com", password="testpass123", full_name="Seed")
        _path(user, proficiency=42)
        created = seed_from_paths(LearningPath, ConceptTracker)
        self.assertEqual(created, 1)
        row = ConceptTracker.objects.get(user=user, concept_id="torque")
        self.assertEqual(row.mastery, 42)
        self.assertTrue(row.flagged_weak)
        self.assertEqual(row.attempts, 0)
        self.assertEqual(row.title, "Torque")

        row.mastery = 90
        row.flagged_weak = False
        row.save(update_fields=["mastery", "flagged_weak"])
        again = seed_from_paths(LearningPath, ConceptTracker)
        self.assertEqual(again, 0)
        row.refresh_from_db()
        self.assertEqual(row.mastery, 90)


class EvidenceApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="score@example.com",
            password="testpass123",
            full_name="Score Student",
        )
        self.other = User.objects.create_user(
            email="other@example.com",
            password="testpass123",
            full_name="Other",
        )
        _path(self.user, proficiency=80)
        seed_from_paths(LearningPath, ConceptTracker)
        self.client.force_authenticate(self.user)
        cache.clear()

    def test_attempt_with_mastery_moves_home_and_not_a_second_score(self):
        before = ConceptMastery.objects.count()
        res = self.client.post(
            "/api/v1/classroom/evidence/",
            {
                "concept_id": "torque",
                "surface": "lesson",
                "specialist": "tutor",
                "kind": "attempt",
                "payload": {"correct": False, "mastery": 30},
            },
            format="json",
        )
        self.assertEqual(res.status_code, 201)
        row = ConceptTracker.objects.get(user=self.user, concept_id="torque")
        self.assertEqual(row.attempts, 1)
        self.assertEqual(row.correct, 0)
        self.assertEqual(row.mastery, 30)
        self.assertTrue(row.flagged_weak)
        self.assertEqual(EvidenceEvent.objects.filter(user=self.user).count(), 1)
        self.assertEqual(ConceptMastery.objects.count(), before)

        home = self.client.get("/api/v1/classroom/home/")
        self.assertEqual(home.status_code, 200)
        torque = next(item for item in home.data["map"] if item["concept_id"] == "torque")
        self.assertEqual(torque["mastery"], 30)
        self.assertEqual(home.data["revise"][0]["concept_id"], "torque")
        self.assertEqual(home.data["revise"][0]["due"], "today")
        self.assertEqual(home.data["readiness"], {"score": 30, "label": "early"})

    def test_cached_home_follows_a_later_evidence_write(self):
        first = self.client.get("/api/v1/classroom/home/")
        torque = next(item for item in first.data["map"] if item["concept_id"] == "torque")
        self.assertEqual(torque["mastery"], 80)
        res = self.client.post(
            "/api/v1/classroom/evidence/",
            {
                "concept_id": "torque",
                "surface": "lesson",
                "specialist": "tutor",
                "kind": "mastery",
                "payload": {"mastery": 30},
            },
            format="json",
        )
        self.assertEqual(res.status_code, 201)
        second = self.client.get("/api/v1/classroom/home/")
        torque = next(item for item in second.data["map"] if item["concept_id"] == "torque")
        self.assertEqual(torque["mastery"], 30)

    def test_mastery_event_sets_score_without_counting_an_attempt(self):
        res = self.client.post(
            "/api/v1/classroom/evidence/",
            {
                "concept_id": "torque",
                "surface": "lesson",
                "specialist": "tutor",
                "kind": "mastery",
                "payload": {"mastery": 70},
            },
            format="json",
        )
        self.assertEqual(res.status_code, 201)
        row = ConceptTracker.objects.get(user=self.user, concept_id="torque")
        self.assertEqual(row.mastery, 70)
        self.assertEqual(row.attempts, 0)
        self.assertFalse(row.flagged_weak)

    def test_readiness_is_mean_of_attempted_rows_only(self):
        ConceptTracker.objects.create(
            user=self.user,
            concept_id="energy",
            title="Energy",
            mastery=90,
            attempts=0,
            correct=0,
            flagged_weak=False,
        )
        self.client.post(
            "/api/v1/classroom/evidence/",
            {
                "concept_id": "torque",
                "surface": "assess",
                "specialist": "evaluation",
                "kind": "attempt",
                "payload": {"correct": True, "mastery": 40},
            },
            format="json",
        )
        self.client.post(
            "/api/v1/classroom/evidence/",
            {
                "concept_id": "friction",
                "surface": "assess",
                "specialist": "evaluation",
                "kind": "attempt",
                "payload": {"correct": True, "mastery": 60},
            },
            format="json",
        )
        home = self.client.get("/api/v1/classroom/home/")
        self.assertEqual(home.data["readiness"]["score"], 50)
        self.assertEqual(home.data["readiness"]["label"], "building")
        ids = [item["concept_id"] for item in home.data["revise"]]
        self.assertIn("torque", ids)
        self.assertNotIn("friction", ids)
        self.assertNotIn("energy", ids)

    def test_unknown_kind_is_rejected(self):
        res = self.client.post(
            "/api/v1/classroom/evidence/",
            {
                "concept_id": "torque",
                "surface": "lesson",
                "specialist": "tutor",
                "kind": "grade",
                "payload": {},
            },
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(EvidenceEvent.objects.count(), 0)

    def test_other_learner_does_not_see_the_row(self):
        self.client.post(
            "/api/v1/classroom/evidence/",
            {
                "concept_id": "torque",
                "surface": "lesson",
                "specialist": "tutor",
                "kind": "mastery",
                "payload": {"mastery": 12},
            },
            format="json",
        )
        self.client.force_authenticate(self.other)
        home = self.client.get("/api/v1/classroom/home/")
        self.assertEqual([m for m in home.data["map"] if m.get("mastery", 0) > 0], [])
        self.assertEqual(home.data["revise"], [])
        self.assertEqual(home.data["readiness"]["score"], 0)

    def test_anonymous_post_is_rejected(self):
        self.client.force_authenticate(user=None)
        res = self.client.post(
            "/api/v1/classroom/evidence/",
            {
                "concept_id": "torque",
                "surface": "lesson",
                "specialist": "tutor",
                "kind": "attempt",
                "payload": {"correct": True},
            },
            format="json",
        )
        self.assertEqual(res.status_code, 401)


class DaySpecialistHomeTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="day@example.com",
            password="testpass123",
            full_name="Day Student",
        )
        _path(self.user, proficiency=40)
        self.client.force_authenticate(self.user)
        cache.clear()

    def test_stored_today_plan_and_readiness_win(self):
        from django.utils import timezone

        from classroom.models import EvidenceEvent

        for_date = timezone.localdate().isoformat()
        EvidenceEvent.objects.create(
            user=self.user,
            concept_id="friction",
            surface="home",
            specialist="daily",
            kind="today",
            payload={
                "concept_id": "friction",
                "title": "Friction",
                "action": "revise",
                "minutes": 25,
                "for_date": for_date,
            },
        )
        EvidenceEvent.objects.create(
            user=self.user,
            surface="home",
            specialist="planning",
            kind="plan",
            payload=[
                {
                    "concept_id": "energy",
                    "title": "Energy",
                    "status": "pending",
                    "when": "today",
                }
            ],
        )
        EvidenceEvent.objects.create(
            user=self.user,
            surface="home",
            specialist="readiness-agent",
            kind="readiness",
            payload={"score": 62, "label": "building"},
        )
        home = self.client.get("/api/v1/classroom/home/")
        self.assertEqual(home.status_code, 200)
        self.assertEqual(home.data["today"]["concept_id"], "friction")
        self.assertNotIn("provisional", home.data["today"])
        self.assertEqual(home.data["plan"][0]["concept_id"], "energy")
        self.assertEqual(home.data["readiness"], {"score": 62, "label": "building"})

    def test_missing_today_is_provisional_when_agent_is_unset(self):
        home = self.client.get("/api/v1/classroom/home/")
        self.assertEqual(home.data["today"]["concept_id"], "torque")
        self.assertTrue(home.data["today"]["provisional"])

    def test_complete_omits_todays_concept(self):
        warm = self.client.get("/api/v1/classroom/home/")
        self.assertEqual(warm.data["today"]["concept_id"], "torque")
        res = self.client.post("/api/v1/classroom/today/torque/complete/", {}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertIsNone(res.data["today"])
        again = self.client.get("/api/v1/classroom/home/")
        self.assertIsNone(again.data["today"])

    def test_home_loads_the_active_path_once_and_caches_the_payload(self):
        from unittest.mock import patch

        from classroom.views import _provisional_home
        from roadmap.generator import get_active_learning_path as real_get_path

        with (
            patch("classroom.views.get_active_learning_path", wraps=real_get_path) as loaded,
            patch("roadmap.generator.get_active_learning_path", wraps=real_get_path) as loaded_again,
            patch("classroom.views._provisional_home", wraps=_provisional_home) as built,
        ):
            first = self.client.get("/api/v1/classroom/home/")
            second = self.client.get("/api/v1/classroom/home/")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.data, first.data)
        self.assertEqual(loaded.call_count, 1)
        self.assertEqual(loaded_again.call_count, 0)
        self.assertEqual(built.call_count, 1)

    def test_agent_fill_is_stored_and_not_repeated(self):
        from unittest.mock import patch

        from classroom.models import EvidenceEvent

        calls = []

        def fake(name, body):
            calls.append(name)
            for_date = body["for_date"]
            if name == "daily":
                return {
                    "today": {
                        "concept_id": "energy",
                        "title": "Energy",
                        "action": "lesson",
                        "minutes": 25,
                        "for_date": for_date,
                    }
                }
            if name == "plan":
                return {
                    "plan": [
                        {
                            "concept_id": "energy",
                            "title": "Energy",
                            "status": "in_progress",
                            "when": "today",
                        }
                    ]
                }
            if name == "revise":
                return {"revise": []}
            if name == "readiness":
                return {"readiness": {"score": 55, "label": "building"}}
            return None

        with patch("classroom.day.call_specialist", side_effect=fake):
            first = self.client.get("/api/v1/classroom/home/")
            second = self.client.get("/api/v1/classroom/home/")

        self.assertEqual(first.data["today"]["concept_id"], "energy")
        self.assertNotIn("provisional", first.data["today"])
        self.assertEqual(second.data["today"]["concept_id"], "energy")
        self.assertEqual(calls.count("daily"), 1)
        self.assertEqual(
            EvidenceEvent.objects.filter(user=self.user, kind="today").count(),
            1,
        )


class SessionTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="room@example.com",
            password="testpass123",
            full_name="Room Student",
        )
        self.client.force_authenticate(self.user)

    def test_repeat_lesson_open_returns_the_same_row(self):
        first = self.client.post(
            "/api/v1/classroom/sessions/",
            {"surface": "lesson", "concept_id": "torque"},
            format="json",
        )
        second = self.client.post(
            "/api/v1/classroom/sessions/",
            {"surface": "lesson", "concept_id": "torque", "agent_session_id": "sess-1"},
            format="json",
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.data["agent_session_id"], "sess-1")
        self.assertEqual(second.data["surface"], "lesson")
        lookup = self.client.get("/api/v1/classroom/sessions/sess-1/")
        self.assertEqual(lookup.status_code, 200)
        self.assertEqual(lookup.data["concept_id"], "torque")
