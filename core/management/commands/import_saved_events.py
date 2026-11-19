"""Explicit offline import of a saved feed with verified enrichment."""
import json
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from core.event_import.ics import SOURCES, parse_feed
from core.event_import.persistence import persist_candidates


class Command(BaseCommand):
    help = "Import saved ICS with verified price/coordinates JSON; no network or image API calls."

    def add_arguments(self, parser):
        parser.add_argument("file", type=Path)
        parser.add_argument("--source", choices=SOURCES, required=True)
        parser.add_argument("--enrichment", type=Path, required=True)
        parser.add_argument("--until", help="Exclusive ISO start-time cutoff with offset")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        now = timezone.now()
        try:
            extra = json.loads(options["enrichment"].read_text())
            if not isinstance(extra, dict) or not all(isinstance(v, dict) for v in extra.values()):
                raise ValueError("Enrichment must map external IDs to objects")
            until = datetime.fromisoformat(options["until"]) if options["until"] else None
            preview = parse_feed(options["file"].read_bytes(), options["source"], now=now, until=until)
        except (OSError, ValueError, TypeError) as exc:
            raise CommandError(f"Cannot import feed: {exc}") from exc
        counts = {} if options["dry_run"] else persist_candidates(preview.events, extra, now=now)
        self.stdout.write(json.dumps({"dry_run": options["dry_run"],
                                      "parsing": dict(preview.counts), "persistence": dict(counts)}))
