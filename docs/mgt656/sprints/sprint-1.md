# Sprint 1 Report (walking skeleton)

**Due:** Wed Nov 11, 11:59pm ET

## Sprint goal
Ship a deployed walking skeleton of our Yale event discovery app: Django on Render with a Supabase Postgres database, Yale email login with seeded grader accounts, onboarding, a placeholder map home screen, and the required A/B test page.

## What shipped
- Django skeleton, database connection and Render deploy: [#10](https://github.com/acebonkowski/mgt656-final-project/issues/10) → PR [#22](https://github.com/acebonkowski/mgt656-final-project/pull/22)
- Home screen placeholder (dark MapTiler map of New Haven): [#8](https://github.com/acebonkowski/mgt656-final-project/issues/8) → PR [#23](https://github.com/acebonkowski/mgt656-final-project/pull/23)
- A/B test page and stats endpoint: [#9](https://github.com/acebonkowski/mgt656-final-project/issues/9) → PRs [#24](https://github.com/acebonkowski/mgt656-final-project/pull/24), [#26](https://github.com/acebonkowski/mgt656-final-project/pull/26) (real member nicknames)
- User authentication (Yale email one-time code, grader accounts, seed command): [#6](https://github.com/acebonkowski/mgt656-final-project/issues/6) → PR [#25](https://github.com/acebonkowski/mgt656-final-project/pull/25)
- Onboarding (profile, Yale school/program, profile photo): [#7](https://github.com/acebonkowski/mgt656-final-project/issues/7) → PR [#27](https://github.com/acebonkowski/mgt656-final-project/pull/27)
- Team file: [#4](https://github.com/acebonkowski/mgt656-final-project/issues/4) (`team.yaml`)

## What works on staging now
https://mgt656-final-project-staging.onrender.com (free plan, so the first request after idle can take about a minute)
- `/healthz` returns the app and database status.
- `/e75d81f` is the public A/B page: five member nicknames and one `kudos`/`thanks` button. `/e75d81f/stats` returns the live counts and `preferred`.
- `/login/`: log in as a grader with the address and code from our submission notes. The admin account opens `/admin`, and both accounts land on the map. Log out with the button on the map.
- `/onboarding/` shows the profile form for a new student, and graders can open it to edit their profile.

## Working with our agents
The map story (#8) passed all of the agent's tests, but when we opened the page in a browser the map was 0px tall: MapLibre's stylesheet overrode our container CSS. The tests only checked the HTML, so the agent could not see the layout. We asked the agent to diagnose and fix it and to add a regression test, and from then on every UI pull request needed a manual browser check before approval (Harshita checked the A/B page that way in #24, and the PR descriptions list a staging check after merge).

## Backlog changes for next sprint
- All Sprint 1 stories were finished, so none moved to Sprint 2.
- Follow-ups raised in Sprint 1 pull requests: deploy and verify production (needed from Sprint 2 on); verify a team-owned email domain in Resend so student login emails send (graders log in without email); team sign-off on the provisional Yale school/program list; a command to delete our own A/B test visits from production before the Sprint 4 bot run.
- Next: the OpenRouter AI feature and the first event discovery stories.

---
*Drafted by Claude (Anthropic), based on the direction of Ace Bonkowski.*
