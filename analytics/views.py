import datetime

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.exceptions import NotAuthenticated

from analytics.models import ConceptProficiency, StudyStreak

class _SessionMixin:
    def _get_actor_user(self, request):
        if request.user and request.user.is_authenticated:
            return request.user

        if not getattr(settings, "CHATBOT_AUTH_DISABLED", False):
            raise NotAuthenticated("Authentication credentials were not provided.")

        User = get_user_model()
        email = getattr(settings, "CHATBOT_DEV_EMAIL", "chatbot-dev@local.test")
        dev_user, _ = User.objects.get_or_create(
            email=email,
            defaults={"full_name": "Chatbot Dev", "is_active": True},
        )
        return dev_user


def seed_default_metrics(user):
    default_concepts = [
        # Laws of Motion
        ("Newton's First Law", "Laws of Motion", 82, 14, "flat"),
        ("Free Body Diagram", "Laws of Motion", 71, 11, "flat"),
        ("Constraint Motion", "Laws of Motion", 34, 6, "down"),
        ("Pseudo Force", "Laws of Motion", 52, 8, "flat"),
        ("Friction", "Laws of Motion", 68, 10, "flat"),
        ("Newton's Third Law", "Laws of Motion", 58, 9, "flat"),
        
        # Rotational Motion
        ("Torque", "Rotational Motion", 32, 18, "down"),
        ("Rolling with Slipping", "Rotational Motion", 38, 11, "up"),
        ("Moment of Inertia", "Rotational Motion", 58, 12, "flat"),
        ("Angular Momentum", "Rotational Motion", 45, 7, "flat"),
        ("Fixed Axis Rotation", "Rotational Motion", 61, 14, "flat"),
        
        # Work Energy & Power
        ("Work-Energy Theorem", "Work Energy & Power", 78, 24, "up"),
        ("Conservative Forces", "Work Energy & Power", 80, 15, "flat"),
        ("Power", "Work Energy & Power", 76, 12, "flat"),
        ("Potential Energy Curve", "Work Energy & Power", 65, 8, "flat"),
    ]
    
    for name, chapter, score, attempts, trend in default_concepts:
        ConceptProficiency.objects.get_or_create(
            user=user,
            concept_name=name,
            defaults={
                "chapter": chapter,
                "score": score,
                "attempts": attempts,
                "correct_attempts": int(attempts * (score / 100.0)),
                "trend": trend,
            }
        )
        
    # Seed StudyStreak
    StudyStreak.objects.get_or_create(
        user=user,
        defaults={
            "current_streak": 4,
            "longest_streak": 7,
            "last_study_date": timezone.now().date(),
        }
    )


