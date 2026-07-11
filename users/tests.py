from django.test import TestCase

from users.models import JourneyType, StudentProfile, SyllabusPlacement, User
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
        self.assertIsNone(pct)
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
        self.assertEqual(label, "strong")
