import hashlib
import importlib
import json
import pathlib
import subprocess
import sys


ROOT = pathlib.Path(__file__).resolve().parents[2]
HELPER = ROOT / "scripts" / "release" / "shadow_judging_config.py"
SETTER = ROOT / "scripts" / "release" / "set-shadow-judging.ps1"
RUNBOOK = ROOT / "docs" / "deployment" / "shadow_judging_kill_switch.md"
PROD_COMPOSE = ROOT / "docker-compose.prod.yml"
RELEASE_COMPOSE = ROOT / "docker-compose.release.yml"
UNSET = object()


def load_production_owner_gates():
    spec = importlib.util.spec_from_file_location(
        "validated_production_shadow_judging_config", HELPER
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return dict(module.OWNER_GATES)


MUTATION_GATES = load_production_owner_gates()


def invoke_helper(
    tmp_path,
    operation,
    content=UNSET,
    *,
    desired=None,
    execute=False,
    owner_gate=None,
    rollback_backup_id=None,
):
    env_path = tmp_path / ".env"
    if content is not UNSET:
        data = content.encode("utf-8") if isinstance(content, str) else content
        env_path.write_bytes(data)

    args = [
        sys.executable,
        str(HELPER),
        "--operation",
        operation,
        "--env-path",
        str(env_path),
        "--backup-dir",
        str(tmp_path / "backups"),
        "--audit-path",
        str(tmp_path / "audit" / "audit.jsonl"),
        "--lock-path",
        str(tmp_path / "shadow.lock"),
    ]
    if desired is not None:
        args.extend(("--desired", desired))
    if execute:
        args.append("--execute")
    if owner_gate is not None:
        args.extend(("--owner-gate", owner_gate))
    if rollback_backup_id is not None:
        args.extend(("--rollback-backup-id", rollback_backup_id))

    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.stdout.strip(), result.stderr
    payload = json.loads(result.stdout.strip())
    return result, payload, env_path


def mutate(tmp_path, operation, content=UNSET, *, rollback_backup_id=None):
    return invoke_helper(
        tmp_path,
        operation,
        content,
        execute=True,
        owner_gate=MUTATION_GATES[operation],
        rollback_backup_id=rollback_backup_id,
    )


def test_status_defaults_unset_to_disabled_without_exposing_other_values(tmp_path):
    secret = "synthetic-do-not-print"
    result, payload, env_path = invoke_helper(
        tmp_path,
        "status",
        f"SYNTHETIC_SECRET={secret}\n# preserve this comment\n",
    )

    assert result.returncode == 0
    assert payload["key"] == "SHADOW_JUDGING_ENABLED"
    assert payload["value_state"] == "UNSET_DEFAULT_FALSE"
    assert payload["effective"]["state"] == "unset_default_disabled"
    assert payload["effective"]["enabled"] is False
    assert payload["mutation_performed"] is False
    assert "SYNTHETIC_SECRET" not in result.stdout
    assert secret not in result.stdout
    assert env_path.read_text(encoding="utf-8") == f"SYNTHETIC_SECRET={secret}\n# preserve this comment\n"
    assert not (tmp_path / "backups").exists()
    assert not (tmp_path / "audit" / "audit.jsonl").exists()


def test_status_matches_runtime_aliases_and_malformed_values_fail_closed(tmp_path):
    cases = (
        ("true", "enabled", True),
        ("YES", "enabled", True),
        ("false", "disabled", False),
        ("0", "disabled", False),
        ("unexpected", "invalid_fail_closed", False),
        ('"true"', "invalid_fail_closed", False),
    )
    for index, (value, expected_state, expected_enabled) in enumerate(cases):
        case_dir = tmp_path / str(index)
        case_dir.mkdir()
        result, payload, _ = invoke_helper(
            case_dir,
            "status",
            f"SHADOW_JUDGING_ENABLED={value}\n",
        )
        assert result.returncode == 0
        assert payload["effective"]["state"] == expected_state
        assert payload["effective"]["enabled"] is expected_enabled
        if expected_state == "invalid_fail_closed":
            assert value not in result.stdout


def test_dry_run_is_non_mutating_and_reports_enable_and_disable_plans(tmp_path):
    original = b"OPAQUE=synthetic\r\nSHADOW_JUDGING_ENABLED=false\r\n"
    result, payload, env_path = invoke_helper(
        tmp_path,
        "dry-run",
        original,
        desired="enable",
    )
    assert result.returncode == 0
    assert payload["desired"] == "enable"
    assert payload["desired_value"] == "true"
    assert payload["change"] == "update"
    assert payload["execution_allowed"] is True
    assert payload["service_recreate_required"] is True
    assert env_path.read_bytes() == original

    result, payload, env_path = invoke_helper(
        tmp_path,
        "dry-run",
        desired="disable",
    )
    assert result.returncode == 0
    assert payload["change"] == "unchanged"
    assert payload["service_recreate_required"] is False
    assert env_path.read_bytes() == original
    assert not (tmp_path / "backups").exists()


def test_all_mutations_require_execute_and_exact_operation_owner_gate(tmp_path):
    assert MUTATION_GATES == {
        "enable": "GO_ENABLE_SHADOW",
        "disable": "GO_DISABLE_SHADOW",
        "rollback": "GO_SHADOW_ROLLBACK",
    }
    original = "SHADOW_JUDGING_ENABLED=false\nOPAQUE=synthetic\n"
    rejected = {
        None,
        "",
        "ARBITRARY",
        "GO_DEPLOY",
        "GO_MIGRATE_IDENTITY",
        "GO_BACKFILL_IDENTITY",
        *MUTATION_GATES.values(),
    }
    for index, operation in enumerate(MUTATION_GATES):
        operation_dir = tmp_path / str(index)
        operation_dir.mkdir()
        result, payload, env_path = invoke_helper(operation_dir, operation, original)
        assert result.returncode == 1
        assert payload == {"reason": "mutation_requires_execute", "status": "fail_closed"}
        assert env_path.read_text(encoding="utf-8") == original

        for gate in rejected - {MUTATION_GATES[operation]}:
            result, payload, env_path = invoke_helper(
                operation_dir,
                operation,
                execute=True,
                owner_gate=gate,
            )
            assert result.returncode == 1
            assert payload == {"reason": "owner_gate_mismatch", "status": "fail_closed"}
            assert env_path.read_text(encoding="utf-8") == original
            assert not (operation_dir / "backups").exists()


def test_enable_changes_only_allowed_key_and_creates_governed_backup(tmp_path):
    original = b"SYNTHETIC_SECRET=opaque\n\n# exact bytes stay\nSHADOW_JUDGING_ENABLED=off\nOTHER=x=y\n"
    original_hash = hashlib.sha256(original).hexdigest()
    result, payload, env_path = mutate(tmp_path, "enable", original)

    assert result.returncode == 0
    expected = original.replace(b"SHADOW_JUDGING_ENABLED=off", b"SHADOW_JUDGING_ENABLED=true")
    assert env_path.read_bytes() == expected
    assert payload["effective"]["state"] == "enabled"
    assert payload["effective"]["enabled"] is True
    assert payload["mutation_performed"] is True
    assert payload["service_recreate_required"] is True
    assert "SYNTHETIC_SECRET" not in result.stdout
    assert "opaque" not in result.stdout

    backups = list((tmp_path / "backups").glob("*.env"))
    metadata_files = list((tmp_path / "backups").glob("*.json"))
    assert len(backups) == 1
    assert len(metadata_files) == 1
    assert backups[0].read_bytes() == original
    metadata = json.loads(metadata_files[0].read_text(encoding="utf-8"))
    assert metadata["marker"] == "shadow-judging-governed-backup-v1"
    assert metadata["backup_id"] == backups[0].stem == metadata_files[0].stem
    assert metadata["backup_sha256"] == original_hash
    assert metadata["original"]["sha256"] == original_hash
    assert pathlib.Path(metadata["env_path"]) == env_path.resolve()
    assert pathlib.Path(metadata["backup_path"]) == backups[0].resolve()
    assert metadata_files[0].is_file()
    assert not metadata_files[0].is_symlink()

    audit = (tmp_path / "audit" / "audit.jsonl").read_text(encoding="utf-8")
    assert "SYNTHETIC_SECRET" not in audit
    assert "opaque" not in audit
    audit_record = json.loads(audit)
    assert audit_record["operation"] == "enable"
    assert audit_record["effective_state"] == "enabled"


def test_enable_handles_missing_key_and_final_line_without_newline(tmp_path):
    original = b"OPAQUE=synthetic"
    result, payload, env_path = mutate(tmp_path, "enable", original)
    assert result.returncode == 0
    assert payload["changed"] is True
    assert env_path.read_bytes() == b"OPAQUE=synthetic\nSHADOW_JUDGING_ENABLED=true\n"


def test_malformed_value_blocks_enable_but_disable_remediates_fail_closed(tmp_path):
    original = "SHADOW_JUDGING_ENABLED=maybe\nOPAQUE=synthetic\n"
    result, payload, env_path = mutate(tmp_path, "enable", original)
    assert result.returncode == 1
    assert payload == {
        "reason": "current_shadow_judging_configuration_invalid",
        "status": "fail_closed",
    }
    assert env_path.read_text(encoding="utf-8") == original
    assert not (tmp_path / "backups").exists()

    result, payload, env_path = mutate(tmp_path, "disable")
    assert result.returncode == 0
    assert payload["effective"]["state"] == "disabled"
    assert env_path.read_text(encoding="utf-8") == "SHADOW_JUDGING_ENABLED=false\nOPAQUE=synthetic\n"


def test_duplicate_unknown_and_noncanonical_shadow_assignments_fail_closed(tmp_path):
    cases = (
        (
            "SHADOW_JUDGING_ENABLED=true\nSHADOW_JUDGING_ENABLED=false\n",
            "duplicate_shadow_judging_assignment",
        ),
        ("SHADOW_JUDGING_SAMPLE=1\n", "unknown_shadow_judging_key"),
        ("export SHADOW_JUDGING_ENABLED=true\n", "malformed_shadow_judging_assignment"),
    )
    for index, (content, reason) in enumerate(cases):
        case_dir = tmp_path / str(index)
        case_dir.mkdir()
        result, payload, env_path = invoke_helper(case_dir, "status", content)
        assert result.returncode == 1
        assert payload == {"reason": reason, "status": "fail_closed"}
        assert env_path.read_text(encoding="utf-8") == content


def test_rollback_restores_exact_bytes_and_keeps_a_reverse_backup(tmp_path):
    original = b"OPAQUE=synthetic\r\nSHADOW_JUDGING_ENABLED=false\r\n"
    result, _, env_path = mutate(tmp_path, "enable", original)
    assert result.returncode == 0
    enabled = env_path.read_bytes()
    assert enabled != original

    target = next((tmp_path / "backups").glob("*.env")).stem
    result, payload, env_path = mutate(tmp_path, "rollback", rollback_backup_id=target)
    assert result.returncode == 0
    assert env_path.read_bytes() == original
    assert payload["effective"]["state"] == "disabled"
    assert payload["backup_id"]
    assert payload["rollback_backup_id"]
    assert payload["backup_id"] != payload["rollback_backup_id"]
    assert len(list((tmp_path / "backups").glob("*.env"))) == 2

    result, payload, env_path = mutate(tmp_path, "rollback", rollback_backup_id=target)
    assert result.returncode == 0
    assert env_path.read_bytes() == original
    assert payload["effective"]["state"] == "disabled"


def test_tampered_backup_is_not_accepted_for_rollback(tmp_path):
    original = "SHADOW_JUDGING_ENABLED=false\nOPAQUE=synthetic\n"
    result, _, env_path = mutate(tmp_path, "enable", original)
    assert result.returncode == 0
    enabled = env_path.read_bytes()
    backup = next((tmp_path / "backups").glob("*.env"))
    backup.write_text("SHADOW_JUDGING_ENABLED=true\nTAMPERED=1\n", encoding="utf-8")

    result, payload, env_path = mutate(tmp_path, "rollback")
    assert result.returncode == 1
    assert payload == {"reason": "no_valid_governed_backup", "status": "fail_closed"}
    assert env_path.read_bytes() == enabled


def test_explicit_unknown_rollback_identity_fails_closed(tmp_path):
    original = "SHADOW_JUDGING_ENABLED=false\n"
    result, _, env_path = mutate(tmp_path, "enable", original)
    assert result.returncode == 0
    before = env_path.read_bytes()
    result, payload, _ = mutate(tmp_path, "rollback", rollback_backup_id="missing-backup")
    assert result.returncode == 1
    assert payload == {"reason": "no_valid_governed_backup", "status": "fail_closed"}
    assert env_path.read_bytes() == before


def test_lock_file_is_removed_after_governed_operation(tmp_path):
    result, _, _ = mutate(tmp_path, "enable", "SHADOW_JUDGING_ENABLED=false\n")
    assert result.returncode == 0
    assert not (tmp_path / "shadow.lock").exists()


def test_lock_is_non_reentrant_for_read_and_write_operations(tmp_path):
    module_directory = str(HELPER.parent)
    sys.path.insert(0, module_directory)
    try:
        helper_module = importlib.import_module("shadow_judging_config")
        lock_path = tmp_path / "shadow.lock"
        lock_path.write_text("0", encoding="utf-8")
        (tmp_path / ".env").write_text("SHADOW_JUDGING_ENABLED=false\n", encoding="utf-8")
        with lock_path.open("r+") as lock_handle:
            helper_module.acquire_lock(lock_handle)
            result, payload, _ = invoke_helper(tmp_path, "status")
        assert result.returncode == 1
        assert payload == {"reason": "lock_unavailable", "status": "fail_closed"}
    finally:
        sys.path.remove(module_directory)


def test_compose_contract_defaults_only_the_explicit_flag_to_false():
    prod = PROD_COMPOSE.read_text(encoding="utf-8")
    release = RELEASE_COMPOSE.read_text(encoding="utf-8")

    assert prod.count("SHADOW_JUDGING_ENABLED=${SHADOW_JUDGING_ENABLED:-false}") == 2
    assert release.count('SHADOW_JUDGING_ENABLED: "${SHADOW_JUDGING_ENABLED:-false}"') == 2
    assert "SHADOW_JUDGING_ENABLED=1" not in prod
    assert 'SHADOW_JUDGING_ENABLED: "1"' not in release


def test_real_wait_convergence_seam_executes_identity_bound_state_machine():
    setter = SETTER.read_text(encoding="utf-8")
    prefix = setter.split("$result = $null", 1)[0].replace("'", "''")
    script = f"""
$ErrorActionPreference='Stop'
$source=Get-Content '{str(SETTER).replace("'", "''")}' -Raw; Invoke-Expression $source.Substring($source.IndexOf('function Get-ShadowRuntimeFlag'),$source.IndexOf('$result = $null')-$source.IndexOf('function Get-ShadowRuntimeFlag'))
$script:i=0
$script:health=@(
  [pscustomobject]@{{app_container_id='app-old';scheduler_container_id='sch-old';app_image_id='img';scheduler_image_id='img';app='running|healthy';scheduler='running';healthz=200}},
  [pscustomobject]@{{app_container_id='app-new';scheduler_container_id='sch-old';app_image_id='img';scheduler_image_id='img';app='running|healthy';scheduler='running';healthz=200}},
  [pscustomobject]@{{app_container_id='app-new';scheduler_container_id='sch-new';app_image_id='img';scheduler_image_id='img';app='running|healthy';scheduler='running';healthz=200}},
  [pscustomobject]@{{app_container_id='app-new';scheduler_container_id='sch-new';app_image_id='img';scheduler_image_id='img';app='running|healthy';scheduler='running';healthz=200}}
)
function Get-TestHealth {{ $x=$script:health[[Math]::Min($script:i,($script:health.Count-1))]; $script:i++; return $x }}
$runtime={{ param($a,$s) if($a -ne 'app-new' -or $s -ne 'sch-new'){{throw 'wrong identity'}}; [pscustomobject]@{{app=[pscustomobject]@{{enabled=$true;state='enabled'}};scheduler=[pscustomobject]@{{enabled=$true;state='enabled'}}}} }}
$clockValue=[datetime]'2026-01-01T00:00:00Z'
$clock={{ $script:clockValue }}
$sleep={{ param($seconds) $script:clockValue=$script:clockValue.AddSeconds(1) }}
$before=[pscustomobject]@{{app_container_id='app-old';scheduler_container_id='sch-old';app_image_id='img';scheduler_image_id='img'}}
$helper=[pscustomobject]@{{effective=[pscustomobject]@{{enabled=$true;state='enabled'}}}}
    $r=Wait-ShadowPostChangeConvergence -HelperResult $helper -ExpectedOperation enable -BeforeHealth $before -DeadlineSeconds 10 -PollIntervalSeconds 1 -HealthProbe ${{function:Get-TestHealth}} -RuntimeProbe $runtime -Clock $clock -SleepAction $sleep
    if($r.health.app_container_id -ne 'app-new' -or $r.health.scheduler_container_id -ne 'sch-new'){{throw ('identity convergence seam failed: ' + ($r | ConvertTo-Json -Compress))}}
Write-Output 'OK'
"""
    result = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script], cwd=ROOT, capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip().endswith("OK")


