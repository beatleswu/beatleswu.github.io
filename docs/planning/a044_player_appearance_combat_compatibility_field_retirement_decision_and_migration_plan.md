# A044 player_appearance combat compatibility-field retirement plan

## Decision status and exact lineage

```text
TASK=A044_PLAYER_APPEARANCE_COMBAT_COMPATIBILITY_FIELD_RETIREMENT_DECISION_AND_MIGRATION_PLAN_001
CURRENT_ORIGIN_MASTER=574b3eeb9641c48676e95d3744d204dffca1e1fa
BASE_SHA=574b3eeb9641c48676e95d3744d204dffca1e1fa
A043_HEAD=98ccaa6a43482661cd7a0b3d19ac09f415a9e341
FRESH_MASTER_RECONCILIATION=PASS
```

`origin/master` contains the B057 merge at `574b3eeb9`. A043 is an accepted
post-RC branch, but it is not an ancestor of this fresh master and fresh master
is not an ancestor of A043. This packet audits fresh master and explicitly
compares the accepted A043 route closure; it does not merge or apply A043.

## Exact field inventory

The inventory is exactly these eight fields:

```text
combat_armor
combat_weapon
combat_cape
combat_offhand
combat_hat
combat_pet
combat_aura
combat_acc
```

`player_appearance` is keyed by `user_id INTEGER PRIMARY KEY`. The eight fields
are nullable `TEXT` columns added by the existing `add_column_if_not_exists`
startup compatibility list (`app.py:5505-5512`); the original table-creation
shape does not include them. There is no per-field foreign key, check
constraint, ownership index, or link to `player_inventory`.

### Reader/writer matrix

| Field | Database storage | Source readers | Source writers | Client readers/writers | Serialization, admin, tests | Current data role |
| --- | --- | --- | --- | --- | --- | --- |
| `combat_armor` | Nullable `player_appearance.combat_armor` | `_get_appearance_effects`; `/api/player/appearance`; community/friend/badge/DM loadout queries | `/api/skills/character` `combat_in`; test fixtures | Bot, Community, Messages read server payload; Hero has a gated legacy batch writer | `/api/player/appearance`, `_row_loadout` social payloads, leaderboard reward participant read; no admin-only writer; fixtures/test-only schemas | Legacy appearance visual plus legacy noncombat modifier input |
| `combat_weapon` | Nullable `player_appearance.combat_weapon` | `_get_appearance_effects`; `/api/player/appearance`; community/friend/badge/DM loadout queries | `/api/skills/character` `combat_in` | Bot, Community, Messages read server payload; Hero gated legacy batch writer | Same social/profile serialization family; test fixtures | Legacy appearance visual plus legacy noncombat modifier input |
| `combat_cape` | Nullable `player_appearance.combat_cape` | `_get_appearance_effects`; community/friend/badge/DM loadout queries | `/api/skills/character` `combat_in` | Community and Messages read server payload; Hero gated legacy batch writer | Social payloads and leaderboard reward participant read; test fixtures | Legacy appearance visual plus legacy noncombat modifier input |
| `combat_offhand` | Nullable `player_appearance.combat_offhand` | `_get_appearance_effects`; `/api/player/appearance`; community/friend/badge/DM loadout queries | `/api/skills/character` `combat_in` | Bot, Community, Messages read server payload; Hero gated legacy batch writer | Same social/profile serialization family; test fixtures | Legacy appearance visual plus legacy noncombat modifier input |
| `combat_hat` | Nullable `player_appearance.combat_hat` | `_get_appearance_effects`; community/friend/badge/DM loadout queries | `/api/skills/character` `combat_in` | Community and Messages read server payload; Hero gated legacy batch writer | Social payloads and leaderboard reward participant read; test fixtures | Legacy appearance visual plus legacy noncombat modifier input |
| `combat_pet` | Nullable `player_appearance.combat_pet` | `_get_appearance_effects`; community/friend/badge/DM loadout queries | `/api/skills/character` `combat_in` | Community and Messages read server payload; Hero gated legacy batch writer sends neutral `none` | Social payloads and leaderboard reward participant read; test fixtures | Legacy appearance visual plus legacy noncombat modifier input; Spirit is separate |
| `combat_aura` | Nullable `player_appearance.combat_aura` | `_get_appearance_effects`; community/friend/badge/DM loadout queries | `/api/skills/character` `combat_in` | Community and Messages read server payload; Hero gated legacy batch writer | Social payloads and leaderboard reward participant read; test fixtures | Legacy appearance visual plus legacy noncombat modifier input |
| `combat_acc` | Nullable `player_appearance.combat_acc` | `_get_appearance_effects` only; no raw current API/social serializer found | `/api/skills/character` `combat_in` | Hero gated legacy batch writer; no current raw client reader found | Aggregate `active_effects` only; test fixtures do not establish Production data | Legacy noncombat modifier input; no current raw display surface |

