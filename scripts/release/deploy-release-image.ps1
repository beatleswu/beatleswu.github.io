#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ExpectedGitSha,
    [Parameter(Mandatory = $true)][string]$ReleaseManifest,
    [string]$ReleaseArchive,
    [string]$ExpectedImageId,
    [string]$ExpectedArchiveSha256,
    [string]$ExpectedPlatform = 'linux/arm64',
    [string]$LayoutFile = 'deploy\release-layout.example.json',
    [switch]$Execute,
    [string]$OwnerGate
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'ReleaseTooling.psm1') -Force -DisableNameChecking

$repoRoot = Get-RepoRoot
$layout = Get-ReleaseLayout -Path (Resolve-RepoPath $LayoutFile)
$manifestPath = Resolve-RepoPath $ReleaseManifest
$manifest = Read-JsonFile -Path $manifestPath
$ExpectedGitSha = (Invoke-Git -Arguments @('rev-parse', $ExpectedGitSha) -WorkingDirectory $repoRoot).Trim()
$expectedImageTag = Get-ReleaseImageTag -GitSha $ExpectedGitSha
$ExpectedImageId = if ($ExpectedImageId) { $ExpectedImageId.Trim() } else { $manifest.image_id }
$ExpectedArchiveSha256 = if ($ExpectedArchiveSha256) { $ExpectedArchiveSha256.Trim().ToLowerInvariant() } else { $manifest.archive_sha256 }
$ExpectedPlatform = if ($ExpectedPlatform) { $ExpectedPlatform.Trim().ToLowerInvariant() } else { 'linux/arm64' }
$archivePath = if ($ReleaseArchive) {
    Resolve-RepoPath $ReleaseArchive
} elseif ($manifest.PSObject.Properties.Name -contains 'image_archive_filename') {
    Join-Path (Split-Path -Parent $manifestPath) $manifest.image_archive_filename
} else {
    $null
}
$composeFilePath = Resolve-RepoPath 'docker-compose.release.yml'
$nginxConfigPath = Resolve-RepoPath 'nginx\default.conf'
$artifactBaseName = Get-ReleaseArtifactBaseName -GitSha $ExpectedGitSha
$deploymentRecordPath = Join-Path (Split-Path -Parent $manifestPath) ("{0}.deployment.json" -f $artifactBaseName)

function Invoke-RemoteText {
    param([Parameter(Mandatory = $true)][string]$Command)
    $output = & ssh $layout.ssh_alias $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Remote command failed: $Command"
    }
    return ($output | Out-String).Trim()
}

function Join-RemotePath {
    param(
        [Parameter(Mandatory = $true)][string]$Left,
        [Parameter(Mandatory = $true)][string]$Right
    )
    return ($Left.TrimEnd('/') + '/' + $Right.TrimStart('/'))
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

function Get-RemoteImageSummary {
    param([Parameter(Mandatory = $true)][string]$ImageTag)
    $labels = Get-RemoteImageLabels -ImageTag $ImageTag
    return [ordered]@{
        image_id = (Invoke-RemoteText "docker image inspect $(Quote-PosixShellArgument $ImageTag) --format '{{.Id}}'")
        platform = (Invoke-RemoteText "docker image inspect $(Quote-PosixShellArgument $ImageTag) --format '{{.Os}}/{{.Architecture}}'")
        revision = $labels.'org.opencontainers.image.revision'
        source = $labels.'org.opencontainers.image.source'
        sgf_engine_source_commit = $labels.'com.godokoro.sgf-engine.source-commit'
    }
}

function Get-LocalImageSummary {
    param([Parameter(Mandatory = $true)][string]$ImageTag)
    $labelsRaw = & docker image inspect $ImageTag --format "{{json .Config.Labels}}"
    if ($LASTEXITCODE -ne 0) {
        throw "Local image inspect failed for $ImageTag."
    }
    $labels = if ([string]::IsNullOrWhiteSpace($labelsRaw) -or $labelsRaw -eq 'null') { @{} } else { $labelsRaw | ConvertFrom-Json }
    return [ordered]@{
        image_id = (& docker image inspect $ImageTag --format "{{.Id}}").Trim()
        platform = (& docker image inspect $ImageTag --format "{{.Os}}/{{.Architecture}}").Trim().ToLowerInvariant()
        revision = $labels.'org.opencontainers.image.revision'
        source = $labels.'org.opencontainers.image.source'
        sgf_engine_source_commit = $labels.'com.godokoro.sgf-engine.source-commit'
    }
}

function New-DeploymentRecord {
    param(
        [Parameter(Mandatory = $true)]$RollbackIdentity,
        [Parameter(Mandatory = $true)][string]$VerificationResult
    )
    return New-ReleaseManifestObject `
        -GitSha $manifest.release_git_sha `
        -ImageTag $manifest.image_tag `
        -ImageId $manifest.image_id `
        -ArchiveFilename $manifest.image_archive_filename `
        -ArchiveSha256 $manifest.archive_sha256 `
        -BuildTimestamp $manifest.build_timestamp `
        -BuildMachineIdentityClass $manifest.build_machine_identity_class `
        -TargetServiceNames $manifest.target_service_names `
        -ExternalContentRequirements $manifest.external_content_requirements `
        -ExpectedHealthEndpoints $manifest.expected_health_endpoints `
        -RollbackImageIdentity $RollbackIdentity `
        -VerificationResult $VerificationResult `
        -DeploymentTimestamp ([DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')) `
        -OCIRevision $manifest.oci_revision `
        -OCIImageSource $manifest.oci_source `
        -SGFEngineSourceCommit $manifest.sgf_engine_source_commit
}

function Save-DeploymentRecord {
    param(
        [Parameter(Mandatory = $true)]$Record,
        [Parameter(Mandatory = $true)][string]$Path
    )
    Write-JsonFile -InputObject $Record -Path $Path
}

$localArchiveSha = $null
if ($archivePath -and (Test-Path -LiteralPath $archivePath)) {
    $localArchiveSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $archivePath).Hash.ToLowerInvariant()
}
$localArchiveSize = if ($archivePath -and (Test-Path -LiteralPath $archivePath)) {
    (Get-Item -LiteralPath $archivePath).Length
} else {
    0
}
$localImageSummary = Get-LocalImageSummary -ImageTag $manifest.image_tag

