from datetime import date, timedelta

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from typing import Any, Dict, List, Optional
from apis.models import Concept
from classroom.day import overlay_specialists, record_today_decision
from classroom.models import ClassroomSession, ConceptTracker
from classroom.tracker import EvidenceError, apply_evidence
from roadmap.generator import get_active_learning_path, generate_learning_path
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

def _build_plan(user, limit: int = 5) -> List[Dict[str, Any]]:
    """Return only the agent-decided window (next `limit` concepts).

    Students never see all 133 nodes. The agent picks the window:
    the in-progress node + the next (limit-1) pending nodes in sequence order.
    """
    path = get_active_learning_path(user)
    if not path:
        return []

    # Only non-skipped, non-completed nodes ordered by sequence
    open_nodes = list(
        path.nodes.exclude(status__in=[NodeStatus.SKIPPED, "completed"])
        .order_by("sequence_index")
    )
    if not open_nodes:
        return []

    # Find the current node (in_progress first, then first pending)
    current_idx = next(
        (i for i, n in enumerate(open_nodes) if n.status == NodeStatus.IN_PROGRESS),
        0,
    )

    window = open_nodes[current_idx: current_idx + limit]
    remaining_after = len(open_nodes) - current_idx - len(window)

    plan: List[Dict[str, Any]] = []
    for i, node in enumerate(window):
        when = "today" if i == 0 else "this_week"
        plan.append(
            {
                "concept_id": node.concept_id or "",
                "title": node.concept_name or "",
                "status": node.status or "pending",
                "when": when,
                "chapter": node.chapter or "",
                "estimated_minutes": int(getattr(node, "estimated_minutes", 12) or 12),
            }
        )

    # Append a summary stub so the UI can show "N more concepts" without fetching all
    if remaining_after > 0:
        plan.append({
            "concept_id": "__more__",
            "title": f"{remaining_after} more concepts in your plan",
            "status": "pending",
            "when": "later",
            "chapter": "",
            "estimated_minutes": 0,
        })

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


def _build_streak(user) -> Dict[str, Any]:
    """Return current streak and which days this week had activity."""
    today = date.today()
    week_start = today - timedelta(days=today.weekday())  # Monday
    week_days = [week_start + timedelta(days=i) for i in range(7)]

    # Days with any tracker update this week
    active_dates = set(
        ConceptTracker.objects.filter(
            user=user,
            updated_at__date__gte=week_start,
            attempts__gte=1,
        ).values_list("updated_at__date", flat=True)
    )

    week_activity = [
        {"date": d.isoformat(), "active": d in active_dates, "is_today": d == today}
        for d in week_days
    ]

    # Streak: consecutive days ending today going backwards
    streak = 0
    check = today
    all_active = set(
        ConceptTracker.objects.filter(user=user, attempts__gte=1)
        .values_list("updated_at__date", flat=True)
        .distinct()
    )
    while check in all_active:
        streak += 1
        check -= timedelta(days=1)

    return {"current_streak": streak, "week": week_activity}


def _build_insights(user, map_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Rules-based insight cards — no LLM needed."""
    insights: List[Dict[str, Any]] = []

    trackers = list(ConceptTracker.objects.filter(user=user))
    weak = [t for t in trackers if t.flagged_weak]
    attempted = [t for t in trackers if t.attempts >= 1]

    # Weak concepts alert
    if weak:
        insights.append({
            "type": "weak_concepts",
            "title": f"{len(weak)} concept{'s' if len(weak) > 1 else ''} flagged as weak",
            "body": "Revise these before moving on to keep your score from dropping.",
            "action": "/home",
            "action_label": "Review Now",
            "count": len(weak),
        })

    # Chapter mastery unlock
    if map_data:
        chapters: Dict[str, List[int]] = {}
        for item in map_data:
            ch = item["chapter"]
            chapters.setdefault(ch, []).append(item["mastery"])
        for ch, scores in list(chapters.items())[:3]:
            avg = sum(scores) / len(scores) if scores else 0
            if avg >= 60:
                insights.append({
                    "type": "chapter_ready",
                    "title": f"{ch} — ready to level up",
                    "body": f"Your average mastery in {ch} is {int(avg)}%. Consider a practice test.",
                    "action": "/practice",
                    "action_label": "Practice",
                })
                break

    # Cold start nudge — no attempts yet
    if not attempted:
        insights.append({
            "type": "cold_start",
            "title": "Your learning path is ready",
            "body": "The AI has built a personalised study plan for you. Start your first session now.",
            "action": "/chat",
            "action_label": "Start Learning",
        })
    elif len(attempted) < 5:
        insights.append({
            "type": "early_progress",
            "title": f"{len(attempted)} concept{'s' if len(attempted) > 1 else ''} studied",
            "body": "Great start! Keep going — consistency beats cramming.",
            "action": "/home",
            "action_label": "Continue",
        })

    return insights[:3]


def _build_subject_mastery(user) -> List[Dict[str, Any]]:
    """Per-subject aggregated mastery for the three rings."""
    subjects = [
        {"id": "physics", "label": "Physics", "color": "physics", "active": True},
        {"id": "chemistry", "label": "Chemistry", "color": "chemistry", "active": False},
        {"id": "maths", "label": "Maths", "color": "maths", "active": False},
    ]
    trackers = list(ConceptTracker.objects.filter(user=user, attempts__gte=1))
    result = []
    for subj in subjects:
        if subj["active"]:
            relevant = trackers  # all current trackers are Physics for now
            if relevant:
                avg = int(round(sum(t.mastery for t in relevant) / len(relevant)))
                total = ConceptTracker.objects.filter(user=user).count()
                mastered = ConceptTracker.objects.filter(user=user, mastery__gte=65).count()
            else:
                avg, total, mastered = 0, 0, 0
            result.append({**subj, "mastery": avg, "total": total, "mastered": mastered})
        else:
            result.append({**subj, "mastery": 0, "total": 0, "mastered": 0, "coming_soon": True})
    return result


def _ensure_learning_path(user) -> None:
    """Auto-generate a learning path if the user has none (first visit)."""
    from roadmap.generator import get_active_learning_path, generate_learning_path
    path = get_active_learning_path(user, subject="Physics")
    if path is None:
        try:
            generate_learning_path(user, subject="Physics")
        except Exception:
            pass  # Best effort


def _provisional_home(user) -> Dict[str, Any]:
    _ensure_learning_path(user)
    map_data = _build_map(user)
    return {
        "today": _build_today(user),
        "plan": _build_plan(user),
        "map": map_data,
        "revise": _build_revise(user),
        "readiness": _build_readiness(user),
        "streak": _build_streak(user),
        "insights": _build_insights(user, map_data),
        "subject_mastery": _build_subject_mastery(user),
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

class CalendarAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        path = get_active_learning_path(request.user)
        if not path:
            return Response([])

        open_nodes = list(
            path.nodes.exclude(status__in=[NodeStatus.SKIPPED, "completed"])
            .order_by("sequence_index")[:30]
        )

        calendar_plan = []
        today = date.today()
        
        # Agentic logic: map the next 30 concepts over the next 30 days
        for i, node in enumerate(open_nodes):
            assigned_date = today + timedelta(days=i)
            calendar_plan.append({
                "date": assigned_date.isoformat(),
                "concept_id": node.concept_id or "",
                "title": node.concept_name or "",
                "chapter": node.chapter or "",
                "estimated_minutes": int(getattr(node, "estimated_minutes", 15) or 15),
            })
            
        return Response(calendar_plan)

