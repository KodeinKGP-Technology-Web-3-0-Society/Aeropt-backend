from django.urls import path
from classroom.views import ClassroomEvidenceView, ClassroomHomeView, TodayDecisionView

urlpatterns = [
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
]
