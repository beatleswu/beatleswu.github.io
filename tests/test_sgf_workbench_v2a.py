from __future__ import annotations

import sqlite3
import time

import sgf_admin_workbench as workbench
from sgf_workbench_v2a import (
    build_question_context,
    compute_local_viewport,
    ensure_human_review_table,
    go_coordinate,
    get_human_review_state,
    load_human_review_index,
    record_hash,
    replay_sgf_tree,
    save_human_review_state,
    serialize_sgf_tree,
)


def _conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    workbench.ensure_sgf_workbench_tables(conn)
    ensure_human_review_table(conn)
    return conn


def _record():
    return {
        "id": 431,
        "source": "fixture",
        "content": "(;GM[1]FF[4]SZ[19]AB[aa]AW[ss]PL[B](;B[bb](;W[cc])(;W[dd]))(;B[ee]))",
        "enabled": True,
        "tags": ["life"],
    }


def test_record_hash_is_full_record_and_key_order_independent():
    record = _record()
    reordered = {"tags": record["tags"], "enabled": True, "content": record["content"], "source": "fixture", "id": 431}
    assert record_hash(record) == record_hash(reordered)
    changed = dict(record, source="other")
    assert record_hash(changed) != record_hash(record)


def test_tree_adapter_preserves_paths_order_and_replays_selected_node():
    tree = serialize_sgf_tree(_record()["content"])
    assert tree["root_id"] == "0"
    assert tree["nodes"][0]["children"] == ["0.0", "0.1"]
    assert tree["nodes"][1]["children"] == ["0.0.0", "0.0.1"]
    replay = replay_sgf_tree(tree, "0.0.0")
    assert replay["status"] == "PASS"
    assert replay["path"] == ["0", "0.0", "0.0.0"]
    assert { (stone["x"], stone["y"], stone["color"]) for stone in replay["stones"] } >= {
        (0, 0, "B"), (18, 18, "W"), (1, 1, "B"), (2, 2, "W")
    }


def test_capture_replay_states_are_backend_authoritative_for_tree_playback():
    tree = serialize_sgf_tree("(;GM[1]FF[4]SZ[5]AB[aa][ca]AW[ba];B[bb])")
    root = {(stone["x"], stone["y"], stone["color"]) for stone in replay_sgf_tree(tree, "0")["stones"]}
    captured = {(stone["x"], stone["y"], stone["color"]) for stone in replay_sgf_tree(tree, "0.0")["stones"]}
    assert (1, 0, "W") in root
    assert (1, 0, "W") not in captured
    assert tree["board_states"]["0.0"] == replay_sgf_tree(tree, "0.0")["stones"]


def test_capture_variations_and_predecessor_restore_are_deterministic():
    multi = serialize_sgf_tree("(;GM[1]FF[4]SZ[5]AB[aa][ca][ab][cb]AW[ba][bb];B[bc])")
    captured = {(stone["x"], stone["y"], stone["color"]) for stone in replay_sgf_tree(multi, "0.0")["stones"]}
    assert (1, 0, "W") not in captured and (1, 1, "W") not in captured
    sibling = serialize_sgf_tree("(;GM[1]FF[4]SZ[5]AB[aa]AW[bb](;B[cc])(;B[dd]))")
    first = {(stone["x"], stone["y"], stone["color"]) for stone in replay_sgf_tree(sibling, "0.0")["stones"]}
    second = {(stone["x"], stone["y"], stone["color"]) for stone in replay_sgf_tree(sibling, "0.1")["stones"]}
    root = {(stone["x"], stone["y"], stone["color"]) for stone in replay_sgf_tree(sibling, "0")["stones"]}
    assert (2, 2, "B") in first and (3, 3, "B") in second
    assert first != second and root == {(0, 0, "B"), (1, 1, "W")}


def test_go_coordinate_formatter_uses_real_go_columns_and_orientation():
    assert go_coordinate(7, 0) == "H19"
    assert go_coordinate(8, 0) == "J19"
    assert go_coordinate(0, 18) == "A1"


def test_viewport_includes_tree_moves_and_corner_edges():
    tree = serialize_sgf_tree("(;GM[1]FF[4]SZ[19]AB[aa](;B[cc])(;B[ss]))")
    viewport = compute_local_viewport(tree, {})
    assert viewport["touch_left"] and viewport["touch_top"]
    assert viewport["touch_right"] and viewport["touch_bottom"]


def test_version_scoped_review_locator_and_content_changed():
    conn = _conn()
    record = _record()
    first_hash = record_hash(record)
    saved = save_human_review_state(
        conn, reviewer_id=7, record_index=812, legacy_question_id=431,
        reviewed_record_sha256=first_hash, classification="CORRECT", now="2026-01-01T00:00:00+00:00",
    )
    assert saved["state"] == "CURRENT"
    current = get_human_review_state(conn, reviewer_id=7, record_index=812,
                                     legacy_question_id=431, current_record_sha256=first_hash)
    assert current["state"] == "CURRENT" and current["classification"] == "CORRECT"
    changed = get_human_review_state(conn, reviewer_id=7, record_index=812,
                                     legacy_question_id=431, current_record_sha256="b" * 64)
    assert changed["state"] == "CONTENT_CHANGED"
    assert changed["classification"] is None


