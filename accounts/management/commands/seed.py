"""
`python manage.py seed`: demo data and the grader accounts.

Safe to run more than once: it creates or updates, never duplicates. Run it
after every database reset and after the first deploy of an environment.

#6 seeds the two grader accounts. They have no usable password: they log in on
the Welcome screen with the fixed code from GRADER_FIXED_OTP. #7 adds the Yale
schools/programs, fake student profiles and the graders' profile fields here.
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import Profile
from core.yale_catalog import seed_catalog
from core.models import Program


class Command(BaseCommand):
    help = "Create or update demo data and the grader accounts (safe to run more than once)."

    @transaction.atomic
    def handle(self, *args, **options):
        seed_catalog()
        graders = [
            (settings.GRADER_ADMIN_EMAIL, True),    # admin: staff + superuser, can open /admin
            (settings.GRADER_MEMBER_EMAIL, False),  # member: a regular student
        ]
        for email, is_admin in graders:
            self._seed_grader(email.strip().lower(), is_admin)

        if not settings.GRADER_FIXED_OTP:
            self.stderr.write(self.style.WARNING(
                "GRADER_FIXED_OTP is not set: the grader accounts exist but can't log in."
            ))
        self.stdout.write(self.style.SUCCESS("Seed complete."))

    def _seed_grader(self, email, is_admin):
        user, created = get_user_model().objects.get_or_create(
            username=email, defaults={"email": email}
        )
        user.email = email
        user.is_active = True
        user.is_staff = is_admin
        user.is_superuser = is_admin
        user.set_unusable_password()
        user.save()
        profile, _ = Profile.objects.get_or_create(user=user)
        if not profile.display_name:
            profile.display_name = "Demo administrator" if is_admin else "Demo student"
        if not profile.program_id:
            profile.program = Program.objects.get(
                school__name="School of Management", name="Master of Business Administration (M.B.A.)")
        profile.onboarding_complete = True
        profile.save()
        role = "admin" if is_admin else "member"
        self.stdout.write(f"{'Created' if created else 'Updated'} {role} grader: {email}")
