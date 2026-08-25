from __future__ import annotations

import copy
import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from player_presentation_api_contract import (
    B030_READ_SERVICE_CONTRACT,
    PLAYER_PRESENTATION_API_V1,
    PlayerPresentationApiContractError,
    PlayerPresentationApiV1,
    build_player_presentation_api_v1,
    serialize_player_presentation_api_v1,
)


def _b028_state() -> dict:
    slots = {
        slot: {
            "slot": slot,
            "item_id": None,
            "owned": False,
            "equipped": False,
            "quantity": 0,
            "functional_status": "NONE",
            "display": None,
        }
        for slot in ("weapon", "armor", "accessory")
    }
    return {
        "read_model": "player_hero_state",
        "read_model_version": "player_hero_state_v1",
        "projection_status": "OK",
        "read_only": True,
        "mutates": False,
        "player_id": 17,
        "hero": {
            "hero_id": "apprentice",
            "identity_status": "PRESENTATION_SELECTION",
            "authority": "player_appearance.character_key",
            "authority_scope": "presentation_only",
            "presentation_fallback_id": "apprentice",
        },
        "progression": {
            "projection_status": "OK",
            "authority": "user_stats",
            "source_version": "existing_user_stats_xp_rank_projection",
            "xp": 120,
            "rank_level": "LV3",
            "level": 3,
            "rank_xp": 20,
            "go_rank": "30k",
            "total_correct": 12,
            "current_streak": 2,
            "max_streak": 4,
        },
        "hp": {
            "projection_status": "OK",
            "authority": "user_stats",
            "scope": "persistent_player_state_for_legacy_battlefield",
            "persistent_player_hp": 80,
            "persistent_player_max_hp": 100,
            "encounter_hp": {
                "projected": False,
                "authority": "encounter_local_battle_state",
                "reason": "battle context required",
            },
        },
        "equipment": {
            "projection_status": "OK",
            "authority": "player_inventory",
            "slots": slots,
            "owned_items": [],
            "invalid_item_ids": [],
            "equipped_slot_conflicts": [],
            "combat_stats_projected": False,
        },
        "spirit": {
            "projection_status": "OK",
            "authority": "pet_collection_and_user_pets",
            "active": {
                "spirit_id": "ink_drop_kelpie",
                "enabled": True,
                "ownership_validated": True,
                "evolution_stage": "STAGE_I",
                "progression_level": 1,
                "authority": "server_b022_d008_active_spirit_projection",
            },
            "single_active_spirit": True,
            "combat_effects_projected": False,
        },
        "cosmetics": {
            "projection_status": "OK",
            "authority": "player_wardrobe_and_player_appearance",
            "selected": {slot: None for slot in ("outfit", "hat", "back", "title", "accessory", "pet", "aura")},
            "owned_items": [],
            "invalid_item_ids": [],
            "invalid_selected_ids": [],
            "gameplay_effects_projected": False,
        },
        "world": {
            "projected": False,
            "authority": "world_progression_system",
            "selected_zone_is_not_player_progression": True,
            "reason": "World is outside the Player/Hero read model",
        },
        "provenance": {
            "player": {"authority": "users.id", "source_version": "existing_users_identity"},
            "hero": {"authority": "player_appearance.character_key", "scope": "presentation_only"},
            "progression": {"authority": "user_stats", "projection_status": "OK"},
            "hp": {"authority": "user_stats.player_hp/player_max_hp", "scope": "persistent player state"},
            "equipment": {"authority": "player_inventory", "projection_status": "OK"},
            "spirit": {"authority": "pet_collection_and_user_pets", "projection_status": "OK"},
            "cosmetics": {"authority": "player_wardrobe_and_player_appearance", "projection_status": "OK"},
            "world": {"authority": "world_progression_system", "projected": False},
        },
    }


def _service_result() -> dict:
    return {
        "contract_version": B030_READ_SERVICE_CONTRACT,
        "status": "OK",
        "player_state": _b028_state(),
        "warnings": [],
        "read_only": True,
        "mutates": False,
    }


