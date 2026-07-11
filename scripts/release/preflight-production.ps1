#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$LayoutFile = 'deploy\release-layout.example.json',
    [string]$ReleaseManifest = 'deploy\release-manifest.example.json',
    [string]$ReleaseArchive,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'ReleaseTooling.psm1') -Force -DisableNameChecking

$repoRoot = Get-RepoRoot
$layout = Get-ReleaseLayout -Path (Resolve-RepoPath $LayoutFile)
$releaseManifestPath = Resolve-RepoPath $ReleaseManifest
$candidateManifestExists = Test-Path -LiteralPath $releaseManifestPath
$candidateArchiveExists = $false
if ($ReleaseArchive) {
    $candidateArchiveExists = Test-Path -LiteralPath (Resolve-RepoPath $ReleaseArchive)
}
$script:FakeRemoteResponses = $null
if ($env:GO_ODYSSEY_PREFLIGHT_FAKE_REMOTE_RESPONSES) {
    $fakeRemotePath = Resolve-RepoPath $env:GO_ODYSSEY_PREFLIGHT_FAKE_REMOTE_RESPONSES
    $script:FakeRemoteResponses = Read-JsonFile -Path $fakeRemotePath
}

function Get-FakeRemoteResponse {
    param([Parameter(Mandatory = $true)][string]$Name)
    if (-not $script:FakeRemoteResponses) {
        throw "Fake remote responses are not configured."
    }
    $responses = $script:FakeRemoteResponses.responses
    if (-not $responses) {
        throw "Fake remote response file is missing the responses object."
    }
    $property = $responses.PSObject.Properties[$Name]
    if (-not $property) {
        throw "Fake remote response is missing required entry: $Name"
    }
    return $property.Value
}

function Invoke-RemoteCommandResult {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [string]$Command,
        [string]$ScriptText
    )
    if ($script:FakeRemoteResponses) {
        $fake = Get-FakeRemoteResponse -Name $Name
        return [ordered]@{
            name = $Name
            output = [string]$fake.stdout
            exit_code = [int]$(if ($fake.PSObject.Properties.Name -contains 'exit_code') { $fake.exit_code } else { 0 })
            mode = 'fake'
        }
    }
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        if ($PSBoundParameters.ContainsKey('ScriptText')) {
            $normalizedScriptText = $ScriptText -replace "`r`n", "`n" -replace "`r", "`n"
            $rawOutput = $normalizedScriptText | & ssh $layout.ssh_alias 'sh -s' 2>&1
        }
        else {
            $rawOutput = & ssh $layout.ssh_alias $Command 2>&1
        }
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    $output = ($rawOutput | ForEach-Object {
        if ($_ -is [System.Management.Automation.ErrorRecord]) {
            $_.ToString()
        }
        else {
            [string]$_
        }
    } | Out-String).Trim()
    return [ordered]@{
        name = $Name
        output = $output
        exit_code = $exitCode
        mode = 'ssh'
    }
}

function Invoke-RemoteText {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Command
    )
    $result = Invoke-RemoteCommandResult -Name $Name -Command $Command
    if ($result.exit_code -ne 0) {
        throw "Remote command failed [$Name]: $($result.output)"
    }
    return $result.output
}

function Invoke-RemoteScriptText {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$ScriptText
    )
    $result = Invoke-RemoteCommandResult -Name $Name -ScriptText $ScriptText
    if ($result.exit_code -ne 0) {
        throw "Remote script failed [$Name]: $($result.output)"
    }
    return $result.output
}

