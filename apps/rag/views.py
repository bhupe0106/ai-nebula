import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from apps.chat.models import Conversation

from .forms import validate_upload
from .models import Document
from .services import queue_ingestion

logger = logging.getLogger(__name__)


def _is_htmx(request) -> bool:
    return request.headers.get("HX-Request") == "true"


@login_required
def library(request):
    documents = Document.objects.filter(user=request.user).select_related("conversation")
    return render(
        request,
        "rag/library.html",
        {
            "documents": documents,
            "global_count": documents.filter(conversation__isnull=True).count(),
            "chat_count": documents.filter(conversation__isnull=False).count(),
        },
    )


@login_required
@require_POST
def upload(request):
    conversation = None
    conversation_id = request.POST.get("conversation_id", "").strip()
    if conversation_id:
        conversation = get_object_or_404(
            Conversation, pk=conversation_id, user=request.user
        )

    upload_file = request.FILES.get("file")
    error = ""
    if upload_file is None:
        error = "Choose a PDF, DOCX, Markdown, or text file first."
    else:
        try:
            validate_upload(upload_file)
        except ValidationError as exc:
            error = exc.messages[0]

    if error:
        if _is_htmx(request):
            return render(
                request,
                "rag/_upload_error.html",
                {"error": error, "conversation": conversation},
                status=400,
            )
        messages.error(request, error)
        return redirect("rag:library")

    document = Document.objects.create(
        user=request.user,
        conversation=conversation,
        title=(request.POST.get("title") or "").strip(),
        file=upload_file,
        size_bytes=upload_file.size,
    )

    document = queue_ingestion(document)

    if _is_htmx(request):
        return render(
            request,
            "rag/_document_row.html",
            {"document": document, "conversation": conversation},
        )
    messages.success(request, f"{document.display_title} is ready.")
    if conversation:
        return redirect(conversation.get_absolute_url())
    return redirect("rag:library")


@login_required
@require_GET
def status(request, document_id):
    document = get_object_or_404(Document, pk=document_id, user=request.user)
    return render(
        request,
        "rag/_document_row.html",
        {"document": document, "conversation": document.conversation},
    )


@login_required
@require_POST
def delete(request, document_id):
    document = get_object_or_404(Document, pk=document_id, user=request.user)
    conversation = document.conversation
    document.delete()
    if _is_htmx(request):
        return HttpResponse("")
    messages.success(request, "Document deleted.")
    if conversation:
        return redirect(conversation.get_absolute_url())
    return redirect("rag:library")
