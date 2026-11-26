"""
Recurring searches (#37): save a search, and each day look for new matches.

The AI is used once, in the chat, to turn the student's words into filters. The
daily run only re-runs the stored filters through search_events(), so it costs
no AI credits and honours the same rules as the map: events the user marked
"Not going" (#84) and, once #91 lands, events the user cannot see (#41) never
come back.
"""

import json
import logging
from collections import Counter

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from core import ai_search
from core.models import Event, SavedSearch, SearchSuggestion
from core.search import EventSearchForm

logger = logging.getLogger(__name__)

MAX_SEARCHES_PER_USER = 10
MAX_SUGGESTIONS_PER_RUN = 10  # new suggestions per saved search per run
MAX_LABEL_CHARS = 200
DEFAULT_LABEL = "Saved search"

# Filters a saved search may keep (the rest of the browser's data is dropped).
FILTER_KEYS = ("q", "category", "when", "date_from", "date_to", "time_from", "time_to",
               "near_lat", "near_lng", "near_label", "radius_mi")
# A search needs at least one of these, or it would suggest every event.
MEANINGFUL_KEYS = ("q", "category", "when", "date_from", "date_to", "time_from", "time_to",
                   "near_lat")


class SavedSearchError(Exception):
    """The message is safe to show to the user."""


def newest_event_id():
    return Event.objects.aggregate(top=Max("pk"))["top"] or 0


def clean_filters(raw, now=None):
    """
    Validate filters sent by the browser with the same form as search. Invalid
    filters are dropped. Raises SavedSearchError if nothing useful is left.
    """
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = None
    if not isinstance(raw, dict):
        raise SavedSearchError("That search couldn't be saved. Try asking again.")
    data = {}
    for key in FILTER_KEYS:
        value = raw.get(key)
        if value in (None, "", []):
            continue
        data[key] = value if key == "category" else str(value)
    _, data = ai_search.validated_form(data, now or timezone.now())
    data = {key: value for key, value in data.items() if key in FILTER_KEYS}
    if not any(data.get(key) for key in MEANINGFUL_KEYS):
        raise SavedSearchError("Add at least one filter before saving a search.")
    return data


def clean_label(label, filters):
    label = " ".join((label or "").split())[:MAX_LABEL_CHARS]
    return label or (filters.get("q") or DEFAULT_LABEL)[:MAX_LABEL_CHARS]


def save_search(user, raw_filters, label="", now=None):
    """Save a search. Returns (saved_search, created). Saving the same filters twice is a no-op."""
    filters = clean_filters(raw_filters, now)
    for existing in SavedSearch.objects.filter(user=user):
        if existing.filters == filters:
            return existing, False
    if SavedSearch.objects.filter(user=user).count() >= MAX_SEARCHES_PER_USER:
        raise SavedSearchError(
            f"You can keep up to {MAX_SEARCHES_PER_USER} saved searches. Delete one first."
        )
    saved = SavedSearch.objects.create(
        user=user, label=clean_label(label, filters), filters=filters,
        last_seen_event_id=newest_event_id(),
    )
    return saved, True


@transaction.atomic
def update_search(saved, raw_filters, label="", now=None):
    """
    Replace a saved search's filters. The old suggestions no longer match the
    search, so they are removed (hidden ones stay hidden), and only events added
    from now on count as new.
    """
    filters = clean_filters(raw_filters, now)
    saved.filters = filters
    if label:
        saved.label = clean_label(label, filters)
    saved.last_seen_event_id = newest_event_id()
    saved.save()
    saved.suggestions.filter(hidden=False).delete()
    return saved


@transaction.atomic
def delete_search(saved):
    """Delete a saved search and the suggestions it made. Hidden ones are kept so they stay hidden."""
    saved.suggestions.filter(hidden=False).delete()
    saved.delete()


def scan_search(saved, now=None):
    """
    Add suggestions for events created since the last scan that match `saved`.
    Skips events the owner hosts or has answered, ended events and anything
    search_events() hides from them. Returns the number of suggestions added.
    """
    now = now or timezone.now()
    newest = newest_event_id()  # read first: events added during the scan wait for tomorrow
    form = EventSearchForm(saved.filters, now=now)
    if not form.is_valid():
        logger.warning("saved_search invalid_filters id=%s fields=%s", saved.pk, sorted(form.errors))
        return 0
    owner = saved.user
    candidates = (
        form.search(user=owner)
        .filter(pk__gt=saved.last_seen_event_id, pk__lte=newest)
        .exclude(creator=owner)
        .exclude(attendances__user=owner)
        .exclude(search_suggestions__user=owner)
    )
    events = list(candidates[:MAX_SUGGESTIONS_PER_RUN])
    with transaction.atomic():
        SearchSuggestion.objects.bulk_create(
            [SearchSuggestion(user=owner, event=event, search=saved) for event in events],
            ignore_conflicts=True,
        )
        saved.last_seen_event_id = max(saved.last_seen_event_id, newest)
        saved.save(update_fields=["last_seen_event_id", "updated_at"])
    return len(events)


def run_saved_searches(now=None):
    """Scan every saved search. One failing search never stops the others."""
    now = now or timezone.now()
    counts = Counter()
    logger.info("saved_searches start")
    for saved in SavedSearch.objects.select_related("user").order_by("pk"):
        counts["searches"] += 1
        try:
            counts["suggested"] += scan_search(saved, now=now)
        except Exception as exc:
            counts["failed"] += 1
            logger.warning("saved_search failed id=%s type=%s", saved.pk, type(exc).__name__)
    for name in ("searches", "suggested", "failed"):
        counts.setdefault(name, 0)
    logger.info("saved_searches end counts=%s", dict(counts))
    return counts
