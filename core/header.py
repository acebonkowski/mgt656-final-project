"""Profile menu integration points for Friends (#39) and Settings (#83)."""
from django.urls import reverse

from accounts.models import Profile


def incoming_friend_request_count(user):
    """Return the signed-in user's pending incoming request count.

    Temporary zero until #39 supplies its model/query. Count received pending
    requests only, not sent, accepted, rejected, or cancelled requests. The
    menu reads this once per page render; both badges share the result.
    """
    return 0


def profile_menu_context(user):
    profile = Profile.objects.filter(user=user).first()
    return {
        "menu_photo_url": reverse("profile_photo") if profile and profile.photo_reference else None,
        "incoming_friend_requests": incoming_friend_request_count(user),
        "friends_menu_url": reverse("friends"),
        "settings_menu_url": reverse("settings"),
    }
