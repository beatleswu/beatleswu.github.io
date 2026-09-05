"""Focused contract tests for the standalone Zone 3 presentation package.

These tests intentionally inspect only the package contract and do not import
the application or any gameplay authority module.
"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_008A = ROOT / "docs/planning/w1_01_world_zone3_presentation_fx_cue_manifest_008a.json"
PACKAGE = ROOT / "docs/planning/w1_01_world_zone3_presentation_fx_runtime_package_009.json"
MODULE = ROOT / "js/e9/zone3_presentation_fx.js"
STYLES = ROOT / "css/e9/zone3_presentation_fx.css"

EXPECTED_EFFECTS = [
    ("Z3_L01", "SUBTLE_WARM_LIGHT_FLICKER"),
    ("Z3_V01", "CAVE_DUST_MOTES"),
    ("Z3_V02", "WATER_REFLECTION_SHIMMER"),
    ("Z3_V03", "SHUI_WATER_PARTICLES"),
    ("Z3_V04", "SHUI_TRANSLUCENT_PULSE"),
    ("Z3_V05", "ROCK_DUST_FALL"),
    ("Z3_V06", "SMALL_ROCK_DEBRIS"),
    ("Z3_V07", "BLOCKED_WATER_MIST"),
    ("Z3_V08", "CENTURION_SPEAR_DUST_IMPULSE"),
    ("Z3_V09", "TRIAL_SUBTLE_ENVIRONMENT_TENSION"),
    ("Z3_V10", "TRUCE_ENVIRONMENT_CALMING"),
    ("Z3_T01_VISUAL", "MISTY_FOREST_FOG_TRANSITION"),
]

EXPECTED_SHOTS = [
    "SHOT01", "SHOT02", "SHOT03", "SHOT04", "SHOT05",
    "SHOT06", "SHOT07", "SHOT08", "SHOT09", "SHOT10",
]


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_package_files_exist_and_point_to_008a() -> None:
    assert SOURCE_008A.is_file()
    assert PACKAGE.is_file()
    assert MODULE.is_file()
    assert STYLES.is_file()
    package = read_json(PACKAGE)
    assert package["SOURCE_008A_MANIFEST"] == (
        "docs/planning/w1_01_world_zone3_presentation_fx_cue_manifest_008a.json"
    )
    assert package["SOURCE_HEAD"] == "00dd5e07e67f2a83e9eb5a06b04d498e72af2e6d"
    assert package["SOURCE_TREE"] == "fe6a277126d2f89bd88c993d92cd82012490f14c"


def test_exact_12_effect_ids_and_008a_consumption() -> None:
    source = read_json(SOURCE_008A)
    package = read_json(PACKAGE)
    expected_ids = [effect_id for effect_id, _ in EXPECTED_EFFECTS]
    package_effects = package["EFFECTS"]
    assert len(package_effects) == 12
    assert [entry["EFFECT_ID"] for entry in package_effects] == expected_ids
    source_by_cue = {entry["CUE_ID"]: entry for entry in source["CUE_SHEET"]}
    for effect_id, name in EXPECTED_EFFECTS:
        entry = next(item for item in package_effects if item["EFFECT_ID"] == effect_id)
        assert entry["NAME"] == name
        assert entry["CUE_ID"] in source_by_cue
        assert source_by_cue[entry["CUE_ID"]]["CATEGORY"] in {"LIGHT", "VFX", "TRANSITION"}
        evaluation_id = source_by_cue[entry["CUE_ID"]]["EVALUATION_ID"]
        if isinstance(evaluation_id, list):
            assert name in evaluation_id
        else:
            assert evaluation_id == name


def test_zone_identity_and_style_are_preserved() -> None:
    package = read_json(PACKAGE)
    assert package["ZONE"] == {
        "KEY": "k16_20",
        "NAME_ZH": "哥布林洞穴",
        "NAME_EN": "Goblin Cave",
        "STYLE": "STYLIZED_ADVENTURE",
    }
    assert package["BOUNDARIES"]["PARALLAX_IMPLEMENTED"] is False
    assert package["BOUNDARIES"]["PARALLAX_RECOMMENDED_CLASSIFICATION"] == (
        "INTENTIONALLY_DIFFERENT_NOT_REQUIRED_FOR_ZONE3_V1"
    )


def test_all_ten_camera_cues_are_explicit_and_restrained() -> None:
    package = read_json(PACKAGE)
    cues = package["CAMERA_CUES"]
    assert list(cues) == EXPECTED_SHOTS
    assert len(cues) == 10
    allowed_modes = {
        "slow_push", "slow_drift", "static_hold",
        "bounded_impact_impulse", "slow_pull",
    }
    for shot_id in EXPECTED_SHOTS:
        cue = cues[shot_id]
        assert cue["MODE"] in allowed_modes
        assert cue["REDUCED_MOTION"] == "STATIC_HOLD"
        assert "rotation" not in json.dumps(cue).lower()
    assert cues["SHOT05"]["AMPLITUDE_PX"] == 2
    assert cues["SHOT07"]["AMPLITUDE_PX"] == 1
    assert cues["SHOT05"]["REPETITIONS"] == 1
    assert cues["SHOT07"]["REPETITIONS"] == 1


def test_shot_effect_mapping_preserves_the_accepted_visual_intent() -> None:
    package = read_json(PACKAGE)
    assert list(package["SHOT_EFFECTS"]) == EXPECTED_SHOTS
    assert package["SHOT_EFFECTS"]["SHOT01"] == ["Z3_L01", "Z3_V01"]
    assert package["SHOT_EFFECTS"]["SHOT03"] == ["Z3_L01", "Z3_V01", "Z3_V03"]
    assert package["SHOT_EFFECTS"]["SHOT04"] == ["Z3_L01", "Z3_V01"]
    assert package["SHOT_EFFECTS"]["SHOT05"] == [
        "Z3_L01", "Z3_V01", "Z3_V02", "Z3_V03", "Z3_V05", "Z3_V06", "Z3_V07",
    ]
    assert package["SHOT_EFFECTS"]["SHOT07"] == ["Z3_L01", "Z3_V01", "Z3_V08", "Z3_V09"]
    assert package["SHOT_EFFECTS"]["SHOT08"] == ["Z3_L01", "Z3_V01", "Z3_V03", "Z3_V10"]
    assert package["SHOT_EFFECTS"]["SHOT09"] == ["Z3_L01", "Z3_V01"]
    assert package["SHOT_EFFECTS"]["SHOT10"] == ["Z3_L01", "Z3_V01", "Z3_T01_VISUAL"]
    assert package["SHOT_OPTIONAL_EFFECTS"] == {
        "SHOT03": ["Z3_V04"],
        "SHOT05": ["Z3_V04"],
        "SHOT08": ["Z3_V04"],
    }


def test_story_guards_keep_shard_ordinary_and_characters_grounded() -> None:
    package = read_json(PACKAGE)
    guards = package["STORY_GUARDS"]
    assert guards["STONE_SHARD_MAGIC_GLOW"] == "NO"
    assert guards["STONE_SHARD_MAGIC_PARTICLES"] == "NO"
    assert guards["STONE_SHARD_RUNE_EFFECT"] == "NO"
    assert guards["SHUI_NONVERBAL_VISUAL_CONTRACT"] == "PASS"
    assert guards["CENTURION_PROTECTOR_VISUAL_CONTRACT"] == "PASS"
    assert guards["SHOT08_NO_VICTORY_FIREWORKS"] is True
    assert guards["SHOT10_NO_ZONE4_UNLOCK"] is True


def test_reduced_motion_and_lifecycle_contracts_are_complete() -> None:
    package = read_json(PACKAGE)
    lifecycle = package["LIFECYCLE"]
    assert package["VALIDATION"]["REDUCED_MOTION_COVERAGE"] == (
        "12/12 visual effects plus all camera cues"
    )
    assert set(lifecycle["API"]) >= {
        "create", "start", "stop", "stopAll", "startCameraCue",
        "stopCamera", "transitionShot", "getResourceStats", "destroy",
    }
    assert set(lifecycle["CLEANUP_POINTS"]) == {
        "shot_change", "cinematic_exit", "replay_exit", "route_change",
        "interruption", "error",
    }
    assert lifecycle["POST_CLEANUP"] == {
        "ACTIVE_TIMER_COUNT": 0,
        "ACTIVE_RAF_COUNT": 0,
        "TEMPORARY_EFFECT_NODE_COUNT": 0,
        "ACTIVE_EVENT_LISTENER_COUNT": 0,
    }
    assert lifecycle["FAILURE_BEHAVIOR"] == "STATIC_PRESENTATION_CONTINUES"


def test_implementation_contains_every_effect_and_browser_motion_hooks() -> None:
    source = MODULE.read_text(encoding="utf-8")
    styles = STYLES.read_text(encoding="utf-8")
    for effect_id, name in EXPECTED_EFFECTS:
        assert f"'{effect_id}'" in source
        assert name in source
        css_slug = effect_id.lower().replace("_", "-")
        assert f"z3-effect-{css_slug}" in styles
    assert "prefers-reduced-motion" in styles
    assert "requestAnimationFrame" in source
    assert "cancelAnimationFrame" in source
    assert "removeEventListener" in source
    assert "STATIC_PRESENTATION_CONTINUES" in source
    assert "getShotEffects" in source


def test_no_runtime_authority_or_audio_hooks_are_present() -> None:
    source = MODULE.read_text(encoding="utf-8")
    forbidden_tokens = (
        "fetch(", "XMLHttpRequest", "localStorage", "sessionStorage",
        "indexedDB", "awardReward", "grantReward", "unlockZone",
        "setZoneClear", "inventory", "mastery",
    )
    for token in forbidden_tokens:
        assert token not in source
    package = read_json(PACKAGE)
    assert package["BOUNDARIES"]["GAMEPLAY_AUTHORITY_EFFECT_COUNT"] == 0
    assert package["BOUNDARIES"]["NEW_AUDIO_FILE_COUNT"] == 0
    assert package["BOUNDARIES"]["AUDIO_IMPLEMENTED"] is False


def test_no_raster_or_journey_binding_is_claimed() -> None:
    package = read_json(PACKAGE)
    boundaries = package["BOUNDARIES"]
    journey = package["JOURNEY_BINDING"]
    assert boundaries["NEW_RASTER_ASSET_COUNT"] == 0
    assert boundaries["VOICE_FILE_COUNT_CHANGED"] == 0
    assert boundaries["JOURNEY_RUNTIME_CONTROLLER_CHANGED"] is False
    assert boundaries["INDEX_HTML_SHARED_RUNTIME_CHANGED"] is False
    assert boundaries["APP_PY_CHANGED"] is False
    assert boundaries["GAMEPLAY_AUTHORITY_CHANGED"] is False
    assert journey["READY"] is True
    assert journey["IMPLEMENTED"] is False
