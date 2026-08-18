#Requires -Version 5.1
<#
.SYNOPSIS
  Deployment Workflow V3: coordinated static+app release with bounded
  operational recovery.

.DESCRIPTION
  Thin CLI entrypoint over scripts/release/CoordinatedReleaseStateMachine.psm1.
  This script itself never contains recovery/classification logic -- it only
  wires the state machine's injected phase scriptblocks to the existing,
  already-governed release scripts (build-release-image.ps1,
  package-release-image.ps1, package-static-release.ps1,
  deploy-release-image.ps1, deploy-static-release.ps1, rollback-release.ps1,
  rollback-static-release.ps1, preflight-production.ps1), each invoked as a
  bounded child process via Invoke-BoundedNativeCommand. No low-level
  build/deploy/rollback logic is duplicated here.

  Without -Execute, this is a read-only plan/precondition report -- it never
  builds, packages, promotes, or contacts Production, exactly like every
  other canonical release script's dry-run mode.

  With -Execute, -OwnerGate must be exactly 'GO_DEPLOY_WITH_BOUNDED_RECOVERY'
  (Assert-OwnerGate: exact string match, same mechanism every other gated
  release script uses). This authorizes promotion of ONE exact -ExpectedGitSha
  WITH the bounded recovery behavior documented in
  docs/deployment/deployment_workflow_v3_bounded_recovery.md -- it does NOT
  authorize changing the source SHA, modifying repo/release-tooling source
  during the run, bypassing any gate, or accepting an unverifiable Production
  state. Those remain hard L3 stops (see the state machine module).

.PARAMETER ExpectedGitSha
  The exact candidate commit to promote. Required.

.PARAMETER LayoutFile
  Release layout config (ssh alias, service names, health URLs, etc.).
  Defaults to the example layout, exactly like every other release script,
  so accidentally omitting -LayoutFile can never reach a real host.

.PARAMETER Execute
  Without this switch, only PRECHECK-equivalent validation and a plan report
  run -- no build, package, promote, or Production contact of any kind.

.PARAMETER OwnerGate
  Must equal 'GO_DEPLOY_WITH_BOUNDED_RECOVERY' when -Execute is set.

.PARAMETER MaxAttemptsPerRootCause
  Passed through to Invoke-CoordinatedReleaseStateMachine. Defaults to 2,
  matching this workflow's documented retry budget.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ExpectedGitSha,
    [string]$LayoutFile = 'deploy\release-layout.example.json',
    [switch]$Execute,
    [string]$OwnerGate,
    [int]$MaxAttemptsPerRootCause = 2
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'ReleaseTooling.psm1') -Force -DisableNameChecking
Import-Module (Join-Path $PSScriptRoot 'CoordinatedReleaseStateMachine.psm1') -Force -DisableNameChecking

function Fail($msg) {
    throw $msg
}

$repoRoot = Get-RepoRoot
$ExpectedGitSha = (Invoke-Git -Arguments @('rev-parse', "$ExpectedGitSha^{commit}") -WorkingDirectory $repoRoot).Trim()
$layout = Get-ReleaseLayout -Path (Resolve-RepoPath $LayoutFile)
$requiredOwnerGate = 'GO_DEPLOY_WITH_BOUNDED_RECOVERY'

$plan = @(
    'PRECHECK', 'BUILD_APP', 'PACKAGE_APP', 'PACKAGE_STATIC',
    'SNAPSHOT_BASELINE', 'VERIFY_ROLLBACK_READY',
    'PROMOTE_STATIC', 'VERIFY_STATIC', 'PROMOTE_APP', 'VERIFY_APP',
    'JOINT_PROVENANCE', 'PRODUCTION_SMOKE'
)

if (-not $Execute) {
    [ordered]@{
        dry_run = $true
        execute_requested = $false
        expected_git_sha = $ExpectedGitSha
        release_layout = $layout
        required_owner_gate = $requiredOwnerGate
        max_attempts_per_root_cause = $MaxAttemptsPerRootCause
        plan = $plan
        result = 'DRY_RUN_COMPLETE'
    } | ConvertTo-Json -Depth 10 | Write-Output
    return
}

Assert-OwnerGate -Provided $OwnerGate -Expected $requiredOwnerGate

