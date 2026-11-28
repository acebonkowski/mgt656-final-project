"""
Usernames (#95): the handle friends search for (#96). Stored on Profile, not on
Django's User, whose `username` already holds the login email.

Rules: 3-20 characters; lowercase letters, digits, "_" and "."; starts with a
letter; no "." or "_" twice in a row; not reserved. Input is trimmed and
lowercased first, so "Alex.K" is saved as "alex.k". Uniqueness ignores case and
is enforced by a database constraint on Profile as well as by the forms.
"""

import re

from django.core.exceptions import ValidationError

MIN_LENGTH = 3
MAX_LENGTH = 20
RESERVED = frozenset({"admin", "support", "friends", "settings", "me"})
TAKEN_MESSAGE = "That username is taken."
RULES_HELP = (
    f"{MIN_LENGTH}-{MAX_LENGTH} characters: lowercase letters, numbers, "
    "\"_\" and \".\". Start with a letter."
)

_ALLOWED = re.compile(r"[a-z0-9._]+")
_REPEATED_SEPARATOR = re.compile(r"[._]{2}")


def normalize(value):
    return (value or "").strip().lower()


def validate_username(value):
    """Raise ValidationError naming the first rule `value` breaks."""
    if len(value) < MIN_LENGTH:
        raise ValidationError(f"Use at least {MIN_LENGTH} characters.", code="too_short")
    if len(value) > MAX_LENGTH:
        raise ValidationError(f"Use at most {MAX_LENGTH} characters.", code="too_long")
    if not _ALLOWED.fullmatch(value):
        raise ValidationError(
            'Use only lowercase letters, numbers, "_" and ".".', code="invalid_character"
        )
    if not value[0].isalpha():
        raise ValidationError("Start with a letter.", code="must_start_with_letter")
    if _REPEATED_SEPARATOR.search(value):
        raise ValidationError('Don\'t use "." or "_" twice in a row.', code="repeated_separator")
    if value in RESERVED:
        raise ValidationError("That username is reserved.", code="reserved")


def is_taken(username, exclude_profile_pk=None):
    from accounts.models import Profile

    others = Profile.objects.filter(username__iexact=username)
    if exclude_profile_pk is not None:
        others = others.exclude(pk=exclude_profile_pk)
    return others.exists()
