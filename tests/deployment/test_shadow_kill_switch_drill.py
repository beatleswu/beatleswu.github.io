import json
import pathlib
import subprocess

import pytest


ROOT = pathlib.Path(__file__).resolve().parents[2]
DRILL = ROOT / "scripts" / "release" / "run-shadow-kill-switch-drill.ps1"
MODULE = ROOT / "scripts" / "release" / "ShadowKillSwitchDrill.psm1"
RELEASE_TOOLING = ROOT / "scripts" / "release" / "ReleaseTooling.psm1"
APP = ROOT / "app.py"


def run_powershell(script, timeout=30):
    return subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def state_machine_harness(*, initial_enabled=True, fail_stage=None, disable_shape="nested"):
    module = str(MODULE).replace("'", "''")
    initial = "$true" if initial_enabled else "$false"
    failure = (fail_stage or "").replace("'", "''")
    disable_results = {
        "nested": "[pscustomobject]@{ backup = [pscustomobject]@{ id = 'initial-backup' }; effective = [pscustomobject]@{ enabled = $false; state = 'disabled' } }",
        "internal_recovery": "[pscustomobject]@{ backup = [pscustomobject]@{ id = 'initial-backup' }; effective = [pscustomobject]@{ enabled = $true; state = 'enabled' }; internal_recovery_attempted = $true; internal_recovery_succeeded = $true; failed_generation_evidence = [pscustomobject]@{ status = 'captured'; operation_id = 'operation-1' } }",
        "missing_backup": "[pscustomobject]@{ effective = [pscustomobject]@{ enabled = $false; state = 'disabled' } }",
        "missing_id": "[pscustomobject]@{ backup = [pscustomobject]@{}; effective = [pscustomobject]@{ enabled = $false; state = 'disabled' } }",
        "null_id": "[pscustomobject]@{ backup = [pscustomobject]@{ id = $null }; effective = [pscustomobject]@{ enabled = $false; state = 'disabled' } }",
        "empty_id": "[pscustomobject]@{ backup = [pscustomobject]@{ id = '' }; effective = [pscustomobject]@{ enabled = $false; state = 'disabled' } }",
        "whitespace_id": "[pscustomobject]@{ backup = [pscustomobject]@{ id = '   ' }; effective = [pscustomobject]@{ enabled = $false; state = 'disabled' } }",
        "malformed": "'not-an-object'",
    }
    disable_result = disable_results[disable_shape]
    script = f"""
$ErrorActionPreference = 'Stop'
Import-Module '{module}' -Force
$script:initialEnabled = {initial}
$script:enabled = $script:initialEnabled
$script:failure = '{failure}'
$script:getCalls = 0
$script:writesChecked = 0
$script:resumeChecked = 0
function Test-Failure {{ param([string]$stage) return @(($script:failure -split '\\+')) -contains $stage }}
$get = {{
    $script:getCalls++
    if((Test-Failure 'initial_state') -and $script:getCalls -eq 1){{throw 'injected'}}
    [pscustomobject]@{{ effective = [pscustomobject]@{{ enabled = $script:enabled; state = $(if($script:enabled){{'enabled'}}else{{'disabled'}}) }} }}
}}
$disable = {{
    $script:enabled = $false
    if(Test-Failure 'disable'){{throw 'injected'}}
    if('{disable_shape}' -eq 'internal_recovery'){{ $script:enabled = $true }}
    return {disable_result}
}}
$verifyDisabled = {{ param($result) if(Test-Failure 'disable_verification'){{throw 'injected'}}; if($result.effective.enabled){{throw 'not disabled'}} }}
$verifyInfrastructure = {{ param($result) if(Test-Failure 'legacy_infrastructure'){{throw 'injected'}}; $null = $result }}
$verifyLegacyCanary = {{
    param($checkpoint)
    $stage = "legacy_$checkpoint"
    $ok = -not (Test-Failure $stage)
    [pscustomobject]@{{
        ok = $ok
        name = 'rating_test_synthetic_single_move'
        expected_result = 'correct'
        actual_result = $(if($ok){{'correct'}}else{{'incorrect'}})
    }}
}}
$verifyWriteStop = {{ if(Test-Failure 'write_stop'){{throw 'injected'}}; $script:writesChecked++ }}
$verifyDashboard = {{ if(Test-Failure 'dashboard'){{throw 'injected'}} }}
$restore = {{
    param($disableResult,$initialState)
    if(Test-Failure 'restoration'){{throw 'injected'}}
    if(-not (Test-Failure 'final_state_mismatch')){{
        $script:enabled = [bool]$initialState.effective.enabled
    }}
    [pscustomobject]@{{ rollback_backup_id = 'restoration-backup' }}
}}
$verifyResumed = {{
    if(Test-Failure 'event_resumption'){{throw 'injected'}}
    if(-not $script:enabled){{throw 'not resumed'}}
    $script:resumeChecked++
}}
$result = Invoke-ShadowKillSwitchDrillStateMachine -GetState $get -Disable $disable -VerifyDisabled $verifyDisabled -VerifyInfrastructure $verifyInfrastructure -VerifyLegacyCanary $verifyLegacyCanary -VerifyWriteStop $verifyWriteStop -VerifyDashboard $verifyDashboard -Restore $restore -VerifyResumed $verifyResumed
[ordered]@{{ report=$result; enabled=$script:enabled; writes=$script:writesChecked; resumes=$script:resumeChecked }} | ConvertTo-Json -Depth 12
if(-not $result.success){{exit 1}}
"""
    result = run_powershell(script)
    assert result.stdout.strip(), result.stderr
    return result.returncode, json.loads(result.stdout)


