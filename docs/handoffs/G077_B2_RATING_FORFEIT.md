# G077 Lane B / B2 Rating forfeit authority

Date: 2026-10-23 (Asia/Taipei)
Workspace: `D:\go-odyssey-g076-p0b-rating-20261023`
Branch: `g076-p0b-rating-20261023`
Required and observed base HEAD: `6214f7b5f4f69c979da44d4ea989d3b03b6863f6`
Status: **CORE_VERIFIED / INTEGRATION_HOLD / NOT_COMMITTED**

## Authority and boundary

User authorized sole-writer B2 work in this worktree, including narrowly needed
original `app.py` additions. No sub-agents, GitHub operation, push, merge, Oracle
operation, deploy, production connection or production data access occurred.
Initial tracked tree was clean; `artifacts/g076-rating/` was already untracked.
Historical artifacts were left intact. No global privacy flag was enabled.
The user's prior 52 Python PASS and Chrome verification are historical input,
not fresh results for these modified bytes.

## Implemented candidate

`g076_rating_steps.py` enables steps with **G076_RATING_STEPS_ENABLED=on only**.
Global privacy can remain unset/off. Unknown Rating or privacy flag values HOLD;
privacy ON with Rating OFF remains HOLD; both OFF preserve legacy capability.
The blueprint still holds when no trusted service is supplied.

`advance` retains owner/current-context binding, exact nonce/body replay,
server clock/deadline checks and stored move history. Empty timeout, partial
sequence timeout, give-up and a move at/after deadline use `settle_forfeit`.
A late move is validated structurally but never appended or sent to the judge.
The ledger records the trusted timeout/give_up reason atomically with its
terminal state and receipt. An absent forfeit adapter still returns 503 HOLD.

Three private, undecorated app helpers were added:

- `_rt_forfeit_on_connection`: accepts trusted server context and reason only;
  rechecks current pool bytes, validates reason/time bounds and calls the writer
  with `correct=False`. It does not pretend that empty moves passed the judge.
- `_rt_write_step_result`: retains original `rating_test_sessions FOR UPDATE`,
  owner/token/round checks, `_rt_estimate`, streak, selection, responses,
  mistake log and `_finalize_placement` effects. It never commits or opens a
  connection and returns a payload to the caller's existing transaction.
- `_rt_step_placement_unlock`: same travel unlock upsert, placement source and
  1570 cap as original placement completion, on the caller connection. Unlock,
  Elo/session writes, ledger state and replay receipt roll back together.

Every pre-existing app function, including `rt_answer`, `_rt_server_verify`,
`_finalize_placement`, claims and OFF routes, is AST-identical to the specified
base. The original normal judge and its policy/unsupported outcomes were not
relaxed. The new writer's effects from question-role handling through finalizing
placement are AST-identical to the original writer. This deliberate bounded
copy preserves the OFF body; its parity test detects future divergence.

**This does not install an app runtime adapter or register new app routes.**
The disposable fixture binds its `settle_forfeit` to the actual extracted app
helper, using the already owned connection. The master/runtime adapter must
make the equivalent binding only after original-session resolution/locking:

```python
def settle_forfeit(self, conn, ctx, moves, response_ms, reason):
    return _rt_forfeit_on_connection(conn, ctx, moves, response_ms, reason)
```

Do not register this helper as an HTTP endpoint, accept client correctness or
reason as a verdict, call `rt_answer` for an empty sequence, or use the original
post-commit unlock callback inside the ledger transaction. Existing integration
requirements for guarding direct legacy Rating routes/exposure remain open.

## Fresh verification

| Check | Result and actual scope |
| --- | --- |
| Windows CPython 3.12.14 stdlib tests | **11 PASS**, final run 18.677 seconds |
| Node client runner | **24 PASS**, client VM/syntax contracts only |
| Modified Chrome runner syntax | PASS (`node --check`) |
| Python parsing and diff whitespace | PASS |
| Updated Rating pytest suite | **NOT_EXECUTED**, pytest unavailable |
| Flask fixture server | **NOT_STARTED**, Flask unavailable |
| Chrome against current page + Flask | **NOT_EXECUTED**, no identified fresh Flask backend |
| Atomic PostgreSQL application tests | **NOT_EXECUTED**, psycopg2 unavailable; no database launched/contacted |
| Exact app registration / production / release admission | **NOT_EVALUATED** |