function Get-RemoteContainerSnapshot {
    param(
        [Parameter(Mandatory = $true)][string]$ContainerName,
        [Parameter(Mandatory = $true)][string]$ResponseName
    )
    $script = @"
docker inspect $ContainerName --format '{{.Id}}|{{.Image}}|{{.Config.Image}}|{{.State.Status}}|{{with index .State "Health"}}{{index . "Status"}}{{end}}|{{.RestartCount}}|{{if .State.Restarting}}true{{else}}false{{end}}|{{index .Config.Labels "com.docker.compose.project"}}|{{index .Config.Labels "com.docker.compose.service"}}'
"@
    $raw = Invoke-RemoteScriptText -Name $ResponseName -ScriptText $script
    $parts = $raw -split '\|', 9
    if ($parts.Count -lt 9) {
        throw "Container snapshot response [$ResponseName] is malformed."
    }
    return [ordered]@{
        container_id = $parts[0]
        image_id = $parts[1]
        image_ref = $parts[2]
        status = $parts[3]
        health = $(if ([string]::IsNullOrWhiteSpace($parts[4])) { 'n/a' } else { $parts[4] })
        restart_count = [int]$parts[5]
        restarting = $parts[6] -eq 'true'
        compose_project = $parts[7]
        compose_service = $parts[8]
    }
}

function Get-RemoteContainerEnvMap {
    param(
        [Parameter(Mandatory = $true)][string]$ContainerName,
        [Parameter(Mandatory = $true)][string]$ResponseName
    )
    $raw = Invoke-RemoteText -Name $ResponseName -Command "docker inspect $ContainerName --format '{{json .Config.Env}}'"
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

function Get-Sha256Hex {
    param([string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) {
        return ''
    }
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($Value)
        $hashBytes = $sha.ComputeHash($bytes)
        return ([BitConverter]::ToString($hashBytes)).Replace('-', '').ToLowerInvariant()
    }
    finally {
        $sha.Dispose()
    }
}

function Get-DatabaseIdentitySummary {
    param([string]$DatabaseUrl)
    $value = ([string]$DatabaseUrl).Trim()
    if ([string]::IsNullOrWhiteSpace($value)) {
        return [ordered]@{
            configured = $false
            host = ''
            port = $null
            database = ''
            user = ''
            password_present = $false
        }
    }
    $uri = [Uri]$value
    $userInfo = $uri.UserInfo
    $user = ''
    $passwordPresent = $false
    if (-not [string]::IsNullOrWhiteSpace($userInfo)) {
        $parts = $userInfo -split ':', 2
        $user = [Uri]::UnescapeDataString($parts[0])
        $passwordPresent = $parts.Count -gt 1 -and -not [string]::IsNullOrWhiteSpace($parts[1])
    }
    return [ordered]@{
        configured = $true
        host = $uri.Host
        port = $uri.Port
        database = $uri.AbsolutePath.TrimStart('/')
        user = $user
        password_present = $passwordPresent
    }
}

function Get-SanitizedDatabaseIdentity {
    param($Identity)
    return [ordered]@{
        configured = [bool]$Identity.configured
        host = [string]$Identity.host
        port = $Identity.port
        database = [string]$Identity.database
        user_hash = Get-Sha256Hex -Value ([string]$Identity.user)
        password_present = [bool]$Identity.password_present
    }
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

function Try-Get-RemoteReadinessReport {
    param([Parameter(Mandatory = $true)][string]$ContainerName)
    $result = Invoke-RemoteCommandResult -Name 'app_helper_readiness' -Command "docker exec $ContainerName python -X utf8 -c 'import json, app; print(json.dumps(app._read_runtime_deployment_readiness(), ensure_ascii=False))'"
    if ($result.exit_code -eq 0) {
        return [ordered]@{
            mode = 'helper'
            report = ($result.output | ConvertFrom-Json)
            helper_available = $true
            helper_output = $result.output
        }
    }
    if (Test-HelperUnavailableOutput -Output $result.output) {
        return [ordered]@{
            mode = 'legacy_fallback'
            report = $null
            helper_available = $false
            helper_output = $result.output
        }
    }
    throw "Runtime readiness helper failed unexpectedly: $($result.output)"
}

function Get-RemoteQuestionsReport {
    param(
        [Parameter(Mandatory = $true)][string]$ContainerName,
        [Parameter(Mandatory = $true)][string]$QuestionsPath
    )
    $script = @"
docker exec $ContainerName python - <<'PY'
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
PY
"@
    $json = Invoke-RemoteScriptText -Name 'questions_report' -ScriptText $script
    return ($json | ConvertFrom-Json)
}

function Get-RemoteHttpStatus {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Url
    )
    return (Invoke-RemoteText -Name $Name -Command "curl -sS -o /dev/null -w '%{http_code}' $(Quote-PosixShellArgument $Url)").Trim()
}

function Get-RemoteHttpBody {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Url
    )
    return (Invoke-RemoteText -Name $Name -Command "curl -sS $(Quote-PosixShellArgument $Url)").Trim()
}

