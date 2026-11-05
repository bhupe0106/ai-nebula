"""Quota calculations and usage recording.

Both sync and async variants are provided because the chat flow runs inside an
ASGI consumer (async) while the HTTP fallback and DRF views are sync.
"""
from __future__ import annotations

from datetime import datetime

from asgiref.sync import sync_to_async
from django.conf import settings
from django.db.models import Sum
from django.utils import timezone

from .models import UsageEvent


def month_start(now: datetime | None = None) -> datetime:
    now = now or timezone.now()
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def next_month_start(now: datetime | None = None) -> datetime:
    start = month_start(now)
    if start.month == 12:
        return start.replace(year=start.year + 1, month=1)
    return start.replace(month=start.month + 1)


def quota_for(user) -> int:
    try:
        return int(user.profile.monthly_token_quota)
    except Exception:  # Profile missing / unsaved user
        return int(settings.DEFAULT_MONTHLY_TOKEN_QUOTA)


def tokens_used(user, since: datetime | None = None) -> int:
    aggregate = UsageEvent.objects.filter(
        user=user, created_at__gte=since or month_start()
    ).aggregate(prompt=Sum("prompt_tokens"), completion=Sum("completion_tokens"))
    return int(aggregate["prompt"] or 0) + int(aggregate["completion"] or 0)


def quota_status(user) -> dict:
    quota = quota_for(user)
    used = tokens_used(user)
    unlimited = quota <= 0
    remaining = None if unlimited else max(quota - used, 0)
    return {
        "used": used,
        "quota": quota,
        "remaining": remaining,
        "unlimited": unlimited,
        "percent": 0 if unlimited or quota == 0 else round(min(used / quota, 1) * 100, 1),
        "exceeded": (not unlimited) and used >= quota,
        "resets_on": next_month_start(),
    }


async def aquota_status(user) -> dict:
    """Async-safe wrapper (runs the small sync query in a worker thread)."""
    return await sync_to_async(quota_status, thread_sensitive=True)(user)


def serialize_quota(status: dict) -> dict:
    """Return a JSON-safe copy of a quota status mapping (used over WebSockets)."""
    payload = dict(status)
    resets_on = payload.get("resets_on")
    if hasattr(resets_on, "date"):
        payload["resets_on"] = resets_on.date().isoformat()
    return payload


async def aquota_payload(user) -> dict:
    """Quota status ready to be sent through ``send_json``."""
    return serialize_quota(await aquota_status(user))


def record_usage(
    *,
    user,
    kind: str = UsageEvent.Kind.CHAT,
    conversation=None,
    model: str = "",
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> UsageEvent:
    return UsageEvent.objects.create(
        user=user,
        kind=kind,
        conversation=conversation,
        model=model,
        prompt_tokens=max(int(prompt_tokens or 0), 0),
        completion_tokens=max(int(completion_tokens or 0), 0),
    )


async def arecord_usage(**kwargs) -> UsageEvent:
    return await UsageEvent.objects.acreate(
        user=kwargs["user"],
        kind=kwargs.get("kind", UsageEvent.Kind.CHAT),
        conversation=kwargs.get("conversation"),
        model=kwargs.get("model", ""),
        prompt_tokens=max(int(kwargs.get("prompt_tokens") or 0), 0),
        completion_tokens=max(int(kwargs.get("completion_tokens") or 0), 0),
    )
