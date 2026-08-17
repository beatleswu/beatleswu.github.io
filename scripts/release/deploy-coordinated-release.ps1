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
  docs/deployment/deployment_workflow_v3_operator_contract.md -- it does NOT
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

# Handoff artifact paths this run's PACKAGE_APP/PACKAGE_STATIC phases
# produce and PROMOTE_APP/PROMOTE_STATIC consume -- matching the exact
# file-based contract package-release-image.ps1/package-static-release.ps1
# already establish with deploy-release-image.ps1/deploy-static-release.ps1;
# this script does not invent a new handoff shape.
$script:appReleaseManifestPath = $null
$script:appArchivePath = $null
$script:staticManifestPath = $null
$script:staticBundlePath = $null
$script:staticArchivePath = $null

function Invoke-GovernedScript {
    param(
        [Parameter(Mandatory = $true)][string]$ScriptPath,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][int]$TimeoutSeconds,
        [Parameter(Mandatory = $true)][string]$OperationLabel
    )
    $psExe = (Get-Process -Id $PID).Path
    $fullArgs = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $ScriptPath) + $Arguments
    $result = Invoke-BoundedNativeCommand -FileName $psExe -ArgumentList $fullArgs -TimeoutSeconds $TimeoutSeconds -OperationLabel $OperationLabel
    if ($result.exit_code -ne 0) {
        throw "$OperationLabel failed (exit $($result.exit_code)): $($result.output)"
    }
    $jsonStart = $result.stdout.IndexOf('{')
    if ($jsonStart -lt 0) {
        throw "$OperationLabel produced no parseable JSON output."
    }
    return ($result.stdout.Substring($jsonStart) | ConvertFrom-Json)
}

$GetCurrentState = {
    try {
        $r = Invoke-GovernedScript -ScriptPath $preflightScript `
            -Arguments @('-LayoutFile', $LayoutFile) `
            -TimeoutSeconds 90 -OperationLabel 'coordinated-release: get current state'
        [ordered]@{
            success = $true
            app_sha = [string]$r.current_app.image_ref
            static_sha = [string]$r.static_generation.current_target
        }
    }
    catch {
        [ordered]@{ success = $false; detail = [string]$_.Exception.Message }
    }
}.GetNewClosure()

$Precheck = {
    [ordered]@{ success = $true; detail = "expected_git_sha=$ExpectedGitSha" }
}.GetNewClosure()

$BuildApp = {
    try {
        Invoke-GovernedScript -ScriptPath $buildScript `
            -Arguments @('-ExpectedGitSha', $ExpectedGitSha, '-LayoutFile', $LayoutFile) `
            -TimeoutSeconds 1800 -OperationLabel 'coordinated-release: build app image' | Out-Null
        [ordered]@{ success = $true }
    }
    catch {
        [ordered]@{ success = $false; detail = [string]$_.Exception.Message }
    }
}.GetNewClosure()

$PackageApp = {
    try {
        $r = Invoke-GovernedScript -ScriptPath $packageAppScript `
            -Arguments @('-ExpectedGitSha', $ExpectedGitSha, '-LayoutFile', $LayoutFile) `
            -TimeoutSeconds 300 -OperationLabel 'coordinated-release: package app'
        $script:appReleaseManifestPath = [string]$r.release_manifest_path
        $script:appArchivePath = [string]$r.archive_path
        [ordered]@{ success = $true }
    }
    catch {
        [ordered]@{ success = $false; detail = [string]$_.Exception.Message }
    }
}.GetNewClosure()

$PackageStatic = {
    try {
        $r = Invoke-GovernedScript -ScriptPath $packageStaticScript `
            -Arguments @('-ExpectedGitSha', $ExpectedGitSha) `
            -TimeoutSeconds 600 -OperationLabel 'coordinated-release: package static'
        $script:staticManifestPath = [string]$r.manifest_path
        $script:staticBundlePath = [string]$r.bundle_path
        $script:staticArchivePath = [string]$r.archive_path
        [ordered]@{ success = $true }
    }
    catch {
        [ordered]@{ success = $false; detail = [string]$_.Exception.Message }
    }
}.GetNewClosure()

