"""Apply evidence onto the tracker, and seed rows from an existing path once."""

from __future__ import annotations

from typing import Any, Dict, Tuple

from django.db import transaction

from classroom.models import KINDS, SURFACES, ConceptTracker, EvidenceEvent


class EvidenceError(ValueError):
    """The posted body cannot be applied. The view turns this into HTTP 400."""


def seed_from_paths(LearningPath, Tracker) -> int:
    """Copy each active path node into a tracker row that does not exist yet.

    Returns the number of rows created. Existing rows are left alone so a
    later evidence write is never overwritten by the seed.
    """
    created = 0
    paths = LearningPath.objects.filter(is_active=True).prefetch_related("nodes")
    for path in paths:
        for node in path.nodes.all():
            concept_id = (getattr(node, "concept_id", None) or "").strip()
            if not concept_id:
                continue
            mastery = _clamp(getattr(node, "proficiency_pct", 0) or 0)
            _, was_created = Tracker.objects.get_or_create(
                user_id=path.user_id,
                concept_id=concept_id,
                defaults={
                    "title": (getattr(node, "concept_name", None) or concept_id)[:160],
                    "chapter": (getattr(node, "chapter", None) or "")[:120],
                    "mastery": mastery,
                    "attempts": 0,
                    "correct": 0,
                    "flagged_weak": mastery < 50,
                },
            )
            if was_created:
                created += 1
    return created


def apply_evidence(user, body: Dict[str, Any]) -> EvidenceEvent:
    """Append one bus row. Attempt and mastery also update that user's tracker."""
    if not isinstance(body, dict):
        raise EvidenceError("evidence body must be an object")

    surface = str(body.get("surface") or "").strip()
    kind = str(body.get("kind") or "").strip()
    specialist = str(body.get("specialist") or "").strip()[:40]
    concept_id = str(body.get("concept_id") or "").strip()[:80]
    payload = body.get("payload") if body.get("payload") is not None else {}

    if surface not in SURFACES:
        raise EvidenceError("surface is not a classroom surface")
    if kind not in KINDS:
        raise EvidenceError("kind is not a classroom evidence kind")
    if not isinstance(payload, dict):
        raise EvidenceError("payload must be an object")

    mastery = _optional_mastery(payload) if kind in ("attempt", "mastery") else None
    if kind == "mastery" and mastery is None:
        raise EvidenceError("mastery payload requires mastery between 0 and 100")
    if kind == "attempt" and not isinstance(payload.get("correct"), bool):
        raise EvidenceError("attempt payload requires correct true or false")

    with transaction.atomic():
        event = EvidenceEvent.objects.create(
            user=user,
            concept_id=concept_id,
            surface=surface,
            specialist=specialist,
            kind=kind,
            payload=payload,
        )
        if kind in ("attempt", "mastery") and concept_id:
            _apply_tracker(user, concept_id, kind, payload, mastery)
    from apis.cache_layer import invalidate_user_reads

    invalidate_user_reads(user)
    return event


def _apply_tracker(user, concept_id: str, kind: str, payload: Dict[str, Any], mastery) -> None:
    tracker = (
        ConceptTracker.objects.select_for_update()
        .filter(user=user, concept_id=concept_id)
        .first()
    )
    if tracker is None:
        title, chapter = _lookup_title(user, concept_id)
        tracker = ConceptTracker.objects.create(
            user=user,
            concept_id=concept_id,
            title=title,
            chapter=chapter,
            mastery=0,
            attempts=0,
            correct=0,
            flagged_weak=True,
        )
    if kind == "attempt":
        tracker.attempts += 1
        if payload.get("correct") is True:
            tracker.correct += 1
    if mastery is not None:
        tracker.mastery = mastery
    tracker.flagged_weak = tracker.mastery < 50
    tracker.save(
        update_fields=["attempts", "correct", "mastery", "flagged_weak", "updated_at"]
    )


def _lookup_title(user, concept_id: str) -> Tuple[str, str]:
    from apis.models import Concept
    from roadmap.models import PathNode

    node = (
        PathNode.objects.filter(learning_path__user=user, concept_id=concept_id)
        .order_by("-learning_path__updated_at")
        .first()
    )
    if node is not None:
        return (node.concept_name or concept_id)[:160], (node.chapter or "")[:120]

    concept = Concept.objects.filter(slug=concept_id).select_related("chapter").first()
    if concept is not None:
        chapter = concept.chapter.name if concept.chapter_id else ""
        return (concept.name or concept_id)[:160], chapter[:120]
    return concept_id[:160], ""


def _optional_mastery(payload: Dict[str, Any]):
    if "mastery" not in payload or payload.get("mastery") is None:
        return None
    return _clamp(payload.get("mastery"))


def _clamp(value) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise EvidenceError("mastery must be an integer from 0 to 100")
    if number < 0 or number > 100:
        raise EvidenceError("mastery must be an integer from 0 to 100")
    return number
