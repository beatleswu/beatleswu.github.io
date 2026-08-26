"""Focused F018 result-shell tests over the accepted F017/F015 path."""

from __future__ import annotations

from dataclasses import asdict
import sqlite3
from pathlib import Path
import re
from types import SimpleNamespace

import pytest

from migrations.world_battlefield_boss_milestone_v1 import TABLE_NAME, upgrade
from world_battlefield_boss_orchestrator import (
    CONFLICT,
    RECORDED,
    REJECTED,
    REPLAYED,
    orchestrate_battlefield_boss_milestone,
)
from world_battlefield_boss_reward_result import (
    F018_RESULT_CONTRACT_VERSION,
    REWARD_CONTENT_AUTHORITY_MISSING_STATUS,
    BattlefieldBossMilestoneRewardResult,
    build_battlefield_boss_milestone_reward_result,
)
from world_monster_boss_adapter import (
    BATTLEFIELD_BOSS_CLASS,
    ServerBattlefieldBossSelection,
    ServerMonsterSettlementEvidence,
)
from world_monster_boundary_contract import (
    BATTLEFIELD_BOSS_ENCOUNTER_INTENT_V1,
    BattlefieldBossEncounterIntent,
    WORLD_PROGRESSION_AUTHORITY,
)


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    upgrade(conn)
    conn.commit()
    return conn


def _intent(
    *,
    user_id: int = 7,
    zone_key: str = "zone_01",
    operation: str = "operation-001",
) -> BattlefieldBossEncounterIntent:
    return BattlefieldBossEncounterIntent.from_mapping(
        {
            "contract_version": BATTLEFIELD_BOSS_ENCOUNTER_INTENT_V1,
            "user_id": user_id,
            "zone_key": zone_key,
            "intent_operation_id": operation,
            "encounter_class": BATTLEFIELD_BOSS_CLASS,
            "eligibility_authority": WORLD_PROGRESSION_AUTHORITY,
            "eligibility_reference": f"world-{user_id}-{zone_key}",
            "requested_at": "2026-08-26T10:00:00Z",
            "replayed": False,
            "metadata": {"policy_version": "world-boundary-v1"},
        }
    )


def _selection(
    *,
    user_id: int = 7,
    zone_key: str = "zone_01",
    operation: str = "operation-001",
    monster_id: str = "legacy_bf_01_boss",
) -> ServerBattlefieldBossSelection:
    return ServerBattlefieldBossSelection.from_f010_result(
        user_id=user_id,
        zone_key=zone_key,
        encounter_operation_id=operation,
        monster_id=monster_id,
        encounter_class=BATTLEFIELD_BOSS_CLASS,
    )


def _settlement(
    *,
    user_id: int = 7,
    zone_key: str = "zone_01",
    operation: str = "operation-001",
    monster_id: str = "legacy_bf_01_boss",
    settlement_id: str = "settlement-001",
) -> ServerMonsterSettlementEvidence:
    return ServerMonsterSettlementEvidence.from_server_settlement(
        user_id=user_id,
        zone_key=zone_key,
        monster_id=monster_id,
        encounter_class=BATTLEFIELD_BOSS_CLASS,
        encounter_operation_id=operation,
        settlement_id=settlement_id,
        hp_before=100,
        hp_after=0,
        committed=True,
        occurred_at="2026-08-26T10:01:00Z",
    )


def _run(
    conn: sqlite3.Connection,
    *,
    user_id: int = 7,
    zone_key: str = "zone_01",
    operation: str = "operation-001",
    monster_id: str = "legacy_bf_01_boss",
    settlement_id: str = "settlement-001",
    intent=None,
    selection=None,
    settlement=None,
    **kwargs,
):
    return orchestrate_battlefield_boss_milestone(
        conn,
        authenticated_user_id=user_id,
        intent=intent if intent is not None else _intent(
            user_id=user_id,
            zone_key=zone_key,
            operation=operation,
        ),
        selection=selection if selection is not None else _selection(
            user_id=user_id,
            zone_key=zone_key,
            operation=operation,
            monster_id=monster_id,
        ),
        settlement=settlement if settlement is not None else _settlement(
            user_id=user_id,
            zone_key=zone_key,
            operation=operation,
            monster_id=monster_id,
            settlement_id=settlement_id,
        ),
        **kwargs,
    )


def test_recorded_f017_milestone_becomes_detached_f018_result():
    conn = _db()
    try:
        milestone = _run(conn)
        result = build_battlefield_boss_milestone_reward_result(milestone)

        assert milestone.status == RECORDED
        assert result.status == RECORDED
        assert result.contract_version == F018_RESULT_CONTRACT_VERSION
        assert result.milestone_status == RECORDED
        assert result.reward_status == REWARD_CONTENT_AUTHORITY_MISSING_STATUS
        assert result.reward_content_authority_missing is True
        assert result.recorded is True
        assert result.replayed is False
        assert result.user_id == 7
        assert result.settlement_id == "settlement-001"
        assert result.zone_key == "zone_01"
        assert result.monster_id == "legacy_bf_01_boss"
        assert result.encounter_operation_id == "operation-001"
    finally:
        conn.close()


