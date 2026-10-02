"""Personal roadmap generator — Phase 2."""

from __future__ import annotations

import heapq
from typing import Any, Dict, List, Optional, Tuple

from django.db import transaction
from django.utils import timezone

from roadmap.models import LearningPath, NodeStatus, NodeType, PathNode
from roadmap.syllabus import chapter_order_map, prerequisite_map, syllabus_concept_map
from users.models import JourneyType, StudentProfile, SyllabusPlacement
from users.supabase_sync import get_supabase_client, is_supabase_configured


def _read_live_concepts(subject: str = "Physics") -> List[Dict[str, Any]]:
    if not is_supabase_configured():
        return []
    client = get_supabase_client()
    if client is None:
        return []
    res = (
        client.table("concepts")
        .select("concept_id, concept_name, chapter, subject")
        .eq("subject", subject)
        .execute()
    )
    return res.data or []


def live_concept_ids(subject: str = "Physics") -> set:
    """concept_ids the tutor can actually teach right now, for this subject.

    Used to mark roadmap nodes teachable-or-not (see
    PathNodeSerializer.get_content_ready).

    Deliberately keyed on the `content` table, not `concepts`: a concept row
    on its own teaches nobody. Syllabus content arrives incrementally — a
    concept can be registered before its theory/examples/questions are
    authored — and gating on `concepts` alone would flip a node to "ready"
    at that moment, handing the student a button that opens on an empty
    retrieval. Gating on real content means the roadmap only promises what
    the tutor can deliver.

    Returns an empty set when Supabase is unreachable/unconfigured, which
    the serializer shows as "not ready" — conservative on purpose.
    """
    concept_ids = {row["concept_id"] for row in _read_live_concepts(subject)}
    if not concept_ids:
        return set()

    client = get_supabase_client()
    if client is None:
        return set()
    try:
        res = (
            client.table("content")
            .select("primary_concept_id")
            .in_("primary_concept_id", list(concept_ids))
            .execute()
        )
    except Exception:
        # Never fail a roadmap render over this — fall back to "concept row
        # exists", the previous behaviour.
        return concept_ids
    return {
        row["primary_concept_id"]
        for row in (res.data or [])
        if row.get("primary_concept_id")
    }


def _syllabus_concepts_fallback(subject: str = "Physics") -> List[Dict[str, Any]]:
    """Build concept rows from the canonical syllabus spec.

    Used when Supabase `concepts` is empty/unreachable for this subject (true
    today for every subject except Physics — the knowledge graph was only ever
    seeded with Physics content) so the roadmap can still be generated from
    the YAML source of truth instead of failing hard.
    """
    rows: List[Dict[str, Any]] = []
    for concept_id, spec in syllabus_concept_map(subject).items():
        rows.append(
            {
                "concept_id": concept_id,
                "concept_name": spec.get("name") or concept_id,
                "chapter": spec.get("chapter") or subject,
                "subject": spec.get("subject") or subject,
            }
        )
    return rows


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


