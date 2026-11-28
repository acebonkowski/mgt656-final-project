"""Settings (#83): profile photo, who sees the events I'm going to, delete account."""
import logging

from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from accounts.models import Profile
from core import photo_storage
from core.header import profile_menu_context
from core.models import Event, ProfilePhoto

logger = logging.getLogger(__name__)

CONFIRM_WORD = "DELETE"


def delete_account_data(user):
    """Delete the user and everything of theirs, then remove their photos from storage.

    Hosted events: upcoming ones are deleted (nobody is left to run them), and so
    are past ones that were not public, because an event with no creator is treated
    as visible to everyone (core.visibility) and would otherwise leak. Past public
    events stay, without a host.
    """
    keys = []
    with transaction.atomic():
        Event.objects.filter(creator=user).filter(
            Q(end_at__gte=timezone.now()) | ~Q(visibility=Event.Visibility.EVERYONE)
        ).delete()
        profile = Profile.objects.filter(user=user).first()
        if profile:
            photos = ProfilePhoto.objects.filter(profile=profile)
            keys = list(photos.values_list("object_key", flat=True))
            photos.delete()  # PROTECT on the profile FK would otherwise block the cascade
        user.delete()
    for key in keys:
        try:
            photo_storage.delete(key)
        except photo_storage.StorageUnavailable:
            logger.warning("Could not remove profile photo object after account deletion")


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def settings_page(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    saved = False
    error = ""
    if request.method == "POST":
        value = request.POST.get("attendance_visibility", "")
        if value in Profile.AttendanceVisibility.values:
            profile.attendance_visibility = value
            profile.save(update_fields=["attendance_visibility", "updated_at"])
            return redirect("/settings/?saved=1")
        error = "Choose who can see the events you are going to."
    saved = request.GET.get("saved") == "1"
    return render(request, "core/settings.html", {
        "profile": profile,
        "choices": Profile.AttendanceVisibility.choices,
        "saved": saved,
        "error": error,
        **profile_menu_context(request.user),
    }, status=400 if error else 200)


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def delete_account(request):
    error = ""
    if request.method == "POST":
        if request.POST.get("confirm", "").strip() == CONFIRM_WORD:
            delete_account_data(request.user)
            logout(request)
            return redirect("accounts:welcome")
        error = f"Type {CONFIRM_WORD} to confirm."
    return render(request, "core/delete_account.html", {
        "confirm_word": CONFIRM_WORD, "error": error,
    }, status=400 if error else 200)
