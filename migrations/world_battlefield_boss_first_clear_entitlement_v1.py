"""Additive F022 schema for Battlefield Boss first-clear entitlements.

This table is a business-correctness authority, not a settlement ledger and
not a World-progression projection.  It records the one lifetime dedicated
reward entitlement for a user and Zone.  F015 remains the authority that
records every consumed Battlefield Boss settlement fact.

The primary key is intentionally ``(user_id, zone_key)``.  The reward policy
version is immutable provenance for the entitlement; it is not part of the
uniqueness key, so changing a cosmetic mapping cannot silently create a
second lifetime first-clear reward.

The migration is a candidate only.  It never commits, never rolls back, and
is not called by application startup.  The caller owns the transaction and
must apply it only in an explicitly governed environment.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


SCHEMA_VERSION = "world_battlefield_boss_first_clear_entitlement_v1"
TABLE_NAME = "world_battlefield_boss_first_clear_entitlements"
ADVISORY_LOCK_KEY = 773310036
PRIMARY_KEY_COLUMNS = ("user_id", "zone_key")

SOURCE_AUTHORITY = "SERVER_MONSTER_SETTLEMENT"
SOURCE_EVENT_TYPE = "MONSTER_DEFEATED"
SOURCE_CONTRACT_VERSION = "BATTLEFIELD_BOSS_DEFEATED_FACT_V1"

INDEX_SPECS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "idx_world_boss_first_clear_source",
        ("user_id", "source_settlement_id"),
    ),
    (
        "idx_world_boss_first_clear_claimed_at",
        ("claimed_at",),
    ),
)


class MigrationError(RuntimeError):
    """Base class for explicit F022 schema failures."""


class SchemaMismatch(MigrationError):
    """An existing table does not satisfy the F022 contract."""


@dataclass(frozen=True)
class ColumnSpec:
    name: str
    postgres_type: str
    sqlite_type: str
    nullable: bool


COLUMNS = (
    ColumnSpec("user_id", "integer", "INTEGER", False),
    ColumnSpec("zone_key", "text", "TEXT", False),
    ColumnSpec("source_settlement_id", "text", "TEXT", False),
    ColumnSpec("source_encounter_operation_id", "text", "TEXT", False),
    ColumnSpec("source_monster_id", "text", "TEXT", False),
    ColumnSpec("eligibility_reference", "text", "TEXT", False),
    ColumnSpec("intent_replay_fingerprint", "text", "TEXT", False),
    ColumnSpec("source_authority", "text", "TEXT", False),
    ColumnSpec("source_event_type", "text", "TEXT", False),
    ColumnSpec("source_contract_version", "text", "TEXT", False),
    ColumnSpec("reward_item_id", "text", "TEXT", False),
    ColumnSpec("reward_policy_version", "text", "TEXT", False),
    ColumnSpec("claimed_at", "timestamp with time zone", "TEXT", False),
)

_CHECK_FRAGMENTS = (
    "USER_ID > 0",
    "SOURCE_AUTHORITY = 'SERVER_MONSTER_SETTLEMENT'",
    "SOURCE_EVENT_TYPE = 'MONSTER_DEFEATED'",
    "SOURCE_CONTRACT_VERSION = 'BATTLEFIELD_BOSS_DEFEATED_FACT_V1'",
)
_POSTGRES_CHECK_NAMES = (
    "ck_world_boss_first_clear_user_positive",
    "ck_world_boss_first_clear_source_authority",
    "ck_world_boss_first_clear_event_type",
    "ck_world_boss_first_clear_contract_version",
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


def _normalize_type(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


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
            for row in sorted(
                (row for row in rows if int(_row_value(row, 5, "pk")) > 0),
                key=lambda row: int(_row_value(row, 5, "pk")),
            )
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


def _check_constraints(conn: Any) -> None:
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
            WHERE conrelid = 'public.world_battlefield_boss_first_clear_entitlements'::regclass
              AND contype='c'""",
    )
    names = {str(_row_value(row, 0, "conname")) for row in rows}
    missing = sorted(set(_POSTGRES_CHECK_NAMES) - names)
    if missing:
        raise SchemaMismatch(f"{TABLE_NAME}: required checks missing {missing}")


