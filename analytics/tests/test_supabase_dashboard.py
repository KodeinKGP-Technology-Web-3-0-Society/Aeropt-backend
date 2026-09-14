from django.test import SimpleTestCase

from analytics.supabase_dashboard import (
    _concept_tag,
    _display_score_percent,
    _is_unexplored,
)
from users.models import JourneyType, SyllabusPlacement


class SupabaseDashboardDisplayTests(SimpleTestCase):
    def test_unexplored_cold_start(self):
        state = {"proficiency_score": 0.5, "is_cold_start": True, "attempts": 0}
        self.assertTrue(_is_unexplored(state, "Laws of Motion", None))
        self.assertEqual(_display_score_percent(state, "Laws of Motion", None), 0)
        self.assertIsNone(_concept_tag(0, False, unexplored=True))

    def test_explored_uses_internal_score(self):
        state = {"proficiency_score": 0.72, "is_cold_start": False, "attempts": 3}
        self.assertFalse(_is_unexplored(state, "Laws of Motion", None))
        self.assertEqual(_display_score_percent(state, "Laws of Motion", None), 72)
        self.assertEqual(_concept_tag(76, False), "STRONG")

    def test_placement_seeded_score_with_covered_chapter(self):
        """Mid-journey: show seeded score for chapters marked as covered."""
        placement = SyllabusPlacement(
            journey_type=JourneyType.MID_JOURNEY,
            covered_chapters=["Laws of Motion"],
            self_assessed_coverage={"Laws of Motion": "moderate"}
        )
        state = {
            "proficiency_score": 0.45,
            "is_cold_start": False,
            "attempts": 0,
            "concept_id": "newtons_first_law"
        }
        self.assertFalse(_is_unexplored(state, "Laws of Motion", placement))
        self.assertEqual(_display_score_percent(state, "Laws of Motion", placement), 45)

    def test_hide_score_for_uncovered_chapter(self):
        """Mid-journey: hide score for chapters NOT marked as covered."""
        placement = SyllabusPlacement(
            journey_type=JourneyType.MID_JOURNEY,
            covered_chapters=["Laws of Motion"],
        )
        state = {
            "proficiency_score": 0.5,
            "is_cold_start": True,
            "attempts": 0,
            "concept_id": "torque"
        }
        self.assertTrue(_is_unexplored(state, "Rotational Motion", placement))
        self.assertEqual(_display_score_percent(state, "Rotational Motion", placement), 0)

    def test_diagnostic_seeded_shows_score(self):
        """Diagnostic tested concepts show their score even without practice."""
        placement = SyllabusPlacement(
            journey_type=JourneyType.FRESH_START,
            diagnostic_baseline={
                "concept_scores": {"newtons_first_law": 0.53}
            }
        )
        state = {
            "proficiency_score": 0.53,
            "is_cold_start": False,
            "attempts": 0,
            "concept_id": "newtons_first_law"
        }
        self.assertFalse(_is_unexplored(state, "Laws of Motion", placement))
        self.assertEqual(_display_score_percent(state, "Laws of Motion", placement), 53)

    def test_show_score_after_practice(self):
        """Always show score if user has practiced (attempts > 0)."""
        state = {
            "proficiency_score": 0.68,
            "is_cold_start": False,
            "attempts": 2,
            "concept_id": "newtons_first_law"
        }
        self.assertFalse(_is_unexplored(state, "Laws of Motion", None))
        self.assertEqual(_display_score_percent(state, "Laws of Motion", None), 68)
