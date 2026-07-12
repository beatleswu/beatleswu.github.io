# E9.1B — Real Data Contract and Dormant Runtime Wiring

```
Sprint: E9.1B
Branch: feature/e9-1b-real-data-contract
Base: master @ 9d7cb09132b57a5e60ec98ca746f73ab50b3e36f
Production mutation target: dormant code only -- e9Shell stays false
```

## Objective

Formalize the data contract behind the five E9.1A adventure components and
introduce an explicit adapter layer (`js/e9/adapters/`) as the single
source of truth for canonical runtime data, replacing the inline
`fetch().then()` parsing each component did directly in E9.1A/E9.1A2.

This sprint does **not** flip `e9Shell` to `true`. It ships dormant,
activation-ready code, verified under the approved debug environment only.

## Canonical sources verified against `app.py` (not guessed from docs)

Every source below was confirmed by reading the actual Flask route handler
in `app.py`, not assumed from the E9.1A/E9.1A2 planning docs:

| Endpoint | Handler (`app.py`) | Real fields used |
|---|---|---|
| `GET /api/skills/profile` | `skills_profile()` (line ~11785) | `display_name` (string), `rank_level` (string, e.g. `'LV12'`) |
| `GET /api/user/coins` | `get_user_coins()` (line ~16198) | `coins` (int) |
| `GET /api/adventure/bootstrap` | `adventure_bootstrap()` (line ~8511) | `zones[]`, each `{key, name, status, stars, boss:{available}}` via `_adventure_map_state_from_zones()` |
| `GET /api/daily-challenge/today` | `dc_today()` (line ~11060) | `user_submitted` (bool), `user_correct` (bool\|null) |
| `GET /api/srs/due` | `srs_due()` (line ~9940) | `count` (int) |
| `GET /api/mistakes/stats` | `mistake_stats()` (line ~10975) | `total` (int) |

**A real bug found and fixed during this sprint**: `rank_level` is a string
already prefixed with `LV` (e.g. `'LV12'`), but the pre-E9.1B `top_hud.js`
rendered it directly next to a `"Lv."` label, producing a doubled
`"Lv. LV12"`. The new `PlayerState` adapter (`js/e9/adapters/player_state.js`)
extracts the numeric level via regex so the rendered text is `"Lv. 12"`.

## Data Contract Table

