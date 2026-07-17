Set-StrictMode -Version Latest

function Invoke-ShadowKillSwitchDrillStateMachine {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][scriptblock]$GetState,
        [Parameter(Mandatory = $true)][scriptblock]$Disable,
        [Parameter(Mandatory = $true)][scriptblock]$VerifyDisabled,
        [Parameter(Mandatory = $true)][scriptblock]$VerifyLegacy,
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
        legacy_routes_healthy = $false
        write_stop_verified = $false
        dashboard_readable = $false
        restoration_attempted = $false
        restoration_succeeded = $false
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

        $stage = 'disable'
        $mutationMayHaveStarted = $true
        $disableResult = & $Disable
        if (-not $disableResult -or [string]::IsNullOrWhiteSpace([string]$disableResult.backup_id)) {
            throw 'Disable did not report the governed initial backup identity.'
        }
        $report.initial_backup_identity = [string]$disableResult.backup_id

        $stage = 'disable_verification'
        & $VerifyDisabled $disableResult
        $report.disable_verified = $true

        $stage = 'legacy_health'
        & $VerifyLegacy $disableResult
        $report.legacy_routes_healthy = $true

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
            try {
                $restoreResult = & $Restore $disableResult $initial
                if (-not $restoreResult) {
                    throw 'Restore did not report a result.'
                }
                if (-not [string]::IsNullOrWhiteSpace([string]$restoreResult.rollback_backup_id)) {
                    $report.restoration_backup_identity = [string]$restoreResult.rollback_backup_id
                }
                elseif ($disableResult -and -not [string]::IsNullOrWhiteSpace([string]$disableResult.backup_id)) {
                    throw 'Restore did not report its governed reverse-backup identity.'
                }
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
                    throw 'Final Shadow state differs from the initial intended state.'
                }
                if ($report.initial_intended_enabled) {
                    & $VerifyResumed
                    $report.resume_verified = $true
                }
                else {
                    $report.resume_verified = $null
                }
                $report.restoration_succeeded = $true
            }
            catch {
                if (-not $report.failure_stage) {
                    $report.failure_stage = 'restoration'
                }
                $report.restoration_succeeded = $false
            }
        }
    }

    $checksPassed = (
        $report.initial_state_captured -and
        $report.disable_verified -and
        $report.legacy_routes_healthy -and
        $report.write_stop_verified -and
        $report.dashboard_readable -and
        $report.restoration_succeeded -and
        $report.final_matches_initial -and
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
