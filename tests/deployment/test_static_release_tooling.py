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
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
INVENTORY_PATH = REPO_ROOT / "deploy" / "live-static-asset-inventory.json"
APP_PY = REPO_ROOT / "app.py"
DOCKERFILE = REPO_ROOT / "Dockerfile"
INDEX_HTML = REPO_ROOT / "index.html"
PSM1 = REPO_ROOT / "scripts" / "release" / "ReleaseTooling.psm1"
PACKAGE_SCRIPT = REPO_ROOT / "scripts" / "release" / "package-static-release.ps1"
DEPLOY_SCRIPT = REPO_ROOT / "scripts" / "release" / "deploy-static-release.ps1"
ROLLBACK_SCRIPT = REPO_ROOT / "scripts" / "release" / "rollback-static-release.ps1"
PREFLIGHT_SCRIPT = REPO_ROOT / "scripts" / "release" / "preflight-production.ps1"
CONTRACT_DOC = REPO_ROOT / "docs" / "deployment" / "canonical_static_release_contract.md"
AUDIT_DOC = REPO_ROOT / "docs" / "deployment" / "live_static_drift_impact_audit_20260712.md"
PRESENTATION_DISPATCHER_PATH = "js/game/presentation_dispatcher.js"
PRESENTATION_DISPATCHER_ROUTE = "@app.route('/js/game/presentation_dispatcher.js')"
PRESENTATION_DISPATCHER_COPY = (
    "COPY js/game/presentation_dispatcher.js ./js/game/presentation_dispatcher.js"
)
PRESENTATION_DISPATCHER_SCRIPT = "/js/game/presentation_dispatcher.js"
STATIC_PRE_B1_REQUIRED_COUNT = 8
STATIC_B1_REQUIRED_COUNT = 9

PRE_B1_REQUIRED_IN_GENERATION = frozenset(
    {
        "i18n.js", "sw.js", "index.html", "site-nav.js",
        "inventory.html",
        "js/e9/shell.js", "js/map_battle_v1_adapter.js",
        "js/game/lord_trial_controller.js",
    }
)


def _read(path):
    assert path.is_file(), f"expected file to exist: {path}"
    return path.read_text(encoding="utf-8")


def _load_inventory():
    return json.loads(_read(INVENTORY_PATH))


def _presentation_source_present(repo_root=REPO_ROOT):
    return (repo_root / PRESENTATION_DISPATCHER_PATH).is_file()


def _expected_required_in_generation(presentation_present):
    expected = set(PRE_B1_REQUIRED_IN_GENERATION)
    if presentation_present:
        expected.add(PRESENTATION_DISPATCHER_PATH)
    return frozenset(expected)


# B2-B7 each landed one or two additional js/game/*.js runtime modules on top
# of B1's single presentation_dispatcher.js addition. deploy/live-static-
# asset-inventory.json's required_in_generation.entries was correctly
# updated at every wave (verified: 16 real entries, byte-accurate); only
# this test's own current-state expected-set was never extended past B1.
# This is historical governance debt in the TEST, not the manifest --
# corrected here rather than weakened. The PRE_B1/B1-present dual-state
# constants and tests above are a historical snapshot of the B1 rollout
# mechanism itself and are deliberately left untouched.
POST_B1_REQUIRED_IN_GENERATION = frozenset(
    {
        "js/game/presentation_effects_b2.js",
        "js/game/review_transport.js",
        "js/game/game_session.js",
        "js/game/question_loader.js",
        "js/game/board_renderer.js",
        "js/game/mode_context.js",
        "js/game/game_bootstrap.js",
        # E10_ZONE_GENERIC_CINEMATIC_REPLAY_001 adds the zone-agnostic
        # cinematic replay model as a governed static subpath asset.
        "js/game/cinematic_replay.js",
    }
)
STATIC_CURRENT_REQUIRED_COUNT = STATIC_B1_REQUIRED_COUNT + len(POST_B1_REQUIRED_IN_GENERATION)


def _current_expected_required_in_generation(presentation_present):
    return frozenset(
        _expected_required_in_generation(presentation_present) | POST_B1_REQUIRED_IN_GENERATION
    )


def test_static_post_b1_expected_set_is_exact():
    assert len(_current_expected_required_in_generation(True)) == STATIC_CURRENT_REQUIRED_COUNT
    for path in POST_B1_REQUIRED_IN_GENERATION:
        assert path not in _expected_required_in_generation(True), (
            f"{path} is a post-B1 addition and must not be back-dated into the B1 baseline"
        )


