"""W1-A2 proof for the Owner-approved Map Battle evidence contract."""

from __future__ import annotations

import sqlite3

import pytest

from adventure_progress_compatibility import (
    MAP_BATTLE_GRANDFATHERED_SOURCE_PREFIX,
    MAP_BATTLE_TRUSTED_EVIDENCE_POLICY as PROGRESS_TRUSTED_EVIDENCE_POLICY,
    TRUSTED_REVIEW_SOURCE_PREFIXES,
    trusted_correct_count_after,
    trusted_current_memberships,
    visible_adventure_question_ids,
)
from map_battle_persistence import MAP_BATTLE_JUDGE_VERSION
from map_battle_runtime import (
    CanonicalAnswer,
    JudgeOutcome,
    JudgeUnavailable,
    MAP_BATTLE_TRUSTED_CORRECT_REASON_CODES,
    MAP_BATTLE_TRUSTED_EVIDENCE_POLICY as RUNTIME_TRUSTED_EVIDENCE_POLICY,
    MAP_BATTLE_TRUSTED_INCORRECT_REASON_CODES,
    is_owner_approved_map_battle_outcome,
    judge_map_battle_answer_v1,
)
from migrations.adventure_historical_mastery_v1 import upgrade


def _attempt():
    return {"board_size": 19, "transform_id": "identity"}


def _answer(*moves):
    return CanonicalAnswer(
        {
            "player_color": "B",
            "moves": [
                {"action": "play", "color": "B", "x": x, "y": y}
                for x, y in moves
            ],
        }
    )


@pytest.mark.parametrize(
    ("question", "answer", "expected"),
    [
        (
            {"content": "(;SZ[19];B[dd])"},
            _answer((3, 3)),
            ("CORRECT", 5, "answer_tree_leaf"),
        ),
        (
            {"content": "(;SZ[19];B[dd];W[ee])"},
            _answer((3, 3)),
            ("CORRECT", 5, "answer_tree_reply_leaf"),
        ),
        (
            {
                "content": "(;SZ[19];B[dd])",
                "accepted_moves": [{"x": 4, "y": 4}],
            },
            _answer((4, 4)),
            ("CORRECT", 5, "accepted_authoritative_alternative"),
        ),
        (
            {"content": "(;SZ[19];B[dd])"},
            _answer((4, 4)),
            ("INCORRECT", 0, "off_answer_tree"),
        ),
        (
            {"content": "(;SZ[19];B[dd])"},
            CanonicalAnswer({"player_color": "B", "moves": [{"action": "resign"}]}),
            ("INCORRECT", 0, "resign"),
        ),
        (
            {"content": "(;SZ[19];B[dd];W[ee];B[ff])"},
            _answer((3, 3)),
            ("INCORRECT", 0, "partial_answer_sequence"),
        ),
    ],
)
def test_owner_approved_judge_outcomes_are_preserved(question, answer, expected):
    outcome = judge_map_battle_answer_v1(question, _attempt(), answer)
    assert (
        outcome.result,
        outcome.authoritative_grade,
        outcome.reason_code,
    ) == expected
    assert is_owner_approved_map_battle_outcome(outcome) is True


def test_unavailable_authoritative_content_is_retryable_and_not_classified():
    with pytest.raises(JudgeUnavailable):
        judge_map_battle_answer_v1(
            {"content": "   "},
            _attempt(),
            _answer((3, 3)),
        )


def test_invalid_input_stays_invalid_and_no_new_terminal_verdict_is_required():
    invalid = judge_map_battle_answer_v1(
        {"content": "(;SZ[19];B[dd])"},
        _attempt(),
        CanonicalAnswer(
            {"player_color": "B", "moves": []},
            result="INVALID",
            reason_code="empty_sequence",
        ),
    )
    special = judge_map_battle_answer_v1(
        {"content": "(;SZ[19];B[dd])"},
        _attempt(),
        CanonicalAnswer(
            {"player_color": "B", "moves": [{"action": "pass"}]}
        ),
    )
    assert invalid == JudgeOutcome(
        "INVALID", None, MAP_BATTLE_JUDGE_VERSION, "empty_sequence"
    )
    assert special == JudgeOutcome(
        "INVALID", None, MAP_BATTLE_JUDGE_VERSION, "special_move_not_judged"
    )
    assert is_owner_approved_map_battle_outcome(invalid) is True
    assert is_owner_approved_map_battle_outcome(special) is True


