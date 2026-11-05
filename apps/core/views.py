from django.db import connections
from django.db.utils import OperationalError
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET


def home(request):
    if request.user.is_authenticated:
        return redirect("chat:list")
    return render(request, "core/home.html")


@never_cache
@require_GET
def health(request):
    """Liveness/readiness probe used by Docker and load balancers."""
    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except OperationalError:
        return JsonResponse({"status": "error", "database": "unavailable"}, status=503)
    return JsonResponse({"status": "ok", "database": "ok"})
