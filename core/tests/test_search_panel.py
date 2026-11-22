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

    def test_map_runs_under_the_glass_panel_and_legend_sits_beside_it(self):
        # #65: the map is visible through the translucent panel.
        self.assertNotIn("body.map-screen:not(.search-collapsed) .map {", self.desktop)
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

    def test_search_icon_sits_next_to_the_filter_icon(self):
        bar = self.html.split('class="search-bar"', 1)[1].split("</div>", 1)[0]
        self.assertLess(bar.index('id="search-filters-toggle"'), bar.index('id="search-ai-toggle"'))
        self.assertContains(self.response, 'id="search-ai-toggle" class="search-icon-button" type="button"\n'
                                           '              aria-controls="search-ai"')

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


class AiChatPanelTests(TestCase):
    """#36: the text chat in the AI view."""

    def setUp(self):
        user = get_user_model().objects.create_user(username="ai-chat@yale.edu")
        self.client.force_login(user)
        self.response = self.client.get("/map/")
        self.html = self.response.content.decode()
        self.source = static_source("core/search.js")

    def test_chat_markup(self):
        self.assertContains(self.response, 'data-ai-url="/events/search/ai/"')
        self.assertContains(self.response, 'data-ai-reset-url="/events/search/ai/reset/"')
        self.assertContains(self.response, 'id="search-ai-log" class="search-ai-log" role="log"')
        self.assertContains(self.response, 'id="search-ai-input" name="message" rows="2" maxlength="300"')
        self.assertContains(self.response, 'id="search-ai-send"')
        self.assertContains(self.response, 'id="search-ai-new"')
        self.assertContains(self.response, 'id="search-ai-results"')

    def test_chat_form_carries_the_csrf_token(self):
        ai_form = self.html.split('id="search-ai-form"', 1)[1].split("</form>", 1)[0]
        self.assertIn('name="csrfmiddlewaretoken"', ai_form)

    def test_messages_are_posted_with_the_csrf_header(self):
        self.assertIn('"X-CSRFToken": csrfToken()', self.source)
        self.assertIn('method: "POST"', self.source)

    def test_enter_sends_and_shift_enter_does_not(self):
        self.assertIn('event.key === "Enter" && !event.shiftKey', self.source)

    def test_chat_text_is_never_inserted_as_html(self):
        body = self.source.split("function aiEntry(entry) {", 1)[1].split("\n  }\n", 1)[0]
        self.assertIn("text.textContent = entry.text;", body)
        self.assertNotIn("innerHTML", body)

    def test_transcript_survives_a_refresh_and_new_chat_clears_it(self):
        self.assertIn("window.sessionStorage.setItem(CHAT_KEY", self.source)
        new_chat = self.source.split('aiNew.addEventListener("click"', 1)[1].split("\n  });\n", 1)[0]
        self.assertIn("aiResetUrl", new_chat)
        self.assertIn("chat = [];", new_chat)

    def test_edit_in_filters_applies_the_ai_filters(self):
        body = self.source.split("function editInFilters(filters) {", 1)[1].split("\n  }\n", 1)[0]
        self.assertIn("writeFilters(fromParams(filtersToParams(filters)))", body)
        self.assertIn('setMode("filters")', body)
        self.assertIn("runSearch()", body)

    def test_errors_show_the_server_message(self):
        self.assertIn('chat.push({ role: "error", text: result.payload.error', self.source)


class AiImageAttachTests(TestCase):
    """#36: attaching a poster in the AI chat."""

    def setUp(self):
        user = get_user_model().objects.create_user(username="ai-attach@yale.edu")
        self.client.force_login(user)
        self.response = self.client.get("/map/")
        self.source = static_source("core/search.js")

    def test_attach_control_accepts_the_supported_types(self):
        self.assertContains(self.response, 'id="search-ai-image" class="visually-hidden" type="file" name="image"')
        self.assertContains(self.response, 'accept="image/png,image/jpeg,image/heic,image/heif"')
        self.assertContains(self.response, 'aria-label="Remove attached image"')
        self.assertContains(self.response, 'id="search-ai-attachment" class="search-ai-attachment" hidden')

    def test_image_is_checked_in_the_browser_and_sent_with_the_message(self):
        self.assertIn("var MAX_IMAGE_BYTES = 5 * 1024 * 1024;", self.source)
        self.assertIn('if (image) body.append("image", image);', self.source)
        self.assertIn("if (aiBusy || (!message && !image)) return;", self.source)

    def test_the_chat_shows_which_image_was_sent(self):
        self.assertIn('imageName: image ? image.name : ""', self.source)
        self.assertIn('attached.className = "search-ai-attached"', self.source)


