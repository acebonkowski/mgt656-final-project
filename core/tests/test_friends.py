"""Friend search, requests, Open Requests and the resend rule (#96)."""

from datetime import datetime, timedelta, timezone as dt_timezone
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from accounts.models import Profile
from core import friends, people, resend
from core.models import FriendRequest, Program, ProfilePhoto, School

User = get_user_model()
T0 = datetime(2026, 11, 1, 12, 0, tzinfo=dt_timezone.utc)


def at(moment):
    """Run with the clock fixed at `moment` (every timezone.now() call)."""
    return mock.patch("django.utils.timezone.now", return_value=moment)


def make_user(username, email=None, name="", program=None, onboarded=True):
    email = email or f"{username.replace('.', '_')}@yale.edu"
    user = User.objects.create_user(username=email, email=email)
    Profile.objects.create(user=user, username=username if onboarded else "", display_name=name,
                           program=program, onboarding_complete=onboarded)
    return user


class FriendsTestCase(TestCase):
    def setUp(self):
        school = School.objects.create(name="School of Management")
        self.program = Program.objects.create(school=school, name="MBA")
        self.alex = make_user("alex.k", "alex.k@yale.edu", "Alex", self.program)
        self.bea = make_user("bea", name="Bea")
        self.cy = make_user("cy", name="Cy")
        self.client.force_login(self.alex)

    def login(self, user):
        self.client.force_login(user)

    def send(self, username, **extra):
        return self.client.post("/friends/requests/", {"username": username, **extra})

    def request_between(self, sender, recipient):
        return FriendRequest.objects.get(sender=sender, recipient=recipient)


class SearchTests(FriendsTestCase):
    def search(self, query):
        return self.client.get("/friends/", {"q": query})

    def test_exact_username_or_email_in_any_case_finds_the_one_user(self):
        self.login(self.bea)
        for query in ["alex.k", "ALEX.K", " alex.k ", "alex.k@yale.edu", "Alex.K@Yale.edu"]:
            with self.subTest(query=query):
                response = self.search(query)
                self.assertEqual(response.context["result"]["person"]["user"], self.alex)
                self.assertContains(response, "@alex.k")
                self.assertContains(response, "MBA")

    def test_partial_matches_find_nobody(self):
        self.login(self.bea)
        for query in ["alex", "alex.", "lex.k", "yale.edu", "@yale.edu"]:
            with self.subTest(query=query):
                response = self.search(query)
                self.assertIsNone(response.context["result"])
                self.assertContains(response, "No user has that exact username or email.")

    def test_you_never_find_yourself(self):
        self.assertIsNone(self.search("alex.k").context["result"])
        self.assertIsNone(self.search("alex.k@yale.edu").context["result"])

    def test_users_still_in_onboarding_are_not_found(self):
        make_user("new", "new@yale.edu", onboarded=False)
        self.assertIsNone(self.search("new@yale.edu").context["result"])

    def test_the_button_follows_the_relationship(self):
        self.assertEqual(self.search("bea").context["result"]["state"], "none")
        self.assertContains(self.search("bea"), "Add Friend")
        self.send("bea")
        self.assertContains(self.search("bea"), "Request Sent")
        self.login(self.bea)
        self.assertContains(self.search("alex.k"), ">Accept<")
        self.send("alex.k")
        self.assertEqual(self.search("alex.k").context["result"]["state"], "friends")