if (-not $Execute) {
    [ordered]@{
        dry_run = $true
        execute_requested = $false
        expected_git_sha = $ExpectedGitSha
        expected_image_tag = $expectedImageTag
        expected_image_id = $ExpectedImageId
        expected_archive_sha256 = $ExpectedArchiveSha256
        expected_platform = $ExpectedPlatform
        release_archive_exists = $(if ($archivePath) { Test-Path -LiteralPath $archivePath } else { $false })
        release_archive_size_bytes = $localArchiveSize
        release_archive_sha256 = $localArchiveSha
        local_image_summary = $localImageSummary
        release_manifest = $manifest
        compose_project = $layout.compose_project
        target_services = @($layout.app_service_name, $layout.scheduler_service_name)
        required_owner_gate = 'GO_DEPLOY'
        deployment_plan = @(
            'verify manifest and archive checksum',
            'stage compose file and nginx config on the production host',
            'transfer image archive and deployment record',
            'verify remote archive checksum',
            'verify compose resolves exact release image',
            'load the exact image into the remote Docker engine',
            'capture rollback identity from currently running services',
            'switch app to the release image',
            'verify app health and runtime readiness',
            'switch scheduler to the release image',
            'restart nginx to refresh upstream resolution',
            'run production verification',
            'write sanitized deployment record'
        )
    } | ConvertTo-Json -Depth 12 | Write-Output
    return
}

Assert-OwnerGate -Provided $OwnerGate -Expected 'GO_DEPLOY'
if ($manifest.release_git_sha -ne $ExpectedGitSha) {
    throw "Release manifest SHA does not match expected Git SHA."
}
if ($manifest.oci_revision -ne $ExpectedGitSha) {
    throw "Release manifest OCI revision does not match expected Git SHA."
}
if ($manifest.image_id -ne $ExpectedImageId) {
    throw "Release manifest image ID does not match expected image ID."
}
if ($manifest.archive_sha256 -ne $ExpectedArchiveSha256) {
    throw "Release manifest archive checksum does not match expected archive checksum."
}
if ($ExpectedPlatform -ne 'linux/arm64') {
    throw "Expected platform must be linux/arm64."
}
if ($manifest.image_tag -ne $expectedImageTag) {
    throw "Release manifest image tag does not match expected Git SHA."
}
if (-not $archivePath -or -not (Test-Path -LiteralPath $archivePath)) {
    throw "Release archive not found: $archivePath"
}
if ($localArchiveSize -le 0) {
    throw "Release archive is empty."
}
if ([string]::IsNullOrWhiteSpace($localArchiveSha) -or $localArchiveSha -ne $manifest.archive_sha256) {
    throw "Release archive checksum does not match the manifest."
}
if ($localImageSummary.image_id -ne $ExpectedImageId) {
    throw "Local image ID does not match the expected release image ID."
}
if ($localImageSummary.platform -ne $ExpectedPlatform) {
    throw "Local image platform does not match expected platform."
}
if ($localImageSummary.revision -ne $ExpectedGitSha) {
    throw "Local image revision does not match expected Git SHA."
}
if ($localImageSummary.source -ne $manifest.oci_source) {
    throw "Local image source does not match the release manifest."
}
if ($localImageSummary.sgf_engine_source_commit -ne $manifest.sgf_engine_source_commit) {
    throw "Local image SGF Engine source commit does not match the release manifest."
}

