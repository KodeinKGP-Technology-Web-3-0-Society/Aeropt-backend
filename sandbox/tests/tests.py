from django.test import SimpleTestCase, TestCase

from sandbox.orchestrator import _pack_queue_to_goal, build_queue_meta
from users.models import StudentProfile, User


class PackQueueTests(SimpleTestCase):
    def test_packs_toward_capped_daily_goal(self):
        queue = [
            {
                "id": "focus-1",
                "action": "LEARN",
                "concept_id": "torque",
                "concept_name": "Torque",
                "duration_min": 20,
                "priority": 1,
            },
            {
                "id": "next-2",
                "action": "LEARN",
                "concept_id": "angular_momentum",
                "concept_name": "Angular Momentum",
                "duration_min": 12,
                "priority": 2,
            },
        ]
        packed = _pack_queue_to_goal(queue, daily_goal=30)
        total = sum(int(item["duration_min"]) for item in packed)
        self.assertLessEqual(total, 30)
        self.assertGreaterEqual(total, 15)

    def test_adds_practice_slice_when_budget_allows(self):
        queue = [
            {
                "id": "focus-1",
                "action": "LEARN",
                "concept_id": "torque",
                "concept_name": "Torque",
                "chapter": "Rotational Motion",
                "roadmap_node_id": "n1",
                "duration_min": 10,
                "priority": 1,
            }
        ]
        packed = _pack_queue_to_goal(queue, daily_goal=45)
        self.assertTrue(any(item["id"] == "practice-slice" for item in packed))

    def test_high_daily_goal_caps_at_sixty(self):
        queue = [
            {
                "id": "focus-1",
                "action": "LEARN",
                "concept_id": "torque",
                "concept_name": "Torque",
                "duration_min": 20,
                "priority": 1,
            }
        ]
        packed = _pack_queue_to_goal(queue, daily_goal=120)
        total = sum(int(item["duration_min"]) for item in packed)
        self.assertLessEqual(total, 60)


class QueueMetaTests(TestCase):
    def test_build_queue_meta_reads_profile(self):
        user = User.objects.create_user(
            email="queue@example.com",
            password="testpass123",
            full_name="Queue Student",
        )
        profile = StudentProfile.objects.get(user=user)
        profile.daily_goal_minutes = 75
        profile.preferred_depth = "quick"
        profile.save(update_fields=["daily_goal_minutes", "preferred_depth"])
        user.student_profile.refresh_from_db()

        meta = build_queue_meta(user)
        self.assertEqual(meta["daily_goal_minutes"], 75)
        self.assertEqual(meta["preferred_depth"], "quick")
        self.assertEqual(meta["queue_target_minutes"], 60)
