from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.yale_catalog import seed_catalog


class Command(BaseCommand):
    help = "Legacy local command: seed provisional Yale choices. Prefer manage.py seed."

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG or settings.APP_ENV != "local":
            raise CommandError("Demo choices are only allowed with DEBUG enabled and APP_ENV=local.")
        seed_catalog()
        self.stdout.write(self.style.SUCCESS("Provisional Yale catalog ready. Use manage.py seed for grader accounts too."))