| Component | UI field | Canonical source | Runtime owner | Data shape | Nullable? | Empty state | Error state | Refresh trigger | Legacy dependency | Activation status |
|---|---|---|---|---|---|---|---|---|---|---|
| Top HUD | Player name | `GET /api/skills/profile` → `display_name` | `js/e9/adapters/player_state.js` | REAL — string | yes (missing → error text, never a fabricated name) | n/a (name is never "empty", only present/error) | `e9.top_hud.error` / `e9.top_hud.unauthorized` | component mount only (no polling) | none — same endpoint the legacy `hero.html`/skills pages already call | dormant (debug only) |
| Top HUD | Level | `GET /api/skills/profile` → `rank_level` (numeric part extracted) | `js/e9/adapters/player_state.js` | DERIVED — integer, parsed from a REAL string field | yes (missing/malformed → field omitted, `#top-hud-level` stays hidden) | field hidden, not a fake `0` | same element hidden on error (no separate error text for this one field) | component mount only | none | dormant |
| Top HUD | Coins | `GET /api/user/coins` → `coins` | `js/e9/adapters/player_state.js` | REAL — integer, `0` is valid | yes (missing/negative/NaN → field omitted) | field hidden | same element hidden on error | component mount only | none | dormant |
| Top HUD | Stars (global) | **UNAVAILABLE** | — | — | — | — | — | — | — | **not rendered** — stars only exist per-zone (0-3), summing them would be DERIVED-but-fabricated (no canonical "global stars" concept exists) |
| Top HUD | HP / SP | **UNAVAILABLE** | — | — | — | — | — | — | — | **not rendered** — only transient in-battle DOM state exists, no persistence API |
| World Stage | Zone list | `GET /api/adventure/bootstrap` → `zones[]` | `js/e9/adapters/adventure_state.js` | REAL — array | empty array is a **critical** condition (falls back to legacy), not an empty-state UI | n/a — see Legacy fallback | triggers full `recoverToLegacy()` after one retry | component mount, one automatic retry on recoverable failure | same endpoint as legacy Adventure Map | dormant |
| World Stage | Zone name | `zones[].name` | adapter | REAL — string | zone dropped if missing (never rendered with a placeholder name) | — | — | — | same | dormant |
| World Stage | Zone status (locked/unlocked/completed/skipped) | `zones[].status` | adapter | REAL — enum, validated against a fixed allow-list | zone dropped if not one of the 4 known values | — | — | — | same | dormant |
| World Stage | Zone stars (0-3) | `zones[].stars` | adapter | REAL — integer, clamped to [0,3] | defaults to `0` only when the field itself is a valid non-negative number rounded/clamped — never fabricated for a dropped zone | `0` is valid (unstarred zone) | — | — | same | dormant |
| World Stage | Boss available | `zones[].boss.available` | adapter | REAL — boolean | `false` if missing (never assumed `true`) | — | — | — | same | dormant |
| Right Cards | Daily Challenge status | `GET /api/daily-challenge/today` → `user_submitted` | `js/e9/adapters/activity_state.js` | REAL — boolean | — | n/a (always either submitted or available) | `e9.right_cards.error` / `unauthorized` | component mount only | same endpoint as legacy daily challenge page | dormant |
| Right Cards | Boss Progress | `GET /api/adventure/bootstrap` → `zones[].status==='completed'` count / total | adapter (`normalizeBossProgress`) | DERIVED — counted live from REAL zones, never persisted separately | `total===0` → empty state | `e9.right_cards.empty` | `e9.right_cards.error` / `unauthorized` | component mount only | same | dormant |
| Right Cards | SRS Due | `GET /api/srs/due` → `count` | adapter | REAL — integer, `0` is valid | missing/negative → unavailable (error state, not silently `0`) | `count===0` → `e9.right_cards.empty` | `e9.right_cards.error` / `unauthorized` | component mount only | same endpoint as legacy SRS review | dormant |
| Right Cards | Weakness Summary | `GET /api/mistakes/stats` → `total` | adapter | REAL — integer, `0` is valid | missing/negative → unavailable | `total===0` → `e9.right_cards.empty` | `e9.right_cards.error` / `unauthorized` | component mount only | same endpoint as legacy mistakes page | dormant |
| Right Cards | Guild Pass | **UNAVAILABLE** | — | — | — | — | — | — | — | **not rendered, not stubbed as "Coming Soon"** — confirmed in the E9.1A0 audit (Phase F) that no Guild Pass system exists anywhere in this codebase |
| Left Nav / Bottom Dock | Navigation links | static hrefs to existing real routes (`/hero`, `/community`, `/badges`, `/profile/<username>` via `GET /api/auth/me`) | none (no data adapter needed — pure navigation) | REAL | n/a | n/a | n/a | n/a | routes are the same ones the legacy nav already uses | dormant |

## What stays UNAVAILABLE (confirmed, not assumed)

Per the audit already performed in E9.1A0/E9.1A2 and re-confirmed this
sprint by reading `app.py`/`db.py` directly:

- **Global Stars total** — no such field or aggregate exists anywhere; only
  per-zone `stars` (0-3) exists.
- **Persistent HP/SP** — no such column in `user_stats` or any other table;
  HP/SP only exist as transient in-battle DOM state with no API.
- **Guild Pass / Guild membership / Guild quests / Guild rewards** — no
  `guild` table, route, or field anywhere in `app.py`/`db.py`.
- **Fake stamina/energy timers, fake premium currency, fake unlocked zones,
  fake achievements** — none exist; `Badges`/`achievements` ARE real
  (`/api/badges/*`) but are not part of this sprint's five components'
  scope (Bottom Dock links to the real `/badges` page instead of
  duplicating badge data inline).

None of the above are rendered as `0`, `—`, `N/A`, `"Coming Soon"`, or a
"Locked" placeholder — per the contract, a non-existent data model is
simply never rendered, full stop.

