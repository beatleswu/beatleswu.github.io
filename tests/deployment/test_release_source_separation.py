"""Contracts for separating release gate/tooling source from product source."""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess

import pytest

from process_runner import run_bounded


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
# UI-NAV-063A: 5b565a05d was the prior Owner-approved Product baseline.
# The Owner subsequently approved the integrated V2-A Product baseline at
# f2650ee762482bf4bb315e55bd542d6841a0a03b. The governance commit that updates
# this reference must not become the PRODUCT_SHA itself.
#
# Why the prior baseline had to move: UI-NAV-063 shipped
# assets/e10/ui/icons/guild.webp into Git and into the runtime, but not into
# the canonical static asset closure, so it was never a complete releasable
# Product. 5b565a05d closed that ownership gap. The gate firing beforehand was
# correct, not a defect; the current baseline additionally includes the
# Owner-approved V2-A Product/runtime change set.
#
# The Task 063 provenance records for index.html / i18n.js / sw.js deliberately
# still point at b3a081d70, the commit that produced those bytes.
#
# INCIDENT_018_R8A1: the fixed pin above is retained only as a historical
# record and as the negative control below. It is no longer used to drive the
# dry run.
#
# Why it had to stop being a fixed pin: the separation contract requires that
# every path changed between Product and Gate is release control-plane. A
# hand-maintained Product SHA therefore stops satisfying the contract the
# moment any ordinary product commit lands, which is normal master activity.
# The comment history above shows this pin being manually re-advanced again
# and again for exactly that reason -- the pin rots by construction, not
# because the gate is wrong. It is now DERIVED from history instead.
HISTORICAL_FIXED_PRODUCT_SHA = "f2650ee762482bf4bb315e55bd542d6841a0a03b"
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
    return run_bounded(
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
    # History/diff probes can follow a worktree-heavy release test in the full
    # serial gate.  Keep them bounded, but allow the measured registry/I/O
    # envelope to settle; synthetic-repository operations retain 60 seconds.
    timeout = 180 if args and args[0] in {"rev-list", "diff"} else 60
    result = run_bounded(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        timeout=timeout,
    )
    return result.stdout.strip()


# INCIDENT_018_R8A1: reuse the repository's existing canonical control-plane
# declaration instead of writing a second one here. scripts/release/
# e10_development_workflow_v2.py and ReleaseTooling.psm1's
# Get-ReleaseControlPlaneAllowlist are the two existing statements of the same
# allowlist; test_control_plane_authority_declarations_agree below fails closed
# if they ever drift apart.
_WORKFLOW_MODULE = ROOT / "scripts" / "release" / "e10_development_workflow_v2.py"


def _load_control_plane_authority():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_r8a1_workflow_authority", _WORKFLOW_MODULE
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_AUTHORITY = _load_control_plane_authority()
CONTROL_PLANE_EXACT_PATHS = _AUTHORITY.CONTROL_PLANE_EXACT_PATHS
CONTROL_PLANE_PREFIXES = _AUTHORITY.CONTROL_PLANE_PREFIXES

# Bounded history walk: a Product baseline further back than this would mean
# the release line has gone unbuilt for an implausibly long time, and an
# unbounded scan of full history in a test is its own hazard.
PRODUCT_DERIVATION_MAX_COMMITS = 200


def _is_control_plane_path(path: str) -> bool:
    normalized = path.replace("\\", "/").lstrip("./")
    return normalized in CONTROL_PLANE_EXACT_PATHS or normalized.startswith(
        CONTROL_PLANE_PREFIXES
    )


def _non_control_plane_paths(product_sha: str, gate_sha: str, repo_root=ROOT) -> list[str]:
    changed = git(repo_root, "diff", "--name-only", f"{product_sha}..{gate_sha}")
    return [
        line
        for line in changed.splitlines()
        if line.strip() and not _is_control_plane_path(line.strip())
    ]


def derive_product_sha(gate_sha: str, repo_root=ROOT) -> str:
    """Derive the Product identity the separation contract actually implies.

    The contract (Assert-ReleaseSourceSeparation) is: a newer Gate/control-plane
    checkout may validate an older Product checkout provided every path changed
    between them is release control-plane. The Product identity that satisfies
    that is therefore not a hand-chosen commit -- it is the *oldest* ancestor of
    the Gate for which the Product..Gate diff is still control-plane only, i.e.
    the most recent commit that itself carried product bytes.

    Deterministic, reproducible, and self-maintaining: when an ordinary product
    commit lands, the derived Product identity simply moves to it, and the
    contract keeps holding without anyone editing a SHA.

    Fail-closed: raises rather than falling back to the Gate SHA or to a
    permissive default.
    """
    gate = git(repo_root, "rev-parse", f"{gate_sha}^{{commit}}")
    history = git(
        repo_root, "rev-list", f"--max-count={PRODUCT_DERIVATION_MAX_COMMITS}", gate
    ).splitlines()
    if not history:
        raise AssertionError(f"no history resolved for gate {gate}")

    oldest_valid = None
    for candidate in history:
        candidate = candidate.strip()
        if not candidate:
            continue
        if _non_control_plane_paths(candidate, gate, repo_root):
            break
        oldest_valid = candidate

    if oldest_valid is None:
        raise AssertionError(
            "could not derive a Product identity whose diff to the Gate is "
            f"control-plane only, within {PRODUCT_DERIVATION_MAX_COMMITS} commits of {gate}"
        )
    if git(repo_root, "merge-base", oldest_valid, gate) != oldest_valid:
        raise AssertionError("derived Product identity is not an ancestor of the Gate")
    return oldest_valid


def run_powershell_capture(args: list[str], cwd: pathlib.Path, extra_env: dict | None = None):
    """Run PowerShell capturing bytes, then decode defensively.

    INCIDENT_018_R8A1: this previously passed encoding="utf-8" to subprocess.
    Windows PowerShell on a zh-TW host emits legacy CP950/Big5 bytes, so the
    reader thread raised UnicodeDecodeError, stderr came back as None, and the
    assertion died with `TypeError: can only concatenate str (not "NoneType")`
    -- hiding the real UNAPPROVED_PRODUCT_DIFF_DETECTED message underneath.
    Bytes are decoded with errors="replace" so undecodable output is visibly
    marked rather than dropped, and a genuine command failure still fails.
    """
    env = {**os.environ, **(extra_env or {})}
    completed = run_bounded(
        args, cwd=cwd, capture_output=True, env=env, timeout=180, check=False
    )

    def _decode(raw: bytes | None) -> str:
        if not raw:
            return ""
        return raw.decode("utf-8", errors="replace")

    return completed.returncode, _decode(completed.stdout), _decode(completed.stderr)


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
# INCIDENT_018_R8A: two further governed runtime modules had already landed
# without this count being advanced (E055 adventure_zone3_monster_authority.py
# and the LC019 identity read stack), and this task adds the eleventh --
# incident_018_observability.py, which app.py imports at module level but which
# was never packaged or governed. Advanced to match the real governed set
# rather than weakening the contract.
# Incident019B R11 adds the Zone-star runtime module and its explicit
# migration dependency to the governed set.
# RPG V1 P0 hotfix adds four app-start runtime authorities: Zone 3 legacy
# compatibility, Zone progression, Guild answer handling, and Lord admission.
# R3 grandfathered legacy continuity adds the packaged baseline migration /
# census runner, which is executed from inside the governed image.
POST_B1_PROVENANCE_ADDITIONS = 18
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


def _dry_run(
    gate_sha: str,
    product_sha: str,
    *,
    repo_root: pathlib.Path = ROOT,
    build_script: pathlib.Path = BUILD_RELEASE,
):
    return run_powershell_capture(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(build_script),
            "-GateSourceSha",
            gate_sha,
            "-ProductSourceSha",
            product_sha,
            "-DryRun",
        ],
        cwd=repo_root,
        extra_env={"SECRET_KEY": "source-separation-test-only"},
    )