def _build() -> PlayerPresentationApiV1:
    return build_player_presentation_api_v1(_service_result())


def test_valid_b028_b030_projection_is_accepted() -> None:
    envelope = _build()
    assert envelope.contract_version == PLAYER_PRESENTATION_API_V1
    assert envelope.player_id == 17
    assert envelope.projection_status == "OK"
    assert envelope.persistent_hp["persistent_player_hp"] == 80


def test_progression_narrows_learning_and_streak_facts_from_b028_input() -> None:
    source_progression = _service_result()["player_state"]["progression"]
    assert {"total_correct", "current_streak", "max_streak"}.issubset(source_progression)

    transport_progression = _build().to_dict()["progression"]
    assert transport_progression["xp"] == 120
    assert transport_progression["level"] == 3
    assert transport_progression["rank_level"] == "LV3"
    assert transport_progression["rank_xp"] == 20
    assert transport_progression["go_rank"] == "30k"
    assert "total_correct" not in transport_progression
    assert "current_streak" not in transport_progression
    assert "max_streak" not in transport_progression


@pytest.mark.parametrize("field", ["learning_stats", "engagement_streak", "correct_count"])
def test_progression_equivalent_learning_aliases_fail_closed(field: str) -> None:
    service = _service_result()
    service["player_state"]["progression"][field] = 1
    with pytest.raises(PlayerPresentationApiContractError):
        build_player_presentation_api_v1(service)


def test_transport_envelope_is_immutable() -> None:
    envelope = _build()
    with pytest.raises(TypeError):
        envelope.hero["hero_id"] = "mage"  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        envelope.player_id = 99  # type: ignore[misc]


def test_to_dict_is_detached_and_has_only_contract_fields() -> None:
    payload = _build().to_dict()
    assert set(payload) == {
        "contract_version",
        "player_id",
        "projection_status",
        "hero",
        "progression",
        "persistent_hp",
        "equipment",
        "spirit",
        "cosmetics",
        "provenance",
    }
    assert "world" not in payload
    assert "encounter" not in payload
    assert "quest" not in payload
    assert "shop" not in payload
    assert "premium" not in payload
    assert "battle" not in payload
    assert "reward" not in payload


