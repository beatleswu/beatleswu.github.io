#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$LayoutFile = 'deploy\release-layout.example.json',
    [string]$ReleaseManifest = 'deploy\release-manifest.example.json',
    [string]$ReleaseArchive,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'ReleaseTooling.psm1') -Force -DisableNameChecking

$repoRoot = Get-RepoRoot
$layout = Get-ReleaseLayout -Path (Resolve-RepoPath $LayoutFile)
$releaseManifestPath = Resolve-RepoPath $ReleaseManifest
$candidateManifestExists = Test-Path -LiteralPath $releaseManifestPath
$candidateArchiveExists = $false
if ($ReleaseArchive) {
    $candidateArchiveExists = Test-Path -LiteralPath (Resolve-RepoPath $ReleaseArchive)
}

function Invoke-RemoteText {
    param([Parameter(Mandatory = $true)][string]$Command)
    $output = & ssh $layout.ssh_alias $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Remote command failed: $Command"
    }
    return ($output | Out-String).Trim()
}

function Get-RemoteHealthStatus {
    param([Parameter(Mandatory = $true)][string]$ContainerName)
    $raw = Invoke-RemoteText "docker inspect $ContainerName --format '{{json .State}}'"
    if ([string]::IsNullOrWhiteSpace($raw) -or $raw -eq 'null') {
        return 'n/a'
    }
    $state = $raw | ConvertFrom-Json
    if ($state.PSObject.Properties.Name -contains 'Health' -and $state.Health) {
        return $state.Health.Status
    }
    return 'n/a'
}

if ($DryRun) {
    [ordered]@{
        dry_run = $true
        ssh_alias = $layout.ssh_alias
        compose_project = $layout.compose_project
        compose_directory = $layout.compose_directory
        app_service_name = $layout.app_service_name
        scheduler_service_name = $layout.scheduler_service_name
        nginx_service_name = $layout.nginx_service_name
        candidate_release_manifest_exists = $candidateManifestExists
        candidate_release_archive_exists = $candidateArchiveExists
        asset_source_path = $layout.asset_source_path
        asset_container_mount_destination = $layout.asset_container_mount_destination
        questions_content_source_path = $layout.questions_content_source_path
        questions_content_mount_destination = $layout.questions_content_mount_destination
        shadow_event_log_path = $layout.shadow_event_log_path
    } | ConvertTo-Json -Depth 8 | Write-Output
    return
}

$report = [ordered]@{
    ssh_alias = $layout.ssh_alias
    docker_version = Invoke-RemoteText 'docker version --format "{{.Server.Version}}"'
    compose_version = Invoke-RemoteText 'docker compose version --short'
    disk_free = Invoke-RemoteText 'df -h --output=avail,target / | tail -n 1'
    current_app = Invoke-RemoteText "docker inspect $($layout.app_service_name) --format '{{.Id}}|{{.Config.Image}}|{{.State.Status}}|{{range .Mounts}}{{.Destination}}={{.Source}}={{.RW}};{{end}}'"
    current_scheduler = Invoke-RemoteText "docker inspect $($layout.scheduler_service_name) --format '{{.Id}}|{{.Config.Image}}|{{.State.Status}}|{{range .Mounts}}{{.Destination}}={{.Source}}={{.RW}};{{end}}'"
    current_nginx = Invoke-RemoteText "docker inspect $($layout.nginx_service_name) --format '{{.Id}}|{{.Config.Image}}|{{.State.Status}}'"
    current_project = $layout.compose_project
    current_compose_directory = $layout.compose_directory
    asset_source = $layout.asset_source_path
    asset_mount_destination = $layout.asset_container_mount_destination
    questions_source = $layout.questions_content_source_path
    questions_mount_destination = $layout.questions_content_mount_destination
    shadow_log_path = $layout.shadow_event_log_path
    app_health = Get-RemoteHealthStatus $layout.app_service_name
    scheduler_health = Get-RemoteHealthStatus $layout.scheduler_service_name
    nginx_health = Get-RemoteHealthStatus $layout.nginx_service_name
    candidate_release_manifest_exists = $candidateManifestExists
    candidate_release_archive_exists = $candidateArchiveExists
}

Write-Output ($report | ConvertTo-Json -Depth 8)
