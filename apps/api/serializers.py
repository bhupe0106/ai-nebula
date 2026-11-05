from rest_framework import serializers

from apps.chat.models import Conversation, Message
from apps.rag.forms import validate_upload
from apps.rag.models import Document


class MessageSerializer(serializers.ModelSerializer):
    total_tokens = serializers.IntegerField(read_only=True)
    citations = serializers.SerializerMethodField()
    stopped = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = (
            "id",
            "role",
            "content",
            "model",
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "latency_ms",
            "error",
            "citations",
            "stopped",
            "created_at",
        )

    def get_citations(self, obj):
        return obj.citations

    def get_stopped(self, obj):
        return bool((obj.metadata or {}).get("stopped"))


class ConversationSerializer(serializers.ModelSerializer):
    resolved_model = serializers.CharField(read_only=True)
    message_count = serializers.IntegerField(source="messages.count", read_only=True)

    class Meta:
        model = Conversation
        fields = (
            "id",
            "title",
            "model",
            "resolved_model",
            "system_prompt",
            "temperature",
            "use_documents",
            "is_archived",
            "message_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at", "is_archived")


class ConversationCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Conversation
        fields = ("id", "title", "model", "system_prompt", "temperature", "use_documents")
        read_only_fields = ("id",)


class SendMessageSerializer(serializers.Serializer):
    content = serializers.CharField(max_length=8000, trim_whitespace=True)


class DocumentSerializer(serializers.ModelSerializer):
    display_title = serializers.CharField(read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Document
        fields = (
            "id",
            "title",
            "display_title",
            "conversation",
            "status",
            "status_display",
            "error",
            "size_bytes",
            "chunk_count",
            "created_at",
        )
        read_only_fields = ("status", "error", "size_bytes", "chunk_count", "created_at")


class DocumentCreateSerializer(serializers.Serializer):
    file = serializers.FileField()
    title = serializers.CharField(required=False, allow_blank=True, max_length=200)
    conversation = serializers.UUIDField(required=False, allow_null=True)

    def validate_file(self, value):
        validate_upload(value)
        return value

    def validate_conversation(self, value):
        if value is None:
            return None
        request = self.context.get("request")
        conversation = Conversation.objects.filter(pk=value, user=request.user).first()
        if conversation is None:
            raise serializers.ValidationError("Conversation not found.")
        return conversation
