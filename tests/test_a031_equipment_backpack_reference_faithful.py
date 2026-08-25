"""Static contracts for the A031 reference-faithful E10 presentation slice."""

import json
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = (ROOT / "inventory.html").read_text(encoding="utf-8")
CSS = (ROOT / "css/e10/backpack.css").read_text(encoding="utf-8")
DOC = (ROOT / "docs/planning/art/A031_EQUIPMENT_BACKPACK_REFERENCE_FAITHFUL_ART_PRODUCTION_001.md").read_text(encoding="utf-8")
MANIFEST_PATH = ROOT / "docs/planning/art/A031_EQUIPMENT_BACKPACK_ASSET_MANIFEST_001.json"


def _manifest():
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_manifest_closes_current_equipment_and_backpack_art():
    manifest = _manifest()
    functional = manifest["functional_equipment"]
    backpack = manifest["backpack_items"]
    assert len(functional) == 15
    assert len(backpack) == 24
    assert manifest["runtime_visible_item_counts"]["total_current_items"] == 39
    assert {item["functional_slot"] for item in functional} == {"weapon", "armor", "accessory"}
    assert {item["item_id"] for item in functional if item["functional_slot"] == "weapon"} == {
        "wooden_sword", "iron_sword", "fox_fang", "dragon_claw", "celestial_blade"
    }
    assert {item["item_id"] for item in functional if item["functional_slot"] == "armor"} == {
        "cloth_robe", "leather_armor", "fox_pelt", "dragon_scale", "void_mantle"
    }
    assert {item["item_id"] for item in functional if item["functional_slot"] == "accessory"} == {
        "lucky_stone", "xp_amulet", "fox_mask", "dragon_eye", "go_stone_black"
    }
    assert next(item for item in functional if item["item_id"] == "xp_amulet")["equip_allowed"] is False
    go_stone = next(item for item in functional if item["item_id"] == "go_stone_black")
    assert go_stone["canonical_class"] == "TROPHY"
    assert go_stone["hero_overlay_requirement"] == "INVENTORY_ONLY"
    assert all(item["asset_status"] == "EXISTING_APPROVED" for item in functional + backpack)
    assert manifest["quality_contract"]["missing_final_item_art"] == []


def test_manifest_asset_paths_exist_and_are_not_reference_screenshot_dependencies():
    manifest = _manifest()
    records = manifest["functional_equipment"] + manifest["backpack_items"]
    for record in records:
        assert not record["current_asset_path"].lower().endswith((".jpg", ".jpeg", ".png")) or \
            "/hero/equipment/wearables/overlays/" in record["current_asset_path"]
        assert (ROOT / record["current_asset_path"].lstrip("/")).is_file(), record["item_id"]
    for record in manifest["functional_equipment"]:
        overlay = record["hero_overlay_asset_path"]
        if overlay:
            assert (ROOT / overlay.lstrip("/")).is_file(), record["item_id"]
    assert "RUNTIME_REFERENCES_REVIEW_SCREENSHOT" not in manifest


def test_e10_composition_keeps_existing_authorities_and_uses_real_art_mapping():
    for marker in (
        'data-a031-equipment-board',
        'id="a031-loadout-grid"',
        'id="functional-wearable-preview"',
        'id="functional-equipment-detail"',
        'id="functional-equipment-grid"',
        'const A031_BACKPACK_ART = Object.freeze({',
        'data-art-status="${backpackArt(item).status}"',
        'fetch(\'/api/player/inventory\'',
        'fetch(\'/api/player/inventory/equip\'',
        'fetch(\'/api/shop/catalog\'',
        'fetch(\'/api/pet/status\'',
        'player_inventory',
    ):
        assert marker in INVENTORY
    assert "${item.icon || '🎒'}" not in INVENTORY
    assert "document.getElementById('e10-backpack-dialog-icon').textContent" not in INVENTORY
    assert "chibi_apprentice_normalized.webp" not in INVENTORY
    assert "function functionalEquipmentCanEquip(item)" in INVENTORY
    assert "item.item_id === 'go_stone_black'" in INVENTORY
    assert "item.item_id === 'xp_amulet'" in INVENTORY


def test_bright_adventure_and_responsive_contract_are_scoped_to_e10():
    for token in (
        "--a031-blue: #1e6fc7",
        "--a031-teal: #39c9b6",
        "--a031-yellow: #f6c957",
        "--a031-cream: #fff4d8",
        "--a031-sky: #ddf2ff",
        "--a031-navy: #173653",
        ".a031-equipment-board",
        ".a031-loadout-grid",
        ".a031-hero-art-scene",
        ".a031-functional-collection",
        "grid-template-columns: repeat(6, minmax(0, 1fr))",
        "grid-template-columns: repeat(2, minmax(0, 1fr))",
        "min-height: 44px",
        "prefers-reduced-motion: reduce",
    ):
        assert token in CSS
    assert 'html[data-e10-backpack-shell="true"]' in CSS
    assert "GAMEPLAY / DATA / PRODUCT AUTHORITY" in DOC or "gameplay and data authority" in DOC


def test_manifest_and_docs_state_reference_examples_are_not_products():
    manifest = _manifest()
    assert "reference_examples_not_products" in manifest
    assert "Spirit Badge" in manifest["reference_examples_not_products"]
    assert "No reference-only item" in DOC
    assert "No unsupported Combat Power" in DOC


def test_hero_overlay_alpha_cleanup_does_not_leave_baked_checkerboard():
    """The two existing overlays used by the default Hero must isolate art."""
    for name in ("cloth_robe.png", "fox_pelt.png"):
        path = ROOT / "assets/hero/equipment/wearables/overlays" / name
        with Image.open(path).convert("RGBA") as image:
            pixels = list(image.getdata())
        opaque = [pixel for pixel in pixels if pixel[3] >= 250]
        near_white_opaque = [
            pixel for pixel in opaque
            if pixel[0] >= 245 and pixel[1] >= 245 and pixel[2] >= 245
        ]
        assert opaque
        assert len(near_white_opaque) / len(opaque) < 0.12, name
