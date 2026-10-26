# G078 Lane B2 Rating PostgreSQL parity and app integration

Date: 2026-10-23 (Asia/Taipei)
Workspace: `D:\go-odyssey-g076-p0b-rating-20261023`
Branch: `g076-p0b-rating-20261023`
Verified starting HEAD: `282f4ead69a6daff59e87466f6871a7fbfd94ca6`

**PARTIAL / BLOCKED_ENVIRONMENT. Authentic PG parity and formal Flask runtime
acceptance remain NOT_EXECUTED. This is a locally tested adapter candidate,
not release admission.**

## Authority and retained evidence

Writes were confined to this worktree. No push, merge, deploy, production DDL,
production connection, existing account/corpus write or other checkout edit.
No sub-agent was used. Initial tracked tree was clean; existing untracked
`artifacts/g076-rating/` and `artifacts/g077-b2/` were retained.

G077's 63 Python PASS plus 12 subtests and Chrome/Flask/WGo 61 PASS are the
user-established historical results at the specified base. Those suites were
**not rerun**, and those numbers are not fresh G078 or PostgreSQL results.
The G077 writer and original Rating route bodies were left intact.

## Exact container gate: not satisfied

Required container name: `g076-r5-isolated-pg-20261023`.
Required label: `go-odyssey.g076.r5=isolated-disposable`.
Required image: `postgres:16-alpine`.
Actual full container ID, label, image identity, state and endpoint: **UNKNOWN**.

Both the initial filtered `docker ps -a --no-trunc` and exact-name
`docker inspect --type container ... --format '{{json .}}'` failed with Docker
API permission denied at `npipe:////./pipe/docker_engine`; Docker also reported
access denied reading `C:\Users\beatl\.docker\config.json`.
The inspect output is retained in `artifacts/g078-b2/container-inspect.txt`.
No permission escalation, alternate database, container launch, restart,
schema creation, schema deletion or PG connection was attempted.

The instruction says to add the PG backend fixture **only after** exact
container verification. Therefore no new PG fixture was added, and no
ephemeral PG schema was created. The existing SQLite fixture was used only
for explicitly bounded adapter tests. No SQLite lock result is called PG parity.

## Candidate app wiring

`app.py` installs `g078_rating_integration.install(app, globals(), os.environ)`
before its main block, and serves the existing Rating client JS through the
same static/baked helper used by other candidate clients. Installation itself
does not open a DB connection or create tables.

`RatingAppServices` uses the real late-bound app namespace:

- Canonical `_ensure_rt_pool`, `_RT_POOL`, `_pick_question`, role/anchor/version,
  recent-history, transform, convergence and rank functions. No replacement
  player/corpus provider is installed into the application.
- The blueprint obtains identity from Flask session. Authenticated accounts
  must exist in `users`; no account or prior Elo is fabricated. Secure start
  accepts only trigger, preserving the existing account-prior formula and
  anonymous 1500/400 default without accepting browser Elo/exclusion authority.
- Account row `FOR UPDATE` precedes original-session `FOR UPDATE`, serializing
  multiple sessions for the same account as well as one session's nonce writes.
  Anonymous sessions retain the original sid-capability semantics.
- One caller connection owns start/resolution, ledger, original judge/writer,
  Elo, mistakes, placement finalization, queue invalidation, unlock and receipt.
  The adapter commits once and rolls back exceptions including commit failure.
  It never calls HTTP `rt_answer`, its shadow observer or post-commit callback.
- Normal steps call original `_rt_server_verify` and `_rt_write_step_result`;
  forfeits call G077 `_rt_forfeit_on_connection`. Current private pool bytes
  are rechecked. No client verdict or fabricated move enters the writer.

The blueprint checks the optional adapter readiness hook on ON requests. This
reads the two ledger table column sets; missing schema/backend returns HOLD.
It installs no schema and is not a full constraints, corpus or PG admission test.
OFF capability short-circuits without querying the database.

Rating ON works independently of global privacy; no environment flag was set
or global privacy enabled during this work. Under ON/HOLD, the integration
blocks legacy start/answer/resume/placement_finish/claim_anon/claim_sp writes
and exposure shortcuts. Under ON only, original GET `rt_result` and
`rt_pool_info` remain available: reviewed bodies expose completed owned result
metadata and pool counts, with no SGF/solution tree. Those responses get
no-store and Vary Cookie. All original legacy endpoints remain intact under
both flags OFF. Claims are deliberately HOLD under secure ON; secure account
claim/SP lifecycle acceptance remains open.

