"""
My Events (#82): the dashboard rows, View All pages, cards and badges, the
login redirect and the link on the map. No external services are involved.
"""

import re
from datetime import timedelta
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils.html import escape
from django.utils import timezone

from core.models import Event, EventAttendance
from core.my_events import ROW_LIMIT, favorite_events

DASHBOARD = "/my-events/"


def make_user(name):
    return get_user_model().objects.create_user(username=f"{name}@yale.edu", email=f"{name}@yale.edu")


def make_event(name, days_ahead=1, creator=None, **fields):
    start = timezone.now() + timedelta(days=days_ahead)
    values = {
        "image": "default", "name": name, "description": "Something happening",
        "category": "music_performance", "start_at": start,
        "end_at": start + timedelta(hours=2), "location": f"Place for {name}",
        "latitude": "41.308300", "longitude": "-72.927900", "price": "0",
        "link": "https://example.com/event", "creator": creator,
    }
    values.update(fields)
    return Event.objects.create(**values)


def answer(user, event, status):
    EventAttendance.objects.create(user=user, event=event, status=status)


class MyEventsTestCase(TestCase):
    def setUp(self):
        self.user = make_user("student")
        self.host = make_user("host")
        self.client.force_login(self.user)

    def page(self, url=DASHBOARD):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def section(self, html, key):
        """The HTML of one dashboard row."""
        match = re.search(rf'<section class="my-events-row" aria-labelledby="row-{key}">(.*?)</section>',
                          html, re.S)
        self.assertIsNotNone(match, key)
        return match.group(1)


class DashboardTests(MyEventsTestCase):
    def test_three_rows_in_order(self):
        html = self.page()
        titles = re.findall(r'<h2 id="row-\w+">(.*?)</h2>', html)
        self.assertEqual(titles, ["Upcoming Events", "Hosted Events", "Favorites"])

    def test_empty_rows_show_their_messages(self):
        html = self.page()
        self.assertIn("Nothing coming up yet", self.section(html, "upcoming"))
        self.assertIn(escape("You haven't hosted any events"), self.section(html, "hosted"))
        self.assertIn("No favorites yet", self.section(html, "favorites"))
        self.assertNotIn("my-events-scroller", html)

    def test_an_event_i_host_is_in_upcoming_and_hosted(self):
        make_event("My Party", creator=self.user)
        html = self.page()
        self.assertIn("My Party", self.section(html, "upcoming"))
        self.assertIn("My Party", self.section(html, "hosted"))

    def test_going_and_maybe_are_upcoming_but_not_going_and_unanswered_are_not(self):
        answer(self.user, make_event("Going One", days_ahead=2, creator=self.host), "going")
        answer(self.user, make_event("Maybe One", days_ahead=3, creator=self.host), "maybe")
        answer(self.user, make_event("Skipped One", days_ahead=4, creator=self.host), "not_going")
        make_event("Unanswered One", days_ahead=5, creator=self.host)
        upcoming = self.section(self.page(), "upcoming")
        self.assertIn("Going One", upcoming)
        self.assertIn("Maybe One", upcoming)
        self.assertNotIn("Skipped One", upcoming)
        self.assertNotIn("Unanswered One", upcoming)

    def test_upcoming_is_earliest_first(self):
        answer(self.user, make_event("Later", days_ahead=5, creator=self.host), "going")
        answer(self.user, make_event("Sooner", days_ahead=1, creator=self.host), "going")
        upcoming = self.section(self.page(), "upcoming")
        self.assertLess(upcoming.index("Sooner"), upcoming.index("Later"))

    def test_ended_events_are_not_upcoming_but_hosted_keeps_them_last(self):
        make_event("Old Show", days_ahead=-3, creator=self.user)
        make_event("New Show", days_ahead=2, creator=self.user)
        html = self.page()
        self.assertNotIn("Old Show", self.section(html, "upcoming"))
        hosted = self.section(html, "hosted")
        self.assertLess(hosted.index("New Show"), hosted.index("Old Show"))

    def test_past_hosted_events_are_latest_first(self):
        make_event("Older", days_ahead=-9, creator=self.user)
        make_event("Recent", days_ahead=-2, creator=self.user)
        hosted = self.section(self.page(), "hosted")
        self.assertLess(hosted.index("Recent"), hosted.index("Older"))

    def test_other_users_events_and_answers_stay_out(self):
        theirs = make_event("Their Party", creator=self.host)
        answer(self.host, theirs, "going")
        html = self.page()
        self.assertNotIn("Their Party", html)

    def test_rows_stop_at_ten_events_and_view_all_lists_everything(self):
        for number in range(ROW_LIMIT + 3):
            make_event(f"Event {number:02d}", days_ahead=number + 1, creator=self.user)
        hosted = self.section(self.page(), "hosted")
        self.assertEqual(hosted.count('class="my-event-card"'), ROW_LIMIT)
        everything = self.page("/my-events/hosted/")
        self.assertEqual(everything.count('class="my-event-card"'), ROW_LIMIT + 3)

    def test_no_n_plus_one_queries(self):
        for number in range(8):
            answer(self.user, make_event(f"Going {number}", days_ahead=number + 1, creator=self.host), "going")
        # Favorites adds one bounded query, regardless of the number of cards.
        with self.assertNumQueries(7):
            self.client.get(DASHBOARD)


