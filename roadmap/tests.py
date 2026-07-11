from django.test import TestCase

from roadmap.generator import topological_sort
from roadmap.syllabus import prerequisite_map, syllabus_concept_map


class RoadmapGeneratorTests(TestCase):
    def test_syllabus_has_at_least_20_concepts(self):
        concepts = syllabus_concept_map()
        self.assertGreaterEqual(len(concepts), 20)

    def test_topological_sort_respects_prerequisites(self):
        concept_ids = list(syllabus_concept_map().keys())
        prereqs = prerequisite_map()
        ordered = topological_sort(concept_ids, prereqs)
        positions = {cid: idx for idx, cid in enumerate(ordered)}
        for cid, deps in prereqs.items():
            if cid not in positions:
                continue
            for dep in deps:
                if dep in positions:
                    self.assertLess(positions[dep], positions[cid])
