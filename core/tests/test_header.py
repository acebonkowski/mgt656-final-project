"""
Top-right header on the map screen (#81): Create and the profile menu.
"""

import re

from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.test import TestCase


def static_source(path):
    with open(finders.find(path), encoding="utf-8") as f:
        return f.read()


def relative_luminance(hex_colour):
    channels = [int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast_ratio(a, b):
    lighter, darker = sorted((relative_luminance(a), relative_luminance(b)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


class HeaderMarkupTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="header@yale.edu")
        self.client.force_login(self.user)
        self.response = self.client.get("/map/")
        self.html = self.response.content.decode()
        self.header = self.html.split('class="top-actions"', 1)[1].split("</form>", 1)[0]

    def test_create_button_has_a_plus_icon_and_the_word_create(self):
        create = self.header.split('id="open-event-form"', 1)[1].split("</button>", 1)[0]
        self.assertIn("<svg", create)
        self.assertIn("<span>Create</span>", create)
        self.assertNotIn(">+</button>", self.html)

    def test_create_button_still_opens_the_dialog(self):
        # map.js binds the dialog to this id (#57).
        self.assertIn('aria-controls="event-form-dialog"', self.header)
        self.assertIn('getElementById("open-event-form")', static_source("core/map.js"))

    def test_logout_is_in_a_csrf_protected_post_form(self):
        form = self.header.split('class="logout"', 1)[1]
        self.assertIn('method="post"', form)
        self.assertIn('action="/logout/"', form)
        self.assertIn('name="csrfmiddlewaretoken"', form)
        self.assertIn('aria-label="Log Out"', form)
        self.assertNotIn(">Log out<", self.html)

    def test_create_precedes_profile_menu(self):
        self.assertLess(self.header.index('id="open-event-form"'), self.header.index('id="profile-menu-toggle"'))

    def test_logout_signs_the_user_out(self):
        response = self.client.post("/logout/")
        self.assertRedirects(response, "/login/", fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)


class HeaderStyleTests(TestCase):
    def setUp(self):
        self.css = static_source("core/map.css")

    def token(self, name):
        match = re.search(rf"--{name}:\s*(#[0-9a-fA-F]{{6}})", self.css)
        self.assertIsNotNone(match, f"--{name} missing")
        return match.group(1)

    def test_create_button_text_contrast_is_at_least_4_5_to_1(self):
        for background in ("create-bg", "create-bg-hover"):
            ratio = contrast_ratio(self.token(background), self.token("create-text"))
            self.assertGreaterEqual(ratio, 4.5, f"{background}: {ratio:.2f}")

    def test_create_fill_is_saturated_and_distinct_from_the_dark_map(self):
        bg = self.token("create-bg")
        r, g, b = (int(bg[i:i + 2], 16) for i in (1, 3, 5))
        saturation = (max(r, g, b) - min(r, g, b)) / max(r, g, b)
        self.assertGreater(saturation, 0.6)
        self.assertGreater(contrast_ratio(bg, "#0b1220"), 2.5)  # --map-bg

    def test_header_sits_above_the_search_panel(self):
        rule = self.css.split(".top-actions {", 1)[1].split("}", 1)[0]
        self.assertIn("z-index: 3;", rule)
        self.assertIn("position: absolute;", rule)


class ProfileMenuTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="profile-menu@yale.edu")
        self.client.force_login(self.user)

    def test_menu_order_placeholder_and_no_legacy_buttons(self):
        response = self.client.get("/map/")
        html = response.content.decode()
        self.assertContains(response, 'class="profile-placeholder"')
        self.assertNotContains(response, 'id="profile-menu-photo"')
        self.assertNotContains(response, 'class="logout-button"')
        self.assertNotContains(response, 'id="my-events-link"')
        self.assertLess(html.index('id="open-event-form"'), html.index('id="profile-menu-toggle"'))
        panel = html.split('<nav id="profile-menu-panel"', 1)[1].split('</nav>', 1)[0]
        positions = [panel.index(f'<span>{label}</span>') for label in ('My Events', 'Friends', 'Settings', 'Log Out')]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(panel.count('<svg'), 4)
        self.assertIn('href="/my-events/"', panel)
        self.assertNotIn('friend-request-badge', html)

    def test_photo_uses_authenticated_endpoint(self):
        from accounts.models import Profile
        Profile.objects.create(user=self.user, photo_reference="profiles/test/photo.png")
        response = self.client.get("/map/")
        self.assertContains(response, 'id="profile-menu-photo" src="/onboarding/photo/"')
        self.assertNotContains(response, "profiles/test/photo.png")

    def test_two_incoming_requests_render_both_badges(self):
        from unittest.mock import patch
        with patch("core.header.incoming_friend_request_count", return_value=2) as count:
            response = self.client.get("/map/")
        count.assert_called_once_with(self.user)
        self.assertContains(response, 'class="friend-request-badge"', count=2)
        self.assertContains(response, 'aria-label="2 incoming friend requests">2</span>', count=2)

    def test_logout_requires_csrf_and_ends_session(self):
        from django.test import Client
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post("/logout/").status_code, 403)
        client.get("/map/")
        response = client.post("/logout/", HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value)
        self.assertRedirects(response, "/login/", fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", client.session)

    def test_pending_destinations_are_accessible_only_after_login(self):
        for url, title in (("/friends/", "Friends"), ("/settings/", "Settings")):
            response = self.client.get(url)
            self.assertContains(response, f"<h1>{title}</h1>")
            self.assertContains(response, "coming soon")
        self.client.logout()
        for url in ("/friends/", "/settings/"):
            self.assertEqual(self.client.get(url).status_code, 302)

    def test_zero_count_hides_both_badges(self):
        from unittest.mock import patch
        with patch("core.header.incoming_friend_request_count", return_value=0):
            response = self.client.get("/map/")
        self.assertNotContains(response, 'class="friend-request-badge"')

    def test_destination_links_use_named_routes(self):
        from django.urls import reverse
        response = self.client.get("/map/")
        for name in ("my_events", "friends", "settings"):
            self.assertContains(response, f'href="{reverse(name)}"')

    def test_header_reflects_count_changes_on_next_page_load(self):
        from unittest.mock import patch
        with patch("core.header.incoming_friend_request_count", side_effect=[2, 0]):
            self.assertContains(self.client.get("/map/"), 'class="friend-request-badge"', count=2)
            response = self.client.get("/map/")
            self.assertNotContains(response, 'class="friend-request-badge"')
            self.assertIn("no-cache", response["Cache-Control"])
