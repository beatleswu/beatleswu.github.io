#requires -Version 5.1
<#
.SYNOPSIS
The canonical Production deployment entrypoint: one short, linear, bounded,
rollbackable, independently verified sequence over the proven release tools.

.DESCRIPTION
This is the recommended path for deploying an exact Git SHA to Production.

It is deliberately a STRAIGHT LINE, not an orchestration framework. It has
eight named phases, executed once each, in order:

    PRECHECK -> BUILD -> PACKAGE -> BASELINE -> STATIC -> APP -> VERIFY -> SUCCESS

Two design rules make this path predictable, and both exist because of real
failures observed in production runs of the previous generic state machine:

1. IT NEVER PARSES A CHILD SCRIPT'S HUMAN-READABLE STDOUT.
   Every fact this script acts on comes from one of three deterministic
   sources: a child's process EXIT CODE, an ARTIFACT FILE at a path derived
   from the SHA via Get-ReleaseArtifactBaseName, or a DIRECT identity read
   (a --format template or a file read over SSH). Scraping a build log for a
   JSON payload once turned a fully successful build into a phantom failure;
   there is no log scraping here to regress into.

2. IT HAS NO GENERIC RECOVERY MACHINERY.
   No state machine, no root-cause taxonomy, no per-error retry budget. A
   step either succeeds or the deployment stops. If it stops AFTER Production
   was mutated, this script rolls the mutated components back with the
   canonical rollback tools and then PROVES the original baseline is intact
   before reporting failure.

Everything that actually touches Production is delegated to the existing
canonical tools, which already own their own transfer, validation, atomic
switch, verification and self-rollback behaviour. This script sequences them
and checks their results; it does not reimplement them.

.PARAMETER ExpectedGitSha
The exact 40-character commit SHA to deploy. Every identity gate compares
against this value and nothing else.

.PARAMETER LayoutFile
Release layout describing the Production topology.

.PARAMETER Execute
Required for any Production mutation. Without it this script performs
PRECHECK/BUILD/PACKAGE/BASELINE and then stops, having proven the candidate
and the baseline without changing anything.

.PARAMETER OwnerGate
Must be exactly GO_DEPLOY when -Execute is supplied. Rollback steps use the
canonical GO_ROLLBACK gate internally.

.EXAMPLE
.\deploy-production.ps1 -ExpectedGitSha <sha> -LayoutFile deploy\release-layout.production.json -Execute -OwnerGate GO_DEPLOY
#>
param(
    [Parameter(Mandatory = $true)][string]$ExpectedGitSha,
    [string]$LayoutFile = 'deploy\release-layout.example.json',
    [switch]$Execute,
    [string]$OwnerGate
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'ReleaseTooling.psm1') -Force -DisableNameChecking

# ----------------------------------------------------------------------
# Bounds. Finite, per child process. These are per-invocation limits, NOT a
# total for the phase -- a phase runs its child exactly once, so here the two
# happen to be the same number. That equivalence is the point: there is no
# replay loop that could multiply them.
# ----------------------------------------------------------------------
$BUILD_TIMEOUT_SECONDS = 3900
$PACKAGE_APP_TIMEOUT_SECONDS = 900
$PACKAGE_STATIC_TIMEOUT_SECONDS = 900
$DEPLOY_STATIC_TIMEOUT_SECONDS = 1200
$DEPLOY_APP_TIMEOUT_SECONDS = 1200
$VERIFY_TIMEOUT_SECONDS = 600
$ROLLBACK_TIMEOUT_SECONDS = 900
$IDENTITY_READ_TIMEOUT_SECONDS = 30
$READINESS_TIMEOUT_SECONDS = 120

$script:phaseIndex = 0
function Write-Phase {
    param([Parameter(Mandatory = $true)][string]$Name)
    $script:phaseIndex++
    Write-Host ''
    Write-Host ("== [{0}/8] {1} ==" -f $script:phaseIndex, $Name)
}

