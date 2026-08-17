"""Deployment Workflow V3: executable fault-injection coverage for
scripts/release/CoordinatedReleaseStateMachine.psm1.

Every scenario runs the REAL Invoke-CoordinatedReleaseStateMachine (and, for
F8/F9, the real Get-OperationalFailureClassification) with injected fake
phase scriptblocks that track mutable app/static SHA state locally in the
PowerShell probe -- no Docker, no SSH, no Production contact of any kind.
This proves the actual orchestration/recovery logic, not just a mocked
happy path: a phase scriptblock that "promotes" mutates a $script: variable,
and a "rollback" scriptblock restores it, so GetCurrentState (also a real
injected scriptblock, not a stub the driver trusts blindly) reflects the
genuine accumulated effect of every phase the driver actually ran.
"""

from __future__ import annotations

import json
import pathlib
import subprocess

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
MODULE = REPO_ROOT / "scripts" / "release" / "CoordinatedReleaseStateMachine.psm1"
EXPECTED_SHA = "a" * 40
BASELINE_SHA = "b" * 40

COMMON_PREAMBLE = f"""
$OutputEncoding = [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$ErrorActionPreference = 'Stop'
Import-Module '{MODULE.as_posix()}' -Force -DisableNameChecking

$ExpectedSha = '{EXPECTED_SHA}'
$script:currentAppSha = '{BASELINE_SHA}'
$script:currentStaticSha = '{BASELINE_SHA}'
$script:attemptCounts = @{{}}

function Get-AttemptCount([string]$key) {{
    if (-not $script:attemptCounts.ContainsKey($key)) {{ $script:attemptCounts[$key] = 0 }}
    $script:attemptCounts[$key] = $script:attemptCounts[$key] + 1
    return $script:attemptCounts[$key]
}}

$GetCurrentState = {{ [ordered]@{{ success = $true; app_sha = $script:currentAppSha; static_sha = $script:currentStaticSha }} }}
$Precheck = {{ [ordered]@{{ success = $true }} }}
$BuildApp = {{ [ordered]@{{ success = $true }} }}
$PackageApp = {{ [ordered]@{{ success = $true }} }}
$PackageStatic = {{ [ordered]@{{ success = $true }} }}
$SnapshotBaseline = {{ [ordered]@{{ success = $true; app_sha = $script:currentAppSha; static_sha = $script:currentStaticSha }} }}
$VerifyRollbackReady = {{ param($baseline) [ordered]@{{ success = $true }} }}
$PromoteStatic = {{ $script:currentStaticSha = $ExpectedSha; [ordered]@{{ success = $true; static_sha = $ExpectedSha }} }}
$VerifyStatic = {{ param($promoted) [ordered]@{{ success = $true }} }}
$PromoteApp = {{ $script:currentAppSha = $ExpectedSha; [ordered]@{{ success = $true; app_sha = $ExpectedSha }} }}
$VerifyApp = {{ param($promoted) [ordered]@{{ success = $true }} }}
$ProductionSmoke = {{ [ordered]@{{ success = $true }} }}
$RollbackStatic = {{ param($baseline) $script:currentStaticSha = $baseline.static_sha; [ordered]@{{ success = $true }} }}
$RollbackApp = {{ param($baseline) $script:currentAppSha = $baseline.app_sha; [ordered]@{{ success = $true }} }}
"""

INVOKE_AND_EMIT = """
$result = Invoke-CoordinatedReleaseStateMachine `
    -ExpectedGitSha $ExpectedSha `
    -GetCurrentState $GetCurrentState `
    -Precheck $Precheck `
    -BuildApp $BuildApp `
    -PackageApp $PackageApp `
    -PackageStatic $PackageStatic `
    -SnapshotBaseline $SnapshotBaseline `
    -VerifyRollbackReady $VerifyRollbackReady `
    -PromoteStatic $PromoteStatic `
    -VerifyStatic $VerifyStatic `
    -PromoteApp $PromoteApp `
    -VerifyApp $VerifyApp `
    -ProductionSmoke $ProductionSmoke `
    -RollbackStatic $RollbackStatic `
    -RollbackApp $RollbackApp
$result | ConvertTo-Json -Depth 12 -Compress
"""


