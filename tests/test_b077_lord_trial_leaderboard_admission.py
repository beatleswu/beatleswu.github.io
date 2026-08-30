"""B077 Lord Trial admission into the shared community leaderboard path."""

from __future__ import annotations

import json
import sqlite3

import community_leaderboard_rewards as leaderboard_rewards
from lord_trial_answer_service import (
    LORD_TRIAL_JUDGE_VERSION,
    encode_lord_trial_verdict,
)
from srs_review_authority import (
    AUTHORITATIVE_REVIEW_SOURCE_CONTEXT_PREFIXES,
    AUTHORITATIVE_REVIEW_SOURCE_PREFIXES,
    is_authoritative_review_source_context,
)


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE users(
            id INTEGER PRIMARY KEY, username TEXT NOT NULL, nickname TEXT,
            plan TEXT DEFAULT 'free', is_admin INTEGER DEFAULT 0
        );
        CREATE TABLE review_log(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL, question_id INTEGER NOT NULL,
            grade INTEGER NOT NULL, reviewed_at TEXT NOT NULL,
            source TEXT, source_context TEXT
        );
        CREATE TABLE user_stats(
            user_id INTEGER PRIMARY KEY, rank_level TEXT
        );
        CREATE TABLE player_appearance(
            user_id INTEGER PRIMARY KEY, character_key TEXT,
            combat_armor TEXT, combat_weapon TEXT, combat_cape TEXT,
            combat_offhand TEXT, combat_hat TEXT, combat_pet TEXT,
            combat_aura TEXT
        );
        """
    )
    return conn


def _add_user(conn: sqlite3.Connection, user_id: int) -> None:
    conn.execute(
        "INSERT INTO users(id, username, nickname) VALUES (?, ?, ?)",
        (user_id, f"user_{user_id}", f"User {user_id}"),
    )
    conn.execute(
        "INSERT INTO user_stats(user_id, rank_level) VALUES (?, ?)",
        (user_id, "LV1"),
    )
    conn.execute(
        "INSERT INTO player_appearance(user_id, character_key) VALUES (?, ?)",
        (user_id, "apprentice"),
    )


def _lord_verdict(
    *, attempt_id: str, question_id: int, verdict: str = "AUTHORITATIVE_PASS",
    grade: int = 5,
) -> str:
    return encode_lord_trial_verdict({
        "schema": "lord_trial_verdict_v1",
        "attempt_id": attempt_id,
        "question_id": question_id,
        "verdict": verdict,
        "authoritative_grade": grade,
        "judge_version": LORD_TRIAL_JUDGE_VERSION,
        "reason_code": "answer_tree_leaf",
    })


def _insert_review(
    conn: sqlite3.Connection, *, user_id: int, question_id: int,
    reviewed_at: str, grade: int, source_context: str | None = None,
    source: str | None = None,
) -> None:
    conn.execute(
        """INSERT INTO review_log(
            user_id, question_id, grade, reviewed_at, source_context, source
        ) VALUES (?, ?, ?, ?, ?, ?)""",
        (user_id, question_id, grade, reviewed_at, source_context, source),
    )


def _rows(conn, start: str, end: str):
    return leaderboard_rewards.fetch_leaderboard_participant_rows(conn, start, end)


def test_valid_lord_pass_is_admitted_and_client_grade_is_ignored():
    conn = _db()
    _add_user(conn, 7)
    _insert_review(
        conn,
        user_id=7,
        question_id=7001,
        reviewed_at="2026-08-25T00:00:00",
        grade=0,
        source_context=_lord_verdict(attempt_id="attempt-7001", question_id=7001),
    )
    _insert_review(
        conn,
        user_id=7,
        question_id=7002,
        reviewed_at="2026-08-25T00:01:00",
        grade=5,
        source_context=_lord_verdict(
            attempt_id="attempt-7002", question_id=7002,
            verdict="AUTHORITATIVE_FAIL", grade=0,
        ),
    )
    _insert_review(
        conn,
        user_id=7,
        question_id=7003,
        reviewed_at="2026-08-25T00:02:00",
        grade=5,
        source_context="lord_trial:v1:pending",
    )
    _insert_review(
        conn,
        user_id=7,
        question_id=7004,
        reviewed_at="2026-08-25T00:03:00",
        grade=5,
        source_context="boss_trial:attempt-7004",
    )
    conn.commit()

    rows = _rows(conn, "2026-08-23T16:00:00", "2026-08-30T16:00:00")
    assert [(row["id"], row["score"]) for row in rows] == [(7, 1)]


def test_lord_uses_shared_user_question_dedupe_with_existing_trusted_sources():
    conn = _db()
    _add_user(conn, 7)
    _insert_review(
        conn,
        user_id=7,
        question_id=7001,
        reviewed_at="2026-08-24T00:00:00",
        grade=3,
        source="rt:rating-session",
    )
    _insert_review(
        conn,
        user_id=7,
        question_id=7001,
        reviewed_at="2026-08-24T00:01:00",
        grade=0,
        source_context=_lord_verdict(attempt_id="attempt-7001", question_id=7001),
    )
    _insert_review(
        conn,
        user_id=7,
        question_id=7002,
        reviewed_at="2026-08-24T00:02:00",
        grade=0,
        source_context=_lord_verdict(attempt_id="attempt-7002", question_id=7002),
    )
    conn.commit()

    rows = _rows(conn, "2026-08-23T16:00:00", "2026-08-30T16:00:00")
    assert len(rows) == 1
    assert rows[0]["score"] == 2


def test_lord_retry_or_replay_cannot_add_a_second_weekly_point():
    conn = _db()
    _add_user(conn, 7)
    _insert_review(
        conn,
        user_id=7,
        question_id=7001,
        reviewed_at="2026-08-24T00:00:00",
        grade=0,
        source_context=_lord_verdict(attempt_id="attempt-first", question_id=7001),
    )
    _insert_review(
        conn,
        user_id=7,
        question_id=7001,
        reviewed_at="2026-08-24T00:01:00",
        grade=0,
        source_context=_lord_verdict(attempt_id="attempt-replay", question_id=7001),
    )
    conn.commit()

    rows = _rows(conn, "2026-08-23T16:00:00", "2026-08-30T16:00:00")
    assert len(rows) == 1
    assert rows[0]["score"] == 1


def test_lord_admission_has_weekly_monthly_window_parity():
    conn = _db()
    _add_user(conn, 7)
    _insert_review(
        conn,
        user_id=7,
        question_id=7001,
        reviewed_at="2026-08-20T00:00:00",
        grade=0,
        source_context=_lord_verdict(attempt_id="attempt-7001", question_id=7001),
    )
    _insert_review(
        conn,
        user_id=7,
        question_id=7002,
        reviewed_at="2026-08-25T00:00:00",
        grade=0,
        source_context=_lord_verdict(attempt_id="attempt-7002", question_id=7002),
    )
    conn.commit()

    weekly = _rows(conn, "2026-08-23T16:00:00", "2026-08-30T16:00:00")
    monthly = _rows(conn, "2026-07-31T16:00:00", "2026-08-31T16:00:00")
    assert weekly[0]["score"] == 1
    assert monthly[0]["score"] == 2


def test_lord_source_is_admitted_separately_from_the_b050_whitelist():
    assert AUTHORITATIVE_REVIEW_SOURCE_CONTEXT_PREFIXES == ("mbv1:", "daily_d5b:v1:")
    assert AUTHORITATIVE_REVIEW_SOURCE_PREFIXES == ("rt:",)
    assert is_authoritative_review_source_context("lord_trial:v1:server-result") is False

    malformed_payload = {
        "schema": "lord_trial_verdict_v1",
        "attempt_id": "attempt-7001",
        "question_id": 7001,
        "verdict": "AUTHORITATIVE_PASS",
        "authoritative_grade": 5,
        "judge_version": "not-the-server-judge",
        "reason_code": "answer_tree_leaf",
    }
    conn = _db()
    _add_user(conn, 7)
    _insert_review(
        conn,
        user_id=7,
        question_id=7001,
        reviewed_at="2026-08-25T00:00:00",
        grade=5,
        source_context="lord_trial:v1:" + json.dumps(malformed_payload),
    )
    conn.commit()
    assert _rows(conn, "2026-08-23T16:00:00", "2026-08-30T16:00:00") == []
