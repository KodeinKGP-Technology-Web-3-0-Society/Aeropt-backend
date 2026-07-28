from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from sandbox.orchestrator import build_action_queue, build_queue_meta
from sandbox.readiness import compute_readiness
from apis.cache_layer import TTL_SANDBOX_QUEUE, get_or_set, sandbox_queue_key


class SandboxQueueView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        def _build():
            queue = build_action_queue(request.user)
            meta = build_queue_meta(request.user)
            return {"queue": queue, "count": len(queue), **meta}

        payload = get_or_set(sandbox_queue_key(request.user), TTL_SANDBOX_QUEUE, _build)
        return Response(payload)


class SandboxReadinessView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(compute_readiness(request.user))
