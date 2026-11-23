"""
Going status (#84): the dropdown, the endpoint, hiding "Not going" events from
search, the map and AI search, and the Upcoming query for My Events (#82).
OpenRouter and the geocoder are mocked; nothing external is called.
"""

from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from core.attendance import upcoming_events
from core.models import Event, EventAttendance

Status = EventAttendance.Status
CONFIGURED = dict(OPENROUTER_API_KEY="fake-key", OPENROUTER_MODEL="test/model",
                  OPENROUTER_SEARCH_MODEL="")


def make_event(name, days_ahead=1, creator=None, **fields):
    start = timezone.now() + timedelta(days=days_ahead)
    values = {
        "image": "events/1/test.jpg", "name": name, "description": "Something happening",
        "category": "music_performance", "start_at": start,
        "end_at": start + timedelta(hours=2), "location": f"Place for {name}",
        "latitude": "41.308300", "longitude": "-72.927900", "price": "0",
        "link": "https://example.com/event", "creator": creator,
    }
    values.update(fields)
    return Event.objects.create(**values)


def make_user(name):
    return get_user_model().objects.create_user(username=f"{name}@yale.edu", email=f"{name}@yale.edu")


class GoingTestCase(TestCase):
    def setUp(self):
        self.user = make_user("student")
        self.other = make_user("other")
        self.host = make_user("host")
        self.event = make_event("Jazz Night", creator=self.host)
        self.client.force_login(self.user)

    def go(self, status, event=None):
        return self.client.post(f"/events/{(event or self.event).pk}/going/", {"status": status})

    def saved(self, user=None, event=None):
        row = EventAttendance.objects.filter(user=user or self.user, event=event or self.event).first()
        return row.status if row else None


