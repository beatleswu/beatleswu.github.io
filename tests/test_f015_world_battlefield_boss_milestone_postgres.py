"""Optional F015 acceptance against an explicitly disposable PostgreSQL 16.14."""

from __future__ import annotations

import os
from urllib.parse import urlsplit

import pytest

from migrations.world_battlefield_boss_milestone_v1 import (
    TABLE_NAME,
    downgrade_for_isolated_test,
    upgrade,
    validate_schema,
)
from world_battlefield_boss_milestone import (
    MilestoneProjectionConflict,
    record_battlefield_boss_defeated_fact,
)
from world_monster_boss_adapter import (
    BATTLEFIELD_BOSS_CLASS,
    ServerBattlefieldBossSelection,
    ServerMonsterSettlementEvidence,
    bind_battlefield_boss_selection,
    build_battlefield_boss_defeated_fact,
    build_f010_battlefield_boss_selector_call,
)
from world_monster_boundary_contract import (
    BATTLEFIELD_BOSS_ENCOUNTER_INTENT_V1,
    BattlefieldBossEncounterIntent,
    WORLD_PROGRESSION_AUTHORITY,
)


def _url() -> str:
    url = os.environ.get("F015_WORLD_BOSS_POSTGRES_URL", "").strip()
    if not url or os.environ.get("F015_WORLD_BOSS_POSTGRES_DISPOSABLE") != "1":
        pytest.skip("requires explicitly marked disposable PostgreSQL")
    database = (urlsplit(url).path or "").lstrip("/").lower()
    if "test" not in database and "f015" not in database:
        pytest.fail("refusing PostgreSQL URL without a disposable test/f015 database")
    return url


def _open(url: str):
    import psycopg2
    from psycopg2.extras import DictCursor

    from db import PostgresConnectionWrapper

    raw = psycopg2.connect(url)
    raw.cursor_factory = DictCursor
    return PostgresConnectionWrapper(raw)


def _fact(*, user_id: int = 7, monster_id: str = "legacy_bf_01_boss"):
    intent = BattlefieldBossEncounterIntent.from_mapping(
        {
            "contract_version": BATTLEFIELD_BOSS_ENCOUNTER_INTENT_V1,
            "user_id": user_id,
            "zone_key": "zone_01",
            "intent_operation_id": "pg-intent-001",
            "encounter_class": BATTLEFIELD_BOSS_CLASS,
            "eligibility_authority": WORLD_PROGRESSION_AUTHORITY,
            "eligibility_reference": f"pg-world-{user_id}",
            "requested_at": "2026-08-25T10:00:00Z",
            "replayed": False,
            "metadata": {},
        }
    )
    call = build_f010_battlefield_boss_selector_call(intent)
    selection = ServerBattlefieldBossSelection.from_f010_result(
        user_id=user_id,
        zone_key="zone_01",
        encounter_operation_id="pg-intent-001",
        monster_id=monster_id,
        encounter_class=BATTLEFIELD_BOSS_CLASS,
    )
    binding = bind_battlefield_boss_selection(call, selection)
    evidence = ServerMonsterSettlementEvidence.from_server_settlement(
        user_id=user_id,
        zone_key="zone_01",
        monster_id=monster_id,
        encounter_class=BATTLEFIELD_BOSS_CLASS,
        encounter_operation_id="pg-intent-001",
        settlement_id="pg-settlement-001",
        hp_before=100,
        hp_after=0,
        committed=True,
        occurred_at="2026-08-25T10:01:00Z",
    )
    return build_battlefield_boss_defeated_fact(binding, evidence)


def _reset(url: str):
    conn = _open(url)
    downgrade_for_isolated_test(conn)
    conn.commit()
    status = upgrade(conn)
    conn.commit()
    assert status["valid"] is True
    return conn


def test_postgres_16_14_migration_replay_conflict_and_cross_user_isolation():
    conn = _reset(_url())
    try:
        version = conn.execute("SELECT version() AS version").fetchone()["version"]
        assert str(version).startswith("PostgreSQL 16.14")
        assert validate_schema(conn)["valid"] is True
        assert upgrade(conn)["valid"] is True
        conn.commit()

        first = record_battlefield_boss_defeated_fact(
            conn, _fact(), created_at="2026-08-25T10:02:00Z"
        )
        replay = record_battlefield_boss_defeated_fact(
            conn, _fact(), created_at="2026-08-25T11:02:00Z"
        )
        other_user = record_battlefield_boss_defeated_fact(
            conn, _fact(user_id=8), created_at="2026-08-25T10:03:00Z"
        )
        assert first.recorded is True
        assert replay.replayed is True
        assert other_user.recorded is True
        assert conn.execute(f"SELECT COUNT(*) AS n FROM {TABLE_NAME}").fetchone()["n"] == 2
        conn.commit()

        with pytest.raises(MilestoneProjectionConflict):
            record_battlefield_boss_defeated_fact(
                conn,
                _fact(monster_id="legacy_bf_02_boss"),
                created_at="2026-08-25T12:00:00Z",
            )
        conn.rollback()
        assert conn.execute(f"SELECT COUNT(*) AS n FROM {TABLE_NAME}").fetchone()["n"] == 2
    finally:
        conn.rollback()
        downgrade_for_isolated_test(conn)
        conn.commit()
        conn.close()