The 11 unittest methods execute the actual ledger and extracted app helpers on
fresh disposable SQLite databases. They cover all four forfeits for both users
7 and 8; original numeric Elo/SE; full wrong-answer versus forfeit session
parity for manual/placement; one settlement on sequential and six-way concurrent
replay; changed-body replay conflict; cross-account denial; forged token/owner;
changed corpus; early timeout; missing adapter; unknown flags/policy; unchanged
normal multistep success; full snapshot rollback after effects and at commit;
original placement account update, queue invalidation and unlock SQL. Fixture
selection/rank/zone mappings remain synthetic. SQLite BEGIN IMMEDIATE is not
PostgreSQL row-lock/concurrency evidence. HTTP handlers were not invoked by the
stdlib tests, and no fake Flask or pytest implementation was used.

The Chrome runner now authors desktop/mobile, two-account checks for all four
forfeits, lost-response replay, one original Elo response, no forged/late stone
and board-only next question. These added browser cases have syntax validation
only. They require live execution before claiming browser PASS.

Initial stdlib attempt hit Windows SQLite file locks during test cleanup.
The fixture connection context now closes connections after commit/rollback;
subsequent complete 11-test execution passed. Earlier tool errors and historical
Chrome failures are not counted as PASS.

## Reproduction and environment blockers

Working Windows runtime discovered during this attempt:

```powershell
$py = 'C:\Users\beatl\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $py -B tests/test_g077_rating_forfeit_writer.py
node tests/e2e/g076_rating_client.mjs
node --check tests/e2e/g076_rating_chrome.mjs
```

The original Python312 executable under AppData/Local/Programs reports access
denied. The working primary runtime lacks Flask, pytest and psycopg2. A second
working Python 3.13 (Blender) also lacks those packages. A workspace-target pip
install attempt failed with WinError 10013/network denial; no alternate network
path or permission escalation was attempted. A text question requesting an
available runtime/dependency location is pending. Native PostgreSQL 17.10
`initdb --version` works, but that alone proves no application transaction.

After dependencies are available, execute from this exact worktree:

```powershell
& $py -B -m pytest -q tests/test_g076_rating_steps.py tests/test_g077_rating_forfeit_writer.py --basetemp=artifacts/g077-b2/pytest-tmp --junitxml=artifacts/g077-b2/pytest.xml
& $py -B tests/e2e/g076_rating_fixture_server.py
# In a separate terminal, only against that newly identified disposable server:
node tests/e2e/g076_rating_chrome.mjs
```

Then validate the same app helpers/ledger on a fresh isolated PostgreSQL fixture,
including original-session row locks, same/different nonce races, placement
unlock and commit rollback. No claim of executable PG coverage is made here.

## Files, receipts and commit gate

Changed source: `app.py`, `g076_rating_steps.py`,
`tests/g076_rating_fixture.py`, `tests/test_g076_rating_steps.py`,
`tests/test_g077_rating_forfeit_writer.py`,
`tests/e2e/g076_rating_fixture_server.py`, `tests/e2e/g076_rating_chrome.mjs`.
This file is the requested handoff. No other product files were edited.

Final core output: `artifacts/g077-b2/core-tests-verified.txt`.
Candidate SHA-256 bindings: `artifacts/g077-b2/source-receipt.json`.
Artifacts/dependencies/profiles must not be staged wholesale.

No commit was made: required Flask/Chrome behavior is not verified for this
candidate, so the user's verified-files-only commit gate remains unsatisfied.
HEAD remains the authorized base; the source candidate is reviewable in the
working tree. Core Elo parity is demonstrated in the bounded synthetic fixture;
full corpus/PG/runtime parity and browser acceptance remain HOLD. Do not report
this candidate as release-ready or use these tests as production admission.
