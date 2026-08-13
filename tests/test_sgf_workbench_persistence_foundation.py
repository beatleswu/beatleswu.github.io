"""Focused persistence-contract tests for the seven-table Workbench store."""

from __future__ import annotations

import os
import sqlite3

import pytest

import sgf_admin_workbench as wb


def _sqlite_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    wb.ensure_sgf_workbench_tables(conn)
    return conn


def _report(conn, *, external_key="foundation-report", now="2026-08-13T00:00:00+00:00"):
    return wb.capture_workbench_report(
        conn,
        source="PLAYER_REPORT",
        reporter_id=11,
        question_id=431,
        record_index=12,
        issue_type="ALTERNATIVE_CORRECT_MOVE",
        candidate_move={"x": 15, "y": 3},
        observed_system_verdict="WRONG",
        gameplay_surface="main_practice",
        sgf_identity="sgf-431",
        node_identity="node-1",
        board_state={"stones": []},
        source_provenance={"fixture": True},
        external_key=external_key,
        now=now,
    )


def _stage(conn, item_id, *, mutation_key="foundation-repair", now="2026-08-13T00:00:00+00:00"):
    return wb.stage_workbench_repair(
        conn,
        item_id=item_id,
        reviewer_id=7,
        action="ADD_ALTERNATIVE_CORRECT_MOVE",
        original_state={"accepted_moves": [{"x": 3, "y": 3}]},
        proposed_state={"accepted_moves": [{"x": 3, "y": 3}, {"x": 15, "y": 3}]},
        candidate_move={"x": 15, "y": 3},
        mutation_key=mutation_key,
        now=now,
    )


def test_repository_map_covers_all_seven_tables():
    mapping = wb.workbench_persistence_map()
    assert {entry["table"] for entry in mapping.values()} == {
        "sgf_workbench_reports",
        "sgf_workbench_review_items",
        "sgf_workbench_staged_repairs",
        "sgf_workbench_batches",
        "sgf_workbench_batch_items",
        "sgf_workbench_audit",
        "sgf_workbench_direct_versions",
    }


def test_staging_duplicate_is_idempotent_and_audited_once():
    conn = _sqlite_db()
    item = _report(conn)["review_item_id"]
    first = _stage(conn, item)
    duplicate = _stage(conn, item)
    assert first["id"] == duplicate["id"]
    assert duplicate["duplicate"] is True
    assert conn.execute(
        "SELECT COUNT(*) FROM sgf_workbench_staged_repairs WHERE mutation_key=?",
        ("foundation-repair",),
    ).fetchone()[0] == 1
    assert conn.execute(
        "SELECT COUNT(*) FROM sgf_workbench_audit WHERE action='STAGED_REPAIR'"
    ).fetchone()[0] == 1


def test_stale_and_terminal_state_transitions_fail_closed():
    conn = _sqlite_db()
    item = _report(conn)["review_item_id"]
    opened = wb.get_workbench_item(conn, item)
    wb.resolve_workbench_item(conn, item_id=item, reviewer_id=7, status="REJECTED")
    with pytest.raises(wb.InvalidWorkbenchState, match="invalid_state_transition"):
        _stage(conn, item)
    with pytest.raises(wb.StaleWorkbenchState, match="stale_workbench_item"):
        wb.resolve_workbench_item(
            conn,
            item_id=item,
            reviewer_id=7,
            status="NEEDS_RESEARCH",
            expected_item_updated_at=opened["updated_at"],
        )


def test_stage_audit_failure_rolls_back_repair_and_review_transition(monkeypatch):
    conn = _sqlite_db()
    item = _report(conn)["review_item_id"]

    def fail_audit(*_args, **_kwargs):
        raise RuntimeError("audit_sink_down")

    monkeypatch.setattr(wb, "_audit", fail_audit)
    with pytest.raises(RuntimeError, match="audit_sink_down"):
        _stage(conn, item)
    assert conn.execute("SELECT status FROM sgf_workbench_review_items").fetchone()[0] == "OPEN"
    assert conn.execute("SELECT COUNT(*) FROM sgf_workbench_staged_repairs").fetchone()[0] == 0


