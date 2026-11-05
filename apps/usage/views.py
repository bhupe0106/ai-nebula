from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.db.models.functions import TruncDate
from django.shortcuts import render
from django.utils import timezone

from .models import UsageEvent
from .services import quota_status


@login_required
def dashboard(request):
    since = timezone.now() - timedelta(days=29)
    rows = (
        UsageEvent.objects.filter(user=request.user, created_at__gte=since)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(
            prompt=Sum("prompt_tokens"),
            completion=Sum("completion_tokens"),
        )
        .order_by("day")
    )
    by_day = {
        row["day"]: (row["prompt"] or 0) + (row["completion"] or 0) for row in rows
    }
    today = timezone.localdate()
    chart = []
    for offset in range(29, -1, -1):
        day = today - timedelta(days=offset)
        chart.append({"day": day, "tokens": by_day.get(day, 0)})
    peak = max((point["tokens"] for point in chart), default=0) or 1

    recent = UsageEvent.objects.filter(user=request.user).select_related("conversation")[:25]

    return render(
        request,
        "usage/dashboard.html",
        {
            "quota": quota_status(request.user),
            "chart": chart,
            "peak": peak,
            "recent": recent,
        },
    )
