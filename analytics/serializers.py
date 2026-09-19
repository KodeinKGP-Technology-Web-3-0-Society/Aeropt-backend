from rest_framework import serializers

from apis.models import Chapter, Concept, ContentItem, Subject
from analytics.models import (
    Assessment,
    AssessmentQuestion,
    ChapterProgress,
    ConceptMastery,
    DailyActivity,
    LearningGap,
    ProficiencySnapshot,
    QuestionAttempt,
    Recommendation,
    Streak,
)
from apis.serializers import ChapterSerializer, ConceptSerializer, ContentItemSerializer, SubjectSerializer












class ConceptMasterySerializer(serializers.ModelSerializer):
    concept = ConceptSerializer(read_only=True)
    concept_id = serializers.PrimaryKeyRelatedField(
        queryset=Concept.objects.all(),
        source="concept",
        write_only=True,
    )

    class Meta:
        model = ConceptMastery
        fields = (
            "user",
            "concept",
            "concept_id",
            "mastery_score",
            "status",
            "is_flagged_weak",
            "total_attempts",
            "correct_attempts",
            "last_practiced_at",
            "updated_at",
        )
        read_only_fields = ("updated_at", "user")


class ChapterProgressSerializer(serializers.ModelSerializer):
    chapter = ChapterSerializer(read_only=True)
    chapter_id = serializers.PrimaryKeyRelatedField(
        queryset=Chapter.objects.all(),
        source="chapter",
        write_only=True,
    )

    class Meta:
        model = ChapterProgress
        fields = (
            "user",
            "chapter",
            "chapter_id",
            "mastery_score",
            "completion_percent",
            "updated_at",
        )
        read_only_fields = ("updated_at", "user")


class ProficiencySnapshotSerializer(serializers.ModelSerializer):
    subject = SubjectSerializer(read_only=True)
    subject_id = serializers.PrimaryKeyRelatedField(
        queryset=Subject.objects.all(),
        source="subject",
        write_only=True,
    )

    class Meta:
        model = ProficiencySnapshot
        fields = ("user", "subject", "subject_id", "snapshot_date", "proficiency")
        read_only_fields = ("user",)


class LearningGapSerializer(serializers.ModelSerializer):
    concept = ConceptSerializer(read_only=True)
    concept_id = serializers.PrimaryKeyRelatedField(
        queryset=Concept.objects.all(),
        source="concept",
        write_only=True,
    )

    class Meta:
        model = LearningGap
        fields = (
            "id",
            "user",
            "concept",
            "concept_id",
            "severity",
            "source",
            "detected_at",
            "resolved_at",
        )
        read_only_fields = ("id", "detected_at", "user")


