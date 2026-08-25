"""Route-independent server authority for functional Equipment loadouts.

The caller owns authentication, the connection, and the transaction.  This
module owns only the desired-state Equipment mutation semantics.  It requires
the accepted B033 schema candidate before it reads or writes loadout state and
never commits or rolls back the caller transaction.

The only definition source is the server ``EQUIPMENT_DEFS`` registry (loaded
lazily when tests or a caller do not provide an explicit registry).  No
legacy ``player_appearance.combat_*`` field, client slot, catalog, or combat
stat is consulted.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Mapping

from migrations.equipment_canonical_slot_v1 import (
    CANONICAL_SLOTS,
    CANONICAL_SLOT_COLUMN,
    HOLD_FOR_AUTHORITY_EQUIPMENT_IDS,
    INVENTORY_ONLY_EQUIPMENT_IDS,
    NON_FUNCTIONAL_EQUIPMENT_IDS,
    build_slot_projection,
    validate_schema,
)


TABLE_NAME = "player_inventory"
BASE_COLUMNS = frozenset({"id", "user_id", "equip_id", "equipped", CANONICAL_SLOT_COLUMN})


class EquipmentLoadoutError(ValueError):
    """Stable, route-independent rejection for loadout command failures."""

    def __init__(self, code: str, message: str, **details: Any):
        self.code = code
        self.details = details
        super().__init__(message)


def _is_sqlite(conn: Any) -> bool:
    raw = getattr(conn, "_conn", conn)
    return raw.__class__.__module__.startswith("sqlite3")


def _value(row: Any, index: int, name: str) -> Any:
    try:
        return row[name]
    except (KeyError, TypeError, IndexError):
        return row[index]


def _table_name(conn: Any) -> str:
    return TABLE_NAME if _is_sqlite(conn) else f"public.{TABLE_NAME}"


def _column_names(conn: Any) -> set[str]:
    if _is_sqlite(conn):
        rows = conn.execute(f"PRAGMA table_info({TABLE_NAME})").fetchall()
        return {str(_value(row, 1, "name")) for row in rows}
    rows = conn.execute(
        """SELECT column_name
             FROM information_schema.columns
            WHERE table_schema='public' AND table_name=?""",
        (TABLE_NAME,),
    ).fetchall()
    return {str(_value(row, 0, "column_name")) for row in rows}


def _load_authoritative_defs() -> Iterable[Mapping[str, Any]]:
    from app import EQUIPMENT_DEFS

    return EQUIPMENT_DEFS


def _catalog(
    equipment_defs: Iterable[Mapping[str, Any]] | None,
) -> tuple[dict[str, Mapping[str, Any]], dict[str, str]]:
    definitions = tuple(equipment_defs if equipment_defs is not None else _load_authoritative_defs())
    all_defs: dict[str, Mapping[str, Any]] = {}
    for definition in definitions:
        equip_id = str(definition.get("id") or "")
        if not equip_id or equip_id in all_defs:
            raise EquipmentLoadoutError(
                "EQUIPMENT_DEFINITION_INVALID",
                "server Equipment definitions are invalid",
            )
        all_defs[equip_id] = definition
    return all_defs, build_slot_projection(definitions)


def _validate_user_id(user_id: Any) -> int:
    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
        raise EquipmentLoadoutError("INVALID_USER_ID", "user_id must be a positive integer")
    return user_id


def _validate_equip_id(equip_id: Any) -> str:
    if not isinstance(equip_id, str) or not equip_id.strip():
        raise EquipmentLoadoutError("INVALID_EQUIPMENT_ID", "equip_id must be a non-empty string")
    return equip_id.strip()


def _require_b033_schema(conn: Any) -> None:
    status = validate_schema(conn)
    columns = _column_names(conn)
    missing = sorted(BASE_COLUMNS - columns)
    if missing or not status.get("valid"):
        details = {
            "missing_columns": missing,
            "schema_missing": status.get("missing", []),
        }
        raise EquipmentLoadoutError(
            "SCHEMA_INVARIANT_UNAVAILABLE",
            "B033 Equipment schema/invariant is unavailable or malformed",
            **details,
        )


def _locked_inventory_rows(conn: Any, user_id: int) -> list[dict[str, Any]]:
    sql = (
        f"SELECT id, user_id, equip_id, equipped, {CANONICAL_SLOT_COLUMN} "
        f"FROM {_table_name(conn)} WHERE user_id=? ORDER BY id"
    )
    if not _is_sqlite(conn):
        sql += " FOR UPDATE"
    cursor = conn.execute(sql, (user_id,))
    columns = ("id", "user_id", "equip_id", "equipped", CANONICAL_SLOT_COLUMN)
    return [
        {column: _value(row, index, column) for index, column in enumerate(columns)}
        for row in cursor.fetchall()
    ]


def _compact_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "equip_id": row["equip_id"],
        "equipped": row["equipped"],
        "canonical_slot": row[CANONICAL_SLOT_COLUMN],
    }


def _state_report(
    rows: list[dict[str, Any]],
    all_defs: Mapping[str, Mapping[str, Any]],
    functional_slots: Mapping[str, str],
) -> dict[str, Any]:
    blockers: dict[str, list[dict[str, Any]]] = defaultdict(list)
    equipped_by_slot: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in rows:
        equip_id = str(row["equip_id"])
        equipped = bool(row["equipped"])
        actual_slot = row[CANONICAL_SLOT_COLUMN]
        expected_slot = functional_slots.get(equip_id)

        if equip_id not in all_defs:
            if equipped:
                blockers["UNKNOWN_EQUIPPED_EQUIP_ID"].append(_compact_row(row))
                if actual_slot is None:
                    blockers["EQUIPPED_WITH_NULL_CANONICAL_SLOT"].append(
                        _compact_row(row)
                    )
            if actual_slot is not None:
                blockers["CANONICAL_SLOT_PROJECTION_DISAGREEMENT"].append(
                    _compact_row(row)
                )
            continue

        if expected_slot is None:
            if equipped:
                if equip_id in INVENTORY_ONLY_EQUIPMENT_IDS:
                    category = "GO_STONE_BLACK_EQUIPPED"
                elif equip_id in HOLD_FOR_AUTHORITY_EQUIPMENT_IDS:
                    category = "XP_AMULET_EQUIPPED"
                else:
                    category = "NON_FUNCTIONAL_EQUIPMENT_EQUIPPED"
                blockers[category].append(_compact_row(row))
            if actual_slot is not None:
                blockers["CANONICAL_SLOT_PROJECTION_DISAGREEMENT"].append(
                    _compact_row(row)
                )
            if equipped and actual_slot is None:
                blockers["EQUIPPED_WITH_NULL_CANONICAL_SLOT"].append(
                    _compact_row(row)
                )
            continue

        # ``canonical_slot`` is nullable for unequipped ownership rows.  A
        # NULL projection is therefore not itself disagreement; it becomes a
        # blocking state only when the row is equipped.  A non-NULL value
        # must always agree with the server registry.
        if actual_slot is not None and actual_slot != expected_slot:
            blockers["CANONICAL_SLOT_PROJECTION_DISAGREEMENT"].append(
                {
                    **_compact_row(row),
                    "expected_canonical_slot": expected_slot,
                }
            )
        if equipped:
            if actual_slot is None:
                blockers["EQUIPPED_WITH_NULL_CANONICAL_SLOT"].append(
                    _compact_row(row)
                )
            else:
                equipped_by_slot[expected_slot].append(row)

    for slot in CANONICAL_SLOTS:
        grouped = equipped_by_slot.get(slot, [])
        if len(grouped) > 1:
            blockers[f"DUPLICATE_EQUIPPED_{slot.upper()}"] = [
                {
                    "user_id": grouped[0]["user_id"],
                    "canonical_slot": slot,
                    "rows": [_compact_row(row) for row in grouped],
                }
            ]

    return {
        "clean": not blockers,
        "blocking_categories": sorted(blockers),
        "blockers": dict(blockers),
    }


def _raise_for_malformed_state(report: Mapping[str, Any]) -> None:
    if report.get("clean"):
        return
    raise EquipmentLoadoutError(
        "MALFORMED_EQUIPPED_STATE",
        "existing equipped state is malformed; explicit repair is required",
        report=dict(report),
    )


def _result(
    *,
    user_id: int,
    equip_id: str,
    canonical_slot: str,
    changed: bool,
    previous_equipped_item_id: str | None,
    equipped_item_id: str | None,
) -> dict[str, Any]:
    return {
        "user_id": user_id,
        "target_equip_id": equip_id,
        "canonical_slot": canonical_slot,
        "changed": changed,
        "previous_equipped_item_id": previous_equipped_item_id,
        "equipped_item_id": equipped_item_id,
    }


def _prove_final_state(
    conn: Any,
    user_id: int,
    target_id: int,
    equip_id: str,
    canonical_slot: str,
    all_defs: Mapping[str, Mapping[str, Any]],
    functional_slots: Mapping[str, str],
) -> None:
    final_rows = _locked_inventory_rows(conn, user_id)
    _raise_for_malformed_state(_state_report(final_rows, all_defs, functional_slots))
    target_rows = [row for row in final_rows if row["id"] == target_id]
    equipped_target = [row for row in target_rows if bool(row["equipped"])]
    if len(equipped_target) != 1 or equipped_target[0][CANONICAL_SLOT_COLUMN] != canonical_slot:
        raise EquipmentLoadoutError(
            "FINAL_LOADOUT_INVARIANT_FAILED",
            "loadout command did not produce the requested equipped state",
            equip_id=equip_id,
            canonical_slot=canonical_slot,
        )


def equip_owned_item(
    conn: Any,
    user_id: int,
    equip_id: str,
    *,
    equipment_defs: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Equip an owned server-defined item using desired-state semantics.

    The caller must already own the transaction.  This function performs no
    commit or rollback.  A repeated request for the currently equipped target
    returns ``changed=False`` without writing a second transition.
    """

    user_id = _validate_user_id(user_id)
    equip_id = _validate_equip_id(equip_id)
    _require_b033_schema(conn)
    all_defs, functional_slots = _catalog(equipment_defs)

    if equip_id not in all_defs:
        raise EquipmentLoadoutError("UNKNOWN_EQUIPMENT", "unknown Equipment id", equip_id=equip_id)
    canonical_slot = functional_slots.get(equip_id)
    if canonical_slot is None:
        if equip_id in INVENTORY_ONLY_EQUIPMENT_IDS:
            code = "GO_STONE_BLACK_NOT_EQUIPPABLE"
        elif equip_id in HOLD_FOR_AUTHORITY_EQUIPMENT_IDS:
            code = "XP_AMULET_HOLD_FOR_AUTHORITY"
        else:
            code = "NON_FUNCTIONAL_EQUIPMENT"
        raise EquipmentLoadoutError(code, "Equipment is not functionally equippable", equip_id=equip_id)

    rows = _locked_inventory_rows(conn, user_id)
    owned_rows = [row for row in rows if str(row["equip_id"]) == equip_id]
    if not owned_rows:
        raise EquipmentLoadoutError("EQUIPMENT_NOT_OWNED", "target Equipment is not owned", equip_id=equip_id)
    _raise_for_malformed_state(_state_report(rows, all_defs, functional_slots))

    target_row = min(
        owned_rows,
        key=lambda row: (not bool(row["equipped"]), int(row["id"])),
    )
    previous = [
        row
        for row in rows
        if bool(row["equipped"]) and row[CANONICAL_SLOT_COLUMN] == canonical_slot
    ]
    previous_id = str(previous[0]["equip_id"]) if previous else None

    if bool(target_row["equipped"]):
        return _result(
            user_id=user_id,
            equip_id=equip_id,
            canonical_slot=canonical_slot,
            changed=False,
            previous_equipped_item_id=previous_id,
            equipped_item_id=equip_id,
        )

    table = _table_name(conn)
    conn.execute(
        f"UPDATE {table} SET equipped=0 "
        f"WHERE user_id=? AND {CANONICAL_SLOT_COLUMN}=? AND equipped=1",
        (user_id, canonical_slot),
    )
    conn.execute(
        f"UPDATE {table} SET {CANONICAL_SLOT_COLUMN}=?, equipped=1 "
        "WHERE id=? AND user_id=?",
        (canonical_slot, target_row["id"], user_id),
    )
    _prove_final_state(
        conn,
        user_id,
        int(target_row["id"]),
        equip_id,
        canonical_slot,
        all_defs,
        functional_slots,
    )
    return _result(
        user_id=user_id,
        equip_id=equip_id,
        canonical_slot=canonical_slot,
        changed=True,
        previous_equipped_item_id=previous_id,
        equipped_item_id=equip_id,
    )


