#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ExpectedGitSha,
    [Parameter(Mandatory = $true)][string]$ReleaseManifest,
    [string]$ReleaseArchive,
    [string]$ExpectedImageId,
    [string]$ExpectedArchiveSha256,
    [string]$ExpectedPlatform = 'linux/arm64',
    [string]$LayoutFile = 'deploy\release-layout.example.json',
    [switch]$Execute,
    [string]$OwnerGate
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'ReleaseTooling.psm1') -Force -DisableNameChecking

$repoRoot = Get-RepoRoot
$layout = Get-ReleaseLayout -Path (Resolve-RepoPath $LayoutFile)
$manifestPath = Resolve-RepoPath $ReleaseManifest
$manifest = Read-JsonFile -Path $manifestPath
$ExpectedGitSha = (Invoke-Git -Arguments @('rev-parse', $ExpectedGitSha) -WorkingDirectory $repoRoot).Trim()
$expectedImageTag = Get-ReleaseImageTag -GitSha $ExpectedGitSha
$ExpectedImageId = if ($ExpectedImageId) { $ExpectedImageId.Trim() } else { $manifest.image_id }
$ExpectedArchiveSha256 = if ($ExpectedArchiveSha256) { $ExpectedArchiveSha256.Trim().ToLowerInvariant() } else { $manifest.archive_sha256 }
$ExpectedPlatform = if ($ExpectedPlatform) { $ExpectedPlatform.Trim().ToLowerInvariant() } else { 'linux/arm64' }
$archivePath = if ($ReleaseArchive) {
    Resolve-RepoPath $ReleaseArchive
} elseif ($manifest.PSObject.Properties.Name -contains 'image_archive_filename') {
    Join-Path (Split-Path -Parent $manifestPath) $manifest.image_archive_filename
} else {
    $null
}
$artifactBaseName = Get-ReleaseArtifactBaseName -GitSha $ExpectedGitSha
$composeFilePath = Resolve-RepoPath 'docker-compose.release.yml'
$healthcheckOverridePath = Join-Path ([System.IO.Path]::GetTempPath()) ("docker-compose.release.healthcheck.{0}.yml" -f $artifactBaseName)
$nginxConfigPath = Resolve-RepoPath 'nginx\default.conf'
$deploymentRecordPath = Join-Path (Split-Path -Parent $manifestPath) ("{0}.deployment.json" -f $artifactBaseName)
$canonicalAppHealthcheck = Get-CanonicalAppHealthcheckDefinition
Set-Content -LiteralPath $healthcheckOverridePath -Value (New-CanonicalAppHealthcheckOverrideYaml) -Encoding UTF8

function Invoke-RemoteCommandResult {
    # RELEASE-TOOLING-HOTFIX-01: delegates to ReleaseTooling.psm1's shared
    # Invoke-RemoteShellCommand -- do not re-implement stdin piping here.
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [string]$Command,
        [string]$ScriptText,
        [string]$StdinText
    )
    $params = @{ SshAlias = $layout.ssh_alias; Name = $Name }
    if ($PSBoundParameters.ContainsKey('Command')) { $params.Command = $Command }
    if ($PSBoundParameters.ContainsKey('ScriptText')) { $params.ScriptText = $ScriptText }
    if ($PSBoundParameters.ContainsKey('StdinText')) { $params.StdinText = $StdinText }
    return Invoke-RemoteShellCommand @params
}

function Invoke-RemoteText {
    param([Parameter(Mandatory = $true)][string]$Command)
    $result = Invoke-RemoteCommandResult -Name 'remote_command' -Command $Command
    if ($result.exit_code -ne 0) {
        throw "Remote command failed: $($result.output)"
    }
    return $result.output
}

function Join-RemotePath {
    param(
        [Parameter(Mandatory = $true)][string]$Left,
        [Parameter(Mandatory = $true)][string]$Right
    )
    return ($Left.TrimEnd('/') + '/' + $Right.TrimStart('/'))
}

function Get-RemoteComposeEnvironmentPrefix {
    <#
    .SYNOPSIS
    Non-secret, deploy-computed compose interpolation values only.
    DB credentials never appear here -- they reach Compose exclusively via
    `docker compose --env-file <production_env_path>`, sourced by
    Assert-ProtectedHostEnvCredentialAndTcpAuthentication (see PRODUCTION-RUNTIME-CANONICALIZATION).
    #>
    param(
        [Parameter(Mandatory = $true)][string]$ImageTag,
        [Parameter(Mandatory = $true)][string]$QuestionsVolumeName
    )
    $pairs = [ordered]@{
        GO_ODYSSEY_IMAGE = $ImageTag
        QUESTIONS_CONTENT_VOLUME_NAME = $QuestionsVolumeName
        QUESTIONS_CONTENT_MOUNT_DESTINATION = $layout.questions_content_mount_destination
        ASSET_SOURCE_PATH = $layout.asset_source_path
        ASSET_CONTAINER_MOUNT_DESTINATION = $layout.asset_container_mount_destination
        SHADOW_EVENT_LOG_PATH = $layout.shadow_event_log_path
    }
    return (($pairs.GetEnumerator() | ForEach-Object {
        "{0}={1}" -f $_.Key, (Quote-PosixShellArgument ([string]$_.Value))
    }) -join ' ')
}

function Get-RemoteQuestionsVolumeName {
    param([Parameter(Mandatory = $true)][string]$ContainerName)
    $mountsJson = Invoke-RemoteText "docker inspect $(Quote-PosixShellArgument $ContainerName) --format '{{json .Mounts}}'"
    $mount = Select-ContainerMountForDestination -MountsJson $mountsJson -Destination $layout.questions_content_mount_destination -Context $ContainerName
    if ($mount.type -ne 'volume') {
        throw "Live questions mount for $ContainerName at $($layout.questions_content_mount_destination) is not a named Docker volume (found: $($mount.type)). Refusing to guess a bind path; confirm the live mount and update the release compose contract explicitly for this host."
    }
    return $mount.name
}

function Get-RemoteContainerSnapshot {
    param([Parameter(Mandatory = $true)][string]$ContainerName)
    $raw = Invoke-RemoteText "docker inspect $ContainerName --format '{{json .State}}|{{.Config.Image}}|{{.Image}}|{{.Id}}|{{json .Config.Labels}}'"
    $parts = $raw -split '\|', 5
    if ($parts.Count -lt 5) {
        throw "Unable to read remote container snapshot for $ContainerName."
    }
    $state = $parts[0] | ConvertFrom-Json
    $health = if ($state.PSObject.Properties.Name -contains 'Health' -and $state.Health) { $state.Health.Status } else { 'n/a' }
    $labels = if ([string]::IsNullOrWhiteSpace($parts[4]) -or $parts[4] -eq 'null') { @{} } else { $parts[4] | ConvertFrom-Json }
    return [ordered]@{
        image_tag = $parts[1]
        image_id = $parts[2]
        container_id = $parts[3]
        state = $state.Status
        health = $health
        compose_project = $labels.'com.docker.compose.project'
        compose_service = $labels.'com.docker.compose.service'
    }
}

function Wait-ForRemoteContainerHealth {
    param(
        [Parameter(Mandatory = $true)][string]$ContainerName,
        [int]$TimeoutSeconds = 300,
        [int]$PollIntervalSeconds = 2
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $snapshot = Get-RemoteContainerSnapshot -ContainerName $ContainerName
        if ($snapshot.state -eq 'running' -and $snapshot.health -eq 'healthy') {
            return $snapshot
        }
        if ((Get-Date) -ge $deadline) {
            return $snapshot
        }
        Start-Sleep -Seconds $PollIntervalSeconds
    } while ($true)
}

