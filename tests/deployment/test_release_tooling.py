"""Validate the release tooling added for DEPLOY-GOV-3."""
import json
import os
import pathlib
import shutil
import subprocess

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
RELEASE_SCRIPTS = [
    REPO_ROOT / "scripts" / "release" / "ReleaseTooling.psm1",
    REPO_ROOT / "scripts" / "release" / "build-release-image.ps1",
    REPO_ROOT / "scripts" / "release" / "package-release-image.ps1",
    REPO_ROOT / "scripts" / "release" / "preflight-production.ps1",
    REPO_ROOT / "scripts" / "release" / "deploy-release-image.ps1",
    REPO_ROOT / "scripts" / "release" / "verify-production-release.ps1",
    REPO_ROOT / "scripts" / "release" / "rollback-release.ps1",
]


def read_text(path):
    return path.read_text(encoding="utf-8")


def load_json(path):
    return json.loads(read_text(path))


def assert_powershell_parse_ok(path):
    if shutil.which("powershell") is None:
        raise AssertionError("powershell is required for release script parse checks")
    escaped = str(path).replace("'", "''")
    script = (
        "$errors = $null; "
        f"[System.Management.Automation.Language.Parser]::ParseFile('{escaped}', [ref]$null, [ref]$errors) | Out-Null; "
        "if ($errors.Count -gt 0) { $errors | ForEach-Object { Write-Host $_.ToString() }; exit 1 }"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"{path} did not parse: {result.stdout}\n{result.stderr}"


def test_release_layout_example_has_required_contract_fields():
    layout = load_json(REPO_ROOT / "deploy" / "release-layout.example.json")
    required = {
        "ssh_alias",
        "remote_release_staging_directory",
        "compose_project",
        "compose_directory",
        "app_service_name",
        "scheduler_service_name",
        "nginx_service_name",
        "asset_source_path",
        "asset_container_mount_destination",
        "questions_content_source_path",
        "questions_content_mount_destination",
        "shadow_event_log_path",
        "health_url",
        "login_url",
        "homepage_url",
    }
    assert required.issubset(layout)
    assert "password" not in json.dumps(layout).lower()
    assert ".env" not in json.dumps(layout)


def test_release_layout_schema_requires_the_same_contract():
    schema = load_json(REPO_ROOT / "deploy" / "release-layout.schema.json")
    assert schema["type"] == "object"
    assert set(schema["required"]) >= {
        "ssh_alias",
        "compose_project",
        "app_service_name",
        "scheduler_service_name",
    }


def test_release_manifest_example_has_required_fields():
    manifest = load_json(REPO_ROOT / "deploy" / "release-manifest.example.json")
    required = {
        "release_git_sha",
        "image_tag",
        "image_id",
        "image_archive_filename",
        "archive_sha256",
        "oci_revision",
        "oci_source",
        "sgf_engine_source_commit",
        "build_timestamp",
        "build_machine_identity_class",
        "target_service_names",
        "external_content_requirements",
        "expected_health_endpoints",
        "rollback_image_identity",
        "deployment_timestamp",
        "verification_result",
    }
    assert required.issubset(manifest)
    assert manifest["image_tag"].startswith("go-odyssey-app:")
    assert manifest["release_git_sha"] == manifest["oci_revision"]
    assert len(manifest["release_git_sha"]) == 40


def test_release_manifest_schema_matches_required_fields():
    schema = load_json(REPO_ROOT / "deploy" / "release-manifest.schema.json")
    assert schema["type"] == "object"
    assert "rollback_image_identity" in schema["required"]
    assert "external_content_requirements" in schema["required"]


def test_release_compose_references_an_immutable_image_and_disabled_scheduler():
    content = read_text(REPO_ROOT / "docker-compose.release.yml")
    assert "GO_ODYSSEY_IMAGE" in content
    assert "go-odyssey-app:latest" not in content
    assert "PREMIUM_WEEKLY_SCHEDULER_ENABLED" in content
    assert ":-0" in content
    assert "version:" not in content
    assert "postgres:" in content and "nginx:" in content


def test_release_compose_config_with_fake_values():
    if shutil.which("docker") is None:
        return
    env = os.environ.copy()
    env.update(
        {
            "GO_ODYSSEY_IMAGE": "go-odyssey-app:deadbeef",
            "POSTGRES_PASSWORD": "fake-password",
            "ASSET_SOURCE_PATH": "/opt/fake-assets",
            "ASSET_CONTAINER_MOUNT_DESTINATION": "/opt/fake-assets",
            "QUESTIONS_CONTENT_SOURCE_PATH": "/opt/fake-data",
            "QUESTIONS_CONTENT_MOUNT_DESTINATION": "/app/data",
        }
    )
    result = subprocess.run(
        ["docker", "compose", "-f", "docker-compose.release.yml", "config"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "go-odyssey-app:deadbeef" in result.stdout


def test_build_script_uses_clean_tree_and_detached_worktree():
    content = read_text(REPO_ROOT / "scripts" / "release" / "build-release-image.ps1")
    for token in ("Assert-TrackedTreeClean", "New-DetachedWorktree", "shadow_judging.py --selftest", "py_compile"):
        assert token in content


def test_package_script_exports_checksum_and_manifest():
    content = read_text(REPO_ROOT / "scripts" / "release" / "package-release-image.ps1")
    for token in ("docker save", "Get-FileHash -Algorithm SHA256", "New-ReleaseManifestObject", "archive_sha256"):
        assert token in content


def test_preflight_script_reports_read_only_production_state():
    content = read_text(REPO_ROOT / "scripts" / "release" / "preflight-production.ps1")
    for token in (
        "docker version",
        "docker compose version",
        "df -h",
        "candidate_release_manifest_exists",
        "Get-RemoteReadinessReport",
        "QUESTIONS_JSON_PATH",
        "database_identity_match",
    ):
        assert token in content
    assert "docker compose up" not in content
    assert "docker push" not in content


def test_deploy_script_defaults_to_dry_run_and_requires_owner_gate():
    content = read_text(REPO_ROOT / "scripts" / "release" / "deploy-release-image.ps1")
    for token in ("GO_DEPLOY", "dry_run = $true", "deployment_plan"):
        assert token in content
    assert "Real deployment execution is not enabled in this Sprint" in content


def test_rollback_script_defaults_to_dry_run_and_requires_owner_gate():
    content = read_text(REPO_ROOT / "scripts" / "release" / "rollback-release.ps1")
    for token in ("GO_ROLLBACK", "dry_run = $true", "rollback_plan"):
        assert token in content
    assert "Real rollback execution is not enabled in this Sprint" in content


def test_verify_script_includes_e24a_and_premium_weekly_checks():
    content = read_text(REPO_ROOT / "scripts" / "release" / "verify-production-release.ps1")
    for token in (
        "SELFTEST OK (10/10)",
        "premium_weekly_default",
        "fail_observable_code_present",
        "shadow_verdict_simple_absent",
        "Get-RemoteReadinessReport",
        "readiness",
    ):
        assert token in content


def test_env_example_documents_runtime_contract():
    content = read_text(REPO_ROOT / ".env.production.example")
    for token in ("GO_ODYSSEY_LIVE_STATIC_ROOT", "QUESTIONS_JSON_PATH", "SHADOW_EVENTS_PATH"):
        assert token in content


def test_project_os_doc_describes_required_workflow():
    content = read_text(REPO_ROOT / "docs" / "project-os-v2.md")
    for token in ("risk classes", "standard sprint lifecycle", "mandatory production gates", "gameplay deployment definition", "go deploy"):
        assert token in content.lower()


def test_drift_verification_example_is_secret_free_and_structured():
    report = load_json(REPO_ROOT / "deploy" / "drift-verification.example.json")
    assert report["image_tag"].startswith("go-odyssey-app:")
    assert report["architecture"] == "linux/arm64"
    assert report["app_scheduler_config_match"] is True
    serialized = json.dumps(report).lower()
    assert "password" not in serialized
    assert "database_url" not in serialized


def test_release_artifacts_are_ignored():
    gitignore = read_text(REPO_ROOT / ".gitignore")
    assert "release-artifacts/" in gitignore


def test_release_scripts_parse_cleanly():
    for script in RELEASE_SCRIPTS:
        assert_powershell_parse_ok(script)
