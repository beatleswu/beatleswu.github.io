import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from workflow_v2_evidence import (  # noqa: E402
    EvidenceError,
    collect_candidate_evidence,
    collect_release_provenance,
    required_check_categories,
    validate_candidate_evidence,
    validate_release_provenance,
)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _make_repo(tmp_path: Path) -> tuple[Path, str, str, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "master")
    _git(repo, "config", "user.email", "workflow-v2-test@example.invalid")
    _git(repo, "config", "user.name", "Workflow V2 Test")

    (repo / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(repo, "add", "app.py")
    _git(repo, "commit", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")

    _git(repo, "checkout", "-b", "feature")
    (repo / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
    (repo / "feature.py").write_text("FEATURE = True\n", encoding="utf-8")
    _git(repo, "add", "app.py", "feature.py")
    _git(repo, "commit", "-m", "feature")
    feature = _git(repo, "rev-parse", "HEAD")

    _git(repo, "checkout", "master")
    (repo / "base_only.txt").write_text("base side change\n", encoding="utf-8")
    _git(repo, "add", "base_only.txt")
    _git(repo, "commit", "-m", "canonical side change")
    _git(repo, "merge", "--no-ff", "feature", "-m", "Merge feature")
    merged = _git(repo, "rev-parse", "HEAD")
    return repo, base, feature, merged


def _checks(*, python=False, javascript=False, browser=False, heavy=False):
    categories = required_check_categories(
        "HEAVY" if heavy else "NORMAL",
        python_relevant=python,
        javascript_relevant=javascript,
        browser_relevant=browser,
    )
    return [
        {"category": category, "status": "PASS", "details": "test evidence"}
        for category in sorted(categories)
    ]


def _app_artifact(source_sha: str):
    return {
        "image_tag": "go-odyssey-app:test",
        "image_id": "sha256:" + "1" * 64,
        "archive_sha256": "a" * 64,
        "oci_revision": source_sha,
    }


def _static_artifact(source_sha: str):
    return {
        "static_generation_id": "20260812-test-v1",
        "archive_sha256": "b" * 64,
        "release_git_sha": source_sha,
        "service_worker_identity": "release-" + source_sha,
    }


def test_candidate_evidence_derives_tree_blobs_and_changed_scope(tmp_path):
    repo, base, feature, _ = _make_repo(tmp_path)

    evidence = collect_candidate_evidence(
        repo,
        base_ref=base,
        head_ref="feature",
        repository="go-odyssey",
        risk_class="NORMAL",
        classification_basis=["bounded_server_logic"],
        scope_statement="One bounded application behavior change",
        checks=_checks(python=True),
        python_relevant=True,
        planned_release_type="APP_ONLY",
        pr_number=401,
        generated_at="2026-08-12T00:00:00Z",
    )

    assert evidence["pr_head"]["sha"] == feature
    assert len(evidence["pr_head"]["tree_sha"]) == 40
    assert {entry["path"] for entry in evidence["scope"]["changed_files"]} == {
        "app.py",
        "feature.py",
    }
    assert all(len(entry["blob_sha"]) == 40 for entry in evidence["scope"]["changed_files"])
    assert "merged_source_sha" not in evidence
    validate_candidate_evidence(evidence, repo)


def test_candidate_contract_requires_relevant_checks_and_authority_basis(tmp_path):
    repo, base, _, _ = _make_repo(tmp_path)

    with pytest.raises(EvidenceError, match="missing required validation"):
        collect_candidate_evidence(
            repo,
            base_ref=base,
            head_ref="feature",
            repository="go-odyssey",
            risk_class="NORMAL",
            classification_basis=["ui"],
            scope_statement="Browser behavior",
            checks=_checks(),
            browser_relevant=True,
        )

    with pytest.raises(EvidenceError, match="NORMAL cannot claim"):
        collect_candidate_evidence(
            repo,
            base_ref=base,
            head_ref="feature",
            repository="go-odyssey",
            risk_class="NORMAL",
            classification_basis=["deployment_tooling"],
            scope_statement="Invalid class",
            checks=_checks(),
        )

    with pytest.raises(EvidenceError, match="HOTFIX requires"):
        collect_candidate_evidence(
            repo,
            base_ref=base,
            head_ref="feature",
            repository="go-odyssey",
            risk_class="HOTFIX",
            classification_basis=["ui"],
            scope_statement="Invalid hotfix",
            checks=_checks(),
        )


def test_release_provenance_binds_exact_merged_source_and_paired_artifacts(tmp_path):
    repo, base, _, merged = _make_repo(tmp_path)
    candidate = collect_candidate_evidence(
        repo,
        base_ref=base,
        head_ref="feature",
        repository="go-odyssey",
        risk_class="NORMAL",
        classification_basis=["bounded_server_logic"],
        scope_statement="Paired release candidate",
        checks=_checks(python=True),
        python_relevant=True,
        planned_release_type="PAIRED_APP_STATIC",
        pr_number=402,
    )
    candidate["base_ref"] = "master"
    candidate_path = tmp_path / "pr-evidence.json"
    candidate_path.write_text(json.dumps(candidate), encoding="utf-8")

    release = collect_release_provenance(
        repo,
        merged_ref=merged,
        canonical_ref="master",
        repository="go-odyssey",
        release_id="release-402",
        release_type="PAIRED_APP_STATIC",
        risk_class="NORMAL",
        classification_basis=["bounded_server_logic"],
        app_artifact=_app_artifact(merged),
        static_artifact=_static_artifact(merged),
        candidate_evidence_path=candidate_path,
        generated_at="2026-08-12T00:00:00Z",
    )

    assert release["merged_source_sha"] == merged
    assert release["merged_tree_sha"] == _git(repo, "rev-parse", merged + "^{tree}")
    assert len(release["merge_parents"]) == 2
    assert release["pr_evidence"]["pr_head_sha"] == candidate["pr_head"]["sha"]
    validate_release_provenance(release, repo)


def test_release_type_requires_only_the_declared_artifact_pair(tmp_path):
    repo, _, _, merged = _make_repo(tmp_path)
    common = {
        "repo": repo,
        "merged_ref": merged,
        "canonical_ref": "master",
        "repository": "go-odyssey",
        "release_id": "release-type-test",
        "risk_class": "NORMAL",
        "classification_basis": ["documentation"],
        "external_content": [],
    }

    app_only = collect_release_provenance(
        **common,
        release_type="APP_ONLY",
        app_artifact=_app_artifact(merged),
        static_artifact=None,
    )
    static_only = collect_release_provenance(
        **common,
        release_type="STATIC_ONLY",
        app_artifact=None,
        static_artifact=_static_artifact(merged),
    )
    assert app_only["artifacts"]["static"] is None
    assert static_only["artifacts"]["app"] is None

    with pytest.raises(EvidenceError, match="static artifact is required"):
        collect_release_provenance(
            **common,
            release_type="PAIRED_APP_STATIC",
            app_artifact=_app_artifact(merged),
            static_artifact=None,
        )


def test_release_cannot_be_generated_from_unmerged_candidate(tmp_path):
    repo, base, feature, _ = _make_repo(tmp_path)
    with pytest.raises(EvidenceError, match="reachable from canonical_ref"):
        collect_release_provenance(
            repo,
            merged_ref=feature,
            canonical_ref=base,
            repository="go-odyssey",
            release_id="release-unmerged",
            release_type="APP_ONLY",
            risk_class="NORMAL",
            classification_basis=["bounded_server_logic"],
            app_artifact=_app_artifact(feature),
            static_artifact=None,
        )


def test_schema_documents_and_deploy_boundary_are_present():
    for name in (
        "workflow-v2-pr-evidence.schema.json",
        "workflow-v2-release-provenance.schema.json",
    ):
        schema = json.loads(
            (REPO_ROOT / "docs" / "architecture" / name).read_text(encoding="utf-8")
        )
        assert schema["$schema"].startswith("https://json-schema.org/")
        assert schema["properties"]["artifact_kind"]["const"] in {
            "PR_EVIDENCE",
            "RELEASE_PROVENANCE",
        }

    assert not (REPO_ROOT / "deploy.ps1").exists()


def test_cli_validates_a_candidate_artifact(tmp_path):
    repo, base, _, _ = _make_repo(tmp_path)
    evidence = collect_candidate_evidence(
        repo,
        base_ref=base,
        head_ref="feature",
        repository="go-odyssey",
        risk_class="NORMAL",
        classification_basis=["documentation"],
        scope_statement="CLI validation contract",
        checks=_checks(),
    )
    evidence_path = tmp_path / "candidate.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "workflow_v2_evidence.py"),
            "validate",
            "--kind",
            "candidate",
            "--repo",
            str(repo),
            "--input",
            str(evidence_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"status": "PASS"' in result.stdout
