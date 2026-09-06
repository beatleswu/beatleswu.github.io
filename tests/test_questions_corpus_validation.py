"""Offline tests for the explicit questions-corpus release gate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.content_release_core import identify_json
from tools.questions_corpus_validation import (
    CorpusValidationError,
    RELEASE_ENFORCEMENT,
    REPORT_ONLY,
    validate_questions_corpus,
)


def _record(*, moves=None, crop=None, katago=None):
    row = {
        "id": 1001,
        "board_size": 19,
        "crop": crop or {"origin_x": 3, "origin_y": 4, "width": 9, "height": 9},
        "accepted_moves": moves if moves is not None else [{"x": 5, "y": 6}],
    }
    if katago is not None:
        row["katago_best_move"] = katago
    return row


def _write(path: Path, rows) -> Path:
    path.write_text(json.dumps(rows, separators=(",", ":")), encoding="utf-8")
    return path


def _binding(path: Path, *, sha=None, count=None, size=None, snapshot="snapshot-001", source_sha=None, source_count=None):
    identity = identify_json(path)
    return {
        "questions_corpus_sha256": sha or identity.sha256,
        "questions_corpus_record_count": identity.record_count if count is None else count,
        "questions_corpus_bytes": identity.size_bytes if size is None else size,
        "questions_corpus_snapshot_id": snapshot,
        "questions_corpus_source_identity": "f" * 64,
        "questions_corpus_source_sha256": source_sha or identity.sha256,
        "questions_corpus_source_record_count": identity.record_count if source_count is None else source_count,
    }


def test_valid_fixture_passes_enforcement(tmp_path: Path):
    path = _write(tmp_path / "questions.json", [_record()])
    result = validate_questions_corpus(
        path, mode=RELEASE_ENFORCEMENT, release_binding=_binding(path)
    )
    assert result["status"] == "PASS"
    assert result["release_rejected"] is False
    assert all(item["pass"] for item in result["gates"].values())


@pytest.mark.parametrize(
    "field, value, gate",
    [
        ("questions_corpus_sha256", "0" * 64, "CORPUS_SHA256_PRESENT"),
        ("questions_corpus_record_count", 2, "CORPUS_RECORD_COUNT_PRESENT"),
        ("questions_corpus_bytes", 1, "CORPUS_SHA256_PRESENT"),
        ("questions_corpus_source_sha256", "1" * 64, "CORPUS_SOURCE_IDENTITY_PRESENT"),
        ("questions_corpus_source_record_count", 2, "CORPUS_SOURCE_IDENTITY_PRESENT"),
        ("questions_corpus_snapshot_id", None, "CORPUS_SOURCE_IDENTITY_PRESENT"),
    ],
)
def test_identity_mismatch_fails_closed(tmp_path: Path, field, value, gate):
    path = _write(tmp_path / "questions.json", [_record()])
    binding = _binding(path)
    binding[field] = value
    identity = identify_json(path)
    result = validate_questions_corpus(
        path,
        release_binding=binding,
        expected_source_sha256=identity.sha256,
        expected_source_record_count=identity.record_count,
    )
    assert result["status"] == "FAIL"
    assert result["gates"][gate]["pass"] is False
    with pytest.raises(CorpusValidationError):
        validate_questions_corpus(
            path,
            mode=RELEASE_ENFORCEMENT,
            release_binding=binding,
            expected_source_sha256=identity.sha256,
            expected_source_record_count=identity.record_count,
        )


def test_missing_identity_binding_is_reported_and_enforcement_rejects(tmp_path: Path):
    path = _write(tmp_path / "questions.json", [_record()])
    report = validate_questions_corpus(path, mode=REPORT_ONLY)
    assert report["status"] == "FAIL"
    assert report["gates"]["CORPUS_SHA256_PRESENT"]["pass"] is False
    with pytest.raises(CorpusValidationError):
        validate_questions_corpus(path, mode=RELEASE_ENFORCEMENT)


def test_negative_crop_origin_fails(tmp_path: Path):
    path = _write(
        tmp_path / "questions.json",
        [_record(crop={"origin_x": -1, "origin_y": 0, "width": 9, "height": 9})],
    )
    result = validate_questions_corpus(path, release_binding=_binding(path))
    assert result["gates"]["NON_NEGATIVE_CROP_ORIGIN"]["pass"] is False
    assert result["gates"]["DETERMINISTIC_GLOBAL_LOCAL_MAPPING"]["pass"] is False


def test_all_authoritative_moves_off_crop_fails(tmp_path: Path):
    path = _write(
        tmp_path / "questions.json",
        [_record(moves=[{"x": 18, "y": 18}])],
    )
    result = validate_questions_corpus(path, release_binding=_binding(path))
    assert result["gates"]["NO_INVALID_ALL_OFF_CROP_AUTHORITY"]["pass"] is False
    assert result["gates"]["AT_LEAST_ONE_PLAYABLE_AUTHORITATIVE_ANSWER"]["pass"] is False


def test_mixed_in_crop_and_off_crop_authority_is_reported_but_not_all_off_crop(tmp_path: Path):
    path = _write(
        tmp_path / "questions.json",
        [_record(moves=[{"x": 5, "y": 6}, {"x": 18, "y": 18}])],
    )
    result = validate_questions_corpus(path, release_binding=_binding(path))
    assert result["gates"]["NO_INVALID_ALL_OFF_CROP_AUTHORITY"]["pass"] is True
    assert result["gates"]["AT_LEAST_ONE_PLAYABLE_AUTHORITATIVE_ANSWER"]["pass"] is True


def test_explicit_pass_is_valid_special_move(tmp_path: Path):
    path = _write(tmp_path / "questions.json", [_record(moves=[{"type": "pass"}])])
    result = validate_questions_corpus(path, release_binding=_binding(path))
    assert result["gates"]["EXPLICIT_PASS_SPECIAL_MOVE_SEMANTICS"]["pass"] is True
    assert result["gates"]["AT_LEAST_ONE_PLAYABLE_AUTHORITATIVE_ANSWER"]["pass"] is True


def test_katago_off_crop_is_not_silently_promoted(tmp_path: Path):
    path = _write(tmp_path / "questions.json", [_record(katago="T1")])
    result = validate_questions_corpus(path, release_binding=_binding(path))
    assert result["gates"]["KATAGO_LOCAL_CROP_REPRESENTABILITY"]["pass"] is False


def test_known_bad_shape_without_crop_metadata_fails_without_repair(tmp_path: Path):
    path = _write(
        tmp_path / "questions.json",
        [{"id": 1, "content": "(;GM[1]SZ[19];B[aa])", "accepted_moves": [{"x": 0, "y": 0}]}],
    )
    result = validate_questions_corpus(path, release_binding=_binding(path))
    assert result["status"] == "FAIL"
    assert result["gates"]["VALID_CROP_METADATA"]["pass"] is False
    assert json.loads(path.read_text(encoding="utf-8"))[0]["id"] == 1
