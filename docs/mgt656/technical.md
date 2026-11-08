# Technical Challenge & Testing Strategy

<!-- Aim for ~3 items done well: tested, working in the deployed app, handling failure. -->

## Technical-challenge items

### 1. <Item name>
- **What it is:** <one or two lines>
- **Main files:** `<path>`, `<path>`
- **Pull requests:** #<n>, #<n>
- **How to see it working:** <URL / steps on staging or production>
- **Failure handling:** <what happens when it fails>

### 2. <Item name>
- **What it is:**
- **Main files:**
- **Pull requests:**
- **How to see it working:**
- **Failure handling:**

### 3. <Item name>
- **What it is:**
- **Main files:**
- **Pull requests:**
- **How to see it working:**
- **Failure handling:**

## Testing strategy

### What we test at which level
| Level | What we test | Tools | Location |
|-------|--------------|-------|----------|
| Unit | <models, services, LLM output parsing> | <pytest / Django test> | `<path>` |
| Integration | <views, DB queries, A/B counting> | | `<path>` |
| End-to-end | <key user journeys, if any> | <Playwright?> | `<path>` |

### What we mock
- **LLM (OpenRouter):** <how it is mocked; tests never call the real LLM>
- **Other external services:** <list + how>

### What we don't test, and why
- <item>: <reason>

## How to run the tests
```
DJANGO_DEBUG=true .venv/bin/python manage.py test
```
