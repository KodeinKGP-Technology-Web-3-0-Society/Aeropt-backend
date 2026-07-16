from django.test import SimpleTestCase

from analytics.supabase_dashboard import (
    _concept_tag,
    _display_score_percent,
    _is_unexplored,
)


class SupabaseDashboardDisplayTests(SimpleTestCase):
    def test_unexplored_cold_start(self):
        state = {"proficiency_score": 0.5, "is_cold_start": True, "attempts": 0}
        self.assertTrue(_is_unexplored(state))
        self.assertEqual(_display_score_percent(state), 0)
        self.assertIsNone(_concept_tag(0, False, unexplored=True))

    def test_explored_uses_internal_score(self):
        state = {"proficiency_score": 0.72, "is_cold_start": False, "attempts": 3}
        self.assertFalse(_is_unexplored(state))
        self.assertEqual(_display_score_percent(state), 72)
        self.assertEqual(_concept_tag(72, False), "STRONG")

    def test_zero_attempts_even_without_cold_start_flag(self):
        state = {"proficiency_score": 0.5, "is_cold_start": False, "attempts": 0}
        self.assertTrue(_is_unexplored(state))
        self.assertEqual(_display_score_percent(state), 0)
