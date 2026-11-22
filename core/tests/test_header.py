"""
Top-right header on the map screen (#64): a logout icon and a Create button.
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

    def test_logout_is_an_icon_button_in_a_csrf_protected_post_form(self):
        form = self.header.split('class="logout"', 1)[1]
        self.assertIn('method="post"', form)
        self.assertIn('action="/logout/"', form)
        self.assertIn('name="csrfmiddlewaretoken"', form)
        self.assertIn('aria-label="Log Out"', form)
        self.assertNotIn(">Log out<", self.html)

    def test_create_sits_next_to_logout_in_one_row(self):
        self.assertLess(self.header.index('id="open-event-form"'), self.header.index('class="logout"'))

    def test_logout_icon_signs_the_user_out(self):
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