class AiVoiceTests(TestCase):
    """#36: start, text and voice input modes (browser Web Speech API)."""

    def setUp(self):
        user = get_user_model().objects.create_user(username="ai-voice@yale.edu")
        self.client.force_login(user)
        self.response = self.client.get("/map/")
        self.html = self.response.content.decode()
        self.source = static_source("core/search.js")

    def test_start_controls_attach_left_microphone_centre_type_right(self):
        controls = self.html.split('id="search-ai-controls"', 1)[1].split("</div>", 1)[0]
        attach = controls.index('class="search-ai-attach"')
        mic = controls.index('id="search-ai-mic"')
        keyboard = controls.index('id="search-ai-keyboard"')
        self.assertLess(attach, mic)
        self.assertLess(mic, keyboard)
        self.assertIn('aria-label="Speak your request"', controls)
        self.assertIn('id="search-ai-volume" class="search-ai-round" type="button" aria-pressed="false"', controls)

    def test_text_box_small_mic_and_voice_exit_start_hidden(self):
        self.assertContains(self.response, 'id="search-ai-form" class="search-ai-form" novalidate hidden')
        self.assertContains(self.response, 'aria-label="Speak instead" title="Speak instead" hidden')
        self.assertContains(self.response, 'aria-label="Leave voice mode" title="Leave voice mode" hidden')

    def test_modes_show_the_right_controls(self):
        body = self.source.split("function setInputMode(value) {", 1)[1].split("\n  }\n", 1)[0]
        self.assertIn('aiMicSmall.hidden = value !== "text";', body)   # mic top right in text mode
        self.assertIn('aiVolume.hidden = value !== "voice";', body)    # volume only in voice mode
        self.assertIn('aiVoiceExit.hidden = value !== "voice";', body)  # X only in voice mode
        self.assertIn("stopSpeaking();", body)                          # text mode never speaks

    def test_uses_the_browser_speech_api_with_a_fallback_message(self):
        self.assertIn("window.SpeechRecognition || window.webkitSpeechRecognition", self.source)
        self.assertIn("Voice isn't supported in this browser. You can type instead.", self.source)
        unsupported = self.source.split("if (!Recognition) {", 1)[1].split("}", 1)[0]
        self.assertIn('setInputMode("text")', unsupported)

    def test_live_transcript_is_sent_as_a_message(self):
        self.assertIn("current.interimResults = true;", self.source)
        self.assertIn("aiTranscript.textContent = (heard + interim).trim();", self.source)
        self.assertIn("sendToAi(text);  // the transcript becomes a chat message", self.source)

    def test_replies_are_spoken_only_in_voice_mode_and_when_not_muted(self):
        speak = self.source.split("function speak(text) {", 1)[1].split("\n  }\n", 1)[0]
        self.assertIn('if (aiInputMode !== "voice" || muted || !text || !window.speechSynthesis) return;', speak)
        self.assertIn("if (answer && answer.role !== \"user\") speak(answer.text);", self.source)

    def test_mute_toggle_and_exit(self):
        self.assertIn("muted = !muted;", self.source)
        self.assertIn('aiVolume.setAttribute("aria-pressed", String(muted));', self.source)
        self.assertIn('aiVoiceExit.addEventListener("click", function () {\n    setInputMode("text");', self.source)

    def test_volume_button_uses_a_visible_outline_icon(self):
        volume = self.html.split('id="search-ai-volume"', 1)[1].split("</button>", 1)[0]
        self.assertIn('stroke="currentColor"', volume)
        self.assertIn("aiVolume.innerHTML = muted ? VOLUME_OFF_ICON : VOLUME_ON_ICON;", self.source)

    def test_microphone_permission_denied_is_explained(self):
        self.assertIn('event.error === "not-allowed"', self.source)
        self.assertIn("Microphone access is blocked", self.source)

    def test_voice_stops_when_leaving_ai_mode_or_starting_a_new_chat(self):
        back = self.source.split('aiBack.addEventListener("click", function () {', 1)[1].split("});", 1)[0]
        self.assertIn("stopVoice();", back)
        new_chat = self.source.split('aiNew.addEventListener("click"', 1)[1].split("\n  });\n", 1)[0]
        self.assertIn("stopVoice();", new_chat)

    def test_listening_pulse_respects_reduced_motion(self):
        css = static_source("core/search.css")
        self.assertIn(".search-panel .search-ai-mic.is-listening", css)
        self.assertIn("@media (prefers-reduced-motion: reduce)", css)


