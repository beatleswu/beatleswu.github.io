"""F023 Battlefield Boss first-clear reward runtime integration tests."""

from __future__ import annotations

from dataclasses import asdict
import contextlib
import os
from pathlib import Path
import re
import sqlite3
import threading
from urllib.parse import urlsplit

import pytest

from migrations.domain_event_outbox_v1 import upgrade as upgrade_outbox
from migrations.world_battlefield_boss_first_clear_entitlement_v1 import (
    TABLE_NAME as ENTITLEMENT_TABLE,
    downgrade_for_isolated_test as downgrade_entitlement,
    upgrade as upgrade_entitlement,
)
from world_battlefield_boss_first_clear_entitlement import (
    MAPPING_A,
    POLICY_VERSION,
)
from world_battlefield_boss_reward_runtime import (
    CONFLICT,
    COSMETIC_GRANT_SOURCE,
    FIRST_CLEAR_ALREADY_OWNED_NO_OP,
    FIRST_CLEAR_NEW_COSMETIC,
    NOT_FIRST_CLEAR,
    BattlefieldBossFirstClearRewardResult,
    BattlefieldBossRewardValidationError,
    settle_battlefield_boss_first_clear_reward,
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


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    upgrade_outbox(conn)
    upgrade_entitlement(conn)
    conn.execute(
        """CREATE TABLE player_wardrobe (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               user_id INTEGER NOT NULL,
               item_id TEXT NOT NULL,
               obtained_at TEXT NOT NULL,
               source TEXT NOT NULL,
               UNIQUE(user_id, item_id)
           )"""
    )
    conn.commit()
    return conn


def _fact(
    *,
    user_id: int = 7,
    zone_key: str = "zone_01",
    operation: str = "boss-operation-001",
    monster_id: str = "legacy_bf_01_boss",
    settlement_id: str = "settlement-001",
):
    intent = BattlefieldBossEncounterIntent.from_mapping(
        {
            "contract_version": BATTLEFIELD_BOSS_ENCOUNTER_INTENT_V1,
            "user_id": user_id,
            "zone_key": zone_key,
            "intent_operation_id": operation,
            "encounter_class": BATTLEFIELD_BOSS_CLASS,
            "eligibility_authority": WORLD_PROGRESSION_AUTHORITY,
            "eligibility_reference": f"world-{user_id}-{zone_key}",
            "requested_at": "2026-08-27T10:00:00Z",
            "replayed": False,
            "metadata": {"source": "f023-test"},
        }
    )
    call = build_f010_battlefield_boss_selector_call(intent)
    selection = ServerBattlefieldBossSelection.from_f010_result(
        user_id=user_id,
        zone_key=zone_key,
        encounter_operation_id=operation,
        monster_id=monster_id,
        encounter_class=BATTLEFIELD_BOSS_CLASS,
    )
    binding = bind_battlefield_boss_selection(call, selection)
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
        occurred_at="2026-08-27T10:01:00Z",
    )
    return build_battlefield_boss_defeated_fact(binding, evidence)


def _wardrobe_writer(conn: sqlite3.Connection, user_id: int, calls=None):
    calls = calls if calls is not None else []

    def grant(item_id: str, source: str):
        calls.append((item_id, source))
        inserted = conn.execute(
            "INSERT INTO player_wardrobe"
            "(user_id,item_id,obtained_at,source) VALUES(?,?,?,?) "
            "ON CONFLICT(user_id,item_id) DO NOTHING",
            (user_id, item_id, "2026-08-27T10:02:00Z", source),
        )
        if int(getattr(inserted, "rowcount", 0)) != 1:
            return {"new": False, "item_id": item_id, "payload": None}
        row = conn.execute(
            "SELECT id FROM player_wardrobe WHERE user_id=? AND item_id=?",
            (user_id, item_id),
        ).fetchone()
        return {
            "new": True,
            "item_id": item_id,
            "grant_id": f"player_wardrobe:{row['id']}",
            "payload": {"item_id": item_id},
        }

    return grant


def _award(conn, *, fact=None, user_id=7, zone_key="zone_01", calls=None):
    current_fact = fact or _fact(user_id=user_id, zone_key=zone_key)
    return settle_battlefield_boss_first_clear_reward(
        conn,
        fact=current_fact,
        user_id=user_id,
        zone_key=zone_key,
        grant_wardrobe_item=_wardrobe_writer(conn, user_id, calls),
    )


