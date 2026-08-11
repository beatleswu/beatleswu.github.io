from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(name):
    return (ROOT / name).read_text(encoding="utf-8")


def test_workbench_contract_routes_and_widget_are_present():
    app = _read("app.py")
    module = _read("sgf_admin_workbench.py")
    widget = _read("sgf_report_widget.js")
    assert "/api/admin/sgf-workbench/bootstrap" in app
    assert "/api/admin/sgf-workbench/items/<int:item_id>/stage" in app
    assert "/api/admin/sgf-workbench/items/<int:item_id>/retest" in app
    assert "/api/admin/sgf-workbench/batches" in app
    assert "WORKBENCH_SOURCES" in module and "CORPUS_SCAN" in module
    assert "OWNER_DESIRED_VERDICT" not in widget  # widget captures, it does not redefine judging
    assert "/api/question/report" in widget
    assert "data-sgf-report-surface" in widget
    assert "data-sgf-admin-flag" in widget
    assert "data-sgf-admin-stage" in widget
    assert "data-sgf-admin-retest" in widget


def test_all_required_surface_documents_load_the_shared_report_widget():
    expected = {
        "index.html": "main_practice",
        "mistakes.html": "main_practice",
        "rating_test.html": "rating_test_server",
        "daily_challenge.html": "daily_challenge_client",
        "community.html": "friend_challenge_client_then_server_trust",
        "play.html": "friend_challenge_client_then_server_trust",
    }
    for name, surface in expected.items():
        page = _read(name)
        assert "<script src=\"/sgf_report_widget.js\"" in page
        assert f'data-sgf-report-surface="{surface}"' in page


def test_review_queue_keeps_touch_contract_and_unified_panel():
    html = _read("sgf_answer_review.html")
    js = _read("sgf_answer_review.js")
    assert "ipad-768x1024" in html and "touch-action:manipulation" in html
    assert "unified-workbench-panel" in html
    assert "workbench-source-filter" in html
    assert "/api/admin/sgf-workbench/items" in js
    assert "CREATE staged batch" not in js
    assert "workbench-batch-btn" in js
    assert "data-action=\"inspect\"" in js


def test_workbench_routes_are_explicitly_non_mutating_and_csrf_protected():
    app = _read("app.py")
    start = app.index("@app.route('/api/admin/sgf-workbench/flag'")
    end = app.index("@app.route('/api/admin/shadow/dashboard')", start)
    block = app[start:end]
    assert block.count("_review_csrf_failure()") >= 5
    assert "production_mutation': False" in block
    assert "_save_questions" not in block
