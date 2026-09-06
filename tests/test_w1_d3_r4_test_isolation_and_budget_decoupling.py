from __future__ import annotations

import ast
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _application(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "w1-d3-r4-rate-limit-test-only")
    import app as application

    application.app.secret_key = "w1-d3-r4-rate-limit-test-only"
    return application


def _headers(application, client, user_id=7):
    token = "t" * 32
    with client.session_transaction() as session:
        session["user_id"] = user_id
        session["is_admin"] = True
        session["sgf_answer_review_csrf"] = token
    return {application._REVIEW_CSRF_HEADER: token}


def _function_source(path: Path, function_name: str) -> str:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    lines = source.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            return "\n".join(lines[node.lineno - 1:node.end_lineno])
    raise AssertionError(f"function not found: {function_name}")


class _Db:
    def __enter__(self):
        return self

    def execute(self, *_args, **_kwargs):
        return _Row()

    def commit(self):
        return None

    def __exit__(self, exc_type, _value, _traceback):
        return False


class _Row:
    def fetchone(self):
        return {"id": 1}


def _patch_report_context(monkeypatch, application):
    context = {
        "question_id": 1,
        "record_index": 0,
        "candidate_move": None,
        "gameplay_surface": "training",
        "sgf_identity": "fixture",
        "node_identity": None,
        "board_state": None,
        "question_content_sha256": "fixture-sha",
        "authority": "fixture",
    }
    capture = {
        "review_item_id": 1,
        "group_key": "fixture",
        "report_count": 1,
    }
    monkeypatch.setattr(application, "_workbench_question_context", lambda *_a, **_k: context)
    monkeypatch.setattr(application, "capture_workbench_report", lambda *_a, **_k: capture)
    monkeypatch.setattr(application, "_get_questions_json_commit", lambda: "fixture-commit")
    monkeypatch.setattr(
        application,
        "_load_questions",
        lambda: [{"id": 1, "content": "(;GM[1]FF[4]SZ[19])"}],
    )
    monkeypatch.setattr(application, "get_db", lambda: _Db())


