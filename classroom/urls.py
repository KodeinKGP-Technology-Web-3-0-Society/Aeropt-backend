from django.urls import path
from classroom.views import ClassroomHomeView

urlpatterns = [
    path("home/", ClassroomHomeView.as_view(), name="classroom-home"),
]
