#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidateSet('status','dry-run','enable-admin-only','disable','rollback','enable-allowlist')][string]$Operation,
    [string]$LayoutFile = 'deploy\release-layout.example.json',
    # Comma-separated canonical user IDs (decimal positive integers, ^[1-9][0-9]*$
    # each -- no leading zeros, no sign, no decimal point, no username/email text).
    # Required for -Operation enable-allowlist. Optional for -Operation dry-run:
    # when supplied, the dry-run previews enable-allowlist with these IDs instead
    # of the default enable-admin-only preview, preserving prior dry-run behavior
    # for anyone not passing it.
    [string]$AllowlistIds,
    [switch]$Execute,
    [string]$OwnerGate
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'ReleaseTooling.psm1') -Force -DisableNameChecking

# Mirrors scripts/release/e9_rollout_config.py's CANONICAL_USER_ID_PATTERN /
# parse_allowlist exactly (decimal positive integers, no leading zero, no
# sign, no decimal point, deduped) -- validated here, locally, before any
# remote call is opened, per the required "local validation before any
# remote mutation path" contract. The remote helper re-validates independently
# as defense in depth; neither side trusts the other's validation alone.
function Assert-CanonicalAllowlistIds {
    param([Parameter(Mandatory = $true)][string]$Raw)
    $entries = @($Raw -split ',' | ForEach-Object { $_.Trim() })
    if (-not $entries -or ($entries | Where-Object { [string]::IsNullOrEmpty($_) })) {
        throw 'Allowlist IDs must be a non-empty, comma-separated list with no empty entries.'
    }
    foreach ($entry in $entries) {
        if ($entry -notmatch '^[1-9][0-9]*$') {
            throw "Allowlist ID '$entry' is not a canonical positive decimal integer (no leading zero, sign, or decimal point)."
        }
    }
    $distinct = $entries | Select-Object -Unique
    if ($distinct.Count -ne $entries.Count) {
        throw 'Allowlist IDs must not contain duplicates.'
    }
    return ($entries | Sort-Object { [long]$_ }) -join ','
}

$repoRoot = Get-RepoRoot
$layout = Get-ReleaseLayout -Path (Resolve-RepoPath $LayoutFile)
if ($layout.production_env_path -ne '/opt/go-odyssey/.env') {
    throw 'E9 setter refuses any production env path other than /opt/go-odyssey/.env.'
}

$normalizedAllowlistIds = $null
if ($Operation -eq 'enable-allowlist') {
    if (-not $AllowlistIds) { throw 'enable-allowlist requires -AllowlistIds.' }
    $normalizedAllowlistIds = Assert-CanonicalAllowlistIds -Raw $AllowlistIds
} elseif ($Operation -eq 'dry-run' -and $AllowlistIds) {
    $normalizedAllowlistIds = Assert-CanonicalAllowlistIds -Raw $AllowlistIds
}

# GO_ENABLE_E9_ALLOWLIST is a distinct gate from GO_DEPLOY (finalized decision,
# not open for reinterpretation): GO_DEPLOY authorizes deploying an approved
# runtime/static version and says nothing about who is exposed to what;
# enable-allowlist changes which real, non-admin end users are exposed to E9
# on the same running image. A future action needing both a deploy and an
# allowlist enablement must be authorized under both gates explicitly -- one
# is never implied by the other.
if ($Operation -in @('enable-admin-only','disable','rollback')) {
    if (-not $Execute) { throw 'Mutating E9 operations require -Execute.' }
    Assert-OwnerGate -Provided $OwnerGate -Expected 'GO_DEPLOY'
} elseif ($Operation -eq 'enable-allowlist') {
    if (-not $Execute) { throw 'Mutating E9 operations require -Execute.' }
    Assert-OwnerGate -Provided $OwnerGate -Expected 'GO_ENABLE_E9_ALLOWLIST'
}

