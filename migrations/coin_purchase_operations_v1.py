"""Additive C019 purchase-operation schema.

The table is the business-correctness authority for Coin purchases.  It binds
one authenticated user and purchase operation identity to the server-resolved
offer semantics and the committed result.  It is deliberately separate from
D5A's domain-event outbox, which remains acquisition evidence/lineage only.

This module is migration code only.  It never commits, never runs at request
time, and does not mutate a Production database by itself.  The caller owns
the surrounding transaction.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


SCHEMA_VERSION = "coin_purchase_operations_v1"
TABLE_NAME = "coin_purchase_operations"
ADVISORY_LOCK_KEY = 773310026
OPERATION_STATUSES = ("IN_PROGRESS", "COMMITTED")
PRIMARY_KEY_COLUMNS = ("user_id", "purchase_operation_id")
INDEX_SPECS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "idx_coin_purchase_operations_user_created_at",
        ("user_id", "created_at"),
    ),
    (
        "idx_coin_purchase_operations_user_offer",
        ("user_id", "offer_id"),
    ),
)


class MigrationError(RuntimeError):
    """Base class for fail-closed migration errors."""


class SchemaMismatch(MigrationError):
    """An existing table does not match the C019 contract."""


@dataclass(frozen=True)
class ColumnSpec:
    name: str
    postgres_type: str
    sqlite_type: str
    nullable: bool


COLUMNS = (
    ColumnSpec("user_id", "integer", "INTEGER", False),
    ColumnSpec("purchase_operation_id", "text", "TEXT", False),
    ColumnSpec("offer_id", "text", "TEXT", False),
    ColumnSpec("request_fingerprint", "text", "TEXT", False),
    ColumnSpec("offer_version", "text", "TEXT", False),
    ColumnSpec("currency_type", "text", "TEXT", False),
    ColumnSpec("resolved_price", "integer", "INTEGER", False),
    ColumnSpec("reward_id", "text", "TEXT", False),
    ColumnSpec("reward_quantity", "integer", "INTEGER", False),
    ColumnSpec("destination", "text", "TEXT", False),
    ColumnSpec("acquisition_class", "text", "TEXT", False),
    ColumnSpec("operation_status", "text", "TEXT", False),
    ColumnSpec("result_payload", "jsonb", "TEXT", False),
    ColumnSpec("lineage_event_id", "text", "TEXT", True),
    ColumnSpec("created_at", "timestamp with time zone", "TEXT", False),
    ColumnSpec("updated_at", "timestamp with time zone", "TEXT", False),
    ColumnSpec("committed_at", "timestamp with time zone", "TEXT", True),
)


def _is_sqlite(conn: Any) -> bool:
    raw = getattr(conn, "_conn", conn)
    return raw.__class__.__module__.startswith("sqlite3")


def _row_value(row: Any, index: int, name: str) -> Any:
    try:
        return row[name]
    except (KeyError, TypeError, IndexError):
        return row[index]


def _normalize_type(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _sqlite_index_columns(conn: Any, index_name: str) -> tuple[str, ...]:
    rows = conn.execute(f"PRAGMA index_info({index_name})").fetchall()
    return tuple(str(_row_value(row, 2, "name")) for row in rows)


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
        kind = str(_row_value(row, 0, "contype"))
        definition = str(_row_value(row, 2, "pg_get_constraintdef"))
        if kind == "p":
            match = re.search(r"\(([^)]*)\)", definition)
            if match:
                primary.update(
                    part.strip().strip('"') for part in match.group(1).split(",")
                )
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

    expected = {spec.name: spec for spec in COLUMNS}
    actual_names = {str(_row_value(row, 1, "name")) for row in rows}
    if actual_names != set(expected):
        raise SchemaMismatch(
            f"{TABLE_NAME}: columns differ; unexpected="
            f"{sorted(actual_names - set(expected))}, "
            f"missing={sorted(set(expected) - actual_names)}"
        )
    for row in rows:
        name = str(_row_value(row, 1, "name"))
        observed_type = _normalize_type(_row_value(row, 2, "type"))
        nullable = not bool(_row_value(row, 3, "notnull"))
        spec = expected[name]
        if (
            observed_type != _normalize_type(spec.sqlite_type)
            or nullable != spec.nullable
        ):
            raise SchemaMismatch(
                f"{TABLE_NAME}.{name}: expected type={spec.sqlite_type} "
                f"nullable={spec.nullable}; observed type={observed_type} "
                f"nullable={nullable}"
            )

    primary = {
        str(_row_value(row, 1, "name"))
        for row in rows
        if bool(_row_value(row, 5, "pk"))
    }
    if primary != set(PRIMARY_KEY_COLUMNS):
        raise SchemaMismatch(f"{TABLE_NAME}: primary key differs: {sorted(primary)}")

    index_names = {
        str(_row_value(row, 1, "name"))
        for row in conn.execute(f"PRAGMA index_list({TABLE_NAME})").fetchall()
    }
    required_index_names = {name for name, _columns in INDEX_SPECS}
    missing_indexes = sorted(required_index_names - index_names)
    if missing_indexes:
        raise SchemaMismatch(f"{TABLE_NAME}: missing indexes {missing_indexes}")
    for index_name, columns in INDEX_SPECS:
        if _sqlite_index_columns(conn, index_name) != columns:
            raise SchemaMismatch(
                f"{TABLE_NAME}: index {index_name} has unexpected columns"
            )

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

    expected = {spec.name: spec for spec in COLUMNS}
    found = {str(_row_value(row, 0, "column_name")): row for row in rows}
    if set(found) != set(expected):
        raise SchemaMismatch(
            f"{TABLE_NAME}: columns differ; unexpected="
            f"{sorted(set(found) - set(expected))}, "
            f"missing={sorted(set(expected) - set(found))}"
        )
    for name, spec in expected.items():
        row = found[name]
        observed_type = _normalize_type(_row_value(row, 1, "data_type"))
        nullable = str(_row_value(row, 2, "is_nullable")).upper() == "YES"
        if (
            observed_type != _normalize_type(spec.postgres_type)
            or nullable != spec.nullable
        ):
            raise SchemaMismatch(
                f"{TABLE_NAME}.{name}: expected type={spec.postgres_type} "
                f"nullable={spec.nullable}; observed type={observed_type} "
                f"nullable={nullable}"
            )

    primary, checks = _postgres_constraints(conn)
    if primary != set(PRIMARY_KEY_COLUMNS):
        raise SchemaMismatch(f"{TABLE_NAME}: primary key differs: {sorted(primary)}")
    if not any(
        "IN_PROGRESS" in check
        and "COMMITTED" in check
        and "OPERATION_STATUS" in check
        for check in checks
    ):
        raise SchemaMismatch(f"{TABLE_NAME}: operation status check is missing")
    if not any("RESOLVED_PRICE" in check and "> 0" in check for check in checks):
        raise SchemaMismatch(f"{TABLE_NAME}: resolved-price check is missing")
    if not any("REWARD_QUANTITY" in check and "> 0" in check for check in checks):
        raise SchemaMismatch(f"{TABLE_NAME}: reward-quantity check is missing")

    index_rows = conn.execute(
        """SELECT indexname, indexdef
             FROM pg_indexes
            WHERE schemaname = 'public' AND tablename = ?""",
        (TABLE_NAME,),
    ).fetchall()
    indexes = {
        str(_row_value(row, 0, "indexname")): _normalize_type(
            _row_value(row, 1, "indexdef")
        )
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
        purchase_operation_id TEXT NOT NULL,
        offer_id TEXT NOT NULL,
        request_fingerprint TEXT NOT NULL,
        offer_version TEXT NOT NULL,
        currency_type TEXT NOT NULL,
        resolved_price INTEGER NOT NULL CHECK (resolved_price > 0),
        reward_id TEXT NOT NULL,
        reward_quantity INTEGER NOT NULL CHECK (reward_quantity > 0),
        destination TEXT NOT NULL,
        acquisition_class TEXT NOT NULL,
        operation_status TEXT NOT NULL CHECK (operation_status IN ({statuses})),
        result_payload TEXT NOT NULL DEFAULT '{{}}',
        lineage_event_id TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        committed_at TEXT,
        PRIMARY KEY (user_id, purchase_operation_id)
    )"""


