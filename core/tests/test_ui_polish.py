"""UI polish (#79): text limits, import truncation, default image, price, auth page, title case.

The CSS criteria (dropdown arrow, time row, glass) can't be rendered by the
test client, so those tests check the rules the browser relies on; the look
is checked by hand at desktop and phone widths.
"""

import importlib
import json
import re
from datetime import datetime, timedelta
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Profile
from accounts.views import SESSION_EMAIL
from core.event_import import sources
from core.event_import.ics import parse_feed
from core.forms import EventForm
from core.models import (
    DEFAULT_EVENT_IMAGE,
    EVENT_DESCRIPTION_MAX_LENGTH,
    EVENT_NAME_MAX_LENGTH,
    Event,
    fit_to_limit,
)

NEW_YORK = ZoneInfo("America/New_York")
FIXTURES = Path(__file__).parent / "fixtures"
DEFAULT_IMAGE_URL = "/static/core/img/default-event.svg"


def static_source(path):
    return Path(finders.find(path)).read_text()


def make_event(**overrides):
    start = timezone.now() + timedelta(days=1)
    values = {
        "image": "events/1/photo.jpg",
        "name": "Jazz Night",
        "description": "Live trio",
        "category": Event.Category.MUSIC_PERFORMANCE,
        "start_at": start,
        "end_at": start + timedelta(hours=2),
        "location": "Yale Commons",
        "latitude": Decimal("41.308300"),
        "longitude": Decimal("-72.927900"),
        "price": Decimal("5"),
    }
    values.update(overrides)
    return Event.objects.create(**values)


def make_user(email="student@yale.edu", onboarded=True):
    user = get_user_model().objects.create_user(username=email, email=email)
    Profile.objects.create(user=user, onboarding_complete=onboarded)
    return user


def ics_feed(summary, description="Short"):
    return ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\n"
            f"UID:test\r\nSUMMARY:{summary}\r\nDESCRIPTION:{description}\r\n"
            "LOCATION:Example Hall\r\nURL:https://example.test/event\r\n"
            "DTSTART:20261201T230000Z\r\nDTEND:20261202T000000Z\r\n"
            "END:VEVENT\r\nEND:VCALENDAR\r\n").encode()


class FitToLimitTests(SimpleTestCase):
    def test_text_that_fits_is_unchanged(self):
        self.assertEqual(fit_to_limit("Jazz Night", 50), "Jazz Night")
        self.assertEqual(fit_to_limit("x" * 50, 50), "x" * 50)  # exactly at the limit
        self.assertEqual(fit_to_limit("", 50), "")

    def test_long_text_is_exactly_the_limit_and_ends_in_dots(self):
        for limit in (EVENT_NAME_MAX_LENGTH, EVENT_DESCRIPTION_MAX_LENGTH):
            with self.subTest(limit=limit):
                result = fit_to_limit("y" * (limit + 1), limit)
                self.assertEqual(len(result), limit)
                self.assertTrue(result.endswith("..."))
                self.assertEqual(result, "y" * (limit - 3) + "...")


class ImportTruncationTests(SimpleTestCase):
    now = datetime(2026, 11, 17, tzinfo=ZoneInfo("UTC"))

    def parse(self, summary, description="Short"):
        result = parse_feed(ics_feed(summary, description), "som", now=self.now)
        self.assertEqual(len(result.events), 1, result.counts)
        return result.events[0]

    def test_long_ics_title_is_cut_to_50_with_dots(self):
        title = "Career networking evening " + "with alumni " * 5
        event = self.parse(title)
        self.assertEqual(len(event.name), 50)
        self.assertEqual(event.name, title[:47] + "...")

    def test_long_ics_description_is_cut_to_300_with_dots(self):
        event = self.parse("Talk", "z" * 450)
        self.assertEqual(len(event.description), 300)
        self.assertEqual(event.description, "z" * 297 + "...")

    def test_text_that_fits_is_stored_unchanged(self):
        title, description = "n" * 50, "d" * 300
        event = self.parse(title, description)
        self.assertEqual(event.name, title)
        self.assertEqual(event.description, description)
        self.assertNotIn("...", event.name + event.description)

    def test_ticketmaster_title_and_description_use_the_same_rule(self):
        data = json.loads((FIXTURES / "ticketmaster.json").read_text())
        raw = data["_embedded"]["events"][0]
        raw["name"] = "A" * 60
        raw["info"] = "B" * 400
        result = sources.parse_ticketmaster(data, now=datetime(2026, 11, 17, tzinfo=ZoneInfo("UTC")),
                                            until=datetime(2027, 1, 1, tzinfo=ZoneInfo("UTC")))
        event = result.events[0]
        self.assertEqual(event.name, "A" * 47 + "...")
        self.assertEqual(event.description, "B" * 297 + "...")