def test_batch_items_repairs_and_audit_are_one_atomic_operation(monkeypatch):
    conn = _sqlite_db()
    for index in range(2):
        item = _report(conn, external_key=f"batch-report-{index}")["review_item_id"]
        _stage(conn, item, mutation_key=f"batch-repair-{index}")

    def fail_audit(*_args, **_kwargs):
        raise RuntimeError("audit_sink_down")

    monkeypatch.setattr(wb, "_audit", fail_audit)
    with pytest.raises(RuntimeError, match="audit_sink_down"):
        wb.create_workbench_batch(conn, created_by=7, now="2026-08-13T00:00:01+00:00")
    assert conn.execute("SELECT COUNT(*) FROM sgf_workbench_batches").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM sgf_workbench_batch_items").fetchone()[0] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM sgf_workbench_staged_repairs WHERE status='STAGED'"
    ).fetchone()[0] == 2


def test_batch_idempotency_key_returns_existing_batch_without_duplicates():
    conn = _sqlite_db()
    item = _report(conn)["review_item_id"]
    _stage(conn, item)
    first = wb.create_workbench_batch(
        conn, created_by=7, idempotency_key="batch-operation-1",
        now="2026-08-13T00:00:01+00:00",
    )
    duplicate = wb.create_workbench_batch(
        conn, created_by=7, idempotency_key="batch-operation-1",
        now="2026-08-13T00:00:02+00:00",
    )
    assert duplicate["duplicate"] is True
    assert duplicate["id"] == first["id"]
    assert conn.execute("SELECT COUNT(*) FROM sgf_workbench_batches").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM sgf_workbench_batch_items").fetchone()[0] == 1


def test_schema_status_does_not_make_sqlite_tables_into_question_authority():
    conn = _sqlite_db()
    assert wb.WorkbenchRepository(conn).schema_status()["valid"] is True
    assert conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE name LIKE 'questions%'"
    ).fetchone()[0] == 0


def test_direct_version_audit_failure_restores_fixture_and_db(monkeypatch, tmp_path):
    conn = _sqlite_db()
    record = {
        "id": 900001,
        "content": "(;GM[1]FF[4]SZ[19];B[aa])",
        "accepted_moves": [{"x": 3, "y": 3}],
        "enabled": True,
    }
    proposed = dict(record)
    proposed["accepted_moves"] = [{"x": 3, "y": 3}, {"x": 15, "y": 3}]
    path = tmp_path / "questions.json"
    original_bytes = (
        "[{\"id\":900001,\"content\":\"(;GM[1]FF[4]SZ[19];B[aa])\","
        "\"accepted_moves\":[{\"x\":3,\"y\":3}],\"enabled\":true}]\n"
    ).encode("utf-8")
    path.write_bytes(original_bytes)

    def fail_audit(*_args, **_kwargs):
        raise RuntimeError("audit_sink_down")

    monkeypatch.setattr(wb, "_audit", fail_audit)
    with pytest.raises(RuntimeError, match="audit_sink_down"):
        wb.apply_direct_question_edit(
            conn,
            questions_path=str(path),
            actor_id=7,
            question_id=900001,
            record_index=0,
            expected_predecessor_hash=wb.direct_record_hash(record),
            action_type="ADD_ALTERNATIVE_CORRECT_MOVE",
            proposed_record=proposed,
            operation_id="audit-failure-operation",
        )
    assert path.read_bytes() == original_bytes
    assert conn.execute("SELECT COUNT(*) FROM sgf_workbench_direct_versions").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM sgf_workbench_audit").fetchone()[0] == 0


def _pg_connect(url):
    import psycopg2

    from db import PostgresConnectionWrapper
    from psycopg2.extras import DictCursor

    raw = psycopg2.connect(url)
    raw.cursor_factory = DictCursor
    return PostgresConnectionWrapper(raw)


def _prepare_pg(conn):
    from migrations.sgf_admin_workbench_v1 import TABLE_SPECS, upgrade, validate_schema

    conn.execute(
        "DROP TABLE IF EXISTS "
        + ", ".join(f"public.{name}" for name in reversed(tuple(TABLE_SPECS)))
        + " CASCADE"
    )
    conn.commit()
    result = upgrade(conn)
    conn.commit()
    assert len(result["created"]) == 7
    assert validate_schema(conn)["missing"] == []


