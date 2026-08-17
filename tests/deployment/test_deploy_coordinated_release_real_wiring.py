"""Coordinator-review follow-up: integration-level contract coverage for the
REAL phase-executor wiring in scripts/release/deploy-coordinated-release.ps1
-- not the simplified "every identity happens to be a 40-char Git SHA"
shapes used by test_coordinated_release_state_machine.py's fault-injection
suite.

Each test extracts the actual `$PhaseName = { ... }.GetNewClosure()` source
block(s) from the real orchestrator script (same source-slicing technique as
test_deploy_coordinated_release_cli.py and the established
production_function_block() pattern elsewhere in this suite), then executes
that REAL code with only the external-boundary dependency
(Invoke-GovernedScript, and the two new Get-RemoteImageSourceGitSha /
Get-RemoteStaticGenerationSourceGitSha functions) replaced by fakes that
return realistic canned data shaped exactly like the real underlying
scripts' actual JSON output (a Docker image tag for image_ref, a content
digest for image_id, a filesystem path for static_generation.current_target,
a deployment_record_path field, etc.) -- proving the field-mapping/identity-
domain logic itself, not just a synthetic happy path. No Docker, SSH, or
Production contact.
"""

from __future__ import annotations

import json
import pathlib
import subprocess

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
ORCHESTRATOR = REPO_ROOT / "scripts" / "release" / "deploy-coordinated-release.ps1"
MODULE = REPO_ROOT / "scripts" / "release" / "ReleaseTooling.psm1"
STATE_MACHINE_MODULE = REPO_ROOT / "scripts" / "release" / "CoordinatedReleaseStateMachine.psm1"

EXPECTED_SHA = "c" * 40
BASELINE_SHA = "d" * 40
REALISTIC_APP_IMAGE_ID = "sha256:" + "1234567890abcdef" * 4
REALISTIC_STATIC_GENERATION_PATH = "/opt/go-odyssey-static/releases/20260817-abcdef1"
BASELINE_STATIC_GENERATION_PATH = "/opt/go-odyssey-static/releases/20260810-fedcba9"


def _extract_block(start_marker: str, end_marker: str) -> str:
    source = ORCHESTRATOR.read_text(encoding="utf-8")
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    return source[start:end]


def _get_current_state_block() -> str:
    return _extract_block("$GetCurrentState = {", "$Precheck = {")


def _snapshot_baseline_block() -> str:
    return _extract_block("$SnapshotBaseline = {", "$VerifyRollbackReady = {")


def _promote_app_block() -> str:
    return _extract_block("$PromoteApp = {", "$VerifyApp = {")


def _rollback_app_block() -> str:
    return _extract_block("$RollbackApp = {", "$result = Invoke-CoordinatedReleaseStateMachine")


def _rollback_static_block() -> str:
    return _extract_block("$RollbackStatic = {", "$RollbackApp = {")


