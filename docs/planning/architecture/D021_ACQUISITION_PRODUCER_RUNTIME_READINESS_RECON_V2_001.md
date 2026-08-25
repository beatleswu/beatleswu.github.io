# D021 Acquisition Producer Runtime Readiness Recon V2

Status: read-only reconciliation; docs-only candidate

## Scope and provenance

This recon compares the current canonical master runtime with three distinct
candidate states. It does not wire an adapter, change a producer, run a
migration, or access Production.

| State | SHA | Meaning | In current `origin/master`? |
| --- | --- | --- | --- |
| Current master | `b75308d44806bb7c2e2b131a73ba06a71c188b3c` | Runtime authority used for the recon | Yes |
| D020 | `d251ed92c46ebf6e7806ba4258ba6ba6b032e4a6` | D018 exact contract plus D019 and D019-R1, current-master candidate | No |
| C022 | `b08c822573051635c92070d696ca43fcb49020f1` | C019/C020/C021 commerce foundation, current-master candidate | No |
| F013 | `becea9efb54679526ebdfda842da5b798c691392` | Monster/Battlefield Boss read-only recon; no runtime implementation | No runtime changes |

The current master tree does not contain `canonical_acquisition_result.py`,
`acquisition_result_adapters.py`, `coin_purchase_authority.py`,
`shop_offer_adapter.py`, or `shop_offer_authority.py`. Therefore a candidate
result is never described as live merely because its accepted SHA was inspected.

## D020 fact contract used for this audit

For one committed item or governed benefit component, the required envelope
facts are:

`item_id`, `quantity`, `source_operation_id`, `source_reference`,
`destination`, `ownership_authority`, `ownership_reference`,
`resulting_quantity`, `can_equip`, `can_use`, `can_wear`, `replayed`,
`lineage_event_id`, `item_class`, and `is_new`.

`resulting_quantity` may be `null` only where the authority has set-like
ownership and no meaningful quantity. `is_new` may be `null` when the
authority cannot prove pre-grant ownership. Neither nullable rule permits
guessing. Committed-result evidence is audited separately from these fields.

The status below is the best status of the observed producer output after
joining its own committed lineage where that join is already defined:

| Producer | Status | Current-master runtime boundary | Main finding |
| --- | --- | --- | --- |
| `MONSTER_DROP` | `NEEDS_PRODUCER_PAYLOAD_EXTENSION` | Settlement and D5A events exist | The committed item event lacks a uniform operation binding, destination, post-grant state, capabilities, item class, and replay result. |
| `QUEST_REWARD` | `NEEDS_PRODUCER_PAYLOAD_EXTENSION` | D015 claim and D5A item acquisition events exist | Claim/item lineage is strong, but the committed component does not preserve item class, capabilities, or stack post-quantity. |
| `PREMIUM_REWARD` | `NEEDS_PRODUCER_PAYLOAD_EXTENSION` | D5E/D5F claim and component authorities exist | Cosmetic and capacity components have different evidence shapes; capacity ownership reference and D018 class semantics are not persisted in the bundle component. |
| `SHOP_COIN_PURCHASE` | `NEEDS_DESTINATION_ADAPTER` | C022 is accepted but unmerged; current master has no C019 runtime | C022 provides the strongest result shape, but raw destination names and a recoverable ownership reference still need a destination-scoped bridge. |

`READY_NOW` is intentionally not assigned to any family. `READY_FROM_ACCEPTED_CANDIDATE_NOT_MERGED` is also not assigned: C022 improves Shop evidence but does not itself emit a D018 envelope, and D020 is a pure adapter candidate rather than producer wiring.

## Producer evidence

### MONSTER_DROP

The current path is:

```text
server HP transition
  -> monster_settlement.settle_monster_defeat
  -> committed MONSTER_DEFEATED D5A event
  -> grant_functional_item / grant_wardrobe_item
  -> committed ITEM_ACQUISITION D5A event
```

`MONSTER_DEFEATED` is a defeat settlement, not an acquisition result. The
supported drop result must be taken from the subsequent `ITEM_ACQUISITION`
event. F013 confirms that the caller owns the transaction and that the
truthful acquisition evidence exists only after that transaction commits.

Available facts include item identity, quantity, `settlement_id` as a source
reference, ownership authority, a `grant_id` that can be normalized to an
ownership reference, and the D5A event row ID. The event payload does not
persist a uniform `source_operation_id`, destination, resulting quantity,
capabilities, item class, or replay result. The transient grant payload is
not a substitute for committed lineage.

