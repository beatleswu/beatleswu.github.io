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
            'restore app first',
            'verify app health',
            'verify runtime readiness',
            'verify gameplay gates',
            'restore scheduler',
            'verify both services use the rollback image',
            'preserve PostgreSQL and candidate evidence'
        )
    } | ConvertTo-Json -Depth 12 | Write-Output
    return
}

Assert-OwnerGate -Provided $OwnerGate -Expected 'GO_ROLLBACK'
throw "Real rollback execution is not enabled in this Sprint. Use dry-run only."
