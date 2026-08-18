"""Executable contract for the preflight-only SSH invocation retry."""

import json
import pathlib
import shutil
import subprocess


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
PREFLIGHT = REPO_ROOT / "scripts" / "release" / "preflight-production.ps1"
MUTATING_SCRIPTS = (
    "scripts/release/deploy-release-image.ps1",
    "scripts/release/deploy-static-release.ps1",
    "scripts/release/rollback-release.ps1",
    "scripts/release/rollback-static-release.ps1",
)


def _remote_command_result_function() -> str:
    source = PREFLIGHT.read_text(encoding="utf-8")
    start = source.index("function Invoke-RemoteCommandResult")
    end = source.index("\nfunction Invoke-RemoteText", start)
    return source[start:end]


def _run_probe(tmp_path: pathlib.Path, mode: str) -> dict[str, object]:
    if shutil.which("powershell") is None:
        raise AssertionError("Windows PowerShell is required for preflight retry probes")

    function_body = _remote_command_result_function()
    probe = tmp_path / f"preflight-retry-{mode}.ps1"
    probe.write_text(
        "[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)\n"
        "$ErrorActionPreference = 'Stop'\n"
        f"$script:Mode = '{mode}'\n"
        "$script:CallCount = 0\n"
        "$script:FakeResponseCalls = 0\n"
        "$layout = [pscustomobject]@{ ssh_alias = 'fake-host' }\n"
        "$script:FakeRemoteResponses = $null\n"
        "function Get-FakeRemoteResponse {\n"
        "    param([string]$Name)\n"
        "    $script:FakeResponseCalls = $script:FakeResponseCalls + 1\n"
        "    return [pscustomobject]@{ stdout = 'fake'; exit_code = 0 }\n"
        "}\n"
        "function Invoke-RemoteShellCommand {\n"
        "    param([string]$SshAlias, [string]$Name, [string]$Command, [string]$ScriptText, [string]$StdinText)\n"
        "    $script:CallCount = $script:CallCount + 1\n"
        "    if ($script:Mode -eq 'fake') { throw 'SSH helper must not run in fake mode' }\n"
        "    if ($script:Mode -eq 'throw-once' -and $script:CallCount -eq 1) { throw 'transport failure 1' }\n"
        "    if ($script:Mode -eq 'throw-twice') { throw ('transport failure ' + $script:CallCount) }\n"
        "    if ($script:Mode -eq 'nonzero') {\n"
        "        return [ordered]@{ exit_code = 17; stdout = 'remote-failure'; stderr = 'remote-error'; output = 'remote-failure' }\n"
        "    }\n"
        "    return [ordered]@{ exit_code = 0; stdout = 'ok'; stderr = ''; output = 'ok' }\n"
        "}\n"
        + function_body
        + "\n"
        + ("$script:FakeRemoteResponses = [pscustomobject]@{ responses = $true }\n" if mode == "fake" else "")
        + "try {\n"
        + "    $result = Invoke-RemoteCommandResult -Name 'probe' -Command 'printf ready'\n"
        + "    [ordered]@{ ok = $true; call_count = $script:CallCount; fake_response_calls = $script:FakeResponseCalls; mode = $result.mode; exit_code = $result.exit_code; stdout = $result.stdout } | ConvertTo-Json -Compress\n"
        + "} catch {\n"
        + "    [ordered]@{ ok = $false; call_count = $script:CallCount; fake_response_calls = $script:FakeResponseCalls; error = $_.Exception.Message } | ConvertTo-Json -Compress\n"
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
        timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert lines, result.stdout + result.stderr
    return json.loads(lines[-1])


def test_first_readonly_remote_invocation_result_is_returned_without_retry(tmp_path):
    payload = _run_probe(tmp_path, "success")
    assert payload == {
        "ok": True,
        "call_count": 1,
        "fake_response_calls": 0,
        "mode": "ssh",
        "exit_code": 0,
        "stdout": "ok",
    }


def test_thrown_readonly_remote_invocation_gets_one_retry(tmp_path):
    payload = _run_probe(tmp_path, "throw-once")
    assert payload == {
        "ok": True,
        "call_count": 2,
        "fake_response_calls": 0,
        "mode": "ssh",
        "exit_code": 0,
        "stdout": "ok",
    }


def test_second_thrown_readonly_remote_invocation_propagates_after_two_attempts(tmp_path):
    payload = _run_probe(tmp_path, "throw-twice")
    assert payload["ok"] is False
    assert payload["call_count"] == 2
    assert "transport failure 2" in payload["error"]


def test_nonzero_remote_result_is_returned_without_retry(tmp_path):
    payload = _run_probe(tmp_path, "nonzero")
    assert payload == {
        "ok": True,
        "call_count": 1,
        "fake_response_calls": 0,
        "mode": "ssh",
        "exit_code": 17,
        "stdout": "remote-failure",
    }


def test_fake_response_mode_has_one_deterministic_response_and_no_ssh_retry(tmp_path):
    payload = _run_probe(tmp_path, "fake")
    assert payload == {
        "ok": True,
        "call_count": 0,
        "fake_response_calls": 1,
        "mode": "fake",
        "exit_code": 0,
        "stdout": "fake",
    }


def test_retry_is_explicitly_bounded_without_an_unbounded_loop():
    function_body = _remote_command_result_function()
    assert function_body.count("Invoke-RemoteShellCommand @params") == 2
    assert "while (" not in function_body
    assert "for (" not in function_body
    assert "Start-Sleep -Milliseconds 250" in function_body


def test_retry_boundary_is_preflight_local_only():
    marker = "A returned non-zero exit code remains a single, fail-closed result."
    assert marker in _remote_command_result_function()
    for relative_path in MUTATING_SCRIPTS:
        content = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        assert marker not in content, f"read-only retry boundary leaked into {relative_path}"
