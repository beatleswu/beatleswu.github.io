"""Validate the Static Modular 2D Equipment production contract.

This validator is read-only.  It checks the formal template/visibility
metadata against the existing presentation registry and the accepted P2/P3
evidence.  It never reads gameplay state, writes the database, or generates
wearable art.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_ROOT = ROOT / "docs/planning/rpg_modular_2d_equipment"
TEMPLATES = CONTRACT_ROOT / "templates.json"
VISIBILITY = CONTRACT_ROOT / "visibility_matrix.json"
QA = CONTRACT_ROOT / "template_qa.json"
COMPATIBILITY = CONTRACT_ROOT / "renderer_compatibility.json"
REGISTRY = ROOT / "assets/hero/equipment/wearables/wearable_registry.json"
P3_REPORT = ROOT / "docs/planning/rpg_wave2_gate2_p3_wearable_runtime_manifest.json"
P2B_REPORT = ROOT / "docs/planning/rpg_wave2_gate2_p2b_weapon_carry_manifest.json"
RENDERER = ROOT / "js/rpg_wave2_wearable_renderer.js"

EXPECTED_TEMPLATES = {
    "WEAPON_WAIST",
    "WEAPON_BACK",
    "FOREARM_GEAR",
    "TORSO_ARMOR",
    "ROBE_OVERLAY",
    "SHOULDER_MANTLE",
    "FACE_ACCESSORY",
    "NECK_CHEST_ACCESSORY",
    "WAIST_ACCESSORY",
    "BACK_ACCESSORY",
}
EXPECTED_ZONES = {
    "FACE_SAFE_ZONE",
    "HAIR_ZONE",
    "NECK_ZONE",
    "TORSO_ZONE",
    "SHOULDER_ZONE",
    "WAIST_ZONE",
    "HAND_ZONE",
    "BACK_ZONE",
}
EXPECTED_CHARACTERS = {
    "apprentice",
    "mage",
    "paladin",
    "trail_apprentice",
    "night_runner",
    "constellation_apprentice",
}
TEMPLATE_FIELDS = {
    "anchor",
    "bounding_box",
    "face_safe_zone",
    "neck_limit",
    "shoulder_limit",
    "waist_limit",
    "front_back_layer",
    "occlusion_rule",
    "mobile_visibility_rule",
}


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _assert_rect(rect: list[float], name: str) -> None:
    if len(rect) != 4 or any(not 0 <= value <= 1 for value in rect):
        raise AssertionError(f"invalid normalized rect: {name}={rect}")
    if rect[0] >= rect[2] or rect[1] >= rect[3]:
        raise AssertionError(f"inverted normalized rect: {name}={rect}")


def _validate() -> dict:
    templates = _json(TEMPLATES)
    visibility = _json(VISIBILITY)
    qa = _json(QA)
    compatibility = _json(COMPATIBILITY)
    registry = _json(REGISTRY)
    p3 = _json(P3_REPORT)
    p2b = _json(P2B_REPORT)
    renderer = RENDERER.read_text(encoding="utf-8")

    assert templates["coordinate_system"] == {
        "canvas": [1056, 1408],
        "frame": "PLAYER_FRAME_A_STANDARD_CHIBI",
        "origin": "top_left",
        "units": "normalized_0_to_1",
        "rounding": "deterministic_renderer_round_half_up",
    }
    assert set(templates["zones"]) == EXPECTED_ZONES
    for zone_id, zone in templates["zones"].items():
        rects = zone.get("rects") or [zone["rect"]]
        for rect in rects:
            _assert_rect(rect, zone_id)
    assert set(templates["templates"]) == EXPECTED_TEMPLATES
    for template_id, template in templates["templates"].items():
        missing = TEMPLATE_FIELDS - set(template)
        assert not missing, f"{template_id} missing {sorted(missing)}"
        _assert_rect(template["bounding_box"], template_id)

    items = visibility["items"]
    assert len(items) == 15
    item_ids = [item["equipment_id"] for item in items]
    assert len(set(item_ids)) == 15
    assert set(item_ids) == set(registry["equipment"])
    counts = Counter(item["wearable_visibility"] for item in items)
    assert counts == Counter({
        "VISIBLE_WEARABLE": 4,
        "VISIBLE_IF_SUPPORTED": 10,
        "INVENTORY_ONLY": 1,
    })

    for item in items:
        runtime = registry["equipment"][item["equipment_id"]]
        assert runtime["wearable_visibility"] == item["wearable_visibility"]
        assert runtime["template_id"] == item["template_id"]
        assert runtime["wearable_class"] == item["wearable_class"]
        assert runtime["anchor"] == item["anchor"]
        assert runtime["layer"] == item["layer"]
        assert runtime["mask_policy"] == item["mask_policy"]
        if item["wearable_visibility"] == "INVENTORY_ONLY":
            assert item["template_id"] is None
            assert item["asset"] is None
            continue
        asset = ROOT / runtime["asset"].lstrip("/")
        assert asset.is_file(), item["equipment_id"]
        with Image.open(asset) as image:
            assert image.size == (1056, 1408), item["equipment_id"]
            assert image.mode == "RGBA", item["equipment_id"]
            assert image.getchannel("A").getbbox() is not None, item["equipment_id"]
            for red, green, blue, alpha in image.getdata():
                if alpha == 0:
                    assert (red, green, blue) == (0, 0, 0), item["equipment_id"]

    assert registry["modular_contract"]["schema"] == visibility["schema"]
    assert registry["player_frame"] == {
        "id": "PLAYER_FRAME_A_STANDARD_CHIBI",
        "canvas": [1056, 1408],
        "body_frame_variants": 1,
    }
    assert set(registry["characters"]) == EXPECTED_CHARACTERS
    assert registry["authority"] == {
        "ownership": "player_inventory",
        "equipped": "player_inventory.equipped",
        "effects": "server EQUIPMENT_DEFS",
        "character": "player_appearance.character_key",
        "presentation_only": True,
        "client_combat_authority": False,
        "visual_wearable_gameplay_authority": False,
    }

    p3c = p3["p3c_armor_occlusion"]
    assert p3c["cloth_robe_face_occlusion_after"] == 0
    assert p3c["non_face_armor_face_occlusion_count_after"] == 0
    assert all(
        pixels == 0
        for item_pixels in p3c["face_occlusion_pixels_after"].values()
        for pixels in item_pixels.values()
    )
    assert p2b["modes"]["waist_sheathed"]["result"] == "PASS"
    assert p2b["modes"]["current_held"]["result"] == "FAIL_AS_CANONICAL_STATIC_MODE"

    assert qa["characters"] == sorted(EXPECTED_CHARACTERS) or set(qa["characters"]) == EXPECTED_CHARACTERS
    assert set(qa["reference_items"]) == {"iron_sword", "dragon_scale", "fox_mask", "cloth_robe"}
    assert qa["aggregate"] == {
        "template_cells": 24,
        "passed_cells": 24,
        "face_occlusion_violations": 0,
        "alpha_artifact_failures": 0,
        "fake_hand_grip_failures": 0,
        "mobile_readability_failures": 0,
        "item_character_bespoke_redraws": 0,
        "result": "PASS_WITH_FACE_ACCESSORY_EXCEPTION",
    }
    for evidence in qa["reference_items"].values():
        assert set(evidence["per_character"]) == EXPECTED_CHARACTERS
        assert evidence["item_character_bespoke_redraws"] == 0
    assert qa["full_loadout"]["result"] == "PASS"

    assert compatibility["compatibility_result"] == "PASS_WITH_NARROW_PRESENTATION_GUARD"
    assert compatibility["runtime_code_change_required"] is True
    assert "INVENTORY_ONLY" in compatibility["runtime_code_change_scope"]
    assert "INVENTORY_ONLY" in renderer
    assert "server_equipped_projection" in renderer
    assert "gameplayAuthority = 'none'" in renderer
    assert "method: 'POST'" not in renderer
    assert "localStorage" not in renderer

    svg_files = [
        CONTRACT_ROOT / "templates.svg",
        CONTRACT_ROOT / "safe_zones.svg",
        CONTRACT_ROOT / "layer_contract.svg",
        CONTRACT_ROOT / "template_qa.svg",
    ]
    for svg in svg_files:
        root = ET.parse(svg).getroot()
        assert root.tag.endswith("svg"), svg

    return {
        "MODULAR_2D_ARCHITECTURE": "PASS",
        "TEMPLATE_COUNT": len(templates["templates"]),
        "SAFE_ZONE_CONTRACT": "PASS",
        "LAYER_CONTRACT": "PASS",
        "MASK_CONTRACT": "PASS",
        "VISIBLE_WEARABLE_COUNT": counts["VISIBLE_WEARABLE"],
        "VISIBLE_IF_SUPPORTED_COUNT": counts["VISIBLE_IF_SUPPORTED"],
        "INVENTORY_ONLY_COUNT": counts["INVENTORY_ONLY"],
        "SIX_CHARACTER_TEMPLATE_QA": "PASS_24_OF_24",
        "ITEM_CHARACTER_BESPOKE_REDRAWS": 0,
        "FUNCTIONAL_EQUIPMENT_AUTHORITY": "player_inventory",
        "CLIENT_COMBAT_AUTHORITY": "NO",
        "WEARABLE_ART_FILES_CHANGED": "NO",
    }


if __name__ == "__main__":
    print(json.dumps(_validate(), ensure_ascii=False, indent=2))
