"""Route-independent Player presentation read service.

The canonical Player/Hero aggregation remains in
``player_state_read_model.build_player_state_read_model``.  This module is
deliberately a thin service boundary for a future API caller: it validates
the caller-owned identity, invokes B028 once, preserves the read-model
authority/provenance, and returns a deterministic JSON-safe envelope.

It does not own a database connection, authentication, Flask state, a
mutation, a Hero selector, World progression, or any combat calculation.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any
from uuid import UUID

import player_state_read_model as _b028


PLAYER_PRESENTATION_READ_CONTRACT_VERSION = "PLAYER_PRESENTATION_READ_CONTRACT_V1"

_B028_STATUS_TO_SERVICE_STATUS = {
    "OK": "OK",
    "PARTIAL": "PARTIAL",
    "OPTIONAL_PROJECTION_UNAVAILABLE": "PARTIAL",
    "INVALID_STORED_STATE": "INVALID_STATE",
    "AUTHORITY_AMBIGUOUS": "INVALID_STATE",
    "AUTHORITY_UNAVAILABLE": "UNAVAILABLE",
}


class PlayerPresentationReadServiceError(RuntimeError):
    """Stable, safe error raised at the service boundary.

    The original exception is intentionally not retained as a public field.
    Callers may log the exception chain server-side, but serialization of
    this object never exposes SQL, filesystem, or traceback details.
    """

    def __init__(self, code: str, status: str, message: str):
        super().__init__(message)
        self.code = code
        self.status = status

    def as_dict(self) -> dict[str, str]:
        """Return the only error fields suitable for a future API response."""

        return {"code": self.code, "status": self.status}


def _json_default(value: Any) -> str:
    """Convert common read-only values without leaking driver objects.

    B028 normally returns JSON-native values.  These explicit conversions
    make the service boundary robust to legacy date/decimal/UUID values while
    rejecting arbitrary database row objects or custom objects instead of
    serializing them through an unsafe ``repr``.
    """

    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, UUID):
        return str(value)
    raise TypeError(f"unsupported player presentation value: {type(value).__name__}")


def _json_safe_copy(value: Any) -> Any:
    """Return a detached JSON-safe copy with no internal mutable references."""

    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            default=_json_default,
            allow_nan=False,
        )
        return json.loads(encoded)
    except (TypeError, ValueError, OverflowError) as exc:
        raise PlayerPresentationReadServiceError(
            "PLAYER_STATE_INVALID",
            "INVALID_STATE",
            "player state contains a non-serializable value",
        ) from exc


def _validate_user_id(user_id: Any) -> int:
    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
        raise PlayerPresentationReadServiceError(
            "INVALID_USER_ID",
            "INVALID_STATE",
            "user_id must be a positive integer",
        )
    return user_id


def _service_status_for_projection(raw_status: Any) -> str:
    if not isinstance(raw_status, str):
        raise PlayerPresentationReadServiceError(
            "PLAYER_STATE_INVALID",
            "INVALID_STATE",
            "player state has no valid projection status",
        )
    try:
        return _B028_STATUS_TO_SERVICE_STATUS[raw_status]
    except KeyError as exc:
        raise PlayerPresentationReadServiceError(
            "PLAYER_STATE_INVALID",
            "INVALID_STATE",
            "player state has an unsupported projection status",
        ) from exc


def _safe_warnings(state: Mapping[str, Any]) -> list[Any]:
    """Preserve only B028-supplied warnings; do not invent domain warnings."""

    warnings = state.get("warnings", [])
    if warnings is None:
        return []
    if not isinstance(warnings, (list, tuple)):
        raise PlayerPresentationReadServiceError(
            "PLAYER_STATE_INVALID",
            "INVALID_STATE",
            "player state warnings are malformed",
        )
    return list(warnings)


def build_player_presentation_state(conn: Any, *, user_id: Any) -> dict[str, Any]:
    """Build the stable API-ready Player presentation read envelope.

    ``conn`` and its transaction remain caller-owned.  This function does no
    SQL itself and calls the B028 builder exactly once per successful or
    failed read attempt.  The returned ``player_state`` retains the complete
    B028 shape rather than flattening fields into a second authority model.
    """

    validated_user_id = _validate_user_id(user_id)

    try:
        state = _b028.build_player_state_read_model(conn, validated_user_id)
    except _b028.PlayerStateReadModelError as exc:
        if exc.code in {"INVALID_STORED_STATE", "AUTHORITY_AMBIGUOUS"}:
            raise PlayerPresentationReadServiceError(
                "PLAYER_STATE_INVALID",
                "INVALID_STATE",
                "canonical player state is invalid",
            ) from exc
        raise PlayerPresentationReadServiceError(
            "PLAYER_STATE_UNAVAILABLE",
            "UNAVAILABLE",
            "canonical player state is unavailable",
        ) from exc
    except Exception as exc:
        # No driver or internal exception text crosses the route boundary.
        raise PlayerPresentationReadServiceError(
            "PLAYER_STATE_UNAVAILABLE",
            "UNAVAILABLE",
            "canonical player state is unavailable",
        ) from exc

    if not isinstance(state, Mapping):
        raise PlayerPresentationReadServiceError(
            "PLAYER_STATE_INVALID",
            "INVALID_STATE",
            "canonical player state is not a mapping",
        )

    service_status = _service_status_for_projection(state.get("projection_status"))
    warnings = _safe_warnings(state)
    detached_state = _json_safe_copy(dict(state))
    detached_warnings = _json_safe_copy(warnings)

    return {
        "contract_version": PLAYER_PRESENTATION_READ_CONTRACT_VERSION,
        "status": service_status,
        "player_state": detached_state,
        "warnings": detached_warnings,
        "read_only": True,
        "mutates": False,
    }


def serialize_player_presentation_state(result: Mapping[str, Any]) -> str:
    """Serialize a service result deterministically for a future API route."""

    if not isinstance(result, Mapping):
        raise PlayerPresentationReadServiceError(
            "PLAYER_STATE_INVALID",
            "INVALID_STATE",
            "service result is not a mapping",
        )
    try:
        return json.dumps(
            result,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
            default=_json_default,
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise PlayerPresentationReadServiceError(
            "PLAYER_STATE_INVALID",
            "INVALID_STATE",
            "service result is not JSON serializable",
        ) from exc


__all__ = [
    "PLAYER_PRESENTATION_READ_CONTRACT_VERSION",
    "PlayerPresentationReadServiceError",
    "build_player_presentation_state",
    "serialize_player_presentation_state",
]