def test_drill_public_gate_is_exact_and_go_deploy_is_rejected():
    content = DRILL.read_text(encoding="utf-8")
    assert "Assert-OwnerGate -Provided $OwnerGate -Expected 'GO_KILL_SWITCH_DRILL'" in content
    assert "The governed Shadow kill-switch drill requires -Execute." in content
    assert "GO_DEPLOY" not in content
    assert "GO_DISABLE_SHADOW" in content
    assert "GO_SHADOW_ROLLBACK" in content

    drill = str(DRILL).replace("'", "''")
    missing_execute = run_powershell(f"& '{drill}' -OwnerGate GO_KILL_SWITCH_DRILL")
    assert missing_execute.returncode != 0
    assert "requires -Execute" in (missing_execute.stdout + missing_execute.stderr)

    for gate in (
        "GO_DEPLOY",
        "GO_ENABLE_SHADOW",
        "GO_DISABLE_SHADOW",
        "GO_SHADOW_ROLLBACK",
        "GO_MIGRATE_IDENTITY",
        "GO_BACKFILL_IDENTITY",
        "ARBITRARY",
        "''",
    ):
        wrong_gate = run_powershell(f"& '{drill}' -Execute -OwnerGate {gate}")
        assert wrong_gate.returncode != 0
        output = wrong_gate.stdout + wrong_gate.stderr
        if gate == "''":
            assert "EmptyStringNotAllowed" in output
        else:
            assert "Expected -OwnerGate GO_KILL_SWITCH_DRILL" in output


def test_legacy_canary_invokes_real_legacy_verifier_with_only_tracked_synthetic_data():
    content = DRILL.read_text(encoding="utf-8")
    canary = content.split("function Invoke-LegacyJudgingCanary", 1)[1].split(
        "function Invoke-ShadowObservationProbe", 1
    )[0]
    assert "tests/test_shadow_envelope_v4.py::SYNTHETIC_SGF" in canary
    assert "app._rt_server_verify" in canary
    assert '"legacy-canary-0"' in canary
    assert '"expected_result": "correct"' in canary
    assert "shadow_judging" not in canary
    assert "Invoke-WebRequest" not in canary
    assert "questions.json" not in canary
    assert "get_db" not in canary

    app_source = APP.read_text(encoding="utf-8")
    assert "server_correct = _rt_server_verify(pool_q, sid, moves)" in app_source
    assert "correct = bool(server_correct)" in app_source
    assert "final_correct=bool(correct)" in app_source


