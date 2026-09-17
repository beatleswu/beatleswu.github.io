from __future__ import annotations

import json
import sqlite3

import pytest

from adventure_progress_compatibility import (
    current_adventure_question_count,
    visible_adventure_question_count,
    visible_adventure_question_ids,
)
from adventure_progress_recovery import (
    EVIDENCE_CLASS_ALREADY_CREDITED,
    EVIDENCE_CLASS_UNRESOLVED_GAP,
    GAP_REASON_CANONICAL_IDENTITY_UNRESOLVED,
    GAP_REASON_CORRECTNESS_AUTHORITY_MISSING,
    OWNER_POLICY_REASON,
    RecoveryCandidateError,
    build_owner_policy_package,
    build_owner_policy_progression_dry_run,
    build_owner_policy_recovery_set,
    build_owner_policy_reported_player_dry_run,
    owner_policy_reward_deltas,
    recovery_question_ids,
    rollback_owner_policy_operation,
    write_owner_policy_records,
)
from migrations.adventure_progress_recovery_v1 import (
    HISTORICAL_CORRECTNESS_UNRESOLVED_DUE_TO_INCIDENT,
    POLICY_CLASSIFICATION_CORRECTNESS_AUTHORITY_MISSING,
    upgrade,
)


START = "2026-08-03T12:54:13Z"


def _connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def _gap_row(**overrides):
    row = {
        "user_id": "7",
        "zone_key": "k26_30",
        "canonical_question_id": "uuid-101",
        "legacy_question_id": "101",
        "evidence_class": EVIDENCE_CLASS_UNRESOLVED_GAP,
        "gap_reason": GAP_REASON_CORRECTNESS_AUTHORITY_MISSING,
        "existing_credit": "0",
        "first_event_at": "2026-09-16T16:00:00Z",
        "last_event_at": "2026-09-16T16:00:00Z",
        "source_row_count": "1",
        "provenance": "review_log:source_context=practice;server_correctness=UNRESOLVED;epoch=A",
        # Deliberately present but not an authority input.
        "grade": "5",
    }
    row.update(overrides)
    return row


def _result(rows, *, identity_rows=(), end="STILL_ACTIVE"):
    return build_owner_policy_recovery_set(
        rows,
        identity_rows=identity_rows,
        affected_user_ids={7, 991294},
        incident_start=START,
        incident_end=end,
        operation_id="owner-op-1",
    )


def test_one_owner_policy_pair_adds_exactly_one_credit():
    result = _result([_gap_row()])
    assert result["preliminary_policy_pairs"] == 1
    record = result["records"][0]
    assert record.credit_delta == 1
    assert record.policy_classification == POLICY_CLASSIFICATION_CORRECTNESS_AUTHORITY_MISSING
    assert record.historical_correctness_status == HISTORICAL_CORRECTNESS_UNRESOLVED_DUE_TO_INCIDENT

    conn = _connection()
    upgrade(conn)
    assert write_owner_policy_records(conn, result["records"]) == {"inserted": 1, "duplicates": 0}
    conn.commit()
    assert recovery_question_ids(conn, 7) == {101}


def test_progression_reader_unions_trusted_current_and_owner_policy_credit():
    conn = _connection()
    conn.execute(
        "CREATE TABLE review_log (user_id INTEGER, question_id INTEGER, grade INTEGER, source_context TEXT)"
    )
    conn.execute("INSERT INTO review_log VALUES (7, 100, 5, 'mbv1:owner-policy-test')")
    upgrade(conn)
    result = _result([_gap_row()])
    assert write_owner_policy_records(conn, result["records"]) == {"inserted": 1, "duplicates": 0}
    conn.commit()

    assert visible_adventure_question_ids(conn, 7) == {100, 101}
    assert visible_adventure_question_count(conn, 7, [100, 101, 102]) == 2
    assert current_adventure_question_count(conn, 7, [100, 101, 102]) == 1


