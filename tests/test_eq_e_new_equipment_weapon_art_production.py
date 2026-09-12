"""Focused acceptance tests for the EQ-E generated Equipment art package."""

from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "docs" / "planning" / "eq_e_new_equipment_weapon_art_production_001"
MANIFEST_PATH = PACKAGE / "eq_e_asset_production_manifest.json"
REPORT_PATH = PACKAGE / "eq_e_asset_qa_report.json"
OVERLAY_ROOT = ROOT / "assets" / "hero" / "equipment" / "wearables" / "overlays"
ICON_ROOT = ROOT / "assets" / "hero" / "equipment" / "functional"
CANVAS = (1056, 1408)
FACE_SAFE = (0.40, 0.085, 0.60, 0.205)

EXPECTED = {
    "bamboo_shadow_blade": ("weapon", "common", "ZONE_EXCLUSIVE"),
    "jade_river_bead": ("accessory", "common", "ZONE_EXCLUSIVE"),
    "bamboo_scale_vest": ("armor", "common", "ZONE_EXCLUSIVE"),
    "foxtail_traveler_mantle": ("armor", "rare", "ZONE_EXCLUSIVE"),
    "riverguard_coat": ("armor", "rare", "ZONE_EXCLUSIVE"),
    "riverstone_sabre": ("weapon", "rare", "ZONE_EXCLUSIVE"),
    "cloudstep_star_lamellar": ("armor", "epic", "ZONE_EXCLUSIVE"),
    "constellation_focus_lens": ("accessory", "epic", "ZONE_EXCLUSIVE"),
    "moonstar_rapier": ("weapon", "epic", "ZONE_EXCLUSIVE"),
    "odyssey_star_compass": ("accessory", "legendary", "ZONE_EXCLUSIVE"),
    "emberline_cutlass": ("weapon", "rare", "SHOP_EXCLUSIVE"),
    "starglass_needle": ("weapon", "epic", "SHOP_EXCLUSIVE"),
    "weaveguard_vest": ("armor", "rare", "SHOP_EXCLUSIVE"),
    "mirrorfall_mantle": ("armor", "epic", "SHOP_EXCLUSIVE"),
    "copper_jade_talisman": ("accessory", "rare", "SHOP_EXCLUSIVE"),
    "prism_focus_charm": ("accessory", "epic", "SHOP_EXCLUSIVE"),
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_manifest_is_exactly_the_locked_eq_d_portfolio_and_presentation_only():
    manifest = load_manifest()
    assert manifest["schema"] == "go-odyssey.eq-e-asset-production-manifest.v2"
    assert manifest["authority_boundary"]["art_role"] == "presentation_only"
    assert manifest["authority_boundary"]["registry_or_renderer_changes"] is False
    assert manifest["authority_boundary"]["app_py_changes"] is False
    assert manifest["authority_boundary"]["index_html_changes"] is False
    assert manifest["eq_d_reconciliation"]["lock_commit"] == "426f9ee57481f697e71756110c946b51a74c9f6f"
    rows = {row["item_id"]: row for row in manifest["items"]}
    assert set(rows) == set(EXPECTED)
    for item_id, (item_type, rarity, slot) in EXPECTED.items():
        row = rows[item_id]
        assert (row["type"], row["rarity"], row["source_classification"]) == (item_type, rarity, slot)
        if slot == "SHOP_EXCLUSIVE":
            assert row["shop_preview"].endswith(f"/{item_id}.svg")
            assert row["zone_reward_presentation"] is None
        else:
            assert row["shop_preview"] is None
            assert row["zone_reward_presentation"].endswith(f"/{item_id}.svg")


def test_every_overlay_is_new_rgba_canvas_alpha_clean_and_template_bounded():
    manifest = load_manifest()
    for row in manifest["items"]:
        item_id = row["item_id"]
        path = OVERLAY_ROOT / f"{item_id}.png"
        assert path.exists(), item_id
        assert path.stat().st_size > 0
        with Image.open(path) as image:
            assert image.mode == "RGBA", item_id
            assert image.size == CANVAS, item_id
            alpha = image.getchannel("A")
            bbox = alpha.getbbox()
            assert bbox is not None and bbox[2] > bbox[0] and bbox[3] > bbox[1], item_id
            assert all(
                pixel[:3] == (0, 0, 0)
                for pixel in image.get_flattened_data()
                if pixel[3] == 0
            ), item_id
            if row["handheld_required"]:
                assert row["layer"] == "MAIN_HAND_WEAPON"
                assert row["grip_compatible_asset"] == row["overlay"]
                assert row["handheld_anchor_px"] == [800, 800]
                assert row["front_grip_target_height_px"] == 240
                assert bbox[2] > 700 and bbox[3] > 650, (item_id, bbox)
                assert bbox[2] <= CANVAS[0] - 24, (item_id, bbox)
            else:
                x0, y0, x1, y1 = row["template_box"]
                expected_box = (
                    round(x0 * CANVAS[0]),
                    round(y0 * CANVAS[1]),
                    round(x1 * CANVAS[0]),
                    round(y1 * CANVAS[1]),
                )
                assert bbox[0] >= expected_box[0] - 2, (item_id, bbox, expected_box)
                assert bbox[1] >= expected_box[1] - 2, (item_id, bbox, expected_box)
                assert bbox[2] <= expected_box[2] + 2, (item_id, bbox, expected_box)
                assert bbox[3] <= expected_box[3] + 2, (item_id, bbox, expected_box)
            face = tuple(
                (
                    FACE_SAFE[0] * CANVAS[0],
                    FACE_SAFE[1] * CANVAS[1],
                    FACE_SAFE[2] * CANVAS[0],
                    FACE_SAFE[3] * CANVAS[1],
                )
            )
            assert not (
                bbox[0] < face[2]
                and bbox[2] > face[0]
                and bbox[1] < face[3]
                and bbox[3] > face[1]
            ), item_id


def test_every_icon_is_real_transparent_svg_without_baked_ui_text():
    for item_id in EXPECTED:
        path = ICON_ROOT / f"{item_id}.svg"
        assert path.exists(), item_id
        raw = path.read_text(encoding="utf-8")
        root = ET.fromstring(raw)
        assert root.tag.endswith("svg")
        assert root.attrib["width"] == "256"
        assert root.attrib["height"] == "256"
        assert root.attrib["viewBox"] == "0 0 256 256"
        assert "<text" not in raw.lower()
        assert "checkerboard" not in raw.lower()
        assert re.search(r"<(path|circle|rect|ellipse|polygon)\b", raw)


def test_outputs_and_sources_are_unique_and_do_not_reuse_existing_bytes():
    manifest = load_manifest()
    overlay_hashes = [digest(OVERLAY_ROOT / f"{item_id}.png") for item_id in EXPECTED]
    icon_hashes = [digest(ICON_ROOT / f"{item_id}.svg") for item_id in EXPECTED]
    source_hashes = [digest(PACKAGE / "sources" / "generated_raw" / f"{item_id}.png") for item_id in EXPECTED]
    assert len(set(overlay_hashes)) == len(EXPECTED)
    assert len(set(icon_hashes)) == len(EXPECTED)
    assert len(set(source_hashes)) == len(EXPECTED)
    known_overlay_hashes = {
        digest(path)
        for path in (OVERLAY_ROOT).glob("*.png")
        if path.stem not in EXPECTED
    }
    known_icon_hashes = {
        digest(path)
        for path in (ICON_ROOT).glob("*.svg")
        if path.stem not in EXPECTED
    }
    assert not known_overlay_hashes.intersection(overlay_hashes)
    assert not known_icon_hashes.intersection(icon_hashes)
    report_rows = {row["item_id"]: row for row in json.loads(REPORT_PATH.read_text(encoding="utf-8"))["items"]}
    for item_id in EXPECTED:
        assert report_rows[item_id]["overlay_sha256"] == digest(OVERLAY_ROOT / f"{item_id}.png")
        assert report_rows[item_id]["icon_sha256"] == digest(ICON_ROOT / f"{item_id}.svg")
        assert report_rows[item_id]["source_sha256"] == digest(PACKAGE / "sources" / "generated_raw" / f"{item_id}.png")


def test_mobile_downscale_keeps_every_item_visible():
    for item_id in EXPECTED:
        with Image.open(OVERLAY_ROOT / f"{item_id}.png") as image:
            mobile = image.resize((264, 352), Image.Resampling.LANCZOS)
            bbox = mobile.getchannel("A").getbbox()
            assert bbox is not None, item_id
            assert bbox[2] - bbox[0] >= 3, item_id
            assert bbox[3] - bbox[1] >= 3, item_id
            assert sum(1 for alpha in mobile.getchannel("A").get_flattened_data() if alpha > 16) >= 20, item_id


def test_overlay_composites_on_shared_character_frame_without_face_identity_change():
    base_path = ROOT / "assets" / "hero" / "characters" / "wave2_p1" / "apprentice_p1.png"
    with Image.open(base_path) as base_image:
        base = base_image.convert("RGBA")
    assert base.size == CANVAS
    face_box = (
        round(FACE_SAFE[0] * CANVAS[0]),
        round(FACE_SAFE[1] * CANVAS[1]),
        round(FACE_SAFE[2] * CANVAS[0]),
        round(FACE_SAFE[3] * CANVAS[1]),
    )
    for item_id in EXPECTED:
        with Image.open(OVERLAY_ROOT / f"{item_id}.png") as overlay_image:
            composite = base.copy()
            composite.alpha_composite(overlay_image.convert("RGBA"))
        assert composite.crop(face_box).tobytes() == base.crop(face_box).tobytes(), item_id


def test_handheld_is_not_faked_and_no_production_authority_is_claimed():
    manifest = load_manifest()
    rows = manifest["items"]
    handheld = [row for row in rows if row["handheld_required"]]
    assert len(handheld) == 5
    assert all(row["layer"] == "MAIN_HAND_WEAPON" for row in handheld)
    assert all(row["grip_compatible_asset"] == row["overlay"] for row in handheld)
    assert manifest["technical_contract"]["handheld_contract"]["renderer_layer"] == "MAIN_HAND_WEAPON"
    assert manifest["authority_boundary"]["shop_or_reward_logic_changes"] is False
    assert manifest["authority_boundary"]["equipment_effects"] == "server EQUIPMENT_DEFS"


def test_qa_report_records_sixteen_real_outputs_and_no_placeholders():
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    assert report["canvas"] == list(CANVAS)
    assert report["placeholder_count"] == 0
    assert len(report["items"]) == 16
    assert {row["item_id"] for row in report["items"]} == set(EXPECTED)
    assert all(row["overlay_dimensions"] == list(CANVAS) for row in report["items"])
    assert Counter(row["source_classification"] for row in report["items"]) == {
        "ZONE_EXCLUSIVE": 10,
        "SHOP_EXCLUSIVE": 6,
    }
    assert sum(row["handheld_required"] for row in report["items"]) == 5
