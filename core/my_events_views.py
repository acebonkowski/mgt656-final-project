"""
My Events pages (#82). Kept apart from core/views.py like search_views.py.
"""

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render
from django.views.decorators.cache import never_cache

from core.my_events import ROW_LIMIT, ROWS, add_badges


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
    return render(request, "core/my_events_list.html", {
        "key": row,
        "title": ROWS[row]["title"],
        "empty": ROWS[row]["empty"],
        "events": row_events(row, request.user),
    })
