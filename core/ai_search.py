"""
AI search (#36): turn a student's message into the same filters as manual
search (#35), then run the normal search.

The model only proposes filters and writes a short reply. Every filter is
validated with EventSearchForm (invalid ones are dropped) and the events always
come from search_events(), so the AI can never add events that aren't in the
database.
"""

import base64
import json
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone

from core import geocoding, llm
from core.models import Event
from core.search import RADIUS_CHOICES, WHEN_CHOICES, EventSearchForm

NEW_YORK = ZoneInfo("America/New_York")
HISTORY_SESSION_KEY = "ai_search_history"
MAX_MESSAGE_CHARS = 300
MAX_HISTORY_MESSAGES = 12  # the last 6 turns (student + AI)
MAX_REPLY_CHARS = 500
DEFAULT_REPLY = "Here's what I found."
DEFAULT_IMAGE_MESSAGE = "Find events like the one in this image."

RADIUS_VALUES = [value for value, _ in RADIUS_CHOICES]
WHEN_VALUES = [value for value, _ in WHEN_CHOICES]
NULLABLE_STRING = {"type": ["string", "null"]}

# Strict JSON schema: every key is required, unused filters are null.
RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["reply", "filters"],
    "properties": {
        "reply": {"type": "string"},
        "filters": {
            "type": "object",
            "additionalProperties": False,
            "required": ["q", "categories", "when", "date_from", "date_to",
                         "time_from", "time_to", "near_address", "radius_mi"],
            "properties": {
                "q": NULLABLE_STRING,
                "categories": {
                    "type": "array",
                    "items": {"type": "string", "enum": list(Event.Category.values)},
                },
                "when": {"type": ["string", "null"], "enum": WHEN_VALUES + [None]},
                "date_from": NULLABLE_STRING,
                "date_to": NULLABLE_STRING,
                "time_from": NULLABLE_STRING,
                "time_to": NULLABLE_STRING,
                "near_address": NULLABLE_STRING,
                "radius_mi": {"type": ["string", "null"], "enum": RADIUS_VALUES + [None]},
            },
        },
    },
}


def system_prompt(now):
    local = now.astimezone(NEW_YORK)
    categories = "\n".join(f"  - {value}: {label}" for value, label in Event.Category.choices)
    return (
        "You help Yale students find events in New Haven by turning their request into "
        "search filters for the app's event database.\n"
        f"Today is {local:%A}, {local:%B} {local.day}, {local.year}, and the time in New Haven "
        f"(America/New_York) is {local:%H:%M}.\n"
        "Rules:\n"
        "- Fill only the filters the student asked for. Set every other filter to null "
        "(categories to an empty list).\n"
        "- q: a few keywords to match event names and descriptions. Don't repeat dates, "
        "places or categories that other filters already cover.\n"
        f"- categories: zero or more of these values:\n{categories}\n"
        '- when: "today", "tomorrow" or "weekend" for exactly those requests, otherwise null.\n'
        "- date_from and date_to: YYYY-MM-DD for other days or ranges. For a single day, "
        "set date_from only.\n"
        "- time_from and time_to: a start-time window as HH:MM (24-hour). For example, "
        '"evening" is 17:00 to 23:59 and "morning" is 06:00 to 11:59.\n'
        "- near_address: a place in New Haven if the student named one, with radius_mi "
        '"0.5", "1", "2" or "5" (use "1" if they didn\'t say).\n'
        "- reply: one or two friendly sentences saying what you searched for. Never name, "
        "list or invent specific events: the app shows the real results.\n"
        "- If an image is attached (for example a poster or flyer), read what it shows: the "
        "kind of event, keywords, date, time and place. Use those for the filters, and say in "
        "the reply what you read from it.\n"
        "- If the request isn't about finding events, set all filters to null and say "
        "briefly that you can only help find events.\n"
        "- Later messages may refine the previous search (for example \"what about "
        'Sunday?"). Keep the earlier filters unless the student changes them.'
    )


def _text(value, limit):
    return value.strip()[:limit] if isinstance(value, str) and value.strip() else ""


