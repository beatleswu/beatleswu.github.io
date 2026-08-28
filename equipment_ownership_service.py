"""Route-independent server authority for Equipment ownership creation.

The caller decides that an already-authorized grant should happen and owns
the surrounding transaction. This module writes exactly one unequipped
``player_inventory`` row and returns the inserted row identity. It does not
decide Monster drops, Admin authorization, Commerce, loadout state, combat,
or transaction control.

The writer is intentionally compatible with both repository schema phases:

* on the legacy six-column table, functional Equipment is inserted without
  the additive ``canonical_slot`` projection;
* on a valid B033 table, functional Equipment is inserted with the slot
  derived from the server Equipment registry;
* a partially-present or malformed B033 projection fails closed.

``xp_amulet`` and ``go_stone_black`` remain ownership-only records. They are
never assigned a functional slot and are never auto-equipped.
"""

from __future__ import annotations

from dataclasses import dataclass
import datetime
from typing import Any, Iterable, Mapping

from migrations.equipment_canonical_slot_v1 import (
    CANONICAL_SLOTS,
    CANONICAL_SLOT_COLUMN,
    NON_FUNCTIONAL_EQUIPMENT_IDS,
    build_slot_projection,
    validate_schema,
)


TABLE_NAME = "player_inventory"
LEGACY_SCHEMA = "LEGACY_SCHEMA"
B033_VALID_SCHEMA = "B033_VALID_SCHEMA"
B033_MALFORMED_SCHEMA = "B033_MALFORMED_SCHEMA"

# These are the exact server-owned source values used by the current Monster,
# Admin, and Coin Shop writers. A route may not pass arbitrary client
# provenance through this boundary.
SUPPORTED_SOURCES = frozenset({"drop", "admin", "coin_shop"})

REQUIRED_COLUMNS = frozenset(
    {"id", "user_id", "equip_id", "equipped", "obtained_at", "source"}
)


class EquipmentOwnershipError(ValueError):
    """Stable route-independent rejection for ownership creation."""

    def __init__(self, code: str, message: str, **details: Any):
        self.code = code
        self.details = details
        super().__init__(message)


@dataclass(frozen=True)
class EquipmentOwnershipResult:
    """The exact ownership row created by one authorized grant."""

    row_id: int
    user_id: int
    equip_id: str
    canonical_slot: str | None
    equipped: bool
    source: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "row_id": self.row_id,
            "user_id": self.user_id,
            "equip_id": self.equip_id,
            "canonical_slot": self.canonical_slot,
            "equipped": self.equipped,
            "source": self.source,
        }


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
    try:
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
    except Exception as exc:
        raise EquipmentOwnershipError(
            "SCHEMA_UNAVAILABLE",
            "player_inventory schema authority is unavailable",
        ) from exc


def _schema_state(conn: Any) -> str:
    columns = _column_names(conn)
    missing = sorted(REQUIRED_COLUMNS - columns)
    if missing:
        code = (
            "B033_MALFORMED_SCHEMA"
            if CANONICAL_SLOT_COLUMN in columns
            else "LEGACY_SCHEMA_UNAVAILABLE"
        )
        raise EquipmentOwnershipError(
            code,
            "player_inventory does not expose the required ownership columns",
            schema_state=(
                B033_MALFORMED_SCHEMA
                if CANONICAL_SLOT_COLUMN in columns
                else LEGACY_SCHEMA
            ),
            missing_columns=missing,
        )

    if CANONICAL_SLOT_COLUMN not in columns:
        return LEGACY_SCHEMA

    try:
        status = validate_schema(conn)
    except Exception as exc:
        raise EquipmentOwnershipError(
            "B033_MALFORMED_SCHEMA",
            "player_inventory canonical-slot schema could not be validated",
            schema_state=B033_MALFORMED_SCHEMA,
        ) from exc
    if not status.get("valid"):
        raise EquipmentOwnershipError(
            "B033_MALFORMED_SCHEMA",
            "player_inventory canonical-slot schema is incomplete or invalid",
            schema_state=B033_MALFORMED_SCHEMA,
            schema_missing=status.get("missing", []),
        )
    return B033_VALID_SCHEMA


