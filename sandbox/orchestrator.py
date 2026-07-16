"""Sandbox orchestrator — proactive action queue (computed, read-only inputs)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from django.contrib.auth import get_user_model

User = get_user_model()


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

    queue.append(
        {
            "id": f"focus-{current['roadmap_node_id']}",
            "action": primary_action,
            "concept_id": current["concept_id"],
            "concept_name": current["concept_name"],
            "chapter": current["chapter"],
            "roadmap_node_id": current["roadmap_node_id"],
            "duration_min": current.get("estimated_minutes", 8),
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
                        "duration_min": node.estimated_minutes,
                        "proficiency_pct": node.proficiency_pct,
                        "reason": "Up next on your path",
                        "priority": idx,
                    }
                )
    except Exception:
        pass

    profile = getattr(user, "student_profile", None)
    if profile and (profile.daily_goal_minutes or 0) >= 60:
        queue.append(
            {
                "id": "practice-slice",
                "action": "PRACTICE",
                "concept_id": current["concept_id"],
                "concept_name": current["concept_name"],
                "chapter": current.get("chapter"),
                "roadmap_node_id": current["roadmap_node_id"],
                "duration_min": 10,
                "proficiency_pct": current.get("proficiency_pct"),
                "reason": "Extra practice block for your daily goal",
                "priority": 99,
            }
        )

    return sorted(queue, key=lambda item: item.get("priority", 50))
