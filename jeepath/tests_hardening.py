"""Tests for the production-hardening layer: request ids, logging correlation,
throttling, health-check depth and the TLS-gated security settings.

Throttle rates are disabled in ``jeepath.ci_settings`` (the suite would trip
them), so the throttling test patches ``SimpleRateThrottle.THROTTLE_RATES``
directly — DRF caches that dict on the class at import time, so
``override_settings`` alone would not take effect.
"""

from __future__ import annotations

import logging
from unittest import mock

from django.conf import settings
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from rest_framework.throttling import SimpleRateThrottle

from jeepath.logging_utils import (
    NO_REQUEST_ID,
    JSONFormatter,
    RequestIDFilter,
    get_request_id,
    reset_request_id,
    set_request_id,
)
from jeepath.middleware import REQUEST_ID_HEADER
from jeepath.throttling import AuthBurstRateThrottle


class RequestIDMiddlewareTests(TestCase):
    def test_response_carries_a_generated_request_id(self):
        response = self.client.get(reverse("health-check"))
        request_id = response.headers.get(REQUEST_ID_HEADER)
        self.assertTrue(request_id)
        self.assertEqual(len(request_id), 32)
        # The view sees the same id the caller gets back.
        self.assertEqual(response.data["request_id"], request_id)

    def test_inbound_request_id_is_reused(self):
        response = self.client.get(
            reverse("health-check"), headers={"x-request-id": "frontend-abc-123"}
        )
        self.assertEqual(response.headers[REQUEST_ID_HEADER], "frontend-abc-123")

    def test_hostile_inbound_request_id_is_replaced(self):
        for bad in ("short", "x" * 200, "has spaces and \n newline", "semi;colon"):
            with self.subTest(bad=bad):
                response = self.client.get(
                    reverse("health-check"), headers={"x-request-id": bad}
                )
                self.assertNotEqual(response.headers[REQUEST_ID_HEADER], bad)
                self.assertEqual(len(response.headers[REQUEST_ID_HEADER]), 32)

    def test_context_is_cleared_after_the_request(self):
        self.client.get(reverse("health-check"))
        self.assertEqual(get_request_id(), NO_REQUEST_ID)


class LoggingCorrelationTests(TestCase):
    def test_log_lines_emitted_during_a_request_carry_its_id(self):
        records: list[logging.LogRecord] = []

        class Capture(logging.Handler):
            def emit(self, record):
                records.append(record)

        handler = Capture(level=logging.INFO)
        handler.addFilter(RequestIDFilter())
        access_logger = logging.getLogger("jeepath.request")
        previous_level = access_logger.level
        access_logger.addHandler(handler)
        access_logger.setLevel(logging.INFO)
        try:
            # /health/ is deliberately not access-logged; use another endpoint.
            response = self.client.get("/api/v1/subjects/")
        finally:
            access_logger.removeHandler(handler)
            access_logger.setLevel(previous_level)

        request_id = response.headers[REQUEST_ID_HEADER]
        self.assertTrue(records, "expected an access log record")
        record = records[-1]
        self.assertEqual(record.request_id, request_id)
        # A 4xx access line is levelled up so failures are greppable.
        self.assertEqual(record.levelno, logging.WARNING)
        self.assertEqual(record.status, response.status_code)
        formatted = logging.Formatter(
            settings.LOGGING["formatters"]["plain"]["format"]
        ).format(record)
        self.assertIn(request_id, formatted)

    def test_filter_defaults_outside_a_request(self):
        record = logging.LogRecord("t", logging.INFO, __file__, 1, "hello", (), None)
        self.assertTrue(RequestIDFilter().filter(record))
        self.assertEqual(record.request_id, NO_REQUEST_ID)

    def test_json_formatter_includes_request_id_and_extras(self):
        token = set_request_id("abcdef123456")
        try:
            record = logging.LogRecord("t", logging.WARNING, __file__, 1, "oops", (), None)
            record.status = 503
            RequestIDFilter().filter(record)
            line = JSONFormatter().format(record)
        finally:
            reset_request_id(token)
        self.assertIn('"request_id": "abcdef123456"', line)
        self.assertIn('"status": 503', line)
        self.assertIn('"message": "oops"', line)


class ThrottleTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def test_auth_endpoint_burst_returns_429(self):
        url = reverse("auth:token-obtain")
        rates = {"auth": "3/min", "anon": None, "user": None}
        with mock.patch.object(SimpleRateThrottle, "THROTTLE_RATES", rates):
            statuses = [
                self.client.post(url, {"email": "nobody@example.com", "password": "x"}).status_code
                for _ in range(4)
            ]
        self.assertNotIn(429, statuses[:3])
        self.assertEqual(statuses[3], 429)

    def test_non_auth_paths_are_not_touched_by_the_auth_throttle(self):
        rates = {"auth": "1/min", "anon": None, "user": None}
        with mock.patch.object(SimpleRateThrottle, "THROTTLE_RATES", rates):
            for _ in range(5):
                response = self.client.get("/api/v1/subjects/")
                self.assertNotEqual(response.status_code, 429)

    def test_health_check_is_never_throttled(self):
        rates = {"auth": "1/min", "anon": "1/min", "user": "1/min"}
        with mock.patch.object(SimpleRateThrottle, "THROTTLE_RATES", rates):
            for _ in range(5):
                self.assertEqual(self.client.get(reverse("health-check")).status_code, 200)

    def test_auth_throttle_scope_matching(self):
        from django.test import RequestFactory

        factory = RequestFactory()
        rates = {"auth": "1/min", "anon": None, "user": None}
        with mock.patch.object(SimpleRateThrottle, "THROTTLE_RATES", rates):
            # Non-credential path: short-circuits to allowed, twice over.
            for _ in range(2):
                self.assertTrue(
                    AuthBurstRateThrottle().allow_request(
                        factory.get("/api/v1/analytics/dashboard/"), None
                    )
                )
            # Credential path: second request from the same IP is blocked.
            request = factory.post("/api/v1/auth/register/")
            self.assertTrue(AuthBurstRateThrottle().allow_request(request, None))
            self.assertFalse(AuthBurstRateThrottle().allow_request(request, None))

    def test_default_throttle_classes_are_configured(self):
        classes = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"]
        self.assertIn("jeepath.throttling.AuthBurstRateThrottle", classes)
        self.assertIn("rest_framework.throttling.AnonRateThrottle", classes)
        self.assertIn("rest_framework.throttling.UserRateThrottle", classes)


class HealthCheckTests(TestCase):
    def test_happy_path_reports_dependencies(self):
        response = self.client.get(reverse("health-check"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "ok")
        self.assertEqual(response.data["checks"]["database"]["status"], "ok")
        # ci_settings blanks the Supabase credentials on purpose.
        self.assertEqual(response.data["checks"]["supabase"]["status"], "unconfigured")

    def test_supabase_reported_configured_without_a_live_call(self):
        with self.settings(SUPABASE_URL="https://x.supabase.co", SUPABASE_KEY="k"):
            response = self.client.get(reverse("health-check"))
        self.assertEqual(response.data["checks"]["supabase"]["status"], "configured")

    def test_database_failure_returns_503(self):
        from apis import views as apis_views

        with mock.patch.object(
            apis_views.HealthCheckView, "_check_database", return_value=(False, "OperationalError")
        ):
            response = self.client.get(reverse("health-check"))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["status"], "degraded")
        self.assertEqual(response.data["checks"]["database"]["status"], "error")


class SecuritySettingsTests(SimpleTestCase):
    def test_tls_settings_follow_the_behind_tls_flag(self):
        behind_tls = settings.BEHIND_TLS
        self.assertEqual(settings.SECURE_SSL_REDIRECT, behind_tls)
        self.assertEqual(settings.SESSION_COOKIE_SECURE, behind_tls)
        self.assertEqual(settings.CSRF_COOKIE_SECURE, behind_tls)
        if behind_tls:
            self.assertGreaterEqual(settings.SECURE_HSTS_SECONDS, 31536000)
        else:
            self.assertEqual(settings.SECURE_HSTS_SECONDS, 0)

    def test_tls_independent_headers_are_always_on(self):
        self.assertTrue(settings.SECURE_CONTENT_TYPE_NOSNIFF)
        self.assertEqual(settings.X_FRAME_OPTIONS, "DENY")
        self.assertTrue(settings.SESSION_COOKIE_HTTPONLY)

    def test_cors_is_never_wide_open(self):
        self.assertFalse(getattr(settings, "CORS_ALLOW_ALL_ORIGINS", False))
        self.assertTrue(settings.CORS_ALLOWED_ORIGINS)

    def test_request_id_middleware_runs_first(self):
        self.assertEqual(settings.MIDDLEWARE[0], "jeepath.middleware.RequestIDMiddleware")