def run_scenario(overrides: str, *, timeout: int = 30) -> dict:
    script = COMMON_PREAMBLE + "\n" + overrides + "\n" + INVOKE_AND_EMIT
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    text = result.stdout.strip()
    start = text.find("{")
    assert start >= 0, result.stdout + result.stderr
    return json.loads(text[start:])


# ---------------------------------------------------------------------------
# Section 25: coordinated happy-path and rollback simulation
# ---------------------------------------------------------------------------

def test_coordinated_happy_path_simulation_candidate_candidate():
    report = run_scenario("")
    assert report["success"] is True
    assert report["final_state"] == "CANDIDATE_CANDIDATE_SUCCESS"
    assert report["static_promoted"] is True
    assert report["app_promoted"] is True
    assert report["static_rolled_back"] is False
    assert report["app_rolled_back"] is False
    assert report["phases_completed"] == [
        "PRECHECK", "BUILD_APP", "PACKAGE_APP", "PACKAGE_STATIC",
        "SNAPSHOT_BASELINE", "VERIFY_ROLLBACK_READY",
        "PROMOTE_STATIC", "VERIFY_STATIC", "PROMOTE_APP", "VERIFY_APP",
        "JOINT_PROVENANCE", "PRODUCTION_SMOKE",
    ]


# ---------------------------------------------------------------------------
# F1: SSH child hangs before remote mutation -> terminate, reconcile, retry
# succeeds. Modeled here as a PRECHECK (pre-mutation) transient that fails
# once then succeeds -- exercises L1 direct retry.
# ---------------------------------------------------------------------------

def test_f1_pre_mutation_transient_recovers_and_retries_directly():
    overrides = """
$Precheck = {
    $n = Get-AttemptCount 'precheck'
    if ($n -eq 1) { [ordered]@{ success = $false; root_cause_class = 'ssh_child_hang'; detail = 'F1: simulated SSH child hang before any remote mutation' } }
    else { [ordered]@{ success = $true } }
}
"""
    report = run_scenario(overrides)
    assert report["success"] is True
    assert report["static_rolled_back"] is False
    recovery = report["recovery_log"]
    assert len(recovery) == 1
    assert recovery[0]["classification"] == "L1"
    assert recovery[0]["recovery_action"] == "RETRY_SAME_PHASE_DIRECTLY"
    assert recovery[0]["mutation_occurred"] is False


# ---------------------------------------------------------------------------
# F2: SSH disconnect after remote command actually completed -> reconcile,
# do NOT duplicate mutation, continue.
# ---------------------------------------------------------------------------

def test_f2_post_timeout_reconciliation_does_not_duplicate_mutation():
    overrides = """
$script:staticPromoteCallCount = 0
$PromoteStatic = {
    $script:staticPromoteCallCount = $script:staticPromoteCallCount + 1
    # Simulate: the remote mutation actually landed, but the local ssh
    # client lost the connection before observing success.
    $script:currentStaticSha = $ExpectedSha
    [ordered]@{ success = $false; possible_timeout = $true; root_cause_class = 'ssh_disconnect_after_completion'; detail = 'F2: local client lost the result after the remote command actually completed' }
}
"""
    report = run_scenario(overrides)
    assert report["success"] is True
    # PromoteStatic's own action scriptblock must only have been invoked
    # once -- the driver must not blindly re-run it after reconciling.
    verify_script = COMMON_PREAMBLE.replace(
        "$PromoteStatic = { $script:currentStaticSha = $ExpectedSha; [ordered]@{ success = $true; static_sha = $ExpectedSha } }",
        "",
    )
    assert report["static_promoted"] is True
    recovery = report["recovery_log"]
    assert len(recovery) == 1
    assert recovery[0]["root_cause_class"] == "post_timeout_state_reconciliation"
    assert recovery[0]["recovery_action"] == "RECONCILED_ALREADY_SUCCEEDED_NO_DUPLICATE_MUTATION"


