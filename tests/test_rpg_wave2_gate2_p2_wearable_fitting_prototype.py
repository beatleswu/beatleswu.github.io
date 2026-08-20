"""Contract tests for the review-only wearable fitting prototype."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/planning/rpg_wave2_gate2_p2_wearable_fitting_manifest.json"
REVIEW = ROOT / "docs/planning/rpg_wave2_gate2_p2_wearable_fitting_review.html"
CONTACT_SHEET = ROOT / "docs/planning/rpg_wave2_gate2_p2_wearable_fitting_contact_sheet.png"
ASSET_DIR = ROOT / "docs/planning/rpg_wave2_gate2_p2_wearable_fitting_assets"


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_prototype_preserves_frame_scope_and_server_authorities():
    manifest = _manifest()
    assert manifest["task_id"] == "RPG_WAVE2_GATE2_P2_WEARABLE_FITTING_PROTOTYPE_001"
    assert manifest["base_sha"] == "ac182ed173620a11e66bebeb6003c121b9ceee95"
    assert manifest["review_only"] is True
    assert manifest["runtime_wiring"] is False
    assert manifest["player_frame"] == {
        "id": "PLAYER_FRAME_A_STANDARD_CHIBI",
        "canvas": [1056, 1408],
        "color_mode": "RGBA",
        "foot_baseline": 0.975,
        "body_frame_variants": 1,
    }
    assert set(manifest["characters"]) == {"apprentice", "mage", "paladin"}
    assert set(manifest["equipment"]) == {"iron_sword", "dragon_scale", "fox_mask"}
    assert manifest["authority"] == {
        "player_appearance": "player_appearance.character_key",
        "functional_equipment_ownership": "player_inventory",
        "functional_equipment_equipped": "player_inventory.equipped",
        "functional_effects": "server EQUIPMENT_DEFS",
        "character_combat_authority": False,
        "client_combat_authority": False,
        "combat_delta_from_wearable_rendering": 0,
        "writes_api": False,
        "writes_db": False,
    }


def test_three_universal_overlays_and_three_reusable_character_masks_are_rgba():
    manifest = _manifest()
    assert manifest["scalability"] == {
        "can_one_body_frame_support_reusable_wearables": "PASS_WITH_REUSABLE_CHARACTER_MASKS",
        "universal_overlays": 3,
        "body_frame_variants": 1,
        "character_reusable_masks": 3,
        "item_character_bespoke_redraws": 0,
        "future_15_equipment_scalability": "PASS_PROTOTYPE_ARCHITECTURE",
    }
    for item_id, item in manifest["equipment"].items():
        assert item["item_presentation_art_reused_as_wearable"] is False
        assert (ROOT / item["inventory_icon"]).is_file()
        assert (ROOT / item["generated_source"]).is_file()
        cutout_path = ROOT / item["normalized_cutout"]
        overlay_path = ROOT / item["canonical_overlay"]
        assert cutout_path.is_file(), item_id
        assert overlay_path.is_file(), item_id
        with Image.open(cutout_path) as cutout:
            rgba = cutout.convert("RGBA")
            assert rgba.getchannel("A").getextrema() == (0, 255)
            for red, green, blue, alpha in rgba.get_flattened_data():
                if alpha == 0:
                    assert (red, green, blue) == (0, 0, 0)
        with Image.open(overlay_path) as overlay:
            assert overlay.size == (1056, 1408)
            assert overlay.mode == "RGBA"

    assert manifest["occlusion"]["front_hand_mask_required"] is False
    assert manifest["occlusion"]["item_character_bespoke_redraws"] == 0
    for character_id, relative in manifest["occlusion"]["masks"].items():
        with Image.open(ROOT / relative) as mask:
            assert mask.size == (1056, 1408), character_id
            assert mask.mode == "RGBA"
            assert mask.getchannel("A").getbbox() is not None


def test_exact_twelve_composites_and_equal_scale_contact_sheet_exist():
    manifest = _manifest()
    expected = {
        ASSET_DIR / "composites" / f"{character}_{loadout}.png"
        for character in ("apprentice", "mage", "paladin")
        for loadout in ("iron_sword", "dragon_scale", "fox_mask", "full")
    }
    actual = set((ASSET_DIR / "composites").glob("*.png"))
    assert actual == expected
    assert len([entry for entry in manifest["qa_matrix"] if entry["loadout"] != "full"]) == 9
    assert len([entry for entry in manifest["qa_matrix"] if entry["loadout"] == "full"]) == 3
    assert all(entry["result"] in {"PASS", "PASS_WITH_MINOR_OFFSET", "FAIL"} for entry in manifest["qa_matrix"])
    for composite in expected:
        with Image.open(composite) as image:
            assert image.size == (1056, 1408)
            assert image.mode == "RGBA"
            assert image.getchannel("A").getbbox() is not None
    with Image.open(CONTACT_SHEET) as sheet:
        assert sheet.width >= 1100
        assert sheet.height >= 2500
        assert sheet.mode == "RGB"


def test_review_html_is_static_interactive_and_never_wires_runtime_state():
    html = REVIEW.read_text(encoding="utf-8")
    for character in ("apprentice", "mage", "paladin"):
        assert f'data-character="{character}"' in html
    for loadout in ("none", "iron_sword", "dragon_scale", "fox_mask", "full"):
        assert f'data-loadout="{loadout}"' in html
    for contract in (
        "PLAYER_FRAME_A_STANDARD_CHIBI",
        "player_appearance.character_key",
        "player_inventory.equipped",
        "EQUIPMENT_DEFS",
        "PASS_WITH_REUSABLE_CHARACTER_MASKS",
        "rpg_wave2_gate2_p2_wearable_fitting_contact_sheet.png",
    ):
        assert contract in html
    for forbidden in (
        "fetch(",
        "XMLHttpRequest",
        "localStorage",
        "sessionStorage",
        "name=\"attack\"",
        "name=\"defense\"",
        "data-rarity=",
    ):
        assert forbidden not in html


def test_current_character_and_equipment_ids_remain_the_runtime_contract():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    for character_id in ("apprentice", "mage", "paladin"):
        assert f"'{character_id}'" in app
    for equipment_id in ("iron_sword", "dragon_scale", "fox_mask"):
        assert f"'id': '{equipment_id}'" in app
        assert f"'{equipment_id}':" in app
    assert "def _get_authoritative_combat_stats" in app
    assert "SELECT equip_id FROM player_inventory WHERE user_id=? AND equipped=1" in app
