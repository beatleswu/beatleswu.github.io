from __future__ import annotations

import copy
import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from player_presentation_consumer_adapter import (
    PLAYER_PRESENTATION_API_V1,
    PLAYER_PRESENTATION_VIEW_MODEL_V1,
    PlayerPresentationConsumerAdapterError,
    PlayerPresentationViewModelV1,
    build_player_presentation_view_model,
    serialize_player_presentation_view_model,
)
from tests.test_a025_player_presentation_api_contract import _build as build_a025_snapshot


def _snapshot() -> dict:
    return build_a025_snapshot().to_dict()


def test_valid_full_presentation_snapshot_is_adapted() -> None:
    snapshot = _snapshot()
    snapshot["display_identity"] = {"display_name": "A026 QA", "username": "qa"}

    view_model = build_player_presentation_view_model(snapshot)
    payload = view_model.to_dict()

    assert isinstance(view_model, PlayerPresentationViewModelV1)
    assert payload["view_model_version"] == PLAYER_PRESENTATION_VIEW_MODEL_V1
    assert payload["contract_version"] == PLAYER_PRESENTATION_API_V1
    assert payload["projection_status"] == "OK"
    assert payload["player_id"] == 17
    assert payload["display_identity"] == {"display_name": "A026 QA", "username": "qa"}
    assert payload["hero"]["hero_id"] == "apprentice"
    assert payload["progression"]["xp"] == 120
    assert payload["progression"]["level"] == 3
    assert payload["persistent_hp"]["persistent_player_hp"] == 80
    assert payload["spirit"]["active"]["spirit_id"] == "ink_drop_kelpie"
    assert set(payload) == {
        "view_model_version",
        "contract_version",
        "projection_status",
        "player_id",
        "display_identity",
        "hero",
        "progression",
        "persistent_hp",
        "equipment",
        "spirit",
        "cosmetics",
    }
    assert "provenance" not in payload


def test_immutable_a025_transport_object_is_accepted() -> None:
    payload = build_player_presentation_view_model(build_a025_snapshot()).to_dict()

    assert payload["contract_version"] == PLAYER_PRESENTATION_API_V1
    assert payload["player_id"] == 17


def test_missing_optional_presentation_fields_are_allowed() -> None:
    snapshot = _snapshot()
    snapshot["hero"].pop("invalid_stored_value", None)
    snapshot["progression"].pop("source_version", None)
    snapshot["progression"].pop("invalid_fields", None)
    snapshot["progression"].pop("reason", None)
    snapshot["display_identity"] = None

    payload = build_player_presentation_view_model(snapshot).to_dict()

    assert "display_identity" not in payload
    assert payload["hero"]["hero_id"] == "apprentice"
    assert payload["progression"]["xp"] == 120


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("hero", "authority", "client_state"),
        ("equipment", "authority", "shop_catalog"),
        ("spirit", "authority", "client_selected_spirit"),
        ("cosmetics", "authority", "shop_catalog"),
        ("persistent_hp", "authority", "encounter_local_battle_state"),
    ],
)
def test_invalid_authority_payload_fails_closed(section: str, field: str, value: str) -> None:
    snapshot = _snapshot()
    snapshot[section][field] = value

    with pytest.raises(PlayerPresentationConsumerAdapterError):
        build_player_presentation_view_model(snapshot)


@pytest.mark.parametrize(
    "field",
    [
        "total_correct",
        "current_streak",
        "max_streak",
        "learning_stats",
        "engagement_streak",
        "correct_count",
    ],
)
def test_learning_and_streak_aliases_are_rejected(field: str) -> None:
    snapshot = _snapshot()
    snapshot["progression"][field] = 1

    with pytest.raises(PlayerPresentationConsumerAdapterError):
        build_player_presentation_view_model(snapshot)


@pytest.mark.parametrize("field", ["world", "selected_zone", "progression_zone"])
def test_world_fields_are_rejected(field: str) -> None:
    snapshot = _snapshot()
    snapshot[field] = {}

    with pytest.raises(PlayerPresentationConsumerAdapterError):
        build_player_presentation_view_model(snapshot)


@pytest.mark.parametrize("field", ["quest", "shop", "premium"])
def test_quest_shop_and_premium_fields_are_rejected(field: str) -> None:
    snapshot = _snapshot()
    snapshot[field] = {}

    with pytest.raises(PlayerPresentationConsumerAdapterError):
        build_player_presentation_view_model(snapshot)


@pytest.mark.parametrize("field", ["encounter_hp", "encounter"])
def test_encounter_hp_and_encounter_state_are_rejected(field: str) -> None:
    snapshot = _snapshot()
    snapshot[field] = {"current": 10}

    with pytest.raises(PlayerPresentationConsumerAdapterError):
        build_player_presentation_view_model(snapshot)


