"""Executable tests for candidate failure evidence persistence and cleanup ordering."""

import base64
import json
import pathlib
import shutil
import subprocess

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
DEPLOY = REPO_ROOT / "scripts" / "release" / "deploy-release-image.ps1"


def production_preservation_block():
    source = DEPLOY.read_text(encoding="utf-8")
    start = source.index("function Save-CandidateEvidenceAtomically")
    end = source.index("function Remove-RemoteStaleCandidateCanaries", start)
    return source[start:end]


def run_preservation(tmp_path, *, capture_fails=False, cleanup_fails=False, partial_capture=False):
    if shutil.which("powershell") is None:
        pytest.fail("Windows PowerShell 5.1 is required")
    evidence_path = tmp_path / "candidate-evidence.json"
    encoded_path = base64.b64encode(str(evidence_path).encode("utf-8")).decode("ascii")
    probe = tmp_path / "preservation-probe.ps1"
    if capture_fails:
        capture_body = "throw 'capture sentinel must not become primary'"
    else:
        capture_errors = "@([ordered]@{container='candidate-name';field='logs';code='container_logs_failed'})" if partial_capture else "@()"
        capture_body = (
            "return [ordered]@{ status='captured'; operation_id=$operationId; "
            "capture_errors=" + capture_errors + "; candidate=[ordered]@{ container_id='candidate-id'; "
            "image_id='sha256:image'; created='2026-07-18T22:17:00Z'; started_at='2026-07-18T22:17:01Z'; "
            "status='running'; health='healthy'; restart_count=0; exit_code=0; oom_killed=$false; "
            "startup_diagnostics=@([ordered]@{ schema='startup-diagnostic-v1'; boot_id='boot-id'; "
            "timestamp_utc='2026-07-18T22:17:02Z'; elapsed_seconds=1.5; phase='database'; status='start'; "
            "threads=@([ordered]@{ thread_id='1'; frames=@([ordered]@{file='app.py';function='create_app';line=42})}) }) } }"
        )
    cleanup_body = (
        "throw 'cleanup sentinel must remain secondary'"
        if cleanup_fails
        else "$before = Get-Content -Raw -LiteralPath $evidencePath | ConvertFrom-Json; if($before.cleanup.status -ne 'not_started'){throw 'evidence was not persisted before cleanup'}; return [ordered]@{status='completed';candidate_container='candidate-name'}"
    )
    probe.write_text(
        "[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)\n"
        "$ErrorActionPreference='Stop'\n"
        + production_preservation_block()
        + f"\n$evidencePath=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{encoded_path}'))\n"
        + "$operationId='deploy-test-operation'\n"
        + f"$captureAction={{ {capture_body} }}\n"
        + f"$cleanupAction={{ {cleanup_body} }}\n"
        + "$original=[ordered]@{stage='candidate_readiness_helper';code='helper_failed';message='Candidate readiness helper failed with exit code 1.'}\n"
        + "$helper=[ordered]@{exit_code=1;elapsed_seconds=2.5;stdout='';stderr='';framed_payload_present=$false}\n"
        + "$result=Invoke-CandidateFailurePreservation -OperationId $operationId -CandidateContainerName 'candidate-name' -OriginalFailure $original -EvidencePath $evidencePath -HelperAttempt $helper -CaptureAction $captureAction -CleanupAction $cleanupAction\n"
        + "$persisted=Get-Content -Raw -LiteralPath $evidencePath | ConvertFrom-Json\n"
        + "[ordered]@{result=$result;persisted=$persisted}|ConvertTo-Json -Depth 20 -Compress\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(probe)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_candidate_identity_lifecycle_boot_phases_and_stack_persist_before_cleanup(tmp_path):
    payload = run_preservation(tmp_path)
    evidence = payload["persisted"]
    assert evidence["operation_id"] == "deploy-test-operation"
    assert evidence["original_failure"]["code"] == "helper_failed"
    assert evidence["cleanup"]["status"] == "completed"
    candidate = evidence["capture"]["candidate"]
    assert candidate["container_id"] == "candidate-id"
    event = candidate["startup_diagnostics"][0]
    assert event["boot_id"] == "boot-id"
    assert event["phase"] == "database"
    assert event["threads"][0]["frames"][0] == {"file": "app.py", "function": "create_app", "line": 42}


def test_evidence_capture_failure_does_not_block_cleanup_or_replace_original(tmp_path):
    evidence = run_preservation(tmp_path, capture_fails=True)["persisted"]
    assert evidence["capture"]["status"] == "partial"
    assert evidence["capture"]["candidate"]["name"] == "candidate-name"
    assert evidence["capture_errors"] == [
        {"field": "remote_capture", "code": "candidate_evidence_capture_failed_closed"}
    ]
    assert evidence["cleanup"]["status"] == "completed"
    assert evidence["original_failure"]["code"] == "helper_failed"


def test_failed_log_subcapture_retains_candidate_identity_lifecycle_and_boot_phases(tmp_path):
    evidence = run_preservation(tmp_path, partial_capture=True)["persisted"]
    candidate = evidence["capture"]["candidate"]
    assert candidate["container_id"] == "candidate-id"
    assert candidate["image_id"] == "sha256:image"
    assert candidate["status"] == "running"
    assert candidate["startup_diagnostics"][0]["boot_id"] == "boot-id"
    assert evidence["capture_errors"] == [
        {"container": "candidate-name", "field": "logs", "code": "container_logs_failed"}
    ]


def test_cleanup_failure_is_secondary_and_original_readiness_failure_remains_primary(tmp_path):
    evidence = run_preservation(tmp_path, cleanup_fails=True)["persisted"]
    assert evidence["cleanup"] == {"status": "failed", "failure_code": "candidate_cleanup_failed_closed"}
    assert evidence["original_failure"] == {
        "stage": "candidate_readiness_helper",
        "code": "helper_failed",
        "message": "Candidate readiness helper failed with exit code 1.",
    }


def test_deployment_record_persists_operation_and_evidence_identity_before_candidate_start():
    source = DEPLOY.read_text(encoding="utf-8")
    record = source.index("$deploymentRecord['operation_id'] = $operationId")
    evidence = source.index("$deploymentRecord['candidate_evidence_filename']")
    save = source.index("Save-DeploymentRecord -Record $deploymentRecord", record)
    candidate = source.index("$candidateCreationAttempted = $true", save)
    assert record < evidence < save < candidate


def test_release_lock_result_is_persisted_without_replacing_failure():
    source = DEPLOY.read_text(encoding="utf-8")
    finally_block = source.split("finally {", 1)[1]
    assert "release_lock_cleanup = [ordered]@{ status = 'completed'" in finally_block
    assert "release_lock_cleanup = [ordered]@{ status = 'failed'" in finally_block
    assert "Save-CandidateEvidenceAtomically" in finally_block
