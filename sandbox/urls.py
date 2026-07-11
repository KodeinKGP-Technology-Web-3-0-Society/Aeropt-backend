from django.urls import path

from sandbox.views import SandboxQueueView, SandboxReadinessView

urlpatterns = [
    path("queue/", SandboxQueueView.as_view(), name="sandbox-queue"),
    path("readiness/", SandboxReadinessView.as_view(), name="sandbox-readiness"),
]