def test_deterministic_json_serialization() -> None:
    first = serialize_player_presentation_api_v1(_build())
    second = serialize_player_presentation_api_v1(_build())
    assert first == second
    assert first == json.dumps(json.loads(first), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@pytest.mark.parametrize("field", ["world", "quest", "shop", "premium", "battle", "reward", "unknown"])
def test_forbidden_or_unknown_service_top_level_field_rejected(field: str) -> None:
    service = _service_result()
    service[field] = {}
    with pytest.raises(PlayerPresentationApiContractError):
        build_player_presentation_api_v1(service)


def test_encounter_hp_value_rejected() -> None:
    service = _service_result()
    service["player_state"]["hp"]["encounter_hp"] = {
        "projected": True,
        "authority": "encounter_local_battle_state",
        "reason": "bad fixture",
        "current": 10,
    }
    with pytest.raises(PlayerPresentationApiContractError):
        build_player_presentation_api_v1(service)


def test_hero_functional_or_combat_field_rejected() -> None:
    service = _service_result()
    service["player_state"]["hero"]["combat_power"] = 99
    with pytest.raises(PlayerPresentationApiContractError):
        build_player_presentation_api_v1(service)


def test_equipment_combat_stats_rejected() -> None:
    service = _service_result()
    service["player_state"]["equipment"]["combat_stats"] = {"attack": 99}
    with pytest.raises(PlayerPresentationApiContractError):
        build_player_presentation_api_v1(service)


def test_equipment_combat_stats_flag_must_be_false() -> None:
    service = _service_result()
    service["player_state"]["equipment"]["combat_stats_projected"] = True
    with pytest.raises(PlayerPresentationApiContractError):
        build_player_presentation_api_v1(service)


def test_spirit_combat_effects_rejected() -> None:
    service = _service_result()
    service["player_state"]["spirit"]["combat_effects"] = {"damage": 1}
    with pytest.raises(PlayerPresentationApiContractError):
        build_player_presentation_api_v1(service)


def test_spirit_effect_projection_flag_must_be_false() -> None:
    service = _service_result()
    service["player_state"]["spirit"]["combat_effects_projected"] = True
    with pytest.raises(PlayerPresentationApiContractError):
        build_player_presentation_api_v1(service)


def test_world_boundary_is_metadata_only() -> None:
    envelope = _build().to_dict()
    excluded = envelope["provenance"]["excluded_authorities"]
    assert excluded["world"] == {
        "projected": False,
        "authority": "world_progression_system",
    }
    assert "world" not in envelope


def test_optional_server_derived_display_identity_is_allowed() -> None:
    service = _service_result()
    service["display_identity"] = {"display_name": "A024 QA", "username": "qa"}
    payload = build_player_presentation_api_v1(service).to_dict()
    assert payload["display_identity"] == {"display_name": "A024 QA", "username": "qa"}


def test_b030_status_must_match_b028_projection_status() -> None:
    service = _service_result()
    service["status"] = "PARTIAL"
    with pytest.raises(PlayerPresentationApiContractError):
        build_player_presentation_api_v1(service)


def test_partial_b028_projection_remains_partial_without_effect_authority() -> None:
    service = _service_result()
    service["status"] = "PARTIAL"
    service["player_state"]["projection_status"] = "OPTIONAL_PROJECTION_UNAVAILABLE"
    service["player_state"]["spirit"].pop("combat_effects_projected")
    service["player_state"]["cosmetics"].pop("gameplay_effects_projected")
    payload = build_player_presentation_api_v1(service).to_dict()
    assert payload["projection_status"] == "PARTIAL"
    assert payload["spirit"]["combat_effects_projected"] is False
    assert payload["cosmetics"]["gameplay_effects_projected"] is False


def test_surface_matrix_is_complete_and_matches_a024() -> None:
    matrix_path = Path(__file__).parents[1] / "docs/planning/architecture/a025_player_presentation_surface_adapter_matrix.json"
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    expected = {
        "hero_overview",
        "hero_appearance_wardrobe",
        "hero_equipment_loadout",
        "hero_spirit_panel",
        "hero_achievement_badges",
        "adventure_world_identity",
        "adventure_encounter_result",
        "backpack_inventory",
        "item_journal",
        "shop_cosmetic_and_item_preview",
        "public_profile",
        "stats_dashboard",
        "premium_account_display",
        "quest_reward_result",
    }
    assert matrix["total_surfaces"] == 14
    assert matrix["progression_transport_fields"] == [
        "xp",
        "rank_level",
        "level",
        "rank_xp",
        "go_rank",
    ]
    assert matrix["progression_excluded_fields"] == [
        "total_correct",
        "current_streak",
        "max_streak",
    ]
    assert {row["surface_id"] for row in matrix["surfaces"]} == expected
    assert len(matrix["surfaces"]) == 14
    assert all(row["adapter_required"] in (True, False) for row in matrix["surfaces"])


def test_contract_module_has_no_route_sql_or_mutation_wiring() -> None:
    source = Path(__file__).parents[1].joinpath("player_presentation_api_contract.py").read_text(encoding="utf-8")
    assert "@app.route" not in source
    assert "conn.execute" not in source
    assert "INSERT" not in source
    assert "UPDATE" not in source
    assert "DELETE" not in source
    assert ".commit(" not in source


def test_serializer_rejects_non_contract_object() -> None:
    with pytest.raises(PlayerPresentationApiContractError):
        serialize_player_presentation_api_v1(copy.deepcopy({}))  # type: ignore[arg-type]
