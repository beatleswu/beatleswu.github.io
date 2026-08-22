"""Additive D5A foundation for the shared transactional outbox.

This module is a migration candidate only.  It never commits and it never
creates schema at request time.  The caller owns the surrounding transaction.
The PostgreSQL schema is the production target; SQLite DDL is deliberately
kept compatible with the repository's disposable test fixtures.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


SCHEMA_VERSION = "domain_event_outbox_v1"
TABLE_NAME = "domain_event_outbox"
ADVISORY_LOCK_KEY = 773310022

EVENT_TYPES = (
    "ITEM_ACQUISITION",
    "ITEM_CONSUME_EFFECT",
    "QUESTION_CAPACITY",
    "GACHA_DRAW",
    "PREMIUM_CLAIM",
)
OUTCOMES = ("SUCCESS", "FAILED", "UNKNOWN", "UNVERIFIED")

INDEX_SPECS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("idx_deo_player_occurred_at", ("player_id", "occurred_at")),
    ("idx_deo_player_event_type", ("player_id", "event_type")),
    ("idx_deo_event_type_idempotency", ("event_type", "idempotency_key")),
    ("idx_deo_source_event_id", ("source_event_id",)),
)


class MigrationError(RuntimeError):
    """Base class for a fail-closed schema candidate."""


class SchemaMismatch(MigrationError):
    """An existing table does not match the D5A contract."""


@dataclass(frozen=True)
class ColumnSpec:
    name: str
    postgres_type: str
    sqlite_type: str
    nullable: bool


COLUMNS = (
    ColumnSpec("event_id", "text", "TEXT", False),
    ColumnSpec("schema_version", "bigint", "INTEGER", False),
    ColumnSpec("event_type", "text", "TEXT", False),
    ColumnSpec("player_id", "text", "TEXT", False),
    ColumnSpec("occurred_at", "timestamp with time zone", "TEXT", False),
    ColumnSpec("lineage_id", "text", "TEXT", False),
    ColumnSpec("source_event_id", "text", "TEXT", True),
    ColumnSpec("idempotency_key", "text", "TEXT", False),
    ColumnSpec("outcome", "text", "TEXT", False),
    ColumnSpec("payload", "jsonb", "TEXT", False),
    ColumnSpec("created_at", "timestamp with time zone", "TEXT", False),
    ColumnSpec("published_at", "timestamp with time zone", "TEXT", True),
)
UNIQUE_CONTRACT = ("player_id", "event_type", "idempotency_key")


def _is_sqlite(conn: Any) -> bool:
    raw = getattr(conn, "_conn", conn)
    return raw.__class__.__module__.startswith("sqlite3")


def _row_value(row: Any, index: int, name: str) -> Any:
    try:
        return row[name]
    except (KeyError, TypeError, IndexError):
        return row[index]


def _run(conn: Any, sql: str, params: Iterable[Any] | None = None) -> list[Any]:
    with conn.cursor() as cursor:
        cursor.execute(sql, params)
        if cursor.description is None:
            return []
        return cursor.fetchall()


def _normalize_type(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _sqlite_index_columns(conn: Any, index_name: str) -> tuple[str, ...]:
    rows = conn.execute(f"PRAGMA index_info({index_name})").fetchall()
    return tuple(str(_row_value(row, 2, "name")) for row in rows)


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
    actual_names = {
        str(_row_value(row, 1, "name"))
        for row in rows
    }
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
        if observed_type != _normalize_type(spec.sqlite_type) or nullable != spec.nullable:
            raise SchemaMismatch(
                f"{TABLE_NAME}.{name}: expected type={spec.sqlite_type} "
                f"nullable={spec.nullable}; observed type={observed_type} "
                f"nullable={nullable}"
            )
    primary_key_columns = {
        str(_row_value(row, 1, "name"))
        for row in rows
        if bool(_row_value(row, 5, "pk"))
    }
    if primary_key_columns != {"event_id"}:
        raise SchemaMismatch(f"{TABLE_NAME}: primary key differs: {sorted(primary_key_columns)}")

    unique_sets: set[tuple[str, ...]] = set()
    index_names: set[str] = set()
    for row in conn.execute(f"PRAGMA index_list({TABLE_NAME})").fetchall():
        index_name = str(_row_value(row, 1, "name"))
        index_names.add(index_name)
        if bool(_row_value(row, 2, "unique")):
            unique_sets.add(_sqlite_index_columns(conn, index_name))
    if UNIQUE_CONTRACT not in unique_sets:
        raise SchemaMismatch(f"{TABLE_NAME}: required uniqueness is missing")

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


def _postgres_constraints(conn: Any) -> tuple[set[str], set[tuple[str, ...]], set[str]]:
    rows = _run(
        conn,
        """SELECT c.contype, c.conname, pg_get_constraintdef(c.oid)
             FROM pg_constraint c
             JOIN pg_class t ON t.oid = c.conrelid
             JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE n.nspname = 'public' AND t.relname = %s
            ORDER BY c.contype, c.oid""",
        (TABLE_NAME,),
    )
    primary: set[str] = set()
    unique: set[tuple[str, ...]] = set()
    checks: set[str] = set()
    import re

    for row in rows:
        kind = str(_row_value(row, 0, "contype"))
        name = str(_row_value(row, 1, "conname"))
        definition = str(_row_value(row, 2, "pg_get_constraintdef"))
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
            checks.add(name + " " + definition.upper())
    return primary, unique, checks


def _validate_postgres(conn: Any) -> dict[str, Any]:
    rows = _run(
        conn,
        """SELECT column_name, data_type, is_nullable
             FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position""",
        (TABLE_NAME,),
    )
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
        if observed_type != _normalize_type(spec.postgres_type) or nullable != spec.nullable:
            raise SchemaMismatch(
                f"{TABLE_NAME}.{name}: expected type={spec.postgres_type} "
                f"nullable={spec.nullable}; observed type={observed_type} "
                f"nullable={nullable}"
            )

    primary, unique, checks = _postgres_constraints(conn)
    if primary != {"event_id"}:
        raise SchemaMismatch(f"{TABLE_NAME}: primary key differs: {sorted(primary)}")
    if UNIQUE_CONTRACT not in unique:
        raise SchemaMismatch(f"{TABLE_NAME}: required uniqueness is missing")
    if not any("OUTCOME" in value and "SUCCESS" in value and "UNVERIFIED" in value for value in checks):
        raise SchemaMismatch(f"{TABLE_NAME}: outcome check constraint is missing")

    index_rows = _run(
        conn,
        """SELECT indexname, indexdef
             FROM pg_indexes
            WHERE schemaname = 'public' AND tablename = %s""",
        (TABLE_NAME,),
    )
    indexes = {
        str(_row_value(row, 0, "indexname")): str(_row_value(row, 1, "indexdef"))
        for row in index_rows
    }
    for index_name, columns in INDEX_SPECS:
        definition = _normalize_type(indexes.get(index_name))
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
    return f"""CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
        event_id TEXT PRIMARY KEY NOT NULL,
        schema_version INTEGER NOT NULL,
        event_type TEXT NOT NULL,
        player_id TEXT NOT NULL,
        occurred_at TEXT NOT NULL,
        lineage_id TEXT NOT NULL,
        source_event_id TEXT,
        idempotency_key TEXT NOT NULL,
        outcome TEXT NOT NULL CHECK (outcome IN
          ('SUCCESS','FAILED','UNKNOWN','UNVERIFIED')),
        payload TEXT NOT NULL,
        created_at TEXT NOT NULL,
        published_at TEXT,
        UNIQUE(player_id, event_type, idempotency_key)
    )"""


def _create_postgres_sql() -> str:
    return f"""CREATE TABLE IF NOT EXISTS public.{TABLE_NAME} (
        event_id TEXT PRIMARY KEY,
        schema_version BIGINT NOT NULL,
        event_type TEXT NOT NULL,
        player_id TEXT NOT NULL,
        occurred_at TIMESTAMPTZ NOT NULL,
        lineage_id TEXT NOT NULL,
        source_event_id TEXT,
        idempotency_key TEXT NOT NULL,
        outcome TEXT NOT NULL CHECK (outcome IN
          ('SUCCESS','FAILED','UNKNOWN','UNVERIFIED')),
        payload JSONB NOT NULL,
        created_at TIMESTAMPTZ NOT NULL,
        published_at TIMESTAMPTZ,
        CONSTRAINT uq_domain_event_outbox_player_type_key
          UNIQUE(player_id, event_type, idempotency_key)
    )"""


def _create_index_sql(index_name: str, columns: tuple[str, ...], *, sqlite: bool) -> str:
    table = TABLE_NAME if sqlite else f"public.{TABLE_NAME}"
    return f"CREATE INDEX IF NOT EXISTS {index_name} ON {table} ({', '.join(columns)})"


def upgrade(conn: Any, *, dry_run: bool = False) -> dict[str, Any]:
    """Create and validate the additive D5A schema; caller owns commit."""
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
        raise SchemaMismatch(f"outbox schema missing: {after['missing']}")
    return {
        **after,
        "created": before["missing"],
        "planned_create": [],
        "dry_run": False,
    }


def downgrade_for_isolated_test(conn: Any) -> None:
    """Drop only the D5A schema from a disposable test database."""
    if _is_sqlite(conn):
        conn.execute(f"DROP TABLE IF EXISTS {TABLE_NAME}")
    else:
        conn.execute(f"DROP TABLE IF EXISTS public.{TABLE_NAME}")
