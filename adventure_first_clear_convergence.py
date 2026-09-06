"""Durable receipt primitives for Adventure Lord first-clear projection.

The authoritative Boss clear, first-clear reward, and Spirit settlement keep
their existing transaction boundary.  This module only records an immutable
receipt in the already deployed D5A outbox.  A second immutable event marks
the receipt complete after the separate Zone-star transaction commits.

There is intentionally no update/delete operation here.  ``UNKNOWN`` is the
durable pending marker, ``FAILED`` events are bounded diagnostics, and a
deterministic ``SUCCESS`` completion event is the convergence proof.  The
append-only shape means a request crash cannot erase the work that remains.
"""

from __future__ import annotations

from collections.abc import Mapping
import json
import re
from typing import Any

from event_outbox import (
    DuplicateOutboxEvent,
    append_event,
    get_event_by_idempotency_key,
)
from migrations.domain_event_outbox_v1 import TABLE_NAME


FIRST_CLEAR_PROJECTION_EVENT_TYPE = "ADVENTURE_FIRST_CLEAR_PROJECTION"
RECEIPT_SCHEMA_VERSION = "adventure_first_clear_projection_receipt_v1"
PENDING_OUTCOME = "UNKNOWN"
COMPLETED_OUTCOME = "SUCCESS"
FAILED_OUTCOME = "FAILED"
_RECEIPT_KEY_PREFIX = "adventure:first-clear-projection:"
_PENDING_SUFFIX = ":pending"
_COMPLETE_SUFFIX = ":complete"
_FAILURE_MARKER = ":failure:"


class FirstClearProjectionReceiptError(RuntimeError):
    """Base class for receipt failures that must remain observable."""


class FirstClearProjectionReceiptSchemaUnavailable(
    FirstClearProjectionReceiptError
):
    """The pre-existing D5A outbox is not available on this connection."""


def _normalize_zone_key(zone_key: Any) -> str:
    normalized = str(zone_key or "").strip()
    if not normalized:
        raise ValueError("zone_key is required")
    return normalized


def _uid_text(user_id: Any) -> str:
    try:
        return str(int(user_id))
    except (TypeError, ValueError) as exc:
        raise ValueError("user_id must be an integer") from exc


def pending_idempotency_key(user_id: Any, zone_key: Any) -> str:
    return (
        f"{_RECEIPT_KEY_PREFIX}{_uid_text(user_id)}:"
        f"{_normalize_zone_key(zone_key)}{_PENDING_SUFFIX}"
    )


def completion_idempotency_key(user_id: Any, zone_key: Any) -> str:
    return pending_idempotency_key(user_id, zone_key)[:-len(_PENDING_SUFFIX)] + _COMPLETE_SUFFIX


def failure_idempotency_key(user_id: Any, zone_key: Any, error_code: Any) -> str:
    normalized_code = re.sub(r"[^a-z0-9_.-]+", "_", str(error_code or "unknown").lower()).strip("_")
    normalized_code = normalized_code[:80] or "unknown"
    return (
        pending_idempotency_key(user_id, zone_key)[:-len(_PENDING_SUFFIX)]
        + _FAILURE_MARKER
        + normalized_code
    )


def _outbox_connection(conn: Any) -> Any:
    """Return a connection shape accepted by the shared outbox helper.

    Production uses ``PostgresConnectionWrapper``.  A few focused route tests
    wrap a SQLite connection with only ``execute`` and context-manager methods;
    its raw connection is still the same transaction and is safe to pass to
    the caller-owned outbox writer.
    """

    if callable(getattr(conn, "cursor", None)) and callable(getattr(conn, "execute", None)):
        return conn
    raw = getattr(conn, "_conn", None)
    if callable(getattr(raw, "cursor", None)) and callable(getattr(raw, "execute", None)):
        return raw
    raise FirstClearProjectionReceiptSchemaUnavailable(
        "domain_event_outbox connection adapter is unavailable"
    )