def test_already_credited_pair_is_excluded_with_zero_delta():
    result = _result(
        [
            _gap_row(
                evidence_class=EVIDENCE_CLASS_ALREADY_CREDITED,
                gap_reason="ALREADY_CREDITED",
                existing_credit="1",
            )
        ]
    )
    assert result["records"] == ()
    assert result["already_credited_excluded"] == 1


def test_duplicate_package_rows_create_one_pair_and_report_exclusion():
    result = _result([_gap_row(), _gap_row()])
    assert result["preliminary_policy_pairs"] == 1
    assert result["duplicate_pairs_excluded"] == 1


def test_second_identical_apply_is_a_noop():
    result = _result([_gap_row()])
    conn = _connection()
    upgrade(conn)
    assert write_owner_policy_records(conn, result["records"]) == {"inserted": 1, "duplicates": 0}
    conn.commit()
    assert write_owner_policy_records(conn, result["records"]) == {"inserted": 0, "duplicates": 1}
    conn.rollback()
    assert recovery_question_ids(conn, 7) == {101}


def test_identity_unresolved_is_hold_and_not_apply_eligible():
    result = _result(
        [],
        identity_rows=[
            {
                "user_id": "7",
                "zone_key": "k26_30",
                "canonical_question_id": "",
                "gap_reason": GAP_REASON_CANONICAL_IDENTITY_UNRESOLVED,
            }
        ],
    )
    assert result["records"] == ()
    assert result["identity_unresolved_excluded"] == 1


def test_owner_policy_does_not_assert_historical_correctness():
    result = _result([_gap_row(grade="0", source_context="practice")])
    record = result["records"][0]
    assert record.historical_correctness_status == HISTORICAL_CORRECTNESS_UNRESOLVED_DUE_TO_INCIDENT
    assert record.policy_classification == POLICY_CLASSIFICATION_CORRECTNESS_AUTHORITY_MISSING
    assert not hasattr(record, "server_correct")


def test_owner_policy_package_contains_no_fake_mbv1_submission_verdict_or_moves():
    result = _result([_gap_row()])
    package = build_owner_policy_package(
        result,
        operation_id="owner-op-1",
        incident_start=START,
        incident_end="STILL_ACTIVE",
    )
    serialized = json.dumps(package, sort_keys=True).lower()
    assert "mbv1" not in serialized
    assert "submission" not in serialized
    assert "verdict" not in serialized
    assert "move_sequence" not in serialized


def test_reward_side_effects_are_all_zero():
    assert all(value == 0 for value in owner_policy_reward_deltas().values())


def test_lord_threshold_crossing_only_makes_challenge_eligible():
    result = _result([_gap_row()])
    dry_run = build_owner_policy_progression_dry_run(
        {(7, "k26_30"): 0},
        result["records"],
        zone_thresholds={"k26_30": 1},
    )
    assert dry_run["players_crossing_lord_threshold"] == 1
    assert dry_run["reward_deltas"]["lord_defeat"] == 0


def test_lord_victory_is_never_granted_by_threshold_crossing():
    result = _result([_gap_row()])
    dry_run = build_owner_policy_progression_dry_run(
        {(7, "k26_30"): 0}, result["records"], zone_thresholds={"k26_30": 1}
    )
    assert dry_run["lord_defeated_delta"] == 0
    assert dry_run["zone_clear_delta"] == 0
    assert dry_run["star_grant_delta"] == 0


def test_injected_failure_rolls_back_all_owner_policy_rows():
    result = _result([_gap_row(), _gap_row(canonical_question_id="uuid-102", legacy_question_id="102")])
    conn = _connection()
    upgrade(conn)
    conn.commit()
    conn.execute("BEGIN")
    write_owner_policy_records(conn, result["records"])
    conn.rollback()
    assert conn.execute("SELECT COUNT(*) FROM adventure_progress_recovery_ledger").fetchone()[0] == 0


