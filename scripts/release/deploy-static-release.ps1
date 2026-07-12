#Requires -Version 5.1
<#
.SYNOPSIS
  RELEASE-FIX-A: upload a packaged static release bundle to a NEW remote
  generation directory and atomically switch /opt/go-odyssey-static/current
  to point at it, verifying actual public HTTPS-served bytes afterward.

.DESCRIPTION
  Reuses the exact atomic-switch pattern already proven by the untracked,
  host-only /opt/go-odyssey/deploy-static.ps1 (ln -sfnT + mv -Tf into a
  *.next symlink, never a partial write to "current" itself) -- see
  docs/deployment/canonical_static_release_contract.md for why this script
  exists instead of just fixing that one's hard-coded branch guard.

  Never overwrites an existing generation directory. Always verifies the
  PUBLIC, cache-busted HTTPS response (not just the container filesystem or
  the host directory) before declaring success, and automatically rolls
  the symlink back on any post-switch verification failure.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ExpectedGitSha,
    [Parameter(Mandatory = $true)][string]$StaticManifest,
    [Parameter(Mandatory = $true)][string]$BundlePath,
    [string]$LayoutFile = 'deploy\release-layout.example.json',
    [switch]$Execute,
    [string]$OwnerGate
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'ReleaseTooling.psm1') -Force -DisableNameChecking

$repoRoot = Get-RepoRoot
$layout = Get-ReleaseLayout -Path (Resolve-RepoPath $LayoutFile)
if (-not $layout.PSObject.Properties.Name -contains 'static_release_root' -or [string]::IsNullOrWhiteSpace($layout.static_release_root)) {
    throw "Release layout is missing static_release_root -- required for static release deploy."
}
$ExpectedGitSha = (Invoke-Git -Arguments @('rev-parse', $ExpectedGitSha) -WorkingDirectory $repoRoot).Trim()
$manifestPath = Resolve-RepoPath $StaticManifest
$manifest = Read-JsonFile -Path $manifestPath
$bundlePath = Resolve-RepoPath $BundlePath

if ($manifest.release_git_sha -ne $ExpectedGitSha) {
    throw "Static release manifest git SHA ($($manifest.release_git_sha)) does not match expected SHA ($ExpectedGitSha)."
}