class SendAndRespondTests(FriendsTestCase):
    def test_a_sent_request_shows_in_both_tabs_and_on_the_counter(self):
        self.send("bea")
        sent = self.client.get("/friends/?tab=sent")
        self.assertContains(sent, "@bea")
        self.login(self.bea)
        received = self.client.get("/friends/")
        self.assertEqual(received.context["received_count"], 1)
        self.assertContains(received, "alex.k@yale.edu")  # Received shows the email
        self.assertContains(received, 'aria-label="1 incoming friend requests"')
        self.assertEqual(friends.incoming_request_count(self.bea), 1)

    def test_accepting_makes_both_users_friends(self):
        self.send("bea")
        request = self.request_between(self.alex, self.bea)
        self.login(self.bea)
        response = self.client.post(f"/friends/requests/{request.pk}/accept/")
        self.assertRedirects(response, "/friends/", fetch_redirect_response=False)
        self.assertTrue(friends.are_friends(self.alex, self.bea))
        self.assertTrue(friends.are_friends(self.bea, self.alex))
        self.assertEqual(list(friends.friends_of(self.alex)), [self.bea])
        self.assertEqual(list(friends.friends_of(self.bea)), [self.alex])
        self.assertEqual(friends.incoming_request_count(self.bea), 0)
        self.assertEqual(self.client.get("/friends/").context["received"], [])
        self.login(self.alex)
        self.assertEqual(self.client.get("/friends/?tab=sent").context["sent"], [])

    def test_declining_hides_it_from_the_recipient_but_not_the_sender(self):
        self.send("bea")
        request = self.request_between(self.alex, self.bea)
        self.login(self.bea)
        self.client.post(f"/friends/requests/{request.pk}/decline/")
        self.assertFalse(friends.are_friends(self.alex, self.bea))
        self.assertEqual(self.client.get("/friends/").context["received"], [])
        self.login(self.alex)
        sent = self.client.get("/friends/?tab=sent")
        self.assertEqual([item["request"].pk for item in sent.context["sent"]], [request.pk])
        self.assertNotContains(sent, "Declined")

    def test_a_request_back_accepts_the_pending_one(self):
        self.send("bea")
        self.login(self.bea)
        self.send("alex.k")
        self.assertTrue(friends.are_friends(self.alex, self.bea))
        self.assertEqual(FriendRequest.objects.count(), 1)

    def test_a_request_back_after_declining_also_makes_friends(self):
        self.send("bea")
        request = self.request_between(self.alex, self.bea)
        self.login(self.bea)
        self.client.post(f"/friends/requests/{request.pk}/decline/")
        self.send("alex.k")
        self.assertTrue(friends.are_friends(self.alex, self.bea))

    def test_only_the_recipient_can_answer(self):
        self.send("bea")
        request = self.request_between(self.alex, self.bea)
        for user in (self.alex, self.cy):
            self.login(user)
            for action in ("accept", "decline"):
                with self.subTest(user=user.email, action=action):
                    response = self.client.post(f"/friends/requests/{request.pk}/{action}/")
                    self.assertEqual(response.status_code, 404)
        request.refresh_from_db()
        self.assertEqual(request.status, FriendRequest.Status.PENDING)

    def test_an_answered_request_cannot_be_answered_again(self):
        self.send("bea")
        request = self.request_between(self.alex, self.bea)
        self.login(self.bea)
        self.client.post(f"/friends/requests/{request.pk}/accept/")
        self.assertEqual(self.client.post(f"/friends/requests/{request.pk}/decline/").status_code, 404)
        self.assertTrue(friends.are_friends(self.alex, self.bea))

    def test_requests_to_yourself_or_to_a_friend_are_refused(self):
        self.send("alex.k")
        self.assertEqual(FriendRequest.objects.count(), 0)
        self.send("bea")
        request = self.request_between(self.alex, self.bea)
        FriendRequest.objects.filter(pk=request.pk).update(status=FriendRequest.Status.ACCEPTED)
        response = self.send("bea")
        self.assertEqual(FriendRequest.objects.count(), 1)
        self.assertContains(self.client.get(response.url), "You&#x27;re already friends.")

    def test_sending_twice_does_not_create_a_second_request(self):
        self.send("bea")
        response = self.send("bea")
        self.assertEqual(FriendRequest.objects.count(), 1)
        self.assertContains(self.client.get(response.url), "Use Resend in Sent.")

    def test_an_unknown_username_is_refused(self):
        response = self.send("nobody")
        self.assertEqual(FriendRequest.objects.count(), 0)
        self.assertContains(self.client.get(response.url), "find that user")

    def test_the_database_refuses_a_request_to_yourself(self):
        from django.db import IntegrityError, transaction
        with self.assertRaises(IntegrityError), transaction.atomic():
            FriendRequest.objects.create(sender=self.alex, recipient=self.alex, last_sent_at=T0)

    def test_return_to_stays_on_the_friends_page(self):
        response = self.send("bea", return_to="/friends/?tab=sent")
        self.assertRedirects(response, "/friends/?tab=sent", fetch_redirect_response=False)
        response = self.send("cy", return_to="https://evil.example.com/friends/")
        self.assertRedirects(response, "/friends/", fetch_redirect_response=False)
        response = self.send("cy", return_to="/friends//evil.example.com")
        self.assertRedirects(response, "/friends/", fetch_redirect_response=False)


