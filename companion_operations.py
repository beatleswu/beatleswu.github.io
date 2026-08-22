"""Durable, server-owned operation authority for Companion mutations.

The operation row in ``companion_operations`` is the correctness authority
for unlock/feed/train/switch/evolve.  D5A remains evidence/lineage and D5C
remains the business authority for a consumed functional item.  All helpers
use the caller's transaction and deliberately never commit or roll back.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any

from migrations.companion_operations_v1 import (
    OPERATION_STATUSES,
    TABLE_NAME,
)
from migrations.spirit_evolution_events_v1 import TABLE_NAME as EVOLUTION_TABLE_NAME
from spirit_lineage import (
    SpiritContractError,
    append_spirit_reward_event,
    build_evolution_transitions,
    canonical_companion_payload,
    companion_request_fingerprint,
    evolution_stage_for_level,
    normalize_companion_operation_id,
    validate_evolution_event,
)


COMPANION_OPERATION_TYPES = (
    "SPIRIT_UNLOCK",
    "SPIRIT_FEED",
    "SPIRIT_TRAIN",
    "SPIRIT_SWITCH",
    "SPIRIT_EVOLVE",
)
COMPANION_POLICY_VERSION = "E10_COMPANION_OPERATION_V1"
_LINEAGE_OPERATION_TYPES = {
    "SPIRIT_UNLOCK": "UNLOCK",
    "SPIRIT_FEED": "ITEM_USE",
    "SPIRIT_TRAIN": "TRAIN",
    "SPIRIT_SWITCH": "SWITCH",
    "SPIRIT_EVOLVE": "EVOLUTION",
}
_TERMINAL_STATUSES = frozenset({"COMPLETED", "FAILED"})


class CompanionOperationError(RuntimeError):
    """Base class for fail-closed operation errors."""


class CompanionOperationValidationError(ValueError, CompanionOperationError):
    """The caller proposed an invalid operation identity or payload."""


class CompanionOperationConflict(CompanionOperationError):
    """One operation identity was already bound to another intent."""

    def __init__(self, existing: Mapping[str, Any]):
        self.existing = dict(existing)
        super().__init__(
            "companion operation identity is already bound to a different request: "
            f"user_id={self.existing.get('user_id')!r}, "
            f"operation_id={self.existing.get('operation_id')!r}"
        )


class CompanionOperationInProgress(CompanionOperationError):
    """A committed PENDING row was found; callers must not mutate."""

    def __init__(self, existing: Mapping[str, Any]):
        self.existing = dict(existing)
        super().__init__(
            "companion operation is unexpectedly still pending: "
            f"user_id={self.existing.get('user_id')!r}, "
            f"operation_id={self.existing.get('operation_id')!r}"
        )


class CompanionOperationSchemaUnavailable(CompanionOperationError):
    """The additive schema has not been applied; runtime fails closed."""


class CompanionMutationRejected(CompanionOperationError):
    """A deterministic business rejection that can be safely replayed."""

    def __init__(self, body: Mapping[str, Any], *, status_code: int = 400, error_code: str = "REJECTED"):
        self.body = dict(body)
        self.status_code = int(status_code)
        self.error_code = str(error_code)
        super().__init__(str(self.body.get("error") or self.error_code))


@dataclass(frozen=True)
class CompanionExecution:
    body: dict[str, Any]
    status_code: int
    replayed: bool
    operation_status: str


def _is_sqlite(conn: Any) -> bool:
    raw = getattr(conn, "_conn", conn)
    return raw.__class__.__module__.startswith("sqlite3")


def _json_parameter(conn: Any, payload: Mapping[str, Any]) -> Any:
    if _is_sqlite(conn):
        return json.dumps(dict(payload), ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True)
    from psycopg2.extras import Json

    return Json(dict(payload))


def _timestamp(conn: Any, value: datetime | None = None) -> Any:
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None:
        raise CompanionOperationValidationError("operation timestamps must be timezone-aware")
    return value.isoformat() if _is_sqlite(conn) else value


def _missing_table_error(exc: Exception) -> bool:
    text = str(exc).lower()
    name = exc.__class__.__name__.lower()
    return (
        "no such table" in text
        or "does not exist" in text
        or "undefinedtable" in name
    )


def assert_companion_schema(conn: Any) -> None:
    """Fail closed when the additive migration is not present."""

    try:
        conn.execute(f"SELECT 1 FROM {TABLE_NAME} LIMIT 1").fetchone()
    except Exception as exc:
        if _missing_table_error(exc):
            raise CompanionOperationSchemaUnavailable(
                "companion operation schema is not installed"
            ) from exc
        raise


def _row_to_dict(row: Any, description: Any = None) -> dict[str, Any] | None:
    if row is None:
        return None
    if hasattr(row, "keys"):
        result = {str(key): row[key] for key in row.keys()}
    elif description:
        result = {
            str(column[0]): row[index]
            for index, column in enumerate(description)
        }
    else:
        result = dict(row)
    payload = result.get("result_json")
    if isinstance(payload, str):
        try:
            result["result_json"] = json.loads(payload)
        except (TypeError, ValueError):
            result["result_json"] = {}
    return result


def normalize_operation_id(candidate: Any = None) -> tuple[str, bool]:
    try:
        return normalize_companion_operation_id(candidate)
    except SpiritContractError as exc:
        raise CompanionOperationValidationError(str(exc)) from exc


def build_companion_operation_request(
    *,
    user_id: int,
    operation_type: str,
    operation_id: Any = None,
    spirit_id: str | None = None,
    item_id: str | None = None,
    payload: Mapping[str, Any] | None = None,
    policy_version: str = COMPANION_POLICY_VERSION,
) -> dict[str, Any]:
    """Build the server-defined identity without trusting client results."""

    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
        raise CompanionOperationValidationError("user_id must be a positive authenticated integer")
    operation_type = str(operation_type or "").strip().upper()
    if operation_type not in COMPANION_OPERATION_TYPES:
        raise CompanionOperationValidationError(f"unsupported Companion operation type: {operation_type}")
    operation_id, server_generated = normalize_operation_id(operation_id)
    try:
        lineage_payload = canonical_companion_payload(
            user_id=user_id,
            operation_type=_LINEAGE_OPERATION_TYPES[operation_type],
            spirit_id=spirit_id,
            item_id=item_id,
            policy_version=policy_version,
            payload=payload or {},
        )
        # Include the B023 type explicitly.  The D007 vocabulary remains
        # preserved in the lineage payload, while the durable B023 table
        # stores the exact public operation family.
        identity_payload = {
            "contract": "B023_COMPANION_OPERATION_V1",
            "operation_type": operation_type,
            "lineage_payload": lineage_payload,
        }
        fingerprint = companion_request_fingerprint(identity_payload)
    except SpiritContractError as exc:
        raise CompanionOperationValidationError(str(exc)) from exc
    return {
        "operation_id": operation_id,
        "user_id": user_id,
        "operation_type": operation_type,
        "spirit_id": spirit_id,
        "item_id": item_id,
        "payload_hash": fingerprint,
        "policy_version": policy_version,
        "canonical_payload": identity_payload,
        "server_generated_identity": server_generated,
        "client_identity_is_authority": False,
    }


def get_companion_operation(
    conn: Any,
    *,
    user_id: int,
    operation_id: str,
) -> dict[str, Any] | None:
    assert_companion_schema(conn)
    cursor = conn.execute(
        f"""SELECT user_id, operation_id, operation_type, spirit_id,
                    payload_hash, status, result_json, error_code,
                    policy_version, created_at, updated_at, completed_at
               FROM {TABLE_NAME}
              WHERE user_id=? AND operation_id=?""",
        (user_id, operation_id),
    )
    row = cursor.fetchone()
    return _row_to_dict(row, getattr(cursor, "description", None))


def reserve_companion_operation(
    conn: Any,
    *,
    request: Mapping[str, Any],
    created_at: datetime | None = None,
) -> dict[str, Any]:
    """Reserve one logical operation or recover its existing state."""

    assert_companion_schema(conn)
    user_id = request["user_id"]
    operation_id = request["operation_id"]
    now = _timestamp(conn, created_at)
    cursor = conn.execute(
        f"""INSERT INTO {TABLE_NAME}(
                    user_id, operation_id, operation_type, spirit_id,
                    payload_hash, status, result_json, error_code,
                    policy_version, created_at, updated_at, completed_at
                ) VALUES(?,?,?,?,?,?,?,NULL,?,?,?,NULL)
                ON CONFLICT(user_id, operation_id) DO NOTHING""",
        (
            user_id,
            operation_id,
            request["operation_type"],
            request.get("spirit_id"),
            request["payload_hash"],
            "PENDING",
            _json_parameter(conn, {}),
            request["policy_version"],
            now,
            now,
        ),
    )
    inserted = getattr(cursor, "rowcount", 0) == 1
    existing = get_companion_operation(
        conn,
        user_id=user_id,
        operation_id=operation_id,
    )
    if existing is None:
        raise CompanionOperationError("companion operation reservation was not recoverable")
    if (
        existing.get("operation_type") != request.get("operation_type")
        or existing.get("spirit_id") != request.get("spirit_id")
        or existing.get("payload_hash") != request.get("payload_hash")
        or existing.get("policy_version") != request.get("policy_version")
    ):
        raise CompanionOperationConflict(existing)
    status = str(existing.get("status") or "").upper()
    if not inserted and status == "PENDING":
        raise CompanionOperationInProgress(existing)
    if status not in OPERATION_STATUSES:
        raise CompanionOperationError("companion operation record has an unsupported status")
    return {
        "inserted": inserted,
        "duplicate": not inserted,
        "operation": existing,
        "request": dict(request),
    }


def _result_envelope(body: Mapping[str, Any], status_code: int) -> dict[str, Any]:
    if not isinstance(status_code, int) or isinstance(status_code, bool) or not 100 <= status_code <= 599:
        raise CompanionOperationValidationError("status_code must be an HTTP status")
    normalized = dict(body)
    return {"body": normalized, "status_code": status_code}


def _decode_result(operation: Mapping[str, Any]) -> tuple[dict[str, Any], int]:
    envelope = operation.get("result_json") or {}
    if not isinstance(envelope, Mapping):
        raise CompanionOperationError("committed Companion result is not an object")
    body = envelope.get("body")
    status_code = envelope.get("status_code")
    if not isinstance(body, Mapping) or not isinstance(status_code, int):
        raise CompanionOperationError("committed Companion result envelope is invalid")
    return dict(body), status_code


def complete_companion_operation(
    conn: Any,
    *,
    user_id: int,
    operation_id: str,
    status: str,
    body: Mapping[str, Any],
    status_code: int,
    error_code: str | None = None,
    completed_at: datetime | None = None,
) -> dict[str, Any]:
    status = str(status or "").upper()
    if status not in _TERMINAL_STATUSES:
        raise CompanionOperationValidationError("operation must complete as COMPLETED or FAILED")
    now = _timestamp(conn, completed_at)
    cursor = conn.execute(
        f"""UPDATE {TABLE_NAME}
               SET status=?, result_json=?, error_code=?,
                   updated_at=?, completed_at=?
             WHERE user_id=? AND operation_id=? AND status='PENDING'""",
        (
            status,
            _json_parameter(conn, _result_envelope(body, status_code)),
            error_code,
            now,
            now,
            user_id,
            operation_id,
        ),
    )
    if getattr(cursor, "rowcount", 0) != 1:
        raise CompanionOperationError("companion operation was not pending")
    result = get_companion_operation(conn, user_id=user_id, operation_id=operation_id)
    if result is None:
        raise CompanionOperationError("completed Companion operation was not recoverable")
    return result


def execute_companion_operation(
    conn: Any,
    *,
    user_id: int,
    operation_type: str,
    operation_id: Any = None,
    spirit_id: str | None = None,
    item_id: str | None = None,
    payload: Mapping[str, Any] | None = None,
    policy_version: str = COMPANION_POLICY_VERSION,
    mutation: Callable[[Any, str], tuple[Mapping[str, Any], int]],
) -> CompanionExecution:
    """Run one mutation inside one caller-owned transaction.

    A terminal row is replayed without invoking ``mutation``.  A deterministic
    domain rejection is persisted as FAILED so the same request receives the
    same result.  Unexpected exceptions are intentionally allowed to escape;
    the caller's transaction context then rolls back reservation and mutation.
    """

    request = build_companion_operation_request(
        user_id=user_id,
        operation_type=operation_type,
        operation_id=operation_id,
        spirit_id=spirit_id,
        item_id=item_id,
        payload=payload,
        policy_version=policy_version,
    )
    reservation = reserve_companion_operation(conn, request=request)
    if not reservation["inserted"]:
        body, status_code = _decode_result(reservation["operation"])
        return CompanionExecution(
            body=body,
            status_code=status_code,
            replayed=True,
            operation_status=str(reservation["operation"]["status"]).upper(),
        )

    operation_id = str(request["operation_id"])
    try:
        body, status_code = mutation(conn, operation_id)
        if not isinstance(body, Mapping):
            raise CompanionOperationError("Companion mutation must return a JSON object")
        body = dict(body)
        body.setdefault("operation_id", operation_id)
        completed = complete_companion_operation(
            conn,
            user_id=user_id,
            operation_id=operation_id,
            status="COMPLETED",
            body=body,
            status_code=status_code,
        )
        replay_body, replay_status = _decode_result(completed)
        return CompanionExecution(
            body=replay_body,
            status_code=replay_status,
            replayed=False,
            operation_status="COMPLETED",
        )
    except CompanionMutationRejected as exc:
        body = dict(exc.body)
        body.setdefault("operation_id", operation_id)
        completed = complete_companion_operation(
            conn,
            user_id=user_id,
            operation_id=operation_id,
            status="FAILED",
            body=body,
            status_code=exc.status_code,
            error_code=exc.error_code,
        )
        replay_body, replay_status = _decode_result(completed)
        return CompanionExecution(
            body=replay_body,
            status_code=replay_status,
            replayed=False,
            operation_status="FAILED",
        )


def _select_pet_for_update(conn: Any, user_id: int, spirit_id: str) -> Any:
    suffix = "" if _is_sqlite(conn) else " FOR UPDATE"
    return conn.execute(
        f"SELECT * FROM user_pets WHERE user_id=? AND pet_key=?{suffix}",
        (user_id, spirit_id),
    ).fetchone()


def commit_evolution_transition(
    conn: Any,
    *,
    user_id: int,
    operation_id: Any,
    spirit_id: str,
    from_level: int,
    to_level: int,
    source: str,
    policy_version: str = COMPANION_POLICY_VERSION,
) -> CompanionExecution:
    """Persist one server-derived transition for D008.

    ``from_level``, ``to_level``, and ``source`` are internal inputs from a
    server policy caller.  The function re-checks the current authoritative
    Spirit row and rejects direct multi-stage jumps.  It does not accept a
    client-proposed final stage and does not change progression balance.
    """

    if isinstance(from_level, bool) or not isinstance(from_level, int):
        raise CompanionOperationValidationError("from_level must be an integer")
    if isinstance(to_level, bool) or not isinstance(to_level, int):
        raise CompanionOperationValidationError("to_level must be an integer")
    payload = {
        "from_level": from_level,
        "to_level": to_level,
        "source": str(source or "").strip(),
    }

    def mutate(inner_conn: Any, op_id: str) -> tuple[Mapping[str, Any], int]:
        pet = _select_pet_for_update(inner_conn, user_id, spirit_id)
        if not pet:
            pet = inner_conn.execute(
                "SELECT * FROM pet_collection WHERE user_id=? AND pet_key=?",
                (user_id, spirit_id),
            ).fetchone()
        if not pet:
            raise CompanionMutationRejected(
                {"ok": False, "error": "尚未擁有此棋靈"},
                status_code=403,
                error_code="UNOWNED_SPIRIT",
            )
        current_level = max(1, int(pet["level"] or 1))
        if current_level != from_level:
            raise CompanionMutationRejected(
                {"ok": False, "error": "棋靈狀態已更新，請重新計算進化"},
                status_code=409,
                error_code="STALE_SPIRIT_LEVEL",
            )
        lineage_id = f"companion:{user_id}:{op_id}"
        transitions = build_evolution_transitions(
            user_id=user_id,
            spirit_id=spirit_id,
            from_level=from_level,
            to_level=to_level,
            operation_id=op_id,
            lineage_id=lineage_id,
            source=payload["source"],
            policy_version=policy_version,
        )
        if len(transitions) != 1 or not validate_evolution_event(transitions[0]):
            raise CompanionMutationRejected(
                {"ok": False, "error": "進化只能由伺服器逐階確認"},
                status_code=400,
                error_code="INVALID_EVOLUTION_TRANSITION",
            )
        event = transitions[0]
        inserted = inner_conn.execute(
            f"""INSERT INTO {EVOLUTION_TABLE_NAME}(
                        event_id, user_id, spirit_id, operation_id,
                        from_stage, to_stage, from_level, to_level,
                        source, policy_version, created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(user_id, spirit_id, from_stage, to_stage, from_level, to_level)
                    DO NOTHING""",
            (
                event["event_id"],
                user_id,
                spirit_id,
                op_id,
                event["from_stage"],
                event["to_stage"],
                event["from_level"],
                event["to_level"],
                event["source"],
                event["policy_version"],
                _timestamp(inner_conn),
            ),
        )
        if getattr(inserted, "rowcount", 0) != 1:
            raise CompanionMutationRejected(
                {"ok": False, "error": "此進化轉換已完成"},
                status_code=409,
                error_code="EVOLUTION_ALREADY_COMMITTED",
            )
        return {
            "ok": True,
            "status": "SUCCESS",
            "event_id": event["event_id"],
            "spirit_id": spirit_id,
            "from_stage": event["from_stage"],
            "to_stage": event["to_stage"],
            "from_level": event["from_level"],
            "to_level": event["to_level"],
            "client_can_set_evolution": False,
        }, 200

    return execute_companion_operation(
        conn,
        user_id=user_id,
        operation_type="SPIRIT_EVOLVE",
        operation_id=operation_id,
        spirit_id=spirit_id,
        payload=payload,
        policy_version=policy_version,
        mutation=mutate,
    )


__all__ = [
    "COMPANION_OPERATION_TYPES",
    "COMPANION_POLICY_VERSION",
    "CompanionExecution",
    "CompanionMutationRejected",
    "CompanionOperationConflict",
    "CompanionOperationError",
    "CompanionOperationInProgress",
    "CompanionOperationSchemaUnavailable",
    "CompanionOperationValidationError",
    "assert_companion_schema",
    "build_companion_operation_request",
    "commit_evolution_transition",
    "complete_companion_operation",
    "execute_companion_operation",
    "get_companion_operation",
    "normalize_operation_id",
    "reserve_companion_operation",
]