class DashboardView(APIView, _SessionMixin):
    permission_classes = (AllowAny if getattr(settings, "CHATBOT_AUTH_DISABLED", False) else IsAuthenticated,)

    def get(self, request):
        user = self._get_actor_user(request)
        
        if not ConceptProficiency.objects.filter(user=user).exists():
            seed_default_metrics(user)
            
        proficiencies = ConceptProficiency.objects.filter(user=user)
        streak, _ = StudyStreak.objects.get_or_create(user=user)
        
        # 1. Calculate stats
        total_score = sum(p.score for p in proficiencies)
        total_concepts = proficiencies.count()
        overall_proficiency = int(total_score / total_concepts) if total_concepts > 0 else 0
        
        total_attempted = proficiencies.filter(attempts__gt=0).count()
        
        weak_concepts_queryset = proficiencies.filter(score__lt=50)
        weak_count = weak_concepts_queryset.count()
        weak_list = [p.concept_name for p in weak_concepts_queryset]
        
        # Build 7-day dots array (True if studied that day)
        today = timezone.now().date()
        dots = []
        for i in range(6, -1, -1):  # 7 days: 6 days ago → today
            day = today - datetime.timedelta(days=i)
            if streak.last_study_date and day <= streak.last_study_date:
                # Within the current streak window
                days_diff = (streak.last_study_date - day).days
                dots.append(days_diff < streak.current_streak)
            else:
                dots.append(False)

        stats = [
            {
                "id": "proficiency",
                "label": "Overall Proficiency",
                "value": f"{overall_proficiency}%",
                "subtext": f"across {total_attempted} attempted concepts"
            },
            {
                "id": "weak_concepts",
                "label": "Concepts Flagged Weak",
                "value": str(weak_count),
                "subtext": "need focused attention",
                "list": weak_list
            },
            {
                "id": "streak",
                "label": "Session Streak",
                "value": str(streak.current_streak),
                "subtext": "days in a row",
                "dots": dots
            }
        ]
        
        # 2. Group concepts by chapter
        chapters_names = ["Laws of Motion", "Work Energy & Power", "Rotational Motion"]
        chapters_data = []
        
        for ch_name in chapters_names:
            ch_proficiencies = proficiencies.filter(chapter=ch_name)
            ch_total_score = sum(p.score for p in ch_proficiencies)
            ch_count = ch_proficiencies.count()
            ch_overall_score = int(ch_total_score / ch_count) if ch_count > 0 else 0
            
            concepts_list = []
            for p in ch_proficiencies:
                tag = None
                if p.score < 50:
                    tag = "WEAK"
                elif p.score >= 75:
                    tag = "STRONG"

                accuracy = int((p.correct_attempts / p.attempts) * 100) if p.attempts > 0 else 0

                concepts_list.append({
                    "name": p.concept_name,
                    "score": p.score,
                    "attempts": p.attempts,
                    "accuracy": accuracy,
                    "tag": tag
                })
                
            chapters_data.append({
                "name": ch_name,
                "conceptCount": ch_count,
                "overallScore": ch_overall_score,
                "concepts": concepts_list
            })
            
        conceptHealth = {
            "title": "Physics — Concept Health",
            "tabs": chapters_names,
            "chapters": chapters_data
        }
        
        return Response({
            "stats": stats,
            "conceptHealth": conceptHealth
        })


from apis.viewsets import BaseModelViewSet, UserPrimaryKeyViewSet, UserScopedViewSet
from analytics.models import (
    Assessment,
    AssessmentQuestion,
    ChapterProgress,
    ConceptMastery,
    ConceptProficiency,
    DailyActivity,
    DailyProficiencySnapshot,
    LearningGap,
    PracticeAttempt,
    ProficiencySnapshot,
    QuestionAttempt,
    Recommendation,
    Streak,
    StudyStreak,
    WeeklyImprovement,
)
from analytics.serializers import (
    AssessmentQuestionSerializer,
    AssessmentSerializer,
    ChapterProgressSerializer,
    ConceptMasterySerializer,
    ConceptProficiencySerializer,
    DailyActivitySerializer,
    DailyProficiencySnapshotSerializer,
    LearningGapSerializer,
    PracticeAttemptSerializer,
    ProficiencySnapshotSerializer,
    QuestionAttemptSerializer,
    RecommendationSerializer,
    StreakSerializer,
    StudyStreakSerializer,
    WeeklyImprovementSerializer,
)


class ConceptProficiencyViewSet(UserScopedViewSet):
    queryset = ConceptProficiency.objects.select_related("user").all()
    serializer_class = ConceptProficiencySerializer
    filterset_fields = ("chapter", "trend", "user")
    search_fields = ("concept_name", "chapter")
    ordering_fields = ("score", "last_attempted", "attempts")


class StudyStreakLegacyViewSet(UserScopedViewSet):
    queryset = StudyStreak.objects.select_related("user").all()
    serializer_class = StudyStreakSerializer
    filterset_fields = ("user")
    ordering_fields = ("current_streak", "longest_streak")


class DailyProficiencySnapshotViewSet(UserScopedViewSet):
    queryset = DailyProficiencySnapshot.objects.select_related("user").all()
    serializer_class = DailyProficiencySnapshotSerializer
    filterset_fields = ("chapter", "date", "user")
    ordering_fields = ("date", "avg_score")


