from django.test import SimpleTestCase

from analytics.supabase_progress import (
    _aggregate_mistakes,
    _trend_label,
    _wma_update,
)


class SupabaseProgressHelpersTests(SimpleTestCase):
    def test_wma_update_correct(self):
        self.assertAlmostEqual(_wma_update(0.5, True), 0.65)

    def test_wma_update_incorrect(self):
        self.assertAlmostEqual(_wma_update(0.5, False), 0.35)

    def test_trend_label(self):
        self.assertEqual(_trend_label(0.7, 0.5), "up")
        self.assertEqual(_trend_label(0.4, 0.5), "down")
        self.assertEqual(_trend_label(0.51, 0.5), "flat")

    def test_aggregate_mistakes(self):
        states = [
            {
                "error_type_dist": {
                    "conceptual": 2,
                    "procedural": 1,
                    "calculation": 0,
                    "misread": 1,
                }
            },
            {
                "error_type_dist": {
                    "conceptual": 1,
                    "procedural": 2,
                    "calculation": 1,
                    "misread": 0,
                }
            },
        ]
        rows = _aggregate_mistakes(states)
        by_type = {row["type"]: row for row in rows}
        self.assertEqual(by_type["Conceptual"]["count"], 3)
        self.assertEqual(by_type["Procedural"]["count"], 3)
        self.assertEqual(by_type["Calculation"]["count"], 1)
        self.assertEqual(by_type["Misinterpretation"]["count"], 1)
        self.assertEqual(sum(row["percentage"] for row in rows), 100)