def test_failed_generation_evidence_capture_is_real_bounded_and_fail_closed():
    script = f"""
$ErrorActionPreference='Stop'
$source=Get-Content '{str(SETTER).replace("'", "''")}' -Raw
$start=$source.IndexOf('function Get-ShadowFailedGenerationEvidence')
$end=$source.IndexOf('function New-ShadowRecoveredFailureResult')
Invoke-Expression $source.Substring($start,$end-$start)
$okProbe={{ param($id) [pscustomobject]@{{status='captured';operation_id=$id;containers=[pscustomobject]@{{app=[pscustomobject]@{{metadata=[pscustomobject]@{{id='app-id'}}}};scheduler=[pscustomobject]@{{metadata=[pscustomobject]@{{id='scheduler-id'}}}}}}}} }}
$badProbe={{ param($id) throw 'sentinel-secret-capture-error' }}
$ok=Get-ShadowFailedGenerationEvidenceSafely -OperationId 'operation-1' -CaptureProbe $okProbe
$bad=Get-ShadowFailedGenerationEvidenceSafely -OperationId 'operation-2' -CaptureProbe $badProbe
[pscustomobject]@{{ok=$ok;bad=$bad}} | ConvertTo-Json -Compress -Depth 8
"""
    result = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script], cwd=ROOT, capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout.strip())
    assert payload["ok"]["status"] == "captured"
    assert payload["ok"]["operation_id"] == "operation-1"
    assert payload["bad"]["status"] == "capture_failed"
    assert payload["bad"]["failure_code"] == "startup_evidence_capture_failed_closed"
    assert "sentinel-secret" not in result.stdout