class DropdownTests(GoingTestCase):
    def page(self, popup=False):
        suffix = "popup/" if popup else ""
        return self.client.get(f"/events/{self.event.pk}/{suffix}").content.decode()

    def test_shows_going_question_when_unanswered(self):
        html = self.page()
        self.assertIn('class="going-select"', html)
        self.assertIn('<option value="" selected>Going?</option>', html)

    def test_shows_the_saved_answer_after_reload(self):
        self.go("maybe")
        self.assertIn('<option value="maybe" selected>', self.page())
        self.assertNotIn('<option value="" selected>', self.page())

    def test_the_map_event_window_has_the_dropdown_too(self):
        self.go("going")
        html = self.page(popup=True)
        self.assertIn('<option value="going" selected>', html)
        self.assertIn(f'data-going-url="/events/{self.event.pk}/going/"', html)

    def test_each_user_sees_only_their_own_answer(self):
        self.go("going")
        self.client.force_login(self.other)
        self.go("not_going")
        self.assertIn('<option value="not_going" selected>', self.page())
        self.client.force_login(self.user)
        self.assertIn('<option value="going" selected>', self.page())
        self.assertEqual(self.saved(self.other), "not_going")

    def test_hidden_from_visitors_who_are_not_logged_in(self):
        self.client.logout()
        response = self.client.get(f"/events/{self.event.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("going-select", response.content.decode())
        self.assertIn("Join to Discover More", response.content.decode())

    def test_host_sees_hosting_instead_of_the_dropdown(self):
        self.client.force_login(self.host)
        html = self.page()
        self.assertIn("You're hosting", html)
        self.assertNotIn("going-select", html)

    def test_hidden_after_the_event_has_ended(self):
        ended = make_event("Old Show", days_ahead=-2)
        html = self.client.get(f"/events/{ended.pk}/").content.decode()
        self.assertNotIn("going-select", html)

    def test_an_event_in_progress_still_takes_an_answer(self):
        now = timezone.now()
        live = make_event("Happening Now", start_at=now - timedelta(hours=1),
                          end_at=now + timedelta(hours=1))
        self.assertIn("going-select", self.client.get(f"/events/{live.pk}/").content.decode())

    def test_pages_are_not_cached_because_they_differ_per_user(self):
        self.assertIn("no-cache", self.client.get(f"/events/{self.event.pk}/")["Cache-Control"])


class EndpointTests(GoingTestCase):
    def test_saves_each_status(self):
        for status in ("going", "maybe", "not_going"):
            response = self.go(status)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"status": status})
            self.assertEqual(self.saved(), status)
        self.assertEqual(EventAttendance.objects.count(), 1)  # one row per user and event

    def test_choosing_going_question_again_clears_the_answer(self):
        self.go("going")
        response = self.go("")
        self.assertEqual(response.json(), {"status": ""})
        self.assertIsNone(self.saved())

    def test_clearing_with_no_answer_is_fine(self):
        self.assertEqual(self.go("").status_code, 200)

    def test_unknown_status_is_rejected_and_nothing_is_saved(self):
        self.assertEqual(self.go("definitely").status_code, 400)
        self.assertEqual(self.go("GOING").status_code, 400)
        self.assertEqual(EventAttendance.objects.count(), 0)

    def test_unknown_status_keeps_the_existing_answer(self):
        self.go("going")
        self.go("nonsense")
        self.assertEqual(self.saved(), "going")

    def test_login_required(self):
        self.client.logout()
        response = self.go("going")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])
        self.assertEqual(EventAttendance.objects.count(), 0)

    def test_post_only(self):
        self.assertEqual(self.client.get(f"/events/{self.event.pk}/going/").status_code, 405)

    def test_missing_event_is_404(self):
        self.assertEqual(self.client.post("/events/99999/going/", {"status": "going"}).status_code, 404)

    def test_ended_event_is_rejected(self):
        ended = make_event("Old Show", days_ahead=-2)
        self.assertEqual(self.go("going", ended).status_code, 400)
        self.assertEqual(EventAttendance.objects.count(), 0)

    def test_host_cannot_answer_for_their_own_event(self):
        self.client.force_login(self.host)
        self.assertEqual(self.go("not_going").status_code, 400)
        self.assertEqual(EventAttendance.objects.count(), 0)

    def test_csrf_is_enforced(self):
        from django.test import Client
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.user)
        response = strict.post(f"/events/{self.event.pk}/going/", {"status": "going"})
        self.assertEqual(response.status_code, 403)

    def test_database_allows_one_row_per_user_and_event(self):
        EventAttendance.objects.create(user=self.user, event=self.event, status="going")
        with self.assertRaises(IntegrityError), transaction.atomic():
            EventAttendance.objects.create(user=self.user, event=self.event, status="maybe")

    def test_rows_are_removed_with_the_user_or_the_event(self):
        EventAttendance.objects.create(user=self.user, event=self.event, status="going")
        EventAttendance.objects.create(user=self.other, event=self.event, status="maybe")
        self.other.delete()
        self.assertEqual(EventAttendance.objects.count(), 1)
        self.event.delete()
        self.assertEqual(EventAttendance.objects.count(), 0)


class SearchHidingTests(GoingTestCase):
    def setUp(self):
        super().setUp()
        self.skipped = make_event("Skipped Show", days_ahead=2)
        self.kept = make_event("Kept Show", days_ahead=3)
        EventAttendance.objects.create(user=self.user, event=self.skipped, status=Status.NOT_GOING)

    def names(self, query=""):
        data = self.client.get("/events/search/" + query).json()
        return [event["name"] for event in data["events"]]

    def test_not_going_events_are_missing_from_search_results(self):
        self.assertEqual(self.names(), ["Jazz Night", "Kept Show"])

    def test_going_maybe_and_unanswered_events_still_show(self):
        EventAttendance.objects.create(user=self.user, event=self.kept, status=Status.MAYBE)
        EventAttendance.objects.create(user=self.user, event=self.event, status=Status.GOING)
        self.assertEqual(self.names(), ["Jazz Night", "Kept Show"])

    def test_the_filter_brings_them_back(self):
        self.assertEqual(self.names("?include_not_going=1"),
                         ["Jazz Night", "Skipped Show", "Kept Show"])

    def test_other_users_still_see_the_event(self):
        self.client.force_login(self.other)
        self.assertIn("Skipped Show", self.names())

    def test_text_and_category_searches_hide_them_too(self):
        self.assertEqual(self.names("?q=skipped"), [])
        self.assertEqual(self.names("?q=skipped&include_not_going=1"), ["Skipped Show"])
        self.assertNotIn("Skipped Show", self.names("?category=music_performance"))

    def test_the_count_matches_the_list(self):
        data = self.client.get("/events/search/").json()
        self.assertEqual(data["count"], len(data["events"]))
        self.assertEqual(data["count"], 2)

    def test_map_pins_on_first_load_skip_not_going_events(self):
        config = self.client.get("/map/").context["map_config"]
        self.assertEqual([e["name"] for e in config["events"]], ["Jazz Night", "Kept Show"])

    def test_the_event_page_still_opens_for_a_not_going_event(self):
        self.assertEqual(self.client.get(f"/events/{self.skipped.pk}/").status_code, 200)

    def test_panel_has_the_include_filter_and_script_handles_it(self):
        html = self.client.get("/map/").content.decode()
        self.assertIn('id="search-include-not-going"', html)
        self.assertIn("Include Events I'm Not Going To", html)
        self.assertIn("core/going.js", html)
        script = open("core/static/core/search.js").read()
        self.assertIn('params.get("include_not_going")', script)
        self.assertIn("Including Not Going", script)


