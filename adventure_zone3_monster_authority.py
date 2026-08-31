"""E055 Zone 3 content plugged into the reusable Adventure authority template."""

from __future__ import annotations

from adventure_zone_authority_template import (
    AdventureMonsterBinding,
    AdventureMonsterSpec,
    AdventureZoneAuthorityError,
    AdventureZoneAuthoritySpec,
    build_adventure_zone_authority,
)

from monster_drop_profiles import CANONICAL_DROP_PROFILE_REGISTRY
from monster_reward_profiles import CANONICAL_REWARD_PROFILE_REGISTRY


ZONE3_KEY = "k16_20"
ZONE3_DISPLAY_KEY = "adventure.zone3.goblin_cave"
ZONE3_LORD_ID = "goblin_centurion"
ZONE3_LORD_CLASSIFICATION = "LORD_ONLY"
ZONE3_ENCOUNTER_CLASS = "NORMAL"
ZONE3_BINDING_SOURCE = "adventure-zone3-monster-catalog"
ZONE3_BINDING_VERSION = "e055.zone3.binding.v1"
ZONE3_PROFILE_VERSION = "e055.zone3.normal.v1"
ZONE3_NORMAL_MAX_HP = 100
ZONE3_NORMAL_ATTACK = 8

ZONE3_NORMAL_SPECS: tuple[AdventureMonsterSpec, ...] = (
    AdventureMonsterSpec("M022", "洞穴獸人", "Cave Orc Grunt", "orc", "/assets/monsters/orc_grunt_chibi.png"),
    AdventureMonsterSpec("M023", "銅帽哥布林", "Coppercap Goblin", "goblin", "/art/monsters/M023_coppercap_goblin.png"),
    AdventureMonsterSpec("M024", "回音蝙蝠", "Echo Bat", "bat", "/art/monsters/M024_echo_bat.png"),
    AdventureMonsterSpec("M025", "鎬工鼴鼠", "Pickaxe Moleworker", "mole", "/art/monsters/M025_pickaxe_moleworker.png"),
    AdventureMonsterSpec("M026", "菌燈小鬼", "Fungus Lantern Imp", "imp", "/art/monsters/M026_fungus_lantern_imp.png"),
    AdventureMonsterSpec("M027", "繩梯蜥蜴", "Rope-Ladder Lizard", "lizard", "/art/monsters/M027_rope_ladder_lizard.png"),
    AdventureMonsterSpec("M028", "鐵桶甲蟲", "Ironbucket Beetle", "beetle", "/art/monsters/M028_ironbucket_beetle.png"),
    AdventureMonsterSpec("M029", "裂隙蛇", "Crevice Snake", "snake", "/art/monsters/M029_crevice_snake.png"),
    AdventureMonsterSpec("M030", "礦車爬蟲", "Cartcap Crawler", "crawler", "/art/monsters/M030_cartcap_crawler.png"),
    AdventureMonsterSpec("M031", "晶礦哥布林", "Crystal Ore Gob", "goblin", "/art/monsters/M031_crystal_ore_gob.png"),
    AdventureMonsterSpec("M032", "洞窟投石手", "Cavern Slinger", "goblin", "/art/monsters/M032_cavern_slinger.png"),
    AdventureMonsterSpec("M033", "鐘乳石巨龜", "Stalactite Tortoise", "tortoise", "/art/monsters/M033_stalactite_tortoise.png"),
    AdventureMonsterSpec("M060", "晶角蜥蜴", "Crystalhorn Lizard", "lizard", "/art/monsters/M060_crystalhorn_lizard.png"),
)

ZONE3_NORMAL_IDS = tuple(row.monster_id for row in ZONE3_NORMAL_SPECS)
ZONE3_PRESENTATION_ASSET_FILENAMES = tuple(
    row.presentation_asset.rsplit("/", 1)[-1]
    for row in ZONE3_NORMAL_SPECS
    if row.presentation_asset.startswith("/art/monsters/")
)

ZONE3_AUTHORITY = build_adventure_zone_authority(
    AdventureZoneAuthoritySpec(
        zone_key=ZONE3_KEY,
        display_key=ZONE3_DISPLAY_KEY,
        binding_source=ZONE3_BINDING_SOURCE,
        binding_version=ZONE3_BINDING_VERSION,
        profile_version=ZONE3_PROFILE_VERSION,
        profile_namespace="adventure_z3",
        normal_max_hp=ZONE3_NORMAL_MAX_HP,
        normal_attack=ZONE3_NORMAL_ATTACK,
        combat_stat_source="E055_ADVENTURE_ZONE3_MONSTER_CATALOG",
        combat_compatibility_mode="ADVENTURE_ZONE3_EXPLICIT_PROFILE",
        drop_legacy_type="goblin",
        normal_specs=ZONE3_NORMAL_SPECS,
    )
)

ZONE3_MONSTER_PROFILE_REGISTRY = ZONE3_AUTHORITY.profile_registry
ZONE3_DROP_PROFILE_REGISTRY = CANONICAL_DROP_PROFILE_REGISTRY
ZONE3_REWARD_PROFILE_REGISTRY = CANONICAL_REWARD_PROFILE_REGISTRY
ZONE3_BINDING_COUNT = ZONE3_AUTHORITY.binding_count

AdventureZone3MonsterBinding = AdventureMonsterBinding
Zone3MonsterAuthorityError = AdventureZoneAuthorityError


def get_zone3_binding(monster_id):
    return ZONE3_AUTHORITY.get_binding(monster_id)


def require_zone3_binding(monster_id):
    return ZONE3_AUTHORITY.require_binding(monster_id)


def select_zone3_binding(question_id):
    return ZONE3_AUTHORITY.select_binding(question_id)


def zone3_combat_profile(binding):
    return ZONE3_AUTHORITY.combat_profile(binding)


def encode_zone3_binding(binding):
    return ZONE3_AUTHORITY.encode_binding(binding)


def decode_zone3_binding(battle):
    return ZONE3_AUTHORITY.decode_binding(battle)


def zone3_presentation_for_battle(battle):
    return ZONE3_AUTHORITY.presentation_for_battle(battle)


def resolve_zone3_binding_for_battle(battle):
    return decode_zone3_binding(battle)


__all__ = [
    "AdventureZone3MonsterBinding",
    "ZONE3_AUTHORITY",
    "ZONE3_BINDING_COUNT",
    "ZONE3_BINDING_SOURCE",
    "ZONE3_BINDING_VERSION",
    "ZONE3_DISPLAY_KEY",
    "ZONE3_DROP_PROFILE_REGISTRY",
    "ZONE3_ENCOUNTER_CLASS",
    "ZONE3_KEY",
    "ZONE3_LORD_CLASSIFICATION",
    "ZONE3_LORD_ID",
    "ZONE3_MONSTER_PROFILE_REGISTRY",
    "ZONE3_NORMAL_ATTACK",
    "ZONE3_NORMAL_IDS",
    "ZONE3_NORMAL_MAX_HP",
    "ZONE3_NORMAL_SPECS",
    "ZONE3_PRESENTATION_ASSET_FILENAMES",
    "ZONE3_PROFILE_VERSION",
    "ZONE3_REWARD_PROFILE_REGISTRY",
    "Zone3MonsterAuthorityError",
    "decode_zone3_binding",
    "encode_zone3_binding",
    "get_zone3_binding",
    "require_zone3_binding",
    "resolve_zone3_binding_for_battle",
    "select_zone3_binding",
    "zone3_combat_profile",
    "zone3_presentation_for_battle",
]
