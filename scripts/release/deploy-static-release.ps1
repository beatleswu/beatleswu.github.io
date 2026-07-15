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

  IMPORTANT, discovered live during this Sprint's own production deploy:
  the app/scheduler containers' bind mount of /opt/go-odyssey-static/current
  resolves the symlink's target ONCE, at container start -- changing what
  the symlink points to on the HOST has zero effect on what the RUNNING
  containers see until they are restarted (confirmed directly: `sha256sum`
  on the host showed the new file immediately after the switch, while
  `docker exec go-odyssey-app sha256sum` on the exact same path still showed
  the OLD file, until `docker restart` was run). This is why this script
  restarts app+scheduler after the symlink switch and before public
  verification -- omitting that step would make the switch filesystem-real
  but functionally inert, exactly reproducing the original drift this
  Sprint exists to fix, just one layer deeper.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ExpectedGitSha,
    [Parameter(Mandatory = $true)][string]$StaticManifest,
    [Parameter(Mandatory = $true)][string]$BundlePath,
    [Parameter(Mandatory = $true)][string]$ArchivePath,
    [string]$LayoutFile = 'deploy\release-layout.example.json',
    [switch]$Execute,
    [string]$OwnerGate,
    [string]$GnuTarPath
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
$archivePath = Resolve-RepoPath $ArchivePath

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

# RELEASE-FIX-A3-STATIC-DEPLOY-FIX3: this script consumes the ALREADY-BUILT
# deterministic archive package-static-release.ps1 produced -- it never
# calls New-DeterministicStaticArchive and never rebuilds an archive. The
# archive a Release Review verified is the exact archive bytes uploaded
# here, verified by SHA-256/size/entry-count against what the manifest
# recorded at packaging time, not re-derived from whatever GNU tar (or
# bsdtar) happens to be resolvable on this deploy workstation's PATH today.
if (-not (Test-Path -LiteralPath $archivePath -PathType Leaf)) {
    throw "Static release archive not found: $archivePath. Run package-static-release.ps1 first; this script never builds an archive itself."
}
if ([string]::IsNullOrWhiteSpace($manifest.archive_sha256) -or [string]::IsNullOrWhiteSpace($manifest.archive_filename)) {
    throw "Static release manifest does not record archive identity (archive_filename/archive_sha256) -- it was built before RELEASE-FIX-A3-STATIC-DEPLOY-FIX3 or is otherwise incompatible. Re-run package-static-release.ps1."
}
$actualArchiveHash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualArchiveHash -ne $manifest.archive_sha256) {
    throw "Local archive SHA-256 ($actualArchiveHash) does not match the manifest's recorded archive_sha256 ($($manifest.archive_sha256)) -- refusing to upload a mismatched archive. Re-run package-static-release.ps1."
}
$actualArchiveSize = (Get-Item -LiteralPath $archivePath).Length
if ($manifest.archive_size -and $actualArchiveSize -ne $manifest.archive_size) {
    throw "Local archive byte size ($actualArchiveSize) does not match the manifest's recorded archive_size ($($manifest.archive_size))."
}

$gnuTar = Resolve-GnuTarExecutable -OverridePath $GnuTarPath
Test-StaticArchiveEntrySafety -ArchivePath $archivePath -GnuTarExecutablePath $gnuTar.path

$RemoteCommandTimeoutSeconds = 30
$RemoteRestartTimeoutSeconds = 45
$RemoteHealthPollTimeoutSeconds = 20
$RemoteDirectoryBatchTimeoutSeconds = 30
$ScpUploadTimeoutSeconds = 90
$PublicVerificationConcurrency = 8
$PublicVerificationRequestTimeoutSeconds = 15
$PublicVerificationDeadlineSeconds = 240
$phaseClock = [System.Diagnostics.Stopwatch]::StartNew()

function Write-StaticDeployTiming {
    param([Parameter(Mandatory = $true)][string]$Phase)
    if ($env:GO_ODYSSEY_STATIC_DEPLOY_TIMING -eq '1') {
        [Console]::Error.WriteLine(('[static-deploy +{0:n3}s] {1}' -f $phaseClock.Elapsed.TotalSeconds, $Phase))
    }
}

