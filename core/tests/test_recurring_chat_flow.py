"""
Recurring searches (#37), stage C, server side: what the Ask AI panel needs to
offer "keep looking every day" and to edit a saved search with a confirmation.
The browser code itself is plain JavaScript; these tests cover everything it
relies on: the panel's data attributes, the CSRF token, the save and update
endpoints, and the whole flow with the AI mocked (no network).
"""

import json
import re
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from core import saved_searches
from core.models import SavedSearch
from core.tests.test_ui_polish import apa_violations

CONFIGURED = dict(OPENROUTER_API_KEY="fake-key", OPENROUTER_MODEL="test/model",
                  OPENROUTER_SEARCH_MODEL="")
NO_FILTERS = {"q": None, "categories": [], "when": None, "date_from": None, "date_to": None,
              "time_from": None, "time_to": None, "near_address": None, "radius_mi": None}
SEARCH_JS = Path(__file__).resolve().parent.parent / "static" / "core" / "search.js"


def make_user(name):
    return get_user_model().objects.create_user(username=f"{name}@yale.edu", email=f"{name}@yale.edu")


def panel_tag(html):
    match = re.search(r'<section id="search-panel".*?>', html, re.S)
    assert match, "search panel not found"
    return match.group(0)


def csrf_token(html):
    form = re.search(r'<form id="search-ai-form".*?</form>', html, re.S).group(0)
    return re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', form).group(1)


@override_settings(**CONFIGURED)
class RecurringChatFlowTests(TestCase):
    def setUp(self):
        self.user = make_user("ana")
        self.other = make_user("ben")
        self.client.force_login(self.user)
        patcher = mock.patch("core.ai_search.llm.chat_json")
        self.chat_json = patcher.start()
        self.addCleanup(patcher.stop)
        geo = mock.patch("core.ai_search.geocoding.search", return_value=[])
        geo.start()
        self.addCleanup(geo.stop)

    def ask(self, message, **filters):
        """One Ask AI exchange (mocked model). Returns the JSON the browser receives."""
        self.chat_json.return_value = {"reply": "Looking.", "filters": {**NO_FILTERS, **filters}}
        response = self.client.post("/events/search/ai/", {"message": message})
        self.assertEqual(response.status_code, 200)
        return response.json()

    def browser_post(self, url, answer, label, **extra):
        """What search.js sends: the answer's filters as JSON, the student's message, the CSRF header."""
        return self.client.post(url, {"filters": json.dumps(answer["filters"]), "label": label, **extra})


class PanelAttributesTests(RecurringChatFlowTests):
    def test_panel_always_knows_where_to_save(self):
        tag = panel_tag(self.client.get("/map/?mode=ai").content.decode())
        self.assertIn(f'data-save-url="{reverse("save_search")}"', tag)
        self.assertNotIn("data-edit-id", tag)
        self.assertNotIn("data-update-url", tag)

    def test_edit_link_from_my_queries_puts_the_search_in_edit_mode(self):
        saved = SavedSearch.objects.create(user=self.user, label="Jazz this week",
                                           filters={"q": "jazz"})
        tag = panel_tag(self.client.get(f"/map/?mode=ai&edit={saved.pk}").content.decode())
        self.assertIn(f'data-edit-id="{saved.pk}"', tag)
        self.assertIn('data-edit-label="Jazz this week"', tag)
        self.assertIn(f'data-update-url="{reverse("update_saved_search", args=[saved.pk])}"', tag)

    def test_the_edit_label_is_escaped(self):
        saved = SavedSearch.objects.create(user=self.user, label='"><script>alert(1)</script>',
                                           filters={"q": "x"})
        html = self.client.get(f"/map/?mode=ai&edit={saved.pk}").content.decode()
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&quot;&gt;&lt;script&gt;", panel_tag(html))

    def test_someone_elses_search_or_a_bad_id_is_ignored(self):
        theirs = SavedSearch.objects.create(user=self.other, label="Ben's secret", filters={"q": "x"})
        for value in (theirs.pk, "abc", "-1", "0", "9" * 40, ""):
            with self.subTest(edit=value):
                response = self.client.get(f"/map/?mode=ai&edit={value}")
                self.assertEqual(response.status_code, 200)
                self.assertNotIn("data-edit-id", panel_tag(response.content.decode()))
                self.assertNotIn("Ben&#x27;s secret", response.content.decode())

    def test_logged_out_visitors_still_go_to_login(self):
        self.client.logout()
        saved = SavedSearch.objects.create(user=self.user, label="Mine", filters={"q": "x"})
        self.assertEqual(self.client.get(f"/map/?mode=ai&edit={saved.pk}").status_code, 302)

    def test_the_ai_form_carries_the_csrf_token_the_script_reads(self):
        self.assertTrue(csrf_token(self.client.get("/map/").content.decode()))


