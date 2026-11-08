# Issue #7: local onboarding milestone

This branch implements the form and profile persistence. It is not the complete issue.

## Run locally

Use a local shell without a deployed `DATABASE_URL` configured:

```sh
export DJANGO_DEBUG=true
export APP_ENV=local
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_onboarding_demo
.venv/bin/python manage.py createsuperuser
.venv/bin/python manage.py runserver
```

Sign in at `/admin/login/`, then visit `/onboarding/` in the same browser.
This uses the existing Django session; there is no authentication bypass.
The demo seed command is repeatable and refuses non-local environments.
The choices are deliberately fictional, not approved Yale school/program data.

## Integration points

- Authentication owner: establish a Django user session after verification and route
  new users to the named `onboarding` URL. Configure Django's `LOGIN_URL` to the
  team's sign-in route; until then anonymous requests redirect to Django's default
  `/accounts/login/`, which this repository does not yet implement.
- Catalog: populate `School` and `Program` with approved seed data. Programs belong
  to schools. Profile school is derived from its program to avoid inconsistent data.
  No sample catalog is loaded by migrations or deployment.
- Navigation: set `ONBOARDING_SUCCESS_URL` in Django settings to the agreed route
  name or URL. It currently falls back to the existing home page.
- Photos: `photo_reference` reserves an object-storage key. Upload/edit/removal and
  storage policies are not implemented yet. Do not use the default filesystem
  storage for uploads. The bundled SVG is an original Bulldog placeholder, pending
  an approved Yale Bulldog asset.
- Validation: errors appear after field interaction and on invalid server posts.
  JavaScript disables submission until fields are valid. Without JavaScript, users
  can submit a school first to load its programs; server validation still applies.

## Verification and remaining scope

```sh
DJANGO_DEBUG=true .venv/bin/python manage.py test
DJANGO_DEBUG=true .venv/bin/python manage.py makemigrations --check --dry-run
```

Before closing #7: approve the catalog and asset, integrate verified sign-in and the
destination route, implement object-storage photos with server validation and tests,
check keyboard/mobile/iPad behavior in a browser, and verify the flow on staging.
Do not mark the full issue complete based on this milestone.
