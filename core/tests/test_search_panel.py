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
        self.assertIn("function setCollapsed(value)", source)
        self.assertIn("function updateSummary()", source)
        # Phones: dragging the map tucks the panel away.
        self.assertIn('window.matchMedia("(max-width: 767px)")', source)
        self.assertIn("window.eventMap.onUserMoveStart", source)
        # Opening an event centres the map on its pin.
        self.assertIn("window.eventMap.focusEvent(event.id)", source)
        provider = static_source("core/map_provider.js")
        self.assertIn("focusEvent: function (id)", provider)
        self.assertIn("onUserMoveStart: function (callback)", provider)


class SidePanelLayoutTests(TestCase):
    """#34: full-height side panel on tablets and desktops."""

    def setUp(self):
        self.css = static_source("core/search.css")
        desktop = self.css.split("@media (min-width: 768px) {", 1)
        self.assertEqual(len(desktop), 2, "desktop rules missing")
        self.desktop = desktop[1]

    def test_panel_is_full_height_on_the_left(self):
        rule = self.desktop.split(".search-panel {", 1)[1].split("}", 1)[0]
        for declaration in ("position: fixed;", "top: 0;", "bottom: 0;", "left: 0;",
                            "width: var(--search-panel-width);"):
            self.assertIn(declaration, rule)

    def test_map_and_legend_sit_beside_the_open_panel(self):
        self.assertIn("body.map-screen:not(.search-collapsed) .map {\n    left: var(--search-panel-width);",
                      self.desktop)
        self.assertIn("body.map-screen:not(.search-collapsed) .poi-legend {\n"
                      "    left: calc(var(--search-panel-width) + 0.75rem);", self.desktop)

    def test_collapsing_gives_the_map_full_width(self):
        self.assertIn(".search-collapsed .search-panel {", self.desktop)
        source = static_source("core/search.js")
        self.assertIn('document.body.classList.toggle("search-collapsed", collapsed)', source)
        self.assertIn("window.eventMap.resize()", source)
        self.assertIn("resize: function () { map.resize(); }", static_source("core/map_provider.js"))


class EventDialogTests(TestCase):
    """#34: result cards and pins open one event dialog with previous/next."""

    def setUp(self):
        user = get_user_model().objects.create_user(username="dialog-user@yale.edu")
        self.client.force_login(user)
        self.response = self.client.get("/map/")
        self.source = static_source("core/search.js")
        self.provider = static_source("core/map_provider.js")

    def test_dialog_markup(self):
        self.assertContains(self.response, 'id="search-event-dialog" class="event-detail-popup search-event-dialog"')
        self.assertContains(self.response, 'id="search-event-prev" type="button" aria-label="Previous event"')
        self.assertContains(self.response, 'id="search-event-next" type="button" aria-label="Next event"')
        self.assertContains(self.response, 'id="search-event-close"')
        self.assertContains(self.response, 'id="search-event-position"')
        self.assertContains(self.response, 'data-popup-url="/events/0/popup/"')

    def test_popup_page_the_dialog_loads_exists(self):
        from core.tests.test_search_endpoint import make_event

        event = make_event("Jazz Night")
        response = self.client.get(f"/events/{event.pk}/popup/")
        self.assertContains(response, "Jazz Night")
        self.assertNotContains(response, "<html")  # a fragment for the dialog

    def test_cards_and_pins_open_the_dialog(self):
        self.assertIn("openEvent(index, link)", self.source)
        self.assertIn("window.eventMap.onEventClick(function (id)", self.source)
        self.assertIn("onEventClick: function (callback) { eventClickHandler = callback; }",
                      self.provider)
        self.assertNotIn("setPopup(popup)", self.provider.split("function eventMarker", 1)[1]
                         .split("function setEvents", 1)[0])

    def test_previous_and_next_are_disabled_at_the_ends(self):
        self.assertIn("prevButton.disabled = index === 0;", self.source)
        self.assertIn("nextButton.disabled = index === currentEvents.length - 1;", self.source)
        self.assertIn('(index + 1) + " of " + currentEvents.length', self.source)

    def test_closing_returns_focus_to_the_card(self):
        self.assertIn('dialog.addEventListener("close"', self.source)
        self.assertIn("openedFrom.focus()", self.source)

    def test_pins_are_keyboard_accessible_and_fall_back_to_the_page(self):
        self.assertIn('element.setAttribute("role", "button")', self.provider)
        self.assertIn('element.setAttribute("tabindex", "0")', self.provider)
        self.assertIn('window.location.href = event.detail_url || event.url || "/events/" + event.id + "/"',
                      self.provider)

    def test_cards_have_a_thumbnail_with_initial_fallback(self):
        self.assertIn('box.className = "search-result-thumb"', self.source)
        self.assertIn("box.textContent = event.name.charAt(0).toUpperCase()", self.source)
        self.assertIn(".search-result-thumb img", static_source("core/search.css"))

    def test_list_loads_on_arrival(self):
        # Without filters in the URL the panel lists all upcoming events.
        tail = self.source.rsplit("var initial = new URLSearchParams(window.location.search);", 1)[1]
        self.assertIn("runSearch();", tail)
        self.assertNotIn("if (initial.toString()) {", tail)


class AiModeTests(TestCase):
    """#34: an AI button switches the panel to AI mode (#36 fills it in)."""

    def setUp(self):
        user = get_user_model().objects.create_user(username="ai-mode@yale.edu")
        self.client.force_login(user)
        self.response = self.client.get("/map/")
        self.html = self.response.content.decode()
        self.source = static_source("core/search.js")

    def test_ai_button_sits_next_to_filters(self):
        row = self.html.split('class="search-row"', 1)[1].split("</div>", 1)[0]
        self.assertLess(row.index('id="search-filters-toggle"'), row.index('id="search-ai-toggle"'))
        self.assertContains(self.response, 'aria-controls="search-ai" aria-pressed="false"')

    def test_search_button_is_an_icon_with_a_label(self):
        self.assertContains(self.response, 'aria-label="Search" title="Search"')

    def test_ai_view_is_hidden_until_chosen_and_has_a_back_arrow(self):
        self.assertContains(self.response, 'id="search-ai" class="search-ai" aria-labelledby="search-ai-title" hidden')
        self.assertContains(self.response, 'id="search-ai-back"')
        self.assertContains(self.response, 'aria-label="Back to filters"')

    def test_mode_is_kept_in_the_url_and_restored(self):
        self.assertIn('if (mode === "ai") page.set("mode", "ai");', self.source)
        self.assertIn('if (initial.get("mode") === "ai") setMode("ai");', self.source)

    def test_switching_keeps_the_filters(self):
        # setMode only swaps the views; it never resets the filter controls.
        body = self.source.split("function setMode(value) {", 1)[1].split("\n  }\n", 1)[0]
        self.assertNotIn("writeFilters", body)
        self.assertNotIn("runSearch", body)
        self.assertIn("form.hidden = collapsed || mode === \"ai\";", self.source)
