"""
Event search core (#35): EventSearchForm and search_events().

The clock is fixed (NOW, a Wednesday) so date rules are deterministic. Tests
that need Postgres full-text search are skipped on SQLite; CI runs on Postgres.
"""

import unittest
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from django.db import connection
from django.test import TestCase

from core.models import Event
from core.search import EventSearchForm, distance_mi, quick_pick_dates, search_events

NY = ZoneInfo("America/New_York")
NOW = datetime(2026, 11, 18, 12, 0, tzinfo=NY)  # Wednesday noon
YALE = (41.3083, -72.9279)

postgres_only = unittest.skipUnless(
    connection.vendor == "postgresql", "Full-text search needs Postgres"
)


def at(day, hour, minute=0):
    return datetime(2026, 11, day, hour, minute, tzinfo=NY)


def make_event(name="Event", start=None, end=None, **fields):
    start = start or at(19, 18)
    values = {
        "image": "events/test.jpg",
        "name": name,
        "description": "Something happening",
        "category": "social_community",
        "start_at": start,
        "end_at": end or start + timedelta(hours=2),
        "location": "Yale Commons",
        "latitude": f"{YALE[0]:.6f}",
        "longitude": f"{YALE[1]:.6f}",
        "price": "0",
        "link": "https://example.com/event",
    }
    values.update(fields)
    return Event.objects.create(**values)


class SearchTestCase(TestCase):
    def search(self, **params):
        form = EventSearchForm(params, now=NOW)
        self.assertTrue(form.is_valid(), form.errors)
        return list(form.search())

    def names(self, **params):
        return [event.name for event in self.search(**params)]

    def errors(self, **params):
        form = EventSearchForm(params, now=NOW)
        self.assertFalse(form.is_valid())
        return form.errors


class NoFilterAndExpiryTests(SearchTestCase):
    def test_no_filters_returns_all_upcoming_sorted_by_start(self):
        make_event("Later", start=at(20, 18))
        make_event("Sooner", start=at(19, 9))
        self.assertEqual(self.names(), ["Sooner", "Later"])

    def test_ended_events_are_never_returned(self):
        make_event("Ended", start=at(18, 8), end=at(18, 11))
        make_event("Running now", start=at(18, 11), end=at(18, 13))
        self.assertEqual(self.names(), ["Running now"])
        self.assertEqual(self.names(q="ended"), [])


class TextSearchTests(SearchTestCase):
    def test_matches_name_and_description_ignoring_case(self):
        make_event("Jazz Night")
        make_event("Open Mic", description="Bring your JAZZ standards")
        make_event("Book Club")
        self.assertCountEqual(self.names(q="jazz"), ["Jazz Night", "Open Mic"])
        self.assertCountEqual(self.names(q="JAZZ"), ["Jazz Night", "Open Mic"])

    def test_half_typed_word_matches(self):
        make_event("Concert on the Green")
        self.assertEqual(self.names(q="conc"), ["Concert on the Green"])

    def test_name_match_is_listed_before_description_match(self):
        make_event("Open Mic", start=at(19, 9), description="Some jazz tonight")
        make_event("Jazz Night", start=at(20, 20))
        self.assertEqual(self.names(q="jazz"), ["Jazz Night", "Open Mic"])

    @postgres_only
    def test_word_forms_match(self):
        make_event("Green Music", description="A concert in the park")
        self.assertEqual(self.names(q="concerts"), ["Green Music"])

    def test_blank_text_is_ignored(self):
        make_event("Anything")
        self.assertEqual(self.names(q="   "), ["Anything"])


class CategoryTests(SearchTestCase):
    def test_category_choices_are_exactly_the_12(self):
        self.assertEqual(len(EventSearchForm().fields["category"].choices), 12)

    def test_one_or_more_categories(self):
        make_event("Gig", category="music_performance")
        make_event("Lunch", category="food_drink")
        make_event("Panel", category="talks_panels")
        self.assertEqual(self.names(category=["food_drink"]), ["Lunch"])
        self.assertCountEqual(
            self.names(category=["food_drink", "talks_panels"]), ["Lunch", "Panel"]
        )

    def test_unknown_category_is_rejected(self):
        self.assertIn("category", self.errors(category=["not_a_category"]))


class DateTests(SearchTestCase):
    def test_single_day_includes_events_still_running_from_earlier(self):
        make_event("Multi-day", start=at(18, 13), end=at(21, 17))
        make_event("That day", start=at(20, 10))
        make_event("Other day", start=at(22, 10))
        self.assertCountEqual(self.names(date_from="2026-11-20"), ["Multi-day", "That day"])

    def test_only_end_date_means_that_single_day(self):
        make_event("That day", start=at(20, 10))
        make_event("Other day", start=at(19, 10))
        self.assertEqual(self.names(date_to="2026-11-20"), ["That day"])

    def test_range_returns_overlapping_events(self):
        make_event("Before", start=at(19, 10))
        make_event("Inside", start=at(21, 10))
        make_event("Crosses end", start=at(22, 23), end=at(23, 2))
        make_event("After", start=at(23, 10))
        self.assertCountEqual(
            self.names(date_from="2026-11-20", date_to="2026-11-22"), ["Inside", "Crosses end"]
        )

    def test_end_date_before_start_date_is_rejected(self):
        self.assertIn("date_to", self.errors(date_from="2026-11-22", date_to="2026-11-20"))

    def test_malformed_date_is_rejected(self):
        self.assertIn("date_from", self.errors(date_from="20/11/2026"))


