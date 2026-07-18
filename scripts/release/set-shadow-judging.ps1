#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('status','dry-run','enable','disable','rollback')]
    [string]$Operation,

    [ValidateSet('enable','disable')]
    [string]$Desired = 'disable',

    [string]$LayoutFile = 'deploy\release-layout.example.json',
    [switch]$Execute,
    [string]$OwnerGate
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'ReleaseTooling.psm1') -Force -DisableNameChecking

$repoRoot = Get-RepoRoot
$layout = Get-ReleaseLayout -Path (Resolve-RepoPath $LayoutFile)
if ($layout.production_env_path -ne '/opt/go-odyssey/.env') {
    throw 'Shadow Judging setter refuses any production env path other than /opt/go-odyssey/.env.'
}

$mutationOperations = @('enable','disable','rollback')
$ownerGates = @{
    enable = 'GO_ENABLE_SHADOW'
    disable = 'GO_DISABLE_SHADOW'
    rollback = 'GO_SHADOW_ROLLBACK'
}
if ($Operation -in $mutationOperations) {
    if (-not $Execute) {
        throw 'Mutating Shadow Judging operations require -Execute.'
    }
    Assert-OwnerGate -Provided $OwnerGate -Expected $ownerGates[$Operation]
}

$helperPath = Join-Path $repoRoot 'scripts\release\shadow_judging_config.py'
$helperSource = Get-Content -Raw -LiteralPath $helperPath
if ($helperSource.Contains('__SHADOW_JUDGING_HELPER__')) {
    throw 'Shadow Judging helper contains the reserved transport delimiter.'
}

$envPath = [string]$layout.production_env_path
$envDirectory = $envPath.Substring(0, $envPath.LastIndexOf('/'))
$backupDirectory = "$envDirectory/.shadow-judging-backups"
$auditDirectory = "$($layout.remote_release_staging_directory.TrimEnd('/'))/.shadow-judging-audit"
$auditPath = "$auditDirectory/audit.jsonl"
$lockPath = "$envPath.shadow-judging.lock"

function Get-ShadowHelperArguments {
    param(
        [Parameter(Mandatory = $true)][string]$RequestedOperation,
        [string]$RequestedDesired,
        [string]$RequestedRollbackBackupId
    )

    $parts = @(
        '--operation', (Quote-PosixShellArgument $RequestedOperation),
        '--env-path', (Quote-PosixShellArgument $envPath),
        '--backup-dir', (Quote-PosixShellArgument $backupDirectory),
        '--audit-path', (Quote-PosixShellArgument $auditPath),
        '--lock-path', (Quote-PosixShellArgument $lockPath)
    )
    if ($RequestedOperation -eq 'dry-run') {
        $parts += @('--desired', (Quote-PosixShellArgument $RequestedDesired))
    }
    if ($RequestedOperation -eq 'rollback') {
        if ([string]::IsNullOrWhiteSpace($RequestedRollbackBackupId)) {
            throw 'Explicit rollback backup identity is required for governed recovery.'
        }
        $parts += @('--rollback-backup-id', (Quote-PosixShellArgument $RequestedRollbackBackupId))
    }
    if ($RequestedOperation -in $mutationOperations) {
        $parts += @('--execute', '--owner-gate', (Quote-PosixShellArgument $ownerGates[$RequestedOperation]))
    }
    return ($parts -join ' ')
}