class CardTests(MyEventsTestCase):
    def test_card_shows_all_six_fields_and_opens_the_event_page(self):
        event = make_event("Jazz Night", creator=self.user, price="12.50",
                           location="Woolsey Hall")
        html = self.section(self.page(), "hosted")
        self.assertIn(f'href="/events/{event.pk}/"', html)
        self.assertIn(event.image_url, html)  # image
        self.assertIn("Jazz Night", html)  # title
        self.assertRegex(html, r"<time datetime=[^>]+>\w{3}, \w{3} \d+</time>")  # date
        self.assertRegex(html, r"· \d{1,2}:\d{2} [AP]M")  # time
        self.assertIn("Woolsey Hall", html)  # location
        self.assertIn("$12.50", html)  # price

    def test_free_events_say_free(self):
        make_event("Free Show", creator=self.user, price="0")
        self.assertIn("Free", self.section(self.page(), "hosted"))

    def test_times_are_new_york_time(self):
        start = (timezone.now() + timedelta(days=2)).replace(hour=3, minute=0, second=0, microsecond=0)
        make_event("Late Show", creator=self.user, start_at=start, end_at=start + timedelta(hours=1))
        expected = start.astimezone(ZoneInfo("America/New_York")).strftime("%I:%M %p").lstrip("0")
        self.assertIn(f"· {expected}", self.section(self.page(), "hosted"))

    def test_badges_on_upcoming_cards(self):
        make_event("Mine", days_ahead=1, creator=self.user)
        answer(self.user, make_event("Going Show", days_ahead=2, creator=self.host), "going")
        answer(self.user, make_event("Maybe Show", days_ahead=3, creator=self.host), "maybe")
        upcoming = self.section(self.page(), "upcoming")
        self.assertIn("my-event-badge--hosting", upcoming)
        self.assertIn("my-event-badge--going", upcoming)
        self.assertIn("my-event-badge--maybe", upcoming)

    def test_hosted_row_has_no_badges(self):
        make_event("Mine", creator=self.user)
        self.assertNotIn("my-event-badge", self.section(self.page(), "hosted"))


class ViewAllTests(MyEventsTestCase):
    def test_each_row_links_to_its_view_all_page(self):
        html = self.page()
        for key in ("upcoming", "hosted", "favorites"):
            self.assertIn(f'href="/my-events/{key}/"', self.section(html, key))

    def test_view_all_lists_the_row_with_a_back_arrow(self):
        make_event("My Party", creator=self.user)
        html = self.page("/my-events/hosted/")
        self.assertIn("My Party", html)
        self.assertIn("<h1>Hosted Events</h1>", html)
        self.assertIn(f'href="{reverse("my_events")}"', html)
        self.assertIn("← My Events", html)

    def test_view_all_upcoming_matches_the_row_rules(self):
        answer(self.user, make_event("Skipped One", creator=self.host), "not_going")
        answer(self.user, make_event("Going One", creator=self.host), "going")
        html = self.page("/my-events/upcoming/")
        self.assertIn("Going One", html)
        self.assertNotIn("Skipped One", html)

    def test_view_all_empty_message(self):
        self.assertIn(escape("You haven't hosted any events"), self.page("/my-events/hosted/"))
        self.assertIn("No favorites yet", self.page("/my-events/favorites/"))

    def test_unknown_row_is_404(self):
        self.assertEqual(self.client.get("/my-events/friends/").status_code, 404)


class FavoritesStubTests(MyEventsTestCase):
    def test_favorites_is_empty_without_saved_events(self):
        make_event("Anything", creator=self.user)
        self.assertEqual(list(favorite_events(self.user)), [])


class AccessTests(MyEventsTestCase):
    def test_login_required_everywhere(self):
        self.client.logout()
        for url in (DASHBOARD, "/my-events/upcoming/", "/my-events/hosted/", "/my-events/favorites/"):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302, url)
            self.assertIn("/login/", response["Location"])

    def test_pages_are_not_cached(self):
        self.assertIn("no-cache", self.client.get(DASHBOARD)["Cache-Control"])

    def test_map_has_the_my_events_link(self):
        html = self.page("/map/")
        self.assertIn('id="my-events-link"', html)
        self.assertIn(f'href="{reverse("my_events")}"', html)

    def test_dashboard_links_back_to_the_map(self):
        self.assertIn(f'href="{reverse("map")}"', self.page())
