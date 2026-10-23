import logging

from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from drf_spectacular.utils import OpenApiParameter, extend_schema

from apis.viewsets import ActorMixin

from analytics.cache_keys import (
    TTL_CHAT_HISTORY,
    TTL_CHAT_HISTORY_DETAIL,
    chat_history_detail_key,
    chat_history_key,
)
from analytics.serializers import (
    ChatHistoryDetailSerializer,
    ChatHistoryListSerializer,
    DashboardSerializer,
    DetailMessageSerializer,
    ProgressSerializer,
)
from analytics.supabase_chat_history import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    build_chat_history_detail,
    build_chat_history_list,
)
from analytics.supabase_dashboard import build_dashboard_from_supabase
from analytics.supabase_progress import build_progress_from_supabase
from apis.cache_layer import (
    TTL_DASHBOARD,
    TTL_PROGRESS,
    dashboard_key,
    get_or_set,
    progress_key,
)
from users.models import SyllabusPlacement
from users.supabase_sync import ensure_supabase_user, is_supabase_configured

logger = logging.getLogger(__name__)


class DashboardView(ActorMixin, APIView):
    permission_classes = (AllowAny if getattr(settings, "DEV_AUTH_BYPASS", False) else IsAuthenticated,)

    @extend_schema(responses={200: DashboardSerializer, 503: DetailMessageSerializer})
    def get(self, request):
        user = self.get_actor_user()
        supabase_user_id = ensure_supabase_user(user)

        if not is_supabase_configured():
            return Response(
                {"detail": "Supabase is not configured. Set SUPABASE_URL and SUPABASE_KEY in .env."},
                status=503,
            )
        if not supabase_user_id:
            return Response(
                {"detail": "Could not link your account to Supabase. Sign out and sign in again."},
                status=503,
            )

        placement = getattr(user, "syllabus_placement", None)

        def _build():
            payload = build_dashboard_from_supabase(supabase_user_id, placement=placement)
            if payload is None:
                return None
            payload = dict(payload)
            payload["source"] = "supabase"
            return payload

        payload = get_or_set(dashboard_key(user), TTL_DASHBOARD, _build)
        if payload is not None:
            return Response(payload)
        return Response(
            {"detail": "Supabase dashboard data is temporarily unavailable."},
            status=503,
        )


class ProgressView(ActorMixin, APIView):
    permission_classes = (AllowAny if getattr(settings, "DEV_AUTH_BYPASS", False) else IsAuthenticated,)

    @extend_schema(responses={200: ProgressSerializer, 503: DetailMessageSerializer})
    def get(self, request):
        user = self.get_actor_user()
        supabase_user_id = ensure_supabase_user(user)

        if not is_supabase_configured():
            return Response(
                {"detail": "Supabase is not configured. Set SUPABASE_URL and SUPABASE_KEY in .env."},
                status=503,
            )
        if not supabase_user_id:
            return Response(
                {"detail": "Could not link your account to Supabase. Sign out and sign in again."},
                status=503,
            )

        placement = SyllabusPlacement.objects.filter(user=user).first()

        def _build():
            payload = build_progress_from_supabase(supabase_user_id, placement=placement)
            if payload is None:
                return None
            payload = dict(payload)
            payload["source"] = "supabase"
            return payload

        payload = get_or_set(progress_key(user), TTL_PROGRESS, _build)
        if payload is not None:
            return Response(payload)
        return Response(
            {"detail": "Supabase progress data is temporarily unavailable."},
            status=503,
        )


class _SupabaseReadView(ActorMixin, APIView):
    """Shared preamble for the Supabase-backed read endpoints.

    Returns (user, supabase_user_id, error_response). CI and any unconfigured
    environment take the error path with a 503 and a readable `detail`, never a
    500 out of the Supabase client.
    """

    permission_classes = (AllowAny if getattr(settings, "DEV_AUTH_BYPASS", False) else IsAuthenticated,)

    def _resolve(self, request):
        user = self.get_actor_user()
        supabase_user_id = ensure_supabase_user(user)
        if not is_supabase_configured():
            return user, None, Response(
                {"detail": "Supabase is not configured. Set SUPABASE_URL and SUPABASE_KEY in .env."},
                status=503,
            )
        if not supabase_user_id:
            return user, None, Response(
                {"detail": "Could not link your account to Supabase. Sign out and sign in again."},
                status=503,
            )
        return user, supabase_user_id, None


class ChatHistoryListView(_SupabaseReadView):
    """Paginated list of a student's past tutoring sessions."""

    @extend_schema(
        parameters=[
            OpenApiParameter("page", int, description="1-based page number (default 1)."),
            OpenApiParameter(
                "page_size",
                int,
                description=f"Sessions per page (default {DEFAULT_PAGE_SIZE}, max {MAX_PAGE_SIZE}).",
            ),
            OpenApiParameter("subject", str, description="Optional subject filter."),
        ],
        responses={200: ChatHistoryListSerializer},
        operation_id="analytics_chat_history_list",
    )
    def get(self, request):
        user, supabase_user_id, error = self._resolve(request)
        if error is not None:
            return error

        try:
            page = max(1, int(request.query_params.get("page", 1)))
        except (TypeError, ValueError):
            page = 1
        try:
            page_size = int(request.query_params.get("page_size", DEFAULT_PAGE_SIZE))
        except (TypeError, ValueError):
            page_size = DEFAULT_PAGE_SIZE
        page_size = max(1, min(page_size, MAX_PAGE_SIZE))
        subject = (request.query_params.get("subject") or "").strip() or None

        payload = get_or_set(
            chat_history_key(user, page, page_size, subject or ""),
            TTL_CHAT_HISTORY,
            lambda: build_chat_history_list(
                supabase_user_id,
                page=page,
                page_size=page_size,
                subject_filter=subject,
            ),
        )
        if payload is None:
            logger.warning("Chat history unavailable for user %s", user.pk)
            return Response(
                {"detail": "Chat history is temporarily unavailable."},
                status=503,
            )
        return Response(payload)


