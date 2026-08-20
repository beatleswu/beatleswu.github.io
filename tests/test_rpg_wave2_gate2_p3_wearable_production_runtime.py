"""Wave 2 Gate 2 P3 functional-equipment wearable runtime contracts."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "assets/hero/equipment/wearables/wearable_registry.json"
REPORT = ROOT / "docs/planning/rpg_wave2_gate2_p3_wearable_runtime_manifest.json"
RUNTIME = ROOT / "js/rpg_wave2_wearable_renderer.js"
APP = ROOT / "app.py"
HERO = ROOT / "hero.html"
PROFILE = ROOT / "profile.html"
INVENTORY = ROOT / "inventory.html"

CHARACTERS = {
    "apprentice", "mage", "paladin", "trail_apprentice", "night_runner",
    "constellation_apprentice",
}
EQUIPMENT = {
    "wooden_sword": "weapon",
    "iron_sword": "weapon",
    "fox_fang": "weapon",
    "dragon_claw": "weapon",
    "celestial_blade": "weapon",
    "cloth_robe": "armor",
    "leather_armor": "armor",
    "fox_pelt": "armor",
    "dragon_scale": "armor",
    "void_mantle": "armor",
    "lucky_stone": "accessory",
    "xp_amulet": "accessory",
    "fox_mask": "accessory",
    "dragon_eye": "accessory",
    "go_stone_black": "accessory",
}


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_p3_registry_has_exact_frame_characters_and_immutable_items():
    registry = _json(REGISTRY)
    report = _json(REPORT)
    assert report["task_id"] == "RPG_WAVE2_GATE2_P3_WEARABLE_PRODUCTION_RUNTIME_001"
    assert registry["player_frame"] == {
        "id": "PLAYER_FRAME_A_STANDARD_CHIBI",
        "canvas": [1056, 1408],
        "body_frame_variants": 1,
    }
    assert set(registry["characters"]) == CHARACTERS
    assert set(registry["equipment"]) == set(EQUIPMENT)
    assert report["counts"] == {
        "functional_equipment_total": 15,
        "wearable_ready": 0,
        "wearable_ready_with_mask": 15,
        "wearable_blocked": 0,
        "universal_runtime_overlays": 15,
        "body_frame_variants": 1,
        "character_reusable_masks": 6,
        "item_character_bespoke_redraws": 0,
    }
    assert report["player_frame"] == "PLAYER_FRAME_A_STANDARD_CHIBI"


def test_registry_preserves_authority_and_static_weapon_decision():
    registry = _json(REGISTRY)
    assert registry["authority"] == {
        "ownership": "player_inventory",
        "equipped": "player_inventory.equipped",
        "effects": "server EQUIPMENT_DEFS",
        "character": "player_appearance.character_key",
        "presentation_only": True,
        "client_combat_authority": False,
        "visual_wearable_gameplay_authority": False,
    }
    assert registry["layer_order"] == [
        "BACK_WEAPON", "BACK_BODY", "CHARACTER_BASE", "TORSO_ARMOR",
        "FRONT_BODY", "FRONT_ACCESSORY", "HEAD_FACE", "HAIR_FRONT_MASK",
    ]
    assert registry["equipment"]["iron_sword"]["wearable_class"] == "WEAPON_WAIST"
    assert registry["equipment"]["iron_sword"]["anchor"] == "waist_right"
    assert registry["equipment"]["iron_sword"]["layer"] == "BACK_WEAPON"
    assert registry["equipment"]["fox_mask"]["wearable_class"] == "HEAD_FACE"
    assert registry["equipment"]["dragon_claw"]["wearable_class"] == "FOREARM_OR_HAND_GEAR"
    assert registry["equipment"]["celestial_blade"]["wearable_class"] == "WEAPON_BACK"


def test_all_runtime_overlays_and_masks_are_true_alpha_and_normalized():
    registry = _json(REGISTRY)
    for item_id, item in registry["equipment"].items():
        overlay = ROOT / item["asset"].lstrip("/")
        assert overlay.is_file(), item_id
        with Image.open(overlay) as image:
            assert image.size == (1056, 1408), item_id
            rgba = image.convert("RGBA")
            assert rgba.getchannel("A").getbbox() is not None, item_id
            for red, green, blue, alpha in rgba.getdata():
                if alpha == 0:
                    assert (red, green, blue) == (0, 0, 0), item_id
    for character, data in registry["characters"].items():
        mask = ROOT / data["hair_front_mask"].lstrip("/")
        assert mask.is_file(), character
        with Image.open(mask) as image:
            assert image.size == (1056, 1408)
            assert image.mode == "RGBA"
            assert image.getchannel("A").getbbox() is not None


def test_fit_matrices_are_deterministic_review_artifacts():
    matrix_root = ROOT / "docs/planning/rpg_wave2_gate2_p3_wearable_fit_matrices"
    expected = {
        "P3_WEAPON_FIT_MATRIX.png",
        "P3_ARMOR_FIT_MATRIX.png",
        "P3_ACCESSORY_FIT_MATRIX.png",
        "P3_FULL_LOADOUT_QA.png",
    }
    assert {path.name for path in matrix_root.glob("*.png")} == expected
    for path in matrix_root.glob("*.png"):
        with Image.open(path) as image:
            assert image.mode == "RGB"
            assert image.width >= 1200
            assert image.height >= 300


def test_server_projection_is_read_only_and_keeps_inventory_as_authority():
    app = APP.read_text(encoding="utf-8")
    assert "def _functional_equipment_presentation_projection" in app
    assert "SELECT equip_id FROM player_inventory WHERE user_id=? AND equipped=1 ORDER BY id" in app
    assert "'functional_equipment': functional_equipment" in app
    assert "'equipment_id': equip['id']" in app
    assert "'presentation_only': True" in app
    assert "EQUIPMENT_DEFS" in app
    projection = app.split("def _functional_equipment_presentation_projection", 1)[1].split("# ── 掉落", 1)[0]
    assert "INSERT INTO player_inventory" not in projection
    assert "UPDATE player_inventory" not in projection
    assert "DELETE FROM player_inventory" not in projection


def test_runtime_renderer_cannot_become_gameplay_or_inventory_authority():
    runtime = RUNTIME.read_text(encoding="utf-8")
    assert "wearable_registry.json" in runtime
    assert "server_equipped_projection" in runtime
    assert "gameplayAuthority = 'none'" in runtime
    assert "method: 'POST'" not in runtime
    assert "player_inventory" not in runtime
    assert "EQUIPMENT_DEFS" not in runtime
    assert "localStorage" not in runtime
    assert "unequip" not in runtime


def test_hero_profile_and_backpack_share_the_safe_renderer():
    hero = HERO.read_text(encoding="utf-8")
    profile = PROFILE.read_text(encoding="utf-8")
    inventory = INVENTORY.read_text(encoding="utf-8")
    for page in (hero, profile, inventory):
        assert "/js/rpg_wave2_wearable_renderer.js" in page
    assert "char-functional-wearable-stage" in hero
    assert "pv-functional-wearable-stage" in hero
    assert "renderFunctionalWearableProjection" in hero
    assert "profile-wearable-stage" in profile
    assert "d.functional_equipment || []" in profile
    assert "functional-wearable-preview" in inventory
    assert "functionalPreviewProfile" in inventory
    assert "fetch('/api/player/inventory/equip'" in inventory
    assert "renderFunctionalWearablePreview();" in inventory


def test_equipment_and_character_selection_authority_are_unchanged():
    app = APP.read_text(encoding="utf-8")
    assert "FUNCTIONAL_EQUIPMENT_ART" in app
    assert "def equip_item()" in app
    assert "UPDATE player_inventory SET equipped=0" in app
    assert "UPDATE player_inventory SET equipped=1" in app
    assert "def skills_character()" in app
    # P1 candidate characters remain presentation-supported but not added to
    # the server selection authority in this task.
    selection_block = app.split("VALID_CHARACTER_KEYS = {", 1)[1].split("}\n\n@app.route('/api/skills/character'", 1)[0]
    for candidate in ("trail_apprentice", "night_runner", "constellation_apprentice"):
        assert candidate not in selection_block


def test_p2_artitecture_is_reused_without_bespoke_item_character_redraws():
    report = _json(REPORT)
    assert report["counts"]["item_character_bespoke_redraws"] == 0
    assert report["counts"]["body_frame_variants"] == 1
    assert report["counts"]["character_reusable_masks"] == 6
    assert report["equipment"]["dragon_scale"]["qa"] == "PASS_WITH_REUSABLE_MASK"
    assert report["equipment"]["fox_mask"]["qa"] == "PASS_WITH_REUSABLE_MASK"
    assert report["equipment"]["iron_sword"]["production_status"] == "READY_WITH_REUSABLE_MASK"


def test_no_forbidden_domain_or_deployment_scope_was_added_to_runtime_files():
    runtime = RUNTIME.read_text(encoding="utf-8")
    for forbidden in ("combat formulas", "damage", "drop rates", "DB migration", "deploy", "payment"):
        assert forbidden not in runtime.lower()
