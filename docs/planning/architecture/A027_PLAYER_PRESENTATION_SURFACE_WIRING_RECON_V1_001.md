# A027 Player Presentation Surface Wiring Recon V1

## Decision summary

This is a read-only recon of exactly four current frontend presentation
families. The current implementation has no `PLAYER_PRESENTATION_API_V1`
route wiring. The four surfaces are inline HTML/JavaScript consumers with
several overlapping server reads and a small number of presentation caches.

The safe adoption boundary is narrow:

- Hero identity, XP/level/rank, character presentation, one active Spirit
  display, owned/equipped functional-equipment display, and pure cosmetic
  display are candidates for an A026 adapter.
- World/Zone, Adventure/Quest, encounter/battle, Shop, Premium, consumable,
  material, pet-inventory and mutation state remain outside Player
  Presentation.
- Current `hero_combat_gear_v1` is a legacy visual cache. It must not become
  authority during migration.
- Effect-bearing appearances remain functional/effect presentation and must
  never be promoted to pure cosmetics by an adapter.

Recommended first implementation after the E026 Owner gate:

`HERO_OVERVIEW_READ_ONLY_OVERVIEW_FRAGMENT`

That means only the safe overview fragment, not the Hero equipment controls,
effect arithmetic, Premium state, milestones or Spirit mutations.

## Provenance and boundary

| Field | Value |
|---|---|
| Task | `A027_PLAYER_PRESENTATION_SURFACE_WIRING_RECON_V1_001` |
| Audited master | `b75308d44806bb7c2e2b131a73ba06a71c188b3c` |
| Accepted A025-R1 input | `d1401925952181b02da75a60e87c6bb851909125` |
| Accepted A026 input | `a3808a095054856d23db5f0168c6c359976a210d` |
| E026 | In progress; route acceptance and merge are not assumed |
| Runtime/frontend/app.py changes | None |
| Scope | Four audited presentation families only |

A026 is treated as a conceptual accepted input, not as a claim that its
files are ancestors of the audited master. The future route is recorded as
`PLAYER_PRESENTATION_API_V1_ENDPOINT_PENDING_E026`.

The machine-readable source matrix contains the full per-surface evidence:
[a027_player_presentation_surface_source_matrix.json](a027_player_presentation_surface_source_matrix.json).
The proposed adoption sequence is in:
[a027_player_presentation_frontend_migration_order.json](a027_player_presentation_frontend_migration_order.json).

## Current route and file map

| Surface | Current route(s) | Current file | Auth | Primary render path |
|---|---|---|---|---|
| `HERO_OVERVIEW` | `/hero`, `/skills`, `/hero?tab=overview` | `hero.html` | Yes | `renderHeroOverview()` and `initPage()` |
| `ADVENTURE_PLAYER_IDENTITY` | `/`, `/?e9=1` (query form), Adventure resume query on `/` | `index.html` | Authenticated `/` serves `index.html`; unauthenticated `/` serves landing | `loadPlayerAvatar()`, `applyHeroCombatAvatarToIndex()` |
| `BACKPACK_EQUIPMENT_PRESENTATION` | `/inventory`, `/inventory?e10=1`, equipment focus query | `inventory.html` | Yes | `loadFunctionalEquipment()` plus `loadBackpack()` |
| `WARDROBE_PURE_COSMETIC_PRESENTATION` | `/hero#appearance`, `/skills#appearance`, `/hero?tab=appearance` | `hero.html` | Yes | `renderWardrobeSlots()`, `renderCosmeticProjection()` |

Route evidence is in `app.py`: authenticated `/` serves `index.html`
(`app.py:20617-20621`), `/inventory` serves `inventory.html`
(`app.py:21370-21376`), and `/skills` plus `/hero` both serve `hero.html`
(`app.py:23928-23931`). The `/item-journal` route exists but is outside the
four-family scope and is not counted here.

The Adventure query `/?e9=1` is a shell/rollout query shape, not a separate
server route. E10/E9 shell ownership is presentation/runtime shell state and
must not be folded into A026.

## 1. HERO_OVERVIEW

### Current DOM and render contract

The main character and summary DOM is in `hero.html:1840-1867` and the
overview/equipment projection containers are referenced by
`hero.html:4780-4817`. The relevant render helpers are:

- `renderHeroOverview()` (`hero.html:4780-4818`)
- `hydrateAuthoritativeHeroPresentation()` (`hero.html:4819-4862`)
- `renderFunctionalEquipmentProjection()` (`hero.html:4068-4076`)
- `renderCosmeticProjection()` (`hero.html:4078-4105`)
- `renderWardrobeSlots()` / `renderWardrobeEquipmentProjections()`
- `loadPetStatus()` and `loadNavAvatar()`

