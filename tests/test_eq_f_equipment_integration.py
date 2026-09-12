"""Focused EQ-F integration proof for the additive Equipment release candidate."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import sqlite3

import pytest

os.environ.setdefault("SECRET_KEY", "eq-f-integration-disposable-test-secret")

from equipment_first_clear_reward_service import (  # noqa: E402
    ALREADY_OWNED,
    GRANTED,
    NO_REWARD,
    EquipmentFirstClearRewardError,
    EquipmentFirstClearSettlement,
    backfill_cleared_equipment,
    grant_equipment_first_clear_reward,
)
from equipment_loadout_service import (  # noqa: E402
    equip_owned_item,
    unequip_owned_item,
)
from equipment_ownership_service import grant_equipment_ownership  # noqa: E402
from equipment_portfolio_registry import (  # noqa: E402
    EQ_F_FUNCTIONAL_EQUIPMENT_ART,
    EQ_F_HANDHELD_WEAPON_IDS,
    EQ_F_NEW_EQUIPMENT_DEFS,
    EQ_F_SHOP_EQUIPMENT_IDS,
    EQ_F_ZONE_EQUIPMENT_BY_ZONE,
    validate_eq_f_portfolio,
)
from equipment_shop_eq_f_admission import (  # noqa: E402
    EqFShopPriceAuthorityPending,
    admission_status,
    build_price_authorized_offer_facts,
)
from migrations.equipment_canonical_slot_v1 import upgrade as upgrade_b033  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFINITIONS = tuple(EQ_F_NEW_EQUIPMENT_DEFS)


def _new_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE adventure_boss_progress (
            user_id INTEGER NOT NULL,
            zone_key TEXT NOT NULL,
            cleared INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, zone_key)
        );
        CREATE TABLE player_inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            equip_id TEXT NOT NULL,
            equipped INTEGER NOT NULL DEFAULT 0,
            obtained_at TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'test',
            UNIQUE(user_id, equip_id)
        );
        CREATE TABLE active_effects (
            user_id INTEGER NOT NULL,
            effect_key TEXT NOT NULL
        );
        """
    )
    return conn


def _settlement(user_id: int, zone_key: str, *, first_clear: bool = True,
                replay: bool = False, passed: bool = True) -> EquipmentFirstClearSettlement:
    return EquipmentFirstClearSettlement.from_authoritative_attempt(
        user_id=user_id,
        zone_key=zone_key,
        passed=passed,
        attempt_result={
            "operation_id": f"adventure:first_clear:{user_id}:{zone_key}",
            "is_first_clear": first_clear,
            "is_replay": replay,
        },
    )


def test_locked_portfolio_and_assets_are_complete_and_data_driven():
    validate_eq_f_portfolio(DEFINITIONS)
    assert len(DEFINITIONS) == 16
    assert Counter(item["slot"] for item in DEFINITIONS) == {
        "weapon": 5,
        "armor": 6,
        "accessory": 5,
    }
    assert set(EQ_F_ZONE_EQUIPMENT_BY_ZONE.values()).isdisjoint(
        EQ_F_SHOP_EQUIPMENT_IDS
    )
    assert len(EQ_F_ZONE_EQUIPMENT_BY_ZONE) == 10
    assert len(EQ_F_HANDHELD_WEAPON_IDS) == 5

    wearable_registry = json.loads(
        (REPO_ROOT / "assets/hero/equipment/wearables/wearable_registry.json")
        .read_text(encoding="utf-8")
    )
    handheld_registry = json.loads(
        (
            REPO_ROOT
            / "assets/hero/equipment/wearables/handheld/handheld_runtime_registry.json"
        ).read_text(encoding="utf-8")
    )
    for definition in DEFINITIONS:
        item_id = str(definition["id"])
        art = EQ_F_FUNCTIONAL_EQUIPMENT_ART[item_id]
        wearable = wearable_registry["equipment"][item_id]
        assert (REPO_ROOT / art["icon_path"].lstrip("/")).is_file()
        asset_path = REPO_ROOT / art["asset_path"].lstrip("/")
        assert asset_path.is_file()
        assert wearable["asset"] == art["asset_path"]
        assert wearable["production_status"] == "EQ_E_ACCEPTED_ASSET"
        if item_id in EQ_F_HANDHELD_WEAPON_IDS:
            runtime = handheld_registry["weapons"][item_id]
            assert runtime["runtime_supported"] is True
            assert runtime["weapon_only"] is True
            assert runtime["asset"] == art["asset_path"]
            assert hashlib.sha256(asset_path.read_bytes()).hexdigest() == runtime[
                "source_sha256"
            ]


