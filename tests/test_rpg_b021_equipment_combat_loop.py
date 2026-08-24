"""B021 proof that authoritative equipment reaches real battle settlement."""

import hashlib
import os
import sqlite3

import pytest

os.environ.setdefault("SECRET_KEY", "rpg-b021-combat-loop-test-secret")

import app as app_module  # noqa: E402
import monster_settlement as monster_settlement_module  # noqa: E402
from map_battle_persistence import create_map_battle, ensure_map_battle_tables  # noqa: E402
from migrations.domain_event_outbox_v1 import upgrade as upgrade_outbox  # noqa: E402
from map_battle_runtime import (  # noqa: E402
    ensure_submission_lifecycle_schema,
    issue_attempt_for_context,
    issue_submission_nonce_for_attempt,
    settle_answer,
)


def _create_legacy_db(path, *, equipment=(), monster_idx=0, monster_type="caterpillar",
                      max_hp=1000, current_hp=1000):
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE user_stats (
                user_id INTEGER PRIMARY KEY,
                total_correct INTEGER NOT NULL DEFAULT 0,
                current_streak INTEGER NOT NULL DEFAULT 0,
                max_streak INTEGER NOT NULL DEFAULT 0,
                mistake_corrected INTEGER NOT NULL DEFAULT 0,
                xp INTEGER NOT NULL DEFAULT 0,
                rank_level TEXT NOT NULL DEFAULT 'LV1',
                rank_xp INTEGER NOT NULL DEFAULT 0,
                coins INTEGER NOT NULL DEFAULT 0,
                player_hp INTEGER NOT NULL DEFAULT 100,
                player_max_hp INTEGER NOT NULL DEFAULT 100
            );
            CREATE TABLE currency_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                delta INTEGER NOT NULL,
                balance_after INTEGER NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE player_inventory (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                equip_id TEXT NOT NULL,
                equipped INTEGER NOT NULL DEFAULT 0,
                obtained_at TEXT,
                source TEXT,
                rarity TEXT
            );
            CREATE TABLE player_skills (
                user_id INTEGER NOT NULL,
                skill_id TEXT NOT NULL,
                equipped INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(user_id, skill_id)
            );
            CREATE TABLE battlefield_monster (
                user_id INTEGER NOT NULL,
                bf_date TEXT NOT NULL,
                monster_idx INTEGER NOT NULL DEFAULT 0,
                monster_type TEXT NOT NULL,
                monster_name TEXT NOT NULL,
                monster_avatar TEXT,
                max_hp INTEGER NOT NULL,
                current_hp INTEGER NOT NULL,
                defeated INTEGER NOT NULL DEFAULT 0,
                kill_count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(user_id, bf_date)
            );
            CREATE TABLE monster_kill_log (
                user_id INTEGER NOT NULL,
                monster_type TEXT NOT NULL,
                kill_count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(user_id, monster_type)
            );
            CREATE TABLE monster_kill_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                monster_type TEXT NOT NULL,
                monster_name TEXT NOT NULL,
                killed_at TEXT NOT NULL,
                bf_date TEXT NOT NULL
            );
            """
        )
        conn.execute(
            "INSERT INTO user_stats(user_id,player_hp,player_max_hp) VALUES(1,100,100)"
        )
        upgrade_outbox(conn)
        conn.execute(
            """INSERT INTO battlefield_monster(
                 user_id,bf_date,monster_idx,monster_type,monster_name,
                 monster_avatar,max_hp,current_hp,defeated,kill_count
               ) VALUES(1,'2026-08-14',?,?,?,?,?,?,0,0)""",
            # The production loader treats non-canonical names as legacy rows
            # and resets them to the current roster profile.  Keep this
            # disposable fixture canonical while retaining its deterministic
            # 1000 HP comparison target.
            (monster_idx, monster_type, "LV B021 encounter", "monster.svg", max_hp, current_hp),
        )
        for row_id, equip_id, equipped in equipment:
            conn.execute(
                """INSERT INTO player_inventory(
                     id,user_id,equip_id,equipped,obtained_at,source
                   ) VALUES(?,?,?,?,?,?)""",
                (row_id, 1, equip_id, equipped, "2026-08-14", "test"),
            )


def _inventory_conn(*equipment_ids):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE player_inventory(
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               user_id INTEGER NOT NULL,
               equip_id TEXT NOT NULL,
               equipped INTEGER NOT NULL DEFAULT 0
           )"""
    )
    conn.executemany(
        "INSERT INTO player_inventory(user_id,equip_id,equipped) VALUES(1,?,1)",
        [(equipment_id,) for equipment_id in equipment_ids],
    )
    return conn