function Invoke-BoundedPublicVerification {
    param(
        [Parameter(Mandatory = $true)][object[]]$Entries,
        [Parameter(Mandatory = $true)][string]$PublicBase,
        [Parameter(Mandatory = $true)][string]$ShortSha,
        [int]$Concurrency = $PublicVerificationConcurrency,
        [int]$RequestTimeoutSeconds = $PublicVerificationRequestTimeoutSeconds,
        [int]$DeadlineSeconds = $PublicVerificationDeadlineSeconds
    )

    $worker = {
        param($Url, $ExpectedHash, $Path, $TimeoutSeconds)
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec $TimeoutSeconds
            $bytes = $response.Content
            if ($bytes -is [string]) {
                $bytes = [System.Text.Encoding]::UTF8.GetBytes($bytes)
            }
            $hasher = [System.Security.Cryptography.SHA256]::Create()
            try {
                $observedHash = (([System.BitConverter]::ToString($hasher.ComputeHash($bytes))) -replace '-', '').ToLowerInvariant()
            }
            finally {
                $hasher.Dispose()
            }
            if ($observedHash -ne $ExpectedHash) {
                return [pscustomobject]@{ path = $Path; status = 'sha_mismatch'; expected = $ExpectedHash; observed = $observedHash; error = "Public content hash mismatch" }
            }
            return [pscustomobject]@{ path = $Path; status = 'passed'; expected = $ExpectedHash; observed = $observedHash }
        }
        catch {
            return [pscustomobject]@{ path = $Path; status = 'http_failed'; error = $_.Exception.Message }
        }
    }

    $results = New-Object System.Collections.Generic.List[object]
    $deadline = [DateTime]::UtcNow.AddSeconds($DeadlineSeconds)
    $nextProgress = 100
    for ($offset = 0; $offset -lt $Entries.Count; $offset += $Concurrency) {
        $remaining = [int][Math]::Floor(($deadline - [DateTime]::UtcNow).TotalSeconds)
        if ($remaining -le 0) {
            foreach ($entry in $Entries[$offset..($Entries.Count - 1)]) {
                $results.Add([pscustomobject]@{ path = $entry.path; status = 'cancelled_deadline' })
            }
            break
        }
        $last = [Math]::Min($offset + $Concurrency - 1, $Entries.Count - 1)
        $jobs = @()
        $jobEntries = @{}
        try {
            foreach ($entry in $Entries[$offset..$last]) {
                $url = "$PublicBase/$($entry.path)?deploy-verify=$ShortSha"
                $job = Start-Job -ScriptBlock $worker -ArgumentList $url, $entry.sha256, $entry.path, $RequestTimeoutSeconds
                $jobs += $job
                $jobEntries[$job.Id] = $entry
            }
            $waitSeconds = [Math]::Min($remaining, $RequestTimeoutSeconds + 5)
            $completed = @(Wait-Job -Job $jobs -Timeout $waitSeconds)
            foreach ($job in $completed) {
                $received = @(Receive-Job -Job $job -ErrorAction SilentlyContinue)
                if ($received.Count -gt 0) { $results.Add($received[0]) }
                else { $results.Add([pscustomobject]@{ path = "job:$($job.Id)"; status = 'worker_exception' }) }
            }
            $completedIds = @($completed | ForEach-Object { $_.Id })
            foreach ($job in @($jobs | Where-Object { $_.Id -notin $completedIds })) {
                $entry = $jobEntries[$job.Id]
                $results.Add([pscustomobject]@{ path = $entry.path; status = if (([DateTime]::UtcNow -ge $deadline)) { 'cancelled_deadline' } else { 'timeout' }; expected = $entry.sha256 })
            }
        }
        finally {
            foreach ($job in $jobs) {
                if ($job.State -in @('Running', 'NotStarted')) { Stop-Job -Job $job -ErrorAction SilentlyContinue }
                Remove-Job -Job $job -Force -ErrorAction SilentlyContinue
            }
        }
        if ($results.Count -ge $nextProgress) {
            Write-StaticDeployTiming "PUBLIC HASH PROGRESS $($results.Count)/$($Entries.Count)"
            while ($nextProgress -le $results.Count) { $nextProgress += 100 }
        }
    }
    return @($results)
}

function Invoke-RemoteText {
    <#
    .SYNOPSIS
    Bounded remote command execution -- RELEASE-FIX-A2-STATIC-DEPLOY-FIX1.
    A hung ssh process is killed after $TimeoutSeconds instead of blocking
    the deploy indefinitely (confirmed live: a single stuck `mkdir -p`
    ssh invocation hung for ~15 minutes with no bound at all previously).
    #>
    param(
        [Parameter(Mandatory = $true)][string]$Command,
        [int]$TimeoutSeconds = $RemoteCommandTimeoutSeconds,
        [string]$OperationLabel = 'remote command'
    )
    $result = Invoke-BoundedSshCommand -SshAlias $layout.ssh_alias -Command $Command -TimeoutSeconds $TimeoutSeconds -OperationLabel $OperationLabel
    if ($result.exit_code -ne 0) {
        throw "Remote command failed ($OperationLabel): $($result.output)"
    }
    return $result.output
}

