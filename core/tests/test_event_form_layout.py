"""
Create event: compact two-column form, limits, optional link (#69).

Photo storage is mocked; nothing leaves the test process.
"""

import re
from base64 import b64decode
from datetime import datetime, time, timedelta
from unittest import mock
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from core.forms import EventForm, TwelveHourTimeWidget, to_12_hour, to_24_hour
from core.models import Event

NEW_YORK = ZoneInfo("America/New_York")
PNG = b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")


def static_source(path):
    with open(finders.find(path), encoding="utf-8") as f:
        return f.read()


def event_values(**overrides):
    tomorrow = timezone.now().astimezone(NEW_YORK).date() + timedelta(days=1)
    values = {
        "image": SimpleUploadedFile("event.png", PNG, content_type="image/png"),
        "name": "Layout Event", "description": "Compact form", "category": "music_performance",
        "date": tomorrow.isoformat(),
        "start_time_hour": "6", "start_time_minute": "00", "start_time_period": "PM",
        "end_time_hour": "8", "end_time_minute": "00", "end_time_period": "PM",
        "location": "Yale Commons", "location_confirmed": "Yale Commons",
        "latitude": "41.308300", "longitude": "-72.927900", "price": "0", "link": "",
    }
    values.update(overrides)
    return values


class CreateFormLayoutTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="layout@yale.edu")
        self.client.force_login(self.user)
        self.response = self.client.get("/map/")
        self.html = self.response.content.decode()
        self.form = self.html.split('class="event-fields"', 1)[1].split("</form>", 1)[0]

    def rows(self):
        return [[name for name in re.findall(r'<label for="id_([a-z_]+?)(?:_hour)?">', row)
                 if not name.endswith(("_am", "_pm"))]
                for row in self.form.split('<div class="event-row">')[1:]]

    def test_title_label_and_limits(self):
        self.assertIn('<label for="id_name">Title</label>', self.form)
        self.assertNotIn(">Name", self.form)
        self.assertIn('data-count-for="id_name" data-max="30">0/30</span>', self.form)
        self.assertIn('data-count-for="id_description" data-max="150">0/150</span>', self.form)
        self.assertIn('maxlength="30"', self.form)
        self.assertIn('maxlength="150"', self.form)

    def test_two_column_rows(self):
        self.assertEqual([row[:2] for row in self.rows()],
                         [["category", "date"], ["start_time", "end_time"], ["price", "link"]])
        # Address stays full width: a direct child of .event-fields, not in a row.
        self.assertIn('\n  <div class="event-field">\n    <label for="id_location">Address</label>', self.form)

    def test_link_is_marked_optional(self):
        link = self.form.split('for="id_link"', 1)[1].split("</div>\n  </div>", 1)[0]
        self.assertIn('<span class="field-optional">Optional</span>', self.form)
        self.assertIn('placeholder="Optional"', link)
        self.assertNotIn("required", re.search(r'<input[^>]*id="id_link"[^>]*>', self.form).group(0))

    def test_times_are_12_hour_controls(self):
        for name in ("start_time", "end_time"):
            self.assertIn(f'id="id_{name}_hour" class="time12-hour" name="{name}_hour"', self.form)
            self.assertIn(f'name="{name}_period" value="PM" checked', self.form)
        self.assertNotIn('type="time"', self.form)

    def test_counters_and_auto_grow_script(self):
        source = static_source("core/event_form.js")
        self.assertIn('counter.textContent = input.value.length + "/" + max;', source)
        self.assertIn("description.style.height = description.scrollHeight", source)
        css = static_source("core/map.css")
        textarea = css.split(".event-fields textarea {", 1)[1].split("}", 1)[0]
        self.assertIn("overflow: hidden;", textarea)  # no inner scrollbar
        self.assertIn("resize: none;", textarea)
        self.assertLess(self.html.index("core/time12.js"), self.html.index("core/map.js"))
        self.assertIn("core/event_form.js", self.html)

    def test_rows_fit_a_phone(self):
        css = static_source("core/map.css")
        row = css.split(".event-row {", 1)[1].split("}", 1)[0]
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr));", row)
        self.assertIn("flex-wrap: wrap;", css.split(".event-fields .time12 {", 1)[1].split("}", 1)[0])


class OptionalLinkTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="link@yale.edu")
        self.client.force_login(self.user)
        mock.patch("core.views.photo_storage.upload").start()
        self.addCleanup(mock.patch.stopall)

    def test_event_without_a_link_is_created(self):
        response = self.client.post("/map/", event_values(link=""))
        self.assertRedirects(response, "/map/", fetch_redirect_response=False)
        event = Event.objects.get(name="Layout Event")
        self.assertEqual(event.link, "")
        self.assertEqual(event.start_at.astimezone(NEW_YORK).time(), time(18, 0))
        self.assertEqual(event.end_at.astimezone(NEW_YORK).time(), time(20, 0))

    def test_price_is_still_required(self):
        response = self.client.post("/map/", event_values(price=""))
        self.assertEqual(response.status_code, 200)
        self.assertIn("price", response.context["event_form"].errors)
        self.assertFalse(Event.objects.exists())

    def test_detail_page_hides_the_link_row_when_empty(self):
        start = datetime(2030, 1, 15, 18, 0, tzinfo=NEW_YORK)
        event = Event.objects.create(
            image="events/x.jpg", name="No Link", description="d", category="music_performance",
            start_at=start, end_at=start + timedelta(hours=2), location="Yale Commons",
            latitude="41.308300", longitude="-72.927900", price="0", link="", creator=self.user)
        page = self.client.get(f"/events/{event.pk}/")
        self.assertNotContains(page, 'data-field="link"')
        self.assertNotContains(page, "<dt>Link</dt>")
        event.link = "https://example.com/x"
        event.save()
        self.assertContains(self.client.get(f"/events/{event.pk}/"), 'data-field="link"')

    def test_edit_page_uses_the_same_layout_and_prefills_12_hour_times(self):
        start = datetime(2030, 1, 15, 20, 5, tzinfo=NEW_YORK)
        event = Event.objects.create(
            image="events/x.jpg", name="Edit Me", description="d", category="music_performance",
            start_at=start, end_at=start + timedelta(hours=1), location="Yale Commons",
            latitude="41.308300", longitude="-72.927900", price="0", link="", creator=self.user)
        html = self.client.get(f"/events/{event.pk}/edit/").content.decode()
        self.assertIn('class="event-fields"', html)
        self.assertIn('<label for="id_name">Title</label>', html)
        self.assertIn('id="id_start_time_hour" class="time12-hour" name="start_time_hour" type="text"', html)
        self.assertRegex(html, r'name="start_time_hour"[^>]*value="8"')
        self.assertRegex(html, r'name="start_time_minute"[^>]*value="05"')
        self.assertIn('name="start_time_period" value="PM" checked', html)
        self.assertIn("core/event_form.js", html)


class TwelveHourConversionTests(SimpleTestCase):
    """The server-side twin of time12.js (#67)."""

    def test_to_24_hour(self):
        cases = {("8", "00", "PM"): "20:00", ("12", "00", "AM"): "00:00", ("12", "30", "PM"): "12:30",
                 ("9", "", "AM"): "09:00", ("13", "00", "PM"): None, ("8", "61", "PM"): None,
                 ("8", "00", ""): None, ("x", "00", "AM"): None}
        for args, expected in cases.items():
            with self.subTest(args=args):
                self.assertEqual(to_24_hour(*args), expected)

    def test_to_12_hour_for_display(self):
        self.assertEqual(to_12_hour(time(20, 5)), ("8", "05", "PM"))
        self.assertEqual(to_12_hour(time(0, 0)), ("12", "00", "AM"))
        self.assertEqual(to_12_hour("13:45"), ("1", "45", "PM"))
        self.assertEqual(to_12_hour("13:5 PM"), ("13", "5", "PM"))  # what the user typed
        self.assertEqual(to_12_hour(None), ("", "", "PM"))

    def test_widget_posts_24_hour_values(self):
        widget = TwelveHourTimeWidget()
        read = widget.value_from_datadict
        self.assertEqual(read({"t_hour": "8", "t_minute": "00", "t_period": "PM"}, {}, "t"), "20:00")
        self.assertEqual(read({"t_hour": "", "t_minute": "", "t_period": "PM"}, {}, "t"), "")
        self.assertEqual(read({"t": "18:30"}, {}, "t"), "18:30")  # a plain value still works
        self.assertTrue(widget.value_omitted_from_data({}, {}, "t"))

    def test_invalid_12_hour_time_is_a_field_error(self):
        form = EventForm(data={"start_time_hour": "13", "start_time_minute": "00", "start_time_period": "PM"})
        form.is_valid()
        self.assertIn("start_time", form.errors)