def test_unrecognised_correct_outcome_cannot_enter_the_settlement_contract():
    assert is_owner_approved_map_battle_outcome(
        JudgeOutcome("CORRECT", 5, MAP_BATTLE_JUDGE_VERSION, "invented_reason")
    ) is False


def test_owner_policy_and_reason_sets_are_explicit_and_shared_with_progress():
    expected_policy = "PRESERVE_BARE_LEAF_AND_GRANDFATHER_MBV1"
    assert RUNTIME_TRUSTED_EVIDENCE_POLICY == expected_policy
    assert PROGRESS_TRUSTED_EVIDENCE_POLICY == expected_policy
    assert RUNTIME_TRUSTED_EVIDENCE_POLICY == PROGRESS_TRUSTED_EVIDENCE_POLICY
    assert MAP_BATTLE_TRUSTED_CORRECT_REASON_CODES == {
        "accepted_authoritative_alternative",
        "answer_tree_leaf",
        "answer_tree_reply_leaf",
    }
    assert MAP_BATTLE_TRUSTED_INCORRECT_REASON_CODES == {
        "off_answer_tree",
        "resign",
        "partial_answer_sequence",
    }


def test_existing_mbv1_evidence_remains_grandfathered_for_visible_progress():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE review_log(user_id INTEGER, question_id INTEGER, grade INTEGER, "
        "reviewed_at TEXT, source_context TEXT)"
    )
    upgrade(conn)
    conn.executemany(
        "INSERT INTO review_log(user_id,question_id,grade,reviewed_at,source_context) "
        "VALUES (?,?,?,?,?)",
        [
            (7, 7001, 5, "2026-08-01T00:00:00", "mbv1:historical-1"),
            (7, 7002, 3, "2026-08-01T00:00:00", "mbv1:historical-2"),
            (7, 7003, 5, "2026-08-01T00:00:00", "practice"),
        ],
    )
    conn.commit()
    try:
        assert MAP_BATTLE_GRANDFATHERED_SOURCE_PREFIX == "mbv1:"
        assert TRUSTED_REVIEW_SOURCE_PREFIXES == ("mbv1:",)
        assert trusted_current_memberships(conn, user_id=7) == {7001, 7002}
        assert visible_adventure_question_ids(conn, 7) == {7001, 7002}
    finally:
        conn.close()


def test_r3_count_remains_tier2_only_distinct_and_strictly_after_failure():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE review_log(user_id INTEGER, question_id INTEGER, grade INTEGER, "
        "reviewed_at TEXT, source_context TEXT)"
    )
    conn.executemany(
        "INSERT INTO review_log(user_id,question_id,grade,reviewed_at,source_context) "
        "VALUES (?,?,?,?,?)",
        [
            (7, 7101, 5, "2026-09-02T00:00:00", "mbv1:one"),
            (7, 7101, 5, "2026-09-02T00:01:00", "mbv1:duplicate"),
            (7, 7102, 2, "2026-09-02T00:02:00", "mbv1:low"),
            (7, 7103, 5, "2026-09-02T00:03:00", "practice"),
            (7, 7104, 5, "2026-08-31T00:00:00", "mbv1:before"),
        ],
    )
    conn.commit()
    try:
        assert trusted_correct_count_after(
            conn,
            7,
            {7101, 7102, 7103, 7104},
            "2026-09-01T00:00:00",
        ) == 1
    finally:
        conn.close()