def test_shared_fixture_is_lazy_and_only_resets_feature_namespaces():
    source = (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    assert "sys.modules.get(\"app\")" in source
    assert "import app as application" not in source
    assert "def isolate_w1_d3_throttle_state" in source
    assert "pytest.fixture(autouse=True)" in source
    assert "workbench:" in source
    assert "question-report:" in source
    assert "login:" not in source
    assert "DM" not in source


def test_fixture_boundary_clears_feature_state_but_preserves_other_limiters(monkeypatch):
    application = _application(monkeypatch)
    with application._auth_fail_lock:
        application._auth_fail_log.update({
            "workbench:7": [1.0],
            "question-report:7": [1.0],
            "login:127.0.0.1": [1.0],
        })
    from conftest import _clear_feature_throttle_entries

    _clear_feature_throttle_entries()
    with application._auth_fail_lock:
        assert "workbench:7" not in application._auth_fail_log
        assert "question-report:7" not in application._auth_fail_log
        assert application._auth_fail_log["login:127.0.0.1"] == [1.0]


def test_workbench_budget_does_not_throttle_question_reports(monkeypatch):
    application = _application(monkeypatch)
    _patch_report_context(monkeypatch, application)
    monkeypatch.setattr(
        application,
        "resolve_workbench_item",
        lambda *_a, **_k: {"status": "NEEDS_RESEARCH"},
    )
    client = application.app.test_client()
    headers = _headers(application, client)

    for _ in range(application.WORKBENCH_MUTATION_RATE_MAX):
        assert client.post(
            "/api/admin/sgf-workbench/items/1/status",
            json={"status": "NEEDS_RESEARCH"},
            headers=headers,
        ).status_code == 200
    assert client.post(
        "/api/question/report",
        json={"question_id": 1, "reason": "OTHER"},
        headers=headers,
    ).status_code == 200


def test_question_report_budget_does_not_throttle_workbench(monkeypatch):
    application = _application(monkeypatch)
    _patch_report_context(monkeypatch, application)
    monkeypatch.setattr(
        application,
        "resolve_workbench_item",
        lambda *_a, **_k: {"status": "NEEDS_RESEARCH"},
    )
    client = application.app.test_client()
    headers = _headers(application, client)

    for _ in range(application.QUESTION_REPORT_RATE_MAX):
        assert client.post(
            "/api/question/report",
            json={"question_id": 1, "reason": "OTHER"},
            headers=headers,
        ).status_code == 200
    response = client.post(
        "/api/admin/sgf-workbench/items/1/status",
        json={"status": "NEEDS_RESEARCH"},
        headers=headers,
    )
    assert response.status_code == 200


def test_workbench_budget_throttles_its_sixth_request(monkeypatch):
    application = _application(monkeypatch)
    monkeypatch.setattr(application, "get_db", lambda: _Db())
    monkeypatch.setattr(
        application,
        "resolve_workbench_item",
        lambda *_a, **_k: {"status": "NEEDS_RESEARCH"},
    )
    client = application.app.test_client()
    headers = _headers(application, client)

    for _ in range(5):
        response = client.post(
            "/api/admin/sgf-workbench/items/1/status",
            json={"status": "NEEDS_RESEARCH"},
            headers=headers,
        )
        assert response.status_code == 200
    throttled = client.post(
        "/api/admin/sgf-workbench/items/1/status",
        json={"status": "NEEDS_RESEARCH"},
        headers=headers,
    )
    assert throttled.status_code == 429


@pytest.mark.parametrize(
    "endpoint, payload",
    [
        (
            "/api/question/problem-report",
            {"question_id": 1, "reason_code": "other"},
        ),
        (
            "/api/question/report",
            {"question_id": 1, "reason": "OTHER"},
        ),
        (
            "/api/question/alternative-report",
            {"question_id": 1, "move": {"x": 1, "y": 1}},
        ),
    ],
)
def test_all_question_report_aliases_throttle_their_sixth_request(
    monkeypatch, endpoint, payload
):
    application = _application(monkeypatch)
    _patch_report_context(monkeypatch, application)
    client = application.app.test_client()
    headers = _headers(application, client)

    for _ in range(application.QUESTION_REPORT_RATE_MAX):
        response = client.post(endpoint, json=payload, headers=headers)
        assert response.status_code == 200, response.get_json()
    throttled = client.post(endpoint, json=payload, headers=headers)
    assert throttled.status_code == 429
    assert throttled.get_json() == {"error": "rate_limited"}


@pytest.mark.parametrize(
    "endpoint",
    [
        "/api/question/problem-report",
        "/api/question/report",
        "/api/question/alternative-report",
    ],
)
def test_all_question_report_aliases_remain_authenticated(monkeypatch, endpoint):
    application = _application(monkeypatch)
    client = application.app.test_client()
    response = client.post(endpoint, json={"question_id": 1})
    assert response.status_code == 401


def test_question_report_routes_use_distinct_helper_and_policy():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "QUESTION_REPORT_RATE_MAX = 5" in source
    assert "QUESTION_REPORT_RATE_WINDOW_SEC = 10" in source
    for name in (
        "api_question_problem_report",
        "api_question_unified_report",
        "question_alternative_report",
    ):
        function = _function_source(ROOT / "app.py", name)
        assert "_question_report_throttle_failure()" in function
        assert "_workbench_mutation_throttle_failure()" not in function


def test_question_report_workbench_and_dm_policies_remain_independent(monkeypatch):
    application = _application(monkeypatch)
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "DM_RATE_MAX = 5" in source
    assert "DM_RATE_WINDOW_SEC = 10" in source
    assert "WHERE sender_id=? AND created_at>=?" in source
    assert application.WORKBENCH_MUTATION_RATE_MAX == 5
    assert application.QUESTION_REPORT_RATE_MAX == 5

    monkeypatch.setattr(application, "DM_RATE_MAX", 99)
    monkeypatch.setattr(application, "DM_RATE_WINDOW_SEC", 99)
    assert application.WORKBENCH_MUTATION_RATE_MAX == 5
    assert application.WORKBENCH_MUTATION_RATE_WINDOW_SEC == 10
    assert application.QUESTION_REPORT_RATE_MAX == 5
    assert application.QUESTION_REPORT_RATE_WINDOW_SEC == 10

    monkeypatch.setattr(application, "QUESTION_REPORT_RATE_MAX", 3)
    monkeypatch.setattr(application, "QUESTION_REPORT_RATE_WINDOW_SEC", 7)
    assert application.DM_RATE_MAX == 99
    assert application.DM_RATE_WINDOW_SEC == 99
    assert application.WORKBENCH_MUTATION_RATE_MAX == 5
    assert application.WORKBENCH_MUTATION_RATE_WINDOW_SEC == 10
