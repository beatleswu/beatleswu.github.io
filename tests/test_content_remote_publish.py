"""Deterministic local coverage for the governed content publish runner.

No test in this module contacts SSH, Docker, or Production.  The promotion
tests exercise the same byte-exact staging/receipt/rollback protocol used by
the host-side helper against disposable temporary files.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools import content_remote_publish as runner


def _write_questions(path: Path, rows: list[dict]) -> None:
    path.write_text(json.dumps(rows, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def _identity(path: Path) -> runner.FileIdentity:
    return runner.identify_file(path)


def _promotion_inputs(tmp_path: Path) -> dict:
    live = tmp_path / "questions.json"
    candidate = tmp_path / "candidate.json"
    _write_questions(live, [{"id": 1, "answer": "A"}, {"id": 2, "answer": "B"}])
    _write_questions(candidate, [{"id": 1, "answer": "C"}, {"id": 2, "answer": "B"}])
    previous = _identity(live)
    target = _identity(candidate)
    return {
        "live": live,
        "candidate": candidate,
        "expected_predecessor_sha256": previous.sha256,
        "expected_predecessor_record_count": previous.record_count,
        "expected_candidate_sha256": target.sha256,
        "expected_candidate_record_count": target.record_count,
        "release_id": "test-release-001",
        "receipt_dir": tmp_path / "receipts",
        "package_sha256": "a" * 64,
        "rollback_manifest_sha256": "b" * 64,
        "target_identity": {
            "container_name": "test-app",
            "mount_destination": "/app/data",
            "volume_name": "test_go-data",
            "mountpoint": str(tmp_path),
            "target_path": "/app/data/questions.json",
        },
    }


def test_dry_run_verifies_without_mutating(tmp_path: Path) -> None:
    values = _promotion_inputs(tmp_path)
    before = values["live"].read_bytes()
    result = runner.promote_local(**values, execute=False)
    assert result["status"] == "DRY_RUN"
    assert result["production_mutation"] is False
    assert values["live"].read_bytes() == before
    assert not values["receipt_dir"].exists()


def test_predecessor_mismatch_fails_closed_before_receipt(tmp_path: Path) -> None:
    values = _promotion_inputs(tmp_path)
    values["expected_predecessor_sha256"] = "c" * 64
    with pytest.raises(runner.ContentPublishError, match="predecessor_sha256_or_record_count_mismatch"):
        runner.promote_local(**values, execute=True)
    assert not values["receipt_dir"].exists()


def test_candidate_mismatch_fails_closed_before_receipt(tmp_path: Path) -> None:
    values = _promotion_inputs(tmp_path)
    values["expected_candidate_sha256"] = "d" * 64
    with pytest.raises(runner.ContentPublishError, match="candidate_sha256_or_record_count_mismatch"):
        runner.promote_local(**values, execute=True)
    assert not values["receipt_dir"].exists()


def test_atomic_promotion_and_post_verification(tmp_path: Path) -> None:
    values = _promotion_inputs(tmp_path)
    result = runner.promote_local(**values, execute=True)
    assert result["status"] == "NEW_VERIFIED_CONTENT"
    assert result["production_mutation"] is True
    assert _identity(values["live"]).sha256 == values["expected_candidate_sha256"]
    assert (values["receipt_dir"] / "test-release-001.rollback-receipt.json").is_file()
    assert (values["receipt_dir"] / "test-release-001.publish-receipt.json").is_file()
    assert not (values["live"].parent / ".go-odyssey-content-test-release-001.stage").exists()


def test_integrity_failure_after_replace_restores_exact_predecessor(tmp_path: Path) -> None:
    values = _promotion_inputs(tmp_path)
    predecessor = _identity(values["live"])
    result = runner.promote_local(**values, execute=True, fail_after_replace=True)
    assert result["status"] == "OLD_VERIFIED_CONTENT"
    assert result["rollback_executed"] is True
    restored = _identity(values["live"])
    assert restored.sha256 == predecessor.sha256
    assert restored.record_count == predecessor.record_count
    assert (values["receipt_dir"] / "test-release-001.rollback-result.json").is_file()


def test_no_arbitrary_target_path_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_command(*args: str, label: str):
        if args[1:3] == ("inspect", "app"):
            return [{"Type": "volume", "Name": "go-data", "Destination": "/app/data", "Source": "/var/lib/docker/volumes/go-data/_data"}]
        return [{"Name": "go-data", "Driver": "local", "Mountpoint": "/var/lib/docker/volumes/go-data/_data"}]

    monkeypatch.setattr(runner, "_run_json_command", fake_command)
    with pytest.raises(runner.ContentPublishError, match="unsupported_content_target"):
        runner.resolve_volume_target(
            container_name="app",
            mount_destination="/app/data",
            target_path="/app/data/other.json",
        )


def test_bind_mount_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_command(*args: str, label: str):
        return [{"Type": "bind", "Source": "/tmp/data", "Destination": "/app/data"}]

    monkeypatch.setattr(runner, "_run_json_command", fake_command)
    with pytest.raises(runner.ContentPublishError, match="content_mount_is_not_named_volume"):
        runner.resolve_volume_target(
            container_name="app",
            mount_destination="/app/data",
            target_path="/app/data/questions.json",
        )


def test_approved_historical_bundle_contract_when_artifact_is_available() -> None:
    bundle = Path(r"D:\go-website-sgf-prod-baseline-release-prep-001-artifacts\release-bundle-b7b4-20260812T-prep")
    if not bundle.is_dir():
        pytest.skip("approved historical bundle is external to the repository")
    result = runner.validate_bundle(
        bundle,
        expected_predecessor_sha256="4d13fa98af8c1a180e719b7a261c5ca638e042a8edbd3fdfe8d2c2f947cdaa28",
        expected_predecessor_record_count=41591,
        expected_candidate_sha256="b7b4eedf72a87ab8fbc82ff51b658cd4dc0f08cb33426aee013e97814edae232",
        expected_candidate_record_count=41591,
        expected_release_package_sha256="82bb3fe290ccfdb7d8204651434a2128e40b404204f1e49b97adef26153b116a",
        expected_rollback_manifest_sha256="6c91e493cb0bdd3230b30658afaaeedec59c2492b88ce0e2a2beabe812438bd5",
    )
    assert result["package_sha256"] == "82bb3fe290ccfdb7d8204651434a2128e40b404204f1e49b97adef26153b116a"
    assert result["candidate_sha256"] == "b7b4eedf72a87ab8fbc82ff51b658cd4dc0f08cb33426aee013e97814edae232"
    assert result["changed_record_count"] == 54
    assert result["review_group_count"] == 43
    assert result["six_surfaces_complete"] is True
    assert result["verdict_mismatch_count"] == 0
