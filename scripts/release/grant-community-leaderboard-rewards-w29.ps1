#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidateSet('w29-c866f611-20260720T055453Z-c001bcd0')][string]$OperationId,
    [Parameter(Mandatory = $true)][ValidateSet('go-odyssey-app:c866f611')][string]$ExpectedSchedulerImageTag,
    [Parameter(Mandatory = $true)][ValidateSet('sha256:e8bafcd1bce435f78782e220f82058112e930c71dcaea6a87ff0adb2462a8ac3')][string]$ExpectedSchedulerImageId,
    [Parameter(Mandatory = $true)][ValidateSet('c866f6114232839c2951d02c71f000983098eda6')][string]$ExpectedRevision,
    [Parameter(Mandatory = $true)][ValidateSet('4c7aa3ea6d9c477fe34951054d89ecb2c11e6f2bac925142c06e1c44beff7740')][string]$CanonicalSnapshotSha256,
    [Parameter(Mandatory = $true)][ValidateSet('449f33defce8a134990f61448316a9bf4e3ceae8e75f0a803fb1822aa1f8d0dc')][string]$CanonicalPreviewSha256,
    [string]$LayoutFile = 'deploy\release-layout.production.json',
    [switch]$Execute,
    [string]$OwnerGate
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'ReleaseTooling.psm1') -Force -DisableNameChecking
Import-Module (Join-Path $PSScriptRoot 'CommunityRewardsExecutionControl.psm1') -Force -DisableNameChecking

if (-not $Execute) { throw 'Exact W29 grant requires -Execute.' }
Assert-OwnerGate -Provided $OwnerGate -Expected 'GO_GRANT_W29'
$layout = Get-ReleaseLayout -Path (Resolve-RepoPath $LayoutFile)
$remoteOperationDirectory = "/opt/go-odyssey/reward-operations/$OperationId"
$wrapperSourceRevision = (& git -C (Resolve-RepoPath '.') rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $wrapperSourceRevision -notmatch '^[0-9a-f]{40}$') {
    throw 'Unable to resolve the exact wrapper source revision.'
}
$releaseOperationId = "community-w29-grant-$([Guid]::NewGuid().ToString('N'))"
$lockPath = "$($layout.compose_directory.TrimEnd('/'))/.release-operation.lock"
$lockHeld = $false
$grantRemoteExitCode = $null
$launchCount = 0

