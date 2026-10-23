"""Project middleware.

``RequestIDMiddleware`` is the correlation spine: it gives every request an id
(reusing an inbound ``X-Request-ID`` when the client supplies a sane one),
exposes it as ``request.request_id``, echoes it back on the response, binds it
to the logging context so *every* log line emitted while serving the request
carries it, and logs one access line per request.
"""

from __future__ import annotations

import logging
import re
import time
import uuid

from jeepath.logging_utils import reset_request_id, set_request_id

logger = logging.getLogger("jeepath.request")

REQUEST_ID_HEADER = "X-Request-ID"
_WSGI_KEY = "HTTP_X_REQUEST_ID"
_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")

# Endpoints a load balancer hammers: keep them out of the access log.
_QUIET_PATHS = frozenset({"/api/v1/health/"})


def _incoming_id(request) -> str:
    candidate = (request.META.get(_WSGI_KEY) or "").strip()
    if candidate and _SAFE_ID.match(candidate):
        return candidate
    return uuid.uuid4().hex


class RequestIDMiddleware:
    """Assign/propagate a request id and emit one access log line."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = _incoming_id(request)
        request.request_id = request_id
        token = set_request_id(request_id)
        started = time.monotonic()
        try:
            response = self.get_response(request)
        except Exception:
            # Django logs this traceback too, but from outside the middleware
            # chain, where the request id is already gone. Log a correlated copy.
            logger.exception(
                "%s %s raised after %.1fms",
                request.method,
                request.get_full_path(),
                (time.monotonic() - started) * 1000,
            )
            raise
        else:
            response[REQUEST_ID_HEADER] = request_id
            # Authenticated API payloads must never be kept by a shared cache or proxy.
            if request.path.startswith("/api/") and "Cache-Control" not in response:
                response["Cache-Control"] = "no-store"
            status_code = response.status_code
            # Django's own django.request lines for 4xx/5xx are emitted after this
            # middleware returns, so they cannot carry the id. This line can, and
            # is levelled by status so an operator greps the failures directly.
            if status_code >= 500:
                level = logging.ERROR
            elif status_code >= 400:
                level = logging.WARNING
            else:
                level = logging.INFO
            # Load-balancer probes are only worth a line when they fail.
            if request.path not in _QUIET_PATHS or status_code >= 400:
                duration_ms = (time.monotonic() - started) * 1000
                logger.log(
                    level,
                    "%s %s %s %.1fms",
                    request.method,
                    request.get_full_path(),
                    response.status_code,
                    duration_ms,
                    extra={
                        "method": request.method,
                        "path": request.path,
                        "status": response.status_code,
                        "duration_ms": round(duration_ms, 1),
                    },
                )
            return response
        finally:
            reset_request_id(token)
