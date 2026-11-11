import logging

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import DatabaseError, connection
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import redirect, render

from core.forms import OnboardingForm
from accounts.models import Profile
from core.models import Program
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def onboarding(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    form = OnboardingForm(request.POST if request.method == "POST" else None, instance=profile)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            # Update only onboarding fields so a concurrent photo upload is preserved.
            profile = Profile.objects.select_for_update().get(pk=profile.pk)
            profile.display_name = form.cleaned_data["display_name"]
            profile.program = form.cleaned_data["program"]
            profile.onboarding_complete = True
            profile.save(update_fields=["display_name", "program", "onboarding_complete", "updated_at"])
        return redirect(getattr(settings, "ONBOARDING_SUCCESS_URL", "home"))
    return render(request, "core/onboarding.html", {
        "form": form,
        "profile": profile,
        "programs": list(Program.objects.filter(school__is_active=True).values("id", "school_id", "name")),
    })

logger = logging.getLogger(__name__)

# Centre of New Haven, CT, as [latitude, longitude].
NEW_HAVEN_CENTER = [41.3083, -72.9279]
NEW_HAVEN_ZOOM = 13


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
