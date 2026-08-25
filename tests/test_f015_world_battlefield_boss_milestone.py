"""Disposable SQLite contract tests for the F015 milestone projection."""

from __future__ import annotations

from dataclasses import asdict
import sqlite3
from pathlib import Path

import pytest

from migrations.world_battlefield_boss_milestone_v1 import (
    DEDUPE_KEY,
    TABLE_NAME,
    downgrade_for_isolated_test,
    upgrade,
    validate_schema,
)
from world_battlefield_boss_milestone import (
    MilestoneProjectionConflict,
    MilestoneProjectionSchemaUnavailable,
    MilestoneProjectionValidationError,
    record_battlefield_boss_defeated_fact,
)
from world_monster_boss_adapter import (
    BATTLEFIELD_BOSS_CLASS,
    BattlefieldBossAdapterValidationError,
    ServerBattlefieldBossSelection,
    ServerMonsterSettlementEvidence,
    bind_battlefield_boss_selection,
    build_battlefield_boss_defeated_fact,
    build_f010_battlefield_boss_selector_call,
)
from world_monster_boundary_contract import (
    BATTLEFIELD_BOSS_DEFEATED_FACT_V1,
    BATTLEFIELD_BOSS_ENCOUNTER_INTENT_V1,
    BattlefieldBossDefeatedFact,
    BattlefieldBossEncounterIntent,
    WORLD_PROGRESSION_AUTHORITY,
)


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _intent(*, user_id: int = 7, zone_key: str = "zone_01", operation: str = "intent-001"):
    return BattlefieldBossEncounterIntent.from_mapping(
        {
            "contract_version": BATTLEFIELD_BOSS_ENCOUNTER_INTENT_V1,
            "user_id": user_id,
            "zone_key": zone_key,
            "intent_operation_id": operation,
            "encounter_class": BATTLEFIELD_BOSS_CLASS,
            "eligibility_authority": WORLD_PROGRESSION_AUTHORITY,
            "eligibility_reference": f"world-eligibility-{user_id}-{zone_key}",
            "requested_at": "2026-08-25T10:00:00Z",
            "replayed": False,
            "metadata": {"policy_version": "world-boundary-v1"},
        }
    )


def _fact(
    *,
    user_id: int = 7,
    zone_key: str = "zone_01",
    operation: str = "intent-001",
    monster_id: str = "legacy_bf_01_boss",
    settlement_id: str = "settlement-001",
    occurred_at: str = "2026-08-25T10:01:00Z",
):
    intent = _intent(user_id=user_id, zone_key=zone_key, operation=operation)
    call = build_f010_battlefield_boss_selector_call(intent)
    server_selection = ServerBattlefieldBossSelection.from_f010_result(
        user_id=user_id,
        zone_key=zone_key,
        encounter_operation_id=operation,
        monster_id=monster_id,
        encounter_class=BATTLEFIELD_BOSS_CLASS,
    )
    binding = bind_battlefield_boss_selection(call, server_selection)
    evidence = ServerMonsterSettlementEvidence.from_server_settlement(
        user_id=user_id,
        zone_key=zone_key,
        monster_id=monster_id,
        encounter_class=BATTLEFIELD_BOSS_CLASS,
        encounter_operation_id=operation,
        settlement_id=settlement_id,
        hp_before=100,
        hp_after=0,
        committed=True,
        occurred_at=occurred_at,
    )
    return build_battlefield_boss_defeated_fact(binding, evidence)


def test_schema_is_additive_exact_and_rerunnable():
    conn = _db()
    try:
        assert validate_schema(conn)["valid"] is False
        first = upgrade(conn)
        assert first["valid"] is True
        assert first["table"] == TABLE_NAME
        assert first["dedupe_key"] == list(DEDUPE_KEY)
        second = upgrade(conn)
        assert second["valid"] is True
        columns = {
            row["name"]
            for row in conn.execute(f"PRAGMA table_info({TABLE_NAME})").fetchall()
        }
        forbidden = {
            "boss_ready",
            "lord_ready",
            "zone_clear",
            "zone_cleared",
            "stars",
            "next_zone",
            "next_zone_unlocked",
            "mastery_pct",
            "quest_completed",
            "correctness",
            "damage",
            "monster_hp",
            "monster_attack",
            "reward_amount",
        }
        assert columns.isdisjoint(forbidden)
        assert DEDUPE_KEY == ("user_id", "settlement_id")
    finally:
        downgrade_for_isolated_test(conn)
        conn.close()


def test_valid_fact_inserts_one_exact_projection_row():
    conn = _db()
    upgrade(conn)
    conn.commit()
    try:
        result = record_battlefield_boss_defeated_fact(
            conn,
            _fact(),
            created_at="2026-08-25T10:02:00Z",
        )
        assert result.recorded is True
        assert result.replayed is False
        assert result.zone_key == "zone_01"
        assert result.monster_id == "legacy_bf_01_boss"
        assert result.encounter_operation_id == "intent-001"
        row = conn.execute(f"SELECT * FROM {TABLE_NAME}").fetchone()
        assert row["user_id"] == 7
        assert row["settlement_id"] == "settlement-001"
        assert row["eligibility_reference"] == "world-eligibility-7-zone_01"
        assert row["intent_replay_fingerprint"]
        assert row["source_authority"] == "SERVER_MONSTER_SETTLEMENT"
        assert row["source_event_type"] == "MONSTER_DEFEATED"
        assert row["contract_version"] == "BATTLEFIELD_BOSS_DEFEATED_FACT_V1"
        assert conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0] == 1
    finally:
        conn.close()


