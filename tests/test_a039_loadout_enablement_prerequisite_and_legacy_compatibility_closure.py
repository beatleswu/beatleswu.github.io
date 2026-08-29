"""A039 source contracts for future Loadout enablement and legacy compatibility.

This file is intentionally an audit contract.  It does not enable Loadout or
change the app/runtime authority; it records the current prerequisites so a
future owner-gated enablement cannot silently bypass them.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "a039-loadout-prerequisite-test-secret")
import app as app_module  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
APP_TEXT = (ROOT / "app.py").read_text(encoding="utf-8")
HERO_TEXT = (ROOT / "hero.html").read_text(encoding="utf-8")
INVENTORY_TEXT = (ROOT / "inventory.html").read_text(encoding="utf-8")
OWNERSHIP_TEXT = (ROOT / "equipment_ownership_service.py").read_text(encoding="utf-8")
COMMERCE_TEXT = (ROOT / "equipment_commerce_service.py").read_text(encoding="utf-8")


EXPECTED_IDS = {
    "wooden_sword": ("weapon", {"dmg_bonus": 0.05}),
    "iron_sword": ("weapon", {"dmg_bonus": 0.12}),
    "fox_fang": ("weapon", {"dmg_bonus": 0.20, "fox_dmg_bonus": 0.15}),
    "dragon_claw": ("weapon", {"dmg_bonus": 0.35, "dragon_dmg_bonus": 0.20}),
    "celestial_blade": ("weapon", {"dmg_bonus": 0.60, "combo_multiplier_double": True}),
    "cloth_robe": ("armor", {"player_dmg_reduce": 0.08}),
    "leather_armor": ("armor", {"player_dmg_reduce": 0.15}),
    "fox_pelt": ("armor", {"player_dmg_reduce": 0.25, "xp_bonus": 0.10}),
    "dragon_scale": ("armor", {"player_dmg_reduce": 0.40, "sp_bonus": 30}),
    "void_mantle": ("armor", {"player_dmg_reduce": 0.60, "negate_counter": True}),
    "lucky_stone": ("accessory", {"loot_bonus": 0.10}),
    "xp_amulet": ("accessory", {"xp_bonus": 0.20}),
    "fox_mask": ("accessory", {"quest_xp_bonus": 0.25}),
    "dragon_eye": ("accessory", {"crit_multiplier": 3}),
    "go_stone_black": ("accessory", {"first_question_ace": True}),
}


def _function_source(source: str, name: str) -> str:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(source, node) or ""
    raise AssertionError(f"missing function: {name}")


def test_a039_roster_and_slot_authority_are_exactly_fifteen_server_definitions():
    actual = {
        str(item["id"]): (str(item["slot"]), dict(item.get("effects") or {}))
        for item in app_module.EQUIPMENT_DEFS
    }
    assert actual == EXPECTED_IDS
    assert len(actual) == 15
    assert {slot: sum(value[0] == slot for value in actual.values()) for slot in (
        "weapon", "armor", "accessory"
    )} == {"weapon": 5, "armor": 5, "accessory": 5}
    assert app_module.INVENTORY_ONLY_EQUIPMENT_IDS == {"go_stone_black"}
    assert app_module._FUNCTIONAL_EFFECT_ACTIVE_KEYS["xp_amulet"] == set()
    assert app_module._FUNCTIONAL_EFFECT_ACTIVE_KEYS["go_stone_black"] == set()


def test_a039_server_authority_and_acquisition_boundaries_remain_explicit():
    combat_stats = _function_source(APP_TEXT, "_get_authoritative_combat_stats")
    assert "player_inventory" in combat_stats
    assert "player_appearance.combat_*" in combat_stats
    assert "_safe_active_equipment_effect" in combat_stats
    assert "_get_appearance_effects" not in combat_stats
    assert "equipped=0" in OWNERSHIP_TEXT
    assert "never auto-equipped" in OWNERSHIP_TEXT
    assert "grant_equipment_ownership(" in COMMERCE_TEXT
    assert "ownership.equipped is not False" in COMMERCE_TEXT


def test_a039_loadout_gate_is_default_off_but_legacy_api_fallback_is_visible_prerequisite(
    monkeypatch,
):
    monkeypatch.delenv(app_module.EQUIPMENT_CANONICAL_LOADOUT_FLAG, raising=False)
    assert app_module._equipment_canonical_loadout_enabled() is False
    assert "EQUIPMENT_CANONICAL_LOADOUT_FLAG = 'EQUIPMENT_CANONICAL_LOADOUT_ENABLED'" in APP_TEXT
    equip_route = _function_source(APP_TEXT, "equip_item")
    assert "if _equipment_canonical_loadout_enabled()" in equip_route
    assert "UPDATE player_inventory SET equipped=1" in equip_route
    assert "XP_AMULET_HOLD_FOR_AUTHORITY" in equip_route
    assert "INVENTORY_ONLY_EQUIPMENT_IDS" in equip_route
    assert "const FUNCTIONAL_EQUIPMENT_LOADOUT_ENABLED = false;" in INVENTORY_TEXT
    assert "action.disabled = blockedNewEquip" in INVENTORY_TEXT


def test_a039_legacy_appearance_is_compatibility_only_and_not_hero_equipment_authority():
    appearance = _function_source(APP_TEXT, "_get_appearance_effects")
    review = _function_source(APP_TEXT, "_srs_review_operation")
    assert "compatibility projection" in appearance
    assert "player_inventory" in appearance
    assert "EQUIPMENT_DEFS" in appearance
    assert "_get_appearance_effects" not in review
    assert "const HERO_LEGACY_LOADOUT_EFFECTIVE = false;" in HERO_TEXT
    assert "const COMBAT_STORAGE_KEY = 'hero_combat_gear_v1';" in HERO_TEXT
    for field in (
        "combat_armor", "combat_weapon", "combat_cape", "combat_offhand",
        "combat_hat", "combat_pet", "combat_aura", "combat_acc",
    ):
        assert field in APP_TEXT


def test_a039_cosmetic_spirit_and_permanent_locks_remain_closed():
    assert "Visual only · no combat authority" in HERO_TEXT
    assert "No combat power" in INVENTORY_TEXT
    assert "HERO_LEGACY_LOADOUT_EFFECTIVE = false" in HERO_TEXT
    assert "functional_equipment" in HERO_TEXT
    assert "active_spirit" in HERO_TEXT or "activeSpirit" in HERO_TEXT
    assert "active_effect_details" in INVENTORY_TEXT
    assert "FUNCTIONAL_INVENTORY_ONLY_IDS = new Set(['go_stone_black']);" in INVENTORY_TEXT
