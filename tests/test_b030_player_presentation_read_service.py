"""Focused contract tests for the B030 Player presentation read service."""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal

import pytest

import player_presentation_read_service as service
from player_state_read_model import PlayerStateReadModelError


class NoSqlConnection:
    """Connection spy proving B030 itself never executes SQL."""

    def __init__(self):
        self.execute_calls = []

    def execute(self, *args, **kwargs):
        self.execute_calls.append((args, kwargs))
        raise AssertionError("B030 must not issue SQL")


def _complete_state(*, projection_status="OK"):
    return {
        "read_model": "player_hero_state",
        "read_model_version": "player_hero_state_v1",
        "projection_status": projection_status,
        "read_only": True,
        "mutates": False,
        "player_id": 7,
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
            "xp": 123,
            "rank_level": "LV12",
            "level": 12,
            "rank_xp": 40,
        },
        "hp": {
            "projection_status": "OK",
            "authority": "user_stats",
            "scope": "persistent_player_state_for_legacy_battlefield",
            "persistent_player_hp": 80,
            "persistent_player_max_hp": 120,
            "encounter_hp": {
                "projected": False,
                "authority": "encounter_local_battle_state",
            },
        },
        "equipment": {
            "projection_status": "OK",
            "authority": "player_inventory",
            "slots": {
                "weapon": {"item_id": "iron_sword", "equipped": True},
                "armor": {"item_id": None, "equipped": False},
                "accessory": {"item_id": None, "equipped": False},
            },
            "owned_items": [
                {
                    "item_id": "iron_sword",
                    "quantity": 1,
                    "equipped": True,
                    "combat_power_projected": False,
                }
            ],
            "equipped_slot_conflicts": [],
            "combat_stats_projected": False,
        },
        "spirit": {
            "projection_status": "OK",
            "authority": "pet_collection_and_user_pets",
            "active": {
                "spirit_id": "fatty",
                "enabled": True,
                "ownership_validated": True,
                "evolution_stage": "STAGE_II",
            },
            "single_active_spirit": True,
            "combat_effects_projected": False,
        },
        "cosmetics": {
            "projection_status": "OK",
            "authority": "player_wardrobe_and_player_appearance",
            "selected": {
                "outfit": {
                    "item_id": "robe_plain",
                    "presentation_only": True,
                    "combat_power_projected": False,
                }
            },
            "owned_items": [],
            "gameplay_effects_projected": False,
        },
        "world": {
            "projected": False,
            "authority": "world_progression_system",
            "selected_zone_is_not_player_progression": True,
        },
        "provenance": {
            "hero": {
                "authority": "player_appearance.character_key",
                "scope": "presentation_only",
            },
            "progression": {"authority": "user_stats"},
            "hp": {"authority": "user_stats.player_hp/player_max_hp"},
            "equipment": {"authority": "player_inventory"},
            "spirit": {"authority": "pet_collection_and_user_pets"},
            "cosmetics": {"authority": "player_wardrobe_and_player_appearance"},
            "world": {"authority": "world_progression_system", "projected": False},
        },
    }


def _stub_builder(state, calls):
    def builder(_conn, user_id):
        calls.append(user_id)
        return state

    return builder


def test_valid_complete_state_uses_b028_once_and_preserves_shape(monkeypatch):
    state = _complete_state()
    calls = []
    monkeypatch.setattr(
        service._b028,
        "build_player_state_read_model",
        _stub_builder(state, calls),
    )

    result = service.build_player_presentation_state(NoSqlConnection(), user_id=7)

    assert calls == [7]
    assert result["contract_version"] == "PLAYER_PRESENTATION_READ_CONTRACT_V1"
    assert result["status"] == "OK"
    assert result["player_state"]["read_model"] == "player_hero_state"
    assert result["player_state"]["provenance"] == state["provenance"]
    assert result["read_only"] is True
    assert result["mutates"] is False
    assert result["player_state"] is not state

    state["progression"]["xp"] = 999
    assert result["player_state"]["progression"]["xp"] == 123


