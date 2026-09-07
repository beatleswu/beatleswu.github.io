"""Focused A3A/R2 authority and exploit regressions."""

from __future__ import annotations

import sqlite3

import pytest

from migrations.w2_a1_onboarding_v1 import upgrade
from wave2_onboarding_authority import (
    COMPLETED,
    FACT_COMBAT_RESULT,
    FACT_FIRST_CONTEXT,
    FACT_FIRST_QUESTION,
    FACT_GROWTH_COMMITTED,
    FACT_REWARD_GRANTED,
    FACT_REVIEW_ACCEPTED,
    IN_PROGRESS,
    NOT_STARTED,
    STEP_FIRST_COMBAT,
    STEP_FIRST_CONTEXT,
    STEP_FIRST_GROWTH,
    STEP_FIRST_QUESTION,
    STEP_FIRST_REVIEW,
    STEP_FIRST_REWARD,
    STEP_NEXT_ACTION,
    advance_from_server_fact,
    finish,
    get_state,
    replay,
    resume,
    skip,
    start,
)


USER_ID = 7
ATTEMPT_ID = "mb-attempt-zone1"
QUESTION_ID = 31001


@pytest.fixture()
def connection():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    upgrade(conn)
    conn.executescript(
        """
        CREATE TABLE map_battles (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            zone_key TEXT NOT NULL,
            state TEXT NOT NULL,
            monster_hp INTEGER NOT NULL,
            player_hp INTEGER NOT NULL
        );
        CREATE TABLE map_battle_attempts (
            id TEXT PRIMARY KEY,
            battle_id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            state TEXT NOT NULL
        );
        CREATE TABLE map_battle_submissions (
            id TEXT PRIMARY KEY,
            battle_id TEXT NOT NULL,
            attempt_id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            settlement_state TEXT NOT NULL,
            judge_result TEXT,
            settled_at TEXT
        );
        CREATE TABLE review_log (
            user_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            submission_id TEXT,
            source_context TEXT
        );
        CREATE TABLE wave2_onboarding_server_facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            attempt_id TEXT NOT NULL,
            question_id INTEGER NOT NULL,
            fact_type TEXT NOT NULL,
            committed INTEGER NOT NULL DEFAULT 0,
            replay INTEGER NOT NULL DEFAULT 0,
            outcome TEXT
        );
        """
    )
    conn.execute(
        "INSERT INTO map_battles VALUES (?, ?, ?, ?, ?, ?)",
        ("battle-zone1", USER_ID, "k26_30", "OPEN", 100, 100),
    )
    conn.execute(
        "INSERT INTO map_battle_attempts VALUES (?, ?, ?, ?, ?)",
        (ATTEMPT_ID, "battle-zone1", USER_ID, QUESTION_ID, "ISSUED"),
    )
    conn.commit()
    try:
        yield conn
    finally:
        conn.close()


def _enroll(conn):
    assert start(conn, USER_ID)["state_version"] == 1
    assert resume(conn, USER_ID, expected_state_version=1)["state_version"] == 2


def _context_and_question(conn):
    _enroll(conn)
    result = advance_from_server_fact(
        conn,
        USER_ID,
        FACT_FIRST_CONTEXT,
        {"attempt_id": ATTEMPT_ID, "question_id": 999999, "zone": "k26_30"},
        expected_state_version=2,
    )
    assert result["ok"] is False
    assert result["reason"] == "QUESTION_IDENTITY_MISMATCH"
    assert get_state(conn, USER_ID).current_step == STEP_FIRST_CONTEXT

    result = advance_from_server_fact(
        conn,
        USER_ID,
        FACT_FIRST_CONTEXT,
        {"attempt_id": ATTEMPT_ID, "question_id": QUESTION_ID, "zone": "zone9"},
        expected_state_version=2,
    )
    assert result["changed"] is True
    assert result["current_step"] == STEP_FIRST_QUESTION
    assert result["first_context_attempt_id"] == ATTEMPT_ID

    result = advance_from_server_fact(
        conn,
        USER_ID,
        "journey:question-ready",
        {"attempt_id": ATTEMPT_ID, "question_id": QUESTION_ID},
        expected_state_version=3,
    )
    assert result["changed"] is True
    assert result["current_step"] == STEP_FIRST_REVIEW


def _commit_review(conn):
    conn.execute(
        "INSERT INTO map_battle_submissions VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("submission-1", "battle-zone1", ATTEMPT_ID, USER_ID, "SETTLED", "CORRECT", "t1"),
    )
    conn.execute(
        "UPDATE map_battle_attempts SET state='SETTLED' WHERE id=?",
        (ATTEMPT_ID,),
    )
    conn.execute(
        "INSERT INTO review_log VALUES (?, ?, ?, ?)",
        (USER_ID, QUESTION_ID, "submission-1", "mbv1:submission-1"),
    )
    conn.commit()


