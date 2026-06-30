# Failure Analysis

Validation command: `pytest`
Final baseline result: **15 passed, 1 skipped**.

## Attempt 1

| Field | Analysis |
|---|---|
| Failure | `ModuleNotFoundError: No module named 'app'` while loading `tests/conftest.py`. |
| Classification | **B — generated test/bootstrap assumption incorrect.** |
| Evidence | The pytest console entrypoint did not expose the repository root on `sys.path`; application code was not reached. |
| Resolution | Added the resolved repository root to `sys.path` in the test-only bootstrap before importing root-level `app.py`. |
| Production change | None. |

## Attempt 2

| Field | Analysis |
|---|---|
| Failure | Puzzle summary returned `corner-capture`, while the generated test expected `Corner capture`. |
| Classification | **B — generated test assumption incorrect.** |
| Evidence | Existing `_question_display_name()` intentionally derives the public name from the source basename. |
| Resolution | Changed the test expectation to the observed contract `corner-capture`. |
| Production change | None. |

## Attempt 3

Result: **15 passed, 1 skipped in 2.22s**.

The skip is intentional: successful `/api/srs/review` coverage awaits a production-faithful fixture for the high-fan-out progression/equipment/pet/monster/quest/badge/reward schema. No production behavior was classified as A and no production logic was repaired.

## SGF engine validation

After the separately requested SGF engine was added, tests were executed in dependency order and then as one complete suite.

- coord utilities: 26 passed;
- matcher: 5 passed;
- tree: 5 passed;
- override loader: 5 passed;
- auto-reply: 5 passed;
- parser invalid-structure contract: 10 passed;
- engine orchestration: 6 passed;
- final complete suite: **77 passed, 2 skipped in 2.06s**.

The second skip is the required PENDING integration gate: 0 of 10 manually verified gold SGFs are present, so no synthetic SGFs were fabricated.