$helperPath = Join-Path $repoRoot 'scripts\release\e9_rollout_config.py'
$helper = Get-Content -Raw -LiteralPath $helperPath
$envPath = $layout.production_env_path
$envDir = $envPath.Substring(0, $envPath.LastIndexOf('/'))
$backupDir = "$envDir/.e9-rollout-backups"
$auditPath = "$($layout.remote_release_staging_directory.TrimEnd('/'))/e9-rollout-audit.jsonl"
$lockPath = "$envPath.e9-rollout.lock"
$operationArgs = "--operation $(Quote-PosixShellArgument $Operation) --env-path $(Quote-PosixShellArgument $envPath) --backup-dir $(Quote-PosixShellArgument $backupDir) --audit-path $(Quote-PosixShellArgument $auditPath) --lock-path $(Quote-PosixShellArgument $lockPath)"
if ($Operation -eq 'dry-run') {
    if ($normalizedAllowlistIds) {
        $operationArgs += " --desired enable-allowlist --allowlist $(Quote-PosixShellArgument $normalizedAllowlistIds)"
    } else {
        $operationArgs += ' --desired enable-admin-only'
    }
}
if ($Operation -eq 'enable-allowlist') {
    $operationArgs += " --allowlist $(Quote-PosixShellArgument $normalizedAllowlistIds)"
}

function Invoke-E9Helper {
    param([string]$ArgumentText)
    $remoteScript = "sudo -n python3 - $ArgumentText <<'__E9_ROLLOUT_HELPER__'`n$helper`n__E9_ROLLOUT_HELPER__"
    $result = Invoke-RemoteShellCommand -SshAlias $layout.ssh_alias -Name 'e9_rollout_config' -ScriptText $remoteScript
    if ($result.exit_code -ne 0) { throw "E9 setter failed closed: $($result.output)" }
    try { return ((Get-RemoteStandardOutput -Result $result) | ConvertFrom-Json) } catch { throw 'E9 setter returned invalid sanitized JSON.' }
}