def test_embedded_evidence_capture_redacts_logs_and_whitelists_stack_fields(monkeypatch):
    source = SETTER.read_text(encoding="utf-8")
    embedded = source.split("python3 - <<'__SHADOW_STARTUP_EVIDENCE__'", 1)[1].split("__SHADOW_STARTUP_EVIDENCE__", 1)[0]
    definitions = embedded.split("payload = {", 1)[0]
    definitions = definitions.replace("__APP_JSON__", repr("app")).replace("__SCHEDULER_JSON__", repr("scheduler")).replace("__OPERATION_JSON__", repr("operation"))
    namespace = {}
    exec(definitions, namespace)

    diagnostic = {
        "schema": "startup-diagnostic-v1",
        "boot_id": "12345678-1234-5678-1234-567812345678",
        "phase": "delayed_start_stack",
        "status": "snapshot",
        "threads": [{"thread_id": 1, "frames": [{"file": "app.py", "function": "init_db", "line": 2632, "locals": {"secret": "leak"}}]}],
        "environment": {"SECRET_KEY": "leak"},
    }
    raw = "\n".join(
        [
            "[startup-diagnostic] " + json.dumps(diagnostic),
            "SECRET_KEY=sentinel-private-value",
            "connecting to postgresql://user:opaquevalue@example.invalid/db",
            "ordinary bounded log line",
        ]
    )

    class Result:
        returncode = 0
        stdout = raw

    monkeypatch.setitem(namespace, "bounded", lambda command, timeout: Result())
    captured = namespace["safe_logs"]("container-id")
    encoded = json.dumps(captured, sort_keys=True)
    assert "sentinel-private-value" not in encoded
    assert "opaquevalue" not in encoded
    assert "environment" not in encoded
    assert "locals" not in encoded
    assert captured["lines"] == [
        "[redacted suspicious log line]",
        "connecting to postgresql://[redacted]@example.invalid/db",
        "ordinary bounded log line",
    ]
    frame = captured["startup_diagnostics"][0]["threads"][0]["frames"][0]
    assert frame == {"file": "app.py", "function": "init_db", "line": 2632}


