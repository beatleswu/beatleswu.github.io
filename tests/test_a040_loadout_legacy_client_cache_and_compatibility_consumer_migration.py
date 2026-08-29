"""A040 client-cache authority and compatibility-consumer contracts."""

from __future__ import annotations

import ast
import os
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "a040-legacy-cache-contract-test-secret")
import app as app_module  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "app.py").read_text(encoding="utf-8")
HERO = (ROOT / "hero.html").read_text(encoding="utf-8")
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")
CURRICULUM = (ROOT / "curriculum.html").read_text(encoding="utf-8")
BOT = (ROOT / "bot.html").read_text(encoding="utf-8")
COMMUNITY = (ROOT / "community.html").read_text(encoding="utf-8")
MESSAGES = (ROOT / "messages.html").read_text(encoding="utf-8")
GUARD = (ROOT / "js" / "hero_legacy_cache_guard.js").read_text(encoding="utf-8")
INVENTORY = (ROOT / "inventory.html").read_text(encoding="utf-8")

FUNCTIONAL_IDS = {
    "wooden_sword",
    "iron_sword",
    "fox_fang",
    "dragon_claw",
    "celestial_blade",
    "cloth_robe",
    "leather_armor",
    "fox_pelt",
    "dragon_scale",
    "void_mantle",
    "lucky_stone",
    "xp_amulet",
    "fox_mask",
    "dragon_eye",
    "go_stone_black",
}


def _function_source(source: str, name: str) -> str:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(source, node) or ""
    raise AssertionError(f"missing function: {name}")


def test_every_legacy_cache_consumer_is_bounded_or_removed():
    assert "JSON.parse(localStorage.getItem(COMBAT_STORAGE_KEY)" not in HERO
    assert "GoOdysseyLegacyHeroCache.discardFunctionalEquipment" in HERO
    assert "JSON.parse(localStorage.getItem(HERO_COMBAT_STORAGE_KEY)" not in INDEX
    assert "_serverHeroCharacter" in INDEX
    assert "GoOdysseyLegacyHeroCache.discardFunctionalEquipment" in INDEX
    assert "localStorage.removeItem('hero_combat_gear_v1')" in INDEX
    assert "localStorage.removeItem(COMBAT_STORAGE_KEY)" in HERO

    assert "GUILD_COMBAT_STORAGE_KEY" not in CURRICULUM
    assert "localStorage.getItem(GUILD_COMBAT_STORAGE_KEY" not in CURRICULUM
    assert "_guildServerCharacter" in CURRICULUM

    assert "hero_combat_gear_v1" not in BOT
    assert "localStorage.getItem('hero_combat_gear_v1'" not in BOT
    assert "localBotHeroGear" not in BOT

    # These social surfaces still consume server-serialized legacy appearance
    # fields for compatibility avatars; they do not read the browser cache.
    assert "combat_" in COMMUNITY and "combat_" in MESSAGES
    assert "localStorage.getItem('hero_combat_gear_v1'" not in COMMUNITY
    assert "localStorage.getItem('hero_combat_gear_v1'" not in MESSAGES


def test_server_effect_and_appearance_authority_remain_separate():
    review = _function_source(APP, "_srs_review_operation")
    effects = _function_source(APP, "_get_appearance_effects")
    combat = _function_source(APP, "_get_authoritative_combat_stats")

    assert "_get_appearance_effects" not in review
    assert "_safe_active_equipment_effect" in review
    assert "player_inventory" in combat
    assert "APPEARANCE_EFFECTS" in effects
    assert "compatibility projection" in effects
    assert "EQUIPMENT_DEFS" in effects
    assert "player_appearance.combat_*" in APP
    assert "_get_appearance_effects" in APP


def test_client_has_no_ownership_equip_or_damage_authority():
    client_sources = (HERO, INDEX, CURRICULUM, BOT)
    for source in client_sources:
        assert "dmg_bonus" not in source
        assert "player_dmg_reduce" not in source
        assert "EQUIPMENT_EFFECTS =" not in source
        assert "fetch('/api/player/inventory/equip'" not in source

    assert "_get_authoritative_combat_stats" in APP
    assert "BASELINE_DAMAGE" not in HERO
    assert "damage =" not in INDEX


def test_canonical_equipment_ids_and_permanent_locks_are_unchanged():
    definitions = {str(item["id"]): item for item in app_module.EQUIPMENT_DEFS}
    assert set(definitions) == FUNCTIONAL_IDS
    assert len(definitions) == 15
    assert app_module.INVENTORY_ONLY_EQUIPMENT_IDS == {"go_stone_black"}

    xp = app_module._functional_equipment_payload(definitions["xp_amulet"])
    stone = app_module._functional_equipment_payload(definitions["go_stone_black"])
    assert xp["active_effect_details"] == []
    assert stone["active_effect_details"] == []
    assert stone["presentation"]["family"] == "INVENTORY_ONLY"


def test_feature_gates_and_server_boundaries_remain_closed():
    assert "const FUNCTIONAL_EQUIPMENT_LOADOUT_ENABLED = false;" in INVENTORY
    assert "EQUIPMENT_CANONICAL_LOADOUT_ENABLED" in APP
    assert "CANONICAL_COIN_SHOP_PURCHASE_ENABLED" in APP
    assert "HERO_LEGACY_LOADOUT_EFFECTIVE = false" in HERO
    assert "purchase_equipment_with_coins" in APP
    assert "equipped=0" in APP


def test_legacy_compatibility_fields_are_not_removed_by_client_migration():
    assert "player_appearance.combat_*" in APP
    for field in (
        "combat_armor",
        "combat_weapon",
        "combat_cape",
        "combat_offhand",
        "combat_hat",
        "combat_pet",
        "combat_aura",
        "combat_acc",
    ):
        assert field in APP
    assert "DATA_MIGRATION" not in GUARD


def test_shared_guard_is_storage_only_and_never_creates_gameplay_state():
    assert "FUNCTIONAL_CACHE_FIELDS" in GUARD
    assert "discardFunctionalEquipment" in GUARD
    for forbidden in (
        "fetch(",
        "player_inventory",
        "dmg_bonus",
        "combat_stats",
    ):
        assert forbidden not in GUARD
