"""
Map home screen (#8).

No test talks to a real map service: Django's test client does not run browser
JavaScript, and every key used here is fake.
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.shortcuts import resolve_url
from django.test import TestCase, override_settings

FAKE_KEY = "fake-test-key"
FALLBACK_TEXT = "The map isn't available right now."


class MapAccessTests(TestCase):
    def test_logged_out_user_is_redirected_to_login(self):
        response = self.client.get("/map/")
        self.assertRedirects(
            response, f"{settings.LOGIN_URL}?next=/map/", fetch_redirect_response=False
        )

    def test_login_redirect_and_onboarding_success_point_to_map(self):
        self.assertEqual(resolve_url(settings.LOGIN_REDIRECT_URL), "/map/")
        self.assertEqual(resolve_url(settings.ONBOARDING_SUCCESS_URL), "/map/")

    def test_logging_in_from_the_map_lands_back_on_the_map(self):
        # Uses the temporary admin login (staff only) until #6 adds the real one.
        get_user_model().objects.create_user(
            username="student", password="not-a-real-password-123", is_staff=True
        )
        response = self.client.post(
            f"{settings.LOGIN_URL}?next=/map/",
            {"username": "student", "password": "not-a-real-password-123", "next": "/map/"},
        )
        self.assertRedirects(response, "/map/", fetch_redirect_response=False)


@override_settings(MAP_API_KEY=FAKE_KEY)
class MapScreenWithKeyTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="student", password="x")
        self.client.force_login(user)

    def test_shows_headline_and_map_centred_on_new_haven(self):
        response = self.client.get("/map/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/map.html")
        self.assertContains(response, "More coming soon.")
        self.assertContains(response, 'id="map"')
        self.assertEqual(response.context["map_config"]["center"], [41.3083, -72.9279])
        self.assertContains(response, "41.3083")
        self.assertContains(response, "-72.9279")

    def test_key_comes_from_settings_and_fallback_is_hidden(self):
        response = self.client.get("/map/")
        self.assertEqual(response.context["map_config"]["apiKey"], FAKE_KEY)
        self.assertTrue(response.context["map_enabled"])
        self.assertContains(response, 'id="map-config"')
        self.assertContains(response, FAKE_KEY)
        self.assertContains(response, 'role="status" hidden>')

    def test_page_is_mobile_friendly(self):
        response = self.client.get("/map/")
        self.assertContains(response, 'name="viewport"')
        self.assertContains(response, "core/map.css")


@override_settings(MAP_API_KEY="")
class MapScreenWithoutKeyTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="student", password="x")
        self.client.force_login(user)

    def test_missing_key_shows_fallback_and_logs_warning(self):
        with self.assertLogs("core.views", level="WARNING") as logs:
            response = self.client.get("/map/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "More coming soon.")
        self.assertContains(response, FALLBACK_TEXT)
        self.assertNotContains(response, 'role="status" hidden>')
        self.assertFalse(response.context["map_enabled"])
        self.assertIn("MAP_API_KEY is not set", logs.output[0])
