from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from adventure_progress_compatibility import (
    visible_adventure_question_count,
    visible_adventure_question_ids,
)
from adventure_progress_recovery import (
    EVIDENCE_CLASS_UNRESOLVED_GAP,
    GAP_REASON_CANONICAL_IDENTITY_UNRESOLVED,
    OWNER_POLICY_REASON,
    RecoveryCandidateError,
    RecoveryRecord,
    owner_policy_reward_deltas,
    write_decision_records,
    write_recovery_records,
)
from adventure_zone_progression_authority import lord_eligibility_requirement
from migrations.adventure_progress_recovery_v1 import (
    TABLE_NAME,
    validate_schema,
    upgrade,
)


def _connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE review_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            grade INTEGER NOT NULL,
            source_context TEXT
        )"""
    )
    return conn


def _review(conn: sqlite3.Connection, user_id: int, question_id: int, source: str) -> None:
    conn.execute(
        "INSERT INTO review_log(user_id,question_id,grade,source_context) VALUES (?,?,?,?)",
        (user_id, question_id, 4, source),
    )


def _owner_record(
    *,
    user_id: int,
    question_id: int,
    operation_id: str = "admission-op",
    canonical_question_id: str | None = None,
) -> RecoveryRecord:
    return RecoveryRecord(
        user_id=user_id,
        zone_key="k26_30",
        canonical_question_id=canonical_question_id or f"canonical-{question_id}",
        legacy_question_id=question_id,
        existing_credit=False,
        proposed_recovery_credit=1,
        recovery_reason=OWNER_POLICY_REASON,
        operation_id=operation_id,
        provenance="incident:owner-policy;historical_correctness=unresolved_due_to_incident",
        evidence_class=EVIDENCE_CLASS_UNRESOLVED_GAP,
        apply_eligible=True,
        gap_reason="CORRECTNESS_AUTHORITY_MISSING",
        credit_delta=1,
    )


def test_app_wires_only_the_empty_idempotent_schema_admission():
    source = (Path(__file__).resolve().parents[1] / "app.py").read_text(
        encoding="utf-8"
    )
    assert "upgrade_adventure_progress_recovery_schema" in source
    assert "upgrade_adventure_progress_recovery_schema(conn)" in source
    assert "P0 Lane C: admit the additive recovery ledger schema only" in source


def test_empty_ledger_migration_is_additive_idempotent_and_empty():
    conn = _connection()

    first = upgrade(conn)
    second = upgrade(conn)

    assert first["dry_run"] is False
    assert second["dry_run"] is False
    assert validate_schema(conn)["missing"] == []
    assert conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM review_log").fetchone()[0] == 0
    assert owner_policy_reward_deltas() == {
        "coins": 0,
        "xp": 0,
        "stars": 0,
        "lord_defeat": 0,
        "zone_clear": 0,
        "first_clear": 0,
        "first_clear_reward": 0,
        "leaderboard_reward": 0,
        "event_achievement": 0,
        "boss_settlement": 0,
        "quest_reward": 0,
    }


def test_empty_recovery_ledger_preserves_ordinary_practice_progress_and_threshold_state():
    conn = _connection()
    _review(conn, 10, 1001, "mbv1:ordinary")
    _review(conn, 11, 1002, "practice:v1:server-judge")
    _review(conn, 12, 1003, "mbv1:already-progressed")
    threshold = lord_eligibility_requirement(1939)
    for question_id in range(1, threshold + 1):
        _review(conn, 13, question_id, "mbv1:threshold")

    before = {
        "ordinary": visible_adventure_question_count(conn, 10, {1001}),
        "practice": visible_adventure_question_count(
            conn, 11, {1002}, trusted_source_prefixes=("practice:v1:",)
        ),
        "progressed": visible_adventure_question_count(conn, 12, {1003}),
        "threshold": visible_adventure_question_count(
            conn, 13, set(range(1, threshold + 1))
        ),
    }

    upgrade(conn)

    after = {
        "ordinary": visible_adventure_question_count(conn, 10, {1001}),
        "practice": visible_adventure_question_count(
            conn, 11, {1002}, trusted_source_prefixes=("practice:v1:",)
        ),
        "progressed": visible_adventure_question_count(conn, 12, {1003}),
        "threshold": visible_adventure_question_count(
            conn, 13, set(range(1, threshold + 1))
        ),
    }

    assert after == before
    assert before == {
        "ordinary": 1,
        "practice": 1,
        "progressed": 1,
        "threshold": threshold,
    }
    assert conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0] == 0


def test_valid_pair_adds_one_and_duplicate_same_pair_is_bounded():
    conn = _connection()
    upgrade(conn)
    record = _owner_record(user_id=7, question_id=2001)

    assert visible_adventure_question_count(conn, 7, {2001}) == 0
    assert write_recovery_records(conn, [record]) == {"inserted": 1, "duplicates": 0}
    conn.commit()
    assert visible_adventure_question_count(conn, 7, {2001}) == 1
    assert visible_adventure_question_ids(conn, 7) == {2001}

    assert write_recovery_records(conn, [record]) == {"inserted": 0, "duplicates": 1}
    conn.commit()
    assert visible_adventure_question_count(conn, 7, {2001}) == 1
    assert conn.execute(
        f"SELECT COUNT(*) FROM {TABLE_NAME} WHERE user_id=? AND legacy_question_id=?",
        (7, 2001),
    ).fetchone()[0] == 1


def test_already_credited_and_identity_unresolved_pairs_cannot_credit():
    conn = _connection()
    upgrade(conn)
    _review(conn, 8, 3001, "mbv1:already-credited")

    already_credited = _owner_record(
        user_id=8,
        question_id=3001,
        canonical_question_id="canonical-3001",
    )
    assert visible_adventure_question_count(conn, 8, {3001}) == 1
    assert write_recovery_records(conn, [already_credited]) == {
        "inserted": 1,
        "duplicates": 0,
    }
    conn.commit()
    assert visible_adventure_question_count(conn, 8, {3001}) == 1

    unresolved_identity = RecoveryRecord(
        user_id=9,
        zone_key="k26_30",
        canonical_question_id="unresolved-placeholder",
        legacy_question_id=3002,
        existing_credit=False,
        proposed_recovery_credit=0,
        recovery_reason=OWNER_POLICY_REASON,
        operation_id="identity-hold",
        provenance="incident:identity-unresolved",
        evidence_class=EVIDENCE_CLASS_UNRESOLVED_GAP,
        apply_eligible=False,
        gap_reason=GAP_REASON_CANONICAL_IDENTITY_UNRESOLVED,
        credit_delta=0,
    )
    assert write_decision_records(conn, [unresolved_identity]) == {
        "inserted": 1,
        "duplicates": 0,
    }
    conn.commit()
    assert visible_adventure_question_count(conn, 9, {3002}) == 0
    with pytest.raises(RecoveryCandidateError):
        write_recovery_records(conn, [unresolved_identity])


def test_threshold_crossing_is_challenge_eligibility_only_and_rewards_stay_zero():
    conn = _connection()
    upgrade(conn)
    threshold = lord_eligibility_requirement(1939)
    for question_id in range(1, threshold):
        _review(conn, 14, question_id, "mbv1:threshold")
    record = _owner_record(user_id=14, question_id=threshold, operation_id="threshold-op")

    before = visible_adventure_question_count(conn, 14, set(range(1, threshold + 1)))
    assert before == threshold - 1
    assert write_recovery_records(conn, [record]) == {"inserted": 1, "duplicates": 0}
    conn.commit()
    after = visible_adventure_question_count(conn, 14, set(range(1, threshold + 1)))

    assert after == threshold
    assert after >= threshold
    can_challenge_lord = after >= threshold
    lord_defeated = False
    assert can_challenge_lord is True
    assert lord_defeated is False
    assert owner_policy_reward_deltas() == {key: 0 for key in owner_policy_reward_deltas()}
    assert conn.execute("SELECT COUNT(*) FROM review_log").fetchone()[0] == threshold - 1
    assert conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0] == 1
