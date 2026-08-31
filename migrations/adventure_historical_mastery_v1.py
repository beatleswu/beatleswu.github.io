"""Additive schema for Incident 019B's one-time Adventure compatibility baseline.

The schema is deliberately separate from ``review_log`` and ``srs_cards``.
Those source tables remain authoritative for their own domains and are never
rewritten by this migration.  A controlled baseline runner captures the
historical visible-product set once, then the Adventure read path unions that
immutable membership with the current trusted review evidence.

This module never commits.  The caller owns the transaction, which lets the
future migration/backfill runner capture the membership set and freeze its
metadata atomically.
"""

from __future__ import annotations

import re
from typing import Any


SCHEMA_VERSION = "incident019b_adventure_historical_mastery_v1"
BASELINE_VERSION = "INCIDENT019B_B050_COMPAT_V1"
TABLE_NAME = "adventure_historical_mastery"
BASELINE_TABLE_NAME = "adventure_historical_mastery_baseline"
ADVISORY_LOCK_KEY = 773310031

STATUS_CAPTURING = "CAPTURING"
STATUS_FROZEN = "FROZEN"
SOURCE_REVIEW_MASK = 1
SOURCE_CARD_MASK = 2
SOURCE_BOTH_MASK = SOURCE_REVIEW_MASK | SOURCE_CARD_MASK
CUTOFF_LITERAL = "2026-08-29T13:17:30"

INDEX_SPECS: tuple[tuple[str, str, str], ...] = (
    (
        "idx_adventure_historical_mastery_user_version",
        TABLE_NAME,
        "user_id, baseline_version",
    ),
    (
        "idx_adventure_historical_mastery_version_question",
        TABLE_NAME,
        "baseline_version, question_id",
    ),
)


class MigrationError(RuntimeError):
    """Base class for fail-closed schema errors."""


class SchemaMismatch(MigrationError):
    """An existing compatibility schema does not match this contract."""


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


def _table_prefix(conn: Any) -> str:
    return "" if _is_sqlite(conn) else "public."


def _table_exists(conn: Any, table_name: str) -> bool:
    if _is_sqlite(conn):
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone()
    else:
        row = conn.execute(
            """SELECT 1 FROM information_schema.tables
                WHERE table_schema='public' AND table_name=?""",
            (table_name,),
        ).fetchone()
    return row is not None


def _columns(conn: Any, table_name: str) -> dict[str, tuple[str, bool]]:
    if _is_sqlite(conn):
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        return {
            str(_value(row, 1, "name")): (
                _normalize_type(_value(row, 2, "type")),
                not bool(_value(row, 3, "notnull")),
            )
            for row in rows
        }
    rows = conn.execute(
        """SELECT column_name, data_type, is_nullable
             FROM information_schema.columns
            WHERE table_schema='public' AND table_name=?
            ORDER BY ordinal_position""",
        (table_name,),
    ).fetchall()
    return {
        str(_value(row, 0, "column_name")): (
            _normalize_type(_value(row, 1, "data_type")),
            str(_value(row, 2, "is_nullable")).upper() == "YES",
        )
        for row in rows
    }


def _sqlite_index_columns(conn: Any, index_name: str) -> tuple[str, ...]:
    rows = conn.execute(f"PRAGMA index_info({index_name})").fetchall()
    return tuple(str(_value(row, 2, "name")) for row in rows)


def _index_names_and_columns(conn: Any, table_name: str) -> dict[str, tuple[str, ...]]:
    if _is_sqlite(conn):
        rows = conn.execute(f"PRAGMA index_list({table_name})").fetchall()
        return {
            str(_value(row, 1, "name")): _sqlite_index_columns(
                conn, str(_value(row, 1, "name"))
            )
            for row in rows
        }
    rows = conn.execute(
        """SELECT indexname, indexdef
             FROM pg_indexes
            WHERE schemaname='public' AND tablename=?""",
        (table_name,),
    ).fetchall()
    result: dict[str, tuple[str, ...]] = {}
    for row in rows:
        name = str(_value(row, 0, "indexname"))
        definition = str(_value(row, 1, "indexdef"))
        match = re.search(r"\(([^)]*)\)", definition)
        result[name] = (
            tuple(part.strip().strip('"') for part in match.group(1).split(","))
            if match
            else ()
        )
    return result


