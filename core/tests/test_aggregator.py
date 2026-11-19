import io
import json
import time
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from core.event_import import enrichment, runner, sources
from core.event_import.ics import Preview, parse_feed
from core.models import Event, EventGeocodeCache, EventImportLock

NOW = datetime(2026, 11, 17, tzinfo=timezone.utc)
UNTIL = datetime(2027, 1, 1, tzinfo=timezone.utc)
FIXTURE = Path(__file__).parent / "fixtures" / "event_import.ics"
COORDS = {"latitude": "41.308300", "longitude": "-72.927900", "city": "New Haven", "state": "CT"}


class AggregatorTests(TestCase):
    def setUp(self):
        self.candidate = parse_feed(FIXTURE.read_bytes(), "som", now=NOW).events[0]
        self.network = mock.patch("socket.socket", side_effect=AssertionError("Unexpected network call"))
        self.network.start()
        self.addCleanup(self.network.stop)

    def run_batch(self, events=None, **kwargs):
        with mock.patch.object(runner, "source_batches", return_value=iter([Preview(events or [self.candidate])])), \
                mock.patch.object(enrichment, "locate", return_value=COORDS), \
                mock.patch.object(runner.timezone, "now", return_value=NOW):
            token = runner.acquire_lock()
            return runner.run_import(token, sources=["som"], until=UNTIL, **kwargs)

    @override_settings(AGGREGATOR_TOKEN="test-token")
    def test_endpoint_auth_and_fast_background_acceptance(self):
        with mock.patch("core.event_import.views.Thread") as thread:
            for header in ("", "Bearer wrong", "Bearer test-token-extra"):
                response = self.client.post(reverse("trigger_event_import"), HTTP_AUTHORIZATION=header)
                self.assertEqual(response.status_code, 403)
            thread.assert_not_called()
            self.assertFalse(EventImportLock.objects.exists())
            started = time.monotonic()
            response = self.client.post(reverse("trigger_event_import"), HTTP_AUTHORIZATION="Bearer test-token")
            self.assertEqual(response.status_code, 202)
            self.assertLess(time.monotonic() - started, 2)
            thread.return_value.start.assert_called_once()
            response = self.client.post(reverse("trigger_event_import"), HTTP_AUTHORIZATION="Bearer test-token")
            self.assertEqual(response.json()["status"], "already_running")
            thread.return_value.start.assert_called_once()

    @override_settings(AGGREGATOR_TOKEN="")
    def test_unconfigured_endpoint_fails_closed(self):
        self.assertEqual(self.client.post(reverse("trigger_event_import")).status_code, 403)
        self.assertEqual(self.client.get(reverse("trigger_event_import")).status_code, 405)

    @override_settings(AGGREGATOR_TOKEN="test-token")
    def test_thread_start_failure_releases_lock(self):
        with mock.patch("core.event_import.views.Thread") as thread:
            thread.return_value.start.side_effect = RuntimeError()
            response = self.client.post(reverse("trigger_event_import"), HTTP_AUTHORIZATION="Bearer test-token")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(EventImportLock.objects.get().token, "")

    def test_lock_rejects_overlap_and_wrong_owner_release(self):
        token = runner.acquire_lock()
        self.assertIsNone(runner.acquire_lock())
        self.assertEqual(runner.release_lock("wrong"), 0)
        self.assertEqual(runner.release_lock(token), 1)
        self.assertIsNotNone(runner.acquire_lock())

    def test_source_failure_does_not_stop_next_source_and_logs_counts(self):
        def batches(source, **kwargs):
            if source == "yale_connect":
                raise TimeoutError("secret-url-should-not-be-logged")
            return [Preview([self.candidate])]
        with mock.patch.object(runner, "source_batches", side_effect=batches), \
                mock.patch.object(enrichment, "locate", return_value=COORDS), \
                mock.patch.object(runner.timezone, "now", return_value=NOW), \
                self.assertLogs("core.event_import.runner", level="INFO") as logs:
            result = runner.run_import(runner.acquire_lock(), sources=["yale_connect", "som"], until=UNTIL)
        self.assertEqual(result["imported"], 1)
        self.assertEqual(result["sources_failed"], 1)
        self.assertEqual(EventImportLock.objects.get().token, "")
        self.assertIn("event_import end", " ".join(logs.output))
        self.assertNotIn("secret-url", " ".join(logs.output))

    @override_settings(AGGREGATOR_MAX_IMAGES_PER_RUN=1)
    def test_image_cap_and_second_run_no_paid_calls(self):
        second = replace(self.candidate, external_id="second", location_text="Another hall")
        with mock.patch.object(enrichment, "generate_event_image") as generate:
            result = self.run_batch([self.candidate, second])
            self.assertEqual(result["imported"], 2)
            self.assertEqual(result["images_generated"], 1)
            generate.assert_called_once()
            result = self.run_batch([self.candidate, second])
            self.assertEqual(result["already_imported"], 2)
            generate.assert_called_once()
        self.assertEqual(Event.objects.filter(image="").count(), 2)

    @override_settings(AGGREGATOR_MAX_IMAGES_PER_RUN=1)
    def test_image_failure_keeps_import_and_consumes_cap(self):
        second = replace(self.candidate, external_id="second", location_text="Another hall")
        with mock.patch.object(enrichment, "generate_event_image", side_effect=ValueError()) as generate:
            result = self.run_batch([self.candidate, second])
        self.assertEqual(result["imported"], 2)
        self.assertEqual(result["image_failed"], 1)
        generate.assert_called_once()
        self.assertEqual(Event.objects.filter(image="").count(), 2)

    @override_settings(AGGREGATOR_MAX_IMAGES_PER_RUN=0, AGGREGATOR_MAX_CLASSIFICATIONS_PER_RUN=0)
    def test_default_budget_makes_no_ai_calls(self):
        with mock.patch.object(enrichment, "ai_category") as classify, \
                mock.patch.object(enrichment, "generate_event_image") as image:
            self.run_batch([replace(self.candidate, category_source="default")])
        classify.assert_not_called()
        image.assert_not_called()

    @override_settings(AGGREGATOR_MAX_CLASSIFICATIONS_PER_RUN=1)
    def test_llm_fallback_only_for_unmatched_events_and_is_capped(self):
        events = [replace(self.candidate, category_source="default"),
                  replace(self.candidate, external_id="second", location_text="Other", category_source="default")]
        with mock.patch.object(enrichment, "ai_category", return_value="talks_panels") as classify:
            self.run_batch(events)
        classify.assert_called_once()
        self.assertEqual(Event.objects.get(external_id=self.candidate.external_id).category, "talks_panels")

    def test_geocoding_cache_and_negative_result(self):
        suggestion = {"address": "Example Hall, New Haven, Connecticut, United States",
                      "latitude": 41.3083, "longitude": -72.9279}
        with mock.patch("core.geocoding.search", return_value=[suggestion]) as search:
            self.assertEqual(enrichment.locate(self.candidate), COORDS)
            self.assertEqual(enrichment.locate(self.candidate), COORDS)
            search.assert_called_once()
        with mock.patch("core.geocoding.search", return_value=[]) as search:
            other = replace(self.candidate, location_text="Unknown hall")
            self.assertIsNone(enrichment.locate(other))
            self.assertIsNone(enrichment.locate(other))
            search.assert_called_once()
        self.assertEqual(EventGeocodeCache.objects.count(), 2)

    def test_wrong_locality_and_invalid_coordinates_are_rejected(self):
        self.assertIsNone(enrichment.verified_coordinates("41.3", "-72.9", "Boston", "MA"))
        self.assertIsNone(enrichment.verified_coordinates("0", "0", "New Haven", "CT"))
        self.assertIsNone(enrichment.verified_coordinates("NaN", "-72.9", "New Haven", "CT"))

    def test_campus_room_prefix_falls_back_to_supplied_street_address(self):
        candidate = replace(self.candidate, location_text="Kroon Hall, Burke Auditorium, 165 Whitney Avenue, New Haven, CT 06511, United States")
        suggestion = {"address": "165 Whitney Avenue, New Haven, Connecticut",
                      "latitude": 41.3083, "longitude": -72.9279}
        with mock.patch("core.geocoding.search", side_effect=[[], [suggestion]]) as search:
            self.assertEqual(enrichment.locate(candidate), COORDS)
        self.assertEqual(search.call_args_list[1].args[0], "165 Whitney Avenue, New Haven, CT 06511, United States")

    def test_fallback_does_not_relocate_an_out_of_town_event(self):
        candidate = replace(self.candidate, location_text="Ohiri Field, 95 N Harvard St, Boston, MA 02134")
        with mock.patch("core.geocoding.search", return_value=[]) as search:
            self.assertIsNone(enrichment.locate(candidate))
        search.assert_called_once()

    @override_settings(TICKETMASTER_API_KEY="")
    def test_missing_ticketmaster_key_keeps_both_open_feeds_and_per_source_limit(self):
        def batches(source, **kwargs):
            return [Preview([replace(self.candidate, source=source, external_id=f"{source}-{i}",
                                     location_text=f"{source} hall {i}") for i in range(3)])]
        with mock.patch.object(runner, "source_batches", side_effect=batches) as fetch, \
                mock.patch.object(enrichment, "locate", return_value=COORDS), \
                mock.patch.object(runner.timezone, "now", return_value=NOW):
            result = runner.run_import(runner.acquire_lock(), until=UNTIL, limit_per_source=1)
        self.assertEqual(result["imported"], 2)
        self.assertEqual(result["unconfigured_sources"], 1)
        self.assertEqual([call.args[0] for call in fetch.call_args_list], ["yale_connect", "som"])
        self.assertEqual(set(Event.objects.values_list("source", flat=True)), {"yale_connect", "som"})

    def test_hidden_and_online_locations_are_not_geocoded(self):
        for location in ("Online Event", "Sign in to download the location", "-"):
            data = FIXTURE.read_bytes().replace(b"Example Hall\\, New Haven", location.encode())
            data = data.replace(b"Example Hall", location.encode())
            batch = parse_feed(data, "som", now=NOW)
            self.assertEqual(batch.events, [])
            self.assertEqual(batch.counts["no_physical_location"], 2)

    def test_ai_category_validates_response(self):
        with mock.patch("core.llm.chat", return_value='{"category":"made_up"}'):
            with self.assertRaises(ValueError):
                enrichment.ai_category(self.candidate)

    def test_image_generation_reuses_validation_and_storage(self):
        from PIL import Image
        output = io.BytesIO()
        Image.new("RGB", (2, 2)).save(output, format="PNG")
        self.run_batch()
        event = Event.objects.get()
        with mock.patch("core.llm.generate_image", return_value=(output.getvalue(), "image/png")), \
                mock.patch("core.photo_storage.upload") as upload:
            enrichment.generate_event_image(event)
        event.refresh_from_db()
        self.assertTrue(event.image.startswith("events/imported/"))
        upload.assert_called_once()

    def test_unknown_price_and_source_display(self):
        self.run_batch()
        user = get_user_model().objects.create_user(username="viewer@yale.edu")
        self.client.force_login(user)
        event = Event.objects.get()
        response = self.client.get(reverse("event_detail", args=[event.pk]))
        self.assertContains(response, "Price not listed")
        self.assertContains(response, "Yale SOM")
        self.assertContains(response, "Image unavailable")
        with mock.patch("core.views.timezone.now", return_value=NOW):
            response = self.client.get("/map/")
        self.assertEqual(response.context["map_config"]["events"][0]["price"], "Price not listed")

    def test_deadline_releases_lock_without_fetching(self):
        with mock.patch.object(runner.time, "monotonic", side_effect=[0, 1000]), \
                mock.patch.object(runner, "source_batches") as fetch:
            result = runner.run_import(runner.acquire_lock(), sources=["som"], until=UNTIL)
        fetch.assert_not_called()
        self.assertEqual(result["deadline_reached"], 1)
        self.assertEqual(EventImportLock.objects.get().token, "")

    def test_initial_population_command_uses_shared_runner(self):
        from django.core.management import call_command
        with mock.patch.object(runner, "source_batches", return_value=[Preview([self.candidate])]), \
                mock.patch.object(enrichment, "locate", return_value=COORDS), \
                mock.patch.object(runner.timezone, "now", return_value=NOW):
            for _ in range(2):
                call_command("import_events", source=["som"], until=UNTIL.isoformat(), stdout=io.StringIO())
        self.assertEqual(Event.objects.count(), 1)

    def test_tomorrow_command_imports_only_starts_within_local_day(self):
        from django.core.management import call_command
        # NOW is Nov 16 at 7 PM Eastern; tomorrow starts at Nov 17 05:00 UTC.
        lower = datetime(2026, 11, 17, 5, tzinfo=timezone.utc)
        upper = lower + timedelta(days=1)
        events = [replace(self.candidate, external_id=str(i), location_text=f"Hall {i}",
                          starts_at=start, ends_at=start + timedelta(hours=1))
                  for i, start in enumerate([lower - timedelta(seconds=1), lower,
                                             upper - timedelta(seconds=1), upper])]
        with mock.patch.object(runner, "source_batches", return_value=[Preview(events)]), \
                mock.patch.object(enrichment, "locate", return_value=COORDS) as locate, \
                mock.patch.object(runner.timezone, "now", return_value=NOW):
            call_command("import_events", source=["som"], tomorrow=True, stdout=io.StringIO())
        self.assertEqual(set(Event.objects.values_list("external_id", flat=True)), {"1", "2"})
        self.assertEqual(locate.call_count, 2)

    def test_tomorrow_handles_daylight_saving_time_boundaries(self):
        from django.core.management import call_command
        for now, hours in [(datetime(2026, 3, 7, 17, tzinfo=timezone.utc), 23),
                           (datetime(2026, 10, 31, 17, tzinfo=timezone.utc), 25)]:
            with self.subTest(hours=hours), \
                    mock.patch.object(runner.timezone, "now", return_value=now), \
                    mock.patch("core.management.commands.import_events.acquire_lock", return_value="test"), \
                    mock.patch("core.management.commands.import_events.run_import", return_value={}) as run:
                call_command("import_events", tomorrow=True, stdout=io.StringIO())
                options = run.call_args.kwargs
                duration = options["until"].astimezone(timezone.utc) - options["starts_from"].astimezone(timezone.utc)
                self.assertEqual(duration, timedelta(hours=hours))
                self.assertIsNone(options["limit_per_source"])

    def test_tomorrow_rejects_conflicting_cutoff_before_acquiring_lock(self):
        from django.core.management import call_command, CommandError
        with self.assertRaisesMessage(CommandError, "Use either --tomorrow or --until"):
            call_command("import_events", tomorrow=True, until=UNTIL.isoformat())
        self.assertFalse(EventImportLock.objects.exists())