def _assert_static_presentation_state(
    presentation_present,
    required_entries,
    eligible_entries,
    app_content,
    dockerfile,
    html,
    expected_override=None,
):
    expected = expected_override if expected_override is not None else _expected_required_in_generation(presentation_present)
    required = set(required_entries)
    eligible = set(eligible_entries)
    assert len(PRE_B1_REQUIRED_IN_GENERATION) == STATIC_PRE_B1_REQUIRED_COUNT
    assert len(required_entries) == len(expected)
    assert required == expected
    assert (PRESENTATION_DISPATCHER_PATH in eligible) is presentation_present
    assert (PRESENTATION_DISPATCHER_PATH in required) is presentation_present
    if presentation_present:
        assert PRESENTATION_DISPATCHER_ROUTE in app_content
    assert (PRESENTATION_DISPATCHER_COPY in dockerfile) is presentation_present
    assert (PRESENTATION_DISPATCHER_SCRIPT in html) is presentation_present


def test_static_dual_state_expected_sets_are_exact():
    assert len(PRE_B1_REQUIRED_IN_GENERATION) == STATIC_PRE_B1_REQUIRED_COUNT
    assert len(_expected_required_in_generation(False)) == STATIC_PRE_B1_REQUIRED_COUNT
    assert PRESENTATION_DISPATCHER_PATH not in _expected_required_in_generation(False)
    assert len(_expected_required_in_generation(True)) == STATIC_B1_REQUIRED_COUNT
    assert PRESENTATION_DISPATCHER_PATH in _expected_required_in_generation(True)


def test_static_dual_state_rejects_partial_b1_contract():
    baseline = PRE_B1_REQUIRED_IN_GENERATION
    empty_assets = ()
    with pytest.raises(AssertionError):
        _assert_static_presentation_state(
            True,
            baseline,
            empty_assets,
            "",
            "",
            "",
        )
    with pytest.raises(AssertionError):
        _assert_static_presentation_state(
            False,
            tuple(baseline | {PRESENTATION_DISPATCHER_PATH}),
            (PRESENTATION_DISPATCHER_PATH,),
            PRESENTATION_DISPATCHER_ROUTE,
            PRESENTATION_DISPATCHER_COPY,
            PRESENTATION_DISPATCHER_SCRIPT,
        )


def _ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def _ps_array(values):
    return "@(" + ", ".join(_ps_quote(value) for value in values) + ")"


def _run_powershell(tmp_path, body):
    script = tmp_path / "release_tooling_test.ps1"
    script.write_text(body, encoding="utf-8")
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True, text=True, timeout=120,
    )


def _run_route_fixture(tmp_path, inventory_status=302, inventory_location="/login"):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - stdlib handler contract
            if self.path.startswith("/inventory"):
                self.send_response(inventory_status)
                if inventory_location is not None:
                    self.send_header("Location", inventory_location)
                self.end_headers()
                if inventory_status == 200:
                    self.wfile.write(b"unexpected inventory body")
                return
            if self.path.startswith("/login"):
                body = b"login page body"
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            body = b"raw public bytes"
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        body = f"""
Import-Module {_ps_quote(PSM1)} -Force -DisableNameChecking
Test-PublicAuthenticatedRoute -Url {_ps_quote(f'http://127.0.0.1:{server.server_port}/inventory')} -Path 'inventory.html' | ConvertTo-Json -Compress
"""
        result = _run_powershell(tmp_path, body)
        assert result.returncode == 0, f"PowerShell route helper failed:\n{result.stdout}\n{result.stderr}"
        return json.loads(result.stdout.strip().splitlines()[-1])
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _bundle_inventory(entries):
    entries_ps = _ps_array(entries)
    return f"""
$inventory = [pscustomobject]@{{
    required_in_generation = [pscustomobject]@{{ entries = {entries_ps} }}
    eligible_files = [pscustomobject]@{{ entries = {entries_ps} }}
    forbidden_patterns = [pscustomobject]@{{ path_patterns = @() }}
    required_subtrees = [pscustomobject]@{{ entries = @() }}
}}
"""


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
    # app.py's frozenset is intentionally root-level. Explicitly routed
    # subpath assets are also eligible for the static release, but are not
    # part of that flat runtime allowlist.
    inventory_root_files = {path for path in inventory_files if "/" not in path and "\\" not in path}
    assert inventory_root_files == app_py_files, (
        f"deploy/live-static-asset-inventory.json root entries have drifted from app.py's "
        f"_LIVE_STATIC_ELIGIBLE_FILES.\nOnly in inventory: {inventory_files - app_py_files}\n"
        f"Only in app.py: {app_py_files - inventory_root_files}"
    )


