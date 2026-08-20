"""Contracts for the first template-first modular equipment art batch."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
P1_ROOT = ROOT / "docs/planning/rpg_wave2_modular_equipment_production_v2_p1"
MANIFEST = P1_ROOT / "manifest.json"

EXPECTED_ITEMS = {
    "iron_sword": "WEAPON_WAIST",
    "dragon_scale": "TORSO_ARMOR",
    "fox_mask": "FACE_ACCESSORY",
    "void_mantle": "SHOULDER_MANTLE",
}
EXPECTED_APPROVED_ASSET_SHA256 = {
    "dragon_scale": "ee04722af396d433aec98b5d6f75750a3172987bbcc704d7ecbfd4c1d0cdca98",
    "fox_mask": "d1bcea46b3650833b268f5e20d6eed4fa1706a931aaf9a949bb42437672dd02c",
}
CHARACTERS = {
    "apprentice",
    "mage",
    "paladin",
    "trail_apprentice",
    "night_runner",
    "constellation_apprentice",
}


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_p1_selects_four_template_authorized_reference_items():
    report = _manifest()
    assert report["task_id"] == "RPG_WAVE2_MODULAR_2D_EQUIPMENT_PRODUCTION_V2_P1_001"
    assert report["foundation_head"] == "2575e79f14b62e3880cd66f61a4055cf01d67e1b"
    assert report["selected_templates"] == EXPECTED_ITEMS
    assert set(report["selected_items"]) == set(EXPECTED_ITEMS)
    assert report["selected_items"] == ["iron_sword", "dragon_scale", "fox_mask", "void_mantle"]
    assert report["inventory_only_policy"] == {"go_stone_black": "NONE"}


def test_p1_has_all_24_template_first_qa_results_and_no_bespoke_redraws():
    report = _manifest()
    assert report["characters"] == sorted(CHARACTERS, key=lambda value: [
        "apprentice", "mage", "paladin", "trail_apprentice", "night_runner", "constellation_apprentice",
    ].index(value))
    assert len(report["qa_matrix"]) == 24
    assert report["counts"] == {
        "fit_combinations": 24,
        "fit_pass_count": 24,
        "face_safe_zone_violations": 0,
        "alpha_artifacts": 0,
        "white_box_artifacts": 0,
        "matte_halo": 0,
        "chroma_residue": 0,
        "item_character_bespoke_redraws": 0,
    }
    assert all(entry["result"] == "PASS" for entry in report["qa_matrix"])
    assert all(entry["bespoke_redraw"] is False for entry in report["qa_matrix"])
    assert all(set(entry["metrics"]) == {
        "FACE_CLEARANCE", "HEAD_CLEARANCE", "SHOULDER_FIT", "TORSO_FIT", "WAIST_FIT",
        "HAIR_COLLISION", "ROBE_COLLISION", "ARMOR_COLLISION", "DEPTH_ORDER",
        "MOBILE_READABILITY", "ITEM_RECOGNIZABILITY", "CHARACTER_IDENTITY_PRESERVATION",
    } for entry in report["qa_matrix"])


def test_p1_overlays_are_true_alpha_and_inside_canonical_template_bounds():
    report = _manifest()
    for item_id, item in report["equipment"].items():
        path = P1_ROOT / item["asset"]
        assert path.is_file(), item_id
        with Image.open(path) as image:
            assert image.size == (1056, 1408), item_id
            rgba = image.convert("RGBA")
            assert rgba.getchannel("A").getbbox() is not None, item_id
            for red, green, blue, alpha in rgba.getdata():
                if alpha == 0:
                    assert (red, green, blue) == (0, 0, 0), item_id
            assert item["alpha_audit"]["inside_template_bbox"] is True
            assert item["alpha_audit"]["alpha_artifacts"] == 0
            assert item["alpha_audit"]["transparent_rgb_nonzero"] == 0


def test_p1_matrices_and_review_are_static_review_artifacts():
    report = _manifest()
    desktop = P1_ROOT / report["outputs"]["desktop_matrix"]
    mobile = P1_ROOT / report["outputs"]["mobile_matrix"]
    review = P1_ROOT / report["outputs"]["review_html"]
    assert desktop.is_file()
    assert mobile.is_file()
    assert review.is_file()
    with Image.open(desktop) as image:
        assert image.mode == "RGB"
        assert image.width == 1236
    with Image.open(mobile) as image:
        assert image.mode == "RGB"
        assert image.width == 430
    html = review.read_text(encoding="utf-8")
    for item_id in EXPECTED_ITEMS:
        assert f'data-item="{item_id}"' in html
    for character in CHARACTERS:
        assert f'data-character="{character}"' in html
    assert "player_inventory" in html
    assert "fetch(" not in html
    assert "go_stone_black" not in html


def test_p1_preserves_presentation_only_authority():
    report = _manifest()
    assert report["authority"] == {
        "ownership": "player_inventory",
        "equipped": "player_inventory.equipped",
        "effects": "server EQUIPMENT_DEFS",
        "wearable_renderer": "presentation only",
        "client_combat_authority": False,
        "combat_delta": 0,
    }
    assert report["template_first_workflow"]["post_hoc_character_dragging"] is False
    assert report["template_first_workflow"]["character_specific_art"] is False
    assert report["template_first_workflow"]["runtime_wiring_expanded"] is False


def test_p1b_narrow_fix_contract_and_approved_asset_locks():
    report = _manifest()
    p1b = report["p1b"]
    assert p1b["task_id"] == "RPG_WAVE2_MODULAR_2D_EQUIPMENT_PRODUCTION_V2_P1B_NARROW_FIX_001"
    assert p1b["head_before"] == "c733b59e83fc3e641314064033ca165b782975f5"
    assert p1b["items"] == ["iron_sword", "void_mantle"]
    assert p1b["templates"] == {
        "iron_sword": "WEAPON_WAIST",
        "void_mantle": "SHOULDER_MANTLE",
    }
    assert p1b["template_changes"] == {
        "WEAPON_WAIST": False,
        "SHOULDER_MANTLE": False,
    }
    assert p1b["approved_assets_unchanged"] == {
        "dragon_scale": True,
        "fox_mask": True,
    }
    assert p1b["counts"] == {
        "fit_combinations": 12,
        "fit_pass_count": 12,
        "face_safe_zone_violations": 0,
        "alpha_artifacts": 0,
        "white_box_artifacts": 0,
        "matte_halo_artifacts": 0,
        "item_character_bespoke_redraws": 0,
    }
    assert p1b["mobile"] == {
        "iron_sword_recognizability": "6/6",
        "void_mantle_recognizability": "6/6",
        "result": "PASS",
    }
    assert all(entry["result"] == "PASS" for entry in p1b["qa_matrix"])
    assert len(p1b["qa_matrix"]) == 12

    for item_id, expected_sha in EXPECTED_APPROVED_ASSET_SHA256.items():
        path = P1_ROOT / "overlays" / f"{item_id}.png"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected_sha


def test_p1b_sources_are_true_alpha_and_matrices_exist():
    report = _manifest()
    p1b = report["p1b"]
    for item_id in p1b["items"]:
        source = P1_ROOT / "sources" / f"P1B_{item_id}_source.png"
        assert source.is_file(), item_id
        with Image.open(source) as image:
            rgba = image.convert("RGBA")
            assert rgba.getchannel("A").getbbox() is not None, item_id
            assert all(
                (red, green, blue) == (0, 0, 0)
                for red, green, blue, alpha in rgba.getdata()
                if alpha == 0
            ), item_id

    for output in p1b["outputs"].values():
        path = P1_ROOT / output
        assert path.is_file(), output
        with Image.open(path) as image:
            assert image.mode == "RGB"
            assert image.width in {430, 1236}


def test_p1c_iron_sword_readability_fix_is_narrow_and_reusable():
    report = _manifest()
    p1c = report["p1c"]
    assert p1c["task_id"] == "RPG_WAVE2_MODULAR_2D_EQUIPMENT_PRODUCTION_V2_P1C_IRON_SWORD_READABILITY_FIX_001"
    assert p1c["head_before"] == "c5aca3015061f3968ae3d080fca2dd52456b5db7"
    assert p1c["item"] == "iron_sword"
    assert p1c["template"] == "WEAPON_WAIST"
    assert p1c["static_weapon_mode"] == "WAIST_SHEATHED"
    assert p1c["hand_held_static_mode"] == "FORBIDDEN"
    assert p1c["fake_hand_grip"] is False
    assert p1c["template_changed"] is False
    assert p1c["front_segment_policy"] == "REUSABLE_HILT_GUARD_AND_SHEATH_EDGE_SEGMENT"
    assert p1c["qa"] == {
        "fit_combinations": 6,
        "fit_pass_count": 6,
        "face_safe_zone_violations": 0,
        "alpha_artifacts": 0,
        "white_box_artifacts": 0,
        "matte_halo_artifacts": 0,
        "mobile_recognizability": "6/6",
        "result": "PASS",
        "item_character_bespoke_redraws": 0,
    }
    for output in p1c["outputs"].values():
        path = P1_ROOT / output
        assert path.is_file(), output
        if path.suffix.lower() == ".png":
            with Image.open(path) as image:
                assert image.mode in {"RGB", "RGBA"}
                if "overlay" not in path.name:
                    assert image.width in {430, 1236}

    assert report["equipment"]["iron_sword"]["front_segment_policy"] == (
        "REUSABLE_HILT_GUARD_AND_SHEATH_EDGE_SEGMENT"
    )
    assert report["equipment"]["dragon_scale"]["front_segment_policy"] == "NONE"
    assert report["equipment"]["fox_mask"]["front_segment_policy"] == "NONE"
    assert report["equipment"]["void_mantle"]["front_segment_policy"] == "REUSABLE_SIDE_SHOULDER_SEGMENTS"
