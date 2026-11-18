"""Offline preview only: never writes Event records or calls external services."""

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from core.event_import.ics import SOURCES, parse_feed


class Command(BaseCommand):
    help = "Preview a saved Yale/SOM ICS feed as JSON, without database or network access."
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument("file", type=Path)
        parser.add_argument("--source", choices=SOURCES, required=True)
        parser.add_argument("--now", help="ISO date-time with offset; defaults to current time")
        parser.add_argument("--until", help="Exclusive start-time cutoff, ISO date-time with offset")

    def handle(self, *args, **options):
        try:
            now = datetime.fromisoformat(options["now"]) if options["now"] else timezone.now()
            until = datetime.fromisoformat(options["until"]) if options["until"] else None
            preview = parse_feed(options["file"].read_bytes(), options["source"], now=now, until=until)
        except (OSError, ValueError, TypeError) as exc:
            raise CommandError(f"Cannot preview feed: {exc}") from exc
        self.stdout.write(json.dumps({"mode": "preview_only", "counts": dict(preview.counts),
                                      "events": [asdict(e) for e in preview.events]},
                                     default=str, indent=2))
