"""Focused acceptance checks for the Owner-approved Zone 3 cinematic package.

The source package is supplied as an external Owner artifact, so the targeted
run supplies W1_05_OWNER_PACKAGE_PATH.  The test intentionally does not copy
the art into the repository or modify runtime files.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import zipfile
from pathlib import Path

import pytest
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_SHA256 = "b3aa7e3e4d0d06c294d8f30eb3a05f5e9c5375721bbf4a4e16ccd6a1134ed1b8"
WORLD_CANDIDATE = "39c587a216f6cc13efe572066d9d8f0299960f1b"
WORLD_TREE = "676da3ddd4456b83aaa591e830a7adf4dab5c161"
WORLD_MANIFEST_PATH = "assets/e10/art/zone3/zone3-world-asset-package.json"
CINEMATIC_MANIFEST_PATH = "assets/e10/art/zone3/cinematic/zone3-cinematic-asset-package.json"

EXPECTED_TITLES = [
    "moving_refugees",
    "household_belongings",
    "meet_grik",
    "shrinking_living_space",
    "blocked_water_route",
    "last_door_centurion",
    "lord_trial_challenge",
    "fragile_truce",
    "stone_shard_handoff",
    "mist_forest_hook",
]

pytestmark = pytest.mark.skipif(
    not os.environ.get("W1_05_OWNER_PACKAGE_PATH"),
    reason="set W1_05_OWNER_PACKAGE_PATH to run the external Owner-artifact gate",
)


def package_path() -> Path:
    path = Path(os.environ["W1_05_OWNER_PACKAGE_PATH"])
    assert path.is_file(), path
    return path


def load_zip_manifest(zf: zipfile.ZipFile) -> dict:
    name = "ZONE3_FINAL_10SHOT_OWNER_APPROVED_manifest.json"
    return json.loads(zf.read(name).decode("utf-8"))


def git_bytes(ref: str, path: str) -> bytes:
    return subprocess.check_output(["git", "show", f"{ref}:{path}"], cwd=ROOT)


def load_world_manifest() -> dict:
    return json.loads(git_bytes(WORLD_CANDIDATE, WORLD_MANIFEST_PATH).decode("utf-8"))


def load_cinematic_manifest() -> dict:
    return json.loads(git_bytes(WORLD_CANDIDATE, CINEMATIC_MANIFEST_PATH).decode("utf-8"))


def test_owner_package_identity_and_exact_ten_shot_sequence() -> None:
    package = package_path()
    assert hashlib.sha256(package.read_bytes()).hexdigest() == PACKAGE_SHA256

    with zipfile.ZipFile(package) as zf:
        entries = [info for info in zf.infolist() if not info.is_dir()]
        manifest = load_zip_manifest(zf)
        shot_entries = [info.filename for info in entries if info.filename != "ZONE3_FINAL_10SHOT_OWNER_APPROVED_manifest.json"]

    assert len(entries) == 11
    assert manifest["package"] == "ZONE3_FINAL_10SHOT_OWNER_APPROVED"
    assert manifest["zone"] == 3
    assert manifest["shot_count"] == 10
    assert [shot["title"] for shot in manifest["shots"]] == EXPECTED_TITLES
    assert [shot["shot"] for shot in manifest["shots"]] == list(range(1, 11))
    assert len(shot_entries) == 10
    assert len(set(shot_entries)) == 10
    assert all("owner_approved" in name for name in shot_entries)
    assert manifest["notes"][0].startswith("Shots 7 and 8 are the final revised versions")


def test_all_owner_sources_match_package_metadata_and_decode() -> None:
    package = package_path()
    with zipfile.ZipFile(package) as zf:
        manifest = load_zip_manifest(zf)
        for shot in manifest["shots"]:
            raw = zf.read(shot["filename"])
            assert len(raw) == shot["bytes"]
            assert hashlib.sha256(raw).hexdigest() == shot["sha256"]
            with Image.open(io.BytesIO(raw)) as image:
                image.verify()
            with Image.open(io.BytesIO(raw)) as image:
                image.load()
                assert list(image.size) == [shot["width"], shot["height"]]


def test_owner_sources_match_world_candidate_bytes_and_source_identity() -> None:
    package = package_path()
    world = load_world_manifest()
    world_assets = {
        asset["SOURCE_FILENAME"]: asset
        for asset in world["assets"]
        if asset["TYPE"] == "CINEMATIC_SHOT"
    }

    tree = subprocess.check_output(
        ["git", "show", "-s", "--format=%T", WORLD_CANDIDATE], cwd=ROOT, text=True
    ).strip()
    assert tree == WORLD_TREE

    with zipfile.ZipFile(package) as zf:
        manifest = load_zip_manifest(zf)
        for shot in manifest["shots"]:
            world_asset = world_assets[shot["filename"]]
            package_bytes = zf.read(shot["filename"])
            world_bytes = git_bytes(WORLD_CANDIDATE, world_asset["SOURCE_PATH"])
            assert package_bytes == world_bytes
            assert world_asset["SOURCE_BYTES"] == shot["bytes"]
            assert world_asset["SOURCE_SHA256"] == shot["sha256"]
            assert world_asset["SOURCE_DIMENSIONS"] == f'{shot["width"]}x{shot["height"]}'


def test_world_responsive_manifest_covers_all_ten_shots() -> None:
    world = load_world_manifest()
    rows = world["responsive_recommendations"]
    assert len(rows) == 10
    assert [row["SHOT"] for row in rows] == [f"SHOT{i:02d}" for i in range(1, 11)]
    assert sum(row["IPAD_PORTRAIT_GENERIC_CROP_SAFE"] == "YES" for row in rows) == 2
    assert sum(row["MOBILE_GENERIC_CROP_SAFE"] == "YES" for row in rows) == 2
    assert sum(bool(row["IPAD_PORTRAIT_CUSTOM_POSITION_REQUIRED"]) for row in rows) == 2
    assert sum(bool(row["MOBILE_CUSTOM_POSITION_REQUIRED"]) for row in rows) == 2
    assert all(row["RECOMMENDED_PRESENTATION_MODE"] in {"CONTAIN", "CUSTOM_POSITION"} for row in rows)
    assert rows[-2]["IPAD_PORTRAIT_OBJECT_POSITION"] == "58% 50%"
    assert rows[-1]["IPAD_PORTRAIT_OBJECT_POSITION"] == "58% 50%"
    assert rows[-2]["MOBILE_OBJECT_POSITION"] == "58% 50%"
    assert rows[-1]["MOBILE_OBJECT_POSITION"] == "58% 50%"


def test_world_cinematic_contract_keeps_text_and_runtime_state_out_of_art() -> None:
    cinematic = load_cinematic_manifest()
    assert cinematic["owner_approved"] is True
    assert cinematic["source_shot_count"] == 10
    assert cinematic["runtime_derivative_count"] == 10
    assert cinematic["rejected_asset_paths"] == []
    assert cinematic["runtime_delivery"]["source_master_untouched"] is True
    assert cinematic["runtime_delivery"]["stretching_used"] is False
    assert cinematic["runtime_delivery"]["text_inserted"] is False
    guards = cinematic["content_guards"]
    assert guards["TEXT_NOT_BAKED_INTO_BASE_IMAGE"] is True
    assert guards["ZONE_STATE_NOT_BAKED_INTO_BASE_IMAGE"] is True
    assert guards["BOSS_STATE_NOT_BAKED_INTO_BASE_IMAGE"] is True
    assert guards["ROUTE_NOT_BAKED_INTO_BASE_IMAGE"] is True
    assert guards["REWARD_NOT_BAKED_INTO_BASE_IMAGE"] is True
    shard = cinematic["stone_shard_contract"]
    assert shard == {
        "shot": "SHOT09",
        "ordinary": True,
        "glowing": False,
        "irregular": True,
        "natural_marks_only": True,
        "magic_map": False,
        "rune_artifact": False,
        "gameplay_authority_object": False,
    }
