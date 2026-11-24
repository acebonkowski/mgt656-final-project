"""
My Events (#82): what each row of the dashboard lists.

Upcoming comes from #84's going status. Favorites is filled in by #38: until
then favorite_events() returns nothing, and #38 only replaces its body.
"""

from django.utils import timezone

from core.attendance import upcoming_events
from core.models import Event, EventAttendance

ROW_LIMIT = 10  # events shown in a dashboard row; View All lists the rest


def hosted_events(user, now=None):
    """Events I created: upcoming first (earliest first), then past (latest first)."""
    now = now or timezone.now()
    mine = Event.objects.filter(creator=user)
    upcoming = mine.filter(end_at__gt=now).order_by("start_at", "pk")
    past = mine.filter(end_at__lte=now).order_by("-start_at", "-pk")
    return [*upcoming, *past]


def favorite_events(user, now=None):
    """Events I marked as favorites (#38 fills this in)."""
    return Event.objects.none()


ROWS = {
    "upcoming": {
        "title": "Upcoming Events",
        "empty": "Nothing coming up yet",
        "events": upcoming_events,
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