### Current sources

`renderHeroOverview()` reads `_profileData`, `_combatGear`,
`_wardrobeItems` and `_petState`. It currently displays identity, rank,
XP, title, Spirit name, equipment names and a calculated bonus summary
(`hero.html:4780-4817`). This is not one safe snapshot: the helper computes
effects from local `COMBAT_GEAR`, wardrobe effect objects and
`_petState.bonus.current_pct`.

The server reads are:

- `/api/skills/profile` for display identity, titles, level/XP/rank,
  wardrobe, skin fields and legacy aggregate fields
  (`hero.html:4864-4870`, `app.py:17273-17481`). The backend response also
  contains `combat_stats`, `active_effects`, milestones including
  `total_correct`/`max_streak`, and Premium state. Those fields require
  narrowing, not direct transport reuse.
- `/api/player/appearance` for the server `character_key`, equipped
  appearance IDs and character presentation source
  (`hero.html:4827-4839`, `app.py:16941-16999`).
- `/api/player/inventory` for functional equipment rows and equipped state
  (`hero.html:4827-4848`, `app.py:16856-16885`).
- `/api/pet/status` for the active Spirit/pet projection
  (`hero.html:2824-2828`, `hero.html:4803-4815`, `app.py:15479-15516`).
- `/api/auth/me` for shared navigation identity
  (`hero.html:5057-5076`, `app.py:8837-8910`).

### A026 fit

| Fact | Fit | Reason |
|---|---|---|
| Hero/character identity | Thin adapter | Current page splits identity between profile, auth and appearance. |
| `character_key` | Direct candidate | Server appearance already exposes a presentation-safe key. |
| XP / level / Go rank | Direct candidate | A026 supports these after field narrowing. |
| Persistent HP | Not currently consumed | No inspected Hero overview DOM currently consumes a persistent HP field. |
| Owned/equipped equipment display | Thin adapter | Read projection is safe; local catalog/effects are not. |
| Active Spirit identity | Thin adapter | Use one active presentation projection; retain Spirit authority. |
| Pure cosmetics | Thin adapter | Only presentation-only owned/selected items. |
| Bonus/effect summary | Do not migrate | Current calculation crosses combat/effect and Spirit state boundaries. |
| Premium status | Separate authority | Premium is explicitly outside A026. |
| Milestones/learning/streak | Do not migrate | A025-R1/A026 exclude these facts. |
| ELO | Separate authority | Not part of A026 Player Presentation scope. |

### Local and in-memory state

`hero_combat_gear_v1` is read at `hero.html:3757-3769` and written by
selection paths at `hero.html:4262-4282`. The file comment explicitly calls
it a legacy style-control cache and says it is not character authority.
`_profileData`, `_combatGear`, `_wardrobeItems`, `_petState` and
`_functionalEquipmentItems` remain duplicated in-memory sources.

Disposition: keep the cache readable during fallback; retire it only after a
server-backed presentation route has proven parity. Never use it to override
server `character_key`.

## 2. ADVENTURE_PLAYER_IDENTITY

### Current DOM and render contract

The player identity card is `index.html:7416-7441`:

- `.home-player-card`
- `#home-player-figure`, `#home-player-base`, layered gear and
  `#home-player-pet-layer`
- `#home-player-name`, `#home-player-title`, `#home-player-handle`
- `#home-player-lv`, `#home-player-rank`, `#home-player-elo`, `#home-player-xp`

The relevant helpers are `loadPlayerAvatar()` and
`applyHeroCombatAvatarToIndex()` (`index.html:8100-8184`).
`loadPlayerAvatar()` fills the card from `/api/auth/me`,
`/api/player/appearance`, `/api/skills/profile` and `/api/pet/status`
(`index.html:8165-8225`).

### What must remain World/Adventure authority

`renderAdventureInfoPanel()` and `renderAdventureMap()` use
`_adventureProgress`, `adventureActiveZone()`, selected-zone state and
Adventure bootstrap data (`index.html:13733-13907`). The bootstrap is loaded
from `/api/adventure/bootstrap` (`index.html:14274-14288`,
`app.py:11869-11887`). It owns zones, selected/progression state, stars,
quest detail, CTA and Lord/Boss readiness.

