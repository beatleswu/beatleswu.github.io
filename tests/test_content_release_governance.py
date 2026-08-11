import json
import hashlib
import os
import shutil
import subprocess
from pathlib import Path

import pytest

import tools.content_release_core as core
from tools.content_release_core import (
    GovernanceError,
    LocalReleaseRegistry,
    PUBLISH_EXECUTION_GATE,
    ROLLBACK_EXECUTION_GATE,
    atomic_replace_verified,
    build_backup_bundle,
    build_rollback_proof,
    build_release_bundle,
    build_source_provenance,
    canonical_payload_sha256,
    deterministic_gzip,
    identify_json,
    publish_content,
    preflight_remote_assets,
    rollback_content,
    sha256_file,
    simulated_directory_fsync,
    verify_backup_bundle,
    verify_publish_gates,
    verify_release_round_trip,
    validate_acceptance_evidence,
    validate_rollback_proof,
    validate_review_binding,
    write_round_trip_receipt,
)


TAG = "content-baseline-20260810-test"


def _write_json(path: Path, payload) -> Path:
    path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    return path


def _write_manifest(path: Path, payload=None) -> Path:
    path.write_text(json.dumps(payload or {"schema_version": "test"}), encoding="utf-8")
    return path


def _fixture(tmp_path: Path):
    baseline = _write_json(
        tmp_path / "baseline.json",
        [{"id": 1, "answer": "A"}, {"id": 2, "answer": "B"}],
    )
    candidate = _write_json(
        tmp_path / "candidate.json",
        [{"id": 1, "answer": "B"}, {"id": 2, "answer": "B"}],
    )
    baseline_identity = identify_json(baseline)
    candidate_identity = identify_json(candidate)
    source_provenance = build_source_provenance(baseline)
    group_id = "1" * 64
    review_binding_payload = {
        "schema_version": "1.0",
        "authority": "OWNER_APPROVED_REPAIR_PROPOSAL",
        "canonicality": "STAGED_NOT_APPLIED",
        "identity_boundary": "AUDIT_LOCATOR_ONLY",
        "review_source_id": "2" * 64,
        "source_snapshot_sha256": baseline_identity.sha256,
        "detector_manifest_sha256": "3" * 64,
        "validation_pack_id": "4" * 64,
        "approved_proposal_set_sha256": "5" * 64,
        "review_group_ids": [group_id],
        "owner_authority": "owner:test",
        "proposals": [{
            "authority": "OWNER_APPROVED_REPAIR_PROPOSAL",
            "canonicality": "STAGED_NOT_APPLIED",
            "identity_boundary": "AUDIT_LOCATOR_ONLY",
        }],
    }
    review_binding_payload["binding_identity_sha256"] = canonical_payload_sha256(review_binding_payload)
    review_binding = _write_json(tmp_path / "review-binding.json", review_binding_payload)
    review_binding_sha256 = sha256_file(review_binding)
    evidence_artifact_sha256 = sha256_file(baseline)
    acceptance_payload = {
        "schema_version": "1.0",
        "authority": "EXTERNAL_ACCEPTANCE_RUNNER",
        "canonicality": "VERIFICATION_EVIDENCE_ONLY",
        "candidate_sha256": candidate_identity.sha256,
        "records": [{
            "record_index": 0,
            "legacy_question_id": 1,
            "content_sha256": candidate_identity.sha256,
            "owner_desired_verdict": "B",
            "final_effective_player_verdict": "B",
            "source_precedence_used": ["native_sgf"],
            "accepted_moves_influence": False,
            "native_sgf_influence": True,
            "historical_katago_best_move_influence": False,
            "surfaces": {
                surface: {"pass": True, "match": True, "evidence_artifact_sha256": evidence_artifact_sha256}
                for surface in (
                    "sgf_engine_native",
                    "rating_test_server",
                    "map_battle_server",
                    "main_practice_client",
                    "daily_challenge_client",
                    "friend_challenge_client_then_server_trust",
                )
            },
            "evidence_artifact_sha256": evidence_artifact_sha256,
        }],
        "summary": {
            "records_validated": 1,
            "all_final_effective_match": True,
            "surfaces": [
                "sgf_engine_native",
                "rating_test_server",
                "map_battle_server",
                "main_practice_client",
                "daily_challenge_client",
                "friend_challenge_client_then_server_trust",
            ],
        },
    }
    acceptance_payload["evidence_identity_sha256"] = canonical_payload_sha256(acceptance_payload)
    acceptance_evidence = _write_json(tmp_path / "acceptance-evidence.json", acceptance_payload)
    acceptance_sha256 = sha256_file(acceptance_evidence)
    mutation_audit_payload = {
        "schema_version": "1.0",
        "source_sha256": baseline_identity.sha256,
        "candidate_sha256": candidate_identity.sha256,
        "changed_record_count": 1,
        "review_group_count": 1,
        "non_target_records_changed": 0,
        "accepted_moves_changed": 0,
    }
    mutation_audit = _write_json(tmp_path / "mutation-audit.json", mutation_audit_payload)
    mutation_audit_sha256 = sha256_file(mutation_audit)
    repair_batch_payload = {
        "schema_version": "1.0",
        "source_sha256": baseline_identity.sha256,
        "candidate_sha256": candidate_identity.sha256,
        "review_binding_sha256": review_binding_sha256,
        "mutation_audit_sha256": mutation_audit_sha256,
        "acceptance_evidence_sha256": acceptance_sha256,
        "changed_record_count": 1,
        "review_group_count": 1,
    }
    repair_batch_manifest = _write_json(tmp_path / "repair-batch-manifest.json", repair_batch_payload)
    repair_batch_sha256 = sha256_file(repair_batch_manifest)
    rollback_manifest = _write_manifest(tmp_path / "rollback.json", {
        "schema_version": "1.0",
        "rollback_governance": {
            "previous_sha256": baseline_identity.sha256,
            "candidate_sha256": candidate_identity.sha256,
            "record_count": baseline_identity.record_count,
            "restore_target": "questions.json",
            "post_rollback": {
                "sha256": baseline_identity.sha256,
                "size_bytes": baseline_identity.size_bytes,
                "record_count": baseline_identity.record_count,
            },
        },
    })
    rollback_sha256 = sha256_file(rollback_manifest)
    allowed_assets = [
        "questions.repaired-candidate.json.gz",
        "content-release-manifest.json",
        "content-rollback-manifest.json",
        acceptance_evidence.name,
        "content-registry-entry.json",
        "SHA256SUMS.txt",
    ]
    release_manifest = _write_manifest(tmp_path / "release.json", {
        "schema_version": "1.0",
        "source_baseline_sha256": baseline_identity.sha256,
        "pre_mutation_artifact": {
            "sha256": baseline_identity.sha256,
            "size_bytes": baseline_identity.size_bytes,
            "record_count": baseline_identity.record_count,
        },
        "repaired_candidate_artifact": {
            "sha256": candidate_identity.sha256,
            "size_bytes": candidate_identity.size_bytes,
            "record_count": candidate_identity.record_count,
        },
        "release_governance": {
            "source_provenance": source_provenance,
            "source_identity_sha256": source_provenance["source_identity_sha256"],
            "review_binding_sha256": review_binding_sha256,
            "repair_batch_manifest_sha256": repair_batch_sha256,
            "mutation_audit_sha256": mutation_audit_sha256,
            "acceptance_evidence_sha256": acceptance_sha256,
            "rollback_manifest_sha256": rollback_sha256,
            "changed_record_count": 1,
            "review_group_count": 1,
            "excluded_record_count": 11,
            "allowed_asset_names": allowed_assets,
        },
    })
    bundle = build_backup_bundle(
        source=baseline,
        output_dir=tmp_path / "bundle",
        expected_sha256=baseline_identity.sha256,
        expected_record_count=baseline_identity.record_count,
        artifact_role="pre_mutation_baseline",
        source_environment="synthetic",
        source_path_label="synthetic/baseline.json",
        created_at_utc="2026-08-10T00:00:00Z",
        source_provenance=source_provenance,
    )
    registry = LocalReleaseRegistry(tmp_path / "remote", visibility="PRIVATE", tag=TAG)
    registry.upload(
        [Path(bundle.compressed_path), Path(bundle.manifest_path), Path(bundle.checksums_path)]
    )
    receipt = verify_release_round_trip(
        registry=registry,
        source=baseline,
        local_compressed=Path(bundle.compressed_path),
        expected_source_sha256=baseline_identity.sha256,
        expected_record_count=baseline_identity.record_count,
        expected_tag=TAG,
        download_dir=tmp_path / "download",
    )
    receipt_path = tmp_path / "receipt.json"
    write_round_trip_receipt(receipt_path, receipt)
    return {
        "baseline": baseline,
        "candidate": candidate,
        "original_candidate": candidate,
        "release_manifest": release_manifest,
        "rollback_manifest": rollback_manifest,
        "source_provenance": source_provenance,
        "review_binding": review_binding,
        "repair_batch_manifest": repair_batch_manifest,
        "mutation_audit": mutation_audit,
        "acceptance_evidence": acceptance_evidence,
        "repair_batch_sha256": repair_batch_sha256,
        "baseline_identity": baseline_identity,
        "candidate_identity": candidate_identity,
        "bundle": bundle,
        "registry": registry,
        "receipt": receipt_path,
    }


