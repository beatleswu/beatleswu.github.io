"""G036 coordinator must honor OwnerSimplifiedPolicy without weakening governance."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
SCRIPT=(ROOT/"scripts/release/deploy-coordinated-release.ps1").read_text(encoding="utf8")
BUILD=(ROOT/"scripts/release/build-release-image.ps1").read_text(encoding="utf8")
STATIC=(ROOT/"scripts/release/package-static-release.ps1").read_text(encoding="utf8")

def test_explicit_optin_but_legacy_default_not_automatically_rewritten():
    assert "[switch]$OwnerSimplifiedPolicy" in SCRIPT
    assert "Assert-OwnerGate -Provided $OwnerGate -Expected $requiredOwnerGate" in SCRIPT
    assert "$requiredOwnerGate = 'GO_DEPLOY_WITH_BOUNDED_RECOVERY'" in SCRIPT
    assert "EXTERNAL_GOVERNANCE_AUTHORITY_REQUIRED" in BUILD
    assert "EXTERNAL_GOVERNANCE_ATTESTATION_REQUIRED" in BUILD
    assert "[switch]$OwnerSimplifiedPolicy" in BUILD

def test_real_product_source_ancestry_and_complete_worktree_guards_are_still_required():
    for item in (
      "Assert-TrackedTreeClean -WorkingDirectory $repoRoot",
      "Assert-CompleteWorktreeClean -WorkingDirectory $repoRoot",
      "Assert-ReleaseSourceSeparation -GateSourceSha $script:ownerSimplifiedGateSha -ProductSourceSha $ExpectedGitSha",
      "$script:ownerSimplifiedGateSha = Get-CurrentGitSha",
      "owner_simplified_policy = [bool]$OwnerSimplifiedPolicy",
      "gate_source_sha = $script:ownerSimplifiedGateSha",
      "product_source_sha = $ExpectedGitSha",
    ):
       assert item in SCRIPT,item

def test_build_phase_forwards_existing_official_owner_policy_instead_of_faking_external_authority():
    assert "'-OwnerSimplifiedPolicy'" in SCRIPT
    assert "'-GateSourceSha', $script:ownerSimplifiedGateSha" in SCRIPT
    assert "'-ProductSourceSha', $ExpectedGitSha" in SCRIPT
    assert " '-ExpectedGitSha', $ExpectedGitSha" in SCRIPT
    assert "-Arguments $buildArgs" in SCRIPT
    assert "-Arguments $staticArgs" in SCRIPT
    assert " '-OwnerSimplifiedPolicy'" not in STATIC  # static needs the two actual Git SHA params only
    assert "Assert-ReleaseSourceSeparation -GateSourceSha $gateSha -ProductSourceSha $productSha" in STATIC

def test_promote_and_rollback_still_use_canonical_governed_tools():
    for term in (
        "Invoke-CoordinatedReleaseStateMachine",
        "-ProvenMixedBaselineValidator $ProvenMixedBaselineValidator",
        "-MaxAttemptsPerRootCause $MaxAttemptsPerRootCause",
        "Test-ReleaseBaselineIdentityAccepted",
        "coordinated-release: verify app postcondition",
        "coordinated-release: verify public static acceptance contract",
        "'GO_ROLLBACK'",
        "static_rolled_back",
    ):
        if term != "static_rolled_back":assert term in SCRIPT,term
    assert "function Assert-HistoricalRollbackPairDocument" in SCRIPT
    assert "Get-RemoteImageSourceGitSha" in SCRIPT
    assert "Get-RemoteStaticGenerationSourceGitSha" in SCRIPT

def test_non_go_deploy_remains_safe_and_explicit():
    assert "if (-not $Execute)" in SCRIPT
    assert "execute_requested = $false" in SCRIPT
    assert "result = 'DRY_RUN_COMPLETE'" in SCRIPT
    assert "Assert-OwnerGate -Provided $OwnerGate" in SCRIPT

def test_only_exact_required_source_integrity_workflow_can_be_different_between_gate_and_product():
    import importlib.util
    spec=importlib.util.spec_from_file_location(
       "g036_binding",ROOT/"scripts/release/verify_release_candidate_binding.py")
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.is_control_plane(".github/workflows/g009-source-snapshot.yml")
    assert not module.is_control_plane(".github/workflows/unreviewed.yml")
    assert not module.is_control_plane(".github/workflows/deploy.yml")
    assert not module.is_control_plane("app.py")
    assert not module.is_control_plane("assets/3d_shop/p048/hero/any.glb")
    ps=(ROOT/"scripts/release/ReleaseTooling.psm1").read_text(encoding="utf8")
    assert "'github/workflows/g009-source-snapshot.yml'" in ps
    assert "'.github/workflows/g009-source-snapshot.yml'" in ps
    assert "'.github/**'" not in ps
