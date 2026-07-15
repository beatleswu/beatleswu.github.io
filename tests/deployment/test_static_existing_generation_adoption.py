from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEPLOY = (ROOT / "scripts/release/deploy-static-release.ps1").read_text(encoding="utf-8")


def test_existing_generation_is_explicit_and_mutually_exclusive():
    assert "ExistingGenerationPath" in DEPLOY
    assert "Existing-generation adoption is mutually exclusive" in DEPLOY
    assert "Existing-generation adoption requires StaticManifest" in DEPLOY
    assert "Normal static deployment requires StaticManifest, BundlePath, and ArchivePath" in DEPLOY


def test_existing_generation_path_is_fail_closed():
    assert "must be absolute" in DEPLOY
    assert "must be contained under the static releases root" in DEPLOY
    assert "failed directory/symlink/mount safety checks" in DEPLOY
    assert "does not match the governed generation naming contract" in DEPLOY
    assert "cannot be the releases root" in DEPLOY
    assert "contains unsafe path components" in DEPLOY


def test_remote_safety_command_is_constructed_without_local_command_substitution():
    assert "$adoptionCheckCommand = 'test -d '" in DEPLOY
    assert "findmnt -T ' + $quotedExistingGeneration" in DEPLOY
    assert 'Invoke-RemoteText $adoptionCheckCommand' in DEPLOY
    assert '$adoptionCheck = Invoke-RemoteText "p=$(Quote-PosixShellArgument' not in DEPLOY


def test_existing_generation_manifest_path_is_quoted_for_remote_shell():
    assert '$quotedExistingManifest = Quote-PosixShellArgument "$remoteReleaseDir/manifest.json"' in DEPLOY
    assert 'Invoke-RemoteText ("cat " + $quotedExistingManifest)' in DEPLOY
    assert 'Invoke-RemoteText ("sha256sum " + $quotedExistingManifest)' in DEPLOY
    assert 'Quote-PosixShellArgument \\\"$remoteReleaseDir/manifest.json\\\"' not in DEPLOY


def test_static_adoption_emits_phase_history_without_changing_gates():
    assert 'function Write-StaticDeployPhase' in DEPLOY
    assert 'phase_history = @($phaseHistory)' in DEPLOY
    assert "Write-StaticDeployPhase -Phase 'ROLLBACK_BEGIN' -Status 'BEGIN'" in DEPLOY
    assert "Write-StaticDeployPhase -Phase 'ROLLBACK_COMPLETE' -Status 'END'" in DEPLOY
    assert "Assert-OwnerGate -Provided $OwnerGate -Expected 'GO_DEPLOY'" in DEPLOY


def test_observability_logging_is_non_throwing_and_failure_fields_are_structured():
    assert 'catch {' in DEPLOY
    assert 'STATIC_PHASE_WARNING' in DEPLOY
    assert 'accepted = $false' in DEPLOY
    for field in (
        'failure_phase', 'failure_message', 'failure_exit_code',
        'rollback_required', 'rollback_started', 'rollback_finished',
        'rollback_result', 'rollback_failure_phase',
        'rollback_failure_message', 'final_current_generation',
    ):
        assert f'{field} =' in DEPLOY
    assert "$rollbackResult = 'succeeded'" in DEPLOY
    assert "$rollbackResult = 'failed'" in DEPLOY
    assert "$rollbackResult = 'not_required'" in DEPLOY
    assert 'failure_record=$($failureRecord | ConvertTo-Json' in DEPLOY


def test_adoption_preflight_verifies_remote_identity_and_all_governed_files():
    assert "existing generation manifest" in DEPLOY
    assert "Existing generation manifest identity does not match" in DEPLOY
    assert "Existing generation manifest SHA mismatch" in DEPLOY
    assert "existing governed file count" in DEPLOY
    assert "existing generation SHA verification" in DEPLOY
    assert "existing generation residue check" in DEPLOY
    assert "EXISTING GENERATION PRE-ACTIVATION VERIFIED" in DEPLOY


def test_adoption_skips_upload_and_extract_but_reuses_activation_verification():
    assert "if (-not $adoptionMode)" in DEPLOY
    assert "mode = if ($adoptionMode) { 'existing_generation_adoption' }" in DEPLOY
    assert "atomic symlink switch" in DEPLOY
    assert "Invoke-BoundedPublicVerification" in DEPLOY
    assert "automatic rollback succeeded" in DEPLOY
    assert "ARCHIVE UPLOAD COMPLETE" in DEPLOY
    assert "ARCHIVE EXTRACT COMPLETE" in DEPLOY


def test_existing_generation_does_not_weaken_owner_gate_or_normal_overwrite_guard():
    assert "Assert-OwnerGate -Provided $OwnerGate -Expected 'GO_DEPLOY'" in DEPLOY
    assert "refusing to overwrite" in DEPLOY
    assert "ExistingGenerationPath" in DEPLOY
    assert "-OwnerGate 'GO_ROLLBACK'" not in DEPLOY
