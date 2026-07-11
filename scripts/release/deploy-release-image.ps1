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
$composeFilePath = Resolve-RepoPath 'docker-compose.release.yml'
$nginxConfigPath = Resolve-RepoPath 'nginx\default.conf'
$artifactBaseName = Get-ReleaseArtifactBaseName -GitSha $ExpectedGitSha
$deploymentRecordPath = Join-Path (Split-Path -Parent $manifestPath) ("{0}.deployment.json" -f $artifactBaseName)

function Invoke-RemoteCommandResult {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [string]$Command,
        [string]$ScriptText,
        [string]$StdinText
    )
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        if ($PSBoundParameters.ContainsKey('ScriptText')) {
            $normalizedScriptText = $ScriptText -replace "`r`n", "`n" -replace "`r", "`n"
            $rawOutput = $normalizedScriptText | & ssh $layout.ssh_alias 'sh -s' 2>&1
        }
        elseif ($PSBoundParameters.ContainsKey('StdinText')) {
            $normalizedStdinText = $StdinText -replace "`r`n", "`n" -replace "`r", "`n"
            $rawOutput = $normalizedStdinText | & ssh $layout.ssh_alias $Command 2>&1
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
    }
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
    param([Parameter(Mandatory = $true)][string]$ImageTag)
    $pairs = [ordered]@{
        GO_ODYSSEY_IMAGE = $ImageTag
        QUESTIONS_CONTENT_SOURCE_PATH = $layout.questions_content_source_path
        QUESTIONS_CONTENT_MOUNT_DESTINATION = $layout.questions_content_mount_destination
        ASSET_SOURCE_PATH = $layout.asset_source_path
        ASSET_CONTAINER_MOUNT_DESTINATION = $layout.asset_container_mount_destination
        SHADOW_EVENT_LOG_PATH = $layout.shadow_event_log_path
    }
    return (($pairs.GetEnumerator() | ForEach-Object {
        "{0}={1}" -f $_.Key, (Quote-PosixShellArgument ([string]$_.Value))
    }) -join ' ')
}

