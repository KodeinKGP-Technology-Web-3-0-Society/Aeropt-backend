from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from sandbox.orchestrator import build_action_queue
from sandbox.readiness import compute_readiness


class SandboxQueueView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        queue = build_action_queue(request.user)
        return Response({"queue": queue, "count": len(queue)})


class SandboxReadinessView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(compute_readiness(request.user))
