"""Focused F017 orchestration tests using disposable SQLite storage."""

from __future__ import annotations

from dataclasses import asdict
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from migrations.world_battlefield_boss_milestone_v1 import (
    TABLE_NAME,
    upgrade,
)
from world_battlefield_boss_orchestrator import (
    CONFLICT,
    RECORDED,
    REJECTED,
    REPLAYED,
    orchestrate_battlefield_boss_milestone,
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
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    upgrade(conn)
    conn.commit()
    return conn


def _intent(
    *,
    user_id: int = 7,
    zone_key: str = "zone_01",
    operation: str = "operation-001",
):
    return BattlefieldBossEncounterIntent.from_mapping(
        {
            "contract_version": BATTLEFIELD_BOSS_ENCOUNTER_INTENT_V1,
            "user_id": user_id,
            "zone_key": zone_key,
            "intent_operation_id": operation,
            "encounter_class": BATTLEFIELD_BOSS_CLASS,
            "eligibility_authority": WORLD_PROGRESSION_AUTHORITY,
            "eligibility_reference": f"world-{user_id}-{zone_key}",
            "requested_at": "2026-08-25T10:00:00Z",
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
):
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
    committed: bool = True,
):
    return ServerMonsterSettlementEvidence.from_server_settlement(
        user_id=user_id,
        zone_key=zone_key,
        monster_id=monster_id,
        encounter_class=BATTLEFIELD_BOSS_CLASS,
        encounter_operation_id=operation,
        settlement_id=settlement_id,
        hp_before=100,
        hp_after=0,
        committed=committed,
        occurred_at="2026-08-25T10:01:00Z",
    )


def _run(
    conn,
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
        intent=intent or _intent(
            user_id=user_id,
            zone_key=zone_key,
            operation=operation,
        ),
        selection=selection or _selection(
            user_id=user_id,
            zone_key=zone_key,
            operation=operation,
            monster_id=monster_id,
        ),
        settlement=settlement or _settlement(
            user_id=user_id,
            zone_key=zone_key,
            operation=operation,
            monster_id=monster_id,
            settlement_id=settlement_id,
        ),
        **kwargs,
    )


def test_valid_committed_battlefield_boss_fact_is_recorded_once():
    conn = _db()
    try:
        result = _run(conn)
        assert result.status == RECORDED
        assert result.recorded is True
        assert result.replayed is False
        assert result.user_id == 7
        assert result.settlement_id == "settlement-001"
        assert result.zone_key == "zone_01"
        assert result.monster_id == "legacy_bf_01_boss"
        assert result.encounter_operation_id == "operation-001"
        assert conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0] == 1
    finally:
        conn.close()


def test_same_fact_replay_is_idempotent_and_returns_replayed():
    conn = _db()
    try:
        first = _run(conn)
        replay = _run(conn, fact_replayed=True, created_at="2026-08-25T11:00:00Z")
        assert first.status == RECORDED
        assert replay.status == REPLAYED
        assert replay.recorded is False
        assert replay.replayed is True
        assert conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0] == 1
    finally:
        conn.close()


def test_changed_fact_same_user_and_settlement_is_conflict():
    conn = _db()
    try:
        _run(conn)
        changed = _run(
            conn,
            monster_id="legacy_bf_02_boss",
            settlement_id="settlement-001",
        )
        assert changed.status == CONFLICT
        assert changed.error_code == "CHANGED_AUTHORITATIVE_PAYLOAD"
        assert conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0] == 1
        assert conn.execute(f"SELECT monster_id FROM {TABLE_NAME}").fetchone()[0] == (
            "legacy_bf_01_boss"
        )
    finally:
        conn.close()


def test_same_settlement_id_across_users_isolated():
    conn = _db()
    try:
        first = _run(conn, user_id=7, settlement_id="shared-settlement")
        second = _run(conn, user_id=8, settlement_id="shared-settlement")
        assert first.status == RECORDED
        assert second.status == RECORDED
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
    ids=["invalid_world_eligibility", "lord_cannot_masquerade_as_boss"],
)
def test_invalid_world_or_lord_intent_is_rejected_before_storage(bad_intent):
    conn = _db()
    try:
        result = _run(conn, intent=bad_intent)
        assert result.status == REJECTED
        assert conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0] == 0
    finally:
        conn.close()


def test_monster_binding_mismatch_is_rejected_before_storage():
    conn = _db()
    try:
        result = _run(
            conn,
            selection=_selection(monster_id="legacy_bf_02_boss"),
            settlement=_settlement(monster_id="legacy_bf_01_boss"),
        )
        assert result.status == REJECTED
        assert result.error_code == "monster_binding_mismatch"
        assert conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0] == 0
    finally:
        conn.close()


def test_encounter_operation_mismatch_is_rejected_before_storage():
    conn = _db()
    try:
        result = _run(
            conn,
            selection=_selection(operation="operation-002"),
        )
        assert result.status == REJECTED
        assert result.error_code == "operation_binding_mismatch"
        assert conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0] == 0
    finally:
        conn.close()


def test_raw_client_defeat_claim_is_rejected():
    conn = _db()
    try:
        raw_claim = SimpleNamespace(
            user_id=7,
            zone_key="zone_01",
            monster_id="legacy_bf_01_boss",
            encounter_operation_id="operation-001",
            settlement_id="settlement-001",
            committed=True,
        )
        result = _run(conn, settlement=raw_claim)
        assert result.status == REJECTED
        assert result.error_code == "settlement_evidence_type_required"
        assert conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0] == 0
    finally:
        conn.close()


def test_service_commits_and_rolls_back_zero_times():
    conn = _db()

    class NoTransactionControl:
        _conn = conn

        def execute(self, sql, params=()):
            return conn.execute(sql, params)

        def commit(self):
            raise AssertionError("F017 must not commit")

        def rollback(self):
            raise AssertionError("F017 must not roll back")

    try:
        result = _run(NoTransactionControl())
        assert result.status == RECORDED
        assert conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0] == 1
        conn.rollback()
        assert conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0] == 0
    finally:
        conn.close()


def test_result_has_no_world_policy_decisions_and_module_has_no_runtime_wiring():
    conn = _db()
    try:
        result = _run(conn)
        fields = set(asdict(result))
        forbidden_fields = {
            "zone_clear",
            "zone_cleared",
            "star",
            "star_granted",
            "world_unlock",
            "lord_ready",
            "progression_zone",
            "selected_zone",
        }
        assert fields.isdisjoint(forbidden_fields)
    finally:
        conn.close()

    source = Path(__file__).resolve().parents[1].joinpath(
        "world_battlefield_boss_orchestrator.py"
    ).read_text(encoding="utf-8").lower()
    assert "import app" not in source
    assert "from app" not in source
    assert "flask" not in source
    assert "conn.execute" not in source
    assert ".commit(" not in source
    assert ".rollback(" not in source
    assert "zone_clear" not in source
    assert "lord_ready" not in source
    assert "selected_zone" not in source
    assert "progression_zone" not in source
