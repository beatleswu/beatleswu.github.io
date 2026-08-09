import hashlib
import json
from pathlib import Path

import pytest

from tools import sgf_answer_content_release as release
from tools import sgf_answer_repair_batch as repair


ONE_A2 = "(;GM[1]FF[4]SZ[19]PL[W]AB[cc](;W[ar]))"
ONE_B1 = "(;GM[1]FF[4]SZ[19]PL[W]AB[cc](;W[bs]))"
BRANCHED_REPLY = (
    "(;GM[1]FF[4]SZ[19]PL[W]AB[cc]"
    "(;W[ar](;B[aq];W[br])(;B[bq];W[cr])))"
)


def _sha(raw):
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _write_json(path: Path, value):
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _locked_batches(tmp_path):
    repaired, _ = repair._rewrite_answer_set(ONE_A2, [(1, 18)])
    native_hash = "1" * 64
    fallback_hash = "2" * 64
    native = {
        "batch_sha256": native_hash,
        "groups": [
            {
                "records": [
                    {
                        "legacy_question_id": 1,
                        "current_record_index": 0,
                        "current_fallback_move": "",
                        "desired_native_accepted_set": ["B1"],
                        "planned_operations": [
                            {
                                "type": "REWRITE_NATIVE_ROOT_ANSWER_SET",
                                "after": ["B1"],
                            }
                        ],
                        "owner_desired_verdict": ["B1"],
                        "source_content_sha256_before": _sha(ONE_A2),
                        "source_content_sha256_after": _sha(repaired),
                    }
                ]
            }
        ],
    }
    fallback = {
        "batch_sha256": fallback_hash,
        "groups": [
            {
                "records": [
                    {
                        "legacy_question_id": 2,
                        "current_record_index": 1,
                        "current_fallback_move": "Q4",
                        "desired_fallback_move": "",
                        "owner_desired_verdict": ["B1"],
                        "source_content_sha256_before": _sha(ONE_B1),
                        "source_content_sha256_after": _sha(ONE_B1),
                    }
                ]
            }
        ],
    }
    native_path = tmp_path / "native.json"
    fallback_path = tmp_path / "fallback.json"
    _write_json(native_path, native)
    _write_json(fallback_path, fallback)
    return {
        "native_path": native_path,
        "native_hash": native_hash,
        "native_file_hash": release._sha256_file(native_path),
        "fallback_path": fallback_path,
        "fallback_hash": fallback_hash,
        "fallback_file_hash": release._sha256_file(fallback_path),
    }


