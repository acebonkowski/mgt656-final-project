"""
Search endpoint (#35): GET /events/search/.

The matching rules are tested in test_search.py; these tests cover the HTTP
layer: login, JSON shape, validation errors and parity with the map's events.
"""

from datetime import timedelta
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from core.models import Event

NY = ZoneInfo("America/New_York")


def make_event(name, days_ahead=1, **fields):
    start = timezone.now() + timedelta(days=days_ahead)
    values = {
        "image": "events/1/test.jpg",
        "name": name,
        "description": "Something happening",
        "category": "music_performance",
        "start_at": start,
        "end_at": start + timedelta(hours=2),
        "location": "Yale Commons",
        "latitude": "41.308300",
        "longitude": "-72.927900",
        "price": "0",
        "link": "https://example.com/event",
    }
    values.update(fields)
    return Event.objects.create(**values)


class SearchEndpointTests(TestCase):
    url = "/events/search/"

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="search-user@yale.edu")
        self.client.force_login(self.user)

    def test_requires_login(self):
        make_event("Jazz Night")
        self.client.logout()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertNotIn(b"Jazz Night", response.content)

    def test_only_get_is_allowed(self):
        self.assertEqual(self.client.post(self.url).status_code, 405)

    def test_no_filters_returns_upcoming_events_in_start_order(self):
        make_event("Later", days_ahead=3)
        make_event("Sooner", days_ahead=1)
        ended = make_event("Ended", days_ahead=-2)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 2)
        self.assertEqual([e["name"] for e in data["events"]], ["Sooner", "Later"])
        self.assertNotIn(ended.pk, [e["id"] for e in data["events"]])

    def test_result_fields(self):
        event = make_event("Jazz Night", price="12.5", category="food_drink")
        result = self.client.get(self.url).json()["events"][0]
        self.assertEqual(result["id"], event.pk)
        self.assertEqual(result["price"], "$12.50")
        self.assertEqual(result["category"], "food_drink")
        self.assertEqual(result["category_label"], "Food & Drink")
        self.assertEqual(result["start_at"], event.start_at.astimezone(NY).isoformat())
        self.assertEqual(result["end_at"], event.end_at.astimezone(NY).isoformat())
        self.assertEqual(result["image_url"], "/event-photo/events/1/test.jpg")
        self.assertEqual(result["detail_url"], f"/events/{event.pk}/")
        self.assertEqual(result["popup_url"], f"/events/{event.pk}/popup/")

    def test_free_price(self):
        make_event("Free Gig", price="0")
        self.assertEqual(self.client.get(self.url).json()["events"][0]["price"], "Free")

    def test_results_share_the_map_event_format(self):
        make_event("Jazz Night", price="5")
        map_event = self.client.get("/map/").context["map_config"]["events"][0]
        result = self.client.get(self.url).json()["events"][0]
        self.assertEqual({key: result[key] for key in map_event}, map_event)

    def test_filters_from_query_string_including_repeated_category(self):
        make_event("Jazz Night", category="music_performance")
        make_event("Jazz Lunch", category="food_drink")
        make_event("Book Talk", category="talks_panels")
        response = self.client.get(
            self.url, {"q": "jazz", "category": ["music_performance", "food_drink"]}
        )
        self.assertCountEqual([e["name"] for e in response.json()["events"]],
                              ["Jazz Night", "Jazz Lunch"])

    def test_no_match_returns_empty_list(self):
        make_event("Jazz Night")
        data = self.client.get(self.url, {"q": "karaoke"}).json()
        self.assertEqual(data, {"count": 0, "events": []})

    def test_invalid_parameters_return_400_with_field_errors(self):
        response = self.client.get(self.url, {
            "date_from": "not-a-date", "category": "nope", "area": "1,2",
        })
        self.assertEqual(response.status_code, 400)
        errors = response.json()["errors"]
        self.assertEqual(set(errors), {"date_from", "category", "area"})
        self.assertTrue(all(isinstance(m, str) for msgs in errors.values() for m in msgs))

    def test_end_date_before_start_date_returns_400(self):
        response = self.client.get(self.url, {"date_from": "2030-01-05", "date_to": "2030-01-01"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("date_to", response.json()["errors"])
