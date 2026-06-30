# Testability Report

## Startup/database-first findings

### Bare application import

**Partially Testable.** Importing `app.py`:

- constructs Flask, CORS, Socket.IO, and registers the Blueprint;
- does not call `init_db()`;
- does not start Socket.IO;
- does not load `questions.json`;
- does not start the weekly scheduler;
- may create `secret_key.txt` if `SECRET_KEY` is absent;
- chooses gevent Socket.IO mode if gevent is importable and no mode is forced.

Test bootstrap must set `SECRET_KEY`, `SOCKETIO_ASYNC_MODE=threading`, `PREMIUM_WEEKLY_SCHEDULER_ENABLED=0`, and empty external-service secrets before import.

### Production entrypoints

**Not suitable for isolated tests.**

- `wsgi.py` performs gevent and psycopg monkey patching, initializes PostgreSQL schema, and preloads the question dataset.
- `scheduler.py` initializes PostgreSQL and starts a perpetual scheduler thread.
- `app.py` under `__main__` initializes DB, starts the scheduler and runs Socket.IO.

Tests must import `app`, never `wsgi` or `scheduler`.

### Database isolation decision

**Partially Testable with an adapter.** Production SQL is PostgreSQL-oriented but many narrow auth/question validation paths can use SQLite in memory. The test fixture will:

- create one in-memory SQLite connection per test;
- use `sqlite3.Row`;
- provide a non-closing context wrapper;
- monkeypatch `app.get_db`;
- create only the minimal tables needed by Tier 1 tests;
- never call `app.init_db()`.

The SQLite baseline is not proof of PostgreSQL SQL compatibility. Full review-success testing is deferred because `/api/srs/review` touches a broad PostgreSQL schema and many helper systems.

## Question dataset rule

### Loaders and caches identified

- **Verified** — `app._load_questions()`: `questions.json`, global `_questions_cache`, `_questions_mtime`, mtime reload, taxonomy mutation, DB `question_overrides`.
- **Verified** — `app._invalidate_questions_cache()`: clears the main cache.
- **Verified** — `grimoire_api.load_questions()`: separate question access path.
- **Verified** — `app._build_rt_pool()` / `_ensure_rt_pool()`: rating-test question pool.
- **Verified** — `app._load_rt_verified()` and `_load_rt_anchor_bank()`: rating JSON sources.
- **Verified** — `explain_overrides.load_overrides()`: independent mtime cache.

Tier 1 tests will monkeypatch both application question access points with a tiny in-memory fixture. They will not read `questions.json` or any production SGF dataset.

## Feature assessment

| Feature | Rating | Evidence / blocker |
|---|---|---|
| Authentication | **Testable** for email/password register/login/logout | Flask test client plus minimal SQLite tables. Turnstile, Resend and Google are external; mail/thread functions must be patched. |
| Puzzle load | **Testable** | Monkeypatch `_load_questions()`; session client requests summary/detail endpoints without loading production data. |
| Answer submission | **Partially Testable** | Request validation/auth guard is narrow. Successful review fans out across SRS, progression, equipment, pet, monster, quest, badge and reward tables. The server trusts a grade rather than validating a move. |
| Equipment | **Partially Testable** | Pure definitions/helpers are testable; API flows need many inventory/appearance/effect tables and authenticated state. Not Tier 1. |
| Leaderboard | **Partially Testable** | Query/output could use fixtures, but production ordering/data volume and cross-table state require a broader DB harness. Not Tier 1. |
| Arena | **Partially Testable** | Board helpers can be unit tested; Socket.IO events depend on process-global lobby/game dictionaries, timers, sessions and DB persistence. |
| Admin tools | **Partially Testable** | Auth guards and narrow validators are testable; mutation tools touch production-style schema, `questions.json`, external payment/report data, or large datasets. |
| Rating test | **Partially Testable** | Parser/replay/math helpers are unit-testable; pool/session flows need curated datasets and DB schema. |
| Payments | **Not Testable end-to-end locally** | Missing provider credentials, callbacks and external sandbox state. |
| AI/KataGo/GNU Go | **Not Testable end-to-end in baseline** | Optional binaries/models/cache and external APIs are unavailable/not authorized for this mission. |

## Blockers

- Missing production PostgreSQL service for isolated local tests.
- Missing Turnstile, Resend, Google, OpenAI, NewebPay and PayPal credentials.
- Optional GNU Go/KataGo executable/model/cache requirements.
- Browser-global frontend with extensive DOM/WGo/Socket.IO coupling.
- Production question dataset is too large for unit-test loading.
- Successful `/api/srs/review` has high schema and helper fan-out.

## Planned Tier 1 boundary

- Login: valid, invalid, and session behavior using isolated SQLite.
- Registration: valid, duplicate, and validation behavior with email/notifications patched.
- Puzzle load: authenticated summary/detail with a lightweight in-memory question.
- Answer submission: authentication and payload validation regression tests. A success-path placeholder will be explicitly skipped until a production-faithful review fixture exists.

This applies the “maximum three repair attempts” rule. If import or isolation fails three times, tests will remain placeholders and the blocker will be recorded rather than changing production logic.
