"""
analytics/supabase_performance.py

Builds the Performance analytics payload:
  - Subject/chapter/concept breakdown with error_type_dist
  - Timeline (from daily_activity)
  - Error breakdown (aggregated across all concepts)
"""

from __future__ import annotations

import datetime
from collections import defaultdict
from typing import Any, Dict, List, Optional

from django.utils import timezone

from analytics.supabase_dashboard import (
    CHAPTER_ORDER,
    _display_score_percent,
    _is_unexplored,
    _score_to_percent,
)
from users.supabase_sync import get_supabase_client, is_supabase_configured

ERROR_KEYS = ["conceptual", "procedural", "calculation", "misread"]
SUBJECTS = ["Physics", "Chemistry", "Maths"]


def _build_error_breakdown(states: List[Dict[str, Any]]) -> Dict[str, Any]:
    totals: Dict[str, int] = defaultdict(int)
    for state in states:
        dist = state.get("error_type_dist") or {}
        for key in ERROR_KEYS:
            totals[key] += int(dist.get(key, 0))
    total = sum(totals.values())
    return {
        key: {
            "count": totals[key],
            "pct": int(round(totals[key] / total * 100)) if total else 0,
        }
        for key in ERROR_KEYS
    }


def _build_subject_breakdown(
    states: List[Dict[str, Any]],
    concept_names: Dict[str, str],
    concept_subjects: Dict[str, str],
    concept_chapters: Dict[str, str],
    subject_filter: Optional[str] = None,
    chapter_filter: Optional[str] = None,
    placement=None,
) -> List[Dict[str, Any]]:
    # Group states by subject → chapter → concept
    tree: Dict[str, Dict[str, List[Dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for state in states:
        cid = state.get("concept_id", "")
        subject = state.get("subject") or concept_subjects.get(cid, "Physics")
        chapter = state.get("chapter") or concept_chapters.get(cid, "")
        if subject_filter and subject != subject_filter:
            continue
        if chapter_filter and chapter != chapter_filter:
            continue
        tree[subject][chapter].append(state)

    result = []
    for subject in SUBJECTS:
        if subject not in tree:
            continue
        chapters_out = []
        for chapter_name in sorted(tree[subject].keys()):
            cstates = tree[subject][chapter_name]
            concepts_out = []
            chapter_scores = []
            for state in cstates:
                cid = state.get("concept_id", "")
                chapter = state.get("chapter") or concept_chapters.get(cid, "")
                unexplored = _is_unexplored(state, chapter, placement)
                score = _display_score_percent(state, chapter, placement)
                attempts = int(state.get("attempts") or 0)
                correct = int(state.get("correct") or 0)
                accuracy = int(correct / attempts * 100) if attempts else 0
                if not unexplored:
                    chapter_scores.append(score)
                concepts_out.append({
                    "concept_id": cid,
                    "concept_name": concept_names.get(cid, cid),
                    "proficiency": score,
                    "attempts": attempts,
                    "correct": correct,
                    "accuracy": accuracy,
                    "avg_time_seconds": float(state.get("avg_time_seconds") or 0),
                    "error_type_dist": state.get("error_type_dist") or {},
                    "flagged_weak": bool(state.get("flagged_weak")),
                    "is_decaying": bool(state.get("is_decaying")),
                    "is_cold_start": bool(state.get("is_cold_start")),
                    "last_seen_at": state.get("last_seen_at"),
                })
            chapter_avg = int(sum(chapter_scores) / len(chapter_scores)) if chapter_scores else 0
            chapters_out.append({
                "chapter": chapter_name,
                "proficiency": chapter_avg,
                "concept_count": len(concepts_out),
                "concepts": concepts_out,
            })

        subject_scores = [c["proficiency"] for c in chapters_out if c["proficiency"] > 0]
        subject_avg = int(sum(subject_scores) / len(subject_scores)) if subject_scores else 0
        result.append({
            "subject": subject,
            "proficiency": subject_avg,
            "chapters": chapters_out,
        })
    return result


def _build_timeline(client, user_id: str, days: int = 30) -> List[Dict[str, Any]]:
    """Read daily_activity rows for the last N days."""
    cutoff = (timezone.now().date() - datetime.timedelta(days=days)).isoformat()
    try:
        res = (
            client.table("daily_activity")
            .select("activity_date,minutes_studied,questions_attempted,correct_answers,goal_met,subjects_touched")
            .eq("user_id", user_id)
            .gte("activity_date", cutoff)
            .order("activity_date", desc=False)
            .execute()
        )
        return res.data or []
    except Exception:
        return []


def build_performance_from_supabase(
    supabase_user_id: str,
    subject_filter: Optional[str] = None,
    chapter_filter: Optional[str] = None,
    timeline_days: int = 30,
    placement=None,
) -> Optional[Dict[str, Any]]:
    if not is_supabase_configured():
        return None
    client = get_supabase_client()
    if client is None:
        return None

    concepts_res = client.table("concepts").select("concept_id,concept_name,chapter,subject").execute()
    concept_names = {r["concept_id"]: r.get("concept_name", r["concept_id"]) for r in (concepts_res.data or [])}
    concept_subjects = {r["concept_id"]: r.get("subject", "Physics") for r in (concepts_res.data or [])}
    concept_chapters = {r["concept_id"]: r.get("chapter", "") for r in (concepts_res.data or [])}

    states_res = (
        client.table("user_concept_state")
        .select("*")
        .eq("user_id", supabase_user_id)
        .execute()
    )
    states = states_res.data or []

    total_attempts = sum(int(s.get("attempts") or 0) for s in states)
    total_correct = sum(int(s.get("correct") or 0) for s in states)
    concepts_attempted = sum(1 for s in states if int(s.get("attempts") or 0) > 0)

    measured = [
        s for s in states
        if not _is_unexplored(s, s.get("chapter") or concept_chapters.get(s.get("concept_id", ""), ""), placement)
    ]
    overall_proficiency = (
        int(sum(_score_to_percent(s.get("proficiency_score", 0.5)) for s in measured) / len(measured))
        if measured else 0
    )

    subjects = _build_subject_breakdown(
        states, concept_names, concept_subjects, concept_chapters,
        subject_filter=subject_filter, chapter_filter=chapter_filter, placement=placement,
    )
    error_breakdown = _build_error_breakdown(states)
    timeline_rows = _build_timeline(client, supabase_user_id, days=timeline_days)

    timeline = [
        {
            "date": row["activity_date"],
            "minutes_studied": row.get("minutes_studied", 0),
            "questions_attempted": row.get("questions_attempted", 0),
            "correct_answers": row.get("correct_answers", 0),
            "accuracy": int(
                row["correct_answers"] / row["questions_attempted"] * 100
            ) if (row.get("questions_attempted") or 0) > 0 else 0,
            "goal_met": bool(row.get("goal_met", False)),
            "subjects_touched": row.get("subjects_touched") or [],
        }
        for row in timeline_rows
    ]

    return {
        "overall": {
            "proficiency": overall_proficiency,
            "attempted": concepts_attempted,
            "total_concepts": len(states),
            "total_attempts": total_attempts,
            "total_correct": total_correct,
            "overall_accuracy": int(total_correct / total_attempts * 100) if total_attempts else 0,
        },
        "subjects": subjects,
        "error_breakdown": error_breakdown,
        "timeline": timeline,
    }