def _create_postgres_sql() -> str:
    statuses = ",".join("'%s'" % value for value in OPERATION_STATUSES)
    return f"""CREATE TABLE IF NOT EXISTS public.{TABLE_NAME} (
        user_id INTEGER NOT NULL,
        purchase_operation_id TEXT NOT NULL,
        offer_id TEXT NOT NULL,
        request_fingerprint TEXT NOT NULL,
        offer_version TEXT NOT NULL,
        currency_type TEXT NOT NULL,
        resolved_price INTEGER NOT NULL CHECK (resolved_price > 0),
        reward_id TEXT NOT NULL,
        reward_quantity INTEGER NOT NULL CHECK (reward_quantity > 0),
        destination TEXT NOT NULL,
        acquisition_class TEXT NOT NULL,
        operation_status TEXT NOT NULL CHECK (operation_status IN ({statuses})),
        result_payload JSONB NOT NULL DEFAULT '{{}}'::jsonb,
        lineage_event_id TEXT,
        created_at TIMESTAMPTZ NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL,
        committed_at TIMESTAMPTZ,
        CONSTRAINT pk_coin_purchase_operations
          PRIMARY KEY (user_id, purchase_operation_id)
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
    """Create and validate C019 schema; the caller owns commit/rollback."""

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
        raise SchemaMismatch(f"purchase operation schema missing: {after['missing']}")
    return {
        **after,
        "created": before["missing"],
        "planned_create": [],
        "dry_run": False,
    }


def downgrade_for_isolated_test(conn: Any) -> None:
    """Drop only the C019 table from a disposable test database."""

    if _is_sqlite(conn):
        conn.execute(f"DROP TABLE IF EXISTS {TABLE_NAME}")
    else:
        conn.execute(f"DROP TABLE IF EXISTS public.{TABLE_NAME}")


__all__ = [
    "ADVISORY_LOCK_KEY",
    "COLUMNS",
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
