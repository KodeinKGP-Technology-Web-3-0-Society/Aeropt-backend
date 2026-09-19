import logging

from django.core.cache import cache
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apis.cache_layer import TTL_SANDBOX_QUEUE, get_or_set, sandbox_queue_key
from sandbox.models import SandboxActionEvent, SandboxActionStatus, canonical_action_key
from sandbox.orchestrator import build_action_queue, build_queue_meta
from sandbox.readiness import compute_readiness
from sandbox.serializers import (
    SandboxActionEventRequestSerializer,
    SandboxActionResultSerializer,
    SandboxQueueSerializer,
    SandboxReadinessSerializer,
)

logger = logging.getLogger(__name__)


def _queue_payload(user) -> dict:
    queue = build_action_queue(user)
    meta = build_queue_meta(user)
    return {"queue": queue, "count": len(queue), **meta}


class SandboxQueueView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: SandboxQueueSerializer})
    def get(self, request):
        payload = get_or_set(
            sandbox_queue_key(request.user),
            TTL_SANDBOX_QUEUE,
            lambda: _queue_payload(request.user),
        )
        return Response(payload)


class _SandboxActionDecisionView(APIView):
    """Record one decision about one computed queue card.

    Idempotent by construction: the row is keyed on (user, action_id, date), so
    a repeated POST updates the same row and reports `already_recorded: true`
    rather than erroring or adding a second event.
    """

    permission_classes = [IsAuthenticated]
    status_value: str = ""

    @extend_schema(
        request=SandboxActionEventRequestSerializer,
        responses={200: SandboxActionResultSerializer},
    )
    def post(self, request, action_id: str):
        body = SandboxActionEventRequestSerializer(data=request.data or {})
        body.is_valid(raise_exception=True)
        context = body.validated_data

        defaults = {"status": self.status_value, "action_id": action_id}
        for field in ("action", "concept_id", "roadmap_node_id"):
            value = (context.get(field) or "").strip()
            if value:
                defaults[field] = value

        event, created = SandboxActionEvent.objects.update_or_create(
            user=request.user,
            target_key=canonical_action_key(action_id),
            for_date=timezone.localdate(),
            defaults=defaults,
        )

        # Drop the cached queue so the very next GET reflects this decision.
        cache.delete(sandbox_queue_key(request.user))
        logger.info(
            "sandbox action %s marked %s for user %s (new=%s)",
            action_id,
            self.status_value,
            request.user.pk,
            created,
        )

        payload = get_or_set(
            sandbox_queue_key(request.user),
            TTL_SANDBOX_QUEUE,
            lambda: _queue_payload(request.user),
        )
        return Response(
            SandboxActionResultSerializer(
                {"event": event, "already_recorded": not created, "queue": payload}
            ).data
        )


class SandboxActionCompleteView(_SandboxActionDecisionView):
    status_value = SandboxActionStatus.COMPLETED


class SandboxActionDismissView(_SandboxActionDecisionView):
    status_value = SandboxActionStatus.DISMISSED


class SandboxReadinessView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: SandboxReadinessSerializer})
    def get(self, request):
        return Response(compute_readiness(request.user))
