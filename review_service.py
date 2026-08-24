"""V1A2/V1A3 ReviewService: the review application-service boundary.

This module is the seam described in
``docs/planning/e10_backend_v1a2_reviewservice_implementation_packet.md``.
It owns dispatching a typed command to the one existing durable review
operation and classifying its result -- nothing else.

The existing operation (injected as ``legacy_operation``, concretely
``app.py``'s ``_srs_review_operation``) remains the sole durable authority.
This module never imports ``app.py`` -- the operation is passed in at
construction time -- so there is no import cycle and no ambiguity about
which function actually writes ``srs_cards``/``review_log``/etc.

What this module owns:
    * dispatching a public or internal ``ReviewCommand`` to the injected
      legacy operation, exactly once per call to ``ReviewService.review``;
    * classifying the result into SUCCESS/REJECTED/ERROR and, for a
      success, into the FULL26/CORE20/DUP4 shape (via the existing pure
      ``review_compatibility``/``legacy_review_serializer`` adapters);
    * enforcing that a DUP4 result can only ever come from an internal
      call (mirrors the existing ``adapt_legacy_review_result`` guard);
    * formalizing the MapBattle -> Review cross-domain handoff
      (``MapBattleReviewHandoff``) as an explicit port, without absorbing
      MapBattle's own settlement authority.

What this module does not own (V1A2/V1A3 boundary, unchanged from the
accepted backend packet):
    * Flask request parsing, session/authentication, or user lookup -- the
      caller supplies an already-authenticated ``user_id``; ``ReviewCommand``
      has no actor field;
    * a database connection, transaction lifecycle, or commit/rollback
      policy -- ``_srs_review_operation`` remains the only place that opens
      ``get_db()`` for review writes;
    * any reward, XP, badge, loot, quest, or Grimoire business logic;
    * MapBattle settlement, nonce reservation, or the MapBattle response
      contract -- ``settle_answer``/``settle_map_battle_submission`` are
      untouched and this module is never given settlement authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Protocol

from legacy_review_serializer import LegacyReviewSerializer
from review_compatibility import adapt_legacy_review_result
from review_contracts import (
    EXTERNAL_AUTHORITATIVE_MAP_BATTLE,
    ReviewCommand,
    ReviewOutcomeKind,
)


class ReviewServiceStatus(str, Enum):
    """Service-facing result classification (backend packet, section 3)."""

    SUCCESS = "SUCCESS"
    REJECTED = "REJECTED"
    ERROR = "ERROR"


# Maps a successful legacy shape (already classified by the existing pure
# adapter) to the service-facing shape label the packet names.
_SHAPE_LABEL_BY_OUTCOME_KIND: dict[ReviewOutcomeKind, str] = {
    ReviewOutcomeKind.PUBLIC_FULL: "FULL26",
    ReviewOutcomeKind.PUBLIC_CORE: "CORE20",
    ReviewOutcomeKind.INTERNAL_DUPLICATE: "DUP4",
}

# The legacy operation's own documented intentional-rejection statuses
# (backend packet section 3, "Rejected and error outcomes"): 401
# unauthenticated, 400 parameter/source/Boss errors, 403 Premium/training
# item, 409 invalid settled submission, 429 free daily limit. Anything else
# non-200 is an unexpected operation/adapter failure (ERROR), matching the
# packet's own status/error split -- this module does not add a broad catch
# that changes current 5xx behavior.
_REJECTED_HTTP_STATUSES = frozenset({400, 401, 403, 409, 429})


@dataclass(frozen=True, slots=True)
class ReviewServiceOutcome:
    """The service's classified result. Callers never see the raw Flask
    response the legacy operation produced -- only this typed outcome."""

    status: ReviewServiceStatus
    shape: str | None
    payload: Mapping[str, Any]
    http_status: int
    error_code: str | None = None
    retryable: bool = False

    def __post_init__(self) -> None:
        # Same defensive snapshot discipline as review_contracts.ReviewOutcome:
        # a caller must not be able to mutate this outcome's payload through
        # a reference to the original legacy result.
        object.__setattr__(self, "payload", dict(self.payload))


class LegacyReviewOperation(Protocol):
    """The one durable-write port this service is allowed to call.

    ``app.py``'s ``_srs_review_operation`` is the only production
    implementation. This Protocol exists so review_service.py can be
    imported and unit-tested (see review_contracts.py's own docstring: pure
    modules import no Flask/database module) without ever importing app.py,
    and so a test can substitute a spy/stub that proves the service calls
    this port exactly once per review -- see
    tests/test_e10_backend_review_service_v1a2.py's
    RUNTIME_TRANSACTION_CHARACTERIZATION cases.
    """

    def __call__(
        self,
        uid: int,
        data: Mapping[str, Any],
        *,
        internal: bool = False,
        submission_id: str | None = None,
    ) -> Any:
        ...


def _unwrap_legacy_response(response: Any) -> tuple[int, Mapping[str, Any]]:
    """Extract (http_status, json_payload) from whatever the legacy
    operation returned. ``_srs_review_operation`` returns either a bare
    Flask Response (implicit 200) or a ``(Response, status)`` tuple --
    exactly Flask's own view-function return convention, unchanged here."""
    if isinstance(response, tuple):
        body, status = response[0], int(response[1])
    else:
        body, status = response, 200
    payload = body.get_json(silent=True) if hasattr(body, "get_json") else None
    if not isinstance(payload, Mapping):
        payload = {}
    return status, payload


