"""Bounded WORLD package checks for Zone 3 final support art and shot binding."""

import hashlib
import json
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
WORLD_PACKAGE_PATH = ROOT / "assets/e10/art/zone3/zone3-world-asset-package.json"
CINEMATIC_PACKAGE_PATH = ROOT / "assets/e10/art/zone3/cinematic/zone3-cinematic-asset-package.json"

CINEMATIC_IDS = [f"ZONE3_CINEMATIC_SHOT{i:02d}" for i in range(1, 11)]
SUPPORT_IDS = [
    "ZONE3_WORLD_MAP_LANDMARK",
    "ZONE3_CAVE_PRIMARY_ENVIRONMENT_PLATE",
]
EXPECTED_IDS = CINEMATIC_IDS + SUPPORT_IDS

SUPPORT_RECORDS = {
    "ZONE3_WORLD_MAP_LANDMARK": {
        "source_sha256": "4c8b7f54578da1aee95eaf3bfb94f532af86d4167caec2105d112ed5716671b0",
        "source_bytes": 438330,
        "source_dimensions": (1254, 1254),
        "runtime_sha256": "c391799949568706ee58458421e1ec4c71161d5e3c71a8004ba2485a04e98db6",
        "runtime_bytes": 31410,
        "runtime_dimensions": (320, 320),
    },
    "ZONE3_CAVE_PRIMARY_ENVIRONMENT_PLATE": {
        "source_sha256": "dd40a804bbff23011cf682fbf2d3cd269b6ce30c73f093693fbea00929dd6d2e",
        "source_bytes": 331814,
        "source_dimensions": (1280, 853),
        "runtime_sha256": "d4c1de8f3e40305f490b52cfcafcca2fced018329fb3ec3e84443cc340b25862",
        "runtime_bytes": 144274,
        "runtime_dimensions": (1280, 720),
    },
}


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_world_manifest_has_exact_twelve_assets_and_no_lord_package():
    manifest = _load(WORLD_PACKAGE_PATH)
    assert manifest["expected_world_visual_asset_count"] == 12
    assert manifest["actual_world_visual_asset_count"] == 12
    assert [asset["ASSET_ID"] for asset in manifest["assets"]] == EXPECTED_IDS
    assert len({asset["ASSET_ID"] for asset in manifest["assets"]}) == 12
    assert manifest["category_counts"] == {
        "CINEMATIC_SHOT": 10,
        "WORLD_MAP_LANDMARK": 1,
        "WORLD_ENVIRONMENT_PLATE": 1,
    }
    assert manifest["lord_assets_included"] is False
    assert manifest["lord_asset_ids"] == []
    assert all(
        asset["TYPE"] in {"CINEMATIC_SHOT", "WORLD_MAP_LANDMARK", "WORLD_ENVIRONMENT_PLATE"}
        for asset in manifest["assets"]
    )
    assert all(asset["OWNER_APPROVED"] == "YES" for asset in manifest["assets"])


def test_cinematic_entries_match_the_existing_ten_shot_package():
    world = _load(WORLD_PACKAGE_PATH)
    cinematic = _load(CINEMATIC_PACKAGE_PATH)
    by_id = {asset["ASSET_ID"]: asset for asset in world["assets"]}
    for shot in cinematic["shots"]:
        asset_id = f"ZONE3_CINEMATIC_{shot['SHOT_ID']}"
        world_asset = by_id[asset_id]
        assert world_asset["SOURCE_PATH"] == shot["SOURCE_PATH"]
        assert world_asset["SOURCE_SHA256"] == shot["SOURCE_SHA256"]
        assert world_asset["RUNTIME_PATH"] == shot["RUNTIME_PATH"]
        assert world_asset["RUNTIME_SHA256"] == shot["RUNTIME_SHA256"]
        assert world_asset["SOURCE_DIMENSIONS"] == shot["SOURCE_DIMENSIONS"]
        assert world_asset["RUNTIME_DIMENSIONS"] == shot["RUNTIME_DIMENSIONS"]
        assert world_asset["PHASE"] == shot["PHASE"]


def test_all_source_masters_and_runtime_derivatives_resolve_to_recorded_hashes():
    manifest = _load(WORLD_PACKAGE_PATH)
    for asset in manifest["assets"]:
        source = ROOT / asset["SOURCE_PATH"]
        runtime = ROOT / asset["RUNTIME_PATH"]
        assert source.is_file(), asset["SOURCE_PATH"]
        assert runtime.is_file(), asset["RUNTIME_PATH"]
        assert source.stat().st_size == asset["SOURCE_BYTES"]
        assert runtime.stat().st_size == asset["RUNTIME_BYTES"]
        assert _sha256(source) == asset["SOURCE_SHA256"]
        assert _sha256(runtime) == asset["RUNTIME_SHA256"]
        with Image.open(source) as image:
            assert image.size == tuple(int(value) for value in asset["SOURCE_DIMENSIONS"].split("x"))
            image.verify()
        with Image.open(runtime) as image:
            assert image.size == tuple(int(value) for value in asset["RUNTIME_DIMENSIONS"].split("x"))
            assert image.format == "WEBP"
            image.verify()

    by_id = {asset["ASSET_ID"]: asset for asset in manifest["assets"]}
    for asset_id, expected in SUPPORT_RECORDS.items():
        asset = by_id[asset_id]
        assert asset["SOURCE_SHA256"] == expected["source_sha256"]
        assert asset["SOURCE_BYTES"] == expected["source_bytes"]
        assert tuple(int(value) for value in asset["SOURCE_DIMENSIONS"].split("x")) == expected[
            "source_dimensions"
        ]
        assert asset["RUNTIME_SHA256"] == expected["runtime_sha256"]
        assert asset["RUNTIME_BYTES"] == expected["runtime_bytes"]
        assert tuple(int(value) for value in asset["RUNTIME_DIMENSIONS"].split("x")) == expected[
            "runtime_dimensions"
        ]