def _primary_columns(conn: Any, table_name: str) -> set[str]:
    if _is_sqlite(conn):
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        return {
            str(_value(row, 1, "name"))
            for row in rows
            if bool(_value(row, 5, "pk"))
        }
    rows = conn.execute(
        """SELECT pg_get_constraintdef(c.oid)
             FROM pg_constraint c
             JOIN pg_class t ON t.oid=c.conrelid
             JOIN pg_namespace n ON n.oid=t.relnamespace
            WHERE n.nspname='public' AND t.relname=? AND c.contype='p'""",
        (table_name,),
    ).fetchall()
    result: set[str] = set()
    for row in rows:
        match = re.search(r"\(([^)]*)\)", str(_value(row, 0, "pg_get_constraintdef")))
        if match:
            result.update(part.strip().strip('"') for part in match.group(1).split(","))
    return result


EXPECTED_BASELINE_COLUMNS = {
    "baseline_version": ("text", False),
    "cutoff_literal": ("text", False),
    "captured_at": ("text", False),
    "frozen_at": ("text", False),
    "status": ("text", False),
    "membership_count": ("integer", False),
}

EXPECTED_MEMBERSHIP_COLUMNS = {
    "user_id": ("integer", False),
    "question_id": ("integer", False),
    "baseline_version": ("text", False),
    "source_mask": ("integer", False),
    "entitlement_source": ("text", False),
    "captured_at": ("text", False),
    "cutoff_literal": ("text", False),
}


def _validate_columns(conn: Any, table_name: str, expected: dict[str, tuple[str, bool]]) -> None:
    found = _columns(conn, table_name)
    if set(found) != set(expected):
        raise SchemaMismatch(
            f"{table_name}: columns differ; unexpected={sorted(set(found)-set(expected))}, "
            f"missing={sorted(set(expected)-set(found))}"
        )
    for name, (expected_type, expected_nullable) in expected.items():
        observed_type, observed_nullable = found[name]
        if observed_type != expected_type or observed_nullable != expected_nullable:
            raise SchemaMismatch(
                f"{table_name}.{name}: expected type={expected_type}, "
                f"nullable={expected_nullable}; observed type={observed_type}, "
                f"nullable={observed_nullable}"
            )


def validate_schema(conn: Any) -> dict[str, Any]:
    tables = (BASELINE_TABLE_NAME, TABLE_NAME)
    missing_tables = [table for table in tables if not _table_exists(conn, table)]
    if missing_tables:
        return {
            "schema_version": SCHEMA_VERSION,
            "baseline_version": BASELINE_VERSION,
            "valid": False,
            "missing_tables": missing_tables,
            "indexes": [],
        }

    _validate_columns(conn, BASELINE_TABLE_NAME, EXPECTED_BASELINE_COLUMNS)
    _validate_columns(conn, TABLE_NAME, EXPECTED_MEMBERSHIP_COLUMNS)
    if _primary_columns(conn, BASELINE_TABLE_NAME) != {"baseline_version"}:
        raise SchemaMismatch(f"{BASELINE_TABLE_NAME}: primary key differs")
    if _primary_columns(conn, TABLE_NAME) != {
        "user_id",
        "question_id",
        "baseline_version",
    }:
        raise SchemaMismatch(f"{TABLE_NAME}: primary key differs")

    indexes: list[str] = []
    for name, table_name, columns in INDEX_SPECS:
        found_indexes = _index_names_and_columns(conn, table_name)
        if name in found_indexes:
            observed = found_indexes[name]
            if observed != tuple(part.strip() for part in columns.split(",")):
                raise SchemaMismatch(f"{name}: index columns differ")
            indexes.append(name)
    if set(indexes) != {name for name, _table_name, _columns in INDEX_SPECS}:
        raise SchemaMismatch(
            f"compatibility schema indexes missing: "
            f"{sorted({name for name, _table_name, _columns in INDEX_SPECS} - set(indexes))}"
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "baseline_version": BASELINE_VERSION,
        "valid": True,
        "missing_tables": [],
        "indexes": sorted(indexes),
    }