def test_failed_generation_summary_names_blocked_phase_and_latest_safe_stack():
    source = SETTER.read_text(encoding="utf-8")
    embedded = source.split("python3 - <<'__SHADOW_STARTUP_EVIDENCE__'", 1)[1].split(
        "__SHADOW_STARTUP_EVIDENCE__", 1
    )[0]
    definitions = embedded.split("payload = {", 1)[0]
    definitions = definitions.replace("__APP_JSON__", repr("app")).replace(
        "__SCHEDULER_JSON__", repr("scheduler")
    ).replace("__OPERATION_JSON__", repr("operation"))
    namespace = {}
    exec(definitions, namespace)
    events = [
        {"boot_id": "boot-1", "elapsed_seconds": 0.8, "phase": "app_module_import", "status": "success"},
        {"boot_id": "boot-1", "elapsed_seconds": 0.9, "phase": "database_initialization", "status": "start"},
        {
            "boot_id": "boot-1",
            "elapsed_seconds": 135.9,
            "phase": "delayed_start_stack",
            "status": "snapshot",
            "snapshot_sequence": 3,
            "threads": [
                {
                    "thread_id": 7,
                    "frames": [
                        {"file": "app.py", "function": "init_db", "line": 2649},
                        {"file": "cursor.py", "function": "execute", "line": 88},
                    ],
                }
            ],
        },
    ]
    summary = namespace["summarize_startup"](events)
    assert summary["boot_id"] == "boot-1"
    assert summary["last_completed_phase"] == "app_module_import"
    assert summary["current_phase"] == "database_initialization"
    assert summary["snapshot_count"] == 1
    assert summary["latest_stack_threads"][0]["frames"][-1] == {
        "file": "cursor.py",
        "function": "execute",
        "line": 88,
    }


