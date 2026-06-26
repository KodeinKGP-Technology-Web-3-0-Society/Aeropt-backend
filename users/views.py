from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apis.viewsets import BaseModelViewSet, UserPrimaryKeyViewSet, UserScopedViewSet
from users.models import (
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
from users.serializers import (
    AchievementSerializer,
    AuthSessionSerializer,
    NotificationSerializer,
    OAuthAccountSerializer,
    PlanSerializer,
    StudentProfileSerializer,
    SubscriptionSerializer,
    UserAchievementSerializer,
    UserPreferencesSerializer,
    UserSerializer,
)


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    username_field = User.USERNAME_FIELD


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