$releaseArtifactsDir = Join-Path $repoRoot 'release-artifacts'
$buildScript = Join-Path $PSScriptRoot 'build-release-image.ps1'
$packageAppScript = Join-Path $PSScriptRoot 'package-release-image.ps1'
$packageStaticScript = Join-Path $PSScriptRoot 'package-static-release.ps1'
$deployAppScript = Join-Path $PSScriptRoot 'deploy-release-image.ps1'
$deployStaticScript = Join-Path $PSScriptRoot 'deploy-static-release.ps1'
$rollbackAppScript = Join-Path $PSScriptRoot 'rollback-release.ps1'
$rollbackStaticScript = Join-Path $PSScriptRoot 'rollback-static-release.ps1'
$preflightScript = Join-Path $PSScriptRoot 'preflight-production.ps1'
$verifyProductionScript = Join-Path $PSScriptRoot 'verify-production-release.ps1'

# Handoff artifact paths this run's PACKAGE_APP/PACKAGE_STATIC phases
# produce and PROMOTE_APP/PROMOTE_STATIC consume -- matching the exact
# file-based contract package-release-image.ps1/package-static-release.ps1
# already establish with deploy-release-image.ps1/deploy-static-release.ps1;
# this script does not invent a new handoff shape.
#
# Deployment Workflow V3 coordinator-review fix: the phase scriptblocks
# below deliberately do NOT call .GetNewClosure(). That method snapshots a
# scriptblock's variables (including $script:-scoped ones) at creation
# time -- a mutation to $script:someVar INSIDE a .GetNewClosure()'d block
# updates only that snapshot, never the real script scope, so a later
# phase's own scriptblock (or this script's own code after the state
# machine returns) would never see it. Confirmed live: an earlier version
# of this script used .GetNewClosure() everywhere, and $script:
# handoff variables like this one were silently never actually shared
# between phases -- undetectable by any test that used only synthetic,
# already-a-SHA fake state, and caught only once a realistic integration
# test exercised the real field-mapping/handoff logic end-to-end. Plain
# scriptblocks (no .GetNewClosure()) do not have this problem: PowerShell
# scriptblocks already carry a reference to their defining scope, so `&
# $SomePhase` from inside Invoke-CoordinatedReleaseStateMachine (a
# different module/function scope) still correctly resolves and mutates
# this script's own variables, exactly like $GetState/$Disable/etc. already
# do in the established ShadowKillSwitchDrill.psm1 precedent this design
# follows.
$script:appReleaseManifestPath = $null
$script:appArchivePath = $null
$script:appDeploymentRecordPath = $null
$script:staticManifestPath = $null
$script:staticBundlePath = $null
$script:staticArchivePath = $null

function Invoke-GovernedScript {
    <#
    .SYNOPSIS
    Runs one existing governed release script as a bounded child process and
    returns a result that DISTINGUISHES a genuine process-level timeout from
    an ordinary, definite failure (non-zero exit, or no parseable output).
    .DESCRIPTION
    Invoke-BoundedNativeCommand only ever throws for two reasons: an enforced
    process-level timeout (its message always starts with "Timed out after"
    -- see ReleaseTooling.psm1), or the child process could not be started
    at all. Both are ambiguous about whether the child's own governed
    mutation happened -- possible_timeout in the phase result below is set
    ONLY for this case. A clean, non-zero EXIT from the child (the governed
    script's own gate/verification refused, or it failed after producing a
    definite result) is a completely different, non-ambiguous situation and
    must never be conflated with "maybe it actually succeeded" -- doing so
    would let a definite governed-script failure be silently reinterpreted
    as a possibly-successful timeout and skip retry/rollback it actually
    needs.
    #>
    param(
        [Parameter(Mandatory = $true)][string]$ScriptPath,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][int]$TimeoutSeconds,
        [Parameter(Mandatory = $true)][string]$OperationLabel
    )
    $psExe = (Get-Process -Id $PID).Path
    $fullArgs = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $ScriptPath) + $Arguments
    try {
        $result = Invoke-BoundedNativeCommand -FileName $psExe -ArgumentList $fullArgs -TimeoutSeconds $TimeoutSeconds -OperationLabel $OperationLabel
    }
    catch {
        $timedOut = [string]$_.Exception.Message -like 'Timed out after*'
        return [ordered]@{ success = $false; timed_out = $timedOut; exit_code = $null; output = [string]$_.Exception.Message; data = $null }
    }
    if ($result.exit_code -ne 0) {
        return [ordered]@{ success = $false; timed_out = $false; exit_code = $result.exit_code; output = $result.output; data = $null }
    }
    $jsonStart = $result.stdout.IndexOf('{')
    if ($jsonStart -lt 0) {
        return [ordered]@{ success = $false; timed_out = $false; exit_code = $result.exit_code; output = "$OperationLabel produced no parseable JSON output: $($result.output)"; data = $null }
    }
    $data = $result.stdout.Substring($jsonStart) | ConvertFrom-Json
    return [ordered]@{ success = $true; timed_out = $false; exit_code = $result.exit_code; output = $result.output; data = $data }
}