## REAL / DERIVED / OPTIONAL / UNAVAILABLE definitions

- **REAL**: provided directly by an existing canonical source (a real
  Flask route reading real DB/session state), used as-is.
- **DERIVED**: computed at render time purely from REAL data already in
  hand (e.g. counting `completed` zones from the zones array) — never
  persisted as a second copy of state.
- **OPTIONAL**: the feature/field is real, but a given player may simply
  have no data for it yet (e.g. zero SRS cards due) — renders a translated
  empty state, not an error.
- **UNAVAILABLE**: no canonical data model exists for this at all — the
  field or component is not rendered, not stubbed, not faked.

## Adapter architecture (single source of truth)

```
js/e9/adapters/
  player_state.js     -- Top HUD: /api/skills/profile + /api/user/coins
  adventure_state.js  -- World Stage: /api/adventure/bootstrap
  activity_state.js   -- Right Cards: daily-challenge/today, adventure/bootstrap,
                          srs/due, mistakes/stats
```

Each adapter exposes:
- One or more **pure normalization functions** (`normalizeProfile`,
  `normalizeZone`, `normalizeDailyChallenge`, etc.) that take a raw parsed
  JSON body and return a validated view model, or throw on a structurally
  invalid response. These are unit-testable in isolation (see
  `tests/e9_node_tests/`) without a network or DOM.
- One or more **fetch functions** (`fetchPlayerState`, `fetchAdventureState`,
  `fetchDailyChallenge`, etc.) that perform the real `fetch()` call,
  classify HTTP failures into `'unauthorized'` (401/403) or `'error'`
  (everything else) or `'network'` (fetch itself threw), and return a
  tagged result object: `{ok: true, data: ...}` or `{ok: false, kind, status}`.

Components (`top_hud.js`, `right_cards.js`, `world_stage.js`) call the
adapter's fetch function, branch on `result.ok`/`result.kind`, and render —
they never parse a raw HTTP response themselves anymore, and never persist
a second copy of the data (no adapter-level cache, no localStorage, no
module-level state surviving across page loads — every mount re-reads the
canonical source fresh).

`left_nav.js` and `bottom_dock.js` need no adapter (pure navigation to
existing real routes).

## Event contract

| Event | Producer | Consumer | Payload | Notes |
|---|---|---|---|---|
| `e9:component-loaded` | `component_loader.js` | each component's own init listener | `{component, root}` | pre-existing (E9.1A), unchanged |
| `e9:zone-selected` | `world_stage.js` (zone tile click/Enter/Space) | none required (observability hook) | `{zoneKey, status}` | new this sprint; dispatched before invoking the adapter action, bubbles |
| `e9:refresh-requested` | `world_stage.js` (automatic single retry on a recoverable fetch failure) | none required (observability hook) | `{component, reason}` | new this sprint |
| (implicit) `window.E9.recoverToLegacy(reason)` | `world_stage.js` / `shell.js` | `shell.js` | `Error` | pre-existing (E9.1A2), unchanged; still the only path that hides the E9 shell and shows legacy |

Zone-tile clicks are guarded against duplicate rapid-fire submission the
same way they always were: `startAdventureStage()` (the legacy function
being adapted to) already owns its own idempotency; this sprint does not
duplicate that logic.

## Feature flag contract — unchanged

`PRODUCTION_FLAGS` in `js/e9/feature_flags.js` remain all `false`. The
debug override still requires an approved debug hostname **and**
`E9_DEBUG=1` **and** an explicit per-flag override — no new override
mechanism (query-only, localStorage, cookie, hash) was added this sprint.

## Out of scope (confirmed unchanged)

No DB schema change, no migration, no `questions.json` change, no new
write-capable API route. All six data-fetching calls this sprint uses
(`/api/skills/profile`, `/api/user/coins`, `/api/adventure/bootstrap`,
`/api/daily-challenge/today`, `/api/srs/due`, `/api/mistakes/stats`) are
pre-existing, already-authenticated, read-only GET routes reused as-is.