def test_persistent_hp_is_not_aliased_to_encounter_hp() -> None:
    snapshot = _snapshot()
    snapshot["persistent_hp"]["encounter_hp"] = 10

    with pytest.raises(PlayerPresentationConsumerAdapterError):
        build_player_presentation_view_model(snapshot)


@pytest.mark.parametrize("field", ["combat_stats", "combat_modifiers", "damage", "defense", "bonus"])
def test_equipment_combat_fields_are_rejected(field: str) -> None:
    snapshot = _snapshot()
    snapshot["equipment"][field] = {"value": 1}

    with pytest.raises(PlayerPresentationConsumerAdapterError):
        build_player_presentation_view_model(snapshot)


def test_equipment_combat_projection_flag_is_rejected() -> None:
    snapshot = _snapshot()
    snapshot["equipment"]["combat_stats_projected"] = True

    with pytest.raises(PlayerPresentationConsumerAdapterError):
        build_player_presentation_view_model(snapshot)


@pytest.mark.parametrize("field", ["combat_effects", "combat_effects_projected", "spirit_effects"])
def test_spirit_effect_fields_are_rejected(field: str) -> None:
    snapshot = _snapshot()
    snapshot["spirit"][field] = {"damage": 1} if field != "combat_effects_projected" else True

    with pytest.raises(PlayerPresentationConsumerAdapterError):
        build_player_presentation_view_model(snapshot)


def test_pure_cosmetics_are_accepted_without_effect_fields() -> None:
    snapshot = _snapshot()
    snapshot["cosmetics"]["selected"]["outfit"] = {
        "item_id": "robe_plain",
        "owned": True,
        "equipped": True,
        "display": {"item_id": "robe_plain", "name": "Plain Robe"},
        "presentation_only": True,
        "combat_power_projected": False,
    }
    snapshot["cosmetics"]["owned_items"] = [
        {
            "item_id": "robe_plain",
            "slot": "outfit",
            "display": {"item_id": "robe_plain", "name": "Plain Robe"},
            "source": "earned",
            "presentation_only": True,
            "combat_power_projected": False,
        }
    ]

    cosmetics = build_player_presentation_view_model(snapshot).to_dict()["cosmetics"]

    assert cosmetics["selected"]["outfit"]["item_id"] == "robe_plain"
    assert cosmetics["selected"]["outfit"]["presentation_only"] is True
    assert cosmetics["owned_items"][0]["item_id"] == "robe_plain"
    assert "combat_power_projected" not in json.dumps(cosmetics)
    assert "gameplay_effects_projected" not in cosmetics


def test_effect_bearing_cosmetic_fails_closed() -> None:
    snapshot = _snapshot()
    snapshot["cosmetics"]["selected"]["outfit"] = {
        "item_id": "legacy_effect_robe",
        "owned": True,
        "equipped": True,
        "display": {"item_id": "legacy_effect_robe"},
        "presentation_only": False,
        "combat_power_projected": True,
    }

    with pytest.raises(PlayerPresentationConsumerAdapterError):
        build_player_presentation_view_model(snapshot)


def test_view_model_is_immutable_and_detached() -> None:
    snapshot = _snapshot()
    view_model = build_player_presentation_view_model(snapshot)

    with pytest.raises(TypeError):
        view_model.hero["hero_id"] = "other"  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        view_model.player_id = 99  # type: ignore[misc]

    snapshot["hero"]["hero_id"] = "mutated-input"
    detached = view_model.to_dict()
    detached["hero"]["hero_id"] = "mutated-output"

    assert view_model.hero["hero_id"] == "apprentice"
    assert view_model.to_dict()["hero"]["hero_id"] == "apprentice"


def test_view_model_serialization_is_deterministic() -> None:
    first = serialize_player_presentation_view_model(
        build_player_presentation_view_model(_snapshot())
    )
    second = serialize_player_presentation_view_model(
        build_player_presentation_view_model(_snapshot())
    )

    assert first == second
    assert first == json.dumps(json.loads(first), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def test_adapter_has_no_route_api_storage_or_mutation_wiring() -> None:
    source = Path(__file__).parents[1].joinpath("player_presentation_consumer_adapter.py").read_text(encoding="utf-8")
    assert "@app.route" not in source
    assert "fetch(" not in source
    assert "localStorage" not in source
    assert "conn.execute" not in source
    assert ".commit(" not in source
    assert "INSERT" not in source
    assert "UPDATE" not in source
    assert "DELETE" not in source
