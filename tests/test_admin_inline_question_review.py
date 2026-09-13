from __future__ import annotations

import sqlite3
from pathlib import Path

import sgf_admin_workbench as workbench


ROOT = Path(__file__).resolve().parents[1]


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


def _record():
    return {
        "id": 431,
        "source": "inline-fixture",
        "content": "(;GM[1]FF[4]SZ[19]PL[B]AB[aa]AW[ss](;B[dd]))",
        "accepted_moves": [{"x": 3, "y": 3}],
        "enabled": True,
        "solution_state": "verified",
    }


def test_surface_census_uses_one_shared_widget_and_board_seams():
    expected = {
        "index.html": "main_practice",
        "mistakes.html": "main_practice",
        "daily_challenge.html": "daily_challenge_client",
        "rating_test.html": "rating_test_server",
        "community.html": "friend_challenge_client_then_server_trust",
        "play.html": "friend_challenge_client_then_server_trust",
    }
    for filename, surface in expected.items():
        page = (ROOT / filename).read_text(encoding="utf-8")
        assert "/sgf_report_widget.js" in page
        assert f'data-sgf-report-surface="{surface}"' in page

    for filename in ("index.html", "mistakes.html", "daily_challenge.html", "rating_test.html"):
        page = (ROOT / filename).read_text(encoding="utf-8")
        assert "consumeBoardMove" in page
        assert "sgf:inline-review-marker" in page

    index = (ROOT / "index.html").read_text(encoding="utf-8")
    assert "_adminInlineReviewNextHandler" in index
    assert "_mapBattleV1IsActive()" in index
    assert "_guildQuestMode" in index


def test_inline_widget_reuses_review_and_staging_authorities():
    widget = (ROOT / "sgf_report_widget.js").read_text(encoding="utf-8")
    assert all(label in widget for label in ("✓ 沒問題", "✎ 改答案", "✎ 改題目", "＋ 補正解", "⏭ 稍後"))
    assert "/api/admin/sgf-answer-review/v2a/reviews" in widget
    assert "/api/admin/sgf-workbench/direct-context/" in widget
    assert "/api/admin/sgf-workbench/flag" in widget
    assert "/stage" in widget and "/validate" in widget
    assert "canonical_questions_mutated !== false" in widget
    assert "direct-apply" in widget  # existing gated shortcut remains separate from inline save
    assert "QUESTION_IDENTITY_MIGRATION=NO" in (
        ROOT / "docs/planning/ADMIN_INLINE_QUESTION_REVIEW_SURFACE_REGISTRY.md"
    ).read_text(encoding="utf-8")


def test_inline_question_edit_stages_through_existing_workbench_and_validates(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "admin-inline-review-test")
    import app as application

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    workbench.ensure_sgf_workbench_tables(conn)
    record = _record()
    content_sha = application._question_content_sha256(record)
    capture = workbench.capture_workbench_report(
        conn,
        source="ADMIN_PLAY",
        reporter_id=7,
        question_id=431,
        record_index=0,
        issue_type="QUESTION_CONTENT_PROBLEM",
        candidate_move=None,
        observed_system_verdict=None,
        gameplay_surface="main_practice",
        sgf_identity=content_sha,
        node_identity=None,
        board_state=None,
        question_content_sha256=content_sha,
        comment="INLINE_ADMIN_REVIEW",
        external_key="inline-question-edit-fixture",
    )

    monkeypatch.setattr(application, "get_db", lambda: _ConnectionContext(conn))
    monkeypatch.setattr(application, "parse_sgf", lambda _content: True)
    monkeypatch.setattr(application, "_load_questions", lambda: [record])
    monkeypatch.setattr(
        application,
        "_workbench_question_context",
        lambda question_id, **_kwargs: {
            "question_id": int(question_id),
            "record_index": 0,
            "record": record,
            "question_content_sha256": content_sha,
            "gameplay_surface": "main_practice",
            "sgf_identity": content_sha,
            "node_identity": None,
            "board_state": None,
            "candidate_move": None,
            "authority": {"accepted_moves": record["accepted_moves"]},
        },
    )

    client = application.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 7
        session["is_admin"] = True

    security = client.get("/api/admin/sgf-workbench/bootstrap").get_json()["security"]
    headers = {security["csrf_header"]: security["csrf_token"]}
    stage = client.post(
        f"/api/admin/sgf-workbench/items/{capture['review_item_id']}/stage",
        json={
            "action": "CHANGE_SIDE_TO_PLAY",
            "side_to_play": "W",
            "baseline_sha256": content_sha,
            "mutation_key": "inline-question-edit-repair",
        },
        headers=headers,
    )
    assert stage.status_code == 200
    repair = stage.get_json()["repair"]
    assert "PL[W]" in repair["proposed_state"]["content"]

    validation = client.post(
        f"/api/admin/sgf-workbench/items/{capture['review_item_id']}/validate",
        json={"repair_id": repair["id"]},
        headers=headers,
    )
    payload = validation.get_json()
    assert validation.status_code == 200
    assert payload["status"] == "PASS"
    assert payload["canonical_mutation"] is False
    assert "PL[B]" in record["content"]


def test_inline_question_edit_rejects_invalid_side_at_existing_adapter(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "admin-inline-review-invalid-side")
    import app as application

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    workbench.ensure_sgf_workbench_tables(conn)
    record = _record()
    content_sha = application._question_content_sha256(record)
    capture = workbench.capture_workbench_report(
        conn,
        source="ADMIN_PLAY",
        reporter_id=7,
        question_id=431,
        record_index=0,
        issue_type="QUESTION_CONTENT_PROBLEM",
        candidate_move=None,
        observed_system_verdict=None,
        gameplay_surface="main_practice",
        sgf_identity=content_sha,
        node_identity=None,
        board_state=None,
        question_content_sha256=content_sha,
        comment="INLINE_ADMIN_REVIEW",
        external_key="inline-question-edit-invalid-side",
    )
    monkeypatch.setattr(application, "get_db", lambda: _ConnectionContext(conn))
    monkeypatch.setattr(
        application,
        "_workbench_question_context",
        lambda question_id, **_kwargs: {
            "question_id": int(question_id),
            "record_index": 0,
            "record": record,
            "question_content_sha256": content_sha,
            "gameplay_surface": "main_practice",
            "sgf_identity": content_sha,
            "node_identity": None,
            "board_state": None,
            "candidate_move": None,
            "authority": {"accepted_moves": record["accepted_moves"]},
        },
    )
    client = application.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 7
        session["is_admin"] = True
    security = client.get("/api/admin/sgf-workbench/bootstrap").get_json()["security"]
    response = client.post(
        f"/api/admin/sgf-workbench/items/{capture['review_item_id']}/stage",
        json={"action": "CHANGE_SIDE_TO_PLAY", "side_to_play": "X"},
        headers={security["csrf_header"]: security["csrf_token"]},
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_side_to_play"
