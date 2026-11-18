"""Single-event iCalendar (.ics) files for "Save to calendar" (#32).

One file works with Apple, Google and Outlook calendars, so there are no
per-provider integrations. Times are written in America/New_York with a
VTIMEZONE block (Outlook needs it); DTSTAMP is UTC as RFC 5545 requires.
"""

from datetime import datetime, timezone as dt_timezone
from zoneinfo import ZoneInfo

NEW_YORK = ZoneInfo("America/New_York")
TZID = "America/New_York"
PRODID = "-//Yale Events//Event page//EN"
UID_DOMAIN = "yale-events"
MAX_LINE_OCTETS = 75

# US daylight-saving rules in force since 2007.
NEW_YORK_VTIMEZONE = [
    "BEGIN:VTIMEZONE",
    f"TZID:{TZID}",
    "BEGIN:DAYLIGHT",
    "TZOFFSETFROM:-0500",
    "TZOFFSETTO:-0400",
    "TZNAME:EDT",
    "DTSTART:19700308T020000",
    "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU",
    "END:DAYLIGHT",
    "BEGIN:STANDARD",
    "TZOFFSETFROM:-0400",
    "TZOFFSETTO:-0500",
    "TZNAME:EST",
    "DTSTART:19701101T020000",
    "RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU",
    "END:STANDARD",
    "END:VTIMEZONE",
]


def escape_text(value):
    """Escape a TEXT value (RFC 5545 section 3.3.11)."""
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n", "\\n")
    )


def fold_line(line):
    """Fold a content line at 75 octets without splitting UTF-8 characters."""
    parts = []
    current = ""
    current_octets = 0
    for char in line:
        size = len(char.encode("utf-8"))
        if current_octets + size > MAX_LINE_OCTETS:
            parts.append(current)
            # Continuation lines start with one space, which counts as an octet.
            current, current_octets = " ", 1
        current += char
        current_octets += size
    parts.append(current)
    return "\r\n".join(parts)


def local_time(value):
    """Format an aware datetime as New York local time (YYYYMMDDTHHMMSS)."""
    return value.astimezone(NEW_YORK).strftime("%Y%m%dT%H%M%S")


def utc_time(value):
    return value.astimezone(dt_timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def build_ics(event, now=None):
    """Return a VCALENDAR with exactly one VEVENT for `event` as a string."""
    now = now or datetime.now(dt_timezone.utc)
    description = event.description
    if event.link:
        description = f"{description}\n\n{event.link}"
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        *NEW_YORK_VTIMEZONE,
        "BEGIN:VEVENT",
        f"UID:event-{event.pk}@{UID_DOMAIN}",
        f"DTSTAMP:{utc_time(now)}",
        f"DTSTART;TZID={TZID}:{local_time(event.start_at)}",
        f"DTEND;TZID={TZID}:{local_time(event.end_at)}",
        f"SUMMARY:{escape_text(event.name)}",
        f"DESCRIPTION:{escape_text(description)}",
        f"LOCATION:{escape_text(event.location)}",
    ]
    if event.link:
        lines.append(f"URL:{event.link}")
    lines += ["END:VEVENT", "END:VCALENDAR"]
    return "".join(fold_line(line) + "\r\n" for line in lines)
