"""Server-bound identities for D5B question and capacity retries.

These helpers intentionally do not decide whether an answer is correct or
whether an item may be consumed.  They only validate/bind a retry identity to
the authenticated server-side player and produce a stable digest for
same-id/different-payload conflict detection.
"""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
import re
import uuid
from typing import Any


IDENTITY_MAX_LENGTH = 128
IDENTITY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class IdempotencyIdentityError(ValueError):
    """A retry identity is malformed or outside the server contract."""


def normalize_identity(
    value: Any,
    *,
    field: str,
    generate_if_missing: bool = True,
) -> tuple[str, bool]:
    """Return ``(identity, generated)`` after server-side validation.

    A caller-provided value is only an idempotency proposal.  The caller's
    authenticated player binding is supplied separately by the server and is
    enforced by the database uniqueness key at each business boundary.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        if not generate_if_missing:
            raise IdempotencyIdentityError(f"{field} is required")
        return f"srv-{uuid.uuid4().hex}", True
    if not isinstance(value, str):
        raise IdempotencyIdentityError(f"{field} must be a string")
    identity = value.strip()
    if len(identity) > IDENTITY_MAX_LENGTH or not IDENTITY_PATTERN.fullmatch(identity):
        raise IdempotencyIdentityError(
            f"{field} must match {IDENTITY_PATTERN.pattern} and be at most "
            f"{IDENTITY_MAX_LENGTH} characters"
        )
    return identity, False


def canonical_payload_digest(payload: Mapping[str, Any]) -> str:
    """Hash the normalized logical request, not client correctness claims."""
    if not isinstance(payload, Mapping):
        raise TypeError("payload must be a mapping")
    try:
        encoded = json.dumps(
            dict(payload),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("idempotency payload must be JSON serializable") from exc
    return hashlib.sha256(encoded).hexdigest()


def insert_review_log_with_identity(
    conn: Any,
    *,
    user_id: int,
    question_id: int,
    grade: int,
    topic: str,
    level: str,
    difficulty: str,
    reviewed_at: str,
    response_ms: int | None,
    discipline: str,
    player_rating_snapshot: float | None,
    question_rating_snapshot: float | None,
    item_rating_version: str,
    question_version: str,
    source_context: str,
    is_scaffolding: int,
    training_set_id: int | None,
    submission_id: str,
    submission_payload_hash: str,
) -> dict[str, Any]:
    """Insert one canonical review identity without aborting a retry.

    ``ON CONFLICT DO NOTHING`` is intentionally broad only within this
    append-style review row: the primary key and the D5B partial unique index
    are the expected conflict surfaces.  The caller compares the recovered
    digest and owns the surrounding business transaction.
    """
    inserted = conn.execute(
        """INSERT INTO review_log(
               user_id,question_id,grade,topic,level,difficulty,reviewed_at,
               response_ms,discipline,player_rating_snapshot,
               question_rating_snapshot,item_rating_version,question_version,
               source_context,is_scaffolding,training_set_id,
               submission_id,submission_payload_hash)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT DO NOTHING""",
        (
            user_id,
            question_id,
            grade,
            topic,
            level,
            difficulty,
            reviewed_at,
            response_ms,
            discipline,
            player_rating_snapshot,
            question_rating_snapshot,
            item_rating_version,
            question_version,
            source_context,
            is_scaffolding,
            training_set_id,
            submission_id,
            submission_payload_hash,
        ),
    )
    if getattr(inserted, "rowcount", 0) == 1:
        return {"inserted": True, "existing": None}
    existing = conn.execute(
        """SELECT submission_id, question_id, grade, submission_payload_hash,
                          source_context
             FROM review_log
            WHERE user_id=? AND submission_id=?""",
        (user_id, submission_id),
    ).fetchone()
    if existing is None:
        raise RuntimeError("review submission uniqueness result is not recoverable")
    return {"inserted": False, "existing": existing}


__all__ = [
    "IDENTITY_MAX_LENGTH",
    "IDENTITY_PATTERN",
    "IdempotencyIdentityError",
    "canonical_payload_digest",
    "insert_review_log_with_identity",
    "normalize_identity",
]
