"""Additive F015 schema for World Battlefield Boss milestone evidence.

This migration is a candidate only.  It never commits, is not imported by
request-time application startup, and does not apply World progression.  The
caller owns the transaction around ``upgrade`` and around the storage service.

The composite primary key ``(user_id, settlement_id)`` is intentional:
``settlement_id`` has not been proven globally unique.  The table records
consumed server facts only; it has no Zone-clear, Star, Lord, Quest, or other
World-policy state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


SCHEMA_VERSION = "world_battlefield_boss_milestone_v1"
TABLE_NAME = "world_battlefield_boss_milestones"
ADVISORY_LOCK_KEY = 773310032
DEDUPE_KEY = ("user_id", "settlement_id")

SOURCE_EVENT_TYPE = "MONSTER_DEFEATED"
SOURCE_AUTHORITY = "SERVER_MONSTER_SETTLEMENT"
CONTRACT_VERSION = "BATTLEFIELD_BOSS_DEFEATED_FACT_V1"

INDEX_SPECS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "idx_world_boss_milestones_user_zone",
        ("user_id", "zone_key"),
    ),
    (
        "idx_world_boss_milestones_operation",
        ("encounter_operation_id",),
    ),
    (
        "idx_world_boss_milestones_created_at",
        ("created_at",),
    ),
)


class MigrationError(RuntimeError):
    """Base class for fail-closed F015 schema failures."""


class SchemaMismatch(MigrationError):
    """An existing table does not satisfy the F015 contract."""


@dataclass(frozen=True)
class ColumnSpec:
    name: str
    postgres_type: str
    sqlite_type: str
    nullable: bool


COLUMNS = (
    ColumnSpec("user_id", "integer", "INTEGER", False),
    ColumnSpec("settlement_id", "text", "TEXT", False),
    ColumnSpec("zone_key", "text", "TEXT", False),
    ColumnSpec("monster_id", "text", "TEXT", False),
    ColumnSpec("encounter_operation_id", "text", "TEXT", False),
    ColumnSpec("eligibility_reference", "text", "TEXT", False),
    ColumnSpec("intent_replay_fingerprint", "text", "TEXT", False),
    ColumnSpec("source_authority", "text", "TEXT", False),
    ColumnSpec("occurred_at", "timestamp with time zone", "TEXT", False),
    ColumnSpec("created_at", "timestamp with time zone", "TEXT", False),
    ColumnSpec("source_event_type", "text", "TEXT", False),
    ColumnSpec("contract_version", "text", "TEXT", False),
)

_CHECK_FRAGMENTS = (
    "USER_ID > 0",
    "SOURCE_AUTHORITY = 'SERVER_MONSTER_SETTLEMENT'",
    "SOURCE_EVENT_TYPE = 'MONSTER_DEFEATED'",
    "CONTRACT_VERSION = 'BATTLEFIELD_BOSS_DEFEATED_FACT_V1'",
)
_POSTGRES_CHECK_NAMES = (
    "ck_world_boss_milestone_user_positive",
    "ck_world_boss_milestone_source_authority",
    "ck_world_boss_milestone_event_type",
    "ck_world_boss_milestone_contract_version",
)


def _raw(conn: Any) -> Any:
    return getattr(conn, "_conn", conn)


def _is_sqlite(conn: Any) -> bool:
    return _raw(conn).__class__.__module__.lower().startswith("sqlite3")


def _row_value(row: Any, index: int, name: str) -> Any:
    try:
        return row[name]
    except (KeyError, TypeError, IndexError):
        return row[index]


def _execute(conn: Any, sql: str, params: Iterable[Any] = ()) -> Any:
    values = tuple(params)
    if hasattr(conn, "execute"):
        return conn.execute(sql, values)
    cursor = conn.cursor()
    cursor.execute(sql.replace("?", "%s"), values)
    return cursor


def _fetchall(conn: Any, sql: str, params: Iterable[Any] = ()) -> list[Any]:
    cursor = _execute(conn, sql, params)
    try:
        return list(cursor.fetchall())
    finally:
        if not hasattr(conn, "execute"):
            cursor.close()


def _fetchone(conn: Any, sql: str, params: Iterable[Any] = ()) -> Any:
    cursor = _execute(conn, sql, params)
    try:
        return cursor.fetchone()
    finally:
        if not hasattr(conn, "execute"):
            cursor.close()


def _normalize_type(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _table_columns(conn: Any) -> dict[str, Any]:
    if _is_sqlite(conn):
        rows = _fetchall(conn, f"PRAGMA table_info({TABLE_NAME})")
        return {str(_row_value(row, 1, "name")): row for row in rows}
    rows = _fetchall(
        conn,
        """SELECT column_name, data_type, is_nullable
             FROM information_schema.columns
            WHERE table_schema='public' AND table_name=?
            ORDER BY ordinal_position""",
        (TABLE_NAME,),
    )
    return {str(_row_value(row, 0, "column_name")): row for row in rows}


def _primary_key(conn: Any) -> tuple[str, ...]:
    if _is_sqlite(conn):
        rows = _fetchall(conn, f"PRAGMA table_info({TABLE_NAME})")
        return tuple(
            str(_row_value(row, 1, "name"))
            for row in sorted(rows, key=lambda item: int(_row_value(item, 5, "pk")))
            if int(_row_value(row, 5, "pk")) > 0
        )
    rows = _fetchall(
        conn,
        """SELECT kcu.column_name, kcu.ordinal_position
             FROM information_schema.table_constraints tc
             JOIN information_schema.key_column_usage kcu
               ON tc.constraint_name=kcu.constraint_name
              AND tc.table_schema=kcu.table_schema
            WHERE tc.table_schema='public'
              AND tc.table_name=?
              AND tc.constraint_type='PRIMARY KEY'
         ORDER BY kcu.ordinal_position""",
        (TABLE_NAME,),
    )
    return tuple(str(_row_value(row, 0, "column_name")) for row in rows)


def _unique_sets(conn: Any) -> set[tuple[str, ...]]:
    if _is_sqlite(conn):
        result: set[tuple[str, ...]] = set()
        for row in _fetchall(conn, f"PRAGMA index_list({TABLE_NAME})"):
            if bool(_row_value(row, 2, "unique")):
                index_name = str(_row_value(row, 1, "name"))
                columns = tuple(
                    str(_row_value(item, 2, "name"))
                    for item in _fetchall(conn, f"PRAGMA index_info({index_name})")
                )
                result.add(columns)
        return result

    rows = _fetchall(
        conn,
        """SELECT tc.constraint_type, kcu.constraint_name,
                          kcu.column_name, kcu.ordinal_position
             FROM information_schema.table_constraints tc
             JOIN information_schema.key_column_usage kcu
               ON tc.constraint_name=kcu.constraint_name
              AND tc.table_schema=kcu.table_schema
            WHERE tc.table_schema='public'
              AND tc.table_name=?
              AND tc.constraint_type IN ('PRIMARY KEY', 'UNIQUE')
         ORDER BY kcu.constraint_name, kcu.ordinal_position""",
        (TABLE_NAME,),
    )
    grouped: dict[str, list[str]] = {}
    for row in rows:
        name = str(_row_value(row, 1, "constraint_name"))
        grouped.setdefault(name, []).append(str(_row_value(row, 2, "column_name")))
    return {tuple(columns) for columns in grouped.values()}


def _index_names(conn: Any) -> set[str]:
    if _is_sqlite(conn):
        return {
            str(_row_value(row, 1, "name"))
            for row in _fetchall(conn, f"PRAGMA index_list({TABLE_NAME})")
        }
    return {
        str(_row_value(row, 0, "indexname"))
        for row in _fetchall(
            conn,
            """SELECT indexname FROM pg_indexes
                WHERE schemaname='public' AND tablename=?""",
            (TABLE_NAME,),
        )
    }


def _index_columns(conn: Any, index_name: str) -> tuple[str, ...]:
    if _is_sqlite(conn):
        return tuple(
            str(_row_value(row, 2, "name"))
            for row in _fetchall(conn, f"PRAGMA index_info({index_name})")
        )
    rows = _fetchall(
        conn,
        """SELECT a.attname
             FROM pg_index i
             JOIN pg_class t ON t.oid=i.indrelid
             JOIN pg_class ix ON ix.oid=i.indexrelid
             JOIN pg_attribute a ON a.attrelid=t.oid
                               AND a.attnum=ANY(i.indkey)
            WHERE t.relname=? AND ix.relname=?
         ORDER BY array_position(i.indkey, a.attnum)""",
        (TABLE_NAME, index_name),
    )
    return tuple(str(_row_value(row, 0, "attname")) for row in rows)


def _check_contract_constraints(conn: Any) -> None:
    if _is_sqlite(conn):
        row = _fetchone(
            conn,
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (TABLE_NAME,),
        )
        sql = str(_row_value(row, 0, "sql") if row is not None else "").upper()
        missing = [fragment for fragment in _CHECK_FRAGMENTS if fragment not in sql]
        if missing:
            raise SchemaMismatch(f"{TABLE_NAME}: required checks missing {missing}")
        return

    rows = _fetchall(
        conn,
        """SELECT conname, pg_get_constraintdef(oid)
             FROM pg_constraint
            WHERE conrelid = 'public.world_battlefield_boss_milestones'::regclass
              AND contype='c'""",
    )
    names = {str(_row_value(row, 0, "conname")) for row in rows}
    missing = sorted(set(_POSTGRES_CHECK_NAMES) - names)
    if missing:
        raise SchemaMismatch(f"{TABLE_NAME}: required checks missing {missing}")


def validate_schema(conn: Any) -> dict[str, Any]:
    """Validate the exact additive F015 table without changing the database."""

    found = _table_columns(conn)
    if not found:
        return {
            "schema_version": SCHEMA_VERSION,
            "table": TABLE_NAME,
            "present": False,
            "valid": False,
            "missing": [TABLE_NAME],
            "columns": [],
            "indexes": [],
        }

    expected = {spec.name: spec for spec in COLUMNS}
    if set(found) != set(expected):
        raise SchemaMismatch(
            f"{TABLE_NAME}: columns differ; unexpected={sorted(set(found)-set(expected))}, "
            f"missing={sorted(set(expected)-set(found))}"
        )
    for name, spec in expected.items():
        row = found[name]
        if _is_sqlite(conn):
            observed_type = _normalize_type(_row_value(row, 2, "type"))
            nullable = not bool(_row_value(row, 3, "notnull"))
            expected_type = _normalize_type(spec.sqlite_type)
        else:
            observed_type = _normalize_type(_row_value(row, 1, "data_type"))
            nullable = str(_row_value(row, 2, "is_nullable")).upper() == "YES"
            expected_type = _normalize_type(spec.postgres_type)
        if observed_type != expected_type or nullable != spec.nullable:
            raise SchemaMismatch(
                f"{TABLE_NAME}.{name}: expected type={expected_type} nullable={spec.nullable}; "
                f"observed type={observed_type} nullable={nullable}"
            )

    primary = _primary_key(conn)
    if primary != DEDUPE_KEY:
        raise SchemaMismatch(f"{TABLE_NAME}: primary key differs: {primary!r}")
    if DEDUPE_KEY not in _unique_sets(conn):
        raise SchemaMismatch(f"{TABLE_NAME}: composite dedupe uniqueness is missing")

    index_names = _index_names(conn)
    expected_indexes = {name for name, _columns in INDEX_SPECS}
    missing_indexes = sorted(expected_indexes - index_names)
    if missing_indexes:
        raise SchemaMismatch(f"{TABLE_NAME}: indexes missing {missing_indexes}")
    for index_name, columns in INDEX_SPECS:
        if _index_columns(conn, index_name) != columns:
            raise SchemaMismatch(f"{TABLE_NAME}: index {index_name} columns differ")
    _check_contract_constraints(conn)
    return {
        "schema_version": SCHEMA_VERSION,
        "table": TABLE_NAME,
        "present": True,
        "valid": True,
        "missing": [],
        "columns": sorted(found),
        "indexes": sorted(expected_indexes),
        "dedupe_key": list(DEDUPE_KEY),
    }


def _create_sqlite_sql() -> str:
    return f"""CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
        user_id INTEGER NOT NULL CHECK (user_id > 0),
        settlement_id TEXT NOT NULL CHECK (length(trim(settlement_id)) > 0),
        zone_key TEXT NOT NULL CHECK (length(trim(zone_key)) > 0),
        monster_id TEXT NOT NULL CHECK (length(trim(monster_id)) > 0),
        encounter_operation_id TEXT NOT NULL CHECK (length(trim(encounter_operation_id)) > 0),
        eligibility_reference TEXT NOT NULL CHECK (length(trim(eligibility_reference)) > 0),
        intent_replay_fingerprint TEXT NOT NULL CHECK (length(trim(intent_replay_fingerprint)) > 0),
        source_authority TEXT NOT NULL
            CONSTRAINT ck_world_boss_milestone_source_authority
            CHECK (source_authority = '{SOURCE_AUTHORITY}'),
        occurred_at TEXT NOT NULL,
        created_at TEXT NOT NULL,
        source_event_type TEXT NOT NULL
            CONSTRAINT ck_world_boss_milestone_event_type
            CHECK (source_event_type = '{SOURCE_EVENT_TYPE}'),
        contract_version TEXT NOT NULL
            CONSTRAINT ck_world_boss_milestone_contract_version
            CHECK (contract_version = '{CONTRACT_VERSION}'),
        CONSTRAINT ck_world_boss_milestone_user_positive CHECK (user_id > 0),
        PRIMARY KEY (user_id, settlement_id)
    )"""


def _create_postgres_sql() -> str:
    return f"""CREATE TABLE IF NOT EXISTS public.{TABLE_NAME} (
        user_id INTEGER NOT NULL,
        settlement_id TEXT NOT NULL,
        zone_key TEXT NOT NULL,
        monster_id TEXT NOT NULL,
        encounter_operation_id TEXT NOT NULL,
        eligibility_reference TEXT NOT NULL,
        intent_replay_fingerprint TEXT NOT NULL,
        source_authority TEXT NOT NULL,
        occurred_at TIMESTAMPTZ NOT NULL,
        created_at TIMESTAMPTZ NOT NULL,
        source_event_type TEXT NOT NULL,
        contract_version TEXT NOT NULL,
        CONSTRAINT ck_world_boss_milestone_user_positive CHECK (user_id > 0),
        CONSTRAINT ck_world_boss_milestone_source_authority
            CHECK (source_authority = '{SOURCE_AUTHORITY}'),
        CONSTRAINT ck_world_boss_milestone_event_type
            CHECK (source_event_type = '{SOURCE_EVENT_TYPE}'),
        CONSTRAINT ck_world_boss_milestone_contract_version
            CHECK (contract_version = '{CONTRACT_VERSION}'),
        PRIMARY KEY (user_id, settlement_id)
    )"""


def _create_index_sql(
    index_name: str,
    columns: tuple[str, ...],
    *,
    sqlite: bool,
) -> str:
    table = TABLE_NAME if sqlite else f"public.{TABLE_NAME}"
    return f"CREATE INDEX IF NOT EXISTS {index_name} ON {table} ({', '.join(columns)})"


def upgrade(conn: Any, *, dry_run: bool = False) -> dict[str, Any]:
    """Create and validate the additive schema; caller owns commit/rollback."""

    sqlite = _is_sqlite(conn)
    if not sqlite:
        _execute(conn, "SELECT pg_advisory_xact_lock(?)", (ADVISORY_LOCK_KEY,))
    before = validate_schema(conn)
    if dry_run:
        return {
            **before,
            "created": [],
            "planned_create": before["missing"],
            "dry_run": True,
        }
    if not before["present"]:
        _execute(conn, _create_sqlite_sql() if sqlite else _create_postgres_sql())
    for index_name, columns in INDEX_SPECS:
        _execute(
            conn,
            _create_index_sql(index_name, columns, sqlite=sqlite),
        )
    after = validate_schema(conn)
    if not after["valid"]:
        raise SchemaMismatch(f"{TABLE_NAME}: schema remains invalid")
    return {
        **after,
        "created": before["missing"],
        "planned_create": [],
        "dry_run": False,
    }


def downgrade_for_isolated_test(conn: Any) -> None:
    """Drop only F015's table in a disposable test database."""

    prefix = "" if _is_sqlite(conn) else "public."
    _execute(conn, f"DROP TABLE IF EXISTS {prefix}{TABLE_NAME}")


__all__ = [
    "ADVISORY_LOCK_KEY",
    "COLUMNS",
    "CONTRACT_VERSION",
    "DEDUPE_KEY",
    "INDEX_SPECS",
    "MigrationError",
    "SCHEMA_VERSION",
    "SOURCE_AUTHORITY",
    "SOURCE_EVENT_TYPE",
    "SchemaMismatch",
    "TABLE_NAME",
    "downgrade_for_isolated_test",
    "upgrade",
    "validate_schema",
]