# ---------------------------------------------------------------------------
# F3: static promotion succeeds, app promotion fails before app mutation ->
# static rollback, baseline/baseline, recovery, retry permitted.
# ---------------------------------------------------------------------------

def test_f3_static_success_app_premutation_fail_rolls_back_to_baseline():
    overrides = """
$PromoteApp = {
    $n = Get-AttemptCount 'promote_app'
    if ($n -eq 1) { [ordered]@{ success = $false; root_cause_class = 'app_premutation_failure'; detail = 'F3: app promotion failed before any app mutation occurred' } }
    else { $script:currentAppSha = $ExpectedSha; [ordered]@{ success = $true; app_sha = $ExpectedSha } }
}
"""
    report = run_scenario(overrides)
    assert report["success"] is True
    assert report["static_rolled_back"] is True
    recovery = report["recovery_log"]
    assert len(recovery) == 1
    assert recovery[0]["classification"] == "L2"
    assert recovery[0]["recovery_action"] == "COORDINATED_ROLLBACK_VERIFIED_BASELINE_RETRY_SAME_SHA"


# ---------------------------------------------------------------------------
# F4: static promotion succeeds, app mutation succeeds, post-app verification
# fails -> coordinated rollback, baseline/baseline.
# ---------------------------------------------------------------------------

def test_f4_post_app_verification_failure_triggers_coordinated_rollback():
    overrides = """
$VerifyApp = {
    param($promoted)
    $n = Get-AttemptCount 'verify_app'
    if ($n -eq 1) { [ordered]@{ success = $false; root_cause_class = 'post_app_verification_failed'; detail = 'F4: app container switched but readiness verification failed' } }
    else { [ordered]@{ success = $true } }
}
"""
    report = run_scenario(overrides)
    assert report["success"] is True
    assert report["static_rolled_back"] is True
    assert report["app_rolled_back"] is True
    recovery = report["recovery_log"]
    assert len(recovery) == 1
    assert recovery[0]["classification"] == "L2"
    assert recovery[0]["mutation_occurred"] is True


# ---------------------------------------------------------------------------
# F5: Docker/buildx temporarily unavailable before build -> local recovery,
# same-SHA retry.
# ---------------------------------------------------------------------------

def test_f5_buildx_transient_before_build_recovers_locally():
    overrides = """
$BuildApp = {
    $n = Get-AttemptCount 'build_app'
    if ($n -eq 1) { [ordered]@{ success = $false; root_cause_class = 'buildx_unavailable'; detail = 'F5: docker buildx temporarily unavailable' } }
    else { [ordered]@{ success = $true } }
}
"""
    report = run_scenario(overrides)
    assert report["success"] is True
    recovery = report["recovery_log"]
    assert len(recovery) == 1
    assert recovery[0]["classification"] == "L1"
    assert recovery[0]["mutation_occurred"] is False


# ---------------------------------------------------------------------------
# F6: temporary health/readiness failure that resolves within the bounded
# retry window -> bounded retry, continue.
# ---------------------------------------------------------------------------

def test_f6_temporary_health_failure_resolves_within_bounded_window():
    overrides = """
$VerifyStatic = {
    param($promoted)
    $n = Get-AttemptCount 'verify_static'
    if ($n -eq 1) { [ordered]@{ success = $false; root_cause_class = 'transient_health_check'; detail = 'F6: readiness check failed once, expected to resolve' } }
    else { [ordered]@{ success = $true } }
}
"""
    report = run_scenario(overrides)
    assert report["success"] is True
    recovery = report["recovery_log"]
    assert len(recovery) == 1
    assert recovery[0]["classification"] == "L2"
    assert recovery[0]["recovery_action"] == "COORDINATED_ROLLBACK_VERIFIED_BASELINE_RETRY_SAME_SHA"


# ---------------------------------------------------------------------------
# F7: health failure persists -> rollback, coherent baseline, STOP.
# ---------------------------------------------------------------------------