class RecommendationSerializer(serializers.ModelSerializer):
    concept = ConceptSerializer(read_only=True)
    content_item = ContentItemSerializer(read_only=True)
    concept_id = serializers.PrimaryKeyRelatedField(
        queryset=Concept.objects.all(),
        source="concept",
        write_only=True,
        required=False,
        allow_null=True,
    )
    content_item_id = serializers.PrimaryKeyRelatedField(
        queryset=ContentItem.objects.all(),
        source="content_item",
        write_only=True,
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Recommendation
        fields = (
            "id",
            "user",
            "type",
            "concept",
            "concept_id",
            "content_item",
            "content_item_id",
            "reason",
            "score",
            "served_at",
            "dismissed_at",
            "created_at",
        )
        read_only_fields = ("id", "created_at", "user")


class QuestionAttemptSerializer(serializers.ModelSerializer):
    content_item = ContentItemSerializer(read_only=True)
    content_item_id = serializers.PrimaryKeyRelatedField(
        queryset=ContentItem.objects.all(),
        source="content_item",
        write_only=True,
    )

    class Meta:
        model = QuestionAttempt
        fields = (
            "id",
            "user",
            "content_item",
            "content_item_id",
            "submitted_answer",
            "is_correct",
            "error_type",
            "time_taken_seconds",
            "hint_used",
            "attempt_number",
            "attempted_at",
        )
        read_only_fields = ("id", "attempted_at", "user")


class StreakSerializer(serializers.ModelSerializer):
    class Meta:
        model = Streak
        fields = (
            "user",
            "current_streak",
            "longest_streak",
            "last_active_date",
            "updated_at",
        )
        read_only_fields = ("updated_at", "user")


class DailyActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = DailyActivity
        fields = (
            "user",
            "activity_date",
            "minutes_studied",
            "questions_attempted",
            "doubts_asked",
            "goal_met",
        )
        read_only_fields = ("user",)


class AssessmentSerializer(serializers.ModelSerializer):
    chapter = ChapterSerializer(read_only=True)
    concept = ConceptSerializer(read_only=True)
    chapter_id = serializers.PrimaryKeyRelatedField(
        queryset=Chapter.objects.all(),
        source="chapter",
        write_only=True,
        required=False,
        allow_null=True,
    )
    concept_id = serializers.PrimaryKeyRelatedField(
        queryset=Concept.objects.all(),
        source="concept",
        write_only=True,
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Assessment
        fields = (
            "id",
            "user",
            "type",
            "chapter",
            "chapter_id",
            "concept",
            "concept_id",
            "total_questions",
            "score",
            "max_score",
            "status",
            "started_at",
            "completed_at",
        )
        read_only_fields = ("id", "started_at", "user")


class AssessmentQuestionSerializer(serializers.ModelSerializer):
    content_item = ContentItemSerializer(read_only=True)
    content_item_id = serializers.PrimaryKeyRelatedField(
        queryset=ContentItem.objects.all(),
        source="content_item",
        write_only=True,
    )

    class Meta:
        model = AssessmentQuestion
        fields = (
            "id",
            "assessment",
            "content_item",
            "content_item_id",
            "step_index",
            "submitted_answer",
            "is_correct",
            "error_type",
            "hint_shown",
            "retries_count",
            "is_flagged",
            "answered_at",
        )
        read_only_fields = ("id",)


# --- Chat history (read models over Supabase `sessions` / `chat_turns`) -------
# These are plain Serializers, not ModelSerializers: the agent owns these tables
# in the `public` schema and Django has no ORM model for them. They exist so
# /api/schema/ documents the shape rather than an opaque object.


class ChatHistorySessionSerializer(serializers.Serializer):
    session_id = serializers.CharField()
    session_type = serializers.CharField(allow_null=True)
    started_at = serializers.DateTimeField(allow_null=True)
    ended_at = serializers.DateTimeField(allow_null=True)
    duration_seconds = serializers.IntegerField()
    concepts_touched = serializers.ListField(child=serializers.CharField(), allow_empty=True)
    summary = serializers.CharField(allow_blank=True)
    last_decision = serializers.CharField(allow_null=True)
    turn_count = serializers.IntegerField()


class ChatHistoryListSerializer(serializers.Serializer):
    sessions = ChatHistorySessionSerializer(many=True)
    total = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    has_next = serializers.BooleanField()


class ChatHistoryTurnSerializer(serializers.Serializer):
    turn_id = serializers.CharField()
    role = serializers.CharField(allow_null=True)
    content = serializers.CharField(allow_blank=True)
    turn_index = serializers.IntegerField(allow_null=True)
    is_summarized = serializers.BooleanField()
    concepts_referenced = serializers.ListField(child=serializers.CharField(), allow_empty=True)
    agent_used = serializers.CharField(allow_null=True)
    created_at = serializers.DateTimeField(allow_null=True)
    decision = serializers.CharField(allow_null=True)
    content_ids_served = serializers.ListField(child=serializers.CharField(), allow_empty=True)
    # The agent writes these as JSON blobs, not strings.
    presentation = serializers.JSONField(allow_null=True, required=False)
    student_feedback = serializers.JSONField(allow_null=True, required=False)


class ChatHistoryDetailSerializer(serializers.Serializer):
    session_id = serializers.CharField()
    session_type = serializers.CharField(allow_null=True)
    started_at = serializers.DateTimeField(allow_null=True)
    ended_at = serializers.DateTimeField(allow_null=True)
    duration_seconds = serializers.IntegerField()
    summary = serializers.CharField(allow_blank=True)
    last_decision = serializers.CharField(allow_null=True)
    concepts_touched = serializers.ListField(child=serializers.CharField(), allow_empty=True)
    turns = ChatHistoryTurnSerializer(many=True)
