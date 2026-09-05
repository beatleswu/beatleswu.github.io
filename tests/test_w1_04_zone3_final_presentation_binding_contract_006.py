"""Contract-only Zone 3 presentation binding scaffold.

This file intentionally does not import the Journey controller or create audio
files.  It validates the immutable handoff contract and negative controls so
the later single-writer task can consume exact external manifests when they
arrive.
"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "docs" / "contracts" / "w1_04_zone3_final_presentation_binding_contract_006.json"
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "w1_04_zone3_final_presentation_binding_external_inputs_006.json"
DOD_PATH = ROOT / "docs" / "audits" / "w1_04_zone3_40item_dod_evidence_reconciled_matrix_005.json"


def _load(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def test_contract_schema_and_expected_component_counts() -> None:
    contract = _load(CONTRACT_PATH)

    assert contract["schema_version"] == "W1_04_ZONE3_FINAL_PRESENTATION_BINDING_CONTRACT_V1"
    assert contract["scope"]["binding_implemented"] is False
    assert contract["scope"]["journey_runtime_changed"] is False
    assert contract["scope"]["app_py_changed"] is False

    components = contract["expected_components"]
    cinematic = components["cinematic_shots"]
    assert cinematic["count"] == 10
    assert cinematic["sequence"] == [f"SHOT{i:02d}" for i in range(1, 11)]
    assert len(components["world_support_images"]["paths"]) == 2
    assert components["normal_monsters"]["count"] == 13
    assert components["normal_monsters"]["elite_count"] == 0
    assert components["battlefield_boss"]["runtime_id"] == "legacy_bf_03_boss"
    assert components["battlefield_boss"]["distinct_from_lord"] is True
    assert components["lord"]["lord_id"] == "goblin_centurion"
    assert components["lord"]["asset_count"] == 6
    assert components["visual_fx"]["count"] == 12
    assert components["visual_fx"]["camera_cue_count"] == 10


def test_locale_contract_is_complete_and_cross_language_fallback_is_forbidden() -> None:
    locales = _load(CONTRACT_PATH)["locale_contract"]

    assert locales["supported_production_locales"] == ["zh-TW", "en-US"]
    assert locales["cross_language_voice_fallback"] == 0
    assert locales["voice_language_mismatch"] == "FORBIDDEN"
    for locale, language in (("zh-TW", "zh"), ("en-US", "en")):
        entry = locales["locales"][locale]
        assert entry["subtitle_beats"] == 97
        assert entry["dialogue_voice_beats"] == 97
        assert entry["voice_language"] == language
        assert entry["subtitle_manifest_ref"]["path"]
        assert entry["voice_manifest_ref"]["path"]


def test_missing_locale_voice_is_subtitle_only_and_fail_closed() -> None:
    contract = _load(CONTRACT_PATH)
    locale = contract["locale_contract"]

    assert locale["fallback_policy"] == "subtitle-only; fail closed"
    assert any("never selects another locale voice" in rule for rule in locale["switch_rules"])
    assert locale["cross_language_voice_fallback"] == 0


def test_global_mute_covers_all_zone3_audio_classes_without_new_mixer_ui() -> None:
    controls = _load(CONTRACT_PATH)["audio_controls"]

    assert controls["global_mute_required"] is True
    assert controls["new_volume_slider"] is False
    assert controls["new_audio_mixer_ui"] is False
    assert controls["muted_audio_classes"] == ["dialogue", "ambience", "SFX", "BGM", "transition"]
    assert controls["preserve_existing_fixed_playback_level_architecture"] is True


def test_replay_cases_preserve_sequence_and_have_no_persistent_mutation() -> None:
    replay = _load(CONTRACT_PATH)["replay_contract"]
    expected = [f"SHOT{i:02d}" for i in range(1, 11)]

    assert replay["cases"]["FIRST_ENTRY"] == expected[:5]
    assert replay["cases"]["BOSS_READY"] == expected[5:7]
    assert replay["cases"]["POST_CLEAR"] == expected[7:]
    assert replay["cases"]["REPLAY"] == expected
    assert all(value is False for value in replay["persistent_mutations"].values())


def test_reduced_motion_preserves_story_audio_and_gameplay() -> None:
    reduced = _load(CONTRACT_PATH)["reduced_motion_contract"]

    assert reduced["story_content_available"] is True
    assert reduced["audio_semantics_unchanged"] is True
    assert reduced["gameplay_affected"] is False
    assert "reduced/disabled" in reduced["camera_motion"]


def test_cleanup_contract_covers_all_exit_and_switch_boundaries() -> None:
    cleanup = _load(CONTRACT_PATH)["cleanup_contract"]
    required_points = {"shot_change", "locale_change", "replay", "cinematic_exit", "route_exit", "runtime_presentation_failure"}
    required_resources = {"audio loops", "timers", "animation frames", "particle emitters", "event listeners", "temporary DOM nodes", "media objects"}

    assert required_points.issubset(set(cleanup["cleanup_points"]))
    assert required_resources.issubset(set(cleanup["owned_resources"]))
    assert all(value is False for key, value in cleanup["post_cleanup_requirements"].items() if key != "gameplay_available")
    assert cleanup["post_cleanup_requirements"]["gameplay_available"] is True


def test_presentation_failure_is_a_gameplay_noop() -> None:
    failure = _load(CONTRACT_PATH)["failure_contract"]
    authority = _load(CONTRACT_PATH)["authority_boundary"]

    assert failure["presentation_failure_must_not_block_gameplay"] is True
    assert len(failure["failures"]) >= 7
    assert authority["presentation_write_authority"] is False
    assert authority["asset_or_locale_event_authority_writes"] == 0


def test_lord_boss_and_monster_boundaries_are_explicit() -> None:
    components = _load(CONTRACT_PATH)["expected_components"]
    authority = _load(CONTRACT_PATH)["authority_boundary"]

    assert components["normal_monsters"]["count"] == len(components["normal_monsters"]["ids"]) == 13
    assert components["normal_monsters"]["elite_count"] == 0
    assert components["battlefield_boss"]["runtime_id"] == "legacy_bf_03_boss"
    assert components["battlefield_boss"]["lord_id"] == "goblin_centurion"
    assert components["battlefield_boss"]["distinct_from_lord"] is True
    assert components["lord"]["asset_count"] == len(components["lord"]["slot_ids"]) == 6
    assert "Battlefield Boss-to-Lord conversion" in authority["presentation_must_not_invoke"]


def test_external_audio_dependency_is_present_without_fake_or_placeholder_assets() -> None:
    contract = _load(CONTRACT_PATH)
    fixture = _load(FIXTURE_PATH)
    dependencies = fixture["external_dependencies"]

    assert contract["scaffold_rules"]["audio_manifest_required_to_run_now"] is False
    assert contract["scaffold_rules"]["fake_production_audio_allowed"] is False
    assert contract["scaffold_rules"]["placeholder_audio_assets_allowed"] is False
    assert len(dependencies) == 2
    assert {item["status"] for item in dependencies} == {"EXTERNAL_DEPENDENCY_PENDING"}
    assert all(item["provided"] is False for item in dependencies)
    assert all(item["manifest_path"] is None for item in dependencies)
    assert all(item["placeholder_assets_allowed"] is False for item in dependencies)
    assert all(item["must_not_generate"] is True for item in dependencies)


def test_master_dod_mapping_only_references_existing_open_items() -> None:
    contract = _load(CONTRACT_PATH)
    dod = _load(DOD_PATH)
    valid_ids = {item["ITEM_ID"] for item in dod["ITEMS"]}
    open_ids = set(dod["OPEN_REQUIRED_ITEMS"])
    mapped_ids = {
        item_id
        for item_ids in contract["master_dod_mapping"].values()
        if isinstance(item_ids, list)
        for item_id in item_ids
    }

    assert mapped_ids <= valid_ids
    assert mapped_ids <= open_ids


def test_no_authority_mutation_is_admitted_by_contract() -> None:
    authority = _load(CONTRACT_PATH)["authority_boundary"]

    assert authority["selected_zone_is_not_progression_zone"] is True
    assert authority["cinematic_completion_is_not_zone_clear"] is True
    assert authority["replay_is_not_reward_replay"] is True
    assert authority["asset_or_locale_event_authority_writes"] == 0
    for forbidden in ("zone clear", "zone unlock/progression mutation", "reward grant/regrant", "Lord eligibility or Lord defeat", "purchase", "equip", "payment or revenue authority"):
        assert forbidden in authority["presentation_must_not_invoke"]
