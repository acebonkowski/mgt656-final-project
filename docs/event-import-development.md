# Event import foundation (#33)

This branch includes #31's Event implementation and prepares saved Yale
Connect/SOM ICS feeds. It supports offline database imports with verified
enrichment (see below). It does not fetch live feeds or invoke geocoding, image
generation, or paid services.

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

## Preview behavior

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

## Integration checklist

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
#31/#33. The importer reuses #31's model and uses #33's exact duplicate rule.
Its additional migration protects source identity. Source attribution, unknown prices,
image cap and treatment of unsupported events still require team decisions.

## Integrated with #31 (PR #46)

The #31 branch is now merged into this development branch. The offline preview
still works; a new persistence layer maps candidates into its actual `Event`
fields (`start_at`, `end_at`, `location`) and validates its category choices.
Migration `0004_event_import_identity` adds a conditional unique constraint on
nonempty `(source, external_id)`. If existing imported records violate this
constraint, migration will fail rather than discard or rewrite them.

The `import_saved_events` command requires a saved ICS and a JSON object keyed
by external ID, containing **verified** enrichment, for example:

```json
{"1001": {"price": "0.00", "latitude": "41.308300", "longitude": "-72.927900", "city": "New Haven", "state": "CT"}}
```

```sh
python manage.py migrate
python manage.py import_saved_events saved.ics --source som --enrichment verified.json --dry-run
python manage.py import_saved_events saved.ics --source som --enrichment verified.json
```

Use your normal local Django configuration. The dry run parses the feed and
reports candidate counts; it does not validate enrichment against the database.
The real import validates each record and reports imported, already imported,
duplicate, unknown-price, unverified-location, expired, and invalid-data counts.
Missing prices are skipped, never silently converted to free. The JSON is an
operator-verified input, not proof from a geocoder; automatic geographic
verification remains pending. Coordinates must fit the model's six decimal places.

Existing source identities are left unchanged on subsequent runs. Exact location
and time collisions with any existing event are rejected. Concurrent imports of
the same identity are database-protected; cross-source or user-created races
still need shared coordination before enabling scheduled imports. Imported
records have no creator and use a text image placeholder. User-created events
continue to require images and prices. No API, geocoding, storage, or LLM calls
are made by this command. It has not been run against the development database.

The remaining checklist above still applies except for the field mapping,
sequential duplicate detection and source-identity constraint now implemented.
When #32 merges, reconcile the detail-page placeholder and its `icalendar`
version with this branch. Unknown-price policy still needs a team decision;
this integration does not change #31's non-null price schema.

Local image dependencies were installed after adding Homebrew libheif.
Building pillow-heif on this machine required setting SDKROOT to the installed
MacOSX26.5.sdk for the pip command; the default MacOSX27.0.sdk failed at linking.
The virtual environment still uses Python 3.15; the repository and CI specify
Python 3.12. The map creation fixture uses tomorrow to avoid expiring at 8 PM
on the day the test runs.
