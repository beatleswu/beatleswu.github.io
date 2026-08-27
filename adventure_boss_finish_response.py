"""Backward-compatible response composition for Adventure boss finish.

The Adventure settlement route remains the authority for the existing boss
response and for D030's milestone outcome.  This module only accepts an
already validated D032 ``AdventureSpiritUnlockTransportResult`` and appends
its serialized value under ``adventure_spirit_unlock_results``.  It does not
read request data, resolve a zone, call a database, or mutate any authority.

An absent milestone result is represented by an empty D032 result list.  An
explicit D032 ``NOT_ELIGIBLE`` result remains available when the server has a
known mapped zone but no eligible persisted milestone.  Neither case is
turned into a fabricated unlock or ownership statement.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from adventure_spirit_unlock_transport import (
    AdventureSpiritUnlockTransportError,
    AdventureSpiritUnlockTransportResult,
    TRANSPORT_FIELD,
    build_adventure_spirit_unlock_result,
)


RESPONSE_FIELD = TRANSPORT_FIELD
NEUTRAL_RESULT = []


class AdventureBossFinishResponseError(ValueError):
    """The response or D032 result cannot be composed safely."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


def _reject(code: str, message: str) -> None:
    raise AdventureBossFinishResponseError(code, message)


def _validated_result(value: Any) -> AdventureSpiritUnlockTransportResult:
    """Revalidate one immutable D032 value before it crosses the response boundary."""

    if not isinstance(value, AdventureSpiritUnlockTransportResult):
        _reject(
            "MALFORMED_TRANSPORT",
            "response composition accepts only a D032 typed result",
        )

    try:
        wire = dict(value.to_wire())
        if value.historical_catchup is None:
            # D032 uses an omitted raw marker to mean unknown.  Its typed
            # serializer exposes that unknown as JSON null, which must not be
            # fed back as a raw boolean input during revalidation.
            wire.pop("historical_catchup", None)
            canonical = build_adventure_spirit_unlock_result(wire)
        else:
            canonical = build_adventure_spirit_unlock_result(
                wire, historical_catchup=value.historical_catchup
            )
    except AdventureSpiritUnlockTransportError as exc:
        raise AdventureBossFinishResponseError(
            "MALFORMED_TRANSPORT", str(exc)
        ) from exc

    # D032 is the sole normalizer.  A directly-constructed or altered
    # dataclass must not be silently repaired by this response adapter.
    if canonical != value:
        _reject(
            "MALFORMED_TRANSPORT",
            "typed result does not match the canonical D032 projection",
        )
    return canonical


def _validated_results(
    spirit_unlock_result: Any,
) -> tuple[AdventureSpiritUnlockTransportResult, ...]:
    """Normalize a single/list D032 value in deterministic zone order."""

    if spirit_unlock_result is None:
        return ()
    if isinstance(spirit_unlock_result, AdventureSpiritUnlockTransportResult):
        values = (spirit_unlock_result,)
    elif isinstance(spirit_unlock_result, (list, tuple)):
        values = tuple(spirit_unlock_result)
    else:
        _reject(
            "MALFORMED_TRANSPORT",
            "result must be a D032 value, list, tuple, or None",
        )

    validated = tuple(_validated_result(value) for value in values)
    seen: set[tuple[int, str]] = set()
    for value in validated:
        identity = (value.user_id, value.zone_key)
        if identity in seen:
            _reject(
                "DUPLICATE_RESULT_IDENTITY",
                "one response cannot contain the same user and zone twice",
            )
        seen.add(identity)
    return tuple(sorted(validated, key=lambda value: (value.user_id, value.zone_number)))


def build_adventure_boss_finish_spirit_result_fragment(
    spirit_unlock_result: Any = None,
) -> dict[str, list[dict[str, Any]]]:
    """Build only the additive D032 response fragment.

    ``None`` and an empty list are the neutral no-result representation.  A
    non-empty value must be an immutable D032 result or a list/tuple of such
    results; raw D030 dictionaries and client-shaped payloads are rejected.
    """

    results = _validated_results(spirit_unlock_result)
    return {RESPONSE_FIELD: [result.to_wire() for result in results]}


def compose_adventure_boss_finish_response(
    existing_response: Mapping[str, Any],
    spirit_unlock_result: Any = None,
) -> dict[str, Any]:
    """Preserve the existing boss-finish response and append D032 data.

    The existing response must not already contain the additive field.  This
    prevents accidental overwrites or a second response authority during the
    later thin route wiring.
    """

    if not isinstance(existing_response, Mapping) or isinstance(
        existing_response, (str, bytes)
    ):
        _reject("RESPONSE_MAPPING_REQUIRED", "existing response must be a mapping")
    if RESPONSE_FIELD in existing_response:
        _reject(
            "RESPONSE_FIELD_ALREADY_PRESENT",
            "the additive D032 field must be attached exactly once",
        )

    fragment = build_adventure_boss_finish_spirit_result_fragment(spirit_unlock_result)
    response = dict(existing_response)
    response[RESPONSE_FIELD] = fragment[RESPONSE_FIELD]
    return response


__all__ = [
    "AdventureBossFinishResponseError",
    "NEUTRAL_RESULT",
    "RESPONSE_FIELD",
    "build_adventure_boss_finish_spirit_result_fragment",
    "compose_adventure_boss_finish_response",
]
