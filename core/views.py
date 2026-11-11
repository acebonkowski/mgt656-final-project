import logging

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.shortcuts import redirect, render

from core.forms import OnboardingForm
from core.models import Profile, Program


@login_required
def onboarding(request):
    profile = Profile.objects.filter(user=request.user).select_related("program").first()
    form = OnboardingForm(request.POST if request.method == "POST" else None, instance=profile)
    if request.method == "POST" and form.is_valid():
        profile = form.save(commit=False)
        profile.user = request.user
        profile.save()
        return redirect(getattr(settings, "ONBOARDING_SUCCESS_URL", "home"))
    return render(request, "core/onboarding.html", {
        "form": form,
        "programs": list(Program.objects.values("id", "school_id", "name")),
    })

logger = logging.getLogger(__name__)

# Centre of New Haven, CT, as [latitude, longitude].
NEW_HAVEN_CENTER = [41.3083, -72.9279]
NEW_HAVEN_ZOOM = 13


def home(request):
    return render(request, "core/home.html", {"app_env": settings.APP_ENV})


@login_required
def map_view(request):
    """Home screen: a dark map of New Haven. The provider plugs in via
    templates/core/_map_provider.html; without a key, a fallback is shown."""
    map_enabled = bool(settings.MAP_API_KEY)
    if not map_enabled:
        logger.warning("MAP_API_KEY is not set; showing the map fallback message")
    map_config = {
        "apiKey": settings.MAP_API_KEY,
        "center": NEW_HAVEN_CENTER,
        "zoom": NEW_HAVEN_ZOOM,
    }
    return render(request, "core/map.html", {
        "map_config": map_config,
        "map_enabled": map_enabled,
    })


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