class ResendTests(FriendsTestCase):
    def setUp(self):
        super().setUp()
        with at(T0):
            self.send("bea")
        self.request = self.request_between(self.alex, self.bea)

    def resend(self, moment):
        with at(moment):
            return self.client.post(f"/friends/requests/{self.request.pk}/resend/")

    def test_within_24h_is_refused(self):
        self.resend(T0 + timedelta(hours=23, minutes=59))
        self.request.refresh_from_db()
        self.assertEqual((self.request.resend_count, self.request.last_sent_at), (0, T0))

    def test_at_24h_it_is_sent_again_and_moves_to_the_top(self):
        with at(T0 + timedelta(hours=1)):
            self.login(self.cy)
            self.send("bea")  # a newer request, so the resend has to move up
        self.login(self.alex)
        self.resend(T0 + timedelta(hours=24))
        self.request.refresh_from_db()
        self.assertEqual(self.request.resend_count, 1)
        self.assertEqual(self.request.last_sent_at, T0 + timedelta(hours=24))
        self.login(self.bea)
        self.assertEqual(self.client.get("/friends/").context["received"][0]["request"], self.request)

    def test_a_third_resend_is_refused(self):
        self.resend(T0 + timedelta(hours=24))
        self.resend(T0 + timedelta(hours=48))
        response = self.resend(T0 + timedelta(hours=72))
        self.request.refresh_from_db()
        self.assertEqual(self.request.resend_count, 2)
        self.assertEqual(self.request.last_sent_at, T0 + timedelta(hours=48))
        with at(T0 + timedelta(hours=72)):
            self.assertContains(self.client.get(response.url), "No resends left.")

    def test_the_24h_wait_counts_from_the_last_resend(self):
        self.resend(T0 + timedelta(hours=30))
        self.resend(T0 + timedelta(hours=50))  # 20h after the first resend
        self.request.refresh_from_db()
        self.assertEqual(self.request.resend_count, 1)

    def test_the_button_is_disabled_with_the_reason(self):
        with at(T0 + timedelta(hours=2)):
            sent = self.client.get("/friends/?tab=sent")
        self.assertContains(sent, "You can resend after Nov 2, 7:00 AM.")  # New York time (EST)
        self.assertContains(sent, "disabled")
        with at(T0 + timedelta(hours=25)):
            sent = self.client.get("/friends/?tab=sent")
        self.assertContains(sent, "2 resends left")

    def test_a_resend_reopens_a_declined_request(self):
        self.login(self.bea)
        self.client.post(f"/friends/requests/{self.request.pk}/decline/")
        self.login(self.alex)
        self.resend(T0 + timedelta(hours=24))
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, FriendRequest.Status.PENDING)
        self.assertEqual(friends.incoming_request_count(self.bea), 1)

    def test_only_the_sender_can_resend(self):
        self.login(self.bea)
        self.resend(T0 + timedelta(hours=24))
        self.request.refresh_from_db()
        self.assertEqual(self.request.resend_count, 0)

    def test_the_rule_itself(self):
        self.assertIsNone(resend.resend_refusal(T0, 0, T0 + timedelta(hours=24)))
        self.assertIsNotNone(resend.resend_refusal(T0, 0, T0 + timedelta(hours=23)))
        self.assertEqual(resend.resend_refusal(T0, 2, T0 + timedelta(days=9)), "No resends left.")


