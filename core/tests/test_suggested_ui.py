"""
Recurring searches (#37), stage B: the Suggested row, the hide cross, the
Suggested Events and My Queries tabs and the delete confirmation page.
Server-rendered only. No AI or network.
"""

import re
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from core import saved_searches
from core.models import Event, EventAttendance, SavedSearch, SearchSuggestion

DASHBOARD = "/my-events/"
SUGGESTED = "/my-events/suggested/"
QUERIES = "/my-events/suggested/?tab=queries"
MUSIC = {"category": ["music_performance"]}


def make_user(name):
    return get_user_model().objects.create_user(username=f"{name}@yale.edu", email=f"{name}@yale.edu")


def make_event(name, days_ahead=2, **fields):
    start = timezone.now() + timedelta(days=days_ahead)
    values = {
        "image": "default", "name": name, "description": "Something happening",
        "category": "music_performance", "start_at": start, "end_at": start + timedelta(hours=2),
        "location": f"Place for {name}", "latitude": "41.308300", "longitude": "-72.927900",
        "price": "0", "link": "https://example.com/event",
    }
    values.update(fields)
    return Event.objects.create(**values)


class SuggestedTestCase(TestCase):
    def setUp(self):
        self.user = make_user("ana")
        self.other = make_user("ben")
        self.client.force_login(self.user)

    def suggest(self, event, user=None, hidden=False, search=None):
        return SearchSuggestion.objects.create(user=user or self.user, event=event,
                                               hidden=hidden, search=search)

    def page(self, url):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def row(self, html, key="suggested"):
        match = re.search(rf'<section class="my-events-row" aria-labelledby="row-{key}">(.*?)</section>',
                          html, re.S)
        self.assertIsNotNone(match, key)
        return match.group(1)

    def hide(self, event, **extra):
        return self.client.post(reverse("hide_suggestion", args=[event.pk]), extra)


class SuggestedRowTests(SuggestedTestCase):
    def test_row_sits_below_upcoming_and_above_hosted(self):
        titles = re.findall(r'<h2 id="row-(\w+)">', self.page(DASHBOARD))
        self.assertEqual(titles, ["upcoming", "suggested", "hosted", "favorites"])

    def test_empty_row_shows_its_message_and_view_all_link(self):
        row = self.row(self.page(DASHBOARD))
        self.assertIn("No suggestions yet", row)
        self.assertIn('href="/my-events/suggested/"', row)

    def test_row_lists_my_suggestions_only(self):
        self.suggest(make_event("For Me"))
        self.suggest(make_event("For Ben"), user=self.other)
        make_event("Not Suggested")
        row = self.row(self.page(DASHBOARD))
        self.assertIn("For Me", row)
        self.assertNotIn("For Ben", row)
        self.assertNotIn("Not Suggested", row)

    def test_cards_are_earliest_first_with_the_usual_fields(self):
        self.suggest(make_event("Later", days_ahead=5))
        self.suggest(make_event("Sooner", days_ahead=2))
        row = self.row(self.page(DASHBOARD))
        self.assertLess(row.index("Sooner"), row.index("Later"))
        self.assertIn("my-event-card", row)
        self.assertIn("Place for Sooner", row)
        self.assertIn("Free", row)

    def test_row_stops_at_ten_and_view_all_lists_everything(self):
        for number in range(13):
            self.suggest(make_event(f"Suggestion {number:02d}", days_ahead=number + 1))
        self.assertEqual(self.row(self.page(DASHBOARD)).count('class="my-event-card"'), 10)
        self.assertEqual(self.page(SUGGESTED).count('class="my-event-card"'), 13)

    def test_ended_and_not_going_events_drop_out_at_display_time(self):
        gone = make_event("Ended Later")
        self.suggest(gone)
        Event.objects.filter(pk=gone.pk).update(start_at=timezone.now() - timedelta(hours=3),
                                                end_at=timezone.now() - timedelta(hours=1))
        skipped = make_event("Skip This")
        self.suggest(skipped)
        EventAttendance.objects.create(user=self.user, event=skipped, status="not_going")
        self.suggest(make_event("Still Here"))
        html = self.page(DASHBOARD)
        self.assertIn("Still Here", html)
        self.assertNotIn("Ended Later", html)
        self.assertNotIn("Skip This", html)
        self.assertNotIn("Ended Later", self.page(SUGGESTED))

    def test_each_card_has_a_hide_cross_that_posts(self):
        event = make_event("Hide Me")
        self.suggest(event)
        row = self.row(self.page(DASHBOARD))
        self.assertIn(f'action="/my-events/suggested/{event.pk}/hide/"', row)
        self.assertIn('method="post"', row)
        self.assertIn("csrfmiddlewaretoken", row)
        self.assertIn('aria-label="Hide Hide Me"', row)

    def test_other_rows_have_no_hide_cross(self):
        event = make_event("Mine", creator=self.user)
        html = self.page(DASHBOARD)
        self.assertNotIn("suggestion-hide", self.row(html, "hosted"))
        self.assertIn("Mine", self.row(html, "hosted"))
        self.assertNotIn("suggestion-hide", self.page("/my-events/hosted/"))
        self.assertTrue(event.pk)


