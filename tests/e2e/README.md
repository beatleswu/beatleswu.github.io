# tests/e2e

Real-browser (`playwright-core`, no `@playwright/test` runner) contract and
acceptance scripts. No `playwright.config.*` — each script is a standalone
Node ESM entry point, run directly via `node <script>.mjs` or the `npm run`
aliases in `package.json`.

| Script | Backend | Purpose |
|---|---|---|
| `run_e9_layout_contract.mjs` | mocked | E9 layout contract |
| `run_e9_fetch_contract.mjs` | mocked (`page.route` fulfills every `/api/*`) | E9 client-side request-dedup/fallback contracts |
| `run_e9_acceptance_journey.mjs` | **real** — no mocking | E9 admin login, reload, logout/relogin, shell destroy/remount lifecycle, admin gate, non-admin Legacy boundary |
| `run_e9_acceptance_helpers_unit_tests.mjs` | n/a — no browser, no network | Direct unit tests for the acceptance journey's pure/near-pure helpers (production guard, strict flag assertion, exit classification) |

## `run_e9_acceptance_journey.mjs`

Status: scaffold added 2026-07-22; hardened again 2026-07-24 (E9 Stage C2.2)
after an independent review identified concrete gaps in the harness itself —
see "2026-07-24 hardening pass" below for exactly what changed and why. Not
wired into CI.

### Why this one hits the real backend

The other two scripts mock every `/api/*` response, which is right for
proving client-side request-dedup contracts but cannot catch a real
integration break — e.g. the JS being intact while the DOM/config it depends
on is missing. This script hits a real Flask backend and a real
Postgres-backed session/rollout decision instead, to close exactly that gap.

### 2026-07-24 hardening pass (E9 Stage C2.2)

An independent review of the 2026-07-22 scaffold raised six concerns. Reading
the actual current code (not a prior report) before making any change showed
three of the six were **already correctly handled** by the existing
implementation, and three were genuine gaps. Recorded here so the next reader
doesn't have to re-derive which is which:

| Concern raised | Actual state found | Action taken |
|---|---|---|
| Production guard bypassable via trailing dot / encoded hostname / raw IP | Already handled: hostname denylist + IP denylist + DNS-resolution follow-through + IPv4-mapped-IPv6 recognition, all pre-existing. Empirically re-verified `new URL()`'s own handling of a percent-encoded trailing dot, explicit ports, and userinfo — all already correctly reduce to the same blocked hostname. | Added a **redirect-bypass** check that was genuinely missing (see below); added comprehensive regression tests for every case in `run_e9_acceptance_helpers_unit_tests.mjs`. |
| Lifecycle scenario only observes a screen transition, not real listener cleanup | Already handled: a prototype-patched `addEventListener`/`removeEventListener` spy proves real removal across two destroy/remount cycles. | Extended to a third listener-count read (anti-accumulation proof across cycles) and split into its own distinctly-reported scenario. |
| No test for stale async callbacks being blocked by generation | Already handled, both in the app (`component_loader.js` + every component module check `isLifecycleCurrent(generation)` before mutating DOM) and in the harness (one `page.route()`-delayed fetch, destroy-mid-flight check). | Extracted into its own distinctly-reported scenario; left as-is otherwise — no runtime defect found. |
| Non-admin assertions could treat a missing flag as `false` | Already handled: `assertFlagsAllEqual()` requires every flag to be an **own**, real-boolean property before comparing values. | Added 15 regression cases (missing key, inherited-only key, string `"false"`, numeric `0`/`1`, explicit `undefined`) to the new unit test file. |
| All-skip still exits success | Already handled: a skipped-only run already exits `2` by default; `0` only with an explicit `E2E_ALLOW_INCOMPLETE=1` opt-in. | Extracted the classification logic into exported pure functions (`classifyOutcome`/`exitCodeForClassification`) and added a direct unit-test matrix for it. |
| No console/page-error or duplicate-DOM checking | **Genuine gap, confirmed absent everywhere in this repo's E2E tooling.** | Added both from scratch — see "Browser error monitoring" and "Duplicate-DOM invariants" below. |