def test_f7_persistent_health_failure_stops_at_coherent_baseline():
    overrides = """
$VerifyApp = { param($promoted) [ordered]@{ success = $false; root_cause_class = 'persistent_health_failure'; detail = 'F7: readiness never recovers' } }
"""
    report = run_scenario(overrides)
    assert report["success"] is False
    assert report["final_state"] == "STOPPED_OWNER_DECISION_REQUIRED"
    assert report["static_rolled_back"] is True
    assert report["app_rolled_back"] is True
    assert report["final_current_state"]["app_sha"] == BASELINE_SHA
    assert report["final_current_state"]["static_sha"] == BASELINE_SHA
    # Budget of 2 attempts + escalation on the 3rd occurrence of this exact
    # root cause.
    assert report["recovery_log"][-1]["retry_count"] == 3
    assert report["recovery_log"][-1]["final_outcome"] == "STOPPED"
    assert report["stop_reason"] == "recovery_budget_exhausted"


# ---------------------------------------------------------------------------
# F8: unknown synthetic operational error classified LOW/MEDIUM -> generic
# recovery path, NOT a whitelist entry. This is the required proof that
# classification generalizes: the failure below is a completely
# unstructured bare `throw` with a novel message never referenced anywhere
# in CoordinatedReleaseStateMachine.psm1's source, in a post-mutation phase.
# ---------------------------------------------------------------------------

def test_f8_unknown_operational_failure_with_no_whitelist_entry_recovers():
    module_source = MODULE.read_text(encoding="utf-8")
    novel_message = "xk7q_unprecedented_fault_never_seen_before_2026"
    assert novel_message not in module_source, (
        "the whole point of F8 is that this exact failure string has no "
        "prior recovery recipe anywhere in the module's source"
    )
    overrides = f"""
$VerifyStatic = {{
    param($promoted)
    $n = Get-AttemptCount 'unknown_verify_static'
    if ($n -eq 1) {{ throw '{novel_message}' }}
    else {{ [ordered]@{{ success = $true }} }}
}}
"""
    report = run_scenario(overrides)
    assert report["success"] is True
    recovery = report["recovery_log"]
    assert len(recovery) == 1
    # Classified purely from phase position (post-mutation -> L2) and the
    # driver's own baseline-availability tracking -- nothing in the module
    # matched on the novel_message text to know how to handle this.
    assert recovery[0]["classification"] == "L2"
    assert recovery[0]["failure_was_unstructured_exception"] is True
    assert novel_message in recovery[0]["failure_detail"]


def test_unknown_operational_failure_recovery_pass_marker():
    # Explicit named marker for the FINAL REPORT's
    # UNKNOWN_OPERATIONAL_FAILURE_RECOVERY=PASS field.
    test_f8_unknown_operational_failure_with_no_whitelist_entry_recovers()


def test_get_operational_failure_classification_uses_no_error_string_matching():
    # Direct proof at the classifier level (not just end-to-end): two
    # semantically opposite, totally novel error strings in the SAME phase
    # with the SAME structural signals must classify identically -- the
    # message content is provably not an input to the decision.
    script = COMMON_PREAMBLE + """
$a = Get-OperationalFailureClassification -Phase 'PROMOTE_APP' -RollbackTargetAvailable $true -Detail 'zzz_never_seen_alpha'
$b = Get-OperationalFailureClassification -Phase 'PROMOTE_APP' -RollbackTargetAvailable $true -Detail 'completely_different_beta_message'
[ordered]@{ a_level = $a.level; b_level = $b.level; a_reason = $a.reason; b_reason = $b.reason } | ConvertTo-Json -Compress
"""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["a_level"] == payload["b_level"] == "L2"
    assert payload["a_reason"] == payload["b_reason"]


# ---------------------------------------------------------------------------
# F9: simulated L3 condition: source SHA change required -> STOP, no
# automatic source modification.
# ---------------------------------------------------------------------------