FAKE_DEPENDENCIES_PREAMBLE = f"""
$OutputEncoding = [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$ErrorActionPreference = 'Stop'
Import-Module '{MODULE.as_posix()}' -Force -DisableNameChecking
Import-Module '{STATE_MACHINE_MODULE.as_posix()}' -Force -DisableNameChecking

$ExpectedGitSha = '{EXPECTED_SHA}'
$LayoutFile = 'deploy\\release-layout.example.json'
$layout = [pscustomobject]@{{ ssh_alias = 'fake-host' }}
$preflightScript = 'preflight-production.ps1'
$deployAppScript = 'deploy-release-image.ps1'
$rollbackAppScript = 'rollback-release.ps1'
$rollbackStaticScript = 'rollback-static-release.ps1'
$script:appReleaseManifestPath = 'D:\\fake\\release-artifacts\\{EXPECTED_SHA[:8]}.release.json'
$script:appArchivePath = 'D:\\fake\\release-artifacts\\{EXPECTED_SHA[:8]}.tar'
$script:appDeploymentRecordPath = $null
$script:staticManifestPath = 'D:\\fake\\release-artifacts\\{EXPECTED_SHA[:8]}.static.json'
$script:staticBundlePath = 'D:\\fake\\release-artifacts\\{EXPECTED_SHA[:8]}-bundle'
$script:staticArchivePath = 'D:\\fake\\release-artifacts\\{EXPECTED_SHA[:8]}.static.tar'

# Realistic canned Get-RemoteImageSourceGitSha / Get-RemoteStaticGenerationSourceGitSha
# -- these shadow the real, exported ReleaseTooling.psm1 functions of the
# same name for any call made from scriptblocks defined in THIS session,
# exactly like the established "redefine a dependency, run the real target
# code" pattern (test_canary_readiness_json_channel.py's Invoke-BoundedSshCommand
# override).
$script:FakeCurrentAppSha = '{EXPECTED_SHA}'
$script:FakeCurrentStaticSha = '{EXPECTED_SHA}'
function Get-RemoteImageSourceGitSha {{
    param([string]$SshAlias, [string]$ImageId, [int]$TimeoutSeconds = 30)
    if ($ImageId -ne '{REALISTIC_APP_IMAGE_ID}') {{ throw "unexpected image id passed: $ImageId" }}
    return $script:FakeCurrentAppSha
}}
function Get-RemoteStaticGenerationSourceGitSha {{
    param([string]$SshAlias, [string]$GenerationPath, [int]$TimeoutSeconds = 30)
    if ($GenerationPath -ne '{REALISTIC_STATIC_GENERATION_PATH}') {{ throw "unexpected generation path passed: $GenerationPath" }}
    return $script:FakeCurrentStaticSha
}}
"""


def run_probe(*, dependency_overrides: str, extracted_blocks: str, invocation: str, timeout: int = 20) -> dict:
    script = FAKE_DEPENDENCIES_PREAMBLE + "\n" + dependency_overrides + "\n" + extracted_blocks + "\n" + invocation
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", timeout=timeout, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    text = result.stdout.strip()
    return json.loads(text[text.find("{"):])


REALISTIC_PREFLIGHT_JSON = f"""{{
  "current_app": {{
    "image_id": "{REALISTIC_APP_IMAGE_ID}",
    "image_ref": "go-odyssey-app:{EXPECTED_SHA[:8]}",
    "status": "running",
    "health": "healthy",
    "restart_count": 0
  }},
  "static_generation": {{
    "current_target": "{REALISTIC_STATIC_GENERATION_PATH}",
    "drift_checked": false
  }}
}}"""


# ---------------------------------------------------------------------------
# GetCurrentState: realistic preflight shape -> correct SHA-domain identity,
# with the non-SHA fields kept separate, never compared to ExpectedGitSha.
# ---------------------------------------------------------------------------

def test_get_current_state_derives_real_git_sha_from_realistic_preflight_shape():
    dependency_overrides = f"""
function Invoke-GovernedScript {{
    param([string]$ScriptPath, [string[]]$Arguments, [int]$TimeoutSeconds, [string]$OperationLabel)
    if ($ScriptPath -eq $preflightScript) {{
        return [ordered]@{{ success = $true; data = (@'
{REALISTIC_PREFLIGHT_JSON}
'@ | ConvertFrom-Json) }}
    }}
    throw "unexpected script invoked: $ScriptPath"
}}
"""
    invocation = "(& $GetCurrentState) | ConvertTo-Json -Compress"
    result = run_probe(dependency_overrides=dependency_overrides, extracted_blocks=_get_current_state_block(), invocation=invocation)
    assert result["success"] is True
    # The two fields the state machine actually compares to ExpectedGitSha
    # must be REAL Git SHAs (from the fake OCI-label/manifest reads), not
    # the raw image_ref/current_target values.
    assert result["app_sha"] == EXPECTED_SHA
    assert result["static_sha"] == EXPECTED_SHA
    assert result["app_sha"] != f"go-odyssey-app:{EXPECTED_SHA[:8]}"
    assert result["static_sha"] != REALISTIC_STATIC_GENERATION_PATH
    # Non-SHA identity fields are preserved, separately, exactly as reported.
    assert result["app_image_tag"] == f"go-odyssey-app:{EXPECTED_SHA[:8]}"
    assert result["app_image_id"] == REALISTIC_APP_IMAGE_ID
    assert result["static_generation_path"] == REALISTIC_STATIC_GENERATION_PATH