def test_duplicate_legacy_ids_do_not_rebind():
    conn = _conn()
    a, b = "a" * 64, "b" * 64
    save_human_review_state(conn, reviewer_id=7, record_index=10, legacy_question_id=9,
                            reviewed_record_sha256=a, classification="UNSURE")
    save_human_review_state(conn, reviewer_id=7, record_index=20, legacy_question_id=9,
                            reviewed_record_sha256=b, classification="SPECIAL")
    assert get_human_review_state(conn, reviewer_id=7, record_index=10, legacy_question_id=9,
                                  current_record_sha256=a)["classification"] == "UNSURE"
    assert get_human_review_state(conn, reviewer_id=7, record_index=20, legacy_question_id=9,
                                  current_record_sha256=b)["classification"] == "SPECIAL"
    assert get_human_review_state(conn, reviewer_id=7, record_index=30, legacy_question_id=9,
                                  current_record_sha256=a)["state"] == "UNREVIEWED"


def test_human_review_migration_is_additive_and_rerunnable():
    from migrations.sgf_human_review_v2a import TABLE_NAME, upgrade, validate_schema

    conn = sqlite3.connect(":memory:")
    first = upgrade(conn)
    second = upgrade(conn)
    assert first["table"] == TABLE_NAME
    assert second["missing"] == []
    assert validate_schema(conn)["columns"]
    assert "record_sha256" in validate_schema(conn)["progress_columns"]


def test_context_has_no_repair_or_canonical_mutation_fields():
    context = build_question_context(_record(), record_index=0, reviewer_id=7)
    assert context["review_state"] == "UNREVIEWED"
    assert "direct_apply" not in context
    assert context["reviewed_record_sha256"] == record_hash(_record())


def test_v2a_admin_api_classifies_without_canonical_mutation(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "sgf-v2a-test")
    import app as application

    conn = _conn()
    records = [_record(), dict(_record(), id=432, content="(;GM[1]FF[4]SZ[19];B[cc])")]
    monkeypatch.setattr(application, "get_db", lambda: _ConnectionContext(conn))
    monkeypatch.setattr(application, "_load_questions", lambda: records)
    client = application.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 7
        session["is_admin"] = True
    bootstrap = client.get("/api/admin/sgf-workbench-v2a/bootstrap")
    assert bootstrap.status_code == 200
    payload = bootstrap.get_json()
    assert payload["current"]["record_index"] == 0
    headers = {payload["security"]["csrf_header"]: payload["security"]["csrf_token"]}
    current = payload["current"]
    response = client.post("/api/admin/sgf-workbench-v2a/reviews", json={
        "record_index": current["record_index"],
        "legacy_question_id": current["legacy_question_id"],
        "reviewed_record_sha256": current["reviewed_record_sha256"],
        "classification": "CORRECT",
    }, headers=headers)
    assert response.status_code == 200
    assert response.get_json()["review"]["classification"] == "CORRECT"
    assert records[0]["content"].startswith("(;GM")


def test_v2a_resume_locator_drift_fails_closed(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "sgf-v2a-resume-test")
    import app as application

    conn = _conn()
    first = _record()
    second = dict(_record(), id=432, content="(;GM[1]FF[4]SZ[19];B[cc])")
    records = [first, second]
    monkeypatch.setattr(application, "get_db", lambda: _ConnectionContext(conn))
    monkeypatch.setattr(application, "_load_questions", lambda: records)
    client = application.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 7
        session["is_admin"] = True
    bootstrap = client.get("/api/admin/sgf-workbench-v2a/bootstrap")
    headers = {bootstrap.get_json()["security"]["csrf_header"]: bootstrap.get_json()["security"]["csrf_token"]}
    progress = client.post("/api/admin/sgf-workbench-v2a/progress", json={"record_index": 0}, headers=headers)
    assert progress.status_code == 200
    records[:] = [second, first]
    reopened = client.get("/api/admin/sgf-workbench-v2a/bootstrap")
    payload = reopened.get_json()
    assert payload["resume_state"] == "RESUME_LOCATOR_STALE"
    assert payload["current"]["record_index"] == 1


