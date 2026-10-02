from django.urls import path
from classroom.views import (
    ClassroomEvidenceView,
    ClassroomHomeView,
    ClassroomSessionLookupView,
    ClassroomSessionView,
    TodayDecisionView,
    CalendarAPIView,
)

urlpatterns = [
    path("calendar/", CalendarAPIView.as_view(), name="classroom-calendar"),
    path("home/", ClassroomHomeView.as_view(), name="classroom-home"),
    path("evidence/", ClassroomEvidenceView.as_view(), name="classroom-evidence"),
    path(
        "today/<str:concept_id>/complete/",
        TodayDecisionView.as_view(),
        {"decision": "complete"},
        name="classroom-today-complete",
    ),
    path(
        "today/<str:concept_id>/dismiss/",
        TodayDecisionView.as_view(),
        {"decision": "dismiss"},
        name="classroom-today-dismiss",
    ),
    path("sessions/", ClassroomSessionView.as_view(), name="classroom-session-open"),
    path(
        "sessions/<str:agent_session_id>/",
        ClassroomSessionLookupView.as_view(),
        name="classroom-session-lookup",
    ),
]