def test_failed_generation_evidence_is_atomically_persisted_before_recovery(tmp_path):
    setter = str(SETTER).replace("'", "''")
    destination = str(tmp_path / "evidence").replace("'", "''")
    script = f"""
$ErrorActionPreference='Stop'
$source=Get-Content '{setter}' -Raw
$start=$source.IndexOf('function Get-ShadowFailedGenerationEvidence')
$end=$source.IndexOf('function New-ShadowRecoveredFailureResult')
Invoke-Expression $source.Substring($start,$end-$start)
$evidence=[pscustomobject]@{{status='captured';operation_id='op-safe';summary=[pscustomobject]@{{app=[pscustomobject]@{{current_phase='database_initialization'}}}}}}
$result=Persist-ShadowFailedGenerationEvidenceSafely -OperationId 'op-safe' -Evidence $evidence -EvidenceDirectory '{destination}'
[pscustomobject]@{{result=$result;exists=(Test-Path -LiteralPath $result.path);temporary_files=@(Get-ChildItem -LiteralPath '{destination}' -Filter '*.tmp' -ErrorAction SilentlyContinue).Count;payload=(Get-Content -Raw -LiteralPath $result.path|ConvertFrom-Json)}}|ConvertTo-Json -Compress -Depth 8
"""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout.strip())
    assert payload["result"]["status"] == "persisted"
    assert payload["exists"] is True
    assert payload["temporary_files"] == 0
    assert payload["payload"]["operation_id"] == "op-safe"
    assert payload["payload"]["summary"]["app"]["current_phase"] == "database_initialization"