class AccessAndBadgeTests(FriendsTestCase):
    def test_logged_out_visitors_are_sent_to_login(self):
        self.client.logout()
        self.assertRedirects(self.client.get("/friends/"), "/login/?next=/friends/")
        for url in ["/friends/requests/", "/friends/requests/1/accept/",
                    "/friends/requests/1/decline/", "/friends/requests/1/resend/"]:
            with self.subTest(url=url):
                response = self.client.post(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn("/login/", response.url)
        self.assertEqual(FriendRequest.objects.count(), 0)

    def test_the_header_badge_counts_pending_received_requests_only(self):
        self.assertEqual(friends.incoming_request_count(self.alex), 0)
        self.login(self.bea)
        self.send("alex.k")
        self.login(self.cy)
        self.send("alex.k")
        self.send("bea")  # sent by Cy to Bea: not Alex's
        self.login(self.alex)
        with mock.patch("core.views.settings.LOCAL_MAP_TILES_PATH") as tiles:
            tiles.is_file.return_value = False
            response = self.client.get("/map/")
        self.assertEqual(response.context["incoming_friend_requests"], 2)
        self.assertContains(response, 'aria-label="2 incoming friend requests"')
        request = self.request_between(self.bea, self.alex)
        self.client.post(f"/friends/requests/{request.pk}/accept/")
        self.assertEqual(friends.incoming_request_count(self.alex), 1)

    def test_the_friends_page_uses_a_fixed_number_of_queries(self):
        for number in range(6):
            sender = make_user(f"sender{number}")
            FriendRequest.objects.create(sender=sender, recipient=self.alex, last_sent_at=T0)
            FriendRequest.objects.create(sender=self.alex, recipient=make_user(f"rec{number}"),
                                         last_sent_at=T0)
        self.client.get("/friends/")
        with self.assertNumQueries(5):  # session, user, received, sent, own username
            self.client.get("/friends/")


class PersonPhotoTests(FriendsTestCase):
    def test_a_signed_link_serves_the_photo_and_a_forged_one_does_not(self):
        profile = self.bea.profile
        ProfilePhoto.objects.create(profile=profile, object_key="profiles/x.png", content_type="image/png")
        profile.photo_reference = "profiles/x.png"
        profile.save()
        url = people.photo_url(User.objects.select_related("profile").get(pk=self.bea.pk))
        self.assertTrue(url.startswith("/people/photo/"))
        with mock.patch("core.photo_storage.download", return_value=b"png-bytes"):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content, b"png-bytes")
            self.assertEqual(self.client.get(f"/people/photo/{self.bea.pk}/").status_code, 404)
            self.assertEqual(self.client.get(url[:-3] + "xx/").status_code, 404)

    def test_an_expired_link_is_refused(self):
        profile = self.bea.profile
        ProfilePhoto.objects.create(profile=profile, object_key="profiles/y.png", content_type="image/png")
        profile.photo_reference = "profiles/y.png"
        profile.save()
        url = people.photo_url(User.objects.select_related("profile").get(pk=self.bea.pk))
        with mock.patch("django.core.signing.time.time",
                        return_value=__import__("time").time() + people.PHOTO_LINK_MAX_AGE + 5):
            self.assertEqual(self.client.get(url).status_code, 404)

    def test_people_without_a_photo_get_the_bulldog(self):
        self.assertTrue(people.photo_url(self.cy).endswith("core/bulldog.svg"))
