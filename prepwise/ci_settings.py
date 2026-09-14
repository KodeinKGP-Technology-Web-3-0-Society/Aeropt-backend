"""Isolated Django settings for local/GitHub CI.

Never points at live Supabase. Import this via DJANGO_SETTINGS_MODULE, not
by running the app — local CD uses prepwise.settings and the real .env.
"""

import os

os.environ.setdefault("SECRET_KEY", "ci-only-not-for-production")
os.environ.setdefault("DEBUG", "True")
os.environ.setdefault("ALLOWED_HOSTS", "localhost,127.0.0.1")
os.environ.setdefault("DB_PASSWORD", "ci")
os.environ.setdefault("DB_HOST", "127.0.0.1")
os.environ.setdefault("DB_SSLMODE", "disable")
# Never talk to live Supabase from CI, even if Aeropt-backend/.env exists.
os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_KEY"] = ""

from prepwise.settings import *  # noqa: E402,F401

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(BASE_DIR / ".ci.sqlite3"),
    }
}

SUPABASE_URL = ""
SUPABASE_KEY = ""