def test_inventory_explicit_subpath_asset_has_a_live_static_route():
    inventory = _load_inventory()
    app_content = _read(APP_PY)
    _assert_static_presentation_state(
        _presentation_source_present(),
        inventory["required_in_generation"]["entries"],
        inventory["eligible_files"]["entries"],
        app_content,
        _read(DOCKERFILE),
        _read(INDEX_HTML),
        expected_override=_current_expected_required_in_generation(_presentation_source_present()),
    )
    for asset_path in ("js/map_battle_v1_adapter.js", "js/e9/shell.js"):
        assert asset_path in inventory["eligible_files"]["entries"]
        assert asset_path in inventory["required_in_generation"]["entries"]
    assert "@app.route('/js/map_battle_v1_adapter.js')" in app_content
    assert "@app.route('/js/e9/<path:subpath>')" in app_content


def test_inventory_required_in_generation_is_subset_of_eligible():
    inventory = _load_inventory()
    required = set(inventory["required_in_generation"]["entries"])
    eligible = set(inventory["eligible_files"]["entries"])
    assert required.issubset(eligible)


def test_inventory_required_in_generation_matches_confirmed_drift_scope():
    # i18n.js and sw.js were the original stale live-static files. index.html
    # is also governed because an older live-static entrypoint can mask the
    # exact image's application shell wiring. inventory.html is governed so
    # the E10 Backpack shell cannot fall back to the pre-hotfix image.
    inventory = _load_inventory()
    entries = inventory["required_in_generation"]["entries"]
    assert entries.count("inventory.html") == 1
    expected = _current_expected_required_in_generation(_presentation_source_present())
    assert set(entries) == expected
    assert len(entries) == len(expected)


def test_inventory_declares_complete_e10_runtime_dependency_boundary():
    inventory = _load_inventory()
    closure = inventory["runtime_dependency_closure"]
    assert closure["entrypoints"] == ["index.html"]
    assert {item["prefix"] for item in closure["subtrees"]} == {
        "js/e9/", "css/e9/", "components/adventure/"
    }
    eligible = set(inventory["eligible_files"]["entries"])
    for required_path in (
        "js/e9/world_stage.js",
        "js/e9/adapters/adventure_state.js",
        "css/e9/world_stage.css",
        "components/adventure/world_stage.html",
    ):
        assert required_path in eligible
        assert (REPO_ROOT / required_path).is_file()


def test_inventory_excludes_icons_prefix():
    # assets/ moved to required_subtrees under RELEASE-FIX-A2 -- see
    # docs/incidents/2026-07-12-full-site-asset-outage.md. icons/ remains
    # excluded: no current runtime reference resolves to it.
    inventory = _load_inventory()
    excluded = set(inventory["excluded_prefixes"]["entries"])
    assert "icons/" in excluded
    assert "assets/" not in excluded


def test_inventory_governs_assets_via_required_subtrees():
    inventory = _load_inventory()
    subtrees = inventory["required_subtrees"]["entries"]
    assets_subtree = next((s for s in subtrees if s["prefix"] == "assets/"), None)
    assert assets_subtree is not None, "assets/ must be declared in required_subtrees"
    # RELEASE-FIX-A3 superseded the 180-file reference-derived closure with
    # the complete verified historical image pack as the ownership boundary
    # for assets/ -- see docs/incidents/2026-07-12-full-site-asset-outage.md.
    assert assets_subtree["manifest"] == "deploy/canonical-image-pack-manifest.json"


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


def test_html_required_legacy_assets_have_image_and_static_contract_entries():
    html = _read(INDEX_HTML)
    dockerfile = _read(DOCKERFILE)
    inventory = _load_inventory()
    eligible = set(inventory["eligible_files"]["entries"])
    required = set(inventory["required_in_generation"]["entries"])

    _assert_static_presentation_state(
        _presentation_source_present(),
        inventory["required_in_generation"]["entries"],
        inventory["eligible_files"]["entries"],
        _read(APP_PY),
        dockerfile,
        html,
        expected_override=_current_expected_required_in_generation(_presentation_source_present()),
    )
    assert "/js/map_battle_v1_adapter.js" in html
    assert "/js/e9/shell.js" in html
    assert "/site-nav.js" in html
    assert "COPY js/map_battle_v1_adapter.js ./js/map_battle_v1_adapter.js" in dockerfile
    assert "site-nav.js" in dockerfile
    assert {
        "site-nav.js",
        "js/e9/shell.js",
        "js/map_battle_v1_adapter.js",
    } <= eligible
    assert {
        "site-nav.js",
        "js/e9/shell.js",
        "js/map_battle_v1_adapter.js",
    } <= required


def test_dockerfile_legacy_asset_sources_exist_and_are_narrow():
    dockerfile = _read(DOCKERFILE)
    assert re.search(r"COPY\s+js/map_battle_v1_adapter\.js\s+\./js/map_battle_v1_adapter\.js", dockerfile)
    presentation_copy = re.search(
        r"COPY\s+js/game/presentation_dispatcher\.js\s+\./js/game/presentation_dispatcher\.js",
        dockerfile,
    )
    assert (presentation_copy is not None) is _presentation_source_present()
    assert not re.search(r"COPY\s+\.\s+\.", dockerfile)
    assert (REPO_ROOT / "site-nav.js").is_file()
    assert (REPO_ROOT / "js" / "map_battle_v1_adapter.js").is_file()
    assert (REPO_ROOT / PRESENTATION_DISPATCHER_PATH).is_file() is _presentation_source_present()


