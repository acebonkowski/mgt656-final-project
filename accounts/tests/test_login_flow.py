"""
Student OTP login (#6). Emails are never really sent: Django's test runner
captures them in memory (mail.outbox), and send failures are mocked.
"""

from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import LoginCode, Profile
from accounts.tests.helpers import assert_error, STUDENT, last_code, send_code

User = get_user_model()


def age_record(email, seconds):
    """Pretend the code for `email` was sent `seconds` ago."""
    record = LoginCode.objects.get(email=email)
    shift = timedelta(seconds=seconds)
    record.sent_at -= shift
    if record.expires_at:
        record.expires_at -= shift
    record.save()


@override_settings(EMAIL_DELIVERY_ENABLED=True)
class WelcomeScreenTests(TestCase):
    def test_welcome_screen_content_and_mobile_ready(self):
        response = self.client.get("/login/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<h1>Welcome.</h1>", html=True)
        self.assertContains(response, "Your Yale email address")
        self.assertContains(response, "Only yale.edu addresses are accepted.")
        self.assertContains(response, ">Send code</button>")
        self.assertContains(response, 'name="viewport"')
        self.assertContains(response, "accounts/auth.css")

    def test_valid_yale_email_sends_code_and_shows_code_screen(self):
        response = send_code(self.client)
        self.assertRedirects(response, "/login/code/")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [STUDENT])
        code = last_code()
        record = LoginCode.objects.get(email=STUDENT)
        self.assertNotIn(code, record.code_hash)  # only a hash is stored
        response = self.client.get("/login/code/")
        self.assertContains(response, "<h1>Code was sent.</h1>", html=True)
        self.assertContains(response, STUDENT)

    def test_empty_invalid_or_non_yale_email_shows_error_and_sends_nothing(self):
        cases = {
            "": "Please enter your Yale email address.",
            "not-an-email": "Please enter a valid email address.",
            "someone@gmail.com": "Only yale.edu email addresses are accepted.",
        }
        for email, message in cases.items():
            with self.subTest(email=email):
                response = send_code(self.client, email)
                self.assertEqual(response.status_code, 400)
                self.assertContains(response, message, status_code=400)
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(LoginCode.objects.exists())

    def test_email_service_failure_shows_error_and_allows_retry(self):
        with mock.patch("accounts.otp.send_mail", side_effect=OSError("smtp down")):
            with self.assertLogs("accounts.otp", level="ERROR"):
                response = send_code(self.client)
        assert_error(self, response, "couldn't send the code")
        self.assertFalse(LoginCode.objects.exists())
        self.assertRedirects(send_code(self.client), "/login/code/")  # no 45 s wait

    @override_settings(EMAIL_DELIVERY_ENABLED=False)
    def test_without_email_service_no_code_is_sent_or_logged(self):
        with self.assertLogs("accounts.otp", level="ERROR"):
            response = send_code(self.client)
        assert_error(self, response, "couldn't send the code")
        self.assertEqual(len(mail.outbox), 0)


@override_settings(EMAIL_DELIVERY_ENABLED=True)
class CodeScreenTests(TestCase):
    def test_code_screen_needs_an_email_first(self):
        self.assertRedirects(self.client.get("/login/code/"), "/login/")

    def test_confirm_disabled_back_arrow_and_countdown(self):
        send_code(self.client)
        response = self.client.get("/login/code/")
        self.assertContains(response, 'id="confirm" type="submit" class="primary" disabled')
        self.assertContains(response, 'class="back" href="/login/"')
        self.assertContains(response, 'data-seconds="45"')
        self.assertContains(response, "You can resend the code in")
        self.assertContains(response, 'id="resend-form" method="post" action="/login/resend/" hidden')
        self.assertContains(response, "accounts/code.js")

    def test_back_arrow_returns_to_welcome_with_email_filled_in(self):
        send_code(self.client)
        response = self.client.get("/login/")
        self.assertContains(response, f'value="{STUDENT}"')

    def test_resend_is_refused_before_45_seconds(self):
        send_code(self.client)
        response = self.client.post("/login/resend/")
        self.assertContains(response, "You can resend the code in", status_code=400)
        self.assertEqual(len(mail.outbox), 1)
        # Going back and submitting the same address doesn't bypass the wait either.
        send_code(self.client)
        self.assertEqual(len(mail.outbox), 1)

    def test_resend_after_45_seconds_sends_a_new_code_and_old_one_stops_working(self):
        send_code(self.client)
        old_code = last_code()
        age_record(STUDENT, 45)
        response = self.client.get("/login/code/")
        self.assertContains(response, 'data-seconds="0"')
        self.assertNotContains(response, 'action="/login/resend/" hidden')
        self.assertRedirects(self.client.post("/login/resend/"), "/login/code/")
        self.assertEqual(len(mail.outbox), 2)
        new_code = last_code()
        if new_code != old_code:
            response = self.client.post("/login/code/", {"code": old_code})
            self.assertEqual(response.status_code, 400)
        response = self.client.post("/login/code/", {"code": new_code})
        self.assertEqual(response.status_code, 302)


