"""A036 proof that effect presentation stays bound to canonical definitions."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "a036-effect-presentation-test-secret")
import app as app_module  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
HERO = (ROOT / "hero.html").read_text(encoding="utf-8")
INVENTORY = (ROOT / "inventory.html").read_text(encoding="utf-8")

FUNCTIONAL_EFFECT_MATRIX = {
    "wooden_sword": ("weapon", {"dmg_bonus": 0.05}, {"dmg_bonus"}),
    "iron_sword": ("weapon", {"dmg_bonus": 0.12}, {"dmg_bonus"}),
    "fox_fang": (
        "weapon",
        {"dmg_bonus": 0.20, "fox_dmg_bonus": 0.15},
        {"dmg_bonus", "fox_dmg_bonus"},
    ),
    "dragon_claw": (
        "weapon",
        {"dmg_bonus": 0.35, "dragon_dmg_bonus": 0.20},
        {"dmg_bonus", "dragon_dmg_bonus"},
    ),
    "celestial_blade": (
        "weapon",
        {"dmg_bonus": 0.60, "combo_multiplier_double": True},
        {"dmg_bonus", "combo_multiplier_double"},
    ),
    "cloth_robe": ("armor", {"player_dmg_reduce": 0.08}, {"player_dmg_reduce"}),
    "leather_armor": ("armor", {"player_dmg_reduce": 0.15}, {"player_dmg_reduce"}),
    "fox_pelt": (
        "armor",
        {"player_dmg_reduce": 0.25, "xp_bonus": 0.10},
        {"player_dmg_reduce", "xp_bonus"},
    ),
    "dragon_scale": (
        "armor",
        {"player_dmg_reduce": 0.40, "sp_bonus": 30},
        {"player_dmg_reduce", "sp_bonus"},
    ),
    "void_mantle": (
        "armor",
        {"player_dmg_reduce": 0.60, "negate_counter": True},
        {"player_dmg_reduce", "negate_counter"},
    ),
    "lucky_stone": ("accessory", {"loot_bonus": 0.10}, {"loot_bonus"}),
    "xp_amulet": ("accessory", {"xp_bonus": 0.20}, set()),
    "fox_mask": ("accessory", {"quest_xp_bonus": 0.25}, {"quest_xp_bonus"}),
    "dragon_eye": ("accessory", {"crit_multiplier": 3}, {"crit_multiplier"}),
    "go_stone_black": ("accessory", {"first_question_ace": True}, set()),
}


def test_functional_equipment_matrix_is_exactly_fifteen_canonical_rows():
    assert len(FUNCTIONAL_EFFECT_MATRIX) == 15
    assert set(FUNCTIONAL_EFFECT_MATRIX) == {
        str(item["id"]) for item in app_module.EQUIPMENT_DEFS
    }
    assert {
        slot: sum(1 for slot_value, _, _ in FUNCTIONAL_EFFECT_MATRIX.values() if slot_value == slot)
        for slot in ("weapon", "armor", "accessory")
    } == {"weapon": 5, "armor": 5, "accessory": 5}


def test_effect_matrix_values_and_labels_come_from_equipment_defs():
    for item_id, (slot, expected_defined, expected_active) in FUNCTIONAL_EFFECT_MATRIX.items():
        definition = app_module._EQUIP_MAP[item_id]
        payload = app_module._functional_equipment_payload(definition)
        assert payload["slot"] == slot
        assert payload["defined_effects"] == expected_defined
        active = {detail["key"]: detail["value"] for detail in payload["active_effect_details"]}
        assert active == {key: expected_defined[key] for key in expected_active}
        all_details = {
            detail["key"]: detail
            for detail in payload["active_effect_details"] + payload["unsupported_effects"]
        }
        assert set(all_details) == set(expected_defined)
        for key, value in expected_defined.items():
            detail = all_details[key]
            assert detail["label"]
            assert detail["label_en"]
            if key in expected_active:
                assert detail["status"] == "SERVER_EFFECTIVE"
                assert detail["value"] == value
            else:
                assert detail["status"] == "NOT_CURRENTLY_EFFECTIVE"
                assert detail["declared_value"] == value
                assert detail["declared_value_label"]
                assert detail["declared_value_label_en"]


def test_permanent_locks_and_trophy_are_explicitly_non_combat_in_presentation():
    xp = app_module._functional_equipment_payload(app_module._EQUIP_MAP["xp_amulet"])
    stone = app_module._functional_equipment_payload(app_module._EQUIP_MAP["go_stone_black"])
    assert xp["active_effect_details"] == []
    assert {detail["key"] for detail in xp["unsupported_effects"]} == {"xp_bonus"}
    assert stone["active_effect_details"] == []
    assert {detail["key"] for detail in stone["unsupported_effects"]} == {"first_question_ace"}
    assert stone["presentation"]["mode"] == "ICON_ONLY"
    assert stone["presentation"]["family"] == "INVENTORY_ONLY"


def test_frontend_uses_server_effect_details_without_a_duplicate_stat_table():
    for source in (HERO, INVENTORY):
        assert "active_effect_details" in source
        assert "EQUIPMENT_EFFECTS =" not in source
        for raw_key in (
            "dmg_bonus",
            "player_dmg_reduce",
            "negate_counter",
            "first_question_ace",
        ):
            assert raw_key not in source
    assert "server-defined equipment" in HERO
    assert "Server-defined effects only" in INVENTORY
    assert "declared_value_label" in INVENTORY
    assert "hero-functional-projection-state" in HERO


def test_go_stone_and_loadout_gate_are_closed_in_backpack_ui():
    assert "const FUNCTIONAL_EQUIPMENT_LOADOUT_ENABLED = false;" in INVENTORY
    assert "const FUNCTIONAL_INVENTORY_ONLY_IDS = new Set(['go_stone_black']);" in INVENTORY
    assert "No combat power" in INVENTORY
    assert "不提供戰鬥能力" in INVENTORY
    assert "action === 'equip' && !FUNCTIONAL_EQUIPMENT_LOADOUT_ENABLED" in INVENTORY
    assert "action.disabled = blockedNewEquip;" in INVENTORY
    assert "Equip unavailable" in INVENTORY
    assert "尚未開放裝備" in INVENTORY


def test_hero_summary_does_not_repeat_item_effects_as_another_stat_line():
    start = HERO.index("function renderHeroOverview()")
    end = HERO.index("async function hydrateAuthoritativeHeroPresentation", start)
    summary = HERO[start:end]
    assert "const equipmentNames = functionalEquipped.map(functionalProjectionName);" in summary
    assert "active_effect_details" not in summary
    assert "combat_stats" in summary


def test_i18n_and_cross_surface_regression_contracts_remain_present():
    assert "functionalEquipmentIsEn" in INVENTORY
    assert "functionalEffectLabel" in INVENTORY
    assert "functionalEffectValue" in INVENTORY
    assert "Equipped" in HERO and "已裝備" in HERO
    assert "Not currently effective" in HERO and "尚未啟用" in HERO
    assert "cache:'no-store'" in INVENTORY
    assert "cache: 'no-store'" in HERO
    assert "FUNCTIONAL_EQUIPMENT_LOADOUT_ENABLED = false" in INVENTORY
    assert "HERO_LEGACY_LOADOUT_EFFECTIVE = false" in HERO
