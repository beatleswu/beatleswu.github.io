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


def write_json(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def assert_tokens_in_order(content, *tokens):
    cursor = 0
    for token in tokens:
        index = content.find(token, cursor)
        assert index != -1, f"missing ordered token: {token}"
        cursor = index + len(token)


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


def make_fake_preflight_responses(*, helper_mode="helper"):
    responses = {
        "app_container_snapshot": {
            "stdout": "cid-app|sha256:app-current|go-odyssey-app:current|running|healthy|0|false|go-odyssey|app"
        },
        "scheduler_container_snapshot": {
            "stdout": "cid-scheduler|sha256:scheduler-current|go-odyssey-app:current|running||0|false|go-odyssey|scheduler"
        },
        "nginx_container_snapshot": {
            "stdout": "cid-nginx|sha256:nginx-current|nginx:alpine|running||0|false|go-odyssey|nginx"
        },
        "app_env": {
            "stdout": json.dumps(
                [
                    "DATABASE_URL=postgresql://godokoro:super-secret@db.internal:5432/go_odyssey",
                    "QUESTIONS_JSON_PATH=/app/data/questions.json",
                    "GO_ODYSSEY_LIVE_STATIC_ROOT=/opt/go-odyssey-static/current",
                    "SHADOW_EVENTS_PATH=/app/data/shadow_events.jsonl",
                ]
            )
        },
        "scheduler_env": {
            "stdout": json.dumps(
                [
                    "DATABASE_URL=postgresql://godokoro:super-secret@db.internal:5432/go_odyssey",
                    "QUESTIONS_JSON_PATH=/app/data/questions.json",
                ]
            )
        },
        "docker_version": {"stdout": "29.5.3"},
        "compose_version": {"stdout": "2.39.1"},
        "disk_free_kb": {"stdout": "overlay 4194304 1024 4193280 1% /"},
        "remote_staging_path_status": {"stdout": "parent-writable"},
        "healthz_status": {"stdout": "200"},
        "healthz_body": {"stdout": '{"ok": true}'},
        "login_status": {"stdout": "200"},
        "home_status": {"stdout": "200"},
        "daily_challenge_status": {"stdout": "200"},
        "questions_report": {
            "stdout": json.dumps(
                {
                    "path": "/app/data/questions.json",
                    "exists": True,
                    "readable": True,
                    "parseable": True,
                    "top_level_type": "list",
                    "record_count": 321,
                    "record_count_ok": True,
                    "structural_record_check": True,
                    "failures": [],
                }
            )
        },
    }
    if helper_mode == "helper":
        responses["app_helper_readiness"] = {
            "stdout": json.dumps(
                {
                    "ok": True,
                    "questions": {
                        "path": "/app/data/questions.json",
                        "exists": True,
                        "readable": True,
                        "parseable": True,
                        "record_count": 321,
                        "record_count_ok": True,
                        "structural_record_check": True,
                        "failures": [],
                    },
                    "database": {"reachable": True, "tables": {}},
                }
            )
        }
    elif helper_mode == "legacy":
        responses["app_helper_readiness"] = {
            "stdout": "AttributeError: module 'app' has no attribute '_read_runtime_deployment_readiness'",
            "exit_code": 1,
        }
    elif helper_mode == "error":
        responses["app_helper_readiness"] = {
            "stdout": "Traceback (most recent call last): RuntimeError: helper crashed unexpectedly",
            "exit_code": 1,
        }
    else:
        raise AssertionError(f"unknown helper_mode: {helper_mode}")
    return {"responses": responses}


def run_preflight_with_fake_remote(tmp_path, fake_remote_payload):
    fake_remote_path = tmp_path / "fake-remote.json"
    archive_path = tmp_path / "release.tar"
    archive_path.write_bytes(b"artifact")
    write_json(fake_remote_path, fake_remote_payload)
    env = os.environ.copy()
    env["GO_ODYSSEY_PREFLIGHT_FAKE_REMOTE_RESPONSES"] = str(fake_remote_path)
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(REPO_ROOT / "scripts" / "release" / "preflight-production.ps1"),
            "-LayoutFile",
            str(REPO_ROOT / "deploy" / "release-layout.example.json"),
            "-ReleaseManifest",
            str(REPO_ROOT / "deploy" / "release-manifest.example.json"),
            "-ReleaseArchive",
            str(archive_path),
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return result


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
        "df -Pk",
        "candidate_release_manifest_exists",
        "Try-Get-RemoteReadinessReport",
        "legacy_fallback",
        "questions_report",
        "daily_challenge_status",
        "remote_staging_path_status",
        "QUESTIONS_JSON_PATH",
        "database_identity_match",
        "[System.Management.Automation.ErrorRecord]",
        '-replace "`r`n", "`n" -replace "`r", "`n"',
        "docker exec -i $ContainerName python -X utf8 -",
    ):
        assert token in content
    assert '{{with index .State "Health"}}{{index . "Status"}}{{end}}' in content
    assert "docker compose up" not in content
    assert "docker push" not in content


