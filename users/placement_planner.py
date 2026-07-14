"""
Rules-first placement diagnostic planner (onboarding v1).

Picks one concept probe per covered chapter (capped) so onboarding stays ~2–3 min
as the concept catalog grows.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional, Set

from roadmap.syllabus import chapter_order_map, syllabus_concept_map
from users.models import JourneyType
from users.supabase_sync import get_supabase_client, is_supabase_configured

_DEPTH_PRIORITY = {"barely": 0, "moderate": 1, "strong": 2}
FRESH_START_MAX_PROBES = 2
REVISION_MAX_PROBES = 5
SECONDS_PER_PROBE = 30


def _read_live_concepts() -> List[Dict[str, Any]]:
    if not is_supabase_configured():
        return []
    client = get_supabase_client()
    if client is None:
        return []
    res = client.table("concepts").select("concept_id, concept_name, chapter, subject").execute()
    return res.data or []


def _practice_concept_ids() -> Set[str]:
    if not is_supabase_configured():
        return set()
    client = get_supabase_client()
    if client is None:
        return set()
    res = (
        client.table("content")
        .select("primary_concept_id")
        .eq("content_type", "practice")
        .execute()
    )
    return {row["primary_concept_id"] for row in (res.data or []) if row.get("primary_concept_id")}


def _concepts_by_chapter(concepts: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for concept in concepts:
        chapter = concept.get("chapter")
        if chapter:
            grouped[chapter].append(concept)
    return grouped


def _concept_sort_key(
    concept: Dict[str, Any],
    syllabus_map: Dict[str, Dict[str, Any]],
    practice_ids: Set[str],
) -> tuple:
    concept_id = concept["concept_id"]
    spec = syllabus_map.get(concept_id, {})
    has_practice = 0 if concept_id in practice_ids else 1
    exam_weight = 0 if spec.get("exam_weight") == "high" else 1
    chapter_order = spec.get("chapter_order", 99)
    return (has_practice, exam_weight, chapter_order, concept_id)


def _pick_concept_for_chapter(
    chapter: str,
    by_chapter: Dict[str, List[Dict[str, Any]]],
    syllabus_map: Dict[str, Dict[str, Any]],
    practice_ids: Set[str],
) -> Optional[Dict[str, Any]]:
    candidates = by_chapter.get(chapter) or []
    if not candidates:
        return None
    sorted_candidates = sorted(
        candidates,
        key=lambda c: _concept_sort_key(c, syllabus_map, practice_ids),
    )
    chosen = sorted_candidates[0]
    return {
        "chapter": chapter,
        "concept_id": chosen["concept_id"],
        "concept_name": chosen.get("concept_name", chosen["concept_id"]),
        "reason": "chapter_probe",
    }


def _ordered_chapter_names(concepts: List[Dict[str, Any]]) -> List[str]:
    order_map = chapter_order_map()
    live_chapters = sorted({c.get("chapter") for c in concepts if c.get("chapter")})
    return sorted(live_chapters, key=lambda ch: order_map.get(ch, 99))


def _sort_chapters_by_depth(
    chapters: List[str],
    self_assessed_coverage: Dict[str, str],
) -> List[str]:
    return sorted(
        chapters,
        key=lambda ch: _DEPTH_PRIORITY.get((self_assessed_coverage.get(ch) or "moderate").lower(), 1),
    )


def build_placement_plan(
    journey_type: str,
    covered_chapters: Optional[List[str]] = None,
    self_assessed_coverage: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Return probe plan and metadata for the onboarding diagnostic step.
    """
    covered = list(covered_chapters or [])
    depth_map = dict(self_assessed_coverage or {})
    concepts = _read_live_concepts()
    syllabus_map = syllabus_concept_map()
    practice_ids = _practice_concept_ids()
    by_chapter = _concepts_by_chapter(concepts)
    all_chapters = _ordered_chapter_names(concepts)

    target_chapters: List[str] = []
    skipped_chapters: List[str] = []

    if journey_type == JourneyType.FRESH_START:
        target_chapters = all_chapters[:FRESH_START_MAX_PROBES]
        skipped_chapters = all_chapters[FRESH_START_MAX_PROBES:]
    elif covered:
        # mid_journey / revision_dropper with self-reported coverage
        pool = _sort_chapters_by_depth(list(covered), depth_map)
        target_chapters = pool[:REVISION_MAX_PROBES]
        skipped_chapters = [ch for ch in all_chapters if ch not in target_chapters]
    elif journey_type == JourneyType.REVISION_DROPPER:
        pool = _sort_chapters_by_depth(all_chapters, depth_map)
        target_chapters = pool[:REVISION_MAX_PROBES]
        skipped_chapters = [ch for ch in all_chapters if ch not in target_chapters]
    else:
        # mid_journey with no chapters selected — no probes
        target_chapters = []
        skipped_chapters = all_chapters

    probes: List[Dict[str, Any]] = []
    for chapter in target_chapters:
        depth = (depth_map.get(chapter) or "moderate").lower()
        probe = _pick_concept_for_chapter(chapter, by_chapter, syllabus_map, practice_ids)
        if probe:
            probe["reason"] = f"{depth}_self_report" if chapter in covered else "first_chapter_probe"
            probes.append(probe)

    total = len(probes)
    return {
        "probes": probes,
        "total_probes": total,
        "estimated_minutes": max(1, round(total * SECONDS_PER_PROBE / 60)),
        "skipped_chapters": skipped_chapters,
        "journey_type": journey_type,
    }


def get_physics_chapters_metadata() -> List[Dict[str, Any]]:
    """Chapter list with concept counts and syllabus order for scalable onboarding UI."""
    concepts = _read_live_concepts()
    order_map = chapter_order_map()
    by_chapter = _concepts_by_chapter(concepts)

    if not by_chapter and not is_supabase_configured():
        fallback = [
            "Laws of Motion",
            "Work Energy & Power",
            "Rotational Motion",
        ]
        return [
            {"name": name, "concept_count": 0, "order": idx + 1}
            for idx, name in enumerate(fallback)
        ]

    names = set(by_chapter.keys()) | set(order_map.keys())
    return [
        {
            "name": name,
            "concept_count": len(by_chapter.get(name, [])),
            "order": order_map.get(name, 99),
        }
        for name in sorted(names, key=lambda ch: order_map.get(ch, 99))
    ]
