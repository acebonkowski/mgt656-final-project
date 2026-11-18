"""
Map home screen (#8).

No test contacts MapTiler or the MapLibre CDN: MapLibre assets and basemap tiles
are served locally, and NoNetworkTests fails if rendering the page opens a
network connection.
"""

import re
import gzip
import sqlite3
import socket
import tempfile
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.core import mail
from django.shortcuts import resolve_url
from django.test import TestCase, override_settings
from django.utils import timezone
from decimal import Decimal
from zoneinfo import ZoneInfo
from base64 import b64decode
from unittest import mock
from datetime import datetime
from django.core.files.uploadedfile import SimpleUploadedFile

from accounts.models import Profile
from core.models import Event
from core.map_places import YALE_AREA_PLACES

FAKE_KEY = "fake-test-key"
FALLBACK_TEXT = "The map isn't available right now."


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


class MapScreenTests(TestCase):
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
        self.assertEqual(
            response.context["map_config"]["bounds"],
            [-72.99, 41.26, -72.86, 41.36],
        )
        self.assertContains(response, "41.3083")
        self.assertContains(response, "-72.9279")
        places = response.context["map_config"]["places"]
        self.assertEqual(places, YALE_AREA_PLACES)
        self.assertTrue(any("Yale School of Management" in place["name"] for place in places))
        self.assertEqual(
            {place["kind"] for place in places},
            {"yale", "restaurant", "bar"},
        )

    def test_local_tiles_enable_map_without_a_provider_key(self):
        response = self.client.get("/map/")
        self.assertTrue(response.context["map_enabled"])
        self.assertNotIn("apiKey", response.context["map_config"])
        self.assertEqual(
            response.context["map_config"]["tileUrl"],
            "/map/tiles/{z}/{x}/{y}.pbf",
        )
        self.assertContains(response, 'id="map-config"')
        self.assertContains(response, 'role="status" hidden>')

    def test_page_is_mobile_friendly(self):
        response = self.client.get("/map/")
        self.assertContains(response, 'name="viewport"')
        self.assertContains(response, "core/map.css")

    def test_includes_local_maplibre_assets_and_provider(self):
        response = self.client.get("/map/")
        self.assertTemplateUsed(response, "core/_map_provider.html")
        self.assertContains(response, "/static/core/vendor/maplibre-gl.js")
        self.assertContains(response, "/static/core/vendor/maplibre-gl.css")
        self.assertContains(response, "core/map_provider.js")
        # The provider must load before the neutral loader that calls it.
        html = response.content.decode()
        self.assertLess(html.index("core/map_provider.js"), html.index("core/map.js"))

class MapEventTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="event-user@yale.edu")
        self.client.force_login(self.user)
        self.storage = mock.patch("core.views.photo_storage.upload").start()
        self.addCleanup(mock.patch.stopall)

    def event_values(self, **overrides):
        new_york_date = timezone.now().astimezone(ZoneInfo("America/New_York")).date()
        png = b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")
        values = {
            "image": SimpleUploadedFile("event.png", png, content_type="image/png"),
            "name": "Map Event",
            "description": "Created from the map",
            "category": "music_performance",
            "date": new_york_date.isoformat(),
            "start_time": "18:00",
            "end_time": "20:00",
            "location": "Yale Commons",
            "location_confirmed": "Yale Commons",
            "latitude": "41.308300",
            "longitude": "-72.927900",
            "price": "0",
            "link": "https://example.com/event",
        }
        values.update(overrides)
        return values

    @override_settings(MAP_API_KEY=FAKE_KEY)
    def test_plus_button_opens_create_form_and_valid_post_saves_pin(self):
        response = self.client.get("/map/")
        self.assertContains(response, 'id="open-event-form"')
        self.assertContains(response, "Create event")

        response = self.client.post("/map/", self.event_values())
        self.assertRedirects(response, "/map/", fetch_redirect_response=False)
        event = Event.objects.get(name="Map Event")
        self.assertEqual(event.creator, self.user)
        self.assertEqual(event.price, Decimal("0"))

        response = self.client.get("/map/")
        self.assertIn(event.pk, [item["id"] for item in response.context["map_config"]["events"]])
        self.assertContains(response, "Free")

    @override_settings(MAP_API_KEY=FAKE_KEY)
    def test_expired_event_is_hidden_but_record_remains(self):
        start = timezone.now() - timezone.timedelta(hours=3)
        expired = Event.objects.create(
            image="events/expired.jpg",
            name="Expired Event",
            description="Already finished",
            category="music_performance",
            start_at=start,
            end_at=timezone.now() - timezone.timedelta(hours=1),
            location="Yale Commons",
            latitude="41.308300",
            longitude="-72.927900",
            price="0",
            link="https://example.com/expired",
            creator=self.user,
        )
        response = self.client.get("/map/")
        event_ids = [item["id"] for item in response.context["map_config"]["events"]]
        self.assertNotIn(expired.pk, event_ids)
        self.assertTrue(Event.objects.filter(pk=expired.pk).exists())

    @override_settings(MAP_API_KEY=FAKE_KEY)
    def test_image_menu_offers_gallery_ai_files_camera_and_actions(self):
        response = self.client.get("/map/")
        self.assertContains(response, "Gallery")
        self.assertContains(response, "Generate with AI")
        self.assertContains(response, "Files")
        self.assertContains(response, 'capture="environment"')
        self.assertContains(response, "Replace")
        self.assertContains(response, "Delete")

    @override_settings(MAP_API_KEY=FAKE_KEY)
    def test_ai_generation_endpoint_returns_preview_and_never_exposes_key(self):
        png = b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")
        with mock.patch("core.views.llm.generate_image", return_value=(png, "image/png")):
            response = self.client.post(
                "/event-image/generate/",
                {"name": "Yale Event", "description": "A campus gathering"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["image"].startswith("data:image/png;base64,"))
        self.assertNotIn("OPENROUTER", response.content.decode())

    @override_settings(MAP_API_KEY=FAKE_KEY)
    def test_ai_generation_failure_returns_error(self):
        from core.llm import LLMUnavailable
        with mock.patch(
            "core.views.llm.generate_image",
            side_effect=LLMUnavailable("The AI image service is temporarily unavailable."),
        ):
            response = self.client.post(
                "/event-image/generate/",
                {"name": "Yale Event", "description": "A campus gathering"},
            )
        self.assertEqual(response.status_code, 502)
        self.assertIn("temporarily unavailable", response.json()["error"])

    @override_settings(MAP_API_KEY=FAKE_KEY)
    def test_geocoding_endpoint_mocked_and_requires_login(self):
        suggestions = [{
            "address": "Yale Commons, New Haven, CT",
            "latitude": 41.308300,
            "longitude": -72.927900,
        }]
        with mock.patch("core.views.geocoding.search", return_value=suggestions) as search:
            response = self.client.get("/map/geocode/", {"q": "Yale Commons"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["suggestions"], suggestions)
        search.assert_called_once_with("Yale Commons")

        self.client.logout()
        response = self.client.get("/map/geocode/", {"q": "Yale Commons"})
        self.assertEqual(response.status_code, 302)

    @override_settings(MAP_API_KEY=FAKE_KEY)
    def test_location_autocomplete_script_and_confirmed_field_are_rendered(self):
        response = self.client.get("/map/")
        self.assertContains(response, 'data-geocode-url="/map/geocode/"')
        self.assertContains(response, 'id="id_location_confirmed"')
        path = finders.find("core/map.js")
        with open(path, encoding="utf-8") as f:
            source = f.read()
        self.assertIn("address-suggestions", source)
        self.assertIn("id_location_confirmed", source)

    @override_settings(MAP_API_KEY=FAKE_KEY)
    def test_form_field_order_and_calendar_time_inputs(self):
        response = self.client.get("/map/")
        html = response.content.decode()
        labels = [
            'for="id_image"',
            'for="id_name"',
            'for="id_description"',
            'for="id_category"',
            'for="id_date"',
            'for="id_start_time"',
            'for="id_end_time"',
            'for="id_location"',
            'for="id_price"',
            'for="id_link"',
        ]
        positions = [html.index(label) for label in labels]
        self.assertEqual(positions, sorted(positions))
        self.assertIn('type="date"', html)
        self.assertIn('type="time"', html)

    def test_live_duplicate_popup_and_two_step_buttons_are_in_browser_code(self):
        path = finders.find("core/map.js")
        with open(path, encoding="utf-8") as f:
            source = f.read()
        self.assertIn("openDialog(duplicateDialog)", source)
        self.assertIn("submitButton.disabled = true", source)
        self.assertIn("thatsMyEvent", source)
        self.assertIn("requestCollab", source)
        self.assertIn("window.location.reload()", source)

    @override_settings(MAP_API_KEY=FAKE_KEY)
    def test_invalid_post_keeps_form_open_with_field_errors(self):
        count = Event.objects.count()
        response = self.client.post("/map/", self.event_values(price="-1", end_time="17:00"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Event.objects.count(), count)
        self.assertTrue(response.context["event_form"].errors)
        self.assertContains(response, 'id="event-form-dialog"')
        self.assertContains(response, "open")

    @override_settings(MAP_API_KEY=FAKE_KEY)
    def test_exact_duplicate_endpoint_returns_match(self):
        new_york = ZoneInfo("America/New_York")
        start = datetime(2026, 12, 1, 18, 0, tzinfo=new_york)
        end = datetime(2026, 12, 1, 20, 0, tzinfo=new_york)
        duplicate = Event.objects.create(
            image="events/duplicate.jpg",
            name="Existing Event",
            description="Same details",
            category="music_performance",
            start_at=start,
            end_at=end,
            location="Yale Commons",
            latitude="41.308300",
            longitude="-72.927900",
            price="0",
            link="https://example.com/existing",
            creator=self.user,
        )
        response = self.client.get("/map/duplicate/", {
            "location": "Yale Commons",
            "date": "2026-12-01",
            "start_time": "18:00",
            "end_time": "20:00",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["match"]["id"], duplicate.pk)

    @override_settings(MAP_API_KEY=FAKE_KEY)
    def test_duplicate_endpoint_only_matches_all_exact_fields(self):
        new_york = ZoneInfo("America/New_York")
        Event.objects.create(
            image="events/duplicate.jpg",
            name="Existing Event",
            description="Same details",
            category="music_performance",
            start_at=datetime(2026, 12, 1, 18, 0, tzinfo=new_york),
            end_at=datetime(2026, 12, 1, 20, 0, tzinfo=new_york),
            location="Yale Commons",
            latitude="41.308300",
            longitude="-72.927900",
            price="0",
            link="https://example.com/existing",
            creator=self.user,
        )
        response = self.client.get("/map/duplicate/", {
            "location": "Yale Commons",
            "date": "2026-12-01",
            "start_time": "18:30",
            "end_time": "20:00",
        })
        self.assertIsNone(response.json()["match"])

    @override_settings(MAP_API_KEY=FAKE_KEY)
    def test_server_submit_blocks_duplicate_and_creates_nothing(self):
        new_york = ZoneInfo("America/New_York")
        Event.objects.create(
            image="events/duplicate.jpg",
            name="Existing Event",
            description="Same details",
            category="music_performance",
            start_at=datetime(2026, 12, 1, 18, 0, tzinfo=new_york),
            end_at=datetime(2026, 12, 1, 20, 0, tzinfo=new_york),
            location="Yale Commons",
            latitude="41.308300",
            longitude="-72.927900",
            price="0",
            link="https://example.com/existing",
            creator=self.user,
        )
        data = self.event_values(
            date="2026-12-01",
            start_time="18:00",
            end_time="20:00",
        )
        count = Event.objects.count()
        response = self.client.post("/map/", data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Event.objects.count(), count)
        self.assertContains(response, "An event already exists")

    def test_duplicate_popup_template_flow_is_rendered(self):
        response = self.client.get("/map/")
        self.assertContains(response, 'id="duplicate-event-dialog"')
        self.assertContains(response, 'id="view-duplicate-event"')
        self.assertContains(response, 'id="event-detail-popup"')
        self.assertContains(response, "That's my event")
        self.assertContains(response, "Request collab")
        self.assertContains(response, "Return to map")

    def test_event_detail_page_and_popup_use_shared_view(self):
        event = Event.objects.create(
            image="events/detail.jpg",
            name="Shared Detail",
            description="Details",
            category="talks_panels",
            start_at=timezone.now() + timezone.timedelta(days=1),
            end_at=timezone.now() + timezone.timedelta(days=1, hours=1),
            location="Yale Commons",
            latitude="41.308300",
            longitude="-72.927900",
            price="0",
            link="https://example.com/detail",
        )
        page = self.client.get(f"/events/{event.pk}/")
        popup = self.client.get(f"/events/{event.pk}/popup/")
        self.assertEqual(page.status_code, 200)
        self.assertEqual(popup.status_code, 200)
        self.assertContains(page, "Shared Detail")
        self.assertContains(popup, "Shared Detail")
        self.assertEqual(
            self.client.get("/events/999999/").status_code,
            404,
        )

    def test_creator_can_edit_event_without_replacing_image(self):
        event = Event.objects.create(
            image="events/edit.jpg",
            name="Original Name",
            description="Original description",
            category="talks_panels",
            start_at=datetime(2026, 12, 1, 18, 0, tzinfo=ZoneInfo("America/New_York")),
            end_at=datetime(2026, 12, 1, 20, 0, tzinfo=ZoneInfo("America/New_York")),
            location="Yale Commons",
            latitude="41.308300",
            longitude="-72.927900",
            price="0",
            link="https://example.com/original",
            creator=self.user,
        )
        get_response = self.client.get(f"/events/{event.pk}/edit/")
        self.assertEqual(get_response.status_code, 200)

        data = self.event_values(
            name="Updated Name",
            date="2026-12-01",
            start_time="18:00",
            end_time="20:00",
        )
        data.pop("image")
        response = self.client.post(f"/events/{event.pk}/edit/", data)
        self.assertRedirects(
            response,
            f"/events/{event.pk}/",
            fetch_redirect_response=False,
        )
        event.refresh_from_db()
        self.assertEqual(event.name, "Updated Name")
        self.assertEqual(event.image, "events/edit.jpg")

    def test_other_user_gets_403_for_edit_and_delete(self):
        event = Event.objects.create(
            image="events/owned.jpg",
            name="Owned Event",
            description="Owner only",
            category="talks_panels",
            start_at=timezone.now() + timezone.timedelta(days=1),
            end_at=timezone.now() + timezone.timedelta(days=1, hours=1),
            location="Yale Commons",
            latitude="41.308300",
            longitude="-72.927900",
            price="0",
            link="https://example.com/owned",
            creator=self.user,
        )
        other = get_user_model().objects.create_user(username="other-edit@yale.edu")
        self.client.force_login(other)
        self.assertEqual(self.client.get(f"/events/{event.pk}/edit/").status_code, 403)
        self.assertEqual(self.client.post(f"/events/{event.pk}/delete/").status_code, 403)
        self.assertTrue(Event.objects.filter(pk=event.pk).exists())

    def test_creator_can_delete_event(self):
        event = Event.objects.create(
            image="events/delete.jpg",
            name="Delete Me",
            description="Owner delete",
            category="talks_panels",
            start_at=timezone.now() + timezone.timedelta(days=1),
            end_at=timezone.now() + timezone.timedelta(days=1, hours=1),
            location="Yale Commons",
            latitude="41.308300",
            longitude="-72.927900",
            price="0",
            link="https://example.com/delete",
            creator=self.user,
        )
        response = self.client.post(f"/events/{event.pk}/delete/")
        self.assertRedirects(response, "/map/", fetch_redirect_response=False)
        self.assertFalse(Event.objects.filter(pk=event.pk).exists())

    def test_edit_delete_missing_event_returns_404(self):
        self.assertEqual(self.client.get("/events/999999/edit/").status_code, 404)
        self.assertEqual(self.client.post("/events/999999/delete/").status_code, 404)


class MapProviderScriptTests(TestCase):
    def test_provider_uses_local_osm_vector_tiles(self):
        path = finders.find("core/map_provider.js")
        self.assertIsNotNone(path)
        with open(path, encoding="utf-8") as f:
            source = f.read()
        self.assertIn("window.renderMap", source)
        self.assertIn("function localStyle(config)", source)
        self.assertIn("tiles: [window.location.origin + config.tileUrl]", source)
        self.assertIn('"source-layer": "transportation"', source)
        self.assertIn('"source-layer": "water"', source)
        self.assertIn("© OpenStreetMap contributors", source)
        self.assertNotIn("https://", source)
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

    def test_event_form_has_responsive_phone_tablet_desktop_styles(self):
        path = finders.find("core/map.css")
        with open(path, encoding="utf-8") as f:
            css = f.read()
        self.assertIn("width: min(92vw, 34rem)", css)
        self.assertIn("100dvh", css)
        self.assertIn("@media (min-width: 768px)", css)
        self.assertIn("@media (min-width: 1280px)", css)

    def test_map_provider_renders_category_icons_and_place_popups(self):
        path = finders.find("core/map_provider.js")
        with open(path, encoding="utf-8") as f:
            source = f.read()
        self.assertIn("(config.places || []).forEach", source)
        self.assertIn("poi-marker--", source)
        self.assertIn('place.kind === "yale"', source)
        self.assertIn('place.kind === "restaurant"', source)
        self.assertIn(".setPopup(popup)", source)

    def test_place_legend_explains_each_icon(self):
        user = get_user_model().objects.create_user(username="poi-legend@yale.edu")
        self.client.force_login(user)
        response = self.client.get("/map/")
        self.assertContains(response, 'aria-label="Map place legend"')
        self.assertContains(response, "Yale facilities")
        self.assertContains(response, "Restaurants")
        self.assertContains(response, "Bars")


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

    def test_event_external_dependencies_are_mocked_not_contacted(self):
        user = get_user_model().objects.create_user(username="no-network@yale.edu")
        self.client.force_login(user)
        png = b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
        with (
            mock.patch.object(socket.socket, "connect",
                              side_effect=AssertionError("network call attempted")) as connect,
            mock.patch("core.views.geocoding.search",
                       return_value=[{"address": "Yale Commons", "latitude": 41.3083, "longitude": -72.9279}]),
            mock.patch("core.views.llm.generate_image", return_value=(png, "image/png")),
            mock.patch("core.views.photo_storage.upload"),
        ):
            geocode = self.client.get("/map/geocode/", {"q": "Yale"})
            generated = self.client.post(
                "/event-image/generate/",
                {"name": "Yale Event", "description": "Campus event"},
            )
            page = self.client.get("/map/")
        self.assertEqual(geocode.status_code, 200)
        self.assertEqual(generated.status_code, 200)
        self.assertEqual(page.status_code, 200)
        connect.assert_not_called()


@override_settings(MAP_API_KEY="")
class MapScreenWithoutKeyTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="student", password="x")
        self.client.force_login(user)

    def test_missing_maptiler_key_does_not_disable_local_basemap(self):
        response = self.client.get("/map/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "More coming soon.")
        self.assertTrue(response.context["map_enabled"])
        self.assertContains(response, '<p id="map-fallback" class="fallback" role="status" hidden>')
        self.assertContains(response, "core/map_provider.js")

    def test_missing_local_tiles_show_the_fallback(self):
        missing_tiles = Path(tempfile.gettempdir()) / "no-such-map-tiles.mbtiles"
        with self.settings(LOCAL_MAP_TILES_PATH=missing_tiles):
            with self.assertLogs("core.views", level="ERROR"):
                response = self.client.get("/map/")
        self.assertFalse(response.context["map_enabled"])
        self.assertContains(response, FALLBACK_TEXT)
        self.assertNotContains(response, "core/map_provider.js")


class MapTileTests(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.tile_path = Path(self.temp_dir.name) / "tiles.mbtiles"
        with sqlite3.connect(self.tile_path) as database:
            database.execute(
                "CREATE TABLE tiles "
                "(zoom_level INTEGER, tile_column INTEGER, tile_row INTEGER, tile_data BLOB)"
            )
            database.execute(
                "INSERT INTO tiles VALUES (?, ?, ?, ?)",
                (8, 1, 253, gzip.compress(b"test vector tile")),
            )

    def test_serves_gzipped_tile_with_tms_row_conversion(self):
        with self.settings(LOCAL_MAP_TILES_PATH=self.tile_path):
            response = self.client.get("/map/tiles/8/1/2.pbf")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/vnd.mapbox-vector-tile")
        self.assertEqual(response["Content-Encoding"], "gzip")
        self.assertEqual(gzip.decompress(response.content), b"test vector tile")

    def test_missing_tile_returns_no_content_and_out_of_range_zoom_is_rejected(self):
        with self.settings(LOCAL_MAP_TILES_PATH=self.tile_path):
            missing = self.client.get("/map/tiles/8/1/3.pbf")
            invalid = self.client.get("/map/tiles/7/1/2.pbf")
        self.assertEqual(missing.status_code, 204)
        self.assertEqual(invalid.status_code, 404)

    def test_bundled_archive_serves_a_new_haven_center_tile(self):
        response = self.client.get("/map/tiles/13/2436/3062.pbf")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Encoding"], "gzip")
        self.assertGreater(len(response.content), 0)
