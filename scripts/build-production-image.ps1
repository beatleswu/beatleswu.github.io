#Requires -Version 5.1
<#
.SYNOPSIS
  Canonical build-only tooling for the go-odyssey-app production image.

.DESCRIPTION
  Builds an immutable, Git-SHA-tagged candidate image from a clean checkout
  of this repository. This script BUILDS ONLY. It never deploys, never SSHes
  anywhere, never restarts a container, and never reads or prints secrets.

  It fails fast, with a clear message, if required tracked build inputs are
  missing (see deploy/build-manifest.json for the current list of inputs
  not yet vendored into the canonical branch).

.PARAMETER GitSha
  The commit to build. Defaults to the current HEAD. The script verifies
  this commit is based on canonical origin/master before building.

.PARAMETER SkipCleanCheck
  Allow a non-clean working tree (for local iteration only). Never use this
  for a build whose image tag will be trusted as reproducible.

.PARAMETER Platform
  RELEASE-TOOLING-HOTFIX-02: the target image platform. Defaults to the
  production contract, linux/arm64 (production runs on real aarch64
  hardware -- confirmed directly against the live host, not assumed from
  docs). Changing this
  requires explicitly passing -Platform; there is no silent fallback to the
  local build machine's native platform. Uses `docker buildx build
  --platform <Platform> --load`, never plain `docker build` (which always
  targets the local daemon's native platform with no way to cross-build
  arm64 from an amd64 host, which is exactly how a wrong-architecture image
  was silently produced before this fix). The resulting image's actual
  platform is inspected immediately after build and the script fails if it
  does not match -- this is not something later gates (e.g.
  deploy-release-image.ps1's -ExpectedPlatform check) may be relied on to
  catch alone. See docs/deployment/release_tooling_hotfix_02_arm64_build_contract.md.

.EXAMPLE
  pwsh ./scripts/build-production-image.ps1
#>
[CmdletBinding()]
param(
    [string]$GitSha,
    [switch]$SkipCleanCheck,
    [string]$Platform = 'linux/arm64',
    [Parameter(Mandatory = $true)][string]$ExpectedCanonicalWorktreeRoot,
    [Parameter(Mandatory = $true)][string]$ExpectedExactGitSha,
    [Parameter(Mandatory = $true)][string]$ExpectedGitCommonDirectory,
    [Parameter(Mandatory = $true)][ValidateSet('detached')][string]$ExpectedHeadState
)

$ErrorActionPreference = 'Stop'
$Platform = $Platform.Trim().ToLowerInvariant()

# Bootstrap without importing repository code first. This rejects a redirected
# root or script path before loading ReleaseTooling.psm1. It intentionally uses
# lexical normalization plus per-component ReparsePoint inspection; resolving
# through a junction and approving its target would defeat this boundary.
function Fail-Bootstrap($msg) {
    Write-Host "BUILD FAILED: $msg" -ForegroundColor Red
    exit 1
}

function Get-BootstrapCanonicalPath([string]$Path, [string]$Label) {
    if ([string]::IsNullOrWhiteSpace($Path) -or -not [System.IO.Path]::IsPathRooted($Path)) {
        Fail-Bootstrap "$Label must be a nonblank absolute filesystem path."
    }
    try { $fullPath = [System.IO.Path]::GetFullPath($Path) }
    catch { Fail-Bootstrap "$Label is not a valid absolute filesystem path." }
    $root = [System.IO.Path]::GetPathRoot($fullPath)
    if ([string]::Equals($fullPath, $root, [System.StringComparison]::OrdinalIgnoreCase)) { return $root }
    return $fullPath.TrimEnd('\', '/')
}

function Assert-BootstrapNoReparse([string]$Path, [string]$Label) {
    $canonical = Get-BootstrapCanonicalPath $Path $Label
    $root = [System.IO.Path]::GetPathRoot($canonical)
    $current = $root
    $components = $canonical.Substring($root.Length) -split '[\\/]+' | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    $paths = @($root)
    foreach ($component in $components) {
        $current = Join-Path $current $component
        $paths += $current
    }
    foreach ($candidate in $paths) {
        if (-not ([System.IO.Directory]::Exists($candidate) -or [System.IO.File]::Exists($candidate))) {
            Fail-Bootstrap "$Label contains a missing or unsupported filesystem component."
        }
        try { $attributes = [System.IO.File]::GetAttributes($candidate) }
        catch { Fail-Bootstrap "$Label contains a filesystem component whose attributes cannot be verified." }
        if (($attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            Fail-Bootstrap "$Label must not contain a symbolic link, junction, mount point, or filesystem reparse point."
        }
    }
    return $canonical
}

$bootstrapRoot = Assert-BootstrapNoReparse $ExpectedCanonicalWorktreeRoot 'Expected canonical worktree path'
$bootstrapCommonGitDirectory = Assert-BootstrapNoReparse $ExpectedGitCommonDirectory 'Expected Git common directory'
$bootstrapCurrentDirectory = Assert-BootstrapNoReparse ([Environment]::CurrentDirectory) 'Child process current directory'
if (-not [string]::Equals($bootstrapRoot, $bootstrapCurrentDirectory, [System.StringComparison]::OrdinalIgnoreCase)) {
    Fail-Bootstrap "Child process current directory does not equal the expected canonical worktree root."
}
$bootstrapScript = Assert-BootstrapNoReparse $PSCommandPath 'Executing build script path'
$rootPrefix = $bootstrapRoot + [System.IO.Path]::DirectorySeparatorChar
if (-not $bootstrapScript.StartsWith($rootPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    Fail-Bootstrap "Executing build script is not inside the exact canonical worktree root."
}
$bootstrapGitFile = Assert-BootstrapNoReparse (Join-Path $bootstrapRoot '.git') 'Worktree Git administrative path'
$bootstrapModule = Assert-BootstrapNoReparse (Join-Path $bootstrapRoot 'scripts\release\ReleaseTooling.psm1') 'Release tooling module path'
if (-not $bootstrapModule.StartsWith($rootPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    Fail-Bootstrap "Release tooling module is not inside the exact canonical worktree root."
}

function Invoke-BootstrapGit([string[]]$Arguments) {
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $output = @(& git -C $bootstrapRoot @Arguments 2>$null)
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($exitCode -ne 0) {
        Fail-Bootstrap "Child bootstrap Git identity command failed closed."
    }
    return $output
}

function Get-BootstrapSafeFirstOutputLine([AllowNull()][object]$Value) {
    $items = @($Value)
    if ($items.Count -eq 0 -or $null -eq $items[0]) {
        return [string]::Empty
    }
    return ([string]$items[0]).Trim()
}

function Get-BootstrapProtectedPattern([string]$RelativePath) {
    $leaf = [System.IO.Path]::GetFileName(($RelativePath -replace '/', '\'))
    if ($leaf -ieq 'secret_key.txt') { return 'secret_key.txt' }
    if ($leaf -like '.env*') { return '.env*' }
    if ($leaf -like '*.db') { return '*.db' }
    if ($leaf -like '*.sqlite*') { return '*.sqlite*' }
    if ($leaf -ieq 'questions.json') { return 'questions.json' }
    if ($leaf -like '*.sgf') { return '*.sgf' }
    if ($leaf -like '*.pem') { return '*.pem' }
    if ($leaf -like '*.key') { return '*.key' }
    if ($leaf -like '*.bak*') { return '*.bak*' }
    return $null
}

$bootstrapTopLevel = Get-BootstrapCanonicalPath (Get-BootstrapSafeFirstOutputLine (Invoke-BootstrapGit @('rev-parse', '--show-toplevel'))) 'Bootstrap Git top-level path'
if (-not [string]::Equals($bootstrapTopLevel, $bootstrapRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    Fail-Bootstrap "Bootstrap Git top-level path does not equal the expected canonical worktree root."
}
$bootstrapHead = Get-BootstrapSafeFirstOutputLine (Invoke-BootstrapGit @('rev-parse', 'HEAD'))
$bootstrapExpectedHead = Get-BootstrapSafeFirstOutputLine (Invoke-BootstrapGit @('rev-parse', $ExpectedExactGitSha))
if ($bootstrapHead -ne $bootstrapExpectedHead) {
    Fail-Bootstrap "Bootstrap HEAD does not equal the expected exact Git SHA."
}
$bootstrapBranch = Get-BootstrapSafeFirstOutputLine (Invoke-BootstrapGit @('branch', '--show-current'))
if (-not [string]::IsNullOrWhiteSpace($bootstrapBranch) -or $ExpectedHeadState -ne 'detached') {
    Fail-Bootstrap "Bootstrap worktree HEAD is not detached as required."
}
$bootstrapCommonRaw = Get-BootstrapSafeFirstOutputLine (Invoke-BootstrapGit @('rev-parse', '--git-common-dir'))
$bootstrapActualCommon = if ([System.IO.Path]::IsPathRooted($bootstrapCommonRaw)) {
    Assert-BootstrapNoReparse $bootstrapCommonRaw 'Actual Git common directory'
}
else {
    Assert-BootstrapNoReparse (Join-Path $bootstrapRoot $bootstrapCommonRaw) 'Actual Git common directory'
}
if (-not [string]::Equals($bootstrapActualCommon, $bootstrapCommonGitDirectory, [System.StringComparison]::OrdinalIgnoreCase)) {
    Fail-Bootstrap "Bootstrap worktree does not belong to the expected repository common Git directory."
}
$bootstrapUntrackedAndIgnored = @(
    Invoke-BootstrapGit @('ls-files', '--others', '--exclude-standard')
    Invoke-BootstrapGit @('ls-files', '--others', '--ignored', '--exclude-standard')
) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Unique
foreach ($relativePath in $bootstrapUntrackedAndIgnored) {
    $pattern = Get-BootstrapProtectedPattern $relativePath
    if ($pattern) {
        Fail-Bootstrap "Bootstrap found protected untracked or ignored path '$relativePath' (pattern '$pattern')."
    }
}
$bootstrapStatus = @(Invoke-BootstrapGit @('status', '--porcelain=v1', '--untracked-files=all') | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
if ($bootstrapStatus.Count -ne 0) {
    Fail-Bootstrap "Bootstrap worktree must be completely clean, including untracked files."
}

Import-Module $bootstrapModule -Force -DisableNameChecking

function Fail($msg) {
    Write-Host "BUILD FAILED: $msg" -ForegroundColor Red
    exit 1
}

$validatedWorktreeRoot = Assert-GovernedBuildChildIdentity `
    -ExpectedCanonicalWorktreeRoot $bootstrapRoot `
    -ExpectedGitSha $ExpectedExactGitSha `
    -ExpectedGitCommonDirectory $bootstrapCommonGitDirectory `
    -ExecutingBuildScriptPath $bootstrapScript `
    -ExpectedHeadState $ExpectedHeadState