function Get-DailyChallengeUrl {
    param([Parameter(Mandatory = $true)][string]$BaseUrl)
    $uri = [Uri]$BaseUrl
    $builder = [UriBuilder]::new($uri)
    $builder.Path = '/api/daily-challenge/today'
    $builder.Query = ''
    return $builder.Uri.AbsoluteUri
}

function Get-RemoteDiskReport {
    $raw = Invoke-RemoteText -Name 'disk_free_kb' -Command "df -Pk / | tail -n 1"
    $parts = [regex]::Split($raw.Trim(), '\s+') | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    if ($parts.Count -lt 6) {
        throw "Disk report is malformed."
    }
    return [ordered]@{
        filesystem = $parts[0]
        available_kb = [int64]$parts[3]
        mount_point = $parts[5]
        raw = $raw.Trim()
    }
}

function Get-RemoteStagingPathStatus {
    param([Parameter(Mandatory = $true)][string]$RemotePath)
    $quotedPath = Quote-PosixShellArgument $RemotePath
    $command = 'path=__REMOTE_PATH__; if [ -d "$path" ]; then if [ -w "$path" ]; then echo existing-writable; else echo existing-not-writable; fi; else parent=$(dirname "$path"); if [ -d "$parent" ] && [ -w "$parent" ]; then echo parent-writable; else echo unavailable; fi; fi'.Replace('__REMOTE_PATH__', $quotedPath)
    return (Invoke-RemoteText -Name 'remote_staging_path_status' -Command $command).Trim()
}

function Assert-ContainerSnapshotValid {
    param(
        [Parameter(Mandatory = $true)]$Snapshot,
        [Parameter(Mandatory = $true)][string]$Name
    )
    if ([string]::IsNullOrWhiteSpace($Snapshot.container_id)) {
        throw "$Name container ID is missing."
    }
    if ([string]::IsNullOrWhiteSpace($Snapshot.image_id)) {
        throw "$Name image ID is missing."
    }
    if ([string]::IsNullOrWhiteSpace($Snapshot.image_ref)) {
        throw "$Name image reference is missing."
    }
    if ($Snapshot.status -ne 'running') {
        throw "$Name container is not running."
    }
    if ($Snapshot.restarting -eq $true) {
        throw "$Name container is restarting."
    }
    if (-not [string]::IsNullOrWhiteSpace($Snapshot.health) -and $Snapshot.health -notin @('healthy', 'n/a')) {
        throw "$Name container health is not healthy."
    }
    if ([string]::IsNullOrWhiteSpace($Snapshot.compose_project) -or [string]::IsNullOrWhiteSpace($Snapshot.compose_service)) {
        throw "$Name compose identity is missing."
    }
}

if ($DryRun) {
    [ordered]@{
        dry_run = $true
        ssh_alias = $layout.ssh_alias
        compose_project = $layout.compose_project
        compose_directory = $layout.compose_directory
        app_service_name = $layout.app_service_name
        scheduler_service_name = $layout.scheduler_service_name
        nginx_service_name = $layout.nginx_service_name
        candidate_release_manifest_exists = $candidateManifestExists
        candidate_release_archive_exists = $candidateArchiveExists
        asset_source_path = $layout.asset_source_path
        asset_container_mount_destination = $layout.asset_container_mount_destination
        questions_content_source_path = $layout.questions_content_source_path
        questions_content_mount_destination = $layout.questions_content_mount_destination
        shadow_event_log_path = $layout.shadow_event_log_path
        runtime_contract = @(
            'QUESTIONS_JSON_PATH',
            'GO_ODYSSEY_LIVE_STATIC_ROOT',
            'DATABASE_URL',
            'SHADOW_EVENTS_PATH'
        )
    } | ConvertTo-Json -Depth 8 | Write-Output
    return
}

