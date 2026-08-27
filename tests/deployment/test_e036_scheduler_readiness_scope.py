"""Focused E036 coverage for role-aware scheduler readiness."""

import base64
import json
import pathlib
import shutil
import subprocess

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
PREFLIGHT_SCRIPT = REPO_ROOT / "scripts" / "release" / "preflight-production.ps1"
RELEASE_TOOLING = REPO_ROOT / "scripts" / "release" / "ReleaseTooling.psm1"
SCHEDULER_PREFIX = "__GO_ODYSSEY_SCHEDULER_READINESS_V1__:"


def _source(path=PREFLIGHT_SCRIPT):
    return path.read_text(encoding="utf-8")


def _function_block(start, end):
    source = _source()
    start_index = source.index(start)
    end_index = source.index(end, start_index)
    return source[start_index:end_index]


def _run_ps(tmp_path, body):
    if shutil.which("powershell") is None:
        pytest.skip("Windows PowerShell is required for release tooling tests")
    script = tmp_path / "e036-scheduler-readiness.ps1"
    script.write_text(
        "[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)\n"
        "$ErrorActionPreference='Stop'\n"
        f"Import-Module '{RELEASE_TOOLING.as_posix()}' -Force -DisableNameChecking\n"
        + body,
        encoding="utf-8",
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert lines, result.stdout + result.stderr
    return json.loads(lines[-1])


def _scheduler_payload(*, ok=True):
    return {
        "ok": ok,
        "role": "scheduler",
        "app": {"git_sha": "a" * 40, "image_revision": "a" * 40},
        "database": {
            "identity": {
                "configured": True,
                "host": "db.internal",
                "port": 5432,
                "database": "go_odyssey",
                "user": "scheduler_probe",
                "password_present": True,
            },
            "reachable": True,
            "tables": {
                "users": {"ok": True},
                "review_log": {"ok": True},
                "user_stats": {"ok": True},
            },
            "failures": [],
        },
        "scheduler": {
            "entrypoint": {
                "path": "/app/scheduler.py",
                "present": True,
                "importable": True,
                "required": True,
            },
            "community_job": {
                "enabled": False,
                "module_present": False,
                "module_importable": False,
                "required": False,
                "operations_root": {
                    "required": False,
                    "path": "",
                    "ready": True,
                },
            },
            "premium_job": {
                "enabled": False,
                "supported": True,
                "required": False,
            },
        },
        "questions": {"required": False, "status": "not_required"},
        "static_root": {"required": False, "status": "not_required"},
        "shadow_events": {"required": False, "status": "not_required"},
        "failures": [] if ok else ["database connection failed"],
    }


def _run_scheduler_probe(tmp_path, payload):
    encoded = base64.b64encode(
        (SCHEDULER_PREFIX + base64.b64encode(
            json.dumps(payload, separators=(",", ":")).encode("utf-8")
        ).decode("ascii")).encode("utf-8")
    ).decode("ascii")
    block = _function_block(
        "function Get-RemoteSchedulerReadinessReport",
        "function Resolve-RemoteRuntimeConfig",
    )
    # The outer base64 keeps the generated PowerShell probe free of quoting
    # surprises.  The function itself receives the framed JSON payload that a
    # real remote Python process would print.
    return _run_ps(
        tmp_path,
        f"$script:FakeOutput=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{encoded}'))\n"
        "$script:CapturedStdin=''\n"
        "$script:CapturedCommand=''\n"
        "function Invoke-RemoteCommandResult {\n"
        "    param([string]$Name,[string]$Command,[string]$ScriptText,[string]$StdinText)\n"
        "    $script:CapturedStdin=$StdinText\n"
        "    $script:CapturedCommand=$Command\n"
        "    return [ordered]@{stdout=$script:FakeOutput;stderr='';output=$script:FakeOutput;exit_code=0}\n"
        "}\n"
        + block
        + "$result=Get-RemoteSchedulerReadinessReport -ContainerName 'go-odyssey-scheduler' -ResponseName 'scheduler_probe'\n"
        + "[ordered]@{mode=$result.mode;ok=[bool]$result.report.ok;role=$result.report.role;questions_required=[bool]$result.report.questions.required;static_required=[bool]$result.report.static_root.required;shadow_required=[bool]$result.report.shadow_events.required;database_reachable=[bool]$result.report.database.reachable;entrypoint_present=[bool]$result.report.scheduler.entrypoint.present;captured_script=$script:CapturedStdin;captured_command=$script:CapturedCommand} | ConvertTo-Json -Compress\n",
    )


def test_scheduler_probe_is_role_specific_and_does_not_read_app_only_paths(tmp_path):
    result = _run_scheduler_probe(tmp_path, _scheduler_payload())

    assert result["mode"] == "scheduler_probe"
    assert result["ok"] is True
    assert result["role"] == "scheduler"
    assert result["database_reachable"] is True
    assert result["entrypoint_present"] is True
    assert result["questions_required"] is False
    assert result["static_required"] is False
    assert result["shadow_required"] is False
    assert "QUESTIONS_JSON_PATH" not in result["captured_script"]
    assert "GO_ODYSSEY_LIVE_STATIC_ROOT" not in result["captured_script"]
    assert "SHADOW_EVENTS_PATH" not in result["captured_script"]
    assert "_read_runtime_deployment_readiness" not in result["captured_script"]
    assert "Config.Env" not in result["captured_script"]
    assert "docker exec" in result["captured_command"]


def test_scheduler_probe_preserves_a_failing_scheduler_report_for_main_gate(tmp_path):
    result = _run_scheduler_probe(tmp_path, _scheduler_payload(ok=False))
    assert result["mode"] == "scheduler_probe"
    assert result["ok"] is False
    assert result["questions_required"] is False
    source = _source()
    assert "Scheduler runtime readiness probe reported a failing state." in source


def test_scheduler_probe_keeps_real_scheduler_database_requirements():
    block = _function_block(
        "function Get-RemoteSchedulerReadinessReport",
        "function Resolve-RemoteRuntimeConfig",
    )
    assert "conn.execute('SELECT 1')" in block
    assert "required_tables = ['users', 'review_log', 'user_stats']" in block
    assert "importlib.import_module(name)" in block
    assert "leaderboard_snapshots" in block
    assert "leaderboard_reward_claims" in block
    assert "leaderboard_reward_component_log" in block
    assert "scheduler entrypoint is unavailable" in block
    assert "community reward operations path is unavailable" in block


def test_scheduler_role_bypasses_app_readiness_helper(tmp_path):
    block = _function_block(
        "function Try-Get-RemoteReadinessReport",
        "function Get-RemoteSchedulerReadinessReport",
    )
    result = _run_ps(
        tmp_path=tmp_path,
        body=(
            "$script:Called=$false\n"
            "function Get-RemoteSchedulerReadinessReport { param([string]$ContainerName,[string]$ResponseName); $script:Called=$true; return [ordered]@{mode='scheduler_probe'} }\n"
            + block
            + "$result=Try-Get-RemoteReadinessReport -ContainerName 'scheduler' -ResponseName 'scheduler_probe' -Role 'scheduler'\n"
            + "[ordered]@{called=$script:Called;mode=$result.mode} | ConvertTo-Json -Compress\n"
        ),
    )
    assert result == {"called": True, "mode": "scheduler_probe"}


def test_scheduler_runtime_config_never_uses_exact_env_fallback(tmp_path):
    block = _function_block(
        "function Resolve-RemoteSchedulerRuntimeConfig",
        "function Get-RemoteQuestionsReport",
    )
    result = _run_ps(
        tmp_path,
        "function Get-RemoteExactEnvValue { throw 'exact env fallback must not run' }\n"
        + block
        + "$mode=[pscustomobject]@{mode='scheduler_probe';report=[pscustomobject]@{database=[pscustomobject]@{identity=[pscustomobject]@{configured=$true;host='db';port=5432;database='go';user='u';password_present=$true}}}}\n"
        + "$result=Resolve-RemoteSchedulerRuntimeConfig -ContainerName 'scheduler' -ContainerLabel 'Scheduler' -ResponsePrefix 'scheduler' -ReadinessMode $mode\n"
        + "[ordered]@{database=$result.database_identity.database;questions_source=$result.questions_path_source;questions=$null -eq $result.questions_path;static=$null -eq $result.live_static_root;shadow=$null -eq $result.shadow_events_path} | ConvertTo-Json -Compress\n",
    )
    assert result == {
        "database": "go",
        "questions_source": "not_required",
        "questions": True,
        "static": True,
        "shadow": True,
    }


def test_preflight_source_has_one_minimized_boundary_and_no_full_env_reader():
    source = _source()
    assert "function Get-RemoteContainerEnvMap" not in source
    assert "{{json .Config.Env}}" not in source
    assert source.count("function Get-RemoteExactEnvValue") == 1
    assert "-Role 'scheduler'" in source
    assert "function Get-RemoteSchedulerReadinessReport" in source
    assert "function Resolve-RemoteSchedulerRuntimeConfig" in source
    assert "'questions': {'required': False, 'status': 'not_required'}" in source
    assert "'static_root': {'required': False, 'status': 'not_required'}" in source
    assert "'shadow_events': {'required': False, 'status': 'not_required'}" in source


def test_preflight_dry_run_still_parses_and_preserves_layout_contract(tmp_path):
    if shutil.which("powershell") is None:
        pytest.skip("Windows PowerShell is required for release script tests")
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(PREFLIGHT_SCRIPT),
            "-DryRun",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["dry_run"] is True
    assert report["scheduler_service_name"] == "go-odyssey-scheduler"
