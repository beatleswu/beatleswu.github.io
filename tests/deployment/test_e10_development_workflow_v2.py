"""Fail-closed contracts for the E10 Development Workflow V2 foundation."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "release" / "e10_development_workflow_v2.py"
sys.path.insert(0, str(SCRIPT.parent))
import e10_development_workflow_v2 as workflow  # noqa: E402


def git(repo: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if check and result.returncode:
        raise AssertionError(result.stderr or result.stdout)
    return result.stdout.strip()


def commit(repo: Path, paths: list[str], message: str) -> str:
    assert paths
    git(repo, "add", "--", *paths)
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def make_repo(tmp_path: Path) -> tuple[Path, str, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Workflow V2 Test")
    git(repo, "config", "user.email", "workflow-v2@example.invalid")

    files = {
        "product.txt": "product-v1\n",
        "tests/smoke.py": "print('workflow smoke')\n",
    }
    for relative, content in files.items():
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    for relative in workflow.CANONICAL_RELEASE_TOOLS.values():
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# canonical test seam\n", encoding="utf-8")
        files[relative] = path.read_text(encoding="utf-8")
    root_sha = commit(repo, list(files), "synthetic product source")

    (repo / "product.txt").write_text("product-v2\n", encoding="utf-8")
    base_sha = commit(repo, ["product.txt"], "synthetic product baseline")
    return repo, root_sha, base_sha


def add_candidate(repo: Path, relative: str = "scripts/release/workflow-change.txt") -> str:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("workflow-only\n", encoding="utf-8")
    return commit(repo, [relative], "synthetic workflow implementation")


def smoke_test_spec(*, failing: bool = False) -> list[dict[str, object]]:
    code = "raise SystemExit(7)" if failing else "from pathlib import Path; assert Path('tests/smoke.py').is_file()"
    return [
        {
            "name": "synthetic smoke",
            "path": "tests/smoke.py",
            "command": [sys.executable, "-c", code],
        }
    ]


def pr_payload(repo: Path, base: str, candidate: str, *, tests=None) -> dict[str, object]:
    return {
        "repo": str(repo),
        "base_sha": base,
        "candidate_sha": candidate,
        "implementation_sha": candidate,
        "product_source_sha": base,
        "tooling_sha": candidate,
        "tests": smoke_test_spec() if tests is None else tests,
    }


def make_post_merge_fixture(tmp_path: Path) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    repo, _root, base = make_repo(tmp_path)
    candidate = add_candidate(repo)
    pr = workflow.build_pr_ready_packet(pr_payload(repo, base, candidate))
    git(repo, "checkout", "-q", "-b", "canonical", base)
    git(repo, "merge", "--no-ff", "-m", "Owner merge for test", candidate)
    merge = git(repo, "rev-parse", "HEAD")
    gates = {
        name: {"status": "PASS"} for name in sorted(workflow.REQUIRED_POST_MERGE_GATES)
    }
    payload = {
        "repo": str(repo),
        "base_sha": base,
        "expected_implementation_sha": candidate,
        "expected_product_source_sha": base,
        "tooling_sha": candidate,
        "actual_merge_sha": merge,
        "expected_changed_files": pr["CHANGED_FILES"],
        "provenance": {
            "base_sha": base,
            "implementation_sha": candidate,
            "product_source_sha": base,
            "tooling_sha": candidate,
            "merge_sha": merge,
            "runtime_source_sha": base,
            "canonical_ref": "HEAD",
            "canonical_ref_sha": merge,
            "gates": gates,
            "product_runtime_changed_files": [],
        },
    }
    post = workflow.build_post_merge_packet(payload)
    return payload, post, {"repo": repo, "base": base, "candidate": candidate, "merge": merge}


def rollback_pair_payload(source_sha: str) -> dict[str, object]:
    app = {
        "image_id": "sha256:" + "1" * 64,
        "image_tag": "go-odyssey-app:previous",
        "oci_revision": source_sha,
    }
    static = {
        "manifest_sha256": "2" * 64,
        "static_generation_id": "static-previous",
        "release_git_sha": source_sha,
        "service_worker_identity": "sw-previous",
    }
    return {
        "authority": workflow.ROLLBACK_AUTHORITY,
        "captured_before_deploy": True,
        "source_tool": "preflight-production.ps1",
        "capture_id": "predeploy-capture-001",
        "pair_id": workflow.calculate_current_pair_id(app, static),
        "app": app,
        "static": static,
    }


def release_payload(post: dict[str, object], *, rollback=None) -> dict[str, object]:
    return {
        "post_merge": post,
        "required_test_gates": [
            {"name": "targeted_workflow_v2", "status": "PASS", "evidence": "pytest:pass"},
            {"name": "source_separation", "status": "PASS", "evidence": "contract:pass"},
        ],
        "static_build_required": True,
        "oci_build_required": True,
        "rollback_preflight_required": True,
        "owner_gate": {
            "explicit": True,
            "name": "GO_DEPLOY",
            "evidence": "Owner supplied gate in coordinator packet",
        },
        "rollback_authority": rollback or rollback_pair_payload(post["PRODUCT_SOURCE_SHA"]),
    }


def test_valid_pr_ready_packet_is_deterministic_and_separate(tmp_path: Path) -> None:
    repo, _root, base = make_repo(tmp_path)
    candidate = add_candidate(repo)
    packet = workflow.build_pr_ready_packet(pr_payload(repo, base, candidate))

    assert packet["PR_READY"] == "YES"
    assert packet["BASE_SHA"] == base
    assert packet["CANDIDATE_SHA"] == candidate
    assert packet["IMPLEMENTATION_SHA"] == candidate
    assert packet["PRODUCT_SOURCE_SHA"] == base
    assert packet["TOOLING_SHA"] == candidate
    assert packet["MERGE_SHA"] == workflow.NOT_YET_MERGED
    assert packet["PRODUCT_RUNTIME_CHANGED"] == "NO"
    assert packet["R2A_INCLUDED"] == "NO"
    assert packet["BLOCKERS"] == []
    assert packet == workflow.build_pr_ready_packet(pr_payload(repo, base, candidate))


def test_dirty_worktree_fails_closed(tmp_path: Path) -> None:
    repo, _root, base = make_repo(tmp_path)
    candidate = add_candidate(repo)
    (repo / "dirty.txt").write_text("uncommitted\n", encoding="utf-8")
    with pytest.raises(workflow.WorkflowError, match="worktree must be clean"):
        workflow.build_pr_ready_packet(pr_payload(repo, base, candidate))


def test_unknown_base_fails_closed(tmp_path: Path) -> None:
    repo, _root, base = make_repo(tmp_path)
    candidate = add_candidate(repo)
    payload = pr_payload(repo, base, candidate)
    payload["base_sha"] = "0" * 40
    with pytest.raises(workflow.WorkflowError, match="BASE_SHA"):
        workflow.build_pr_ready_packet(payload)


def test_candidate_not_descendant_of_expected_base_fails_closed(tmp_path: Path) -> None:
    repo, root, base = make_repo(tmp_path)
    git(repo, "checkout", "-q", "-b", "unrelated", root)
    candidate = add_candidate(repo, "scripts/release/unrelated-change.txt")
    payload = pr_payload(repo, base, candidate)
    payload["product_source_sha"] = root
    with pytest.raises(workflow.WorkflowError, match="not a descendant"):
        workflow.build_pr_ready_packet(payload)


def test_forbidden_r2a_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo, _root, base = make_repo(tmp_path)
    candidate = add_candidate(repo)
    monkeypatch.setattr(workflow, "FORBIDDEN_R2A_SHA", candidate)
    with pytest.raises(workflow.WorkflowError, match="forbidden R2A"):
        workflow.build_pr_ready_packet(pr_payload(repo, base, candidate))


def test_missing_test_evidence_fails_closed(tmp_path: Path) -> None:
    repo, _root, base = make_repo(tmp_path)
    candidate = add_candidate(repo)
    with pytest.raises(workflow.WorkflowError, match="supplied tests are required"):
        workflow.build_pr_ready_packet(pr_payload(repo, base, candidate, tests=[]))


def test_failed_supplied_test_fails_closed(tmp_path: Path) -> None:
    repo, _root, base = make_repo(tmp_path)
    candidate = add_candidate(repo)
    with pytest.raises(workflow.WorkflowError, match="supplied test failed"):
        workflow.build_pr_ready_packet(
            pr_payload(repo, base, candidate, tests=smoke_test_spec(failing=True))
        )


def test_tooling_sha_cannot_be_product_sha(tmp_path: Path) -> None:
    repo, _root, base = make_repo(tmp_path)
    candidate = add_candidate(repo)
    payload = pr_payload(repo, base, candidate)
    payload["tooling_sha"] = base
    with pytest.raises(workflow.WorkflowError, match="must not equal TOOLING_SHA"):
        workflow.build_pr_ready_packet(payload)


def test_conflict_marker_fails_closed(tmp_path: Path) -> None:
    repo, _root, base = make_repo(tmp_path)
    candidate = add_candidate(repo)
    path = repo / "scripts/release/workflow-change.txt"
    path.write_text("<<<<<<< HEAD\nconflict\n>>>>>>> branch\n", encoding="utf-8")
    candidate = commit(repo, ["scripts/release/workflow-change.txt"], "conflict marker")
    payload = pr_payload(repo, base, candidate)
    with pytest.raises(workflow.WorkflowError, match="conflict markers"):
        workflow.build_pr_ready_packet(payload)


def test_valid_post_merge_packet_checks_lineage_and_provenance(tmp_path: Path) -> None:
    payload, post, state = make_post_merge_fixture(tmp_path)

    assert post["POST_MERGE"] == "YES"
    assert post["MERGE_SHA"] == state["merge"]
    assert post["OWNER_MERGE_OBSERVED"] == "YES"
    assert post["PRODUCT_SOURCE_SHA"] != post["TOOLING_SHA"]
    assert post["R2A_IS_ANCESTOR_OF_FINAL_HEAD"] == "NO"
    assert post["PROVENANCE"]["runtime_source_sha"] == state["base"]
    assert payload["actual_merge_sha"] == state["merge"]


def test_missing_provenance_identity_fails_closed(tmp_path: Path) -> None:
    payload, _post, _state = make_post_merge_fixture(tmp_path)
    del payload["provenance"]["runtime_source_sha"]
    with pytest.raises(workflow.WorkflowError, match="provenance.runtime_source_sha"):
        workflow.build_post_merge_packet(payload)


def test_post_merge_unrelated_file_fails_closed(tmp_path: Path) -> None:
    payload, _post, state = make_post_merge_fixture(tmp_path)
    repo = state["repo"]
    assert isinstance(repo, Path)
    path = repo / "scripts/release/unrelated-after-merge.txt"
    path.write_text("unexpected\n", encoding="utf-8")
    git(repo, "add", "--", "scripts/release/unrelated-after-merge.txt")
    git(repo, "commit", "-q", "-m", "unrelated post merge change")
    payload["actual_merge_sha"] = git(repo, "rev-parse", "HEAD")
    payload["provenance"]["merge_sha"] = payload["actual_merge_sha"]
    payload["provenance"]["canonical_ref_sha"] = payload["actual_merge_sha"]
    with pytest.raises(workflow.WorkflowError, match="unrelated or missing"):
        workflow.build_post_merge_packet(payload)


def test_rollback_inferred_only_from_previous_symlink_fails_closed(tmp_path: Path) -> None:
    _payload, post, _state = make_post_merge_fixture(tmp_path)
    rollback = {"authority": "LEGACY_PREVIOUS_SYMLINK", "previous_symlink": "/releases/previous"}
    with pytest.raises(workflow.WorkflowError, match="EXPLICIT_PRE_DEPLOY_CURRENT_PAIR"):
        workflow.build_release_prep_handoff(release_payload(post, rollback=rollback))


def test_unknown_rollback_current_pair_fails_closed(tmp_path: Path) -> None:
    _payload, post, _state = make_post_merge_fixture(tmp_path)
    rollback = rollback_pair_payload(post["PRODUCT_SOURCE_SHA"])
    del rollback["static"]
    with pytest.raises(workflow.WorkflowError, match="rollback_authority.static"):
        workflow.build_release_prep_handoff(release_payload(post, rollback=rollback))


def test_valid_release_prep_handoff_requires_explicit_owner_gate_and_pair(tmp_path: Path) -> None:
    _payload, post, _state = make_post_merge_fixture(tmp_path)
    handoff = workflow.build_release_prep_handoff(release_payload(post))

    assert handoff["RELEASE_PREP_HANDOFF"] == "YES"
    assert handoff["PRODUCT_SOURCE_SHA"] == post["PRODUCT_SOURCE_SHA"]
    assert handoff["TOOLING_SHA"] == post["TOOLING_SHA"]
    assert handoff["MERGE_SHA"] == post["MERGE_SHA"]
    assert handoff["STATIC_BUILD_REQUIRED"] is True
    assert handoff["OCI_BUILD_REQUIRED"] is True
    assert handoff["ROLLBACK_PREFLIGHT_REQUIRED"] is True
    assert handoff["NEXT_OWNER_GATE"] == "GO_DEPLOY"
    assert handoff["OWNER_GATE_INFERENCE"] == "FORBIDDEN"
    assert handoff["ROLLBACK_CURRENT_PAIR_AUTHORITY"] == workflow.ROLLBACK_AUTHORITY
    assert set(handoff["CANONICAL_RELEASE_TOOLS"]) == set(workflow.CANONICAL_RELEASE_TOOLS)
    assert handoff["BLOCKERS"] == []


def test_cli_writes_machine_and_human_packets_on_success(tmp_path: Path) -> None:
    repo, _root, base = make_repo(tmp_path)
    candidate = add_candidate(repo)
    input_path = tmp_path / "pr-ready-input.json"
    output_path = tmp_path / "pr-ready-packet.json"
    human_path = tmp_path / "pr-ready-packet.txt"
    input_path.write_text(
        json.dumps(pr_payload(repo, base, candidate), sort_keys=True),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "pr-ready",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--human-output",
            str(human_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    packet = json.loads(output_path.read_text(encoding="utf-8"))
    assert packet["PR_READY"] == "YES"
    human = human_path.read_text(encoding="utf-8")
    assert "PR_READY=YES" in human
    assert "PRODUCT_SOURCE_SHA=" in human