def test_get_current_state_fails_closed_when_oci_label_read_fails():
    dependency_overrides = f"""
function Invoke-GovernedScript {{
    param([string]$ScriptPath, [string[]]$Arguments, [int]$TimeoutSeconds, [string]$OperationLabel)
    return [ordered]@{{ success = $true; data = (@'
{REALISTIC_PREFLIGHT_JSON}
'@ | ConvertFrom-Json) }}
}}
function Get-RemoteImageSourceGitSha {{
    param([string]$SshAlias, [string]$ImageId, [int]$TimeoutSeconds = 30)
    throw 'simulated: image has no org.opencontainers.image.revision label'
}}
"""
    invocation = "(& $GetCurrentState) | ConvertTo-Json -Compress"
    result = run_probe(dependency_overrides=dependency_overrides, extracted_blocks=_get_current_state_block(), invocation=invocation)
    assert result["success"] is False
    assert "revision" in result["detail"] or "label" in result["detail"]


# ---------------------------------------------------------------------------
# SnapshotBaseline: carries the extra rollback-identity fields through,
# never conflating them with the SHA fields.
# ---------------------------------------------------------------------------

def test_snapshot_baseline_carries_static_generation_path_separately_from_sha():
    dependency_overrides = f"""
function Invoke-GovernedScript {{
    param([string]$ScriptPath, [string[]]$Arguments, [int]$TimeoutSeconds, [string]$OperationLabel)
    return [ordered]@{{ success = $true; data = (@'
{REALISTIC_PREFLIGHT_JSON}
'@ | ConvertFrom-Json) }}
}}
"""
    invocation = "(& $SnapshotBaseline) | ConvertTo-Json -Compress"
    extracted = _get_current_state_block() + "\n" + _snapshot_baseline_block()
    result = run_probe(dependency_overrides=dependency_overrides, extracted_blocks=extracted, invocation=invocation)
    assert result["success"] is True
    assert result["app_sha"] == EXPECTED_SHA
    assert result["static_sha"] == EXPECTED_SHA
    assert result["static_generation_path"] == REALISTIC_STATIC_GENERATION_PATH
    assert result["app_image_id"] == REALISTIC_APP_IMAGE_ID


# ---------------------------------------------------------------------------
# PromoteApp -> RollbackApp: the actionable deployment_record_path handoff,
# not the package-time release manifest.
# ---------------------------------------------------------------------------

def test_promote_app_captures_real_deployment_record_path_not_package_manifest():
    # data MUST be a real PSCustomObject here, not a bare [ordered] hashtable
    # -- ConvertFrom-Json (what the real code path produces) always returns
    # PSCustomObject, and the real $PromoteApp code correctly relies on
    # .PSObject.Properties[...] to check for an optional field, which (per
    # the ReleaseTooling.psm1/CoordinatedReleaseStateMachine.psm1 fixes
    # elsewhere in this task) does NOT reliably detect Hashtable/
    # OrderedDictionary keys -- so the fake must match the real shape.
    dependency_overrides = """
function Invoke-GovernedScript {
    param([string]$ScriptPath, [string[]]$Arguments, [int]$TimeoutSeconds, [string]$OperationLabel)
    if ($ScriptPath -eq $deployAppScript) {
        return [ordered]@{
            success = $true
            data = [pscustomobject]@{
                deployment_record_path = 'D:\\fake\\release-artifacts\\real-deployment-record.deployment.json'
                rollback_image_identity = [pscustomobject]@{ previous_app_release_git_sha = $BaselineSha }
            }
        }
    }
    throw "unexpected script invoked: $ScriptPath"
}
"""
    dependency_overrides = dependency_overrides.replace("$BaselineSha", f"'{BASELINE_SHA}'")
    invocation = "(& $PromoteApp) | Out-Null\n[ordered]@{ deployment_record_path = $script:appDeploymentRecordPath; package_manifest_path = $script:appReleaseManifestPath } | ConvertTo-Json -Compress"
    result = run_probe(dependency_overrides=dependency_overrides, extracted_blocks=_promote_app_block(), invocation=invocation)
    assert result["deployment_record_path"] == "D:\\fake\\release-artifacts\\real-deployment-record.deployment.json"
    assert result["deployment_record_path"] != result["package_manifest_path"], (
        "RollbackApp must use the actionable deployment record, never the package-time release manifest"
    )


