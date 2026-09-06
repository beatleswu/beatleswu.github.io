"""Machine-readable guard for the frozen W1-C1 Zone 3 reference contract."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "docs/contracts/w1_c1_zone3_reference_vertical_slice_template_001.json"


def _load_contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def test_zone3_reference_contract_is_frozen_against_canonical_base() -> None:
    contract = _load_contract()
    assert contract["task"] == "W1-C1-ZONE3-CLOSURE-REFERENCE-TEMPLATE-FREEZE-001"
    assert contract["wave_package"] == "W1-C1"
    assert contract["status"] == "PASS_Z3_CONTENT_CANDIDATE_READY"
    assert contract["reference_template_frozen"] is True
    assert contract["canonical_base"] == {
        "ref": "origin/master",
        "sha": "3dc517bfbf789da378f971b092980fb53e7a5e2f",
        "tree": "f794a931c7243a5cea6655b2ab71313bd563c19a",
        "planning_authority_local_head": "9dda8945e74cbda2902fa30ddd973ba125fbd203",
    }


def test_zone3_reference_contract_has_all_reusable_vertical_slice_sections() -> None:
    contract = _load_contract()
    assert contract["zone"] == {
        "number": 3,
        "key": "k16_20",
        "name_zh": "哥布林洞穴",
        "name_en": "Goblin Cave",
        "stage": "LV3",
        "level_band": "16-20",
        "theme": contract["zone"]["theme"],
        "learning_books": ["5哥布林洞穴", "6哥布林巡邏隊"],
        "lord": {
            "id": "goblin_centurion",
            "name_zh": "哥布林百夫長",
            "name_en": "Goblin Centurion",
            "classification": "LORD_ONLY",
        },
    }
    assert set(contract["components"]) == {
        "environment",
        "monster_roster",
        "encounter_profiles",
        "story_npc",
        "cinematic",
        "audio",
        "learning_binding",
        "drops_rewards",
        "lord_presentation",
        "progression",
        "replay",
        "responsive_device_acceptance",
    }


def test_zone3_reference_contract_preserves_roster_and_identity_boundaries() -> None:
    contract = _load_contract()
    roster = contract["components"]["monster_roster"]
    assert roster["count"] == 13
    assert roster["monster_ids"] == [
        "M022",
        "M023",
        "M024",
        "M025",
        "M026",
        "M027",
        "M028",
        "M029",
        "M030",
        "M031",
        "M032",
        "M033",
        "M060",
    ]
    assert roster["art_created_in_this_task"] == 0
    assert roster["cross_zone_roster_leakage_guard"] is True

    lord = contract["components"]["lord_presentation"]
    assert lord["lord_id"] == "goblin_centurion"
    assert lord["lord_classification"] == "LORD_ONLY"
    assert lord["owner_approved_runtime_slot_count"] == 6
    assert lord["battlefield_boss"]["runtime_id"] == "legacy_bf_03_boss"
    assert lord["battlefield_boss"]["distinct_from_lord"] is True


def test_zone3_reference_contract_evidence_paths_exist_and_runtime_rebind_is_canonical() -> None:
    contract = _load_contract()
    evidence = {
        path
        for component in contract["components"].values()
        for path in component.get("evidence", [])
        if isinstance(component, dict)
    }
    for relative in sorted(evidence):
        path = ROOT / relative
        assert path.exists(), relative

    world_stage = (ROOT / "js/e9/world_stage.js").read_text(encoding="utf-8")
    assert "k16_20: '/assets/e10/art/zone3/environment/zone3_map_landmark.webp'" in world_stage
    assert "k16_20: '/assets/maps/e10-vs1f-landmarks/zone-03-goblin-cave.webp'" not in world_stage

    rail = (ROOT / "components/adventure/zone3_vertical_slice.html").read_text(encoding="utf-8")
    assert "Final Zone 3 cinematic artwork is intentionally not present" not in rail

    view = (ROOT / "js/e9/journey_zone3_vertical_slice_view.js").read_text(encoding="utf-8")
    assert "e9.zone3.presentation_ready" in view


def test_zone3_reference_contract_keeps_gates_explicit() -> None:
    contract = _load_contract()
    assert contract["scope_locks"]["app_py_mutation"] is False
    assert contract["scope_locks"]["monster_art_created"] == 0
    assert contract["scope_locks"]["zone4_implementation"] is False
    assert contract["scope_locks"]["w1_a2_semantics_implementation"] is False
    assert contract["provenance"]["production_mutation"] is False
    assert contract["provenance"]["merge"] is False
    assert contract["provenance"]["deploy"] is False