def test_same_fact_replay_is_replayed_without_new_row_or_reward_content():
    conn = _db()
    try:
        first = build_battlefield_boss_milestone_reward_result(_run(conn))
        replay = build_battlefield_boss_milestone_reward_result(
            _run(conn, fact_replayed=True, created_at="2026-08-26T11:00:00Z")
        )

        assert first.status == RECORDED
        assert replay.status == REPLAYED
        assert replay.recorded is False
        assert replay.replayed is True
        assert replay.reward_content_authority_missing is True
        assert conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0] == 1
    finally:
        conn.close()


def test_changed_fact_conflict_is_preserved_without_reward_projection():
    conn = _db()
    try:
        _run(conn)
        conflict = build_battlefield_boss_milestone_reward_result(
            _run(
                conn,
                monster_id="legacy_bf_02_boss",
                settlement_id="settlement-001",
            )
        )

        assert conflict.status == CONFLICT
        assert conflict.milestone_status == CONFLICT
        assert conflict.error_code == "CHANGED_AUTHORITATIVE_PAYLOAD"
        assert conflict.reward_content_authority_missing is True
        assert conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0] == 1
        assert conn.execute(f"SELECT monster_id FROM {TABLE_NAME}").fetchone()[0] == (
            "legacy_bf_01_boss"
        )
    finally:
        conn.close()


def test_same_settlement_id_for_different_users_isolated():
    conn = _db()
    try:
        first = build_battlefield_boss_milestone_reward_result(
            _run(conn, user_id=7, settlement_id="shared-settlement")
        )
        second = build_battlefield_boss_milestone_reward_result(
            _run(conn, user_id=8, settlement_id="shared-settlement")
        )

        assert first.status == RECORDED
        assert second.status == RECORDED
        assert first.user_id != second.user_id
        assert first.settlement_id == second.settlement_id
        assert conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0] == 2
    finally:
        conn.close()


@pytest.mark.parametrize(
    "bad_intent",
    [
        SimpleNamespace(
            user_id=7,
            zone_key="zone_01",
            intent_operation_id="operation-001",
            encounter_class=BATTLEFIELD_BOSS_CLASS,
            eligibility_authority="CLIENT",
        ),
        SimpleNamespace(
            user_id=7,
            zone_key="zone_01",
            intent_operation_id="operation-001",
            encounter_class="LORD",
            eligibility_authority=WORLD_PROGRESSION_AUTHORITY,
        ),
    ],
    ids=["client-eligibility", "lord-cannot-be-boss"],
)
def test_invalid_eligibility_or_lord_path_is_rejected_and_has_no_reward(
    bad_intent,
):
    conn = _db()
    try:
        milestone = _run(conn, intent=bad_intent)
        result = build_battlefield_boss_milestone_reward_result(milestone)

        assert milestone.status == REJECTED
        assert result.status == REJECTED
        assert result.reward_content_authority_missing is True
        assert conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0] == 0
    finally:
        conn.close()


def test_raw_f017_mapping_cannot_cross_typed_result_boundary():
    result = build_battlefield_boss_milestone_reward_result(
        {"status": RECORDED, "user_id": 7}
    )

    assert result.status == REJECTED
    assert result.error_code == "MILESTONE_RESULT_TYPE_REQUIRED"
    assert result.recorded is False
    assert result.replayed is False


def test_result_has_no_reward_values_or_world_policy_decisions():
    conn = _db()
    try:
        result = build_battlefield_boss_milestone_reward_result(_run(conn))
        fields = set(asdict(result))
        forbidden_fields = {
            "coins",
            "xp",
            "item",
            "drop",
            "reward_profile_id",
            "zone_clear",
            "zone_cleared",
            "star",
            "star_granted",
            "world_unlock",
            "lord_ready",
            "selected_zone",
            "progression_zone",
            "next_zone",
            "quest_completed",
        }

        assert fields.isdisjoint(forbidden_fields)
        assert result.reward_status == REWARD_CONTENT_AUTHORITY_MISSING_STATUS
        for forbidden in ("coins", "xp", "item", "drop", "reward_profile_id"):
            assert not hasattr(result, forbidden)
    finally:
        conn.close()


def test_f018_is_pure_and_does_not_import_runtime_or_storage_authority():
    source = Path(__file__).resolve().parents[1].joinpath(
        "world_battlefield_boss_reward_result.py"
    ).read_text(encoding="utf-8").lower()

    for forbidden in (
        "import app",
        "from app",
        "flask",
        ".execute(",
        ".commit(",
        ".rollback(",
        "create table",
        "coins",
        "reward_profile_id",
        "zone_clear",
        "lord_ready",
        "star_granted",
        "next_zone",
    ):
        assert forbidden not in source
    assert re.search(r"\bxp\b", source) is None


def test_f018_result_type_is_immutable():
    result = BattlefieldBossMilestoneRewardResult(
        contract_version=F018_RESULT_CONTRACT_VERSION,
        status=REJECTED,
        milestone_status=REJECTED,
        reward_status=REWARD_CONTENT_AUTHORITY_MISSING_STATUS,
        reward_content_authority_missing=True,
        user_id=None,
        settlement_id=None,
        zone_key=None,
        monster_id=None,
        encounter_operation_id=None,
        recorded=False,
        replayed=False,
        error_code="test",
    )

    with pytest.raises(AttributeError):
        result.status = RECORDED
