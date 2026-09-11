"""Additive Friend Challenge settlement-claim schema candidate.

This module is migration code only.  It never commits, rolls back, runs at
request time, or applies itself to Production.  The explicit migration runner
and the caller-owned transaction remain responsible for invocation and commit.

The table is deliberately limited to the claim identity, settlement state,
and timestamps.  Random reward detail belongs to the first response only and
must not become durable schema authority.
"""

from __future__ import annotations

import re
from typing import Any


SCHEMA_VERSION = "friend_challenge_reward_settlements_v1"
TABLE_NAME = "friend_challenge_reward_settlements"
ADVISORY_LOCK_KEY = 773310043
SETTLEMENT_STATUSES = ("PENDING", "SETTLED")
PRIMARY_KEY_COLUMNS = ("challenge_id", "user_id")
INDEX_SPECS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "idx_friend_challenge_reward_settlements_user_settled_at",
        ("user_id", "settled_at"),
    ),
)


class MigrationError(RuntimeError):
    """Base class for fail-closed migration errors."""


class SchemaMismatch(MigrationError):
    """An existing table does not match the exact settlement contract."""


def _raw_connection(conn: Any) -> Any:
    return getattr(conn, "_conn", conn)


def _is_sqlite(conn: Any) -> bool:
    return _raw_connection(conn).__class__.__module__.startswith("sqlite3")


def _prefix(conn: Any) -> str:
    return "" if _is_sqlite(conn) else "public."


def _row_value(row: Any, index: int, name: str) -> Any:
    try:
        return row[name]
    except (KeyError, TypeError, IndexError):
        return row[index]


