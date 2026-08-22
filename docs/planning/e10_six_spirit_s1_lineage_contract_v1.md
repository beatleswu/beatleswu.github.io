# E10 Six-Spirit Companion S1 Lineage Contract

Status: implementation candidate; no route or runtime integration.

## Authority boundary

`pet_collection` remains the functional Spirit ownership/progression
authority. `user_pets` remains the active/current-state projection and
`pet_inventory` remains the legacy resource surface. `player_wardrobe`
remains cosmetic ownership. `player_appearance.pet_id` / `combat_pet` remain
legacy cosmetic quarantine state.

The D5A `domain_event_outbox` is evidence only. D5C's item-use operation
record is the item-use correctness authority. Analytics consumes committed
facts and never authorizes mutations. D007 adds no table, migration, route, or
`app.py` integration.

## Operation identity

The reusable Companion identity binds:

`(user_id, operation_type, operation_id, target_spirit_id, target_item_id,
policy_version, request_fingerprint)`.

The recommended future durable uniqueness key is:

`(user_id, operation_type, operation_id)`.

The canonical fingerprint excludes timestamps, event IDs, request nonces,
client presentation fields, and `client_*` fields. A same-identity/same-
fingerprint request replays the committed result. A same-identity/different-
fingerprint request is a conflict. A different user cannot recover another
user's operation. A client-generated ID is only a validated request key; it is
not ownership, eligibility, quantity, effect, or progression authority.

## D5A/D5C evidence

Spirit reward grants reuse the D5A `ITEM_ACQUISITION` event family with a
typed `SPIRIT_REWARD` payload. Functional item uses reuse the D5C
`ITEM_CONSUME_EFFECT` event family with a typed `SPIRIT_ITEM_USE` payload.
Both carry `operation_id`, `lineage_id`, user/Spirit/item identity, source,
outcome, and only server-derived result fields. Neither event family becomes
the business authority, and no second outbox is created.

## Runtime handoff invariants

- Feed: owned Spirit and positive legacy inventory are required; one
  conditional decrement, one effect application; retry/concurrency replays
  without another decrement.
- Train: owned target, cooldown, and daily cap are checked in the same
  authority transaction; retries do not increment the cap twice.
- Unlock: eligibility is server-derived; ownership is inserted once;
  already-owned retries produce no reward.
- Switch: target must be owned; stale competing writes must reject or resolve
  deterministically; `user_pets` cannot introduce ownership.
- Evolution: Stage I is Lv1–9, Stage II Lv10–24, Stage III Lv25+. A jump over
  multiple thresholds produces one deterministic transition per crossed
  threshold. The client cannot set a stage.
- Replay/cinematic/scene override sources create zero Spirit XP, items,
  unlock progress, or evolution rewards.
- `pet_cat`, `pet_turtle`, `pet_rabbit`, `pet_fox`, `pet_wolf`, `pet_dragon`,
  and `pet_premium` are legacy cosmetic IDs and cannot enter functional
  Spirit lineage.
- Spirit effects are evaluated after authoritative Go result/battle
  settlement; no effect event may claim answer correctness changed before
  judging.

## Read-only auditing

`spirit_lineage_auditor.audit_companion_snapshot` validates source authority,
reward components, D5A outbox linkage, D5C operation/consumption linkage,
catalog/ownership/active projection consistency, evolution uniqueness,
replay exclusion, legacy quarantine, and effect timing. It only consumes
snapshots. `read_snapshot_tables` issues `SELECT` statements against
operator-supplied existing tables and performs no writes.

The snapshot collections named `reward_authorities` and
`item_consumptions` are integration interfaces for Lane B's existing or
future authority rows; they are not new D007 sources of truth.

## Current Spirit IDs

The contract keeps the three current IDs valid:

`ink_drop_kelpie`, `whispering_void_kit`, `star_shell_hatchling`.

No Spirit #4–#6 names or per-ID behavior branches are introduced.
