"""
Placement-based proficiency seeding for user_concept_state (Phase 1).
"""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional, Tuple

from users.models import JourneyType, SyllabusPlacement

# Display bands (meeting Jul 17 — mastery at 0.8). Agent weak/clear flags unchanged (0.4 / 0.65).
MASTERY_THRESHOLD = 0.8
ALMOST_MASTERED_THRESHOLD = 0.65
WEAK_DISPLAY_THRESHOLD = 0.4

_DEPTH_SCORES = {
    "strong": 0.65,
    "moderate": 0.45,
    "barely": 0.25,
}


def node_proficiency_display(
    proficiency_score: float,
    chapter: str,
    placement: Optional[SyllabusPlacement],
    *,
    is_cold_start: bool = False,
    status: str = "pending",
    node_type: str = "LEARN",
) -> tuple[Optional[int], str]:
    """
    Return (display_pct or None, label) for UI surfaces.
    Internal agent score may remain 0.5 for cold-start concepts; UI shows 0%.
    """
    if status == "skipped" and node_type == "MASTERED":
        return round(proficiency_score * 100), "mastered"

    if status == "completed":
        pct = round(proficiency_score * 100)
        if proficiency_score >= MASTERY_THRESHOLD:
            return pct, "strong"
        if proficiency_score >= ALMOST_MASTERED_THRESHOLD:
            return pct, "almost_mastered"
        if proficiency_score >= WEAK_DISPLAY_THRESHOLD:
            return pct, "moderate"
        return pct, "weak"

    covered = set(placement.covered_chapters or []) if placement else set()
    journey = placement.journey_type if placement else JourneyType.FRESH_START

    if is_cold_start or journey == JourneyType.FRESH_START:
        if journey == JourneyType.MID_JOURNEY and chapter in covered:
            pass
        else:
            return 0, "not_started"

    if journey == JourneyType.MID_JOURNEY and chapter not in covered:
        return 0, "not_started"

    pct = round(proficiency_score * 100)
    if proficiency_score >= MASTERY_THRESHOLD:
        return pct, "strong"
    if proficiency_score >= ALMOST_MASTERED_THRESHOLD:
        return pct, "almost_mastered"
    if proficiency_score >= WEAK_DISPLAY_THRESHOLD:
        return pct, "moderate"
    return pct, "weak"


def _diagnostic_concept_scores(placement: Optional[SyllabusPlacement]) -> Dict[str, float]:
    if placement is None:
        return {}
    baseline = placement.diagnostic_baseline or {}
    raw = baseline.get("concept_scores") or {}
    return {cid: float(score) for cid, score in raw.items()}


def _chapter_label(score: float, probed: bool, *, is_not_started: bool = False) -> str:
    if is_not_started:
        return "not_started"
    if not probed:
        return "not_started"
    if score >= MASTERY_THRESHOLD:
        return "strong"
    if score >= ALMOST_MASTERED_THRESHOLD:
        return "almost_mastered"
    if score >= WEAK_DISPLAY_THRESHOLD:
        return "moderate"
    return "weak"


def _score_for_concept(
    concept: Dict[str, Any],
    placement: Optional[SyllabusPlacement],
) -> Tuple[float, bool]:
    """
    Return (proficiency_score, is_cold_start) for one concept row.
    """
    concept_id = concept.get("concept_id") or ""
    diagnostic_scores = _diagnostic_concept_scores(placement)
    if concept_id in diagnostic_scores:
        score = max(0.0, min(1.0, diagnostic_scores[concept_id]))
        return score, score < 0.4

    if placement is None or placement.journey_type == JourneyType.FRESH_START:
        return 0.5, True

    chapter = concept.get("chapter") or ""

    if placement.journey_type == JourneyType.REVISION_DROPPER:
        baseline = placement.diagnostic_baseline or {}
        overall = baseline.get("overall")
        if overall is not None:
            score = float(overall) + random.uniform(-0.08, 0.08)
            return max(0.2, min(0.85, score)), score < 0.4
        return 0.45, False

    # mid_journey
    covered = set(placement.covered_chapters or [])
    if chapter not in covered:
        return 0.5, True

    depth_map = placement.self_assessed_coverage or {}
    depth = (depth_map.get(chapter) or "moderate").lower()
    score = _DEPTH_SCORES.get(depth, 0.45)
    return score, score < 0.4


