"""Contracts for separating release gate/tooling source from product source."""

from __future__ import annotations

import json
import os
import pathlib
import subprocess

import pytest


ROOT = pathlib.Path(__file__).resolve().parents[2]
MODULE = ROOT / "scripts" / "release" / "ReleaseTooling.psm1"
BUILD_RELEASE = ROOT / "scripts" / "release" / "build-release-image.ps1"
BUILD_PRODUCTION = ROOT / "scripts" / "build-production-image.ps1"
PACKAGE_STATIC = ROOT / "scripts" / "release" / "package-static-release.ps1"
# Refreshed each time canonical master's tip advances so this dry-run test
# exercises the separation mechanism against a real, current, zero-diff
# product baseline instead of drifting further behind. Was pinned to a
# pre-Architecture-V1 commit (45eef15e..., 2026-08-15) and never advanced
# through B1-B7 or the backend V1A2/V1A3 waves, so the mechanism correctly
# (by design) fail-closed with UNAPPROVED_PRODUCT_DIFF_DETECTED against
# every product file those waves touched -- not a bug in the assertion.
# E10_REPLAY_STORY_CROSS_SURFACE_V237_ISOLATED_RELEASE_001: Owner-approved
# Product baseline, advanced for the isolated cross-surface hotfix branch
# (built from the exact deployed Product source 8d1c1f893, not current
# master -- see RELEASE_SCOPE_DIFF). Same two-commit-role pattern the prior
# E10_REPLAY_STORY_BUTTON_HOTFIX_001 baseline used, and which it replaces:
#   5126dd3bb = CONTENT_PRODUCING_COMMIT and the Product source this release
#               builds. Records runtime provenance for the three governed
#               files the hotfix changed (index.html, sw.js,
#               js/e9/world_stage.js). It stays immutable.
#   240801f32 = the cross-surface fix: one shared availability authority
#               replaces right_cards.js's hardcoded 'k26_30' allowlist, and
#               the E9 shell publishes its authoritative bootstrap snapshot
#               to the cinematic model. Bumps sw.js VERSION to the v237
#               family and both changed modules' cache tags. The provenance
#               entries for index.html and sw.js point at it. Immutable.
#   95cb44570 = 002A's final predicate: Replay Story requires an
#               authoritative record, not locked, cleared, and canonical
#               replayable segments, failing closed on every other path.
#               The provenance entry for js/e9/world_stage.js points at it.
#               Immutable.
#   7e744efde = prior APPROVED_PRODUCT_BASELINE (E10_REPLAY_STORY_BUTTON_
#               HOTFIX_001), inherited unchanged and superseded here only
#               because this hotfix's own product bytes postdate it.
# The commit that advances this constant to 5126dd3bb touches only this
# gate-scope file, so it is self-terminating: no tracked product file
# changes after that SHA, which is what lets the Gate checkout validate it.
PRODUCT_SHA = "5126dd3bbf2a93228c81f1aefd66de3a17c77426"
PRESENTATION_DISPATCHER_PATH = "js/game/presentation_dispatcher.js"
PRE_B1_PROVENANCE_COUNT = 79
B1_PRESENT_PROVENANCE_COUNT = 80


def ps_quote(value: pathlib.Path | str) -> str:
    return str(value).replace("'", "''")


def run_powershell(script: str, *, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    preamble = (
        "$OutputEncoding = [Console]::OutputEncoding = "
        "New-Object System.Text.UTF8Encoding($false);\n"
    )
    return subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            preamble + script,
        ],
        cwd=ROOT,
        env={**os.environ, "SECRET_KEY": "source-separation-test-only"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
        check=False,
    )


def parse_last_json(stdout: str) -> dict:
    text = stdout.strip()
    start = text.find("{")
    assert start >= 0, stdout
    payload, _ = json.JSONDecoder().raw_decode(text[start:])
    return payload


