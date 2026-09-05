"""W2-03 Hero wearable visual refresh and presentation safety contracts."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/planning/w2_03_hero_wearable_visual_refresh_002r1_manifest.json"
REGISTRY = ROOT / "assets/hero/equipment/wearables/wearable_registry.json"
RENDERER = ROOT / "js/rpg_wave2_wearable_renderer.js"
HERO = ROOT / "hero.html"
APP = ROOT / "app.py"

OVERLAY_ROOT = ROOT / "assets/hero/equipment/wearables/overlays"
EXPECTED_WEARABLES = {
    "wooden_sword", "iron_sword", "fox_fang", "dragon_claw", "celestial_blade",
    "cloth_robe", "leather_armor", "fox_pelt", "dragon_scale", "void_mantle",
    "lucky_stone", "xp_amulet", "fox_mask", "dragon_eye",
}
EXPECTED_A = {
    "wooden_sword", "iron_sword", "fox_fang", "dragon_claw", "celestial_blade",
    "leather_armor", "dragon_scale", "void_mantle", "lucky_stone", "xp_amulet",
    "fox_mask", "dragon_eye",
}
EXPECTED_C = {"cloth_robe", "fox_pelt"}


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_manifest_preserves_exact_fourteen_item_visual_classification():
    manifest = _json(MANIFEST)
    assert manifest["task_id"] == "W2_03_HERO_WEARABLE_VISUAL_REFRESH_002R1"
    assert manifest["base_head"] == "5b713a4cac285ffde3f9cd1ca911d61dd284e511"
    assert manifest["base_tree"] == "55bf9016733546b2b3b4ea28908ff3bfdb4cf46b"
    assert set(manifest["classification"]["A_READY_TRANSPARENT_WEARABLE"]) == EXPECTED_A
    assert len(manifest["classification"]["A_READY_TRANSPARENT_WEARABLE"]) == 12
    assert manifest["classification"]["B_COMPOSITING_FIX_REQUIRED"] == []
    assert set(manifest["classification"]["C_ART_REPLACEMENT_REQUIRED"]) == EXPECTED_C
    assert len(manifest["classification"]["C_ART_REPLACEMENT_REQUIRED"]) == 2
    assert manifest["counts"] == {
        "total_wearable_overlays": 14,
        "ready_transparent_wearable": 12,
        "compositing_fix_required": 0,
        "art_replacement_required": 2,
    }


def test_manifest_item_rows_cover_exactly_the_runtime_wearable_set():
    manifest = _json(MANIFEST)
    rows = {row["item_id"]: row for row in manifest["items"]}
    assert set(rows) == EXPECTED_WEARABLES
    assert {item_id for item_id, row in rows.items() if row["class"] == "A"} == EXPECTED_A
    assert {item_id for item_id, row in rows.items() if row["class"] == "C"} == EXPECTED_C
    assert all(row["runtime_policy"] == "render" for row in rows.values() if row["class"] == "A")
    assert all(
        row["runtime_policy"] == "fail_closed_until_replacement"
        for row in rows.values()
        if row["class"] == "C"
    )


def test_registry_and_assets_prove_the_two_replacement_candidates_are_not_inventory_only():
    registry = _json(REGISTRY)
    for item_id in EXPECTED_WEARABLES:
        item = registry["equipment"][item_id]
        assert item["wearable_visibility"] != "INVENTORY_ONLY"
        assert item["frame"] == "PLAYER_FRAME_A_STANDARD_CHIBI"
        assert (ROOT / item["asset"].lstrip("/")).is_file(), item_id


def test_replacement_candidates_have_baked_opaque_fields_while_a_assets_are_true_alpha():
    def alpha_summary(item_id: str) -> tuple[int, int, float]:
        with Image.open(OVERLAY_ROOT / f"{item_id}.png") as image:
            rgba = image.convert("RGBA")
            alpha = rgba.getchannel("A")
            pixels = alpha.get_flattened_data()
            nonzero = sum(1 for value in pixels if value > 0)
            opaque = sum(1 for value in pixels if value == 255)
            return nonzero, opaque, opaque / (rgba.width * rgba.height)

    for item_id in EXPECTED_C:
        nonzero, opaque, opaque_ratio = alpha_summary(item_id)
        assert nonzero == opaque
        assert opaque_ratio > 0.10, item_id

    for item_id in EXPECTED_A:
        nonzero, opaque, opaque_ratio = alpha_summary(item_id)
        assert nonzero > 0, item_id
        assert opaque_ratio < 0.10, item_id


def test_renderer_fails_closed_before_dom_layer_creation_for_c_class_assets():
    renderer = RENDERER.read_text(encoding="utf-8")
    assert "ART_REPLACEMENT_REQUIRED_IDS = Object.freeze(['cloth_robe', 'fox_pelt'])" in renderer
    assert "ART_REPLACEMENT_REQUIRED.has(id)" in renderer
    assert "const replacementIds = requestedIds.filter(id => ART_REPLACEMENT_REQUIRED.has(id));" in renderer
    assert "stage.dataset.replacementIds = replacementIds.join(',');" in renderer
    assert "replacementRequired: replacementIds" in renderer
    assert "css crop" not in renderer.lower()
    assert "background-colored" not in renderer.lower()
    assert "method: 'POST'" not in renderer
    assert "player_inventory" not in renderer
    assert "EQUIPMENT_DEFS" not in renderer


def test_renderer_keeps_the_existing_presentation_only_authority_boundary():
    manifest = _json(MANIFEST)
    assert manifest["authority"] == {
        "ownership": "player_inventory",
        "equipped": "player_inventory.equipped",
        "character": "player_appearance.character_key",
        "effects": "server EQUIPMENT_DEFS",
        "projection": "read_only",
        "client_combat_authority": False,
        "visual_wearable_gameplay_authority": False,
    }
    hero = HERO.read_text(encoding="utf-8")
    app = APP.read_text(encoding="utf-8")
    assert "server_equipped_projection" in RENDERER.read_text(encoding="utf-8")
    assert "gameplayAuthority = 'none'" in RENDERER.read_text(encoding="utf-8")
    assert "data-gameplay-authority" not in RENDERER.read_text(encoding="utf-8")
    assert "player_inventory" in app
    assert "FUNCTIONAL_WEARABLE_ART_REPLACEMENT_IDS" in hero
    assert "穿戴圖待替換" in hero
    assert "window.GoOdysseyWearableRenderer?.artReplacementRequiredIds" in hero
    assert "localStorage" not in RENDERER.read_text(encoding="utf-8")


def test_representative_proof_uses_allowed_functional_items_only():
    proof = _json(MANIFEST)["representative_proof"]
    assert proof["weapon"] == ["wooden_sword"]
    assert proof["armor"] == ["dragon_scale"]
    assert proof["accessory"] == ["lucky_stone"]
    assert proof["full_loadout"] == ["wooden_sword", "dragon_scale", "lucky_stone"]
    assert "xp_amulet" in proof["excluded_from_representative_proof"]
    assert "go_stone_black" in proof["excluded_from_representative_proof"]
