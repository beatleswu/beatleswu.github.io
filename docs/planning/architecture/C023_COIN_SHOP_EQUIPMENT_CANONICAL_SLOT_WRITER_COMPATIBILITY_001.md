# C023 — Coin Shop Equipment canonical-slot writer compatibility

Status: implementation candidate for Owner review.  This document records a
pure Commerce acquisition-writer change; it does not wire a Shop route, run a
schema migration, or change Production.

## Provenance and controlled stack

The isolated branch starts from current `origin/master`:

```text
current master: b75308d44806bb7c2e2b131a73ba06a71c188b3c
branch: codex/c023-coin-shop-equipment-canonical-slot-writer
```

Current master is an ancestor of the controlled stack.  The accepted inputs
were forward-integrated rather than merged from their old branches:

| Accepted input | Forward-integrated commit |
| --- | --- |
| C019 base `8016d7a9e9f6316b8977865ee8233934d8efac28` | `365a601e1` |
| C019-R1 `cb8f7e07350edb873c6300bfae3680819b0329f6` | `16d86b006` |
| C020 `2d2d20afad69fe7b7e0b00f2c78c74f9b9d7694c` | `a8c8c41b4` |
| C021 `f8124b4d77cf04f2b9fb09fd5e8a5f14faeb93fe` | `2aab903f3` |
| C021-R1 `8af8e69cd22b1fddb2dab8e9b769067091d51d90` | `711da28f1` |
| C022 `b08c822573051635c92070d696ca43fcb49020f1` | `c61d928a1` |
| B033 `15f665f656418ab189d32aa809c163f3e27fa92c` | `f3ee9a6f1` |

B033 contributes only its accepted migration candidate and schema tests.  The
migration is not imported by application startup and was used only against
disposable test databases.

## Authority boundary

- `player_inventory` remains Equipment ownership authority.
- `app.EQUIPMENT_DEFS` remains the server Equipment definition and slot
  authority.
- `canonical_slot` remains a derived B033 projection, not a Shop or client
  field.
- `SqlAcquisitionAuthority` accepts an injected `equipment_slot_source`,
  either a server-built resolver or projection map.  It does not import
  `app.py` and does not copy `EQUIPMENT_DEFS`.
- C019 still owns exactly-once operation identity, caller-owned transaction
  boundaries, Coin debit, acquisition, and D5A lineage.  D5C is not used.

The caller must bind the server projection for functional Equipment.  Without
that authority, the writer fails closed with
`OWNERSHIP_AUTHORITY_UNAVAILABLE`; an unknown functional identity fails with
`ACQUISITION_FAILED`.  A client-supplied `canonical_slot` in an offer mapping
or presentation metadata is ignored.

## Writer behavior

For `WEAPON`, `ARMOR`, and `ACCESSORY` offers routed to `player_inventory`:

1. Read existing ownership and enforce the existing duplicate policy.
2. Resolve the item slot from the injected server-owned projection.
3. Detect whether `player_inventory.canonical_slot` exists.
4. Insert `equipped=0` and, when present, the derived canonical slot.
5. Return the existing truthful ownership result (`is_new` and count).

This is the `SCHEMA_AWARE_INSERT` strategy:

- Pre-B033 schema: preserve the existing five-column insert shape, so current
  installations without `canonical_slot` continue to work.
- Post-B033 schema: use the six-column insert and persist the derived
  `canonical_slot`.

Trophy/non-functional records remain slotless.  `xp_amulet` remains
`HOLD_FOR_AUTHORITY`; `go_stone_black` remains inventory-only Trophy and is
rejected from the Coin sale path.  No equip mutation, combat calculation,
catalog duplication, free grant, Premium cash purchase, or D5C write was
added.

All writer failures remain inside the caller-owned C019 transaction.  A failed
slot resolution, ownership insert, or lineage step rolls back the operation
reservation, Coin debit, currency log, inventory mutation, and D5A event
together.

## Validation evidence

The focused C023 suite covers functional weapon/armor/accessory projection,
pre- and post-B033 schemas, client slot rejection, unknown functional-item
fail-closed behavior, locked identities, replay, changed-operation conflict,
duplicate rejection, and rollback:

```text
C023: 12 passed
C019: 19 passed
C021-R1: 23 passed
B033 schema: 12 passed, 4 skipped (PostgreSQL environment gap)
```

The SQLite evidence covers the writer and transaction behavior only; it is not
PostgreSQL concurrency proof.  No Production database was queried or
mutated, and the B033 migration was not run outside disposable test
connections.

## Remaining integration gate

The future app/E-lane integration must construct the slot projection from the
live server `EQUIPMENT_DEFS` authority and inject it into the eventual Shop
caller.  That later task may wire routes only under its own authorization.  It
must not move slot authority into the catalog or client, and it must preserve
the B033 migration gate before relying on post-B033 projection storage.

`app.py` is unchanged in this candidate.
