"""Additive review-log identity support for D5B.

Historical rows remain valid with NULL identity fields.  New canonical
question submissions bind a validated identity to the authenticated player;
the partial unique index is the PostgreSQL correctness gate.
"""

from __future__ import annotations

from typing import Any


SCHEMA_VERSION = "review_log_submission_idempotency_v1"
TABLE_NAME = "review_log"
SUBMISSION_ID_COLUMN = "submission_id"
PAYLOAD_HASH_COLUMN = "submission_payload_hash"
UNIQUE_INDEX_NAME = "uq_review_log_user_submission_id"


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
        # SQLite supports DROP COLUMN in the repository's supported test
        # runtime, but does not accept PostgreSQL's IF EXISTS clause here.
        conn.execute(f"ALTER TABLE {TABLE_NAME} DROP COLUMN {column}")


def _duplicate_identities(conn: Any) -> list[Any]:
    rows = conn.execute(
        f"""SELECT user_id, {SUBMISSION_ID_COLUMN}, COUNT(*) AS n
              FROM {TABLE_NAME}
             WHERE {SUBMISSION_ID_COLUMN} IS NOT NULL
          GROUP BY user_id, {SUBMISSION_ID_COLUMN}
            HAVING COUNT(*) > 1"""
    ).fetchall()
    return rows


def validate_schema(conn: Any) -> dict[str, Any]:
    columns = _column_names(conn)
    missing = [
        column
        for column in (SUBMISSION_ID_COLUMN, PAYLOAD_HASH_COLUMN)
        if column not in columns
    ]
    indexes = _index_names(conn)
    if not missing and UNIQUE_INDEX_NAME not in indexes:
        missing.append(UNIQUE_INDEX_NAME)
    duplicates = _duplicate_identities(conn) if not missing else []
    if duplicates:
        raise MigrationError(
            f"{TABLE_NAME} contains duplicate non-null submission identities"
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "table": TABLE_NAME,
        "columns": sorted(columns),
        "indexes": sorted(indexes),
        "missing": missing,
        "historical_null_identities_allowed": True,
    }


def upgrade(conn: Any, *, dry_run: bool = False) -> dict[str, Any]:
    """Apply the additive candidate without committing the caller transaction."""
    if _is_sqlite(conn):
        existing = _column_names(conn)
        if SUBMISSION_ID_COLUMN not in existing and not dry_run:
            conn.execute(f"ALTER TABLE {TABLE_NAME} ADD COLUMN {SUBMISSION_ID_COLUMN} TEXT")
        if PAYLOAD_HASH_COLUMN not in existing and not dry_run:
            conn.execute(f"ALTER TABLE {TABLE_NAME} ADD COLUMN {PAYLOAD_HASH_COLUMN} TEXT")
        if not dry_run:
            conn.execute(
                f"CREATE UNIQUE INDEX IF NOT EXISTS {UNIQUE_INDEX_NAME} "
                f"ON {TABLE_NAME}(user_id, {SUBMISSION_ID_COLUMN}) "
                f"WHERE {SUBMISSION_ID_COLUMN} IS NOT NULL"
            )
    else:
        conn.execute("SELECT pg_advisory_xact_lock(?)", (773310023,))
        existing = _column_names(conn)
        if SUBMISSION_ID_COLUMN not in existing and not dry_run:
            conn.execute(
                f"ALTER TABLE public.{TABLE_NAME} "
                f"ADD COLUMN {SUBMISSION_ID_COLUMN} TEXT"
            )
        if PAYLOAD_HASH_COLUMN not in existing and not dry_run:
            conn.execute(
                f"ALTER TABLE public.{TABLE_NAME} "
                f"ADD COLUMN {PAYLOAD_HASH_COLUMN} TEXT"
            )
        if not dry_run:
            conn.execute(
                f"CREATE UNIQUE INDEX IF NOT EXISTS {UNIQUE_INDEX_NAME} "
                f"ON public.{TABLE_NAME}(user_id, {SUBMISSION_ID_COLUMN}) "
                f"WHERE {SUBMISSION_ID_COLUMN} IS NOT NULL"
            )
    if dry_run:
        return {**validate_schema(conn), "dry_run": True}
    result = validate_schema(conn)
    if result["missing"]:
        raise MigrationError(f"review-log submission schema missing: {result['missing']}")
    return {**result, "dry_run": False}


def downgrade_for_isolated_test(conn: Any) -> None:
    """Remove only this additive candidate from a disposable fixture."""
    if _is_sqlite(conn):
        conn.execute(f"DROP INDEX IF EXISTS {UNIQUE_INDEX_NAME}")
        _drop_sqlite_column_if_present(conn, PAYLOAD_HASH_COLUMN)
        _drop_sqlite_column_if_present(conn, SUBMISSION_ID_COLUMN)
    else:
        conn.execute(f"DROP INDEX IF EXISTS public.{UNIQUE_INDEX_NAME}")
        conn.execute(
            f"ALTER TABLE public.{TABLE_NAME} DROP COLUMN IF EXISTS {PAYLOAD_HASH_COLUMN}"
        )
        conn.execute(
            f"ALTER TABLE public.{TABLE_NAME} DROP COLUMN IF EXISTS {SUBMISSION_ID_COLUMN}"
        )


__all__ = [
    "MigrationError",
    "PAYLOAD_HASH_COLUMN",
    "SCHEMA_VERSION",
    "SUBMISSION_ID_COLUMN",
    "TABLE_NAME",
    "UNIQUE_INDEX_NAME",
    "downgrade_for_isolated_test",
    "upgrade",
    "validate_schema",
]