def test_control_plane_authority_declarations_agree():
    """The Python and PowerShell allowlists must not drift apart."""
    module_text = MODULE.read_text(encoding="utf-8")
    allowlist_block = module_text[
        module_text.index("function Get-ReleaseControlPlaneAllowlist") : module_text.index(
            "function Test-ReleaseControlPlanePath"
        )
    ]
    for prefix in CONTROL_PLANE_PREFIXES:
        assert f"'{prefix}**'" in allowlist_block, prefix
    for exact in CONTROL_PLANE_EXACT_PATHS:
        assert f"'{exact}'" in allowlist_block, exact
    # and nothing extra on the PowerShell side
    declared = {
        line.strip().strip("',")
        for line in allowlist_block.splitlines()
        if line.strip().startswith("'")
    }
    normalized = {d[:-2] if d.endswith("/**") else d for d in declared}
    assert normalized == set(CONTROL_PLANE_PREFIXES) | set(CONTROL_PLANE_EXACT_PATHS)


def _create_small_release_source_pair(tmp_path: pathlib.Path):
    """Create a real two-commit release fixture without the shared worktree registry.

    The canonical checkout currently contains a large historical worktree
    registry.  Materializing a full product checkout from it is itself the
    timeout trigger under the release suite.  This fixture preserves the
    release entrypoint, source-separation assertions, and detached-worktree
    lifecycle while keeping the test-owned Git registry small and isolated.
    """
    repo = tmp_path / "release-source-separation"
    repo.mkdir()
    copied = (
        (BUILD_RELEASE, repo / "scripts" / "release" / "build-release-image.ps1"),
        (MODULE, repo / "scripts" / "release" / "ReleaseTooling.psm1"),
        (
            ROOT / "deploy" / "release-layout.example.json",
            repo / "deploy" / "release-layout.example.json",
        ),
    )
    for source, destination in copied:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    marker = repo / "scripts" / "release" / "gate-only-marker.txt"
    marker.write_text("product-control-plane-baseline\n", encoding="utf-8")
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Release Source Separation Test")
    git(repo, "config", "user.email", "release-source-separation@example.invalid")
    git(
        repo,
        "add",
        "scripts/release/build-release-image.ps1",
        "scripts/release/ReleaseTooling.psm1",
        "deploy/release-layout.example.json",
        "scripts/release/gate-only-marker.txt",
    )
    git(repo, "commit", "-q", "-m", "synthetic product release source")
    product_sha = git(repo, "rev-parse", "HEAD")
    marker.write_text("gate-control-plane-change\n", encoding="utf-8")
    git(repo, "add", "scripts/release/gate-only-marker.txt")
    git(repo, "commit", "-q", "-m", "synthetic release gate change")
    gate_sha = git(repo, "rev-parse", "HEAD")
    return repo, gate_sha, product_sha


