# Git Diff Summary

Scope of this report is limited to added test assets, configurations and fixtures, as required by Phase 4.

## Added tests

- `tests/test_authentication.py`
  - login success/failure/validation;
  - logout;
  - registration success, duplicate and invalid payload.
- `tests/test_puzzle_core.py`
  - puzzle authentication, list, detail and missing-id behavior;
  - answer submission authentication and payload validation;
  - one explicit pending successful-review placeholder.
- `tests/js/browser_globals.test.js`
  - skipped Jest contract scaffold for browser-global scripts.
- `tests/e2e/critical_flows.spec.ts`
  - generated Playwright login, registration and puzzle-load flows;
  - skipped deterministic answer scenario.
- `tests/sgf_engine/test_coord_utils.py`
- `tests/sgf_engine/test_matcher.py`
- `tests/sgf_engine/test_tree.py`
- `tests/sgf_engine/test_override_loader.py`
- `tests/sgf_engine/test_autoreply.py`
- `tests/sgf_engine/test_parser_errors.py`
- `tests/sgf_engine/test_engine.py`
- `tests/sgf_engine/test_integration_fixtures.py`
  - dependency-ordered SGF unit coverage;
  - integration remains PENDING without 10 manually verified real fixtures.

## Added configurations

- `pytest.ini`
- `requirements-test.txt`
- `jest.config.cjs`
- `tests/js/package.json`
- `playwright.config.ts`

## Added fixtures/bootstrap

- `tests/conftest.py`
  - Flask test client;
  - in-memory SQLite auth schema;
  - isolated DB adapter;
  - gevent avoidance through direct `app.py` import and forced threading;
  - disabled scheduler/external secrets;
  - lightweight in-memory question data;
  - seeded/authenticated user fixtures.
- `tests/js/setup.js`
  - minimal browser API stubs for future Jest execution.
- `puzzle_variation_overrides.json`
  - empty exception-layer data file; no inferred override entries.
- `sgf_engine/data/fixtures/`
  - required empty directory; no synthetic SGF fixtures.

No protected production file was modified.
