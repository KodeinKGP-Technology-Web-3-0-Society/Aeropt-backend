from django.test import SimpleTestCase

from roadmap.generator import topological_sort
from roadmap.syllabus import (
    available_subjects,
    chapter_order_map,
    prerequisite_map,
    syllabus_concept_map,
)

# SimpleTestCase (not TestCase): every assertion here reads YAML only, so
# these run without provisioning a database.


class SyllabusSpecTests(SimpleTestCase):
    def test_every_registered_subject_has_a_syllabus(self):
        self.assertEqual(sorted(available_subjects()), ["Chemistry", "Maths", "Physics"])

    def test_syllabus_has_at_least_20_concepts(self):
        for subject in available_subjects():
            with self.subTest(subject=subject):
                self.assertGreaterEqual(len(syllabus_concept_map(subject)), 20)

    def test_no_dangling_prerequisites(self):
        """A prerequisite naming a concept that doesn't exist would silently
        drop out of the ordering, so the roadmap would teach a dependent
        before its foundation with no visible error."""
        for subject in available_subjects():
            with self.subTest(subject=subject):
                concepts = syllabus_concept_map(subject)
                for cid, deps in prerequisite_map(subject).items():
                    for dep in deps:
                        self.assertIn(dep, concepts, f"{subject}: {cid} -> missing {dep}")

    def test_chapter_orders_are_unique(self):
        for subject in available_subjects():
            with self.subTest(subject=subject):
                orders = list(chapter_order_map(subject).values())
                self.assertEqual(len(orders), len(set(orders)))


class TopologicalSortTests(SimpleTestCase):
    def test_topological_sort_respects_prerequisites(self):
        for subject in available_subjects():
            with self.subTest(subject=subject):
                concept_ids = list(syllabus_concept_map(subject).keys())
                prereqs = prerequisite_map(subject)
                ordered = topological_sort(concept_ids, prereqs)
                self.assertCountEqual(ordered, concept_ids)
                positions = {cid: idx for idx, cid in enumerate(ordered)}
                for cid, deps in prereqs.items():
                    for dep in deps:
                        if dep in positions and cid in positions:
                            self.assertLess(positions[dep], positions[cid])

    def test_priority_breaks_ties_in_syllabus_order(self):
        """Without a priority, unblocked concepts are ordered alphabetically,
        which scatters chapters — a student would open a 16-chapter path on
        whichever concept_id happened to sort first."""
        ids = ["zebra_first_chapter", "alpha_last_chapter"]
        prereqs = {"zebra_first_chapter": [], "alpha_last_chapter": []}

        self.assertEqual(
            topological_sort(ids, prereqs),
            ["alpha_last_chapter", "zebra_first_chapter"],
        )
        self.assertEqual(
            topological_sort(
                ids, prereqs, priority={"zebra_first_chapter": 0, "alpha_last_chapter": 1}
            ),
            ["zebra_first_chapter", "alpha_last_chapter"],
        )

    def test_priority_never_overrides_a_prerequisite(self):
        """Priority is a tie-break only — it must not be able to pull a
        dependent ahead of its own prerequisite."""
        ids = ["foundation", "advanced"]
        prereqs = {"advanced": ["foundation"], "foundation": []}
        ordered = topological_sort(
            ids, prereqs, priority={"advanced": 0, "foundation": 99}
        )
        self.assertEqual(ordered, ["foundation", "advanced"])

    def test_cycle_still_returns_every_concept(self):
        ids = ["a", "b"]
        prereqs = {"a": ["b"], "b": ["a"]}
        self.assertCountEqual(topological_sort(ids, prereqs), ids)
