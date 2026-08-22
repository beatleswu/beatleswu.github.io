"""Additive durable identity for server-owned item-use operations.

The table in this migration is a business-correctness record, not an event
ledger.  It reserves one logical item-use request inside the caller's
transaction so a retry can replay the committed result without running the
inventory/effect mutation again.  D5A's outbox remains a separate evidence
surface and is never used as the item-use dedupe authority.

This module is a migration candidate only.  It never commits and it is not
invoked by application startup; an explicitly governed migration step must
apply it before the item-use route is enabled.
"""

from __future__ import annotations

from typing import Any


SCHEMA_VERSION = "item_use_operations_v1"
TABLE_NAME = "item_use_operations"
ADVISORY_LOCK_KEY = 773310024
OPERATION_FAMILY = "ITEM_USE"
OPERATION_STATUSES = (
    "PENDING",
    "SUCCESS",
    "REJECTED",
    "FAILED",
    "UNKNOWN",
    "UNVERIFIED",
)
PRIMARY_KEY_COLUMNS = ("player_id", "operation_family", "operation_id")
INDEX_SPECS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("idx_item_use_operations_player_created_at", ("player_id", "created_at")),
    ("idx_item_use_operations_player_item", ("player_id", "item_id")),
)


class MigrationError(RuntimeError):
    """Base class for a fail-closed schema candidate."""


class SchemaMismatch(MigrationError):
    """An existing table does not match the D5C contract."""


def _is_sqlite(conn: Any) -> bool:
    raw = getattr(conn, "_conn", conn)
    return raw.__class__.__module__.startswith("sqlite3")


def _value(row: Any, index: int, name: str) -> Any:
    try:
        return row[name]
    except (KeyError, TypeError, IndexError):
        return row[index]