def validate_schema(conn: Any) -> dict[str, Any]:
    """Validate the exact F022 table without changing the database."""

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
    if primary != PRIMARY_KEY_COLUMNS:
        raise SchemaMismatch(f"{TABLE_NAME}: primary key differs: {primary!r}")

    index_names = _index_names(conn)
    expected_indexes = {name for name, _columns in INDEX_SPECS}
    missing_indexes = sorted(expected_indexes - index_names)
    if missing_indexes:
        raise SchemaMismatch(f"{TABLE_NAME}: indexes missing {missing_indexes}")
    for index_name, columns in INDEX_SPECS:
        if _index_columns(conn, index_name) != columns:
            raise SchemaMismatch(f"{TABLE_NAME}: index {index_name} columns differ")
    _check_constraints(conn)
    return {
        "schema_version": SCHEMA_VERSION,
        "table": TABLE_NAME,
        "present": True,
        "valid": True,
        "missing": [],
        "columns": sorted(found),
        "indexes": sorted(expected_indexes),
        "primary_key": list(PRIMARY_KEY_COLUMNS),
    }


def _create_sqlite_sql() -> str:
    return f"""CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
        user_id INTEGER NOT NULL
            CONSTRAINT ck_world_boss_first_clear_user_positive CHECK (user_id > 0),
        zone_key TEXT NOT NULL CHECK (length(trim(zone_key)) > 0),
        source_settlement_id TEXT NOT NULL CHECK (length(trim(source_settlement_id)) > 0),
        source_encounter_operation_id TEXT NOT NULL
            CHECK (length(trim(source_encounter_operation_id)) > 0),
        source_monster_id TEXT NOT NULL CHECK (length(trim(source_monster_id)) > 0),
        eligibility_reference TEXT NOT NULL CHECK (length(trim(eligibility_reference)) > 0),
        intent_replay_fingerprint TEXT NOT NULL
            CHECK (length(trim(intent_replay_fingerprint)) > 0),
        source_authority TEXT NOT NULL
            CONSTRAINT ck_world_boss_first_clear_source_authority
            CHECK (source_authority = '{SOURCE_AUTHORITY}'),
        source_event_type TEXT NOT NULL
            CONSTRAINT ck_world_boss_first_clear_event_type
            CHECK (source_event_type = '{SOURCE_EVENT_TYPE}'),
        source_contract_version TEXT NOT NULL
            CONSTRAINT ck_world_boss_first_clear_contract_version
            CHECK (source_contract_version = '{SOURCE_CONTRACT_VERSION}'),
        reward_item_id TEXT NOT NULL CHECK (length(trim(reward_item_id)) > 0),
        reward_policy_version TEXT NOT NULL
            CHECK (length(trim(reward_policy_version)) > 0),
        claimed_at TEXT NOT NULL CHECK (length(trim(claimed_at)) > 0),
        PRIMARY KEY (user_id, zone_key)
    )"""


def _create_postgres_sql() -> str:
    return f"""CREATE TABLE IF NOT EXISTS public.{TABLE_NAME} (
        user_id INTEGER NOT NULL,
        zone_key TEXT NOT NULL,
        source_settlement_id TEXT NOT NULL,
        source_encounter_operation_id TEXT NOT NULL,
        source_monster_id TEXT NOT NULL,
        eligibility_reference TEXT NOT NULL,
        intent_replay_fingerprint TEXT NOT NULL,
        source_authority TEXT NOT NULL,
        source_event_type TEXT NOT NULL,
        source_contract_version TEXT NOT NULL,
        reward_item_id TEXT NOT NULL,
        reward_policy_version TEXT NOT NULL,
        claimed_at TIMESTAMPTZ NOT NULL,
        CONSTRAINT ck_world_boss_first_clear_user_positive CHECK (user_id > 0),
        CONSTRAINT ck_world_boss_first_clear_source_authority
            CHECK (source_authority = '{SOURCE_AUTHORITY}'),
        CONSTRAINT ck_world_boss_first_clear_event_type
            CHECK (source_event_type = '{SOURCE_EVENT_TYPE}'),
        CONSTRAINT ck_world_boss_first_clear_contract_version
            CHECK (source_contract_version = '{SOURCE_CONTRACT_VERSION}'),
        PRIMARY KEY (user_id, zone_key)
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
    """Create and validate the additive schema; caller owns the transaction."""

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
    """Drop only F022's table from a disposable test database."""

    prefix = "" if _is_sqlite(conn) else "public."
    _execute(conn, f"DROP TABLE IF EXISTS {prefix}{TABLE_NAME}")


__all__ = [
    "ADVISORY_LOCK_KEY",
    "COLUMNS",
    "INDEX_SPECS",
    "MigrationError",
    "PRIMARY_KEY_COLUMNS",
    "SCHEMA_VERSION",
    "SOURCE_AUTHORITY",
    "SOURCE_CONTRACT_VERSION",
    "SOURCE_EVENT_TYPE",
    "SchemaMismatch",
    "TABLE_NAME",
    "downgrade_for_isolated_test",
    "upgrade",
    "validate_schema",
]
