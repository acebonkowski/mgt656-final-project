"""Friends going on the map and the event page (#85)."""

from unittest import mock

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from core import friends
from core.models import Event, EventAttendance, FriendRequest
from core.tests.test_friend_profiles import befriend, going, make_event
from core.tests.test_friends import make_user


class FriendsGoingTestCase(TestCase):
    def setUp(self):
        self.alex = make_user("alex", name="Alex")
        self.bea = make_user("bea", name="Bea")
        self.cy = make_user("cy", name="Cy")
        self.dee = make_user("dee", name="Dee")
        self.eve = make_user("eve", name="Eve")  # not a friend
        for friend in (self.bea, self.cy, self.dee):
            befriend(self.alex, friend)
        self.event = make_event("Jazz Night")
        going(self.bea, self.event)
        going(self.cy, self.event)
        going(self.dee, self.event, "maybe")
        self.client.force_login(self.alex)

    def page(self, suffix=""):
        return self.client.get(f"/events/{self.event.pk}/{suffix}")

    def listed(self, response):
        return [p["name"] for p in response.context["friends_going"]]

    def pin_count(self, event=None):
        event = event or self.event
        pins = self.client.get("/map/").context["map_config"]["events"]
        return {pin["id"]: pin["friends_going"] for pin in pins}[event.pk]

    def search_count(self, event=None):
        event = event or self.event
        results = self.client.get("/events/search/").json()["events"]
        return {e["id"]: e["friends_going"] for e in results}[event.pk]


class CountAndListTests(FriendsGoingTestCase):
    def test_the_count_is_friends_with_going_only(self):
        response = self.page()
        self.assertContains(response, "2 friends going")
        self.assertEqual(self.pin_count(), 2)
        self.assertEqual(self.search_count(), 2)

    def test_the_list_names_those_friends(self):
        response = self.page()
        self.assertEqual(self.listed(response), ["Bea", "Cy"])
        self.assertContains(response, 'href="/people/bea/"')
        self.assertContains(response, 'href="/people/cy/"')
        self.assertNotContains(response, 'href="/people/dee/"')

    def test_non_friends_are_not_counted(self):
        going(self.eve, self.event)
        FriendRequest.objects.create(sender=self.alex, recipient=self.eve, last_sent_at=timezone.now())
        self.assertEqual(self.listed(self.page()), ["Bea", "Cy"])
        self.assertEqual(self.pin_count(), 2)

    def test_the_viewer_is_not_counted(self):
        going(self.alex, self.event)
        self.assertEqual(self.pin_count(), 2)
        self.assertNotIn("Alex", self.listed(self.page()))

    def test_a_friend_who_hosts_counts_once(self):
        hosted = make_event("Bea's Party", creator=self.bea)
        EventAttendance.objects.create(user=self.bea, event=hosted, status="going")  # old data
        self.client.get("/map/")
        self.assertEqual(self.pin_count(hosted), 1)
        self.assertEqual(self.listed(self.client.get(f"/events/{hosted.pk}/")), ["Bea"])

    def test_a_change_to_not_going_drops_the_friend(self):
        EventAttendance.objects.filter(user=self.bea, event=self.event).update(status="not_going")
        self.assertContains(self.page(), "1 friend going")
        self.assertEqual(self.listed(self.page()), ["Cy"])
        self.assertEqual(self.pin_count(), 1)

    def test_no_friends_going_shows_nothing(self):
        quiet = make_event("Quiet Talk")
        response = self.client.get(f"/events/{quiet.pk}/")
        self.assertNotContains(response, "friends going")
        self.assertNotContains(response, "friend going")
        self.assertEqual(self.pin_count(quiet), 0)

    def test_the_event_window_shows_the_same_list(self):
        response = self.page("popup/")
        self.assertContains(response, "2 friends going")
        self.assertEqual(self.listed(response), ["Bea", "Cy"])

    def test_the_count_and_list_agree(self):
        self.assertEqual(len(friends.friends_going_to(self.event, self.alex)), self.pin_count())

    def test_the_attendance_visibility_hook_is_respected(self):
        from django.db.models import Q
        with mock.patch("core.friends.attendance_visible_q", return_value=Q(pk__in=[])):
            self.assertEqual(self.listed(self.page()), [])
            self.assertEqual(self.pin_count(), 0)


class LoggedOutTests(FriendsGoingTestCase):
    def test_logged_out_visitors_see_no_counts(self):
        self.client.logout()
        response = self.page()
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "friends going")
        self.assertEqual(response.context["friends_going"], [])
        anonymous = Event.objects.filter(pk=self.event.pk)
        from django.contrib.auth.models import AnonymousUser
        self.assertEqual(friends.with_friends_going(anonymous, AnonymousUser()).get().friends_going, 0)


class QueryCountTests(FriendsGoingTestCase):
    def map_queries(self):
        self.client.get("/map/")
        with CaptureQueriesContext(connection) as queries:
            self.client.get("/map/")
        return len(queries)

    def test_the_map_query_count_does_not_grow_with_events(self):
        few = self.map_queries()
        for number in range(8):
            event = make_event(f"Show {number}", days_ahead=number + 2)
            going(self.bea, event)
            going(self.cy, event)
        self.assertEqual(self.map_queries(), few)
        self.assertEqual(self.search_count(event), 2)
