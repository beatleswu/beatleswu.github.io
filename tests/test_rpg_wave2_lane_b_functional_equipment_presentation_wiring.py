"""Lane B functional-equipment presentation wiring proof.

These contracts exercise the read-only bridge from server-owned inventory to
Hero/Preview presentation.  They intentionally do not add an authority,
change combat, or require PostgreSQL.
"""

import os
import sqlite3
import struct
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "rpg-wave2-lane-b-functional-presentation-test-secret")
import app as app_module  # noqa: E402
from migrations.equipment_canonical_slot_v1 import upgrade as upgrade_b033  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
HERO = (ROOT / "hero.html").read_text(encoding="utf-8")
APP = (ROOT / "app.py").read_text(encoding="utf-8")

FUNCTIONAL_IDS = {
    "wooden_sword",
    "iron_sword",
    "fox_fang",
    "dragon_claw",
    "celestial_blade",
    "cloth_robe",
    "leather_armor",
    "fox_pelt",
    "dragon_scale",
    "void_mantle",
    "lucky_stone",
    "xp_amulet",
    "fox_mask",
    "dragon_eye",
    "go_stone_black",
}
FULL_BODY_IDS = FUNCTIONAL_IDS - {"go_stone_black"}
WEAPON_IDS = {
    "wooden_sword",
    "iron_sword",
    "fox_fang",
    "dragon_claw",
    "celestial_blade",
}
ARMOR_IDS = {
    "cloth_robe",
    "leather_armor",
    "fox_pelt",
    "dragon_scale",
    "void_mantle",
}
ACCESSORY_IDS = {"lucky_stone", "xp_amulet", "fox_mask", "dragon_eye"}


class _DbContext:
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


