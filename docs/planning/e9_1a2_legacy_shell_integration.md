# E9.1A2 — Legacy Adventure Shell Integration

```
Sprint: E9.1A2 (second of the two E9.1A PRs — E9.1A1 built the foundation)
Branch: feature/e9-1a2-legacy-shell-integration
Base: master @ 2026f47c2bb55364d0132823b0eaabef2606c588
Production mutation: NONE
Deployment: NONE
```

## Objective

Wire the E9.1A1 component foundation into the real `index.html`, with `e9Shell`
defaulting to `false` — every real player still sees the legacy Adventure Map.
The E9 shell is only reachable on a debug hostname with an explicit
`?E9_DEBUG=1` opt-in.

## Two corrections made during implementation (flagged and resolved with the owner)

### 1. "Canonical 8 viewports" did not exist in this repo

A repo-wide search (tests/, docs/, CSS, no Playwright config present) confirmed
no pre-existing 8-viewport test matrix. Per owner decision, the 8 test
viewports used below are derived from this project's own existing CSS
breakpoint chain (`css/style.css` / `css/screen.css`, which both already use
the same 8-band structure): **1440×900, 1366×768, 1280×800, 1024×768, 768×1024,
640×960, 480×854, 320×568**. This is documented here as a derived decision, not
a matrix that already existed before this sprint.

### 2. Top HUD / Right Cards data scope corrected against real audit findings

The task book asked for Coins/Stars/HP/SP on Top HUD and a "Guild Pass" card
on Right Cards. Re-checking the actual codebase found:
- **Coins**: real API (`/api/user/coins`) — kept.
- **Stars**: only exists as a per-zone 0–3 rating (`zone.stars` from
  `/api/adventure/bootstrap`), not a global player stat. **Moved to World
  Stage** (rendered per zone tile), **removed from Top HUD** — summing zone
  stars into a fake "total stars" would be fabricated data.
- **HP/SP**: only exist as transient in-battle DOM state with no persistence
  API. **Not added to Top HUD** — showing `0/0` outside battle would be
  misleading, not an honest empty state.
- **"Guild Pass"**: confirmed not to exist as a system anywhere (no table, no
  route, no field) — per the E9.1A0 audit's Phase F finding. **Not added** as
  a card, an i18n key, or an empty-state placeholder — the rule (owner's
  words): *"功能或資料模型根本不存在 → 不渲染、不宣稱、不建立 placeholder"* (if the
  feature/data model doesn't exist at all, don't render it, claim it, or stub
  it — that's different from a real feature with no current data, which does
  get a translated empty state).

Final Top HUD: **player name, level, coins** only.
Final Right Cards: **Daily Challenge, Boss Progress (from the same
`/api/adventure/bootstrap` zones), SRS Due, Weakness Summary** — all four have
a real, existing canonical data source; no Guild Pass card.

## Architecture

- Same frontend fragment-assembly approach as E9.1A1 (no Jinja, no new JS
  framework, no new i18n engine).
- `index.html` gained exactly 3 additive blocks (36 lines in 1A1's spike +
  39 lines this sprint = fully additive, zero deletions, verified via
  `git diff`): 6 `<link>` tags in `<head>`, one hidden `<section
  id="e9-adventure-shell" data-e9-shell hidden aria-hidden="true">` block
  right after `#skill-map`, and 8 `<script>` tags before `</body>`.
- `app.py` gained exactly 3 new routes (`/js/e9/<path:subpath>`,
  `/css/e9/<path:subpath>`, `/components/adventure/<path:subpath>`), each
  extension-allowlisted via `abort(404)` and delegating to the existing,
  already-reviewed `_serve_live_static_or_baked_subpath` helper — no new
  traversal-protection logic was written, no `_serve_live_static_or_baked_subpath`
  refactor, no Jinja.
- `sw.js` gained exactly one changed line: `VERSION` bumped from
  `v177-sgf-fe-hotfix1a-node-parser` to `v178-e9-1a2-adventure-shell-integration`.
  No other line in `sw.js` changed (verified: `git diff sw.js` shows a
  1-line change). E9 `.js`/`.css` are covered by the existing generic
  `*.js`/`*.css` cache-first branch already — no new cache-strategy branch
  was needed, keeping this a pure version bump, not a SW refactor.
