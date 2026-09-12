"""EQ-F's additive Equipment portfolio registry.

The original fifteen legacy definitions remain in ``app.py`` because the
existing C045 starter-catalog contract intentionally audits that historical
pool.  This module is the narrow, server-owned extension consumed by the
runtime as ``CANONICAL_EQUIPMENT_DEFS``.  It contains no ownership writes,
Shop prices, feature flags, or presentation authority.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from types import MappingProxyType
from typing import Any, Final


EQ_F_EFFECT_ALLOWLIST: Final[frozenset[str]] = frozenset(
    {
        "dmg_bonus",
        "dragon_dmg_bonus",
        "player_dmg_reduce",
        "crit_multiplier",
        "xp_bonus",
        "quest_xp_bonus",
        "loot_bonus",
        "sp_bonus",
    }
)

EQ_F_ZONE_EQUIPMENT_BY_ZONE: Final[Mapping[str, str]] = MappingProxyType(
    {
        "k26_30": "bamboo_shadow_blade",
        "k21_25": "jade_river_bead",
        "k16_20": "bamboo_scale_vest",
        "k11_15": "foxtail_traveler_mantle",
        "k6_10": "riverguard_coat",
        "k1_5": "riverstone_sabre",
        "d1_2": "cloudstep_star_lamellar",
        "d3_4": "constellation_focus_lens",
        "d5_6": "moonstar_rapier",
        "d7_plus": "odyssey_star_compass",
    }
)

EQ_F_SHOP_EQUIPMENT_IDS: Final[tuple[str, ...]] = (
    "emberline_cutlass",
    "starglass_needle",
    "weaveguard_vest",
    "mirrorfall_mantle",
    "copper_jade_talisman",
    "prism_focus_charm",
)

EQ_F_HANDHELD_WEAPON_IDS: Final[frozenset[str]] = frozenset(
    {
        "bamboo_shadow_blade",
        "riverstone_sabre",
        "moonstar_rapier",
        "emberline_cutlass",
        "starglass_needle",
    }
)

EQ_F_PRICE_AUTHORITY_STATUS: Final[str] = "LOCKED_C045"


def _definition(
    item_id: str,
    name: str,
    slot: str,
    rarity: str,
    desc: str,
    effects: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "id": item_id,
        "name": name,
        "slot": slot,
        "rarity": rarity,
        "icon": "✦",
        "desc": desc,
        "effects": dict(effects),
        # New EQ-F products are not Monster drops.  Keeping an empty source
        # list prevents them from entering the legacy random-drop pool.
        "drop_from": [],
        "drop_weight": 0,
    }


EQ_F_NEW_EQUIPMENT_DEFS: Final[tuple[Mapping[str, Any], ...]] = (
    _definition(
        "bamboo_shadow_blade",
        "竹影短刃",
        "weapon",
        "common",
        "竹影般輕巧的短刃，傷害 +6%。",
        {"dmg_bonus": 0.06},
    ),
    _definition(
        "jade_river_bead",
        "玉河珠",
        "accessory",
        "common",
        "河玉護珠，掉寶機率 +5%。",
        {"loot_bonus": 0.05},
    ),
    _definition(
        "bamboo_scale_vest",
        "竹鱗甲",
        "armor",
        "common",
        "竹片編成的護甲，受到傷害 -6%。",
        {"player_dmg_reduce": 0.06},
    ),
    _definition(
        "foxtail_traveler_mantle",
        "狐尾行旅披風",
        "armor",
        "rare",
        "旅人的狐尾披風，受到傷害 -8%，XP +5%。",
        {"player_dmg_reduce": 0.08, "xp_bonus": 0.05},
    ),
    _definition(
        "riverguard_coat",
        "河守長衣",
        "armor",
        "rare",
        "河守長衣，受到傷害 -10%，SP 每日上限 +8。",
        {"player_dmg_reduce": 0.10, "sp_bonus": 8},
    ),
    _definition(
        "riverstone_sabre",
        "河石軍刀",
        "weapon",
        "rare",
        "河石磨成的軍刀，傷害 +7%，對龍族額外 +6%。",
        {"dmg_bonus": 0.07, "dragon_dmg_bonus": 0.06},
    ),
    _definition(
        "cloudstep_star_lamellar",
        "雲步星札",
        "armor",
        "epic",
        "雲步星札，受到傷害 -12%，任務 XP +8%。",
        {"player_dmg_reduce": 0.12, "quest_xp_bonus": 0.08},
    ),
    _definition(
        "constellation_focus_lens",
        "星座聚焦鏡",
        "accessory",
        "epic",
        "星座聚焦鏡，暴擊倍率 ×1.20。",
        {"crit_multiplier": 1.20},
    ),
    _definition(
        "moonstar_rapier",
        "月星細劍",
        "weapon",
        "epic",
        "月星細劍，傷害 +10%，暴擊倍率 ×1.20。",
        {"dmg_bonus": 0.10, "crit_multiplier": 1.20},
    ),
    _definition(
        "odyssey_star_compass",
        "奧德賽星羅盤",
        "accessory",
        "legendary",
        "星羅盤，掉寶機率 +6%，SP 每日上限 +12。",
        {"loot_bonus": 0.06, "sp_bonus": 12},
    ),
    _definition(
        "emberline_cutlass",
        "赤焰航刃",
        "weapon",
        "rare",
        "赤焰航刃，傷害 +11%。",
        {"dmg_bonus": 0.11},
    ),
    _definition(
        "starglass_needle",
        "星璃針劍",
        "weapon",
        "epic",
        "星璃針劍，傷害 +16%，暴擊倍率 ×1.15。",
        {"dmg_bonus": 0.16, "crit_multiplier": 1.15},
    ),
    _definition(
        "weaveguard_vest",
        "織衛戰背",
        "armor",
        "rare",
        "織衛戰背，受到傷害 -11%。",
        {"player_dmg_reduce": 0.11},
    ),
    _definition(
        "mirrorfall_mantle",
        "鏡瀑披風",
        "armor",
        "epic",
        "鏡瀑披風，受到傷害 -16%，XP +4%。",
        {"player_dmg_reduce": 0.16, "xp_bonus": 0.04},
    ),
    _definition(
        "copper_jade_talisman",
        "銅玉護符",
        "accessory",
        "rare",
        "銅玉護符，掉寶機率 +8%。",
        {"loot_bonus": 0.08},
    ),
    _definition(
        "prism_focus_charm",
        "稜晶定心符",
        "accessory",
        "epic",
        "稜晶定心符，暴擊倍率 ×1.15。",
        {"crit_multiplier": 1.15},
    ),
)


_EQ_F_ENGLISH_NAMES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "bamboo_shadow_blade": "Bamboo Shadow Blade",
        "jade_river_bead": "Jade River Bead",
        "bamboo_scale_vest": "Bamboo Scale Vest",
        "foxtail_traveler_mantle": "Foxtail Traveler Mantle",
        "riverguard_coat": "Riverguard Coat",
        "riverstone_sabre": "Riverstone Sabre",
        "cloudstep_star_lamellar": "Cloudstep Star Lamellar",
        "constellation_focus_lens": "Constellation Focus Lens",
        "moonstar_rapier": "Moonstar Rapier",
        "odyssey_star_compass": "Odyssey Star Compass",
        "emberline_cutlass": "Emberline Cutlass",
        "starglass_needle": "Starglass Needle",
        "weaveguard_vest": "Weaveguard Vest",
        "mirrorfall_mantle": "Mirrorfall Mantle",
        "copper_jade_talisman": "Copper-Jade Talisman",
        "prism_focus_charm": "Prism Focus Charm",
    }
)

_EQ_F_PRESENTATION_BY_ID: Final[Mapping[str, Mapping[str, Any]]] = MappingProxyType(
    {
        "bamboo_shadow_blade": {"layer": "MAIN_HAND_WEAPON", "anchor": "main_hand"},
        "jade_river_bead": {"layer": "FRONT_ACCESSORY", "anchor": "chest"},
        "bamboo_scale_vest": {"layer": "TORSO_ARMOR", "anchor": "torso"},
        "foxtail_traveler_mantle": {"layer": "BACK_BODY", "anchor": "torso"},
        "riverguard_coat": {"layer": "TORSO_ARMOR", "anchor": "torso"},
        "riverstone_sabre": {"layer": "MAIN_HAND_WEAPON", "anchor": "main_hand"},
        "cloudstep_star_lamellar": {"layer": "TORSO_ARMOR", "anchor": "torso"},
        "constellation_focus_lens": {"layer": "FRONT_ACCESSORY", "anchor": "chest"},
        "moonstar_rapier": {"layer": "MAIN_HAND_WEAPON", "anchor": "main_hand"},
        "odyssey_star_compass": {"layer": "FRONT_ACCESSORY", "anchor": "chest"},
        "emberline_cutlass": {"layer": "MAIN_HAND_WEAPON", "anchor": "main_hand"},
        "starglass_needle": {"layer": "MAIN_HAND_WEAPON", "anchor": "main_hand"},
        "weaveguard_vest": {"layer": "TORSO_ARMOR", "anchor": "torso"},
        "mirrorfall_mantle": {"layer": "BACK_BODY", "anchor": "torso"},
        "copper_jade_talisman": {"layer": "FRONT_ACCESSORY", "anchor": "chest"},
        "prism_focus_charm": {"layer": "FRONT_ACCESSORY", "anchor": "chest"},
    }
)


def _presentation_record(item_id: str, definition: Mapping[str, Any]) -> dict[str, Any]:
    slot = str(definition["slot"])
    handheld = item_id in EQ_F_HANDHELD_WEAPON_IDS
    if slot == "weapon":
        family = "ONE_HAND_SWORD"
        wearable_class = "WEAPON_HANDHELD"
        mode = "HANDHELD_OVERLAY"
        layer = "MAIN_HAND_WEAPON"
    elif slot == "armor":
        family = "ARMOR_OVERLAY"
        wearable_class = "ROBE_OR_BODY_OVERLAY"
        mode = "FULL_BODY_OVERLAY"
        layer = _EQ_F_PRESENTATION_BY_ID[item_id]["layer"]
    else:
        family = "ACCESSORY_OVERLAY"
        wearable_class = "BODY_ACCESSORY"
        mode = "FULL_BODY_OVERLAY"
        layer = "FRONT_ACCESSORY"
    return {
        "name_en": _EQ_F_ENGLISH_NAMES[item_id],
        "desc_en": f"{_EQ_F_ENGLISH_NAMES[item_id]} — a server-owned Go Odyssey Equipment item.",
        "icon_key": f"rpg.equipment.functional.{item_id}.icon",
        "icon_path": f"/assets/hero/equipment/functional/{item_id}.svg",
        "presentation_mode": mode,
        "presentation_family": family,
        "weapon_family": family if slot == "weapon" else None,
        "presentation_anchor": _EQ_F_PRESENTATION_BY_ID[item_id]["anchor"],
        "presentation_layer": layer,
        "wearable_class": wearable_class,
        "asset_path": f"/assets/hero/equipment/wearables/overlays/{item_id}.png",
        "mask_requirement": "BASE_OCCLUSION",
        "full_body_required": True,
        "handheld_required": handheld,
        "source_classification": "ZONE_EXCLUSIVE"
        if item_id in EQ_F_ZONE_EQUIPMENT_BY_ZONE.values()
        else "SHOP_EXCLUSIVE",
    }


EQ_F_FUNCTIONAL_EQUIPMENT_ART: Final[Mapping[str, Mapping[str, Any]]] = MappingProxyType(
    {
        item_id: _presentation_record(item_id, definition)
        for item_id, definition in (
            (str(item["id"]), item) for item in EQ_F_NEW_EQUIPMENT_DEFS
        )
    }
)


def build_canonical_equipment_defs(
    legacy_defs: Iterable[Mapping[str, Any]],
) -> tuple[Mapping[str, Any], ...]:
    """Return the legacy definitions plus the locked EQ-F extension."""

    legacy = tuple(legacy_defs)
    legacy_ids = {str(item.get("id")) for item in legacy}
    overlap = legacy_ids.intersection(
        str(item["id"]) for item in EQ_F_NEW_EQUIPMENT_DEFS
    )
    if overlap:
        raise ValueError(f"EQ-F identities overlap legacy definitions: {sorted(overlap)}")
    return legacy + EQ_F_NEW_EQUIPMENT_DEFS


def validate_eq_f_portfolio(definitions: Iterable[Mapping[str, Any]]) -> None:
    """Fail closed if the runtime extension drifts from the locked contract."""

    rows = {str(item.get("id")): item for item in definitions}
    expected = {str(item["id"]): item for item in EQ_F_NEW_EQUIPMENT_DEFS}
    if set(rows) != set(expected):
        raise ValueError("EQ-F portfolio identities are incomplete or ambiguous")
    for item_id, expected_item in expected.items():
        item = rows[item_id]
        if item.get("slot") not in {"weapon", "armor", "accessory"}:
            raise ValueError(f"EQ-F slot is unsupported: {item_id}")
        if item.get("rarity") not in {"common", "rare", "epic", "legendary"}:
            raise ValueError(f"EQ-F rarity is unsupported: {item_id}")
        if set(item.get("effects") or {}) - EQ_F_EFFECT_ALLOWLIST:
            raise ValueError(f"EQ-F effect is unsupported: {item_id}")
        if dict(item.get("effects") or {}) != dict(expected_item["effects"]):
            raise ValueError(f"EQ-F effect values drifted: {item_id}")
    if sum(item.get("slot") == "weapon" for item in rows.values()) != 5:
        raise ValueError("EQ-F weapon count must remain five")
    if sum(item.get("slot") == "armor" for item in rows.values()) != 6:
        raise ValueError("EQ-F armor count must remain six")
    if sum(item.get("slot") == "accessory" for item in rows.values()) != 5:
        raise ValueError("EQ-F accessory count must remain five")


__all__ = [
    "EQ_F_EFFECT_ALLOWLIST",
    "EQ_F_FUNCTIONAL_EQUIPMENT_ART",
    "EQ_F_HANDHELD_WEAPON_IDS",
    "EQ_F_NEW_EQUIPMENT_DEFS",
    "EQ_F_PRICE_AUTHORITY_STATUS",
    "EQ_F_SHOP_EQUIPMENT_IDS",
    "EQ_F_ZONE_EQUIPMENT_BY_ZONE",
    "build_canonical_equipment_defs",
    "validate_eq_f_portfolio",
]
