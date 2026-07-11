from rest_framework import serializers

from roadmap.models import LearningPath, PathNode, PathProgress
from users.placement import node_proficiency_display


class PathNodeSerializer(serializers.ModelSerializer):
    proficiency_pct = serializers.SerializerMethodField()
    proficiency_display = serializers.SerializerMethodField()

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
            "status",
            "started_at",
            "completed_at",
        )

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
            "nodes",
            "created_at",
            "updated_at",
        )

    def get_progress_pct(self, obj: LearningPath) -> int:
        completed = obj.nodes.filter(status__in=["completed", "skipped"]).count()
        if obj.total_nodes <= 0:
            return 0
        return round((completed / obj.total_nodes) * 100)

    def get_current_node(self, obj: LearningPath):
        node = (
            obj.nodes.filter(status="in_progress").order_by("sequence_index").first()
            or obj.nodes.filter(status="pending").order_by("sequence_index").first()
        )
        if not node:
            return None
        return PathNodeSerializer(node, context=self.context).data


class RoadmapNextSerializer(serializers.Serializer):
    nodes = PathNodeSerializer(many=True)


class PathProgressUpdateSerializer(serializers.Serializer):
    node_id = serializers.UUIDField()
    status = serializers.ChoiceField(choices=["in_progress", "completed", "skipped", "pending"])
    proficiency_pct = serializers.IntegerField(required=False, min_value=0, max_value=100)


class PathProgressSerializer(serializers.ModelSerializer):
    class Meta:
        model = PathProgress
        fields = ("id", "path_node", "status", "proficiency_pct", "note", "created_at")
