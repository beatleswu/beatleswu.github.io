Set-StrictMode -Version Latest

function Invoke-ShadowKillSwitchDrillStateMachine {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][scriptblock]$GetState,
        [Parameter(Mandatory = $true)][scriptblock]$Disable,
        [Parameter(Mandatory = $true)][scriptblock]$VerifyDisabled,
        [Parameter(Mandatory = $true)][scriptblock]$VerifyInfrastructure,
        [Parameter(Mandatory = $true)][scriptblock]$VerifyLegacyCanary,
        [Parameter(Mandatory = $true)][scriptblock]$VerifyWriteStop,
        [Parameter(Mandatory = $true)][scriptblock]$VerifyDashboard,
        [Parameter(Mandatory = $true)][scriptblock]$Restore,
        [Parameter(Mandatory = $true)][scriptblock]$VerifyResumed
    )

    $report = [ordered]@{
        operation = 'shadow_kill_switch_drill'
        success = $false
        initial_state_captured = $false
        initial_intended_enabled = $null
        initial_effective_state = $null
        initial_backup_identity = $null
        disable_verified = $false
        legacy_infrastructure_healthy = $false
        legacy_judging_baseline_ok = $false
        legacy_judging_disabled_ok = $false
        legacy_judging_restored_ok = $false
        legacy_canary_name = $null
        legacy_expected_result = $null
        legacy_actual_result = $null
        legacy_baseline_actual_result = $null
        legacy_disabled_actual_result = $null
        legacy_restored_actual_result = $null
        write_stop_verified = $false
        dashboard_readable = $false
        restoration_attempted = $false
        restoration_succeeded = $false
        outer_restoration_attempted = $false
        setter_internal_recovery_attempted = $false
        setter_internal_recovery_succeeded = $false
        failed_generation_evidence = $null
        evidence_capture_status = $null
        restoration_backup_identity = $null
        resume_verified = $null
        final_effective_state = $null
        final_matches_initial = $false
        failure_stage = $null
        partial_state = $true
    }

    $initial = $null
    $disableResult = $null
    $mutationMayHaveStarted = $false
    $stage = 'initial_state'

    function Assert-LegacyCanaryResult {
        param($CanaryResult, [string]$Checkpoint)
        if (-not $CanaryResult) {
            throw 'Legacy judging canary returned no result.'
        }
        if ((-not [string]::IsNullOrWhiteSpace($report.legacy_canary_name) -and
             $report.legacy_canary_name -ne [string]$CanaryResult.name) -or
            (-not [string]::IsNullOrWhiteSpace($report.legacy_expected_result) -and
             $report.legacy_expected_result -ne [string]$CanaryResult.expected_result)) {
            throw 'Legacy judging canary contract changed between checkpoints.'
        }
        $report.legacy_canary_name = [string]$CanaryResult.name
        $report.legacy_expected_result = [string]$CanaryResult.expected_result
        $report.legacy_actual_result = [string]$CanaryResult.actual_result
        $report["legacy_${Checkpoint}_actual_result"] = [string]$CanaryResult.actual_result
        if ([string]::IsNullOrWhiteSpace($report.legacy_canary_name) -or
            [string]::IsNullOrWhiteSpace($report.legacy_expected_result) -or
            [string]::IsNullOrWhiteSpace($report.legacy_actual_result) -or
            $CanaryResult.ok -ne $true -or
            $report.legacy_actual_result -ne $report.legacy_expected_result) {
            throw 'Legacy judging canary failed closed.'
        }
    }

    try {
        $initial = & $GetState
        if (-not $initial -or -not $initial.effective -or $null -eq $initial.effective.enabled) {
            throw 'Initial Shadow effective state is missing.'
        }
        if ([string]$initial.effective.state -notin @('enabled','disabled','unset_default_disabled')) {
            throw 'Initial Shadow effective state is not drill-safe.'
        }
        $report.initial_state_captured = $true
        $report.initial_intended_enabled = [bool]$initial.effective.enabled
        $report.initial_effective_state = [string]$initial.effective.state

        $stage = 'legacy_baseline'
        Assert-LegacyCanaryResult (& $VerifyLegacyCanary 'baseline') 'baseline'
        $report.legacy_judging_baseline_ok = $true

        $stage = 'disable'
        $mutationMayHaveStarted = $true
        $disableResult = & $Disable
        if (-not $disableResult -or
            -not $disableResult.backup -or
            [string]::IsNullOrWhiteSpace([string]$disableResult.backup.id)) {
            throw 'Disable did not report the governed initial backup identity.'
        }
        $report.initial_backup_identity = [string]$disableResult.backup.id
        $report.setter_internal_recovery_attempted = ($null -ne $disableResult.PSObject.Properties['internal_recovery_attempted'] -and $disableResult.internal_recovery_attempted -eq $true)
        $report.setter_internal_recovery_succeeded = ($null -ne $disableResult.PSObject.Properties['internal_recovery_succeeded'] -and $disableResult.internal_recovery_succeeded -eq $true)
        if ($null -ne $disableResult.PSObject.Properties['failed_generation_evidence']) {
            $report.failed_generation_evidence = $disableResult.failed_generation_evidence
            $report.evidence_capture_status = [string]$disableResult.failed_generation_evidence.status
        }
        if ($report.setter_internal_recovery_succeeded) {
            $mutationMayHaveStarted = $false
            if (-not $disableResult.effective -or [bool]$disableResult.effective.enabled -ne [bool]$report.initial_intended_enabled) {
                throw 'Setter internal recovery did not restore the initial effective state.'
            }
            throw 'Disable verification failed after setter internal recovery; initial state restored.'
        }

        $stage = 'disable_verification'
        & $VerifyDisabled $disableResult
        $report.disable_verified = $true

        $stage = 'legacy_infrastructure'
        & $VerifyInfrastructure $disableResult
        $report.legacy_infrastructure_healthy = $true

        $stage = 'legacy_disabled'
        Assert-LegacyCanaryResult (& $VerifyLegacyCanary 'disabled') 'disabled'
        $report.legacy_judging_disabled_ok = $true

        $stage = 'write_stop'
        & $VerifyWriteStop
        $report.write_stop_verified = $true

        $stage = 'dashboard'
        & $VerifyDashboard
        $report.dashboard_readable = $true
    }
    catch {
        $report.failure_stage = $stage
    }
    finally {
        if ($mutationMayHaveStarted -and $report.initial_state_captured) {
            $report.restoration_attempted = $true
            $report.outer_restoration_attempted = $true
            $restoreCompleted = $false
            try {
                $restoreResult = & $Restore $disableResult $initial
                if (-not $restoreResult) {
                    throw 'Restore did not report a result.'
                }
                if (-not $restoreResult -or
                    [string]::IsNullOrWhiteSpace([string]$restoreResult.rollback_backup_id)) {
                    throw 'Restore did not report its governed reverse-backup identity.'
                }
                $report.restoration_backup_identity = [string]$restoreResult.rollback_backup_id
                $restoreCompleted = $true
            }
            catch {
                if (-not $report.failure_stage) {
                    $report.failure_stage = 'restoration'
                }
            }

            try {
                $final = & $GetState
                if (-not $final -or -not $final.effective -or $null -eq $final.effective.enabled) {
                    throw 'Final Shadow effective state is missing.'
                }
                $report.final_effective_state = [string]$final.effective.state
                $report.final_matches_initial = (
                    ([bool]$final.effective.enabled -eq [bool]$report.initial_intended_enabled) -and
                    ([string]$final.effective.state -eq [string]$report.initial_effective_state)
                )
                if (-not $report.final_matches_initial) {
                    if (-not $report.failure_stage) {
                        $report.failure_stage = 'final_state_mismatch'
                    }
                    throw 'Final Shadow state differs from the initial intended state.'
                }
                $report.restoration_succeeded = [bool]$restoreCompleted
            }
            catch {
                if (-not $report.failure_stage) {
                    $report.failure_stage = 'restoration'
                }
                $report.restoration_succeeded = $false
            }

            if ($report.final_matches_initial -and $restoreCompleted) {
                try {
                    $stage = 'legacy_restored'
                    Assert-LegacyCanaryResult (& $VerifyLegacyCanary 'restored') 'restored'
                    $report.legacy_judging_restored_ok = $true
                }
                catch {
                    if (-not $report.failure_stage) {
                        $report.failure_stage = $stage
                    }
                }

                if ($report.initial_intended_enabled) {
                    try {
                        $stage = 'event_resumption'
                        & $VerifyResumed
                        $report.resume_verified = $true
                    }
                    catch {
                        if (-not $report.failure_stage) {
                            $report.failure_stage = $stage
                        }
                        $report.resume_verified = $false
                    }
                }
                else {
                    $report.resume_verified = $null
                }
            }
        }
        elseif ($report.initial_state_captured) {
            try {
                $final = & $GetState
                $report.final_effective_state = [string]$final.effective.state
                $report.final_matches_initial = (
                    ([bool]$final.effective.enabled -eq [bool]$report.initial_intended_enabled) -and
                    ([string]$final.effective.state -eq [string]$report.initial_effective_state)
                )
            }
            catch {
                $report.final_matches_initial = $false
            }
        }
    }

    $checksPassed = (
        $report.initial_state_captured -and
        $report.legacy_judging_baseline_ok -and
        $report.disable_verified -and
        $report.legacy_infrastructure_healthy -and
        $report.legacy_judging_disabled_ok -and
        $report.write_stop_verified -and
        $report.dashboard_readable -and
        $report.restoration_succeeded -and
        $report.final_matches_initial -and
        $report.legacy_judging_restored_ok -and
        ((-not $report.initial_intended_enabled) -or ($report.resume_verified -eq $true))
    )
    $report.success = [bool]$checksPassed
    $report.partial_state = -not $report.success
    if ($report.success) {
        $report.failure_stage = $null
    }
    return [pscustomobject]$report
}

Export-ModuleMember -Function 'Invoke-ShadowKillSwitchDrillStateMachine'
