# B028 Player / Hero Canonical State Read Model V1

Status: implementation candidate; read-only projection only.

Start canonical master: `58d9b7047f285751a048fc551c955909c87984ac`

This document records the B028 contract. It does not create a new player
state authority, a route, a migration, or a mutation path.

## Scope and authority rule

B028 exposes one deterministic server-side projection through
`build_player_state_read_model(conn, user_id)` in
`player_state_read_model.py`. The authenticated caller supplies the user ID;
the client does not supply state, derived combat numbers, ownership, level,
or results.

The projection is read-only and side-effect free. It performs bounded reads,
does not commit, and does not write `user_stats`, `player_inventory`, Spirit
tables, appearance tables, or World tables.

The read model is an aggregation contract, not a second durable authority:

```text
existing authorities
    -> validated projections with provenance/status
    -> player_hero_state_v1
```

## Current authority inventory

| Read-model field/group | Current source authority | Read path | Mutation authority | B028 behavior |
|---|---|---|---|---|
| `player_id` | `users.id` | `SELECT id FROM users WHERE id=?` | Existing authenticated account/user flows | Missing user is `PLAYER_NOT_FOUND`; no synthetic player |
| Hero identity | `player_appearance.character_key` when present | Existing `/api/skills/character` and `/api/player/appearance` semantics; B028 reads the row | Existing character-selection/appearance route | Presentation-only identity; missing selection is `hero_id=None` with an explicit `apprentice` presentation fallback |
| XP / rank / level | `user_stats.xp`, `user_stats.rank_level`, `user_stats.rank_xp` | Existing `user_stats` row; level normalization uses the existing `_rank_to_lv` authority lazily | Existing XP/progression settlement | Raw stored values are projected; no XP ledger or level mutation is created |
| Player HP | `user_stats.player_hp`, `user_stats.player_max_hp` | Existing `user_stats` row | Existing legacy/global battlefield/stat flows | Projected as persistent/global HP only; invalid bounds fail closed |
| Encounter HP | `map_battles.player_hp`, `map_battles.player_hp_max` and other encounter state | Requires a battle/encounter context | Map Battle/encounter settlement | Not flattened into Player/Hero state; exposed only as an excluded encounter boundary |
| Equipment ownership/equipped state | `player_inventory` | Existing inventory rows, joined in one bounded read | Existing acquire/equip/unequip authority | Slots are projected without combat stat calculation or mutation |
| Equipment catalog/status | `EQUIPMENT_DEFS`, `INVENTORY_ONLY_EQUIPMENT_IDS`, `_FUNCTIONAL_EFFECT_ACTIVE_KEYS` | Existing server catalog adapter, imported lazily | Existing equipment catalog/runtime | Display identity and functional-status labels only; B028 does not calculate damage/mitigation |
| Active Spirit/ownership/stage | `pet_collection` plus `user_pets` active projection | Existing `spirit_runtime.build_b022_active_spirit_projection` | Existing Spirit/D008/B023 operation authority | One active projection only; invalid multi-active input is `AUTHORITY_AMBIGUOUS` and never stacked |
| Cosmetic ownership | `player_wardrobe` | Existing wardrobe rows | Existing wardrobe acquisition authority | Presentation-owned item summary only |
| Cosmetic selection | `player_appearance` slot columns | Existing appearance route semantics | Existing appearance equip/character routes | Selected appearance is validated against wardrobe/catalog; no gameplay power is projected |
| World progression | World authorities such as `adventure_zone_unlocks` and `adventure_boss_progress` | Existing World/adventure code | System 02/World authority | Not queried or owned by B028; World boundary is returned as metadata only |

The schema definitions supporting these sources are in `app.py`: `users` and
`user_stats` around the initialization block, `player_wardrobe`,
`player_appearance`, and `player_inventory` in the player-state schema block,
and Spirit storage in the `user_pets`/`pet_collection` block. The exact
runtime readers are `_rank_to_lv`, `_functional_equipped_by_slot`,
`_functional_equipment_presentation_projection`, `_get_authoritative_combat_stats`,
`get_appearance`, and `skills_character`. Spirit projection is kept in
`spirit_runtime.py` rather than copied into B028.

## Final read-model contract

The top-level shape is:

```text
{
  read_model: "player_hero_state",
  read_model_version: "player_hero_state_v1",
  projection_status: OK | PARTIAL | INVALID_STORED_STATE | AUTHORITY_AMBIGUOUS,
  read_only: true,
  mutates: false,
  player_id,
  hero,
  progression,
  hp,
  equipment,
  spirit,
  cosmetics,
  world,
  provenance,
}
```

Every state group includes an authority and a projection status. Missing
optional rows are represented as `None`/empty values with
`OPTIONAL_PROJECTION_UNAVAILABLE`; they are not filled with fabricated
ownership, XP, HP, Spirit, or cosmetic selections. Structural read failures
raise `PlayerStateReadModelError(code="AUTHORITY_UNAVAILABLE")`. An unknown
player raises `PLAYER_NOT_FOUND`; malformed caller identity raises
`INVALID_REQUEST`.

### Hero identity

The current runtime has a durable presentation selection in
`player_appearance.character_key`, but no separate functional Hero selector
was found. B028 consumes that existing selection and labels its scope
`presentation_only`. It does not turn a display key into combat authority or
create a new Hero roster/selector.

