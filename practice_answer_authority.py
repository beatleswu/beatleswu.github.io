"""Server-owned public-practice answer authority for Incident 002.

The legacy ``/api/srs/review`` transport remains a scheduling-only path.  This
module supplies the additive answer boundary used by the corrective path:

* a server-signed attempt binds the authenticated user, legacy qid, canonical
  ``source_record_uuid``, question revision, board context, and one nonce;
* the client submits only moves;
* the existing SGF judge decides CORRECT/INCORRECT;
* the nonce becomes the review submission identity and trusted source marker.

This module is deliberately free of Flask and database code.  It never mints
or changes puzzle identity, and it never accepts a client correctness or trust
claim.  Persistence and existing SRS transaction policy stay with the caller.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import secrets
from collections.abc import Mapping
from typing import Any

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from map_battle_runtime import (
    CanonicalAnswer,
    JudgeOutcome,
    JudgeUnavailable,
    MAP_BATTLE_JUDGE_VERSION,
    MapBattleRuntimeError,
    RequestRejected,
    canonicalize_answer,
    judge_map_battle_answer_v1,
    question_revision_for,
)


PRACTICE_ATTEMPT_VERSION = "practice-attempt-v1"
PRACTICE_ATTEMPT_FLOW = "PUBLIC_PRACTICE"
PRACTICE_ATTEMPT_SALT = "go-odyssey.practice.attempt.v1"
PRACTICE_ATTEMPT_TTL_SECONDS = 24 * 60 * 60
PRACTICE_JUDGE_VERSION = MAP_BATTLE_JUDGE_VERSION

# This namespace is additive.  It is accepted only by readers that explicitly
# opt into the new server-judged practice contract; the old public route never
# accepts it from a request body.
PRACTICE_TRUSTED_SOURCE_CONTEXT_PREFIX = "practice:v1:"
PRACTICE_SUBMISSION_PREFIX = "practice-v1:"
PRACTICE_SOURCE_CONTEXT_MAX_LENGTH = 40

_ANSWER_FIELDS = frozenset({"moves"})
_FORBIDDEN_AUTHORITY_FIELDS = frozenset(
    {
        "grade",
        "correct",
        "is_correct",
        "authoritative_grade",
        "server_verified",
        "trusted",
        "trusted_server_evidence",
        "source_context",
        "source",
        "progress_eligible",
        "server_judge",
        "judge_result",
    }
)


class PracticeAttemptError(ValueError):
    """Expected fail-closed error exposed by the practice route."""

    def __init__(
        self,
        code: str,
        *,
        status: int = 409,
        retryable: bool = False,
        reason_code: str | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.status = status
        self.retryable = retryable
        self.reason_code = reason_code or code


def _serializer(secret_key: Any) -> URLSafeTimedSerializer:
    if not secret_key:
        raise PracticeAttemptError("practice_attempt_signing_unavailable", status=503)
    return URLSafeTimedSerializer(secret_key, salt=PRACTICE_ATTEMPT_SALT)


def _epoch(value: Any = None) -> int:
    if value is None:
        return int(datetime.now(timezone.utc).timestamp())
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return int(value.timestamp())
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise PracticeAttemptError("practice_attempt_invalid") from error


def _required_context_value(context: Mapping[str, Any], key: str) -> Any:
    value = context.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        raise PracticeAttemptError("practice_attempt_context_invalid", status=503)
    return value


def issue_practice_attempt(
    secret_key: Any,
    *,
    user_id: int,
    question: Mapping[str, Any],
    source_record_uuid: str,
    question_context: Mapping[str, Any],
    now: Any = None,
) -> str:
    """Issue one signed, server-bound public-practice answer event."""

    if not isinstance(question, Mapping):
        raise PracticeAttemptError("practice_question_invalid", status=503)
    try:
        normalized_user_id = int(user_id)
        question_id = int(question["id"])
        board_size = int(_required_context_value(question_context, "board_size"))
        player_color = str(
            _required_context_value(question_context, "player_color")
        ).upper()
        revision = str(
            _required_context_value(question_context, "question_revision")
        )
    except (KeyError, TypeError, ValueError) as error:
        raise PracticeAttemptError("practice_attempt_context_invalid", status=503) from error
    canonical_uuid = str(source_record_uuid or "").strip()
    if normalized_user_id <= 0 or question_id < 0:
        raise PracticeAttemptError("practice_attempt_context_invalid", status=503)
    if not (2 <= board_size <= 25) or player_color not in {"B", "W"}:
        raise PracticeAttemptError("practice_attempt_context_invalid", status=503)
    if not canonical_uuid:
        raise PracticeAttemptError("practice_identity_unavailable", status=503)
    try:
        if question_revision_for(question) != revision:
            raise PracticeAttemptError("practice_question_revision_unavailable", status=503)
    except MapBattleRuntimeError as error:
        raise PracticeAttemptError("practice_question_revision_unavailable", status=503) from error

    issued_at = _epoch(now)
    expires_at = issued_at + PRACTICE_ATTEMPT_TTL_SECONDS
    payload = {
        "version": PRACTICE_ATTEMPT_VERSION,
        "flow": PRACTICE_ATTEMPT_FLOW,
        "user_id": normalized_user_id,
        "question_id": question_id,
        "source_record_uuid": canonical_uuid,
        "question_revision": revision,
        "board_size": board_size,
        "player_color": player_color,
        "transform_id": str(question_context.get("transform_id") or "identity"),
        "transform_version": str(
            question_context.get("transform_version") or PRACTICE_ATTEMPT_VERSION
        ),
        "issued_at": issued_at,
        "expires_at": expires_at,
        # This is the answer-event identity.  A later issued attempt has a
        # different nonce even when it names the same canonical question.
        "nonce": secrets.token_urlsafe(18),
    }
    return _serializer(secret_key).dumps(payload)


def verify_practice_attempt(
    secret_key: Any,
    token: Any,
    *,
    user_id: int,
    question_id: int | None = None,
    question_revision: str | None = None,
    source_record_uuid: str | None = None,
    now: Any = None,
) -> dict[str, Any]:
    """Verify ownership, identity binding, revision, and expiry."""

    if not isinstance(token, str) or not token.strip():
        raise PracticeAttemptError("practice_attempt_required", status=400)
    try:
        # Production calls retain itsdangerous' own timestamp TTL.  A caller
        # supplying ``now`` is the deterministic test/shadow clock; the signed
        # payload expiry below remains the authority for that clock.
        payload = _serializer(secret_key).loads(
            token,
            **({} if now is not None else {"max_age": PRACTICE_ATTEMPT_TTL_SECONDS}),
        )
    except SignatureExpired as error:
        raise PracticeAttemptError("practice_attempt_expired") from error
    except BadSignature as error:
        raise PracticeAttemptError("practice_attempt_invalid") from error
    if not isinstance(payload, dict):
        raise PracticeAttemptError("practice_attempt_invalid")

    required = (
        "version",
        "flow",
        "user_id",
        "question_id",
        "source_record_uuid",
        "question_revision",
        "board_size",
        "player_color",
        "transform_id",
        "transform_version",
        "issued_at",
        "expires_at",
        "nonce",
    )
    if any(key not in payload for key in required):
        raise PracticeAttemptError("practice_attempt_invalid")
    if payload.get("version") != PRACTICE_ATTEMPT_VERSION:
        raise PracticeAttemptError("practice_attempt_version_unsupported")
    if payload.get("flow") != PRACTICE_ATTEMPT_FLOW:
        raise PracticeAttemptError("practice_attempt_flow_mismatch")
    try:
        normalized_user_id = str(int(user_id))
        normalized_question_id = (
            str(int(question_id)) if question_id is not None else None
        )
    except (TypeError, ValueError) as error:
        raise PracticeAttemptError("practice_attempt_invalid") from error
    if str(payload.get("user_id")) != normalized_user_id:
        raise PracticeAttemptError("practice_attempt_user_mismatch")
    if (
        normalized_question_id is not None
        and str(payload.get("question_id")) != normalized_question_id
    ):
        raise PracticeAttemptError("practice_attempt_question_mismatch")
    if question_revision is not None and payload.get("question_revision") != question_revision:
        raise PracticeAttemptError("practice_attempt_stale_question")
    if source_record_uuid is not None and payload.get("source_record_uuid") != source_record_uuid:
        raise PracticeAttemptError("practice_attempt_identity_mismatch")
    if not isinstance(payload.get("source_record_uuid"), str) or not payload["source_record_uuid"].strip():
        raise PracticeAttemptError("practice_identity_unavailable")
    if not isinstance(payload.get("nonce"), str) or len(payload["nonce"]) < 16:
        raise PracticeAttemptError("practice_attempt_invalid")
    try:
        issued_at = int(payload["issued_at"])
        expires_at = int(payload["expires_at"])
        board_size = int(payload["board_size"])
        current = _epoch(now)
    except (TypeError, ValueError) as error:
        raise PracticeAttemptError("practice_attempt_invalid") from error
    if not (2 <= board_size <= 25):
        raise PracticeAttemptError("practice_attempt_invalid")
    if payload.get("player_color") not in {"B", "W"}:
        raise PracticeAttemptError("practice_attempt_invalid")
    if issued_at > current or expires_at <= current or expires_at <= issued_at:
        raise PracticeAttemptError("practice_attempt_expired")
    if expires_at - issued_at > PRACTICE_ATTEMPT_TTL_SECONDS:
        raise PracticeAttemptError("practice_attempt_invalid")
    return payload


def _reject_unexpected_answer_fields(answer: Mapping[str, Any]) -> None:
    unexpected = set(answer).difference(_ANSWER_FIELDS)
    forbidden = unexpected.intersection(_FORBIDDEN_AUTHORITY_FIELDS)
    if forbidden:
        raise PracticeAttemptError("forbidden_answer_field", status=400)
    if unexpected:
        raise PracticeAttemptError("forbidden_answer_field", status=400)


def canonicalize_practice_answer(
    answer: Mapping[str, Any],
    attempt: Mapping[str, Any],
) -> CanonicalAnswer:
    """Canonicalize moves while deriving every authority field server-side."""

    if not isinstance(answer, Mapping):
        raise PracticeAttemptError("practice_answer_required", status=400)
    _reject_unexpected_answer_fields(answer)
    if "moves" not in answer:
        raise PracticeAttemptError("practice_answer_required", status=400)

    try:
        nonce = str(_required_context_value(attempt, "nonce"))
        question_revision = str(_required_context_value(attempt, "question_revision"))
        player_color = str(_required_context_value(attempt, "player_color")).upper()
        board_size = int(_required_context_value(attempt, "board_size"))
    except (TypeError, ValueError) as error:
        raise PracticeAttemptError("practice_attempt_invalid") from error
    if not (2 <= board_size <= 25) or player_color not in {"B", "W"}:
        raise PracticeAttemptError("practice_attempt_invalid")

    # ``canonicalize_answer`` is reused only after the server has constructed
    # all metadata.  No client-supplied authority field enters this mapping.
    server_payload = {
        "battle_id": f"practice:{attempt['source_record_uuid']}",
        "attempt_id": nonce,
        "submission_nonce": nonce,
        "battle_revision": 0,
        "question_revision": question_revision,
        "player_color": player_color,
        "transform_id": str(attempt.get("transform_id") or "identity"),
        "transform_version": str(
            attempt.get("transform_version") or PRACTICE_ATTEMPT_VERSION
        ),
        "moves": answer.get("moves"),
    }
    try:
        canonical = canonicalize_answer(server_payload, attempt)
    except RequestRejected as error:
        raise PracticeAttemptError(
            "malformed_answer", status=400, reason_code="client_answer_invalid"
        ) from error
    except MapBattleRuntimeError as error:
        raise PracticeAttemptError(
            "malformed_answer", status=400, reason_code="canonicalization_failed"
        ) from error
    if canonical.is_invalid:
        raise PracticeAttemptError(
            "malformed_answer", status=400, reason_code=canonical.reason_code
        )
    return canonical


def judge_practice_answer(
    question: Mapping[str, Any],
    attempt: Mapping[str, Any],
    answer: CanonicalAnswer,
) -> JudgeOutcome:
    """Use the existing server-only SGF judge; never accept client grade."""

    try:
        outcome = judge_map_battle_answer_v1(question, attempt, answer)
    except JudgeUnavailable as error:
        raise PracticeAttemptError(
            "judge_unavailable", status=503, retryable=True, reason_code="judge_unavailable"
        ) from error
    if outcome.result not in {"CORRECT", "INCORRECT"}:
        raise PracticeAttemptError(
            "malformed_answer", status=400, reason_code=outcome.reason_code
        )
    if outcome.judge_version != PRACTICE_JUDGE_VERSION:
        raise PracticeAttemptError(
            "judge_unavailable", status=503, retryable=True, reason_code="judge_version_mismatch"
        )
    if outcome.result == "CORRECT" and outcome.authoritative_grade != 5:
        raise PracticeAttemptError(
            "judge_unavailable", status=503, retryable=True, reason_code="invalid_correct_verdict"
        )
    if outcome.result == "INCORRECT" and outcome.authoritative_grade != 0:
        raise PracticeAttemptError(
            "judge_unavailable", status=503, retryable=True, reason_code="invalid_incorrect_verdict"
        )
    return outcome


def practice_submission_id(attempt: Mapping[str, Any]) -> str:
    nonce = str(_required_context_value(attempt, "nonce"))
    value = f"{PRACTICE_SUBMISSION_PREFIX}{nonce}"
    if len(value) > 128:
        raise PracticeAttemptError("practice_attempt_invalid")
    return value


def practice_source_context(attempt: Mapping[str, Any]) -> str:
    nonce = str(_required_context_value(attempt, "nonce"))
    value = f"{PRACTICE_TRUSTED_SOURCE_CONTEXT_PREFIX}{nonce}"
    if len(value) > PRACTICE_SOURCE_CONTEXT_MAX_LENGTH:
        raise PracticeAttemptError("practice_attempt_invalid")
    return value


def practice_submission_payload(
    *,
    attempt: Mapping[str, Any],
    canonical: CanonicalAnswer,
    authoritative_grade: int,
) -> dict[str, Any]:
    """Return the server-derived logical payload used for retry comparison."""

    if authoritative_grade not in (0, 5):
        raise PracticeAttemptError("invalid_authoritative_grade", status=500)
    return {
        "flow": PRACTICE_ATTEMPT_FLOW,
        "question_id": int(_required_context_value(attempt, "question_id")),
        "source_record_uuid": str(_required_context_value(attempt, "source_record_uuid")),
        "attempt_nonce": str(_required_context_value(attempt, "nonce")),
        "authoritative_grade": int(authoritative_grade),
        "judge_version": PRACTICE_JUDGE_VERSION,
        "answer": canonical.payload,
    }


def content_identity_digest(question: Mapping[str, Any]) -> str:
    content = question.get("content")
    if not isinstance(content, str) or not content:
        raise PracticeAttemptError("practice_question_content_unavailable", status=503)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


__all__ = [
    "PRACTICE_ATTEMPT_FLOW",
    "PRACTICE_ATTEMPT_SALT",
    "PRACTICE_ATTEMPT_TTL_SECONDS",
    "PRACTICE_ATTEMPT_VERSION",
    "PRACTICE_JUDGE_VERSION",
    "PRACTICE_SOURCE_CONTEXT_MAX_LENGTH",
    "PRACTICE_SUBMISSION_PREFIX",
    "PRACTICE_TRUSTED_SOURCE_CONTEXT_PREFIX",
    "PracticeAttemptError",
    "canonicalize_practice_answer",
    "content_identity_digest",
    "issue_practice_attempt",
    "judge_practice_answer",
    "practice_source_context",
    "practice_submission_id",
    "practice_submission_payload",
    "verify_practice_attempt",
]
