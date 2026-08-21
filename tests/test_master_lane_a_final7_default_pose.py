from __future__ import annotations

import json
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "assets/hero/characters/wave2_final7_default_pose_v1"
PACKAGE_DIR = ROOT / "docs/planning/rpg_wave2_master_lane_a_final7_default_pose"
BUILT_DIR = PACKAGE_DIR / "built"
CHARACTERS = (
    "river_wayfinder",
    "stone_caretaker",
    "duelist_scout",
    "bastion_warden",
    "forest_pathfinder",
    "archive_scholar",
    "worldkeeper",
)


def test_final7_manifest_is_presentation_only():
    manifest = json.loads((PACKAGE_DIR / "final7_default_pose_manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["characters"]) == 7
    assert manifest["functional_weapon_baked_in_base_art"] is False
    assert manifest["character_combat_authority"] == "NO"
    assert manifest["runtime_registration"] == "NOT_CHANGED"


def test_final7_png_and_webp_assets_close_the_frame_contract():
    for character_id in CHARACTERS:
        for suffix in ("png", "webp"):
            path = ASSET_DIR / f"{character_id}_default_pose_v1.{suffix}"
            with Image.open(path) as image:
                assert image.size == (1056, 1408)
                assert image.mode == "RGBA"
                bbox = image.getchannel("A").getbbox()
                assert bbox is not None
                assert bbox[1] == 49
                assert bbox[3] == 1373


def test_final7_owner_review_matrices_exist():
    for filename in (
        "FINAL7_DEFAULT_POSE_MATRIX.png",
        "FINAL7_DEFAULT_POSE_MOBILE_MATRIX.png",
        "FINAL7_DEFAULT_POSE_SCALE_LINEUP.png",
    ):
        path = BUILT_DIR / filename
        with Image.open(path) as image:
            assert image.mode == "RGBA"
            assert image.width > 0 and image.height > 0