$GetCurrentState = {
    # Coordinator-review fix: preflight-production.ps1's own current_app.
    # image_ref/image_id and static_generation.current_target are NEVER
    # Git SHAs -- image_ref/image_id are a Docker tag and content digest;
    # current_target is a remote filesystem path. Comparing either directly
    # to -ExpectedGitSha can never correctly succeed. The real source Git
    # SHA is read independently, over SSH, from the authoritative source
    # for each: the running app image's own org.opencontainers.image.revision
    # OCI label (Get-RemoteImageSourceGitSha), and the active static
    # generation's own manifest.json release_git_sha
    # (Get-RemoteStaticGenerationSourceGitSha) -- both already-proven
    # mechanisms this repository's own tooling uses elsewhere, not invented
    # here. app_sha/static_sha below are the ONLY two fields the state
    # machine itself compares to -ExpectedGitSha; every other field is kept
    # separate and is never used for a SHA-domain comparison.
    $r = Invoke-GovernedScript -ScriptPath $preflightScript `
        -Arguments @('-LayoutFile', $LayoutFile) `
        -TimeoutSeconds 90 -OperationLabel 'coordinated-release: get current state'
    if (-not $r.success) {
        return [ordered]@{ success = $false; detail = $r.output }
    }
    $preflight = $r.data
    $appImageId = [string]$preflight.current_app.image_id
    $schedulerImageId = [string]$preflight.current_scheduler.image_id
    $staticGenerationPath = [string]$preflight.static_generation.current_target
    try {
        # An Architecture V1 app release switches TWO container images
        # (app AND scheduler) plus the static generation. All three source
        # identities are established independently -- an app-only check
        # would silently accept a candidate app running beside a baseline
        # scheduler.
        $appSourceGitSha = Get-RemoteImageSourceGitSha -SshAlias $layout.ssh_alias -ImageId $appImageId -TimeoutSeconds 30
        $schedulerSourceGitSha = Get-RemoteImageSourceGitSha -SshAlias $layout.ssh_alias -ImageId $schedulerImageId -TimeoutSeconds 30
        $staticSourceGitSha = Get-RemoteStaticGenerationSourceGitSha -SshAlias $layout.ssh_alias -GenerationPath $staticGenerationPath -TimeoutSeconds 30
    }
    catch {
        return [ordered]@{ success = $false; detail = [string]$_.Exception.Message }
    }
    [ordered]@{
        success = $true
        app_sha = $appSourceGitSha
        scheduler_sha = $schedulerSourceGitSha
        static_sha = $staticSourceGitSha
        app_image_tag = [string]$preflight.current_app.image_ref
        app_image_id = $appImageId
        scheduler_image_tag = [string]$preflight.current_scheduler.image_ref
        scheduler_image_id = $schedulerImageId
        static_generation_path = $staticGenerationPath
    }
}

$Precheck = {
    [ordered]@{ success = $true; detail = "expected_git_sha=$ExpectedGitSha" }
}

$BuildApp = {
    $r = Invoke-GovernedScript -ScriptPath $buildScript `
        -Arguments @('-ExpectedGitSha', $ExpectedGitSha, '-LayoutFile', $LayoutFile) `
        -TimeoutSeconds 1800 -OperationLabel 'coordinated-release: build app image'
    if (-not $r.success) {
        return [ordered]@{ success = $false; detail = $r.output }
    }
    [ordered]@{ success = $true }
}

$PackageApp = {
    $r = Invoke-GovernedScript -ScriptPath $packageAppScript `
        -Arguments @('-ExpectedGitSha', $ExpectedGitSha, '-LayoutFile', $LayoutFile) `
        -TimeoutSeconds 300 -OperationLabel 'coordinated-release: package app'
    if (-not $r.success) {
        return [ordered]@{ success = $false; detail = $r.output }
    }
    $script:appReleaseManifestPath = [string]$r.data.release_manifest_path
    $script:appArchivePath = [string]$r.data.archive_path
    [ordered]@{ success = $true }
}