def _legacy_battle(path, monkeypatch, *, equipment=(), grade=5, monster_idx=0,
                   monster_type="caterpillar", max_hp=1000, current_hp=1000,
                   loot_roll=None):
    _create_legacy_db(
        path,
        equipment=equipment,
        monster_idx=monster_idx,
        monster_type=monster_type,
        max_hp=max_hp,
        current_hp=current_hp,
    )
    monkeypatch.setattr(app_module, "_update_daily_quests", lambda *args, **kwargs: [])
    monkeypatch.setattr(app_module, "_gain_sp", lambda conn, uid, amount: amount)
    monkeypatch.setattr(app_module, "_roll_appearance_loot", lambda *args: None)
    monkeypatch.setattr(app_module, "_roll_loot", loot_roll or (lambda *args: None))
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        return app_module._update_monster_and_quests(
            conn, 1, 9001, grade, {"monster_atk": 999}, 0, "2026-08-14"
        )


@pytest.mark.parametrize(
    "equip_id,monster_idx,monster_type,expected_damage",
    [
        (None, 0, "caterpillar", 80),
        ("wooden_sword", 0, "caterpillar", 84),
        ("iron_sword", 0, "caterpillar", 90),
        ("fox_fang", 12, "fox", 108),
        ("dragon_claw", 11, "dragon", 124),
        ("celestial_blade", 0, "caterpillar", 128),
    ],
)
def test_every_canonical_weapon_changes_real_legacy_battle_damage(
    tmp_path, monkeypatch, equip_id, monster_idx, monster_type, expected_damage
):
    equipment = ((1, equip_id, 1),) if equip_id else ()
    result = _legacy_battle(
        tmp_path / f"{equip_id or 'baseline'}.sqlite",
        monkeypatch,
        equipment=equipment,
        monster_idx=monster_idx,
        monster_type=monster_type,
    )
    assert result["monster"]["dmg"] == expected_damage
    assert result["combat_stats"]["attack_bonus"] == pytest.approx(
        {None: 0, "wooden_sword": 0.05, "iron_sword": 0.12,
         "fox_fang": 0.35, "dragon_claw": 0.55,
         "celestial_blade": 0.60}[equip_id]
    )


def test_weapon_unequip_restores_real_legacy_damage(tmp_path, monkeypatch):
    equipped = _legacy_battle(
        tmp_path / "equipped.sqlite", monkeypatch,
        equipment=((1, "iron_sword", 1),),
    )
    unequipped = _legacy_battle(
        tmp_path / "unequipped.sqlite", monkeypatch,
        equipment=((1, "iron_sword", 0),),
    )
    baseline = _legacy_battle(tmp_path / "baseline.sqlite", monkeypatch)
    assert equipped["monster"]["dmg"] == 90
    assert unequipped["monster"]["dmg"] == baseline["monster"]["dmg"] == 80


