#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidateSet('status','dry-run','enable-admin-only','disable','rollback')][string]$Operation,
    [string]$LayoutFile = 'deploy\release-layout.example.json',
    [switch]$Execute,
    [string]$OwnerGate
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'ReleaseTooling.psm1') -Force -DisableNameChecking

$repoRoot = Get-RepoRoot
$layout = Get-ReleaseLayout -Path (Resolve-RepoPath $LayoutFile)
if ($layout.production_env_path -ne '/opt/go-odyssey/.env') {
    throw 'E9 setter refuses any production env path other than /opt/go-odyssey/.env.'
}
if ($Operation -in @('enable-admin-only','disable','rollback')) {
    if (-not $Execute) { throw 'Mutating E9 operations require -Execute.' }
    Assert-OwnerGate -Provided $OwnerGate -Expected 'GO_DEPLOY'
}

$helperPath = Join-Path $repoRoot 'scripts\release\e9_rollout_config.py'
$helper = Get-Content -Raw -LiteralPath $helperPath
$envPath = $layout.production_env_path
$envDir = Split-Path -Parent $envPath
$backupDir = "$envDir/.e9-rollout-backups"
$auditPath = "$($layout.remote_release_staging_directory.TrimEnd('/'))/e9-rollout-audit.jsonl"
$lockPath = "$envPath.e9-rollout.lock"
$operationArgs = "--operation $(Quote-PosixShellArgument $Operation) --env-path $(Quote-PosixShellArgument $envPath) --backup-dir $(Quote-PosixShellArgument $backupDir) --audit-path $(Quote-PosixShellArgument $auditPath) --lock-path $(Quote-PosixShellArgument $lockPath)"
if ($Operation -eq 'dry-run') { $operationArgs += ' --desired enable-admin-only' }

function Invoke-E9Helper {
    param([string]$Args)
    $result = Invoke-RemoteShellCommand -SshAlias $layout.ssh_alias -Name 'e9_rollout_config' -Command "python3 - $Args" -StdinText $helper
    if ($result.exit_code -ne 0) { throw "E9 setter failed closed: $($result.output)" }
    try { return ($result.output | ConvertFrom-Json) } catch { throw 'E9 setter returned invalid sanitized JSON.' }
}

function Invoke-E9ComposeRecreate {
    $composeDir = Quote-PosixShellArgument $layout.compose_directory
    $envFile = Quote-PosixShellArgument $envPath
    $releaseFile = Quote-PosixShellArgument "$($layout.compose_directory.TrimEnd('/'))/docker-compose.release.yml"
    $command = "IMAGE=`$(docker inspect $($layout.app_service_name) --format '{{.Config.Image}}') && VOLUME=`$(docker inspect $($layout.app_service_name) --format '{{range .Mounts}}{{if eq .Destination '$($layout.questions_content_mount_destination)'}}{{.Name}}{{end}}{{end}}') && test -n `"`$IMAGE`" && test -n `"`$VOLUME`" && cd $composeDir && GO_ODYSSEY_IMAGE=`$IMAGE QUESTIONS_CONTENT_VOLUME_NAME=`$VOLUME QUESTIONS_CONTENT_MOUNT_DESTINATION=$(Quote-PosixShellArgument $layout.questions_content_mount_destination) ASSET_SOURCE_PATH=$(Quote-PosixShellArgument $layout.asset_source_path) ASSET_CONTAINER_MOUNT_DESTINATION=$(Quote-PosixShellArgument $layout.asset_container_mount_destination) SHADOW_EVENT_LOG_PATH=$(Quote-PosixShellArgument $layout.shadow_event_log_path) docker compose --env-file $envFile -f $releaseFile up -d --no-build --no-deps --force-recreate app scheduler && docker restart $($layout.nginx_service_name)"
    $result = Invoke-BoundedSshCommand -SshAlias $layout.ssh_alias -Command $command -TimeoutSeconds 180 -OperationLabel 'E9 rollout service recreate'
    if ($result.exit_code -ne 0 -or $result.timed_out) { throw "E9 service recreate failed closed: $($result.operation)" }
}

