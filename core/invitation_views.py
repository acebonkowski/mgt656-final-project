"""
Invitation endpoints and the View All page (#86). Plain form POSTs that
redirect back with a message, so they also work from the map's event window.
"""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.text import get_text_list
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from core import invitations, people
from core.models import Event, EventInvitation
from core.visibility import can_view


def _safe_return(request, default):
    target = request.POST.get("return_to", "")
    if target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return redirect(target)
    return redirect(default)


def invitation_box_context(user):
    """The Invitations box on the map (#86)."""
    items = []
    for invitation in invitations.inbox(user):
        status = invitation.status or ""
        items.append({
            "invitation": invitation,
            "event": invitation.event,
            "sender": people.person(invitation.sender),
            "status": status,
            "status_label": invitations.STATUS_LABELS[status],
        })
    return {
        "invitation_items": items,
        "unanswered_invitations": sum(1 for item in items if not item["status"]),
    }


def invite_context(request, event):
    """"Send to Friend" on the event page and event window (#86)."""
    user = request.user
    if not user.is_authenticated:
        return {"show_invite": False}
    if event.end_at <= timezone.now():
        return {"show_invite": False}
    candidates = invitations.invitable_friends(user, event)
    return {
        "show_invite": True,
        "invite_friends": [people.person(friend) for friend in candidates],
        "note_max_length": invitations.INVITATION_TEXT_MAX_LENGTH,
    }


@login_required
@require_POST
def send_invitations(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
    if not can_view(request.user, event):
        raise Http404
    page = reverse("event_detail", kwargs={"event_id": event.pk})
    ids = [value for value in request.POST.getlist("recipients") if value.isdigit()]
    recipients = list(get_user_model().objects.filter(pk__in=ids).select_related("profile"))
    if len(recipients) != len(set(ids)):
        messages.error(request, "You can only send events to friends.")
        return redirect(page)
    try:
        sent = invitations.send(request.user, event, recipients, request.POST.get("note", ""))
    except invitations.InvitationError as error:
        messages.error(request, str(error))
        return redirect(page)
    names = [people.display_name(invitation.recipient) for invitation in sent]
    messages.success(request, f"Sent to {get_text_list(names, 'and')}.")
    return redirect(page)


@login_required
@require_POST
def reply_invitation(request, invitation_id):
    try:
        invitations.reply(invitation_id, request.user, request.POST.get("status", ""),
                          request.POST.get("message", ""))
    except EventInvitation.DoesNotExist:
        raise Http404
    except invitations.InvitationError as error:
        messages.error(request, str(error))
    return _safe_return(request, reverse("map") + "#invitations")


@login_required
@require_POST
def resend_invitation(request, invitation_id):
    refusal = invitations.resend_invitation(invitation_id, request.user)
    if refusal:
        messages.error(request, refusal)
    else:
        messages.success(request, "Invitation sent again.")
    return redirect("invitations")


@login_required
@never_cache
@require_GET
def invitations_page(request):
    """View All (#86): sent invitations grouped by event, with each friend's answer."""
    groups = invitations.sent_by_event(request.user)
    for group in groups:
        for item in group["items"]:
            item["person"] = people.person(item["invitation"].recipient)
    return render(request, "core/invitations.html", {"groups": groups})
