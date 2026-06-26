from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apis.models import (
    Chapter,
    Concept,
    ConceptPrerequisite,
    ContentFlag,
    ContentItem,
    ContentSecondaryConcept,
    Subject,
)
from apis.serializers import (
    ChapterSerializer,
    ConceptPrerequisiteSerializer,
    ConceptSerializer,
    ContentFlagSerializer,
    ContentItemSerializer,
    ContentSecondaryConceptSerializer,
    HealthCheckSerializer,
    SubjectSerializer,
)
from apis.viewsets import BaseModelViewSet, UserScopedViewSet


class HealthCheckView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        data = HealthCheckSerializer({"status": "ok", "version": "1.0.0"}).data
        return Response(data)


class SubjectViewSet(BaseModelViewSet):
    queryset = Subject.objects.all()
    serializer_class = SubjectSerializer
    filterset_fields = ("slug",)
    search_fields = ("name", "slug")
    ordering_fields = ("order_index", "name", "id")


class ChapterViewSet(BaseModelViewSet):
    queryset = Chapter.objects.select_related("subject").all()
    serializer_class = ChapterSerializer
    filterset_fields = ("subject", "slug")
    search_fields = ("name", "slug")
    ordering_fields = ("order_index", "name", "id")


class ConceptViewSet(BaseModelViewSet):
    queryset = Concept.objects.select_related("chapter", "chapter__subject").all()
    serializer_class = ConceptSerializer
    filterset_fields = ("chapter", "slug")
    search_fields = ("name", "slug")
    ordering_fields = ("order_index", "name", "id")


class ConceptPrerequisiteViewSet(BaseModelViewSet):
    queryset = ConceptPrerequisite.objects.select_related("concept", "prerequisite_concept").all()
    serializer_class = ConceptPrerequisiteSerializer
    filterset_fields = ("concept", "prerequisite_concept")
    ordering_fields = ("concept", "prerequisite_concept")


class ContentItemViewSet(BaseModelViewSet):
    queryset = ContentItem.objects.select_related(
        "subject", "chapter", "primary_concept"
    ).all()
    serializer_class = ContentItemSerializer
    filterset_fields = (
        "content_type",
        "subject",
        "chapter",
        "primary_concept",
        "source_book",
        "question_type",
        "exam_type",
        "target_exam",
        "is_active",
        "has_diagram",
        "difficulty",
    )
    search_fields = ("vector_id", "external_row_id", "page_number")
    ordering_fields = ("created_at", "difficulty", "jee_year")


class ContentSecondaryConceptViewSet(BaseModelViewSet):
    queryset = ContentSecondaryConcept.objects.select_related("content_item", "concept").all()
    serializer_class = ContentSecondaryConceptSerializer
    filterset_fields = ("content_item", "concept")
    ordering_fields = ("content_item", "concept")


class ContentFlagViewSet(UserScopedViewSet):
    queryset = ContentFlag.objects.select_related(
        "content_item", "reported_by", "resolved_by"
    ).all()
    serializer_class = ContentFlagSerializer
    owner_field = "reported_by"
    filterset_fields = ("status", "content_item", "reported_by", "resolved_by")
    search_fields = ("reason",)
    ordering_fields = ("created_at", "resolved_at")

    def perform_create(self, serializer):
        serializer.save(reported_by=self.get_actor_user())
