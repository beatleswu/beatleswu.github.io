"""Deterministic adapter from existing legacy Review results to new seams."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from legacy_review_serializer import LegacyReviewSerializer
from review_contracts import (
    APPROVED_PRESENTATION_EXTENSION_FIELDS,
    CORE_20_FIELDS,
    FULL_26_FIELDS,
    INTERNAL_DUPLICATE_4_FIELDS,
    ReviewOutcome,
    ReviewOutcomeKind,
)


_PUBLIC_FULL_KEY_SET = frozenset(FULL_26_FIELDS)
_PUBLIC_CORE_KEY_SET = frozenset(CORE_20_FIELDS)
_INTERNAL_DUPLICATE_KEY_SET = frozenset(INTERNAL_DUPLICATE_4_FIELDS)
_APPROVED_EXTENSION_KEY_SET = frozenset(APPROVED_PRESENTATION_EXTENSION_FIELDS)


def adapt_legacy_review_result(
    legacy_result: Mapping[str, Any], *, internal: bool = False
) -> ReviewOutcome:
    """Map an already-materialized legacy result to a plain outcome.

    The caller supplies the existing internal/public boundary.  No database,
    Flask response, transaction, reward, or progression operation is invoked
    here.  A duplicate projection is accepted only for an internal caller so
    it cannot be accidentally surfaced as a new public envelope.

    Exactly the keys named in ``APPROVED_PRESENTATION_EXTENSION_FIELDS`` are
    set aside before the legacy shape is classified, then carried on the
    outcome as ``presentation_extensions``.  This is deliberately a fixed
    allowlist, not a generic passthrough: any other unrecognized key still
    fails closed below, exactly as before this seam existed.
    """

    if not isinstance(legacy_result, Mapping):
        raise TypeError("legacy_result must be a mapping")

    presentation_extensions = {
        key: legacy_result[key]
        for key in APPROVED_PRESENTATION_EXTENSION_FIELDS
        if key in legacy_result
    }
    core_result = {
        key: value
        for key, value in legacy_result.items()
        if key not in _APPROVED_EXTENSION_KEY_SET
    }

    key_set = frozenset(core_result)
    if key_set == _PUBLIC_FULL_KEY_SET:
        return ReviewOutcome.public_full(
            core_result, presentation_extensions=presentation_extensions
        )
    if key_set == _PUBLIC_CORE_KEY_SET:
        return ReviewOutcome.public_core(
            core_result, presentation_extensions=presentation_extensions
        )
    if key_set == _INTERNAL_DUPLICATE_KEY_SET:
        if not internal:
            raise ValueError("internal duplicate result cannot use public boundary")
        return ReviewOutcome.internal_duplicate(
            core_result, presentation_extensions=presentation_extensions
        )

    raise ValueError(
        "unrecognized legacy review result shape; "
        f"keys={tuple(legacy_result)!r}, internal={internal!r}"
    )


def serialize_legacy_review_result(
    legacy_result: Mapping[str, Any], *, internal: bool = False
) -> dict[str, Any]:
    """Adapt and serialize a legacy result without changing its semantics."""

    return LegacyReviewSerializer.serialize(
        adapt_legacy_review_result(legacy_result, internal=internal)
    )


class LegacyReviewCompatibilityAdapter:
    """Named adapter boundary for future bounded orchestration wiring."""

    @staticmethod
    def to_outcome(
        legacy_result: Mapping[str, Any], *, internal: bool = False
    ) -> ReviewOutcome:
        return adapt_legacy_review_result(legacy_result, internal=internal)

    @staticmethod
    def to_legacy_payload(
        legacy_result: Mapping[str, Any], *, internal: bool = False
    ) -> dict[str, Any]:
        return serialize_legacy_review_result(legacy_result, internal=internal)


__all__ = [
    "LegacyReviewCompatibilityAdapter",
    "adapt_legacy_review_result",
    "serialize_legacy_review_result",
]
