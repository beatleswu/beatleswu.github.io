# D022 Shop Acquisition Ownership Reference Contract Recon V1

Status: read-only destination contract reconciliation; docs-only candidate

## Scope and provenance

This recon defines how a future Shop result bridge may populate D018's
`ownership_reference`. It does not add that field to C019/C023, wire a Shop
route, read or write a database at runtime, or create an ownership authority.

| State | SHA | Meaning | Present in current `origin/master`? |
| --- | --- | --- | --- |
| Current master | `b75308d44806bb7c2e2b131a73ba06a71c188b3c` | Runtime baseline used for this recon | Yes |
| D020 | `d251ed92c46ebf6e7806ba4258ba6ba6b032e4a6` | D018 envelope plus D019 adapter candidate | No |
| D021 | `3e764df5dbc1aefb487f770d7f2ac673362978b3` | Producer readiness recon candidate | No |
| C023 | `ab588aa28cbae92a8c29bffe575b67b1f3207793` | Accepted C019/C023 Shop candidate | No |
| C024 | `IN_PROGRESS` | Concurrent catalog/route recon | Not used; not assumed |

The D022 worktree was created from freshly fetched `origin/master`. C023 was
inspected by exact SHA in a detached inspection worktree. C024 is deliberately
not treated as current catalog or runtime evidence.

At the initial fetch, `origin/master` was
`b75308d44806bb7c2e2b131a73ba06a71c188b3c`. Before publication it advanced to
`e2669bfa8582239dd001dbb41b2cd134923e9e27` through the independent E026/E027
player-presentation path. The drift touches `app.py`, player presentation
read modules, and their tests, but none of the three D022 artifacts. No
rebase or merge was performed; this candidate remains based on its recorded
start base and has no semantic collision with the drift.

## Contract boundary

D018 `ownership_reference` identifies the authority-owned state represented by
the acquisition result. It is not any of the following:

* the C019 purchase idempotency key;
* the D5A `lineage_event_id` or outbox row identity;
* `canonical_slot`;
* a presentation item ID without its authority/user binding; or
* a value selected by the client.

The future bridge must consume a committed C019 operation result and trusted
authenticated user context. A reference must be recoverable from the
authority after commit and must be identical on replay of the same committed
purchase operation.

## Accepted C023 input facts

`CoinPurchaseResult` contains `operation_id`, offer/item identity, quantity,
raw destination, `ownership_result`, `is_new`, capability booleans,
`lineage_event_id`, offer version, and replay delivery metadata. The durable
`coin_purchase_operations` row is keyed by `(user_id,purchase_operation_id)`,
stores the canonical result payload, and reaches `COMMITTED` only after the
caller-owned transaction has completed the Coin debit, destination mutation,
D5A event append, and result update.

`AcquisitionOutcome` contains the destination, item identity, granted
quantity, `new_quantity`, ownership state, `is_new`, capabilities, and
presentation metadata. It does not contain an ownership reference or a
destination row primary key.

C023's `SqlAcquisitionAuthority` actually writes only:

1. `shop_inventory` for `STACK` offers;
2. `player_inventory` for `WEAPON`, `ARMOR`, `ACCESSORY`, or `TROPHY` offers;
3. `player_wardrobe` for `COSMETIC` offers.

The C023 destination vocabulary also names `capacity`, `credit`, and
`entitlement`, but the accepted writer rejects those destinations.
`pet_inventory` is not a C023 destination. They are therefore not counted as
supported destinations in this recon.

## Destination ownership-reference matrix

| C019 destination | D018 destination | Authority | Truthful reference contract | Duplicate policy | Replay result | Classification |
| --- | --- | --- | --- | --- | --- | --- |
| `shop_inventory` | `STACK_INVENTORY` | `shop_inventory` | `shop_inventory:{user_id}:{item_key}`, the existing primary-key aggregate `(user_id,item_key)` | `STACK` only | Same aggregate reference; stored `new_quantity` remains the result of the original grant even if later consumption changes current quantity | `NEEDS_DESTINATION_READ_ADAPTER` |
| `player_inventory` | `PLAYER_INVENTORY` | `player_inventory` | `player_inventory:{row_id}`, where `row_id` is the authority table primary key for the exact acquired row | `ALLOW_DUPLICATE` or `REJECT_IF_OWNED` | Must replay the exact acquired row reference; a new operation may create a different row under `ALLOW_DUPLICATE` | `NEEDS_PRODUCER_RESULT_EXTENSION` |
| `player_wardrobe` | `PLAYER_WARDROBE` | `player_wardrobe` | `player_wardrobe:{user_id}:{item_id}`, the unique set-membership key `(user_id,item_id)` | `REJECT_IF_OWNED` only | Same set-membership reference; a different operation for an owned cosmetic is rejected, not a second grant | `NEEDS_DESTINATION_READ_ADAPTER` |

### `shop_inventory`

The table's primary key is `(user_id,item_key)` and C023 updates that one row
with `ON CONFLICT ... DO UPDATE`, returning the authoritative post-grant
`new_quantity`. The reference is therefore an aggregate ownership key, not a
purchase-specific row and not a newly invented ID. Genuine purchases of the
same item reuse the reference while changing the post-grant quantity. A replay
of one committed operation must reuse the stored result and the same
reference.