def test_failed_generation_persistence_failure_is_sanitized_and_non_throwing(tmp_path):
    setter = str(SETTER).replace("'", "''")
    blocking_file = tmp_path / "not-a-directory"
    blocking_file.write_text("fixture", encoding="utf-8")
    destination = str(blocking_file).replace("'", "''")
    script = f"""
$ErrorActionPreference='Stop'
$source=Get-Content '{setter}' -Raw
$start=$source.IndexOf('function Get-ShadowFailedGenerationEvidence')
$end=$source.IndexOf('function New-ShadowRecoveredFailureResult')
Invoke-Expression $source.Substring($start,$end-$start)
$evidence=[pscustomobject]@{{status='captured';operation_id='op-safe';sentinel='must-not-appear-in-error'}}
$result=Persist-ShadowFailedGenerationEvidenceSafely -OperationId 'op-safe' -Evidence $evidence -EvidenceDirectory '{destination}'
$result|ConvertTo-Json -Compress
"""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout.strip())
    assert payload == {
        "status": "persistence_failed",
        "failure_code": "atomic_evidence_persistence_failed",
    }
    assert "must-not-appear" not in result.stdout + result.stderr


def test_evidence_capture_precedes_exact_target_recovery_and_is_bounded():
    setter = SETTER.read_text(encoding="utf-8")
    capture = setter.index("Get-ShadowFailedGenerationEvidenceSafely -OperationId")
    persist = setter.index("Persist-ShadowFailedGenerationEvidenceSafely -OperationId", capture)
    rollback = setter.index("Invoke-ShadowHelper -RequestedOperation 'rollback'", capture)
    assert capture < persist < rollback
    assert "MAX_LOG_BYTES = 32768" in setter
    assert "MAX_LOG_LINES = 160" in setter
    assert "-TimeoutSeconds 20" in setter
    assert 'docker", "inspect", name, "--format", template' in setter
    assert "Config.Env" not in setter


