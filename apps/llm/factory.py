"""Select the configured provider once per process."""
from __future__ import annotations

from functools import lru_cache

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .base import BaseLLM, ChatMessage, ChatResult, LLMError, StreamChunk
from .mock import MockLLM
from .openai_compatible import OpenAICompatibleLLM

_OPENAI_ALIASES = {
    "openai",
    "openai_compatible",
    "openai-compatible",
    "azure",
    "azure_openai",
    "groq",
    "openrouter",
    "together",
    "fireworks",
    "ollama",
    "lmstudio",
    "local",
}


@lru_cache(maxsize=1)
def get_llm() -> BaseLLM:
    provider = (settings.LLM_PROVIDER or "mock").strip().lower()
    if provider == "mock":
        return MockLLM()
    if provider in _OPENAI_ALIASES:
        return OpenAICompatibleLLM()
    raise ImproperlyConfigured(
        f"Unknown LLM_PROVIDER={provider!r}. Use 'mock' or an OpenAI-compatible provider."
    )


def reset_llm_cache() -> None:
    """Clear the cached provider (used by tests and settings changes)."""
    get_llm.cache_clear()


__all__ = [
    "BaseLLM",
    "ChatMessage",
    "ChatResult",
    "LLMError",
    "StreamChunk",
    "get_llm",
    "reset_llm_cache",
]
