#Requires -Version 5.1
<#
.SYNOPSIS
  RELEASE-FIX-A: switch /opt/go-odyssey-static/current back to a named
  previous generation directory, verifying public HTTPS-served bytes
  afterward.

.DESCRIPTION
  Reads the remote release-manifest.json already stored inside the target
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
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [int]$TimeoutSeconds = (Get-StaticPublicVerificationRequestTimeoutSeconds)
    )
    $response = $null
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -MaximumRedirection 0 -TimeoutSec $TimeoutSeconds
    }
    catch {
        $failure = Get-PublicVerificationFailureRecord -Exception $_.Exception -Path $Url -VerificationMode 'SERVICE_WORKER_VERSION' -Response $response
        throw "Could not fetch $Url for sw.js VERSION verification [$($failure.status)]: $($failure.error)"
    }
    try {
        return (Get-SwVersionFromText -SwText $response.Content -SourceLabel $Url)
    }
    catch {
        throw "Could not parse sw.js VERSION from $Url [malformed_response]: $($_.Exception.Message)"
    }
}

function Get-PublicStaticReleaseProvenance {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [int]$TimeoutSeconds = (Get-StaticPublicVerificationRequestTimeoutSeconds)
    )
    $response = $null
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -MaximumRedirection 0 -TimeoutSec $TimeoutSeconds -Headers @{ 'Cache-Control' = 'no-cache'; 'Pragma' = 'no-cache' }
        if ([int]$response.StatusCode -ne 200) { throw "HTTP status $([int]$response.StatusCode)" }
        return ($response.Content | ConvertFrom-Json)
    }
    catch {
        $failure = Get-PublicVerificationFailureRecord -Exception $_.Exception -Path $Url -VerificationMode 'STATIC_RELEASE_PROVENANCE' -Response $response
        throw "Could not fetch static release provenance from $Url [$($failure.status)]: $($failure.error)"
    }
}

$existsCheck = Invoke-RemoteText "if [ -d $(Quote-PosixShellArgument $TargetGenerationPath) ]; then echo EXISTS; else echo ABSENT; fi"
if ($existsCheck.Trim() -ne 'EXISTS') {
    throw "Target generation directory does not exist on the remote host: $TargetGenerationPath"
}

$remoteManifestJson = Invoke-RemoteText "cat $(Quote-PosixShellArgument "$TargetGenerationPath/release-manifest.json")"
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

$targetInventoryEntry = @($targetManifest.files | Where-Object { $_.path -eq 'inventory.html' })
if ($targetInventoryEntry.Count -eq 1) {
    $targetInventoryHash = (Invoke-RemoteText "sha256sum $(Quote-PosixShellArgument "$TargetGenerationPath/inventory.html")").Split(' ')[0].Trim().ToLowerInvariant()
    if ($targetInventoryHash -ne $targetInventoryEntry[0].sha256) {
        throw "Target generation inventory.html hash does not match its manifest. Expected '$($targetInventoryEntry[0].sha256)', observed '$targetInventoryHash'."
    }
    $mountedInventoryHash = (Invoke-RemoteText "docker exec $(Quote-PosixShellArgument $layout.app_service_name) sha256sum $(Quote-PosixShellArgument "$($layout.asset_container_mount_destination)/inventory.html")").Split(' ')[0].Trim().ToLowerInvariant()
    if ($mountedInventoryHash -ne $targetInventoryEntry[0].sha256) {
        throw "Mounted inventory.html hash does not match the rollback target manifest. Expected '$($targetInventoryEntry[0].sha256)', observed '$mountedInventoryHash'."
    }
}

# This is the complete targetManifest.files set (the former equivalent was
# `foreach ($entry in $targetManifest.files)`), with only the dynamic index
# shell excluded because it is verified through static-release provenance.
$rollbackPublicEntries = @($targetManifest.files | Where-Object { $_.path -ne 'index.html' })
$rollbackPublicVerificationConcurrency = 8
$rollbackPublicVerificationRequestTimeoutSeconds = Get-StaticPublicVerificationRequestTimeoutSeconds
$rollbackPublicVerificationAttempts = 1
$rollbackPublicVerificationDeadlineSeconds = Get-StaticPublicVerificationDeadlineSeconds -FileCount $rollbackPublicEntries.Count -Concurrency $rollbackPublicVerificationConcurrency -RequestTimeoutSeconds $rollbackPublicVerificationRequestTimeoutSeconds -AttemptCount $rollbackPublicVerificationAttempts
$rollbackPublicResults = @(Invoke-BoundedPublicStaticVerification -Entries $rollbackPublicEntries -PublicBase $publicBase -Concurrency $rollbackPublicVerificationConcurrency -RequestTimeoutSeconds $rollbackPublicVerificationRequestTimeoutSeconds -DeadlineSeconds $rollbackPublicVerificationDeadlineSeconds -AttemptCount $rollbackPublicVerificationAttempts)
$rollbackPublicFailures = @($rollbackPublicResults | Where-Object { $_.status -ne 'passed' })
if ($rollbackPublicFailures.Count -gt 0 -or $rollbackPublicResults.Count -ne $rollbackPublicEntries.Count) {
    $failureDetails = @($rollbackPublicFailures | Select-Object -First 10 | ForEach-Object {
        [ordered]@{
            path = $_.path
            status = $_.status
            http_status = $_.http_status
            web_exception_status = $_.web_exception_status
            error = $_.error
        }
    }) | ConvertTo-Json -Compress -Depth 6
    throw "Public content verification failed after rollback: total=$($rollbackPublicEntries.Count), completed=$($rollbackPublicResults.Count), failures=$($rollbackPublicFailures.Count), deadline_seconds=$rollbackPublicVerificationDeadlineSeconds. Details: $failureDetails"
}
$publicVerification = @($rollbackPublicResults | ForEach-Object {
    $plan = Get-StaticPublicVerificationPlan -RelativePath ([string]$_.path)
    if ($plan.verification_mode -eq 'AUTHENTICATED_ROUTE') {
        [ordered]@{
            path = $_.path
            url = "$publicBase$($plan.route)"
            verification_mode = 'AUTHENTICATED_ROUTE'
            authenticated_route_verified = $true
            login_body_hashed = $false
        }
    }
    else {
        [ordered]@{
            path = $_.path
            url = "$publicBase$($plan.route)"
            verification_mode = 'RAW_PUBLIC_BYTES'
            sha256_match = $true
        }
    }
})
$publicSwVersion = Get-SwVersionFromUrl -Url "$publicBase/sw.js"
if ($publicSwVersion -ne $targetManifest.service_worker_version) {
    throw "Public sw.js VERSION mismatch after rollback. Expected '$($targetManifest.service_worker_version)', observed '$publicSwVersion'."
}
$provenance = Get-PublicStaticReleaseProvenance -Url "$publicBase/healthz/static-release"
$expectedIndexSha = ($targetManifest.files | Where-Object { $_.path -eq 'index.html' }).sha256
$expectedGeneration = $TargetGenerationPath.Split('/')[-1]
if (-not $provenance.ok -or $provenance.generation -ne $expectedGeneration -or $provenance.index_sha256 -ne $expectedIndexSha) {
    throw "Public static provenance mismatch after rollback. Expected generation '$expectedGeneration' and index SHA '$expectedIndexSha'."
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
