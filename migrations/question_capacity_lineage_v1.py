"""Minimal durable operation identity for question-capacity effects.

This is not a generic item ledger.  It only extends the existing
``active_effects`` authority with the identity needed to make +5/+10/+20
capacity consumption retry-safe and to bind the D5A QUESTION_CAPACITY event
to the actual effect row.
"""

from __future__ import annotations

from typing import Any


SCHEMA_VERSION = "question_capacity_lineage_v1"
TABLE_NAME = "active_effects"
OPERATION_ID_COLUMN = "operation_id"
SOURCE_ITEM_COLUMN = "source_item_key"
UNIQUE_INDEX_NAME = "uq_active_effects_user_operation_id"


class MigrationError(RuntimeError):
    """Fail-closed migration/schema error."""


def _is_sqlite(conn: Any) -> bool:
    raw = getattr(conn, "_conn", conn)
    return raw.__class__.__module__.startswith("sqlite3")


def _column_names(conn: Any) -> set[str]:
    if _is_sqlite(conn):
        return {
            str(row[1])
            for row in conn.execute(f"PRAGMA table_info({TABLE_NAME})").fetchall()
        }
    rows = conn.execute(
        """SELECT column_name FROM information_schema.columns
             WHERE table_schema='public' AND table_name=?""",
        (TABLE_NAME,),
    ).fetchall()
    return {str(row["column_name"] if hasattr(row, "keys") else row[0]) for row in rows}


def _index_names(conn: Any) -> set[str]:
    if _is_sqlite(conn):
        return {
            str(row[1])
            for row in conn.execute(f"PRAGMA index_list({TABLE_NAME})").fetchall()
        }
    rows = conn.execute(
        """SELECT indexname FROM pg_indexes
             WHERE schemaname='public' AND tablename=?""",
        (TABLE_NAME,),
    ).fetchall()
    return {str(row["indexname"] if hasattr(row, "keys") else row[0]) for row in rows}


def _drop_sqlite_column_if_present(conn: Any, column: str) -> None:
    columns = _column_names(conn)
    if column in columns:
        # SQLite does not accept PostgreSQL's ``DROP COLUMN IF EXISTS``
        # spelling; this path is only for disposable rollback fixtures.
        conn.execute(f"ALTER TABLE {TABLE_NAME} DROP COLUMN {column}")


def validate_schema(conn: Any) -> dict[str, Any]:
    columns = _column_names(conn)
    missing = [
        column
        for column in (OPERATION_ID_COLUMN, SOURCE_ITEM_COLUMN)
        if column not in columns
    ]
    indexes = _index_names(conn)
    if not missing and UNIQUE_INDEX_NAME not in indexes:
        missing.append(UNIQUE_INDEX_NAME)
    return {
        "schema_version": SCHEMA_VERSION,
        "table": TABLE_NAME,
        "columns": sorted(columns),
        "indexes": sorted(indexes),
        "missing": missing,
        "historical_null_operation_ids_allowed": True,
    }


def upgrade(conn: Any, *, dry_run: bool = False) -> dict[str, Any]:
    """Apply the additive candidate without committing the caller transaction."""
    if _is_sqlite(conn):
        existing = _column_names(conn)
        if OPERATION_ID_COLUMN not in existing and not dry_run:
            conn.execute(f"ALTER TABLE {TABLE_NAME} ADD COLUMN {OPERATION_ID_COLUMN} TEXT")
        if SOURCE_ITEM_COLUMN not in existing and not dry_run:
            conn.execute(f"ALTER TABLE {TABLE_NAME} ADD COLUMN {SOURCE_ITEM_COLUMN} TEXT")
        if not dry_run:
            conn.execute(
                f"CREATE UNIQUE INDEX IF NOT EXISTS {UNIQUE_INDEX_NAME} "
                f"ON {TABLE_NAME}(user_id, {OPERATION_ID_COLUMN}) "
                f"WHERE {OPERATION_ID_COLUMN} IS NOT NULL"
            )
    else:
        conn.execute("SELECT pg_advisory_xact_lock(?)", (773310024,))
        existing = _column_names(conn)
        if OPERATION_ID_COLUMN not in existing and not dry_run:
            conn.execute(
                f"ALTER TABLE public.{TABLE_NAME} "
                f"ADD COLUMN {OPERATION_ID_COLUMN} TEXT"
            )
        if SOURCE_ITEM_COLUMN not in existing and not dry_run:
            conn.execute(
                f"ALTER TABLE public.{TABLE_NAME} "
                f"ADD COLUMN {SOURCE_ITEM_COLUMN} TEXT"
            )
        if not dry_run:
            conn.execute(
                f"CREATE UNIQUE INDEX IF NOT EXISTS {UNIQUE_INDEX_NAME} "
                f"ON public.{TABLE_NAME}(user_id, {OPERATION_ID_COLUMN}) "
                f"WHERE {OPERATION_ID_COLUMN} IS NOT NULL"
            )
    if dry_run:
        return {**validate_schema(conn), "dry_run": True}
    result = validate_schema(conn)
    if result["missing"]:
        raise MigrationError(f"question-capacity schema missing: {result['missing']}")
    return {**result, "dry_run": False}


def downgrade_for_isolated_test(conn: Any) -> None:
    """Remove only this additive candidate from a disposable fixture."""
    if _is_sqlite(conn):
        conn.execute(f"DROP INDEX IF EXISTS {UNIQUE_INDEX_NAME}")
        _drop_sqlite_column_if_present(conn, SOURCE_ITEM_COLUMN)
        _drop_sqlite_column_if_present(conn, OPERATION_ID_COLUMN)
    else:
        conn.execute(f"DROP INDEX IF EXISTS public.{UNIQUE_INDEX_NAME}")
        conn.execute(
            f"ALTER TABLE public.{TABLE_NAME} DROP COLUMN IF EXISTS {SOURCE_ITEM_COLUMN}"
        )
        conn.execute(
            f"ALTER TABLE public.{TABLE_NAME} DROP COLUMN IF EXISTS {OPERATION_ID_COLUMN}"
        )


__all__ = [
    "MigrationError",
    "OPERATION_ID_COLUMN",
    "SCHEMA_VERSION",
    "SOURCE_ITEM_COLUMN",
    "TABLE_NAME",
    "UNIQUE_INDEX_NAME",
    "downgrade_for_isolated_test",
    "upgrade",
    "validate_schema",
]
