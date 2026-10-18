from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from roadmap.generator import (
    generate_learning_path,
    get_next_nodes,
    get_or_generate_learning_path,
    live_concept_ids,
    _read_concept_state_map,
)
from roadmap.models import LearningPath, NodeStatus, PathNode, PathProgress
from roadmap.serializers import (
    LearningPathSerializer,
    PathNodeSerializer,
    PathProgressUpdateSerializer,
    RoadmapNextSerializer,
    RoadmapProgressResponseSerializer,
    RoadmapSubjectsSerializer,
)
from roadmap.syllabus import available_subjects
from apis.cache_layer import (
    TTL_ROADMAP,
    get_or_set,
    invalidate_roadmap,
    invalidate_user_reads,
    roadmap_key,
)


def _roadmap_serializer_context(user, subject: str = "Physics"):
    placement = getattr(user, "syllabus_placement", None)
    return {
        "placement": placement,
        "concept_states": _read_concept_state_map(user),
        # Lets PathNodeSerializer mark nodes the tutor can't teach yet.
        "live_concept_ids": live_concept_ids(subject),
    }


_NO_SYLLABUS_MESSAGE = (
    "We couldn't build your roadmap yet because the syllabus is unavailable. "
    "Please try again shortly."
)


def _resolve_subject(request) -> str:
    """?subject=Chemistry — falls back to Physics (the pre-existing default,
    so every caller that never sends this param keeps working unchanged) and
    rejects anything without a real syllabus file rather than silently
    building an empty roadmap for a typo'd subject name."""
    requested = request.query_params.get("subject") or "Physics"
    valid = available_subjects()
    return requested if requested in valid else "Physics"


class RoadmapView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter("subject", str, description="Physics or Chemistry. Anything else falls back to Physics."),
            OpenApiParameter("regenerate", str, description="Pass 1 to rebuild the active path."),
        ],
        responses={200: LearningPathSerializer},
    )
    def get(self, request):
        subject = _resolve_subject(request)
        regenerate = request.query_params.get("regenerate") == "1"
        try:
            if regenerate:
                path = generate_learning_path(request.user, subject=subject, force=True)
                invalidate_roadmap(request.user, subject)

                def _fresh():
                    return LearningPathSerializer(
                        path, context=_roadmap_serializer_context(request.user, subject)
                    ).data

                payload = _fresh()
                from django.core.cache import cache

                cache.set(roadmap_key(request.user, subject), payload, TTL_ROADMAP)
                return Response(payload)

            def _build():
                path = get_or_generate_learning_path(request.user, subject=subject)
                return LearningPathSerializer(
                    path, context=_roadmap_serializer_context(request.user, subject)
                ).data

            payload = get_or_set(roadmap_key(request.user, subject), TTL_ROADMAP, _build)
            return Response(payload)
        except ValueError:
            return Response(
                {"detail": _NO_SYLLABUS_MESSAGE},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

    @extend_schema(
        parameters=[
            OpenApiParameter("subject", str, description="Physics or Chemistry. Anything else falls back to Physics."),
        ],
        request=None,
        responses={201: LearningPathSerializer},
    )
    def post(self, request):
        subject = _resolve_subject(request)
        try:
            path = generate_learning_path(request.user, subject=subject, force=True)
            invalidate_user_reads(request.user, subject)
        except ValueError:
            return Response(
                {"detail": _NO_SYLLABUS_MESSAGE},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(
            LearningPathSerializer(path, context=_roadmap_serializer_context(request.user, subject)).data,
            status=status.HTTP_201_CREATED,
        )


class RoadmapSubjectsView(APIView):
    """Which subjects actually have a roadmap available right now."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: RoadmapSubjectsSerializer})
    def get(self, request):
        return Response({"subjects": available_subjects()})


class RoadmapNextView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter("subject", str, description="Physics or Chemistry. Anything else falls back to Physics."),
        ],
        responses={200: RoadmapNextSerializer},
    )
    def get(self, request):
        subject = _resolve_subject(request)
        try:
            path = get_or_generate_learning_path(request.user, subject=subject)
        except ValueError:
            return Response(
                {"detail": _NO_SYLLABUS_MESSAGE},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        nodes = get_next_nodes(path, limit=3)
        ctx = _roadmap_serializer_context(request.user, subject)
        return Response({"nodes": PathNodeSerializer(nodes, many=True, context=ctx).data})


class RoadmapProgressView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=PathProgressUpdateSerializer,
        responses={200: RoadmapProgressResponseSerializer},
    )
    def patch(self, request):
        serializer = PathProgressUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        node_id = serializer.validated_data["node_id"]
        new_status = serializer.validated_data["status"]
        proficiency_pct = serializer.validated_data.get("proficiency_pct")

        try:
            node = PathNode.objects.select_related("learning_path").get(
                id=node_id,
                learning_path__user=request.user,
                learning_path__is_active=True,
            )
        except PathNode.DoesNotExist:
            return Response({"detail": "Path node not found."}, status=status.HTTP_404_NOT_FOUND)

        now = timezone.now()
        if new_status == NodeStatus.IN_PROGRESS:
            node.status = NodeStatus.IN_PROGRESS
            node.started_at = node.started_at or now
            node.completed_at = None
            PathNode.objects.filter(
                learning_path_id=node.learning_path_id,
                status=NodeStatus.IN_PROGRESS,
            ).exclude(chapter=node.chapter).update(
                status=NodeStatus.PENDING,
                completed_at=None,
            )
        elif new_status == NodeStatus.COMPLETED:
            node.status = NodeStatus.COMPLETED
            node.completed_at = now
        elif new_status == NodeStatus.SKIPPED:
            node.status = NodeStatus.SKIPPED
            node.completed_at = now
        else:
            node.status = NodeStatus.PENDING
            node.completed_at = None

        if proficiency_pct is not None:
            node.proficiency_pct = proficiency_pct

        node.save()

        if new_status == NodeStatus.COMPLETED and node.learning_path_id:
            next_pending = (
                PathNode.objects.filter(
                    learning_path_id=node.learning_path_id,
                    status=NodeStatus.PENDING,
                    sequence_index__gt=node.sequence_index,
                )
                .order_by("sequence_index")
                .first()
            )
            if next_pending:
                next_pending.status = NodeStatus.IN_PROGRESS
                next_pending.started_at = next_pending.started_at or now
                next_pending.save(update_fields=["status", "started_at"])

        PathProgress.objects.create(
            user=request.user,
            path_node=node,
            status=node.status,
            proficiency_pct=node.proficiency_pct,
        )

        # Progress is addressed by node id, not by query param — take the
        # subject from the path the node actually belongs to.
        node_subject = node.learning_path.subject or "Physics"
        invalidate_user_reads(request.user, node_subject)

        path = LearningPath.objects.prefetch_related("nodes").get(id=node.learning_path_id)
        ctx = _roadmap_serializer_context(request.user, node_subject)
        return Response(
            {
                "node": PathNodeSerializer(node, context=ctx).data,
                "roadmap": LearningPathSerializer(path, context=ctx).data,
            }
        )
