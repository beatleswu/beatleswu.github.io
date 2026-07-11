#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$RollbackManifest,
    [string]$LayoutFile = 'deploy\release-layout.example.json',
    [switch]$Execute,
    [string]$OwnerGate
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'ReleaseTooling.psm1') -Force -DisableNameChecking

$repoRoot = Get-RepoRoot
$layout = Get-ReleaseLayout -Path (Resolve-RepoPath $LayoutFile)
$manifest = Read-JsonFile -Path (Resolve-RepoPath $RollbackManifest)
$rollbackArtifactsRoot = Resolve-RepoPath 'release-artifacts'
Ensure-Directory -Path $rollbackArtifactsRoot

function Invoke-RemoteText {
    param([Parameter(Mandatory = $true)][string]$Command)
    $output = & ssh $layout.ssh_alias $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Remote command failed: $Command"
    }
    return ($output | Out-String).Trim()
}

function Get-RemoteContainerSnapshot {
    param([Parameter(Mandatory = $true)][string]$ContainerName)
    $raw = Invoke-RemoteText "docker inspect $ContainerName --format '{{.Config.Image}}|{{.Image}}|{{.Id}}|{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}n/a{{end}}'"
    $parts = $raw -split '\|', 5
    if ($parts.Count -lt 5) {
        throw "Unable to read remote container snapshot for $ContainerName."
    }
    return [ordered]@{
        image_tag = $parts[0]
        image_id = $parts[1]
        container_id = $parts[2]
        state = $parts[3]
        health = $parts[4]
    }
}

function Get-RemoteImageLabels {
    param([Parameter(Mandatory = $true)][string]$ImageTag)
    $raw = Invoke-RemoteText "docker image inspect $(Quote-PosixShellArgument $ImageTag) --format '{{json .Config.Labels}}'"
    if ([string]::IsNullOrWhiteSpace($raw) -or $raw -eq 'null') {
        return @{}
    }
    return $raw | ConvertFrom-Json
}

