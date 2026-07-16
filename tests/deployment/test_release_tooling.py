"""Validate the release tooling added for DEPLOY-GOV-3."""
import json
import os
import pathlib
import shutil
import subprocess

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
RELEASE_SCRIPTS = [
    REPO_ROOT / "scripts" / "release" / "ReleaseTooling.psm1",
    REPO_ROOT / "scripts" / "build-production-image.ps1",
    REPO_ROOT / "scripts" / "release" / "build-release-image.ps1",
    REPO_ROOT / "scripts" / "release" / "package-release-image.ps1",
    REPO_ROOT / "scripts" / "release" / "preflight-production.ps1",
    REPO_ROOT / "scripts" / "release" / "deploy-release-image.ps1",
    REPO_ROOT / "scripts" / "release" / "verify-production-release.ps1",
    REPO_ROOT / "scripts" / "release" / "rollback-release.ps1",
]
BUILD_PRODUCTION_IMAGE_SCRIPT = REPO_ROOT / "scripts" / "build-production-image.ps1"


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
        "static_current_target": {
            "stdout": "/opt/go-odyssey-static/releases/20260710-163737-0d8407496-v177-sgf-fe-hotfix1a-node-parser"
        },
        "static_current_files": {
            "stdout": (
                "bf84cca277addbdc408e83c55e93559cdb94e710b0a68fe8e43a9ea64c6e672a  "
                "/opt/go-odyssey-static/releases/20260710-163737-0d8407496-v177-sgf-fe-hotfix1a-node-parser/i18n.js\n"
                "150e0ecbef379637c48d53a6e43c20a6610dc384e1adf782a674e8775f9b4aed  "
                "/opt/go-odyssey-static/releases/20260710-163737-0d8407496-v177-sgf-fe-hotfix1a-node-parser/sw.js"
            )
        },
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


def run_module_probe(tmp_path, probe_body):
    """Run a small PowerShell script that imports ReleaseTooling.psm1 and executes probe_body."""
    script = tmp_path / "probe.ps1"
    module_path = str(REPO_ROOT / "scripts" / "release" / "ReleaseTooling.psm1")
    script.write_text(
        # Some PowerShell/.NET built-in exception messages (e.g. ConvertFrom-Json's
        # own parse-error text) are localized to the OS display language. Forcing
        # UTF-8 output here means that localized text -- wherever a probe
        # intentionally surfaces it -- round-trips as valid UTF-8 instead of
        # being emitted in the console's active code page (e.g. cp950/Big5 on a
        # zh-TW host), which a strict UTF-8 reader (python -X utf8) can't decode.
        "[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)\n"
        "$ErrorActionPreference = 'Stop'\n"
        f"Import-Module '{module_path}' -Force -DisableNameChecking\n" + probe_body,
        encoding="utf-8",
    )
    return subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def run_preflight_with_fake_remote(tmp_path, fake_remote_payload, static_manifest=None):
    fake_remote_path = tmp_path / "fake-remote.json"
    archive_path = tmp_path / "release.tar"
    archive_path.write_bytes(b"artifact")
    write_json(fake_remote_path, fake_remote_payload)
    env = os.environ.copy()
    env["GO_ODYSSEY_PREFLIGHT_FAKE_REMOTE_RESPONSES"] = str(fake_remote_path)
    command = [
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
        ]
    if static_manifest is not None:
        static_manifest_path = tmp_path / "static-manifest.json"
        write_json(static_manifest_path, static_manifest)
        command.extend(["-StaticManifest", str(static_manifest_path)])
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    return result


