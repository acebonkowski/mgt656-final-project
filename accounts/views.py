"""Welcome and Code sent screens, login routing and the onboarding placeholder (#6)."""

from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render, resolve_url
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST

from accounts import otp, usernames
from accounts.forms import UsernameForm
from accounts.middleware import mark_username_set, username_url
from accounts.models import Profile

SESSION_EMAIL = "login_email"
SESSION_NEXT = "login_next"

ERRORS = {
    otp.Result.INVALID: "That code isn't right. Check it and try again.",
    otp.Result.EXPIRED: "That code has expired. Request a new one.",
    otp.Result.TOO_MANY: "Too many wrong tries. Request a new code.",
    otp.Result.LOCKED: "Too many wrong tries. Try again in 15 minutes.",
    otp.Result.DISABLED: "Grader login isn't set up yet.",
}


def destination_for(user, next_url=None):
    """Where a logged-in user goes: onboarding until their profile is complete,
    then the page they asked for, or the map."""
    profile, _ = Profile.objects.get_or_create(user=user)
    if not profile.onboarding_complete:
        return resolve_url(settings.ONBOARDING_URL)
    if not profile.username:
        # Accounts from before usernames (#95) choose one first.
        return username_url(next_url)
    return next_url or resolve_url(settings.LOGIN_REDIRECT_URL)


def _safe_next(request, value):
    if value and url_has_allowed_host_and_scheme(
        value, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return value
    return None


def _log_in(request, email):
    user, created = get_user_model().objects.get_or_create(
        username=email, defaults={"email": email}
    )
    if created:
        user.set_unusable_password()
        user.save(update_fields=["password"])
    next_url = request.session.pop(SESSION_NEXT, None)
    request.session.pop(SESSION_EMAIL, None)
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return destination_for(user, next_url)


def home(request):
    """'/' sends logged-in users to their home screen and everyone else to Welcome."""
    if request.user.is_authenticated:
        return redirect(destination_for(request.user))
    return redirect("accounts:welcome")


@never_cache
@require_http_methods(["GET", "POST"])
def welcome(request):
    if request.user.is_authenticated:
        return redirect(destination_for(request.user))

    next_url = _safe_next(request, request.GET.get("next"))
    if next_url:
        request.session[SESSION_NEXT] = next_url

    email = request.session.get(SESSION_EMAIL, "")
    error = None
    if request.method == "POST":
        email = request.POST.get("email", "")
        try:
            email = otp.check_email(email)
            otp.request_code(email)
        except (otp.EmailNotAllowed, otp.CodeNotSent) as exc:
            error = str(exc)
        else:
            request.session[SESSION_EMAIL] = email
            return redirect("accounts:code")

    return render(request, "accounts/welcome.html", {
        "email": email,
        "error": error,
    }, status=400 if error else 200)


@never_cache
@require_http_methods(["GET", "POST"])
def code(request):
    email = request.session.get(SESSION_EMAIL)
    if not email:
        return redirect("accounts:welcome")

    error = None
    if request.method == "POST":
        result = otp.verify_code(email, request.POST.get("code", ""))
        if result is otp.Result.OK:
            return redirect(_log_in(request, email))
        error = ERRORS[result]

    return render(request, "accounts/code.html", {
        "email": email,
        "error": error,
        "seconds_until_resend": otp.seconds_until_resend(otp.get_record(email)),
    }, status=400 if error else 200)


@never_cache
@require_POST
def resend(request):
    email = request.session.get(SESSION_EMAIL)
    if not email:
        return redirect("accounts:welcome")
    error = None
    try:
        outcome = otp.request_code(email)
        if not outcome.sent:
            error = f"You can resend the code in {outcome.seconds_until_resend} seconds."
    except otp.CodeNotSent as exc:
        error = str(exc)
    if error:
        return render(request, "accounts/code.html", {
            "email": email,
            "error": error,
            "seconds_until_resend": otp.seconds_until_resend(otp.get_record(email)),
        }, status=400)
    return redirect("accounts:code")


@login_required
def onboarding(request):
    """Compatibility entry point; all routes use the real #7 screen."""
    from core.views import onboarding as onboarding_view
    return onboarding_view(request)


def admin_login(request):
    """Django admin's password login is replaced by the Welcome screen. Staff who
    logged in there are let into /admin by Django's normal staff check."""
    url = resolve_url("accounts:welcome")
    next_url = _safe_next(request, request.GET.get("next"))
    if next_url:
        url = f"{url}?{urlencode({'next': next_url})}"
    return redirect(url)


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def choose_username(request):
    """
    /username/ (#95): choose a username, or change it. Users who finished
    onboarding without one are sent here by UsernameRequiredMiddleware.
    """
    profile, _ = Profile.objects.get_or_create(user=request.user)
    if not profile.onboarding_complete:
        return redirect(settings.ONBOARDING_URL)  # onboarding asks for it
    next_url = _safe_next(request, request.POST.get("next") or request.GET.get("next"))
    had_username = bool(profile.username)
    form = UsernameForm(request.POST if request.method == "POST" else None, instance=profile)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                Profile.objects.filter(pk=profile.pk).update(
                    username=form.cleaned_data["username"], updated_at=timezone.now()
                )
        except IntegrityError:
            # Someone took the name between validation and saving.
            form.add_error("username", usernames.TAKEN_MESSAGE)
        else:
            mark_username_set(request)
            return redirect(next_url or resolve_url(settings.LOGIN_REDIRECT_URL))
    return render(request, "accounts/username.html", {
        "form": form,
        "next": next_url or "",
        "is_change": had_username,
        "current_username": profile.username if had_username else "",
    }, status=400 if form.errors else 200)
