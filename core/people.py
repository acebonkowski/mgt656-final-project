"""
Showing other people (#96, #97, #85): name, username, program and photo.

Other users' photos are served from a signed, expiring link. A page creates
the link only for people it is allowed to show (a search match, a friend, a
request), so the photo view itself needs no relationship query and a photo
cannot be fetched by guessing a user id.
"""

from django.core import signing
from django.templatetags.static import static
from django.urls import reverse

PHOTO_SALT = "core.people.photo"
PHOTO_LINK_MAX_AGE = 60 * 60 * 24  # seconds
DEFAULT_PHOTO = "core/bulldog.svg"


def photo_url(user):
    profile = getattr(user, "profile", None)
    if profile is None or not profile.photo_reference:
        return static(DEFAULT_PHOTO)
    token = signing.dumps(user.pk, salt=PHOTO_SALT, compress=True)
    return reverse("person_photo", kwargs={"token": token})


def user_from_photo_token(token):
    """The user id in a valid, unexpired photo link, or None."""
    try:
        return signing.loads(token, salt=PHOTO_SALT, max_age=PHOTO_LINK_MAX_AGE)
    except signing.BadSignature:
        return None


def display_name(user):
    profile = getattr(user, "profile", None)
    if profile is not None and profile.display_name:
        return profile.display_name
    if profile is not None and profile.username:
        return profile.username
    return user.email


def person(user):
    """Template-ready details. Expects `profile` (and its program) selected."""
    profile = getattr(user, "profile", None)
    return {
        "user": user,
        "name": display_name(user),
        "username": profile.username if profile else "",
        "email": user.email,
        "program": profile.program if profile and profile.program_id else None,
        "photo_url": photo_url(user),
        "has_photo": bool(profile and profile.photo_reference),
    }
