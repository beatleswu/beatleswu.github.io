"""Pure adapters from committed producer results to D018 acquisition facts.

The functions in this module translate facts that an upstream authority has
already committed.  They never open a database, call a mutation hook, retry a
producer, or infer a grant from a preview, catalog, entitlement, or state
flag.  Missing authority evidence returns ``INSUFFICIENT_AUTHORITY_EVIDENCE``
instead of a partially populated :class:`CanonicalAcquisitionResult`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable

from canonical_acquisition_result import (
    AcquisitionResultValidationError,
    CanonicalAcquisitionResult,
)


ADAPTER_VERSION = "ACQUISITION_PRODUCER_ADAPTER_CORE_V1"
READY = "READY"
INSUFFICIENT_AUTHORITY_EVIDENCE = "INSUFFICIENT_AUTHORITY_EVIDENCE"
DATABASE_WRITES = 0
MUTATION_CAPABILITY = "NO"

MONSTER_DROP = "MONSTER_DROP"
QUEST_REWARD = "QUEST_REWARD"
PREMIUM_REWARD = "PREMIUM_REWARD"
SHOP_COIN_PURCHASE = "SHOP_COIN_PURCHASE"

SUPPORTED_ADAPTER_FAMILIES = (
    MONSTER_DROP,
    QUEST_REWARD,
    PREMIUM_REWARD,
    SHOP_COIN_PURCHASE,
)

_MISSING = object()
_COMMITTED_STATUSES = frozenset({"COMMITTED", "SETTLED"})
_SUCCESS_STATUSES = frozenset({"SUCCESS", "COMMITTED", "SETTLED"})
_REJECTED_PREVIEW_VALUES = frozenset({"PREVIEW", "UNCOMMITTED", "UNSETTLED"})


@dataclass(frozen=True, slots=True)
class AcquisitionAdapterResult:
    """A pure adapter decision and, only when ready, its D018 result."""

    adapter_family: str
    status: str
    result: CanonicalAcquisitionResult | None = None
    reason_code: str | None = None
    missing_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.adapter_family not in SUPPORTED_ADAPTER_FAMILIES:
            raise ValueError("unsupported acquisition adapter family")
        if self.status not in {READY, INSUFFICIENT_AUTHORITY_EVIDENCE}:
            raise ValueError("unsupported adapter status")
        if self.status == READY and self.result is None:
            raise ValueError("READY adapter results require a canonical result")
        if self.status == INSUFFICIENT_AUTHORITY_EVIDENCE and self.result is not None:
            raise ValueError("insufficient adapter results cannot contain a canonical result")
        if any(not isinstance(field, str) or not field for field in self.missing_fields):
            raise ValueError("missing_fields must contain non-empty strings")

    @property
    def is_ready(self) -> bool:
        return self.status == READY

    def as_dict(self) -> dict[str, Any]:
        return {
            "adapter_family": self.adapter_family,
            "status": self.status,
            "reason_code": self.reason_code,
            "missing_fields": list(self.missing_fields),
            "result": self.result.to_dict() if self.result is not None else None,
        }


def _insufficient(
    family: str,
    reason_code: str,
    *,
    missing_fields: tuple[str, ...] = (),
) -> AcquisitionAdapterResult:
    return AcquisitionAdapterResult(
        adapter_family=family,
        status=INSUFFICIENT_AUTHORITY_EVIDENCE,
        reason_code=reason_code,
        missing_fields=missing_fields,
    )


def _mapping(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _lookup(
    payload: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *names: str,
) -> Any:
    """Look up an explicit producer field without deriving a value."""

    ownership = _mapping(candidate.get("ownership_result"))
    for mapping in (candidate, ownership, payload):
        if mapping is None:
            continue
        for name in names:
            if name in mapping:
                return mapping[name]
    return _MISSING


def _candidate(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    for key in ("acquisition", "reward", "component"):
        nested = _mapping(payload.get(key))
        if nested is not None:
            return nested
    return payload


def _has_explicit_commit_marker(
    payload: Mapping[str, Any],
    *,
    marker_names: tuple[str, ...],
    status_names: tuple[str, ...],
    accepted_statuses: frozenset[str],
) -> bool:
    for name in marker_names:
        if payload.get(name) is True:
            return True
    for name in status_names:
        value = payload.get(name)
        if isinstance(value, str) and value.strip().upper() in accepted_statuses:
            return True
    return False


def _preview_rejected(payload: Mapping[str, Any]) -> bool:
    if payload.get("preview") is True or payload.get("is_preview") is True:
        return True
    for name in ("status", "settlement_status", "claim_status", "purchase_status"):
        value = payload.get(name)
        if isinstance(value, str) and value.strip().upper() in _REJECTED_PREVIEW_VALUES:
            return True
    return False


def _source_status_rejected(
    payload: Mapping[str, Any],
    *,
    status_names: tuple[str, ...],
    accepted_statuses: frozenset[str],
) -> bool:
    """Reject an explicit terminal status that is not a committed success."""

    for name in status_names:
        if name not in payload:
            continue
        value = payload[name]
        if not isinstance(value, str):
            return True
        normalized = value.strip().upper()
        if normalized in _REJECTED_PREVIEW_VALUES:
            return True
        if normalized not in accepted_statuses and normalized not in {"SUCCESS"}:
            return True
    return False


def _required_fields(
    payload: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    source_operation_names: tuple[str, ...],
    source_reference_names: tuple[str, ...],
) -> tuple[dict[str, Any] | None, tuple[str, ...]]:
    """Collect only explicit facts required by D018."""

    values: dict[str, Any] = {}
    missing: list[str] = []

    aliases = {
        "item_id": ("item_id", "reward_id"),
        "quantity": ("quantity", "reward_quantity"),
        "source_operation_id": source_operation_names,
        "source_reference": source_reference_names,
        "destination": ("destination",),
        "ownership_authority": ("ownership_authority",),
        "ownership_reference": ("ownership_reference",),
        "resulting_quantity": ("resulting_quantity", "new_quantity"),
        "can_equip": ("can_equip",),
        "can_use": ("can_use",),
        "can_wear": ("can_wear",),
        "replayed": ("replayed",),
        "lineage_event_id": (
            "lineage_event_id",
            "item_acquisition_event_id",
            "acquisition_event_id",
            "event_id",
        ),
        "item_class": ("item_class",),
    }
    for field, names in aliases.items():
        value = _lookup(payload, candidate, *names)
        if value is _MISSING:
            missing.append(field)
        else:
            values[field] = value
    if missing:
        return None, tuple(sorted(missing))

    # ``is_new`` is deliberately nullable. Absence means the producer could
    # not prove pre-grant ownership; it never means ``not replayed``.
    values["is_new"] = _lookup(payload, candidate, "is_new")
    if values["is_new"] is _MISSING:
        values["is_new"] = None

    metadata = _lookup(payload, candidate, "metadata", "presentation_metadata")
    values["metadata"] = {} if metadata is _MISSING else metadata
    return values, ()


def _build_result(
    family: str,
    payload: Mapping[str, Any],
    *,
    source_operation_names: tuple[str, ...],
    source_reference_names: tuple[str, ...],
) -> AcquisitionAdapterResult:
    candidate = _candidate(payload)
    values, missing = _required_fields(
        payload,
        candidate,
        source_operation_names=source_operation_names,
        source_reference_names=source_reference_names,
    )
    if values is None:
        return _insufficient(family, "REQUIRED_AUTHORITY_FIELD_MISSING", missing_fields=missing)
    values["contract_version"] = "CANONICAL_ACQUISITION_RESULT_V1"
    values["source_type"] = family
    try:
        result = CanonicalAcquisitionResult.from_mapping(values)
    except AcquisitionResultValidationError as exc:
        return _insufficient(family, f"D018_{exc.code}")
    return AcquisitionAdapterResult(adapter_family=family, status=READY, result=result)


def _adapt(
    family: str,
    payload: Mapping[str, Any],
    *,
    marker_names: tuple[str, ...],
    status_names: tuple[str, ...],
    accepted_statuses: frozenset[str],
    source_operation_names: tuple[str, ...],
    source_reference_names: tuple[str, ...],
    precondition: Callable[[Mapping[str, Any]], AcquisitionAdapterResult | None] | None = None,
) -> AcquisitionAdapterResult:
    if not isinstance(payload, Mapping):
        return _insufficient(family, "PRODUCER_RESULT_NOT_MAPPING")
    if _preview_rejected(payload):
        return _insufficient(family, "PREVIEW_NOT_COMMITTED")
    if precondition is not None:
        failure = precondition(payload)
        if failure is not None:
            return failure
    if _source_status_rejected(
        payload,
        status_names=status_names,
        accepted_statuses=accepted_statuses,
    ):
        return _insufficient(family, "SOURCE_STATUS_NOT_COMMITTED")
    if not _has_explicit_commit_marker(
        payload,
        marker_names=marker_names,
        status_names=status_names,
        accepted_statuses=accepted_statuses,
    ):
        return _insufficient(family, "COMMITTED_RESULT_EVIDENCE_REQUIRED")
    return _build_result(
        family,
        payload,
        source_operation_names=source_operation_names,
        source_reference_names=source_reference_names,
    )


def _quest_precondition(payload: Mapping[str, Any]) -> AcquisitionAdapterResult | None:
    claim_status = payload.get("claim_status")
    if claim_status is not None:
        if not isinstance(claim_status, str) or claim_status.strip().upper() not in _SUCCESS_STATUSES:
            return _insufficient(QUEST_REWARD, "QUEST_CLAIM_NOT_SETTLED")
    if payload.get("claimed") is False or payload.get("claimable") is True and payload.get("claimed") is not True:
        return _insufficient(QUEST_REWARD, "QUEST_CLAIM_NOT_SETTLED")
    if payload.get("completed") is True and claim_status is None and payload.get("claimed") is not True:
        return _insufficient(QUEST_REWARD, "QUEST_CLAIM_RESULT_REQUIRED")
    if claim_status is None and payload.get("claimed") is not True and payload.get("committed") is not True:
        return _insufficient(QUEST_REWARD, "QUEST_CLAIM_RESULT_REQUIRED")
    return None


def _premium_precondition(payload: Mapping[str, Any]) -> AcquisitionAdapterResult | None:
    status = payload.get("claim_status", payload.get("reward_status"))
    if status is not None:
        if not isinstance(status, str) or status.strip().upper() not in _SUCCESS_STATUSES:
            return _insufficient(PREMIUM_REWARD, "PREMIUM_REWARD_NOT_SETTLED")
    if payload.get("entitlement_active") is True and status is None and payload.get("committed") is not True:
        return _insufficient(PREMIUM_REWARD, "PREMIUM_ENTITLEMENT_IS_NOT_A_REWARD_RESULT")
    return None


def adapt_monster_drop(payload: Mapping[str, Any]) -> AcquisitionAdapterResult:
    """Adapt a committed Monster settlement, never a defeat/preview surface."""

    return _adapt(
        MONSTER_DROP,
        payload,
        marker_names=("committed", "settlement_committed"),
        status_names=("settlement_status", "transaction_status", "status"),
        accepted_statuses=_COMMITTED_STATUSES,
        source_operation_names=("source_operation_id", "operation_id", "settlement_operation_id"),
        source_reference_names=("source_reference", "settlement_id", "source_id"),
    )


def adapt_quest_reward(payload: Mapping[str, Any]) -> AcquisitionAdapterResult:
    """Adapt a settled Quest claim/reward result, not completion state."""

    return _adapt(
        QUEST_REWARD,
        payload,
        marker_names=("committed", "claim_committed"),
        status_names=("claim_status", "transaction_status", "status"),
        accepted_statuses=_SUCCESS_STATUSES,
        source_operation_names=("source_operation_id", "operation_id", "claim_operation_id"),
        source_reference_names=("source_reference", "claim_idempotency_key", "claim_id", "period_key"),
        precondition=_quest_precondition,
    )


def adapt_premium_reward(payload: Mapping[str, Any]) -> AcquisitionAdapterResult:
    """Adapt a committed Premium reward result, not entitlement state."""

    return _adapt(
        PREMIUM_REWARD,
        payload,
        marker_names=("committed", "claim_committed", "reward_committed"),
        status_names=("claim_status", "reward_status", "transaction_status", "status"),
        accepted_statuses=_SUCCESS_STATUSES,
        source_operation_names=("source_operation_id", "operation_id", "claim_operation_id"),
        source_reference_names=("source_reference", "claim_idempotency_key", "claim_id", "period_key"),
        precondition=_premium_precondition,
    )


def adapt_shop_coin_purchase(payload: Mapping[str, Any]) -> AcquisitionAdapterResult:
    """Adapt a committed C019 purchase result, not an offer/catalog record."""

    return _adapt(
        SHOP_COIN_PURCHASE,
        payload,
        marker_names=("committed", "purchase_committed"),
        status_names=("purchase_status", "operation_status", "transaction_status", "status"),
        accepted_statuses=_COMMITTED_STATUSES,
        source_operation_names=("source_operation_id", "operation_id", "purchase_operation_id"),
        source_reference_names=("source_reference", "offer_id", "purchase_id"),
    )


_ADAPTERS = MappingProxyType(
    {
        MONSTER_DROP: adapt_monster_drop,
        QUEST_REWARD: adapt_quest_reward,
        PREMIUM_REWARD: adapt_premium_reward,
        SHOP_COIN_PURCHASE: adapt_shop_coin_purchase,
    }
)


def adapt_acquisition_result(
    family: str,
    payload: Mapping[str, Any],
) -> AcquisitionAdapterResult:
    """Dispatch one of the four supported pure producer adapters."""

    adapter = _ADAPTERS.get(family)
    if adapter is None:
        raise ValueError(f"unsupported acquisition adapter family: {family!r}")
    return adapter(payload)


__all__ = [
    "ADAPTER_VERSION",
    "DATABASE_WRITES",
    "INSUFFICIENT_AUTHORITY_EVIDENCE",
    "MUTATION_CAPABILITY",
    "AcquisitionAdapterResult",
    "MONSTER_DROP",
    "PREMIUM_REWARD",
    "QUEST_REWARD",
    "READY",
    "SHOP_COIN_PURCHASE",
    "SUPPORTED_ADAPTER_FAMILIES",
    "adapt_acquisition_result",
    "adapt_monster_drop",
    "adapt_premium_reward",
    "adapt_quest_reward",
    "adapt_shop_coin_purchase",
]