function Invoke-RemoteDirectoryBatch {
    <#
    .SYNOPSIS
    Creates every required remote directory (generation root + every
    nested governed-subtree parent directory) in ONE bounded ssh session,
    not one ssh invocation per directory.
    #>
    param(
        [Parameter(Mandatory = $true)][string[]]$Directories,
        [int]$TimeoutSeconds = $RemoteDirectoryBatchTimeoutSeconds
    )
    $script = New-RemoteMkdirScriptText -Directories $Directories
    $result = Invoke-BoundedSshCommand -SshAlias $layout.ssh_alias -ScriptText $script -TimeoutSeconds $TimeoutSeconds -OperationLabel "batched remote mkdir ($($Directories.Count) directories)"
    if ($result.exit_code -ne 0) {
        throw "Remote directory batch creation failed: $($result.output)"
    }
}

function Invoke-BoundedFileUpload {
    param(
        [Parameter(Mandatory = $true)][string]$LocalPath,
        [Parameter(Mandatory = $true)][string]$RemotePath,
        [int]$TimeoutSeconds = $ScpUploadTimeoutSeconds
    )
    $result = Invoke-BoundedScpUpload -LocalPath $LocalPath -SshAlias $layout.ssh_alias -RemotePath $RemotePath -TimeoutSeconds $TimeoutSeconds -OperationLabel "scp upload: $RemotePath"
    if ($result.exit_code -ne 0) {
        throw "scp failed while uploading to $RemotePath`: $($result.output)"
    }
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
Write-StaticDeployTiming "START generation=$generationId entries=$($manifest.files.Count)"

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
            'verify remote sha256 for all uploaded files in one batched remote operation',
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
    # Step 2+3: create the generation root and every nested governed-subtree
    # parent directory in ONE bounded ssh session (RELEASE-FIX-A2-STATIC-
    # DEPLOY-FIX1) -- not one ssh mkdir invocation per unique directory,
    # which is what hung in production during the first attempt.
    $relativePaths = @($manifest.files | ForEach-Object { $_.path })
    $requiredDirectories = Get-RemoteParentDirectorySet -RelativePaths $relativePaths -RemoteReleaseDir $remoteReleaseDir
    Invoke-RemoteDirectoryBatch -Directories $requiredDirectories
    Write-StaticDeployTiming 'REMOTE DIRECTORIES COMPLETE'

    # Step 4: upload the ALREADY-BUILT deterministic archive (RELEASE-FIX-A3
    # / RELEASE-FIX-A3-STATIC-DEPLOY-FIX3), not one scp per file and not a
    # freshly-rebuilt archive -- this is the exact same archive bytes a
    # Release Review verified (SHA-256-checked above, before any remote
    # call), uploaded as-is: exactly 2 bounded remote operations (upload,
    # extract) for a hundreds-of-files, hundreds-of-MB canonical image pack.
    $expectedBytes = ($manifest.files | Measure-Object -Property size -Sum).Sum
    $archiveTimeoutSeconds = Get-ArchiveTransferTimeoutSeconds -TotalBytes $expectedBytes
    $remoteArchivePath = "$($layout.static_release_root.TrimEnd('/'))/releases/.upload-$generationId.tar"
    Invoke-BoundedFileUpload -LocalPath $archivePath -RemotePath $remoteArchivePath -TimeoutSeconds $archiveTimeoutSeconds
    Write-StaticDeployTiming 'ARCHIVE UPLOAD COMPLETE'
    $extractResult = Invoke-RemoteText "tar -xf $(Quote-PosixShellArgument $remoteArchivePath) -C $(Quote-PosixShellArgument $remoteReleaseDir) && rm -f $(Quote-PosixShellArgument $remoteArchivePath)" -TimeoutSeconds $archiveTimeoutSeconds -OperationLabel 'extract static release archive'
    Write-StaticDeployTiming 'ARCHIVE EXTRACT COMPLETE'

    # Step 5: validate uploaded file count before trusting anything else.
    $uploadedCount = [int](Invoke-RemoteText "find $(Quote-PosixShellArgument $remoteReleaseDir) -type f | wc -l" -OperationLabel 'count uploaded files').Trim()
    if ($uploadedCount -ne $manifest.files.Count) {
        throw "Uploaded file count mismatch: expected $($manifest.files.Count), remote has $uploadedCount (manifest.json not yet uploaded, so these must match exactly)."
    }

    # Step 6: validate uploaded total byte size.
    $uploadedBytes = [long](Invoke-RemoteText "find $(Quote-PosixShellArgument $remoteReleaseDir) -type f -exec stat -c%s {} \; | awk '{s+=`$1} END{print s+0}'" -OperationLabel 'sum uploaded bytes').Trim()
    if ($uploadedBytes -ne $expectedBytes) {
        throw "Uploaded byte size mismatch: expected $expectedBytes, remote has $uploadedBytes."
    }

    # Step 7: validate every uploaded file's SHA-256 in ONE batched remote
    # operation (RELEASE-FIX-A2-STATIC-DEPLOY-FIX2) -- not one ssh session
    # per file. Confirmed live in production: with 182 separate sessions,
    # one otherwise-instant verification exceeded a 30s bound while 181
    # others succeeded; a single batched check of the same 182 files
    # measured 1.13s wall-clock during this Sprint's own diagnostic.
    $batchTimeoutSeconds = Get-BatchVerificationTimeoutSeconds -TotalBytes $expectedBytes
    $verificationScript = New-RemoteBatchShaVerificationScript -RemoteReleaseDir $remoteReleaseDir -Files $manifest.files
    $verificationResult = Invoke-BoundedSshCommand -SshAlias $layout.ssh_alias -ScriptText $verificationScript -TimeoutSeconds $batchTimeoutSeconds -OperationLabel "batch SHA-256 verification ($($manifest.files.Count) files)"
    if ($verificationResult.exit_code -ne 0) {
        $failedLines = ($verificationResult.output -split "`n" | Where-Object { $_ -match 'FAILED' }) -join '; '
        throw "Batch SHA-256 verification failed (exit $($verificationResult.exit_code)): $failedLines"
    }
    Write-StaticDeployTiming 'REMOTE GOVERNED SHA COMPLETE'

    # Step 8: manifest.json uploads LAST, only after every governed file has
    # passed count/size/hash verification -- a partial or corrupted
    # generation never gets a manifest, so it can never be mistaken for a
    # complete, deployable release (see rollback-static-release.ps1 and
    # preflight-production.ps1, which both treat manifest.json as the sole
    # source of truth for "this generation is real").
    Invoke-BoundedFileUpload -LocalPath $manifestPath -RemotePath "$remoteReleaseDir/manifest.json"

    # Step 9: re-read and validate the now-complete remote generation.
    $finalCount = [int](Invoke-RemoteText "find $(Quote-PosixShellArgument $remoteReleaseDir) -type f | wc -l" -OperationLabel 'final count including manifest').Trim()
    if ($finalCount -ne ($manifest.files.Count + 1)) {
        throw "Final remote file count mismatch after manifest upload: expected $($manifest.files.Count + 1), observed $finalCount."
    }
    $remoteManifestHash = (Invoke-RemoteText "sha256sum $(Quote-PosixShellArgument "$remoteReleaseDir/manifest.json")" -OperationLabel 'sha256sum: manifest.json').Split(' ')[0].Trim().ToLowerInvariant()
    $localManifestHash = (Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($remoteManifestHash -ne $localManifestHash) {
        throw "Remote manifest.json hash does not match the local manifest after upload."
    }
    Write-StaticDeployTiming 'MANIFEST UPLOAD/VALIDATION COMPLETE'

    # Step 10: atomic switch. sudo is required because /opt/go-odyssey-static itself
    # (the parent of current/previous) is more tightly permissioned than
    # releases/ -- matching deploy-static.ps1's own proven pattern.
    $quotedRoot = Quote-PosixShellArgument $layout.static_release_root
    $quotedRelease = Quote-PosixShellArgument $remoteReleaseDir
    Invoke-RemoteText "cd $quotedRoot && sudo ln -sfnT $quotedRelease current.next && sudo mv -Tf current.next current" -OperationLabel 'atomic symlink switch' | Out-Null

    $newCurrentTarget = Get-RemoteCurrentTarget -StaticRoot $layout.static_release_root
    if ($newCurrentTarget -ne $remoteReleaseDir) {
        throw "Remote current does not point to the new release after switch. Expected '$remoteReleaseDir', observed '$newCurrentTarget'."
    }
    Write-StaticDeployTiming 'SYMLINK SWITCH COMPLETE'

    # Step 11: restart app+scheduler. The bind-mounted containers resolved
    # the OLD symlink target at their own start time -- restart them so
    # their mount namespace re-resolves against the new "current" target.
    # See the module docstring above for how this was discovered.
    Invoke-RemoteText "docker restart $(Quote-PosixShellArgument $layout.app_service_name) $(Quote-PosixShellArgument $layout.scheduler_service_name)" -TimeoutSeconds $RemoteRestartTimeoutSeconds -OperationLabel 'docker restart app+scheduler' | Out-Null
    $deadline = (Get-Date).AddSeconds(60)
    $appHealthy = $false
    do {
        Start-Sleep -Seconds 2
        $health = (Invoke-RemoteText "docker inspect $(Quote-PosixShellArgument $layout.app_service_name) --format '{{.State.Health.Status}}'" -TimeoutSeconds $RemoteHealthPollTimeoutSeconds -OperationLabel 'poll app health').Trim()
        if ($health -eq 'healthy') { $appHealthy = $true }
    } while (-not $appHealthy -and (Get-Date) -lt $deadline)
    if (-not $appHealthy) {
        throw "App container did not become healthy after restart following the static release switch."
    }
    Write-StaticDeployTiming 'CONTAINER RESTART/HEALTH COMPLETE'
    # Step 12 (part 1 of 2): container-internal verification, before the
    # public HTTPS check below.
    $containerServedHash = (Invoke-RemoteText "docker exec $(Quote-PosixShellArgument $layout.app_service_name) sha256sum $(Quote-PosixShellArgument "$($layout.asset_container_mount_destination)/i18n.js")" -OperationLabel 'container-internal i18n.js hash').Split(' ')[0].Trim().ToLowerInvariant()
    $expectedI18nHash = ($manifest.files | Where-Object { $_.path -eq 'i18n.js' }).sha256
    if ($containerServedHash -ne $expectedI18nHash) {
        throw "Container-internal i18n.js hash still does not match the new release after restart. Expected '$expectedI18nHash', observed '$containerServedHash'."
    }

    Write-StaticDeployTiming 'PUBLIC HASH VERIFICATION START'
    $publicResults = Invoke-BoundedPublicVerification -Entries $manifest.files -PublicBase $publicBase -ShortSha $shortSha
    $publicVerification = @($publicResults | Where-Object { $_.status -eq 'passed' } | ForEach-Object { [ordered]@{ path = $_.path; url = "$publicBase/$($_.path)?deploy-verify=$shortSha"; sha256_match = $true } })
    $publicFailures = @($publicResults | Where-Object { $_.status -ne 'passed' })
    if ($publicFailures.Count -gt 0 -or $publicResults.Count -ne $manifest.files.Count) {
        $failureDetails = ($publicFailures | ConvertTo-Json -Compress -Depth 6)
        throw "Public content verification failed: total=$($manifest.files.Count), completed=$($publicResults.Count), passed=$($publicVerification.Count), failures=$($publicFailures.Count). Details: $failureDetails"
    }
    Write-StaticDeployTiming 'PUBLIC HASH VERIFICATION COMPLETE'

    $publicSwVersion = Get-SwVersionFromUrl -Url "$publicBase/sw.js?deploy-verify=$shortSha"
    if ($publicSwVersion -ne $manifest.service_worker_version) {
        throw "Public sw.js VERSION mismatch after switch. Expected '$($manifest.service_worker_version)', observed '$publicSwVersion'."
    }
    Write-StaticDeployTiming 'PUBLIC SW VERSION COMPLETE'

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
            Invoke-RemoteText "cd $quotedRoot && sudo ln -sfnT $quotedPrevious current.next && sudo mv -Tf current.next current" -OperationLabel 'rollback: symlink switch' | Out-Null
            # The containers may already have been restarted onto the failed
            # release's mount target (see the restart step above) -- restart
            # again so they actually pick up the reverted symlink too, or the
            # rollback would be filesystem-real but functionally inert, same
            # as the original bug.
            Invoke-RemoteText "docker restart $(Quote-PosixShellArgument $layout.app_service_name) $(Quote-PosixShellArgument $layout.scheduler_service_name)" -TimeoutSeconds $RemoteRestartTimeoutSeconds -OperationLabel 'rollback: docker restart' | Out-Null
            $rollbackPerformed = $true
        }
        catch {
            throw "Static release deploy failed: $failureMessage`nAutomatic rollback ALSO failed: $($_.Exception.Message)"
        }
    }
    if ($rollbackPerformed) {
        throw "Static release deploy failed and automatic rollback succeeded (current restored to $previousCurrentTarget, containers restarted): $failureMessage"
    }
    throw
}
