import runpy
from dataclasses import replace
from unittest import mock

from django.conf import settings
from django.db import OperationalError
from django.test import SimpleTestCase, TestCase, override_settings

from core.event_import import runner, startup
from core.event_import.ics import Preview, parse_feed
from core.models import Event, EventImportLock
from core.tests.test_aggregator import COORDS, FIXTURE, NOW


class StartupTriggerTests(SimpleTestCase):
    @override_settings(AGGREGATOR_IMPORT_ON_STARTUP=False, MAP_API_KEY="test")
    def test_disabled_does_not_start_work(self):
        with mock.patch.object(startup, "Thread") as thread:
            startup.start_import_on_startup()
        thread.assert_not_called()

    @override_settings(AGGREGATOR_IMPORT_ON_STARTUP=True, MAP_API_KEY="test")
    def test_enabled_starts_background_work_without_waiting_for_database(self):
        with mock.patch.object(startup, "Thread") as thread, \
                mock.patch.object(startup, "acquire_lock") as acquire:
            startup.start_import_on_startup()
        thread.assert_called_once_with(target=startup.background_startup_import,
                                       daemon=True, name="startup-event-import")
        thread.return_value.start.assert_called_once()
        acquire.assert_not_called()

    @override_settings(AGGREGATOR_IMPORT_ON_STARTUP=True, MAP_API_KEY="", TICKETMASTER_API_KEY="")
    def test_missing_keys_skip_import_with_actionable_log(self):
        with mock.patch.object(startup, "Thread") as thread, \
                self.assertLogs(startup.logger, level="WARNING") as logs:
            startup.start_import_on_startup()
        thread.assert_not_called()
        self.assertIn("skipped=no_provider_keys", " ".join(logs.output))

    @override_settings(AGGREGATOR_IMPORT_ON_STARTUP=True, MAP_API_KEY="test")
    def test_thread_failure_does_not_block_serving_or_acquire_lock(self):
        with mock.patch.object(startup, "Thread") as thread, \
                mock.patch.object(startup, "acquire_lock") as acquire, \
                self.assertLogs(startup.logger, level="ERROR"):
            thread.return_value.start.side_effect = RuntimeError("private diagnostic")
            startup.start_import_on_startup()
        acquire.assert_not_called()

    def test_wsgi_initializes_django_before_startup_hook(self):
        calls = []
        with mock.patch("django.core.wsgi.get_wsgi_application", side_effect=lambda: calls.append("django")), \
                mock.patch.object(startup, "start_import_on_startup", side_effect=lambda: calls.append("import")):
            runpy.run_path(str(settings.BASE_DIR / "config" / "wsgi.py"))
        self.assertEqual(calls, ["django", "import"])

    def test_database_failure_is_logged_without_crashing_server(self):
        with mock.patch.object(startup, "close_old_connections"), \
                mock.patch.object(startup, "acquire_lock", side_effect=OperationalError("secret connection string")), \
                self.assertLogs(startup.logger, level="ERROR") as logs:
            startup.background_startup_import()
        self.assertIn("type=OperationalError", " ".join(logs.output))
        self.assertNotIn("secret connection string", " ".join(logs.output))


class StartupImportTests(TestCase):
    def test_busy_lock_prevents_second_worker_or_scheduled_import(self):
        token = runner.acquire_lock()
        with mock.patch.object(startup, "close_old_connections"), \
                mock.patch.object(startup, "run_import") as run:
            startup.background_startup_import()
        run.assert_not_called()
        self.assertEqual(EventImportLock.objects.get().token, token)

    @override_settings(AGGREGATOR_MAX_IMAGES_PER_RUN=0, AGGREGATOR_MAX_CLASSIFICATIONS_PER_RUN=0,
                       TICKETMASTER_API_KEY="")
    def test_startup_uses_week_window_and_is_idempotent(self):
        candidate = parse_feed(FIXTURE.read_bytes(), "som", now=NOW).events[0]
        candidate = replace(candidate, starts_at=NOW + runner.timedelta(days=2),
                            ends_at=NOW + runner.timedelta(days=2, hours=1))
        with mock.patch("socket.socket", side_effect=AssertionError("Unexpected network")), \
                mock.patch.object(startup, "close_old_connections"), \
                mock.patch.object(runner.timezone, "now", return_value=NOW), \
                mock.patch.object(runner, "source_batches", side_effect=lambda source, **kw: [Preview([candidate])] if source == "som" else []), \
                mock.patch.object(runner.enrichment, "locate", return_value=COORDS) as locate, \
                mock.patch.object(startup, "run_import", wraps=runner.run_import) as run:
            startup.background_startup_import()
            startup.background_startup_import()
        self.assertEqual(Event.objects.count(), 1)
        self.assertEqual(EventImportLock.objects.get().token, "")
        locate.assert_called_once()
        options = run.call_args.kwargs
        self.assertEqual(options["starts_from"].hour, 0)
        self.assertEqual(options["until"] - options["starts_from"], runner.timedelta(days=7))