function New-RollbackVerificationManifest {
    param(
        [Parameter(Mandatory = $true)][string]$RollbackImageTag,
        [Parameter(Mandatory = $true)][string]$RollbackGitSha,
        [Parameter(Mandatory = $true)][string]$RollbackImageId
    )
    return New-ReleaseManifestObject `
        -GitSha $RollbackGitSha `
        -ImageTag $RollbackImageTag `
        -ImageId $RollbackImageId `
        -ArchiveFilename ("rollback-{0}.tar" -f (Get-ShortGitSha -GitSha $RollbackGitSha)) `
        -ArchiveSha256 ('0' * 64) `
        -BuildTimestamp ([DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')) `
        -BuildMachineIdentityClass 'rollback-verification' `
        -TargetServiceNames @($layout.app_service_name, $layout.scheduler_service_name) `
        -ExternalContentRequirements $manifest.external_content_requirements `
        -ExpectedHealthEndpoints $manifest.expected_health_endpoints `
        -RollbackImageIdentity ([ordered]@{}) `
        -VerificationResult 'rollback verification pending' `
        -DeploymentTimestamp ([DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')) `
        -OCIRevision $RollbackGitSha `
        -OCIImageSource $manifest.oci_source `
        -SGFEngineSourceCommit $manifest.sgf_engine_source_commit
}

$rollbackManifestPath = Join-Path $rollbackArtifactsRoot ("{0}.rollback.json" -f (Get-ReleaseArtifactBaseName -GitSha $manifest.release_git_sha))
$rollbackVerificationManifestPath = Join-Path $rollbackArtifactsRoot ("{0}.rollback-verify.json" -f (Get-ReleaseArtifactBaseName -GitSha $manifest.release_git_sha))

if (-not $Execute) {
    [ordered]@{
        dry_run = $true
        execute_requested = $false
        rollback_manifest = $manifest
        compose_project = $layout.compose_project
        target_services = @($layout.app_service_name, $layout.scheduler_service_name)
        required_owner_gate = 'GO_ROLLBACK'
        rollback_plan = @(
            'validate rollback target',
            'capture current app and scheduler identity',
            'restore app first',
            'verify app health and runtime readiness',
            'restore scheduler',
            'verify both services use the rollback image',
            'restart nginx',
            'run rollback verification',
            'preserve candidate evidence'
        )
    } | ConvertTo-Json -Depth 12 | Write-Output
    return
}

Assert-OwnerGate -Provided $OwnerGate -Expected 'GO_ROLLBACK'

if (-not ($manifest.PSObject.Properties.Name -contains 'rollback_image_identity')) {
    throw "Rollback manifest is missing rollback_image_identity."
}

$rollbackIdentity = $manifest.rollback_image_identity
$rollbackImageTag = $rollbackIdentity.previous_app_image_tag
if ([string]::IsNullOrWhiteSpace($rollbackImageTag)) {
    $rollbackImageTag = $rollbackIdentity.previous_scheduler_image_tag
}
$rollbackGitSha = $rollbackIdentity.previous_app_release_git_sha
if ([string]::IsNullOrWhiteSpace($rollbackGitSha)) {
    $rollbackGitSha = $rollbackIdentity.previous_scheduler_release_git_sha
}
$rollbackImageId = $rollbackIdentity.previous_app_image_id
if ([string]::IsNullOrWhiteSpace($rollbackImageId)) {
    $rollbackImageId = $rollbackIdentity.previous_scheduler_image_id
}

if ([string]::IsNullOrWhiteSpace($rollbackImageTag) -or [string]::IsNullOrWhiteSpace($rollbackGitSha) -or [string]::IsNullOrWhiteSpace($rollbackImageId)) {
    throw "Rollback manifest does not contain an actionable rollback image identity."
}
if ($rollbackIdentity.previous_app_image_tag -and $rollbackIdentity.previous_scheduler_image_tag -and $rollbackIdentity.previous_app_image_tag -ne $rollbackIdentity.previous_scheduler_image_tag) {
    throw "Rollback manifest records mismatched app and scheduler image tags."
}
if ($rollbackIdentity.previous_app_release_git_sha -and $rollbackIdentity.previous_scheduler_release_git_sha -and $rollbackIdentity.previous_app_release_git_sha -ne $rollbackIdentity.previous_scheduler_release_git_sha) {
    throw "Rollback manifest records mismatched app and scheduler release SHAs."
}

$appBefore = Get-RemoteContainerSnapshot -ContainerName $layout.app_service_name
$schedulerBefore = Get-RemoteContainerSnapshot -ContainerName $layout.scheduler_service_name
$appBeforeLabels = Get-RemoteImageLabels -ImageTag $appBefore.image_tag
$schedulerBeforeLabels = Get-RemoteImageLabels -ImageTag $schedulerBefore.image_tag

$rollbackVerificationManifest = New-RollbackVerificationManifest -RollbackImageTag $rollbackImageTag -RollbackGitSha $rollbackGitSha -RollbackImageId $rollbackImageId
Write-JsonFile -InputObject $rollbackVerificationManifest -Path $rollbackVerificationManifestPath

Invoke-RemoteText "cd $(Quote-PosixShellArgument $layout.compose_directory) && GO_ODYSSEY_IMAGE=$(Quote-PosixShellArgument $rollbackImageTag) docker compose -f docker-compose.release.yml up -d --no-build --force-recreate $($layout.app_service_name)"

$appAfter = Get-RemoteContainerSnapshot -ContainerName $layout.app_service_name
if ($appAfter.image_tag -ne $rollbackImageTag) {
    throw "App container did not switch to the rollback image."
}
if ($appAfter.image_id -ne $rollbackImageId) {
    throw "App container image ID does not match the rollback image ID."
}
if ($appAfter.health -ne 'healthy') {
    throw "App container is not healthy after rollback."
}

$appReadiness = Invoke-RemoteText "docker exec $($layout.app_service_name) python -X utf8 -c 'import json, app; print(json.dumps(app._read_runtime_deployment_readiness(), ensure_ascii=False))'"
$appReadinessReport = $appReadiness | ConvertFrom-Json
if ($appReadinessReport.ok -ne $true) {
    throw "App runtime readiness check failed after rollback."
}

Invoke-RemoteText "cd $(Quote-PosixShellArgument $layout.compose_directory) && GO_ODYSSEY_IMAGE=$(Quote-PosixShellArgument $rollbackImageTag) docker compose -f docker-compose.release.yml up -d --no-build --force-recreate $($layout.scheduler_service_name)"

$schedulerAfter = Get-RemoteContainerSnapshot -ContainerName $layout.scheduler_service_name
if ($schedulerAfter.image_tag -ne $rollbackImageTag) {
    throw "Scheduler container did not switch to the rollback image."
}
if ($schedulerAfter.image_id -ne $rollbackImageId) {
    throw "Scheduler container image ID does not match the rollback image ID."
}
if ($appAfter.image_id -ne $schedulerAfter.image_id) {
    throw "App and scheduler image IDs do not match after rollback."
}

Invoke-RemoteText "docker restart $(Quote-PosixShellArgument $layout.nginx_service_name)"

$verificationOutput = & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'verify-production-release.ps1') -ReleaseManifest $rollbackVerificationManifestPath -LayoutFile $LayoutFile
if ($LASTEXITCODE -ne 0) {
    throw "Rollback verification failed with exit code $LASTEXITCODE."
}
$verificationReport = $verificationOutput | ConvertFrom-Json

$rollbackRecord = [ordered]@{
    rollback_manifest = $RollbackManifest
    rollback_image_tag = $rollbackImageTag
    rollback_release_git_sha = $rollbackGitSha
    rollback_image_id = $rollbackImageId
    previous_app = $appBefore
    previous_scheduler = $schedulerBefore
    current_app = $appAfter
    current_scheduler = $schedulerAfter
    app_readiness = $appReadinessReport
    verification = $verificationReport
}
Write-JsonFile -InputObject $rollbackRecord -Path $rollbackManifestPath

[ordered]@{
    dry_run = $false
    execute_requested = $true
    rollback_manifest_path = $RollbackManifest
    rollback_record_path = $rollbackManifestPath
    rollback_verification_manifest_path = $rollbackVerificationManifestPath
    rollback_image_tag = $rollbackImageTag
    rollback_release_git_sha = $rollbackGitSha
    rollback_image_id = $rollbackImageId
    previous_app = $appBefore
    previous_scheduler = $schedulerBefore
    current_app = $appAfter
    current_scheduler = $schedulerAfter
    app_readiness = $appReadinessReport
    verification = $verificationReport
} | ConvertTo-Json -Depth 12 | Write-Output
