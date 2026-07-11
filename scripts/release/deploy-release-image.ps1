#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ExpectedGitSha,
    [Parameter(Mandatory = $true)][string]$ReleaseManifest,
    [string]$ReleaseArchive,
    [string]$LayoutFile = 'deploy\release-layout.example.json',
    [switch]$Execute,
    [string]$OwnerGate
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'ReleaseTooling.psm1') -Force -DisableNameChecking

$repoRoot = Get-RepoRoot
$layout = Get-ReleaseLayout -Path (Resolve-RepoPath $LayoutFile)
$manifest = Read-JsonFile -Path (Resolve-RepoPath $ReleaseManifest)
$archivePath = if ($ReleaseArchive) { Resolve-RepoPath $ReleaseArchive } else { $null }
$ExpectedGitSha = (Invoke-Git -Arguments @('rev-parse', $ExpectedGitSha) -WorkingDirectory $repoRoot).Trim()

if (-not $Execute) {
    [ordered]@{
        dry_run = $true
        execute_requested = $false
        expected_git_sha = $ExpectedGitSha
        release_archive_exists = $(if ($archivePath) { Test-Path -LiteralPath $archivePath } else { $false })
        release_manifest = $manifest
        compose_project = $layout.compose_project
        target_services = @($layout.app_service_name, $layout.scheduler_service_name)
        required_owner_gate = 'GO_DEPLOY'
        deployment_plan = @(
            'verify checksum',
            'transfer image package',
            'verify remote checksum',
            'load exact image',
            'verify OCI revision',
            'capture rollback identity',
            'start candidate app',
            'verify strong runtime readiness',
            'verify daily challenge and gameplay gates',
            'run browser board smoke',
            'run safe SRS review smoke',
            'switch scheduler',
            'verify scheduler image and database identity',
            'write drift verification report',
            'stop before Production mutation'
        )
    } | ConvertTo-Json -Depth 12 | Write-Output
    return
}

Assert-OwnerGate -Provided $OwnerGate -Expected 'GO_DEPLOY'
if ($manifest.release_git_sha -ne $ExpectedGitSha) {
    throw "Release manifest SHA does not match expected Git SHA."
}
if ($archivePath -and -not (Test-Path -LiteralPath $archivePath)) {
    throw "Release archive not found: $archivePath"
}
throw "Real deployment execution is not enabled in this Sprint. Use dry-run only."