def test_armor_and_void_mantle_change_real_retaliation_and_unequip_restores_baseline(
    tmp_path, monkeypatch
):
    baseline = _legacy_battle(
        tmp_path / "baseline.sqlite", monkeypatch, grade=0, monster_idx=11, monster_type="dragon"
    )
    cloth = _legacy_battle(
        tmp_path / "cloth.sqlite", monkeypatch,
        equipment=((1, "cloth_robe", 1),), grade=0, monster_idx=11, monster_type="dragon"
    )
    void = _legacy_battle(
        tmp_path / "void.sqlite", monkeypatch,
        equipment=((1, "void_mantle", 1),), grade=0, monster_idx=11, monster_type="dragon"
    )
    unequipped = _legacy_battle(
        tmp_path / "unequipped.sqlite", monkeypatch,
        equipment=((1, "cloth_robe", 0),), grade=0, monster_idx=11, monster_type="dragon"
    )
    assert baseline["monster"]["player_dmg"] == 14
    assert cloth["monster"]["player_dmg"] == 13
    assert void["monster"]["player_dmg"] == 0
    assert unequipped["monster"]["player_dmg"] == baseline["monster"]["player_dmg"]


def test_dragon_eye_grade_five_critical_effect_is_server_effective(tmp_path, monkeypatch):
    baseline = _legacy_battle(tmp_path / "baseline.sqlite", monkeypatch)
    critical = _legacy_battle(
        tmp_path / "critical.sqlite", monkeypatch,
        equipment=((1, "dragon_eye", 1),),
    )
    assert baseline["monster"]["dmg"] == 80
    assert critical["monster"]["dmg"] == 240
    assert critical["combat_stats"]["crit_multiplier"] == 3.0


def test_accessory_swap_and_unequip_restore_real_legacy_damage(tmp_path, monkeypatch):
    path = tmp_path / "accessory-swap.sqlite"
    _create_legacy_db(path, equipment=((1, "dragon_eye", 1),))
    monkeypatch.setattr(app_module, "_update_daily_quests", lambda *args, **kwargs: [])
    monkeypatch.setattr(app_module, "_gain_sp", lambda conn, uid, amount: amount)
    monkeypatch.setattr(app_module, "_roll_appearance_loot", lambda *args: None)
    monkeypatch.setattr(app_module, "_roll_loot", lambda *args: None)
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        critical = app_module._update_monster_and_quests(
            conn, 1, 9001, 5, {"monster_atk": 999}, 0, "2026-08-14"
        )
        conn.execute("UPDATE player_inventory SET equipped=0 WHERE id=1")
        conn.execute(
            "UPDATE battlefield_monster SET current_hp=1000 WHERE user_id=1 AND bf_date=?",
            ("2026-08-14",),
        )
        baseline = app_module._update_monster_and_quests(
            conn, 1, 9002, 5, {"monster_atk": 999}, 0, "2026-08-14"
        )

    assert critical["monster"]["dmg"] == 240
    assert baseline["monster"]["dmg"] == 80


def test_approved_effect_allowlist_keeps_hold_items_inactive():
    conn = _inventory_conn(
        "fox_pelt",
        "celestial_blade",
        "void_mantle",
        "fox_mask",
        "dragon_eye",
        "xp_amulet",
        "go_stone_black",
    )
    assert app_module._get_active_equip_effect(conn, 1, "xp_bonus") == pytest.approx(0.10)
    assert app_module._get_active_equip_effect(conn, 1, "combo_multiplier_double") == pytest.approx(1.0)
    assert app_module._get_active_equip_effect(conn, 1, "negate_counter") == pytest.approx(1.0)
    assert app_module._get_active_equip_effect(conn, 1, "quest_xp_bonus") == pytest.approx(0.25)
    assert app_module._get_active_equip_effect(conn, 1, "crit_multiplier") == pytest.approx(3.0)
    assert app_module._get_active_equip_effect(conn, 1, "first_question_ace") == 0
    conn.close()


