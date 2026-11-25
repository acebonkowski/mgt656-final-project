"""
My Events pages (#82). Kept apart from core/views.py like search_views.py.
"""

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render
from django.views.decorators.cache import never_cache

from core.my_events import ROW_LIMIT, ROWS, add_badges, favorite_events
from core.favorite_forms import FavoriteSearchForm
from core.search import search_events


def row_events(key, user, limit=None):
    events = ROWS[key]["events"](user)
    events = list(events[:limit]) if limit else list(events)
    return add_badges(events, user) if key == "upcoming" else events


@login_required
@never_cache
def my_events(request):
    """The dashboard: Upcoming, Hosted and Favorites, a scrolling row each."""
    rows = [
        {"key": key, "title": row["title"], "empty": row["empty"],
         "events": row_events(key, request.user, ROW_LIMIT)}
        for key, row in ROWS.items()
    ]
    return render(request, "core/my_events.html", {"rows": rows})


@login_required
@never_cache
def my_events_list(request, row):
    """View All for one row, with a back arrow to the dashboard."""
    if row not in ROWS:
        raise Http404
    form = None
    events = row_events(row, request.user) if row != "favorites" else favorite_events(request.user)
    empty = ROWS[row]["empty"]
    if row == "favorites":
        has_favorites = events.exists()
        form = FavoriteSearchForm(request.GET)
        if form.is_valid():
            events = search_events(
                {**form.cleaned_data, "include_not_going": True}, queryset=events
            ).order_by("start_at", "pk")
        else:
            events = events.none()
        if has_favorites:
            empty = "No matching favorites. Try changing or clearing your filters."
    return render(request, "core/my_events_list.html", {
        "key": row,
        "title": ROWS[row]["title"],
        "empty": empty,
        "events": events,
        "filter_form": form,
    })
