"""P0 regression coverage for the shared review toolbar authorization boundary."""

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
WIDGET_SOURCE = (REPO_ROOT / "sgf_report_widget.js").read_text(encoding="utf-8")


def _authorized_client(application, *, is_admin):
    client = application.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 991111
        session["is_admin"] = is_admin
    return client


def test_privileged_toolbar_is_deferred_until_strict_admin_bootstrap():
    assert "data-sgf-admin-controls-template" in WIDGET_SOURCE
    assert "me.logged_in !== true || me.is_admin !== true" in WIDGET_SOURCE
    assert "mountAdminControls(state.host)" in WIDGET_SOURCE
    assert "quarantineAdminControls(host)" in WIDGET_SOURCE


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/admin/sgf-workbench/bootstrap"),
        ("get", "/api/admin/sgf-workbench/direct-context/431"),
        ("post", "/api/admin/sgf-workbench/flag"),
        ("post", "/api/admin/sgf-workbench/items/1/stage"),
        ("post", "/api/admin/sgf-workbench/items/1/validate"),
        ("post", "/api/admin/sgf-workbench/items/1/retest"),
        ("post", "/api/admin/sgf-workbench/direct-apply"),
        ("post", "/api/admin/sgf-workbench/direct-retest"),
        ("post", "/api/admin/sgf-workbench/direct-versions/1/rollback"),
        ("post", "/api/admin/sgf-answer-review/v2a/reviews"),
        ("post", "/api/admin/sgf-answer-review/v2a/progress"),
        ("post", "/api/admin/sgf-answer-review/progress"),
    ],
)
def test_non_admin_cannot_reach_privileged_review_endpoints(monkeypatch, method, path):
    monkeypatch.setenv("SECRET_KEY", "p0-nonadmin-toolbar-test")
    monkeypatch.setenv("SITE_URL", "http://localhost")
    import app as application

    client = _authorized_client(application, is_admin=False)
    request = getattr(client, method)
    response = request(path, json={}) if method == "post" else request(path)
    assert response.status_code == 403, (method, path, response.status_code, response.get_data(as_text=True))


def test_anonymous_privileged_bootstrap_is_unauthorized(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "p0-nonadmin-toolbar-test")
    monkeypatch.setenv("SITE_URL", "http://localhost")
    import app as application

    response = application.app.test_client().get("/api/admin/sgf-workbench/bootstrap")
    assert response.status_code == 401
