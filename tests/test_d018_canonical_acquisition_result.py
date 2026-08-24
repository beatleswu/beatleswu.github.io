"""Pure contract tests for D018 Canonical Acquisition Result V1."""

from __future__ import annotations

import json

import pytest

from canonical_acquisition_result import (
    CONTRACT_VERSION,
    DESTINATIONS,
    GO_STONE_BLACK_STATUS,
    ITEM_CLASSES,
    SOURCE_TYPES,
    XP_AMULET_STATUS,
    AcquisitionResultValidationError,
    CanonicalAcquisitionResult,
)


def _payload(**overrides):
    payload = {
        "contract_version": CONTRACT_VERSION,
        "item_id": "go_spirit_candy",
        "quantity": 1,
        "source_type": "QUEST_REWARD",
        "source_operation_id": "quest-claim:daily:answer",
        "source_reference": "quest:daily:answer:2026-08-25",
        "destination": "STACK_INVENTORY",
        "ownership_authority": "pet_inventory",
        "ownership_reference": "pet_inventory:42:go_spirit_candy",
        "resulting_quantity": 4,
        "is_new": False,
        "can_equip": False,
        "can_use": True,
        "can_wear": False,
        "replayed": False,
        "lineage_event_id": "event-item-acquisition-1",
        "item_class": "SPIRIT_CONSUMABLE",
        "metadata": {},
    }
    payload.update(overrides)
    return payload


def _result(**overrides):
    return CanonicalAcquisitionResult.from_mapping(_payload(**overrides))


def _assert_code(code, **overrides):
    with pytest.raises(AcquisitionResultValidationError) as caught:
        _result(**overrides)
    assert caught.value.code == code


def test_result_has_required_fields_and_deterministic_round_trip():
    result = _result()

    encoded = result.to_json()
    assert json.loads(encoded) == result.to_dict()
    assert CanonicalAcquisitionResult.from_json(encoded) == result
    assert set(result.to_dict()) == {
        "contract_version",
        "item_id",
        "quantity",
        "source_type",
        "source_operation_id",
        "source_reference",
        "destination",
        "ownership_authority",
        "ownership_reference",
        "resulting_quantity",
        "is_new",
        "can_equip",
        "can_use",
        "can_wear",
        "replayed",
        "lineage_event_id",
        "item_class",
        "metadata",
    }


def test_envelope_is_immutable():
    result = _result()
    with pytest.raises((AttributeError, TypeError)):
        result.item_id = "different"  # type: ignore[misc]


@pytest.mark.parametrize("source_type", SOURCE_TYPES)
def test_all_supported_source_types_are_explicit(source_type):
    assert _result(source_type=source_type).source_type == source_type


@pytest.mark.parametrize("destination", DESTINATIONS)
def test_destination_vocabulary_is_explicit(destination):
    payload = _payload(destination=destination)
    if destination == "PLAYER_WARDROBE":
        payload.update(
            item_id="robe_plain",
            ownership_authority="player_wardrobe",
            ownership_reference="player_wardrobe:7",
            resulting_quantity=None,
            is_new=True,
            can_equip=False,
            can_use=False,
            can_wear=True,
            item_class="COSMETIC",
        )
    elif destination == "PLAYER_INVENTORY":
        payload.update(
            item_id="iron_sword",
            ownership_authority="player_inventory",
            ownership_reference="player_inventory:8",
            can_equip=True,
            can_use=False,
            item_class="WEAPON",
        )
    elif destination == "TROPHY_OWNERSHIP":
        payload.update(
            item_id="zone_trophy",
            ownership_authority="trophy_ownership",
            ownership_reference="trophy_ownership:9",
            resulting_quantity=None,
            is_new=True,
            can_use=False,
            item_class="TROPHY",
        )
    elif destination in {"QUESTION_CAPACITY", "CREDIT", "ENTITLEMENT"}:
        payload.update(
            item_id="capacity_or_credit",
            ownership_authority=destination.lower(),
            ownership_reference=f"{destination.lower()}:10",
            resulting_quantity=5,
            is_new=None,
            can_use=False,
            item_class="MATERIAL",
        )
    result = CanonicalAcquisitionResult.from_mapping(payload)
    assert result.destination == destination


