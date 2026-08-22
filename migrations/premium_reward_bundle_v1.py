"""Additive schema candidate for one Premium claim with many components.

The parent claim remains the single period-level business authority.  This
table records its deterministic child components for support reconstruction;
it is not a second claim ledger and does not grant ownership by itself.
"""

from __future__ import annotations

from typing import Any


SCHEMA_VERSION = "premium_reward_bundle_v1"
TABLE_NAME = "premium_reward_bundle_components"
COMPONENT_TYPES = ("QUESTION_CAPACITY", "PURE_COSMETIC")
COMPONENT_STATUSES = ("GRANTED", "DENIED", "UNKNOWN", "UNVERIFIED")
REQUIRED_COLUMNS = {
    "id",
    "claim_id",
    "user_id",
    "reward_period_id",
    "component_key",
    "component_type",
    "component_status",
    "item_id",
    "capacity_delta",
    "operation_id",
    "result_payload",
    "event_id",
    "created_at",
}


class PremiumRewardBundleSchemaError(RuntimeError):
    """The bundle component candidate is not available."""


def _raw(conn: Any) -> Any:
    return getattr(conn, "_conn", conn)


def _is_sqlite(conn: Any) -> bool:
    return _raw(conn).__class__.__module__.lower().startswith("sqlite3")


def _execute(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> Any:
    if hasattr(conn, "execute"):
        return conn.execute(sql, params)
    cursor = conn.cursor()
    cursor.execute(sql.replace("?", "%s"), params)
    return cursor


def _table_exists(conn: Any) -> bool:
    if _is_sqlite(conn):
        return bool(_execute(
            conn,
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (TABLE_NAME,),
        ).fetchone())
    return bool(_execute(
        conn,
        "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=%s",
        (TABLE_NAME,),
    ).fetchone())


def _columns(conn: Any) -> set[str]:
    if _is_sqlite(conn):
        return {str(row[1]) for row in _execute(conn, f"PRAGMA table_info({TABLE_NAME})").fetchall()}
    rows = _execute(
        conn,
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name=%s",
        (TABLE_NAME,),
    ).fetchall()
    return {str(row[0]) for row in rows}


def validate_schema(conn: Any) -> dict[str, Any]:
    missing_columns = sorted(REQUIRED_COLUMNS - _columns(conn)) if _table_exists(conn) else sorted(REQUIRED_COLUMNS)
    return {
        "schema_version": SCHEMA_VERSION,
        "table": TABLE_NAME,
        "valid": not missing_columns,
        "missing_columns": missing_columns,
        "dialect": "sqlite" if _is_sqlite(conn) else "postgres",
    }


def _ddl(conn: Any) -> str:
    if _is_sqlite(conn):
        identity = "INTEGER PRIMARY KEY AUTOINCREMENT"
        stamp = "TEXT"
        payload = "TEXT"
    else:
        identity = "BIGSERIAL PRIMARY KEY"
        stamp = "TIMESTAMPTZ"
        payload = "JSONB"
    return f"""CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
        id {identity},
        claim_id BIGINT NOT NULL,
        user_id INTEGER NOT NULL,
        reward_period_id BIGINT NOT NULL,
        component_key TEXT NOT NULL,
        component_type TEXT NOT NULL CHECK (component_type IN ('QUESTION_CAPACITY','PURE_COSMETIC')),
        component_status TEXT NOT NULL CHECK (component_status IN ('GRANTED','DENIED','UNKNOWN','UNVERIFIED')),
        item_id TEXT,
        capacity_delta INTEGER,
        operation_id TEXT NOT NULL,
        result_payload {payload} NOT NULL,
        event_id TEXT,
        created_at {stamp} NOT NULL,
        UNIQUE(user_id, reward_period_id, component_key),
        UNIQUE(claim_id, component_key),
        FOREIGN KEY(claim_id) REFERENCES premium_reward_claims(id),
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(reward_period_id) REFERENCES premium_reward_periods(id)
    )"""


INDEXES = (
    ("idx_premium_bundle_components_claim", "claim_id, component_key"),
    ("idx_premium_bundle_components_user_period", "user_id, reward_period_id"),
    ("idx_premium_bundle_components_operation", "user_id, operation_id"),
)


def upgrade(conn: Any, *, dry_run: bool = False) -> dict[str, Any]:
    before = validate_schema(conn)
    if dry_run:
        return {**before, "dry_run": True}
    _execute(conn, _ddl(conn))
    for name, columns in INDEXES:
        _execute(conn, f"CREATE INDEX IF NOT EXISTS {name} ON {TABLE_NAME} ({columns})")
    after = validate_schema(conn)
    if not after["valid"]:
        raise PremiumRewardBundleSchemaError(f"Premium reward bundle schema incomplete: {after}")
    return {**after, "created": True, "dry_run": False}


def downgrade_for_isolated_test(conn: Any) -> None:
    for name, _columns_value in reversed(INDEXES):
        _execute(conn, f"DROP INDEX IF EXISTS {name}")
    _execute(conn, f"DROP TABLE IF EXISTS {TABLE_NAME}")


__all__ = [
    "COMPONENT_STATUSES",
    "COMPONENT_TYPES",
    "INDEXES",
    "PremiumRewardBundleSchemaError",
    "SCHEMA_VERSION",
    "TABLE_NAME",
    "downgrade_for_isolated_test",
    "upgrade",
    "validate_schema",
]
