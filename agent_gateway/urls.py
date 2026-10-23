from django.urls import re_path

from agent_gateway.views import AgentGatewayView

urlpatterns = [
    # Optional trailing slash: the Next.js dev rewrite appends one to every /api/v1 path.
    re_path(r"^(?P<path>.+?)/?$", AgentGatewayView.as_view(), name="agent-gateway"),
]