def build_diagnostic_baseline(
    concept_scores: Dict[str, float],
    concepts: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build normalized diagnostic_baseline payload for SyllabusPlacement."""
    if not concept_scores:
        return {}

    chapter_buckets: Dict[str, List[float]] = {}
    for concept in concepts:
        cid = concept.get("concept_id")
        chapter = concept.get("chapter")
        if cid in concept_scores and chapter:
            chapter_buckets.setdefault(chapter, []).append(float(concept_scores[cid]))

    chapter_scores = {
        chapter: round(sum(values) / len(values), 4)
        for chapter, values in chapter_buckets.items()
    }
    probed_values = list(concept_scores.values())
    overall = round(sum(probed_values) / len(probed_values), 4) if probed_values else 0.5

    return {
        "concept_scores": {cid: round(float(score), 4) for cid, score in concept_scores.items()},
        "chapter_scores": chapter_scores,
        "probed_chapters": list(chapter_scores.keys()),
        "overall": overall,
        "source": "onboarding_v1",
    }


def build_concept_state_rows(
    user_id: str,
    concepts: List[Dict[str, Any]],
    placement: Optional[SyllabusPlacement],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for concept in concepts:
        score, is_cold = _score_for_concept(concept, placement)
        rows.append(
            {
                "user_id": user_id,
                "concept_id": concept["concept_id"],
                "subject": concept.get("subject", "Physics"),
                "chapter": concept.get("chapter"),
                "proficiency_score": round(score, 4),
                "attempts": 0,
                "correct": 0,
                "flagged_weak": score < 0.4,
                "struggle_streak": 0,
                "error_type_dist": {
                    "conceptual": 0,
                    "procedural": 0,
                    "calculation": 0,
                    "misread": 0,
                },
                "avg_time_seconds": 0.0,
                "is_cold_start": is_cold,
            }
        )
    return rows


def sandbox_summary_from_rows(
    profile,
    placement: Optional[SyllabusPlacement],
    concept_rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build the slide-deck summary shown at onboarding reveal."""
    chapters = sorted({r.get("chapter") for r in concept_rows if r.get("chapter")})
    covered_count = len(placement.covered_chapters or []) if placement else 0
    avg_prof = (
        sum(r["proficiency_score"] for r in concept_rows) / len(concept_rows)
        if concept_rows
        else 0.5
    )
    cold_count = sum(1 for r in concept_rows if r.get("is_cold_start"))
    daily = getattr(profile, "daily_goal_minutes", 30) or 30
    weeks = max(1, round(cold_count * 12 / max(daily, 15)))

    target_exam = getattr(profile, "target_exam", "BOTH")
    target_year = getattr(profile, "target_year", None)
    target_label = f"JEE {'Advanced' if target_exam == 'JEE_ADVANCED' else 'Mains' if target_exam == 'JEE_MAINS' else 'Main + Advanced'}"
    if target_year:
        target_label = f"{target_label} {target_year}"

    first_concept = next((r for r in concept_rows if r.get("is_cold_start")), concept_rows[0] if concept_rows else None)
    first_up = first_concept.get("concept_id", "your first concept").replace("_", " ").title() if first_concept else "your first concept"

    baseline = (placement.diagnostic_baseline or {}) if placement else {}
    probed_chapters = set(baseline.get("probed_chapters") or [])
    chapter_scores = baseline.get("chapter_scores") or {}

    chapter_avgs: Dict[str, List[float]] = {}
    for row in concept_rows:
        chapter = row.get("chapter")
        if chapter:
            chapter_avgs.setdefault(chapter, []).append(float(row["proficiency_score"]))

    chapter_snapshots = []
    covered_set = set(placement.covered_chapters or []) if placement else set()
    for chapter in chapters:
        probed = chapter in probed_chapters
        chapter_rows = [r for r in concept_rows if r.get("chapter") == chapter]
        all_cold = bool(chapter_rows) and all(r.get("is_cold_start") for r in chapter_rows)
        is_not_started = (
            all_cold
            and (
                (placement and placement.journey_type == JourneyType.FRESH_START)
                or chapter not in covered_set
            )
        )
        if is_not_started:
            chapter_snapshots.append(
                {
                    "chapter": chapter,
                    "proficiency_pct": None,
                    "label": "not_started",
                    "probed": probed,
                }
            )
            continue
        if probed and chapter in chapter_scores:
            score = float(chapter_scores[chapter])
        else:
            values = chapter_avgs.get(chapter, [0.5])
            score = sum(values) / len(values)
        chapter_snapshots.append(
            {
                "chapter": chapter,
                "proficiency_pct": round(score * 100),
                "label": _chapter_label(score, probed),
                "probed": probed,
            }
        )

    measured_rows = [r for r in concept_rows if not r.get("is_cold_start")]
    if measured_rows:
        overall_pct: Optional[int] = round(
            sum(r["proficiency_score"] for r in measured_rows) / len(measured_rows) * 100
        )
    else:
        overall_pct = None

    chapter_snapshots.sort(
        key=lambda item: item["proficiency_pct"] if item["proficiency_pct"] is not None else -1
    )
    focus_chapters = [item["chapter"] for item in chapter_snapshots if item["label"] in ("weak", "moderate")][:2]
    strong_chapters = [item["chapter"] for item in reversed(chapter_snapshots) if item["label"] == "strong"][:2]

    return {
        "target_label": target_label,
        "chapters_total": len(chapters),
        "chapters_covered": covered_count,
        "overall_proficiency_pct": overall_pct,
        "concepts_on_path": cold_count or len(concept_rows),
        "estimated_weeks": weeks,
        "first_up": first_up,
        "journey_type": placement.journey_type if placement else JourneyType.FRESH_START,
        "chapter_snapshots": chapter_snapshots,
        "focus_chapters": focus_chapters,
        "strong_chapters": strong_chapters,
    }
