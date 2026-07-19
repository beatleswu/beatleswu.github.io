#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$LayoutFile = 'deploy\release-layout.example.json',
    [switch]$Execute,
    [string]$OwnerGate,
    [ValidateRange(5, 120)]
    [int]$ObservationSeconds = 15
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'ReleaseTooling.psm1') -Force -DisableNameChecking
Import-Module (Join-Path $PSScriptRoot 'ShadowKillSwitchDrill.psm1') -Force -DisableNameChecking

if (-not $Execute) {
    throw 'The governed Shadow kill-switch drill requires -Execute.'
}
Assert-OwnerGate -Provided $OwnerGate -Expected 'GO_KILL_SWITCH_DRILL'

$layout = Get-ReleaseLayout -Path (Resolve-RepoPath $LayoutFile)
$setterPath = Join-Path $PSScriptRoot 'set-shadow-judging.ps1'

function Invoke-ShadowSetterJson {
    param(
        [Parameter(Mandatory = $true)][ValidateSet('status','disable','rollback')][string]$Operation,
        [string]$RollbackBackupId
    )
    $arguments = @('-NoProfile','-ExecutionPolicy','Bypass','-File',$setterPath,'-Operation',$Operation,'-LayoutFile',$LayoutFile)
    if ($Operation -eq 'disable') {
        $arguments += @('-Execute','-OwnerGate','GO_DISABLE_SHADOW')
    }
    elseif ($Operation -eq 'rollback') {
        $arguments += @('-Execute','-OwnerGate','GO_SHADOW_ROLLBACK')
        if ([string]::IsNullOrWhiteSpace($RollbackBackupId)) { throw 'Rollback requires an exact backup identity.' }
        $arguments += @('-RollbackBackupId', $RollbackBackupId)
    }
    $raw = & powershell @arguments 2>&1
    $exitCode = $LASTEXITCODE
    try {
        $payload = ($raw | Out-String) | ConvertFrom-Json
    }
    catch {
        throw "Shadow setter $Operation returned invalid sanitized JSON."
    }
    if ($exitCode -ne 0) {
        if ($payload.status -eq 'recovered_failure' -and $payload.internal_recovery_succeeded -eq $true) { return $payload }
        throw "Shadow setter $Operation failed closed."
    }
    return $payload
}

function Assert-DrillDisabled {
    param($DisableResult)
    if (-not $DisableResult.effective -or [bool]$DisableResult.effective.enabled) {
        throw 'Governed disable did not report an effectively disabled configuration.'
    }
    if (-not $DisableResult.runtime -or [bool]$DisableResult.runtime.app.enabled -or [bool]$DisableResult.runtime.scheduler.enabled) {
        throw 'App and scheduler were not both effectively disabled.'
    }
    if ($DisableResult.runtime.app.state -ne 'disabled' -or $DisableResult.runtime.scheduler.state -ne 'disabled') {
        throw 'App and scheduler did not converge to canonical disabled state.'
    }
}

function Assert-LegacyInfrastructureHealthy {
    param($DisableResult)
    if (-not $DisableResult.health -or $DisableResult.health.status -ne 'ok' -or [int]$DisableResult.health.healthz -ne 200) {
        throw 'Legacy health convergence was not preserved after Shadow disable.'
    }
    foreach ($route in @('homepage_url', 'login_url')) {
        try {
            $response = Invoke-WebRequest -Uri ([string]$layout.$route) -UseBasicParsing -MaximumRedirection 5 -TimeoutSec 15
        }
        catch {
            throw "Legacy route $route failed its governed health probe."
        }
        if ([int]$response.StatusCode -ne 200) {
            throw "Legacy route $route did not return HTTP 200."
        }
    }
}

function Invoke-LegacyJudgingCanary {
    param([Parameter(Mandatory = $true)][ValidateSet('baseline','disabled','restored')][string]$Checkpoint)

    $scriptTemplate = @'
set -eu
docker exec -i __APP__ python -X utf8 - <<'__LEGACY_JUDGING_CANARY__'
import json

import app

# Reuses tests/test_shadow_envelope_v4.py::SYNTHETIC_SGF. The production
# corpus, database, HTTP routes, player accounts, and Shadow judge are not used.
fixture = {
    "id": 123,
    "content": "(;SZ[19];B[aa])",
    "accepted_moves": [],
    "katago_best_move": "",
}
moves = [{"x": 0, "y": 0}]
actual = app._rt_server_verify(fixture, "legacy-canary-0", moves)
actual_label = "correct" if actual is True else ("incorrect" if actual is False else "indeterminate")
payload = {
    "ok": actual is True,
    "name": "rating_test_synthetic_single_move",
    "expected_result": "correct",
    "actual_result": actual_label,
}
print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
__LEGACY_JUDGING_CANARY__
'@
    $quotedAppService = Quote-PosixShellArgument ([string]$layout.app_service_name)
    $remoteScript = $scriptTemplate.Replace('__APP__', $quotedAppService)
    $remote = Invoke-BoundedSshCommand -SshAlias $layout.ssh_alias -ScriptText $remoteScript -TimeoutSeconds 30 -OperationLabel "Legacy judging canary ($Checkpoint)"
    if ($remote.timed_out -or $remote.exit_code -ne 0) {
        throw "Legacy judging canary $Checkpoint failed closed; remote output withheld."
    }
    try {
        $payload = (Get-RemoteStandardOutput -Result $remote) | ConvertFrom-Json
    }
    catch {
        throw "Legacy judging canary $Checkpoint returned invalid sanitized JSON."
    }
    if (-not $payload -or [string]::IsNullOrWhiteSpace([string]$payload.name)) {
        throw "Legacy judging canary $Checkpoint was unavailable or indeterminate."
    }
    return $payload
}

