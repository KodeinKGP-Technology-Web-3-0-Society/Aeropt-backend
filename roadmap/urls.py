from django.urls import path

from roadmap.views import (
    RoadmapNextView,
    RoadmapProgressView,
    RoadmapSubjectsView,
    RoadmapView,
)

urlpatterns = [
    path("", RoadmapView.as_view(), name="roadmap"),
    path("subjects/", RoadmapSubjectsView.as_view(), name="roadmap-subjects"),
    path("next/", RoadmapNextView.as_view(), name="roadmap-next"),
    path("progress/", RoadmapProgressView.as_view(), name="roadmap-progress"),
]