def topological_sort(
    concept_ids: List[str],
    prereqs: Dict[str, List[str]],
    priority: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Order concepts so every prerequisite precedes its dependents.

    `priority` breaks ties between concepts that are *all* currently
    unblocked — pass {concept_id: sort_key} to teach in syllabus order
    (chapter 1 before chapter 7). Without it, ties break alphabetically by
    concept_id, which scatters chapters: a 16-chapter Chemistry path would
    open on "Acid-Base Concepts" purely because 'a' sorts early.

    Ties are resolved with a heap rather than a FIFO queue, so a
    just-unblocked chapter-1 concept is picked ahead of an already-queued
    chapter-7 one instead of waiting behind it.
    """
    valid = set(concept_ids)
    in_degree = {cid: 0 for cid in concept_ids}
    adjacency: Dict[str, List[str]] = {cid: [] for cid in concept_ids}

    for cid in concept_ids:
        for prereq in prereqs.get(cid, []):
            if prereq not in valid:
                continue
            adjacency[prereq].append(cid)
            in_degree[cid] += 1

    def key(cid: str):
        # (caller's ordering, concept_id) — the id keeps it deterministic
        # when two concepts share a priority.
        return ((priority or {}).get(cid, 0), cid)

    heap = [key(cid) for cid, deg in in_degree.items() if deg == 0]
    heapq.heapify(heap)
    ordered: List[str] = []

    while heap:
        _, current = heapq.heappop(heap)
        ordered.append(current)
        for nxt in adjacency.get(current, []):
            in_degree[nxt] -= 1
            if in_degree[nxt] == 0:
                heapq.heappush(heap, key(nxt))

    if len(ordered) != len(concept_ids):
        # Cycle (or ids referenced but absent) — append the stragglers in
        # priority order rather than dropping them from the roadmap.
        seen = set(ordered)
        remaining = sorted((cid for cid in concept_ids if cid not in seen), key=key)
        ordered.extend(remaining)

    return ordered


def _path_concept_rows(subject: str = "Physics") -> List[Dict[str, Any]]:
    """Rows that belong on the student path.

    The path is the JEE syllabus YAML. Live knowledge-graph rows overlay
    names for matching concept_ids so seeded content wins on naming.
    Extra live concepts (textbook dumps outside the syllabus) stay out of
    the path — they must not inflate the study plan into a thousand-node
    dump. Chat can still retrieve them if the student asks.
    """
    spec_rows = _syllabus_concepts_fallback(subject)
    live_by_id = {row["concept_id"]: row for row in _read_live_concepts(subject)}
    if spec_rows:
        rows: List[Dict[str, Any]] = []
        for row in spec_rows:
            live = live_by_id.get(row["concept_id"])
            if not live:
                rows.append(row)
                continue
            rows.append(
                {
                    **row,
                    "concept_name": live.get("concept_name") or row.get("concept_name"),
                }
            )
        return rows
    return list(live_by_id.values())


def _merge_concepts(live_rows: List[Dict[str, Any]], subject: str = "Physics") -> List[Dict[str, Any]]:
    spec_map = syllabus_concept_map(subject)
    chapter_orders = chapter_order_map(subject)
    merged: List[Dict[str, Any]] = []

    for row in live_rows:
        concept_id = row["concept_id"]
        spec = spec_map.get(concept_id, {})
        chapter = spec.get("chapter") or row.get("chapter") or subject
        merged.append(
            {
                "concept_id": concept_id,
                "concept_name": row.get("concept_name") or spec.get("name") or concept_id,
                "chapter": chapter,
                "chapter_order": spec.get("chapter_order", chapter_orders.get(chapter, 99)),
                "prerequisites": spec.get("prerequisites") or [],
                "exam_weight": spec.get("exam_weight", "medium"),
                "content_sequence": spec.get("content_sequence", ["theory", "example", "practice", "pyq"]),
                "mastery_threshold": spec.get("mastery_threshold", 80),
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

    # YAML is the path (all JEE chapters). Live KG rows overlay matching
    # ids so seeded names win. They used to be unioned, which pulled every
    # extra textbook concept into the student plan.
    live_rows = _path_concept_rows(subject)
    if not live_rows:
        raise ValueError("No concepts available to build a roadmap.")

    merged = _merge_concepts(live_rows, subject)
    concept_ids = [item["concept_id"] for item in merged]
    prereqs = prerequisite_map(subject)
    # _merge_concepts already sorted by (chapter_order, chapter, concept_id),
    # so its index is exactly "syllabus order" — use it to break ties so the
    # path opens on chapter 1 rather than whatever sorts first alphabetically.
    syllabus_order = {item["concept_id"]: i for i, item in enumerate(merged)}
    ordered_ids = topological_sort(concept_ids, prereqs, priority=syllabus_order)
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


_STAGE_WORDS = {
    "theory": "theory",
    "example": "a worked example",
    "practice": "practice",
    "pyq": "a PYQ",
}


def _action_for(node: Any) -> str:
    node_type = str(getattr(node, "node_type", "") or "").upper()
    sequence = list(getattr(node, "content_sequence", None) or ["theory", "example", "practice"])
    words = [_STAGE_WORDS.get(str(stage).lower(), str(stage)) for stage in sequence[:3]]
    path = " → ".join(words) if words else "theory → a worked example"
    if node_type == NodeType.REVISE:
        return "Skip a full theory pass. Do a worked example, then a PYQ."
    return f"Complete {path}. Go deeper only if you want more."


def compose_study_plan(
    nodes: List[Any],
    *,
    subject: str = "Physics",
    daily_goal_minutes: int = 45,
    week_limit: int = 5,
) -> Dict[str, Any]:
    """Narrow Planly-style plan from the full generated path.

    The generator still stores every syllabus node. This view tells the student
    what to follow *this week* and hides the rest behind chapter explore.
    """
    ordered = sorted(nodes, key=lambda n: int(getattr(n, "sequence_index", 0) or 0))
    open_nodes = [
        n
        for n in ordered
        if str(getattr(n, "status", "")) not in {NodeStatus.SKIPPED, NodeStatus.COMPLETED}
    ]
    current = next(
        (n for n in open_nodes if str(getattr(n, "status", "")) == NodeStatus.IN_PROGRESS),
        None,
    ) or (open_nodes[0] if open_nodes else None)

    limit = max(3, min(week_limit, max(3, (daily_goal_minutes or 45) // 12)))
    if current is None:
        this_week_nodes = []
    else:
        current_id = str(getattr(current, "id"))
        start = next(
            (i for i, n in enumerate(open_nodes) if str(getattr(n, "id")) == current_id),
            0,
        )
        this_week_nodes = open_nodes[start : start + limit]
    this_week = [
        {
            "node_id": str(getattr(n, "id")),
            "action": _action_for(n),
        }
        for n in this_week_nodes
    ]

    week_ids = {str(getattr(n, "id")) for n in this_week_nodes}
    last_seq = max(
        (int(getattr(n, "sequence_index", 0) or 0) for n in this_week_nodes),
        default=-1,
    )
    later_counts: Dict[str, Dict[str, int]] = {}
    for n in open_nodes:
        if str(getattr(n, "id")) in week_ids:
            continue
        if int(getattr(n, "sequence_index", 0) or 0) <= last_seq:
            continue
        chapter = getattr(n, "chapter", None) or subject
        bucket = later_counts.setdefault(chapter, {"remaining": 0, "minutes": 0})
        bucket["remaining"] += 1
        bucket["minutes"] += int(getattr(n, "estimated_minutes", 0) or 0)
    later_all = [
        {"chapter": chapter, "remaining": counts["remaining"], "minutes": counts["minutes"]}
        for chapter, counts in later_counts.items()
    ]
    later_cap = 14
    later = later_all[:later_cap]
    later_more = max(0, len(later_all) - later_cap)

    if current is None:
        headline = f"{subject} path complete"
        why = "Every concept on this path is done or skipped. Open a chapter below to review."
    else:
        week_chapters = []
        for n in this_week_nodes:
            ch = getattr(n, "chapter", "") or subject
            if ch not in week_chapters:
                week_chapters.append(ch)
        if len(week_chapters) == 1:
            headline = f"This week: {week_chapters[0]}"
        elif week_chapters:
            headline = f"This week: {week_chapters[0]}, then {week_chapters[1]}"
        else:
            headline = f"This week on {subject}"
        why = (
            f"Follow this order. Prerequisites come first, so do not skip ahead. "
            f"Today start with {getattr(current, 'concept_name', 'the next concept')}."
        )

    return {
        "headline": headline,
        "why": why,
        "today_node_id": str(getattr(current, "id")) if current is not None else None,
        "this_week": this_week,
        "later": later,
        "later_more": later_more,
    }
