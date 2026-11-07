# Project Brief

Build a web application in a team, the way professional teams build them: a batteries-included framework, a relational database, tests, staging and production environments, and a backlog that drives the work.

You will use AI coding agents for most of the code. That is expected. Your job is to direct them well: clear stories, careful review, and an app your team understands. The project is a modest part of your grade, and everyone on a team gets the same grade.

# Timeline
All deadlines are 11:59pm ET.

Wed Oct 28: Team selection
Mon Nov 2: Proposal
Wed Nov 11: Sprint 1: walking skeleton
Wed Nov 18: Sprint 2
Wed Dec 2: Sprint 3
Fri Dec 11: Sprint 4, then the A/B run on production
Fri Dec 18: Final submission (this page)

# Required
Your app must have all of these.

## Framework: 
Django, Rails, Laravel, Phoenix, or AdonisJS. Phoenix and AdonisJS have smaller communities, so AI agents are less reliable with them.

## Database
PostgreSQL or MySQL. Staging and production each have their own database.

## User accounts 
using your framework's standard authentication. Kyle may waive this if accounts make no sense for your app.

## An AI feature
Call the LLM through OpenRouter from your server, never from browser JavaScript. Kyle will tell you how to get an OpenRouter key with credits.

## Automated tests
Tests must not call the real LLM or other external services; mock them.

## Environments
Staging and production environments, both public.

## 12-factor basics
configuration and secrets in environment variables, never in git; the database attached by a URL in an environment variable; logs written to stdout; no uploads or other lasting data on local disk (use the database or object storage); the app listens on $PORT; schema changes made with migrations.

## Seed Command 
A seed command that creates demo data and the accounts graders use. Make it safe to run more than once, and run it after any database reset.

## Responsiveness 
A usable interface that works on phones and desktops. A CSS framework makes this easy.

## A/B Test Page
The A/B test page described below.

# Technical challenge
Beyond the required list, build things that make your app more serious. We judge depth and how impressive the work is. Aim for about three items done well: tested, working in your deployed app, and handling failure. Three solid items beat eight shallow ones. Pick from this list or propose your own.

## Delivery
CI (tests and linting on every pull request, merge blocked on failure); CD (merging to main deploys staging automatically, with a deliberate step to promote to production); a Docker Compose development setup; error tracking and a health-check endpoint.

## Backend: 
a background job queue with a separate worker process; scheduled jobs; a documented JSON API with token authentication; importing external data; roles and permissions beyond logged-in or not; full-text search; file uploads to object storage; email notifications; webhooks; social login.

## AI: 
retrieval over your own data with pgvector; structured LLM output that drives app behavior; an evaluation set run like tests; per-user AI usage limits.

## Frontend and quality: 
live updates without full page reloads (Hotwire, LiveView, Livewire, htmx); end-to-end browser tests (Playwright); accessibility checks in CI; measured performance work (indexes, fixing N+1 queries, caching).

# How you work
## Project board: 
one GitHub Project for your team, linked to your repo. Add an Iteration field with one iteration per sprint, dated to match the course deadlines. Turn on the built-in workflows that add new issues and move finished items to Done.

## Backlog: 
issues labeled user story, each with a statement ("As a ..., I want ..., so that ...") and acceptance criteria. Write the criteria precisely enough to hand to your AI agent; they are its spec. Break a story into sub-issues when it needs several pieces of work.

## Sprints: 
at the start of each sprint, put the stories you commit to in that iteration. Unfinished stories move to the next iteration; don't delete them.
## Milestones (optional)
are for product goals that span sprints, such as "MVP" or "launch", not for sprints.

## Branches and pull requests: 
work on branches. Each pull request says Closes #<issue> and is reviewed by a teammate before merging. Its description says what the agent produced and what your team changed or rejected.

No story points, velocity, or burndown charts.

## The docs/mgt656/ folder
Your repo must contain this folder. We grade what is on main at each deadline. Never put passwords or keys in the repo.

