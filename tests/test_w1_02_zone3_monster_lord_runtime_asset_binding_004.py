"""Focused W1-02 checks for the Zone 3 presentation binding contract."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from PIL import Image

from adventure_zone3_monster_authority import (
    ZONE3_KEY,
    ZONE3_LORD_ID,
    ZONE3_NORMAL_IDS,
    get_zone3_binding,
)
from zone3_runtime_asset_bindings import (
    OWNER_PACKAGE_SHA256,
    PRESENTATION_FALLBACK_HIDE,
    ZONE3_BATTLEFIELD_BOSS_ASSET,
    ZONE3_BATTLEFIELD_BOSS_PRESENTATION_BINDING,
    ZONE3_BATTLEFIELD_BOSS_RUNTIME_ID,
    ZONE3_ELITE_COUNT,
    ZONE3_LORD_ASSET_SLOT_COUNT,
    ZONE3_LORD_PRESENTATION_SLOTS,
    ZONE3_NORMAL_MONSTER_PRESENTATION_BINDINGS,
    ZONE3_NORMAL_MONSTER_PRESENTATION_BY_ID,
    resolve_zone3_lord_presentation,
)


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_NORMAL_IDS = (
    "M022",
    "M023",
    "M024",
    "M025",
    "M026",
    "M027",
    "M028",
    "M029",
    "M030",
    "M031",
    "M032",
    "M033",
    "M060",
)
EXPECTED_LORD_SLOT_PATHS = {
    "/assets/e10/art/zone3/lord_trial/zone3_lord_01_ritual_key_art.webp",
    "/assets/e10/art/zone3/lord_trial/zone3_lord_02_challenge_backplate.webp",
    "/assets/e10/art/zone3/lord_trial/zone3_lord_03_failure_backplate.webp",
    "/assets/e10/art/zone3/lord_trial/zone3_lord_04_first_star_success_backplate.webp",
    "/assets/e10/art/zone3/lord_trial/zone3_lord_05_lord_portrait.webp",
    "/assets/e10/art/zone3/lord_trial/zone3_lord_06_success_lord_portrait.webp",
}
EXPECTED_OWNER_PACKAGE_SHA256 = (
    "7d57988635b20339f877817375f41260bd7aa6480aa2b3a6110a09ceb88e0b43"
)
EXPECTED_LORD_ASSETS = {
    "Z3_LORD_RITUAL_KEY_ART": {
        "source_path": "/assets/e10/art/zone3/lord_trial/zone3_lord_01_ritual_key_art.png",
        "source_sha256": "fa98c1fc2ccc351c37958a99e71da7f037bf967e8b4f948580a57424f0f314ee",
        "dimensions": (1448, 1086),
        "runtime_path": "/assets/e10/art/zone3/lord_trial/zone3_lord_01_ritual_key_art.webp",
        "runtime_sha256": "0cadd81786f9fc76d2555917aca28bffd48326fd76298521e15dddac23cff423",
    },
    "Z3_LORD_CHALLENGE_BACKPLATE": {
        "source_path": "/assets/e10/art/zone3/lord_trial/zone3_lord_02_challenge_backplate.png",
        "source_sha256": "ea7d18554be39c956f374f7802006d1b4ffa2cb2958e661e8ebe3efc627c3704",
        "dimensions": (1024, 1536),
        "runtime_path": "/assets/e10/art/zone3/lord_trial/zone3_lord_02_challenge_backplate.webp",
        "runtime_sha256": "8c465f2f24a8adb15b81b40d2da5ce6bf16b5b73596ca9b4aa12d86163eee2d3",
    },
    "Z3_LORD_FAILURE_BACKPLATE": {
        "source_path": "/assets/e10/art/zone3/lord_trial/zone3_lord_03_failure_backplate.png",
        "source_sha256": "9749b28e968e748adf578b32e5a5ff629deb69d1cbdb5321a69869f4dbad1c56",
        "dimensions": (1024, 1536),
        "runtime_path": "/assets/e10/art/zone3/lord_trial/zone3_lord_03_failure_backplate.webp",
        "runtime_sha256": "73e5760c120f0c3bc0a4b720b7fbc096c6c1abb3d0d1c29a64c52b2d8f4aed0c",
    },
    "Z3_FIRST_STAR_SUCCESS_BACKPLATE": {
        "source_path": "/assets/e10/art/zone3/lord_trial/zone3_lord_04_first_star_success_backplate.png",
        "source_sha256": "30aded5b2adf5cf113b72d14fe111a91e16295ea58f5314ef8fba79b72133be5",
        "dimensions": (1086, 1448),
        "runtime_path": "/assets/e10/art/zone3/lord_trial/zone3_lord_04_first_star_success_backplate.webp",
        "runtime_sha256": "4cd9570539bf9253da800031c78465f90f18119db85654ced2375a181a15898f",
    },
    "Z3_LORD_PORTRAIT": {
        "source_path": "/assets/e10/art/zone3/lord_trial/zone3_lord_05_lord_portrait.png",
        "source_sha256": "cbcdda5c6c51f7f0d664710bd5ef15cd28601f6046c585670fcee753c9b1ce8c",
        "dimensions": (1254, 1254),
        "runtime_path": "/assets/e10/art/zone3/lord_trial/zone3_lord_05_lord_portrait.webp",
        "runtime_sha256": "18f157d094d3f5bf5807400def5738f43cefa3a5db1b443c71ed18c83edbe35e",
    },
    "Z3_SUCCESS_LORD_PORTRAIT": {
        "source_path": "/assets/e10/art/zone3/lord_trial/zone3_lord_06_success_lord_portrait.png",
        "source_sha256": "759dbcc871bf551d5ba63bbfbefad730d5be6293c7d4df57f37781613c40368a",
        "dimensions": (1254, 1254),
        "runtime_path": "/assets/e10/art/zone3/lord_trial/zone3_lord_06_success_lord_portrait.webp",
        "runtime_sha256": "13b4437bd72de85d51ba377264cdb8a11bac40b8e21d3e475cb511b4f19e7827",
    },
}


def _repo_path(runtime_path: str) -> Path:
    return ROOT / runtime_path.lstrip("/")


def test_exact_thirteen_existing_normal_monster_bindings_and_assets():
    assert ZONE3_NORMAL_IDS == EXPECTED_NORMAL_IDS
    assert tuple(
        row.monster_id for row in ZONE3_NORMAL_MONSTER_PRESENTATION_BINDINGS
    ) == EXPECTED_NORMAL_IDS
    assert len(ZONE3_NORMAL_MONSTER_PRESENTATION_BINDINGS) == 13
    assert len(ZONE3_NORMAL_MONSTER_PRESENTATION_BY_ID) == 13
    assert len({row.monster_id for row in ZONE3_NORMAL_MONSTER_PRESENTATION_BINDINGS}) == 13

    for row in ZONE3_NORMAL_MONSTER_PRESENTATION_BINDINGS:
        binding = get_zone3_binding(row.monster_id)
        assert binding is not None
        assert row.presentation_id == f"presentation_{binding.profile_id}"
        assert row.zone_key == ZONE3_KEY
        assert row.encounter_class == "NORMAL"
        assert row.runtime_asset_path == binding.presentation_asset
        assert row.asset_status == "CURRENT_CANONICAL"
        assert row.reuse_as_is is True
        assert row.redraw_required is False
        assert _repo_path(row.runtime_asset_path).is_file()


def test_battlefield_boss_is_current_and_distinct_from_lord_and_normals():
    boss = ZONE3_BATTLEFIELD_BOSS_PRESENTATION_BINDING
    assert ZONE3_BATTLEFIELD_BOSS_RUNTIME_ID == "legacy_bf_03_boss"
    assert boss.runtime_id == ZONE3_BATTLEFIELD_BOSS_RUNTIME_ID
    assert boss.presentation_id == ZONE3_BATTLEFIELD_BOSS_RUNTIME_ID
    assert boss.identity_zh == "LV3 做眼厚壁兵"
    assert boss.identity_en == "LV3 Eye-Shape Shield Guard"
    assert boss.encounter_class == "BATTLEFIELD_BOSS"
    assert boss.runtime_asset_path == ZONE3_BATTLEFIELD_BOSS_ASSET
    assert _repo_path(boss.runtime_asset_path).is_file()
    assert boss.runtime_id != ZONE3_LORD_ID
    assert boss.distinct_from_lord is True
    assert boss.runtime_asset_path not in {
        row.runtime_asset_path for row in ZONE3_NORMAL_MONSTER_PRESENTATION_BINDINGS
    }
    assert ZONE3_ELITE_COUNT == 0


def test_six_lord_slots_are_owner_approved_and_bound_without_placeholders():
    assert OWNER_PACKAGE_SHA256 == EXPECTED_OWNER_PACKAGE_SHA256
    assert ZONE3_LORD_ASSET_SLOT_COUNT == 6
    assert len(ZONE3_LORD_PRESENTATION_SLOTS) == 6
    assert len({slot.slot_id for slot in ZONE3_LORD_PRESENTATION_SLOTS}) == 6
    assert {slot.expected_runtime_path for slot in ZONE3_LORD_PRESENTATION_SLOTS} == {
        asset["runtime_path"] for asset in EXPECTED_LORD_ASSETS.values()
    }
    assert EXPECTED_LORD_SLOT_PATHS == {
        asset["runtime_path"] for asset in EXPECTED_LORD_ASSETS.values()
    }

    normal_paths = {
        row.runtime_asset_path for row in ZONE3_NORMAL_MONSTER_PRESENTATION_BINDINGS
    }
    for slot in ZONE3_LORD_PRESENTATION_SLOTS:
        expected = EXPECTED_LORD_ASSETS[slot.slot_id]
        assert slot.lord_id == ZONE3_LORD_ID
        assert slot.role in {
            "LORD_RITUAL_KEY_ART",
            "LORD_CHALLENGE_BACKPLATE",
            "LORD_FAILURE_BACKPLATE",
            "FIRST_STAR_SUCCESS_BACKPLATE",
            "LORD_PORTRAIT",
            "SUCCESS_LORD_PORTRAIT",
        }
        assert slot.source_path == expected["source_path"]
        assert slot.source_sha256 == expected["source_sha256"]
        assert slot.source_dimensions == expected["dimensions"]
        assert slot.master_dimensions == expected["dimensions"]
        assert slot.runtime_path == expected["runtime_path"]
        assert slot.runtime_dimensions == expected["dimensions"]
        assert slot.runtime_sha256 == expected["runtime_sha256"]
        assert slot.owner_approved is True
        assert slot.master_format == "PNG"
        assert slot.runtime_format == "WEBP"
        assert slot.asset_status == "OWNER_APPROVED_PRESENT"
        assert slot.present is True
        assert slot.pending is False
        assert slot.placeholder is False
        assert slot.gameplay_authority is False
        assert slot.expected_runtime_path not in normal_paths
        assert not slot.expected_runtime_path.startswith(
            ("/art/monsters/", "/assets/monsters/")
        )
        source_path = _repo_path(slot.source_path)
        runtime_path = _repo_path(slot.runtime_path)
        assert source_path.is_file()
        assert runtime_path.is_file()
        assert hashlib.sha256(source_path.read_bytes()).hexdigest() == expected["source_sha256"]
        assert hashlib.sha256(runtime_path.read_bytes()).hexdigest() == expected["runtime_sha256"]
        with Image.open(source_path) as source_image:
            assert source_image.format == "PNG"
            assert source_image.size == expected["dimensions"]
        with Image.open(runtime_path) as runtime_image:
            assert runtime_image.format == "WEBP"
            assert runtime_image.size == expected["dimensions"]


def test_owner_approved_lord_slots_resolve_to_their_bound_runtime_assets():
    for slot in ZONE3_LORD_PRESENTATION_SLOTS:
        result = resolve_zone3_lord_presentation(slot.slot_id)
        assert result.available is True
        assert result.runtime_asset_path == slot.runtime_path
        assert result.fallback_policy is None
        assert result.gameplay_authority is False


@pytest.mark.parametrize("slot_id", [slot.slot_id for slot in ZONE3_LORD_PRESENTATION_SLOTS])
def test_missing_lord_art_fails_closed_to_same_identity_presentation(slot_id):
    result = resolve_zone3_lord_presentation(slot_id, asset_present=False)
    payload = result.to_payload()

    assert result.available is False
    assert result.runtime_asset_path is None
    assert result.fallback_policy == PRESENTATION_FALLBACK_HIDE
    assert result.gameplay_authority is False
    assert payload["lord_id"] == ZONE3_LORD_ID
    assert payload["available"] is False
    assert payload["gameplay_authority"] is False
    assert "runtime_asset_path" not in payload
    assert "monster_id" not in payload
    assert "encounter_class" not in payload
    assert "max_hp" not in payload
    assert "attack" not in payload
    assert "reward_profile_id" not in payload


def test_lord_resolution_never_accepts_an_ordinary_monster_as_a_fallback():
    normal_paths = {
        row.runtime_asset_path for row in ZONE3_NORMAL_MONSTER_PRESENTATION_BINDINGS
    }
    for slot in ZONE3_LORD_PRESENTATION_SLOTS:
        resolved = resolve_zone3_lord_presentation(slot.slot_id, asset_present=False)
        assert resolved.runtime_asset_path is None
        assert slot.expected_runtime_path not in normal_paths
