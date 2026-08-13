"""Flask contract test for the real Workbench workflow endpoints."""

from __future__ import annotations

import sqlite3

import sgf_admin_workbench as wb


class _ConnectionContext:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, exc_type, _exc, _tb):
        if exc_type:
            self.connection.rollback()
        else:
            self.connection.commit()
        return False


def test_admin_report_to_ready_for_apply_route_flow(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "sgf-workflow-api-test")
    import app as application

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    wb.ensure_sgf_workbench_tables(conn)
    record = {
        "id": 431,
        "content": "(;GM[1]FF[4]SZ[19])",
        "accepted_moves": [{"x": 3, "y": 3}],
        "enabled": True,
    }
    content_sha = "a" * 64
    capture = wb.capture_workbench_report(
        conn,
        source="PLAYER_REPORT",
        reporter_id=11,
        question_id=431,
        record_index=0,
        issue_type="ALTERNATIVE_CORRECT_MOVE",
        candidate_move={"x": 15, "y": 3},
        observed_system_verdict="WRONG",
        gameplay_surface="main_practice",
        sgf_identity="sgf-431",
        node_identity="root",
        board_state={"stones": []},
        question_content_sha256=content_sha,
        external_key="api-workflow-report",
    )
    monkeypatch.setattr(application, "get_db", lambda: _ConnectionContext(conn))
    monkeypatch.setattr(application, "parse_sgf", lambda _content: True)
    monkeypatch.setattr(application, "_rt_server_verify", lambda *_args: True)
    monkeypatch.setattr(
        application,
        "_workbench_question_context",
        lambda question_id, **_kwargs: {
            "question_id": int(question_id),
            "record_index": 0,
            "record": record,
            "question_content_sha256": content_sha,
            "gameplay_surface": "admin_workbench",
            "sgf_identity": content_sha,
            "node_identity": "root",
            "board_state": {},
            "candidate_move": {"x": 15, "y": 3},
            "authority": {"accepted_moves": record["accepted_moves"]},
        },
    )

    client = application.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 7
        session["is_admin"] = True
    bootstrap = client.get("/api/admin/sgf-workbench/bootstrap")
    assert bootstrap.status_code == 200
    security = bootstrap.get_json()["security"]
    headers = {security["csrf_header"]: security["csrf_token"]}

    stage = client.post(
        f"/api/admin/sgf-workbench/items/{capture['review_item_id']}/stage",
        json={"action": "ADD_ALTERNATIVE_CORRECT_MOVE", "mutation_key": "api-workflow-repair"},
        headers=headers,
    )
    assert stage.status_code == 200
    repair_id = stage.get_json()["repair"]["id"]

    validation = client.post(
        f"/api/admin/sgf-workbench/items/{capture['review_item_id']}/validate",
        json={"repair_id": repair_id}, headers=headers,
    )
    assert validation.status_code == 200
    assert validation.get_json()["status"] == "PASS"
    assert validation.get_json()["canonical_mutation"] is False

    batch = client.post("/api/admin/sgf-workbench/batches", json={}, headers=headers)
    assert batch.status_code == 200
    batch_id = batch.get_json()["batch"]["id"]
    ready = client.post(f"/api/admin/sgf-workbench/batches/{batch_id}/ready", json={}, headers=headers)
    assert ready.status_code == 200
    payload = ready.get_json()
    assert payload["batch"]["status"] == "READY_FOR_APPLY"
    assert payload["apply_enabled"] is False
    assert payload["production_mutation"] is False
    assert record["accepted_moves"] == [{"x": 3, "y": 3}]

    ordinary = application.app.test_client()
    with ordinary.session_transaction() as session:
        session["user_id"] = 8
        session["is_admin"] = False
    assert ordinary.post(
        f"/api/admin/sgf-workbench/items/{capture['review_item_id']}/validate",
        json={"repair_id": repair_id}, headers=headers,
    ).status_code == 403