class EventFormLimitTests(SimpleTestCase):
    def test_inputs_cap_at_50_and_300(self):
        form = EventForm()
        self.assertIn('maxlength="50"', str(form["name"]))
        self.assertIn('maxlength="300"', str(form["description"]))

    def test_longer_title_or_description_is_rejected(self):
        for field, value in (("name", "n" * 51), ("description", "d" * 301)):
            with self.subTest(field=field):
                form = EventForm(data={field: value})
                form.is_valid()
                self.assertIn(field, form.errors)
                self.assertIn("at most", form.errors[field][0])

    def test_limits_themselves_are_accepted(self):
        form = EventForm(data={"name": "n" * 50, "description": "d" * 300})
        form.is_valid()
        self.assertNotIn("name", form.errors)
        self.assertNotIn("description", form.errors)


class PriceLabelTests(SimpleTestCase):
    def test_number_or_free_never_not_listed(self):
        cases = {None: "Free", Decimal("0"): "Free", Decimal("5"): "$5.00", Decimal("12.5"): "$12.50"}
        for price, label in cases.items():
            with self.subTest(price=price):
                self.assertEqual(Event(price=price).price_label, label)


class DefaultImageTests(TestCase):
    def setUp(self):
        self.client.force_login(make_user())

    def test_image_url_falls_back_to_the_bulldog(self):
        self.assertTrue(finders.find("core/img/default-event.svg"))
        for image in ("", DEFAULT_EVENT_IMAGE):
            with self.subTest(image=image):
                self.assertEqual(Event(image=image).image_url, DEFAULT_IMAGE_URL)
        self.assertEqual(Event(image="events/1/a.jpg").image_url, "/event-photo/events/1/a.jpg")

    def test_detail_page_and_popup_show_the_default_image(self):
        event = make_event(image=DEFAULT_EVENT_IMAGE)
        for url in (f"/events/{event.pk}/", f"/events/{event.pk}/popup/"):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertContains(response, f'class="event-detail-image" src="{DEFAULT_IMAGE_URL}"')
                self.assertNotContains(response, "Image unavailable")

    def test_side_panel_results_use_the_default_image(self):
        make_event(image="")
        event = self.client.get("/events/search/").json()["events"][0]
        self.assertEqual(event["image_url"], DEFAULT_IMAGE_URL)
        self.assertContains(self.client.get("/map/"), f'data-default-image="{DEFAULT_IMAGE_URL}"')
        self.assertNotIn("charAt(0).toUpperCase()", static_source("core/search.js"))

    def test_default_marker_is_not_served_as_a_stored_photo(self):
        make_event(image=DEFAULT_EVENT_IMAGE)
        self.assertEqual(self.client.get(f"/event-photo/{DEFAULT_EVENT_IMAGE}").status_code, 404)