class HideSuggestionTests(SuggestedTestCase):
    def test_hiding_removes_the_card_from_the_row_and_view_all(self):
        event = make_event("Hide Me")
        self.suggest(event)
        self.suggest(make_event("Keep Me"))
        self.assertEqual(self.hide(event, next=DASHBOARD).status_code, 302)
        for url in (DASHBOARD, SUGGESTED):
            html = self.page(url)
            self.assertNotIn("Hide Me", html)
            self.assertIn("Keep Me", html)

    def test_hidden_suggestion_stays_hidden_after_another_daily_run(self):
        saved = SavedSearch.objects.create(user=self.user, label="Music", filters=MUSIC)
        event = make_event("Jazz")
        saved_searches.run_saved_searches()
        self.assertIn("Jazz", self.page(DASHBOARD))
        self.hide(event)
        SavedSearch.objects.filter(pk=saved.pk).update(last_seen_event_id=0)  # force a rescan
        saved_searches.run_saved_searches()
        self.assertNotIn("Jazz", self.page(DASHBOARD))
        self.assertNotIn("Jazz", self.page(SUGGESTED))
        self.assertEqual(SearchSuggestion.objects.get().hidden, True)

    def test_hiding_returns_to_where_the_user_was(self):
        event = make_event("Back")
        self.suggest(event)
        self.assertRedirects(self.hide(event, next=SUGGESTED), SUGGESTED)
        other = make_event("Default Back")
        self.suggest(other)
        self.assertRedirects(self.hide(other), DASHBOARD)

    def test_next_must_stay_inside_my_events(self):
        for target in ("https://evil.example/", "//evil.example/", "/map/", "javascript:alert(1)"):
            event = make_event(f"Next {target[:6]}")
            self.suggest(event)
            self.assertRedirects(self.hide(event, next=target), DASHBOARD)

    def test_hiding_is_per_user(self):
        event = make_event("Shared")
        self.suggest(event)
        self.suggest(event, user=self.other)
        self.hide(event)
        self.assertNotIn("Shared", self.page(DASHBOARD))
        self.assertTrue(SearchSuggestion.objects.get(user=self.other).hidden is False)
        self.client.force_login(self.other)
        self.assertIn("Shared", self.page(DASHBOARD))

    def test_cannot_hide_an_event_that_was_not_suggested_to_me(self):
        event = make_event("Not Mine")
        self.suggest(event, user=self.other)
        self.assertEqual(self.hide(event).status_code, 404)
        self.assertFalse(SearchSuggestion.objects.get().hidden)
        self.assertEqual(self.hide(make_event("Nobody Suggested")).status_code, 404)

    def test_hiding_twice_is_harmless(self):
        event = make_event("Twice")
        self.suggest(event)
        self.assertEqual(self.hide(event).status_code, 302)
        self.assertEqual(self.hide(event).status_code, 302)

    def test_post_only_csrf_and_login(self):
        event = make_event("Locked")
        self.suggest(event)
        url = reverse("hide_suggestion", args=[event.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.user)
        self.assertEqual(strict.post(url).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertFalse(SearchSuggestion.objects.get().hidden)


class TabsTests(SuggestedTestCase):
    def saved(self, label="Jazz this week", filters=None, user=None):
        return SavedSearch.objects.create(user=user or self.user, label=label, filters=filters or MUSIC)

    def test_view_all_has_two_tabs_and_defaults_to_suggested_events(self):
        html = self.page(SUGGESTED)
        self.assertIn("Suggested Events</a>", html)
        self.assertIn("My Queries</a>", html)
        self.assertRegex(html, r'href="/my-events/suggested/" aria-current="page">Suggested Events')
        self.assertIn("No suggestions yet", html)
        self.assertIn('href="/my-events/"', html)  # back arrow

    def test_my_queries_tab_lists_my_saved_searches(self):
        mine = self.saved("Jazz this week", {"q": "jazz", "category": ["music_performance"],
                                             "when": "weekend"})
        self.saved("Ben's Search", user=self.other)
        html = self.page(QUERIES)
        self.assertRegex(html, r'href="/my-events/suggested/\?tab=queries" aria-current="page">My Queries')
        self.assertIn("Jazz this week", html)
        self.assertNotIn("Ben&#x27;s Search", html)
        self.assertNotIn("Ben's Search", html)
        for phrase in ("“jazz”", "Music &amp; Performance", "This weekend"):
            self.assertIn(phrase, html)
        self.assertIn(f'href="/saved-searches/{mine.pk}/delete/"', html)
        self.assertIn(f"/map/?mode=ai&amp;edit={mine.pk}", html)
        self.assertNotIn("my-event-card", html)

    def test_my_queries_empty_message(self):
        self.assertIn("No saved searches yet", self.page(QUERIES))

    def test_unknown_tab_falls_back_to_suggested_events(self):
        self.assertIn("No suggestions yet", self.page(SUGGESTED + "?tab=nonsense"))

    def test_login_required(self):
        self.client.logout()
        for url in (SUGGESTED, QUERIES):
            self.assertEqual(self.client.get(url).status_code, 302)


class DescribeFiltersTests(TestCase):
    def test_plain_words(self):
        parts = saved_searches.describe_filters({
            "q": "jazz", "category": ["music_performance", "bogus"], "date_from": "2026-12-05",
            "date_to": "2026-12-06", "time_from": "17:00", "time_to": "21:30",
            "near_lat": "41.3", "near_lng": "-72.9", "near_label": "Yale Commons", "radius_mi": "1",
        })
        self.assertEqual(parts, ["“jazz”", "Music & Performance", "Dec 5 – Dec 6",
                                 "Starts 5:00 PM – 9:30 PM", "Within 1 mi of Yale Commons"])

    def test_single_day_and_open_ended_times(self):
        self.assertEqual(saved_searches.describe_filters({"date_from": "2026-12-05", "time_from": "18:00"}),
                         ["Dec 5", "Starts after 6:00 PM"])
        self.assertEqual(saved_searches.describe_filters({"when": "tomorrow", "time_to": "09:00"}),
                         ["Tomorrow", "Starts before 9:00 AM"])
        self.assertEqual(saved_searches.describe_filters({}), [])


class DeleteConfirmationPageTests(SuggestedTestCase):
    def setUp(self):
        super().setUp()
        self.saved = SavedSearch.objects.create(user=self.user, label="Jazz this week", filters=MUSIC)
        self.url = reverse("delete_saved_search", args=[self.saved.pk])

    def test_get_asks_first_and_deletes_nothing(self):
        html = self.page(self.url)
        self.assertIn("Delete This Saved Search?", html)
        self.assertIn("Jazz this week", html)
        self.assertIn('name="confirm" value="1"', html)
        self.assertIn('href="/my-events/suggested/?tab=queries"', html)  # Cancel and back
        self.assertTrue(SavedSearch.objects.filter(pk=self.saved.pk).exists())

    def test_confirming_deletes_and_returns_to_my_queries(self):
        response = self.client.post(self.url, {"confirm": "1"})
        self.assertRedirects(response, QUERIES)
        self.assertFalse(SavedSearch.objects.exists())
        self.assertIn("No saved searches yet", self.page(QUERIES))

    def test_posting_without_confirmation_changes_nothing(self):
        self.assertEqual(self.client.post(self.url).status_code, 409)
        self.assertTrue(SavedSearch.objects.exists())

    def test_deleting_removes_its_suggestions_but_keeps_hidden_ones_hidden(self):
        shown, hidden = make_event("Shown One"), make_event("Hidden One")
        self.suggest(shown, search=self.saved)
        self.suggest(hidden, search=self.saved, hidden=True)
        self.client.post(self.url, {"confirm": "1"})
        self.assertNotIn("Shown One", self.page(DASHBOARD))
        self.assertEqual(list(SearchSuggestion.objects.values_list("event__name", "hidden")),
                         [("Hidden One", True)])

    def test_someone_elses_search_is_a_404_and_login_is_required(self):
        theirs = SavedSearch.objects.create(user=self.other, label="Theirs", filters=MUSIC)
        url = reverse("delete_saved_search", args=[theirs.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, {"confirm": "1"}).status_code, 404)
        self.assertTrue(SavedSearch.objects.filter(pk=theirs.pk).exists())
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
