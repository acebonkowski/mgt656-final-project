"""
Recurring searches (#37), stage A: saving, the daily scan, delete and update.
The AI is mocked (core.ai_search.llm.chat_json) and nothing touches the network.
"""

import io
import itertools
import json
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core import saved_searches
from core.event_import import runner
from core.models import Event, EventAttendance, SavedSearch, SearchSuggestion

CONFIGURED = dict(OPENROUTER_API_KEY="fake-key", OPENROUTER_MODEL="test/model",
                  OPENROUTER_SEARCH_MODEL="")
MUSIC = {"category": ["music_performance"]}
ART = {"category": ["art_film_exhibits"]}
NO_FILTERS = {"q": None, "categories": [], "when": None, "date_from": None, "date_to": None,
              "time_from": None, "time_to": None, "near_address": None, "radius_mi": None}
counter = itertools.count(1)


def make_event(name="Jazz Night", category="music_performance", **fields):
    n = next(counter)
    start = timezone.now() + timedelta(days=2, minutes=n)
    values = {
        "image": "default", "name": name, "description": "Something happening",
        "category": category, "start_at": start, "end_at": start + timedelta(hours=2),
        "location": f"Yale Commons {n}", "latitude": "41.308300", "longitude": "-72.927900",
        "price": "0", "link": "https://example.com/event",
    }
    values.update(fields)
    return Event.objects.create(**values)


def make_user(name):
    return get_user_model().objects.create_user(username=f"{name}@yale.edu", email=f"{name}@yale.edu")


def save(client, filters, label="", **extra):
    return client.post(reverse("save_search"), {"filters": json.dumps(filters), "label": label, **extra})


class SavedSearchTestCase(TestCase):
    def setUp(self):
        self.user = make_user("ana")
        self.other = make_user("ben")
        self.client.force_login(self.user)

    def saved(self, filters=MUSIC, user=None, **fields):
        return SavedSearch.objects.create(
            user=user or self.user, label="Jazz", filters=filters,
            last_seen_event_id=Event.objects.order_by("-pk").values_list("pk", flat=True).first() or 0,
            **fields,
        )

    def suggested(self, user=None):
        rows = SearchSuggestion.objects.filter(user=user or self.user)
        return sorted(rows.values_list("event__name", flat=True))


class DailyScanTests(SavedSearchTestCase):
    def test_new_matching_event_becomes_a_suggestion(self):
        self.saved()
        make_event("Jazz Night")
        counts = saved_searches.run_saved_searches()
        self.assertEqual(self.suggested(), ["Jazz Night"])
        self.assertEqual((counts["searches"], counts["suggested"], counts["failed"]), (1, 1, 0))

    def test_events_that_existed_when_saved_are_not_suggested(self):
        make_event("Already There")
        self.saved()
        make_event("Brand New")
        saved_searches.run_saved_searches()
        self.assertEqual(self.suggested(), ["Brand New"])

    def test_skips_events_that_should_not_be_suggested(self):
        self.saved()
        not_going = make_event("Not Going")
        EventAttendance.objects.create(user=self.user, event=not_going,
                                       status=EventAttendance.Status.NOT_GOING)
        going = make_event("Going")
        EventAttendance.objects.create(user=self.user, event=going,
                                       status=EventAttendance.Status.GOING)
        make_event("Mine", creator=self.user)
        past_start = timezone.now() - timedelta(days=3)
        make_event("Ended", start_at=past_start, end_at=past_start + timedelta(hours=1))
        make_event("Wrong Category", category="art_film_exhibits")
        make_event("Match")
        saved_searches.run_saved_searches()
        self.assertEqual(self.suggested(), ["Match"])

    def test_another_users_not_going_does_not_hide_the_event_for_me(self):
        self.saved()
        event = make_event("Shared")
        EventAttendance.objects.create(user=self.other, event=event,
                                       status=EventAttendance.Status.NOT_GOING)
        saved_searches.run_saved_searches()
        self.assertEqual(self.suggested(), ["Shared"])

    def test_running_twice_adds_nothing(self):
        self.saved()
        make_event()
        saved_searches.run_saved_searches()
        counts = saved_searches.run_saved_searches()
        self.assertEqual(SearchSuggestion.objects.count(), 1)
        self.assertEqual(counts["suggested"], 0)

    def test_hidden_suggestion_is_never_added_again(self):
        self.saved()
        event = make_event("Hidden One")
        saved_searches.run_saved_searches()
        SearchSuggestion.objects.filter(event=event).update(hidden=True)
        # Rewinding the marker makes the scan consider the event again.
        SavedSearch.objects.update(last_seen_event_id=0)
        saved_searches.run_saved_searches()
        row = SearchSuggestion.objects.get()
        self.assertTrue(row.hidden)

    def test_two_searches_finding_the_same_event_make_one_suggestion(self):
        self.saved(MUSIC)
        self.saved({"category": ["music_performance", "art_film_exhibits"]})
        make_event()
        saved_searches.run_saved_searches()
        self.assertEqual(SearchSuggestion.objects.count(), 1)

    def test_suggestions_are_per_user(self):
        self.saved()
        self.saved(user=self.other)
        make_event()
        saved_searches.run_saved_searches()
        self.assertEqual(len(self.suggested()), 1)
        self.assertEqual(len(self.suggested(self.other)), 1)

    def test_caps_new_suggestions_per_search_per_run(self):
        self.saved()
        for _ in range(saved_searches.MAX_SUGGESTIONS_PER_RUN + 3):
            make_event()
        counts = saved_searches.run_saved_searches()
        self.assertEqual(SearchSuggestion.objects.count(), saved_searches.MAX_SUGGESTIONS_PER_RUN)
        self.assertEqual(counts["suggested"], saved_searches.MAX_SUGGESTIONS_PER_RUN)

    def test_one_failing_search_does_not_stop_the_others(self):
        first = self.saved()
        self.saved(user=self.other)
        make_event()
        real = saved_searches.scan_search

        def flaky(saved, now=None):
            if saved.pk == first.pk:
                raise RuntimeError("boom")
            return real(saved, now=now)

        with mock.patch.object(saved_searches, "scan_search", side_effect=flaky):
            counts = saved_searches.run_saved_searches()
        self.assertEqual((counts["failed"], counts["suggested"]), (1, 1))
        self.assertEqual(len(self.suggested(self.other)), 1)

    def test_invalid_stored_filters_are_skipped(self):
        self.saved({"category": ["not_a_category"]})
        make_event()
        saved_searches.run_saved_searches()
        self.assertEqual(SearchSuggestion.objects.count(), 0)

    def test_command_prints_the_counts(self):
        self.saved()
        make_event()
        out = io.StringIO()
        call_command("run_saved_searches", stdout=out)
        self.assertEqual(json.loads(out.getvalue())["suggested"], 1)


