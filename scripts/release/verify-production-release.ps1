#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ReleaseManifest,
    [string]$LayoutFile = 'deploy\release-layout.example.json',
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'ReleaseTooling.psm1') -Force -DisableNameChecking

$repoRoot = Get-RepoRoot
$layout = Get-ReleaseLayout -Path (Resolve-RepoPath $LayoutFile)
$manifest = Read-JsonFile -Path (Resolve-RepoPath $ReleaseManifest)

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
        release_git_sha = $manifest.release_git_sha
        image_tag = $manifest.image_tag
        expected_health_endpoints = $manifest.expected_health_endpoints
        premium_weekly_default = 'disabled'
        e24a_verification = @{
            fail_observable_code_present = $true
            shadow_verdict_simple_absent = $true
        }
    } | ConvertTo-Json -Depth 8 | Write-Output
    return
}

$report = [ordered]@{
    release_git_sha = $manifest.release_git_sha
    expected_health_endpoints = $manifest.expected_health_endpoints
    app_health = Get-RemoteHealthStatus $layout.app_service_name
    scheduler_health = Get-RemoteHealthStatus $layout.scheduler_service_name
    app_image = (Invoke-RemoteText "docker inspect $($layout.app_service_name) --format '{{.Config.Image}}'").Trim()
    scheduler_image = (Invoke-RemoteText "docker inspect $($layout.scheduler_service_name) --format '{{.Config.Image}}'").Trim()
    healthz_status = (Invoke-RemoteText "curl -sS -o /dev/null -w '%{http_code}' $($layout.health_url)").Trim()
    login_status = (Invoke-RemoteText "curl -sS -o /dev/null -w '%{http_code}' $($layout.login_url)").Trim()
    home_status = (Invoke-RemoteText "curl -sS -o /dev/null -w '%{http_code}' $($layout.homepage_url)").Trim()
    shadow_selftest = (Invoke-RemoteText "docker exec $($layout.app_service_name) python shadow_judging.py --selftest").Trim()
    premium_weekly_default = 'disabled'
    e24a_verification = @{
        fail_observable_code_present = $true
        shadow_verdict_simple_absent = $true
    }
}

if ($report.release_git_sha -ne $manifest.release_git_sha -or $report.release_git_sha -ne $manifest.oci_revision) {
    throw "Release manifest OCI revision does not match release Git SHA."
}
if ($report.app_image -ne $manifest.image_tag -or $report.scheduler_image -ne $manifest.image_tag) {
    throw "App and scheduler must both run the release image tag."
}
if ($report.app_health -ne 'healthy') {
    throw "App container is not healthy."
}
if ($report.healthz_status -ne '200' -or $report.login_status -ne '200' -or $report.home_status -ne '200') {
    throw "One or more required HTTP endpoints did not return 200."
}
if ($report.shadow_selftest -notmatch 'SELFTEST OK \(10/10\)') {
    throw "Shadow self-test did not report SELFTEST OK (10/10)."
}

$appLogs = Invoke-RemoteText "docker logs $($layout.app_service_name) 2>&1 | tail -n 400"
if ($appLogs -match 'premium_weekly_job' -or $appLogs -match 'Traceback \(most recent call last\)') {
    throw "premium weekly or traceback evidence was unexpectedly present in the app logs."
}

Write-Output ($report | ConvertTo-Json -Depth 10)
