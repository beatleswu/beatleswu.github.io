"""F027-R1 Mapping A wardrobe/runtime consumption contracts."""

from __future__ import annotations

import os
import sqlite3

import pytest

os.environ.setdefault("SECRET_KEY", "f027-r1-mapping-a-wardrobe-test-secret")

from mapping_a_wardrobe_runtime import (  # noqa: E402
    INVALID_STORED_STATE,
    MAPPING_A_CATALOG,
    MAPPING_A_COMBAT_POWER,
    MAPPING_A_ID_COUNT,
    MAPPING_A_IDS,
    READY,
    consume_mapping_a_cosmetics,
    validate_mapping_a_catalog,
)
from player_state_read_model import build_player_state_read_model  # noqa: E402


CANONICAL_MAPPING_A_DEFINITIONS = [
    {"id": "back_pack", "name": "Pack", "slot": "back", "rarity": "common"},
    {"id": "hat_cloth", "name": "Cloth Hat", "slot": "hat", "rarity": "common"},
    {"id": "hat_bamboo", "name": "Bamboo Hat", "slot": "hat", "rarity": "common"},
    {"id": "robe_crane", "name": "Crane Robe", "slot": "outfit", "rarity": "uncommon"},
    {"id": "hat_onihorns", "name": "Oni Horns", "slot": "hat", "rarity": "rare"},
    {"id": "robe_dragon", "name": "Dragon Robe", "slot": "outfit", "rarity": "epic"},
    {"id": "acc_dragon_pendant", "name": "Dragon Pendant", "slot": "accessory", "rarity": "epic"},
    {"id": "back_cloak", "name": "Star Cloak", "slot": "back", "rarity": "epic"},
    {"id": "hat_dragon_horn", "name": "Dragon Horn", "slot": "hat", "rarity": "epic"},
    {"id": "hat_celestial_crown", "name": "Celestial Crown", "slot": "hat", "rarity": "legendary"},
]
DEFINITION_BY_ID = {item["id"]: item for item in CANONICAL_MAPPING_A_DEFINITIONS}


def _display(item_id: str) -> dict[str, object]:
    definition = DEFINITION_BY_ID[item_id]
    return {
        "item_id": item_id,
        "name": definition["name"],
        "slot": definition["slot"],
        "rarity": definition["rarity"],
        "presentation_only": True,
    }


def _cosmetics(*, owned_ids=MAPPING_A_IDS, selected_ids=()):
    selected = {
        "outfit": None,
        "hat": None,
        "back": None,
        "title": None,
        "accessory": None,
        "pet": None,
        "aura": None,
    }
    for item_id in selected_ids:
        slot = DEFINITION_BY_ID[item_id]["slot"]
        selected[slot] = {
            "item_id": item_id,
            "owned": True,
            "equipped": True,
            "display": _display(item_id),
            "presentation_only": True,
            "combat_power_projected": False,
        }
    return {
        "projection_status": "OK",
        "authority": "player_wardrobe_and_player_appearance",
        "selected": selected,
        "owned_items": [
            {
                "item_id": item_id,
                "slot": DEFINITION_BY_ID[item_id]["slot"],
                "display": _display(item_id),
                "obtained_at": "2026-08-28T00:00:00",
                "source": "controlled_authoritative_fixture",
                "presentation_only": True,
                "combat_power_projected": False,
            }
            for item_id in owned_ids
        ],
        "invalid_item_ids": [],
        "invalid_selected_ids": [],
        "gameplay_effects_projected": False,
    }