class SaveFlowTests(RecurringChatFlowTests):
    def test_asking_then_saying_yes_saves_the_search_the_ai_used(self):
        answer = self.ask("jazz nights this weekend", q="jazz", categories=["music_performance"],
                          when="weekend")
        response = self.browser_post(reverse("save_search"), answer, "jazz nights this weekend")
        self.assertEqual(response.status_code, 201)
        saved = SavedSearch.objects.get()
        self.assertEqual(saved.label, "jazz nights this weekend")
        self.assertEqual(saved.filters["q"], "jazz")
        self.assertEqual(saved.filters["when"], "weekend")
        self.assertEqual(saved.filters["category"], ["music_performance"])

    def test_saying_yes_twice_does_not_duplicate(self):
        answer = self.ask("jazz", q="jazz")
        first = self.browser_post(reverse("save_search"), answer, "jazz")
        second = self.browser_post(reverse("save_search"), answer, "jazz")
        self.assertEqual((first.status_code, second.status_code), (201, 200))
        self.assertEqual(SavedSearch.objects.count(), 1)

    def test_an_answer_without_filters_cannot_be_saved(self):
        answer = self.ask("what's the weather?")  # the AI says it only finds events
        self.assertEqual(answer["filters"], {})
        response = self.browser_post(reverse("save_search"), answer, "what's the weather?")
        self.assertEqual(response.status_code, 400)
        self.assertIn("filter", response.json()["error"])
        self.assertEqual(SavedSearch.objects.count(), 0)

    def test_a_long_message_is_trimmed_to_a_label(self):
        answer = self.ask("jazz", q="jazz")
        self.browser_post(reverse("save_search"), answer, "very " * 100)
        self.assertLessEqual(len(SavedSearch.objects.get().label), saved_searches.MAX_LABEL_CHARS)

    def test_the_script_can_save_with_only_the_csrf_header(self):
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.user)
        token = csrf_token(strict.get("/map/").content.decode())
        body = {"filters": json.dumps({"q": "jazz"}), "label": "jazz"}
        self.assertEqual(strict.post(reverse("save_search"), body).status_code, 403)
        self.assertEqual(strict.post(reverse("save_search"), body, HTTP_X_CSRFTOKEN=token).status_code, 201)
        self.assertEqual(SavedSearch.objects.count(), 1)


class EditConfirmFlowTests(RecurringChatFlowTests):
    def setUp(self):
        super().setUp()
        self.saved = SavedSearch.objects.create(
            user=self.user, label="jazz nights", filters={"q": "jazz"})
        self.url = reverse("update_saved_search", args=[self.saved.pk])

    def test_replacing_needs_the_confirmation_and_then_replaces(self):
        answer = self.ask("poetry readings instead", q="poetry")
        refused = self.browser_post(self.url, answer, "poetry readings instead")  # "Replace Saved Search" only
        self.assertEqual(refused.status_code, 409)
        self.saved.refresh_from_db()
        self.assertEqual((self.saved.label, self.saved.filters), ("jazz nights", {"q": "jazz"}))

        confirmed = self.browser_post(self.url, answer, "poetry readings instead", confirm="1")  # "Yes, Replace"
        self.assertEqual(confirmed.status_code, 200)
        self.saved.refresh_from_db()
        self.assertEqual((self.saved.label, self.saved.filters),
                         ("poetry readings instead", {"q": "poetry"}))

    def test_the_new_search_shows_in_my_queries_and_the_old_one_is_gone(self):
        answer = self.ask("poetry readings", q="poetry", categories=["talks_panels"])
        self.browser_post(self.url, answer, "poetry readings", confirm="1")
        html = self.client.get("/my-events/suggested/?tab=queries").content.decode()
        self.assertIn("poetry readings", html)
        self.assertIn("“poetry”", html)
        self.assertNotIn("jazz nights", html)
        self.assertEqual(SavedSearch.objects.count(), 1)

    def test_an_answer_without_filters_cannot_replace_the_search(self):
        answer = self.ask("tell me a joke")
        response = self.browser_post(self.url, answer, "tell me a joke", confirm="1")
        self.assertEqual(response.status_code, 400)
        self.saved.refresh_from_db()
        self.assertEqual(self.saved.filters, {"q": "jazz"})

    def test_someone_else_cannot_replace_my_search_even_with_the_confirmation(self):
        answer = self.ask("anything", q="other")
        self.client.force_login(self.other)
        response = self.browser_post(self.url, answer, "anything", confirm="1")
        self.assertEqual(response.status_code, 404)
        self.saved.refresh_from_db()
        self.assertEqual(self.saved.filters, {"q": "jazz"})

    def test_the_script_can_replace_with_only_the_csrf_header(self):
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.user)
        token = csrf_token(strict.get(f"/map/?mode=ai&edit={self.saved.pk}").content.decode())
        body = {"filters": json.dumps({"q": "poetry"}), "label": "poetry", "confirm": "1"}
        self.assertEqual(strict.post(self.url, body).status_code, 403)
        self.assertEqual(strict.post(self.url, body, HTTP_X_CSRFTOKEN=token).status_code, 200)


class ScriptContractTests(TestCase):
    """The few facts about search.js the server tests above depend on."""

    source = SEARCH_JS.read_text(encoding="utf-8")

    def test_the_script_posts_what_the_endpoints_expect(self):
        for needle in ('panel.dataset.saveUrl', 'panel.dataset.updateUrl', 'panel.dataset.editId',
                       'body.append("filters", JSON.stringify(entry.filters))',
                       'body.append("label"', '"X-CSRFToken": csrfToken()'):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.source)

    def test_only_the_confirmed_replace_sends_confirm(self):
        self.assertEqual(self.source.count('body.append("confirm", "1")'), 1)
        self.assertIn('send(panel.dataset.updateUrl, true)', self.source)
        self.assertNotIn('send(panel.dataset.updateUrl, false)', self.source)

    def test_button_labels_follow_title_case(self):
        for label in ("Yes", "No Thanks", "Replace Saved Search", "Yes, Replace", "Cancel"):
            with self.subTest(label=label):
                self.assertEqual(apa_violations(label), [])
                self.assertIn(f'"{label}"', self.source)