def _commit_fact(conn, fact_type, *, attempt_id=ATTEMPT_ID, question_id=QUESTION_ID, outcome=None, replay=0):
    conn.execute(
        """INSERT INTO wave2_onboarding_server_facts
           (user_id,attempt_id,question_id,fact_type,committed,replay,outcome)
           VALUES (?, ?, ?, ?, 1, ?, ?)""",
        (USER_ID, attempt_id, question_id, fact_type, replay, outcome),
    )
    conn.commit()


def _advance_to_combat(conn):
    _context_and_question(conn)
    _commit_review(conn)
    result = advance_from_server_fact(
        conn,
        USER_ID,
        FACT_REVIEW_ACCEPTED,
        {"attempt_id": ATTEMPT_ID, "accepted": False, "grade": 0},
        expected_state_version=4,
    )
    assert result["changed"] is True
    assert result["current_step"] == STEP_FIRST_COMBAT


def test_first_adventure_is_bound_to_authenticated_zone1_attempt_and_question(connection):
    _enroll(connection)
    connection.execute(
        "INSERT INTO map_battles VALUES (?, ?, ?, ?, ?, ?)",
        ("battle-zone9", USER_ID, "zone9", "OPEN", 100, 100),
    )
    connection.execute(
        "INSERT INTO map_battle_attempts VALUES (?, ?, ?, ?, ?)",
        ("attempt-zone9", "battle-zone9", USER_ID, 99901, "ISSUED"),
    )
    connection.commit()
    rejected = advance_from_server_fact(
        connection,
        USER_ID,
        FACT_FIRST_CONTEXT,
        {
            "attempt_id": "attempt-zone9",
            "question_id": QUESTION_ID,
            "defeated": True,
            "damage": 999,
            "reward": {"coins": 999},
            "xp": 999,
        },
        expected_state_version=2,
    )
    assert rejected["changed"] is False
    assert rejected["reason"] == "FIRST_CONTEXT_REQUIRES_ZONE1_MAP_BATTLE_ATTEMPT"
    assert get_state(connection, USER_ID).first_context_attempt_id is None


def test_review_requires_committed_evidence_not_caller_acceptance(connection):
    _context_and_question(connection)
    blocked = advance_from_server_fact(
        connection,
        USER_ID,
        FACT_REVIEW_ACCEPTED,
        {"attempt_id": ATTEMPT_ID, "accepted": True, "committed": True},
        expected_state_version=4,
    )
    assert blocked["noop"] is True
    assert blocked["reason"] == "COMMITTED_REVIEW_REQUIRED"
    assert get_state(connection, USER_ID).current_step == STEP_FIRST_REVIEW

    _commit_review(connection)
    accepted = advance_from_server_fact(
        connection,
        USER_ID,
        FACT_REVIEW_ACCEPTED,
        {"attempt_id": ATTEMPT_ID, "accepted": False, "grade": 0},
        expected_state_version=4,
    )
    assert accepted["current_step"] == STEP_FIRST_COMBAT


def test_battle_reward_and_growth_require_same_context_server_facts(connection):
    _advance_to_combat(connection)
    fake = advance_from_server_fact(
        connection,
        USER_ID,
        FACT_COMBAT_RESULT,
        {
            "attempt_id": ATTEMPT_ID,
            "defeated": True,
            "damage": 100000,
            "battle_result": "VICTORY",
        },
        expected_state_version=5,
    )
    assert fake["noop"] is True
    assert fake["reason"] == "COMMITTED_BATTLE_RESULT_REQUIRED"

    connection.execute(
        "UPDATE map_battles SET state='COMPLETED', monster_hp=0 WHERE id=?",
        ("battle-zone1",),
    )
    connection.commit()
    victory = advance_from_server_fact(
        connection,
        USER_ID,
        FACT_COMBAT_RESULT,
        {"attempt_id": ATTEMPT_ID, "defeated": False, "damage": 0},
        expected_state_version=5,
    )
    assert victory["current_step"] == STEP_FIRST_REWARD

    fake_reward = advance_from_server_fact(
        connection,
        USER_ID,
        FACT_REWARD_GRANTED,
        {"attempt_id": ATTEMPT_ID, "reward": {"coins": 999}, "replay": False},
        expected_state_version=6,
    )
    assert fake_reward["noop"] is True

    _commit_fact(connection, "reward_committed")
    reward = advance_from_server_fact(
        connection,
        USER_ID,
        FACT_REWARD_GRANTED,
        {"attempt_id": ATTEMPT_ID, "reward": {"coins": 999}},
        expected_state_version=6,
    )
    assert reward["current_step"] == STEP_FIRST_GROWTH

    _commit_fact(connection, "growth_committed")
    growth = advance_from_server_fact(
        connection,
        USER_ID,
        FACT_GROWTH_COMMITTED,
        {"attempt_id": ATTEMPT_ID, "xp": 100000, "growth": True},
        expected_state_version=7,
    )
    assert growth["current_step"] == STEP_NEXT_ACTION
    assert growth["status"] == IN_PROGRESS


