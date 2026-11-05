"""Chat orchestration shared by the WebSocket consumer, HTML fallback and API."""
from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field

from asgiref.sync import async_to_sync
from django.conf import settings
from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.utils import timezone

from apps.llm import ChatMessage, LLMError, get_llm
from apps.llm.tokens import estimate_messages_tokens, estimate_tokens
from apps.rag.services import aretrieve, format_context
from apps.usage.models import UsageEvent
from apps.usage.services import aquota_status, arecord_usage

from .models import Conversation, Message

logger = logging.getLogger(__name__)

MAX_MESSAGE_CHARS = 8000

DEFAULT_SYSTEM_PROMPT = (
    "You are a knowledgeable, friendly assistant inside a chat application. "
    "Answer clearly and use Markdown when it improves readability. "
    "If document excerpts are provided, ground your answer in them and cite "
    "the source numbers inline, for example [1]. "
    "If you do not know something, say so instead of inventing details."
)


class QuotaExceeded(RuntimeError):
    """The account has exhausted its monthly token allowance."""


@dataclass
class PreparedTurn:
    conversation: Conversation
    user: Message
    prompt: list[ChatMessage]
    citations: list[dict] = field(default_factory=list)
    model: str = ""
    temperature: float = 0.7
    user_obj: object | None = None
    started_at: float = field(default_factory=time.perf_counter)


@dataclass
class ReplyEvent:
    delta: str = ""
    done: bool = False
    message: Message | None = None
    error: str = ""
    stopped: bool = False


def derive_title(content: str) -> str:
    line = " ".join((content or "").strip().split())
    if not line:
        return "New chat"
    if len(line) <= 60:
        return line
    return line[:57].rstrip() + "…"


async def prepare_turn(conversation: Conversation, content: str) -> PreparedTurn:
    content = (content or "").strip()
    if not content:
        raise ValueError("Message cannot be empty.")
    if len(content) > MAX_MESSAGE_CHARS:
        raise ValueError(f"Messages are limited to {MAX_MESSAGE_CHARS} characters.")

    user_model = get_user_model()
    user = await user_model.objects.select_related("profile").aget(pk=conversation.user_id)

    status = await aquota_status(user)
    if status["exceeded"]:
        raise QuotaExceeded(
            "You have reached this month's token allowance. "
            "Top up from your profile or wait for the monthly reset."
        )

    user_message = await Message.objects.acreate(
        conversation=conversation,
        role=Message.Role.USER,
        content=content,
    )

    updates: dict = {"updated_at": timezone.now()}
    if conversation.title in ("", "New chat"):
        updates["title"] = derive_title(content)
    await Conversation.objects.filter(pk=conversation.pk).aupdate(**updates)
    for key, value in updates.items():
        setattr(conversation, key, value)

    prompt, citations = await build_prompt(
        conversation, content, exclude_message_id=user_message.pk, user=user
    )
    return PreparedTurn(
        conversation=conversation,
        user=user_message,
        prompt=prompt,
        citations=citations,
        model=conversation.resolved_model,
        temperature=conversation.temperature,
        user_obj=user,
    )


async def build_prompt(
    conversation: Conversation,
    query: str,
    *,
    exclude_message_id=None,
    user=None,
) -> tuple[list[ChatMessage], list[dict]]:
    system = (conversation.system_prompt or "").strip() or DEFAULT_SYSTEM_PROMPT
    citations: list[dict] = []

    if conversation.use_documents:
        try:
            results = await aretrieve(
                query, user=user, conversation=conversation, limit=settings.RAG_TOP_K
            )
        except LLMError as exc:
            logger.warning("Retrieval skipped: %s", exc)
            results = []
        except Exception:
            logger.exception("Retrieval failed; continuing without documents")
            results = []

        if results:
            system += (
                "\n\nAnswer using the document excerpts below when relevant. "
                "Cite them as [n] using the numbers shown.\n\n"
                + format_context(results)
            )
            seen: set[str] = set()
            for result in results:
                key = str(result.document_id)
                if key in seen:
                    continue
                seen.add(key)
                citations.append(
                    {
                        "document_id": key,
                        "title": result.title,
                        "score": round(float(result.score), 3),
                    }
                )

    messages: list[ChatMessage] = [ChatMessage("system", system)]

    history_qs = conversation.messages.exclude(
        role=Message.Role.SYSTEM
    ).filter(error="")
    if exclude_message_id:
        history_qs = history_qs.exclude(pk=exclude_message_id)
    history_qs = history_qs.order_by("-created_at")[: settings.CHAT_HISTORY_LIMIT]
    history = [message async for message in history_qs]

    for message in reversed(history):
        if message.content:
            messages.append(ChatMessage(message.role, message.content))

    messages.append(ChatMessage("user", query))
    return messages, citations


