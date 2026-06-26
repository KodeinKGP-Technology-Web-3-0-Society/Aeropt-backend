from rest_framework import serializers
from django.utils import timezone

from apis.models import Concept, ContentItem
from chatbot.models import (
    ChatMessage,
    ChatSession,
    ConceptSnapshot,
    Conversation,
    ConversationMessage,
    MessageConcept,
    StudySession,
)
from apis.serializers import ConceptSerializer, ContentItemSerializer


class ConceptSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConceptSnapshot
        fields = ("concept_name", "score_at_time", "trend", "is_prerequisite")


class ChatMessageSerializer(serializers.ModelSerializer):
    concept_snapshots = ConceptSnapshotSerializer(many=True, read_only=True)

    class Meta:
        model = ChatMessage
        fields = (
            "id",
            "role",
            "content",
            "structured_response",
            "tokens_used",
            "latency_ms",
            "created_at",
            "concept_snapshots",
        )
        read_only_fields = fields


class ChatSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatSession
        fields = ("id", "title", "subject", "active_chapters", "started_at", "ended_at", "is_active")
        read_only_fields = ("id", "started_at", "ended_at", "is_active")


class ChatSessionDetailSerializer(ChatSessionSerializer):
    messages = ChatMessageSerializer(many=True, read_only=True)

    class Meta(ChatSessionSerializer.Meta):
        fields = ChatSessionSerializer.Meta.fields + ("messages",)


class CreateChatSessionSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200, required=False, allow_blank=True)
    subject = serializers.CharField(max_length=50, required=False, default="Physics")
    active_chapters = serializers.ListField(
        child=serializers.CharField(max_length=100),
        required=False,
        default=list,
    )

    def create(self, validated_data):
        request = self.context["request"]
        actor_user = self.context.get("actor_user", request.user)
        ChatSession.objects.filter(user=actor_user, is_active=True).update(
            is_active=False,
            ended_at=timezone.now(),
        )
        title = validated_data.get("title") or "New Session"
        return ChatSession.objects.create(
            user=actor_user,
            title=title,
            subject=validated_data.get("subject", "Physics"),
            active_chapters=validated_data.get("active_chapters", []),
            is_active=True,
        )


class SendMessageSerializer(serializers.Serializer):
    content = serializers.CharField(allow_blank=False, trim_whitespace=True)


class StudySessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudySession
        fields = ("id", "user", "type", "started_at", "ended_at", "duration_seconds")
        read_only_fields = ("id", "started_at", "user")


class ConversationSerializer(serializers.ModelSerializer):
    source_content_item = ContentItemSerializer(read_only=True)
    source_content_item_id = serializers.PrimaryKeyRelatedField(
        queryset=ContentItem.objects.all(),
        source="source_content_item",
        write_only=True,
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Conversation
        fields = (
            "id",
            "user",
            "study_session",
            "title",
            "source_content_item",
            "source_content_item_id",
            "created_at",
        )
        read_only_fields = ("id", "created_at", "user")


class ConversationMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConversationMessage
        fields = (
            "id",
            "conversation",
            "role",
            "content",
            "retrieved_content_ids",
            "model",
            "metadata",
            "created_at",
        )
        read_only_fields = ("id", "created_at")


class MessageConceptSerializer(serializers.ModelSerializer):
    concept = ConceptSerializer(read_only=True)
    concept_id = serializers.PrimaryKeyRelatedField(
        queryset=Concept.objects.all(),
        source="concept",
        write_only=True,
    )

    class Meta:
        model = MessageConcept
        fields = ("id", "message", "concept", "concept_id", "relation")
