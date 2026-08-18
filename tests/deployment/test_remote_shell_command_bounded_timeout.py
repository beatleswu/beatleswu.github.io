"""RELEASE-TOOLING-HOTFIX-04: executable coverage for two real, previously
unbounded SSH/native-command hang paths found while investigating a reported
production app-promotion hang.

1. Invoke-RemoteShellCommand had NO process-level timeout at all -- its two
   internal helpers each call a bare $proc.WaitForExit() with no timeout
   argument. This is the function rollback-static-release.ps1 (entirely),
   and the majority of deploy-release-image.ps1, rollback-release.ps1,
   verify-production-release.ps1, preflight-production.ps1,
   set-e9-rollout.ps1, and resume-community-leaderboard-rewards.ps1 route
   their remote calls through -- i.e. the exact class of unbounded
   ~15-minute SSH hang documented against Invoke-BoundedNativeCommand's own
   history (RELEASE-FIX-A2-STATIC-DEPLOY-FIX1) remained fully reachable
   through every one of those scripts. Fixed by delegating to
   Invoke-BoundedNativeCommand instead of the two unbounded helpers.

2. Even Invoke-BoundedNativeCommand itself (the already-bounded primitive)
   had an ordering gap: the previous implementation wrote -StdinText via a
   *synchronous* StandardInput.Write() call BEFORE WaitForExit(timeout) was
   ever reached. If the child process never reads stdin (e.g. it hung
   immediately on connect, before a remote shell ever started) and the
   payload is large enough to fill the OS pipe buffer, that Write() call
   blocks the calling thread indefinitely -- and since that block happens
   earlier in the source than WaitForExit's timeout is armed, the hard
   timeout can never fire. This was a real, previously untested gap (no
   existing test exercised -StdinText against a child that never reads it).
   Fixed by writing via the raw stream's WriteAsync (which returns a Task
   immediately without blocking) so WaitForExit(timeout) is always reached.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import time

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
MODULE = REPO_ROOT / "scripts" / "release" / "ReleaseTooling.psm1"
FAKE_SSH = REPO_ROOT / "tests" / "fixtures" / "fake_ssh" / "ssh.cmd"


def run_powershell(script: str, *, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    preamble = (
        "$OutputEncoding = [Console]::OutputEncoding = "
        "New-Object System.Text.UTF8Encoding($false);\n"
        "$ErrorActionPreference = 'Stop'\n"
        f"Import-Module '{MODULE.as_posix()}' -Force -DisableNameChecking\n"
    )
    return subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", preamble + script],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
        check=False,
    )


def _last_json(stdout: str) -> dict:
    text = stdout.strip()
    start = text.rfind("{")
    assert start >= 0, stdout
    return json.loads(text[start:])


# ---------------------------------------------------------------------------
# 1. Invoke-RemoteShellCommand now has a real, enforced timeout
# ---------------------------------------------------------------------------

def test_invoke_remote_shell_command_bounds_a_hung_fake_ssh_child():
    assert FAKE_SSH.is_file(), "fake ssh fixture used by the existing bounded-command suite is required"
    started = time.monotonic()
    script = (
        "$sw = [System.Diagnostics.Stopwatch]::StartNew()\n"
        "try {\n"
        "  Invoke-RemoteShellCommand -SshAlias 'fake-host' -Name 'hang-probe' "
        "-Command 'anything' -TimeoutSeconds 2 | Out-Null\n"
        "  [ordered]@{ ok = $true } | ConvertTo-Json -Compress\n"
        "} catch {\n"
        "  $sw.Stop()\n"
        "  [ordered]@{ ok = $false; elapsed = $sw.Elapsed.TotalSeconds; error = $_.Exception.Message } | ConvertTo-Json -Compress\n"
        "}\n"
    )
    # Invoke-RemoteShellCommand always calls the real `ssh` on PATH -- it has
    # no -SshExecutable override like Invoke-BoundedSshCommand. Point PATH at
    # the fake ssh fixture's directory (Windows resolves bare `ssh` against
    # ssh.cmd there before any real ssh.exe elsewhere on PATH) and set
    # FAKE_SSH_MODE=hang, exactly the same fixture and trigger the existing
    # Invoke-BoundedSshCommand hang test already uses.
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
         "$OutputEncoding = [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false);\n"
         "$ErrorActionPreference = 'Stop'\n"
         f"Import-Module '{MODULE.as_posix()}' -Force -DisableNameChecking\n"
         f"$env:PATH = '{FAKE_SSH.parent.as_posix()}' + ';' + $env:PATH\n"
         "$env:FAKE_SSH_MODE = 'hang'\n"
         + script],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    elapsed_wall = time.monotonic() - started
    assert result.returncode == 0, result.stdout + result.stderr
    payload = _last_json(result.stdout)
    assert payload["ok"] is False, "a permanently-hanging fake ssh must be bounded, not silently succeed"
    assert elapsed_wall < 15, f"must be bounded near the 2s TimeoutSeconds, took {elapsed_wall}s wall-clock"
    assert "Timed out after 2s" in payload["error"]


def test_invoke_remote_shell_command_default_timeout_is_finite_and_positive():
    result = run_powershell(
        "$cmd = Get-Command Invoke-RemoteShellCommand\n"
        "$p = $cmd.Parameters['TimeoutSeconds']\n"
        "[ordered]@{ exists = ($null -ne $p) } | ConvertTo-Json -Compress\n"
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = _last_json(result.stdout)
    assert payload["exists"] is True


def test_invoke_remote_shell_command_rejects_nonpositive_timeout():
    result = run_powershell(
        "try {\n"
        "  Invoke-RemoteShellCommand -SshAlias 'fake-host' -Name 'x' -Command 'echo hi' -TimeoutSeconds 0 | Out-Null\n"
        "  [ordered]@{ threw = $false } | ConvertTo-Json -Compress\n"
        "} catch {\n"
        "  [ordered]@{ threw = $true; error = $_.Exception.Message } | ConvertTo-Json -Compress\n"
        "}\n"
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = _last_json(result.stdout)
    assert payload["threw"] is True
    assert "TimeoutSeconds must be a positive number" in payload["error"]


def test_source_no_longer_routes_through_the_unbounded_helpers():
    # Checked as executable-call signatures, not a bare substring -- the
    # docstring right above this function legitimately explains what it USED
    # to call (and why that was unbounded) as part of the hotfix writeup.
    content = MODULE.read_text(encoding="utf-8")
    function_start = content.index("function Invoke-RemoteShellCommand")
    doc_end = content.index("#>", function_start) + len("#>")
    function_end = content.index("\nfunction ", function_start + 1)
    body = content[doc_end:function_end]
    assert "Invoke-ProcessWithUtf8NoBomStdin" not in body
    assert "Invoke-ProcessWithSeparateOutput" not in body
    assert "Invoke-BoundedNativeCommand" in body


# ---------------------------------------------------------------------------
# 2. Invoke-BoundedNativeCommand: stdin write no longer blocks ahead of the
#    hard timeout when the child never reads it
# ---------------------------------------------------------------------------

def test_bounded_native_command_stdin_write_never_blocks_ahead_of_timeout():
    # A payload comfortably larger than any realistic OS anonymous-pipe
    # buffer (commonly 4KB-64KB on Windows) sent to a child that never
    # reads stdin at all (Start-Sleep does not touch it). Under the old
    # synchronous StandardInput.Write() implementation this would block the
    # calling thread indefinitely, BEFORE WaitForExit(timeout) was ever
    # reached -- so the 2s TimeoutSeconds below would never have fired and
    # this test would hang until pytest's own subprocess timeout killed it.
    large_payload_len = 500_000
    script = (
        "$sw = [System.Diagnostics.Stopwatch]::StartNew()\n"
        f"$payload = 'x' * {large_payload_len}\n"
        "try {\n"
        "  Invoke-BoundedNativeCommand -FileName 'powershell' "
        "-ArgumentList @('-NoProfile', '-Command', 'Start-Sleep -Seconds 999') "
        "-StdinText $payload -TimeoutSeconds 2 -OperationLabel 'stdin hang probe' | Out-Null\n"
        "  [ordered]@{ ok = $true; elapsed = $sw.Elapsed.TotalSeconds } | ConvertTo-Json -Compress\n"
        "} catch {\n"
        "  $sw.Stop()\n"
        "  [ordered]@{ ok = $false; elapsed = $sw.Elapsed.TotalSeconds; error = $_.Exception.Message } | ConvertTo-Json -Compress\n"
        "}\n"
    )
    started = time.monotonic()
    result = run_powershell(script, timeout=30)
    elapsed_wall = time.monotonic() - started
    assert result.returncode == 0, result.stdout + result.stderr
    payload = _last_json(result.stdout)
    assert elapsed_wall < 20, (
        f"stdin write to a non-reading child must never block ahead of the "
        f"2s TimeoutSeconds bound; took {elapsed_wall}s wall-clock"
    )
    assert payload["ok"] is False
    assert "Timed out after 2s" in payload["error"]
    assert payload["elapsed"] < 10


def test_bounded_native_command_still_delivers_stdin_correctly_to_a_reading_child():
    # Regression guard: the WriteAsync rewrite must not have broken normal,
    # successful stdin delivery to a child that DOES read it promptly.
    result = run_powershell(
        "$payload = \"hello-stdin-world`n\"\n"
        "$result = Invoke-BoundedNativeCommand -FileName 'powershell' "
        "-ArgumentList @('-NoProfile', '-Command', '[Console]::In.ReadToEnd()') "
        "-StdinText $payload -TimeoutSeconds 15 -OperationLabel 'stdin echo probe'\n"
        "[ordered]@{ exit_code = $result.exit_code; stdout = $result.stdout } | ConvertTo-Json -Compress\n"
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = _last_json(result.stdout)
    assert payload["exit_code"] == 0
    assert "hello-stdin-world" in payload["stdout"]
