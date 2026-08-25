# B040 Functional Equipment Ownership Writer Service v1

## Status and boundary

This document describes the B040 candidate at current canonical master
`7c30a44867501ef936f84a41f2b25032c186f367`.

B040 adds one route-independent server-side writer for creating one already
authorized `player_inventory` ownership row. The caller remains responsible
for authentication, grant policy, transaction ownership, commit/rollback,
HTTP mapping, and the Monster/Admin/Commerce decision that a grant should
occur. B040 does not change `app.py`, execute a migration, or access
Production.

The service is `equipment_ownership_service.py` and its public operation is
`grant_equipment_ownership(conn, user_id, equip_id, source, *,
equipment_defs=None)`.

## Authorities

| Concern | Authority | B040 behavior |
| --- | --- | --- |
| Ownership row | `player_inventory` | Inserts exactly one row. |
| Functional slot | Server `EQUIPMENT_DEFS`, projected through B033 helpers | Never accepts a client slot and never infers a slot from an item name. |
| Functional slots | `weapon`, `armor`, `accessory` | Unknown or invalid definitions fail closed. |
| Equip state | Caller-created ownership is always `equipped=0` | B040 never auto-equips. |
| Combat | B021/B034 consumers | B040 calculates no combat values. |
| Grant authorization | Caller | B040 validates only the bounded server source vocabulary (`drop`, `admin`). |

The service does not read or write legacy `player_appearance.combat_*`
fields, does not use client/UI/Shop values as authority, and does not create
a second ownership or item-definition authority.

## Schema compatibility

B040 recognizes the following states before writing:

| State | Required behavior |
| --- | --- |
| `LEGACY_SCHEMA` | The required legacy columns exist and `canonical_slot` is absent. Functional rows are inserted without that column. Locked inventory-only rows are also inserted with `equipped=0`. |
| `B033_VALID_SCHEMA` | `canonical_slot` exists and B033 validation succeeds. Functional rows persist the server-derived slot; locked rows persist `canonical_slot=NULL`. |
| `B033_MALFORMED_SCHEMA` | `canonical_slot` exists but the B033 validity shape is incomplete or invalid. The service fails closed before inserting. |
| Missing required legacy columns | The service fails closed with a schema error; it does not guess a compatible shape. |

The service does not run `migrations/equipment_canonical_slot_v1.py` and does
not repair historical malformed rows. B033 remains the schema owner and its
invariants remain the production gate:

```text
equipped=false OR canonical_slot IS NOT NULL
UNIQUE(user_id, canonical_slot)
  WHERE equipped=true AND canonical_slot IS NOT NULL
```

An unequipped `canonical_slot=NULL` row remains legal. A newly created
functional row in a valid B033 schema receives its slot immediately, so it is
ready for `equipment_loadout_service.equip_owned_item()` without a repair
step.

## Locked items

`go_stone_black` remains an inventory-only Trophy with no combat power. If an
authorized non-Commerce grant path creates ownership, B040 stores it as
`equipped=0, canonical_slot=NULL`.

`xp_amulet` remains `HOLD_FOR_AUTHORITY`. B040 does not grant it a functional
slot merely because a legacy definition contains accessory-like metadata. If
an existing accepted grant path permits ownership, the only B040 projection
is `equipped=0, canonical_slot=NULL`; it is never auto-equipped or treated as
functional Equipment.

## Current writer mapping

The current writers can be mapped to the bounded B040 source values without
changing their grant semantics:

| Existing writer | Current source | Current behavior | B040 mapping |
| --- | --- | --- | --- |
| `app.py::_settle_monster_defeat_in_tx.grant_functional_item` | `drop` (from `monster_settlement`) | Inserts one `equipped=0` ownership row per granted quantity and permits duplicate ownership rows. | Future caller passes `source="drop"`; B040 preserves one-row-per-grant behavior. |
| `app.py::admin_set_equipment` | `admin` | Inserts one `equipped=0` ownership row after server-side definition validation. | Future caller passes `source="admin"`; B040 derives the slot and returns the exact inserted row id. |

B040 does not modify either writer. It also does not modify the independent
C026 Commerce authority. C026 uses the same server-derived B033 slot meaning
when `canonical_slot` is present, but C026 remains its own acquisition path.

## Result and transaction contract

The detached result contains:

```text
row_id
user_id
equip_id
canonical_slot
equipped
source
```

SQLite obtains `row_id` from `cursor.lastrowid`. PostgreSQL uses
`INSERT ... RETURNING id`. No `MAX(id)`, latest-row lookup, timestamp
inference, or ordering heuristic is used.

The caller owns `BEGIN`, `COMMIT`, and `ROLLBACK`. B040 performs zero commits
and zero rollbacks. A caller rollback removes the inserted ownership row.
Duplicate policy is intentionally not invented: callers retain the existing
Monster/Admin semantics and decide whether a repeated grant is allowed.

## B034 and release boundary

For a valid B033 schema, the B040 result is immediately consumable by B034
for weapon, armor, and accessory ownership. B034 remains the loadout command
authority; B040 does not equip or unequip anything.

B039 Option C remains the safe cutover recommendation. B040 alone does not
make the legacy equip route safe after B033 because that route still needs
its controlled B034 integration. The future sequence is:

1. Integrate all functional ownership writers through B040 or an equivalent
   server-slot-compatible adapter.
2. Accept and test the B034 route cutover while preserving B036 locked-item
   behavior.
3. Run the read-only malformed-data preflight.
4. Freeze incompatible writers and execute the Owner-authorized B033
   migration in the approved release boundary.
5. Verify post-migration writer and loadout invariants before any enablement.

No step in B040 grants Production migration, feature enablement, merge, or
deployment authority.

## Validation scope

The focused test module covers PRE-B033 and valid POST-B033 writes for all
three functional slots, unknown/invalid definitions, client-slot rejection,
locked-item projections, exact inserted IDs, caller-owned rollback, zero
service commits/rollbacks, malformed partial-B033 rejection, current
Monster/Admin source mapping, and B040-to-B034 equip compatibility.

The candidate does not alter `app.py`, `coin_purchase_authority.py`,
`equipment_loadout_service.py`, the B033 migration, or any Production data.
