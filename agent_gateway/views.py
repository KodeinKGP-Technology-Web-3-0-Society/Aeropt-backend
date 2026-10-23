"""The browser's only door to the tutor agent.

`/api/v1/agent/<path>` is forwarded to the agent's `/api/v1/<path>`. Django authenticates
the caller (SimpleJWT, same as every other route), checks the route against an allowlist,
pins the learner's identity into the request, and streams the agent's reply back, so the
agent itself can sit on a private port that only Django reaches.

Identity: the agent knows learners by `supabase_user_id`. Any `user_id` the browser names
(path, query string or JSON body) must equal the caller's, and is overwritten with it. The
caller's own bearer token is forwarded too, so an agent that verifies tokens still does.

Server-to-server routes (classroom specialists, coach, admin traces) are not on the
allowlist: Django calls those itself with `AGENT_SERVICE_TOKEN` (`classroom/agent_client.py`).
"""

from __future__ import annotations

import json
import logging
import re
import threading
from typing import Iterator, Optional
from urllib.parse import parse_qsl, urlencode

import httpx
from django.conf import settings
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView

logger = logging.getLogger("agent_gateway")

_UID = r"[^/]+"
_ID = r"[A-Za-z0-9_.:-]+"

# (methods, path under /api/v1/) the browser may reach. Anything else is a 404 here.
_ROUTES = [
    ({"POST"}, r"chat/message"),
    ({"POST"}, r"chat/end-session"),
    ({"GET", "POST"}, r"chat/sessions"),
    ({"GET", "PATCH", "DELETE"}, rf"chat/sessions/{_ID}"),
    ({"POST"}, r"onboarding/diagnostic"),
    ({"POST"}, r"study/(?:start|message|stop|answer|next|advance)"),
    ({"GET"}, rf"study/session/{_ID}"),
    ({"GET"}, rf"study/(?:overview|history)/(?P<uid>{_UID})"),
    ({"GET"}, rf"concepts/{_ID}/(?:pyqs|proficiency)"),
    ({"POST"}, r"classroom/assess/(?:build|grade)"),
    ({"GET"}, rf"progress/(?P<uid>{_UID})"),
    ({"PUT"}, r"plan/settings"),
    ({"GET"}, rf"plan/(?P<uid>{_UID})"),
    ({"POST"}, r"voice/(?:transcribe|synthesize)"),
]
# Content-addressed or static, no learner data: no sign-in needed (an <img> sends no token).
_PUBLIC_ROUTES = [
    ({"GET"}, r"diagrams/[0-9a-f]{20}\.svg"),
    ({"GET"}, r"voice/speakers"),
]
_COMPILED = [(m, re.compile(rf"^{p}$"), False) for m, p in _ROUTES] + [
    (m, re.compile(rf"^{p}$"), True) for m, p in _PUBLIC_ROUTES
]

# Request headers worth passing on; everything else (cookies, host, hop-by-hop) stays here.
_FORWARD_REQUEST = ("content-type", "accept", "accept-language", "authorization")
# Response headers worth passing back.
_FORWARD_RESPONSE = ("content-type", "cache-control", "retry-after", "content-disposition", "etag", "last-modified")

_client: Optional[httpx.Client] = None
_client_lock = threading.Lock()


def _agent_client() -> httpx.Client:
    """One pooled client per process: keep-alive connections to the agent instead of a
    TCP handshake per request."""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = httpx.Client(
                    timeout=httpx.Timeout(
                        connect=settings.AGENT_CONNECT_TIMEOUT,
                        read=settings.AGENT_READ_TIMEOUT,
                        write=30.0,
                        pool=10.0,
                    ),
                    limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
                    follow_redirects=False,
                )
    return _client


def match_route(method: str, path: str):
    """Return (match, public) for an allowed route, else None."""
    for methods, pattern, public in _COMPILED:
        m = pattern.match(path)
        if m and method in methods:
            return m, public
    return None


def _error(status: int, detail: str) -> JsonResponse:
    return JsonResponse({"detail": detail}, status=status)


