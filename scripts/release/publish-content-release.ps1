<#
.SYNOPSIS
  Governed content-only Production promotion for the PR318 release contract.

.DESCRIPTION
  This runner consumes an immutable, already-built content bundle. It uses
  the existing bounded SSH/SCP and release-operation-lock primitives from
  ReleaseTooling.psm1, then invokes the reviewed standard-library helper on
  the Production host. The helper resolves the live questions target from
  Docker's actual named-volume mount; no host mountpoint is guessed.

  Verification-only behavior is the default. -Execute requires the explicit
  content-release Owner gate and is intentionally not used by normal tests or
  release preparation.

  This is content-only: it does not build or deploy an application image,
  switch static assets, restart services, regenerate SGF repairs, or alter
  runtime judging semantics.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$BundlePath,
    [Parameter(Mandatory = $true)][string]$ExpectedPredecessorSha256,
    [Parameter(Mandatory = $true)][int]$ExpectedPredecessorRecordCount,
    [Parameter(Mandatory = $true)][string]$TargetCandidateSha256,
    [Parameter(Mandatory = $true)][int]$TargetCandidateRecordCount,
    [Parameter(Mandatory = $true)][string]$ExpectedReleasePackageSha256,
    [Parameter(Mandatory = $true)][string]$ExpectedRollbackManifestSha256,
    [string]$ReleaseId,
    [string]$ReceiptOutput,
    [string]$LayoutFile = 'deploy\release-layout.production.json',
    [switch]$Execute,
    [string]$OwnerGate
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'ReleaseTooling.psm1') -Force -DisableNameChecking

$ContentReleaseOwnerGate = 'GO_PRODUCTION_CONTENT_RELEASE'
$RemoteCommandTimeoutSeconds = 90
$RemoteUploadTimeoutSeconds = 180

function Assert-ContentSha256 {
    param([Parameter(Mandatory = $true)][string]$Value, [Parameter(Mandatory = $true)][string]$Label)
    if ($Value -notmatch '^[0-9a-f]{64}$') { throw "$Label must be a lowercase SHA-256." }
}

function Assert-ContentReleaseId {
    param([Parameter(Mandatory = $true)][string]$Value)
    if ($Value -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$') {
        throw 'ReleaseId must contain only bounded ASCII release-id characters.'
    }
}

function Assert-AbsoluteRemotePath {
    param([Parameter(Mandatory = $true)][string]$Value, [Parameter(Mandatory = $true)][string]$Label)
    if ([string]::IsNullOrWhiteSpace($Value) -or -not $Value.StartsWith('/')) {
        throw "$Label must be an absolute POSIX path."
    }
    $normalized = $Value.Replace('\','/')
    if ($normalized -match '(^|/)\.\.?(/|$)' -or $normalized -match '[\x00-\x1f\x7f;|&$<>]') {
        throw "$Label contains unsafe path components."
    }
}

function Get-LocalPythonExecutable {
    $command = Get-Command python -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $command -or [string]::IsNullOrWhiteSpace($command.Source)) {
        throw 'Python executable is required for local bundle validation.'
    }
    return $command.Source
}

function Invoke-LocalBundleValidation {
    param(
        [Parameter(Mandatory = $true)][string]$Bundle,
        [Parameter(Mandatory = $true)][string]$Python,
        [Parameter(Mandatory = $true)][string]$Validator
    )
    $arguments = @($Validator, 'validate-bundle', '--bundle-dir', $Bundle,
        '--expected-predecessor-sha256', $ExpectedPredecessorSha256,
        '--expected-predecessor-record-count', [string]$ExpectedPredecessorRecordCount,
        '--expected-candidate-sha256', $TargetCandidateSha256,
        '--expected-candidate-record-count', [string]$TargetCandidateRecordCount,
        '--expected-release-package-sha256', $ExpectedReleasePackageSha256,
        '--expected-rollback-manifest-sha256', $ExpectedRollbackManifestSha256,
        '--target-path', $targetPath)
    $result = Invoke-BoundedNativeCommand -FileName $Python -ArgumentList $arguments -TimeoutSeconds $RemoteUploadTimeoutSeconds -OperationLabel 'local content bundle validation'
    if ($result.exit_code -ne 0) { throw "Content bundle validation failed closed: $($result.output)" }
    $stdout = [string]$result.stdout
    try { return ($stdout | ConvertFrom-Json) } catch { throw 'Content bundle validator returned malformed JSON.' }
}

