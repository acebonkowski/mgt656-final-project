"""Friends-only events (#98): the creator and their accepted friends see them."""

from unittest import mock

from django.utils import timezone

from core.models import Event, FriendRequest
from core.tests.test_visibility import VisibilityTestCase, make_event
from core.visibility import can_view

E = Event.Visibility


class FriendsOnlyTests(VisibilityTestCase):
    def setUp(self):
        # same_program is the creator's friend; same_school is not, even in the same school.
        self.friend = self.same_program
        self.stranger = self.same_school
        FriendRequest.objects.create(sender=self.friend, recipient=self.creator,
                                     status=FriendRequest.Status.ACCEPTED, last_sent_at=timezone.now())
        self.event = make_event("Small Dinner", E.FRIENDS, self.creator)
        self.page = f"/events/{self.event.pk}/"

    def pins(self, user):
        return [e["name"] for e in self.get_as(user, "/map/").context["map_config"]["events"]]

    def search(self, user):
        return [e["name"] for e in self.get_as(user, "/events/search/").json()["events"]]

    def test_a_friend_sees_it_on_the_map_in_search_and_on_the_page(self):
        self.assertEqual(self.pins(self.friend), ["Small Dinner"])
        self.assertEqual(self.search(self.friend), ["Small Dinner"])
        for suffix in ("", "popup/", "calendar.ics"):
            self.assertEqual(self.get_as(self.friend, self.page + suffix).status_code, 200, suffix)

    def test_friendship_counts_in_both_directions(self):
        FriendRequest.objects.create(sender=self.creator, recipient=self.outsider,
                                     status=FriendRequest.Status.ACCEPTED, last_sent_at=timezone.now())
        self.assertTrue(can_view(self.outsider, self.event))

    def test_a_non_friend_sees_nothing_even_in_the_same_program(self):
        for user in (self.stranger, self.outsider, self.no_program):
            self.assertEqual(self.pins(user), [], user)
            self.assertEqual(self.search(user), [], user)
            for suffix in ("", "popup/", "calendar.ics"):
                self.assertEqual(self.get_as(user, self.page + suffix).status_code, 404, (suffix, user))
        with mock.patch("core.views.photo_storage.download", return_value=b"img"):
            self.assertEqual(self.get_as(self.stranger, f"/event-photo/{self.event.image}").status_code, 404)
            self.assertEqual(self.get_as(self.friend, f"/event-photo/{self.event.image}").status_code, 200)

    def test_pending_or_declined_requests_do_not_count(self):
        FriendRequest.objects.create(sender=self.stranger, recipient=self.creator,
                                     last_sent_at=timezone.now())
        FriendRequest.objects.create(sender=self.creator, recipient=self.outsider,
                                     status=FriendRequest.Status.DECLINED, last_sent_at=timezone.now())
        self.assertFalse(can_view(self.stranger, self.event))
        self.assertFalse(can_view(self.outsider, self.event))

    def test_a_friend_of_a_friend_does_not_see_it(self):
        FriendRequest.objects.create(sender=self.friend, recipient=self.outsider,
                                     status=FriendRequest.Status.ACCEPTED, last_sent_at=timezone.now())
        self.assertFalse(can_view(self.outsider, self.event))

    def test_the_creator_always_sees_it(self):
        self.assertEqual(self.pins(self.creator), ["Small Dinner"])

    def test_a_friend_can_answer_going(self):
        response = self.post_as(self.friend, self.page + "going/", {"status": "going"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.post_as(self.stranger, self.page + "going/", {"status": "going"}).status_code, 404)

    def test_the_map_query_count_does_not_grow_with_friends(self):
        for number in range(5):
            user = self.user(f"f{number}", None)
            FriendRequest.objects.create(sender=user, recipient=self.friend,
                                         status=FriendRequest.Status.ACCEPTED, last_sent_at=timezone.now())
            make_event(f"Dinner {number}", E.FRIENDS, user, location=f"Table {number}")
        self.client.force_login(self.friend)
        self.client.get("/events/search/")
        with self.assertNumQueries(3):  # session, user, events (visibility is subqueries)
            response = self.client.get("/events/search/")
        self.assertEqual(len(response.json()["events"]), 6)