def unequip_owned_item(
    conn: Any,
    user_id: int,
    equip_id: str,
    *,
    equipment_defs: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Unequip an owned functional item without consuming ownership."""

    user_id = _validate_user_id(user_id)
    equip_id = _validate_equip_id(equip_id)
    _require_b033_schema(conn)
    all_defs, functional_slots = _catalog(equipment_defs)
    if equip_id not in all_defs:
        raise EquipmentLoadoutError("UNKNOWN_EQUIPMENT", "unknown Equipment id", equip_id=equip_id)
    canonical_slot = functional_slots.get(equip_id)
    if canonical_slot is None:
        raise EquipmentLoadoutError(
            "NON_FUNCTIONAL_EQUIPMENT",
            "Equipment is not functionally equippable",
            equip_id=equip_id,
        )

    rows = _locked_inventory_rows(conn, user_id)
    owned_rows = [row for row in rows if str(row["equip_id"]) == equip_id]
    if not owned_rows:
        raise EquipmentLoadoutError("EQUIPMENT_NOT_OWNED", "target Equipment is not owned", equip_id=equip_id)
    _raise_for_malformed_state(_state_report(rows, all_defs, functional_slots))
    target_row = min(
        owned_rows,
        key=lambda row: (not bool(row["equipped"]), int(row["id"])),
    )
    was_equipped = bool(target_row["equipped"])
    if was_equipped:
        conn.execute(
            f"UPDATE {_table_name(conn)} SET equipped=0 WHERE id=? AND user_id=?",
            (target_row["id"], user_id),
        )
        _prove_final_state_after_unequip(
            conn, user_id, int(target_row["id"]), all_defs, functional_slots
        )
    return _result(
        user_id=user_id,
        equip_id=equip_id,
        canonical_slot=canonical_slot,
        changed=was_equipped,
        previous_equipped_item_id=equip_id if was_equipped else None,
        equipped_item_id=None,
    )


def _prove_final_state_after_unequip(
    conn: Any,
    user_id: int,
    target_id: int,
    all_defs: Mapping[str, Mapping[str, Any]],
    functional_slots: Mapping[str, str],
) -> None:
    final_rows = _locked_inventory_rows(conn, user_id)
    _raise_for_malformed_state(_state_report(final_rows, all_defs, functional_slots))
    target_rows = [row for row in final_rows if row["id"] == target_id]
    if len(target_rows) != 1 or bool(target_rows[0]["equipped"]):
        raise EquipmentLoadoutError(
            "FINAL_LOADOUT_INVARIANT_FAILED",
            "unequip command did not clear the requested item",
        )


__all__ = [
    "EquipmentLoadoutError",
    "equip_owned_item",
    "unequip_owned_item",
]