def test_dockerfile_copies_shared_map_battle_runtime_modules():
    dockerfile = _read(DOCKERFILE)
    for module in ("map_battle_runtime.py", "map_battle_persistence.py"):
        assert re.search(rf"COPY\s+{re.escape(module)}\s+\./", dockerfile)
        assert (REPO_ROOT / module).is_file()


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
    # RELEASE-FIX-A2-STATIC-DEPLOY-FIX2: per-file "sha256sum <path>" checks
    # (one ssh session per file) were replaced with a single batched
    # `sha256sum --check --strict` verification -- see
    # tests/deployment/test_static_deploy_fix2.py for the full coverage.
    deploy_content = _read(DEPLOY_SCRIPT)
    assert "New-RemoteBatchShaVerificationScript" in deploy_content
    assert "Batch SHA-256 verification failed" in deploy_content
    psm1_content = _read(PSM1)
    assert "sha256sum --check --strict" in psm1_content


def test_deploy_script_uses_atomic_symlink_switch_pattern():
    content = _read(DEPLOY_SCRIPT)
    assert "ln -sfnT" in content
    assert "mv -Tf" in content
    # never a direct overwrite of "current" itself
    assert re.search(r"ln -sfnT \S+ current[^.]", content) is None or "current.next" in content


def test_deploy_script_verifies_public_https_bytes_not_just_filesystem():
    content = _read(DEPLOY_SCRIPT)
    assert "Invoke-WebRequest" in content
    assert "Resolve-StaticPublicRoute" in content
    assert '"$PublicBase/$($entry.path)"' not in content
    assert "Cache-Control" in content
    assert "Get-PublicFileSha256" in content
    assert "Public content hash mismatch" in content


def test_inventory_manifest_filename_uses_canonical_public_routes(tmp_path):
    body = f"""
Import-Module {_ps_quote(PSM1)} -Force -DisableNameChecking
[ordered]@{{
    generic = Resolve-StaticPublicRoute -RelativePath 'inventory.html'
    e10 = Resolve-StaticPublicRoute -RelativePath 'inventory.html' -E10Context
    javascript = Resolve-StaticPublicRoute -RelativePath 'site-nav.js'
}} | ConvertTo-Json -Compress
"""
    result = _run_powershell(tmp_path, body)
    assert result.returncode == 0, f"canonical route helper failed:\n{result.stdout}\n{result.stderr}"
    assert json.loads(result.stdout) == {
        "generic": "/inventory",
        "e10": "/inventory?e10=1",
        "javascript": "/site-nav.js",
    }


def test_inventory_verification_plan_is_authenticated_route_not_raw_bytes(tmp_path):
    body = f"""
Import-Module {_ps_quote(PSM1)} -Force -DisableNameChecking
[ordered]@{{
    inventory = Get-StaticPublicVerificationPlan -RelativePath 'inventory.html'
    javascript = Get-StaticPublicVerificationPlan -RelativePath 'i18n.js'
}} | ConvertTo-Json -Compress
"""
    result = _run_powershell(tmp_path, body)
    assert result.returncode == 0, f"verification plan helper failed:\n{result.stdout}\n{result.stderr}"
    payload = json.loads(result.stdout)
    assert payload["inventory"]["verification_mode"] == "AUTHENTICATED_ROUTE"
    assert payload["inventory"]["route"] == "/inventory"
    assert payload["inventory"]["expected_redirect_path"] == "/login"
    assert payload["javascript"]["verification_mode"] == "RAW_PUBLIC_BYTES"


def test_authenticated_inventory_redirect_is_verified_without_hashing_login_body(tmp_path):
    result = _run_route_fixture(tmp_path)
    assert result["status"] == "passed"
    assert result["verification_mode"] == "AUTHENTICATED_ROUTE"
    assert result["http_status"] == 302
    assert result["redirect_path"] == "/login"
    assert result["authenticated_route_verified"] is True
    assert result["login_body_hashed"] is False


def test_authenticated_inventory_unexpected_redirect_fails_closed(tmp_path):
    result = _run_route_fixture(tmp_path, inventory_status=302, inventory_location="/other")
    assert result["status"] == "unexpected_redirect"
    assert result["login_body_hashed"] is False


def test_authenticated_inventory_unexpected_unauthenticated_200_fails_closed(tmp_path):
    result = _run_route_fixture(tmp_path, inventory_status=200, inventory_location=None)
    assert result["status"] == "unexpected_auth_status"
    assert result["http_status"] == 200
    assert result["login_body_hashed"] is False


