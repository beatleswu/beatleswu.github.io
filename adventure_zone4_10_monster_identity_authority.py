"""Identity-only authority for the planned Zone 4-10 Adventure Monsters.

This module is the L2 content identity handoff for the 79 Owner-approved
Zone 4-10 records.  It deliberately does not admit a runtime roster and does
not own combat, reward, drop, question, Elite, Battlefield Boss, or Lord
semantics.  Those concerns remain separate L3 authorities.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Mapping


IDENTITY_AUTHORITY_VERSION: Final = "w2-b5.zone4-10.monster-identity.v1"
IDENTITY_PROVENANCE: Final = (
    "docs/planning/monster_art_content_zone_assignment_v1.json"
)
L3_IDENTITY_INPUT_READY: Final = True
RUNTIME_ADMISSION_PERFORMED: Final = False


@dataclass(frozen=True)
class AdventureZoneMonsterIdentity:
    """One stable content identity, without gameplay authority fields."""

    monster_id: str
    canonical_name_zh: str
    canonical_name_en: str
    zone_key: str

    @property
    def M_ID(self) -> str:
        """Return the planning vocabulary's explicit M-ID spelling."""

        return self.monster_id

    def as_record(self) -> dict[str, str]:
        """Return the minimal L3-consumable identity record."""

        return {
            "M_ID": self.monster_id,
            "canonical_name_zh": self.canonical_name_zh,
            "canonical_name_en": self.canonical_name_en,
            "zone_key": self.zone_key,
        }


