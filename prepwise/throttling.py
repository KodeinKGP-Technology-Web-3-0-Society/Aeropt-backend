"""Project throttle classes.

The only unauthenticated endpoints are the credential endpoints
(``/api/v1/auth/register/``, ``/auth/token/``, ``/auth/token/refresh/``), the
health check and the OpenAPI schema/Swagger pages. Everything else requires a
JWT, so a per-user rate plus a per-IP anonymous rate covers the whole API.

:class:`AuthBurstRateThrottle` adds a much tighter per-IP limit on the
credential endpoints only. It is applied globally (via
``DEFAULT_THROTTLE_CLASSES``) rather than per view, because the auth views live
in ``users/`` and this keeps the policy in one auditable place.
"""

from __future__ import annotations

from rest_framework.throttling import AnonRateThrottle

# Suffix-matched so the ``/api/v1`` prefix can move without breaking this.
AUTH_PATH_SUFFIXES = (
    "/auth/register/",
    "/auth/token/",
    "/auth/token/refresh/",
)


class AuthBurstRateThrottle(AnonRateThrottle):
    """Per-IP burst limit on credential endpoints; a no-op everywhere else.

    Unlike :class:`AnonRateThrottle` this also throttles *authenticated*
    callers, because ``token/refresh/`` is hit with a valid refresh token and a
    credential-stuffing loop should not be able to dodge the limit by holding
    one.
    """

    scope = "auth"

    def allow_request(self, request, view):
        path = request.path or ""
        if not path.endswith(AUTH_PATH_SUFFIXES):
            return True
        return super().allow_request(request, view)

    def get_cache_key(self, request, view):
        ident = self.get_ident(request)
        if not ident:
            return None
        return self.cache_format % {"scope": self.scope, "ident": ident}
