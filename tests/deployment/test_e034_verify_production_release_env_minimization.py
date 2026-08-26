"""Regression coverage for E034's minimum-data readiness fallback."""

import base64
import json
import pathlib
import shutil
import subprocess

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "release" / "verify-production-release.ps1"
RELEASE_TOOLING = REPO_ROOT / "scripts" / "release" / "ReleaseTooling.psm1"
READINESS_PREFIX = "__GO_ODYSSEY_READINESS_V1__:"


def read_text(path):
    return path.read_text(encoding="utf-8")


def framed(payload):
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return READINESS_PREFIX + base64.b64encode(raw).decode("ascii")


def run_ps(tmp_path, body):
    if shutil.which("powershell") is None:
        pytest.fail("Windows PowerShell 5.1 is required")
    script = tmp_path / "e034-probe.ps1"
    script.write_text(
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
    source = read_text(VERIFY_SCRIPT)
    start_index = source.index(start)
    end_index = source.index(end, start_index)
    return source[start_index:end_index]


def run_exact_key_probe(tmp_path, output):
    output_b64 = base64.b64encode(output.encode("utf-8")).decode("ascii")
    block = function_block(
        "function Get-RemoteQuestionsJsonPath",
        "function Test-HelperUnavailableOutput",
    )
    return run_ps(
        tmp_path,
        f"$script:FakeRemoteOutput=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{output_b64}'))\n"
        "$script:CapturedCommands=@()\n"
        "function Invoke-RemoteText { param([string]$Command); $script:CapturedCommands += $Command; return $script:FakeRemoteOutput }\n"
        + block
        + "try {\n"
        + "  $value=Get-RemoteQuestionsJsonPath -ContainerName 'app-current'\n"
        + "  [ordered]@{ok=$true; value=$value; value_is_null=($null -eq $value); command_count=$script:CapturedCommands.Count; command=$script:CapturedCommands[0]} | ConvertTo-Json -Compress\n"
        + "} catch {\n"
        + "  [ordered]@{ok=$false; error=$_.Exception.Message; command_count=$script:CapturedCommands.Count; command=$script:CapturedCommands[0]} | ConvertTo-Json -Compress\n"
        + "}\n",
    )


def test_verify_removes_full_environment_reader_and_keeps_helper_first():
    source = read_text(VERIFY_SCRIPT)
    assert "function Get-RemoteContainerEnvMap" not in source
    assert "Get-RemoteContainerEnvMap" not in source
    assert "{{json .Config.Env}}" not in source
    assert "Get-RemoteQuestionsJsonPath" in source
    assert "Resolve-RemoteQuestionsReadiness" in source
    assert source.index("$readinessMode = Try-Get-RemoteReadinessReport") < source.index(
        "$questionsReadiness = Resolve-RemoteQuestionsReadiness"
    )
    assert "if ($ReadinessMode.mode -eq 'helper')" in source


def test_legacy_exact_key_probe_reads_one_allowlisted_key(tmp_path):
    result = run_exact_key_probe(tmp_path, "QUESTIONS_JSON_PATH=/app/data/questions.json\n")
    assert result["ok"] is True
    assert result["value"] == "/app/data/questions.json"
    assert result["command_count"] == 1
    assert "{{json .Config.Env}}" not in result["command"]
    assert 'hasPrefix . "QUESTIONS_JSON_PATH="' in result["command"]


def test_legacy_unset_exact_key_uses_null_for_layout_fallback(tmp_path):
    result = run_exact_key_probe(tmp_path, "")
    assert result["ok"] is True
    assert result["value_is_null"] is True
    assert result["command_count"] == 1


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
def test_legacy_exact_key_probe_fails_closed_without_echoing_values(
    tmp_path, output, error_fragment
):
    result = run_exact_key_probe(tmp_path, output)
    assert result["ok"] is False
    assert error_fragment in result["error"]
    assert "must-not-leak" not in result["error"]
    assert "/safe/one" not in result["error"]
    assert "/safe/two" not in result["error"]
    assert result["command_count"] == 1


def test_helper_mode_uses_questions_result_without_exact_key_probe(tmp_path):
    payload = {
        "ok": True,
        "app": {"git_sha": "a" * 40},
        "questions": {
            "configured_path": "/helper/questions.json",
            "parseable": True,
            "record_count_ok": True,
            "structural_record_check": True,
        },
        "database": {"reachable": True},
        "static_root": {"readable": True},
        "shadow_events": {"writable_or_valid": True},
        "failures": [],
    }
    output_b64 = base64.b64encode(framed(payload).encode("utf-8")).decode("ascii")
    block = function_block(
        "function Get-RemoteQuestionsJsonPath",
        "function Get-RemoteImageLabels",
    )
    result = run_ps(
        tmp_path,
        f"$script:FakeHelperOutput=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{output_b64}'))\n"
        "$script:ExactProbeCalls=0\n"
        "$layout=[pscustomobject]@{ssh_alias='test-host'}\n"
        "function Invoke-BoundedSshCommand { param([string]$SshAlias,[string]$Command,[int]$TimeoutSeconds,[string]$OperationLabel); [ordered]@{stdout=$script:FakeHelperOutput;stderr='';output=$script:FakeHelperOutput;exit_code=0} }\n"
        "function Invoke-RemoteText { $script:ExactProbeCalls += 1; throw 'exact probe must not run in helper mode' }\n"
        + block
        + "$mode=Try-Get-RemoteReadinessReport -ContainerName 'app-current'\n"
        + "$resolved=Resolve-RemoteQuestionsReadiness -ContainerName 'app-current' -ReadinessMode $mode -ExpectedQuestionsPath '/layout/questions.json'\n"
        + "[ordered]@{mode=$mode.mode; path=$resolved.path; report_path=$resolved.report.configured_path; exact_probe_calls=$script:ExactProbeCalls} | ConvertTo-Json -Compress\n",
    )
    assert result == {
        "mode": "helper",
        "path": "/helper/questions.json",
        "report_path": "/helper/questions.json",
        "exact_probe_calls": 0,
    }


def test_legacy_resolution_uses_one_exact_probe_then_layout_fallback(tmp_path):
    block = function_block(
        "function Get-RemoteQuestionsJsonPath",
        "function Get-RemoteImageLabels",
    )
    result = run_ps(
        tmp_path,
        "$script:CapturedCommands=@()\n"
        "function Invoke-RemoteText { param([string]$Command); $script:CapturedCommands += $Command; return '' }\n"
        + block
        + "function Get-RemoteQuestionsReport { param([string]$ContainerName,[string]$QuestionsPath); [pscustomobject]@{path=$QuestionsPath} }\n"
        + "$mode=[ordered]@{mode='legacy_fallback';report=$null}\n"
        + "$resolved=Resolve-RemoteQuestionsReadiness -ContainerName 'app-current' -ReadinessMode $mode -ExpectedQuestionsPath '/layout/questions.json'\n"
        + r"[ordered]@{path=$resolved.path; report_path=$resolved.report.path; exact_probe_calls=$script:CapturedCommands.Count; full_env=$($script:CapturedCommands -match '\{\{json \.Config\.Env\}\}').Count} | ConvertTo-Json -Compress"
        + "\n",
    )
    assert result == {
        "path": "/layout/questions.json",
        "report_path": "/layout/questions.json",
        "exact_probe_calls": 1,
        "full_env": 0,
    }
