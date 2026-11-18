"""
Per-user AI usage limits (#36).

Call reserve() before every OpenRouter request. It raises LimitReached when a
limit is hit, otherwise it records the call (also when the request later
fails: it still used credits). Limits come from settings (environment
variables) and days run midnight to midnight in America/New_York.

Built to be shared: #31's AI image generation can add its own Kind and call
reserve() the same way.
"""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone

from core.models import AIUsage

NEW_YORK = ZoneInfo("America/New_York")


class LimitReached(Exception):
    """The message is safe to show to the user."""


def start_of_day(now):
    local = now.astimezone(NEW_YORK)
    return datetime.combine(local.date(), time.min, tzinfo=NEW_YORK)


def is_exempt(user):
    """Graders (seeded accounts) and staff skip the per-user limits."""
    email = (user.email or user.get_username() or "").strip().lower()
    return user.is_staff or email in {e.lower() for e in settings.GRADER_EMAILS}


def check(user, kind, now=None):
    """Raise LimitReached if `user` may not make another `kind` call now."""
    now = now or timezone.now()
    today = start_of_day(now)

    if AIUsage.objects.filter(created_at__gte=today).count() >= settings.AI_GLOBAL_DAILY_LIMIT:
        raise LimitReached(
            "AI search has reached today's limit for the whole app. "
            "Try again tomorrow; manual search still works."
        )
    if is_exempt(user):
        return

    mine = AIUsage.objects.filter(user=user)
    if mine.filter(created_at__gte=now - timedelta(minutes=1)).count() >= settings.AI_SEARCH_PER_MINUTE_LIMIT:
        raise LimitReached("You're sending messages quickly. Wait a minute and try again.")
    if mine.filter(created_at__gte=today).count() >= settings.AI_SEARCH_DAILY_LIMIT:
        raise LimitReached(
            f"You've used today's {settings.AI_SEARCH_DAILY_LIMIT} AI searches. "
            "Try again tomorrow; manual search still works."
        )
    if kind == AIUsage.Kind.IMAGE_SEARCH and (
        mine.filter(kind=AIUsage.Kind.IMAGE_SEARCH, created_at__gte=today).count()
        >= settings.AI_IMAGE_SEARCH_DAILY_LIMIT
    ):
        raise LimitReached(
            f"You've used today's {settings.AI_IMAGE_SEARCH_DAILY_LIMIT} image searches. "
            "You can still type or say what you're looking for."
        )


def reserve(user, kind, now=None):
    """Check the limits, then record the call. Raises LimitReached."""
    now = now or timezone.now()
    check(user, kind, now)
    return AIUsage.objects.create(user=user, kind=kind, created_at=now)
