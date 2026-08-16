"""Pure serialization of Review compatibility outcomes."""

from __future__ import annotations

from typing import Any

from review_contracts import (
    CORE_20_FIELDS,
    FULL_26_FIELDS,
    INTERNAL_DUPLICATE_4_FIELDS,
    ReviewOutcome,
    ReviewOutcomeKind,
)


def _expected_fields(kind: ReviewOutcomeKind) -> tuple[str, ...]:
    if kind is ReviewOutcomeKind.PUBLIC_FULL:
        return FULL_26_FIELDS
    if kind is ReviewOutcomeKind.PUBLIC_CORE:
        return CORE_20_FIELDS
    if kind is ReviewOutcomeKind.INTERNAL_DUPLICATE:
        return INTERNAL_DUPLICATE_4_FIELDS
    raise ValueError(f"unsupported review outcome kind: {kind!r}")


class LegacyReviewSerializer:
    """Serialize an outcome without consulting any external authority.

    Shape validation here is a wire-contract check, not a business decision.
    Values are copied without coercion so ``None`` remains a present JSON
    value, while omitted T2 fields remain omitted.
    """

    @staticmethod
    def serialize(outcome: ReviewOutcome) -> dict[str, Any]:
        if not isinstance(outcome, ReviewOutcome):
            raise TypeError("outcome must be a ReviewOutcome")

        expected = _expected_fields(outcome.kind)
        actual = tuple(outcome.payload.keys())
        if set(actual) != set(expected):
            missing = tuple(field for field in expected if field not in outcome.payload)
            unexpected = tuple(field for field in actual if field not in expected)
            raise ValueError(
                "legacy review payload shape mismatch: "
                f"missing={missing!r}, unexpected={unexpected!r}"
            )

        return {field: outcome.payload[field] for field in expected}


def serialize_legacy_review(outcome: ReviewOutcome) -> dict[str, Any]:
    """Functional alias for callers that prefer a function boundary."""

    return LegacyReviewSerializer.serialize(outcome)


__all__ = ["LegacyReviewSerializer", "serialize_legacy_review"]