def _publish_kwargs(fixture, live: Path):
    receipt_payload = json.loads(fixture["receipt"].read_text(encoding="utf-8"))
    proof = build_rollback_proof(
        previous=fixture["baseline"],
        candidate=fixture["original_candidate"],
        rollback_manifest=fixture["rollback_manifest"],
        restore_target=live,
        local_simulation_id="test-simulation",
        remote_predecessor={
            "source_sha256": fixture["baseline_identity"].sha256,
            "asset_sha256": receipt_payload["remote_asset_sha256"],
            "receipt_sha256": sha256_file(fixture["receipt"]),
        },
        normalized_rollback_inputs={"live": str(live.resolve()), "candidate": str(fixture["candidate"].resolve())},
    )
    return {
        "live": live,
        "candidate": fixture["candidate"],
        "local_baseline_backup": Path(fixture["bundle"].compressed_path),
        "offsite_receipt": fixture["receipt"],
        "release_manifest": fixture["release_manifest"],
        "expected_live_sha256": fixture["baseline_identity"].sha256,
        "expected_candidate_sha256": fixture["candidate_identity"].sha256,
        "expected_release_manifest_sha256": sha256_file(fixture["release_manifest"]),
        "expected_record_count": fixture["baseline_identity"].record_count,
        "expected_backup_tag": TAG,
        "rollback_manifest": fixture["rollback_manifest"],
        "rollback_proof": proof,
        "source_provenance": fixture["source_provenance"],
        "review_binding": fixture["review_binding"],
        "repair_batch_manifest": fixture["repair_batch_manifest"],
        "mutation_audit": fixture["mutation_audit"],
        "acceptance_evidence": fixture["acceptance_evidence"],
    }