$remoteArchivePath = Join-RemotePath $layout.remote_release_staging_directory ([IO.Path]::GetFileName($archivePath))
$remoteManifestPath = Join-RemotePath $layout.remote_release_staging_directory ([IO.Path]::GetFileName($manifestPath))
$remoteComposePath = Join-RemotePath $layout.compose_directory 'docker-compose.release.yml'
$remoteNginxPath = Join-RemotePath (Join-RemotePath $layout.compose_directory 'nginx') 'default.conf'
$remoteDeploymentRecordPath = Join-RemotePath $layout.remote_release_staging_directory ([IO.Path]::GetFileName($deploymentRecordPath))

Invoke-RemoteText "mkdir -p $(Quote-PosixShellArgument $layout.remote_release_staging_directory) $(Quote-PosixShellArgument $layout.compose_directory) $(Quote-PosixShellArgument (Join-RemotePath $layout.compose_directory 'nginx'))"

& scp $composeFilePath "$($layout.ssh_alias):$remoteComposePath" | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "scp failed while transferring docker-compose.release.yml."
}
& scp $nginxConfigPath "$($layout.ssh_alias):$remoteNginxPath" | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "scp failed while transferring nginx/default.conf."
}
& scp $manifestPath "$($layout.ssh_alias):$remoteManifestPath" | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "scp failed while transferring the release manifest."
}
& scp $archivePath "$($layout.ssh_alias):$remoteArchivePath" | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "scp failed while transferring the release archive."
}

$remoteArchiveSha = (Invoke-RemoteText "sha256sum $(Quote-PosixShellArgument $remoteArchivePath)").Split(' ')[0].Trim().ToLowerInvariant()
if ($remoteArchiveSha -ne $manifest.archive_sha256) {
    throw "Remote archive checksum does not match the manifest."
}

$composeServices = Invoke-RemoteText "cd $(Quote-PosixShellArgument $layout.compose_directory) && GO_ODYSSEY_IMAGE=$(Quote-PosixShellArgument $manifest.image_tag) docker compose -f docker-compose.release.yml config --services"
foreach ($serviceName in @($layout.app_service_name, $layout.scheduler_service_name, $layout.nginx_service_name)) {
    if ($composeServices -notmatch "(?m)^$([Regex]::Escape($serviceName))$") {
        throw "docker compose config did not expose expected service: $serviceName"
    }
}

$composeImages = Invoke-RemoteText "cd $(Quote-PosixShellArgument $layout.compose_directory) && GO_ODYSSEY_IMAGE=$(Quote-PosixShellArgument $manifest.image_tag) docker compose -f docker-compose.release.yml config --images"
$composeImageMatches = ([regex]::Split($composeImages, '\r?\n') | Where-Object { $_.Trim() -eq $manifest.image_tag }).Count
if ($composeImageMatches -lt 2) {
    throw "docker compose config did not resolve the exact release image for app and scheduler."
}

Invoke-RemoteText "docker load -i $(Quote-PosixShellArgument $remoteArchivePath)"

$remoteImageSummary = Get-RemoteImageSummary -ImageTag $manifest.image_tag
if ($remoteImageSummary.image_id -ne $manifest.image_id) {
    throw "Remote image ID does not match the release manifest."
}
if ($remoteImageSummary.revision -ne $ExpectedGitSha) {
    throw "Remote image revision does not match the release manifest."
}
if ($remoteImageSummary.source -ne $manifest.oci_source) {
    throw "Remote image source does not match the release manifest."
}
if ($remoteImageSummary.sgf_engine_source_commit -ne $manifest.sgf_engine_source_commit) {
    throw "Remote image SGF Engine source commit does not match the release manifest."
}
if ($remoteImageSummary.platform -ne 'linux/arm64') {
    throw "Remote image platform does not match linux/arm64."
}