def test_v2a_progress_does_not_mutate_legacy_progress_semantics(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "sgf-v2a-progress-test")
    from sgf_answer_review_queue import ensure_review_queue_tables
    import app as application

    conn = _conn()
    ensure_review_queue_tables(conn)
    conn.execute("INSERT INTO sgf_answer_review_progress(owner_user_id,snapshot_sha256,current_content_sha256,revision,updated_at) VALUES(?,?,?,?,?)",
                 (7, "legacy-snapshot", "legacy-content-sha", 4, "legacy-time"))
    records = [_record(), dict(_record(), id=432, content="(;GM[1]FF[4]SZ[19];B[cc])")]
    monkeypatch.setattr(application, "get_db", lambda: _ConnectionContext(conn))
    monkeypatch.setattr(application, "_load_questions", lambda: records)
    client = application.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 7
        session["is_admin"] = True
    bootstrap = client.get("/api/admin/sgf-workbench-v2a/bootstrap")
    security = bootstrap.get_json()["security"]
    headers = {security["csrf_header"]: security["csrf_token"]}
    response = client.post("/api/admin/sgf-workbench-v2a/progress", json={"record_index": 0}, headers=headers)
    assert response.status_code == 200
    legacy = conn.execute("SELECT current_content_sha256,revision,updated_at FROM sgf_answer_review_progress WHERE owner_user_id=? AND snapshot_sha256=?",
                          (7, "legacy-snapshot")).fetchone()
    assert tuple(legacy) == ("legacy-content-sha", 4, "legacy-time")
    v2a = conn.execute("SELECT record_index,legacy_question_id,record_sha256 FROM sgf_human_review_progress WHERE reviewer_id=?",
                       (7,)).fetchone()
    assert tuple(v2a) == (0, "431", record_hash(records[0]))


def test_v2a_bulk_bootstrap_has_bounded_database_queries_for_40k_records(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "sgf-v2a-40k-test")
    import app as application

    conn = _conn()
    records = [dict(_record(), id=index) for index in range(40000)]
    monkeypatch.setattr(application, "get_db", lambda: _ConnectionContext(conn))
    monkeypatch.setattr(application, "_load_questions", lambda: records)
    client = application.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 7
        session["is_admin"] = True
    queries = []
    conn.set_trace_callback(queries.append)
    started = time.perf_counter()
    response = client.get("/api/admin/sgf-workbench-v2a/bootstrap?limit=200")
    elapsed = time.perf_counter() - started
    conn.set_trace_callback(None)
    assert response.status_code == 200
    assert response.get_json()["total"] == 40000
    selects = [query for query in queries if query.lstrip().upper().startswith("SELECT")]
    assert len(selects) <= 4
    assert sum("FROM SGF_HUMAN_REVIEW_STATE" in query.upper() for query in selects) <= 1
    assert elapsed < 10


def test_v2a_reports_full_total_and_position_beyond_200(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "sgf-v2a-position-test")
    import app as application
    conn = _conn()
    records = [dict(_record(), id=index) for index in range(250)]
    monkeypatch.setattr(application, "get_db", lambda: _ConnectionContext(conn))
    monkeypatch.setattr(application, "_load_questions", lambda: records)
    client = application.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 7
        session["is_admin"] = True
    first = client.get("/api/admin/sgf-workbench-v2a/bootstrap?limit=200").get_json()
    assert len(first["items"]) == 200 and first["total"] == 250 and first["current_position"] == 1
    later = client.get("/api/admin/sgf-workbench-v2a/questions/220").get_json()
    assert later["current_position"] == 221 and later["total"] == 250


def test_v2a_mutation_guards_and_legacy_secondary_entry(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "sgf-v2a-security-test")
    import app as application
    conn = _conn()
    records = [_record()]
    monkeypatch.setattr(application, "get_db", lambda: _ConnectionContext(conn))
    monkeypatch.setattr(application, "_load_questions", lambda: records)
    client = application.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 7
        session["is_admin"] = True
    bootstrap = client.get("/api/admin/sgf-workbench-v2a/bootstrap").get_json()
    headers = {bootstrap["security"]["csrf_header"]: bootstrap["security"]["csrf_token"]}
    body = {"record_index": 0, "legacy_question_id": 431,
            "reviewed_record_sha256": record_hash(records[0]), "classification": "CORRECT"}
    assert client.post("/api/admin/sgf-workbench-v2a/reviews", json=body,
                       headers={**headers, "Origin": "https://evil.example"}).status_code == 403
    assert client.post("/api/admin/sgf-workbench-v2a/reviews", data="{}",
                       headers=headers, content_type="text/plain").status_code == 415
    assert client.post("/api/admin/sgf-workbench-v2a/reviews", json=body,
                       headers={"X-SGF-Answer-Review-CSRF": "wrong"}).status_code == 403
    default_page = client.get("/admin/sgf-answer-review")
    legacy_page = client.get("/admin/sgf-answer-review?mode=legacy")
    assert "/admin/sgf-answer-review-ux-v2.js" in default_page.get_data(as_text=True)
    assert "/admin/sgf-answer-review.js" in legacy_page.get_data(as_text=True)
    assert "/admin/sgf-answer-review-legacy-ux-v2.js" in legacy_page.get_data(as_text=True)


class _ConnectionContext:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, exc_type, _value, _traceback):
        if exc_type:
            self.connection.rollback()
        else:
            self.connection.commit()
        return False
