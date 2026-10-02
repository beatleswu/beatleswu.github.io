"""Validator for the Owner-approved Zone 3 voice-lock succession."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "tests" / "governance" / "g009_w1_zone3_voice_locks_successor_registry.json"

VOICE_NODE_IDS = [
    "tests/test_w1_03_journey_zone3_en_us_full_97beat_british_voice_production_008.py::test_zh_tw_surfaces_are_source_unchanged_and_no_cross_language_fallback",
    "tests/test_w1_03_journey_zone3_en_us_script_and_voice_authority_recovery_007.py::test_protected_accepted_zone3_zh_tw_surfaces_match_source_bytes",
    "tests/test_w1_03_journey_zone3_final_audio_production.py::test_hero_runtime_audio_is_byte_identical_to_locked_base",
]

SUCCESSOR_NODE_IDS = [
    "tests/test_w1_03_journey_zone3_final_qa_blocker_repair.py::test_repair_runtime_seams_remain_presentation_only",
    "tests/test_w1_03_journey_zone3_final_qa_blocker_repair_012.py::test_runner_keeps_the_default_gate_bounded_and_complete",
    "tests/test_w1_03_journey_zone3_final_qa_blocker_repair_012.py::test_route_cleanup_invalidates_zone3_presentation_only_state",
    "tests/test_w1_04_zone3_final_presentation_binding_contract_006.py::test_global_mute_covers_all_zone3_audio_classes_without_new_mixer_ui",
    "tests/test_w1_03_journey_zone3_i18n_subtitle_voice_production.py::test_canonical_manifest_covers_all_ten_shots_and_exact_beats",
    "tests/test_w1_03_journey_zone3_i18n_subtitle_voice_production.py::test_audio_manifest_is_locale_scoped_and_subtitle_aligned",
    "tests/test_w1_03_journey_zone3_i18n_subtitle_voice_production.py::test_replay_and_locale_contract_is_presentation_only",
    "tests/test_w1_03_journey_zone3_vertical_slice_wiring.py::test_manifest_is_explicit_and_style_lock_safe",
    "tests/test_w1_03_journey_zone3_vertical_slice_wiring.py::test_controller_is_presentation_only_and_has_authority_guards",
    "tests/test_w1_04_zone3_final_presentation_binding_contract_006.py::test_locale_contract_is_complete_and_cross_language_fallback_is_forbidden",
    "tests/test_w1_04_zone3_final_presentation_binding_contract_006.py::test_missing_locale_voice_is_subtitle_only_and_fail_closed",
    "tests/test_w1_04_zone3_final_presentation_binding_contract_006.py::test_cleanup_contract_covers_all_exit_and_switch_boundaries",
]

EXPECTED_SUCCESSOR_FIELDS = {
    "AUDIO_OWNER_COUNT": 1,
    "PLAYBACK_OWNER_COUNT": 1,
    "ENTER_STATE": "PASS",
    "EXIT_STATE": "PASS",
    "CLEANUP_PASS": "YES",
    "REPLAY_DUPLICATION": "NO",
    "ORIENTATION_DUPLICATION": "NO",
    "CROSS_ZONE_LEAK": "NO",
}


def _node_exists(node: str) -> bool:
    relative_path, function_node = node.split("::", 1)
    path = ROOT / relative_path
    if not path.is_file():
        return False
    function_name = function_node.split("[", 1)[0]
    source = path.read_text(encoding="utf-8")
    return re.search(rf"^(?:async\s+)?def\s+{re.escape(function_name)}\s*\(", source, re.M) is not None


def test_voice_locks_three_of_three_are_formally_superseded_by_semantic_successor():
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    assert registry["schema"] == "g009-protected-test-successor-registry-v1"
    assert registry["scope"] == "test-governance-only"
    assert registry["registration_date"] == "2026-10-02"
    assert registry["resulting_commit"] == "POST_COMMIT_OUTPUT_HEAD"
    assert registry["resulting_commit_binding"]
    assert registry["owner_gate"] == "G009_OWNER_GATE_ZONE3_VOICE_LOCKS_AUTHORITY_001"
    assert registry["owner_gate_status"] == "AUTHORIZED"
    assert registry["semantic_successor"]["SUCCESSOR_PASS"] is True
    assert registry["semantic_successor"]["CORRECT_LOCALE_CHARACTER_BINDING"] == "YES"
    assert registry["semantic_successor"]["GOVERNED_MANIFEST_OR_RUNTIME_ROUTING"] == "PASS"
    for key, value in EXPECTED_SUCCESSOR_FIELDS.items():
        assert registry["semantic_successor"][key] == value

    entries = registry["entries"]
    assert len(entries) == len(VOICE_NODE_IDS) == 3
    assert [entry["old_protected_node_identity"] for entry in entries] == VOICE_NODE_IDS
    assert all(_node_exists(node) for node in VOICE_NODE_IDS)

    for entry in entries:
        assert entry["old_node_presence"] == "PRESENT"
        assert entry["status"] == "SUPERSEDED"
        assert entry["old_contract"] == "EXACT_VOICE_BYTE_OR_SHA_LOCK"
        assert entry["retirement_or_supersession_reason"] == "OWNER_RETIRED_BYTE_HASH_LOCK"
        assert entry["successor_contract"] == "ZONE3_AUDIO_SEMANTIC_CONTRACT"
        assert entry["owner_gate"] == "G009_OWNER_GATE_ZONE3_VOICE_LOCKS_AUTHORITY_001"
        assert entry["successor_evidence"] == "G009_W1_ZONE3_AUDIO_BINDING_EVIDENCE_CLOSURE_001"
        assert entry["successor_pass_required_before_retirement"] is True
        assert entry["old_authority_source"]["historical_pin_commit"]
        assert entry["old_authority_source"]["historical_pin_path"]
        assert entry["old_byte_or_sha_expectation"]
        assert all(
            re.fullmatch(r"[0-9a-f]{64}", item["sha256"])
            and isinstance(item["bytes"], int)
            and item["bytes"] > 0
            for item in entry["old_byte_or_sha_expectation"]
        )
        assert entry["current_state"]["baseline_state"] == "FAIL"
        assert entry["current_state"]["candidate_state"] == "FAIL"
        assert entry["semantic_successor_node_ids"] == SUCCESSOR_NODE_IDS
        assert entry["successor_current_status"] == {
            node: "PASS" for node in SUCCESSOR_NODE_IDS
        }
        assert all(_node_exists(node) for node in entry["semantic_successor_node_ids"])
        assert entry["semantic_successor_result"] == "PASS"
        assert entry["OLD_VOICE_SHA_REQUIRED_BY_RELEASE"] == "NO"
        assert entry["OLD_VOICE_BYTE_IDENTITY_REQUIRED_BY_RELEASE"] == "NO"
        assert entry["NEW_EXACT_VOICE_SHA_LOCK_INTRODUCED"] == "NO"
        assert entry["AUDIO_BYTES_CHANGED"] == "NO"
        assert entry["RUNTIME_BEHAVIOR_CHANGED"] == "NO"
        assert entry["OWNER_AUTHORITY_MATCH"] == "YES"


def test_successor_contract_does_not_reintroduce_a_current_byte_lock():
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    successor = registry["semantic_successor"]
    assert "SHA256" not in json.dumps(successor, sort_keys=True)
    assert "sha256" not in json.dumps(successor, sort_keys=True)
    assert all(entry["successor_contract"] == "ZONE3_AUDIO_SEMANTIC_CONTRACT" for entry in registry["entries"])
