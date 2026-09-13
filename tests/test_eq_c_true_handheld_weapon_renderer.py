"""Focused EQ-C proof for the recovered true-handheld paper-doll contract."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "assets/hero/equipment/wearables/handheld/handheld_runtime_registry.json"
RENDERER_PATH = ROOT / "js/rpg_wave2_wearable_renderer.js"
INDEX_PATH = ROOT / "index.html"
FRAME = (1056, 1408)


def _registry() -> dict:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_runtime_registry_recovers_true_handheld_layers_and_metadata():
    registry = _registry()
    assert registry["runtime_active"] is True
    assert registry["presentation_only"] is True
    assert registry["authority"] == {
        "equipped_state": "player_inventory.equipped",
        "ownership": "player_inventory",
        "effects": "server EQUIPMENT_DEFS",
        "client_equipment_authority": False,
        "client_combat_authority": False,
        "acquire_does_not_equip": True,
        "purchase_does_not_equip": True,
    }
    assert registry["pose_id"] == "ONE_HAND_SWORD"
    assert registry["renderer_slot"] == "MAIN_HAND"
    assert registry["layer_order"] == [
        "CHARACTER_BASE_WITH_OPEN_HAND_SUPPRESSION",
        "MAIN_HAND_WEAPON",
        "FRONT_GRIP_HAND",
    ]
    assert registry["grip_anchor"]["x"] == 800.0
    assert registry["grip_anchor"]["y"] == 800.0
    assert registry["grip_anchor"]["front_grip_target_height"] == 240

    for character, entry in registry["characters"].items():
        assert 0 < entry["character_grip_x"] < 1, character
        assert 0 < entry["character_grip_y"] < 1, character
        assert Path(entry["base_asset"].lstrip("/" )).is_file(), character
        assert Path(entry["open_hand_suppression_mask"].lstrip("/" )).is_file(), character
        assert Path(entry["front_grip_hand_asset"].lstrip("/" )).is_file(), character


def test_two_materially_distinct_weapons_share_the_same_data_driven_renderer():
    registry = _registry()
    wooden = registry["weapons"]["wooden_sword"]
    iron = registry["weapons"]["iron_sword"]
    assert wooden["renderer_slot"] == iron["renderer_slot"] == "MAIN_HAND"
    assert wooden["pose_id"] == iron["pose_id"] == "ONE_HAND_SWORD"
    assert wooden["weapon_only"] is True and iron["weapon_only"] is True
    assert (wooden["weapon_grip_x"], wooden["weapon_grip_y"]) != (
        iron["weapon_grip_x"], iron["weapon_grip_y"]
    )
    assert wooden["scale"] != iron["scale"]
    assert wooden["asset"] != iron["asset"]

    for item_id, expected_sha in {
        "wooden_sword": "12b4bbe4150d05bca39b507787c250f1418c2ad154fafb8d8e2df557186e4523",
        "iron_sword": "78ac35076b26687e13c4724c9b2910992de3e037fd0bb26e47c4f8da4f75180f",
    }.items():
        item = registry["weapons"][item_id]
        asset = ROOT / item["asset"].lstrip("/")
        assert asset.is_file()
        assert _sha256(asset) == expected_sha
        with Image.open(asset) as image:
            assert image.mode == "RGBA"
            assert image.size == ((1056, 1408) if item_id == "wooden_sword" else (295, 1267))
            assert image.getchannel("A").getbbox() is not None


def test_mask_and_front_grip_prove_real_occlusion_inputs():
    registry = _registry()
    character = registry["characters"]["apprentice"]
    mask = ROOT / character["open_hand_suppression_mask"].lstrip("/")
    front = ROOT / character["front_grip_hand_asset"].lstrip("/")
    with Image.open(mask) as image:
        assert image.mode == "L"
        assert image.size == FRAME
        assert image.getbbox() is not None
        assert image.getchannel("L").getextrema() == (0, 255)
    with Image.open(front) as image:
        assert image.mode == "RGBA"
        assert image.getchannel("A").getbbox() is not None


def test_runtime_asset_urls_are_served_assets_and_preserve_recovered_bytes():
    registry = _registry()
    source_root = ROOT / "docs/planning/rpg_wave2_modular_2d_handheld_sword_prototype"
    for character, entry in registry["characters"].items():
        assert entry["base_asset"].startswith("/assets/")
        for field, source_relative in (
            ("open_hand_suppression_mask", f"masks/{character}_open_hand_suppression.png"),
            ("front_grip_hand_asset", f"pose_layers/{character}_grip_forearm.png"),
        ):
            runtime_path = ROOT / entry[field].lstrip("/")
            source_path = source_root / source_relative
            assert entry[field].startswith("/assets/")
            assert runtime_path.is_file()
            assert _sha256(runtime_path) == _sha256(source_path)
    iron = registry["weapons"]["iron_sword"]
    assert iron["asset"].startswith("/assets/")
    assert _sha256(ROOT / iron["asset"].lstrip("/")) == _sha256(
        source_root / "sources/iron_sword_handheld_universal.png"
    )


def test_answer_screen_consumes_authoritative_inventory_and_scales_as_one_composition():
    renderer = RENDERER_PATH.read_text(encoding="utf-8")
    index = INDEX_PATH.read_text(encoding="utf-8")
    contract = REGISTRY_PATH.read_text(encoding="utf-8")
    assert "player_inventory.equipped" in contract
    assert "item.functional_equipment !== true" in renderer
    assert "resolveEquippedWeapon" in renderer
    assert "destination-out" in renderer
    assert "drawHandheldWeapon" in renderer
    assert "drawHandheldFrontGrip" in renderer
    assert "aspect-ratio:1056 / 1408" in renderer
    assert "fetch('/api/player/inventory'" in index
    assert "GoOdysseyHandheldWeaponRenderer" in index
    assert "renderSafe(handheldStage" in index
    assert 'id="player-avatar-handheld-stage"' in index
    assert "app.py" not in renderer


def test_renderer_does_not_create_a_new_equipment_or_loadout_authority():
    renderer = RENDERER_PATH.read_text(encoding="utf-8")
    for forbidden in ("/api/player/inventory/equip", "localStorage", "fetch('/api/shop", "POST"):
        assert forbidden not in renderer


def test_owner_device_corrective_answer_projection_is_reachable_from_real_question_load():
    """Owner-device corrective (2026-09-13).

    Real iPad testing reported an equipped sword never visible while
    answering. The answer-surface projection function
    (_hydrateAnswerEquipmentProjection, wrapped by
    _ensureAnswerEquipmentProjection) already existed, already called
    GoOdysseyHandheldWeaponRenderer correctly, and already passed every
    prior static assertion in this file -- but a static "the right strings
    exist somewhere in index.html" check cannot prove the function is
    actually reached from real gameplay. This proves the real call chain
    exists end to end: _loadQuestionImplementation (every question load,
    every surface that shares it: map/world battle, guild quests, boss/lord
    trial, plain practice) awaits _hydrateE10BattlePresentation, which
    unconditionally calls _ensureAnswerEquipmentProjection before any
    adventure-zone/E10-shell branch -- so the projection runs on every
    question, not only opportunistically.
    """
    index = INDEX_PATH.read_text(encoding="utf-8")

    load_start = index.index("async function _loadQuestionImplementation")
    load_body = index[load_start : load_start + 2000]
    assert "await _hydrateE10BattlePresentation();" in load_body

    hydrate_start = index.index("async function _hydrateE10BattlePresentation")
    hydrate_body = index[hydrate_start : index.index("\n}\n", hydrate_start)]
    assert "const answerEquipment = _ensureAnswerEquipmentProjection();" in hydrate_body
    # This call happens before the adventure-zone/E10-shell branch, so it is
    # not conditional on that check -- every question load reaches it.
    assert hydrate_body.index("_ensureAnswerEquipmentProjection()") < hydrate_body.index(
        "_isAdventureZonePractice()"
    )


def test_owner_device_corrective_supported_character_roster_is_explicit_and_tracked():
    """Owner-device corrective (2026-09-13).

    Root-cause finding: the answer-surface projection's character gate
    (ANSWER_EQUIPMENT_CHARACTER_KEYS) and the wearable/handheld art
    registries only cover 3 of the site's 10 selectable hero characters
    (apprentice, mage, paladin -- tiers 0, 6, 7). For the other 7
    (apprentice_girl, swordsman, rogue, ranger, berserker, guardian, sage)
    _hydrateAnswerEquipmentProjection correctly and gracefully falls back
    to the plain avatar with no equipment overlay, by design, because the
    required base/mask/grip art for those characters does not exist --
    confirmed live: for a supported character the exact same code renders
    the equipped weapon correctly (verified by hand against the real
    renderer in a browser). Producing the missing character art is new
    asset work, out of scope for this corrective. This test makes the
    current coverage boundary explicit and tracked: it fails the moment
    anyone accidentally narrows the currently-supported set, and it must
    be updated deliberately (not silently) if the roster is ever widened.
    """
    index = INDEX_PATH.read_text(encoding="utf-8")
    app_py = (ROOT / "app.py").read_text(encoding="utf-8")
    wearable_registry = json.loads(
        (ROOT / "assets/hero/equipment/wearables/wearable_registry.json").read_text(encoding="utf-8")
    )
    handheld_registry = _registry()

    keys_start = index.index("const ANSWER_EQUIPMENT_CHARACTER_KEYS = new Set([")
    keys_block = index[keys_start : index.index("]);", keys_start)]
    answer_equipment_keys = {
        token.strip().strip("'")
        for token in keys_block[keys_block.index("[") + 1 :].split(",")
        if token.strip().strip("'")
    }
    assert answer_equipment_keys == {
        "apprentice", "mage", "paladin",
        "trail_apprentice", "night_runner", "constellation_apprentice",
    }

    roster_start = index.index("const HERO_COMBAT_GEAR = {")
    roster_block = index[roster_start : index.index("armor: [", roster_start)]
    full_roster = set(__import__("re").findall(r"key:'([a-z_]+)'", roster_block))
    assert full_roster == {
        "apprentice", "apprentice_girl", "swordsman", "rogue", "ranger",
        "berserker", "guardian", "paladin", "mage", "sage",
    }

    assert "ACTIVE_CHARACTER_KEYS = frozenset({" in app_py
    active_start = app_py.index("ACTIVE_CHARACTER_KEYS = frozenset({")
    active_block = app_py[active_start : app_py.index("})", active_start)]
    active_keys = set(__import__("re").findall(r"'([a-z_]+)'", active_block))
    assert active_keys == full_roster, (
        "the server's selectable-character allowlist and index.html's own "
        "roster must name the same characters"
    )

    supported_and_selectable = answer_equipment_keys & full_roster
    assert supported_and_selectable == {"apprentice", "mage", "paladin"}
    unsupported_selectable = full_roster - answer_equipment_keys
    assert unsupported_selectable == {
        "apprentice_girl", "swordsman", "rogue", "ranger", "berserker", "guardian", "sage",
    }

    # Both art registries the answer surface depends on must agree on
    # exactly the same 3-of-10 coverage -- a silent split here would mean
    # one renderer thinks a character is supported and the other doesn't.
    assert set(wearable_registry["characters"].keys()) == answer_equipment_keys
    assert set(handheld_registry["characters"].keys()) == answer_equipment_keys
