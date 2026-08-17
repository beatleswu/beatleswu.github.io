Set-StrictMode -Version Latest

<#
Deployment Workflow V3: bounded operational recovery for the coordinated
static+app release transaction.

Design summary (see docs/deployment/deployment_workflow_v3_operator_contract.md
for the full operator-facing contract):

  - Phases run in the fixed order PRECHECK -> BUILD_APP -> PACKAGE_APP ->
    PACKAGE_STATIC -> SNAPSHOT_BASELINE -> VERIFY_ROLLBACK_READY ->
    PROMOTE_STATIC -> VERIFY_STATIC -> PROMOTE_APP -> VERIFY_APP ->
    JOINT_PROVENANCE -> PRODUCTION_SMOKE -> SUCCESS. Every phase is an
    injected scriptblock so this module never itself calls ssh/docker/git --
    it only sequences and recovers around whatever the caller wires up (the
    real release scripts in production; fakes in tests).

  - Classification (Get-OperationalFailureClassification) is structural,
    not name/message-based: which PHASE failed determines whether
    Production mutation was even possible (PRECHECK..VERIFY_ROLLBACK_READY
    are read-only/local by construction; nothing there can have touched
    Production, known failure or not), and three explicit boundary flags a
    phase result may set (RequiresSourceChange, RequiresGateBypass, an
    unavailable rollback target) force L3 regardless of phase. Everything
    else post-mutation defaults to L2. This is what lets a completely novel
    failure -- one this module has never seen and has no name for -- still
    be classified correctly: nothing here matches on error identity.

  - Bounded retry: MAX_AUTOMATIC_RECOVERY_ATTEMPTS_PER_ROOT_CAUSE = 2,
    tracked per (phase, root_cause_class) key so an unrelated LOW/MEDIUM
    failure in a different phase (or a differently-classified failure in
    the same phase) gets its own independent budget rather than sharing one
    global counter.

  - static_sha == app_sha is enforced, not merely documented: JOINT_PROVENANCE
    independently re-reads current state via -GetCurrentState and fails
    (forcing rollback) if the two identities, or either against
    -ExpectedGitSha, disagree.
#>

$PRE_MUTATION_PHASES = @(
    'PRECHECK', 'BUILD_APP', 'PACKAGE_APP', 'PACKAGE_STATIC',
    'SNAPSHOT_BASELINE', 'VERIFY_ROLLBACK_READY'
)
$POST_MUTATION_PHASES = @(
    'PROMOTE_STATIC', 'VERIFY_STATIC', 'PROMOTE_APP', 'VERIFY_APP',
    'JOINT_PROVENANCE', 'PRODUCTION_SMOKE'
)
$ALL_PHASES = @($PRE_MUTATION_PHASES) + @($POST_MUTATION_PHASES)
$MAX_AUTOMATIC_RECOVERY_ATTEMPTS_PER_ROOT_CAUSE = 2

function Get-OperationalFailureClassification {
    <#
    .SYNOPSIS
    Classifies an operational failure as L1, L2, or L3. See module header.
    #>
    param(
        [Parameter(Mandatory = $true)][ValidateSet(
            'PRECHECK', 'BUILD_APP', 'PACKAGE_APP', 'PACKAGE_STATIC',
            'SNAPSHOT_BASELINE', 'VERIFY_ROLLBACK_READY',
            'PROMOTE_STATIC', 'VERIFY_STATIC', 'PROMOTE_APP', 'VERIFY_APP',
            'JOINT_PROVENANCE', 'PRODUCTION_SMOKE'
        )][string]$Phase,
        [bool]$RequiresSourceChange = $false,
        [bool]$RequiresGateBypass = $false,
        [bool]$RollbackTargetAvailable = $true,
        [string]$Detail = ''
    )
    if ($RequiresSourceChange) {
        return [ordered]@{
            level = 'L3'; reason = 'requires_source_change'
            retry_strategy = 'NOT_RETRYABLE_WITHOUT_OWNER'; detail = $Detail
        }
    }
    if ($RequiresGateBypass) {
        return [ordered]@{
            level = 'L3'; reason = 'requires_gate_bypass'
            retry_strategy = 'NOT_RETRYABLE_WITHOUT_OWNER'; detail = $Detail
        }
    }
    $isPostMutation = $Phase -in $POST_MUTATION_PHASES
    if ($isPostMutation -and -not $RollbackTargetAvailable) {
        return [ordered]@{
            level = 'L3'; reason = 'rollback_identity_unavailable'
            retry_strategy = 'NOT_RETRYABLE_WITHOUT_OWNER'; detail = $Detail
        }
    }
    if ($isPostMutation) {
        return [ordered]@{
            level = 'L2'; reason = 'post_mutation_operational_failure'
            retry_strategy = 'REQUIRES_ROLLBACK_BEFORE_RETRY'; detail = $Detail
        }
    }
    return [ordered]@{
        level = 'L1'; reason = 'pre_mutation_operational_failure'
        retry_strategy = 'SAFE_TO_RETRY_DIRECTLY'; detail = $Detail
    }
}

