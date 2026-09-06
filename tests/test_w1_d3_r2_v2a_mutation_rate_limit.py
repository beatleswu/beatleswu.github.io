from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import sgf_admin_workbench as workbench
from sgf_workbench_v2a import ensure_human_review_table, record_hash


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


def _connection():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    workbench.ensure_sgf_workbench_tables(connection)
    ensure_human_review_table(connection)
    return connection


def _record():
    return {
        "id": 431,
        "source": "w1-d3-r2-fixture",
        "content": "(;GM[1]FF[4]SZ[19]AB[aa]AW[ss]PL[B];B[bb])",
        "enabled": True,
    }


def _application(monkeypatch, records=None):
    monkeypatch.setenv("SECRET_KEY", "w1-d3-r2-v2a-test-only")
    import app as application

    application.app.secret_key = "w1-d3-r2-v2a-test-only"
    with application._auth_fail_lock:
        application._auth_fail_log.clear()
    connection = _connection()
    values = records if records is not None else [_record()]
    monkeypatch.setattr(application, "get_db", lambda: _ConnectionContext(connection))
    monkeypatch.setattr(application, "_load_questions", lambda: values)
    return application, connection, values


def _headers(application, client, user_id=7):
    token = "t" * 32
    with client.session_transaction() as session:
        session["user_id"] = user_id
        session["is_admin"] = True
        session["sgf_answer_review_csrf"] = token
    return {application._REVIEW_CSRF_HEADER: token}


def _review_body(values, classification="CORRECT"):
    record = values[0]
    return {
        "record_index": 0,
        "legacy_question_id": record["id"],
        "reviewed_record_sha256": record_hash(record),
        "classification": classification,
    }


def _table_counts(connection):
    names = [row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )]
    return {
        name: connection.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
        for name in names
    }


@pytest.mark.parametrize(
    "path,kind",
    [
        ("/api/admin/sgf-workbench-v2a/reviews", "review"),
        ("/api/admin/sgf-answer-review/v2a/reviews", "review"),
        ("/api/admin/sgf-workbench-v2a/progress", "progress"),
        ("/api/admin/sgf-answer-review/v2a/progress", "progress"),
    ],
)
def test_v2a_mutation_aliases_are_throttled(monkeypatch, path, kind):
    application, _connection_value, values = _application(monkeypatch)
    client = application.app.test_client()
    headers = _headers(application, client)
    payload = _review_body(values) if kind == "review" else {"record_index": 0}

    for _ in range(application.WORKBENCH_MUTATION_RATE_MAX):
        response = client.post(path, json=payload, headers=headers)
        assert response.status_code == 200, response.get_json()

    throttled = client.post(path, json=payload, headers=headers)
    assert throttled.status_code == 429
    assert throttled.get_json() == {"error": "rate_limited"}


def test_v2a_review_and_progress_persist_below_limit(monkeypatch):
    application, connection, values = _application(monkeypatch)
    client = application.app.test_client()
    headers = _headers(application, client)

    review = client.post(
        "/api/admin/sgf-workbench-v2a/reviews",
        json=_review_body(values),
        headers=headers,
    )
    progress = client.post(
        "/api/admin/sgf-workbench-v2a/progress",
        json={"record_index": 0},
        headers=headers,
    )

    assert review.status_code == 200
    assert progress.status_code == 200
    assert connection.execute(
        "SELECT COUNT(*) FROM sgf_human_review_state WHERE reviewer_id=7"
    ).fetchone()[0] == 1
    assert connection.execute(
        "SELECT COUNT(*) FROM sgf_human_review_progress WHERE reviewer_id=7"
    ).fetchone()[0] == 1
    with application._auth_fail_lock:
        assert len(application._auth_fail_log["workbench:7"]) == 2


def test_v2a_throttle_blocks_review_and_progress_without_any_persistent_write(monkeypatch):
    application, connection, values = _application(monkeypatch)
    client = application.app.test_client()
    headers = _headers(application, client, user_id=7)
    review_body = _review_body(values)

    for _ in range(application.WORKBENCH_MUTATION_RATE_MAX):
        assert client.post(
            "/api/admin/sgf-workbench-v2a/reviews",
            json=review_body,
            headers=headers,
        ).status_code == 200
    before_review_throttle = _table_counts(connection)
    throttled_review = client.post(
        "/api/admin/sgf-workbench-v2a/reviews",
        json=review_body,
        headers=headers,
    )
    assert throttled_review.status_code == 429
    assert _table_counts(connection) == before_review_throttle

    progress_client = application.app.test_client()
    progress_headers = _headers(application, progress_client, user_id=8)
    progress_body = {"record_index": 0}
    for _ in range(application.WORKBENCH_MUTATION_RATE_MAX):
        assert progress_client.post(
            "/api/admin/sgf-workbench-v2a/progress",
            json=progress_body,
            headers=progress_headers,
        ).status_code == 200
    before_progress_throttle = _table_counts(connection)
    throttled_progress = progress_client.post(
        "/api/admin/sgf-workbench-v2a/progress",
        json=progress_body,
        headers=progress_headers,
    )
    assert throttled_progress.status_code == 429
    assert _table_counts(connection) == before_progress_throttle


def test_workbench_policy_is_independent_from_dm_constants(monkeypatch):
    application, _connection_value, _values = _application(monkeypatch)
    source = (ROOT / "app.py").read_text(encoding="utf-8")

    assert application.WORKBENCH_MUTATION_RATE_MAX == 5
    assert application.WORKBENCH_MUTATION_RATE_WINDOW_SEC == 10
    assert "WORKBENCH_MUTATION_RATE_MAX = DM_RATE_MAX" not in source
    assert "WORKBENCH_MUTATION_RATE_WINDOW_SEC = DM_RATE_WINDOW_SEC" not in source

    monkeypatch.setattr(application, "DM_RATE_MAX", 99)
    monkeypatch.setattr(application, "DM_RATE_WINDOW_SEC", 99)
    assert application.WORKBENCH_MUTATION_RATE_MAX == 5
    assert application.WORKBENCH_MUTATION_RATE_WINDOW_SEC == 10

    monkeypatch.setattr(application, "WORKBENCH_MUTATION_RATE_MAX", 3)
    monkeypatch.setattr(application, "WORKBENCH_MUTATION_RATE_WINDOW_SEC", 7)
    assert application.DM_RATE_MAX == 99
    assert application.DM_RATE_WINDOW_SEC == 99


def test_workbench_and_dm_limiters_keep_separate_state_paths():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "key = f'workbench:{user_id}'" in source
    assert "WHERE sender_id=? AND created_at>=?" in source
    assert "DM_RATE_MAX = 5" in source
    assert "WORKBENCH_MUTATION_RATE_MAX = 5" in source


def test_normal_v2a_ipad_review_actions_stay_below_limit(monkeypatch):
    application, _connection_value, values = _application(monkeypatch)
    client = application.app.test_client()
    headers = _headers(application, client)

    review = client.post(
        "/api/admin/sgf-workbench-v2a/reviews",
        json=_review_body(values),
        headers=headers,
    )
    progress = client.post(
        "/api/admin/sgf-workbench-v2a/progress",
        json={"record_index": 0},
        headers=headers,
    )

    assert review.status_code == 200
    assert progress.status_code == 200
    with application._auth_fail_lock:
        assert len(application._auth_fail_log["workbench:7"]) < application.WORKBENCH_MUTATION_RATE_MAX
