"""Focused tests for the pure F014 World/Monster Boss adapter core."""

from __future__ import annotations

from pathlib import Path

import pytest

from world_monster_boss_adapter import (
    BATTLEFIELD_BOSS_CLASS,
    CLIENT_CAN_AUTHORIZE_BOSS,
    BattlefieldBossAdapterValidationError,
    BattlefieldBossBindingError,
    BattlefieldBossEncounterBinding,
    ServerBattlefieldBossSelection,
    ServerMonsterSettlementEvidence,
    bind_battlefield_boss_selection,
    build_battlefield_boss_defeated_fact,
    build_f010_battlefield_boss_selector_call,
)
from world_monster_boundary_contract import (
    BATTLEFIELD_BOSS_DEFEATED_FACT_V1,
    BATTLEFIELD_BOSS_ENCOUNTER_INTENT_V1,
    BoundaryContractValidationError,
    BoundaryReplayMismatchError,
    BattlefieldBossDefeatedFact,
    BattlefieldBossEncounterIntent,
    SERVER_MONSTER_SETTLEMENT_AUTHORITY,
    WORLD_PROGRESSION_AUTHORITY,
    assert_defeated_fact_replay_compatible,
    defeated_fact_dedupe_key,
)


def _intent_payload(**changes):
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


def _intent(**changes):
    return BattlefieldBossEncounterIntent.from_mapping(_intent_payload(**changes))


def _call(**changes):
    return build_f010_battlefield_boss_selector_call(_intent(**changes))


def _selection(call, **changes):
    payload = {
        "user_id": call.user_id,
        "zone_key": call.zone_key,
        "encounter_operation_id": call.encounter_operation_id,
        "monster_id": "legacy_bf_01_boss",
        "encounter_class": BATTLEFIELD_BOSS_CLASS,
    }
    payload.update(changes)
    return ServerBattlefieldBossSelection.from_f010_result(**payload)


def _binding(**changes):
    call = _call()
    selection = _selection(call, **changes)
    return bind_battlefield_boss_selection(call, selection)


def _settlement(binding, **changes):
    payload = {
        "user_id": binding.user_id,
        "zone_key": binding.zone_key,
        "monster_id": binding.monster_id,
        "encounter_class": BATTLEFIELD_BOSS_CLASS,
        "encounter_operation_id": binding.encounter_operation_id,
        "settlement_id": "settlement-001",
        "hp_before": 100,
        "hp_after": 0,
        "committed": True,
        "occurred_at": "2026-08-25T10:01:00Z",
    }
    payload.update(changes)
    return ServerMonsterSettlementEvidence.from_server_settlement(**payload)


def test_valid_intent_maps_to_f010_boss_call_and_retains_authority_evidence():
    call = _call()

    assert call.to_selector_kwargs() == {
        "user_id": 7,
        "zone_key": "zone_01",
        "encounter_operation_id": "intent-001",
        "encounter_intent": "BATTLEFIELD_BOSS",
        "battlefield_boss_authorized": True,
    }
    assert call.battlefield_boss_authorized is True
    assert call.eligibility_reference == "world-eligibility-001"
    assert call.audit_context["eligibility_reference"] == "world-eligibility-001"
    assert call.intent_replay_fingerprint


def test_raw_or_client_payload_cannot_directly_authorize_f010_boss_call():
    with pytest.raises(BattlefieldBossAdapterValidationError, match="intent_type_required"):
        build_f010_battlefield_boss_selector_call(
            {
                **_intent_payload(),
                "battlefield_boss_authorized": True,
            }
        )

    assert CLIENT_CAN_AUTHORIZE_BOSS is False


def test_non_world_authority_is_rejected_before_adapter_output():
    with pytest.raises(BoundaryContractValidationError):
        BattlefieldBossEncounterIntent.from_mapping(
            _intent_payload(eligibility_authority="CLIENT")
        )


@pytest.mark.parametrize("encounter_class", ["LORD", "NORMAL"])
def test_lord_and_regular_intents_are_not_boss_intents(encounter_class):
    with pytest.raises(BoundaryContractValidationError):
        BattlefieldBossEncounterIntent.from_mapping(
            _intent_payload(encounter_class=encounter_class)
        )


def test_server_selection_is_required_and_must_match_the_intent_operation():
    call = _call()

    with pytest.raises(BattlefieldBossAdapterValidationError, match="selection_type_required"):
        bind_battlefield_boss_selection(call, {"monster_id": "legacy_bf_01_boss"})

    mismatched = _selection(call, encounter_operation_id="other-operation")
    with pytest.raises(BattlefieldBossBindingError, match="operation_binding_mismatch"):
        bind_battlefield_boss_selection(call, mismatched)


