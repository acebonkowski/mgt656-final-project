"""Persist prepared events using #31's model; all enrichment is explicit.

No external calls. Unknown prices and unverified locations remain skipped until
team policy/provider integration is ready. Existing source records are retained.
"""
from collections import Counter
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from core.models import Event


def persist_candidates(candidates, enrichments, *, now):
    """enrichments maps external IDs to verified price/coordinates for one source.

    Sequential exact duplicates are rejected, including user-created events.
    A database constraint protects source identity across concurrent imports.
    Cross-source/location concurrency still requires the scheduled-job lock.
    """
    counts = Counter()
    for candidate in candidates:
        identity = {"source": candidate.source, "external_id": candidate.external_id}
        if candidate.ends_at <= now:
            counts["expired"] += 1
            continue
        if Event.objects.filter(**identity).exists():
            counts["already_imported"] += 1
            continue
        extra = enrichments.get(candidate.external_id, {})
        if extra.get("price") is None:
            counts["unknown_price"] += 1
            continue
        if extra.get("city") != "New Haven" or extra.get("state") != "CT":
            counts["unverified_location"] += 1
            continue
        try:
            lat = Decimal(str(extra["latitude"]))
            lon = Decimal(str(extra["longitude"]))
            price = Decimal(str(extra["price"]))
            if not all(value.is_finite() for value in (lat, lon, price)):
                raise ValueError("Non-finite number")
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError("Coordinates out of range")
            values = dict(identity, name=candidate.name, description=candidate.description,
                          category=candidate.category, start_at=candidate.starts_at,
                          end_at=candidate.ends_at, location=candidate.location_text,
                          link=candidate.link, creator=None, latitude=lat, longitude=lon,
                          price=price, image="")
            event = Event(**values)
            # Imported images are optional (placeholder); user forms still require them.
            event.full_clean(exclude=["image", "description"], validate_unique=False,
                             validate_constraints=False)
            if price < 0 or event.end_at <= event.start_at:
                raise ValueError("Invalid price or interval")
            with transaction.atomic():
                if Event.objects.filter(location=event.location, start_at=event.start_at,
                                        end_at=event.end_at).exists():
                    counts["duplicates"] += 1
                    continue
                event.save(force_insert=True)
            counts["imported"] += 1
        except IntegrityError:
            if Event.objects.filter(**identity).exists():
                counts["already_imported"] += 1
            else:
                raise
        except (ValidationError, InvalidOperation, ValueError, KeyError, TypeError):
            counts["invalid_enrichment"] += 1
    return counts
