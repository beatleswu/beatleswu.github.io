"""Server-authoritative Daily Challenge attempt and answer contract.

This module owns only the Daily Challenge transport boundary.  Canonical
question revisions and SGF answer-tree judging remain delegated to the
existing map-battle runtime primitives; this module does not implement a
second Go rules engine.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import secrets
from typing import Any, Mapping

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from map_battle_runtime import (
    CanonicalAnswer,
    JudgeOutcome,
    judge_map_battle_answer_v1,
    question_revision_for,
)


DAILY_ATTEMPT_VERSION = "daily-challenge-attempt-v1"
DAILY_ATTEMPT_FLOW = "DAILY_CHALLENGE"
DAILY_ATTEMPT_SALT = "go-odyssey.daily-challenge.attempt.v1"
DAILY_ATTEMPT_TTL_SECONDS = 24 * 60 * 60
DAILY_JUDGE_VERSION = "map-battle-judge-v1"


class DailyAttemptError(ValueError):
    """Expected Daily attempt/answer failure safe to expose to the client."""

    def __init__(self, code: str, *, status: int = 409):
        super().__init__(code)
        self.code = code
        self.status = status


def _serializer(secret_key: Any) -> URLSafeTimedSerializer:
    if not secret_key:
        raise DailyAttemptError("daily_attempt_signing_unavailable", status=503)
    return URLSafeTimedSerializer(secret_key, salt=DAILY_ATTEMPT_SALT)


def _epoch(value: Any = None) -> int:
    if value is None:
        return int(datetime.now(timezone.utc).timestamp())
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return int(value.timestamp())
    return int(value)


def issue_daily_attempt(
    secret_key: Any,
    *,
    user_id: int,
    challenge_date: str,
    question: Mapping[str, Any],
    question_context: Mapping[str, Any],
    now: Any = None,
) -> str:
    """Issue a signed, stateless attempt bound to the current Daily problem."""

    revision = question_revision_for(question)
    context_revision = str(question_context.get("question_revision") or "")
    if revision != context_revision:
        raise DailyAttemptError("daily_question_revision_unavailable", status=503)
    content = question.get("content")
    if not isinstance(content, str) or not content:
        raise DailyAttemptError("daily_question_content_unavailable", status=503)
    content_sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
    context_content_sha256 = str(question_context.get("initial_position_identity") or "")
    if context_content_sha256 and content_sha256 != context_content_sha256:
        raise DailyAttemptError("daily_question_content_unavailable", status=503)

    try:
        normalized_user_id = int(user_id)
        question_id = int(question["id"])
        board_size = int(question_context["board_size"])
        player_color = str(question_context["player_color"]).upper()
    except (KeyError, TypeError, ValueError) as error:
        raise DailyAttemptError("daily_attempt_context_invalid", status=503) from error
    if normalized_user_id <= 0 or question_id < 0 or not (2 <= board_size <= 25):
        raise DailyAttemptError("daily_attempt_context_invalid", status=503)
    if player_color not in {"B", "W"}:
        raise DailyAttemptError("daily_attempt_context_invalid", status=503)
    if not isinstance(challenge_date, str) or not challenge_date:
        raise DailyAttemptError("daily_attempt_context_invalid", status=503)

    issued_at = _epoch(now)
    expires_at = issued_at + DAILY_ATTEMPT_TTL_SECONDS
    payload = {
        "version": DAILY_ATTEMPT_VERSION,
        "flow": DAILY_ATTEMPT_FLOW,
        "user_id": normalized_user_id,
        "challenge_date": challenge_date,
        "question_id": question_id,
        "question_revision": revision,
        "content_sha256": content_sha256,
        "board_size": board_size,
        "player_color": player_color,
        "transform_id": "identity",
        "transform_version": DAILY_ATTEMPT_VERSION,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "nonce": secrets.token_urlsafe(18),
    }
    return _serializer(secret_key).dumps(payload)


def verify_daily_attempt(
    secret_key: Any,
    token: Any,
    *,
    user_id: int,
    challenge_date: str,
    question_id: int,
    question_revision: str,
    question_content_sha256: str,
    now: Any = None,
) -> dict[str, Any]:
    """Verify ownership, flow, date, question, revision, and expiry."""

    if not isinstance(token, str) or not token.strip():
        raise DailyAttemptError("daily_attempt_required", status=400)
    try:
        payload = _serializer(secret_key).loads(token, max_age=DAILY_ATTEMPT_TTL_SECONDS)
    except SignatureExpired as error:
        raise DailyAttemptError("daily_attempt_expired") from error
    except BadSignature as error:
        raise DailyAttemptError("daily_attempt_invalid") from error
    if not isinstance(payload, dict):
        raise DailyAttemptError("daily_attempt_invalid")

    required = (
        "version", "flow", "user_id", "challenge_date", "question_id",
        "question_revision", "content_sha256", "issued_at", "expires_at", "nonce",
    )
    if any(key not in payload for key in required):
        raise DailyAttemptError("daily_attempt_invalid")
    if payload.get("version") != DAILY_ATTEMPT_VERSION:
        raise DailyAttemptError("daily_attempt_version_unsupported")
    if payload.get("flow") != DAILY_ATTEMPT_FLOW:
        raise DailyAttemptError("daily_attempt_flow_mismatch")
    if str(payload.get("user_id")) != str(int(user_id)):
        raise DailyAttemptError("daily_attempt_user_mismatch")
    if payload.get("challenge_date") != challenge_date:
        raise DailyAttemptError("daily_attempt_date_mismatch")
    if str(payload.get("question_id")) != str(int(question_id)):
        raise DailyAttemptError("daily_attempt_question_mismatch")
    if payload.get("question_revision") != question_revision:
        raise DailyAttemptError("daily_attempt_stale_question")
    if payload.get("content_sha256") != question_content_sha256:
        raise DailyAttemptError("daily_attempt_invalid")
    if not isinstance(payload.get("nonce"), str) or len(payload["nonce"]) < 16:
        raise DailyAttemptError("daily_attempt_invalid")
    try:
        issued_at = int(payload["issued_at"])
        expires_at = int(payload["expires_at"])
        current = _epoch(now)
    except (TypeError, ValueError) as error:
        raise DailyAttemptError("daily_attempt_invalid") from error
    if issued_at > current or expires_at <= current or expires_at <= issued_at:
        raise DailyAttemptError("daily_attempt_expired")
    if expires_at - issued_at > DAILY_ATTEMPT_TTL_SECONDS:
        raise DailyAttemptError("daily_attempt_invalid")
    return payload


def canonicalize_daily_answer(
    payload: Mapping[str, Any],
    attempt: Mapping[str, Any],
) -> CanonicalAnswer:
    """Normalize answer evidence without accepting client result authority."""

    moves = payload.get("moves")
    if not isinstance(moves, list):
        raise DailyAttemptError("daily_answer_moves_required", status=400)
    if len(moves) > 256:
        raise DailyAttemptError("daily_answer_too_long", status=400)
    try:
        board_size = int(attempt["board_size"])
        player_color = str(attempt["player_color"]).upper()
    except (KeyError, TypeError, ValueError) as error:
        raise DailyAttemptError("daily_attempt_invalid", status=409) from error
    if player_color not in {"B", "W"} or not (2 <= board_size <= 25):
        raise DailyAttemptError("daily_attempt_invalid", status=409)

    canonical_moves: list[dict[str, Any]] = []
    for raw in moves:
        if not isinstance(raw, Mapping):
            raise DailyAttemptError("daily_answer_malformed_move", status=400)
        action = str(raw.get("action") or "play").strip().lower()
        if action not in {"play", "move"}:
            raise DailyAttemptError("daily_answer_action_unsupported", status=400)
        x, y = raw.get("x"), raw.get("y")
        if (
            isinstance(x, bool)
            or isinstance(y, bool)
            or not isinstance(x, int)
            or not isinstance(y, int)
        ):
            raise DailyAttemptError("daily_answer_malformed_coordinate", status=400)
        if not (0 <= x < board_size and 0 <= y < board_size):
            raise DailyAttemptError("daily_answer_coordinate_out_of_bounds", status=400)
        canonical_moves.append({"action": "play", "color": player_color, "x": x, "y": y})

    canonical = {
        "battle_id": f"daily:{attempt['challenge_date']}",
        "attempt_id": str(attempt["nonce"]),
        "question_revision": str(attempt["question_revision"]),
        "player_color": player_color,
        "transform_id": "identity",
        "transform_version": DAILY_ATTEMPT_VERSION,
        "battle_revision": 0,
        "moves": canonical_moves,
    }
    return CanonicalAnswer(
        payload=canonical,
        result=None,
        reason_code="empty_sequence" if not canonical_moves else "canonicalized",
    )


def judge_daily_answer(
    question: Mapping[str, Any],
    attempt: Mapping[str, Any],
    answer: CanonicalAnswer,
) -> JudgeOutcome:
    """Judge Daily answers with the existing canonical SGF tree judge."""

    if not answer.payload["moves"]:
        return JudgeOutcome("INCORRECT", 0, DAILY_JUDGE_VERSION, "empty_sequence")
    return judge_map_battle_answer_v1(question, attempt, answer)


def question_content_sha256(question: Mapping[str, Any]) -> str:
    """Expose the canonical content identity for focused contract tests."""

    content = question.get("content")
    if not isinstance(content, str) or not content:
        raise DailyAttemptError("daily_question_content_unavailable", status=503)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


__all__ = [
    "DAILY_ATTEMPT_TTL_SECONDS",
    "DAILY_ATTEMPT_VERSION",
    "DAILY_JUDGE_VERSION",
    "DailyAttemptError",
    "canonicalize_daily_answer",
    "issue_daily_attempt",
    "judge_daily_answer",
    "question_content_sha256",
    "verify_daily_attempt",
]