$appBefore = Get-RemoteContainerSnapshot -ContainerName $layout.app_service_name
$schedulerBefore = Get-RemoteContainerSnapshot -ContainerName $layout.scheduler_service_name
$appBeforeLabels = Get-RemoteImageLabels -ImageTag $appBefore.image_tag
$schedulerBeforeLabels = Get-RemoteImageLabels -ImageTag $schedulerBefore.image_tag
$rollbackIdentity = [ordered]@{
    previous_app_image_tag = $appBefore.image_tag
    previous_app_image_id = $appBefore.image_id
    previous_app_container_id = $appBefore.container_id
    previous_app_release_git_sha = $appBeforeLabels.'org.opencontainers.image.revision'
    previous_scheduler_image_tag = $schedulerBefore.image_tag
    previous_scheduler_image_id = $schedulerBefore.image_id
    previous_scheduler_container_id = $schedulerBefore.container_id
    previous_scheduler_release_git_sha = $schedulerBeforeLabels.'org.opencontainers.image.revision'
    previous_health_state = $appBefore.health
    current_compose_project = $layout.compose_project
    current_compose_directory = $layout.compose_directory
}
$deploymentRecord = New-DeploymentRecord -RollbackIdentity $rollbackIdentity -VerificationResult 'deployment in progress'
Save-DeploymentRecord -Record $deploymentRecord -Path $deploymentRecordPath
& scp $deploymentRecordPath "$($layout.ssh_alias):$remoteDeploymentRecordPath" | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "scp failed while transferring the deployment record."
}

Invoke-RemoteText "cd $(Quote-PosixShellArgument $layout.compose_directory) && GO_ODYSSEY_IMAGE=$(Quote-PosixShellArgument $manifest.image_tag) docker compose -f docker-compose.release.yml up -d --no-build --force-recreate $($layout.app_service_name)"

$appAfter = Get-RemoteContainerSnapshot -ContainerName $layout.app_service_name
if ($appAfter.image_tag -ne $manifest.image_tag) {
    throw "App container is not running the release image."
}
if ($appAfter.image_id -ne $ExpectedImageId) {
    throw "App container image ID does not match the release image ID."
}
if ($appAfter.health -ne 'healthy') {
    throw "App container is not healthy after the image switch."
}

$appReadiness = Invoke-RemoteText "docker exec $($layout.app_service_name) python -X utf8 -c 'import json, app; print(json.dumps(app._read_runtime_deployment_readiness(), ensure_ascii=False))'"
$appReadinessReport = $appReadiness | ConvertFrom-Json
if ($appReadinessReport.ok -ne $true) {
    throw "App runtime readiness check failed after the image switch."
}

Invoke-RemoteText "cd $(Quote-PosixShellArgument $layout.compose_directory) && GO_ODYSSEY_IMAGE=$(Quote-PosixShellArgument $manifest.image_tag) docker compose -f docker-compose.release.yml up -d --no-build --force-recreate $($layout.scheduler_service_name)"

$schedulerAfter = Get-RemoteContainerSnapshot -ContainerName $layout.scheduler_service_name
if ($schedulerAfter.image_tag -ne $manifest.image_tag) {
    throw "Scheduler container is not running the release image."
}
if ($schedulerAfter.image_id -ne $ExpectedImageId) {
    throw "Scheduler container image ID does not match the release image ID."
}
if ($appAfter.image_id -ne $schedulerAfter.image_id) {
    throw "App and scheduler image IDs do not match after rollout."
}

Invoke-RemoteText "docker restart $(Quote-PosixShellArgument $layout.nginx_service_name)"

$verificationOutput = & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'verify-production-release.ps1') -ReleaseManifest $deploymentRecordPath -LayoutFile $LayoutFile
if ($LASTEXITCODE -ne 0) {
    throw "verify-production-release.ps1 failed with exit code $LASTEXITCODE."
}
$verificationReport = $verificationOutput | ConvertFrom-Json

if ($deploymentRecord.Contains('verification_result')) {
    $deploymentRecord['verification_result'] = 'production verified'
}
Save-DeploymentRecord -Record $deploymentRecord -Path $deploymentRecordPath
& scp $deploymentRecordPath "$($layout.ssh_alias):$remoteDeploymentRecordPath" | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "scp failed while updating the remote deployment record."
}

[ordered]@{
    dry_run = $false
    execute_requested = $true
    expected_git_sha = $ExpectedGitSha
    expected_image_tag = $manifest.image_tag
    expected_image_id = $ExpectedImageId
    expected_archive_sha256 = $ExpectedArchiveSha256
    expected_platform = $ExpectedPlatform
    release_archive_path = $archivePath
    release_archive_size_bytes = $localArchiveSize
    release_archive_sha256 = $localArchiveSha
    remote_release_archive_path = $remoteArchivePath
    remote_release_archive_sha256 = $remoteArchiveSha
    release_manifest_path = $manifestPath
    deployment_record_path = $deploymentRecordPath
    local_image_summary = $localImageSummary
    rollback_image_identity = $rollbackIdentity
    remote_image_id = $remoteImageSummary.image_id
    remote_image_platform = $remoteImageSummary.platform
    app_before = $appBefore
    scheduler_before = $schedulerBefore
    app_after = $appAfter
    scheduler_after = $schedulerAfter
    app_readiness = $appReadinessReport
    verification = $verificationReport
} | ConvertTo-Json -Depth 12 | Write-Output