Missing envelope facts after safe normalization:

`source_operation_id`, `destination`, `resulting_quantity`, `can_equip`,
`can_use`, `can_wear`, `replayed`, `item_class` — 8.

The D5A event contains `ownership_committed=true` and `outcome=SUCCESS`; the
future bridge must normalize the committed row and marker. `SUCCESS` alone is
not accepted as commit evidence.

F013 also proves that the current Monster event has no uniform encounter
operation ID and that `(user_id, settlement_id)` is the safe current dedupe
scope. Do not use a defeat event, UI preview, or pre-commit
`MonsterSettlementResult` as an acquisition envelope.

### QUEST_REWARD

D015 stores `quest_claims_v2` with `claim_status=SETTLED` and emits one D5A
`ITEM_ACQUISITION` event per item/cosmetic component. The event preserves
claim operation identity, quest/period/version, item identity, quantity,
source reference, ownership authority/reference, `ownership_committed=true`,
and its own event ID. XP and Coin components are not item acquisitions and
must not be forced into an item envelope.

The component/result surface does not persist a normalized destination,
resulting stack quantity, item class, or capability booleans. `duplicate` on
the claim result can become delivery metadata `replayed` only at a trusted
adapter boundary; it is not ownership evidence. `is_new` remains nullable
because the current committed component does not prove the pre-grant state.

Missing envelope facts after safe destination/replay normalization:

`resulting_quantity`, `can_equip`, `can_use`, `can_wear`, `item_class` — 5.

The claim row's `SETTLED` status plus the committed D5A event is sufficient
commit evidence. A completion/claimable response without that evidence must
remain rejected.

### PREMIUM_REWARD

Premium entitlement is not a reward result. The recon considered only the
committed component paths:

* the pure-cosmetic path records claim operation, wardrobe ownership
  reference, D5A Premium/item events, and `ownership_committed=true`;
* the deterministic bundle records `QUESTION_CAPACITY` and optional
  `PURE_COSMETIC` components with operation IDs and event IDs.

The public `ClaimResult`/`BundleClaimResult` status is producer-specific
(`SUCCESS` or `GRANTED`) and must not be treated as committed evidence by
itself. A future bridge must join the committed claim/component/outbox rows
and emit an explicit committed marker or a `COMMITTED`/`SETTLED` status.

The cosmetic component can safely normalize quantity `1`,
`PLAYER_WARDROBE`, `COSMETIC`, and the three pure-cosmetic capabilities from
its validated reward contract. Its resulting quantity is set-like and may be
`null`. The capacity component has `capacity_delta`, effective capacity, an
operation ID, and a capacity event, but the bundle component does not retain
an ownership reference or a D018 item class. Those facts must not be guessed
from `effective_capacity_after`.

Aggregate missing facts for the supported bundle components after joining
committed events: `ownership_reference`, `item_class` — 2. The status remains
`NEEDS_PRODUCER_PAYLOAD_EXTENSION` because the current component record cannot
represent both component types truthfully in D018 V1.

### SHOP_COIN_PURCHASE

C022's accepted C019 result is substantially stronger than the old D019
recon: `CoinPurchaseResult` carries operation identity, offer/item identity,
quantity, raw destination, ownership result, `is_new`, capabilities,
`replayed`, and lineage event ID. The committed operation row is
`operation_status=COMMITTED`; C022's D5A event includes resolved offer class,
destination, ownership authority, and the same operation identity.

The remaining gap is destination-specific ownership reference. The
`ownership_result` contains state and `new_quantity`, but C022 does not
return a stable reference to the resulting `player_inventory`,
`shop_inventory`, or `player_wardrobe` record. Raw C019 names also require
normalization to D018 destinations and authority names. Item class is
available from the server-resolved offer/lineage (`acquisition_class`) and
must not come from the client.

Missing envelope facts: `ownership_reference` — 1. This is classified as
`NEEDS_DESTINATION_ADAPTER`, not as a new ownership authority. If a future
adapter cannot recover a truthful reference from the existing authority, the
producer result must be extended rather than guessing one.

## Commit-evidence lock

The D019-R1 distinction remains mandatory for every family:

```text
SUCCESS alone                         = not commit evidence
COMMITTED / SETTLED status            = commit evidence
explicit committed boolean marker    = commit evidence
```

