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


def invoke_helper(
    tmp_path,
    operation,
    content=UNSET,
    *,
    desired=None,
    execute=False,
    owner_gate=None,
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


def mutate(tmp_path, operation, content=UNSET):
    return invoke_helper(
        tmp_path,
        operation,
        content,
        execute=True,
        owner_gate="GO_DEPLOY",
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


def test_all_mutations_require_execute_and_exact_owner_gate(tmp_path):
    original = "SHADOW_JUDGING_ENABLED=false\nOPAQUE=synthetic\n"
    result, payload, env_path = invoke_helper(tmp_path, "enable", original)
    assert result.returncode == 1
    assert payload == {"reason": "mutation_requires_execute", "status": "fail_closed"}
    assert env_path.read_text(encoding="utf-8") == original

    result, payload, env_path = invoke_helper(
        tmp_path,
        "enable",
        execute=True,
        owner_gate="NOT_AUTHORIZED",
    )
    assert result.returncode == 1
    assert payload == {"reason": "owner_gate_mismatch", "status": "fail_closed"}
    assert env_path.read_text(encoding="utf-8") == original
    assert not (tmp_path / "backups").exists()


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

    result, payload, env_path = mutate(tmp_path, "rollback")
    assert result.returncode == 0
    assert env_path.read_bytes() == original
    assert payload["effective"]["state"] == "disabled"
    assert payload["backup_id"]
    assert payload["rollback_backup_id"]
    assert payload["backup_id"] != payload["rollback_backup_id"]
    assert len(list((tmp_path / "backups").glob("*.env"))) == 2

    result, payload, env_path = mutate(tmp_path, "rollback")
    assert result.returncode == 0
    assert env_path.read_bytes() == enabled
    assert payload["effective"]["state"] == "enabled"


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


def test_setter_is_allowlist_only_owner_gated_and_fully_bounded():
    setter = SETTER.read_text(encoding="utf-8")
    helper = HELPER.read_text(encoding="utf-8")

    for operation in ("status", "dry-run", "enable", "disable", "rollback"):
        assert operation in setter
        assert operation in helper
    assert "SHADOW_JUDGING_ENABLED" in setter
    assert "SHADOW_JUDGING_ENABLED" in helper
    assert "production_env_path -ne '/opt/go-odyssey/.env'" in setter
    assert "Assert-OwnerGate -Provided $OwnerGate -Expected 'GO_DEPLOY'" in setter
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


def test_runbook_records_owner_gate_and_pending_drill_without_raw_recipes():
    runbook = RUNBOOK.read_text(encoding="utf-8")
    assert runbook.count("PENDING OWNER-GATED DRILL") >= 2
    assert "GO_DEPLOY" in runbook
    assert "DEPLOY-GOV-1" in runbook
    assert "-Operation status" in runbook
    assert "-Operation dry-run" in runbook
    assert "-Operation enable" in runbook
    assert "-Operation disable" in runbook
    assert "-Operation rollback" in runbook
    assert "zero new Shadow events" in runbook
    assert "Admin Shadow dashboard remains readable" in runbook
    assert "Shadow events resume" in runbook
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
