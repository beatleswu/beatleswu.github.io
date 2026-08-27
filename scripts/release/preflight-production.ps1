#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$LayoutFile = 'deploy\release-layout.example.json',
    [string]$ReleaseManifest = 'deploy\release-manifest.example.json',
    [string]$ReleaseArchive,
    [string]$StaticManifest,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
# Machine-readable output (the final ConvertTo-Json report, and any fail-closed
# gate message a caller greps for) must be valid UTF-8 regardless of the host's
# active code page. Without this, an uncaught terminating error is instead
# formatted and written by PowerShell's own top-level handler using the
# console's default (locale-dependent) encoding, and in a non-English-locale
# Windows install that handler's own boilerplate text (e.g. the localized "at
# <script>:<line>" header) is emitted in that locale, not UTF-8 -- corrupting
# the byte stream for any strict-UTF-8 reader even though every message this
# script itself writes is plain ASCII.
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
trap {
    # Emit only this script's own ASCII gate-violation message, bypassing
    # PowerShell's default unhandled-exception formatting (the source of the
    # locale-dependent bytes above). Fail-closed behavior is unchanged: same
    # message text, same non-zero exit.
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
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
    # RELEASE-TOOLING-HOTFIX-01: the actual ssh/stdin invocation now lives
    # once, shared, in ReleaseTooling.psm1's Invoke-RemoteShellCommand --
    # do not re-implement stdin piping here. This wrapper only adds
    # preflight's fake-remote-response test seam on top of it.
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [string]$Command,
        [string]$ScriptText,
        [string]$StdinText
    )
    if ($script:FakeRemoteResponses) {
        $fake = Get-FakeRemoteResponse -Name $Name
        return [ordered]@{
            name = $Name
            output = [string]$fake.stdout
            stdout = [string]$fake.stdout
            stderr = [string]$(if ($fake.PSObject.Properties.Name -contains 'stderr') { $fake.stderr } else { '' })
            exit_code = [int]$(if ($fake.PSObject.Properties.Name -contains 'exit_code') { $fake.exit_code } else { 0 })
            mode = 'fake'
        }
    }
    $params = @{ SshAlias = $layout.ssh_alias; Name = $Name }
    if ($PSBoundParameters.ContainsKey('Command')) { $params.Command = $Command }
    if ($PSBoundParameters.ContainsKey('ScriptText')) { $params.ScriptText = $ScriptText }
    if ($PSBoundParameters.ContainsKey('StdinText')) { $params.StdinText = $StdinText }
    try {
        $result = Invoke-RemoteShellCommand @params
    }
    catch {
        # Preflight remote probes are read-only. Allow one bounded retry only
        # when the SSH/process invocation throws before a result exists.
        # A returned non-zero exit code remains a single, fail-closed result.
        Start-Sleep -Milliseconds 250
        $result = Invoke-RemoteShellCommand @params
    }
    $result.mode = 'ssh'
    return $result
}

function Invoke-RemoteText {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Command
    )
    $result = Invoke-RemoteCommandResult -Name $Name -Command $Command
    if ($result.exit_code -ne 0) {
        throw "Remote command failed [$Name] with exit code $($result.exit_code)."
    }
    return $result.stdout
}

function Invoke-RemoteScriptText {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$ScriptText
    )
    $result = Invoke-RemoteCommandResult -Name $Name -ScriptText $ScriptText
    if ($result.exit_code -ne 0) {
        throw "Remote script failed [$Name] with exit code $($result.exit_code)."
    }
    return $result.stdout
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

$script:ExactRemoteEnvKeys = @(
    'DATABASE_URL',
    'QUESTIONS_JSON_PATH',
    'GO_ODYSSEY_LIVE_STATIC_ROOT',
    'SHADOW_EVENTS_PATH'
)

