"""A051 wooden_sword Backpack -> Equip -> Hero vertical-slice contracts.

The source keeps the shipped Loadout gate closed.  The server-side flag is
enabled only in disposable SQLite fixtures below so the existing canonical
equip route and the existing Hero projection can be proven together.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

os.environ.setdefault("SECRET_KEY", "a051-wooden-sword-vertical-slice-test-secret")

import app as app_module  # noqa: E402
from migrations.equipment_canonical_slot_v1 import upgrade as upgrade_b033  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = (ROOT / "inventory.html").read_text(encoding="utf-8")
HERO = (ROOT / "hero.html").read_text(encoding="utf-8")
RENDERER = (ROOT / "js" / "rpg_wave2_wearable_renderer.js").read_text(
    encoding="utf-8"
)
WOODEN_SWORD_OVERLAY = (
    ROOT / "assets" / "hero" / "equipment" / "wearables" / "overlays" / "wooden_sword.png"
)
WOODEN_SWORD_ICON = ROOT / "assets" / "hero" / "equipment" / "functional" / "wooden_sword.svg"


class _DbContext:
    def __init__(self, path: Path):
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


def _create_db(path: Path) -> None:
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
        upgrade_b033(conn, equipment_defs=app_module.EQUIPMENT_DEFS)


def _grant(path: Path, equip_id: str):
    with sqlite3.connect(path) as conn:
        result = app_module.grant_equipment_ownership(
            conn,
            1,
            equip_id,
            "drop",
            equipment_defs=app_module.EQUIPMENT_DEFS,
        )
        conn.commit()
        return result


def _client(path: Path, monkeypatch, *, loadout_enabled: bool):
    monkeypatch.setenv(
        app_module.EQUIPMENT_CANONICAL_LOADOUT_FLAG,
        "1" if loadout_enabled else "0",
    )
    monkeypatch.setattr(app_module, "get_db", lambda: _DbContext(path))
    app_module.app.config.update(TESTING=True)
    client = app_module.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 1
        session["username"] = "a051-wooden-sword"
    return client


def _inventory_row(path: Path, row_id: int):
    with sqlite3.connect(path) as conn:
        return conn.execute(
            "SELECT equip_id,equipped,canonical_slot FROM player_inventory WHERE id=?",
            (row_id,),
        ).fetchone()


def test_wooden_sword_acquisition_stays_unequipped_and_disabled_server_path_is_noop(
    tmp_path: Path, monkeypatch
):
    path = tmp_path / "a051-disabled.sqlite"
    _create_db(path)
    wooden = _grant(path, "wooden_sword")
    client = _client(path, monkeypatch, loadout_enabled=False)

    backpack = client.get("/api/player/inventory")
    assert backpack.status_code == 200
    item = next(entry for entry in backpack.get_json() if entry["item_id"] == "wooden_sword")
    assert item["owned_quantity"] == 1
    assert item["equipped"] is False

    blocked = client.post(
        "/api/player/inventory/equip",
        json={"inv_id": wooden.row_id, "action": "equip"},
    )
    assert blocked.status_code == 409
    assert blocked.get_json() == {"error": "LOADOUT_DISABLED"}
    assert _inventory_row(path, wooden.row_id) == ("wooden_sword", 0, "weapon")


def test_enabled_fixture_uses_canonical_route_projects_wooden_sword_and_unequips(
    tmp_path: Path, monkeypatch
):
    path = tmp_path / "a051-enabled.sqlite"
    _create_db(path)
    wooden = _grant(path, "wooden_sword")
    iron = _grant(path, "iron_sword")
    client = _client(path, monkeypatch, loadout_enabled=True)

    equipped = client.post(
        "/api/player/inventory/equip",
        json={"inv_id": wooden.row_id, "action": "equip"},
    )
    assert equipped.status_code == 200
    assert equipped.get_json() == {
        "ok": True,
        "item_id": "wooden_sword",
        "inv_id": wooden.row_id,
        "equipped": True,
        "canonical_slot": "weapon",
        "changed": True,
        "target_ownership_row_id": wooden.row_id,
    }

    backpack = client.get("/api/player/inventory")
    by_id = {entry["item_id"]: entry for entry in backpack.get_json()}
    assert by_id["wooden_sword"]["equipped"] is True
    assert by_id["iron_sword"]["equipped"] is False

    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        projection = app_module._functional_equipment_presentation_projection(conn, 1)
        stats = app_module._get_authoritative_combat_stats(conn, 1)
    assert projection == [
        {
            "equipment_id": "wooden_sword",
            "slot": "weapon",
            "equipped": True,
            "presentation_only": True,
        }
    ]
    assert stats["attack_bonus"] == pytest.approx(0.05)
    assert app_module._calc_damage(5, 1000, attack_bonus=stats["attack_bonus"]) == 84

    # A fresh request is the reload/hydration proof: no client-local state is
    # involved in reconstructing the equipped item.
    reloaded = _client(path, monkeypatch, loadout_enabled=True)
    reloaded_item = next(
        entry
        for entry in reloaded.get("/api/player/inventory").get_json()
        if entry["item_id"] == "wooden_sword"
    )
    assert reloaded_item["equipped"] is True

    unequipped = reloaded.post(
        "/api/player/inventory/equip",
        json={"inv_id": wooden.row_id, "action": "unequip"},
    )
    assert unequipped.status_code == 200
    assert unequipped.get_json()["equipped"] is False

    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        assert app_module._functional_equipment_presentation_projection(conn, 1) == []
        final_stats = app_module._get_authoritative_combat_stats(conn, 1)
    assert final_stats["attack_bonus"] == 0
    assert app_module._calc_damage(5, 1000, attack_bonus=final_stats["attack_bonus"]) == 80
    assert _inventory_row(path, wooden.row_id) == ("wooden_sword", 0, "weapon")


def test_inventory_enabled_path_is_server_gated_and_reuses_authoritative_endpoint():
    """The shipped UI gate stays closed and is never a second authority.

    The gate used to be the literal ``FUNCTIONAL_EQUIPMENT_LOADOUT_ENABLED =
    false``. That hard-coded copy meant enabling the server flag alone could
    not restore player access, so it was replaced by a read-only capability the
    server projects on /api/auth/me. The invariant this test protects is
    unchanged and now strictly stronger: the client still ships closed, still
    cannot open itself, and still reuses the authoritative endpoint.
    """
    # Ships closed, and only the server can open it.
    assert "let functionalEquipmentLoadoutCapability = false;" in INVENTORY
    assert "!!(me && me.equipment_loadout_enabled === true)" in INVENTORY
    assert "FUNCTIONAL_EQUIPMENT_LOADOUT_ENABLED" not in INVENTORY
    assert "window.__GO_EQUIPMENT_LOADOUT_TEST_MODE__ === true" in INVENTORY
    assert "window.__GO_EQUIPMENT_LOADOUT_TEST_OVERRIDE__ === true" in INVENTORY
    assert "fetch('/api/player/inventory/equip'" in INVENTORY
    assert "body:JSON.stringify({ inv_id:item.inv_id, action })" in INVENTORY
    assert "await loadFunctionalEquipment(item.inv_id)" in INVENTORY
    assert "LOADOUT_DISABLED" not in INVENTORY
    assert "localStorage" not in INVENTORY
    # The control is now disabled by a strictly wider condition: the Loadout
    # capability being off, OR the canonical server saying the item is not
    # equippable at all (go_stone_black / xp_amulet).
    assert "const blocked = notEquippable || blockedNewEquip;" in INVENTORY
    assert "action.disabled = blocked;" in INVENTORY
    assert "action === 'equip' && !functionalEquipmentLoadoutEnabled()" in INVENTORY


def test_hero_projection_consumes_server_equipped_wooden_sword_mapping_only():
    assert WOODEN_SWORD_ICON.is_file()
    assert WOODEN_SWORD_OVERLAY.is_file()
    registry = app_module.FUNCTIONAL_EQUIPMENT_PRESENTATION_REGISTRY["wooden_sword"]
    assert registry["presentation_mode"] == "FULL_BODY_OVERLAY"
    assert registry["presentation_family"] == "ONE_HAND_SWORD"
    assert registry["presentation_layer"] == "BACK_WEAPON"
    assert registry["wearable_class"] == "WEAPON_WAIST"
    assert registry["asset_path"] == "/assets/hero/equipment/wearables/overlays/wooden_sword.png"

    hydration = HERO[HERO.index("async function hydrateAuthoritativeHeroPresentation"):]
    assert "fetch('/api/player/inventory'" in hydration
    assert "normalizeHeroFunctionalEquipment(inventory)" in hydration
    assert "renderFunctionalWearableProjection();" in hydration
    assert "item.functional_equipment !== true || item.equipped !== true" in HERO
    assert "renderer.renderSafe(stage" in HERO
    assert "localStorage.getItem(COMBAT_STORAGE_KEY" not in HERO
    assert "server_equipped_projection" in RENDERER
