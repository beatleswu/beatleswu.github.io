import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = (
    REPO_ROOT / "tests" / "sgf_engine" / "data" / "gold_fixtures" / "fixtures.json"
)
OVERRIDES_PATH = REPO_ROOT / "puzzle_variation_overrides.json"

REVIEW_TRACEABILITY_FIELDS = {
    "gf_id",
    "fixture_path",
    "player_move_sgf",
    "canonical_move_sgf",
    "disabled_override_metadata",
    "proposed_override",
    "reason",
}
VISUAL_SGF_SAFE_SUBSET_FIELDS = {
    "gold_fixture_id",
    "source_path",
    "player_move_sgf",
    "canonical_move_sgf",
    "runtime_status",
    "apply_automatically",
}
INACTIVE_RUNTIME_STATUSES = {"disabled"}
FUTURE_C_LEVEL_REQUIREMENT_FIELDS = {
    "teacher_facing_status_bucket",
    "canonical_answer_display_coordinate",
    "proposed_candidate_display_coordinate",
    "review_notes",
    "student_report_context",
    "frontend_sgf_playback_payload",
    "review_card_payload",
}


@pytest.fixture(scope="module")
def manifest():
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def gf003(manifest):
    excluded_by_id = {
        record["gf_id"]: record for record in manifest["excluded_fixtures"]
    }
    return excluded_by_id["GF-003"]


def test_gf003_exposes_current_review_traceability_subset(gf003):
    metadata = gf003["disabled_override_metadata"]

    assert REVIEW_TRACEABILITY_FIELDS.issubset(gf003)
    assert VISUAL_SGF_SAFE_SUBSET_FIELDS.issubset(metadata)

    assert gf003["gf_id"] == "GF-003"
    assert gf003["fixture_path"] == "tests/sgf_engine/data/gold_fixtures/431.sgf"
    assert metadata["gold_fixture_id"] == "GF-003"
    assert metadata["source_path"] == gf003["fixture_path"]


def test_gf003_keeps_canonical_answer_separate_from_proposed_candidate_answer(gf003):
    metadata = gf003["disabled_override_metadata"]
    proposed_override = gf003["proposed_override"]

    assert gf003["canonical_move_sgf"] == "B[sf]"
    assert gf003["player_move_sgf"] == "B[sd]"
    assert metadata["canonical_move_sgf"] == gf003["canonical_move_sgf"]
    assert metadata["player_move_sgf"] == gf003["player_move_sgf"]
    assert proposed_override["source_key"] == gf003["fixture_path"]
    assert proposed_override["equivalent_moves"] == {"sf": ["sd"]}
    assert gf003["canonical_move_sgf"] != gf003["player_move_sgf"]


def test_gf003_runtime_and_activation_flags_remain_inactive(gf003):
    metadata = gf003["disabled_override_metadata"]

    assert gf003["status"] == "CANDIDATE_REQUIRES_OVERRIDE"
    assert metadata["runtime_status"] in INACTIVE_RUNTIME_STATUSES
    assert metadata["apply_automatically"] is False
    assert metadata["runtime_override_active"] is False
    assert metadata["ready_activation"] is False
    assert gf003["runtime_override_active"] is False
    assert gf003["ready_activation"] is False
    assert gf003["ready_for_next_test_commit"] is False


def test_production_override_document_remains_empty_and_inactive():
    overrides = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))

    assert overrides == {}


def test_visual_review_sgf_reference_exists_and_looks_like_sgf(gf003):
    fixture_path = REPO_ROOT / gf003["fixture_path"]
    content = fixture_path.read_text(encoding="utf-8")
    stripped = content.strip()

    assert fixture_path.suffix == ".sgf"
    assert fixture_path.exists()
    assert stripped
    assert stripped.startswith("(")
    assert ";" in stripped
    assert stripped.endswith(")")


def test_current_metadata_remains_traceability_only_not_future_review_card_api(gf003):
    metadata = gf003["disabled_override_metadata"]

    for field in FUTURE_C_LEVEL_REQUIREMENT_FIELDS:
        assert field not in gf003
        assert field not in metadata
