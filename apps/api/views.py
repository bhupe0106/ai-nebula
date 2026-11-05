"""REST API: JWT-authenticated conversation and document endpoints."""
from __future__ import annotations

import logging

from django.db.models import Sum
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.chat.models import Conversation, Message
from apps.chat.services import QuotaExceeded, generate_reply
from apps.rag.models import Document
from apps.rag.services import queue_ingestion
from apps.usage.services import quota_status

from .serializers import (
    ConversationCreateSerializer,
    ConversationSerializer,
    DocumentCreateSerializer,
    DocumentSerializer,
    MessageSerializer,
    SendMessageSerializer,
)

logger = logging.getLogger(__name__)


class ConversationViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    lookup_field = "pk"

    def get_queryset(self):
        return Conversation.objects.filter(user=self.request.user).order_by("-updated_at")

    def get_serializer_class(self):
        if self.action == "create":
            return ConversationCreateSerializer
        return ConversationSerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=["get", "post"], url_path="messages")
    def messages(self, request, pk=None):
        conversation = self.get_object()

        if request.method == "GET":
            queryset = conversation.messages.all()
            page = self.paginate_queryset(queryset)
            if page is not None:
                return self.get_paginated_response(MessageSerializer(page, many=True).data)
            return Response(MessageSerializer(queryset, many=True).data)

        serializer = SendMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            assistant_message = generate_reply(
                conversation, serializer.validated_data["content"]
            )
        except QuotaExceeded as exc:
            return Response(
                {"detail": str(exc), "code": "quota_exceeded"},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        except Exception:
            logger.exception("API chat send failed")
            return Response(
                {"detail": "The model provider failed to answer. Try again."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        user_message = (
            conversation.messages.filter(role=Message.Role.USER)
            .order_by("-created_at")
            .first()
        )
        return Response(
            {
                "user_message": MessageSerializer(user_message).data,
                "assistant_message": MessageSerializer(assistant_message).data,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="clear")
    def clear(self, request, pk=None):
        conversation = self.get_object()
        conversation.messages.all().delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="archive")
    def archive(self, request, pk=None):
        conversation = self.get_object()
        conversation.is_archived = not conversation.is_archived
        conversation.save(update_fields=["is_archived", "updated_at"])
        return Response(ConversationSerializer(conversation).data)


class DocumentViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Document.objects.filter(user=self.request.user).select_related("conversation")

    def get_serializer_class(self):
        if self.action == "create":
            return DocumentCreateSerializer
        return DocumentSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        upload = data["file"]
        document = Document.objects.create(
            user=request.user,
            conversation=data.get("conversation"),
            title=data.get("title", ""),
            file=upload,
            size_bytes=upload.size,
        )
        queue_ingestion(document)
        document.refresh_from_db()
        return Response(DocumentSerializer(document).data, status=status.HTTP_201_CREATED)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response(
            {
                "id": user.pk,
                "email": user.email,
                "display_name": user.display_name,
                "quota": quota_status(user),
            }
        )


class UsageView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        aggregate = request.user.usage_events.aggregate(
            prompt=Sum("prompt_tokens"), completion=Sum("completion_tokens")
        )
        return Response(
            {
                "quota": quota_status(request.user),
                "lifetime": {
                    "prompt_tokens": aggregate["prompt"] or 0,
                    "completion_tokens": aggregate["completion"] or 0,
                    "total_tokens": (aggregate["prompt"] or 0)
                    + (aggregate["completion"] or 0),
                },
            }
        )
