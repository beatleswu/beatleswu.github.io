"""Authority decisions for the legacy public SRS review transport.

The public ``/api/srs/review`` request carries a client-reported SRS grade,
but this path has no server-judged answer evidence.  The grade therefore
remains usable as the legacy SM-2 scheduling input only; it must not be
promoted to correctness or progression authority.

This module is deliberately pure.  It does not judge answers, open a
database connection, mutate state, or import ``app``.  A trusted route/service
caller can use the returned decision to keep scheduling and gate all
correctness-dependent mutations.  Map Battle's existing server-owned judge is
outside this policy and must continue to use its own settled-result handoff.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final


PUBLIC_REVIEW_NO_SERVER_JUDGE: Final[str] = "LEGACY_PUBLIC_REVIEW_NO_SERVER_JUDGE"
PUBLIC_SRS_GRADES: Final[frozenset[int]] = frozenset({0, 3, 5})


class PublicSrsReviewAuthorityError(ValueError):
    """Raised when a public review scheduling grade is not valid transport."""


@dataclass(frozen=True, slots=True)
class PublicSrsReviewAuthority:
    """Trusted policy result for one public legacy review request.

    ``scheduling_grade`` is intentionally separate from correctness.  The
    public request has no server answer evidence, so the latter is always
    ``None`` and correctness-dependent progression is always ineligible.
    """

    scheduling_grade: int
    authoritative_answer_correct: bool | None = None
    progress_eligible: bool = False
    correctness_source: str = PUBLIC_REVIEW_NO_SERVER_JUDGE


def resolve_public_srs_review_authority(grade: Any) -> PublicSrsReviewAuthority:
    """Return the fail-closed authority decision for a public SRS grade.

    The accepted values mirror the existing public operation's explicit
    scheduling validation (0, 3, and 5).  This function does not interpret
    those values as answer correctness and never grants progression authority.
    """

    if type(grade) is not int or grade not in PUBLIC_SRS_GRADES:
        raise PublicSrsReviewAuthorityError("public SRS grade is invalid")
    return PublicSrsReviewAuthority(scheduling_grade=grade)


__all__ = [
    "PUBLIC_REVIEW_NO_SERVER_JUDGE",
    "PUBLIC_SRS_GRADES",
    "PublicSrsReviewAuthority",
    "PublicSrsReviewAuthorityError",
    "resolve_public_srs_review_authority",
]