def test_deterministic_gzip_and_backup_manifest(tmp_path):
    source = _write_json(tmp_path / "source.json", [{"id": 1}])
    one = tmp_path / "one.gz"
    two = tmp_path / "two.gz"
    assert deterministic_gzip(source, one) == deterministic_gzip(source, two)
    assert one.read_bytes() == two.read_bytes()

    identity = identify_json(source)
    bundle = build_backup_bundle(
        source=source,
        output_dir=tmp_path / "bundle",
        expected_sha256=identity.sha256,
        expected_record_count=1,
        artifact_role="baseline",
        source_environment="synthetic",
        source_path_label="synthetic",
        created_at_utc="2026-08-10T00:00:00Z",
    )
    verified = verify_backup_bundle(tmp_path / "bundle")
    assert verified.source.sha256 == identity.sha256
    assert Path(bundle.checksums_path).read_text(encoding="ascii").count("\n") == 2


def test_release_bundle_preserves_locked_manifests(tmp_path):
    fixture = _fixture(tmp_path)
    result = build_release_bundle(
        candidate=fixture["candidate"],
        release_manifest=fixture["release_manifest"],
        rollback_manifest=fixture["rollback_manifest"],
        output_dir=tmp_path / "release-bundle",
        expected_candidate_sha256=fixture["candidate_identity"].sha256,
        expected_record_count=2,
        expected_release_manifest_sha256=sha256_file(fixture["release_manifest"]),
        expected_rollback_manifest_sha256=sha256_file(fixture["rollback_manifest"]),
        baseline_sha256=fixture["baseline_identity"].sha256,
        release_records=1,
        excluded_map_battle_records=11,
        created_at_utc="2026-08-10T00:00:00Z",
        source_provenance=fixture["source_provenance"],
        review_binding=fixture["review_binding"],
        repair_batch_manifest=fixture["repair_batch_manifest"],
        mutation_audit=fixture["mutation_audit"],
        acceptance_evidence=fixture["acceptance_evidence"],
    )
    assert sha256_file(Path(result.release_manifest_path)) == sha256_file(fixture["release_manifest"])
    assert sha256_file(Path(result.rollback_manifest_path)) == sha256_file(fixture["rollback_manifest"])


def test_triple_hash_gate_passes_only_after_redownload(tmp_path):
    fixture = _fixture(tmp_path)
    receipt = fixture["receipt"]
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert payload["offsite_backup_verified"] is True
    assert len(
        {
            payload["source_uncompressed_sha256"],
            payload["local_uncompressed_sha256"],
            payload["remote_uncompressed_sha256"],
        }
    ) == 1


@pytest.mark.parametrize("visibility", ["PUBLIC", "INTERNAL", ""])
def test_wrong_repo_visibility_fails_closed(tmp_path, visibility):
    fixture = _fixture(tmp_path)
    registry = LocalReleaseRegistry(tmp_path / "other", visibility=visibility, tag=TAG)
    registry.upload([Path(fixture["bundle"].compressed_path)])
    with pytest.raises(GovernanceError, match="visibility"):
        verify_release_round_trip(
            registry=registry,
            source=fixture["baseline"],
            local_compressed=Path(fixture["bundle"].compressed_path),
            expected_source_sha256=fixture["baseline_identity"].sha256,
            expected_record_count=2,
            expected_tag=TAG,
            download_dir=tmp_path / "bad-download",
        )


def test_wrong_release_tag_fails_closed(tmp_path):
    fixture = _fixture(tmp_path)
    with pytest.raises(GovernanceError, match="wrong_release_tag"):
        verify_release_round_trip(
            registry=fixture["registry"],
            source=fixture["baseline"],
            local_compressed=Path(fixture["bundle"].compressed_path),
            expected_source_sha256=fixture["baseline_identity"].sha256,
            expected_record_count=2,
            expected_tag="wrong-tag",
            download_dir=tmp_path / "bad-download",
        )


def test_missing_release_asset_fails_closed(tmp_path):
    fixture = _fixture(tmp_path)
    remote_asset = fixture["registry"].release_dir / Path(fixture["bundle"].compressed_path).name
    remote_asset.unlink()
    with pytest.raises(GovernanceError, match="missing_release_asset"):
        verify_release_round_trip(
            registry=fixture["registry"],
            source=fixture["baseline"],
            local_compressed=Path(fixture["bundle"].compressed_path),
            expected_source_sha256=fixture["baseline_identity"].sha256,
            expected_record_count=2,
            expected_tag=TAG,
            download_dir=tmp_path / "bad-download",
        )


