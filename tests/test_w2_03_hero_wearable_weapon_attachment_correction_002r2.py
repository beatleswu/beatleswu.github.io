"""Focused contract for the W2-03 wooden-sword attachment correction."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "assets/hero/equipment/wearables/wearable_registry.json"
RUNTIME = ROOT / "js/rpg_wave2_wearable_renderer.js"
APP = ROOT / "app.py"
HERO = ROOT / "hero.html"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_wooden_sword_r2_path_is_superseded_by_owner_selected_hand_held_metadata():
    registry = _json(REGISTRY)
    wooden_sword = registry["equipment"]["wooden_sword"]
    assert wooden_sword["slot"] == "weapon"
    assert wooden_sword["anchor"] == "right_palm"
    assert wooden_sword["layer"] == "FRONT_WEAPON"
    assert wooden_sword["presentation_only"] is True
    assert wooden_sword["presentation_mode"] == "HAND_HELD"
    assert wooden_sword["presentation_attachment"] == "RIGHT_PALM"
    assert wooden_sword["presentation_transform"] == {
        "mode": "FRONT_WEAPON_HAND_ALIGNED",
        "offset_percent": {"x": 5, "y": 3},
        "rotation_deg": 0,
        "scale": 0.95,
        "transform_origin": "center center",
        "occlusion": "FRONT_WEAPON",
    }


def test_only_wooden_sword_receives_this_targeted_transform():
    registry = _json(REGISTRY)
    transformed = [
        item_id for item_id, item in registry["equipment"].items()
        if "presentation_transform" in item
    ]
    assert transformed == ["wooden_sword"]
    assert "presentation_transform" not in registry["equipment"]["dragon_scale"]
    assert "presentation_transform" not in registry["equipment"]["lucky_stone"]


def test_renderer_consumes_registry_transform_without_new_authority():
    runtime = RUNTIME.read_text(encoding="utf-8")
    assert "presentation?.presentation_transform" in runtime
    assert "CARRIED_AT_HIP" not in runtime
    assert "server_equipped_projection" in runtime
    assert "gameplayAuthority = 'none'" in runtime
    assert "method: 'POST'" not in runtime
    assert "player_inventory" not in runtime
    assert "localStorage" not in runtime
    assert "Math.abs(x) <= 30" in runtime
    assert "scale > 0.5 && scale <= 1.1" in runtime


def test_occlusion_and_accepted_armor_accessory_layers_are_preserved():
    registry = _json(REGISTRY)
    for item_id, layer in (("dragon_scale", "TORSO_ARMOR"), ("lucky_stone", "FRONT_ACCESSORY")):
        item = registry["equipment"][item_id]
        assert item["layer"] == layer
        assert item["frame"] == "PLAYER_FRAME_A_STANDARD_CHIBI"
        assert item["presentation_only"] is True
    assert registry["equipment"]["wooden_sword"]["presentation_transform"]["occlusion"] == "FRONT_WEAPON"


def test_replacement_and_authority_policies_remain_held():
    runtime = RUNTIME.read_text(encoding="utf-8")
    hero = HERO.read_text(encoding="utf-8")
    app = APP.read_text(encoding="utf-8")
    assert "ART_REPLACEMENT_REQUIRED_IDS = Object.freeze([])" in runtime
    assert "go_stone_black" in hero
    assert "fetch('/api/player/inventory/equip'" not in hero
    assert "def equip_item()" in app
