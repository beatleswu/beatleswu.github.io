# Task Book: E9 Phase 1 — Allowlist Foundation (C-level)

Status: DRAFT — pending owner approval before dispatch to Codex
Author: Claude (per 2026-07-02 process rule: C-level task books are drafted by Claude)
Date: 2026-07-22
Executor: Codex
Terminal state: **Draft PR only.** Codex does not merge, does not deploy, does not
change any Production environment variable or rollout scope. Merge audit is
performed by Claude; merge and deployment are separate owner-gated operations
per ADR-0001. This task book covers **Phase 1** of the frozen v1.0 Roadmap
(`Go Odyssey E9 收尾 → E10 美術 → SGF Engine V1 → School Channel → Public
Release`) only — it does not authorize Phase 2 (Production Allowlist
Enablement), which is a separate, later owner gate.

---

## 1. Objective

Make it possible to safely move E9 from `admin_only` to a small `named_allowlist`
rollout, with zero change to Production behavior in this task. Three parts,
all required — none is sufficient alone:

1. **Runtime hardening** — close the confirmed infinite-spinner gap in
   `js/e9/component_loader.js`.
2. **Canonical user-ID allowlist correction** — correct the identity model
   the existing `named_allowlist` decision logic in `app.py` uses, and
   verify the rest of that already-working logic.
3. **Deployment governance tooling** — extend `scripts/release/set-e9-rollout.ps1`
   to safely enable `named_allowlist`, inspect its status, and — on failure —
   restore the prior rollout state, with the same safety rigor already proven
   for `enable-admin-only`. This task adds one new operation
   (`enable-allowlist`); it does not add a separate "disable-allowlist"
   operation — the existing `disable` operation (full rollout kill switch)
   and `rollback` (restore prior state) already cover stepping back from an
   allowlist rollout.

This task book **does not** cover Phase 2 (the actual Production cutover),
Phase 3 (observation), or anything in E10/SGF Engine/Corpus Audit. Do not
pull work from those phases in here.

## 2. WI-0: Verified Baseline (2026-07-22 — verify, do not redo)

