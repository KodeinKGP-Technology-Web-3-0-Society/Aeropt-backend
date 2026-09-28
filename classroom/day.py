"""Home overlay: stored specialist rows win. Missing rows are filled once."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from django.utils import timezone

from apis.models import Concept
from classroom.agent_client import call_specialist
from classroom.models import ConceptTracker, EvidenceEvent, TodayDecision

Call = Callable[[str, Dict[str, Any]], Optional[Dict[str, Any]]]

_MISSING = object()
_SPECIALISTS = {
    "plan": "planning",
    "today": "daily",
    "revise": "revision",
    "readiness": "readiness-agent",
}


def overlay_specialists(
    user,
    provisional: Dict[str, Any],
    call: Optional[Call] = None,
) -> Dict[str, Any]:
    """Return the home payload. Map stays the tracker view in `provisional`."""
    caller = call or call_specialist
    for_date = timezone.localdate()
    for_date_text = for_date.isoformat()
    skip = list(
        TodayDecision.objects.filter(user=user, for_date=for_date).values_list(
            "concept_id", flat=True
        )
    )
    body = _learner_body(user, provisional, for_date_text, skip)

    plan = _stored_plan(user)
    if plan is _MISSING:
        plan = _fill_plan(user, caller, body, provisional["plan"])

    revise = _stored_revise(user)
    if revise is _MISSING:
        revise = _fill_revise(user, caller, body, provisional["revise"])

    readiness = _stored_readiness(user)
    if readiness is _MISSING:
        readiness = _fill_readiness(user, caller, body, provisional["readiness"])

    today = _stored_today(user, for_date_text, set(skip))
    if today is _MISSING:
        today = _fill_today(user, caller, body, provisional["today"], for_date_text, set(skip))

    return {
        "today": None if today is _MISSING else today,
        "plan": plan if isinstance(plan, list) else provisional["plan"],
        "map": provisional["map"],
        "revise": revise if isinstance(revise, list) else provisional["revise"],
        "readiness": readiness if isinstance(readiness, dict) else provisional["readiness"],
        # New dashboard fields — passed through from provisional, never overridden by specialists
        "streak": provisional.get("streak", {"current_streak": 0, "week": []}),
        "insights": provisional.get("insights", []),
        "subject_mastery": provisional.get("subject_mastery", []),
    }


def record_today_decision(user, concept_id: str, status: str) -> None:
    TodayDecision.objects.update_or_create(
        user=user,
        concept_id=concept_id,
        for_date=timezone.localdate(),
        defaults={"status": status},
    )


def _learner_body(user, provisional, for_date: str, skip: List[str]) -> Dict[str, Any]:
    return {
        "for_date": for_date,
        "skip_concept_ids": skip,
        "home": provisional,
        "catalog": _catalog(),
        "trackers": _trackers(user),
    }


def _catalog() -> List[Dict[str, str]]:
    rows = (
        Concept.objects.filter(chapter__subject__name="Physics")
        .select_related("chapter")
        .order_by("chapter__order_index", "order_index", "id")
    )
    catalog = []
    for concept in rows:
        concept_id = (concept.slug or "").strip() or str(concept.id)
        title = (concept.name or "").strip()
        if not concept_id or not title:
            continue
        catalog.append(
            {
                "concept_id": concept_id,
                "title": title,
                "chapter": concept.chapter.name if concept.chapter_id else "",
            }
        )
    return catalog


def _trackers(user) -> List[Dict[str, Any]]:
    return [
        {
            "concept_id": row.concept_id,
            "title": row.title,
            "chapter": row.chapter,
            "mastery": int(row.mastery),
            "attempts": int(row.attempts),
            "flagged_weak": bool(row.flagged_weak),
        }
        for row in ConceptTracker.objects.filter(user=user).order_by("concept_id")
    ]


def _store(user, kind: str, payload: Any, concept_id: str = "") -> None:
    EvidenceEvent.objects.create(
        user=user,
        concept_id=concept_id,
        surface="home",
        specialist=_SPECIALISTS[kind],
        kind=kind,
        payload=payload,
    )


def _latest(user, kind: str):
    return (
        EvidenceEvent.objects.filter(user=user, kind=kind).order_by("-created_at", "-id").first()
    )


def _stored_plan(user):
    row = _latest(user, "plan")
    if row is None:
        return _MISSING
    return _plan_list(row.payload)


def _stored_revise(user):
    row = _latest(user, "revise")
    if row is None:
        return _MISSING
    return _revise_list(row.payload)


def _stored_readiness(user):
    row = _latest(user, "readiness")
    if row is None:
        return _MISSING
    parsed = _readiness(row.payload)
    return parsed if parsed is not None else _MISSING


def _stored_today(user, for_date: str, skip: set):
    row = (
        EvidenceEvent.objects.filter(user=user, kind="today", payload__for_date=for_date)
        .order_by("-created_at", "-id")
        .first()
    )
    if row is None:
        return _MISSING
    block = _today_block(row.payload, for_date)
    if block is None:
        return _MISSING
    if block.get("empty"):
        return None
    if block["concept_id"] in skip:
        return _MISSING
    return block


def _fill_plan(user, caller: Call, body, fallback):
    filled = caller("plan", body)
    if filled is None:
        return fallback
    plan = _plan_list(filled.get("plan"))
    # An empty agent plan means the planning agent hasn't generated one yet;
    # use the provisional (learning-path-derived) plan instead of overwriting with [].
    if plan is None or not plan:
        return fallback
    _store(user, "plan", plan)
    return plan


def _fill_revise(user, caller: Call, body, fallback):
    filled = caller("revise", body)
    if filled is None:
        return fallback
    revise = _revise_list(filled.get("revise"))
    if revise is None:
        return fallback
    _store(user, "revise", revise)
    return revise


def _fill_readiness(user, caller: Call, body, fallback):
    filled = caller("readiness", body)
    if filled is None:
        return fallback
    readiness = _readiness(filled.get("readiness"))
    if readiness is None:
        return fallback
    _store(user, "readiness", readiness)
    return readiness


def _fill_today(user, caller: Call, body, fallback, for_date: str, skip: set):
    filled = caller("daily", body)
    if filled is None:
        if isinstance(fallback, dict) and fallback.get("concept_id") not in skip:
            return {**fallback, "provisional": True}
        return None
    raw = filled.get("today")
    if not isinstance(raw, dict):
        _store(user, "today", {"for_date": for_date, "concept_id": ""})
        return None
    block = _today_block({**raw, "for_date": for_date}, for_date)
    if block is None or block.get("empty") or block["concept_id"] in skip:
        _store(user, "today", {"for_date": for_date, "concept_id": ""})
        return None
    _store(user, "today", {**block, "for_date": for_date}, concept_id=block["concept_id"])
    return block


def _plan_list(payload: Any) -> Optional[List[Dict[str, str]]]:
    rows = payload
    if isinstance(payload, dict):
        rows = payload.get("plan")
    if not isinstance(rows, list):
        return None
    plan = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        concept_id = str(row.get("concept_id") or "").strip()
        title = str(row.get("title") or "").strip()
        if not concept_id or not title:
            continue
        plan.append(
            {
                "concept_id": concept_id,
                "title": title,
                "status": str(row.get("status") or "pending"),
                "when": str(row.get("when") or "this_week"),
            }
        )
    return plan


def _revise_list(payload: Any) -> Optional[List[Dict[str, str]]]:
    rows = payload
    if isinstance(payload, dict):
        rows = payload.get("revise")
    if not isinstance(rows, list):
        return None
    revise = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        concept_id = str(row.get("concept_id") or "").strip()
        title = str(row.get("title") or "").strip()
        if not concept_id or not title:
            continue
        due = str(row.get("due") or "this_week")
        revise.append({"concept_id": concept_id, "title": title, "due": due})
    return revise


def _readiness(payload: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return None
    try:
        score = int(payload.get("score"))
    except (TypeError, ValueError):
        return None
    score = max(0, min(100, score))
    label = str(payload.get("label") or "").strip().lower()
    if label not in ("early", "building", "ready"):
        return None
    return {"score": score, "label": label}


def _today_block(payload: Any, for_date: str) -> Optional[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return None
    if str(payload.get("for_date") or "") != for_date:
        return None
    concept_id = str(payload.get("concept_id") or "").strip()
    if not concept_id:
        return {"empty": True}
    action = str(payload.get("action") or "lesson")
    if action not in ("lesson", "revise", "assess"):
        action = "lesson"
    title = str(payload.get("title") or concept_id).strip() or concept_id
    try:
        minutes = int(payload.get("minutes") or 25)
    except (TypeError, ValueError):
        minutes = 25
    return {
        "concept_id": concept_id,
        "title": title,
        "action": action,
        "minutes": minutes,
    }