def test_raw_public_route_exact_bytes_pass_and_wrong_bytes_fail(tmp_path):
    expected = "726177207075626c6963206279746573"  # SHA is supplied below by PS.
    body = f"""
Import-Module {_ps_quote(PSM1)} -Force -DisableNameChecking
$good = (Get-FileHash -Algorithm SHA256 -LiteralPath {_ps_quote(str(tmp_path / 'raw.txt'))}).Hash.ToLowerInvariant()
$pass = Test-PublicRawStaticRoute -Url 'http://127.0.0.1:__PORT__/raw' -Path 'i18n.js' -ExpectedHash $good
$fail = Test-PublicRawStaticRoute -Url 'http://127.0.0.1:__PORT__/raw' -Path 'i18n.js' -ExpectedHash ('0' * 64)
[ordered]@{{ pass = $pass; fail = $fail }} | ConvertTo-Json -Compress
"""
    # This test uses the same deterministic fixture server as the auth tests;
    # replace the port after the server is allocated below.
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - stdlib handler contract
            payload = b"raw public bytes"
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    raw_file = tmp_path / "raw.txt"
    raw_file.write_bytes(b"raw public bytes")
    try:
        result = _run_powershell(
            tmp_path,
            body.replace("__PORT__", str(server.server_port)),
        )
        assert result.returncode == 0, f"raw route helper failed:\n{result.stdout}\n{result.stderr}"
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        assert payload["pass"]["status"] == "passed"
        assert payload["pass"]["sha256_match"] is True
        assert payload["fail"]["status"] == "sha_mismatch"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_static_verifiers_use_canonical_route_helper_for_inventory():
    deploy = _read(DEPLOY_SCRIPT)
    rollback = _read(ROLLBACK_SCRIPT)
    assert "Resolve-StaticPublicRoute -RelativePath" in deploy
    assert "Get-StaticPublicVerificationPlan" in deploy
    assert "Get-StaticPublicVerificationPlan" in rollback
    assert "Test-PublicAuthenticatedRoute" in deploy
    assert "Test-PublicAuthenticatedRoute" in rollback
    assert "MaximumRedirection 0" in deploy
    assert "MaximumRedirection 0" in rollback
    assert "container-internal inventory.html hash" in deploy
    assert "Mounted inventory.html hash" in rollback
    assert '"$publicBase/$($entry.path)"' not in rollback


def test_inventory_source_filename_is_not_an_application_public_route():
    app_content = _read(APP_PY)
    assert "@app.route('/inventory')" in app_content
    assert "@app.route('/inventory.html')" not in app_content


def test_timeout_reconciles_before_rollback_and_accepts_remote_completion():
    content = _read(DEPLOY_SCRIPT)
    assert "Get-StaticDeploymentReconciliation" in content
    assert "REMOTE_COMPLETED_SWITCHED" in content
    assert "original_local_failure" in content
    assert content.index("Get-StaticDeploymentReconciliation") < content.index("$rollbackRequired = $false")


def test_query_string_verification_is_diagnostic_only():
    content = _read(DEPLOY_SCRIPT)
    assert "Query-string" in content
    assert "diagnostic-only" in content
    assert "Get-SwVersionFromUrl -Url \"$publicBase/sw.js\"" in content


def test_index_shell_uses_narrow_runtime_provenance_endpoint():
    content = _read(DEPLOY_SCRIPT)
    assert 'healthz/static-release' in content
    assert 'index.html' in content
    assert 'PUBLIC_INDEX_PROVENANCE' in content
    assert 'publicEntries = @($manifest.files | Where-Object { $_.path -ne \'index.html\' })' in content
    app_content = _read(APP_PY)
    assert "@app.route('/healthz/static-release')" in app_content
    for field in ('generation', 'index_sha256', 'i18n_sha256', 'sw_sha256'):
        assert "'" + field + "'" in app_content
    assert "static_root_unavailable" in app_content


def test_public_verification_collection_has_explicit_arraylist_type():
    content = _read(DEPLOY_SCRIPT)
    assert 'New-Object System.Collections.ArrayList' in content
    assert '$phaseHistory = New-Object System.Collections.ArrayList' in content
    assert '[void]$phaseHistory.Add' in content
    assert '$results.ToArray()' in content
    assert 'Argument types do not match' in content


def test_deploy_script_verifies_sw_version_publicly_not_just_locally():
    content = _read(DEPLOY_SCRIPT)
    assert "Get-SwVersionFromUrl" in content
    assert "Public sw.js VERSION mismatch" in content