function Get-RemoteExactEnvValue {
    <#
    Read one allow-listed container environment key without returning the
    container's full environment. Docker's template ranges the environment
    internally but emits only the exact requested entry. A missing entry is
    the only non-error empty result; malformed, duplicate, ambiguous, or
    present-but-empty results fail closed.
    #>
    param(
        [Parameter(Mandatory = $true)][string]$ContainerName,
        [Parameter(Mandatory = $true)][string]$Key,
        [Parameter(Mandatory = $true)][string]$ResponseName
    )
    if ($script:ExactRemoteEnvKeys -notcontains $Key) {
        throw "Remote environment key is not allow-listed: $Key"
    }
    $template = '{{range .Config.Env}}{{if or (eq . "__KEY__") (hasPrefix . "__KEY__=")}}{{println .}}{{end}}{{end}}'.Replace('__KEY__', $Key)
    $raw = Invoke-RemoteText -Name $ResponseName -Command "docker inspect $(Quote-PosixShellArgument $ContainerName) --format '$template'"
    if ([string]::IsNullOrWhiteSpace($raw)) {
        return $null
    }

    $entries = @(
        $raw -split "`r?`n" |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    )
    if ($entries.Count -ne 1) {
        throw "$Key exact-key probe was duplicated or ambiguous."
    }

    $entry = [string]$entries[0]
    $prefix = "$Key="
    if (-not $entry.StartsWith($prefix, [System.StringComparison]::Ordinal)) {
        throw "$Key exact-key probe returned a malformed entry."
    }
    $value = $entry.Substring($prefix.Length)
    if ([string]::IsNullOrWhiteSpace($value)) {
        throw "$Key exact-key probe returned an empty value."
    }
    return $value
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
    try {
        $uri = [Uri]$value
    }
    catch {
        throw 'DATABASE_URL is malformed.'
    }
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
    param(
        [Parameter(Mandatory = $true)][string]$ContainerName,
        [Parameter(Mandatory = $true)][string]$ResponseName,
        [ValidateSet('app', 'scheduler')][string]$Role = 'app'
    )
    if ($Role -eq 'scheduler') {
        return Get-RemoteSchedulerReadinessReport -ContainerName $ContainerName -ResponseName $ResponseName
    }
    $command = "docker exec $(Quote-PosixShellArgument $ContainerName) python -X utf8 -c 'import base64, json, app; payload=json.dumps(app._read_runtime_deployment_readiness(), ensure_ascii=False).encode(`"utf-8`"); print(`"__GO_ODYSSEY_READINESS_V1__:`" + base64.b64encode(payload).decode(`"ascii`"))'"
    $result = if ($env:GO_ODYSSEY_PREFLIGHT_FAKE_REMOTE_RESPONSES) {
        $fake = Invoke-RemoteCommandResult -Name $ResponseName -Command $command
        [ordered]@{ stdout = [string]$fake.output; stderr = ''; output = [string]$fake.output; exit_code = $fake.exit_code; elapsed_seconds = 0; timed_out = $false }
    }
    else {
        Invoke-BoundedSshCommand -SshAlias $layout.ssh_alias -Command $command -TimeoutSeconds 45 -OperationLabel 'preflight runtime readiness helper'
    }
    $combined = (@([string]$result.stdout, [string]$result.stderr) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }) -join "`n"
    $report = $null
    try {
        $report = ConvertFrom-FramedJsonRecord -Output $combined -Prefix '__GO_ODYSSEY_READINESS_V1__:' -Context 'Preflight runtime readiness' -RequiredProperties @('ok','app','questions','database','static_root','shadow_events','failures')
    }
    catch {
        if ($result.exit_code -eq 0) { throw }
    }
    if ($result.exit_code -eq 0) {
        return [ordered]@{
            mode = 'helper'
            report = $report
            helper_available = $true
            helper_output = '__GO_ODYSSEY_READINESS_V1__:<validated>'
        }
    }
    if (Test-HelperUnavailableOutput -Output $combined) {
        return [ordered]@{
            mode = 'legacy_fallback'
            report = $null
            helper_available = $false
            helper_output = 'legacy helper unavailable'
        }
    }
    throw "Runtime readiness helper failed unexpectedly with exit code $($result.exit_code)."
}

