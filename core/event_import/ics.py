"""Parse saved Yale/SOM feeds into a provisional, model-independent contract."""

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import parse_qs, urlsplit

from icalendar import Calendar

from .categories import classify

SOURCES = ("yale_connect", "som")


@dataclass(frozen=True)
class Candidate:
    source: str
    external_id: str
    name: str
    description: str
    starts_at: datetime
    ends_at: datetime
    location_text: str
    link: str
    category: str
    category_source: str
    # Unknown price is not free. Coordinates/images await shared services in #31.
    price: Decimal | None = None
    latitude: str | None = None
    longitude: str | None = None
    city: str = ""
    state: str = ""

    @property
    def identity(self):
        return self.source, self.external_id

    @property
    def duplicate_key(self):
        # Exact address and instants, not fuzzy title matching. Reconcile with #31.
        return self.location_text, self.starts_at, self.ends_at


@dataclass
class Preview:
    events: list[Candidate] = field(default_factory=list)
    counts: Counter = field(default_factory=Counter)


def aware_datetime(value):
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("A timezone-aware date-time is required")
    return value.astimezone(timezone.utc)


def parse_feed(data, source, *, now, until=None):
    """Prepare future, timed, non-recurring events; report all skipped entries.

    No HTTP, database, geocoder or LLM use. All-day, floating, recurring and
    missing-end events are explicitly skipped pending team policy decisions.
    until is an exclusive upper bound on event start.
    """
    if source not in SOURCES:
        raise ValueError("Unsupported source")
    now = aware_datetime(now)
    until = aware_datetime(until) if until else None
    result = Preview()
    identities, duplicates = set(), set()
    calendar = Calendar.from_ical(data)
    for event in calendar.walk("VEVENT"):
        result.counts["seen"] += 1
        try:
            if event.errors:
                raise ValueError("Invalid ICS property")
            if str(event.get("STATUS", "")).upper() == "CANCELLED":
                result.counts["cancelled"] += 1
                continue
            if any(key in event for key in ("RRULE", "RDATE", "RECURRENCE-ID", "EXDATE")):
                result.counts["unsupported_recurrence"] += 1
                continue
            start = aware_datetime(event.decoded("DTSTART"))
            end = (aware_datetime(event.decoded("DTEND")) if "DTEND" in event
                   else start + event.decoded("DURATION"))
            if end <= start:
                raise ValueError("End must follow start")
            if start < now:
                result.counts["past_start"] += 1
                continue
            if until and start >= until:
                result.counts["outside_window"] += 1
                continue
            name = str(event.get("SUMMARY", "")).strip()
            location = str(event.get("LOCATION", "")).strip()
            link = str(event.get("URL", "")).strip()
            url = urlsplit(link)
            uid = str(event.get("UID", "")).strip()
            if not all((name, location, uid)) or url.scheme not in ("http", "https") or not url.hostname:
                raise ValueError("Missing required text or source URL")
            if location.casefold() in {"online", "online only", "zoom", "tbd", "tba", "to be announced"}:
                result.counts["no_physical_location"] += 1
                continue
            external_id = parse_qs(url.query).get("id", [uid])[0]
            description = str(event.get("DESCRIPTION", "")).strip()
            groups = event.get("CATEGORIES", [])
            if not isinstance(groups, list):
                groups = [groups]
            categories = [str(c) for group in groups for c in group.cats]
            category, method = classify(categories, f"{name} {description} {location}")
            if category is None:
                result.counts["not_discoverable"] += 1
                continue
            candidate = Candidate(source, external_id, name[:30], description[:150],
                                  start, end, location, link, category, method)
            if candidate.identity in identities or candidate.duplicate_key in duplicates:
                result.counts["duplicates"] += 1
                continue
            identities.add(candidate.identity)
            duplicates.add(candidate.duplicate_key)
            result.events.append(candidate)
            result.counts["prepared"] += 1
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
            result.counts["invalid_or_unsupported"] += 1
    return result