def test_mapping_a_first_clear_creates_entitlement_wardrobe_and_d5a_lineage():
    conn = _db()
    try:
        result = _award(conn)
        assert result.status == FIRST_CLEAR_NEW_COSMETIC
        assert result.reward_policy_version == POLICY_VERSION
        assert result.mapped_cosmetic_id == MAPPING_A["zone_01"] == "back_pack"
        assert result.first_clear_entitlement_consumed is True
        assert result.cosmetic_newly_owned is True
        assert result.already_owned_no_op is False
        assert result.acquisition_lineage_id
        conn.commit()
        assert conn.execute(
            f"SELECT COUNT(*) FROM {ENTITLEMENT_TABLE}"
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM player_wardrobe WHERE user_id=7 AND item_id='back_pack'"
        ).fetchone()[0] == 1
        event = conn.execute(
            "SELECT event_type,source_event_id,payload FROM domain_event_outbox "
            "WHERE event_type='ITEM_ACQUISITION'"
        ).fetchone()
        assert event[0] == "ITEM_ACQUISITION"
        assert event[1] == "settlement-001"
        assert '"acquisition_source":"BATTLEFIELD_BOSS_FIRST_CLEAR"' in event[2]
    finally:
        downgrade_entitlement(conn)
        conn.close()


def test_first_clear_already_owned_is_consumed_noop_without_compensation():
    conn = _db()
    try:
        conn.execute(
            "INSERT INTO player_wardrobe(user_id,item_id,obtained_at,source) "
            "VALUES(7,'back_pack','before','shop')"
        )
        calls = []
        result = _award(conn, calls=calls)
        assert result.status == FIRST_CLEAR_ALREADY_OWNED_NO_OP
        assert result.first_clear_entitlement_consumed is True
        assert result.cosmetic_newly_owned is False
        assert result.already_owned_no_op is True
        assert result.acquisition_lineage_id is None
        assert calls == [("back_pack", COSMETIC_GRANT_SOURCE)]
        assert conn.execute(
            "SELECT COUNT(*) FROM player_wardrobe WHERE user_id=7 AND item_id='back_pack'"
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM domain_event_outbox WHERE event_type='ITEM_ACQUISITION'"
        ).fetchone()[0] == 0
    finally:
        downgrade_entitlement(conn)
        conn.close()


def test_same_settlement_replay_is_not_a_new_entitlement_or_cosmetic_grant():
    conn = _db()
    try:
        calls = []
        first = _award(conn, calls=calls)
        conn.commit()
        replay = _award(conn, calls=calls)
        assert first.status == FIRST_CLEAR_NEW_COSMETIC
        assert replay.status == NOT_FIRST_CLEAR
        assert replay.entitlement_status == "REPLAYED"
        assert replay.entitlement_replayed is True
        assert replay.first_clear_entitlement_consumed is False
        assert replay.cosmetic_newly_owned is False
        assert calls == [("back_pack", COSMETIC_GRANT_SOURCE)]
        assert conn.execute(
            f"SELECT COUNT(*) FROM {ENTITLEMENT_TABLE}"
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM domain_event_outbox WHERE event_type='ITEM_ACQUISITION'"
        ).fetchone()[0] == 1
    finally:
        downgrade_entitlement(conn)
        conn.close()


def test_later_settlement_same_zone_is_not_a_new_entitlement_or_grant():
    conn = _db()
    try:
        calls = []
        _award(conn, calls=calls)
        conn.commit()
        later = _award(
            conn,
            calls=calls,
            fact=_fact(
                operation="boss-operation-002",
                settlement_id="settlement-002",
            ),
        )
        assert later.status == NOT_FIRST_CLEAR
        assert later.entitlement_status == "ALREADY_CLAIMED"
        assert later.requested_settlement_id == "settlement-002"
        assert later.entitlement_settlement_id == "settlement-001"
        assert calls == [("back_pack", COSMETIC_GRANT_SOURCE)]
    finally:
        downgrade_entitlement(conn)
        conn.close()


def test_conflicting_authoritative_fact_fails_closed_without_grant():
    conn = _db()
    try:
        calls = []
        _award(conn, calls=calls)
        conn.commit()
        conflict = _award(
            conn,
            calls=calls,
            fact=_fact(monster_id="legacy_bf_02_boss"),
        )
        assert conflict.status == CONFLICT
        assert conflict.entitlement_status == CONFLICT
        assert calls == [("back_pack", COSMETIC_GRANT_SOURCE)]
        assert conn.execute(
            f"SELECT source_monster_id FROM {ENTITLEMENT_TABLE}"
        ).fetchone()[0] == "legacy_bf_01_boss"
    finally:
        downgrade_entitlement(conn)
        conn.close()


