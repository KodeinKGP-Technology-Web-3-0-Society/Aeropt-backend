import logging

from django.utils import timezone as django_timezone
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apis.viewsets import BaseModelViewSet, UserPrimaryKeyViewSet, UserScopedViewSet
from users.models import (
    AccountStatus,
    Achievement,
    AuthSession,
    Notification,
    OAuthAccount,
    OnboardingSession,
    Plan,
    StudentProfile,
    Subscription,
    SyllabusPlacement,
    User,
    UserAchievement,
    UserPreferences,
)
from users.placement_planner import build_placement_plan, get_physics_chapters_metadata
from users.supabase_sync import (
    ensure_supabase_user,
    seed_user_concept_state_from_placement,
    sync_profile_to_supabase,
)

logger = logging.getLogger(__name__)
from users.serializers import (
    AchievementSerializer,
    AuthSessionSerializer,
    NotificationSerializer,
    OAuthAccountSerializer,
    OnboardingSessionSerializer,
    PlanSerializer,
    RegisterSerializer,
    StudentProfileSerializer,
    SubscriptionSerializer,
    SyllabusPlacementSerializer,
    UserAchievementSerializer,
    UserPreferencesSerializer,
    UserSerializer,
)


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    username_field = User.USERNAME_FIELD

    def validate(self, attrs):
        data = super().validate(attrs)
        user = self.user
        if user.status != AccountStatus.ACTIVE:
            raise serializers.ValidationError("This account is not active.")
        if not user.is_active:
            raise serializers.ValidationError("This account has been disabled.")
        supabase_user_id = ensure_supabase_user(user, seed_concepts=False)
        data["supabase_user_id"] = supabase_user_id
        data["user"] = {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "supabase_user_id": supabase_user_id,
        }
        return data