def test_remote_redownload_hash_mismatch_fails_closed(tmp_path):
    fixture = _fixture(tmp_path)
    remote_asset = fixture["registry"].release_dir / Path(fixture["bundle"].compressed_path).name
    remote_asset.write_bytes(remote_asset.read_bytes() + b"corruption")
    with pytest.raises(GovernanceError, match="remote_redownload"):
        verify_release_round_trip(
            registry=fixture["registry"],
            source=fixture["baseline"],
            local_compressed=Path(fixture["bundle"].compressed_path),
            expected_source_sha256=fixture["baseline_identity"].sha256,
            expected_record_count=2,
            expected_tag=TAG,
            download_dir=tmp_path / "bad-download",
        )


def test_malformed_json_fails_closed(tmp_path):
    malformed = tmp_path / "malformed.json"
    malformed.write_text("[{", encoding="utf-8")
    with pytest.raises(GovernanceError, match="malformed_or_unreadable_json"):
        identify_json(malformed)


def test_publish_dry_run_never_replaces_live(tmp_path):
    fixture = _fixture(tmp_path)
    live = tmp_path / "live.json"
    shutil.copyfile(fixture["baseline"], live)
    before = live.read_bytes()
    result = publish_content(**_publish_kwargs(fixture, live), execute=False, owner_gate="")
    assert result["mode"] == "dry-run"
    assert live.read_bytes() == before


def test_wrong_live_baseline_hash_fails_closed(tmp_path):
    fixture = _fixture(tmp_path)
    live = _write_json(tmp_path / "live.json", [{"id": 99}, {"id": 2}])
    with pytest.raises(GovernanceError, match="live_baseline_sha256_mismatch"):
        verify_publish_gates(**_publish_kwargs(fixture, live))


def test_wrong_live_record_count_fails_closed(tmp_path):
    fixture = _fixture(tmp_path)
    live = _write_json(tmp_path / "live.json", [{"id": 1}])
    kwargs = _publish_kwargs(fixture, live)
    kwargs["expected_live_sha256"] = sha256_file(live)
    with pytest.raises(GovernanceError, match="live_baseline_record_count_mismatch"):
        verify_publish_gates(**kwargs)


def test_wrong_candidate_hash_fails_closed(tmp_path):
    fixture = _fixture(tmp_path)
    live = tmp_path / "live.json"
    shutil.copyfile(fixture["baseline"], live)
    fixture["candidate"].write_text('[{"id":1}]', encoding="utf-8")
    with pytest.raises(GovernanceError, match="candidate_sha256_mismatch"):
        verify_publish_gates(**_publish_kwargs(fixture, live))


def test_wrong_candidate_record_count_fails_closed(tmp_path):
    fixture = _fixture(tmp_path)
    live = tmp_path / "live.json"
    shutil.copyfile(fixture["baseline"], live)
    candidate = _write_json(tmp_path / "wrong-count.json", [{"id": 1}])
    fixture["candidate"] = candidate
    fixture["candidate_identity"] = identify_json(candidate)
    with pytest.raises(GovernanceError, match="candidate_record_count_mismatch"):
        verify_publish_gates(**_publish_kwargs(fixture, live))


def test_wrong_release_manifest_hash_fails_closed(tmp_path):
    fixture = _fixture(tmp_path)
    live = tmp_path / "live.json"
    shutil.copyfile(fixture["baseline"], live)
    kwargs = _publish_kwargs(fixture, live)
    kwargs["expected_release_manifest_sha256"] = "0" * 64
    with pytest.raises(GovernanceError, match="release_manifest_sha256_mismatch"):
        verify_publish_gates(**kwargs)


def test_malformed_release_manifest_fails_closed(tmp_path):
    fixture = _fixture(tmp_path)
    live = tmp_path / "live.json"
    shutil.copyfile(fixture["baseline"], live)
    fixture["release_manifest"].write_text("{", encoding="utf-8")
    kwargs = _publish_kwargs(fixture, live)
    kwargs["expected_release_manifest_sha256"] = sha256_file(fixture["release_manifest"])
    with pytest.raises(GovernanceError, match="malformed_release_manifest"):
        verify_publish_gates(**kwargs)


def test_missing_baseline_backup_fails_closed(tmp_path):
    fixture = _fixture(tmp_path)
    live = tmp_path / "live.json"
    shutil.copyfile(fixture["baseline"], live)
    kwargs = _publish_kwargs(fixture, live)
    kwargs["local_baseline_backup"] = tmp_path / "missing.gz"
    with pytest.raises(GovernanceError, match="missing_baseline_backup"):
        verify_publish_gates(**kwargs)


def test_wrong_baseline_backup_hash_fails_closed(tmp_path):
    fixture = _fixture(tmp_path)
    live = tmp_path / "live.json"
    shutil.copyfile(fixture["baseline"], live)
    wrong = _write_json(tmp_path / "wrong-backup.json", [{"id": 1}, {"id": 2}])
    kwargs = _publish_kwargs(fixture, live)
    kwargs["local_baseline_backup"] = wrong
    with pytest.raises(GovernanceError, match="baseline_backup_sha256_mismatch"):
        verify_publish_gates(**kwargs)


def test_publish_requires_exact_owner_gate(tmp_path):
    fixture = _fixture(tmp_path)
    live = tmp_path / "live.json"
    shutil.copyfile(fixture["baseline"], live)
    with pytest.raises(GovernanceError, match="not_authorized"):
        publish_content(**_publish_kwargs(fixture, live), execute=True, owner_gate="wrong")
    assert sha256_file(live) == fixture["baseline_identity"].sha256


