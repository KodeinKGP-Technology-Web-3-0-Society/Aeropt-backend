from django.conf import settings
from django.db import models


SURFACES = (
    "home",
    "plan",
    "map",
    "revise",
    "lesson",
    "assess",
    "doubt",
    "readiness",
)

KINDS = (
    "attempt",
    "mastery",
    "doubt",
    "handoff",
    "plan",
    "today",
    "readiness",
    "revise",
)


class ConceptTracker(models.Model):
    """One mastery row per learner per concept. This is the learner-facing score."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="concept_trackers",
    )
    concept_id = models.CharField(max_length=80)
    title = models.CharField(max_length=160)
    chapter = models.CharField(max_length=120, blank=True, default="")
    mastery = models.SmallIntegerField(default=0)
    attempts = models.PositiveIntegerField(default=0)
    correct = models.PositiveIntegerField(default=0)
    flagged_weak = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "classroom_concept_tracker"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "concept_id"],
                name="classroom_tracker_user_concept",
            ),
        ]
        indexes = [
            models.Index(fields=["concept_id"], name="classroom_tracker_concept"),
        ]

    def __str__(self):
        return f"{self.user_id}:{self.concept_id}:{self.mastery}"


class EvidenceEvent(models.Model):
    """Append-only bus. Agents post here; they do not write the tracker row themselves."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="evidence_events",
    )
    concept_id = models.CharField(max_length=80, blank=True, default="")
    surface = models.CharField(max_length=20)
    specialist = models.CharField(max_length=40, blank=True, default="")
    kind = models.CharField(max_length=20)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "classroom_evidence_event"
        ordering = ("created_at", "id")
        indexes = [
            models.Index(fields=["user", "created_at"], name="classroom_evidence_user_time"),
            models.Index(fields=["user", "kind"], name="classroom_evidence_user_kind"),
        ]

    def __str__(self):
        return f"{self.user_id}:{self.kind}:{self.concept_id}"


class TodayDecision(models.Model):
    """Complete or dismiss for one concept on one date. Home omits that concept."""

    COMPLETE = "complete"
    DISMISS = "dismiss"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="today_decisions",
    )
    concept_id = models.CharField(max_length=80)
    for_date = models.DateField()
    status = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "classroom_today_decision"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "concept_id", "for_date"],
                name="classroom_today_decision_once",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "for_date"], name="classroom_today_user_date"),
        ]

    def __str__(self):
        return f"{self.user_id}:{self.for_date}:{self.concept_id}:{self.status}"


class ClassroomSession(models.Model):
    """One open room. Lesson is unique per concept; doubt and assess, one each."""

    OPEN = "open"
    CLOSED = "closed"
    SURFACES = ("lesson", "doubt", "assess")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="classroom_sessions",
    )
    surface = models.CharField(max_length=20)
    concept_id = models.CharField(max_length=80, blank=True, default="")
    agent_session_id = models.CharField(max_length=80, blank=True, default="")
    status = models.CharField(max_length=20, default=OPEN)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "classroom_session"

    def __str__(self):
        return f"{self.user_id}:{self.surface}:{self.concept_id}:{self.status}"
