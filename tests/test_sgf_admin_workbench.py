import hashlib
import json
import sqlite3

import pytest

from sgf_admin_workbench import (
    capture_workbench_report,
    create_workbench_batch,
    ensure_sgf_workbench_tables,
    get_workbench_item,
    list_workbench_items,
    resolve_workbench_item,
    stage_workbench_repair,
)


def _db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_sgf_workbench_tables(conn)
    return conn


def _capture(conn, *, source="PLAYER_REPORT", move=None, node="n1", board=None, key=None):
    return capture_workbench_report(
        conn,
        source=source,
        reporter_id=7,
        question_id=431,
        record_index=12,
        issue_type="ALTERNATIVE_CORRECT_MOVE",
        candidate_move=move or {"x": 15, "y": 3},
        observed_system_verdict="WRONG",
        gameplay_surface="main_practice",
        sgf_identity="sgf-431",
        node_identity=node,
        board_state=board or {"stones": []},
        question_content_sha256="a" * 64,
        comment="evidence",
        source_provenance={"source": source, "immutable": True},
        external_key=key or f"{source}:{node}:{move or {'x': 15, 'y': 3}}",
        now="2026-08-12T00:00:00+00:00",
    )


def test_same_semantic_position_aggregates_and_preserves_individual_reports():
    conn = _db()
    first = _capture(conn, key="player:1")
    second = _capture(conn, key="player:2")
    items = list_workbench_items(conn)
    assert first["review_item_id"] == second["review_item_id"]
    assert items[0]["report_count"] == 2
    detail = get_workbench_item(conn, first["review_item_id"])
    assert len(detail["reports"]) == 2
    assert detail["source_types"] == ["PLAYER_REPORT"]


def test_different_moves_and_positions_are_not_collapsed():
    conn = _db()
    a = _capture(conn, move={"x": 15, "y": 3}, key="a")
    b = _capture(conn, move={"x": 14, "y": 3}, key="b")
    c = _capture(conn, move={"x": 15, "y": 3}, node="n2", key="c")
    assert len(list_workbench_items(conn)) == 3
    assert len({a["group_key"], b["group_key"], c["group_key"]}) == 3


def test_admin_and_future_scan_sources_share_the_same_queue_contract():
    conn = _db()
    admin = _capture(conn, source="ADMIN_PLAY", key="admin")
    scan = _capture(conn, source="CORPUS_SCAN", key="scan")
    assert set(list_workbench_items(conn)[0]["source_types"]) == {"ADMIN_PLAY", "CORPUS_SCAN"}
    assert admin["review_item_id"] == scan["review_item_id"]


def test_staging_is_server_persisted_and_does_not_mutate_canonical_state():
    conn = _db()
    capture = _capture(conn, key="stage")
    original = {"accepted_moves": [{"x": 3, "y": 3}], "enabled": True}
    proposed = {"accepted_moves": [{"x": 3, "y": 3}, {"x": 15, "y": 3}], "enabled": True}
    repair = stage_workbench_repair(
        conn,
        item_id=capture["review_item_id"],
        reviewer_id=99,
        action="ADD_ALTERNATIVE_CORRECT_MOVE",
        original_state=original,
        proposed_state=proposed,
        candidate_move={"x": 15, "y": 3},
        reason="verified during admin retest",
        source_provenance={"review_item_id": capture["review_item_id"]},
        baseline_sha256="b" * 64,
        mutation_key="repair-1",
    )
    assert repair["status"] == "STAGED"
    item = get_workbench_item(conn, capture["review_item_id"])
    assert item["status"] == "STAGED"
    assert item["staged_repairs"][0]["original_state"] == original
    assert item["staged_repairs"][0]["proposed_state"] == proposed
    # The persistence layer has no canonical corpus handle and must not create one.
    assert not any("questions" in row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'"))


def test_rejection_and_research_preserve_evidence():
    conn = _db()
    capture = _capture(conn, key="resolution")
    assert resolve_workbench_item(conn, item_id=capture["review_item_id"], reviewer_id=5, status="NEEDS_RESEARCH")["status"] == "NEEDS_RESEARCH"
    detail = get_workbench_item(conn, capture["review_item_id"])
    assert len(detail["reports"]) == 1
    with pytest.raises(ValueError):
        resolve_workbench_item(conn, item_id=capture["review_item_id"], reviewer_id=5, status="PUBLISHED")


def test_deterministic_batch_handoff_is_hash_addressed_and_non_mutating():
    conn = _db()
    for idx, move in enumerate(({"x": 15, "y": 3}, {"x": 14, "y": 3}), 1):
        captured = _capture(conn, move=move, node=f"n{idx}", key=f"batch-{idx}")
        stage_workbench_repair(
            conn, item_id=captured["review_item_id"], reviewer_id=1,
            action="ADD_ALTERNATIVE_CORRECT_MOVE", original_state={"accepted_moves": []},
            proposed_state={"accepted_moves": [move]}, candidate_move=move,
            baseline_sha256="c" * 64, mutation_key=f"batch-repair-{idx}",
            now="2026-08-12T00:00:00+00:00",
        )
    batch = create_workbench_batch(conn, created_by=1, baseline_sha256="c" * 64, now="2026-08-12T00:00:00+00:00")
    assert batch["staged_count"] == 2
    assert batch["manifest"]["handoff"]["production_mutation"] is False
    assert batch["manifest"]["handoff"]["repair_batch_tool"].endswith("sgf_answer_repair_batch.py")
    assert len(batch["manifest_sha256"]) == 64
    assert conn.execute("SELECT COUNT(*) FROM sgf_workbench_staged_repairs WHERE status='BATCHED'").fetchone()[0] == 2
