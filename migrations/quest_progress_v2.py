"""Additive D014 schema for durable Quest V2 progress application.

The migration is a candidate only.  It never commits and is not imported by
application startup.  The caller owns the surrounding transaction.

``quest_progress_v2`` is the canonical state projection keyed by one user,
Quest identity, and resolved period.  The application table is the durable
exactly-once gate for one authoritative event fan-out into one Quest period.
Neither table settles claims or rewards.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


SCHEMA_VERSION = "quest_progress_v2"
PROGRESS_TABLE_NAME = "quest_progress_v2"
APPLICATION_TABLE_NAME = "quest_progress_event_applications_v2"
ADVISORY_LOCK_KEY = 773310024

PROGRESS_UNIQUE_KEY = ("user_id", "quest_id", "period_key")
# One authoritative event can resolve to only one period for one Quest.  The
# period is retained as immutable evidence, but is deliberately not part of
# the idempotency key so a replay cannot be applied a second time after a
# catalog/window change.
APPLICATION_UNIQUE_KEY = ("user_id", "source_event_id", "quest_id")

PROGRESS_INDEX_SPECS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("idx_quest_progress_v2_user_period", ("user_id", "period_key")),
)
APPLICATION_INDEX_SPECS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("idx_quest_progress_app_v2_user_event", ("user_id", "source_event_id")),
)


class MigrationError(RuntimeError):
    """Base class for fail-closed D014 schema validation."""


class SchemaMismatch(MigrationError):
    """An existing D014 table does not satisfy the candidate contract."""


@dataclass(frozen=True)
class ColumnSpec:
    name: str
    postgres_type: str
    sqlite_type: str
    nullable: bool


PROGRESS_COLUMNS = (
    ColumnSpec("user_id", "text", "TEXT", False),
    ColumnSpec("quest_id", "text", "TEXT", False),
    ColumnSpec("period_key", "text", "TEXT", False),
    ColumnSpec("progress", "bigint", "INTEGER", False),
    ColumnSpec("completed", "boolean", "INTEGER", False),
    ColumnSpec("definition_version", "bigint", "INTEGER", False),
    ColumnSpec("target_snapshot", "bigint", "INTEGER", False),
    ColumnSpec("created_at", "timestamp with time zone", "TEXT", False),
    ColumnSpec("updated_at", "timestamp with time zone", "TEXT", False),
)

APPLICATION_COLUMNS = (
    ColumnSpec("user_id", "text", "TEXT", False),
    ColumnSpec("source_event_id", "text", "TEXT", False),
    ColumnSpec("quest_id", "text", "TEXT", False),
    ColumnSpec("period_key", "text", "TEXT", False),
    ColumnSpec("source_event_type", "text", "TEXT", False),
    ColumnSpec("source_authority", "text", "TEXT", False),
    ColumnSpec("source_operation_id", "text", "TEXT", False),
    ColumnSpec("operation", "text", "TEXT", False),
    ColumnSpec("amount", "bigint", "INTEGER", False),
    ColumnSpec("resulting_progress", "bigint", "INTEGER", False),
    ColumnSpec("completed", "boolean", "INTEGER", False),
    ColumnSpec("definition_version", "bigint", "INTEGER", False),
    ColumnSpec("target_snapshot", "bigint", "INTEGER", False),
    ColumnSpec("source_payload_hash", "text", "TEXT", False),
    ColumnSpec("source_occurred_at", "timestamp with time zone", "TEXT", False),
    ColumnSpec("applied_at", "timestamp with time zone", "TEXT", False),
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


def _execute(conn: Any, sql: str, params: Iterable[Any] = ()) -> Any:
    params = tuple(params)
    if hasattr(conn, "execute"):
        return conn.execute(sql, params)
    cursor = conn.cursor()
    cursor.execute(sql.replace("?", "%s"), params)
    return cursor


def _fetchall(conn: Any, sql: str, params: Iterable[Any] = ()) -> list[Any]:
    cursor = _execute(conn, sql, params)
    try:
        return list(cursor.fetchall())
    finally:
        if not hasattr(conn, "execute"):
            cursor.close()


def _normalize_type(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _table_columns(conn: Any, table_name: str) -> dict[str, Any]:
    if _is_sqlite(conn):
        rows = _fetchall(conn, f"PRAGMA table_info({table_name})")
        return {str(_row_value(row, 1, "name")): row for row in rows}
    rows = _fetchall(
        conn,
        """SELECT column_name, data_type, is_nullable
             FROM information_schema.columns
            WHERE table_schema='public' AND table_name=?
            ORDER BY ordinal_position""",
        (table_name,),
    )
    return {str(_row_value(row, 0, "column_name")): row for row in rows}


def _index_columns(conn: Any, table_name: str, index_name: str) -> tuple[str, ...]:
    if _is_sqlite(conn):
        rows = _fetchall(conn, f"PRAGMA index_info({index_name})")
        return tuple(str(_row_value(row, 2, "name")) for row in rows)
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
        (table_name, index_name),
    )
    return tuple(str(_row_value(row, 0, "attname")) for row in rows)


def _index_names(conn: Any, table_name: str) -> set[str]:
    if _is_sqlite(conn):
        rows = _fetchall(conn, f"PRAGMA index_list({table_name})")
        return {str(_row_value(row, 1, "name")) for row in rows}
    rows = _fetchall(
        conn,
        """SELECT indexname FROM pg_indexes
             WHERE schemaname='public' AND tablename=?""",
        (table_name,),
    )
    return {str(_row_value(row, 0, "indexname")) for row in rows}


def _primary_key(conn: Any, table_name: str) -> tuple[str, ...]:
    if _is_sqlite(conn):
        rows = _fetchall(conn, f"PRAGMA table_info({table_name})")
        return tuple(
            str(_row_value(row, 1, "name"))
            for row in sorted(rows, key=lambda item: int(_row_value(item, 5, "pk")))
            if int(_row_value(row, 5, "pk")) > 0
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
        (table_name,),
    )
    return tuple(str(_row_value(row, 0, "column_name")) for row in rows)


def _validate_table(
    conn: Any,
    table_name: str,
    columns: tuple[ColumnSpec, ...],
    primary_key: tuple[str, ...],
) -> dict[str, Any]:
    found = _table_columns(conn, table_name)
    if not found:
        return {
            "table": table_name,
            "present": False,
            "missing": [table_name],
            "columns": [],
            "indexes": [],
        }
    expected = {spec.name: spec for spec in columns}
    if set(found) != set(expected):
        raise SchemaMismatch(
            f"{table_name}: columns differ; unexpected={sorted(set(found)-set(expected))}, "
            f"missing={sorted(set(expected)-set(found))}"
        )
    for name, spec in expected.items():
        row = found[name]
        if _is_sqlite(conn):
            observed_type = _normalize_type(_row_value(row, 2, "type"))
            nullable = not bool(_row_value(row, 3, "notnull"))
        else:
            observed_type = _normalize_type(_row_value(row, 1, "data_type"))
            nullable = str(_row_value(row, 2, "is_nullable")).upper() == "YES"
        expected_type = spec.sqlite_type if _is_sqlite(conn) else spec.postgres_type
        if observed_type != _normalize_type(expected_type) or nullable != spec.nullable:
            raise SchemaMismatch(
                f"{table_name}.{name}: expected type={expected_type} nullable={spec.nullable}; "
                f"observed type={observed_type} nullable={nullable}"
            )
    observed_pk = _primary_key(conn, table_name)
    if observed_pk != primary_key:
        raise SchemaMismatch(f"{table_name}: primary key differs: {observed_pk!r}")
    return {
        "table": table_name,
        "present": True,
        "missing": [],
        "columns": sorted(found),
        "indexes": sorted(_index_names(conn, table_name)),
    }


def validate_schema(conn: Any) -> dict[str, Any]:
    progress = _validate_table(
        conn,
        PROGRESS_TABLE_NAME,
        PROGRESS_COLUMNS,
        PROGRESS_UNIQUE_KEY,
    )
    applications = _validate_table(
        conn,
        APPLICATION_TABLE_NAME,
        APPLICATION_COLUMNS,
        APPLICATION_UNIQUE_KEY,
    )
    missing_indexes: list[str] = []
    for table_name, specs in (
        (PROGRESS_TABLE_NAME, PROGRESS_INDEX_SPECS),
        (APPLICATION_TABLE_NAME, APPLICATION_INDEX_SPECS),
    ):
        if not _table_columns(conn, table_name):
            missing_indexes.extend(name for name, _columns in specs)
            continue
        index_names = _index_names(conn, table_name)
        for index_name, columns in specs:
            if index_name not in index_names or _index_columns(conn, table_name, index_name) != columns:
                missing_indexes.append(index_name)
    return {
        "schema_version": SCHEMA_VERSION,
        "dialect": "sqlite" if _is_sqlite(conn) else "postgres",
        "valid": not progress["missing"] and not applications["missing"] and not missing_indexes,
        "progress": progress,
        "applications": applications,
        "missing_indexes": sorted(missing_indexes),
    }


def _create_progress_sql(sqlite: bool) -> str:
    stamp = "TEXT" if sqlite else "TIMESTAMPTZ"
    integer = "INTEGER" if sqlite else "BIGINT"
    boolean = "INTEGER" if sqlite else "BOOLEAN"
    completed_check = "completed IN (0, 1)" if sqlite else "completed IN (FALSE, TRUE)"
    table = PROGRESS_TABLE_NAME if sqlite else f"public.{PROGRESS_TABLE_NAME}"
    return f"""CREATE TABLE IF NOT EXISTS {table} (
        user_id TEXT NOT NULL,
        quest_id TEXT NOT NULL,
        period_key TEXT NOT NULL,
        progress {integer} NOT NULL CHECK (progress >= 0),
        completed {boolean} NOT NULL CHECK ({completed_check}),
        definition_version {integer} NOT NULL CHECK (definition_version >= 1),
        target_snapshot {integer} NOT NULL CHECK (target_snapshot >= 1),
        created_at {stamp} NOT NULL,
        updated_at {stamp} NOT NULL,
        PRIMARY KEY (user_id, quest_id, period_key)
    )"""


def _create_application_sql(sqlite: bool) -> str:
    stamp = "TEXT" if sqlite else "TIMESTAMPTZ"
    integer = "INTEGER" if sqlite else "BIGINT"
    boolean = "INTEGER" if sqlite else "BOOLEAN"
    completed_check = "completed IN (0, 1)" if sqlite else "completed IN (FALSE, TRUE)"
    table = APPLICATION_TABLE_NAME if sqlite else f"public.{APPLICATION_TABLE_NAME}"
    return f"""CREATE TABLE IF NOT EXISTS {table} (
        user_id TEXT NOT NULL,
        source_event_id TEXT NOT NULL,
        quest_id TEXT NOT NULL,
        period_key TEXT NOT NULL,
        source_event_type TEXT NOT NULL,
        source_authority TEXT NOT NULL,
        source_operation_id TEXT NOT NULL,
        operation TEXT NOT NULL CHECK (operation IN ('INCREMENT', 'RESET')),
        amount {integer} NOT NULL CHECK (amount >= 0),
        resulting_progress {integer} NOT NULL CHECK (resulting_progress >= 0),
        completed {boolean} NOT NULL CHECK ({completed_check}),
        definition_version {integer} NOT NULL CHECK (definition_version >= 1),
        target_snapshot {integer} NOT NULL CHECK (target_snapshot >= 1),
        source_payload_hash TEXT NOT NULL,
        source_occurred_at {stamp} NOT NULL,
        applied_at {stamp} NOT NULL,
        PRIMARY KEY (user_id, source_event_id, quest_id)
    )"""


def _create_index_sql(table_name: str, index_name: str, columns: tuple[str, ...], sqlite: bool) -> str:
    table = table_name if sqlite else f"public.{table_name}"
    return f"CREATE INDEX IF NOT EXISTS {index_name} ON {table} ({', '.join(columns)})"


def upgrade(conn: Any, *, dry_run: bool = False) -> dict[str, Any]:
    """Create and validate the additive D014 schema; caller owns commit."""

    sqlite = _is_sqlite(conn)
    if not sqlite:
        _execute(conn, "SELECT pg_advisory_xact_lock(?)", (ADVISORY_LOCK_KEY,))
    before = validate_schema(conn)
    if dry_run:
        return {**before, "dry_run": True, "created": []}
    if not before["progress"]["present"]:
        _execute(conn, _create_progress_sql(sqlite))
    if not before["applications"]["present"]:
        _execute(conn, _create_application_sql(sqlite))
    for table_name, specs in (
        (PROGRESS_TABLE_NAME, PROGRESS_INDEX_SPECS),
        (APPLICATION_TABLE_NAME, APPLICATION_INDEX_SPECS),
    ):
        for index_name, columns in specs:
            _execute(conn, _create_index_sql(table_name, index_name, columns, sqlite))
    after = validate_schema(conn)
    if not after["valid"]:
        raise SchemaMismatch(f"D014 schema incomplete: {after}")
    return {**after, "dry_run": False, "created": [PROGRESS_TABLE_NAME, APPLICATION_TABLE_NAME]}


def downgrade_for_isolated_test(conn: Any) -> None:
    """Drop only D014 tables from a disposable test database."""

    sqlite = _is_sqlite(conn)
    for table_name, specs in (
        (APPLICATION_TABLE_NAME, APPLICATION_INDEX_SPECS),
        (PROGRESS_TABLE_NAME, PROGRESS_INDEX_SPECS),
    ):
        for index_name, _columns in specs:
            _execute(conn, f"DROP INDEX IF EXISTS {index_name}")
        table = table_name if sqlite else f"public.{table_name}"
        _execute(conn, f"DROP TABLE IF EXISTS {table}")


__all__ = [
    "APPLICATION_TABLE_NAME",
    "APPLICATION_UNIQUE_KEY",
    "MigrationError",
    "PROGRESS_TABLE_NAME",
    "PROGRESS_UNIQUE_KEY",
    "SCHEMA_VERSION",
    "SchemaMismatch",
    "downgrade_for_isolated_test",
    "upgrade",
    "validate_schema",
]
