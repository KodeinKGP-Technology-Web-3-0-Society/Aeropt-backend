"""
Bridge Django users to the agent's Supabase `users` + `user_concept_state` tables.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from django.conf import settings

logger = logging.getLogger(__name__)

_client = None


def get_supabase_client():
    global _client
    if _client is not None:
        return _client

    url = getattr(settings, "SUPABASE_URL", "")
    key = getattr(settings, "SUPABASE_KEY", "")
    if not url or not key:
        return None

    from supabase import create_client

    _client = create_client(url, key)
    return _client


def is_supabase_configured() -> bool:
    return bool(getattr(settings, "SUPABASE_URL", "") and getattr(settings, "SUPABASE_KEY", ""))


def _supabase_target_exam(user) -> str:
    """
    Supabase `users.target_exam` only allows JEE_MAINS / JEE_ADVANCED.
    Django StudentProfile may use BOTH — map that to JEE_ADVANCED.
    """
    profile = getattr(user, "student_profile", None)
    raw = getattr(profile, "target_exam", None) if profile else None
    if raw in ("JEE_MAINS", "JEE_ADVANCED"):
        return raw
    return "JEE_ADVANCED"


def _read_concepts(client) -> List[Dict[str, Any]]:
    res = client.table("concepts").select("concept_id, concept_name, chapter, subject").execute()
    return res.data or []


def _batch_create_user_concept_states(client, user_id: str, concepts: List[Dict[str, Any]]) -> None:
    if not concepts:
        return
    rows = [
        {
            "user_id": user_id,
            "concept_id": concept["concept_id"],
            "subject": concept.get("subject", "Physics"),
            "chapter": concept.get("chapter"),
            "proficiency_score": 0.5,
            "attempts": 0,
            "correct": 0,
            "flagged_weak": False,
            "struggle_streak": 0,
            "error_type_dist": {
                "conceptual": 0,
                "procedural": 0,
                "calculation": 0,
                "misread": 0,
            },
            "avg_time_seconds": 0.0,
            "is_cold_start": True,
        }
        for concept in concepts
    ]
    client.table("user_concept_state").insert(rows).execute()


def ensure_supabase_user(user) -> Optional[str]:
    """
    Return the linked Supabase user_id for a Django user, creating/linking as needed.
    """
    if not is_supabase_configured():
        return None

    if user.supabase_user_id:
        return str(user.supabase_user_id)

    client = get_supabase_client()
    if client is None:
        return None

    email = (user.email or "").strip().lower()
    if email:
        existing = (
            client.table("users")
            .select("user_id")
            .eq("email", email)
            .limit(1)
            .execute()
        )
        if existing.data:
            supabase_id = existing.data[0]["user_id"]
            user.supabase_user_id = supabase_id
            user.save(update_fields=["supabase_user_id"])
            return str(supabase_id)

    supabase_id = str(user.id)
    name = user.full_name or (email.split("@")[0] if email else "Student")
    row = {
        "user_id": supabase_id,
        "name": name,
        "email": user.email,
        "target_exam": _supabase_target_exam(user),
        "preferred_depth": "standard",
    }

    try:
        client.table("users").insert(row).execute()
    except Exception:
        # Race or duplicate — re-fetch by email or id
        lookup = (
            client.table("users")
            .select("user_id")
            .eq("user_id", supabase_id)
            .limit(1)
            .execute()
        )
        if not lookup.data and email:
            lookup = (
                client.table("users")
                .select("user_id")
                .eq("email", email)
                .limit(1)
                .execute()
            )
        if lookup.data:
            supabase_id = lookup.data[0]["user_id"]
        else:
            logger.exception("Failed to create or resolve Supabase user for %s", user.id)
            return None

    concepts = _read_concepts(client)
    existing_states = (
        client.table("user_concept_state")
        .select("concept_id")
        .eq("user_id", supabase_id)
        .limit(1)
        .execute()
    )
    if not existing_states.data and concepts:
        try:
            _batch_create_user_concept_states(client, supabase_id, concepts)
        except Exception:
            logger.exception("Failed to seed user_concept_state for %s", supabase_id)

    try:
        user.supabase_user_id = uuid.UUID(str(supabase_id))
    except (ValueError, AttributeError):
        user.supabase_user_id = supabase_id
    user.save(update_fields=["supabase_user_id"])
    return str(supabase_id)
