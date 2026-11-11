from io import StringIO

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import resolve, reverse

from accounts.models import LoginCode, Profile
from accounts.tests.helpers import last_code, send_code
from core.models import Program, School
from core.yale_catalog import CATALOG


@override_settings(EMAIL_DELIVERY_ENABLED=True, GRADER_FIXED_OTP="135790")
class OnboardingJourneyTests(TestCase):
    def setUp(self):
        call_command("seed", stdout=StringIO(), stderr=StringIO())
        self.program = Program.objects.get(school__name="School of Management", name="Master of Business Administration (M.B.A.)")

    def test_new_student_completes_onboarding_and_next_login_skips_it(self):
        email = "new.student@yale.edu"
        send_code(self.client, email)
        self.assertRedirects(self.client.post("/login/code/", {"code": last_code()}), "/onboarding/")
        response = self.client.get("/onboarding/")
        self.assertTemplateUsed(response, "core/onboarding.html")
        user = get_user_model().objects.get(username=email)
        self.assertFalse(user.profile.onboarding_complete)
        self.client.post("/onboarding/", {})
        user.profile.refresh_from_db()
        self.assertFalse(user.profile.onboarding_complete)
        response = self.client.post("/onboarding/", {
            "display_name": "Alex", "school": self.program.school_id, "program": self.program.pk,
        })
        self.assertRedirects(response, "/map/")
        user.profile.refresh_from_db()
        self.assertTrue(user.profile.onboarding_complete)
        self.assertEqual(user.profile.program, self.program)
        self.assertEqual(Profile.objects.filter(user=user).count(), 1)
        self.client.post("/logout/")
        LoginCode.objects.filter(email=email).update(sent_at=None)
        send_code(self.client, email)
        self.assertRedirects(self.client.post("/login/code/", {"code": last_code()}), "/map/")

    def test_both_route_names_resolve_to_the_same_real_screen(self):
        self.assertEqual(reverse("onboarding"), reverse("accounts:onboarding"))
        self.assertEqual(resolve(reverse("accounts:onboarding")).func.__name__, "onboarding")

    def test_seed_is_repeatable_and_does_not_overwrite_student_or_grader_choices(self):
        admin = Profile.objects.get(user__username=settings.GRADER_ADMIN_EMAIL)
        admin.display_name = "Chosen nickname"
        admin.program = Program.objects.exclude(pk=self.program.pk).first()
        admin.save()
        expected_program = admin.program_id
        count = Program.objects.count()
        call_command("seed", stdout=StringIO(), stderr=StringIO())
        admin.refresh_from_db()
        self.assertEqual(admin.display_name, "Chosen nickname")
        self.assertEqual(admin.program_id, expected_program)
        self.assertEqual(Program.objects.count(), count)
        self.assertEqual(School.objects.filter(is_active=True).count(), len(CATALOG))
        self.assertFalse(School.objects.filter(name="Yale College").exists())

    def test_ab_page_is_public_even_without_a_profile(self):
        response = self.client.get(reverse("abtest:page"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Profile.objects.filter(user__username="new.student@yale.edu").exists())
