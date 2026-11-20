import json
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from core.event_import.ics import aware_datetime
from core.event_import.runner import DEFAULT_SOURCES, acquire_lock, default_until, next_days_window, release_lock, run_import


class Command(BaseCommand):
    help = "Import public event feeds (initial population or daily refresh)."

    def add_arguments(self, parser):
        parser.add_argument("--source", choices=DEFAULT_SOURCES, action="append")
        parser.add_argument("--limit-per-source", type=int, help="Maximum new events to attempt per source (for small live checks)")
        parser.add_argument("--until", help="Exclusive ISO start cutoff with offset; default Jan 1, 2027 Eastern")
        parser.add_argument("--tomorrow", action="store_true", help="Import events starting tomorrow, midnight to midnight in America/New_York")
        parser.add_argument("--next-week", action="store_true", help="Import the next seven full days, starting tomorrow in America/New_York")
        parser.add_argument("--release-lock", metavar="TOKEN", help="Recovery only after confirming the old worker stopped")

    def handle(self, *args, **options):
        if options["limit_per_source"] is not None and options["limit_per_source"] < 1:
            raise CommandError("--limit-per-source must be positive")
        if options["release_lock"]:
            self.stdout.write(f"Released locks: {release_lock(options['release_lock'])}")
            return
        if options["tomorrow"] and options["until"]:
            raise CommandError("Use either --tomorrow or --until")
        if options["next_week"] and (options["tomorrow"] or options["until"]):
            raise CommandError("Use --next-week without --tomorrow or --until")
        starts_from = None
        try:
            if options["tomorrow"] or options["next_week"]:
                days = 7 if options["next_week"] else 1
                starts_from, until = next_days_window(days)
            else:
                until = aware_datetime(datetime.fromisoformat(options["until"])) if options["until"] else default_until()
            if until <= timezone.now():
                raise ValueError("Window must end in the future")
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        token = acquire_lock()
        if token is None:
            raise CommandError("An event import is already active")
        result = run_import(token, sources=options["source"] or DEFAULT_SOURCES, until=until,
                            limit_per_source=options["limit_per_source"], starts_from=starts_from)
        self.stdout.write(json.dumps(dict(result)))
