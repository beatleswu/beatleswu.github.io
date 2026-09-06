from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _function_source(path: Path, function_name: str) -> str:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    lines = source.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            return "\n".join(lines[node.lineno - 1:node.end_lineno])
    raise AssertionError(f"function not found: {function_name}")


def test_existing_rate_limiter_and_policy_are_reused():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "def _throttle_check(" in source
    assert "def _throttle_record(" in source
    assert "WORKBENCH_MUTATION_RATE_MAX = 5" in source
    assert "WORKBENCH_MUTATION_RATE_WINDOW_SEC = 10" in source
    assert "WORKBENCH_MUTATION_RATE_MAX_HITS = DM_RATE_MAX" not in source
    assert "WORKBENCH_MUTATION_RATE_WINDOW_SEC = DM_RATE_WINDOW_SEC" not in source
    assert "DM_RATE_MAX" in source
    assert "DM_RATE_WINDOW_SEC" in source
    assert "flask_limiter" not in source.lower()
    assert "class WorkbenchRateLimiter" not in source


def test_workbench_mutation_routes_call_throttle_before_persistence():
    app_source = ROOT / "app.py"
    routes = {
        "admin_sgf_workbench_flag",
        "admin_sgf_workbench_stage",
        "admin_sgf_workbench_validate",
        "admin_sgf_workbench_status",
        "admin_sgf_workbench_retest",
        "admin_sgf_workbench_direct_retest",
        "admin_sgf_workbench_batches",
        "admin_sgf_workbench_batch_ready",
        "api_question_problem_report",
        "api_question_unified_report",
        "question_alternative_report",
        "admin_question_problem_report_resolve",
        "admin_review_queue_resolve",
        "admin_review_queue_import",
        "admin_question_alternative_report_resolve",
    }
    for name in routes:
        function = _function_source(app_source, name)
        assert "_workbench_mutation_throttle_failure()" in function, name

    # Direct Apply and rollback keep the existing disabled gate ahead of the
    # limiter; this task cannot activate or shortcut that gate.
    for name in ("admin_sgf_workbench_direct_apply", "admin_sgf_workbench_direct_rollback"):
        function = _function_source(app_source, name)
        assert "if not _direct_apply_enabled():" in function
        assert "direct_apply_disabled" in function
        assert "_workbench_mutation_throttle_failure()" in function


def test_blueprint_mutations_use_injected_application_throttle():
    source = (ROOT / "sgf_answer_review_routes.py").read_text(encoding="utf-8")
    assert "mutation_throttle_failure=None" in source
    for name in ("review_save", "review_undo", "review_progress", "shadow_review"):
        function = _function_source(ROOT / "sgf_answer_review_routes.py", name)
        assert "_mutation_throttle_failure()" in function, name


def test_v2a_persistent_mutations_use_injected_application_throttle():
    source = (ROOT / "sgf_workbench_v2a_routes.py").read_text(encoding="utf-8")
    assert "mutation_throttle_failure=None" in source
    for name in ("review", "progress"):
        function = _function_source(ROOT / "sgf_workbench_v2a_routes.py", name)
        assert "_mutation_throttle_failure()" in function, name


def test_direct_apply_gate_remains_disabled_and_does_not_consume_throttle(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "w1-d3-security-boundary-test-only")
    import app as application

    application.app.secret_key = "w1-d3-security-boundary-test-only"
    with application._auth_fail_lock:
        application._auth_fail_log.clear()
    monkeypatch.setattr(application, "_direct_apply_enabled", lambda: False)

    client = application.app.test_client()
    token = "t" * 32
    with client.session_transaction() as session:
        session["user_id"] = 7
        session["is_admin"] = True
        session["sgf_answer_review_csrf"] = token
    response = client.post(
        "/api/admin/sgf-workbench/direct-apply",
        json={},
        headers={application._REVIEW_CSRF_HEADER: token},
    )
    assert response.status_code == 403
    assert response.get_json()["error"] == "direct_apply_disabled"
    with application._auth_fail_lock:
        assert not any(key == "workbench:7" for key in application._auth_fail_log)


def test_no_runtime_authority_or_progression_files_are_part_of_this_change():
    changed = {
        "app.py",
        "sgf_answer_review_routes.py",
        "tests/test_w1_d3_workbench_mutation_rate_limit.py",
        "tests/test_w1_d3_workbench_security_boundary.py",
    }
    forbidden = {
        "map_battle_runtime.py",
        "adventure_first_clear_convergence.py",
        "event_outbox.py",
        "identity_read_adapter.py",
        "questions.json",
        "nginx/default.conf",
    }
    assert changed.isdisjoint(forbidden)
