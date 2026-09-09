"""
analytics/supabase_chat_history.py

Reads chat history from Supabase sessions + chat_turns.
The agent is the canonical writer; Django reads and serves.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

from django.utils import timezone

from users.supabase_sync import get_supabase_client, is_supabase_configured

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


def _parse_dt(raw: Any) -> Optional[datetime.datetime]:
    if not raw:
        return None
    try:
        return datetime.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


def build_chat_history_list(
    supabase_user_id: str,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    subject_filter: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Return a paginated list of sessions (no turn join).
    Each row has a summary, turn_count, and last_decision for the resume widget.
    """
    if not is_supabase_configured():
        return None
    client = get_supabase_client()
    if client is None:
        return None

    page_size = min(page_size, MAX_PAGE_SIZE)
    offset = (page - 1) * page_size

    try:
        query = (
            client.table("sessions")
            .select(
                "session_id,session_type,started_at,ended_at,duration_seconds,"
                "concepts_touched,session_summary,last_decision,interaction_count",
                count="exact",
            )
            .eq("user_id", supabase_user_id)
            .order("started_at", desc=True)
            .range(offset, offset + page_size - 1)
        )
        res = query.execute()
    except Exception:
        return None

    rows = res.data or []
    total = res.count or 0

    sessions = []
    for row in rows:
        touched = row.get("concepts_touched") or []
        # If subject filter provided, only include sessions that touched that subject.
        # (Full subject lookup would need a join — approximation via session_type for now)
        sessions.append({
            "session_id": row["session_id"],
            "session_type": row.get("session_type"),
            "started_at": row.get("started_at"),
            "ended_at": row.get("ended_at"),
            "duration_seconds": row.get("duration_seconds") or 0,
            "concepts_touched": touched,
            "summary": row.get("session_summary") or "",
            "last_decision": row.get("last_decision"),
            "turn_count": row.get("interaction_count") or 0,
        })

    return {
        "sessions": sessions,
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_next": offset + page_size < total,
    }


def build_chat_history_detail(
    supabase_user_id: str,
    session_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Return a single session with full turn-by-turn transcript.
    Verifies ownership via user_id match.
    """
    if not is_supabase_configured():
        return None
    client = get_supabase_client()
    if client is None:
        return None

    try:
        session_res = (
            client.table("sessions")
            .select(
                "session_id,user_id,session_type,started_at,ended_at,"
                "duration_seconds,session_summary,last_decision,interaction_count,concepts_touched"
            )
            .eq("session_id", session_id)
            .eq("user_id", supabase_user_id)
            .limit(1)
            .execute()
        )
    except Exception:
        return None

    if not session_res.data:
        return None  # not found or not owned by this user

    session = session_res.data[0]

    try:
        turns_res = (
            client.table("chat_turns")
            .select(
                "turn_id,role,content,turn_index,is_summarized,"
                "concepts_referenced,agent_used,created_at,decision,"
                "content_ids_served,presentation,student_feedback"
            )
            .eq("session_id", session_id)
            .order("turn_index", desc=False)
            .execute()
        )
        turns = turns_res.data or []
    except Exception:
        turns = []

    return {
        "session_id": session["session_id"],
        "session_type": session.get("session_type"),
        "started_at": session.get("started_at"),
        "ended_at": session.get("ended_at"),
        "duration_seconds": session.get("duration_seconds") or 0,
        "summary": session.get("session_summary") or "",
        "last_decision": session.get("last_decision"),
        "concepts_touched": session.get("concepts_touched") or [],
        "turns": [
            {
                "turn_id": t["turn_id"],
                "role": t.get("role"),
                "content": t.get("content", ""),
                "turn_index": t.get("turn_index"),
                "is_summarized": bool(t.get("is_summarized")),
                "concepts_referenced": t.get("concepts_referenced") or [],
                "agent_used": t.get("agent_used"),
                "created_at": t.get("created_at"),
                "decision": t.get("decision"),
                "content_ids_served": t.get("content_ids_served") or [],
                "presentation": t.get("presentation"),
                "student_feedback": t.get("student_feedback"),
            }
            for t in turns
        ],
    }