`app.py:2851-2902` is the common server reader. `app.py:17949-18005`
is the common server writer. The writer accepts client-provided legacy tier
keys after `_gear_unlocked` checks; it does not establish `player_inventory`
ownership or equipped-state authority.

The common social query/read model is implemented by `_row_loadout`
(`app.py:18201-18212`) and its community, friends, badges, profile, and DM
callers. Those callers select seven fields and omit `combat_acc`. The
standalone reward participant reader in
`community_leaderboard_rewards.py:360-405` also selects seven fields.

```text
UNKNOWN_FIELD_READERS=0
UNKNOWN_FIELD_WRITERS=0
COMBAT_COMPATIBILITY_FIELD_COUNT=8
```

There are no current admin-only field writers. SQL fixture creation/inserts in
tests are test-only writers and are not Production authority.

## Authority classification

For every one of the eight fields:

```text
FUNCTIONAL_COMBAT_AUTHORITY=NO
EQUIPMENT_OWNERSHIP_AUTHORITY=NO
EQUIP_STATE_AUTHORITY=NO
```

Authoritative combat stats are derived by `_get_authoritative_combat_stats`
from owned/equipped `player_inventory` rows and `EQUIPMENT_DEFS`; the function
does not read any `combat_*` field. SRS review uses the server equipment effect
resolver rather than `_get_appearance_effects`.

However, retirement is not currently safe to execute. `_get_appearance_effects`
does read every field and interprets `_tN` values as XP/drop modifiers:

```text
combat_weapon  -> xp_bonus       tier * 0.01
combat_cape    -> xp_bonus       tier * 0.005
combat_armor   -> drop_bonus     tier * 0.01
combat_offhand -> drop_bonus     tier * 0.005
combat_hat     -> xp_bonus       tier * 0.005
combat_aura    -> xp_bonus       tier * 0.01
combat_pet     -> drop_bonus     tier * 0.01
combat_acc     -> drop_bonus     tier * 0.01
```

This is not authoritative combat damage, but it is live legacy noncombat
gameplay behavior exposed as `skills_profile.active_effects`. Therefore:

```text
RETIREMENT_BLOCKED_REAL_AUTHORITY_FOUND=YES
CALLER=_get_appearance_effects -> skills_profile.active_effects
```

Visual roles are compatibility-only: seven fields feed Bot/Community/Messages
avatar layers; `combat_acc` has no current raw visual serializer. None of these
fields owns functional equipment ownership, equipped state, combat damage, or
Spirit state.

## Proposed field dispositions

The same disposition is intentional but not a blanket assumption: the seven
displayed fields have both social visual readers and the shared legacy modifier
reader, while `combat_acc` has only the modifier reader and a latent writer.

