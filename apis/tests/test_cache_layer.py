from django.core.cache import cache
from django.test import SimpleTestCase

from apis.cache_layer import classroom_home_key, get_or_set, invalidate_user_reads, roadmap_key


class FakeUser:
    id = "user-1"


class CacheLayerTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_get_or_set_caches_producer(self):
        calls = {"n": 0}

        def produce():
            calls["n"] += 1
            return {"ok": True}

        first = get_or_set("k1", 60, produce)
        second = get_or_set("k1", 60, produce)
        self.assertEqual(first, {"ok": True})
        self.assertEqual(second, {"ok": True})
        self.assertEqual(calls["n"], 1)

    def test_invalidate_user_reads_clears_roadmap(self):
        user = FakeUser()
        cache.set(roadmap_key(user), {"nodes": []}, 60)
        cache.set(classroom_home_key(user), {"today": None}, 60)
        invalidate_user_reads(user)
        self.assertIsNone(cache.get(roadmap_key(user)))
        self.assertIsNone(cache.get(classroom_home_key(user)))