function Invoke-ShadowHelper {
    param(
        [Parameter(Mandatory = $true)][string]$RequestedOperation,
        [string]$RequestedDesired = 'disable',
        [string]$RequestedRollbackBackupId
    )

    $argumentText = Get-ShadowHelperArguments -RequestedOperation $RequestedOperation -RequestedDesired $RequestedDesired -RequestedRollbackBackupId $RequestedRollbackBackupId
    $remoteScript = "set -eu`nsudo -n python3 - $argumentText <<'__SHADOW_JUDGING_HELPER__'`n$helperSource`n__SHADOW_JUDGING_HELPER__`n"
    $remote = Invoke-BoundedSshCommand `
        -SshAlias $layout.ssh_alias `
        -ScriptText $remoteScript `
        -TimeoutSeconds 60 `
        -OperationLabel "Shadow Judging $RequestedOperation helper"
    if ($remote.timed_out -or $remote.exit_code -ne 0) {
        throw "Shadow Judging $RequestedOperation helper failed closed; remote output withheld."
    }
    try {
        $payload = $remote.output | ConvertFrom-Json
    }
    catch {
        throw "Shadow Judging $RequestedOperation helper returned invalid sanitized JSON."
    }
    if (-not $payload -or $payload.operation -ne $RequestedOperation -or $payload.key -ne 'SHADOW_JUDGING_ENABLED') {
        throw "Shadow Judging $RequestedOperation helper response failed closed."
    }
    if (-not $payload.effective -or $null -eq $payload.effective.enabled) {
        throw "Shadow Judging $RequestedOperation helper omitted its effective state."
    }
    return $payload
}

function Invoke-ShadowComposeRecreate {
    $mountTemplate = "{{range .Mounts}}{{if and (eq .Destination `"$($layout.questions_content_mount_destination)`") (eq .Type `"volume`")}}{{println .Name}}{{end}}{{end}}"
    $scriptTemplate = @'
set -eu
APP_CONTAINER=__APP_CONTAINER__
SCHEDULER_CONTAINER=__SCHEDULER_CONTAINER__
COMPOSE_DIRECTORY=__COMPOSE_DIRECTORY__
COMPOSE_PROJECT=__COMPOSE_PROJECT__
ENV_PATH=__ENV_PATH__
RELEASE_FILE=__RELEASE_FILE__
QUESTIONS_DESTINATION=__QUESTIONS_DESTINATION__
ASSET_SOURCE=__ASSET_SOURCE__
ASSET_DESTINATION=__ASSET_DESTINATION__
SHADOW_EVENT_LOG=__SHADOW_EVENT_LOG__
MOUNT_TEMPLATE=__MOUNT_TEMPLATE__

APP_IMAGE=$(docker inspect "$APP_CONTAINER" --format '{{.Config.Image}}')
APP_IMAGE_ID=$(docker inspect "$APP_CONTAINER" --format '{{.Image}}')
SCHEDULER_IMAGE=$(docker inspect "$SCHEDULER_CONTAINER" --format '{{.Config.Image}}')
SCHEDULER_IMAGE_ID=$(docker inspect "$SCHEDULER_CONTAINER" --format '{{.Image}}')
RESOLVED_IMAGE_ID=$(docker image inspect "$APP_IMAGE" --format '{{.Id}}')
APP_PROJECT=$(docker inspect "$APP_CONTAINER" --format '{{index .Config.Labels "com.docker.compose.project"}}')
SCHEDULER_PROJECT=$(docker inspect "$SCHEDULER_CONTAINER" --format '{{index .Config.Labels "com.docker.compose.project"}}')
APP_SERVICE=$(docker inspect "$APP_CONTAINER" --format '{{index .Config.Labels "com.docker.compose.service"}}')
SCHEDULER_SERVICE=$(docker inspect "$SCHEDULER_CONTAINER" --format '{{index .Config.Labels "com.docker.compose.service"}}')
test -n "$APP_IMAGE"
test -n "$APP_IMAGE_ID"
test "$APP_IMAGE" = "$SCHEDULER_IMAGE"
test "$APP_IMAGE_ID" = "$SCHEDULER_IMAGE_ID"
test "$APP_IMAGE_ID" = "$RESOLVED_IMAGE_ID"
test "$APP_PROJECT" = "$COMPOSE_PROJECT"
test "$SCHEDULER_PROJECT" = "$COMPOSE_PROJECT"
test "$APP_SERVICE" = "app"
test "$SCHEDULER_SERVICE" = "scheduler"