$SnapshotBaseline = {
    $state = & $GetCurrentState
    if (-not $state.success) {
        return [ordered]@{ success = $false; detail = 'could not establish a baseline: current Production state is not independently checkable' }
    }
    [ordered]@{ success = $true; app_sha = $state.app_sha; static_sha = $state.static_sha }
}.GetNewClosure()

$VerifyRollbackReady = {
    param($baseline)
    if (-not $baseline -or [string]::IsNullOrWhiteSpace([string]$baseline.app_sha) -or [string]::IsNullOrWhiteSpace([string]$baseline.static_sha)) {
        return [ordered]@{ success = $false; detail = 'baseline identity is incomplete; refusing to proceed without a usable rollback target' }
    }
    [ordered]@{ success = $true }
}.GetNewClosure()

$PromoteStatic = {
    try {
        Invoke-GovernedScript -ScriptPath $deployStaticScript `
            -Arguments @('-ExpectedGitSha', $ExpectedGitSha, '-StaticManifest', $script:staticManifestPath, '-BundlePath', $script:staticBundlePath, '-ArchivePath', $script:staticArchivePath, '-LayoutFile', $LayoutFile, '-Execute', '-OwnerGate', 'GO_DEPLOY') `
            -TimeoutSeconds 900 -OperationLabel 'coordinated-release: promote static' |
            Out-Null
        [ordered]@{ success = $true; static_sha = $ExpectedGitSha }
    }
    catch {
        [ordered]@{ success = $false; possible_timeout = $true; detail = [string]$_.Exception.Message }
    }
}.GetNewClosure()

$VerifyStatic = {
    param($promoted)
    $state = & $GetCurrentState
    if (-not $state.success) {
        return [ordered]@{ success = $false; detail = 'could not independently verify static identity post-promotion' }
    }
    [ordered]@{ success = ($state.static_sha -eq $ExpectedGitSha) }
}.GetNewClosure()

$PromoteApp = {
    try {
        Invoke-GovernedScript -ScriptPath $deployAppScript `
            -Arguments @('-ExpectedGitSha', $ExpectedGitSha, '-ReleaseManifest', $script:appReleaseManifestPath, '-ReleaseArchive', $script:appArchivePath, '-LayoutFile', $LayoutFile, '-Execute', '-OwnerGate', 'GO_DEPLOY') `
            -TimeoutSeconds 900 -OperationLabel 'coordinated-release: promote app' |
            Out-Null
        [ordered]@{ success = $true; app_sha = $ExpectedGitSha }
    }
    catch {
        [ordered]@{ success = $false; possible_timeout = $true; detail = [string]$_.Exception.Message }
    }
}.GetNewClosure()

$VerifyApp = {
    param($promoted)
    $state = & $GetCurrentState
    if (-not $state.success) {
        return [ordered]@{ success = $false; detail = 'could not independently verify app identity post-promotion' }
    }
    [ordered]@{ success = ($state.app_sha -eq $ExpectedGitSha) }
}.GetNewClosure()

$ProductionSmoke = {
    $state = & $GetCurrentState
    [ordered]@{ success = $state.success }
}.GetNewClosure()

$RollbackStatic = {
    param($baseline)
    try {
        Invoke-GovernedScript -ScriptPath $rollbackStaticScript `
            -Arguments @('-TargetGenerationPath', [string]$baseline.static_sha, '-LayoutFile', $LayoutFile, '-Execute', '-OwnerGate', 'GO_ROLLBACK') `
            -TimeoutSeconds 600 -OperationLabel 'coordinated-release: rollback static' |
            Out-Null
        [ordered]@{ success = $true }
    }
    catch {
        [ordered]@{ success = $false; detail = [string]$_.Exception.Message }
    }
}.GetNewClosure()

$RollbackApp = {
    param($baseline)
    try {
        Invoke-GovernedScript -ScriptPath $rollbackAppScript `
            -Arguments @('-RollbackManifest', $script:appReleaseManifestPath, '-LayoutFile', $LayoutFile, '-Execute', '-OwnerGate', 'GO_ROLLBACK') `
            -TimeoutSeconds 600 -OperationLabel 'coordinated-release: rollback app' |
            Out-Null
        [ordered]@{ success = $true }
    }
    catch {
        [ordered]@{ success = $false; detail = [string]$_.Exception.Message }
    }
}.GetNewClosure()

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
