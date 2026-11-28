"""Usernames (#95): rules, uniqueness, onboarding, the /username/ page and gate."""

from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Profile
from accounts.tests.helpers import STUDENT, last_code, send_code
from core.models import Program, School

User = get_user_model()
USERNAME_URL = "/username/"


def race():
    """Both checks before saving pass, as when two users submit at the same moment."""
    taken = mock.patch("accounts.usernames.is_taken", return_value=False)
    constraints = mock.patch.object(Profile, "validate_constraints", return_value=None)
    return taken, constraints


def make_user(email, username="", onboarded=True):
    user = User.objects.create_user(username=email, email=email)
    Profile.objects.create(user=user, username=username, onboarding_complete=onboarded)
    return user


class DatabaseConstraintTests(TestCase):
    def test_the_same_name_in_another_case_is_refused_by_the_database(self):
        make_user("a@yale.edu", "alex.k")
        other = User.objects.create_user(username="b@yale.edu")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Profile.objects.create(user=other, username="ALEX.K")

    def test_many_users_may_have_no_username_yet(self):
        make_user("a@yale.edu")
        make_user("b@yale.edu")
        self.assertEqual(Profile.objects.filter(username="").count(), 2)


class UsernamePageTests(TestCase):
    def setUp(self):
        make_user("taken@yale.edu", "alex.k")
        self.user = make_user(STUDENT)
        self.client.force_login(self.user)

    def post(self, username, **extra):
        return self.client.post(USERNAME_URL, {"username": username, **extra})

    def test_a_taken_name_is_refused_in_any_case(self):
        for attempt in ["alex.k", "Alex.K", "  ALEX.K "]:
            with self.subTest(attempt=attempt):
                response = self.post(attempt)
                self.assertEqual(response.status_code, 400)
                self.assertContains(response, "That username is taken.", status_code=400)
                self.user.profile.refresh_from_db()
                self.assertEqual(self.user.profile.username, "")

    def test_each_broken_rule_is_named(self):
        cases = {
            "ab": "at least 3",
            "a" * 21: "at most 20",
            "alex-k": "only lowercase letters",
            "alex k": "only lowercase letters",
            "1alex": "Start with a letter",
            "_alex": "Start with a letter",
            "al..ex": "twice in a row",
            "al._ex": "twice in a row",
            "admin": "reserved",
            "": "This field is required",
        }
        for value, message in cases.items():
            with self.subTest(value=value):
                response = self.post(value)
                self.assertEqual(response.status_code, 400)
                self.assertIn(message, response.context["form"].errors["username"][0])
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.username, "")

    def test_a_valid_name_is_saved_lowercase_and_goes_to_next(self):
        response = self.post("Sam_Lee.2", next="/my-events/")
        self.assertRedirects(response, "/my-events/", fetch_redirect_response=False)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.username, "sam_lee.2")

    def test_without_next_or_with_an_unsafe_next_it_goes_to_the_map(self):
        response = self.post("sam", next="https://evil.example.com/")
        self.assertRedirects(response, "/map/", fetch_redirect_response=False)

    def test_a_race_for_the_same_name_shows_the_taken_message(self):
        # Validation passes, then the database constraint refuses the save.
        taken, constraints = race()
        with taken, constraints:
            response = self.post("alex.k")
        self.assertContains(response, "That username is taken.", status_code=400)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.username, "")

    def test_changing_the_name_frees_the_old_one(self):
        self.post("first.name")
        response = self.client.get(USERNAME_URL)
        self.assertContains(response, "@first.name")
        self.assertContains(response, "Change Your Username.")
        self.post("second.name")
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.username, "second.name")
        other = make_user("other@yale.edu")
        self.client.force_login(other)
        self.assertRedirects(self.post("first.name"), "/map/", fetch_redirect_response=False)

    def test_keeping_your_own_name_is_not_taken(self):
        self.post("sam")
        self.assertRedirects(self.post("SAM"), "/map/", fetch_redirect_response=False)

    def test_logged_out_visitors_are_sent_to_login(self):
        self.client.logout()
        self.assertRedirects(self.client.get(USERNAME_URL), f"/login/?next={USERNAME_URL}")

    def test_a_user_still_in_onboarding_is_sent_there(self):
        self.client.force_login(make_user("new@yale.edu", onboarded=False))
        self.assertRedirects(self.client.get(USERNAME_URL), "/onboarding/",
                             fetch_redirect_response=False)


