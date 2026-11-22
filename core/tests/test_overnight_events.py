"""
Create event: overnight and multi-day events (#70).

The End date field's show/hide logic runs in core/static/core/event_form.js;
these tests cover the server rules (America/New_York), the edit pre-fill and
the duplicate check. Photo storage is mocked.
"""

from base64 import b64decode
from datetime import date, datetime, timezone
from unittest import mock
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from core.forms import EventForm
from core.models import Event

NEW_YORK = ZoneInfo("America/New_York")
PNG = b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")


def png():
    return SimpleUploadedFile("event.png", PNG, content_type="image/png")


def values(**overrides):
    # Nov 21, 8:00 PM to 1:00 AM: the example from the issue.
    data = {
        "name": "Late Show", "description": "Overnight", "category": "music_performance",
        "date": "2030-11-21",
        "start_time_hour": "8", "start_time_minute": "00", "start_time_period": "PM",
        "end_time_hour": "1", "end_time_minute": "00", "end_time_period": "AM",
        "end_date": "2030-11-22",
        "location": "Yale Commons", "location_confirmed": "Yale Commons",
        "latitude": "41.308300", "longitude": "-72.927900", "price": "0", "link": "",
    }
    data.update(overrides)
    return data


class OvernightFormTests(TestCase):
    def form(self, **overrides):
        return EventForm(data=values(**overrides), files={"image": png()})

    def test_overnight_event_ends_the_next_day_in_new_york(self):
        form = self.form()
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["start_at"], datetime(2030, 11, 21, 20, 0, tzinfo=NEW_YORK))
        self.assertEqual(form.cleaned_data["end_at"], datetime(2030, 11, 22, 1, 0, tzinfo=NEW_YORK))

    def test_end_date_can_be_moved_later(self):
        form = self.form(end_date="2030-11-23")
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["end_at"], datetime(2030, 11, 23, 1, 0, tzinfo=NEW_YORK))

    def test_without_end_date_the_event_ends_on_the_start_date(self):
        form = self.form(end_date="", end_time_hour="11", end_time_period="PM")
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["end_at"], datetime(2030, 11, 21, 23, 0, tzinfo=NEW_YORK))
        self.assertEqual(form.cleaned_data["end_date"], date(2030, 11, 21))

    def test_end_date_before_the_start_date_is_rejected(self):
        form = self.form(end_date="2030-11-20")
        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors["end_date"], ["End date can't be before the start date."])

    def test_overnight_times_without_an_end_date_are_rejected(self):
        form = self.form(end_date="")
        self.assertFalse(form.is_valid())
        self.assertIn("End time must be after start time.", form.non_field_errors())

    def test_equal_start_and_end_stays_an_error(self):
        form = self.form(end_date="", end_time_hour="8", end_time_period="PM")
        self.assertFalse(form.is_valid())
        self.assertIn("End time must be after start time.", form.non_field_errors())

    def test_end_date_across_the_dst_change_uses_new_york_time(self):
        # Clocks go back at 2 AM on Nov 3, 2030: 8 PM Nov 2 (EDT) to 3 AM Nov 3
        # (EST) is 7 hours on the clock but 8 real hours.
        form = self.form(date="2030-11-02", end_date="2030-11-03", end_time_hour="3")
        self.assertTrue(form.is_valid(), form.errors)
        # Subtract in UTC: with one shared tzinfo Python would subtract wall-clock times.
        utc = [form.cleaned_data[key].astimezone(timezone.utc) for key in ("start_at", "end_at")]
        hours = (utc[1] - utc[0]).total_seconds() / 3600
        self.assertEqual(hours, 8)


class OvernightViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="overnight@yale.edu")
        self.client.force_login(self.user)
        mock.patch("core.views.photo_storage.upload").start()
        self.addCleanup(mock.patch.stopall)

    def test_creating_with_end_date_nov_23_saves_end_at_nov_23_1_am(self):
        response = self.client.post("/map/", {**values(end_date="2030-11-23"), "image": png()})
        self.assertRedirects(response, "/map/", fetch_redirect_response=False)
        event = Event.objects.get(name="Late Show")
        self.assertEqual(event.end_at.astimezone(NEW_YORK), datetime(2030, 11, 23, 1, 0, tzinfo=NEW_YORK))

    def test_end_date_field_is_hidden_until_needed(self):
        html = self.client.get("/map/").content.decode()
        self.assertIn('<div id="end-date-row" class="event-row" hidden>', html)
        self.assertIn('<input type="date" name="end_date"', html)

    def test_rejected_end_date_keeps_the_field_visible_with_its_error(self):
        response = self.client.post("/map/", {**values(end_date="2030-11-20"), "image": png()})
        html = response.content.decode()
        self.assertIn('<div id="end-date-row" class="event-row">', html)
        self.assertIn("End date can&#x27;t be before the start date.", html)

    def make_event(self, start, end):
        return Event.objects.create(
            image="events/x.jpg", name="Saved Late Show", description="d", category="music_performance",
            start_at=start, end_at=end, location="Yale Commons", latitude="41.308300",
            longitude="-72.927900", price="0", link="", creator=self.user)

    def test_edit_page_of_an_overnight_event_shows_the_end_date(self):
        event = self.make_event(datetime(2030, 11, 21, 20, 0, tzinfo=NEW_YORK),
                                datetime(2030, 11, 22, 1, 0, tzinfo=NEW_YORK))
        html = self.client.get(f"/events/{event.pk}/edit/").content.decode()
        self.assertIn('<div id="end-date-row" class="event-row">', html)
        self.assertIn('name="end_date" value="2030-11-22"', html)

    def test_edit_page_of_a_same_day_event_hides_it(self):
        event = self.make_event(datetime(2030, 11, 21, 18, 0, tzinfo=NEW_YORK),
                                datetime(2030, 11, 21, 20, 0, tzinfo=NEW_YORK))
        html = self.client.get(f"/events/{event.pk}/edit/").content.decode()
        self.assertIn('<div id="end-date-row" class="event-row" hidden>', html)

    def test_duplicate_check_uses_the_end_date(self):
        self.make_event(datetime(2030, 11, 21, 20, 0, tzinfo=NEW_YORK),
                        datetime(2030, 11, 22, 1, 0, tzinfo=NEW_YORK))
        params = {"location": "Yale Commons", "date": "2030-11-21", "start_time": "20:00", "end_time": "01:00"}
        self.assertIsNotNone(self.client.get("/map/duplicate/", {**params, "end_date": "2030-11-22"}).json()["match"])
        self.assertIsNone(self.client.get("/map/duplicate/", {**params, "end_date": "2030-11-23"}).json()["match"])
        # The server-side submit check also uses it.
        response = self.client.post("/map/", {**values(), "name": "Copy", "image": png()})
        self.assertContains(response, "An event already exists at this location and time.")


class EndDateScriptTests(TestCase):
    def setUp(self):
        self.source = finders.find("core/event_form.js")
        with open(self.source, encoding="utf-8") as f:
            self.source = f.read()

    def test_end_earlier_than_start_shows_the_next_day(self):
        self.assertIn("return Boolean(start && end && end < start);", self.source)
        self.assertIn("endDate.value = nextDay(dateInput.value);", self.source)
        self.assertIn("new Date(Date.UTC(p[0], p[1] - 1, p[2] + 1))", self.source)

    def test_end_later_hides_and_clears_it(self):
        body = self.source.split("var syncEndDate = function (onLoad) {", 1)[1].split("\n    };\n", 1)[0]
        self.assertIn("endDateRow.hidden = !show;", body)
        self.assertIn('endDate.value = "";', body)

    def test_a_date_the_user_picked_is_kept(self):
        self.assertIn('endDate.addEventListener("input", function () { autoEndDate = false; });', self.source)
