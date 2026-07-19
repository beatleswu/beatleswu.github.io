"""Executable coverage for deploy-release-image.ps1's framed readiness channel."""

import base64
import json
import pathlib
import shutil
import subprocess

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
DEPLOY_SCRIPT = REPO_ROOT / "scripts" / "release" / "deploy-release-image.ps1"
PREFIX = "__GO_ODYSSEY_READINESS_V1__:"


def readiness_report(**overrides):
    report = {
        "ok": True,
        "app": {"git_sha": "a" * 40, "image_revision": "a" * 40},
        "questions": {"parseable": True, "record_count_ok": True, "structural_record_check": True},
        "database": {"reachable": True, "tables": {}},
        "static_root": {"readable": True},
        "shadow_events": {"writable_or_valid": True},
        "failures": [],
    }
    report.update(overrides)
    return report


def framed(payload):
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return PREFIX + base64.b64encode(raw).decode("ascii")


def production_function_block():
    source = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    start = source.index("function Test-HelperUnavailableOutput")
    end = source.index("function Get-RemoteQuestionsReport", start)
    return source[start:end]


def run_real_functions(tmp_path, output, *, stderr="", exit_code=0, call_try=True):
    if shutil.which("powershell") is None:
        pytest.fail("Windows PowerShell 5.1 is required")
    output_b64 = base64.b64encode(output.encode("utf-8")).decode("ascii")
    stderr_b64 = base64.b64encode(stderr.encode("utf-8")).decode("ascii")
    probe = tmp_path / "readiness-probe.ps1"
    invocation = (
        "$value = Try-Get-RemoteReadinessReport -ContainerName 'candidate-test'"
        if call_try
        else "$value = ConvertFrom-FramedReadinessOutput -Output $script:FakeOutput"
    )
    probe.write_text(
        "[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)\n"
        "$ErrorActionPreference = 'Stop'\n"
        f"Import-Module '{(REPO_ROOT / 'scripts' / 'release' / 'ReleaseTooling.psm1').as_posix()}' -Force -DisableNameChecking\n"
        f"$script:FakeOutput = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{output_b64}'))\n"
        f"$script:FakeStderr = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{stderr_b64}'))\n"
        f"$script:FakeExitCode = {exit_code}\n"
        "$script:CapturedCommand = ''\n"
        "$layout = [pscustomobject]@{ ssh_alias = 'test-host' }\n"
        "function Invoke-BoundedSshCommand {\n"
        "  param([string]$SshAlias, [string]$Command, [int]$TimeoutSeconds, [string]$OperationLabel)\n"
        "  $script:CapturedCommand = $Command\n"
        "  return [ordered]@{ stdout = $script:FakeOutput; stderr = $script:FakeStderr; output = ($script:FakeOutput + $script:FakeStderr); exit_code = $script:FakeExitCode; elapsed_seconds = 1.25; timed_out = $false }\n"
        "}\n"
        + production_function_block()
        + "\ntry {\n"
        + f"  {invocation}\n"
        + "  [ordered]@{ ok = $true; value = $value; command = $script:CapturedCommand } | ConvertTo-Json -Depth 20 -Compress\n"
        + "} catch {\n"
        + "  [ordered]@{ ok = $false; error = $_.Exception.Message; attempt = $script:LastReadinessAttempt } | ConvertTo-Json -Depth 20 -Compress\n"
        + "}\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(probe)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize(
    "output",
    [
        lambda record: record,
        lambda record: '[startup-diagnostic] {"schema":"startup-diagnostic-v1","phase":"import","status":"start"}\n' + record,
        lambda record: record + '\n[startup-diagnostic] {"schema":"startup-diagnostic-v1","phase":"ready","status":"success"}',
        lambda record: '[startup-diagnostic] punctuation: {not readiness}; [1,2,3]!\nnoise={"ok":false}\n' + record,
    ],
    ids=["pure-framed-json", "diagnostic-before", "diagnostic-after", "json-like-diagnostics"],
)
def test_real_readiness_helper_extracts_one_framed_result_amid_diagnostics(tmp_path, output):
    result = run_real_functions(tmp_path, output(framed(readiness_report())))
    assert result["ok"] is True
    assert result["value"]["mode"] == "helper"
    assert result["value"]["report"]["ok"] is True
    assert 'encode("utf-8")' in result["command"]
    assert "__GO_ODYSSEY_READINESS_V1__:" in result["command"]