$PackageStatic = {
    $r = Invoke-GovernedScript -ScriptPath $packageStaticScript `
        -Arguments @('-ExpectedGitSha', $ExpectedGitSha) `
        -TimeoutSeconds 600 -OperationLabel 'coordinated-release: package static'
    if (-not $r.success) {
        return [ordered]@{ success = $false; detail = $r.output }
    }
    $script:staticManifestPath = [string]$r.data.manifest_path
    $script:staticBundlePath = [string]$r.data.bundle_path
    $script:staticArchivePath = [string]$r.data.archive_path
    [ordered]@{ success = $true }
}

$SnapshotBaseline = {
    $state = & $GetCurrentState
    if (-not $state.success) {
        return [ordered]@{ success = $false; detail = 'could not establish a baseline: current Production state is not independently checkable' }
    }
    # app_sha/static_sha (real Git SHAs) are the state-machine's own
    # coherence-comparison contract. app_deployment_record_path/
    # static_generation_path are ADDITIONAL, separately-tracked identity
    # concepts RollbackApp/RollbackStatic need -- never conflated with the
    # SHA fields (Section 1 of the coordinator review).
    [ordered]@{
        success = $true
        app_sha = $state.app_sha
        scheduler_sha = $state.scheduler_sha
        static_sha = $state.static_sha
        app_image_id = $state.app_image_id
        scheduler_image_id = $state.scheduler_image_id
        static_generation_path = $state.static_generation_path
    }
}

$VerifyRollbackReady = {
    param($baseline)
    if (-not $baseline -or
        [string]::IsNullOrWhiteSpace([string]$baseline.app_sha) -or
        [string]::IsNullOrWhiteSpace([string]$baseline.scheduler_sha) -or
        [string]::IsNullOrWhiteSpace([string]$baseline.static_sha) -or
        [string]::IsNullOrWhiteSpace([string]$baseline.static_generation_path)) {
        return [ordered]@{ success = $false; detail = 'baseline identity is incomplete; refusing to proceed without a usable rollback target' }
    }
    # Defence in depth: the state machine already refuses an incoherent
    # baseline at SNAPSHOT_BASELINE (L3, before any mutation). Re-assert it
    # here so this executor is independently safe if ever reused.
    if (-not (Test-ReleaseIdentityCoherent -State $baseline)) {
        return [ordered]@{ success = $false; baseline_incoherent = $true; detail = "baseline is not coherent: app_sha=$($baseline.app_sha) scheduler_sha=$($baseline.scheduler_sha) static_sha=$($baseline.static_sha)" }
    }
    [ordered]@{ success = $true }
}

$PromoteStatic = {
    $r = Invoke-GovernedScript -ScriptPath $deployStaticScript `
        -Arguments @('-ExpectedGitSha', $ExpectedGitSha, '-StaticManifest', $script:staticManifestPath, '-BundlePath', $script:staticBundlePath, '-ArchivePath', $script:staticArchivePath, '-LayoutFile', $LayoutFile, '-Execute', '-OwnerGate', 'GO_DEPLOY') `
        -TimeoutSeconds 900 -OperationLabel 'coordinated-release: promote static'
    if (-not $r.success) {
        return [ordered]@{ success = $false; possible_timeout = $r.timed_out; detail = $r.output }
    }
    [ordered]@{ success = $true; static_sha = $ExpectedGitSha }
}

