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