## SQL inspection and compatibility limits

The current canonical `db.py` is psycopg2 PostgreSQL, not a MySQL adapter.
It translates `?` to `%s` and retains native `FOR UPDATE`.
Reviewed Rating session/response DDL uses TEXT/REAL/INTEGER, SERIAL and
UNIQUE(session_id, round). The G077 placement/finalization helpers use
PostgreSQL `ON CONFLICT`, not MySQL `ON DUPLICATE KEY`.
No MySQL dialect substitution or lock stripping was added to product code.
This is source inspection only: authentic PostgreSQL typing, REAL precision,
constraints, isolation, blocking and rollback are still untested here.

## Fresh verification

Command (Windows CPython 3.12.14):

```powershell
& 'C:/Users/beatl/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' -B tests/test_g078_rating_integration.py
```

**11 unittest methods PASS**, 14.046 seconds. Receipt:
`artifacts/g078-b2/adapter-tests.txt`.

These new tests invoke the actual adapter against the existing disposable
SQLite/AST seam. They cover stored-account prior/private projection, original
judge and writer on normal multistep success, unjudgeable/corpus-change denial,
missing accounts, two owners and anonymous capability, one receipt on replay,
numeric Elo/SE, commit rollback/retry, placement account/unlock rollback,
missing-schema readiness, and source registration ordering/asset presence.
The fixture uses synthetic questions/rank/selection/zone mappings explicitly;
its lock wrapper strips FOR UPDATE for SQLite. It proves neither PG row locks
nor real Flask handler execution nor full-corpus compatibility.

Four changed/new Python sources parse; `git diff --check` passes.
The last cache-header-only hook addition received syntax/source review; live
Flask hook ordering, OFF routing and secure ON with global privacy OFF remain
NOT_EXECUTED. No fake Flask implementation was used.

The available Python runtime lacks Flask, pytest and psycopg2. Apparent packages
in an older checkout resolve as incomplete namespace directories, not usable
dependencies. A workspace-target pip install of Flask/psycopg2-binary/pytest
failed with `No matching distribution found for Flask`; no package was installed.
The full app was not imported or launched (avoids unrelated startup DB effects).
Chrome-Flask-PG: **NOT_EXECUTED**, with no fresh browser claim.

## Required continuation and local commit scope

First restore supported Docker access and inspect the exact named container.
Record its actual immutable full ID, required label, image and endpoint before
adding any PG fixture or executing DDL. Use a newly generated separate schema
only, containing synthetic accounts/questions; never reuse existing users or
corpus. Restrict search_path to that schema and bind all cleanup to its exact
name and container ID.

Then exercise real `db.PostgresConnectionWrapper` and this adapter against that
schema: concurrent identical nonce and changed-body races, different nonce on
one session, same account across sessions, independent users, original Elo/SE,
normal/late/partial/timeout/give_up paths, placement/queue/unlock and response
rollback, and commit failure. Demonstrate actual backend blocking/lock behavior,
not only SQL text. Run genuine Flask OFF and secure ON/global privacy OFF
through the actual install hooks and session identity, then Chrome/WGo against
that newly identified Flask-PG server. Full application startup and unrelated
shared-route effects need independent integration acceptance.

Only the adapter candidate, its app/blueprint wiring, new adapter tests and
this handoff are intended for the local commit. Artifacts, dependencies,
historical G077 evidence and browser profiles must not be staged wholesale.
Source SHA-256 receipt: `artifacts/g078-b2/source-receipt.json`.
Any local commit is a bounded candidate checkpoint with the above unresolved
gates, not an assertion that the requested PG/formal integration task passed.

### Actual commit outcome

**NOT_COMMITTED / NOT_STAGED.** The explicit-file `git add` failed before
staging with permission denied creating
`D:/go-website/.git/worktrees/go-odyssey-g076-p0b-rating-20261023/index.lock`.
This checkout's `.git` points outside the sole writable root. No permission
escalation, alternate git directory or other-checkout write was attempted.
The commit command did not execute. HEAD remains the verified base above.
The five candidate files remain reviewable in this worktree; the source
receipt binds their final bytes. Completing the requested local commit needs
supported access to the existing worktree git metadata.
