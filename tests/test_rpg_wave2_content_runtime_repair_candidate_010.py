"""Deterministic B_010 proofs for repaired content consumers and presentation.

The fixtures are disposable SQLite connections.  They exercise server-owned
definitions and projections only; no Production database or migration is
involved.
"""

import os
import sqlite3
from pathlib import Path

import pytest

os.environ.setdefault("SECRET_KEY", "rpg-wave2-content-runtime-repair-test-secret")
import app as app_module  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]

REPAIRED_PRESENTATION_IDS = {
    # Outfit/body records with a current visual path.
    "robe_plain", "robe_student", "robe_bamboo", "robe_crane", "robe_fox",
    "robe_dragon", "robe_celestial", "robe_rank_1d", "robe_rank_3d",
    "robe_rank_5d", "robe_premium",
    # Back records with a current visual path.
    "back_pack", "back_flag", "back_lantern", "back_wings", "back_foxtail",
    "back_cloak", "back_dragon_wings",
    # Accessory records with a current visual path.
    "acc_bracelet", "acc_fan", "acc_goboard_bag", "acc_jade_ring",
    "acc_dragon_pendant", "acc_premium",
}

NON_REPAIRABLE_AUDIT_BUCKET = {
    "robe_snow", "back_scroll", "acc_goban_seal", "acc_golden_bell",
}