function Write-Step {
    param([Parameter(Mandatory = $true)][string]$Message)
    Write-Host ("   {0}" -f $Message)
}

function Fail-Deployment {
    param([Parameter(Mandatory = $true)][string]$Message)
    throw $Message
}

function Invoke-ReleaseStep {
    <#
    Runs one canonical release script as a bounded child process and returns
    ONLY its exit code plus its output for human display.

    The returned output is written to the console for the operator and is
    never inspected programmatically. Callers decide success from the exit
    code, and then prove the postcondition from artifacts or identity reads.
    #>
    param(
        [Parameter(Mandatory = $true)][string]$ScriptPath,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][int]$TimeoutSeconds,
        [Parameter(Mandatory = $true)][string]$Label
    )
    if (-not (Test-Path -LiteralPath $ScriptPath)) {
        Fail-Deployment "Required release script is missing: $ScriptPath"
    }
    $psExe = (Get-Process -Id $PID).Path
    $fullArgs = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $ScriptPath) + $Arguments
    Write-Step ("running {0} (bound {1}s)" -f (Split-Path -Leaf $ScriptPath), $TimeoutSeconds)
    try {
        $result = Invoke-BoundedNativeCommand -FileName $psExe -ArgumentList $fullArgs `
            -TimeoutSeconds $TimeoutSeconds -OperationLabel $Label
    }
    catch {
        # Invoke-BoundedNativeCommand throws only on an enforced timeout or a
        # failure to start the child at all. Both mean "this step did not
        # report a definite result"; the caller treats that as failure and,
        # if Production was already mutated, inspects real state before
        # deciding anything.
        Write-Step ("FAILED: {0}" -f $_.Exception.Message)
        return [ordered]@{ exit_code = $null; completed = $false; detail = [string]$_.Exception.Message }
    }
    if ($result.output) { Write-Host $result.output }
    return [ordered]@{ exit_code = $result.exit_code; completed = $true; detail = '' }
}

function Get-ProductionIdentity {
    <#
    Reads the three governed source-SHA identities directly from Production.

    Each is read independently and in its own domain: the app and scheduler
    SHAs come from the OCI revision label on the image each container is
    actually running; the static SHA comes from release_git_sha inside the
    manifest.json of the generation the `current` symlink actually resolves
    to. An image id and a generation path are NOT Git SHAs and are never
    compared as such.
    #>
    param([Parameter(Mandatory = $true)]$Layout)
    $sshAlias = [string]$Layout.ssh_alias
    $appImageId = Get-RemoteContainerImageId -SshAlias $sshAlias -ContainerName ([string]$Layout.app_service_name) -TimeoutSeconds $IDENTITY_READ_TIMEOUT_SECONDS
    $schedulerImageId = Get-RemoteContainerImageId -SshAlias $sshAlias -ContainerName ([string]$Layout.scheduler_service_name) -TimeoutSeconds $IDENTITY_READ_TIMEOUT_SECONDS
    $generationPath = Get-RemoteStaticCurrentGenerationPath -SshAlias $sshAlias -StaticReleaseRoot ([string]$Layout.static_release_root) -TimeoutSeconds $IDENTITY_READ_TIMEOUT_SECONDS
    return [ordered]@{
        app_source_sha = Get-RemoteImageSourceGitSha -SshAlias $sshAlias -ImageId $appImageId -TimeoutSeconds $IDENTITY_READ_TIMEOUT_SECONDS
        scheduler_source_sha = Get-RemoteImageSourceGitSha -SshAlias $sshAlias -ImageId $schedulerImageId -TimeoutSeconds $IDENTITY_READ_TIMEOUT_SECONDS
        static_source_sha = Get-RemoteStaticGenerationSourceGitSha -SshAlias $sshAlias -GenerationPath $generationPath -TimeoutSeconds $IDENTITY_READ_TIMEOUT_SECONDS
        static_generation_path = $generationPath
    }
}

function Test-IdentityIsUniformly {
    param(
        [Parameter(Mandatory = $true)]$Identity,
        [Parameter(Mandatory = $true)][string]$Sha
    )
    return (($Identity.app_source_sha -eq $Sha) -and
            ($Identity.scheduler_source_sha -eq $Sha) -and
            ($Identity.static_source_sha -eq $Sha))
}

function Write-Identity {
    param([Parameter(Mandatory = $true)][string]$Title, [Parameter(Mandatory = $true)]$Identity)
    Write-Step ("{0}: app={1} scheduler={2} static={3}" -f $Title,
        $Identity.app_source_sha, $Identity.scheduler_source_sha, $Identity.static_source_sha)
}

# ======================================================================
# PRECHECK
# ======================================================================
Write-Phase 'PRECHECK'

if ($Execute) {
    if ([string]::IsNullOrWhiteSpace($OwnerGate)) {
        Fail-Deployment 'A Production deployment requires -OwnerGate GO_DEPLOY.'
    }
    Assert-OwnerGate -Provided $OwnerGate -Expected 'GO_DEPLOY'
    Write-Step 'owner gate GO_DEPLOY accepted'
}
else {
    Write-Step 'no -Execute: this run stops after BASELINE and mutates nothing'
}

if ($ExpectedGitSha -notmatch '^[0-9a-f]{40}$') {
    Fail-Deployment "ExpectedGitSha must be a full 40-character commit SHA; got '$ExpectedGitSha'."
}

$repoRoot = Get-RepoRoot
Assert-TrackedTreeClean -WorkingDirectory $repoRoot
Assert-CompleteWorktreeClean -WorkingDirectory $repoRoot
Write-Step 'working tree clean (tracked and untracked)'

$headSha = Get-SafeFirstOutputLine (& git -C $repoRoot rev-parse HEAD)
if ($headSha -ne $ExpectedGitSha) {
    Fail-Deployment "Worktree HEAD is $headSha but -ExpectedGitSha is $ExpectedGitSha. Deploy from the exact commit."
}
Write-Step "HEAD == ExpectedGitSha ($ExpectedGitSha)"

$layoutPath = Resolve-RepoPath $LayoutFile
$layout = Get-ReleaseLayout -Path $layoutPath
Write-Step "layout $LayoutFile loaded (ssh_alias=$($layout.ssh_alias))"

$artifactBaseName = Get-ReleaseArtifactBaseName -GitSha $ExpectedGitSha
$artifactDirectory = Join-Path $repoRoot 'release-artifacts'
$appArchivePath = Join-Path $artifactDirectory ("{0}.tar" -f $artifactBaseName)
$appManifestPath = Join-Path $artifactDirectory ("{0}.release.json" -f $artifactBaseName)
$appDeploymentRecordPath = Join-Path $artifactDirectory ("{0}.deployment.json" -f $artifactBaseName)
$staticManifestPath = Join-Path $artifactDirectory ("{0}.static.json" -f $artifactBaseName)
$staticBundlePath = Join-Path $artifactDirectory ("{0}.static-bundle" -f $artifactBaseName)
$staticArchivePath = Join-Path $artifactDirectory ("{0}.static.tar" -f $artifactBaseName)
Write-Step "artifact base name $artifactBaseName (all artifact paths derived, not discovered)"

$buildScript = Join-Path $PSScriptRoot 'build-release-image.ps1'
$packageAppScript = Join-Path $PSScriptRoot 'package-release-image.ps1'
$packageStaticScript = Join-Path $PSScriptRoot 'package-static-release.ps1'
$deployStaticScript = Join-Path $PSScriptRoot 'deploy-static-release.ps1'
$deployAppScript = Join-Path $PSScriptRoot 'deploy-release-image.ps1'
$rollbackStaticScript = Join-Path $PSScriptRoot 'rollback-static-release.ps1'
$rollbackAppScript = Join-Path $PSScriptRoot 'rollback-release.ps1'
$verifyScript = Join-Path $PSScriptRoot 'verify-production-release.ps1'

# ======================================================================
# BUILD
# ======================================================================
Write-Phase 'BUILD'

$imageTag = "go-odyssey-app:{0}" -f (Get-ShortGitSha -GitSha $ExpectedGitSha)

function Test-CandidateImageProven {
    <#
    Proves an exact candidate already exists locally, from Docker identity
    only. All four facts must hold independently: the image exists, its OCI
    revision label is exactly ExpectedGitSha, its platform is linux/arm64,
    and its image id is readable. Nothing here reads a build log.
    #>
    param([Parameter(Mandatory = $true)][string]$Tag, [Parameter(Mandatory = $true)][string]$Sha)
    $inspect = & docker image inspect $Tag --format '{{index .Config.Labels "org.opencontainers.image.revision"}}|{{.Os}}/{{.Architecture}}|{{.Id}}' 2>$null
    if ($LASTEXITCODE -ne 0) { return $null }
    $line = Get-SafeFirstOutputLine $inspect
    if ([string]::IsNullOrWhiteSpace($line)) { return $null }
    $parts = $line -split '\|'
    if ($parts.Count -lt 3) { return $null }
    if ($parts[0] -ne $Sha) { return $null }
    if ($parts[1] -ne 'linux/arm64') { return $null }
    if ([string]::IsNullOrWhiteSpace($parts[2])) { return $null }
    return [ordered]@{ revision = $parts[0]; platform = $parts[1]; image_id = $parts[2] }
}

function Assert-BuildEnvironmentReady {
    <#
    Establishes local Docker/buildx readiness BEFORE the expensive build.

    The known temporary condition is an inactive builder node, which makes
    `docker buildx inspect` omit its Platforms: line. Exactly one bounded
    recovery is attempted -- `docker buildx inspect --bootstrap` -- and then
    readiness is re-checked. If it is still not ready, this stops here,
    before Production is touched and before the build gate spends ten
    minutes to reach the same conclusion.

    This is preparation, not a deployment attempt, and it deliberately never
    downgrades the requirement: no plain-docker fallback, no assuming
    arm64 support, no proceeding on unknown capability.
    #>
    $requiredPlatform = 'linux/arm64'

    & docker version --format '{{.Server.Version}}' *> $null
    if ($LASTEXITCODE -ne 0) {
        Fail-Deployment 'Docker engine is not reachable. Start Docker and retry; nothing has been changed.'
    }
    Write-Step 'docker engine reachable'

    function Get-BuildxPlatformLine {
        $out = @(& docker buildx inspect 2>$null)
        if ($LASTEXITCODE -ne 0) { return $null }
        foreach ($line in $out) {
            if ($null -ne $line -and $line -match '^Platforms:\s*(.+?)\s*$') { return $Matches[1] }
        }
        return $null
    }

    $platformLine = Get-BuildxPlatformLine
    if ($null -eq $platformLine) {
        Write-Step 'buildx builder is not reporting platforms; attempting one bounded bootstrap'
        & docker buildx inspect --bootstrap *> $null
        $platformLine = Get-BuildxPlatformLine
    }
    if ($null -eq $platformLine) {
        Fail-Deployment 'buildx builder is still not reporting platform capability after one bootstrap. Fix the local builder (QEMU/binfmt or Docker Desktop connectivity) and retry; nothing has been changed.'
    }
    $platforms = @($platformLine -split ',\s*' | Where-Object { $_ })
    if ($platforms -notcontains $requiredPlatform) {
        Fail-Deployment "buildx builder does not report $requiredPlatform (reported: $($platforms -join ', ')). Refusing to build; nothing has been changed."
    }
    Write-Step "buildx builder active and reports $requiredPlatform"
}

$candidate = Test-CandidateImageProven -Tag $imageTag -Sha $ExpectedGitSha
if ($null -ne $candidate) {
    # An exact candidate is already present and independently proven. Do not
    # spend a full rebuild to re-establish a fact Docker already asserts.
    Write-Step "existing candidate proven: $imageTag revision=$ExpectedGitSha platform=linux/arm64"
    Write-Step 'skipping rebuild (identity proven from Docker, not from a log)'
}
else {
    Assert-BuildEnvironmentReady
    $build = Invoke-ReleaseStep -ScriptPath $buildScript `
        -Arguments @('-ExpectedGitSha', $ExpectedGitSha, '-LayoutFile', $LayoutFile) `
        -TimeoutSeconds $BUILD_TIMEOUT_SECONDS -Label 'deploy-production: build app image'
    if ((-not $build.completed) -or ($build.exit_code -ne 0)) {
        Fail-Deployment "BUILD failed (exit $($build.exit_code)). Nothing has been changed in Production."
    }
    $candidate = Test-CandidateImageProven -Tag $imageTag -Sha $ExpectedGitSha
    if ($null -eq $candidate) {
        Fail-Deployment "BUILD reported success but $imageTag does not independently prove revision=$ExpectedGitSha on linux/arm64. Nothing has been changed in Production."
    }
    Write-Step "candidate proven: $imageTag revision=$ExpectedGitSha platform=linux/arm64"
}
$candidateImageId = [string]$candidate.image_id

# ======================================================================
# PACKAGE
# ======================================================================
Write-Phase 'PACKAGE'

$packageApp = Invoke-ReleaseStep -ScriptPath $packageAppScript `
    -Arguments @('-ExpectedGitSha', $ExpectedGitSha, '-LayoutFile', $LayoutFile) `
    -TimeoutSeconds $PACKAGE_APP_TIMEOUT_SECONDS -Label 'deploy-production: package app'
if ((-not $packageApp.completed) -or ($packageApp.exit_code -ne 0)) {
    Fail-Deployment "PACKAGE (app) failed (exit $($packageApp.exit_code)). Nothing has been changed in Production."
}
foreach ($required in @($appArchivePath, $appManifestPath)) {
    if (-not (Test-Path -LiteralPath $required)) {
        Fail-Deployment "PACKAGE (app) did not produce the expected artifact $required. Nothing has been changed in Production."
    }
}
# Field names here are the canonical ones New-ReleaseManifestObject actually
# writes (ReleaseTooling.psm1) -- release_git_sha / oci_revision / image_id,
# NOT a guessed "git_sha". image_id is cross-checked against the candidate
# Docker itself proved in BUILD, so the packaged archive cannot silently
# describe a different image than the one that was verified.
$appManifest = Read-JsonFile -Path $appManifestPath
if ([string]$appManifest.release_git_sha -ne $ExpectedGitSha) {
    Fail-Deployment "App release manifest release_git_sha is '$($appManifest.release_git_sha)', expected $ExpectedGitSha. Nothing has been changed in Production."
}
if ([string]$appManifest.oci_revision -ne $ExpectedGitSha) {
    Fail-Deployment "App release manifest oci_revision is '$($appManifest.oci_revision)', expected $ExpectedGitSha. Nothing has been changed in Production."
}
if ([string]$appManifest.image_id -ne $candidateImageId) {
    Fail-Deployment "App release manifest image_id is '$($appManifest.image_id)' but the verified candidate image is '$candidateImageId'. Nothing has been changed in Production."
}
Write-Step "app artifacts verified (release_git_sha, oci_revision, image_id all match the proven candidate)"

$packageStatic = Invoke-ReleaseStep -ScriptPath $packageStaticScript `
    -Arguments @('-ExpectedGitSha', $ExpectedGitSha) `
    -TimeoutSeconds $PACKAGE_STATIC_TIMEOUT_SECONDS -Label 'deploy-production: package static'
if ((-not $packageStatic.completed) -or ($packageStatic.exit_code -ne 0)) {
    Fail-Deployment "PACKAGE (static) failed (exit $($packageStatic.exit_code)). Nothing has been changed in Production."
}
foreach ($required in @($staticManifestPath, $staticArchivePath)) {
    if (-not (Test-Path -LiteralPath $required)) {
        Fail-Deployment "PACKAGE (static) did not produce the expected artifact $required. Nothing has been changed in Production."
    }
}
$staticManifest = Read-JsonFile -Path $staticManifestPath
if ([string]$staticManifest.release_git_sha -ne $ExpectedGitSha) {
    Fail-Deployment "Static manifest identity is $($staticManifest.release_git_sha), expected $ExpectedGitSha. Nothing has been changed in Production."
}
Write-Step "static artifacts verified (manifest release_git_sha == $ExpectedGitSha)"

# ======================================================================
# BASELINE
# ======================================================================
Write-Phase 'BASELINE'

$baseline = Get-ProductionIdentity -Layout $layout
Write-Identity -Title 'current Production' -Identity $baseline
Write-Step "static generation path: $($baseline.static_generation_path)"

if (-not (Test-IdentityIsUniformly -Identity $baseline -Sha ([string]$baseline.app_source_sha))) {
    Fail-Deployment ("Production baseline is MIXED (app={0} scheduler={1} static={2}). Refusing to mutate a Production that has no single coherent identity to roll back to." -f
        $baseline.app_source_sha, $baseline.scheduler_source_sha, $baseline.static_source_sha)
}
$baselineSha = [string]$baseline.app_source_sha
$baselineStaticGenerationPath = [string]$baseline.static_generation_path
if ([string]::IsNullOrWhiteSpace($baselineStaticGenerationPath)) {
    Fail-Deployment 'No static rollback identity (current generation path) could be captured. Refusing to mutate.'
}
Write-Step "baseline coherent at $baselineSha; rollback identities captured"

if ($baselineSha -eq $ExpectedGitSha) {
    Write-Step "Production is already at $ExpectedGitSha; nothing to deploy."
    Write-Host ''
    Write-Host '== ALREADY AT TARGET =='
    Write-Output (ConvertTo-FramedJsonRecord -InputObject ([ordered]@{
        result = 'ALREADY_AT_TARGET'
        expected_git_sha = $ExpectedGitSha
        baseline_git_sha = $baselineSha
        mutated = $false
    }) -Prefix '__GO_ODYSSEY_POWERSHELL_RESULT_V1__:')
    exit 0
}

if (-not $Execute) {
    Write-Host ''
    Write-Host '== PREPARED (no -Execute; Production untouched) =='
    Write-Output (ConvertTo-FramedJsonRecord -InputObject ([ordered]@{
        result = 'PREPARED_NOT_EXECUTED'
        expected_git_sha = $ExpectedGitSha
        baseline_git_sha = $baselineSha
        candidate_image_id = $candidateImageId
        app_manifest_path = $appManifestPath
        static_manifest_path = $staticManifestPath
        mutated = $false
    }) -Prefix '__GO_ODYSSEY_POWERSHELL_RESULT_V1__:')
    exit 0
}

# ----------------------------------------------------------------------
# From here on Production can change. Everything below either reaches
# SUCCESS or restores $baselineSha and reports failure.
# ----------------------------------------------------------------------
$staticPromoted = $false
$appPromoted = $false

function Restore-Baseline {
    <#
    Rolls back exactly the components this run promoted, using the canonical
    rollback tools, and then PROVES the original baseline is coherent again.

    App is restored first because its deployment record is what pins the
    pre-promotion image identity; static is restored to the exact generation
    path captured in BASELINE. The final word is an independent identity
    read, never the rollback tools' own say-so.
    #>
    param([Parameter(Mandatory = $true)][string]$Reason)
    Write-Host ''
    Write-Host '== ROLLBACK =='
    Write-Step $Reason

    if ($script:appPromoted) {
        if (Test-Path -LiteralPath $appDeploymentRecordPath) {
            $rb = Invoke-ReleaseStep -ScriptPath $rollbackAppScript `
                -Arguments @('-RollbackManifest', $appDeploymentRecordPath, '-LayoutFile', $LayoutFile, '-Execute', '-OwnerGate', 'GO_ROLLBACK') `
                -TimeoutSeconds $ROLLBACK_TIMEOUT_SECONDS -Label 'deploy-production: rollback app'
            if ((-not $rb.completed) -or ($rb.exit_code -ne 0)) {
                Write-Step 'app rollback did not complete cleanly; state will be judged by identity read'
            }
        }
        else {
            Write-Step "no app deployment record at $appDeploymentRecordPath; cannot construct an app rollback"
        }
    }

    if ($script:staticPromoted) {
        $rb = Invoke-ReleaseStep -ScriptPath $rollbackStaticScript `
            -Arguments @('-TargetGenerationPath', $baselineStaticGenerationPath, '-LayoutFile', $LayoutFile, '-Execute', '-OwnerGate', 'GO_ROLLBACK') `
            -TimeoutSeconds $ROLLBACK_TIMEOUT_SECONDS -Label 'deploy-production: rollback static'
        if ((-not $rb.completed) -or ($rb.exit_code -ne 0)) {
            Write-Step 'static rollback did not complete cleanly; state will be judged by identity read'
        }
    }

    $after = Get-ProductionIdentity -Layout $layout
    Write-Identity -Title 'after rollback' -Identity $after
    if (Test-IdentityIsUniformly -Identity $after -Sha $baselineSha) {
        Write-Host ''
        Write-Host '== FAILED (baseline restored) =='
        Write-Output (ConvertTo-FramedJsonRecord -InputObject ([ordered]@{
            result = 'FAILED_BASELINE_RESTORED'
            expected_git_sha = $ExpectedGitSha
            baseline_git_sha = $baselineSha
            app_source_sha = $after.app_source_sha
            scheduler_source_sha = $after.scheduler_source_sha
            static_source_sha = $after.static_source_sha
            reason = $Reason
        }) -Prefix '__GO_ODYSSEY_POWERSHELL_RESULT_V1__:')
        exit 1
    }

    Write-Host ''
    Write-Host '== MIXED_OR_UNVERIFIED =='
    Write-Output (ConvertTo-FramedJsonRecord -InputObject ([ordered]@{
        result = 'MIXED_OR_UNVERIFIED'
        expected_git_sha = $ExpectedGitSha
        baseline_git_sha = $baselineSha
        app_source_sha = $after.app_source_sha
        scheduler_source_sha = $after.scheduler_source_sha
        static_source_sha = $after.static_source_sha
        reason = $Reason
    }) -Prefix '__GO_ODYSSEY_POWERSHELL_RESULT_V1__:')
    exit 2
}

# ======================================================================
# STATIC
# ======================================================================
Write-Phase 'STATIC'

$staticDeploy = Invoke-ReleaseStep -ScriptPath $deployStaticScript `
    -Arguments @('-ExpectedGitSha', $ExpectedGitSha, '-StaticManifest', $staticManifestPath,
                 '-ArchivePath', $staticArchivePath, '-LayoutFile', $LayoutFile,
                 '-Execute', '-OwnerGate', 'GO_DEPLOY') `
    -TimeoutSeconds $DEPLOY_STATIC_TIMEOUT_SECONDS -Label 'deploy-production: deploy static'

# Whether it reported success, failure, or nothing at all, the question is
# the same and is answered by looking at Production once.
$afterStatic = Get-ProductionIdentity -Layout $layout
Write-Identity -Title 'after static step' -Identity $afterStatic
if ([string]$afterStatic.static_source_sha -eq $ExpectedGitSha) {
    $staticPromoted = $true
}

if ((-not $staticDeploy.completed) -or ($staticDeploy.exit_code -ne 0)) {
    if (-not $staticPromoted) {
        # deploy-static-release.ps1 owns its own rollback and has already
        # left the previous generation live. Confirm, then stop.
        if ([string]$afterStatic.static_source_sha -eq $baselineSha) {
            Restore-Baseline -Reason "STATIC failed (exit $($staticDeploy.exit_code)); static was already back at baseline"
        }
    }
    Restore-Baseline -Reason "STATIC failed (exit $($staticDeploy.exit_code))"
}
if (-not $staticPromoted) {
    Restore-Baseline -Reason 'STATIC reported success but the live static generation is not the expected SHA'
}
Write-Step "static promoted to $ExpectedGitSha"

# ======================================================================
# APP
# ======================================================================
Write-Phase 'APP'

$appDeploy = Invoke-ReleaseStep -ScriptPath $deployAppScript `
    -Arguments @('-ExpectedGitSha', $ExpectedGitSha, '-ReleaseManifest', $appManifestPath,
                 '-ReleaseArchive', $appArchivePath, '-ExpectedImageId', $candidateImageId,
                 '-LayoutFile', $LayoutFile, '-Execute', '-OwnerGate', 'GO_DEPLOY') `
    -TimeoutSeconds $DEPLOY_APP_TIMEOUT_SECONDS -Label 'deploy-production: deploy app and scheduler'

$afterApp = Get-ProductionIdentity -Layout $layout
Write-Identity -Title 'after app step' -Identity $afterApp
if (([string]$afterApp.app_source_sha -eq $ExpectedGitSha) -or ([string]$afterApp.scheduler_source_sha -eq $ExpectedGitSha)) {
    $appPromoted = $true
}

if ((-not $appDeploy.completed) -or ($appDeploy.exit_code -ne 0)) {
    Restore-Baseline -Reason "APP failed (exit $($appDeploy.exit_code))"
}
if (-not (Test-IdentityIsUniformly -Identity $afterApp -Sha $ExpectedGitSha)) {
    Restore-Baseline -Reason 'APP reported success but app/scheduler/static are not all at the expected SHA'
}
Write-Step "app and scheduler promoted to $ExpectedGitSha"

# ======================================================================
# VERIFY
# ======================================================================
Write-Phase 'VERIFY'

$final = Get-ProductionIdentity -Layout $layout
Write-Identity -Title 'final identity' -Identity $final
if (-not (Test-IdentityIsUniformly -Identity $final -Sha $ExpectedGitSha)) {
    Restore-Baseline -Reason 'final identity read does not show all three components at the expected SHA'
}

$verify = Invoke-ReleaseStep -ScriptPath $verifyScript `
    -Arguments @('-ReleaseManifest', $appManifestPath, '-LayoutFile', $LayoutFile) `
    -TimeoutSeconds $VERIFY_TIMEOUT_SECONDS -Label 'deploy-production: canonical production verification'
if ((-not $verify.completed) -or ($verify.exit_code -ne 0)) {
    Restore-Baseline -Reason "canonical production verification did not pass (exit $($verify.exit_code))"
}
Write-Step 'canonical production verification PASS'

$publicStatic = Invoke-ReleaseStep -ScriptPath $deployStaticScript `
    -Arguments @('-ExpectedGitSha', $ExpectedGitSha, '-VerifyOnly', '-LayoutFile', $LayoutFile) `
    -TimeoutSeconds $VERIFY_TIMEOUT_SECONDS -Label 'deploy-production: public static acceptance'
if ((-not $publicStatic.completed) -or ($publicStatic.exit_code -ne 0)) {
    Restore-Baseline -Reason "public static acceptance did not pass (exit $($publicStatic.exit_code))"
}
Write-Step 'public static acceptance PASS'

# ======================================================================
# SUCCESS
# ======================================================================
Write-Phase 'SUCCESS'
Write-Step "Production is at $ExpectedGitSha across app, scheduler and static, independently verified."

Write-Output (ConvertTo-FramedJsonRecord -InputObject ([ordered]@{
    result = 'DEPLOYMENT_VERIFIED'
    expected_git_sha = $ExpectedGitSha
    previous_baseline_git_sha = $baselineSha
    app_source_sha = $final.app_source_sha
    scheduler_source_sha = $final.scheduler_source_sha
    static_source_sha = $final.static_source_sha
    static_generation_path = $final.static_generation_path
    candidate_image_id = $candidateImageId
    mutated = $true
}) -Prefix '__GO_ODYSSEY_POWERSHELL_RESULT_V1__:')
exit 0
