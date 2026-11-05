from django.conf import settings
from django.db import models


class UsageEvent(models.Model):
    """One billable LLM operation (chat completion or embedding batch)."""

    class Kind(models.TextChoices):
        CHAT = "chat", "Chat completion"
        EMBEDDING = "embedding", "Embedding"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="usage_events"
    )
    conversation = models.ForeignKey(
        "chat.Conversation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="usage_events",
    )
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.CHAT)
    model = models.CharField(max_length=120, blank=True)
    prompt_tokens = models.PositiveIntegerField(default=0)
    completion_tokens = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "created_at"], name="usage_user_created_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} - {self.total_tokens} tokens ({self.user_id})"

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens
