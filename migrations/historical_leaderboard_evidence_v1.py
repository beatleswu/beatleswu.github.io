"""Additive sink for server-created historical leaderboard evidence.

This migration is deliberately separate from ``review_log``.  Historical
reconciliation rows are not public SRS submissions and must never be made to
look like ``mbv1:``, ``daily_d5b:v1:`` or ``rt:`` evidence.  The table has no
HTTP writer; the controlled reconciliation runner is its only writer.

The migration never commits.  A governed caller owns the surrounding
transaction, just like the other repository migrations.
"""

from __future__ import annotations

import re
from typing import Any


SCHEMA_VERSION = "historical_leaderboard_evidence_v1"
TABLE_NAME = "historical_leaderboard_evidence"
SOURCE_PREFIX = "historical_leaderboard_reconciliation:v1:"
EVENT_TYPE = "LEADERBOARD_HISTORICAL_EVIDENCE"
ADVISORY_LOCK_KEY = 773310026

INDEX_SPECS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "idx_hle_period_user_question",
        ("period_key", "user_id", "question_id"),
    ),
    (
        "idx_hle_user_event_timestamp",
        ("user_id", "event_timestamp"),
    ),
)

EXPECTED_COLUMNS = {
    "canonical_idempotency_key": ("TEXT", False),
    "user_id": ("INTEGER", False),
    "question_id": ("INTEGER", False),
    "source_prefix": ("TEXT", False),
    "canonical_source": ("TEXT", False),
    "legacy_event_id": ("TEXT", False),
    "legacy_source": ("TEXT", False),
    "event_timestamp": ("TEXT", False),
    "score": ("INTEGER", False),
    "period_key": ("TEXT", False),
    "period_start_at": ("TEXT", False),
    "period_end_at": ("TEXT", False),
    "policy_version": ("TEXT", False),
    "reconciliation_class": ("TEXT", False),
    "evidence_json": ("TEXT", False),
    "created_at": ("TEXT", False),
}


class MigrationError(RuntimeError):
    """Base class for fail-closed migration/schema errors."""


class SchemaMismatch(MigrationError):
    """An existing table does not match the v1 evidence contract."""


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


def _column_rows(conn: Any) -> list[Any]:
    if _is_sqlite(conn):
        return conn.execute(f"PRAGMA table_info({TABLE_NAME})").fetchall()
    return conn.execute(
        """SELECT column_name, data_type, is_nullable
             FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = ?
            ORDER BY ordinal_position""",
        (TABLE_NAME,),
    ).fetchall()


def _postgres_primary_columns(conn: Any) -> set[str]:
    rows = conn.execute(
        """SELECT pg_get_constraintdef(c.oid)
             FROM pg_constraint c
             JOIN pg_class t ON t.oid = c.conrelid
             JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE n.nspname = 'public' AND t.relname = ?
              AND c.contype = 'p'""",
        (TABLE_NAME,),
    ).fetchall()
    result: set[str] = set()
    for row in rows:
        definition = str(_value(row, 0, "pg_get_constraintdef"))
        match = re.search(r"\(([^)]*)\)", definition)
        if match:
            result.update(part.strip().strip('"') for part in match.group(1).split(","))
    return result


def _postgres_constraints(conn: Any) -> tuple[set[str], set[tuple[str, ...]], set[str]]:
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
    unique: set[tuple[str, ...]] = set()
    checks: set[str] = set()
    for row in rows:
        kind = str(_value(row, 0, "contype"))
        definition = str(_value(row, 2, "pg_get_constraintdef"))
        match = re.search(r"\(([^)]*)\)", definition)
        columns = (
            tuple(part.strip().strip('"') for part in match.group(1).split(","))
            if match
            else ()
        )
        if kind == "p":
            primary.update(columns)
        elif kind == "u":
            unique.add(columns)
        elif kind == "c":
            checks.add(definition.upper())
    return primary, unique, checks


def _validate_indexes(conn: Any) -> list[str]:
    if _is_sqlite(conn):
        index_names = {
            str(_value(row, 1, "name"))
            for row in conn.execute(f"PRAGMA index_list({TABLE_NAME})").fetchall()
        }
        for index_name, columns in INDEX_SPECS:
            if index_name not in index_names:
                raise SchemaMismatch(f"{TABLE_NAME}: missing index {index_name}")
            if _sqlite_index_columns(conn, index_name) != columns:
                raise SchemaMismatch(f"{TABLE_NAME}: index {index_name} has unexpected columns")
        return sorted(index_names)

    rows = conn.execute(
        """SELECT indexname, indexdef
             FROM pg_indexes
            WHERE schemaname = 'public' AND tablename = ?""",
        (TABLE_NAME,),
    ).fetchall()
    definitions = {
        str(_value(row, 0, "indexname")): _normalize_type(_value(row, 1, "indexdef"))
        for row in rows
    }
    for index_name, columns in INDEX_SPECS:
        definition = definitions.get(index_name)
        if not definition or not all(column in definition for column in columns):
            raise SchemaMismatch(f"{TABLE_NAME}: missing or incorrect index {index_name}")
    return sorted(definitions)


def validate_schema(conn: Any) -> dict[str, Any]:
    rows = _column_rows(conn)
    if not rows:
        return {
            "schema_version": SCHEMA_VERSION,
            "table": TABLE_NAME,
            "present": False,
            "missing": [TABLE_NAME],
            "columns": [],
            "indexes": [],
        }

    if _is_sqlite(conn):
        found = {
            str(_value(row, 1, "name")): row
            for row in rows
        }
        primary = {
            name for name, row in found.items() if bool(_value(row, 5, "pk"))
        }
        for name, (expected_type, expected_nullable) in EXPECTED_COLUMNS.items():
            row = found.get(name)
            if row is None:
                raise SchemaMismatch(f"{TABLE_NAME}: missing column {name}")
            observed_type = _normalize_type(_value(row, 2, "type"))
            nullable = not bool(_value(row, 3, "notnull"))
            if observed_type != _normalize_type(expected_type) or nullable != expected_nullable:
                raise SchemaMismatch(
                    f"{TABLE_NAME}.{name}: expected type={expected_type}, "
                    f"nullable={expected_nullable}; observed type={observed_type}, "
                    f"nullable={nullable}"
                )
        if set(found) != set(EXPECTED_COLUMNS):
            raise SchemaMismatch(
                f"{TABLE_NAME}: unexpected columns {sorted(set(found) - set(EXPECTED_COLUMNS))}"
            )
        if primary != {"canonical_idempotency_key"}:
            raise SchemaMismatch(f"{TABLE_NAME}: primary key differs: {sorted(primary)}")
        unique_sets = {
            _sqlite_index_columns(conn, str(_value(row, 1, "name")))
            for row in conn.execute(f"PRAGMA index_list({TABLE_NAME})").fetchall()
            if bool(_value(row, 2, "unique"))
        }
        if ("period_key", "user_id", "question_id") not in unique_sets:
            raise SchemaMismatch(f"{TABLE_NAME}: required uniqueness is missing")
    else:
        expected_pg = {
            name: (
                "jsonb"
                if name == "evidence_json"
                else "text" if expected_type == "TEXT" else "integer",
                nullable,
            )
            for name, (expected_type, nullable) in EXPECTED_COLUMNS.items()
        }
        found = {
            str(_value(row, 0, "column_name")): row
            for row in rows
        }
        if set(found) != set(expected_pg):
            raise SchemaMismatch(
                f"{TABLE_NAME}: columns differ; unexpected="
                f"{sorted(set(found) - set(expected_pg))}, "
                f"missing={sorted(set(expected_pg) - set(found))}"
            )
        for name, (expected_type, expected_nullable) in expected_pg.items():
            row = found[name]
            observed_type = _normalize_type(_value(row, 1, "data_type"))
            nullable = str(_value(row, 2, "is_nullable")).upper() == "YES"
            if observed_type != _normalize_type(expected_type) or nullable != expected_nullable:
                raise SchemaMismatch(
                    f"{TABLE_NAME}.{name}: expected type={expected_type}, "
                    f"nullable={expected_nullable}; observed type={observed_type}, "
                    f"nullable={nullable}"
                )
        primary, unique, checks = _postgres_constraints(conn)
        if primary != {"canonical_idempotency_key"}:
            raise SchemaMismatch(f"{TABLE_NAME}: primary key differs")
        if ("period_key", "user_id", "question_id") not in unique:
            raise SchemaMismatch(f"{TABLE_NAME}: required uniqueness is missing")
        if not any("SOURCE_PREFIX" in check and SOURCE_PREFIX.upper() in check for check in checks):
            raise SchemaMismatch(f"{TABLE_NAME}: source-prefix check constraint is missing")
        if not any("SCORE" in check and "= 1" in check for check in checks):
            raise SchemaMismatch(f"{TABLE_NAME}: score check constraint is missing")
        if not any("CANONICAL_SOURCE" in check and "SOURCE_PREFIX" in check for check in checks):
            raise SchemaMismatch(f"{TABLE_NAME}: canonical-source check constraint is missing")

    indexes = _validate_indexes(conn)
    return {
        "schema_version": SCHEMA_VERSION,
        "table": TABLE_NAME,
        "present": True,
        "missing": [],
        "columns": sorted(EXPECTED_COLUMNS),
        "indexes": indexes,
    }


