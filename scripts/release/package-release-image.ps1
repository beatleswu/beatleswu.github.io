#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ExpectedGitSha,
    [string]$ImageTag,
    [string]$ArchivePath,
    [string]$ReleaseManifestPath,
    [string]$LayoutFile = 'deploy\release-layout.example.json',
    [Parameter(Mandatory = $true)][string]$QuestionsCorpusPath,
    [Parameter(Mandatory = $true)][string]$QuestionsCorpusSha256,
    [Parameter(Mandatory = $true)][long]$QuestionsCorpusRecordCount,
    [Parameter(Mandatory = $true)][long]$QuestionsCorpusBytes,
    [Parameter(Mandatory = $true)][string]$QuestionsCorpusSnapshotId,
    [Parameter(Mandatory = $true)][string]$QuestionsCorpusSourceIdentity,
    [Parameter(Mandatory = $true)][string]$QuestionsCorpusSourceSha256,
    [Parameter(Mandatory = $true)][long]$QuestionsCorpusSourceRecordCount,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'ReleaseTooling.psm1') -Force -DisableNameChecking

$repoRoot = Get-RepoRoot
$ExpectedGitSha = (Invoke-Git -Arguments @('rev-parse', $ExpectedGitSha) -WorkingDirectory $repoRoot).Trim()
$layout = Get-ReleaseLayout -Path (Resolve-RepoPath $LayoutFile)
if (-not $ImageTag) {
    $ImageTag = Get-ReleaseImageTag -GitSha $ExpectedGitSha
}

$baseName = Get-ReleaseArtifactBaseName -GitSha $ExpectedGitSha
if (-not $ArchivePath) {
    Ensure-Directory -Path (Join-Path $repoRoot 'release-artifacts')
    $ArchivePath = Join-Path $repoRoot ("release-artifacts\{0}.tar" -f $baseName)
}
if (-not $ReleaseManifestPath) {
    $ReleaseManifestPath = Join-Path (Split-Path -Parent $ArchivePath) ("{0}.release.json" -f $baseName)
}

$labels = Assert-ImageRevisionMatches -ImageTag $ImageTag -ExpectedGitSha $ExpectedGitSha

$resolvedQuestionsCorpusPath = Assert-NoReparsePointPath -Path ((Resolve-Path -LiteralPath $QuestionsCorpusPath -ErrorAction Stop).Path) -Label 'Questions corpus'
if (-not (Test-Path -LiteralPath $resolvedQuestionsCorpusPath -PathType Leaf)) {
    throw "QuestionsCorpusPath must resolve to an existing regular file."
}
$pythonCommand = Get-Command python -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $pythonCommand -or [string]::IsNullOrWhiteSpace([string]$pythonCommand.Source)) {
    throw 'Python executable is required for questions corpus validation.'
}
$validatorPath = Resolve-RepoPath 'tools/questions_corpus_validation.py'
$validationArgs = @(
    $validatorPath, 'validate', '--corpus-path', $resolvedQuestionsCorpusPath,
    '--mode', 'RELEASE_ENFORCEMENT',
    '--questions_corpus_sha256', $QuestionsCorpusSha256.ToLowerInvariant(),
    '--questions_corpus_record_count', [string]$QuestionsCorpusRecordCount,
    '--questions_corpus_bytes', [string]$QuestionsCorpusBytes,
    '--questions_corpus_snapshot_id', $QuestionsCorpusSnapshotId,
    '--questions_corpus_source_identity', $QuestionsCorpusSourceIdentity.ToLowerInvariant(),
    '--questions_corpus_source_sha256', $QuestionsCorpusSourceSha256.ToLowerInvariant(),
    '--questions_corpus_source_record_count', [string]$QuestionsCorpusSourceRecordCount
)
$quotedValidationArgs = ($validationArgs | ForEach-Object {
    '"' + ([string]$_ -replace '"', '\"') + '"'
}) -join ' '
$validationResult = Invoke-ProcessWithSeparateOutput -FileName $pythonCommand.Source -Arguments ("-B " + $quotedValidationArgs) -WorkingDirectory $repoRoot -TimeoutSeconds 300
if ($validationResult.exit_code -ne 0) {
    throw "Questions corpus release validation failed closed: $($validationResult.stdout)"
}
try {
    $corpusValidation = [string]$validationResult.stdout | ConvertFrom-Json
} catch {
    throw 'Questions corpus validator returned malformed JSON.'
}
if ($corpusValidation.status -ne 'PASS' -or $corpusValidation.release_rejected -eq $true) {
    throw 'Questions corpus release validation did not return PASS.'
}
$corpusIdentity = [ordered]@{
    questions_corpus_sha256 = $QuestionsCorpusSha256.ToLowerInvariant()
    questions_corpus_record_count = [int64]$QuestionsCorpusRecordCount
    questions_corpus_bytes = [int64]$QuestionsCorpusBytes
    questions_corpus_snapshot_id = $QuestionsCorpusSnapshotId
    questions_corpus_source_identity = $QuestionsCorpusSourceIdentity.ToLowerInvariant()
    questions_corpus_source_sha256 = $QuestionsCorpusSourceSha256.ToLowerInvariant()
    questions_corpus_source_record_count = [int64]$QuestionsCorpusSourceRecordCount
}

if ($DryRun) {
    [ordered]@{
        dry_run = $true
        image_tag = $ImageTag
        archive_path = $ArchivePath
        release_manifest_path = $ReleaseManifestPath
        release_layout = $layout
        revision = $labels.'org.opencontainers.image.revision'
        questions_corpus_identity = $corpusIdentity
        questions_corpus_validation = $corpusValidation.summary
    } | ConvertTo-Json -Depth 8 | Write-Output
    return
}

docker save -o $ArchivePath $ImageTag | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "docker save failed with exit code $LASTEXITCODE."
}

$archiveSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $ArchivePath).Hash.ToLowerInvariant()
$imageId = (& docker image inspect $ImageTag --format '{{.Id}}').Trim()
$manifest = New-ReleaseManifestObject `
    -GitSha $ExpectedGitSha `
    -ImageTag $ImageTag `
    -ImageId $imageId `
    -ArchiveFilename ([IO.Path]::GetFileName($ArchivePath)) `
    -ArchiveSha256 $archiveSha `
    -BuildTimestamp ([DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')) `
    -BuildMachineIdentityClass 'local-release-workstation' `
    -TargetServiceNames @($layout.app_service_name, $layout.scheduler_service_name) `
    -ExternalContentRequirements ([ordered]@{
        asset_source_path = $layout.asset_source_path
        asset_container_mount_destination = $layout.asset_container_mount_destination
        questions_content_source_path = $layout.questions_content_source_path
        questions_content_mount_destination = $layout.questions_content_mount_destination
        shadow_event_log_path = $layout.shadow_event_log_path
    }) `
    -QuestionsCorpusIdentity $corpusIdentity `
    -ExpectedHealthEndpoints @($layout.health_url, $layout.login_url, $layout.homepage_url) `
    -RollbackImageIdentity ([ordered]@{}) `
    -VerificationResult 'package complete; deployment pending' `
    -DeploymentTimestamp $null `
    -OCIRevision $labels.'org.opencontainers.image.revision'

Write-JsonFile -InputObject $manifest -Path $ReleaseManifestPath
[ordered]@{
    image_tag = $ImageTag
    image_id = $imageId
    archive_path = $ArchivePath
    archive_sha256 = $archiveSha
    release_manifest_path = $ReleaseManifestPath
} | ConvertTo-Json -Depth 8 | Write-Output
