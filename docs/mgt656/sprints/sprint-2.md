# Sprint 2 Report

**Due:** Wed Nov 18, 11:59pm ET

## Sprint goal
Make the map useful. Students can now create, view, share and search events. The AI search and event generation has been started. Production is now deployed alongside staging, with CI.

## What shipped
- Production deploy and server-side OpenRouter client: [#30](https://github.com/acebonkowski/mgt656-final-project/issues/30) → PR [#42](https://github.com/acebonkowski/mgt656-final-project/pull/42); MapTiler enabled for the production hostname: [#45](https://github.com/acebonkowski/mgt656-final-project/issues/45) (config only)
- CI (tests on Postgres 17) and one-click promotion to production: [#43](https://github.com/acebonkowski/mgt656-final-project/issues/43) → PR [#44](https://github.com/acebonkowski/mgt656-final-project/pull/44)
- Create an event (form over the map, image upload, geocoded location, 12 categories): [#31](https://github.com/acebonkowski/mgt656-final-project/issues/31) → PR [#46](https://github.com/acebonkowski/mgt656-final-project/pull/46), build fix PR [#54](https://github.com/acebonkowski/mgt656-final-project/pull/54)
- View event (public shareable page, share button, `.ics` calendar download): [#32](https://github.com/acebonkowski/mgt656-final-project/issues/32) → PR [#47](https://github.com/acebonkowski/mgt656-final-project/pull/47)
- Manual search (text, category, date, time, distance, "Search this area"): [#35](https://github.com/acebonkowski/mgt656-final-project/issues/35) → PR [#49](https://github.com/acebonkowski/mgt656-final-project/pull/49)
- Search panel, result cards, event dialog with previous/next: [#34](https://github.com/acebonkowski/mgt656-final-project/issues/34) → PR [#50](https://github.com/acebonkowski/mgt656-final-project/pull/50)
- AI search (chat, poster image, voice; the AI picks filters, and results always come from our database; per-user usage limits): [#36](https://github.com/acebonkowski/mgt656-final-project/issues/36) → PR [#52](https://github.com/acebonkowski/mgt656-final-project/pull/52)
- Event aggregator (Yale Connect / Yale SOM ICS feeds, deduplication, secret-protected daily import endpoint): [#33](https://github.com/acebonkowski/mgt656-final-project/issues/33) → PR [#51](https://github.com/acebonkowski/mgt656-final-project/pull/51)
- Bug fixes found on staging: create-event form never saved [#55](https://github.com/acebonkowski/mgt656-final-project/issues/55) → PR [#56](https://github.com/acebonkowski/mgt656-final-project/pull/56); form errors hidden under the map [#57](https://github.com/acebonkowski/mgt656-final-project/issues/57) → PR [#58](https://github.com/acebonkowski/mgt656-final-project/pull/58)
- Team testing of the Sprint 1 build: [#29](https://github.com/acebonkowski/mgt656-final-project/issues/29)

## What works on staging now
https://mgt656-final-project-staging.onrender.com (production: https://mgt656-final-project-y89o.onrender.com). Free plan, so the first request after idle can take about a minute.
- Log in at `/login/` with the grader accounts from our submission notes; you land on the map.
- **Create:** the + button opens the event form. Upload an image (PNG/JPEG/HEIC, max 5 MB), fill in the fields and submit; the event appears as a pin. ("Generate with AI" for the image is broken, see below.)
- **View/share:** click a pin or a result card to open the event dialog, then "View event" for the public page. It opens without login, has a share button and "Save to calendar" (`.ics`).
- **Search:** the side panel filters by text, category, date, time and distance. Filters show as chips and are kept in the URL. 
- The A/B page `/e75d81f` and `/e75d81f/stats` work as in Sprint 1.

## Working with our agents
The create-event form (#31) passed all of the agent's tests, but on staging no event ever saved. The agent's test posted the form the way a test client does, not the way the browser does: without multipart encoding, so no image arrived, and with pre-rounded coordinates, while MapTiler returns more digits than the field allows (#55). Then the error dialog opened *under* the map, and its test passed only because it looked for the word "open" anywhere in the page (#57). We gave the agent the browser console error and the staging request log, and it found both causes. What we changed: regression tests now post what the browser actually sends and assert on the specific element; rejected submits are logged by field name, so staging failures are visible; and every UI story is clicked through on staging before we close it, not only before merging.

## Backlog changes for next sprint
- **Carried over:** "Generate with AI" event images always return 502, because the image request goes to a text-only model ([#59](https://github.com/acebonkowski/mgt656-final-project/issues/59)).
- **Still to verify:** We have not tested the AI search yet. Additionally, the aggregator's live setup (cron-job.org daily job) and the initial event import through Dec 31 to populate the app are still outstanding. 
- **Added from PR follow-ups:**  Delete our own A/B test visits from production before the Sprint 4 run (from Sprint 1).
- **Spikes to turn into stories:** favorites [#38](https://github.com/acebonkowski/mgt656-final-project/issues/38), recurring saved searches [#37](https://github.com/acebonkowski/mgt656-final-project/issues/37), friends [#39](https://github.com/acebonkowski/mgt656-final-project/issues/39), privacy and visibility [#41](https://github.com/acebonkowski/mgt656-final-project/issues/41), AI safety and moderation [#40](https://github.com/acebonkowski/mgt656-final-project/issues/40).
- **Process change:** #32, #35, #34 and #36 all depended on #31's Event model, so their PRs were stacked and merged in order. In Sprint 3 we land shared models first, so stories can be built in parallel.

---
*Drafted by Claude (Anthropic), based on the direction of Ace Bonkowski.*
