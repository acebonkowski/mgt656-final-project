# Issue #81: profile dropdown integration

Internal implementation note. The header is implemented on `feature/81-profile-dropdown`; the live Friends count and final destination pages are pending their owning stories.

## Implemented

- Profile photo and dropdown arrow to the right of Create; placeholder for missing or failed photos.
- My Events, Friends, Settings, and Log Out in that order, with icons.
- My Events uses the existing `my_events` route; the temporary standalone link and old logout icon are removed.
- Logout uses the existing CSRF-protected POST route and returns to login.
- Keyboard activation, Tab navigation, ArrowDown into the menu, Escape with focus restoration, and dismissal on outside click or focus leaving.
- Both red badges share one count; neither is rendered at zero.

## Integration for #39 (Friends owner)

Replace the temporary body of `incoming_friend_request_count(user)` in `core/header.py` with the real query. Return a nonnegative integer counting pending requests received by this user. Exclude sent and resolved requests. No model name or schema is assumed by #81.

The header calls this once per map page render. Both badges update on the next page load; no polling is introduced.

Replace the temporary Friends view registered at `/friends/`, retaining URL name `friends`, or update the reverse call in `profile_menu_context` if the final route name differs. Avoid registering duplicate routes that leave the placeholder shadowing the real page.

Add integration tests using real request records: two pending received requests produce both badges showing 2; another user's requests and sent requests are excluded; accepting/rejecting requests reduces the count; zero hides both badges. Current mocked count tests validate presentation only.

## Integration for #83 (Settings owner)

Replace the temporary Settings view at `/settings/`, retaining URL name `settings`, or update `profile_menu_context` to use the final name. Page content is owned by #83. Avoid duplicate route registrations.

## Manual review

On `/map/`, check a user with and without a photo, open/close by mouse and keyboard, follow all links, and log out. Check narrow mobile widths and a failed photo download. Friends and Settings currently show explicit coming-soon pages.

Real request-count integration, PostgreSQL CI, and browser visual review must be reported separately from local unit tests. Do not treat the zero-count fallback or mocked badge tests as completion of #39's integration.