Applied to the four paths:

| Family | Raw success-only result | Trusted committed evidence |
| --- | --- | --- |
| Monster | `outcome=SUCCESS` or defeat result alone is insufficient | committed D5A `ITEM_ACQUISITION` row plus `ownership_committed=true`, after transaction commit |
| Quest | completion/claimable or a generic `SUCCESS` response is insufficient | `quest_claims_v2.claim_status=SETTLED` plus committed D5A item event |
| Premium | entitlement active or `ClaimResult.status=SUCCESS`/`BundleClaimResult.status=GRANTED` alone is insufficient | committed claim/component rows and D5A event(s), normalized by a future bridge |
| Shop | offer/purchase preview or generic success is insufficient | C022 purchase operation `operation_status=COMMITTED` plus D5A acquisition event |

No D021 document treats a generic success value as commit evidence.

## D5A / D5C boundary

`D5A_D5C_BOUNDARY=PASS`.

D5A `ITEM_ACQUISITION`/domain-event rows are acquisition evidence. D5C item
use/consume operations are not acquisition producers and are not used to fill
any missing acquisition fact. The D5F capacity/cosmetic paths are read as
their existing domain settlement records; this recon does not reinterpret
D5C as a grant authority.

## Special item locks

The D018 and C022 contract tests preserve:

* `go_stone_black` = `TROPHY`, inventory-only, no equip/use/wear/combat power;
* `xp_amulet` = `HOLD_FOR_AUTHORITY`, no newly activated capability.

There is a current producer coverage gap that must remain visible:
`monster_drop_profiles.py` lists `xp_amulet` in reachable legacy drop profiles
and `go_stone_black` in the reachable Dragon profile. The Monster D5A event
does not persist item class, capability flags, or special status, so a future
Monster result bridge must fail closed or add truthful producer evidence before
returning either item as D018. C022's Shop authority independently rejects
both IDs. D021 does not repair the Monster path.

Accordingly, for producer-wide readiness reporting:

* `GO_STONE_BLACK_LOCK=FAIL` — C022 passes, but current Monster output is
  untyped and cannot prove the lock;
* `XP_AMULET_HOLD=FAIL` — C022 passes, but current Monster output has no
  persisted HOLD marker or capability proof.

This is a recon finding, not a claim that a D018 envelope has already violated
the lock; the current untyped Monster path is not D018-ready.

## Current master versus accepted candidates

`CURRENT_MASTER_VS_ACCEPTED_CANDIDATE_BOUNDARY=PASS`.

* D020 is an accepted unmerged stack. Its pure contract/adapter modules are
  not current-master runtime.
* C022 is an accepted unmerged commerce candidate. Its C019/C021 code and
  migration are not current-master runtime, and no Shop route was wired.
* F013 is a read-only recon. It did not import F012 or add a Monster runtime
  adapter, schema, or World milestone writer.

The recon therefore reports both the current-master fact source and the
accepted-candidate improvement without claiming either candidate is live.

## Next integration recommendation

`NEXT_ACQUISITION_PRODUCER_INTEGRATION=SHOP_RESULT_BRIDGE`.

Reason: C022 is the closest accepted current-master candidate to the D020
envelope. Its operation status, ownership result, capabilities, replay
metadata, D5A lineage, and server-resolved item class are already explicit.
A narrow destination-scoped bridge can be designed without changing payment
or ownership authority; it must first define how each existing destination
returns a truthful ownership reference. Shop is therefore the lowest-
ambiguity next step, while Monster operation binding, Quest item taxonomy,
and Premium multi-component semantics remain larger gaps.

## Validation and safety

Read-only current-master characterization run:

```text
tests/test_monster_drop_profiles.py
tests/test_monster_settlement.py
tests/test_d015_quest_claim_reward.py
tests/test_d5e_premium_claim_lineage.py
tests/test_d5f_premium_reward_bundle.py
42 passed, 3 skipped
```

Referenced accepted-candidate evidence was not reclassified as current
master: D020 reported 137 passed/6 skipped for its combined acquisition and
lineage suites; C022 reported 42 C019/C021 focused passes and 14 D5A passes
with 1 skip; F013 reported its four read-only characterization groups as
27 passed, 20 passed/1 skipped, 37 passed, and 72 passed.

This D021 candidate changes only the three recon artifacts. It does not
modify `app.py`, runtime producer modules, migrations, ownership state,
payments, Production, or deployment.