def _normalise_type(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _normalise_sql(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _status_literals(expressions: list[str]) -> set[str]:
    literals: set[str] = set()
    for expression in expressions:
        literals.update(re.findall(r"'([^']+)'", expression.upper()))
    return literals


def _sqlite_index_columns(conn: Any, index_name: str) -> tuple[str, ...]:
    rows = conn.execute(f"PRAGMA index_info({index_name})").fetchall()
    return tuple(str(_row_value(row, 2, "name")) for row in rows)


def _table_sqlite(conn: Any) -> str:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (TABLE_NAME,),
    ).fetchone()
    return str(_row_value(row, 0, "sql") or "") if row is not None else ""


def _postgres_constraints(conn: Any) -> tuple[set[str], list[str]]:
    rows = conn.execute(
        """SELECT c.contype, pg_get_constraintdef(c.oid)
             FROM pg_constraint c
             JOIN pg_class t ON t.oid = c.conrelid
             JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE n.nspname = 'public' AND t.relname = ?
            ORDER BY c.contype, c.oid""",
        (TABLE_NAME,),
    ).fetchall()
    primary: set[str] = set()
    checks: list[str] = []
    for row in rows:
        kind = str(_row_value(row, 0, "contype"))
        definition = str(_row_value(row, 1, "pg_get_constraintdef"))
        if kind == "p":
            match = re.search(r"\(([^)]*)\)", definition)
            if match:
                primary.update(
                    part.strip().strip('"') for part in match.group(1).split(",")
                )
        elif kind == "c":
            checks.append(definition)
    return primary, checks


def _validate_sqlite(conn: Any) -> dict[str, Any]:
    rows = conn.execute(f"PRAGMA table_info({TABLE_NAME})").fetchall()
    if not rows:
        return {
            "table": TABLE_NAME,
            "present": False,
            "valid": False,
            "missing": [TABLE_NAME],
            "columns": [],
            "indexes": [],
        }

    expected = {
        "challenge_id": ("integer", False, True),
        "user_id": ("integer", False, True),
        "settlement_status": ("text", False, False),
        "created_at": ("text", False, False),
        "settled_at": ("text", True, False),
    }
    actual_names = {str(_row_value(row, 1, "name")) for row in rows}
    if actual_names != set(expected):
        raise SchemaMismatch(
            f"{TABLE_NAME}: columns differ; unexpected="
            f"{sorted(actual_names - set(expected))}, "
            f"missing={sorted(set(expected) - actual_names)}"
        )
    for row in rows:
        name = str(_row_value(row, 1, "name"))
        expected_type, expected_nullable, expected_pk = expected[name]
        observed_type = _normalise_type(_row_value(row, 2, "type"))
        nullable = not bool(_row_value(row, 3, "notnull"))
        primary_key = bool(_row_value(row, 5, "pk"))
        if observed_type != expected_type or nullable != expected_nullable:
            raise SchemaMismatch(
                f"{TABLE_NAME}.{name}: expected type={expected_type} "
                f"nullable={expected_nullable}; observed type={observed_type} "
                f"nullable={nullable}"
            )
        if primary_key != expected_pk:
            raise SchemaMismatch(f"{TABLE_NAME}.{name}: primary-key contract differs")

    if set(
        _row_value(row, 1, "name")
        for row in rows
        if bool(_row_value(row, 5, "pk"))
    ) != set(PRIMARY_KEY_COLUMNS):
        raise SchemaMismatch(f"{TABLE_NAME}: primary key differs")

    table_sql = _normalise_sql(_table_sqlite(conn))
    if "settlement_status" not in table_sql or _status_literals([table_sql]) != set(
        SETTLEMENT_STATUSES
    ):
        raise SchemaMismatch(f"{TABLE_NAME}: settlement status CHECK is missing or weakened")

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
            raise SchemaMismatch(f"{TABLE_NAME}: index {index_name} has unexpected columns")

    return {
        "table": TABLE_NAME,
        "present": True,
        "valid": True,
        "missing": [],
        "columns": [str(_row_value(row, 1, "name")) for row in rows],
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
            "valid": False,
            "missing": [TABLE_NAME],
            "columns": [],
            "indexes": [],
        }

    expected = {
        "challenge_id": ("integer", False),
        "user_id": ("integer", False),
        "settlement_status": ("text", False),
        "created_at": ("timestamp with time zone", False),
        "settled_at": ("timestamp with time zone", True),
    }
    found = {str(_row_value(row, 0, "column_name")): row for row in rows}
    if set(found) != set(expected):
        raise SchemaMismatch(
            f"{TABLE_NAME}: columns differ; unexpected="
            f"{sorted(set(found) - set(expected))}, "
            f"missing={sorted(set(expected) - set(found))}"
        )
    for name, (expected_type, expected_nullable) in expected.items():
        row = found[name]
        observed_type = _normalise_type(_row_value(row, 1, "data_type"))
        nullable = str(_row_value(row, 2, "is_nullable")).upper() == "YES"
        if observed_type != expected_type or nullable != expected_nullable:
            raise SchemaMismatch(
                f"{TABLE_NAME}.{name}: expected type={expected_type} "
                f"nullable={expected_nullable}; observed type={observed_type} "
                f"nullable={nullable}"
            )

    primary, checks = _postgres_constraints(conn)
    if primary != set(PRIMARY_KEY_COLUMNS):
        raise SchemaMismatch(f"{TABLE_NAME}: primary key differs: {sorted(primary)}")
    if not any(
        "SETTLEMENT_STATUS" in check.upper()
        and _status_literals([check]) == set(SETTLEMENT_STATUSES)
        for check in checks
    ):
        raise SchemaMismatch(f"{TABLE_NAME}: settlement status CHECK is missing or weakened")

    index_rows = conn.execute(
        """SELECT indexname, indexdef
             FROM pg_indexes
            WHERE schemaname = 'public' AND tablename = ?""",
        (TABLE_NAME,),
    ).fetchall()
    indexes = {
        str(_row_value(row, 0, "indexname")): _normalise_sql(
            _row_value(row, 1, "indexdef")
        )
        for row in index_rows
    }
    for index_name, columns in INDEX_SPECS:
        definition = indexes.get(index_name, "")
        if not definition:
            raise SchemaMismatch(f"{TABLE_NAME}: index {index_name} is missing")
        match = re.search(r"\(([^()]*)\)", definition)
        observed = tuple(part.strip().strip('"') for part in match.group(1).split(",")) if match else ()
        if observed != columns:
            raise SchemaMismatch(f"{TABLE_NAME}: index {index_name} has unexpected columns")

    return {
        "table": TABLE_NAME,
        "present": True,
        "valid": True,
        "missing": [],
        "columns": [str(_row_value(row, 0, "column_name")) for row in rows],
        "indexes": sorted(name for name, _columns in INDEX_SPECS),
    }


def validate_schema(conn: Any) -> dict[str, Any]:
    result = _validate_sqlite(conn) if _is_sqlite(conn) else _validate_postgres(conn)
    return {**result, "schema_version": SCHEMA_VERSION}


def _create_sql(conn: Any) -> str:
    statuses = ", ".join(f"'{value}'" for value in SETTLEMENT_STATUSES)
    table = f"{_prefix(conn)}{TABLE_NAME}"
    created_type = "TEXT" if _is_sqlite(conn) else "TIMESTAMPTZ"
    return f"""CREATE TABLE IF NOT EXISTS {table} (
        challenge_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        settlement_status TEXT NOT NULL CHECK (settlement_status IN ({statuses})),
        created_at {created_type} NOT NULL,
        settled_at {created_type} NULL,
        CONSTRAINT pk_friend_challenge_reward_settlements
          PRIMARY KEY (challenge_id, user_id)
    )"""


def _create_index_sql(conn: Any, index_name: str, columns: tuple[str, ...]) -> str:
    table = f"{_prefix(conn)}{TABLE_NAME}"
    return f"CREATE INDEX IF NOT EXISTS {index_name} ON {table} ({', '.join(columns)})"


def upgrade(conn: Any, *, dry_run: bool = False) -> dict[str, Any]:
    """Create and validate the additive schema; the caller owns commit/rollback."""

    if not _is_sqlite(conn):
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
        conn.execute(_create_sql(conn))
    for index_name, columns in INDEX_SPECS:
        conn.execute(_create_index_sql(conn, index_name, columns))
    after = validate_schema(conn)
    if not after["valid"]:
        raise SchemaMismatch(f"Friend Challenge settlement schema incomplete: {after}")
    return {
        **after,
        "created": before["missing"],
        "planned_create": [],
        "dry_run": False,
    }


__all__ = [
    "ADVISORY_LOCK_KEY",
    "INDEX_SPECS",
    "MigrationError",
    "PRIMARY_KEY_COLUMNS",
    "SCHEMA_VERSION",
    "SETTLEMENT_STATUSES",
    "SchemaMismatch",
    "TABLE_NAME",
    "upgrade",
    "validate_schema",
]