$VerifyStatic = {
    param($promoted)
    # PROMOTE_STATIC's postcondition is NOT "the symlink points at a
    # generation whose manifest reports the candidate SHA". The canonical
    # deploy-static-release.ps1 also performs the post-switch container
    # restart / mount refresh and public static-byte verification -- a
    # timeout after the symlink switch but before those finish must not be
    # accepted on identity alone. This executor is what the state machine
    # re-runs to prove the full postcondition before advancing past an
    # ambiguous PROMOTE_STATIC timeout, so an identity-only check here would
    # directly reintroduce that defect.
    $state = & $GetCurrentState
    if (-not $state.success) {
        return [ordered]@{ success = $false; detail = 'could not independently verify static identity post-promotion' }
    }
    if ([string]$state.static_sha -ne $ExpectedGitSha) {
        return [ordered]@{ success = $false; detail = "active static generation is not on the candidate: static_sha=$($state.static_sha) expected=$ExpectedGitSha" }
    }

    # Independent canonical verification of the complete static postcondition,
    # reusing the existing governed mechanism rather than duplicating it:
    # preflight-production.ps1 with THIS run's candidate -StaticManifest
    #   - resolves what /current actually points at now,
    #   - verifies every manifest file's sha256 against the LIVE generation in
    #     one remote batch and fails closed on any drift
    #     ("STATIC GENERATION DRIFT: ..."), which is exactly the post-switch
    #     byte-level check,
    #   - asserts app AND scheduler AND nginx are running, not restarting and
    #     healthy (Assert-ContainerSnapshotValid) -- i.e. the post-switch
    #     restart / mount refresh really completed,
    #   - asserts /healthz returns 200 with ok=true.
    # Passing -StaticManifest is what arms the drift gate; without it
    # preflight sets drift_checked=$false and that gate is a no-op, so the
    # manifest argument below is load-bearing, not decorative.
    if ([string]::IsNullOrWhiteSpace([string]$script:staticManifestPath)) {
        return [ordered]@{ success = $false; detail = 'no candidate static manifest path is known; cannot verify the static postcondition' }
    }
    $v = Invoke-GovernedScript -ScriptPath $preflightScript `
        -Arguments @('-LayoutFile', $LayoutFile, '-StaticManifest', $script:staticManifestPath) `
        -TimeoutSeconds 300 -OperationLabel 'coordinated-release: verify static postcondition'
    if (-not $v.success) {
        return [ordered]@{ success = $false; detail = "canonical static verification did not pass: $($v.output)" }
    }

    # Defence in depth: preflight throws (non-zero exit) on drift, which the
    # check above already catches. Also assert positively on the reported
    # payload so a future change that downgraded that throw to a soft report,
    # or an invocation that somehow lost -StaticManifest, cannot silently
    # turn this into an identity-only check again.
    $staticReport = $null
    if ($v.data -and $v.data.PSObject.Properties['static_generation']) {
        $staticReport = $v.data.static_generation
    }
    if (-not $staticReport) {
        return [ordered]@{ success = $false; detail = 'canonical static verification returned no static_generation report' }
    }
    if (-not $staticReport.PSObject.Properties['drift_checked'] -or $staticReport.drift_checked -ne $true) {
        return [ordered]@{ success = $false; detail = 'canonical static verification did not actually check for drift (drift_checked was not true)' }
    }
    if ($staticReport.PSObject.Properties['drift'] -and $staticReport.drift -eq $true) {
        return [ordered]@{ success = $false; detail = 'canonical static verification reported live-static drift against the candidate manifest' }
    }
    [ordered]@{ success = $true }
}

$PromoteApp = {
    # The deployment record path is deterministic from the release manifest
    # path (see deploy-release-image.ps1's own
    # $deploymentRecordPath = Join-Path (Split-Path -Parent $manifestPath)
    # ("{0}.deployment.json" -f $artifactBaseName)) and is proactively
    # computed here -- not only captured from a successful return -- because
    # deploy-release-image.ps1 saves this record BEFORE the app switch
    # (so a rollback identity exists even if the switch itself then fails)
    # and again in its own failure path. RollbackApp must be able to use it
    # even when this phase itself returns success=$false.
    $artifactBaseName = Get-ReleaseArtifactBaseName -GitSha $ExpectedGitSha
    $script:appDeploymentRecordPath = Join-Path (Split-Path -Parent $script:appReleaseManifestPath) ("{0}.deployment.json" -f $artifactBaseName)

    $r = Invoke-GovernedScript -ScriptPath $deployAppScript `
        -Arguments @('-ExpectedGitSha', $ExpectedGitSha, '-ReleaseManifest', $script:appReleaseManifestPath, '-ReleaseArchive', $script:appArchivePath, '-LayoutFile', $LayoutFile, '-Execute', '-OwnerGate', 'GO_DEPLOY') `
        -TimeoutSeconds 900 -OperationLabel 'coordinated-release: promote app'
    if (-not $r.success) {
        return [ordered]@{ success = $false; possible_timeout = $r.timed_out; detail = $r.output }
    }
    if ($r.data.PSObject.Properties['deployment_record_path'] -and $r.data.deployment_record_path) {
        $script:appDeploymentRecordPath = [string]$r.data.deployment_record_path
    }
    [ordered]@{ success = $true; app_sha = $ExpectedGitSha }
}

