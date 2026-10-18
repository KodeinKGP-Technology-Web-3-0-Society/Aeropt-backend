from django.test import SimpleTestCase

from analytics.supabase_progress import (
    PROGRESS_DAYS,
    _aggregate_mistakes,
    _chapter_series,
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

    def test_chapter_series_reads_each_concept_once(self):
        states = [
            {"concept_id": "other", "proficiency_score": 0.1, "attempts": 0, "is_cold_start": True},
            {"concept_id": "laws", "proficiency_score": 0.8, "attempts": 1},
            {"concept_id": "work", "proficiency_score": 0.4, "attempts": 1},
            {"concept_id": "laws", "proficiency_score": 0.1, "attempts": 9},
        ]
        payload = _chapter_series(
            attempts=[],
            concept_chapters={
                "laws": "Laws of Motion",
                "work": "Laws of Motion",
                "spin": "Rotational Motion",
            },
            baseline={},
            states=states,
        )
        by_name = {chapter["name"]: chapter["data"] for chapter in payload["chapters"]}
        self.assertEqual(len(payload["dates"]), PROGRESS_DAYS)
        # 80 and 40 average to 60. The later duplicate state for "laws" must not win.
        self.assertTrue(all(value == 60 for value in by_name["Laws of Motion"]))
        self.assertNotIn("Rotational Motion", by_name)