def test_celestial_blade_combo_bonus_is_server_defined():
    plain_xp, plain_multiplier = app_module.calc_xp_gain("hard", 0, False, False)
    zero_combo_xp, zero_combo_multiplier = app_module.calc_xp_gain(
        "hard", 0, False, False, combo_multiplier_double=True
    )
    assert zero_combo_xp == plain_xp
    assert zero_combo_multiplier == plain_multiplier == 1.0

    plain_combo_xp, plain_combo_multiplier = app_module.calc_xp_gain(
        "hard", 10, False, False
    )
    blade_combo_xp, blade_combo_multiplier = app_module.calc_xp_gain(
        "hard", 10, False, False, combo_multiplier_double=True
    )
    assert blade_combo_multiplier > plain_combo_multiplier
    assert blade_combo_xp > plain_combo_xp


def test_fox_mask_daily_quest_xp_uses_server_equipment_effect(monkeypatch):
    conn = _inventory_conn("fox_mask")
    conn.execute(
        "CREATE TABLE user_stats(user_id INTEGER PRIMARY KEY, xp INTEGER NOT NULL DEFAULT 0, rank_xp INTEGER NOT NULL DEFAULT 0)"
    )
    conn.execute(
        """CREATE TABLE daily_quests(
               user_id INTEGER NOT NULL,
               quest_key TEXT NOT NULL,
               target INTEGER NOT NULL,
               progress INTEGER NOT NULL DEFAULT 0,
               completed INTEGER NOT NULL DEFAULT 0,
               xp_awarded INTEGER NOT NULL DEFAULT 0,
               quest_date TEXT NOT NULL,
               PRIMARY KEY(user_id, quest_key, quest_date)
           )"""
    )
    conn.execute("INSERT INTO user_stats(user_id) VALUES(1)")
    conn.execute(
        "INSERT INTO daily_quests(user_id,quest_key,target,progress,quest_date) "
        "VALUES(1,'kill_monsters',5,4,'2026-08-22')"
    )
    monkeypatch.setattr(app_module, "_grant_pet_food", lambda *args, **kwargs: None)
    monkeypatch.setattr(app_module, "_grant_coins", lambda *args, **kwargs: None)
    results = app_module._update_daily_quests(
        conn,
        1,
        "2026-08-22",
        grade=5,
        monster_defeated=True,
        monster_type="goblin",
        combo_streak=0,
        shadow_events=[],
    )
    assert results[0]["key"] == "kill_monsters"
    assert results[0]["xp"] == 37
    assert tuple(conn.execute("SELECT xp,rank_xp FROM user_stats WHERE user_id=1").fetchone()) == (37, 37)
    conn.close()