The selected Zone cache `adventure_selected_stage_v1` is read/written at
`index.html:13130-13142` and must remain outside A026. The E9/E10 shell state
is also separate: `window.__GO_WORLD_PRESENTATION_STATE__`,
`window.__GO_ADVENTURE_SHELL_OWNER__`, `window.__GO_E9_ACTIVE_SHELL__` and
server rollout flags are managed at `index.html:20083-20225`.

### A026 fit

| Fact | Fit | Boundary |
|---|---|---|
| Player/Hero identity | Thin adapter | Replace only the card read. |
| Character presentation | Thin adapter | Keep current art/fallback and server key validation. |
| XP / level / rank | Direct candidate | No World semantics implied. |
| Active Spirit identity | Thin adapter | Display only; no Spirit effect. |
| Selected Zone | Separate authority | World state, not Player state. |
| Progression Zone/unlocks/stars | Separate authority | Adventure bootstrap remains source. |
| Quest/Boss readiness | Separate authority | Never add to Player snapshot. |
| Encounter/battle/replay | Do not migrate | Battle/SRS/Map Battle state is separate. |
| E9/E10 shell ownership | Do not migrate | Technical shell state, not Hero presentation. |

The lowest-risk adoption is a bounded identity-card adapter after the Hero
overview pattern is proven. It must not rerender or reinitialize the map.

## 3. BACKPACK_EQUIPMENT_PRESENTATION

### Current DOM and render contract

`inventory.html:479-556` contains both functional-equipment and general
Backpack regions. Functional equipment uses:

- `#functional-equipment-filters`
- `#functional-equipment-grid`
- `#functional-equipment-detail`
- `#functional-wearable-preview`

General Backpack uses `#backpack-filters`, `#backpack-grid` and the E10 item
detail dialog (`inventory.html:563-586`, `inventory.html:555-556`).

Functional reads are implemented by `loadFunctionalEquipment()` and its grid,
detail and preview helpers (`inventory.html:615-842`). It reads
`/api/player/inventory` plus `/api/skills/profile` for the preview character.
The endpoint is server-owned `player_inventory` state
(`app.py:16856-16885`).

General Backpack reads are implemented by `loadBackpack()` and
`renderBackpackGrid()` (`inventory.html:1057-1164`). It combines:

- `/api/shop/catalog` for shop definitions and `shop_inventory` quantities;
- `/api/auth/me` for the display name;
- `/api/pet/status` for `pet_inventory` materials.

The general Backpack action is a mutation: `useBackpackItem()` posts to
`/api/shop/use` (`inventory.html:1099-1112`). Functional equip/unequip posts
to `/api/player/inventory/equip` (`inventory.html:799-814`). Neither action
belongs in A026.

### A026 fit

| Fact | Fit | Boundary |
|---|---|---|
| Owned functional equipment | Thin adapter | Read projection only; authority remains `player_inventory`. |
| Equipped functional equipment | Thin adapter | Do not recalculate effects. |
| Equipment slot state | Thin adapter | Safe if constrained to A026 slots. |
| Effect details/comparison/combat stats | Do not migrate | A026 forbids combat/effect authority. |
| Consumables/materials/training/quest items | Separate authority | Shop and pet inventory domains. |
| Item use | Separate authority | Keep `/api/shop/use`. |
| Shop quantities/catalog | Separate authority | Player snapshot is not Shop authority. |
| Spirit materials | Separate authority | Keep `/api/pet/status` and Spirit contracts. |
| Player display name | Direct candidate | Low-risk display-only field. |

`functional_equipment_new_ids` in sessionStorage is read at
`inventory.html:656-667` and populated from the Adventure loot toast at
`index.html:8315-8323`. It controls only a transient New badge. Keep it
until the new contract has an equivalent UI-only fact; it is not ownership.

## 4. WARDROBE_PURE_COSMETIC_PRESENTATION

### Current DOM and render contract

The Appearance tab and wardrobe slot containers are in
`hero.html:2153-2232`; the effect-bearing Equipment projection is
`#wardrobe-effect-equipment-grid` at `hero.html:2142-2150`.

The pure cosmetic path is:

- `renderWardrobeSlots()` → `renderInvSlot()`
  (`hero.html:4513-4550`)
- `wardrobeHasGameplayEffect()` (`hero.html:4320-4327`)
- `renderCosmeticProjection()` (`hero.html:4078-4105`)
- `handleInvClick()` (`hero.html:4552-4595`)

The current profile response contains `wardrobe` rows with `owned`,
`equipped`, `effects` and presentation metadata (`app.py:17349-17385`).
The server builds that projection from `player_wardrobe` and
`player_appearance`; hidden/unreleased IDs are filtered server-side in the
profile response (`app.py:17351-17354`).

