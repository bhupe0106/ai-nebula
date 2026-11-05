"""Provider-agnostic chat/embedding contracts."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass


class LLMError(RuntimeError):
    """Raised for provider, transport, or malformed-response failures."""


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str


@dataclass
class StreamChunk:
    delta: str = ""
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    finish_reason: str = ""
    model: str = ""


@dataclass
class ChatResult:
    content: str
    prompt_tokens: int
    completion_tokens: int
    model: str
    finish_reason: str = "stop"


class BaseLLM(ABC):
    """Every provider implements streaming, completion, and embeddings."""

    name: str = "base"
    supports_embeddings: bool = True

    @abstractmethod
    def stream_chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Yield incremental deltas, optionally ending with usage metadata."""

    @abstractmethod
    async def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ChatResult:
        """Return a single complete answer."""

    @abstractmethod
    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Return one vector per input text."""
