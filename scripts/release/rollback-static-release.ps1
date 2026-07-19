#Requires -Version 5.1
<#
.SYNOPSIS
  RELEASE-FIX-A: switch /opt/go-odyssey-static/current back to a named
  previous generation directory, verifying public HTTPS-served bytes
  afterward.

.DESCRIPTION
  Reads the remote manifest.json already stored inside the target
  generation directory (written by package-static-release.ps1 /
  deploy-static-release.ps1) as the source of truth for what to verify --
  never assumes what the target generation should contain.

  Restarts app+scheduler after the symlink switch, same as
  deploy-static-release.ps1 -- the containers' bind mount of
  /opt/go-odyssey-static/current resolves the symlink target once, at
  container start, so a rollback that only changes the symlink without
  restarting would be filesystem-real but functionally inert (discovered
  live during this Sprint's own production deploy).
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$TargetGenerationPath,
    [string]$LayoutFile = 'deploy\release-layout.example.json',
    [switch]$Execute,
    [string]$OwnerGate
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'ReleaseTooling.psm1') -Force -DisableNameChecking

$layout = Get-ReleaseLayout -Path (Resolve-RepoPath $LayoutFile)
if (-not $layout.PSObject.Properties.Name -contains 'static_release_root' -or [string]::IsNullOrWhiteSpace($layout.static_release_root)) {
    throw "Release layout is missing static_release_root -- required for static release rollback."
}

function Invoke-RemoteText {
    param([Parameter(Mandatory = $true)][string]$Command)
    $result = Invoke-RemoteShellCommand -SshAlias $layout.ssh_alias -Name 'remote_command' -Command $Command
    if ($result.exit_code -ne 0) {
        throw "Remote command failed: $($result.output)"
    }
    return $result.output
}

function Get-RemoteCurrentTarget {
    param([Parameter(Mandatory = $true)][string]$StaticRoot)
    $command = "readlink -f $(Quote-PosixShellArgument "$StaticRoot/current") 2>/dev/null || true"
    return (Invoke-RemoteText $command).Trim()
}

function Get-SwVersionFromUrl {
    param([Parameter(Mandatory = $true)][string]$Url)
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing
    }
    catch {
        throw "Could not fetch $Url for sw.js VERSION verification: $($_.Exception.Message)"
    }
    return (Get-SwVersionFromText -SwText $response.Content -SourceLabel $Url)
}

function Get-PublicFileSha256 {
    param([Parameter(Mandatory = $true)][string]$Url)
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing
    }
    catch {
        throw "Could not fetch $Url for content verification: $($_.Exception.Message)"
    }
    $bytes = $response.Content
    if ($bytes -is [string]) {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($bytes)
    }
    $hasher = [System.Security.Cryptography.SHA256]::Create()
    try {
        return ([System.BitConverter]::ToString($hasher.ComputeHash($bytes)) -replace '-', '').ToLowerInvariant()
    }
    finally {
        $hasher.Dispose()
    }
}

$existsCheck = Invoke-RemoteText "if [ -d $(Quote-PosixShellArgument $TargetGenerationPath) ]; then echo EXISTS; else echo ABSENT; fi"
if ($existsCheck.Trim() -ne 'EXISTS') {
    throw "Target generation directory does not exist on the remote host: $TargetGenerationPath"
}

$remoteManifestJson = Invoke-RemoteText "cat $(Quote-PosixShellArgument "$TargetGenerationPath/manifest.json")"
$targetManifest = $remoteManifestJson | ConvertFrom-Json

$previousCurrentTarget = Get-RemoteCurrentTarget -StaticRoot $layout.static_release_root
$homepageUri = [Uri]$layout.homepage_url
$publicBase = "$($homepageUri.Scheme)://$($homepageUri.Host)"
$shortSha = Get-ShortGitSha -GitSha $targetManifest.release_git_sha

if (-not $Execute) {
    [ordered]@{
        dry_run = $true
        execute_requested = $false
        target_generation_path = $TargetGenerationPath
        target_manifest = $targetManifest
        current_before_rollback = $previousCurrentTarget
        required_owner_gate = 'GO_ROLLBACK'
    } | ConvertTo-Json -Depth 8 | Write-Output
    return
}

Assert-OwnerGate -Provided $OwnerGate -Expected 'GO_ROLLBACK'

$quotedRoot = Quote-PosixShellArgument $layout.static_release_root
$quotedTarget = Quote-PosixShellArgument $TargetGenerationPath
Invoke-RemoteText "cd $quotedRoot && sudo ln -sfnT $quotedTarget current.next && sudo mv -Tf current.next current" | Out-Null

$newCurrentTarget = Get-RemoteCurrentTarget -StaticRoot $layout.static_release_root
if ($newCurrentTarget -ne $TargetGenerationPath) {
    throw "Remote current does not point to the rollback target. Expected '$TargetGenerationPath', observed '$newCurrentTarget'."
}

Invoke-RemoteText "docker restart $(Quote-PosixShellArgument $layout.app_service_name) $(Quote-PosixShellArgument $layout.scheduler_service_name)" | Out-Null
$deadline = (Get-Date).AddSeconds(60)
$appHealthy = $false
do {
    Start-Sleep -Seconds 2
    $health = (Invoke-RemoteText "docker inspect $(Quote-PosixShellArgument $layout.app_service_name) --format '{{.State.Health.Status}}'").Trim()
    if ($health -eq 'healthy') { $appHealthy = $true }
} while (-not $appHealthy -and (Get-Date) -lt $deadline)
if (-not $appHealthy) {
    throw "App container did not become healthy after restart following the static release rollback."
}

$publicVerification = @()
foreach ($entry in $targetManifest.files) {
    # Canonical URL verification is mandatory.  Query-string variants are
    # diagnostic only and are not part of the rollback acceptance contract.
    $url = "$publicBase/$($entry.path)"
    $observedHash = Get-PublicFileSha256 -Url $url
    if ($observedHash -ne $entry.sha256) {
        throw "Public content hash mismatch after rollback for '$($entry.path)'. Expected '$($entry.sha256)', observed '$observedHash'."
    }
    $publicVerification += [ordered]@{ path = $entry.path; url = $url; sha256_match = $true }
}
    $publicSwVersion = Get-SwVersionFromUrl -Url "$publicBase/sw.js"
if ($publicSwVersion -ne $targetManifest.service_worker_version) {
    throw "Public sw.js VERSION mismatch after rollback. Expected '$($targetManifest.service_worker_version)', observed '$publicSwVersion'."
}

[ordered]@{
    dry_run = $false
    execute_requested = $true
    target_generation_path = $TargetGenerationPath
    previous_current_target = $previousCurrentTarget
    new_current_target = $newCurrentTarget
    public_content_verification = $publicVerification
    public_sw_version_after_rollback = $publicSwVersion
    result = 'STATIC RELEASE ROLLBACK SUCCEEDED'
} | ConvertTo-Json -Depth 8 | Write-Output
