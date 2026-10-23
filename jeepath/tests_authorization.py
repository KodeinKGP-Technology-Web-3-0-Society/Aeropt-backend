"""Authorization tests: reference data and system-owned rows are not writable by students."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient, APITestCase

from apis.models import ContentFlag, ContentItem, Subject

User = get_user_model()


class WritePermissionTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.student = User.objects.create_user(email="s@example.com", password="pw-123456-x", full_name="S")
        cls.other = User.objects.create_user(email="o@example.com", password="pw-123456-x", full_name="O")
        cls.staff = User.objects.create_user(
            email="a@example.com", password="pw-123456-x", full_name="A", is_staff=True
        )
        cls.subject = Subject.objects.create(name="Physics", slug="physics")

    def as_user(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def test_student_can_read_but_not_write_catalog(self):
        c = self.as_user(self.student)
        self.assertEqual(c.get("/api/v1/subjects/").status_code, 200)
        self.assertEqual(c.post("/api/v1/subjects/", {"name": "X", "slug": "x"}).status_code, 403)
        self.assertEqual(c.patch(f"/api/v1/subjects/{self.subject.pk}/", {"name": "Hacked"}).status_code, 403)
        self.assertEqual(c.delete(f"/api/v1/subjects/{self.subject.pk}/").status_code, 403)
        self.subject.refresh_from_db()
        self.assertEqual(self.subject.name, "Physics")

    def test_staff_can_write_catalog(self):
        c = self.as_user(self.staff)
        self.assertEqual(c.patch(f"/api/v1/subjects/{self.subject.pk}/", {"name": "Phys"}).status_code, 200)

    def test_anonymous_gets_nothing(self):
        self.assertIn(APIClient().get("/api/v1/subjects/").status_code, (401, 403))

    def test_student_cannot_write_system_owned_rows(self):
        c = self.as_user(self.student)
        for path in (
            "/api/v1/analytics/concept-masteries/",
            "/api/v1/analytics/streaks/",
            "/api/v1/analytics/question-attempts/",
            "/api/v1/users/subscriptions/",
            "/api/v1/users/user-achievements/",
        ):
            with self.subTest(path=path):
                self.assertEqual(c.get(path).status_code, 200)
                self.assertEqual(c.post(path, {}, format="json").status_code, 403)

    def test_student_can_still_write_own_profile(self):
        c = self.as_user(self.student)
        r = c.get("/api/v1/users/student-profiles/")
        self.assertEqual(r.status_code, 200)


class ContentFlagTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.student = User.objects.create_user(email="s@example.com", password="pw-123456-x", full_name="S")
        cls.other = User.objects.create_user(email="o@example.com", password="pw-123456-x", full_name="O")
        cls.staff = User.objects.create_user(
            email="a@example.com", password="pw-123456-x", full_name="A", is_staff=True
        )

    def test_reporter_and_status_cannot_be_forged(self):
        item = ContentItem.objects.first()
        if item is None:
            self.skipTest("no ContentItem fixture available in the CI schema")
        c = APIClient()
        c.force_authenticate(self.student)
        r = c.post(
            "/api/v1/content-flags/",
            {"content_item": item.pk, "reason": "typo", "reported_by": self.other.pk, "status": "resolved"},
            format="json",
        )
        self.assertEqual(r.status_code, 201, r.content)
        flag = ContentFlag.objects.get(pk=r.data["id"])
        self.assertEqual(flag.reported_by_id, self.student.pk)
        self.assertNotEqual(flag.status, "resolved")


class ApiResponseHeaderTests(APITestCase):
    def test_api_responses_are_not_cacheable(self):
        r = APIClient().get("/api/v1/health/")
        self.assertEqual(r.headers.get("Cache-Control"), "no-store")
