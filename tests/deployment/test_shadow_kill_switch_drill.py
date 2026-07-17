import json
import pathlib
import subprocess


ROOT = pathlib.Path(__file__).resolve().parents[2]
DRILL = ROOT / "scripts" / "release" / "run-shadow-kill-switch-drill.ps1"
MODULE = ROOT / "scripts" / "release" / "ShadowKillSwitchDrill.psm1"


def run_powershell(script, timeout=30):
    return subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def state_machine_harness(*, initial_enabled=True, fail_stage=None):
    module = str(MODULE).replace("'", "''")
    initial = "$true" if initial_enabled else "$false"
    fail_write = "throw 'injected'" if fail_stage == "write_stop" else "$script:writesChecked++"
    script = f"""
$ErrorActionPreference = 'Stop'
Import-Module '{module}' -Force
$script:enabled = {initial}
$script:writesChecked = 0
$script:resumeChecked = 0
$get = {{
    [pscustomobject]@{{ effective = [pscustomobject]@{{ enabled = $script:enabled; state = $(if($script:enabled){{'enabled'}}else{{'disabled'}}) }} }}
}}
$disable = {{
    $script:enabled = $false
    [pscustomobject]@{{ backup_id = 'initial-backup'; effective = [pscustomobject]@{{ enabled = $false; state = 'disabled' }} }}
}}
$verifyDisabled = {{ param($result) if($result.effective.enabled){{throw 'not disabled'}} }}
$verifyLegacy = {{ param($result) $null = $result }}
$verifyWriteStop = {{ {fail_write} }}
$verifyDashboard = {{ $true | Out-Null }}
$restore = {{
    param($disableResult,$initialState)
    $script:enabled = [bool]$initialState.effective.enabled
    [pscustomobject]@{{ rollback_backup_id = 'restoration-backup' }}
}}
$verifyResumed = {{ if(-not $script:enabled){{throw 'not resumed'}}; $script:resumeChecked++ }}
$result = Invoke-ShadowKillSwitchDrillStateMachine -GetState $get -Disable $disable -VerifyDisabled $verifyDisabled -VerifyLegacy $verifyLegacy -VerifyWriteStop $verifyWriteStop -VerifyDashboard $verifyDashboard -Restore $restore -VerifyResumed $verifyResumed
[ordered]@{{ report=$result; enabled=$script:enabled; writes=$script:writesChecked; resumes=$script:resumeChecked }} | ConvertTo-Json -Depth 12
"""
    result = run_powershell(script)
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


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


def test_successful_drill_restores_enabled_initial_state_and_reports_backups():
    payload = state_machine_harness(initial_enabled=True)
    report = payload["report"]
    assert report["success"] is True
    assert report["partial_state"] is False
    assert report["initial_state_captured"] is True
    assert report["initial_intended_enabled"] is True
    assert report["initial_backup_identity"] == "initial-backup"
    assert report["disable_verified"] is True
    assert report["legacy_routes_healthy"] is True
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
    payload = state_machine_harness(initial_enabled=False)
    report = payload["report"]
    assert report["success"] is True
    assert report["initial_intended_enabled"] is False
    assert report["final_matches_initial"] is True
    assert report["resume_verified"] is None
    assert payload["enabled"] is False
    assert payload["resumes"] == 0


def test_injected_failure_attempts_restoration_and_reports_partial_state():
    payload = state_machine_harness(initial_enabled=True, fail_stage="write_stop")
    report = payload["report"]
    assert report["success"] is False
    assert report["partial_state"] is True
    assert report["failure_stage"] == "write_stop"
    assert report["disable_verified"] is True
    assert report["legacy_routes_healthy"] is True
    assert report["write_stop_verified"] is False
    assert report["dashboard_readable"] is False
    assert report["restoration_attempted"] is True
    assert report["restoration_succeeded"] is True
    assert report["final_matches_initial"] is True
    assert payload["enabled"] is True


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
