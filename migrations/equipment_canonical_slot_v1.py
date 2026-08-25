"""Additive canonical-slot projection for the existing Equipment authority.

This is a migration candidate only.  It is not imported by application
startup, never commits, and never repairs data.  ``app.EQUIPMENT_DEFS``
remains the server-side slot-definition authority; ``canonical_slot`` is only
an additive projection used to enforce one effective equipped item per user
and canonical slot.

The migration deliberately separates the phases:

* add the nullable projection;
* backfill known functional Equipment from the server definition registry;
* fail closed on malformed equipped rows;
* add the final validity and uniqueness gates only after a clean preflight.

PostgreSQL uses a CHECK constraint.  SQLite cannot add a CHECK constraint to
an existing table with portable ALTER TABLE syntax, so its equivalent
validity enforcement is two named BEFORE INSERT/UPDATE triggers.  Both
dialects enforce the same ``equipped=true -> canonical_slot IS NOT NULL``
semantics.
"""

from __future__ import annotations

from collections import defaultdict
import re
from typing import Any, Iterable, Mapping


SCHEMA_VERSION = "equipment_canonical_slot_v1"
TABLE_NAME = "player_inventory"
CANONICAL_SLOT_COLUMN = "canonical_slot"
VALIDITY_CONSTRAINT_NAME = "ck_player_inventory_equipped_requires_slot"
UNIQUE_INDEX_NAME = "uq_player_inventory_user_equipped_slot"
SQLITE_VALIDITY_INSERT_TRIGGER = "trg_player_inventory_equipped_requires_slot_insert"
SQLITE_VALIDITY_UPDATE_TRIGGER = "trg_player_inventory_equipped_requires_slot_update"
ADVISORY_LOCK_KEY = 773310034

CANONICAL_SLOTS = ("weapon", "armor", "accessory")
INVENTORY_ONLY_EQUIPMENT_IDS = frozenset({"go_stone_black"})
HOLD_FOR_AUTHORITY_EQUIPMENT_IDS = frozenset({"xp_amulet"})
NON_FUNCTIONAL_EQUIPMENT_IDS = (
    INVENTORY_ONLY_EQUIPMENT_IDS | HOLD_FOR_AUTHORITY_EQUIPMENT_IDS
)

BASE_COLUMNS = frozenset({"user_id", "equip_id", "equipped"})


class MigrationError(RuntimeError):
    """Base class for fail-closed schema-candidate errors."""


class SchemaMismatch(MigrationError):
    """The existing table or final constraint shape is incompatible."""


class MalformedInventoryState(MigrationError):
    """The required preflight found data that must be repaired explicitly."""

    def __init__(self, report: dict[str, Any]):
        self.report = report
        categories = ", ".join(report.get("blocking_categories", ())) or "unknown"
        super().__init__(f"player_inventory migration preflight blocked: {categories}")


def _is_sqlite(conn: Any) -> bool:
    raw = getattr(conn, "_conn", conn)
    return raw.__class__.__module__.startswith("sqlite3")


def _value(row: Any, index: int, name: str) -> Any:
    try:
        return row[name]
    except (KeyError, TypeError, IndexError):
        return row[index]


