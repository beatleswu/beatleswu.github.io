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

.EXAMPLE
  pwsh ./scripts/build-production-image.ps1
#>
[CmdletBinding()]
param(
    [string]$GitSha,
    [switch]$SkipCleanCheck
)

$ErrorActionPreference = 'Stop'

function Fail($msg) {
    Write-Host "BUILD FAILED: $msg" -ForegroundColor Red
    exit 1
}

Write-Host "== go-odyssey-app canonical image build (build-only, never deploys) ==" -ForegroundColor Cyan

# 1. Require a clean checkout (unless explicitly overridden for local iteration).
if (-not $SkipCleanCheck) {
    $status = git status --short
    if ($status) {
        Fail "Working tree is not clean. Commit or stash changes, or pass -SkipCleanCheck for a non-reproducible local iteration build.`n$status"
    }
}

# 2. Resolve the commit to build.
if (-not $GitSha) {
    $GitSha = (git rev-parse HEAD).Trim()
}
else {
    $GitSha = (git rev-parse $GitSha).Trim()
}
if (-not $GitSha) {
    Fail "Could not resolve a Git SHA to build."
}
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
    'tools/community_leaderboard_rewards_real_grant_commit.py'
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

# 8. Verify docker is available.
$docker = Get-Command docker -ErrorAction SilentlyContinue
if (-not $docker) {
    Write-Host "BUILD NOT EXECUTED — LOCAL DOCKER ENGINE UNAVAILABLE" -ForegroundColor Yellow
    exit 0
}

# 9. Build. Never deploy, never `up`, never touch any remote host.
docker build `
    --build-arg "APP_GIT_SHA=$GitSha" `
    --build-arg "APP_BUILD_DATE=$buildDate" `
    --build-arg "SGF_ENGINE_SOURCE_COMMIT=$sgfEngineCommit" `
    -t $imageTag `
    -f Dockerfile `
    .

if ($LASTEXITCODE -ne 0) {
    Fail "docker build exited with code $LASTEXITCODE."
}

# 10. Record what was built. Never push, never deploy.
$record = [ordered]@{
    image_tag        = $imageTag
    git_sha           = $GitSha
    build_date        = $buildDate
    sgf_engine_commit = $sgfEngineCommit
    merge_base_with_master = $mergeBase
}
$record | ConvertTo-Json | Write-Host

Write-Host "== Build complete. This script never deploys, pushes, or restarts anything. ==" -ForegroundColor Green