def test_real_wait_convergence_fail_closed_matrix_and_attempt_isolation():
    script = f"""
$ErrorActionPreference='Stop'
$source=Get-Content '{str(SETTER).replace("'", "''")}' -Raw; Invoke-Expression $source.Substring($source.IndexOf('function Get-ShadowRuntimeFlag'),$source.IndexOf('$result = $null')-$source.IndexOf('function Get-ShadowRuntimeFlag'))
function Invoke-Case {{ param([string]$mode)
  $script:n=0; $script:t=[datetime]'2026-01-01T00:00:00Z'
  $before=[pscustomobject]@{{app_container_id='old-app';scheduler_container_id='old-sch';app_image_id='img';scheduler_image_id='img'}}
  $helper=[pscustomobject]@{{effective=[pscustomobject]@{{enabled=$true;state='enabled'}}}}
  $health={{
    $script:n++
    if($mode -eq 'timeout'){{ return [pscustomobject]@{{app_container_id='new-app';scheduler_container_id='old-sch';app_image_id='img';scheduler_image_id='img';app='running|healthy';scheduler='running';healthz=200}} }}
    if($mode -eq 'image'){{ return [pscustomobject]@{{app_container_id='new-app';scheduler_container_id='new-sch';app_image_id='wrong';scheduler_image_id='img';app='running|healthy';scheduler='running';healthz=200}} }}
    if($mode -eq 'replacement' -and $script:n -eq 2){{ return [pscustomobject]@{{app_container_id='new-app-2';scheduler_container_id='new-sch';app_image_id='img';scheduler_image_id='img';app='running|healthy';scheduler='running';healthz=200}} }}
    return [pscustomobject]@{{app_container_id='new-app';scheduler_container_id='new-sch';app_image_id='img';scheduler_image_id='img';app='running|healthy';scheduler='running';healthz=200}}
  }}
  $runtime={{ param($a,$s) if($mode -eq 'runtime_throw'){{ throw 'sentinel-secret-runtime' }}; [pscustomobject]@{{app=[pscustomobject]@{{enabled=$true;state='enabled'}};scheduler=[pscustomobject]@{{enabled=$true;state='enabled'}}}} }}
  $clock={{ $script:t }}; $sleep={{ param($s) $script:t=$script:t.AddSeconds(1) }}
  try {{ $r=Wait-ShadowPostChangeConvergence -HelperResult $helper -ExpectedOperation enable -BeforeHealth $before -DeadlineSeconds 2 -PollIntervalSeconds 1 -HealthProbe $health -RuntimeProbe $runtime -Clock $clock -SleepAction $sleep; [pscustomobject]@{{mode=$mode;success=$true;attempts=$r.attempts;stable=$true}} }}
  catch {{ [pscustomobject]@{{mode=$mode;success=$false;attempts=$_.Exception.Data['attempts'];stable=$_.Exception.Data['identity_stable'];runtime=if($_.Exception.Data['runtime']){{'present'}}else{{'null'}};message=$_.Exception.Message}} }}
}}
@('timeout','image','replacement','runtime_throw') | % {{ Invoke-Case $_ }} | ConvertTo-Json -Compress -Depth 6
"""
    result = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script], cwd=ROOT, capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    rows = {row["mode"]: row for row in json.loads(result.stdout.strip())}
    assert all(not rows[name]["success"] for name in rows if name != "replacement"), result.stdout
    assert rows["replacement"]["success"] is True
    assert rows["timeout"]["stable"] is False
    assert rows["runtime_throw"]["runtime"] == "null"
    assert "sentinel-secret" not in result.stdout


def test_current_attempt_image_observation_is_used_after_retry():
    script = f"""
$ErrorActionPreference='Stop'; $source=Get-Content '{str(SETTER).replace("'", "''")}' -Raw; Invoke-Expression $source.Substring($source.IndexOf('function Get-ShadowRuntimeFlag'),$source.IndexOf('$result = $null')-$source.IndexOf('function Get-ShadowRuntimeFlag'))
$script:n=0; $script:t=[datetime]'2026-01-01Z'; $before=[pscustomobject]@{{app_container_id='old';scheduler_container_id='old-s';app_image_id='img-good';scheduler_image_id='img-good'}}; $helper=[pscustomobject]@{{effective=[pscustomobject]@{{enabled=$true;state='enabled'}}}}
function H {{ $script:n++; if($script:n -eq 1){{ [pscustomobject]@{{app_container_id='new';scheduler_container_id='new-s';app_image_id='img-bad';scheduler_image_id='img-bad'}} }} else {{ [pscustomobject]@{{app_container_id='new';scheduler_container_id='new-s';app_image_id='img-good';scheduler_image_id='img-good'}} }} }}
$rprobe={{ param($a,$s) [pscustomobject]@{{app=[pscustomobject]@{{enabled=$true;state='enabled'}};scheduler=[pscustomobject]@{{enabled=$true;state='enabled'}}}} }}; $clock={{$script:t}}; $sleep={{param($x) $script:t=$script:t.AddSeconds(1)}}
$r=Wait-ShadowPostChangeConvergence -HelperResult $helper -ExpectedOperation enable -BeforeHealth $before -DeadlineSeconds 4 -PollIntervalSeconds 1 -HealthProbe ${{function:H}} -RuntimeProbe $rprobe -Clock $clock -SleepAction $sleep
if($r.health.app_image_id -ne 'img-good'){{throw 'current-attempt image was not used'}}; 'OK'
"""
    result = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script], cwd=ROOT, capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 0, result.stdout + result.stderr


