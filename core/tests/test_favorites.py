"""Favorites persistence, isolation, filtering, and optional geocoding."""
from datetime import timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from core.models import EventFavorite
from core.my_events import ROW_LIMIT, favorite_events
from core.tests.test_my_events import answer, make_event, make_user


class FavoritesTests(TestCase):
    def setUp(self):
        self.user = make_user("favorite-user")
        self.other = make_user("other-user")
        start = (timezone.now().astimezone(ZoneInfo("America/New_York")) + timedelta(days=1)).replace(hour=12, minute=0, second=0)
        self.event = make_event("Saved concert", creator=self.user, start_at=start, end_at=start + timedelta(hours=2))
        self.url = f"/events/{self.event.pk}/favorite/"
        self.client.force_login(self.user)

    def save(self, event=None, user=None):
        return EventFavorite.objects.create(user=user or self.user, event=event or self.event)

    def results(self, **params):
        response = self.client.get("/my-events/favorites/", params)
        self.assertEqual(response.status_code, 200)
        return list(response.context["events"])

    def test_save_remove_idempotent_and_host_allowed(self):
        for _ in range(2):
            self.assertEqual(self.client.post(self.url, {"favorited": "true"}).json(), {"favorited": True})
        self.assertEqual(EventFavorite.objects.count(), 1)
        for _ in range(2):
            self.assertEqual(self.client.post(self.url, {"favorited": "false"}).json(), {"favorited": False})
        self.assertFalse(EventFavorite.objects.exists())

    def test_auth_method_validation_and_missing_event(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        for data in ({}, {"favorited": "yes"}):
            self.assertEqual(self.client.post(self.url, data).status_code, 400)
        self.assertEqual(self.client.post("/events/99999/favorite/", {"favorited": "true"}).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.post(self.url, {"favorited": "true"}).status_code, 302)
        self.assertFalse(EventFavorite.objects.exists())

    def test_csrf_enforced(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(self.url, {"favorited": "true"}).status_code, 403)
        client.get(f"/events/{self.event.pk}/")
        self.assertEqual(client.post(self.url, {"favorited": "true"},
                                    HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value).status_code, 200)

    def test_user_isolation_and_unique_constraint(self):
        self.save(user=self.other)
        self.assertEqual(self.results(), [])
        self.client.post(self.url, {"favorited": "false"})
        self.assertTrue(EventFavorite.objects.filter(user=self.other).exists())
        self.save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.save()

    def test_end_boundary_ongoing_and_history_retained(self):
        now = timezone.now()
        self.event.start_at = now - timedelta(hours=1)
        self.event.end_at = now
        self.event.save()
        self.save()
        self.assertEqual(list(favorite_events(self.user, now)), [])
        self.assertEqual(list(favorite_events(self.user, now - timedelta(seconds=1))), [self.event])
        self.assertTrue(EventFavorite.objects.exists())
        self.assertEqual(self.client.post(self.url, {"favorited": "true"}).status_code, 400)
        self.assertEqual(self.client.post(self.url, {"favorited": "false"}).status_code, 200)

    def test_attendance_independence_and_chronological_text_search(self):
        later = make_event("Concert concert concert", days_ahead=3, creator=self.other)
        self.save(later)
        self.save()
        answer(self.user, self.event, "not_going")
        self.assertEqual(self.results(q="concert", include_not_going="false"), [self.event, later])
        self.client.post(self.url, {"favorited": "false"})
        self.assertEqual(self.user.attendances.get(event=self.event).status, "not_going")

    def test_filters_and_combination(self):
        local = self.event.start_at.astimezone(ZoneInfo("America/New_York"))
        self.save()
        other = make_event("Far talk", days_ahead=5, latitude="40.000000", longitude="-73.000000")
        self.save(other)
        params = dict(q="concert", category=self.event.category,
                      date_from=local.date().isoformat(), date_to=local.date().isoformat(),
                      time_from=(local - timedelta(minutes=1)).strftime("%H:%M"),
                      time_to=(local + timedelta(minutes=1)).strftime("%H:%M"),
                      near_lat="41.3083", near_lng="-72.9279", radius_mi="0.5")
        for key, value in params.items():
            with self.subTest(filter=key):
                # Coordinates are validated as a pair.
                if key not in ("near_lat", "near_lng", "radius_mi"):
                    self.assertIn(self.event, self.results(**{key: value}))
        self.assertEqual(self.results(**params), [self.event])
        self.assertEqual(self.results(when="tomorrow"), [self.event])
        self.assertEqual(self.results(near_lat="40", near_lng="-73", radius_mi="1"), [other])
        self.assertEqual(self.results(q="missing"), [])

    def test_invalid_filters_and_empty_states(self):
        self.assertContains(self.client.get("/my-events/favorites/"), "No favorites yet")
        self.save()
        for params in ({"category": "unknown"}, {"near_lat": "41"},
                       {"date_from": "2026-12-02", "date_to": "2026-12-01"},
                       {"time_from": "18:00", "time_to": "09:00"}):
            response = self.client.get("/my-events/favorites/", params)
            self.assertContains(response, "Please correct the filters")
            self.assertEqual(list(response.context["events"]), [])
        response = self.client.get("/my-events/favorites/", {"q": "unmatched"})
        self.assertContains(response, "No matching favorites")
        self.assertContains(response, 'value="unmatched"')
        self.assertContains(response, "Clear Filters")

    @override_settings(MAP_API_KEY="")
    def test_geocoding_not_needed_for_save_or_search(self):
        with patch("core.geocoding.search", side_effect=AssertionError("unexpected geocoding")):
            self.assertEqual(self.client.post(self.url, {"favorited": "true"}).status_code, 200)
            self.assertEqual(self.results(q="concert", near_label="Unresolved address"), [self.event])
            self.assertEqual(self.results(near_lat="41.3083", near_lng="-72.9279", radius_mi="1"), [self.event])
        self.assertEqual(self.client.get("/map/geocode/", {"q": "Yale"}).status_code, 503)
        self.assertEqual(self.results(), [self.event])

    def test_dashboard_limit_and_view_all(self):
        events = [make_event(f"Favorite {i}", days_ahead=i + 1) for i in range(ROW_LIMIT + 2)]
        for event in events:
            self.save(event)
        response = self.client.get("/my-events/")
        row = next(row for row in response.context["rows"] if row["key"] == "favorites")
        self.assertEqual(row["events"], events[:ROW_LIMIT])
        self.assertEqual(self.results(), events)

    def test_shared_assets_loaded_on_map_and_event_page(self):
        for url in ("/map/", f"/events/{self.event.pk}/"):
            response = self.client.get(url)
            self.assertContains(response, "core/favorites.css")
            self.assertContains(response, "core/favorites.js")

    def test_full_page_popup_state_and_guest_return(self):
        for suffix in ("", "popup/"):
            url = f"/events/{self.event.pk}/{suffix}"
            self.assertContains(self.client.get(url), 'aria-pressed="false"')
            self.save()
            self.assertContains(self.client.get(url), 'aria-pressed="true"')
            EventFavorite.objects.all().delete()
        self.client.logout()
        response = self.client.get(f"/events/{self.event.pk}/")
        self.assertContains(response, "Log in to favorite this event")
        self.assertContains(response, f"next=%2Fevents%2F{self.event.pk}%2F")
