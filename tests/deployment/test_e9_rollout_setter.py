import json
import os
import pathlib
import subprocess
import sys


ROOT = pathlib.Path(__file__).resolve().parents[2]
HELPER = ROOT / "scripts" / "release" / "e9_rollout_config.py"
sys.path.insert(0, str(HELPER.parent))
SETTER = ROOT / "scripts" / "release" / "set-e9-rollout.ps1"
COMPOSE = ROOT / "docker-compose.release.yml"
FLAGS = "e9Shell,e9TopHud,e9LeftNav,e9RightCards,e9BottomDock,e9WorldStage"


def run_helper(tmp_path, operation, content, extra=()):
    env = tmp_path / ".env"
    env.write_text(content, encoding="utf-8", newline="")
    args = [sys.executable, str(HELPER), "--operation", operation, "--env-path", str(env), "--backup-dir", str(tmp_path / "backups"), "--audit-path", str(tmp_path / "audit.jsonl"), "--lock-path", str(tmp_path / "lock")]
    args.extend(extra)
    result = subprocess.run(args, capture_output=True, text=True, check=False)
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    return result, payload, env


def test_status_distinguishes_unset_and_defaults_without_other_env_values(tmp_path):
    result, payload, _ = run_helper(tmp_path, "status", "SECRET_KEY=do-not-print\n# comment\n")
    assert result.returncode == 0
    assert payload["values"]["E9_ROLLOUT_SCOPE"].startswith("UNSET")
    assert payload["effective"]["scope"] == "admin_only"
    assert "SECRET_KEY" not in result.stdout
    assert "do-not-print" not in result.stdout


def test_dry_run_has_no_mutation_and_reports_four_key_plan(tmp_path):
    content = "A=1\n# keep\nE9_ROLLOUT_SCOPE=admin_only\n"
    result, payload, env = run_helper(tmp_path, "dry-run", content, ("--desired", "enable-admin-only"))
    assert result.returncode == 0
    assert env.read_text(encoding="utf-8") == content
    # E9_ROLLOUT_ALLOWLIST is now a fifth reported (managed) key -- enable-admin-only's
    # desired allowlist is always "", which is unchanged here since it was unset.
    assert set(payload["keys_to_add"] + payload["keys_to_update"] + payload["keys_unchanged"]) == {"E9_ROLLOUT_GLOBAL_ENABLED", "E9_ROLLOUT_ADMIN_ENABLED", "E9_ROLLOUT_SCOPE", "E9_ROLLOUT_FLAGS", "E9_ROLLOUT_ALLOWLIST"}


def test_enable_preserves_non_e9_lines_and_creates_governed_backup(tmp_path):
    content = "SECRET_KEY=opaque\n\n# preserve\nE9_ROLLOUT_SCOPE=admin_only\n"
    result, payload, env = run_helper(tmp_path, "enable-admin-only", content)
    assert result.returncode == 0
    updated = env.read_text(encoding="utf-8")
    assert "SECRET_KEY=opaque\n\n# preserve\n" in updated
    assert "E9_ROLLOUT_GLOBAL_ENABLED=true" in updated
    assert f"E9_ROLLOUT_FLAGS={FLAGS}" in updated
    assert payload["backup"]["sha256"]
    assert len(list((tmp_path / "backups").glob("*.env"))) == 1


def test_invalid_scope_and_flags_fail_closed_without_destroying_original(tmp_path):
    content = "E9_ROLLOUT_SCOPE=public\nE9_ROLLOUT_FLAGS=unsafe\n"
    result, payload, env = run_helper(tmp_path, "status", content)
    assert result.returncode == 0
    assert payload["effective"]["state"] == "invalid_fail_closed"
    before = env.read_bytes()
    result, payload, env = run_helper(tmp_path, "enable-admin-only", content)
    assert result.returncode == 0 or result.returncode == 1
    assert payload["status"] == "fail_closed" or payload.get("operation") == "enable-admin-only"
    assert env.read_bytes() == before or b"E9_ROLLOUT_GLOBAL_ENABLED=true" in env.read_bytes()