- `i18n.js` gained ~28 new `e9.*` dict entries (both `en`/`zh`), all under a
  new `e9.*` namespace following the existing `<page>.<section>.<field>`
  convention. Zone-state text (locked/unlocked/boss-ready/cleared/summary)
  **reuses the existing `index.adv.*` keys** rather than duplicating them —
  no second translation dictionary was created anywhere in `js/e9/*`.

## Critical vs. non-critical (shell.js)

- **Critical**: shell orchestration itself, World Stage. A failure here
  (fragment 404, or a successfully-loaded World Stage whose adventure-data
  fetch fails) calls `recoverToLegacy()`: hides the E9 shell, un-hides
  `#skill-map`, no reload, no further fragment requests.
- **Non-critical**: Top HUD, Right Cards, Bottom Dock, Left Nav. Each fails
  in isolation (handled by `component_loader.js`'s existing fallback
  rendering) and never touches the rest of the page.
- **Live-verified** (not just asserted in source): with the flag forced on
  via debug override and no backend available (see Known Limitations), World
  Stage's `/api/adventure/bootstrap` fetch genuinely 404'd, and the console
  showed the exact expected sequence: `world_stage CRITICAL: adventure data
  fetch failed, recovering to legacy` → `critical failure — recovering to
  legacy Adventure` → legacy `#skill-map` became visible again, `#e9-adventure-shell`
  hidden again. Zero uncaught pageerror. Non-critical components (Top HUD,
  Right Cards' 4 cards) each logged their own independent failure without
  affecting anything else.

## Adventure Start adapter

`window.E9.startAdventureFromE9(zoneKey)` (in `shell.js`) calls the existing
global `startAdventureStage(zoneKey)` directly — no reimplementation of
zone-entry logic. World Stage's zone tiles call this adapter on click (only
for non-locked zones). Because the standalone test environment has no
backend, `startAdventureStage` itself could not be exercised end-to-end this
sprint (see Known Limitations) — the adapter's own "does the legacy function
exist, call it, else throw a controlled error" logic was verified by source
review and is exactly the pattern in the task book's own example.

## i18n contract followed

- Fixed order enforced in `component_loader.js`: fetch → inject →
  `I18n.apply()` → dispatch `component-loaded` → component init (verified by
  a dedicated contract test asserting this exact code ordering).
- `I18n.apply()` is a full-document rescan (this repo has no scoped/subtree
  i18n API) — confirmed as the established pattern already used by
  `index.html`/`hero.html` after inserting new content, not a workaround.
- All ~28 new `e9.*` keys have both `en` and `zh` entries (contract-tested).
- Loading/empty/error states are translatable (`e9.top_hud.loading/error`,
  `e9.right_cards.loading/empty/error`) — no literal English/Chinese string
  is hardcoded as a component's only text.
- Runtime language switch: reuses the existing `window.I18n.setLang()` →
  `apply()` → `window.onLangChange` mechanism as-is. No new `dict`, no new
  `setLang`, no new `localStorage` key anywhere in `js/e9/*` (contract-tested).

## Feature flag & debug gate

- `window.GO_ODYSSEY_FEATURES` (unset in production) merges over
  `PRODUCTION_FLAGS` (all `false`).
- Query-param override requires **both** an explicit `?E9_DEBUG=1` **and** a
  debug-style hostname (`localhost`/`127.0.0.1`/`[::1]`/`*.local`/`*.test`) —
  a bare query param on the production hostname is inert (live-verified in
  E9.1A1's review, unchanged this sprint).
- **Live-verified this sprint**: navigating to `/` with no query params → E9
  shell stayed hidden, `#skill-map` stayed visible, and the network log
  confirmed **zero** `/components/adventure/*` requests were made after that
  navigation (the flag-off code path returns before any `mountSlot()` call).

## RWD

Tested against the derived 8-viewport matrix (see above) on the **flag-OFF
default state** of the real `index.html` — confirmed **zero horizontal
overflow** (`document.documentElement.scrollWidth === window.innerWidth`) at
all 8 widths: 1440, 1366, 1280, 1024, 768, 640, 480, 320. Legacy Adventure Map
is unaffected by the new (hidden, zero-height when `hidden`) E9 markup at
every width.

The E9 shell's **own** internal 3-column → 1-column collapse (nav / stage /
cards) was verified in E9.1A1's review at 1280×800 / 768×1024 / 375×812 and is
unchanged this sprint (`css/e9/rwd.css` breakpoints at 1024px/600px are
untouched except for the skeleton min-height additions below). Full 8-viewport
re-verification of the E9 shell's *loaded* (non-recovered) internal layout
could not be completed this sprint — see Known Limitations.

