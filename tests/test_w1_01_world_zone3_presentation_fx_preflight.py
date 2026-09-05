"""Bounded content contracts for the Zone 3 presentation FX preflight.

This test file validates planning data only. It intentionally does not import
app.py or execute Journey, cinematic, audio, progression, reward, or database
runtime code.
"""

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / (
    "docs/planning/w1_01_world_zone3_presentation_fx_cue_manifest_008a.json"
)
CINEMATIC_MANIFEST_PATH = ROOT / (
    "assets/e10/art/zone3/cinematic/zone3-cinematic-asset-package.json"
)

EXPECTED_SOURCE_HEAD = "39c587a216f6cc13efe572066d9d8f0299960f1b"
EXPECTED_SOURCE_TREE = "676da3ddd4456b83aaa591e830a7adf4dab5c161"
EXPECTED_CATEGORIES = {
    "AMBIENCE",
    "SFX",
    "VFX",
    "LIGHT",
    "CHARACTER_FX",
    "TRANSITION",
}
EXPECTED_AUDIO_IDS = {
    "CAVE_ROOM_TONE",
    "DISTANT_CAVE_WIND",
    "WATER_DRIP",
    "REFUGEE_FOOTSTEPS",
    "BELONGINGS_MOVEMENT",
    "DISTANT_FAMILY_ACTIVITY",
    "SHUI_WATER_SPIRIT_SOUND",
    "ROCKFALL",
    "BLOCKED_WATER_FLOW",
    "CENTURION_ARMOR",
    "CENTURION_SPEAR_PLANT",
    "TRIAL_TENSION_AMBIENCE",
    "FRAGILE_TRUCE_AMBIENCE",
    "STONE_SHARD_PHYSICAL_HANDOFF",
    "MISTY_FOREST_WIND_TRANSITION",
}
EXPECTED_VFX_IDS = {
    "CAVE_DUST_MOTES",
    "SUBTLE_WARM_LIGHT_FLICKER",
    "WATER_REFLECTION_SHIMMER",
    "SHUI_WATER_PARTICLES",
    "SHUI_TRANSLUCENT_PULSE",
    "ROCK_DUST_FALL",
    "SMALL_ROCK_DEBRIS",
    "BLOCKED_WATER_MIST",
    "CENTURION_SPEAR_DUST_IMPULSE",
    "TRIAL_SUBTLE_ENVIRONMENT_TENSION",
    "TRUCE_ENVIRONMENT_CALMING",
    "MISTY_FOREST_FOG_TRANSITION",
}
EXPECTED_CONTENT_FIELDS = {
    "CUE_ID",
    "SHOT_ID",
    "CATEGORY",
    "STORY_PURPOSE",
    "INTENSITY",
    "LOOP",
    "ASSET_REQUIRED",
    "REUSABLE_EXISTING_ASSET",
    "NEW_ASSET_REQUIRED",
}
EXPECTED_HANDOFF_FIELDS = {
    "CUE_ID",
    "SHOT_ID",
    "CATEGORY",
    "ASSET_PATH_OR_PLACEHOLDER",
    "LOOP",
    "INTENSITY",
    "DIALOGUE_DUCKING_RECOMMENDED",
    "REDUCED_MOTION_RECOMMENDATION",
    "REPLAY_RECOMMENDATION",
}
EXPECTED_SHOTS = {f"SHOT{number:02d}" for number in range(1, 11)}


def _load_manifest():
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_metadata_and_current_zone_audit_are_pinned():
    manifest = _load_manifest()
    assert manifest["SOURCE_WORLD_HEAD"] == EXPECTED_SOURCE_HEAD
    assert manifest["SOURCE_WORLD_TREE"] == EXPECTED_SOURCE_TREE
    assert manifest["JOURNEY_REFERENCE_ONLY"] is True
    assert manifest["JOURNEY_REFERENCE_HEAD"] == (
        "f77bce46302974c8a8aa9d296ae0ea548a707691"
    )
    assert manifest["OWNER_STYLE"] == "B — STYLIZED_ADVENTURE"
    assert manifest["ZONE"] == {
        "ZONE_ID": 3,
        "ZONE_KEY": "k16_20",
        "NAME_ZH": "哥布林洞穴",
        "NAME_EN": "Goblin Cave",
        "IDENTITY_AUTHORITY": "current runtime/API identity at SOURCE_WORLD_HEAD",
        "LORD_IDENTITY": "哥布林百夫長 / Goblin Centurion",
    }
    assert manifest["AUDIT"]["ZONE3"] == {
        "AMBIENCE_ASSETS_PRESENT": False,
        "EVENT_SFX_ASSETS_PRESENT": False,
        "VFX_ASSETS_PRESENT": False,
        "SHUI_AUDIO_ASSETS_PRESENT": False,
        "TRANSITION_ASSETS_PRESENT": False,
        "STATIC_CINEMATIC_ART_EXCLUDED_FROM_FX_AUDIT": True,
        "CURRENT_ART_PACKAGE": "assets/e10/art/zone3/ (10 cinematic shots, 1 landmark, 1 environment plate)",
        "EVIDENCE": [
            "assets/e10/audio/zone3/ does not exist at the source head",
            "assets/e10/art/zone3/ contains approved visual art only",
            "no dedicated assets/e10/vfx/zone3 or equivalent Zone 3 effect root exists",
        ],
    }