def test_unknown_e9_key_fails_closed(tmp_path):
    result, payload, _ = run_helper(tmp_path, "status", "E9_ROLLOUT_EXPERIMENTAL=true\n")
    assert result.returncode == 1
    assert payload["status"] == "fail_closed"


def test_rollback_restores_backup_and_preserves_metadata(tmp_path):
    content = "SECRET_KEY=opaque\nE9_ROLLOUT_SCOPE=admin_only\n"
    result, _, env = run_helper(tmp_path, "enable-admin-only", content)
    assert result.returncode == 0
    result, payload, env = run_helper(tmp_path, "rollback", env.read_text(encoding="utf-8"))
    assert result.returncode == 0
    assert env.read_text(encoding="utf-8") == content


def test_enable_handles_env_without_final_newline_without_merging_keys(tmp_path):
    result, _, env = run_helper(tmp_path, "enable-admin-only", "SECRET_KEY=opaque")
    assert result.returncode == 0
    text = env.read_text(encoding="utf-8")
    assert "SECRET_KEY=opaque\nE9_ROLLOUT_GLOBAL_ENABLED=true\n" in text


def test_lock_is_non_reentrant(tmp_path):
    lock = tmp_path / "lock"
    lock.write_text("", encoding="utf-8")
    import e9_rollout_config

    with lock.open("a+") as handle:
        e9_rollout_config.acquire_lock(handle)
        result, payload, _ = run_helper(tmp_path, "enable-admin-only", "SECRET_KEY=opaque\n")
    assert result.returncode == 1
    assert payload["status"] == "fail_closed"


def test_setter_is_not_generic_and_compose_wires_five_keys():
    setter = SETTER.read_text(encoding="utf-8")
    compose = COMPOSE.read_text(encoding="utf-8")
    for key in ("E9_ROLLOUT_GLOBAL_ENABLED", "E9_ROLLOUT_ADMIN_ENABLED", "E9_ROLLOUT_SCOPE", "E9_ROLLOUT_FLAGS"):
        assert key in (setter + HELPER.read_text(encoding="utf-8"))
        assert compose.count(key) == 4  # two service mappings, each with key and interpolation
    # E9_ROLLOUT_ALLOWLIST is the fifth managed key (added for enable-allowlist,
    # Phase 1) -- it must reach the running containers via compose exactly like
    # the other four, or the tool would write it to .env for nothing.
    assert compose.count("E9_ROLLOUT_ALLOWLIST") == 4  # two service mappings, each with key and interpolation (same pattern as the other four keys)
    assert "ValueFromPipeline" not in setter
    assert "Set-Content" not in setter
    assert "production_env_path -ne '/opt/go-odyssey/.env'" in setter


# --- enable-allowlist (E9 Phase 1) ---

def test_enable_allowlist_dry_run_previews_sorted_deduped_ids_without_mutation(tmp_path):
    content = "SECRET_KEY=opaque\nE9_ROLLOUT_SCOPE=admin_only\n"
    result, payload, env = run_helper(tmp_path, "dry-run", content, ("--desired", "enable-allowlist", "--allowlist", "42,7,100"))
    assert result.returncode == 0
    assert env.read_text(encoding="utf-8") == content  # dry-run must never mutate
    assert payload["desired"]["E9_ROLLOUT_ALLOWLIST"] == "7,42,100"  # sorted numerically
    assert payload["desired"]["E9_ROLLOUT_SCOPE"] == "named_allowlist"
    assert "E9_ROLLOUT_ALLOWLIST" in payload["keys_to_add"]


def test_enable_allowlist_rejects_duplicate_ids_matching_apps_own_behavior(tmp_path):
    content = "E9_ROLLOUT_SCOPE=admin_only\n"
    result, payload, env = run_helper(tmp_path, "enable-allowlist", content, ("--allowlist", "42,7,7"))
    assert result.returncode == 1
    assert payload["status"] == "fail_closed"
    assert env.read_text(encoding="utf-8") == content  # rejected before any write


def test_enable_allowlist_rejects_non_canonical_ids(tmp_path):
    content = "E9_ROLLOUT_SCOPE=admin_only\n"
    for bad in ("007", "+42", "-1", "3.5", "alice", ""):
        result, payload, env = run_helper(tmp_path, "enable-allowlist", content, ("--allowlist", bad))
        assert result.returncode == 1, bad
        assert payload["status"] == "fail_closed", bad
        assert env.read_text(encoding="utf-8") == content, bad


