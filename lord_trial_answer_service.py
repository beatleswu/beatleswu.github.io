"""Server-owned answer judging and replay facts for E10 Lord Trial.

Lord Trial historically travelled through the public SRS review transport,
where ``grade`` is a scheduling-quality signal.  This module keeps that
legacy field separate from correctness: it adapts the player move payload to
the existing server-only SGF judge and provides a compact, server-written
result envelope for the existing review submission identity.

The result envelope is intentionally persisted in ``review_log.source_context``
only after the answer has been judged.  A client can propose the signed
``boss_trial:<attempt>`` context, but cannot write the ``lord_trial:v1:``
envelope because the public request parser never accepts it as an authority
field.  This mirrors the existing Daily D5B pending/result replay pattern
without adding a new schema or reusing Map Battle's domain tables.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from map_battle_runtime import (
    CanonicalAnswer,
    JudgeOutcome,
    JudgeUnavailable,
    MapBattleRuntimeError,
    canonicalize_answer,
    judge_map_battle_answer_v1,
    question_revision_for,
)


LORD_TRIAL_RESULT_SOURCE_PREFIX = "lord_trial:v1:"
LORD_TRIAL_PENDING_SOURCE = LORD_TRIAL_RESULT_SOURCE_PREFIX + "pending"
LORD_TRIAL_JUDGE_VERSION = "lord-trial-map-battle-judge-v1"
_LORD_TRIAL_RESULT_KEYS = frozenset({
    "schema",
    "attempt_id",
    "question_id",
    "verdict",
    "authoritative_grade",
    "judge_version",
    "reason_code",
})
_LORD_TRIAL_VERDICTS = frozenset({"AUTHORITATIVE_PASS", "AUTHORITATIVE_FAIL"})
_SIZE_RE = re.compile(r"SZ\[(\d+)\]", re.IGNORECASE)
_PLAYER_RE = re.compile(r"PL\[([BW])\]", re.IGNORECASE)


class LordTrialAnswerError(ValueError):
    """Expected fail-closed answer error exposed by the route."""

    def __init__(self, code: str, *, status: int = 400, retryable: bool = False):
        self.code = code
        self.status = status
        self.retryable = retryable
        super().__init__(code)


class LordTrialVerdictPersistenceError(RuntimeError):
    """A judged result could not be bound to its durable review identity."""


def _attempt_value(exam: Mapping[str, Any], key: str) -> str:
    value = exam.get(key)
    if not isinstance(value, str) or not value.strip():
        raise LordTrialAnswerError("invalid_boss_attempt_context")
    return value.strip()


def _question_board_context(question: Mapping[str, Any]) -> tuple[int, str]:
    content = question.get("content")
    if not isinstance(content, str) or not content.strip():
        raise LordTrialAnswerError("judge_unavailable", status=503, retryable=True)
    size_match = _SIZE_RE.search(content)
    player_match = _PLAYER_RE.search(content)
    try:
        board_size = int(size_match.group(1)) if size_match else 19
    except (AttributeError, TypeError, ValueError) as error:
        raise LordTrialAnswerError("judge_unavailable", status=503, retryable=True) from error
    player_color = player_match.group(1).upper() if player_match else None
    if not (2 <= board_size <= 25) or player_color not in {"B", "W"}:
        raise LordTrialAnswerError("judge_unavailable", status=503, retryable=True)
    return board_size, player_color


def build_lord_trial_attempt_context(
    question: Mapping[str, Any], exam: Mapping[str, Any]
) -> dict[str, Any]:
    """Build the server-owned subset required by the existing SGF judge."""

    if not isinstance(question, Mapping) or not isinstance(exam, Mapping):
        raise LordTrialAnswerError("invalid_boss_attempt_context")
    attempt_id = _attempt_value(exam, "attempt_id")
    zone_key = _attempt_value(exam, "zone_key")
    question_id = question.get("id")
    if isinstance(question_id, bool) or not isinstance(question_id, int):
        raise LordTrialAnswerError("unknown_question")
    board_size, player_color = _question_board_context(question)
    try:
        revision = question_revision_for(question)
    except MapBattleRuntimeError as error:
        raise LordTrialAnswerError("judge_unavailable", status=503, retryable=True) from error
    return {
        "battle_id": f"lord-trial:{zone_key}",
        "attempt_id": attempt_id,
        "question_id": question_id,
        "question_revision": revision,
        "board_size": board_size,
        "player_color": player_color,
        "transform_id": "identity",
        "transform_version": "lord-trial-v1",
        "battle_revision": 0,
        "pass_allowed": False,
    }


def canonicalize_lord_trial_answer(
    answer: Mapping[str, Any],
    *,
    question: Mapping[str, Any],
    exam: Mapping[str, Any],
) -> CanonicalAnswer:
    """Canonicalize only player moves; all judge context is server-derived."""

    if not isinstance(answer, Mapping):
        raise LordTrialAnswerError("answer_required")
    unexpected = sorted(set(answer).difference({"moves"}))
    if unexpected:
        raise LordTrialAnswerError("forbidden_answer_field")
    if "moves" not in answer:
        raise LordTrialAnswerError("answer_required")

    context = build_lord_trial_attempt_context(question, exam)
    payload = {
        "battle_id": context["battle_id"],
        "attempt_id": context["attempt_id"],
        "submission_nonce": f"lord-trial:{context['attempt_id']}:{context['question_id']}",
        "battle_revision": context["battle_revision"],
        "question_revision": context["question_revision"],
        "player_color": context["player_color"],
        "transform_id": context["transform_id"],
        "transform_version": context["transform_version"],
        "moves": answer.get("moves"),
    }
    try:
        canonical = canonicalize_answer(payload, context)
    except MapBattleRuntimeError as error:
        raise LordTrialAnswerError("malformed_answer") from error
    if canonical.is_invalid:
        raise LordTrialAnswerError("malformed_answer")
    return canonical


def judge_lord_trial_answer(
    answer: Mapping[str, Any],
    *,
    question: Mapping[str, Any],
    exam: Mapping[str, Any],
) -> tuple[CanonicalAnswer, JudgeOutcome]:
    """Return a server-only SGF verdict for one current Lord question."""

    canonical = canonicalize_lord_trial_answer(answer, question=question, exam=exam)
    context = build_lord_trial_attempt_context(question, exam)
    try:
        judge = judge_map_battle_answer_v1(question, context, canonical)
    except JudgeUnavailable as error:
        raise LordTrialAnswerError("judge_unavailable", status=503, retryable=True) from error
    if judge.result == "INVALID" or judge.authoritative_grade not in {0, 5}:
        raise LordTrialAnswerError("malformed_answer")
    return canonical, JudgeOutcome(
        result=judge.result,
        authoritative_grade=judge.authoritative_grade,
        judge_version=LORD_TRIAL_JUDGE_VERSION,
        reason_code=judge.reason_code,
    )


def lord_trial_submission_id(attempt_id: str, question_id: int) -> str:
    """Return the server-owned identity shared by all retries of one answer."""

    if not isinstance(attempt_id, str) or not attempt_id.strip():
        raise LordTrialAnswerError("invalid_boss_attempt_context")
    if isinstance(question_id, bool) or not isinstance(question_id, int):
        raise LordTrialAnswerError("unknown_question")
    return f"lord-trial:{attempt_id.strip()}:{question_id}"


def build_lord_trial_verdict(
    *, attempt_id: str, question_id: int, judge: JudgeOutcome
) -> dict[str, Any]:
    """Build the exact server-owned replay envelope."""

    if judge.result == "CORRECT" and judge.authoritative_grade == 5:
        verdict = "AUTHORITATIVE_PASS"
    elif judge.result == "INCORRECT" and judge.authoritative_grade == 0:
        verdict = "AUTHORITATIVE_FAIL"
    else:
        raise LordTrialVerdictPersistenceError("judge result is not persistable")
    return {
        "schema": "lord_trial_verdict_v1",
        "attempt_id": str(attempt_id),
        "question_id": int(question_id),
        "verdict": verdict,
        "authoritative_grade": int(judge.authoritative_grade),
        "judge_version": str(judge.judge_version),
        "reason_code": str(judge.reason_code),
    }


def encode_lord_trial_verdict(verdict: Mapping[str, Any]) -> str:
    payload = dict(verdict)
    if set(payload) != _LORD_TRIAL_RESULT_KEYS:
        raise LordTrialVerdictPersistenceError("invalid Lord Trial verdict envelope")
    if payload.get("schema") != "lord_trial_verdict_v1":
        raise LordTrialVerdictPersistenceError("invalid Lord Trial verdict schema")
    if payload.get("verdict") not in _LORD_TRIAL_VERDICTS:
        raise LordTrialVerdictPersistenceError("invalid Lord Trial verdict state")
    return LORD_TRIAL_RESULT_SOURCE_PREFIX + json.dumps(
        payload, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    )


def decode_lord_trial_verdict(source_context: Any) -> dict[str, Any] | None:
    if not isinstance(source_context, str) or not source_context.startswith(
        LORD_TRIAL_RESULT_SOURCE_PREFIX
    ):
        return None
    encoded = source_context[len(LORD_TRIAL_RESULT_SOURCE_PREFIX) :]
    if not encoded or encoded == "pending":
        return None
    try:
        payload = json.loads(encoded)
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, Mapping) or set(payload) != _LORD_TRIAL_RESULT_KEYS:
        return None
    if payload.get("schema") != "lord_trial_verdict_v1":
        return None
    if payload.get("verdict") not in _LORD_TRIAL_VERDICTS:
        return None
    if isinstance(payload.get("attempt_id"), str) is False:
        return None
    if isinstance(payload.get("question_id"), bool) or not isinstance(
        payload.get("question_id"), int
    ):
        return None
    if payload.get("authoritative_grade") not in {0, 5}:
        return None
    if (
        payload["verdict"] == "AUTHORITATIVE_PASS"
        and payload["authoritative_grade"] != 5
    ) or (
        payload["verdict"] == "AUTHORITATIVE_FAIL"
        and payload["authoritative_grade"] != 0
    ):
        return None
    if not isinstance(payload.get("judge_version"), str) or not isinstance(
        payload.get("reason_code"), str
    ):
        return None
    return dict(payload)


def persist_lord_trial_verdict(
    conn: Any,
    *,
    user_id: int,
    submission_id: str,
    verdict: Mapping[str, Any],
) -> None:
    """Replace the private pending source with the committed server result."""

    encoded = encode_lord_trial_verdict(verdict)
    updated = conn.execute(
        """UPDATE review_log
              SET source_context=?
            WHERE user_id=? AND submission_id=?
              AND source_context=?""",
        (encoded, int(user_id), str(submission_id), LORD_TRIAL_PENDING_SOURCE),
    )
    if getattr(updated, "rowcount", 0) != 1:
        raise LordTrialVerdictPersistenceError("Lord Trial verdict identity is not recoverable")


def summarize_lord_trial_evidence(
    rows: Any, *, attempt_id: str, question_ids: list[int]
) -> dict[str, Any]:
    """Derive ordered progress from server-owned verdict envelopes only."""

    expected = set(question_ids)
    verdict_by_qid: dict[int, dict[str, Any]] = {}
    for row in rows:
        try:
            qid = int(row["question_id"])
            source_context = row["source_context"]
        except (KeyError, TypeError, ValueError, IndexError) as error:
            raise LordTrialVerdictPersistenceError("malformed Lord Trial evidence") from error
        verdict = decode_lord_trial_verdict(source_context)
        if verdict is None:
            continue
        # A prior attempt by the same player may legitimately share the same
        # question ID. It is not evidence for this signed attempt and must be
        # ignored rather than contaminating resume. Once the attempt matches,
        # a question mismatch is malformed evidence and fails closed.
        if verdict["attempt_id"] != attempt_id:
            continue
        if verdict["question_id"] != qid:
            raise LordTrialVerdictPersistenceError("mismatched Lord Trial evidence")
        if qid not in expected:
            continue
        previous = verdict_by_qid.get(qid)
        if previous is not None and previous != verdict:
            raise LordTrialVerdictPersistenceError("conflicting Lord Trial verdict")
        verdict_by_qid[qid] = verdict

    settled_prefix_count = 0
    for qid in question_ids:
        if qid not in verdict_by_qid:
            break
        settled_prefix_count += 1
    if any(qid in verdict_by_qid for qid in question_ids[settled_prefix_count:]):
        raise LordTrialVerdictPersistenceError("nonsequential Lord Trial evidence")
    settled_qids = question_ids[:settled_prefix_count]
    return {
        "verdict_by_qid": verdict_by_qid,
        "settled_prefix_count": settled_prefix_count,
        "answered_count": settled_prefix_count,
        "correct_count": sum(
            1
            for qid in settled_qids
            if verdict_by_qid[qid]["verdict"] == "AUTHORITATIVE_PASS"
        ),
        "total": len(question_ids),
        "complete": settled_prefix_count == len(question_ids),
    }


__all__ = [
    "LORD_TRIAL_JUDGE_VERSION",
    "LORD_TRIAL_PENDING_SOURCE",
    "LORD_TRIAL_RESULT_SOURCE_PREFIX",
    "LordTrialAnswerError",
    "LordTrialVerdictPersistenceError",
    "build_lord_trial_attempt_context",
    "build_lord_trial_verdict",
    "canonicalize_lord_trial_answer",
    "decode_lord_trial_verdict",
    "encode_lord_trial_verdict",
    "judge_lord_trial_answer",
    "lord_trial_submission_id",
    "persist_lord_trial_verdict",
    "summarize_lord_trial_evidence",
]
