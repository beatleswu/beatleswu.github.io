"""Server-internal durable identity for item-use business operations.

This module owns request reservation and deterministic result replay.  It is
deliberately separate from :mod:`event_outbox`: the operation row is the
business correctness authority, while the outbox is evidence/lineage only.
All functions use the caller's open connection and never commit or roll back.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Mapping

from migrations.item_use_operations_v1 import (
    OPERATION_FAMILY,
    OPERATION_STATUSES,
    TABLE_NAME,
)
from question_idempotency import normalize_identity


class ItemUseOperationError(RuntimeError):
    """Base class for fail-closed operation identity errors."""


class ItemUseOperationConflict(ItemUseOperationError):
    """An existing identity was bound to a different logical request."""

    def __init__(self, existing: Mapping[str, Any]):
        self.existing = dict(existing)
        super().__init__(
            "item-use operation identity is already bound to a different request: "
            f"player_id={self.existing.get('player_id')!r}, "
            f"operation_id={self.existing.get('operation_id')!r}"
        )


class ItemUseOperationInProgress(ItemUseOperationError):
    """A committed PENDING row was found; callers must fail closed."""

    def __init__(self, existing: Mapping[str, Any]):
        self.existing = dict(existing)
        super().__init__(
            "item-use operation is unexpectedly still pending: "
            f"player_id={self.existing.get('player_id')!r}, "
            f"operation_id={self.existing.get('operation_id')!r}"
        )


def normalize_operation_identity(candidate: Any) -> tuple[str, bool]:
    """Validate a client proposal or generate a server-bound identity.

    The returned value is only a request identity.  Ownership, eligibility,
    effect definitions, and mutation correctness remain server-authoritative.
    """

    return normalize_identity(
        candidate,
        field="operation_id",
        generate_if_missing=True,
    )


def canonical_item_use_request(
    *,
    item_id: str,
    action: str = "USE",
    quantity: int = 1,
    effect_key: str | None = None,
    effect_value: Any = None,
    effect_minutes: int | None = None,
    source: str = "SHOP_USE",
) -> dict[str, Any]:
    """Build the server-defined, non-volatile request identity payload.

    Only business inputs that affect the server mutation belong here.  The
    helper intentionally excludes timestamps, HTTP headers, presentation
    fields, and any client-supplied effect values.
    """

    if not isinstance(item_id, str) or not item_id.strip():
        raise ValueError("item_id must be a non-empty string")
    if not isinstance(action, str) or not action.strip():
        raise ValueError("action must be a non-empty string")
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
        raise ValueError("quantity must be a positive integer")
    payload: dict[str, Any] = {
        "action": action.strip(),
        "item_id": item_id.strip(),
        "quantity": quantity,
        "source": source,
    }
    if effect_key is not None:
        payload["effect_key"] = str(effect_key).strip()
    if effect_value is not None:
        payload["effect_value"] = effect_value
    if effect_minutes is not None:
        if isinstance(effect_minutes, bool) or not isinstance(effect_minutes, int) or effect_minutes <= 0:
            raise ValueError("effect_minutes must be a positive integer")
        payload["effect_minutes"] = effect_minutes
    return payload


def request_fingerprint(payload: Mapping[str, Any]) -> str:
    """Return a deterministic SHA-256 digest for a logical request payload."""

    encoded = json.dumps(
        dict(payload),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _is_sqlite(conn: Any) -> bool:
    raw = getattr(conn, "_conn", conn)
    return raw.__class__.__module__.startswith("sqlite3")


def _json_parameter(conn: Any, payload: Mapping[str, Any]) -> Any:
    if _is_sqlite(conn):
        return json.dumps(
            dict(payload),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    from psycopg2.extras import Json

    return Json(dict(payload))


def _timestamp(conn: Any, value: datetime | None = None) -> Any:
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None:
        raise ValueError("operation timestamps must be timezone-aware")
    return value.isoformat() if _is_sqlite(conn) else value


def _row_to_dict(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    if hasattr(row, "keys"):
        result = {str(key): row[key] for key in row.keys()}
    else:
        result = dict(row)
    payload = result.get("result_payload")
    if isinstance(payload, str):
        try:
            result["result_payload"] = json.loads(payload)
        except (TypeError, ValueError):
            result["result_payload"] = {}
    return result


def get_item_use_operation(
    conn: Any,
    *,
    player_id: int,
    operation_id: str,
    operation_family: str = OPERATION_FAMILY,
) -> dict[str, Any] | None:
    """Read one operation without changing transaction ownership."""

    row = conn.execute(
        f"""SELECT operation_id, player_id, operation_family, item_id,
                    request_fingerprint, operation_status, result_payload,
                    created_at, committed_at
               FROM {TABLE_NAME}
              WHERE player_id=? AND operation_family=? AND operation_id=?""",
        (player_id, operation_family, operation_id),
    ).fetchone()
    return _row_to_dict(row)


def reserve_item_use_operation(
    conn: Any,
    *,
    player_id: int,
    operation_id: str,
    item_id: str,
    request_payload: Mapping[str, Any],
    operation_family: str = OPERATION_FAMILY,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    """Reserve or recover one operation inside the caller's transaction.

    ``INSERT ... ON CONFLICT DO NOTHING`` makes the database uniqueness rule
    the concurrency gate for the operation record.  It does not decide
    whether the item may be used; the business caller makes that decision
    after a new reservation is obtained.
    """

    if isinstance(player_id, bool) or not isinstance(player_id, int):
        raise ValueError("player_id must be an authenticated integer")
    if operation_family not in (OPERATION_FAMILY,):
        raise ValueError("unsupported item-use operation family")
    if not isinstance(operation_id, str) or not operation_id.strip():
        raise ValueError("operation_id must be a non-empty validated string")
    if not isinstance(item_id, str) or not item_id.strip():
        raise ValueError("item_id must be a non-empty string")
    payload = dict(request_payload)
    fingerprint = request_fingerprint(payload)
    cursor = conn.execute(
        f"""INSERT INTO {TABLE_NAME}(
                    operation_id, player_id, operation_family, item_id,
                    request_fingerprint, operation_status, result_payload,
                    created_at, committed_at
                ) VALUES(?,?,?,?,?,?,?,?,NULL)
                ON CONFLICT(player_id, operation_family, operation_id)
                DO NOTHING""",
        (
            operation_id,
            player_id,
            operation_family,
            item_id.strip(),
            fingerprint,
            "PENDING",
            _json_parameter(conn, {}),
            _timestamp(conn, created_at),
        ),
    )
    inserted = getattr(cursor, "rowcount", 0) == 1
    existing = get_item_use_operation(
        conn,
        player_id=player_id,
        operation_id=operation_id,
        operation_family=operation_family,
    )
    if existing is None:
        raise ItemUseOperationError("operation reservation was not recoverable")
    if existing["item_id"] != item_id.strip() or existing["request_fingerprint"] != fingerprint:
        raise ItemUseOperationConflict(existing)
    if existing["operation_status"] == "PENDING" and not inserted:
        raise ItemUseOperationInProgress(existing)
    if existing["operation_status"] not in OPERATION_STATUSES:
        raise ItemUseOperationError("operation record has an unsupported status")
    return {
        "inserted": inserted,
        "duplicate": not inserted,
        "operation": existing,
        "request_payload": payload,
        "request_fingerprint": fingerprint,
    }


def complete_item_use_operation(
    conn: Any,
    *,
    player_id: int,
    operation_id: str,
    operation_status: str,
    result_payload: Mapping[str, Any],
    committed_at: datetime | None = None,
    operation_family: str = OPERATION_FAMILY,
) -> dict[str, Any]:
    """Commit a terminal operation result before the caller commits.

    Only a newly reserved PENDING row may be completed.  A duplicate retry
    never calls this function and therefore cannot mutate business state or
    overwrite the original result.
    """

    if operation_status not in OPERATION_STATUSES or operation_status == "PENDING":
        raise ValueError("operation_status must be a terminal supported status")
    cursor = conn.execute(
        f"""UPDATE {TABLE_NAME}
               SET operation_status=?, result_payload=?, committed_at=?
             WHERE player_id=? AND operation_family=? AND operation_id=?
               AND operation_status='PENDING'""",
        (
            operation_status,
            _json_parameter(conn, result_payload),
            _timestamp(conn, committed_at),
            player_id,
            operation_family,
            operation_id,
        ),
    )
    if getattr(cursor, "rowcount", 0) != 1:
        raise ItemUseOperationError("item-use operation was not pending")
    result = get_item_use_operation(
        conn,
        player_id=player_id,
        operation_id=operation_id,
        operation_family=operation_family,
    )
    if result is None:
        raise ItemUseOperationError("completed item-use operation was not recoverable")
    return result


def operation_result(operation: Mapping[str, Any]) -> dict[str, Any]:
    """Return a defensive copy of the server-committed replay payload."""

    payload = operation.get("result_payload") or {}
    if not isinstance(payload, Mapping):
        raise ItemUseOperationError("committed item-use result is not an object")
    return dict(payload)


__all__ = [
    "ItemUseOperationConflict",
    "ItemUseOperationError",
    "ItemUseOperationInProgress",
    "canonical_item_use_request",
    "complete_item_use_operation",
    "get_item_use_operation",
    "normalize_operation_identity",
    "operation_result",
    "request_fingerprint",
    "reserve_item_use_operation",
]
