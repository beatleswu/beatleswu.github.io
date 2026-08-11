"""Deterministic checks for the checked-in PR318 repair-package binding."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

import tools.content_release_core as core
from tools.content_release_core import GovernanceError


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs/planning/sgf_answer_pr318_contract"
BASELINE_SHA256 = "4d13fa98af8c1a180e719b7a261c5ca638e042a8edbd3fdfe8d2c2f947cdaa28"
CANDIDATE_SHA256 = "b7b4eedf72a87ab8fbc82ff51b658cd4dc0f08cb33426aee013e97814edae232"
SURFACES = {
    "sgf_engine_native",
    "rating_test_server",
    "map_battle_server",
    "main_practice_client",
    "daily_challenge_client",
    "friend_challenge_client_then_server_trust",
}


def _load(name: str):
    return json.loads((CONTRACT / name).read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_checked_in_contract_artifacts_have_stable_identity_links():
    release = _load("release-manifest.json")
    governance = release["release_governance"]
    assert release["source_baseline_sha256"] == BASELINE_SHA256
    assert release["pre_mutation_artifact"]["sha256"] == BASELINE_SHA256
    assert release["repaired_candidate_artifact"]["sha256"] == CANDIDATE_SHA256
    for artifact, field in (
        ("review-binding.json", "review_binding_sha256"),
        ("repair-batch-manifest.json", "repair_batch_manifest_sha256"),
        ("mutation-audit.json", "mutation_audit_sha256"),
        ("acceptance-evidence.json", "acceptance_evidence_sha256"),
        ("rollback-manifest.json", "rollback_manifest_sha256"),
    ):
        assert _sha(CONTRACT / artifact) == governance[field]


def test_review_queue_binding_is_typed_and_staged():
    payload = _load("review-binding.json")
    checked = core.validate_review_binding(payload)
    assert checked["canonicality"] == "STAGED_NOT_APPLIED"
    assert checked["identity_boundary"] == "AUDIT_LOCATOR_ONLY"
    assert len(checked["review_group_ids"]) == 43
    assert checked["approved_proposal_set_sha256"] == _sha(
        ROOT / "docs/planning/sgf_answer_repair_batch_001_proposal_snapshot.json"
    )


def test_acceptance_evidence_covers_all_surfaces_and_verdicts():
    payload = _load("acceptance-evidence.json")
    checked = core.validate_acceptance_evidence(
        payload,
        expected_candidate_sha256=CANDIDATE_SHA256,
        expected_record_count=54,
    )
    assert checked["summary"]["all_final_effective_match"] is True
    assert set(checked["summary"]["surfaces"]) == SURFACES
    assert all(
        row["owner_desired_verdict"] == row["final_effective_player_verdict"]
        and set(row["surfaces"]) == SURFACES
        for row in checked["records"]
    )


def test_repair_batch_and_mutation_audit_bind_exact_counts():
    batch = _load("repair-batch-manifest.json")
    audit = _load("mutation-audit.json")
    acceptance = _load("acceptance-evidence.json")
    assert batch["source_sha256"] == BASELINE_SHA256
    assert batch["candidate_sha256"] == CANDIDATE_SHA256
    assert batch["changed_record_count"] == 54
    assert batch["review_group_count"] == 43
    assert batch["excluded_record_count"] == 11
    assert batch["conflict_count"] == 3
    assert audit["source_sha256"] == BASELINE_SHA256
    assert audit["candidate_sha256"] == CANDIDATE_SHA256
    assert audit["changed_record_count"] == 54
    assert audit["review_group_count"] == 43
    assert audit["non_target_records_changed"] == 0
    assert audit["accepted_moves_changed"] == 0
    assert acceptance["candidate_sha256"] == batch["candidate_sha256"]


def test_immutable_source_provenance_fails_closed_on_expected_hash_drift():
    payload = _load("source-provenance.json")
    core.verify_source_provenance(payload, expected_sha256=BASELINE_SHA256, expected_record_count=41591)
    with pytest.raises(GovernanceError, match="source_bytes_sha256_mismatch|source_sha256_mismatch"):
        core.verify_source_provenance(payload, expected_sha256="0" * 64, expected_record_count=41591)


def test_review_binding_spoof_is_rejected():
    payload = copy.deepcopy(_load("review-binding.json"))
    payload["review_source_id"] = "0" * 64
    with pytest.raises(GovernanceError, match="review_binding_identity_hash_mismatch"):
        core.validate_review_binding(payload)


def test_acceptance_verdict_spoof_is_rejected():
    payload = copy.deepcopy(_load("acceptance-evidence.json"))
    payload["records"][0]["final_effective_player_verdict"] = ["A1"]
    with pytest.raises(GovernanceError, match="acceptance_verdict_mismatch"):
        core.validate_acceptance_evidence(
            payload,
            expected_candidate_sha256=CANDIDATE_SHA256,
            expected_record_count=54,
        )


def test_pr318_bundle_compatibility_against_real_candidate_when_available(tmp_path):
    candidate = Path(
        r"D:\go-website-sgf-answer-repair-batch-001-artifacts\content-release-phase2f-20260809T222000Z-4d13fa98\questions.repaired-candidate.b7b4eedf72a8.json"
    )
    if not candidate.is_file():
        pytest.skip("external byte-exact candidate evidence is not present")
    bundle = core.build_release_bundle(
        candidate=candidate,
        release_manifest=CONTRACT / "release-manifest.json",
        rollback_manifest=CONTRACT / "rollback-manifest.json",
        output_dir=tmp_path,
        expected_candidate_sha256=CANDIDATE_SHA256,
        expected_record_count=41591,
        expected_release_manifest_sha256=_sha(CONTRACT / "release-manifest.json"),
        expected_rollback_manifest_sha256=_sha(CONTRACT / "rollback-manifest.json"),
        baseline_sha256=BASELINE_SHA256,
        release_records=54,
        excluded_map_battle_records=11,
        source_provenance=CONTRACT / "source-provenance.json",
        review_binding=CONTRACT / "review-binding.json",
        repair_batch_manifest=CONTRACT / "repair-batch-manifest.json",
        mutation_audit=CONTRACT / "mutation-audit.json",
        acceptance_evidence=CONTRACT / "acceptance-evidence.json",
    )
    assert Path(bundle.compressed_path).is_file()
    assert bundle.acceptance_evidence_sha256 == _sha(CONTRACT / "acceptance-evidence.json")
