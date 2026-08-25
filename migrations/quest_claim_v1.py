"""Additive D015 schema for exactly-once Quest V2 claims.

The claim row is the Quest business authority for one settled reward period.
It is deliberately separate from D014 progress and from the D5A outbox:
the outbox records acquisition evidence, while this table decides whether a
Quest period has already been settled.  The migration is a candidate only;
callers own the surrounding transaction and this module never commits.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable


SCHEMA_VERSION = "quest_claim_v1"
TABLE_NAME = "quest_claims_v2"
ADVISORY_LOCK_KEY = 773310025

CLAIM_BUSINESS_UNIQUE_KEY = ("user_id", "quest_id", "period_key")
CLAIM_OPERATION_UNIQUE_KEY = ("user_id", "claim_operation_id")
INDEX_SPECS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("idx_quest_claims_v2_user_period", ("user_id", "period_key")),
)


class MigrationError(RuntimeError):
    """Base class for fail-closed D015 schema validation."""


class SchemaMismatch(MigrationError):
    """An existing claim table does not satisfy the D015 contract."""


@dataclass(frozen=True)
class ColumnSpec:
    name: str
    postgres_type: str
    sqlite_type: str
    nullable: bool


COLUMNS = (
    ColumnSpec("claim_id", "text", "TEXT", False),
    ColumnSpec("user_id", "text", "TEXT", False),
    ColumnSpec("quest_id", "text", "TEXT", False),
    ColumnSpec("period_key", "text", "TEXT", False),
    ColumnSpec("claim_operation_id", "text", "TEXT", False),
    ColumnSpec("request_fingerprint", "text", "TEXT", False),
    ColumnSpec("quest_definition_version", "bigint", "INTEGER", False),
    ColumnSpec("reward_profile_id", "text", "TEXT", False),
    ColumnSpec("claim_status", "text", "TEXT", False),
    ColumnSpec("result_payload", "jsonb", "TEXT", False),
    ColumnSpec("created_at", "timestamp with time zone", "TEXT", False),
    ColumnSpec("settled_at", "timestamp with time zone", "TEXT", True),
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


def _table_columns(conn: Any) -> dict[str, Any]:
    if _is_sqlite(conn):
        rows = _fetchall(conn, f"PRAGMA table_info({TABLE_NAME})")
        return {str(_row_value(row, 1, "name")): row for row in rows}
    rows = _fetchall(
        conn,
        """SELECT column_name, data_type, is_nullable
             FROM information_schema.columns
            WHERE table_schema='public' AND table_name=?
            ORDER BY ordinal_position""",
        (TABLE_NAME,),
    )
    return {str(_row_value(row, 0, "column_name")): row for row in rows}


def _primary_key(conn: Any) -> tuple[str, ...]:
    if _is_sqlite(conn):
        rows = _fetchall(conn, f"PRAGMA table_info({TABLE_NAME})")
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
        (TABLE_NAME,),
    )
    return tuple(str(_row_value(row, 0, "column_name")) for row in rows)


def _sqlite_index_columns(conn: Any, index_name: str) -> tuple[str, ...]:
    rows = _fetchall(conn, f"PRAGMA index_info({index_name})")
    return tuple(str(_row_value(row, 2, "name")) for row in rows)


def _postgres_constraints(conn: Any) -> tuple[tuple[str, ...], set[tuple[str, ...]]]:
    rows = _fetchall(
        conn,
        """SELECT c.contype, pg_get_constraintdef(c.oid)
             FROM pg_constraint c
             JOIN pg_class t ON t.oid=c.conrelid
             JOIN pg_namespace n ON n.oid=t.relnamespace
            WHERE n.nspname='public' AND t.relname=?
         ORDER BY c.contype, c.oid""",
        (TABLE_NAME,),
    )
    primary: tuple[str, ...] = ()
    unique: set[tuple[str, ...]] = set()
    for row in rows:
        kind = str(_row_value(row, 0, "contype"))
        definition = str(_row_value(row, 1, "pg_get_constraintdef"))
        match = re.search(r"\(([^)]*)\)", definition)
        columns = (
            tuple(part.strip().strip('"') for part in match.group(1).split(","))
            if match
            else ()
        )
        if kind == "p":
            primary = columns
        elif kind == "u":
            unique.add(columns)
    return primary, unique


def _index_names(conn: Any) -> set[str]:
    if _is_sqlite(conn):
        return {
            str(_row_value(row, 1, "name"))
            for row in _fetchall(conn, f"PRAGMA index_list({TABLE_NAME})")
        }
    rows = _fetchall(
        conn,
        """SELECT indexname FROM pg_indexes
             WHERE schemaname='public' AND tablename=?""",
        (TABLE_NAME,),
    )
    return {str(_row_value(row, 0, "indexname")) for row in rows}


def _postgres_index_columns(conn: Any, index_name: str) -> tuple[str, ...]:
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
        (TABLE_NAME, index_name),
    )
    return tuple(str(_row_value(row, 0, "attname")) for row in rows)


def validate_schema(conn: Any) -> dict[str, Any]:
    found = _table_columns(conn)
    if not found:
        return {
            "schema_version": SCHEMA_VERSION,
            "dialect": "sqlite" if _is_sqlite(conn) else "postgres",
            "valid": False,
            "table": TABLE_NAME,
            "present": False,
            "missing": [TABLE_NAME],
            "columns": [],
            "indexes": [],
        }

    expected = {spec.name: spec for spec in COLUMNS}
    if set(found) != set(expected):
        raise SchemaMismatch(
            f"{TABLE_NAME}: columns differ; unexpected={sorted(set(found)-set(expected))}, "
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
                f"{TABLE_NAME}.{name}: expected type={expected_type} nullable={spec.nullable}; "
                f"observed type={observed_type} nullable={nullable}"
            )

    primary = _primary_key(conn)
    if primary != ("claim_id",):
        raise SchemaMismatch(f"{TABLE_NAME}: primary key differs: {primary!r}")

    if _is_sqlite(conn):
        unique_sets = {
            _sqlite_index_columns(conn, str(_row_value(row, 1, "name")))
            for row in _fetchall(conn, f"PRAGMA index_list({TABLE_NAME})")
            if bool(_row_value(row, 2, "unique"))
        }
    else:
        _pg_primary, unique_sets = _postgres_constraints(conn)
    for required in (CLAIM_BUSINESS_UNIQUE_KEY, CLAIM_OPERATION_UNIQUE_KEY):
        if required not in unique_sets:
            raise SchemaMismatch(f"{TABLE_NAME}: required uniqueness is missing: {required!r}")

    index_names = _index_names(conn)
    for index_name, columns in INDEX_SPECS:
        if index_name not in index_names:
            raise SchemaMismatch(f"{TABLE_NAME}: required index is missing: {index_name}")
        observed = (
            _sqlite_index_columns(conn, index_name)
            if _is_sqlite(conn)
            else _postgres_index_columns(conn, index_name)
        )
        if observed != columns:
            raise SchemaMismatch(
                f"{TABLE_NAME}: index {index_name} differs; expected={columns!r}, observed={observed!r}"
            )

    return {
        "schema_version": SCHEMA_VERSION,
        "dialect": "sqlite" if _is_sqlite(conn) else "postgres",
        "valid": True,
        "table": TABLE_NAME,
        "present": True,
        "missing": [],
        "columns": [spec.name for spec in COLUMNS],
        "indexes": [name for name, _columns in INDEX_SPECS],
    }


def _create_sqlite_sql() -> str:
    return f"""CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
        claim_id TEXT PRIMARY KEY NOT NULL,
        user_id TEXT NOT NULL,
        quest_id TEXT NOT NULL,
        period_key TEXT NOT NULL,
        claim_operation_id TEXT NOT NULL,
        request_fingerprint TEXT NOT NULL,
        quest_definition_version INTEGER NOT NULL CHECK (quest_definition_version >= 1),
        reward_profile_id TEXT NOT NULL,
        claim_status TEXT NOT NULL CHECK (claim_status IN ('PENDING','SETTLED')),
        result_payload TEXT NOT NULL,
        created_at TEXT NOT NULL,
        settled_at TEXT,
        UNIQUE(user_id, quest_id, period_key),
        UNIQUE(user_id, claim_operation_id)
    )"""


def _create_postgres_sql() -> str:
    return f"""CREATE TABLE IF NOT EXISTS public.{TABLE_NAME} (
        claim_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        quest_id TEXT NOT NULL,
        period_key TEXT NOT NULL,
        claim_operation_id TEXT NOT NULL,
        request_fingerprint TEXT NOT NULL,
        quest_definition_version BIGINT NOT NULL CHECK (quest_definition_version >= 1),
        reward_profile_id TEXT NOT NULL,
        claim_status TEXT NOT NULL CHECK (claim_status IN ('PENDING','SETTLED')),
        result_payload JSONB NOT NULL,
        created_at TIMESTAMPTZ NOT NULL,
        settled_at TIMESTAMPTZ,
        CONSTRAINT uq_quest_claims_v2_user_business UNIQUE(user_id, quest_id, period_key),
        CONSTRAINT uq_quest_claims_v2_user_operation UNIQUE(user_id, claim_operation_id)
    )"""


def _create_index_sql(index_name: str, columns: tuple[str, ...], *, sqlite: bool) -> str:
    table = TABLE_NAME if sqlite else f"public.{TABLE_NAME}"
    return f"CREATE INDEX IF NOT EXISTS {index_name} ON {table} ({', '.join(columns)})"


def upgrade(conn: Any, *, dry_run: bool = False) -> dict[str, Any]:
    """Create and validate the additive D015 claim schema."""

    if not _is_sqlite(conn):
        _execute(conn, "SELECT pg_advisory_xact_lock(?)", (ADVISORY_LOCK_KEY,))
    before = validate_schema(conn)
    if dry_run:
        return {**before, "dry_run": True, "created": []}
    sqlite = _is_sqlite(conn)
    if not before["present"]:
        _execute(conn, _create_sqlite_sql() if sqlite else _create_postgres_sql())
    for index_name, columns in INDEX_SPECS:
        _execute(conn, _create_index_sql(index_name, columns, sqlite=sqlite))
    after = validate_schema(conn)
    if not after["valid"]:
        raise SchemaMismatch(f"D015 schema incomplete: {after}")
    return {**after, "dry_run": False, "created": [TABLE_NAME] if not before["present"] else []}


def downgrade_for_isolated_test(conn: Any) -> None:
    """Drop only the D015 claim schema from a disposable database."""

    sqlite = _is_sqlite(conn)
    for index_name, _columns in INDEX_SPECS:
        _execute(conn, f"DROP INDEX IF EXISTS {index_name}")
    table = TABLE_NAME if sqlite else f"public.{TABLE_NAME}"
    _execute(conn, f"DROP TABLE IF EXISTS {table}")


__all__ = [
    "CLAIM_BUSINESS_UNIQUE_KEY",
    "CLAIM_OPERATION_UNIQUE_KEY",
    "COLUMNS",
    "INDEX_SPECS",
    "MigrationError",
    "SCHEMA_VERSION",
    "SchemaMismatch",
    "TABLE_NAME",
    "downgrade_for_isolated_test",
    "upgrade",
    "validate_schema",
]
