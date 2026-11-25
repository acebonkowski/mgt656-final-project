"""Favorites state and writes, independent of attendance."""
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from core.models import Event, EventFavorite


def favorite_context(request, event):
    saved = request.user.is_authenticated and EventFavorite.objects.filter(
        user=request.user, event=event
    ).exists()
    return {
        "is_favorited": saved,
        "favorite_ended": event.end_at <= timezone.now(),
        "favorite_login_url": reverse("accounts:welcome") + "?" + urlencode({
            "next": reverse("event_detail", args=[event.pk]),
        }),
    }


@login_required
@never_cache
@require_POST
def set_favorite(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
    value = request.POST.get("favorited")
    if value not in ("true", "false"):
        return JsonResponse({"error": "Choose true or false for favorited."}, status=400)
    saved = value == "true"
    if saved:
        if event.end_at <= timezone.now():
            return JsonResponse({"error": "This event has ended."}, status=400)
        EventFavorite.objects.get_or_create(user=request.user, event=event)
    else:
        EventFavorite.objects.filter(user=request.user, event=event).delete()
    return JsonResponse({"favorited": saved})