The one concrete code change to the guard itself: it previously only
evaluated `E2E_BASE_URL` once, before `chromium.launch()`. If the target
redirects to Production *after* that check (e.g. a staging proxy that 302s
under some path), nothing re-checked the page's actual landed URL. The guard
is now re-evaluated against `page.url()` immediately after every navigation
that precedes a login form interaction, and before any credential is filled
in — see "Production guard" below.

### What it covers

Ten requirements, reported as ten distinctly-named scenarios (some share
underlying browser state/session with the scenario immediately before them,
matching the existing pattern of `reload_stability` reusing
`admin_login_journey_and_gate`'s page):

1. `admin_login_journey_and_gate` — real login → `/api/auth/me` →
   `e9_rollout.eligible/reason/effective_flags` → `activeShell === 'e9'`.
2. `reload_stability` — same assertions survive a reload.
3. `lifecycle_destroy_remount` — two destroy/remount cycles: lifecycle
   generation advances each time, `destroyShell()` genuinely removes
   listeners, a remount genuinely re-registers them, and a **third**
   listener-count read after the second remount must equal the first
   remount's count exactly (not just `>0`) — proving no accumulation across
   cycles, not merely that registration happens at all.
4. `lifecycle_listener_cleanup_accounting` — re-reports item 3's listener
   deltas as their own distinct, independently-checkable result.
5. `lifecycle_no_duplicate_action_dispatch` — registers a test-only probe
   listener via the *real* `E9.on()`/`registerCleanup()` mechanism (the exact
   function every real component uses) on the persistent shell root
   (`#e9-adventure-shell` itself is never recreated by destroy/remount, only
   its descendants are wiped — so a listener attached directly to it
   survives physically unless `removeEventListener` bookkeeping actually ran)
   bound to the current generation, dispatches one synthetic event, and
   requires exactly one invocation. Repeats after one more destroy/remount:
   if a prior generation's probe were not truly removed, this second
   dispatch would report 2 invocations for one event, not 1.
6. `lifecycle_stale_async_generation_rejection` — the pre-existing
   engineered-delay/destroy-mid-flight check, now its own named scenario.
7. `lifecycle_duplicate_dom_invariants` — see "Duplicate-DOM invariants"
   below.
8. `relogin_journey` — logout → re-login, same assertions as #1 plus a
   duplicate-DOM check.
9. `non_admin_legacy_boundary` — separate account, all six flags strictly
   asserted `false`, `activeShell === 'legacy'`, plus a duplicate-DOM check
   for the legacy state.
10. `browser_runtime_error_free` — always runs (needs no credentials);
    asserts the aggregate `report.browser_errors` collected across every
    scenario that did run is empty. See "Browser error monitoring" below.

Each scenario reports `passed` / `failed` / `skipped` independently —
scenarios needing credentials that aren't set are skipped, not failed, so the
connectivity check and `browser_runtime_error_free` can both run with zero
credentials configured. **A run with skipped scenarios is never reported as
a complete acceptance pass** — see "Result semantics and exit codes" below.

### What the lifecycle scenario does and does not prove

Directly verified, with a real observable signal: `destroyShell()` actually
executing (checked via the `activeShell` transition to `'legacy'`, which only
happens if `applyShellState('legacy')` ran), the lifecycle generation counter
advancing on each of two consecutive remounts, a real remount succeeding
(only possible because `destroyLifecycle()` reset `mountStarted`), and —
new in this hardened version — that `destroyShell()` genuinely calls
`removeEventListener` on the instrumented E9 roots (not just that it didn't
throw), and that a second destroy doesn't lose track of listeners the prior
remount added.

Still not verified: listeners on `document`/`window` (the spy is
deliberately scoped to the E9 shell + slot roots only, to keep the signal
attributable and avoid noise from unrelated document-level listeners
elsewhere in the app) and non-critical-slot fragments other than
`top_hud.html` for the stale-callback check. The stale-callback check uses a
deterministic, engineered network delay (`page.route()` + a fixed timeout),
not a blind `waitForTimeout` guess — but it only exercises one slot's race,
not all four non-critical slots'.

### Duplicate-DOM invariants

`assertNoDuplicateE9Dom(page, expectedActiveShell)` checks, on demand:

- exactly one of each of the six E9 root selectors (`#e9-adventure-shell` and
  the five slot roots) — never zero, never duplicated;
- no `id` used by any node inside the shell root is duplicated anywhere else
  in the document (catches a stale fragment leaking outside its owning root);
- `activeShell` matches what's expected, and `#e9-adventure-shell.hidden`
  is consistent with it (`hidden === true` for legacy, `false` for e9 — this
  is the concrete meaning of "zero/one **active** shell roots", since the
  single `#e9-adventure-shell` element always exists structurally, hidden or
  not);
- when legacy is active, every slot is free of both mount markers
  (`data-e9-loaded`/`data-e9-inited`) and leftover `innerHTML` — proving
  `destroyLifecycle()`'s cleanup actually ran, not merely that the shell
  root itself got hidden.

Run inside `admin_login_journey_and_gate`, `reload_stability`,
`relogin_journey`, `non_admin_legacy_boundary`, and — most thoroughly, in
both the e9 and legacy state within one fresh destroy/remount cycle —
`lifecycle_duplicate_dom_invariants`.

### Browser error monitoring

Every page created by this script has, before any navigation:

- `page.on('console', ...)` — captures `console.error`-level messages;
- `page.on('pageerror', ...)` — captures uncaught exceptions;
- an `addInitScript()`-installed `window.addEventListener('unhandledrejection', ...)`
  — Playwright has no direct browser-level event for this, so it's captured
  in-page and drained via `page.evaluate()` at checkpoints. `addInitScript`
  (not a one-off `page.evaluate()`) is used specifically because it survives
  reloads and re-navigations within the same page;
- `page.on('requestfailed', ...)` and 5xx responses on `page.on('response', ...)`,
  scoped to E9-relevant paths only (`/api/auth/me`, `/api/auth/logout`,
  `/components/adventure/*`, `/js/e9/*`) — an unrelated third-party asset
  404 is not this harness's concern.

All entries accumulate into one `report.browser_errors` array shared across
every scenario. `BROWSER_ERROR_ALLOWLIST` is a narrow, exact-match allowlist
for individually-justified benign messages — **empty by default**. An entry
may only be added once a specific message is independently confirmed benign,
with a comment explaining why; this must never become a broad category
suppression. The final `browser_runtime_error_free` scenario asserts the
aggregate array is empty and includes full captured detail in its failure
message if not.

### effective_flags shape validation

Before comparing any of the six flags, the response must have
`rollout.effective_flags` present, be a plain object, contain every expected
flag key as the object's **own** property (`Object.prototype.hasOwnProperty`,
not merely reachable through its prototype chain), and hold a real boolean
for each — a missing object, a missing or only-inherited key, or a
non-boolean value fails the assertion for **both** expected-true and
expected-false cases. (Two gaps closed here: a missing `effective_flags`
object could previously be mistaken for "correctly all false" in the
non-admin scenario, since `undefined` coerced to `false`; and a flag key
satisfied only via inheritance — never present in the actual API response —
could previously pass as if it were real data.) Verified with 14 cases,
including an object where one flag exists only on its prototype (not as an
own property) and is correctly rejected either way (expected `true` or
`false`).