def make_static_manifest(files=None):
    return {
        "static_generation_id": "test-full-generation",
        "files": files
        if files is not None
        else [
            {
                "path": "i18n.js",
                "sha256": "bf84cca277addbdc408e83c55e93559cdb94e710b0a68fe8e43a9ea64c6e672a",
            },
            {
                "path": "sw.js",
                "sha256": "150e0ecbef379637c48d53a6e43c20a6610dc384e1adf782a674e8775f9b4aed",
            },
            {
                "path": "assets/storyboards/nested/scene 01.mp3",
                "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            },
        ],
    }


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
            "QUESTIONS_CONTENT_VOLUME_NAME": "go-odyssey_go-data",
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


def test_release_compose_uses_external_named_volume_for_questions_data():
    content = read_text(REPO_ROOT / "docker-compose.release.yml")
    assert "QUESTIONS_CONTENT_SOURCE_PATH" not in content
    assert "QUESTIONS_CONTENT_VOLUME_NAME" in content
    assert content.count("go-data:${QUESTIONS_CONTENT_MOUNT_DESTINATION") == 2
    assert "  go-data:\n    external: true\n    name: ${QUESTIONS_CONTENT_VOLUME_NAME" in content


def test_build_script_uses_clean_tree_and_detached_worktree():
    content = read_text(REPO_ROOT / "scripts" / "release" / "build-release-image.ps1")
    for token in ("Assert-TrackedTreeClean", "New-DetachedWorktree", "shadow_judging.py --selftest", "py_compile"):
        assert token in content


def test_canonical_build_uses_exit_code_native_helper_for_stderr_safe_execution():
    release_content = read_text(REPO_ROOT / "scripts" / "release" / "build-release-image.ps1")
    image_content = read_text(BUILD_PRODUCTION_IMAGE_SCRIPT)
    assert "Invoke-BoundedNativeCommand" in release_content
    assert "-OperationLabel 'canonical production image build script'" in release_content
    assert "$buildResult.exit_code -ne 0" in release_content
    assert "Invoke-BoundedNativeCommand" in image_content
    assert "-OperationLabel 'canonical production image build'" in image_content
    assert "$buildResult.exit_code -ne 0" in image_content
    assert "docker buildx build `" not in image_content


def test_invoke_git_treats_native_stderr_as_diagnostic_and_checks_exit_code():
    content = read_text(REPO_ROOT / "scripts" / "release" / "ReleaseTooling.psm1")
    assert "2> $stderrPath" in content
    assert "$previousErrorActionPreference = $ErrorActionPreference" in content
    assert "$ErrorActionPreference = 'Continue'" in content
    assert "$ErrorActionPreference = $previousErrorActionPreference" in content
    assert "$exitCode = $LASTEXITCODE" in content
    assert "if ($exitCode -ne 0)" in content


def test_detached_worktree_cleanup_uses_checked_git_helper():
    content = read_text(REPO_ROOT / "scripts" / "release" / "ReleaseTooling.psm1")
    assert "Invoke-Git -Arguments @('worktree', 'remove', '--force', $Path)" in content
    assert "& git worktree remove --force $Path" not in content


# ---------------------------------------------------------------------------
# RELEASE-TOOLING-HOTFIX-02: ARM64 build contract
# ---------------------------------------------------------------------------
#
# Root cause this closes: scripts/build-production-image.ps1 used a plain
# `docker build` with no --platform flag, which always targets the local
# Docker daemon's native platform. Run from a Windows/amd64 machine, this
# silently produced a linux/amd64 image with no error, even though
# production runs on real aarch64 hardware (confirmed directly via
# `ssh <prod> uname -m`, not assumed). The wrong-architecture image was only
# ever going to be caught by deploy-release-image.ps1's -ExpectedPlatform
# check, i.e. much later, right before an actual deploy attempt -- this
# closes the gap at build time instead.

def test_build_script_uses_buildx_not_plain_docker_build():
    content = read_text(BUILD_PRODUCTION_IMAGE_SCRIPT)
    assert "docker buildx build" in content
    # a bare `docker build` invocation (as an actual executed statement, at
    # the start of a line -- not mentioned in prose/comments explaining what
    # NOT to do) must not remain anywhere
    import re
    executable_lines = [
        line for line in content.splitlines()
        if re.match(r"^\s*docker build\b", line) and "buildx" not in line
    ]
    assert executable_lines == [], (
        f"no plain `docker build` invocation may remain (found: {executable_lines}) "
        "-- it cannot cross-build for a non-native platform"
    )


def test_build_script_default_platform_contract_is_arm64():
    content = read_text(BUILD_PRODUCTION_IMAGE_SCRIPT)
    assert "[string]$Platform = 'linux/arm64'" in content


def test_build_script_platform_is_an_overridable_parameter():
    content = read_text(BUILD_PRODUCTION_IMAGE_SCRIPT)
    # It must be a real parameter (so `-Platform` on the command line is the
    # only way to change it -- not, say, an environment variable read
    # implicitly, and not hardcoded inline at the buildx call site).
    assert "param(" in content
    param_block = content[content.index("param("):content.index("param(") + 400]
    assert "$Platform" in param_block
    assert "--platform $Platform" in content


def test_build_script_passes_explicit_platform_to_buildx():
    content = read_text(BUILD_PRODUCTION_IMAGE_SCRIPT)
    assert "--platform $Platform" in content
    assert "--load" in content


def test_build_script_has_capability_preflight_before_building():
    content = read_text(BUILD_PRODUCTION_IMAGE_SCRIPT)
    assert "docker buildx version" in content
    assert "docker buildx inspect" in content
    # must fail, not warn-and-continue, when the builder doesn't support it
    assert "does not report support for" in content
    assert "Fail " in content or "Fail(" in content


def test_build_script_verifies_platform_immediately_after_build():
    content = read_text(BUILD_PRODUCTION_IMAGE_SCRIPT)
    assert "Get-ImagePlatform -ImageTag $imageTag" in content
    build_pos = content.index("docker buildx build")
    verify_pos = content.index("Get-ImagePlatform -ImageTag $imageTag")
    assert build_pos < verify_pos, "platform must be verified AFTER the build, not before"


def test_build_script_fails_closed_on_platform_mismatch():
    content = read_text(BUILD_PRODUCTION_IMAGE_SCRIPT)
    assert "$actualPlatform -ne $Platform" in content
    mismatch_check_pos = content.index("$actualPlatform -ne $Platform")
    # the very next non-blank construct after the mismatch check must be a Fail call
    snippet = content[mismatch_check_pos:mismatch_check_pos + 200]
    assert "Fail " in snippet or "Fail(" in snippet


def test_build_script_has_no_silent_fallback_between_capability_check_and_build():
    content = read_text(BUILD_PRODUCTION_IMAGE_SCRIPT)
    # Anchor on the section marker and the EXECUTABLE buildx invocation (not
    # its mention in the docstring earlier in the file, which would make a
    # naive first-index slice empty/reversed).
    section_start = content.index("docker buildx version")
    build_invocation_pos = content.index("docker buildx build `")
    capability_section = content[section_start:build_invocation_pos]
    assert "docker buildx version" in capability_section
    # the buildx capability checks themselves must not swallow failures
    # (Get-Command docker -ErrorAction SilentlyContinue, earlier in the
    # section, is a separate and legitimate "is docker installed at all"
    # check -- excluded from this section's slice by starting at
    # "docker buildx version" instead of the section's comment header)
    assert "-ErrorAction SilentlyContinue" not in capability_section
    # There must be no alternate/fallback branch that proceeds with a plain
    # `docker build` (or continues past a capability failure) -- the only
    # acceptable outcomes in this section are: buildx + arm64 support
    # confirmed, or Fail().
    assert capability_section.count("Fail ") + capability_section.count("Fail(") >= 2


def test_shared_get_image_platform_helper_exists_and_is_exported():
    module_content = read_text(REPO_ROOT / "scripts" / "release" / "ReleaseTooling.psm1")
    assert "function Get-ImagePlatform" in module_content
    assert "{{.Os}}/{{.Architecture}}" in module_content
    assert "'Get-ImagePlatform'" in module_content
    build_content = read_text(BUILD_PRODUCTION_IMAGE_SCRIPT)
    assert "Import-Module" in build_content
    assert "ReleaseTooling.psm1" in build_content


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
        "docker exec -i $ContainerName python -X utf8 -",
    ):
        assert token in content
    assert '{{with index .State "Health"}}{{index . "Status"}}{{end}}' in content
    assert "docker compose up" not in content
    assert "docker push" not in content
    # RELEASE-TOOLING-HOTFIX-01: preflight no longer implements its own
    # ssh/stdin piping -- it must delegate to the shared module helper.
    assert "Invoke-RemoteShellCommand" in content
    assert '-replace "`r`n", "`n" -replace "`r", "`n"' not in content
    assert "[System.Management.Automation.ErrorRecord]" not in content