def test_lucky_stone_swap_changes_real_drop_roll_input(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(
        monster_settlement_module,
        "roll_functional_drop",
        lambda profile, loot_bonus=0.0, random_source=None: seen.append(loot_bonus) or (None, 0),
    )
    _legacy_battle(
        tmp_path / "lucky.sqlite", monkeypatch,
        # One grade-five hit is 80 base damage on this deterministic 1000 HP
        # encounter, so start at 80 HP to exercise the real defeat/drop path.
        equipment=((1, "lucky_stone", 1),), current_hp=80,
    )
    _legacy_battle(
        tmp_path / "plain.sqlite", monkeypatch, current_hp=80,
    )
    assert seen == [pytest.approx(0.10), pytest.approx(0.0)]


def _map_battle_settlement(tmp_path, *, equipment=(), moves=None):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE users(id INTEGER PRIMARY KEY)")
    conn.execute("INSERT INTO users(id) VALUES(101)")
    conn.execute(
        """CREATE TABLE player_inventory(
             id INTEGER PRIMARY KEY, user_id INTEGER, equip_id TEXT,
             equipped INTEGER NOT NULL DEFAULT 0, obtained_at TEXT, source TEXT
           )"""
    )
    ensure_map_battle_tables(conn)
    ensure_submission_lifecycle_schema(conn)
    create_map_battle(
        conn,
        battle_id="b021-battle",
        user_id=101,
        zone_key="legacy::forest",
        player_hp=100,
        player_hp_max=100,
        monster_hp=1000,
        monster_hp_max=1000,
        now="2026-08-14T00:00:00+00:00",
    )
    question = {
        "id": 7021,
        "content": "(;SZ[19];B[dd];W[ee])",
        "monster_atk": 20,
    }
    issue_attempt_for_context(
        conn,
        user_id=101,
        battle_id="b021-battle",
        question=question,
        initial_position_identity="b021-position",
        board_size=19,
        player_color="B",
        transform_version="transform-v1",
        transform_id="identity",
        attempt_id="b021-attempt",
        issued_at="2026-08-14T00:00:00+00:00",
        expires_at="2026-08-15T00:00:00+00:00",
    )
    issued = issue_submission_nonce_for_attempt(
        conn,
        user_id=101,
        attempt_id="b021-attempt",
        now="2026-08-14T00:01:00+00:00",
        mode_environ={"E10_MAP_BATTLE_V1_MODE": "global"},
    )
    attempt = conn.execute(
        "SELECT * FROM map_battle_attempts WHERE id='b021-attempt'"
    ).fetchone()
    if equipment:
        conn.execute(
            "INSERT INTO player_inventory(id,user_id,equip_id,equipped,obtained_at,source) "
            "VALUES(?,?,?,?,?,?)",
            (1, 101, equipment, 1, "2026-08-14", "test"),
        )
    payload = {
        "battle_id": "b021-battle",
        "attempt_id": "b021-attempt",
        "submission_nonce": issued["submission_nonce"],
        "battle_revision": 0,
        "question_revision": attempt["question_revision"],
        "player_color": "black",
        "transform_id": attempt["transform_id"],
        "transform_version": attempt["transform_version"],
        "moves": moves if moves is not None else [{"x": 3, "y": 3}],
    }
    result = settle_answer(
        conn,
        user_id=101,
        payload=payload,
        question_loader=lambda question_id: question if question_id == question["id"] else None,
        mode_environ={"E10_MAP_BATTLE_V1_MODE": "global"},
        now="2026-08-14T00:02:00+00:00",
        combat_stats_resolver=app_module._get_authoritative_combat_stats,
    )
    conn.commit()
    conn.close()
    return result


@pytest.mark.parametrize(
    "equipment,expected_damage",
    [(None, 80), ("iron_sword", 90), ("dragon_eye", 240)],
)
def test_map_battle_settlement_uses_server_equipment_stats(
    tmp_path, equipment, expected_damage
):
    result = _map_battle_settlement(tmp_path, equipment=equipment)
    assert result["result"] == "CORRECT"
    assert result["damage_to_monster"] == expected_damage


def test_map_battle_void_mantle_negates_real_retaliation(tmp_path):
    result = _map_battle_settlement(tmp_path, equipment="void_mantle", moves=[{"x": 0, "y": 0}])
    assert result["result"] == "INCORRECT"
    assert result["damage_to_player"] == 0


def test_inventory_only_go_stone_cannot_be_equipped(tmp_path, monkeypatch):
    path = tmp_path / "inventory-only.sqlite"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE player_inventory(id INTEGER PRIMARY KEY,user_id INTEGER,equip_id TEXT,equipped INTEGER,obtained_at TEXT,source TEXT)"
        )
        conn.execute(
            "INSERT INTO player_inventory VALUES(1,1,'go_stone_black',0,'2026-08-14','boss')"
        )
        conn.execute(
            "INSERT INTO player_inventory VALUES(2,1,'unknown_equipment',0,'2026-08-14','test')"
        )

    class _Db:
        def __enter__(self):
            self.conn = sqlite3.connect(path)
            self.conn.row_factory = sqlite3.Row
            return self.conn

        def __exit__(self, exc_type, exc, tb):
            (self.conn.rollback() if exc_type else self.conn.commit())
            self.conn.close()

    monkeypatch.setattr(app_module, "get_db", lambda: _Db())
    app_module.app.config["TESTING"] = True
    client = app_module.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 1
        session["username"] = "b021-test"
    response = client.post(
        "/api/player/inventory/equip",
        json={"inv_id": 1, "action": "equip", "effects": {"first_question_ace": True}},
    )
    assert response.status_code == 400
    unknown_response = client.post(
        "/api/player/inventory/equip",
        json={"inv_id": 2, "action": "equip"},
    )
    assert unknown_response.status_code == 400
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT equipped FROM player_inventory WHERE id=1").fetchone()[0] == 0
        assert conn.execute("SELECT equipped FROM player_inventory WHERE id=2").fetchone()[0] == 0


