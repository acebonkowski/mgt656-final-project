from unittest import mock

from django.db import OperationalError
from django.test import TestCase, override_settings


class HomeViewTests(TestCase):
    def test_root_sends_visitors_to_the_welcome_screen(self):
        self.assertRedirects(self.client.get("/"), "/login/")

    @override_settings(APP_ENV="staging")
    def test_welcome_screen_is_public_and_hides_environment(self):
        # #79: the environment line was removed from the login page.
        response = self.client.get("/login/")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Environment:")


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
