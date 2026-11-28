"""
Friends (#96): queries and actions shared by the Friends page, the header badge
(#81), profiles (#97), friends-only events (#98), friends going (#85) and
invitations (#86).

Two users are friends when a request between them, in either direction, was
accepted. A request the other way round accepts the pending one, so two users
never both have an open request to each other.
"""

import enum

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils import timezone

from accounts import usernames
from core import resend
from core.models import Event, EventAttendance, FriendRequest
from core.visibility import visible_events

Status = FriendRequest.Status


class Relationship(enum.Enum):
    NONE = "none"
    SENT = "sent"          # the viewer asked; pending, or declined without telling them
    RECEIVED = "received"  # the other user asked and the viewer has not answered
    FRIENDS = "friends"


class SendResult(enum.Enum):
    SENT = "sent"
    BECAME_FRIENDS = "became_friends"
    ALREADY_SENT = "already_sent"
    ALREADY_FRIENDS = "already_friends"
    NOT_ALLOWED = "not_allowed"


def _between(a, b):
    return Q(sender=a, recipient=b) | Q(sender=b, recipient=a)


def friend_ids(user):
    """A Q on User matching `user`'s friends, built from two subqueries."""
    accepted = FriendRequest.objects.filter(status=Status.ACCEPTED)
    return (
        Q(pk__in=accepted.filter(sender=user).values("recipient_id"))
        | Q(pk__in=accepted.filter(recipient=user).values("sender_id"))
    )


def friends_of(user):
    return get_user_model().objects.filter(friend_ids(user))


def friends_list(user):
    """The Friends page list (#97): friends sorted by name, profiles selected."""
    return (
        friends_of(user)
        .select_related("profile__program")
        .order_by(Lower("profile__display_name"), "profile__username")
    )


def attendance_visible_to(viewer, attendee):
    """
    Whether `viewer` may see which events `attendee` is going to (#41, #83).

    Settings (#83) will store each user's choice (friends, program, school or
    everyone) and check it here. Until then the default, "everyone", applies.
    Every place that shows another user's going status calls this function, or
    attendance_visible_q() for many users at once.
    """
    return True


def attendance_visible_q(viewer):
    """Queryset form of attendance_visible_to(): a Q on User. Matches all until #83."""
    return Q()


def are_friends(a, b):
    if a is None or b is None or a.pk == b.pk:
        return False
    return FriendRequest.objects.filter(_between(a, b), status=Status.ACCEPTED).exists()


def incoming_request_count(user):
    """Pending requests sent to `user`: the red counters (#81, #96)."""
    return FriendRequest.objects.filter(recipient=user, status=Status.PENDING).count()


def findable_users():
    """Users who finished onboarding and have a username."""
    return (
        get_user_model().objects
        .filter(profile__onboarding_complete=True, is_active=True)
        .exclude(profile__username="")
        .select_related("profile__program")
    )


def find_user(query, viewer):
    """
    The one user whose username or email is exactly `query`, ignoring case, or
    None. No partial matches, so search cannot list the directory. The viewer
    never finds themselves.
    """
    query = (query or "").strip()
    if not query:
        return None
    if "@" in query:
        match = Q(email__iexact=query) | Q(username__iexact=query)  # User.username is the email
    else:
        match = Q(profile__username=usernames.normalize(query))
    return findable_users().filter(match).exclude(pk=viewer.pk).first()


def find_by_username(username):
    return findable_users().filter(profile__username=usernames.normalize(username)).first()


def relationship(viewer, other):
    """(Relationship, the request that decides it or None)."""
    requests = list(FriendRequest.objects.filter(_between(viewer, other)))
    for request in requests:
        if request.status == Status.ACCEPTED:
            return Relationship.FRIENDS, request
    for request in requests:
        if request.sender_id == viewer.pk:
            return Relationship.SENT, request
    for request in requests:
        if request.status == Status.PENDING:
            return Relationship.RECEIVED, request
    # The viewer declined the other user's request: sending again accepts it.
    return Relationship.NONE, None


def send_request(sender, recipient, now=None):
    now = now or timezone.now()
    if recipient is None or sender.pk == recipient.pk:
        return SendResult.NOT_ALLOWED
    try:
        with transaction.atomic():
            rows = {
                r.sender_id: r
                for r in FriendRequest.objects.select_for_update().filter(_between(sender, recipient))
            }
            mine, theirs = rows.get(sender.pk), rows.get(recipient.pk)
            if any(r.status == Status.ACCEPTED for r in rows.values()):
                return SendResult.ALREADY_FRIENDS
            if theirs is not None:
                # They asked first (even if this user declined): accept it.
                theirs.status = Status.ACCEPTED
                theirs.responded_at = now
                theirs.save(update_fields=["status", "responded_at"])
                return SendResult.BECAME_FRIENDS
            if mine is not None:
                return SendResult.ALREADY_SENT
            FriendRequest.objects.create(sender=sender, recipient=recipient, last_sent_at=now)
    except IntegrityError:
        # The same request was created at the same moment.
        return SendResult.ALREADY_SENT
    return SendResult.SENT


def respond(request_id, recipient, accept, now=None):
    """Accept or decline a pending request sent to `recipient`. False if there is none."""
    now = now or timezone.now()
    updated = FriendRequest.objects.filter(
        pk=request_id, recipient=recipient, status=Status.PENDING
    ).update(status=Status.ACCEPTED if accept else Status.DECLINED, responded_at=now)
    return bool(updated)


def resend_request(request_id, sender, now=None):
    """
    Resend `sender`'s request. Returns None on success, or why it was refused.
    A declined request becomes pending again (the sender was never told).
    """
    now = now or timezone.now()
    with transaction.atomic():
        request = (
            FriendRequest.objects.select_for_update()
            .filter(pk=request_id, sender=sender)
            .exclude(status=Status.ACCEPTED)
            .first()
        )
        if request is None:
            return "That request can't be resent."
        refusal = resend.resend_refusal(request.last_sent_at, request.resend_count, now)
        if refusal:
            return refusal
        request.last_sent_at = now
        request.resend_count += 1
        request.status = Status.PENDING
        request.responded_at = None
        request.save(update_fields=["last_sent_at", "resend_count", "status", "responded_at"])
    return None


def received_requests(user):
    return (
        FriendRequest.objects.filter(recipient=user, status=Status.PENDING)
        .select_related("sender__profile__program")
        .order_by("-last_sent_at", "-pk")
    )


def sent_requests(user):
    return (
        FriendRequest.objects.filter(sender=user)
        .exclude(status=Status.ACCEPTED)
        .select_related("recipient__profile__program")
        .order_by("-last_sent_at", "-pk")
    )


def can_view_profile(viewer, other):
    """
    Profiles (#97) are open to friends and to the two users of a pending
    request (either direction). Everyone else gets a 404.
    """
    if viewer.pk == other.pk:
        return True
    state, _ = relationship(viewer, other)
    return state != Relationship.NONE


def upcoming_events_of(friend, viewer, now=None):
    """
    A friend's profile (#97): events that have not ended which the friend hosts
    or answered Going, limited to what the viewer may see (#41). Maybe and Not
    going are left out.
    """
    if not attendance_visible_to(viewer, friend):
        return Event.objects.none()
    now = now or timezone.now()
    going = Q(attendances__user=friend, attendances__status=EventAttendance.Status.GOING)
    return (
        visible_events(Event.objects.filter(end_at__gt=now), viewer)
        .filter(Q(creator=friend) | going)
        .distinct()
        .order_by("start_at", "pk")
    )
