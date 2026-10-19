# Go Odyssey G MASTER — G009 P1 Companion visible UI candidate (2026-10-19)

**Kind:** isolated Product **candidate**, never GitHub origin/master, Oracle, formal Build, or production Test02 UAT.
**Base:** G integrated candidate `02f5f700dbe4057cfed55d66c1ab9ed671e5642e`. Preserves monthly rewards `00e9120d3cab59d88bd0fe1f2aaafb74bad15412`.

## Reproduced defect and actual fix

Chrome headless against the REAL Flask application's local `/hero?tab=pet` (D037 in-memory SQLite):
- G009 Hero Hub companion tab was visible but owned Spirit tiles were static `div` elements. The actual legacy `switchPet()`, `feedPet()` and `interactPet()` buttons existed inside the hidden legacy panel and therefore were not physically clickable. Playwright confirmed zero-sized, invisible legacy elements even though the API status loaded correctly.
- Patched `js/g009_hero_hub_batch_a.js` to render keyboard/touch-accessible buttons **only for owned, non-active Spirits**, a visible Pat button and food buttons with authoritative quantities. Delegates all actions to the original `switchPet`, `interactPet`, and `feedPet` route consumers, maintains one in-flight action lock, and accepts server reload projections; no new source of truth.
- Patched `css/g009_hero_hub_batch_a.css` for visible hit targets and focus/disabled styles. No G009 source authority changes.
- Extended disposable `tests/e2e/d037_local_runtime_server.py` to create two real in-memory food units plus item-use operation schema; no production database or user.
- Added `tests/e2e/run_20261019_g009_companion_visible_browser.mjs`, a real Chrome + Flask integration journey; requires local 127.0.0.1 fixture and deliberately refuses production host.

## Actual evidence

**Browser:** local Chrome + real Flask routes + disposable SQLite:
- 8/8 PASS: visible action buttons, single server switch, Pat POST, double-click food sends one POST and consumes one item, **committed feed with two lost HTTP responses recovers the exact original operation ID at zero remaining inventory without a second debit**, reload state, Chrome tablet **touch emulation** and no JS exceptions. Fault injection invokes the actual Flask route for the committed POST and aborts the response, rather than fabricating a success.
- Final create-only receipt: `docs/handoffs/GO_ODYSSEY_G009_COMPANION_BROWSER_20261019_R2.json` (**8/8**); earlier 7/7 receipt preserved separately.
- Actual API traffic: `/api/pet/switch`, `/api/pet/interact`, `/api/pet/feed` all HTTP 200, with durable operation IDs. No mock API.
- No actual Test02 production login, actual Safari/iPad or player wallet was involved. Browser harness blocks service workers for deterministic Playwright network-loss interception.

**Regressions:** `python -B -m pytest ...` across C/B/A/E targets **71 passed, 2 skipped**; Node previous companion **12/12**, D037 **10/10**, checks exit 0. Existing broader previous run **124 passed, 2 skipped, 1 deselected**. Separate Docker PostgreSQL 16.14 loopback disposable `tests/test_d015_quest_claim_reward_postgres.py` and `tests/test_d017_quest_runtime_postgres.py` **8/8 PASS** on real concurrent claim/replay and rollback. Docker container removed after run.

The Docker tests prove the **candidate backend** quest and idempotency contract; **not** that Quest V2 is enabled in production. `git diff --check` exit 0.

## Still blocked / not claimed

- **Test02 formal site:** Login-only page `https://godokoro.com/hero.html` redirects anonymous users to `/login`; `/api/pet/status` anonymously returns 401. No authenticated Test02 production E2E yet.
- **Production site uses original `go-odyssey-app:69dbe57a`**. This candidate is not deployed.
- **Hero growth → adventure** player-account cycle, production quest reward replay, production ranking identity, real monthly award delivered on logout/login, and Owner real iPad battle/map/touch UAT are separate remaining release gates. Fresh disposable native PostgreSQL 17 local tests for monthly settlement and independent-new-Flask-session rehydration were rerun **6/6 PASS**: NOT actual production login.
- **R15 V4 autonomous Goal Loop** continues **NO_GO** pending independently approved Owner trust root and real external WORM.
- Formal trusted source adoption / signature, GitHub origin/master sync, Build attestation, required Docker release matrix and rollback test must pass before seeking Owner GO_MERGE/GO_DEPLOY. Local tests do not waive any of them.

## A–F continuation

A: visible G009 switch, Pat, Feed isolation candidate, **lost-HTTP-response same-ID recovery** and replay proof PASS; production Test02 pending.
B: first-pass presentation candidate retained; cross-system player/hero/adventure E2E pending.
C: 8 PostgreSQL 16.14 quest claim and server idempotency tests PASS; production Quest V2 remains disabled and live E2E pending.
D: first-pass map/clear/resume candidate retained; real Owner iPad UAT pending.
E: previous October monthly rewards candidate retained; fresh native PG 17 first-settlement, notifications and new-session rehydration **6/6 PASS** independent of production.
F: first-pass shop/backpack candidate retained; official interface/release acceptance pending.

No formal Commit/Merge/Build/Deploy/production mutation is implied by this document.