The browser deliberately separates effect-bearing appearances:

- `renderCosmeticProjection()` requires `owned === true`, `equipped ===
  true` and `!wardrobeHasGameplayEffect(item)`.
- `renderWardrobeEquipmentProjections()` filters the inverse and renders
  those items under functional Equipment (`hero.html:4504-4510`).

That split is a critical compatibility rule. A future A026 adapter must keep
it, not reinterpret an effect-bearing appearance as pure cosmetics.

One current classifier caveat must remain visible in the migration contract:
`wardrobeHasGameplayEffect()` returns `false` early for `pet` and `title`
items (`hero.html:4320-4327`). That means a future adapter must not infer
that every pet/title row is pure merely because this helper does not inspect
its effects. Those categories require the same server-backed presentation
classification and Owner review before adoption.

### A026 fit

| Fact | Fit | Boundary |
|---|---|---|
| Owned/selected pure appearance: outfit, hat, back, accessory, pet, aura, title | Thin adapter | These are the seven A026 cosmetic slots. |
| Character key | Direct candidate | Hero presentation identity. |
| Stone skin / board skin | Do not migrate | Current A026 adapter slot contract does not include them. |
| Effect-bearing appearance | Do not migrate | Must stay functional/effect presentation. |
| Cosmetic unlock/milestones | Separate authority | Current profile includes learning-adjacent milestone facts; do not forward. |
| Equip/unequip mutation | Separate authority | Keep `/api/skills/equip` and `/api/player/appearance/unequip`. |
| Premium unlock state | Separate authority | Premium is excluded from A026. |

## Cross-surface local/global state audit

| State | Storage | Classification | Disposition |
|---|---|---|---|
| `hero_combat_gear_v1` | localStorage | `SERVER_AUTHORITY_WITH_LOCAL_CACHE` | Retire after server route adoption; never authority |
| `functional_equipment_new_ids` | sessionStorage | `LOCAL_PRESENTATION_CACHE_ONLY` | Keep for transient New badge unless a later UI contract replaces it |
| `adventure_selected_stage_v1` | localStorage | `SEPARATE_DOMAIN_AUTHORITY` | Not A026 scope; retain as World selection state |
| `map_battle_v1_resume_v1`, `placement_ritual_*` | sessionStorage | `SEPARATE_DOMAIN_AUTHORITY` | Not A026 scope; retain Battle/Adventure semantics |
| `last_session_uid_v1` | localStorage | `LOCAL_PRESENTATION_CACHE_ONLY` | Keep account-switch hygiene |
| `window.__GO_WORLD_PRESENTATION_STATE__` | window global | `SEPARATE_DOMAIN_AUTHORITY` | Keep E10/E9 shell state separate |
| `window.__GO_ADVENTURE_SHELL_OWNER__`, `__GO_E9_*` | window global | `LEGACY_COMPATIBILITY` | Keep strangler fallback and rollout handoff |
| `window.__GO_E10_BACKPACK_MODE__` | window global | `SEPARATE_DOMAIN_AUTHORITY` | Keep Backpack shell mode separate |

In-memory duplicates include `_profileData`, `_combatGear`, `_wardrobeItems`,
`_petState`, `_functionalEquipmentItems`, `backpackItems`,
`_adventureProgress` and `_homeSpiritPet`. These are render state, not a new
authority, but each future adapter must define which safe fields it replaces.

## Current source classifications and counts

The counts use explicit group definitions, not DOM-node counts:

- `DUPLICATED_PRESENTATION_SOURCES=5`: five source groups feed at least two
  audited surfaces: skills profile, player appearance, functional inventory,
  Spirit status, and the local Hero loadout cache.
- `LOCAL_PRESENTATION_CACHES=2`: `hero_combat_gear_v1` and
  `functional_equipment_new_ids`. World/Battle caches are reported separately
  because they are not A026 presentation fields.
- `LEGACY_COMPATIBILITY_SOURCES=4`: broad skills-profile compatibility,
  Adventure E9/fallback paths, Backpack legacy/catalog fallback, and the
  local COMBAT_GEAR compatibility layer.

Full source-to-surface entries and the count definition are in the JSON
matrix; no current frontend file was modified.

## A026 replacement boundary

