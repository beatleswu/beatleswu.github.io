"""G114 EQ-F legit owned items survive read-only presentation with loadout OFF."""
import sqlite3
import sys
import types
import threading

from equipment_portfolio_registry import build_canonical_equipment_defs
from player_state_read_model import _canonical_equipment_catalog, _project_equipment


def _conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE player_inventory (id INTEGER PRIMARY KEY, "
        "user_id INTEGER NOT NULL, equip_id TEXT NOT NULL, equipped INTEGER NOT NULL)"
    )
    return conn


def test_locked_eqf_items_are_not_unknown_when_loadout_off(monkeypatch):
    defs = build_canonical_equipment_defs((
        {"id": "iron_sword", "slot": "weapon", "name": "Iron Sword"},
    ))
    fake_app = types.SimpleNamespace(
        CANONICAL_EQUIPMENT_DEFS=defs,
        EQUIPMENT_DEFS=[{"id": "iron_sword", "slot": "weapon"}],
        INVENTORY_ONLY_EQUIPMENT_IDS=frozenset(),
        _FUNCTIONAL_EFFECT_ACTIVE_KEYS={},
        EQUIPMENT_CANONICAL_LOADOUT_ENABLED=False,
        _auth_fail_lock=threading.Lock(),
        _auth_fail_log={},
    )
    monkeypatch.setitem(sys.modules, "app", fake_app)
    catalog, _, _ = _canonical_equipment_catalog(None)
    assert "bamboo_shadow_blade" in catalog
    assert "jade_river_bead" in catalog
    with _conn() as conn:
        conn.execute(
            "INSERT INTO player_inventory(user_id,equip_id,equipped) VALUES(?,?,?)",
            (99, "bamboo_shadow_blade", 1),
        )
        conn.execute(
            "INSERT INTO player_inventory(user_id,equip_id,equipped) VALUES(?,?,?)",
            (99, "jade_river_bead", 1),
        )
        before = conn.total_changes
        projected, _ = _project_equipment(conn, 99, equipment_definitions=None)
        assert projected["projection_status"] == "OK"
        assert projected["invalid_item_ids"] == []
        assert {item["item_id"] for item in projected["owned_items"]} == {
            "bamboo_shadow_blade", "jade_river_bead"
        }
        assert conn.total_changes == before


def test_unknown_equipment_still_invalid_and_never_deleted(monkeypatch):
    defs = build_canonical_equipment_defs(())
    monkeypatch.setitem(sys.modules, "app", types.SimpleNamespace(
        CANONICAL_EQUIPMENT_DEFS=defs,
        INVENTORY_ONLY_EQUIPMENT_IDS=frozenset(),
        _FUNCTIONAL_EFFECT_ACTIVE_KEYS={},
        _auth_fail_lock=threading.Lock(),
        _auth_fail_log={},
    ))
    with _conn() as conn:
        conn.execute(
            "INSERT INTO player_inventory(user_id,equip_id,equipped) VALUES(?,?,?)",
            (99, "truly_unknown_new_item", 0),
        )
        before = conn.total_changes
        projection, _ = _project_equipment(conn, 99, equipment_definitions=None)
        assert projection["projection_status"] == "INVALID_STORED_STATE"
        assert projection["invalid_item_ids"] == ["truly_unknown_new_item"]
        assert conn.total_changes == before