docs/mgt656/
  team.yaml        # who you are and what you built with (template below)
  technical.md       # your technical-challenge items and testing strategy
  sprints/
    sprint-1.md      # one short report per sprint
    sprint-2.md
    sprint-3.md
    sprint-4.md
    img/             # screenshots, if useful; link to videos instead of committing them
  retrospective.md   # final: what you learned

# team.yaml:

framework: django # django | rails | laravel | phoenix | adonisjs
database: postgres # postgres | mysql
members:
  - nickname: bald-chicken    # course nickname
    github: kljensen          # GitHub username
Sprint report (about half a page):

the sprint goal
what shipped, with links to closed issues and merged pull requests
what works on staging now
working with your agents: one concrete thing that worked or didn't, and what you changed
backlog changes for next sprint
technical.md: for each technical-challenge item, a line or two on what it is, the main file paths and pull requests, and how to see it working. Then your testing strategy: what you test at which level, what you mock, and what you don't test and why.

retrospective.md (about half a page): what went well, what you would do differently, and how your way of working with AI agents changed over the project.

# A/B test page
Your app must serve a public page at / followed by the first 7 characters of the SHA-1 hash of your team nickname (not a member's nickname), exactly as shown on the course site.

printf %s bright-forest | shasum      # 211c220... so the page is /211c220

Do not use echo bright-forest | shasum: it hashes a trailing newline and gives the wrong answer (1ea0cdf). Check your method on bright-forest first.

The page must:

– return 200 without logging in, with no pop-up in the way
– list your team members' nicknames
contain exactly one <button id="abtest"> whose text, ignoring surrounding whitespace, is exactly kudos or thanks (lowercase)
– give each new visitor kudos or thanks at random, 50/50, and keep showing that visitor the same one (use the session or a cookie); put the text in the HTML from the server, not with JavaScript
– count one impression per visitor, the first time they see the page (reloads and redirects do not count again)
– send a request to your server when the button is clicked (a plain <form method="post"> is simplest) and count at most one click per visitor. If the click redirects back to the page, that must not count a new impression or change the visitor's variant
– store impressions and clicks in your database, with timestamps
– Also serve /<hash>/stats, public, returning JSON with a preferred key whose value is "kudos" or "thanks": the variant with the higher click rate (clicks divided by impressions), computed live from your database. 

You may add other keys, such as your counts:

{"preferred": "kudos", "kudos": {"impressions": 212, "clicks": 63}, "thanks": {"impressions": 207, "clicks": 21}}

After Sprint 4, a bot visits your production app with a real browser (Playwright), each visit a new visitor, during an announced window of a few hours. It clicks one variant more often than the other, and that preference does not change during the run. Free hosting that sleeps when idle is fine; the bot wakes your app first. There is no practice run, so test your counting yourself. Your own test visits count too, so delete them before the run. Kyle reads preferred from your /stats page right after the run, and that value is graded.

# Hosting
Free tiers can work because the bot only runs in short windows. Suggestions: Vercel & Render

Check current limits and prices before you choose. As of October 2026, Render's free Postgres is deleted after 30 days (use Neon instead), and background worker processes usually cost a few dollars a month.

# Submitting
Every sprint and this final submission ask for your repo and staging URLs (plus production from Sprint 2 on) and notes. In the notes, tell us how to use your app: the login page, and a username and password for each kind of user. Add anything else we should know, such as a feature that is half done. Use this format:

Access:
https://bright-forest-staging.onrender.com/login
admin: admin@example.com / correct-horse-battery
member: member@example.com / staple-paper-lamp

Notes:
CSV export is half-done; skip it this sprint.
These accounts must use fake data, passwords you use nowhere else, and no two-factor or email verification. Create them in your seed command. Your sprint report goes in the repo, not in the notes.

If your app or a grader account is broken when we grade, we will tell you and you will have 24 hours to fix it.

# Grading (60 points)
20: Working app and the required items
20: Technical challenge
10: A/B test: a working A/B page and a correct preferred value after the run
10: Process and docs: backlog, pull requests, technical.md, retrospective
The four sprints are graded separately (Sprint 1: 10 points; Sprints 2–4: 15 each).