### Result semantics and exit codes

The final JSON summary (always printed to stdout, including on a
preflight production-guard rejection — see below) reports: `base_url`,
`scenarios_total`, `passed`/`skipped`/`failed`, `ok` (no scenario failed),
`complete` (`failed === 0 && skipped === 0`), `browser_errors` (the full
captured-detail array — see "Browser error monitoring"),
`production_guard_result` (the initial guard verdict for `E2E_BASE_URL`),
and `final_exit_classification`, one of:

| `final_exit_classification` | Meaning | Exit code |
|---|---|---|
| `COMPLETE_PASS` | Every scenario ran and passed | `0` |
| `FAILED` | At least one scenario failed | `1` |
| `INCOMPLETE_BLOCKED` | No failures, but something was skipped, and `E2E_ALLOW_INCOMPLETE` was not set | `2` |
| `INCOMPLETE_PASS_OPTED_IN` | Same as above, but `E2E_ALLOW_INCOMPLETE=1` was explicitly set | `0` |
| `PRODUCTION_TARGET_REJECTED` | `E2E_BASE_URL` itself was refused by the production guard, before any browser launched | `1` |

`classifyOutcome({failed, skipped, allowIncomplete})` and
`exitCodeForClassification(classification)` are exported pure functions
covering this exact matrix, directly unit-tested (no subprocess spawning
needed) in `run_e9_acceptance_helpers_unit_tests.mjs`.