def test_first_clear_grants_all_ten_items_unequipped_and_retries_converge():
    conn = _new_connection()
    try:
        uid = 7001
        for zone_key in EQ_F_ZONE_EQUIPMENT_BY_ZONE:
            conn.execute(
                "INSERT INTO adventure_boss_progress(user_id,zone_key,cleared) VALUES(?,?,1)",
                (uid, zone_key),
            )

        results = [
            grant_equipment_first_clear_reward(
                conn,
                _settlement(uid, zone_key),
                equipment_defs=DEFINITIONS,
            )
            for zone_key in EQ_F_ZONE_EQUIPMENT_BY_ZONE
        ]
        assert [result.status for result in results] == [GRANTED] * 10
        assert {
            row["equip_id"]
            for row in conn.execute("SELECT equip_id FROM player_inventory")
        } == set(EQ_F_ZONE_EQUIPMENT_BY_ZONE.values())
        assert conn.execute(
            "SELECT COUNT(*) FROM player_inventory WHERE equipped=1"
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM active_effects"
        ).fetchone()[0] == 0
        assert {
            row["source"]
            for row in conn.execute("SELECT source FROM player_inventory")
        } == {"adventure_first_clear"}

        retry = grant_equipment_first_clear_reward(
            conn,
            _settlement(uid, "k26_30"),
            equipment_defs=DEFINITIONS,
        )
        assert retry.status == ALREADY_OWNED
        assert conn.execute(
            "SELECT COUNT(*) FROM player_inventory WHERE user_id=? AND equip_id=?",
            (uid, EQ_F_ZONE_EQUIPMENT_BY_ZONE["k26_30"]),
        ).fetchone()[0] == 1
    finally:
        conn.close()


def test_all_sixteen_items_use_existing_ownership_and_loadout_authorities():
    conn = _new_connection()
    try:
        uid = 7006
        for index, definition in enumerate(DEFINITIONS, start=1):
            result = grant_equipment_ownership(
                conn,
                uid + index,
                str(definition["id"]),
                "coin_shop",
                equipment_defs=DEFINITIONS,
            )
            assert result.equipped is False
        assert conn.execute(
            "SELECT COUNT(*) FROM player_inventory"
        ).fetchone()[0] == 16
        upgrade_b033(conn, equipment_defs=DEFINITIONS)
        conn.commit()

        weapon_id = "starglass_needle"
        conn.execute(
            "INSERT INTO player_inventory(user_id,equip_id,equipped,obtained_at,source) "
            "VALUES(?,?,?,?,?)",
            (uid, weapon_id, 0, "now", "coin_shop"),
        )
        equipped = equip_owned_item(
            conn, uid, weapon_id, equipment_defs=DEFINITIONS
        )
        assert equipped["canonical_slot"] == "weapon"
        assert conn.execute(
            "SELECT equipped FROM player_inventory WHERE user_id=? AND equip_id=?",
            (uid, weapon_id),
        ).fetchone()[0] == 1
        unequipped = unequip_owned_item(
            conn, uid, weapon_id, equipment_defs=DEFINITIONS
        )
        assert unequipped["canonical_slot"] == "weapon"
        assert conn.execute(
            "SELECT equipped FROM player_inventory WHERE user_id=? AND equip_id=?",
            (uid, weapon_id),
        ).fetchone()[0] == 0
    finally:
        conn.close()


def test_first_clear_is_fail_closed_for_uncleared_and_replay_attempts():
    conn = _new_connection()
    try:
        uid = 7002
        conn.execute(
            "INSERT INTO adventure_boss_progress(user_id,zone_key,cleared) VALUES(?,?,0)",
            (uid, "k1_5"),
        )
        with pytest.raises(EquipmentFirstClearRewardError) as error:
            grant_equipment_first_clear_reward(
                conn,
                _settlement(uid, "k1_5"),
                equipment_defs=DEFINITIONS,
            )
        assert error.value.code == "CLEAR_NOT_CONFIRMED"
        replay = grant_equipment_first_clear_reward(
            conn,
            _settlement(uid, "k1_5", first_clear=False, replay=True),
            equipment_defs=DEFINITIONS,
        )
        assert replay.status == NO_REWARD
        assert conn.execute(
            "SELECT COUNT(*) FROM player_inventory"
        ).fetchone()[0] == 0
    finally:
        conn.close()