class UserViewSet(BaseModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    filterset_fields = ("role", "status", "email_verified", "phone_verified")
    search_fields = ("email", "full_name", "phone")
    ordering_fields = ("created_at", "email", "full_name")

    def get_permissions(self):
        if self.action in ("list", "create", "destroy"):
            return [IsAdminUser()]
        if self.action in ("update", "partial_update"):
            if self.request.user.is_staff:
                return [IsAdminUser()]
            return [IsAuthenticated()]
        return [IsAuthenticated()]

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.request.user.is_staff:
            return queryset
        return queryset.filter(id=self.request.user.id)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context


class OAuthAccountViewSet(UserScopedViewSet):
    queryset = OAuthAccount.objects.select_related("user").all()
    serializer_class = OAuthAccountSerializer
    filterset_fields = ("provider", "user")
    search_fields = ("email", "provider_user_id")
    ordering_fields = ("created_at",)


class AuthSessionViewSet(UserScopedViewSet):
    queryset = AuthSession.objects.select_related("user").all()
    serializer_class = AuthSessionSerializer
    filterset_fields = ("user", "revoked_at")
    ordering_fields = ("created_at", "expires_at")


class StudentProfileViewSet(UserPrimaryKeyViewSet):
    queryset = StudentProfile.objects.select_related("user").all()
    serializer_class = StudentProfileSerializer
    filterset_fields = ("target_exam", "grade_level", "onboarding_completed")
    search_fields = ("school_name", "city", "state")
    lookup_field = "user_id"

    def perform_update(self, serializer):
        instance = serializer.save()
        sync_profile_to_supabase(instance.user)


class SyllabusPlacementViewSet(UserPrimaryKeyViewSet):
    queryset = SyllabusPlacement.objects.select_related("user").all()
    serializer_class = SyllabusPlacementSerializer
    filterset_fields = ("journey_type", "learning_source")
    lookup_field = "user_id"


class OnboardingSessionViewSet(UserPrimaryKeyViewSet):
    queryset = OnboardingSession.objects.select_related("user").all()
    serializer_class = OnboardingSessionSerializer
    lookup_field = "user_id"


class UserPreferencesViewSet(UserPrimaryKeyViewSet):
    queryset = UserPreferences.objects.select_related("user").all()
    serializer_class = UserPreferencesSerializer
    filterset_fields = ("theme", "preferred_language")
    lookup_field = "user_id"


class PlanViewSet(BaseModelViewSet):
    queryset = Plan.objects.all()
    serializer_class = PlanSerializer
    filterset_fields = ("is_active", "code")
    search_fields = ("name", "code")
    ordering_fields = ("id", "price_inr", "name")

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [IsAdminUser()]
        return [IsAuthenticated()]


class SubscriptionViewSet(UserScopedViewSet):
    queryset = Subscription.objects.select_related("user", "plan").all()
    serializer_class = SubscriptionSerializer
    filterset_fields = ("status", "provider", "plan", "user")
    ordering_fields = ("started_at", "current_period_end")


class AchievementViewSet(BaseModelViewSet):
    queryset = Achievement.objects.all()
    serializer_class = AchievementSerializer
    filterset_fields = ("code",)
    search_fields = ("name", "code", "description")
    ordering_fields = ("id", "name")

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [IsAdminUser()]
        return [IsAuthenticated()]


class UserAchievementViewSet(UserScopedViewSet):
    queryset = UserAchievement.objects.select_related("user", "achievement").all()
    serializer_class = UserAchievementSerializer
    filterset_fields = ("achievement", "user")
    ordering_fields = ("earned_at",)


class NotificationViewSet(UserScopedViewSet):
    queryset = Notification.objects.select_related("user").all()
    serializer_class = NotificationSerializer
    filterset_fields = ("type", "user", "read_at")
    search_fields = ("title", "body")
    ordering_fields = ("created_at",)


class TokenObtainPairViewAlias(TokenObtainPairView):
    serializer_class = EmailTokenObtainPairSerializer


class TokenRefreshViewAlias(TokenRefreshView):
    pass


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        ensure_supabase_user(user, seed_concepts=False)
        return Response(UserSerializer(user, context={"request": request}).data, status=status.HTTP_201_CREATED)


def _profile_payload(user: User) -> dict:
    profile, _ = StudentProfile.objects.get_or_create(user=user)
    placement, _ = SyllabusPlacement.objects.get_or_create(user=user)
    session, _ = OnboardingSession.objects.get_or_create(user=user)

    profile_data = StudentProfileSerializer(profile).data
    placement_data = SyllabusPlacementSerializer(placement).data
    session_data = OnboardingSessionSerializer(session).data

    return {
        "profile": profile_data,
        "placement": placement_data,
        "onboarding_session": session_data,
        "onboarding_completed": bool(profile.onboarding_completed),
        "onboarding_step": profile.onboarding_step,
    }


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        supabase_user_id = ensure_supabase_user(user, seed_concepts=False)
        payload = {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "supabase_user_id": supabase_user_id,
        }
        payload.update(_profile_payload(user))
        return Response(payload)


class OnboardingChaptersView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        chapters = get_physics_chapters_metadata()
        return Response({"chapters": chapters})


class OnboardingPlacementPlanView(APIView):
    """Rules-first diagnostic probe plan from journey + self-reported coverage."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        body = request.data if isinstance(request.data, dict) else {}
        plan = build_placement_plan(
            journey_type=body.get("journey_type", "fresh_start"),
            covered_chapters=body.get("covered_chapters") or [],
            self_assessed_coverage=body.get("self_assessed_coverage") or {},
        )
        return Response(plan)


class OnboardingCompleteView(APIView):
    """Finalize onboarding: seed proficiency, sync Supabase, mark complete."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        profile, _ = StudentProfile.objects.get_or_create(user=user)
        placement, _ = SyllabusPlacement.objects.get_or_create(user=user)
        session, _ = OnboardingSession.objects.get_or_create(user=user)

        body = request.data if isinstance(request.data, dict) else {}

        profile_fields = body.get("profile") or {}
        for field in (
            "target_exam",
            "target_year",
            "grade_level",
            "daily_goal_minutes",
            "preferred_depth",
            "onboarding_step",
        ):
            if field in profile_fields:
                setattr(profile, field, profile_fields[field])

        placement_fields = body.get("placement") or {}
        for field in (
            "journey_type",
            "learning_source",
            "covered_chapters",
            "self_assessed_coverage",
            "diagnostic_baseline",
        ):
            if field in placement_fields:
                setattr(placement, field, placement_fields[field])

        if "snapshot" in body:
            session.snapshot = body["snapshot"]
        if "current_step" in body:
            session.current_step = body["current_step"]

        profile.onboarding_completed = True
        profile.onboarding_step = body.get("onboarding_step", 8)
        session.completed_at = django_timezone.now()

        profile.save()
        placement.save()
        session.save()

        sandbox = seed_user_concept_state_from_placement(user)
        if sandbox is None:
            sandbox = {
                "target_label": profile.target_exam,
                "chapters_total": 0,
                "chapters_covered": len(placement.covered_chapters or []),
                "overall_proficiency_pct": 50,
                "concepts_on_path": 0,
                "estimated_weeks": 8,
                "first_up": "your first concept",
                "journey_type": placement.journey_type,
            }

        roadmap_summary = None
        try:
            from roadmap.generator import generate_learning_path, _read_concept_state_map
            from roadmap.serializers import LearningPathSerializer

            path = generate_learning_path(user, force=True)
            roadmap_ctx = {
                "placement": getattr(user, "syllabus_placement", None),
                "concept_states": _read_concept_state_map(user),
            }
            roadmap_data = LearningPathSerializer(path, context=roadmap_ctx).data
            roadmap_summary = {
                "total_nodes": roadmap_data.get("total_nodes"),
                "active_nodes": roadmap_data.get("active_nodes"),
                "estimated_weeks": roadmap_data.get("estimated_weeks"),
                "progress_pct": roadmap_data.get("progress_pct"),
                "current_node": roadmap_data.get("current_node"),
            }
            if roadmap_data.get("current_node"):
                sandbox["first_up"] = roadmap_data["current_node"].get("concept_name", sandbox.get("first_up"))
                sandbox["concepts_on_path"] = roadmap_data.get("active_nodes", sandbox.get("concepts_on_path"))
                sandbox["estimated_weeks"] = roadmap_data.get("estimated_weeks", sandbox.get("estimated_weeks"))
        except Exception:
            logger.exception("Failed to generate learning path after onboarding for %s", user.id)

        return Response(
            {
                "ok": True,
                "onboarding_completed": True,
                "sandbox": sandbox,
                "roadmap": roadmap_summary,
            },
            status=status.HTTP_200_OK,
        )


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response({"detail": "Refresh token is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except Exception:
            return Response({"detail": "Invalid or expired refresh token."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_205_RESET_CONTENT)