function Wait-ForRemoteContainerRunning {
    param(
        [Parameter(Mandatory = $true)][string]$ContainerName,
        [int]$TimeoutSeconds = 120,
        [int]$PollIntervalSeconds = 2,
        [int]$RequiredConsecutiveSamples = 3
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $consecutive = 0
    do {
        $snapshot = Get-RemoteContainerSnapshot -ContainerName $ContainerName
        if ($snapshot.state -eq 'running') {
            $consecutive++
            if ($consecutive -ge $RequiredConsecutiveSamples) {
                return $snapshot
            }
        }
        else {
            $consecutive = 0
        }
        if ((Get-Date) -ge $deadline) {
            return $snapshot
        }
        Start-Sleep -Seconds $PollIntervalSeconds
    } while ($true)
}

function Get-RemoteContainerHealthcheckTest {
    param([Parameter(Mandatory = $true)][string]$ContainerName)
    $raw = Invoke-RemoteText "docker inspect $(Quote-PosixShellArgument $ContainerName) --format '{{json .Config.Healthcheck.Test}}'"
    if ([string]::IsNullOrWhiteSpace($raw) -or $raw -eq 'null') {
        return @()
    }
    return @($raw | ConvertFrom-Json)
}

function Assert-CanonicalExecHealthcheckTest {
    param(
        [Parameter(Mandatory = $true)][object[]]$HealthcheckTest,
        [Parameter(Mandatory = $true)][string]$Context
    )
    $normalizedHealthcheckTest = @($HealthcheckTest)
    if (
        $normalizedHealthcheckTest.Count -eq 1 -and
        $null -ne $normalizedHealthcheckTest[0] -and
        $normalizedHealthcheckTest[0] -is [System.Collections.IEnumerable] -and
        -not ($normalizedHealthcheckTest[0] -is [string])
    ) {
        $normalizedHealthcheckTest = @($normalizedHealthcheckTest[0])
    }
    if ($normalizedHealthcheckTest.Count -lt 4) {
        throw "$Context healthcheck is incomplete: $($normalizedHealthcheckTest | ConvertTo-Json -Compress)"
    }
    if ($normalizedHealthcheckTest[0] -ne 'CMD') {
        throw "$Context healthcheck must use CMD exec form. Actual: $($normalizedHealthcheckTest | ConvertTo-Json -Compress)"
    }
    if ($normalizedHealthcheckTest[1] -ne 'python') {
        throw "$Context healthcheck must invoke python. Actual: $($normalizedHealthcheckTest | ConvertTo-Json -Compress)"
    }
    if ($normalizedHealthcheckTest[2] -ne '-c') {
        throw "$Context healthcheck must pass -c to python. Actual: $($normalizedHealthcheckTest | ConvertTo-Json -Compress)"
    }
    if ([string]$normalizedHealthcheckTest[3] -notmatch '127\.0\.0\.1:8080/healthz') {
        throw "$Context healthcheck must probe http://127.0.0.1:8080/healthz. Actual: $($normalizedHealthcheckTest | ConvertTo-Json -Compress)"
    }
}

function Get-RemoteContainerEnvMap {
    param([Parameter(Mandatory = $true)][string]$ContainerName)
    $raw = Invoke-RemoteText "docker inspect $ContainerName --format '{{json .Config.Env}}'"
    if ([string]::IsNullOrWhiteSpace($raw) -or $raw -eq 'null') {
        return @{}
    }
    $env = $raw | ConvertFrom-Json
    $map = @{}
    foreach ($entry in $env) {
        $pair = $entry -split '=', 2
        if ($pair.Count -ge 1 -and -not [string]::IsNullOrWhiteSpace($pair[0])) {
            $map[$pair[0]] = if ($pair.Count -gt 1) { $pair[1] } else { '' }
        }
    }
    return $map
}

function Get-RemoteRuntimeContract {
    param([Parameter(Mandatory = $true)][string]$ContainerName)
    $script = @'
import hashlib
import json
import subprocess

name = "__CONTAINER_NAME__"
raw = subprocess.check_output(["docker", "inspect", name], text=True)
item = json.loads(raw)[0]
config = item.get("Config") or {}
host = item.get("HostConfig") or {}
labels = config.get("Labels") or {}
env_entries = config.get("Env") or []
env_keys = []
env_fingerprints = {}
for entry in env_entries:
    key, _, value = entry.partition("=")
    if not key:
        continue
    env_keys.append(key)
    env_fingerprints[key] = hashlib.sha256(value.encode("utf-8")).hexdigest()
mounts = []
for mount in item.get("Mounts") or []:
    mounts.append({
        "type": mount.get("Type"),
        "source_hash": hashlib.sha256((mount.get("Source") or "").encode("utf-8")).hexdigest(),
        "destination": mount.get("Destination"),
        "mode": mount.get("Mode"),
        "rw": mount.get("RW"),
    })
networks = sorted((item.get("NetworkSettings") or {}).get("Networks") or {})
report = {
    "container": name,
    "image": config.get("Image"),
    "image_id": item.get("Image"),
    "environment_keys": sorted(env_keys),
    "environment_value_fingerprints": env_fingerprints,
    "required_database_keys": {
        "DATABASE_URL": "DATABASE_URL" in env_keys,
        "QUESTIONS_JSON_PATH": "QUESTIONS_JSON_PATH" in env_keys,
    },
    "postgres_compose_keys_required": ["POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"],
    "questions_json_path_present": "QUESTIONS_JSON_PATH" in env_keys,
    "mounts": mounts,
    "networks": networks,
    "entrypoint": config.get("Entrypoint"),
    "command": config.get("Cmd"),
    "working_dir": config.get("WorkingDir"),
    "user": config.get("User"),
    "healthcheck_present": bool(config.get("Healthcheck")),
    "restart_policy": (host.get("RestartPolicy") or {}).get("Name"),
    "compose_project": labels.get("com.docker.compose.project"),
    "compose_service": labels.get("com.docker.compose.service"),
    "compose_config_files": labels.get("com.docker.compose.project.config_files"),
    "compose_working_dir": labels.get("com.docker.compose.project.working_dir"),
}
print(json.dumps(report, ensure_ascii=False))
'@
    $script = $script.Replace('__CONTAINER_NAME__', $ContainerName)
    $result = Invoke-RemoteCommandResult -Name 'runtime_contract' -Command 'python3 -' -StdinText $script
    if ($result.exit_code -ne 0) {
        throw "Remote command failed [runtime_contract]: $($result.output)"
    }
    return ($result.output | ConvertFrom-Json)
}

function Start-RemoteCandidateCanary {
    param(
        [Parameter(Mandatory = $true)][string]$SourceContainerName,
        [Parameter(Mandatory = $true)][string]$CandidateContainerName,
        [Parameter(Mandatory = $true)][string]$ImageTag
    )
    $payload = @{
        source_container = $SourceContainerName
        candidate_container = $CandidateContainerName
        image_tag = $ImageTag
    } | ConvertTo-Json -Compress
    $script = @'
import json
import re
import subprocess
import time

cfg = json.loads(r'''__CANARY_CONFIG__''')
source = cfg["source_container"]
candidate = cfg["candidate_container"]
image = cfg["image_tag"]
healthcheck = cfg["healthcheck"]
compose_path = cfg["compose_path"]
project_name = cfg["project_name"]

def run(args, check=True):
    proc = subprocess.run(args, text=True, capture_output=True)
    if check and proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout).strip())
    return proc

def duration_arg(ns):
    if not ns:
        return None
    seconds = max(1, int(round(ns / 1000000000)))
    return f"{seconds}s"

def sanitize(text):
    text = re.sub(r"(postgres(?:ql)?://[^:/\s]+:)[^@\s]+(@)", r"\1<redacted>\2", text)
    text = re.sub(r"(?i)(password|secret|token|key)=([^\\s]+)", r"\1=<redacted>", text)
    return text

raw = subprocess.check_output(["docker", "inspect", source], text=True)
item = json.loads(raw)[0]
config = item.get("Config") or {}
networks = list(((item.get("NetworkSettings") or {}).get("Networks") or {}).keys())

def yaml_scalar(value):
    return json.dumps("" if value is None else value)

def yaml_list(values, indent):
    return "\n".join((" " * indent) + "- " + json.dumps(value) for value in values)

env_map = {}
for env in config.get("Env") or []:
    key, _, value = env.partition("=")
    if key and key != "HOSTNAME":
        env_map[key] = value

volume_lines = []
volume_defs = []
seen_named_volumes = set()
for mount in item.get("Mounts") or []:
    mtype = mount.get("Type")
    source_path = mount.get("Name") if mtype == "volume" else mount.get("Source")
    dest = mount.get("Destination")
    if not mtype or not source_path or not dest:
        continue
    suffix = ":ro" if not mount.get("RW", True) else ""
    volume_lines.append(f'      - {json.dumps(source_path + ":" + dest + suffix)}')
    if mtype == "volume" and source_path not in seen_named_volumes:
        seen_named_volumes.add(source_path)
        volume_defs.append(f"  {source_path}:")
        volume_defs.append("    external: true")
        volume_defs.append(f"    name: {source_path}")

network_defs = []
network_refs = []
for network in networks:
    network_refs.append(f"      - {network}")
    network_defs.append(f"  {network}:")
    network_defs.append(f"    external: true")
    network_defs.append(f"    name: {network}")

compose_lines = [
    "services:",
    "  candidate:",
    f"    image: {json.dumps(image)}",
    f"    container_name: {json.dumps(candidate)}",
    "    restart: \"no\"",
    "    environment:",
]
for key in sorted(env_map):
    compose_lines.append(f"      {key}: {yaml_scalar(env_map[key])}")
if config.get("WorkingDir"):
    compose_lines.append(f"    working_dir: {yaml_scalar(config['WorkingDir'])}")
if config.get("User"):
    compose_lines.append(f"    user: {yaml_scalar(config['User'])}")
if config.get("Entrypoint"):
    compose_lines.append("    entrypoint:")
    compose_lines.extend(yaml_list(config["Entrypoint"], 6).splitlines())
if config.get("Cmd"):
    compose_lines.append("    command:")
    compose_lines.extend(yaml_list(config["Cmd"], 6).splitlines())
compose_lines.append("    volumes:")
compose_lines.extend(volume_lines)
compose_lines.append("    networks:")
compose_lines.extend(network_refs)
compose_lines.append("    healthcheck:")
compose_lines.append(f"      test: {json.dumps(healthcheck['test'])}")
compose_lines.append(f"      interval: {healthcheck['interval']}")
compose_lines.append(f"      timeout: {healthcheck['timeout']}")
compose_lines.append(f"      retries: {healthcheck['retries']}")
compose_lines.append(f"      start_period: {healthcheck['start_period']}")
compose_lines.append("networks:")
compose_lines.extend(network_defs)
if volume_defs:
    compose_lines.append("volumes:")
    compose_lines.extend(volume_defs)

run(["docker", "rm", "-f", candidate], check=False)
with open(compose_path, "w", encoding="utf-8") as handle:
    handle.write("\n".join(compose_lines) + "\n")
run(["docker", "compose", "-p", project_name, "-f", compose_path, "up", "-d", "candidate"])

health_status = "no-healthcheck"
state_status = "unknown"
for _ in range(60):
    state_raw = subprocess.check_output(["docker", "inspect", candidate, "--format", "{{json .State}}"], text=True)
    state = json.loads(state_raw)
    state_status = state.get("Status", "unknown")
    health_status = (state.get("Health") or {}).get("Status", "no-healthcheck")
    if state_status != "running":
        break
    if health_status in ("healthy", "no-healthcheck"):
        break
    if health_status == "unhealthy":
        break
    time.sleep(2)