def test_hero_remains_presentation_only_and_missing_selection_is_preserved(monkeypatch):
    state = _complete_state()
    state["hero"] = {
        "hero_id": None,
        "identity_status": "MISSING_HERO_SELECTION",
        "authority": "player_appearance.character_key",
        "authority_scope": "presentation_only",
        "presentation_fallback_id": "apprentice",
    }
    monkeypatch.setattr(service._b028, "build_player_state_read_model", lambda _c, _u: state)

    result = service.build_player_presentation_state(NoSqlConnection(), user_id=7)
    hero = result["player_state"]["hero"]

    assert result["status"] == "OK"
    assert hero["hero_id"] is None
    assert hero["identity_status"] == "MISSING_HERO_SELECTION"
    assert hero["authority"] == "player_appearance.character_key"
    assert hero["authority_scope"] == "presentation_only"
    assert "functional_hero_id" not in hero
    assert "hero_combat_stats" not in hero


def test_invalid_hero_projection_surfaces_invalid_state(monkeypatch):
    state = _complete_state(projection_status="INVALID_STORED_STATE")
    state["hero"] = {
        "hero_id": None,
        "identity_status": "INVALID_STORED_STATE",
        "invalid_stored_value": "not-active",
        "authority": "player_appearance.character_key",
        "authority_scope": "presentation_only",
    }
    monkeypatch.setattr(service._b028, "build_player_state_read_model", lambda _c, _u: state)

    result = service.build_player_presentation_state(NoSqlConnection(), user_id=7)

    assert result["status"] == "INVALID_STATE"
    assert result["player_state"]["hero"]["invalid_stored_value"] == "not-active"


def test_partial_state_and_xp_hp_authority_are_preserved(monkeypatch):
    state = _complete_state(projection_status="PARTIAL")
    state["progression"]["projection_status"] = "OPTIONAL_PROJECTION_UNAVAILABLE"
    state["progression"]["xp"] = None
    state["progression"]["level"] = None
    monkeypatch.setattr(service._b028, "build_player_state_read_model", lambda _c, _u: state)

    result = service.build_player_presentation_state(NoSqlConnection(), user_id=7)
    player_state = result["player_state"]

    assert result["status"] == "PARTIAL"
    assert player_state["progression"]["xp"] is None
    assert player_state["hp"]["persistent_player_hp"] == 80
    assert player_state["hp"]["persistent_player_max_hp"] == 120
    assert player_state["hp"]["encounter_hp"]["projected"] is False
    assert "encounter_player_hp" not in player_state


@pytest.mark.parametrize(
    "equipment",
    [
        {
            "projection_status": "OK",
            "slots": {"weapon": {"item_id": "iron_sword", "equipped": True}},
            "owned_items": [{"item_id": "iron_sword", "equipped": True}],
            "equipped_slot_conflicts": [],
        },
        {
            "projection_status": "INVALID_STORED_STATE",
            "slots": {"weapon": {"item_id": None, "equipped": False}},
            "owned_items": [
                {"item_id": "iron_sword", "equipped": False},
                {"item_id": "wooden_sword", "equipped": False},
            ],
            "equipped_slot_conflicts": ["weapon"],
        },
        {
            "projection_status": "INVALID_STORED_STATE",
            "slots": {"weapon": {"item_id": None, "equipped": False}},
            "owned_items": [{"item_id": "iron_sword", "quantity": 2, "equipped": False}],
            "equipped_slot_conflicts": ["weapon"],
        },
    ],
)
def test_equipment_projection_is_consumed_without_repairing_conflicts(monkeypatch, equipment):
    state = _complete_state()
    state["equipment"] = equipment
    if equipment["projection_status"] != "OK":
        state["projection_status"] = "INVALID_STORED_STATE"
    monkeypatch.setattr(service._b028, "build_player_state_read_model", lambda _c, _u: state)

    result = service.build_player_presentation_state(NoSqlConnection(), user_id=7)
    projected = result["player_state"]["equipment"]

    assert projected["slots"]["weapon"]["item_id"] is None or projected["slots"]["weapon"]["item_id"] == "iron_sword"
    if projected["equipped_slot_conflicts"]:
        assert projected["slots"]["weapon"]["item_id"] is None
        assert all(item["equipped"] is False for item in projected["owned_items"])


