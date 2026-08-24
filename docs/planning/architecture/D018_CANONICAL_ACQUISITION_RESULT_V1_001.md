# D018 Canonical Acquisition Result V1

Status: implementation candidate; pure contract only

## Decision

`CanonicalAcquisitionResult` is a cross-producer result envelope. It is not
an inventory, wardrobe, currency, capacity, entitlement, or item-use ledger.
It describes one already-authorized and committed acquisition so that a
Backpack, Wardrobe, or reward surface can present the same facts regardless
of whether the producer was Monster, Quest, Premium, Shop, Starter, Admin,
Legacy, or Event.

Ownership remains domain-specific:

* functional equipment and inventory state: `player_inventory`;
* pure cosmetic state: `player_wardrobe`;
* Coins: `user_stats.coins`;
* question capacity: the existing capacity authority;
* Premium entitlement/reward state: the existing Premium authorities;
* acquisition evidence: D5A `domain_event_outbox` / acquisition lineage;
* item use and consumption: D5C, never this result envelope.

`OWNERSHIP_AUTHORITY_REMAINS_DOMAIN_SPECIFIC=YES` is therefore a contract
invariant, not a suggestion to create a universal ownership table.

## Envelope

The immutable V1 fields are:

| Field | Meaning |
| --- | --- |
| `contract_version` | Exact value `CANONICAL_ACQUISITION_RESULT_V1`. |
| `item_id` | Stable identity of the acquired object or governed benefit. |
| `quantity` | Positive quantity granted by this operation. |
| `source_type` | One of the eight stable producer categories below. |
| `source_operation_id` | Server-bound operation identity for the grant. |
| `source_reference` | Stable source/business reference, not display text. |
| `destination` | Existing authority receiving the result. |
| `ownership_authority` | Domain authority name, such as `player_inventory`. |
| `ownership_reference` | Recoverable reference in that authority. Required even when the destination is not a conventional item table. |
| `resulting_quantity` | Non-negative post-grant quantity, or `null` when set-like state does not expose a meaningful quantity. |
| `is_new` | `true`, `false`, or `null` when the authority cannot truthfully answer the set-like question. It is not derived from replay status. |
| `can_equip` | Existing, server-authorized capability only. |
| `can_use` | Existing, server-authorized use capability only. |
| `can_wear` | Existing, server-authorized cosmetic-wear capability only. |
| `replayed` | Delivery/idempotency metadata: the committed result is being returned again. |
| `lineage_event_id` | D5A or equivalent committed lineage evidence identifier. |
| `item_class` | V1 taxonomy used to validate capability contradictions. |
| `metadata` | Bounded JSON object for non-authoritative presentation/context facts. |

The Python module validates all fields, rejects unknown top-level fields when
deserializing, freezes the object and metadata, and serializes with stable
sorted JSON keys. It does not perform a grant, purchase, consume, equip,
wear, or database write.

## Source and destination vocabulary

Source types are exactly:

`MONSTER_DROP`, `QUEST_REWARD`, `PREMIUM_REWARD`, `SHOP_COIN_PURCHASE`,
`STARTER_GRANT`, `ADMIN_GRANT`, `LEGACY_GRANT`, and `EVENT_REWARD`.

Destinations are exactly:

`PLAYER_INVENTORY`, `PLAYER_WARDROBE`, `STACK_INVENTORY`, `ENTITLEMENT`,
`QUESTION_CAPACITY`, `CREDIT`, `TROPHY_OWNERSHIP`, and
`OTHER_EXISTING_AUTHORITY`.

The envelope normalizes these controlled vocabulary values to uppercase, but
does not fuzzy-match item IDs, source references, display labels, or producer
names.

## Capability rules

The V1 item classes are `WEAPON`, `ARMOR`, `ACCESSORY`, `CONSUMABLE`,
`SPIRIT_CONSUMABLE`, `XP_CONSUMABLE`, `MATERIAL`, `COSMETIC`, and `TROPHY`.

* Weapons, armor, and accessories may declare `can_equip=true` only when
  the existing authority already supports that capability.
* Consumables and Spirit consumables must declare `can_use=true`.
* Pure cosmetics land in `player_wardrobe`, declare `can_wear=true`, and do
  not become usable or combat equipment through this contract. The only
  exception for equip terminology requires explicit metadata
  `capability_basis=EXISTING_EQUIP_SEMANTICS`.
* Materials and trophies have no direct use/equip/wear capability.

`go_stone_black` is locked as `TROPHY` at `PLAYER_INVENTORY` with all three
capabilities false. Its optional special status is
`TROPHY_INVENTORY_ONLY_NO_COMBAT_POWER`.

`xp_amulet` remains `HOLD_FOR_AUTHORITY`. A result may describe ownership,
but it must carry `special_status=HOLD_FOR_AUTHORITY` and all three
capabilities false. D018 does not activate XP, equip, or combat behavior.

## New and replay semantics

`is_new` is a fact about ownership immediately before the original grant. A
transport retry does not imply a new acquisition. A replay with
`is_new=false` (or `null`) is valid. A replay with `is_new=true` is accepted
only with bounded metadata proving `ownership_evidence.verified=true`,
`ownership_evidence.pre_grant_owned=false`, and naming the authority that
performed the observation. Without that evidence the contract fails closed.

This prevents `replayed=False` from becoming a proxy for `is_new=True`, and
prevents replay presentation from being mistaken for another grant.

## D5A / D5C boundary

`D5A_IS_ACQUISITION=YES` and `D5C_IS_USE=YES`.

The envelope can report `can_use=true` for a consumable, but it contains no
`used`, `consumed`, `equipped`, or `worn` transition. Therefore:

* `ACQUIRE_EQUALS_USE=NO`;
* `ACQUIRE_EQUALS_EQUIP=NO`;
* `ACQUIRE_EQUALS_CONSUME=NO`.

Any producer that cannot supply a server operation identity, destination,
ownership reference, truthful capabilities, and committed lineage event is
not a direct V1 adapter. It requires a scoped producer-adapter task; D018
does not silently fill those fields from UI text or guessed state.

## Current producer readiness

The deterministic matrix in
`d018_acquisition_producer_matrix.json` records the current evidence and the
missing adapter fields. The current result shapes are heterogeneous:

* Monster settlement returns legacy loot/appearance structures from `app.py`;
* current Daily/Quest-style rewards return reward maps rather than this
  envelope;
* Premium claim/bundle services have operation, ownership, and D5A evidence
  but use their own result dataclasses;
* the accepted C019 `CoinPurchaseResult` has a strong operation/result shape,
  but is not this contract and is not edited here;
* Starter/Admin/Legacy/Event and equipment/consumable/trophy writers use
  domain-specific result maps or direct authority mutations.

Those sources remain authoritative. D018 supplies the common target shape;
it does not retrofit runtime producers or create a universal grant writer.

## Explicit scope boundary

This candidate changes only the pure module, pure tests, the contract
documentation, and the deterministic producer matrix. It does not change
`app.py`, schemas/migrations, live producer behavior, D5A/D5C behavior, C019
modules, UI, ownership state, Production, deployment, or master.