def test_equipped_state_rehydrates_from_server_for_a_new_client(tmp_path, monkeypatch):
    path = tmp_path / "rehydrate.sqlite"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE player_inventory(id INTEGER PRIMARY KEY,user_id INTEGER,equip_id TEXT,equipped INTEGER,obtained_at TEXT,source TEXT)"
        )
        conn.executemany(
            "INSERT INTO player_inventory VALUES(?,?,?,?,?,?)",
            [
                (1, 1, "wooden_sword", 1, "2026-08-14", "test"),
                (2, 1, "iron_sword", 0, "2026-08-14", "test"),
            ],
        )

    class _Db:
        def __enter__(self):
            self.conn = sqlite3.connect(path)
            self.conn.row_factory = sqlite3.Row
            return self.conn

        def __exit__(self, exc_type, exc, tb):
            (self.conn.rollback() if exc_type else self.conn.commit())
            self.conn.close()

    monkeypatch.setattr(app_module, "get_db", lambda: _Db())
    app_module.app.config["TESTING"] = True
    first_client = app_module.app.test_client()
    with first_client.session_transaction() as session:
        session["user_id"] = 1
    assert first_client.post(
        "/api/player/inventory/equip", json={"inv_id": 2, "action": "equip"}
    ).status_code == 200

    reloaded_client = app_module.app.test_client()
    with reloaded_client.session_transaction() as session:
        session["user_id"] = 1
    inventory = reloaded_client.get("/api/player/inventory").get_json()
    equipped = {item["item_id"]: item["equipped"] for item in inventory}
    assert equipped["iron_sword"] is True
    assert equipped["wooden_sword"] is False


def test_battle_after_reload_reads_server_equipment_state(tmp_path, monkeypatch):
    path = tmp_path / "rehydrated-battle.sqlite"
    _create_legacy_db(
        path,
        equipment=(
            (1, "wooden_sword", 0),
            (2, "iron_sword", 0),
        ),
    )

    class _Db:
        def __enter__(self):
            self.conn = sqlite3.connect(path)
            self.conn.row_factory = sqlite3.Row
            return self.conn

        def __exit__(self, exc_type, exc, tb):
            (self.conn.rollback() if exc_type else self.conn.commit())
            self.conn.close()

    monkeypatch.setattr(app_module, "get_db", lambda: _Db())
    monkeypatch.setattr(app_module, "_update_daily_quests", lambda *args, **kwargs: [])
    monkeypatch.setattr(app_module, "_gain_sp", lambda conn, uid, amount: amount)
    monkeypatch.setattr(app_module, "_roll_appearance_loot", lambda *args: None)
    monkeypatch.setattr(app_module, "_roll_loot", lambda *args: None)

    client = app_module.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 1
    assert client.post(
        "/api/player/inventory/equip", json={"inv_id": 2, "action": "equip"}
    ).status_code == 200

    # A fresh connection models reload/re-entry; the real battle function
    # derives damage from the persisted equipped row, not browser state.
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        result = app_module._update_monster_and_quests(
            conn, 1, 9021, 5, {"monster_atk": 999}, 0, "2026-08-14"
        )
    assert result["monster"]["dmg"] == 90