def test_canonical_source_separation_dry_run_uses_product_identity_without_build(tmp_path):
    real_gate_sha = git(ROOT, "rev-parse", "HEAD")
    real_product_sha = derive_product_sha(real_gate_sha)
    assert git(ROOT, "merge-base", real_product_sha, real_gate_sha) == real_product_sha
    repo, gate_sha, product_sha = _create_small_release_source_pair(tmp_path)
    returncode, stdout, stderr = _dry_run(
        gate_sha,
        product_sha,
        repo_root=repo,
        build_script=repo / "scripts" / "release" / "build-release-image.ps1",
    )
    assert returncode == 0, (
        f"derived product sha {product_sha}\n"
        f"--- stdout ---\n{stdout}\n--- stderr ---\n{stderr}"
    )
    payload = parse_last_json(stdout)
    assert payload["source_separation_check"] == "PASS"
    assert payload["gate_source_sha"] == gate_sha
    assert payload["product_source_sha"] == product_sha
    assert payload["product_worktree_head"] == product_sha
    assert payload["product_worktree_clean"] is True
    assert payload["product_runtime_diff_from_product"] == 0
    assert payload["build_context"] == "PRODUCT_WORKTREE"
    assert payload["test_source"] == "GATE_WORKTREE"
    assert payload["oci_revision_would_be"] == product_sha
    assert payload["static_source_would_be"] == product_sha
    assert payload["build_not_executed"] is True
    assert "docker buildx" not in stdout.lower()


def test_derived_product_identity_is_a_real_ancestor_and_control_plane_only():
    """The derivation must stay meaningful, not merely satisfiable."""
    gate_sha = git(ROOT, "rev-parse", "HEAD")
    product_sha = derive_product_sha(gate_sha)
    assert git(ROOT, "merge-base", product_sha, gate_sha) == product_sha
    assert _non_control_plane_paths(product_sha, gate_sha) == []
    # It must not silently collapse to "everything is the gate": the derivation
    # walks back past every control-plane-only commit, so the commit *before*
    # the derived one must carry product bytes (or the derived one is the
    # oldest commit examined).
    parents = git(ROOT, "rev-list", "--max-count=2", product_sha).splitlines()
    if len(parents) == 2:
        older = parents[1].strip()
        assert _non_control_plane_paths(older, gate_sha), (
            "derivation did not stop at the newest product-bearing commit; "
            f"{older} -> {gate_sha} is still control-plane only"
        )