def test_promote_app_proactively_computes_deployment_record_path_even_on_failure():
    # deploy-release-image.ps1 saves its deployment record BEFORE the app
    # switch and again in its own failure path -- so even when this phase
    # itself returns success=$false, a usable rollback path must already be
    # known (deterministically computed from Get-ReleaseArtifactBaseName),
    # not left null.
    dependency_overrides = """
function Invoke-GovernedScript {
    param([string]$ScriptPath, [string[]]$Arguments, [int]$TimeoutSeconds, [string]$OperationLabel)
    return [ordered]@{ success = $false; timed_out = $false; output = 'simulated definite failure after mutation' }
}
"""
    invocation = "(& $PromoteApp) | Out-Null\n[ordered]@{ deployment_record_path = $script:appDeploymentRecordPath } | ConvertTo-Json -Compress"
    result = run_probe(dependency_overrides=dependency_overrides, extracted_blocks=_promote_app_block(), invocation=invocation)
    assert result["deployment_record_path"], "a deployment record path must be proactively computed, not left null, even on failure"
    assert result["deployment_record_path"].endswith(".deployment.json")


def test_rollback_app_uses_the_captured_deployment_record_not_the_package_manifest():
    dependency_overrides = """
$script:CapturedRollbackManifestArg = $null
function Invoke-GovernedScript {
    param([string]$ScriptPath, [string[]]$Arguments, [int]$TimeoutSeconds, [string]$OperationLabel)
    if ($ScriptPath -eq $rollbackAppScript) {
        $idx = [array]::IndexOf($Arguments, '-RollbackManifest')
        $script:CapturedRollbackManifestArg = $Arguments[$idx + 1]
        return [ordered]@{ success = $true; data = [ordered]@{ result = 'ok' } }
    }
    throw "unexpected script invoked: $ScriptPath"
}
$script:appDeploymentRecordPath = 'D:\\fake\\release-artifacts\\real-deployment-record.deployment.json'
"""
    invocation = "(& $RollbackApp $null) | Out-Null\n[ordered]@{ captured = $script:CapturedRollbackManifestArg } | ConvertTo-Json -Compress"
    result = run_probe(dependency_overrides=dependency_overrides, extracted_blocks=_rollback_app_block(), invocation=invocation)
    assert result["captured"] == "D:\\fake\\release-artifacts\\real-deployment-record.deployment.json"


def test_rollback_app_fails_closed_when_no_deployment_record_path_known():
    dependency_overrides = "function Invoke-GovernedScript { throw 'must not be called' }\n$script:appDeploymentRecordPath = $null\n"
    invocation = "(& $RollbackApp $null) | ConvertTo-Json -Compress"
    result = run_probe(dependency_overrides=dependency_overrides, extracted_blocks=_rollback_app_block(), invocation=invocation)
    assert result["success"] is False
    assert "deployment record" in result["detail"]


# ---------------------------------------------------------------------------
# RollbackStatic: uses the baseline's generation PATH, never its SHA.
# ---------------------------------------------------------------------------

