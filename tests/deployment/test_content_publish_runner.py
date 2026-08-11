"""Static safety contract for the governed content-only runner."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "scripts/release/publish-content-release.ps1"
HELPER = ROOT / "tools/content_remote_publish.py"
RECEIPT_SCHEMA = ROOT / "schemas/content_remote_publish_receipt.schema.json"


def test_runner_and_receipt_schema_exist_and_parse() -> None:
    assert RUNNER.is_file()
    assert HELPER.is_file()
    assert json.loads(RECEIPT_SCHEMA.read_text(encoding="utf-8"))["$id"].endswith("content_remote_publish_receipt.schema.json")


def test_runner_reuses_bounded_transport_and_existing_release_lock() -> None:
    content = RUNNER.read_text(encoding="utf-8")
    for primitive in (
        "Invoke-BoundedNativeCommand",
        "Invoke-BoundedSshCommand",
        "Invoke-BoundedScpUpload",
        "Enter-RemoteReleaseOperationLock",
        "Exit-RemoteReleaseOperationLock",
    ):
        assert primitive in content
    assert "NEW_REMOTE_FRAMEWORK_CREATED" not in content


def test_runner_is_content_only_and_does_not_restart_or_deploy_services() -> None:
    content = RUNNER.read_text(encoding="utf-8").lower()
    for forbidden in ("docker exec", "docker compose up", "docker restart", "deploy-release-image", "deploy-static-release"):
        assert forbidden not in content
    assert "questions.json" in content
    assert "app/data/questions.json" in content


def test_runner_is_fail_closed_and_dry_run_by_default() -> None:
    content = RUNNER.read_text(encoding="utf-8")
    assert "if (-not $Execute)" in content
    assert "Assert-OwnerGate -Provided $OwnerGate -Expected $ContentReleaseOwnerGate" in content
    assert "GO_PRODUCTION_CONTENT_RELEASE" in content
    assert "remote_staging = 'NOT_CREATED'" in content
    assert "production_mutation = $false" in content


def test_remote_helper_resolves_named_volume_and_rejects_arbitrary_paths() -> None:
    content = HELPER.read_text(encoding="utf-8")
    assert "docker" in content
    assert 'mount.get("Type") != "volume"' in content
    assert 'target.name != "questions.json"' in content
    assert "os.replace(stage_path, live)" in content
    assert "OLD_VERIFIED_CONTENT" in content
    assert "NEW_VERIFIED_CONTENT" in content


def test_no_sgf_specific_values_are_embedded_in_generic_runner() -> None:
    content = RUNNER.read_text(encoding="utf-8") + HELPER.read_text(encoding="utf-8")
    for value in ("4d13fa98", "b7b4eedf", "41591", "43", "54"):
        assert value not in content
