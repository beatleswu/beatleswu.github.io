#Requires -Version 5.1
<#
.SYNOPSIS
  RELEASE-FIX-A: package a static release bundle (i18n.js, sw.js per
  deploy/live-static-asset-inventory.json) from an exact release git SHA.

.DESCRIPTION
  Mirrors package-release-image.ps1's pattern: resolves the exact git SHA,
  checks out a detached worktree at that SHA (source of truth is never the
  calling branch's working directory, production's live-static current, or
  a prior release bundle), stages the required_in_generation files, computes
  SHA-256/size for each, parses sw.js's VERSION, and writes a static release
  manifest to release-artifacts/.

  This script never touches the network or any remote host -- see
  deploy-static-release.ps1 for the upload + atomic switch step.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ExpectedGitSha,
    [string]$ManifestPath,
    [string]$BundlePath
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'ReleaseTooling.psm1') -Force -DisableNameChecking

$repoRoot = Get-RepoRoot
$ExpectedGitSha = (Invoke-Git -Arguments @('rev-parse', $ExpectedGitSha) -WorkingDirectory $repoRoot).Trim()
$inventory = Get-StaticAssetInventory
$baseName = Get-ReleaseArtifactBaseName -GitSha $ExpectedGitSha

if (-not $ManifestPath) {
    Ensure-Directory -Path (Join-Path $repoRoot 'release-artifacts')
    $ManifestPath = Join-Path $repoRoot ("release-artifacts\{0}.static.json" -f $baseName)
}
if (-not $BundlePath) {
    $BundlePath = Join-Path $repoRoot ("release-artifacts\{0}.static-bundle" -f $baseName)
}

$worktree = $null
try {
    $worktree = New-DetachedWorktree -GitSha $ExpectedGitSha -Prefix 'go-odyssey-static-release'

    $files = New-StaticReleaseBundle -SourceRoot $worktree -StagePath $BundlePath -Inventory $inventory

    $swFile = $files | Where-Object { $_.path -eq 'sw.js' }
    if (-not $swFile) {
        throw "sw.js is not present in required_in_generation -- cannot determine service_worker_version."
    }
    $swText = Get-Content -Raw -Encoding UTF8 (Join-Path $BundlePath 'sw.js')
    $swVersion = Get-SwVersionFromText -SwText $swText -SourceLabel 'staged sw.js'

    $generationId = Get-StaticReleaseGenerationName -GitSha $ExpectedGitSha -SwVersion $swVersion -TimestampUtc ([DateTime]::UtcNow)
    $manifest = New-StaticReleaseManifestObject `
        -GitSha $ExpectedGitSha `
        -GenerationId $generationId `
        -SwVersion $swVersion `
        -Files $files `
        -CreatedAtUtc ([DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ'))

    Write-JsonFile -InputObject $manifest -Path $ManifestPath

    [ordered]@{
        static_generation_id = $generationId
        release_git_sha = $ExpectedGitSha
        service_worker_version = $swVersion
        bundle_path = $BundlePath
        manifest_path = $ManifestPath
        files = $files
    } | ConvertTo-Json -Depth 8 | Write-Output
}
finally {
    if ($worktree) {
        Remove-DetachedWorktree -Path $worktree
    }
}
