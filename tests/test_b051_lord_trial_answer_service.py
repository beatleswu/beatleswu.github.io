"""Focused B051 tests for the server-owned Lord Trial answer seam."""

import sqlite3

import pytest

from lord_trial_answer_service import (
    LORD_TRIAL_PENDING_SOURCE,
    LordTrialAnswerError,
    LordTrialVerdictPersistenceError,
    build_lord_trial_verdict,
    decode_lord_trial_verdict,
    encode_lord_trial_verdict,
    judge_lord_trial_answer,
    lord_trial_submission_id,
    persist_lord_trial_verdict,
    summarize_lord_trial_evidence,
)


QUESTION = {
    "id": 970001,
    "content": "(;GM[1]FF[4]CA[UTF-8]SZ[19]PL[B]AB[dp]AW[pd](;B[dd]C[answer]))",
    "accepted_moves": [{"x": 3, "y": 3}],
}
EXAM = {
    "zone_key": "k26_30",
    "attempt_id": "unit-attempt",
}


def test_server_judge_uses_moves_not_client_grade():
    _canonical, judged = judge_lord_trial_answer(
        {"moves": [{"x": 3, "y": 3}]}, question=QUESTION, exam=EXAM
    )
    assert judged.result == "CORRECT"
    assert judged.authoritative_grade == 5

    _canonical, judged = judge_lord_trial_answer(
        {"moves": [{"x": 4, "y": 3}]}, question=QUESTION, exam=EXAM
    )
    assert judged.result == "INCORRECT"
    assert judged.authoritative_grade == 0


@pytest.mark.parametrize(
    "answer",
    [
        {},
        {"moves": []},
        {"moves": [{"x": 3, "y": 3}], "grade": 5},
        {"moves": [{"x": 3, "y": 3}], "correct": True},
        {"moves": [{"x": 3, "y": 3}], "total": 20},
        {"moves": [{"x": 99, "y": 99}]},
    ],
)
def test_malformed_or_forged_answer_fails_closed(answer):
    with pytest.raises(LordTrialAnswerError):
        judge_lord_trial_answer(answer, question=QUESTION, exam=EXAM)


def test_verdict_envelope_round_trips_and_rejects_tampered_shape():
    _canonical, judged = judge_lord_trial_answer(
        {"moves": [{"x": 3, "y": 3}]}, question=QUESTION, exam=EXAM
    )
    verdict = build_lord_trial_verdict(
        attempt_id=EXAM["attempt_id"], question_id=QUESTION["id"], judge=judged
    )
    encoded = encode_lord_trial_verdict(verdict)
    assert decode_lord_trial_verdict(encoded) == verdict
    assert decode_lord_trial_verdict(encoded.replace("AUTHORITATIVE_PASS", "AUTHORITATIVE_FAIL")) is None


def test_evidence_deduplicates_identical_server_verdict_and_rejects_conflict():
    passed = {
        "schema": "lord_trial_verdict_v1",
        "attempt_id": EXAM["attempt_id"],
        "question_id": 970001,
        "verdict": "AUTHORITATIVE_PASS",
        "authoritative_grade": 5,
        "judge_version": "lord-trial-map-battle-judge-v1",
        "reason_code": "answer_tree_leaf",
    }
    row = {"question_id": 970001, "source_context": encode_lord_trial_verdict(passed)}
    summary = summarize_lord_trial_evidence(
        [row, row], attempt_id=EXAM["attempt_id"], question_ids=[970001]
    )
    assert summary["complete"] is True
    assert summary["correct_count"] == 1

    failed = dict(passed, verdict="AUTHORITATIVE_FAIL", authoritative_grade=0)
    with pytest.raises(LordTrialVerdictPersistenceError):
        summarize_lord_trial_evidence(
            [row, {"question_id": 970001, "source_context": encode_lord_trial_verdict(failed)}],
            attempt_id=EXAM["attempt_id"], question_ids=[970001]
        )


def test_existing_review_identity_can_persist_server_result_without_schema_change():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE review_log (user_id INTEGER, submission_id TEXT, source_context TEXT)"
    )
    submission_id = lord_trial_submission_id(EXAM["attempt_id"], QUESTION["id"])
    conn.execute(
        "INSERT INTO review_log VALUES (?,?,?)",
        (7, submission_id, LORD_TRIAL_PENDING_SOURCE),
    )
    _canonical, judged = judge_lord_trial_answer(
        {"moves": [{"x": 3, "y": 3}]}, question=QUESTION, exam=EXAM
    )
    verdict = build_lord_trial_verdict(
        attempt_id=EXAM["attempt_id"], question_id=QUESTION["id"], judge=judged
    )
    persist_lord_trial_verdict(
        conn, user_id=7, submission_id=submission_id, verdict=verdict
    )
    stored = conn.execute(
        "SELECT source_context FROM review_log WHERE user_id=7"
    ).fetchone()[0]
    assert decode_lord_trial_verdict(stored) == verdict
