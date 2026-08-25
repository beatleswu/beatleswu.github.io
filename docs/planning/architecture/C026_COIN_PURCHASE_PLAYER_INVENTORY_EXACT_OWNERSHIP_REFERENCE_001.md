# C026 Coin Purchase `player_inventory` Exact Ownership Reference

Task: `C026_COIN_PURCHASE_PLAYER_INVENTORY_EXACT_OWNERSHIP_REFERENCE_001`

C026 is a current-master Commerce foundation candidate. It forward-integrates
the accepted C019 transaction core and C023 acquisition writer, then closes
the producer-side D022/D023 gap for functional Equipment and inventory-only
Trophy rows.

## Provenance and current-master overlay

| Fact | Value |
|---|---|
| Original C026 implementation base | `7d876fdb6fc9ac506f6bebfa622a62e51187d442` |
| Current candidate base after F016 overlay | `1566888b2327e39789381c5fb4f59d33fb73d732` |
| C019 accepted semantics | `cb8f7e07350edb873c6300bfae3680819b0329f6` |
| C023 accepted semantics | `ab588aa28cbae92a8c29bffe575b67b1f3207793` |
| C021-R1 reference | `8af8e69cd22b1fddb2dab8e9b769067091d51d90` |
| C025 current-master contract | `shop_offer_identity_projection.py` |
| D022 contract reference | `7ab57ee78c74aa4526bfa29b6a8a0aa998604882` |
| B033 schema owner | `migrations/equipment_canonical_slot_v1.py` in current master |

The accepted Commerce files were forward-integrated as source-level semantics
onto the current master. Old branch history, duplicate B033 migration history,
and unrelated planning artifacts were not imported.

## Scope and authority boundary

```text
server-resolved CoinShopOffer
              |
              v
caller-owned purchase_with_coins transaction
              |
              +--> user_stats.coins debit
              +--> destination acquisition
              |       |
              |       +--> player_inventory INSERT + exact id
              |       +--> shop_inventory quantity
              |       +--> player_wardrobe ownership
              +--> D5A ITEM_ACQUISITION evidence
              +--> result_payload
              +--> operation_status=COMMITTED
```

C026 does not modify `app.py`, HTTP routes, frontend, Production, or the D023
read-side bridge. It does not make C025 execute a purchase. C025 remains the
pure server-fact offer identity/version projection; C019 remains the purchase
and exactly-once authority.

`player_inventory` remains the ownership authority. The B033
`canonical_slot` column is a derived server projection consumed by Commerce;
it is not an ownership identity. The injected slot source is the only source
of functional Equipment slot facts at this boundary.

## Exact row-id producer contract

For `destination == "player_inventory"`, the acquisition writer now:

1. validates duplicate policy and server-derived functional slot;
2. detects whether the current disposable schema has B033's
   `canonical_slot` column;
3. executes the INSERT;
4. captures the primary key returned by that INSERT itself;
5. validates that the captured ID is a positive, non-boolean integer; and
6. returns the canonical reference:

```text
player_inventory:{row_id}
```

SQLite uses the INSERT cursor's `lastrowid`. PostgreSQL uses
`INSERT ... RETURNING id`. No second query infers the inserted row. In
particular, C026 does not use `MAX(id)`, `ORDER BY id DESC`, timestamps,
`(user_id,equip_id)`, `canonical_slot`, D5A IDs, or purchase-operation IDs as
ownership identity.

For post-B033 schemas, functional Equipment writes `canonical_slot` from the
injected server resolver and persists `equipped=0`. For a pre-B033 disposable
schema, the old insert shape remains usable while the same exact row ID is
captured. Trophy rows remain slotless.

## Result and replay contract

`AcquisitionOutcome` carries `ownership_reference`. The value is required for a
new successful `player_inventory` acquisition and is included in its nested
ownership result. `CoinPurchaseResult` carries the same single canonical value
at top level. If both values are present during payload recovery, they must be
identical.

`canonical_payload()` persists the reference in
`coin_purchase_operations.result_payload` before the operation is changed to
`COMMITTED`. A committed replay reads the stored payload and returns the
original reference without querying current inventory state.

Example:

```text
operation A -> INSERT row 101 -> player_inventory:101 -> COMMITTED
operation B -> INSERT row 102 -> player_inventory:102 -> COMMITTED
replay A   -> stored player_inventory:101
```

`shop_inventory` and `player_wardrobe` continue to return a null ownership
reference in C026. Their read-side reference derivation remains D023-owned.

Old non-`player_inventory` payloads remain readable when the optional field is
absent. C026 never synthesizes a missing reference during replay. A committed
`player_inventory` payload produced by C026 must contain the exact reference;
otherwise replay fails closed.

## Transaction boundary

The service remains caller-transaction-owned. It never calls `commit()` or
`rollback()`. The following operations remain coupled until the caller
commits:

```text
reserve purchase operation
  -> debit Coins and currency_log
  -> INSERT player_inventory
  -> capture exact row ID
  -> append D5A ITEM_ACQUISITION
  -> persist result_payload
  -> mark operation COMMITTED
  -> caller commit
```

Any failure after the ownership INSERT is still rolled back by the caller,
removing the row, Coin debit, operation reservation, and D5A evidence.

D5A `lineage_event_id` remains evidence only. It is deliberately distinct from
`ownership_reference`, `purchase_operation_id`, and `canonical_slot`. D5C is
not imported or used for acquisition.

## Locked identities and unchanged destinations

- `xp_amulet` remains `HOLD_FOR_AUTHORITY`; C026 inserts no row for it.
- `go_stone_black` remains `TROPHY / INVENTORY_ONLY / NO_COMBAT_POWER`; C026
  does not make it a functional Coin-sale item.
- `REJECT_IF_OWNED` still fails before a second insert and rolls back the
  reserved operation and debit.
- `ALLOW_DUPLICATE` creates independent rows and independent references.
- `shop_inventory` quantity stacking and `player_wardrobe` ownership behavior
  remain unchanged.

## Schema decision

`NEW_OPERATION_SCHEMA_COLUMN_REQUIRED=NO`.

The existing C019 `result_payload` JSON contract truthfully stores the optional
reference and preserves deterministic replay. No migration was added or
changed. The only equipment schema authority is the current-master B033
migration; C026 does not duplicate it.

## Validation evidence

The focused C026 suite covers:

- exact INSERT row ID and `player_inventory:{row_id}` format;
- committed result payload and replay stability;
- two `ALLOW_DUPLICATE` rows with distinct references;
- first-operation replay after a second purchase;
- no latest-row inference patterns;
- lineage and result-persistence rollback;
- zero service commits/rollbacks;
- post-B033 server slot projection and pre-B033 insert compatibility;
- client slot rejection, `xp_amulet`, `go_stone_black`, and unknown-item
  fail-closed behavior;
- unchanged `shop_inventory` and `player_wardrobe` results;
- C025-to-C019 normalized offer compatibility;
- distinct D5A, operation, and ownership identities.

PostgreSQL validation is environment-gated. If no explicitly disposable
PostgreSQL target is present, SQLite evidence must not be described as proof of
PostgreSQL concurrency or `RETURNING` behavior.
