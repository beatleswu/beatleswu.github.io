"""Contracts for scripts/release/deploy-coordinated-release.ps1, the
Deployment Workflow V3 CLI entrypoint.

Only the genuinely testable-without-Production surface is covered here:
argument validation, the OwnerGate contract, and the dry-run plan report
(which never builds, packages, promotes, or contacts Production -- exactly
like every other canonical release script's dry-run mode). The real
-Execute wiring to build-release-image.ps1/package-*.ps1/deploy-*.ps1/
rollback-*.ps1 is exercised indirectly by test_coordinated_release_state_machine.py
(which proves the underlying state machine those phase scriptblocks drive
is correct) and by source-level checks here that each phase is wrapped in
Invoke-BoundedNativeCommand -- not by an actual end-to-end -Execute run,
which this task is explicitly not authorized to perform against any real
host.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "release" / "deploy-coordinated-release.ps1"
EXAMPLE_LAYOUT = "deploy\\release-layout.example.json"
CANDIDATE_SHA = "aa3d56b369be72c74d79f5a3c0fd04b7e847475e"


def run_powershell(args: list[str], *, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    quoted_args = " ".join(
        f"'{a}'" if not a.startswith("-") else a for a in args
    )
    preamble = (
        "$OutputEncoding = [Console]::OutputEncoding = "
        "New-Object System.Text.UTF8Encoding($false);\n"
    )
    return subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
         preamble + f"& '{SCRIPT.as_posix()}' {quoted_args}"],
        cwd=REPO_ROOT,
        env={**os.environ, "SECRET_KEY": "coordinated-release-cli-test-only"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
        check=False,
    )


def _last_json(stdout: str) -> dict:
    start = stdout.find("{")
    assert start >= 0, stdout
    return json.loads(stdout[start:])


def test_script_parses_as_valid_powershell():
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "$t=$null;$e=$null;"
         f"[System.Management.Automation.Language.Parser]::ParseFile('{SCRIPT.as_posix()}', [ref]$t, [ref]$e) | Out-Null;"
         "if ($e.Count -gt 0) { $e | ForEach-Object { Write-Host $_.Message }; exit 1 } else { Write-Host 'OK' }"],
        cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", timeout=20, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK" in result.stdout


def test_dry_run_never_mutates_and_reports_the_full_phase_plan():
    result = run_powershell(["-ExpectedGitSha", CANDIDATE_SHA, "-LayoutFile", EXAMPLE_LAYOUT])
    assert result.returncode == 0, result.stdout + result.stderr
    payload = _last_json(result.stdout)
    assert payload["dry_run"] is True
    assert payload["execute_requested"] is False
    assert payload["expected_git_sha"] == CANDIDATE_SHA
    assert payload["required_owner_gate"] == "GO_DEPLOY_WITH_BOUNDED_RECOVERY"
    assert payload["result"] == "DRY_RUN_COMPLETE"
    assert payload["plan"] == [
        "PRECHECK", "BUILD_APP", "PACKAGE_APP", "PACKAGE_STATIC",
        "SNAPSHOT_BASELINE", "VERIFY_ROLLBACK_READY",
        "PROMOTE_STATIC", "VERIFY_STATIC", "PROMOTE_APP", "VERIFY_APP",
        "JOINT_PROVENANCE", "PRODUCTION_SMOKE",
    ]
    # The example layout's host/URLs are all example.invalid / a fake ssh
    # alias -- confirms dry-run only ever reads local config, never resolves
    # or contacts anything real.
    assert "example" in payload["release_layout"]["health_url"]


def test_execute_without_owner_gate_fails_closed():
    result = run_powershell(["-ExpectedGitSha", CANDIDATE_SHA, "-LayoutFile", EXAMPLE_LAYOUT, "-Execute"])
    assert result.returncode != 0
    assert "docker" not in (result.stdout + result.stderr).lower() or "ParameterBindingValidationException" in (result.stdout + result.stderr)


def test_execute_with_wrong_owner_gate_fails_closed_before_any_mutation():
    result = run_powershell([
        "-ExpectedGitSha", CANDIDATE_SHA, "-LayoutFile", EXAMPLE_LAYOUT,
        "-Execute", "-OwnerGate", "GO_DEPLOY",
    ])
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "Owner gate mismatch" in combined
    assert "GO_DEPLOY_WITH_BOUNDED_RECOVERY" in combined


def test_execute_rejects_arbitrary_gate_strings():
    result = run_powershell([
        "-ExpectedGitSha", CANDIDATE_SHA, "-LayoutFile", EXAMPLE_LAYOUT,
        "-Execute", "-OwnerGate", "totally-not-a-real-gate",
    ])
    assert result.returncode != 0
    assert "Owner gate mismatch" in (result.stdout + result.stderr)


def test_invalid_git_sha_fails_before_any_mutation():
    result = run_powershell(["-ExpectedGitSha", "not-a-real-commit-ish", "-LayoutFile", EXAMPLE_LAYOUT])
    assert result.returncode != 0


# ---------------------------------------------------------------------------
# Source-level: every phase must be bounded, and this script must not
# duplicate low-level build/deploy/rollback logic.
# ---------------------------------------------------------------------------

def test_every_governed_script_invocation_is_bounded():
    content = SCRIPT.read_text(encoding="utf-8")
    assert "function Invoke-GovernedScript" in content
    invoke_block_start = content.index("function Invoke-GovernedScript")
    invoke_block_end = content.index("$GetCurrentState = {", invoke_block_start)
    invoke_body = content[invoke_block_start:invoke_block_end]
    assert "Invoke-BoundedNativeCommand" in invoke_body
    assert "TimeoutSeconds" in invoke_body
    # One call site per phase that actually shells out to an existing
    # governed script: GetCurrentState, BuildApp, PackageApp, PackageStatic,
    # PromoteStatic, PromoteApp, RollbackStatic, RollbackApp, plus
    # VerifyApp's and VerifyStatic's independent canonical verifications.
    call_sites = [line for line in content.splitlines() if "Invoke-GovernedScript -ScriptPath" in line]
    assert len(call_sites) == 10
    # Every one of those call sites supplies an explicit bound (plus one
    # more -TimeoutSeconds inside Invoke-GovernedScript's own definition,
    # plus three more for GetCurrentState's two Get-RemoteImageSourceGitSha
    # reads (app + scheduler) and its Get-RemoteStaticGenerationSourceGitSha
    # read).
    assert content.count("-TimeoutSeconds") == 14


def test_does_not_duplicate_low_level_release_logic():
    content = SCRIPT.read_text(encoding="utf-8")
    # This script must only ORCHESTRATE the existing governed scripts, never
    # reimplement their internals.
    assert "docker buildx build" not in content
    assert "docker save" not in content
    assert "ConvertTo-FramedJsonRecord" not in content
    for existing_script in [
        "build-release-image.ps1", "package-release-image.ps1",
        "package-static-release.ps1", "deploy-release-image.ps1",
        "deploy-static-release.ps1", "rollback-release.ps1",
        "rollback-static-release.ps1", "preflight-production.ps1",
    ]:
        assert existing_script in content, f"expected {existing_script} to be wired as a phase executor"


def test_gate_required_string_matches_state_machine_authority_model():
    content = SCRIPT.read_text(encoding="utf-8")
    assert "GO_DEPLOY_WITH_BOUNDED_RECOVERY" in content
    assert "Assert-OwnerGate" in content
