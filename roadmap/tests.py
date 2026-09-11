from unittest import mock

from django.test import SimpleTestCase

from roadmap.generator import live_concept_ids, topological_sort
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


class TeachableConceptTests(SimpleTestCase):
    """`content_ready` must track authored lessons, not registered concepts.

    Syllabus content lands incrementally: a concept row can exist well before
    its theory/examples/questions do. Gating on the `concepts` table alone
    would call such a node "ready" and hand the student a button that opens
    on an empty retrieval.
    """

    REGISTERED = [
        {"concept_id": "has_lessons"},
        {"concept_id": "registered_only"},
    ]

    def _client_returning(self, content_rows):
        client = mock.MagicMock()
        (
            client.table.return_value.select.return_value.in_.return_value.execute.return_value
        ) = mock.Mock(data=content_rows)
        return client

    def test_concept_without_content_is_not_teachable(self):
        client = self._client_returning([{"primary_concept_id": "has_lessons"}])
        with mock.patch("roadmap.generator._read_live_concepts", return_value=self.REGISTERED), \
             mock.patch("roadmap.generator.get_supabase_client", return_value=client):
            self.assertEqual(live_concept_ids("Physics"), {"has_lessons"})

    def test_no_registered_concepts_skips_the_content_query(self):
        client = self._client_returning([])
        with mock.patch("roadmap.generator._read_live_concepts", return_value=[]), \
             mock.patch("roadmap.generator.get_supabase_client", return_value=client):
            self.assertEqual(live_concept_ids("Chemistry"), set())
        client.table.assert_not_called()

    def test_content_query_failure_falls_back_to_registered_concepts(self):
        """A roadmap render must never fail over this check."""
        client = mock.MagicMock()
        client.table.side_effect = RuntimeError("supabase down")
        with mock.patch("roadmap.generator._read_live_concepts", return_value=self.REGISTERED), \
             mock.patch("roadmap.generator.get_supabase_client", return_value=client):
            self.assertEqual(
                live_concept_ids("Physics"), {"has_lessons", "registered_only"}
            )
