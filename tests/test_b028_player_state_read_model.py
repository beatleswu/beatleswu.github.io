"""Focused contract tests for the B028 Player/Hero read model."""

from __future__ import annotations

import sqlite3

import pytest

from player_state_read_model import (
    PlayerStateReadModelError,
    build_player_state_read_model,
)


EQUIPMENT_DEFINITIONS = [
    {"id": "wooden_sword", "name": "Wooden Sword", "slot": "weapon", "rarity": "common", "icon": "wood"},
    {"id": "iron_sword", "name": "Iron Sword", "slot": "weapon", "rarity": "common", "icon": "sword"},
    {"id": "leather_armor", "name": "Leather Armor", "slot": "armor", "rarity": "common", "icon": "armor"},
    {"id": "lucky_stone", "name": "Lucky Stone", "slot": "accessory", "rarity": "common", "icon": "stone"},
    {"id": "xp_amulet", "name": "XP Amulet", "slot": "accessory", "rarity": "rare", "icon": "amulet"},
    {"id": "go_stone_black", "name": "Black Go Stone", "slot": "accessory", "rarity": "legendary", "icon": "go"},
]

APPEARANCE_DEFINITIONS = [
    {"id": "robe_plain", "name": "Plain Robe", "slot": "outfit", "rarity": "common"},
    {"id": "hat_plain", "name": "Plain Hat", "slot": "hat", "rarity": "common"},
]


def _spirit_projection(active_spirit_id=None):
    def builder(_conn, _user_id):
        return {
            "active_spirit_id": active_spirit_id,
            "ownership_validated": bool(active_spirit_id),
            "evolution_stage": "STAGE_II" if active_spirit_id else None,
            "progression_level": 12 if active_spirit_id else None,
            "enabled": bool(active_spirit_id),
            "single_active_spirit": True,
        }

    return builder


