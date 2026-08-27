"""Focused regression coverage for E035 preflight environment minimization."""

import base64
import json
import pathlib
import shutil
import subprocess

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
PREFLIGHT_SCRIPT = REPO_ROOT / "scripts" / "release" / "preflight-production.ps1"
RELEASE_TOOLING = REPO_ROOT / "scripts" / "release" / "ReleaseTooling.psm1"
READINESS_PREFIX = "__GO_ODYSSEY_READINESS_V1__:"


def read_text(path):
    return path.read_text(encoding="utf-8")


def run_ps(tmp_path, body):
    if shutil.which("powershell") is None:
        pytest.fail("Windows PowerShell 5.1 is required")
    script = tmp_path / "e035-probe.ps1"
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
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def function_block(start, end):
    source = read_text(PREFLIGHT_SCRIPT)
    start_index = source.index(start)
    end_index = source.index(end, start_index)
    return source[start_index:end_index]


def run_exact_key_probe(tmp_path, output, key="QUESTIONS_JSON_PATH"):
    output_b64 = base64.b64encode(output.encode("utf-8")).decode("ascii")
    block = function_block(
        "function Get-RemoteExactEnvValue",
        "function Get-Sha256Hex",
    )
    return run_ps(
        tmp_path,
        "$script:ExactRemoteEnvKeys=@('DATABASE_URL','QUESTIONS_JSON_PATH','GO_ODYSSEY_LIVE_STATIC_ROOT','SHADOW_EVENTS_PATH')\n"
        f"$script:FakeRemoteOutput=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{output_b64}'))\n"
        "$script:CapturedCommands=@()\n"
        "function Invoke-RemoteText { param([string]$Name,[string]$Command); $script:CapturedCommands += $Command; return $script:FakeRemoteOutput }\n"
        + block
        + "try {\n"
        + f"  $value=Get-RemoteExactEnvValue -ContainerName 'app-current' -Key '{key}' -ResponseName 'app_key'\n"
        + "  [ordered]@{ok=$true; value=$value; value_is_null=($null -eq $value); command_count=$script:CapturedCommands.Count; command=$script:CapturedCommands[0]} | ConvertTo-Json -Compress\n"
        + "} catch {\n"
        + "  [ordered]@{ok=$false; error=$_.Exception.Message; command_count=$script:CapturedCommands.Count; command=$script:CapturedCommands[0]} | ConvertTo-Json -Compress\n"
        + "}\n",
    )


def test_preflight_has_no_full_environment_reader_and_covers_both_containers():
    source = read_text(PREFLIGHT_SCRIPT)
    assert "function Get-RemoteContainerEnvMap" not in source
    assert "Get-RemoteContainerEnvMap" not in source
    assert "{{json .Config.Env}}" not in source
    assert source.count("function Get-RemoteExactEnvValue") == 1
    assert "Try-Get-RemoteReadinessReport -ContainerName $layout.app_service_name -ResponseName 'app_helper_readiness'" in source
    assert "Try-Get-RemoteReadinessReport -ContainerName $layout.scheduler_service_name -ResponseName 'scheduler_helper_readiness'" in source
    assert "-ResponsePrefix 'app'" in source
    assert "-ResponsePrefix 'scheduler'" in source


def test_exact_key_probe_reads_one_allowlisted_key_only(tmp_path):
    result = run_exact_key_probe(
        tmp_path, "QUESTIONS_JSON_PATH=/app/data/questions.json\n"
    )
    assert result["ok"] is True
    assert result["value"] == "/app/data/questions.json"
    assert result["command_count"] == 1
    assert "{{json .Config.Env}}" not in result["command"]
    assert 'hasPrefix . "QUESTIONS_JSON_PATH="' in result["command"]


def test_unset_optional_exact_key_is_available_for_layout_fallback(tmp_path):
    result = run_exact_key_probe(tmp_path, "")
    assert result["ok"] is True
    assert result["value_is_null"] is True
    assert result["command_count"] == 1


def test_unallowlisted_key_is_rejected_before_remote_probe(tmp_path):
    result = run_exact_key_probe(tmp_path, "SECRET_KEY=must-not-leak\n", key="SECRET_KEY")
    assert result["ok"] is False
    assert "not allow-listed" in result["error"]
    assert "must-not-leak" not in result["error"]
    assert result["command_count"] == 0


@pytest.mark.parametrize(
    ("output", "error_fragment"),
    [
        ("QUESTIONS_JSON_PATH\n", "malformed entry"),
        ("QUESTIONS_JSON_PATH=\n", "empty value"),
        (
            "QUESTIONS_JSON_PATH=/safe/one\nQUESTIONS_JSON_PATH=/safe/two\n",
            "duplicated or ambiguous",
        ),
        ("OTHER_ENV=must-not-leak\n", "malformed entry"),
    ],
    ids=["missing-equals", "empty", "duplicate", "unexpected-key"],
)
def test_malformed_duplicate_and_ambiguous_exact_key_results_fail_closed(
    tmp_path, output, error_fragment
):
    result = run_exact_key_probe(tmp_path, output)
    assert result["ok"] is False
    assert error_fragment in result["error"]
    assert "must-not-leak" not in result["error"]
    assert "/safe/one" not in result["error"]
    assert "/safe/two" not in result["error"]
    assert result["command_count"] == 1