def _normalize_sql(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").upper().replace('"', ""))


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


def _column_nullability(conn: Any, column: str) -> bool | None:
    if _is_sqlite(conn):
        rows = conn.execute(f"PRAGMA table_info({TABLE_NAME})").fetchall()
        for row in rows:
            if str(_value(row, 1, "name")) == column:
                return not bool(_value(row, 3, "notnull"))
        return None
    row = conn.execute(
        """SELECT is_nullable
             FROM information_schema.columns
            WHERE table_schema='public' AND table_name=? AND column_name=?""",
        (TABLE_NAME, column),
    ).fetchone()
    if row is None:
        return None
    return str(_value(row, 0, "is_nullable")).upper() == "YES"


def _postgres_constraints(conn: Any) -> dict[str, str]:
    rows = conn.execute(
        """SELECT c.conname, pg_get_constraintdef(c.oid)
             FROM pg_constraint c
             JOIN pg_class t ON t.oid=c.conrelid
             JOIN pg_namespace n ON n.oid=t.relnamespace
            WHERE n.nspname='public' AND t.relname=?
            ORDER BY c.conname""",
        (TABLE_NAME,),
    ).fetchall()
    return {
        str(_value(row, 0, "conname")): str(_value(row, 1, "pg_get_constraintdef"))
        for row in rows
    }


def _postgres_indexes(conn: Any) -> dict[str, str]:
    rows = conn.execute(
        """SELECT indexname, indexdef
             FROM pg_indexes
            WHERE schemaname='public' AND tablename=?""",
        (TABLE_NAME,),
    ).fetchall()
    return {
        str(_value(row, 0, "indexname")): str(_value(row, 1, "indexdef"))
        for row in rows
    }


def _sqlite_indexes(conn: Any) -> dict[str, str]:
    rows = conn.execute(
        """SELECT name, sql
             FROM sqlite_master
            WHERE type='index' AND tbl_name=?""",
        (TABLE_NAME,),
    ).fetchall()
    return {
        str(_value(row, 0, "name")): str(_value(row, 1, "sql"))
        for row in rows
    }


def _sqlite_triggers(conn: Any) -> dict[str, str]:
    rows = conn.execute(
        """SELECT name, sql
             FROM sqlite_master
            WHERE type='trigger' AND tbl_name=?""",
        (TABLE_NAME,),
    ).fetchall()
    return {
        str(_value(row, 0, "name")): str(_value(row, 1, "sql"))
        for row in rows
    }


def _validity_definition_matches(definition: str) -> bool:
    normalized = _normalize_sql(definition)
    return (
        "EQUIPPED=0" in normalized
        and "CANONICAL_SLOTISNOTNULL" in normalized
    )


def _unique_index_definition_matches(definition: str) -> bool:
    normalized = _normalize_sql(definition)
    return (
        "UNIQUEINDEX" in normalized
        and "USER_ID" in normalized
        and "CANONICAL_SLOT" in normalized
        and "EQUIPPED=1" in normalized
        and "CANONICAL_SLOTISNOTNULL" in normalized
    )


def _sqlite_validity_trigger_matches(definition: str) -> bool:
    normalized = _normalize_sql(definition)
    return "NEW.EQUIPPED=1" in normalized and "NEW.CANONICAL_SLOTISNULL" in normalized


def validate_schema(conn: Any) -> dict[str, Any]:
    """Return non-mutating schema status for this candidate."""

    columns = _column_names(conn)
    missing: list[str] = []
    if not columns:
        missing.append(TABLE_NAME)
        return {
            "schema_version": SCHEMA_VERSION,
            "table": TABLE_NAME,
            "dialect": "sqlite" if _is_sqlite(conn) else "postgresql",
            "columns": [],
            "missing": missing,
            "canonical_slot_nullable": None,
            "validity_constraint": False,
            "partial_unique_index": False,
            "valid": False,
        }

    if not BASE_COLUMNS.issubset(columns):
        missing.extend(sorted(BASE_COLUMNS - columns))
    if CANONICAL_SLOT_COLUMN not in columns:
        missing.append(CANONICAL_SLOT_COLUMN)
    canonical_slot_nullable = _column_nullability(conn, CANONICAL_SLOT_COLUMN)
    if canonical_slot_nullable is not True:
        missing.append("canonical_slot_nullable")

    if _is_sqlite(conn):
        triggers = _sqlite_triggers(conn)
        insert_definition = triggers.get(SQLITE_VALIDITY_INSERT_TRIGGER, "")
        update_definition = triggers.get(SQLITE_VALIDITY_UPDATE_TRIGGER, "")
        validity_constraint = (
            _sqlite_validity_trigger_matches(insert_definition)
            and _sqlite_validity_trigger_matches(update_definition)
        )
        indexes = _sqlite_indexes(conn)
        unique_definition = indexes.get(UNIQUE_INDEX_NAME, "")
        partial_unique_index = _unique_index_definition_matches(unique_definition)
    else:
        constraints = _postgres_constraints(conn)
        validity_constraint = _validity_definition_matches(
            constraints.get(VALIDITY_CONSTRAINT_NAME, "")
        )
        indexes = _postgres_indexes(conn)
        unique_definition = indexes.get(UNIQUE_INDEX_NAME, "")
        partial_unique_index = _unique_index_definition_matches(unique_definition)

    if not validity_constraint:
        missing.append("equipped_requires_canonical_slot")
    if not partial_unique_index:
        missing.append(UNIQUE_INDEX_NAME)

    return {
        "schema_version": SCHEMA_VERSION,
        "table": TABLE_NAME,
        "dialect": "sqlite" if _is_sqlite(conn) else "postgresql",
        "columns": sorted(columns),
        "missing": sorted(set(missing)),
        "canonical_slot_nullable": canonical_slot_nullable,
        "validity_constraint": validity_constraint,
        "partial_unique_index": partial_unique_index,
        "valid": not missing,
    }


def _load_authoritative_equipment_defs() -> Iterable[Mapping[str, Any]]:
    """Load the current server registry only when a caller omits test input."""

    from app import EQUIPMENT_DEFS

    return EQUIPMENT_DEFS


def _catalog(
    equipment_defs: Iterable[Mapping[str, Any]] | None,
) -> tuple[dict[str, Mapping[str, Any]], dict[str, str]]:
    definitions = equipment_defs
    if definitions is None:
        definitions = _load_authoritative_equipment_defs()

    all_defs: dict[str, Mapping[str, Any]] = {}
    functional_slots: dict[str, str] = {}
    for definition in definitions:
        equip_id = str(definition.get("id") or "")
        if not equip_id:
            raise MigrationError("EQUIPMENT_DEFS contains an item without an id")
        if equip_id in all_defs:
            raise MigrationError(f"EQUIPMENT_DEFS contains duplicate id: {equip_id}")
        all_defs[equip_id] = definition
        if equip_id in NON_FUNCTIONAL_EQUIPMENT_IDS:
            continue
        slot = definition.get("slot")
        if slot in (None, ""):
            continue
        if slot not in CANONICAL_SLOTS:
            raise MigrationError(f"EQUIPMENT_DEFS contains invalid slot: {equip_id}={slot!r}")
        functional_slots[equip_id] = str(slot)
    return all_defs, functional_slots


def build_slot_projection(
    equipment_defs: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, str]:
    """Return the server-derived slot projection for functional Equipment."""

    return _catalog(equipment_defs)[1]


def _row_as_dict(row: Any, columns: tuple[str, ...]) -> dict[str, Any]:
    return {column: _value(row, index, column) for index, column in enumerate(columns)}


def _equipped_rows(conn: Any) -> list[dict[str, Any]]:
    columns = _column_names(conn)
    if CANONICAL_SLOT_COLUMN not in columns:
        raise SchemaMismatch("player_inventory.canonical_slot is not present")
    selected = ["user_id", "equip_id", "equipped", CANONICAL_SLOT_COLUMN]
    if "id" in columns:
        selected.insert(0, "id")
    cursor = conn.execute(
        f"SELECT {', '.join(selected)} FROM {_table_name(conn)} "
        "WHERE equipped=1 ORDER BY user_id, equip_id",
    )
    return [_row_as_dict(row, tuple(selected)) for row in cursor.fetchall()]


def _compact_row(row: Mapping[str, Any]) -> dict[str, Any]:
    result = {
        "user_id": row.get("user_id"),
        "equip_id": row.get("equip_id"),
        "equipped": row.get("equipped"),
        "canonical_slot": row.get(CANONICAL_SLOT_COLUMN),
    }
    if "id" in row:
        result["id"] = row["id"]
    return result


def detect_malformed_rows(
    conn: Any,
    equipment_defs: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Detect blocking equipped rows without mutating or repairing them."""

    all_defs, functional_slots = _catalog(equipment_defs)
    rows = _equipped_rows(conn)
    blockers: dict[str, list[dict[str, Any]]] = {}

    unknown = [row for row in rows if row["equip_id"] not in all_defs]
    if unknown:
        blockers["UNKNOWN_EQUIPPED_EQUIP_ID"] = [_compact_row(row) for row in unknown]

    null_slot = [
        row for row in rows if row[CANONICAL_SLOT_COLUMN] is None
    ]
    if null_slot:
        blockers["EQUIPPED_WITH_NULL_CANONICAL_SLOT"] = [
            _compact_row(row) for row in null_slot
        ]

    go_stone = [row for row in rows if row["equip_id"] == "go_stone_black"]
    if go_stone:
        blockers["GO_STONE_BLACK_EQUIPPED"] = [_compact_row(row) for row in go_stone]

    xp_amulet = [row for row in rows if row["equip_id"] == "xp_amulet"]
    if xp_amulet:
        blockers["XP_AMULET_EQUIPPED"] = [_compact_row(row) for row in xp_amulet]

    grouped: dict[tuple[Any, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        slot = functional_slots.get(str(row["equip_id"]))
        if slot:
            grouped[(row["user_id"], slot)].append(row)
    for (user_id, slot), grouped_rows in sorted(
        grouped.items(), key=lambda entry: (str(entry[0][0]), entry[0][1])
    ):
        if len(grouped_rows) <= 1:
            continue
        category = f"DUPLICATE_EQUIPPED_{slot.upper()}"
        blockers[category] = [
            {
                "user_id": user_id,
                "canonical_slot": slot,
                "rows": [_compact_row(row) for row in grouped_rows],
            }
        ]

    return {
        "clean": not blockers,
        "blocking_categories": sorted(blockers),
        "blockers": blockers,
        "equipped_row_count": len(rows),
    }


def _ensure_projection_column(conn: Any, *, dry_run: bool) -> list[str]:
    if CANONICAL_SLOT_COLUMN in _column_names(conn):
        return []
    if dry_run:
        return [CANONICAL_SLOT_COLUMN]
    conn.execute(
        f"ALTER TABLE {_table_name(conn)} ADD COLUMN {CANONICAL_SLOT_COLUMN} TEXT"
    )
    return [CANONICAL_SLOT_COLUMN]


def _backfill_known_functional_equipment(
    conn: Any,
    functional_slots: Mapping[str, str],
    *,
    dry_run: bool,
) -> int:
    if dry_run:
        return 0
    changed = 0
    for equip_id, slot in sorted(functional_slots.items()):
        cursor = conn.execute(
            f"UPDATE {_table_name(conn)} SET {CANONICAL_SLOT_COLUMN}=? "
            "WHERE equip_id=?",
            (slot, equip_id),
        )
        if getattr(cursor, "rowcount", -1) >= 0:
            changed += int(cursor.rowcount)
    return changed


def _ensure_validity_enforcement(conn: Any) -> list[str]:
    created: list[str] = []
    if _is_sqlite(conn):
        triggers = _sqlite_triggers(conn)
        if SQLITE_VALIDITY_INSERT_TRIGGER in triggers:
            if not _sqlite_validity_trigger_matches(
                triggers[SQLITE_VALIDITY_INSERT_TRIGGER]
            ):
                raise SchemaMismatch("existing SQLite insert validity trigger is incorrect")
        else:
            conn.execute(
                f"""CREATE TRIGGER IF NOT EXISTS {SQLITE_VALIDITY_INSERT_TRIGGER}
                    BEFORE INSERT ON {TABLE_NAME}
                    WHEN NEW.equipped=1 AND NEW.canonical_slot IS NULL
                    BEGIN
                      SELECT RAISE(ABORT, 'equipped item requires canonical_slot');
                    END"""
            )
            created.append(SQLITE_VALIDITY_INSERT_TRIGGER)
        if SQLITE_VALIDITY_UPDATE_TRIGGER in triggers:
            if not _sqlite_validity_trigger_matches(
                triggers[SQLITE_VALIDITY_UPDATE_TRIGGER]
            ):
                raise SchemaMismatch("existing SQLite update validity trigger is incorrect")
        else:
            conn.execute(
                f"""CREATE TRIGGER IF NOT EXISTS {SQLITE_VALIDITY_UPDATE_TRIGGER}
                    BEFORE UPDATE OF equipped, canonical_slot ON {TABLE_NAME}
                    WHEN NEW.equipped=1 AND NEW.canonical_slot IS NULL
                    BEGIN
                      SELECT RAISE(ABORT, 'equipped item requires canonical_slot');
                    END"""
            )
            created.append(SQLITE_VALIDITY_UPDATE_TRIGGER)
        return created

    constraints = _postgres_constraints(conn)
    existing = constraints.get(VALIDITY_CONSTRAINT_NAME)
    if existing:
        if not _validity_definition_matches(existing):
            raise SchemaMismatch("existing PostgreSQL validity constraint is incorrect")
    else:
        conn.execute(
            f"""ALTER TABLE public.{TABLE_NAME}
                 ADD CONSTRAINT {VALIDITY_CONSTRAINT_NAME}
                 CHECK (equipped=0 OR canonical_slot IS NOT NULL)"""
        )
        created.append(VALIDITY_CONSTRAINT_NAME)
    return created


def _ensure_unique_index(conn: Any) -> list[str]:
    if _is_sqlite(conn):
        indexes = _sqlite_indexes(conn)
        existing = indexes.get(UNIQUE_INDEX_NAME)
        if existing and not _unique_index_definition_matches(existing):
            raise SchemaMismatch("existing SQLite unique index is incorrect")
        if not existing:
            conn.execute(
                f"""CREATE UNIQUE INDEX IF NOT EXISTS {UNIQUE_INDEX_NAME}
                    ON {TABLE_NAME}(user_id, canonical_slot)
                    WHERE equipped=1 AND canonical_slot IS NOT NULL"""
            )
            return [UNIQUE_INDEX_NAME]
        return []

    indexes = _postgres_indexes(conn)
    existing = indexes.get(UNIQUE_INDEX_NAME)
    if existing and not _unique_index_definition_matches(existing):
        raise SchemaMismatch("existing PostgreSQL unique index is incorrect")
    if not existing:
        conn.execute(
            f"""CREATE UNIQUE INDEX IF NOT EXISTS {UNIQUE_INDEX_NAME}
                ON public.{TABLE_NAME}(user_id, canonical_slot)
                WHERE equipped=1 AND canonical_slot IS NOT NULL"""
        )
        return [UNIQUE_INDEX_NAME]
    return []


def upgrade(
    conn: Any,
    *,
    equipment_defs: Iterable[Mapping[str, Any]] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Apply the additive candidate without committing the caller transaction.

    A malformed preflight raises :class:`MalformedInventoryState` after the
    nullable projection/backfill phase and before either final enforcement
    object is created.  The caller owns rollback/commit.
    """

    columns = _column_names(conn)
    if not columns:
        raise SchemaMismatch(f"{TABLE_NAME} does not exist")
    missing_base = BASE_COLUMNS - columns
    if missing_base:
        raise SchemaMismatch(f"{TABLE_NAME} is missing base columns: {sorted(missing_base)}")
    if not _is_sqlite(conn):
        conn.execute("SELECT pg_advisory_xact_lock(?)", (ADVISORY_LOCK_KEY,))

    _all_defs, functional_slots = _catalog(equipment_defs)
    before = validate_schema(conn)
    if dry_run:
        preflight = (
            detect_malformed_rows(conn, equipment_defs)
            if CANONICAL_SLOT_COLUMN in columns
            else {"clean": None, "blocking_categories": [], "blockers": {}}
        )
        return {
            **before,
            "created": [],
            "backfilled_rows": 0,
            "planned": {
                "add_projection": CANONICAL_SLOT_COLUMN not in columns,
                "backfill_known_functional": True,
                "add_validity_enforcement": True,
                "add_partial_unique_index": True,
            },
            "malformed_preflight": preflight,
            "dry_run": True,
        }

    created = _ensure_projection_column(conn, dry_run=False)
    backfilled_rows = _backfill_known_functional_equipment(
        conn, functional_slots, dry_run=False
    )
    preflight = detect_malformed_rows(conn, equipment_defs)
    if not preflight["clean"]:
        raise MalformedInventoryState(preflight)

    created.extend(_ensure_validity_enforcement(conn))
    created.extend(_ensure_unique_index(conn))
    after = validate_schema(conn)
    if not after["valid"]:
        raise SchemaMismatch(f"{TABLE_NAME} schema candidate incomplete: {after['missing']}")
    return {
        **after,
        "created": created,
        "backfilled_rows": backfilled_rows,
        "malformed_preflight": preflight,
        "dry_run": False,
    }


def downgrade_for_isolated_test(conn: Any) -> None:
    """Remove only this candidate from a disposable test table."""

    if _is_sqlite(conn):
        conn.execute(f"DROP INDEX IF EXISTS {UNIQUE_INDEX_NAME}")
        conn.execute(f"DROP TRIGGER IF EXISTS {SQLITE_VALIDITY_INSERT_TRIGGER}")
        conn.execute(f"DROP TRIGGER IF EXISTS {SQLITE_VALIDITY_UPDATE_TRIGGER}")
        if CANONICAL_SLOT_COLUMN in _column_names(conn):
            conn.execute(f"ALTER TABLE {TABLE_NAME} DROP COLUMN {CANONICAL_SLOT_COLUMN}")
    else:
        conn.execute(f"DROP INDEX IF EXISTS public.{UNIQUE_INDEX_NAME}")
        conn.execute(
            f"ALTER TABLE public.{TABLE_NAME} DROP CONSTRAINT IF EXISTS {VALIDITY_CONSTRAINT_NAME}"
        )
        if CANONICAL_SLOT_COLUMN in _column_names(conn):
            conn.execute(
                f"ALTER TABLE public.{TABLE_NAME} DROP COLUMN IF EXISTS {CANONICAL_SLOT_COLUMN}"
            )


__all__ = [
    "ADVISORY_LOCK_KEY",
    "CANONICAL_SLOTS",
    "CANONICAL_SLOT_COLUMN",
    "HOLD_FOR_AUTHORITY_EQUIPMENT_IDS",
    "INVENTORY_ONLY_EQUIPMENT_IDS",
    "MalformedInventoryState",
    "MigrationError",
    "NON_FUNCTIONAL_EQUIPMENT_IDS",
    "SCHEMA_VERSION",
    "SchemaMismatch",
    "TABLE_NAME",
    "UNIQUE_INDEX_NAME",
    "VALIDITY_CONSTRAINT_NAME",
    "build_slot_projection",
    "detect_malformed_rows",
    "downgrade_for_isolated_test",
    "upgrade",
    "validate_schema",
]
