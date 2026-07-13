#Requires -Version 5.1
<#
.SYNOPSIS
  RELEASE-FIX-A: package a static release bundle (i18n.js, sw.js, and every
  RELEASE-FIX-A3-governed assets/** file per deploy/live-static-asset-
  inventory.json) from an exact release git SHA.

.DESCRIPTION
  Mirrors package-release-image.ps1's pattern: resolves the exact git SHA,
  checks out a detached worktree at that SHA (source of truth is never the
  calling branch's working directory, production's live-static current, or
  a prior release bundle), stages the required_in_generation files, computes
  SHA-256/size for each, parses sw.js's VERSION, and writes a static release
  manifest to release-artifacts/.

  RELEASE-FIX-A3-STATIC-DEPLOY-FIX3: this script now ALSO builds the final,
  immutable deterministic archive (New-DeterministicStaticArchive) and
  records its identity (filename, SHA-256, byte size, entry count, and the
  exact GNU tar executable + version used to build it) in the static
  manifest. This is now the ONLY place a static release archive is ever
  built -- deploy-static-release.ps1 consumes this exact archive as an
  explicit input and never rebuilds it, so the archive a Release Review
  verifies is provably the same bytes that get uploaded to production,
  regardless of the deploy workstation's PATH or installed tar
  implementation at deploy time.

  This script never touches the network or any remote host -- see
  deploy-static-release.ps1 for the upload + atomic switch step.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ExpectedGitSha,
    [string]$ManifestPath,
    [string]$BundlePath,
    [string]$ArchivePath,
    [string]$GnuTarPath
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
if (-not $ArchivePath) {
    Ensure-Directory -Path (Join-Path $repoRoot 'release-artifacts')
    $ArchivePath = Join-Path $repoRoot ("release-artifacts\{0}.static.tar" -f $baseName)
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

    # RELEASE-FIX-A3-STATIC-DEPLOY-FIX3: resolve a verified GNU tar (never a
    # bare `tar` name, never a silent bsdtar fallback) and build the ONE
    # final deterministic archive here, at packaging time -- this is the
    # exact artifact a Release Review verifies and deploy later consumes.
    $gnuTar = Resolve-GnuTarExecutable -OverridePath $GnuTarPath
    $relativePaths = @($files | ForEach-Object { $_.path })
    # $files entries are ordered hashtables (from New-StaticReleaseBundle),
    # not JSON-deserialized PSCustomObjects -- Measure-Object -Property
    # does not bind to hashtable keys, so extract the values explicitly.
    $expectedBytes = (@($files) | ForEach-Object { $_.size } | Measure-Object -Sum).Sum
    $archiveTimeoutSeconds = Get-ArchiveTransferTimeoutSeconds -TotalBytes $expectedBytes

    # Immediately re-verify every staged file's hash right before archiving
    # -- fail closed if the on-disk bytes have changed since
    # New-StaticReleaseBundle's own copy-time verification. Confirmed live
    # on this workstation: a staged file can silently diverge from its
    # verified bytes between being copied/verified and being archived
    # (observed twice, a different random file each time, sizes unchanged,
    # both still valid images of the declared type -- consistent with a
    # host-level disk/AV write race, not a logic defect) with no exception
    # raised anywhere in the pipeline. Re-hashing immediately before the
    # archive read closes that window as tightly as this script can.
    $staleFiles = @()
    foreach ($entry in $files) {
        $stagedFile = Join-Path $BundlePath $entry.path
        $reverifyHash = (Get-FileHash -LiteralPath $stagedFile -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($reverifyHash -ne $entry.sha256) {
            $staleFiles += "$($entry.path) (verified $($entry.sha256), now $reverifyHash)"
        }
    }
    if ($staleFiles.Count -gt 0) {
        throw "Staged file(s) changed on disk between copy-time verification and archiving -- refusing to build an archive from unverified bytes: $($staleFiles -join '; ')"
    }

    New-DeterministicStaticArchive -BundlePath $BundlePath -RelativePaths $relativePaths -ArchivePath $ArchivePath -GnuTarExecutablePath $gnuTar.path -TimeoutSeconds $archiveTimeoutSeconds | Out-Null

    # Prove the archive is safe and record its real, freshly-computed
    # identity -- never trust the build call's own success alone.
    Test-StaticArchiveEntrySafety -ArchivePath $ArchivePath -GnuTarExecutablePath $gnuTar.path -TimeoutSeconds $archiveTimeoutSeconds
    # --force-local: Git for Windows' GNU tar otherwise misreads a Windows
    # "D:\..." archive path as a "host:path" remote-tar spec.
    $listResult = Invoke-BoundedNativeCommand -FileName $gnuTar.path -ArgumentList @('--force-local', '-tf', $ArchivePath) -TimeoutSeconds $archiveTimeoutSeconds -OperationLabel 'count static archive entries'
    if ($listResult.exit_code -ne 0) {
        throw "Failed to enumerate the built archive's entries: $($listResult.output)"
    }
    $archiveEntryCount = @($listResult.output -split "`n" | Where-Object { $_.Trim() }).Count
    if ($archiveEntryCount -ne $relativePaths.Count) {
        throw "Archive entry count ($archiveEntryCount) does not match the staged file count ($($relativePaths.Count)) -- refusing to publish a manifest for a mismatched archive."
    }

    # Extract the just-built archive and re-verify every file's hash against
    # what was staged -- the strongest available proof that the BYTES THAT
    # ACTUALLY SHIPPED are correct, not merely that the staging directory
    # looked correct at some earlier point. This closes the same
    # disk-corruption-race window as the pre-archive re-check above, but
    # against the archive's own contents rather than the staging directory.
    $verifyExtractPath = Join-Path ([System.IO.Path]::GetTempPath()) ("archive-verify-" + [System.Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $verifyExtractPath -Force | Out-Null
    try {
        # GNU tar's -C target directory (unlike its -f archive path, which
        # --force-local already covers) still mis-parses a Windows
        # backslash-style absolute path ("C:\Users\...") -- confirmed live:
        # "Cannot open: No such file or directory" even with --force-local
        # and the directory already created. Forward slashes avoid the
        # ambiguity entirely and Windows accepts them equally.
        $extractResult = Invoke-BoundedNativeCommand -FileName $gnuTar.path -ArgumentList @('--force-local', '-xf', $ArchivePath, '-C', ($verifyExtractPath -replace '\\', '/')) -TimeoutSeconds $archiveTimeoutSeconds -OperationLabel 'extract archive for post-build verification'
        if ($extractResult.exit_code -ne 0) {
            throw "Failed to extract the built archive for verification: $($extractResult.output)"
        }
        $archiveContentMismatches = @()
        foreach ($entry in $files) {
            $extractedFile = Join-Path $verifyExtractPath $entry.path
            if (-not (Test-Path -LiteralPath $extractedFile -PathType Leaf)) {
                $archiveContentMismatches += "$($entry.path) (missing from extracted archive)"
                continue
            }
            $extractedHash = (Get-FileHash -LiteralPath $extractedFile -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($extractedHash -ne $entry.sha256) {
                $archiveContentMismatches += "$($entry.path) (expected $($entry.sha256), archive has $extractedHash)"
            }
        }
        if ($archiveContentMismatches.Count -gt 0) {
            throw "Built archive contains incorrect bytes for $($archiveContentMismatches.Count) file(s) -- refusing to publish a manifest for a corrupted archive: $($archiveContentMismatches -join '; ')"
        }
    }
    finally {
        Remove-Item -LiteralPath $verifyExtractPath -Recurse -Force -ErrorAction SilentlyContinue
    }

    $archiveHash = (Get-FileHash -LiteralPath $ArchivePath -Algorithm SHA256).Hash.ToLowerInvariant()
    $archiveSize = (Get-Item -LiteralPath $ArchivePath).Length

    $manifest = New-StaticReleaseManifestObject `
        -GitSha $ExpectedGitSha `
        -GenerationId $generationId `
        -SwVersion $swVersion `
        -Files $files `
        -CreatedAtUtc ([DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')) `
        -ArchiveFileName (Split-Path -Leaf $ArchivePath) `
        -ArchiveSha256 $archiveHash `
        -ArchiveSize $archiveSize `
        -ArchiveEntryCount $archiveEntryCount `
        -GnuTarExecutablePath $gnuTar.path `
        -GnuTarVersion $gnuTar.version_output

    Write-JsonFile -InputObject $manifest -Path $ManifestPath

    [ordered]@{
        static_generation_id = $generationId
        release_git_sha = $ExpectedGitSha
        service_worker_version = $swVersion
        bundle_path = $BundlePath
        manifest_path = $ManifestPath
        archive_path = $ArchivePath
        archive_sha256 = $archiveHash
        archive_size = $archiveSize
        archive_entry_count = $archiveEntryCount
        gnu_tar_executable_path = $gnuTar.path
        gnu_tar_version = $gnuTar.version_output
        files = $files
    } | ConvertTo-Json -Depth 8 | Write-Output
}
finally {
    if ($worktree) {
        Remove-DetachedWorktree -Path $worktree
    }
}
