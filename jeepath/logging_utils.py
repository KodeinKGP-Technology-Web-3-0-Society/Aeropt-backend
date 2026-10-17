"""Request-id aware logging support.

Two pieces, both referenced from ``jeepath.settings.LOGGING``:

* :class:`RequestIDFilter` — stamps every log record with the request id of the
  request being served (``-`` outside a request), so a ``X-Request-ID`` a user
  quotes from a frontend bug report maps straight onto backend log lines.
* :class:`JSONFormatter` — one JSON object per line for log aggregators.
  Selected with ``LOG_FORMAT=json``; the default is human-readable text.

The id lives in a :mod:`contextvars` ContextVar, so it is correct under WSGI
threads and under ASGI/async views without any thread-local juggling.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
from contextvars import ContextVar

NO_REQUEST_ID = "-"

_request_id: ContextVar[str] = ContextVar("jeepath_request_id", default=NO_REQUEST_ID)


def set_request_id(request_id: str):
    """Bind ``request_id`` to the current context; returns the reset token."""
    return _request_id.set(request_id or NO_REQUEST_ID)


def reset_request_id(token) -> None:
    """Undo a :func:`set_request_id` using its token."""
    try:
        _request_id.reset(token)
    except ValueError:
        # Different context (e.g. the response was streamed from elsewhere).
        _request_id.set(NO_REQUEST_ID)


def get_request_id() -> str:
    return _request_id.get()


class RequestIDFilter(logging.Filter):
    """Attach ``record.request_id`` so formatters can print it."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(record, "request_id", None):
            record.request_id = get_request_id()
        return True


_RESERVED = frozenset(
    vars(logging.LogRecord("", 0, "", 0, "", (), None)).keys()
) | {"asctime", "message", "request_id", "taskName"}


class JSONFormatter(logging.Formatter):
    """Single-line JSON records, including any ``extra=`` keys."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": _dt.datetime.fromtimestamp(
                record.created, tz=_dt.timezone.utc
            ).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", NO_REQUEST_ID),
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in _RESERVED or key.startswith("_"):
                continue
            try:
                json.dumps(value)
            except (TypeError, ValueError):
                value = repr(value)
            payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)
        return json.dumps(payload, default=str)
