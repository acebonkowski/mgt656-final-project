"""
Event search (#35).

One filter form and one query function, shared by manual search and AI search
(#36): the AI's structured output is validated with the same form, so both
modes always search the same way.

All dates and times are America/New_York. All filters combine with AND, and
events that have already ended are never returned.
"""

import re
from datetime import datetime, time, timedelta
from math import asin, cos, radians, sin, sqrt
from zoneinfo import ZoneInfo

from django import forms
from django.db import connection
from django.db.models import Case, IntegerField, Q, Value, When
from django.utils import timezone

from core.attendance import exclude_not_going
from core.models import Event
from core.friends import with_friends_going
from core.visibility import visible_events

NEW_YORK = ZoneInfo("America/New_York")
EARTH_RADIUS_MI = 3958.8
MILES_PER_DEGREE_LAT = 69.0
RADIUS_CHOICES = [("0.5", "0.5 mi"), ("1", "1 mi"), ("2", "2 mi"), ("5", "5 mi")]
DEFAULT_RADIUS_MI = 1.0
# "Search this area": a circle around the map centre, sized by the zoom level.
AREA_MIN_RADIUS_MI = 0.1
AREA_MAX_RADIUS_MI = 10.0
WHEN_CHOICES = [("today", "Today"), ("tomorrow", "Tomorrow"), ("weekend", "This weekend")]
SEARCH_CONFIG = "english"
WORD_RE = re.compile(r"[^\W_]+")


def quick_pick_dates(when, today):
    """Return (date_from, date_to) for a quick pick, relative to `today`."""
    if when == "today":
        return today, today
    if when == "tomorrow":
        day = today + timedelta(days=1)
        return day, day
    if when == "weekend":
        # Saturday is weekday 5, Sunday is 6.
        if today.weekday() == 6:
            return today, today
        saturday = today + timedelta(days=(5 - today.weekday()) % 7)
        return saturday, saturday + timedelta(days=1)
    raise ValueError(f"Unknown quick pick: {when}")


def new_york_today(now=None):
    return (now or timezone.now()).astimezone(NEW_YORK).date()


class EventSearchForm(forms.Form):
    """Validates search query parameters (manual search) or AI filters (#36)."""

    q = forms.CharField(required=False, max_length=200, strip=True)
    category = forms.MultipleChoiceField(choices=Event.Category.choices, required=False)
    when = forms.ChoiceField(choices=WHEN_CHOICES, required=False)
    date_from = forms.DateField(required=False, input_formats=["%Y-%m-%d"])
    date_to = forms.DateField(required=False, input_formats=["%Y-%m-%d"])
    time_from = forms.TimeField(required=False, input_formats=["%H:%M"])
    time_to = forms.TimeField(required=False, input_formats=["%H:%M"])
    near_lat = forms.FloatField(required=False, min_value=-90, max_value=90)
    near_lng = forms.FloatField(required=False, min_value=-180, max_value=180)
    radius_mi = forms.TypedChoiceField(
        choices=RADIUS_CHOICES, coerce=float, required=False, empty_value=None
    )
    area = forms.CharField(required=False)  # "lat,lng,radius_mi" from Search this area
    # Off by default: events the user marked "Not going" are hidden (#84).
    include_not_going = forms.BooleanField(required=False)

    def __init__(self, *args, now=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.now = now

    def clean_area(self):
        raw = self.cleaned_data.get("area")
        if not raw:
            return None
        try:
            lat, lng, radius = (float(part) for part in raw.split(","))
        except ValueError:
            raise forms.ValidationError("Map area must be latitude,longitude,radius.")
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            raise forms.ValidationError("Map area centre is not a valid location.")
        if not AREA_MIN_RADIUS_MI <= radius <= AREA_MAX_RADIUS_MI:
            raise forms.ValidationError(
                f"Map area radius must be {AREA_MIN_RADIUS_MI:g}–{AREA_MAX_RADIUS_MI:g} mi."
            )
        return lat, lng, radius

    def clean(self):
        data = super().clean()

        when = data.get("when")
        if when:
            data["date_from"], data["date_to"] = quick_pick_dates(when, new_york_today(self.now))
        date_from, date_to = data.get("date_from"), data.get("date_to")
        if date_from and not date_to:
            data["date_to"] = date_from
        elif date_to and not date_from:
            data["date_from"] = date_to
        elif date_from and date_to and date_to < date_from:
            self.add_error("date_to", "End date can't be before the start date.")

        time_from, time_to = data.get("time_from"), data.get("time_to")
        if time_from and time_to and time_to <= time_from:
            self.add_error("time_to", "End time must be after the start time.")

        has_lat = data.get("near_lat") is not None
        has_lng = data.get("near_lng") is not None
        if has_lat != has_lng:
            self.add_error("near_lat", "Location needs both latitude and longitude.")
        if has_lat and has_lng and data.get("radius_mi") is None:
            data["radius_mi"] = DEFAULT_RADIUS_MI
        return data

    def search(self, user=None):
        """Run the search. Call only after is_valid(). `user` hides their "Not going" events."""
        return search_events(self.cleaned_data, now=self.now, user=user)


def distance_mi(lat1, lng1, lat2, lng2):
    """Great-circle (Haversine) distance in miles."""
    lat1, lng1, lat2, lng2 = map(radians, (lat1, lng1, lat2, lng2))
    a = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lng2 - lng1) / 2) ** 2
    return 2 * EARTH_RADIUS_MI * asin(sqrt(a))