if ($SkipCleanCheck) {
    Fail "SkipCleanCheck is not permitted for a governed detached-worktree build."
}

if (-not $GitSha) {
    $GitSha = $ExpectedExactGitSha
}
else {
    $GitSha = Get-SafeFirstOutputLine (Invoke-Git -Arguments @('rev-parse', $GitSha) -WorkingDirectory $validatedWorktreeRoot)
}
$resolvedExpectedExactGitSha = Get-SafeFirstOutputLine (Invoke-Git -Arguments @('rev-parse', $ExpectedExactGitSha) -WorkingDirectory $validatedWorktreeRoot)
if ($GitSha -ne $resolvedExpectedExactGitSha) {
    Fail "GitSha does not equal the independently validated expected exact Git SHA."
}

Write-Host "== go-odyssey-app canonical image build (build-only, never deploys) ==" -ForegroundColor Cyan

# 1-2. The child has now independently proved exact cwd, canonical Git root,
# exact SHA, detached HEAD, complete cleanliness, script provenance, and no
# reparse boundary. No Docker/build action occurs above this point.
$shortSha = $GitSha.Substring(0, 8)

# 3. Verify the commit is based on canonical origin/master.
git fetch origin master --quiet 2>$null
$mergeBase = (git merge-base $GitSha origin/master 2>$null)
if (-not $mergeBase) {
    Fail "Commit $GitSha has no merge-base with origin/master. Refusing to build from an unrelated history."
}

