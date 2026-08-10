import json
import os
import shutil
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
    build_release_bundle,
    deterministic_gzip,
    identify_json,
    publish_content,
    rollback_content,
    sha256_file,
    simulated_directory_fsync,
    verify_backup_bundle,
    verify_publish_gates,
    verify_release_round_trip,
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
    release_manifest = _write_manifest(tmp_path / "release.json", {"release_records": 1})
    rollback_manifest = _write_manifest(tmp_path / "rollback.json", {"restore": "baseline"})
    baseline_identity = identify_json(baseline)
    candidate_identity = identify_json(candidate)
    bundle = build_backup_bundle(
        source=baseline,
        output_dir=tmp_path / "bundle",
        expected_sha256=baseline_identity.sha256,
        expected_record_count=baseline_identity.record_count,
        artifact_role="pre_mutation_baseline",
        source_environment="synthetic",
        source_path_label="synthetic/baseline.json",
        created_at_utc="2026-08-10T00:00:00Z",
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
        "release_manifest": release_manifest,
        "rollback_manifest": rollback_manifest,
        "baseline_identity": baseline_identity,
        "candidate_identity": candidate_identity,
        "bundle": bundle,
        "registry": registry,
        "receipt": receipt_path,
    }


def _publish_kwargs(fixture, live: Path):
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
            execute=False,
            owner_gate="",
        )