def test_disposable_postgres_round_trip_and_schema_contract():
    url = os.environ.get("SGF_WORKBENCH_PERSISTENCE_DATABASE_URL")
    if not url:
        pytest.skip("requires explicitly marked disposable PostgreSQL")
    conn = _pg_connect(url)
    try:
        _prepare_pg(conn)
        report = _report(conn, external_key="pg-report")
        staged = _stage(conn, report["review_item_id"], mutation_key="pg-repair")
        batch = wb.create_workbench_batch(
            conn, created_by=7, idempotency_key="pg-batch", now="2026-08-13T00:00:01+00:00"
        )
        conn.commit()
        assert staged["status"] == "STAGED"
        assert batch["staged_count"] == 1
        assert conn.execute("SELECT version() AS v").fetchone()["v"].startswith("PostgreSQL")
        assert conn.execute("SELECT COUNT(*) AS n FROM sgf_workbench_audit").fetchone()["n"] >= 2
    finally:
        conn.rollback()
        conn.close()


def test_disposable_postgres_stale_transition_and_direct_version_atomicity(monkeypatch, tmp_path):
    url = os.environ.get("SGF_WORKBENCH_PERSISTENCE_DATABASE_URL")
    if not url:
        pytest.skip("requires explicitly marked disposable PostgreSQL")
    first = _pg_connect(url)
    second = _pg_connect(url)
    try:
        _prepare_pg(first)
        first_report = _report(first, external_key="pg-concurrency-report")
        first.commit()
        item_id = first_report["review_item_id"]
        old_updated_at = first.execute(
            "SELECT updated_at FROM sgf_workbench_review_items WHERE id=?", (item_id,)
        ).fetchone()["updated_at"]
        _stage(first, item_id, mutation_key="pg-concurrency-repair", now="2026-08-13T00:00:01+00:00")
        first.commit()
        with pytest.raises(wb.StaleWorkbenchState, match="stale_workbench_item"):
            wb.resolve_workbench_item(
                second,
                item_id=item_id,
                reviewer_id=8,
                status="NEEDS_RESEARCH",
                expected_item_updated_at=old_updated_at,
            )
        second.rollback()
        duplicate = _stage(second, item_id, mutation_key="pg-concurrency-repair")
        assert duplicate["duplicate"] is True
        second.commit()

        rollback_report = _report(first, external_key="pg-audit-rollback")
        first.commit()
        real_audit = wb._audit

        def fail_audit(*_args, **_kwargs):
            raise RuntimeError("audit_sink_down")

        monkeypatch.setattr(wb, "_audit", fail_audit)
        with pytest.raises(RuntimeError, match="audit_sink_down"):
            _stage(first, rollback_report["review_item_id"], mutation_key="pg-audit-repair")
        first.commit()
        monkeypatch.setattr(wb, "_audit", real_audit)
        assert first.execute(
            "SELECT COUNT(*) AS n FROM sgf_workbench_staged_repairs WHERE mutation_key=?",
            ("pg-audit-repair",),
        ).fetchone()["n"] == 0

        record = {
            "id": 900001,
            "content": "(;GM[1]FF[4]SZ[19];B[aa])",
            "accepted_moves": [{"x": 3, "y": 3}],
            "enabled": True,
        }
        path = tmp_path / "questions.json"
        path.write_text("[{\"id\":900001,\"content\":\"(;GM[1]FF[4]SZ[19];B[aa])\",\"accepted_moves\":[{\"x\":3,\"y\":3}],\"enabled\":true}]\n", encoding="utf-8")
        proposed = dict(record)
        proposed["accepted_moves"] = [{"x": 3, "y": 3}, {"x": 15, "y": 3}]
        version = wb.apply_direct_question_edit(
            first,
            questions_path=str(path),
            actor_id=7,
            question_id=900001,
            record_index=0,
            expected_predecessor_hash=wb.direct_record_hash(record),
            action_type="ADD_ALTERNATIVE_CORRECT_MOVE",
            proposed_record=proposed,
            operation_id="pg-direct-operation",
        )
        first.commit()
        assert version["new_hash"] == wb.direct_record_hash(proposed)
        assert first.execute(
            "SELECT COUNT(*) AS n FROM sgf_workbench_audit WHERE action='DIRECT_APPLY'"
        ).fetchone()["n"] == 1
    finally:
        first.rollback()
        second.rollback()
        first.close()
        second.close()
