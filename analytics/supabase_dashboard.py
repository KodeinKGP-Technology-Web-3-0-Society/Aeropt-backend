"""
Build the dashboard payload from Supabase user_concept_state + concepts + sessions.
"""

from __future__ import annotations

import datetime
from collections import defaultdict
from typing import Any, Dict, List, Optional

from django.utils import timezone

from users.supabase_sync import get_supabase_client, is_supabase_configured

CHAPTER_ORDER = ["Laws of Motion", "Work Energy & Power", "Rotational Motion"]


def _score_to_percent(proficiency_score: float) -> int:
    return max(0, min(100, int(round(float(proficiency_score) * 100))))


def _is_unexplored(state: Dict[str, Any]) -> bool:
    """Concept not yet practiced — internal score may be 0.5 but UI should show 0%."""
    return bool(state.get("is_cold_start")) or int(state.get("attempts") or 0) == 0


def _display_score_percent(state: Dict[str, Any]) -> int:
    if _is_unexplored(state):
        return 0
    return _score_to_percent(state.get("proficiency_score", 0.5))


def _concept_tag(score: int, flagged_weak: bool, *, unexplored: bool = False) -> Optional[str]:
    if unexplored:
        return None
    if flagged_weak or score < 50:
        return "WEAK"
    if score >= 75:
        return "STRONG"
    return None


def _compute_streak(session_dates: List[datetime.date]) -> Dict[str, Any]:
    if not session_dates:
        return {"current_streak": 0, "dots": [False] * 7}

    unique_days = sorted(set(session_dates), reverse=True)
    today = timezone.now().date()
    current = 0

    if unique_days[0] == today:
        cursor = today
        for day in unique_days:
            if day == cursor:
                current += 1
                cursor -= datetime.timedelta(days=1)
            elif day < cursor:
                break
    elif unique_days[0] == today - datetime.timedelta(days=1):
        cursor = today - datetime.timedelta(days=1)
        for day in unique_days:
            if day == cursor:
                current += 1
                cursor -= datetime.timedelta(days=1)
            elif day < cursor:
                break

    dots = []
    for offset in range(6, -1, -1):
        day = today - datetime.timedelta(days=offset)
        dots.append(day in unique_days)

    return {"current_streak": current, "dots": dots}


def build_dashboard_from_supabase(supabase_user_id: str) -> Optional[Dict[str, Any]]:
    if not is_supabase_configured():
        return None

    client = get_supabase_client()
    if client is None:
        return None

    concepts_res = client.table("concepts").select("concept_id, concept_name, chapter").execute()
    concept_names = {row["concept_id"]: row.get("concept_name", row["concept_id"]) for row in (concepts_res.data or [])}
    concept_chapters = {row["concept_id"]: row.get("chapter", "Physics") for row in (concepts_res.data or [])}

    states_res = (
        client.table("user_concept_state")
        .select("*")
        .eq("user_id", supabase_user_id)
        .execute()
    )
    states = states_res.data or []

    sessions_res = (
        client.table("sessions")
        .select("updated_at")
        .eq("user_id", supabase_user_id)
        .execute()
    )
    session_dates: List[datetime.date] = []
    for session in sessions_res.data or []:
        raw = session.get("updated_at")
        if not raw:
            continue
        try:
            dt = datetime.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            session_dates.append(dt.date())
        except ValueError:
            continue

    streak_info = _compute_streak(session_dates)

    attempted = [s for s in states if not _is_unexplored(s)]
    overall = (
        int(sum(_display_score_percent(s) for s in attempted) / len(attempted))
        if attempted
        else 0
    )

    weak_states = [
        s for s in states
        if not _is_unexplored(s)
        and (s.get("flagged_weak") or _display_score_percent(s) < 50)
    ]
    weak_list = [
        concept_names.get(s.get("concept_id"), s.get("concept_id", ""))
        for s in weak_states
    ]

    stats = [
        {
            "id": "proficiency",
            "label": "Overall Proficiency",
            "value": f"{overall}%",
            "subtext": f"across {len(attempted)} attempted concepts",
        },
        {
            "id": "weak_concepts",
            "label": "Concepts Flagged Weak",
            "value": str(len(weak_states)),
            "subtext": "need focused attention",
            "list": weak_list,
        },
        {
            "id": "streak",
            "label": "Session Streak",
            "value": str(streak_info["current_streak"]),
            "subtext": "days in a row",
            "dots": streak_info["dots"],
        },
    ]

    chapters_map: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for state in states:
        concept_id = state.get("concept_id", "")
        chapter = state.get("chapter") or concept_chapters.get(concept_id, "Physics")
        unexplored = _is_unexplored(state)
        score = _display_score_percent(state)
        attempts = int(state.get("attempts") or 0)
        correct = int(state.get("correct") or 0)
        accuracy = int((correct / attempts) * 100) if attempts > 0 else 0

        chapters_map[chapter].append({
            "name": concept_names.get(concept_id, concept_id),
            "score": score,
            "attempts": attempts,
            "accuracy": accuracy,
            "tag": _concept_tag(score, bool(state.get("flagged_weak")), unexplored=unexplored),
            "not_started": unexplored,
        })

    ordered_chapters = [name for name in CHAPTER_ORDER if name in chapters_map]
    ordered_chapters.extend(sorted(name for name in chapters_map if name not in CHAPTER_ORDER))

    chapters_data = []
    for chapter_name in ordered_chapters:
        concepts_list = chapters_map[chapter_name]
        explored = [c for c in concepts_list if not c.get("not_started")]
        ch_total = sum(c["score"] for c in explored)
        ch_count = len(explored)
        chapters_data.append({
            "name": chapter_name,
            "conceptCount": len(concepts_list),
            "overallScore": int(ch_total / ch_count) if ch_count else 0,
            "concepts": concepts_list,
        })

    return {
        "stats": stats,
        "conceptHealth": {
            "title": "Physics — Concept Health",
            "tabs": ordered_chapters or CHAPTER_ORDER,
            "chapters": chapters_data,
        },
    }
