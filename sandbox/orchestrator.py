"""Sandbox orchestrator — proactive action queue (computed, read-only inputs)."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Distinguishes "caller did not load a path" from "caller already knows there is none".
_PATH_UNSET = object()


def _nodes_with_status(path, status: str):
    return sorted(
        (node for node in path.nodes.all() if node.status == status),
        key=lambda node: node.sequence_index,
    )


def _roadmap_current(user, path=_PATH_UNSET) -> Optional[Dict[str, Any]]:
    try:
        from roadmap.models import NodeStatus

        if path is _PATH_UNSET:
            from roadmap.generator import get_active_learning_path

            path = get_active_learning_path(user)
        if not path:
            return None
        in_progress = _nodes_with_status(path, NodeStatus.IN_PROGRESS)
        pending = _nodes_with_status(path, NodeStatus.PENDING)
        node = (in_progress[0] if in_progress else None) or (pending[0] if pending else None)
        if not node:
            return None
        return {
            "concept_id": node.concept_id,
            "concept_name": node.concept_name,
            "chapter": node.chapter,
            "node_type": node.node_type,
            "roadmap_node_id": str(node.id),
            "estimated_minutes": node.estimated_minutes,
            "proficiency_pct": node.proficiency_pct,
        }
    except Exception:
        logger.exception("Failed to retrieve current roadmap position for user %s", getattr(user, "pk", user))
        return None


def _daily_goal_minutes(user) -> int:
    profile = getattr(user, "student_profile", None)
    return int(getattr(profile, "daily_goal_minutes", None) or 45)


def _preferred_depth(user) -> str:
    profile = getattr(user, "student_profile", None)
    return str(getattr(profile, "preferred_depth", None) or "standard")


def _decisions_today(user) -> Dict[str, str]:
    """{canonical action key: status} for the cards acted on today.

    Returns {} on any failure — a queue that shows an extra card is a much
    smaller problem than a queue that fails to render.
    """
    try:
        from django.utils import timezone

        from sandbox.models import SandboxActionEvent

        rows = SandboxActionEvent.objects.filter(
            user=user, for_date=timezone.localdate()
        ).values_list("target_key", "status")
        return {target_key: status for target_key, status in rows}
    except Exception:
        logger.exception("Failed to read sandbox decisions for user %s", getattr(user, "pk", user))
        return {}


def _drop_decided(queue: List[Dict[str, Any]], decided: Dict[str, str]) -> List[Dict[str, Any]]:
    """Remove cards the student already acted on, keyed independently of position."""
    if not decided:
        return queue
    from sandbox.models import canonical_action_key

    return [
        item
        for item in queue
        if canonical_action_key(str(item.get("id") or "")) not in decided
    ]


def _pack_queue_to_goal(queue: List[Dict[str, Any]], daily_goal: int) -> List[Dict[str, Any]]:
    """Scale / trim / pad the queue so total minutes ≈ min(daily_goal, 60)."""
    if not queue:
        return queue

    target = min(max(daily_goal, 15), 60)
    packed = [dict(item) for item in queue]

    # Drop lowest-priority "up next" cards until focus + one next fit the budget.
    while len(packed) > 1:
        total = sum(int(item.get("duration_min") or 0) for item in packed)
        if total <= target:
            break
        drop_idx = max(range(len(packed)), key=lambda i: packed[i].get("priority", 50))
        if packed[drop_idx].get("priority", 50) <= 1:
            break
        packed.pop(drop_idx)

    total = sum(int(item.get("duration_min") or 0) for item in packed)
    if total > target and total > 0:
        scale = target / total
        for item in packed:
            raw = int(item.get("duration_min") or 8)
            item["duration_min"] = max(5, int(round(raw * scale)))

    total = sum(int(item.get("duration_min") or 0) for item in packed)
    remaining = target - total
    if remaining >= 8 and packed:
        focus = packed[0]
        packed.append(
            {
                "id": "practice-slice",
                "action": "PRACTICE",
                "concept_id": focus["concept_id"],
                "concept_name": focus["concept_name"],
                "chapter": focus.get("chapter"),
                "roadmap_node_id": focus.get("roadmap_node_id"),
                "duration_min": min(15, remaining),
                "proficiency_pct": focus.get("proficiency_pct"),
                "reason": "Extra practice block for your daily goal",
                "priority": 99,
            }
        )

    return sorted(packed, key=lambda item: item.get("priority", 50))


def build_action_queue(user, path=_PATH_UNSET) -> List[Dict[str, Any]]:
    """Build an ordered proactive queue from roadmap position (no static seed data).

    Pass `path` when the caller already loaded the active learning path.
    Omit it to load that path once. `None` means the caller already checked
    and there is no active path.
    """
    queue: List[Dict[str, Any]] = []
    if path is _PATH_UNSET:
        try:
            from roadmap.generator import get_active_learning_path

            path = get_active_learning_path(user)
        except Exception:
            logger.exception(
                "Failed to retrieve current roadmap position for user %s",
                getattr(user, "pk", user),
            )
            return queue
    current = _roadmap_current(user, path)
    if not current:
        return queue

    # Cards the student completed or dismissed today are gone for today. This is
    # read before building so the budget packer works on what is actually left.
    decided = _decisions_today(user)

    action_map = {
        "learn": "LEARN",
        "revise": "REVISE",
        "mastered": "REVISE",
    }
    primary_action = action_map.get((current.get("node_type") or "learn").lower(), "LEARN")
    daily_goal = _daily_goal_minutes(user)

    # Focus block sized from daily goal (roughly 40% of the capped budget).
    focus_budget = max(8, min(20, int(round(min(daily_goal, 60) * 0.4))))
    queue.append(
        {
            "id": f"focus-{current['roadmap_node_id']}",
            "action": primary_action,
            "concept_id": current["concept_id"],
            "concept_name": current["concept_name"],
            "chapter": current["chapter"],
            "roadmap_node_id": current["roadmap_node_id"],
            "duration_min": focus_budget,
            "proficiency_pct": current.get("proficiency_pct"),
            "reason": "Today's focus on your roadmap",
            "priority": 1,
        }
    )

    try:
        from roadmap.models import NodeStatus

        if path:
            next_nodes = _nodes_with_status(path, NodeStatus.PENDING)[:2]
            for idx, node in enumerate(next_nodes, start=2):
                queue.append(
                    {
                        "id": f"next-{node.id}",
                        "action": action_map.get((node.node_type or "learn").lower(), "LEARN"),
                        "concept_id": node.concept_id,
                        "concept_name": node.concept_name,
                        "chapter": node.chapter,
                        "roadmap_node_id": str(node.id),
                        "duration_min": max(5, min(node.estimated_minutes or 8, 12)),
                        "proficiency_pct": node.proficiency_pct,
                        "reason": "Up next on your path",
                        "priority": idx,
                    }
                )
    except Exception:
        logger.exception("Failed to retrieve next roadmap nodes for user %s", getattr(user, "pk", user))

    queue = _drop_decided(queue, decided)
    if not queue:
        return queue

    # Packing can append `practice-slice`, so filter once more afterwards.
    return _drop_decided(_pack_queue_to_goal(queue, daily_goal), decided)


def build_queue_meta(user) -> Dict[str, Any]:
    daily = _daily_goal_minutes(user)
    decided = _decisions_today(user)
    statuses = list(decided.values())
    return {
        "daily_goal_minutes": daily,
        "preferred_depth": _preferred_depth(user),
        "queue_target_minutes": min(max(daily, 15), 60),
        "completed_today": statuses.count("completed"),
        "dismissed_today": statuses.count("dismissed"),
    }
