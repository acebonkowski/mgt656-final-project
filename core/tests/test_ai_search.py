"""
AI search (#36). OpenRouter is always mocked: either core.llm.OpenAI (the
client) or core.ai_search.llm.chat_json. The geocoder is mocked too.
"""

import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest import mock
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from openai import OpenAIError

from core import ai_search, geocoding
from core.models import AIUsage, Event

NY = ZoneInfo("America/New_York")
CONFIGURED = dict(OPENROUTER_API_KEY="fake-key", OPENROUTER_MODEL="test/model",
                  OPENROUTER_SEARCH_MODEL="")
URL = "/events/search/ai/"
NO_FILTERS = {"q": None, "categories": [], "when": None, "date_from": None, "date_to": None,
              "time_from": None, "time_to": None, "near_address": None, "radius_mi": None}


def model_output(reply="Here are some jazz events.", **filters):
    return {"reply": reply, "filters": {**NO_FILTERS, **filters}}


def fake_completion(content):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def make_event(name, days_ahead=1, **fields):
    start = timezone.now() + timedelta(days=days_ahead)
    values = {
        "image": "events/1/test.jpg", "name": name, "description": "Something happening",
        "category": "music_performance", "start_at": start, "end_at": start + timedelta(hours=2),
        "location": "Yale Commons", "latitude": "41.308300", "longitude": "-72.927900",
        "price": "0", "link": "https://example.com/event",
    }
    values.update(fields)
    return Event.objects.create(**values)