def git(cwd: pathlib.Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return result.stdout.strip()


def _presentation_source_present(repo_root=ROOT):
    return (repo_root / PRESENTATION_DISPATCHER_PATH).is_file()


def _expected_provenance_contract(presentation_present):
    return (
        B1_PRESENT_PROVENANCE_COUNT
        if presentation_present
        else PRE_B1_PROVENANCE_COUNT,
        presentation_present,
    )


def _assert_provenance_contract(governed_paths, presentation_present, expected_count_override=None):
    expected_count, presentation_required = _expected_provenance_contract(
        presentation_present
    )
    if expected_count_override is not None:
        expected_count = expected_count_override
    assert len(governed_paths) == expected_count
    assert "js/game/lord_trial_controller.js" in governed_paths
    assert (PRESENTATION_DISPATCHER_PATH in governed_paths) is presentation_required


# B2-B7 each landed one or two additional js/game/*.js runtime modules on top
# of B1's single presentation_dispatcher.js addition. deploy/runtime-source-
# provenance.json was correctly updated at every wave (verified: 87 real
# entries, byte-accurate); only this test's own current-state expected count
# was never extended past B1. Historical governance debt in the TEST, not
# the manifest -- corrected here rather than weakened. The PRE_B1/B1-present
# dual-state constants and tests above are a historical snapshot of the B1
# rollout mechanism itself and are deliberately left untouched.
# E10_ZONE_GENERIC_CINEMATIC_REPLAY_001 adds js/game/cinematic_replay.js as
# the eighth post-B1 governed runtime module.
POST_B1_PROVENANCE_ADDITIONS = 8
CURRENT_PROVENANCE_COUNT = B1_PRESENT_PROVENANCE_COUNT + POST_B1_PROVENANCE_ADDITIONS


def test_provenance_dual_state_branches_are_exact():
    assert _expected_provenance_contract(False) == (PRE_B1_PROVENANCE_COUNT, False)
    assert _expected_provenance_contract(True) == (B1_PRESENT_PROVENANCE_COUNT, True)


def test_provenance_dual_state_rejects_partial_b1_contract():
    with pytest.raises(AssertionError):
        _assert_provenance_contract(
            {"js/game/lord_trial_controller.js"},
            True,
        )
    with pytest.raises(AssertionError):
        _assert_provenance_contract(
            {"js/game/lord_trial_controller.js", PRESENTATION_DISPATCHER_PATH},
            False,
        )


def create_source_pair(tmp_path: pathlib.Path) -> tuple[pathlib.Path, str, str]:
    repo = tmp_path / "source-pair"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Source Separation Test")
    git(repo, "config", "user.email", "source-separation@example.invalid")
    (repo / "index.html").write_text("product-v1\n", encoding="utf-8")
    git(repo, "add", "index.html")
    git(repo, "commit", "-q", "-m", "synthetic product source")
    product_sha = git(repo, "rev-parse", "HEAD")
    return repo, product_sha, product_sha


def commit_gate_change(repo: pathlib.Path, relative_path: str, content: str) -> str:
    path = repo / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    git(repo, "add", relative_path)
    git(repo, "commit", "-q", "-m", f"gate change {relative_path}")
    return git(repo, "rev-parse", "HEAD")


def invoke_separation(repo: pathlib.Path, gate_sha: str, product_sha: str) -> dict:
    script = f"""
$ErrorActionPreference = 'Stop'
Import-Module '{ps_quote(MODULE)}' -Force -DisableNameChecking
try {{
    $plan = Assert-ReleaseSourceSeparation -GateSourceSha '{gate_sha}' -ProductSourceSha '{product_sha}' -GateWorkingDirectory '{ps_quote(repo)}'
    [ordered]@{{ok=$true;plan=$plan}} | ConvertTo-Json -Depth 8 -Compress
}}
catch {{
    [ordered]@{{ok=$false;message=$_.Exception.Message}} | ConvertTo-Json -Compress
}}
"""
    result = run_powershell(script)
    assert result.returncode == 0, result.stdout + result.stderr
    return parse_last_json(result.stdout)


def test_runtime_byte_change_fails_closed_before_build_step(tmp_path):
    repo, product_sha, _ = create_source_pair(tmp_path)
    (repo / "index.html").write_text("product-v1-runtime-byte-change\n", encoding="utf-8")
    gate_sha = commit_gate_change(repo, "index.html", "product-v1-runtime-byte-change\n")
    script = f"""
$ErrorActionPreference = 'Stop'
Import-Module '{ps_quote(MODULE)}' -Force -DisableNameChecking
$buildStarted = $false
try {{
    Assert-ReleaseSourceSeparation -GateSourceSha '{gate_sha}' -ProductSourceSha '{product_sha}' -GateWorkingDirectory '{ps_quote(repo)}' | Out-Null
    $buildStarted = $true
    [ordered]@{{failed_closed=$false;build_not_started=$false;message=''}} | ConvertTo-Json -Compress
}}
catch {{
    [ordered]@{{failed_closed=$true;build_not_started=(-not $buildStarted);message=$_.Exception.Message}} | ConvertTo-Json -Compress
}}
"""
    result = run_powershell(script)
    assert result.returncode == 0, result.stdout + result.stderr
    payload = parse_last_json(result.stdout)
    assert payload["failed_closed"] is True
    assert payload["build_not_started"] is True
    assert "UNAPPROVED_PRODUCT_DIFF_DETECTED" in payload["message"]
    assert "index.html" in payload["message"]


def test_test_only_delta_passes_with_zero_product_runtime_diff(tmp_path):
    repo, product_sha, _ = create_source_pair(tmp_path)
    (repo / "tests" / "deployment").mkdir(parents=True)
    gate_sha = commit_gate_change(repo, "tests/deployment/test_gate_fixture.py", "def test_gate_fixture():\n    assert True\n")
    payload = invoke_separation(repo, gate_sha, product_sha)
    assert payload["ok"] is True
    plan = payload["plan"]
    assert plan["product_source_sha"] == product_sha
    assert plan["gate_source_sha"] == gate_sha
    assert plan["product_runtime_diff_count"] == 0
    assert plan["unapproved_product_paths"] == []
    assert plan["changed_paths"] == ["tests/deployment/test_gate_fixture.py"]


def test_mixed_release_tooling_and_deployment_test_delta_passes(tmp_path):
    repo, product_sha, _ = create_source_pair(tmp_path)
    commit_gate_change(repo, "scripts/release/gate-helper.ps1", "'gate-helper'\n")
    gate_sha = commit_gate_change(repo, "tests/deployment/test_gate_fixture.py", "def test_gate_fixture():\n    assert True\n")
    payload = invoke_separation(repo, gate_sha, product_sha)
    assert payload["ok"] is True
    assert payload["plan"]["product_runtime_diff_count"] == 0
    assert set(payload["plan"]["changed_paths"]) == {
        "scripts/release/gate-helper.ps1",
        "tests/deployment/test_gate_fixture.py",
    }


def test_mixed_runtime_and_tooling_delta_fails_closed(tmp_path):
    repo, product_sha, _ = create_source_pair(tmp_path)
    commit_gate_change(repo, "tests/deployment/test_gate_fixture.py", "def test_gate_fixture():\n    assert True\n")
    gate_sha = commit_gate_change(repo, "srs.js", "runtime-byte-change\n")
    payload = invoke_separation(repo, gate_sha, product_sha)
    assert payload["ok"] is False
    assert "UNAPPROVED_PRODUCT_DIFF_DETECTED" in payload["message"]
    assert "srs.js" in payload["message"]


def test_product_must_be_ancestor_of_gate(tmp_path):
    repo, product_sha, _ = create_source_pair(tmp_path)
    other_sha = commit_gate_change(repo, "tests/deployment/test_gate_fixture.py", "def test_gate_fixture():\n    assert True\n")
    payload = invoke_separation(repo, product_sha, other_sha)
    assert payload["ok"] is False
    assert "GATE_PRODUCT_ANCESTRY_REQUIRED" in payload["message"]


def test_release_entrypoint_exposes_separate_gate_and_product_identity_contracts():
    content = BUILD_RELEASE.read_text(encoding="utf-8")
    assert "GateSourceSha" in content
    assert "ProductSourceSha" in content
    assert "Assert-ReleaseSourceSeparation" in content
    assert "GO_ODYSSEY_RELEASE_GATE_SOURCE_SHA" in content
    assert "GO_ODYSSEY_RELEASE_PRODUCT_SOURCE_SHA" in content
    assert "build_context = 'PRODUCT_WORKTREE'" in content
    assert "test_source = 'GATE_WORKTREE'" in content
    assert "oci_revision_would_be = $productSha" in content
    assert "static_source_would_be = $productSha" in content
    assert "'-ExpectedHeadState', 'branch'" in content
    assert "'-ProductSourceRoot', $productWorktree" in content
    assert "'-ExpectedProductGitSha', $productSha" in content


def test_child_build_uses_product_root_for_runtime_inputs_and_docker_context():
    content = BUILD_PRODUCTION.read_text(encoding="utf-8")
    assert "[string]$ProductSourceRoot" in content
    assert "[string]$ExpectedProductGitSha" in content
    assert "Assert-DetachedWorktreeIdentity -Path $bootstrapProductRoot" in content
    assert "$validatedProductRoot = $validatedWorktreeRoot" in content
    assert "$dockerBuildContext = Assert-DetachedWorktreeIdentity" in content
    assert "-Path $validatedProductRoot" in content
    assert "gate_source_sha   = $ExpectedExactGitSha" in content
    assert "product_source_sha = $GitSha" in content


def test_static_packaging_binds_bundle_and_inventory_to_product_source():
    content = PACKAGE_STATIC.read_text(encoding="utf-8")
    assert "GateSourceSha" in content
    assert "ProductSourceSha" in content
    assert "Assert-ReleaseSourceSeparation" in content
    assert "Get-StaticAssetInventory -Path (Join-Path $worktree" in content
    assert "New-StaticReleaseBundle" in content
    assert "-SourceRoot $worktree" in content
    assert "-GateSourceSha $gateSha" in content
    assert "-ProductSourceSha $productSha" in content


def test_static_manifest_supports_distinct_gate_and_product_identities():
    content = (ROOT / "scripts" / "release" / "ReleaseTooling.psm1").read_text(
        encoding="utf-8"
    )
    assert "[string]$GateSourceSha" in content
    assert "[string]$ProductSourceSha" in content
    assert "$manifest.gate_source_sha = $GateSourceSha" in content
    assert "$manifest.product_source_sha = $ProductSourceSha" in content


def test_provenance_count_recovery_and_controller_membership_remain_intact():
    recovery_test = (ROOT / "tests" / "deployment" / "test_shadow_storage_packaging.py").read_text(
        encoding="utf-8"
    )
    assert "js/game/lord_trial_controller.js" in recovery_test
    assert "governed_paths" in recovery_test
    assert "manifest[\"runtime_dependency_provenance\"][\"files_covered\"] == len(" in recovery_test
    provenance = json.loads(
        (ROOT / "deploy" / "runtime-source-provenance.json").read_text(encoding="utf-8")
    )
    governed_paths = {entry["path"] for entry in provenance["files"]}
    _assert_provenance_contract(
        governed_paths,
        _presentation_source_present(),
        expected_count_override=CURRENT_PROVENANCE_COUNT,
    )


def test_canonical_source_separation_dry_run_uses_product_identity_without_build():
    gate_sha = git(ROOT, "rev-parse", "HEAD")
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(BUILD_RELEASE),
            "-GateSourceSha",
            gate_sha,
            "-ProductSourceSha",
            PRODUCT_SHA,
            "-DryRun",
        ],
        cwd=ROOT,
        env={**os.environ, "SECRET_KEY": "source-separation-test-only"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=90,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = parse_last_json(result.stdout)
    assert payload["source_separation_check"] == "PASS"
    assert payload["gate_source_sha"] == gate_sha
    assert payload["product_source_sha"] == PRODUCT_SHA
    assert payload["product_worktree_head"] == PRODUCT_SHA
    assert payload["product_worktree_clean"] is True
    assert payload["product_runtime_diff_from_product"] == 0
    assert payload["build_context"] == "PRODUCT_WORKTREE"
    assert payload["test_source"] == "GATE_WORKTREE"
    assert payload["oci_revision_would_be"] == PRODUCT_SHA
    assert payload["static_source_would_be"] == PRODUCT_SHA
    assert payload["build_not_executed"] is True
    assert "docker buildx" not in result.stdout.lower()