def test_zone1_zone2_audit_and_bee_boundary_are_explicit():
    manifest = _load_manifest()
    zone1 = manifest["AUDIT"]["ZONE1"]
    zone2 = manifest["AUDIT"]["ZONE2"]
    assert (zone1["AMBIENCE_PRESENT"], zone1["AMBIENCE_ASSET_COUNT"]) == (
        True,
        1,
    )
    assert (zone1["SFX_PRESENT"], zone1["SFX_ASSET_COUNT"]) == (True, 4)
    assert zone1["VFX_DEDICATED_ASSET_COUNT"] == 0
    assert (zone2["AMBIENCE_PRESENT"], zone2["AMBIENCE_ASSET_COUNT"]) == (
        True,
        4,
    )
    assert (zone2["SFX_PRESENT"], zone2["SFX_ASSET_COUNT"]) == (True, 10)
    assert zone2["VFX_DEDICATED_ASSET_COUNT"] == 0
    assert zone2["BEE_AUDIO_PATHS"] == [
        "assets/e10/audio/zone2/sfx/zone2_ambient_bee_distant.mp3",
        "assets/e10/audio/zone2/sfx/zone2_sfx_bee_close.mp3",
    ]
    assert zone2["BEE_CONTENT_ROLE"] == "AMBIENT_SWARM_PRESSURE_ONLY"
    assert "NO_DEDICATED_BEE_ART_OR_BEE_EFFECT_FOUND" in (
        zone2["BEE_VISUAL_ASSET_OR_EFFECT"]
    )
    assert "Slime Swarm Lord" in zone2["BEE_VISUAL_ASSET_OR_EFFECT"]


def test_audio_evaluation_covers_exact_requested_set_and_reuse_counts():
    manifest = _load_manifest()
    audio = manifest["AUDIO_EVALUATION"]
    assert len(audio) == 15
    assert {item["ID"] for item in audio} == EXPECTED_AUDIO_IDS
    assert {item["STATUS"] for item in audio} == {"REQUIRED"}
    safe_reuse = [item for item in audio if item["CLASSIFICATION"] == "SAFE_REUSE"]
    new_assets = [
        item for item in audio if item["CLASSIFICATION"] == "NEW_ASSET_REQUIRED"
    ]
    assert len(safe_reuse) == 2
    assert len(new_assets) == 13
    assert {
        item["ID"] for item in safe_reuse
    } == {"SHUI_WATER_SPIRIT_SOUND", "STONE_SHARD_PHYSICAL_HANDOFF"}
    assert manifest["ASSET_REUSE_INVENTORY"]["COUNT_REPORT"] == {
        "REUSABLE_AUDIO_ASSET_COUNT": 2,
        "REUSABLE_VFX_ASSET_COUNT": 0,
        "NEW_AUDIO_ASSET_COUNT_REQUIRED": 13,
        "NEW_VFX_ASSET_COUNT_REQUIRED": 0,
        "CODE_ONLY_VFX_COUNT": 12,
    }
    assert manifest["ASSET_REUSE_INVENTORY"]["BEE_AUDIO_REUSE"].startswith(
        "REJECTED_FOR_ZONE3"
    )


def test_vfx_evaluation_covers_exact_requested_set_and_is_code_only():
    manifest = _load_manifest()
    vfx = manifest["VFX_EVALUATION"]
    assert len(vfx) == 12
    assert {item["ID"] for item in vfx} == EXPECTED_VFX_IDS
    assert {item["STATUS"] for item in vfx} == {"REQUIRED", "OPTIONAL"}
    assert [item["ID"] for item in vfx if item["STATUS"] == "OPTIONAL"] == [
        "SHUI_TRANSLUCENT_PULSE"
    ]
    assert all(item["ASSET_REQUIRED"] is False for item in vfx)
    assert all(item["CLASSIFICATION"] == "CODE_ONLY_VFX" for item in vfx)


def test_cue_sheet_has_exact_content_and_later_binding_fields_without_triggers():
    manifest = _load_manifest()
    cues = manifest["CUE_SHEET"]
    assert len(cues) == 26
    assert len({cue["CUE_ID"] for cue in cues}) == len(cues)
    assert all(EXPECTED_CONTENT_FIELDS <= cue.keys() for cue in cues)
    assert all(EXPECTED_HANDOFF_FIELDS <= cue.keys() for cue in cues)
    assert all(cue["CATEGORY"] in EXPECTED_CATEGORIES for cue in cues)
    assert all(set(cue["SHOT_ID"]) <= EXPECTED_SHOTS for cue in cues)
    assert all(cue["SHOT_ID"] for cue in cues)
    assert all(
        cue["RUNTIME_TRIGGER_CODE"] == "NOT_DEFINED_IN_008A" for cue in cues
    )
    assert all(
        cue["REPLAY_RECOMMENDATION"] == "REUSE_PRESENTATION_NO_REWARD"
        for cue in cues
    )
    assert all(
        cue["DIALOGUE_DUCKING_RECOMMENDED"] in {"YES", "NO"} for cue in cues
    )