def test_same_fact_replay_returns_replayed_and_does_not_add_a_row():
    conn = _db()
    upgrade(conn)
    conn.commit()
    try:
        first = _fact()
        recorded = record_battlefield_boss_defeated_fact(
            conn, first, created_at="2026-08-25T10:02:00Z"
        )
        replay = record_battlefield_boss_defeated_fact(
            conn,
            _fact(occurred_at="2026-08-25T11:01:00Z"),
            created_at="2026-08-25T11:02:00Z",
        )
        assert recorded.recorded is True
        assert replay.recorded is False
        assert replay.replayed is True
        assert replay.created_at == recorded.created_at
        assert conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0] == 1
    finally:
        conn.close()


def test_changed_authoritative_fact_with_same_composite_key_fails_closed():
    conn = _db()
    upgrade(conn)
    conn.commit()
    try:
        record_battlefield_boss_defeated_fact(conn, _fact())
        changed = _fact(monster_id="legacy_bf_02_boss")
        with pytest.raises(MilestoneProjectionConflict, match="changed authoritative"):
            record_battlefield_boss_defeated_fact(conn, changed)
        row = conn.execute(f"SELECT monster_id FROM {TABLE_NAME}").fetchone()
        assert row[0] == "legacy_bf_01_boss"
        assert conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0] == 1
    finally:
        conn.close()


def test_same_settlement_id_across_users_is_independent():
    conn = _db()
    upgrade(conn)
    conn.commit()
    try:
        first = record_battlefield_boss_defeated_fact(conn, _fact(user_id=7))
        second = record_battlefield_boss_defeated_fact(conn, _fact(user_id=8))
        assert first.recorded is True
        assert second.recorded is True
        assert conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0] == 2
    finally:
        conn.close()


def test_raw_mapping_and_missing_lineage_evidence_are_rejected():
    conn = _db()
    upgrade(conn)
    conn.commit()
    try:
        with pytest.raises(MilestoneProjectionValidationError, match="validated"):
            record_battlefield_boss_defeated_fact(conn, _fact().to_dict())

        fact = _fact()
        payload = fact.to_dict()
        payload["metadata"] = {}
        missing_evidence = BattlefieldBossDefeatedFact.from_mapping(payload)
        with pytest.raises(MilestoneProjectionValidationError, match="eligibility_reference"):
            record_battlefield_boss_defeated_fact(conn, missing_evidence)
    finally:
        conn.close()


def test_f014_precommit_path_cannot_reach_storage():
    conn = _db()
    upgrade(conn)
    conn.commit()
    try:
        intent = _intent()
        call = build_f010_battlefield_boss_selector_call(intent)
        selection = ServerBattlefieldBossSelection.from_f010_result(
            user_id=7,
            zone_key="zone_01",
            encounter_operation_id="intent-001",
            monster_id="legacy_bf_01_boss",
            encounter_class=BATTLEFIELD_BOSS_CLASS,
        )
        binding = bind_battlefield_boss_selection(call, selection)
        evidence = ServerMonsterSettlementEvidence.from_server_settlement(
            user_id=7,
            zone_key="zone_01",
            monster_id="legacy_bf_01_boss",
            encounter_class=BATTLEFIELD_BOSS_CLASS,
            encounter_operation_id="intent-001",
            settlement_id="precommit-001",
            hp_before=100,
            hp_after=0,
            committed=False,
            occurred_at="2026-08-25T10:01:00Z",
        )
        with pytest.raises(BattlefieldBossAdapterValidationError, match="settlement_not_committed"):
            build_battlefield_boss_defeated_fact(binding, evidence)
        assert conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0] == 0
    finally:
        conn.close()


def test_service_does_not_commit_and_caller_rollback_removes_row():
    conn = _db()
    upgrade(conn)
    conn.commit()
    try:
        class NoCommitConnection:
            _conn = conn

            def execute(self, sql, params=()):
                return conn.execute(sql, params)

            def commit(self):
                raise AssertionError("F015 service must not commit")

        wrapped = NoCommitConnection()
        record_battlefield_boss_defeated_fact(wrapped, _fact())
        assert conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0] == 1
        conn.rollback()
        assert conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0] == 0
    finally:
        conn.close()


def test_schema_missing_fails_without_auto_creating_table():
    conn = _db()
    try:
        with pytest.raises(MilestoneProjectionSchemaUnavailable):
            record_battlefield_boss_defeated_fact(conn, _fact())
        assert conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
            (TABLE_NAME,),
        ).fetchone()[0] == 0
    finally:
        conn.close()


def test_result_has_no_world_policy_fields_and_service_source_is_runtime_free():
    conn = _db()
    upgrade(conn)
    conn.commit()
    try:
        result = record_battlefield_boss_defeated_fact(conn, _fact())
        result_fields = set(asdict(result))
        forbidden = {
            "boss_ready",
            "lord_ready",
            "zone_clear",
            "stars",
            "next_zone",
            "next_zone_unlocked",
            "quest_completed",
        }
        assert result_fields.isdisjoint(forbidden)
    finally:
        conn.close()

    source = Path(__file__).resolve().parents[1].joinpath(
        "world_battlefield_boss_milestone.py"
    ).read_text(encoding="utf-8").lower()
    assert "import app" not in source
    assert "from app" not in source
    assert "flask" not in source
    assert "psycopg" not in source
    assert ".commit(" not in source
    assert "zone_cleared" not in source
    assert "lord_ready" not in source
