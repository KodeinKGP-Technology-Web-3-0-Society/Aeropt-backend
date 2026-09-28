from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from typing import Any, Dict, List, Optional
from apis.models import Concept
from classroom.models import ConceptTracker
from classroom.tracker import EvidenceError, apply_evidence
from roadmap.generator import get_active_learning_path
from roadmap.models import NodeStatus
from sandbox.orchestrator import build_action_queue

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

def _trackers_by_concept(user) -> Dict[str, ConceptTracker]:
    return {row.concept_id: row for row in ConceptTracker.objects.filter(user=user)}


def _tracker_mastery(trackers: Dict[str, ConceptTracker], concept_id: str) -> int:
    row = trackers.get(concept_id)
    if row is None:
        return 0
    return max(0, min(100, int(row.mastery)))


def _readiness_label(score: int) -> str:
    if score < 40:
        return "early"
    if score < 75:
        return "building"
    return "ready"


def _build_map(user) -> List[Dict[str, Any]]:
    path = get_active_learning_path(user)
    path_nodes = list(path.nodes.all()) if path else []
    trackers = _trackers_by_concept(user)

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
                "mastery": _tracker_mastery(trackers, node.concept_id or ""),
                "prereqs": [],
            }
            for node in path_nodes
            if node.concept_id
        ]

    result: List[Dict[str, Any]] = []
    for concept in concepts:
        public_id = _concept_public_id(concept)
        mastery = _tracker_mastery(trackers, public_id)
        if mastery == 0 and str(concept.id) in trackers:
            mastery = _tracker_mastery(trackers, str(concept.id))
        result.append(
            {
                "concept_id": public_id,
                "title": concept.name or "",
                "chapter": concept.chapter.name if concept.chapter_id else "",
                "mastery": mastery,
                "prereqs": [],
            }
        )
    return result

def _build_revise(user) -> List[Dict[str, Any]]:
    rows = ConceptTracker.objects.filter(user=user, flagged_weak=True).order_by(
        "updated_at", "concept_id"
    )
    revise = []
    for row in rows:
        revise.append(
            {
                "concept_id": row.concept_id,
                "title": row.title or row.concept_id,
                "due": "today" if not revise else "this_week",
            }
        )
    return revise

def _build_readiness(user) -> Dict[str, Any]:
    rows = list(ConceptTracker.objects.filter(user=user, attempts__gte=1))
    if not rows:
        return {"score": 0, "label": "early"}
    score = int(round(sum(int(row.mastery) for row in rows) / len(rows)))
    score = max(0, min(100, score))
    return {"score": score, "label": _readiness_label(score)}


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


class ClassroomEvidenceView(APIView):
    """Append one bus event. Attempt and mastery update this learner's tracker."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            event = apply_evidence(request.user, request.data)
        except EvidenceError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(
            {"id": event.id, "concept_id": event.concept_id, "kind": event.kind},
            status=201,
        )