def test_real_legacy_canary_ignores_startup_diagnostics_on_stderr():
    content = DRILL.read_text(encoding="utf-8")
    canary = "function Invoke-LegacyJudgingCanary" + content.split(
        "function Invoke-LegacyJudgingCanary", 1
    )[1].split("function Invoke-ShadowObservationProbe", 1)[0]
    release_tooling = str(RELEASE_TOOLING).replace("'", "''")
    script = f"""
$ErrorActionPreference='Stop'
Import-Module '{release_tooling}' -Force -DisableNameChecking
$layout=[pscustomobject]@{{ssh_alias='test-host';app_service_name='app-current'}}
function Invoke-BoundedSshCommand {{
    [ordered]@{{
        stdout='{{"actual_result":"correct","expected_result":"correct","name":"rating_test_synthetic_single_move","ok":true}}'
        stderr='[startup-diagnostic] {{"phase":"python_start","status":"point"}}'
        output='{{"actual_result":"correct","expected_result":"correct","name":"rating_test_synthetic_single_move","ok":true}}[startup-diagnostic]'
        exit_code=0
        elapsed_seconds=1
        timed_out=$false
    }}
}}
{canary}
Invoke-LegacyJudgingCanary -Checkpoint baseline | ConvertTo-Json -Compress
"""
    result = run_powershell(script)
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout.strip())
    assert payload["ok"] is True
    assert payload["actual_result"] == "correct"
    assert "startup-diagnostic" not in result.stdout


def test_successful_drill_restores_enabled_initial_state_and_requires_all_canaries():
    returncode, payload = state_machine_harness(initial_enabled=True)
    report = payload["report"]
    assert returncode == 0
    assert report["success"] is True
    assert report["partial_state"] is False
    assert report["initial_backup_identity"] == "initial-backup"
    assert report["legacy_infrastructure_healthy"] is True
    assert report["legacy_judging_baseline_ok"] is True
    assert report["legacy_judging_disabled_ok"] is True
    assert report["legacy_judging_restored_ok"] is True
    assert report["legacy_canary_name"] == "rating_test_synthetic_single_move"
    assert report["legacy_expected_result"] == "correct"
    assert report["legacy_actual_result"] == "correct"
    assert report["write_stop_verified"] is True
    assert report["dashboard_readable"] is True
    assert report["restoration_attempted"] is True
    assert report["restoration_succeeded"] is True
    assert report["restoration_backup_identity"] == "restoration-backup"
    assert report["final_matches_initial"] is True
    assert report["resume_verified"] is True
    assert payload["enabled"] is True
    assert payload["resumes"] == 1


def test_successful_drill_restores_disabled_initial_state_without_resume_probe():
    returncode, payload = state_machine_harness(initial_enabled=False)
    report = payload["report"]
    assert returncode == 0
    assert report["success"] is True
    assert report["initial_intended_enabled"] is False
    assert report["final_matches_initial"] is True
    assert report["legacy_judging_restored_ok"] is True
    assert report["resume_verified"] is None
    assert payload["enabled"] is False
    assert payload["resumes"] == 0


@pytest.mark.parametrize(
    "disable_shape",
    ("missing_backup", "missing_id", "null_id", "empty_id", "whitespace_id", "malformed"),
)
def test_disable_backup_identity_contract_fails_closed(disable_shape):
    returncode, payload = state_machine_harness(disable_shape=disable_shape)
    report = payload["report"]
    assert returncode != 0
    assert report["success"] is False
    assert report["failure_stage"] == "disable"
    assert report["initial_backup_identity"] is None
    assert report["restoration_attempted"] is True
    assert report["restoration_succeeded"] is True
    assert report["final_matches_initial"] is True


def test_internal_recovery_skips_outer_restore_and_preserves_disable_failure():
    returncode, payload = state_machine_harness(initial_enabled=True, disable_shape="internal_recovery")
    report = payload["report"]
    assert returncode != 0
    assert report["failure_stage"] == "disable"
    assert report["setter_internal_recovery_succeeded"] is True
    assert report["evidence_capture_status"] == "captured"
    assert report["failed_generation_evidence"]["operation_id"] == "operation-1"
    assert report["outer_restoration_attempted"] is False
    assert report["final_matches_initial"] is True


def test_original_drill_failure_message_remains_primary_when_restore_also_fails():
    returncode, payload = state_machine_harness(
        initial_enabled=True,
        fail_stage="write_stop+restoration",
    )
    report = payload["report"]
    assert returncode != 0
    assert report["failure_stage"] == "write_stop"
    assert report["failure_code"] == "shadow_kill_switch_drill_failed"
    assert report["failure_message"] == "injected"
    assert report["restoration_attempted"] is True
    assert report["restoration_succeeded"] is False


def test_restore_requires_real_flat_rollback_backup_identity():
    returncode, payload = state_machine_harness(initial_enabled=True, fail_stage="write_stop")
    report = payload["report"]
    assert returncode != 0
    assert report["restoration_backup_identity"] == "restoration-backup"


