"""Daily Challenge integration with the canonical D5B submission identity.

The D5B ``review_log(user_id, submission_id)`` identity is the only
submission uniqueness authority used here.  The existing ``source_context``
text column carries a compact, committed Daily response envelope so a
response-loss retry can return the original result without adding a Daily
idempotency table or making the outbox authoritative.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from question_idempotency import (
    IdempotencyIdentityError,
    canonical_payload_digest,
    insert_review_log_with_identity,
    normalize_identity,
)


DAILY_D5B_SOURCE_PREFIX = "daily_d5b:v1:"
DAILY_D5B_PENDING_SOURCE = DAILY_D5B_SOURCE_PREFIX + "pending"


class DailySubmissionConflict(ValueError):
    """The D5B identity was reused for a different logical request."""

    def __init__(self, submission_id: str):
        super().__init__("submission_id is already bound to a different Daily result")
        self.submission_id = submission_id


class DailyReplayUnavailable(RuntimeError):
    """A committed D5B identity has no recoverable Daily result envelope."""

    def __init__(self, submission_id: str):
        super().__init__("committed Daily result is not recoverable")
        self.submission_id = submission_id


def normalize_daily_submission_id(value: Any) -> tuple[str, bool]:
    """Validate a client proposal or generate a server-side D5B identity."""

    try:
        return normalize_identity(value, field="submission_id")
    except IdempotencyIdentityError:
        raise


def daily_submission_payload(data: Mapping[str, Any]) -> dict[str, Any]:
    """Return the logical retry payload; client correctness is diagnostic only."""

    if not isinstance(data, Mapping):
        raise TypeError("Daily submission payload must be a mapping")
    return {
        "flow": "DAILY_CHALLENGE",
        "attempt_token": data.get("attempt_token"),
        "moves": data.get("moves"),
    }


def daily_submission_payload_hash(data: Mapping[str, Any]) -> str:
    """Hash answer/attempt evidence, deliberately excluding ``correct``."""

    return canonical_payload_digest(daily_submission_payload(data))


def _row_value(row: Any, key: str, index: int = 0) -> Any:
    if row is None:
        return None
    try:
        return row[key]
    except (KeyError, TypeError, IndexError):
        return row[index]


def _load_submission(conn: Any, *, user_id: int, submission_id: str) -> Any:
    return conn.execute(
        """SELECT submission_id, question_id, grade,
                          submission_payload_hash, source_context, reviewed_at
             FROM review_log
            WHERE user_id=? AND submission_id=?""",
        (int(user_id), submission_id),
    ).fetchone()


def _decode_result(source_context: Any) -> dict[str, Any] | None:
    if not isinstance(source_context, str) or not source_context.startswith(
        DAILY_D5B_SOURCE_PREFIX
    ):
        return None
    encoded = source_context[len(DAILY_D5B_SOURCE_PREFIX) :]
    if not encoded or encoded == "pending":
        return None
    try:
        result = json.loads(encoded)
    except (TypeError, ValueError):
        return None
    return dict(result) if isinstance(result, Mapping) else None


def load_daily_replay(
    conn: Any,
    *,
    user_id: int,
    submission_id: str,
    payload_hash: str,
) -> dict[str, Any] | None:
    """Return the committed original result, or ``None`` if identity is new."""

    row = _load_submission(conn, user_id=user_id, submission_id=submission_id)
    if row is None:
        return None
    stored_hash = _row_value(row, "submission_payload_hash", 3)
    if stored_hash != payload_hash:
        raise DailySubmissionConflict(submission_id)
    result = _decode_result(_row_value(row, "source_context", 4))
    if result is None:
        raise DailyReplayUnavailable(submission_id)
    return result


def reserve_daily_submission(
    conn: Any,
    *,
    user_id: int,
    question_id: int,
    question_revision: str,
    server_correct: bool,
    reviewed_at: str,
    submission_id: str,
    payload_hash: str,
) -> dict[str, Any]:
    """Reserve or replay one D5B identity inside the caller transaction."""

    inserted = insert_review_log_with_identity(
        conn,
        user_id=int(user_id),
        question_id=int(question_id),
        grade=5 if server_correct else 0,
        topic="daily_challenge",
        level="",
        difficulty="",
        reviewed_at=reviewed_at,
        response_ms=None,
        discipline="whole_board",
        player_rating_snapshot=None,
        question_rating_snapshot=None,
        item_rating_version="daily-d5b-v1",
        question_version=str(question_revision),
        source_context=DAILY_D5B_PENDING_SOURCE,
        is_scaffolding=0,
        training_set_id=None,
        submission_id=submission_id,
        submission_payload_hash=payload_hash,
    )
    if inserted["inserted"]:
        return {"inserted": True, "result": None}

    row = _load_submission(conn, user_id=int(user_id), submission_id=submission_id)
    if row is None:
        raise DailyReplayUnavailable(submission_id)
    stored_hash = _row_value(row, "submission_payload_hash", 3)
    if stored_hash != payload_hash:
        raise DailySubmissionConflict(submission_id)
    result = _decode_result(_row_value(row, "source_context", 4))
    if result is None:
        raise DailyReplayUnavailable(submission_id)
    return {"inserted": False, "result": result}


def persist_daily_result(
    conn: Any,
    *,
    user_id: int,
    submission_id: str,
    result: Mapping[str, Any],
) -> None:
    """Persist the replay envelope before the caller commits side effects."""

    encoded = json.dumps(
        dict(result), ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    )
    source_context = DAILY_D5B_SOURCE_PREFIX + encoded
    updated = conn.execute(
        """UPDATE review_log
              SET source_context=?
            WHERE user_id=? AND submission_id=?
              AND source_context=?""",
        (source_context, int(user_id), submission_id, DAILY_D5B_PENDING_SOURCE),
    )
    if getattr(updated, "rowcount", 0) != 1:
        raise DailyReplayUnavailable(submission_id)


__all__ = [
    "DAILY_D5B_PENDING_SOURCE",
    "DAILY_D5B_SOURCE_PREFIX",
    "DailyReplayUnavailable",
    "DailySubmissionConflict",
    "daily_submission_payload",
    "daily_submission_payload_hash",
    "load_daily_replay",
    "normalize_daily_submission_id",
    "persist_daily_result",
    "reserve_daily_submission",
]