class ChainedIntoImportTests(TestCase):
    def run_background(self, import_effect=None, searches_effect=None):
        with mock.patch.object(runner, "close_old_connections"), \
                mock.patch.object(runner, "run_import", side_effect=import_effect) as run_import, \
                mock.patch.object(runner, "run_saved_searches", side_effect=searches_effect) as scan:
            runner.background_import("token")
        return run_import, scan

    def test_saved_searches_run_after_the_import(self):
        run_import, scan = self.run_background()
        run_import.assert_called_once_with("token")
        scan.assert_called_once_with()

    def test_failing_import_still_runs_saved_searches(self):
        _, scan = self.run_background(import_effect=RuntimeError("feed down"))
        scan.assert_called_once_with()

    def test_failing_saved_searches_do_not_break_the_import_thread(self):
        self.run_background(searches_effect=RuntimeError("boom"))  # must not raise


@override_settings(**CONFIGURED)
class SaveSearchEndpointTests(SavedSearchTestCase):
    def test_saves_the_validated_filters(self):
        response = save(self.client, MUSIC, label="  jazz   this week ")
        self.assertEqual(response.status_code, 201)
        saved = SavedSearch.objects.get()
        self.assertEqual((saved.user, saved.label, saved.filters), (self.user, "jazz this week", MUSIC))

    def test_baseline_is_the_newest_event(self):
        event = make_event()
        save(self.client, MUSIC)
        self.assertEqual(SavedSearch.objects.get().last_seen_event_id, event.pk)

    def test_unknown_and_unsafe_filters_are_dropped(self):
        save(self.client, {**MUSIC, "include_not_going": True, "area": "1,2,3", "evil": "x"})
        self.assertEqual(SavedSearch.objects.get().filters, MUSIC)

    def test_invalid_filter_values_are_dropped_and_empty_searches_refused(self):
        response = save(self.client, {"category": ["nope"], "date_from": "next friday"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(save(self.client, {}).status_code, 400)
        self.assertEqual(self.client.post(reverse("save_search"), {"filters": "not json"}).status_code, 400)
        self.assertEqual(SavedSearch.objects.count(), 0)

    def test_saving_the_same_search_twice_keeps_one(self):
        first = save(self.client, MUSIC)
        second = save(self.client, MUSIC)
        self.assertEqual((first.status_code, second.status_code), (201, 200))
        self.assertEqual(SavedSearch.objects.count(), 1)

    def test_limit_per_user(self):
        for n in range(saved_searches.MAX_SEARCHES_PER_USER):
            self.assertEqual(save(self.client, {"q": f"topic{n}"}).status_code, 201)
        self.assertEqual(save(self.client, {"q": "one more"}).status_code, 400)
        self.client.force_login(self.other)
        self.assertEqual(save(self.client, {"q": "one more"}).status_code, 201)

    def test_requires_login_and_post(self):
        self.client.logout()
        self.assertEqual(save(self.client, MUSIC).status_code, 302)
        self.assertEqual(SavedSearch.objects.count(), 0)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("save_search")).status_code, 405)

    def test_filters_from_the_mocked_ai_chat_can_be_saved_and_scanned(self):
        with mock.patch("core.ai_search.llm.chat_json") as chat_json, \
                mock.patch("core.ai_search.geocoding.search", return_value=[]):
            chat_json.return_value = {
                "reply": "Looking for jazz.",
                "filters": {**NO_FILTERS, "q": "jazz", "categories": ["music_performance"]},
            }
            answer = self.client.post("/events/search/ai/", {"message": "jazz nights"}).json()
        response = save(self.client, answer["filters"], label="jazz nights")
        self.assertEqual(response.status_code, 201)
        make_event("Late Jazz Night")
        saved_searches.run_saved_searches()
        self.assertEqual(self.suggested(), ["Late Jazz Night"])