def test_owner_policy_package_hash_is_order_independent():
    result_a = _result([_gap_row(), _gap_row(canonical_question_id="uuid-102", legacy_question_id="102")])
    result_b = _result([_gap_row(canonical_question_id="uuid-102", legacy_question_id="102"), _gap_row()])
    package_a = build_owner_policy_package(
        result_a, operation_id="owner-op-1", incident_start=START, incident_end="STILL_ACTIVE"
    )
    package_b = build_owner_policy_package(
        result_b, operation_id="owner-op-1", incident_start=START, incident_end="STILL_ACTIVE"
    )
    assert package_a["package_sha256"] == package_b["package_sha256"]


def test_reported_player_is_resolved_by_username_for_dry_run():
    result = _result([_gap_row(user_id="7")])
    projection = build_owner_policy_reported_player_dry_run(
        "g_andychiang06_81928",
        [{"user_id": 7, "username": "g_andychiang06_81928", "is_admin": False}],
        {(7, "k26_30"): 0},
        result["records"],
        zone_key="k26_30",
        lord_threshold=1,
    )
    assert projection["username"] == "g_andychiang06_81928"
    assert projection["current_progress"] == 0
    assert projection["policy_pair_count"] == 1
    assert projection["post_policy_progress"] == 1
    assert projection["can_challenge_lord"] is True
    assert projection["lord_defeated"] is False


def test_final_incident_window_refresh_changes_package_without_applying():
    rows = [
        _gap_row(),
        _gap_row(
            canonical_question_id="uuid-102",
            legacy_question_id="102",
            first_event_at="2026-09-18T16:00:00Z",
        ),
    ]
    preliminary = _result(rows, end="2026-09-17T00:00:00Z")
    final = _result(rows, end="2026-09-19T00:00:00Z")
    assert preliminary["preliminary_policy_pairs"] == 1
    assert final["preliminary_policy_pairs"] == 2
    package_a = build_owner_policy_package(
        preliminary,
        operation_id="owner-op-1",
        incident_start=START,
        incident_end="2026-09-17T00:00:00Z",
    )
    package_b = build_owner_policy_package(
        final,
        operation_id="owner-op-1",
        incident_start=START,
        incident_end="2026-09-19T00:00:00Z",
    )
    assert package_a["package_sha256"] != package_b["package_sha256"]
    assert "production_apply" not in package_b


def test_final_package_preserves_authoritative_incident_end_precision():
    result = _result([_gap_row()])
    package = build_owner_policy_package(
        result,
        operation_id="owner-op-final",
        incident_start=START,
        incident_end="2026-09-17T02:53:29.2448507Z",
    )
    assert package["incident_start"] == START
    assert package["incident_end"] == "2026-09-17T02:53:29.2448507Z"


def test_owner_policy_rollback_is_operation_scoped():
    result = _result([_gap_row()])
    conn = _connection()
    upgrade(conn)
    write_owner_policy_records(conn, result["records"])
    conn.commit()
    assert rollback_owner_policy_operation(conn, "owner-op-1") == 1
    conn.commit()
    assert recovery_question_ids(conn, 7) == set()


def test_owner_policy_writer_rejects_non_owner_record():
    result = _result([_gap_row()])
    bad = result["records"][0]
    with pytest.raises(RecoveryCandidateError):
        # A fresh record with the same gap class but no Owner reason cannot be
        # smuggled into the apply writer.
        bad.__class__(
            user_id=bad.user_id,
            zone_key=bad.zone_key,
            canonical_question_id=bad.canonical_question_id,
            legacy_question_id=bad.legacy_question_id,
            existing_credit=False,
            proposed_recovery_credit=1,
            recovery_reason="P0_ADVENTURE_PROGRESS_MAKE_WHOLE_2026",
            operation_id="owner-op-2",
            provenance=bad.provenance,
            evidence_class=EVIDENCE_CLASS_UNRESOLVED_GAP,
            apply_eligible=True,
            gap_reason=GAP_REASON_CORRECTNESS_AUTHORITY_MISSING,
            policy_classification=POLICY_CLASSIFICATION_CORRECTNESS_AUTHORITY_MISSING,
            credit_delta=1,
            historical_correctness_status=HISTORICAL_CORRECTNESS_UNRESOLVED_DUE_TO_INCIDENT,
        )