function Invoke-RemotePythonStdin {
    param(
        [Parameter(Mandatory = $true)][string]$Command,
        [Parameter(Mandatory = $true)][string]$ScriptText,
        [Parameter(Mandatory = $true)][string]$OperationLabel
    )
    $sshOptions = Get-BoundedSshOptionArguments
    $arguments = @($sshOptions) + @($layout.ssh_alias, $Command)
    return Invoke-BoundedNativeCommand -FileName 'ssh' -ArgumentList $arguments -StdinText $ScriptText -TimeoutSeconds $RemoteCommandTimeoutSeconds -OperationLabel $OperationLabel
}

function Convert-RemoteJsonResult {
    param([Parameter(Mandatory = $true)]$Result, [Parameter(Mandatory = $true)][string]$Context)
    $stdout = [string]$Result.stdout
    if ([string]::IsNullOrWhiteSpace($stdout)) { throw "$Context returned no JSON result." }
    try { return ($stdout | ConvertFrom-Json) } catch { throw "$Context returned malformed JSON." }
}

Assert-ContentSha256 -Value $ExpectedPredecessorSha256.ToLowerInvariant() -Label 'ExpectedPredecessorSha256'
Assert-ContentSha256 -Value $TargetCandidateSha256.ToLowerInvariant() -Label 'TargetCandidateSha256'
Assert-ContentSha256 -Value $ExpectedReleasePackageSha256.ToLowerInvariant() -Label 'ExpectedReleasePackageSha256'
Assert-ContentSha256 -Value $ExpectedRollbackManifestSha256.ToLowerInvariant() -Label 'ExpectedRollbackManifestSha256'
if ($ExpectedPredecessorRecordCount -le 0 -or $TargetCandidateRecordCount -le 0) { throw 'Content record counts must be positive.' }