def test_static_deploy_has_env_gated_phase_timing_without_contract_change():
    content = _read(DEPLOY_SCRIPT)
    assert "GO_ODYSSEY_STATIC_DEPLOY_TIMING" in content
    assert "PUBLIC HASH VERIFICATION START" in content
    assert "PUBLIC HASH PROGRESS" in content
    assert "PUBLIC HASH VERIFICATION COMPLETE" in content
    assert "[Console]::Error.WriteLine" in content


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


def test_preflight_drift_is_judged_by_content_not_generation_id():
    # Live-discovered while verifying this Sprint's own fix: a later commit
    # that never touches i18n.js/sw.js legitimately produces a new
    # static_generation_id with byte-identical content -- that must NOT be
    # reported as drift. Only a per-file SHA-256 mismatch is real drift.
    content = _read(PREFLIGHT_SCRIPT)
    assert "static_generation_id" not in content or "notmatch" not in content, (
        "drift must not be judged by comparing the generation directory name/timestamp -- "
        "only by comparing served file content (SHA-256)"
    )


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
        "Get-SwAssetIdentityFromText", "Get-StaticReleaseAssetIdentity",
        "Set-StaticReleaseServiceWorkerIdentity", "Get-StaticRuntimeDependencyClosure",
        "Assert-SafeStaticRelativePath", "Get-StaticReleaseGenerationName",
        "New-StaticReleaseBundle", "New-StaticReleaseManifestObject",
    ]:
        assert f"'{fn}'" in content, f"{fn} must be exported from ReleaseTooling.psm1"


def test_package_script_binds_worker_identity_to_exact_source_sha():
    content = _read(PACKAGE_SCRIPT)
    assert "Get-StaticReleaseAssetIdentity -GitSha $ExpectedGitSha" in content
    assert "-ServiceWorkerAssetIdentity $serviceWorkerAssetIdentity" in content
    assert "Get-SwAssetIdentityFromText" in content
    assert "service_worker_asset_identity" in content


def test_static_release_bundle_rejects_empty_files():
    content = _read(PSM1)
    assert "Staged static release file is empty" in content


def test_static_release_generation_name_matches_existing_host_convention():
    # Confirmed via direct host inspection: releases/<YYYYMMDD-HHMMSS>-<short-sha>-<label>/
    content = _read(PSM1)
    assert "yyyyMMdd-HHmmss" in content


def _runtime_closure_fixture_inventory():
    return """
$inventory = [pscustomobject]@{
    required_in_generation = [pscustomobject]@{ entries = @('index.html') }
    eligible_files = [pscustomobject]@{ entries = @(
        'index.html', 'js/e9/world_stage.js', 'js/e9/adapters/adventure_state.js',
        'components/adventure/world_stage.html', 'css/e9/world_stage.css'
    ) }
    runtime_dependency_closure = [pscustomobject]@{
        entrypoints = @('index.html')
        subtrees = @(
            [pscustomobject]@{ prefix = 'js/e9/'; extensions = @('.js') },
            [pscustomobject]@{ prefix = 'css/e9/'; extensions = @('.css') },
            [pscustomobject]@{ prefix = 'components/adventure/'; extensions = @('.html') }
        )
    }
    forbidden_patterns = [pscustomobject]@{ path_patterns = @() }
    required_subtrees = [pscustomobject]@{ entries = @() }
}
"""


def test_runtime_dependency_closure_stages_transitive_files_and_manifest_hashes(tmp_path):
    source = tmp_path / "source"
    stage = tmp_path / "stage"
    (source / "js" / "e9" / "adapters").mkdir(parents=True)
    (source / "css" / "e9").mkdir(parents=True)
    (source / "components" / "adventure").mkdir(parents=True)
    (source / "index.html").write_text(
        '<script src="/js/e9/world_stage.js?v=release"></script>'
        '<link rel="stylesheet" href="/css/e9/world_stage.css">',
        encoding="utf-8",
    )
    (source / "js" / "e9" / "world_stage.js").write_text(
        "var state = '/js/e9/adapters/adventure_state.js';\n"
        "var view = '/components/adventure/world_stage.html';\n",
        encoding="utf-8",
    )
    (source / "js" / "e9" / "adapters" / "adventure_state.js").write_text(
        "window.AdventureState = {};\n", encoding="utf-8"
    )
    (source / "components" / "adventure" / "world_stage.html").write_text(
        "<div class='world-stage'></div>\n", encoding="utf-8"
    )
    (source / "css" / "e9" / "world_stage.css").write_text(
        ".world-stage { display: block; }\n", encoding="utf-8"
    )

    body = f"""
Import-Module {_ps_quote(PSM1)} -Force -DisableNameChecking
{_runtime_closure_fixture_inventory()}
$files = @(New-StaticReleaseBundle -SourceRoot {_ps_quote(source)} -StagePath {_ps_quote(stage)} -Inventory $inventory)
$manifest = New-StaticReleaseManifestObject -GitSha ('a' * 40) -GenerationId 'test-generation' -SwVersion 'test-sw' -Files $files -CreatedAtUtc '2026-08-07T00:00:00Z'
[ordered]@{{ files = $files; manifest_files = $manifest.files }} | ConvertTo-Json -Depth 8
"""
    result = _run_powershell(tmp_path, body)
    assert result.returncode == 0, f"runtime closure staging failed:\n{result.stdout}\n{result.stderr}"
    payload = json.loads(result.stdout)
    expected = {
        "index.html",
        "js/e9/world_stage.js",
        "js/e9/adapters/adventure_state.js",
        "components/adventure/world_stage.html",
        "css/e9/world_stage.css",
    }
    assert {entry["path"] for entry in payload["files"]} == expected
    assert {entry["path"] for entry in payload["manifest_files"]} == expected
    for entry in payload["manifest_files"]:
        actual = __import__("hashlib").sha256(
            (stage / entry["path"]).read_bytes()
        ).hexdigest()
        assert actual == entry["sha256"]
        assert (stage / entry["path"]).stat().st_size == entry["size"]


