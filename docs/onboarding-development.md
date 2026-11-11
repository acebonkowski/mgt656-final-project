# Issue #7: onboarding integration

The branch integrates the issue #6 authentication branch with onboarding, the map
(#8), the public A/B page (#9), and the database/deployment foundation (#10).
Issue #18 is review automation and has no runtime dependency on onboarding.
The full issue is not ready to close until the release checks below are completed.

## Local setup

Use a local shell without a deployed `DATABASE_URL` configured:

```sh
export DJANGO_DEBUG=true
export APP_ENV=local
.venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed
.venv/bin/python manage.py runserver
```

Open `/login/`. In local debug mode, ordinary Yale addresses receive a code through
Django's console email backend when Resend is not configured. No real email is
sent in that mode. Never use the console backend on deployed environments.
Seeded grader addresses use `GRADER_FIXED_OTP`, supplied separately in the environment.
Do not commit this value. Both graders have complete profiles and go to `/map/`.
A new student goes to `/onboarding/`; saving valid fields completes their profile.
Future logins go to the map. The onboarding page remains available for profile edits.

## Shared profile and migrations

`accounts.Profile` is the only live profile model. Its fields can initially be
empty because OTP registration creates a user before onboarding. The onboarding
form requires a trimmed display name and a valid school/program pair before
setting `onboarding_complete=True`. School is derived from the selected program.
Photo changes do not mark an incomplete profile complete.

The migrations copy existing `core.Profile` data to `accounts.Profile`, then
remove the old model from Django's migration state. The old `core_profile` table
is intentionally retained as a recovery snapshot; it is not written by the app.
Do not manually drop it. Historical migrations are unchanged. Data preservation
was checked against an isolated database containing an earlier onboarding profile.

## Yale catalog and seeds

`core/yale_catalog.py` contains provisional school/degree choices from the
[2026–27 Yale catalog](https://catalog.yale.edu/ycps/work-of-yale-university/),
reviewed November 10, 2026. This is a degree-level list, not a comprehensive list
of tracks or specializations. It includes the 14 graduate/professional schools
and excludes undergraduate Yale College. Degrees awarded by GSAS but listed
under another school remain selectable under that school as an affiliation.
Certificates and joint degrees appear where the source lists them.

The team still needs to approve this interpretation and the final names. Edit
this data file and rerun `seed` for additions. Renaming existing choices should
use a reviewed data migration so existing selections retain their identity.

`manage.py seed` works in local, staging and production, is repeatable, and creates
Yale choices plus the two grader accounts with usable profile fields. It preserves
existing grader names and programs. Previously created fictional sample schools
are hidden, not deleted. The older local `seed_onboarding_demo` command now loads
the same Yale catalog; prefer the shared `seed` command.

## Photo behavior

- Add a picture uploads immediately; Edit picture replaces it with a new upload.
  This version does not provide a crop editor.
- The browser and server enforce JPEG/PNG and a maximum of 5 MiB (5,242,880 bytes,
  displayed as 5 MB). Exactly the limit is accepted. The server checks decoded
  image data with Pillow, rejects corrupt files and images over 25 million pixels,
  strips metadata, and resizes to fit within 1024 by 1024 pixels.
- Multipart files are bounded in memory; no temporary or lasting upload is written
  to the server filesystem. The current photo remains unchanged if an upload fails.
- A private Supabase Storage bucket holds the image. Django authenticates requests
  and proxies only the signed-in user's active image; the service-role key and
  object identifiers are not accepted from the browser or returned to it.
- Each upload uses a unique object key. Delete picture detaches it and restores
  the bundled Bulldog. Replaced/removed objects are retained in private storage,
  with recoverable references in `core.ProfilePhoto`. No permanent object-deletion
  API is called. Failed uploads also retain a history record in case the provider
  accepted the object before the connection failed. Retention/cleanup needs a
  separately approved policy; do not promise permanent erasure.
- The bundled Bulldog SVG remains an original placeholder pending the team's
  approved image. No Supabase client SDK or Supabase Auth is used.

## Configure staging and production storage

The repository does not contain the team's live storage credentials. Configure
these separately on each Render service, using that environment's Supabase project:

- `SUPABASE_STORAGE_URL`: project base URL, e.g. `https://<ref>.supabase.co`.
- `SUPABASE_STORAGE_KEY`: legacy `service_role` key; server-only.
- `SUPABASE_PHOTO_BUCKET`: defaults to `profile-photos`.

Then run, once per environment, with its own configuration:

```sh
python manage.py setup_photo_storage
```

The command creates the bucket only if it is missing and verifies that it is
private, limited to 5 MiB and restricted to `image/jpeg` and `image/png`. It refuses
to silently change an existing bucket with incompatible settings. It does not run
on startup and was not executed against any live project in this session.

Access rules: leave anonymous/authenticated direct object access denied. Do not add
public-read or public-write RLS policies for this bucket. Review any existing
project-wide storage policies to ensure they do not grant access. The server's
service-role key bypasses RLS, so Django enforces ownership; browser clients never
receive the key. Review [Supabase access control documentation](https://supabase.com/docs/guides/storage/security/access-control).

Without configured storage, photo attempts show a recoverable error and students
can still complete the required profile fields. Live photo acceptance criteria
remain unmet until the environment is configured and tested.

## Verification

```sh
DJANGO_DEBUG=true DATABASE_URL=sqlite:///:memory: .venv/bin/python manage.py test
DJANGO_DEBUG=true DATABASE_URL=sqlite:///:memory: .venv/bin/python manage.py makemigrations --check --dry-run
```

Tests cover shared-profile registration and repeat login, required fields and
school/program validation, grader seeding, public A/B access, photo ownership and
CSRF, upload limits, recoverable replacement/removal, and storage failure handling.
External services are mocked. Image-decoding tests require Pillow; a skipped result
is not evidence that image validation works. Install requirements before release.

## Release checks still required

- Install Pillow and run all tests with no image-validation skips. Local installation
  was declined during this session, so actual decoding tests could not run.
- Browser-check empty/valid/error states, dependent dropdowns, photo upload/edit/
  delete, keyboard access and narrow/mobile/iPad layouts. Browser access was not
  available/approved during this session.
- Approve the Yale catalog scope and default Bulldog asset.
- Configure and verify the separate storage buckets and access rules.
- On staging, verify real Yale email login, onboarding, photos, logout and returning
  login, both grader roles, and the public A/B page and stats.
- Obtain teammate review; the repository owner approves merging to `main`.

Do not close #7 or claim staging verification based only on local tests.
