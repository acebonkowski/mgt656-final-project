"""
Friends page and friend request endpoints (#96).

The endpoints are plain form POSTs that redirect back to the Friends page with
a message, so they work without JavaScript.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from accounts.models import Profile
from core import friends, people, photo_storage, resend
from core.models import ProfilePhoto

TABS = ("received", "sent")
SEND_MESSAGES = {
    friends.SendResult.SENT: (messages.SUCCESS, "Friend request sent."),
    friends.SendResult.BECAME_FRIENDS: (messages.SUCCESS, "You're now friends."),
    friends.SendResult.ALREADY_SENT: (messages.INFO, "You already sent a request. Use Resend in Sent."),
    friends.SendResult.ALREADY_FRIENDS: (messages.INFO, "You're already friends."),
    friends.SendResult.NOT_ALLOWED: (messages.ERROR, "You can't send a request to that account."),
}


def _back(request):
    """The Friends page the form was on (search and tab kept), never another site."""
    target = request.POST.get("return_to", "")
    friends_url = reverse("friends")
    if target.startswith(friends_url) and "//" not in target:
        return redirect(target)
    return redirect(friends_url)


def _sent_item(request_obj, now=None):
    refusal = resend.resend_refusal(request_obj.last_sent_at, request_obj.resend_count, now)
    return {
        "request": request_obj,
        "person": people.person(request_obj.recipient),
        "resend_refusal": refusal,
        "resends_left": resend.resends_left(request_obj.resend_count),
    }


@login_required
@never_cache
@require_GET
def friends_page(request):
    tab = request.GET.get("tab")
    tab = tab if tab in TABS else "received"
    query = request.GET.get("q", "").strip()[:254]

    result = None
    if query:
        match = friends.find_user(query, request.user)
        if match is not None:
            state, _ = friends.relationship(request.user, match)
            result = {"person": people.person(match), "state": state.value}

    received = [
        {"request": r, "person": people.person(r.sender)}
        for r in friends.received_requests(request.user)
    ]
    sent = [_sent_item(r) for r in friends.sent_requests(request.user)]
    friend_list = [people.person(friend) for friend in friends.friends_list(request.user)]
    profile = Profile.objects.filter(user=request.user).only("username").first()
    return render(request, "core/friends.html", {
        "my_username": profile.username if profile else "",
        "query": query,
        "searched": bool(query),
        "result": result,
        "tab": tab,
        "received": received,
        "sent": sent,
        "received_count": len(received),
        "friends": friend_list,
        "return_to": request.get_full_path(),
    })


@login_required
@require_POST
def send_friend_request(request):
    recipient = friends.find_by_username(request.POST.get("username", ""))
    if recipient is None:
        messages.error(request, "We couldn't find that user.")
        return _back(request)
    level, text = SEND_MESSAGES[friends.send_request(request.user, recipient)]
    messages.add_message(request, level, text)
    return _back(request)


@login_required
@require_POST
def accept_friend_request(request, request_id):
    if not friends.respond(request_id, request.user, accept=True):
        raise Http404
    messages.success(request, "You're now friends.")
    return _back(request)


@login_required
@require_POST
def decline_friend_request(request, request_id):
    if not friends.respond(request_id, request.user, accept=False):
        raise Http404
    messages.info(request, "Request declined.")
    return _back(request)


@login_required
@require_POST
def resend_friend_request(request, request_id):
    refusal = friends.resend_request(request_id, request.user)
    if refusal:
        messages.error(request, refusal)
    else:
        messages.success(request, "Friend request sent again.")
    return _back(request)


@login_required
@never_cache
@require_GET
def profile_page(request, username):
    """
    /people/<username>/ (#97): name, photo and program for friends and pending
    requests; a friend's upcoming events too. Anyone else gets a 404, so
    profiles cannot be browsed by guessing usernames.
    """
    other = friends.find_by_username(username)
    if other is None or other.pk == request.user.pk:
        if other is not None:
            return redirect("friends")  # your own profile: the Friends page
        raise Http404
    state, _ = friends.relationship(request.user, other)
    if state == friends.Relationship.NONE:
        raise Http404
    is_friend = state == friends.Relationship.FRIENDS
    events = list(friends.upcoming_events_of(other, request.user)) if is_friend else []
    return render(request, "core/profile.html", {
        "p": people.person(other),
        "state": state.value,
        "is_friend": is_friend,
        "events": events,
    })


@login_required
@require_GET
def person_photo(request, token):
    """Another user's photo, from a signed link a page made for them (core.people)."""
    user_id = people.user_from_photo_token(token)
    profile = Profile.objects.filter(user_id=user_id).only("photo_reference").first() if user_id else None
    if profile is None or not profile.photo_reference:
        raise Http404
    photo = ProfilePhoto.objects.filter(
        profile=profile, object_key=profile.photo_reference, archived_at=None
    ).first()
    if photo is None:
        raise Http404
    try:
        data = photo_storage.download(photo.object_key)
    except photo_storage.StorageUnavailable:
        return HttpResponse(status=503)
    response = HttpResponse(data, content_type=photo.content_type)
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, max-age=3600"
    return response
