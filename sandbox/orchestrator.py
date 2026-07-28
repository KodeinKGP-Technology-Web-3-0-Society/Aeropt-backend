"""Sandbox orchestrator — proactive action queue (computed, read-only inputs)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _roadmap_current(user) -> Optional[Dict[str, Any]]:
    try:
        from roadmap.generator import get_active_learning_path
        from roadmap.models import NodeStatus

        path = get_active_learning_path(user)
        if not path:
            return None
        node = (
            path.nodes.filter(status=NodeStatus.IN_PROGRESS).order_by("sequence_index").first()
            or path.nodes.filter(status=NodeStatus.PENDING).order_by("sequence_index").first()
        )
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
        return None


def _daily_goal_minutes(user) -> int:
    profile = getattr(user, "student_profile", None)
    return int(getattr(profile, "daily_goal_minutes", None) or 45)


def _preferred_depth(user) -> str:
    profile = getattr(user, "student_profile", None)
    return str(getattr(profile, "preferred_depth", None) or "standard")


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


def build_action_queue(user) -> List[Dict[str, Any]]:
    """Build an ordered proactive queue from roadmap position (no static seed data)."""
    queue: List[Dict[str, Any]] = []
    current = _roadmap_current(user)
    if not current:
        return queue

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
        from roadmap.generator import get_active_learning_path
        from roadmap.models import NodeStatus

        path = get_active_learning_path(user)
        if path:
            next_nodes = path.nodes.filter(status=NodeStatus.PENDING).order_by("sequence_index")[:2]
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
        pass

    return _pack_queue_to_goal(queue, daily_goal)


def build_queue_meta(user) -> Dict[str, Any]:
    daily = _daily_goal_minutes(user)
    return {
        "daily_goal_minutes": daily,
        "preferred_depth": _preferred_depth(user),
        "queue_target_minutes": min(max(daily, 15), 60),
    }
