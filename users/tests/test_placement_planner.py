from unittest.mock import patch

from django.test import TestCase

from users.models import JourneyType
from users.placement import build_concept_state_rows, sandbox_summary_from_rows
from users.placement_planner import build_placement_plan

_MOCK_CONCEPTS = [
    {"concept_id": "newtons_1st_law", "concept_name": "Newton's 1st Law", "chapter": "Laws of Motion", "subject": "Physics"},
    {"concept_id": "newtons_2nd_law_f__ma", "concept_name": "Newton's 2nd Law", "chapter": "Laws of Motion", "subject": "Physics"},
    {"concept_id": "torque", "concept_name": "Torque", "chapter": "Rotational Motion", "subject": "Physics"},
    {"concept_id": "work", "concept_name": "Work", "chapter": "Work Energy & Power", "subject": "Physics"},
]


@patch("users.placement_planner._practice_concept_ids", return_value={"newtons_2nd_law_f__ma", "torque"})
@patch("users.placement_planner._read_live_concepts", return_value=_MOCK_CONCEPTS)
class PlacementPlannerTests(TestCase):
    def test_mid_journey_probes_covered_chapters(self, _mock_concepts, _mock_practice):
        plan = build_placement_plan(
            journey_type=JourneyType.MID_JOURNEY,
            covered_chapters=["Laws of Motion", "Rotational Motion"],
            self_assessed_coverage={
                "Laws of Motion": "strong",
                "Rotational Motion": "barely",
            },
        )
        self.assertEqual(plan["total_probes"], 2)
        self.assertEqual(len(plan["probes"]), 2)
        self.assertIn("Work Energy & Power", plan["skipped_chapters"])

    def test_revision_dropper_probes_covered_chapters(self, _mock_concepts, _mock_practice):
        covered = ["Laws of Motion", "Rotational Motion", "Work Energy & Power"]
        depth = {ch: "moderate" for ch in covered}
        plan = build_placement_plan(
            journey_type=JourneyType.REVISION_DROPPER,
            covered_chapters=covered,
            self_assessed_coverage=depth,
        )
        self.assertEqual(plan["total_probes"], 3)
        self.assertEqual(len(plan["skipped_chapters"]), 0)

    def test_fresh_start_limits_to_two_probes(self, _mock_concepts, _mock_practice):
        plan = build_placement_plan(
            journey_type=JourneyType.FRESH_START,
            covered_chapters=[],
            self_assessed_coverage={},
        )
        self.assertLessEqual(plan["total_probes"], 2)
        self.assertGreater(plan["total_probes"], 0)


class PlacementMergeTests(TestCase):
    def setUp(self):
        from users.models import StudentProfile, SyllabusPlacement, User

        self.user = User.objects.create_user(
            email="merge@example.com",
            password="testpass123",
            full_name="Merge Student",
        )
        self.profile = StudentProfile.objects.get(user=self.user)
        self.placement = SyllabusPlacement.objects.get(user=self.user)

    def _concepts(self):
        return [
            {"concept_id": "newtons_first_law", "chapter": "Laws of Motion", "subject": "Physics"},
            {"concept_id": "torque", "chapter": "Rotational Motion", "subject": "Physics"},
        ]

    def test_diagnostic_overrides_mid_journey_depth(self):
        self.placement.journey_type = JourneyType.MID_JOURNEY
        self.placement.covered_chapters = ["Laws of Motion"]
        self.placement.self_assessed_coverage = {"Laws of Motion": "strong"}
        self.placement.diagnostic_baseline = {
            "concept_scores": {"newtons_first_law": 0.32},
            "chapter_scores": {"Laws of Motion": 0.32},
            "probed_chapters": ["Laws of Motion"],
            "overall": 0.32,
            "source": "onboarding_v1",
        }
        rows = {r["concept_id"]: r for r in build_concept_state_rows("uid", self._concepts(), self.placement)}
        self.assertEqual(rows["newtons_first_law"]["proficiency_score"], 0.32)
        self.assertTrue(rows["newtons_first_law"]["flagged_weak"])

    def test_sandbox_summary_includes_chapter_snapshots(self):
        self.placement.journey_type = JourneyType.MID_JOURNEY
        self.placement.covered_chapters = ["Laws of Motion"]
        self.placement.diagnostic_baseline = {
            "chapter_scores": {"Laws of Motion": 0.32},
            "probed_chapters": ["Laws of Motion"],
        }
        rows = build_concept_state_rows("uid", self._concepts(), self.placement)
        summary = sandbox_summary_from_rows(self.profile, self.placement, rows)
        self.assertIn("chapter_snapshots", summary)
        self.assertTrue(any(s["chapter"] == "Laws of Motion" for s in summary["chapter_snapshots"]))
