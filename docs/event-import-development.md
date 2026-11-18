# Event importer development

The #33 branch includes #31's Event model and shared geocoding, OpenRouter and
image-storage services. `import_events` and the secret-authenticated webhook use
one runner and a database lock. `preview_event_import` and `import_saved_events`
remain available for offline inspection and explicitly enriched imports.

## Data contract

`Candidate` is independent of the database. Persistence maps `starts_at`,
`ends_at`, `location_text` to `start_at`, `end_at`, `location`; validates model
categories and limits; preserves null unknown prices; and stores source identity.
User-created forms still require price and image. Imported pages show source,
unknown price and an image placeholder when no image is available.

Migration 0004 protects nonempty (source, external_id). Migration 0005 adds the
job lock, geocode cache and nullable price. Migrations fail on pre-existing
constraint violations rather than discard records. No deployment or development
database imports are part of automated tests.

## Source handling

Sources follow `.documentation/aggregator-sources.md` and `event-sources.md`.
ICS parsing supports aware timestamps and DURATION. All-day/floating, recurring,
missing-end and malformed entries are counted/skipped. Past starts are skipped
(including ongoing events), as directed by the source reference. Names and
descriptions truncate to 30/150. Categories map first, then ordered keywords,
then optional capped LLM classification. Event URLs must be HTTP(S).

Ticketmaster uses city/state filtering, up to five pages of 200 records (its
1,000-result deep-paging limit), and bounded requests. Missing end times are
skipped rather than guessed. Unequal min/max prices remain unknown because a
minimum is not an exact admission price. Localist is not enabled: the reference
marks access unverified, and the issue makes that adapter conditional.

Feed fetching restricts HTTPS hosts/redirects, limits response size to 8 MiB,
and uses timeouts. Source failures do not abort others. Each scheduled run has
a finite runtime budget checked between operations; an in-flight request can
finish after the budget. Repeating runs advances past already imported events.

## Location verification

Source coordinates require New Haven/CT locality plus a coordinate sanity
boundary. ICS uses the existing geocoder's top result, requiring New Haven and
Connecticut/CT in the address plus that boundary. This is provider-locality
verification, not a municipal GIS polygon. Matches are cached for 30 days;
negative results for one day. Provider errors are not cached. Coordinates are
quantized to the Event model's six decimal places.

## Identity and locking

Existing source identities are retained unchanged on re-import. Exact
location/start/end collisions are rejected, including across sources. All live
imports share the database job lock. The unique source-ID constraint protects
same-identity races. A further database constraint protects exact
location/start/end uniqueness across sources and user-created events, including
concurrent writes. Existing duplicate rows make that migration fail safely and
require explicit team review; no records are automatically removed.

The lock intentionally does not expire automatically: a slow worker must not
continue after another worker takes its lock. After confirming a crashed worker
has stopped, use the documented token-specific recovery command. Redeployments
can interrupt a background thread; this is not a durable task queue.

## Offline workflow

```sh
python manage.py preview_event_import core/tests/fixtures/event_import.ics --source som --now 2026-11-17T00:00:00-05:00
python manage.py import_saved_events saved.ics --source som --enrichment verified.json --dry-run
python manage.py import_saved_events saved.ics --source som --enrichment verified.json
```

Enrichment maps IDs to objects with latitude, longitude, city=New Haven, state=CT,
and price (nullable). Values must be operator verified; these commands do not
call the geocoder. A dry run parses and counts only; it does not validate against
the database. Fixtures are synthetic, not claims about real events.

## Local environment

Local testing uses Python 3.15, while CI specifies 3.12. Installing Homebrew
libheif and building pillow-heif with SDKROOT pointing at the installed
MacOSX26.5.sdk resolved local image-package installation. The default macOS 27 SDK
failed at the linker step. No system-default SDK or Python version was changed.

Read-only public-feed checks prepared 325 Yale Connect and 60 SOM candidates
before geocoding/city filtering. No provider-backed geocoding, AI calls, database
population, deployment or cron-job.org provisioning was performed by that check.