@pytest.fixture()
def conn():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            username TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE user_stats (
            user_id INTEGER PRIMARY KEY,
            total_correct INTEGER NOT NULL DEFAULT 0,
            current_streak INTEGER NOT NULL DEFAULT 0,
            max_streak INTEGER NOT NULL DEFAULT 0,
            xp INTEGER NOT NULL DEFAULT 0,
            rank_level TEXT NOT NULL DEFAULT 'LV1',
            rank_xp INTEGER NOT NULL DEFAULT 0,
            go_rank TEXT NOT NULL DEFAULT '30k',
            player_hp INTEGER NOT NULL DEFAULT 100,
            player_max_hp INTEGER NOT NULL DEFAULT 100
        );
        CREATE TABLE player_inventory (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            equip_id TEXT NOT NULL,
            equipped INTEGER NOT NULL DEFAULT 0,
            obtained_at TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'drop'
        );
        CREATE TABLE pet_collection (
            user_id INTEGER NOT NULL,
            pet_key TEXT NOT NULL,
            level INTEGER NOT NULL DEFAULT 1,
            xp INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, pet_key)
        );
        CREATE TABLE user_pets (
            user_id INTEGER PRIMARY KEY,
            pet_key TEXT NOT NULL,
            level INTEGER NOT NULL DEFAULT 1,
            xp INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE player_wardrobe (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            item_id TEXT NOT NULL,
            obtained_at TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'drop'
        );
        CREATE TABLE player_appearance (
            user_id INTEGER PRIMARY KEY,
            outfit_id TEXT,
            hat_id TEXT,
            back_id TEXT,
            title_id TEXT,
            accessory_id TEXT,
            pet_id TEXT,
            aura_id TEXT,
            character_key TEXT,
            updated_at TEXT
        );
        """
    )
    connection.execute(
        "INSERT INTO users(id, username, password_hash, created_at) VALUES(1, 'p1', 'x', 'now')"
    )
    connection.execute(
        """
        INSERT INTO user_stats(
            user_id, total_correct, current_streak, max_streak, xp, rank_level,
            rank_xp, go_rank, player_hp, player_max_hp
        ) VALUES(1, 4, 3, 5, 123, 'LV12', 40, '18k', 80, 120)
        """
    )
    connection.commit()
    try:
        yield connection
    finally:
        connection.close()


def _build(connection, *, spirit=None):
    return build_player_state_read_model(
        connection,
        1,
        level_resolver=lambda rank: int(str(rank)[2:]),
        equipment_definitions=EQUIPMENT_DEFINITIONS,
        appearance_definitions=APPEARANCE_DEFINITIONS,
        active_character_keys={"apprentice"},
        spirit_projection_builder=spirit or _spirit_projection(),
    )


def _insert_inventory(connection, row_id, item_id, equipped=0):
    connection.execute(
        "INSERT INTO player_inventory(id, user_id, equip_id, equipped, obtained_at) "
        "VALUES(?, 1, ?, ?, 'now')",
        (row_id, item_id, equipped),
    )
    connection.commit()


def test_valid_normal_player_projection_is_server_owned(conn):
    _insert_inventory(conn, 1, "iron_sword", 1)
    conn.execute("INSERT INTO player_wardrobe VALUES(1, 1, 'robe_plain', 'now', 'drop')")
    conn.execute("INSERT INTO player_appearance(user_id, outfit_id, character_key) VALUES(1, 'robe_plain', 'apprentice')")
    conn.commit()

    model = _build(conn)

    assert model["player_id"] == 1
    assert model["read_only"] is True
    assert model["mutates"] is False
    assert model["progression"]["xp"] == 123
    assert model["progression"]["level"] == 12
    assert model["equipment"]["slots"]["weapon"]["item_id"] == "iron_sword"
    assert model["hero"]["hero_id"] == "apprentice"
    assert model["world"]["projected"] is False


def test_default_current_catalog_adapter_projects_current_hero_and_spirit(conn):
    _insert_inventory(conn, 1, "iron_sword", 1)
    conn.execute("INSERT INTO player_wardrobe VALUES(1, 1, 'robe_plain', 'now', 'drop')")
    conn.execute("INSERT INTO player_appearance(user_id, outfit_id, character_key) VALUES(1, 'robe_plain', 'apprentice')")
    conn.execute("INSERT INTO pet_collection(user_id, pet_key, level, xp) VALUES(1, 'ink_drop_kelpie', 12, 7)")
    conn.execute("INSERT INTO user_pets(user_id, pet_key, level, xp) VALUES(1, 'ink_drop_kelpie', 12, 7)")
    conn.commit()

    model = build_player_state_read_model(conn, 1)

    assert model["hero"]["hero_id"] == "apprentice"
    assert model["hero"]["authority"] == "player_appearance.character_key"
    assert model["spirit"]["active"]["spirit_id"] == "ink_drop_kelpie"
    assert model["equipment"]["slots"]["weapon"]["item_id"] == "iron_sword"


def test_no_equipment_is_truthful_and_does_not_fabricate_ownership(conn):
    model = _build(conn)

    assert all(slot["item_id"] is None for slot in model["equipment"]["slots"].values())
    assert model["equipment"]["owned_items"] == []


def test_equipment_projection_preserves_ownership_and_equipped_state(conn):
    _insert_inventory(conn, 1, "iron_sword", 1)
    _insert_inventory(conn, 2, "leather_armor", 1)
    _insert_inventory(conn, 3, "lucky_stone", 1)
    before = conn.execute("SELECT equip_id, equipped FROM player_inventory ORDER BY id").fetchall()
    changes_before = conn.total_changes

    model = _build(conn)

    after = conn.execute("SELECT equip_id, equipped FROM player_inventory ORDER BY id").fetchall()
    assert [(row["equip_id"], row["equipped"]) for row in after] == [
        (row["equip_id"], row["equipped"]) for row in before
    ]
    assert conn.total_changes == changes_before
    assert model["equipment"]["slots"]["armor"]["item_id"] == "leather_armor"
    assert model["equipment"]["slots"]["accessory"]["item_id"] == "lucky_stone"


def test_conflicted_different_equipped_items_fail_closed_without_effective_item(conn):
    _insert_inventory(conn, 1, "iron_sword", 1)
    _insert_inventory(conn, 2, "wooden_sword", 1)
    before = conn.execute(
        "SELECT equip_id, equipped FROM player_inventory ORDER BY id"
    ).fetchall()
    changes_before = conn.total_changes

    model = _build(conn)
    equipment = model["equipment"]
    owned = {item["item_id"]: item for item in equipment["owned_items"]}

    assert equipment["projection_status"] == "INVALID_STORED_STATE"
    assert "weapon" in equipment["equipped_slot_conflicts"]
    assert equipment["slots"]["weapon"]["item_id"] is None
    assert equipment["slots"]["weapon"]["equipped"] is False
    assert owned["iron_sword"]["equipped"] is False
    assert owned["wooden_sword"]["equipped"] is False
    assert conn.total_changes == changes_before
    after = conn.execute(
        "SELECT equip_id, equipped FROM player_inventory ORDER BY id"
    ).fetchall()
    assert [(row["equip_id"], row["equipped"]) for row in after] == [
        (row["equip_id"], row["equipped"]) for row in before
    ]


def test_conflicted_duplicate_equipped_item_rows_remain_unresolved(conn):
    _insert_inventory(conn, 1, "iron_sword", 1)
    _insert_inventory(conn, 2, "iron_sword", 1)

    model = _build(conn)
    equipment = model["equipment"]
    owned = next(item for item in equipment["owned_items"] if item["item_id"] == "iron_sword")

    assert equipment["projection_status"] == "INVALID_STORED_STATE"
    assert "weapon" in equipment["equipped_slot_conflicts"]
    assert equipment["slots"]["weapon"]["item_id"] is None
    assert equipment["slots"]["weapon"]["equipped"] is False
    assert owned["quantity"] == 2
    assert owned["equipped"] is False


def test_xp_amulet_remains_hold_for_authority(conn):
    _insert_inventory(conn, 1, "xp_amulet", 1)

    model = _build(conn)
    accessory = model["equipment"]["slots"]["accessory"]

    assert accessory["item_id"] == "xp_amulet"
    assert accessory["functional_status"] == "HOLD_FOR_AUTHORITY"
    assert "effects" not in accessory


def test_go_stone_black_remains_inventory_only_trophy(conn):
    _insert_inventory(conn, 1, "go_stone_black", 1)

    model = _build(conn)
    trophy = model["equipment"]["owned_items"][0]

    assert trophy["item_id"] == "go_stone_black"
    assert trophy["functional_status"] == "INVENTORY_ONLY_TROPHY"
    assert trophy["combat_power_projected"] is False
    assert model["equipment"]["slots"]["accessory"]["item_id"] is None
    assert model["equipment"]["projection_status"] == "INVALID_STORED_STATE"


def test_active_and_missing_spirit_are_projected_without_combat_effects(conn):
    active = _build(conn, spirit=_spirit_projection("fatty"))
    empty = _build(conn, spirit=_spirit_projection())

    assert active["spirit"]["active"]["spirit_id"] == "fatty"
    assert active["spirit"]["active"]["evolution_stage"] == "STAGE_II"
    assert active["spirit"]["combat_effects_projected"] is False
    assert empty["spirit"]["active"] is None


def test_multiple_active_spirit_projection_fails_closed(conn):
    def ambiguous(_conn, _user_id):
        return {
            "active_spirit_id": "fatty",
            "ownership_validated": True,
            "enabled": True,
            "single_active_spirit": False,
        }

    model = _build(conn, spirit=ambiguous)

    assert model["projection_status"] == "AUTHORITY_AMBIGUOUS"
    assert model["spirit"]["active"] is None
    assert model["spirit"]["single_active_spirit"] is False


def test_cosmetic_projection_is_presentation_only(conn):
    conn.execute("INSERT INTO player_wardrobe VALUES(1, 1, 'robe_plain', 'now', 'drop')")
    conn.execute("INSERT INTO player_appearance(user_id, outfit_id) VALUES(1, 'robe_plain')")
    conn.commit()

    model = _build(conn)
    outfit = model["cosmetics"]["selected"]["outfit"]

    assert outfit["item_id"] == "robe_plain"
    assert outfit["presentation_only"] is True
    assert outfit["combat_power_projected"] is False
    assert model["cosmetics"]["gameplay_effects_projected"] is False


def test_missing_hero_selection_is_truthful(conn):
    model = _build(conn)

    assert model["hero"]["hero_id"] is None
    assert model["hero"]["identity_status"] == "MISSING_HERO_SELECTION"
    assert model["hero"]["presentation_fallback_id"] == "apprentice"


def test_xp_level_and_hp_are_read_from_user_stats_authority(conn):
    model = _build(conn)

    assert model["progression"]["xp"] == 123
    assert model["progression"]["rank_level"] == "LV12"
    assert model["progression"]["level"] == 12
    assert model["hp"]["persistent_player_hp"] == 80
    assert model["hp"]["persistent_player_max_hp"] == 120
    assert model["hp"]["encounter_hp"]["projected"] is False


def test_missing_stats_row_is_partial_not_synthetic(conn):
    conn.execute("DELETE FROM user_stats WHERE user_id=1")
    conn.commit()

    model = _build(conn)

    assert model["projection_status"] == "PARTIAL"
    assert model["progression"]["xp"] is None
    assert model["hp"]["persistent_player_hp"] is None


def test_invalid_stored_hp_is_rejected_without_repair(conn):
    conn.execute("UPDATE user_stats SET player_hp=121 WHERE user_id=1")
    conn.commit()

    model = _build(conn)

    assert model["projection_status"] == "INVALID_STORED_STATE"
    assert "player_hp exceeds player_max_hp" in model["hp"]["invalid_fields"]
    assert conn.execute("SELECT player_hp FROM user_stats WHERE user_id=1").fetchone()[0] == 121


def test_world_progression_is_not_player_owned(conn):
    model = _build(conn)

    assert model["world"]["projected"] is False
    assert model["world"]["authority"] == "world_progression_system"
    assert model["world"]["selected_zone_is_not_player_progression"] is True
    assert "zone_id" not in model["world"]


def test_invalid_user_fails_safely(conn):
    with pytest.raises(PlayerStateReadModelError) as error:
        build_player_state_read_model(
            conn,
            999,
            level_resolver=lambda rank: int(str(rank)[2:]),
            equipment_definitions=EQUIPMENT_DEFINITIONS,
            appearance_definitions=APPEARANCE_DEFINITIONS,
            spirit_projection_builder=_spirit_projection(),
        )

    assert error.value.code == "PLAYER_NOT_FOUND"


def test_malformed_user_id_fails_safely(conn):
    with pytest.raises(PlayerStateReadModelError) as error:
        build_player_state_read_model(conn, "1")

    assert error.value.code == "INVALID_REQUEST"
