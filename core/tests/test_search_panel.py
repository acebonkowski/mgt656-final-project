"""
Search panel on the map screen (#35).

The panel's behaviour runs in the browser (core/static/core/search.js). These
tests cover what the server renders and the hooks the script relies on.
"""

import re

from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.test import TestCase

from core.models import Event


def static_source(path):
    with open(finders.find(path), encoding="utf-8") as f:
        return f.read()


class SearchPanelTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="panel-user@yale.edu")
        self.client.force_login(user)
        self.response = self.client.get("/map/")
        self.html = self.response.content.decode()

    def test_panel_is_on_the_map_screen_with_endpoints(self):
        self.assertTemplateUsed(self.response, "core/_search_panel.html")
        self.assertContains(self.response, 'id="search-panel"')
        self.assertContains(self.response, 'data-search-url="/events/search/"')
        self.assertContains(self.response, 'data-geocode-url="/map/geocode/"')
        self.assertContains(self.response, 'role="search"')

    def test_search_box_search_and_filters_buttons(self):
        self.assertContains(self.response, 'id="search-q"')
        self.assertContains(self.response, 'id="search-submit"')
        self.assertContains(self.response, 'aria-controls="search-filters"')

    def test_only_one_clear_filters_button(self):
        self.assertEqual(self.html.count(">Clear filters<"), 1)
        self.assertContains(self.response, 'id="search-clear" type="button" hidden')

    def test_category_list_has_exactly_the_12_categories(self):
        values = re.findall(r'name="category" value="([a-z_]+)"', self.html)
        self.assertEqual(values, list(Event.Category.values))
        self.assertEqual(len(values), 12)
        self.assertIn('data-label="Food &amp; Drink"', self.html)

    def test_date_quick_picks_and_pick_dates(self):
        values = re.findall(r'name="when" value="([a-z]*)"', self.html)
        self.assertEqual(values, ["", "today", "tomorrow", "weekend", "dates"])
        self.assertContains(self.response, 'id="search-date-range"')
        self.assertContains(self.response, 'id="search-date-from"')
        self.assertContains(self.response, 'id="search-date-to"')

    def test_start_time_window(self):
        self.assertContains(self.response, 'id="search-time-from" type="time"')
        self.assertContains(self.response, 'id="search-time-to" type="time"')

    def test_location_radius_defaults_to_one_mile(self):
        self.assertContains(self.response, 'id="search-address"')
        self.assertContains(self.response, 'id="search-my-location"')
        options = re.findall(r'<option value="([0-9.]+)"( selected)?>', self.html)
        self.assertEqual([value for value, _ in options], ["0.5", "1", "2", "5"])
        self.assertEqual([value for value, selected in options if selected], ["1"])

    def test_panel_collapses_to_a_one_line_summary(self):
        self.assertContains(self.response, 'id="search-collapse"')
        self.assertContains(self.response, 'aria-label="Collapse search panel"')
        self.assertContains(self.response, 'id="search-summary" class="search-summary"')
        self.assertContains(self.response, 'id="search-summary-text"')
        self.assertNotContains(self.response, "search-list-toggle")

    def test_search_this_area_stays_visible_when_collapsed(self):
        # The button sits outside the form, which is what collapsing hides.
        form_end = self.html.index("</form>")
        self.assertGreater(self.html.index('id="search-this-area"'), form_end)

    def test_chips_status_results_and_search_this_area(self):
        self.assertContains(self.response, 'id="search-chips"')
        self.assertContains(self.response, 'id="search-status"')
        self.assertContains(self.response, 'id="search-results"')
        self.assertContains(self.response, 'id="search-this-area"')

    def test_assets_load_after_the_map_script(self):
        self.assertContains(self.response, "core/search.css")
        self.assertLess(self.html.index("core/map.js"), self.html.index("core/search.js"))

    def test_placeholder_headline_is_replaced_by_an_accessible_heading(self):
        self.assertNotContains(self.response, "More coming soon.")
        self.assertContains(self.response, '<h1 class="visually-hidden">Find events in New Haven</h1>')

    def test_existing_map_screen_content_is_kept(self):
        self.assertContains(self.response, 'id="open-event-form"')
        self.assertContains(self.response, 'aria-label="Map place legend"')


class SearchScriptTests(TestCase):
    def test_provider_lets_search_replace_event_markers(self):
        source = static_source("core/map_provider.js")
        self.assertIn("window.eventMap = {", source)
        self.assertIn("setEvents: setEvents", source)
        self.assertIn("setEvents(pendingEvents || config.events)", source)
        self.assertIn("event.originalEvent", source)

    def test_provider_draws_a_zoom_sized_search_circle(self):
        source = static_source("core/map_provider.js")
        self.assertIn("setArea: setArea", source)
        self.assertIn("viewCircle: viewCircle", source)
        self.assertIn('map.addSource("search-area"', source)
        self.assertIn("function circlePolygon(lat, lng, radius)", source)
        # Dashed preview after a drag, solid once searched.
        self.assertIn('id: "search-area-preview"', source)
        self.assertIn('id: "search-area-line"', source)

    def test_marker_popup_links_to_the_event_page(self):
        source = static_source("core/map_provider.js")
        self.assertIn('className: "event-popup"', source)
        self.assertIn('link.textContent = "View event"', source)
        css = static_source("core/search.css")
        self.assertIn(".event-popup .event-popup-name", css)

    def test_search_script_uses_endpoint_and_keeps_filters_in_the_url(self):
        source = static_source("core/search.js")
        self.assertIn("panel.dataset.searchUrl", source)
        self.assertIn("window.eventMap.setEvents(events)", source)
        self.assertIn("window.history.replaceState", source)
        self.assertIn("renderResults(events)", source)
        self.assertIn("window.eventMap.setArea", source)
        self.assertIn("No events found", source)
        self.assertNotIn("https://", source)

    def test_search_script_handles_location_failures(self):
        source = static_source("core/search.js")
        self.assertIn("Location access was denied", source)
        self.assertIn("Address search is unavailable right now", source)

    def test_filters_apply_when_changed(self):
        source = static_source("core/search.js")
        self.assertIn('input.addEventListener("change", applySoon)', source)

    def test_search_this_area_previews_then_searches_the_circle(self):
        source = static_source("core/search.js")
        self.assertIn("previewArea = window.eventMap.viewCircle()", source)
        self.assertIn("area: area,", source)
        self.assertNotIn("bbox", source)

    def test_collapse_behaviour(self):
        source = static_source("core/search.js")
        self.assertIn("function setCollapsed(collapsed)", source)
        self.assertIn("function updateSummary()", source)
        # Phones: dragging the map tucks the panel away.
        self.assertIn('window.matchMedia("(max-width: 767px)")', source)
        self.assertIn("window.eventMap.onUserMoveStart", source)
        # Choosing a result collapses the panel and shows the event on the map.
        self.assertIn("window.eventMap.focusEvent(event.id)", source)
        provider = static_source("core/map_provider.js")
        self.assertIn("focusEvent: function (id)", provider)
        self.assertIn("onUserMoveStart: function (callback)", provider)
