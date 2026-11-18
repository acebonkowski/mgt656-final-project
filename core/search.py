"""
Event search (#35).

One filter form and one query function, shared by manual search and AI search
(#36): the AI's structured output is validated with the same form, so both
modes always search the same way.

All dates and times are America/New_York. All filters combine with AND, and
events that have already ended are never returned.
"""

from datetime import datetime, time, timedelta
from math import asin, cos, radians, sin, sqrt
from zoneinfo import ZoneInfo

from django import forms
from django.db import connection
from django.db.models import Case, IntegerField, Q, Value, When
from django.utils import timezone

from core.models import Event

NEW_YORK = ZoneInfo("America/New_York")
EARTH_RADIUS_MI = 3958.8
MILES_PER_DEGREE_LAT = 69.0
RADIUS_CHOICES = [("0.5", "0.5 mi"), ("1", "1 mi"), ("2", "2 mi"), ("5", "5 mi")]
DEFAULT_RADIUS_MI = 1.0
WHEN_CHOICES = [("today", "Today"), ("tomorrow", "Tomorrow"), ("weekend", "This weekend")]
SEARCH_CONFIG = "english"


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
    bbox = forms.CharField(required=False)

    def __init__(self, *args, now=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.now = now

    def clean_bbox(self):
        raw = self.cleaned_data.get("bbox")
        if not raw:
            return None
        try:
            west, south, east, north = (float(part) for part in raw.split(","))
        except ValueError:
            raise forms.ValidationError("Map area must be west,south,east,north.")
        if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
            raise forms.ValidationError("Map area is not a valid box.")
        return west, south, east, north

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

    def search(self):
        """Run the search. Call only after is_valid()."""
        return search_events(self.cleaned_data, now=self.now)


def distance_mi(lat1, lng1, lat2, lng2):
    """Great-circle (Haversine) distance in miles."""
    lat1, lng1, lat2, lng2 = map(radians, (lat1, lng1, lat2, lng2))
    a = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lng2 - lng1) / 2) ** 2
    return 2 * EARTH_RADIUS_MI * asin(sqrt(a))


def uses_full_text_search():
    return connection.vendor == "postgresql"


def _filter_text(events, q):
    name_hit = Case(When(name__icontains=q, then=Value(1)), default=Value(0),
                    output_field=IntegerField())
    substring = Q(name__icontains=q) | Q(description__icontains=q)
    if not uses_full_text_search():
        # SQLite (local development only): case-insensitive substring match.
        return events.filter(substring).annotate(name_hit=name_hit).order_by(
            "-name_hit", "start_at", "pk"
        )

    from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector

    # Must match the GIN index expression in the migration so Postgres uses it.
    vector = (SearchVector("name", weight="A", config=SEARCH_CONFIG)
              + SearchVector("description", weight="B", config=SEARCH_CONFIG))
    query = SearchQuery(q, search_type="websearch", config=SEARCH_CONFIG)
    return (
        events.annotate(document=vector, rank=SearchRank(vector, query), name_hit=name_hit)
        # Full-text match finds word forms ("concerts" -> "concert"); the
        # substring match finds half-typed words ("conc").
        .filter(Q(document=query) | substring)
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


def search_events(filters, now=None):
    """
    Return upcoming events matching every filter in `filters`
    (EventSearchForm.cleaned_data). Ordered by relevance when there is text,
    otherwise by start time.
    """
    now = now or timezone.now()
    events = Event.objects.filter(end_at__gt=now)

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

    bbox = filters.get("bbox")
    if bbox:
        west, south, east, north = bbox
        events = events.filter(latitude__gte=south, latitude__lte=north,
                               longitude__gte=west, longitude__lte=east)

    if filters.get("near_lat") is not None and filters.get("near_lng") is not None:
        events = _filter_distance(events, filters["near_lat"], filters["near_lng"],
                                  filters.get("radius_mi") or DEFAULT_RADIUS_MI)

    q = filters.get("q")
    if q:
        return _filter_text(events, q)
    return events.order_by("start_at", "pk")