def test_preflight_uses_helper_when_runtime_helper_is_available(tmp_path):
    payload = make_fake_preflight_responses(helper_mode="helper")
    payload["responses"].pop("questions_report")
    result = run_preflight_with_fake_remote(tmp_path, payload)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["readiness_mode"] == "helper"
    assert report["helper_available"] is True
    assert report["questions"]["record_count"] == 321


def test_preflight_uses_legacy_fallback_when_runtime_helper_is_absent(tmp_path):
    result = run_preflight_with_fake_remote(
        tmp_path, make_fake_preflight_responses(helper_mode="legacy")
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["readiness_mode"] == "legacy_fallback"
    assert report["helper_available"] is False
    assert report["questions"]["record_count"] == 321
    assert report["daily_challenge_status"] == "200"


def test_preflight_fails_closed_on_unexpected_helper_errors(tmp_path):
    result = run_preflight_with_fake_remote(
        tmp_path, make_fake_preflight_responses(helper_mode="error")
    )
    assert result.returncode != 0
    assert "helper failed unexpectedly" in (result.stdout + result.stderr)


def test_preflight_fails_closed_when_scheduler_is_not_running(tmp_path):
    payload = make_fake_preflight_responses(helper_mode="legacy")
    payload["responses"]["scheduler_container_snapshot"]["stdout"] = (
        "cid-scheduler|sha256:scheduler-current|go-odyssey-app:current|exited||0|false|go-odyssey|scheduler"
    )
    result = run_preflight_with_fake_remote(tmp_path, payload)
    assert result.returncode != 0
    assert "Scheduler container is not running." in (result.stdout + result.stderr)


def test_preflight_detects_restart_loops(tmp_path):
    payload = make_fake_preflight_responses(helper_mode="legacy")
    payload["responses"]["app_container_snapshot"]["stdout"] = (
        "cid-app|sha256:app-current|go-odyssey-app:current|running|healthy|4|true|go-odyssey|app"
    )
    result = run_preflight_with_fake_remote(tmp_path, payload)
    assert result.returncode != 0
    assert "App container is restarting." in (result.stdout + result.stderr)


def test_preflight_requires_valid_questions_report(tmp_path):
    payload = make_fake_preflight_responses(helper_mode="legacy")
    payload["responses"]["questions_report"]["stdout"] = json.dumps(
        {
            "path": "/app/data/questions.json",
            "exists": True,
            "readable": True,
            "parseable": False,
            "top_level_type": "",
            "record_count": 0,
            "record_count_ok": False,
            "structural_record_check": False,
            "failures": ["questions file parse failed: JSONDecodeError"],
        }
    )
    result = run_preflight_with_fake_remote(tmp_path, payload)
    assert result.returncode != 0
    assert "Questions file is not parseable JSON." in (result.stdout + result.stderr)


def test_preflight_requires_non_empty_daily_challenge(tmp_path):
    payload = make_fake_preflight_responses(helper_mode="legacy")
    payload["responses"]["daily_challenge_status"]["stdout"] = "503"
    result = run_preflight_with_fake_remote(tmp_path, payload)
    assert result.returncode != 0
    assert "Daily challenge returned 503." in (result.stdout + result.stderr)


def test_preflight_requires_matching_sanitized_database_identity(tmp_path):
    payload = make_fake_preflight_responses(helper_mode="legacy")
    payload["responses"]["scheduler_env"]["stdout"] = json.dumps(
        [
            "DATABASE_URL=postgresql://godokoro:other-secret@db.internal:5432/other_db",
            "QUESTIONS_JSON_PATH=/app/data/questions.json",
        ]
    )
    result = run_preflight_with_fake_remote(tmp_path, payload)
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "App and scheduler database configuration must match." in combined
    assert "super-secret" not in combined
    assert "other-secret" not in combined


def test_preflight_requires_sufficient_disk_and_rollback_identity(tmp_path):
    payload = make_fake_preflight_responses(helper_mode="legacy")
    payload["responses"]["disk_free_kb"]["stdout"] = "overlay 1024 1000 24 99% /"
    payload["responses"]["scheduler_container_snapshot"]["stdout"] = (
        "cid-scheduler||go-odyssey-app:current|running||0|false|go-odyssey|scheduler"
    )
    result = run_preflight_with_fake_remote(tmp_path, payload)
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert (
        "Production host does not have enough free disk for the release artifact." in combined
        or "Scheduler image ID is missing." in combined
    )


def test_deploy_script_defaults_to_dry_run_and_supports_real_image_deploy():
    content = read_text(REPO_ROOT / "scripts" / "release" / "deploy-release-image.ps1")
    for token in (
        "GO_DEPLOY",
        "GO_ROLLBACK",
        "dry_run = $true",
        "deployment_plan",
        "ExpectedImageId",
        "ExpectedArchiveSha256",
        "ExpectedPlatform",
        "docker load",
        "scp",
        "verify-production-release.ps1",
        "rollback_image_identity",
        "deployment_record_path",
        "release_archive_size_bytes",
        "local_image_summary",
        "linux/arm64",
    ):
        assert token in content
    assert "docker build" not in content.lower()
    assert "Real deployment execution is not enabled in this Sprint" not in content


def test_deploy_script_supports_legacy_readiness_and_automatic_rollback():
    content = read_text(REPO_ROOT / "scripts" / "release" / "deploy-release-image.ps1")
    for token in (
        "legacy_fallback",
        "Get-AppReadinessGateReport",
        "Assert-QuestionsReportSatisfiesGate",
        "Get-CanonicalAppHealthcheckDefinition",
        "New-CanonicalAppHealthcheckOverrideYaml",
        "Get-RemoteRuntimeContract",
        "Start-RemoteCandidateCanary",
        "Get-RemoteContainerHttpStatus",
        "public_traffic_attached",
        "scheduler_started",
        "Remove-RemoteCandidateCanary",
        "rollback-release.ps1",
        "Deployment failed and automatic rollback succeeded",
        "Automatic rollback failed",
    ):
        assert token in content


def test_deploy_script_orders_release_mutations_safely():
    content = read_text(REPO_ROOT / "scripts" / "release" / "deploy-release-image.ps1")
    assert_tokens_in_order(
        content,
        "Assert-OwnerGate -Provided $OwnerGate -Expected 'GO_DEPLOY'",
        "$appComposeService = if ([string]::IsNullOrWhiteSpace($appBefore.compose_service)) { $layout.app_service_name } else { $appBefore.compose_service }",
        "$composeEnvPrefix = Get-RemoteComposeEnvironmentPrefix -ImageTag $manifest.image_tag",
        'Invoke-RemoteText "docker load -i $(Quote-PosixShellArgument $remoteArchivePath)"',
        "$appRuntimeContract = Get-RemoteRuntimeContract -ContainerName $layout.app_service_name",
        "$schedulerRuntimeContract = Get-RemoteRuntimeContract -ContainerName $layout.scheduler_service_name",
        "$candidateCanary = Start-RemoteCandidateCanary -SourceContainerName $layout.app_service_name",
        "if ($candidateCanary.public_traffic_attached -ne $false)",
        "if ($candidateCanary.scheduler_started -ne $false)",
        "$candidateHealthcheckTest = @($candidateCanary.healthcheck_test | ConvertFrom-Json)",
        "$candidateReadinessReport = Get-AppReadinessGateReport -ContainerName $candidateContainerName -UseContainerHttp",
        "if ($candidateReadinessReport.healthz_status -ne '200'",
        'Invoke-RemoteText "cd $(Quote-PosixShellArgument $layout.compose_directory) && $composeEnvPrefix docker compose -f docker-compose.release.yml -f $(Quote-PosixShellArgument $remoteHealthcheckOverridePath) up -d --no-build --no-deps --force-recreate $appComposeService"',
        'Invoke-RemoteText "cd $(Quote-PosixShellArgument $layout.compose_directory) && $composeEnvPrefix docker compose -f docker-compose.release.yml -f $(Quote-PosixShellArgument $remoteHealthcheckOverridePath) up -d --no-build --no-deps --force-recreate $schedulerComposeService"',
        'Invoke-RemoteText "docker restart $(Quote-PosixShellArgument $layout.nginx_service_name)"',
        "Remove-RemoteCandidateCanary -CandidateContainerName $candidateContainerName -ComposeProjectName $candidateCanary.compose_project -ComposePath $candidateCanary.compose_path",
    )


def test_deploy_script_persists_sanitized_runtime_contracts_for_rollback():
    content = read_text(REPO_ROOT / "scripts" / "release" / "deploy-release-image.ps1")
    for token in (
        '"environment_keys"',
        '"environment_value_fingerprints"',
        '"source_hash"',
        '"postgres_compose_keys_required"',
        "previous_app_runtime_contract = $appRuntimeContract",
        "previous_scheduler_runtime_contract = $schedulerRuntimeContract",
        "Runtime-derived compose database values are incomplete.",
    ):
        assert token in content
    for token in ("full DATABASE_URL", "complete .env"):
        assert token not in content


def test_canonical_app_healthcheck_contract_is_exec_form():
    tooling = read_text(REPO_ROOT / "scripts" / "release" / "ReleaseTooling.psm1")
    deploy = read_text(REPO_ROOT / "scripts" / "release" / "deploy-release-image.ps1")
    for token in (
        "'CMD'",
        "'python'",
        "'-c'",
        "127.0.0.1:8080/healthz",
        "interval = '10s'",
        "timeout = '5s'",
        "retries = 12",
        "start_period = '30s'",
    ):
        assert token in tooling
    assert "args.extend([\"--health-cmd\", test[3]])" not in deploy


def test_deploy_script_verifies_exec_form_healthcheck_for_canary_and_app():
    content = read_text(REPO_ROOT / "scripts" / "release" / "deploy-release-image.ps1")
    for token in (
        "Assert-CanonicalExecHealthcheckTest",
        "if ($HealthcheckTest[0] -ne 'CMD')",
        "if ($HealthcheckTest[1] -ne 'python')",
        "if ($HealthcheckTest[2] -ne '-c')",
        "127\\.0\\.0\\.1:8080/healthz",
        "Assert-CanonicalExecHealthcheckTest -HealthcheckTest $candidateHealthcheckTest -Context 'Candidate canary'",
        "Assert-CanonicalExecHealthcheckTest -HealthcheckTest $appHealthcheckTest -Context 'App container'",
        "$remoteHealthcheckOverridePath",
        "docker-compose.release.healthcheck.override.yml",
    ):
        assert token in content


def test_candidate_compose_declares_named_volumes_as_external_runtime_dependencies():
    content = read_text(REPO_ROOT / "scripts" / "release" / "deploy-release-image.ps1")
    for token in (
        "volume_defs = []",
        "seen_named_volumes = set()",
        'if mtype == "volume" and source_path not in seen_named_volumes:',
        'volume_defs.append(f"  {source_path}:")',
        'volume_defs.append("    external: true")',
        'compose_lines.append("volumes:")',
        "compose_lines.extend(volume_defs)",
    ):
        assert token in content


def test_rollback_script_defaults_to_dry_run_and_supports_real_rollback():
    content = read_text(REPO_ROOT / "scripts" / "release" / "rollback-release.ps1")
    for token in (
        "GO_ROLLBACK",
        "legacy_fallback",
        "dry_run = $true",
        "rollback_plan",
        "rollback_image_identity",
        "rollback_verification_manifest_path",
        "verify-production-release.ps1",
        "compose_config_files",
        "compose_working_dir",
        "docker compose -f $(Quote-PosixShellArgument $rollbackComposeFile) up -d --no-deps --force-recreate",
        "image ID does not match the rollback image ID",
    ):
        assert token in content
    assert "Real rollback execution is not enabled in this Sprint" not in content


def test_rollback_script_restores_app_before_scheduler():
    content = read_text(REPO_ROOT / "scripts" / "release" / "rollback-release.ps1")
    assert_tokens_in_order(
        content,
        "Assert-OwnerGate -Provided $OwnerGate -Expected 'GO_ROLLBACK'",
        "$appComposeService = if ([string]::IsNullOrWhiteSpace($appBefore.compose_service)) { $layout.app_service_name } else { $appBefore.compose_service }",
        "$rollbackComposeFile = if ([string]::IsNullOrWhiteSpace($schedulerBefore.compose_config_files)) { (Join-RemotePath $layout.compose_directory 'docker-compose.release.yml') } else { $schedulerBefore.compose_config_files }",
        "$composeEnvPrefix = Get-RemoteComposeEnvironmentPrefix -ImageTag $rollbackImageTag -DatabaseComponents $databaseComponents",
        "Invoke-RemoteText $rollbackAppCommand",
        "Invoke-RemoteText $rollbackSchedulerCommand",
        'Invoke-RemoteText "docker restart $(Quote-PosixShellArgument $layout.nginx_service_name)"',
    )


def test_verify_script_includes_e24a_and_premium_weekly_checks():
    content = read_text(REPO_ROOT / "scripts" / "release" / "verify-production-release.ps1")
    for token in (
        "SELFTEST OK (10/10)",
        "premium_weekly_default",
        "fail_observable_code_present",
        "shadow_verdict_simple_absent",
        "Try-Get-RemoteReadinessReport",
        "legacy_fallback",
        "readiness",
        "questions",
        "daily_challenge_status",
        "exact release image ID",
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
