"""Bounded W1-05 acceptance evidence for Wave1 final-gate planning.

This module is deliberately test-owned.  It exercises existing first-clear,
Map Battle, Zone3 asset, and release contracts; it does not add product
authority or replace the Owner/device/Production gates recorded in the matrix.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from adventure_first_clear_convergence import (
    record_completion,
    record_pending_receipt,
)
from map_battle_persistence import MAP_BATTLE_JUDGE_VERSION
from map_battle_runtime import (
    CanonicalAnswer,
    JudgeOutcome,
    JudgeUnavailable,
    MAP_BATTLE_TRUSTED_CORRECT_REASON_CODES,
    MAP_BATTLE_TRUSTED_EVIDENCE_POLICY,
    MAP_BATTLE_TRUSTED_INCORRECT_REASON_CODES,
    judge_map_battle_answer_v1,
)
from migrations.domain_event_outbox_v1 import TABLE_NAME, upgrade as upgrade_domain_event_outbox


ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = ROOT / "tests" / "w1_05_wave1_acceptance_matrix.json"
ZONE3_AUDIO_PRESENTATION = ROOT / "assets/e10/audio/zone3/zone3-presentation-audio-manifest.json"
ZONE3_AUDIO_ZH = ROOT / "assets/e10/audio/zone3/zone3-cinematic-audio-manifest.json"
ZONE3_AUDIO_EN = ROOT / "assets/e10/audio/zone3/zone3-cinematic-audio-manifest-en-US.json"
ZONE3_CINEMATIC = ROOT / "assets/e10/art/zone3/cinematic/zone3-cinematic-asset-package.json"
ZONE3_WORLD = ROOT / "assets/e10/art/zone3/zone3-world-asset-package.json"
C1_CONTRACT = ROOT / "docs/contracts/w1_c1_zone3_reference_vertical_slice_template_001.json"
VIEWPORT_RUNNER = ROOT / (
    "tests/e2e/run_w1_03_journey_zone3_final_presentation_single_writer_binding_010.mjs"
)


EXPECTED_ROW_IDS = {
    "W1-05-A-SESSION",
    "W1-05-B-FIRST-CLEAR",
    "W1-05-C-REWARD",
    "W1-05-D-ZONE-STAR",
    "W1-05-E-NEXT-ZONE",
    "W1-05-F-REPLAY",
    "W1-05-G-ZONE3",
    "W1-05-H-HERO",
    "W1-05-H-LORD",
    "W1-05-I-AUDIO",
    "W1-05-J-DESKTOP",
    "W1-05-J-IPAD-LANDSCAPE",
    "W1-05-J-IPAD-PORTRAIT",
    "W1-05-J-IPHONE",
    "W1-05-K-STATIC",
    "W1-05-K-ROLLBACK",
}
REQUIRED_MATRIX_FIELDS = {
    "gate_id",
    "surface",
    "test_or_check",
    "automatable",
    "requires_physical_device",
    "requires_owner_perceptual_acceptance",
    "requires_production",
    "current_result",
    "evidence_location",
}


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _answer(*moves: tuple[int, int]) -> CanonicalAnswer:
    return CanonicalAnswer(
        {
            "player_color": "B",
            "moves": [
                {"action": "play", "color": "B", "x": x, "y": y}
                for x, y in moves
            ],
        }
    )


def test_matrix_is_complete_and_keeps_acceptance_layers_explicit() -> None:
    matrix = _load_json(MATRIX_PATH)
    rows = matrix["rows"]

    assert matrix["schema"] == "w1_05_wave1_acceptance_matrix_v1"
    assert len(rows) == 16
    assert {row["gate_id"] for row in rows} == EXPECTED_ROW_IDS
    assert all(REQUIRED_MATRIX_FIELDS <= set(row) for row in rows)
    assert all(isinstance(row["evidence_location"], list) for row in rows)

    # A test result is not allowed to silently become physical, perceptual,
    # publication, or Production acceptance merely by being in this matrix.
    for row in rows:
        result = row["current_result"]
        assert "PHYSICAL_ACCEPTED" not in result
        assert "PRODUCTION_ACCEPTED" not in result
        if row["requires_physical_device"]:
            assert "PHYSICAL_PENDING" in result or "DEVICE_PENDING" in result
        if row["requires_owner_perceptual_acceptance"]:
            assert "OWNER_PENDING" in result or "PERCEPTUAL_PENDING" in result
        if row["requires_production"]:
            assert "PRODUCTION_PENDING" not in result
            assert any(
                marker in result
                for marker in ("NOT_RUN", "AUTOMATED", "PREEXISTING")
            )


def test_matrix_evidence_locations_are_current_repository_surfaces() -> None:
    matrix = _load_json(MATRIX_PATH)
    missing = [
        evidence
        for row in matrix["rows"]
        for evidence in row["evidence_location"]
        if not (ROOT / evidence).is_file()
    ]
    assert missing == []


def test_first_clear_projection_replay_is_exactly_once() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    upgrade_domain_event_outbox(connection)
    try:
        pending = record_pending_receipt(
            connection,
            user_id=705,
            zone_key="k16_20",
            operation_id="w1-05-first-clear-705-k16_20",
            occurred_at="2026-09-08T00:00:00",
        )
        pending_replay = record_pending_receipt(
            connection,
            user_id=705,
            zone_key="k16_20",
            operation_id="w1-05-first-clear-705-k16_20",
            occurred_at="2026-09-08T00:00:01",
        )
        completion = record_completion(
            connection,
            user_id=705,
            zone_key="k16_20",
            operation_id="w1-05-first-clear-705-k16_20",
            occurred_at="2026-09-08T00:00:02",
            projection={"reward": "first_clear", "stars": 1, "next_zone_unlocked": True},
        )
        completion_replay = record_completion(
            connection,
            user_id=705,
            zone_key="k16_20",
            operation_id="w1-05-first-clear-705-k16_20",
            occurred_at="2026-09-08T00:00:03",
            projection={"reward": "first_clear", "stars": 1, "next_zone_unlocked": True},
        )

        assert pending["duplicate"] is False
        assert pending_replay["duplicate"] is True
        assert completion["duplicate"] is False
        assert completion_replay["duplicate"] is True
        rows = connection.execute(
            f"SELECT idempotency_key FROM {TABLE_NAME} "
            "WHERE event_type=? ORDER BY idempotency_key",
            ("ADVENTURE_FIRST_CLEAR_PROJECTION",),
        ).fetchall()
        assert len(rows) == 2
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("question", "answer", "expected"),
    [
        (
            {"content": "(;SZ[19];B[dd])"},
            _answer((3, 3)),
            ("CORRECT", 5, "answer_tree_leaf"),
        ),
        (
            {"content": "(;SZ[19];B[dd];W[ee])"},
            _answer((3, 3)),
            ("CORRECT", 5, "answer_tree_reply_leaf"),
        ),
        (
            {"content": "(;SZ[19];B[dd])", "accepted_moves": [{"x": 4, "y": 4}]},
            _answer((4, 4)),
            ("CORRECT", 5, "accepted_authoritative_alternative"),
        ),
        (
            {"content": "(;SZ[19];B[dd])"},
            _answer((4, 4)),
            ("INCORRECT", 0, "off_answer_tree"),
        ),
        (
            {"content": "(;SZ[19];B[dd])"},
            CanonicalAnswer({"player_color": "B", "moves": [{"action": "resign"}]}),
            ("INCORRECT", 0, "resign"),
        ),
        (
            {"content": "(;SZ[19];B[dd];W[ee];B[ff])"},
            _answer((3, 3)),
            ("INCORRECT", 0, "partial_answer_sequence"),
        ),
    ],
)
def test_settled_a2_judge_contract_remains_unchanged(question, answer, expected) -> None:
    outcome = judge_map_battle_answer_v1(
        question,
        {"board_size": 19, "transform_id": "identity"},
        answer,
    )
    assert (outcome.result, outcome.authoritative_grade, outcome.reason_code) == expected


def test_a2_retry_and_mbv1_boundaries_remain_explicit() -> None:
    assert MAP_BATTLE_TRUSTED_EVIDENCE_POLICY == "PRESERVE_BARE_LEAF_AND_GRANDFATHER_MBV1"
    assert MAP_BATTLE_TRUSTED_CORRECT_REASON_CODES == {
        "accepted_authoritative_alternative",
        "answer_tree_leaf",
        "answer_tree_reply_leaf",
    }
    assert MAP_BATTLE_TRUSTED_INCORRECT_REASON_CODES == {
        "off_answer_tree",
        "resign",
        "partial_answer_sequence",
    }
    with pytest.raises(JudgeUnavailable):
        judge_map_battle_answer_v1(
            {"content": ""},
            {"board_size": 19, "transform_id": "identity"},
            _answer((3, 3)),
        )
    assert MAP_BATTLE_JUDGE_VERSION


def test_zone3_visual_and_audio_manifest_bindings_have_no_missing_files() -> None:
    cinematic = _load_json(ZONE3_CINEMATIC)
    world = _load_json(ZONE3_WORLD)
    assert len(cinematic["shots"]) == 10
    assert len(world["assets"]) == 12

    for record in [*cinematic["shots"], *world["assets"]]:
        runtime_path = ROOT / record["RUNTIME_PATH"]
        assert runtime_path.is_file(), record["RUNTIME_PATH"]
        assert runtime_path.stat().st_size == record.get("RUNTIME_BYTES", runtime_path.stat().st_size)
        if record.get("RUNTIME_SHA256"):
            assert _sha256(runtime_path) == record["RUNTIME_SHA256"]

    presentation = _load_json(ZONE3_AUDIO_PRESENTATION)
    audio_records = list(presentation["CUES"])
    for manifest_path in (ZONE3_AUDIO_ZH, ZONE3_AUDIO_EN):
        audio_records.extend(_load_json(manifest_path)["entries"])
    assert len(audio_records) == 212
    for record in audio_records:
        audio_path = ROOT / record["OUTPUT_PATH"] if "OUTPUT_PATH" in record else ROOT / record["AUDIO_PATH"]
        assert audio_path.is_file(), str(audio_path)
        assert audio_path.stat().st_size == record["BYTES"]
        assert _sha256(audio_path) == record["SHA256"]


def test_zone3_contract_keeps_device_and_production_gates_unclaimed() -> None:
    contract = _load_json(C1_CONTRACT)
    responsive = contract["components"]["responsive_device_acceptance"]
    audio = contract["components"]["audio"]

    assert contract["status"] == "PASS_Z3_CONTENT_CANDIDATE_READY"
    assert contract["scope_locks"]["app_py_mutation"] is False
    assert contract["provenance"]["production_mutation"] is False
    assert contract["provenance"]["merge"] is False
    assert contract["provenance"]["deploy"] is False
    assert responsive["physical_device_tested"] is False
    assert responsive["authenticated_walkthrough_tested"] is False
    assert "separate" in audio["owner_gate"].lower()


def test_existing_browser_runner_covers_four_emulated_layouts_without_physical_claim() -> None:
    source = VIEWPORT_RUNNER.read_text(encoding="utf-8")
    for marker in (
        "['DESKTOP', { width: 1440, height: 900 }]",
        "['IPAD_LANDSCAPE', { width: 1180, height: 820 }]",
        "['IPAD_PORTRAIT', { width: 834, height: 1194 }]",
        "['MOBILE_PORTRAIT', { width: 430, height: 932 }]",
    ):
        assert marker in source
    assert "BROWSER_QA=PASS" in source
    assert "PHYSICAL_DEVICE_ACCEPTED" not in source
