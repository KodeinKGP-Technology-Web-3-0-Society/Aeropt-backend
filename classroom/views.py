from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from typing import Any, Dict, List, Optional
from apis.models import Concept
from roadmap.generator import get_active_learning_path
from roadmap.models import NodeStatus
from sandbox.orchestrator import build_action_queue
from sandbox.readiness import compute_readiness

_ACTION_MAP = {
    "LEARN": "lesson",
    "REVISE": "revise",
    "PRACTICE": "assess",
}

def _concept_public_id(concept) -> str:
    slug = (getattr(concept, "slug", None) or "").strip()
    return slug if slug else str(concept.id)

def _build_today(user) -> Optional[Dict[str, Any]]:
    queue = build_action_queue(user)
    if not queue:
        return None
    card = queue[0]
    return {
        "concept_id": card.get("concept_id") or "",
        "title": card.get("concept_name") or "",
        "action": _ACTION_MAP.get(str(card.get("action") or "").upper(), "lesson"),
        "minutes": int(card.get("duration_min") or 25),
    }

def _build_plan(user) -> List[Dict[str, Any]]:
    path = get_active_learning_path(user)
    if not path:
        return []

    nodes = list(path.nodes.order_by("sequence_index"))
    today_idx: Optional[int] = None
    for i, node in enumerate(nodes):
        if node.status == NodeStatus.IN_PROGRESS:
            today_idx = i
            break
    if today_idx is None:
        for i, node in enumerate(nodes):
            if node.status == NodeStatus.PENDING:
                today_idx = i
                break

    plan: List[Dict[str, Any]] = []
    for i, node in enumerate(nodes):
        when = "today" if today_idx is not None and i == today_idx else "this_week"
        plan.append(
            {
                "concept_id": node.concept_id or "",
                "title": node.concept_name or "",
                "status": node.status or "pending",
                "when": when,
            }
        )
    return plan

def _build_map(user) -> List[Dict[str, Any]]:
    path = get_active_learning_path(user)
    path_nodes = list(path.nodes.all()) if path else []
    nodes_by_id = {n.concept_id: n for n in path_nodes if n.concept_id}
    
    concepts = list(
        Concept.objects.filter(chapter__subject__name="Physics")
        .select_related("chapter")
        .order_by("chapter__order_index", "order_index", "id")
    )
    
    if not concepts:
        return [
            {
                "concept_id": node.concept_id or "",
                "title": node.concept_name or "",
                "chapter": node.chapter or "",
                "mastery": int(node.proficiency_pct or 0),
                "prereqs": [],
            }
            for node in path_nodes
        ]

    result: List[Dict[str, Any]] = []
    for concept in concepts:
        public_id = _concept_public_id(concept)
        node = nodes_by_id.get(public_id) or nodes_by_id.get(str(concept.id))
        mastery = int(node.proficiency_pct or 0) if node else 0
        
        result.append(
            {
                "concept_id": public_id,
                "title": concept.name or "",
                "chapter": concept.chapter.name if concept.chapter_id else "",
                "mastery": max(0, min(100, mastery)),
                "prereqs": [],
            }
        )
    return result

def _build_revise(user) -> List[Dict[str, Any]]:
    path = get_active_learning_path(user)
    if not path:
        return []
    
    revise = []
    for node in path.nodes.all():
        if node.status == NodeStatus.REVISE or int(node.proficiency_pct or 0) < 50:
            if not node.concept_id:
                continue
            revise.append({
                "concept_id": node.concept_id,
                "title": node.concept_name or "",
                "due": "today" if not revise else "this_week"
            })
    return revise

def _build_readiness(user) -> Dict[str, Any]:
    readiness_data = compute_readiness(user) or {}
    score = readiness_data.get("overall", 0)
    score = max(0, min(100, int(score)))
    if score < 40:
        label = "early"
    elif score < 75:
        label = "building"
    else:
        label = "ready"
    return {"score": score, "label": label}


class ClassroomHomeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({
            "today": _build_today(request.user),
            "plan": _build_plan(request.user),
            "map": _build_map(request.user),
            "revise": _build_revise(request.user),
            "readiness": _build_readiness(request.user),
        })
