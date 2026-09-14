"""
APP: analytics
==============
The data backbone for the Dashboard and Progress pages.

This app computes and stores all learning metrics derived from chat sessions
(chatbot app) and practice attempts. It is the source of truth for every
number and chart shown in the UI.

  Dashboard page (from Figma):
    - Overall Proficiency %         e.g. "64% across 18 attempted concepts"
    - Concepts Flagged Weak         e.g. "5 — Torque, Constraint Motion, Rolling with Slipping"
    - Session Streak                e.g. "4 days in a row" with 7 dot indicators
    - Physics Concept Health cards  per-concept: score bar, color, WEAK badge, attempt count
    - Chapter rollup score          e.g. "Laws of Motion 72%", "Rotational Motion 48%"

  Progress page (from Figma):
    - Total Questions Attempted     e.g. 147
    - Overall Accuracy              e.g. 71% correct on first attempt
    - Most Improved concept         e.g. "Work-Energy Theorem" (most delta this week)
    - Proficiency Over Time chart   line graph per chapter, last 14 days
    - Where Mistakes Come From      Conceptual 34%, Procedural 28%, Calculation 22%, Misinterpretation 16%
    - Concept Breakdown table       concept, chapter, score bar, attempts, accuracy, last attempted, trend sparkline

TABLES PLANNED
--------------
1. ConceptProficiency  (core score table — updated after every chat message or practice attempt)
   - user             : FK → users.User
   - concept_name     : CharField  (e.g. "Torque", "Newton's First Law")
   - chapter          : CharField  (e.g. "Laws of Motion", "Rotational Motion")
   - score            : PositiveSmallIntegerField (0–100)
                        Color thresholds: ≥70 → green, 50–69 → orange/yellow, <50 → red + WEAK badge
   - attempts         : PositiveIntegerField — total attempts across chat + practice
   - correct_attempts : PositiveIntegerField — used to compute accuracy %
   - last_attempted   : DateTimeField
   - trend            : CharField, choices = ['up', 'down', 'flat']
                        Computed by comparing score vs. score 3 days ago
   unique_together: (user, concept_name)

2. DailyProficiencySnapshot  (time-series for the line chart on Progress page)
   - user             : FK → users.User
   - chapter          : CharField
   - date             : DateField
   - avg_score        : FloatField — mean ConceptProficiency.score across concepts in chapter
   unique_together: (user, chapter, date)
   (Written by a Celery beat task at midnight UTC; one row per user+chapter+day)

3. StudyStreak
   - user             : OneToOneField → users.User
   - current_streak   : PositiveIntegerField — consecutive study days (Dashboard dot row)
   - longest_streak   : PositiveIntegerField
   - last_study_date  : DateField — updated on any chat message or practice attempt

4. PracticeAttempt  (records each Practice page question attempt)
   - user             : FK → users.User
   - concept_name     : CharField
   - chapter          : CharField
   - question_id      : CharField — stable identifier for the question
   - question_type    : CharField, choices = ['SCQ', 'MCQ', 'Numerical', 'PYQ']
   - difficulty       : PositiveSmallIntegerField (1–5, matching Practice page filter buttons)
   - selected_answer  : CharField
   - is_correct       : BooleanField
   - time_taken_secs  : PositiveIntegerField — timer from Practice page ("Time: 1m 23s")
   - mistake_type     : CharField, choices = ['Conceptual', 'Procedural', 'Calculation', 'Misinterpretation']
                        null when is_correct=True; drives the "Where mistakes come from" chart
   - attempted_at     : DateTimeField (auto_now_add)

5. WeeklyImprovement  (most-improved concept card on Progress page)
   - user             : FK → users.User
   - concept_name     : CharField
   - score_7d_ago     : PositiveSmallIntegerField
   - score_now        : PositiveSmallIntegerField
   - delta            : IntegerField — score_now − score_7d_ago
   - week_start       : DateField
   (Recomputed by Celery beat every Sunday; top record by delta per user = "Most Improved")

API ENDPOINTS NEEDED
--------------------
GET  /api/v1/analytics/dashboard/
  — Single payload for the entire Dashboard page:
    {
      "overall_proficiency": 64,
      "total_concepts_attempted": 18,
      "weak_concepts": [
        {"name": "Torque",            "score": 34},
        {"name": "Constraint Motion", "score": 34},
        {"name": "Rolling with Slipping", "score": 38}
      ],
      "session_streak": {
        "current": 4,
        "longest": 7,
        "dots": [true, true, true, true, false, false, false]
      },
      "chapters": [
        {
          "name": "Laws of Motion",
          "rollup_score": 72,
          "concepts": [
            {"name": "Newton's First Law", "score": 82, "attempts": 14, "is_weak": false},
            {"name": "Constraint Motion",  "score": 34, "attempts": 6,  "is_weak": true},
            ...
          ]
        },
        ...
      ]
    }
  Cache: Redis, TTL 5 min per user; invalidate on new chat message or practice attempt.

GET  /api/v1/analytics/progress/
  — Single payload for the entire Progress page:
    {
      "total_attempts": 147,
      "overall_accuracy": 71,
      "most_improved": {"concept": "Work-Energy Theorem", "delta": 22},
      "proficiency_over_time": [
        {"date": "2025-02-01", "Laws of Motion": 45, "Work Energy and Power": 38, "Rotational Motion": 22},
        ...
      ],
      "mistake_breakdown": {
        "Conceptual":        {"count": 14, "pct": 34},
        "Procedural":        {"count": 12, "pct": 28},
        "Calculation":       {"count": 9,  "pct": 22},
        "Misinterpretation": {"count": 7,  "pct": 16}
      },
      "concept_breakdown": [
        {
          "concept": "Torque",
          "chapter": "Rotational Motion",
          "score": 32,
          "attempts": 18,
          "accuracy": 33,
          "last_attempted": "2h ago",
          "trend_data": [28, 29, 30, 31, 32]
        },
        ...
      ]
    }
  Cache: Redis, TTL 15 min per user.

GET  /api/v1/analytics/concepts/
  — Full list of ConceptProficiency rows for the logged-in user.
  — Used by the chatbot app to inject concept scores into the LLM system prompt.
  — Query params: ?chapter=laws_of_motion   ?weak_only=true

POST /api/v1/analytics/practice-attempts/
  — Log a practice attempt (called by frontend Practice page after user submits).
  — Side effects:
      1. Upsert ConceptProficiency (recalculate score, accuracy, trend)
      2. Update StudyStreak
      3. Upsert DailyProficiencySnapshot for today
      4. Invalidate dashboard/progress cache for the user

GET  /api/v1/analytics/streak/
  — Returns { "current": 4, "longest": 7 }

SIGNAL HANDLER (analytics/signals.py — not a view)
  on_concept_mentioned(sender, user, concepts_data, ...)
    Receives signal fired by chatbot app after each assistant message.
    Updates ConceptProficiency rows + StudyStreak + invalidates cache.
"""

