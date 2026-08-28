"""A038 fresh-master integration and legacy authority retirement contracts."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "app.py").read_text(encoding="utf-8")
HERO = (ROOT / "hero.html").read_text(encoding="utf-8")
INVENTORY = (ROOT / "inventory.html").read_text(encoding="utf-8")


def _function_source(source: str, name: str) -> str:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(source, node) or ""
    raise AssertionError(f"missing function: {name}")


def test_review_gameplay_no_longer_consumes_legacy_appearance_effects():
    review = _function_source(APP, "_srs_review_operation")
    assert "_get_appearance_effects" not in review
    assert "equipment_xp_bonus = _safe_active_equipment_effect" in review
    assert "total_xp_bonus = equipment_xp_bonus" in review
    compatibility = _function_source(APP, "_get_appearance_effects")
    assert "compatibility projection" in compatibility
    assert "player_inventory" in compatibility
    assert "EQUIPMENT_DEFS" in compatibility


def test_a038_keeps_one_server_equipment_authority_and_all_product_gates_closed():
    assert APP.count("'wooden_sword'") >= 1
    assert "_get_authoritative_combat_stats" in APP
    assert "_functional_equipment_payload" in APP
    assert "EQUIPMENT_CANONICAL_LOADOUT_ENABLED" in APP
    assert "CANONICAL_COIN_SHOP_PURCHASE_ENABLED" in APP
    assert "go_stone_black" in APP
    assert 'data-loadout-effective="off"' in HERO
    assert "const FUNCTIONAL_EQUIPMENT_LOADOUT_ENABLED = false;" in INVENTORY


def test_a038_preserves_cosmetic_and_functional_separation():
    assert "functional_equipment" in HERO
    assert "style_equipment" in APP
    assert "Visual only · no combat authority" in HERO
    assert "No combat power" in INVENTORY
    assert "player_wardrobe" in APP
    assert "player_inventory" in APP