def test_real_readiness_helper_accepts_stderr_diagnostics_merged_around_stdout_record(tmp_path):
    diagnostic = '[startup-diagnostic] {"schema":"startup-diagnostic-v1","boot_id":"boot-safe","phase":"python_start","status":"start","secret":"must-not-survive"}'
    result = run_real_functions(tmp_path, framed(readiness_report()), stderr=diagnostic)
    assert result["ok"] is True
    assert len(result["value"]["startup_diagnostics"]) == 1
    assert result["value"]["startup_diagnostics"][0]["boot_id"] == "boot-safe"
    assert "secret" not in result["value"]["startup_diagnostics"][0]


@pytest.mark.parametrize(
    ("output", "error_fragment"),
    [
        ("diagnostic only", "exactly one framed JSON result; found 0"),
        (framed(readiness_report()) + "\n" + framed(readiness_report()), "exactly one framed JSON result; found 2"),
        (PREFIX + "%%%not-base64%%%", "framed JSON result is malformed"),
        (framed({"ok": True}), "invalid schema"),
    ],
    ids=["missing", "duplicate", "malformed", "invalid-schema"],
)
def test_real_readiness_helper_fails_closed_for_invalid_channel(tmp_path, output, error_fragment):
    result = run_real_functions(tmp_path, output)
    assert result["ok"] is False
    assert error_fragment in result["error"]


def test_unexpected_helper_failure_does_not_copy_merged_output_into_error(tmp_path):
    sentinel = "DATABASE_URL=postgresql://private.example/secret"
    result = run_real_functions(tmp_path, sentinel, exit_code=9)
    assert result["ok"] is False
    assert "exit code 9" in result["error"]
    assert sentinel not in result["error"]
    assert result["attempt"]["exit_code"] == 9
    assert result["attempt"]["stdout"] == ""


def test_nonzero_helper_retains_separate_channels_and_decodes_valid_frame(tmp_path):
    diagnostic = '[startup-diagnostic] {"schema":"startup-diagnostic-v1","boot_id":"boot-failure","phase":"database","status":"start"}'
    result = run_real_functions(tmp_path, framed(readiness_report(ok=False, failures=["safe failure"])), stderr=diagnostic, exit_code=1)
    assert result["ok"] is False
    assert "exit code 1" in result["error"]
    attempt = result["attempt"]
    assert attempt["framed_payload_present"] is True
    assert attempt["framed_report"]["ok"] is False
    assert attempt["stdout"] == "__GO_ODYSSEY_READINESS_V1__:<payload retained separately>"
    assert "boot-failure" in attempt["stderr"]
    assert attempt["elapsed_seconds"] == 1.25


def test_persisted_framed_evidence_omits_database_identity_paths_and_failure_text(tmp_path):
    report = readiness_report(
        database={"reachable": False, "tables": {}, "identity": {"host": "private.internal", "user": "credential-user"}},
        failures=["postgresql://credential-user:secret@private.internal/db"],
    )
    result = run_real_functions(tmp_path, framed(report), exit_code=1)
    serialized = json.dumps(result["attempt"]["framed_report"], sort_keys=True)
    for sentinel in ("private.internal", "credential-user", "postgresql://", "secret"):
        assert sentinel not in serialized
    assert result["attempt"]["framed_report"]["database"]["reachable"] is False
    assert result["attempt"]["framed_report"]["failure_count"] == 1


def test_deploy_script_keeps_candidate_and_release_lock_cleanup_paths():
    source = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    catch_block = source.split("catch {\n    $deploymentFailure = $_", 1)[1]
    assert "Remove-RemoteCandidateCanary" in catch_block
    assert "Invoke-CandidateFailurePreservation" in catch_block
    assert "Exit-RemoteReleaseOperationLock" in source
    assert "finally" in source
