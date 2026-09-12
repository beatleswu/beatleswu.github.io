"""EQ-B proof for the shared answer-screen equipment projection."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
RENDERER = ROOT / "js" / "rpg_wave2_wearable_renderer.js"
REGISTRY = ROOT / "assets" / "hero" / "equipment" / "wearables" / "wearable_registry.json"


def test_answer_surface_mounts_the_existing_registry_renderer() -> None:
    html = INDEX.read_text(encoding="utf-8")

    assert '/js/rpg_wave2_wearable_renderer.js' in html
    assert 'id="player-answer-equipment-stage"' in html
    assert 'id="player-avatar-figure" data-answer-equipment-state="pending"' in html
    assert "fetch('/api/player/inventory'" in html
    assert "fetch('/api/player/appearance'" in html
    assert "renderer.renderSafe(stage, characterKey, equipped" in html
    assert "player_inventory.equipped" in html
    assert "refreshAnswerScreenEquipment" in html
    assert "document.visibilityState === 'visible'" in html
    assert "_ensureAnswerEquipmentProjection()" in html


def test_ordinary_and_adventure_question_hydration_share_the_same_answer_path() -> None:
    html = INDEX.read_text(encoding="utf-8")
    start = html.index("async function _hydrateE10BattlePresentation")
    body = html[start : start + 1_200]

    assert "const answerEquipment = _ensureAnswerEquipmentProjection();" in body
    assert "await answerEquipment;" in body
    assert "answerEquipment," in body
    assert "if (!_isAdventureZonePractice() || !_isE10BattleShell())" in body


def test_refresh_is_revision_guarded_and_old_combat_layers_cannot_duplicate() -> None:
    html = INDEX.read_text(encoding="utf-8")
    renderer = RENDERER.read_text(encoding="utf-8")

    assert "_answerEquipmentRenderRevision" in html
    assert "isCurrent: () => revision === _answerEquipmentRenderRevision" in html
    assert 'data-answer-equipment-state="ready"' in html
    assert ".player-combat-layer" in html
    assert "display: none !important" in html
    assert "typeof opts.isCurrent === 'function'" in renderer
    assert "reason: 'stale_render'" in renderer


def test_three_slot_legacy_compatible_items_are_registry_backed_and_mobile_visible() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    equipment = registry["equipment"]

    expected = {
        "wooden_sword": ("weapon", "BACK_WEAPON"),
        "dragon_scale": ("armor", "TORSO_ARMOR"),
        "dragon_eye": ("accessory", "FRONT_ACCESSORY"),
    }
    for item_id, (slot, layer) in expected.items():
        item = equipment[item_id]
        assert item["slot"] == slot
        assert item["layer"] == layer
        assert item["wearable_visibility"] != "INVENTORY_ONLY"
        assert item["mobile_visibility"] == "VISIBLE_AT_HERO_MOBILE_SIZE"
        assert item["frame"] == "PLAYER_FRAME_A_STANDARD_CHIBI"
        assert item["asset"]

    assert registry["provenance"]["hand_held_static_mode"] == "FORBIDDEN"
    assert registry["authority"]["ownership"] == "player_inventory"
    assert registry["authority"]["equipped"] == "player_inventory.equipped"
    assert registry["authority"]["presentation_only"] is True


def test_answer_projection_has_no_equipment_write_or_effect_activation_path() -> None:
    html = INDEX.read_text(encoding="utf-8")
    start = html.index("async function _hydrateAnswerEquipmentProjection")
    body = html[start : html.index("function _ensureAnswerEquipmentProjection", start)]

    assert "method: 'POST'" not in body
    assert "/api/player/inventory/equip" not in body
    assert "active_effects" not in body
    assert "player_inventory" in body