def _baseline(tmp_path):
    path = tmp_path / "baseline.json"
    raw = (
        json.dumps(
            [
                {
                    "id": 1,
                    "content": ONE_A2,
                    "katago_best_move": "",
                    "metadata": {"keep": True},
                },
                {
                    "id": 2,
                    "content": ONE_B1,
                    "katago_best_move": "Q4",
                    "metadata": {"keep": True},
                },
                {
                    "id": 3,
                    "content": ONE_A2,
                    "katago_best_move": "D4",
                    "metadata": {"keep": True},
                },
            ],
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")
    path.write_bytes(raw)
    return path, raw


def test_verify_baseline_fails_closed_on_hash_mismatch(tmp_path):
    path, raw = _baseline(tmp_path)
    with pytest.raises(release.ContentReleaseError, match="baseline SHA-256"):
        release.verify_baseline(
            path,
            expected_sha256="0" * 64,
            expected_size_bytes=len(raw),
            expected_records=3,
        )


def test_targeted_patch_preserves_non_target_record_and_non_target_fields(tmp_path):
    path, raw = _baseline(tmp_path)
    records = json.loads(raw)
    repaired, _ = repair._rewrite_answer_set(ONE_A2, [(1, 18)])
    candidate_raw, old = release.patch_corpus_string_fields(
        raw,
        records,
        {0: {"content": repaired}, 1: {"katago_best_move": ""}},
    )
    candidate = json.loads(candidate_raw)
    diff = release.semantic_diff(
        records,
        candidate,
        native_ids={1},
        fallback_ids={2},
    )

    assert old == {0: {"content": ONE_A2}, 1: {"katago_best_move": "Q4"}}
    assert diff["target_records_changed"] == 2
    assert diff["non_target_records_changed"] == 0
    assert records[2] == candidate[2]
    assert records[0]["metadata"] == candidate[0]["metadata"]
    assert records[1]["content"] == candidate[1]["content"]


def test_semantic_diff_rejects_non_target_change(tmp_path):
    _, raw = _baseline(tmp_path)
    records = json.loads(raw)
    candidate = json.loads(raw)
    candidate[2]["metadata"]["keep"] = False
    with pytest.raises(release.ContentReleaseError, match="changed fields"):
        release.semantic_diff(
            records,
            candidate,
            native_ids={1},
            fallback_ids={2},
        )


def test_non_target_duplicate_legacy_ids_do_not_block_locked_record_indexes(tmp_path):
    _, raw = _baseline(tmp_path)
    records = json.loads(raw)
    records.append(dict(records[2]))
    indexes = release._record_indexes(records)

    assert indexes[3] == [2, 3]
    assert indexes[1] == [0]


def test_atomic_replace_refuses_wrong_current_hash_without_touching_target(tmp_path):
    baseline, raw = _baseline(tmp_path)
    candidate = tmp_path / "candidate.json"
    changed = json.loads(raw)
    changed[0]["katago_best_move"] = "Q4"
    _write_json(candidate, changed)
    before = baseline.read_bytes()

    with pytest.raises(release.ContentReleaseError, match="precondition"):
        release.atomic_replace_from_artifact(
            target=baseline,
            artifact=candidate,
            expected_current_sha256="0" * 64,
            expected_artifact_sha256=release._sha256_file(candidate),
            expected_record_count=3,
        )

    assert baseline.read_bytes() == before
    assert not list(tmp_path.glob(".baseline.json.stage-*"))


def test_interrupted_atomic_replace_keeps_original_and_cleans_stage(tmp_path):
    baseline, raw = _baseline(tmp_path)
    candidate = tmp_path / "candidate.json"
    changed = json.loads(raw)
    changed[0]["katago_best_move"] = "Q4"
    _write_json(candidate, changed)
    before = baseline.read_bytes()

    def interrupt(_target, _stage):
        raise RuntimeError("simulated interruption")

    with pytest.raises(RuntimeError, match="simulated interruption"):
        release.atomic_replace_from_artifact(
            target=baseline,
            artifact=candidate,
            expected_current_sha256=_sha(before),
            expected_artifact_sha256=release._sha256_file(candidate),
            expected_record_count=3,
            before_replace=interrupt,
        )

    assert baseline.read_bytes() == before
    assert not list(tmp_path.glob(".baseline.json.stage-*"))


def test_local_publish_and_rollback_is_byte_exact(tmp_path):
    baseline, raw = _baseline(tmp_path)
    candidate = tmp_path / "candidate.json"
    changed = json.loads(raw)
    changed[1]["katago_best_move"] = ""
    _write_json(candidate, changed)
    output = tmp_path / "simulation.json"

    result = release.simulate_publish_and_rollback(
        baseline_artifact=baseline,
        candidate_artifact=candidate,
        baseline_sha256=_sha(raw),
        candidate_sha256=release._sha256_file(candidate),
        expected_record_count=3,
        output_path=output,
        created_at="2026-08-10T00:00:00Z",
    )

    assert result["wrong_hash_fail_closed_test"] == "PASS"
    assert result["publisher_local_simulation"] == "PASS"
    assert result["rollback_byte_exact"] == "YES"
    assert result["rollback_final_sha256"] == _sha(raw)


def test_publish_and_rollback_cli_execution_are_owner_gated():
    with pytest.raises(release.ContentReleaseError, match="GO_CONTENT_PUBLISH"):
        release._guard_execute("", False, "GO_CONTENT_PUBLISH")
    with pytest.raises(release.ContentReleaseError, match="GO_CONTENT_ROLLBACK"):
        release._guard_execute("GO_CONTENT_PUBLISH", True, "GO_CONTENT_ROLLBACK")


def test_actual_runtime_validation_fails_closed_on_map_battle_branching_gap():
    record = {
        "id": 4,
        "content": BRANCHED_REPLY,
        "katago_best_move": "",
    }
    with pytest.raises(release.ContentReleaseError, match="Map Battle verdict mismatch"):
        release.validate_player_verdicts([record], {4: ["A2"]})

    diagnostic = release.validate_player_verdicts(
        [record],
        {4: ["A2"]},
        fail_on_map_battle_mismatch=False,
    )
    assert diagnostic["all_final_effective_match"] is False
    assert diagnostic["map_battle_mismatch_ids"] == [4]


def test_build_package_is_deterministic_and_validates_actual_player_surfaces(tmp_path):
    baseline, raw = _baseline(tmp_path)
    batches = _locked_batches(tmp_path)
    common = {
        "baseline_path": baseline,
        "native_batch_path": batches["native_path"],
        "fallback_batch_path": batches["fallback_path"],
        "created_at": "2026-08-10T00:00:00Z",
        "expected_baseline_sha256": _sha(raw),
        "expected_baseline_size": len(raw),
        "expected_baseline_records": 3,
        "expected_native_batch_sha256": batches["native_hash"],
        "expected_native_batch_file_sha256": batches["native_file_hash"],
        "expected_fallback_batch_sha256": batches["fallback_hash"],
        "expected_fallback_batch_file_sha256": batches["fallback_file_hash"],
        "expected_native_ids": frozenset({1}),
        "expected_excluded_ids": frozenset(),
        "expected_fallback_records": 1,
        "expected_fallback_groups": 1,
        "validate_runtime": True,
    }
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first = release.build_release_package(output_dir=first_dir, **common)
    second = release.build_release_package(output_dir=second_dir, **common)

    assert first == second
    assert first["target_records_changed"] == 2
    assert first["non_target_records_changed"] == 0
    assert first["fallback_fields_cleared"] == 1
    assert first["native_repair_records"] == 1
    assert first["all_65_final_effective_match"] is True
    for filename in (
        first["candidate_artifact"]["filename"],
        first["release_manifest"],
        first["rollback_manifest"],
    ):
        assert (first_dir / filename).read_bytes() == (second_dir / filename).read_bytes()
