"""
Username gate (#95): a logged-in user who finished onboarding before usernames
existed is sent to /username/ until they choose one.

The check runs once per session: at login (the `user_logged_in` signal) or, for
sessions from before #95, on the first page load. When no username is needed,
the session remembers it, so later page loads make no extra query. Usernames
cannot be cleared again, and onboarding (which asks for one) marks the session
itself, so the remembered answer does not go stale.

Only GET and HEAD page loads are redirected, so a POST already in flight (a
going answer, a photo upload) is not turned into a redirect.
"""

from urllib.parse import urlencode

from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from django.shortcuts import redirect
from django.urls import reverse

from accounts.models import Profile

SESSION_KEY = "username_checked"

# The page itself, the way out, onboarding (which asks for the username) and
# the user's own photo (onboarding shows it).
EXEMPT_URL_NAMES = frozenset({
    "username", "logout", "onboarding", "profile_photo", "healthz", "admin_login",
})
EXEMPT_PATH_PREFIXES = ("/admin/", "/static/", "/internal/")


def mark_username_set(request):
    request.session[SESSION_KEY] = True


def username_url(next_url=None):
    url = reverse("username")
    return f"{url}?{urlencode({'next': next_url})}" if next_url else url


def needs_username(user):
    """True when `user` finished onboarding but has no username yet."""
    profile = Profile.objects.filter(user=user).only("onboarding_complete", "username").first()
    return bool(profile and profile.onboarding_complete and not profile.username)


@receiver(user_logged_in, dispatch_uid="accounts_username_check_at_login")
def check_username_at_login(sender, request, user, **kwargs):
    if request is not None and hasattr(request, "session") and not needs_username(user):
        mark_username_set(request)


class UsernameRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        if request.method not in ("GET", "HEAD"):
            return None
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated or request.session.get(SESSION_KEY):
            return None
        if request.path.startswith(EXEMPT_PATH_PREFIXES):
            return None
        match = request.resolver_match
        if match is not None and match.url_name in EXEMPT_URL_NAMES:
            return None
        if needs_username(user):
            return redirect(username_url(request.get_full_path()))
        mark_username_set(request)
        return None
