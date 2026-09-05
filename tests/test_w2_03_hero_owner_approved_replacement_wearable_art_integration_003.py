"""W2-03 Owner-approved replacement wearable integration contracts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/planning/w2_03_hero_owner_approved_replacement_wearable_art_integration_003.json"
REGISTRY = ROOT / "assets/hero/equipment/wearables/wearable_registry.json"
VISIBILITY = ROOT / "docs/planning/rpg_modular_2d_equipment/visibility_matrix.json"
RENDERER = ROOT / "js/rpg_wave2_wearable_renderer.js"
BROWSER_HARNESS = ROOT / "tests/e2e/run_w2_03_owner_approved_replacement_wearable_browser_qa.mjs"
SOURCE_ROOT = ROOT / "docs/planning/w2_03_hero_owner_approved_replacement_wearable_sources"
OUTPUT_ROOT = ROOT / "assets/hero/equipment/wearables/overlays"

CHARACTER_ASSETS = {
    "apprentice_p1": "apprentice",
    "mage_p1": "mage",
    "paladin_p1": "paladin",
    "trail_apprentice_p1": "trail_apprentice",
    "night_runner_p1": "night_runner",
    "constellation_apprentice_p1": "constellation_apprentice",
}


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rgba_summary(path: Path) -> tuple[tuple[int, int], tuple[int, int, int, int] | None]:
    with Image.open(path) as image:
        rgba = image.convert("RGBA")
        alpha = rgba.getchannel("A")
        return rgba.size, alpha.getbbox()


def test_owner_approved_inputs_are_exact_and_manifest_is_traceable():
    manifest = _json(MANIFEST)
    assert manifest["task_id"] == (
        "W2_03_HERO_OWNER_APPROVED_REPLACEMENT_WEARABLE_ART_INTEGRATION_003"
    )
    assert manifest["base"] == {
        "head": "6fd716f49de8772b1c085ed9d51448371ef59439",
        "tree": "a87f681b30a30d8e9007d779134daa0cec3e46e3",
    }
    assert manifest["owner_approval"]["status"] == "GRANTED"
    assert manifest["owner_approval"]["approved_assets"] == {
        "cloth_robe": "cloth_robe_owner_approved.png",
        "fox_pelt": "fox_pelt_owner_approved.png",
    }
    for item_id, expected_size in (("cloth_robe", (1086, 1448)), ("fox_pelt", (1086, 1448))):
        item = manifest["items"][item_id]
        source = ROOT / item["source_copy"]
        assert source.is_file(), item_id
        assert _sha256(source) == item["source_sha256"], item_id
        assert _rgba_summary(source) == (expected_size, tuple(item["source_alpha_bbox_px"])), item_id


def test_outputs_are_normalized_rgba_transparent_and_exactly_manifested():
    manifest = _json(MANIFEST)
    for item_id in ("cloth_robe", "fox_pelt"):
        item = manifest["items"][item_id]
        output = ROOT / item["output_path"].lstrip("/")
        assert output.is_file(), item_id
        assert _sha256(output) == item["output_sha256"], item_id
        with Image.open(output) as image:
            assert image.size == (1056, 1408), item_id
            assert image.mode == "RGBA", item_id
            assert image.getchannel("A").getbbox() == tuple(item["output_alpha_bbox_px"]), item_id
            assert image.getpixel((0, 0))[3] == 0, item_id
            assert image.getpixel((1055, 0))[3] == 0, item_id
            assert image.getpixel((0, 1407))[3] == 0, item_id
            assert image.getpixel((1055, 1407))[3] == 0, item_id
            # Transparent pixels are canonical black RGBA, so no opaque matte
            # or export-colored transparent field can enter the stage.
            assert all(
                pixel[:3] == (0, 0, 0)
                for pixel in image.get_flattened_data()
                if pixel[3] == 0
            ), item_id


def test_registry_bindings_match_the_owner_approved_frame_contract():
    manifest = _json(MANIFEST)
    registry = _json(REGISTRY)
    visibility = _json(VISIBILITY)
    for item_id, layer, anchor, template in (
        ("cloth_robe", "TORSO_ARMOR", "torso", "ROBE_OVERLAY"),
        ("fox_pelt", "BACK_BODY", "shoulder_or_torso", "SHOULDER_MANTLE"),
    ):
        item = registry["equipment"][item_id]
        spec = manifest["items"][item_id]
        row = next(row for row in visibility["items"] if row["equipment_id"] == item_id)
        assert item["slot"] == "armor"
        assert item["frame"] == "PLAYER_FRAME_A_STANDARD_CHIBI"
        assert item["asset"] == spec["output_path"]
        assert item["source"] == spec["source_copy"]
        assert item["anchor"] == anchor
        assert item["layer"] == layer
        assert item["template_id"] == template
        assert item["wearable_visibility"] == "VISIBLE_WEARABLE"
        assert item["presentation_only"] is True
        assert row["anchor"] == anchor
        assert row["layer"] == layer
        assert row["template_id"] == template
        assert row["asset"] == spec["output_path"]
        assert "FACE_SAFE_ZONE_CLEARANCE" in row["mask_policy"]
        assert "BASE_OCCLUSION" in row["mask_policy"]


def test_fox_preserves_aspect_and_declares_the_approved_tail_extension():
    manifest = _json(MANIFEST)
    item = manifest["items"]["fox_pelt"]
    normalization = item["normalization"]
    assert normalization["preserve_aspect_ratio"] is True
    assert normalization["distortion"] is False
    assert normalization["design_changed"] is False
    assert normalization["paste_px"] == [169, 310]
    assert normalization["declared_shoulder_alignment_bbox_px"] == [169, 310, 887, 732]
    assert normalization["preserved_tail_extension_beyond_declared_bbox"] is True
    assert normalization["tail_extension_requires_owner_review"] is True
    assert item["output_alpha_bbox_px"] == [169, 310, 887, 1237]


def test_shared_frame_covers_all_six_canonical_hero_characters_without_bespoke_art():
    manifest = _json(MANIFEST)
    registry = _json(REGISTRY)
    alignment = manifest["six_character_alignment"]
    assert alignment["characters"] == list(CHARACTER_ASSETS)
    assert alignment["canvas"] == [1056, 1408]
    assert alignment["frame"] == "PLAYER_FRAME_A_STANDARD_CHIBI"
    assert alignment["body_frame_variants"] == 1
    assert alignment["bespoke_replacement_art"] is False
    assert alignment["cloth_robe"] == "PASS"
    assert alignment["fox_pelt"] == "PASS"
    for filename, registry_key in CHARACTER_ASSETS.items():
        character = registry["characters"][registry_key]
        base = ROOT / character["base"].lstrip("/")
        assert base.name == f"{filename}.png"
        assert _rgba_summary(base)[0] == (1056, 1408)


def test_renderer_promotes_both_approved_items_without_new_authority():
    runtime = RENDERER.read_text(encoding="utf-8")
    assert "ART_REPLACEMENT_REQUIRED_IDS = Object.freeze([])" in runtime
    assert "ART_REPLACEMENT_REQUIRED.has(id)" in runtime
    assert "server_equipped_projection" in runtime
    assert "gameplayAuthority = 'none'" in runtime
    assert "method: 'POST'" not in runtime
    assert "player_inventory" not in runtime
    assert "localStorage" not in runtime
    assert "wooden_sword" not in runtime


def test_browser_harness_covers_required_states_viewports_and_shared_frames():
    harness = BROWSER_HARNESS.read_text(encoding="utf-8")
    for state in ("none", "cloth", "fox", "full_cloth", "full_fox"):
        assert f"{state}:" in harness
    for viewport in ("desktop", "ipad-landscape", "ipad-portrait", "mobile-portrait"):
        assert f"['{viewport}'" in harness
    assert "characterKeys = [" in harness
    assert "renderSafe" in harness
    assert "server_equipped_projection" in harness
    assert "gameplayAuthority" in harness


def test_preserved_authority_and_existing_accepted_bindings_remain_locked():
    manifest = _json(MANIFEST)
    registry = _json(REGISTRY)
    assert manifest["authority"] == {
        "presentation_consumes_server_equipped_projection": True,
        "client_ownership_authority": False,
        "client_equip_authority": False,
        "auto_equip": False,
        "gameplay_authority_changed": False,
    }
    equipment = registry["equipment"]
    assert (equipment["wooden_sword"]["presentation_mode"],
            equipment["wooden_sword"]["presentation_attachment"],
            equipment["wooden_sword"]["layer"]) == ("HAND_HELD", "RIGHT_PALM", "FRONT_WEAPON")
    assert equipment["dragon_scale"]["layer"] == "TORSO_ARMOR"
    assert equipment["lucky_stone"]["layer"] == "FRONT_ACCESSORY"
    assert equipment["xp_amulet"]["wearable_visibility"] == "VISIBLE_IF_SUPPORTED"
    assert equipment["go_stone_black"]["wearable_visibility"] == "INVENTORY_ONLY"
    assert manifest["preserved_bindings"]["xp_amulet"] == "HOLD_FOR_AUTHORITY"
    assert manifest["preserved_bindings"]["go_stone_black"] == "INVENTORY_ONLY"