def _spirit_projection(_conn, _user_id):
    return {
        "active_spirit_id": None,
        "ownership_validated": False,
        "evolution_stage": None,
        "progression_level": None,
        "enabled": False,
        "single_active_spirit": True,
    }


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
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            item_id TEXT NOT NULL,
            obtained_at TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'drop',
            UNIQUE(user_id, item_id)
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
        INSERT INTO users(id, username, password_hash, created_at)
            VALUES(1, 'mapping-a', 'x', 'now');
        INSERT INTO user_stats(user_id, xp, rank_level, rank_xp, go_rank)
            VALUES(1, 123, 'LV12', 40, '18k');
        INSERT INTO player_appearance(user_id) VALUES(1);
        """
    )
    connection.commit()
    try:
        yield connection
    finally:
        connection.close()


def _build(conn, *, appearance_definitions=CANONICAL_MAPPING_A_DEFINITIONS):
    return build_player_state_read_model(
        conn,
        1,
        level_resolver=lambda rank: int(str(rank)[2:]),
        equipment_definitions=[],
        appearance_definitions=appearance_definitions,
        active_character_keys={"apprentice"},
        spirit_projection_builder=_spirit_projection,
    )


def test_mapping_a_catalog_is_exact_and_slots_are_locked():
    assert MAPPING_A_ID_COUNT == 10
    assert MAPPING_A_IDS == tuple(item.item_id for item in MAPPING_A_CATALOG)
    catalog = validate_mapping_a_catalog(CANONICAL_MAPPING_A_DEFINITIONS)
    assert tuple(catalog) == tuple(item["id"] for item in CANONICAL_MAPPING_A_DEFINITIONS)
    assert {item.item_id: item.slot for item in MAPPING_A_CATALOG} == {
        item["id"]: item["slot"] for item in CANONICAL_MAPPING_A_DEFINITIONS
    }


def test_mapping_a_matches_current_canonical_app_catalog():
    import app as app_module

    validate_mapping_a_catalog(app_module.APPEARANCE_DEFS)
    canonical = {item["id"]: item for item in app_module.APPEARANCE_DEFS}
    assert {item.item_id: canonical[item.item_id]["slot"] for item in MAPPING_A_CATALOG} == {
        item.item_id: item.slot for item in MAPPING_A_CATALOG
    }
    assert all(not app_module.APPEARANCE_EFFECTS.get(item_id, {}) for item_id in MAPPING_A_IDS)
    assert all(
        app_module.PURE_COSMETIC_PRESENTATION_REGISTRY[item_id]["combat_authority"] == "NO"
        for item_id in MAPPING_A_IDS
    )


def test_b028_read_model_activates_mapping_a_gate_with_current_catalog(conn):
    import app as app_module

    for row_id, item_id in enumerate(MAPPING_A_IDS, start=1):
        conn.execute(
            "INSERT INTO player_wardrobe(id,user_id,item_id,obtained_at,source) "
            "VALUES(?,?,?,?,?)",
            (row_id, 1, item_id, "2026-08-28T00:00:00", "controlled_authoritative_fixture"),
        )
    conn.commit()

    model = _build(conn, appearance_definitions=app_module.APPEARANCE_DEFS)
    projection = consume_mapping_a_cosmetics(
        model["cosmetics"], appearance_definitions=app_module.APPEARANCE_DEFS
    )

    assert model["projection_status"] == "OK"
    assert projection.status == READY
    assert projection.owned_ids == MAPPING_A_IDS
    assert projection.selected_ids == ()


def test_consumer_exhaustively_consumes_all_ten_without_auto_equip():
    projection = consume_mapping_a_cosmetics(
        _cosmetics(), appearance_definitions=CANONICAL_MAPPING_A_DEFINITIONS
    )

    assert projection.status == READY
    assert projection.owned_ids == MAPPING_A_IDS
    assert projection.selected_ids == ()
    assert tuple(item["item_id"] for item in projection.items) == MAPPING_A_IDS
    assert all(item["owned"] is True and item["equipped"] is False for item in projection.items)
    assert projection.as_dict()["auto_equip"] is False
    assert projection.as_dict()["combat_power"] == 0


def test_selected_state_is_separate_from_ownership():
    projection = consume_mapping_a_cosmetics(
        _cosmetics(selected_ids=("back_pack",)),
        appearance_definitions=CANONICAL_MAPPING_A_DEFINITIONS,
    )

    assert projection.status == READY
    assert projection.owned_ids == MAPPING_A_IDS
    assert projection.selected_ids == ("back_pack",)
    selected = {item["item_id"]: item for item in projection.items}
    assert selected["back_pack"]["equipped"] is True
    assert all(selected[item_id]["equipped"] is False for item_id in MAPPING_A_IDS if item_id != "back_pack")


def test_authoritative_ownership_acquire_reload_is_persistent_and_deduplicated(conn):
    for row_id, item_id in enumerate(MAPPING_A_IDS, start=1):
        conn.execute(
            "INSERT INTO player_wardrobe(id,user_id,item_id,obtained_at,source) "
            "VALUES(?,?,?,?,?)",
            (row_id, 1, item_id, "2026-08-28T00:00:00", "controlled_authoritative_fixture"),
        )
    conn.commit()
    changes_before_read = conn.total_changes

    first = _build(conn)
    second = _build(conn)
    first_projection = consume_mapping_a_cosmetics(
        first["cosmetics"], appearance_definitions=CANONICAL_MAPPING_A_DEFINITIONS
    )
    second_projection = consume_mapping_a_cosmetics(
        second["cosmetics"], appearance_definitions=CANONICAL_MAPPING_A_DEFINITIONS
    )

    assert first["projection_status"] == "OK"
    assert second["projection_status"] == "OK"
    assert first_projection.owned_ids == MAPPING_A_IDS
    assert second_projection.owned_ids == MAPPING_A_IDS
    assert first_projection.selected_ids == ()
    assert second_projection.selected_ids == ()
    assert conn.total_changes == changes_before_read
    assert conn.execute("SELECT COUNT(*) FROM player_wardrobe WHERE user_id=1").fetchone()[0] == 10
    appearance_row = conn.execute(
        "SELECT outfit_id,hat_id,back_id,title_id,accessory_id,pet_id,aura_id "
        "FROM player_appearance WHERE user_id=1"
    ).fetchone()
    assert all(value is None for value in appearance_row)

    for item_id in MAPPING_A_IDS:
        conn.execute(
            "INSERT OR IGNORE INTO player_wardrobe(user_id,item_id,obtained_at,source) "
            "VALUES(?,?,?,?)",
            (1, item_id, "2026-08-28T00:01:00", "replayed_entitlement"),
        )
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM player_wardrobe WHERE user_id=1").fetchone()[0] == 10
    assert conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='currency_log'").fetchone()[0] == 0


@pytest.mark.parametrize(
    "mutator",
    (
        lambda payload: payload["owned_items"].append({"item_id": "not-a-cosmetic"}),
        lambda payload: payload["owned_items"].append({"slot": "hat"}),
        lambda payload: payload["owned_items"][0].update({"slot": "accessory"}),
        lambda payload: payload.update({"owned_items": "malformed"}),
        lambda payload: payload["selected"].update({"unknown": {"item_id": "hat_cloth"}}),
    ),
)
def test_unknown_missing_wrong_type_and_malformed_payload_fail_closed(mutator):
    payload = _cosmetics()
    mutator(payload)

    projection = consume_mapping_a_cosmetics(
        payload, appearance_definitions=CANONICAL_MAPPING_A_DEFINITIONS
    )

    assert projection.status == INVALID_STORED_STATE
    assert projection.items == ()
    assert projection.as_dict()["auto_equip"] is False
    assert projection.as_dict()["combat_power"] == MAPPING_A_COMBAT_POWER


def test_unknown_and_missing_canonical_catalog_fail_closed():
    incomplete = CANONICAL_MAPPING_A_DEFINITIONS[:-1]
    projection = consume_mapping_a_cosmetics(_cosmetics(), appearance_definitions=incomplete)

    assert projection.status == "AUTHORITY_UNAVAILABLE"
    assert projection.items == ()
    assert projection.reason_code == "MAPPING_A_CATALOG_MISSING"


def test_duplicate_mapping_a_ownership_payload_is_rejected_without_replacement_or_compensation():
    payload = _cosmetics()
    payload["owned_items"].append(dict(payload["owned_items"][0]))

    projection = consume_mapping_a_cosmetics(
        payload, appearance_definitions=CANONICAL_MAPPING_A_DEFINITIONS
    )

    assert projection.status == INVALID_STORED_STATE
    assert projection.duplicate_item_ids == ("back_pack",)
    assert "compensation" not in projection.as_dict()
    assert "replacement_reward" not in projection.as_dict()


def test_wardrobe_read_model_is_the_persisted_authority_and_remains_read_only(conn):
    conn.execute(
        "INSERT INTO player_wardrobe(user_id,item_id,obtained_at,source) VALUES(?,?,?,?)",
        (1, "acc_dragon_pendant", "2026-08-28T00:00:00", "controlled_authoritative_fixture"),
    )
    conn.commit()
    before = conn.total_changes

    model = _build(conn)
    projection = consume_mapping_a_cosmetics(
        model["cosmetics"], appearance_definitions=CANONICAL_MAPPING_A_DEFINITIONS
    )

    assert projection.status == READY
    assert projection.owned_ids == ("acc_dragon_pendant",)
    assert model["cosmetics"]["authority"] == "player_wardrobe_and_player_appearance"
    assert model["cosmetics"]["gameplay_effects_projected"] is False
    assert conn.total_changes == before