def test_stage_copy_corruption_fails_before_replace(tmp_path):
    fixture = _fixture(tmp_path)
    live = tmp_path / "live.json"
    shutil.copyfile(fixture["baseline"], live)

    def corrupt(_source, stage):
        _write_json(stage, [{"corrupted": True}, {"id": 2}])

    with pytest.raises(GovernanceError, match="staged_candidate_sha256_mismatch"):
        atomic_replace_verified(
            source=fixture["candidate"],
            live=live,
            expected_current_sha256=fixture["baseline_identity"].sha256,
            expected_current_record_count=2,
            expected_source_sha256=fixture["candidate_identity"].sha256,
            expected_source_record_count=2,
            directory_fsync=simulated_directory_fsync,
            copy_and_fsync=corrupt,
        )
    assert sha256_file(live) == fixture["baseline_identity"].sha256


def test_file_fsync_or_stage_failure_fails_closed(tmp_path):
    fixture = _fixture(tmp_path)
    live = tmp_path / "live.json"
    shutil.copyfile(fixture["baseline"], live)

    def fail_stage(_source, _stage):
        raise OSError("injected fsync failure")

    with pytest.raises(GovernanceError, match="stage_copy_or_file_fsync_failed"):
        atomic_replace_verified(
            source=fixture["candidate"],
            live=live,
            expected_current_sha256=fixture["baseline_identity"].sha256,
            expected_current_record_count=2,
            expected_source_sha256=fixture["candidate_identity"].sha256,
            expected_source_record_count=2,
            directory_fsync=simulated_directory_fsync,
            copy_and_fsync=fail_stage,
        )
    assert sha256_file(live) == fixture["baseline_identity"].sha256


def test_atomic_replace_failure_leaves_live_unchanged(tmp_path):
    fixture = _fixture(tmp_path)
    live = tmp_path / "live.json"
    shutil.copyfile(fixture["baseline"], live)

    def fail_replace(_source, _destination):
        raise OSError("injected replace failure")

    with pytest.raises(GovernanceError, match="atomic_replace_failed"):
        atomic_replace_verified(
            source=fixture["candidate"],
            live=live,
            expected_current_sha256=fixture["baseline_identity"].sha256,
            expected_current_record_count=2,
            expected_source_sha256=fixture["candidate_identity"].sha256,
            expected_source_record_count=2,
            directory_fsync=simulated_directory_fsync,
            replace=fail_replace,
        )
    assert sha256_file(live) == fixture["baseline_identity"].sha256


def test_directory_fsync_failure_is_reported(tmp_path):
    fixture = _fixture(tmp_path)
    live = tmp_path / "live.json"
    shutil.copyfile(fixture["baseline"], live)

    def fail_directory(_path):
        raise OSError("injected directory fsync failure")

    with pytest.raises(GovernanceError, match="directory_fsync_failed"):
        atomic_replace_verified(
            source=fixture["candidate"],
            live=live,
            expected_current_sha256=fixture["baseline_identity"].sha256,
            expected_current_record_count=2,
            expected_source_sha256=fixture["candidate_identity"].sha256,
            expected_source_record_count=2,
            directory_fsync=fail_directory,
        )


def test_post_replace_verification_failure_is_reported(tmp_path, monkeypatch):
    fixture = _fixture(tmp_path)
    live = tmp_path / "live.json"
    shutil.copyfile(fixture["baseline"], live)
    real_verify = core.verify_json_identity

    def injected(path, **kwargs):
        if kwargs.get("label") == "post_replace":
            raise GovernanceError("post_replace_verification_failure")
        return real_verify(path, **kwargs)

    monkeypatch.setattr(core, "verify_json_identity", injected)
    with pytest.raises(GovernanceError, match="post_replace_verification_failure"):
        atomic_replace_verified(
            source=fixture["candidate"],
            live=live,
            expected_current_sha256=fixture["baseline_identity"].sha256,
            expected_current_record_count=2,
            expected_source_sha256=fixture["candidate_identity"].sha256,
            expected_source_record_count=2,
            directory_fsync=simulated_directory_fsync,
        )


def test_publish_then_rollback_is_byte_exact(tmp_path):
    fixture = _fixture(tmp_path)
    live = tmp_path / "live.json"
    shutil.copyfile(fixture["baseline"], live)
    original = live.read_bytes()
    published = publish_content(
        **_publish_kwargs(fixture, live),
        execute=True,
        owner_gate=PUBLISH_EXECUTION_GATE,
        directory_fsync=simulated_directory_fsync,
    )
    assert published["final"]["sha256"] == fixture["candidate_identity"].sha256
    rolled_back = rollback_content(
        live=live,
        baseline=fixture["baseline"],
        rollback_manifest=fixture["rollback_manifest"],
        expected_current_sha256=fixture["candidate_identity"].sha256,
        expected_baseline_sha256=fixture["baseline_identity"].sha256,
        expected_rollback_manifest_sha256=sha256_file(fixture["rollback_manifest"]),
        expected_record_count=2,
        rollback_proof=_publish_kwargs(fixture, live)["rollback_proof"],
        execute=True,
        owner_gate=ROLLBACK_EXECUTION_GATE,
        directory_fsync=simulated_directory_fsync,
    )
    assert rolled_back["final"]["sha256"] == fixture["baseline_identity"].sha256
    assert live.read_bytes() == original


