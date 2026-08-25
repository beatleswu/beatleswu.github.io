# A025 Player Presentation API Contract and Surface Adapter Spec V1

Status: contract and documentation candidate; no route or frontend wiring.

## Scope and provenance

This document defines the transport boundary for a future authenticated
Player Presentation API. It does not implement the route, aggregate player
state, or replace any existing authority.

| Reference | SHA | Relationship to current master |
| --- | --- | --- |
| Current canonical master | `b75308d44806bb7c2e2b131a73ba06a71c188b3c` | current base |
| A024 accepted recon | `4c99bd36261c24b8be9cdd82ca3840a768dc19c5` | accepted candidate; not an ancestor |
| B028 accepted read model | `2c8b879a8667c0247c23e560475ee29fafad508d` | accepted candidate; not an ancestor |
| B030 accepted read service | `ade769b9a3ae8267ca06a4cd0327b45eb7ac5627` | accepted candidate; not an ancestor |

The accepted B028 and B030 SHAs are contract references only. A025 does not
pretend that either candidate is merged into the current master.

## Target topology

```text
B028 canonical Player/Hero read model
    -> B030 read service
    -> future authenticated route
    -> PLAYER_PRESENTATION_API_V1 transport contract
    -> per-surface presentation adapters
```

B028 remains the canonical aggregator and B030 remains the thin read service.
A025 is a pure validator/narrowing layer. It does not create a second Player
state authority, run SQL, authenticate callers, issue mutations, or calculate
gameplay values.

## Transport contract

The module `player_presentation_api_contract.py` defines the immutable
`PlayerPresentationApiV1` envelope and the `build_player_presentation_api_v1`
adapter. Its contract version is:

```text
PLAYER_PRESENTATION_API_V1
```

The transport body contains only these top-level fields:

```text
contract_version
player_id
projection_status
display_identity (optional)
hero
progression
persistent_hp
equipment
spirit
cosmetics
provenance
```

`display_identity` is limited to server-derived display identity fields. The
envelope and nested mappings are immutable after construction, and the JSON
serializer emits deterministic sorted compact JSON.

### Projection status

The adapter accepts the detached B030 service envelope
`PLAYER_PRESENTATION_READ_CONTRACT_V1` and maps B028 projection status as
follows:

| B028 status | A025 status |
| --- | --- |
| `OK` | `OK` |
| `PARTIAL`, `OPTIONAL_PROJECTION_UNAVAILABLE` | `PARTIAL` |
| `INVALID_STORED_STATE`, `AUTHORITY_AMBIGUOUS` | `INVALID_STATE` |
| `AUTHORITY_UNAVAILABLE` | `UNAVAILABLE` |

Only an explicit B030 `read_only=true`, `mutates=false` result is accepted.
Malformed, unknown, or forbidden top-level fields fail closed.

## Authority-safe field groups

### Player and Hero

`player_id` and optional display identity are read-only transport identity.
Hero data is presentation-only and is sourced from
`player_appearance.character_key`. The contract does not create functional
Hero authority and does not expose Hero STR, DEF, class power, skills,
passives, combat modifiers, or a Hero-specific XP curve.

### Progression and persistent HP

Progression is the evidence-backed `user_stats` XP/level/rank projection.
`persistent_hp` contains only persistent player HP and max HP from the B028
`user_stats` projection.

Encounter HP is not a transport field. The B028 boundary marker may be
retained as provenance, but active encounter HP belongs to encounter-local
battle state. Therefore:

```text
persistent HP != encounter HP
```

### Equipment

Equipment is read state only:

```text
ownership = player_inventory
equipped = player_inventory.equipped
```

The adapter exposes display-safe owned/equipped slot information and
definition references where supplied by B028. It does not equip, unequip,
consume, recalculate combat stats, resolve conflicted slots, or promote
legacy `player_appearance combat_*` fields.

### Spirit

The contract exposes one active Spirit presentation projection, including
server-provided identity, stage, level, and presentation metadata where
available. Spirit ownership, selection, progression, and combat settlement
remain outside this contract. Spirit combat effects are explicitly excluded;
`LORD_TRIAL_SPIRIT_EFFECTS=OFF`.

### Cosmetics

Cosmetics are presentation-only selected/owned state from
`player_wardrobe`/`player_appearance`. The adapter preserves the distinction
between pure cosmetics and effect-bearing legacy appearances. It does not
turn an effect-bearing appearance into a pure cosmetic, grant ownership, or
perform wardrobe mutations.

## Explicit exclusions

The transport body must not contain authority payloads for:

```text
world
encounter
quest
shop
premium
battle
reward
badges
analytics
public_profile
```

