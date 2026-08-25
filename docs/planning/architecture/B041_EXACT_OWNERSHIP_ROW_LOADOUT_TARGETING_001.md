# B041 Exact Ownership-Row Loadout Targeting

## Scope and provenance

B041 is based on current canonical master
`d29610726b9a5f2e46a3ba0ce1b60af414f95802` and extends the existing
`equipment_loadout_service.py`. It does not modify `app.py`, the schema,
migrations, frontend, Shop, grant writers, or Production.

The service remains the single B034 loadout authority. The caller owns
authentication, the connection, and the transaction; the service performs no
commit or rollback.

## Old and new command semantics

The existing item-identity contract remains unchanged:

```python
equip_owned_item(conn, user_id, equip_id, equipment_defs=...)
unequip_owned_item(conn, user_id, equip_id, equipment_defs=...)
```

When `ownership_row_id` is omitted, B034 keeps its existing desired-state
selection behavior: it operates on the deterministic owned row selected for
the requested `equip_id`. Existing result fields and their shape are
preserved for these callers.

B041 adds an optional exact-row mode:

```python
equip_owned_item(
    conn,
    user_id,
    equip_id,
    ownership_row_id=205,
    equipment_defs=...,
)
```

The same keyword is available on `unequip_owned_item`. When supplied, the
service targets only `player_inventory.id=205`; it never substitutes another
row with the same `equip_id`.

## Exact-row validation

`ownership_row_id` must be a positive integer. The service then proves:

1. the row exists;
2. the row belongs to the supplied authenticated `user_id`;
3. its stored `equip_id` equals the requested server-side `equip_id`; and
4. the requested identity resolves to functional Equipment through the
   server-owned `EQUIPMENT_DEFS` projection.

Stable failures are:

| Condition | Error code |
| --- | --- |
| Non-positive, Boolean, or non-integer row id | `INVALID_OWNERSHIP_ROW_ID` |
| No row with that id | `EQUIPMENT_OWNERSHIP_ROW_NOT_FOUND` |
| Wrong user or row/equipment identity mismatch | `EQUIPMENT_OWNERSHIP_IDENTITY_MISMATCH` |

The service does not expose raw SQL errors or accept a client-supplied slot,
class, combat stat, or ownership claim.

## Duplicate ownership proof

Duplicate ownership remains legal. If the user owns:

```text
player_inventory.id=101, equip_id=iron_sword
player_inventory.id=205, equip_id=iron_sword
```

then exact equip with `ownership_row_id=205` produces:

```text
row 101: equipped=0
row 205: equipped=1, canonical_slot=weapon
```

If another weapon is already equipped, B034's existing slot replacement
clears that previous weapon before setting the exact requested row. The final
proof checks the requested row id itself and the canonical slot invariant,
not merely whether some row with the same `equip_id` is equipped.

Exact unequip changes only the requested row. If that row is already
unequipped, the result is `changed=False`; another duplicate row is not
selected as a substitute.

## Result contract

Legacy item-identity results retain the existing B034 fields:

```text
user_id
target_equip_id
canonical_slot
changed
previous_equipped_item_id
equipped_item_id
```

Exact-row results add:

```text
target_ownership_row_id
equipped_ownership_row_id
```

For exact equip, both fields identify the requested row after a successful
mutation or idempotent replay. For exact unequip,
`equipped_ownership_row_id` is `None` after the target is unequipped.

## Locked and malformed states

`xp_amulet` remains `HOLD_FOR_AUTHORITY` and
`go_stone_black` remains an inventory-only Trophy. Exact row targeting cannot
bypass either functional-equip lock.

B033 schema validation remains mandatory. Missing or malformed B033 schema
fails closed before mutation, with no legacy fallback and no automatic repair.

## E030 handoff

The future E030 route may continue to resolve and authenticate `inv_id` in
`app.py`, read that exact row's server-owned `equip_id`, and call B034 with
the resolved id:

```text
authenticate user
→ resolve player_inventory.id=205 for that user
→ read server equip_id=iron_sword
→ B034 ownership_row_id=205
→ serialize target_ownership_row_id=205
```

This is a service contract only. B041 does not perform the route cutover and
does not authorize a merge, deployment, feature enablement, or schema change.
