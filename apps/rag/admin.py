from django.contrib import admin
from django.utils.html import format_html

from .models import Document, DocumentChunk
from .services import ingest_document_sync


class DocumentChunkInline(admin.TabularInline):
    model = DocumentChunk
    extra = 0
    fields = ("index", "token_count", "content")
    readonly_fields = ("index", "token_count", "content")
    can_delete = False
    max_num = 0
    show_change_link = True


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("display_title", "user", "scope", "status", "chunk_count", "size_kb", "created_at")
    list_filter = ("status", "conversation", "created_at")
    search_fields = ("title", "user__email", "file")
    readonly_fields = ("status", "error", "size_bytes", "chunk_count", "created_at", "updated_at")
    autocomplete_fields = ("user", "conversation")
    inlines = [DocumentChunkInline]
    actions = ["reingest"]

    @admin.display(description="Scope")
    def scope(self, obj):
        return "Global" if obj.is_global else "Conversation"

    @admin.action(description="Re-run ingestion for selected documents")
    def reingest(self, request, queryset):
        for document in queryset:
            ingest_document_sync(document.pk)
        self.message_user(request, f"Re-ingested {queryset.count()} document(s).")


@admin.register(DocumentChunk)
class DocumentChunkAdmin(admin.ModelAdmin):
    list_display = ("id", "document", "index", "token_count", "preview")
    list_filter = ("document",)
    search_fields = ("content", "document__title")
    autocomplete_fields = ("document",)

    @admin.display(description="Content")
    def preview(self, obj):
        return format_html("<span>{}</span>", obj.content[:120])
