"""Single-event .ics generation for "Save to calendar" (#32). Pure unit tests."""

from datetime import datetime, timezone as dt_timezone
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase
from icalendar import Calendar

from core.ics import build_ics, escape_text, fold_line

NEW_YORK = ZoneInfo("America/New_York")
NOW = datetime(2026, 11, 17, 12, 0, tzinfo=dt_timezone.utc)


def stand_in(**overrides):
    values = {
        "pk": 7,
        "name": "Jazz Night",
        "description": "Live trio, bring friends",
        "location": "Yale Commons, 168 Grove St, New Haven",
        "link": "https://example.com/jazz",
        "price": Decimal("0"),
        "start_at": datetime(2026, 11, 20, 19, 0, tzinfo=NEW_YORK),
        "end_at": datetime(2026, 11, 20, 21, 0, tzinfo=NEW_YORK),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class BuildIcsTests(SimpleTestCase):
    def test_contains_exactly_one_event_with_new_york_times(self):
        ics = build_ics(stand_in(), now=NOW)
        self.assertEqual(ics.count("BEGIN:VEVENT"), 1)
        self.assertEqual(ics.count("END:VEVENT"), 1)
        self.assertIn("DTSTART;TZID=America/New_York:20261120T190000\r\n", ics)
        self.assertIn("DTEND;TZID=America/New_York:20261120T210000\r\n", ics)
        self.assertIn("TZID:America/New_York\r\n", ics)
        self.assertIn("UID:event-7@yale-events\r\n", ics)
        self.assertIn("DTSTAMP:20261117T120000Z\r\n", ics)

    def test_utc_input_is_converted_to_new_york_in_summer(self):
        # 22:00 UTC on 10 July is 18:00 EDT (UTC-4).
        event = stand_in(
            start_at=datetime(2026, 7, 10, 22, 0, tzinfo=dt_timezone.utc),
            end_at=datetime(2026, 7, 10, 23, 30, tzinfo=dt_timezone.utc),
        )
        ics = build_ics(event, now=NOW)
        self.assertIn("DTSTART;TZID=America/New_York:20260710T180000", ics)
        self.assertIn("DTEND;TZID=America/New_York:20260710T193000", ics)

    def test_includes_name_description_location_and_link(self):
        ics = build_ics(stand_in(), now=NOW)
        self.assertIn("SUMMARY:Jazz Night\r\n", ics)
        self.assertIn("DESCRIPTION:Live trio\\, bring friends\\n\\nhttps://example.com/jazz", ics)
        self.assertIn("LOCATION:Yale Commons\\, 168 Grove St\\, New Haven\r\n", ics)
        self.assertIn("URL:https://example.com/jazz\r\n", ics)

    def test_every_line_ends_with_crlf_and_fits_75_octets(self):
        event = stand_in(description="Très long " * 30, name="Café; jazz, & more")
        ics = build_ics(event, now=NOW)
        self.assertTrue(ics.endswith("END:VCALENDAR\r\n"))
        self.assertNotIn("\n", ics.replace("\r\n", ""))
        for line in ics.split("\r\n"):
            self.assertLessEqual(len(line.encode("utf-8")), 75, line)

    def test_escape_text(self):
        self.assertEqual(escape_text("a\\b;c,d\r\ne"), "a\\\\b\\;c\\,d\\ne")

    def test_fold_line_never_splits_a_multibyte_character(self):
        folded = fold_line("DESCRIPTION:" + "é" * 80)
        for part in folded.split("\r\n"):
            part.encode("utf-8").decode("utf-8")
            self.assertLessEqual(len(part.encode("utf-8")), 75)
        self.assertEqual(folded.replace("\r\n ", ""), "DESCRIPTION:" + "é" * 80)


class IcsParserTests(SimpleTestCase):
    def test_icalendar_parser_reads_back_the_same_event(self):
        event = stand_in(description="Line one\nLine two; with, punctuation")
        calendar = Calendar.from_ical(build_ics(event, now=NOW))
        events = list(calendar.walk("VEVENT"))
        self.assertEqual(len(events), 1)
        parsed = events[0]
        self.assertEqual(parsed.decoded("DTSTART"), event.start_at)
        self.assertEqual(parsed.decoded("DTEND"), event.end_at)
        self.assertEqual(str(parsed["DTSTART"].dt.tzinfo), "America/New_York")
        self.assertEqual(str(parsed["SUMMARY"]), "Jazz Night")
        self.assertEqual(
            str(parsed["DESCRIPTION"]),
            "Line one\nLine two; with, punctuation\n\nhttps://example.com/jazz",
        )
        self.assertEqual(str(parsed["LOCATION"]), event.location)
        self.assertEqual(str(parsed["URL"]), event.link)
        self.assertEqual(len(list(calendar.walk("VTIMEZONE"))), 1)