def test_item_class_vocabulary_and_truthful_capabilities():
    assert set(ITEM_CLASSES) == {
        "WEAPON",
        "ARMOR",
        "ACCESSORY",
        "CONSUMABLE",
        "SPIRIT_CONSUMABLE",
        "XP_CONSUMABLE",
        "MATERIAL",
        "COSMETIC",
        "TROPHY",
    }
    assert _result(item_id="iron_sword", item_class="WEAPON", destination="PLAYER_INVENTORY", ownership_authority="player_inventory", ownership_reference="player_inventory:1", can_equip=True, can_use=False).can_equip
    assert _result(item_class="CONSUMABLE", can_equip=False, can_use=True).can_use
    assert _result(item_class="MATERIAL", can_equip=False, can_use=False, can_wear=False).item_class == "MATERIAL"
    assert _result(item_id="robe_plain", item_class="COSMETIC", destination="PLAYER_WARDROBE", ownership_authority="player_wardrobe", ownership_reference="player_wardrobe:2", resulting_quantity=None, is_new=True, can_equip=False, can_use=False, can_wear=True).can_wear


def test_is_new_is_independent_from_replay():
    assert _result(is_new=True, replayed=False).is_new is True
    assert _result(is_new=False, replayed=False).is_new is False
    assert _result(is_new=False, replayed=True).replayed is True
    assert _result(is_new=True, replayed=True, metadata={"ownership_evidence": {"verified": True, "pre_grant_owned": False, "authority": "player_inventory"}}).is_new is True


def test_replay_cannot_claim_new_without_ownership_evidence():
    _assert_code("REPLAY_NEW_OWNERSHIP_UNVERIFIED", is_new=True, replayed=True)
    _assert_code(
        "REPLAY_NEW_OWNERSHIP_UNVERIFIED",
        is_new=True,
        replayed=True,
        metadata={"ownership_evidence": {"verified": False, "pre_grant_owned": False, "authority": "player_inventory"}},
    )


def test_d5a_acquisition_and_d5c_use_are_not_conflated():
    result = _result(
        source_type="QUEST_REWARD",
        metadata={"lineage_kind": "D5A_ACQUISITION"},
    )
    payload = result.to_dict()
    assert payload["source_type"] == "QUEST_REWARD"
    assert payload["lineage_event_id"] == "event-item-acquisition-1"
    assert "used" not in payload
    assert "equipped" not in payload
    assert "consumed" not in payload
    assert "worn" not in payload
    assert payload["can_use"] is True


@pytest.mark.parametrize(
    ("producer", "source_type"),
    [
        ("monster", "MONSTER_DROP"),
        ("quest", "QUEST_REWARD"),
        ("premium", "PREMIUM_REWARD"),
        ("shop_c019", "SHOP_COIN_PURCHASE"),
    ],
)
def test_named_producer_results_can_target_the_same_envelope(producer, source_type):
    result = _result(
        source_type=source_type,
        source_operation_id=f"{producer}:operation:1",
        source_reference=f"{producer}:reference:1",
        lineage_event_id=f"{producer}:lineage:1",
        metadata={"producer": producer},
    )
    assert result.source_type == source_type
    assert result.source_operation_id.startswith(producer)
    assert result.lineage_event_id.startswith(producer)


def test_missing_identity_lineage_and_operation_fail_closed():
    _assert_code("MISSING_REQUIRED_FIELD", item_id="")
    _assert_code("MISSING_REQUIRED_FIELD", source_operation_id="")
    _assert_code("MISSING_REQUIRED_FIELD", lineage_event_id="")
    _assert_code("MISSING_REQUIRED_FIELD", ownership_reference="")


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("quantity", 0, "NON_POSITIVE_QUANTITY"),
        ("quantity", -1, "NON_POSITIVE_QUANTITY"),
        ("resulting_quantity", -1, "NEGATIVE_RESULTING_QUANTITY"),
        ("source_type", "UNKNOWN", "UNKNOWN_ENUM_VALUE"),
        ("destination", "UNKNOWN", "UNKNOWN_ENUM_VALUE"),
        ("item_class", "UNKNOWN", "UNKNOWN_ENUM_VALUE"),
    ],
)
def test_invalid_identity_and_quantity_values_fail_closed(field, value, code):
    _assert_code(code, **{field: value})


