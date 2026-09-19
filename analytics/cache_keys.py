"""Cache keys owned by `analytics`.

The shared helpers live in `apis/cache_layer.py` (`get_or_set`,
`dashboard_key`, `sandbox_queue_key`, …) and these follow the same
`prefix:user[:suffix]` shape. They are defined here rather than there only
because chat history is an analytics concern; use `apis.cache_layer.get_or_set`
with them exactly as the dashboard/progress views do.
"""

from __future__ import annotations

# TTLs (seconds). Chat history changes every turn, so both are deliberately
# short — just enough to absorb a page's duplicate mounts.
TTL_CHAT_HISTORY = 20
TTL_CHAT_HISTORY_DETAIL = 30


def _uid(user) -> str:
    return str(getattr(user, "id", user))


def chat_history_key(user, page: int, page_size: int, subject: str = "") -> str:
    return f"chat:hist:{_uid(user)}:{page}:{page_size}:{subject or 'all'}"


def chat_history_detail_key(user, session_id: str) -> str:
    return f"chat:hist:{_uid(user)}:s:{session_id}"