def _load_authoritative_defs() -> Iterable[Mapping[str, Any]]:
    # Lazy import keeps the service route-agnostic and allows tests/callers to
    # inject a server-owned snapshot without importing Flask application state.
    from app import EQUIPMENT_DEFS

    return EQUIPMENT_DEFS


def _catalog(
    equipment_defs: Iterable[Mapping[str, Any]] | None,
) -> tuple[dict[str, Mapping[str, Any]], dict[str, str]]:
    definitions = tuple(
        equipment_defs if equipment_defs is not None else _load_authoritative_defs()
    )
    all_defs: dict[str, Mapping[str, Any]] = {}
    for definition in definitions:
        if not isinstance(definition, Mapping):
            raise EquipmentOwnershipError(
                "EQUIPMENT_DEFINITION_INVALID",
                "server Equipment definitions must be mappings",
            )
        equip_id = str(definition.get("id") or "").strip()
        if not equip_id or equip_id in all_defs:
            raise EquipmentOwnershipError(
                "EQUIPMENT_DEFINITION_INVALID",
                "server Equipment definitions contain an invalid or duplicate id",
            )
        all_defs[equip_id] = definition

    try:
        functional_slots = build_slot_projection(definitions)
    except Exception as exc:
        raise EquipmentOwnershipError(
            "EQUIPMENT_DEFINITION_INVALID",
            "server Equipment slot projection could not be resolved",
        ) from exc

    # B033 deliberately excludes the two locked/non-functional identities.
    # Every other definition must resolve to one of the canonical functional
    # slots; a missing slot is not silently treated as ownership-only.
    for equip_id, definition in all_defs.items():
        if equip_id in NON_FUNCTIONAL_EQUIPMENT_IDS:
            continue
        if equip_id not in functional_slots:
            raise EquipmentOwnershipError(
                "EQUIPMENT_DEFINITION_INVALID",
                "functional Equipment has no valid canonical slot",
                equip_id=equip_id,
                slot=definition.get("slot"),
            )
        if functional_slots[equip_id] not in CANONICAL_SLOTS:
            raise EquipmentOwnershipError(
                "EQUIPMENT_DEFINITION_INVALID",
                "functional Equipment resolved to an unsupported slot",
                equip_id=equip_id,
                slot=functional_slots[equip_id],
            )
    return all_defs, functional_slots


def _validate_user_id(user_id: Any) -> int:
    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
        raise EquipmentOwnershipError(
            "INVALID_USER_ID", "user_id must be a positive integer"
        )
    return user_id


def _validate_equip_id(equip_id: Any) -> str:
    if not isinstance(equip_id, str) or not equip_id.strip():
        raise EquipmentOwnershipError(
            "INVALID_EQUIPMENT_ID", "equip_id must be a non-empty string"
        )
    return equip_id.strip()


def _validate_source(source: Any) -> str:
    if not isinstance(source, str) or source not in SUPPORTED_SOURCES:
        raise EquipmentOwnershipError(
            "INVALID_OWNERSHIP_SOURCE",
            "source must be a server-owned Equipment grant source",
            allowed_sources=sorted(SUPPORTED_SOURCES),
        )
    return source


def _row_id(value: Any) -> int:
    if isinstance(value, bool):
        raise EquipmentOwnershipError(
            "OWNERSHIP_INSERT_ID_UNAVAILABLE",
            "player_inventory INSERT did not return a valid row id",
        )
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise EquipmentOwnershipError(
            "OWNERSHIP_INSERT_ID_UNAVAILABLE",
            "player_inventory INSERT did not return a valid row id",
        ) from exc
    if result <= 0:
        raise EquipmentOwnershipError(
            "OWNERSHIP_INSERT_ID_UNAVAILABLE",
            "player_inventory INSERT did not return a positive row id",
        )
    return result


