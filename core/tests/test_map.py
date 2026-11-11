"""
Map home screen (#8).

No test talks to MapTiler or the MapLibre CDN: Django's test client does not
run browser JavaScript, every key used here is fake, and NoNetworkTests fails
if rendering the page opens any network connection.
"""

import re
import socket
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.core import mail
from django.shortcuts import resolve_url
from django.test import TestCase, override_settings

from accounts.models import Profile

FAKE_KEY = "fake-test-key"
FALLBACK_TEXT = "The map isn't available right now."
MAPLIBRE_JS = "https://unpkg.com/maplibre-gl@5.24.0/dist/maplibre-gl.js"
MAPLIBRE_CSS = "https://unpkg.com/maplibre-gl@5.24.0/dist/maplibre-gl.css"


class MapAccessTests(TestCase):
    def test_logged_out_user_is_redirected_to_login(self):
        response = self.client.get("/map/")
        self.assertRedirects(
            response, f"{resolve_url(settings.LOGIN_URL)}?next=/map/", fetch_redirect_response=False
        )

    def test_login_redirect_and_onboarding_success_point_to_map(self):
        self.assertEqual(resolve_url(settings.LOGIN_REDIRECT_URL), "/map/")
        self.assertEqual(resolve_url(settings.ONBOARDING_SUCCESS_URL), "/map/")

    @override_settings(EMAIL_DELIVERY_ENABLED=True)
    def test_logging_in_from_the_map_lands_back_on_the_map(self):
        # The login story (#6) replaced the temporary admin password login.
        user = get_user_model().objects.create_user(username="student@yale.edu")
        Profile.objects.create(user=user, onboarding_complete=True)
        self.client.get(f"{resolve_url(settings.LOGIN_URL)}?next=/map/")
        self.client.post("/login/", {"email": "student@yale.edu"})
        code = re.search(r"\b(\d{6})\b", mail.outbox[-1].body).group(1)
        response = self.client.post("/login/code/", {"code": code})
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

    def test_includes_pinned_maplibre_and_maptiler_provider(self):
        response = self.client.get("/map/")
        self.assertTemplateUsed(response, "core/_map_provider.html")
        self.assertContains(response, f'src="{MAPLIBRE_JS}"')
        self.assertContains(response, f'href="{MAPLIBRE_CSS}"')
        self.assertContains(response, 'integrity="sha384-', count=2)
        self.assertContains(response, "core/map_provider.js")
        # The provider must load before the neutral loader that calls it.
        html = response.content.decode()
        self.assertLess(html.index("core/map_provider.js"), html.index("core/map.js"))

    def test_sends_origin_so_maptiler_domain_restriction_works(self):
        response = self.client.get("/map/")
        self.assertContains(
            response, '<meta name="referrer" content="strict-origin-when-cross-origin">'
        )


class MapProviderScriptTests(TestCase):
    def test_provider_uses_maptiler_dark_style_and_key_from_config(self):
        path = finders.find("core/map_provider.js")
        self.assertIsNotNone(path)
        with open(path, encoding="utf-8") as f:
            source = f.read()
        self.assertIn("window.renderMap", source)
        self.assertIn("https://api.maptiler.com/maps/", source)
        self.assertIn('"dataviz-dark"', source)
        self.assertIn("config.apiKey", source)  # never a hard-coded key
        self.assertIn("window.showMapFallback", source)

    def test_map_container_rule_outranks_maplibre_position_relative(self):
        # Regression: MapLibre's .maplibregl-map { position: relative } loads after
        # map.css, so a single-class .map rule lost and the map was 0px tall.
        path = finders.find("core/map.css")
        with open(path, encoding="utf-8") as f:
            css = f.read()
        rule = css.split(".map-screen .map {", 1)[1].split("}", 1)[0]
        self.assertIn("position: absolute;", rule)
        self.assertIn("height: 100%;", rule)
        self.assertIn("width: 100%;", rule)


@override_settings(MAP_API_KEY=FAKE_KEY)
class NoNetworkTests(TestCase):
    def test_rendering_the_map_makes_no_network_calls(self):
        user = get_user_model().objects.create_user(username="student", password="x")
        self.client.force_login(user)
        with mock.patch.object(
            socket.socket, "connect", side_effect=AssertionError("network call attempted")
        ) as connect:
            response = self.client.get("/map/")
        self.assertEqual(response.status_code, 200)
        connect.assert_not_called()


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

    def test_missing_key_does_not_load_the_map_provider(self):
        with self.assertLogs("core.views", level="WARNING"):
            response = self.client.get("/map/")
        self.assertNotContains(response, "maplibre-gl")
        self.assertNotContains(response, "core/map_provider.js")
        self.assertContains(response, "core/map.js")
