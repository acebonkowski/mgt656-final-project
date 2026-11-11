# CLAUDE.md

MGT656 (Software Management) final project, built by a team of 5. The repo owner is @acebonkowski, and only they can approve PRs into `main`.

## Source of truth
@.documentation/project-brief.md holds the project brief and grading criteria. It is **always the truth**.
- Never implement anything that breaks a requirement in the brief.
- If an issue, PR or instruction conflicts with the brief, stop and point out the conflict. Don't pick one side on your own.
- Re-read the brief before planning any feature.

## Tech stack (locked, don't change without team agreement)
- **Framework:** Django (Python). Use Django's built-in auth, ORM, migrations and admin.
- **Database:** PostgreSQL hosted on Supabase (approved by the professor). Use it as plain Postgres via `DATABASE_URL`, with no Supabase Auth or Supabase client SDK. Staging and production use **separate** databases.
- **LLM:** OpenRouter, called server-side only, and always mocked in tests.

## Issues = user stories
An issue needs these sections before implementation. If one is missing, ask for it before coding.

```
## User story
As a <role>, I want <capability>, so that <benefit>.

## Technical approach
- <stack, constraints, how it should be built>

## Acceptance criteria
- [ ] **Given** <context>, **when** <action>, **then** <outcome>

## Tasks
- [ ] <concrete piece of work>
```
- Split a story into sub-issues when it needs several pieces of work.
- Acceptance criteria are the agent's spec. They must be precise and testable.
- No story points, velocity or burndown charts (the brief forbids them).

## Git workflow
- **Never commit to `main`.** Always create a new branch first: `<type>/<issue#>-<short-slug>`, e.g. `feat/12-user-login`. Types: `feat`, `fix`, `docs`, `chore`, `test`.
- Keep commits small, with imperative messages that reference the issue (`Add login form (#12)`).
- Each PR covers one issue. Every PR description must use this structure:

```
## Summary
<what changed and why, 1–3 sentences>
Closes #<issue>

## Changes
- ...

## Agent output vs. team changes
- Agent produced: <what the AI agent generated>
- Team changed / rejected: <what we edited, rewrote or threw out, and why>

## Acceptance criteria
- [x] <copied from the issue, each one checked and verified>

## Brief compliance
<which brief requirements / grading criteria this touches; confirm none are violated>

## Testing
<how it was tested: commands run, results, screenshots for UI>

## Notes / risks
<follow-ups, open questions, or "none">
```

## Required docs (`docs/mgt656/`, graded from `main` at each deadline)
- `team.yaml`, `technical.md`, `sprints/sprint-1..4.md`, `retrospective.md`. Fill in the templates; don't rename the files.
- Never put passwords, keys or secrets in the repo.

## Agents (placeholder, to be defined)
Tier models by how much judgment the task needs:

| Agent  | Purpose                                         | Model  |
|--------|-------------------------------------------------|--------|
| design | Architecture, UX, breaking issues into tasks    | Opus   |
| build  | Implementing well-specified issues              | Sonnet |
| test   | Writing and running automated tests, reporting  | Haiku (Sonnet for writing complex tests) |

# TODO: add agent definitions in `.claude/agents/`, the test command, the build command and the CI setup.
