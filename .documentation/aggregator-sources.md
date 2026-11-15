# Yale & New Haven Event Sources

Reference for the event-import feature (Django + Supabase Postgres). Verified 2026-11-15.

## Sources

| # | Name | Link / feed | Format | Coordinates | Status |
|---|------|-------------|--------|-------------|--------|
| 1 | Yale Connect (university-wide student orgs and public events) | `https://yaleconnect.yale.edu/ical/yale/ical_yale.ics` (302 to `static-prod-us-east-1.campusgroups.com`) | ICS | No GEO, address text in LOCATION | Works, fetched OK |
| 2 | Yale SOM portal (SOM clubs, career-tagged events) | `https://groups.som.yale.edu/ical/yalesom/ical_yalesom.ics` (302 to same CDN) | ICS | No GEO, address text in LOCATION | Works, fetched OK |
| 3 | Yale University calendar (Localist) | `https://events.yale.edu/api/2/events` | JSON | Yes (`geo.latitude`, `geo.longitude`) | **Unverified.** Docs say anonymous access; my fetch was blocked by robots rules |
| 4 | Ticketmaster Discovery API (New Haven venues) | `https://app.ticketmaster.com/discovery/v2/events.json?apikey=KEY&city=New Haven&stateCode=CT` | JSON | Yes (venue location) | Documented; New Haven coverage unverified |
| 5 | Arts Council / INFO New Haven | `https://events.newhavenarts.org`, `https://events.infonewhaven.com` | HTML | No | No feed found. Ask Arts Council or scrape last |

Not usable: Eventbrite (no public search API), Visit New Haven (`?ical=1` returns HTML), City of New Haven (HTML list only).

Group-level feeds exist too: `https://groups.som.yale.edu/ical/yalesom/ical_club_<id>.ics`. Get the CDO group's ID from the "Copy Link" on `https://groups.som.yale.edu/ics_helper`. Anonymous pulls only return public events.

## Implementation

### Data model
One `Event` table, one `EventSource` table:
- `source` (FK), `external_id` (unique together with source), `title`, `description`, `starts_at` (UTC, timezone-aware), `ends_at` (nullable), `location_text`, `latitude`/`longitude` (nullable), `url`, `category`, `raw` (JSONB), `last_seen_at`
- Index on `starts_at`. Geocode cache keyed by normalized `location_text`.

### Importer
Management command: `python manage.py import_events [--source yale_connect|som|localist|ticketmaster]`. Run it on a schedule (cron or job queue), never per request.

1. **Fetch** with `requests`, `allow_redirects=True`, a timeout, and a descriptive User-Agent. Send `If-None-Match` / `If-Modified-Since` when the server returns ETag or Last-Modified. The Yale feed is about 4 MB, so poll at most every 30-60 minutes.
2. **Parse ICS** with the `icalendar` package. DTSTART values are UTC (`...Z`). Skip events with `DTSTART < now`: the feed includes past events.
3. **external_id:** use the number in the event URL (`rsvp?id=2308631`), falling back to `UID`.
4. **Category:** CampusGroups puts `event_type` and `event_tags` in CATEGORIES (e.g. `Tour (event_type)`, `Career` tag). Map these to your own categories.
5. **Geocode** `location_text` when lat/lng are missing. Skip online or placeholder locations. Cache results, and rate-limit to the provider's terms. Provider is the team's decision (Google Maps API is the one in the project plan).
6. **Upsert** on `(source, external_id)`. Do not delete events that disappear. Mark them cancelled or stale based on `last_seen_at`.
7. **Dedupe across sources** on normalized title plus `starts_at` plus venue. Prefer the source with coordinates.

### Localist adapter (only if the API test passes)
Test first:
```bash
curl -s https://events.yale.edu/robots.txt
curl -s "https://events.yale.edu/api/2/events?pp=3&days=14" | head -c 1500
```
If it returns JSON and robots.txt allows it, use `GET /api/2/events?days=30&pp=100&page=N`. Per the Localist docs: `pp` max 100, response has `page` (current, size, total), and each event has `geo` (latitude, longitude, street, city), `location_name`, `event_instances`, `localist_url`. If blocked or paid, email calendar.support@yale.edu or drop this adapter.

### Ticketmaster adapter
Key goes in env var `TICKETMASTER_API_KEY` (never in the repo). Free quota is 5,000 calls/day at 5 requests/second, and results are limited to size x page < 1,000. First check venue coverage: `/discovery/v2/venues.json?city=New Haven&stateCode=CT&apikey=KEY`.

### 12-Factor and project requirements
- All keys and URLs from environment variables. Log to stdout. No local file persistence.
- Tests must mock all external calls. Save a trimmed real ICS response (and a Localist JSON sample) as fixtures under `tests/fixtures/`. Test: parsing, past-event filtering, upsert idempotency (run twice, row count unchanged), dedupe, geocode-cache hit.
- The seed command should load fixture events so staging has map data without hitting the network.
- Failure handling: one source failing must not abort the others. Log the error and keep the existing rows.

### Open items
- Terms of service for CampusGroups, Localist and Ticketmaster have not been read. Check before public launch.
- Whether SOM events also appear in the university feed is untested. Dedupe handles it either way.
- 12twenty (SOM CDO employer events), Yale Career Link and Handshake need logins and cannot be imported.
