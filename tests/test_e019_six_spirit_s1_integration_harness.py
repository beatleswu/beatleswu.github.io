"""E019 executable S1 contracts for the future Six-Spirit Companion.

The file intentionally tests fixtures and static current-runtime boundaries;
it does not implement or claim the future six-Spirit runtime.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from e019_six_spirit_s1_harness import (
    apply_scene_override,
    asset_failure_fallback,
    authority_boundary,
    future_slot_projection,
    load_contract,
    presentation_adapter,
    replay_settlement_delta,
    roster_projection,
    stage_for_level,
    validate_server_state,
)


ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")


def test_contract_fixture_is_valid_and_declares_only_three_existing_ids():
    contract = load_contract()
    assert contract["canonical_existing_spirit_ids"] == [
        "ink_drop_kelpie",
        "whispering_void_kit",
        "star_shell_hatchling",
    ]
    assert len(contract["six_slots"]) == 6
    assert contract["status_vocabulary"] == [
        "PASS_CURRENT_RUNTIME",
        "PASS_FIXTURE_CONTRACT",
        "PENDING_RUNTIME",
        "BLOCKED",
    ]
    assert {
        item["status"] for item in contract["current_runtime_contracts"].values()
    } == {"PASS_CURRENT_RUNTIME"}


def test_existing_three_fixture_is_grounded_in_current_runtime():
    contract = load_contract()
    for spirit_id in contract["canonical_existing_spirit_ids"]:
        assert f"'{spirit_id}'" in APP_SOURCE
    assert "PET_STARTER_KEY = 'ink_drop_kelpie'" in APP_SOURCE
    assert "PET_UNLOCK_ORDER = [" in APP_SOURCE
    assert "PET_UNLOCK_THRESHOLDS = [1, 11, 16]" in APP_SOURCE
    assert "def _pet_stage(level):" in APP_SOURCE


@pytest.mark.parametrize(
    "fixture_name",
    [
        "owned_starter_only",
        "owned_first_second",
        "owned_all_current_three",
        "active_first",
        "active_second",
        "active_third",
        "locked_second",
        "locked_third",
    ],
)
def test_existing_three_state_fixtures_project_without_invalid_active_state(fixture_name):
    state = load_contract()["state_fixtures"][fixture_name]
    validate_server_state(state)
    projection = roster_projection(state)
    assert len(projection) == 6
    assert sum(slot["state"] == "active" for slot in projection) == 1
    assert {slot["spirit_id"] for slot in projection[:3]} == set(
        load_contract()["canonical_existing_spirit_ids"]
    )
    assert all(slot["spirit_id"] is None for slot in projection[3:])


def test_six_slot_contract_uses_roles_only_for_future_slots():
    slots = load_contract()["six_slots"]
    assert [slot["slot"] for slot in slots] == [1, 2, 3, 4, 5, 6]
    assert [slot["role"] for slot in slots[3:]] == [
        "EXPLORATION",
        "PRECISION",
        "SUPPORT",
    ]
    assert all(slot["spirit_id"] is None for slot in slots[3:])
    assert all(slot["canonical_name"] is None for slot in slots[3:])


def test_generic_future_unlock_state_has_no_identity_branch():
    for state in ("LOCKED", "AVAILABLE", "OWNED"):
        projection = future_slot_projection("EXPLORATION", state)
        assert projection["spirit_id"] is None
        assert projection["canonical_name"] is None
        assert projection["unlock_state"] == state
    assert load_contract()["unlock_ui_generic_contract"]["requires_spirit_id_branch"] is False


def test_active_spirit_must_be_owned_and_presentation_cannot_create_ownership():
    state = load_contract()["state_fixtures"]["owned_first_second"]
    before = json.loads(json.dumps(state))
    presentation = presentation_adapter(state)
    assert presentation["spirit_id"] == state["active"]
    assert state == before
    with pytest.raises(ValueError, match="active Spirit"):
        validate_server_state({"owned": ["ink_drop_kelpie"], "active": "star_shell_hatchling"})


def test_legacy_pets_are_quarantined_from_functional_six_spirit_roster():
    contract = load_contract()
    legacy = set(contract["legacy_pet_ids"])
    functional = set(contract["canonical_existing_spirit_ids"])
    assert legacy.isdisjoint(functional)
    assert contract["world_map_follower_interface"]["authority"] == "presentation_only"
    assert all(future_slot_projection("SUPPORT", state)["spirit_id"] is None for state in (
        "LOCKED", "AVAILABLE", "OWNED"
    ))


def test_follower_adapter_is_presentation_only():
    state = load_contract()["state_fixtures"]["active_first"]
    before = json.loads(json.dumps(state))
    follower = presentation_adapter(state)
    assert set(follower) == {
        "spirit_id",
        "evolution_stage",
        "art_manifest",
        "animation_manifest",
        "presentation_state",
    }
    assert state == before
    assert authority_boundary()["follower_can_change_active_spirit"] is False
    assert authority_boundary()["follower_can_unlock_spirit"] is False
    assert authority_boundary()["follower_can_grant_reward"] is False
    assert authority_boundary()["follower_can_change_zone_progress"] is False


def test_battle_interface_keeps_spirit_effect_after_server_judge():
    contract = load_contract()["battle_interface"]
    assert contract["sequence"].index("server_go_judge") < contract["sequence"].index(
        "spirit_effect_adapter"
    )
    assert authority_boundary()["spirit_effect_before_judge"] is False
    assert authority_boundary()["second_combat_engine"] is False
    assert authority_boundary()["client_spirit_damage_authority"] is False


def test_scene_override_changes_presentation_only():
    state = load_contract()["state_fixtures"]["active_second"]
    before = json.loads(json.dumps(state))
    overridden = apply_scene_override(state, "ink_drop_kelpie")
    assert overridden["scene_override"] == "ink_drop_kelpie"
    assert overridden["active"] == before["active"]
    assert overridden["owned"] == before["owned"]
    assert overridden["levels"] == before["levels"]
    assert load_contract()["scene_override"]["required_invariants"] == [
        "active_ownership_unchanged",
        "active_selection_unchanged",
        "spirit_xp_delta_zero",
        "unlock_delta_zero",
        "functional_item_delta_zero",
    ]


@pytest.mark.parametrize("case", ["story_replay", "boss_replay", "cinematic_replay"])
def test_replay_has_no_spirit_settlement(case):
    assert case in load_contract()["replay"]["cases"]
    assert replay_settlement_delta() == {
        "spirit_xp": 0,
        "spirit_items": 0,
        "spirit_unlock_progress": 0,
        "evolution_reward": 0,
    }


def test_hero_world_backpack_consume_one_server_active_source():
    contract = load_contract()["single_active_source"]
    assert contract["source"] == "SERVER_ACTIVE_SPIRIT"
    assert contract["consumers"] == ["Hero", "World", "Backpack"]
    assert contract["multiple_client_active_authorities"] is False
    state = load_contract()["state_fixtures"]["active_third"]
    projections = {consumer: presentation_adapter(state)["spirit_id"] for consumer in contract["consumers"]}
    assert set(projections.values()) == {state["active"]}


def test_current_hero_world_and_backpack_surfaces_read_the_existing_pet_authority():
    for relative_path in ("hero.html", "index.html", "inventory.html"):
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        assert "/api/pet/status" in source, relative_path


@pytest.mark.parametrize(
    ("level", "expected_stage"),
    [(9, "I"), (10, "II"), (24, "II"), (25, "III")],
)
def test_evolution_stage_boundaries_are_server_derived(level, expected_stage):
    assert stage_for_level(level) == expected_stage
    assert authority_boundary()["client_can_select_evolution_stage"] is False


def test_responsive_acceptance_matrix_is_defined_without_claiming_runtime_pass():
    contract = load_contract()
    matrix = contract["responsive_acceptance_matrix"]
    assert {entry["device"] for entry in matrix} == {
        "desktop",
        "ipad_landscape",
        "ipad_portrait",
        "mobile_portrait",
        "narrow_portrait",
    }
    for entry in matrix:
        assert entry["viewport"]["width"] > 0
        assert entry["viewport"]["height"] > 0
        assert entry["grid"]["columns"] * entry["grid"]["rows"] == 6
    assert contract["hero_companion_ui"]["runtime_status"] == "PENDING_RUNTIME"


@pytest.mark.parametrize("failure", load_contract()["asset_failure_contract"]["failure_inputs"])
def test_asset_failure_fallback_cannot_change_authority(failure):
    state = load_contract()["state_fixtures"]["active_first"]
    fallback = asset_failure_fallback(state, failure)
    assert fallback["active"] == state["active"]
    assert fallback["owned"] == state["owned"]
    assert fallback["presentation_fallback"] == "safe_placeholder"


def test_future_runtime_contracts_are_explicitly_pending_not_false_passes():
    contract = load_contract()
    pending = {
        contract["hero_companion_ui"]["runtime_status"],
        contract["world_map_follower_interface"]["runtime_status"],
        contract["unlock_ui_generic_contract"]["runtime_status"],
        contract["asset_failure_contract"]["runtime_status"],
        contract["owner_visual_evidence"]["runtime_status"],
    }
    assert pending == {"PENDING_RUNTIME"}