def test_responsive_binding_recommendations_cover_all_shots():
    manifest = _load(WORLD_PACKAGE_PATH)
    recommendations = manifest["responsive_recommendations"]
    assert manifest["responsive_recommendation_count"] == 10
    assert [entry["SHOT"] for entry in recommendations] == [
        f"SHOT{i:02d}" for i in range(1, 11)
    ]
    required_fields = {
        "SHOT",
        "SOURCE_ASPECT",
        "DESKTOP_OBJECT_POSITION",
        "IPAD_LANDSCAPE_OBJECT_POSITION",
        "IPAD_PORTRAIT_OBJECT_POSITION",
        "MOBILE_OBJECT_POSITION",
        "IPAD_PORTRAIT_GENERIC_CROP_SAFE",
        "MOBILE_GENERIC_CROP_SAFE",
        "ESSENTIAL_LEFT_SUBJECT",
        "ESSENTIAL_CENTER_SUBJECT",
        "ESSENTIAL_RIGHT_SUBJECT",
        "RECOMMENDED_PRESENTATION_MODE",
    }
    assert all(required_fields <= entry.keys() for entry in recommendations)
    assert all(
        entry["RECOMMENDED_PRESENTATION_MODE"] in {
            "COVER",
            "CONTAIN",
            "CUSTOM_POSITION",
            "OTHER_EXISTING_SUPPORTED_MODE",
        }
        for entry in recommendations
    )
    assert sum(
        entry["IPAD_PORTRAIT_GENERIC_CROP_SAFE"] == "YES"
        for entry in recommendations
    ) == 2
    assert sum(entry["MOBILE_GENERIC_CROP_SAFE"] == "YES" for entry in recommendations) == 2
    assert sum(
        entry["IPAD_PORTRAIT_CUSTOM_POSITION_REQUIRED"]
        for entry in recommendations
    ) == manifest["ipad_portrait_custom_position_required_count"] == 2
    assert sum(
        entry["MOBILE_CUSTOM_POSITION_REQUIRED"] for entry in recommendations
    ) == manifest["mobile_custom_position_required_count"] == 2


def test_support_assets_are_clean_environment_surfaces_and_not_runtime_authority():
    manifest = _load(WORLD_PACKAGE_PATH)
    support = {
        asset["ASSET_ID"]: asset
        for asset in manifest["assets"]
        if asset["TYPE"] != "CINEMATIC_SHOT"
    }
    assert set(support) == set(SUPPORT_IDS)
    assert support["ZONE3_WORLD_MAP_LANDMARK"]["NO_TEXT"] is True
    assert support["ZONE3_WORLD_MAP_LANDMARK"]["NO_CHARACTER_AUTHORITY"] is True
    assert support["ZONE3_WORLD_MAP_LANDMARK"]["NO_UI"] is True
    plate = support["ZONE3_CAVE_PRIMARY_ENVIRONMENT_PLATE"]
    assert plate["NO_CHARACTER_AUTHORITY"] is True
    assert plate["NO_TEXT"] is True
    assert plate["NO_UI"] is True
    assert plate["RUNTIME_PATH"].endswith("zone3_environment_master.webp")
    for key in (
        "not_cinematic_completion_authority",
        "not_zone_clear_authority",
        "not_battlefield_boss_state",
        "not_lord_state",
    ):
        assert manifest["primary_environment_delivery"][key] is True
    assert manifest["battlefield_boss_context_plate"] == "NOT_REQUIRED_BY_DEFAULT"


def test_content_and_journey_boundaries_are_explicitly_preserved():
    manifest = _load(WORLD_PACKAGE_PATH)
    guards = manifest["content_guards"]
    for key in (
        "TEXT_NOT_BAKED_INTO_BASE_IMAGE",
        "ZONE_STATE_NOT_BAKED_INTO_BASE_IMAGE",
        "BOSS_STATE_NOT_BAKED_INTO_BASE_IMAGE",
        "ROUTE_NOT_BAKED_INTO_BASE_IMAGE",
        "REWARD_NOT_BAKED_INTO_BASE_IMAGE",
        "MAP_NODE_STATE_REMAINS_RUNTIME",
        "CTA_REMAINS_RUNTIME",
    ):
        assert guards[key] is True
    assert guards["GAMEPLAY_AUTHORITY_CHANGED"] is False
    journey = manifest["journey_dependency"]
    assert journey["candidate_head"] == "d5d3d3d08757d70e182d67a4547fbfbcaab8a561"
    assert journey["current_candidate_has_zone3_image_slot"] is False
    assert journey["current_candidate_has_per_shot_object_position_contract"] is False
    assert journey["responsive_presentation_dependency"] == "OPEN"
    assert journey["shared_shell_write_performed"] is False
