"""Rough token estimation used when a provider omits usage data."""
from __future__ import annotations


def estimate_tokens(text: str) -> int:
    """~4 characters per token, never below 1 for non-empty text."""
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)


def estimate_messages_tokens(messages) -> int:
    total = 0
    for message in messages:
        total += estimate_tokens(getattr(message, "content", "") or "")
        total += 4  # role / formatting overhead
    return total