$repoRoot = Get-RepoRoot
$layout = Get-ReleaseLayout -Path (Resolve-RepoPath $LayoutFile)
$targetPath = ($layout.questions_content_mount_destination.TrimEnd('/','\') + '/questions.json')
if ($targetPath -ne '/app/data/questions.json') {
    throw "Unsupported content target '$targetPath'; canonical target must be /app/data/questions.json."
}
Assert-AbsoluteRemotePath -Value ([string]$layout.remote_release_staging_directory) -Label 'remote_release_staging_directory'
Assert-AbsoluteRemotePath -Value ([string]$layout.compose_directory) -Label 'compose_directory'
$bundle = (Resolve-Path -LiteralPath $BundlePath -ErrorAction Stop).Path
if (-not (Test-Path -LiteralPath $bundle -PathType Container)) { throw 'BundlePath must resolve to a directory.' }
$helperPath = Resolve-RepoPath 'tools/content_remote_publish.py'
$python = Get-LocalPythonExecutable
$validation = Invoke-LocalBundleValidation -Bundle $bundle -Python $python -Validator $helperPath

if ([string]::IsNullOrWhiteSpace($ReleaseId)) {
    $ReleaseId = 'content-{0}-{1}-{2}' -f $TargetCandidateSha256.Substring(0, 12), $ExpectedReleasePackageSha256.Substring(0, 12), ([DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ'))
}
Assert-ContentReleaseId -Value $ReleaseId
$remoteRoot = ([string]$layout.remote_release_staging_directory).TrimEnd('/')
$remoteReleaseDir = "$remoteRoot/content/$ReleaseId"
Assert-AbsoluteRemotePath -Value $remoteReleaseDir -Label 'remote content release directory'
$remoteLockPath = (([string]$layout.compose_directory).TrimEnd('/') + '/.release-operation.lock')
$operationId = "content-$ReleaseId"

$remoteInspectCommand = @(
    'sudo -n python3 - remote-inspect',
    '--container-name', (Quote-PosixShellArgument ([string]$layout.app_service_name)),
    '--mount-destination', (Quote-PosixShellArgument ([string]$layout.questions_content_mount_destination)),
    '--target-path', (Quote-PosixShellArgument $targetPath),
    '--expected-predecessor-sha256', (Quote-PosixShellArgument $ExpectedPredecessorSha256.ToLowerInvariant()),
    '--expected-predecessor-record-count', (Quote-PosixShellArgument ([string]$ExpectedPredecessorRecordCount)),
    '--staging-root', (Quote-PosixShellArgument $remoteRoot),
    '--release-dir', (Quote-PosixShellArgument $remoteReleaseDir),
    '--release-id', (Quote-PosixShellArgument $ReleaseId)
) -join ' '

if (-not $Execute) {
    # The helper is sent over stdin only. No remote staging directory,
    # receipt, backup, lock, or content file is created in dry-run mode.
    $remoteInspect = Invoke-RemotePythonStdin -Command $remoteInspectCommand -ScriptText (Get-Content -Raw -LiteralPath $helperPath) -OperationLabel 'content release remote predecessor preflight'
    if ($remoteInspect.exit_code -ne 0) { throw "Remote content predecessor preflight failed closed: $($remoteInspect.output)" }
    $remoteReport = Convert-RemoteJsonResult -Result $remoteInspect -Context 'remote content predecessor preflight'
    $report = [ordered]@{
        mode = 'DRY_RUN'
        production_mutation = $false
        publish_executed = $false
        target = $targetPath
        local_bundle = $validation
        remote_predecessor = $remoteReport
        remote_staging = 'NOT_CREATED'
        rollback_readiness = 'BUNDLE_ROLLBACK_MANIFEST_VERIFIED; REMOTE_CAPTURE_DEFERRED_TO_EXECUTION'
        existing_remote_primitives_reused = @('Invoke-BoundedNativeCommand', 'Invoke-BoundedSshCommand', 'Invoke-BoundedScpUpload', 'Enter-RemoteReleaseOperationLock', 'Exit-RemoteReleaseOperationLock')
    }
    if (-not [string]::IsNullOrWhiteSpace($ReceiptOutput)) { Write-JsonFile -InputObject $report -Path $ReceiptOutput }
    $report | ConvertTo-Json -Depth 30 | Write-Output
    return
}

Assert-OwnerGate -Provided $OwnerGate -Expected $ContentReleaseOwnerGate
$lockHeld = $false
try {
    $null = Enter-RemoteReleaseOperationLock -SshAlias $layout.ssh_alias -LockPath $remoteLockPath -OperationId $operationId
    $lockHeld = $true
    $mkdirCommand = "if test -e $(Quote-PosixShellArgument $remoteReleaseDir); then exit 73; fi; install -d -m 700 $(Quote-PosixShellArgument $remoteReleaseDir) && install -d -m 700 $(Quote-PosixShellArgument ($remoteReleaseDir + '/.runner'))"
    $mkdirResult = Invoke-BoundedSshCommand -SshAlias $layout.ssh_alias -Command $mkdirCommand -TimeoutSeconds $RemoteCommandTimeoutSeconds -OperationLabel 'content release remote staging directory'
    if ($mkdirResult.exit_code -ne 0) { throw "Remote content staging directory could not be created: $($mkdirResult.output)" }

    $allowedAssets = @('acceptance-evidence.json', 'content-registry-entry.json', 'content-release-manifest.json', 'content-rollback-manifest.json', 'questions.repaired-candidate.json.gz', 'SHA256SUMS.txt')
    foreach ($asset in $allowedAssets) {
        $localAsset = Join-Path $bundle $asset
        if (-not (Test-Path -LiteralPath $localAsset -PathType Leaf)) { throw "Validated bundle asset disappeared: $asset" }
        $upload = Invoke-BoundedScpUpload -LocalPath $localAsset -SshAlias $layout.ssh_alias -RemotePath "$remoteReleaseDir/$asset" -TimeoutSeconds $RemoteUploadTimeoutSeconds -OperationLabel "content release upload $asset"
        if ($upload.exit_code -ne 0) { throw "Remote upload failed for ${asset}: $($upload.output)" }
    }
    $helperRemotePath = "$remoteReleaseDir/.runner/content_remote_publish.py"
    $helperUpload = Invoke-BoundedScpUpload -LocalPath $helperPath -SshAlias $layout.ssh_alias -RemotePath $helperRemotePath -TimeoutSeconds $RemoteUploadTimeoutSeconds -OperationLabel 'content release helper upload'
    if ($helperUpload.exit_code -ne 0) { throw "Remote content helper upload failed: $($helperUpload.output)" }

    $remotePromoteCommand = @(
        'sudo -n python3', (Quote-PosixShellArgument $helperRemotePath), 'remote-promote',
        '--bundle-dir', (Quote-PosixShellArgument $remoteReleaseDir),
        '--staging-root', (Quote-PosixShellArgument $remoteRoot),
        '--release-dir', (Quote-PosixShellArgument $remoteReleaseDir),
        '--release-id', (Quote-PosixShellArgument $ReleaseId),
        '--container-name', (Quote-PosixShellArgument ([string]$layout.app_service_name)),
        '--mount-destination', (Quote-PosixShellArgument ([string]$layout.questions_content_mount_destination)),
        '--target-path', (Quote-PosixShellArgument $targetPath),
        '--expected-predecessor-sha256', (Quote-PosixShellArgument $ExpectedPredecessorSha256.ToLowerInvariant()),
        '--expected-predecessor-record-count', (Quote-PosixShellArgument ([string]$ExpectedPredecessorRecordCount)),
        '--expected-candidate-sha256', (Quote-PosixShellArgument $TargetCandidateSha256.ToLowerInvariant()),
        '--expected-candidate-record-count', (Quote-PosixShellArgument ([string]$TargetCandidateRecordCount)),
        '--expected-release-package-sha256', (Quote-PosixShellArgument $ExpectedReleasePackageSha256.ToLowerInvariant()),
        '--expected-rollback-manifest-sha256', (Quote-PosixShellArgument $ExpectedRollbackManifestSha256.ToLowerInvariant())
    ) -join ' '
    $promote = Invoke-BoundedSshCommand -SshAlias $layout.ssh_alias -Command $remotePromoteCommand -TimeoutSeconds $RemoteUploadTimeoutSeconds -OperationLabel 'content release atomic promotion'
    if ($promote.exit_code -notin @(0, 75)) { throw "Remote content promotion failed closed: $($promote.output)" }
    $remoteResult = Convert-RemoteJsonResult -Result $promote -Context 'remote content promotion'
    $report = [ordered]@{
        mode = 'EXECUTE'
        production_mutation = ($remoteResult.production_mutation -eq $true)
        publish_executed = $true
        target = $targetPath
        release_id = $ReleaseId
        local_bundle = $validation
        remote_result = $remoteResult
        existing_remote_primitives_reused = @('Invoke-BoundedNativeCommand', 'Invoke-BoundedSshCommand', 'Invoke-BoundedScpUpload', 'Enter-RemoteReleaseOperationLock', 'Exit-RemoteReleaseOperationLock')
    }
    if (-not [string]::IsNullOrWhiteSpace($ReceiptOutput)) { Write-JsonFile -InputObject $report -Path $ReceiptOutput }
    $report | ConvertTo-Json -Depth 40 | Write-Output
}
finally {
    if ($lockHeld) {
        $null = Exit-RemoteReleaseOperationLock -SshAlias $layout.ssh_alias -LockPath $remoteLockPath -OperationId $operationId
    }
}