def ensure_receipt_schema(conn: Any) -> None:
    """Fail closed when the already governed D5A outbox is absent."""

    try:
        cursor = conn.execute(f"SELECT event_id FROM {TABLE_NAME} LIMIT 0")
        close = getattr(cursor, "close", None)
        if callable(close):
            close()
        _outbox_connection(conn)
    except FirstClearProjectionReceiptSchemaUnavailable:
        raise
    except Exception as exc:
        raise FirstClearProjectionReceiptSchemaUnavailable(
            "domain_event_outbox is unavailable"
        ) from exc


def _event_payload(event: Mapping[str, Any] | None) -> dict[str, Any]:
    if not event:
        return {}
    payload = event.get("payload")
    if isinstance(payload, Mapping):
        return dict(payload)
    if isinstance(payload, str):
        try:
            decoded = json.loads(payload)
        except (TypeError, ValueError):
            return {}
        return dict(decoded) if isinstance(decoded, Mapping) else {}
    return {}


def _append_receipt_event(
    conn: Any,
    *,
    user_id: Any,
    zone_key: Any,
    operation_id: Any,
    idempotency_key: str,
    outcome: str,
    payload: Mapping[str, Any],
    occurred_at: Any,
) -> dict[str, Any]:
    ensure_receipt_schema(conn)
    outbox_conn = _outbox_connection(conn)
    try:
        return append_event(
            outbox_conn,
            event_type=FIRST_CLEAR_PROJECTION_EVENT_TYPE,
            player_id=_uid_text(user_id),
            lineage_id=str(operation_id),
            source_event_id=str(operation_id),
            idempotency_key=idempotency_key,
            outcome=outcome,
            payload=dict(payload),
            occurred_at=occurred_at,
        )
    except DuplicateOutboxEvent as duplicate:
        event = dict(duplicate.existing_event)
        event["duplicate"] = True
        return event


def record_pending_receipt(
    conn: Any,
    *,
    user_id: Any,
    zone_key: Any,
    operation_id: Any,
    occurred_at: Any,
) -> dict[str, Any]:
    """Record the durable obligation in the core first-clear transaction."""

    zone_key = _normalize_zone_key(zone_key)
    operation_id = str(operation_id or "").strip()
    if not operation_id:
        raise ValueError("operation_id is required")
    key = pending_idempotency_key(user_id, zone_key)
    payload = {
        "schema": RECEIPT_SCHEMA_VERSION,
        "kind": "lord_first_clear_projection",
        "status": "PENDING",
        "user_id": int(user_id),
        "zone_key": zone_key,
        "operation_id": operation_id,
        "projection": "zone_star_and_next_zone_unlock",
    }
    event = _append_receipt_event(
        conn,
        user_id=user_id,
        zone_key=zone_key,
        operation_id=operation_id,
        idempotency_key=key,
        outcome=PENDING_OUTCOME,
        payload=payload,
        occurred_at=occurred_at,
    )
    return {
        "receipt_event_id": event.get("event_id"),
        "receipt_key": key,
        "operation_id": operation_id,
        "zone_key": zone_key,
        "status": "PENDING",
        "duplicate": bool(event.get("duplicate")),
    }


