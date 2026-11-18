# Issue #33 acceptance review

Scope: `feat/33-event-import-foundation`, including the #31 implementation.
Criteria: https://github.com/acebonkowski/mgt656-final-project/issues/33.
“Tested” below means automated local tests with external services mocked; it does
not mean the deployed service or external cron job has been configured.

| Acceptance criterion | Implementation / evidence |
| --- | --- |
| Missing/wrong token returns 403 | Tested; no job or lock created. Empty server configuration fails closed. |
| Valid token returns 202 promptly; background import and logs | Tested under two seconds with thread startup mocked; worker logs start, per-source progress and final counts. Deployment cold-start latency is not measured. |
| Active run prevents another run | Tested database-backed lock shared by endpoint and command; token-specific recovery and thread-start failure cleanup. |
| Already-ended events skipped | Parser skips past starts; persistence checks expiry again. |
| Exact location/date/start/end duplicates rejected | Sequential tests plus database constraint covering concurrent writes across sources and user-created events. Form races show a duplicate error. |
| Stored fields valid | Model validation, truncation, category checks and geocoded/source coordinates with New Haven locality checks. |
| Re-import does not duplicate | Runner and persistence repeat-run tests plus unique source identity. |
| Per-run image cap; remainder gets placeholder | Tested successful/failed calls, zero budget, and repeat-run behavior. Failures consume budget. |
| Source HTTP failure does not stop others | Tested failed source followed by successful import; logs omit exception text and credentials. |
| Initial population through Dec 31 | `import_events` processes all configured sources through exclusive Jan 1 cutoff, using shared runner; command idempotency tested. Deployment population is not run. |
| Expired imported event hidden on map | Integration test checks visible before end, hidden at end, retained in database. |
| README cron setup | Documents POST URL, header token, daily 18:00 America/New_York, logs and recovery; no secret values. |
| Mocked auth/dedupe/idempotency/expiry/cap tests | Covered by importer, source, enrichment, scheduler and map integration tests. |

## Validation

All 223 local tests pass. Ruff, migration consistency, and whitespace checks pass.
External services are mocked in the test suite; live ICS probes were read-only.

## Confirmed choices

The user approved null unknown prices displayed as “Price not listed” and visible
source attribution. User-created event forms still require a price and image.
Image and LLM caps default to zero; code paths are implemented and tested, but
paid calls must be explicitly enabled after a budget is approved.

## Operational validation still required

- Set deployment secrets, MapTiler key/quota, optional Ticketmaster key and
  image-capable OpenRouter model/storage before enabling those integrations.
- Apply migrations, run population, and configure the external cron-job.org job.
- Measure deployed startup/response/runtime and provider quotas. A 202 is only
  acknowledgement; monitor final logs. A killed thread requires manual lock
  recovery after confirming its worker stopped.
- Use the repository's Python 3.12 CI environment as well as local Python 3.15.
- Localist is conditional in the issue and remains excluded until access is
  verified. Ticketmaster live coverage is unverified without a key. Events with
  missing ends/unsupported recurrence are skipped; no times are fabricated.
- New Haven checking uses provider locality plus a sanity envelope, not a precise
  city polygon. The per-run deadline may require repeat runs for initial backfill;
  Ticketmaster's 1,000-result limit is counted if reached.

Read-only live ICS parsing prepared 325 Yale Connect and 60 SOM candidates before
geocoding/city filtering. No development or production event writes, paid calls,
deployment, external job creation or GitHub issue changes were performed.