function Invoke-ShadowObservationProbe {
    param([Parameter(Mandatory = $true)][bool]$ExpectWrite)

    $scriptTemplate = @'
set -eu
docker exec -i __APP__ python -X utf8 - <<'__SHADOW_DRILL_PROBE__'
import json
import os
import time

import shadow_judging
from shadow_dashboard import recent_shadow_dashboard_data

path = os.environ.get("SHADOW_EVENTS_PATH", "/app/data/shadow_events.jsonl")
before = os.path.getsize(path) if os.path.exists(path) else 0
shadow_judging.observe_answer_route(
    entry_point="governed_kill_switch_drill",
    question_id=None,
    session_id="governed-kill-switch-drill",
    transform_idx=0,
    sgf_transformed="(;SZ[19];B[qd])",
    moves=[{"x": 16, "y": 3}],
    client_correct=True,
    final_correct=True,
    katago_best_move="Q16",
)
time.sleep(__SECONDS__)
after = os.path.getsize(path) if os.path.exists(path) else 0
dashboard = recent_shadow_dashboard_data(path=path, limit=1)
payload = {
    "status": "ok",
    "before_bytes": before,
    "after_bytes": after,
    "write_observed": after > before,
    "dashboard_readable": isinstance(dashboard, dict),
}
print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
__SHADOW_DRILL_PROBE__
'@
    $quotedAppService = Quote-PosixShellArgument ([string]$layout.app_service_name)
    $remoteScript = $scriptTemplate.Replace('__APP__', $quotedAppService).Replace('__SECONDS__', [string]$ObservationSeconds)
    $remote = Invoke-BoundedSshCommand -SshAlias $layout.ssh_alias -ScriptText $remoteScript -TimeoutSeconds ($ObservationSeconds + 30) -OperationLabel 'Governed Shadow kill-switch observation probe'
    if ($remote.timed_out -or $remote.exit_code -ne 0) {
        throw 'Governed Shadow observation probe failed closed; remote output withheld.'
    }
    try {
        $payload = (Get-RemoteStandardOutput -Result $remote) | ConvertFrom-Json
    }
    catch {
        throw 'Governed Shadow observation probe returned invalid sanitized JSON.'
    }
    if (-not $payload -or $payload.status -ne 'ok' -or $payload.dashboard_readable -ne $true) {
        throw 'Governed Shadow observation probe response failed closed.'
    }
    if ([bool]$payload.write_observed -ne $ExpectWrite) {
        throw 'Shadow write behavior did not match the governed drill expectation.'
    }
    return $payload
}

$disabledProbe = $null
$report = Invoke-ShadowKillSwitchDrillStateMachine `
    -GetState { Invoke-ShadowSetterJson -Operation status } `
    -Disable { Invoke-ShadowSetterJson -Operation disable } `
    -VerifyDisabled { param($result) Assert-DrillDisabled -DisableResult $result } `
    -VerifyInfrastructure { param($result) Assert-LegacyInfrastructureHealthy -DisableResult $result } `
    -VerifyLegacyCanary { param($checkpoint) Invoke-LegacyJudgingCanary -Checkpoint $checkpoint } `
    -VerifyWriteStop { $script:disabledProbe = Invoke-ShadowObservationProbe -ExpectWrite $false } `
    -VerifyDashboard { if (-not $script:disabledProbe -or $script:disabledProbe.dashboard_readable -ne $true) { throw 'Dashboard read verification missing.' } } `
    -Restore {
        param($disableResult, $initial)
        if (-not $disableResult.backup -or [string]::IsNullOrWhiteSpace([string]$disableResult.backup.id)) { throw 'Missing exact recovery target.' }
        Invoke-ShadowSetterJson -Operation rollback -RollbackBackupId ([string]$disableResult.backup.id)
    } `
    -VerifyResumed { $null = Invoke-ShadowObservationProbe -ExpectWrite $true }

$report | ConvertTo-Json -Depth 12 | Write-Output
if (-not $report.success) {
    exit 1
}
