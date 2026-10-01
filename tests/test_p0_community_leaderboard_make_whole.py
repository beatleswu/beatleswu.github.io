from __future__ import annotations

import sqlite3

import community_leaderboard_rewards as leaderboard
from community_leaderboard_make_whole import (
    INCIDENT_WINDOW_END,
    P0_MAKE_WHOLE_OPERATION_ID,
    classify_original_periods,
    fetch_p0_make_whole_period_rows,
)
from migrations.adventure_progress_recovery_v1 import (
    OWNER_POLICY_RECOVERY_REASON,
    upgrade,
)


WEEK_START = "2026-09-13T16:00:00"
WEEK_END = "2026-09-20T16:00:00"
MONTH_START = "2026-08-31T16:00:00"
MONTH_END = "2026-09-30T16:00:00"


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
        CREATE TABLE user_stats(user_id INTEGER PRIMARY KEY, rank_level TEXT);
        CREATE TABLE player_appearance(
            user_id INTEGER PRIMARY KEY, character_key TEXT,
            combat_armor TEXT, combat_weapon TEXT, combat_cape TEXT,
            combat_offhand TEXT, combat_hat TEXT, combat_pet TEXT,
            combat_aura TEXT
        );
        """
    )
    upgrade(conn)
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


def _add_review(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    question_id: int,
    reviewed_at: str,
    source_context: str | None = "practice",
    source: str | None = None,
    grade: int = 3,
) -> None:
    conn.execute(
        """INSERT INTO review_log(
               user_id, question_id, grade, reviewed_at, source, source_context
           ) VALUES (?, ?, ?, ?, ?, ?)""",
        (user_id, question_id, grade, reviewed_at, source, source_context),
    )


def _add_recovery(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    question_id: int,
    canonical_question_id: str,
) -> None:
    conn.execute(
        """INSERT INTO adventure_progress_recovery_ledger(
               operation_id, user_id, canonical_question_id,
               legacy_question_id, zone_key, recovery_reason, provenance,
               evidence_class, gap_reason, apply_eligible, existing_credit,
               proposed_recovery_credit, policy_classification, credit_delta,
               historical_correctness_status, created_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            P0_MAKE_WHOLE_OPERATION_ID,
            user_id,
            canonical_question_id,
            question_id,
            "k11_15",
            OWNER_POLICY_RECOVERY_REASON,
            "review_log:source_context=practice;server_correctness=UNRESOLVED;epoch=A",
            "UNRESOLVED_EVIDENCE_GAP",
            "CORRECTNESS_AUTHORITY_MISSING",
            1,
            0,
            1,
            "CORRECTNESS_AUTHORITY_MISSING",
            1,
            "UNRESOLVED_DUE_TO_INCIDENT",
            # Deliberately outside the answer period.  This must never be
            # consulted for Community period membership.
            "2026-09-17T10:26:36.604603+00:00",
        ),
    )


def test_owner_make_whole_uses_original_review_time_and_is_read_time_only():
    conn = _db()
    _add_user(conn, 1)
    _add_review(
        conn,
        user_id=1,
        question_id=101,
        reviewed_at="2026-09-14T01:00:00",
    )
    _add_recovery(conn, user_id=1, question_id=101, canonical_question_id="uuid-101")
    conn.commit()

    projection = fetch_p0_make_whole_period_rows(conn, WEEK_START, WEEK_END)
    assert [row.key for row in projection["candidate_rows"]] == [(1, 101)]
    assert projection["candidate_rows"][0].original_activity_timestamp == "2026-09-14T01:00:00"
    assert projection["candidate_rows"][0].historical_correctness_status == "UNRESOLVED_DUE_TO_INCIDENT"
    assert conn.execute(
        "SELECT COUNT(*) FROM adventure_progress_recovery_ledger"
    ).fetchone()[0] == 1

    normal = leaderboard.fetch_leaderboard_participant_rows(
        conn, WEEK_START, WEEK_END, include_p0_make_whole=False
    )
    effective = leaderboard.fetch_leaderboard_participant_rows(
        conn, WEEK_START, WEEK_END, include_p0_make_whole=True
    )
    assert normal == []
    assert [(row["id"], row["score"]) for row in effective] == [(1, 1)]