class ReviewService:
    """Thin orchestration boundary in front of the existing durable
    review operation. See module docstring for the full owns/does-not-own
    split."""

    def __init__(self, legacy_operation: LegacyReviewOperation) -> None:
        self._legacy_operation = legacy_operation

    def review(self, *, user_id: int, command: ReviewCommand) -> ReviewServiceOutcome:
        """Execute one public or post-settlement internal review.

        Calls the injected legacy operation exactly once. Never opens a
        database connection, never retries, never mutates ``command``.
        """
        data = self._command_to_legacy_data(command)
        response = self._legacy_operation(
            user_id,
            data,
            internal=command.internal,
            submission_id=command.submission_id,
        )
        http_status, payload = _unwrap_legacy_response(response)

        if http_status != 200:
            error_code = payload.get("error") if isinstance(payload, Mapping) else None
            status = (
                ReviewServiceStatus.REJECTED
                if http_status in _REJECTED_HTTP_STATUSES
                else ReviewServiceStatus.ERROR
            )
            return ReviewServiceOutcome(
                status=status,
                shape=None,
                payload=payload,
                http_status=http_status,
                error_code=error_code if isinstance(error_code, str) else None,
                retryable=False,
            )

        # D5B public retry acknowledgement.  This is a committed review
        # result, not the internal MapBattle DUP4 handoff and not a second
        # durable write.  Keep it outside the legacy FULL26/CORE20 adapter.
        if (
            not command.internal
            and payload.get("ok") is True
            and payload.get("submission_duplicate") is True
        ):
            return ReviewServiceOutcome(
                status=ReviewServiceStatus.SUCCESS,
                shape="PUBLIC_SUBMISSION_DUPLICATE",
                payload=payload,
                http_status=200,
            )

        outcome = adapt_legacy_review_result(payload, internal=command.internal)
        serialized = LegacyReviewSerializer.serialize(outcome)
        return ReviewServiceOutcome(
            status=ReviewServiceStatus.SUCCESS,
            shape=_SHAPE_LABEL_BY_OUTCOME_KIND[outcome.kind],
            payload=serialized,
            http_status=200,
        )

    @staticmethod
    def _command_to_legacy_data(command: ReviewCommand) -> dict[str, Any]:
        """The exact field set _srs_review_operation's ``data`` parsing
        reads (app.py:11700-11729): question_id, grade, unit_name,
        unit_done, response_ms, source_context, training_set_id,
        is_scaffolding. ``internal``/``submission_id`` are passed as
        keyword arguments to the operation itself, not through ``data``
        (matching the existing internal call shape at
        ``_run_map_battle_progression``, app.py:12224-12232)."""
        return {
            "question_id": command.question_id,
            "grade": command.grade,
            "unit_name": command.unit_name,
            "unit_done": command.unit_done,
            "response_ms": command.response_ms,
            "source_context": command.source_context,
            "training_set_id": command.training_set_id,
            "is_scaffolding": command.is_scaffolding,
            **(
                {"combat_settlement_context": command.combat_settlement_context}
                if command.combat_settlement_context is not None
                else {}
            ),
        }


class MapBattleReviewHandoff:
    """V1A3: makes the MapBattle -> Review cross-domain handoff an explicit,
    named port instead of an inline direct call to the legacy operation.

    This class owns nothing new: it only shapes a settled MapBattle result
    into the same internal ``ReviewCommand``/outcome round trip the public
    route also uses, through the same ``ReviewService``. It never reserves
    a nonce, judges an answer, or writes battle/submission/attempt state --
    that remains the MapBattle persistence and runtime modules' authority,
    called before this handoff ever runs (matches the backend packet
    section 7's documented settle-then-progress ordering).
    """

    def __init__(self, service: ReviewService) -> None:
        self._service = service

    def apply(self, *, user_id: int, settlement: Mapping[str, Any]) -> ReviewServiceOutcome:
        command = ReviewCommand(
            question_id=settlement.get("question_id"),
            grade=settlement.get("authoritative_grade"),
            internal=True,
            submission_id=settlement.get("submission_id"),
            combat_settlement_context=EXTERNAL_AUTHORITATIVE_MAP_BATTLE,
        )
        return self._service.review(user_id=user_id, command=command)


__all__ = [
    "LegacyReviewOperation",
    "MapBattleReviewHandoff",
    "ReviewService",
    "ReviewServiceOutcome",
    "ReviewServiceStatus",
]
