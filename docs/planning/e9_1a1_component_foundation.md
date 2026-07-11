# E9.1A1 — Adventure Shell Component Architecture Foundation

```
Sprint: E9.1A1 (first of two PRs — E9.1A2 does the real index.html integration)
Branch: feature/e9-1a1-component-foundation
Base: master
Production mutation: NONE
Runtime behavior changes: NONE (index.html and app.py are untouched)
Deployment: NONE
```

## Decisions locked in before this sprint

- **Architecture**: frontend fragment assembly (`fetch()` + `innerHTML`), not Jinja,
  not React/Vue. This repo has zero `render_template()` calls — `index.html` and
  friends are served as static files via `send_from_directory`/`send_file`.
- **JS test framework**: not introduced in E9.1A1. Verification is two layers:
  1. Python/pytest **contract tests** (`tests/test_e9_adventure_shell_foundation.py`)
     that assert structural invariants in the JS/HTML source (flag defaults, fail-safe
     patterns, slot↔fragment mapping, versioning, scope boundary).
  2. A **manual browser checklist** (below) for actual runtime behavior, since this
     repo has no Jest/Mocha/Vitest and E9.1A1 does not add one.
- **Feature rollout**: Stage A (standalone demo) → Stage B (integrated into
  index.html, `e9Shell` flag stays `false`) → Stage C (flag flips to `true` in a
  real release, after UI/RWD/Avatar/Monster/regression work). No production gray
  rollout, no player-facing query-param toggle.
- **Sprint split**: E9.1A1 (this PR) = component loader, flags, fail-safe fallback,
  stable slots, fragment versioning, CSS preload + skeleton, pytest contracts,
  standalone demo, SW version-bump contract (documented, not yet exercised).
  E9.1A2 (separate PR, after this merges) = wiring into the real `index.html`
  behind the flag, legacy fallback, DOM/visual parity, Adventure Start regression,
  RWD screenshots on the real page, SW cache behavior on the real page.

## What's in this PR

```
components/adventure/
    top_hud.html
    left_nav.html
    right_cards.html
    bottom_dock.html
    world_stage.html
js/e9/
    feature_flags.js
    component_loader.js
    shell.js
    top_hud.js
    left_nav.js
    right_cards.js
    bottom_dock.js
    world_stage.js
css/e9/
    shell.css
    top_hud.css
    navigation.css
    cards.css
    world_stage.css
    rwd.css
e9_adventure_shell_spike.html   (Stage A standalone demo)
tests/test_e9_adventure_shell_foundation.py
```

`index.html` and `app.py` are **not** modified — verified by
`test_legacy_adventure_map_section_is_untouched` and
`test_index_html_does_not_yet_reference_e9_shell` in the contract test file.

## Feature flag contract

- Source of truth: `window.GO_ODYSSEY_FEATURES` (static config), merged over
  `PRODUCTION_FLAGS` defaults (all `false`) in `js/e9/feature_flags.js`.
- Query-param overrides (`?E9_DEBUG=1&e9RightCards=0`) only apply when **both**
  `E9_DEBUG=1` is present **and** `location.hostname` matches a debug-style host
  (`localhost`, `127.0.0.1`, `[::1]`, `*.local`, `*.test`). A bare query param on
  a production hostname is inert — verified in the browser (see checklist) and
  by `test_query_override_requires_debug_environment_and_explicit_opt_in`.

## Service Worker version contract

`sw.js` caches `*.js`/`*.css` **cache-first** and HTML pages/fragments
**network-first** (confirmed by reading `sw.js` directly, not assumed). This
means: **any future change to `js/e9/*.js` or `css/e9/*.css` content must ship
together with a `sw.js` `VERSION` bump**, or returning users can be served a
stale cached copy indefinitely. This PR does not touch `sw.js` (no runtime
behavior change), and `feature_flags.js`'s own `ASSET_VERSION` constant plus a
code comment document this coupling for whoever ships the next E9 asset change.
Fragment fetches already append `?v=<ASSET_VERSION>` (see `component_loader.js`
`versionedUrl()`).

## Manual browser verification checklist

Run against `e9_adventure_shell_spike.html` via the repo's existing `static`
preview server (`.claude/launch.json`), Browser pane tooling:

| # | Check | Result |
|---|---|---|
| 1 | Legacy layout unchanged when flag off | N/A this PR — index.html untouched; re-verify in E9.1A2 |
| 2 | All 5 components load with `e9Shell`+all sub-flags on | PASS — top_hud, left_nav, world_stage (10 real zones), right_cards, bottom_dock all rendered |
| 3 | Single fragment 404 doesn't affect the rest | PASS — renamed `right_cards.html` away, reloaded: only that slot showed a `role="status"` "unavailable" fallback; other 4 components rendered normally, console showed a caught `console.error`, no uncaught pageerror |
| 4 | No uncaught browser pageerror | PASS — console only shows expected `console.error` calls from the fail-safe catch blocks |
| 5 | No duplicate event binding | PASS — called `E9.loadComponent('top_hud', root, url)` a second time via devtools on an already-loaded root: resolved `true` immediately, DOM unchanged, no re-fetch, no re-dispatch (idempotency guard on `data-e9-loaded`) |
| 6 | i18n | N/A this PR — fragments carry no `data-i18n` yet (placeholder-only), re-verify in E9.1A2 when real content/i18n is wired |
| 7 | Desktop/iPad/Mobile responsive check | PASS — 1280×800 keeps the 3-column row body; 768×1024 and 375×812 both collapse `.e9-body` to `flex-direction: column` per `css/e9/rwd.css` |
| 8 | Existing Adventure Start still operable | N/A this PR — legacy page untouched; re-verify in E9.1A2 |
| 9 | Query override gating | PASS — `?E9_DEBUG=1&e9RightCards=0` on `localhost` flips the flag; `?e9RightCards=0` alone (no `E9_DEBUG=1`) is ignored, flag stays at its base value |

Items marked N/A are inherently out of scope for a PR that doesn't touch
`index.html` — they become real acceptance criteria for **E9.1A2**, not
skipped requirements.

## Automated contract tests

`python -m pytest tests/test_e9_adventure_shell_foundation.py -v` — 31 passed.
Covers: fragment existence, stable root IDs (Rule #6) and uniqueness, slot↔fragment
mapping completeness, production flag defaults, debug-gating logic, loader
fail-safe patterns (`response.ok`, `catch`, fallback render, idempotency),
shell init try/catch, fragment URL versioning, `ASSET_VERSION` presence and its
documented `sw.js` coupling, and the E9.1A1 scope boundary (`index.html`/`app.py`
untouched).

## Not in scope for E9.1A1 (per sprint definition)

- No modification to `index.html` or `app.py`
- No porting of existing Adventure functionality/data
- No new API, no DB changes
- No deployment
- No Avatar/Monster art or animation
- No Backpack logic

## Status

```
E9.1A1: READY FOR REVIEW
```

Do not deploy. E9.1A2 (real `index.html` integration, legacy fallback, DOM/visual
parity, full regression) starts only after this PR merges.
