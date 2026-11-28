"""
The resend rule shared by friend requests (#96) and event invitations (#86):
the first send plus up to 2 resends, each at least 24h after the previous send.
"""

from datetime import timedelta

from django.utils import formats, timezone

MAX_RESENDS = 2
MIN_INTERVAL = timedelta(hours=24)


def next_resend_at(last_sent_at):
    return last_sent_at + MIN_INTERVAL


def resend_refusal(last_sent_at, resend_count, now=None):
    """None when a resend is allowed now, otherwise the reason it is not."""
    now = now or timezone.now()
    if resend_count >= MAX_RESENDS:
        return "No resends left."
    allowed_at = next_resend_at(last_sent_at)
    if now < allowed_at:
        local = timezone.localtime(allowed_at)
        return f"You can resend after {formats.date_format(local, 'M j, g:i A')}."
    return None


def resends_left(resend_count):
    return max(0, MAX_RESENDS - resend_count)