def test_release_tooling_module_owns_the_stdin_piping_implementation():
    # RELEASE-TOOLING-HOTFIX-01: the ssh/stdin piping logic (and its
    # UTF-8-no-BOM fix) must live exactly once, in the shared module --
    # not duplicated across preflight/deploy/rollback/verify scripts.
    module_content = read_text(REPO_ROOT / "scripts" / "release" / "ReleaseTooling.psm1")
    assert "function Invoke-RemoteShellCommand" in module_content
    assert "function ConvertTo-Utf8NoBomLfBytes" in module_content
    assert '-replace "`r`n", "`n" -replace "`r", "`n"' in module_content
    assert "[System.Management.Automation.ErrorRecord]" in module_content
    assert "System.Text.UTF8Encoding($false)" in module_content
    assert "'Invoke-RemoteShellCommand'" in module_content
    assert "'ConvertTo-Utf8NoBomLfBytes'" in module_content

    for script_name in (
        "preflight-production.ps1",
        "deploy-release-image.ps1",
        "rollback-release.ps1",
        "verify-production-release.ps1",
    ):
        script_content = read_text(REPO_ROOT / "scripts" / "release" / script_name)
        assert "Invoke-RemoteShellCommand" in script_content, (
            f"{script_name} must delegate to the shared stdin-piping helper"
        )
        assert script_content.count("| & ssh ") == 0, (
            f"{script_name} must not re-implement its own ssh stdin pipe"
        )