def test_runtime_dependency_closure_fails_closed_for_missing_transitive_file(tmp_path):
    source = tmp_path / "source"
    stage = tmp_path / "stage"
    source.mkdir()
    (source / "index.html").write_text(
        '<script src="/js/e9/world_stage.js"></script>', encoding="utf-8"
    )
    (source / "js").mkdir()
    (source / "js" / "e9").mkdir()
    (source / "js" / "e9" / "world_stage.js").write_text(
        "var missing = '/js/e9/adapters/adventure_state.js';\n", encoding="utf-8"
    )
    body = f"""
Import-Module {_ps_quote(PSM1)} -Force -DisableNameChecking
{_runtime_closure_fixture_inventory()}
try {{
    New-StaticReleaseBundle -SourceRoot {_ps_quote(source)} -StagePath {_ps_quote(stage)} -Inventory $inventory | Out-Null
    Write-Output 'UNEXPECTED_SUCCESS'
    exit 1
}} catch {{
    Write-Output $_.Exception.Message
    exit 0
}}
"""
    result = _run_powershell(tmp_path, body)
    assert result.returncode == 0, f"missing dependency test failed:\n{result.stdout}\n{result.stderr}"
    assert "UNEXPECTED_SUCCESS" not in result.stdout
    assert "missing from source checkout" in result.stdout


def test_release_service_worker_identity_is_deterministic_and_manifested(tmp_path):
    worker = tmp_path / "sw.js"
    worker.write_text("const ASSET_IDENTITY = 'source-test';\n", encoding="utf-8")
    body = f"""
Import-Module {_ps_quote(PSM1)} -Force -DisableNameChecking
$one = Get-StaticReleaseAssetIdentity -GitSha ('a' * 40)
$same = Get-StaticReleaseAssetIdentity -GitSha ('a' * 40)
$other = Get-StaticReleaseAssetIdentity -GitSha ('b' * 40)
Set-StaticReleaseServiceWorkerIdentity -Path {_ps_quote(worker)} -AssetIdentity $one | Out-Null
$parsed = Get-SwAssetIdentityFromText -SwText (Get-Content -Raw -Encoding UTF8 {_ps_quote(worker)})
[ordered]@{{ one = $one; same = $same; other = $other; parsed = $parsed }} | ConvertTo-Json -Compress
"""
    result = _run_powershell(tmp_path, body)
    assert result.returncode == 0, f"identity test failed:\n{result.stdout}\n{result.stderr}"
    payload = json.loads(result.stdout)
    assert payload["one"] == payload["same"] == payload["parsed"]
    assert payload["one"] != payload["other"]
    assert payload["one"].startswith("release-")


