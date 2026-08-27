"""F024 Battlefield Boss reward result transport contract tests."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from pathlib import Path

import pytest

from world_battlefield_boss_reward_runtime import (
    CONFLICT,
    FIRST_CLEAR_ALREADY_OWNED_NO_OP,
    FIRST_CLEAR_NEW_COSMETIC,
    F023_REWARD_RESULT_CONTRACT_VERSION,
    NOT_FIRST_CLEAR,
    BattlefieldBossFirstClearRewardResult,
)
from world_battlefield_boss_reward_result import (
    build_battlefield_boss_reward_transport as build_f018_reward_transport,
)
from world_battlefield_boss_reward_transport import (
    F024_RESULT_TRANSPORT_CONTRACT_VERSION,
    BattlefieldBossRewardResultTransport,
    BattlefieldBossRewardTransportError,
    build_battlefield_boss_reward_transport,
)


def _f023_result(
    status: str,
    *,
    entitlement_replayed: bool = False,
) -> BattlefieldBossFirstClearRewardResult:
    if status == FIRST_CLEAR_NEW_COSMETIC:
        consumed, newly_owned, owned_no_op = True, True, False
        entitlement_status = "RECORDED"
    elif status == FIRST_CLEAR_ALREADY_OWNED_NO_OP:
        consumed, newly_owned, owned_no_op = True, False, True
        entitlement_status = "RECORDED"
    elif status == NOT_FIRST_CLEAR:
        consumed, newly_owned, owned_no_op = False, False, False
        entitlement_status = "REPLAYED" if entitlement_replayed else "ALREADY_CLAIMED"
    else:
        consumed, newly_owned, owned_no_op = False, False, False
        entitlement_status = "CONFLICT"
    return BattlefieldBossFirstClearRewardResult(
        contract_version=F023_REWARD_RESULT_CONTRACT_VERSION,
        status=status,
        entitlement_status=entitlement_status,
        user_id=7,
        zone_key="zone_01",
        requested_settlement_id="settlement-001",
        entitlement_settlement_id="settlement-001",
        encounter_operation_id="boss-operation-001",
        reward_policy_version="F022_BATTLEFIELD_BOSS_FIRST_CLEAR_MAPPING_A_V1",
        mapped_cosmetic_id="back_pack",
        first_clear_entitlement_consumed=consumed,
        entitlement_replayed=entitlement_replayed,
        cosmetic_newly_owned=newly_owned,
        already_owned_no_op=owned_no_op,
        acquisition_lineage_id=(
            "event-001" if status == FIRST_CLEAR_NEW_COSMETIC else None
        ),
    )


@pytest.mark.parametrize(
    "status",
    [
        FIRST_CLEAR_NEW_COSMETIC,
        FIRST_CLEAR_ALREADY_OWNED_NO_OP,
        NOT_FIRST_CLEAR,
    ],
)
def test_result_contract_supports_required_f023_statuses(status: str) -> None:
    transport = build_battlefield_boss_reward_transport(_f023_result(status))
    assert transport.contract_version == F024_RESULT_TRANSPORT_CONTRACT_VERSION
    assert transport.status == status
    assert transport.zone_key == "zone_01"
    assert transport.reward_policy_version == (
        "F022_BATTLEFIELD_BOSS_FIRST_CLEAR_MAPPING_A_V1"
    )
    assert transport.mapped_cosmetic_id == "back_pack"


def test_new_cosmetic_exposes_only_server_authored_transport_facts() -> None:
    payload = build_battlefield_boss_reward_transport(
        _f023_result(FIRST_CLEAR_NEW_COSMETIC)
    ).to_dict()
    assert set(payload) == {
        "contract_version",
        "status",
        "zone_key",
        "reward_policy_version",
        "mapped_cosmetic_id",
        "first_clear_entitlement_consumed",
        "cosmetic_newly_owned",
        "already_owned_no_op",
        "entitlement_replayed",
    }
    assert payload["first_clear_entitlement_consumed"] is True
    assert payload["cosmetic_newly_owned"] is True
    assert payload["already_owned_no_op"] is False


def test_already_owned_no_op_is_transportable_without_compensation_fields() -> None:
    transport = build_battlefield_boss_reward_transport(
        _f023_result(FIRST_CLEAR_ALREADY_OWNED_NO_OP)
    )
    assert transport.first_clear_entitlement_consumed is True
    assert transport.cosmetic_newly_owned is False
    assert transport.already_owned_no_op is True
    assert "compensation" not in transport.to_dict()
    assert "replacement" not in transport.to_dict()


def test_not_first_clear_preserves_replay_fact_without_new_grant() -> None:
    transport = build_battlefield_boss_reward_transport(
        _f023_result(NOT_FIRST_CLEAR, entitlement_replayed=True)
    )
    assert transport.status == NOT_FIRST_CLEAR
    assert transport.entitlement_replayed is True
    assert transport.first_clear_entitlement_consumed is False
    assert transport.cosmetic_newly_owned is False
    assert transport.already_owned_no_op is False


def test_conflict_is_preserved_without_reward_mutation_facts() -> None:
    transport = build_battlefield_boss_reward_transport(_f023_result(CONFLICT))
    assert transport.status == CONFLICT
    assert transport.first_clear_entitlement_consumed is False
    assert transport.cosmetic_newly_owned is False
    assert transport.already_owned_no_op is False


def test_f018_exposes_the_f024_transport_seam_without_owning_reward_policy() -> None:
    result = _f023_result(FIRST_CLEAR_NEW_COSMETIC)
    direct = build_battlefield_boss_reward_transport(result)
    through_f018 = build_f018_reward_transport(result)
    assert through_f018.to_dict() == direct.to_dict()
    assert through_f018.status == FIRST_CLEAR_NEW_COSMETIC


def test_unknown_payload_fails_closed() -> None:
    payload = build_battlefield_boss_reward_transport(
        _f023_result(FIRST_CLEAR_NEW_COSMETIC)
    ).to_dict()
    payload["zone_clear"] = False
    with pytest.raises(
        BattlefieldBossRewardTransportError,
        match="unknown_payload_field",
    ):
        BattlefieldBossRewardResultTransport.from_mapping(payload)


def test_missing_payload_fails_closed() -> None:
    payload = build_battlefield_boss_reward_transport(
        _f023_result(FIRST_CLEAR_NEW_COSMETIC)
    ).to_dict()
    del payload["mapped_cosmetic_id"]
    with pytest.raises(
        BattlefieldBossRewardTransportError,
        match="missing_payload_field",
    ):
        BattlefieldBossRewardResultTransport.from_mapping(payload)


def test_transport_is_immutable_and_round_trips_deterministically() -> None:
    transport = build_battlefield_boss_reward_transport(
        _f023_result(FIRST_CLEAR_NEW_COSMETIC)
    )
    with pytest.raises(FrozenInstanceError):
        transport.status = NOT_FIRST_CLEAR  # type: ignore[misc]
    first = transport.to_json()
    second = json.dumps(
        json.loads(first),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    assert first == second
    assert BattlefieldBossRewardResultTransport.from_json(first).to_dict() == (
        transport.to_dict()
    )


@pytest.mark.parametrize(
    "status",
    [FIRST_CLEAR_NEW_COSMETIC, FIRST_CLEAR_ALREADY_OWNED_NO_OP, CONFLICT],
)
def test_replay_flag_is_false_for_non_replay_statuses(status: str) -> None:
    result = _f023_result(status)
    payload = build_battlefield_boss_reward_transport(result).to_dict()
    payload["entitlement_replayed"] = True
    with pytest.raises(
        BattlefieldBossRewardTransportError,
        match="replay_flag_mismatch",
    ):
        BattlefieldBossRewardResultTransport.from_mapping(payload)


def test_raw_mapping_cannot_cross_typed_f023_authority_boundary() -> None:
    with pytest.raises(
        BattlefieldBossRewardTransportError,
        match="result_type_required",
    ):
        build_battlefield_boss_reward_transport(  # type: ignore[arg-type]
            {"status": FIRST_CLEAR_NEW_COSMETIC}
        )


def test_world_decision_fields_are_not_present_in_module_or_payload() -> None:
    source = Path(__file__).resolve().parents[1].joinpath(
        "world_battlefield_boss_reward_transport.py"
    ).read_text(encoding="utf-8").lower()
    payload = build_battlefield_boss_reward_transport(
        _f023_result(FIRST_CLEAR_NEW_COSMETIC)
    ).to_dict()
    for field in (
        "boss_ready",
        "lord_ready",
        "zone_clear",
        "zone_cleared",
        "star_granted",
        "stars",
        "next_zone",
        "next_zone_unlocked",
        "quest_completed",
    ):
        assert field not in payload
        assert field not in source


def test_transport_does_not_import_app_or_mutation_authorities() -> None:
    source = Path(__file__).resolve().parents[1].joinpath(
        "world_battlefield_boss_reward_transport.py"
    ).read_text(encoding="utf-8").lower()
    assert "import app" not in source
    assert "from app" not in source
    assert "flask" not in source
    assert ".commit(" not in source
    assert ".rollback(" not in source
    assert "event_outbox" not in source
    assert "player_wardrobe" not in source
    assert "migrations" not in source