class AgentGatewayView(APIView):
    # Content negotiation and parsing are the agent's job; Django only relays bytes.
    parser_classes: list = []

    def get_permissions(self):
        found = match_route(self.request.method, self._path())
        if found and found[1]:
            return [AllowAny()]
        return [IsAuthenticated()]

    def get_authenticators(self):
        # A public route must not 401 on a stale token in the header.
        found = match_route(self.request.method, self._path())
        if found and found[1]:
            return []
        return super().get_authenticators()

    def _path(self) -> str:
        return (self.kwargs.get("path") or "").strip("/")

    def get(self, request, path):
        return self._forward(request)

    def post(self, request, path):
        return self._forward(request)

    def put(self, request, path):
        return self._forward(request)

    def patch(self, request, path):
        return self._forward(request)

    def delete(self, request, path):
        return self._forward(request)

    def _forward(self, request):
        base = (settings.AGENT_API_BASE_URL or "").rstrip("/")
        if not base:
            return _error(503, "The tutor is not configured on this server.")
        path = self._path()
        found = match_route(request.method, path)
        if not found:
            return _error(404, "Not found.")
        match, public = found

        uid = None
        if not public:
            uid = str(getattr(request.user, "supabase_user_id", "") or "")
            if not uid:
                return _error(409, "Your account is still being set up. Please sign in again.")
            named = match.groupdict().get("uid")
            if named and named != uid:
                return _error(403, "That belongs to another account.")

        pairs = parse_qsl(request.META.get("QUERY_STRING", ""), keep_blank_values=True)
        body = request.body
        if uid:
            if any(k == "user_id" and v and v != uid for k, v in pairs):
                return _error(403, "That belongs to another account.")
            pairs = [(k, v) for k, v in pairs if k != "user_id"] + [("user_id", uid)]
            if request.method in ("POST", "PUT", "PATCH", "DELETE"):
                body, problem = _pin_body(body, request.content_type, uid)
                if problem:
                    return problem

        headers = {k: request.headers[k] for k in _FORWARD_REQUEST if k in request.headers}
        headers["Accept-Encoding"] = "identity"  # bytes are relayed as-is, so no compression to undo
        headers["X-Request-ID"] = getattr(request, "request_id", "") or ""
        headers["X-Forwarded-For"] = request.META.get("REMOTE_ADDR", "")
        url = f"{base}/api/v1/{path}"
        if pairs:
            url += "?" + urlencode(pairs)

        client = _agent_client()
        try:
            upstream = client.send(
                client.build_request(request.method, url, headers=headers, content=body or None),
                stream=True,
            )
        except httpx.TimeoutException:
            logger.warning("agent timed out: %s %s", request.method, path)
            return _error(504, "The tutor took too long to answer. Please try again.")
        except httpx.HTTPError as exc:
            logger.warning("agent unreachable: %s %s: %s", request.method, path, exc)
            return _error(502, "The tutor is unavailable right now. Please try again shortly.")

        if upstream.headers.get("content-type", "").startswith("text/event-stream"):
            response = StreamingHttpResponse(_relay(upstream), status=upstream.status_code)
            response["X-Accel-Buffering"] = "no"  # nginx and friends must not hold SSE back
        else:
            try:
                content = upstream.read()
            except httpx.HTTPError as exc:
                logger.warning("agent reply cut off: %s %s: %s", request.method, path, exc)
                return _error(502, "The tutor's reply was cut off. Please try again.")
            finally:
                upstream.close()
            response = HttpResponse(content, status=upstream.status_code)
        for name in _FORWARD_RESPONSE:
            if name in upstream.headers:
                response[name] = upstream.headers[name]
        return response


def _pin_body(body: bytes, content_type: str, uid: str):
    """Pin `user_id` in a JSON object body. Other bodies (audio uploads) pass unchanged."""
    if not body.strip() or (content_type or "").split(";")[0].strip().lower() != "application/json":
        return body, None
    try:
        data = json.loads(body)
    except ValueError:
        return body, _error(400, "That request was not valid JSON.")
    if not isinstance(data, dict):
        return body, None
    named = data.get("user_id")
    if named not in (None, "") and str(named) != uid:
        return body, _error(403, "That belongs to another account.")
    data["user_id"] = uid
    return json.dumps(data).encode("utf-8"), None


def _relay(upstream: httpx.Response) -> Iterator[bytes]:
    """Pass SSE bytes through as they arrive; always release the connection."""
    try:
        for chunk in upstream.iter_bytes():
            if chunk:
                yield chunk
    except httpx.HTTPError as exc:
        logger.warning("agent stream ended early: %s", exc)
    finally:
        upstream.close()