These names are also rejected as unknown/forbidden top-level input fields.
Only explicit exclusion metadata in `provenance` is permitted. In
particular, the Player Presentation endpoint must not become a World,
Quest, Shop, Premium, battle-result, reward, or public-profile endpoint.

Public-profile privacy/redaction is deferred for Owner decision. An
authenticated Player Presentation response must never be exposed as a
public-profile response by implication.

## Surface adapter matrix

The machine-readable matrix is
`docs/planning/architecture/a025_player_presentation_surface_adapter_matrix.json`.
It classifies all 14 A024 surfaces without deleting their existing route or
authority semantics.

| Surface | Classification | Snapshot use | Separate authority |
| --- | --- | --- | --- |
| `hero_overview` | `snapshot_adapter` | Identity, Hero, progression, equipment, Spirit, cosmetics | Notifications, badges, retained legacy effects |
| `hero_appearance_wardrobe` | `snapshot_adapter` | Hero and cosmetic owned/selected presentation | Wardrobe/appearance writes and release policy |
| `hero_equipment_loadout` | `snapshot_adapter` | Owned/equipped equipment and resolved slots | Inventory mutations and combat settlement |
| `hero_spirit_panel` | `snapshot_adapter` | One active Spirit presentation | Spirit ownership, selection, training, effects |
| `hero_achievement_badges` | `separate_authority` | Shared header context only | Badge/achievement/title authority |
| `adventure_world_identity` | `snapshot_adapter` | Player marker, identity, level, Spirit | World zones, selection, stars, completion, Lord readiness |
| `adventure_encounter_result` | `separate_authority` | Post-settlement player refresh | Encounter HP, Monster, correctness, damage, rewards |
| `backpack_inventory` | `separate_authority` | Functional-equipment slice | Consumables, materials, pet inventory, item use |
| `item_journal` | `separate_authority` | Optional shared header only | Item registry and journal taxonomy |
| `shop_cosmetic_and_item_preview` | `separate_authority` | Owned/selected preview context | Catalog, price, purchase, Coins, Gacha, Premium, payment |
| `public_profile` | `owner_decision_required` | None | Public privacy/redaction and profile projection |
| `stats_dashboard` | `legacy_compatibility` | Identity and XP/level header only | History, analytics, daily/quest/Monster charts |
| `premium_account_display` | `separate_authority` | Identity header only | Offer, entitlement, expiry, claim, payment, grace |
| `quest_reward_result` | `legacy_compatibility` | Post-result Player refresh | Quest, reward settlement, claim, idempotency |

The matrix records the exact legacy dependencies, safe replacement scope,
forbidden replacement scope, and whether a refresh is allowed after a
server-committed mutation. A refresh is a read after settlement; it never
replays the mutation.

### Adapter rules

1. A surface may consume the snapshot only for the listed presentation
   fragment; the surface keeps its own authority for all other data.
2. No adapter may infer ownership from Shop catalog data or from client state.
3. No adapter may infer World progression, Quest progress, reward truth,
   Premium entitlement, or encounter correctness from the snapshot.
4. No adapter may merge persistent HP with encounter HP.
5. Equipment and Spirit adapters remain read-only and do not create mutation
   authorities.
6. Legacy routes remain available until a separately approved migration.
7. The endpoint is authenticated-player presentation only; public profile is
   not an automatic consumer.

## Validation contract

`tests/test_a025_player_presentation_api_contract.py` covers:

- immutable envelope and nested immutable values;
- deterministic JSON serialization;
- exact transport top-level shape;
- rejection of unknown and forbidden World, Quest, Shop, Premium, battle,
  reward, and encounter fields;
- rejection of active encounter HP;
- rejection of Hero functional/combat fields;
- rejection of equipment combat statistics and Spirit combat effects;
- acceptance of a valid B028/B030-safe projection, including partial optional
  projections;
- status mapping and display identity handling;
- exact 14-surface matrix and complete classification counts;
- static absence of route, SQL, and mutation wiring.

The A025 candidate is limited to the four requested contract/test/document
files. It does not modify `app.py`, HTML, JavaScript, schema, runtime state,
payment, Production, or deployment configuration.

## Owner decision packet

```text
TOTAL_SURFACES=14
SNAPSHOT_ADAPTERS=5
SEPARATE_AUTHORITY=6
LEGACY_COMPATIBILITY=2
OWNER_DECISION_REQUIRED=1
```

Recommendation: `RECOMMENDATION_A` — build the authenticated Player
Presentation read API next, using B028 as the canonical aggregator and B030
as the read service. Keep the route implementation, authentication policy,
and each surface's non-player authorities as separately governed work.
