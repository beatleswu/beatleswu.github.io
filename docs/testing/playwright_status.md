# Playwright Status

Status: **Tests generated; execution intentionally not required.**

## Generated coverage

- Login through the real browser form and authenticated `/api/auth/me`.
- Puzzle summary and detail loading with one unlocked question.
- Registration form generation behind an explicit mutation opt-in.
- Answer-submission scenario documented as skipped pending a curated disposable account and known SGF branch.

## Required services

- A separately started application stack reachable over HTTP(S).
- PostgreSQL with the current schema.
- The question dataset and static assets used by the target environment.
- For full UI puzzle execution: WGo scripts/assets.
- Depending on target configuration: Turnstile and mail provider availability.

No web server, Docker service, database or browser was created by this mission.

## Required environment variables

| Variable | Required | Purpose |
|---|---|---|
| `E2E_BASE_URL` | Yes | Base URL of an already-running disposable/test environment. |
| `E2E_USERNAME` | For login/puzzle | Dedicated existing test user. |
| `E2E_PASSWORD` | For login/puzzle | Password for the dedicated test user. |
| `E2E_ALLOW_REGISTRATION=1` | Only registration | Explicitly permits a test that creates an account. |

Target service credentials such as `DATABASE_URL`, `SECRET_KEY`, Turnstile and mail keys belong to the separately operated environment, not the Playwright runner.

## Execution blockers

- No disposable running service was authorized or provisioned.
- No dedicated E2E credentials were provided.
- Registration can be blocked by Turnstile and triggers account/email side effects.
- Puzzle answer execution changes persistent progression/reward state.
- WGo board coordinates require a curated known puzzle and viewport-stable board geometry.
- The frontend is browser-global and service-worker caching may affect repeated runs.

## Suggested future command

After installing `@playwright/test` in a dedicated test environment:

```text
npx playwright test
```

This command was not executed during the baseline mission.