class DeleteAndUpdateTests(SavedSearchTestCase):
    def delete(self, saved, **data):
        return self.client.post(reverse("delete_saved_search", args=[saved.pk]), data)

    def update(self, saved, filters=ART, **data):
        return self.client.post(
            reverse("update_saved_search", args=[saved.pk]),
            {"filters": json.dumps(filters), **data},
        )

    def test_delete_needs_confirmation(self):
        saved = self.saved()
        for data in ({}, {"confirm": "0"}, {"confirm": "yes"}):
            self.assertEqual(self.delete(saved, **data).status_code, 409)
        self.assertTrue(SavedSearch.objects.filter(pk=saved.pk).exists())
        self.assertEqual(self.delete(saved, confirm="1").status_code, 302)  # back to My Queries
        self.assertFalse(SavedSearch.objects.filter(pk=saved.pk).exists())

    def test_delete_removes_its_visible_suggestions_but_keeps_hidden_ones(self):
        saved = self.saved()
        make_event("Shown")
        hidden = make_event("Hidden")
        saved_searches.run_saved_searches()
        SearchSuggestion.objects.filter(event=hidden).update(hidden=True)
        self.delete(saved, confirm="1")
        row = SearchSuggestion.objects.get()
        self.assertEqual((row.event, row.hidden, row.search), (hidden, True, None))

    def test_update_needs_confirmation(self):
        saved = self.saved()
        self.assertEqual(self.update(saved).status_code, 409)
        self.assertEqual(self.update(saved, confirm="no").status_code, 409)
        saved.refresh_from_db()
        self.assertEqual(saved.filters, MUSIC)
        self.assertEqual(self.update(saved, confirm="1", label="Art").status_code, 200)
        saved.refresh_from_db()
        self.assertEqual((saved.filters, saved.label), (ART, "Art"))

    def test_update_resets_the_baseline_and_drops_old_suggestions(self):
        saved = self.saved()
        make_event("Old Match")
        saved_searches.run_saved_searches()
        newest = make_event("Newest", category="art_film_exhibits")
        self.update(saved, confirm="1")
        saved.refresh_from_db()
        self.assertEqual(saved.last_seen_event_id, newest.pk)
        self.assertEqual(SearchSuggestion.objects.count(), 0)
        saved_searches.run_saved_searches()
        self.assertEqual(SearchSuggestion.objects.count(), 0)  # "Newest" predates the edit

    def test_update_with_bad_filters_changes_nothing(self):
        saved = self.saved()
        self.assertEqual(self.update(saved, {}, confirm="1").status_code, 400)
        saved.refresh_from_db()
        self.assertEqual(saved.filters, MUSIC)

    def test_a_user_cannot_change_someone_elses_search(self):
        theirs = self.saved(user=self.other)
        self.assertEqual(self.delete(theirs, confirm="1").status_code, 404)
        self.assertEqual(self.update(theirs, confirm="1").status_code, 404)
        theirs.refresh_from_db()
        self.assertEqual(theirs.filters, MUSIC)

    def test_update_is_post_only_and_login_is_required(self):
        saved = self.saved()
        self.assertEqual(self.client.get(reverse("update_saved_search", args=[saved.pk])).status_code, 405)
        self.client.logout()
        self.assertEqual(self.delete(saved, confirm="1").status_code, 302)
        self.assertEqual(self.update(saved, confirm="1").status_code, 302)
        self.assertTrue(SavedSearch.objects.filter(pk=saved.pk).exists())