def test_rollback_unexpected_current_hash_fails_closed(tmp_path):
    fixture = _fixture(tmp_path)
    live = _write_json(tmp_path / "live.json", [{"id": "unexpected"}, {"id": 2}])
    with pytest.raises(GovernanceError, match="rollback_current_sha256_mismatch"):
        rollback_content(
            live=live,
            baseline=fixture["baseline"],
            rollback_manifest=fixture["rollback_manifest"],
            expected_current_sha256=fixture["candidate_identity"].sha256,
            expected_baseline_sha256=fixture["baseline_identity"].sha256,
            expected_rollback_manifest_sha256=sha256_file(fixture["rollback_manifest"]),
            expected_record_count=2,
            rollback_proof=_publish_kwargs(fixture, live)["rollback_proof"],
            execute=False,
            owner_gate="",
        )


def test_corrupted_rollback_artifact_fails_closed(tmp_path):
    fixture = _fixture(tmp_path)
    live = tmp_path / "live.json"
    shutil.copyfile(fixture["candidate"], live)
    corrupted = _write_json(tmp_path / "corrupted-baseline.json", [{"id": 1}, {"id": 2}])
    with pytest.raises(GovernanceError, match="rollback_artifact_sha256_mismatch"):
        rollback_content(
            live=live,
            baseline=corrupted,
            rollback_manifest=fixture["rollback_manifest"],
            expected_current_sha256=fixture["candidate_identity"].sha256,
            expected_baseline_sha256=fixture["baseline_identity"].sha256,
            expected_rollback_manifest_sha256=sha256_file(fixture["rollback_manifest"]),
            expected_record_count=2,
            rollback_proof=_publish_kwargs(fixture, live)["rollback_proof"],
            execute=False,
            owner_gate="",
        )


def test_source_provenance_spoof_rejected(tmp_path):
    source = _write_json(tmp_path / "source.json", [{"id": 1}])
    provenance = build_source_provenance(source)
    spoofed = dict(provenance)
    spoofed["source_sha256"] = "0" * 64
    spoofed["source_identity_sha256"] = canonical_payload_sha256(spoofed, without="source_identity_sha256")
    with pytest.raises(GovernanceError, match="source_bytes_sha256_mismatch"):
        core.verify_source_provenance(spoofed, source=source)


def test_source_provenance_identity_hash_spoof_rejected(tmp_path):
    source = _write_json(tmp_path / "source.json", [{"id": 1}])
    provenance = build_source_provenance(source)
    provenance["source_identity_sha256"] = "0" * 64
    with pytest.raises(GovernanceError, match="source_identity_hash_mismatch"):
        core.verify_source_provenance(provenance, source=source)


def test_mutable_external_snapshot_fails_closed(tmp_path):
    source = _write_json(tmp_path / "source.json", [{"id": 1}])
    with pytest.raises(GovernanceError, match="source_status_not_verifiable|external_snapshot_not_immutable"):
        build_source_provenance(
            source,
            source_kind="immutable_snapshot",
            source_commit_or_snapshot_id="snapshot-1",
            source_receipt_sha256="1" * 64,
            source_status="MUTABLE_LABEL",
        )


def test_wrong_git_ancestry_fails_closed(tmp_path):
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    repo_id = subprocess.run(
        ["git", "config", "--get", "remote.origin.url"], capture_output=True, text=True, check=True
    ).stdout.strip().split("github.com/")[-1].removesuffix(".git")
    source_path = "tools/content_release_core.py"
    blob_sha = subprocess.run(
        ["git", "rev-parse", f"{commit}:{source_path}"], capture_output=True, text=True, check=True
    ).stdout.strip()
    raw = subprocess.run(
        ["git", "cat-file", "blob", blob_sha], capture_output=True, check=True
    ).stdout
    provenance = {
        "source_kind": "git_blob",
        "source_repo_id": repo_id,
        "source_commit_or_snapshot_id": commit,
        "source_path": source_path,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "source_size_bytes": len(raw),
        "source_record_count": 0,
        "source_status": "GIT_COMMIT_BYTE_VERIFIED",
    }
    provenance["source_identity_sha256"] = canonical_payload_sha256(provenance)
    with pytest.raises(GovernanceError, match="source_commit_not_ancestral"):
        core.verify_source_provenance(provenance, repo_root=Path.cwd(), current_ref="origin/master")


def test_semantic_manifest_batch_count_mismatch_fails_closed(tmp_path):
    fixture = _fixture(tmp_path)
    payload = json.loads(fixture["release_manifest"].read_text(encoding="utf-8"))
    payload["release_governance"]["changed_record_count"] = 2
    changed = _write_manifest(tmp_path / "bad-release.json", payload)
    with pytest.raises(GovernanceError, match="release_governance_changed_record_count_mismatch"):
        build_release_bundle(
            candidate=fixture["candidate"],
            release_manifest=changed,
            rollback_manifest=fixture["rollback_manifest"],
            output_dir=tmp_path / "bad-release-bundle",
            expected_candidate_sha256=fixture["candidate_identity"].sha256,
            expected_record_count=2,
            expected_release_manifest_sha256=sha256_file(changed),
            expected_rollback_manifest_sha256=sha256_file(fixture["rollback_manifest"]),
            baseline_sha256=fixture["baseline_identity"].sha256,
            release_records=1,
            excluded_map_battle_records=11,
            source_provenance=fixture["source_provenance"],
            review_binding=fixture["review_binding"],
            repair_batch_manifest=fixture["repair_batch_manifest"],
            mutation_audit=fixture["mutation_audit"],
            acceptance_evidence=fixture["acceptance_evidence"],
        )


