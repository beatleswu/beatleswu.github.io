#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ExpectedGitSha,
    [string]$ImageTag,
    [string]$ArchivePath,
    [string]$ReleaseManifestPath,
    [string]$LayoutFile = 'deploy\release-layout.example.json',
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'ReleaseTooling.psm1') -Force -DisableNameChecking

$repoRoot = Get-RepoRoot
$ExpectedGitSha = (Invoke-Git -Arguments @('rev-parse', $ExpectedGitSha) -WorkingDirectory $repoRoot).Trim()
$layout = Get-ReleaseLayout -Path (Resolve-RepoPath $LayoutFile)
if (-not $ImageTag) {
    $ImageTag = Get-ReleaseImageTag -GitSha $ExpectedGitSha
}

$baseName = Get-ReleaseArtifactBaseName -GitSha $ExpectedGitSha
if (-not $ArchivePath) {
    Ensure-Directory -Path (Join-Path $repoRoot 'release-artifacts')
    $ArchivePath = Join-Path $repoRoot ("release-artifacts\{0}.tar" -f $baseName)
}
if (-not $ReleaseManifestPath) {
    $ReleaseManifestPath = Join-Path (Split-Path -Parent $ArchivePath) ("{0}.release.json" -f $baseName)
}

$labels = Assert-ImageRevisionMatches -ImageTag $ImageTag -ExpectedGitSha $ExpectedGitSha

if ($DryRun) {
    [ordered]@{
        dry_run = $true
        image_tag = $ImageTag
        archive_path = $ArchivePath
        release_manifest_path = $ReleaseManifestPath
        release_layout = $layout
        revision = $labels.'org.opencontainers.image.revision'
    } | ConvertTo-Json -Depth 8 | Write-Output
    return
}

docker save -o $ArchivePath $ImageTag | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "docker save failed with exit code $LASTEXITCODE."
}

$archiveSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $ArchivePath).Hash.ToLowerInvariant()
$imageId = (& docker image inspect $ImageTag --format '{{.Id}}').Trim()
$manifest = New-ReleaseManifestObject `
    -GitSha $ExpectedGitSha `
    -ImageTag $ImageTag `
    -ImageId $imageId `
    -ArchiveFilename ([IO.Path]::GetFileName($ArchivePath)) `
    -ArchiveSha256 $archiveSha `
    -BuildTimestamp ([DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')) `
    -BuildMachineIdentityClass 'local-release-workstation' `
    -TargetServiceNames @($layout.app_service_name, $layout.scheduler_service_name) `
    -ExternalContentRequirements ([ordered]@{
        asset_source_path = $layout.asset_source_path
        asset_container_mount_destination = $layout.asset_container_mount_destination
        questions_content_source_path = $layout.questions_content_source_path
        questions_content_mount_destination = $layout.questions_content_mount_destination
        shadow_event_log_path = $layout.shadow_event_log_path
    }) `
    -ExpectedHealthEndpoints @($layout.health_url, $layout.login_url, $layout.homepage_url) `
    -RollbackImageIdentity ([ordered]@{}) `
    -VerificationResult 'package complete; deployment pending' `
    -DeploymentTimestamp $null `
    -OCIRevision $labels.'org.opencontainers.image.revision'

Write-JsonFile -InputObject $manifest -Path $ReleaseManifestPath
[ordered]@{
    image_tag = $ImageTag
    image_id = $imageId
    archive_path = $ArchivePath
    archive_sha256 = $archiveSha
    release_manifest_path = $ReleaseManifestPath
} | ConvertTo-Json -Depth 8 | Write-Output
