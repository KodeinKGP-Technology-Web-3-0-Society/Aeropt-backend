"""Personal roadmap generator — Phase 2."""

from __future__ import annotations

from collections import deque
from typing import Any, Dict, List, Optional, Tuple

from django.db import transaction
from django.utils import timezone

from roadmap.models import LearningPath, NodeStatus, NodeType, PathNode
from roadmap.syllabus import chapter_order_map, prerequisite_map, syllabus_concept_map
from users.models import JourneyType, StudentProfile, SyllabusPlacement
from users.supabase_sync import get_supabase_client, is_supabase_configured


def _read_live_concepts() -> List[Dict[str, Any]]:
    if not is_supabase_configured():
        return []
    client = get_supabase_client()
    if client is None:
        return []
    res = client.table("concepts").select("concept_id, concept_name, chapter, subject").execute()
    return res.data or []


def _read_concept_state_map(user) -> Dict[str, Dict[str, Any]]:
    if not is_supabase_configured() or not user.supabase_user_id:
        return {}
    client = get_supabase_client()
    if client is None:
        return {}
    res = (
        client.table("user_concept_state")
        .select("concept_id, proficiency_score, is_cold_start")
        .eq("user_id", str(user.supabase_user_id))
        .execute()
    )
    return {
        row["concept_id"]: {
            "score": float(row.get("proficiency_score", 0.5)),
            "is_cold_start": bool(row.get("is_cold_start", True)),
        }
        for row in (res.data or [])
    }


def _read_proficiency_map(user) -> Dict[str, float]:
    if not is_supabase_configured() or not user.supabase_user_id:
        return {}
    client = get_supabase_client()
    if client is None:
        return {}
    res = (
        client.table("user_concept_state")
        .select("concept_id, proficiency_score, flagged_weak, is_cold_start")
        .eq("user_id", str(user.supabase_user_id))
        .execute()
    )
    return {
        row["concept_id"]: float(row.get("proficiency_score", 0.5))
        for row in (res.data or [])
    }


def _chapter_depth(
    placement: Optional[SyllabusPlacement],
    chapter: str,
) -> Optional[str]:
    if placement is None:
        return None
    return (placement.self_assessed_coverage or {}).get(chapter)


def _classify_node(
    concept_id: str,
    chapter: str,
    proficiency: float,
    placement: Optional[SyllabusPlacement],
    mastery_threshold: int,
) -> Tuple[str, str]:
    """
    Return (node_type, status).
    """
    depth = _chapter_depth(placement, chapter)
    mastery = mastery_threshold / 100.0

    if proficiency >= mastery:
        return NodeType.MASTERED, NodeStatus.SKIPPED

    if placement and placement.journey_type == JourneyType.MID_JOURNEY:
        baseline = placement.diagnostic_baseline or {}
        concept_scores = baseline.get("concept_scores") or {}
        if concept_id in concept_scores and float(concept_scores[concept_id]) >= mastery:
            return NodeType.MASTERED, NodeStatus.SKIPPED
        if depth == "strong" and proficiency >= 0.6:
            return NodeType.MASTERED, NodeStatus.SKIPPED
        if depth == "moderate":
            return NodeType.REVISE, NodeStatus.PENDING
        if depth == "barely":
            return NodeType.LEARN, NodeStatus.PENDING

    if placement and placement.journey_type == JourneyType.REVISION_DROPPER:
        baseline = placement.diagnostic_baseline or {}
        concept_scores = baseline.get("concept_scores") or {}
        if concept_id in concept_scores and float(concept_scores[concept_id]) >= mastery:
            return NodeType.MASTERED, NodeStatus.SKIPPED
        if proficiency < 0.45:
            return NodeType.REVISE, NodeStatus.PENDING

    return NodeType.LEARN, NodeStatus.PENDING


def topological_sort(concept_ids: List[str], prereqs: Dict[str, List[str]]) -> List[str]:
    valid = set(concept_ids)
    in_degree = {cid: 0 for cid in concept_ids}
    adjacency: Dict[str, List[str]] = {cid: [] for cid in concept_ids}

    for cid in concept_ids:
        for prereq in prereqs.get(cid, []):
            if prereq not in valid:
                continue
            adjacency[prereq].append(cid)
            in_degree[cid] += 1

    queue = deque(sorted([cid for cid, deg in in_degree.items() if deg == 0]))
    ordered: List[str] = []

    while queue:
        current = queue.popleft()
        ordered.append(current)
        for nxt in sorted(adjacency.get(current, [])):
            in_degree[nxt] -= 1
            if in_degree[nxt] == 0:
                queue.append(nxt)

    if len(ordered) != len(concept_ids):
        remaining = [cid for cid in concept_ids if cid not in ordered]
        ordered.extend(sorted(remaining))

    return ordered


