import logging

from django.conf import settings
from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.shortcuts import render

logger = logging.getLogger(__name__)


def home(request):
    return render(request, "core/home.html", {"app_env": settings.APP_ENV})


def healthz(request):
    """Liveness + database check, used as Render's health check path."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        logger.exception("Health check failed: database unreachable")
        return JsonResponse({"status": "error", "database": "unreachable"}, status=503)
    return JsonResponse({"status": "ok", "database": "ok"})
