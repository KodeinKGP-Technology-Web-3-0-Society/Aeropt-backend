"""
analytics/urls.py
=================
Mounted at: /api/v1/analytics/

All routes below are relative to /api/v1/analytics/.
"""

from django.urls import path

# from analytics.views import (
#     DashboardView,
#     ProgressView,
#     ConceptProficiencyListView,
#     PracticeAttemptCreateView,
#     StreakView,
# )

urlpatterns = [
    # GET /api/v1/analytics/dashboard/
    # Full Dashboard page payload — concept health, weak flags, streak, chapter rollups
    # Cached in Redis (TTL 5 min); cache invalidated on new chat message or practice attempt
    # path('dashboard/', DashboardView.as_view(), name='analytics-dashboard'),

    # GET /api/v1/analytics/progress/
    # Full Progress page payload — 14-day chart, mistake breakdown, concept table
    # Cached in Redis (TTL 15 min)
    # path('progress/', ProgressView.as_view(), name='analytics-progress'),

    # GET /api/v1/analytics/concepts/
    # All ConceptProficiency rows for the logged-in user
    # Query params: ?chapter=laws_of_motion   ?weak_only=true
    # Used by chatbot to inject concept scores into the LLM system prompt
    # path('concepts/', ConceptProficiencyListView.as_view(), name='analytics-concepts'),

    # POST /api/v1/analytics/practice-attempts/
    # Log a Practice page question attempt; triggers score recalculation + streak update
    # path('practice-attempts/', PracticeAttemptCreateView.as_view(), name='analytics-practice-attempts'),

    # GET /api/v1/analytics/streak/
    # Returns { "current": 4, "longest": 7 }
    # path('streak/', StreakView.as_view(), name='analytics-streak'),
]
