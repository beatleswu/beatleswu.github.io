"""Additive schema for server-owned Adventure Zone-star progression.

The Incident019B compatibility baseline is a read entitlement only.  This
schema is deliberately separate from both ``adventure_boss_progress`` and
the historical mastery tables:

* ``adventure_zone_star_progress`` owns newly earned Zone stars (0..3).
* ``adventure_zone_star_earnings`` is the idempotency/audit ledger for the
  server-settled events that earned those stars.

This module only creates and validates schema.  It never runs from
``app.init_db()`` and never commits; the explicit migration runner owns the
production gate and transaction.
"""

from __future__ import annotations

import re
from typing import Any


SCHEMA_VERSION = "incident019b_adventure_zone_star_progression_v1"
PROGRESS_TABLE_NAME = "adventure_zone_star_progress"
EARNINGS_TABLE_NAME = "adventure_zone_star_earnings"
ADVISORY_LOCK_KEY = 773310032

INDEX_SPECS: tuple[tuple[str, str, str], ...] = (
    (
        "idx_adventure_zone_star_progress_user",
        PROGRESS_TABLE_NAME,
        "user_id",
    ),
    (
        "idx_adventure_zone_star_earnings_zone",
        EARNINGS_TABLE_NAME,
        "user_id, zone_key, earned_at",
    ),
)


class MigrationError(RuntimeError):
    """Base class for fail-closed schema errors."""


class SchemaMismatch(MigrationError):
    """An existing Zone-star schema does not match this contract."""


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


EXPECTED_PROGRESS_COLUMNS = {
    "user_id": ("integer", False),
    "zone_key": ("text", False),
    "earned_stars": ("integer", False),
    "updated_at": ("text", False),
}

EXPECTED_EARNINGS_COLUMNS = {
    "user_id": ("integer", False),
    "zone_key": ("text", False),
    "event_id": ("text", False),
    "star_number": ("integer", False),
    "source": ("text", False),
    "earned_at": ("text", False),
}


def _validate_columns(
    conn: Any,
    table_name: str,
    expected: dict[str, tuple[str, bool]],
) -> None:
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
    missing_tables = [
        table
        for table in (PROGRESS_TABLE_NAME, EARNINGS_TABLE_NAME)
        if not _table_exists(conn, table)
    ]
    if missing_tables:
        return {
            "schema_version": SCHEMA_VERSION,
            "valid": False,
            "missing_tables": missing_tables,
            "indexes": [],
        }

    _validate_columns(conn, PROGRESS_TABLE_NAME, EXPECTED_PROGRESS_COLUMNS)
    _validate_columns(conn, EARNINGS_TABLE_NAME, EXPECTED_EARNINGS_COLUMNS)
    if _primary_columns(conn, PROGRESS_TABLE_NAME) != {"user_id", "zone_key"}:
        raise SchemaMismatch(f"{PROGRESS_TABLE_NAME}: primary key differs")
    if _primary_columns(conn, EARNINGS_TABLE_NAME) != {"user_id", "event_id"}:
        raise SchemaMismatch(f"{EARNINGS_TABLE_NAME}: primary key differs")

    indexes: list[str] = []
    for name, table_name, columns in INDEX_SPECS:
        found_indexes = _index_names_and_columns(conn, table_name)
        if name in found_indexes:
            observed = found_indexes[name]
            if observed != tuple(part.strip() for part in columns.split(",")):
                raise SchemaMismatch(f"{name}: index columns differ")
            indexes.append(name)
    if set(indexes) != {name for name, _table, _columns in INDEX_SPECS}:
        raise SchemaMismatch(
            "Zone-star schema indexes missing: "
            f"{sorted({name for name, _table, _columns in INDEX_SPECS} - set(indexes))}"
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "valid": True,
        "missing_tables": [],
        "indexes": sorted(indexes),
    }


def _create_sqlite_sql() -> tuple[str, str]:
    return (
        f"""CREATE TABLE IF NOT EXISTS {PROGRESS_TABLE_NAME} (
            user_id INTEGER NOT NULL,
            zone_key TEXT NOT NULL,
            earned_stars INTEGER NOT NULL DEFAULT 0
                CHECK (earned_stars BETWEEN 0 AND 3),
            updated_at TEXT NOT NULL,
            PRIMARY KEY (user_id, zone_key)
        )""",
        f"""CREATE TABLE IF NOT EXISTS {EARNINGS_TABLE_NAME} (
            user_id INTEGER NOT NULL,
            zone_key TEXT NOT NULL,
            event_id TEXT NOT NULL,
            star_number INTEGER NOT NULL CHECK (star_number BETWEEN 1 AND 3),
            source TEXT NOT NULL CHECK (source IN
                ('authoritative_adventure_answer','authoritative_boss_clear')),
            earned_at TEXT NOT NULL,
            PRIMARY KEY (user_id, event_id),
            UNIQUE (user_id, zone_key, star_number)
        )""",
    )


def _create_postgres_sql() -> tuple[str, str]:
    return (
        f"""CREATE TABLE IF NOT EXISTS public.{PROGRESS_TABLE_NAME} (
            user_id INTEGER NOT NULL,
            zone_key TEXT NOT NULL,
            earned_stars INTEGER NOT NULL DEFAULT 0
                CHECK (earned_stars BETWEEN 0 AND 3),
            updated_at TEXT NOT NULL,
            PRIMARY KEY (user_id, zone_key)
        )""",
        f"""CREATE TABLE IF NOT EXISTS public.{EARNINGS_TABLE_NAME} (
            user_id INTEGER NOT NULL,
            zone_key TEXT NOT NULL,
            event_id TEXT NOT NULL,
            star_number INTEGER NOT NULL CHECK (star_number BETWEEN 1 AND 3),
            source TEXT NOT NULL CHECK (source IN
                ('authoritative_adventure_answer','authoritative_boss_clear')),
            earned_at TEXT NOT NULL,
            PRIMARY KEY (user_id, event_id),
            UNIQUE (user_id, zone_key, star_number)
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
        raise SchemaMismatch(f"Zone-star schema incomplete: {after}")
    return {
        **after,
        "created": before.get("missing_tables", []),
        "planned_create": [],
        "dry_run": False,
    }


def downgrade_for_isolated_test(conn: Any) -> None:
    """Drop only this candidate schema from a disposable test database."""

    prefix = _table_prefix(conn)
    conn.execute(f"DROP TABLE IF EXISTS {prefix}{EARNINGS_TABLE_NAME}")
    conn.execute(f"DROP TABLE IF EXISTS {prefix}{PROGRESS_TABLE_NAME}")


__all__ = [
    "ADVISORY_LOCK_KEY",
    "EARNINGS_TABLE_NAME",
    "INDEX_SPECS",
    "MigrationError",
    "PROGRESS_TABLE_NAME",
    "SCHEMA_VERSION",
    "SchemaMismatch",
    "downgrade_for_isolated_test",
    "upgrade",
    "validate_schema",
]