def _merge_concepts(live_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    spec_map = syllabus_concept_map()
    chapter_orders = chapter_order_map()
    merged: List[Dict[str, Any]] = []

    for row in live_rows:
        concept_id = row["concept_id"]
        spec = spec_map.get(concept_id, {})
        chapter = row.get("chapter") or spec.get("chapter") or "Physics"
        merged.append(
            {
                "concept_id": concept_id,
                "concept_name": row.get("concept_name") or spec.get("name") or concept_id,
                "chapter": chapter,
                "chapter_order": spec.get("chapter_order", chapter_orders.get(chapter, 99)),
                "prerequisites": spec.get("prerequisites") or [],
                "exam_weight": spec.get("exam_weight", "medium"),
                "content_sequence": spec.get("content_sequence", ["theory", "example", "practice", "pyq"]),
                "mastery_threshold": spec.get("mastery_threshold", 75),
                "estimated_minutes": spec.get("estimated_minutes", 12),
            }
        )

    merged.sort(key=lambda item: (item["chapter_order"], item["chapter"], item["concept_id"]))
    return merged


def _estimate_weeks(active_nodes: int, daily_minutes: int, avg_minutes: int = 12) -> int:
    if daily_minutes <= 0:
        daily_minutes = 45
    concepts_per_day = max(1, daily_minutes // max(avg_minutes, 8))
    return max(1, round(active_nodes / (concepts_per_day * 5)))


@transaction.atomic
def generate_learning_path(user, *, subject: str = "Physics", force: bool = False) -> LearningPath:
    profile = getattr(user, "student_profile", None)
    placement = getattr(user, "syllabus_placement", None)
    daily_goal = getattr(profile, "daily_goal_minutes", 45) or 45

    existing = (
        LearningPath.objects.filter(user=user, subject=subject, is_active=True)
        .order_by("-updated_at")
        .first()
    )
    if existing and not force:
        return existing

    if existing:
        existing.is_active = False
        existing.save(update_fields=["is_active", "updated_at"])

    live_rows = _read_live_concepts()
    if not live_rows:
        raise ValueError("No concepts available to build a roadmap.")

    merged = _merge_concepts(live_rows)
    concept_ids = [item["concept_id"] for item in merged]
    prereqs = prerequisite_map()
    ordered_ids = topological_sort(concept_ids, prereqs)
    order_lookup = {cid: idx for idx, cid in enumerate(ordered_ids)}
    merged.sort(key=lambda item: order_lookup.get(item["concept_id"], 999))

    proficiency_map = _read_proficiency_map(user)

    path = LearningPath.objects.create(
        user=user,
        subject=subject,
        daily_goal_minutes=daily_goal,
    )

    nodes: List[PathNode] = []
    active_count = 0
    first_active_assigned = False

    for index, item in enumerate(merged):
        concept_id = item["concept_id"]
        proficiency = proficiency_map.get(concept_id, 0.5)
        node_type, status = _classify_node(
            concept_id,
            item["chapter"],
            proficiency,
            placement,
            int(item["mastery_threshold"]),
        )

        if status != NodeStatus.SKIPPED:
            active_count += 1
            if not first_active_assigned:
                status = NodeStatus.IN_PROGRESS
                first_active_assigned = True

        nodes.append(
            PathNode(
                learning_path=path,
                sequence_index=index,
                concept_id=concept_id,
                concept_name=item["concept_name"],
                chapter=item["chapter"],
                node_type=node_type,
                exam_weight=item["exam_weight"],
                content_sequence=item["content_sequence"],
                mastery_threshold=item["mastery_threshold"],
                estimated_minutes=item["estimated_minutes"],
                proficiency_pct=round(proficiency * 100),
                status=status,
                started_at=timezone.now() if status == NodeStatus.IN_PROGRESS else None,
            )
        )

    PathNode.objects.bulk_create(nodes)

    path.total_nodes = len(nodes)
    path.active_nodes = active_count
    path.estimated_weeks = _estimate_weeks(active_count, daily_goal)
    path.save(update_fields=["total_nodes", "active_nodes", "estimated_weeks", "updated_at"])
    return path


def get_active_learning_path(user, subject: str = "Physics") -> Optional[LearningPath]:
    return (
        LearningPath.objects.filter(user=user, subject=subject, is_active=True)
        .prefetch_related("nodes")
        .order_by("-updated_at")
        .first()
    )


def get_or_generate_learning_path(user, subject: str = "Physics") -> LearningPath:
    path = get_active_learning_path(user, subject=subject)
    if path:
        return path
    return generate_learning_path(user, subject=subject)


def get_next_nodes(path: LearningPath, limit: int = 3) -> List[PathNode]:
    in_progress = path.nodes.filter(status=NodeStatus.IN_PROGRESS).order_by("sequence_index")
    if in_progress.exists():
        first = in_progress.first()
        remaining = path.nodes.filter(
            status=NodeStatus.PENDING,
            sequence_index__gt=first.sequence_index,
        ).order_by("sequence_index")[: max(0, limit - 1)]
        return [first, *list(remaining)]

    pending = path.nodes.filter(status=NodeStatus.PENDING).order_by("sequence_index")[:limit]
    return list(pending)