function New-RecoveryBudgetTracker {
    return @{}
}

function Update-RecoveryBudget {
    <#
    .SYNOPSIS
    Bounded per-root-cause retry accounting. Returns allowed=$false once a
    given (phase, root cause) pair has already been attempted MaxAttempts
    times, regardless of how many OTHER distinct root causes have also
    entered recovery in this same run.
    #>
    param(
        [Parameter(Mandatory = $true)][hashtable]$Tracker,
        [Parameter(Mandatory = $true)][string]$RootCauseKey,
        [int]$MaxAttempts = $MAX_AUTOMATIC_RECOVERY_ATTEMPTS_PER_ROOT_CAUSE
    )
    if (-not $Tracker.ContainsKey($RootCauseKey)) {
        $Tracker[$RootCauseKey] = 0
    }
    $Tracker[$RootCauseKey] = $Tracker[$RootCauseKey] + 1
    $attemptNumber = $Tracker[$RootCauseKey]
    return [ordered]@{
        root_cause_key = $RootCauseKey
        attempt_number = $attemptNumber
        max_attempts = $MaxAttempts
        allowed = ($attemptNumber -le $MaxAttempts)
    }
}

function New-RootCauseKey {
    param([Parameter(Mandatory = $true)][string]$Phase, [string]$RootCauseClass = '')
    $normalizedClass = if ([string]::IsNullOrWhiteSpace($RootCauseClass)) { 'default' } else { $RootCauseClass }
    return "${Phase}::${normalizedClass}"
}

function Get-PhaseResultProperty {
    <#
    .SYNOPSIS
    Reads a named field from a phase result that may be either a Hashtable/
    OrderedDictionary (the natural, idiomatic `[ordered]@{ ... }` PowerShell
    return shape used throughout this module and its tests) or a real
    PSCustomObject.
    .DESCRIPTION
    These two shapes are NOT interchangeable via `.PSObject.Properties[...]`:
    a Hashtable/OrderedDictionary's own dictionary keys are not exposed as
    PSObject properties at all (PSObject.Properties on a Hashtable reflects
    the .NET Hashtable TYPE's real members -- Keys, Values, Count, Item --
    not its dynamic key/value entries), even though direct dot-access
    (`$dict.SomeKey`) works via PowerShell's separate member-adaptation for
    dictionaries. A `.PSObject.Properties['x']`-gated check therefore always
    silently misses every key on an `[ordered]@{}` result -- confirmed live:
    it caused requires_source_change/possible_timeout/detail to be silently
    dropped for every phase result built the natural way in this module's
    own tests, misclassifying an explicit L3 boundary signal as ordinary L2.
    #>
    param($Object, [Parameter(Mandatory = $true)][string]$Name, $Default)
    if ($null -eq $Object) { return $Default }
    if ($Object -is [System.Collections.IDictionary]) {
        if ($Object.Contains($Name)) { return $Object[$Name] }
        return $Default
    }
    $prop = $Object.PSObject.Properties[$Name]
    if ($null -ne $prop) { return $prop.Value }
    return $Default
}

