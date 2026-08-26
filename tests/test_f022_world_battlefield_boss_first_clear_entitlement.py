"""F022 Battlefield Boss first-clear entitlement authority tests."""

from __future__ import annotations

from dataclasses import asdict
import contextlib
import os
from pathlib import Path
import sqlite3
import threading
from urllib.parse import urlsplit

import pytest

os.environ.setdefault("SECRET_KEY", "f022-disposable-test-secret")

from migrations.world_battlefield_boss_first_clear_entitlement_v1 import (  # noqa: E402
    PRIMARY_KEY_COLUMNS,
    TABLE_NAME,
    downgrade_for_isolated_test,
    upgrade,
    validate_schema,
)
from world_battlefield_boss_first_clear_entitlement import (  # noqa: E402
    ALREADY_CLAIMED,
    CONFLICT,
    MAPPING_A,
    POLICY_VERSION,
    RECORDED,
    REPLAYED,
    BattlefieldBossFirstClearEntitlementResult,
    FirstClearEntitlementSchemaUnavailable,
    FirstClearEntitlementValidationError,
    claim_battlefield_boss_first_clear_entitlement,
    validate_mapping_a_against_catalog,
)
from world_monster_boss_adapter import (  # noqa: E402
    BATTLEFIELD_BOSS_CLASS,
    ServerBattlefieldBossSelection,
    ServerMonsterSettlementEvidence,
    bind_battlefield_boss_selection,
    build_battlefield_boss_defeated_fact,
    build_f010_battlefield_boss_selector_call,
)
from world_monster_boundary_contract import (  # noqa: E402
    BATTLEFIELD_BOSS_ENCOUNTER_INTENT_V1,
    BattlefieldBossEncounterIntent,
    WORLD_PROGRESSION_AUTHORITY,
)


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
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
            "metadata": {"policy_version": "world-boundary-v1"},
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


def _claim(
    conn: sqlite3.Connection,
    *,
    fact=None,
    user_id: int = 7,
    zone_key: str = "zone_01",
    settlement_id: str = "settlement-001",
    reward_item_id: str | None = None,
    reward_policy_version: str = POLICY_VERSION,
    claimed_at: str = "2026-08-27T10:02:00Z",
):
    current_fact = fact or _fact(
        user_id=user_id,
        zone_key=zone_key,
        settlement_id=settlement_id,
    )
    return claim_battlefield_boss_first_clear_entitlement(
        conn,
        fact=current_fact,
        user_id=user_id,
        zone_key=zone_key,
        source_settlement_id=settlement_id,
        reward_item_id=reward_item_id or MAPPING_A[zone_key],
        reward_policy_version=reward_policy_version,
        claimed_at=claimed_at,
    )


def test_mapping_a_is_exactly_the_owner_locked_v1_mapping():
    assert dict(MAPPING_A) == {
        "zone_01": "back_pack",
        "zone_02": "hat_cloth",
        "zone_03": "hat_bamboo",
        "zone_04": "robe_crane",
        "zone_05": "hat_onihorns",
        "zone_06": "robe_dragon",
        "zone_07": "acc_dragon_pendant",
        "zone_08": "back_cloak",
        "zone_09": "hat_dragon_horn",
        "zone_10": "hat_celestial_crown",
    }
    assert len(MAPPING_A) == 10


def test_mapping_a_validates_against_existing_canonical_cosmetic_catalog():
    import app as app_module

    appearance_defs = {item["id"]: item for item in app_module.APPEARANCE_DEFS}
    premium_ids = {
        item_id
        for item_id, item in appearance_defs.items()
        if item.get("premium_only")
    }
    shop_ids = {
        product["cosmetic_id"]
        for product in app_module.COSMETIC_COMMERCE_PRODUCTS
    }
    quest_exclusive_ids = {
        item_id
        for item_id, item in appearance_defs.items()
        if item.get("source_hint") in {"quest", "achievement"}
    }
    validate_mapping_a_against_catalog(
        presentation_registry=app_module.PURE_COSMETIC_PRESENTATION_REGISTRY,
        appearance_defs=appearance_defs,
        appearance_effects=app_module.APPEARANCE_EFFECTS,
        premium_item_ids=premium_ids,
        shop_item_ids=shop_ids,
        quest_exclusive_item_ids=quest_exclusive_ids,
    )


