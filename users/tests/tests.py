from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from users.models import JourneyType, OnboardingSession, StudentProfile, SyllabusPlacement, User
from users.placement import build_concept_state_rows, node_proficiency_display


class PlacementSeedingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="student@example.com",
            password="testpass123",
            full_name="Test Student",
        )
        self.profile = StudentProfile.objects.get(user=self.user)
        self.placement = SyllabusPlacement.objects.get(user=self.user)

    def _concepts(self):
        return [
            {"concept_id": "newtons_first_law", "chapter": "Laws of Motion", "subject": "Physics"},
            {"concept_id": "torque", "chapter": "Rotational Motion", "subject": "Physics"},
        ]

    def test_fresh_start_seeds_cold_start_at_fifty_percent(self):
        self.placement.journey_type = JourneyType.FRESH_START
        rows = build_concept_state_rows("uid", self._concepts(), self.placement)
        self.assertTrue(all(r["is_cold_start"] for r in rows))
        self.assertTrue(all(r["proficiency_score"] == 0.5 for r in rows))

    def test_mid_journey_varies_by_chapter_depth(self):
        self.placement.journey_type = JourneyType.MID_JOURNEY
        self.placement.covered_chapters = ["Laws of Motion", "Rotational Motion"]
        self.placement.self_assessed_coverage = {
            "Laws of Motion": "strong",
            "Rotational Motion": "barely",
        }
        rows = {r["concept_id"]: r for r in build_concept_state_rows("uid", self._concepts(), self.placement)}
        self.assertEqual(rows["newtons_first_law"]["proficiency_score"], 0.65)
        self.assertFalse(rows["newtons_first_law"]["is_cold_start"])
        self.assertEqual(rows["torque"]["proficiency_score"], 0.25)
        self.assertTrue(rows["torque"]["flagged_weak"])

    def test_register_creates_profile_and_placement(self):
        self.assertIsNotNone(self.profile)
        self.assertIsNotNone(self.placement)
        self.assertFalse(self.profile.onboarding_completed)

    def test_node_proficiency_display_not_started_for_fresh_start(self):
        pct, label = node_proficiency_display(0.5, "Laws of Motion", self.placement, is_cold_start=True)
        self.assertEqual(pct, 0)
        self.assertEqual(label, "not_started")

    def test_node_proficiency_display_shows_covered_chapter_score(self):
        self.placement.journey_type = JourneyType.MID_JOURNEY
        self.placement.covered_chapters = ["Laws of Motion"]
        pct, label = node_proficiency_display(
            0.65,
            "Laws of Motion",
            self.placement,
            is_cold_start=False,
        )
        self.assertEqual(pct, 65)
        self.assertEqual(label, "almost_mastered")


class OnboardingMilestoneApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="onboard@example.com",
            password="testpass123",
            full_name="Onboard Student",
        )
        self.client.force_authenticate(self.user)
        self.profile = StudentProfile.objects.get(user=self.user)
        self.placement = SyllabusPlacement.objects.get(user=self.user)
        self.session = OnboardingSession.objects.get(user=self.user)

    def test_patch_onboarding_session_advances_step_and_snapshot(self):
        url = f"/api/v1/users/onboarding-sessions/{self.user.id}/"
        payload = {
            "current_step": 3,
            "snapshot": {
                "journey_type": "mid_journey",
                "target_exam": "JEE_MAINS",
                "current_step": 3,
            },
        }
        res = self.client.patch(url, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.session.refresh_from_db()
        self.assertEqual(self.session.current_step, 3)
        self.assertEqual(self.session.snapshot.get("target_exam"), "JEE_MAINS")

    def test_patch_profile_rhythm_fields(self):
        url = f"/api/v1/users/student-profiles/{self.user.id}/"
        res = self.client.patch(
            url,
            {"daily_goal_minutes": 90, "preferred_depth": "deep", "onboarding_step": 5},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.daily_goal_minutes, 90)
        self.assertEqual(self.profile.preferred_depth, "deep")
        self.assertEqual(self.profile.onboarding_step, 5)

    def test_complete_marks_onboarding_done(self):
        url = "/api/v1/onboarding/complete/"
        res = self.client.post(
            url,
            {
                "profile": {
                    "target_exam": "BOTH",
                    "target_year": 2027,
                    "grade_level": "CLASS_12",
                    "daily_goal_minutes": 45,
                    "preferred_depth": "standard",
                    "onboarding_step": 7,
                },
                "placement": {
                    "journey_type": "fresh_start",
                    "covered_chapters": [],
                    "self_assessed_coverage": {},
                    "diagnostic_baseline": {},
                },
                "snapshot": {"current_step": 7},
                "current_step": 7,
                "onboarding_step": 7,
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data.get("ok"))
        self.profile.refresh_from_db()
        self.session.refresh_from_db()
        self.assertTrue(self.profile.onboarding_completed)
        self.assertEqual(self.profile.onboarding_step, 7)
        self.assertIsNotNone(self.session.completed_at)
