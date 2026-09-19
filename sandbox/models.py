"""Sandbox persistence — only the student's decisions about the queue.

`sandbox.orchestrator.build_action_queue` recomputes the whole queue from
roadmap state on every read, so there is no row per action to mutate. The one
thing that cannot be recomputed is what the student *did* with a card, so that
is all this model stores: one row per (user, action id, day).
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


# `build_action_queue` prefixes a card's id with its position in today's queue
# ("focus-" for the one in progress, "next-" for the ones behind it). That
# position moves as the student works through the queue, so the prefix is not
# part of the card's identity — strip it before recording a decision, or a card
# completed as `next-<node>` reappears tomorrow-morning-fresh as `focus-<node>`.
QUEUE_POSITION_PREFIXES = ("focus-", "next-")


def canonical_action_key(action_id: str) -> str:
    """Identity of a queue card, independent of where it sits in the queue."""
    for prefix in QUEUE_POSITION_PREFIXES:
        if action_id.startswith(prefix):
            return action_id[len(prefix):]
    return action_id


class SandboxActionStatus(models.TextChoices):
    COMPLETED = "completed", "Completed"
    DISMISSED = "dismissed", "Dismissed"


class SandboxActionEvent(models.Model):
    """A student's decision about one computed queue card, scoped to one day.

    `action_id` is the id `build_action_queue` puts on the card
    (``focus-<node uuid>``, ``next-<node uuid>``, ``practice-slice``). Those ids
    are derived from roadmap node ids, so they are stable for as long as the
    node is, which is exactly the lifetime a decision needs to survive — but the
    position prefix is not, hence `target_key`.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sandbox_action_events",
    )
    # As posted by the client, kept verbatim for traceability.
    action_id = models.CharField(max_length=128)
    # `canonical_action_key(action_id)` — what uniqueness and filtering key on.
    target_key = models.CharField(max_length=128)
    status = models.CharField(
        max_length=16,
        choices=SandboxActionStatus.choices,
    )
    for_date = models.DateField(default=timezone.localdate)

    # Context snapshot, so an event is still readable after the roadmap moves on.
    action = models.CharField(max_length=32, blank=True, default="")
    concept_id = models.CharField(max_length=128, blank=True, default="")
    roadmap_node_id = models.CharField(max_length=64, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "sandbox_action_events"
        ordering = ("-updated_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["user", "target_key", "for_date"],
                name="uniq_sandbox_action_per_user_day",
            )
        ]
        indexes = [
            models.Index(fields=["user", "for_date"]),
        ]

    def save(self, *args, **kwargs):
        # Derive the key rather than trusting every call site to pass it.
        if not self.target_key:
            self.target_key = canonical_action_key(self.action_id)
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.user_id}:{self.action_id}:{self.status}@{self.for_date}"
