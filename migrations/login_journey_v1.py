"""Additive D016 schema for server-owned Login Journey and login streak state.

The migration is a candidate only.  It is never imported by application
startup and never commits or rolls back.  Callers own the surrounding
transaction so attendance, streak summary, and Journey projection can be
committed (or rolled back) together.

``login_days_v1`` is the durable attendance authority.  The other two tables
are deterministic projections of that ledger and are deliberately separate
from Quest progress and Quest claims.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable


SCHEMA_VERSION = "login_journey_v1"
LOGIN_DAYS_TABLE_NAME = "login_days_v1"
STREAK_TABLE_NAME = "login_streak_state_v1"
JOURNEY_TABLE_NAME = "login_journey_state_v1"
ADVISORY_LOCK_KEY = 773310026

LOGIN_DAY_BUSINESS_KEY = ("user_id", "local_login_date")
SOURCE_EVENT_UNIQUE_KEY = ("user_id", "source_event_id")
JOURNEY_LENGTH = 7
JOURNEY_ID = "engagement:login_journey"
JOURNEY_VERSION = 1

INDEX_SPECS: tuple[tuple[str, str, tuple[str, ...]], ...] = ()


class MigrationError(RuntimeError):
    """Base class for fail-closed D016 schema validation."""


class SchemaMismatch(MigrationError):
    """An existing D016 table does not satisfy the candidate contract."""


@dataclass(frozen=True)
class ColumnSpec:
    name: str
    postgres_type: str
    sqlite_type: str
    nullable: bool


LOGIN_DAYS_COLUMNS = (
    ColumnSpec("user_id", "bigint", "INTEGER", False),
    ColumnSpec("local_login_date", "date", "TEXT", False),
    ColumnSpec("source_event_id", "text", "TEXT", False),
    ColumnSpec("source_operation_id", "text", "TEXT", True),
    ColumnSpec("source_authority", "text", "TEXT", False),
    ColumnSpec("occurred_at", "timestamp with time zone", "TEXT", False),
    ColumnSpec("recorded_at", "timestamp with time zone", "TEXT", False),
)

STREAK_COLUMNS = (
    ColumnSpec("user_id", "bigint", "INTEGER", False),
    ColumnSpec("current_streak_days", "bigint", "INTEGER", False),
    ColumnSpec("best_streak_days", "bigint", "INTEGER", False),
    ColumnSpec("total_login_days", "bigint", "INTEGER", False),
    ColumnSpec("last_login_date", "date", "TEXT", True),
    ColumnSpec("updated_at", "timestamp with time zone", "TEXT", False),
)

JOURNEY_COLUMNS = (
    ColumnSpec("user_id", "bigint", "INTEGER", False),
    ColumnSpec("journey_id", "text", "TEXT", False),
    ColumnSpec("journey_version", "bigint", "INTEGER", False),
    ColumnSpec("completed_day_count", "bigint", "INTEGER", False),
    ColumnSpec("first_login_date", "date", "TEXT", True),
    ColumnSpec("last_progress_date", "date", "TEXT", True),
    ColumnSpec("completed_at", "timestamp with time zone", "TEXT", True),
    ColumnSpec("status", "text", "TEXT", False),
    ColumnSpec("updated_at", "timestamp with time zone", "TEXT", False),
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


def _unique_sets(conn: Any, table_name: str) -> set[tuple[str, ...]]:
    if _is_sqlite(conn):
        result: set[tuple[str, ...]] = set()
        for row in _fetchall(conn, f"PRAGMA index_list({table_name})"):
            if bool(_row_value(row, 2, "unique")):
                result.add(_index_columns(conn, table_name, str(_row_value(row, 1, "name"))))
        return result
    rows = _fetchall(
        conn,
        """SELECT c.contype, pg_get_constraintdef(c.oid)
             FROM pg_constraint c
             JOIN pg_class t ON t.oid=c.conrelid
             JOIN pg_namespace n ON n.oid=t.relnamespace
            WHERE n.nspname='public' AND t.relname=?
              AND c.contype IN ('p', 'u')
         ORDER BY c.oid""",
        (table_name,),
    )
    result = set()
    for row in rows:
        definition = str(_row_value(row, 1, "pg_get_constraintdef"))
        match = re.search(r"\(([^)]*)\)", definition)
        if match:
            result.add(tuple(part.strip().strip('"') for part in match.group(1).split(",")))
    return result


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
        "columns": [spec.name for spec in columns],
        "indexes": sorted(_index_names(conn, table_name)),
    }


def validate_schema(conn: Any) -> dict[str, Any]:
    """Validate all D016 tables without creating or mutating anything."""

    days = _validate_table(conn, LOGIN_DAYS_TABLE_NAME, LOGIN_DAYS_COLUMNS, LOGIN_DAY_BUSINESS_KEY)
    streak = _validate_table(conn, STREAK_TABLE_NAME, STREAK_COLUMNS, ("user_id",))
    journey = _validate_table(conn, JOURNEY_TABLE_NAME, JOURNEY_COLUMNS, ("user_id",))
    unique_sets = _unique_sets(conn, LOGIN_DAYS_TABLE_NAME) if days["present"] else set()
    if days["present"] and SOURCE_EVENT_UNIQUE_KEY not in unique_sets:
        raise SchemaMismatch(
            f"{LOGIN_DAYS_TABLE_NAME}: required uniqueness is missing: {SOURCE_EVENT_UNIQUE_KEY!r}"
        )
    missing_indexes: list[str] = []
    for key, table_name, columns in INDEX_SPECS:
        index_name = f"idx_{table_name}_{'user_date' if key == 'login_days' else 'user_source'}"
        if not _table_columns(conn, table_name):
            missing_indexes.append(index_name)
            continue
        names = _index_names(conn, table_name)
        if index_name not in names or _index_columns(conn, table_name, index_name) != columns:
            missing_indexes.append(index_name)
    return {
        "schema_version": SCHEMA_VERSION,
        "dialect": "sqlite" if _is_sqlite(conn) else "postgres",
        "valid": (
            not days["missing"]
            and not streak["missing"]
            and not journey["missing"]
            and not missing_indexes
        ),
        "login_days": days,
        "streak": streak,
        "journey": journey,
        "missing_indexes": sorted(missing_indexes),
    }


def _create_login_days_sql(sqlite: bool) -> str:
    integer = "INTEGER" if sqlite else "BIGINT"
    date = "TEXT" if sqlite else "DATE"
    stamp = "TEXT" if sqlite else "TIMESTAMPTZ"
    table = LOGIN_DAYS_TABLE_NAME if sqlite else f"public.{LOGIN_DAYS_TABLE_NAME}"
    return f"""CREATE TABLE IF NOT EXISTS {table} (
        user_id {integer} NOT NULL,
        local_login_date {date} NOT NULL,
        source_event_id TEXT NOT NULL,
        source_operation_id TEXT,
        source_authority TEXT NOT NULL,
        occurred_at {stamp} NOT NULL,
        recorded_at {stamp} NOT NULL,
        PRIMARY KEY (user_id, local_login_date),
        UNIQUE (user_id, source_event_id)
    )"""


def _create_streak_sql(sqlite: bool) -> str:
    integer = "INTEGER" if sqlite else "BIGINT"
    date = "TEXT" if sqlite else "DATE"
    stamp = "TEXT" if sqlite else "TIMESTAMPTZ"
    table = STREAK_TABLE_NAME if sqlite else f"public.{STREAK_TABLE_NAME}"
    return f"""CREATE TABLE IF NOT EXISTS {table} (
        user_id {integer} NOT NULL PRIMARY KEY,
        current_streak_days {integer} NOT NULL CHECK (current_streak_days >= 0),
        best_streak_days {integer} NOT NULL CHECK (best_streak_days >= 0),
        total_login_days {integer} NOT NULL CHECK (total_login_days >= 0),
        last_login_date {date},
        updated_at {stamp} NOT NULL
    )"""


def _create_journey_sql(sqlite: bool) -> str:
    integer = "INTEGER" if sqlite else "BIGINT"
    date = "TEXT" if sqlite else "DATE"
    stamp = "TEXT" if sqlite else "TIMESTAMPTZ"
    table = JOURNEY_TABLE_NAME if sqlite else f"public.{JOURNEY_TABLE_NAME}"
    return f"""CREATE TABLE IF NOT EXISTS {table} (
        user_id {integer} NOT NULL PRIMARY KEY,
        journey_id TEXT NOT NULL,
        journey_version {integer} NOT NULL CHECK (journey_version >= 1),
        completed_day_count {integer} NOT NULL CHECK (completed_day_count BETWEEN 0 AND {JOURNEY_LENGTH}),
        first_login_date {date},
        last_progress_date {date},
        completed_at {stamp},
        status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'COMPLETED')),
        updated_at {stamp} NOT NULL
    )"""


def _create_index_sql(table_name: str, index_name: str, columns: tuple[str, ...], *, sqlite: bool) -> str:
    table = table_name if sqlite else f"public.{table_name}"
    return f"CREATE INDEX IF NOT EXISTS {index_name} ON {table} ({', '.join(columns)})"


def upgrade(conn: Any, *, dry_run: bool = False) -> dict[str, Any]:
    """Create and validate the additive D016 schema; caller owns commit."""

    if not _is_sqlite(conn):
        _execute(conn, "SELECT pg_advisory_xact_lock(?)", (ADVISORY_LOCK_KEY,))
    before = validate_schema(conn)
    if dry_run:
        return {**before, "dry_run": True, "created": []}
    sqlite = _is_sqlite(conn)
    if not before["login_days"]["present"]:
        _execute(conn, _create_login_days_sql(sqlite))
    if not before["streak"]["present"]:
        _execute(conn, _create_streak_sql(sqlite))
    if not before["journey"]["present"]:
        _execute(conn, _create_journey_sql(sqlite))
    for key, table_name, columns in INDEX_SPECS:
        index_name = f"idx_{table_name}_{'user_date' if key == 'login_days' else 'user_source'}"
        _execute(conn, _create_index_sql(table_name, index_name, columns, sqlite=sqlite))
    after = validate_schema(conn)
    if not after["valid"]:
        raise SchemaMismatch(f"D016 schema incomplete: {after}")
    created = [
        table_name
        for table_name, state in (
            (LOGIN_DAYS_TABLE_NAME, before["login_days"]),
            (STREAK_TABLE_NAME, before["streak"]),
            (JOURNEY_TABLE_NAME, before["journey"]),
        )
        if not state["present"]
    ]
    return {**after, "dry_run": False, "created": created}


def downgrade_for_isolated_test(conn: Any) -> None:
    """Drop only D016 tables from a disposable test database."""

    sqlite = _is_sqlite(conn)
    for _key, table_name, _columns in INDEX_SPECS:
        index_name = f"idx_{table_name}_{'user_date' if _key == 'login_days' else 'user_source'}"
        _execute(conn, f"DROP INDEX IF EXISTS {index_name}")
    for table_name in (JOURNEY_TABLE_NAME, STREAK_TABLE_NAME, LOGIN_DAYS_TABLE_NAME):
        table = table_name if sqlite else f"public.{table_name}"
        _execute(conn, f"DROP TABLE IF EXISTS {table}")


__all__ = [
    "ADVISORY_LOCK_KEY",
    "JOURNEY_ID",
    "JOURNEY_LENGTH",
    "JOURNEY_TABLE_NAME",
    "JOURNEY_VERSION",
    "LOGIN_DAY_BUSINESS_KEY",
    "LOGIN_DAYS_TABLE_NAME",
    "MigrationError",
    "SCHEMA_VERSION",
    "SOURCE_EVENT_UNIQUE_KEY",
    "STREAK_TABLE_NAME",
    "SchemaMismatch",
    "downgrade_for_isolated_test",
    "upgrade",
    "validate_schema",
]