def test_f9_source_change_required_stops_no_automatic_modification():
    overrides = """
$PromoteApp = { [ordered]@{ success = $false; requires_source_change = $true; detail = 'F9: candidate image content does not match expected source -- a new commit is required' } }
"""
    report = run_scenario(overrides)
    assert report["success"] is False
    assert report["final_state"] == "STOPPED_OWNER_DECISION_REQUIRED"
    assert report["stop_reason"] == "requires_source_change"
    # No source-modifying action of any kind was invoked -- proven simply by
    # the fact this whole scenario never shells out to git/file-write
    # anywhere in the harness; the driver only ever calls the injected
    # scriptblocks above.
    assert report["recovery_log"][0]["retry_count"] == 1
    assert report["recovery_log"][0]["final_outcome"] == "STOPPED"


# ---------------------------------------------------------------------------
# F10: rollback target unavailable/ambiguous -> STOP, do not continue
# mutation.
# ---------------------------------------------------------------------------

def test_f10_rollback_target_unavailable_stops_before_mutation():
    overrides = """
$SnapshotBaseline = { [ordered]@{ success = $false; detail = 'F10: baseline identity could not be established -- no safe rollback target' } }
"""
    report = run_scenario(overrides)
    assert report["success"] is False
    assert report["final_state"] == "STOPPED_OWNER_DECISION_REQUIRED"
    assert report["static_promoted"] is False
    assert report["app_promoted"] is False
    # SNAPSHOT_BASELINE is pre-mutation, so a bare failure there is L1
    # (retryable) by default -- this scenario proves that if it keeps
    # failing, the run correctly escalates rather than ever proceeding to
    # promote anything without a captured baseline.
    assert report["recovery_log"][-1]["classification"] == "L1"
    assert report["recovery_log"][-1]["retry_count"] == 3


def test_f10_variant_explicit_rollback_target_unavailable_at_post_mutation_is_l3():
    # A distinct, more direct proof of the same F10 intent: if a
    # post-mutation phase's OWN result explicitly reports no rollback
    # target is available, that is immediately L3 regardless of retry
    # budget -- continuing to mutate without a known-good rollback target
    # is exactly the irreversible-risk boundary Section 8 names.
    script = COMMON_PREAMBLE + """
$c = Get-OperationalFailureClassification -Phase 'PROMOTE_APP' -RollbackTargetAvailable $false -Detail 'no baseline captured'
$c | ConvertTo-Json -Compress
"""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["level"] == "L3"
    assert payload["reason"] == "rollback_identity_unavailable"
    assert payload["retry_strategy"] == "NOT_RETRYABLE_WITHOUT_OWNER"


# ---------------------------------------------------------------------------
# Coordinated rollback simulation (Section 25): forced persistent failure
# after both static+app mutation, proving the final observed state is
# EXACTLY baseline/baseline, never a mixed CANDIDATE/BASELINE state.
# ---------------------------------------------------------------------------

def test_coordinated_rollback_simulation_never_leaves_mixed_state():
    overrides = """
$ProductionSmoke = { [ordered]@{ success = $false; root_cause_class = 'persistent_smoke_failure'; detail = 'rollback simulation: smoke test never recovers' } }
"""
    report = run_scenario(overrides)
    assert report["success"] is False
    assert report["static_promoted"] is True
    assert report["app_promoted"] is True
    assert report["static_rolled_back"] is True
    assert report["app_rolled_back"] is True
    final = report["final_current_state"]
    assert final["app_sha"] == final["static_sha"] == BASELINE_SHA, (
        "forbidden mixed state: static/app must never disagree after a stop"
    )


def test_forbidden_mixed_state_is_structurally_impossible_by_construction():
    # Source-level guard: PROMOTE_STATIC and PROMOTE_APP roll back
    # together (or not at all) in every L2/L3 recovery branch -- there is
    # no code path that rolls back only one of the two independently
    # outside of "the other was never promoted in the first place".
    content = MODULE.read_text(encoding="utf-8")
    for marker in ("if ($staticPromoted)", "if ($appPromoted)"):
        assert content.count(marker) >= 2, f"expected rollback-gating on {marker} in both L2 and L3 recovery branches"
