from pathlib import Path

import pytest

from map_battle_runtime import question_revision_for
from practice_answer_authority import (
    PRACTICE_TRUSTED_SOURCE_CONTEXT_PREFIX,
    PracticeAttemptError,
    canonicalize_practice_answer,
    issue_practice_attempt,
    judge_practice_answer,
    practice_source_context,
    practice_submission_id,
    verify_practice_attempt,
)


QUESTION = {
    "id": 701,
    "content": "(;GM[1]SZ[5]PL[B];B[aa])",
}
CONTEXT = {
    "question_revision": question_revision_for(QUESTION),
    "board_size": 5,
    "player_color": "B",
    "transform_id": "identity",
    "transform_version": "map-battle-v1",
}


def _issue(*, now=100):
    return issue_practice_attempt(
        "incident-002-test-secret",
        user_id=42,
        question=QUESTION,
        source_record_uuid="uuid-q-701",
        question_context=CONTEXT,
        now=now,
    )


def test_correctness_is_server_judged_and_trusted_namespace_is_server_owned():
    token = _issue()
    attempt = verify_practice_attempt(
        "incident-002-test-secret", token, user_id=42, now=101
    )
    canonical = canonicalize_practice_answer(
        {"moves": [{"action": "play", "x": 0, "y": 0}]}, attempt
    )
    outcome = judge_practice_answer(QUESTION, attempt, canonical)

    assert outcome.result == "CORRECT"
    assert outcome.authoritative_grade == 5
    assert practice_source_context(attempt).startswith(
        PRACTICE_TRUSTED_SOURCE_CONTEXT_PREFIX
    )
    assert practice_submission_id(attempt).startswith("practice-v1:")


def test_wrong_answer_is_a_server_judged_preserved_result_without_correct_grade():
    token = _issue()
    attempt = verify_practice_attempt(
        "incident-002-test-secret", token, user_id=42, now=101
    )
    canonical = canonicalize_practice_answer(
        {"moves": [{"action": "play", "x": 1, "y": 1}]}, attempt
    )
    outcome = judge_practice_answer(QUESTION, attempt, canonical)
    assert outcome.result == "INCORRECT"
    assert outcome.authoritative_grade == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("grade", 5),
        ("trusted", True),
        ("server_verified", True),
        ("source_context", "practice:v1:forged"),
        ("authoritative_grade", 5),
    ],
)
def test_client_authority_claims_are_rejected(field, value):
    token = _issue()
    attempt = verify_practice_attempt(
        "incident-002-test-secret", token, user_id=42, now=101
    )
    with pytest.raises(PracticeAttemptError) as error:
        canonicalize_practice_answer(
            {"moves": [{"action": "play", "x": 0, "y": 0}], field: value},
            attempt,
        )
    assert error.value.code == "forbidden_answer_field"


def test_one_signed_nonce_is_one_answer_event_and_later_nonce_is_new_play():
    first = _issue(now=100)
    second = _issue(now=101)
    first_attempt = verify_practice_attempt(
        "incident-002-test-secret", first, user_id=42, now=102
    )
    second_attempt = verify_practice_attempt(
        "incident-002-test-secret", second, user_id=42, now=102
    )
    assert practice_submission_id(first_attempt) == practice_submission_id(first_attempt)
    assert practice_submission_id(first_attempt) != practice_submission_id(second_attempt)
    assert first_attempt["source_record_uuid"] == second_attempt["source_record_uuid"]


def test_attempt_binds_user_question_uuid_revision_and_expiry():
    token = _issue(now=100)
    with pytest.raises(PracticeAttemptError) as user_error:
        verify_practice_attempt(
            "incident-002-test-secret", token, user_id=43, now=101
        )
    assert user_error.value.code == "practice_attempt_user_mismatch"

    with pytest.raises(PracticeAttemptError) as q_error:
        verify_practice_attempt(
            "incident-002-test-secret", token, user_id=42, question_id=702, now=101
        )
    assert q_error.value.code == "practice_attempt_question_mismatch"

    with pytest.raises(PracticeAttemptError) as expired:
        verify_practice_attempt(
            "incident-002-test-secret", token, user_id=42,
            now=100 + 24 * 60 * 60,
        )
    assert expired.value.code == "practice_attempt_expired"


def test_source_code_wires_server_only_practice_boundary_without_client_trust_fields():
    root = Path(__file__).resolve().parents[1]
    app_source = (root / "app.py").read_text(encoding="utf-8")
    transport_source = (root / "js" / "game" / "review_transport.js").read_text(
        encoding="utf-8"
    )
    assert "@app.route('/api/srs/practice/attempt'" in app_source
    assert "@app.route('/api/srs/practice/answer'" in app_source
    assert "judge_practice_answer(question, attempt, canonical)" in app_source
    assert "PRACTICE_TRUSTED_SOURCE_CONTEXT_PREFIX" in app_source
    practice_transport = transport_source[
        transport_source.index("async function practiceAnswer"):
    ]
    assert "request.grade" not in practice_transport
    assert "request.trusted" not in practice_transport
    assert "request.server_verified" not in practice_transport
