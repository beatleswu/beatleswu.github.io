"""Additive, fail-closed schema contract for Wave 2 onboarding state.

The explicit migration runner owns commit and invocation. This module only
creates the new table when absent and validates an existing table. It never
changes users, legacy tour state, MapBattle tables, SRS rows, rewards, or
progression state.
"""

from __future__ import annotations

import re
from typing import Any


SCHEMA_VERSION = "w2_a1_onboarding_v1"
TABLE_NAME = "wave2_onboarding_state_v1"
ADVISORY_LOCK_KEY = 773310041

STATUS_VALUES = (
    "NOT_ENROLLED",
    "NOT_STARTED",
    "IN_PROGRESS",
    "SKIPPED",
    "COMPLETED",
)
STEP_VALUES = (
    "start",
    "first_context",
    "first_question",
    "first_review",
    "first_combat",
    "first_reward",
    "first_growth",
    "next_action",
)


class MigrationError(RuntimeError):
    """Base class for fail-closed onboarding schema errors."""


class SchemaMismatch(MigrationError):
    """The existing onboarding table does not match the v1 contract."""


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


def _table_exists(conn: Any) -> bool:
    if _is_sqlite(conn):
        return conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (TABLE_NAME,),
        ).fetchone() is not None
    return conn.execute(
        """SELECT 1 FROM information_schema.tables
             WHERE table_schema='public' AND table_name=?""",
        (TABLE_NAME,),
    ).fetchone() is not None


def _create_sql(conn: Any) -> str:
    status_sql = ", ".join(f"'{value}'" for value in STATUS_VALUES)
    step_sql = ", ".join(f"'{value}'" for value in STEP_VALUES)
    return f"""CREATE TABLE IF NOT EXISTS {_prefix(conn)}{TABLE_NAME} (
        user_id INTEGER PRIMARY KEY,
        state_version INTEGER NOT NULL DEFAULT 0
            CHECK (state_version >= 0),
        status TEXT NOT NULL CHECK (status IN ({status_sql})),
        current_step TEXT NOT NULL CHECK (current_step IN ({step_sql})),
        first_context_attempt_id TEXT,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )"""


def _sqlite_columns(conn: Any) -> list[dict[str, Any]]:
    rows = conn.execute(f"PRAGMA table_info({TABLE_NAME})").fetchall()
    return [
        {
            "name": str(_row_value(row, 1, "name")),
            "type": _normalise_type(_row_value(row, 2, "type")),
            "nullable": (
                not bool(_row_value(row, 3, "notnull"))
                and not bool(_row_value(row, 5, "pk"))
            ),
            "primary_key": bool(_row_value(row, 5, "pk")),
            "default": _row_value(row, 4, "dflt_value"),
        }
        for row in rows
    ]