function Get-E9RuntimeHealth {
    $command = "docker inspect $($layout.app_service_name) --format '{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}n/a{{end}}'; docker inspect $($layout.scheduler_service_name) --format '{{.State.Status}}'; docker inspect $($layout.nginx_service_name) --format '{{.State.Status}}'; curl -sS -o /dev/null -w '%{http_code}' $(Quote-PosixShellArgument $layout.health_url)"
    $result = Invoke-RemoteShellCommand -SshAlias $layout.ssh_alias -Name 'e9_rollout_health' -Command $command
    if ($result.exit_code -ne 0) { throw 'E9 health query failed closed.' }
    $lines = @($result.output -split "`r?`n" | Where-Object { $_ -ne '' })
    if ($lines.Count -lt 4 -or $lines[0] -notmatch '^running\|healthy$' -or $lines[1] -ne 'running' -or $lines[2] -ne 'running' -or $lines[3] -ne '200') { throw 'E9 post-change health gate failed closed.' }
    return [ordered]@{ app = $lines[0]; scheduler = $lines[1]; nginx = $lines[2]; healthz = $lines[3] }
}

function Get-E9RuntimeFlags {
    $command = 'for key in E9_ROLLOUT_GLOBAL_ENABLED E9_ROLLOUT_ADMIN_ENABLED E9_ROLLOUT_SCOPE E9_ROLLOUT_FLAGS; do value=$(docker exec {0} printenv $key 2>/dev/null || true); printf ''%s=%s\n'' $key $value; done' -f $layout.app_service_name
    $result = Invoke-RemoteShellCommand -SshAlias $layout.ssh_alias -Name 'e9_rollout_runtime_flags' -Command $command
    if ($result.exit_code -ne 0) { throw 'E9 runtime flag query failed closed.' }
    $map = [ordered]@{}
    foreach ($line in @($result.output -split "`r?`n" | Where-Object { $_ -ne '' })) {
        $pair = $line -split '=', 2
        if ($pair.Count -ne 2 -or $pair[0] -notin @('E9_ROLLOUT_GLOBAL_ENABLED','E9_ROLLOUT_ADMIN_ENABLED','E9_ROLLOUT_SCOPE','E9_ROLLOUT_FLAGS')) { throw 'E9 runtime flag output failed closed.' }
        $map[$pair[0]] = $pair[1]
    }
    if ($map.Count -ne 4) { throw 'E9 runtime flags are incomplete.' }
    return $map
}

function Assert-E9RuntimeFlags {
    param([hashtable]$Flags, [string]$ExpectedOperation)
    if ($Flags.E9_ROLLOUT_SCOPE -ne 'admin_only' -or $Flags.E9_ROLLOUT_FLAGS -ne 'e9Shell,e9TopHud,e9LeftNav,e9RightCards,e9BottomDock,e9WorldStage') { throw 'E9 runtime scope/flags failed closed.' }
    if ($ExpectedOperation -eq 'enable-admin-only' -and ($Flags.E9_ROLLOUT_GLOBAL_ENABLED -ne 'true' -or $Flags.E9_ROLLOUT_ADMIN_ENABLED -ne 'true')) { throw 'E9 admin-only runtime flags failed closed.' }
    if ($ExpectedOperation -eq 'disable' -and ($Flags.E9_ROLLOUT_GLOBAL_ENABLED -ne 'false' -or $Flags.E9_ROLLOUT_ADMIN_ENABLED -ne 'false')) { throw 'E9 disabled runtime flags failed closed.' }
}

$result = Invoke-E9Helper -Args $operationArgs
if ($Operation -in @('enable-admin-only','disable','rollback')) {
    try {
        Invoke-E9ComposeRecreate
        $health = Get-E9RuntimeHealth
        $result | Add-Member -NotePropertyName health -NotePropertyValue $health
        $runtimeFlags = Get-E9RuntimeFlags
        Assert-E9RuntimeFlags -Flags $runtimeFlags -ExpectedOperation $Operation
        $result | Add-Member -NotePropertyName runtime_flags -NotePropertyValue $runtimeFlags
    }
    catch {
        if ($Operation -eq 'enable-admin-only') {
            try {
                Invoke-E9Helper -Args ("--operation disable --env-path $(Quote-PosixShellArgument $envPath) --backup-dir $(Quote-PosixShellArgument $backupDir) --audit-path $(Quote-PosixShellArgument $auditPath) --lock-path $(Quote-PosixShellArgument $lockPath)") | Out-Null
                Invoke-E9ComposeRecreate
            } catch {}
        }
        throw
    }
}
$result | ConvertTo-Json -Depth 12 | Write-Output