def test_different_zones_and_users_are_independent():
    conn = _db()
    try:
        first = _award(conn)
        second = _award(
            conn,
            user_id=8,
            zone_key="zone_01",
            fact=_fact(user_id=8),
        )
        third = _award(
            conn,
            zone_key="zone_02",
            fact=_fact(
                zone_key="zone_02",
                operation="boss-operation-002",
                monster_id="legacy_bf_02_boss",
                settlement_id="settlement-002",
            ),
        )
        assert [first.status, second.status, third.status] == [
            FIRST_CLEAR_NEW_COSMETIC,
            FIRST_CLEAR_NEW_COSMETIC,
            FIRST_CLEAR_NEW_COSMETIC,
        ]
        assert second.mapped_cosmetic_id == "back_pack"
        assert third.mapped_cosmetic_id == "hat_cloth"
        assert conn.execute(
            f"SELECT COUNT(*) FROM {ENTITLEMENT_TABLE}"
        ).fetchone()[0] == 3
        assert conn.execute(
            "SELECT COUNT(*) FROM player_wardrobe"
        ).fetchone()[0] == 3
    finally:
        downgrade_entitlement(conn)
        conn.close()


def test_caller_rollback_removes_entitlement_wardrobe_and_lineage_together():
    conn = _db()
    try:
        def failing_writer(item_id, source):
            conn.execute(
                "INSERT INTO player_wardrobe(user_id,item_id,obtained_at,source) "
                "VALUES(7,?,?,?)",
                (item_id, "now", source),
            )
            raise RuntimeError("simulated wardrobe failure")

        with pytest.raises(RuntimeError, match="simulated wardrobe failure"):
            settle_battlefield_boss_first_clear_reward(
                conn,
                fact=_fact(),
                user_id=7,
                zone_key="zone_01",
                grant_wardrobe_item=failing_writer,
            )
        conn.rollback()
        assert conn.execute(
            f"SELECT COUNT(*) FROM {ENTITLEMENT_TABLE}"
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM player_wardrobe"
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM domain_event_outbox"
        ).fetchone()[0] == 0
    finally:
        downgrade_entitlement(conn)
        conn.close()


def test_lineage_failure_requires_caller_rollback_after_ownership_mutation():
    conn = _db()
    try:
        def grant_then_bad_lineage(item_id, source):
            return _wardrobe_writer(conn, 7)(item_id, source)

        original_append = __import__(
            "world_battlefield_boss_reward_runtime",
            fromlist=["append_event"],
        ).append_event
        runtime = __import__(
            "world_battlefield_boss_reward_runtime",
            fromlist=["append_event"],
        )
        runtime.append_event = lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("simulated lineage failure")
        )
        try:
            with pytest.raises(RuntimeError, match="simulated lineage failure"):
                settle_battlefield_boss_first_clear_reward(
                    conn,
                    fact=_fact(),
                    user_id=7,
                    zone_key="zone_01",
                    grant_wardrobe_item=grant_then_bad_lineage,
                )
        finally:
            runtime.append_event = original_append
        conn.rollback()
        assert conn.execute(
            f"SELECT COUNT(*) FROM {ENTITLEMENT_TABLE}"
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM player_wardrobe"
        ).fetchone()[0] == 0
    finally:
        downgrade_entitlement(conn)
        conn.close()


def test_service_is_caller_owned_and_result_contains_no_world_decisions():
    conn = _db()
    conn.commit()
    try:
        class TransactionSpy:
            _conn = conn

            def execute(self, sql, params=()):
                return conn.execute(sql, params)

            def commit(self):
                raise AssertionError("F023 must not commit")

            def rollback(self):
                raise AssertionError("F023 must not rollback")

        result = settle_battlefield_boss_first_clear_reward(
            TransactionSpy(),
            fact=_fact(),
            user_id=7,
            zone_key="zone_01",
            grant_wardrobe_item=_wardrobe_writer(conn, 7),
        )
        assert result.status == FIRST_CLEAR_NEW_COSMETIC
        assert set(asdict(result)).isdisjoint(
            {
                "boss_ready",
                "lord_ready",
                "zone_clear",
                "zone_cleared",
                "star_granted",
                "stars",
                "next_zone",
                "next_zone_unlocked",
                "quest_completed",
            }
        )
        conn.rollback()
    finally:
        downgrade_entitlement(conn)
        conn.close()


def test_raw_or_lord_like_inputs_cannot_reach_reward_runtime():
    conn = _db()
    try:
        with pytest.raises(BattlefieldBossRewardValidationError, match="fact_type_required"):
            settle_battlefield_boss_first_clear_reward(
                conn,
                fact={"encounter_class": "LORD"},
                user_id=7,
                zone_key="zone_01",
                grant_wardrobe_item=_wardrobe_writer(conn, 7),
            )
        assert conn.execute(
            f"SELECT COUNT(*) FROM {ENTITLEMENT_TABLE}"
        ).fetchone()[0] == 0
    finally:
        downgrade_entitlement(conn)
        conn.close()


