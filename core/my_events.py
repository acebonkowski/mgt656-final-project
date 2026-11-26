"""
My Events (#82): what each row of the dashboard lists.

Upcoming comes from #84's going status. Favorites is independent of attendance.
"""

from django.utils import timezone

from core.attendance import exclude_not_going, upcoming_events
from core.models import Event, EventAttendance
from core.visibility import visible_events

ROW_LIMIT = 10  # events shown in a dashboard row; View All lists the rest


def hosted_events(user, now=None):
    """Events I created: upcoming first (earliest first), then past (latest first)."""
    now = now or timezone.now()
    mine = Event.objects.filter(creator=user)
    upcoming = mine.filter(end_at__gt=now).order_by("start_at", "pk")
    past = mine.filter(end_at__lte=now).order_by("-start_at", "-pk")
    return [*upcoming, *past]


def favorite_events(user, now=None):
    """Saved events that have not ended, including events marked Not going."""
    return visible_events(Event.objects.filter(
        favorites__user=user, end_at__gt=now or timezone.now()
    ), user).order_by("start_at", "pk")


def suggested_events(user, now=None):
    """
    Events recurring searches (#37) found for me and I haven't hidden. Checked
    again now, because things change after the daily scan: ended events and
    events I've since marked Not going drop out. (When #41's visibility lands,
    filter with visible_events() here too.)
    """
    events = Event.objects.filter(
        search_suggestions__user=user,
        search_suggestions__hidden=False,
        end_at__gt=now or timezone.now(),
    )
    return exclude_not_going(events, user).order_by("start_at", "pk")


ROWS = {
    "upcoming": {
        "title": "Upcoming Events",
        "empty": "Nothing coming up yet",
        "events": upcoming_events,
    },
    "suggested": {
        "title": "Suggested",
        "empty": "No suggestions yet. Ask AI to keep looking for events you like.",
        "events": suggested_events,
    },
    "hosted": {
        "title": "Hosted Events",
        "empty": "You haven't hosted any events",
        "events": hosted_events,
    },
    "favorites": {
        "title": "Favorites",
        "empty": "No favorites yet",
        "events": favorite_events,
    },
}


def add_badges(events, user):
    """Mark each event Hosting, Going or Maybe on the user's Upcoming cards."""
    events = list(events)
    answers = dict(
        EventAttendance.objects.filter(user=user, event__in=events)
        .values_list("event_id", "status")
    )
    labels = {EventAttendance.Status.GOING: "Going", EventAttendance.Status.MAYBE: "Maybe"}
    for event in events:
        if event.creator_id == user.pk:
            event.badge = "Hosting"
        else:
            event.badge = labels.get(answers.get(event.pk), "")
    return events