APP_VOLUME=$(docker inspect "$APP_CONTAINER" --format "$MOUNT_TEMPLATE")
SCHEDULER_VOLUME=$(docker inspect "$SCHEDULER_CONTAINER" --format "$MOUNT_TEMPLATE")
test -n "$APP_VOLUME"
test "$APP_VOLUME" = "$SCHEDULER_VOLUME"
test "$(printf '%s\n' "$APP_VOLUME" | wc -l | tr -d ' ')" -eq 1

cd "$COMPOSE_DIRECTORY"
GO_ODYSSEY_IMAGE="$APP_IMAGE" \
QUESTIONS_CONTENT_VOLUME_NAME="$APP_VOLUME" \
QUESTIONS_CONTENT_MOUNT_DESTINATION="$QUESTIONS_DESTINATION" \
ASSET_SOURCE_PATH="$ASSET_SOURCE" \
ASSET_CONTAINER_MOUNT_DESTINATION="$ASSET_DESTINATION" \
SHADOW_EVENT_LOG_PATH="$SHADOW_EVENT_LOG" \
docker compose -p "$COMPOSE_PROJECT" --env-file "$ENV_PATH" -f "$RELEASE_FILE" \
    up -d --no-build --no-deps --force-recreate app scheduler

NEW_APP_IMAGE_ID=$(docker inspect "$APP_CONTAINER" --format '{{.Image}}')
NEW_SCHEDULER_IMAGE_ID=$(docker inspect "$SCHEDULER_CONTAINER" --format '{{.Image}}')
NEW_APP_VOLUME=$(docker inspect "$APP_CONTAINER" --format "$MOUNT_TEMPLATE")
NEW_SCHEDULER_VOLUME=$(docker inspect "$SCHEDULER_CONTAINER" --format "$MOUNT_TEMPLATE")
test "$NEW_APP_IMAGE_ID" = "$APP_IMAGE_ID"
test "$NEW_SCHEDULER_IMAGE_ID" = "$APP_IMAGE_ID"
test "$NEW_APP_VOLUME" = "$APP_VOLUME"
test "$NEW_SCHEDULER_VOLUME" = "$APP_VOLUME"
'@
    $remoteScript = $scriptTemplate
    $replacements = [ordered]@{
        '__APP_CONTAINER__' = Quote-PosixShellArgument ([string]$layout.app_service_name)
        '__SCHEDULER_CONTAINER__' = Quote-PosixShellArgument ([string]$layout.scheduler_service_name)
        '__COMPOSE_DIRECTORY__' = Quote-PosixShellArgument ([string]$layout.compose_directory)
        '__COMPOSE_PROJECT__' = Quote-PosixShellArgument ([string]$layout.compose_project)
        '__ENV_PATH__' = Quote-PosixShellArgument $envPath
        '__RELEASE_FILE__' = Quote-PosixShellArgument "$($layout.compose_directory.TrimEnd('/'))/docker-compose.release.yml"
        '__QUESTIONS_DESTINATION__' = Quote-PosixShellArgument ([string]$layout.questions_content_mount_destination)
        '__ASSET_SOURCE__' = Quote-PosixShellArgument ([string]$layout.asset_source_path)
        '__ASSET_DESTINATION__' = Quote-PosixShellArgument ([string]$layout.asset_container_mount_destination)
        '__SHADOW_EVENT_LOG__' = Quote-PosixShellArgument ([string]$layout.shadow_event_log_path)
        '__MOUNT_TEMPLATE__' = Quote-PosixShellArgument $mountTemplate
    }
    foreach ($replacement in $replacements.GetEnumerator()) {
        $remoteScript = $remoteScript.Replace($replacement.Key, $replacement.Value)
    }

    $remote = Invoke-BoundedSshCommand `
        -SshAlias $layout.ssh_alias `
        -ScriptText $remoteScript `
        -TimeoutSeconds 180 `
        -OperationLabel 'Shadow Judging exact-image app and scheduler recreate'
    if ($remote.timed_out -or $remote.exit_code -ne 0) {
        throw 'Shadow Judging service recreate failed closed; remote output withheld.'
    }
}

