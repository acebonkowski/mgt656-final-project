"""
Invitations (#86): send an event to friends, answer on the map, see the answers.

An invitation's status is the recipient's going status for the event (#84):
Going, Maybe, Not going, or no answer yet. Replying writes that status with the
same rules as the event page dropdown (core.attendance.can_answer), so the
event page and My Events > Upcoming show it, and a later change on the event
page shows up here.
"""

from collections import OrderedDict

from django.db import IntegrityError, transaction
from django.db.models import OuterRef, Subquery
from django.utils import timezone

from core import friends, resend
from core.attendance import can_answer
from core.models import INVITATION_TEXT_MAX_LENGTH, Event, EventAttendance, EventInvitation
from core.visibility import can_view, visible_events

Status = EventAttendance.Status
STATUS_LABELS = {
    Status.GOING: "Going",
    Status.MAYBE: "Maybe",
    Status.NOT_GOING: "Not going",
    "": "No answer yet",
}


class InvitationError(Exception):
    """A refused send or reply. The message is shown to the user."""


def _clean_text(value):
    return (value or "").strip()[:INVITATION_TEXT_MAX_LENGTH]


def with_status(invitations):
    """Annotate `status`: the recipient's going answer for the event, or ""."""
    answer = EventAttendance.objects.filter(
        user=OuterRef("recipient_id"), event=OuterRef("event_id")
    ).values("status")[:1]
    return invitations.annotate(status=Subquery(answer))


def can_invite(sender, recipient, event, now=None):
    """Why `sender` may not send `event` to `recipient`, or None if they may."""
    now = now or timezone.now()
    if event.end_at <= now:
        return "This event has ended."
    if not can_view(sender, event):
        return "You can't send this event."
    if recipient.pk == sender.pk or not friends.are_friends(sender, recipient):
        return "You can only send events to friends."
    if event.creator_id == recipient.pk:
        return "They're hosting this event."
    if not can_view(recipient, event):
        return "They can't see this event."
    return None


def invitable_friends(sender, event, now=None):
    """The friend picker: friends who may get this event and were not sent it yet."""
    now = now or timezone.now()
    if event.end_at <= now:
        return []
    already = EventInvitation.objects.filter(sender=sender, event=event).values("recipient_id")
    candidates = friends.friends_list(sender).exclude(pk__in=already)
    if event.creator_id:
        candidates = candidates.exclude(pk=event.creator_id)
    # One visibility check per friend; friend lists are short.
    return [friend for friend in candidates if can_view(friend, event)]


def send(sender, event, recipients, note="", now=None):
    """
    Send `event` to each of `recipients`. All or nothing: if any recipient is
    not allowed, nothing is saved and InvitationError says why.
    """
    now = now or timezone.now()
    recipients = list({user.pk: user for user in recipients}.values())
    if not recipients:
        raise InvitationError("Choose at least one friend.")
    for recipient in recipients:
        refusal = can_invite(sender, recipient, event, now)
        if refusal:
            raise InvitationError(refusal)
    already = set(
        EventInvitation.objects.filter(sender=sender, event=event, recipient__in=recipients)
        .values_list("recipient_id", flat=True)
    )
    if already:
        raise InvitationError("You already sent this event to that friend. Use Resend.")
    note = _clean_text(note)
    try:
        with transaction.atomic():
            return EventInvitation.objects.bulk_create([
                EventInvitation(sender=sender, recipient=recipient, event=event, note=note,
                                last_sent_at=now)
                for recipient in recipients
            ])
    except IntegrityError:
        raise InvitationError("You already sent this event to that friend. Use Resend.")


def reply(invitation_id, recipient, status, message="", now=None):
    """
    The recipient answers Going, Maybe or Not going, with an optional message.
    Writes the going status (#84). Returns the invitation, or raises
    EventInvitation.DoesNotExist (shown as 404) / InvitationError.
    """
    now = now or timezone.now()
    invitation = (
        EventInvitation.objects.select_related("event")
        .get(pk=invitation_id, recipient=recipient)
    )
    if not can_view(recipient, invitation.event):
        raise EventInvitation.DoesNotExist
    if status not in Status.values:
        raise InvitationError("Choose Going, Maybe or Not going.")
    if not can_answer(recipient, invitation.event, now):
        raise InvitationError("You can't answer for this event any more.")
    with transaction.atomic():
        EventAttendance.objects.update_or_create(
            user=recipient, event=invitation.event, defaults={"status": status}
        )
        invitation.reply_message = _clean_text(message)
        invitation.replied_at = now
        invitation.save(update_fields=["reply_message", "replied_at"])
    return invitation


def resend_invitation(invitation_id, sender, now=None):
    """None when resent, otherwise why not. Only unanswered invitations."""
    now = now or timezone.now()
    with transaction.atomic():
        invitation = (
            EventInvitation.objects.select_for_update()
            .select_related("event", "recipient")
            .filter(pk=invitation_id, sender=sender)
            .first()
        )
        if invitation is None:
            return "That invitation can't be resent."
        if EventAttendance.objects.filter(user=invitation.recipient, event=invitation.event).exists():
            return "They already answered."
        if invitation.event.end_at <= now:
            return "This event has ended."
        refusal = resend.resend_refusal(invitation.last_sent_at, invitation.resend_count, now)
        if refusal:
            return refusal
        invitation.last_sent_at = now
        invitation.resend_count += 1
        invitation.save(update_fields=["last_sent_at", "resend_count"])
    return None


def inbox(user, now=None):
    """
    The Invitations box (#86): invitations received for events that have not
    ended and that the user can still see, newest send first.
    """
    now = now or timezone.now()
    visible = visible_events(Event.objects.filter(end_at__gt=now), user).values("pk")
    return list(
        with_status(EventInvitation.objects.filter(recipient=user, event__in=visible))
        .select_related("event", "sender__profile")
        .order_by("-last_sent_at", "-pk")
    )


def sent_by_event(user, now=None):
    """
    View All (#86): the events the user sent, each with the friends invited,
    their status and reply message. Events that have not ended, soonest first.
    """
    now = now or timezone.now()
    invitations = (
        with_status(EventInvitation.objects.filter(sender=user, event__end_at__gt=now))
        .select_related("event", "recipient__profile")
        .order_by("event__start_at", "event_id", "recipient__profile__display_name", "pk")
    )
    groups = OrderedDict()
    for invitation in invitations:
        refusal = (
            "They already answered." if invitation.status
            else resend.resend_refusal(invitation.last_sent_at, invitation.resend_count, now)
        )
        groups.setdefault(invitation.event_id, {"event": invitation.event, "items": []})["items"].append({
            "invitation": invitation,
            "status": invitation.status or "",
            "status_label": STATUS_LABELS[invitation.status or ""],
            "resend_refusal": refusal,
        })
    return list(groups.values())