def test_empty_required_database_key_fails_closed_without_leaking_values(tmp_path):
    block = function_block(
        "function Get-RemoteExactEnvValue",
        "function Get-RemoteQuestionsReport",
    )
    result = run_ps(
        tmp_path,
        "$script:ExactRemoteEnvKeys=@('DATABASE_URL','QUESTIONS_JSON_PATH','GO_ODYSSEY_LIVE_STATIC_ROOT','SHADOW_EVENTS_PATH')\n"
        "$script:FakeOutputs=@{app_DATABASE_URL='';app_QUESTIONS_JSON_PATH='';app_GO_ODYSSEY_LIVE_STATIC_ROOT='';app_SHADOW_EVENTS_PATH=''}\n"
        "function Invoke-RemoteText { param([string]$Name,[string]$Command); return $script:FakeOutputs[$Name] }\n"
        + block
        + "$mode=[ordered]@{mode='legacy_fallback';report=$null}\n"
        + "try {\n"
        + "  Resolve-RemoteRuntimeConfig -ContainerName 'app-current' -ContainerLabel 'App' -ResponsePrefix 'app' -ReadinessMode $mode -ExpectedQuestionsPath '/layout/questions.json' | Out-Null\n"
        + "  [ordered]@{ok=$true} | ConvertTo-Json -Compress\n"
        + "} catch {\n"
        + "  [ordered]@{ok=$false;error=$_.Exception.Message} | ConvertTo-Json -Compress\n"
        + "}\n",
    )
    assert result["ok"] is False
    assert "DATABASE_URL is unavailable" in result["error"]
    assert "postgres" not in result["error"].lower()


def test_helper_mode_does_not_call_exact_key_fallback(tmp_path):
    payload = {
        "ok": True,
        "app": {"git_sha": "a" * 40},
        "questions": {"path": "/helper/questions.json"},
        "database": {
            "identity": {
                "configured": True,
                "host": "db.internal",
                "port": 5432,
                "database": "go_odyssey",
                "user": "release-check",
                "password_present": True,
            }
        },
        "static_root": {"path": "/static/current"},
        "shadow_events": {"path": "/data/shadow_events.jsonl"},
        "failures": [],
    }
    raw = READINESS_PREFIX + base64.b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")
    output_b64 = base64.b64encode(raw.encode("utf-8")).decode("ascii")
    block = function_block(
        "function Test-HelperUnavailableOutput",
        "function Get-RemoteQuestionsReport",
    )
    result = run_ps(
        tmp_path,
        f"$script:FakeHelperOutput=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{output_b64}'))\n"
        "$script:ExactProbeCalls=0\n"
        "$layout=[pscustomobject]@{ssh_alias='test-host'}\n"
        "function Invoke-BoundedSshCommand { param([string]$SshAlias,[string]$Command,[int]$TimeoutSeconds,[string]$OperationLabel); [ordered]@{stdout=$script:FakeHelperOutput;stderr='';output=$script:FakeHelperOutput;exit_code=0} }\n"
        "function Invoke-RemoteText { $script:ExactProbeCalls += 1; throw 'exact probe must not run in helper mode' }\n"
        + block
        + "$mode=Try-Get-RemoteReadinessReport -ContainerName 'app-current' -ResponseName 'app_helper_readiness'\n"
        + "$resolved=Resolve-RemoteRuntimeConfig -ContainerName 'app-current' -ContainerLabel 'App' -ResponsePrefix 'app' -ReadinessMode $mode -ExpectedQuestionsPath '/layout/questions.json'\n"
        + "[ordered]@{mode=$mode.mode;path=$resolved.questions_path;exact_probe_calls=$script:ExactProbeCalls} | ConvertTo-Json -Compress\n",
    )
    assert result == {
        "mode": "helper",
        "path": "/helper/questions.json",
        "exact_probe_calls": 0,
    }


def test_app_and_scheduler_use_the_same_minimized_readiness_boundary():
    source = read_text(PREFLIGHT_SCRIPT)
    assert 'ResponseName ("{0}_DATABASE_URL" -f $ResponsePrefix)' in source
    assert 'ResponseName ("{0}_QUESTIONS_JSON_PATH" -f $ResponsePrefix)' in source
    assert 'ResponseName ("{0}_GO_ODYSSEY_LIVE_STATIC_ROOT" -f $ResponsePrefix)' in source
    assert 'ResponseName ("{0}_SHADOW_EVENTS_PATH" -f $ResponsePrefix)' in source
    assert "-ResponsePrefix 'app'" in source
    assert "-ResponsePrefix 'scheduler'" in source
    assert "{{json .Config.Env}}" not in source
