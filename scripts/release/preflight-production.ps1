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
    docker_version = (& ssh $layout.ssh_alias 'docker version --format "{{.Server.Version}}"').Trim()
    compose_version = (& ssh $layout.ssh_alias 'docker compose version --short').Trim()
    disk_free = (& ssh $layout.ssh_alias 'df -h --output=avail,target / | tail -n 1').Trim()
    current_app = (& ssh $layout.ssh_alias "docker inspect $($layout.app_service_name) --format '{{.Id}}|{{.Config.Image}}|{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}n/a{{end}}|{{range .Mounts}}{{.Destination}}={{.Source}}={{.RW}};{{end}}'").Trim()
    current_scheduler = (& ssh $layout.ssh_alias "docker inspect $($layout.scheduler_service_name) --format '{{.Id}}|{{.Config.Image}}|{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}n/a{{end}}|{{range .Mounts}}{{.Destination}}={{.Source}}={{.RW}};{{end}}'").Trim()
    current_nginx = (& ssh $layout.ssh_alias "docker inspect $($layout.nginx_service_name) --format '{{.Id}}|{{.Config.Image}}|{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}n/a{{end}}'").Trim()
    current_project = $layout.compose_project
    current_compose_directory = $layout.compose_directory
    asset_source = $layout.asset_source_path
    asset_mount_destination = $layout.asset_container_mount_destination
    questions_source = $layout.questions_content_source_path
    questions_mount_destination = $layout.questions_content_mount_destination
    shadow_log_path = $layout.shadow_event_log_path
    candidate_release_manifest_exists = $candidateManifestExists
    candidate_release_archive_exists = $candidateArchiveExists
}

Write-Output ($report | ConvertTo-Json -Depth 8)
