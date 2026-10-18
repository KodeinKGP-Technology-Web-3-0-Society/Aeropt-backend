"""
Bridge Django users to the agent's Supabase `users` + `user_concept_state` tables.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from django.conf import settings

from users.placement import build_concept_state_rows, sandbox_summary_from_rows

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


def _preferred_depth(user) -> str:
    profile = getattr(user, "student_profile", None)
    if profile and profile.preferred_depth:
        return profile.preferred_depth
    return "standard"


def _read_concepts(client) -> List[Dict[str, Any]]:
    res = client.table("concepts").select("concept_id, concept_name, chapter, subject").execute()
    return res.data or []


def get_physics_chapters(client=None) -> List[str]:
    from users.placement_planner import get_physics_chapters_metadata

    return [ch["name"] for ch in get_physics_chapters_metadata()]


def _batch_create_user_concept_states(client, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return
    client.table("user_concept_state").insert(rows).execute()


def _upsert_user_concept_states(client, rows: List[Dict[str, Any]]) -> None:
    """Insert or update placement rows in one request.

    The table is keyed by (user_id, concept_id). service_role cannot delete,
    so a re-seed must not wipe the table. One upsert covers both new concepts
    and existing ones; a per-row update was one HTTP call per concept.
    """
    if not rows:
        return
    client.table("user_concept_state").upsert(
        rows,
        on_conflict="user_id,concept_id",
    ).execute()


def sync_profile_to_supabase(user) -> None:
    """Push target_exam and preferred_depth to Supabase users row."""
    if not is_supabase_configured():
        return

    supabase_id = ensure_supabase_user(user, seed_concepts=False)
    if not supabase_id:
        return

    client = get_supabase_client()
    if client is None:
        return

    try:
        client.table("users").update(
            {
                "target_exam": _supabase_target_exam(user),
                "preferred_depth": _preferred_depth(user),
                "name": user.full_name or user.email,
            }
        ).eq("user_id", supabase_id).execute()
    except Exception:
        logger.exception("Failed to sync profile to Supabase for %s", user.id)


def seed_user_concept_state_from_placement(user) -> Optional[Dict[str, Any]]:
    """
    Seed or replace user_concept_state rows from syllabus placement.
    Returns sandbox summary dict for the reveal slide deck.
    """
    if not is_supabase_configured():
        return None

    supabase_id = ensure_supabase_user(user, seed_concepts=False)
    if not supabase_id:
        return None

    client = get_supabase_client()
    if client is None:
        return None

    concepts = _read_concepts(client)
    if not concepts:
        return None

    placement = getattr(user, "syllabus_placement", None)
    profile = getattr(user, "student_profile", None)
    rows = build_concept_state_rows(supabase_id, concepts, placement)

    try:
        _upsert_user_concept_states(client, rows)
    except Exception:
        logger.exception("Failed to seed placement proficiency for %s", supabase_id)
        return None

    sync_profile_to_supabase(user)
    return sandbox_summary_from_rows(profile, placement, rows)


def ensure_supabase_user(user, *, seed_concepts: bool = True) -> Optional[str]:
    """
    Return the linked Supabase user_id for a Django user, creating/linking as needed.

    Concept seeding is deferred until onboarding completes unless seed_concepts=True
    and the user already finished onboarding (or has no profile gate).
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
        "preferred_depth": _preferred_depth(user),
    }

    try:
        client.table("users").insert(row).execute()
    except Exception:
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

    profile = getattr(user, "student_profile", None)
    onboarding_done = bool(profile and profile.onboarding_completed)

    if seed_concepts:
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
                if onboarding_done and hasattr(user, "syllabus_placement"):
                    placement_rows = build_concept_state_rows(
                        supabase_id, concepts, user.syllabus_placement
                    )
                    _batch_create_user_concept_states(client, placement_rows)
                elif onboarding_done or profile is None:
                    flat_rows = build_concept_state_rows(supabase_id, concepts, None)
                    _batch_create_user_concept_states(client, flat_rows)
                # else: defer until onboarding complete
            except Exception:
                logger.exception("Failed to seed user_concept_state for %s", supabase_id)

    try:
        user.supabase_user_id = uuid.UUID(str(supabase_id))
    except (ValueError, AttributeError):
        user.supabase_user_id = supabase_id
    user.save(update_fields=["supabase_user_id"])
    return str(supabase_id)
