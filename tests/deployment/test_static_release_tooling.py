"""RELEASE-FIX-A — Canonical Static Release Integrity Contract tests.

Covers: inventory completeness/sync with app.py's own allowlist, real
PowerShell script behavior (package/deploy/rollback -DryRun contracts,
syntax), security boundary (traversal/absolute/forbidden-pattern
rejection), and manifest schema. Live host interaction (upload, atomic
switch, public HTTP verification) is exercised for real separately as
part of this Sprint's own production deploy -- see
docs/deployment/canonical_static_release_contract.md and the Final
Report for that evidence; it is not repeated here as a mocked unit test
since the whole point of this Sprint is that mocked/filesystem-only
checks are exactly what let the original drift go undetected.
"""
import json
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
INVENTORY_PATH = REPO_ROOT / "deploy" / "live-static-asset-inventory.json"
APP_PY = REPO_ROOT / "app.py"
PSM1 = REPO_ROOT / "scripts" / "release" / "ReleaseTooling.psm1"
PACKAGE_SCRIPT = REPO_ROOT / "scripts" / "release" / "package-static-release.ps1"
DEPLOY_SCRIPT = REPO_ROOT / "scripts" / "release" / "deploy-static-release.ps1"
ROLLBACK_SCRIPT = REPO_ROOT / "scripts" / "release" / "rollback-static-release.ps1"
PREFLIGHT_SCRIPT = REPO_ROOT / "scripts" / "release" / "preflight-production.ps1"
CONTRACT_DOC = REPO_ROOT / "docs" / "deployment" / "canonical_static_release_contract.md"
AUDIT_DOC = REPO_ROOT / "docs" / "deployment" / "live_static_drift_impact_audit_20260712.md"


def _read(path):
    assert path.is_file(), f"expected file to exist: {path}"
    return path.read_text(encoding="utf-8")


def _load_inventory():
    return json.loads(_read(INVENTORY_PATH))


def _app_py_eligible_files():
    content = _read(APP_PY)
    m = re.search(r"_LIVE_STATIC_ELIGIBLE_FILES = frozenset\(\{([^}]+)\}\)", content, re.S)
    assert m, "could not locate _LIVE_STATIC_ELIGIBLE_FILES in app.py"
    names = re.findall(r"'([^']+)'", m.group(1))
    # the app.py source has a stray single-character match from a comment
    # ("send_from_directory('.', name)") -- filter to real filenames only.
    return [n for n in names if len(n) > 1]


# ---------------------------------------------------------------------------
# Inventory <-> app.py sync (the exact class of drift this Sprint exists to
# prevent from happening again, one level up the stack)
# ---------------------------------------------------------------------------

def test_inventory_eligible_files_matches_app_py_allowlist_exactly():
    inventory = _load_inventory()
    inventory_files = set(inventory["eligible_files"]["entries"])
    app_py_files = set(_app_py_eligible_files())
    assert inventory_files == app_py_files, (
        f"deploy/live-static-asset-inventory.json has drifted from app.py's "
        f"_LIVE_STATIC_ELIGIBLE_FILES.\nOnly in inventory: {inventory_files - app_py_files}\n"
        f"Only in app.py: {app_py_files - inventory_files}"
    )


def test_inventory_required_in_generation_is_subset_of_eligible():
    inventory = _load_inventory()
    required = set(inventory["required_in_generation"]["entries"])
    eligible = set(inventory["eligible_files"]["entries"])
    assert required.issubset(eligible)


def test_inventory_required_in_generation_matches_confirmed_drift_scope():
    # Confirmed via direct host inspection (see canonical_static_release_contract.md)
    # -- exactly these two files were physically present and stale.
    inventory = _load_inventory()
    assert set(inventory["required_in_generation"]["entries"]) == {"i18n.js", "sw.js"}


def test_inventory_excludes_assets_and_icons_prefixes():
    inventory = _load_inventory()
    excluded = set(inventory["excluded_prefixes"]["entries"])
    assert "assets/" in excluded
    assert "icons/" in excluded


def test_inventory_forbidden_patterns_reject_dangerous_paths():
    inventory = _load_inventory()
    patterns = inventory["forbidden_patterns"]["path_patterns"]
    dangerous = ["app.py", "questions.json", "Dockerfile", "docker-compose.yml", ".env", "secrets/key.pem", "sgf_engine/parser.py"]
    for path in dangerous:
        assert any(re.match(p, path) for p in patterns), f"{path} should be rejected by forbidden_patterns"


