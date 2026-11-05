import uuid
from pathlib import Path

from django.conf import settings
from django.db import models


def document_upload_to(instance, filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    return f"documents/{instance.user_id}/{uuid.uuid4().hex}{suffix}"


class Document(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Queued"
        PROCESSING = "processing", "Processing"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="documents"
    )
    conversation = models.ForeignKey(
        "chat.Conversation",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="documents",
        help_text="Leave empty to make this document available to every conversation.",
    )
    title = models.CharField(max_length=200, blank=True)
    file = models.FileField(upload_to=document_upload_to)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    error = models.TextField(blank=True)
    size_bytes = models.PositiveBigIntegerField(default=0)
    chunk_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "status"], name="rag_user_status_idx"),
            models.Index(fields=["user", "conversation"], name="rag_user_conv_idx"),
        ]

    def __str__(self) -> str:
        return self.display_title

    @property
    def display_title(self) -> str:
        return self.title or Path(self.file.name).name or "Untitled document"

    @property
    def extension(self) -> str:
        return Path(self.file.name).suffix.lower().lstrip(".")

    @property
    def is_global(self) -> bool:
        return self.conversation_id is None

    @property
    def size_kb(self) -> int:
        return max(1, round(self.size_bytes / 1024))


class DocumentChunk(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="chunks")
    index = models.PositiveIntegerField()
    content = models.TextField()
    embedding = models.JSONField(default=list, blank=True)
    token_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["document_id", "index"]
        constraints = [
            models.UniqueConstraint(
                fields=["document", "index"], name="rag_chunk_unique_index"
            )
        ]
        indexes = [
            models.Index(fields=["document", "index"], name="rag_chunk_doc_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.document_id} #{self.index}"