class ChatHistoryDetailView(_SupabaseReadView):
    """Full turn-by-turn transcript of one session, scoped to its owner."""

    @extend_schema(
        responses={200: ChatHistoryDetailSerializer},
        operation_id="analytics_chat_history_retrieve",
    )
    def get(self, request, session_id: str):
        user, supabase_user_id, error = self._resolve(request)
        if error is not None:
            return error

        payload = get_or_set(
            chat_history_detail_key(user, session_id),
            TTL_CHAT_HISTORY_DETAIL,
            lambda: build_chat_history_detail(supabase_user_id, session_id),
        )
        if payload is None:
            # build_chat_history_detail filters on user_id, so "no row" means
            # either no such session or not this student's — same answer either way.
            return Response({"detail": "Session not found."}, status=404)
        return Response(payload)


from apis.viewsets import BaseModelViewSet, StaffWriteViewSet, SystemOwnedMixin, UserPrimaryKeyViewSet, UserScopedViewSet
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
from analytics.serializers import (
    AssessmentQuestionSerializer,
    AssessmentSerializer,
    ChapterProgressSerializer,
    ConceptMasterySerializer,
    DailyActivitySerializer,
    LearningGapSerializer,
    ProficiencySnapshotSerializer,
    QuestionAttemptSerializer,
    RecommendationSerializer,
    StreakSerializer,
)












class ConceptMasteryViewSet(SystemOwnedMixin, UserScopedViewSet):
    queryset = ConceptMastery.objects.select_related("user", "concept").all()
    serializer_class = ConceptMasterySerializer
    filterset_fields = ("status", "is_flagged_weak", "user", "concept")
    ordering_fields = ("mastery_score", "updated_at", "last_practiced_at")


class ChapterProgressViewSet(SystemOwnedMixin, UserScopedViewSet):
    queryset = ChapterProgress.objects.select_related("user", "chapter").all()
    serializer_class = ChapterProgressSerializer
    filterset_fields = ("chapter", "user")
    ordering_fields = ("mastery_score", "completion_percent", "updated_at")


class ProficiencySnapshotViewSet(SystemOwnedMixin, UserScopedViewSet):
    queryset = ProficiencySnapshot.objects.select_related("user", "subject").all()
    serializer_class = ProficiencySnapshotSerializer
    filterset_fields = ("subject", "snapshot_date", "user")
    ordering_fields = ("snapshot_date", "proficiency")


class LearningGapViewSet(SystemOwnedMixin, UserScopedViewSet):
    queryset = LearningGap.objects.select_related("user", "concept").all()
    serializer_class = LearningGapSerializer
    filterset_fields = ("severity", "source", "user", "concept")
    ordering_fields = ("detected_at", "resolved_at", "severity")


class RecommendationViewSet(SystemOwnedMixin, UserScopedViewSet):
    queryset = Recommendation.objects.select_related("user", "concept", "content_item").all()
    serializer_class = RecommendationSerializer
    filterset_fields = ("type", "user", "concept", "content_item")
    search_fields = ("reason",)
    ordering_fields = ("score", "created_at", "served_at")


class QuestionAttemptViewSet(SystemOwnedMixin, UserScopedViewSet):
    # `study_session` used to appear here and in the serializer, but no such
    # field (or model) exists on QuestionAttempt — it made every request to this
    # viewset, and all of /api/schema/, raise TypeError from django-filter.
    queryset = QuestionAttempt.objects.select_related("user", "content_item").all()
    serializer_class = QuestionAttemptSerializer
    filterset_fields = ("is_correct", "error_type", "user", "content_item")
    ordering_fields = ("attempted_at", "attempt_number")


class StreakViewSet(SystemOwnedMixin, UserPrimaryKeyViewSet):
    queryset = Streak.objects.select_related("user").all()
    serializer_class = StreakSerializer
    lookup_field = "user_id"


class DailyActivityViewSet(SystemOwnedMixin, UserScopedViewSet):
    queryset = DailyActivity.objects.select_related("user").all()
    serializer_class = DailyActivitySerializer
    filterset_fields = ("activity_date", "goal_met", "user")
    ordering_fields = ("activity_date", "minutes_studied")


class AssessmentViewSet(SystemOwnedMixin, UserScopedViewSet):
    queryset = Assessment.objects.select_related("user", "chapter", "concept").all()
    serializer_class = AssessmentSerializer
    filterset_fields = ("type", "status", "user", "chapter", "concept")
    ordering_fields = ("started_at", "completed_at", "score")


class AssessmentQuestionViewSet(StaffWriteViewSet):
    queryset = AssessmentQuestion.objects.select_related("assessment", "content_item").all()
    serializer_class = AssessmentQuestionSerializer
    filterset_fields = ("assessment", "content_item", "is_correct", "is_flagged")
    ordering_fields = ("step_index", "answered_at")

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if not user.is_authenticated:
            if getattr(settings, "DEV_AUTH_BYPASS", False):
                return queryset
            return queryset.none()
        if user.is_staff:
            return queryset
        return queryset.filter(assessment__user=user)