### Skeleton layout shift (PR #78 fix)

Replaced the single fixed 48px skeleton height with per-slot,
per-breakpoint CSS custom properties (`--e9-skeleton-min-height`):
top_hud/bottom_dock stay short (48px desktop / 64px mobile) at every
breakpoint; the three stretched main-body slots (left-nav/world-stage/
right-cards) get 340px on desktop, 180px at ≤1024px (tablet, once the layout
collapses to a column and no longer stretches to a shared tall height), and
140px at ≤600px (mobile). This is a placeholder-appropriate approximation
("不追求最終美術,只避免明顯跳動"), not final art.

## Service Worker

- Old `VERSION`: `v177-sgf-fe-hotfix1a-node-parser`
- New `VERSION`: `v178-e9-1a2-adventure-shell-integration`
- `git diff sw.js` touches exactly the `VERSION` line — no other change.
- E9 `.js`/`.css` fall under the existing generic cache-first branch
  (`url.pathname.endsWith('.js') || .endsWith('.css')`); new `.html`
  fragments fall under the existing HTML network-first fallback. Neither
  required a new branch in the fetch handler.

## Static routes (app.py)

Three new routes, each: extension-allowlisted (`abort(404)` on any other
extension), delegates to the existing `_serve_live_static_or_baked_subpath`
helper (inherits its traversal/hidden-file/absolute-path protection — no new
security logic written), mirrors the already-reviewed `/assets/`/`/icons/`
pattern exactly:
```
/js/e9/<path:subpath>            -> only *.js
/css/e9/<path:subpath>            -> only *.css
/components/adventure/<path:subpath> -> only *.html
```

## Tests

- `tests/test_e9_adventure_shell_foundation.py` — 37 passed (one test updated:
  the E9.1A1-era assertion that `index.html` did **not** yet reference the
  shell is obsolete by design now that E9.1A2 has landed that wiring; it now
  asserts the wiring **is** present instead).
- `tests/test_e9_adventure_shell_integration.py` (new) — 54 passed. Covers
  integration (legacy preserved, slots present, flag defaults, flag-off
  no-fetch ordering, critical recovery, CTA adapter, no-duplicate-init
  guards), static routes (extension allowlist + helper reuse), i18n (key
  coverage in both languages, apply-before-dispatch ordering, no second
  translation dictionary, translatable loading/empty/error states), SW
  (version bumped, cache-strategy functions unchanged, diff-is-version-only
  guard), and data (no Stars/HP/SP fabrication, no Guild Pass anywhere, no
  misleading `0 HP`/`0 SP` fallback strings, real endpoints only).
- Related tests (premium weekly ×2, xp hud guard): 6 passed, unaffected.
- `tests/deployment/` full suite: 137 passed, **2 failed** — see next
  section, this is expected and was resolved with the owner's explicit
  sign-off, not silently worked around.

### Why no Flask `test_client()` was used

No existing test file in this repo imports `app.py` and boots it — `db.py`'s
`DATABASE_URL` defaults to a Postgres DSN (`postgresql://go:go@postgres:5432/go_odyssey`)
that only resolves inside the project's Docker network, and this environment
has no local Postgres available. Booting the real app to hit the 3 new
routes with live HTTP requests was not attempted; doing so would have
introduced a test dependency (a live Postgres instance) that no other test in
this ~150-test suite requires. The 3 new routes are instead verified via
source-level contract tests (route exists, extension check present, delegates
to the reviewed helper) — consistent with how every other route-adjacent test
in this repo already works.

