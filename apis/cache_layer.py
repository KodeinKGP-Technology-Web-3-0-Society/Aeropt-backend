"""In-process response cache (LocMem) — no Redis required.

Use for expensive read endpoints that hit Supabase or rebuild large payloads.
Invalidate per-user on mutations that change proficiency / roadmap / sandbox.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from django.core.cache import cache

# TTLs (seconds)
TTL_DASHBOARD = 90
TTL_PROGRESS = 180
TTL_ROADMAP = 60
TTL_SANDBOX_QUEUE = 30
TTL_CHAPTERS = 600  # syllabus metadata changes rarely


def _uid(user) -> str:
    return str(getattr(user, "id", user))


def dashboard_key(user) -> str:
    return f"dash:{_uid(user)}"


def progress_key(user) -> str:
    return f"prog:{_uid(user)}"


def roadmap_key(user) -> str:
    return f"roadmap:{_uid(user)}"


def sandbox_queue_key(user) -> str:
    return f"sandbox:q:{_uid(user)}"


def chapters_key() -> str:
    return "onboarding:chapters:v1"


def get_or_set(key: str, ttl: int, producer: Callable[[], Any]) -> Any:
    cached = cache.get(key)
    if cached is not None:
        return cached
    value = producer()
    if value is not None:
        cache.set(key, value, ttl)
    return value


def invalidate_user_reads(user) -> None:
    """Drop per-user read caches after proficiency / path / onboarding changes."""
    if user is None:
        return
    cache.delete_many(
        [
            dashboard_key(user),
            progress_key(user),
            roadmap_key(user),
            sandbox_queue_key(user),
        ]
    )


def invalidate_roadmap(user) -> None:
    if user is None:
        return
    cache.delete_many([roadmap_key(user), sandbox_queue_key(user)])
