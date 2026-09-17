from __future__ import annotations

import json
import sqlite3
import pytest

from adventure_progress_recovery import (
    EVIDENCE_CLASS_ALREADY_CREDITED,
    EVIDENCE_CLASS_PROVEN_RECOVERABLE,
    EVIDENCE_CLASS_UNRESOLVED_GAP,
    NORMAL_ADVENTURE_ORIGIN,
    RECOVERY_REASON,
    RecoveryRecord,
    build_recovery_candidates,
    build_recovery_decision_set,
    build_recovery_package,
    recovery_question_ids,
    rollback_operation,
    union_current_with_recovery,
    write_recovery_records,
    write_decision_records,
)
from adventure_progress_compatibility import recovery_memberships
from migrations.adventure_progress_recovery_v1 import upgrade


def _connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def _evidence(**overrides):
    row = {
        "user_id": 7,
        "question_id": 101,
        "zone_key": "k26_30",
        "event_at": "2026-09-16T16:00:00Z",
        "server_correct": True,
        "incident_route": NORMAL_ADVENTURE_ORIGIN,
        "source_context": "practice",
        "provenance": {
            "authority": "server_judge_fixture",
            "note": "source_context is preserved, not used as a correctness predicate",
        },
        # A grade is deliberately present but is never consumed by the builder.
        "grade": 0,
    }
    row.update(overrides)
    return row


def test_practice_label_is_not_exclusion_but_grade_is_not_authority():
    result = build_recovery_candidates(
        [
            _evidence(),
            _evidence(),  # same user/question/Zone must deduplicate
            _evidence(question_id=999),  # not in the canonical Zone pool
            _evidence(server_correct=False),
        ],
        affected_user_ids={7},
        zone_question_identity={"k26_30": {101: "uuid-101"}},
        incident_start="2026-08-03T12:54:13Z",
        incident_end="STILL_ACTIVE",
        operation_id="op-1",
    )

    records = result["records"]
    assert len(records) == 1
    assert records[0].canonical_question_id == "uuid-101"
    assert records[0].proposed_recovery_credit == 1
    assert result["skipped"]["server_correctness_not_proven"] == 1

    package_a = build_recovery_package(result, operation_id="op-1")
    package_b = build_recovery_package(
        {**result, "records": tuple(reversed(records))}, operation_id="op-1"
    )
    assert package_a["sha256"] == package_b["sha256"]
    assert package_a["record_count"] == 1
    assert json.loads(json.dumps(package_a, sort_keys=True))["records"][0][
        "existing_credit"
    ] is False


def test_existing_credit_is_union_deduplicated_and_not_rewritten():
    result = build_recovery_candidates(
        [_evidence()],
        affected_user_ids={7},
        zone_question_identity={"k26_30": {101: "uuid-101"}},
        existing_credit={(7, "uuid-101", "k26_30", RECOVERY_REASON)},
        incident_start="2026-08-03T12:54:13Z",
        incident_end="2026-09-17T00:00:00Z",
        operation_id="op-2",
    )
    assert result["records"] == ()
    assert len(result["already_credited"]) == 1


def test_ledger_replay_and_rollback_are_caller_transaction_owned():
    conn = _connection()
    upgrade(conn)
    record = RecoveryRecord(
        user_id=7,
        zone_key="k26_30",
        canonical_question_id="uuid-101",
        legacy_question_id=101,
        existing_credit=False,
        proposed_recovery_credit=1,
        recovery_reason=RECOVERY_REASON,
        operation_id="op-3",
        provenance='{"authority":"server_judge_fixture"}',
    )

    assert write_recovery_records(conn, [record]) == {"inserted": 1, "duplicates": 0}
    conn.commit()
    assert write_recovery_records(conn, [record]) == {"inserted": 0, "duplicates": 1}
    conn.rollback()
    assert recovery_question_ids(conn, 7) == {101}
    assert union_current_with_recovery(conn, 7, {202}) == {101, 202}

    assert rollback_operation(conn, "op-3") == 1
    # The caller chooses whether to commit the rollback; no helper commit has
    # occurred implicitly.
    conn.commit()
    assert recovery_question_ids(conn, 7) == set()
    conn.close()