function Get-ShadowRuntimeFlag {
    param([string]$AppContainerId, [string]$SchedulerContainerId)
    $appJson = ConvertTo-Json -Compress -InputObject ([string]$layout.app_service_name)
    $schedulerJson = ConvertTo-Json -Compress -InputObject ([string]$layout.scheduler_service_name)
    $scriptTemplate = @'
set -eu
python3 - <<'__SHADOW_RUNTIME_FLAG__'
import json
import subprocess
import sys

KEY = "SHADOW_JUDGING_ENABLED"
APP = __APP_JSON__
SCHEDULER = __SCHEDULER_JSON__
TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"", "0", "false", "no", "off"}


def probe(container):
    try:
        result = subprocess.run(
            ["docker", "exec", container, "printenv", KEY],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"state": "probe_failed_closed", "enabled": False}
    if result.returncode != 0:
        return {"state": "missing_fail_closed", "enabled": False}
    value = result.stdout.rstrip("\r\n")
    if "\r" in value or "\n" in value or "\x00" in value:
        return {"state": "invalid_fail_closed", "enabled": False}
    normalized = value.strip().lower()
    if normalized in TRUE_VALUES:
        return {"state": "enabled", "enabled": True}
    if normalized in FALSE_VALUES:
        return {"state": "disabled", "enabled": False}
    return {"state": "invalid_fail_closed", "enabled": False}


app = probe(APP)
scheduler = probe(SCHEDULER)
if app["state"] in {"probe_failed_closed", "missing_fail_closed"} or scheduler["state"] in {"probe_failed_closed", "missing_fail_closed"}:
    print(json.dumps({"status": "fail", "reason": "runtime_probe_failed_closed"}, sort_keys=True, separators=(",", ":")))
    sys.exit(1)
payload = {"status": "ok", "key": KEY, "app": app, "scheduler": scheduler}
print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
sys.exit(0)
__SHADOW_RUNTIME_FLAG__
'@
    if (-not [string]::IsNullOrWhiteSpace($AppContainerId)) { $appJson = ConvertTo-Json -Compress -InputObject $AppContainerId }
    if (-not [string]::IsNullOrWhiteSpace($SchedulerContainerId)) { $schedulerJson = ConvertTo-Json -Compress -InputObject $SchedulerContainerId }
    $remoteScript = $scriptTemplate.Replace('__APP_JSON__', $appJson).Replace('__SCHEDULER_JSON__', $schedulerJson)
    $remote = Invoke-BoundedSshCommand `
        -SshAlias $layout.ssh_alias `
        -ScriptText $remoteScript `
        -TimeoutSeconds 30 `
        -OperationLabel 'Shadow Judging normalized runtime flag probe'
    if ($remote.timed_out -or $remote.exit_code -ne 0) {
        throw 'Shadow Judging runtime flag probe failed closed; remote output withheld.'
    }
    try {
        $payload = $remote.output | ConvertFrom-Json
    }
    catch {
        throw 'Shadow Judging runtime flag probe returned invalid sanitized JSON.'
    }
    if ($payload.status -ne 'ok' -or $payload.key -ne 'SHADOW_JUDGING_ENABLED' -or -not $payload.app -or -not $payload.scheduler) {
        throw 'Shadow Judging runtime flag probe response failed closed.'
    }
    return $payload
}