| Field | Proposed disposition | Reason and prerequisite |
| --- | --- | --- |
| `combat_armor` | `BLOCKED_NEEDS_OWNER_DECISION` | Active legacy drop modifier plus raw social visual readers; decide modifier retirement and reader migration first |
| `combat_weapon` | `BLOCKED_NEEDS_OWNER_DECISION` | Active legacy XP modifier plus raw social visual readers; no `player_inventory` linkage may be inferred |
| `combat_cape` | `BLOCKED_NEEDS_OWNER_DECISION` | Active legacy XP modifier plus raw social visual readers |
| `combat_offhand` | `BLOCKED_NEEDS_OWNER_DECISION` | Active legacy drop modifier plus raw social visual readers |
| `combat_hat` | `BLOCKED_NEEDS_OWNER_DECISION` | Active legacy XP modifier plus raw social visual readers |
| `combat_pet` | `BLOCKED_NEEDS_OWNER_DECISION` | Active legacy drop modifier plus raw social visual readers; do not conflate it with D038 Spirit |
| `combat_aura` | `BLOCKED_NEEDS_OWNER_DECISION` | Active legacy XP modifier plus raw social visual readers |
| `combat_acc` | `BLOCKED_NEEDS_OWNER_DECISION` | Active legacy drop modifier; no raw display reader, but writer/effect dependency remains |

No field is proposed for immediate `STOP_WRITING_AND_READING` or physical
column removal. The next safe target after Owner decisions is generally
`STOP_WRITING_KEEP_READING` for the seven social fields and
`STOP_WRITING_AND_READING` for `combat_acc`, but only after the active effect
consumer has been retired or explicitly preserved elsewhere.

## Canonical replacement matrix

| Retired responsibility | Canonical replacement | Migration constraint |
| --- | --- | --- |
| Functional ownership/equip state | `player_inventory` ownership row, `equipped`, `canonical_slot`, server `EQUIPMENT_DEFS` | Requires B033 source/Production readiness; never infer ownership from appearance fields |
| Functional equipment combat effects | Server `_get_authoritative_combat_stats` / `_safe_active_equipment_effect` | Keep client and appearance fields out of combat authority |
| Hero functional equipment presentation | Server `/api/player/inventory` projection | A034/A035/A040 behavior; no localStorage or `hero_combat_gear_v1` authority |
| Pure cosmetic appearance | `player_wardrobe`, `player_appearance` cosmetic slot columns, `APPEARANCE_DEFS`, `PURE_COSMETIC_PRESENTATION_REGISTRY` | Cosmetic state remains presentation-only and has zero combat power |
| Community/DM avatar display | A migrated server presentation read model using canonical cosmetic state, or neutral fallback | Migrate readers before removing seven-field compatibility serialization |
| Legacy XP/drop modifiers | Owner-selected replacement or explicit retirement | No canonical replacement is proven for the current `_tN` formula; do not silently change rewards |

No replacement points to localStorage, `hero_combat_gear_v1`, client-supplied
combat state, or `APPEARANCE_EFFECTS` as functional combat authority.

## Dual-write analysis

```text
DUAL_WRITE_SURFACES=
No active atomic same-request dual write was found. There is a semantic dual
representation: /api/skills/character writes player_appearance.combat_* while
the canonical equipment route writes player_inventory separately. The Hero
legacy batch writer is source-present but gated by
HERO_LEGACY_LOADOUT_EFFECTIVE=false, so it does not currently send these fields.
```

| Surface | SAFE_TO_STOP_COMPAT_WRITE | REQUIRES_EXISTING_DATA_BACKFILL | REQUIRES_READER_MIGRATION_FIRST |
| --- | --- | --- | --- |
| `/api/skills/character` eight-field compatibility write | NO, not until legacy modifier semantics are decided | Not proven; only exact validated ownership references may be backfilled | YES |
| Hero gated legacy batch writer | YES after confirming the disabled gate remains fixed false | NO | No, because it is not active today |
| Test fixture writers | YES per individual test cleanup | NO | NO |

There is no safe A044 backfill mapping from `combat_*` text to
`player_inventory`: the appearance row has no exact inventory ownership
reference, and a name/slot/latest-row inference would be unsafe.

## Local fixture census and Production boundary

