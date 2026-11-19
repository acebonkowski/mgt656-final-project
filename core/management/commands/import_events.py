import json
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from core.event_import.ics import aware_datetime
from core.event_import.runner import DEFAULT_SOURCES, acquire_lock, default_until, release_lock, run_import


class Command(BaseCommand):
    help = "Import public event feeds (initial population or daily refresh)."

    def add_arguments(self, parser):
        parser.add_argument("--source", choices=DEFAULT_SOURCES, action="append")
        parser.add_argument("--until", help="Exclusive ISO start cutoff with offset; default Jan 1, 2027 Eastern")
        parser.add_argument("--release-lock", metavar="TOKEN", help="Recovery only after confirming the old worker stopped")

    def handle(self, *args, **options):
        if options["release_lock"]:
            self.stdout.write(f"Released locks: {release_lock(options['release_lock'])}")
            return
        try:
            until = aware_datetime(datetime.fromisoformat(options["until"])) if options["until"] else default_until()
            if until <= timezone.now():
                raise ValueError("Window must end in the future")
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        token = acquire_lock()
        if token is None:
            raise CommandError("An event import is already active")
        result = run_import(token, sources=options["source"] or DEFAULT_SOURCES, until=until)
        self.stdout.write(json.dumps(dict(result)))