def to_form_data(filters, geocode=None):
    """
    Map the model's filters to EventSearchForm data (query-parameter shape).
    Returns (data, notes); notes explain anything the app couldn't use.
    """
    geocode = geocode or geocoding.search
    filters = filters if isinstance(filters, dict) else {}
    data, notes = {}, []

    for key, limit in (("q", 200), ("date_from", 10), ("date_to", 10),
                       ("time_from", 5), ("time_to", 5)):
        value = _text(filters.get(key), limit)
        if value:
            data[key] = value
    categories = filters.get("categories")
    if isinstance(categories, list):
        valid = [c for c in categories if c in Event.Category.values]
        if valid:
            data["category"] = list(dict.fromkeys(valid))
    if filters.get("when") in WHEN_VALUES:
        data["when"] = filters["when"]

    place = _text(filters.get("near_address"), 200)
    if place:
        try:
            matches = geocode(place)
        except geocoding.GeocodingUnavailable:
            matches = []
        if matches:
            data["near_lat"] = str(matches[0]["latitude"])
            data["near_lng"] = str(matches[0]["longitude"])
            data["near_label"] = matches[0].get("address") or place
            if filters.get("radius_mi") in RADIUS_VALUES:
                data["radius_mi"] = filters["radius_mi"]
        else:
            notes.append(f"I couldn't look up “{place}”, so I didn't filter by location.")
    return data, notes


# A filter the form rejects is dropped together with the fields it depends on.
RELATED_FIELDS = {
    "near_lat": ("near_lat", "near_lng", "near_label", "radius_mi"),
    "near_lng": ("near_lat", "near_lng", "near_label", "radius_mi"),
    "radius_mi": ("radius_mi",),
    "date_to": ("date_to",),
}


def validated_form(data, now):
    """Return a valid EventSearchForm, dropping whatever the form rejects."""
    data = dict(data)
    for _ in range(5):
        form = EventSearchForm(data, now=now)
        if form.is_valid():
            return form, data
        for field in form.errors:
            for key in RELATED_FIELDS.get(field, (field,)):
                data.pop(key, None)
            if field == "category":
                data.pop("category", None)
    form = EventSearchForm({}, now=now)
    form.is_valid()
    return form, {}


def search(message, history, now=None, geocode=None, image=None, user=None):
    """
    Ask the model for filters, validate them and search.
    `image` is an optional (bytes, content_type) pair, already validated and
    converted in memory; it is sent to the model and never stored.
    Returns a dict with reply, filters (query-parameter shape), notes, events
    and the two history entries to append. Raises llm.LLMUnavailable.
    """
    now = now or timezone.now()
    message = message or (DEFAULT_IMAGE_MESSAGE if image else "")
    messages = [{"role": "system", "content": system_prompt(now)}]
    messages += history[-MAX_HISTORY_MESSAGES:]
    if image:
        data, content_type = image
        url = f"data:{content_type};base64,{base64.b64encode(data).decode('ascii')}"
        messages.append({"role": "user", "content": [
            {"type": "text", "text": message},
            {"type": "image_url", "image_url": {"url": url}},
        ]})
    else:
        messages.append({"role": "user", "content": message})

    output = llm.chat_json(messages, "event_search", RESPONSE_SCHEMA,
                           model=settings.OPENROUTER_SEARCH_MODEL or None)
    reply = _text(output.get("reply"), MAX_REPLY_CHARS) or DEFAULT_REPLY
    raw_filters = output.get("filters") if isinstance(output.get("filters"), dict) else {}

    data, notes = to_form_data(raw_filters, geocode=geocode)
    form, data = validated_form(data, now)
    return {
        "reply": reply,
        "filters": data,
        "notes": notes,
        # Never "Not going" events (#84): the model cannot set include_not_going.
        "events": list(form.search(user=user)),
        "history": [
            # Only the text is remembered; the image is never stored, even in the session.
            {"role": "user", "content": f"[Image attached] {message}" if image else message},
            # The model sees its earlier filters, so follow-ups can refine them.
            {"role": "assistant", "content": json.dumps({"reply": reply, "filters": raw_filters})},
        ],
    }