def _postgres_columns(conn: Any) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT c.column_name, c.data_type, c.is_nullable,
                       c.column_default,
                       CASE WHEN k.column_name IS NULL THEN 0 ELSE 1 END
                  FROM information_schema.columns c
             LEFT JOIN information_schema.key_column_usage k
                    ON k.table_schema=c.table_schema
                   AND k.table_name=c.table_name
                   AND k.column_name=c.column_name
                   AND k.constraint_name IN (
                         SELECT tc.constraint_name
                           FROM information_schema.table_constraints tc
                          WHERE tc.table_schema=c.table_schema
                            AND tc.table_name=c.table_name
                            AND tc.constraint_type='PRIMARY KEY'
                       )
                 WHERE c.table_schema='public' AND c.table_name=?
              ORDER BY c.ordinal_position""",
        (TABLE_NAME,),
    ).fetchall()
    return [
        {
            "name": str(_row_value(row, 0, "column_name")),
            "type": _normalise_type(_row_value(row, 1, "data_type")),
            "nullable": str(_row_value(row, 2, "is_nullable")).upper() == "YES",
            "default": _row_value(row, 3, "column_default"),
            "primary_key": bool(_row_value(row, 4, "primary_key")),
        }
        for row in rows
    ]


def _check_expressions(conn: Any) -> list[str]:
    if _is_sqlite(conn):
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (TABLE_NAME,),
        ).fetchone()
        return [str(row[0] if not hasattr(row, "keys") else row["sql"] or "")]
    rows = conn.execute(
        """SELECT pg_get_constraintdef(oid)
             FROM pg_constraint
            WHERE conrelid='public.wave2_onboarding_state_v1'::regclass
              AND contype='c'"""
    ).fetchall()
    return [str(_row_value(row, 0, "pg_get_constraintdef")) for row in rows]


def _normalise_sql(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _check_in_values(expressions: list[str], field: str, values: tuple[str, ...]) -> bool:
    wanted = {value.lower() for value in values}
    pattern = re.compile(
        rf"check\s*\(\s*{re.escape(field)}\s+in\s*\(([^)]*)\)",
        re.IGNORECASE,
    )
    for expression in expressions:
        match = pattern.search(_normalise_sql(expression))
        if match:
            observed = set(re.findall(r"'([^']+)'", match.group(1).lower()))
            if observed == wanted:
                return True
    return False


def _has_check(expressions: list[str], pattern: str) -> bool:
    return any(re.search(pattern, _normalise_sql(expression)) for expression in expressions)


def validate_schema(conn: Any) -> dict[str, Any]:
    if not _table_exists(conn):
        return {
            "schema_version": SCHEMA_VERSION,
            "table": TABLE_NAME,
            "present": False,
            "valid": False,
            "missing": [TABLE_NAME],
            "columns": [],
        }

    columns = _sqlite_columns(conn) if _is_sqlite(conn) else _postgres_columns(conn)
    expected = {
        "user_id": ("integer", False, True),
        "state_version": ("integer", False, False),
        "status": ("text", False, False),
        "current_step": ("text", False, False),
        "first_context_attempt_id": ("text", True, False),
        "updated_at": ("text", False, False),
    }
    actual_names = {column["name"] for column in columns}
    if actual_names != set(expected):
        raise SchemaMismatch(
            f"{TABLE_NAME}: columns differ; unexpected="
            f"{sorted(actual_names - set(expected))}, "
            f"missing={sorted(set(expected) - actual_names)}"
        )
    for column in columns:
        name = column["name"]
        expected_type, expected_nullable, expected_pk = expected[name]
        if column["type"] != expected_type:
            raise SchemaMismatch(
                f"{TABLE_NAME}.{name}: expected type={expected_type}; "
                f"observed type={column['type']}"
            )
        if column["nullable"] != expected_nullable:
            raise SchemaMismatch(
                f"{TABLE_NAME}.{name}: expected nullable={expected_nullable}; "
                f"observed nullable={column['nullable']}"
            )
        if column["primary_key"] != expected_pk:
            raise SchemaMismatch(f"{TABLE_NAME}.{name}: primary-key contract differs")

    by_name = {column["name"]: column for column in columns}
    state_default = _normalise_sql(by_name["state_version"]["default"])
    updated_default = _normalise_sql(by_name["updated_at"]["default"])
    if state_default not in {"0", "0::integer"}:
        raise SchemaMismatch(
            f"{TABLE_NAME}.state_version: default must be 0, observed={state_default!r}"
        )
    if "current_timestamp" not in updated_default:
        raise SchemaMismatch(
            f"{TABLE_NAME}.updated_at: CURRENT_TIMESTAMP default is required"
        )

    expressions = _check_expressions(conn)
    if not _has_check(expressions, r"check\s*\(\s*state_version\s*>=\s*0\s*\)"):
        raise SchemaMismatch(f"{TABLE_NAME}: state_version non-negative CHECK missing")
    if not _check_in_values(expressions, "status", STATUS_VALUES):
        raise SchemaMismatch(f"{TABLE_NAME}: status CHECK is missing or weakened")
    if not _check_in_values(expressions, "current_step", STEP_VALUES):
        raise SchemaMismatch(f"{TABLE_NAME}: current_step CHECK is missing or weakened")

    return {
        "schema_version": SCHEMA_VERSION,
        "table": TABLE_NAME,
        "present": True,
        "valid": True,
        "missing": [],
        "columns": [column["name"] for column in columns],
    }


def upgrade(conn: Any, *, dry_run: bool = False) -> dict[str, Any]:
    """Create and validate the additive table; caller owns commit."""

    if not _is_sqlite(conn):
        conn.execute("SELECT pg_advisory_xact_lock(?)", (ADVISORY_LOCK_KEY,))
    before = validate_schema(conn)
    if dry_run:
        return {
            **before,
            "created": [],
            "planned_create": [TABLE_NAME] if not before["present"] else [],
            "dry_run": True,
        }
    if not before["present"]:
        conn.execute(_create_sql(conn))
    after = validate_schema(conn)
    if not after["valid"]:
        raise SchemaMismatch(f"onboarding schema incomplete: {after}")
    return {
        **after,
        "created": [TABLE_NAME] if not before["present"] else [],
        "planned_create": [],
        "dry_run": False,
    }


def apply(conn: Any, *, dry_run: bool = False) -> dict[str, Any]:
    return upgrade(conn, dry_run=dry_run)


def downgrade_for_isolated_test(conn: Any) -> None:
    conn.execute(f"DROP TABLE IF EXISTS {_prefix(conn)}{TABLE_NAME}")


__all__ = [
    "ADVISORY_LOCK_KEY",
    "MigrationError",
    "SCHEMA_VERSION",
    "STATUS_VALUES",
    "STEP_VALUES",
    "SchemaMismatch",
    "TABLE_NAME",
    "apply",
    "downgrade_for_isolated_test",
    "upgrade",
    "validate_schema",
]