class DefaultImageBackfillTests(TestCase):
    migration = importlib.import_module("core.migrations.0009_event_text_limits_default_image")

    def test_backfill_sets_default_only_where_image_is_missing(self):
        missing = [make_event(image="", location=f"Hall {n}") for n in range(3)]
        pictured = make_event(image="events/1/own.jpg", location="Other Hall")
        self.migration.backfill_default_image(django_apps, None)
        for event in missing:
            event.refresh_from_db()
            self.assertEqual(event.image, DEFAULT_EVENT_IMAGE)
        pictured.refresh_from_db()
        self.assertEqual(pictured.image, "events/1/own.jpg")
        self.assertFalse(Event.objects.filter(image="").exists())

    def test_backfill_is_safe_to_run_again(self):
        make_event(image="")
        self.migration.backfill_default_image(django_apps, None)
        self.migration.backfill_default_image(django_apps, None)
        self.assertEqual(Event.objects.get().image, DEFAULT_EVENT_IMAGE)

    def test_migration_uses_the_model_marker(self):
        self.assertEqual(self.migration.DEFAULT_EVENT_IMAGE, DEFAULT_EVENT_IMAGE)


class LoginPageTests(TestCase):
    def test_no_environment_line_or_email_hint(self):
        response = self.client.get("/login/")
        self.assertNotContains(response, "Environment:")
        self.assertNotContains(response, "Only yale.edu addresses are accepted.")
        self.assertNotContains(response, "email-hint")

    def test_non_yale_email_is_still_rejected_with_an_error(self):
        response = self.client.post("/login/", {"email": "someone@gmail.com"})
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, 'role="alert"', status_code=400)
        self.assertContains(response, 'aria-describedby="email-error"', status_code=400)
        self.assertContains(response, "Only yale.edu email addresses are accepted.", status_code=400)

    def test_auth_box_is_dark_glass(self):
        css = static_source("accounts/auth.css")
        glass = css.split("@supports", 1)[1]
        self.assertIn("backdrop-filter: blur(", glass)
        self.assertIn("-webkit-backdrop-filter: blur(", glass)
        self.assertRegex(glass, r"\.auth-card \{\s*background: rgba\(18, 27, 46, 0\.\d+\)")


class LayoutCssTests(SimpleTestCase):
    def test_category_dropdown_arrow_sits_inside_the_padding(self):
        for path, selector in (("core/map.css", ".event-fields select"),
                               ("core/search.css", ".search-panel select {")):
            with self.subTest(path=path):
                css = static_source(path)
                rule = css[css.rindex(selector):]
                rule = rule[:rule.index("}")]
                self.assertIn("appearance: none;", rule)
                self.assertIn("padding-right: 2.25rem;", rule)
                self.assertIn("background-position: right 0.75rem center;", rule)

    def test_start_and_end_time_fill_their_columns(self):
        css = static_source("core/map.css")
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr));", css)
        rule = css[css.rindex(".event-fields .time12 {"):]
        self.assertIn("width: 100%;", rule[:rule.index("}")])
        self.assertIn("flex-wrap: nowrap;", rule[:rule.index("}")])
        inputs = css[css.rindex(".event-fields .time12 input.time12-minute {"):]
        self.assertIn("flex: 1 1 0;", inputs[:inputs.index("}")])

    def test_side_panel_is_dark_glass_collapsed_and_expanded(self):
        css = static_source("core/search.css")
        glass = css[css.rindex("@supports"):]
        self.assertIn("background: var(--search-panel-glass);", glass)
        self.assertIn("backdrop-filter: blur(", glass)
        self.assertIn("-webkit-backdrop-filter: blur(", glass)
        self.assertIn("--search-panel-glass: rgba(11, 18, 32, 0.8)", css)
        # The collapsed state only moves the panel; it sets no background of its own.
        collapsed = css[css.index(".search-collapsed .search-panel {"):]
        self.assertNotIn("background", collapsed[:collapsed.index("}")])


# APA title case: capitalize the first and last word, words of four or more
# letters and all major words; lowercase short conjunctions, articles and
# prepositions (three letters or fewer) in between.
MINOR_WORDS = {"a", "an", "the", "and", "but", "or", "nor", "for", "so", "yet",
               "as", "at", "by", "in", "of", "off", "on", "per", "to", "up", "via"}