image_id = subprocess.check_output(["docker", "inspect", candidate, "--format", "{{.Image}}"], text=True).strip()
logs = subprocess.run(["docker", "logs", "--tail", "120", candidate], text=True, capture_output=True)
print(json.dumps({
    "candidate_container": candidate,
    "source_container": source,
    "compose_project": project_name,
    "compose_path": compose_path,
    "public_traffic_attached": False,
    "scheduler_started": False,
    "state": state_status,
    "health": health_status,
    "image_id": image_id,
    "healthcheck_test": subprocess.check_output(["docker", "inspect", candidate, "--format", "{{json .Config.Healthcheck.Test}}"], text=True).strip(),
    "logs_tail": sanitize(logs.stdout + logs.stderr)[-8000:],
}, ensure_ascii=False))
'@
    $payloadObject = @{
        source_container = $SourceContainerName
        candidate_container = $CandidateContainerName
        image_tag = $ImageTag
        healthcheck = $canonicalAppHealthcheck
        compose_path = "/tmp/$CandidateContainerName.compose.yml"
        project_name = ($CandidateContainerName -replace '[^a-zA-Z0-9_-]', '-')
    }
    $payload = $payloadObject | ConvertTo-Json -Compress -Depth 8
    $script = $script.Replace('__CANARY_CONFIG__', $payload)
    $result = Invoke-RemoteCommandResult -Name 'candidate_canary' -Command 'python3 -' -StdinText $script
    if ($result.exit_code -ne 0) {
        throw "Remote command failed [candidate_canary]: $($result.output)"
    }
    return ($result.output | ConvertFrom-Json)
}

function Remove-RemoteCandidateCanary {
    param(
        [Parameter(Mandatory = $true)][string]$CandidateContainerName,
        [string]$ComposeProjectName,
        [string]$ComposePath
    )
    $composeCleanupAttempted = -not [string]::IsNullOrWhiteSpace($ComposeProjectName) -and -not [string]::IsNullOrWhiteSpace($ComposePath)
    if ($composeCleanupAttempted) {
        Invoke-RemoteText "docker compose -p $(Quote-PosixShellArgument $ComposeProjectName) -f $(Quote-PosixShellArgument $ComposePath) down --remove-orphans >/dev/null 2>&1 || true" | Out-Null
        Invoke-RemoteText "rm -f $(Quote-PosixShellArgument $ComposePath) >/dev/null 2>&1 || true" | Out-Null
    }
    Invoke-RemoteText "docker rm -f $(Quote-PosixShellArgument $CandidateContainerName) >/dev/null 2>&1 || true" | Out-Null
    $containerState = Invoke-RemoteText "if docker inspect $(Quote-PosixShellArgument $CandidateContainerName) >/dev/null 2>&1; then printf present; else printf absent; fi"
    $composePathState = if ($composeCleanupAttempted) {
        Invoke-RemoteText "if test -e $(Quote-PosixShellArgument $ComposePath); then printf present; else printf absent; fi"
    } else { 'not_applicable' }
    if ($containerState -ne 'absent' -or $composePathState -eq 'present') {
        throw 'Candidate cleanup verification failed closed.'
    }
    return [ordered]@{
        status = 'completed'
        candidate_container = $CandidateContainerName
        compose_cleanup_attempted = $composeCleanupAttempted
        container_remove_attempted = $true
        container_state = $containerState
        compose_path_state = $composePathState
    }
}