def test_trusted_overlap_is_zero_additional_credit():
    conn = _db()
    _add_user(conn, 1)
    _add_review(
        conn,
        user_id=1,
        question_id=101,
        reviewed_at="2026-09-14T01:00:00",
        source_context="",
        source="rt:validated",
    )
    _add_recovery(conn, user_id=1, question_id=101, canonical_question_id="uuid-101")
    conn.commit()

    normal = leaderboard.fetch_leaderboard_participant_rows(
        conn, WEEK_START, WEEK_END, include_p0_make_whole=False
    )
    projection = fetch_p0_make_whole_period_rows(
        conn,
        WEEK_START,
        WEEK_END,
        normal_identity_keys={(1, 101)},
    )
    effective = leaderboard.fetch_leaderboard_participant_rows(
        conn, WEEK_START, WEEK_END, include_p0_make_whole=True
    )
    assert normal[0]["score"] == 1
    assert projection["candidate_rows"] == []
    assert projection["trusted_overlap_keys"] == {(1, 101)}
    assert effective[0]["score"] == 1


def test_make_whole_then_trusted_and_trusted_then_make_whole_are_idempotent():
    conn = _db()
    _add_user(conn, 1)
    _add_review(conn, user_id=1, question_id=101, reviewed_at="2026-09-14T01:00:00")
    _add_recovery(conn, user_id=1, question_id=101, canonical_question_id="uuid-101")
    conn.commit()

    first = leaderboard.fetch_leaderboard_participant_rows(
        conn, WEEK_START, WEEK_END, include_p0_make_whole=True
    )
    second = leaderboard.fetch_leaderboard_participant_rows(
        conn, WEEK_START, WEEK_END, include_p0_make_whole=True
    )
    assert first[0]["score"] == second[0]["score"] == 1

    _add_review(
        conn,
        user_id=1,
        question_id=101,
        reviewed_at="2026-09-15T01:00:00",
        source_context="",
        source="rt:later-trusted",
    )
    conn.commit()
    trusted_after = leaderboard.fetch_leaderboard_participant_rows(
        conn, WEEK_START, WEEK_END, include_p0_make_whole=True
    )
    assert trusted_after[0]["score"] == 1


def test_ordinary_practice_is_not_normal_correctness_but_owner_policy_can_project_it():
    conn = _db()
    _add_user(conn, 1)
    _add_review(
        conn,
        user_id=1,
        question_id=101,
        reviewed_at="2026-09-14T01:00:00",
        source_context="practice",
        source=None,
    )
    _add_recovery(conn, user_id=1, question_id=101, canonical_question_id="uuid-101")
    conn.commit()

    normal = leaderboard.fetch_leaderboard_participant_rows(
        conn, WEEK_START, WEEK_END, include_p0_make_whole=False
    )
    effective = leaderboard.fetch_leaderboard_participant_rows(
        conn, WEEK_START, WEEK_END, include_p0_make_whole=True
    )
    assert normal == []
    assert effective[0]["score"] == 1


def test_ambiguous_canonical_identity_fails_closed_for_that_pair():
    conn = _db()
    _add_user(conn, 1)
    _add_review(conn, user_id=1, question_id=101, reviewed_at="2026-09-14T01:00:00")
    _add_recovery(conn, user_id=1, question_id=101, canonical_question_id="uuid-101-a")
    _add_recovery(conn, user_id=1, question_id=101, canonical_question_id="uuid-101-b")
    conn.commit()

    projection = fetch_p0_make_whole_period_rows(conn, WEEK_START, WEEK_END)
    assert projection["candidate_rows"] == []
    assert projection["failed_identity_keys"] == {(1, 101)}


