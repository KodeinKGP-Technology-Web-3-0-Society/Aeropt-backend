from django.urls import path
from rest_framework.routers import DefaultRouter

from analytics.views import (
    AssessmentQuestionViewSet,
    AssessmentViewSet,
    ChapterProgressViewSet,
    ConceptMasteryViewSet,
    DailyActivityViewSet,
    DashboardView,
    LearningGapViewSet,
    ProficiencySnapshotViewSet,
    ProgressView,
    QuestionAttemptViewSet,
    RecommendationViewSet,
    StreakViewSet,
)

router = DefaultRouter()
router.register(r"concept-masteries", ConceptMasteryViewSet, basename="concept-mastery")
router.register(r"chapter-progress", ChapterProgressViewSet, basename="chapter-progress")
router.register(r"proficiency-snapshots", ProficiencySnapshotViewSet, basename="proficiency-snapshot")
router.register(r"learning-gaps", LearningGapViewSet, basename="learning-gap")
router.register(r"recommendations", RecommendationViewSet, basename="recommendation")
router.register(r"question-attempts", QuestionAttemptViewSet, basename="question-attempt")
router.register(r"streaks", StreakViewSet, basename="streak")
router.register(r"daily-activities", DailyActivityViewSet, basename="daily-activity")
router.register(r"assessments", AssessmentViewSet, basename="assessment")
router.register(r"assessment-questions", AssessmentQuestionViewSet, basename="assessment-question")

urlpatterns = [
    path("dashboard/", DashboardView.as_view(), name="analytics-dashboard"),
    path("progress/", ProgressView.as_view(), name="analytics-progress"),
] + router.urls
