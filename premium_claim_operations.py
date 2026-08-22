"""Server-internal durable Premium claim operation identity.

The operation row is the business correctness authority for retries.  It is
separate from ``domain_event_outbox``: an outbox uniqueness conflict must
never decide whether a Premium benefit may be granted.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any, Mapping

from migrations.premium_claim_lineage_v1 import CLAIM_OPERATION_STATUSES
from question_idempotency import canonical_payload_digest, normalize_identity


CLAIM_FAMILY = "PREMIUM_CLAIM"
TABLE_NAME = "premium_claim_operations"


class PremiumClaimOperationError(RuntimeError):
    """Base class for fail-closed claim operation errors."""


class PremiumClaimOperationConflict(PremiumClaimOperationError):
    """The same authenticated-user operation ID was reused for another claim."""

    def __init__(self, existing: Mapping[str, Any]):
        self.existing = dict(existing)
        super().__init__(
            "Premium claim operation identity conflicts with the original request: "
            f"user_id={self.existing.get('user_id')!r}, "
            f"operation_id={self.existing.get('operation_id')!r}"
        )


class PremiumClaimOperationInProgress(PremiumClaimOperationError):
    """A committed PENDING operation requires manual reconciliation."""

    def __init__(self, existing: Mapping[str, Any]):
        self.existing = dict(existing)
        super().__init__("Premium claim operation is unexpectedly still pending")


def normalize_claim_operation_id(value: Any) -> tuple[str, bool]:
    """Validate a client proposal or generate a server-bound identity."""

    return normalize_identity(value, field="claim_operation_id", generate_if_missing=True)


def canonical_claim_request(
    *,
    claim_family: str,
    benefit_period_key: str | None,
    requested_reward_id: str | None,
) -> dict[str, Any]:
    """Return only server-relevant identity fields for fingerprinting."""

    return {
        "claim_family": str(claim_family).strip(),
        "benefit_period_key": str(benefit_period_key).strip() if benefit_period_key else None,
        "requested_reward_id": str(requested_reward_id).strip() if requested_reward_id else None,
    }


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


def _timestamp(conn: Any, value: datetime | None = None) -> Any:
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None:
        raise ValueError("claim operation timestamps must be timezone-aware")
    return value.isoformat() if _is_sqlite(conn) else value


def _json_value(conn: Any, payload: Mapping[str, Any]) -> Any:
    if _is_sqlite(conn):
        return json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    from psycopg2.extras import Json

    return Json(dict(payload))


def _row_dict(cursor: Any, row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    if hasattr(row, "keys"):
        result = {str(key): row[key] for key in row.keys()}
    else:
        result = {str(item[0]): row[index] for index, item in enumerate(cursor.description)}
    if isinstance(result.get("result_payload"), str):
        try:
            result["result_payload"] = json.loads(result["result_payload"])
        except (TypeError, ValueError):
            result["result_payload"] = {}
    return result


def get_claim_operation(
    conn: Any,
    *,
    user_id: int,
    operation_id: str,
) -> dict[str, Any] | None:
    cursor = _execute(
        conn,
        f"""SELECT operation_id,user_id,claim_family,request_fingerprint,
                    benefit_period_key,reward_id,operation_status,result_payload,
                    claim_id,created_at,committed_at
               FROM {TABLE_NAME}
              WHERE user_id=? AND operation_id=?""",
        (user_id, operation_id),
    )
    try:
        return _row_dict(cursor, cursor.fetchone())
    finally:
        if not hasattr(conn, "execute"):
            cursor.close()


def reserve_claim_operation(
    conn: Any,
    *,
    user_id: int,
    operation_id: str,
    claim_family: str,
    benefit_period_key: str | None,
    requested_reward_id: str | None,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    """Reserve/recover one operation inside the caller-owned transaction."""

    payload = canonical_claim_request(
        claim_family=claim_family,
        benefit_period_key=benefit_period_key,
        requested_reward_id=requested_reward_id,
    )
    fingerprint = canonical_payload_digest(payload)
    cursor = _execute(
        conn,
        f"""INSERT INTO {TABLE_NAME}(
                    operation_id,user_id,claim_family,request_fingerprint,
                    benefit_period_key,reward_id,operation_status,result_payload,
                    claim_id,created_at,committed_at)
                VALUES(?,?,?,?,?,?,? ,?,NULL,?,NULL)
                ON CONFLICT(user_id,operation_id) DO NOTHING""",
        (
            operation_id,
            user_id,
            claim_family,
            fingerprint,
            benefit_period_key,
            requested_reward_id,
            "PENDING",
            _json_value(conn, {}),
            _timestamp(conn, created_at),
        ),
    )
    inserted = int(getattr(cursor, "rowcount", 0) or 0) == 1
    existing = get_claim_operation(conn, user_id=user_id, operation_id=operation_id)
    if existing is None:
        raise PremiumClaimOperationError("claim operation reservation is not recoverable")
    if (
        existing.get("claim_family") != claim_family
        or existing.get("request_fingerprint") != fingerprint
    ):
        raise PremiumClaimOperationConflict(existing)
    status = str(existing.get("operation_status") or "")
    if status not in CLAIM_OPERATION_STATUSES:
        raise PremiumClaimOperationError("claim operation has unsupported status")
    if status == "PENDING" and not inserted:
        raise PremiumClaimOperationInProgress(existing)
    return {
        "inserted": inserted,
        "duplicate": not inserted,
        "operation": existing,
        "request_payload": payload,
        "request_fingerprint": fingerprint,
    }


def complete_claim_operation(
    conn: Any,
    *,
    user_id: int,
    operation_id: str,
    operation_status: str,
    result_payload: Mapping[str, Any],
    benefit_period_key: str | None,
    reward_id: str | None,
    claim_id: int | None,
    committed_at: datetime | None = None,
) -> dict[str, Any]:
    """Complete a reserved operation without committing or rolling back."""

    if operation_status not in CLAIM_OPERATION_STATUSES or operation_status == "PENDING":
        raise ValueError("operation_status must be terminal")
    cursor = _execute(
        conn,
        f"""UPDATE {TABLE_NAME}
               SET operation_status=?, result_payload=?, benefit_period_key=?,
                   reward_id=?, claim_id=?, committed_at=?
             WHERE user_id=? AND operation_id=? AND operation_status='PENDING'""",
        (
            operation_status,
            _json_value(conn, result_payload),
            benefit_period_key,
            reward_id,
            claim_id,
            _timestamp(conn, committed_at),
            user_id,
            operation_id,
        ),
    )
    if int(getattr(cursor, "rowcount", 0) or 0) != 1:
        existing = get_claim_operation(conn, user_id=user_id, operation_id=operation_id)
        if existing and existing.get("operation_status") != "PENDING":
            return existing
        raise PremiumClaimOperationError("claim operation was not completed")
    result = get_claim_operation(conn, user_id=user_id, operation_id=operation_id)
    if result is None:
        raise PremiumClaimOperationError("completed claim operation is not recoverable")
    return result


__all__ = [
    "CLAIM_FAMILY",
    "PremiumClaimOperationConflict",
    "PremiumClaimOperationError",
    "PremiumClaimOperationInProgress",
    "canonical_claim_request",
    "complete_claim_operation",
    "get_claim_operation",
    "normalize_claim_operation_id",
    "reserve_claim_operation",
]
