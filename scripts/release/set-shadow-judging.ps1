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
if ($Operation -in $mutationOperations) {
    if (-not $Execute) {
        throw 'Mutating Shadow Judging operations require -Execute.'
    }
    Assert-OwnerGate -Provided $OwnerGate -Expected 'GO_DEPLOY'
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
        [string]$RequestedDesired
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
    if ($RequestedOperation -in $mutationOperations) {
        $parts += @('--execute', '--owner-gate', (Quote-PosixShellArgument 'GO_DEPLOY'))
    }
    return ($parts -join ' ')
}

function Invoke-ShadowHelper {
    param(
        [Parameter(Mandatory = $true)][string]$RequestedOperation,
        [string]$RequestedDesired = 'disable'
    )

    $argumentText = Get-ShadowHelperArguments -RequestedOperation $RequestedOperation -RequestedDesired $RequestedDesired
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
            ["docker", "inspect", name, "--format", "{{json .State}}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode != 0:
            return "probe_failed", "probe_failed"
        state = json.loads(result.stdout)
        health = state.get("Health") or {}
        return str(state.get("Status") or "unknown"), str(health.get("Status") or "n/a")
    except (OSError, ValueError, TypeError, subprocess.TimeoutExpired):
        return "probe_failed", "probe_failed"


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
    app_status, app_health = container_state(APP)
    scheduler_status, _scheduler_health = container_state(SCHEDULER)
    nginx_status, _nginx_health = container_state(NGINX)
    healthz = healthz_status()
    last = {
        "app": f"{app_status}|{app_health}",
        "scheduler": scheduler_status,
        "nginx": nginx_status,
        "healthz": healthz,
        "attempts": attempt,
    }
    if app_status == "running" and app_health == "healthy" and scheduler_status == "running" and nginx_status == "running" and healthz == 200:
        print(json.dumps({"status": "ok", **last}, sort_keys=True, separators=(",", ":")))
        sys.exit(0)
    if app_status in {"dead", "exited"} or scheduler_status in {"dead", "exited"} or nginx_status in {"dead", "exited"}:
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

$result = Invoke-ShadowHelper -RequestedOperation $Operation -RequestedDesired $Desired
if ($Operation -in $mutationOperations) {
    try {
        Invoke-ShadowComposeRecreate
        $health = Get-ShadowRuntimeHealth
        $runtime = Get-ShadowRuntimeFlag
        Assert-ShadowRuntimeFlag -Runtime $runtime -HelperResult $result -ExpectedOperation $Operation
        $result | Add-Member -NotePropertyName health -NotePropertyValue $health
        $result | Add-Member -NotePropertyName runtime -NotePropertyValue $runtime
    }
    catch {
        $recoverySucceeded = $false
        try {
            $recovery = Invoke-ShadowHelper -RequestedOperation 'rollback'
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
            throw 'Shadow Judging post-change verification failed; the governed pre-change state was restored and verified.'
        }
        throw 'Shadow Judging post-change verification failed; governed recovery also failed closed and requires owner review.'
    }
}

$result | ConvertTo-Json -Depth 12 | Write-Output
