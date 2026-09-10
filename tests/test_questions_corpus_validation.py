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


def test_known_bad_shape_without_crop_metadata_is_diagnosed_without_repair(tmp_path: Path):
    # Per the Owner/Coordinator ruling the content checks are REPORT_ONLY
    # diagnostics for this corpus family, so a missing crop is reported loudly
    # but does not reject the release. The corpus is still never rewritten.
    path = _write(
        tmp_path / "questions.json",
        [{"id": 1, "content": "(;GM[1]SZ[19];B[aa])", "accepted_moves": [{"x": 0, "y": 0}]}],
    )
    result = validate_questions_corpus(path, release_binding=_binding(path))
    assert result["gates"]["VALID_CROP_METADATA"]["pass"] is False
    assert result["gates"]["VALID_CROP_METADATA"]["blocks_release"] is False
    assert result["summary"]["content_diagnostics_status"] == "FAIL"
    # Identity is intact, so the release itself is not blocked.
    assert result["status"] == "PASS"
    assert result["summary"]["blocking_violation_count"] == 0
    assert json.loads(path.read_text(encoding="utf-8"))[0]["id"] == 1


# ---------------------------------------------------------------------------
# Owner/Coordinator release-policy ruling for the externally-managed Production
# QuestionsCorpus family: exact identity is the only authoritative blocking
# policy; the eight content/schema checks are REPORT_ONLY diagnostics.
#
# The live corpus is an SGF problem set -- board size lives inside the SGF SZ[]
# property in `content`, and crop metadata / structured accepted_moves are
# absent from 100% of records. Rejecting it for lacking fields it has never had
# blocked every real release while production served that exact corpus.
# ---------------------------------------------------------------------------

import pathlib  # noqa: E402

from tools.questions_corpus_validation import (  # noqa: E402
    BLOCKING,
    BLOCKING_IDENTITY_GATE_NAMES,
    GATE_NAMES,
    REPORT_ONLY_CONTENT_GATE_NAMES,
    REPORT_ONLY_DIAGNOSTIC,
)

VALIDATOR_SOURCE = (
    pathlib.Path(__file__).resolve().parents[1]
    / "tools"
    / "questions_corpus_validation.py"
)


def _production_family_record(question_id: int = 48241) -> dict:
    """A record shaped like the real Production corpus: SGF in `content`, no
    board_size, no crop metadata, no structured accepted_moves."""
    return {
        "id": question_id,
        "content": "(;GM[1]SZ[19]AB[ba][be][ca]AW[ab][ac];B[aa])",
        "topic": "10-orc-arena",
        "level": "basics",
        "display_name": "basics No.001",
        "discipline": "life_death",
        "rank": "5k",
        "stage": "LV5",
        "enabled": True,
        "tags": ["basics", "tesuji"],
        "katago_best_move": "",
    }


def test_policy_partition_is_exactly_three_blocking_and_eight_report_only():
    assert len(BLOCKING_IDENTITY_GATE_NAMES) == 3
    assert len(REPORT_ONLY_CONTENT_GATE_NAMES) == 8
    assert len(GATE_NAMES) == 11
    assert set(BLOCKING_IDENTITY_GATE_NAMES) | set(REPORT_ONLY_CONTENT_GATE_NAMES) == set(
        GATE_NAMES
    )
    assert set(BLOCKING_IDENTITY_GATE_NAMES) & set(REPORT_ONLY_CONTENT_GATE_NAMES) == set()
    assert set(BLOCKING_IDENTITY_GATE_NAMES) == {
        "CORPUS_SHA256_PRESENT",
        "CORPUS_RECORD_COUNT_PRESENT",
        "CORPUS_SOURCE_IDENTITY_PRESENT",
    }


def test_production_family_shape_is_not_rejected_for_absent_synthetic_fields(tmp_path: Path):
    path = _write(tmp_path / "questions.json", [_production_family_record()])
    result = validate_questions_corpus(
        path, mode=RELEASE_ENFORCEMENT, release_binding=_binding(path)
    )
    assert result["status"] == "PASS"
    assert result["release_rejected"] is False
    assert result["summary"]["blocking_violation_count"] == 0
    assert result["summary"]["blocking_identity_gates_passed"] == 3
    # ...and the absence of the synthetic schema is still reported, not hidden.
    assert result["summary"]["content_diagnostics_status"] == "FAIL"
    assert result["gates"]["VALID_BOARD_SIZE"]["pass"] is False
    assert result["gates"]["VALID_CROP_METADATA"]["pass"] is False


def test_production_family_shape_does_not_raise_under_enforcement(tmp_path: Path):
    path = _write(
        tmp_path / "questions.json", [_production_family_record(i) for i in range(50)]
    )
    # Must not raise: content diagnostics are not authoritative blocking policy.
    result = validate_questions_corpus(
        path, mode=RELEASE_ENFORCEMENT, release_binding=_binding(path)
    )
    assert result["status"] == "PASS"
    assert result["summary"]["report_only_content_violation_count"] > 0