Preflight (mandatory, before any code change): `git fetch origin`; create a
fresh worktree with a feature branch cut from the latest `origin/master`
(current tip at drafting time: `c0b45c4c8`, PR #205 merged); record the
starting full SHA, branch name, and `git status` in the completion report.
File:line references below are **hints from 2026-07-22, not contracts** —
locate by symbol/content, not by line number, if the codebase has moved on.

### 2.1 Confirmed gap: `js/e9/component_loader.js` has no timeout

Reproduced directly this session against a real running instance (not a
fixture): a `fetch()` that never resolves leaves the slot's loading skeleton
(`data-e9-skeleton`) showing indefinitely — `data-e9-loaded` never gets set to
either `'1'` or `'error'`. The rest of the shell (other slots, `activeShell`)
is unaffected; this is an isolated, not a whole-app, hang. Root cause:
`loadComponent()` (`js/e9/component_loader.js:53-113`) calls
`fetch(versionedUrl(url), {credentials:'same-origin'})` with no
`AbortController`/`signal` and no timer anywhere in the file.

Existing, working patterns to reuse (do not replace):
- `current()` closure (`:65-68`) checks `global.E9.isLifecycleCurrent(generation)`
  — already correctly suppresses stale `.then()`/`.catch()` work after a
  destroy. This is proven correct by `tests/e2e/run_e9_acceptance_journey.mjs`'s
  stale-callback scenario (verified passing against the real app this
  session). Do not duplicate this mechanism; the timeout addition must compose
  with it, not replace it.
- The idempotency guard (`:58-61`): `data-e9-loaded === '1' || 'error'` skips
  re-fetch. Preserve this exactly.
- `fallbackHtml()` (`:35-39`) and the existing `.catch()` fallback-render path
  (`:102-111`). Reuse verbatim for the timeout case — a timeout must produce
  the identical fallback UI as an HTTP error or network failure, not a fourth
  visual state.
- `js/e9/shell.js`'s `on()`/`registerCleanup()`/`lifecycleCleanups` mechanism
  (`js/e9/shell.js:63-80`, `:82-96`) — the existing, already-tested pattern
  that runs cleanup closures in reverse on `destroyLifecycle()`. **Use this
  same mechanism for the new abort-on-destroy behavior** (see WI-1) instead of
  adding a second, parallel cleanup path in `shell.js`. No `shell.js` changes
  should be required if this is done correctly — `component_loader.js` calling
  `global.E9.registerCleanup(...)` is enough.

### 2.2 Confirmed: most of the allowlist decision logic already exists

`app.py`'s `_e9_rollout_config()` (`:180-207`) and `_e9_rollout_decision()`
(`:209-231`) **already implement `named_allowlist` as a first-class scope**:

- `E9_ROLLOUT_SCOPE` accepts `admin_only` or `named_allowlist` only; anything
  else fails closed (`config = None` → `reason: 'invalid_config'`, all flags
  false).
- `E9_ROLLOUT_ALLOWLIST` is already parsed: comma-separated, casefold+trim
  normalized, format-validated (`[a-z0-9_@.+-]{1,160}`), de-duplicated, and
  **must be empty when scope is `admin_only`** (`:191-192`) — this already
  enforces the "don't silently widen admin_only" invariant.
- Reason-code precedence already matches the intended design: `unauthenticated`
  → `global_disabled` → `admin_entitled` (requires `admin_enabled` AND
  `is_admin`) → `named_allowlist` → `not_allowed`. `eligible = reason in
  {admin_entitled, named_allowlist}`. Flags are zeroed entirely unless
  `e9Shell` is itself true (`:229-230`).
- Called with **freshly re-read** `user_id`/`username`/`is_admin` from the
  `users` table at the `/api/auth/me` call site (`:5991-5994`), not trusted
  from `session` — this was already verified during Stage C and remains
  correct; do not change this call site's identity-sourcing pattern.

**Do not rebuild any of the above. WI-2 below is a verify-and-fix task, not a
greenfield build.**

### 2.3 Confirmed gap: allowlist matches on `username`, not a stable ID

`_e9_rollout_decision()` line 223: `_e9_normalize_identity(username) in
config['allowlist']`. This matches on **username**, not a canonical/stable
user identifier — the function already receives `user_id` as a parameter
(used earlier in the same function and passed through to
`_e9_rollout_telemetry`), so switching the match target does not require a
new parameter, only a different comparison. Searched for a username-change
code path (`UPDATE users SET username`, rename-account endpoints) — none
found, so usernames may be immutable today in practice — but matching a
security-relevant allowlist against a display-style identifier instead of the
primary key is fragile by convention regardless (future username-change
features, case-folding edge cases, username reuse after account deletion are
all foreclosed risks if the match key is the numeric ID instead).

### 2.4 Confirmed: `scripts/release/set-e9-rollout.ps1` cannot enable allowlist today

Full current file read this session. Confirmed:
- `[ValidateSet('status','dry-run','enable-admin-only','disable','rollback')]`
  (`:4`) — no `enable-allowlist`.
- `Assert-E9RuntimeFlags` (`:94-99`) hard-codes an assertion that
  `E9_ROLLOUT_SCOPE -eq 'admin_only'` for **every** operation branch it
  checks — it has no branch for `named_allowlist` at all.
- The auto-rollback catch block (`:102-119`) only triggers
  `if ($Operation -eq 'enable-admin-only')` — a failed `enable-allowlist`
  would not auto-roll-back today.
- There is no parameter anywhere in the script for supplying the target
  allowlist's user IDs.
- The underlying Python helper invoked via `Invoke-E9Helper`
  (`scripts/release/e9_rollout_config.py`, referenced but **not yet read this
  session** — WI-3 must read it before extending it) is what actually mutates
  the remote `.env` file; its current `--operation` contract is unknown until
  read and must not be assumed.

## 3. Work Items

### WI-1: `js/e9/component_loader.js` timeout hardening

Add a bounded timeout to `loadComponent()`'s fetch, composing with (not
replacing) the existing generation/idempotency mechanisms in §2.1.

Design (verified reasoning, not just a requirement list — implement this
shape unless a concrete correctness reason forces a different one):