function Write-GrantStageEvidence {
    param(
        [Parameter(Mandatory = $true)][string]$Stage,
        [Parameter(Mandatory = $true)][string]$Status,
        [int]$LaunchCount = 0,
        [Nullable[int]]$RemoteShellExitCode,
        [string]$FailureCategory = ''
    )
    $script = New-CommunityRewardsGrantEvidenceRemoteScript `
        -OperationDirectory $remoteOperationDirectory `
        -OperationId $OperationId `
        -Stage $Stage `
        -Status $Status `
        -LaunchCount $LaunchCount `
        -WrapperSourceRevision $wrapperSourceRevision `
        -RemoteShellExitCode $RemoteShellExitCode `
        -FailureCategory $FailureCategory
    $evidenceResult = Invoke-RemoteShellCommand `
        -SshAlias $layout.ssh_alias `
        -Name "community_w29_evidence_$Stage" `
        -ScriptText $script
    if ($evidenceResult.exit_code -ne 0) {
        throw "Exact W29 grant evidence persistence failed closed at $Stage."
    }
}

try {
    Write-GrantStageEvidence -Stage invocation_started -Status started
    Write-GrantStageEvidence -Stage local_validation_passed -Status passed
    $null = Enter-RemoteReleaseOperationLock `
        -SshAlias $layout.ssh_alias `
        -LockPath $lockPath `
        -OperationId $releaseOperationId
    $lockHeld = $true
    Write-GrantStageEvidence -Stage release_lock_acquired -Status completed
    Write-GrantStageEvidence -Stage remote_preflight_started -Status started
    try {
        $zeroStateScript = New-CommunityRewardsZeroStateProbeRemoteScript `
            -SchedulerContainer $layout.scheduler_service_name
        $zeroStateResult = Invoke-RemoteShellCommand `
            -SshAlias $layout.ssh_alias `
            -Name 'community_w29_exact_grant_zero_state' `
            -ScriptText $zeroStateScript
    }
    catch {
        Write-GrantStageEvidence `
            -Stage remote_preflight_started `
            -Status failed `
            -FailureCategory remote_shell
        throw
    }
    if ($zeroStateResult.exit_code -ne 0) {
        Write-GrantStageEvidence `
            -Stage remote_preflight_started `
            -Status failed `
            -RemoteShellExitCode ([int]$zeroStateResult.exit_code) `
            -FailureCategory remote_shell
        throw 'Exact W29 grant zero-state probe failed closed; remote output withheld.'
    }
    Write-GrantStageEvidence `
        -Stage remote_preflight_passed `
        -Status passed `
        -RemoteShellExitCode ([int]$zeroStateResult.exit_code)
    $remoteScript = New-CommunityRewardsExactW29GrantRemoteScript `
        -SchedulerContainer $layout.scheduler_service_name `
        -ExpectedSchedulerImageTag $ExpectedSchedulerImageTag `
        -ExpectedSchedulerImageId $ExpectedSchedulerImageId `
        -ExpectedRevision $ExpectedRevision `
        -OperationDirectory $remoteOperationDirectory `
        -OperationId $OperationId `
        -SnapshotFileSha256 '53c256c5517e4e9bfa9a1eaf80beeb910eb3a329cbfb3780072d7c2cb76b91cc' `
        -PreviewFileSha256 '8cefc8925b5b142c0e58f10ce04cd2d723102e9c554e1f2332240d63080ab0fa' `
        -ManifestFileSha256 '6d42e5bc7ac7c0494df3492fd480201a20b523ee2884b410edbdd2fc919b752d' `
        -CanonicalSnapshotSha256 $CanonicalSnapshotSha256 `
        -CanonicalPreviewSha256 $CanonicalPreviewSha256 `
        -WrapperSourceRevision $wrapperSourceRevision
    try {
        $result = Invoke-RemoteShellCommand `
            -SshAlias $layout.ssh_alias `
            -Name 'community_w29_exact_grant' `
            -ScriptText $remoteScript
    }
    catch {
        try {
            Write-GrantStageEvidence `
                -Stage child_launch_started `
                -Status failed `
                -LaunchCount $launchCount `
                -FailureCategory remote_shell
        }
        catch {
            # Preserve the original main-grant transport exception. A failed
            # diagnostic append never becomes the primary execution error.
        }
        throw
    }
    $grantRemoteExitCode = [int]$result.exit_code
    if ($result.exit_code -eq 0) { $launchCount = 1 }
    if ($result.exit_code -ne 0) {
        throw 'Exact W29 grant failed closed; recipient-level remote output withheld.'
    }
    [ordered]@{
        operation = 'exact_w29_grant'
        operation_id = $OperationId
        exact_image_tag = $ExpectedSchedulerImageTag
        exact_image_id = $ExpectedSchedulerImageId
        exact_revision = $ExpectedRevision
        canonical_snapshot_sha256 = $CanonicalSnapshotSha256
        canonical_preview_sha256 = $CanonicalPreviewSha256
        expected_claims = 21
        expected_components = 43
        expected_coins = 4060
        remote_result_received = $true
        recipient_output_emitted = $false
    } | ConvertTo-Json -Depth 4
}
finally {
    if ($lockHeld) {
        try {
            $null = Exit-RemoteReleaseOperationLock `
                -SshAlias $layout.ssh_alias `
                -LockPath $lockPath `
                -OperationId $releaseOperationId
        }
        catch {
            try {
                Write-GrantStageEvidence `
                    -Stage release_lock_released `
                    -Status failed `
                    -LaunchCount $launchCount `
                    -RemoteShellExitCode $grantRemoteExitCode `
                    -FailureCategory release_lock
            }
            catch {
                # Preserve the original lock-release failure. The earlier
                # invocation journal still proves the last completed stage.
            }
            throw
        }
        $lockHeld = $false
        Write-GrantStageEvidence `
            -Stage release_lock_released `
            -Status completed `
            -LaunchCount $launchCount `
            -RemoteShellExitCode $grantRemoteExitCode
    }
}
