"""Shareable event page (#32): field order, Free, share, logged-out view, .ics, 404.

The share button's JavaScript can't run in Django's test client, so these tests
check the markup it relies on; the click behaviour is checked by hand.
"""

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.test import TestCase
from icalendar import Calendar

from accounts.models import Profile
from core.models import Event

NEW_YORK = ZoneInfo("America/New_York")


def make_event(**overrides):
    values = {
        "image": "events/1/page.jpg",
        "name": "Jazz Night",
        "description": "Live trio, bring friends",
        "category": Event.Category.MUSIC_PERFORMANCE,
        "start_at": datetime(2026, 11, 20, 19, 0, tzinfo=NEW_YORK),
        "end_at": datetime(2026, 11, 20, 21, 0, tzinfo=NEW_YORK),
        "location": "Yale Commons, 168 Grove St",
        "latitude": Decimal("41.311100"),
        "longitude": Decimal("-72.925300"),
        "price": Decimal("0"),
        "link": "https://example.com/jazz",
    }
    values.update(overrides)
    return Event.objects.create(**values)


def make_user(email="student@yale.edu"):
    user = get_user_model().objects.create_user(username=email, email=email)
    Profile.objects.create(user=user, onboarding_complete=True)
    return user


class EventPageLoggedInTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client.force_login(self.user)
        self.event = make_event()
        self.url = f"/events/{self.event.pk}/"

    def test_fields_appear_in_the_issue_order(self):
        html = self.client.get(self.url).content.decode()
        markers = [
            'class="event-detail-image"',
            'id="event-detail-title"',
            'class="event-description"',
            'data-field="category"',
            'data-field="datetime"',
            'data-field="location"',
            'data-field="price"',
            'data-field="link"',
        ]
        positions = [html.index(marker) for marker in markers]
        self.assertEqual(positions, sorted(positions))

    def test_values_are_shown_with_new_york_date_and_time(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Jazz Night")
        self.assertContains(response, "Live trio, bring friends")
        self.assertContains(response, "Music &amp; Performance")
        self.assertContains(response, "Fri, Nov 20, 2026 · 7:00 PM")
        self.assertContains(response, "9:00 PM")
        self.assertContains(response, "Yale Commons, 168 Grove St")

    def test_price_zero_reads_free(self):
        response = self.client.get(self.url)
        self.assertContains(response, '<dd data-field="price">Free</dd>', html=False)

    def test_paid_price_shows_dollars(self):
        paid = make_event(price=Decimal("12.5"), location="Elsewhere")
        response = self.client.get(f"/events/{paid.pk}/")
        self.assertContains(response, '<dd data-field="price">$12.50</dd>', html=False)
        self.assertNotContains(response, ">Free<")

    def test_link_opens_in_new_tab_with_noopener(self):
        self.assertContains(
            self.client.get(self.url),
            '<a href="https://example.com/jazz" target="_blank" rel="noopener">',
        )

    def test_share_button_carries_the_public_url_and_confirmation_area(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'id="share-event"')
        self.assertContains(response, f'data-share-url="http://testserver{self.url}"')
        self.assertContains(response, 'id="share-status" class="event-share-status" role="status"')
        self.assertContains(response, "core/event.js")

    def test_logged_in_user_gets_back_to_map_and_no_join_cta(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'href="/map/"')
        self.assertNotContains(response, "Join to discover more")

    def test_save_to_calendar_button_links_to_ics(self):
        self.assertContains(
            self.client.get(self.url),
            f'href="/events/{self.event.pk}/calendar.ics" download>Save to calendar</a>',
            html=False,
        )

    def test_owner_sees_edit_and_other_users_do_not(self):
        mine = make_event(creator=self.user, location="Mine")
        self.assertContains(self.client.get(f"/events/{mine.pk}/"), "Edit</a>")
        self.assertNotContains(self.client.get(self.url), "Edit</a>")


class EventPageLoggedOutTests(TestCase):
    def setUp(self):
        self.event = make_event()
        self.url = f"/events/{self.event.pk}/"

    def test_shared_link_returns_200_with_only_the_event_and_join_cta(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Jazz Night")
        self.assertContains(response, "Join to discover more")
        self.assertContains(response, "Save to calendar")
        # No map and no app navigation.
        self.assertNotContains(response, 'id="map"')
        self.assertNotContains(response, 'href="/map/"')
        self.assertNotContains(response, "/logout/")
        self.assertNotContains(response, "Log out")
        self.assertNotContains(response, "Edit</a>")

    def test_join_cta_lands_on_login_and_returns_to_the_event(self):
        response = self.client.get(self.url)
        join_url = f"/login/?next=%2Fevents%2F{self.event.pk}%2F"
        self.assertContains(response, f'id="join-cta" class="event-join-button" href="{join_url}"')
        login = self.client.get(join_url)
        self.assertEqual(login.status_code, 200)
        self.assertTemplateUsed(login, "accounts/welcome.html")
        self.assertEqual(self.client.session.get("login_next"), self.url)

    def test_page_is_set_up_for_phone_and_desktop(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'name="viewport"')
        self.assertContains(response, "core/event.css")
        self.assertIsNotNone(finders.find("core/event.css"))
        self.assertIsNotNone(finders.find("core/event.js"))


class EventPopupTests(TestCase):
    def test_popup_is_the_event_card_only(self):
        event = make_event()
        response = self.client.get(f"/events/{event.pk}/popup/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="event-detail-title"')
        self.assertContains(response, ">Free<")
        self.assertNotContains(response, "<html")
        self.assertNotContains(response, 'id="share-event"')
        self.assertNotContains(response, "Join to discover more")


class EventCalendarDownloadTests(TestCase):
    def test_download_is_one_valid_event_in_new_york_time(self):
        event = make_event(description="Bring friends; snacks, drinks")
        response = self.client.get(f"/events/{event.pk}/calendar.ics")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/calendar; charset=utf-8")
        self.assertEqual(response["Content-Disposition"], 'attachment; filename="jazz-night.ics"')
        body = response.content.decode()
        self.assertEqual(body.count("BEGIN:VEVENT"), 1)
        self.assertIn("DTSTART;TZID=America/New_York:20261120T190000", body)
        self.assertIn("DTEND;TZID=America/New_York:20261120T210000", body)

        parsed = list(Calendar.from_ical(response.content).walk("VEVENT"))
        self.assertEqual(len(parsed), 1)
        vevent = parsed[0]
        self.assertEqual(vevent.decoded("DTSTART"), event.start_at)
        self.assertEqual(vevent.decoded("DTEND"), event.end_at)
        self.assertEqual(str(vevent["SUMMARY"]), "Jazz Night")
        self.assertEqual(
            str(vevent["DESCRIPTION"]),
            "Bring friends; snacks, drinks\n\nhttps://example.com/jazz",
        )
        self.assertEqual(str(vevent["LOCATION"]), "Yale Commons, 168 Grove St")
        self.assertEqual(str(vevent["URL"]), "https://example.com/jazz")

    def test_download_works_logged_out(self):
        event = make_event()
        self.assertEqual(self.client.get(f"/events/{event.pk}/calendar.ics").status_code, 200)


class MissingEventTests(TestCase):
    def test_unknown_event_id_is_404_everywhere(self):
        for path in ("/events/999999/", "/events/999999/popup/", "/events/999999/calendar.ics"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)


class MapMarkerLinkTests(TestCase):
    def test_map_markers_link_to_the_event_page(self):
        self.client.force_login(make_user())
        event = make_event(
            start_at=datetime(2099, 1, 1, 19, 0, tzinfo=NEW_YORK),
            end_at=datetime(2099, 1, 1, 21, 0, tzinfo=NEW_YORK),
        )
        response = self.client.get("/map/")
        events = response.context["map_config"]["events"]
        self.assertEqual(events[0]["url"], f"/events/{event.pk}/")
        self.assertIsNotNone(finders.find("core/map_provider.js"))
