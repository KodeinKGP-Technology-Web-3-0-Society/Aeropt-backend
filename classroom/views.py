from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from typing import Any, Dict, List, Optional
from apis.models import Concept
from classroom.day import overlay_specialists, record_today_decision
from classroom.models import ClassroomSession, ConceptTracker
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


def _provisional_home(user) -> Dict[str, Any]:
    return {
        "today": _build_today(user),
        "plan": _build_plan(user),
        "map": _build_map(user),
        "revise": _build_revise(user),
        "readiness": _build_readiness(user),
    }


class ClassroomHomeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(overlay_specialists(request.user, _provisional_home(request.user)))


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


class TodayDecisionView(APIView):
    """Record complete or dismiss, then return the home with that concept omitted."""

    permission_classes = [IsAuthenticated]

    def post(self, request, concept_id: str, decision: str):
        concept_id = (concept_id or "").strip()
        if decision not in ("complete", "dismiss") or not concept_id:
            return Response({"detail": "unknown today decision"}, status=400)
        record_today_decision(request.user, concept_id, decision)
        return Response(overlay_specialists(request.user, _provisional_home(request.user)))


def _session_payload(row: ClassroomSession) -> Dict[str, str]:
    return {
        "surface": row.surface,
        "concept_id": row.concept_id,
        "agent_session_id": row.agent_session_id,
        "status": row.status,
    }


def _open_session(user, surface: str, concept_id: str, agent_session_id: str) -> ClassroomSession:
    if surface == "lesson":
        existing = ClassroomSession.objects.filter(
            user=user, surface=surface, concept_id=concept_id, status=ClassroomSession.OPEN
        ).first()
    else:
        existing = ClassroomSession.objects.filter(
            user=user, surface=surface, status=ClassroomSession.OPEN
        ).first()
    if existing is not None:
        changed = []
        if concept_id and existing.concept_id != concept_id:
            existing.concept_id = concept_id
            changed.append("concept_id")
        if agent_session_id and existing.agent_session_id != agent_session_id:
            existing.agent_session_id = agent_session_id
            changed.append("agent_session_id")
        if changed:
            existing.save(update_fields=changed)
        return existing
    return ClassroomSession.objects.create(
        user=user,
        surface=surface,
        concept_id=concept_id,
        agent_session_id=agent_session_id,
        status=ClassroomSession.OPEN,
    )


class ClassroomSessionView(APIView):
    """Open or return the room for this learner. A repeat open returns the same row."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        surface = str(request.data.get("surface") or "").strip().lower()
        concept_id = str(request.data.get("concept_id") or "").strip()
        agent_session_id = str(request.data.get("agent_session_id") or "").strip()
        if surface not in ClassroomSession.SURFACES:
            return Response({"detail": "surface must be lesson, doubt, or assess"}, status=400)
        if surface == "lesson" and not concept_id:
            return Response({"detail": "concept_id is required"}, status=400)
        row = _open_session(request.user, surface, concept_id, agent_session_id)
        return Response(_session_payload(row))


class ClassroomSessionLookupView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, agent_session_id: str):
        row = ClassroomSession.objects.filter(
            user=request.user, agent_session_id=agent_session_id
        ).first()
        if row is None:
            return Response({"detail": "not found"}, status=404)
        return Response(_session_payload(row))