The accepted result itself does not carry `user_id` or
`ownership_reference`. A future read-only bridge must bind the authenticated
user to the committed operation row, verify the destination and item key, and
verify committed stack ownership after the caller transaction. It must not use
the current quantity as a substitute for the stored result quantity.

### `player_inventory`

The authority table has a durable `id` primary key, but C023's writer inserts
the row and returns an ownership count (`new_quantity`) without the row ID.
`ALLOW_DUPLICATE` is an accepted
policy: two committed purchases can create two rows with the same
`(user_id,equip_id)`. Consequently that pair is not a unique ownership
reference for this destination.

The current writer does not capture the inserted row ID in `AcquisitionOutcome`,
`CoinPurchaseResult`, `coin_purchase_operations.result_payload`, or the D5A
payload. A post-hoc `MAX(id)`, `ORDER BY id DESC LIMIT 1`, or timestamp lookup
would be non-authoritative and is forbidden. C019/C023 must first persist the
exact returned row primary key as the ownership reference (or an equivalently
bound authority-owned identity) inside the committed result. Only then can a
generic Shop bridge support this destination.

`canonical_slot` remains an Equipment projection. It proves slot semantics,
not ownership identity, and cannot replace the row reference.

### `player_wardrobe`

The authority enforces `UNIQUE(user_id,item_id)` and C023 accepts only
`REJECT_IF_OWNED`. A composite set-membership reference is therefore truthful
and stable; a row ID is not required for the ownership identity. The accepted
operation row supplies the authenticated user binding and the result supplies
the item identity. A post-commit read adapter must verify that the unique row
exists before emitting the D018 result.

## Duplicate and replay rules

| Policy | Ownership identity | Same operation replay | Different operation |
| --- | --- | --- | --- |
| `STACK` | One aggregate key `(user_id,item_key)` | Same reference and original stored result | Same reference, new committed quantity result |
| `REJECT_IF_OWNED` set ownership | One composite membership key | Same reference and original stored result | Fail closed as already owned; no new acquisition result |
| `ALLOW_DUPLICATE` row ownership | One authority row primary key per grant | Same row reference from persisted result | New row reference for each committed operation |

Purchase operation identity and ownership identity remain separate. A purchase
operation may be replay-safe without being an ownership reference. D5A records
why the acquisition was committed; `event_id`, `lineage_id`, and
`lineage_event_id` must not be reinterpreted as the owned row or aggregate.

## Commit timing

`PRE_COMMIT_NOT_ALLOWED`: a D018 result must never be published as a committed
acquisition before the C019 caller transaction commits.

For `shop_inventory` and `player_wardrobe`, the next bridge should use
`POST_COMMIT_READ_ONLY`: recover the committed operation, bind its trusted
`user_id`, verify the authority row/key, and normalize the D018 destination.
For `player_inventory`, the producer extension must capture the inserted row
identity `IN_TRANSACTION_WITH_EXPLICIT_COMMIT_EVIDENCE`, persist it in the
canonical operation result and D5A payload, and make it available for replay.

No bridge may open or commit a transaction, retry a purchase, or create a
second ownership ledger.

## D5A, special items, and authority locks

`D5A_IS_ACQUISITION=YES`; `D5C_IS_USE=YES`. No C023 path imports or uses D5C.
The D5A `ITEM_ACQUISITION` event is evidence and lineage, not the ownership
reference.

C023 rejects `go_stone_black` as a Coin Shop product and preserves its
`TROPHY / INVENTORY_ONLY / NO_COMBAT_POWER` lock. C023 rejects `xp_amulet` and
preserves `HOLD_FOR_AUTHORITY`. This recon introduces no reference scheme that
can reclassify either item.

## Bridge decision

`SHOP_RESULT_BRIDGE_DECISION=PARTIAL_BRIDGE_READY_SOME_DESTINATIONS_BLOCKED`.

The stack aggregate and wardrobe set-membership references are contract-ready
from existing durable authorities, but both need a narrow post-commit read
adapter because the accepted result does not carry the reference directly.
Player Equipment remains blocked until C019/C023 persists the exact inserted
row identity. Implementing a generic fallback using `MAX(id)`, latest-row
ordering, `lineage_event_id`, `purchase_operation_id`, or `canonical_slot`
would be an authority violation.

Recommended next D implementation:

`SHOP_RESULT_BRIDGE_READ_ADAPTER_FOR_STACK_AND_WARDROBE_PLUS_PLAYER_INVENTORY_RESULT_EXTENSION`.

## Validation and safety

Static inspection was performed against exact D020 and C023 objects. The
accepted C023 focused characterization was run in a detached exact-SHA
worktree:

```text
tests/test_c019_atomic_coin_purchase_transaction_core.py
tests/test_c023_coin_shop_equipment_canonical_slot_writer.py
31 passed
```

This D022 candidate changes only the three recon documents. It does not
modify `app.py`, C019/C023 modules, D020 modules, C024 work, schema files,
frontend files, databases, Production, or deployment.