A connectivity-only run with zero credentials configured — server reachable,
most scenarios skipped — reports `ok: true, complete: false,
final_exit_classification: 'INCOMPLETE_BLOCKED'` and **exits 2**, not 0.
Setting `E2E_ALLOW_INCOMPLETE=1` allows that same run to exit `0` instead,
for an intentional local partial check, but `complete: false` is still
reported either way — this opt-in never makes a partial run look like a
full acceptance pass.

### Env vars

| Var | Required | Notes |
|---|---|---|
| `E2E_BASE_URL` | no | Defaults to `http://localhost:5000` (the app's own default `PORT`). Never defaults to production. |
| `E2E_ADMIN_USERNAME` / `E2E_ADMIN_PASSWORD` | for admin scenarios | Admin-gated scenarios skip if unset. |
| `E2E_NONADMIN_USERNAME` / `E2E_NONADMIN_PASSWORD` | for non-admin scenario | Skips if unset. |
| `E2E_ALLOW_PRODUCTION` | only to target production | Must equal exactly `I_UNDERSTAND_PRODUCTION_RISK`. See "Production guard" below for exactly what triggers this. |
| `E2E_ALLOW_INCOMPLETE` | no | Set to `1` to let a run with skipped scenarios exit `0` instead of `2`. Never changes `complete` in the reported output — see "Result semantics" below. |
| `CHROME_BIN` | no | Same convention as `run_e9_fetch_contract.mjs`; falls back to common Chrome/Edge install paths. |

Credentials are read from the environment only — never hardcoded, defaulted,
or logged.

### Production guard

Runs before `chromium.launch()` — before any browser, page, login, or network
request to the target. The target hostname is normalized (lowercased,
trailing dot(s) stripped, so `godokoro.com.` and `GODOKORO.COM` are treated
identically to `godokoro.com`) and refused if it:

- is `godokoro.com` or any subdomain of it, or
- is the known production IP, **in any of these representations**:
  - the plain IPv4 literal `152.69.200.105`;
  - the IPv4-mapped IPv6 form as typed by a person, `::ffff:152.69.200.105`
    (case-insensitive prefix, so `::FFFF:...` matches too);
  - the IPv4-mapped IPv6 form as WHATWG URL parsing and some DNS resolvers
    normalize it to, the pure hex-group spelling `::ffff:9845:c869`;
  - any of the above returned by DNS resolution (see below), not just as a
    literal in the URL;
  - an IPv6 zone identifier (`%eth0`) on any of the above is stripped before
    comparison — it only scopes which interface an address applies to, never
    changes the address's identity, so discarding it is correct rather than
    a loophole;
- or is a non-IP hostname that **resolves via DNS** to any of those same
  representations, even if the hostname itself doesn't look like production.

This is a **specific, narrow comparison** against known spellings of one
known IP — it is not general-purpose protection against every possible
network alias, reverse proxy, hosts-file mapping, NAT64 translation, or a
future production IP that isn't this one. A malformed attempt at the
IPv4-mapped form (e.g. an out-of-range octet) is rejected by Node's own IPv6
parser before it ever reaches this comparison — it simply isn't recognized
as an IPv4-mapped address, so it can't be "close enough" to match by accident.

A DNS resolution failure is never treated as evidence of production (the
direct hostname/IP checks above run first and don't depend on DNS
succeeding) — an unreachable or nonexistent host just fails naturally later,
as a normal connectivity error. None of this touches or logs URL-embedded
userinfo (`user:pass@host` credentials are stripped by URL parsing before
any comparison or logging happens).

**Redirect defense-in-depth:** the guard only ever sees `E2E_BASE_URL` once,
before `chromium.launch()` — that alone can't catch a target that only
*redirects* to Production after that check. `guardPageNotOnProductionTarget(page, context)`
re-evaluates the exact same guard against `page.url()` (the browser's
actually-landed URL, post-redirect) immediately after the connectivity
check's navigation and immediately after every navigation inside
`loginViaForm()` — always before any credential is filled in or submitted.

Any of the above requires `E2E_ALLOW_PRODUCTION=I_UNDERSTAND_PRODUCTION_RISK`
to proceed. Verified against the actual exported guard function in
`run_e9_acceptance_helpers_unit_tests.mjs` (`npm run e9:acceptance:unit`):
19 blocked cases (exact/uppercase/mixed-case hostname, trailing dot, multiple
trailing dots, percent-encoded terminal dot, explicit ports 80/443/8443,
userinfo, subdomains at multiple depths, a combined subdomain+port+userinfo
case, the plain production IP with and without a port, both IPv4-mapped-IPv6
textual forms as direct literals, a DNS-resolved address carrying an IPv6
zone id, and a hostname that only resolves to the production IP via a mocked
DNS resolver), 12 allowed cases (localhost, `127.0.0.1`, an unrelated staging
domain, a hostname that merely starts with `godokoro.com.` as a longer
suffix — not a real subdomain boundary — in both directions, the production
domain embedded in a path/query/both with a safe host, an unrelated IPv4 and
IPv6 literal), a DNS-resolution-failure case (confirmed not to block), and a
syntactically invalid URL (confirmed to throw a clear parse error rather
than silently proceeding). Note: a bracketed IPv6 literal carrying a zone id
(e.g. `[fe80::1%eth0]`) is not constructible as a `new URL(...)` at all —
confirmed empirically — so `stripBracketsAndZone()`'s zone-handling is only
reachable via a DNS-resolved address string, which is what its dedicated
test exercises.

### Running it

```
cd tests/e2e
npm install   # first time only

# Pure helper unit tests — no server, no browser, no credentials needed:
npm run e9:acceptance:unit

# Full acceptance journey against a real local/staging instance:
E2E_BASE_URL=http://localhost:5000 \
E2E_ADMIN_USERNAME=... E2E_ADMIN_PASSWORD=... \
E2E_NONADMIN_USERNAME=... E2E_NONADMIN_PASSWORD=... \
npm run e9:acceptance
```

Point `E2E_BASE_URL` at a local or staging instance you already have running
— this script does not provision or start any server, Postgres included, and
does not create the admin/non-admin test accounts it logs into. Never point
it at a production hostname/IP without deliberately understanding the risk —
see "Production guard" above.

### Explicitly out of scope for this scaffold

- **Not wired into CI.** No workflow file was added or changed. Whether and
  how this runs in CI — and whether it's ever pointed at production on a
  schedule — is a separate decision for the repo owner, per the E9
  reconciliation discussion on 2026-07-22.
- **Not a substitute for one manual owner-run check.** Before this suite's
  output is trusted as a baseline, a manual admin login/reload/relogin pass
  against the target environment should still happen once.
- **Does not create test accounts** — the accounts it logs into must already
  exist wherever `E2E_BASE_URL` points.
- **Not yet executed end-to-end against a real app, and this hardening pass
  did not change that.** This was already true of the 2026-07-22 scaffold
  and remains true after the 2026-07-24 hardening pass: running the
  admin/non-admin scenarios needs pre-existing test account credentials, and
  this scaffold deliberately never creates accounts itself (that would be a
  database mutation, which it — and the sprint that hardened it — is
  explicitly not authorized to do). Verified so far without a live app:
  `node --check` syntax on every changed file; the full
  `run_e9_acceptance_helpers_unit_tests.mjs` suite (production guard, strict
  flag assertion, exit-classification matrix — see the relevant sections
  above for exact case counts); the repository's static/source-level E9
  lifecycle and rollout contract suites (`tests/test_e9_shell_exclusivity.py`
  and the 13 other E9/Adventure test files, plus
  `tests/e9_node_tests/run_shell_exclusivity_tests.js`) all still pass
  unaffected, since this sprint touches no production runtime file. The
  admin/non-admin happy-path scenarios — including the lifecycle
  destroy/remount cycle's assertions, the new duplicate-DOM invariants, and
  browser-error monitoring running against the *actual* E9 shell rather than
  a fixture — have still never been run against a live local/staging app.
  Whoever next has real local admin/non-admin credentials available should
  run `npm run e9:acceptance` once against a local instance before trusting
  this as a baseline.

### Safety

Only exercises actions a normal user/admin can already take through the UI
(login, reload, logout, relogin, destroy/remount via the exposed `E9`
globals). Never touches `E9_ROLLOUT_*` env vars, database rows, or deploy
tooling.
