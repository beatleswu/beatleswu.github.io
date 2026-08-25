# D019 Acquisition Producer Adapter Core V1

Status: pure adapter candidate; no producer runtime integration

## Purpose

D019 provides one narrow translation boundary from an already committed
producer result to the D018 `CanonicalAcquisitionResult` envelope. It does
not execute a grant, purchase, retry, claim, consume, equip, wear, or
database operation.

The four supported families are:

* `MONSTER_DROP`
* `QUEST_REWARD`
* `PREMIUM_REWARD`
* `SHOP_COIN_PURCHASE`

Each function returns an immutable `AcquisitionAdapterResult` with exactly one
of these statuses:

* `READY`: a validated D018 result is present;
* `INSUFFICIENT_AUTHORITY_EVIDENCE`: the result is absent and the reason and
  missing fields explain why the adapter failed closed.

No adapter returns a partially populated D018 envelope.

## Committed-result boundary

The adapter input must contain an explicit committed-result marker or a
family-specific committed terminal status. A generic `success`, UI string,
catalog record, entitlement flag, or preview is not enough by itself.

The accepted markers are:

| Family | Accepted committed evidence | Rejected evidence |
| --- | --- | --- |
| Monster | `committed=true`, `settlement_committed=true`, or `settlement_status=COMMITTED/SETTLED` | defeat UI, animation, `preview=true`, uncommitted drop preview |
| Quest | `committed=true`, `claim_committed=true`, `claim_status=SETTLED`, `transaction_status=COMMITTED/SETTLED`, or `status=COMMITTED/SETTLED` | `claim_status=SUCCESS`/`status=SUCCESS` without a separate marker; completed/claimable state without a settled claim |
| Premium | `committed=true`, `claim_committed=true`, `reward_committed=true`, `claim_status=SETTLED`, `reward_status=SETTLED`, `transaction_status=COMMITTED/SETTLED`, or `status=COMMITTED/SETTLED` | `claim_status=SUCCESS`/`reward_status=SUCCESS`/`status=SUCCESS` without a separate marker; entitlement-only state |
| Shop | `committed=true`, `purchase_committed=true`, or `purchase/operation/transaction_status=COMMITTED/SETTLED` | Shop offer/catalog alone |

Machine-readable status split:

```text
SUCCESS_STATUS_IS_COMMIT_EVIDENCE=NO
COMMITTED_OR_SETTLED_STATUS_IS_COMMIT_EVIDENCE=YES
VALID_RESULT_STATUSES=SUCCESS,COMMITTED,SETTLED
COMMITTED_EVIDENCE_STATUSES=COMMITTED,SETTLED
```

`SUCCESS` remains a valid producer-result vocabulary value, but it becomes
commit evidence only when a separate boolean commit marker is present. The
adapter never treats a generic `SUCCESS` field as persistence proof.

Source-specific aliases (`claim_operation_id`, `purchase_operation_id`,
`item_acquisition_event_id`, and similar) only select a value that is already
present in the committed producer payload. They never generate an operation
or lineage ID.

## Required authority facts

Before returning `READY`, an adapter must have explicit values for:

* `item_id`, positive `quantity`, and `item_class`;
* `source_operation_id` and `source_reference`;
* `destination`, `ownership_authority`, and `ownership_reference`;
* `resulting_quantity`, including an explicit `null` for a truthful set-like
  result;
* all three capability booleans;
* `replayed` as a result/transport fact;
* `lineage_event_id` for committed acquisition evidence.

`is_new` is deliberately different: if the producer does not prove whether
the identity was owned before the original grant, D019 passes `null` to D018.
It never calculates `is_new = !replayed`.

D018 remains the final capability and replay/new-evidence validator. For
example, a replay with `is_new=true` still requires D018's verified
pre-grant ownership evidence.

## Authority boundaries

The adapters do not write any domain authority:

* no `player_inventory` or `player_wardrobe` writes;
* no Shop, pet inventory, Coins, capacity, entitlement, or reward writes;
* no D5C item consumption;
* no D5A event append.

D5A remains acquisition lineage evidence. D5C remains item-use/consume
authority. Acquisition, equip, use, consume, and wear are never collapsed
into one result transition.

## Locked special items

`go_stone_black` is accepted only as a `TROPHY` in `PLAYER_INVENTORY` with
`can_equip=false`, `can_use=false`, and `can_wear=false`. Its optional status
is `TROPHY_INVENTORY_ONLY_NO_COMBAT_POWER`.

`xp_amulet` may be described as an `ACCESSORY`, but must carry
`special_status=HOLD_FOR_AUTHORITY` and all three capabilities false. D019
does not activate any XP, equip, or combat semantics.

## Current producer readiness

The adapter functions are pure-core `READY` for complete committed facts.
The current producer systems are not silently declared runtime-ready:

* Monster needs a committed settlement/result wrapper around its legacy loot
  structures;
* Quest needs a settled claim/reward payload, not merely durable completion;
* Premium needs an acquisition component with the D018 quantity, class,
  capabilities, ownership, and lineage facts;
* Shop needs the committed C019 purchase result boundary and normalized
  ownership evidence. C019 remains the purchase authority and is not edited.

The exact evidence and next task for each family are recorded in
`d019_producer_adapter_readiness_matrix.json`.

## Scope

This candidate contains only `acquisition_result_adapters.py`, focused pure
tests, this contract document, and the readiness matrix. It does not modify
`app.py`, producer modules, D018, schemas, migrations, UI, ownership state,
Production, or deployment configuration.