def _create_sqlite_sql() -> str:
    return f"""CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
        canonical_idempotency_key TEXT PRIMARY KEY NOT NULL,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        question_id INTEGER NOT NULL,
        source_prefix TEXT NOT NULL CHECK (source_prefix = '{SOURCE_PREFIX}'),
        canonical_source TEXT NOT NULL,
        legacy_event_id TEXT NOT NULL,
        legacy_source TEXT NOT NULL,
        event_timestamp TEXT NOT NULL,
        score INTEGER NOT NULL CHECK (score = 1),
        period_key TEXT NOT NULL,
        period_start_at TEXT NOT NULL,
        period_end_at TEXT NOT NULL,
        policy_version TEXT NOT NULL,
        reconciliation_class TEXT NOT NULL,
        evidence_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(period_key, user_id, question_id),
        CHECK (canonical_source = source_prefix || canonical_idempotency_key)
    )"""


def _create_postgres_sql() -> str:
    return f"""CREATE TABLE IF NOT EXISTS public.{TABLE_NAME} (
        canonical_idempotency_key TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
        question_id INTEGER NOT NULL,
        source_prefix TEXT NOT NULL CHECK (source_prefix = '{SOURCE_PREFIX}'),
        canonical_source TEXT NOT NULL,
        legacy_event_id TEXT NOT NULL,
        legacy_source TEXT NOT NULL,
        event_timestamp TEXT NOT NULL,
        score INTEGER NOT NULL CHECK (score = 1),
        period_key TEXT NOT NULL,
        period_start_at TEXT NOT NULL,
        period_end_at TEXT NOT NULL,
        policy_version TEXT NOT NULL,
        reconciliation_class TEXT NOT NULL,
        evidence_json JSONB NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(period_key, user_id, question_id),
        CHECK (canonical_source = source_prefix || canonical_idempotency_key)
    )"""


def _create_index_sql(index_name: str, columns: tuple[str, ...], *, sqlite: bool) -> str:
    table = TABLE_NAME if sqlite else f"public.{TABLE_NAME}"
    return f"CREATE INDEX IF NOT EXISTS {index_name} ON {table} ({', '.join(columns)})"


def upgrade(conn: Any, *, dry_run: bool = False) -> dict[str, Any]:
    """Create and validate the additive schema; caller owns commit."""

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
        raise SchemaMismatch(f"{TABLE_NAME}: schema missing after upgrade")
    return {
        **after,
        "created": before["missing"],
        "planned_create": [],
        "dry_run": False,
    }


def downgrade_for_isolated_test(conn: Any) -> None:
    """Drop only this table in a disposable fixture."""

    table = TABLE_NAME if _is_sqlite(conn) else f"public.{TABLE_NAME}"
    conn.execute(f"DROP TABLE IF EXISTS {table}")


__all__ = [
    "ADVISORY_LOCK_KEY",
    "EVENT_TYPE",
    "EXPECTED_COLUMNS",
    "INDEX_SPECS",
    "MigrationError",
    "SCHEMA_VERSION",
    "SOURCE_PREFIX",
    "SchemaMismatch",
    "TABLE_NAME",
    "downgrade_for_isolated_test",
    "upgrade",
    "validate_schema",
]