def test_review_binding_authority_mismatch_fails_closed(tmp_path):
    fixture = _fixture(tmp_path)
    payload = json.loads(fixture["review_binding"].read_text(encoding="utf-8"))
    payload["authority"] = "CALLER_ASSERTED"
    payload["binding_identity_sha256"] = canonical_payload_sha256(payload, without="binding_identity_sha256")
    with pytest.raises(GovernanceError, match="review_binding_authority_mismatch"):
        validate_review_binding(payload)


def test_acceptance_missing_surface_fails_closed(tmp_path):
    fixture = _fixture(tmp_path)
    payload = json.loads(fixture["acceptance_evidence"].read_text(encoding="utf-8"))
    payload["records"][0]["surfaces"].pop("daily_challenge_client")
    payload["evidence_identity_sha256"] = canonical_payload_sha256(payload, without="evidence_identity_sha256")
    with pytest.raises(GovernanceError, match="acceptance_surface_set_mismatch"):
        validate_acceptance_evidence(payload, expected_candidate_sha256=fixture["candidate_identity"].sha256)


def test_acceptance_verdict_mismatch_fails_closed(tmp_path):
    fixture = _fixture(tmp_path)
    payload = json.loads(fixture["acceptance_evidence"].read_text(encoding="utf-8"))
    payload["records"][0]["final_effective_player_verdict"] = "W"
    payload["evidence_identity_sha256"] = canonical_payload_sha256(payload, without="evidence_identity_sha256")
    with pytest.raises(GovernanceError, match="acceptance_verdict_mismatch"):
        validate_acceptance_evidence(payload, expected_candidate_sha256=fixture["candidate_identity"].sha256)


def test_acceptance_evidence_hash_mismatch_fails_closed(tmp_path):
    fixture = _fixture(tmp_path)
    payload = json.loads(fixture["acceptance_evidence"].read_text(encoding="utf-8"))
    payload["evidence_identity_sha256"] = "0" * 64
    with pytest.raises(GovernanceError, match="acceptance_evidence_identity_hash_mismatch"):
        validate_acceptance_evidence(payload, expected_candidate_sha256=fixture["candidate_identity"].sha256)


def test_remote_predecessor_drift_fails_closed(tmp_path):
    fixture = _fixture(tmp_path)
    remote_asset = fixture["registry"].release_dir / Path(fixture["bundle"].compressed_path).name
    remote_asset.write_bytes(remote_asset.read_bytes() + b"drift")
    paths = [Path(fixture["bundle"].compressed_path), Path(fixture["bundle"].manifest_path), Path(fixture["bundle"].checksums_path)]
    with pytest.raises(GovernanceError, match="remote_asset_predecessor_drift"):
        preflight_remote_assets(fixture["registry"], paths)


def test_remote_asset_inventory_drift_fails_closed(tmp_path):
    fixture = _fixture(tmp_path)
    (fixture["registry"].release_dir / "unexpected.asset").write_bytes(b"unexpected")
    paths = [Path(fixture["bundle"].compressed_path), Path(fixture["bundle"].manifest_path), Path(fixture["bundle"].checksums_path)]
    with pytest.raises(GovernanceError, match="remote_asset_inventory_drift"):
        preflight_remote_assets(fixture["registry"], paths)


def test_existing_remote_asset_cannot_be_overwritten(tmp_path):
    fixture = _fixture(tmp_path)
    changed = tmp_path / Path(fixture["bundle"].compressed_path).name
    changed.write_bytes(Path(fixture["bundle"].compressed_path).read_bytes() + b"changed")
    paths = [changed, Path(fixture["bundle"].manifest_path), Path(fixture["bundle"].checksums_path)]
    with pytest.raises(GovernanceError, match="remote_asset_predecessor_drift"):
        core.upload_immutable_release(fixture["registry"], paths)


def test_publish_requires_rollback_proof(tmp_path):
    fixture = _fixture(tmp_path)
    live = tmp_path / "live.json"
    shutil.copyfile(fixture["baseline"], live)
    kwargs = _publish_kwargs(fixture, live)
    kwargs.pop("rollback_proof")
    with pytest.raises(GovernanceError, match="rollback_proof_missing"):
        publish_content(**kwargs, execute=False, owner_gate="")


def test_rollback_proof_hash_mismatch_fails_closed(tmp_path):
    fixture = _fixture(tmp_path)
    live = tmp_path / "live.json"
    shutil.copyfile(fixture["baseline"], live)
    proof = _publish_kwargs(fixture, live)["rollback_proof"]
    proof["proof_sha256"] = "0" * 64
    with pytest.raises(GovernanceError, match="rollback_proof_hash_mismatch"):
        validate_rollback_proof(
            proof,
            live=live,
            baseline=fixture["baseline"],
            candidate=fixture["candidate"],
            rollback_manifest=fixture["rollback_manifest"],
        )


