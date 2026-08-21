"""Static Modular 2D Equipment production-contract tests."""

from __future__ import annotations

import json
from pathlib import Path

from tools.validate_rpg_modular_2d_equipment_contract import _validate


ROOT = Path(__file__).resolve().parents[1]
VISIBILITY = ROOT / "docs/planning/rpg_modular_2d_equipment/visibility_matrix.json"
REGISTRY = ROOT / "assets/hero/equipment/wearables/wearable_registry.json"
RENDERER = ROOT / "js/rpg_wave2_wearable_renderer.js"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_modular_2d_contract_validator_passes():
    result = _validate()
    assert result["MODULAR_2D_ARCHITECTURE"] == "PASS"
    assert result["TEMPLATE_COUNT"] == 10
    assert result["VISIBLE_WEARABLE_COUNT"] == 4
    assert result["VISIBLE_IF_SUPPORTED_COUNT"] == 10
    assert result["INVENTORY_ONLY_COUNT"] == 1
    assert result["SIX_CHARACTER_TEMPLATE_QA"] == "PASS_24_OF_24"
    assert result["ITEM_CHARACTER_BESPOKE_REDRAWS"] == 0


def test_visibility_matrix_is_exactly_the_immutable_fifteen_item_set():
    visibility = _json(VISIBILITY)
    registry = _json(REGISTRY)
    expected = {
        "wooden_sword", "iron_sword", "fox_fang", "dragon_claw", "celestial_blade",
        "cloth_robe", "leather_armor", "fox_pelt", "dragon_scale", "void_mantle",
        "lucky_stone", "xp_amulet", "fox_mask", "dragon_eye", "go_stone_black",
    }
    assert {item["equipment_id"] for item in visibility["items"]} == expected
    assert set(registry["equipment"]) == expected
    assert sum(item["wearable_visibility"] == "VISIBLE_WEARABLE" for item in visibility["items"]) == 4
    assert sum(item["wearable_visibility"] == "VISIBLE_IF_SUPPORTED" for item in visibility["items"]) == 10
    assert sum(item["wearable_visibility"] == "INVENTORY_ONLY" for item in visibility["items"]) == 1


def test_inventory_only_projection_fails_closed_without_changing_gameplay_authority():
    visibility = _json(VISIBILITY)
    registry = _json(REGISTRY)
    go_stone = next(item for item in visibility["items"] if item["equipment_id"] == "go_stone_black")
    assert go_stone["wearable_visibility"] == "INVENTORY_ONLY"
    assert go_stone["template_id"] is None
    assert registry["equipment"]["go_stone_black"]["wearable_visibility"] == "INVENTORY_ONLY"
    renderer = RENDERER.read_text(encoding="utf-8")
    assert "item.wearable_visibility === 'INVENTORY_ONLY'" in renderer
    assert "player_inventory" not in renderer
    assert "EQUIPMENT_DEFS" not in renderer
    assert "method: 'POST'" not in renderer


def test_contract_preserves_static_weapon_and_frame_authority():
    registry = _json(REGISTRY)
    assert registry["player_frame"]["id"] == "PLAYER_FRAME_A_STANDARD_CHIBI"
    assert registry["player_frame"]["body_frame_variants"] == 1
    assert registry["provenance"]["static_sword_mode"] == "WAIST_SHEATHED"
    assert registry["provenance"]["hand_held_static_mode"] == "FORBIDDEN"
    assert registry["authority"]["ownership"] == "player_inventory"
    assert registry["authority"]["equipped"] == "player_inventory.equipped"
    assert registry["authority"]["effects"] == "server EQUIPMENT_DEFS"
    assert registry["authority"]["client_combat_authority"] is False
