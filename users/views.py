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
    Plan,
    StudentProfile,
    Subscription,
    User,
    UserAchievement,
    UserPreferences,
)
from users.supabase_sync import ensure_supabase_user
from users.serializers import (
    AchievementSerializer,
    AuthSessionSerializer,
    NotificationSerializer,
    OAuthAccountSerializer,
    PlanSerializer,
    RegisterSerializer,
    StudentProfileSerializer,
    SubscriptionSerializer,
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
        supabase_user_id = ensure_supabase_user(user)
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
        ensure_supabase_user(user)
        return Response(UserSerializer(user, context={"request": request}).data, status=status.HTTP_201_CREATED)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        supabase_user_id = ensure_supabase_user(user)
        return Response({
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "supabase_user_id": supabase_user_id,
        })


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