def test_later_unrelated_reward_cannot_advance_first_context(connection):
    _advance_to_combat(connection)
    connection.execute(
        "UPDATE map_battles SET state='COMPLETED', monster_hp=0 WHERE id=?",
        ("battle-zone1",),
    )
    connection.commit()
    victory = advance_from_server_fact(
        connection, USER_ID, FACT_COMBAT_RESULT, {"attempt_id": ATTEMPT_ID}
    )
    assert victory["current_step"] == STEP_FIRST_REWARD
    _commit_fact(connection, "reward_committed", attempt_id="later-attempt")
    result = advance_from_server_fact(
        connection,
        USER_ID,
        FACT_REWARD_GRANTED,
        {"attempt_id": ATTEMPT_ID, "reward": {"coins": 1}},
        expected_state_version=6,
    )
    assert result["noop"] is True
    assert result["reason"] == "SAME_CONTEXT_REWARD_REQUIRED"


def test_presentation_events_and_replay_are_non_authoritative_and_pure(connection):
    before = connection.execute(
        "SELECT COUNT(*) FROM wave2_onboarding_state_v1"
    ).fetchone()[0]
    result = replay(connection, USER_ID, expected_state_version=0)
    assert result["noop"] is True
    assert connection.execute(
        "SELECT COUNT(*) FROM wave2_onboarding_state_v1"
    ).fetchone()[0] == before == 0

    _enroll(connection)
    version = get_state(connection, USER_ID).state_version
    for event in (
        "boardReady",
        "attack_hit",
        "journey:reward-revealed",
        "growth_feedback",
        "zone_progressed",
        "zone3_arrival",
    ):
        result = advance_from_server_fact(
            connection,
            USER_ID,
            event,
            {"attempt_id": ATTEMPT_ID, "defeated": True, "reward": 1000, "xp": 1000},
            expected_state_version=0,
        )
        assert result["noop"] is True
        assert result["state_version"] == version


def test_cas_and_semantic_idempotency_order(connection):
    first = start(connection, USER_ID)
    duplicate = start(connection, USER_ID, expected_state_version=0)
    assert first["changed"] is True
    assert duplicate["noop"] is True
    assert duplicate["state_version"] == 1

    stale = resume(connection, USER_ID, expected_state_version=0)
    assert stale["ok"] is False
    assert stale["status_code"] == 409
    assert stale["reason"] == "STALE_STATE_VERSION"

    skipped = skip(connection, 8)
    duplicate_skip = skip(connection, 8, expected_state_version=0)
    assert skipped["status"] == "SKIPPED"
    assert duplicate_skip["noop"] is True
    assert duplicate_skip["state_version"] == skipped["state_version"]


def test_finish_requires_next_action_and_then_is_idempotent(connection):
    _context_and_question(connection)
    before = finish(connection, USER_ID, expected_state_version=4)
    assert before["ok"] is False
    assert before["reason"] == "COMPLETION_FRONTIER_NOT_REACHED"

    _commit_review(connection)
    advance_from_server_fact(connection, USER_ID, FACT_REVIEW_ACCEPTED, {"attempt_id": ATTEMPT_ID})
    connection.execute(
        "UPDATE map_battles SET state='COMPLETED', monster_hp=0 WHERE id=?",
        ("battle-zone1",),
    )
    connection.commit()
    advance_from_server_fact(connection, USER_ID, FACT_COMBAT_RESULT, {"attempt_id": ATTEMPT_ID})
    _commit_fact(connection, "reward_committed")
    advance_from_server_fact(connection, USER_ID, FACT_REWARD_GRANTED, {"attempt_id": ATTEMPT_ID})
    _commit_fact(connection, "growth_committed")
    ready = advance_from_server_fact(connection, USER_ID, "growth_committed", {"attempt_id": ATTEMPT_ID})
    assert ready["current_step"] == STEP_NEXT_ACTION
    completed = finish(connection, USER_ID, expected_state_version=ready["state_version"])
    assert completed["status"] == COMPLETED
    retry = finish(connection, USER_ID, expected_state_version=0)
    assert retry["noop"] is True
    assert retry["state_version"] == completed["state_version"]


def test_mismatched_question_and_user_claims_cannot_switch_context(connection):
    _enroll(connection)
    result = advance_from_server_fact(
        connection,
        USER_ID,
        FACT_FIRST_CONTEXT,
        {"attempt_id": ATTEMPT_ID, "question_id": QUESTION_ID + 1},
    )
    assert result["ok"] is False
    assert result["reason"] == "QUESTION_IDENTITY_MISMATCH"
    result = advance_from_server_fact(
        connection,
        USER_ID,
        FACT_FIRST_CONTEXT,
        {"attempt_id": ATTEMPT_ID, "user_id": 999},
    )
    assert result["ok"] is False
    assert result["status_code"] == 403