def test_gap_inventory_is_visible_but_not_apply_eligible():
    result = build_recovery_decision_set(
        [],
        gap_rows=[
            {
                "user_id": 7,
                "question_id": 101,
                "zone_key": "k26_30",
                "event_at": "2026-09-16T10:00:00Z",
                "incident_route": NORMAL_ADVENTURE_ORIGIN,
                "provenance": "review_log:source_context=practice;correctness=unresolved",
            },
            {
                "user_id": 7,
                "question_id": 102,
                "zone_key": "k26_30",
                "event_at": "2026-09-16T10:01:00Z",
                "incident_route": NORMAL_ADVENTURE_ORIGIN,
                "provenance": "review_log:source_context=practice;correctness=unresolved",
            },
        ],
        affected_user_ids={7},
        zone_question_identity={"k26_30": {101: "uuid-101", 102: "uuid-102"}},
        existing_credit={(7, "uuid-101", "k26_30", RECOVERY_REASON)},
        incident_start="2026-08-03T12:54:13Z",
        incident_end="STILL_ACTIVE",
        operation_id="op-gap",
    )
    assert [record.evidence_class for record in result["records"]] == [
        EVIDENCE_CLASS_ALREADY_CREDITED,
        EVIDENCE_CLASS_UNRESOLVED_GAP,
    ]
    assert result["strict_proven_records"] == ()
    assert result["owner_policy_gap_records"][0].apply_eligible is False

    conn = _connection()
    upgrade(conn)
    assert write_decision_records(conn, result["records"]) == {
        "inserted": 2,
        "duplicates": 0,
    }
    conn.commit()
    # Decision inventory is retained in the ledger, but it cannot affect the
    # progression consumer until an explicit proven record is admitted.
    assert recovery_question_ids(conn, 7) == set()
    assert recovery_memberships(conn, user_id=7) == set()
    with pytest.raises(Exception):
        write_recovery_records(conn, [result["owner_policy_gap_records"][0]])


def test_strict_record_wins_same_pair_and_only_strict_record_is_read():
    result = build_recovery_decision_set(
        [_evidence()],
        gap_rows=[_evidence(provenance="review_log:practice;correctness=unresolved")],
        affected_user_ids={7},
        zone_question_identity={"k26_30": {101: "uuid-101"}},
        incident_start="2026-08-03T12:54:13Z",
        incident_end="STILL_ACTIVE",
        operation_id="op-mixed",
    )
    assert len(result["records"]) == 1
    assert result["records"][0].evidence_class == EVIDENCE_CLASS_PROVEN_RECOVERABLE
    assert result["records"][0].apply_eligible is True
    assert build_recovery_package(result, operation_id="op-mixed")[
        "strict_proven_record_count"
    ] == 1


def test_prevalidation_prevents_partial_write_on_mixed_failure():
    conn = _connection()
    upgrade(conn)
    valid = RecoveryRecord(
        user_id=7,
        zone_key="k26_30",
        canonical_question_id="uuid-101",
        legacy_question_id=101,
        existing_credit=False,
        proposed_recovery_credit=1,
        recovery_reason=RECOVERY_REASON,
        operation_id="op-partial",
        provenance='{"authority":"server_judge_fixture"}',
    )
    gap = RecoveryRecord(
        user_id=7,
        zone_key="k26_30",
        canonical_question_id="uuid-102",
        legacy_question_id=102,
        existing_credit=False,
        proposed_recovery_credit=0,
        recovery_reason=RECOVERY_REASON,
        operation_id="op-partial",
        provenance="review_log:practice;correctness=unresolved",
        evidence_class=EVIDENCE_CLASS_UNRESOLVED_GAP,
        apply_eligible=False,
    )
    with pytest.raises(Exception):
        write_recovery_records(conn, [valid, gap])
    assert conn.execute(
        "SELECT COUNT(*) FROM adventure_progress_recovery_ledger"
    ).fetchone()[0] == 0
