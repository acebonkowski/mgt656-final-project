from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Program, School


class Command(BaseCommand):
    help = "Add clearly labelled, local-only sample onboarding choices (not approved Yale data)."

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG or settings.APP_ENV != "local":
            raise CommandError("Demo choices are only allowed with DEBUG enabled and APP_ENV=local.")
        for school_name, programs in [
            ("Sample school A — local demo", ["Sample program A1", "Sample program A2"]),
            ("Sample school B — local demo", ["Sample program B1"]),
        ]:
            school, _ = School.objects.get_or_create(name=school_name)
            for name in programs:
                Program.objects.get_or_create(school=school, name=name)
        self.stdout.write(self.style.SUCCESS("Local demo schools and programs are ready."))
