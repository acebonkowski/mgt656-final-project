import io
import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.core.management import call_command
from django.test import TestCase

from core.event_import.ics import parse_feed
from core.event_import.persistence import persist_candidates
from core.models import Event

FIXTURE = Path(__file__).parent / "fixtures" / "event_import.ics"
NOW = datetime(2026, 11, 17, tzinfo=timezone.utc)
EXTRA = {"1001": {"price": "0.00", "latitude": "41.308300",
                  "longitude": "-72.927900", "city": "New Haven", "state": "CT"}}


class ImportPersistenceTests(TestCase):
    def setUp(self):
        self.events = parse_feed(FIXTURE.read_bytes(), "som", now=NOW).events

    def run_import(self, events=None, extra=None):
        with patch("socket.socket", side_effect=AssertionError("Network forbidden")):
            return persist_candidates(self.events if events is None else events,
                                      EXTRA if extra is None else extra, now=NOW)

    def test_mapping_and_second_run_are_idempotent(self):
        self.assertEqual(self.run_import(), {"imported": 1})
        self.assertEqual(self.run_import(), {"already_imported": 1})
        event = Event.objects.get()
        self.assertEqual(event.start_at, self.events[0].starts_at)
        self.assertEqual(event.location, self.events[0].location_text)
        self.assertEqual(event.source, "som")
        self.assertEqual(event.price, 0)
        self.assertIsNone(event.creator)
        self.assertEqual(event.image, "")
        self.assertLessEqual(len(event.name), 30)
        self.assertLessEqual(len(event.description), 150)
        self.assertIn(event.category, Event.Category.values)
        self.assertIsNotNone(event.latitude)
        self.assertIsNotNone(event.longitude)
        self.assertEqual(event.link, self.events[0].link)

    def test_imported_event_disappears_from_map_at_end_time(self):
        self.run_import()
        event = Event.objects.get()
        user = get_user_model().objects.create_user(username="import-viewer@yale.edu")
        self.client.force_login(user)
        with patch("core.views.timezone.now", return_value=NOW):
            response = self.client.get("/map/")
            self.assertEqual(response.status_code, 200)
            self.assertIn(event.pk, [row["id"] for row in response.context["map_config"]["events"]])
        with patch("core.views.timezone.now", return_value=event.end_at):
            response = self.client.get("/map/")
            self.assertEqual(response.status_code, 200)
            self.assertNotIn(event.pk, [row["id"] for row in response.context["map_config"]["events"]])
        self.assertTrue(Event.objects.filter(pk=event.pk).exists())

    def test_exact_collision_with_user_event_is_rejected(self):
        self.run_import()
        Event.objects.update(source="", external_id="")
        self.assertEqual(self.run_import(), {"duplicates": 1})
        self.assertEqual(Event.objects.count(), 1)

    def test_cross_source_collision_is_rejected(self):
        self.run_import()
        self.assertEqual(self.run_import([replace(self.events[0], source="yale_connect")]),
                         {"duplicates": 1})

    def test_unknown_price_is_not_free_and_location_must_be_verified(self):
        self.assertEqual(self.run_import(extra={}), {"unknown_price": 1})
        wrong_city = {"1001": dict(EXTRA["1001"], city="Boston")}
        self.assertEqual(self.run_import(extra=wrong_city), {"unverified_location": 1})
        self.assertFalse(Event.objects.exists())

    def test_invalid_enrichment_and_expiry(self):
        for field, value in (("latitude", "nan"), ("longitude", "200"), ("price", "-1"),
                             ("price", "not a number")):
            with self.subTest(field=field, value=value):
                self.assertEqual(self.run_import(extra={"1001": dict(EXTRA["1001"], **{field: value})}),
                                 {"invalid_enrichment": 1})
        expired = replace(self.events[0], ends_at=NOW)
        self.assertEqual(self.run_import([expired]), {"expired": 1})
        self.assertFalse(Event.objects.exists())

    def test_database_enforces_source_identity(self):
        self.run_import()
        event = Event.objects.get()
        event.pk = None
        with self.assertRaises(IntegrityError), transaction.atomic():
            event.save(force_insert=True)
        self.assertEqual(Event.objects.count(), 1)

    def test_bad_record_does_not_prevent_next_import(self):
        bad = replace(self.events[0], category="invalid", external_id="bad")
        extra = dict(EXTRA, bad=EXTRA["1001"])
        self.assertEqual(self.run_import([bad, self.events[0]], extra),
                         {"invalid_enrichment": 1, "imported": 1})

    def test_command_dry_run_then_import(self):
        with patch("pathlib.Path.read_text", return_value=json.dumps(EXTRA)), \
                patch("core.management.commands.import_saved_events.timezone.now", return_value=NOW):
            output = io.StringIO()
            call_command("import_saved_events", str(FIXTURE), source="som",
                         enrichment=Path("verified.json"), dry_run=True, stdout=output)
            self.assertFalse(Event.objects.exists())
            self.assertTrue(json.loads(output.getvalue())["dry_run"])
            call_command("import_saved_events", str(FIXTURE), source="som",
                         enrichment=Path("verified.json"), stdout=io.StringIO())
            self.assertEqual(Event.objects.count(), 1)