def test_nested_and_root_flat_files_copy_into_manifest_and_archive(tmp_path):
    source = tmp_path / "source"
    (source / "js").mkdir(parents=True)
    (source / "root.txt").write_text("root-file\n", encoding="utf-8")
    (source / "js" / "nested.js").write_text("nested-file\n", encoding="utf-8")
    stage = tmp_path / "stage"
    archive = tmp_path / "static.tar"
    entries = ["root.txt", "js/nested.js"]

    body = f"""
Import-Module {_ps_quote(PSM1)} -Force -DisableNameChecking
{_bundle_inventory(entries)}
$files = @(New-StaticReleaseBundle -SourceRoot {_ps_quote(source)} -StagePath {_ps_quote(stage)} -Inventory $inventory)
$tar = Resolve-GnuTarExecutable
New-DeterministicStaticArchive -BundlePath {_ps_quote(stage)} -RelativePaths @($files | ForEach-Object {{ $_.path }}) -ArchivePath {_ps_quote(archive)} -GnuTarExecutablePath $tar.path -TimeoutSeconds 120 | Out-Null
Test-StaticArchiveEntrySafety -ArchivePath {_ps_quote(archive)} -GnuTarExecutablePath $tar.path -TimeoutSeconds 120
$manifest = New-StaticReleaseManifestObject -GitSha ('a' * 40) -GenerationId 'test-generation' -SwVersion 'test-sw' -Files $files -CreatedAtUtc '2026-08-03T00:00:00Z' -ArchiveFileName 'static.tar' -ArchiveSha256 'b' -ArchiveSize 1 -ArchiveEntryCount $files.Count -GnuTarExecutablePath $tar.path -GnuTarVersion 'test'
[ordered]@{{ files = $files; manifest_files = $manifest.files; archive = {_ps_quote(archive)} }} | ConvertTo-Json -Depth 8
"""
    result = _run_powershell(tmp_path, body)
    assert result.returncode == 0, f"nested static bundle failed:\n{result.stdout}\n{result.stderr}"
    result_json = json.loads(result.stdout)
    expected_paths = set(entries)
    assert {entry["path"] for entry in result_json["files"]} == expected_paths
    assert {entry["path"] for entry in result_json["manifest_files"]} == expected_paths
    assert (stage / "root.txt").is_file()
    assert (stage / "js" / "nested.js").is_file()

    archive_list = subprocess.run(
        ["tar.exe", "-tf", archive.name],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    ).stdout.splitlines()
    assert set(archive_list) == expected_paths


def _assert_bundle_rejected(tmp_path, entries, source_files=(), source_directories=()):
    source = tmp_path / "source"
    for relative_path in source_files:
        path = source / Path(relative_path.replace("\\", "/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture\n", encoding="utf-8")
    for relative_path in source_directories:
        (source / Path(relative_path.replace("\\", "/"))).mkdir(parents=True, exist_ok=True)
    stage = tmp_path / "stage"
    body = f"""
Import-Module {_ps_quote(PSM1)} -Force -DisableNameChecking
{_bundle_inventory(entries)}
try {{
    @(New-StaticReleaseBundle -SourceRoot {_ps_quote(source)} -StagePath {_ps_quote(stage)} -Inventory $inventory) | Out-Null
    Write-Output 'UNEXPECTED_SUCCESS'
    exit 1
}} catch {{
    Write-Output $_.Exception.Message
    exit 0
}}
"""
    result = _run_powershell(tmp_path, body)
    assert result.returncode == 0, f"expected bundle rejection:\n{result.stdout}\n{result.stderr}"
    assert "UNEXPECTED_SUCCESS" not in result.stdout
    return result.stdout


@pytest.mark.parametrize(
    ("entries", "source_files", "expected_message"),
    [
        (["js/missing.js"], [], "source file missing"),
        (["../escape.js"], [], "Path traversal"),
        (["js/../../escape.js"], [], "Path traversal"),
        (["C:/escape.js"], [], "Absolute drive paths"),
        (["/escape.js"], [], "Absolute paths"),
        (["js/foo.js", "js\\foo.js"], ["js/foo.js"], "Duplicate normalized"),
        (["js/Foo.js", "js/foo.js"], ["js/foo.js"], "Duplicate normalized"),
    ],
)
def test_nested_static_path_safety_and_duplicate_contract(
    tmp_path, entries, source_files, expected_message
):
    message = _assert_bundle_rejected(tmp_path, entries, source_files=source_files)
    assert expected_message.lower() in message.lower()


def test_nested_directory_entry_is_rejected_as_non_file(tmp_path):
    message = _assert_bundle_rejected(
        tmp_path,
        ["js/not-a-file"],
        source_directories=["js/not-a-file"],
    )
    assert "directory" in message.lower()


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
# E9-FIX-B boundary -- this Sprint (RELEASE-FIX-A) does not fix the known
# `t(key, fallback)` fallback-helper defect; that is RELEASE-FIX-B's job
# (see docs/planning/release_fix_b_e9_i18n_fallback.md, now merged) --
# infrastructure-only PRs must not silently absorb an unrelated code-level
# fix, and once RELEASE-FIX-B lands, the defective `|| fallback` pattern
# should be gone for good, not reintroduced by a future infra-only PR.
# ---------------------------------------------------------------------------

def test_e9_fallback_helper_defect_is_fixed_not_reintroduced():
    for name in ["top_hud.js", "right_cards.js", "world_stage.js"]:
        content = _read(REPO_ROOT / "js" / "e9" / name)
        assert "val || fallback" not in content, (
            f"{name} must not reintroduce the defective '|| fallback' pattern "
            "fixed by RELEASE-FIX-B"
        )
        assert "window.E9.I18nFallback.t(key, fallback)" in content