@pytest.mark.parametrize(
    "field, value",
    [
        ("questions_corpus_sha256", "0" * 64),
        ("questions_corpus_record_count", 999),
        ("questions_corpus_bytes", 1),
        ("questions_corpus_source_sha256", "1" * 64),
        ("questions_corpus_source_record_count", 999),
    ],
)
def test_identity_mismatch_still_blocks_on_production_family_shape(tmp_path: Path, field, value):
    path = _write(tmp_path / "questions.json", [_production_family_record()])
    identity = identify_json(path)
    binding = _binding(path)
    binding[field] = value
    result = validate_questions_corpus(
        path,
        release_binding=binding,
        expected_source_sha256=identity.sha256,
        expected_source_record_count=identity.record_count,
    )
    assert result["status"] == "FAIL"
    assert result["summary"]["blocking_violation_count"] > 0
    with pytest.raises(CorpusValidationError):
        validate_questions_corpus(
            path,
            mode=RELEASE_ENFORCEMENT,
            release_binding=binding,
            expected_source_sha256=identity.sha256,
            expected_source_record_count=identity.record_count,
        )


def test_missing_identity_binding_still_blocks_on_production_family_shape(tmp_path: Path):
    path = _write(tmp_path / "questions.json", [_production_family_record()])
    report = validate_questions_corpus(path, mode=REPORT_ONLY)
    assert report["status"] == "FAIL"
    for gate in BLOCKING_IDENTITY_GATE_NAMES:
        assert report["gates"][gate]["pass"] is False
    with pytest.raises(CorpusValidationError):
        validate_questions_corpus(path, mode=RELEASE_ENFORCEMENT)


def test_every_gate_declares_its_enforcement_class(tmp_path: Path):
    path = _write(tmp_path / "questions.json", [_production_family_record()])
    result = validate_questions_corpus(path, release_binding=_binding(path))
    for gate in BLOCKING_IDENTITY_GATE_NAMES:
        assert result["gates"][gate]["enforcement"] == BLOCKING
        assert result["gates"][gate]["blocks_release"] is True
    for gate in REPORT_ONLY_CONTENT_GATE_NAMES:
        assert result["gates"][gate]["enforcement"] == REPORT_ONLY_DIAGNOSTIC
        assert result["gates"][gate]["blocks_release"] is False


def test_content_diagnostics_are_recorded_not_suppressed(tmp_path: Path):
    path = _write(
        tmp_path / "questions.json", [_production_family_record(i) for i in range(40)]
    )
    result = validate_questions_corpus(path, release_binding=_binding(path))
    diag = result["content_diagnostics"]
    assert result["summary"]["content_diagnostics_recorded"] is True
    assert result["summary"]["content_diagnostics_suppressed"] is False
    # Exact counts, never zeroed or rounded away.
    assert diag["violation_count"] == result["summary"]["report_only_content_violation_count"]
    assert diag["violation_count"] == sum(
        result["gates"][g]["violation_count"] for g in REPORT_ONLY_CONTENT_GATE_NAMES
    )
    assert diag["reason_counts"]
    assert diag["status"] == "FAIL"
    # Per-gate exact counts survive even though the inline sample is bounded.
    board = result["gates"]["VALID_BOARD_SIZE"]
    assert board["violation_count"] == 40
    assert board["violations_truncated"] is True
    assert len(board["violations"]) == 20
    assert sum(board["reason_counts"].values()) == 40


def test_report_only_content_failure_is_never_a_release_pass_claim(tmp_path: Path):
    path = _write(tmp_path / "questions.json", [_production_family_record()])
    result = validate_questions_corpus(
        path, mode=RELEASE_ENFORCEMENT, release_binding=_binding(path)
    )
    # The release passes on identity, but the report must not claim the content
    # checks passed, and must not claim all gates passed.
    assert result["status"] == "PASS"
    assert result["summary"]["content_diagnostics_status"] == "FAIL"
    assert result["content_diagnostics"]["status"] == "FAIL"
    assert result["summary"]["passed_gate_count"] < len(GATE_NAMES)
    assert not all(item["pass"] for item in result["gates"].values())


def test_policy_block_is_declared_in_the_report(tmp_path: Path):
    path = _write(tmp_path / "questions.json", [_production_family_record()])
    result = validate_questions_corpus(path, release_binding=_binding(path))
    policy = result["release_enforcement_policy"]
    assert policy["blocking_identity_gate_count"] == 3
    assert policy["report_only_content_gate_count"] == 8
    assert policy["content_diagnostics_can_block_release"] is False


def test_validator_never_discovers_or_selects_a_corpus_itself():
    # No staged candidate may be auto-selected: the caller must supply the exact
    # path and the exact identity, and identity is compared against the file.
    # Prose in comments is fine; what must not exist is selection *code*.
    text = VALIDATOR_SOURCE.read_text(encoding="utf-8")
    code = "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )
    for forbidden in (
        "b7b4eedf",  # PR318 staged candidate sha
        "4ac424c4",  # V2 staged candidate sha
        "4d13fa98",  # source baseline sha
        "glob(",  # discovery
        "rglob(",
        "iterdir(",
        "scandir(",
        "listdir(",
        "walk(",
        "environ",  # implicit path from environment
        "getenv(",
        "Path.cwd(",
        "os.getcwd(",
    ):
        assert forbidden not in code, "validator must not reference " + repr(forbidden)
    assert "A caller must provide the exact corpus path" in text
    # The public entrypoint takes the corpus path as a required argument.
    assert "def validate_questions_corpus(" in text
    assert "corpus_path" in text
