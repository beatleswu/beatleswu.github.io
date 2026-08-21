import json
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/planning/rpg_wave2_gate2_p2b_weapon_carry_manifest.json"
P2_MANIFEST = ROOT / "docs/planning/rpg_wave2_gate2_p2_wearable_fitting_manifest.json"
HTML = ROOT / "docs/planning/rpg_wave2_gate2_p2_wearable_fitting_review.html"
ASSET_DIR = ROOT / "docs/planning/rpg_wave2_gate2_p2_wearable_fitting_assets/p2b_weapon_carry"
CONTACT_SHEET = ROOT / "docs/planning/rpg_wave2_gate2_p2b_weapon_carry_contact_sheet.png"


def _manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_exact_base_characters_weapon_and_authority_contract():
    manifest = _manifest()
    assert manifest["base_sha"] == "ac182ed173620a11e66bebeb6003c121b9ceee95"
    assert set(manifest["characters"]) == {"apprentice", "mage", "paladin"}
    assert manifest["weapon"]["id"] == "iron_sword"
    assert manifest["weapon"]["presentation_is_one_universal_overlay"] is True
    assert manifest["weapon"]["item_character_bespoke_redraws"] == 0
    assert manifest["player_frame"]["id"] == "PLAYER_FRAME_A_STANDARD_CHIBI"
    assert tuple(manifest["player_frame"]["canvas"]) == (1056, 1408)
    assert manifest["authority"] == {
        "functional_equipment_ownership": "player_inventory",
        "functional_equipped": "player_inventory.equipped",
        "functional_effects": "server EQUIPMENT_DEFS",
        "gameplay_authority": False,
        "combat_delta_from_rendering": 0,
        "writes_api": False,
        "writes_db": False,
    }


def test_hand_held_is_explicitly_rejected_and_carry_modes_are_scoped():
    manifest = _manifest()
    held = manifest["modes"]["current_held"]
    assert held["result"] == "FAIL_AS_CANONICAL_STATIC_MODE"
    assert held["hand_grip_alignment"] == "FAIL"
    assert held["held_weapon_visual"] == "FAIL"
    assert "open" in held["root_cause"]
    assert set(manifest["modes"]) == {"current_held", "waist_sheathed", "back_mounted"}
    assert manifest["modes"]["waist_sheathed"]["result"] == "PASS"
    assert manifest["modes"]["back_mounted"]["result"] == "PASS_WITH_MINOR_OFFSET"
    assert manifest["qa"]["static_weapon_mode"] == "WAIST_SHEATHED"
    assert manifest["qa"]["mask_complexity"] == "LOW"


def test_nine_equal_scale_review_composites_and_contact_sheet_exist():
    expected = {
        ASSET_DIR / "composites" / f"{character}_{mode}.png"
        for character in ("apprentice", "mage", "paladin")
        for mode in ("current_held", "waist_sheathed", "back_mounted")
    }
    assert set((ASSET_DIR / "composites").glob("*.png")) == expected
    for composite in expected:
        with Image.open(composite) as image:
            assert image.size == (1056, 1408)
            assert image.mode == "RGBA"
            assert image.getchannel("A").getbbox() is not None
    with Image.open(ASSET_DIR / "cutouts/iron_sword_carry_cutout.png") as cutout:
        assert cutout.mode == "RGBA"
        assert cutout.getchannel("A").getextrema() == (0, 255)
        for red, green, blue, alpha in cutout.get_flattened_data():
            if alpha == 0:
                assert (red, green, blue) == (0, 0, 0)
    with Image.open(CONTACT_SHEET) as sheet:
        assert sheet.mode == "RGB"
        assert sheet.width >= 1100
        assert sheet.height >= 1500


def test_review_page_exposes_weapon_modes_without_runtime_wiring():
    html = HTML.read_text(encoding="utf-8")
    for loadout in ("none", "iron_sword", "iron_sword_waist", "iron_sword_back"):
        assert f'data-loadout="{loadout}"' in html
    for label in ("No weapon", "Current Held", "Waist", "Back"):
        assert label in html
    for contract in (
        "FAIL_AS_CANONICAL_STATIC_MODE",
        "player_inventory.equipped",
        "EQUIPMENT_DEFS",
        "p2b_weapon_carry/composites/",
        "rpg_wave2_gate2_p2b_weapon_carry_contact_sheet.png",
        "weapon-controls",
    ):
        assert contract in html
    for forbidden in ("fetch(", "XMLHttpRequest", "localStorage", "sessionStorage"):
        assert forbidden not in html


def test_p2_handheld_correction_and_runtime_ids_are_preserved():
    p2 = json.loads(P2_MANIFEST.read_text(encoding="utf-8"))
    assert p2["aggregate_qa"]["iron_sword_fit"] == "FAIL"
    assert p2["aggregate_qa"]["hand_grip_alignment"] == "FAIL"
    assert p2["aggregate_qa"]["held_weapon_visual"] == "FAIL"
    assert all(
        entry["result"] == "FAIL"
        for entry in p2["qa_matrix"]
        if entry["loadout"] == "iron_sword"
    )

    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert all(f"'{character}'" in app for character in ("apprentice", "mage", "paladin"))
    assert all(f"'id': '{item}'" in app for item in ("iron_sword", "dragon_scale", "fox_mask"))
    assert "SELECT equip_id FROM player_inventory WHERE user_id=? AND equipped=1" in app