def _inventory_conn(*equipment_ids):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE player_inventory(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            equip_id TEXT NOT NULL,
            equipped INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.executemany(
        "INSERT INTO player_inventory(user_id,equip_id,equipped) VALUES(1,?,1)",
        [(item_id,) for item_id in equipment_ids],
    )
    return conn


def test_repaired_effects_are_allowlisted_and_holds_remain_inactive():
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
    assert app_module._get_active_equip_effect(conn, 1, "crit_multiplier") == pytest.approx(3)
    assert app_module._get_active_equip_effect(conn, 1, "first_question_ace") == 0
    conn.close()


def test_celestial_combo_and_dragon_eye_critical_consumers_are_deterministic():
    plain_xp, plain_multiplier = app_module.calc_xp_gain("hard", 0, False, False)
    blade_at_zero_xp, blade_at_zero_multiplier = app_module.calc_xp_gain(
        "hard", 0, False, False, combo_multiplier_double=True
    )
    assert blade_at_zero_xp == plain_xp
    assert blade_at_zero_multiplier == plain_multiplier == 1.0

    plain_combo_xp, plain_combo_multiplier = app_module.calc_xp_gain("hard", 10, False, False)
    blade_combo_xp, blade_combo_multiplier = app_module.calc_xp_gain(
        "hard", 10, False, False, combo_multiplier_double=True
    )
    assert blade_combo_multiplier > plain_combo_multiplier
    assert blade_combo_xp > plain_combo_xp

    assert app_module._calc_damage(5, 1000, crit_multiplier=1) == 80
    assert app_module._calc_damage(5, 1000, crit_multiplier=3) == 240
    assert app_module._calc_damage(4, 1000, crit_multiplier=3) == 60


def test_fox_mask_daily_quest_reward_uses_server_equipment_effect(monkeypatch):
    conn = _inventory_conn("fox_mask")
    conn.execute(
        "CREATE TABLE user_stats(user_id INTEGER PRIMARY KEY, xp INTEGER NOT NULL DEFAULT 0, rank_xp INTEGER NOT NULL DEFAULT 0)"
    )
    conn.execute(
        """
        CREATE TABLE daily_quests(
            user_id INTEGER NOT NULL,
            quest_key TEXT NOT NULL,
            target INTEGER NOT NULL,
            progress INTEGER NOT NULL DEFAULT 0,
            completed INTEGER NOT NULL DEFAULT 0,
            xp_awarded INTEGER NOT NULL DEFAULT 0,
            quest_date TEXT NOT NULL,
            PRIMARY KEY(user_id, quest_key, quest_date)
        )
        """
    )
    conn.execute("INSERT INTO user_stats(user_id) VALUES(1)")
    conn.execute(
        "INSERT INTO daily_quests(user_id,quest_key,target,progress,quest_date) VALUES(1,'kill_monsters',5,4,'2026-08-22')"
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


def test_void_mantle_negates_server_retaliation_without_client_input():
    conn = _inventory_conn("void_mantle")
    conn.executescript(
        """
        CREATE TABLE user_stats(
            user_id INTEGER PRIMARY KEY,
            total_correct INTEGER NOT NULL DEFAULT 0,
            go_rank TEXT NOT NULL DEFAULT '30k',
            xp INTEGER NOT NULL DEFAULT 0,
            rank_level TEXT NOT NULL DEFAULT 'LV1',
            player_hp INTEGER NOT NULL DEFAULT 100,
            player_max_hp INTEGER NOT NULL DEFAULT 100
        );
        CREATE TABLE player_skills(user_id INTEGER, skill_id TEXT, equipped INTEGER DEFAULT 0);
        CREATE TABLE battlefield_monster(
            user_id INTEGER, bf_date TEXT, monster_idx INTEGER DEFAULT 0,
            monster_type TEXT, monster_name TEXT, monster_avatar TEXT,
            max_hp INTEGER, current_hp INTEGER, defeated INTEGER DEFAULT 0,
            kill_count INTEGER DEFAULT 0, PRIMARY KEY(user_id,bf_date)
        );
        INSERT INTO user_stats(user_id,player_hp,player_max_hp) VALUES(1,100,100);
        INSERT INTO battlefield_monster(
            user_id,bf_date,monster_idx,monster_type,monster_name,monster_avatar,
            max_hp,current_hp,defeated,kill_count
        ) VALUES(1,'2026-08-22',0,'goblin','LV1 Goblin','',1000,1000,0,0);
        """
    )
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(app_module, "_update_daily_quests", lambda *args, **kwargs: [])
    try:
        result = app_module._update_monster_and_quests(
            conn, 1, 99, 0, {"monster_atk": 9999}, 0, "2026-08-22"
        )
    finally:
        monkeypatch.undo()

    assert result["monster"]["player_dmg"] == 0
    assert result["player"]["hp"] == 100
    assert result["player"]["ko"] is False
    conn.close()


def test_presentation_metadata_separates_asset_and_visual_generation():
    for item_id in app_module.PURE_COSMETIC_NEW_21:
        item = app_module._APPEAR_MAP[item_id]
        metadata = app_module._appearance_presentation_metadata(item)
        assert metadata["asset_id"] == item_id
        assert metadata["mode"] == "FULL_BODY_COSMETIC_REFERENCE"
        assert metadata["visual_generation"] == "WAVE2_FULL_BODY_REFERENCE"
        assert (ROOT / metadata["asset"].lstrip("/")).is_file(), item_id
        assert metadata["combat_authority"] == "NO"

    for item_id in ("robe_premium", "acc_premium", "aura_premium", "pet_premium"):
        item = app_module._APPEAR_MAP[item_id]
        metadata = app_module._appearance_presentation_metadata(item)
        assert metadata["asset_id"] == item_id
        assert metadata["mode"] == "CATALOG_ICON"
        assert metadata["visual_generation"] == "LEGACY_ICON"
        assert (ROOT / metadata["asset"].lstrip("/")).is_file(), item_id


def test_presentation_repair_scope_reconciles_28_to_24_without_reviving_hidden_content():
    assert len(REPAIRED_PRESENTATION_IDS) == 24
    assert len(NON_REPAIRABLE_AUDIT_BUCKET) == 4
    assert REPAIRED_PRESENTATION_IDS.isdisjoint(NON_REPAIRABLE_AUDIT_BUCKET)

    for item_id in REPAIRED_PRESENTATION_IDS:
        metadata = app_module._appearance_presentation_metadata(app_module._APPEAR_MAP[item_id])
        assert metadata["asset_id"] == item_id
        assert metadata["asset"].startswith("/assets/hero/items/")
        assert metadata["hero_projection_allowed"] is True
        assert (ROOT / metadata["asset"].lstrip("/")).is_file(), item_id

    # These four records remain outside the released/repairable set.  This
    # is a content-release boundary, not an instruction to add art or grant
    # an acquisition path.
    assert {"robe_snow", "back_scroll", "acc_goban_seal"} <= NON_REPAIRABLE_AUDIT_BUCKET
    assert "acc_golden_bell" in NON_REPAIRABLE_AUDIT_BUCKET
    for item_id in NON_REPAIRABLE_AUDIT_BUCKET:
        assert app_module._appearance_presentation_metadata(
            app_module._APPEAR_MAP[item_id]
        )["hero_projection_allowed"] is False


def test_cosmetic_renderer_consumes_server_projection_only():
    source = (ROOT / "js/rpg_wave2_wearable_renderer.js").read_text(encoding="utf-8")
    assert "renderCosmeticSafe" in source
    assert "value.owned !== true || value.equipped !== true" in source
    assert "presentation.selected !== true" in source
    assert "presentation.visible !== true" in source
    assert "presentation.hero_projection_allowed === false" in source
    assert "gameplayAuthority = 'none'" in source
    assert "player_inventory" not in source


class _ShopDbContext:
    def __init__(self, path):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.conn.commit()
        else:
            self.conn.rollback()
        self.conn.close()


def test_question_limit_items_consume_once_persist_and_preserve_boundary(tmp_path, monkeypatch):
    path = tmp_path / "question-limit.sqlite"
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE users(
                id INTEGER PRIMARY KEY,
                plan TEXT NOT NULL DEFAULT 'free',
                premium_until TEXT
            );
            CREATE TABLE shop_inventory(
                user_id INTEGER NOT NULL,
                item_key TEXT NOT NULL,
                qty INTEGER NOT NULL,
                UNIQUE(user_id, item_key)
            );
            CREATE TABLE active_effects(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                effect_key TEXT NOT NULL,
                value REAL NOT NULL,
                effect_date TEXT,
                expires_at TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE review_log(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                reviewed_at TEXT NOT NULL
            );
            INSERT INTO users(id,plan) VALUES(1,'free');
            INSERT INTO shop_inventory(user_id,item_key,qty) VALUES
                (1,'extra_questions_small',1),
                (1,'extra_questions',1),
                (1,'grand_training_pass',1);
            """
        )

    monkeypatch.setattr(app_module, "get_db", lambda: _ShopDbContext(path))
    app_module.app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
    client = app_module.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 1
        session["username"] = "question-limit-test"

    baseline = client.get("/api/subscription/status")
    assert baseline.status_code == 200
    assert baseline.get_json()["daily_limit"] == app_module.FREE_DAILY_LIMIT == 20

    expected_limits = (
        ("extra_questions_small", 25, 5),
        ("extra_questions", 35, 10),
        ("grand_training_pass", 55, 20),
    )
    for item_key, expected_limit, expected_increment in expected_limits:
        used = client.post("/api/shop/use", json={"item_key": item_key})
        assert used.status_code == 200
        payload = used.get_json()
        assert payload["effect"] == "extra_questions"
        assert payload["value"] == expected_increment
        assert payload["remaining"] == 0

        status = client.get("/api/subscription/status")
        assert status.status_code == 200
        assert status.get_json()["daily_limit"] == expected_limit

        # A second request cannot consume the same item again.
        duplicate = client.post("/api/shop/use", json={"item_key": item_key})
        assert duplicate.status_code == 400
        assert duplicate.get_json()["error"] == "not_owned"

    # Re-login/reload reads the same server-side same-day effect rows.
    reloaded = app_module.app.test_client()
    with reloaded.session_transaction() as session:
        session["user_id"] = 1
        session["username"] = "question-limit-test"
    assert reloaded.get("/api/subscription/status").get_json()["daily_limit"] == 55

    # At the final boundary the review guard still blocks; the product limit
    # is server-derived rather than a browser counter.
    monkeypatch.setattr(app_module, "get_today_free_count", lambda uid: 55)
    blocked = reloaded.post("/api/srs/review", json={"question_id": 0, "grade": 5})
    assert blocked.status_code == 429
    assert blocked.get_json()["error"] == "daily_limit"
    assert blocked.get_json()["limit"] == 55
