import json

from django.core.management.base import BaseCommand

from core.saved_searches import run_saved_searches


class Command(BaseCommand):
    help = "Look for new events matching every saved search (#37). Safe to run more than once."

    def handle(self, *args, **options):
        self.stdout.write(json.dumps(dict(run_saved_searches())))