def test_setter_is_allowlist_only_owner_gated_and_fully_bounded():
    setter = SETTER.read_text(encoding="utf-8")
    helper = HELPER.read_text(encoding="utf-8")

    for operation in ("status", "dry-run", "enable", "disable", "rollback"):
        assert operation in setter
        assert operation in helper
    assert "SHADOW_JUDGING_ENABLED" in setter
    assert "SHADOW_JUDGING_ENABLED" in helper
    assert "production_env_path -ne '/opt/go-odyssey/.env'" in setter
    assert "Assert-OwnerGate -Provided $OwnerGate -Expected $ownerGates[$Operation]" in setter
    assert "enable = 'GO_ENABLE_SHADOW'" in setter
    assert "disable = 'GO_DISABLE_SHADOW'" in setter
    assert "rollback = 'GO_SHADOW_ROLLBACK'" in setter
    assert '"enable": "GO_ENABLE_SHADOW"' in helper
    assert '"disable": "GO_DISABLE_SHADOW"' in helper
    assert '"rollback": "GO_SHADOW_ROLLBACK"' in helper
    assert 'OWNER_GATE = "GO_DEPLOY"' not in helper
    assert "Mutating Shadow Judging operations require -Execute." in setter
    assert "--execute" in setter
    assert "--owner-gate" in setter
    assert setter.count("Invoke-BoundedSshCommand") >= 4
    assert "Invoke-RemoteShellCommand" not in setter
    assert "Invoke-RemoteText" not in setter
    assert "ValueFromPipeline" not in setter
    assert "Set-Content" not in setter
    assert "docker restart" not in setter
    assert "curl" not in setter.lower()
    assert "up -d --no-build --no-deps --force-recreate app scheduler" in setter
    assert ".Config.Image" in setter and ".Image" in setter
    assert ".shadow-judging-backups" in setter
    assert "governed pre-change state was restored and verified" in setter
    assert "Wait-ShadowPostChangeConvergence" in setter
    assert "deadline = time.monotonic() + 180" in setter
    assert "-TimeoutSeconds 200" in setter
    for field in (
        "app_container_identity_before",
        "app_container_identity_after",
        "scheduler_container_identity_before",
        "scheduler_container_identity_after",
        "expected_app_image_id",
        "observed_app_image_id",
        "identity_stable_during_last_sample",
    ):
        assert field in setter
    for field in (
        "original_failure_stage",
        "original_failure_code",
        "original_failure_message",
        "verification_attempt_count",
        "verification_elapsed_seconds",
        "final_verified_state",
        "lock_cleanup_result",
    ):
        assert field in setter


def test_runbook_records_operation_specific_gates_without_raw_recipes():
    runbook = RUNBOOK.read_text(encoding="utf-8")
    assert runbook.count("PENDING OWNER-GATED DRILL") >= 2
    assert "GO_ENABLE_SHADOW" in runbook
    assert "GO_DISABLE_SHADOW" in runbook
    assert "GO_SHADOW_ROLLBACK" in runbook
    assert "GO_KILL_SWITCH_DRILL" in runbook
    assert "`GO_DEPLOY` does not authorize" in runbook
    assert "DEPLOY-GOV-1" in runbook
    assert "-Operation status" in runbook
    assert "-Operation dry-run" in runbook
    assert "-Operation enable" in runbook
    assert "-Operation disable" in runbook
    assert "-Operation rollback" in runbook
    assert "zero new Shadow events" in runbook
    assert "Admin Shadow dashboard remains readable" in runbook
    assert "Shadow event-store writes resume" in runbook
    assert "legacy_infrastructure_healthy" in runbook
    assert "actual Legacy judging canary" in runbook
    assert "all three Legacy" in runbook
    assert "docker exec" not in runbook.lower()
    assert "docker compose restart" not in runbook.lower()
    assert "/opt/go-odyssey/.env" not in runbook


def test_setter_powershell_parses_without_errors():
    escaped_path = str(SETTER).replace("'", "''")
    command = (
        "$errors=$null; "
        f"[System.Management.Automation.Language.Parser]::ParseFile('{escaped_path}',"
        "[ref]$null,[ref]$errors)|Out-Null; "
        "if($errors.Count){$errors|ForEach-Object{$_.Message};exit 1}"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