class PracticeAttemptViewSet(UserScopedViewSet):
    queryset = PracticeAttempt.objects.select_related("user").all()
    serializer_class = PracticeAttemptSerializer
    filterset_fields = ("chapter", "question_type", "is_correct", "mistake_type", "user")
    search_fields = ("concept_name", "chapter", "question_id")
    ordering_fields = ("attempted_at", "difficulty")


class WeeklyImprovementViewSet(UserScopedViewSet):
    queryset = WeeklyImprovement.objects.select_related("user").all()
    serializer_class = WeeklyImprovementSerializer
    filterset_fields = ("week_start", "user")
    search_fields = ("concept_name")
    ordering_fields = ("week_start", "delta")


class ConceptMasteryViewSet(UserScopedViewSet):
    queryset = ConceptMastery.objects.select_related("user", "concept").all()
    serializer_class = ConceptMasterySerializer
    filterset_fields = ("status", "is_flagged_weak", "user", "concept")
    ordering_fields = ("mastery_score", "updated_at", "last_practiced_at")


class ChapterProgressViewSet(UserScopedViewSet):
    queryset = ChapterProgress.objects.select_related("user", "chapter").all()
    serializer_class = ChapterProgressSerializer
    filterset_fields = ("chapter", "user")
    ordering_fields = ("mastery_score", "completion_percent", "updated_at")


class ProficiencySnapshotViewSet(UserScopedViewSet):
    queryset = ProficiencySnapshot.objects.select_related("user", "subject").all()
    serializer_class = ProficiencySnapshotSerializer
    filterset_fields = ("subject", "snapshot_date", "user")
    ordering_fields = ("snapshot_date", "proficiency")


class LearningGapViewSet(UserScopedViewSet):
    queryset = LearningGap.objects.select_related("user", "concept").all()
    serializer_class = LearningGapSerializer
    filterset_fields = ("severity", "source", "user", "concept")
    ordering_fields = ("detected_at", "resolved_at", "severity")


class RecommendationViewSet(UserScopedViewSet):
    queryset = Recommendation.objects.select_related("user", "concept", "content_item").all()
    serializer_class = RecommendationSerializer
    filterset_fields = ("type", "user", "concept", "content_item")
    search_fields = ("reason")
    ordering_fields = ("score", "created_at", "served_at")


class QuestionAttemptViewSet(UserScopedViewSet):
    queryset = QuestionAttempt.objects.select_related("user", "content_item", "study_session").all()
    serializer_class = QuestionAttemptSerializer
    filterset_fields = ("is_correct", "error_type", "user", "content_item", "study_session")
    ordering_fields = ("attempted_at", "attempt_number")


class StreakViewSet(UserPrimaryKeyViewSet):
    queryset = Streak.objects.select_related("user").all()
    serializer_class = StreakSerializer
    lookup_field = "user_id"


class DailyActivityViewSet(UserScopedViewSet):
    queryset = DailyActivity.objects.select_related("user").all()
    serializer_class = DailyActivitySerializer
    filterset_fields = ("activity_date", "goal_met", "user")
    ordering_fields = ("activity_date", "minutes_studied")


class AssessmentViewSet(UserScopedViewSet):
    queryset = Assessment.objects.select_related("user", "chapter", "concept").all()
    serializer_class = AssessmentSerializer
    filterset_fields = ("type", "status", "user", "chapter", "concept")
    ordering_fields = ("started_at", "completed_at", "score")


class AssessmentQuestionViewSet(BaseModelViewSet):
    queryset = AssessmentQuestion.objects.select_related("assessment", "content_item").all()
    serializer_class = AssessmentQuestionSerializer
    filterset_fields = ("assessment", "content_item", "is_correct", "is_flagged")
    ordering_fields = ("step_index", "answered_at")

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if not user.is_authenticated:
            if getattr(settings, "CHATBOT_AUTH_DISABLED", False):
                return queryset
            return queryset.none()
        if user.is_staff:
            return queryset
        return queryset.filter(assessment__user=user)
