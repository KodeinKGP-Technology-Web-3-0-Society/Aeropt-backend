"""
analytics/supabase_briefing.py

Builds the daily-briefing payload consumed by the Dashboard.
Reads from: users, user_concept_state, concepts, sessions, daily_activity, session_skips.
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

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DECAY_THRESHOLD_DAYS = 14
WEAK_SCORE_THRESHOLD = 0.50
STRUGGLE_STREAK_TRIGGER = 3
SUBJECTS = ["Physics", "Chemistry", "Maths"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_dt(raw: Any) -> Optional[datetime.datetime]:
    if not raw:
        return None
    try:
        return datetime.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


def _days_since(raw: Any) -> Optional[int]:
    dt = _parse_dt(raw)
    if dt is None:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, datetime.timezone.utc)
    delta = timezone.now() - dt
    return max(0, delta.days)


def _stage_from_proficiency(score: float, is_cold_start: bool) -> str:
    """Pick the next stage based on proficiency score."""
    if is_cold_start or score < 0.3:
        return "theory"
    if score < 0.6:
        return "practice"
    return "pyq"


def _get_active_skips(client, user_id: str) -> set:
    """Return concept_ids currently skipped (within TTL)."""
    try:
        res = (
            client.table("session_skips")
            .select("concept_id")
            .eq("user_id", user_id)
            .gt("expires_at", timezone.now().isoformat())
            .execute()
        )
        return {r["concept_id"] for r in (res.data or [])}
    except Exception:
        return set()


def _get_daily_activity(client, user_id: str) -> Dict[str, Any]:
    """Get today's activity row."""
    today = timezone.now().date().isoformat()
    try:
        res = (
            client.table("daily_activity")
            .select("minutes_studied, questions_attempted, correct_answers, goal_met, streak_day")
            .eq("user_id", user_id)
            .eq("activity_date", today)
            .limit(1)
            .execute()
        )
        return res.data[0] if res.data else {}
    except Exception:
        return {}


def _get_resume_session(client, user_id: str) -> Optional[Dict[str, Any]]:
    """Return the most recent incomplete session for resume widget."""
    try:
        res = (
            client.table("sessions")
            .select("session_id, session_type, last_decision, concepts_touched, updated_at")
            .eq("user_id", user_id)
            .is_("ended_at", "null")
            .order("started_at", desc=True)
            .limit(1)
            .execute()
        )
        return res.data[0] if res.data else None
    except Exception:
        return None


def _build_pcm_rings(
    states: List[Dict[str, Any]],
    concept_subjects: Dict[str, str],
    placement=None,
) -> List[Dict[str, Any]]:
    """Compute readiness % and weak count per subject (Physics, Chemistry, Maths)."""
    subject_scores: Dict[str, List[float]] = defaultdict(list)
    subject_weak: Dict[str, int] = defaultdict(int)

    for state in states:
        cid = state.get("concept_id", "")
        subject = state.get("subject") or concept_subjects.get(cid, "Physics")
        chapter = state.get("chapter", "")
        if _is_unexplored(state, chapter, placement):
            continue
        score = float(state.get("proficiency_score", 0.5))
        subject_scores[subject].append(score)
        if state.get("flagged_weak") or score < WEAK_SCORE_THRESHOLD:
            subject_weak[subject] += 1

    rings = []
    for subject in SUBJECTS:
        scores = subject_scores.get(subject, [])
        readiness = int(round(sum(scores) / len(scores) * 100)) if scores else 0
        rings.append({
            "subject": subject,
            "readiness_pct": readiness,
            "weak_count": subject_weak.get(subject, 0),
            "has_data": len(scores) > 0,
        })
    return rings


def _build_weak_cluster(
    states: List[Dict[str, Any]],
    concept_names: Dict[str, str],
    skipped_ids: set,
    placement=None,
) -> List[Dict[str, Any]]:
    """Return up to 4 weakest non-skipped concepts sorted by proficiency ASC."""
    weak = []
    for state in states:
        cid = state.get("concept_id", "")
        if cid in skipped_ids:
            continue
        chapter = state.get("chapter", "")
        if _is_unexplored(state, chapter, placement):
            continue
        score = float(state.get("proficiency_score", 0.5))
        if state.get("flagged_weak") or score < WEAK_SCORE_THRESHOLD:
            weak.append({
                "concept_id": cid,
                "concept_name": concept_names.get(cid, cid),
                "proficiency": round(score, 3),
                "chapter": chapter,
                "subject": state.get("subject", "Physics"),
            })

    weak.sort(key=lambda x: x["proficiency"])
    return weak[:4]


def _build_decaying(
    states: List[Dict[str, Any]],
    concept_names: Dict[str, str],
) -> List[Dict[str, Any]]:
    """Return concepts where is_decaying=True (pre-computed flag)."""
    return [
        {
            "concept_id": s["concept_id"],
            "concept_name": concept_names.get(s["concept_id"], s["concept_id"]),
            "days_since_practiced": _days_since(s.get("last_seen_at")),
        }
        for s in states
        if s.get("is_decaying")
    ]


