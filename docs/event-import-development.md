# Event import foundation (#33)

This branch prepares saved Yale Connect/SOM ICS feeds without requiring the
`Event` model from #31. It does not import records, populate the map, fetch live
feeds, or invoke geocoding, image generation, or paid services.

## Run an offline preview

Install `requirements-dev.txt` in the project virtual environment, then run:

```sh
DJANGO_DEBUG=true python manage.py preview_event_import core/tests/fixtures/event_import.ics --source yale_connect --now 2026-11-17T00:00:00-05:00 --until 2027-01-01T00:00:00-05:00
DJANGO_DEBUG=true python manage.py test core.tests.test_event_import
```

The fixture is fictional. `--now` defaults to the current time. `--until` is an
exclusive cutoff on event start; both arguments require timezone offsets. Output
is JSON with candidate events and counts for preparation and skip reasons.
This is a preview, not a completed import or database-idempotency check.

## Current behavior

- Uses `icalendar` for folded lines, escaped text and timezone-aware ICS values.
- Uses URL `id`, falling back to UID, for source identity.
- Truncates names/descriptions to #31's 30/150-character limits.
- Maps known categories and career tags before ordered keyword rules; defaults
  to `social_community`. Hidden source types are excluded. No LLM fallback yet.
- Filters events whose start is before now, following the source reference.
  This also skips ongoing events; confirm whether #33 should retain these.
- Deduplicates within one feed by source identity or exact address/start/end.
  This is not cross-run, cross-source, or database duplicate enforcement.
- Rejects missing/invalid URLs, times or required text. Reports cancellations,
  recurring entries and common online/placeholder locations separately.
- All-day/floating times and missing end times are unsupported. DURATION is
  accepted. No invented end times or recurrence expansion.
- Unknown price remains `None`. An address is not proof of New Haven location;
  the geographic filter must follow geocoding before persistence.

## Integration once #31 lands

1. Adapt `Candidate` to the final Event schema and shared category enum. Agree
   on nullable unknown prices, source identity, image placeholders and addresses.
2. Add database upsert/idempotency and exact duplicate enforcement, including
   concurrent writes and collisions between imported and user-created events.
3. Reuse shared geocoding/image services. Add cached coordinates, verified New
   Haven filtering, image cap, failure fallback and optional LLM classification.
4. Add bounded HTTP fetching, per-source failure isolation, Ticketmaster after
   coverage verification, and Localist only after access is verified. Source
   references are `.documentation/aggregator-sources.md` and `event-sources.md`.
5. Add the initial population command and shared map expiry filtering.
6. Add the authenticated scheduler endpoint and a deployment-safe overlap guard;
   a process-local lock alone cannot coordinate multiple Gunicorn workers.
   Configure cron only when a real persistence path is ready.

The source reference's proposed schema and fuzzy duplicate rule differ from
#31/#33. This foundation deliberately creates no model or migration and uses
#33's exact duplicate rule provisionally. Source attribution, unknown prices,
image cap and treatment of unsupported events still require team decisions.
