"""Server-authored transport contract for Adventure Spirit unlock outcomes.

The D030 Adventure milestone service remains the authority for eligibility,
the zone-to-Spirit mapping, and the B023-backed ownership mutation.  This
module only validates and projects a completed D030 outcome into the
``adventure_spirit_unlock_results`` response field consumed by D031.  It
does not call a database, mutate ownership, or decide a milestone.

D030 currently returns the same result shape for a normal settlement and for
historical catch-up.  Historical context is therefore optional at the raw
boundary and is represented as ``None`` when the server caller did not supply
it.  A caller that knows it is running catch-up must pass
``historical_catchup=True``; the transport never guesses.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import json
from typing import Any

from spirit_adventure_milestone import (
    AdventureSpiritAcquisitionError,
    MILESTONE_FACT,
    MILESTONE_SOURCE_AUTHORITY,
    SPIRIT_UNLOCK_OPERATION_TYPE,
    resolve_milestone_for_zone,
)


TRANSPORT_FIELD = "adventure_spirit_unlock_results"
CONTRACT_VERSION = "ADVENTURE_SPIRIT_UNLOCK_RESULT_TRANSPORT_V1"
RESULT_STATES = ("UNLOCKED", "NO_OP", "NOT_ELIGIBLE")
_D030_STATUSES = frozenset({"UNLOCKED", "NO_OP", "REPLAY", "NOT_ELIGIBLE"})
_MISSING = object()

# Readable aliases used by downstream contract tests and future route code.
TRANSPORT_CONTRACT_VERSION = CONTRACT_VERSION
TRANSPORT_RESULT_STATES = RESULT_STATES


class AdventureSpiritUnlockTransportError(ValueError):
    """A D030 result cannot be represented as trusted transport data."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


def _reject(code: str, message: str) -> None:
    raise AdventureSpiritUnlockTransportError(code, message)