def _create_sqlite_sql() -> tuple[str, str]:
    return (
        f"""CREATE TABLE IF NOT EXISTS {BASELINE_TABLE_NAME} (
            baseline_version TEXT PRIMARY KEY NOT NULL,
            cutoff_literal TEXT NOT NULL,
            captured_at TEXT NOT NULL,
            frozen_at TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('CAPTURING','FROZEN')),
            membership_count INTEGER NOT NULL CHECK (membership_count >= 0)
        )""",
        f"""CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            user_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            baseline_version TEXT NOT NULL
                REFERENCES {BASELINE_TABLE_NAME}(baseline_version),
            source_mask INTEGER NOT NULL CHECK (source_mask IN (1,2,3)),
            entitlement_source TEXT NOT NULL CHECK (entitlement_source IN
                ('pre_cutoff_review','frozen_card_snapshot',
                 'pre_cutoff_review+frozen_card_snapshot')),
            captured_at TEXT NOT NULL,
            cutoff_literal TEXT NOT NULL,
            PRIMARY KEY (user_id, question_id, baseline_version)
        )""",
    )


def _create_postgres_sql() -> tuple[str, str]:
    return (
        f"""CREATE TABLE IF NOT EXISTS public.{BASELINE_TABLE_NAME} (
            baseline_version TEXT PRIMARY KEY,
            cutoff_literal TEXT NOT NULL,
            captured_at TEXT NOT NULL,
            frozen_at TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('CAPTURING','FROZEN')),
            membership_count INTEGER NOT NULL CHECK (membership_count >= 0)
        )""",
        f"""CREATE TABLE IF NOT EXISTS public.{TABLE_NAME} (
            user_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            baseline_version TEXT NOT NULL
                REFERENCES public.{BASELINE_TABLE_NAME}(baseline_version),
            source_mask INTEGER NOT NULL CHECK (source_mask IN (1,2,3)),
            entitlement_source TEXT NOT NULL CHECK (entitlement_source IN
                ('pre_cutoff_review','frozen_card_snapshot',
                 'pre_cutoff_review+frozen_card_snapshot')),
            captured_at TEXT NOT NULL,
            cutoff_literal TEXT NOT NULL,
            PRIMARY KEY (user_id, question_id, baseline_version)
        )""",
    )


def upgrade(conn: Any, *, dry_run: bool = False) -> dict[str, Any]:
    """Create and validate the additive schema; caller owns commit."""

    if not _is_sqlite(conn):
        conn.execute("SELECT pg_advisory_xact_lock(?)", (ADVISORY_LOCK_KEY,))
    before = validate_schema(conn)
    if dry_run:
        return {
            **before,
            "created": [],
            "planned_create": before.get("missing_tables", []),
            "dry_run": True,
        }

    statements = _create_sqlite_sql() if _is_sqlite(conn) else _create_postgres_sql()
    for statement in statements:
        conn.execute(statement)
    table_prefix = _table_prefix(conn)
    for index_name, table_name, columns in INDEX_SPECS:
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS {index_name} ON "
            f"{table_prefix}{table_name} ({columns})"
        )
    after = validate_schema(conn)
    if not after["valid"]:
        raise SchemaMismatch(f"compatibility schema incomplete: {after}")
    return {
        **after,
        "created": before.get("missing_tables", []),
        "planned_create": [],
        "dry_run": False,
    }


def downgrade_for_isolated_test(conn: Any) -> None:
    """Drop only this candidate schema from a disposable test database."""

    prefix = _table_prefix(conn)
    conn.execute(f"DROP TABLE IF EXISTS {prefix}{TABLE_NAME}")
    conn.execute(f"DROP TABLE IF EXISTS {prefix}{BASELINE_TABLE_NAME}")


__all__ = [
    "ADVISORY_LOCK_KEY",
    "BASELINE_TABLE_NAME",
    "BASELINE_VERSION",
    "CUTOFF_LITERAL",
    "MigrationError",
    "SCHEMA_VERSION",
    "SOURCE_BOTH_MASK",
    "SOURCE_CARD_MASK",
    "SOURCE_REVIEW_MASK",
    "STATUS_CAPTURING",
    "STATUS_FROZEN",
    "SchemaMismatch",
    "TABLE_NAME",
    "downgrade_for_isolated_test",
    "upgrade",
    "validate_schema",
]
