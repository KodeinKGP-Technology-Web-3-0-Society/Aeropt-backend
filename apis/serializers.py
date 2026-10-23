from rest_framework import serializers

from apis.models import (
    Chapter,
    Concept,
    ConceptPrerequisite,
    ContentFlag,
    ContentItem,
    ContentSecondaryConcept,
    Subject,
)


class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ("id", "name", "slug", "order_index")


class ChapterSerializer(serializers.ModelSerializer):
    subject = SubjectSerializer(read_only=True)
    subject_id = serializers.PrimaryKeyRelatedField(
        queryset=Subject.objects.all(), source="subject", write_only=True
    )

    class Meta:
        model = Chapter
        fields = ("id", "subject", "subject_id", "name", "slug", "order_index")


class ConceptSerializer(serializers.ModelSerializer):
    chapter = ChapterSerializer(read_only=True)
    chapter_id = serializers.PrimaryKeyRelatedField(
        queryset=Chapter.objects.all(), source="chapter", write_only=True
    )

    class Meta:
        model = Concept
        fields = ("id", "chapter", "chapter_id", "name", "slug", "order_index")


class ConceptPrerequisiteSerializer(serializers.ModelSerializer):
    concept = ConceptSerializer(read_only=True)
    prerequisite_concept = ConceptSerializer(read_only=True)
    concept_id = serializers.PrimaryKeyRelatedField(
        queryset=Concept.objects.all(), source="concept", write_only=True
    )
    prerequisite_concept_id = serializers.PrimaryKeyRelatedField(
        queryset=Concept.objects.all(), source="prerequisite_concept", write_only=True
    )

    class Meta:
        model = ConceptPrerequisite
        fields = (
            "id",
            "concept",
            "concept_id",
            "prerequisite_concept",
            "prerequisite_concept_id",
        )


class ContentItemSerializer(serializers.ModelSerializer):
    subject_id = serializers.PrimaryKeyRelatedField(
        queryset=Subject.objects.all(), source="subject", write_only=True
    )
    chapter_id = serializers.PrimaryKeyRelatedField(
        queryset=Chapter.objects.all(), source="chapter", write_only=True
    )
    primary_concept_id = serializers.PrimaryKeyRelatedField(
        queryset=Concept.objects.all(), source="primary_concept", write_only=True
    )

    class Meta:
        model = ContentItem
        fields = (
            "id",
            "vector_id",
            "external_row_id",
            "content_type",
            "subject_id",
            "chapter_id",
            "primary_concept_id",
            "source_book",
            "page_number",
            "difficulty",
            "question_type",
            "jee_year",
            "exam_type",
            "target_exam",
            "has_diagram",
            "diagram_image_key",
            "solution_image_key",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class ContentSecondaryConceptSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentSecondaryConcept
        fields = ("id", "content_item", "concept")


class ContentFlagSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentFlag
        fields = (
            "id",
            "content_item",
            "reported_by",
            "reason",
            "status",
            "resolved_by",
            "created_at",
            "resolved_at",
        )
        read_only_fields = ("id", "created_at", "reported_by")

    _STAFF_ONLY = ("status", "resolved_by", "resolved_at")

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get("request")
        if not (request and request.user and request.user.is_staff):
            for name in self._STAFF_ONLY:
                fields[name].read_only = True
        return fields


class HealthCheckSerializer(serializers.Serializer):
    status = serializers.CharField()
    version = serializers.CharField()