def test_historical_backfill_uses_authoritative_clear_rows_and_does_not_duplicate():
    conn = _new_connection()
    try:
        uid = 7003
        conn.executemany(
            "INSERT INTO adventure_boss_progress(user_id,zone_key,cleared) VALUES(?,?,?)",
            [
                (uid, "k1_5", 1),
                (uid, "d5_6", 1),
                (uid, "not-a-canonical-zone", 1),
            ],
        )
        conn.execute(
            "INSERT INTO player_inventory(user_id,equip_id,equipped,obtained_at,source) "
            "VALUES(?,?,?,?,?)",
            (uid, EQ_F_ZONE_EQUIPMENT_BY_ZONE["k1_5"], 0, "before", "admin"),
        )
        results = backfill_cleared_equipment(
            conn, uid, equipment_defs=DEFINITIONS
        )
        assert [(result.zone_key, result.status) for result in results] == [
            ("d5_6", GRANTED),
            ("k1_5", ALREADY_OWNED),
        ]
        assert conn.execute(
            "SELECT COUNT(*) FROM player_inventory WHERE user_id=?", (uid,)
        ).fetchone()[0] == 2
    finally:
        conn.close()


class _TransactionSpy:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self.commit_calls = 0
        self.rollback_calls = 0

    def execute(self, statement, parameters=()):
        return self._conn.execute(statement, parameters)

    def commit(self):
        self.commit_calls += 1
        self._conn.commit()

    def rollback(self):
        self.rollback_calls += 1
        self._conn.rollback()


def test_first_clear_service_does_not_create_an_inner_transaction():
    conn = _new_connection()
    try:
        uid = 7004
        conn.execute(
            "INSERT INTO adventure_boss_progress(user_id,zone_key,cleared) VALUES(?,?,1)",
            (uid, "k21_25"),
        )
        spy = _TransactionSpy(conn)
        result = grant_equipment_first_clear_reward(
            spy,
            _settlement(uid, "k21_25"),
            equipment_defs=DEFINITIONS,
        )
        assert result.status == GRANTED
        assert spy.commit_calls == 0
        assert spy.rollback_calls == 0
    finally:
        conn.close()


def test_price_gate_is_inactive_until_exact_c045_facts_are_supplied():
    status = admission_status()
    assert status["active"] is False
    assert status["offer_count"] == 0
    assert status["item_ids"] == list(EQ_F_SHOP_EQUIPMENT_IDS)
    with pytest.raises(EqFShopPriceAuthorityPending):
        build_price_authorized_offer_facts(DEFINITIONS)

    prices = {
        item_id: 100 + index
        for index, item_id in enumerate(EQ_F_SHOP_EQUIPMENT_IDS)
    }
    references = {
        item_id: f"test-c045:{item_id}"
        for item_id in EQ_F_SHOP_EQUIPMENT_IDS
    }
    facts = build_price_authorized_offer_facts(
        DEFINITIONS,
        accepted_prices=prices,
        price_references=references,
    )
    assert len(facts) == 6
    assert [fact.item_id for fact in facts] == list(EQ_F_SHOP_EQUIPMENT_IDS)
    assert {fact.destination for fact in facts} == {"player_inventory"}
    assert {fact.duplicate_policy for fact in facts} == {"REJECT_IF_OWNED"}
    assert all(fact.metadata["auto_equip"] is False for fact in facts)


def test_new_equipment_changes_server_stat_then_unequip_restores_baseline():
    import app as app_module

    conn = _new_connection()
    try:
        uid = 7005
        baseline = app_module._get_authoritative_combat_stats(conn, uid)
        conn.execute(
            "INSERT INTO player_inventory(user_id,equip_id,equipped,obtained_at,source) "
            "VALUES(?,?,?,?,?)",
            (uid, "bamboo_shadow_blade", 1, "now", "adventure_first_clear"),
        )
        equipped = app_module._get_authoritative_combat_stats(conn, uid)
        assert baseline["attack_bonus"] == 0.0
        assert equipped["attack_bonus"] == pytest.approx(0.06)
        assert equipped["damage_reduction"] == 0.0
        conn.execute(
            "UPDATE player_inventory SET equipped=0 WHERE user_id=?", (uid,)
        )
        restored = app_module._get_authoritative_combat_stats(conn, uid)
        assert restored == baseline
    finally:
        conn.close()


def test_production_loadout_flag_off_is_fail_closed_for_first_clear_backfill(
    monkeypatch,
):
    import app as app_module

    monkeypatch.delenv(app_module.EQUIPMENT_CANONICAL_LOADOUT_FLAG, raising=False)
    assert app_module._equipment_canonical_loadout_enabled() is False
    # The route-level reconciliation guard is intentionally tested without a
    # database: OFF must not even open the writer transaction.
    result = app_module._adventure_reconcile_first_clear_equipment(7007)
    assert result == {
        'status': 'DISABLED',
        'converged': False,
        'results': [],
        'error_code': 'EQUIPMENT_CANONICAL_LOADOUT_DISABLED',
    }
