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

function Get-RemoteContainerEnvMap {
    param([Parameter(Mandatory = $true)][string]$ContainerName)
    $raw = Invoke-RemoteText "docker inspect $ContainerName --format '{{json .Config.Env}}'"
    if ([string]::IsNullOrWhiteSpace($raw) -or $raw -eq 'null') {
        return @{}
    }
    $env = $raw | ConvertFrom-Json
    $map = @{}
    foreach ($entry in $env) {
        $pair = $entry -split '=', 2
        if ($pair.Count -ge 1 -and -not [string]::IsNullOrWhiteSpace($pair[0])) {
            $map[$pair[0]] = if ($pair.Count -gt 1) { $pair[1] } else { '' }
        }
    }
    return $map
}

function Get-RemoteContainerMounts {
    param([Parameter(Mandatory = $true)][string]$ContainerName)
    $raw = Invoke-RemoteText "docker inspect $ContainerName --format '{{json .Mounts}}'"
    if ([string]::IsNullOrWhiteSpace($raw) -or $raw -eq 'null') {
        return @()
    }
    return @($raw | ConvertFrom-Json)
}

function Get-DatabaseIdentitySummary {
    param([string]$DatabaseUrl)
    $value = ([string]$DatabaseUrl).Trim()
    if ([string]::IsNullOrWhiteSpace($value)) {
        return [ordered]@{
            configured = $false
            host = ''
            port = $null
            database = ''
            user = ''
            password_present = $false
        }
    }
    $uri = [Uri]$value
    $userInfo = $uri.UserInfo
    $user = ''
    $passwordPresent = $false
    if (-not [string]::IsNullOrWhiteSpace($userInfo)) {
        $parts = $userInfo -split ':', 2
        $user = [Uri]::UnescapeDataString($parts[0])
        $passwordPresent = $parts.Count -gt 1 -and -not [string]::IsNullOrWhiteSpace($parts[1])
    }
    return [ordered]@{
        configured = $true
        host = $uri.Host
        port = $uri.Port
        database = $uri.AbsolutePath.TrimStart('/')
        user = $user
        password_present = $passwordPresent
    }
}

function Get-RemoteReadinessReport {
    param([Parameter(Mandatory = $true)][string]$ContainerName)
    $json = Invoke-RemoteText "docker exec $ContainerName python -X utf8 -c 'import json, app; print(json.dumps(app._read_runtime_deployment_readiness(), ensure_ascii=False))'"
    return ($json | ConvertFrom-Json)
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
        runtime_contract = @(
            'QUESTIONS_JSON_PATH',
            'GO_ODYSSEY_LIVE_STATIC_ROOT',
            'DATABASE_URL',
            'SHADOW_EVENTS_PATH'
        )
    } | ConvertTo-Json -Depth 8 | Write-Output
    return
}

$appEnv = Get-RemoteContainerEnvMap -ContainerName $layout.app_service_name
$schedulerEnv = Get-RemoteContainerEnvMap -ContainerName $layout.scheduler_service_name
$appMounts = Get-RemoteContainerMounts -ContainerName $layout.app_service_name
$schedulerMounts = Get-RemoteContainerMounts -ContainerName $layout.scheduler_service_name
$appDb = Get-DatabaseIdentitySummary -DatabaseUrl $appEnv['DATABASE_URL']
$schedulerDb = Get-DatabaseIdentitySummary -DatabaseUrl $schedulerEnv['DATABASE_URL']
$readiness = Get-RemoteReadinessReport -ContainerName $layout.app_service_name
$expectedQuestionsPath = ($layout.questions_content_mount_destination.TrimEnd('/','\') + '/questions.json')

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
    app_db_identity = $appDb
    scheduler_db_identity = $schedulerDb
    database_identity_match = (
        $appDb.configured -and $schedulerDb.configured -and
        $appDb.host -eq $schedulerDb.host -and
        $appDb.port -eq $schedulerDb.port -and
        $appDb.database -eq $schedulerDb.database -and
        $appDb.user -eq $schedulerDb.user -and
        $appDb.password_present -eq $schedulerDb.password_present
    )
    questions_json_path = $appEnv['QUESTIONS_JSON_PATH']
    questions_json_path_matches_mount = $appEnv['QUESTIONS_JSON_PATH'] -eq $expectedQuestionsPath
    live_static_root = $appEnv['GO_ODYSSEY_LIVE_STATIC_ROOT']
    shadow_events_path = $appEnv['SHADOW_EVENTS_PATH']
    app_mount_count = @($appMounts).Count
    scheduler_mount_count = @($schedulerMounts).Count
    app_health = Get-RemoteHealthStatus $layout.app_service_name
    scheduler_health = Get-RemoteHealthStatus $layout.scheduler_service_name
    nginx_health = Get-RemoteHealthStatus $layout.nginx_service_name
    candidate_release_manifest_exists = $candidateManifestExists
    candidate_release_archive_exists = $candidateArchiveExists
    readiness = $readiness
}

if (-not $report.database_identity_match) {
    throw "App and scheduler database configuration must match."
}
if ([string]::IsNullOrWhiteSpace($report.questions_json_path)) {
    throw "QUESTIONS_JSON_PATH must be configured."
}
if (-not ($report.questions_json_path -eq $expectedQuestionsPath)) {
    throw "QUESTIONS_JSON_PATH must match the configured questions mount destination."
}
if ($readiness.ok -ne $true) {
    throw "Runtime readiness check failed."
}

Write-Output ($report | ConvertTo-Json -Depth 8)