async def run_turn(
    turn: PreparedTurn, *, should_stop: Callable[[], bool] | None = None
) -> AsyncIterator[ReplyEvent]:
    """Stream a reply, persist it, and record usage exactly once."""
    client = get_llm()
    parts: list[str] = []
    prompt_tokens = 0
    completion_tokens = 0
    finish_reason = ""
    error = ""
    stopped = False
    started = time.perf_counter()

    try:
        async for chunk in client.stream_chat(
            turn.prompt,
            model=turn.model,
            temperature=turn.temperature,
            max_tokens=settings.LLM_MAX_TOKENS,
        ):
            if should_stop is not None and should_stop():
                stopped = True
                break
            if chunk.delta:
                parts.append(chunk.delta)
                yield ReplyEvent(delta=chunk.delta)
            if chunk.prompt_tokens:
                prompt_tokens = int(chunk.prompt_tokens)
            if chunk.completion_tokens:
                completion_tokens = int(chunk.completion_tokens)
            if chunk.finish_reason:
                finish_reason = chunk.finish_reason
    except LLMError as exc:
        error = str(exc)
        logger.warning("LLM error in conversation %s: %s", turn.conversation_id, exc)
    except Exception:  # pragma: no cover - last-resort guard
        logger.exception("Unexpected LLM failure in conversation %s", turn.conversation_id)
        error = "The assistant hit an unexpected error. Please try again."

    if should_stop is not None and should_stop():
        stopped = True

    content = "".join(parts).strip()
    if not prompt_tokens:
        prompt_tokens = estimate_messages_tokens(turn.prompt)
    if not completion_tokens:
        completion_tokens = estimate_tokens(content)
    latency_ms = int((time.perf_counter() - started) * 1000)

    message = await Message.objects.acreate(
        conversation=turn.conversation,
        role=Message.Role.ASSISTANT,
        content=content,
        model=turn.model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        latency_ms=latency_ms,
        error=error,
        metadata={
            "citations": turn.citations,
            "finish_reason": finish_reason,
            "stopped": stopped,
        },
    )
    await arecord_usage(
        user=turn.user_obj or turn.conversation.user,
        kind=UsageEvent.Kind.CHAT,
        conversation=turn.conversation,
        model=turn.model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )
    await Conversation.objects.filter(pk=turn.conversation.pk).aupdate(
        updated_at=timezone.now()
    )

    yield ReplyEvent(done=True, message=message, error=error, stopped=stopped)


async def collect_turn(turn: PreparedTurn) -> Message:
    message: Message | None = None
    async for event in run_turn(turn):
        if event.done and event.message is not None:
            message = event.message
    if message is None:  # pragma: no cover - run_turn always emits done
        raise RuntimeError("The assistant produced no message.")
    return message


async def generate_reply_async(conversation: Conversation, content: str) -> Message:
    turn = await prepare_turn(conversation, content)
    return await collect_turn(turn)


def generate_reply(conversation: Conversation, content: str) -> Message:
    """Sync entrypoint for DRF and the no-JS fallback view."""
    return async_to_sync(generate_reply_async)(conversation, content)


def serialize_message(message: Message) -> dict:
    return {
        "id": str(message.id),
        "role": message.role,
        "content": message.content,
        "model": message.model,
        "prompt_tokens": message.prompt_tokens,
        "completion_tokens": message.completion_tokens,
        "total_tokens": message.total_tokens,
        "created_at": message.created_at.isoformat(),
        "error": message.error,
        "citations": message.citations,
        "stopped": bool((message.metadata or {}).get("stopped")),
    }


def render_message(message: Message, user) -> str:
    return render_to_string(
        "chat/_message.html", {"message": message, "user": user}
    )


async def arender_message(message: Message, user) -> str:
    from asgiref.sync import sync_to_async

    return await sync_to_async(render_message, thread_sensitive=True)(message, user)