function Get-RemoteSchedulerReadinessReport {
    <#
    Scheduler readiness is deliberately a different contract from the web
    application's deployment-readiness helper.  The standalone scheduler
    imports app.py, but its entrypoint does not load the question dataset,
    serve live static assets, or write shadow events.  Calling the app helper
    for this role would therefore turn app-only paths into a false scheduler
    gate.

    This probe remains read-only.  It checks the scheduler entrypoint/module,
    the database connection and tables used by the scheduler's current jobs,
    and the conditional reward-operation path.  It never calls init_db() or a
    reward cycle, and it emits no environment values.
    #>
    param(
        [Parameter(Mandatory = $true)][string]$ContainerName,
        [Parameter(Mandatory = $true)][string]$ResponseName
    )
    $script = @'
import base64
import importlib.util
import json
import os
import stat
from pathlib import Path

from db import describe_database_url
import app


def _env_flag(name):
    return (os.environ.get(name) or '').strip().lower() in {'1', 'true', 'yes', 'on'}


def _exact_true(name):
    return (os.environ.get(name) or '').strip().lower() == 'true'


def _module_report(name, required):
    report = {
        'required': bool(required),
        'present': False,
        'importable': False,
        'path': '',
    }
    try:
        spec = importlib.util.find_spec(name)
        origin = str(getattr(spec, 'origin', '') or '') if spec else ''
        report['path'] = origin
        report['present'] = bool(origin) and Path(origin).is_file()
        if required:
            importlib.import_module(name)
            report['importable'] = spec is not None and origin not in ('', 'built-in', 'frozen')
    except Exception:
        report['path'] = ''
    return report


community_enabled = _exact_true('COMMUNITY_LEADERBOARD_REWARDS_ENABLED')
premium_enabled = _env_flag('PREMIUM_WEEKLY_SCHEDULER_ENABLED')
failures = []

app_git_sha = ''
for env_name in ('APP_GIT_SHA', 'SOURCE_VERSION', 'GIT_COMMIT'):
    value = str(os.environ.get(env_name) or '').strip()
    if value:
        app_git_sha = value
        break

database = {
    'identity': describe_database_url(os.environ.get('DATABASE_URL')),
    'reachable': False,
    'tables': {},
    'failures': [],
}
required_tables = ['users', 'review_log', 'user_stats']
if community_enabled:
    required_tables.extend([
        'player_appearance',
        'leaderboard_snapshots',
        'leaderboard_reward_claims',
        'leaderboard_reward_component_log',
    ])
try:
    with app.get_db() as conn:
        conn.execute('SELECT 1')
        database['reachable'] = True
        for table in required_tables:
            try:
                conn.execute('SELECT 1 FROM ' + table + ' LIMIT 1')
                database['tables'][table] = {'ok': True}
            except Exception as exc:
                database['tables'][table] = {'ok': False, 'error': exc.__class__.__name__}
                database['failures'].append(table + ' unavailable')
except Exception as exc:
    database['failures'].append('database connection failed: ' + exc.__class__.__name__)

scheduler_module = _module_report('scheduler', True)
community_module = _module_report('community_leaderboard_rewards_scheduler', community_enabled)
scheduler = {
    'entrypoint': {
        'path': scheduler_module['path'],
        'present': scheduler_module['present'],
        'importable': scheduler_module['importable'],
        'required': True,
    },
    'community_job': {
        'enabled': community_enabled,
        'module_present': community_module['present'],
        'module_importable': community_module['importable'],
        'required': community_enabled,
    },
    'premium_job': {
        'enabled': premium_enabled,
        'supported': not premium_enabled,
        'required': True,
    },
}

if not scheduler['entrypoint']['present'] or not scheduler['entrypoint']['importable']:
    failures.append('scheduler entrypoint is unavailable')
if premium_enabled:
    failures.append('unsupported premium scheduler is enabled')
if community_enabled and (
    not community_module['present'] or not community_module['importable']
):
    failures.append('community scheduler module is unavailable')

if community_enabled:
    try:
        from community_leaderboard_rewards_scheduler import DEFAULT_OPERATIONS_ROOT
        operations_root = Path(DEFAULT_OPERATIONS_ROOT)
        parent = operations_root.parent
        if operations_root.exists():
            mode = operations_root.stat().st_mode
            operations_ready = (
                operations_root.is_dir()
                and not operations_root.is_symlink()
                and not bool(mode & stat.S_IWOTH)
                and os.access(operations_root, os.W_OK)
            )
        else:
            operations_ready = (
                parent.is_dir()
                and not parent.is_symlink()
                and os.access(parent, os.W_OK)
            )
        scheduler['community_job']['operations_root'] = {
            'required': True,
            'path': str(operations_root),
            'ready': operations_ready,
        }
        if not operations_ready:
            failures.append('community reward operations path is unavailable')
    except Exception:
        scheduler['community_job']['operations_root'] = {
            'required': True,
            'path': '',
            'ready': False,
        }
        failures.append('community reward operations path is unavailable')
else:
    scheduler['community_job']['operations_root'] = {
        'required': False,
        'path': '',
        'ready': True,
    }

report = {
    'ok': False,
    'role': 'scheduler',
    'app': {
        'git_sha': app_git_sha,
        'image_revision': app_git_sha,
    },
    'database': database,
    'scheduler': scheduler,
    'questions': {'required': False, 'status': 'not_required'},
    'static_root': {'required': False, 'status': 'not_required'},
    'shadow_events': {'required': False, 'status': 'not_required'},
    'failures': failures + database['failures'],
}
if not app_git_sha:
    report['failures'].append('scheduler app git sha is missing')
if not database['reachable'] and not database['failures']:
    report['failures'].append('scheduler database is not reachable')
report['ok'] = len(report['failures']) == 0
payload = json.dumps(report, ensure_ascii=False).encode('utf-8')
print('__GO_ODYSSEY_SCHEDULER_READINESS_V1__:' + base64.b64encode(payload).decode('ascii'))
'@
    $result = Invoke-RemoteCommandResult `
        -Name $ResponseName `
        -Command "docker exec -i $(Quote-PosixShellArgument $ContainerName) python -X utf8 -" `
        -StdinText $script
    $combined = (@([string]$result.stdout, [string]$result.stderr) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }) -join "`n"
    if ($result.exit_code -ne 0) {
        throw "Scheduler readiness probe failed with exit code $($result.exit_code)."
    }
    $report = ConvertFrom-FramedJsonRecord `
        -Output $combined `
        -Prefix '__GO_ODYSSEY_SCHEDULER_READINESS_V1__:' `
        -Context 'Scheduler runtime readiness' `
        -RequiredProperties @('ok', 'role', 'app', 'database', 'scheduler', 'questions', 'static_root', 'shadow_events', 'failures')
    return [ordered]@{
        mode = 'scheduler_probe'
        report = $report
        helper_available = $true
        helper_output = '__GO_ODYSSEY_SCHEDULER_READINESS_V1__:<validated>'
    }
}