Repository fixtures prove that the columns are nullable and can be populated
with `NULL`, empty strings, neutral values (`none`/`cloth`), and parameterized
legacy appearance identifiers. Hero source catalogs contain tier identifiers
such as `armor_tN`, `weapon_tN`, `cape_tN`, `offhand_tN`, `hat_tN`, `pet_tN`,
`aura_tN`, and `acc_tN`. The writer validates unlock thresholds, not
`player_inventory` ownership, so historical values may no longer correspond to
owned equipment. The schema has no constraint that rejects obsolete or unknown
text values; no local fixture establishes a complete real-user distribution.

```text
LOCAL_FIXTURE_DATA_CENSUS=
Nullable/empty/neutral values are present; parameterized legacy values are
supported; appearance values are not ownership-linked; unknown/obsolete text
is not schema-rejected; no Production distribution inferred.
PRODUCTION_FIELD_DATA_STATE=UNKNOWN
PRODUCTION_COMPATIBILITY_FIELD_POPULATION=UNKNOWN
PRODUCTION_QUERY=NO
```

## APPEARANCE_EFFECTS and Hero cache relation

```text
APPEARANCE_EFFECTS_FUNCTIONAL_COMBAT_AUTHORITY=NO
```

`APPEARANCE_EFFECTS` remains a legacy appearance catalog/effect compatibility
map. It is read by the C013 resolver and `_get_appearance_effects`, returned in
appearance/profile presentation shapes, and tested by cosmetic compatibility
suites. Its `xp_bonus`/`drop_bonus` projection is noncombat gameplay behavior,
not combat damage authority. Classification is:

```text
APPEARANCE_EFFECTS_COMPATIBILITY_MATRIX=
KEEP_TEMPORARY for existing appearance/profile compatibility; RETIRE_WITH_FIELDS
for the combat_* tier-derived modifier input after Owner policy and reader
migration; never use it as functional combat authority.
```

```text
HERO_COMBAT_GEAR_V1_FUNCTIONAL_AUTHORITY=NO
HERO_COMBAT_GEAR_V1_FIELD_DEPENDENCY=
No functional dependency. Hero retains a bounded character-only compatibility
hint and a source-present legacy batch writer behind a fixed false gate; Hero
functional equipment reads server inventory projection. The A040 guard discards
functional cache fields and does not create ownership/effect state.
```

`COSMETIC_APPEARANCE_ROUTE_BEHAVIOR_CHANGED=NO`. A044 does not alter wardrobe
equip routes, appearance grants, or cosmetic rendering.

## B033 relationship and migration requirements

The B033 candidate migration is `migrations/equipment_canonical_slot_v1.py`.
It defines `player_inventory.canonical_slot`, valid slots
`weapon/armor/accessory`, the equipped-row validity gate, and the partial unique
`(user_id, canonical_slot)` index. It is not imported by application startup,
does not commit, and its Production state is unknown.

```text
B033_DEPENDENCY_MATRIX=
Source artifact: EXISTS and test-covered.
Current source-created player_inventory: pre-B033 shape; canonical_slot not in
the base CREATE TABLE.
Future functional replacement: depends on canonical_slot population plus B033
validity/unique constraints.
Compatibility-field retirement itself: does not authorize or perform B033.
Production B033 migration: UNKNOWN and Owner-gated; no migration run here.
```

## Safe retirement sequence

1. Obtain Owner decisions for legacy XP/drop modifiers, social visual
   compatibility duration, and dormant-column policy.
2. Run a separately authorized read-only Production census; keep the result
   distinct from local fixtures and never infer readiness from source migration
   existence.
3. Prove the server equipment authority and B033 schema/readiness, including
   exact ownership references and canonical slot population where needed.
4. Migrate the `_get_appearance_effects` consumer: either preserve the legacy
   noncombat behavior under an explicitly approved authority or retire it
   without silently changing player rewards.
5. Stop `/api/skills/character` combat-field writes behind a reviewed
   compatibility window; preserve character/cosmetic routes.
6. Migrate Bot/Community/Messages and internal social serializers away from
   raw combat-field avatar values, with a neutral or canonical cosmetic
   fallback.
