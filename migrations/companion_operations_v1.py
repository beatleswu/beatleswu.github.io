"""Additive durable operation authority for Companion mutations.

This migration owns the business-correctness record for the five canonical
Companion operations.  It is intentionally separate from D5A's event outbox
and D5C's item-use operation table.  The migration never commits; the
governed release step owns when it is applied.
"""

from __future__ import annotations

from typing import Any


SCHEMA_VERSION = "companion_operations_v1"
TABLE_NAME = "companion_operations"
ADVISORY_LOCK_KEY = 773310025
OPERATION_STATUSES = ("PENDING", "COMPLETED", "FAILED")
PRIMARY_KEY_COLUMNS = ("user_id", "operation_id")
INDEX_SPECS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("idx_companion_operations_user_created_at", ("user_id", "created_at")),
    ("idx_companion_operations_user_type", ("user_id", "operation_type")),
)


class MigrationError(RuntimeError):
    """Base class for fail-closed migration/schema errors."""


class SchemaMismatch(MigrationError):
    """An existing table does not match the B023 contract."""


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
    import re

    primary: set[str] = set()
    checks: set[str] = set()
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


EXPECTED_COLUMNS = {
    "user_id": ("INTEGER", False),
    "operation_id": ("TEXT", False),
    "operation_type": ("TEXT", False),
    "spirit_id": ("TEXT", True),
    "payload_hash": ("TEXT", False),
    "status": ("TEXT", False),
    "result_json": ("TEXT", False),
    "error_code": ("TEXT", True),
    "policy_version": ("TEXT", False),
    "created_at": ("TEXT", False),
    "updated_at": ("TEXT", False),
    "completed_at": ("TEXT", True),
}


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

    actual_names = {str(_value(row, 1, "name")) for row in rows}
    if actual_names != set(EXPECTED_COLUMNS):
        raise SchemaMismatch(
            f"{TABLE_NAME}: columns differ; unexpected="
            f"{sorted(actual_names - set(EXPECTED_COLUMNS))}, "
            f"missing={sorted(set(EXPECTED_COLUMNS) - actual_names)}"
        )
    for row in rows:
        name = str(_value(row, 1, "name"))
        observed_type = _normalize_type(_value(row, 2, "type"))
        nullable = not bool(_value(row, 3, "notnull"))
        expected_type, expected_nullable = EXPECTED_COLUMNS[name]
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

    index_names = {
        str(_value(row, 1, "name"))
        for row in conn.execute(f"PRAGMA index_list({TABLE_NAME})").fetchall()
    }
    required = {name for name, _columns in INDEX_SPECS}
    missing_indexes = sorted(required - index_names)
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
        "indexes": sorted(required),
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
        **EXPECTED_COLUMNS,
        "user_id": ("integer", False),
        "operation_id": ("text", False),
        "operation_type": ("text", False),
        "spirit_id": ("text", True),
        "payload_hash": ("text", False),
        "status": ("text", False),
        "result_json": ("jsonb", False),
        "error_code": ("text", True),
        "policy_version": ("text", False),
        "created_at": ("timestamp with time zone", False),
        "updated_at": ("timestamp with time zone", False),
        "completed_at": ("timestamp with time zone", True),
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
    if not any("PENDING" in check and "COMPLETED" in check and "FAILED" in check for check in checks):
        raise SchemaMismatch(f"{TABLE_NAME}: status check constraint is missing")
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
        user_id INTEGER NOT NULL,
        operation_id TEXT NOT NULL,
        operation_type TEXT NOT NULL,
        spirit_id TEXT,
        payload_hash TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ({statuses})),
        result_json TEXT NOT NULL DEFAULT '{{}}',
        error_code TEXT,
        policy_version TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        completed_at TEXT,
        PRIMARY KEY (user_id, operation_id)
    )"""


def _create_postgres_sql() -> str:
    statuses = ",".join("'%s'" % value for value in OPERATION_STATUSES)
    return f"""CREATE TABLE IF NOT EXISTS public.{TABLE_NAME} (
        user_id INTEGER NOT NULL,
        operation_id TEXT NOT NULL,
        operation_type TEXT NOT NULL,
        spirit_id TEXT,
        payload_hash TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ({statuses})),
        result_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
        error_code TEXT,
        policy_version TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL,
        completed_at TIMESTAMPTZ,
        CONSTRAINT pk_companion_operations
          PRIMARY KEY (user_id, operation_id)
    )"""


def _create_index_sql(index_name: str, columns: tuple[str, ...], *, sqlite: bool) -> str:
    table = TABLE_NAME if sqlite else f"public.{TABLE_NAME}"
    return f"CREATE INDEX IF NOT EXISTS {index_name} ON {table} ({', '.join(columns)})"


def upgrade(conn: Any, *, dry_run: bool = False) -> dict[str, Any]:
    """Create and validate the additive B023 schema; caller owns commit."""

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
        raise SchemaMismatch(f"companion operation schema missing: {after['missing']}")
    return {
        **after,
        "created": before["missing"],
        "planned_create": [],
        "dry_run": False,
    }


def downgrade_for_isolated_test(conn: Any) -> None:
    if _is_sqlite(conn):
        conn.execute(f"DROP TABLE IF EXISTS {TABLE_NAME}")
    else:
        conn.execute(f"DROP TABLE IF EXISTS public.{TABLE_NAME}")


__all__ = [
    "ADVISORY_LOCK_KEY",
    "INDEX_SPECS",
    "MigrationError",
    "OPERATION_STATUSES",
    "PRIMARY_KEY_COLUMNS",
    "SCHEMA_VERSION",
    "SchemaMismatch",
    "TABLE_NAME",
    "downgrade_for_isolated_test",
    "upgrade",
    "validate_schema",
]
