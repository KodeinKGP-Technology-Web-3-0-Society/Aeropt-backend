from django.urls import path
from classroom.views import ClassroomEvidenceView, ClassroomHomeView

urlpatterns = [
    path("home/", ClassroomHomeView.as_view(), name="classroom-home"),
    path("evidence/", ClassroomEvidenceView.as_view(), name="classroom-evidence"),
]
