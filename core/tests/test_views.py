from unittest import mock

from django.db import OperationalError
from django.test import TestCase, override_settings


class HomeViewTests(TestCase):
    @override_settings(APP_ENV="staging")
    def test_home_is_public_and_shows_environment(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Environment: staging")


class HealthzViewTests(TestCase):
    def test_healthz_reports_ok_when_database_reachable(self):
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "database": "ok"})

    def test_healthz_returns_503_when_database_unreachable(self):
        with mock.patch("core.views.connection.cursor", side_effect=OperationalError("down")):
            with self.assertLogs("core.views", level="ERROR"):
                response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "error", "database": "unreachable"})