function Resolve-RemoteRuntimeConfig {
    param(
        [Parameter(Mandatory = $true)][string]$ContainerName,
        [Parameter(Mandatory = $true)][string]$ContainerLabel,
        [Parameter(Mandatory = $true)][string]$ResponsePrefix,
        [Parameter(Mandatory = $true)]$ReadinessMode,
        [Parameter(Mandatory = $true)][string]$ExpectedQuestionsPath
    )
    if ($ReadinessMode.mode -eq 'helper') {
        $readiness = $ReadinessMode.report
        $identity = $readiness.database.identity
        if (-not $identity) {
            throw "$ContainerLabel runtime readiness omitted database identity."
        }
        $questionsPath = [string]$readiness.questions.path
        if ([string]::IsNullOrWhiteSpace($questionsPath)) {
            $questionsPath = [string]$readiness.questions.configured_path
        }
        if ([string]::IsNullOrWhiteSpace($questionsPath)) {
            $questionsPath = $ExpectedQuestionsPath
        }
        return [ordered]@{
            database_identity = [ordered]@{
                configured = [bool]$identity.configured
                host = [string]$identity.host
                port = $identity.port
                database = [string]$identity.database
                user = [string]$identity.user
                password_present = [bool]$identity.password_present
            }
            questions_path = $questionsPath
            questions_path_source = 'helper'
            live_static_root = [string]$readiness.static_root.path
            shadow_events_path = [string]$readiness.shadow_events.path
        }
    }

    $databaseUrl = Get-RemoteExactEnvValue `
        -ContainerName $ContainerName `
        -Key 'DATABASE_URL' `
        -ResponseName ("{0}_DATABASE_URL" -f $ResponsePrefix)
    if ([string]::IsNullOrWhiteSpace($databaseUrl)) {
        throw "$ContainerLabel DATABASE_URL is unavailable."
    }
    $configuredQuestionsPath = Get-RemoteExactEnvValue `
        -ContainerName $ContainerName `
        -Key 'QUESTIONS_JSON_PATH' `
        -ResponseName ("{0}_QUESTIONS_JSON_PATH" -f $ResponsePrefix)
    $questionsPath = if (-not [string]::IsNullOrWhiteSpace($configuredQuestionsPath)) {
        $configuredQuestionsPath
    }
    else {
        $ExpectedQuestionsPath
    }
    $liveStaticRoot = Get-RemoteExactEnvValue `
        -ContainerName $ContainerName `
        -Key 'GO_ODYSSEY_LIVE_STATIC_ROOT' `
        -ResponseName ("{0}_GO_ODYSSEY_LIVE_STATIC_ROOT" -f $ResponsePrefix)
    $shadowEventsPath = Get-RemoteExactEnvValue `
        -ContainerName $ContainerName `
        -Key 'SHADOW_EVENTS_PATH' `
        -ResponseName ("{0}_SHADOW_EVENTS_PATH" -f $ResponsePrefix)
    return [ordered]@{
        database_identity = Get-DatabaseIdentitySummary -DatabaseUrl $databaseUrl
        questions_path = $questionsPath
        questions_path_source = $(if ($configuredQuestionsPath) { 'env_exact_key' } else { 'derived_from_layout' })
        live_static_root = [string]$liveStaticRoot
        shadow_events_path = [string]$shadowEventsPath
    }
}

