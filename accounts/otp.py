"""
One-time login codes (#6).

Rules:
- Only @yale.edu addresses and its subdomains (e.g. @som.yale.edu).
- Codes are 6 digits, valid for 10 minutes, and stop working after 5 wrong tries.
  Only a keyed hash is stored, and a code works once.
- A new code can be sent 45 seconds after the previous one.
- The seeded grader addresses use the fixed code from GRADER_FIXED_OTP and never
  receive email. 5 wrong tries lock them out for 15 minutes.
"""

import enum
import logging
import secrets
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

from accounts.models import LoginCode

logger = logging.getLogger(__name__)

CODE_LENGTH = 6
CODE_TTL = timedelta(minutes=10)
RESEND_COOLDOWN = timedelta(seconds=45)
MAX_ATTEMPTS = 5
GRADER_LOCKOUT = timedelta(minutes=15)
ALLOWED_DOMAIN = "yale.edu"
HASH_SALT = "accounts.otp.login-code"


class EmailNotAllowed(Exception):
    """The address is empty, malformed or not a Yale address."""


class CodeNotSent(Exception):
    """The code could not be emailed (delivery off, or the email service failed)."""


class Result(enum.Enum):
    OK = "ok"
    INVALID = "invalid"        # wrong code (or no code requested)
    EXPIRED = "expired"
    TOO_MANY = "too_many"      # 5 wrong tries: this code no longer works
    LOCKED = "locked"          # grader address temporarily locked
    DISABLED = "disabled"      # grader login is not configured


@dataclass
class SendOutcome:
    sent: bool                  # False when the 45-second wait was still running
    seconds_until_resend: int


def normalize_email(email):
    return (email or "").strip().lower()


def check_email(email):
    """Return the normalized address or raise EmailNotAllowed with a user message."""
    email = normalize_email(email)
    if not email:
        raise EmailNotAllowed("Please enter your Yale email address.")
    try:
        validate_email(email)
    except ValidationError:
        raise EmailNotAllowed("Please enter a valid email address.")
    domain = email.rsplit("@", 1)[1]
    if domain != ALLOWED_DOMAIN and not domain.endswith("." + ALLOWED_DOMAIN):
        raise EmailNotAllowed("Only yale.edu email addresses are accepted.")
    return email


def is_grader(email):
    return normalize_email(email) in {normalize_email(e) for e in settings.GRADER_EMAILS}


def _hash(email, code):
    return salted_hmac(HASH_SALT, f"{email}:{code}").hexdigest()


def _new_code():
    return f"{secrets.randbelow(10 ** CODE_LENGTH):0{CODE_LENGTH}d}"


def seconds_until_resend(record, now=None):
    if not record or not record.sent_at:
        return 0
    now = now or timezone.now()
    remaining = (record.sent_at + RESEND_COOLDOWN - now).total_seconds()
    return max(0, int(remaining + 0.999))  # round up, so 0 means "allowed now"


def get_record(email):
    return LoginCode.objects.filter(email=normalize_email(email)).first()


def request_code(email):
    """Send a new code to a checked address, unless the 45-second wait is running.

    Grader addresses get no email: they use the fixed code. Raises CodeNotSent if
    the email can't be delivered; nothing is saved in that case, so the user can
    try again straight away."""
    email = normalize_email(email)
    now = timezone.now()
    record = get_record(email)
    wait = seconds_until_resend(record, now)
    if wait:
        return SendOutcome(sent=False, seconds_until_resend=wait)

    if is_grader(email):
        if not settings.GRADER_FIXED_OTP:
            raise CodeNotSent("Grader login isn't set up yet.")
        LoginCode.objects.update_or_create(email=email, defaults={"sent_at": now})
        return SendOutcome(sent=True, seconds_until_resend=int(RESEND_COOLDOWN.total_seconds()))

    if not settings.EMAIL_DELIVERY_ENABLED:
        logger.error("Login code not sent: RESEND_API_KEY is not set")
        raise CodeNotSent("We couldn't send the code right now. Please try again later.")

    code = _new_code()
    minutes = int(CODE_TTL.total_seconds() // 60)
    try:
        send_mail(
            subject=f"Your Yale Events login code: {code}",
            message=(
                f"Your login code is {code}.\n\n"
                f"It expires in {minutes} minutes and works once. "
                "If you didn't ask for it, you can ignore this email."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
        )
    except Exception:
        # Never log the code itself.
        logger.exception("Sending a login code failed")
        raise CodeNotSent("We couldn't send the code. Please try again in a moment.")

    LoginCode.objects.update_or_create(
        email=email,
        defaults={
            "code_hash": _hash(email, code),
            "sent_at": now,
            "expires_at": now + CODE_TTL,
            "failed_attempts": 0,
            "locked_until": None,
        },
    )
    return SendOutcome(sent=True, seconds_until_resend=int(RESEND_COOLDOWN.total_seconds()))


def verify_code(email, code):
    """Check a code for an address and return a Result."""
    email = normalize_email(email)
    code = (code or "").strip()
    now = timezone.now()

    with transaction.atomic():
        if is_grader(email):
            return _verify_grader(email, code, now)

        record = LoginCode.objects.select_for_update().filter(email=email).first()
        if not record or not record.code_hash:
            return Result.TOO_MANY if record and record.failed_attempts >= MAX_ATTEMPTS else Result.INVALID
        if record.expires_at and now >= record.expires_at:
            return Result.EXPIRED
        if constant_time_compare(record.code_hash, _hash(email, code)):
            record.code_hash = ""  # single use
            record.failed_attempts = 0
            record.save(update_fields=["code_hash", "failed_attempts"])
            return Result.OK

        record.failed_attempts += 1
        if record.failed_attempts >= MAX_ATTEMPTS:
            record.code_hash = ""  # this code no longer works
            record.save(update_fields=["code_hash", "failed_attempts"])
            return Result.TOO_MANY
        record.save(update_fields=["failed_attempts"])
        return Result.INVALID


def _verify_grader(email, code, now):
    if not settings.GRADER_FIXED_OTP:
        return Result.DISABLED
    record, _ = LoginCode.objects.select_for_update().get_or_create(email=email)
    if record.locked_until and now < record.locked_until:
        return Result.LOCKED
    if constant_time_compare(code, settings.GRADER_FIXED_OTP):
        record.failed_attempts = 0
        record.locked_until = None
        record.save(update_fields=["failed_attempts", "locked_until"])
        return Result.OK
    record.failed_attempts += 1
    if record.failed_attempts >= MAX_ATTEMPTS:
        record.failed_attempts = 0
        record.locked_until = now + GRADER_LOCKOUT
        record.save(update_fields=["failed_attempts", "locked_until"])
        logger.warning("Grader login locked for %s minutes after %s wrong codes",
                       int(GRADER_LOCKOUT.total_seconds() // 60), MAX_ATTEMPTS)
        return Result.LOCKED
    record.save(update_fields=["failed_attempts"])
    return Result.INVALID