```js
var COMPONENT_FETCH_TIMEOUT_MS = 8000; // module-level constant, tunable

// inside loadComponent(), after the existing generation/current() setup:
var controller = new AbortController();
var timeoutHandle = setTimeout(function () { controller.abort(); }, COMPONENT_FETCH_TIMEOUT_MS);
if (global.E9 && typeof global.E9.registerCleanup === 'function') {
  global.E9.registerCleanup(function () {
    clearTimeout(timeoutHandle);
    controller.abort();
  }, generation);
}

return fetch(versionedUrl(url), { credentials: 'same-origin', signal: controller.signal })
  .then(function (res) { clearTimeout(timeoutHandle); /* ...unchanged... */ })
  .catch(function (err) {
    clearTimeout(timeoutHandle);
    if (!current()) return false; // stale generation -- covers BOTH the
      // destroy-triggered abort above AND any other already-tested stale
      // case; destroyLifecycle() always advances lifecycleGeneration before
      // its cleanups run, so by the time our destroy-triggered abort() fires,
      // current() is already false here.
    // current() is true and we got an AbortError: the only other abort()
    // call site is the destroy cleanup above, which cannot fire while
    // current() is still true. So reaching here with an AbortError can only
    // mean OUR OWN timeout fired -- render the identical fallback as any
    // other failure, no new visual state needed.
    /* ...existing fallback-render logic, unchanged... */
  });
```

Do not introduce a `timedOut` boolean or any second cleanup path — the
reasoning above is why one isn't needed. **This reasoning is an invariant
that depends on there being exactly two `abort()` call sites in this
function (the timeout handler and the destroy-triggered cleanup) — leave a
comment at both call sites stating this explicitly, so a future change that
adds a third cancellation source (e.g. a manual retry button) is forced to
re-examine this reasoning instead of silently inheriting a now-false
assumption.** If Codex's implementation needs a `timedOut`-style flag anyway
(e.g. because of an ordering subtlety missed above), the completion report
must explain why, not silently add it.

Required behavior (acceptance-test this explicitly, do not just eyeball it):
- Success before timeout: **functionally and visually equivalent** to today
  (rendered fragment, `data-e9-loaded` state, and visible behavior unchanged;
  "byte-identical" is not the right bar once a `signal`/timer are added to
  the call). `COMPONENT_FETCH_TIMEOUT_MS` must be overridable by tests (e.g.
  a small injectable value) so acceptance tests are not required to actually
  wait 8 real seconds per case.
- HTTP error, network error: unchanged behavior (already correct).
- Permanently-pending fetch: after `COMPONENT_FETCH_TIMEOUT_MS`, the slot
  shows the same fallback UI as an HTTP 500 would.
