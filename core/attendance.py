"""
Going status (#84): queries shared by search, the map and My Events (#82).
"""

from django.db.models import Q
from django.utils import timezone

from core.models import Event, EventAttendance


def exclude_not_going(events, user):
    """Hide the events `user` marked "Not going" (search, map pins, AI results)."""
    if user is None or not user.is_authenticated:
        return events
    return events.exclude(
        attendances__user=user, attendances__status=EventAttendance.Status.NOT_GOING
    )


def upcoming_events(user, now=None):
    """
    My Events > Upcoming (#82): events the user hosts, or answered Going or
    Maybe, that have not ended. Events with no answer or "Not going" are left out.
    """
    now = now or timezone.now()
    answered = Q(
        attendances__user=user,
        attendances__status__in=[EventAttendance.Status.GOING, EventAttendance.Status.MAYBE],
    )
    return (
        Event.objects.filter(end_at__gt=now)
        .filter(Q(creator=user) | answered)
        .distinct()
        .order_by("start_at", "pk")
    )


def can_answer(user, event, now=None):
    """The dropdown shows only to a logged-in non-host, until the event ends."""
    now = now or timezone.now()
    return (
        user.is_authenticated
        and event.creator_id != user.pk
        and event.end_at > now
    )