class GateTests(TestCase):
    """Accounts from before #95 choose a username before using the app."""

    def setUp(self):
        self.user = make_user(STUDENT)

    def test_login_sends_them_to_the_username_page_then_where_they_were_going(self):
        self.client.get("/login/?next=/my-events/")
        send_code(self.client)
        response = self.client.post("/login/code/", {"code": last_code()})
        self.assertRedirects(response, "/username/?next=%2Fmy-events%2F",
                             fetch_redirect_response=False)
        response = self.client.post(USERNAME_URL, {"username": "sam", "next": "/my-events/"})
        self.assertRedirects(response, "/my-events/", fetch_redirect_response=False)
        self.assertEqual(self.client.get("/my-events/").status_code, 200)

    def test_every_page_redirects_until_a_name_is_saved(self):
        self.client.force_login(self.user)
        for url in ["/map/", "/my-events/", "/friends/", "/settings/"]:
            with self.subTest(url=url):
                self.assertRedirects(self.client.get(url), f"/username/?next={url.replace('/', '%2F')}",
                                     fetch_redirect_response=False)
        self.client.post(USERNAME_URL, {"username": "sam"})
        self.assertEqual(self.client.get("/map/").status_code, 200)

    def test_a_session_from_before_the_gate_is_checked_on_its_first_page_load(self):
        self.client.force_login(self.user)
        session = self.client.session
        session.pop("username_checked", None)  # as if logged in before #95
        session.save()
        self.assertRedirects(self.client.get("/map/"), "/username/?next=%2Fmap%2F",
                             fetch_redirect_response=False)

    def test_the_way_out_and_the_page_itself_are_not_redirected(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(USERNAME_URL).status_code, 200)
        self.assertEqual(self.client.get("/healthz").status_code, 200)
        self.assertRedirects(self.client.post("/logout/"), "/login/", fetch_redirect_response=False)

    def test_posts_are_not_redirected(self):
        self.client.force_login(self.user)
        response = self.client.post("/events/999/going/", {"status": "going"})
        self.assertEqual(response.status_code, 404)

    def test_users_with_a_name_or_still_in_onboarding_are_not_redirected(self):
        self.client.force_login(make_user("named@yale.edu", "named"))
        self.assertNotEqual(self.client.get("/my-events/").status_code, 302)
        self.client.force_login(make_user("new@yale.edu", onboarded=False))
        self.assertEqual(self.client.get("/onboarding/").status_code, 200)

    def test_page_loads_after_login_add_no_query_for_the_check(self):
        named = make_user("named@yale.edu", "named")
        self.client.force_login(named)
        with self.assertNumQueries(0):
            self.client.get("/does-not-exist/")


class OnboardingUsernameTests(TestCase):
    def setUp(self):
        school = School.objects.create(name="Test school")
        self.program = Program.objects.create(school=school, name="Test program")
        self.user = make_user(STUDENT, onboarded=False)
        self.client.force_login(self.user)

    def payload(self, **changes):
        return {"display_name": "Alex", "username": "alex", "school": self.program.school_id,
                "program": self.program.pk, **changes}

    def test_onboarding_cannot_finish_without_a_username(self):
        response = self.client.post("/onboarding/", self.payload(username=""))
        self.assertIn("username", response.context["form"].errors)
        self.user.profile.refresh_from_db()
        self.assertFalse(self.user.profile.onboarding_complete)

    def test_onboarding_saves_the_username_and_shows_the_rules(self):
        self.assertContains(self.client.get("/onboarding/"), "Start with a letter.")
        response = self.client.post("/onboarding/", self.payload(username="Alex.K"))
        self.assertRedirects(response, reverse("map"), fetch_redirect_response=False)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.username, "alex.k")
        self.assertEqual(self.client.get("/map/").status_code, 200)

    def test_onboarding_refuses_a_taken_name(self):
        make_user("a@yale.edu", "alex")
        response = self.client.post("/onboarding/", self.payload(username="ALEX"))
        self.assertIn("That username is taken.", response.context["form"].errors["username"])
        self.user.profile.refresh_from_db()
        self.assertFalse(self.user.profile.onboarding_complete)

    def test_onboarding_race_for_a_name_shows_the_taken_message(self):
        make_user("a@yale.edu", "alex")
        taken, constraints = race()
        with taken, constraints:
            response = self.client.post("/onboarding/", self.payload())
        self.assertEqual(response.status_code, 200)
        self.assertIn("That username is taken.", response.context["form"].errors["username"])
        self.user.profile.refresh_from_db()
        self.assertFalse(self.user.profile.onboarding_complete)


@override_settings(GRADER_FIXED_OTP="135790")
class SeedUsernameTests(TestCase):
    def run_seed(self):
        out, err = StringIO(), StringIO()
        call_command("seed", stdout=out, stderr=err)
        return err.getvalue()

    def test_graders_get_fixed_usernames_and_seed_runs_twice(self):
        self.assertEqual(self.run_seed(), "")
        self.assertEqual(self.run_seed(), "")
        self.assertEqual(
            sorted(Profile.objects.values_list("username", flat=True)),
            ["demo.admin", "demo.student"],
        )

    def test_a_changed_grader_username_is_kept(self):
        self.run_seed()
        Profile.objects.filter(username="demo.student").update(username="grader.m")
        self.run_seed()
        self.assertTrue(Profile.objects.filter(username="grader.m").exists())
