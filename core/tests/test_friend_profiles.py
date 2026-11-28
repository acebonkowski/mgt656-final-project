"""Friends list and profile pages (#97)."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from core import friends
from core.models import Event, EventAttendance, FriendRequest, Program, School
from core.tests.test_friends import make_user


def make_event(name, days_ahead=1, creator=None, **fields):
    start = timezone.now() + timedelta(days=days_ahead)
    values = {
        "image": "default", "name": name, "description": "Something happening",
        "category": "music_performance", "start_at": start,
        "end_at": start + timedelta(hours=2), "location": f"Place for {name}",
        "latitude": "41.308300", "longitude": "-72.927900", "price": "0", "creator": creator,
    }
    values.update(fields)
    return Event.objects.create(**values)


def befriend(a, b):
    FriendRequest.objects.create(sender=a, recipient=b, status=FriendRequest.Status.ACCEPTED,
                                 last_sent_at=timezone.now())


def going(user, event, status="going"):
    EventAttendance.objects.create(user=user, event=event, status=status)


class ProfileTestCase(TestCase):
    def setUp(self):
        school = School.objects.create(name="School of Management")
        self.mba = Program.objects.create(school=school, name="MBA")
        self.law = Program.objects.create(
            school=School.objects.create(name="Law School"), name="JD")
        self.alex = make_user("alex", name="Alex", program=self.mba)
        self.bea = make_user("bea", name="Bea", program=self.law)
        self.cy = make_user("cy", name="Cy")
        self.dee = make_user("dee", name="Dee")
        befriend(self.alex, self.bea)
        self.client.force_login(self.alex)

    def profile(self, user):
        return self.client.get(f"/people/{user.profile.username}/")

    def listed(self, response):
        return [event.name for event in response.context["events"]]


class FriendsListTests(ProfileTestCase):
    def test_friends_are_listed_by_name_and_link_to_their_profile(self):
        befriend(self.cy, self.alex)  # the other direction counts too
        response = self.client.get("/friends/")
        self.assertEqual([p["name"] for p in response.context["friends"]], ["Bea", "Cy"])
        self.assertContains(response, 'href="/people/bea/"')
        self.assertContains(response, 'href="/people/cy/"')

    def test_pending_and_declined_requests_are_not_friends(self):
        FriendRequest.objects.create(sender=self.alex, recipient=self.cy, last_sent_at=timezone.now())
        FriendRequest.objects.create(sender=self.dee, recipient=self.alex, last_sent_at=timezone.now(),
                                     status=FriendRequest.Status.DECLINED)
        names = [p["name"] for p in self.client.get("/friends/").context["friends"]]
        self.assertEqual(names, ["Bea"])

    def test_no_friends_shows_a_hint(self):
        self.client.force_login(self.dee)
        self.assertContains(self.client.get("/friends/"), "No friends yet.")


class FriendProfileTests(ProfileTestCase):
    def test_a_friend_shows_name_photo_program_and_going_events(self):
        event = make_event("Jazz Night")
        going(self.bea, event)
        response = self.profile(self.bea)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bea")
        self.assertContains(response, "@bea")
        self.assertContains(response, "JD")
        self.assertContains(response, "core/bulldog.svg")
        self.assertEqual(self.listed(response), ["Jazz Night"])
        self.assertContains(response, f'href="/events/{event.pk}/"')

    def test_maybe_not_going_and_ended_events_are_left_out(self):
        going(self.bea, make_event("Maybe Show"), "maybe")
        going(self.bea, make_event("Skipped Show"), "not_going")
        past_start = timezone.now() - timedelta(days=2)
        going(self.bea, make_event("Old Show", start_at=past_start, end_at=past_start + timedelta(hours=1)))
        going(self.bea, make_event("Later Show", days_ahead=3))
        self.assertEqual(self.listed(self.profile(self.bea)), ["Later Show"])

    def test_hosted_events_are_listed_in_start_order(self):
        make_event("Bea's Party", days_ahead=2, creator=self.bea)
        going(self.bea, make_event("Concert", days_ahead=1))
        self.assertEqual(self.listed(self.profile(self.bea)), ["Concert", "Bea's Party"])

    def test_events_hidden_from_the_viewer_are_left_out(self):
        # Program-only event by a Law student: Alex (MBA) may not see it (#41).
        hidden = make_event("JD Mixer", creator=self.cy, visibility=Event.Visibility.PROGRAM)
        self.cy.profile.program = self.law
        self.cy.profile.save()
        going(self.bea, hidden)
        going(self.bea, make_event("Open Talk"))
        self.assertEqual(self.listed(self.profile(self.bea)), ["Open Talk"])

    def test_an_event_both_host_and_answer_is_listed_once(self):
        event = make_event("Own Event", creator=self.bea)
        going(self.bea, event)
        self.assertEqual(self.listed(self.profile(self.bea)), ["Own Event"])

    def test_the_attendance_visibility_hook_can_hide_the_events(self):
        going(self.bea, make_event("Jazz Night"))
        from unittest import mock
        with mock.patch("core.friends.attendance_visible_to", return_value=False):
            self.assertEqual(self.listed(self.profile(self.bea)), [])

    def test_the_profile_uses_a_fixed_number_of_queries(self):
        for number in range(6):
            going(self.bea, make_event(f"Show {number}", days_ahead=number + 1))
        self.profile(self.bea)
        with self.assertNumQueries(5):  # session, user, profile lookup, relationship, events
            self.profile(self.bea)


class RequestProfileTests(ProfileTestCase):
    def test_a_pending_request_shows_the_profile_without_events(self):
        FriendRequest.objects.create(sender=self.alex, recipient=self.cy, last_sent_at=timezone.now())
        going(self.cy, make_event("Cy's Pick"))
        for viewer, other in ((self.alex, self.cy), (self.cy, self.alex)):
            with self.subTest(viewer=viewer.profile.username):
                self.client.force_login(viewer)
                response = self.profile(other)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, other.profile.display_name)
                self.assertEqual(response.context["events"], [])
                self.assertNotContains(response, "Upcoming Events")
                self.assertNotContains(response, "Cy&#x27;s Pick")


class StrangerTests(ProfileTestCase):
    def test_strangers_and_unknown_names_get_a_404(self):
        self.assertEqual(self.profile(self.dee).status_code, 404)
        self.assertEqual(self.client.get("/people/nobody/").status_code, 404)

    def test_a_request_the_viewer_declined_does_not_open_the_profile(self):
        FriendRequest.objects.create(sender=self.dee, recipient=self.alex, last_sent_at=timezone.now(),
                                     status=FriendRequest.Status.DECLINED)
        self.assertEqual(self.profile(self.dee).status_code, 404)

    def test_your_own_profile_goes_to_the_friends_page(self):
        self.assertRedirects(self.profile(self.alex), "/friends/")

    def test_logged_out_visitors_are_sent_to_login(self):
        self.client.logout()
        self.assertRedirects(self.profile(self.bea), "/login/?next=/people/bea/")

    def test_can_view_profile_matches_the_page(self):
        self.assertTrue(friends.can_view_profile(self.alex, self.bea))
        self.assertFalse(friends.can_view_profile(self.alex, self.dee))
