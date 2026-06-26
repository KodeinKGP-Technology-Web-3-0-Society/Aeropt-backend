from django.urls import path
from rest_framework.routers import DefaultRouter

from chatbot.views import (
    ChatMessageListCreateView,
    ChatMessageStreamView,
    ChatSessionDetailView,
    ChatSessionListCreateView,
    ConceptSnapshotView,
    ConversationMessageViewSet,
    ConversationViewSet,
    EndSessionView,
    MessageConceptViewSet,
    StudySessionViewSet,
)

router = DefaultRouter()
router.register(r"study-sessions", StudySessionViewSet, basename="study-session")
router.register(r"conversations", ConversationViewSet, basename="conversation")
router.register(r"conversation-messages", ConversationMessageViewSet, basename="conversation-message")
router.register(r"message-concepts", MessageConceptViewSet, basename="message-concept")

legacy_urlpatterns = [
    path("sessions/", ChatSessionListCreateView.as_view(), name="session-list-create"),
    path("sessions/<uuid:session_id>/", ChatSessionDetailView.as_view(), name="session-detail"),
    path("sessions/<uuid:session_id>/end/", EndSessionView.as_view(), name="session-end"),
    path(
        "sessions/<uuid:session_id>/messages/",
        ChatMessageListCreateView.as_view(),
        name="message-list-create",
    ),
    path(
        "sessions/<uuid:session_id>/messages/<uuid:msg_id>/stream/",
        ChatMessageStreamView.as_view(),
        name="message-stream",
    ),
    path("sessions/<uuid:session_id>/concepts/", ConceptSnapshotView.as_view(), name="session-concepts"),
]

urlpatterns = legacy_urlpatterns + router.urls
