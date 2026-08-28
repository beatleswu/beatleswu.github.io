"""A035 player-visible Hero equipment presentation closure contracts."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HERO = (ROOT / "hero.html").read_text(encoding="utf-8")
APP = (ROOT / "app.py").read_text(encoding="utf-8")


def _between(source: str, start: str, end: str) -> str:
    return source.split(start, 1)[1].split(end, 1)[0]


def test_authoritative_equipment_surface_is_explicit_and_legacy_loadout_stays_off():
    assert 'data-loadout-effective="off"' in HERO
    assert 'data-authoritative-equipment-surface="true"' in HERO
    assert 'id="hero-equipment-functional-projection"' in HERO
    assert 'id="hero-equipment-functional-projection-list"' in HERO
    assert 'body[data-loadout-effective="off"] .legacy-loadout-section { display: none; }' in HERO
    assert 'const HERO_LEGACY_LOADOUT_EFFECTIVE = false;' in HERO
    assert 'if (isEquipment && !HERO_LEGACY_LOADOUT_EFFECTIVE)' in HERO
    assert 'if (HERO_LEGACY_LOADOUT_EFFECTIVE) Object.assign(body' in HERO


def test_functional_projection_has_exact_three_slots_and_fifteen_ids():
    assert "const FUNCTIONAL_HERO_SLOTS = new Set(['weapon', 'armor', 'accessory']);" in HERO
    ids = _between(HERO, 'const FUNCTIONAL_EQUIPMENT_IDS', 'const FUNCTIONAL_FULL_BODY_EQUIPMENT_IDS')
    expected = {
        "wooden_sword", "iron_sword", "fox_fang", "dragon_claw", "celestial_blade",
        "cloth_robe", "leather_armor", "fox_pelt", "dragon_scale", "void_mantle",
        "lucky_stone", "xp_amulet", "fox_mask", "dragon_eye", "go_stone_black",
    }
    assert set(re.findall(r"'([^']+)'", ids)) == expected
    assert len(re.findall(r"'([^']+)'", ids)) == 15
    assert "go_stone_black" not in _between(
        HERO, "const FUNCTIONAL_FULL_BODY_EQUIPMENT_IDS", "function normalizeHeroFunctionalEquipment"
    )


def test_functional_visual_projection_is_server_strict_and_full_body_only():
    assert HERO.count("function renderFunctionalWearableProjection()") == 1
    assert "presentation.mode !== 'FULL_BODY_OVERLAY'" in HERO
    assert "presentation.full_body_required !== true" in HERO
    assert "item.functional_equipment === true" in HERO
    assert "item.equipped === true" in HERO
    assert "/js/rpg_wave2_wearable_renderer.js" in HERO
    assert "window.GoOdysseyWearableRenderer" in HERO
    assert "renderer.renderSafe" in HERO
    assert "function functionalWearableLayerHTML" not in HERO
    assert "onerror=null;this.hidden=true;this.dataset.presentationState='fallback'" in HERO
    projection = _between(HERO, "function renderFunctionalEquipmentProjection()", "function renderAuthoritativeFunctionalEffects")
    assert projection.count("document.getElementById('") >= 6
    assert "hero-equipment-functional-projection-list" in projection
    assert "currently_equipped" not in projection


def test_legacy_visual_and_effect_consumption_are_hardened():
    clear = _between(HERO, "const LEGACY_COMBAT_GEAR_LAYER_SLOTS", "function clearLegacyCombatGearVisuals")
    assert clear.count("['char-") >= 7
    assert clear.count("['pv-") >= 7
    apply = _between(HERO, "function applyCombatGearVisuals()", "// Functional equipment presentation")
    assert "clearLegacyCombatGearVisuals();" in apply
    assert "renderFunctionalWearableProjection();" in apply
    wardrobe_visual = _between(HERO, "function applyEquippedVisuals", "// ── Inventory slot renderer")
    assert "i.owned === true && i.equipped === true" in wardrobe_visual
    assert "i.effects" not in wardrobe_visual
    effects = _between(HERO, "function renderAuthoritativeFunctionalEffects", "function renderCosmeticProjection")
    assert "active_effect_details" in effects
    assert "active_effects" in effects
    assert "go_stone_black" in effects
    assert "wardrobeItems" not in effects


def test_legacy_effect_items_only_allow_recovery_and_not_new_equip():
    legacy_item = _between(HERO, "function _wardrobeEquipmentItemHTML", "function renderWardrobeEquipmentProjections")
    assert "const legacyEquipBlocked = !item.equipped;" in legacy_item
    assert "const action = item.equipped ? 'unequip' : 'blocked';" in legacy_item
    handler = _between(HERO, "function handleInvClick", "// filter tab wiring")
    assert "if (wardrobeHasGameplayEffect(item))" in handler
    assert "if (!item.equipped)" in handler
    assert "Legacy effect gear cannot be newly equipped." in handler


def test_cosmetic_projection_stays_visual_only_and_refreshes_from_server():
    cosmetic = _between(HERO, "function renderCosmeticProjection()", "function combatGearButtonHTML")
    assert "item.owned === true" in cosmetic
    assert "!wardrobeHasGameplayEffect(item)" in cosmetic
    assert "Visual only · no combat authority" in cosmetic
    assert "fetch('/api/skills/profile'" in HERO
    assert "fetch('/api/player/inventory'" in HERO
    assert "async function refreshAuthoritativeHeroPresentation()" in HERO
    assert "cache: 'no-store'" in _between(HERO, "async function refreshAuthoritativeHeroPresentation()", "async function initPage")
    assert "refreshAuthoritativeHeroPresentation();" in _between(HERO, "document.addEventListener('visibilitychange'", "_nqCheckHeroCard")


def test_app_authority_boundaries_remain_unchanged():
    assert "player_inventory" in APP
    assert "_get_authoritative_combat_stats" in APP
    assert "player_appearance.combat_*" in APP
    assert "_get_appearance_effects" in APP
    assert "EQUIPMENT_CANONICAL_LOADOUT_ENABLED" in APP
    assert "go_stone_black" in APP