def test_temporal_classification_uses_original_evidence_not_recovery_created_at():
    conn = _db()
    _add_user(conn, 1)
    _add_user(conn, 2)
    _add_user(conn, 3)
    _add_review(conn, user_id=1, question_id=101, reviewed_at="2026-09-14T01:00:00")
    _add_review(conn, user_id=2, question_id=201, reviewed_at="2026-09-01T01:00:00")
    _add_review(conn, user_id=3, question_id=301, reviewed_at="2026-08-10T01:00:00")
    _add_recovery(conn, user_id=1, question_id=101, canonical_question_id="uuid-101")
    _add_recovery(conn, user_id=2, question_id=201, canonical_question_id="uuid-201")
    _add_recovery(conn, user_id=3, question_id=301, canonical_question_id="uuid-301")
    conn.commit()

    result = classify_original_periods(
        conn,
        week_start_iso=WEEK_START,
        week_end_iso=WEEK_END,
        month_start_iso=MONTH_START,
        month_end_iso=MONTH_END,
    )
    assert result["current_week_pairs"] == {(1, 101)}
    assert result["current_month_pairs"] == {(1, 101), (2, 201)}
    assert result["older_pairs"] == {(3, 301)}
    assert result["unresolved_pairs"] == set()


def test_missing_original_timestamp_fails_closed_without_using_ledger_clock():
    conn = _db()
    _add_user(conn, 1)
    _add_recovery(conn, user_id=1, question_id=101, canonical_question_id="uuid-101")
    conn.commit()

    projection = fetch_p0_make_whole_period_rows(conn, WEEK_START, WEEK_END)
    assert projection["candidate_rows"] == []
    assert projection["missing_time_keys"] == set()
    assert projection["applied_package_rows"] == 1


def test_all_applied_package_identities_are_considered_once():
    conn = _db()
    for user_id in range(1, 40):
        _add_user(conn, user_id)
    review_rows = []
    recovery_rows = []
    for index in range(2716):
        user_id = (index % 39) + 1
        question_id = 100000 + index
        review_rows.append((user_id, question_id, 3, "2026-09-14T01:00:00", None, "practice"))
        recovery_rows.append(
            (
                P0_MAKE_WHOLE_OPERATION_ID,
                user_id,
                f"uuid-{index}",
                question_id,
                "k11_15",
                OWNER_POLICY_RECOVERY_REASON,
                "review_log:source_context=practice;server_correctness=UNRESOLVED;epoch=A",
                "UNRESOLVED_EVIDENCE_GAP",
                "CORRECTNESS_AUTHORITY_MISSING",
                1,
                0,
                1,
                "CORRECTNESS_AUTHORITY_MISSING",
                1,
                "UNRESOLVED_DUE_TO_INCIDENT",
                "2026-09-17T10:26:36.604603+00:00",
            )
        )
    conn.executemany(
        """INSERT INTO review_log(
               user_id, question_id, grade, reviewed_at, source, source_context
           ) VALUES (?, ?, ?, ?, ?, ?)""",
        review_rows,
    )
    conn.executemany(
        """INSERT INTO adventure_progress_recovery_ledger(
               operation_id, user_id, canonical_question_id,
               legacy_question_id, zone_key, recovery_reason, provenance,
               evidence_class, gap_reason, apply_eligible, existing_credit,
               proposed_recovery_credit, policy_classification, credit_delta,
               historical_correctness_status, created_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        recovery_rows,
    )
    conn.commit()

    projection = fetch_p0_make_whole_period_rows(conn, WEEK_START, WEEK_END)
    assert projection["applied_package_rows"] == 2716
    assert len(projection["candidate_rows"]) == 2716
    assert len(projection["candidate_keys"]) == 2716
    assert projection["trusted_overlap_keys"] == set()
    assert projection["failed_identity_keys"] == set()
