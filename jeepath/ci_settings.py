"""Isolated Django settings for local/GitHub CI.

Never points at live Supabase. Import this via DJANGO_SETTINGS_MODULE, not
by running the app — local CD uses jeepath.settings and the real .env.
"""

import os

os.environ.setdefault("SECRET_KEY", "ci-only-not-for-production")
os.environ.setdefault("DEBUG", "True")
os.environ.setdefault("ALLOWED_HOSTS", "localhost,127.0.0.1")
os.environ.setdefault("DB_PASSWORD", "ci")
os.environ.setdefault("DB_HOST", "127.0.0.1")
os.environ.setdefault("DB_SSLMODE", "disable")
# Never talk to live Supabase or live agent from CI, even if Aeropt-backend/.env exists.
os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_KEY"] = ""
os.environ["AGENT_API_BASE_URL"] = ""

from jeepath.settings import *  # noqa: E402,F401

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(BASE_DIR / ".ci.sqlite3"),
    }
}

SUPABASE_URL = ""
SUPABASE_KEY = ""
AGENT_API_BASE_URL = ""

# CI relaxes two production policies, unless CI_HARDENING_LIVE=1. Set that flag
# to run a throwaway sqlite server with the real logging/throttling policy:
#   CI_HARDENING_LIVE=1 DJANGO_SETTINGS_MODULE=jeepath.ci_settings \
#       python manage.py runserver 8011 --noreload
if os.getenv("CI_HARDENING_LIVE", "").strip().lower() not in ("1", "true", "yes", "on"):
    # Throttling off: the suite fires hundreds of requests from one IP and a
    # handful of users within seconds, which is exactly what the limits exist to
    # stop. jeepath/tests_hardening.py re-enables them per test, so the policy
    # itself is still covered.
    REST_FRAMEWORK = {
        **REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": {"auth": None, "anon": None, "user": None},
    }

    # Keep CI output readable: no per-request access lines.
    LOGGING = {
        **LOGGING,
        "root": {**LOGGING["root"], "level": "WARNING"},
        "loggers": {
            name: {**cfg, "level": "WARNING"} for name, cfg in LOGGING["loggers"].items()
        },
    }