def apa_violations(text):
    # Words only: icons and punctuation around them (e.g. "📎Attach") are ignored.
    words = re.findall(r"[^\W\d_][\w'’]*(?:-[\w'’]+)*", text)
    problems = []
    for index, word in enumerate(words):
        edge = index in (0, len(words) - 1)
        for part in word.split("-"):
            if part and part[0].islower() and (edge or part not in MINOR_WORDS):
                problems.append(part)
    return problems


class UiTextCollector(HTMLParser):
    """Text of headings, labels and buttons, plus button aria-label and title."""

    TAGS = {"h1", "h2", "h3", "h4", "h5", "h6", "label", "button", "legend"}

    def __init__(self):
        super().__init__()
        self.stack = []
        self.found = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in self.TAGS:
            self.stack.append([tag, attrs, ""])
            if tag == "button":
                for name in ("aria-label", "title"):
                    if attrs.get(name):
                        self.found.append((f"button[{name}]", attrs[name], attrs))

    def handle_endtag(self, tag):
        if self.stack and self.stack[-1][0] == tag:
            tag, attrs, text = self.stack.pop()
            text = " ".join(text.split())
            if text:
                self.found.append((tag, text, attrs))

    def handle_data(self, data):
        if self.stack:
            self.stack[-1][2] += data


class TitleCaseTests(TestCase):
    def assert_title_case(self, html, page):
        collector = UiTextCollector()
        collector.feed(html)
        self.assertTrue(collector.found, page)
        for tag, text, attrs in collector.found:
            if attrs.get("id") == "abtest":
                continue  # the brief requires exactly "kudos" or "thanks"
            with self.subTest(page=page, tag=tag, text=text):
                self.assertEqual(apa_violations(text), [], f"{tag}: {text!r} on {page}")

    def test_checker_follows_apa(self):
        self.assertEqual(apa_violations("Return to Map"), [])
        self.assertEqual(apa_violations("Search With AI"), [])
        self.assertEqual(apa_violations("Return to map"), ["map"])
        self.assertEqual(apa_violations("Search with AI"), ["with"])
        self.assertEqual(apa_violations("Turn Spoken Replies on"), ["on"])

    def test_logged_out_pages(self):
        self.assert_title_case(self.client.get("/login/").content.decode(), "/login/")
        session = self.client.session
        session[SESSION_EMAIL] = "student@yale.edu"
        session.save()
        self.assert_title_case(self.client.get("/login/code/").content.decode(), "/login/code/")
        event = make_event()
        self.assert_title_case(self.client.get(f"/events/{event.pk}/").content.decode(), "event page")
        self.assert_title_case(self.client.get(reverse("abtest:page")).content.decode(), "A/B page")

    def test_logged_in_pages(self):
        user = make_user()
        self.client.force_login(user)
        event = make_event(creator=user)
        for url in ("/map/", f"/events/{event.pk}/", f"/events/{event.pk}/popup/",
                    f"/events/{event.pk}/edit/"):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assert_title_case(response.content.decode(), url)

    def test_onboarding_page(self):
        self.client.force_login(make_user(onboarded=False))
        response = self.client.get("/onboarding/")
        self.assertEqual(response.status_code, 200)
        self.assert_title_case(response.content.decode(), "/onboarding/")

    def test_js_rendered_labels(self):
        # Button and heading text set from JavaScript (status messages are sentences).
        source = static_source("core/search.js")
        for text in ("Search Events", "Search This Area", "Edit in Filters", "Remove Filter",
                     "Turn Spoken Replies On", "Mute Spoken Replies"):
            with self.subTest(text=text):
                self.assertEqual(apa_violations(text), [])
                self.assertIn(f'"{text}', source)
        for old in ('"Search events"', '"Search this area', '"Edit in filters"', '"Remove filter',
                    '"Turn spoken replies on"', '"Mute spoken replies"'):
            self.assertNotIn(old, source)
        self.assertIn('"Turn Spoken Replies On" : "Mute Spoken Replies"', source)
        self.assertIn("'Edit Picture' : 'Add a Picture'", static_source("core/onboarding.js"))