def uses_full_text_search():
    return connection.vendor == "postgresql"


def full_text_vector():
    """Weighted document; must match the GIN index in migration 0004."""
    from django.contrib.postgres.search import SearchVector

    return (SearchVector("name", weight="A", config=SEARCH_CONFIG)
            + SearchVector("description", weight="B", config=SEARCH_CONFIG))


def full_text_query(words):
    """
    Every word must match as a prefix of a stemmed word: "concerts" finds
    "concert" (stemming) and "conc" finds "Concert" (prefix). Only letters and
    digits reach the raw query, so user input can't break its syntax.
    """
    from django.contrib.postgres.search import SearchQuery

    return SearchQuery(" & ".join(f"{word}:*" for word in words),
                       search_type="raw", config=SEARCH_CONFIG)


def _all_words_in(field, words):
    condition = Q()
    for word in words:
        condition &= Q(**{f"{field}__icontains": word})
    return condition


def _filter_text(events, q):
    words = WORD_RE.findall(q)
    if not words:
        return events.none()
    name_hit = Case(When(_all_words_in("name", words), then=Value(1)), default=Value(0),
                    output_field=IntegerField())

    if not uses_full_text_search():
        # SQLite (local development only): every word as a case-insensitive
        # substring of the name or the description.
        condition = Q()
        for word in words:
            condition &= Q(name__icontains=word) | Q(description__icontains=word)
        return events.filter(condition).annotate(name_hit=name_hit).order_by(
            "-name_hit", "start_at", "pk"
        )

    from django.contrib.postgres.search import SearchRank

    vector, query = full_text_vector(), full_text_query(words)
    return (
        events.annotate(document=vector, rank=SearchRank(vector, query), name_hit=name_hit)
        .filter(document=query)
        .order_by("-rank", "-name_hit", "start_at", "pk")
    )


def _filter_distance(events, lat, lng, radius_mi):
    # Cheap bounding box in the database, then the exact distance in Python.
    lat_delta = radius_mi / MILES_PER_DEGREE_LAT
    lng_delta = radius_mi / (MILES_PER_DEGREE_LAT * max(cos(radians(lat)), 0.01))
    candidates = events.filter(
        latitude__gte=lat - lat_delta, latitude__lte=lat + lat_delta,
        longitude__gte=lng - lng_delta, longitude__lte=lng + lng_delta,
    ).values_list("pk", "latitude", "longitude")
    within = [
        pk for pk, ev_lat, ev_lng in candidates
        if distance_mi(lat, lng, float(ev_lat), float(ev_lng)) <= radius_mi
    ]
    return events.filter(pk__in=within)


def search_events(filters, now=None, user=None, queryset=None):
    """
    Return upcoming events matching every filter in `filters`
    (EventSearchForm.cleaned_data). Ordered by relevance when there is text,
    otherwise by start time. Events `user` marked "Not going" are left out unless
    filters["include_not_going"] is set (#84). An optional queryset restricts
    the search to an existing collection, such as the user's favorites.
    """
    now = now or timezone.now()
    events = (Event.objects.all() if queryset is None else queryset).filter(end_at__gt=now)
    events = visible_events(events, user)  # hidden events never appear (#41)
    events = with_friends_going(events, user)  # person icon on the pin (#85)
    if not filters.get("include_not_going"):
        events = exclude_not_going(events, user)

    if filters.get("category"):
        events = events.filter(category__in=filters["category"])

    date_from, date_to = filters.get("date_from"), filters.get("date_to")
    if date_from and date_to:
        # Overlap: starts before the range ends and ends after it starts.
        range_start = datetime.combine(date_from, time.min, tzinfo=NEW_YORK)
        range_end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=NEW_YORK)
        events = events.filter(start_at__lt=range_end, end_at__gt=range_start)

    # Start time of day, in the current time zone (TIME_ZONE = America/New_York).
    if filters.get("time_from"):
        events = events.filter(start_at__time__gte=filters["time_from"])
    if filters.get("time_to"):
        events = events.filter(start_at__time__lte=filters["time_to"])

    if filters.get("area"):
        area_lat, area_lng, area_radius = filters["area"]
        events = _filter_distance(events, area_lat, area_lng, area_radius)

    if filters.get("near_lat") is not None and filters.get("near_lng") is not None:
        events = _filter_distance(events, filters["near_lat"], filters["near_lng"],
                                  filters.get("radius_mi") or DEFAULT_RADIUS_MI)

    q = filters.get("q")
    if q:
        return _filter_text(events, q)
    return events.order_by("start_at", "pk")
