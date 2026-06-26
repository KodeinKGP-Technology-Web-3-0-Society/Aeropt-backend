from django.urls import path
from rest_framework.routers import DefaultRouter

from users.views import (
    AchievementViewSet,
    AuthSessionViewSet,
    NotificationViewSet,
    OAuthAccountViewSet,
    PlanViewSet,
    StudentProfileViewSet,
    SubscriptionViewSet,
    TokenObtainPairViewAlias,
    TokenRefreshViewAlias,
    UserAchievementViewSet,
    UserPreferencesViewSet,
    UserViewSet,
)

router = DefaultRouter()
router.register(r"", UserViewSet, basename="user")
router.register(r"oauth-accounts", OAuthAccountViewSet, basename="oauth-account")
router.register(r"auth-sessions", AuthSessionViewSet, basename="auth-session")
router.register(r"student-profiles", StudentProfileViewSet, basename="student-profile")
router.register(r"preferences", UserPreferencesViewSet, basename="user-preferences")
router.register(r"plans", PlanViewSet, basename="plan")
router.register(r"subscriptions", SubscriptionViewSet, basename="subscription")
router.register(r"achievements", AchievementViewSet, basename="achievement")
router.register(r"user-achievements", UserAchievementViewSet, basename="user-achievement")
router.register(r"notifications", NotificationViewSet, basename="notification")

auth_urlpatterns = [
    path("token/", TokenObtainPairViewAlias.as_view(), name="token-obtain"),
    path("token/refresh/", TokenRefreshViewAlias.as_view(), name="token-refresh"),
]

user_urlpatterns = router.urls