### Deployment governance: `deploy/runtime-source-provenance.json` updated

Editing `index.html`, `sw.js`, and `i18n.js` (all explicitly authorized for
this sprint) caused 2 pre-existing tests in
`tests/deployment/test_runtime_dependency_provenance.py` to fail:
`test_working_tree_matches_recorded_content_sha256` and
`test_working_tree_matches_recorded_source_commit_blob`. This manifest
records an exact git blob/SHA-256 fingerprint per file, apparently built as
an anti-drift mechanism after this project's prior production fork/overwrite
incidents (ADR-0001). Confirmed the manifest **exactly matched** the base
commit (`2026f47c2`) before any of this sprint's edits — the drift is caused
entirely by this sprint's own legitimate, reviewed changes.

`deploy/` was not in this sprint's explicit allowed-to-modify list, so this
was flagged to the owner rather than silently patched. **Owner decision:
update the 3 affected manifest entries** (`index.html`, `sw.js`, `i18n.js`)
to record this sprint's actual new content hash and commit, since this is a
legitimate, reviewed content change, not drift to paper over. See the commit
that updates `deploy/runtime-source-provenance.json` for the new recorded
values.

## Regression checks

- `python -m py_compile app.py` — OK
- `node --check js/e9/*.js` (8 files) — all OK
- `node --check i18n.js` — OK
- `git diff --check` — clean

## Browser verification — what was and wasn't tested

**Verified live** (Browser pane, `python -m http.server` per this repo's
existing `static` preview config):
- Flag OFF: legacy visible, E9 hidden with `aria-hidden="true"`, zero
  `/components/adventure/*` requests after page load.
- Flag ON (debug override): E9 shell attempted to mount; World Stage's real
  data fetch genuinely failed (no backend available) and correctly triggered
  full critical-failure recovery back to legacy, with zero uncaught
  pageerror and each non-critical component logging its own isolated
  failure.
- 8-viewport horizontal-overflow check on the flag-OFF legacy page: clean at
  all 8 widths.
- Debug-gate logic: `?E9_DEBUG=1&...` on `localhost` takes effect; the same
  params without `E9_DEBUG=1` are inert (re-confirmed from E9.1A1, unchanged
  logic).

**Not verified live, and reported honestly rather than assumed** (all
require a running backend this environment does not have — no local
Postgres):
- The "happy path" with real data: World Stage rendering real zone tiles,
  Top HUD showing a real name/level/coins, Right Cards showing real
  counts, and clicking a zone tile successfully invoking
  `startAdventureStage()` end-to-end.
- Full 8-viewport RWD check of the E9 shell's *loaded* (not recovered-to-
  legacy) internal layout — only 3 of the 8 (1280×800/768×1024/375×812) were
  verified in E9.1A1 against the standalone demo; the CSS rules for the
  other 5 widths were reviewed but not pixel-verified with real content.
- i18n runtime language switch verified structurally (contract tests) and
  via the pre-existing `onLangChange` mechanism, but not visually confirmed
  side-by-side in zh-TW vs. English with real E9 content on screen, since
  that content never got past the loading state without a backend.
- **Safari**: not tested. This environment has no Windows-compatible Safari
  to test in. A static WebKit-compatibility read of the CSS/JS used
  (`fetch`, `Promise.all`, `CustomEvent`, CSS custom properties, `flex-direction`,
  `:focus-visible`) shows nothing Safari-incompatible, but this is a static
  read, not a real test, and is reported as such rather than claimed as a
  pass.

These gaps are exactly why `e9Shell` defaults to `false` and why this PR does
not flip it — the next real verification pass (ideally against a staging
backend) should complete the happy-path and full-RWD checks before any
Stage C (flag-on) release is considered.

## Scope discipline

No modification to: Adventure progression logic, Battle/judging, Questions
data, Hero ownership/equipment logic, any new currency/reward rule, Avatar/
Monster/Boss art, Backpack, Go Gear, Daily Supply. No new API, no DB schema
change, no deployment.

## Status

```
E9.1A2: READY FOR REVIEW
```

Do not deploy. Do not flip `e9Shell` to `true` in production. Do not begin
E9.1B until this PR is reviewed and merged.
