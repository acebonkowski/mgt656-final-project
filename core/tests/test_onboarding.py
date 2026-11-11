from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import Profile, Program, School


class OnboardingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="student")
        cls.other_user = get_user_model().objects.create_user(username="other")
        cls.school = School.objects.create(name="Test school")
        cls.other_school = School.objects.create(name="Other school")
        cls.program = Program.objects.create(school=cls.school, name="Test program")
        cls.other_program = Program.objects.create(school=cls.other_school, name="Other program")

    def setUp(self):
        self.client.force_login(self.user)

    def payload(self, **changes):
        return {"display_name": "Alex", "school": self.school.pk, "program": self.program.pk, **changes}

    def test_anonymous_user_cannot_view_or_save(self):
        self.client.logout()
        for response in [self.client.get(reverse("onboarding")), self.client.post(reverse("onboarding"), self.payload())]:
            self.assertEqual(response.status_code, 302)
        self.assertFalse(Profile.objects.exists())

    def test_page_contains_required_fields_and_default_image(self):
        response = self.client.get(reverse("onboarding"))
        self.assertContains(response, "Let's get to know you better.")
        self.assertContains(response, "core/bulldog.svg")
        self.assertContains(response, "Start discovering")
        self.assertEqual(set(response.context["form"].fields), {"display_name", "school", "program"})

    def test_empty_fields_and_whitespace_name_rejected(self):
        for payload in [{}, self.payload(display_name="   ")]:
            response = self.client.post(reverse("onboarding"), payload)
            self.assertIn("display_name", response.context["form"].errors)
        response = self.client.post(reverse("onboarding"), {})
        self.assertEqual(set(response.context["form"].errors), {"display_name", "school", "program"})
        self.assertFalse(Profile.objects.exists())

    def test_program_must_belong_to_selected_school(self):
        response = self.client.post(reverse("onboarding"), self.payload(program=self.other_program.pk))
        self.assertIn("program", response.context["form"].errors)
        self.assertFalse(Profile.objects.exists())

    def test_invalid_school_is_a_form_error(self):
        for school in ["invalid", "999999", ""]:
            response = self.client.post(reverse("onboarding"), self.payload(school=school))
            self.assertIn("school", response.context["form"].errors)

    def test_save_belongs_to_current_user_and_repeated_posts_update(self):
        payload = self.payload(user=self.other_user.pk)
        self.assertRedirects(self.client.post(reverse("onboarding"), payload), reverse("map"))
        self.client.post(reverse("onboarding"), self.payload(display_name="New name"))
        profile = Profile.objects.get()
        self.assertEqual(profile.user, self.user)
        self.assertEqual(profile.display_name, "New name")
        self.assertEqual(profile.school, self.school)
        self.assertFalse(Profile.objects.filter(user=self.other_user).exists())

    def test_existing_profile_preselects_its_school_and_program(self):
        Profile.objects.create(user=self.user, display_name="Alex", program=self.program)
        form = self.client.get(reverse("onboarding")).context["form"]
        self.assertEqual(form.initial["school"], self.school.pk)
        self.assertEqual(list(form.fields["program"].queryset), [self.program])

    @override_settings(ONBOARDING_SUCCESS_URL="/discover/")
    def test_success_destination_is_configurable(self):
        response = self.client.post(reverse("onboarding"), self.payload())
        self.assertRedirects(response, "/discover/", fetch_redirect_response=False)


class DemoSeedTests(TestCase):
    @override_settings(DEBUG=True, APP_ENV="local")
    def test_seed_is_repeatable(self):
        for _ in range(2):
            call_command("seed_onboarding_demo", stdout=StringIO())
        self.assertEqual(School.objects.count(), 2)
        self.assertEqual(Program.objects.count(), 3)

    def test_seed_refused_outside_local_debug(self):
        for debug, environment in [(False, "local"), (True, "staging"), (True, "production")]:
            with override_settings(DEBUG=debug, APP_ENV=environment):
                with self.assertRaises(CommandError):
                    call_command("seed_onboarding_demo", stdout=StringIO())
        self.assertFalse(School.objects.exists())