def test_schema_is_additive_rerunnable_and_policy_version_is_not_unique_key():
    conn = _db()
    try:
        assert validate_schema(conn)["valid"] is False
        first = upgrade(conn)
        assert first["valid"] is True
        assert upgrade(conn)["valid"] is True
        assert validate_schema(conn)["primary_key"] == list(PRIMARY_KEY_COLUMNS)
        columns = {
            row["name"]
            for row in conn.execute(f"PRAGMA table_info({TABLE_NAME})").fetchall()
        }
        assert "reward_policy_version" in columns
        forbidden = {
            "boss_ready",
            "lord_ready",
            "zone_clear",
            "zone_cleared",
            "stars",
            "star_granted",
            "next_zone",
            "next_zone_unlocked",
            "quest_completed",
            "mastery_pct",
            "correctness",
            "damage",
            "monster_hp",
            "monster_attack",
            "reward_amount",
        }
        assert columns.isdisjoint(forbidden)
    finally:
        downgrade_for_isolated_test(conn)
        conn.close()


def test_first_claim_records_one_entitlement():
    conn = _db()
    upgrade(conn)
    try:
        result = _claim(conn)
        assert isinstance(result, BattlefieldBossFirstClearEntitlementResult)
        assert result.status == RECORDED
        assert result.recorded is True
        assert result.replayed is False
        assert result.already_claimed is False
        assert result.reward_item_id == "back_pack"
        assert result.reward_policy_version == POLICY_VERSION
        assert conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0] == 1
        row = conn.execute(f"SELECT * FROM {TABLE_NAME}").fetchone()
        assert row["user_id"] == 7
        assert row["zone_key"] == "zone_01"
        assert row["source_settlement_id"] == "settlement-001"
        assert row["reward_item_id"] == "back_pack"
    finally:
        conn.close()


def test_same_settlement_replay_is_idempotent():
    conn = _db()
    upgrade(conn)
    try:
        first = _claim(conn)
        replay = _claim(conn, claimed_at="2026-08-27T11:02:00Z")
        assert first.status == RECORDED
        assert replay.status == REPLAYED
        assert replay.replayed is True
        assert replay.entitlement_settlement_id == first.entitlement_settlement_id
        assert replay.reward_item_id == first.reward_item_id
        assert conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0] == 1
    finally:
        conn.close()


def test_later_settlement_same_user_zone_is_already_claimed_not_conflict():
    conn = _db()
    upgrade(conn)
    try:
        _claim(conn)
        later = _claim(
            conn,
            settlement_id="settlement-002",
            fact=_fact(
                operation="boss-operation-002",
                settlement_id="settlement-002",
            ),
        )
        assert later.status == ALREADY_CLAIMED
        assert later.already_claimed is True
        assert later.replayed is False
        assert later.entitlement_settlement_id == "settlement-001"
        assert conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0] == 1
    finally:
        conn.close()


def test_same_settlement_changed_immutable_fact_is_conflict_and_unchanged():
    conn = _db()
    upgrade(conn)
    try:
        _claim(conn)
        changed = _claim(
            conn,
            fact=_fact(monster_id="legacy_bf_02_boss"),
            reward_item_id="back_pack",
        )
        assert changed.status == CONFLICT
        assert changed.recorded is False
        assert changed.replayed is False
        assert changed.already_claimed is False
        row = conn.execute(
            f"SELECT source_monster_id FROM {TABLE_NAME}"
        ).fetchone()
        assert row[0] == "legacy_bf_01_boss"
        assert conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0] == 1
    finally:
        conn.close()


def test_same_settlement_changed_reward_policy_is_conflict_not_regrant():
    conn = _db()
    upgrade(conn)
    try:
        _claim(conn)
        changed = _claim(
            conn,
            reward_item_id="back_flag",
            reward_policy_version="F022_FUTURE_MAPPING_V2",
        )
        assert changed.status == CONFLICT
        assert conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0] == 1
    finally:
        conn.close()


