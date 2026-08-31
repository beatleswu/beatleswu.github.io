"""Server-owned Adventure Normal bindings for the Zone 4 Misty Forest slice.

All twelve rows use existing M034-M045 identities. The module adds no Lord,
Elite, Boss, progression, reward, or schema behavior; it only prepares the
same explicit binding/profile seam that E055 established for Zone 3.
"""

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


ZONE4_KEY = "k11_15"
ZONE4_DISPLAY_KEY = "adventure.zone4.misty_forest"
ZONE4_LORD_ID = "misty_phantom_rabbit_king"
ZONE4_LORD_CLASSIFICATION = "LORD_ONLY"
ZONE4_ENCOUNTER_CLASS = "NORMAL"
ZONE4_BINDING_SOURCE = "adventure-zone4-misty-forest-monster-catalog"
ZONE4_BINDING_VERSION = "wave2.zone4.binding.v1"
ZONE4_PROFILE_VERSION = "wave2.zone4.normal.v1"

# E055's current Map Battle defaults are copied explicitly until an owner-
# approved Adventure balance authority replaces them. They are not inferred
# from the client, historical question counts, or Lord metadata.
ZONE4_NORMAL_MAX_HP = 100
ZONE4_NORMAL_ATTACK = 8

ZONE4_NORMAL_SPECS: tuple[AdventureMonsterSpec, ...] = (
    AdventureMonsterSpec("M034", "霧林精靈", "Mosswood Sprite", "forest_sprite", "/assets/monsters/forest_spirit_chibi.png"),
    AdventureMonsterSpec("M035", "霧尾狐", "Mist-tail Fox", "forest_fox", "/art/monsters/M035_mist_tail_fox.png"),
    AdventureMonsterSpec("M036", "月葉蛾", "Moonleaf Moth", "forest_moth", "/art/monsters/M036_moonleaf_moth.png"),
    AdventureMonsterSpec("M037", "藤蔓爪獸", "Vineclaw Beast", "vine_beast", "/art/monsters/M037_vineclaw_beast.png"),
    AdventureMonsterSpec("M038", "苔背龜", "Mossback Turtle", "moss_tortoise", "/art/monsters/M038_mossback_turtle.png"),
    AdventureMonsterSpec("M039", "露珠蜘蛛", "Dewdrop Spider", "dew_spider", "/art/monsters/M039_dewdrop_spider.png"),
    AdventureMonsterSpec("M040", "枯枝鹿", "Twig Deer", "twig_grazer", "/art/monsters/M040_twig_deer.png"),
    AdventureMonsterSpec("M041", "霧笛蛙", "Fogwhistle Frog", "mist_frog", "/art/monsters/M041_fogwhistle_frog.png"),
    AdventureMonsterSpec("M042", "花冠毛蟲", "Bloomcrown Caterpillar", "flower_caterpillar", "/art/monsters/M042_bloomcrown_caterpillar.png"),
    AdventureMonsterSpec("M043", "影步貓", "Shadowstep Cat", "moss_cat", "/art/monsters/M043_shadowstep_cat.png"),
    AdventureMonsterSpec("M044", "樹洞熊芽", "Hollowtree Cub", "tree_hollow_bear", "/art/monsters/M044_hollowtree_cub.png"),
    AdventureMonsterSpec("M045", "蘚帽小樹", "Mosscap Sapling", "forest_sapling", "/art/monsters/M045_mosscap_sapling.png"),
)

ZONE4_NORMAL_IDS = tuple(row.monster_id for row in ZONE4_NORMAL_SPECS)
ZONE4_PRESENTATION_ASSETS = {
    row.monster_id: row.presentation_asset for row in ZONE4_NORMAL_SPECS
}

ZONE4_AUTHORITY = build_adventure_zone_authority(
    AdventureZoneAuthoritySpec(
        zone_key=ZONE4_KEY,
        display_key=ZONE4_DISPLAY_KEY,
        binding_source=ZONE4_BINDING_SOURCE,
        binding_version=ZONE4_BINDING_VERSION,
        profile_version=ZONE4_PROFILE_VERSION,
        profile_namespace="adventure_z4",
        normal_max_hp=ZONE4_NORMAL_MAX_HP,
        normal_attack=ZONE4_NORMAL_ATTACK,
        combat_stat_source="WAVE2_ADVENTURE_ZONE4_MONSTER_CATALOG",
        combat_compatibility_mode="ADVENTURE_ZONE4_EXPLICIT_PROFILE",
        # Zone 4 inherits the existing stage-compatible legacy drop reference;
        # no new drop or reward channel is created by this foundation.
        drop_legacy_type="rabbit",
        normal_specs=ZONE4_NORMAL_SPECS,
    )
)

ZONE4_MONSTER_PROFILE_REGISTRY = ZONE4_AUTHORITY.profile_registry
ZONE4_DROP_PROFILE_REGISTRY = CANONICAL_DROP_PROFILE_REGISTRY
ZONE4_REWARD_PROFILE_REGISTRY = CANONICAL_REWARD_PROFILE_REGISTRY
ZONE4_BINDING_COUNT = ZONE4_AUTHORITY.binding_count

AdventureZone4MonsterBinding = AdventureMonsterBinding
Zone4MonsterAuthorityError = AdventureZoneAuthorityError


def get_zone4_binding(monster_id):
    return ZONE4_AUTHORITY.get_binding(monster_id)


def require_zone4_binding(monster_id):
    return ZONE4_AUTHORITY.require_binding(monster_id)


def select_zone4_binding(question_id):
    return ZONE4_AUTHORITY.select_binding(question_id)


def zone4_combat_profile(binding):
    return ZONE4_AUTHORITY.combat_profile(binding)


def encode_zone4_binding(binding):
    return ZONE4_AUTHORITY.encode_binding(binding)


def decode_zone4_binding(battle):
    return ZONE4_AUTHORITY.decode_binding(battle)


def zone4_presentation_for_battle(battle):
    return ZONE4_AUTHORITY.presentation_for_battle(battle)


def resolve_zone4_binding_for_battle(battle):
    return decode_zone4_binding(battle)


__all__ = [
    "AdventureZone4MonsterBinding",
    "ZONE4_AUTHORITY",
    "ZONE4_BINDING_COUNT",
    "ZONE4_BINDING_SOURCE",
    "ZONE4_BINDING_VERSION",
    "ZONE4_DISPLAY_KEY",
    "ZONE4_DROP_PROFILE_REGISTRY",
    "ZONE4_ENCOUNTER_CLASS",
    "ZONE4_KEY",
    "ZONE4_LORD_CLASSIFICATION",
    "ZONE4_LORD_ID",
    "ZONE4_MONSTER_PROFILE_REGISTRY",
    "ZONE4_NORMAL_ATTACK",
    "ZONE4_NORMAL_IDS",
    "ZONE4_NORMAL_MAX_HP",
    "ZONE4_NORMAL_SPECS",
    "ZONE4_PRESENTATION_ASSETS",
    "ZONE4_PROFILE_VERSION",
    "ZONE4_REWARD_PROFILE_REGISTRY",
    "Zone4MonsterAuthorityError",
    "decode_zone4_binding",
    "encode_zone4_binding",
    "get_zone4_binding",
    "require_zone4_binding",
    "resolve_zone4_binding_for_battle",
    "select_zone4_binding",
    "zone4_combat_profile",
    "zone4_presentation_for_battle",
]