def test_cue_counts_match_required_content_contract():
    manifest = _load_manifest()
    cues = manifest["CUE_SHEET"]
    status_by_id = {
        item["ID"]: item["STATUS"]
        for item in manifest["VFX_EVALUATION"] + manifest["AUDIO_EVALUATION"]
    }
    summary = manifest["COUNT_SUMMARY"]
    assert sum(cue["CATEGORY"] == "AMBIENCE" for cue in cues) == summary[
        "ZONE3_REQUIRED_AMBIENCE_COUNT"
    ]
    assert sum(cue["CATEGORY"] == "SFX" for cue in cues) == summary[
        "ZONE3_REQUIRED_EVENT_SFX_COUNT"
    ]
    assert sum(
        cue["CATEGORY"] == "VFX"
        and status_by_id[cue["EVALUATION_ID"]] == "REQUIRED"
        for cue in cues
    ) == summary["ZONE3_REQUIRED_VFX_COUNT"]
    assert sum(cue["CATEGORY"] == "TRANSITION" for cue in cues) == summary[
        "ZONE3_REQUIRED_TRANSITION_COUNT"
    ]
    assert sum(
        cue["CATEGORY"] == "VFX"
        and status_by_id[cue["EVALUATION_ID"]] == "OPTIONAL"
        for cue in cues
    ) == summary["ZONE3_OPTIONAL_VFX_COUNT"]
    assert summary["ZONE3_TOTAL_PRESENTATION_CUE_COUNT"] == len(cues)


def test_story_contracts_protect_shui_centurion_and_stone_shard():
    manifest = _load_manifest()
    story = manifest["STORY_CONTRACTS"]
    assert story["GRIK_MONSTROUS"] is False
    assert story["CENTURION_DEMONIC"] is False
    assert story["STONE_SHARD_MAGICAL"] is False
    assert story["FRAGILE_TRUCE_CELEBRATORY"] is False
    assert story["SHUI_HUMAN_SPEAKING"] is False
    assert story["STONE_SHARD_MAGICAL_SFX_COUNT"] == 0
    assert story["STONE_SHARD_MAGICAL_VFX_COUNT"] == 0
    assert story["SHUI_NONVERBAL_FX_CONTRACT"] == "PASS"
    assert story["CENTURION_PROTECTOR_FX_CONTRACT"] == "PASS"
    shard = story["STONE_SHARD_CONTRACT"]
    assert shard == {
        "ordinary": True,
        "non_glowing": True,
        "irregular": True,
        "natural_marks_only": True,
        "magic_map": False,
        "rune_artifact": False,
        "gameplay_authority_object": False,
    }


def test_approved_ten_shot_source_masters_still_resolve_to_recorded_hashes():
    manifest = json.loads(CINEMATIC_MANIFEST_PATH.read_text(encoding="utf-8"))
    assert manifest["source_shot_count"] == 10
    assert manifest["runtime_derivative_count"] == 10
    for shot in manifest["shots"]:
        source = ROOT / shot["SOURCE_PATH"]
        assert source.is_file()
        assert _sha256(source) == shot["SOURCE_SHA256"]
        assert shot["OWNER_APPROVED"] == "YES"
    assert manifest["runtime_delivery"]["source_master_untouched"] is True


def test_device_handoff_and_runtime_boundaries_remain_closed():
    manifest = _load_manifest()
    assert manifest["DEVICE_PERFORMANCE_CONTRACT"]["LOW_END_DEVICE_SAFE_DESIGN"]
    assert manifest["JOURNEY_HANDOFF"] == {
        "READY_FOR_JOURNEY_RUNTIME_BINDING": True,
        "RUNTIME_BINDING_IMPLEMENTED": False,
        "JOURNEY_REFERENCE_ONLY": True,
        "SPEC_IS_MACHINE_READABLE": True,
        "REQUIRED_FIELDS": [
            "CUE_ID",
            "SHOT_ID",
            "CATEGORY",
            "ASSET_PATH_OR_PLACEHOLDER",
            "LOOP",
            "INTENSITY",
            "DIALOGUE_DUCKING_RECOMMENDED",
            "REDUCED_MOTION_RECOMMENDATION",
            "REPLAY_RECOMMENDATION",
        ],
        "REPLAY_RULE": "Presentation may replay the same cue paths; it must not issue rewards, consume items, alter Zone state, or create gameplay authority.",
        "OPEN_RUNTIME_DEPENDENCY": "Later Journey work must bind cues to existing shot lifecycle without changing the approved source art or shared shell in this task.",
    }
    assert all(value is False for key, value in manifest["BOUNDARIES"].items() if key != "LOW_END_DEVICE_SAFE_DESIGN")