function Invoke-ReleasePhase {
    <#
    .SYNOPSIS
    Invokes one phase scriptblock, normalizing both a returned result AND a
    bare thrown exception (the "truly unknown failure, zero structured
    context" case Section 21 requires this module to still recover from)
    into the same PhaseResult shape.
    #>
    param(
        [Parameter(Mandatory = $true)][scriptblock]$Action,
        [object[]]$ActionArgs = @()
    )
    try {
        $raw = & $Action @ActionArgs
        if ($null -eq $raw) {
            throw 'Phase action returned no result.'
        }
        $success = [bool](Get-PhaseResultProperty -Object $raw -Name 'success' -Default $false)
        return [ordered]@{
            success = $success
            requires_source_change = [bool](Get-PhaseResultProperty -Object $raw -Name 'requires_source_change' -Default $false)
            requires_gate_bypass = [bool](Get-PhaseResultProperty -Object $raw -Name 'requires_gate_bypass' -Default $false)
            possible_timeout = [bool](Get-PhaseResultProperty -Object $raw -Name 'possible_timeout' -Default $false)
            root_cause_class = [string](Get-PhaseResultProperty -Object $raw -Name 'root_cause_class' -Default '')
            detail = [string](Get-PhaseResultProperty -Object $raw -Name 'detail' -Default '')
            data = $raw
            threw = $false
        }
    }
    catch {
        # A bare, unstructured exception -- exactly the "unknown operational
        # failure with no prior recovery recipe" case. Every boundary flag
        # defaults to "not a boundary" here deliberately: an operation that
        # cannot even report structured context about itself is NOT thereby
        # assumed to require Owner escalation -- phase-based classification
        # (see Get-OperationalFailureClassification) still applies safely.
        return [ordered]@{
            success = $false
            requires_source_change = $false
            requires_gate_bypass = $false
            possible_timeout = $false
            root_cause_class = ''
            detail = [string]$_.Exception.Message
            data = $null
            threw = $true
        }
    }
}

function Invoke-CoordinatedReleaseStateMachine {
    <#
    .SYNOPSIS
    Runs the coordinated static+app release transaction with bounded
    operational recovery. Never mutates anything itself -- every phase is
    an injected scriptblock; this function only sequences, classifies
    failures, and recovers around them.
    .DESCRIPTION
    Each phase scriptblock returns an object with at least a boolean
    `success` property (and, on failure, optionally `requires_source_change`,
    `requires_gate_bypass`, `possible_timeout`, `root_cause_class`, `detail`)
    -- or may simply throw, which this driver treats identically to a
    structured `success=$false` result with every optional flag defaulted
    to "not a boundary" (see Invoke-ReleasePhase).

    -GetCurrentState is called with no arguments like every other phase
    scriptblock, so it too must return an object with `success` plus (when
    successful) `app_sha` and `static_sha` properties reflecting current,
    actually observed identity (not merely what a prior phase intended to
    promote) -- `success=$false` here means Production's current state
    could not be independently established at all, which is exactly the
    named L3 boundary condition from this workflow's own contract, not an
    ordinary operational failure. It is used for: independent
    JOINT_PROVENANCE verification, and to confirm a rollback actually
    restored the captured baseline before this state machine permits a
    same-SHA retry.

    -RollbackStatic / -RollbackApp are only invoked during L2 recovery, and
    only for whichever of static/app was actually promoted before the
    triggering failure (never both unconditionally) -- receiving the
    baseline snapshot object captured by -SnapshotBaseline as their single
    argument.
    #>
    param(
        [Parameter(Mandatory = $true)][string]$ExpectedGitSha,
        [Parameter(Mandatory = $true)][scriptblock]$GetCurrentState,
        [Parameter(Mandatory = $true)][scriptblock]$Precheck,
        [Parameter(Mandatory = $true)][scriptblock]$BuildApp,
        [Parameter(Mandatory = $true)][scriptblock]$PackageApp,
        [Parameter(Mandatory = $true)][scriptblock]$PackageStatic,
        [Parameter(Mandatory = $true)][scriptblock]$SnapshotBaseline,
        [Parameter(Mandatory = $true)][scriptblock]$VerifyRollbackReady,
        [Parameter(Mandatory = $true)][scriptblock]$PromoteStatic,
        [Parameter(Mandatory = $true)][scriptblock]$VerifyStatic,
        [Parameter(Mandatory = $true)][scriptblock]$PromoteApp,
        [Parameter(Mandatory = $true)][scriptblock]$VerifyApp,
        [Parameter(Mandatory = $true)][scriptblock]$ProductionSmoke,
        [Parameter(Mandatory = $true)][scriptblock]$RollbackStatic,
        [Parameter(Mandatory = $true)][scriptblock]$RollbackApp,
        [int]$MaxAttemptsPerRootCause = $MAX_AUTOMATIC_RECOVERY_ATTEMPTS_PER_ROOT_CAUSE
    )

    $report = [ordered]@{
        operation = 'coordinated_release'
        expected_git_sha = $ExpectedGitSha
        success = $false
        final_state = 'UNKNOWN'
        phases_completed = @()
        recovery_log = @()
        baseline = $null
        static_promoted = $false
        app_promoted = $false
        static_rolled_back = $false
        app_rolled_back = $false
        final_current_state = $null
        stop_reason = $null
        stop_phase = $null
    }

    $budget = New-RecoveryBudgetTracker
    $baseline = $null
    $baselineCaptured = $false
    $staticPromoted = $false
    $appPromoted = $false
    $lastPromoteStaticResult = $null
    $lastPromoteAppResult = $null

    $phaseIndex = 0
    $recoveryId = 0

    while ($phaseIndex -lt $ALL_PHASES.Count) {
        $phase = $ALL_PHASES[$phaseIndex]

        $result = switch ($phase) {
            'PRECHECK' { Invoke-ReleasePhase -Action $Precheck }
            'BUILD_APP' { Invoke-ReleasePhase -Action $BuildApp }
            'PACKAGE_APP' { Invoke-ReleasePhase -Action $PackageApp }
            'PACKAGE_STATIC' { Invoke-ReleasePhase -Action $PackageStatic }
            'SNAPSHOT_BASELINE' { Invoke-ReleasePhase -Action $SnapshotBaseline }
            'VERIFY_ROLLBACK_READY' { Invoke-ReleasePhase -Action $VerifyRollbackReady -ActionArgs @($baseline) }
            'PROMOTE_STATIC' { Invoke-ReleasePhase -Action $PromoteStatic }
            'VERIFY_STATIC' { Invoke-ReleasePhase -Action $VerifyStatic -ActionArgs @($lastPromoteStaticResult) }
            'PROMOTE_APP' { Invoke-ReleasePhase -Action $PromoteApp }
            'VERIFY_APP' { Invoke-ReleasePhase -Action $VerifyApp -ActionArgs @($lastPromoteAppResult) }
            'JOINT_PROVENANCE' {
                $stateResult = Invoke-ReleasePhase -Action $GetCurrentState
                if (-not $stateResult.success) {
                    $stateResult
                }
                else {
                    $state = $stateResult.data
                    $coherent = (
                        [string]$state.app_sha -eq $ExpectedGitSha -and
                        [string]$state.static_sha -eq $ExpectedGitSha -and
                        [string]$state.app_sha -eq [string]$state.static_sha
                    )
                    if ($coherent) {
                        [ordered]@{ success = $true; requires_source_change = $false; requires_gate_bypass = $false; possible_timeout = $false; root_cause_class = ''; detail = ''; data = $state; threw = $false }
                    }
                    else {
                        [ordered]@{ success = $false; requires_source_change = $false; requires_gate_bypass = $false; possible_timeout = $false; root_cause_class = 'joint_provenance_incoherent'; detail = "app_sha=$($state.app_sha) static_sha=$($state.static_sha) expected=$ExpectedGitSha"; data = $state; threw = $false }
                    }
                }
            }
            'PRODUCTION_SMOKE' { Invoke-ReleasePhase -Action $ProductionSmoke }
        }

        if ($result.success) {
            $report.phases_completed += $phase
            switch ($phase) {
                'SNAPSHOT_BASELINE' { $baseline = $result.data; $baselineCaptured = $true; $report.baseline = $baseline }
                'PROMOTE_STATIC' { $staticPromoted = $true; $lastPromoteStaticResult = $result.data; $report.static_promoted = $true }
                'PROMOTE_APP' { $appPromoted = $true; $lastPromoteAppResult = $result.data; $report.app_promoted = $true }
            }
            $phaseIndex = $phaseIndex + 1
            continue
        }

        # --- Failure: possible-timeout state reconciliation first (Section
        # 13/14) -- never blindly re-run a possibly-non-idempotent mutation
        # without first checking whether it already actually landed.
        if ($result.possible_timeout -and $phase -in @('PROMOTE_STATIC', 'PROMOTE_APP')) {
            $reconcile = Invoke-ReleasePhase -Action $GetCurrentState
            if ($reconcile.success) {
                $state = $reconcile.data
                $alreadyLanded = if ($phase -eq 'PROMOTE_STATIC') { [string]$state.static_sha -eq $ExpectedGitSha } else { [string]$state.app_sha -eq $ExpectedGitSha }
                if ($alreadyLanded) {
                    $report.recovery_log += [ordered]@{
                        recovery_id = ($recoveryId++)
                        root_cause_class = 'post_timeout_state_reconciliation'
                        failure_phase = $phase
                        mutation_occurred = $true
                        pre_recovery_state = $state
                        recovery_action = 'RECONCILED_ALREADY_SUCCEEDED_NO_DUPLICATE_MUTATION'
                        post_recovery_state = $state
                        retry_count = 0
                        retry_allowed = $true
                        final_outcome = 'ADVANCED_WITHOUT_RETRY'
                    }
                    $report.phases_completed += $phase
                    if ($phase -eq 'PROMOTE_STATIC') { $staticPromoted = $true; $report.static_promoted = $true }
                    if ($phase -eq 'PROMOTE_APP') { $appPromoted = $true; $report.app_promoted = $true }
                    $phaseIndex = $phaseIndex + 1
                    continue
                }
            }
        }

        $classification = Get-OperationalFailureClassification -Phase $phase `
            -RequiresSourceChange $result.requires_source_change `
            -RequiresGateBypass $result.requires_gate_bypass `
            -RollbackTargetAvailable $baselineCaptured `
            -Detail $result.detail

        $rootCauseKey = New-RootCauseKey -Phase $phase -RootCauseClass $result.root_cause_class
        $budgetResult = Update-RecoveryBudget -Tracker $budget -RootCauseKey $rootCauseKey -MaxAttempts $MaxAttemptsPerRootCause

        $recoveryEntry = [ordered]@{
            recovery_id = ($recoveryId++)
            root_cause_class = $rootCauseKey
            classification = $classification.level
            classification_reason = $classification.reason
            failure_phase = $phase
            mutation_occurred = ($phase -in $POST_MUTATION_PHASES)
            failure_detail = $result.detail
            failure_was_unstructured_exception = $result.threw
            retry_count = $budgetResult.attempt_number
            retry_allowed = $budgetResult.allowed
            recovery_action = $null
            post_recovery_state = $null
            final_outcome = $null
        }

        if (($classification.level -eq 'L3') -or (-not $budgetResult.allowed)) {
            $stopReason = if ($classification.level -eq 'L3') { $classification.reason } else { 'recovery_budget_exhausted' }
            $recoveryEntry.recovery_action = 'RESTORE_BASELINE_IF_POSSIBLE_THEN_STOP'
            if ($baselineCaptured -and ($staticPromoted -or $appPromoted)) {
                if ($staticPromoted) {
                    $rb = Invoke-ReleasePhase -Action $RollbackStatic -ActionArgs @($baseline)
                    $report.static_rolled_back = [bool]$rb.success
                }
                if ($appPromoted) {
                    $rb = Invoke-ReleasePhase -Action $RollbackApp -ActionArgs @($baseline)
                    $report.app_rolled_back = [bool]$rb.success
                }
                $finalState = Invoke-ReleasePhase -Action $GetCurrentState
                $recoveryEntry.post_recovery_state = $finalState.data
                $report.final_current_state = $finalState.data
            }
            $recoveryEntry.final_outcome = 'STOPPED'
            $report.recovery_log += $recoveryEntry
            $report.stop_reason = $stopReason
            $report.stop_phase = $phase
            $report.final_state = 'STOPPED_OWNER_DECISION_REQUIRED'
            $report.success = $false
            return [pscustomobject]$report
        }

        if ($classification.level -eq 'L1') {
            $recoveryEntry.recovery_action = 'RETRY_SAME_PHASE_DIRECTLY'
            $recoveryEntry.final_outcome = 'RETRYING'
            $report.recovery_log += $recoveryEntry
            continue
        }

        # L2: coordinated rollback of whatever was actually promoted, then
        # independently verify the baseline is restored before permitting a
        # same-SHA retry from PROMOTE_STATIC (BUILD_APP/PACKAGE_* artifacts
        # remain valid and are not redone).
        $rollbackOk = $true
        if ($staticPromoted) {
            $rb = Invoke-ReleasePhase -Action $RollbackStatic -ActionArgs @($baseline)
            $report.static_rolled_back = [bool]$rb.success
            $rollbackOk = $rollbackOk -and $rb.success
        }
        if ($appPromoted) {
            $rb = Invoke-ReleasePhase -Action $RollbackApp -ActionArgs @($baseline)
            $report.app_rolled_back = [bool]$rb.success
            $rollbackOk = $rollbackOk -and $rb.success
        }
        $verify = Invoke-ReleasePhase -Action $GetCurrentState
        $recoveryEntry.post_recovery_state = $verify.data
        $baselineRestored = (
            $rollbackOk -and $verify.success -and
            [string]$verify.data.app_sha -eq [string]$baseline.app_sha -and
            [string]$verify.data.static_sha -eq [string]$baseline.static_sha
        )

        if (-not $baselineRestored) {
            $recoveryEntry.recovery_action = 'COORDINATED_ROLLBACK_ATTEMPTED'
            $recoveryEntry.final_outcome = 'STOPPED_BASELINE_NOT_CONFIRMED'
            $report.recovery_log += $recoveryEntry
            $report.stop_reason = 'baseline_not_confirmed_after_rollback'
            $report.stop_phase = $phase
            $report.final_state = 'STOPPED_OWNER_DECISION_REQUIRED'
            $report.final_current_state = $verify.data
            $report.success = $false
            return [pscustomobject]$report
        }

        $recoveryEntry.recovery_action = 'COORDINATED_ROLLBACK_VERIFIED_BASELINE_RETRY_SAME_SHA'
        $recoveryEntry.final_outcome = 'RETRYING_FROM_PROMOTE_STATIC'
        $report.recovery_log += $recoveryEntry
        $report.final_current_state = $verify.data
        $staticPromoted = $false
        $appPromoted = $false
        $phaseIndex = $ALL_PHASES.IndexOf('PROMOTE_STATIC')
        continue
    }

    $report.success = $true
    $report.final_state = 'CANDIDATE_CANDIDATE_SUCCESS'
    return [pscustomobject]$report
}

Export-ModuleMember -Function @(
    'Get-OperationalFailureClassification',
    'New-RecoveryBudgetTracker',
    'Update-RecoveryBudget',
    'New-RootCauseKey',
    'Get-PhaseResultProperty',
    'Invoke-ReleasePhase',
    'Invoke-CoordinatedReleaseStateMachine'
)