def test_rollback_static_uses_generation_path_not_sha():
    dependency_overrides = """
$script:CapturedTargetGenerationPathArg = $null
function Invoke-GovernedScript {
    param([string]$ScriptPath, [string[]]$Arguments, [int]$TimeoutSeconds, [string]$OperationLabel)
    if ($ScriptPath -eq $rollbackStaticScript) {
        $idx = [array]::IndexOf($Arguments, '-TargetGenerationPath')
        $script:CapturedTargetGenerationPathArg = $Arguments[$idx + 1]
        return [ordered]@{ success = $true; data = [ordered]@{ result = 'ok' } }
    }
    throw "unexpected script invoked: $ScriptPath"
}
"""
    baseline_literal = (
        "[pscustomobject]@{ app_sha = '" + BASELINE_SHA + "'; static_sha = '" + BASELINE_SHA
        + "'; static_generation_path = '" + BASELINE_STATIC_GENERATION_PATH + "' }"
    )
    invocation = f"(& $RollbackStatic ({baseline_literal})) | Out-Null\n[ordered]@{{ captured = $script:CapturedTargetGenerationPathArg }} | ConvertTo-Json -Compress"
    result = run_probe(dependency_overrides=dependency_overrides, extracted_blocks=_rollback_static_block(), invocation=invocation)
    assert result["captured"] == BASELINE_STATIC_GENERATION_PATH
    assert result["captured"] != BASELINE_SHA


def test_rollback_static_fails_closed_when_baseline_has_no_generation_path():
    dependency_overrides = "function Invoke-GovernedScript { throw 'must not be called' }\n"
    baseline_literal = "[pscustomobject]@{ app_sha = '" + BASELINE_SHA + "'; static_sha = '" + BASELINE_SHA + "'; static_generation_path = '' }"
    invocation = f"(& $RollbackStatic ({baseline_literal})) | ConvertTo-Json -Compress"
    result = run_probe(dependency_overrides=dependency_overrides, extracted_blocks=_rollback_static_block(), invocation=invocation)
    assert result["success"] is False
    assert "generation path" in result["detail"]


# ---------------------------------------------------------------------------
# Invoke-GovernedScript itself: timeout vs. ordinary failure, against the
# REAL function (not faked) with a REAL bounded child process.
# ---------------------------------------------------------------------------

def test_invoke_governed_script_distinguishes_real_timeout_from_ordinary_failure(tmp_path):
    # Invoke-GovernedScript's contract always runs `powershell -File $ScriptPath`
    # -- $ScriptPath must be a real .ps1 FILE, not an arbitrary executable
    # (passing powershell.exe itself as $ScriptPath, as an earlier version
    # of this test mistakenly did, makes it try to -File "run" the
    # interpreter as a script, which fails almost instantly rather than
    # hanging -- a test bug, not a product bug).
    hang_script = tmp_path / "hang.ps1"
    hang_script.write_text("Start-Sleep -Seconds 999\n", encoding="utf-8")
    fail_script = tmp_path / "fail.ps1"
    fail_script.write_text("exit 3\n", encoding="utf-8")

    invoke_governed_script_block = _extract_block("function Invoke-GovernedScript {", "$GetCurrentState = {")
    script = (
        "$OutputEncoding = [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)\n"
        "$ErrorActionPreference = 'Stop'\n"
        f"Import-Module '{MODULE.as_posix()}' -Force -DisableNameChecking\n"
        + invoke_governed_script_block
        + f"\n$timeoutResult = Invoke-GovernedScript -ScriptPath '{hang_script.as_posix()}' "
        "-Arguments @('-NoLogo') -TimeoutSeconds 2 -OperationLabel 'probe: real timeout'\n"
        f"$ordinaryFailureResult = Invoke-GovernedScript -ScriptPath '{fail_script.as_posix()}' "
        "-Arguments @('-NoLogo') -TimeoutSeconds 15 -OperationLabel 'probe: ordinary failure'\n"
        "[ordered]@{ "
        "timeout_success = $timeoutResult.success; timeout_timed_out = $timeoutResult.timed_out; "
        "ordinary_success = $ordinaryFailureResult.success; ordinary_timed_out = $ordinaryFailureResult.timed_out; "
        "ordinary_exit_code = $ordinaryFailureResult.exit_code "
        "} | ConvertTo-Json -Compress\n"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", timeout=30, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["timeout_success"] is False
    assert payload["timeout_timed_out"] is True
    assert payload["ordinary_success"] is False
    assert payload["ordinary_timed_out"] is False
    assert payload["ordinary_exit_code"] == 3