$appSnapshot = Get-RemoteContainerSnapshot -ContainerName $layout.app_service_name -ResponseName 'app_container_snapshot'
$schedulerSnapshot = Get-RemoteContainerSnapshot -ContainerName $layout.scheduler_service_name -ResponseName 'scheduler_container_snapshot'
$nginxSnapshot = Get-RemoteContainerSnapshot -ContainerName $layout.nginx_service_name -ResponseName 'nginx_container_snapshot'
Assert-ContainerSnapshotValid -Snapshot $appSnapshot -Name 'App'
Assert-ContainerSnapshotValid -Snapshot $schedulerSnapshot -Name 'Scheduler'
Assert-ContainerSnapshotValid -Snapshot $nginxSnapshot -Name 'Nginx'

$appEnv = Get-RemoteContainerEnvMap -ContainerName $layout.app_service_name -ResponseName 'app_env'
$schedulerEnv = Get-RemoteContainerEnvMap -ContainerName $layout.scheduler_service_name -ResponseName 'scheduler_env'
$appDb = Get-DatabaseIdentitySummary -DatabaseUrl $appEnv['DATABASE_URL']
$schedulerDb = Get-DatabaseIdentitySummary -DatabaseUrl $schedulerEnv['DATABASE_URL']
$readinessMode = Try-Get-RemoteReadinessReport -ContainerName $layout.app_service_name
$expectedQuestionsPath = ($layout.questions_content_mount_destination.TrimEnd('/','\') + '/questions.json')
$questionsPath = if (-not [string]::IsNullOrWhiteSpace($appEnv['QUESTIONS_JSON_PATH'])) { $appEnv['QUESTIONS_JSON_PATH'] } else { $expectedQuestionsPath }
$dailyChallengeUrl = Get-DailyChallengeUrl -BaseUrl $layout.homepage_url
$diskReport = Get-RemoteDiskReport
$remoteStagingStatus = Get-RemoteStagingPathStatus -RemotePath $layout.remote_release_staging_directory
$healthzStatus = Get-RemoteHttpStatus -Name 'healthz_status' -Url $layout.health_url
$healthzBody = Get-RemoteHttpBody -Name 'healthz_body' -Url $layout.health_url
$loginStatus = Get-RemoteHttpStatus -Name 'login_status' -Url $layout.login_url
$homeStatus = Get-RemoteHttpStatus -Name 'home_status' -Url $layout.homepage_url
$dailyChallengeStatus = Get-RemoteHttpStatus -Name 'daily_challenge_status' -Url $dailyChallengeUrl
$archiveSizeBytes = if ($candidateArchiveExists -and $ReleaseArchive) { (Get-Item -LiteralPath (Resolve-RepoPath $ReleaseArchive)).Length } else { 0 }
$requiredFreeBytes = [Math]::Max([int64]1073741824, [int64]($archiveSizeBytes * 4))
$requiredFreeKb = [int64][Math]::Ceiling($requiredFreeBytes / 1024.0)
$questionsReport = $null
if ($readinessMode.mode -eq 'helper') {
    $questionsReport = $readinessMode.report.questions
}
else {
    $questionsReport = Get-RemoteQuestionsReport -ContainerName $layout.app_service_name -QuestionsPath $questionsPath
}

$report = [ordered]@{
    ssh_alias = $layout.ssh_alias
    docker_version = Invoke-RemoteText -Name 'docker_version' -Command 'docker version --format "{{.Server.Version}}"'
    compose_version = Invoke-RemoteText -Name 'compose_version' -Command 'docker compose version --short'
    disk = $diskReport
    current_app = $appSnapshot
    current_scheduler = $schedulerSnapshot
    current_nginx = $nginxSnapshot
    current_project = $appSnapshot.compose_project
    current_compose_directory = $layout.compose_directory
    asset_source = $layout.asset_source_path
    asset_mount_destination = $layout.asset_container_mount_destination
    questions_source = $layout.questions_content_source_path
    questions_mount_destination = $layout.questions_content_mount_destination
    shadow_log_path = $layout.shadow_event_log_path
    app_db_identity = Get-SanitizedDatabaseIdentity -Identity $appDb
    scheduler_db_identity = Get-SanitizedDatabaseIdentity -Identity $schedulerDb
    database_identity_match = (
        $appDb.configured -and $schedulerDb.configured -and
        $appDb.host -eq $schedulerDb.host -and
        $appDb.port -eq $schedulerDb.port -and
        $appDb.database -eq $schedulerDb.database -and
        $appDb.user -eq $schedulerDb.user -and
        $appDb.password_present -eq $schedulerDb.password_present
    )
    helper_available = $readinessMode.helper_available
    readiness_mode = $readinessMode.mode
    questions_json_path = $questionsPath
    questions_json_path_source = $(if (-not [string]::IsNullOrWhiteSpace($appEnv['QUESTIONS_JSON_PATH'])) { 'env' } else { 'derived_from_layout' })
    questions_json_path_matches_mount = $questionsPath -eq $expectedQuestionsPath
    live_static_root = $appEnv['GO_ODYSSEY_LIVE_STATIC_ROOT']
    shadow_events_path = $appEnv['SHADOW_EVENTS_PATH']
    app_health = $appSnapshot.health
    scheduler_health = $schedulerSnapshot.health
    nginx_health = $nginxSnapshot.health
    candidate_release_manifest_exists = $candidateManifestExists
    candidate_release_archive_exists = $candidateArchiveExists
    readiness = $readinessMode.report
    questions = $questionsReport
    healthz_status = $healthzStatus
    healthz_payload = $healthzBody
    login_status = $loginStatus
    home_status = $homeStatus
    daily_challenge_status = $dailyChallengeStatus
    remote_staging_path_status = $remoteStagingStatus
    rollback_identity_available = (
        -not [string]::IsNullOrWhiteSpace($appSnapshot.image_id) -and
        -not [string]::IsNullOrWhiteSpace($schedulerSnapshot.image_id) -and
        -not [string]::IsNullOrWhiteSpace($appSnapshot.image_ref) -and
        -not [string]::IsNullOrWhiteSpace($schedulerSnapshot.image_ref)
    )
}

if (-not $report.database_identity_match) {
    throw "App and scheduler database configuration must match."
}
if ([string]::IsNullOrWhiteSpace($report.questions_json_path)) {
    throw "QUESTIONS_JSON_PATH must be configured or determinable."
}
if (-not $report.questions_json_path_matches_mount) {
    throw "QUESTIONS_JSON_PATH must match the configured questions mount destination."
}
if ($report.healthz_status -ne '200') {
    throw "/healthz did not return 200."
}
if ($report.login_status -ne '200') {
    throw "/login did not return 200."
}
if ($report.home_status -ne '200') {
    throw "/ did not return 200."
}
$healthzJson = $null
try {
    $healthzJson = $report.healthz_payload | ConvertFrom-Json
}
catch {
    throw "/healthz payload was not valid JSON."
}
if (-not $healthzJson.ok) {
    throw "/healthz payload did not report ok=true."
}
if (-not $report.questions.exists) {
    throw "Questions file is missing."
}
if (-not $report.questions.readable) {
    throw "Questions file is not readable."
}
if (-not $report.questions.parseable) {
    throw "Questions file is not parseable JSON."
}
if (-not $report.questions.record_count_ok) {
    throw "Questions file did not satisfy the record-count gate."
}
if ($report.questions.record_count -le 0) {
    throw "Questions dataset is empty."
}
if (-not $report.questions.structural_record_check) {
    throw "Questions file failed the structural record gate."
}
if ($report.daily_challenge_status -eq '503') {
    throw "Daily challenge returned 503."
}
if ($report.disk.available_kb -lt $requiredFreeKb) {
    throw "Production host does not have enough free disk for the release artifact."
}
if ($report.remote_staging_path_status -notin @('existing-writable', 'parent-writable')) {
    throw "Remote staging path is not writable or safely creatable."
}
if (-not $report.rollback_identity_available) {
    throw "Rollback image identity is not available."
}
if ($report.readiness_mode -eq 'helper' -and $report.readiness.ok -ne $true) {
    throw "Runtime readiness helper reported a failing state."
}

Write-Output ($report | ConvertTo-Json -Depth 8)
