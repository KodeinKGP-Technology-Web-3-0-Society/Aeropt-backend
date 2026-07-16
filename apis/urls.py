from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apis.views import (
    ChapterViewSet,
    ConceptPrerequisiteViewSet,
    ConceptViewSet,
    ContentFlagViewSet,
    ContentItemViewSet,
    ContentSecondaryConceptViewSet,
    HealthCheckView,
    SubjectViewSet,
)
from users.urls import auth_urlpatterns, onboarding_urlpatterns, user_urlpatterns

router = DefaultRouter()
router.register(r"subjects", SubjectViewSet, basename="subject")
router.register(r"chapters", ChapterViewSet, basename="chapter")
router.register(r"concepts", ConceptViewSet, basename="concept")
router.register(r"concept-prerequisites", ConceptPrerequisiteViewSet, basename="concept-prerequisite")
router.register(r"content-items", ContentItemViewSet, basename="content-item")
router.register(r"content-secondary-concepts", ContentSecondaryConceptViewSet, basename="content-secondary-concept")
router.register(r"content-flags", ContentFlagViewSet, basename="content-flag")

urlpatterns = [
    path("health/", HealthCheckView.as_view(), name="health-check"),
    path("auth/", include((auth_urlpatterns, "users"), namespace="auth")),
    path("onboarding/", include((onboarding_urlpatterns, "users"), namespace="onboarding")),
    path("users/", include((user_urlpatterns, "users"), namespace="users")),
    # LEGACY: Django chatbot — unused by product Study Session (agent :8001).
    path("chat/", include("chatbot.urls")),
    path("analytics/", include("analytics.urls")),
    path("roadmap/", include("roadmap.urls")),
    path("sandbox/", include("sandbox.urls")),
] + router.urls
