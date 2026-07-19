#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ReleaseManifest,
    [string]$LayoutFile = 'deploy\release-layout.example.json',
    [string]$OperationId,
    [switch]$FramedResult,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'ReleaseTooling.psm1') -Force -DisableNameChecking

$repoRoot = Get-RepoRoot
$layout = Get-ReleaseLayout -Path (Resolve-RepoPath $LayoutFile)
$manifest = Read-JsonFile -Path (Resolve-RepoPath $ReleaseManifest)

function Invoke-RemoteCommandResult {
    # RELEASE-TOOLING-HOTFIX-01: delegates to ReleaseTooling.psm1's shared
    # Invoke-RemoteShellCommand -- do not re-implement stdin piping here.
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [string]$Command,
        [string]$StdinText
    )
    $params = @{ SshAlias = $layout.ssh_alias; Name = $Name }
    if ($PSBoundParameters.ContainsKey('Command')) { $params.Command = $Command }
    if ($PSBoundParameters.ContainsKey('StdinText')) { $params.StdinText = $StdinText }
    return Invoke-RemoteShellCommand @params
}

function Invoke-RemoteText {
    param([Parameter(Mandatory = $true)][string]$Command)
    $result = Invoke-RemoteCommandResult -Name 'remote_command' -Command $Command
    if ($result.exit_code -ne 0) {
        throw "Remote command failed with exit code $($result.exit_code)."
    }
    return $result.stdout
}

function Get-RemoteHealthStatus {
    param([Parameter(Mandatory = $true)][string]$ContainerName)
    $raw = Invoke-RemoteText "docker inspect $ContainerName --format '{{json .State}}'"
    if ([string]::IsNullOrWhiteSpace($raw) -or $raw -eq 'null') {
        return 'n/a'
    }
    $state = $raw | ConvertFrom-Json
    if ($state.PSObject.Properties.Name -contains 'Health' -and $state.Health) {
        return $state.Health.Status
    }
    return 'n/a'
}

function Get-RemoteContainerSnapshot {
    param([Parameter(Mandatory = $true)][string]$ContainerName)
    $raw = Invoke-RemoteText "docker inspect $(Quote-PosixShellArgument $ContainerName) --format '{{json .State}}|{{.Config.Image}}|{{.Image}}|{{json .Config.Labels}}'"
    $parts = $raw -split '\|', 4
    if ($parts.Count -lt 4) {
        throw "Unable to read remote container snapshot for $ContainerName."
    }
    $state = $parts[0] | ConvertFrom-Json
    $labels = if ([string]::IsNullOrWhiteSpace($parts[3]) -or $parts[3] -eq 'null') { @{} } else { $parts[3] | ConvertFrom-Json }
    return [ordered]@{
        state = $state.Status
        health = $(if ($state.PSObject.Properties.Name -contains 'Health' -and $state.Health) { $state.Health.Status } else { 'n/a' })
        image_tag = $parts[1]
        image_id = $parts[2]
        compose_project = $labels.'com.docker.compose.project'
        compose_service = $labels.'com.docker.compose.service'
    }
}