function Get-RemoteContainerSnapshot {
    param([Parameter(Mandatory = $true)][string]$ContainerName)
    $raw = Invoke-RemoteText "docker inspect $ContainerName --format '{{json .State}}|{{.Config.Image}}|{{.Image}}|{{.Id}}'"
    $parts = $raw -split '\|', 4
    if ($parts.Count -lt 4) {
        throw "Unable to read remote container snapshot for $ContainerName."
    }
    $state = $parts[0] | ConvertFrom-Json
    $health = if ($state.PSObject.Properties.Name -contains 'Health' -and $state.Health) { $state.Health.Status } else { 'n/a' }
    return [ordered]@{
        image_tag = $parts[1]
        image_id = $parts[2]
        container_id = $parts[3]
        state = $state.Status
        health = $health
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
        }
    }
    if (Test-HelperUnavailableOutput -Output $result.output) {
        return [ordered]@{
            mode = 'legacy_fallback'
            report = $null
            helper_available = $false
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
    param([Parameter(Mandatory = $true)][string]$ContainerName)
    $readinessMode = Try-Get-RemoteReadinessReport -ContainerName $ContainerName
    $appEnv = Get-RemoteContainerEnvMap -ContainerName $ContainerName
    $expectedQuestionsPath = ($layout.questions_content_mount_destination.TrimEnd('/','\') + '/questions.json')
    $questionsPath = if (-not [string]::IsNullOrWhiteSpace($appEnv['QUESTIONS_JSON_PATH'])) { $appEnv['QUESTIONS_JSON_PATH'] } else { $expectedQuestionsPath }
    $questionsReport = if ($readinessMode.mode -eq 'helper') { $readinessMode.report.questions } else { Get-RemoteQuestionsReport -ContainerName $ContainerName -QuestionsPath $questionsPath }
    return [ordered]@{
        helper_available = $readinessMode.helper_available
        readiness_mode = $readinessMode.mode
        readiness = $readinessMode.report
        questions_json_path = $questionsPath
        questions = $questionsReport
        healthz_status = Get-RemoteHttpStatus -Url $layout.health_url
        login_status = Get-RemoteHttpStatus -Url $layout.login_url
        home_status = Get-RemoteHttpStatus -Url $layout.homepage_url
        daily_challenge_status = Get-RemoteHttpStatus -Url (Get-DailyChallengeUrl -BaseUrl $layout.homepage_url)
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
$verificationReport = $null
$rollbackRequired = $false

try {
    Invoke-RemoteText "mkdir -p $(Quote-PosixShellArgument $layout.remote_release_staging_directory) $(Quote-PosixShellArgument $layout.compose_directory) $(Quote-PosixShellArgument (Join-RemotePath $layout.compose_directory 'nginx'))"

    & scp $composeFilePath "$($layout.ssh_alias):$remoteComposePath" | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "scp failed while transferring docker-compose.release.yml."
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

    $composeEnvPrefix = Get-RemoteComposeEnvironmentPrefix -ImageTag $manifest.image_tag
    $composeServices = Invoke-RemoteText "cd $(Quote-PosixShellArgument $layout.compose_directory) && $composeEnvPrefix docker compose -f docker-compose.release.yml config --services"
    foreach ($serviceName in @($layout.app_service_name, $layout.scheduler_service_name, $layout.nginx_service_name)) {
        if ($composeServices -notmatch "(?m)^$([Regex]::Escape($serviceName))$") {
            throw "docker compose config did not expose expected service: $serviceName"
        }
    }

    $composeImages = Invoke-RemoteText "cd $(Quote-PosixShellArgument $layout.compose_directory) && $composeEnvPrefix docker compose -f docker-compose.release.yml config --images"
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

    $appBefore = Get-RemoteContainerSnapshot -ContainerName $layout.app_service_name
    $schedulerBefore = Get-RemoteContainerSnapshot -ContainerName $layout.scheduler_service_name
    $appBeforeLabels = Get-RemoteImageLabels -ImageTag $appBefore.image_tag
    $schedulerBeforeLabels = Get-RemoteImageLabels -ImageTag $schedulerBefore.image_tag
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
    }
    $deploymentRecord = New-DeploymentRecord -RollbackIdentity $rollbackIdentity -VerificationResult 'deployment in progress'
    Save-DeploymentRecord -Record $deploymentRecord -Path $deploymentRecordPath
    & scp $deploymentRecordPath "$($layout.ssh_alias):$remoteDeploymentRecordPath" | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "scp failed while transferring the deployment record."
    }

    $rollbackRequired = $true
    Invoke-RemoteText "cd $(Quote-PosixShellArgument $layout.compose_directory) && $composeEnvPrefix docker compose -f docker-compose.release.yml up -d --no-build --force-recreate $($layout.app_service_name)"

    $appAfter = Get-RemoteContainerSnapshot -ContainerName $layout.app_service_name
    if ($appAfter.image_tag -ne $manifest.image_tag) {
        throw "App container is not running the release image."
    }
    if ($appAfter.image_id -ne $ExpectedImageId) {
        throw "App container image ID does not match the release image ID."
    }
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

    Invoke-RemoteText "cd $(Quote-PosixShellArgument $layout.compose_directory) && $composeEnvPrefix docker compose -f docker-compose.release.yml up -d --no-build --force-recreate $($layout.scheduler_service_name)"

    $schedulerAfter = Get-RemoteContainerSnapshot -ContainerName $layout.scheduler_service_name
    if ($schedulerAfter.image_tag -ne $manifest.image_tag) {
        throw "Scheduler container is not running the release image."
    }
    if ($schedulerAfter.image_id -ne $ExpectedImageId) {
        throw "Scheduler container image ID does not match the release image ID."
    }
    if ($appAfter.image_id -ne $schedulerAfter.image_id) {
        throw "App and scheduler image IDs do not match after rollout."
    }

    Invoke-RemoteText "docker restart $(Quote-PosixShellArgument $layout.nginx_service_name)"

    $verificationOutput = & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'verify-production-release.ps1') -ReleaseManifest $deploymentRecordPath -LayoutFile $LayoutFile
    if ($LASTEXITCODE -ne 0) {
        throw "verify-production-release.ps1 failed with exit code $LASTEXITCODE."
    }
    $verificationReport = $verificationOutput | ConvertFrom-Json

    if ($deploymentRecord.Contains('verification_result')) {
        $deploymentRecord['verification_result'] = 'production verified'
    }
    Save-DeploymentRecord -Record $deploymentRecord -Path $deploymentRecordPath
    & scp $deploymentRecordPath "$($layout.ssh_alias):$remoteDeploymentRecordPath" | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "scp failed while updating the remote deployment record."
    }

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
        app_after = $appAfter
        scheduler_after = $schedulerAfter
        app_readiness = $appReadinessReport
        verification = $verificationReport
    } | ConvertTo-Json -Depth 12 | Write-Output
}
catch {
    $deploymentFailureMessage = $_.Exception.Message
    if ($rollbackRequired -and $deploymentRecordPath -and (Test-Path -LiteralPath $deploymentRecordPath)) {
        try {
            $rollbackOutput = & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'rollback-release.ps1') -RollbackManifest $deploymentRecordPath -LayoutFile $LayoutFile -Execute -OwnerGate 'GO_ROLLBACK'
            if ($LASTEXITCODE -ne 0) {
                throw "rollback-release.ps1 failed with exit code $LASTEXITCODE."
            }
            $null = $rollbackOutput | ConvertFrom-Json
            throw "Deployment failed and automatic rollback succeeded: $deploymentFailureMessage"
        }
        catch {
            throw "Deployment failed: $deploymentFailureMessage`nAutomatic rollback failed: $($_.Exception.Message)"
        }
    }
    throw
}
