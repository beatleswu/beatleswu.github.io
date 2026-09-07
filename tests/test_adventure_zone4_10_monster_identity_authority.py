import json
from dataclasses import fields
from pathlib import Path

from adventure_zone3_monster_authority import ZONE3_NORMAL_IDS
from adventure_zone4_10_monster_identity_authority import (
    AdventureZoneMonsterIdentity,
    RUNTIME_ADMISSION_PERFORMED,
    ZONE4_10_MONSTER_IDENTITIES,
    ZONE4_10_MONSTER_IDENTITY_BY_ID,
    ZONE4_10_MONSTER_IDENTITY_RECORD_COUNT,
)
from monster_identity import CANONICAL_MONSTER_IDENTITY_REGISTRY


REPO_ROOT = Path(__file__).resolve().parents[1]


EXPECTED_ROWS = (
    ("M034", "霧林精靈", "Mosswood Sprite", "Z4"),
    ("M035", "霧尾狐", "Mist-tail Fox", "Z4"),
    ("M036", "月葉蛾", "Moonleaf Moth", "Z4"),
    ("M037", "藤蔓爪獸", "Vineclaw Beast", "Z4"),
    ("M038", "苔背龜", "Mossback Turtle", "Z4"),
    ("M039", "露珠蜘蛛", "Dewdrop Spider", "Z4"),
    ("M040", "枯枝鹿", "Twig Deer", "Z4"),
    ("M041", "霧笛蛙", "Fogwhistle Frog", "Z4"),
    ("M042", "花冠毛蟲", "Bloomcrown Caterpillar", "Z4"),
    ("M043", "影步貓", "Shadowstep Cat", "Z4"),
    ("M044", "樹洞熊芽", "Hollowtree Cub", "Z4"),
    ("M045", "蘚帽小樹", "Mosscap Sapling", "Z4"),
    ("M046", "部落獸人", "Tribal Orc", "Z5"),
    ("M047", "炭鼓獸", "Ember Drum Brute", "Z5"),
    ("M048", "皮盾犀童", "Hide-shield Rhino", "Z5"),
    ("M049", "紅土角羊", "Redclay Ram", "Z5"),
    ("M050", "戰鼓蜥", "War Drum Lizard", "Z5"),
    ("M051", "羽飾獵犬", "Feathercrest Hound", "Z5"),
    ("M052", "石臼巨鼴", "Mortar Mole", "Z5"),
    ("M053", "銅環野豬", "Copperring Boar", "Z5"),
    ("M054", "篝火蜥蜴", "Campfire Skink", "Z5"),
    ("M055", "旗尾牛", "Banner-tail Bison", "Z5"),
    ("M056", "泥甲犰狳", "Mudplate Armadillo", "Z5"),
    ("M057", "鼓面龜", "Drumface Tortoise", "Z5"),
    ("M058", "飛龍", "Wyvern", "Z6"),
    ("M059", "熔岩翼蜥", "Lava-wing Drake", "Z6"),
    ("M061", "雲爪獅鷲", "Cloudclaw Gryphon", "Z6"),
    ("M062", "火花蜥蜴", "Sparkscale Gecko", "Z6"),
    ("M063", "玄岩甲獸", "Basalt Shellbeast", "Z6"),
    ("M064", "風脊飛蛇", "Windspine Serpent", "Z6"),
    ("M065", "焰尾狐龍", "Ember-tail Foxdragon", "Z6"),
    ("M066", "巖跳山羊", "Cliffskip Goat", "Z6"),
    ("M067", "硫磺蠑螈", "Sulfur Salamander", "Z6"),
    ("M068", "龍巢小暴龍", "Nestling Raptor", "Z6"),
    ("M069", "星火翼蝠", "Starflame Bat", "Z6"),
    ("M070", "熔金蜈蚣", "Molten Gold Centipede", "Z6"),
    ("M071", "塔影亡靈術士", "Tower Shade Caster", "Z7"),
    ("M072", "書頁狐", "Pagefox", "Z7"),
    ("M074", "星屑蛾", "Stardust Moth", "Z7"),
    ("M075", "墨池章魚", "Inkwell Octopus", "Z7"),
    ("M076", "浮空鐘蟲", "Floating Bell Bug", "Z7"),
    ("M077", "符文貓頭鷹", "Rune Owl", "Z7"),
    ("M078", "藥瓶咕", "Potion Gob", "Z7"),
    ("M079", "棱鏡蜥", "Prism Gecko", "Z7"),
    ("M080", "重力蟹", "Gravity Crab", "Z7"),
    ("M081", "卷軸龜", "Scrollback Turtle", "Z7"),
    ("M082", "天文蟲", "Astrolabe Beetle", "Z7"),
    ("M083", "雲階羊", "Cloudstep Ram", "Z7"),
    ("M084", "前線鐵甲騎", "Frontline Iron Knight", "Z8"),
    ("M085", "黑門獵犬", "Blackgate Hound", "Z8"),
    ("M086", "破盾甲蟲", "Breakshield Beetle", "Z8"),
    ("M087", "斷旗石獸", "Bannerbreak Stonebeast", "Z8"),
    ("M089", "鋼齒鬣狗", "Steelfang Hyena", "Z8"),
    ("M090", "城垛蜥", "Battlement Lizard", "Z8"),
    ("M092", "鐵輪犀", "Ironwheel Rhino", "Z8"),
    ("M093", "烽火蠍", "Beacon Scorpion", "Z8"),
    ("M095", "黑曜傀儡", "Obsidian Automaton", "Z8"),
    ("M096", "裂牆熊", "Wallbreak Bear", "Z8"),
    ("M097", "斥候鷹獸", "Scout Hawkbeast", "Z8"),
    ("M098", "風暴祈鳥", "Stormpray Bird", "Z9"),
    ("M099", "極光蛇", "Aurora Serpent", "Z9"),
    ("M101", "雲穹鯨", "Skyvault Whale", "Z9"),
    ("M102", "星環猿", "Star-ring Ape", "Z9"),
    ("M103", "裂虹鷹", "Riftbow Eagle", "Z9"),
    ("M104", "月蝕蟲", "Moon-eclipse Mantis", "Z9"),
    ("M106", "星砂狼", "Starsand Wolf", "Z9"),
    ("M108", "雷晶螳螂", "Thundercrystal Mantis", "Z9"),
    ("M109", "蒼穹水母", "Firmament Jelly", "Z9"),
    ("M111", "碎星犀", "Starshard Rhino", "Z9"),
    ("M073", "黃銅魔像", "Brass Golem", "Z10"),
    ("M112", "古殿碑靈", "Ancient Temple Idol", "Z10"),
    ("M113", "時痕石龜", "Timeworn Stone Turtle", "Z10"),
    ("M114", "終焉門獸", "Endgate Beast", "Z10"),
    ("M115", "古鐘巨蟲", "Ancient Bell Crawler", "Z10"),
    ("M116", "白曜甲蟲", "Ivorylight Beetle", "Z10"),
    ("M117", "黑砂獵犬", "Blacksand Hound", "Z10"),
    ("M118", "遺跡殼獸", "Relic Shellbeast", "Z10"),
    ("M119", "靜默碑靈", "Silent Tabletling", "Z10"),
    ("M120", "萬年根獸", "Evergreen Rootbeast", "Z10"),
)