function Invoke-E9ComposeRecreate {
    $composeDir = Quote-PosixShellArgument $layout.compose_directory
    $envFile = Quote-PosixShellArgument $envPath
    $releaseFile = Quote-PosixShellArgument "$($layout.compose_directory.TrimEnd('/'))/docker-compose.release.yml"
    $mountTemplate = "{{range .Mounts}}{{if eq .Destination `"$($layout.questions_content_mount_destination)`"}}{{.Name}}{{end}}{{end}}"
    $mountTemplateQuoted = Quote-PosixShellArgument $mountTemplate
    $command = "IMAGE=`$(docker inspect $($layout.app_service_name) --format '{{.Config.Image}}') && VOLUME=`$(docker inspect $($layout.app_service_name) --format $mountTemplateQuoted) && test -n `"`$IMAGE`" && test -n `"`$VOLUME`" && cd $composeDir && GO_ODYSSEY_IMAGE=`$IMAGE QUESTIONS_CONTENT_VOLUME_NAME=`$VOLUME QUESTIONS_CONTENT_MOUNT_DESTINATION=$(Quote-PosixShellArgument $layout.questions_content_mount_destination) ASSET_SOURCE_PATH=$(Quote-PosixShellArgument $layout.asset_source_path) ASSET_CONTAINER_MOUNT_DESTINATION=$(Quote-PosixShellArgument $layout.asset_container_mount_destination) SHADOW_EVENT_LOG_PATH=$(Quote-PosixShellArgument $layout.shadow_event_log_path) docker compose --env-file $envFile -f $releaseFile up -d --no-build --no-deps --force-recreate app scheduler && docker restart $($layout.nginx_service_name)"
    $result = Invoke-BoundedSshCommand -SshAlias $layout.ssh_alias -Command $command -TimeoutSeconds 180 -OperationLabel 'E9 rollout service recreate'
    if ($result.exit_code -ne 0 -or $result.timed_out) { throw "E9 service recreate failed closed: $($result.operation); diagnostic=$($result.output)" }
}

function Get-E9RuntimeHealth {
    function Read-RemoteHealthValue {
        param([string]$Name, [string]$Command)
        $probe = Invoke-RemoteShellCommand -SshAlias $layout.ssh_alias -Name $Name -Command $Command
        if ($probe.exit_code -ne 0) { throw "E9 health probe failed closed: $Name" }
        return $probe.output.Trim()
    }
    $appCommand = "docker inspect $($layout.app_service_name) --format '{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}n/a{{end}}'"
    $schedulerCommand = "docker inspect $($layout.scheduler_service_name) --format '{{.State.Status}}'"
    $nginxCommand = "docker inspect $($layout.nginx_service_name) --format '{{.State.Status}}'"
    $healthzCommand = "curl -sS -o /dev/null -w '%{http_code}' $(Quote-PosixShellArgument $layout.health_url)"
    $app = $scheduler = $nginx = $healthz = $null
    for ($attempt = 1; $attempt -le 18; $attempt++) {
        $app = Read-RemoteHealthValue 'e9_rollout_app_health' $appCommand
        $scheduler = Read-RemoteHealthValue 'e9_rollout_scheduler_health' $schedulerCommand
        $nginx = Read-RemoteHealthValue 'e9_rollout_nginx_health' $nginxCommand
        $healthz = Read-RemoteHealthValue 'e9_rollout_healthz' $healthzCommand
        if ($app -match '^running\|healthy$' -and $scheduler -eq 'running' -and $nginx -eq 'running' -and $healthz -eq '200') {
            return [ordered]@{ app = $app; scheduler = $scheduler; nginx = $nginx; healthz = $healthz; attempts = $attempt }
        }
        if ($app -match '^(exited|dead|running\|unhealthy)' -or $scheduler -ne 'running' -or $nginx -ne 'running' -or $healthz -ne '200') {
            throw "E9 post-change health gate failed closed: app=$app scheduler=$scheduler nginx=$nginx healthz=$healthz"
        }
        Start-Sleep -Seconds 5
    }
    throw "E9 post-change health gate timed out: app=$app scheduler=$scheduler nginx=$nginx healthz=$healthz"
}

function Get-E9RuntimeFlags {
    $command = 'for key in E9_ROLLOUT_GLOBAL_ENABLED E9_ROLLOUT_ADMIN_ENABLED E9_ROLLOUT_SCOPE E9_ROLLOUT_FLAGS E9_ROLLOUT_ALLOWLIST; do value=$(docker exec {0} printenv $key 2>/dev/null || true); printf ''%s=%s\n'' $key $value; done' -f $layout.app_service_name
    $result = Invoke-RemoteShellCommand -SshAlias $layout.ssh_alias -Name 'e9_rollout_runtime_flags' -Command $command
    if ($result.exit_code -ne 0) { throw 'E9 runtime flag query failed closed.' }
    $map = [ordered]@{}
    $expectedKeys = @('E9_ROLLOUT_GLOBAL_ENABLED','E9_ROLLOUT_ADMIN_ENABLED','E9_ROLLOUT_SCOPE','E9_ROLLOUT_FLAGS','E9_ROLLOUT_ALLOWLIST')
    foreach ($line in @($result.output -split "`r?`n" | Where-Object { $_ -ne '' })) {
        $pair = $line -split '=', 2
        if ($pair.Count -ne 2 -or $pair[0] -notin $expectedKeys) { throw 'E9 runtime flag output failed closed.' }
        $map[$pair[0]] = $pair[1]
    }
    # E9_ROLLOUT_ALLOWLIST legitimately prints as an empty value (key present,
    # value blank) via printenv when the container's environment has it set to
    # empty string -- still counts as present. A container built before this
    # revision's compose change would simply never emit the line at all.
    if ($map.Count -ne 5) { throw 'E9 runtime flags are incomplete (container image predates E9_ROLLOUT_ALLOWLIST compose wiring, or query failed).' }
    return $map
}

function Assert-E9RuntimeFlags {
    param([hashtable]$Flags, [string]$ExpectedOperation, [string]$ExpectedAllowlistIds)
    if ($Flags.E9_ROLLOUT_FLAGS -ne 'e9Shell,e9TopHud,e9LeftNav,e9RightCards,e9BottomDock,e9WorldStage') { throw 'E9 runtime flags failed closed.' }
    # Structural invariant that must hold regardless of which operation
    # produced the current state -- including 'rollback', which can restore
    # any prior governed snapshot and so has no single fixed target to
    # assert below. Mirrors app.py's own _e9_rollout_config() fail-closed
    # rule (`if raw_scope == 'admin_only' and entries: return None`):
    # admin_only scope must never coexist with a non-empty allowlist.
    if ($Flags.E9_ROLLOUT_SCOPE -eq 'admin_only' -and $Flags.E9_ROLLOUT_ALLOWLIST) {
        throw 'E9 runtime state failed closed: admin_only scope must never have a non-empty allowlist.'
    }
    if ($ExpectedOperation -eq 'enable-admin-only' -and ($Flags.E9_ROLLOUT_SCOPE -ne 'admin_only' -or $Flags.E9_ROLLOUT_GLOBAL_ENABLED -ne 'true' -or $Flags.E9_ROLLOUT_ADMIN_ENABLED -ne 'true')) { throw 'E9 admin-only runtime flags failed closed.' }
    # 'disable' also always targets admin_only scope (desired_for('disable')
    # sets it explicitly) -- this branch used to be covered for free by an
    # unconditional (pre-named_allowlist-era) top-level scope check; restored
    # here explicitly now that scope varies by operation.
    if ($ExpectedOperation -eq 'disable' -and ($Flags.E9_ROLLOUT_SCOPE -ne 'admin_only' -or $Flags.E9_ROLLOUT_GLOBAL_ENABLED -ne 'false' -or $Flags.E9_ROLLOUT_ADMIN_ENABLED -ne 'false')) { throw 'E9 disabled runtime flags failed closed.' }
    if ($ExpectedOperation -eq 'enable-allowlist') {
        if ($Flags.E9_ROLLOUT_SCOPE -ne 'named_allowlist' -or $Flags.E9_ROLLOUT_GLOBAL_ENABLED -ne 'true') { throw 'E9 allowlist runtime scope failed closed.' }
        if ($Flags.E9_ROLLOUT_ALLOWLIST -ne $ExpectedAllowlistIds) { throw "E9 allowlist runtime content failed closed: expected '$ExpectedAllowlistIds', got '$($Flags.E9_ROLLOUT_ALLOWLIST)'." }
    }
}

$result = Invoke-E9Helper -ArgumentText $operationArgs
if ($Operation -in @('enable-admin-only','disable','rollback','enable-allowlist')) {
    try {
        Invoke-E9ComposeRecreate
        $health = Get-E9RuntimeHealth
        $result | Add-Member -NotePropertyName health -NotePropertyValue $health
        $runtimeFlags = Get-E9RuntimeFlags
        Assert-E9RuntimeFlags -Flags $runtimeFlags -ExpectedOperation $Operation -ExpectedAllowlistIds $normalizedAllowlistIds
        $result | Add-Member -NotePropertyName runtime_flags -NotePropertyValue $runtimeFlags
    }
    catch {
        if ($Operation -eq 'enable-admin-only') {
            try {
                Invoke-E9Helper -ArgumentText ("--operation disable --env-path $(Quote-PosixShellArgument $envPath) --backup-dir $(Quote-PosixShellArgument $backupDir) --audit-path $(Quote-PosixShellArgument $auditPath) --lock-path $(Quote-PosixShellArgument $lockPath)") | Out-Null
                Invoke-E9ComposeRecreate
            } catch {}
        }
        if ($Operation -eq 'enable-allowlist') {
            # Restore the EXACT pre-operation rollout state from the operation's
            # own governed backup (scripts/release/e9_rollout_config.py's generic
            # `rollback` operation, already proven to restore prior bytes
            # byte-for-byte) -- never hard-code the fallback target to `disable`.
            # Production's pre-Phase-2 state is admin_only; a failed
            # enable-allowlist attempt must restore admin_only, not silently
            # drop existing admins to fully disabled.
            try {
                Invoke-E9Helper -ArgumentText ("--operation rollback --env-path $(Quote-PosixShellArgument $envPath) --backup-dir $(Quote-PosixShellArgument $backupDir) --audit-path $(Quote-PosixShellArgument $auditPath) --lock-path $(Quote-PosixShellArgument $lockPath)") | Out-Null
                Invoke-E9ComposeRecreate
            } catch {}
        }
        throw
    }
}
$result | ConvertTo-Json -Depth 12 | Write-Output