from django.conf import settings
from django.db import models
import uuid


class MasteryStatus(models.TextChoices):
    NOT_STARTED = "NOT_STARTED", "Not Started"
    LEARNING = "LEARNING", "Learning"
    WEAK = "WEAK", "Weak"
    PROFICIENT = "PROFICIENT", "Proficient"
    MASTERED = "MASTERED", "Mastered"


class SessionType(models.TextChoices):
    DOUBT = "DOUBT", "Doubt"
    PRACTICE = "PRACTICE", "Practice"
    DIAGNOSTIC = "DIAGNOSTIC", "Diagnostic"
    REVISION = "REVISION", "Revision"
    MOCK = "MOCK", "Mock"


class ErrorType(models.TextChoices):
    CONCEPTUAL_GAP = "CONCEPTUAL_GAP", "Conceptual Gap"
    CALCULATION_ERROR = "CALCULATION_ERROR", "Calculation Error"
    MISINTERPRETATION = "MISINTERPRETATION", "Misinterpretation"
    PROCEDURAL_SLIP = "PROCEDURAL_SLIP", "Procedural Slip"


class RecommendationType(models.TextChoices):
    NEXT_QUESTION = "NEXT_QUESTION", "Next Question"
    REVISE_CONCEPT = "REVISE_CONCEPT", "Revise Concept"
    LEARN_PREREQUISITE = "LEARN_PREREQUISITE", "Learn Prerequisite"
    PRACTICE_WEAK = "PRACTICE_WEAK", "Practice Weak"


class AssessmentType(models.TextChoices):
    DIAGNOSTIC = "DIAGNOSTIC", "Diagnostic"
    CHAPTER_TEST = "CHAPTER_TEST", "Chapter Test"
    MOCK = "MOCK", "Mock"


class AssessmentStatus(models.TextChoices):
    IN_PROGRESS = "IN_PROGRESS", "In Progress"
    COMPLETED = "COMPLETED", "Completed"
    ABANDONED = "ABANDONED", "Abandoned"





class ConceptMastery(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="concept_masteries")
    concept = models.ForeignKey("apis.Concept", on_delete=models.CASCADE, related_name="concept_masteries")
    mastery_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=MasteryStatus.choices, default=MasteryStatus.NOT_STARTED)
    is_flagged_weak = models.BooleanField(default=False)
    total_attempts = models.IntegerField(default=0)
    correct_attempts = models.IntegerField(default=0)
    last_practiced_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "concept_mastery"
        unique_together = (("user", "concept"),)
        ordering = ("concept_id",)

    def __str__(self):
        return f"{self.user_id}:{self.concept_id}:{self.mastery_score}"


