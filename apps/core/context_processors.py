"""Template context shared by the whole UI."""


def chat_sidebar(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}

    # Imported lazily so the processor does not create import cycles at startup.
    from apps.chat.models import Conversation
    from apps.usage.services import quota_status

    conversations = list(
        Conversation.objects.filter(user=user, is_archived=False)
        .order_by("-updated_at")
        .only("id", "title", "updated_at")[:20]
    )
    return {
        "sidebar_conversations": conversations,
        "quota": quota_status(user),
    }
