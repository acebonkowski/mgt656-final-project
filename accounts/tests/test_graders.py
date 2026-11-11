"""Grader login with the fixed code (per Kyle) and /admin access (#6)."""

from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings

from accounts.models import LoginCode
from accounts.tests.helpers import assert_error, FAKE_FIXED_CODE, send_code

ADMIN = settings.GRADER_ADMIN_EMAIL
MEMBER = settings.GRADER_MEMBER_EMAIL


def logged_in(client):
    return "_auth_user_id" in client.session


@override_settings(GRADER_FIXED_OTP=FAKE_FIXED_CODE, EMAIL_DELIVERY_ENABLED=True)
class GraderLoginTests(TestCase):
    def setUp(self):
        call_command("seed", stdout=open("/dev/null", "w"))

    def log_in(self, email, code=FAKE_FIXED_CODE):
        send_code(self.client, email)
        return self.client.post("/login/code/", {"code": code})

    def test_both_graders_log_in_with_fixed_code_without_email(self):
        for email in (ADMIN, MEMBER):
            with self.subTest(email=email):
                response = self.log_in(email)
                self.assertRedirects(response, "/map/", fetch_redirect_response=False)
                self.assertTrue(logged_in(self.client))
                self.client.post("/logout/")
                LoginCode.objects.filter(email=email).update(sent_at=None)
        self.assertEqual(len(mail.outbox), 0)

    def test_grader_address_is_case_insensitive(self):
        response = self.log_in(ADMIN.upper())
        self.assertRedirects(response, "/map/", fetch_redirect_response=False)

    def test_fixed_code_is_rejected_for_any_other_address(self):
        send_code(self.client, "someone@yale.edu")
        response = self.client.post("/login/code/", {"code": FAKE_FIXED_CODE})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(logged_in(self.client))

    def test_wrong_code_for_grader_is_rejected(self):
        response = self.log_in(ADMIN, "000000")
        assert_error(self, response, "That code isn't right.")
        self.assertFalse(logged_in(self.client))

    def test_five_wrong_codes_lock_grader_for_15_minutes(self):
        send_code(self.client, ADMIN)
        for _ in range(4):
            self.client.post("/login/code/", {"code": "000000"})
        with self.assertLogs("accounts.otp", level="WARNING"):
            response = self.client.post("/login/code/", {"code": "000000"})
        self.assertContains(response, "Try again in 15 minutes.", status_code=400)
        response = self.client.post("/login/code/", {"code": FAKE_FIXED_CODE})
        self.assertContains(response, "Try again in 15 minutes.", status_code=400)
        self.assertFalse(logged_in(self.client))
        record = LoginCode.objects.get(email=ADMIN)
        record.locked_until -= timedelta(minutes=15)
        record.save()
        response = self.client.post("/login/code/", {"code": FAKE_FIXED_CODE})
        self.assertRedirects(response, "/map/", fetch_redirect_response=False)

    @override_settings(GRADER_FIXED_OTP="")
    def test_grader_login_disabled_without_fixed_code_and_no_email_sent(self):
        response = send_code(self.client, ADMIN)
        assert_error(self, response, "Grader login isn't set up yet.")
        self.assertEqual(len(mail.outbox), 0)

    def test_admin_grader_opens_admin_site(self):
        self.log_in(ADMIN)
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Site administration")

    def test_member_grader_cannot_open_admin_site(self):
        self.log_in(MEMBER)
        response = self.client.get("/admin/", follow=True)
        self.assertEqual(response.redirect_chain[-1][0], "/map/")

    def test_logged_out_admin_visit_goes_to_welcome_not_a_password_form(self):
        response = self.client.get("/admin/", follow=True)
        self.assertEqual(response.redirect_chain[-1][0], "/login/?next=%2Fadmin%2F")
        self.assertContains(response, "Your Yale email address")
        self.assertNotContains(response, 'type="password"')

    def test_admin_password_login_post_is_not_available(self):
        response = self.client.post("/admin/login/", {"username": ADMIN, "password": "x"})
        self.assertRedirects(response, "/login/")
        self.assertFalse(logged_in(self.client))
