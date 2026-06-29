# Test Execution Blockers

## Jest

Status: **Scaffolding generated; execution intentionally not prioritized.**

Observed blockers:

- Production scripts are classic browser-global scripts, not ESM or CommonJS.
- Script load order supplies `window.I18n`, `WGo`, `SFX`, Socket.IO `io`, page-specific `onLangChange`, and shared navigation globals.
- Core puzzle logic is inline in `index.html`, not exported from a module.
- DOM IDs and inline event handlers are page-specific.
- WGo, canvas, audio, service-worker, PWA and Socket.IO APIs require purpose-built stubs.
- The repository root already contains user-owned untracked `package.json`/`package-lock.json`; this mission ignores them. Jest dependencies are therefore declared only in `tests/js/package.json`.

The scaffold uses `describe.skip`/`test.todo` and does not attempt production-code conversion. A future execution task can install dependencies under `tests/js` and progressively provide browser contracts without rewriting production logic.

## Pytest

The isolated baseline does not import `wsgi.py`, start gevent/Socket.IO, contact PostgreSQL, or load `questions.json`. The successful `/api/srs/review` path remains a documented pending test because it requires a production-faithful schema spanning progression, equipment, pets, monsters, quests, badges and rewards.

## Playwright

See `playwright_status.md` after Priority 3 generation.