def test_runtime_module_does_not_import_app_or_modify_f022_schema():
    source = Path(__file__).resolve().parents[1].joinpath(
        "world_battlefield_boss_reward_runtime.py"
    ).read_text(encoding="utf-8").lower()
    assert re.search(r"^\s*import\s+app\b", source, re.MULTILINE) is None
    assert re.search(r"^\s*from\s+app\s+import\b", source, re.MULTILINE) is None
    assert "flask" not in source
    assert ".commit(" not in source
    assert ".rollback(" not in source
    assert "zone_clear" not in source
    assert "lord_ready" not in source
    assert "next_zone" not in source


def _postgres_container_and_wrapper():
    disposable_url = os.environ.get("F023_POSTGRES_URL", "").strip()
    if disposable_url and os.environ.get("F023_POSTGRES_DISPOSABLE") == "1":
        database = (urlsplit(disposable_url).path or "").lstrip("/").lower()
        if "test" not in database and "f023" not in database:
            raise RuntimeError(
                "F023_POSTGRES_URL must name an explicitly disposable test/f023 database"
            )
        try:
            from test_map_battle_persistence import _postgres_wrapper
        except ImportError:
            from tests.test_map_battle_persistence import _postgres_wrapper

        @contextlib.contextmanager
        def existing_disposable_container():
            yield disposable_url

        return existing_disposable_container, _postgres_wrapper
    try:
        from test_map_battle_persistence import _postgres_container, _postgres_wrapper
    except ImportError:
        from tests.test_map_battle_persistence import _postgres_container, _postgres_wrapper
    return _postgres_container, _postgres_wrapper


def _postgres_prepare(database_url):
    _container, wrapper = _postgres_container_and_wrapper()
    conn = wrapper(database_url)
    upgrade_outbox(conn)
    upgrade_entitlement(conn)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS player_wardrobe (
               id SERIAL PRIMARY KEY,
               user_id INTEGER NOT NULL,
               item_id TEXT NOT NULL,
               obtained_at TEXT NOT NULL,
               source TEXT NOT NULL,
               UNIQUE(user_id, item_id)
           )"""
    )
    conn.commit()
    return conn


def _postgres_worker(
    database_url,
    *,
    user_id,
    operation,
    settlement_id,
    barrier,
    results,
):
    _container, wrapper = _postgres_container_and_wrapper()
    conn = wrapper(database_url)
    try:
        barrier.wait(timeout=20)
        result = settle_battlefield_boss_first_clear_reward(
            conn,
            fact=_fact(
                user_id=user_id,
                operation=operation,
                settlement_id=settlement_id,
            ),
            user_id=user_id,
            zone_key="zone_01",
            grant_wardrobe_item=_wardrobe_writer(conn, user_id),
        )
        conn.commit()
        results.append(result)
    except Exception as error:
        conn.rollback()
        results.append(error)
    finally:
        conn.close()


def test_postgres_16_concurrent_same_zone_has_one_reward_winner():
    _postgres_container, _postgres_wrapper = _postgres_container_and_wrapper()
    with _postgres_container() as database_url:
        setup = _postgres_prepare(database_url)
        try:
            version = setup.execute("SELECT version() AS version").fetchone()["version"]
            assert str(version).startswith("PostgreSQL 16.")
        finally:
            setup.close()

        barrier = threading.Barrier(2)
        results: list[object] = []
        threads = [
            threading.Thread(
                target=_postgres_worker,
                args=(database_url,),
                kwargs={
                    "user_id": 501,
                    "operation": f"boss-operation-{index}",
                    "settlement_id": f"settlement-{index}",
                    "barrier": barrier,
                    "results": results,
                },
            )
            for index in (1, 2)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
            assert not thread.is_alive()
        assert not any(isinstance(result, Exception) for result in results), results
        assert sorted(result.status for result in results) == [
            "ALREADY_CLAIMED",
            "FIRST_CLEAR_NEW_COSMETIC",
        ]

        inspect = _postgres_prepare(database_url)
        try:
            assert inspect.execute(
                f"SELECT COUNT(*) AS count FROM {ENTITLEMENT_TABLE}"
            ).fetchone()["count"] == 1
            assert inspect.execute(
                "SELECT COUNT(*) AS count FROM player_wardrobe"
            ).fetchone()["count"] == 1
            assert inspect.execute(
                "SELECT COUNT(*) AS count FROM domain_event_outbox "
                "WHERE event_type='ITEM_ACQUISITION'"
            ).fetchone()["count"] == 1
        finally:
            inspect.rollback()
            downgrade_entitlement(inspect)
            inspect.execute("DROP TABLE IF EXISTS player_wardrobe")
            inspect.commit()
            inspect.close()
