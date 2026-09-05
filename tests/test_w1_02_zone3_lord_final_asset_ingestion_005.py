"""Focused W1-02 checks for the final Owner-approved Zone 3 Lord drop."""

from __future__ import annotations

import hashlib
from pathlib import Path

from PIL import Image, ImageChops

from adventure_zone3_monster_authority import ZONE3_LORD_ID, ZONE3_NORMAL_IDS
from zone3_runtime_asset_bindings import (
    OWNER_PACKAGE_SHA256,
    ZONE3_BATTLEFIELD_BOSS_PRESENTATION_BINDING,
    ZONE3_BATTLEFIELD_BOSS_RUNTIME_ID,
    ZONE3_ELITE_COUNT,
    ZONE3_LORD_PRESENTATION_SLOTS,
    resolve_zone3_lord_presentation,
)


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_OWNER_PACKAGE_SHA256 = (
    "7d57988635b20339f877817375f41260bd7aa6480aa2b3a6110a09ceb88e0b43"
)
EXPECTED_SLOT_TO_ASSET = {
    "Z3_LORD_RITUAL_KEY_ART": (
        "zone3_lord_01_ritual_key_art",
        (1448, 1086),
        "fa98c1fc2ccc351c37958a99e71da7f037bf967e8b4f948580a57424f0f314ee",
    ),
    "Z3_LORD_CHALLENGE_BACKPLATE": (
        "zone3_lord_02_challenge_backplate",
        (1024, 1536),
        "ea7d18554be39c956f374f7802006d1b4ffa2cb2958e661e8ebe3efc627c3704",
    ),
    "Z3_LORD_FAILURE_BACKPLATE": (
        "zone3_lord_03_failure_backplate",
        (1024, 1536),
        "9749b28e968e748adf578b32e5a5ff629deb69d1cbdb5321a69869f4dbad1c56",
    ),
    "Z3_FIRST_STAR_SUCCESS_BACKPLATE": (
        "zone3_lord_04_first_star_success_backplate",
        (1086, 1448),
        "30aded5b2adf5cf113b72d14fe111a91e16295ea58f5314ef8fba79b72133be5",
    ),
    "Z3_LORD_PORTRAIT": (
        "zone3_lord_05_lord_portrait",
        (1254, 1254),
        "cbcdda5c6c51f7f0d664710bd5ef15cd28601f6046c585670fcee753c9b1ce8c",
    ),
    "Z3_SUCCESS_LORD_PORTRAIT": (
        "zone3_lord_06_success_lord_portrait",
        (1254, 1254),
        "759dbcc871bf551d5ba63bbfbefad730d5be6293c7d4df57f37781613c40368a",
    ),
}


def _repo_path(runtime_path: str) -> Path:
    return ROOT / runtime_path.lstrip("/")


def test_final_owner_drop_has_exact_slot_mapping_and_lossless_runtime_decode():
    assert OWNER_PACKAGE_SHA256 == EXPECTED_OWNER_PACKAGE_SHA256
    assert len(ZONE3_LORD_PRESENTATION_SLOTS) == 6
    assert {
        slot.slot_id for slot in ZONE3_LORD_PRESENTATION_SLOTS
    } == set(EXPECTED_SLOT_TO_ASSET)

    for slot in ZONE3_LORD_PRESENTATION_SLOTS:
        stem, dimensions, source_sha256 = EXPECTED_SLOT_TO_ASSET[slot.slot_id]
        source_path = _repo_path(slot.source_path)
        runtime_path = _repo_path(slot.runtime_path)
        assert slot.lord_id == ZONE3_LORD_ID
        assert slot.source_path == f"/assets/e10/art/zone3/lord_trial/{stem}.png"
        assert slot.runtime_path == f"/assets/e10/art/zone3/lord_trial/{stem}.webp"
        assert slot.source_sha256 == source_sha256
        assert slot.source_dimensions == dimensions
        assert source_path.is_file()
        assert runtime_path.is_file()
        assert hashlib.sha256(source_path.read_bytes()).hexdigest() == source_sha256

        with Image.open(source_path) as source_image, Image.open(runtime_path) as runtime_image:
            source_image.load()
            runtime_image.load()
            assert source_image.format == "PNG"
            assert runtime_image.format == "WEBP"
            assert source_image.size == dimensions
            assert runtime_image.size == dimensions
            assert ImageChops.difference(source_image, runtime_image).getbbox() is None


def test_portrait_states_and_encounter_hierarchy_remain_distinct():
    slots = {slot.slot_id: slot for slot in ZONE3_LORD_PRESENTATION_SLOTS}
    assert slots["Z3_LORD_PORTRAIT"].source_path != slots["Z3_SUCCESS_LORD_PORTRAIT"].source_path
    assert slots["Z3_LORD_PORTRAIT"].runtime_path != slots["Z3_SUCCESS_LORD_PORTRAIT"].runtime_path
    assert ZONE3_BATTLEFIELD_BOSS_RUNTIME_ID != ZONE3_LORD_ID
    assert ZONE3_BATTLEFIELD_BOSS_PRESENTATION_BINDING.distinct_from_lord is True
    assert ZONE3_ELITE_COUNT == 0
    assert len(ZONE3_NORMAL_IDS) == 13
    assert ZONE3_LORD_ID not in ZONE3_NORMAL_IDS


def test_asset_load_state_cannot_create_gameplay_authority():
    slot_id = "Z3_LORD_PORTRAIT"
    loaded = resolve_zone3_lord_presentation(slot_id, asset_present=True)
    unavailable = resolve_zone3_lord_presentation(slot_id, asset_present=False)

    assert loaded.lord_id == unavailable.lord_id == ZONE3_LORD_ID
    assert loaded.gameplay_authority is False
    assert unavailable.gameplay_authority is False
    loaded_payload = loaded.to_payload()
    unavailable_payload = unavailable.to_payload()
    assert set(loaded_payload) - set(unavailable_payload) == {"runtime_asset_path"}
    assert unavailable_payload["fallback_policy"] == "HIDE_UNAVAILABLE_SAME_IDENTITY"
    for key in ("monster_id", "encounter_class", "max_hp", "attack"):
        assert key not in unavailable_payload