Current active runtime character keys are consumed from the existing
`ACTIVE_CHARACTER_KEYS` registry. A missing or invalid stored value produces
`hero_id=None`, an explicit status, and the existing server presentation
fallback `apprentice`; B028 does not write the fallback back to storage.

### XP, level, progression, and HP

`user_stats.xp` and `user_stats.rank_level` are returned as stored. Numeric
level is normalized through the existing `_rank_to_lv` function rather than a
new XP formula. `rank_xp`, Go rank, correct-answer totals, and streak summary
are read-only metadata from the same row.

`user_stats.player_hp` and `player_max_hp` are exposed only as
`persistent_player_hp` and `persistent_player_max_hp` with a legacy/global
scope. Map Battle HP remains encounter-local and is deliberately not queried
without a battle context. B028 never invents a global HP authority from
`map_battles`.

### Equipment

The projection always exposes the canonical `weapon`, `armor`, and
`accessory` slots. Each slot reports selected item ID, ownership, equipped
state, quantity, display reference, and a non-authoritative functional status.
It does not return combat stats or effect magnitudes.

`xp_amulet` remains `HOLD_FOR_AUTHORITY` and no effect is invented.
`go_stone_black` remains `INVENTORY_ONLY_TROPHY`; it is not projected as a
wearable combat item even if malformed stored data marks it equipped. Unknown
items and conflicting equipped rows are reported as invalid stored state
rather than silently selected.

### Spirit

B028 consumes `spirit_runtime.build_b022_active_spirit_projection`. The
projection carries the validated active Spirit ID, enabled flag, ownership
validation, progression level, and evolution stage. It does not evaluate
B027 combat effects and does not expose a client-selected Spirit as authority.
Owned but inactive Spirits do not appear as active. A projection indicating
more than one active Spirit is returned as `AUTHORITY_AMBIGUOUS` with no active
Spirit, preventing stacking.

### Cosmetics and World boundary

Cosmetic selection and wardrobe records are returned with
`presentation_only=true` and `combat_power_projected=false`. No appearance
record grants equipment power, damage, mitigation, XP, or progression.

World progression is represented only by a boundary metadata object with
`projected=false` and `authority=world_progression_system`. In particular,
selected zone, unlocked zone, quest completion, Monster defeat, Battlefield
Boss state, and Lord state remain outside Player/Hero authority.

## Query/read topology

The default projection uses one identity read, one `user_stats` read, one
inventory read, one Spirit projection read through the existing Spirit module,
and one wardrobe/appearance read each. It does not issue a query per item,
Spirit, or cosmetic and introduces no cache. Catalog lookups are in-memory
server registries; no catalog rows are created or mutated.

The caller-owned connection/transaction remains the caller's boundary. B028
does not commit or roll back a caller transaction. PostgreSQL remains the
authoritative concurrency database for future API integration.

## Legacy and missing-data behavior

* No `user_stats` row: XP, level, and persistent HP remain `None`; the group
  is marked optional/unavailable. No defaults are written.
* No equipment rows: all three slots are empty and ownership is false.
* No active Spirit: active Spirit is `None`; no Spirit effect is inferred.
* Orphaned/ambiguous Spirit projection: no active Spirit is exposed and the
  status is fail-closed.
* No wardrobe/appearance selection: empty cosmetic selection and no selected
  Hero; the presentation fallback is metadata only.
* Invalid stored bounds, unknown equipment, unowned cosmetic selection, or
  conflicting equipped rows: `INVALID_STORED_STATE`; B028 does not repair it.
* Missing user: `PLAYER_NOT_FOUND`.
* Missing required relation or driver/read failure: `AUTHORITY_UNAVAILABLE`.

## Explicitly excluded authorities

B028 does not create or own:

* an XP ledger, level formula, or XP mutation path;
* a Hero roster or durable Hero selector;
* an equipment inventory, combat-stat calculator, or item-use authority;
* a second active-Spirit selector, Spirit progression/evolution authority, or
  B027 evaluator;
* global durable HP derived from an encounter;
* World progression, zone unlock, quest, Boss/Lord, or Monster authority;
* a Player/Hero API route or UI integration.

## Validation

Focused B028 contract tests cover normal and empty projections, all equipment
slots, non-consuming reads, the XP amulet hold, the Black Go Stone trophy,
active/no-active and ambiguous Spirit state, presentation-only cosmetics,
missing Hero selection, XP/level/HP source reads, missing stats, invalid HP,
World-boundary metadata, invalid users, and malformed caller identity.

The focused suite passed: **16 passed**.

`app.py` is unchanged. No schema, migration, production DB, deployment, or
route/UI change is part of B028.

## Remaining System 01 gaps

1. The current runtime registry exposes a presentation character selection,
   not a distinct functional Hero identity authority. A later product task
   must decide whether functional Hero identity is needed; B028 intentionally
   does not create it.
2. The planned 20-Hero content surface and the currently active runtime
   character registry are not the same scope. B028 projects only the current
   runtime registry and does not register planned identities.
3. Persistent/global HP and encounter-local HP remain separate by design.
   A later player-facing state API must provide encounter context before it
   can expose Map Battle HP.
4. This module is not yet wired to a route or frontend. E023 owns the later
   single-owner `app.py` integration decision.