def _choose_mission(
    states: List[Dict[str, Any]],
    concept_names: Dict[str, str],
    skipped_ids: set,
    placement=None,
) -> Optional[Dict[str, Any]]:
    """
    Pick the highest-leverage concept for today's mission.
    Priority: flagged_weak (non-skipped) → lowest proficiency (non-skipped) → decaying.
    """
    candidates = []
    for state in states:
        cid = state.get("concept_id", "")
        if cid in skipped_ids:
            continue
        chapter = state.get("chapter", "")
        if _is_unexplored(state, chapter, placement):
            continue
        score = float(state.get("proficiency_score", 0.5))
        priority = 0
        if state.get("flagged_weak"):
            priority = 2
        elif score < WEAK_SCORE_THRESHOLD:
            priority = 1
        elif state.get("is_decaying"):
            priority = 0
        else:
            continue
        candidates.append((priority, score, state))

    if not candidates:
        return None

    candidates.sort(key=lambda x: (-x[0], x[1]))
    _, _, best = candidates[0]
    cid = best["concept_id"]
    score = float(best.get("proficiency_score", 0.5))
    is_cold = bool(best.get("is_cold_start", True))
    stage = _stage_from_proficiency(score, is_cold)
    # Rough time estimate by stage
    estimate = {"theory": 20, "practice": 15, "pyq": 12}.get(stage, 15)

    return {
        "concept_id": cid,
        "concept_name": concept_names.get(cid, cid),
        "subject": best.get("subject", "Physics"),
        "chapter": best.get("chapter", ""),
        "stage": stage,
        "estimate_min": estimate,
        "proficiency": round(score, 3),
    }


def _build_briefing_text(mission: Optional[Dict], cluster: List[Dict], resume: Optional[Dict]) -> str:
    if resume:
        concept = resume.get("last_decision", {}).get("target", "your last concept") if resume.get("last_decision") else "your last concept"
        return f"You have an unfinished session on {concept}. Resume or start fresh with today's plan."
    if not mission:
        return "No weak concepts detected — great progress! Keep practicing to maintain your edge."
    concept = mission["concept_name"]
    stage = mission["stage"]
    if cluster:
        root = cluster[0]["concept_name"]
        if root != concept:
            return (
                f"Your weak cluster starts at {root}, which is blocking {concept}. "
                f"Let's fix the foundation first — {stage} session ready."
            )
    return f"{concept} needs attention ({stage} recommended). Ready to go?"


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_daily_briefing(
    supabase_user_id: str,
    placement=None,
    goal_minutes: int = 30,
) -> Optional[Dict[str, Any]]:
    """
    Build the full daily-briefing payload for the Dashboard.
    Returns None only on Supabase connectivity failure.
    """
    if not is_supabase_configured():
        return None

    client = get_supabase_client()
    if client is None:
        return None

    # --- Fetch concept catalog ---
    concepts_res = client.table("concepts").select("concept_id, concept_name, chapter, subject").execute()
    concept_names = {r["concept_id"]: r.get("concept_name", r["concept_id"]) for r in (concepts_res.data or [])}
    concept_subjects = {r["concept_id"]: r.get("subject", "Physics") for r in (concepts_res.data or [])}

    # --- Fetch user state ---
    states_res = (
        client.table("user_concept_state")
        .select("*")
        .eq("user_id", supabase_user_id)
        .execute()
    )
    states = states_res.data or []

    # --- Auxiliary queries ---
    skipped_ids = _get_active_skips(client, supabase_user_id)
    today_activity = _get_daily_activity(client, supabase_user_id)
    resume_session = _get_resume_session(client, supabase_user_id)

    # --- Build components ---
    pcm = _build_pcm_rings(states, concept_subjects, placement)
    cluster = _build_weak_cluster(states, concept_names, skipped_ids, placement)
    decaying = _build_decaying(states, concept_names)
    mission = _choose_mission(states, concept_names, skipped_ids, placement)

    # --- Alternative mission (next best after mission) ---
    extended_skips = skipped_ids | ({mission["concept_id"]} if mission else set())
    alternative = _choose_mission(states, concept_names, extended_skips, placement)
    alternatives = [alternative] if alternative else []

    # --- Resume context ---
    resume_payload = None
    if resume_session:
        decision = resume_session.get("last_decision") or {}
        touched = resume_session.get("concepts_touched") or []
        resume_payload = {
            "session_id": resume_session["session_id"],
            "concept": decision.get("target_concept_id") or (touched[0] if touched else ""),
            "stage": decision.get("mode", "practice"),
        }

    # --- Goal widget ---
    minutes_done = int(today_activity.get("minutes_studied") or 0)
    goal = {
        "minutes_target": goal_minutes,
        "minutes_done": minutes_done,
        "goal_met": bool(today_activity.get("goal_met", False)),
        "streak_day": int(today_activity.get("streak_day") or 0),
    }

    # --- Why block (for mission) ---
    why: Dict[str, Any] = {"prereqs": [], "dependents": [], "reason_codes": []}
    if mission:
        if mission["concept_id"] in {s["concept_id"] for s in states if s.get("flagged_weak")}:
            why["reason_codes"].append("error_pattern")
        if mission["concept_id"] in {s["concept_id"] for s in states if s.get("is_decaying")}:
            why["reason_codes"].append("decay")
        if not why["reason_codes"]:
            why["reason_codes"].append("weak_prereq")

    briefing_text = _build_briefing_text(mission, cluster, resume_payload)

    return {
        "briefing_text": briefing_text,
        "plan_minutes": mission["estimate_min"] if mission else goal_minutes,
        "depth": "standard",
        "mission": mission,
        "why": why,
        "pcm": pcm,
        "cluster": cluster,
        "decaying": decaying,
        "goal": goal,
        "resume": resume_payload,
        "alternatives": alternatives,
    }