def test_future_mapping_change_cannot_create_second_entitlement():
    conn = _db()
    upgrade(conn)
    try:
        _claim(conn)
        result = _claim(
            conn,
            settlement_id="settlement-002",
            fact=_fact(
                operation="boss-operation-002",
                settlement_id="settlement-002",
            ),
            reward_item_id="back_flag",
            reward_policy_version="F022_FUTURE_MAPPING_V2",
        )
        assert result.status == ALREADY_CLAIMED
        assert conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0] == 1
    finally:
        conn.close()


def test_different_zones_are_independent():
    conn = _db()
    upgrade(conn)
    try:
        first = _claim(conn)
        second = _claim(
            conn,
            zone_key="zone_02",
            settlement_id="settlement-002",
            fact=_fact(
                zone_key="zone_02",
                operation="boss-operation-002",
                monster_id="legacy_bf_02_boss",
                settlement_id="settlement-002",
            ),
        )
        assert first.status == RECORDED
        assert second.status == RECORDED
        assert second.reward_item_id == "hat_cloth"
        assert conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0] == 2
    finally:
        conn.close()


def test_different_users_are_independent_even_with_same_settlement_id():
    conn = _db()
    upgrade(conn)
    try:
        first = _claim(conn)
        second = _claim(
            conn,
            user_id=8,
            fact=_fact(user_id=8),
        )
        assert first.status == RECORDED
        assert second.status == RECORDED
        assert conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0] == 2
    finally:
        conn.close()


def test_caller_owns_transaction_and_rollback_removes_entitlement():
    conn = _db()
    upgrade(conn)
    conn.commit()
    try:
        class NoCommitConnection:
            _conn = conn

            def execute(self, sql, params=()):
                return conn.execute(sql, params)

            def commit(self):
                raise AssertionError("F022 service must not commit")

            def rollback(self):
                raise AssertionError("F022 service must not rollback")

        claim_battlefield_boss_first_clear_entitlement(
            NoCommitConnection(),
            fact=_fact(),
            user_id=7,
            zone_key="zone_01",
            source_settlement_id="settlement-001",
            reward_item_id="back_pack",
        )
        assert conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0] == 1
        conn.rollback()
        assert conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0] == 0
    finally:
        conn.close()


def test_invalid_fact_and_reward_inputs_fail_closed_without_rows():
    conn = _db()
    upgrade(conn)
    try:
        with pytest.raises(FirstClearEntitlementValidationError, match="fact_type_required"):
            claim_battlefield_boss_first_clear_entitlement(
                conn,
                fact=_fact().to_dict(),
                user_id=7,
                zone_key="zone_01",
                source_settlement_id="settlement-001",
                reward_item_id="back_pack",
            )
        with pytest.raises(FirstClearEntitlementValidationError, match="reward_mapping_mismatch"):
            _claim(conn, reward_item_id="robe_dragon")
        assert conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0] == 0
    finally:
        conn.close()


def test_missing_schema_does_not_auto_create():
    conn = _db()
    try:
        with pytest.raises(FirstClearEntitlementSchemaUnavailable):
            _claim(conn)
        assert conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
            (TABLE_NAME,),
        ).fetchone()[0] == 0
    finally:
        conn.close()


def test_result_has_no_world_progression_or_ownership_decision_fields():
    conn = _db()
    upgrade(conn)
    try:
        result = _claim(conn)
        fields = set(asdict(result))
        forbidden = {
            "boss_ready",
            "lord_ready",
            "zone_clear",
            "zone_cleared",
            "star_granted",
            "stars",
            "next_zone",
            "next_zone_unlocked",
            "quest_completed",
            "compensation",
            "replacement_reward",
        }
        assert fields.isdisjoint(forbidden)
    finally:
        conn.close()

    source = Path(__file__).resolve().parents[1].joinpath(
        "world_battlefield_boss_first_clear_entitlement.py"
    ).read_text(encoding="utf-8").lower()
    assert "import app" not in source
    assert "from app" not in source
    assert "flask" not in source
    assert ".commit(" not in source
    assert ".rollback(" not in source