| A026 group | Current safe adoption | Must remain outside |
|---|---|---|
| Hero identity | Hero and Adventure identity fragments | Functional Hero authority, class power, skills/passives |
| XP/level/rank | Hero summary and Adventure identity | Learning correctness, streaks, SRS and analytics |
| Persistent HP | Future display only where a current surface actually consumes it | Encounter HP and Battle HP |
| Equipment | Owned/equipped read presentation in Hero/Backpack | Equip mutation, effect calculation, combat stats |
| Spirit | One active Spirit display in Hero/Adventure | Spirit ownership/progression/effects/mutations |
| Cosmetics | Seven pure appearance slots | Effect-bearing appearances, Premium/unlock authority, stone/board skin until contract support |
| World | None | Selected Zone, progression Zone, stars, Lord readiness, shell owner |
| Quest/reward/shop | None | Quest state, reward settlement, catalog, quantities, purchase/use |

`SELECTED_ZONE_IS_WORLD_AUTHORITY=YES` is the hard Adventure boundary. The
Player Presentation snapshot must not contain it.

## Recommended migration order

1. **Hero overview read-only fragment** — safest direct A026 fit, but isolate
   the summary from current effect and Premium arithmetic.
2. **Adventure player identity card** — replace name/character/XP/rank/active
   Spirit only; do not touch map bootstrap or shell ownership.
3. **Wardrobe pure cosmetic projection** — consume only the seven supported
   pure slots, keep effect-bearing and unlock paths separate.
4. **Backpack functional equipment subpanel** — adopt read-only owned/equipped
   display last because the page combines multiple inventories and mutation
   endpoints.

Each step has a fallback and rollback boundary in the migration-order JSON.
No step authorizes route creation, API wiring, mutation changes, or deletion
of a legacy path.

## Future file-collision map

- `hero.html`: shared by Hero overview and Wardrobe; high collision risk due
  to inline state, render helpers and mutations.
- `index.html`: very high risk because the identity card shares the World,
  Adventure, E9/E10 shell, Battle and replay runtime.
- `inventory.html`: high risk because functional Equipment and general
  Backpack are co-located but have different authorities and write actions.
- `player_presentation_consumer_adapter.py`: accepted A026 input module;
  no current frontend wiring.
- `app.py`: future E026 route only; Owner-gated and untouched by A027.
- `components/adventure/*.html` and `static/js/e9/*`: compatibility assets
  reachable from the Adventure shell; current index identity helpers remain
  inline, so these are fallback dependencies rather than current A026 source.

## Validation and final boundary

Validation performed for this docs-only recon:

- exact route declarations checked in `app.py`;
- exact DOM/helper/API/local-state references checked in `hero.html`,
  `index.html`, `inventory.html` and the relevant backend route definitions;
- A026 accepted adapter field boundary inspected from accepted commit
  `a3808a095054856d23db5f0168c6c359976a210d`;
- deterministic JSON artifacts prepared for parse validation;
- no browser, route, API, database, frontend or Production mutation.

Required invariants:

```text
SURFACES_AUDITED=4
WORLD_AUTHORITY_MOVED_TO_A026=NO
INVENTORY_AUTHORITY_MOVED_TO_A026=NO
QUEST_AUTHORITY_MOVED_TO_A026=NO
SHOP_AUTHORITY_MOVED_TO_A026=NO
FRONTEND_IMPLEMENTATION_PERFORMED=NO
APP_PY_CHANGED=NO
FRONTEND_CHANGED=NO
SCHEMA_CHANGED=NO
PRODUCTION_MUTATION=NO
DEPLOY=NO
MASTER_MERGE=NO
```

## Owner decision packet

The exact counts for this recon are:

```text
TOTAL_PLAYER_PRESENTATION_SURFACES=4
DUPLICATED_PRESENTATION_SOURCES=5
LOCAL_PRESENTATION_CACHES=2
LEGACY_COMPATIBILITY_SOURCES=4
NEEDS_API_ADAPTER=4 surface families (safe fragments only)
NEEDS_SEPARATE_AUTHORITY=4 surface families contain retained separate authorities
OWNER_DECISION_REQUIRED=1 route/endpoint and adoption gate (E026)
```

These categories are not mutually exclusive: every surface contains a safe
fragment candidate and at least one separate domain boundary. The per-fact
matrix is the source of truth for avoiding double-counting.

Recommendation:

`RECOMMENDATION_A=BUILD_PLAYER_PRESENTATION_READ_API_NEXT`

with the explicit condition that E026 must receive Owner PASS first, and the
first frontend adoption must be the bounded Hero overview read-only fragment.

```text
TASK=A027_PLAYER_PRESENTATION_SURFACE_WIRING_RECON_V1_001
READY_FOR_OWNER_A027_REVIEW=YES
```
