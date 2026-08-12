import json
import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
COMPOSE = ROOT / "docker-compose.acceptance.yml"
LAUNCHER = ROOT / "scripts" / "acceptance" / "run-lan-acceptance.ps1"
SEEDER = ROOT / "scripts" / "acceptance" / "seed_acceptance.py"
FIXTURE = ROOT / "tests" / "fixtures" / "acceptance" / "questions.json"


def test_acceptance_compose_isolated_and_single_host_http_port():
    text = COMPOSE.read_text(encoding="utf-8")
    assert "acceptance-pg-data" in text
    assert "acceptance-app-data" in text
    assert "PRODUCTION: \"0\"" in text
    assert "GO_ODYSSEY_ACCEPTANCE_MODE: \"1\"" in text
    assert "GO_ODYSSEY_ACCEPTANCE_PUBLISH_DISABLED: \"1\"" in text
    assert "./sgf_admin_workbench.py:/app/sgf_admin_workbench.py:ro" in text
    assert "go-data" not in text
    assert "docker-compose.prod.yml" not in text
    assert "${ACCEPTANCE_BIND_HOST:-0.0.0.0}:${ACCEPTANCE_PORT:-5080}:8080" in text
    assert text.count("ports:") == 1
    assert "postgres:5432" in text
    assert "5432:5432" not in text


def test_acceptance_launcher_is_source_checked_and_scope_guarded():
    text = LAUNCHER.read_text(encoding="utf-8")
    assert "git -C $RepoRoot rev-parse HEAD" in text
    assert "docker-compose.acceptance.yml" in text
    assert "go-odyssey-acceptance" in text
    assert "--volumes" in text
    assert "docker-compose.prod.yml" not in text
    assert "go-data" not in text
    assert "secret_key.txt" not in text
    assert "deploy.ps1" not in text


def test_acceptance_fixture_is_small_valid_and_representative():
    records = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert isinstance(records, list)
    assert len(records) >= 3
    ids = [row["id"] for row in records]
    assert len(ids) == len(set(ids))
    assert all("SZ[19]" in row["content"] for row in records)
    assert all(row["enabled"] and row["is_free"] for row in records)
    assert all(row["accepted_moves"] for row in records)


def test_acceptance_seeder_only_targets_fixture_and_acceptance_database():
    text = SEEDER.read_text(encoding="utf-8")
    assert "NON_PRODUCTION_ACCEPTANCE_FIXTURE" in text
    assert "question_problem_reports" in text
    assert "capture_workbench_report" in text
    assert "Production" in text
    assert "_save_questions" not in text
    assert "publish" not in text.lower()
    assert "secret_key.txt" not in text


def test_acceptance_identity_endpoint_and_visible_badge(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "acceptance-unit-test")
    monkeypatch.setenv("APP_GIT_SHA", "8910160855030d6266b52b63242b7a9c384d0e24")
    monkeypatch.setenv("GO_ODYSSEY_ACCEPTANCE_MODE", "1")
    monkeypatch.setenv("GO_ODYSSEY_ACCEPTANCE_SOURCE_SHA", "8910160855030d6266b52b63242b7a9c384d0e24")
    import app as application

    client = application.app.test_client()
    identity = client.get("/api/acceptance/identity")
    assert identity.status_code == 200
    payload = identity.get_json()
    assert payload["ok"] is True
    assert payload["production"] is False
    assert payload["production_publish_available"] is False
    assert payload["source_sha_match"] is True
    page = client.get("/login")
    assert page.status_code == 200
    assert page.headers["X-Go-Odyssey-Environment"] == "NON-PRODUCTION-ACCEPTANCE"
    assert "go-odyssey-acceptance-banner" in page.get_data(as_text=True)


def test_acceptance_identity_is_disabled_outside_profile(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "acceptance-unit-test")
    monkeypatch.delenv("GO_ODYSSEY_ACCEPTANCE_MODE", raising=False)
    import app as application

    response = application.app.test_client().get("/api/acceptance/identity")
    assert response.status_code == 404


def test_production_compose_remains_untouched():
    production = ROOT / "docker-compose.prod.yml"
    assert production.exists()
    changed = os.popen("git diff --name-only -- docker-compose.prod.yml").read()
    assert changed.strip() == ""
