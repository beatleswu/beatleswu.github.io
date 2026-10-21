"""2026-10-21 Owner-approved simplified Product Build policy tests.

Only uses disposable synthetic Git repositories; no official GitHub, Docker
Build, production infrastructure or player data is modified. GO_MERGE and
GO_DEPLOY remain separate explicit Owner decisions. Legacy external default
must stay closed, while opt-in Owner policy may generate an honest DryRun.
"""
from __future__ import annotations
import pathlib
import shutil
import subprocess
import json

import pytest

from test_release_source_separation import _create_small_release_source_pair

ROOT=pathlib.Path(__file__).resolve().parents[2]
BUILD=ROOT/"scripts/release/build-release-image.ps1"

def run(repo,gate,product,*flags):
    args=[
      "powershell","-NoProfile","-NonInteractive",
      "-ExecutionPolicy","Bypass","-File",
      str(repo/"scripts/release/build-release-image.ps1"),
      "-GateSourceSha",gate,"-ProductSourceSha",product,
      "-DryRun",*flags]
    return subprocess.run(args,cwd=repo,capture_output=True,text=True,
                          errors="replace",timeout=90)

def parse_json(raw):
    pos=raw.find("{")
    assert pos!=-1,raw[-1200:]
    return json.JSONDecoder().raw_decode(raw[pos:])[0]

def test_owner_simplified_dry_run_validates_clean_actual_git_sources(tmp_path):
    repo,gate,product=_create_small_release_source_pair(tmp_path)
    p=run(repo,gate,product,"-OwnerSimplifiedPolicy")
    assert p.returncode==0,(p.stdout,p.stderr)
    out=parse_json(p.stdout)
    assert out["dry_run"] is True
    assert out["source_separation_check"]=="PASS"
    assert out["gate_source_sha"]==gate
    assert out["product_source_sha"]==product
    assert out["product_worktree_clean"] is True
    assert out["build_not_executed"] is True

def test_default_legacy_build_policy_still_denies_without_external_host(tmp_path):
    repo,gate,product=_create_small_release_source_pair(tmp_path)
    p=run(repo,gate,product)
    assert p.returncode!=0
    assert "EXTERNAL_GOVERNANCE_AUTHORITY_REQUIRED" in (p.stdout+p.stderr)

def test_owner_simplified_missing_source_identity_is_rejected(tmp_path):
    repo,gate,product=_create_small_release_source_pair(tmp_path)
    p=run(repo,gate,"","-OwnerSimplifiedPolicy")
    assert p.returncode!=0
    assert "OWNER_SIMPLIFIED_POLICY_EXACT_SOURCE_REQUIRED" in p.stdout+p.stderr

def test_owner_simplified_cannot_mix_synthetic_host_authority(tmp_path):
    repo,gate,product=_create_small_release_source_pair(tmp_path)
    p=run(repo,gate,product,"-OwnerSimplifiedPolicy",
          "-GovernanceGateSourceSha",gate)
    assert p.returncode!=0
    assert "OWNER_SIMPLIFIED_POLICY_NO_EXTERNAL_GOVERNANCE_MIX" in p.stdout+p.stderr

def test_owner_simplified_wrong_gate_identity_does_not_authorize(tmp_path):
    repo,gate,product=_create_small_release_source_pair(tmp_path)
    p=run(repo,product,gate,"-OwnerSimplifiedPolicy")
    assert p.returncode!=0
    assert "Gate worktree HEAD" in p.stdout+p.stderr or "GateSourceSha" in p.stdout+p.stderr

def test_owner_simplified_uncommitted_gate_source_rejected(tmp_path):
    repo,gate,product=_create_small_release_source_pair(tmp_path)
    (repo/"scripts/release/gate-only-marker.txt").write_text("tampered-uncommitted\n",encoding="utf8")
    p=run(repo,gate,product,"-OwnerSimplifiedPolicy")
    assert p.returncode!=0
    assert "worktree" in (p.stdout+p.stderr).lower() or "clean" in (p.stdout+p.stderr).lower()

def test_owner_simplified_untracked_gate_source_rejected(tmp_path):
    repo,gate,product=_create_small_release_source_pair(tmp_path)
    (repo/"rogue.py").write_text("print('x')\n",encoding="utf8")
    p=run(repo,gate,product,"-OwnerSimplifiedPolicy")
    assert p.returncode!=0
    assert "clean" in (p.stdout+p.stderr).lower() or "untracked" in (p.stdout+p.stderr).lower()

def test_owner_policy_is_not_merge_or_deploy_permission():
    t=BUILD.read_text(encoding="utf8")
    assert "[switch]$OwnerSimplifiedPolicy" in t
    assert "EXTERNAL_GOVERNANCE_ATTESTATION_REQUIRED" in t
    assert "Assert-CompleteWorktreeClean -WorkingDirectory $gateWorktree" in t
    assert "Assert-ReleaseSourceSeparation" in t
    assert "-Execute" not in t  # This script never authorizes or runs Oracle deployment.
