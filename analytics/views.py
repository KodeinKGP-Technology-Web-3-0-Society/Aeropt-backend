"""
VIEWS — analytics app
=====================
No implementation yet. See models.py for the full schema and endpoint list.

Planned APIViews (Django REST Framework):

DashboardView  (APIView)
  - get()  GET /api/v1/analytics/dashboard/
    Aggregates ConceptProficiency + StudyStreak into a single Dashboard payload.
    Cache with Redis (key: dashboard:{user_id}, TTL 5 min).

ProgressView  (APIView)
  - get()  GET /api/v1/analytics/progress/
    Aggregates DailyProficiencySnapshot (last 14 days) + PracticeAttempt mistake
    breakdown + ConceptProficiency table + WeeklyImprovement.
    Cache with Redis (key: progress:{user_id}, TTL 15 min).

ConceptProficiencyListView  (ListAPIView)
  - get()  GET /api/v1/analytics/concepts/
    Returns all ConceptProficiency rows for the user.
    Supports ?chapter=... and ?weak_only=true.
    Called by chatbot to inject scores into the LLM system prompt.

PracticeAttemptCreateView  (CreateAPIView)
  - post()  POST /api/v1/analytics/practice-attempts/
    Saves PracticeAttempt, then:
      1. Upserts ConceptProficiency (score, accuracy, trend)
      2. Updates StudyStreak
      3. Upserts DailyProficiencySnapshot for today
      4. Invalidates dashboard/progress cache

StreakView  (RetrieveAPIView)
  - get()  GET /api/v1/analytics/streak/

Signal handlers live in analytics/signals.py — connected to chatbot app signals.
"""

from django.shortcuts import render

# Views will be implemented here.
