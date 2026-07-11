#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$RollbackManifest,
    [string]$LayoutFile = 'deploy\release-layout.example.json',
    [switch]$Execute,
    [string]$OwnerGate
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'ReleaseTooling.psm1') -Force -DisableNameChecking

$repoRoot = Get-RepoRoot
$layout = Get-ReleaseLayout -Path (Resolve-RepoPath $LayoutFile)
$manifest = Read-JsonFile -Path (Resolve-RepoPath $RollbackManifest)
$rollbackArtifactsRoot = Resolve-RepoPath 'release-artifacts'
Ensure-Directory -Path $rollbackArtifactsRoot

function Invoke-RemoteCommandResult {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [string]$Command,
        [string]$StdinText
    )
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        if ($PSBoundParameters.ContainsKey('StdinText')) {
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

function Assert-QuestionsReportSatisfiesGate {
    param([Parameter(Mandatory = $true)]$QuestionsReport)
    if (-not $QuestionsReport.exists) {
        throw "Questions file is missing after rollback."
    }
    if (-not $QuestionsReport.readable) {
        throw "Questions file is not readable after rollback."
    }
    if (-not $QuestionsReport.parseable) {
        throw "Questions file is not parseable JSON after rollback."
    }
    if (-not $QuestionsReport.record_count_ok -or $QuestionsReport.record_count -le 0) {
        throw "Questions dataset is empty after rollback."
    }
    if (-not $QuestionsReport.structural_record_check) {
        throw "Questions file failed the structural record gate after rollback."
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

function New-RollbackVerificationManifest {
    param(
        [Parameter(Mandatory = $true)][string]$RollbackImageTag,
        [Parameter(Mandatory = $true)][string]$RollbackGitSha,
        [Parameter(Mandatory = $true)][string]$RollbackImageId
    )
    return New-ReleaseManifestObject `
        -GitSha $RollbackGitSha `
        -ImageTag $RollbackImageTag `
        -ImageId $RollbackImageId `
        -ArchiveFilename ("rollback-{0}.tar" -f (Get-ShortGitSha -GitSha $RollbackGitSha)) `
        -ArchiveSha256 ('0' * 64) `
        -BuildTimestamp ([DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')) `
        -BuildMachineIdentityClass 'rollback-verification' `
        -TargetServiceNames @($layout.app_service_name, $layout.scheduler_service_name) `
        -ExternalContentRequirements $manifest.external_content_requirements `
        -ExpectedHealthEndpoints $manifest.expected_health_endpoints `
        -RollbackImageIdentity ([ordered]@{}) `
        -VerificationResult 'rollback verification pending' `
        -DeploymentTimestamp ([DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')) `
        -OCIRevision $RollbackGitSha `
        -OCIImageSource $manifest.oci_source `
        -SGFEngineSourceCommit $manifest.sgf_engine_source_commit
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

$rollbackManifestPath = Join-Path $rollbackArtifactsRoot ("{0}.rollback.json" -f (Get-ReleaseArtifactBaseName -GitSha $manifest.release_git_sha))
$rollbackVerificationManifestPath = Join-Path $rollbackArtifactsRoot ("{0}.rollback-verify.json" -f (Get-ReleaseArtifactBaseName -GitSha $manifest.release_git_sha))

if (-not $Execute) {
    [ordered]@{
        dry_run = $true
        execute_requested = $false
        rollback_manifest = $manifest
        compose_project = $layout.compose_project
        target_services = @($layout.app_service_name, $layout.scheduler_service_name)
        required_owner_gate = 'GO_ROLLBACK'
        rollback_plan = @(
            'validate rollback target',
            'capture current app and scheduler identity',
            'restore app first',
            'verify app health and runtime readiness',
            'restore scheduler',
            'verify both services use the rollback image',
            'restart nginx',
            'run rollback verification',
            'preserve candidate evidence'
        )
    } | ConvertTo-Json -Depth 12 | Write-Output
    return
}

Assert-OwnerGate -Provided $OwnerGate -Expected 'GO_ROLLBACK'

if (-not ($manifest.PSObject.Properties.Name -contains 'rollback_image_identity')) {
    throw "Rollback manifest is missing rollback_image_identity."
}

$rollbackIdentity = $manifest.rollback_image_identity
$rollbackImageTag = $rollbackIdentity.previous_app_image_tag
if ([string]::IsNullOrWhiteSpace($rollbackImageTag)) {
    $rollbackImageTag = $rollbackIdentity.previous_scheduler_image_tag
}
$rollbackGitSha = $rollbackIdentity.previous_app_release_git_sha
if ([string]::IsNullOrWhiteSpace($rollbackGitSha)) {
    $rollbackGitSha = $rollbackIdentity.previous_scheduler_release_git_sha
}
$rollbackImageId = $rollbackIdentity.previous_app_image_id
if ([string]::IsNullOrWhiteSpace($rollbackImageId)) {
    $rollbackImageId = $rollbackIdentity.previous_scheduler_image_id
}

if ([string]::IsNullOrWhiteSpace($rollbackImageTag) -or [string]::IsNullOrWhiteSpace($rollbackGitSha) -or [string]::IsNullOrWhiteSpace($rollbackImageId)) {
    throw "Rollback manifest does not contain an actionable rollback image identity."
}
if ($rollbackIdentity.previous_app_image_tag -and $rollbackIdentity.previous_scheduler_image_tag -and $rollbackIdentity.previous_app_image_tag -ne $rollbackIdentity.previous_scheduler_image_tag) {
    throw "Rollback manifest records mismatched app and scheduler image tags."
}
if ($rollbackIdentity.previous_app_release_git_sha -and $rollbackIdentity.previous_scheduler_release_git_sha -and $rollbackIdentity.previous_app_release_git_sha -ne $rollbackIdentity.previous_scheduler_release_git_sha) {
    throw "Rollback manifest records mismatched app and scheduler release SHAs."
}

$appBefore = Get-RemoteContainerSnapshot -ContainerName $layout.app_service_name
$schedulerBefore = Get-RemoteContainerSnapshot -ContainerName $layout.scheduler_service_name
$appBeforeLabels = Get-RemoteImageLabels -ImageTag $appBefore.image_tag
$schedulerBeforeLabels = Get-RemoteImageLabels -ImageTag $schedulerBefore.image_tag

$rollbackVerificationManifest = New-RollbackVerificationManifest -RollbackImageTag $rollbackImageTag -RollbackGitSha $rollbackGitSha -RollbackImageId $rollbackImageId
Write-JsonFile -InputObject $rollbackVerificationManifest -Path $rollbackVerificationManifestPath
$composeEnvPrefix = Get-RemoteComposeEnvironmentPrefix -ImageTag $rollbackImageTag

Invoke-RemoteText "cd $(Quote-PosixShellArgument $layout.compose_directory) && $composeEnvPrefix docker compose -f docker-compose.release.yml up -d --no-build --force-recreate $($layout.app_service_name)"

$appAfter = Get-RemoteContainerSnapshot -ContainerName $layout.app_service_name
if ($appAfter.image_tag -ne $rollbackImageTag) {
    throw "App container did not switch to the rollback image."
}
if ($appAfter.image_id -ne $rollbackImageId) {
    throw "App container image ID does not match the rollback image ID."
}
if ($appAfter.health -ne 'healthy') {
    throw "App container is not healthy after rollback."
}

$appReadinessReport = Get-AppReadinessGateReport -ContainerName $layout.app_service_name
if ($appReadinessReport.readiness_mode -eq 'helper' -and $appReadinessReport.readiness.ok -ne $true) {
    throw "App runtime readiness check failed after rollback."
}
Assert-QuestionsReportSatisfiesGate -QuestionsReport $appReadinessReport.questions

Invoke-RemoteText "cd $(Quote-PosixShellArgument $layout.compose_directory) && $composeEnvPrefix docker compose -f docker-compose.release.yml up -d --no-build --force-recreate $($layout.scheduler_service_name)"

$schedulerAfter = Get-RemoteContainerSnapshot -ContainerName $layout.scheduler_service_name
if ($schedulerAfter.image_tag -ne $rollbackImageTag) {
    throw "Scheduler container did not switch to the rollback image."
}
if ($schedulerAfter.image_id -ne $rollbackImageId) {
    throw "Scheduler container image ID does not match the rollback image ID."
}
if ($appAfter.image_id -ne $schedulerAfter.image_id) {
    throw "App and scheduler image IDs do not match after rollback."
}

Invoke-RemoteText "docker restart $(Quote-PosixShellArgument $layout.nginx_service_name)"

$verificationOutput = & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'verify-production-release.ps1') -ReleaseManifest $rollbackVerificationManifestPath -LayoutFile $LayoutFile
if ($LASTEXITCODE -ne 0) {
    throw "Rollback verification failed with exit code $LASTEXITCODE."
}
$verificationReport = $verificationOutput | ConvertFrom-Json

$rollbackRecord = [ordered]@{
    rollback_manifest = $RollbackManifest
    rollback_image_tag = $rollbackImageTag
    rollback_release_git_sha = $rollbackGitSha
    rollback_image_id = $rollbackImageId
    previous_app = $appBefore
    previous_scheduler = $schedulerBefore
    current_app = $appAfter
    current_scheduler = $schedulerAfter
    app_readiness = $appReadinessReport
    verification = $verificationReport
}
Write-JsonFile -InputObject $rollbackRecord -Path $rollbackManifestPath

[ordered]@{
    dry_run = $false
    execute_requested = $true
    rollback_manifest_path = $RollbackManifest
    rollback_record_path = $rollbackManifestPath
    rollback_verification_manifest_path = $rollbackVerificationManifestPath
    rollback_image_tag = $rollbackImageTag
    rollback_release_git_sha = $rollbackGitSha
    rollback_image_id = $rollbackImageId
    previous_app = $appBefore
    previous_scheduler = $schedulerBefore
    current_app = $appAfter
    current_scheduler = $schedulerAfter
    app_readiness = $appReadinessReport
    verification = $verificationReport
} | ConvertTo-Json -Depth 12 | Write-Output