def record_completion(
    conn: Any,
    *,
    user_id: Any,
    zone_key: Any,
    operation_id: Any,
    occurred_at: Any,
    projection: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Append the deterministic completion proof after projection commit."""

    zone_key = _normalize_zone_key(zone_key)
    key = completion_idempotency_key(user_id, zone_key)
    payload = {
        "schema": RECEIPT_SCHEMA_VERSION,
        "kind": "lord_first_clear_projection",
        "status": "COMPLETED",
        "user_id": int(user_id),
        "zone_key": zone_key,
        "operation_id": str(operation_id),
        "projection": "zone_star_and_next_zone_unlock",
        "projection_result": dict(projection or {}),
    }
    event = _append_receipt_event(
        conn,
        user_id=user_id,
        zone_key=zone_key,
        operation_id=operation_id,
        idempotency_key=key,
        outcome=COMPLETED_OUTCOME,
        payload=payload,
        occurred_at=occurred_at,
    )
    return {
        "completion_event_id": event.get("event_id"),
        "receipt_key": pending_idempotency_key(user_id, zone_key),
        "completion_key": key,
        "operation_id": str(operation_id),
        "zone_key": zone_key,
        "status": "COMPLETED",
        "duplicate": bool(event.get("duplicate")),
    }


def record_failure(
    conn: Any,
    *,
    user_id: Any,
    zone_key: Any,
    operation_id: Any,
    error_code: Any,
    occurred_at: Any,
) -> dict[str, Any]:
    """Append one bounded, deterministic diagnostic for a pending receipt."""

    zone_key = _normalize_zone_key(zone_key)
    key = failure_idempotency_key(user_id, zone_key, error_code)
    normalized_code = key.rsplit(_FAILURE_MARKER, 1)[-1]
    payload = {
        "schema": RECEIPT_SCHEMA_VERSION,
        "kind": "lord_first_clear_projection",
        "status": "PENDING",
        "diagnostic": "PROJECTION_FAILURE",
        "error_code": normalized_code,
        "user_id": int(user_id),
        "zone_key": zone_key,
        "operation_id": str(operation_id),
    }
    event = _append_receipt_event(
        conn,
        user_id=user_id,
        zone_key=zone_key,
        operation_id=operation_id,
        idempotency_key=key,
        outcome=FAILED_OUTCOME,
        payload=payload,
        occurred_at=occurred_at,
    )
    return {
        "diagnostic_event_id": event.get("event_id"),
        "diagnostic_key": key,
        "error_code": normalized_code,
        "status": "PENDING",
        "duplicate": bool(event.get("duplicate")),
    }


def _read_event(conn: Any, *, user_id: Any, key: str) -> dict[str, Any] | None:
    ensure_receipt_schema(conn)
    return get_event_by_idempotency_key(
        _outbox_connection(conn),
        player_id=_uid_text(user_id),
        event_type=FIRST_CLEAR_PROJECTION_EVENT_TYPE,
        idempotency_key=key,
    )


def completion_exists(conn: Any, *, user_id: Any, zone_key: Any) -> bool:
    return _read_event(
        conn,
        user_id=user_id,
        key=completion_idempotency_key(user_id, zone_key),
    ) is not None


def pending_receipts(conn: Any, *, user_id: Any) -> list[dict[str, Any]]:
    """Load immutable pending obligations for one authenticated player."""

    ensure_receipt_schema(conn)
    rows = conn.execute(
        f"""SELECT event_id, idempotency_key, payload, occurred_at, created_at
              FROM {TABLE_NAME}
             WHERE player_id=? AND event_type=? AND outcome=?
             ORDER BY created_at, event_id""",
        (_uid_text(user_id), FIRST_CLEAR_PROJECTION_EVENT_TYPE, PENDING_OUTCOME),
    ).fetchall()
    prefix = f"{_RECEIPT_KEY_PREFIX}{_uid_text(user_id)}:"
    receipts: list[dict[str, Any]] = []
    for row in rows:
        if hasattr(row, "keys"):
            raw = {str(key): row[key] for key in row.keys()}
        else:
            raw = dict(row)
        key = str(raw.get("idempotency_key") or "")
        if not key.startswith(prefix) or not key.endswith(_PENDING_SUFFIX):
            continue
        payload = _event_payload(raw)
        zone_key = str(payload.get("zone_key") or "").strip()
        operation_id = str(payload.get("operation_id") or "").strip()
        if not zone_key or not operation_id:
            raise FirstClearProjectionReceiptError(
                "pending first-clear receipt payload is malformed"
            )
        receipts.append(
            {
                "receipt_event_id": raw.get("event_id"),
                "receipt_key": key,
                "zone_key": zone_key,
                "operation_id": operation_id,
                "status": "PENDING",
                "occurred_at": raw.get("occurred_at"),
                "created_at": raw.get("created_at"),
                "payload": payload,
            }
        )
    return receipts


__all__ = [
    "COMPLETED_OUTCOME",
    "FAILED_OUTCOME",
    "FIRST_CLEAR_PROJECTION_EVENT_TYPE",
    "FirstClearProjectionReceiptError",
    "FirstClearProjectionReceiptSchemaUnavailable",
    "PENDING_OUTCOME",
    "completion_exists",
    "completion_idempotency_key",
    "failure_idempotency_key",
    "pending_idempotency_key",
    "pending_receipts",
    "record_completion",
    "record_failure",
    "record_pending_receipt",
    "ensure_receipt_schema",
]