- `destroyShell()` called while a fetch is in flight: no fallback render (the
  root's content is about to be wiped by `destroyLifecycle()` anyway), no
  console error, no uncaught rejection.
- Remount after a timeout: the next `initShell()` cycle loads normally, no
  leftover timer, no leftover AbortController referencing a stale generation.
- Two consecutive destroy/remount cycles with a timeout in each: verify with
  fake timers (or an equivalent deterministic harness) that no timeout
  callback remains capable of firing after settle or destroy — do not
  require a specific active-timer-introspection API; the outcome (no stray
  callback ever fires again) is what matters, not the mechanism used to
  prove it.

Explicitly out of scope for this WI (note in the completion report, do not
fix): the same "no timeout" gap exists in the per-slot **data** fetches inside
`top_hud.js` (player state), `right_cards.js` (4 separate fetches), and
`world_stage.js` (`/api/adventure/bootstrap`) — these are a different call
site than the fragment fetch this WI hardens, and a component whose fragment
loads fine but whose own internal data fetch hangs is not covered by this fix.
Record this as a known, separate residual risk; do not silently expand scope
to cover it in this task.

### WI-2: Canonical User-ID Allowlist Correction and Validation

This is **not** a build task for logic that already exists (see §2.2) — treat
it as a targeted correctness fix plus a verification pass. The name is
deliberate: this work item corrects an identity-model defect in existing
code, it does not construct a new allowlist system.

1. **Identity fix**: change `_e9_rollout_decision()`'s allowlist comparison
   (currently `_e9_normalize_identity(username) in config['allowlist']`) to
   compare against `user_id` instead. **Canonical format, finalized, not an
   executor choice**: `users.id` is `SERIAL PRIMARY KEY` (`app.py:2736`) — a
   Postgres auto-incrementing positive integer. `E9_ROLLOUT_ALLOWLIST`
   entries must therefore be decimal positive integers matching
   `^[1-9][0-9]*$` — no leading zeros (ambiguous representation), no sign, no
   decimal point, no username/email text. Reject anything else at config-parse
   time (fail closed, same as today's malformed-entry handling). Parse each
   entry to an integer (or a canonicalized decimal string — pick one
   representation and use it consistently across `_e9_rollout_config()`,
   `_e9_rollout_decision()`, the `.env` serialization, the Python deploy
   helper, and the PowerShell parameter validation in WI-3; do not let each
   layer invent its own normalization). Update the env var's operator-facing
   documentation
   (`docs/deployment/e9_rollout_setter.md` or equivalent) to state plainly
   that `E9_ROLLOUT_ALLOWLIST` takes canonical user IDs, not usernames — this
   is a behavior change for anyone who might have assumed otherwise from the
   current code, so it must be visible, not silent.
   **Hard prohibition**: do not implement `user_id match OR username match`
   or any other dual-track/fallback comparison "for compatibility." A
   fallback path would let the incorrect identity model persist indefinitely
   alongside the correct one and make the allowlist's true, actual coverage
   impossible to audit with confidence. The migration is a clean cutover:
   `E9_ROLLOUT_ALLOWLIST` entries must be canonical user IDs from that point
   on, full stop. Before dispatch/first production use of `enable-allowlist`
   (Phase 2, not this task), any intended allowlist usernames must be
   resolved to canonical IDs out of band and the tool must validate IDs
   only — this task book does not require building an id-resolution helper,
   only refusing to accept non-ID input silently.
   **No canonical user ID resolvable for the authenticated request** (e.g. a
   session somehow lacking a usable `user_id`) must fail closed to Legacy,
   exactly like any other unresolvable-identity case — never treated as a
   match, never treated as admin-equivalent.
2. **Verification, not rebuild**: confirm the following already work as
   described in §2.2 and add/extend tests only where coverage is missing —
   do not rewrite working code to match this task book's prose if the
   existing code is already correct: fail-closed on malformed config;
   `admin_only` scope rejects a non-empty allowlist; reason-code precedence;
   flags zeroed unless `e9Shell` true; fresh (non-session-trusted)
   `user_id`/`username`/`is_admin` at the `/api/auth/me` call site.
   Also confirm (already true today, per `_e9_rollout_telemetry()` at
   `:233-241` and the `/api/auth/me` response shape): the full allowlist
   is never serialized to the client, and server logs record only
   `eligible`/`reason`/`effective_flags`/`decision_version`/`kill_switch`
   plus a **hashed** user digest — never a raw ID or the allowlist contents.
   Add a regression test asserting the `/api/auth/me` response body and the
   `[e9_rollout_decision]` log line never contain the configured allowlist
   entries verbatim, so this property can't silently regress later.
3. **Frontend flag sourcing**: `js/e9/shell.js`'s `init()` reads flags via
   `global.E9.getFlags()`. Verify exactly where that function's data
   originates (server-rendered inline JSON at page load vs. a live fetch) and
   confirm the `named_allowlist` decision flows through the same path with no
   additional frontend changes required. If it does not, this WI must add
   whatever minimal wiring is needed — but confirm first; do not assume a
   frontend change is necessary.
4. Reason codes already in production use (`global_disabled`,
   `admin_entitled`, `named_allowlist`, `not_allowed`, `unauthenticated`,
   `invalid_config`) must be kept exactly as spelled — do not rename to match
   any other document's suggested wording (e.g. `scope_admin_only`,
   `allowlist_match`, `invalid_configuration`). Canonical First applies to
   working code, not just task books.

### WI-3: `scripts/release/set-e9-rollout.ps1` allowlist support

Read `scripts/release/e9_rollout_config.py` in full before starting — its
current `--operation` contract is unverified as of this task book and must
not be assumed.

Add:
- `enable-allowlist` to the `[ValidateSet(...)]`.
- A new parameter for the target allowlist (canonical user IDs,
  comma-separated or array — match whatever format WI-2 settles on),
  validated locally (format + non-empty + dedup) before any remote call, so a
  malformed list fails before touching the network.
- Extend the Python helper to support writing `E9_ROLLOUT_SCOPE=named_allowlist`
  and `E9_ROLLOUT_ALLOWLIST=<ids>` with the same backup/audit-log/lock
  discipline already used for `enable-admin-only` — do not bypass
  `$backupDir`/`$auditPath`/`$lockPath`.
- Extend `Assert-E9RuntimeFlags` with a `named_allowlist` branch (expected
  scope, expected non-empty allowlist matching what was requested, same
  flags string as today) **without weakening or removing the existing
  `admin_only`/`disable` branches**.
- Extend automatic rollback to cover `enable-allowlist`. **On failure, restore
  the exact pre-operation rollout configuration from the operation's own
  backup** (`$backupDir`/`.e9-rollout-backups` already exists as a mechanism
  today — read `e9_rollout_config.py` to confirm whether it already writes a
  restorable pre-change snapshot there, or only a disable-fallback path; if
  only the latter, extend it to snapshot-and-restore). Do **not** hard-code
  the rollback target to `disable` — Production's pre-Phase-2 state is
  `admin_only`, and a failed `enable-allowlist` attempt must restore
  `admin_only`, not silently drop existing admins to fully disabled, which
  would be an unrelated service regression caused by an unrelated operation's
  failure. The existing `enable-admin-only` rollback path (which does
  hard-code `disable`) is out of scope to change in this task — note it as a
  pre-existing, differently-scoped pattern in the completion report, do not
  silently rewrite it. After any rollback, re-verify scope, allowlist
  contents, flags, admin eligibility, and health — a rollback is not
  complete until it's re-verified, not merely attempted.
- **Owner gate: `GO_ENABLE_E9_ALLOWLIST`** (finalized, not open for Codex to
  reinterpret). Do not reuse the existing `GO_DEPLOY` string this script
  already uses for `enable-admin-only`/`disable`/`rollback` for the new
  `enable-allowlist` operation. Rationale: `GO_DEPLOY` authorizes *deploying
  an approved runtime/static version* — it says nothing about who is exposed
  to what, and a deploy can happen with zero rollout-scope change. Enabling
  the allowlist is a different axis entirely: it changes which real,
  non-admin end users are exposed to E9, on the *same* running image —
  rollback here means reverting rollout state, not reverting a version. These
  two axes must never be collapsible into one ambiguous gate string, per this
  project's own established precedent that operation-specific gates are not
  interchangeable (see `GO_DEPLOY_CONTROLLED_W29`). If a future operation
  needs to both deploy and enable the allowlist in the same sitting, that
  requires **both** gates to be explicitly named by the owner — never assume
  one implies the other.
- Dry-run mode (`-Execute` omitted) must produce a correct preview
  (target scope, target allowlist, effective flags) without opening any
  remote connection that mutates state, matching the existing dry-run
  contract for `enable-admin-only`.

Do **not** touch production in this task. Do not run this script against the
real host. All verification is local/test-only (unit tests over the Python
helper's logic; PowerShell script static/parameter-validation tests; a mocked
remote-response harness matching the existing test pattern in
`tests/deployment/test_e9_rollout_setter.py` if one already covers this
script — extend it, don't duplicate it).

### WI-4: Integrated acceptance and test gate

Before the first code change, run the relevant existing suites and record the
baseline (pre-existing failures/skips) — the final gate is judged against
that baseline, not zero.

**Eligibility matrix — verify every row explicitly (server-side decision
test plus a real browser check for at least the first four rows, mirroring
the Stage C acceptance methodology already used this cycle):**

| User class | Expected result |
|---|---|
| Admin | E9 (`admin_entitled`) |
| Allowlisted non-admin | E9 (`named_allowlist`) |
| Non-allowlisted non-admin | Legacy (`not_allowed`) |
| Logged-out | Legacy (`unauthenticated`) |
| Invalid rollout configuration (malformed scope/allowlist/flags) | Legacy for everyone (`invalid_config`), including admins |
| Authenticated request with no resolvable canonical user ID | Legacy (fail closed, never a match, never admin-equivalent) |

**Reproducible local fixture methodology for the real-browser rows (proven
working this session, reuse this exact approach — do not invent a new one):**
a disposable local Postgres instance (e.g. `docker run --rm -e
POSTGRES_USER=go -e POSTGRES_PASSWORD=<local-only, throwaway> -e
POSTGRES_DB=go_odyssey -p <local-port>:5432 postgres:17-alpine`, never the
production database, never a production dump), a fresh venv with
`pip install -r requirements.txt`, `python app.py` pointed at that local
Postgres via `DATABASE_URL`, then **register test accounts through the app's
own `/api/auth/register` endpoint** (not direct SQL inserts, so password
hashing and normal account-creation invariants are exercised too), and flip
`is_admin`/allowlist membership via a direct `UPDATE users SET ...` against
the *local* Postgres only. Use clearly-scoped local-only usernames and
throwaway passwords (never real credentials, never anything resembling a
production account). Tear down the container and venv after the run. The
completion report may record the local fixture user IDs used (they are
meaningless outside this throwaway local database) but must never include
real user data, production connection strings, or credentials of any kind.

Confirm at the PR stage (not Production):

- `tests/test_e9_server_rollout_targeting.py`,
  `tests/test_e9_stage_c1_1_integration.py`,
  `tests/deployment/test_e9_rollout_setter.py` must all still pass after the
  WI-2/WI-3 changes, with new coverage added for the identity-match fix and
  the new `enable-allowlist` operation.
- `node --check tests/e2e/run_e9_acceptance_journey.mjs` (no scaffold changes
  expected in this task, but confirm untouched).
- A real, non-mocked run of the WI-1 fix is required: reproduce the
  permanently-pending-fetch case against a real running instance (local
  Postgres + `python app.py`, exactly as done this session) and confirm the
  fallback now renders within `COMPONENT_FETCH_TIMEOUT_MS` instead of hanging
  indefinitely. A unit test alone (mocking `fetch`) is not sufficient
  evidence for this specific fix — the whole point is that the real timing
  behavior changed.
- New failures = 0; new skips = 0; pre-existing failures/skips must not
  increase or change unexpectedly (document any pre-existing ones found, do
  not fix unrelated ones in this task).

## 4. Hard Boundaries

- Never read, modify, stage, or commit: `secret_key.txt`, `*.db`, `*.sqlite*`,
  `.env*`, `*.pem`, `*.key`, `*.bak*`, `questions.json`, any `*.sgf` bytes.
- Do not touch Production: no SSH to the production host, no docker commands
  against it, no compose edits beyond documentation, no execution of
  `set-e9-rollout.ps1` with `-Execute` against the real layout file.
- Do not change `E9_ROLLOUT_SCOPE`/`E9_ROLLOUT_ALLOWLIST`/any rollout env var
  on the production host. Phase 2 (a separate task book, separate owner gate)
  covers the actual cutover.
- Do not pull in any E10, SGF Engine V1 Closure, or Corpus Audit work — those
  are separate Roadmap phases with their own task books.
- Do not edit `sgf_engine/` (vendored, unrelated to this task anyway).
- Forbidden git: `add .`/`-A`, `commit -a`, `reset --hard`, `clean`,
  `stash -u`, force push, amend of existing history, squash/rebase merge.
- Work on a feature branch cut from `origin/master`; conventional commits.
  Two commits are expected and acceptable in one PR — WI-1 (runtime
  hardening) and WI-2+WI-3 (allowlist foundation) are naturally separable —
  but do not split further into review-convenience micro-commits.
- No change to player-visible correctness for any user currently in
  `admin_only` scope — an admin's experience must be byte-for-byte identical
  before/after this PR (aside from the timeout fix only ever firing on a
  pathological hang, which no admin should be hitting today).

Stop-and-escalate (OWNER_DECISION_REQUIRED) only for: anything requiring
production data access, or anything requiring a new go-semantics or
identity-scheme ruling beyond what's specified above. The owner-gate name
(`GO_ENABLE_E9_ALLOWLIST`) and the no-username-fallback rule in WI-2 are both
finalized decisions, not open questions — do not re-raise them as
escalations. Ordinary failures (tests, imports, stale contracts, timeouts)
are yours to fix.

## 5. Completion Report (return exactly this structure)

```
E9 Phase 1 — Allowlist Foundation Report
Result: DRAFT_PR_READY | OWNER_DECISION_REQUIRED | TRUE_INFRASTRUCTURE_FAILURE
Preflight: worktree path / branch / starting origin/master SHA / baseline items verified or superseded
Branch / Draft PR:
WI-1 Timeout hardening: constant value used / abort-on-destroy mechanism (registerCleanup reuse confirmed or deviation explained) /
  test evidence for each required behavior in §3 WI-1 / real (non-mocked) hang reproduction before/after
WI-2 Canonical User-ID Allowlist Correction: identity fix applied (user_id, no username fallback confirmed absent) /
  config regex decision / no-full-allowlist-to-client + hashed-log regression test evidence /
  frontend flag-sourcing verification result / reason-code names unchanged confirmation /
  test evidence for existing-logic verification
WI-3 Deployment tooling: e9_rollout_config.py contract as found / enable-allowlist operation added /
  Assert-E9RuntimeFlags extension / auto-rollback extension / GO_ENABLE_E9_ALLOWLIST gate wired in /
  dry-run preview evidence / confirmation no remote host was touched
WI-4 Eligibility matrix: all six rows confirmed (server-side + browser for the first four) / evidence per row
Test gate: baseline pre-existing failures+skips / files discovered=executed / new failures=0 / new skips=0
Boundaries: protected files untouched (git diff --stat evidence) / no production access / no scope pulled from other phases
Open items for merge audit:
```