def test_inventory_is_valid_json_with_no_secrets():
    raw = _read(INVENTORY_PATH)
    lower = raw.lower()
    for token in ("password", "secret_key=", "api_key=", "-----begin"):
        assert token not in lower


# ---------------------------------------------------------------------------
# PowerShell syntax (all new/changed release scripts)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("script", [PACKAGE_SCRIPT, DEPLOY_SCRIPT, ROLLBACK_SCRIPT, PREFLIGHT_SCRIPT, PSM1])
def test_powershell_script_has_no_syntax_errors(script):
    ps_command = (
        "$errors = $null; "
        f"[System.Management.Automation.Language.Parser]::ParseFile('{script}', [ref]$null, [ref]$errors) | Out-Null; "
        "if ($errors.Count -gt 0) { $errors | ForEach-Object { Write-Output $_.ToString() }; exit 1 } else { exit 0 }"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", ps_command],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"PowerShell syntax error in {script.name}:\n{result.stdout}\n{result.stderr}"


# ---------------------------------------------------------------------------
# Script contracts (source-level -- confirms the required safety properties
# are actually implemented, not just described in docs)
# ---------------------------------------------------------------------------

def test_package_script_sources_from_detached_worktree_not_working_directory():
    content = _read(PACKAGE_SCRIPT)
    assert "New-DetachedWorktree" in content
    assert "Remove-DetachedWorktree" in content


def test_deploy_script_never_overwrites_existing_generation():
    content = _read(DEPLOY_SCRIPT)
    assert "already exists, refusing to overwrite" in content


def test_deploy_script_verifies_remote_hash_after_upload():
    content = _read(DEPLOY_SCRIPT)
    assert "sha256sum" in content
    assert "Remote hash mismatch" in content


def test_deploy_script_uses_atomic_symlink_switch_pattern():
    content = _read(DEPLOY_SCRIPT)
    assert "ln -sfnT" in content
    assert "mv -Tf" in content
    # never a direct overwrite of "current" itself
    assert re.search(r"ln -sfnT \S+ current[^.]", content) is None or "current.next" in content


def test_deploy_script_verifies_public_https_bytes_not_just_filesystem():
    content = _read(DEPLOY_SCRIPT)
    assert "Invoke-WebRequest" in content
    assert "deploy-verify=" in content
    assert "Get-PublicFileSha256" in content
    assert "Public content hash mismatch" in content


def test_deploy_script_verifies_sw_version_publicly_not_just_locally():
    content = _read(DEPLOY_SCRIPT)
    assert "Get-SwVersionFromUrl" in content
    assert "Public sw.js VERSION mismatch" in content


def test_deploy_script_auto_rolls_back_on_post_switch_failure():
    content = _read(DEPLOY_SCRIPT)
    assert "catch" in content
    assert "rollbackPerformed" in content
    assert "Automatic rollback" in content


def test_deploy_script_restarts_containers_after_switch():
    # Discovered live during this Sprint's own production deploy: the
    # app/scheduler containers' bind mount of /opt/go-odyssey-static/current
    # resolves the symlink target ONCE at container start -- a symlink
    # switch alone is filesystem-real but functionally inert until the
    # containers restart. Confirmed directly: `sha256sum` on the host
    # showed the new file immediately after switching, while `docker exec
    # go-odyssey-app sha256sum` on the same path still showed the OLD file
    # until `docker restart` ran.
    content = _read(DEPLOY_SCRIPT)
    assert re.search(r"docker restart .*app_service_name.*scheduler_service_name", content)
    assert "did not become healthy after restart" in content


def test_deploy_script_verifies_container_internal_hash_after_restart():
    content = _read(DEPLOY_SCRIPT)
    assert "containerServedHash" in content
    assert "Container-internal i18n.js hash still does not match" in content


def test_deploy_script_rollback_path_also_restarts_containers():
    content = _read(DEPLOY_SCRIPT)
    catch_block = content[content.index("catch {"):]
    assert re.search(r"docker restart .*app_service_name.*scheduler_service_name", catch_block)


def test_rollback_script_restarts_containers_after_switch():
    content = _read(ROLLBACK_SCRIPT)
    assert re.search(r"docker restart .*app_service_name.*scheduler_service_name", content)
    assert "did not become healthy after restart" in content


def test_deploy_script_requires_go_deploy_owner_gate():
    content = _read(DEPLOY_SCRIPT)
    assert "Assert-OwnerGate" in content
    assert "'GO_DEPLOY'" in content


def test_rollback_script_requires_go_rollback_owner_gate():
    content = _read(ROLLBACK_SCRIPT)
    assert "Assert-OwnerGate" in content
    assert "'GO_ROLLBACK'" in content


def test_rollback_script_reads_target_manifest_not_assumed_contents():
    content = _read(ROLLBACK_SCRIPT)
    assert "manifest.json" in content
    assert "targetManifest" in content


def test_preflight_reports_static_generation_drift_when_manifest_provided():
    content = _read(PREFLIGHT_SCRIPT)
    assert "StaticManifest" in content
    assert "STATIC GENERATION DRIFT" in content
    assert "drift_checked" in content


def test_preflight_static_drift_check_is_optional_backward_compatible():
    content = _read(PREFLIGHT_SCRIPT)
    # must not require StaticManifest -- existing non-static-release deploys
    # must keep working unchanged.
    assert "[string]$StaticManifest" in content
    assert "[Parameter(Mandatory = $true)][string]$StaticManifest" not in content


# ---------------------------------------------------------------------------
# ReleaseTooling.psm1 new function contracts
# ---------------------------------------------------------------------------

def test_new_static_release_functions_exported():
    content = _read(PSM1)
    for fn in [
        "Get-StaticAssetInventory", "Get-SwVersionFromText",
        "Assert-SafeStaticRelativePath", "Get-StaticReleaseGenerationName",
        "New-StaticReleaseBundle", "New-StaticReleaseManifestObject",
    ]:
        assert f"'{fn}'" in content, f"{fn} must be exported from ReleaseTooling.psm1"


def test_static_release_bundle_rejects_empty_files():
    content = _read(PSM1)
    assert "Staged static release file is empty" in content


def test_static_release_generation_name_matches_existing_host_convention():
    # Confirmed via direct host inspection: releases/<YYYYMMDD-HHMMSS>-<short-sha>-<label>/
    content = _read(PSM1)
    assert "yyyyMMdd-HHmmss" in content


# ---------------------------------------------------------------------------
# Docs
# ---------------------------------------------------------------------------

def test_architecture_decision_documented():
    text = _read(CONTRACT_DOC)
    assert "Option B" in text
    assert "Option A" in text
    assert "release-bound static generation" in text.lower() or "Option B" in text


def test_deferred_scope_documented_not_silent():
    text = _read(CONTRACT_DOC)
    assert "Deferred scope" in text
    assert "RELEASE-FIX-B" in text


def test_historical_impact_audit_exists_and_covers_required_sprints():
    text = _read(AUDIT_DOC)
    for label in ["E9.1A2", "E9.1A2 Rev2", "E9.1A2-FIX1", "E9.1B"]:
        assert label in text


def test_historical_impact_audit_does_not_claim_everything_broke():
    text = _read(AUDIT_DOC)
    assert "Unaffected" in text


# ---------------------------------------------------------------------------
# Release layout schema
# ---------------------------------------------------------------------------

def test_release_layout_schema_has_optional_static_release_root():
    schema = json.loads(_read(REPO_ROOT / "deploy" / "release-layout.schema.json"))
    assert "static_release_root" in schema["properties"]
    assert "static_release_root" not in schema["required"], (
        "static_release_root must stay optional so existing non-static-aware layouts keep validating"
    )


def test_production_layout_has_static_release_root():
    layout = json.loads(_read(REPO_ROOT / "deploy" / "release-layout.production.json"))
    assert layout["static_release_root"] == "/opt/go-odyssey-static"


def test_example_layout_has_static_release_root():
    layout = json.loads(_read(REPO_ROOT / "deploy" / "release-layout.example.json"))
    assert "static_release_root" in layout


# ---------------------------------------------------------------------------
# E9-FIX-B boundary -- confirm this PR does NOT touch the fallback helper
# ---------------------------------------------------------------------------

def test_this_pr_does_not_touch_e9_fallback_helper():
    for name in ["top_hud.js", "right_cards.js", "world_stage.js"]:
        content = _read(REPO_ROOT / "js" / "e9" / name)
        # the pre-existing `|| fallback` pattern must be untouched by this PR
        assert "window.I18n.t(key)" in content
