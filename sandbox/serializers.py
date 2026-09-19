"""Serializers for the sandbox action queue and its mutations.

These exist so `/api/schema/` describes the queue endpoints instead of showing
an untyped object — the queue itself is computed, not a model, so the read
serializers are plain `Serializer`s that document the orchestrator's output.
"""

from __future__ import annotations

from rest_framework import serializers

from sandbox.models import SandboxActionEvent, SandboxActionStatus


class SandboxQueueItemSerializer(serializers.Serializer):
    id = serializers.CharField()
    action = serializers.CharField()
    concept_id = serializers.CharField()
    concept_name = serializers.CharField()
    chapter = serializers.CharField(allow_null=True, required=False)
    roadmap_node_id = serializers.CharField(allow_null=True, required=False)
    duration_min = serializers.IntegerField()
    proficiency_pct = serializers.IntegerField(allow_null=True, required=False)
    reason = serializers.CharField()
    priority = serializers.IntegerField()


class SandboxQueueSerializer(serializers.Serializer):
    queue = SandboxQueueItemSerializer(many=True)
    count = serializers.IntegerField()
    daily_goal_minutes = serializers.IntegerField()
    preferred_depth = serializers.CharField()
    queue_target_minutes = serializers.IntegerField()
    completed_today = serializers.IntegerField()
    dismissed_today = serializers.IntegerField()


class SandboxActionEventRequestSerializer(serializers.Serializer):
    """Optional context the client may echo back so the event stays readable."""

    action = serializers.CharField(max_length=32, required=False, allow_blank=True)
    concept_id = serializers.CharField(max_length=128, required=False, allow_blank=True)
    roadmap_node_id = serializers.CharField(max_length=64, required=False, allow_blank=True)


class SandboxActionEventSerializer(serializers.ModelSerializer):
    status = serializers.ChoiceField(choices=SandboxActionStatus.choices, read_only=True)

    class Meta:
        model = SandboxActionEvent
        fields = (
            "action_id",
            "target_key",
            "status",
            "for_date",
            "action",
            "concept_id",
            "roadmap_node_id",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class SandboxActionResultSerializer(serializers.Serializer):
    """What complete/dismiss return: the recorded event plus the fresh queue."""

    event = SandboxActionEventSerializer()
    already_recorded = serializers.BooleanField()
    queue = SandboxQueueSerializer()


class SandboxReadinessComponentsSerializer(serializers.Serializer):
    concept_mastery = serializers.IntegerField()
    prerequisite_health = serializers.IntegerField()
    pyq_performance = serializers.IntegerField()
    mock_performance = serializers.IntegerField()
    consistency = serializers.IntegerField()


class SandboxReadinessSerializer(serializers.Serializer):
    overall = serializers.IntegerField()
    target_exam = serializers.CharField()
    components = SandboxReadinessComponentsSerializer()
    concepts_tracked = serializers.IntegerField()
    graduation_state = serializers.CharField()