class GlassIconBarTests(TestCase):
    """#65: a translucent glass panel whose header is three icon buttons."""

    def setUp(self):
        user = get_user_model().objects.create_user(username="glass@yale.edu")
        self.client.force_login(user)
        self.response = self.client.get("/map/")
        self.html = self.response.content.decode()
        self.bar = self.html.split('class="search-bar"', 1)[1].split("</div>", 1)[0]
        self.css = static_source("core/search.css")
        self.source = static_source("core/search.js")

    def test_header_has_only_filter_search_and_chevron_buttons_with_names(self):
        buttons = re.findall(r"<button\b[^>]*>", self.bar)
        ids = [re.search(r'id="([^"]+)"', b).group(1) for b in buttons]
        self.assertEqual(ids, ["search-filters-toggle", "search-ai-toggle", "search-collapse"])
        labels = [re.search(r'aria-label="([^"]+)"', b).group(1) for b in buttons]
        self.assertEqual(labels, ["Filters", "Search", "Collapse search panel"])
        # The text box, the magnifier submit, "Filters" text and "AI" toggle left the header.
        for gone in ('id="search-q"', 'id="search-submit"', ">Filters<", "AI</button>", "<input"):
            self.assertNotIn(gone, self.bar)

    def test_search_text_moved_into_the_filters(self):
        filters = self.html.split('id="search-filters"', 1)[1]
        self.assertIn('id="search-q"', filters.split('id="search-chips"', 1)[0])

    def test_chevron_points_left_and_the_collapsed_one_points_right(self):
        collapse = self.bar.split('id="search-collapse"', 1)[1].split("</button>", 1)[0]
        self.assertIn('points="15 6 9 12 15 18"', collapse)  # <
        summary = self.html.split('id="search-summary"', 1)[1].split("</button>", 1)[0]
        self.assertIn('points="9 6 15 12 9 18"', summary)    # >
        self.assertNotIn("&#8963;", self.html)  # the old up-pointing chevron

    def test_chevron_collapses_and_the_summary_expands(self):
        self.assertIn("setCollapsed(true);", self.source.split("[collapseButton, aiCollapse].forEach", 1)[1])
        self.assertIn("setCollapsed(false);", self.source.split('summary.addEventListener("click"', 1)[1])

    def test_search_icon_opens_the_ai_view_and_filter_icon_opens_the_filters(self):
        ai = self.source.split('aiToggle.addEventListener("click", function () {', 1)[1].split("});", 1)[0]
        self.assertIn('setMode("ai");', ai)
        filt = self.source.split('filtersToggle.addEventListener("click", function () {', 1)[1].split("});", 1)[0]
        self.assertIn("openFilters(", filt)

    def test_glass_is_translucent_and_blurred_with_a_legible_fallback(self):
        glass = self.css.split("@supports ((-webkit-backdrop-filter: blur(1px)) or (backdrop-filter: blur(1px))) {", 1)
        self.assertEqual(len(glass), 2, "glass @supports block missing")
        rule = glass[1].split(".search-panel {", 1)[1].split("}", 1)[0]
        self.assertIn("background: var(--search-panel-glass);", rule)
        self.assertIn("-webkit-backdrop-filter: blur(", rule)
        self.assertIn("\n    backdrop-filter: blur(", rule)
        def alpha(name):
            return float(re.search(rf"--{name}: rgba\([^)]*, ([0-9.]+)\)", self.css).group(1))

        self.assertLess(alpha("search-panel-glass"), 1)
        # Without backdrop-filter the panel stays close to opaque.
        self.assertGreaterEqual(alpha("search-panel-solid"), 0.9)
        base = self.css.split(".search-panel {", 1)[1].split("}", 1)[0]
        self.assertIn("background: var(--search-panel-solid);", base)

    def test_no_later_rule_paints_the_panel_opaque(self):
        desktop = self.css.split("@media (min-width: 768px) {", 1)[1].split("@supports", 1)[0]
        for rule in re.findall(r"\.search-panel \{([^}]*)\}", desktop):
            self.assertNotIn("background", rule)

    def test_map_pins_stay_under_the_panel(self):
        # Without its own stacking context the map's pins (z-index 2) drew over
        # the phone panel (overlay z-index 1).
        rule = static_source("core/map.css").split(".map-screen .map {", 1)[1].split("}", 1)[0]
        self.assertIn("z-index: 0;", rule)