@override_settings(**CONFIGURED)
class AiSearchEndpointTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="ai-user@yale.edu",
                                                         email="ai-user@yale.edu")
        self.client.force_login(self.user)
        patcher = mock.patch("core.ai_search.llm.chat_json")
        self.chat_json = patcher.start()
        self.addCleanup(patcher.stop)
        geo = mock.patch("core.ai_search.geocoding.search", return_value=[])
        self.geocode = geo.start()
        self.addCleanup(geo.stop)

    def post(self, message="jazz tonight", **extra):
        return self.client.post(URL, {"message": message, **extra})

    # --- Access and input --------------------------------------------------------

    def test_requires_login_and_post(self):
        self.client.logout()
        self.assertEqual(self.post().status_code, 302)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(URL).status_code, 405)
        self.chat_json.assert_not_called()

    def test_empty_or_long_message_is_rejected_without_calling_the_ai(self):
        self.assertEqual(self.post("   ").status_code, 400)
        response = self.post("x" * 301)
        self.assertEqual(response.status_code, 400)
        self.assertIn("300 characters", response.json()["error"])
        self.chat_json.assert_not_called()
        self.chat_json.return_value = model_output()
        self.assertEqual(self.post("x" * 300).status_code, 200)  # exactly 300 is allowed

    @override_settings(OPENROUTER_API_KEY="")
    def test_not_configured_is_a_friendly_503_and_uses_no_quota(self):
        response = self.post()
        self.assertEqual(response.status_code, 503)
        self.assertIn("manual search still works", response.json()["error"])
        self.assertFalse(AIUsage.objects.exists())

    # --- Results come only from the database ----------------------------------------

    def test_returns_reply_filters_and_matching_events(self):
        make_event("Jazz Night", category="music_performance")
        make_event("Jazz Brunch", category="food_drink")
        make_event("Book Talk", category="talks_panels")
        self.chat_json.return_value = model_output(q="jazz", categories=["music_performance"])
        response = self.post("live jazz music")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["reply"], "Here are some jazz events.")
        self.assertEqual(data["filters"], {"q": "jazz", "category": ["music_performance"]})
        self.assertEqual([e["name"] for e in data["events"]], ["Jazz Night"])
        self.assertEqual(data["count"], 1)
        self.assertEqual(set(data["events"][0]), {
            "id", "name", "location", "latitude", "longitude", "price", "category",
            "category_label", "start_at", "end_at", "image_url", "detail_url", "popup_url"})

    def test_events_the_ai_mentions_but_the_database_lacks_never_appear(self):
        make_event("Jazz Night")
        self.chat_json.return_value = model_output(
            reply="Try the Imaginary Gala and Jazz Night!", q="jazz")
        data = self.post().json()
        self.assertEqual([e["name"] for e in data["events"]], ["Jazz Night"])
        self.assertFalse(Event.objects.filter(name__icontains="Imaginary").exists())

    def test_past_events_are_never_returned(self):
        make_event("Old Jazz", days_ahead=-3)
        self.chat_json.return_value = model_output(q="jazz")
        self.assertEqual(self.post().json()["events"], [])

    def test_invalid_filter_values_are_dropped(self):
        make_event("Jazz Night")
        self.chat_json.return_value = model_output(
            q="jazz", categories=["music_performance", "not_a_category"],
            date_from="next friday", time_from="20:00", time_to="18:00")
        data = self.post().json()
        self.assertEqual(data["filters"], {"q": "jazz", "category": ["music_performance"],
                                           "time_from": "20:00"})

    def test_quick_pick_from_the_ai(self):
        self.chat_json.return_value = model_output(when="weekend")
        self.assertEqual(self.post("this weekend").json()["filters"], {"when": "weekend"})

    def test_address_is_geocoded_into_a_radius_filter(self):
        self.geocode.return_value = [{"address": "Toad's Place, 300 York St",
                                      "latitude": 41.3115, "longitude": -72.9302}]
        make_event("Near", latitude="41.311500", longitude="-72.930200")
        make_event("Far", latitude="41.250000", longitude="-72.900000")
        self.chat_json.return_value = model_output(near_address="Toad's Place", radius_mi="1")
        data = self.post("near Toad's").json()
        self.geocode.assert_called_once_with("Toad's Place")
        self.assertEqual(data["filters"]["near_label"], "Toad's Place, 300 York St")
        self.assertEqual([e["name"] for e in data["events"]], ["Near"])

    def test_unknown_address_is_skipped_with_a_note(self):
        self.geocode.side_effect = geocoding.GeocodingUnavailable("down")
        make_event("Jazz Night")
        self.chat_json.return_value = model_output(q="jazz", near_address="Atlantis")
        data = self.post().json()
        self.assertNotIn("near_lat", data["filters"])
        self.assertIn("Atlantis", data["notes"][0])
        self.assertEqual(len(data["events"]), 1)

    def test_missing_reply_gets_a_default(self):
        self.chat_json.return_value = {"reply": "  ", "filters": NO_FILTERS}
        self.assertEqual(self.post().json()["reply"], ai_search.DEFAULT_REPLY)

    # --- Failures -------------------------------------------------------------------

    def test_unreadable_ai_output_is_a_friendly_502_and_still_counts(self):
        from core.llm import LLMInvalidResponse

        self.chat_json.side_effect = LLMInvalidResponse("bad")
        response = self.post()
        self.assertEqual(response.status_code, 502)
        self.assertIn("didn't make sense", response.json()["error"])
        self.assertEqual(AIUsage.objects.count(), 1)

    def test_provider_failure_is_a_friendly_503_and_keeps_history(self):
        from core.llm import LLMUnavailable

        self.chat_json.return_value = model_output(q="jazz")
        self.post("jazz")
        self.chat_json.side_effect = LLMUnavailable("down")
        response = self.post("and tomorrow?")
        self.assertEqual(response.status_code, 503)
        history = self.client.session[ai_search.HISTORY_SESSION_KEY]
        self.assertEqual([m["content"] for m in history if m["role"] == "user"], ["jazz"])

    @override_settings(AI_SEARCH_PER_MINUTE_LIMIT=1)
    def test_limit_reached_is_429_and_the_ai_is_not_called(self):
        self.chat_json.return_value = model_output()
        self.post()
        response = self.post()
        self.assertEqual(response.status_code, 429)
        self.assertTrue(response.json()["limit"])
        self.assertIn("Wait a minute", response.json()["error"])
        self.assertEqual(self.chat_json.call_count, 1)

    # --- Conversation ---------------------------------------------------------------

    def test_only_the_last_six_turns_are_sent(self):
        self.chat_json.return_value = model_output()
        with override_settings(AI_SEARCH_PER_MINUTE_LIMIT=100, AI_SEARCH_DAILY_LIMIT=100):
            for i in range(8):
                self.post(f"message {i}")
        messages = self.chat_json.call_args.args[0]
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[-1], {"role": "user", "content": "message 7"})
        self.assertEqual(len(messages), 1 + 12 + 1)  # system + 6 earlier turns + new message
        self.assertEqual(messages[1]["content"], "message 1")
        # The model sees its own earlier filters, so follow-ups can refine them.
        self.assertEqual(json.loads(messages[2]["content"])["filters"], NO_FILTERS)

    def test_new_chat_clears_the_history(self):
        self.chat_json.return_value = model_output()
        self.post()
        self.assertIn(ai_search.HISTORY_SESSION_KEY, self.client.session)
        response = self.client.post("/events/search/ai/reset/")
        self.assertEqual(response.json(), {"ok": True})
        self.assertNotIn(ai_search.HISTORY_SESSION_KEY, self.client.session)


