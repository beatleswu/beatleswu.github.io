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

## `run_e9_acceptance_journey.mjs`

Status: scaffold added 2026-07-22, hardened the same day after an independent
review; still not yet run against a live local/staging instance (none was up
in the session that authored it), not wired into CI.

### Why this one hits the real backend

The other two scripts mock every `/api/*` response, which is right for
proving client-side request-dedup contracts but cannot catch a real
integration break — e.g. the JS being intact while the DOM/config it depends
on is missing. This script hits a real Flask backend and a real
Postgres-backed session/rollout decision instead, to close exactly that gap.

### What it covers

- admin login (real `#username`/`#password`/`#login-btn` → `/api/auth/login`)
- admin gate / rollout assertions (`/api/auth/me` → `e9_rollout.eligible`,
  `reason`, `effective_flags`)
- page reload stability
- shell lifecycle destroy + remount, over **two** consecutive cycles:
  `E9.destroyShell()` → `primeInitialE9ShellOwnership()` + `E9.initShell()`,
  asserting the lifecycle generation counter advances each time, **and** a
  narrowly-scoped `addEventListener`/`removeEventListener` spy on the E9
  shell + slot roots (not `document`/`window`) proving destroy actually
  removes listeners and a second destroy doesn't remove fewer listeners than
  the immediately-preceding remount added (the direct anti-leak/
  anti-duplication signal). Plus one stale-in-flight-callback check: a
  non-critical slot's fragment fetch is deterministically delayed via
  `page.route()`, destroyed mid-flight, and the late completion is asserted
  not to have resurrected the destroyed slot's mounted markers. See
  "What the lifecycle scenario does and does not prove" below — this is not
  a claim of complete lifecycle coverage.
- logout + relogin (`doLogout()`, then a fresh login)
- non-admin Legacy boundary (separate account, asserts all six flags are
  present, are real booleans, and are all `false`, plus `activeShell ===
  'legacy'` — see effective_flags validation below)

Each scenario reports `passed` / `failed` / `skipped` independently —
scenarios needing credentials that aren't set are skipped, not failed, so the
connectivity check alone can run with zero credentials configured. **A run
with skipped scenarios is never reported as a complete acceptance pass** —
see "Result semantics and exit codes" below.

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

The final summary reports `ok` (no scenario failed), `complete` (every
scenario that should have run, did run, and passed — i.e. `failed === 0 &&
skipped === 0`), plus `passed`/`skipped`/`failed` counts. Exit codes:

| Condition | Exit code |
|---|---|
| Any scenario failed | `1` |
| No failures, but something was skipped (e.g. no admin creds configured) | `2` (unless `E2E_ALLOW_INCOMPLETE=1`, see below) |
| Every scenario ran and passed (`complete: true`) | `0` |

A connectivity-only run with zero credentials configured — server reachable,
5 scenarios skipped — reports `ok: true, complete: false` and **exits 2**,
not 0. Setting `E2E_ALLOW_INCOMPLETE=1` allows that same run to exit `0`
instead, for an intentional local partial check, but the console output and
the JSON summary still say `complete: false` either way — this opt-in never
makes a partial run look like a full acceptance pass.

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

Any of the above requires `E2E_ALLOW_PRODUCTION=I_UNDERSTAND_PRODUCTION_RISK`
to proceed. Verified against 29 cases against the actual exported guard
function: 17 inputs confirmed blocked (domain case/trailing-dot/
percent-encoded variants, subdomains, embedded userinfo, the plain
production IP with and without a port, both IPv4-mapped-IPv6 textual forms
as direct literals and via a mocked DNS resolver — including a resolver
returning multiple addresses where only one matches, and the exact
bracket-and-port bypass repro from the prior review round), 11 confirmed
allowed (localhost, a different registrable domain that merely starts with
`godokoro.com.`, an unrelated host, a benign IPv4-mapped address, `::1`,
`2001:db8::1`, a link-local address with a zone identifier, a DNS lookup
that throws, and mocked-resolver cases returning a benign address or a
malformed/garbage mapped-looking string), and 1 case (a syntactically
invalid IPv6 literal in the URL itself) confirmed to throw a clear parse
error rather than silently proceeding.

### Running it

```
cd tests/e2e
npm install   # first time only
E2E_BASE_URL=http://localhost:5000 \
E2E_ADMIN_USERNAME=... E2E_ADMIN_PASSWORD=... \
E2E_NONADMIN_USERNAME=... E2E_NONADMIN_PASSWORD=... \
npm run e9:acceptance
```

Point `E2E_BASE_URL` at a local or staging instance you already have running
— this script does not provision or start any server, Postgres included, and
does not create the admin/non-admin test accounts it logs into.

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
- **Not yet executed end-to-end against a real app.** Verified so far:
  `node --check` syntax; the production guard (29 cases: 17 confirmed
  blocked, 11 confirmed allowed, 1 confirmed to throw a clear parse error —
  see "Production guard" above for the breakdown, including IPv4-mapped-IPv6
  detection via a mocked DNS resolver); `effective_flags` shape validation
  (14 cases, including the missing-field/missing-key false-pass fixes and
  inherited-vs-own-property rejection); the `complete`/exit-code semantics
  (skipped-only run confirmed to exit `2`, and `E2E_ALLOW_INCOMPLETE=1`
  confirmed to exit `0` while still reporting `complete: false`); the
  listener-spy instrumentation mechanics against a plain fixture page
  (counts adds/removes correctly, persists across repeated
  `installListenerSpy()` calls, doesn't double-count) and the `page.route()`
  deterministic-delay-plus-`unroute()` technique used by the stale-callback
  check; and graceful fail/skip behavior against both an unreachable target
  and a reachable-but-unauthenticated one. The admin/non-admin happy-path
  scenarios — including the lifecycle destroy/remount cycle's assertions
  running against the *actual* E9 shell rather than a fixture — have not
  been run against a live local/staging app, since none was up in the
  session that authored and hardened this scaffold.

### Safety

Only exercises actions a normal user/admin can already take through the UI
(login, reload, logout, relogin, destroy/remount via the exposed `E9`
globals). Never touches `E9_ROLLOUT_*` env vars, database rows, or deploy
tooling.
