"""Bounded checks for the W1-02 Zone 3 encounter handoff contract."""

from __future__ import annotations

import json
from pathlib import Path

from adventure_zone3_monster_authority import (
    ZONE3_LORD_ID,
    ZONE3_NORMAL_IDS,
    get_zone3_binding,
)
from zone3_runtime_asset_bindings import (
    ZONE3_BATTLEFIELD_BOSS_ASSET,
    ZONE3_BATTLEFIELD_BOSS_RUNTIME_ID,
    ZONE3_LORD_PRESENTATION_SLOTS,
)


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = (
    ROOT
    / "docs"
    / "planning"
    / "w1_02_hero_zone3_encounter_runtime_contract_and_handoff_006.json"
)
EXPECTED_NORMAL_IDS = (
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
)
EXPECTED_STATE_IDS = {
    "NORMAL",
    "BF_BOSS",
    "LORD_RITUAL",
    "LORD_CHALLENGE",
    "LORD_FAILURE",
    "LORD_FIRST_STAR_SUCCESS",
    "LORD_PORTRAIT",
    "LORD_SUCCESS_PORTRAIT",
}


def _manifest() -> dict[str, object]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _states(manifest: dict[str, object]) -> list[dict[str, object]]:
    return manifest["STATE_BINDINGS"]  # type: ignore[return-value]


def _repo_path(asset_path: str) -> Path:
    return ROOT / asset_path.lstrip("/")


def test_manifest_preserves_exact_normal_roster_and_zero_elites():
    manifest = _manifest()
    normals = manifest["NORMAL_MONSTERS"]
    elites = manifest["ELITES"]

    assert normals["COUNT"] == 13  # type: ignore[index]
    assert tuple(normals["ENTITY_IDS"]) == EXPECTED_NORMAL_IDS  # type: ignore[index]
    assert tuple(ZONE3_NORMAL_IDS) == EXPECTED_NORMAL_IDS
    assert normals["ENCOUNTER_CLASS"] == "NORMAL"  # type: ignore[index]
    assert normals["REUSE_AS_IS"] is True  # type: ignore[index]
    assert normals["REDRAW_REQUIRED"] is False  # type: ignore[index]
    assert elites["COUNT"] == 0  # type: ignore[index]
    assert elites["ENTITY_IDS"] == []  # type: ignore[index]
    assert elites["CREATE_MISSING"] is False  # type: ignore[index]

    normal_states = [row for row in _states(manifest) if row["STATE_ID"] == "NORMAL"]
    assert len(normal_states) == 13
    assert tuple(row["ENTITY_ID"] for row in normal_states) == EXPECTED_NORMAL_IDS
    for row in normal_states:
        binding = get_zone3_binding(row["ENTITY_ID"])
        assert binding is not None
        assert row["ENTITY_ROLE"] == "NORMAL_MONSTER"
        assert row["ASSET_PATH"] == binding.presentation_asset
        assert row["MUST_NOT_BE_USED_AS"] == ["ELITE", "BF_BOSS", "LORD"]
        assert _repo_path(row["ASSET_PATH"]).is_file()


def test_battlefield_boss_remains_distinct_from_lord_and_normal_monsters():
    manifest = _manifest()
    boss = manifest["BATTLEFIELD_BOSS"]
    assert boss["ENTITY_ID"] == ZONE3_BATTLEFIELD_BOSS_RUNTIME_ID  # type: ignore[index]
    assert boss["ASSET_PATH"] == ZONE3_BATTLEFIELD_BOSS_ASSET  # type: ignore[index]
    assert boss["ENCOUNTER_CLASS"] == "BATTLEFIELD_BOSS"  # type: ignore[index]
    assert boss["DISTINCT_FROM_LORD"] is True  # type: ignore[index]
    assert manifest["LORD"]["ENTITY_ID"] == ZONE3_LORD_ID  # type: ignore[index]
    assert boss["ENTITY_ID"] != manifest["LORD"]["ENTITY_ID"]  # type: ignore[index]
    assert _repo_path(boss["ASSET_PATH"]).is_file()  # type: ignore[index]

    normal_paths = {
        row["ASSET_PATH"] for row in _states(manifest) if row["STATE_ID"] == "NORMAL"
    }
    assert boss["ASSET_PATH"] not in normal_paths  # type: ignore[operator]


def test_six_lord_states_are_explicit_present_slots_without_aliases():
    manifest = _manifest()
    lord = manifest["LORD"]
    lord_states = [row for row in _states(manifest) if row["ENTITY_ROLE"].startswith("LORD_")]
    expected_slots = {slot.slot_id: slot for slot in ZONE3_LORD_PRESENTATION_SLOTS}

    assert lord["ENTITY_ID"] == ZONE3_LORD_ID  # type: ignore[index]
    assert lord["LORD_ONLY"] is True  # type: ignore[index]
    assert lord["ASSET_COUNT"] == 6  # type: ignore[index]
    assert len(lord_states) == 6
    assert {row["PRESENTATION_SLOT_ID"] for row in lord_states} == set(expected_slots)

    normal_paths = {
        row["ASSET_PATH"] for row in _states(manifest) if row["STATE_ID"] == "NORMAL"
    }
    for row in lord_states:
        slot = expected_slots[row["PRESENTATION_SLOT_ID"]]
        assert row["ENTITY_ID"] == ZONE3_LORD_ID
        assert row["ASSET_PATH"] == slot.expected_runtime_path
        assert row["MUST_NOT_BE_USED_AS"] == [
            "NORMAL_MONSTER",
            "ELITE",
            "BF_BOSS",
            "COMBAT_AUTHORITY",
        ]
        assert row["ASSET_PATH"] not in normal_paths
        assert row["ASSET_PATH"] != ZONE3_BATTLEFIELD_BOSS_ASSET
        assert _repo_path(row["ASSET_PATH"]).is_file()


def test_state_contract_has_no_collision_and_preserves_authority_invariants():
    manifest = _manifest()
    states = _states(manifest)
    semantic_keys = {
        (row["STATE_ID"], row["ENTITY_ID"], row["ENTITY_ROLE"]) for row in states
    }

    assert len(semantic_keys) == len(states)
    assert {row["STATE_ID"] for row in states} == EXPECTED_STATE_IDS
    assert manifest["INVARIANTS"] == {
        "BF_BOSS_EQ_LORD": False,
        "ACQUIRE_EQ_EQUIP": False,
        "LORD_CLEAR_EQ_BF_BOSS_CLEAR": False,
        "NORMAL_MONSTER_PROMOTED_TO_ELITE": False,
        "ELITE_COUNT": 0,
        "SOURCE_ART_MUTATED": False,
        "GAMEPLAY_AUTHORITY_CHANGED": False,
        "JOURNEY_RUNTIME_CHANGED": False,
        "COMBAT_AUTHORITY_FROM_ASSET_LOAD": False,
        "NO_FALLBACK_TO_ORDINARY_MONSTER": True,
    }
