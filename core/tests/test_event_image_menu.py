"""
Create event: square image placeholder with a plus menu (#68).

The menu's behaviour runs in core/static/core/map.js; these tests cover the
rendered markup, the hooks the script relies on, and the server-side rules.
The image generator is always mocked.
"""

import re
from base64 import b64decode
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.test import TestCase

PNG = b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")


def static_source(path):
    with open(finders.find(path), encoding="utf-8") as f:
        return f.read()


class ImagePlaceholderMarkupTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="image-menu@yale.edu")
        self.client.force_login(self.user)
        self.response = self.client.get("/map/")
        html = self.response.content.decode()
        self.menu = html.split('class="image-menu"', 1)[1].split('id="event-image-error"', 1)[0]
        self.source = static_source("core/map.js")
        self.css = static_source("core/map.css")

    def test_old_button_bar_is_gone(self):
        self.assertNotContains(self.response, "image-menu-actions")
        for gone in ('id="event-image-replace"', 'id="event-image-delete"', ">Add image<",
                     ">Replace<", ">Delete<", "Generate with AI"):
            self.assertNotIn(gone, self.menu)

    def test_empty_state_is_a_centred_square_with_a_plus(self):
        add = self.menu.split('id="event-image-add"', 1)[1].split("</button>", 1)[0]
        self.assertIn('aria-label="Add image"', add)
        self.assertIn('<path d="M12 5v14M5 12h14"/>', add)  # plus
        self.assertIn('aria-controls="event-image-sources"', add)
        square = self.css.split(".image-square {", 1)[1].split("}", 1)[0]
        self.assertIn("aspect-ratio: 1 / 1;", square)
        self.assertIn("justify-items: center;", self.css.split(".image-menu {", 1)[1].split("}", 1)[0])

    def test_menu_lists_gallery_generate_files_camera_in_order(self):
        sources = self.menu.split('id="event-image-sources"', 1)[1]
        items = re.findall(r"<label>(\w+)<input|<button[^>]*>(\w+)</button>", sources)
        self.assertEqual([a or b for a, b in items], ["Gallery", "Generate", "Files", "Camera"])
        self.assertIn('capture="environment"', sources)
        self.assertIn('id="event-image-ai"', sources)

    def test_chosen_image_shows_edit_next_to_a_top_right_cross(self):
        tools = self.menu.split('class="image-tools"', 1)[1]
        self.assertLess(tools.index('id="event-image-edit"'), tools.index('id="event-image-remove"'))
        self.assertIn('aria-controls="event-image-sources"', tools.split('id="event-image-remove"', 1)[0])
        rule = self.css.split(".image-tools {", 1)[1].split("}", 1)[0]
        self.assertIn("top: 0.4rem;", rule)
        self.assertIn("right: 0.4rem;", rule)
        preview = self.css.split(".event-image-preview img {", 1)[1].split("}", 1)[0]
        self.assertIn("object-fit: cover;", preview)

    def test_plus_and_edit_open_the_same_menu_and_cross_clears(self):
        self.assertIn('addButton.addEventListener("click", toggleMenu);', self.source)
        self.assertIn('editButton.addEventListener("click", toggleMenu);', self.source)
        self.assertIn('removeButton.addEventListener("click", clearImage);', self.source)
        clear = self.source.split("function clearImage() {", 1)[1].split("\n    }\n", 1)[0]
        self.assertIn("preview.hidden = true;", clear)
        self.assertIn("addButton.hidden = false;", clear)
        shown = self.source.split("function showSelectedImage(src) {", 1)[1].split("\n    }\n", 1)[0]
        self.assertIn("addButton.hidden = true;", shown)
        self.assertIn("preview.hidden = false;", shown)

    def test_raw_image_field_really_is_hidden(self):
        self.assertIn("formImage.parentElement.hidden = true;", self.source)
        self.assertIn(".event-form p[hidden] {\n  display: none;", self.css)

    def test_generate_still_uses_the_existing_endpoint(self):
        self.assertIn('data-generate-url="/event-image/generate/"', self.menu)
        self.assertIn("fetch(imageMenu.dataset.generateUrl", self.source)


class ImageRequiredTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="image-required@yale.edu")
        self.client.force_login(self.user)

    def values(self, **overrides):
        values = {
            "name": "Placeholder Test", "description": "An event", "category": "music_performance",
            "date": "2030-01-15", "start_time": "18:00", "end_time": "20:00",
            "location": "Yale Commons", "location_confirmed": "Yale Commons",
            "latitude": "41.308300", "longitude": "-72.927900", "price": "0",
            "link": "https://example.com/event",
        }
        values.update(overrides)
        return values

    def test_submitting_without_an_image_shows_choose_an_image(self):
        response = self.client.post("/map/", self.values())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Choose an image.")
        self.assertIn("data-open-on-load", response.content.decode())

    def test_cleared_image_is_still_required(self):
        response = self.client.post("/map/", self.values(remove_image="1"))
        self.assertContains(response, "Choose an image.")

    def test_generate_endpoint_is_mocked_and_returns_an_image(self):
        with mock.patch("core.views.llm.generate_image", return_value=(PNG, "image/png")) as generate:
            response = self.client.post("/event-image/generate/", {"name": "Jazz", "description": "Night"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["image"].startswith("data:image/png;base64,"))
        generate.assert_called_once()
