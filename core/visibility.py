"""
Event visibility (#41): who may see an event. One rule, used by the map, search,
AI search, My Events, the event page, popup, .ics, image and the going/favorite
endpoints, so a hidden event is hidden everywhere.

Rules (the group comes from the creator's *current* profile, not a copy):
- everyone: any visitor, logged in or not.
- school / program: logged-in users in the creator's school / program.
- friends: the creator only for now. There is no friends model yet (#39), so
  this fails closed until it exists.
- The creator always sees their own event. Events with no creator (imports) are
  always visible. A viewer or creator with no program never matches a group.
"""

from django.db.models import Q, Subquery

from accounts.models import Profile
from core.models import Event

Visibility = Event.Visibility

# Choices offered in the create/edit forms. "Friends" waits for #39.
FORM_CHOICES = [
    (value, label) for value, label in Visibility.choices if value != Visibility.FRIENDS
]


def visible_events(events, user):
    """Limit a queryset to the events `user` (possibly anonymous) may see."""
    allowed = Q(visibility=Visibility.EVERYONE) | Q(creator__isnull=True)
    if user is not None and user.is_authenticated:
        allowed |= Q(creator=user)
        # The viewer's own program/school as subqueries: no extra query, and a
        # viewer without a program gets NULL, which matches nothing (fail closed).
        mine = Profile.objects.filter(user=user)
        allowed |= Q(
            visibility=Visibility.PROGRAM,
            creator__profile__program=Subquery(mine.values("program_id")[:1]),
        )
        allowed |= Q(
            visibility=Visibility.SCHOOL,
            creator__profile__program__school=Subquery(mine.values("program__school_id")[:1]),
        )
    return events.filter(allowed)


def can_view(user, event):
    """Single-event form of visible_events(), for pages and endpoints."""
    return visible_events(Event.objects.filter(pk=event.pk), user).exists()