def test_valid_committed_boss_settlement_builds_f012_fact():
    binding = _binding()
    fact = build_battlefield_boss_defeated_fact(binding, _settlement(binding))

    assert fact.contract_version == BATTLEFIELD_BOSS_DEFEATED_FACT_V1
    assert fact.user_id == 7
    assert fact.zone_key == "zone_01"
    assert fact.monster_id == "legacy_bf_01_boss"
    assert fact.encounter_operation_id == binding.encounter_operation_id
    assert fact.defeated is True
    assert fact.source_authority == SERVER_MONSTER_SETTLEMENT_AUTHORITY
    assert fact.metadata["eligibility_reference"] == "world-eligibility-001"
    assert fact.metadata["operation_binding_verified"] is True


def test_precommit_settlement_cannot_emit_defeated_fact():
    binding = _binding()
    evidence = _settlement(binding, committed=False)

    with pytest.raises(BattlefieldBossAdapterValidationError, match="settlement_not_committed"):
        build_battlefield_boss_defeated_fact(binding, evidence)


def test_missing_operation_binding_fails_closed():
    with pytest.raises(BattlefieldBossBindingError, match="operation_binding_required"):
        build_battlefield_boss_defeated_fact(None, _settlement(_binding()))


def test_zone_mismatch_fails_closed():
    binding = _binding()
    evidence = _settlement(binding, zone_key="zone_02")

    with pytest.raises(BattlefieldBossBindingError, match="zone_binding_mismatch"):
        build_battlefield_boss_defeated_fact(binding, evidence)


def test_monster_mismatch_fails_closed():
    binding = _binding()
    evidence = _settlement(binding, monster_id="legacy_bf_02_boss")

    with pytest.raises(BattlefieldBossBindingError, match="monster_binding_mismatch"):
        build_battlefield_boss_defeated_fact(binding, evidence)


def test_operation_mismatch_fails_closed():
    binding = _binding()
    evidence = _settlement(binding, encounter_operation_id="other-operation")

    with pytest.raises(BattlefieldBossBindingError, match="operation_binding_mismatch"):
        build_battlefield_boss_defeated_fact(binding, evidence)


def test_non_boss_settlement_and_non_defeat_transition_are_rejected():
    binding = _binding()
    with pytest.raises(BattlefieldBossAdapterValidationError):
        _settlement(binding, encounter_class="NORMAL")
    with pytest.raises(BattlefieldBossAdapterValidationError, match="invalid_defeat_transition"):
        build_battlefield_boss_defeated_fact(
            binding,
            _settlement(binding, hp_before=100, hp_after=25),
        )


def test_cross_user_settlement_ids_remain_distinct_and_replay_is_compatible():
    binding = _binding()
    original = build_battlefield_boss_defeated_fact(binding, _settlement(binding))
    replay_payload = original.to_dict()
    replay_payload.update(
        {
            "occurred_at": "2026-08-25T10:05:00Z",
            "replayed": True,
        }
    )
    replay = BattlefieldBossDefeatedFact.from_mapping(replay_payload)

    assert defeated_fact_dedupe_key(original) == (7, "settlement-001")
    assert defeated_fact_dedupe_key(replay) == defeated_fact_dedupe_key(original)
    assert_defeated_fact_replay_compatible(original, replay)

    other_user_payload = original.to_dict()
    other_user_payload.update({"user_id": 8, "replayed": True})
    other_user = BattlefieldBossDefeatedFact.from_mapping(other_user_payload)
    assert defeated_fact_dedupe_key(other_user) != defeated_fact_dedupe_key(original)
    with pytest.raises(BoundaryReplayMismatchError):
        assert_defeated_fact_replay_compatible(original, other_user)


def test_fact_contains_no_world_decision_or_monster_stat_authority():
    fact = build_battlefield_boss_defeated_fact(_binding(), _settlement(_binding()))
    forbidden = {
        "boss_ready",
        "lord_ready",
        "stars",
        "zone_clear",
        "zone_cleared",
        "next_zone",
        "next_zone_unlock",
        "mastery_pct",
        "attack",
        "max_hp",
        "monster_hp",
        "stats",
        "drop",
        "reward",
    }
    payload = fact.to_dict()
    assert forbidden.isdisjoint(payload)
    assert forbidden.isdisjoint(payload["metadata"])


def test_adapter_is_pure_and_does_not_import_or_activate_runtime():
    source = Path(__file__).resolve().parents[1].joinpath(
        "world_monster_boss_adapter.py"
    ).read_text(encoding="utf-8")
    lowered = source.lower()

    assert "import app" not in lowered
    assert "from app" not in lowered
    assert "flask" not in lowered
    assert "psycopg" not in lowered
    assert "sqlite" not in lowered
    assert "insert into" not in lowered
    assert "update " not in lowered
    assert "f007" not in lowered
