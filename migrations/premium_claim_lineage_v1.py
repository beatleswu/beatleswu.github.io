"""Additive Premium claim/provenance schema candidate.

This migration is intentionally opt-in.  It is not imported by application
startup and never commits.  The caller owns the transaction and a governed
local/test migration runner must decide when to apply it.

The first five tables preserve the Premium V2 candidate's provenance,
period, credit, and claim model.  ``premium_claim_operations`` is the narrow
additional correctness record: it is the business-operation authority for a
claim retry, while the shared D5A outbox remains evidence only.
"""

from __future__ import annotations

from typing import Any


SCHEMA_VERSION = "premium_claim_lineage_v1"
SOURCE_CLASSES = (
    "VERIFIED_PAID",
    "ADMIN_GRANTED",
    "PERMANENT_COMP",
    "TRIAL",
    "LEGACY",
    "UNKNOWN",
)
CLAIM_OPERATION_STATUSES = ("PENDING", "SUCCESS", "DENIED", "UNKNOWN", "UNVERIFIED")

TABLE_NAMES = (
    "premium_entitlement_grants",
    "premium_entitlement_events",
    "premium_reward_periods",
    "premium_reward_credits",
    "premium_reward_claims",
    "premium_claim_operations",
)

REQUIRED_COLUMNS = {
    "premium_entitlement_grants": {
        "id", "user_id", "source_class", "source_reference", "valid_from",
        "valid_until", "commercial_reward_eligibility", "plan_term",
    },
    "premium_entitlement_events": {
        "id", "entitlement_grant_id", "user_id", "event_type",
        "source_reference", "granted_by_or_system_source", "idempotency_key",
    },
    "premium_reward_periods": {
        "id", "period_key", "reward_type", "reward_catalog_key",
        "period_starts_at", "period_ends_at", "claim_window_starts_at",
        "claim_window_ends_at", "annual_grace_days",
    },
    "premium_reward_credits": {
        "id", "user_id", "reward_period_id", "entitlement_grant_id",
        "source_class_snapshot", "plan_term_snapshot", "credit_state",
        "claim_id",
    },
    "premium_reward_claims": {
        "id", "user_id", "reward_credit_id", "reward_period_id",
        "entitlement_grant_id", "source_class_snapshot", "reward_id",
        "reward_type", "ownership_authority", "ownership_reference",
        "claim_idempotency_key", "claim_status",
    },
    "premium_claim_operations": {
        "operation_id", "user_id", "claim_family", "request_fingerprint",
        "benefit_period_key", "reward_id", "operation_status",
        "result_payload", "claim_id", "created_at", "committed_at",
    },
}


class PremiumClaimSchemaError(RuntimeError):
    """The target does not satisfy the additive Premium claim contract."""


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