@override_settings(EMAIL_DELIVERY_ENABLED=True)
class VerifyCodeTests(TestCase):
    def test_new_user_is_created_logged_in_and_sent_to_onboarding(self):
        send_code(self.client)
        response = self.client.post("/login/code/", {"code": last_code()})
        self.assertRedirects(response, "/onboarding/")
        user = User.objects.get(username=STUDENT)
        self.assertEqual(user.email, STUDENT)
        self.assertFalse(user.has_usable_password())
        self.assertFalse(user.profile.onboarding_complete)
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)
        response = self.client.get("/onboarding/")
        self.assertContains(response, "Let's get to know you better.")

    def test_existing_user_with_completed_profile_goes_to_the_map(self):
        user = User.objects.create_user(username=STUDENT, email=STUDENT)
        Profile.objects.create(user=user, onboarding_complete=True)
        send_code(self.client)
        response = self.client.post("/login/code/", {"code": last_code()})
        self.assertRedirects(response, "/map/", fetch_redirect_response=False)
        self.assertEqual(User.objects.count(), 1)

    def test_logging_in_from_a_protected_page_returns_to_it(self):
        user = User.objects.create_user(username=STUDENT, email=STUDENT)
        Profile.objects.create(user=user, onboarding_complete=True)
        response = self.client.get("/map/")
        self.assertRedirects(response, "/login/?next=/map/")
        self.client.get("/login/?next=/map/")
        send_code(self.client)
        response = self.client.post("/login/code/", {"code": last_code()})
        self.assertRedirects(response, "/map/", fetch_redirect_response=False)

    def test_unsafe_next_is_ignored(self):
        user = User.objects.create_user(username=STUDENT, email=STUDENT)
        Profile.objects.create(user=user, onboarding_complete=True)
        self.client.get("/login/?next=https://evil.example.com/")
        send_code(self.client)
        response = self.client.post("/login/code/", {"code": last_code()})
        self.assertRedirects(response, "/map/", fetch_redirect_response=False)

    def test_wrong_code_shows_error_and_stays_logged_out(self):
        send_code(self.client)
        code = last_code()
        wrong = "000000" if code != "000000" else "111111"
        response = self.client.post("/login/code/", {"code": wrong})
        assert_error(self, response, "That code isn't right.")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_expired_code_is_rejected(self):
        send_code(self.client)
        code = last_code()
        age_record(STUDENT, 10 * 60)
        response = self.client.post("/login/code/", {"code": code})
        self.assertContains(response, "That code has expired.", status_code=400)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_code_stops_working_after_5_wrong_tries(self):
        send_code(self.client)
        code = last_code()
        wrong = "000000" if code != "000000" else "111111"
        for _ in range(4):
            self.client.post("/login/code/", {"code": wrong})
        response = self.client.post("/login/code/", {"code": wrong})
        self.assertContains(response, "Too many wrong tries.", status_code=400)
        response = self.client.post("/login/code/", {"code": code})
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_code_works_only_once(self):
        send_code(self.client)
        code = last_code()
        self.client.post("/login/code/", {"code": code})
        self.client.post("/logout/")
        # Back through Welcome within 45 s: no new code is sent, the old one is used up.
        self.assertRedirects(send_code(self.client), "/login/code/")
        self.assertEqual(len(mail.outbox), 1)
        response = self.client.post("/login/code/", {"code": code})
        assert_error(self, response, "That code isn't right.")
        self.assertNotIn("_auth_user_id", self.client.session)


@override_settings(EMAIL_DELIVERY_ENABLED=True)
class RoutingAndLogoutTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username=STUDENT, email=STUDENT)
        Profile.objects.create(user=self.user, onboarding_complete=True)

    def test_root_sends_visitors_to_welcome_and_users_to_the_map(self):
        self.assertRedirects(self.client.get("/"), "/login/")
        self.client.force_login(self.user)
        self.assertRedirects(self.client.get("/"), "/map/", fetch_redirect_response=False)

    def test_logged_in_user_skips_the_welcome_screen(self):
        self.client.force_login(self.user)
        self.assertRedirects(self.client.get("/login/"), "/map/", fetch_redirect_response=False)

    def test_user_without_completed_profile_is_sent_to_onboarding(self):
        other = User.objects.create_user(username="new@yale.edu")
        self.client.force_login(other)
        self.assertRedirects(self.client.get("/"), "/onboarding/")

    def test_onboarding_placeholder_needs_login(self):
        self.assertRedirects(self.client.get("/onboarding/"), "/login/?next=/onboarding/")

    def test_map_has_log_out_button_that_logs_out(self):
        self.client.force_login(self.user)
        response = self.client.get("/map/")
        self.assertContains(response, 'action="/logout/"')
        self.assertContains(response, ">Log out</button>")
        response = self.client.post("/logout/")
        self.assertRedirects(response, "/login/")
        self.assertNotIn("_auth_user_id", self.client.session)
