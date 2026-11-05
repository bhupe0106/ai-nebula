from django.contrib import admin

from .models import Conversation, Message


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    fields = ("role", "content", "model", "prompt_tokens", "completion_tokens", "created_at")
    readonly_fields = fields
    can_delete = False
    max_num = 0


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "resolved_model", "temperature", "is_archived", "updated_at")
    list_filter = ("is_archived", "model", "created_at")
    search_fields = ("title", "user__email", "messages__content")
    autocomplete_fields = ("user",)
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "updated_at"
    inlines = [MessageInline]

    @admin.display(description="Model")
    def resolved_model(self, obj):
        return obj.resolved_model


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("created_at", "conversation", "role", "total_tokens", "model", "error")
    list_filter = ("role", "created_at")
    search_fields = ("content", "conversation__title", "conversation__user__email")
    autocomplete_fields = ("conversation",)
    readonly_fields = (
        "id",
        "conversation",
        "role",
        "content",
        "model",
        "prompt_tokens",
        "completion_tokens",
        "latency_ms",
        "error",
        "metadata",
        "created_at",
    )

    @admin.display(description="Tokens")
    def total_tokens(self, obj):
        return obj.total_tokens
