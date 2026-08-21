"""Deterministic contract checks for Lane A's remaining Sword Pose pack."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "docs/planning/rpg_wave2_master_lane_a_remaining_one_hand_sword_pose_002"
MANIFEST = PACK / "remaining14_one_hand_sword_pose_manifest.json"
BASE = "c36ce33763c80de7313922ad4096331ded540c18"
FRAME = (1056, 1408)
REMAINING = (
    "apprentice_girl",
    "swordsman",
    "rogue",
    "ranger",
    "berserker",
    "guardian",
    "sage",
    "river_wayfinder",
    "stone_caretaker",
    "duelist_scout",
    "bastion_warden",
    "forest_pathfinder",
    "archive_scholar",
    "worldkeeper",
)
APPROVED_SIX = (
    (
        "apprentice",
        "docs/planning/rpg_wave2_full_body_weapon_pose_system/variants/apprentice_one_hand_sword_pose.png",
    ),
    (
        "mage",
        "docs/planning/rpg_wave2_full_body_weapon_pose_system/variants/mage_one_hand_sword_pose.png",
    ),
    (
        "paladin",
        "docs/planning/rpg_wave2_full_body_weapon_pose_system/variants/paladin_one_hand_sword_pose.png",
    ),
    (
        "trail_apprentice",
        "docs/planning/rpg_wave2_full_body_weapon_pose_batch2/variants/trail_apprentice_one_hand_sword_pose.png",
    ),
    (
        "night_runner",
        "docs/planning/rpg_wave2_full_body_weapon_pose_batch2/variants/night_runner_one_hand_sword_pose.png",
    ),
    (
        "constellation_apprentice",
        "docs/planning/rpg_wave2_full_body_weapon_pose_batch2/variants/constellation_apprentice_one_hand_sword_pose.png",
    ),
)


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _base_blob(path: str) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{BASE}:{path}"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
    )
    return result.stdout


def test_scope_is_exactly_the_remaining_fourteen_and_is_presentation_only():
    report = _manifest()
    records = report["records"]
    assert report["production_base"] == BASE
    assert report["production_base_branch"] == "codex/rpg-wave2-one-hand-sword-pose-batch2-001"
    assert report["dependency_head_final7"] == "546fce85e27f1a6dbbdbf983e6374950f8df44a6"
    assert report["dependency_head_armor"] == "1be5d9523ffd9cc874081d343efc0e4bfa69fa1d"
    assert report["pose_family"] == "ONE_HAND_SWORD_POSE"
    assert report["method"] == "FULL_BODY_REDRAW"
    assert report["new_candidate_count"] == 14
    assert [record["character_id"] for record in records] == list(REMAINING)
    assert len({record["character_id"] for record in records}) == 14
    assert report["owner_pass_count_before_review"] == 6
    assert report["owner_pass_denominator"] == 20
    assert report["owner_status"] == "PRODUCTION_CANDIDATE_OWNER_REVIEW_REQUIRED"
    assert report["runtime_implementation"] is False
    assert report["local_hand_patch_used"] is False
    assert report["local_forearm_patch_used"] is False
    assert report["functional_equipment_authority"] == "player_inventory + server EQUIPMENT_DEFS"
    assert report["character_combat_authority"] == "NO"
    assert report["client_combat_authority"] == "NO"
    for record in records:
        assert record["pose_family"] == "ONE_HAND_SWORD_POSE"
        assert record["method"] == "FULL_BODY_REDRAW"
        assert record["presentation_only"] is True
        assert record["functional_weapon_baked_in"] is False
        assert record["local_hand_patch_used"] is False
        assert record["local_forearm_patch_used"] is False


def test_all_fourteen_sources_and_production_derivatives_are_closed_and_valid():
    report = _manifest()
    source_paths = []
    master_paths = []
    for record in report["records"]:
        source = ROOT / record["source"]
        master = ROOT / record["master_png"]
        derivative = ROOT / record["runtime_derivative_webp"]
        source_paths.append(record["source"])
        master_paths.append(record["master_png"])
        assert source.is_file(), record["character_id"]
        assert master.is_file(), record["character_id"]
        assert derivative.is_file(), record["character_id"]
        assert _sha256_file(source) == record["source_sha256"]

        with Image.open(master) as image:
            assert image.format == "PNG"
            assert image.mode == "RGBA"
            assert image.size == FRAME
            assert image.getchannel("A").getextrema() == (0, 255)
            bbox = image.getchannel("A").getbbox()
            assert bbox is not None
            assert bbox[1] == 49
            assert bbox[3] == 1373
            pixels = np.asarray(image)
            transparent = pixels[:, :, 3] == 0
            assert np.all(pixels[:, :, :3][transparent] == 0)
            assert pixels[0, 0, 3] == 0
            assert pixels[-1, -1, 3] == 0
            assert _sha256_file(master) == record["master_sha256"]

        with Image.open(derivative) as image:
            assert image.format == "WEBP"
            assert image.mode == "RGBA"
            assert image.size == FRAME
            assert image.getchannel("A").getbbox() is not None

    assert len(set(source_paths)) == 14
    assert len(set(master_paths)) == 14


def test_review_matrices_are_present_and_have_expected_readable_surfaces():
    report = _manifest()
    expected = {
        "desktop_matrix": (1328, 1914),
        "mobile_matrix": (568, 2634),
        "all20_scale_lineup": (1248, 1666),
    }
    for key, size in expected.items():
        path = ROOT / report["review_artifacts"][key]
        assert path.is_file(), key
        with Image.open(path) as image:
            assert image.format == "PNG"
            assert image.mode == "RGB"
            assert image.size == size


def test_existing_six_approved_variants_are_byte_unchanged_from_production_base():
    for character_id, relative_path in APPROVED_SIX:
        current = ROOT / relative_path
        assert current.is_file(), character_id
        assert _sha256_file(current) == _sha256_bytes(_base_blob(relative_path)), character_id
