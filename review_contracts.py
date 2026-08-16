"""Pure application contracts for the legacy Review compatibility seam.

The existing Flask operation remains the durable authority.  These contracts
only carry values which have already crossed that legacy compatibility
boundary; they deliberately do not know about HTTP, persistence, or any
domain-specific progression authority.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


# Keep these tuples in the same order as the legacy JSON construction.  The
# order is useful for deterministic serialization and makes the historical
# public contract explicit without changing the public route.
CORE_20_FIELDS: tuple[str, ...] = (
    "ok",
    "ease_factor",
    "interval",
    "due_date",
    "new_badges",
    "stats",
    "xp_gain",
    "combo_mult",
    "pet_xp_added",
    "pet_xp_ratio",
    "pet_xp_gained",
    "combo_streak",
    "shield_used",
    "xp_potion_active",
    "ranked_up",
    "new_rank_level",
    "pet",
    "practice",
    "training",
    "new_appearance_items",
)

T2_OPTIONAL_FIELDS: tuple[str, ...] = (
    "monster",
    "player",
    "quest_updates",
    "sp",
    "loot",
    "appearance_loot",
)

FULL_26_FIELDS: tuple[str, ...] = CORE_20_FIELDS + T2_OPTIONAL_FIELDS

INTERNAL_DUPLICATE_4_FIELDS: tuple[str, ...] = (
    "ok",
    "progression_applied",
    "progression_duplicate",
    "question_id",
)


class ReviewOutcomeKind(str, Enum):
    """The legacy-compatible result shape represented by an outcome."""

    PUBLIC_FULL = "PUBLIC_FULL"
    PUBLIC_CORE = "PUBLIC_CORE"
    INTERNAL_DUPLICATE = "INTERNAL_DUPLICATE"


@dataclass(frozen=True, slots=True)
class ReviewCommand:
    """Values already accepted and normalized by the compatibility boundary.

    This is intentionally not a request parser.  Flask request/session
    handling, authentication, validation, and authoritative Map Battle
    settlement remain outside this contract.  ``internal`` and
    ``submission_id`` carry the existing internal call shape without importing
    or depending on Map Battle code.
    """

    question_id: int
    grade: int
    unit_name: str | None = None
    unit_done: bool = False
    response_ms: int | None = None
    source_context: str = "practice"
    training_set_id: int | None = None
    is_scaffolding: bool = False
    internal: bool = False
    submission_id: str | None = None


@dataclass(frozen=True, slots=True)
class ReviewOutcome:
    """Plain result data handed to the pure legacy serializer."""

    kind: ReviewOutcomeKind
    payload: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Snapshot the top-level mapping so a caller cannot mutate the outcome
        # through the original legacy result after adaptation.  Nested values
        # are intentionally left untouched: serialization preserves their
        # existing types and missing-vs-null semantics exactly.
        object.__setattr__(self, "payload", dict(self.payload))

    @classmethod
    def public_full(cls, payload: Mapping[str, Any]) -> "ReviewOutcome":
        return cls(ReviewOutcomeKind.PUBLIC_FULL, payload)

    @classmethod
    def public_core(cls, payload: Mapping[str, Any]) -> "ReviewOutcome":
        return cls(ReviewOutcomeKind.PUBLIC_CORE, payload)

    @classmethod
    def internal_duplicate(cls, payload: Mapping[str, Any]) -> "ReviewOutcome":
        return cls(ReviewOutcomeKind.INTERNAL_DUPLICATE, payload)


__all__ = [
    "CORE_20_FIELDS",
    "T2_OPTIONAL_FIELDS",
    "FULL_26_FIELDS",
    "INTERNAL_DUPLICATE_4_FIELDS",
    "ReviewCommand",
    "ReviewOutcome",
    "ReviewOutcomeKind",
]
