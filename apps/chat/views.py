import json
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from apps.rag.models import Document

from .forms import ConversationSettingsForm, MessageForm
from .models import Conversation
from .services import QuotaExceeded, generate_reply, serialize_message

logger = logging.getLogger(__name__)

SUGGESTIONS = [
    {
        "title": "Summarize a document",
        "prompt": "Attach a document, then ask me to summarize the key points.",
        "icon": "doc",
    },
    {
        "title": "Brainstorm ideas",
        "prompt": "Brainstorm five names for a developer productivity tool.",
        "icon": "spark",
    },
    {
        "title": "Explain a concept",
        "prompt": "Explain vector databases to a backend developer in simple terms.",
        "icon": "bolt",
    },
    {
        "title": "Draft an email",
        "prompt": "Draft a friendly follow-up email after a product demo.",
        "icon": "send",
    },
]


def _get_conversation(user, conversation_id) -> Conversation:
    return get_object_or_404(
        Conversation.objects.select_related("user"), pk=conversation_id, user=user
    )


@login_required
def conversation_list(request):
    conversations = (
        Conversation.objects.filter(user=request.user)
        .active()
        .order_by("-updated_at")
    )
    archived_count = Conversation.objects.filter(
        user=request.user, is_archived=True
    ).count()
    return render(
        request,
        "chat/list.html",
        {
            "conversations": conversations,
            "archived_count": archived_count,
            "active_nav": "chat",
        },
    )


@login_required
@require_POST
def conversation_create(request):
    conversation = Conversation.objects.create(
        user=request.user,
        title="New chat",
        model=(request.POST.get("model") or "").strip(),
    )
    return redirect(conversation.get_absolute_url())


@login_required
def conversation_detail(request, conversation_id):
    conversation = _get_conversation(request.user, conversation_id)
    documents = (
        Document.objects.filter(user=request.user)
        .filter(Q(conversation=conversation) | Q(conversation__isnull=True))
        .select_related("conversation")
        .order_by("-created_at")
    )
    return render(
        request,
        "chat/detail.html",
        {
            "conversation": conversation,
            "chat_messages": conversation.messages.all(),
            "documents": documents,
            "message_form": MessageForm(),
            "settings_form": ConversationSettingsForm(instance=conversation),
            "suggestions": SUGGESTIONS,
            "active_nav": "chat",
        },
    )


@login_required
@require_GET
def conversation_messages(request, conversation_id):
    conversation = _get_conversation(request.user, conversation_id)
    return render(
        request,
        "chat/_messages.html",
        {"conversation": conversation, "chat_messages": conversation.messages.all()},
    )


@login_required
@require_POST
def conversation_send(request, conversation_id):
    """No-JavaScript / HTTP fallback for sending a message."""
    conversation = _get_conversation(request.user, conversation_id)
    form = MessageForm(request.POST)
    if not form.is_valid():
        messages.error(request, form.errors.get("content", ["Write a message first."])[0])
        return redirect(conversation.get_absolute_url())

    try:
        generate_reply(conversation, form.cleaned_data["content"])
    except QuotaExceeded as exc:
        messages.error(request, str(exc))
    except Exception:
        logger.exception("Fallback chat send failed")
        messages.error(request, "The reply failed. Please try again.")
    return redirect(f"{conversation.get_absolute_url()}#composer")


@login_required
@require_POST
def conversation_settings(request, conversation_id):
    conversation = _get_conversation(request.user, conversation_id)
    form = ConversationSettingsForm(request.POST, instance=conversation)
    if form.is_valid():
        form.save()
        messages.success(request, "Conversation settings saved.")
    else:
        first_error = next(iter(form.errors.values()))[0]
        messages.error(request, f"Settings not saved: {first_error}")
    return redirect(conversation.get_absolute_url())


@login_required
@require_POST
def conversation_archive(request, conversation_id):
    conversation = _get_conversation(request.user, conversation_id)
    conversation.is_archived = not conversation.is_archived
    conversation.save(update_fields=["is_archived", "updated_at"])
    if conversation.is_archived:
        messages.success(request, "Conversation archived.")
        return redirect("chat:list")
    messages.success(request, "Conversation restored.")
    return redirect(conversation.get_absolute_url())


@login_required
@require_POST
def conversation_clear(request, conversation_id):
    conversation = _get_conversation(request.user, conversation_id)
    deleted, _ = conversation.messages.all().delete()
    messages.success(request, f"Cleared {deleted} message(s).")
    return redirect(conversation.get_absolute_url())


@login_required
@require_POST
def conversation_delete(request, conversation_id):
    conversation = _get_conversation(request.user, conversation_id)
    conversation.delete()
    messages.success(request, "Conversation deleted.")
    return redirect("chat:list")


@login_required
@require_GET
def conversation_export(request, conversation_id):
    conversation = _get_conversation(request.user, conversation_id)
    payload = {
        "id": str(conversation.id),
        "title": conversation.title,
        "model": conversation.resolved_model,
        "temperature": conversation.temperature,
        "system_prompt": conversation.system_prompt,
        "created_at": conversation.created_at.isoformat(),
        "updated_at": conversation.updated_at.isoformat(),
        "messages": [serialize_message(message) for message in conversation.messages.all()],
    }
    response = HttpResponse(
        json.dumps(payload, indent=2, ensure_ascii=False),
        content_type="application/json",
    )
    safe_title = "".join(
        character for character in conversation.title if character.isalnum() or character in " -_"
    ).strip() or "conversation"
    response["Content-Disposition"] = f'attachment; filename="{safe_title[:60]}.json"'
    return response


@login_required
@require_GET
def conversation_search(request):
    query = (request.GET.get("q") or "").strip()
    conversations = Conversation.objects.filter(user=request.user).active()
    if query:
        conversations = conversations.filter(
            Q(title__icontains=query) | Q(messages__content__icontains=query)
        ).distinct()
    conversations = conversations.order_by("-updated_at")[:20]
    return render(
        request,
        "chat/_conversation_items.html",
        {
            "sidebar_conversations": conversations,
            "active_id": request.GET.get("active", ""),
        },
    )