class ChapterProgress(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chapter_progress")
    chapter = models.ForeignKey("apis.Chapter", on_delete=models.CASCADE, related_name="chapter_progress")
    mastery_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    completion_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "chapter_progress"
        unique_together = (("user", "chapter"),)
        ordering = ("chapter_id",)

    def __str__(self):
        return f"{self.user_id}:{self.chapter_id}"


class ProficiencySnapshot(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="proficiency_snapshots")
    subject = models.ForeignKey("apis.Subject", on_delete=models.CASCADE, related_name="proficiency_snapshots")
    snapshot_date = models.DateField()
    proficiency = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    class Meta:
        db_table = "proficiency_snapshots"
        unique_together = (("user", "subject", "snapshot_date"),)
        ordering = ("-snapshot_date",)

    def __str__(self):
        return f"{self.user_id}:{self.subject_id}:{self.snapshot_date}"


class LearningGap(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="learning_gaps")
    concept = models.ForeignKey("apis.Concept", on_delete=models.CASCADE, related_name="learning_gaps")
    severity = models.SmallIntegerField(default=1)
    source = models.CharField(max_length=20, choices=SessionType.choices)
    detected_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "learning_gaps"
        ordering = ("-detected_at",)

    def __str__(self):
        return f"{self.user_id}:{self.concept_id}:{self.severity}"


class Recommendation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="recommendations")
    type = models.CharField(max_length=30, choices=RecommendationType.choices)
    concept = models.ForeignKey(
        "apis.Concept", on_delete=models.SET_NULL, null=True, blank=True, related_name="recommendations"
    )
    content_item = models.ForeignKey(
        "apis.ContentItem", on_delete=models.SET_NULL, null=True, blank=True, related_name="recommendations"
    )
    reason = models.CharField(max_length=280, blank=True, default="")
    score = models.DecimalField(max_digits=6, decimal_places=4, default=0)
    served_at = models.DateTimeField(null=True, blank=True)
    dismissed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "recommendations"
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.user_id}:{self.type}"


class QuestionAttempt(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="question_attempts")
    content_item = models.ForeignKey("apis.ContentItem", on_delete=models.CASCADE, related_name="question_attempts")
    submitted_answer = models.JSONField(default=dict, blank=True)
    is_correct = models.BooleanField()
    error_type = models.CharField(max_length=30, choices=ErrorType.choices, blank=True, default="")
    time_taken_seconds = models.IntegerField(default=0)
    hint_used = models.BooleanField(default=False)
    attempt_number = models.SmallIntegerField(default=1)
    attempted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "question_attempts"
        ordering = ("-attempted_at",)

    def __str__(self):
        return f"{self.user_id}:{self.content_item_id}"


class Streak(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, primary_key=True, related_name="streak")
    current_streak = models.SmallIntegerField(default=0)
    longest_streak = models.SmallIntegerField(default=0)
    last_active_date = models.DateField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "streaks"

    def __str__(self):
        return f"{self.user_id}: current={self.current_streak}"


class DailyActivity(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="daily_activities")
    activity_date = models.DateField()
    minutes_studied = models.SmallIntegerField(default=0)
    questions_attempted = models.SmallIntegerField(default=0)
    doubts_asked = models.SmallIntegerField(default=0)
    goal_met = models.BooleanField(default=False)

    class Meta:
        db_table = "daily_activity"
        unique_together = (("user", "activity_date"),)
        ordering = ("-activity_date",)

    def __str__(self):
        return f"{self.user_id}:{self.activity_date}"


class Assessment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="assessments")
    type = models.CharField(max_length=20, choices=AssessmentType.choices)
    chapter = models.ForeignKey(
        "apis.Chapter", on_delete=models.SET_NULL, null=True, blank=True, related_name="assessments"
    )
    concept = models.ForeignKey(
        "apis.Concept", on_delete=models.SET_NULL, null=True, blank=True, related_name="assessments"
    )
    total_questions = models.SmallIntegerField(default=0)
    score = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    max_score = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=AssessmentStatus.choices, default=AssessmentStatus.IN_PROGRESS)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "assessments"
        ordering = ("-started_at",)

    def __str__(self):
        return f"{self.user_id}:{self.type}:{self.status}"


class AssessmentQuestion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, related_name="questions")
    content_item = models.ForeignKey("apis.ContentItem", on_delete=models.CASCADE, related_name="assessment_questions")
    step_index = models.SmallIntegerField(default=0)
    submitted_answer = models.JSONField(default=dict, blank=True)
    is_correct = models.BooleanField(null=True, blank=True)
    error_type = models.CharField(max_length=30, choices=ErrorType.choices, blank=True, default="")
    hint_shown = models.BooleanField(default=False)
    retries_count = models.SmallIntegerField(default=0)
    is_flagged = models.BooleanField(default=False)
    answered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "assessment_questions"
        ordering = ("step_index",)

    def __str__(self):
        return f"{self.assessment_id}:{self.step_index}"