def _postgres_container_and_wrapper():
    disposable_url = os.environ.get("F022_POSTGRES_URL", "").strip()
    if disposable_url and os.environ.get("F022_POSTGRES_DISPOSABLE") == "1":
        database = (urlsplit(disposable_url).path or "").lstrip("/").lower()
        if "test" not in database and "f022" not in database:
            raise RuntimeError(
                "F022_POSTGRES_URL must name an explicitly disposable test/f022 database"
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


def _postgres_worker(
    database_url: str,
    *,
    user_id: int,
    operation: str,
    settlement_id: str,
    barrier: threading.Barrier,
    results: list[object],
):
    _container, wrapper = _postgres_container_and_wrapper()
    conn = wrapper(database_url)
    try:
        barrier.wait(timeout=20)
        result = _claim(
            conn,
            user_id=user_id,
            settlement_id=settlement_id,
            fact=_fact(
                user_id=user_id,
                operation=operation,
                settlement_id=settlement_id,
            ),
        )
        conn.commit()
        results.append(result)
    except Exception as error:  # assertions below expose worker failures
        conn.rollback()
        results.append(error)
    finally:
        conn.close()


def _prepare_postgres(database_url: str):
    _container, wrapper = _postgres_container_and_wrapper()
    conn = wrapper(database_url)
    status = upgrade(conn)
    assert status["valid"] is True
    conn.commit()
    return conn


def test_postgres_16_concurrent_first_claims_have_one_winner_and_replay_is_safe():
    _postgres_container, _postgres_wrapper = _postgres_container_and_wrapper()
    with _postgres_container() as database_url:
        conn = _prepare_postgres(database_url)
        try:
            version = conn.execute("SELECT version() AS version").fetchone()["version"]
            assert str(version).startswith("PostgreSQL 16.")
        finally:
            conn.close()

        # Different settlements for one user/Zone: unique DB authority picks
        # one winner and the other call reports ALREADY_CLAIMED.
        barrier = threading.Barrier(2)
        results: list[object] = []
        threads = [
            threading.Thread(
                target=_postgres_worker,
                args=(database_url,),
                kwargs={
                    "user_id": 101,
                    "operation": f"operation-{index}",
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
        assert sorted(result.status for result in results) == [ALREADY_CLAIMED, RECORDED]

        # Same settlement raced twice: one insert, one replay, one row.
        barrier = threading.Barrier(2)
        replay_results: list[object] = []
        threads = [
            threading.Thread(
                target=_postgres_worker,
                args=(database_url,),
                kwargs={
                    "user_id": 102,
                    "operation": "same-operation",
                    "settlement_id": "same-settlement",
                    "barrier": barrier,
                    "results": replay_results,
                },
            )
            for _ in range(2)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
            assert not thread.is_alive()
        assert not any(isinstance(result, Exception) for result in replay_results), replay_results
        assert sorted(result.status for result in replay_results) == [RECORDED, REPLAYED]

        inspect = _prepare_postgres(database_url)
        try:
            count = inspect.execute(
                f"SELECT COUNT(*) AS count FROM {TABLE_NAME}"
            ).fetchone()["count"]
            assert count == 2
        finally:
            inspect.rollback()
            downgrade_for_isolated_test(inspect)
            inspect.commit()
            inspect.close()


def test_postgres_16_concurrent_users_and_zones_are_independent():
    _postgres_container, _postgres_wrapper = _postgres_container_and_wrapper()
    with _postgres_container() as database_url:
        conn = _prepare_postgres(database_url)
        try:
            barrier = threading.Barrier(2)
            results: list[object] = []
            threads = [
                threading.Thread(
                    target=_postgres_worker,
                    args=(database_url,),
                    kwargs={
                        "user_id": user_id,
                        "operation": f"operation-{user_id}",
                        "settlement_id": "same-settlement",
                        "barrier": barrier,
                        "results": results,
                    },
                )
                for user_id in (201, 202)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=30)
                assert not thread.is_alive()
            assert not any(isinstance(result, Exception) for result in results), results
            assert all(result.status == RECORDED for result in results)
        finally:
            conn.rollback()
            downgrade_for_isolated_test(conn)
            conn.commit()
            conn.close()
