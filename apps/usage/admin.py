from django.contrib import admin

from .models import UsageEvent


@admin.register(UsageEvent)
class UsageEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "kind", "model", "total_tokens")
    list_filter = ("kind", "created_at")
    search_fields = ("user__email", "model")
    autocomplete_fields = ("user", "conversation")
    readonly_fields = ("created_at",)
    date_hierarchy = "created_at"

    @admin.display(description="Tokens")
    def total_tokens(self, obj):
        return obj.total_tokens
