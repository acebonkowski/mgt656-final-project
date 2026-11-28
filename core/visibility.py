"""
Event visibility (#41): who may see an event. One rule, used by the map, search,
AI search, My Events, the event page, popup, .ics, image and the going/favorite
endpoints, so a hidden event is hidden everywhere.

Rules (the group comes from the creator's *current* profile, not a copy):
- everyone: any visitor, logged in or not.
- school / program: logged-in users in the creator's school / program.
- friends: the creator and the creator's friends (#98): users with an accepted
  friend request with the creator, in either direction. A pending or declined
  request does not count. The rule reads current friendships, so it follows
  them if they change.
- The creator always sees their own event. Events with no creator (imports) are
  always visible. A viewer or creator with no program never matches a group.
"""

from django.db.models import Q, Subquery

from accounts.models import Profile
from core.models import Event, FriendRequest

Visibility = Event.Visibility

# Choices offered in the create/edit forms. "Friends" since #98.
FORM_CHOICES = list(Visibility.choices)


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
        # Friends (#98): built from FriendRequest directly, not core.friends,
        # which imports this module.
        accepted = FriendRequest.objects.filter(status=FriendRequest.Status.ACCEPTED)
        allowed |= Q(visibility=Visibility.FRIENDS) & (
            Q(creator__in=accepted.filter(recipient=user).values("sender_id"))
            | Q(creator__in=accepted.filter(sender=user).values("recipient_id"))
        )
    return events.filter(allowed)


def can_view(user, event):
    """Single-event form of visible_events(), for pages and endpoints."""
    return visible_events(Event.objects.filter(pk=event.pk), user).exists()