@override_settings(**CONFIGURED)
class AiSearchHidingTests(GoingTestCase):
    def setUp(self):
        super().setUp()
        self.skipped = make_event("Skipped Jazz", days_ahead=2)
        EventAttendance.objects.create(user=self.user, event=self.skipped, status=Status.NOT_GOING)
        patcher = mock.patch("core.ai_search.llm.chat_json")
        self.chat_json = patcher.start()
        self.addCleanup(patcher.stop)

    def ask(self, filters):
        no_filters = {"q": None, "categories": [], "when": None, "date_from": None,
                      "date_to": None, "time_from": None, "time_to": None,
                      "near_address": None, "radius_mi": None}
        self.chat_json.return_value = {"reply": "ok", "filters": {**no_filters, **filters}}
        return self.client.post("/events/search/ai/", {"message": "jazz"}).json()

    def test_ai_results_skip_not_going_events(self):
        data = self.ask({"q": "jazz"})
        self.assertEqual([e["name"] for e in data["events"]], ["Jazz Night"])

    def test_the_model_cannot_turn_the_include_filter_on(self):
        data = self.ask({"q": "jazz", "include_not_going": True})
        self.assertEqual([e["name"] for e in data["events"]], ["Jazz Night"])
        self.assertNotIn("include_not_going", data["filters"])


class UpcomingTests(GoingTestCase):
    def names(self, user=None):
        return [e.name for e in upcoming_events(user or self.user)]

    def test_going_and_maybe_are_upcoming_but_not_going_and_unanswered_are_not(self):
        going = make_event("Going Event", days_ahead=2)
        maybe = make_event("Maybe Event", days_ahead=3)
        no = make_event("No Event", days_ahead=4)
        make_event("Unanswered Event", days_ahead=5)
        for event, status in ((going, "going"), (maybe, "maybe"), (no, "not_going")):
            EventAttendance.objects.create(user=self.user, event=event, status=status)
        self.assertEqual(self.names(), ["Going Event", "Maybe Event"])

    def test_hosted_events_count_as_going_without_an_answer(self):
        make_event("Mine", days_ahead=2, creator=self.user)
        self.assertEqual(self.names(), ["Mine"])

    def test_ended_events_are_dropped(self):
        old = make_event("Old Show", days_ahead=-2)
        EventAttendance.objects.create(user=self.user, event=old, status="going")
        self.assertEqual(self.names(), [])

    def test_a_hosted_event_the_host_also_answered_is_listed_once(self):
        mine = make_event("Mine", creator=self.user)
        EventAttendance.objects.create(user=self.user, event=mine, status="going")
        self.assertEqual(self.names(), ["Mine"])

    def test_answers_of_other_users_do_not_leak(self):
        EventAttendance.objects.create(user=self.other, event=self.event, status="going")
        self.assertEqual(self.names(), [])
        self.assertEqual(self.names(self.other), ["Jazz Night"])