ZONE4_10_MONSTER_IDENTITIES: tuple[AdventureZoneMonsterIdentity, ...] = (
    # Zone 4 — 迷霧森林
    AdventureZoneMonsterIdentity("M034", "霧林精靈", "Mosswood Sprite", "Z4"),
    AdventureZoneMonsterIdentity("M035", "霧尾狐", "Mist-tail Fox", "Z4"),
    AdventureZoneMonsterIdentity("M036", "月葉蛾", "Moonleaf Moth", "Z4"),
    AdventureZoneMonsterIdentity("M037", "藤蔓爪獸", "Vineclaw Beast", "Z4"),
    AdventureZoneMonsterIdentity("M038", "苔背龜", "Mossback Turtle", "Z4"),
    AdventureZoneMonsterIdentity("M039", "露珠蜘蛛", "Dewdrop Spider", "Z4"),
    AdventureZoneMonsterIdentity("M040", "枯枝鹿", "Twig Deer", "Z4"),
    AdventureZoneMonsterIdentity("M041", "霧笛蛙", "Fogwhistle Frog", "Z4"),
    AdventureZoneMonsterIdentity("M042", "花冠毛蟲", "Bloomcrown Caterpillar", "Z4"),
    AdventureZoneMonsterIdentity("M043", "影步貓", "Shadowstep Cat", "Z4"),
    AdventureZoneMonsterIdentity("M044", "樹洞熊芽", "Hollowtree Cub", "Z4"),
    AdventureZoneMonsterIdentity("M045", "蘚帽小樹", "Mosscap Sapling", "Z4"),
    # Zone 5 — 獸人部落
    AdventureZoneMonsterIdentity("M046", "部落獸人", "Tribal Orc", "Z5"),
    AdventureZoneMonsterIdentity("M047", "炭鼓獸", "Ember Drum Brute", "Z5"),
    AdventureZoneMonsterIdentity("M048", "皮盾犀童", "Hide-shield Rhino", "Z5"),
    AdventureZoneMonsterIdentity("M049", "紅土角羊", "Redclay Ram", "Z5"),
    AdventureZoneMonsterIdentity("M050", "戰鼓蜥", "War Drum Lizard", "Z5"),
    AdventureZoneMonsterIdentity("M051", "羽飾獵犬", "Feathercrest Hound", "Z5"),
    AdventureZoneMonsterIdentity("M052", "石臼巨鼴", "Mortar Mole", "Z5"),
    AdventureZoneMonsterIdentity("M053", "銅環野豬", "Copperring Boar", "Z5"),
    AdventureZoneMonsterIdentity("M054", "篝火蜥蜴", "Campfire Skink", "Z5"),
    AdventureZoneMonsterIdentity("M055", "旗尾牛", "Banner-tail Bison", "Z5"),
    AdventureZoneMonsterIdentity("M056", "泥甲犰狳", "Mudplate Armadillo", "Z5"),
    AdventureZoneMonsterIdentity("M057", "鼓面龜", "Drumface Tortoise", "Z5"),
    # Zone 6 — 龍之谷
    AdventureZoneMonsterIdentity("M058", "飛龍", "Wyvern", "Z6"),
    AdventureZoneMonsterIdentity("M059", "熔岩翼蜥", "Lava-wing Drake", "Z6"),
    AdventureZoneMonsterIdentity("M061", "雲爪獅鷲", "Cloudclaw Gryphon", "Z6"),
    AdventureZoneMonsterIdentity("M062", "火花蜥蜴", "Sparkscale Gecko", "Z6"),
    AdventureZoneMonsterIdentity("M063", "玄岩甲獸", "Basalt Shellbeast", "Z6"),
    AdventureZoneMonsterIdentity("M064", "風脊飛蛇", "Windspine Serpent", "Z6"),
    AdventureZoneMonsterIdentity("M065", "焰尾狐龍", "Ember-tail Foxdragon", "Z6"),
    AdventureZoneMonsterIdentity("M066", "巖跳山羊", "Cliffskip Goat", "Z6"),
    AdventureZoneMonsterIdentity("M067", "硫磺蠑螈", "Sulfur Salamander", "Z6"),
    AdventureZoneMonsterIdentity("M068", "龍巢小暴龍", "Nestling Raptor", "Z6"),
    AdventureZoneMonsterIdentity("M069", "星火翼蝠", "Starflame Bat", "Z6"),
    AdventureZoneMonsterIdentity("M070", "熔金蜈蚣", "Molten Gold Centipede", "Z6"),
    # Zone 7 — 賢者之塔
    AdventureZoneMonsterIdentity("M071", "塔影亡靈術士", "Tower Shade Caster", "Z7"),
    AdventureZoneMonsterIdentity("M072", "書頁狐", "Pagefox", "Z7"),
    AdventureZoneMonsterIdentity("M074", "星屑蛾", "Stardust Moth", "Z7"),
    AdventureZoneMonsterIdentity("M075", "墨池章魚", "Inkwell Octopus", "Z7"),
    AdventureZoneMonsterIdentity("M076", "浮空鐘蟲", "Floating Bell Bug", "Z7"),
    AdventureZoneMonsterIdentity("M077", "符文貓頭鷹", "Rune Owl", "Z7"),
    AdventureZoneMonsterIdentity("M078", "藥瓶咕", "Potion Gob", "Z7"),
    AdventureZoneMonsterIdentity("M079", "棱鏡蜥", "Prism Gecko", "Z7"),
    AdventureZoneMonsterIdentity("M080", "重力蟹", "Gravity Crab", "Z7"),
    AdventureZoneMonsterIdentity("M081", "卷軸龜", "Scrollback Turtle", "Z7"),
    AdventureZoneMonsterIdentity("M082", "天文蟲", "Astrolabe Beetle", "Z7"),
    AdventureZoneMonsterIdentity("M083", "雲階羊", "Cloudstep Ram", "Z7"),
    # Zone 8 — 魔王城前線
    AdventureZoneMonsterIdentity("M084", "前線鐵甲騎", "Frontline Iron Knight", "Z8"),
    AdventureZoneMonsterIdentity("M085", "黑門獵犬", "Blackgate Hound", "Z8"),
    AdventureZoneMonsterIdentity("M086", "破盾甲蟲", "Breakshield Beetle", "Z8"),
    AdventureZoneMonsterIdentity("M087", "斷旗石獸", "Bannerbreak Stonebeast", "Z8"),
    AdventureZoneMonsterIdentity("M089", "鋼齒鬣狗", "Steelfang Hyena", "Z8"),
    AdventureZoneMonsterIdentity("M090", "城垛蜥", "Battlement Lizard", "Z8"),
    AdventureZoneMonsterIdentity("M092", "鐵輪犀", "Ironwheel Rhino", "Z8"),
    AdventureZoneMonsterIdentity("M093", "烽火蠍", "Beacon Scorpion", "Z8"),
    AdventureZoneMonsterIdentity("M095", "黑曜傀儡", "Obsidian Automaton", "Z8"),
    AdventureZoneMonsterIdentity("M096", "裂牆熊", "Wallbreak Bear", "Z8"),
    AdventureZoneMonsterIdentity("M097", "斥候鷹獸", "Scout Hawkbeast", "Z8"),
    # Zone 9 — 諸神黃昏
    AdventureZoneMonsterIdentity("M098", "風暴祈鳥", "Stormpray Bird", "Z9"),
    AdventureZoneMonsterIdentity("M099", "極光蛇", "Aurora Serpent", "Z9"),
    AdventureZoneMonsterIdentity("M101", "雲穹鯨", "Skyvault Whale", "Z9"),
    AdventureZoneMonsterIdentity("M102", "星環猿", "Star-ring Ape", "Z9"),
    AdventureZoneMonsterIdentity("M103", "裂虹鷹", "Riftbow Eagle", "Z9"),
    AdventureZoneMonsterIdentity("M104", "月蝕蟲", "Moon-eclipse Mantis", "Z9"),
    AdventureZoneMonsterIdentity("M106", "星砂狼", "Starsand Wolf", "Z9"),
    AdventureZoneMonsterIdentity("M108", "雷晶螳螂", "Thundercrystal Mantis", "Z9"),
    AdventureZoneMonsterIdentity("M109", "蒼穹水母", "Firmament Jelly", "Z9"),
    AdventureZoneMonsterIdentity("M111", "碎星犀", "Starshard Rhino", "Z9"),
    # Zone 10 — 上古終焉神殿
    AdventureZoneMonsterIdentity("M073", "黃銅魔像", "Brass Golem", "Z10"),
    AdventureZoneMonsterIdentity("M112", "古殿碑靈", "Ancient Temple Idol", "Z10"),
    AdventureZoneMonsterIdentity("M113", "時痕石龜", "Timeworn Stone Turtle", "Z10"),
    AdventureZoneMonsterIdentity("M114", "終焉門獸", "Endgate Beast", "Z10"),
    AdventureZoneMonsterIdentity("M115", "古鐘巨蟲", "Ancient Bell Crawler", "Z10"),
    AdventureZoneMonsterIdentity("M116", "白曜甲蟲", "Ivorylight Beetle", "Z10"),
    AdventureZoneMonsterIdentity("M117", "黑砂獵犬", "Blacksand Hound", "Z10"),
    AdventureZoneMonsterIdentity("M118", "遺跡殼獸", "Relic Shellbeast", "Z10"),
    AdventureZoneMonsterIdentity("M119", "靜默碑靈", "Silent Tabletling", "Z10"),
    AdventureZoneMonsterIdentity("M120", "萬年根獸", "Evergreen Rootbeast", "Z10"),
)


