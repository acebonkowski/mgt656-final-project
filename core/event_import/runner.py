"""Shared bounded runner for CLI and the daily webhook."""
import logging
import time
from collections import Counter
from dataclasses import replace
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import close_old_connections
from django.utils import timezone

from core.models import Event, EventImportLock
from . import enrichment
from .persistence import persist_candidates
from .sources import source_batches

logger = logging.getLogger(__name__)
DEFAULT_SOURCES = ("yale_connect", "som", "ticketmaster")


def acquire_lock():
    EventImportLock.objects.get_or_create(name="events")
    token = str(uuid4())
    updated = EventImportLock.objects.filter(name="events", token="").update(token=token, started_at=timezone.now())
    return token if updated else None


def release_lock(token):
    return EventImportLock.objects.filter(name="events", token=token).update(token="", started_at=None)


def default_until():
    return datetime(2027, 1, 1, tzinfo=ZoneInfo("America/New_York"))


def run_import(token, *, sources=DEFAULT_SOURCES, until=None):
    """Caller owns lock. Stop between operations after budget; never log secrets.

    A crashed process leaves the lock held: explicit operator recovery is safer
    than expiring a lock while an old worker may still be writing.
    """
    counts = Counter()
    now = timezone.now()
    until = until or now + timezone.timedelta(days=settings.AGGREGATOR_WINDOW_DAYS)
    deadline = time.monotonic() + settings.AGGREGATOR_RUN_SECONDS
    image_attempts = classification_attempts = 0
    logger.info("event_import start run=%s", token)
    try:
        if not EventImportLock.objects.filter(name="events", token=token).exists():
            raise ValueError("Import lock is not owned")
        if until <= now:
            raise ValueError("Import window has ended; set a future --until")
        for source in sources:
            if source == "ticketmaster" and not settings.TICKETMASTER_API_KEY:
                counts["unconfigured_sources"] += 1
                logger.info("event_import source=ticketmaster skipped=not_configured")
                continue
            if time.monotonic() >= deadline:
                counts["deadline_reached"] += 1
                break
            try:
                for batch in source_batches(source, now=now, until=until, deadline=deadline):
                    counts["pagination_limit"] += batch.counts["pagination_limit"]
                    counts["skipped_past"] += batch.counts["past_start"]
                    counts["rejected_duplicates"] += batch.counts["duplicates"]
                    counts["invalid_source_events"] += batch.counts["invalid_or_unsupported"]
                    for candidate in batch.events:
                        if time.monotonic() >= deadline:
                            counts["deadline_reached"] += 1
                            break
                        if Event.objects.filter(source=candidate.source, external_id=candidate.external_id).exists():
                            counts["already_imported"] += 1
                            continue
                        try:
                            if candidate.category_source == "default" and classification_attempts < settings.AGGREGATOR_MAX_CLASSIFICATIONS_PER_RUN:
                                classification_attempts += 1
                                try:
                                    category = enrichment.ai_category(candidate)
                                    if category == "not_discoverable":
                                        counts["not_discoverable"] += 1
                                        continue
                                    candidate = replace(candidate, category=category, category_source="llm")
                                except Exception as exc:
                                    counts["classification_failed"] += 1
                                    logger.warning("event_import classification_failed type=%s", type(exc).__name__)
                            coordinates = enrichment.locate(candidate)
                            if coordinates is None:
                                counts["unverified_location"] += 1
                                continue
                            result = persist_candidates([candidate], {candidate.external_id: dict(coordinates, price=candidate.price)}, now=timezone.now())
                            counts["imported"] += result["imported"]
                            counts["rejected_duplicates"] += result["duplicates"]
                            counts["already_imported"] += result["already_imported"]
                            counts["failed"] += result["invalid_enrichment"]
                            counts["skipped_past"] += result["expired"]
                            if result["imported"] and image_attempts < settings.AGGREGATOR_MAX_IMAGES_PER_RUN and time.monotonic() < deadline:
                                image_attempts += 1  # Failures consume budget too.
                                try:
                                    event = Event.objects.get(source=candidate.source, external_id=candidate.external_id)
                                    enrichment.generate_event_image(event)
                                    counts["images_generated"] += 1
                                except Exception as exc:
                                    counts["image_failed"] += 1
                                    logger.warning("event_import image_failed type=%s", type(exc).__name__)
                        except Exception as exc:
                            counts["failed"] += 1
                            logger.warning("event_import event_failed source=%s type=%s", source, type(exc).__name__)
                    if counts["deadline_reached"]:
                        break
            except Exception as exc:
                counts["failed"] += 1
                counts["sources_failed"] += 1
                logger.warning("event_import source_failed source=%s type=%s", source, type(exc).__name__)
            logger.info("event_import progress source=%s counts=%s", source, dict(counts))
        return counts
    finally:
        release_lock(token)
        for name in ("imported", "rejected_duplicates", "skipped_past", "failed"):
            counts.setdefault(name, 0)
        logger.info("event_import end run=%s counts=%s", token, dict(counts))


def background_import(token):
    close_old_connections()
    try:
        run_import(token)
    except Exception as exc:
        logger.error("event_import aborted type=%s", type(exc).__name__)
    finally:
        close_old_connections()
