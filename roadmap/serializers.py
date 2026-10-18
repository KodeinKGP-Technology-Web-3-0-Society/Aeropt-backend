from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from roadmap.models import LearningPath, PathNode, PathProgress
from users.placement import node_proficiency_display


class PathNodeSerializer(serializers.ModelSerializer):
    proficiency_pct = serializers.SerializerMethodField()
    proficiency_display = serializers.SerializerMethodField()
    content_ready = serializers.SerializerMethodField()

    class Meta:
        model = PathNode
        fields = (
            "id",
            "sequence_index",
            "concept_id",
            "concept_name",
            "chapter",
            "node_type",
            "exam_weight",
            "content_sequence",
            "mastery_threshold",
            "estimated_minutes",
            "proficiency_pct",
            "proficiency_display",
            "content_ready",
            "status",
            "started_at",
            "completed_at",
        )

    def get_content_ready(self, obj: PathNode) -> bool:
        """
        Whether the tutor can actually teach this concept yet.

        The roadmap is generated from the syllabus YAML, which intentionally
        describes more of the exam than the knowledge graph has been seeded
        with. A node whose concept_id isn't in the live `concepts` table would
        dead-end if a student opened it — the concept resolver would (correctly)
        report it as outside the covered syllabus. Surfacing this lets the UI
        show the full plan while being honest about what's teachable today,
        instead of handing the student a button that goes nowhere.

        Absent context (any caller that doesn't supply the id set) defaults to
        True, so this can never make an already-working node look broken.
        """
        live_ids = self.context.get("live_concept_ids")
        if live_ids is None:
            return True
        return obj.concept_id in live_ids

    def _state_for(self, obj: PathNode) -> dict:
        concept_states = self.context.get("concept_states") or {}
        return concept_states.get(obj.concept_id, {})

    def _display(self, obj: PathNode) -> tuple[int | None, str]:
        state = self._state_for(obj)
        score = state.get("score", obj.proficiency_pct / 100.0)
        is_cold = state.get("is_cold_start", obj.proficiency_pct == 50 and obj.status == "pending")
        placement = self.context.get("placement")
        return node_proficiency_display(
            score,
            obj.chapter,
            placement,
            is_cold_start=is_cold,
            status=obj.status,
            node_type=obj.node_type,
        )

    @extend_schema_field(serializers.IntegerField(allow_null=True))
    def get_proficiency_pct(self, obj: PathNode):
        pct, _ = self._display(obj)
        return pct

    def get_proficiency_display(self, obj: PathNode) -> str:
        _, label = self._display(obj)
        return label


class LearningPathSerializer(serializers.ModelSerializer):
    nodes = PathNodeSerializer(many=True, read_only=True)
    progress_pct = serializers.SerializerMethodField()
    current_node = serializers.SerializerMethodField()
    study_plan = serializers.SerializerMethodField()

    class Meta:
        model = LearningPath
        fields = (
            "id",
            "subject",
            "total_nodes",
            "active_nodes",
            "estimated_weeks",
            "daily_goal_minutes",
            "progress_pct",
            "current_node",
            "study_plan",
            "nodes",
            "created_at",
            "updated_at",
        )

    def get_progress_pct(self, obj: LearningPath) -> int:
        completed = obj.nodes.filter(status__in=["completed", "skipped"]).count()
        if obj.total_nodes <= 0:
            return 0
        return round((completed / obj.total_nodes) * 100)

    @extend_schema_field(PathNodeSerializer(allow_null=True))
    def get_current_node(self, obj: LearningPath):
        node = (
            obj.nodes.filter(status="in_progress").order_by("sequence_index").first()
            or obj.nodes.filter(status="pending").order_by("sequence_index").first()
        )
        if not node:
            return None
        return PathNodeSerializer(node, context=self.context).data

    def get_study_plan(self, obj: LearningPath) -> dict:
        from roadmap.generator import compose_study_plan

        return compose_study_plan(
            list(obj.nodes.all()),
            subject=obj.subject or "Physics",
            daily_goal_minutes=obj.daily_goal_minutes or 45,
        )


class RoadmapNextSerializer(serializers.Serializer):
    nodes = PathNodeSerializer(many=True)


class PathProgressUpdateSerializer(serializers.Serializer):
    node_id = serializers.UUIDField()
    status = serializers.ChoiceField(choices=["in_progress", "completed", "skipped", "pending"])
    proficiency_pct = serializers.IntegerField(required=False, min_value=0, max_value=100)


class RoadmapSubjectsSerializer(serializers.Serializer):
    subjects = serializers.ListField(child=serializers.CharField())


class RoadmapProgressResponseSerializer(serializers.Serializer):
    node = PathNodeSerializer()
    roadmap = LearningPathSerializer()


class PathProgressSerializer(serializers.ModelSerializer):
    class Meta:
        model = PathProgress
        fields = ("id", "path_node", "status", "proficiency_pct", "note", "created_at")
