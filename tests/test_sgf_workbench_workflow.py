"""Deterministic report-to-ready-for-apply Workbench workflow tests."""

from __future__ import annotations

import sqlite3

import pytest

import sgf_admin_workbench as wb


CONTENT_SHA = "a" * 64


def _db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    wb.ensure_sgf_workbench_tables(conn)
    return conn


def _record():
    return {
        "id": 431,
        "content": "(;GM[1]FF[4]SZ[19])",
        "accepted_moves": [{"x": 3, "y": 3}],
        "enabled": True,
    }


def _report(conn, *, key="workflow-report", move=None):
    return wb.capture_workbench_report(
        conn,
        source="PLAYER_REPORT",
        reporter_id=11,
        question_id=431,
        record_index=0,
        issue_type="ALTERNATIVE_CORRECT_MOVE",
        candidate_move=move or {"x": 15, "y": 3},
        observed_system_verdict="WRONG",
        gameplay_surface="main_practice",
        sgf_identity="sgf-431",
        node_identity="root",
        board_state={"stones": []},
        question_content_sha256=CONTENT_SHA,
        source_provenance={"fixture": "workflow"},
        external_key=key,
        now="2026-08-14T00:00:00+00:00",
    )


def _stage(conn, item_id, *, key="workflow-repair", baseline=CONTENT_SHA):
    record = _record()
    return wb.stage_workbench_repair(
        conn,
        item_id=item_id,
        reviewer_id=7,
        action="ADD_ALTERNATIVE_CORRECT_MOVE",
        original_state={"accepted_moves": record["accepted_moves"]},
        proposed_state={
            "accepted_moves": record["accepted_moves"] + [{"x": 15, "y": 3}],
            "enabled": True,
        },
        candidate_move={"x": 15, "y": 3},
        source_provenance={
            "review_item_id": item_id,
            "canonical_record_hash": wb.direct_record_hash(record),
        },
        baseline_sha256=baseline,
        mutation_key=key,
        now="2026-08-14T00:00:01+00:00",
    )


def _validate(conn, repair_id, *, content_sha=CONTENT_SHA, record=None):
    record = record or _record()
    return wb.validate_staged_repair(
        conn,
        repair_id=repair_id,
        actor_id=7,
        current_record=record,
        current_content_sha256=content_sha,
        current_record_hash=wb.direct_record_hash(record),
        now="2026-08-14T00:00:02+00:00",
    )


def _ready_bases(item_id, record=None, content_sha=CONTENT_SHA):
    record = record or _record()
    return {
        item_id: {
            "content_sha256": content_sha,
            "record_hash": wb.direct_record_hash(record),
        }
    }


def test_report_stage_validate_batch_ready_is_audited_and_non_mutating():
    conn = _db()
    canonical_before = _record()
    capture = _report(conn)
    repair = _stage(conn, capture["review_item_id"])

    validation = _validate(conn, repair["id"])
    assert validation["status"] == "PASS"
    assert validation["canonical_mutation"] is False

    batch = wb.create_workbench_batch(
        conn,
        created_by=7,
        baseline_sha256=CONTENT_SHA,
        require_validation=True,
        idempotency_key="workflow-batch",
        now="2026-08-14T00:00:03+00:00",
    )
    assert batch["status"] == "STAGED"
    assert batch["manifest"]["validation_required"] is True

    ready = wb.mark_batch_ready_for_apply(
        conn,
        batch_id=batch["id"],
        actor_id=7,
        current_bases=_ready_bases(capture["review_item_id"]),
        now="2026-08-14T00:00:04+00:00",
    )
    assert ready["status"] == "READY_FOR_APPLY"
    assert ready["ready_for_apply"] is True
    assert ready["canonical_mutation"] is False
    assert _record() == canonical_before

    actions = [row[0] for row in conn.execute(
        "SELECT action FROM sgf_workbench_audit ORDER BY id"
    ).fetchall()]
    assert actions == [
        "REPORT_CAPTURED",
        "STAGED_REPAIR",
        "VALIDATION_PASS",
        "BATCH_CREATED",
        "READY_FOR_APPLY",
    ]

    duplicate = wb.mark_batch_ready_for_apply(
        conn,
        batch_id=batch["id"],
        actor_id=7,
        current_bases=_ready_bases(capture["review_item_id"]),
        now="2026-08-14T00:00:05+00:00",
    )
    assert duplicate["duplicate"] is True
    assert duplicate["status"] == "READY_FOR_APPLY"


def test_validation_requires_current_basis_and_marks_stale_without_batching():
    conn = _db()
    capture = _report(conn, key="stale-report")
    repair = _stage(conn, capture["review_item_id"], key="stale-repair")

    result = _validate(conn, repair["id"], content_sha="b" * 64)
    assert result["status"] == "STALE"
    assert "canonical_content_basis_changed" in result["errors"]
    assert result["canonical_mutation"] is False
    assert wb.get_workbench_item(conn, capture["review_item_id"])["status"] == "STALE"
    with pytest.raises(wb.InvalidWorkbenchState, match="validation_required"):
        wb.create_workbench_batch(conn, created_by=7, require_validation=True)