def _positive_user_id(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        _reject("INVALID_USER_ID", "user_id must be a positive integer")
    return value


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _reject("MISSING_REQUIRED_FIELD", f"{field} must be a non-empty string")
    return value.strip()


def _bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        _reject("INVALID_BOOLEAN", f"{field} must be boolean")
    return value


def _nonnegative_count(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _reject("INVALID_COUNT", f"{field} must be a non-negative integer")
    return value


def _require_exact_if_present(
    outcome: Mapping[str, Any], field: str, expected: Any
) -> None:
    if field in outcome and outcome[field] != expected:
        _reject("RESULT_FIELD_CONFLICT", f"{field} conflicts with D030 status")


def _historical_marker(outcome: Mapping[str, Any], value: Any) -> bool | None:
    """Preserve explicit server context and never infer normal vs catch-up."""

    embedded = outcome.get("historical_catchup", _MISSING)
    if embedded is not _MISSING:
        embedded = _bool(embedded, "historical_catchup")
    if value is _MISSING:
        # D030 does not currently emit this distinction.  Null is an honest
        # unknown; it is not a guessed ``False``.
        return None
    value = _bool(value, "historical_catchup")
    if embedded is not _MISSING and embedded != value:
        _reject("RESULT_FIELD_CONFLICT", "historical_catchup conflicts with caller context")
    return value


def _validate_d030_outcome(
    outcome: Mapping[str, Any], *, historical_catchup: Any
) -> dict[str, Any]:
    if not isinstance(outcome, Mapping):
        _reject("RESULT_NOT_MAPPING", "D030 outcome must be a mapping")

    user_id = _positive_user_id(outcome.get("user_id"))
    zone_key = _text(outcome.get("zone_key"), "zone_key")
    try:
        milestone = resolve_milestone_for_zone(zone_key)
    except AdventureSpiritAcquisitionError as exc:
        raise AdventureSpiritUnlockTransportError(
            "UNKNOWN_MILESTONE", str(exc)
        ) from exc

    if outcome.get("zone_number") != milestone.zone_number:
        _reject("ZONE_IDENTITY_MISMATCH", "zone_number is not the D030 zone number")
    if outcome.get("spirit_id") != milestone.spirit_id:
        _reject("SPIRIT_IDENTITY_MISMATCH", "spirit_id is not the D030 mapped Spirit")

    expected_operation_id = f"adventure:spirit_unlock:{user_id}:{zone_key}"
    expected_source_reference = f"adventure_boss_progress:{user_id}:{zone_key}"
    if outcome.get("operation_id") != expected_operation_id:
        _reject("OPERATION_ID_MISMATCH", "operation_id is not the D030 operation identity")
    if "source_operation_id" in outcome and outcome["source_operation_id"] != expected_operation_id:
        _reject("OPERATION_ID_MISMATCH", "source_operation_id conflicts with D030 operation identity")
    if outcome.get("source_reference") != expected_source_reference:
        _reject("SOURCE_REFERENCE_MISMATCH", "source_reference is not the D030 fact identity")
    if outcome.get("source_authority") != MILESTONE_SOURCE_AUTHORITY:
        _reject("SOURCE_AUTHORITY_MISMATCH", "source_authority is not Adventure milestone authority")
    if outcome.get("source_fact") != MILESTONE_FACT:
        _reject("SOURCE_FACT_MISMATCH", "source_fact is not the cleared progression fact")
    if outcome.get("operation_type") != SPIRIT_UNLOCK_OPERATION_TYPE:
        _reject("OPERATION_TYPE_MISMATCH", "operation_type is not SPIRIT_UNLOCK")
    if outcome.get("ownership_store") != "pet_collection":
        _reject("OWNERSHIP_STORE_MISMATCH", "ownership_store is not pet_collection")
    if outcome.get("client_completion_authority") is not False:
        _reject("CLIENT_AUTHORITY_PRESENT", "client completion authority must be false")

    status = outcome.get("status")
    if not isinstance(status, str) or status not in _D030_STATUSES:
        _reject("UNKNOWN_RESULT_STATE", "status is not a supported D030 terminal state")

    eligible = _bool(outcome.get("eligible"), "eligible")
    cleared = _bool(outcome.get("cleared"), "cleared")
    replayed = _bool(outcome.get("replayed"), "replayed")
    operation_status = outcome.get("operation_status")
    if status == "NOT_ELIGIBLE":
        if operation_status is not None:
            _reject("MALFORMED_NOT_ELIGIBLE", "NOT_ELIGIBLE cannot have a completed operation")
        expected = {
            "result_state": "NOT_ELIGIBLE",
            "ownership_created": False,
            # D030 does not inspect pet_collection on this branch; absence of
            # eligibility is not proof of non-ownership.
            "already_owned": None,
            "replay": False,
            "eligible": False,
            "cleared": False,
            "replayed": False,
            "ownership_mutation_count": 0,
            "new_unlock_count": 0,
            "reason_code": "MILESTONE_NOT_ELIGIBLE",
        }
    else:
        if operation_status != "COMPLETED":
            _reject("NON_TERMINAL_RESULT", "eligible D030 result must be COMPLETED")
        if status == "UNLOCKED":
            expected = {
                "result_state": "UNLOCKED",
                "ownership_created": True,
                "already_owned": False,
                "replay": False,
                "eligible": True,
                "cleared": True,
                "replayed": False,
                "ownership_mutation_count": 1,
                "new_unlock_count": 1,
                "reason_code": "MILESTONE_UNLOCKED",
            }
        elif status == "NO_OP":
            expected = {
                "result_state": "NO_OP",
                "ownership_created": False,
                "already_owned": True,
                "replay": False,
                "eligible": True,
                "cleared": True,
                "replayed": False,
                "ownership_mutation_count": 0,
                "new_unlock_count": 0,
                "reason_code": "MILESTONE_ALREADY_OWNED",
            }
        else:  # D030 REPLAY is a no-op result for presentation purposes.
            expected = {
                "result_state": "NO_OP",
                "ownership_created": False,
                "already_owned": True,
                "replay": True,
                "eligible": True,
                "cleared": True,
                "replayed": True,
                "ownership_mutation_count": 0,
                "new_unlock_count": 0,
                "reason_code": "MILESTONE_REPLAY",
            }

    for field, expected_value in expected.items():
        _require_exact_if_present(outcome, field, expected_value)
        if field in {"eligible", "cleared", "replayed"}:
            actual = {"eligible": eligible, "cleared": cleared, "replayed": replayed}[field]
            if actual != expected_value:
                _reject("RESULT_FIELD_CONFLICT", f"{field} conflicts with D030 status")
        elif field in {"ownership_mutation_count", "new_unlock_count"}:
            actual = _nonnegative_count(outcome.get(field), field)
            if actual != expected_value:
                _reject("RESULT_FIELD_CONFLICT", f"{field} conflicts with D030 status")

    compensation_count = _nonnegative_count(outcome.get("compensation_count"), "compensation_count")
    replacement_count = _nonnegative_count(outcome.get("replacement_count"), "replacement_count")
    if compensation_count != 0 or replacement_count != 0:
        _reject("UNAUTHORIZED_COMPENSATION", "D030 milestone results cannot compensate or replace")

    historical = _historical_marker(outcome, historical_catchup)
    return {
        "contract_version": CONTRACT_VERSION,
        "user_id": user_id,
        "zone_key": zone_key,
        "zone_number": milestone.zone_number,
        "spirit_id": milestone.spirit_id,
        "result_state": expected["result_state"],
        "status": status,
        "ownership_created": expected["ownership_created"],
        "already_owned": expected["already_owned"],
        "historical_catchup": historical,
        "replay": expected["replay"],
        "reason_code": expected["reason_code"],
        "operation_id": expected_operation_id,
        "source_authority": MILESTONE_SOURCE_AUTHORITY,
        "source_fact": MILESTONE_FACT,
        "source_reference": expected_source_reference,
        "operation_type": SPIRIT_UNLOCK_OPERATION_TYPE,
        "ownership_store": "pet_collection",
        "eligible": expected["eligible"],
        "cleared": expected["cleared"],
        "operation_status": operation_status,
        "replayed": expected["replayed"],
        "ownership_mutation_count": expected["ownership_mutation_count"],
        "new_unlock_count": expected["new_unlock_count"],
        "compensation_count": compensation_count,
        "replacement_count": replacement_count,
        "client_completion_authority": False,
    }


@dataclass(frozen=True, slots=True)
class AdventureSpiritUnlockTransportResult:
    """One immutable, D030-backed response item."""

    contract_version: str
    user_id: int
    zone_key: str
    zone_number: int
    spirit_id: str
    result_state: str
    status: str
    ownership_created: bool
    already_owned: bool | None
    historical_catchup: bool | None
    replay: bool
    reason_code: str
    operation_id: str
    source_authority: str
    source_fact: str
    source_reference: str
    operation_type: str
    ownership_store: str
    eligible: bool
    cleared: bool
    operation_status: str | None
    replayed: bool
    ownership_mutation_count: int
    new_unlock_count: int
    compensation_count: int
    replacement_count: int
    client_completion_authority: bool

    def to_dict(self) -> dict[str, Any]:
        """Return the D031-compatible JSON object without mutable state."""

        result: dict[str, Any] = {
            "contract_version": self.contract_version,
            "user_id": self.user_id,
            "zone_key": self.zone_key,
            "zone_number": self.zone_number,
            "spirit_id": self.spirit_id,
            "result_state": self.result_state,
            "status": self.status,
            "ownership_created": self.ownership_created,
            "already_owned": self.already_owned,
            "historical_catchup": self.historical_catchup,
            "replay": self.replay,
            "reason_code": self.reason_code,
            "operation_id": self.operation_id,
            "source_authority": self.source_authority,
            "source_fact": self.source_fact,
            "source_reference": self.source_reference,
            "operation_type": self.operation_type,
            "ownership_store": self.ownership_store,
            "eligible": self.eligible,
            "cleared": self.cleared,
            "replayed": self.replayed,
            "ownership_mutation_count": self.ownership_mutation_count,
            "new_unlock_count": self.new_unlock_count,
            "compensation_count": self.compensation_count,
            "replacement_count": self.replacement_count,
            "client_completion_authority": self.client_completion_authority,
        }
        if self.operation_status is not None:
            result["operation_status"] = self.operation_status
        return result

    as_dict = to_dict
    to_wire = to_dict


def build_adventure_spirit_unlock_result(
    outcome: Mapping[str, Any], *, historical_catchup: Any = _MISSING
) -> AdventureSpiritUnlockTransportResult:
    """Validate one already-authoritative D030 outcome for transport."""

    values = _validate_d030_outcome(outcome, historical_catchup=historical_catchup)
    return AdventureSpiritUnlockTransportResult(**values)


def build_adventure_spirit_unlock_results(
    outcomes: Iterable[Mapping[str, Any]], *, historical_catchup: Any = _MISSING
) -> tuple[AdventureSpiritUnlockTransportResult, ...]:
    """Build a deterministic result list, sorted by D030 zone number.

    Duplicate mapped zones are rejected rather than allowing an ambiguous
    response to reach D031.  Sorting is transport stability; it does not
    select or authorize a milestone.
    """

    if isinstance(outcomes, (str, bytes, Mapping)):
        _reject("RESULT_LIST_REQUIRED", "outcomes must be an iterable of result mappings")
    try:
        results = tuple(
            build_adventure_spirit_unlock_result(
                outcome, historical_catchup=historical_catchup
            )
            for outcome in outcomes
        )
    except TypeError as exc:
        raise AdventureSpiritUnlockTransportError(
            "RESULT_LIST_REQUIRED", "outcomes must be iterable"
        ) from exc
    seen: set[tuple[int, str]] = set()
    for result in results:
        identity = (result.user_id, result.zone_key)
        if identity in seen:
            _reject("DUPLICATE_RESULT_IDENTITY", "one zone result may appear only once")
        seen.add(identity)
    return tuple(sorted(results, key=lambda item: (item.user_id, item.zone_number)))


def build_adventure_spirit_unlock_transport(
    outcomes: Iterable[Mapping[str, Any]], *, historical_catchup: Any = _MISSING
) -> dict[str, list[dict[str, Any]]]:
    """Return the response fragment that a later thin route may attach."""

    results = build_adventure_spirit_unlock_results(
        outcomes, historical_catchup=historical_catchup
    )
    return {TRANSPORT_FIELD: [result.to_dict() for result in results]}


def serialize_adventure_spirit_unlock_results(
    results: Iterable[AdventureSpiritUnlockTransportResult],
) -> list[dict[str, Any]]:
    """Serialize already-validated result objects as the D031 list value."""

    if isinstance(results, (str, bytes, Mapping)):
        _reject("RESULT_LIST_REQUIRED", "results must be an iterable of typed results")
    serialized = []
    for result in results:
        if not isinstance(result, AdventureSpiritUnlockTransportResult):
            _reject("TYPED_RESULT_REQUIRED", "serialize expects validated transport results")
        serialized.append(result.to_dict())
    return serialized


def serialize_adventure_spirit_unlock_results_json(
    results: Iterable[AdventureSpiritUnlockTransportResult],
) -> str:
    """Serialize the D031 list value deterministically."""

    return json.dumps(
        serialize_adventure_spirit_unlock_results(results),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def serialize_adventure_spirit_unlock_transport(
    outcomes: Iterable[Mapping[str, Any]], *, historical_catchup: Any = _MISSING
) -> str:
    """Serialize the complete response fragment deterministically."""

    return json.dumps(
        build_adventure_spirit_unlock_transport(
            outcomes, historical_catchup=historical_catchup
        ),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


# Compatibility names for the future thin route and focused review suites.
build_adventure_spirit_unlock_transport_result = build_adventure_spirit_unlock_result
build_adventure_spirit_unlock_transport_results = build_adventure_spirit_unlock_results


__all__ = [
    "AdventureSpiritUnlockTransportError",
    "AdventureSpiritUnlockTransportResult",
    "CONTRACT_VERSION",
    "RESULT_STATES",
    "TRANSPORT_CONTRACT_VERSION",
    "TRANSPORT_FIELD",
    "TRANSPORT_RESULT_STATES",
    "build_adventure_spirit_unlock_result",
    "build_adventure_spirit_unlock_results",
    "build_adventure_spirit_unlock_transport",
    "build_adventure_spirit_unlock_transport_result",
    "build_adventure_spirit_unlock_transport_results",
    "serialize_adventure_spirit_unlock_results",
    "serialize_adventure_spirit_unlock_results_json",
    "serialize_adventure_spirit_unlock_transport",
]