def _fetchone(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> Any:
    cursor = _execute(conn, sql, params)
    try:
        return cursor.fetchone()
    finally:
        if not hasattr(conn, "execute"):
            cursor.close()


def _table_exists(conn: Any, table: str) -> bool:
    if _is_sqlite(conn):
        return bool(_fetchone(conn, "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)))
    return bool(_fetchone(
        conn,
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema='public' AND table_name=%s",
        (table,),
    ))


def _columns(conn: Any, table: str) -> set[str]:
    if _is_sqlite(conn):
        rows = _execute(conn, f"PRAGMA table_info({table})").fetchall()
        return {str(row[1]) for row in rows}
    rows = _execute(
        conn,
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name=%s",
        (table,),
    ).fetchall()
    return {str(row[0]) for row in rows}


def _dialect(conn: Any) -> str:
    return "sqlite" if _is_sqlite(conn) else "postgres"


def validate_schema(conn: Any) -> dict[str, Any]:
    missing_tables = [table for table in TABLE_NAMES if not _table_exists(conn, table)]
    missing_columns = {
        table: sorted(REQUIRED_COLUMNS[table] - _columns(conn, table))
        for table in TABLE_NAMES
        if _table_exists(conn, table) and REQUIRED_COLUMNS[table] - _columns(conn, table)
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "dialect": _dialect(conn),
        "valid": not missing_tables and not missing_columns,
        "missing_tables": missing_tables,
        "missing_columns": missing_columns,
    }


def _timestamp_type(dialect: str) -> str:
    return "TEXT" if dialect == "sqlite" else "TIMESTAMPTZ"


def _json_type(dialect: str) -> str:
    return "TEXT" if dialect == "sqlite" else "JSONB"


def _id_type(dialect: str) -> str:
    return "INTEGER PRIMARY KEY AUTOINCREMENT" if dialect == "sqlite" else "BIGSERIAL PRIMARY KEY"


def _ddl(dialect: str) -> list[str]:
    ident = _id_type(dialect)
    stamp = _timestamp_type(dialect)
    payload = _json_type(dialect)
    return [
        f"""CREATE TABLE IF NOT EXISTS premium_entitlement_grants (
            id {ident},
            user_id INTEGER NOT NULL,
            source_class TEXT NOT NULL CHECK (source_class IN ('VERIFIED_PAID','ADMIN_GRANTED','PERMANENT_COMP','TRIAL','LEGACY','UNKNOWN')),
            source_reference TEXT NOT NULL,
            granted_at TEXT NOT NULL,
            granted_by_or_system_source TEXT NOT NULL,
            valid_from TEXT NOT NULL,
            valid_until TEXT,
            commercial_reward_eligibility TEXT NOT NULL CHECK (commercial_reward_eligibility IN ('ALLOWED','BLOCKED','OWNER_POLICY_REQUIRED')),
            grant_policy_profile TEXT,
            provider TEXT,
            currency TEXT,
            amount NUMERIC,
            plan_key TEXT,
            plan_term TEXT,
            payment_order_id INTEGER,
            subscription_id INTEGER,
            trial_redemption_id INTEGER,
            classification_reason TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(user_id, source_class, source_reference),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )""",
        f"""CREATE TABLE IF NOT EXISTS premium_entitlement_events (
            id {ident},
            entitlement_grant_id BIGINT NOT NULL,
            parent_entitlement_event_id BIGINT,
            user_id INTEGER NOT NULL,
            event_type TEXT NOT NULL CHECK (event_type IN ('GRANT','EXTEND','RECLASSIFY_WITH_EVIDENCE','REVOKE_BY_AUTHORIZED_POLICY')),
            source_class TEXT NOT NULL CHECK (source_class IN ('VERIFIED_PAID','ADMIN_GRANTED','PERMANENT_COMP','TRIAL','LEGACY','UNKNOWN')),
            source_reference TEXT NOT NULL,
            granted_at TEXT NOT NULL,
            granted_by_or_system_source TEXT NOT NULL,
            valid_from TEXT NOT NULL,
            valid_until TEXT,
            revoked_at TEXT,
            revoke_reason TEXT,
            commercial_reward_eligibility TEXT NOT NULL CHECK (commercial_reward_eligibility IN ('ALLOWED','BLOCKED','OWNER_POLICY_REQUIRED')),
            grant_policy_profile TEXT,
            provider TEXT,
            currency TEXT,
            amount NUMERIC,
            plan_key TEXT,
            plan_term TEXT,
            payment_order_id INTEGER,
            subscription_id INTEGER,
            trial_redemption_id INTEGER,
            classification_reason TEXT,
            idempotency_key TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            FOREIGN KEY(entitlement_grant_id) REFERENCES premium_entitlement_grants(id),
            FOREIGN KEY(parent_entitlement_event_id) REFERENCES premium_entitlement_events(id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )""",
        f"""CREATE TABLE IF NOT EXISTS premium_reward_periods (
            id {ident},
            period_key TEXT NOT NULL UNIQUE,
            reward_type TEXT NOT NULL,
            reward_catalog_key TEXT NOT NULL,
            period_starts_at TEXT NOT NULL,
            period_ends_at TEXT NOT NULL,
            claim_window_starts_at TEXT NOT NULL,
            claim_window_ends_at TEXT NOT NULL,
            annual_grace_days INTEGER NOT NULL DEFAULT 90 CHECK (annual_grace_days >= 0),
            eligibility_policy_version TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""",
        f"""CREATE TABLE IF NOT EXISTS premium_reward_credits (
            id {ident},
            user_id INTEGER NOT NULL,
            reward_period_id BIGINT NOT NULL,
            entitlement_grant_id BIGINT NOT NULL,
            source_class_snapshot TEXT NOT NULL CHECK (source_class_snapshot IN ('VERIFIED_PAID','ADMIN_GRANTED','PERMANENT_COMP','TRIAL','LEGACY','UNKNOWN')),
            plan_term_snapshot TEXT NOT NULL,
            earned_at TEXT NOT NULL,
            claim_window_starts_at TEXT NOT NULL,
            claim_window_ends_at TEXT NOT NULL,
            credit_state TEXT NOT NULL CHECK (credit_state IN ('EARNED','CLAIMED','EXPIRED','DENIED')),
            claim_id BIGINT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(user_id, reward_period_id),
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(reward_period_id) REFERENCES premium_reward_periods(id),
            FOREIGN KEY(entitlement_grant_id) REFERENCES premium_entitlement_grants(id)
        )""",
        f"""CREATE TABLE IF NOT EXISTS premium_reward_claims (
            id {ident},
            user_id INTEGER NOT NULL,
            reward_credit_id BIGINT NOT NULL,
            reward_period_id BIGINT NOT NULL,
            entitlement_grant_id BIGINT NOT NULL,
            source_class_snapshot TEXT NOT NULL CHECK (source_class_snapshot IN ('VERIFIED_PAID','ADMIN_GRANTED','PERMANENT_COMP','TRIAL','LEGACY','UNKNOWN')),
            reward_id TEXT NOT NULL,
            reward_type TEXT NOT NULL,
            ownership_authority TEXT NOT NULL CHECK (ownership_authority IN ('player_wardrobe','premium_bundle')),
            ownership_reference TEXT,
            claim_idempotency_key TEXT NOT NULL UNIQUE,
            claim_status TEXT NOT NULL CHECK (claim_status IN ('GRANTED','DENIED')),
            denial_reason TEXT,
            granted_at TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(user_id, reward_credit_id),
            UNIQUE(user_id, reward_period_id, reward_id),
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(reward_credit_id) REFERENCES premium_reward_credits(id),
            FOREIGN KEY(reward_period_id) REFERENCES premium_reward_periods(id),
            FOREIGN KEY(entitlement_grant_id) REFERENCES premium_entitlement_grants(id)
        )""",
        f"""CREATE TABLE IF NOT EXISTS premium_claim_operations (
            operation_id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            claim_family TEXT NOT NULL,
            request_fingerprint TEXT NOT NULL,
            benefit_period_key TEXT,
            reward_id TEXT,
            operation_status TEXT NOT NULL CHECK (operation_status IN ('PENDING','SUCCESS','DENIED','UNKNOWN','UNVERIFIED')),
            result_payload {payload} NOT NULL,
            claim_id BIGINT,
            created_at {stamp} NOT NULL,
            committed_at {stamp},
            PRIMARY KEY(user_id, operation_id),
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(claim_id) REFERENCES premium_reward_claims(id)
        )""",
    ]


INDEXES = (
    ("idx_premium_grants_user_validity", "premium_entitlement_grants", "user_id, valid_from"),
    ("idx_premium_events_grant_created", "premium_entitlement_events", "entitlement_grant_id, created_at"),
    ("idx_premium_credits_user_state", "premium_reward_credits", "user_id, credit_state"),
    ("idx_premium_claims_user_created", "premium_reward_claims", "user_id, created_at"),
    ("idx_premium_claim_ops_user_created", "premium_claim_operations", "user_id, created_at"),
    ("idx_premium_claim_ops_user_period", "premium_claim_operations", "user_id, claim_family, benefit_period_key"),
)


def upgrade(conn: Any, *, dry_run: bool = False) -> dict[str, Any]:
    """Create the additive candidate in the caller-owned transaction."""

    before = validate_schema(conn)
    if dry_run:
        return {**before, "created": [], "dry_run": True}
    for statement in _ddl(before["dialect"]):
        _execute(conn, statement)
    for name, table, columns in INDEXES:
        _execute(conn, f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({columns})")
    after = validate_schema(conn)
    if not after["valid"]:
        raise PremiumClaimSchemaError(f"Premium claim schema incomplete: {after}")
    return {**after, "created": True, "dry_run": False}


def downgrade_for_isolated_test(conn: Any) -> None:
    """Drop only this candidate's tables for disposable tests."""

    for name, _table, _columns in reversed(INDEXES):
        _execute(conn, f"DROP INDEX IF EXISTS {name}")
    for table in reversed(TABLE_NAMES):
        _execute(conn, f"DROP TABLE IF EXISTS {table}")


__all__ = [
    "CLAIM_OPERATION_STATUSES",
    "SCHEMA_VERSION",
    "SOURCE_CLASSES",
    "TABLE_NAMES",
    "PremiumClaimSchemaError",
    "downgrade_for_isolated_test",
    "upgrade",
    "validate_schema",
]
