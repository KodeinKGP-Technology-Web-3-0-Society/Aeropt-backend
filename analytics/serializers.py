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
            "study_session",
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
