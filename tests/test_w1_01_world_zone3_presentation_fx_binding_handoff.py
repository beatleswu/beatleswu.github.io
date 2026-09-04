"""Focused machine-readable handoff checks for W1-01 Zone 3 FX."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_PACKAGE = ROOT / "docs/planning/w1_01_world_zone3_presentation_fx_runtime_package_009.json"
HANDOFF = ROOT / "docs/planning/w1_01_world_zone3_presentation_fx_binding_handoff_010.json"

EXPECTED_EFFECT_IDS = [
    "Z3_L01",
    "Z3_V01",
    "Z3_V02",
    "Z3_V03",
    "Z3_V04",
    "Z3_V05",
    "Z3_V06",
    "Z3_V07",
    "Z3_V08",
    "Z3_V09",
    "Z3_V10",
    "Z3_T01_VISUAL",
]
EXPECTED_SHOT_IDS = [
    "SHOT01", "SHOT02", "SHOT03", "SHOT04", "SHOT05",
    "SHOT06", "SHOT07", "SHOT08", "SHOT09", "SHOT10",
]


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_handoff_points_to_exact_009_source() -> None:
    runtime = load(RUNTIME_PACKAGE)
    handoff = load(HANDOFF)
    assert handoff["SOURCE_RUNTIME_PACKAGE"] == (
        "docs/planning/w1_01_world_zone3_presentation_fx_runtime_package_009.json"
    )
    assert handoff["SOURCE_HEAD"] == "9c57faf4435fd3fa6a64ddf2d3b3559deec88d93"
    assert handoff["SOURCE_TREE"] == "2bb6aada1e75725955e5c6cc4d259b7e4624754d"
    assert handoff["SOURCE_BRANCH"] == "codex/w1-01-world-style-b-lock"
    assert handoff["ZONE"] == runtime["ZONE"]


def test_exact_twelve_effect_ids_and_ten_shot_records() -> None:
    runtime = load(RUNTIME_PACKAGE)
    handoff = load(HANDOFF)
    assert handoff["ACCEPTED_IMPLEMENTATION"]["CODE_ONLY_EFFECT_COUNT"] == 12
    assert handoff["ACCEPTED_IMPLEMENTATION"]["EFFECT_IDS"] == EXPECTED_EFFECT_IDS
    records = handoff["SHOT_BINDINGS"]
    assert len(records) == 10
    assert [record["SHOT_ID"] for record in records] == EXPECTED_SHOT_IDS
    assert handoff["VALIDATION"]["SHOT_BINDING_RECORD_COUNT"] == 10
    assert handoff["VALIDATION"]["UNKNOWN_EFFECT_REFERENCE_COUNT"] == 0
    assert handoff["VALIDATION"]["UNKNOWN_CAMERA_CUE_COUNT"] == 0
    assert runtime["EFFECTS"]


def test_shot_references_reconcile_to_009_required_and_optional_mapping() -> None:
    runtime = load(RUNTIME_PACKAGE)
    handoff = load(HANDOFF)
    runtime_required = runtime["SHOT_EFFECTS"]
    runtime_optional = runtime["SHOT_OPTIONAL_EFFECTS"]
    effect_ids = set(handoff["ACCEPTED_IMPLEMENTATION"]["EFFECT_IDS"])
    camera_ids = set(runtime["CAMERA_CUES"])

    for record in handoff["SHOT_BINDINGS"]:
        shot_id = record["SHOT_ID"]
        required_refs = (
            record["ENTRY_EFFECT_IDS"]
            + record.get("PERSISTENT_EFFECT_IDS", [])
            + record["EXIT_EFFECT_IDS"]
        )
        optional_refs = record.get("OPTIONAL_ENTRY_EFFECT_IDS", [])
        all_refs = required_refs + optional_refs
        assert len(all_refs) == len(set(all_refs))
        assert set(all_refs) == set(runtime_required[shot_id] + runtime_optional.get(shot_id, []))
        assert set(all_refs) <= effect_ids
        assert record["CAMERA_CUE_ID"] in camera_ids
        assert record["FAILURE_BEHAVIOR"] == "STATIC_PRESENTATION_CONTINUES"
        assert set(record["CLEANUP_BEHAVIOR"]) == {
            "SHOT_CHANGE", "CINEMATIC_EXIT", "REPLAY_EXIT",
            "ROUTE_CHANGE", "INTERRUPTION_OR_ERROR",
        }


def test_shot_ten_transition_is_explicit_and_not_state_authority() -> None:
    handoff = load(HANDOFF)
    shot10 = next(record for record in handoff["SHOT_BINDINGS"] if record["SHOT_ID"] == "SHOT10")
    assert shot10["EXIT_EFFECT_IDS"] == ["Z3_T01_VISUAL"]
    assert shot10["VISUAL_TRANSITION"] == "Z3_T01_VISUAL"
    assert shot10["TRANSITION_TARGET"] == "MISTY_FOREST"
    reduced_motion = shot10["REDUCED_MOTION_BEHAVIOR"].lower()
    assert "do not infer" in reduced_motion
    assert "or change" in reduced_motion


def test_lifetime_semantics_keep_environment_effects_shot_lifecycle_controlled() -> None:
    handoff = load(HANDOFF)
    lifetime = handoff["LIFETIME_SEMANTICS"]
    assert lifetime["EFFECT_ANIMATION_DURATION_CAP_MS"] == 2800
    assert lifetime["CAP_APPLIES_TO"] == "bounded animation/event instances only"
    assert lifetime["EVENT_EFFECT_DURATION_BOUNDED"] is True
    assert lifetime["SHOT_DURATION_ENVIRONMENT_EFFECT_LIFETIME"] == "SHOT_LIFECYCLE_CONTROLLED"
    assert lifetime["STOP_API_CONTROLS_FINAL_LIFETIME"] is True
    assert set(lifetime["EVENT_EFFECT_IDS"]) | set(lifetime["SHOT_DURATION_ENVIRONMENT_EFFECT_IDS"]) == set(
        EXPECTED_EFFECT_IDS
    )
    assert not set(lifetime["EVENT_EFFECT_IDS"]) & set(
        lifetime["SHOT_DURATION_ENVIRONMENT_EFFECT_IDS"]
    )


def test_reduced_motion_and_cleanup_coverage_are_complete() -> None:
    handoff = load(HANDOFF)
    reduced = handoff["REDUCED_MOTION"]
    cleanup = handoff["CLEANUP_CONTRACT"]
    assert reduced["REDUCED_MOTION_EFFECT_COVERAGE"] == "12/12"
    assert reduced["REDUCED_MOTION_CAMERA_COVERAGE"] == "10/10"
    assert set(reduced["BEHAVIORAL_GUARDS"]) == {
        "NO_ABRUPT_SHAKE",
        "NO_UNNECESSARY_CAMERA_MOTION",
        "NO_MISSING_STORY_STATE",
        "NO_GAMEPLAY_IMPACT",
    }
    assert cleanup["API"] == load(RUNTIME_PACKAGE)["LIFECYCLE"]["API"]
    assert cleanup["TASK_OWNED_RESOURCE_LEAK"] == "NO"
    assert cleanup["EXPECTED_RESOURCE_STATE_AFTER_STOP"] == {
        "ACTIVE_TIMER_COUNT": 0,
        "ACTIVE_RAF_COUNT": 0,
        "TEMPORARY_EFFECT_NODE_COUNT": 0,
        "ACTIVE_EVENT_LISTENER_COUNT": 0,
    }


def test_stone_shard_and_centurion_invariants_are_zero() -> None:
    handoff = load(HANDOFF)
    guards = handoff["STORY_GUARDS"]
    assert guards["STONE_SHARD_GLOW_EFFECT_COUNT"] == 0
    assert guards["STONE_SHARD_RUNE_EFFECT_COUNT"] == 0
    assert guards["STONE_SHARD_MAGIC_EFFECT_COUNT"] == 0
    assert guards["CENTURION_DEMONIC_AURA_COUNT"] == 0
    assert guards["CENTURION_BERSERKER_EFFECT_COUNT"] == 0
    assert guards["SHUI_NONVERBAL_VISUAL_CONTRACT"] == "PASS"
    assert guards["FAILURE_BLOCKS_GAMEPLAY"] == "NO"


def test_handoff_keeps_journey_audio_and_product_boundaries_closed() -> None:
    handoff = load(HANDOFF)
    assert handoff["BOUNDARIES"] == {
        "JOURNEY_RUNTIME_CONTROLLER_CHANGED": False,
        "AUDIO_CHANGED": False,
        "APP_PY_CHANGED": False,
        "GAMEPLAY_CHANGED": False,
        "DB_SCHEMA_CHANGED": False,
        "PRODUCTION_MUTATED": False,
        "MERGED": False,
        "DEPLOYED": False,
    }
    assert handoff["VALIDATION"]["READY_FOR_FINAL_JOURNEY_BINDING"] is True
