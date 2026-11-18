import io
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from core.event_import.categories import classify
from core.event_import.ics import parse_feed

FIXTURE = Path(__file__).parent / "fixtures" / "event_import.ics"
NOW = datetime(2026, 11, 17, tzinfo=timezone.utc)


def feed(properties):
    return ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\n"
            "UID:test\r\nSUMMARY:Test event\r\nLOCATION:Example Hall\r\n"
            "URL:https://example.test/event\r\n" + properties +
            "\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n").encode()


class EventImportTests(SimpleTestCase):
    def test_fixture_mapping_truncation_and_exact_duplicate_instants(self):
        result = parse_feed(FIXTURE.read_bytes(), "yale_connect", now=NOW)
        self.assertEqual(dict(result.counts), {"seen": 3, "prepared": 1,
                                              "duplicates": 1, "past_start": 1})
        event = result.events[0]
        self.assertEqual(event.external_id, "1001")
        self.assertEqual(event.category, "career_networking")
        self.assertEqual(len(event.name), 30)
        self.assertIsNone(event.price)
        self.assertEqual(event.location_text, "Example Hall, New Haven")

    def test_invalid_entry_does_not_discard_valid_events(self):
        bad = feed("DTSTART:invalid\r\nDTEND:invalid")
        bad_event = b"BEGIN:VEVENT" + bad.split(b"BEGIN:VEVENT", 1)[1]
        mixed = FIXTURE.read_bytes().replace(b"END:VCALENDAR", bad_event)
        result = parse_feed(mixed, "som", now=NOW)
        self.assertEqual(len(result.events), 1)
        self.assertEqual(result.counts["invalid_or_unsupported"], 1)

    def test_unsupported_times_and_end_order(self):
        for properties in (
            "DTSTART;VALUE=DATE:20261201\r\nDTEND;VALUE=DATE:20261202",
            "DTSTART:20261201T180000\r\nDTEND:20261201T190000",
            "DTSTART:20261201T230000Z",
            "DTSTART:20261201T230000Z\r\nDTEND:20261201T220000Z",
        ):
            with self.subTest(properties=properties):
                result = parse_feed(feed(properties), "som", now=NOW)
                self.assertEqual(result.counts["invalid_or_unsupported"], 1)
                self.assertEqual(result.events, [])

    def test_repeated_identity_with_changed_location_is_not_prepared_twice(self):
        original = feed("DTSTART:20261201T230000Z\r\nDTEND:20261202T000000Z")
        changed = original.replace(b"Example Hall", b"Another Hall")
        combined = original.replace(b"END:VCALENDAR", b"BEGIN:VEVENT" +
                                    changed.split(b"BEGIN:VEVENT", 1)[1])
        result = parse_feed(combined, "som", now=NOW)
        self.assertEqual(len(result.events), 1)
        self.assertEqual(result.counts["duplicates"], 1)

    def test_duration_uid_fallback_and_description_limit(self):
        result = parse_feed(feed("DTSTART:20261201T230000Z\r\nDURATION:PT1H\r\n"
                                 "DESCRIPTION:" + "x" * 200), "som", now=NOW)
        event = result.events[0]
        self.assertEqual(event.external_id, "test")
        self.assertEqual(len(event.description), 150)
        self.assertEqual((event.ends_at - event.starts_at).total_seconds(), 3600)

    def test_explicit_skip_reasons(self):
        times = "DTSTART:20261201T230000Z\r\nDTEND:20261202T000000Z\r\n"
        for extra, reason in (("STATUS:CANCELLED", "cancelled"),
                              ("RRULE:FREQ=WEEKLY", "unsupported_recurrence"),
                              ("CATEGORIES:Group Meeting", "not_discoverable")):
            with self.subTest(reason=reason):
                self.assertEqual(parse_feed(feed(times + extra), "som", now=NOW).counts[reason], 1)
        data = feed(times).replace(b"LOCATION:Example Hall", b"LOCATION:Online")
        self.assertEqual(parse_feed(data, "som", now=NOW).counts["no_physical_location"], 1)

    def test_cutoff_and_source_validation(self):
        result = parse_feed(FIXTURE.read_bytes(), "som", now=NOW,
                            until=datetime(2026, 12, 1, 23, tzinfo=timezone.utc))
        self.assertEqual(result.counts["outside_window"], 2)
        with self.assertRaises(ValueError):
            parse_feed(FIXTURE.read_bytes(), "unknown", now=NOW)
        with self.assertRaises(ValueError):
            parse_feed(FIXTURE.read_bytes(), "som", now=NOW.replace(tzinfo=None))

    def test_category_mapping_and_keyword_priority(self):
        self.assertEqual(classify(["Performance (event_type)"], ""),
                         ("music_performance", "mapping"))
        self.assertEqual(classify(["Tour"], "Museum tour"), ("art_film_exhibits", "keyword"))
        self.assertEqual(classify([], "prayer and dinner"), ("faith_spirituality", "keyword"))
        self.assertEqual(classify([], "Gather together"), ("social_community", "default"))

    def test_preview_command_is_offline_and_repeatable(self):
        outputs = []
        with patch("socket.socket", side_effect=AssertionError("Network forbidden")):
            for _ in range(2):
                output = io.StringIO()
                call_command("preview_event_import", str(FIXTURE), source="som",
                             now=NOW.isoformat(), stdout=output)
                outputs.append(json.loads(output.getvalue()))
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(outputs[0]["mode"], "preview_only")
        self.assertEqual(len(outputs[0]["events"]), 1)

    def test_command_rejects_invalid_input(self):
        with self.assertRaises(CommandError):
            call_command("preview_event_import", str(FIXTURE), source="som", now="invalid")