# 4. Verify required tracked build inputs exist in this checkout.
$requiredFiles = @(
    'Dockerfile',
    'requirements.txt',
    'entrypoint.sh',
    'app.py',
    'shadow_judging.py',
    'shadow_dashboard.py',
    'shadow_event_storage.py',
    'shadow_dashboard.html',
    'scheduler.py',
    'katago_explain.py',
    'explain_overrides.py',
    'grimoire_api.py',
    'question_taxonomy.py',
    'monster_taxonomy.py',
    'chapter_i18n.py',
    'backend_i18n.py',
    'community_leaderboard_rewards.py',
    'nginx/default.conf',
    'deploy/runtime-source-provenance.json',
    'tools/community_leaderboard_rewards_manual.py',
    'tools/community_leaderboard_rewards_export_entries.py',
    'tools/community_leaderboard_rewards_real_grant_preview.py',
    'tools/community_leaderboard_rewards_real_grant_commit.py',
    'tools/community_leaderboard_rewards_exact_period.py'
)
$missing = @()
foreach ($f in $requiredFiles) {
    if (-not (Test-Path $f)) { $missing += $f }
}
if ($missing.Count -gt 0) {
    Fail "Required tracked build inputs are missing from this checkout:`n$($missing -join "`n")"
}

# 5. Verify SGF Engine provenance / vendoring state.
if (-not (Test-Path 'sgf_engine/VENDORED_FROM.txt')) {
    Fail "sgf_engine provenance record (sgf_engine/VENDORED_FROM.txt) missing. Do not build without an explicit, documented SGF Engine vendoring state."
}
$sgfEngineVendored = Test-Path 'sgf_engine/__init__.py'
if (-not $sgfEngineVendored) {
    Write-Host "NOTE: sgf_engine/ is not vendored in this checkout (see sgf_engine/PROVENANCE_VERIFICATION.md)." -ForegroundColor Yellow
    Write-Host "The Docker build below is EXPECTED TO FAIL at 'COPY sgf_engine ./sgf_engine' until this is resolved." -ForegroundColor Yellow
}

# 6. Verify the large/PENDING build inputs listed in the manifest and report what's missing,
#    rather than silently building from whatever happens to be in the working tree.
$manifestPath = 'deploy/build-manifest.json'
if (-not (Test-Path $manifestPath)) {
    Fail "deploy/build-manifest.json is missing."
}
$manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
$pendingInputs = $manifest.build_inputs.required_but_not_yet_vendored
$missingPending = @()
foreach ($item in $pendingInputs) {
    $p = $item.path -replace '/$', '' -split ',' | ForEach-Object { $_.Trim() } | Select-Object -First 1
    $p = ($item.path -split ',')[0].Trim().TrimEnd('/')
    if ($p -match '\*' -or $p -match '\(') { continue }  # wildcard/annotated entries: informational only
    if (-not (Test-Path $p)) {
        $missingPending += $p
    }
}
if ($missingPending.Count -gt 0) {
    Write-Host "NOTE: the following build inputs are documented as not-yet-vendored and are absent from this checkout:" -ForegroundColor Yellow
    $missingPending | ForEach-Object { Write-Host "  - $_" -ForegroundColor Yellow }
    Write-Host "The Docker build below is EXPECTED TO FAIL at the corresponding COPY instruction(s)." -ForegroundColor Yellow
}

# 7. Derive the immutable image tag and build metadata.
$imageTag = "go-odyssey-app:$shortSha"
$buildDate = $env:APP_BUILD_DATE_OVERRIDE
if (-not $buildDate) {
    Fail "APP_BUILD_DATE_OVERRIDE environment variable must be set to a UTC ISO-8601 timestamp by the caller (this script does not read the system clock, to keep builds reproducible/reviewable)."
}
$sgfEngineCommit = if ($sgfEngineVendored) { 'd729645c0ae267be6d89a5b49c007bc64284bbcc' } else { 'PENDING-not-vendored' }

Write-Host "Image tag:         $imageTag"
Write-Host "APP_GIT_SHA:        $GitSha"
Write-Host "APP_BUILD_DATE:     $buildDate"
Write-Host "SGF_ENGINE_SOURCE_COMMIT: $sgfEngineCommit"

# 8. Verify docker AND buildx are available, and that the active builder
#    actually supports the target platform. RELEASE-TOOLING-HOTFIX-02: do
#    not silently fall back to a plain `docker build` (which targets the
#    local daemon's native platform with no cross-build capability) if
#    buildx or arm64 support is unavailable -- fail closed and say why.
$docker = Get-Command docker -ErrorAction SilentlyContinue
if (-not $docker) {
    Write-Host "BUILD NOT EXECUTED — LOCAL DOCKER ENGINE UNAVAILABLE" -ForegroundColor Yellow
    exit 0
}
& docker buildx version *> $null
if ($LASTEXITCODE -ne 0) {
    Fail "docker buildx is not available. This build requires buildx to target $Platform -- refusing to silently fall back to a plain `docker build` (which would target the local machine's native platform, not the production contract)."
}
$builderPlatforms = (& docker buildx inspect 2>$null | Select-String -Pattern '^Platforms:\s*(.+)$').Matches |
    ForEach-Object { $_.Groups[1].Value } | Select-Object -First 1
if (-not $builderPlatforms -or ($builderPlatforms -split ',\s*') -notcontains $Platform) {
    Fail "The active buildx builder does not report support for $Platform (reported platforms: $builderPlatforms). Refusing to build -- this is a capability gap to fix (e.g. QEMU/binfmt setup), not something to silently downgrade past."
}

# 9. Build with buildx, targeting the explicit platform contract, loaded
#    into the local Docker image store (--load) so the rest of this
#    pipeline (package-release-image.ps1, deploy-release-image.ps1) can
#    use it exactly like any other locally-built image. Never deploy,
#    never `up`, never touch any remote host.
$buildResult = Invoke-BoundedNativeCommand `
    -FileName 'docker' `
    -ArgumentList @(
        'buildx', 'build',
        '--platform', $Platform,
        '--load',
        '--build-arg', "APP_GIT_SHA=$GitSha",
        '--build-arg', "APP_BUILD_DATE=$buildDate",
        '--build-arg', "SGF_ENGINE_SOURCE_COMMIT=$sgfEngineCommit",
        '-t', $imageTag,
        '.'
    ) `
    -TimeoutSeconds 3600 `
    -OperationLabel 'canonical production image build'
Write-Host $buildResult.output
if ($buildResult.exit_code -ne 0) {
    Fail "docker buildx build exited with code $($buildResult.exit_code)."
}

# 9b. Verify the built image's actual platform, immediately, at build time.
#     RELEASE-TOOLING-HOTFIX-02: this must not be the only place platform is
#     checked (deploy-release-image.ps1's -ExpectedPlatform check stays in
#     place too), but it must not be the ONLY line of defense either -- a
#     wrong-architecture image should never leave this script un-flagged.
$actualPlatform = Get-ImagePlatform -ImageTag $imageTag
if ($actualPlatform -ne $Platform) {
    Fail "Built image $imageTag reports platform '$actualPlatform', expected '$Platform'. Refusing to hand off a wrong-architecture image to the rest of the release pipeline."
}
Write-Host "Verified image platform: $actualPlatform" -ForegroundColor Green

# 10. Verify every manifest-declared runtime file is present in the built image.
# This is one bounded, network-isolated container invocation. It overrides the
# application entrypoint, supplies no secrets or mounts, and executes only the
# image's Python interpreter against absolute filesystem paths.
$verificationFiles = @($manifest.post_build_verification_files)
if ($verificationFiles.Count -eq 0) {
    Fail "deploy/build-manifest.json post_build_verification_files must contain at least one path."
}
foreach ($verificationFile in $verificationFiles) {
    $verificationPath = [string]$verificationFile
    if (
        [string]::IsNullOrWhiteSpace($verificationPath) -or
        $verificationPath -notmatch '^/app/[A-Za-z0-9._/-]+$' -or
        $verificationPath -match '(^|/)\.\.(/|$)' -or
        $verificationPath.EndsWith('/')
    ) {
        Fail "deploy/build-manifest.json contains an invalid post-build verification path."
    }
}
$filesystemCheck = "import os,sys; missing=[p for p in sys.argv[1:] if not os.path.isfile(p)]; print(('missing required image files: '+','.join(missing)) if missing else ('verified required image files: '+str(len(sys.argv)-1))); raise SystemExit(1 if missing else 0)"
$verificationArguments = @(
    'run', '--rm',
    '--platform', $Platform,
    '--network', 'none',
    '--read-only',
    '--entrypoint', 'python',
    $imageTag,
    '-c', $filesystemCheck
)
$verificationArguments += $verificationFiles
$filesystemResult = Invoke-BoundedNativeCommand `
    -FileName 'docker' `
    -ArgumentList $verificationArguments `
    -TimeoutSeconds 120 `
    -OperationLabel 'required built-image filesystem verification'
Write-Host $filesystemResult.output
if ($filesystemResult.exit_code -ne 0) {
    Fail "Built image $imageTag is missing one or more manifest-declared runtime files."
}

# 11. Record what was built. Never push, never deploy.
$record = [ordered]@{
    image_tag        = $imageTag
    git_sha           = $GitSha
    build_date        = $buildDate
    sgf_engine_commit = $sgfEngineCommit
    merge_base_with_master = $mergeBase
    platform          = $actualPlatform
}
$record | ConvertTo-Json | Write-Host

Write-Host "== Build complete. This script never deploys, pushes, or restarts anything. ==" -ForegroundColor Green
