# C029 — C025 Player-Inventory Functional-Equipment Offer Projection

Status: `OWNER_REVIEW_CANDIDATE`

This document records a narrow server-fact projection extension. It does not
enable Shop routes, execute purchases, debit Coins, grant ownership, or change
Production.

## Provenance

- Current implementation base: `7c30a44867501ef936f84a41f2b25032c186f367`
- Current repository: `D:\go-website`
- C025 authority extended: `shop_offer_identity_projection.py`
- C019/C026/C027 and D024 are downstream compatibility authorities; none are
  copied into this projection module.

## Authority boundary

C029 accepts caller-supplied, already server-resolved Shop facts and returns a
C021-compatible normalized offer. The caller remains responsible for resolving
the current catalog, price, eligibility, and Equipment identity.

The projection does not own:

- `EQUIPMENT_DEFS` or `canonical_slot`
- Coin balance or debit
- `player_inventory`, `player_wardrobe`, or `shop_inventory` mutation
- purchase operation identity or replay
- D5A/D5C lineage
- HTTP routes, UI, or Production configuration

`C025_CANONICAL_SLOT_AUTHORITY=NO` and
`CLIENT_CANONICAL_SLOT_AUTHORITY=NO`. C026 remains responsible for deriving
the functional Equipment slot from its injected server-owned slot source.

## New ready matrix

The existing `STATIC_SHOP_ITEM` family now has one additional, explicit ready
shape:

| Fact | Required value |
| --- | --- |
| destination | `player_inventory` |
| acquisition class | `WEAPON`, `ARMOR`, or `ACCESSORY` |
| quantity | `1` |
| duplicate policy | `REJECT_IF_OWNED` or `ALLOW_DUPLICATE` |
| offer family | existing static Shop item family |
| currency | `COINS` |
| price | positive, non-boolean integer |
| grant profile | one grant agreeing with the item, quantity, and destination |

The business identity remains `shop.static.<authoritative item_key>`. The
semantic version remains the existing `sha256-canonical-server-facts-v1`
projection. It includes the destination, class, price, quantity, duplicate
policy, and grant profile, so a material Equipment fact change produces a new
version while the business identity remains stable.

The following are deliberately not ready through this extension:

- daily, bundle, or multi-grant Equipment
- `TROPHY`, `COSMETIC`, `CONSUMABLE`, `SPIRIT_CONSUMABLE`, `XP_CONSUMABLE`, or
  `MATERIAL` targeting `player_inventory`
- `pet_inventory`, entitlement, capacity, credit, or unknown destinations
- `STACK` or undefined duplicate policies for functional Equipment
- `xp_amulet` (`AUTHORITY_HOLD`)
- `go_stone_black` (`TROPHY_INVENTORY_ONLY`)
- Premium cash, Premium entitlement, gacha, and zero-price/free grants

The extension intentionally does not add `player_inventory` to the generic
ready-destination set. Readiness is established only by the static functional
Equipment branch above.

## Downstream compatibility evidence

For each supported Equipment class, the test fixture projects C025 facts,
passes `NormalizedShopOffer.as_c019_mapping()` to
`CoinShopOffer.from_mapping()`, and executes the existing C026 acquisition
authority in a disposable SQLite schema. C026 then:

- derives `weapon`, `armor`, or `accessory` from its injected server slot map;
- writes `equipped=0` and the post-B033 `canonical_slot` projection;
- captures the exact inserted `player_inventory.id`; and
- returns `player_inventory:{row_id}`.

The tests also cover both C026 duplicate policies. `REJECT_IF_OWNED` rejects a
second distinct operation without a second row, while `ALLOW_DUPLICATE`
produces distinct exact row references and preserves the first reference on
replay. C025 itself creates no operation, mutation, or replay state.

The D024 bridge is exercised against the committed result. It receives the
stored exact reference without a `player_inventory` identity lookup.

## Current catalog overlay

`CURRENT_REAL_FUNCTIONAL_EQUIPMENT_OFFER_COUNT=0` on this current master.
The source facts were checked read-only:

- `app.py:SHOP_ITEMS` is the existing stackable/training/pet/collection Shop
  catalog and contains no functional Equipment identities;
- `app.py:COSMETIC_COMMERCE_PRODUCTS` is a wardrobe product authority, not a
  functional Equipment catalog; and
- the daily Shop and gacha paths consume their existing item/appearance pools,
  but are not promoted by C029.

This zero count does not block the projection contract. C029 adds no product,
price, catalog entry, or Production offer.

`DAILY_PLAYER_INVENTORY_EQUIPMENT_READY=NO` remains locked. A later task must
provide a durable server-owned daily Equipment identity and an explicit
Owner-reviewed catalog mapping before daily Equipment can be considered.

## Validation scope

The focused C029 suite proves:

- all three functional Equipment classes and both accepted duplicate policies;
- quantity, duplicate-policy, class, lock, daily, and destination fail-closed
  cases;
- client price and canonical-slot rejection;
- stable `shop.static.<item_key>` identity and deterministic semantic version;
- unchanged stackable and wardrobe projection shapes;
- C019 mapping compatibility;
- C026 acquisition, server slot derivation, exact ownership reference, and
  duplicate behavior; and
- D024 canonical result adaptation without player-inventory identity lookup.

Validation evidence on the isolated current-master worktree:

```
C025_TESTS=22 passed
C029_TESTS=27 passed
C026_REGRESSION=20 passed
D024_REGRESSION=16 passed
COMBINED=85 passed
C019_EXPLICIT_OFFER_CONTRACT_CHECKS=2 passed
```

No PostgreSQL or Production access is required for this projection-only change;
the previously accepted C027 PostgreSQL evidence remains downstream evidence
for unchanged C026 runtime behavior.

## Gate result

```
C025_PLAYER_INVENTORY_FUNCTIONAL_EQUIPMENT_READY=YES
SUPPORTED_PLAYER_INVENTORY_CLASSES=WEAPON,ARMOR,ACCESSORY
PLAYER_INVENTORY_QUANTITY_REQUIRED=1
PLAYER_INVENTORY_DUPLICATE_POLICIES=REJECT_IF_OWNED,ALLOW_DUPLICATE
C025_CANONICAL_SLOT_AUTHORITY=NO
CLIENT_CANONICAL_SLOT_AUTHORITY=NO
CLIENT_PRICE_AUTHORITY=NO
PURCHASE_OPERATION_ID_READY=NO
DAILY_PLAYER_INVENTORY_EQUIPMENT_READY=NO
PRODUCTION_QUERY=NO
PRODUCTION_MUTATION=NO
FEATURE_ENABLED=NO
DEPLOY=NO
MASTER_MERGE=NO
```
