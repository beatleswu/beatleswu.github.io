"""RELEASE-TOOLING-HOTFIX-05: every canonical app-deploy file transfer must
be bounded.

scripts/release/deploy-release-image.ps1 previously performed eight raw
`& scp ...` transfers (compose file, healthcheck override, nginx config,
release manifest, the multi-hundred-MB release archive, and three deployment
-record syncs), each checked only via $LASTEXITCODE and each with no timeout
of any kind. A hung scp there would block the whole deployment indefinitely
with no process-tree termination and no classified failure -- precisely the
unbounded-transfer hang class that Invoke-BoundedNativeCommand (and
RELEASE-FIX-A2-STATIC-DEPLOY-FIX1 before it) exists to prevent, and that
deploy-static-release.ps1's own uploads were already hardened against.

These tests prove: (a) no unbounded scp invocation remains in the canonical
app-deploy path, (b) every transfer supplies an operation-appropriate bound
rather than relying on any outer orchestration timeout, and (c) a genuinely
hung scp child is really terminated within its bound and surfaces as a
classified operational failure -- exercised against a real hanging child
process, not a mock.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import time

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
DEPLOY_RELEASE_IMAGE = REPO_ROOT / "scripts" / "release" / "deploy-release-image.ps1"
MODULE = REPO_ROOT / "scripts" / "release" / "ReleaseTooling.psm1"
FAKE_SCP = REPO_ROOT / "tests" / "fixtures" / "fake_ssh" / "scp.cmd"


def _source() -> str:
    return DEPLOY_RELEASE_IMAGE.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# (a) No unbounded scp remains
# ---------------------------------------------------------------------------

def test_no_raw_scp_invocation_remains_in_canonical_app_deploy():
    executable_lines = [
        line for line in _source().splitlines()
        if re.match(r"^\s*&\s*scp\b", line)
    ]
    assert executable_lines == [], (
        f"raw unbounded scp invocations must not remain: {executable_lines}"
    )


def test_every_upload_goes_through_the_shared_bounded_helper():
    content = _source()
    assert "function Invoke-BoundedReleaseUpload" in content
    start = content.index("function Invoke-BoundedReleaseUpload")
    end = content.index("\nfunction ", start + 1)
    body = content[start:end]
    # The shared helper itself delegates to the governed bounded primitive.
    assert "Invoke-BoundedScpUpload" in body
    assert "TimeoutSeconds" in body
    # Every transfer site uses it (5 in the main upload block + 3 deployment
    # record syncs = 8, matching the 8 raw calls it replaced).
    call_sites = [
        line for line in content.splitlines()
        if "Invoke-BoundedReleaseUpload -LocalPath" in line
    ]
    assert len(call_sites) == 8, f"expected 8 bounded upload call sites, found {len(call_sites)}"
    # ... and every one of them supplies an explicit bound.
    for line in call_sites:
        assert "-TimeoutSeconds" in line, f"upload call site without an explicit bound: {line}"


def test_large_archive_upload_uses_a_size_derived_bound_not_a_guessed_constant():
    content = _source()
    assert "Get-ArchiveTransferTimeoutSeconds" in content
    archive_line = next(
        line for line in content.splitlines()
        if "Invoke-BoundedReleaseUpload -LocalPath $archivePath" in line
    )
    assert "$archiveUploadTimeoutSeconds" in archive_line


def test_bounded_helper_is_defined_before_first_use():
    content = _source()
    assert content.index("function Invoke-BoundedReleaseUpload") < content.index(
        "Invoke-BoundedReleaseUpload -LocalPath"
    )


# ---------------------------------------------------------------------------
# (c) A real hung scp child is really terminated within its bound
# ---------------------------------------------------------------------------

def test_hung_scp_child_is_bounded_terminated_and_classified(tmp_path):
    assert FAKE_SCP.is_file(), "fake scp fixture used by the existing bounded-command suite is required"
    payload = tmp_path / "payload.txt"
    payload.write_text("release artifact stand-in\n", encoding="utf-8")

    script = (
        "$OutputEncoding = [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)\n"
        "$ErrorActionPreference = 'Stop'\n"
        f"Import-Module '{MODULE.as_posix()}' -Force -DisableNameChecking\n"
        "$sw = [System.Diagnostics.Stopwatch]::StartNew()\n"
        "try {\n"
        f"  Invoke-BoundedScpUpload -LocalPath '{payload.as_posix()}' -SshAlias 'fake-host' "
        f"-RemotePath '/tmp/payload.txt' -TimeoutSeconds 2 "
        f"-OperationLabel 'probe: hung release upload' -ScpExecutable '{FAKE_SCP.as_posix()}' | Out-Null\n"
        "  [ordered]@{ ok = $true } | ConvertTo-Json -Compress\n"
        "} catch {\n"
        "  $sw.Stop()\n"
        "  [ordered]@{ ok = $false; elapsed = $sw.Elapsed.TotalSeconds; error = $_.Exception.Message } | ConvertTo-Json -Compress\n"
        "}\n"
    )
    started = time.monotonic()
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        cwd=REPO_ROOT,
        env={**os.environ, "FAKE_SCP_MODE": "hang"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=40,
        check=False,
    )
    elapsed_wall = time.monotonic() - started
    assert result.returncode == 0, result.stdout + result.stderr
    payload_out = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload_out["ok"] is False, "a permanently-hanging scp must be bounded, not hang forever"
    assert elapsed_wall < 25, f"must terminate near the 2s bound; took {elapsed_wall}s wall-clock"
    assert "Timed out after 2s" in payload_out["error"]
    assert payload_out["elapsed"] < 15


def test_failing_scp_child_surfaces_a_classified_nonzero_exit_not_a_hang(tmp_path):
    payload = tmp_path / "payload.txt"
    payload.write_text("release artifact stand-in\n", encoding="utf-8")
    script = (
        "$OutputEncoding = [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)\n"
        "$ErrorActionPreference = 'Stop'\n"
        f"Import-Module '{MODULE.as_posix()}' -Force -DisableNameChecking\n"
        f"$r = Invoke-BoundedScpUpload -LocalPath '{payload.as_posix()}' -SshAlias 'fake-host' "
        f"-RemotePath '/tmp/payload.txt' -TimeoutSeconds 15 "
        f"-OperationLabel 'probe: failing release upload' -ScpExecutable '{FAKE_SCP.as_posix()}'\n"
        "[ordered]@{ exit_code = $r.exit_code; timed_out = $r.timed_out } | ConvertTo-Json -Compress\n"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        cwd=REPO_ROOT,
        env={**os.environ, "FAKE_SCP_MODE": "fail"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=40,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload_out = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload_out["exit_code"] == 1
    assert payload_out["timed_out"] is False