def test_spirit_and_cosmetic_projections_remain_read_only(monkeypatch):
    state = _complete_state()
    state["spirit"]["active"] = None
    state["cosmetics"]["selected"]["outfit"]["combat_power_projected"] = False
    monkeypatch.setattr(service._b028, "build_player_state_read_model", lambda _c, _u: state)

    result = service.build_player_presentation_state(NoSqlConnection(), user_id=7)
    player_state = result["player_state"]

    assert player_state["spirit"]["active"] is None
    assert player_state["spirit"]["combat_effects_projected"] is False
    assert player_state["cosmetics"]["selected"]["outfit"]["presentation_only"] is True
    assert player_state["cosmetics"]["selected"]["outfit"]["combat_power_projected"] is False
    assert player_state["world"]["projected"] is False
    assert "progression_zone" not in player_state["world"]


def test_json_safe_detached_and_deterministic_serialization(monkeypatch):
    state = _complete_state()
    state["warnings"] = (Decimal("1.25"),)
    state["provenance"]["generated_at"] = datetime(2026, 8, 25, 12, 30, 0)
    monkeypatch.setattr(service._b028, "build_player_state_read_model", lambda _c, _u: state)

    first = service.build_player_presentation_state(NoSqlConnection(), user_id=7)
    second = service.build_player_presentation_state(NoSqlConnection(), user_id=7)

    assert first["warnings"] == ["1.25"]
    encoded_first = service.serialize_player_presentation_state(first)
    encoded_second = service.serialize_player_presentation_state(second)
    assert encoded_first == encoded_second
    decoded = json.loads(encoded_first)
    assert decoded["contract_version"] == "PLAYER_PRESENTATION_READ_CONTRACT_V1"
    assert decoded["player_state"]["provenance"]["generated_at"] == "2026-08-25T12:30:00"


def test_invalid_user_id_is_rejected_before_b028(monkeypatch):
    called = []

    def unexpected(*_args, **_kwargs):
        called.append(True)
        raise AssertionError("B028 must not receive invalid user IDs")

    monkeypatch.setattr(service._b028, "build_player_state_read_model", unexpected)

    with pytest.raises(service.PlayerPresentationReadServiceError) as error:
        service.build_player_presentation_state(NoSqlConnection(), user_id=True)

    assert error.value.code == "INVALID_USER_ID"
    assert error.value.status == "INVALID_STATE"
    assert called == []


@pytest.mark.parametrize(
    ("b028_code", "service_code", "service_status"),
    [
        ("PLAYER_NOT_FOUND", "PLAYER_STATE_UNAVAILABLE", "UNAVAILABLE"),
        ("AUTHORITY_UNAVAILABLE", "PLAYER_STATE_UNAVAILABLE", "UNAVAILABLE"),
        ("AUTHORITY_AMBIGUOUS", "PLAYER_STATE_INVALID", "INVALID_STATE"),
    ],
)
def test_b028_errors_map_to_stable_service_errors(
    monkeypatch, b028_code, service_code, service_status
):
    def failing(_conn, _user_id):
        raise PlayerStateReadModelError(b028_code, "private driver detail")

    monkeypatch.setattr(service._b028, "build_player_state_read_model", failing)

    with pytest.raises(service.PlayerPresentationReadServiceError) as error:
        service.build_player_presentation_state(NoSqlConnection(), user_id=7)

    assert error.value.code == service_code
    assert error.value.status == service_status
    assert "private driver detail" not in str(error.value)
    assert error.value.as_dict() == {"code": service_code, "status": service_status}


def test_unexpected_b028_failure_is_safe_and_does_not_expose_driver_detail(monkeypatch):
    def failing(_conn, _user_id):
        raise RuntimeError("postgres password and filesystem path")

    monkeypatch.setattr(service._b028, "build_player_state_read_model", failing)

    with pytest.raises(service.PlayerPresentationReadServiceError) as error:
        service.build_player_presentation_state(NoSqlConnection(), user_id=7)

    assert error.value.code == "PLAYER_STATE_UNAVAILABLE"
    assert error.value.status == "UNAVAILABLE"
    assert "postgres" not in str(error.value).lower()
    assert "filesystem" not in str(error.value).lower()


def test_b030_has_no_sql_writer_and_delegates_to_b028(monkeypatch):
    state = _complete_state()
    calls = []
    monkeypatch.setattr(
        service._b028,
        "build_player_state_read_model",
        _stub_builder(state, calls),
    )
    connection = NoSqlConnection()

    service.build_player_presentation_state(connection, user_id=7)

    assert calls == [7]
    assert connection.execute_calls == []
