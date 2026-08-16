"""Contracts for separating release gate/tooling source from product source."""

from __future__ import annotations

import json
import os
import pathlib
import subprocess


ROOT = pathlib.Path(__file__).resolve().parents[2]
MODULE = ROOT / "scripts" / "release" / "ReleaseTooling.psm1"
BUILD_RELEASE = ROOT / "scripts" / "release" / "build-release-image.ps1"
BUILD_PRODUCTION = ROOT / "scripts" / "build-production-image.ps1"
PACKAGE_STATIC = ROOT / "scripts" / "release" / "package-static-release.ps1"
PRODUCT_SHA = "45eef15ec259c6829bc38e57164109ad16950220"


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
    assert len(provenance["files"]) == 80
    governed_paths = {entry["path"] for entry in provenance["files"]}
    assert "js/game/lord_trial_controller.js" in governed_paths
    assert "js/game/presentation_dispatcher.js" in governed_paths


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
