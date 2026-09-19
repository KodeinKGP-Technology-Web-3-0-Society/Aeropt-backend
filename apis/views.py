import logging

from django.conf import settings
from django.db import connections
from drf_spectacular.utils import extend_schema
from rest_framework import status
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


logger = logging.getLogger(__name__)

API_VERSION = "1.0.0"


class HealthCheckView(APIView):
    """Liveness + shallow dependency check for load balancers.

    Deliberately cheap: one `SELECT 1` against the default database and a
    config-only look at the Supabase credentials. It never performs a Supabase
    round trip — that would put a network hop on every load-balancer probe.

    200 when the database answers, 503 when it does not. Never throttled.
    """

    permission_classes = (AllowAny,)
    authentication_classes = ()
    throttle_classes = ()

    @extend_schema(
        responses={200: HealthCheckSerializer, 503: HealthCheckSerializer},
        description=(
            "Liveness probe. Reports API version, the request id, a `SELECT 1` "
            "database ping and whether Supabase credentials are configured. "
            "503 when the database ping fails."
        ),
    )
    def get(self, request):
        db_ok, db_detail = self._check_database()
        supabase_configured = bool(
            getattr(settings, "SUPABASE_URL", "") and getattr(settings, "SUPABASE_KEY", "")
        )

        payload = {
            **HealthCheckSerializer(
                {"status": "ok" if db_ok else "degraded", "version": API_VERSION}
            ).data,
            "request_id": getattr(request, "request_id", None),
            "checks": {
                "database": {"status": "ok" if db_ok else "error", "detail": db_detail},
                # Configured-ness only; no live call.
                "supabase": {
                    "status": "configured" if supabase_configured else "unconfigured"
                },
            },
        }

        if not db_ok:
            logger.error("health check failed: database unreachable (%s)", db_detail)
            return Response(payload, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response(payload)

    @staticmethod
    def _check_database():
        try:
            with connections["default"].cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except Exception as exc:  # a health probe must never itself 500
            return False, type(exc).__name__
        return True, None


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