def test_invalid_validation_and_unvalidated_batch_fail_closed():
    conn = _db()
    capture = _report(conn, key="invalid-report")
    record = _record()
    repair = wb.stage_workbench_repair(
        conn,
        item_id=capture["review_item_id"],
        reviewer_id=7,
        action="ADD_ALTERNATIVE_CORRECT_MOVE",
        original_state={"accepted_moves": record["accepted_moves"]},
        proposed_state={"accepted_moves": []},
        candidate_move={"x": 15, "y": 3},
        source_provenance={"canonical_record_hash": wb.direct_record_hash(record)},
        baseline_sha256=CONTENT_SHA,
        mutation_key="invalid-repair",
    )
    result = _validate(conn, repair["id"])
    assert result["status"] == "FAIL"
    assert "empty_answer_set" in result["errors"]
    with pytest.raises(wb.InvalidWorkbenchState, match="validation_required"):
        wb.create_workbench_batch(conn, created_by=7, require_validation=True)


def test_ready_gate_rejects_stale_basis_and_keeps_batch_staged():
    conn = _db()
    capture = _report(conn, key="batch-stale-report")
    repair = _stage(conn, capture["review_item_id"], key="batch-stale-repair")
    assert _validate(conn, repair["id"])["status"] == "PASS"
    batch = wb.create_workbench_batch(conn, created_by=7, require_validation=True)

    blocked = wb.mark_batch_ready_for_apply(
        conn,
        batch_id=batch["id"],
        actor_id=7,
        current_bases=_ready_bases(capture["review_item_id"], content_sha="c" * 64),
    )
    assert blocked["status"] == "BLOCKED"
    assert blocked["ready_for_apply"] is False
    assert any(row["reason"] == "canonical_content_basis_changed" for row in blocked["failures"])
    assert conn.execute("SELECT status FROM sgf_workbench_batches").fetchone()[0] == "STAGED"


def test_validation_conflict_is_distinct_from_structural_failure():
    conn = _db()
    capture = _report(conn, key="conflict-report")
    repair = wb.stage_workbench_repair(
        conn,
        item_id=capture["review_item_id"],
        reviewer_id=7,
        action="ADD_ALTERNATIVE_CORRECT_MOVE",
        original_state={"accepted_moves": [{"x": 15, "y": 3}]},
        proposed_state={"accepted_moves": [{"x": 15, "y": 3}]},
        candidate_move={"x": 15, "y": 3},
        source_provenance={"canonical_record_hash": wb.direct_record_hash(_record())},
        baseline_sha256=CONTENT_SHA,
        mutation_key="conflict-repair",
    )
    result = _validate(conn, repair["id"])
    assert result["status"] == "CONFLICT"
    assert "alternative_already_accepted" in result["errors"]


def test_multiple_reports_and_repairs_form_one_deterministic_ready_batch():
    conn = _db()
    captures = []
    for index, move in enumerate(({"x": 15, "y": 3}, {"x": 14, "y": 3}), 1):
        captures.append(_report(conn, key=f"multi-report-{index}", move=move))
    for index, capture in enumerate(captures, 1):
        repair = wb.stage_workbench_repair(
            conn,
            item_id=capture["review_item_id"],
            reviewer_id=7,
            action="ADD_ALTERNATIVE_CORRECT_MOVE",
            original_state={"accepted_moves": _record()["accepted_moves"]},
            proposed_state={"accepted_moves": _record()["accepted_moves"] + [_report_move(capture)]},
            candidate_move=_report_move(capture),
            source_provenance={"canonical_record_hash": wb.direct_record_hash(_record())},
            baseline_sha256=CONTENT_SHA,
            mutation_key=f"multi-repair-{index}",
        )
        assert _validate(conn, repair["id"])["status"] == "PASS"
    batch = wb.create_workbench_batch(
        conn, created_by=7, require_validation=True, idempotency_key="multi-batch"
    )
    assert batch["staged_count"] == 2
    assert len(batch["manifest"]["repairs"]) == 2


def test_disposable_postgres_complete_workflow_and_ready_gate():
    url = __import__("os").environ.get("SGF_WORKBENCH_PERSISTENCE_DATABASE_URL")
    if not url:
        pytest.skip("requires explicitly marked disposable PostgreSQL")
    import psycopg2
    from psycopg2.extras import DictCursor
    from db import PostgresConnectionWrapper
    from migrations.sgf_admin_workbench_v1 import TABLE_SPECS, upgrade, validate_schema

    raw = psycopg2.connect(url)
    raw.cursor_factory = DictCursor
    conn = PostgresConnectionWrapper(raw)
    try:
        conn.execute(
            "DROP TABLE IF EXISTS "
            + ", ".join(f"public.{name}" for name in reversed(tuple(TABLE_SPECS)))
            + " CASCADE"
        )
        conn.commit()
        upgrade(conn)
        conn.commit()
        assert validate_schema(conn)["missing"] == []
        capture = _report(conn, key="pg-workflow-report")
        repair = _stage(conn, capture["review_item_id"], key="pg-workflow-repair")
        assert _validate(conn, repair["id"])["status"] == "PASS"
        batch = wb.create_workbench_batch(conn, created_by=7, require_validation=True, idempotency_key="pg-workflow-batch")
        ready = wb.mark_batch_ready_for_apply(
            conn, batch_id=batch["id"], actor_id=7,
            current_bases=_ready_bases(capture["review_item_id"]),
        )
        conn.commit()
        assert ready["status"] == "READY_FOR_APPLY"
        assert conn.execute("SELECT COUNT(*) AS n FROM sgf_workbench_audit").fetchone()["n"] >= 5
        assert conn.execute("SELECT version() AS v").fetchone()["v"].startswith("PostgreSQL 16.")
    finally:
        conn.rollback()
        conn.close()


def _report_move(capture):
    return capture["report"]["candidate_move"]