def test_preflight_uses_helper_when_runtime_helper_is_available(tmp_path):
    payload = make_fake_preflight_responses(helper_mode="helper")
    payload["responses"].pop("questions_report")
    result = run_preflight_with_fake_remote(tmp_path, payload)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["readiness_mode"] == "helper"
    assert report["helper_available"] is True
    assert report["questions"]["record_count"] == 321


def test_preflight_full_static_manifest_requires_complete_observation(tmp_path):
    payload = make_fake_preflight_responses()
    payload["responses"]["static_current_manifest_files"] = {
        "stdout": "i18n.js: OK\nsw.js: OK"
    }
    result = run_preflight_with_fake_remote(
        tmp_path, payload, static_manifest=make_static_manifest()
    )
    assert result.returncode != 0
    assert "STATIC GENERATION DRIFT" in (result.stdout + result.stderr)


def test_preflight_full_static_manifest_accepts_complete_nested_observation(tmp_path):
    payload = make_fake_preflight_responses()
    payload["responses"]["static_current_manifest_files"] = {
        "stdout": (
            "i18n.js: OK\n"
            "sw.js: OK\n"
            "assets/storyboards/nested/scene 01.mp3: OK"
        )
    }
    result = run_preflight_with_fake_remote(
        tmp_path, payload, static_manifest=make_static_manifest()
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["static_generation"]["drift_checked"] is True
    assert report["static_generation"]["drift"] is False
    assert [entry["path"] for entry in report["static_generation"]["files"]] == [
        "i18n.js",
        "sw.js",
        "assets/storyboards/nested/scene 01.mp3",
    ]


def test_preflight_full_static_manifest_normalizes_windows_separators(tmp_path):
    manifest = make_static_manifest()
    manifest["files"][2]["path"] = r"assets\storyboards\nested\scene 01.mp3"
    payload = make_fake_preflight_responses()
    payload["responses"]["static_current_manifest_files"] = {
        "stdout": (
            "i18n.js: OK\n"
            "sw.js: OK\n"
            "assets/storyboards/nested/scene 01.mp3: OK"
        )
    }
    result = run_preflight_with_fake_remote(
        tmp_path, payload, static_manifest=manifest
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_preflight_full_static_manifest_rejects_path_escape(tmp_path):
    manifest = make_static_manifest(
        [
            {
                "path": "../outside.txt",
                "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            }
        ]
    )
    payload = make_fake_preflight_responses()
    payload["responses"]["static_current_manifest_files"] = {
        "stdout": "../outside.txt: OK"
    }
    result = run_preflight_with_fake_remote(
        tmp_path, payload, static_manifest=manifest
    )
    assert result.returncode != 0
    assert "path traversal" in (result.stdout + result.stderr).lower()


def test_preflight_full_static_manifest_fails_on_missing_or_mismatch(tmp_path):
    for label, output in (
        ("missing", "i18n.js: OK\nsw.js: OK\nassets/storyboards/nested/scene 01.mp3: FAILED open or read"),
        ("mismatch", "i18n.js: OK\nsw.js: FAILED\nassets/storyboards/nested/scene 01.mp3: OK"),
    ):
        case_dir = tmp_path / label
        case_dir.mkdir()
        payload = make_fake_preflight_responses()
        payload["responses"]["static_current_manifest_files"] = {
            "stdout": output,
            "exit_code": 1,
        }
        result = run_preflight_with_fake_remote(
            case_dir, payload, static_manifest=make_static_manifest()
        )
        assert result.returncode != 0
        assert "STATIC GENERATION DRIFT" in (result.stdout + result.stderr)


def test_preflight_full_static_manifest_rejects_empty_manifest(tmp_path):
    payload = make_fake_preflight_responses()
    payload["responses"]["static_current_manifest_files"] = {"stdout": ""}
    result = run_preflight_with_fake_remote(
        tmp_path, payload, static_manifest=make_static_manifest([])
    )
    assert result.returncode != 0
    assert "at least one file" in (result.stdout + result.stderr)


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
        "Assert-ProtectedHostEnvCredentialAndTcpAuthentication -SshAlias $layout.ssh_alias -EnvPath $layout.production_env_path -PostgresContainerName $layout.postgres_service_name",
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
        'Invoke-RemoteText "cd $(Quote-PosixShellArgument $layout.compose_directory) && $composeEnvPrefix docker compose $composeEnvFileArg -f docker-compose.release.yml -f $(Quote-PosixShellArgument $remoteHealthcheckOverridePath) up -d --no-build --no-deps --force-recreate $appComposeService"',
        'Invoke-RemoteText "cd $(Quote-PosixShellArgument $layout.compose_directory) && $composeEnvPrefix docker compose $composeEnvFileArg -f docker-compose.release.yml -f $(Quote-PosixShellArgument $remoteHealthcheckOverridePath) up -d --no-build --no-deps --force-recreate $schedulerComposeService"',
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
        "$normalizedHealthcheckTest = @($HealthcheckTest)",
        "$normalizedHealthcheckTest.Count -eq 1",
        "$normalizedHealthcheckTest[0] -is [System.Collections.IEnumerable]",
        "if ($normalizedHealthcheckTest[0] -ne 'CMD')",
        "if ($normalizedHealthcheckTest[1] -ne 'python')",
        "if ($normalizedHealthcheckTest[2] -ne '-c')",
        "127\\.0\\.0\\.1:8080/healthz",
        "Assert-CanonicalExecHealthcheckTest -HealthcheckTest $candidateHealthcheckTest -Context 'Candidate canary'",
        "Assert-CanonicalExecHealthcheckTest -HealthcheckTest $appHealthcheckTest -Context 'App container'",
        "$remoteHealthcheckOverridePath",
        "docker-compose.release.healthcheck.override.yml",
    ):
        assert token in content


def test_container_local_http_probe_uses_python_not_curl():
    content = read_text(REPO_ROOT / "scripts" / "release" / "deploy-release-image.ps1")
    assert "docker exec $(Quote-PosixShellArgument $ContainerName) curl" not in content
    for token in (
        "docker exec -i $(Quote-PosixShellArgument $ContainerName) python - $(Quote-PosixShellArgument $url)",
        "urllib.request.urlopen",
        "urllib.error.HTTPError",
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
        "Wait-ForRemoteContainerHealth",
        "rollback_image_identity",
        "rollback_verification_manifest_path",
        "verify-production-release.ps1",
        "compose_config_files",
        "compose_working_dir",
        "docker compose $composeEnvFileArg -f $(Quote-PosixShellArgument $canonicalComposeFile) up -d --no-build --no-deps --force-recreate",
        "image ID does not match the rollback image ID",
    ):
        assert token in content
    assert "Real rollback execution is not enabled in this Sprint" not in content


def test_rollback_script_restores_app_before_scheduler():
    content = read_text(REPO_ROOT / "scripts" / "release" / "rollback-release.ps1")
    assert_tokens_in_order(
        content,
        "Assert-OwnerGate -Provided $OwnerGate -Expected 'GO_ROLLBACK'",
        "Assert-ProtectedHostEnvCredentialAndTcpAuthentication -SshAlias $layout.ssh_alias -EnvPath $layout.production_env_path -PostgresContainerName $layout.postgres_service_name",
        "$appComposeService = if ([string]::IsNullOrWhiteSpace($appBefore.compose_service)) { $layout.app_service_name } else { $appBefore.compose_service }",
        "$canonicalComposeFile = Join-RemotePath $layout.compose_directory 'docker-compose.release.yml'",
        "$composeEnvPrefix = Get-RemoteComposeEnvironmentPrefix -ImageTag $rollbackImageTag -QuestionsVolumeName $questionsVolumeName",
        "Invoke-RemoteText $rollbackAppCommand",
        "$appAfter = Wait-ForRemoteContainerHealth -ContainerName $layout.app_service_name",
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


def test_select_container_mount_for_destination_identifies_named_volume(tmp_path):
    mounts_json = json.dumps(
        [
            {"Type": "bind", "Source": "/opt/go-odyssey-static", "Destination": "/opt/go-odyssey-static"},
            {"Type": "volume", "Name": "go-odyssey_go-data", "Destination": "/app/data"},
        ]
    )
    probe = (
        f"$mounts = '{mounts_json}'\n"
        "$result = Select-ContainerMountForDestination -MountsJson $mounts -Destination '/app/data' -Context 'probe'\n"
        "Write-Output ($result.type)\n"
        "Write-Output ($result.name)\n"
    )
    result = run_module_probe(tmp_path, probe)
    assert result.returncode == 0, result.stdout + result.stderr
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    assert lines[0] == "volume"
    assert lines[1] == "go-odyssey_go-data"


def test_select_container_mount_for_destination_identifies_bind_mount(tmp_path):
    mounts_json = json.dumps([{"Type": "bind", "Source": "/opt/go-odyssey-data", "Destination": "/app/data"}])
    probe = (
        f"$mounts = '{mounts_json}'\n"
        "$result = Select-ContainerMountForDestination -MountsJson $mounts -Destination '/app/data' -Context 'probe'\n"
        "Write-Output ($result.type)\n"
        "Write-Output ($result.source)\n"
    )
    result = run_module_probe(tmp_path, probe)
    assert result.returncode == 0, result.stdout + result.stderr
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    assert lines[0] == "bind"
    assert lines[1] == "/opt/go-odyssey-data"


def test_select_container_mount_for_destination_fails_closed_when_missing(tmp_path):
    mounts_json = json.dumps([{"Type": "volume", "Name": "other", "Destination": "/somewhere/else"}])
    probe = (
        f"$mounts = '{mounts_json}'\n"
        "try { Select-ContainerMountForDestination -MountsJson $mounts -Destination '/app/data' -Context 'probe-container'; Write-Output 'NO_THROW' } "
        "catch { Write-Output \"THROWN:$($_.Exception.Message)\" }\n"
    )
    result = run_module_probe(tmp_path, probe)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "THROWN:" in result.stdout
    assert "probe-container" in result.stdout


def test_convert_from_nested_powershell_json_parses_multiline_array_output(tmp_path):
    # Regression test for the 2026-07-11 incident: a nested `& powershell -File`
    # invocation's stdout is captured as an ARRAY of per-line strings, and no
    # single line of a pretty-printed ConvertTo-Json payload is valid JSON on
    # its own. The real rollback record legitimately contains the substring
    # "time" (via build_timestamp/deployment_timestamp keys), which is exactly
    # what surfaced as "invalid JSON primitive: time" when the array was fed
    # straight into ConvertFrom-Json without being joined first.
    probe = (
        "$payload = @{ a = 1; note = 'time to celebrate'; nested = @{ b = @(1,2,3) } } | ConvertTo-Json -Depth 5\n"
        "$lines = $payload -split \"`n\"\n"
        "$parsed = ConvertFrom-NestedPowerShellJson -RawOutput $lines -Context 'probe'\n"
        "Write-Output ($parsed.a)\n"
        "Write-Output ($parsed.note)\n"
    )
    result = run_module_probe(tmp_path, probe)
    assert result.returncode == 0, result.stdout + result.stderr
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    assert lines[0] == "1"
    assert lines[1] == "time to celebrate"


def test_convert_from_nested_powershell_json_fails_closed_on_non_json_output(tmp_path):
    probe = (
        "try { ConvertFrom-NestedPowerShellJson -RawOutput @('not json at all', 'still not json') "
        "-Context 'child-script'; Write-Output 'NO_THROW' } "
        "catch { Write-Output \"THROWN:$($_.Exception.Message)\" }\n"
    )
    result = run_module_probe(tmp_path, probe)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "THROWN:" in result.stdout
    assert "child-script" in result.stdout
    assert "NO_THROW" not in result.stdout


def test_deploy_and_rollback_scripts_derive_questions_volume_at_runtime():
    deploy = read_text(REPO_ROOT / "scripts" / "release" / "deploy-release-image.ps1")
    rollback = read_text(REPO_ROOT / "scripts" / "release" / "rollback-release.ps1")
    for content in (deploy, rollback):
        assert "Get-RemoteQuestionsVolumeName" in content
        assert "Select-ContainerMountForDestination" in content
        assert "QuestionsVolumeName" in content
        assert "QUESTIONS_CONTENT_SOURCE_PATH" not in content
        assert "is not a named Docker volume" in content


def test_deploy_and_rollback_scripts_use_safe_nested_json_parsing():
    deploy = read_text(REPO_ROOT / "scripts" / "release" / "deploy-release-image.ps1")
    rollback = read_text(REPO_ROOT / "scripts" / "release" / "rollback-release.ps1")
    assert (
        "$verificationReport = ConvertFrom-NestedPowerShellJson -RawOutput $verificationOutput "
        "-Context 'verify-production-release.ps1'" in deploy
    )
    assert "ConvertFrom-NestedPowerShellJson -RawOutput $rollbackOutput -Context 'rollback-release.ps1'" in deploy
    assert (
        "$verificationReport = ConvertFrom-NestedPowerShellJson -RawOutput $verificationOutput "
        "-Context 'verify-production-release.ps1'" in rollback
    )
    assert "$verificationOutput | ConvertFrom-Json" not in deploy
    assert "$verificationOutput | ConvertFrom-Json" not in rollback
    assert "$rollbackOutput | ConvertFrom-Json" not in deploy


def test_convert_to_utf8_no_bom_lf_bytes_has_no_bom_and_normalizes_line_endings(tmp_path):
    # RELEASE-TOOLING-HOTFIX-01: pure byte-contract test, no process/ssh
    # involved -- this is what Invoke-RemoteShellCommand's stdin pipe must
    # match at runtime.
    probe = (
        "$bytes = ConvertTo-Utf8NoBomLfBytes -Text \"docker inspect foo`r`nsecond line`r`nthird`r`n\"\n"
        "Write-Output $bytes.Length\n"
        "Write-Output (($bytes[0..2] | ForEach-Object { $_.ToString('X2') }) -join '')\n"
        "$decoded = [System.Text.Encoding]::UTF8.GetString($bytes)\n"
        "Write-Output $decoded.Contains(\"`r`n\")\n"
        "Write-Output $decoded.Contains(\"`n\")\n"
        "Write-Output $decoded\n"
    )
    result = run_module_probe(tmp_path, probe)
    assert result.returncode == 0, result.stdout + result.stderr
    lines = result.stdout.replace("\r\n", "\n").split("\n")
    byte_length = int(lines[0])
    first_three_hex = lines[1]
    contains_crlf = lines[2].strip()
    contains_lf = lines[3].strip()
    decoded_text = "\n".join(lines[4:]).strip()
    assert byte_length > 0
    assert first_three_hex != "EFBBBF", "payload must not start with a UTF-8 BOM"
    assert first_three_hex == "646F63"  # 'd','o','c' -- first 3 bytes of "docker..."
    assert contains_crlf == "False", "CRLF must be normalized away"
    assert contains_lf == "True"
    assert decoded_text == "docker inspect foo\nsecond line\nthird"


def test_invoke_process_with_utf8_no_bom_stdin_sends_no_bom_over_a_real_pipe(tmp_path):
    # RELEASE-TOOLING-HOTFIX-01: end-to-end regression test on the actual
    # Windows PowerShell 5.1 host this bug manifested on. Spawns a REAL
    # child process (python.exe, running a script that copies its raw
    # stdin bytes to a file) via the shared Invoke-ProcessWithUtf8NoBomStdin
    # helper, then asserts on the literal bytes that arrived -- proving
    # the fix works end-to-end, not just that the byte-contract helper
    # (ConvertTo-Utf8NoBomLfBytes) is correct in isolation.
    #
    # Targets python.exe directly (by name, resolved via PATH) rather than
    # faking out `ssh` itself: System.Diagnostics.Process.Start with a
    # bare FileName only resolves .exe on classic .NET Framework (does not
    # search PATHEXT for .cmd/.bat the way cmd.exe does), so a `ssh.cmd`
    # stand-in placed earlier on PATH is silently skipped in favor of the
    # real system ssh.exe -- confirmed directly (it printed a real "Could
    # not resolve hostname" error from the genuine OpenSSH client).
    # Invoke-ProcessWithUtf8NoBomStdin takes -FileName as a parameter
    # specifically so this test can target a real, known executable
    # (python) instead of trying to shadow `ssh`.
    if shutil.which("python") is None:
        raise AssertionError("python is required for this stdin-capture test double")
    fake_capture_py = tmp_path / "capture_stdin.py"
    fake_capture_py.write_text(
        "import sys\n"
        "with open(sys.argv[1], 'wb') as f:\n"
        "    f.write(sys.stdin.buffer.read())\n",
        encoding="utf-8",
    )
    probe = (
        "$multiline = \"docker inspect foo`r`nsecond line`r`nthird line`r`n\"\n"
        f"$scriptArg = '{fake_capture_py}'\n"
        f"$outArg = '{tmp_path / 'captured.bin'}'\n"
        "$argsLine = '\"' + $scriptArg + '\" \"' + $outArg + '\"'\n"
        "$result = Invoke-ProcessWithUtf8NoBomStdin -FileName 'python' -Arguments $argsLine -StdinText $multiline\n"
        "Write-Output ('EXIT:' + $result.exit_code)\n"
    )
    result = run_module_probe(tmp_path, probe)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "EXIT:0" in result.stdout
    captured_path = tmp_path / "captured.bin"
    assert captured_path.exists(), "stdin-capture stand-in never received a pipe"
    captured = captured_path.read_bytes()
    assert captured[:3] != b"\xef\xbb\xbf", "stdin payload must not start with a UTF-8 BOM"
    assert captured[:6] == b"docker"
    assert b"\r\n" not in captured, "CRLF must be normalized to LF before piping"
    assert b"\n" in captured


def test_powershell7_compatibility_of_the_stdin_fix_is_documented_and_non_regressive(tmp_path):
    # pwsh (PowerShell 7) is not installed in this environment (confirmed:
    # `pwsh` is not on PATH here) -- this cannot be a live pwsh execution
    # test. Instead this verifies: (a) the fix uses only a standard .NET
    # API (System.Text.UTF8Encoding) with identical behavior on Windows
    # PowerShell 5.1 and PowerShell 7/Core, not a 5.1-only construct, and
    # (b) the compatibility rationale is documented in the module itself
    # so a future reader isn't left to re-derive it.
    module_content = read_text(REPO_ROOT / "scripts" / "release" / "ReleaseTooling.psm1")
    assert "PowerShell 7" in module_content
    assert "System.Text.UTF8Encoding($false)" in module_content
    # Guard against accidentally introducing a 5.1-only cmdlet/parameter
    # (e.g. -Encoding utf8NoBOM string literal, only valid on PS 6+) that
    # would silently diverge between hosts.
    assert "-Encoding utf8NoBOM" not in module_content


def test_release_scripts_parse_cleanly():
    for script in RELEASE_SCRIPTS:
        assert_powershell_parse_ok(script)
