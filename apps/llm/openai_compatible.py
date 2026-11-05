"""OpenAI-compatible HTTP client.

Streams server-sent events from /chat/completions and calls /embeddings. Because
the wire format is the de-facto standard, this one adapter covers OpenAI, Azure
OpenAI, Groq, OpenRouter, Together, Fireworks, Ollama and LM Studio.
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence

import httpx
from django.conf import settings

from .base import BaseLLM, ChatMessage, ChatResult, LLMError, StreamChunk
from .tokens import estimate_messages_tokens, estimate_tokens


class OpenAICompatibleLLM(BaseLLM):
    name = "openai"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self.base_url = (base_url or settings.LLM_BASE_URL).rstrip("/")
        self.api_key = api_key if api_key is not None else settings.LLM_API_KEY
        self.timeout = timeout or settings.LLM_TIMEOUT

    # ------------------------------------------------------------------ utils
    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            **{str(k): str(v) for k, v in (settings.LLM_EXTRA_HEADERS or {}).items()},
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _client(self, base_url: str | None = None) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=(base_url or self.base_url).rstrip("/"),
            headers=self._headers(),
            params=settings.LLM_EXTRA_QUERY or None,
            timeout=httpx.Timeout(self.timeout, connect=10.0),
        )

    @staticmethod
    def _payload(
        messages: Sequence[ChatMessage],
        *,
        model: str | None,
        temperature: float | None,
        max_tokens: int | None,
        stream: bool,
    ) -> dict:
        payload = {
            "model": model or settings.LLM_CHAT_MODEL,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": settings.LLM_TEMPERATURE if temperature is None else temperature,
            "max_tokens": max_tokens or settings.LLM_MAX_TOKENS,
            "stream": stream,
        }
        if stream:
            # Not every provider supports this flag; unknown keys are ignored by
            # most and usage simply stays empty when it is unsupported.
            payload["stream_options"] = {"include_usage": True}
        return payload

    @staticmethod
    def _error_from_response(response: httpx.Response, body: str) -> LLMError:
        detail = body[:800].strip()
        try:
            parsed = json.loads(body)
            detail = (
                parsed.get("error", {}).get("message")
                if isinstance(parsed.get("error"), dict)
                else parsed.get("error") or parsed.get("detail") or detail
            )
        except (ValueError, AttributeError):
            pass
        return LLMError(f"Provider returned HTTP {response.status_code}: {detail}")

    # ------------------------------------------------------------------- chat
    async def stream_chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[StreamChunk]:
        payload = self._payload(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        try:
            async with (
                self._client() as client,
                client.stream("POST", "/chat/completions", json=payload) as response,
            ):
                if response.status_code >= 400:
                    body = (await response.aread()).decode("utf-8", "replace")
                    raise self._error_from_response(response, body)

                async for raw_line in response.aiter_lines():
                    line = raw_line.strip()
                    if not line or line.startswith(":"):
                        continue
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        event = json.loads(data)
                    except json.JSONDecodeError:
                        continue

                    usage = event.get("usage") or {}
                    choices = event.get("choices") or []
                    delta = ""
                    finish_reason = ""
                    if choices:
                        choice = choices[0] or {}
                        piece = (choice.get("delta") or {}).get("content")
                        if isinstance(piece, str):
                            delta = piece
                        finish_reason = choice.get("finish_reason") or ""
                    yield StreamChunk(
                        delta=delta,
                        prompt_tokens=usage.get("prompt_tokens"),
                        completion_tokens=usage.get("completion_tokens"),
                        finish_reason=finish_reason,
                        model=event.get("model", "") or payload["model"],
                    )
        except httpx.TimeoutException as exc:
            raise LLMError("The model provider timed out. Try again.") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"Could not reach the model provider: {exc}") from exc

    async def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ChatResult:
        payload = self._payload(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
        )
        try:
            async with self._client() as client:
                response = await client.post("/chat/completions", json=payload)
                body = response.text
                if response.status_code >= 400:
                    raise self._error_from_response(response, body)
                data = response.json()
        except httpx.TimeoutException as exc:
            raise LLMError("The model provider timed out. Try again.") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"Could not reach the model provider: {exc}") from exc
        except ValueError as exc:
            raise LLMError("The model provider returned an invalid response.") from exc

        choices = data.get("choices") or []
        content = ""
        finish_reason = ""
        if choices:
            content = ((choices[0].get("message") or {}).get("content")) or ""
            finish_reason = choices[0].get("finish_reason") or ""
        usage = data.get("usage") or {}
        return ChatResult(
            content=content.strip(),
            prompt_tokens=int(usage.get("prompt_tokens") or estimate_messages_tokens(messages)),
            completion_tokens=int(usage.get("completion_tokens") or estimate_tokens(content)),
            model=data.get("model") or payload["model"],
            finish_reason=finish_reason,
        )

    # -------------------------------------------------------------- embeddings
    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        clean = [text or "" for text in texts]
        if not clean:
            return []
        payload = {"model": settings.LLM_EMBEDDING_MODEL, "input": clean}
        try:
            async with self._client(settings.LLM_EMBEDDING_BASE_URL or None) as client:
                response = await client.post("/embeddings", json=payload)
                body = response.text
                if response.status_code >= 400:
                    raise self._error_from_response(response, body)
                data = response.json()
        except httpx.TimeoutException as exc:
            raise LLMError("The embedding provider timed out.") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"Could not reach the embedding provider: {exc}") from exc
        except ValueError as exc:
            raise LLMError("The embedding provider returned an invalid response.") from exc

        rows = data.get("data") or []
        if len(rows) != len(clean):
            raise LLMError("The embedding provider returned an unexpected number of vectors.")
        ordered = sorted(rows, key=lambda row: row.get("index", 0))
        return [list(row.get("embedding") or []) for row in ordered]
