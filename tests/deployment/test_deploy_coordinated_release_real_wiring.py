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
REALISTIC_SCHEDULER_IMAGE_ID = "sha256:" + "fedcba0987654321" * 4
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


def _verify_rollback_ready_block() -> str:
    return _extract_block("$VerifyRollbackReady = {", "$PromoteStatic = {")


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
$deployStaticScript = 'deploy-static-release.ps1'
$verifyProductionScript = 'verify-production-release.ps1'
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
$script:FakeCurrentSchedulerSha = '{EXPECTED_SHA}'
$script:FakeCurrentStaticSha = '{EXPECTED_SHA}'
function Get-RemoteImageSourceGitSha {{
    param([string]$SshAlias, [string]$ImageId, [int]$TimeoutSeconds = 30)
    if ($ImageId -eq '{REALISTIC_APP_IMAGE_ID}') {{ return $script:FakeCurrentAppSha }}
    if ($ImageId -eq '{REALISTIC_SCHEDULER_IMAGE_ID}') {{ return $script:FakeCurrentSchedulerSha }}
    throw "unexpected image id passed: $ImageId"
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
  "current_scheduler": {{
    "image_id": "{REALISTIC_SCHEDULER_IMAGE_ID}",
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
    assert result["scheduler_sha"] == EXPECTED_SHA
    assert result["static_sha"] == EXPECTED_SHA
    assert result["app_sha"] != f"go-odyssey-app:{EXPECTED_SHA[:8]}"
    assert result["static_sha"] != REALISTIC_STATIC_GENERATION_PATH
    # Non-SHA identity fields are preserved, separately, exactly as reported.
    assert result["app_image_tag"] == f"go-odyssey-app:{EXPECTED_SHA[:8]}"
    assert result["app_image_id"] == REALISTIC_APP_IMAGE_ID
    assert result["scheduler_image_id"] == REALISTIC_SCHEDULER_IMAGE_ID
    assert result["static_generation_path"] == REALISTIC_STATIC_GENERATION_PATH
    # The scheduler identity is read from the SCHEDULER's own image, never
    # assumed to equal the app's.
    assert result["scheduler_image_id"] != result["app_image_id"]


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
    assert result["scheduler_sha"] == EXPECTED_SHA
    assert result["static_sha"] == EXPECTED_SHA
    assert result["static_generation_path"] == REALISTIC_STATIC_GENERATION_PATH
    assert result["app_image_id"] == REALISTIC_APP_IMAGE_ID
    assert result["scheduler_image_id"] == REALISTIC_SCHEDULER_IMAGE_ID


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


# ---------------------------------------------------------------------------
# Coordinator review #3: PROMOTE_STATIC's postcondition is not "the active
# generation's manifest reports the candidate SHA". deploy-static-release.ps1
# also performs the post-switch container restart / mount refresh and public
# static-byte verification. These exercise the REAL $VerifyStatic executor
# extracted from the orchestrator source, with only the external boundary
# (Invoke-GovernedScript / the two remote SHA readers) faked.
# ---------------------------------------------------------------------------

def _verify_static_block() -> str:
    return _extract_block("$VerifyStatic = {", "$PromoteApp = {")


def _run_verify_static(*, preflight_verification: str, current_static_sha: str | None = None) -> dict:
    """Runs the real $VerifyStatic with a faked canonical-verification result.

    `preflight_verification` is the PowerShell expression Invoke-GovernedScript
    returns for the -StaticManifest verification call (the second preflight
    invocation); the first (identity) call always succeeds with the realistic
    preflight shape.
    """
    static_sha_override = ""
    if current_static_sha is not None:
        static_sha_override = f"$script:FakeCurrentStaticSha = '{current_static_sha}'\n"
    dependency_overrides = f"""
{static_sha_override}$script:CapturedStaticManifestArg = $null
$script:PreflightCallCount = 0
function Invoke-GovernedScript {{
    param([string]$ScriptPath, [string[]]$Arguments, [int]$TimeoutSeconds, [string]$OperationLabel)
    # The public acceptance stage is exercised separately by
    # _run_verify_static_with_public; keep it clean here so these tests
    # isolate the live-generation/health stage.
    if ($ScriptPath -eq $deployStaticScript) {{
        return [ordered]@{{ success = $true; data = [pscustomobject]@{{ result = 'PUBLIC_STATIC_ACCEPTANCE_VERIFIED' }} }}
    }}
    if ($ScriptPath -ne $preflightScript) {{ throw "unexpected script invoked: $ScriptPath" }}
    $script:PreflightCallCount = $script:PreflightCallCount + 1
    if ($Arguments -contains '-StaticManifest') {{
        $idx = [array]::IndexOf($Arguments, '-StaticManifest')
        $script:CapturedStaticManifestArg = $Arguments[$idx + 1]
        return {preflight_verification}
    }}
    # identity read (GetCurrentState)
    return [ordered]@{{ success = $true; data = (@'
{REALISTIC_PREFLIGHT_JSON}
'@ | ConvertFrom-Json) }}
}}
"""
    invocation = (
        "$r = & $VerifyStatic $null\n"
        "[ordered]@{ success = $r.success; detail = $r.detail; "
        "captured_static_manifest = $script:CapturedStaticManifestArg; "
        "preflight_call_count = $script:PreflightCallCount } | ConvertTo-Json -Compress\n"
    )
    extracted = _get_current_state_block() + "\n" + _verify_static_block()
    return run_probe(
        dependency_overrides=dependency_overrides,
        extracted_blocks=extracted,
        invocation=invocation,
    )


CLEAN_STATIC_VERIFICATION = (
    "[ordered]@{ success = $true; data = [pscustomobject]@{ "
    "static_generation = [pscustomobject]@{ drift_checked = $true; drift = $false } } }"
)


# --- A: identity candidate, canonical static verification FAILS ------------

def test_a_verify_static_rejects_identity_only_when_canonical_verification_fails():
    result = _run_verify_static(
        preflight_verification=(
            "[ordered]@{ success = $false; timed_out = $false; "
            "output = 'STATIC GENERATION DRIFT: production live-static current does not match the declared static release manifest'; "
            "data = $null }"
        )
    )
    assert result["success"] is False, (
        "candidate static identity alone must not satisfy the static postcondition"
    )
    assert "canonical static verification did not pass" in result["detail"]
    assert "DRIFT" in result["detail"]


def test_a_verify_static_rejects_reported_drift_even_when_verification_exits_zero():
    # Defence in depth: even if the drift gate were ever downgraded from a
    # throw to a soft report, a drift=true payload must still fail closed.
    result = _run_verify_static(
        preflight_verification=(
            "[ordered]@{ success = $true; data = [pscustomobject]@{ "
            "static_generation = [pscustomobject]@{ drift_checked = $true; drift = $true } } }"
        )
    )
    assert result["success"] is False
    assert "drift" in result["detail"].lower()


def test_a_verify_static_rejects_when_drift_was_never_actually_checked():
    # -StaticManifest is what arms preflight's drift gate; without it
    # drift_checked is false and the gate is a no-op. That must never be
    # accepted as a proven postcondition.
    result = _run_verify_static(
        preflight_verification=(
            "[ordered]@{ success = $true; data = [pscustomobject]@{ "
            "static_generation = [pscustomobject]@{ drift_checked = $false; drift = $null } } }"
        )
    )
    assert result["success"] is False
    assert "drift_checked" in result["detail"]


# --- B: identity candidate, app/scheduler readiness NOT proven -------------

def test_b_verify_static_rejects_when_app_scheduler_post_switch_readiness_is_not_proven():
    # preflight's Assert-ContainerSnapshotValid throws when a container is not
    # running / is restarting / is unhealthy -- i.e. the post-switch restart
    # and mount refresh did not actually complete. That surfaces as a
    # non-zero exit from the verification call.
    result = _run_verify_static(
        preflight_verification=(
            "[ordered]@{ success = $false; timed_out = $false; "
            "output = 'Scheduler container is not running.'; data = $null }"
        )
    )
    assert result["success"] is False
    assert "canonical static verification did not pass" in result["detail"]
    assert "Scheduler container is not running" in result["detail"]


def test_b_verify_static_rejects_when_healthz_gate_fails_after_static_switch():
    result = _run_verify_static(
        preflight_verification=(
            "[ordered]@{ success = $false; timed_out = $false; "
            "output = '/healthz did not return 200.'; data = $null }"
        )
    )
    assert result["success"] is False
    assert "/healthz did not return 200" in result["detail"]


# --- C: identity candidate AND full canonical verification passes ----------

def test_c_verify_static_passes_only_when_full_canonical_verification_passes():
    result = _run_verify_static(preflight_verification=CLEAN_STATIC_VERIFICATION)
    assert result["success"] is True
    # It really did run the canonical verification in addition to the
    # identity read (two preflight invocations, not one).
    assert result["preflight_call_count"] == 2


def test_verify_static_passes_the_candidate_static_manifest_to_the_canonical_verifier():
    # Load-bearing: without -StaticManifest, preflight's per-file sha256
    # drift gate is a no-op, so this argument is what makes the check real.
    result = _run_verify_static(preflight_verification=CLEAN_STATIC_VERIFICATION)
    assert result["success"] is True
    assert result["captured_static_manifest"], "-StaticManifest must be passed to the canonical verifier"
    assert result["captured_static_manifest"].endswith(".static.json")


def test_verify_static_rejects_a_non_candidate_static_identity_before_verifying():
    # If the active generation is not even on the candidate SHA, fail on
    # identity without spending a canonical verification round-trip.
    result = _run_verify_static(
        preflight_verification=CLEAN_STATIC_VERIFICATION,
        current_static_sha=BASELINE_SHA,
    )
    assert result["success"] is False
    assert "not on the candidate" in result["detail"]
    assert result["preflight_call_count"] == 1


def test_verify_static_fails_closed_when_no_candidate_static_manifest_is_known():
    dependency_overrides = f"""
$script:staticManifestPath = ''
function Invoke-GovernedScript {{
    param([string]$ScriptPath, [string[]]$Arguments, [int]$TimeoutSeconds, [string]$OperationLabel)
    if ($Arguments -contains '-StaticManifest') {{ throw 'must not attempt verification without a manifest' }}
    return [ordered]@{{ success = $true; data = (@'
{REALISTIC_PREFLIGHT_JSON}
'@ | ConvertFrom-Json) }}
}}
"""
    invocation = "(& $VerifyStatic $null) | ConvertTo-Json -Compress"
    extracted = _get_current_state_block() + "\n" + _verify_static_block()
    result = run_probe(
        dependency_overrides=dependency_overrides,
        extracted_blocks=extracted,
        invocation=invocation,
    )
    assert result["success"] is False
    assert "static manifest" in result["detail"]


def test_verify_static_source_is_not_an_identity_only_check():
    # Source-level regression guard against silently reverting to
    # `success = ($state.static_sha -eq $ExpectedGitSha)`.
    block = _verify_static_block()
    assert "Invoke-GovernedScript" in block, "VerifyStatic must run a canonical verification, not identity alone"
    assert "-StaticManifest" in block
    assert "drift_checked" in block


# ---------------------------------------------------------------------------
# Coordinator review #4: preflight proves live-generation hashes and container
# health, but NOT deploy-static-release.ps1's PUBLIC acceptance contract
# (served-byte SHAs, authenticated-route contracts, public sw.js VERSION, and
# /healthz/static-release generation + index_sha256 provenance). VerifyStatic
# must prove that too, via the canonical read-only -VerifyOnly entrypoint.
# ---------------------------------------------------------------------------

CLEAN_PUBLIC_ACCEPTANCE = (
    "[ordered]@{ success = $true; data = [pscustomobject]@{ "
    "result = 'PUBLIC_STATIC_ACCEPTANCE_VERIFIED'; public_hash_verified = $true; "
    "public_sw_version_verified = $true; public_static_provenance_verified = $true } }"
)


def _run_verify_static_with_public(*, public_acceptance: str, preflight_verification: str | None = None) -> dict:
    """Runs the real $VerifyStatic with both canonical verifications faked.

    The preflight (-StaticManifest) call defaults to clean, so these tests
    isolate the PUBLIC acceptance stage specifically.
    """
    if preflight_verification is None:
        preflight_verification = CLEAN_STATIC_VERIFICATION
    dependency_overrides = f"""
$script:CapturedVerifyOnlyArgs = $null
$script:UsedExecute = $false
function Invoke-GovernedScript {{
    param([string]$ScriptPath, [string[]]$Arguments, [int]$TimeoutSeconds, [string]$OperationLabel)
    if ($ScriptPath -eq $deployStaticScript) {{
        $script:CapturedVerifyOnlyArgs = $Arguments
        if ($Arguments -contains '-Execute') {{ $script:UsedExecute = $true }}
        return {public_acceptance}
    }}
    if ($ScriptPath -ne $preflightScript) {{ throw "unexpected script invoked: $ScriptPath" }}
    if ($Arguments -contains '-StaticManifest') {{ return {preflight_verification} }}
    return [ordered]@{{ success = $true; data = (@'
{REALISTIC_PREFLIGHT_JSON}
'@ | ConvertFrom-Json) }}
}}
"""
    invocation = (
        "$r = & $VerifyStatic $null\n"
        "[ordered]@{ success = $r.success; detail = $r.detail; "
        "verify_only_args = ($script:CapturedVerifyOnlyArgs -join ' '); "
        "used_execute = $script:UsedExecute } | ConvertTo-Json -Compress\n"
    )
    extracted = _get_current_state_block() + "\n" + _verify_static_block()
    return run_probe(
        dependency_overrides=dependency_overrides,
        extracted_blocks=extracted,
        invocation=invocation,
    )


# --- A: live generation + containers healthy, but public bytes are wrong ---

def test_a_static_public_wrong_bytes_must_not_advance():
    result = _run_verify_static_with_public(
        public_acceptance=(
            "[ordered]@{ success = $false; timed_out = $false; "
            "output = 'Public content verification failed: total=16, completed=16, passed=15, failures=1. "
            "Details: {\"hash_mismatch\":1}'; data = $null }"
        )
    )
    assert result["success"] is False, (
        "live-generation hashes + healthy containers must not be accepted while "
        "the publicly served bytes are still the old release"
    )
    assert "canonical public static acceptance contract did not pass" in result["detail"]
    assert "hash_mismatch" in result["detail"]


# --- B: public bytes pass, but public sw.js VERSION is wrong ---------------

def test_b_static_public_wrong_sw_version_must_not_advance():
    result = _run_verify_static_with_public(
        public_acceptance=(
            "[ordered]@{ success = $false; timed_out = $false; "
            "output = \"Public sw.js VERSION mismatch after switch. Expected '20260818a', observed '20260810z'.\"; "
            "data = $null }"
        )
    )
    assert result["success"] is False
    assert "sw.js VERSION mismatch" in result["detail"]


# --- C: bytes + SW pass, but /healthz/static-release provenance is wrong ---

def test_c_static_public_wrong_provenance_must_not_advance():
    result = _run_verify_static_with_public(
        public_acceptance=(
            "[ordered]@{ success = $false; timed_out = $false; "
            "output = \"Public static provenance mismatch. Expected generation "
            "'20260818-010203-abcdef12-cand' and index SHA 'aa11', observed \"; data = $null }"
        )
    )
    assert result["success"] is False
    assert "Public static provenance mismatch" in result["detail"]


def test_c_static_public_acceptance_without_verified_result_marker_must_not_advance():
    # Exit code 0 is not enough on its own -- the canonical verifier must
    # positively report that it verified the acceptance contract.
    result = _run_verify_static_with_public(
        public_acceptance="[ordered]@{ success = $true; data = [pscustomobject]@{ result = 'DRY_RUN_COMPLETE' } }"
    )
    assert result["success"] is False
    assert "did not report a verified result" in result["detail"]


# --- D: everything passes -> may advance ----------------------------------

def test_d_full_public_and_runtime_and_identity_postcondition_passes():
    result = _run_verify_static_with_public(public_acceptance=CLEAN_PUBLIC_ACCEPTANCE)
    assert result["success"] is True


def test_d_public_acceptance_is_invoked_read_only_never_as_a_mutation():
    result = _run_verify_static_with_public(public_acceptance=CLEAN_PUBLIC_ACCEPTANCE)
    assert result["success"] is True
    args = result["verify_only_args"]
    assert "-VerifyOnly" in args, "must use the canonical read-only verification entrypoint"
    assert "-StaticManifest" in args
    assert result["used_execute"] is False, "verification must never invoke a mutating deploy"
    assert "GO_DEPLOY" not in args


def test_public_acceptance_is_skipped_when_the_earlier_live_generation_gate_already_failed():
    # Ordering guard: if preflight's live-generation/health gate fails, that
    # is already disqualifying -- report it rather than the public stage.
    result = _run_verify_static_with_public(
        public_acceptance=CLEAN_PUBLIC_ACCEPTANCE,
        preflight_verification=(
            "[ordered]@{ success = $false; timed_out = $false; "
            "output = 'Scheduler container is not running.'; data = $null }"
        ),
    )
    assert result["success"] is False
    assert "Scheduler container is not running" in result["detail"]


# ---------------------------------------------------------------------------
# Production baseline reconciliation: the real coordinator may admit the
# one tracked 70f7-runtime/a2f33-static pair, but only after exact identity
# matching. The metadata is local and tracked; these probes never contact
# Production or invoke a mutating phase.
# ---------------------------------------------------------------------------

KNOWN_PAIR = REPO_ROOT / "deploy" / "known-production-rollback-pairs.json"


def test_historical_rollback_pair_metadata_is_exact_and_positive_provenance_bound():
    document = json.loads(KNOWN_PAIR.read_text(encoding="utf-8"))
    assert document["schema"] == "go-odyssey-production-rollback-pair-v1"
    assert document["provenance_policy"] == {
        "mixed_pair_acceptance": "exact_record_only",
        "same_sha_pair_acceptance": "strict_identity_coherence",
    }
    assert len(document["pairs"]) == 1
    pair = document["pairs"][0]
    assert pair["pair_id"] == "production-70f7-runtime-a2f33-static-overlay-20260914"
    assert pair["runtime_source_sha"] == "70f7ed5067e8163eb7bc4cf1cfc664baec06f496"
    assert pair["scheduler_source_sha"] == pair["runtime_source_sha"]
    assert pair["static_source_sha"] == "a2f33eb0b1b567f02d6e46fbe4d19f6a13c358c8"
    assert pair["static_overlay"] is True
    assert pair["schema_migration_required"] is False
    assert pair["schema_fingerprint"] == "5ebf4094dcec631137efe27e3ae38db8ccfde82068a33b2043c3399363dbd3c1"
    assert len(pair["evidence"]["runtime_release_records"]) == 2
    assert pair["evidence"]["compatibility_basis"]


def test_real_pair_document_validator_rejects_a_record_without_compatibility_evidence():
    validator_block = _extract_block(
        "function Get-HistoricalRollbackPairField {",
        "$historicalRollbackPairs =",
    )
    probe = f"""
$ErrorActionPreference = 'Stop'
Import-Module '{STATE_MACHINE_MODULE.as_posix()}' -Force -DisableNameChecking
function Fail($message) {{ throw $message }}
$historicalRollbackPairsPath = '{KNOWN_PAIR.as_posix()}'
{validator_block}
$document = Get-Content -Raw -LiteralPath '{KNOWN_PAIR.as_posix()}' | ConvertFrom-Json
$valid = @(Assert-HistoricalRollbackPairDocument -Document $document)
$broken = Get-Content -Raw -LiteralPath '{KNOWN_PAIR.as_posix()}' | ConvertFrom-Json
$broken.pairs[0].evidence.compatibility_basis = @()
$rejected = $false
try {{ Assert-HistoricalRollbackPairDocument -Document $broken | Out-Null }}
catch {{ $rejected = $true }}
$schema_broken = Get-Content -Raw -LiteralPath '{KNOWN_PAIR.as_posix()}' | ConvertFrom-Json
$schema_broken.pairs[0].schema_migration_required = $true
$schema_rejected = $false
try {{ Assert-HistoricalRollbackPairDocument -Document $schema_broken | Out-Null }}
catch {{ $schema_rejected = $true }}
[ordered]@{{ valid_count = $valid.Count; broken_rejected = $rejected; schema_rejected = $schema_rejected }} | ConvertTo-Json -Compress
"""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", probe],
        cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", timeout=20, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout.strip().splitlines()[-1]) == {
        "valid_count": 1,
        "broken_rejected": True,
        "schema_rejected": True,
    }


def test_coordinator_uses_exact_historical_pair_validator_and_keeps_default_strict_gate():
    content = ORCHESTRATOR.read_text(encoding="utf-8")
    assert "known-production-rollback-pairs.json" in content
    assert "Assert-HistoricalRollbackPairDocument" in content
    assert "Test-ProvenHistoricalMixedBaseline" in content
    assert "Test-ReleaseBaselineIdentityAccepted" in content
    assert "-ProvenMixedBaselineValidator $ProvenMixedBaselineValidator" in content
    assert "static_generation_path = $state.static_generation_path" in content
    assert "app_image_tag = $state.app_image_tag" in content
    assert "scheduler_image_tag = $state.scheduler_image_tag" in content
    # The real coordinator does not replace the default same-SHA validator or
    # accept mixed state from a non-empty SHA/path alone.
    assert "Test-ReleaseIdentityCoherent -State $baseline" not in content
    assert "exact_record_only" in content
    assert "schema_migration_required" in content


def test_real_historical_pair_matcher_accepts_only_the_exact_runtime_static_identity():
    pair = json.loads(KNOWN_PAIR.read_text(encoding="utf-8"))["pairs"][0]
    matcher_dependencies = _extract_block(
        "function Get-HistoricalRollbackPairField {",
        "function Assert-HistoricalRollbackPairDocument {",
    )
    matcher_block = _extract_block(
        "function Test-ProvenHistoricalMixedBaseline {",
        "$releaseArtifactsDir =",
    )
    def ps(value: str) -> str:
        return "'" + value.replace("'", "''") + "'"

    state_fields = {
        "app_sha": pair["runtime_source_sha"],
        "scheduler_sha": pair["scheduler_source_sha"],
        "static_sha": pair["static_source_sha"],
        "app_image_tag": pair["runtime_image_tag"],
        "app_image_id": pair["runtime_image_id"],
        "scheduler_image_tag": pair["scheduler_image_tag"],
        "scheduler_image_id": pair["scheduler_image_id"],
        "static_generation_path": pair["static_generation_path"],
    }
    fields_literal = "\n".join(f"    {name} = {ps(value)}" for name, value in state_fields.items())
    pair_fields = {
        "runtime_source_sha": pair["runtime_source_sha"],
        "scheduler_source_sha": pair["scheduler_source_sha"],
        "static_source_sha": pair["static_source_sha"],
        "runtime_image_tag": pair["runtime_image_tag"],
        "runtime_image_id": pair["runtime_image_id"],
        "scheduler_image_tag": pair["scheduler_image_tag"],
        "scheduler_image_id": pair["scheduler_image_id"],
        "static_generation_path": pair["static_generation_path"],
    }
    pair_fields_literal = "\n".join(f"    {name} = {ps(value)}" for name, value in pair_fields.items())
    probe = FAKE_DEPENDENCIES_PREAMBLE + f"""
{matcher_dependencies}
{matcher_block}
$pair = [pscustomobject]@{{
{pair_fields_literal}
}}
$good = [pscustomobject]@{{
{fields_literal}
}}
$bad = $good | Select-Object *
$bad.static_generation_path = $good.static_generation_path + '-tampered'
$missing = $good | Select-Object *
$missing.scheduler_image_id = ''
[ordered]@{{
    good = (Test-ProvenHistoricalMixedBaseline -State $good -Pairs @($pair))
    bad_path = (Test-ProvenHistoricalMixedBaseline -State $bad -Pairs @($pair))
    missing_image = (Test-ProvenHistoricalMixedBaseline -State $missing -Pairs @($pair))
}} | ConvertTo-Json -Compress
"""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", probe],
        cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", timeout=20, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload == {"good": True, "bad_path": False, "missing_image": False}


def test_real_verify_rollback_ready_uses_the_same_proven_mixed_baseline_policy():
    baseline = """
[pscustomobject]@{
    app_sha = 'd'*40
    scheduler_sha = 'd'*40
    static_sha = 'e'*40
    static_generation_path = '/opt/go-odyssey-static/releases/proven'
}
"""
    probe = FAKE_DEPENDENCIES_PREAMBLE + f"""
$ProvenMixedBaselineValidator = {{ param($state) return [bool]$script:AllowProven }}
$baseline = {baseline}
{_verify_rollback_ready_block()}
$script:AllowProven = $true
$accepted = & $VerifyRollbackReady $baseline
$script:AllowProven = $false
$rejected = & $VerifyRollbackReady $baseline
[ordered]@{{ accepted = $accepted.success; rejected = $rejected.success; rejected_is_incoherent = $rejected.baseline_incoherent }} | ConvertTo-Json -Compress
"""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", probe],
        cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", timeout=20, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout.strip().splitlines()[-1]) == {
        "accepted": True,
        "rejected": False,
        "rejected_is_incoherent": True,
    }
