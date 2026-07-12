"""
Build the Progress page payload from Supabase user_concept_state + user_attempts.
"""

from __future__ import annotations

import datetime
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from django.utils import timezone

from analytics.supabase_dashboard import CHAPTER_ORDER, _score_to_percent
from users.models import SyllabusPlacement
from users.supabase_sync import get_supabase_client, is_supabase_configured

WMA_ALPHA = 0.7
PROGRESS_DAYS = 14
TREND_THRESHOLD = 0.03

ERROR_TYPE_LABELS = {
    "conceptual": "Conceptual",
    "procedural": "Procedural",
    "calculation": "Calculation",
    "misread": "Misinterpretation",
}

CHAPTER_CHART_COLORS = ["#6258ff", "#eab308", "#ef4444", "#38bdf8", "#22c55e"]


def _parse_iso_datetime(raw: Any) -> Optional[datetime.datetime]:
    if not raw:
        return None
    try:
        return datetime.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


def _format_relative_time(raw: Any) -> str:
    dt = _parse_iso_datetime(raw)
    if dt is None:
        return "—"
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, datetime.timezone.utc)
    now = timezone.now()
    delta = now - dt
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        minutes = max(1, seconds // 60)
        return f"{minutes}m ago"
    if seconds < 86400:
        hours = max(1, seconds // 3600)
        return f"{hours}h ago"
    days = max(1, seconds // 86400)
    if days == 1:
        return "1d ago"
    if days < 7:
        return f"{days}d ago"
    return dt.date().strftime("%b %d")


def _baseline_scores(placement: Optional[SyllabusPlacement]) -> Dict[str, float]:
    if placement is None:
        return {}
    baseline = placement.diagnostic_baseline or {}
    raw = baseline.get("concept_scores") or {}
    return {str(k): float(v) for k, v in raw.items()}


def _wma_update(old_score: float, is_correct: bool) -> float:
    outcome = 1.0 if is_correct else 0.0
    return WMA_ALPHA * old_score + (1 - WMA_ALPHA) * outcome


def _trend_label(current: float, baseline: float) -> str:
    delta = current - baseline
    if delta >= TREND_THRESHOLD:
        return "up"
    if delta <= -TREND_THRESHOLD:
        return "down"
    return "flat"


def _aggregate_mistakes(states: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    totals = defaultdict(int)
    for state in states:
        dist = state.get("error_type_dist") or {}
        for key, count in dist.items():
            if key in ERROR_TYPE_LABELS:
                totals[key] += int(count or 0)

    ordered_keys = ["conceptual", "procedural", "calculation", "misread"]
    total = sum(totals.values())
    rows = []
    for key in ordered_keys:
        count = totals.get(key, 0)
        if total == 0:
            percentage = 0
        else:
            percentage = int(round((count / total) * 100))
        rows.append({
            "type": ERROR_TYPE_LABELS[key],
            "count": count,
            "percentage": percentage,
        })
    return rows


def _chapter_series(
    attempts: List[Dict[str, Any]],
    concept_chapters: Dict[str, str],
    baseline: Dict[str, float],
    states: List[Dict[str, Any]],
    days: int = PROGRESS_DAYS,
) -> Dict[str, Any]:
    today = timezone.now().date()
    day_list = [today - datetime.timedelta(days=offset) for offset in range(days - 1, -1, -1)]

    attempted_ids = {
        s.get("concept_id", "")
        for s in states
        if int(s.get("attempts") or 0) > 0 and s.get("concept_id")
    }

    scores: Dict[str, float] = {}
    for concept_id in concept_chapters:
        if concept_id in baseline:
            scores[concept_id] = baseline[concept_id]
        else:
            match = next((s for s in states if s.get("concept_id") == concept_id), None)
            scores[concept_id] = float(match.get("proficiency_score", 0.5)) if match else 0.5

    snapshots: Dict[datetime.date, Dict[str, float]] = {day: dict(scores) for day in day_list}

    sorted_attempts = sorted(
        attempts,
        key=lambda row: str(row.get("created_at") or ""),
    )
    for attempt in sorted_attempts:
        concept_id = attempt.get("concept_id", "")
        if not concept_id:
            continue
        dt = _parse_iso_datetime(attempt.get("created_at"))
        if dt is None:
            continue
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, datetime.timezone.utc)
        attempt_day = dt.date()

        old_score = scores.get(concept_id, baseline.get(concept_id, 0.5))
        scores[concept_id] = _wma_update(old_score, bool(attempt.get("is_correct")))
        attempted_ids.add(concept_id)

        for day in day_list:
            if day >= attempt_day:
                snapshots[day][concept_id] = scores[concept_id]

    chapter_names = list(CHAPTER_ORDER)
    chapter_names.extend(
        sorted({
            chapter
            for chapter in concept_chapters.values()
            if chapter and chapter not in CHAPTER_ORDER
        })
    )

    chapters_payload = []
    for chapter_name in chapter_names:
        concept_ids = [cid for cid, ch in concept_chapters.items() if ch == chapter_name]
        active_ids = [cid for cid in concept_ids if cid in attempted_ids]
        if not active_ids:
            continue

        series: List[int] = []
        for day in day_list:
            day_scores = [
                _score_to_percent(snapshots[day].get(cid, baseline.get(cid, 0.5)))
                for cid in active_ids
            ]
            series.append(int(sum(day_scores) / len(day_scores)) if day_scores else 0)

        chapters_payload.append({
            "name": chapter_name,
            "data": series,
            "color": CHAPTER_CHART_COLORS[len(chapters_payload) % len(CHAPTER_CHART_COLORS)],
        })

    date_labels = [day.strftime("%b %d").replace(" 0", " ") for day in day_list]
    return {"dates": date_labels, "chapters": chapters_payload}


def _most_improved(
    states: List[Dict[str, Any]],
    concept_names: Dict[str, str],
    baseline: Dict[str, float],
) -> Tuple[str, int]:
    best_name = "—"
    best_delta = 0
    for state in states:
        if int(state.get("attempts") or 0) <= 0:
            continue
        concept_id = state.get("concept_id", "")
        current = float(state.get("proficiency_score", 0.5))
        start = baseline.get(concept_id, current)
        delta_pct = int(round((current - start) * 100))
        if delta_pct > best_delta:
            best_delta = delta_pct
            best_name = concept_names.get(concept_id, concept_id)
    return best_name, best_delta


def build_progress_from_supabase(
    supabase_user_id: str,
    placement: Optional[SyllabusPlacement] = None,
) -> Optional[Dict[str, Any]]:
    if not is_supabase_configured():
        return None

    client = get_supabase_client()
    if client is None:
        return None

    concepts_res = client.table("concepts").select("concept_id, concept_name, chapter").execute()
    concept_names = {
        row["concept_id"]: row.get("concept_name", row["concept_id"])
        for row in (concepts_res.data or [])
    }
    concept_chapters = {
        row["concept_id"]: row.get("chapter", "Physics")
        for row in (concepts_res.data or [])
    }

    states_res = (
        client.table("user_concept_state")
        .select("*")
        .eq("user_id", supabase_user_id)
        .execute()
    )
    states = states_res.data or []

    attempts_res = (
        client.table("user_attempts")
        .select("concept_id, is_correct, created_at")
        .eq("user_id", supabase_user_id)
        .order("created_at")
        .execute()
    )
    attempts = attempts_res.data or []

    baseline = _baseline_scores(placement)

    attempted_states = [s for s in states if int(s.get("attempts") or 0) > 0]
    total_attempts = sum(int(s.get("attempts") or 0) for s in states)
    total_correct = sum(int(s.get("correct") or 0) for s in states)
    overall_accuracy = int(round((total_correct / total_attempts) * 100)) if total_attempts > 0 else 0

    most_improved_name, most_improved_delta = _most_improved(states, concept_names, baseline)
    most_improved_subtext = (
        f"+{most_improved_delta}% since onboarding"
        if most_improved_delta > 0
        else "most improved this week"
    )

    stats = [
        {
            "id": "questions_attempted",
            "label": "Total Questions Attempted",
            "value": str(total_attempts),
            "subtext": "questions across all chapters",
        },
        {
            "id": "overall_accuracy",
            "label": "Overall Accuracy",
            "value": f"{overall_accuracy}%",
            "subtext": "cumulative across all attempts",
        },
        {
            "id": "most_improved",
            "label": "Most Improved",
            "value": most_improved_name,
            "subtext": most_improved_subtext,
        },
    ]

    mistakes_distribution = _aggregate_mistakes(attempted_states)

    proficiency_over_time = _chapter_series(
        attempts=attempts,
        concept_chapters=concept_chapters,
        baseline=baseline,
        states=states,
    )

    concept_rows = []
    for state in attempted_states:
        concept_id = state.get("concept_id", "")
        chapter = state.get("chapter") or concept_chapters.get(concept_id, "Physics")
        score = _score_to_percent(state.get("proficiency_score", 0.5))
        attempts_count = int(state.get("attempts") or 0)
        correct = int(state.get("correct") or 0)
        accuracy = int((correct / attempts_count) * 100) if attempts_count > 0 else 0
        current = float(state.get("proficiency_score", 0.5))
        start = baseline.get(concept_id, current)

        concept_rows.append({
            "concept": concept_names.get(concept_id, concept_id),
            "chapter": chapter,
            "score": score,
            "attempts": attempts_count,
            "accuracy": accuracy,
            "lastAttempted": _format_relative_time(state.get("last_seen_at")),
            "trend": _trend_label(current, start),
        })

    concept_rows.sort(key=lambda row: row["score"])

    return {
        "subtitle": f"Your learning trajectory over the last {PROGRESS_DAYS} days",
        "stats": stats,
        "mistakesDistribution": mistakes_distribution,
        "proficiencyOverTime": proficiency_over_time,
        "conceptBreakdownTable": concept_rows,
        "totalAttempts": total_attempts,
    }