ZONE4_10_MONSTER_IDENTITY_BY_ID: Mapping[
    str, AdventureZoneMonsterIdentity
] = MappingProxyType(
    {identity.monster_id: identity for identity in ZONE4_10_MONSTER_IDENTITIES}
)
ZONE4_10_MONSTER_IDENTITY_RECORD_COUNT: Final = len(ZONE4_10_MONSTER_IDENTITIES)


def _validate_identity_authority() -> None:
    """Fail closed if this identity-only table is edited inconsistently."""

    if ZONE4_10_MONSTER_IDENTITY_RECORD_COUNT != 79:
        raise ValueError("Zone 4-10 identity authority must contain exactly 79 records")
    if len(ZONE4_10_MONSTER_IDENTITY_BY_ID) != 79:
        raise ValueError("Zone 4-10 M-IDs must be unique")
    if any(
        set(identity.as_record())
        != {"M_ID", "canonical_name_zh", "canonical_name_en", "zone_key"}
        for identity in ZONE4_10_MONSTER_IDENTITIES
    ):
        raise ValueError("identity records must remain gameplay-authority free")
    if ZONE4_10_MONSTER_IDENTITY_BY_ID["M073"].zone_key != "Z10":
        raise ValueError("M073 must be assigned to Z10")


_validate_identity_authority()


def get_zone4_10_monster_identity(
    monster_id: str,
) -> AdventureZoneMonsterIdentity | None:
    """Return an identity record without admitting it to Adventure runtime."""

    return ZONE4_10_MONSTER_IDENTITY_BY_ID.get(str(monster_id).strip())


__all__ = [
    "AdventureZoneMonsterIdentity",
    "IDENTITY_AUTHORITY_VERSION",
    "IDENTITY_PROVENANCE",
    "L3_IDENTITY_INPUT_READY",
    "RUNTIME_ADMISSION_PERFORMED",
    "ZONE4_10_MONSTER_IDENTITIES",
    "ZONE4_10_MONSTER_IDENTITY_BY_ID",
    "ZONE4_10_MONSTER_IDENTITY_RECORD_COUNT",
    "get_zone4_10_monster_identity",
]