function Save-CandidateEvidenceAtomically {
    param(
        [Parameter(Mandatory = $true)]$Evidence,
        [Parameter(Mandatory = $true)][string]$Path
    )
    $parent = Split-Path -Parent $Path
    if (-not (Test-Path -LiteralPath $parent -PathType Container)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
    $temporary = "$Path.tmp.$([Guid]::NewGuid().ToString('N'))"
    try {
        $Evidence | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $temporary -Encoding UTF8
        Move-Item -LiteralPath $temporary -Destination $Path -Force
    }
    finally {
        Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
    }
}

function Get-RemoteCandidateFailureEvidence {
    param(
        [Parameter(Mandatory = $true)][string]$OperationId,
        [Parameter(Mandatory = $true)][string]$CandidateContainerName,
        [Parameter(Mandatory = $true)][string]$SchedulerContainerName,
        [Parameter(Mandatory = $true)][string]$NginxContainerName,
        [scriptblock]$CaptureProbe
    )
    if ($CaptureProbe) { return & $CaptureProbe $OperationId $CandidateContainerName }
    $payload = [ordered]@{
        operation_id = $OperationId
        candidate = $CandidateContainerName
        scheduler = $SchedulerContainerName
        nginx = $NginxContainerName
    } | ConvertTo-Json -Compress
    $script = @'
import datetime
import json
import re
import subprocess
import sys

cfg = json.loads(r'''__CANDIDATE_EVIDENCE_CONFIG__''')
PREFIX = "[startup-diagnostic] "
MAX_LOG_LINES = 240
MAX_LOG_CHARS = 32768
SUSPICIOUS = re.compile(r"(?i)(://|secret|password|passwd|token|cookie|authorization|database[_-]?url|connection[_-]?string|private[_ -]?key|credential)")
SAFE_LOG = re.compile(r"(?i)(startup-diagnostic|traceback|error|exception|warning|health|connection refused|upstream|listening|ready)")

def bounded(args, timeout=5):
    try:
        return subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None

def safe_startup(line):
    if not line.startswith(PREFIX):
        return None
    try:
        source = json.loads(line[len(PREFIX):])
    except (TypeError, ValueError):
        return None
    allowed = {key: source.get(key) for key in (
        "schema", "boot_id", "timestamp_utc", "elapsed_seconds", "pid", "phase", "status",
        "phase_elapsed_seconds", "exception_type", "snapshot_sequence"
    ) if key in source}
    threads = []
    for thread in (source.get("threads") or [])[:16]:
        frames = []
        for frame in (thread.get("frames") or [])[-48:]:
            try:
                line_number = int(frame.get("line") or 0)
            except (TypeError, ValueError):
                line_number = 0
            frames.append({
                "file": str(frame.get("file") or "")[:160],
                "function": str(frame.get("function") or "")[:160],
                "line": line_number,
            })
        threads.append({"thread_id": str(thread.get("thread_id") or "")[:64], "frames": frames})
    if threads:
        allowed["threads"] = threads
    return allowed

def capture(name):
    inspected = bounded(["docker", "inspect", name], 5)
    if inspected is None or inspected.returncode != 0:
        return {"available": False, "name": name, "failure_code": "container_inspect_unavailable"}
    try:
        item = json.loads(inspected.stdout)[0]
    except (TypeError, ValueError, IndexError):
        return {"available": False, "name": name, "failure_code": "container_inspect_invalid"}
    state = item.get("State") or {}
    health = state.get("Health") or {}
    health_history = []
    for row in (health.get("Log") or [])[-24:]:
        health_history.append({
            "start": row.get("Start"), "end": row.get("End"), "exit_code": row.get("ExitCode")
        })
    logs = bounded(["docker", "logs", "--since", "20m", "--tail", str(MAX_LOG_LINES), name], 5)
    startup = []
    safe_logs = []
    if logs is not None:
        for raw_line in (logs.stdout or "").splitlines():
            event = safe_startup(raw_line)
            if event is not None:
                startup.append(event)
                continue
            if SUSPICIOUS.search(raw_line) or not SAFE_LOG.search(raw_line):
                continue
            safe_logs.append(raw_line[:512])
    safe_log_text = "\n".join(safe_logs)
    if len(safe_log_text) > MAX_LOG_CHARS:
        safe_log_text = safe_log_text[:MAX_LOG_CHARS] + "\n<truncated>"
    return {
        "available": True,
        "name": name,
        "container_id": item.get("Id"),
        "image_id": item.get("Image"),
        "created": item.get("Created"),
        "started_at": state.get("StartedAt"),
        "finished_at": state.get("FinishedAt"),
        "status": state.get("Status"),
        "health": health.get("Status") if health else "n/a",
        "health_history": health_history,
        "restart_count": item.get("RestartCount"),
        "exit_code": state.get("ExitCode"),
        "oom_killed": state.get("OOMKilled"),
        "startup_diagnostics": startup[-160:],
        "bounded_logs": safe_log_text,
    }

print(json.dumps({
    "status": "captured",
    "operation_id": cfg["operation_id"],
    "captured_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "candidate": capture(cfg["candidate"]),
    "scheduler": capture(cfg["scheduler"]),
    "nginx": capture(cfg["nginx"]),
}, sort_keys=True, separators=(",", ":")))
'@
    $script = $script.Replace('__CANDIDATE_EVIDENCE_CONFIG__', $payload)
    $arguments = @((Get-BoundedSshOptionArguments), $layout.ssh_alias, 'python3 -')
    $result = Invoke-BoundedNativeCommand -FileName 'ssh' -ArgumentList $arguments -StdinText $script -TimeoutSeconds 20 -OperationLabel 'candidate failure evidence capture'
    if ($result.exit_code -ne 0) { throw 'Candidate evidence capture failed closed; remote output withheld.' }
    try { $evidence = $result.stdout | ConvertFrom-Json }
    catch { throw 'Candidate evidence capture returned invalid sanitized JSON.' }
    if (-not $evidence -or $evidence.status -ne 'captured' -or $evidence.operation_id -ne $OperationId) {
        throw 'Candidate evidence capture response failed closed.'
    }
    return $evidence
}

function Invoke-CandidateFailurePreservation {
    param(
        [Parameter(Mandatory = $true)][string]$OperationId,
        [Parameter(Mandatory = $true)][string]$CandidateContainerName,
        [Parameter(Mandatory = $true)]$OriginalFailure,
        [Parameter(Mandatory = $true)][string]$EvidencePath,
        $HelperAttempt,
        [scriptblock]$CaptureAction,
        [scriptblock]$CleanupAction
    )
    $capture = $null
    $captureFailure = $null
    try { $capture = & $CaptureAction }
    catch { $captureFailure = 'candidate_evidence_capture_failed_closed' }
    $evidence = [ordered]@{
        schema = 'go-odyssey-candidate-failure-evidence-v1'
        operation_id = $OperationId
        recorded_at_utc = (Get-Date).ToUniversalTime().ToString('o')
        candidate_container_name = $CandidateContainerName
        original_failure = $OriginalFailure
        helper_attempt = $HelperAttempt
        capture = $capture
        capture_failure = $captureFailure
        cleanup = [ordered]@{ status = 'not_started' }
        release_lock_cleanup = [ordered]@{ status = 'pending' }
    }
    Save-CandidateEvidenceAtomically -Evidence $evidence -Path $EvidencePath
    try {
        $cleanup = & $CleanupAction
        $evidence.cleanup = if ($cleanup) { $cleanup } else { [ordered]@{ status = 'completed' } }
    }
    catch {
        $evidence.cleanup = [ordered]@{ status = 'failed'; failure_code = 'candidate_cleanup_failed_closed' }
    }
    try { Save-CandidateEvidenceAtomically -Evidence $evidence -Path $EvidencePath }
    catch {}
    return $evidence
}

function Remove-RemoteStaleCandidateCanaries {
    <#
    Candidate containers are never production traffic targets. Clean only the
    release tool's own precisely labelled/name-prefixed canaries so an aborted
    client cannot leave a conflicting compose project behind.
    #>
    $script = @'
import json
import pathlib
import subprocess

prefix = "go-odyssey-candidate-go-odyssey-app_"
removed = []
ids = subprocess.check_output(["docker", "ps", "-aq"], text=True).split()
for container_id in ids:
    item = json.loads(subprocess.check_output(["docker", "inspect", container_id], text=True))[0]
    name = (item.get("Name") or "").lstrip("/")
    labels = (item.get("Config") or {}).get("Labels") or {}
    project = labels.get("com.docker.compose.project", "")
    service = labels.get("com.docker.compose.service", "")
    if not (name.startswith(prefix) and project.startswith(prefix) and service == "candidate"):
        continue
    subprocess.run(["docker", "rm", "-f", name], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    config_files = labels.get("com.docker.compose.project.config_files", "")
    for raw_path in config_files.split(","):
        path = pathlib.Path(raw_path.strip())
        if str(path).startswith("/tmp/" + prefix) and path.name.endswith(".compose.yml"):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
    removed.append({"container": name, "compose_project": project})
print(json.dumps({"removed": removed}, ensure_ascii=False))
'@
    $result = Invoke-RemoteCommandResult -Name 'stale_candidate_cleanup' -Command 'python3 -' -StdinText $script
    if ($result.exit_code -ne 0) {
        throw "Remote stale candidate cleanup failed: $($result.output)"
    }
    return ($result.output | ConvertFrom-Json)
}

function Test-HelperUnavailableOutput {
    param([string]$Output)
    if ([string]::IsNullOrWhiteSpace($Output)) {
        return $false
    }
    return $Output -match '_read_runtime_deployment_readiness' -and (
        $Output -match 'AttributeError' -or
        $Output -match 'has no attribute'
    )
}

function ConvertFrom-FramedReadinessOutput {
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Output)

    $prefix = '__GO_ODYSSEY_READINESS_V1__:'
    $diagnosticPrefix = '[startup-diagnostic] '
    $lines = @($Output -split "`r?`n")
    $records = @($lines | Where-Object { $_.StartsWith($prefix, [System.StringComparison]::Ordinal) })
    if ($records.Count -ne 1) {
        throw "Runtime readiness output must contain exactly one framed result; found $($records.Count)."
    }

    $encoded = $records[0].Substring($prefix.Length)
    if ([string]::IsNullOrWhiteSpace($encoded)) {
        throw "Runtime readiness framed result is empty."
    }
    try {
        $bytes = [Convert]::FromBase64String($encoded)
        $utf8 = New-Object System.Text.UTF8Encoding($false, $true)
        $json = $utf8.GetString($bytes)
        $report = $json | ConvertFrom-Json
    }
    catch {
        throw "Runtime readiness framed result is malformed."
    }

    $requiredProperties = @('ok', 'app', 'questions', 'database', 'static_root', 'shadow_events', 'failures')
    $propertyNames = @($report.PSObject.Properties.Name)
    foreach ($propertyName in $requiredProperties) {
        if ($propertyNames -notcontains $propertyName) {
            throw "Runtime readiness framed result has an invalid schema: missing $propertyName."
        }
    }
    if ($report.ok -isnot [bool]) {
        throw "Runtime readiness framed result has an invalid schema: ok must be boolean."
    }
    foreach ($propertyName in @('app', 'questions', 'database', 'static_root', 'shadow_events')) {
        if ($null -eq $report.$propertyName -or $report.$propertyName -isnot [psobject]) {
            throw "Runtime readiness framed result has an invalid schema: $propertyName must be an object."
        }
    }
    if ($null -eq $report.failures) {
        throw "Runtime readiness framed result has an invalid schema: failures must be an array."
    }

    # Preserve only the structured, explicitly safe startup diagnostic schema.
    # Unframed output is never fed to ConvertFrom-Json and is never copied into
    # the deployment result, so unexpected stderr cannot disclose private data.
    $diagnostics = @()
    foreach ($line in $lines) {
        if ($diagnostics.Count -ge 64 -or -not $line.StartsWith($diagnosticPrefix, [System.StringComparison]::Ordinal)) {
            continue
        }
        try {
            $source = $line.Substring($diagnosticPrefix.Length) | ConvertFrom-Json
            $safe = [ordered]@{}
            foreach ($name in @('schema', 'boot_id', 'timestamp_utc', 'elapsed_seconds', 'pid', 'phase', 'status', 'phase_elapsed_seconds', 'exception_type', 'snapshot_sequence')) {
                if (@($source.PSObject.Properties.Name) -contains $name) {
                    $safe[$name] = $source.$name
                }
            }
            if (@($source.PSObject.Properties.Name) -contains 'threads') {
                $safeThreads = @()
                foreach ($thread in @($source.threads) | Select-Object -First 16) {
                    $safeFrames = @()
                    foreach ($frame in @($thread.frames) | Select-Object -Last 48) {
                        $safeFrames += [ordered]@{
                            file = ([string]$frame.file).Substring(0, [Math]::Min(160, ([string]$frame.file).Length))
                            function = ([string]$frame.function).Substring(0, [Math]::Min(160, ([string]$frame.function).Length))
                            line = [int]$frame.line
                        }
                    }
                    $safeThreads += [ordered]@{ thread_id = [int]$thread.thread_id; frames = $safeFrames }
                }
                $safe['threads'] = $safeThreads
            }
            $diagnostics += $safe
        }
        catch {
            # Diagnostic decoding is best effort and must never affect the
            # separately framed readiness result.
            continue
        }
    }

    return [ordered]@{
        report = $report
        startup_diagnostics = $diagnostics
    }
}

function ConvertTo-SafeBoundedHelperText {
    param(
        [AllowNull()][string]$Text,
        [int]$MaximumCharacters = 32768,
        [int]$MaximumLines = 160
    )
    if ([string]::IsNullOrWhiteSpace($Text)) { return '' }
    $safeLines = @()
    foreach ($line in @($Text -split "`r?`n")) {
        if ($safeLines.Count -ge $MaximumLines) { break }
        $candidate = [string]$line
        if ($candidate.StartsWith('__GO_ODYSSEY_READINESS_V1__:', [System.StringComparison]::Ordinal)) {
            $safeLines += '__GO_ODYSSEY_READINESS_V1__:<payload retained separately>'
            continue
        }
        if ($candidate.StartsWith('[startup-diagnostic] ', [System.StringComparison]::Ordinal)) {
            try {
                $source = $candidate.Substring(21) | ConvertFrom-Json
                $safe = [ordered]@{}
                foreach ($name in @('schema','boot_id','timestamp_utc','elapsed_seconds','pid','phase','status','phase_elapsed_seconds','exception_type','snapshot_sequence')) {
                    if (@($source.PSObject.Properties.Name) -contains $name) { $safe[$name] = $source.$name }
                }
                $safeLines += ('[startup-diagnostic] ' + ($safe | ConvertTo-Json -Compress -Depth 4))
            }
            catch {}
            continue
        }
        if ($candidate -match '://' -or $candidate -match '(?i)(secret|password|passwd|token|cookie|authorization|database[_-]?url|connection[_-]?string|private[_ -]?key|credential)') {
            continue
        }
        if ($candidate -match '^(Traceback|During handling|The above exception|\s*File \"[^\"]+\", line \d+|\s*\^+\s*$|[A-Za-z_][A-Za-z0-9_.]*(Error|Exception):)') {
            $safeLines += $candidate.Substring(0, [Math]::Min(512, $candidate.Length))
        }
    }
    $safeText = ($safeLines -join "`n")
    if ($safeText.Length -le $MaximumCharacters) { return $safeText }
    return ($safeText.Substring(0, $MaximumCharacters) + "`n<truncated>")
}

function ConvertTo-SafeReadinessEvidenceReport {
    param([AllowNull()]$Report)
    if ($null -eq $Report) { return $null }
    return [ordered]@{
        ok = [bool]$Report.ok
        app = [ordered]@{
            git_sha = [string]$Report.app.git_sha
            image_revision = [string]$Report.app.image_revision
            build_date = [string]$Report.app.build_date
        }
        questions = [ordered]@{
            exists = [bool]$Report.questions.exists
            readable = [bool]$Report.questions.readable
            parseable = [bool]$Report.questions.parseable
            record_count = [int]$Report.questions.record_count
            record_count_ok = [bool]$Report.questions.record_count_ok
            structural_record_check = [bool]$Report.questions.structural_record_check
        }
        database = [ordered]@{
            reachable = [bool]$Report.database.reachable
            tables = $Report.database.tables
        }
        static_root = [ordered]@{
            exists = [bool]$Report.static_root.exists
            readable = [bool]$Report.static_root.readable
        }
        shadow_events = [ordered]@{
            exists = [bool]$Report.shadow_events.exists
            readable = [bool]$Report.shadow_events.readable
            writable_or_valid = [bool]$Report.shadow_events.writable_or_valid
        }
        failure_count = @($Report.failures).Count
    }
}

function Try-Get-RemoteReadinessReport {
    param([Parameter(Mandatory = $true)][string]$ContainerName)
    $command = "docker exec $ContainerName python -X utf8 -c 'import base64, json, app; payload=json.dumps(app._read_runtime_deployment_readiness(), ensure_ascii=False).encode(`"utf-8`"); print(`"__GO_ODYSSEY_READINESS_V1__:`" + base64.b64encode(payload).decode(`"ascii`"))'"
    $result = Invoke-BoundedSshCommand -SshAlias $layout.ssh_alias -Command $command -TimeoutSeconds 45 -OperationLabel 'candidate runtime readiness helper'
    $combined = (@([string]$result.stdout, [string]$result.stderr) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }) -join "`n"
    $decoded = $null
    $decodeFailure = $null
    try { $decoded = ConvertFrom-FramedReadinessOutput -Output $combined }
    catch { $decodeFailure = $_.Exception.Message }
    $script:LastReadinessAttempt = [ordered]@{
        container_name = $ContainerName
        exit_code = [int]$result.exit_code
        elapsed_seconds = [double]$result.elapsed_seconds
        stdout = ConvertTo-SafeBoundedHelperText -Text ([string]$result.stdout)
        stderr = ConvertTo-SafeBoundedHelperText -Text ([string]$result.stderr)
        framed_payload_present = ($null -ne $decoded)
        framed_report = if ($decoded) { ConvertTo-SafeReadinessEvidenceReport -Report $decoded.report } else { $null }
        startup_diagnostics = if ($decoded) { @($decoded.startup_diagnostics) } else { @() }
        framing_failure = if ($decodeFailure) { 'framed_readiness_decode_failed_closed' } else { $null }
    }
    if ($result.exit_code -eq 0) {
        if (-not $decoded) { throw $decodeFailure }
        return [ordered]@{
            mode = 'helper'
            report = $decoded.report
            helper_available = $true
            startup_diagnostics = @($decoded.startup_diagnostics)
        }
    }
    if (Test-HelperUnavailableOutput -Output $combined) {
        return [ordered]@{
            mode = 'legacy_fallback'
            report = $null
            helper_available = $false
            startup_diagnostics = @()
        }
    }
    throw "Runtime readiness helper failed unexpectedly with exit code $($result.exit_code)."
}

function Get-RemoteQuestionsReport {
    param(
        [Parameter(Mandatory = $true)][string]$ContainerName,
        [Parameter(Mandatory = $true)][string]$QuestionsPath
    )
    $script = @"
import json
import pathlib

report = {
    "path": "$QuestionsPath",
    "exists": False,
    "readable": False,
    "parseable": False,
    "top_level_type": "",
    "record_count": 0,
    "record_count_ok": False,
    "structural_record_check": False,
    "failures": [],
}
path = pathlib.Path("$QuestionsPath")
report["exists"] = path.exists()
if not report["exists"]:
    report["failures"].append("questions file is missing")
else:
    try:
        text = path.read_text(encoding="utf-8")
        report["readable"] = True
        payload = json.loads(text)
        report["parseable"] = True
        report["top_level_type"] = type(payload).__name__
        if isinstance(payload, list):
            report["record_count"] = len(payload)
            report["record_count_ok"] = report["record_count"] > 0
            sample = next((row for row in payload[:20] if isinstance(row, dict)), None)
            if sample is not None:
                report["structural_record_check"] = any(
                    sample.get(key) not in (None, "")
                    for key in ("id", "question_id", "source", "content", "sgf")
                )
            if report["record_count"] == 0:
                report["failures"].append("questions file contains no records")
            if not report["structural_record_check"]:
                report["failures"].append("questions file failed the bounded structural record check")
        else:
            report["failures"].append("questions file top-level value must be a JSON list")
    except Exception as exc:
        if not report["readable"]:
            report["failures"].append("questions file is not readable")
        report["failures"].append(f"questions file parse failed: {exc.__class__.__name__}")
print(json.dumps(report, ensure_ascii=False))
"@
    $result = Invoke-RemoteCommandResult -Name 'questions_report' -Command "docker exec -i $ContainerName python -X utf8 -" -StdinText $script
    if ($result.exit_code -ne 0) {
        throw "Remote command failed [questions_report]: $($result.output)"
    }
    return ($result.output | ConvertFrom-Json)
}

function Get-DailyChallengeUrl {
    param([Parameter(Mandatory = $true)][string]$BaseUrl)
    $uri = [Uri]$BaseUrl
    $builder = [UriBuilder]::new($uri)
    $builder.Path = '/api/daily-challenge/today'
    $builder.Query = ''
    return $builder.Uri.AbsoluteUri
}

function Get-RemoteHttpStatus {
    param([Parameter(Mandatory = $true)][string]$Url)
    return (Invoke-RemoteText "curl -sS -o /dev/null -w '%{http_code}' $(Quote-PosixShellArgument $Url)").Trim()
}

function Get-RemoteContainerHttpStatus {
    param(
        [Parameter(Mandatory = $true)][string]$ContainerName,
        [Parameter(Mandatory = $true)][string]$Path
    )
    $url = "http://127.0.0.1:8080$Path"
    $python = @'
import sys
import urllib.error
import urllib.request

url = sys.argv[1]
try:
    with urllib.request.urlopen(url, timeout=5) as response:
        print(response.getcode())
except urllib.error.HTTPError as exc:
    print(exc.code)
'@
    $result = Invoke-RemoteCommandResult -Name 'container_http_status' -Command "docker exec -i $(Quote-PosixShellArgument $ContainerName) python - $(Quote-PosixShellArgument $url)" -StdinText $python
    if ($result.exit_code -ne 0) {
        throw "Remote command failed: $($result.output)"
    }
    return $result.output.Trim()
}

function Assert-QuestionsReportSatisfiesGate {
    param([Parameter(Mandatory = $true)]$QuestionsReport)
    if (-not $QuestionsReport.exists) {
        throw "Questions file is missing after the image switch."
    }
    if (-not $QuestionsReport.readable) {
        throw "Questions file is not readable after the image switch."
    }
    if (-not $QuestionsReport.parseable) {
        throw "Questions file is not parseable JSON after the image switch."
    }
    if (-not $QuestionsReport.record_count_ok -or $QuestionsReport.record_count -le 0) {
        throw "Questions dataset is empty after the image switch."
    }
    if (-not $QuestionsReport.structural_record_check) {
        throw "Questions file failed the structural record gate after the image switch."
    }
}

function Get-AppReadinessGateReport {
    param(
        [Parameter(Mandatory = $true)][string]$ContainerName,
        [switch]$UseContainerHttp
    )
    $readinessMode = Try-Get-RemoteReadinessReport -ContainerName $ContainerName
    $appEnv = Get-RemoteContainerEnvMap -ContainerName $ContainerName
    $expectedQuestionsPath = ($layout.questions_content_mount_destination.TrimEnd('/','\') + '/questions.json')
    $questionsPath = if (-not [string]::IsNullOrWhiteSpace($appEnv['QUESTIONS_JSON_PATH'])) { $appEnv['QUESTIONS_JSON_PATH'] } else { $expectedQuestionsPath }
    $questionsReport = if ($readinessMode.mode -eq 'helper') { $readinessMode.report.questions } else { Get-RemoteQuestionsReport -ContainerName $ContainerName -QuestionsPath $questionsPath }
    $healthzStatus = if ($UseContainerHttp) { Get-RemoteContainerHttpStatus -ContainerName $ContainerName -Path '/healthz' } else { Get-RemoteHttpStatus -Url $layout.health_url }
    $loginStatus = if ($UseContainerHttp) { Get-RemoteContainerHttpStatus -ContainerName $ContainerName -Path '/login' } else { Get-RemoteHttpStatus -Url $layout.login_url }
    $homeStatus = if ($UseContainerHttp) { Get-RemoteContainerHttpStatus -ContainerName $ContainerName -Path '/' } else { Get-RemoteHttpStatus -Url $layout.homepage_url }
    $dailyChallengeStatus = if ($UseContainerHttp) { Get-RemoteContainerHttpStatus -ContainerName $ContainerName -Path '/api/daily-challenge/today' } else { Get-RemoteHttpStatus -Url (Get-DailyChallengeUrl -BaseUrl $layout.homepage_url) }
    return [ordered]@{
        helper_available = $readinessMode.helper_available
        readiness_mode = $readinessMode.mode
        readiness = $readinessMode.report
        startup_diagnostics = @($readinessMode.startup_diagnostics)
        questions_json_path = $questionsPath
        questions = $questionsReport
        http_mode = if ($UseContainerHttp) { 'container_local' } else { 'public' }
        healthz_status = $healthzStatus
        login_status = $loginStatus
        home_status = $homeStatus
        daily_challenge_status = $dailyChallengeStatus
    }
}

function Get-RemoteImageLabels {
    param([Parameter(Mandatory = $true)][string]$ImageTag)
    $raw = Invoke-RemoteText "docker image inspect $(Quote-PosixShellArgument $ImageTag) --format '{{json .Config.Labels}}'"
    if ([string]::IsNullOrWhiteSpace($raw) -or $raw -eq 'null') {
        return @{}
    }
    return $raw | ConvertFrom-Json
}

function Get-RemoteImageSummary {
    param([Parameter(Mandatory = $true)][string]$ImageTag)
    $labels = Get-RemoteImageLabels -ImageTag $ImageTag
    return [ordered]@{
        image_id = (Invoke-RemoteText "docker image inspect $(Quote-PosixShellArgument $ImageTag) --format '{{.Id}}'")
        platform = (Invoke-RemoteText "docker image inspect $(Quote-PosixShellArgument $ImageTag) --format '{{.Os}}/{{.Architecture}}'")
        revision = $labels.'org.opencontainers.image.revision'
        source = $labels.'org.opencontainers.image.source'
        sgf_engine_source_commit = $labels.'com.godokoro.sgf-engine.source-commit'
    }
}

function Get-LocalImageSummary {
    param([Parameter(Mandatory = $true)][string]$ImageTag)
    $labelsRaw = & docker image inspect $ImageTag --format "{{json .Config.Labels}}"
    if ($LASTEXITCODE -ne 0) {
        throw "Local image inspect failed for $ImageTag."
    }
    $labels = if ([string]::IsNullOrWhiteSpace($labelsRaw) -or $labelsRaw -eq 'null') { @{} } else { $labelsRaw | ConvertFrom-Json }
    return [ordered]@{
        image_id = (& docker image inspect $ImageTag --format "{{.Id}}").Trim()
        platform = (& docker image inspect $ImageTag --format "{{.Os}}/{{.Architecture}}").Trim().ToLowerInvariant()
        revision = $labels.'org.opencontainers.image.revision'
        source = $labels.'org.opencontainers.image.source'
        sgf_engine_source_commit = $labels.'com.godokoro.sgf-engine.source-commit'
    }
}

function New-DeploymentRecord {
    param(
        [Parameter(Mandatory = $true)]$RollbackIdentity,
        [Parameter(Mandatory = $true)][string]$VerificationResult
    )
    return New-ReleaseManifestObject `
        -GitSha $manifest.release_git_sha `
        -ImageTag $manifest.image_tag `
        -ImageId $manifest.image_id `
        -ArchiveFilename $manifest.image_archive_filename `
        -ArchiveSha256 $manifest.archive_sha256 `
        -BuildTimestamp $manifest.build_timestamp `
        -BuildMachineIdentityClass $manifest.build_machine_identity_class `
        -TargetServiceNames $manifest.target_service_names `
        -ExternalContentRequirements $manifest.external_content_requirements `
        -ExpectedHealthEndpoints $manifest.expected_health_endpoints `
        -RollbackImageIdentity $RollbackIdentity `
        -VerificationResult $VerificationResult `
        -DeploymentTimestamp ([DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')) `
        -OCIRevision $manifest.oci_revision `
        -OCIImageSource $manifest.oci_source `
        -SGFEngineSourceCommit $manifest.sgf_engine_source_commit
}

function Save-DeploymentRecord {
    param(
        [Parameter(Mandatory = $true)]$Record,
        [Parameter(Mandatory = $true)][string]$Path
    )
    Write-JsonFile -InputObject $Record -Path $Path
}

function Invoke-ProductionVerificationSeries {
    param(
        [Parameter(Mandatory = $true)][string]$OperationId,
        [int]$Count = 3,
        [int]$IntervalSeconds = 10
    )
    $reports = @()
    for ($attempt = 1; $attempt -le $Count; $attempt++) {
        $verificationOutput = & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'verify-production-release.ps1') `
            -ReleaseManifest $deploymentRecordPath `
            -LayoutFile $LayoutFile `
            -OperationId $OperationId
        if ($LASTEXITCODE -ne 0) {
            throw "verify-production-release.ps1 failed on stability pass $attempt of $Count with exit code $LASTEXITCODE."
        }
        $reports += ,(ConvertFrom-NestedPowerShellJson -RawOutput $verificationOutput -Context "verify-production-release.ps1 pass $attempt")
        if ($attempt -lt $Count) {
            Start-Sleep -Seconds $IntervalSeconds
        }
    }
    return @($reports)
}

$localArchiveSha = $null
if ($archivePath -and (Test-Path -LiteralPath $archivePath)) {
    $localArchiveSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $archivePath).Hash.ToLowerInvariant()
}
$localArchiveSize = if ($archivePath -and (Test-Path -LiteralPath $archivePath)) {
    (Get-Item -LiteralPath $archivePath).Length
} else {
    0
}
$localImageSummary = Get-LocalImageSummary -ImageTag $manifest.image_tag

if (-not $Execute) {
    [ordered]@{
        dry_run = $true
        execute_requested = $false
        expected_git_sha = $ExpectedGitSha
        expected_image_tag = $expectedImageTag
        expected_image_id = $ExpectedImageId
        expected_archive_sha256 = $ExpectedArchiveSha256
        expected_platform = $ExpectedPlatform
        release_archive_exists = $(if ($archivePath) { Test-Path -LiteralPath $archivePath } else { $false })
        release_archive_size_bytes = $localArchiveSize
        release_archive_sha256 = $localArchiveSha
        local_image_summary = $localImageSummary
        release_manifest = $manifest
        compose_project = $layout.compose_project
        target_services = @($layout.app_service_name, $layout.scheduler_service_name)
        required_owner_gate = 'GO_DEPLOY'
        deployment_plan = @(
            'verify manifest and archive checksum',
            'stage compose file and nginx config on the production host',
            'transfer image archive and deployment record',
            'verify remote archive checksum',
            'verify compose resolves exact release image',
            'load the exact image into the remote Docker engine',
            'capture rollback identity from currently running services',
            'capture sanitized runtime contracts from app and scheduler',
            'start candidate canary with the live app runtime contract and no public traffic',
            'verify candidate canary health, image identity, questions, and runtime readiness',
            'switch app to the release image',
            'verify app health and runtime readiness',
            'switch scheduler to the release image',
            'restart nginx to refresh upstream resolution',
            'run production verification',
            'write sanitized deployment record'
        )
    } | ConvertTo-Json -Depth 12 | Write-Output
    return
}

Assert-OwnerGate -Provided $OwnerGate -Expected 'GO_DEPLOY'
if ($manifest.release_git_sha -ne $ExpectedGitSha) {
    throw "Release manifest SHA does not match expected Git SHA."
}
if ($manifest.oci_revision -ne $ExpectedGitSha) {
    throw "Release manifest OCI revision does not match expected Git SHA."
}
if ($manifest.image_id -ne $ExpectedImageId) {
    throw "Release manifest image ID does not match expected image ID."
}
if ($manifest.archive_sha256 -ne $ExpectedArchiveSha256) {
    throw "Release manifest archive checksum does not match expected archive checksum."
}
if ($ExpectedPlatform -ne 'linux/arm64') {
    throw "Expected platform must be linux/arm64."
}
if ($manifest.image_tag -ne $expectedImageTag) {
    throw "Release manifest image tag does not match expected Git SHA."
}
if (-not $archivePath -or -not (Test-Path -LiteralPath $archivePath)) {
    throw "Release archive not found: $archivePath"
}
if ($localArchiveSize -le 0) {
    throw "Release archive is empty."
}
if ([string]::IsNullOrWhiteSpace($localArchiveSha) -or $localArchiveSha -ne $manifest.archive_sha256) {
    throw "Release archive checksum does not match the manifest."
}
if ($localImageSummary.image_id -ne $ExpectedImageId) {
    throw "Local image ID does not match the expected release image ID."
}
if ($localImageSummary.platform -ne $ExpectedPlatform) {
    throw "Local image platform does not match expected platform."
}
if ($localImageSummary.revision -ne $ExpectedGitSha) {
    throw "Local image revision does not match expected Git SHA."
}
if ($localImageSummary.source -ne $manifest.oci_source) {
    throw "Local image source does not match the release manifest."
}
if ($localImageSummary.sgf_engine_source_commit -ne $manifest.sgf_engine_source_commit) {
    throw "Local image SGF Engine source commit does not match the release manifest."
}

$remoteArchivePath = Join-RemotePath $layout.remote_release_staging_directory ([IO.Path]::GetFileName($archivePath))
$remoteManifestPath = Join-RemotePath $layout.remote_release_staging_directory ([IO.Path]::GetFileName($manifestPath))
$remoteComposePath = Join-RemotePath $layout.compose_directory 'docker-compose.release.yml'
$remoteHealthcheckOverridePath = Join-RemotePath $layout.compose_directory 'docker-compose.release.healthcheck.override.yml'
$remoteNginxPath = Join-RemotePath (Join-RemotePath $layout.compose_directory 'nginx') 'default.conf'
$remoteDeploymentRecordPath = Join-RemotePath $layout.remote_release_staging_directory ([IO.Path]::GetFileName($deploymentRecordPath))
$remoteArchiveSha = ''
$remoteImageSummary = $null
$appBefore = $null
$schedulerBefore = $null
$rollbackIdentity = $null
$deploymentRecord = $null
$appAfter = $null
$schedulerAfter = $null
$appReadinessReport = $null
$candidateContainerName = "go-odyssey-candidate-$($artifactBaseName)"
$appRuntimeContract = $null
$schedulerRuntimeContract = $null
$candidateCanary = $null
$candidateReadinessReport = $null
$verificationReports = @()
$rollbackRequired = $false
$staleCandidateCleanup = $null
$operationId = "deploy-$artifactBaseName-$([Guid]::NewGuid().ToString('N'))"
$candidateEvidencePath = Join-Path (Split-Path -Parent $manifestPath) ("{0}.{1}.candidate-evidence.json" -f $artifactBaseName, $operationId)
$candidateFailureEvidence = $null
$candidateCreationAttempted = $false
$script:LastReadinessAttempt = $null
$remoteOperationLockPath = Join-RemotePath $layout.compose_directory '.release-operation.lock'
$operationLockHeld = $false

try {
    $null = Enter-RemoteReleaseOperationLock -SshAlias $layout.ssh_alias -LockPath $remoteOperationLockPath -OperationId $operationId
    $operationLockHeld = $true
    $staleCandidateCleanup = Remove-RemoteStaleCandidateCanaries
    Invoke-RemoteText "mkdir -p $(Quote-PosixShellArgument $layout.remote_release_staging_directory) $(Quote-PosixShellArgument $layout.compose_directory) $(Quote-PosixShellArgument (Join-RemotePath $layout.compose_directory 'nginx'))"

    & scp $composeFilePath "$($layout.ssh_alias):$remoteComposePath" | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "scp failed while transferring docker-compose.release.yml."
    }
    & scp $healthcheckOverridePath "$($layout.ssh_alias):$remoteHealthcheckOverridePath" | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "scp failed while transferring docker-compose.release.healthcheck.override.yml."
    }
    & scp $nginxConfigPath "$($layout.ssh_alias):$remoteNginxPath" | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "scp failed while transferring nginx/default.conf."
    }
    & scp $manifestPath "$($layout.ssh_alias):$remoteManifestPath" | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "scp failed while transferring the release manifest."
    }
    & scp $archivePath "$($layout.ssh_alias):$remoteArchivePath" | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "scp failed while transferring the release archive."
    }

    $remoteArchiveSha = (Invoke-RemoteText "sha256sum $(Quote-PosixShellArgument $remoteArchivePath)").Split(' ')[0].Trim().ToLowerInvariant()
    if ($remoteArchiveSha -ne $manifest.archive_sha256) {
        throw "Remote archive checksum does not match the manifest."
    }

    $appBefore = Get-RemoteContainerSnapshot -ContainerName $layout.app_service_name
    $schedulerBefore = Get-RemoteContainerSnapshot -ContainerName $layout.scheduler_service_name
    $nginxBefore = Get-RemoteContainerSnapshot -ContainerName $layout.nginx_service_name

    # PRODUCTION-RUNTIME-CANONICALIZATION: the DB credential source of
    # truth is the protected host env declared by the release layout --
    # never the existing scheduler container's live environment (which
    # would silently propagate a stale/incorrect password forward). This
    # runs entirely on the production host; the raw password never
    # returns to this local process. See
    # Assert-ProtectedHostEnvCredentialAndTcpAuthentication for the
    # fail-closed contract.
    Assert-ProtectedHostEnvCredentialAndTcpAuthentication -SshAlias $layout.ssh_alias -EnvPath $layout.production_env_path -PostgresContainerName $layout.postgres_service_name

    $questionsVolumeName = Get-RemoteQuestionsVolumeName -ContainerName $layout.app_service_name
    $appComposeService = if ([string]::IsNullOrWhiteSpace($appBefore.compose_service)) { $layout.app_service_name } else { $appBefore.compose_service }
    $schedulerComposeService = if ([string]::IsNullOrWhiteSpace($schedulerBefore.compose_service)) { $layout.scheduler_service_name } else { $schedulerBefore.compose_service }
    $nginxComposeService = if ([string]::IsNullOrWhiteSpace($nginxBefore.compose_service)) { $layout.nginx_service_name } else { $nginxBefore.compose_service }
    $composeEnvPrefix = Get-RemoteComposeEnvironmentPrefix -ImageTag $manifest.image_tag -QuestionsVolumeName $questionsVolumeName
    $composeProjectArg = "-p $(Quote-PosixShellArgument $layout.compose_project)"
    $composeEnvFileArg = "--env-file $(Quote-PosixShellArgument $layout.production_env_path)"
    $composeServices = Invoke-RemoteText "cd $(Quote-PosixShellArgument $layout.compose_directory) && $composeEnvPrefix docker compose $composeProjectArg $composeEnvFileArg -f docker-compose.release.yml -f $(Quote-PosixShellArgument $remoteHealthcheckOverridePath) config --services"
    $composeServiceList = [regex]::Split($composeServices, '\r?\n') | ForEach-Object { $_.Trim() } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    foreach ($serviceName in @($appComposeService, $schedulerComposeService, $nginxComposeService)) {
        if ($composeServiceList -notcontains $serviceName) {
            throw "docker compose config did not expose expected service: $serviceName"
        }
    }

    $composeImages = Invoke-RemoteText "cd $(Quote-PosixShellArgument $layout.compose_directory) && $composeEnvPrefix docker compose $composeProjectArg $composeEnvFileArg -f docker-compose.release.yml -f $(Quote-PosixShellArgument $remoteHealthcheckOverridePath) config --images"
    $composeImageMatches = ([regex]::Split($composeImages, '\r?\n') | Where-Object { $_.Trim() -eq $manifest.image_tag }).Count
    if ($composeImageMatches -lt 2) {
        throw "docker compose config did not resolve the exact release image for app and scheduler."
    }

    Invoke-RemoteText "docker load -i $(Quote-PosixShellArgument $remoteArchivePath)"

    $remoteImageSummary = Get-RemoteImageSummary -ImageTag $manifest.image_tag
    if ($remoteImageSummary.image_id -ne $manifest.image_id) {
        throw "Remote image ID does not match the release manifest."
    }
    if ($remoteImageSummary.revision -ne $ExpectedGitSha) {
        throw "Remote image revision does not match the release manifest."
    }
    if ($remoteImageSummary.source -ne $manifest.oci_source) {
        throw "Remote image source does not match the release manifest."
    }
    if ($remoteImageSummary.sgf_engine_source_commit -ne $manifest.sgf_engine_source_commit) {
        throw "Remote image SGF Engine source commit does not match the release manifest."
    }
    if ($remoteImageSummary.platform -ne 'linux/arm64') {
        throw "Remote image platform does not match linux/arm64."
    }

    $appBeforeLabels = Get-RemoteImageLabels -ImageTag $appBefore.image_tag
    $schedulerBeforeLabels = Get-RemoteImageLabels -ImageTag $schedulerBefore.image_tag
    $appRuntimeContract = Get-RemoteRuntimeContract -ContainerName $layout.app_service_name
    $schedulerRuntimeContract = Get-RemoteRuntimeContract -ContainerName $layout.scheduler_service_name
    foreach ($key in @('DATABASE_URL', 'QUESTIONS_JSON_PATH')) {
        if (-not $appRuntimeContract.required_database_keys.$key) {
            throw "Live app runtime contract is missing required environment key: $key"
        }
    }
    $rollbackIdentity = [ordered]@{
        previous_app_image_tag = $appBefore.image_tag
        previous_app_image_id = $appBefore.image_id
        previous_app_container_id = $appBefore.container_id
        previous_app_release_git_sha = $appBeforeLabels.'org.opencontainers.image.revision'
        previous_scheduler_image_tag = $schedulerBefore.image_tag
        previous_scheduler_image_id = $schedulerBefore.image_id
        previous_scheduler_container_id = $schedulerBefore.container_id
        previous_scheduler_release_git_sha = $schedulerBeforeLabels.'org.opencontainers.image.revision'
        previous_health_state = $appBefore.health
        current_compose_project = $layout.compose_project
        current_compose_directory = $layout.compose_directory
        previous_app_runtime_contract = $appRuntimeContract
        previous_scheduler_runtime_contract = $schedulerRuntimeContract
    }
    $deploymentRecord = New-DeploymentRecord -RollbackIdentity $rollbackIdentity -VerificationResult 'deployment in progress'
    $deploymentRecord['operation_id'] = $operationId
    $deploymentRecord['candidate_evidence_filename'] = [IO.Path]::GetFileName($candidateEvidencePath)
    Save-DeploymentRecord -Record $deploymentRecord -Path $deploymentRecordPath
    & scp $deploymentRecordPath "$($layout.ssh_alias):$remoteDeploymentRecordPath" | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "scp failed while transferring the deployment record."
    }

    $candidateCreationAttempted = $true
    $candidateCanary = Start-RemoteCandidateCanary -SourceContainerName $layout.app_service_name -CandidateContainerName $candidateContainerName -ImageTag $manifest.image_tag
    if ($candidateCanary.public_traffic_attached -ne $false) {
        throw "Candidate canary unexpectedly reports public traffic attachment."
    }
    if ($candidateCanary.scheduler_started -ne $false) {
        throw "Candidate canary unexpectedly reports scheduler startup."
    }
    if ($candidateCanary.image_id -ne $ExpectedImageId) {
        throw "Candidate canary image ID does not match the release image ID."
    }
    $candidateHealthcheckTest = @($candidateCanary.healthcheck_test | ConvertFrom-Json)
    Assert-CanonicalExecHealthcheckTest -HealthcheckTest $candidateHealthcheckTest -Context 'Candidate canary'
    if ($candidateCanary.state -ne 'running') {
        throw "Candidate canary is not running. Sanitized logs: $($candidateCanary.logs_tail)"
    }
    if ($candidateCanary.health -ne 'healthy' -and $candidateCanary.health -ne 'no-healthcheck') {
        throw "Candidate canary is not healthy. Sanitized logs: $($candidateCanary.logs_tail)"
    }
    $candidateImageSummary = Get-RemoteImageSummary -ImageTag $manifest.image_tag
    if ($candidateImageSummary.platform -ne 'linux/arm64' -or $candidateImageSummary.revision -ne $ExpectedGitSha) {
        throw "Candidate canary image metadata does not match the expected platform and revision."
    }
    $candidateReadinessReport = Get-AppReadinessGateReport -ContainerName $candidateContainerName -UseContainerHttp
    if ($candidateReadinessReport.readiness_mode -ne 'helper') {
        throw "Candidate canary requires runtime readiness helper for DB and application readiness validation."
    }
    if ($candidateReadinessReport.readiness.ok -ne $true) {
        throw "Candidate canary runtime readiness check failed."
    }
    Assert-QuestionsReportSatisfiesGate -QuestionsReport $candidateReadinessReport.questions
    if ($candidateReadinessReport.healthz_status -ne '200' -or $candidateReadinessReport.login_status -ne '200' -or $candidateReadinessReport.home_status -ne '200') {
        throw "Candidate canary container-local HTTP gates failed."
    }
    if ($candidateReadinessReport.daily_challenge_status -eq '503') {
        throw "Daily challenge returned 503 during candidate canary validation."
    }

    $rollbackRequired = $true
    Invoke-RemoteText "cd $(Quote-PosixShellArgument $layout.compose_directory) && $composeEnvPrefix docker compose $composeProjectArg $composeEnvFileArg -f docker-compose.release.yml -f $(Quote-PosixShellArgument $remoteHealthcheckOverridePath) up -d --no-build --no-deps --force-recreate $appComposeService"

    $appAfter = Wait-ForRemoteContainerHealth -ContainerName $layout.app_service_name
    if ($appAfter.image_tag -ne $manifest.image_tag) {
        throw "App container is not running the release image."
    }
    if ($appAfter.image_id -ne $ExpectedImageId) {
        throw "App container image ID does not match the release image ID."
    }
    if ($appAfter.compose_project -ne $layout.compose_project -or $appAfter.compose_service -ne $appComposeService) {
        throw "App container compose identity did not converge to the canonical project/service."
    }
    $appHealthcheckTest = Get-RemoteContainerHealthcheckTest -ContainerName $layout.app_service_name
    Assert-CanonicalExecHealthcheckTest -HealthcheckTest $appHealthcheckTest -Context 'App container'
    if ($appAfter.health -ne 'healthy') {
        throw "App container is not healthy after the image switch."
    }

    $appReadinessReport = Get-AppReadinessGateReport -ContainerName $layout.app_service_name
    if ($appReadinessReport.readiness_mode -eq 'helper' -and $appReadinessReport.readiness.ok -ne $true) {
        throw "App runtime readiness check failed after the image switch."
    }
    Assert-QuestionsReportSatisfiesGate -QuestionsReport $appReadinessReport.questions
    if ($appReadinessReport.healthz_status -ne '200' -or $appReadinessReport.login_status -ne '200' -or $appReadinessReport.home_status -ne '200') {
        throw "Required HTTP gates failed after the app image switch."
    }
    if ($appReadinessReport.daily_challenge_status -eq '503') {
        throw "Daily challenge returned 503 after the app image switch."
    }

    Invoke-RemoteText "cd $(Quote-PosixShellArgument $layout.compose_directory) && $composeEnvPrefix docker compose $composeProjectArg $composeEnvFileArg -f docker-compose.release.yml -f $(Quote-PosixShellArgument $remoteHealthcheckOverridePath) up -d --no-build --no-deps --force-recreate $schedulerComposeService"

    $schedulerAfter = Wait-ForRemoteContainerRunning -ContainerName $layout.scheduler_service_name
    if ($schedulerAfter.image_tag -ne $manifest.image_tag) {
        throw "Scheduler container is not running the release image."
    }
    if ($schedulerAfter.image_id -ne $ExpectedImageId) {
        throw "Scheduler container image ID does not match the release image ID."
    }
    if ($schedulerAfter.compose_project -ne $layout.compose_project -or $schedulerAfter.compose_service -ne $schedulerComposeService) {
        throw "Scheduler container compose identity did not converge to the canonical project/service."
    }
    if ($appAfter.image_id -ne $schedulerAfter.image_id) {
        throw "App and scheduler image IDs do not match after rollout."
    }

    Invoke-RemoteText "docker restart $(Quote-PosixShellArgument $layout.nginx_service_name)"

    $verificationReports = Invoke-ProductionVerificationSeries -OperationId $operationId -Count 3 -IntervalSeconds 10

    if ($deploymentRecord.Contains('verification_result')) {
        $deploymentRecord['verification_result'] = 'production verified stable 3x'
    }
    Save-DeploymentRecord -Record $deploymentRecord -Path $deploymentRecordPath
    & scp $deploymentRecordPath "$($layout.ssh_alias):$remoteDeploymentRecordPath" | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "scp failed while updating the remote deployment record."
    }
    $null = Remove-RemoteCandidateCanary -CandidateContainerName $candidateContainerName -ComposeProjectName $candidateCanary.compose_project -ComposePath $candidateCanary.compose_path

    [ordered]@{
        dry_run = $false
        execute_requested = $true
        expected_git_sha = $ExpectedGitSha
        expected_image_tag = $manifest.image_tag
        expected_image_id = $ExpectedImageId
        expected_archive_sha256 = $ExpectedArchiveSha256
        expected_platform = $ExpectedPlatform
        release_archive_path = $archivePath
        release_archive_size_bytes = $localArchiveSize
        release_archive_sha256 = $localArchiveSha
        remote_release_archive_path = $remoteArchivePath
        remote_release_archive_sha256 = $remoteArchiveSha
        release_manifest_path = $manifestPath
        deployment_record_path = $deploymentRecordPath
        local_image_summary = $localImageSummary
        rollback_image_identity = $rollbackIdentity
        remote_image_id = $remoteImageSummary.image_id
        remote_image_platform = $remoteImageSummary.platform
        app_before = $appBefore
        scheduler_before = $schedulerBefore
        app_runtime_contract = $appRuntimeContract
        scheduler_runtime_contract = $schedulerRuntimeContract
        candidate_canary = $candidateCanary
        candidate_readiness = $candidateReadinessReport
        stale_candidate_cleanup = $staleCandidateCleanup
        app_after = $appAfter
        scheduler_after = $schedulerAfter
        app_readiness = $appReadinessReport
        verification_1 = $verificationReports[0]
        verification_2 = $verificationReports[1]
        verification_3 = $verificationReports[2]
    } | ConvertTo-Json -Depth 12 | Write-Output
}
catch {
    $deploymentFailure = $_
    $deploymentFailureMessage = $_.Exception.Message
    if ($candidateCreationAttempted) {
        $failureStage = if ($script:LastReadinessAttempt -and $script:LastReadinessAttempt.container_name -eq $candidateContainerName) { 'candidate_readiness_helper' } else { 'candidate_lifecycle' }
        $originalFailure = [ordered]@{
            stage = $failureStage
            code = [string]$deploymentFailure.FullyQualifiedErrorId
            message = if ($failureStage -eq 'candidate_readiness_helper') { "Candidate readiness helper failed with exit code $([int]$script:LastReadinessAttempt.exit_code)." } else { 'Candidate lifecycle validation failed closed.' }
        }
        $captureAction = {
            Get-RemoteCandidateFailureEvidence `
                -OperationId $operationId `
                -CandidateContainerName $candidateContainerName `
                -SchedulerContainerName $layout.scheduler_service_name `
                -NginxContainerName $layout.nginx_service_name
        }
        $cleanupAction = {
            Remove-RemoteCandidateCanary `
                -CandidateContainerName $candidateContainerName `
                -ComposeProjectName $(if ($candidateCanary) { $candidateCanary.compose_project } else { '' }) `
                -ComposePath $(if ($candidateCanary) { $candidateCanary.compose_path } else { '' })
        }
        try {
            $candidateFailureEvidence = Invoke-CandidateFailurePreservation `
                -OperationId $operationId `
                -CandidateContainerName $candidateContainerName `
                -OriginalFailure $originalFailure `
                -EvidencePath $candidateEvidencePath `
                -HelperAttempt $script:LastReadinessAttempt `
                -CaptureAction $captureAction `
                -CleanupAction $cleanupAction
        }
        catch {
            try { & $cleanupAction | Out-Null } catch {}
        }
    }
    elseif ($candidateContainerName) {
        try { Remove-RemoteCandidateCanary -CandidateContainerName $candidateContainerName -ComposeProjectName '' -ComposePath '' | Out-Null } catch {}
    }
    if ($rollbackRequired -and $deploymentRecordPath -and (Test-Path -LiteralPath $deploymentRecordPath)) {
        $reconciliationFailure = $null
        try {
            # A child verification timeout is not proof that the switched
            # release failed. Re-read the remote final state and require the
            # complete canonical verification contract three times before a
            # rollback is even considered.
            Start-Sleep -Seconds 15
            $verificationReports = Invoke-ProductionVerificationSeries -OperationId $operationId -Count 3 -IntervalSeconds 10
        }
        catch {
            $reconciliationFailure = $_.Exception.Message
        }
        if (@($verificationReports).Count -eq 3) {
            if ($deploymentRecord.Contains('verification_result')) {
                $deploymentRecord['verification_result'] = 'production verified stable 3x after transient orchestration failure'
            }
            Save-DeploymentRecord -Record $deploymentRecord -Path $deploymentRecordPath
            $recordSyncError = $null
            try {
                & scp $deploymentRecordPath "$($layout.ssh_alias):$remoteDeploymentRecordPath" | Out-Host
                if ($LASTEXITCODE -ne 0) {
                    $recordSyncError = "scp failed while reconciling the remote deployment record."
                }
            }
            catch {
                $recordSyncError = $_.Exception.Message
            }
            $appAfter = Get-RemoteContainerSnapshot -ContainerName $layout.app_service_name
            $schedulerAfter = Get-RemoteContainerSnapshot -ContainerName $layout.scheduler_service_name
            [ordered]@{
                dry_run = $false
                execute_requested = $true
                deployment_stable = $true
                recovered_from_transient_orchestration_failure = $true
                transient_failure = $deploymentFailureMessage
                deployment_record_sync_error = $recordSyncError
                expected_git_sha = $ExpectedGitSha
                expected_image_tag = $manifest.image_tag
                expected_image_id = $ExpectedImageId
                app_after = $appAfter
                scheduler_after = $schedulerAfter
                verification_1 = $verificationReports[0]
                verification_2 = $verificationReports[1]
                verification_3 = $verificationReports[2]
                rollback_performed = $false
            } | ConvertTo-Json -Depth 12 | Write-Output
            return
        }

        # Release the deploy lease before handing ownership to the canonical
        # rollback script. Rollback acquires the same lease independently.
        if ($operationLockHeld) {
            $null = Exit-RemoteReleaseOperationLock -SshAlias $layout.ssh_alias -LockPath $remoteOperationLockPath -OperationId $operationId
            $operationLockHeld = $false
        }
        try {
            $rollbackOutput = & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'rollback-release.ps1') -RollbackManifest $deploymentRecordPath -LayoutFile $LayoutFile -Execute -OwnerGate 'GO_ROLLBACK'
            if ($LASTEXITCODE -ne 0) {
                throw "rollback-release.ps1 failed with exit code $LASTEXITCODE."
            }
            $null = ConvertFrom-NestedPowerShellJson -RawOutput $rollbackOutput -Context 'rollback-release.ps1'
        }
        catch {
            throw "Deployment failed: $deploymentFailureMessage`nFinal-state reconciliation failed: $reconciliationFailure`nAutomatic rollback failed: $($_.Exception.Message)"
        }
        throw "Deployment failed and automatic rollback succeeded after final-state reconciliation failed: $deploymentFailureMessage"
    }
    throw
}
finally {
    if ($operationLockHeld) {
        try {
            $releaseCleanup = Exit-RemoteReleaseOperationLock -SshAlias $layout.ssh_alias -LockPath $remoteOperationLockPath -OperationId $operationId
            if ($candidateFailureEvidence) {
                $candidateFailureEvidence.release_lock_cleanup = [ordered]@{ status = 'completed'; result = $releaseCleanup }
            }
        }
        catch {
            if ($candidateFailureEvidence) {
                $candidateFailureEvidence.release_lock_cleanup = [ordered]@{ status = 'failed'; failure_code = 'release_lock_cleanup_failed_closed' }
            }
            Write-Warning $_.Exception.Message
        }
    }
    if ($candidateFailureEvidence) {
        try { Save-CandidateEvidenceAtomically -Evidence $candidateFailureEvidence -Path $candidateEvidencePath } catch {}
    }
    Remove-Item -LiteralPath $healthcheckOverridePath -ErrorAction SilentlyContinue
}