def test_capability_contradictions_fail_closed():
    _assert_code("TROPHY_GAMEPLAY_CAPABILITY", item_id="trophy", item_class="TROPHY", can_equip=True, can_use=False, can_wear=False)
    _assert_code("MATERIAL_GAMEPLAY_CAPABILITY", item_class="MATERIAL", can_equip=False, can_use=True, can_wear=False)
    _assert_code("COSMETIC_CAPABILITY_CONTRADICTION", item_id="robe", item_class="COSMETIC", destination="PLAYER_WARDROBE", ownership_authority="player_wardrobe", ownership_reference="player_wardrobe:1", can_equip=False, can_use=True, can_wear=True)
    _assert_code("COSMETIC_COMBAT_CAPABILITY", item_id="robe", item_class="COSMETIC", destination="PLAYER_WARDROBE", ownership_authority="player_wardrobe", ownership_reference="player_wardrobe:1", can_equip=True, can_use=False, can_wear=True)


def test_go_stone_black_is_a_locked_inventory_only_trophy():
    result = _result(
        item_id="go_stone_black",
        item_class="TROPHY",
        destination="PLAYER_INVENTORY",
        ownership_authority="player_inventory",
        ownership_reference="player_inventory:go-stone-1",
        can_equip=False,
        can_use=False,
        can_wear=False,
        metadata={"special_status": GO_STONE_BLACK_STATUS},
    )
    assert result.item_class == "TROPHY"
    assert result.can_equip is False
    assert result.can_use is False
    assert result.can_wear is False
    _assert_code("GO_STONE_BLACK_LOCK", item_id="go_stone_black", item_class="TROPHY", destination="PLAYER_INVENTORY", ownership_authority="player_inventory", ownership_reference="player_inventory:go-stone-2", can_use=True, can_equip=False, can_wear=False)


def test_xp_amulet_hold_is_preserved_without_assigning_behavior():
    result = _result(
        item_id="xp_amulet",
        item_class="ACCESSORY",
        destination="PLAYER_INVENTORY",
        ownership_authority="player_inventory",
        ownership_reference="player_inventory:amulet-1",
        can_equip=False,
        can_use=False,
        can_wear=False,
        metadata={"special_status": XP_AMULET_STATUS},
    )
    assert result.metadata["special_status"] == XP_AMULET_STATUS
    _assert_code("XP_AMULET_HOLD", item_id="xp_amulet", item_class="ACCESSORY", destination="PLAYER_INVENTORY", ownership_authority="player_inventory", ownership_reference="player_inventory:amulet-2", can_equip=True, can_use=False, can_wear=False, metadata={"special_status": XP_AMULET_STATUS})
    _assert_code("XP_AMULET_HOLD", item_id="xp_amulet", item_class="ACCESSORY", destination="PLAYER_INVENTORY", ownership_authority="player_inventory", ownership_reference="player_inventory:amulet-3", can_equip=False, can_use=False, can_wear=False)


def test_mapping_validation_rejects_missing_and_unknown_top_level_fields():
    missing = _payload()
    del missing["lineage_event_id"]
    with pytest.raises(AcquisitionResultValidationError) as missing_error:
        CanonicalAcquisitionResult.from_mapping(missing)
    assert missing_error.value.code == "MISSING_REQUIRED_FIELD"

    unknown = _payload(unrelated="not part of v1")
    with pytest.raises(AcquisitionResultValidationError) as unknown_error:
        CanonicalAcquisitionResult.from_mapping(unknown)
    assert unknown_error.value.code == "UNKNOWN_FIELD"


def test_metadata_is_bounded_and_immutable():
    result = _result(metadata={"source": {"producer": "quest"}, "tags": ["a", "b"]})
    assert result.to_dict()["metadata"] == {"source": {"producer": "quest"}, "tags": ["a", "b"]}
    with pytest.raises(TypeError):
        result.metadata["source"] = "changed"  # type: ignore[index]
    _assert_code("METADATA_TOO_LARGE", metadata={str(index): index for index in range(33)})
