from io import StringIO

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings

from accounts.models import Profile

User = get_user_model()


def run_seed():
    out, err = StringIO(), StringIO()
    call_command("seed", stdout=out, stderr=err)
    return out.getvalue(), err.getvalue()


@override_settings(GRADER_FIXED_OTP="135790")
class SeedCommandTests(TestCase):
    def test_creates_admin_and_member_graders_with_completed_profiles(self):
        out, _ = run_seed()
        admin = User.objects.get(username=settings.GRADER_ADMIN_EMAIL)
        member = User.objects.get(username=settings.GRADER_MEMBER_EMAIL)
        self.assertTrue(admin.is_staff and admin.is_superuser)
        self.assertFalse(member.is_staff or member.is_superuser)
        for user in (admin, member):
            self.assertFalse(user.has_usable_password())
            self.assertTrue(user.profile.onboarding_complete)
        self.assertIn("Seed complete.", out)

    def test_running_twice_creates_no_duplicates_and_no_errors(self):
        run_seed()
        out, err = run_seed()
        self.assertEqual(User.objects.count(), 2)
        self.assertEqual(Profile.objects.count(), 2)
        self.assertIn("Updated admin grader", out)
        self.assertEqual(err, "")

    def test_recreates_everything_after_a_database_reset(self):
        run_seed()
        User.objects.all().delete()
        run_seed()
        self.assertEqual(User.objects.count(), 2)
        self.assertEqual(Profile.objects.filter(onboarding_complete=True).count(), 2)

    def test_restores_grader_roles_if_changed(self):
        run_seed()
        User.objects.filter(username=settings.GRADER_ADMIN_EMAIL).update(is_superuser=False)
        Profile.objects.update(onboarding_complete=False)
        run_seed()
        self.assertTrue(User.objects.get(username=settings.GRADER_ADMIN_EMAIL).is_superuser)
        self.assertEqual(Profile.objects.filter(onboarding_complete=True).count(), 2)

    @override_settings(GRADER_FIXED_OTP="")
    def test_warns_when_fixed_code_is_missing(self):
        _, err = run_seed()
        self.assertIn("GRADER_FIXED_OTP is not set", err)