function Resolve-RemoteSchedulerRuntimeConfig {
    param(
        [Parameter(Mandatory = $true)][string]$ContainerName,
        [Parameter(Mandatory = $true)][string]$ContainerLabel,
        [Parameter(Mandatory = $true)][string]$ResponsePrefix,
        [Parameter(Mandatory = $true)]$ReadinessMode
    )
    if ($ReadinessMode.mode -eq 'scheduler_probe') {
        $readiness = $ReadinessMode.report
        $identity = $readiness.database.identity
        if (-not $identity) {
            throw "$ContainerLabel scheduler readiness omitted database identity."
        }
        return [ordered]@{
            database_identity = [ordered]@{
                configured = [bool]$identity.configured
                host = [string]$identity.host
                port = $identity.port
                database = [string]$identity.database
                user = [string]$identity.user
                password_present = [bool]$identity.password_present
            }
            questions_path = $null
            questions_path_source = 'not_required'
            live_static_root = $null
            shadow_events_path = $null
        }
    }

    $databaseUrl = Get-RemoteExactEnvValue `
        -ContainerName $ContainerName `
        -Key 'DATABASE_URL' `
        -ResponseName ("{0}_DATABASE_URL" -f $ResponsePrefix)
    if ([string]::IsNullOrWhiteSpace($databaseUrl)) {
        throw "$ContainerLabel DATABASE_URL is unavailable."
    }
    return [ordered]@{
        database_identity = Get-DatabaseIdentitySummary -DatabaseUrl $databaseUrl
        questions_path = $null
        questions_path_source = 'not_required'
        live_static_root = $null
        shadow_events_path = $null
    }
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
    $json = Get-RemoteStandardOutput -Result $result
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

function Get-RemoteStaticGenerationReport {
    <#
    .SYNOPSIS
    RELEASE-FIX-A: reports the identity of whatever /opt/go-odyssey-static/current
    actually points at today, and (if -StaticManifest was given) whether it
    matches the declared release -- so a stale live-static generation is a
    visible, fail-closed preflight fact, never silently ignored the way it
    was before this Sprint (see docs/deployment/canonical_static_release_contract.md).
    #>
    param(
        [Parameter(Mandatory = $true)][string]$StaticRoot,
        $ExpectedManifest
    )
    $currentTarget = (Invoke-RemoteText -Name 'static_current_target' -Command "readlink -f $(Quote-PosixShellArgument "$StaticRoot/current") 2>/dev/null || true").Trim()
    if ([string]::IsNullOrWhiteSpace($currentTarget)) {
        return [ordered]@{
            current_target = $null
            files = @()
            drift_checked = $false
            drift = $null
        }
    }
    $files = @()
    $drift = $null
    $driftChecked = $false
    if ($ExpectedManifest) {
        $driftChecked = $true
        $drift = $false
        $normalizedFiles = @()
        $expectedPaths = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::Ordinal)
        foreach ($entry in @($ExpectedManifest.files)) {
            $normalizedPath = ([string]$entry.path).Replace('\', '/')
            Assert-SafeRemoteRelativeFilePath -RelativePath $normalizedPath
            if ($normalizedPath -match "[`r`n]") {
                throw "Static manifest contains an unsafe file path: $($entry.path)"
            }
            $expectedSha = ([string]$entry.sha256).ToLowerInvariant()
            if (-not [regex]::IsMatch($expectedSha, '^[0-9a-f]{64}$')) {
                throw "Static manifest contains an invalid SHA-256 for: $normalizedPath"
            }
            if (-not $expectedPaths.Add($normalizedPath)) {
                throw "Static manifest contains a duplicate normalized path: $normalizedPath"
            }
            $normalizedFiles += [pscustomobject]@{ path = $normalizedPath; sha256 = $expectedSha }
        }
        if ($normalizedFiles.Count -eq 0) {
            throw 'Static manifest must contain at least one file.'
        }

        # Full-manifest verification is one remote batch. The generated script
        # first cd's into the resolved generation root and validates every
        # manifest path before feeding it to sha256sum --check --strict.
        $batchScript = New-RemoteBatchShaVerificationScript -RemoteReleaseDir $currentTarget -Files $normalizedFiles
        $batchResult = Invoke-RemoteCommandResult -Name 'static_current_manifest_files' -ScriptText $batchScript
        $observedPaths = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::Ordinal)
        foreach ($line in ($batchResult.output -split "`r?`n" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })) {
            if ($line -match '^(.*): OK$') {
                [void]$observedPaths.Add($Matches[1])
            }
        }
        if ($batchResult.exit_code -ne 0 -or $observedPaths.Count -ne $expectedPaths.Count) {
            $drift = $true
        }
        foreach ($entry in $normalizedFiles) {
            $present = $observedPaths.Contains($entry.path)
            if (-not $present) {
                $drift = $true
            }
            $files += [ordered]@{
                path = $entry.path
                sha256 = $(if ($present -and $batchResult.exit_code -eq 0) { $entry.sha256 } else { $null })
                present = $present
                verified = ($present -and $batchResult.exit_code -eq 0)
            }
        }
    }
    else {
        $script = @"
for f in i18n.js sw.js; do
  path="$currentTarget/`$f"
  if [ -f "`$path" ]; then
    sha256sum "`$path"
  else
    echo "MISSING `$f"
  fi
done
"@
        $raw = Invoke-RemoteScriptText -Name 'static_current_files' -ScriptText $script
        foreach ($line in ($raw -split "`r?`n" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })) {
            if ($line -match '^MISSING\s+(.+)$') {
                $files += [ordered]@{ path = $Matches[1].Trim(); sha256 = $null; present = $false }
            }
            else {
                $parts = $line -split '\s+', 2
                $files += [ordered]@{ path = (Split-Path -Leaf $parts[1].Trim()); sha256 = $parts[0].Trim().ToLowerInvariant(); present = $true }
            }
        }
    }

    return [ordered]@{
        current_target = $currentTarget
        files = $files
        drift_checked = $driftChecked
        drift = $drift
    }
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
        static_release_root = $(if ($layout.PSObject.Properties.Name -contains 'static_release_root') { $layout.static_release_root } else { $null })
        static_manifest_provided = -not [string]::IsNullOrWhiteSpace($StaticManifest)
    } | ConvertTo-Json -Depth 8 | Write-Output
    return
}