7. Observe and validate that no approved readers/writers remain; do not
   auto-unequip or rewrite existing players.
8. Remove compatibility reads only after the observation/data-validation gate.
9. Consider a separate Owner-authorized schema migration to drop columns last;
   dormant retention remains an allowed outcome.

```text
SCHEMA_DROP_AUTHORIZED=NO
```

## Owner decision packet

```text
OWNER_DECISION_ITEM_COUNT=3
```

### DECISION_ID=A044-D1

```text
QUESTION=Should the legacy combat_* tier-derived XP/drop modifiers remain?
OPTION_A=Keep a timeboxed compatibility read window, then retire the modifiers.
OPTION_B=Preserve the modifiers indefinitely as noncombat legacy behavior.
RECOMMENDED=OPTION_A
RATIONALE=The fields are not combat authority, but the current reader is live
gameplay behavior; a timeboxed window prevents silent reward changes while
avoiding permanent legacy authority.
RISK=Retirement can change XP/drop outcomes for historical values if not
measured and communicated.
```

### DECISION_ID=A044-D2

```text
QUESTION=How should social/avatar readers treat historical seven-field values?
OPTION_A=Migrate to canonical cosmetic projection or neutral fallback, retain a
bounded compatibility window, then stop reading.
OPTION_B=Keep raw combat_* social serialization as long-term dormant compatibility.
RECOMMENDED=OPTION_A
RATIONALE=It removes the misleading combat-prefixed presentation source while
preserving a controlled compatibility period.
RISK=Historical avatars may visually change after the window if no exact
cosmetic mapping exists.
```

### DECISION_ID=A044-D3

```text
QUESTION=After all readers/writers and data are proven clear, should physical
columns be dropped or retained dormant?
OPTION_A=Drop columns in a separately authorized migration after validation.
OPTION_B=Retain dormant nullable columns for long-term rollback compatibility.
RECOMMENDED=OPTION_A only after every gate passes; otherwise OPTION_B.
RATIONALE=No immediate drop is safe while Production population is unknown and
the current effect reader/writer remains active.
RISK=Drop risks irreversible compatibility loss; dormant retention carries
schema debt and future confusion.
```

## Recommended next A-lane sequence

```text
RECOMMENDED_NEXT_A_TASK_SEQUENCE=
A045: Owner decision and read-only Production compatibility-field census contract.
A046: Retire or explicitly re-home legacy _get_appearance_effects tier modifiers;
     stop combat_* writes while preserving cosmetic routes.
A047: Migrate social/profile readers and serializers away from raw combat_* fields.
A048: B033 source/Production schema readiness preflight and exact data validation.
A049: Compatibility read-window closeout and no-reader/no-writer verification.
A050: Separate final Loadout enablement preflight; Owner GO_ENABLE remains required.
```

## Scope and tests

```text
APP_PY_CHANGED=NO
RUNTIME_SOURCE_CHANGED=NO
STATIC_SOURCE_CHANGED=NO
SCHEMA_CHANGED=NO
MIGRATION_CHANGED=NO
DATA_CHANGED=NO
B058_SCOPE_TOUCHED=NO
E046_SCOPE_TOUCHED=NO
F034_R2_SCOPE_TOUCHED=NO
LC015_SCOPE_TOUCHED=NO
ART003_SCOPE_TOUCHED=NO
LOADOUT_ENABLED=NO
GO_ENABLE_CONSUMED=NO
```

Added only the A044 static inventory test. It validates exact eight-field
coverage, server reader/writer coverage, canonical combat authority separation,
B033 replacement symbols, and bounded client compatibility consumers.

```text
FIELD_READER_INVENTORY_TEST=PASS
FIELD_WRITER_INVENTORY_TEST=PASS
AUTHORITY_BOUNDARY_TEST=PASS
CANONICAL_REPLACEMENT_TEST=PASS
TASK_INTRODUCED_FAILURES=0
```

No Production query, mutation, migration, deploy, merge, or feature enablement
was performed.