$VerifyApp = {
    param($promoted)
    # PROMOTE_APP's postcondition covers BOTH container images the canonical
    # deploy switches (app and scheduler), not the app alone. This executor
    # is also what the state machine re-runs to prove the full postcondition
    # before ever advancing past an ambiguous PROMOTE_APP timeout, so an
    # app-only check here would directly reintroduce the
    # "candidate app + baseline scheduler silently accepted" defect.
    $state = & $GetCurrentState
    if (-not $state.success) {
        return [ordered]@{ success = $false; detail = 'could not independently verify app/scheduler identity post-promotion' }
    }
    if ([string]$state.app_sha -ne $ExpectedGitSha) {
        return [ordered]@{ success = $false; detail = "app image is not on the candidate: app_sha=$($state.app_sha) expected=$ExpectedGitSha" }
    }
    if ([string]$state.scheduler_sha -ne $ExpectedGitSha) {
        return [ordered]@{ success = $false; detail = "scheduler image is not on the candidate: scheduler_sha=$($state.scheduler_sha) expected=$ExpectedGitSha" }
    }
    # Independent canonical verification of the complete phase postcondition
    # (app+scheduler runtime health, questions gate, nginx/public routes) via
    # the existing governed verifier -- identity agreement alone is not proof
    # the whole canonical deploy sequence completed.
    $v = Invoke-GovernedScript -ScriptPath $verifyProductionScript `
        -Arguments @('-ReleaseManifest', $script:appReleaseManifestPath, '-LayoutFile', $LayoutFile) `
        -TimeoutSeconds 420 -OperationLabel 'coordinated-release: verify app postcondition'
    if (-not $v.success) {
        return [ordered]@{ success = $false; detail = "canonical production verification did not pass: $($v.output)" }
    }
    [ordered]@{ success = $true }
}

$ProductionSmoke = {
    $state = & $GetCurrentState
    [ordered]@{ success = $state.success }
}

$RollbackStatic = {
    param($baseline)
    # -TargetGenerationPath needs the baseline's static generation
    # DIRECTORY PATH, not its source Git SHA -- these are two separate
    # identity concepts (Section 1 of the coordinator review) and must
    # never be conflated.
    if ([string]::IsNullOrWhiteSpace([string]$baseline.static_generation_path)) {
        return [ordered]@{ success = $false; detail = 'no static generation path captured in baseline; cannot construct a rollback target' }
    }
    $r = Invoke-GovernedScript -ScriptPath $rollbackStaticScript `
        -Arguments @('-TargetGenerationPath', [string]$baseline.static_generation_path, '-LayoutFile', $LayoutFile, '-Execute', '-OwnerGate', 'GO_ROLLBACK') `
        -TimeoutSeconds 600 -OperationLabel 'coordinated-release: rollback static'
    if (-not $r.success) {
        return [ordered]@{ success = $false; detail = $r.output }
    }
    [ordered]@{ success = $true }
}

$RollbackApp = {
    param($baseline)
    # Must be the actionable deployment record deploy-release-image.ps1
    # itself wrote (containing rollback_image_identity -- the actual
    # pre-promotion app/scheduler image identity) -- NEVER the package-time
    # release manifest, which describes the candidate being promoted and
    # has no "previous" identity to roll back to at all.
    if ([string]::IsNullOrWhiteSpace([string]$script:appDeploymentRecordPath)) {
        return [ordered]@{ success = $false; detail = 'no app deployment record path is known; cannot construct a rollback manifest' }
    }
    $r = Invoke-GovernedScript -ScriptPath $rollbackAppScript `
        -Arguments @('-RollbackManifest', $script:appDeploymentRecordPath, '-LayoutFile', $LayoutFile, '-Execute', '-OwnerGate', 'GO_ROLLBACK') `
        -TimeoutSeconds 600 -OperationLabel 'coordinated-release: rollback app'
    if (-not $r.success) {
        return [ordered]@{ success = $false; detail = $r.output }
    }
    [ordered]@{ success = $true }
}

$result = Invoke-CoordinatedReleaseStateMachine `
    -ExpectedGitSha $ExpectedGitSha `
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
    -RollbackApp $RollbackApp `
    -MaxAttemptsPerRootCause $MaxAttemptsPerRootCause

$result | ConvertTo-Json -Depth 12 | Write-Output
if (-not $result.success) {
    exit 1
}
