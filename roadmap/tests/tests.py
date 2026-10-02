from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from roadmap.generator import compose_study_plan, live_concept_ids, topological_sort, _path_concept_rows
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


def _node(**kwargs):
    defaults = {
        "id": "n1",
        "sequence_index": 0,
        "status": "pending",
        "chapter": "Laws of Motion",
        "concept_name": "Newton's 1st Law",
        "node_type": "LEARN",
        "content_sequence": ["theory", "example", "practice"],
        "estimated_minutes": 10,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class StudyPlanTests(SimpleTestCase):
    def test_plan_is_a_short_week_not_the_full_syllabus(self):
        nodes = [
            _node(id="a", sequence_index=0, status="in_progress", concept_name="Newton's 1st Law"),
            _node(id="b", sequence_index=1, status="pending", concept_name="Newton's 2nd Law"),
            _node(id="c", sequence_index=2, status="pending", concept_name="Tension"),
            _node(
                id="d",
                sequence_index=3,
                status="pending",
                chapter="Rotational Motion",
                concept_name="Torque",
            ),
            _node(
                id="e",
                sequence_index=4,
                status="pending",
                chapter="Rotational Motion",
                concept_name="Moment of Inertia",
            ),
            _node(
                id="f",
                sequence_index=5,
                status="pending",
                chapter="Optics",
                concept_name="Lenses",
            ),
        ]
        plan = compose_study_plan(nodes, subject="Physics", daily_goal_minutes=45)
        self.assertEqual(plan["today_node_id"], "a")
        self.assertLessEqual(len(plan["this_week"]), 5)
        self.assertGreaterEqual(len(plan["this_week"]), 3)
        self.assertTrue(plan["headline"].startswith("This week:"))
        later_chapters = {row["chapter"] for row in plan["later"]}
        this_week_ids = {row["node_id"] for row in plan["this_week"]}
        self.assertIn("Optics", later_chapters)
        self.assertIn("Rotational Motion", later_chapters)
        self.assertNotIn("Laws of Motion", later_chapters)
        self.assertIn("a", this_week_ids)
        self.assertNotIn("f", this_week_ids)
        self.assertEqual(plan["later_more"], 0)

    def test_week_starts_at_in_progress_not_the_first_pending(self):
        nodes = [
            _node(id="a", sequence_index=0, status="pending", concept_name="Units"),
            _node(id="b", sequence_index=1, status="pending", concept_name="Vectors"),
            _node(
                id="c",
                sequence_index=2,
                status="in_progress",
                chapter="Kinematics",
                concept_name="Displacement",
            ),
            _node(
                id="d",
                sequence_index=3,
                status="pending",
                chapter="Kinematics",
                concept_name="Velocity",
            ),
            _node(
                id="e",
                sequence_index=4,
                status="pending",
                chapter="Kinematics",
                concept_name="Acceleration",
            ),
            _node(
                id="f",
                sequence_index=5,
                status="pending",
                chapter="Optics",
                concept_name="Lenses",
            ),
        ]
        plan = compose_study_plan(nodes, subject="Physics", daily_goal_minutes=45)
        self.assertEqual(plan["today_node_id"], "c")
        self.assertEqual(plan["this_week"][0]["node_id"], "c")
        self.assertNotIn("a", {row["node_id"] for row in plan["this_week"]})
        later_chapters = {row["chapter"] for row in plan["later"]}
        self.assertIn("Optics", later_chapters)
        self.assertNotIn("Laws of Motion", later_chapters)

    def test_later_chapter_list_is_capped(self):
        nodes = [
            _node(id=str(i), sequence_index=i, status="pending", chapter=f"Ch{i}", concept_name=f"N{i}")
            for i in range(30)
        ]
        plan = compose_study_plan(nodes, daily_goal_minutes=45)
        self.assertLessEqual(len(plan["later"]), 14)
        self.assertGreater(plan["later_more"], 0)

    def test_completed_path_has_no_today(self):
        nodes = [_node(id="done", status="completed")]
        plan = compose_study_plan(nodes)
        self.assertIsNone(plan["today_node_id"])
        self.assertEqual(plan["this_week"], [])
        self.assertIn("complete", plan["headline"].lower())

    def test_revise_action_skips_full_theory(self):
        node = _node(id="r", node_type="REVISE", status="in_progress")
        plan = compose_study_plan([node])
        self.assertIn("Skip a full theory pass", plan["this_week"][0]["action"])


class PathConceptRowTests(SimpleTestCase):
    def test_live_extras_do_not_join_the_path(self):
        yaml_ids = set(syllabus_concept_map("Physics"))
        live = [
            {
                "concept_id": "newtons_1st_law",
                "concept_name": "Newton live",
                "chapter": "Wrong Chapter",
                "subject": "Physics",
            },
            {
                "concept_id": "openstax_not_in_jee",
                "concept_name": "Dump",
                "chapter": "Nuclear Physics",
                "subject": "Physics",
            },
        ]
        with mock.patch("roadmap.generator._read_live_concepts", return_value=live):
            rows = _path_concept_rows("Physics")
        ids = {row["concept_id"] for row in rows}
        self.assertEqual(ids, yaml_ids)
        newton = next(row for row in rows if row["concept_id"] == "newtons_1st_law")
        self.assertEqual(newton["concept_name"], "Newton live")
        self.assertEqual(newton["chapter"], "Laws of Motion")
