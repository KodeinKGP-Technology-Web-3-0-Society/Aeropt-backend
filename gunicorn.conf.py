"""Gunicorn configuration for the Prepwise Django API.

Used by the Dockerfile CMD; also works locally:
    gunicorn -c gunicorn.conf.py prepwise.wsgi:application
"""

import multiprocessing
import os

bind = os.getenv("GUNICORN_BIND", f"0.0.0.0:{os.getenv('PORT', '8000')}")

# 2 * cpu + 1 is the standard starting point, capped at 9: cpu_count() reports the
# host's cores, not the container's cpu limit, so on a big host an uncapped default
# would fork dozens of workers into a 1-cpu container. Raise it with WEB_CONCURRENCY
# when the container really has the cores.
_WORKER_CAP = int(os.getenv("GUNICORN_WORKER_CAP", "9"))
workers = int(
    os.getenv("WEB_CONCURRENCY", str(min(multiprocessing.cpu_count() * 2 + 1, _WORKER_CAP)))
)
threads = int(os.getenv("GUNICORN_THREADS", "2"))
worker_class = os.getenv("GUNICORN_WORKER_CLASS", "sync")

# Requests are short API calls; anything past 30s is a stuck worker.
timeout = int(os.getenv("GUNICORN_TIMEOUT", "30"))
graceful_timeout = int(os.getenv("GUNICORN_GRACEFUL_TIMEOUT", "30"))
keepalive = int(os.getenv("GUNICORN_KEEPALIVE", "5"))

# Recycle workers to bound any slow leak; jitter avoids a synchronised restart.
max_requests = int(os.getenv("GUNICORN_MAX_REQUESTS", "1000"))
max_requests_jitter = int(os.getenv("GUNICORN_MAX_REQUESTS_JITTER", "100"))

# Django's LOGGING owns application logs; gunicorn only reports its own lifecycle
# and access lines. Access logging is off by default because
# prepwise.middleware.RequestIDMiddleware already logs one correlated line per
# request; set GUNICORN_ACCESS_LOG=- to turn gunicorn's own back on.
accesslog = os.getenv("GUNICORN_ACCESS_LOG") or None
access_log_format = '%(h)s "%(r)s" %(s)s %(b)s %(M)sms "%({x-request-id}o)s"'
errorlog = "-"
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")

# Trust the container's reverse proxy for X-Forwarded-*.
forwarded_allow_ips = os.getenv("GUNICORN_FORWARDED_ALLOW_IPS", "*")

# Faster worker boot and shared memory pages; safe here because nothing opens a
# database connection at import time.
preload_app = os.getenv("GUNICORN_PRELOAD", "true").strip().lower() in ("1", "true", "yes", "on")