function Assert-ShadowRuntimeFlag {
    param(
        [Parameter(Mandatory = $true)]$Runtime,
        [Parameter(Mandatory = $true)]$HelperResult,
        [Parameter(Mandatory = $true)][string]$ExpectedOperation
    )

    $expectedEnabled = [bool]$HelperResult.effective.enabled
    if ([bool]$Runtime.app.enabled -ne [bool]$Runtime.scheduler.enabled) {
        throw 'Shadow Judging app and scheduler runtime flags disagree.'
    }
    if ($Runtime.app.state -ne $Runtime.scheduler.state) {
        throw 'Shadow Judging app and scheduler normalized runtime states disagree.'
    }
    if ($Runtime.app.state -notin @('enabled','disabled','invalid_fail_closed')) {
        throw 'Shadow Judging runtime flag state failed closed.'
    }
    if ([bool]$Runtime.app.enabled -ne $expectedEnabled) {
        throw 'Shadow Judging runtime flag does not match the governed configuration.'
    }
    if ($ExpectedOperation -eq 'enable' -and ($Runtime.app.state -ne 'enabled' -or $Runtime.scheduler.state -ne 'enabled')) {
        throw 'Shadow Judging enable did not converge to the canonical enabled runtime state.'
    }
    if ($ExpectedOperation -eq 'disable' -and ($Runtime.app.state -ne 'disabled' -or $Runtime.scheduler.state -ne 'disabled')) {
        throw 'Shadow Judging disable did not converge to the canonical disabled runtime state.'
    }
}

