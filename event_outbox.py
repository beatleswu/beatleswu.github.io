"""Server-internal caller-owned writer for D5A outbox evidence.

The helper deliberately has no commit, rollback, begin, publisher, or public
HTTP surface.  A business caller must pass its existing connection/session so
the state mutation and evidence row share one transaction boundary.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import json
import uuid
from typing import Any

from migrations.domain_event_outbox_v1 import EVENT_TYPES, OUTCOMES, TABLE_NAME


_FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {
        "card_number",
        "cvv",
        "cvc",
        "password",
        "provider_credentials",
        "raw_callback_body",
        "raw_payload",
        "secret",
        "session_secret",
        "token",
    }
)


class OutboxError(RuntimeError):
    """Base class for server-internal outbox errors."""


class OutboxValidationError(ValueError, OutboxError):
    """The caller supplied an invalid envelope or payload."""


class DuplicateOutboxEvent(OutboxError):
    """The logical event already exists and the original is recoverable."""

    def __init__(self, existing_event: dict[str, Any], *, cause: Exception | None = None):
        self.existing_event = existing_event
        self.existing_event_id = existing_event.get("event_id")
        message = (
            "duplicate outbox event for "
            f"player_id={existing_event.get('player_id')!r}, "
            f"event_type={existing_event.get('event_type')!r}, "
            f"idempotency_key={existing_event.get('idempotency_key')!r}; "
            f"existing_event_id={self.existing_event_id!r}"
        )
        super().__init__(message)
        self.__cause__ = cause


def _is_sqlite(conn: Any) -> bool:
    raw = getattr(conn, "_conn", conn)
    return raw.__class__.__module__.startswith("sqlite3")


def _normalize_required_text(value: Any, field: str) -> str:
    if value is None:
        raise OutboxValidationError(f"{field} is required")
    normalized = str(value).strip()
    if not normalized:
        raise OutboxValidationError(f"{field} must not be empty")
    return normalized


def _coerce_timestamp(value: Any, field: str, *, sqlite: bool) -> Any:
    if value is None:
        value = datetime.now(timezone.utc)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise OutboxValidationError(f"{field} must be timezone-aware")
        return value.isoformat() if sqlite else value
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise OutboxValidationError(f"{field} must be an ISO timestamp or datetime")


def _validate_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise OutboxValidationError("payload must be a mapping")
    normalized = dict(payload)
    def check_keys(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                normalized_key = str(key).strip().lower()
                if normalized_key in _FORBIDDEN_PAYLOAD_KEYS:
                    raise OutboxValidationError(
                        f"payload contains forbidden sensitive field: {key}"
                    )
                check_keys(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                check_keys(child)

    check_keys(normalized)
    try:
        json.dumps(normalized, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise OutboxValidationError("payload must be JSON serializable") from exc
    return normalized


def _payload_parameter(payload: dict[str, Any], *, sqlite: bool) -> Any:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    if sqlite:
        return encoded
    from psycopg2.extras import Json

    return Json(payload)


def _row_to_dict(row: Any, description: Any = None) -> dict[str, Any]:
    if row is None:
        return {}
    if hasattr(row, "keys"):
        result = {str(key): row[key] for key in row.keys()}
    elif description:
        result = {str(column[0]): row[index] for index, column in enumerate(description)}
    else:
        result = dict(row)
    if isinstance(result.get("payload"), str):
        try:
            result["payload"] = json.loads(result["payload"])
        except (TypeError, ValueError):
            pass
    return result


def _find_existing(
    conn: Any,
    *,
    player_id: str,
    event_type: str,
    idempotency_key: str,
) -> dict[str, Any] | None:
    cursor = conn.cursor()
    try:
        cursor.execute(
            f"""SELECT event_id, schema_version, event_type, player_id,
                       occurred_at, lineage_id, source_event_id,
                       idempotency_key, outcome, payload, created_at,
                       published_at
                  FROM {TABLE_NAME}
                 WHERE player_id=? AND event_type=? AND idempotency_key=?""",
            (player_id, event_type, idempotency_key),
        )
        row = cursor.fetchone()
        return _row_to_dict(row, cursor.description) if row is not None else None
    finally:
        cursor.close()


def append_event(
    conn: Any,
    *,
    event_type: str,
    player_id: Any,
    lineage_id: Any,
    idempotency_key: Any,
    outcome: str,
    payload: Mapping[str, Any],
    schema_version: int = 1,
    source_event_id: Any = None,
    occurred_at: Any = None,
) -> dict[str, Any]:
    """Append one event using the caller's open transaction.

    ``event_id`` is always generated on the server.  The helper does not
    accept a client event ID and never commits or rolls back the caller's
    transaction.  A duplicate logical event raises ``DuplicateOutboxEvent``
    after recovering the original row through a savepoint.
    """
    if event_type not in EVENT_TYPES:
        raise OutboxValidationError(f"unsupported event_type: {event_type!r}")
    if outcome not in OUTCOMES:
        raise OutboxValidationError(f"unsupported outcome: {outcome!r}")
    if not isinstance(schema_version, int) or isinstance(schema_version, bool) or schema_version < 1:
        raise OutboxValidationError("schema_version must be a positive integer")

    player_id = _normalize_required_text(player_id, "player_id")
    lineage_id = _normalize_required_text(lineage_id, "lineage_id")
    idempotency_key = _normalize_required_text(idempotency_key, "idempotency_key")
    if source_event_id is not None:
        source_event_id = _normalize_required_text(source_event_id, "source_event_id")
    payload = _validate_payload(payload)

    sqlite = _is_sqlite(conn)
    now = datetime.now(timezone.utc)
    occurred_at = _coerce_timestamp(occurred_at or now, "occurred_at", sqlite=sqlite)
    created_at = _coerce_timestamp(now, "created_at", sqlite=sqlite)
    event_id = str(uuid.uuid4())
    savepoint = f"d5a_outbox_{uuid.uuid4().hex}"

    conn.execute(f"SAVEPOINT {savepoint}")
    try:
        conn.execute(
            f"""INSERT INTO {TABLE_NAME} (
                    event_id, schema_version, event_type, player_id,
                    occurred_at, lineage_id, source_event_id,
                    idempotency_key, outcome, payload, created_at,
                    published_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)""",
            (
                event_id,
                schema_version,
                event_type,
                player_id,
                occurred_at,
                lineage_id,
                source_event_id,
                idempotency_key,
                outcome,
                _payload_parameter(payload, sqlite=sqlite),
                created_at,
            ),
        )
        conn.execute(f"RELEASE SAVEPOINT {savepoint}")
    except Exception as exc:
        conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
        existing = _find_existing(
            conn,
            player_id=player_id,
            event_type=event_type,
            idempotency_key=idempotency_key,
        )
        conn.execute(f"RELEASE SAVEPOINT {savepoint}")
        if existing is not None:
            raise DuplicateOutboxEvent(existing, cause=exc) from exc
        raise

    return {
        "event_id": event_id,
        "schema_version": schema_version,
        "event_type": event_type,
        "player_id": player_id,
        "occurred_at": occurred_at,
        "lineage_id": lineage_id,
        "source_event_id": source_event_id,
        "idempotency_key": idempotency_key,
        "outcome": outcome,
        "payload": payload,
        "created_at": created_at,
        "published_at": None,
        "duplicate": False,
    }


def get_event_by_idempotency_key(
    conn: Any,
    *,
    player_id: Any,
    event_type: str,
    idempotency_key: Any,
) -> dict[str, Any] | None:
    """Read the original event without mutating or committing the transaction."""
    player_id = _normalize_required_text(player_id, "player_id")
    idempotency_key = _normalize_required_text(idempotency_key, "idempotency_key")
    if event_type not in EVENT_TYPES:
        raise OutboxValidationError(f"unsupported event_type: {event_type!r}")
    return _find_existing(
        conn,
        player_id=player_id,
        event_type=event_type,
        idempotency_key=idempotency_key,
    )


__all__ = [
    "DuplicateOutboxEvent",
    "OutboxError",
    "OutboxValidationError",
    "append_event",
    "get_event_by_idempotency_key",
]