# Re-verify the staged bundle against the manifest -- defense against a
# stale or tampered bundle directory reused from an earlier invocation.
foreach ($entry in $manifest.files) {
    $stagedFile = Join-Path $bundlePath $entry.path
    if (-not (Test-Path -LiteralPath $stagedFile -PathType Leaf)) {
        throw "Staged static release file missing: $($entry.path)"
    }
    $actualHash = (Get-FileHash -LiteralPath $stagedFile -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne $entry.sha256) {
        throw "Staged static release file hash mismatch for $($entry.path). Re-run package-static-release.ps1."
    }
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

$generationId = $manifest.static_generation_id
$remoteReleaseDir = "$($layout.static_release_root.TrimEnd('/'))/releases/$generationId"
$homepageUri = [Uri]$layout.homepage_url
$publicBase = "$($homepageUri.Scheme)://$($homepageUri.Host)"
$shortSha = Get-ShortGitSha -GitSha $ExpectedGitSha

if (-not $Execute) {
    [ordered]@{
        dry_run = $true
        execute_requested = $false
        release_git_sha = $ExpectedGitSha
        static_generation_id = $generationId
        service_worker_version = $manifest.service_worker_version
        remote_release_dir = $remoteReleaseDir
        files = $manifest.files
        required_owner_gate = 'GO_DEPLOY'
        plan = @(
            'verify remote release directory does not already exist',
            'create remote release directory',
            'upload each staged file + manifest.json',
            'verify remote sha256 for each uploaded file',
            'record previous current symlink target',
            'atomically switch current -> new release directory (ln -sfnT + mv -Tf)',
            'verify remote current now points to the new release directory',
            'verify PUBLIC cache-busted HTTPS bytes/VERSION match the manifest',
            'roll back automatically if any post-switch verification fails'
        )
    } | ConvertTo-Json -Depth 8 | Write-Output
    return
}

Assert-OwnerGate -Provided $OwnerGate -Expected 'GO_DEPLOY'

$existsCheck = Invoke-RemoteText "if [ -e $(Quote-PosixShellArgument $remoteReleaseDir) ]; then echo EXISTS; else echo ABSENT; fi"
if ($existsCheck.Trim() -eq 'EXISTS') {
    throw "Remote release directory already exists, refusing to overwrite: $remoteReleaseDir"
}

$previousCurrentTarget = Get-RemoteCurrentTarget -StaticRoot $layout.static_release_root
$rollbackPerformed = $false

try {
    Invoke-RemoteText "mkdir -p $(Quote-PosixShellArgument $remoteReleaseDir)" | Out-Null

    foreach ($entry in $manifest.files) {
        $localFile = Join-Path $bundlePath $entry.path
        $remoteFile = "$remoteReleaseDir/$($entry.path)"
        & scp $localFile "$($layout.ssh_alias):$remoteFile" | Out-Host
        if ($LASTEXITCODE -ne 0) {
            throw "scp failed while uploading $($entry.path)."
        }
    }
    & scp $manifestPath "$($layout.ssh_alias):$remoteReleaseDir/manifest.json" | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "scp failed while uploading manifest.json."
    }

    foreach ($entry in $manifest.files) {
        $remoteFile = "$remoteReleaseDir/$($entry.path)"
        $remoteHash = (Invoke-RemoteText "sha256sum $(Quote-PosixShellArgument $remoteFile)").Split(' ')[0].Trim().ToLowerInvariant()
        if ($remoteHash -ne $entry.sha256) {
            throw "Remote hash mismatch for $($entry.path) after upload."
        }
    }

    # Atomic switch: sudo is required because /opt/go-odyssey-static itself
    # (the parent of current/previous) is more tightly permissioned than
    # releases/ -- matching deploy-static.ps1's own proven pattern.
    $quotedRoot = Quote-PosixShellArgument $layout.static_release_root
    $quotedRelease = Quote-PosixShellArgument $remoteReleaseDir
    Invoke-RemoteText "cd $quotedRoot && sudo ln -sfnT $quotedRelease current.next && sudo mv -Tf current.next current" | Out-Null

    $newCurrentTarget = Get-RemoteCurrentTarget -StaticRoot $layout.static_release_root
    if ($newCurrentTarget -ne $remoteReleaseDir) {
        throw "Remote current does not point to the new release after switch. Expected '$remoteReleaseDir', observed '$newCurrentTarget'."
    }

    $publicVerification = @()
    foreach ($entry in $manifest.files) {
        $url = "$publicBase/$($entry.path)?deploy-verify=$shortSha"
        $observedHash = Get-PublicFileSha256 -Url $url
        if ($observedHash -ne $entry.sha256) {
            throw "Public content hash mismatch after switch for '$($entry.path)'. Expected '$($entry.sha256)', observed '$observedHash'."
        }
        $publicVerification += [ordered]@{ path = $entry.path; url = $url; sha256_match = $true }
    }

    $publicSwVersion = Get-SwVersionFromUrl -Url "$publicBase/sw.js?deploy-verify=$shortSha"
    if ($publicSwVersion -ne $manifest.service_worker_version) {
        throw "Public sw.js VERSION mismatch after switch. Expected '$($manifest.service_worker_version)', observed '$publicSwVersion'."
    }

    [ordered]@{
        dry_run = $false
        execute_requested = $true
        release_git_sha = $ExpectedGitSha
        static_generation_id = $generationId
        remote_release_dir = $remoteReleaseDir
        previous_current_target = $previousCurrentTarget
        new_current_target = $newCurrentTarget
        public_content_verification = $publicVerification
        public_sw_version_after_switch = $publicSwVersion
        rollback_command = "cd $($layout.static_release_root) && sudo ln -sfnT '$previousCurrentTarget' current.next && sudo mv -Tf current.next current"
        result = 'STATIC RELEASE SWITCH SUCCEEDED'
    } | ConvertTo-Json -Depth 8 | Write-Output
}
catch {
    $failureMessage = $_.Exception.Message
    $currentNow = Get-RemoteCurrentTarget -StaticRoot $layout.static_release_root
    if ($currentNow -eq $remoteReleaseDir -and $previousCurrentTarget) {
        try {
            $quotedRoot = Quote-PosixShellArgument $layout.static_release_root
            $quotedPrevious = Quote-PosixShellArgument $previousCurrentTarget
            Invoke-RemoteText "cd $quotedRoot && sudo ln -sfnT $quotedPrevious current.next && sudo mv -Tf current.next current" | Out-Null
            $rollbackPerformed = $true
        }
        catch {
            throw "Static release deploy failed: $failureMessage`nAutomatic rollback ALSO failed: $($_.Exception.Message)"
        }
    }
    if ($rollbackPerformed) {
        throw "Static release deploy failed and automatic rollback succeeded (current restored to $previousCurrentTarget): $failureMessage"
    }
    throw
}
