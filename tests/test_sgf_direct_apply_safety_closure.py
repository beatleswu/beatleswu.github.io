import json
import os
import sqlite3
import threading
import time

import pytest

import sgf_admin_workbench as wb


def _db(path=":memory:"):
    conn = sqlite3.connect(path, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    wb.ensure_sgf_workbench_tables(conn)
    conn.commit()
    return conn


def _record(question_id=900001, *, fallback=""):
    row = {
        "id": question_id,
        "content": "(;GM[1]FF[4]SZ[19];B[aa])",
        "accepted_moves": [{"x": 3, "y": 3}],
        "enabled": True,
        "solution_state": "open",
    }
    if fallback:
        row["katago_best_move"] = fallback
    return row


def _write(path, records, raw=None):
    if raw is None:
        raw = json.dumps(records, ensure_ascii=False, indent=2).encode("utf-8") + b"\r\n"
    path.write_bytes(raw)


def _proposed(record):
    value = json.loads(json.dumps(record))
    value["accepted_moves"].append({"x": 15, "y": 3})
    return value


def _apply(conn, path, record, proposed, operation, retest):
    return wb.apply_direct_question_edit(
        conn,
        questions_path=str(path),
        actor_id=7,
        question_id=record["id"],
        record_index=0,
        expected_predecessor_hash=wb.direct_record_hash(record),
        expected_canonical_sha256=wb.canonical_file_sha256(str(path)),
        action_type="ADD_ALTERNATIVE_CORRECT_MOVE",
        proposed_record=proposed,
        operation_id=operation,
        retest_fn=retest,
    )


def test_exact_byte_snapshot_and_rollback_sha_match(tmp_path):
    record = _record()
    path = tmp_path / "questions.json"
    original = b'[{"id":900001,"content":"(;GM[1]FF[4]SZ[19];B[aa])","accepted_moves":[{"x":3,"y":3}],"enabled":true,"solution_state":"open"}]\r\n'
    _write(path, [record], raw=original)
    conn = _db()
    version = _apply(conn, path, record, _proposed(record), "exact-apply", lambda current: {"ok": True})
    conn.commit()
    assert version["validation_result"]["retest"]["ok"] is True
    assert version["canonical_snapshot_sha256"] == wb._sha256(original)
    assert wb.canonical_file_sha256(str(path)) != wb._sha256(original)

    restored = wb.rollback_direct_question_edit(
        conn, questions_path=str(path), actor_id=7, version_id=version["id"],
        operation_id="exact-rollback",
    )
    conn.commit()
    assert restored["action_type"] == "ROLLBACK"
    assert path.read_bytes() == original
    assert wb.canonical_file_sha256(str(path)) == wb._sha256(original)


def test_failed_retest_restores_exact_bytes_and_writes_no_applied_version(tmp_path):
    record = _record()
    path = tmp_path / "questions.json"
    original = b" [\n {\"id\":900001,\"content\":\"(;GM[1]FF[4]SZ[19];B[aa])\",\"accepted_moves\":[{\"x\":3,\"y\":3}],\"enabled\":true,\"solution_state\":\"open\"}\n]\r\n"
    _write(path, [record], raw=original)
    conn = _db()
    with pytest.raises(wb.DirectApplyRetestFailed):
        _apply(conn, path, record, _proposed(record), "failed-retest", lambda current: {"ok": False})
    assert path.read_bytes() == original
    assert conn.execute("SELECT COUNT(*) FROM sgf_workbench_direct_versions").fetchone()[0] == 0


@pytest.mark.parametrize("question_id", [15436, 15388, 65095])
def test_known_fallback_conflicts_are_denied(tmp_path, question_id):
    record = _record(question_id, fallback="Q4")
    path = tmp_path / "questions.json"
    _write(path, [record])
    conn = _db()
    with pytest.raises(wb.DirectApplyPolicyError, match="historical_fallback_conflict"):
        _apply(conn, path, record, _proposed(record), f"fallback-{question_id}", lambda current: True)
    assert conn.execute("SELECT COUNT(*) FROM sgf_workbench_direct_versions").fetchone()[0] == 0


def test_known_fallback_conflict_id_fails_closed_without_marker(tmp_path):
    record = _record(65095)
    path = tmp_path / "questions.json"
    _write(path, [record])
    conn = _db()
    with pytest.raises(wb.DirectApplyPolicyError, match="historical_fallback_conflict"):
        _apply(conn, path, record, _proposed(record), "fallback-unresolved", lambda current: True)
    assert conn.execute("SELECT COUNT(*) FROM sgf_workbench_direct_versions").fetchone()[0] == 0


def test_gf003_fixture_is_denied_at_service_boundary(tmp_path):
    record = _record(431, fallback="T14")
    record["source"] = "fixture431"
    path = tmp_path / "questions.json"
    _write(path, [record])
    conn = _db()
    before = path.read_bytes()
    with pytest.raises(wb.DirectApplyPolicyError, match="gf003_direct_apply_denied"):
        _apply(conn, path, record, _proposed(record), "gf003", lambda current: True)
    assert path.read_bytes() == before


def test_stale_canonical_basis_is_rejected(tmp_path):
    record = _record()
    path = tmp_path / "questions.json"
    _write(path, [record])
    conn = _db()
    with pytest.raises(ValueError, match="stale_canonical_basis"):
        wb.apply_direct_question_edit(
            conn, questions_path=str(path), actor_id=7, question_id=record["id"],
            record_index=0, expected_predecessor_hash=wb.direct_record_hash(record),
            expected_canonical_sha256="0" * 64, action_type="ADD_ALTERNATIVE_CORRECT_MOVE",
            proposed_record=_proposed(record), operation_id="stale-source",
            retest_fn=lambda current: True,
        )


def test_distinct_operation_cannot_overwrite_current_basis(tmp_path):
    record = _record()
    path = tmp_path / "questions.json"
    _write(path, [record])
    conn = _db()
    old_hash = wb.direct_record_hash(record)
    old_source = wb.canonical_file_sha256(str(path))
    first = wb.apply_direct_question_edit(
        conn, questions_path=str(path), actor_id=7, question_id=record["id"], record_index=0,
        expected_predecessor_hash=old_hash, expected_canonical_sha256=old_source,
        action_type="ADD_ALTERNATIVE_CORRECT_MOVE", proposed_record=_proposed(record),
        operation_id="op-a", retest_fn=lambda current: True,
    )
    conn.commit()
    assert first.get("duplicate") is not True
    second = json.loads(json.dumps(record))
    second["accepted_moves"].append({"x": 14, "y": 3})
    with pytest.raises(ValueError, match="stale_canonical_basis|stale_predecessor"):
        wb.apply_direct_question_edit(
            conn, questions_path=str(path), actor_id=8, question_id=record["id"], record_index=0,
            expected_predecessor_hash=old_hash, expected_canonical_sha256=old_source,
            action_type="ADD_ALTERNATIVE_CORRECT_MOVE", proposed_record=second,
            operation_id="op-b", retest_fn=lambda current: True,
        )


def test_concurrent_distinct_operations_have_one_winner(tmp_path):
    record = _record()
    path = tmp_path / "questions.json"
    _write(path, [record])
    db_path = tmp_path / "workbench.sqlite"
    connections = []
    for _ in range(2):
        connection = sqlite3.connect(str(db_path), check_same_thread=False, timeout=10)
        connection.row_factory = sqlite3.Row
        wb.ensure_sgf_workbench_tables(connection)
        connection.commit()
        connections.append(connection)

    basis = wb.canonical_file_sha256(str(path))
    predecessor = wb.direct_record_hash(record)
    proposals = []
    for x in (14, 15):
        proposal = _proposed(record)
        proposal["accepted_moves"][-1]["x"] = x
        proposals.append(proposal)
    results = []

    def run(index):
        try:
            results.append((index, "ok", wb.apply_direct_question_edit(
                connections[index], questions_path=str(path), actor_id=index + 1,
                question_id=record["id"], record_index=0,
                expected_predecessor_hash=predecessor,
                expected_canonical_sha256=basis,
                action_type="ADD_ALTERNATIVE_CORRECT_MOVE", proposed_record=proposals[index],
                operation_id=f"concurrent-{index}", retest_fn=lambda current: True,
            )))
        except Exception as error:  # the loser must fail closed, not overwrite
            results.append((index, "error", str(error)))

    threads = [threading.Thread(target=run, args=(index,)) for index in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert len(results) == 2
    assert sum(kind == "ok" for _, kind, _ in results) == 1
    assert sum(kind == "error" and "stale_canonical_basis" in value for _, kind, value in results) == 1
    winning_record = json.loads(path.read_text(encoding="utf-8"))[0]
    assert winning_record["accepted_moves"][-1]["x"] in {14, 15}
    for connection in connections:
        connection.close()


def test_same_operation_remains_idempotent_after_retest(tmp_path):
    record = _record()
    path = tmp_path / "questions.json"
    _write(path, [record])
    conn = _db()
    proposed = _proposed(record)
    first = _apply(conn, path, record, proposed, "same-op", lambda current: True)
    conn.commit()
    duplicate = wb.apply_direct_question_edit(
        conn, questions_path=str(path), actor_id=7, question_id=record["id"], record_index=0,
        expected_predecessor_hash=wb.direct_record_hash(record),
        expected_canonical_sha256=wb._sha256(b"stale"), action_type="ADD_ALTERNATIVE_CORRECT_MOVE",
        proposed_record=proposed, operation_id="same-op", retest_fn=lambda current: False,
    )
    assert duplicate["duplicate"] is True
    assert duplicate["id"] == first["id"]


def test_production_gate_requires_explicit_two_key_owner_gate(monkeypatch):
    monkeypatch.delenv("GO_ODYSSEY_ACCEPTANCE_MODE", raising=False)
    monkeypatch.setenv("GO_ODYSSEY_ADMIN_DIRECT_APPLY_ENABLED", "1")
    monkeypatch.delenv("GO_ODYSSEY_ADMIN_DIRECT_APPLY_PRODUCTION_ENABLE", raising=False)
    monkeypatch.delenv("GO_ODYSSEY_ADMIN_DIRECT_APPLY_OWNER_GATE", raising=False)
    import app as application

    assert application._direct_apply_enabled() is False
    monkeypatch.setenv("GO_ODYSSEY_ADMIN_DIRECT_APPLY_PRODUCTION_ENABLE", "1")
    assert application._direct_apply_enabled() is False
    monkeypatch.setenv("GO_ODYSSEY_ADMIN_DIRECT_APPLY_OWNER_GATE", "GO_ENABLE_DIRECT_APPLY")
    assert application._direct_apply_enabled() is True


def _pg_connection(url):
    import psycopg2

    from db import PostgresConnectionWrapper
    from psycopg2.extras import DictCursor

    raw = psycopg2.connect(url)
    raw.cursor_factory = DictCursor
    return PostgresConnectionWrapper(raw)


def test_disposable_postgres_safety_closure(monkeypatch, tmp_path):
    """Exercise the mutation/rollback boundary against PostgreSQL 16, not SQLite."""
    url = os.environ.get("SGF_WORKBENCH_PERSISTENCE_DATABASE_URL")
    if not url:
        pytest.skip("requires explicitly marked disposable PostgreSQL")
    from migrations.sgf_admin_workbench_v1 import TABLE_SPECS, upgrade

    conn = _pg_connection(url)
    try:
        conn.execute(
            "DROP TABLE IF EXISTS "
            + ", ".join(f"public.{name}" for name in reversed(tuple(TABLE_SPECS)))
            + " CASCADE"
        )
        conn.commit()
        upgrade(conn)
        conn.commit()

        record = _record()
        path = tmp_path / "questions.json"
        original = b'[{"id":900001,"content":"(;GM[1]FF[4]SZ[19];B[aa])","accepted_moves":[{"x":3,"y":3}],"enabled":true,"solution_state":"open"}]\r\n'
        _write(path, [record], raw=original)
        proposed = _proposed(record)
        version = _apply(conn, path, record, proposed, "pg-valid", lambda current: {"ok": True})
        conn.commit()
        assert version["validation_result"]["retest"]["ok"] is True
        assert wb.canonical_file_sha256(str(path)) != wb._sha256(original)

        wb.rollback_direct_question_edit(
            conn, questions_path=str(path), actor_id=7, version_id=version["id"],
            operation_id="pg-rollback",
        )
        conn.commit()
        assert path.read_bytes() == original
        assert wb.canonical_file_sha256(str(path)) == wb._sha256(original)

        _write(path, [record], raw=original)
        with pytest.raises(wb.DirectApplyRetestFailed):
            _apply(conn, path, record, proposed, "pg-failed-retest", lambda current: {"ok": False})
        assert path.read_bytes() == original
        conn.rollback()

        for question_id, source, message in (
            (431, "fixture431", "gf003_direct_apply_denied"),
            (15436, "", "historical_fallback_conflict"),
        ):
            locked = _record(question_id, fallback="T14" if question_id == 431 else "Q4")
            if source:
                locked["source"] = source
            _write(path, [locked])
            with pytest.raises(wb.DirectApplyPolicyError, match=message):
                _apply(conn, path, locked, _proposed(locked), f"pg-policy-{question_id}", lambda current: True)
            conn.rollback()
    finally:
        conn.rollback()
        conn.close()