function Get-ShadowRuntimeHealth {
    $appJson = ConvertTo-Json -Compress -InputObject ([string]$layout.app_service_name)
    $schedulerJson = ConvertTo-Json -Compress -InputObject ([string]$layout.scheduler_service_name)
    $nginxJson = ConvertTo-Json -Compress -InputObject ([string]$layout.nginx_service_name)
    $healthUrlJson = ConvertTo-Json -Compress -InputObject ([string]$layout.health_url)
    $scriptTemplate = @'
set -eu
python3 - <<'__SHADOW_RUNTIME_HEALTH__'
import json
import subprocess
import sys
import time
import urllib.request

APP = __APP_JSON__
SCHEDULER = __SCHEDULER_JSON__
NGINX = __NGINX_JSON__
HEALTH_URL = __HEALTH_URL_JSON__


def container_state(name):
    try:
        result = subprocess.run(
            ["docker", "inspect", name, "--format", "{{json .}}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode != 0:
            return {"id": "", "image_id": "", "status": "probe_failed", "health": "probe_failed"}
        state = json.loads(result.stdout)
        health = (state.get("State") or {}).get("Health") or {}
        return {
            "id": str(state.get("Id") or ""),
            "image_id": str(state.get("Image") or ""),
            "status": str(state.get("State", {}).get("Status") or "unknown"),
            "health": str(health.get("Status") or "n/a"),
        }
    except (OSError, ValueError, TypeError, subprocess.TimeoutExpired):
        return {"id": "", "image_id": "", "status": "probe_failed", "health": "probe_failed"}


def healthz_status():
    try:
        request = urllib.request.Request(HEALTH_URL, method="GET")
        with urllib.request.urlopen(request, timeout=5) as response:
            if response.geturl() != HEALTH_URL:
                return 0
            return int(response.status)
    except Exception:
        return 0


deadline = time.monotonic() + 105
attempt = 0
last = None
while time.monotonic() < deadline:
    attempt += 1
    app = container_state(APP)
    scheduler = container_state(SCHEDULER)
    nginx = container_state(NGINX)
    healthz = healthz_status()
    last = {
        "app": f"{app['status']}|{app['health']}",
        "scheduler": scheduler["status"],
        "nginx": nginx["status"],
        "app_container_id": app["id"],
        "scheduler_container_id": scheduler["id"],
        "app_image_id": app["image_id"],
        "scheduler_image_id": scheduler["image_id"],
        "healthz": healthz,
        "attempts": attempt,
    }
    if app["status"] == "running" and app["health"] == "healthy" and scheduler["status"] == "running" and nginx["status"] == "running" and healthz == 200:
        print(json.dumps({"status": "ok", **last}, sort_keys=True, separators=(",", ":")))
        sys.exit(0)
    if app["status"] in {"dead", "exited"} or scheduler["status"] in {"dead", "exited"} or nginx["status"] in {"dead", "exited"}:
        print(json.dumps({"status": "fail", "reason": "terminal_container_state", **last}, sort_keys=True, separators=(",", ":")))
        sys.exit(1)
    time.sleep(5)

print(json.dumps({"status": "fail", "reason": "health_timeout", **(last or {"attempts": attempt})}, sort_keys=True, separators=(",", ":")))
sys.exit(1)
__SHADOW_RUNTIME_HEALTH__
'@
    $remoteScript = $scriptTemplate.Replace('__APP_JSON__', $appJson).Replace('__SCHEDULER_JSON__', $schedulerJson).Replace('__NGINX_JSON__', $nginxJson).Replace('__HEALTH_URL_JSON__', $healthUrlJson)
    $remote = Invoke-BoundedSshCommand `
        -SshAlias $layout.ssh_alias `
        -ScriptText $remoteScript `
        -TimeoutSeconds 125 `
        -OperationLabel 'Shadow Judging post-change health convergence'
    if ($remote.timed_out -or $remote.exit_code -ne 0) {
        throw 'Shadow Judging post-change health gate failed closed; remote output withheld.'
    }
    try {
        $payload = $remote.output | ConvertFrom-Json
    }
    catch {
        throw 'Shadow Judging health gate returned invalid sanitized JSON.'
    }
    if ($payload.status -ne 'ok' -or $payload.app -ne 'running|healthy' -or $payload.scheduler -ne 'running' -or $payload.nginx -ne 'running' -or [int]$payload.healthz -ne 200) {
        throw 'Shadow Judging health gate response failed closed.'
    }
    return $payload
}

function Wait-ShadowPostChangeConvergence {
    param(
        [Parameter(Mandatory = $true)]$HelperResult,
        [Parameter(Mandatory = $true)][ValidateSet('enable','disable')][string]$ExpectedOperation,
        [Parameter(Mandatory = $true)]$BeforeHealth,
        [int]$DeadlineSeconds = 105,
        [int]$PollIntervalSeconds = 3
    )
    $started = Get-Date
    $attempt = 0
    $lastHealth = $null
    $lastRuntime = $null
    $lastError = $null
    do {
        $attempt++
        $attemptHealth = $null
        $attemptRuntime = $null
        $attemptRecheck = $null
        $attemptAppId = $null
        $attemptSchedulerId = $null
        $attemptIdentityStable = $false
        $attemptFailureCode = $null
        $attemptFailureMessage = $null
        try {
            $attemptHealth = Get-ShadowRuntimeHealth
            $appId = [string]$attemptHealth.app_container_id
            $schedulerId = [string]$attemptHealth.scheduler_container_id
            $attemptAppId = $appId
            $attemptSchedulerId = $schedulerId
            if ([string]::IsNullOrWhiteSpace($appId) -or [string]::IsNullOrWhiteSpace($schedulerId) -or
                $appId -eq [string]$BeforeHealth.app_container_id -or $schedulerId -eq [string]$BeforeHealth.scheduler_container_id) { throw 'Current container identity has not converged.' }
            if ([string]$lastHealth.app_image_id -ne [string]$BeforeHealth.app_image_id -or [string]$lastHealth.scheduler_image_id -ne [string]$BeforeHealth.scheduler_image_id) { throw 'Container image identity changed unexpectedly.' }
            $attemptRuntime = Get-ShadowRuntimeFlag -AppContainerId $appId -SchedulerContainerId $schedulerId
            $attemptRecheck = Get-ShadowRuntimeHealth
            if ([string]$attemptRecheck.app_container_id -ne $appId -or [string]$attemptRecheck.scheduler_container_id -ne $schedulerId) { throw 'Container identity changed during convergence sample.' }
            $attemptIdentityStable = $true
            $lastHealth = $attemptRecheck
            $lastRuntime = $attemptRuntime
            Assert-ShadowRuntimeFlag -Runtime $lastRuntime -HelperResult $HelperResult -ExpectedOperation $ExpectedOperation
            return [pscustomobject]@{ health = $lastHealth; runtime = $lastRuntime; attempts = $attempt; elapsed_seconds = [math]::Round(((Get-Date) - $started).TotalSeconds, 3) }
        }
        catch {
            $lastError = $_.Exception.Message
            $attemptFailureCode = [string]$_.FullyQualifiedErrorId
            $attemptFailureMessage = [string]$_.Exception.Message
            $lastHealth = $attemptHealth
            $lastRuntime = $attemptRuntime
        }
        if (((Get-Date) - $started).TotalSeconds -ge $DeadlineSeconds) { break }
        Start-Sleep -Seconds $PollIntervalSeconds
    } while ($true)
    $message = "Shadow Judging post-change convergence failed after $attempt attempt(s): $lastError"
    $errorRecord = New-Object System.Management.Automation.ErrorRecord ([Exception]::new($message)), 'shadow_convergence_timeout', ([System.Management.Automation.ErrorCategory]::OperationTimeout), $null
    $errorRecord.ErrorDetails = [System.Management.Automation.ErrorDetails]::new(($lastRuntime | ConvertTo-Json -Compress -Depth 6))
    $errorRecord.Data['attempts'] = $attempt
    $errorRecord.Data['elapsed_seconds'] = [math]::Round(((Get-Date) - $started).TotalSeconds, 3)
    $errorRecord.Data['runtime'] = $lastRuntime
    $errorRecord.Data['health'] = $lastHealth
    $errorRecord.Data['app_id'] = $attemptAppId
    $errorRecord.Data['scheduler_id'] = $attemptSchedulerId
    $errorRecord.Data['identity_stable'] = $attemptIdentityStable
    $errorRecord.Data['failure_code'] = $attemptFailureCode
    $errorRecord.Data['failure_message'] = $attemptFailureMessage
    throw $errorRecord
}

$result = $null
$postChangeDiagnostics = $null
$result = Invoke-ShadowHelper -RequestedOperation $Operation -RequestedDesired $Desired
if ($Operation -in $mutationOperations) {
    try {
        $beforeHealth = Get-ShadowRuntimeHealth
        Invoke-ShadowComposeRecreate
        $postChangeDiagnostics = Wait-ShadowPostChangeConvergence -HelperResult $result -ExpectedOperation $Operation -BeforeHealth $beforeHealth
        $result | Add-Member -NotePropertyName health -NotePropertyValue $postChangeDiagnostics.health
        $result | Add-Member -NotePropertyName runtime -NotePropertyValue $postChangeDiagnostics.runtime
        $result | Add-Member -NotePropertyName verification_attempt_count -NotePropertyValue $postChangeDiagnostics.attempts
        $result | Add-Member -NotePropertyName verification_elapsed_seconds -NotePropertyValue $postChangeDiagnostics.elapsed_seconds
        $result | Add-Member -NotePropertyName app_container_identity_before -NotePropertyValue ([string]$beforeHealth.app_container_id)
        $result | Add-Member -NotePropertyName app_container_identity_after -NotePropertyValue ([string]$postChangeDiagnostics.health.app_container_id)
        $result | Add-Member -NotePropertyName scheduler_container_identity_before -NotePropertyValue ([string]$beforeHealth.scheduler_container_id)
        $result | Add-Member -NotePropertyName scheduler_container_identity_after -NotePropertyValue ([string]$postChangeDiagnostics.health.scheduler_container_id)
        $result | Add-Member -NotePropertyName expected_app_image_id -NotePropertyValue ([string]$beforeHealth.app_image_id)
        $result | Add-Member -NotePropertyName expected_scheduler_image_id -NotePropertyValue ([string]$beforeHealth.scheduler_image_id)
        $result | Add-Member -NotePropertyName observed_app_image_id -NotePropertyValue ([string]$postChangeDiagnostics.health.app_image_id)
        $result | Add-Member -NotePropertyName observed_scheduler_image_id -NotePropertyValue ([string]$postChangeDiagnostics.health.scheduler_image_id)
    }
    catch {
        $postChangeError = $_
        if ($postChangeError.Exception.Data['attempts']) {
            $postChangeDiagnostics = [pscustomobject]@{
                attempts = [int]$postChangeError.Exception.Data['attempts']
                elapsed_seconds = [double]$postChangeError.Exception.Data['elapsed_seconds']
                runtime = $postChangeError.Exception.Data['runtime']
                health = $postChangeError.Exception.Data['health']
                app_id = $postChangeError.Exception.Data['app_id']
                scheduler_id = $postChangeError.Exception.Data['scheduler_id']
                identity_stable = [bool]$postChangeError.Exception.Data['identity_stable']
            }
        }
        $recoverySucceeded = $false
        try {
            if (-not $result -or -not $result.backup -or [string]::IsNullOrWhiteSpace([string]$result.backup.id)) {
                throw 'Shadow Judging mutation did not return an exact recovery backup identity.'
            }
            $recovery = Invoke-ShadowHelper -RequestedOperation 'rollback' -RequestedRollbackBackupId ([string]$result.backup.id)
            Invoke-ShadowComposeRecreate
            $recoveryHealth = Get-ShadowRuntimeHealth
            $recoveryRuntime = Get-ShadowRuntimeFlag
            Assert-ShadowRuntimeFlag -Runtime $recoveryRuntime -HelperResult $recovery -ExpectedOperation 'rollback'
            $recoverySucceeded = $true
        }
        catch {
            $recoverySucceeded = $false
        }
        if ($recoverySucceeded) {
            # The governed pre-change state was restored and verified; report the original failure.
            [ordered]@{
                operation = $Operation
                status = 'recovered_failure'
                internal_recovery_attempted = $true
                internal_recovery_succeeded = $true
                backup = $result.backup
                recovery = $recovery
                effective = $recovery.effective
                health = $recoveryHealth
                runtime = $recoveryRuntime
                original_failure_stage = 'post_change_verification'
                original_failure_code = [string]$postChangeError.FullyQualifiedErrorId
                original_failure_message = [string]$postChangeError.Exception.Message
                expected_app_state = [string]$result.effective.state
                expected_scheduler_state = [string]$result.effective.state
                observed_app_state = if ($postChangeDiagnostics) { [string]$postChangeDiagnostics.runtime.app.state } else { $null }
                observed_scheduler_state = if ($postChangeDiagnostics) { [string]$postChangeDiagnostics.runtime.scheduler.state } else { $null }
                verification_attempt_count = if ($postChangeDiagnostics) { $postChangeDiagnostics.attempts } else { $null }
                verification_elapsed_seconds = if ($postChangeDiagnostics) { $postChangeDiagnostics.elapsed_seconds } else { $null }
                final_verified_state = [string]$recovery.effective.state
                recovery_backup_id = [string]$result.backup.id
                lock_cleanup_result = 'governed_helper_cleanup'
                app_container_identity_before = [string]$beforeHealth.app_container_id
                app_container_identity_after = if ($postChangeDiagnostics) { [string]$postChangeDiagnostics.health.app_container_id } else { $null }
                scheduler_container_identity_before = [string]$beforeHealth.scheduler_container_id
                scheduler_container_identity_after = if ($postChangeDiagnostics) { [string]$postChangeDiagnostics.health.scheduler_container_id } else { $null }
                last_observed_app_container_identity = if ($postChangeDiagnostics) { [string]$postChangeDiagnostics.runtime.app_container_id } else { $null }
                last_observed_scheduler_container_identity = if ($postChangeDiagnostics) { [string]$postChangeDiagnostics.runtime.scheduler_container_id } else { $null }
                identity_stable_during_last_sample = if ($postChangeDiagnostics) { $true } else { $false }
            } | ConvertTo-Json -Depth 12 | Write-Output
            exit 1
        }
        throw 'Shadow Judging post-change verification failed; governed recovery also failed closed and requires owner review.'
    }
}

$result | ConvertTo-Json -Depth 12 | Write-Output