class SourceTests(TestCase):
    def test_ics_fetch_and_parse(self):
        with mock.patch.object(sources, "fetch", return_value=FIXTURE.read_bytes()):
            batches = list(sources.source_batches("som", now=NOW, until=UNTIL, deadline=time.monotonic()+10))
        self.assertEqual(len(batches[0].events), 1)

    def test_disallowed_urls_and_redirects(self):
        for url in ("http://yaleconnect.yale.edu/a", "https://localhost/a", "https://user@yaleconnect.yale.edu/a"):
            with self.assertRaises(ValueError):
                sources.validate_url(url)

    def test_oversized_feed(self):
        with mock.patch.object(sources, "build_opener") as opener, mock.patch.object(sources, "MAX_BYTES", 10):
            opener.return_value.open.return_value.__enter__.return_value.read1.return_value = b"x" * 11
            with self.assertRaises(ValueError):
                sources.fetch("https://yaleconnect.yale.edu/feed", time.monotonic()+10)

    def ticketmaster_payload(self):
        return json.loads((FIXTURE.parent / "ticketmaster.json").read_text())

    def test_ticketmaster_mapping_and_missing_end(self):
        data = self.ticketmaster_payload()
        result = sources.parse_ticketmaster(data, now=NOW, until=UNTIL)
        self.assertEqual(len(result.events), 1)
        self.assertEqual(result.events[0].category, "music_performance")
        self.assertEqual(result.events[0].price, 0)
        del data["_embedded"]["events"][0]["dates"]["end"]
        result = sources.parse_ticketmaster(data, now=NOW, until=UNTIL)
        self.assertEqual(result.counts["invalid_or_unsupported"], 1)

    @override_settings(TICKETMASTER_API_KEY="fake")
    def test_ticketmaster_pagination(self):
        data = self.ticketmaster_payload()
        data["page"] = {"totalPages": 2}
        with mock.patch.object(sources, "fetch", return_value=json.dumps(data).encode()) as fetch, \
                mock.patch.object(sources.time, "sleep"):
            self.assertEqual(len(list(sources.source_batches("ticketmaster", now=NOW, until=UNTIL,
                                                           deadline=time.monotonic()+20))), 2)
        self.assertIn("page=1", fetch.call_args.args[0])
