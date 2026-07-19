"""Executable regressions for framed release JSON and diagnostic isolation."""

import base64
import json
import pathlib
import shutil
import subprocess

import pytest


ROOT = pathlib.Path(__file__).resolve().parents[2]
MODULE = ROOT / "scripts/release/ReleaseTooling.psm1"
PREFIX = "__GO_ODYSSEY_READINESS_V1__:"
PS_PREFIX = "__GO_ODYSSEY_POWERSHELL_RESULT_V1__:"


def frame(payload, prefix=PREFIX):
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return prefix + base64.b64encode(raw).decode("ascii")


def readiness_payload(**overrides):
    payload = {
        "ok": True,
        "app": {"git_sha": "a" * 40, "image_revision": "a" * 40},
        "questions": {"parseable": True, "record_count_ok": True},
        "database": {"reachable": True},
        "static_root": {"readable": True},
        "shadow_events": {"writable_or_valid": True},
        "failures": [],
    }
    payload.update(overrides)
    return payload


def run_ps(tmp_path, body):
    if shutil.which("powershell") is None:
        pytest.fail("Windows PowerShell 5.1 is required")
    script = tmp_path / "probe.ps1"
    script.write_text(
        "$ErrorActionPreference='Stop'\n"
        f"Import-Module '{MODULE.as_posix()}' -Force -DisableNameChecking\n"
        + body,
        encoding="utf-8",
    )
    return subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


@pytest.mark.parametrize(
    "result_expression",
    [
        "[ordered]@{stdout='machine-json';stderr='startup-diagnostic';output='machine-jsonstartup-diagnostic'}",
        "@{stdout='machine-json';stderr='startup-diagnostic';output='machine-jsonstartup-diagnostic'}",
        "[pscustomobject]@{stdout='machine-json';stderr='startup-diagnostic';output='machine-jsonstartup-diagnostic'}",
    ],
    ids=["ordered-dictionary", "hashtable", "pscustomobject"],
)
def test_remote_standard_output_never_falls_back_to_merged_diagnostics(tmp_path, result_expression):
    result = run_ps(
        tmp_path,
        f"$remote={result_expression}\n"
        "$selected=Get-RemoteStandardOutput -Result $remote\n"
        "$selected|Write-Output\n",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "machine-json"
    assert "startup-diagnostic" not in result.stdout


@pytest.mark.parametrize(
    "lines",
    [
        lambda record: [record],
        lambda record: ["startup-diagnostic before", record],
        lambda record: [record, "startup-diagnostic after"],
        lambda record: ["Container app Recreate", "{not-json}", record, "Container app Started"],
    ],
    ids=["pure", "diagnostic-before", "diagnostic-after", "compose-and-json-like-diagnostics"],
)
def test_shared_framed_parser_extracts_exact_payload_without_parsing_diagnostics(tmp_path, lines):
    mixed = "\n".join(lines(frame({"ok": True}, PS_PREFIX)))
    encoded = base64.b64encode(mixed.encode("utf-8")).decode("ascii")
    result = run_ps(
        tmp_path,
        f"$raw=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{encoded}'))\n"
        "$parsed=ConvertFrom-NestedPowerShellJson -RawOutput ($raw -split \"`n\") -Context 'child'\n"
        "$parsed|ConvertTo-Json -Compress\n",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout.strip()) == {"ok": True}


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ("diagnostic only", "found 0"),
        (frame({"ok": True}, PS_PREFIX) + "\n" + frame({"ok": True}, PS_PREFIX), "found 2"),
        (PS_PREFIX + "%%%", "malformed"),
        (PS_PREFIX + base64.b64encode(b'{"ok":').decode("ascii"), "malformed"),
    ],
    ids=["missing", "duplicate", "malformed", "truncated-json"],
)
def test_shared_framed_parser_fails_closed_for_invalid_contract(tmp_path, payload, message):
    encoded = base64.b64encode(payload.encode("utf-8")).decode("ascii")
    result = run_ps(
        tmp_path,
        f"$raw=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{encoded}'))\n"
        "try { ConvertFrom-NestedPowerShellJson -RawOutput $raw -Context 'child'|Out-Null; 'NO_THROW' } catch { $_.Exception.Message }\n",
    )
    assert result.returncode == 0, result.stderr
    assert "NO_THROW" not in result.stdout
    assert message in result.stdout


def readiness_function_block(path):
    source = path.read_text(encoding="utf-8")
    start = source.index("function Test-HelperUnavailableOutput")
    end = source.index("function Get-RemoteQuestionsReport", start)
    return source[start:end]


@pytest.mark.parametrize(
    "script_name",
    ["preflight-production.ps1", "verify-production-release.ps1", "rollback-release.ps1"],
)
def test_real_release_readiness_consumers_accept_diagnostics_on_separate_channels(tmp_path, script_name):
    payload = frame(readiness_payload())
    stdout = base64.b64encode(("diagnostic before\n" + payload + "\ndiagnostic after").encode()).decode()
    stderr = base64.b64encode(b"startup-diagnostic stderr").decode()
    block = readiness_function_block(ROOT / "scripts/release" / script_name)
    body = (
        "$layout=[pscustomobject]@{ssh_alias='test-host'}\n"
        "$env:GO_ODYSSEY_PREFLIGHT_FAKE_REMOTE_RESPONSES=$null\n"
        f"$fakeOut=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{stdout}'))\n"
        f"$fakeErr=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{stderr}'))\n"
        "function Invoke-BoundedSshCommand { [ordered]@{stdout=$fakeOut;stderr=$fakeErr;output=($fakeOut+$fakeErr);exit_code=0;elapsed_seconds=1.25;timed_out=$false} }\n"
        + block
        + "\n$result=Try-Get-RemoteReadinessReport -ContainerName 'app-current'\n"
        + "$result|ConvertTo-Json -Depth 10 -Compress\n"
    )
    result = run_ps(tmp_path, body)
    assert result.returncode == 0, result.stdout + result.stderr
    parsed = json.loads(result.stdout.strip().splitlines()[-1])
    assert parsed["mode"] == "helper"
    assert parsed["report"]["ok"] is True


def test_schema_validation_fails_before_payload_can_be_accepted(tmp_path):
    encoded = base64.b64encode(frame({"ok": True}).encode()).decode()
    result = run_ps(
        tmp_path,
        f"$raw=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{encoded}'))\n"
        "try { ConvertFrom-FramedJsonRecord -Output $raw -Prefix '__GO_ODYSSEY_READINESS_V1__:' -Context 'readiness' -RequiredProperties @('ok','app'); 'NO_THROW' } catch { $_.Exception.Message }\n",
    )
    assert result.returncode == 0, result.stderr
    assert "NO_THROW" not in result.stdout
    assert "missing app" in result.stdout


def test_production_scripts_request_framed_child_results_and_separate_streams():
    deploy = (ROOT / "scripts/release/deploy-release-image.ps1").read_text(encoding="utf-8")
    rollback = (ROOT / "scripts/release/rollback-release.ps1").read_text(encoding="utf-8")
    verify = (ROOT / "scripts/release/verify-production-release.ps1").read_text(encoding="utf-8")
    assert "Invoke-BoundedNativeCommand" in deploy
    assert "Invoke-BoundedNativeCommand" in rollback
    assert "'-FramedResult'" in deploy
    assert "'-FramedResult'" in rollback
    assert "[switch]$FramedResult" in verify
    assert "__GO_ODYSSEY_POWERSHELL_RESULT_V1__:" in verify
    assert "$verificationResult.stdout" in deploy
    assert "$rollbackResult.stdout" in deploy
