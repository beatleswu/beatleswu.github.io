"""Focused tests for the pure F012 World/Monster boundary contracts."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from world_monster_boundary_contract import (
    BATTLEFIELD_BOSS_CLASS,
    BATTLEFIELD_BOSS_DEFEATED_FACT_V1,
    BATTLEFIELD_BOSS_ENCOUNTER_INTENT_V1,
    BoundaryContractValidationError,
    BoundaryReplayMismatchError,
    BattlefieldBossDefeatedFact,
    BattlefieldBossEncounterIntent,
    SERVER_MONSTER_SETTLEMENT_AUTHORITY,
    WORLD_PROGRESSION_AUTHORITY,
    assert_defeated_fact_replay_compatible,
    assert_intent_replay_compatible,
    defeated_fact_dedupe_key,
    intent_operation_key,
)


def _intent(**changes):
    payload = {
        "contract_version": BATTLEFIELD_BOSS_ENCOUNTER_INTENT_V1,
        "user_id": 7,
        "zone_key": "zone_01",
        "intent_operation_id": "intent-001",
        "encounter_class": BATTLEFIELD_BOSS_CLASS,
        "eligibility_authority": WORLD_PROGRESSION_AUTHORITY,
        "eligibility_reference": "world-eligibility-001",
        "requested_at": "2026-08-25T10:00:00Z",
        "replayed": False,
        "metadata": {"policy_version": "world-boundary-v1"},
    }
    payload.update(changes)
    return payload


def _fact(**changes):
    payload = {
        "contract_version": BATTLEFIELD_BOSS_DEFEATED_FACT_V1,
        "user_id": 7,
        "zone_key": "zone_01",
        "monster_id": "legacy_bf_01_boss",
        "encounter_class": BATTLEFIELD_BOSS_CLASS,
        "encounter_operation_id": "encounter-001",
        "settlement_id": "settlement-001",
        "defeated": True,
        "source_authority": SERVER_MONSTER_SETTLEMENT_AUTHORITY,
        "occurred_at": "2026-08-25T10:01:00Z",
        "replayed": False,
        "metadata": {"settlement_version": "server-monster-v1"},
    }
    payload.update(changes)
    return payload


def test_valid_battlefield_boss_intent_round_trips_as_json_safe_data():
    intent = BattlefieldBossEncounterIntent.from_mapping(_intent())

    assert intent.encounter_class == BATTLEFIELD_BOSS_CLASS
    assert intent.eligibility_authority == WORLD_PROGRESSION_AUTHORITY
    assert json.loads(intent.canonical_json()) == intent.to_dict()
    assert intent_operation_key(intent) == (7, "intent-001")


def test_valid_battlefield_boss_defeated_fact_round_trips_as_json_safe_data():
    fact = BattlefieldBossDefeatedFact.from_mapping(_fact())

    assert fact.defeated is True
    assert fact.source_authority == SERVER_MONSTER_SETTLEMENT_AUTHORITY
    assert json.loads(fact.canonical_json()) == fact.to_dict()
    assert defeated_fact_dedupe_key(fact) == "settlement-001"


def test_contract_objects_and_nested_metadata_are_immutable():
    intent = BattlefieldBossEncounterIntent.from_mapping(
        _intent(metadata={"nested": {"value": "fixed"}})
    )

    with pytest.raises(FrozenInstanceError):
        intent.zone_key = "zone_02"
    with pytest.raises(TypeError):
        intent.metadata["new"] = "not allowed"
    with pytest.raises(TypeError):
        intent.metadata["nested"]["value"] = "not allowed"


def test_canonical_serialization_is_deterministic_for_key_order():
    left = BattlefieldBossEncounterIntent.from_mapping(
        _intent(metadata={"b": 2, "a": 1})
    )
    right = BattlefieldBossEncounterIntent.from_mapping(
        _intent(metadata={"a": 1, "b": 2})
    )

    assert left.canonical_json() == right.canonical_json()
    assert left.fingerprint() == right.fingerprint()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("encounter_class", "LORD"),
        ("encounter_class", "NORMAL"),
        ("eligibility_authority", "CLIENT"),
    ],
)
def test_intent_requires_world_authorized_battlefield_boss_class(field, value):
    with pytest.raises(BoundaryContractValidationError):
        BattlefieldBossEncounterIntent.from_mapping(_intent(**{field: value}))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("encounter_class", "LORD"),
        ("encounter_class", "NORMAL"),
        ("defeated", False),
        ("source_authority", "CLIENT"),
    ],
)
def test_defeated_fact_requires_server_battlefield_boss_defeat(field, value):
    with pytest.raises(BoundaryContractValidationError):
        BattlefieldBossDefeatedFact.from_mapping(_fact(**{field: value}))


@pytest.mark.parametrize("field", ["monster_id", "encounter_operation_id", "settlement_id"])
def test_defeated_fact_requires_non_empty_server_identifiers(field):
    with pytest.raises(BoundaryContractValidationError):
        BattlefieldBossDefeatedFact.from_mapping(_fact(**{field: ""}))


def test_unknown_top_level_fields_fail_closed_instead_of_being_dropped():
    with pytest.raises(BoundaryContractValidationError, match="unknown_top_level_field"):
        BattlefieldBossEncounterIntent.from_mapping(_intent(boss_ready=True))
    with pytest.raises(BoundaryContractValidationError, match="unknown_top_level_field"):
        BattlefieldBossDefeatedFact.from_mapping(_fact(zone_cleared=True))


@pytest.mark.parametrize(
    "field",
    [
        "boss_ready",
        "lord_ready",
        "stars",
        "zone_cleared",
        "next_zone_unlocked",
        "mastery_pct",
    ],
)
def test_world_policy_fields_are_rejected_from_metadata(field):
    with pytest.raises(BoundaryContractValidationError, match="forbidden_authority_field"):
        BattlefieldBossEncounterIntent.from_mapping(_intent(metadata={field: True}))
    with pytest.raises(BoundaryContractValidationError, match="forbidden_authority_field"):
        BattlefieldBossDefeatedFact.from_mapping(_fact(metadata={field: True}))


@pytest.mark.parametrize("field", ["monster_attack", "monster_hp_max", "stats", "drop"])
def test_intent_cannot_carry_monster_stat_or_reward_authority(field):
    with pytest.raises(BoundaryContractValidationError):
        BattlefieldBossEncounterIntent.from_mapping(_intent(metadata={field: 1}))
    with pytest.raises(BoundaryContractValidationError):
        BattlefieldBossDefeatedFact.from_mapping(_fact(metadata={field: 1}))


def test_intent_retry_allows_delivery_metadata_changes_but_not_meaning_changes():
    original = BattlefieldBossEncounterIntent.from_mapping(_intent())
    replay = BattlefieldBossEncounterIntent.from_mapping(
        _intent(requested_at="2026-08-25T10:05:00Z", replayed=True)
    )

    assert original.replay_fingerprint() == replay.replay_fingerprint()
    assert_intent_replay_compatible(original, replay)

    changed = BattlefieldBossEncounterIntent.from_mapping(
        _intent(replayed=True, zone_key="zone_02")
    )
    with pytest.raises(BoundaryReplayMismatchError, match="intent_payload_mismatch"):
        assert_intent_replay_compatible(original, changed)


def test_intent_operation_identity_must_not_change_on_replay():
    original = BattlefieldBossEncounterIntent.from_mapping(_intent())
    changed = BattlefieldBossEncounterIntent.from_mapping(
        _intent(intent_operation_id="intent-002", replayed=True)
    )

    with pytest.raises(BoundaryReplayMismatchError, match="intent_operation_mismatch"):
        assert_intent_replay_compatible(original, changed)


def test_defeated_fact_replay_uses_settlement_id_and_rejects_changed_payload():
    original = BattlefieldBossDefeatedFact.from_mapping(_fact())
    replay = BattlefieldBossDefeatedFact.from_mapping(
        _fact(occurred_at="2026-08-25T10:05:00Z", replayed=True)
    )

    assert original.replay_fingerprint() == replay.replay_fingerprint()
    assert_defeated_fact_replay_compatible(original, replay)

    changed = BattlefieldBossDefeatedFact.from_mapping(
        _fact(replayed=True, monster_id="legacy_bf_02_boss")
    )
    with pytest.raises(BoundaryReplayMismatchError, match="fact_payload_mismatch"):
        assert_defeated_fact_replay_compatible(original, changed)


def test_fact_dedupe_identity_cannot_change():
    original = BattlefieldBossDefeatedFact.from_mapping(_fact())
    changed = BattlefieldBossDefeatedFact.from_mapping(
        _fact(settlement_id="settlement-002", replayed=True)
    )

    with pytest.raises(BoundaryReplayMismatchError, match="settlement_id_mismatch"):
        assert_defeated_fact_replay_compatible(original, changed)


def test_serialized_contracts_contain_no_world_decision_fields():
    intent = BattlefieldBossEncounterIntent.from_mapping(_intent())
    fact = BattlefieldBossDefeatedFact.from_mapping(_fact())
    forbidden = {
        "boss_ready",
        "lord_ready",
        "stars",
        "zone_cleared",
        "next_zone_unlocked",
        "mastery_pct",
    }

    assert forbidden.isdisjoint(intent.to_dict())
    assert forbidden.isdisjoint(fact.to_dict())


def test_contract_module_is_runtime_independent_and_does_not_write_storage():
    source = Path(__file__).resolve().parents[1].joinpath(
        "world_monster_boundary_contract.py"
    ).read_text(encoding="utf-8")
    lowered = source.lower()

    assert "import app" not in lowered
    assert "from app" not in lowered
    assert "get_db" not in lowered
    assert "sqlite" not in lowered
    assert "psycopg" not in lowered
    assert "insert into" not in lowered
    assert "update " not in lowered
    assert "f007" not in lowered


def test_metadata_is_bounded_and_only_json_safe_values_are_accepted():
    with pytest.raises(BoundaryContractValidationError, match="metadata_too_large"):
        BattlefieldBossEncounterIntent.from_mapping(
            _intent(metadata={str(index): index for index in range(33)})
        )
    with pytest.raises(BoundaryContractValidationError, match="metadata_not_json_safe"):
        BattlefieldBossEncounterIntent.from_mapping(_intent(metadata={"object": object()}))
