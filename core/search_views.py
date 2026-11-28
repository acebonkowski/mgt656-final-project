"""
Event search endpoint (#35).

Kept apart from core/views.py (#31, #32) so the search work and those PRs
don't edit the same file.
"""

from zoneinfo import ZoneInfo

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from core.search import EventSearchForm

NEW_YORK = ZoneInfo("America/New_York")


def event_json(event):
    """
    One search result. The first six keys match #31's map_config.events, so
    the map can draw search results with the same marker code.
    """
    return {
        "id": event.pk,
        "name": event.name,
        "location": event.location,
        "latitude": float(event.latitude),
        "longitude": float(event.longitude),
        "price": event.price_label,
        "friends_going": getattr(event, "friends_going", 0),  # (#85)
        "category": event.category,
        "category_label": event.get_category_display(),
        "start_at": event.start_at.astimezone(NEW_YORK).isoformat(),
        "end_at": event.end_at.astimezone(NEW_YORK).isoformat(),
        "image_url": event.image_url,  # the default bulldog when there is none (#79)
        # Same key the map's own event list uses (#32).
        "url": reverse("event_detail", kwargs={"event_id": event.pk}),
        "detail_url": reverse("event_detail", kwargs={"event_id": event.pk}),
        "popup_url": reverse("event_detail_popup", kwargs={"event_id": event.pk}),
    }


@login_required
@never_cache
@require_http_methods(["GET"])
def search_events_view(request):
    """GET /events/search/?q=&category=&when=&date_from=&... -> matching events."""
    form = EventSearchForm(request.GET)
    if not form.is_valid():
        errors = {field: [str(message) for message in messages]
                  for field, messages in form.errors.items()}
        return JsonResponse({"errors": errors}, status=400)
    events = [event_json(event) for event in form.search(user=request.user)]
    return JsonResponse({"count": len(events), "events": events})