def test_restore_missing_reverse_backup_identity_fails_closed():
    module = str(MODULE).replace("'", "''")
    script = f"""
$ErrorActionPreference = 'Stop'
Import-Module '{module}' -Force
$enabled = $true
$get = {{ [pscustomobject]@{{ effective = [pscustomobject]@{{ enabled = $enabled; state = $(if($enabled){{'enabled'}}else{{'disabled'}}) }} }} }}
$disable = {{ $enabled = $false; [pscustomobject]@{{ backup = [pscustomobject]@{{ id = 'initial-backup' }} }} }}
$canary = {{ param($checkpoint) [pscustomobject]@{{ ok=$true; name='synthetic'; expected_result='correct'; actual_result='correct' }} }}
$restore = {{ param($disableResult,$initialState) $enabled = $true; [pscustomobject]@{{ operation='rollback' }} }}
$result = Invoke-ShadowKillSwitchDrillStateMachine -GetState $get -Disable $disable -VerifyDisabled {{}} -VerifyInfrastructure {{}} -VerifyLegacyCanary $canary -VerifyWriteStop {{ throw 'stop' }} -VerifyDashboard {{}} -Restore $restore -VerifyResumed {{}}
[ordered]@{{ report=$result }} | ConvertTo-Json -Depth 12
if($result.restoration_succeeded){{exit 1}}
"""
    result = run_powershell(script)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)["report"]
    assert report["restoration_attempted"] is True
    assert report["restoration_succeeded"] is False
    assert report["final_matches_initial"] is True


@pytest.mark.parametrize(
    ("failure_stage", "restoration_attempted", "restoration_succeeded"),
    (
        ("initial_state", False, False),
        ("legacy_baseline", False, False),
        ("disable", True, True),
        ("disable_verification", True, True),
        ("legacy_infrastructure", True, True),
        ("legacy_disabled", True, True),
        ("write_stop", True, True),
        ("dashboard", True, True),
        ("restoration", True, False),
        ("final_state_mismatch", True, False),
        ("legacy_restored", True, True),
        ("event_resumption", True, True),
    ),
)
def test_injected_failures_exit_unsuccessfully_and_report_first_partial_state(
    failure_stage, restoration_attempted, restoration_succeeded
):
    returncode, payload = state_machine_harness(
        initial_enabled=True, fail_stage=failure_stage
    )
    report = payload["report"]
    assert returncode != 0
    assert report["success"] is False
    assert report["partial_state"] is True
    assert report["failure_stage"] == failure_stage
    assert report["restoration_attempted"] is restoration_attempted
    assert report["restoration_succeeded"] is restoration_succeeded
    if failure_stage != "initial_state":
        assert report["final_effective_state"] in {"enabled", "disabled"}
    if restoration_succeeded:
        assert report["final_matches_initial"] is True
        assert payload["enabled"] is True
    if failure_stage == "final_state_mismatch":
        assert report["final_effective_state"] == "disabled"
        assert report["final_matches_initial"] is False
    if failure_stage == "legacy_baseline":
        assert report["legacy_baseline_actual_result"] == "incorrect"
    if failure_stage == "legacy_disabled":
        assert report["legacy_disabled_actual_result"] == "incorrect"
    if failure_stage == "legacy_restored":
        assert report["legacy_restored_actual_result"] == "incorrect"


def test_first_failure_stage_is_preserved_when_restoration_also_fails():
    returncode, payload = state_machine_harness(
        initial_enabled=True, fail_stage="write_stop+restoration"
    )
    report = payload["report"]
    assert returncode != 0
    assert report["success"] is False
    assert report["failure_stage"] == "write_stop"
    assert report["restoration_attempted"] is True
    assert report["restoration_succeeded"] is False
    assert report["final_effective_state"] == "disabled"


def test_drill_powershell_files_parse_without_errors():
    for path in (DRILL, MODULE):
        escaped = str(path).replace("'", "''")
        command = (
            "$errors=$null; "
            f"[System.Management.Automation.Language.Parser]::ParseFile('{escaped}',"
            "[ref]$null,[ref]$errors)|Out-Null; "
            "if($errors.Count){$errors|ForEach-Object{$_.Message};exit 1}"
        )
        result = run_powershell(command)
        assert result.returncode == 0, result.stdout + result.stderr
