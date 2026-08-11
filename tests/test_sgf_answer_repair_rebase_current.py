"""Deterministic checks for the current-canonical repair-batch rebase.

The checked-in contract is evidence only: it is staged, never canonical.  The
large candidate itself is kept outside the repository and is verified when it
is available in the local governed workspace.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs" / "planning" / "sgf_answer_current_canonical_contract_v2"
LOCAL_CANONICAL = Path(r"D:\go-website\questions.json")
LOCAL_CANDIDATE = Path(
    r"D:\go-website-sgf-repair-batch-rebase-current-001-artifacts"
    r"\questions.current-canonical-repaired-candidate.4ac424c4af8a.json"
)
BASELINE_SHA256 = "88da3e43b41f46380a2c0534fa2fc892b69eb99df4055dd635333b7153f654ff"
CANDIDATE_SHA256 = "4ac424c4af4acf46d1df1dd4b4579b57b01a08745dd7f621c7f50ce21e78f125"
SURFACES = {
    "sgf_engine_native",
    "rating_test_server",
    "map_battle_server",
    "main_practice_client",
    "daily_challenge_client",
    "friend_challenge_client_then_server_trust",
}


def _load(name: str) -> dict:
    return json.loads((CONTRACT / name).read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_current_rebase_report_is_complete_and_fail_closed() -> None:
    report = _load("current-canonical-rebase-report.json")
    assert report["current_baseline"]["sha256"] == BASELINE_SHA256
    assert report["current_baseline"]["record_count"] == 42_804
    assert report["current_candidate"]["sha256"] == CANDIDATE_SHA256
    assert report["current_candidate"]["record_count"] == 42_804
    assert report["classification_summary"] == {
        "ALREADY_REPAIRED": 0,
        "DRIFTED_TARGET": 0,
        "MISSING_TARGET": 0,
        "UNCHANGED_TARGET": 54,
    }
    assert report["approved_repair_group_count"] == 43
    assert report["approved_record_count"] == 54
    assert report["exclusion_count"] == 11
    assert report["fallback_conflict_count"] == 3
    assert report["six_surfaces_complete"] is True
    assert report["verdict_mismatch_count"] == 0
    assert report["canonical_mutation"] == "NO"
    assert report["production_mutation"] == "NO"
    assert report["gf003_state"] == {
        "apply_automatically": False,
        "ready_promotion": "NO",
        "runtime_status": "disabled",
    }


def test_contract_artifacts_bind_current_candidate_and_acceptance() -> None:
    release = _load("release-manifest.json")
    governance = release["release_governance"]
    provenance = _load("source-provenance.json")
    mutation = _load("mutation-audit.json")
    repair_batch = _load("repair-batch-manifest.json")
    acceptance = _load("acceptance-evidence.json")
    rollback = _load("rollback-manifest.json")

    assert release["source_baseline_sha256"] == BASELINE_SHA256
    assert release["repaired_candidate_artifact"]["sha256"] == CANDIDATE_SHA256
    assert governance["changed_record_count"] == 54
    assert governance["review_group_count"] == 43
    assert governance["excluded_record_count"] == 11
    assert governance["rollback_manifest_sha256"] == _sha256(CONTRACT / "rollback-manifest.json")
    assert governance["acceptance_evidence_sha256"] == _sha256(CONTRACT / "acceptance-evidence.json")

    assert provenance["source_sha256"] == BASELINE_SHA256
    assert provenance["source_record_count"] == 42_804
    assert provenance["source_status"] == "IMMUTABLE_SNAPSHOT_BYTE_VERIFIED"
    assert provenance["source_snapshot_sha256"] == BASELINE_SHA256
    assert mutation["source_sha256"] == BASELINE_SHA256
    assert mutation["candidate_sha256"] == CANDIDATE_SHA256
    assert mutation["changed_record_count"] == 54
    assert mutation["review_group_count"] == 43
    assert mutation["non_target_records_changed"] == 0
    assert mutation["accepted_moves_changed"] == 0
    assert repair_batch["current_baseline_sha256"] == BASELINE_SHA256
    assert repair_batch["candidate_sha256"] == CANDIDATE_SHA256
    assert repair_batch["changed_record_count"] == 54
    assert repair_batch["review_group_count"] == 43

    assert acceptance["candidate_sha256"] == CANDIDATE_SHA256
    assert acceptance["summary"]["records_validated"] == 54
    assert acceptance["summary"]["all_final_effective_match"] is True
    assert set(acceptance["summary"]["surfaces"]) == SURFACES
    assert rollback["rollback_governance"]["previous_sha256"] == BASELINE_SHA256
    assert rollback["rollback_governance"]["candidate_sha256"] == CANDIDATE_SHA256
    assert rollback["safety"]["publish_requires_rollback_proof"] is True


def test_current_candidate_hash_when_local_snapshot_is_available() -> None:
    if not LOCAL_CANDIDATE.is_file():
        pytest.skip("governed candidate artifact is external to the repository")
    assert _sha256(LOCAL_CANDIDATE) == CANDIDATE_SHA256
    records = json.loads(LOCAL_CANDIDATE.read_text(encoding="utf-8"))
    assert isinstance(records, list)
    assert len(records) == 42_804


def test_target_drift_is_classified_without_mutating_the_canonical_snapshot() -> None:
    if not LOCAL_CANONICAL.is_file():
        pytest.skip("canonical snapshot is external to the repository")
    from tools.sgf_answer_repair_rebase import (  # local import keeps the test light
        _load_approved_batch,
        _load_corpus,
        classify_approved_targets,
    )

    _raw, records, _identity = _load_corpus(LOCAL_CANONICAL, "test_current_canonical")
    _locked, native_records, fallback_records = _load_approved_batch(
        ROOT / "docs" / "planning" / "sgf_answer_repair_batch_001_safe_release_batch_001.json"
    )
    tampered = [dict(record) for record in records]
    target_id = int(native_records[0]["legacy_question_id"])
    target = next(record for record in tampered if int(record["id"]) == target_id)
    target["content"] = target["content"] + "\n"
    classified = classify_approved_targets(
        current_records=tampered,
        native_records=native_records,
        fallback_records=fallback_records,
    )
    row = next(item for item in classified if int(item["legacy_question_id"]) == target_id)
    assert row["classification"] == "DRIFTED_TARGET"
    assert LOCAL_CANONICAL.stat().st_size > 0


def test_wrong_current_master_ref_fails_closed() -> None:
    from tools.sgf_answer_repair_rebase import RebaseError, verify_current_base

    with pytest.raises(RebaseError, match="base_ref_not_authorized_current_master"):
        verify_current_base("0" * 40, repo_root=ROOT)