def _insert_row(
    conn: Any,
    *,
    user_id: int,
    equip_id: str,
    canonical_slot: str | None,
    source: str,
    schema_state: str,
) -> int:
    obtained_at = datetime.datetime.now().isoformat()
    table = _table_name(conn)
    if schema_state == B033_VALID_SCHEMA:
        statement = (
            f"INSERT INTO {table}"
            "(user_id,equip_id,equipped,canonical_slot,obtained_at,source) "
            "VALUES(?,?,0,?,?,?)"
        )
        parameters = (user_id, equip_id, canonical_slot, obtained_at, source)
    else:
        statement = (
            f"INSERT INTO {table}"
            "(user_id,equip_id,equipped,obtained_at,source) VALUES(?,?,0,?,?)"
        )
        parameters = (user_id, equip_id, obtained_at, source)

    try:
        if _is_sqlite(conn):
            cursor = conn.execute(statement, parameters)
            inserted_id = getattr(cursor, "lastrowid", None)
        else:
            cursor = conn.execute(f"{statement} RETURNING id", parameters)
            row = cursor.fetchone()
            inserted_id = _value(row, 0, "id") if row is not None else None
    except Exception as exc:
        raise EquipmentOwnershipError(
            "OWNERSHIP_INSERT_FAILED",
            "player_inventory ownership insert failed",
            schema_state=schema_state,
            equip_id=equip_id,
        ) from exc
    return _row_id(inserted_id)


def grant_equipment_ownership(
    conn: Any,
    user_id: Any,
    equip_id: Any,
    source: Any,
    *,
    equipment_defs: Iterable[Mapping[str, Any]] | None = None,
) -> EquipmentOwnershipResult:
    """Create one server-authorized, unequipped Equipment ownership row.

    The function performs no ``commit`` or ``rollback``. ``source`` is the
    bounded server vocabulary used by the current Monster, Admin, and Coin
    Shop writers: ``drop``, ``admin``, and ``coin_shop``. It accepts no client
    slot or equipped flag; the row is always created with ``equipped=0``.
    """

    user_id = _validate_user_id(user_id)
    equip_id = _validate_equip_id(equip_id)
    source = _validate_source(source)
    all_defs, functional_slots = _catalog(equipment_defs)

    if equip_id not in all_defs:
        raise EquipmentOwnershipError(
            "UNKNOWN_EQUIPMENT",
            "unknown server Equipment id",
            equip_id=equip_id,
        )

    if equip_id in NON_FUNCTIONAL_EQUIPMENT_IDS:
        # xp_amulet remains HOLD_FOR_AUTHORITY and go_stone_black remains an
        # inventory-only Trophy. Current Monster/Admin ownership semantics
        # permit the record to exist, but it can never be functional here.
        canonical_slot = None
    else:
        canonical_slot = functional_slots.get(equip_id)
        if canonical_slot is None:
            raise EquipmentOwnershipError(
                "EQUIPMENT_DEFINITION_INVALID",
                "functional Equipment has no canonical slot",
                equip_id=equip_id,
            )

    schema_state = _schema_state(conn)
    inserted_id = _insert_row(
        conn,
        user_id=user_id,
        equip_id=equip_id,
        canonical_slot=canonical_slot,
        source=source,
        schema_state=schema_state,
    )
    return EquipmentOwnershipResult(
        row_id=inserted_id,
        user_id=user_id,
        equip_id=equip_id,
        canonical_slot=canonical_slot,
        equipped=False,
        source=source,
    )


__all__ = [
    "B033_MALFORMED_SCHEMA",
    "B033_VALID_SCHEMA",
    "EquipmentOwnershipError",
    "EquipmentOwnershipResult",
    "LEGACY_SCHEMA",
    "SUPPORTED_SOURCES",
    "grant_equipment_ownership",
]