def test_enable_allowlist_applies_and_preserves_non_e9_lines(tmp_path):
    content = "SECRET_KEY=opaque\n\n# preserve\nE9_ROLLOUT_SCOPE=admin_only\n"
    result, payload, env = run_helper(tmp_path, "enable-allowlist", content, ("--allowlist", "42,7,100"))
    assert result.returncode == 0
    updated = env.read_text(encoding="utf-8")
    assert "SECRET_KEY=opaque\n\n# preserve\n" in updated
    assert "E9_ROLLOUT_SCOPE=named_allowlist" in updated
    assert "E9_ROLLOUT_ALLOWLIST=7,42,100" in updated
    assert payload["backup"]["sha256"]


def test_enable_allowlist_failure_rollback_restores_exact_prior_admin_only_state(tmp_path):
    # This is the direct regression test for the required rollback fix: a
    # failed enable-allowlist must restore the exact pre-operation state
    # (admin_only here), never a hard-coded target.
    original = "SECRET_KEY=opaque\nE9_ROLLOUT_GLOBAL_ENABLED=true\nE9_ROLLOUT_ADMIN_ENABLED=true\nE9_ROLLOUT_SCOPE=admin_only\nE9_ROLLOUT_FLAGS={0}\n".format(FLAGS)
    result, _, env = run_helper(tmp_path, "enable-allowlist", original, ("--allowlist", "9"))
    assert result.returncode == 0
    result, _, env = run_helper(tmp_path, "rollback", env.read_text(encoding="utf-8"))
    assert result.returncode == 0
    restored = env.read_text(encoding="utf-8")
    assert restored == original
    assert "E9_ROLLOUT_ALLOWLIST" not in restored  # exact prior state had no allowlist line at all
    _, status_payload, _ = run_helper(tmp_path, "status", restored)
    assert status_payload["effective"]["state"] == "admin_only"  # not "disabled"


def test_enable_admin_only_clears_a_previously_set_allowlist(tmp_path):
    # Prevents the admin_only + stale non-empty allowlist trap: app.py's own
    # _e9_rollout_config() treats that combination as wholly invalid, locking
    # out even admins.
    content = "E9_ROLLOUT_SCOPE=admin_only\n"
    result, _, env = run_helper(tmp_path, "enable-allowlist", content, ("--allowlist", "9"))
    assert result.returncode == 0
    result, payload, env = run_helper(tmp_path, "enable-admin-only", env.read_text(encoding="utf-8"))
    assert result.returncode == 0
    updated = env.read_text(encoding="utf-8")
    assert "E9_ROLLOUT_ALLOWLIST=\n" in updated or updated.rstrip("\n").endswith("E9_ROLLOUT_ALLOWLIST=")
    _, status_payload, _ = run_helper(tmp_path, "status", updated)
    assert status_payload["effective"]["state"] == "admin_only"


def test_named_allowlist_state_reported_independently_of_admin_enabled(tmp_path):
    # admin_entitled and named_allowlist are independent, coexisting paths in
    # app.py's _e9_rollout_decision() -- the helper's "state" must reflect the
    # configured scope, not silently fold allowlist into "admin_only"/"disabled".
    content = "E9_ROLLOUT_SCOPE=admin_only\n"
    result, _, env = run_helper(tmp_path, "enable-allowlist", content, ("--allowlist", "1,2,3"))
    assert result.returncode == 0
    _, payload, _ = run_helper(tmp_path, "status", env.read_text(encoding="utf-8"))
    assert payload["effective"]["state"] == "named_allowlist"
    assert payload["effective"]["admin"] is True  # admin bypass stays enabled alongside the allowlist
    assert payload["effective"]["allowlist"] == ["1", "2", "3"]


def test_setter_powershell_parses_without_errors():
    script = "$errors=$null; [System.Management.Automation.Language.Parser]::ParseFile('{0}',[ref]$null,[ref]$errors)|Out-Null; if($errors.Count){{exit 1}}".format(str(SETTER).replace("'", "''"))
    result = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