@override_settings(**CONFIGURED)
class AiSearchThroughClientTests(TestCase):
    """End to end through core.llm with the OpenAI client mocked."""

    def setUp(self):
        user = get_user_model().objects.create_user(username="client-user@yale.edu")
        self.client.force_login(user)
        patcher = mock.patch("core.llm.OpenAI")
        self.create = patcher.start().return_value.chat.completions.create
        self.addCleanup(patcher.stop)

    def test_structured_request_and_reply(self):
        make_event("Jazz Night")
        self.create.return_value = fake_completion(json.dumps(model_output(q="jazz")))
        data = self.client.post(URL, {"message": "jazz"}).json()
        self.assertEqual([e["name"] for e in data["events"]], ["Jazz Night"])
        kwargs = self.create.call_args.kwargs
        self.assertEqual(kwargs["model"], "test/model")
        self.assertEqual(kwargs["response_format"]["type"], "json_schema")
        self.assertTrue(kwargs["response_format"]["json_schema"]["strict"])

    @override_settings(OPENROUTER_SEARCH_MODEL="test/vision-model")
    def test_search_model_override(self):
        self.create.return_value = fake_completion(json.dumps(model_output()))
        self.client.post(URL, {"message": "anything"})
        self.assertEqual(self.create.call_args.kwargs["model"], "test/vision-model")

    def test_provider_error_is_friendly(self):
        self.create.side_effect = OpenAIError("connection reset")
        with self.assertLogs("core.llm", "WARNING"):
            response = self.client.post(URL, {"message": "jazz"})
        self.assertEqual(response.status_code, 503)

    def test_non_json_reply_is_friendly(self):
        self.create.return_value = fake_completion("Sure! Here are some events: ...")
        with self.assertLogs("core.llm", "WARNING"):
            response = self.client.post(URL, {"message": "jazz"})
        self.assertEqual(response.status_code, 502)


class PromptTests(TestCase):
    def test_prompt_has_todays_new_york_date_and_the_categories(self):
        late = datetime(2026, 11, 18, 23, 30, tzinfo=NY)  # already the 19th in UTC
        prompt = ai_search.system_prompt(late)
        self.assertIn("Wednesday, November 18, 2026", prompt)
        self.assertIn("23:30", prompt)
        for value in Event.Category.values:
            self.assertIn(value, prompt)
        self.assertIn("Never name, list or invent specific events", prompt)

    def test_schema_allows_only_known_categories_and_radii(self):
        filters = ai_search.RESPONSE_SCHEMA["properties"]["filters"]["properties"]
        self.assertEqual(filters["categories"]["items"]["enum"], list(Event.Category.values))
        self.assertEqual(filters["radius_mi"]["enum"], ["0.5", "1", "2", "5", None])
