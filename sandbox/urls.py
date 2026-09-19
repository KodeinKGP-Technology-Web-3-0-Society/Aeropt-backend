from django.urls import path

from sandbox.views import (
    SandboxActionCompleteView,
    SandboxActionDismissView,
    SandboxQueueView,
    SandboxReadinessView,
)

urlpatterns = [
    path("queue/", SandboxQueueView.as_view(), name="sandbox-queue"),
    path(
        "queue/<str:action_id>/complete/",
        SandboxActionCompleteView.as_view(),
        name="sandbox-action-complete",
    ),
    path(
        "queue/<str:action_id>/dismiss/",
        SandboxActionDismissView.as_view(),
        name="sandbox-action-dismiss",
    ),
    path("readiness/", SandboxReadinessView.as_view(), name="sandbox-readiness"),
]