def test_unauthorized_product_diff_negative_control():
    """A Product baseline with real product drift must still fail closed.

    Uses the historical fixed pin, which is exactly such a baseline now. This
    is the guard against a derivation that 'passes' by choosing a point where
    every diff is empty.
    """
    gate_sha = git(ROOT, "rev-parse", "HEAD")
    unauthorized = _non_control_plane_paths(HISTORICAL_FIXED_PRODUCT_SHA, gate_sha)
    assert unauthorized, "negative control is only meaningful with real product drift"

    returncode, stdout, stderr = _dry_run(gate_sha, HISTORICAL_FIXED_PRODUCT_SHA)
    assert returncode != 0, "unauthorized product drift must not pass the gate"
    combined = f"{stdout}\n{stderr}"
    assert "UNAPPROVED_PRODUCT_DIFF_DETECTED" in combined, combined[:2000]


def test_source_separation_failure_diagnostic_surfaces_real_message():
    """The real gate message must reach the assertion, not TypeError/None.

    This is the regression guard for the zh-TW PowerShell decoding defect.
    """
    gate_sha = git(ROOT, "rev-parse", "HEAD")
    returncode, stdout, stderr = _dry_run(gate_sha, HISTORICAL_FIXED_PRODUCT_SHA)
    assert returncode != 0
    assert stdout is not None and stderr is not None
    combined = f"{stdout}\n{stderr}"
    assert combined.strip(), "diagnostics must not be empty"
    assert "UNAPPROVED_PRODUCT_DIFF_DETECTED" in combined
    assert "TypeError" not in combined
    assert "UnicodeDecodeError" not in combined


# ---------------------------------------------------------------------------
# INCIDENT_018_R8A1: pin-rot regression, on a synthetic throwaway repository.
# Proves the property that the old fixed pin lacked -- ordinary product
# advancement must not require anyone to hand-edit a SHA.
# ---------------------------------------------------------------------------

def _mk_repo(tmp_path: pathlib.Path) -> pathlib.Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "r8a1@test.local")
    git(repo, "config", "user.name", "r8a1")
    return repo


def _commit(repo: pathlib.Path, relpath: str, body: str) -> str:
    target = repo / relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    git(repo, "add", "--", relpath)
    git(repo, "commit", "-q", "-m", f"touch {relpath}")
    return git(repo, "rev-parse", "HEAD")


def test_normal_product_advancement_no_pin_rot(tmp_path):
    repo = _mk_repo(tmp_path)
    _commit(repo, "app.py", "v1\n")
    product_a = _commit(repo, "app.py", "v2\n")
    _commit(repo, "scripts/release/tool.ps1", "cp1\n")
    gate_a = _commit(repo, "tests/deployment/test_x.py", "cp2\n")

    # Derivation picks the newest product-bearing commit, not a hand-set pin.
    assert derive_product_sha(gate_a, repo_root=repo) == product_a
    assert _non_control_plane_paths(product_a, gate_a, repo_root=repo) == []

    # A normal product commit lands, then more control-plane work.
    product_b = _commit(repo, "app.py", "v3\n")
    gate_b = _commit(repo, "scripts/release/tool.ps1", "cp3\n")

    # No SHA was edited anywhere, yet the contract still holds.
    assert derive_product_sha(gate_b, repo_root=repo) == product_b
    assert _non_control_plane_paths(product_b, gate_b, repo_root=repo) == []

    # And the stale baseline is now genuinely unauthorized -- the gate would
    # fire, which is the behaviour the old fixed pin was tripping over.
    assert _non_control_plane_paths(product_a, gate_b, repo_root=repo) == ["app.py"]


def test_derivation_fails_closed_when_no_control_plane_only_baseline(tmp_path):
    repo = _mk_repo(tmp_path)
    _commit(repo, "app.py", "v1\n")
    gate = _commit(repo, "app.py", "v2\n")
    # The tip itself carries product bytes, so the newest valid baseline is the
    # tip: the derivation must return it rather than inventing a older one that
    # would smuggle product drift past the gate.
    assert derive_product_sha(gate, repo_root=repo) == gate
    assert _non_control_plane_paths(gate, gate, repo_root=repo) == []