def test_rollback_postcheck_mismatch_fails_closed(tmp_path):
    fixture = _fixture(tmp_path)
    live = tmp_path / "live.json"
    shutil.copyfile(fixture["baseline"], live)
    proof = _publish_kwargs(fixture, live)["rollback_proof"]
    proof["expected_post_rollback"]["size_bytes"] += 1
    proof["proof_sha256"] = canonical_payload_sha256(proof, without="proof_sha256")
    with pytest.raises(GovernanceError, match="rollback_proof_postcheck_mismatch"):
        validate_rollback_proof(
            proof,
            live=live,
            baseline=fixture["baseline"],
            candidate=fixture["candidate"],
            rollback_manifest=fixture["rollback_manifest"],
        )


def test_rollback_remote_predecessor_mismatch_fails_closed(tmp_path):
    fixture = _fixture(tmp_path)
    live = tmp_path / "live.json"
    live.write_bytes(fixture["baseline"].read_bytes())
    proof = _publish_kwargs(fixture, live)["rollback_proof"]
    proof["remote_predecessor"]["asset_sha256"] = "f" * 64
    proof["proof_sha256"] = canonical_payload_sha256(proof, without="proof_sha256")
    kwargs = _publish_kwargs(fixture, live)
    kwargs["rollback_proof"] = proof
    with pytest.raises(GovernanceError, match="rollback_proof_remote_predecessor_mismatch"):
        verify_publish_gates(**kwargs)


def test_source_record_count_spoof_rejected(tmp_path):
    source = _write_json(tmp_path / "source.json", [{"id": 1}])
    provenance = build_source_provenance(source)
    provenance["source_record_count"] = 2
    provenance["source_identity_sha256"] = canonical_payload_sha256(provenance, without="source_identity_sha256")
    with pytest.raises(GovernanceError, match="source_record_count_mismatch"):
        core.verify_source_provenance(provenance, source=source)


def test_acceptance_candidate_identity_mismatch_rejected(tmp_path):
    fixture = _fixture(tmp_path)
    payload = json.loads(fixture["acceptance_evidence"].read_text(encoding="utf-8"))
    payload["candidate_sha256"] = "0" * 64
    payload["evidence_identity_sha256"] = canonical_payload_sha256(payload, without="evidence_identity_sha256")
    with pytest.raises(GovernanceError, match="acceptance_evidence_candidate_sha256_mismatch"):
        validate_acceptance_evidence(payload, expected_candidate_sha256=fixture["candidate_identity"].sha256)


def test_repair_batch_candidate_binding_mismatch_rejected(tmp_path):
    fixture = _fixture(tmp_path)
    bad_batch_payload = json.loads(fixture["repair_batch_manifest"].read_text(encoding="utf-8"))
    bad_batch_payload["candidate_sha256"] = "0" * 64
    bad_batch = _write_json(tmp_path / "bad-repair-batch.json", bad_batch_payload)
    release_payload = json.loads(fixture["release_manifest"].read_text(encoding="utf-8"))
    release_payload["release_governance"]["repair_batch_manifest_sha256"] = sha256_file(bad_batch)
    changed_release = _write_manifest(tmp_path / "bad-binding-release.json", release_payload)
    with pytest.raises(GovernanceError, match="repair_batch_candidate_sha256_mismatch"):
        build_release_bundle(
            candidate=fixture["candidate"],
            release_manifest=changed_release,
            rollback_manifest=fixture["rollback_manifest"],
            output_dir=tmp_path / "bad-binding-bundle",
            expected_candidate_sha256=fixture["candidate_identity"].sha256,
            expected_record_count=2,
            expected_release_manifest_sha256=sha256_file(changed_release),
            expected_rollback_manifest_sha256=sha256_file(fixture["rollback_manifest"]),
            baseline_sha256=fixture["baseline_identity"].sha256,
            release_records=1,
            excluded_map_battle_records=11,
            source_provenance=fixture["source_provenance"],
            review_binding=fixture["review_binding"],
            repair_batch_manifest=bad_batch,
            mutation_audit=fixture["mutation_audit"],
            acceptance_evidence=fixture["acceptance_evidence"],
        )


def test_remote_exact_identity_is_idempotent_allowed_state(tmp_path):
    fixture = _fixture(tmp_path)
    paths = [Path(fixture["bundle"].compressed_path), Path(fixture["bundle"].manifest_path), Path(fixture["bundle"].checksums_path)]
    assert preflight_remote_assets(fixture["registry"], paths) == "EXACT_BYTE_IDENTICAL_WITH_EXPECTED_METADATA"


def test_rollback_simulation_identity_required(tmp_path):
    fixture = _fixture(tmp_path)
    live = tmp_path / "live.json"
    shutil.copyfile(fixture["baseline"], live)
    proof = _publish_kwargs(fixture, live)["rollback_proof"]
    proof["local_rollback_simulation_id"] = ""
    proof["proof_sha256"] = canonical_payload_sha256(proof, without="proof_sha256")
    with pytest.raises(GovernanceError, match="local_rollback_simulation_id_must_be_non_empty_string"):
        validate_rollback_proof(
            proof,
            live=live,
            baseline=fixture["baseline"],
            candidate=fixture["candidate"],
            rollback_manifest=fixture["rollback_manifest"],
        )