def test_exact_79_identity_records_and_assignments():
    actual = tuple(
        (
            identity.monster_id,
            identity.canonical_name_zh,
            identity.canonical_name_en,
            identity.zone_key,
        )
        for identity in ZONE4_10_MONSTER_IDENTITIES
    )

    assert ZONE4_10_MONSTER_IDENTITY_RECORD_COUNT == 79
    assert len(actual) == 79
    assert len({row[0] for row in actual}) == 79
    assert actual == EXPECTED_ROWS
    assert set(ZONE4_10_MONSTER_IDENTITY_BY_ID) == {row[0] for row in EXPECTED_ROWS}


def test_m073_planning_record_is_reconciled_to_z10():
    candidate_path = REPO_ROOT / "docs" / "planning" / "art_120_monster_roster_candidate.json"
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    records = [row for row in candidate["roster"] if row["MONSTER_ID"] == "M073"]

    assert len(records) == 1
    record = records[0]
    assert record["ZH_NAME"] == "黃銅魔像"
    assert record["EN_NAME"] == "Brass Golem"
    assert record["ZONE"] == "Z10 上古終焉神殿"
    assert record["ZONE_ID"] == "Z10"
    assert "Z7 賢者之塔" not in json.dumps(record, ensure_ascii=False)
    assert record["OWNER_APPROVED"] == "NO"
    assert record["RUNTIME_ID"] is None
    assert record["RUNTIME_MAPPED"] == "NO"


def test_identity_authority_has_no_gameplay_or_battlefield_promotion():
    assert {field.name for field in fields(AdventureZoneMonsterIdentity)} == {
        "monster_id",
        "canonical_name_zh",
        "canonical_name_en",
        "zone_key",
    }
    required_record_keys = {
        "M_ID",
        "canonical_name_zh",
        "canonical_name_en",
        "zone_key",
    }
    assert all(set(identity.as_record()) == required_record_keys for identity in ZONE4_10_MONSTER_IDENTITIES)

    canonical_battlefield_ids = {
        identity.monster_id for identity in CANONICAL_MONSTER_IDENTITY_REGISTRY.entries
    }
    assert not canonical_battlefield_ids.intersection(ZONE4_10_MONSTER_IDENTITY_BY_ID)
    assert not any(
        identity.monster_id.startswith("legacy_bf_")
        for identity in ZONE4_10_MONSTER_IDENTITIES
    )
    assert RUNTIME_ADMISSION_PERFORMED is False


def test_zone3_identity_and_runtime_boundaries_remain_separate():
    assert tuple(ZONE3_NORMAL_IDS) == (
        "M022",
        "M023",
        "M024",
        "M025",
        "M026",
        "M027",
        "M028",
        "M029",
        "M030",
        "M031",
        "M032",
        "M033",
        "M060",
    )
    assert not set(ZONE3_NORMAL_IDS).intersection(ZONE4_10_MONSTER_IDENTITY_BY_ID)
    assert ZONE4_10_MONSTER_IDENTITY_BY_ID["M073"].zone_key == "Z10"