def _create_inventory_db(path, *, post_b033=False):
    rows = [
        (index, 1, item_id, 0, f"2026-08-{index:02d}", "drop")
        for index, item_id in enumerate(sorted(FULL_BODY_IDS), start=1)
    ]
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE player_inventory(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                equip_id TEXT NOT NULL,
                equipped INTEGER NOT NULL DEFAULT 0,
                obtained_at TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'drop'
            )
            """
        )
        if post_b033:
            upgrade_b033(conn, equipment_defs=app_module.EQUIPMENT_DEFS)
            conn.executemany(
                """
                INSERT INTO player_inventory(
                    id,user_id,equip_id,equipped,canonical_slot,obtained_at,source
                ) VALUES(?,?,?,?,?,?,?)
                """,
                [
                    (
                        row[0], row[1], row[2], row[3],
                        app_module._EQUIP_MAP.get(row[2], {}).get("slot")
                        if row[3]
                        else None,
                        row[4], row[5],
                    )
                    for row in rows
                ],
            )
        else:
            conn.executemany(
                """
                INSERT INTO player_inventory(
                    id,user_id,equip_id,equipped,obtained_at,source
                ) VALUES(?,?,?,?,?,?)
                """,
                rows,
            )


def _client_for(path, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: _DbContext(path))
    app_module.app.config.update(TESTING=True)
    client = app_module.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 1
        session["username"] = "wave2-lane-b-functional-presentation-test"
    return client


def _png_dimensions_and_color_type(path):
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert data[12:16] == b"IHDR"
    width, height, bit_depth, color_type = struct.unpack(">IIBB", data[16:26])
    return width, height, bit_depth, color_type


def test_registry_covers_exactly_fourteen_full_body_items_and_inventory_only_stone():
    registry = app_module.FUNCTIONAL_EQUIPMENT_PRESENTATION_REGISTRY
    assert set(registry) == FUNCTIONAL_IDS
    assert len(registry) == 15

    for item_id in FULL_BODY_IDS:
        record = registry[item_id]
        assert record["presentation_mode"] == "FULL_BODY_OVERLAY"
        assert record["full_body_required"] is True
        assert record["asset_path"] == (
            f"/assets/hero/equipment/wearables/overlays/{item_id}.png"
        )
        asset = ROOT / record["asset_path"].lstrip("/")
        assert asset.is_file(), item_id
        assert _png_dimensions_and_color_type(asset) == (1056, 1408, 8, 6)
        assert app_module.FUNCTIONAL_EQUIPMENT_ART[item_id]["fallback"] == (
            "NEUTRAL_FUNCTIONAL_ICON"
        )

    stone = registry["go_stone_black"]
    assert stone["presentation_mode"] == "ICON_ONLY"
    assert stone["presentation_family"] == "INVENTORY_ONLY"
    assert stone["full_body_required"] is False
    assert stone["asset_path"] is None
    assert not (ROOT / "assets/hero/equipment/wearables/overlays/go_stone_black.png").exists()


def test_weapon_armor_and_accessory_mappings_preserve_locked_families():
    registry = app_module.FUNCTIONAL_EQUIPMENT_PRESENTATION_REGISTRY
    assert len(WEAPON_IDS) == 5
    assert all(registry[item_id]["weapon_family"] == "ONE_HAND_SWORD" for item_id in WEAPON_IDS)
    assert all(registry[item_id]["presentation_family"] == "ONE_HAND_SWORD" for item_id in WEAPON_IDS)
    assert all(registry[item_id]["presentation_mode"] == "FULL_BODY_OVERLAY" for item_id in WEAPON_IDS)
    assert all(registry[item_id]["presentation_family"] == "ARMOR_OVERLAY" for item_id in ARMOR_IDS)
    assert all(registry[item_id]["presentation_mode"] == "FULL_BODY_OVERLAY" for item_id in ARMOR_IDS)
    assert all(registry[item_id]["presentation_family"] == "ACCESSORY_OVERLAY" for item_id in ACCESSORY_IDS)
    assert all(registry[item_id]["presentation_mode"] == "FULL_BODY_OVERLAY" for item_id in ACCESSORY_IDS)


def test_payload_exposes_presentation_metadata_without_client_combat_authority():
    registry = app_module.FUNCTIONAL_EQUIPMENT_PRESENTATION_REGISTRY
    for item_id in FUNCTIONAL_IDS:
        payload = app_module._functional_equipment_payload(app_module._EQUIP_MAP[item_id])
        presentation = payload["presentation"]
        assert payload["functional_equipment"] is True
        assert payload["style_equipment"] is False
        assert presentation["presentation_only"] is True
        assert presentation["fallback"] == "NEUTRAL_FUNCTIONAL_ICON"
        assert presentation["mode"] == registry[item_id]["presentation_mode"]
        assert presentation["full_body_required"] is bool(
            registry[item_id]["full_body_required"]
        )
        assert "effects" not in presentation
        assert "damage" not in presentation
        assert "combat_stats" not in presentation


def test_hero_preview_projection_is_server_driven_and_fail_closed():
    assert 'id="char-functional-wearable-back"' in HERO
    assert 'id="char-functional-wearable-front"' in HERO
    assert 'id="pv-functional-wearable-back"' in HERO
    assert 'id="pv-functional-wearable-front"' in HERO
    assert "FUNCTIONAL_FULL_BODY_EQUIPMENT_IDS" in HERO
    full_body_block = HERO[HERO.index("const FUNCTIONAL_FULL_BODY_EQUIPMENT_IDS"):HERO.index("const FUNCTIONAL_WEARABLE_ASSET_ROOT")]
    assert "go_stone_black" not in full_body_block
    assert "presentation.mode !== 'FULL_BODY_OVERLAY'" in HERO
    assert "presentation.full_body_required !== true" in HERO
    assert "item.functional_equipment !== true || item.equipped !== true" in HERO
    assert "onerror=null;this.hidden=true;this.dataset.presentationState='fallback'" in HERO
    assert "renderFunctionalWearableProjection()" in HERO
    assert "fetch('/api/player/inventory'" in HERO
    assert "localStorage" not in HERO[HERO.index("function functionalWearableDescriptor"):HERO.index("const FUNCTIONAL_SLOT_LABELS")]
    assert "POST" not in HERO[HERO.index("function functionalWearableDescriptor"):HERO.index("const FUNCTIONAL_SLOT_LABELS")]


def test_reload_rehydrates_each_equipped_item_and_restores_same_presentation(tmp_path, monkeypatch):
    path = tmp_path / "functional-presentation.sqlite"
    _create_inventory_db(path, post_b033=True)
    monkeypatch.setenv(app_module.EQUIPMENT_CANONICAL_LOADOUT_FLAG, "1")
    client = _client_for(path, monkeypatch)
    registry = app_module.FUNCTIONAL_EQUIPMENT_PRESENTATION_REGISTRY

    rows = sorted(
        (row[0], row[1])
        for row in sqlite3.connect(path).execute(
            "SELECT id,equip_id FROM player_inventory WHERE user_id=1"
        )
    )
    assert len(rows) == 14

    for inv_id, item_id in rows:
        response = client.post(
            "/api/player/inventory/equip",
            json={"inv_id": inv_id, "action": "equip"},
        )
        if item_id == "xp_amulet":
            assert response.status_code == 400
            assert response.get_json()["error"] == "XP_AMULET_HOLD_FOR_AUTHORITY"
            reloaded_client = _client_for(path, monkeypatch)
            by_item = {
                item["item_id"]: item
                for item in reloaded_client.get("/api/player/inventory").get_json()
            }
            assert by_item[item_id]["equipped"] is False
            continue
        assert response.status_code == 200
        assert response.get_json()["item_id"] == item_id

        reloaded_client = _client_for(path, monkeypatch)
        inventory_response = reloaded_client.get("/api/player/inventory")
        assert inventory_response.status_code == 200
        by_item = {item["item_id"]: item for item in inventory_response.get_json()}
        current = by_item[item_id]
        assert current["equipped"] is True
        assert current["presentation"]["mode"] == "FULL_BODY_OVERLAY"
        assert current["presentation"]["full_body_required"] is True
        assert current["presentation"]["asset"] == (
            f"/assets/hero/equipment/wearables/overlays/{item_id}.png"
        )
        assert registry[item_id]["presentation_mode"] == current["presentation"]["mode"]


def test_responsive_overlay_contract_has_no_new_surface_or_authority_path():
    css = HERO[HERO.index(".functional-wearable-stack {"):HERO.index("/* Premium 裝備光效")]
    assert "position: absolute" in css
    assert "inset: 0" in css
    assert "width: 100%" in css
    assert "height: 100%" in css
    assert "pointer-events: none" in css
    assert "@media (min-width: 701px) and (max-width: 1180px)" in HERO
    assert "orientation: portrait" in HERO
    assert "@media (max-width: 700px)" in HERO
    assert "player_inventory" in APP
    assert "EQUIPMENT_DEFS" in APP