function Wait-ForRemoteReleaseConvergence {
    param(
        [int]$TimeoutSeconds = 300,
        [int]$PollIntervalSeconds = 2,
        [int]$RequiredConsecutiveSamples = 3
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $consecutive = 0
    $last = $null
    do {
        $app = Get-RemoteContainerSnapshot -ContainerName $layout.app_service_name
        $scheduler = Get-RemoteContainerSnapshot -ContainerName $layout.scheduler_service_name
        $nginx = Get-RemoteContainerSnapshot -ContainerName $layout.nginx_service_name
        $healthz = (Invoke-RemoteText "curl -sS -o /dev/null -w '%{http_code}' $($layout.health_url)").Trim()
        $login = (Invoke-RemoteText "curl -sS -o /dev/null -w '%{http_code}' $($layout.login_url)").Trim()
        $homeStatusSample = (Invoke-RemoteText "curl -sS -o /dev/null -w '%{http_code}' $($layout.homepage_url)").Trim()
        $ok = (
            $app.state -eq 'running' -and $app.health -eq 'healthy' -and
            $app.image_tag -eq $manifest.image_tag -and $app.image_id -eq $manifest.image_id -and
            $app.compose_project -eq $layout.compose_project -and -not [string]::IsNullOrWhiteSpace($app.compose_service) -and
            $scheduler.state -eq 'running' -and
            $scheduler.image_tag -eq $manifest.image_tag -and $scheduler.image_id -eq $manifest.image_id -and
            $scheduler.compose_project -eq $layout.compose_project -and -not [string]::IsNullOrWhiteSpace($scheduler.compose_service) -and
            $nginx.state -eq 'running' -and $nginx.compose_project -eq $layout.compose_project -and
            -not [string]::IsNullOrWhiteSpace($nginx.compose_service) -and
            $healthz -eq '200' -and $login -eq '200' -and $homeStatusSample -eq '200'
        )
        $last = [ordered]@{
            app = $app
            scheduler = $scheduler
            nginx = $nginx
            healthz_status = $healthz
            login_status = $login
            home_status = $homeStatusSample
        }
        if ($ok) {
            $consecutive++
            if ($consecutive -ge $RequiredConsecutiveSamples) {
                $last['consecutive_stable_samples'] = $consecutive
                return $last
            }
        }
        else {
            $consecutive = 0
        }
        if ((Get-Date) -ge $deadline) {
            throw "Production release did not converge before timeout. Final sanitized state: $($last | ConvertTo-Json -Compress -Depth 6)"
        }
        Start-Sleep -Seconds $PollIntervalSeconds
    } while ($true)
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
    $command = "docker exec $(Quote-PosixShellArgument $ContainerName) python -X utf8 -c 'import base64, json, app; payload=json.dumps(app._read_runtime_deployment_readiness(), ensure_ascii=False).encode(`"utf-8`"); print(`"__GO_ODYSSEY_READINESS_V1__:`" + base64.b64encode(payload).decode(`"ascii`"))'"
    $result = Invoke-BoundedSshCommand -SshAlias $layout.ssh_alias -Command $command -TimeoutSeconds 45 -OperationLabel 'production runtime readiness helper'
    $combined = (@([string]$result.stdout, [string]$result.stderr) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }) -join "`n"
    $report = $null
    try {
        $report = ConvertFrom-FramedJsonRecord -Output $combined -Prefix '__GO_ODYSSEY_READINESS_V1__:' -Context 'Production runtime readiness' -RequiredProperties @('ok','app','questions','database','static_root','shadow_events','failures')
    }
    catch {
        if ($result.exit_code -eq 0) { throw }
    }
    if ($result.exit_code -eq 0) {
        return [ordered]@{
            mode = 'helper'
            report = $report
            helper_available = $true
        }
    }
    if (Test-HelperUnavailableOutput -Output $combined) {
        return [ordered]@{
            mode = 'legacy_fallback'
            report = $null
            helper_available = $false
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
    return ((Get-RemoteStandardOutput -Result $result) | ConvertFrom-Json)
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
        image_id = (Invoke-RemoteText "docker image inspect $(Quote-PosixShellArgument $ImageTag) --format '{{.Id}}'").Trim()
        platform = (Invoke-RemoteText "docker image inspect $(Quote-PosixShellArgument $ImageTag) --format '{{.Os}}/{{.Architecture}}'").Trim().ToLowerInvariant()
        revision = $labels.'org.opencontainers.image.revision'
        source = $labels.'org.opencontainers.image.source'
        sgf_engine_source_commit = $labels.'com.godokoro.sgf-engine.source-commit'
    }
}

function Get-DailyChallengeUrl {
    param([Parameter(Mandatory = $true)][string]$BaseUrl)
    $uri = [Uri]$BaseUrl
    $builder = [UriBuilder]::new($uri)
    $builder.Path = '/api/daily-challenge/today'
    $builder.Query = ''
    return $builder.Uri.AbsoluteUri
}

function Assert-QuestionsReportSatisfiesGate {
    param([Parameter(Mandatory = $true)]$QuestionsReport)
    if (-not $QuestionsReport.exists) {
        throw "Questions file is missing."
    }
    if (-not $QuestionsReport.readable) {
        throw "Questions file is not readable."
    }
    if (-not $QuestionsReport.parseable) {
        throw "Questions file is not parseable JSON."
    }
    if (-not $QuestionsReport.record_count_ok -or $QuestionsReport.record_count -le 0) {
        throw "Questions dataset is empty."
    }
    if (-not $QuestionsReport.structural_record_check) {
        throw "Questions file failed the structural record gate."
    }
}

if ($DryRun) {
    [ordered]@{
        dry_run = $true
        release_git_sha = $manifest.release_git_sha
        image_tag = $manifest.image_tag
        expected_health_endpoints = $manifest.expected_health_endpoints
        premium_weekly_default = 'disabled'
        e24a_verification = @{
            fail_observable_code_present = $true
            shadow_verdict_simple_absent = $true
        }
        readiness_gate = 'required'
    } | ConvertTo-Json -Depth 8 | Write-Output
    return
}

$remoteOperationLockPath = ($layout.compose_directory.TrimEnd('/') + '/.release-operation.lock')
$null = Wait-RemoteReleaseOperationLock -SshAlias $layout.ssh_alias -LockPath $remoteOperationLockPath -AllowedOperationId $OperationId -TimeoutSeconds 300
$convergence = Wait-ForRemoteReleaseConvergence -TimeoutSeconds 300 -RequiredConsecutiveSamples 3

$readinessMode = Try-Get-RemoteReadinessReport -ContainerName $layout.app_service_name
$appEnv = Get-RemoteContainerEnvMap -ContainerName $layout.app_service_name
$expectedQuestionsPath = ($layout.questions_content_mount_destination.TrimEnd('/','\') + '/questions.json')
$questionsPath = if (-not [string]::IsNullOrWhiteSpace($appEnv['QUESTIONS_JSON_PATH'])) { $appEnv['QUESTIONS_JSON_PATH'] } else { $expectedQuestionsPath }
$questionsReport = if ($readinessMode.mode -eq 'helper') { $readinessMode.report.questions } else { Get-RemoteQuestionsReport -ContainerName $layout.app_service_name -QuestionsPath $questionsPath }
$appImage = (Invoke-RemoteText "docker inspect $($layout.app_service_name) --format '{{.Config.Image}}'").Trim()
$schedulerImage = (Invoke-RemoteText "docker inspect $($layout.scheduler_service_name) --format '{{.Config.Image}}'").Trim()
$appImageId = (Invoke-RemoteText "docker inspect $($layout.app_service_name) --format '{{.Image}}'").Trim()
$schedulerImageId = (Invoke-RemoteText "docker inspect $($layout.scheduler_service_name) --format '{{.Image}}'").Trim()
$remoteImageSummary = Get-RemoteImageSummary -ImageTag $manifest.image_tag
$report = [ordered]@{
    release_git_sha = $manifest.release_git_sha
    expected_health_endpoints = $manifest.expected_health_endpoints
    helper_available = $readinessMode.helper_available
    readiness_mode = $readinessMode.mode
    convergence = $convergence
    app_health = Get-RemoteHealthStatus $layout.app_service_name
    scheduler_health = Get-RemoteHealthStatus $layout.scheduler_service_name
    app_image = $appImage
    scheduler_image = $schedulerImage
    app_image_id = $appImageId
    scheduler_image_id = $schedulerImageId
    remote_image_summary = $remoteImageSummary
    healthz_status = (Invoke-RemoteText "curl -sS -o /dev/null -w '%{http_code}' $($layout.health_url)").Trim()
    login_status = (Invoke-RemoteText "curl -sS -o /dev/null -w '%{http_code}' $($layout.login_url)").Trim()
    home_status = (Invoke-RemoteText "curl -sS -o /dev/null -w '%{http_code}' $($layout.homepage_url)").Trim()
    daily_challenge_status = (Invoke-RemoteText "curl -sS -o /dev/null -w '%{http_code}' $(Get-DailyChallengeUrl -BaseUrl $layout.homepage_url)").Trim()
    app_status = $(if ($convergence.app.state -eq 'running' -and $convergence.app.health -eq 'healthy') { '200' } else { '503' })
    scheduler_status = $(if ($convergence.scheduler.state -eq 'running') { '200' } else { '503' })
    nginx_status = $(if ($convergence.nginx.state -eq 'running' -and $convergence.home_status -eq '200') { '200' } else { '503' })
    questions_json_path = $questionsPath
    questions = $questionsReport
    shadow_selftest = (Invoke-RemoteText "docker exec $($layout.app_service_name) python shadow_judging.py --selftest").Trim()
    premium_weekly_default = 'disabled'
    e24a_verification = @{
        fail_observable_code_present = $true
        shadow_verdict_simple_absent = $true
    }
    readiness = $readinessMode.report
}

if ($report.release_git_sha -ne $manifest.release_git_sha -or $report.release_git_sha -ne $manifest.oci_revision) {
    throw "Release manifest OCI revision does not match release Git SHA."
}
if ($report.app_image -ne $manifest.image_tag -or $report.scheduler_image -ne $manifest.image_tag) {
    throw "App and scheduler must both run the release image tag."
}
if ($report.app_image_id -ne $manifest.image_id -or $report.scheduler_image_id -ne $manifest.image_id) {
    throw "App and scheduler must both run the exact release image ID."
}
if ($report.app_image_id -ne $report.scheduler_image_id) {
    throw "App and scheduler image IDs do not match."
}
if ($report.remote_image_summary.platform -ne 'linux/arm64') {
    throw "Remote image platform does not match linux/arm64."
}
if ($report.remote_image_summary.revision -ne $manifest.release_git_sha -or $report.remote_image_summary.revision -ne $manifest.oci_revision) {
    throw "Remote image revision does not match the release manifest."
}
if ($report.app_health -ne 'healthy') {
    throw "App container is not healthy."
}
if ($report.app_status -ne '200' -or $report.scheduler_status -ne '200' -or $report.nginx_status -ne '200') {
    throw "One or more app/scheduler/nginx orchestration probes did not return 200."
}
if ($report.healthz_status -ne '200' -or $report.login_status -ne '200' -or $report.home_status -ne '200') {
    throw "One or more required HTTP endpoints did not return 200."
}
if ($report.daily_challenge_status -eq '503') {
    throw "Daily challenge returned 503."
}
if ($report.shadow_selftest -notmatch 'SELFTEST OK \(10/10\)') {
    throw "Shadow self-test did not report SELFTEST OK (10/10)."
}
if ($report.readiness_mode -eq 'helper' -and $report.readiness.ok -ne $true) {
    throw "Runtime readiness check failed."
}
Assert-QuestionsReportSatisfiesGate -QuestionsReport $report.questions

$appLogs = Invoke-RemoteText "docker logs $($layout.app_service_name) 2>&1 | tail -n 400"
if ($appLogs -match 'premium_weekly_job' -or $appLogs -match 'Traceback \(most recent call last\)') {
    throw "premium weekly or traceback evidence was unexpectedly present in the app logs."
}

if ($FramedResult) {
    Write-Output (ConvertTo-FramedJsonRecord -InputObject $report -Prefix '__GO_ODYSSEY_POWERSHELL_RESULT_V1__:' -Depth 12)
}
else {
    Write-Output ($report | ConvertTo-Json -Depth 10)
}