def _normalize_type(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _sqlite_index_columns(conn: Any, index_name: str) -> tuple[str, ...]:
    rows = conn.execute(f"PRAGMA index_info({index_name})").fetchall()
    return tuple(str(_value(row, 2, "name")) for row in rows)


def _postgres_constraints(conn: Any) -> tuple[set[str], set[str]]:
    rows = conn.execute(
        """SELECT c.contype, c.conname, pg_get_constraintdef(c.oid)
             FROM pg_constraint c
             JOIN pg_class t ON t.oid = c.conrelid
             JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE n.nspname = 'public' AND t.relname = ?
            ORDER BY c.contype, c.oid""",
        (TABLE_NAME,),
    ).fetchall()
    primary: set[str] = set()
    checks: set[str] = set()
    import re

    for row in rows:
        kind = str(_value(row, 0, "contype"))
        definition = str(_value(row, 2, "pg_get_constraintdef"))
        if kind == "p":
            match = re.search(r"\(([^)]*)\)", definition)
            if match:
                primary.update(part.strip().strip('"') for part in match.group(1).split(","))
        elif kind == "c":
            checks.add(definition.upper())
    return primary, checks


def _validate_sqlite(conn: Any) -> dict[str, Any]:
    rows = conn.execute(f"PRAGMA table_info({TABLE_NAME})").fetchall()
    if not rows:
        return {
            "table": TABLE_NAME,
            "present": False,
            "missing": [TABLE_NAME],
            "columns": [],
            "indexes": [],
        }

    expected = {
        "operation_id": ("TEXT", False),
        "player_id": ("INTEGER", False),
        "operation_family": ("TEXT", False),
        "item_id": ("TEXT", False),
        "request_fingerprint": ("TEXT", False),
        "operation_status": ("TEXT", False),
        "result_payload": ("TEXT", False),
        "created_at": ("TEXT", False),
        "committed_at": ("TEXT", True),
    }
    actual_names = {str(_value(row, 1, "name")) for row in rows}
    if actual_names != set(expected):
        raise SchemaMismatch(
            f"{TABLE_NAME}: columns differ; unexpected="
            f"{sorted(actual_names - set(expected))}, "
            f"missing={sorted(set(expected) - actual_names)}"
        )
    for row in rows:
        name = str(_value(row, 1, "name"))
        observed_type = _normalize_type(_value(row, 2, "type"))
        nullable = not bool(_value(row, 3, "notnull"))
        expected_type, expected_nullable = expected[name]
        if observed_type != _normalize_type(expected_type) or nullable != expected_nullable:
            raise SchemaMismatch(
                f"{TABLE_NAME}.{name}: expected type={expected_type} "
                f"nullable={expected_nullable}; observed type={observed_type} "
                f"nullable={nullable}"
            )

    primary = {
        str(_value(row, 1, "name"))
        for row in rows
        if bool(_value(row, 5, "pk"))
    }
    if primary != set(PRIMARY_KEY_COLUMNS):
        raise SchemaMismatch(f"{TABLE_NAME}: primary key differs: {sorted(primary)}")

    index_names: set[str] = set()
    for row in conn.execute(f"PRAGMA index_list({TABLE_NAME})").fetchall():
        index_names.add(str(_value(row, 1, "name")))
    required_index_names = {name for name, _columns in INDEX_SPECS}
    missing_indexes = sorted(required_index_names - index_names)
    if missing_indexes:
        raise SchemaMismatch(f"{TABLE_NAME}: missing indexes {missing_indexes}")
    for index_name, columns in INDEX_SPECS:
        if _sqlite_index_columns(conn, index_name) != columns:
            raise SchemaMismatch(f"{TABLE_NAME}: index {index_name} has unexpected columns")

    return {
        "table": TABLE_NAME,
        "present": True,
        "missing": [],
        "columns": sorted(actual_names),
        "indexes": sorted(required_index_names),
    }


def _validate_postgres(conn: Any) -> dict[str, Any]:
    rows = conn.execute(
        """SELECT column_name, data_type, is_nullable
             FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = ?
            ORDER BY ordinal_position""",
        (TABLE_NAME,),
    ).fetchall()
    if not rows:
        return {
            "table": TABLE_NAME,
            "present": False,
            "missing": [TABLE_NAME],
            "columns": [],
            "indexes": [],
        }

    expected = {
        "operation_id": ("text", False),
        "player_id": ("integer", False),
        "operation_family": ("text", False),
        "item_id": ("text", False),
        "request_fingerprint": ("text", False),
        "operation_status": ("text", False),
        "result_payload": ("jsonb", False),
        "created_at": ("timestamp with time zone", False),
        "committed_at": ("timestamp with time zone", True),
    }
    found = {str(_value(row, 0, "column_name")): row for row in rows}
    if set(found) != set(expected):
        raise SchemaMismatch(
            f"{TABLE_NAME}: columns differ; unexpected="
            f"{sorted(set(found) - set(expected))}, "
            f"missing={sorted(set(expected) - set(found))}"
        )
    for name, (expected_type, expected_nullable) in expected.items():
        row = found[name]
        observed_type = _normalize_type(_value(row, 1, "data_type"))
        nullable = str(_value(row, 2, "is_nullable")).upper() == "YES"
        if observed_type != _normalize_type(expected_type) or nullable != expected_nullable:
            raise SchemaMismatch(
                f"{TABLE_NAME}.{name}: expected type={expected_type} "
                f"nullable={expected_nullable}; observed type={observed_type} "
                f"nullable={nullable}"
            )

    primary, checks = _postgres_constraints(conn)
    if primary != set(PRIMARY_KEY_COLUMNS):
        raise SchemaMismatch(f"{TABLE_NAME}: primary key differs: {sorted(primary)}")
    if not any("PENDING" in check and "SUCCESS" in check and "UNVERIFIED" in check for check in checks):
        raise SchemaMismatch(f"{TABLE_NAME}: operation status check constraint is missing")

    index_rows = conn.execute(
        """SELECT indexname, indexdef
             FROM pg_indexes
            WHERE schemaname = 'public' AND tablename = ?""",
        (TABLE_NAME,),
    ).fetchall()
    indexes = {
        str(_value(row, 0, "indexname")): _normalize_type(_value(row, 1, "indexdef"))
        for row in index_rows
    }
    for index_name, columns in INDEX_SPECS:
        definition = indexes.get(index_name)
        if not definition or not all(column in definition for column in columns):
            raise SchemaMismatch(f"{TABLE_NAME}: index {index_name} is missing or incorrect")
    return {
        "table": TABLE_NAME,
        "present": True,
        "missing": [],
        "columns": sorted(found),
        "indexes": sorted(name for name, _columns in INDEX_SPECS),
    }


def validate_schema(conn: Any) -> dict[str, Any]:
    result = _validate_sqlite(conn) if _is_sqlite(conn) else _validate_postgres(conn)
    return {**result, "schema_version": SCHEMA_VERSION}


def _create_sqlite_sql() -> str:
    statuses = ",".join(repr(value) for value in OPERATION_STATUSES)
    return f"""CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
        operation_id TEXT NOT NULL,
        player_id INTEGER NOT NULL,
        operation_family TEXT NOT NULL,
        item_id TEXT NOT NULL,
        request_fingerprint TEXT NOT NULL,
        operation_status TEXT NOT NULL CHECK (operation_status IN ({statuses})),
        result_payload TEXT NOT NULL,
        created_at TEXT NOT NULL,
        committed_at TEXT,
        PRIMARY KEY (player_id, operation_family, operation_id)
    )"""


def _create_postgres_sql() -> str:
    statuses = ",".join("'%s'" % value for value in OPERATION_STATUSES)
    return f"""CREATE TABLE IF NOT EXISTS public.{TABLE_NAME} (
        operation_id TEXT NOT NULL,
        player_id INTEGER NOT NULL,
        operation_family TEXT NOT NULL,
        item_id TEXT NOT NULL,
        request_fingerprint TEXT NOT NULL,
        operation_status TEXT NOT NULL CHECK (operation_status IN ({statuses})),
        result_payload JSONB NOT NULL,
        created_at TIMESTAMPTZ NOT NULL,
        committed_at TIMESTAMPTZ,
        CONSTRAINT pk_item_use_operations
          PRIMARY KEY (player_id, operation_family, operation_id)
    )"""


def _create_index_sql(index_name: str, columns: tuple[str, ...], *, sqlite: bool) -> str:
    table = TABLE_NAME if sqlite else f"public.{TABLE_NAME}"
    return f"CREATE INDEX IF NOT EXISTS {index_name} ON {table} ({', '.join(columns)})"


def upgrade(conn: Any, *, dry_run: bool = False) -> dict[str, Any]:
    """Create and validate the additive D5C schema; caller owns commit."""
    sqlite = _is_sqlite(conn)
    if not sqlite:
        conn.execute("SELECT pg_advisory_xact_lock(?)", (ADVISORY_LOCK_KEY,))
    before = validate_schema(conn)
    if dry_run:
        return {
            **before,
            "created": [],
            "planned_create": before["missing"],
            "dry_run": True,
        }
    if before["missing"]:
        conn.execute(_create_sqlite_sql() if sqlite else _create_postgres_sql())
    for index_name, columns in INDEX_SPECS:
        conn.execute(_create_index_sql(index_name, columns, sqlite=sqlite))
    after = validate_schema(conn)
    if after["missing"]:
        raise SchemaMismatch(f"item-use operation schema missing: {after['missing']}")
    return {
        **after,
        "created": before["missing"],
        "planned_create": [],
        "dry_run": False,
    }


def downgrade_for_isolated_test(conn: Any) -> None:
    """Drop only this D5C schema from a disposable test database."""
    if _is_sqlite(conn):
        conn.execute(f"DROP TABLE IF EXISTS {TABLE_NAME}")
    else:
        conn.execute(f"DROP TABLE IF EXISTS public.{TABLE_NAME}")


__all__ = [
    "ADVISORY_LOCK_KEY",
    "INDEX_SPECS",
    "MigrationError",
    "OPERATION_FAMILY",
    "OPERATION_STATUSES",
    "PRIMARY_KEY_COLUMNS",
    "SCHEMA_VERSION",
    "SchemaMismatch",
    "TABLE_NAME",
    "downgrade_for_isolated_test",
    "upgrade",
    "validate_schema",
]