class QuickPickTests(SearchTestCase):
    def test_quick_pick_dates(self):
        wednesday, saturday, sunday = date(2026, 11, 18), date(2026, 11, 21), date(2026, 11, 22)
        self.assertEqual(quick_pick_dates("today", wednesday), (wednesday, wednesday))
        self.assertEqual(quick_pick_dates("tomorrow", wednesday), (date(2026, 11, 19),) * 2)
        self.assertEqual(quick_pick_dates("weekend", wednesday), (saturday, sunday))
        self.assertEqual(quick_pick_dates("weekend", saturday), (saturday, sunday))
        self.assertEqual(quick_pick_dates("weekend", sunday), (sunday, sunday))

    def test_today_uses_new_york_date_late_in_the_evening(self):
        # 11:30pm in New York is already the next day in UTC.
        late = datetime(2026, 11, 18, 23, 30, tzinfo=NY)
        form = EventSearchForm({"when": "today"}, now=late)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["date_from"], date(2026, 11, 18))

    def test_weekend_quick_pick_filters_events(self):
        make_event("Friday", start=at(20, 18))
        make_event("Saturday", start=at(21, 18))
        make_event("Sunday", start=at(22, 18))
        self.assertEqual(self.names(when="weekend"), ["Saturday", "Sunday"])

    def test_quick_pick_overrides_typed_dates(self):
        make_event("Tomorrow", start=at(19, 18))
        make_event("Later", start=at(25, 18))
        self.assertEqual(self.names(when="tomorrow", date_from="2026-11-25"), ["Tomorrow"])


class TimeOfDayTests(SearchTestCase):
    def test_start_time_window_uses_new_york_time(self):
        make_event("Morning", start=at(19, 9))
        make_event("Evening", start=at(19, 18, 30))
        make_event("Late", start=at(19, 22))
        self.assertEqual(self.names(time_from="18:00", time_to="20:00"), ["Evening"])

    def test_one_sided_time_window(self):
        make_event("Morning", start=at(19, 9))
        make_event("Evening", start=at(19, 18, 30))
        self.assertEqual(self.names(time_from="12:00"), ["Evening"])
        self.assertEqual(self.names(time_to="12:00"), ["Morning"])

    def test_end_time_not_after_start_time_is_rejected(self):
        self.assertIn("time_to", self.errors(time_from="20:00", time_to="18:00"))


class LocationTests(SearchTestCase):
    def test_distance_helper(self):
        # One degree of latitude is about 69 miles.
        self.assertAlmostEqual(distance_mi(41.0, -72.9, 42.0, -72.9), 69.1, delta=0.2)

    def test_radius_includes_inside_and_excludes_just_outside(self):
        make_event("0.9 mi", latitude=f"{YALE[0] + 0.0130:.6f}")
        make_event("1.1 mi", latitude=f"{YALE[0] + 0.0160:.6f}")
        self.assertEqual(self.names(near_lat=YALE[0], near_lng=YALE[1], radius_mi="1"), ["0.9 mi"])
        self.assertCountEqual(
            self.names(near_lat=YALE[0], near_lng=YALE[1], radius_mi="2"), ["0.9 mi", "1.1 mi"]
        )

    def test_radius_defaults_to_one_mile(self):
        make_event("Near")
        make_event("Far", latitude=f"{YALE[0] + 0.05:.6f}")
        self.assertEqual(self.names(near_lat=YALE[0], near_lng=YALE[1]), ["Near"])

    def test_point_needs_latitude_and_longitude(self):
        self.assertIn("near_lat", self.errors(near_lat=YALE[0]))

    def test_unsupported_radius_is_rejected(self):
        self.assertIn("radius_mi", self.errors(near_lat=YALE[0], near_lng=YALE[1], radius_mi="3"))

    def test_map_area(self):
        make_event("Inside")
        make_event("Outside", longitude="-72.800000")
        bbox = "-72.95,41.29,-72.90,41.33"
        self.assertEqual(self.names(bbox=bbox), ["Inside"])

    def test_malformed_or_inverted_map_area_is_rejected(self):
        self.assertIn("bbox", self.errors(bbox="-72.95,41.29,-72.90"))
        self.assertIn("bbox", self.errors(bbox="abc,41.29,-72.90,41.33"))
        self.assertIn("bbox", self.errors(bbox="-72.90,41.29,-72.95,41.33"))


class CombinedTests(SearchTestCase):
    def test_all_filters_must_match(self):
        make_event("Jazz Night", category="music_performance", start=at(21, 19))
        make_event("Jazz Brunch", category="food_drink", start=at(21, 11))
        make_event("Jazz Far", category="music_performance", start=at(21, 19),
                   latitude=f"{YALE[0] + 0.1:.6f}")
        make_event("Jazz Friday", category="music_performance", start=at(20, 19))
        params = {
            "q": "jazz", "category": ["music_performance"], "when": "weekend",
            "time_from": "17:00", "near_lat": YALE[0], "near_lng": YALE[1], "radius_mi": "1",
        }
        self.assertEqual(self.names(**params), ["Jazz Night"])

    def test_no_match_returns_empty(self):
        make_event("Jazz Night")
        self.assertEqual(self.names(q="karaoke"), [])
        self.assertEqual(search_events({"category": ["faith_spirituality"]}, now=NOW).count(), 0)