$appSnapshot = Get-RemoteContainerSnapshot -ContainerName $layout.app_service_name -ResponseName 'app_container_snapshot'
$schedulerSnapshot = Get-RemoteContainerSnapshot -ContainerName $layout.scheduler_service_name -ResponseName 'scheduler_container_snapshot'
$nginxSnapshot = Get-RemoteContainerSnapshot -ContainerName $layout.nginx_service_name -ResponseName 'nginx_container_snapshot'
Assert-ContainerSnapshotValid -Snapshot $appSnapshot -Name 'App'
Assert-ContainerSnapshotValid -Snapshot $schedulerSnapshot -Name 'Scheduler'
Assert-ContainerSnapshotValid -Snapshot $nginxSnapshot -Name 'Nginx'

$expectedQuestionsPath = ($layout.questions_content_mount_destination.TrimEnd('/','\') + '/questions.json')
$readinessMode = Try-Get-RemoteReadinessReport -ContainerName $layout.app_service_name -ResponseName 'app_helper_readiness'
$schedulerReadinessMode = Try-Get-RemoteReadinessReport -ContainerName $layout.scheduler_service_name -ResponseName 'scheduler_helper_readiness' -Role 'scheduler'
$appRuntimeConfig = Resolve-RemoteRuntimeConfig -ContainerName $layout.app_service_name -ContainerLabel 'App' -ResponsePrefix 'app' -ReadinessMode $readinessMode -ExpectedQuestionsPath $expectedQuestionsPath
$schedulerRuntimeConfig = Resolve-RemoteSchedulerRuntimeConfig -ContainerName $layout.scheduler_service_name -ContainerLabel 'Scheduler' -ResponsePrefix 'scheduler' -ReadinessMode $schedulerReadinessMode
$appDb = $appRuntimeConfig.database_identity
$schedulerDb = $schedulerRuntimeConfig.database_identity
$questionsPath = $appRuntimeConfig.questions_path
$dailyChallengeUrl = Get-DailyChallengeUrl -BaseUrl $layout.homepage_url
$diskReport = Get-RemoteDiskReport
$remoteStagingStatus = Get-RemoteStagingPathStatus -RemotePath $layout.remote_release_staging_directory
$healthzStatus = Get-RemoteHttpStatus -Name 'healthz_status' -Url $layout.health_url
$healthzBody = Get-RemoteHttpBody -Name 'healthz_body' -Url $layout.health_url
$loginStatus = Get-RemoteHttpStatus -Name 'login_status' -Url $layout.login_url
$homeStatus = Get-RemoteHttpStatus -Name 'home_status' -Url $layout.homepage_url
$dailyChallengeStatus = Get-RemoteHttpStatus -Name 'daily_challenge_status' -Url $dailyChallengeUrl
$staticExpectedManifest = $null
if (-not [string]::IsNullOrWhiteSpace($StaticManifest)) {
    $staticExpectedManifest = Read-JsonFile -Path (Resolve-RepoPath $StaticManifest)
}
$staticGenerationReport = $null
if ($layout.PSObject.Properties.Name -contains 'static_release_root' -and -not [string]::IsNullOrWhiteSpace($layout.static_release_root)) {
    $staticGenerationReport = Get-RemoteStaticGenerationReport -StaticRoot $layout.static_release_root -ExpectedManifest $staticExpectedManifest
}
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
    questions_json_path_source = $appRuntimeConfig.questions_path_source
    questions_json_path_matches_mount = $questionsPath -eq $expectedQuestionsPath
    live_static_root = $appRuntimeConfig.live_static_root
    shadow_events_path = $appRuntimeConfig.shadow_events_path
    app_health = $appSnapshot.health
    scheduler_health = $schedulerSnapshot.health
    nginx_health = $nginxSnapshot.health
    candidate_release_manifest_exists = $candidateManifestExists
    candidate_release_archive_exists = $candidateArchiveExists
    readiness = $readinessMode.report
    questions = $questionsReport
    scheduler_readiness = $schedulerReadinessMode.report
    scheduler_readiness_mode = $schedulerReadinessMode.mode
    scheduler_helper_available = $schedulerReadinessMode.helper_available
    healthz_status = $healthzStatus
    healthz_payload = $healthzBody
    login_status = $loginStatus
    home_status = $homeStatus
    daily_challenge_status = $dailyChallengeStatus
    remote_staging_path_status = $remoteStagingStatus
    static_generation = $staticGenerationReport
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
if ($report.scheduler_readiness_mode -eq 'scheduler_probe' -and $report.scheduler_readiness.ok -ne $true) {
    throw "Scheduler runtime readiness probe reported a failing state."
}
if ($report.static_generation -and $report.static_generation.drift_checked -and $report.static_generation.drift -eq $true) {
    throw "STATIC GENERATION DRIFT: production's live-static current ($($report.static_generation.current_target)) does not match the declared static release manifest ($($staticExpectedManifest.static_generation_id)). This is exactly the RELEASE-FIX-A class of defect -- do not proceed without deploying the matching static release first."
}

Write-Output ($report | ConvertTo-Json -Depth 8)
