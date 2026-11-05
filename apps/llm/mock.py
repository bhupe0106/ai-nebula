"""Deterministic offline provider.

Useful for local development, CI and UI demos: streams a realistic answer with
optional latency and produces bag-of-words hashed embeddings so RAG works
without any API key.
"""
from __future__ import annotations

import asyncio
import hashlib
import math
import re
from collections.abc import AsyncIterator, Sequence

from django.conf import settings

from .base import BaseLLM, ChatMessage, ChatResult, StreamChunk
from .tokens import estimate_messages_tokens, estimate_tokens

EMBEDDING_DIMENSION = 256
_WORD_RE = re.compile(r"[a-z0-9']+")

_FOOTER = (
    "\n\n> Running on the built-in **mock** provider. Set `LLM_PROVIDER=openai` "
    "and `LLM_BASE_URL` / `LLM_API_KEY` in `.env` to talk to a real model."
)


def _last_user_message(messages: Sequence[ChatMessage]) -> str:
    for message in reversed(messages):
        if message.role == "user":
            return message.content.strip()
    return ""


def _split_for_stream(text: str) -> list[str]:
    """Split on whitespace boundaries while preserving them."""
    return re.findall(r"\S+\s*", text)


def _hash_embedding(text: str) -> list[float]:
    vector = [0.0] * EMBEDDING_DIMENSION
    words = _WORD_RE.findall(text.lower())
    if not words:
        return vector
    for word in words:
        digest = hashlib.sha256(word.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % EMBEDDING_DIMENSION
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    if norm:
        vector = [value / norm for value in vector]
    return vector


class MockLLM(BaseLLM):
    name = "mock"

    def __init__(self, *, delay: float | None = None) -> None:
        self.delay = settings.MOCK_LLM_DELAY if delay is None else delay

    def _answer(self, messages: Sequence[ChatMessage], model: str) -> str:
        question = _last_user_message(messages)
        return (
            "Here is a streamed mock answer so you can exercise the whole stack.\n\n"
            f"**You asked:** {question or '*(nothing yet)*'}\n\n"
            "This response demonstrates:\n\n"
            "1. Token-by-token WebSocket streaming with a live caret\n"
            "2. Markdown rendering after the stream completes\n"
            "3. Usage accounting and monthly quota tracking\n"
            "4. Conversation history and title generation\n\n"
            f"The active model is `{model}`. Try attaching a document from the "
            "right-hand panel and asking a question about it — retrieval runs "
            "against the same mock embeddings, so it works offline." + _FOOTER
        )

    async def stream_chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[StreamChunk]:
        resolved_model = model or settings.LLM_CHAT_MODEL
        answer = self._answer(messages, resolved_model)
        pieces = _split_for_stream(answer)
        # Respect max_tokens roughly by trimming pieces.
        if max_tokens:
            pieces = pieces[: max(1, int(max_tokens))]
        for piece in pieces:
            if self.delay:
                await asyncio.sleep(self.delay)
            yield StreamChunk(delta=piece, model=resolved_model)
        yield StreamChunk(
            prompt_tokens=estimate_messages_tokens(messages),
            completion_tokens=estimate_tokens(answer),
            finish_reason="stop",
            model=resolved_model,
        )

    async def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ChatResult:
        resolved_model = model or settings.LLM_CHAT_MODEL
        answer = self._answer(messages, resolved_model)
        return ChatResult(
            content=answer,
            prompt_tokens=estimate_messages_tokens(messages),
            completion_tokens=estimate_tokens(answer),
            model=resolved_model,
            finish_reason="stop",
        )

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [_hash_embedding(text) for text in texts]
