#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidateSet('resume')][string]$Operation,
    [Parameter(Mandatory = $true)][string]$ExpectedSchedulerImageTag,
    [Parameter(Mandatory = $true)][string]$ExpectedSchedulerImageId,
    [string]$LayoutFile = 'deploy\release-layout.example.json',
    [switch]$Execute,
    [string]$OwnerGate
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'ReleaseTooling.psm1') -Force -DisableNameChecking
Import-Module (Join-Path $PSScriptRoot 'CommunityRewardsExecutionControl.psm1') -Force -DisableNameChecking
$repoRoot = Get-RepoRoot
$layout = Get-ReleaseLayout -Path (Resolve-RepoPath $LayoutFile)

if (-not $Execute) { throw 'Community rewards resume requires -Execute.' }
Assert-OwnerGate -Provided $OwnerGate -Expected 'GO_GRANT_W29'
if ([string]::IsNullOrWhiteSpace($ExpectedSchedulerImageTag) -or [string]::IsNullOrWhiteSpace($ExpectedSchedulerImageId)) {
    throw 'Community rewards resume requires exact scheduler image tag and ID.'
}

function Invoke-RemoteText([string]$Command) {
    $result = Invoke-RemoteShellCommand -SshAlias $layout.ssh_alias -Name 'community_rewards_resume_probe' -Command $Command
    if ($result.exit_code -ne 0) { throw 'Community rewards resume probe failed closed; remote output withheld.' }
    return (Get-RemoteStandardOutput -Result $result)
}

$operationId = "community-resume-$([Guid]::NewGuid().ToString('N'))"
$lockPath = "$($layout.compose_directory.TrimEnd('/'))/.release-operation.lock"
$lockHeld = $false
try {
    $null = Enter-RemoteReleaseOperationLock -SshAlias $layout.ssh_alias -LockPath $lockPath -OperationId $operationId
    $lockHeld = $true
    $scheduler = Quote-PosixShellArgument $layout.scheduler_service_name
    $actualTag = (Invoke-RemoteText "docker inspect $scheduler --format '{{.Config.Image}}'").Trim()
    $actualId = (Invoke-RemoteText "docker inspect $scheduler --format '{{.Image}}'").Trim()
    if ($actualTag -ne $ExpectedSchedulerImageTag -or $actualId -ne $ExpectedSchedulerImageId) {
        throw 'Community rewards resume scheduler identity differs from the explicit authorization.'
    }
    $mountTemplate = "{{range .Mounts}}{{if and (eq .Destination `"$($layout.questions_content_mount_destination)`") (eq .Type `"volume`")}}{{println .Name}}{{end}}{{end}}"
    $volume = (Invoke-RemoteText "docker inspect $scheduler --format $(Quote-PosixShellArgument $mountTemplate)").Trim()
    if ([string]::IsNullOrWhiteSpace($volume) -or $volume.Contains("`n")) { throw 'Community rewards resume could not resolve one exact questions volume.' }
    $pairs = [ordered]@{
        GO_ODYSSEY_IMAGE = $actualTag
        QUESTIONS_CONTENT_VOLUME_NAME = $volume
        QUESTIONS_CONTENT_MOUNT_DESTINATION = $layout.questions_content_mount_destination
        ASSET_SOURCE_PATH = $layout.asset_source_path
        ASSET_CONTAINER_MOUNT_DESTINATION = $layout.asset_container_mount_destination
        SHADOW_EVENT_LOG_PATH = $layout.shadow_event_log_path
    }
    $prefix = (($pairs.GetEnumerator() | ForEach-Object { "{0}={1}" -f $_.Key, (Quote-PosixShellArgument ([string]$_.Value)) }) -join ' ')
    $script = New-CommunityRewardsResumeRemoteScript `
        -SchedulerContainer $layout.scheduler_service_name `
        -AppContainer $layout.app_service_name `
        -ExpectedSchedulerImageId $actualId `
        -ExpectedSchedulerImageTag $actualTag `
        -ComposeDirectory $layout.compose_directory `
        -ComposeProject $layout.compose_project `
        -ComposeFile "$($layout.compose_directory.TrimEnd('/'))/docker-compose.release.yml" `
        -EnvFile $layout.production_env_path `
        -SchedulerService 'scheduler' `
        -ComposeEnvironmentPrefix $prefix
    $result = Invoke-RemoteShellCommand -SshAlias $layout.ssh_alias -Name 'community_rewards_resume' -ScriptText $script
    if ($result.exit_code -ne 0) { throw 'Community rewards resume failed closed; remote output withheld.' }
    [ordered]@{
        operation = 'resume'
        success = $true
        scheduler_image_tag = $actualTag
        scheduler_image_id = $actualId
        configured_value_restored = $true
        reward_operation_performed = $false
    } | ConvertTo-Json -Depth 4
}
finally {
    if ($lockHeld) { $null = Exit-RemoteReleaseOperationLock -SshAlias $layout.ssh_alias -LockPath $lockPath -OperationId $operationId }
}
