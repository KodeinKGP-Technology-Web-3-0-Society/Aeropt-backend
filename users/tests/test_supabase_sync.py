from django.test import SimpleTestCase

from users.supabase_sync import _upsert_user_concept_states


class _Result:
    def execute(self):
        return self


class _Table:
    def __init__(self, calls):
        self.calls = calls

    def upsert(self, rows, on_conflict=""):
        self.calls.append(("upsert", on_conflict, rows))
        return _Result()

    def update(self, *_args, **_kwargs):
        raise AssertionError("placement re-seed must not update one concept at a time")

    def insert(self, *_args, **_kwargs):
        raise AssertionError("placement re-seed must not insert separately from the upsert")


class _Client:
    def __init__(self):
        self.calls = []

    def table(self, name):
        self.calls.append(("table", name))
        return _Table(self.calls)


class UpsertUserConceptStatesTests(SimpleTestCase):
    def test_reseed_is_one_upsert(self):
        client = _Client()
        rows = [
            {"user_id": "u", "concept_id": f"c{i}", "proficiency_score": 0.5}
            for i in range(133)
        ]
        _upsert_user_concept_states(client, rows)
        upserts = [call for call in client.calls if call[0] == "upsert"]
        self.assertEqual(len(upserts), 1)
        _kind, conflict, sent = upserts[0]
        self.assertEqual(conflict, "user_id,concept_id")
        self.assertEqual(len(sent), 133)

    def test_empty_reseed_does_not_call_supabase(self):
        client = _Client()
        _upsert_user_concept_states(client, [])
        self.assertEqual(client.calls, [])
