import hashlib
import re
from collections import defaultdict


FAMILY_BY_STAGE = {
    "LV1": {
        "key": "slime_goblin",
        "label": "史萊姆 / 哥布林",
        "attribute": "低 HP，新手戰場",
        "weakness": "基本吃子、提子、逃跑",
        "battle_type": "slime",
        "normal": ["黏液斥候", "初階守衛", "氣息巡兵"],
        "chapter_boss": ["新手關卡守門者", "提子訓練守衛", "氣息隊長"],
        "book_boss": ["入門迷宮首領"],
    },
    "LV2": {
        "key": "goblin_bat",
        "label": "哥布林 / 洞窟蝙蝠",
        "attribute": "低 HP，高機動",
        "weakness": "雙叫吃、征子、連接",
        "battle_type": "cave_bat",
        "normal": ["洞窟哨兵", "雙擊小隊", "飛影巡兵"],
        "chapter_boss": ["雙叫吃隊長", "征子洞窟守衛"],
        "book_boss": ["洞窟戰術首領"],
    },
    "LV3": {
        "key": "orc_soldier",
        "label": "獸人小兵",
        "attribute": "中 HP",
        "weakness": "做眼、破眼、基礎死活",
        "battle_type": "orc_grunt",
        "normal": ["獸人斥候", "厚壁守兵", "死活訓練兵"],
        "chapter_boss": ["做眼厚壁兵", "破眼督軍"],
        "book_boss": ["獸人關卡首領"],
    },
    "LV4": {
        "key": "forest_spirit",
        "label": "森林精靈",
        "attribute": "速度與手筋",
        "weakness": "手筋、接觸戰、局部戰鬥",
        "battle_type": "forest_spirit",
        "normal": ["森靈斥候", "手筋巡兵", "霧林守衛"],
        "chapter_boss": ["霧林手筋師", "接觸戰術士"],
        "book_boss": ["森林試煉官"],
    },
    "LV5": {
        "key": "tribal_orc",
        "label": "部落獸人 / 懸賞首領",
        "attribute": "高 HP",
        "weakness": "攻防判斷、形勢轉換",
        "battle_type": "tribal_orc",
        "normal": ["部落獵手", "懸賞哨兵", "戰鼓守衛"],
        "chapter_boss": ["銀牌懸賞首領", "戰鼓隊長"],
        "book_boss": ["部落戰王"],
    },
    "LV6": {
        "key": "wyvern_deity",
        "label": "飛龍 / 低階神靈",
        "attribute": "BOSS 級",
        "weakness": "計算力、攻殺、全局方向",
        "battle_type": "wyvern",
        "normal": ["飛龍巡弋者", "低階神使", "龍谷守衛"],
        "chapter_boss": ["龍谷計算者", "低階神靈守門人"],
        "book_boss": ["飛龍試煉王"],
    },
    "LV7": {
        "key": "sage_mage_undead",
        "label": "賢者 / 魔法師 / 亡靈",
        "attribute": "魔法與詰棋",
        "weakness": "深讀死活、收束變化",
        "battle_type": "lich_mage",
        "normal": ["賢者侍從", "亡靈手筋士", "魔法巡守"],
        "chapter_boss": ["高塔術師", "死活殿守衛"],
        "book_boss": ["魔塔典籍守護者"],
    },
    "LV8": {
        "key": "knight_chaos",
        "label": "騎士 / 混沌領主",
        "attribute": "重甲與魔法",
        "weakness": "厚勢轉換、中盤攻防",
        "battle_type": "armored_knight",
        "normal": ["重甲騎士", "混沌侍從", "王城守衛"],
        "chapter_boss": ["皇家騎士長", "混沌戰術師"],
        "book_boss": ["混沌領主"],
    },
    "LV9": {
        "key": "gods",
        "label": "諸神",
        "attribute": "高壓終盤與全局掌控",
        "weakness": "精準判斷、官子、勝率感",
        "battle_type": "storm_deity",
        "normal": ["神域守衛", "命運巡察者", "雷霆神使"],
        "chapter_boss": ["命運試煉官", "神域審判者"],
        "book_boss": ["諸神試煉主"],
    },
    "LV10": {
        "key": "ancient_domain",
        "label": "上古終焉神殿",
        "attribute": "終局試煉",
        "weakness": "綜合讀棋、局勢掌控、極限判斷",
        "battle_type": "ancient_idol",
        "normal": ["上古神殿守衛", "終焉巡禮者", "古代意志"],
        "chapter_boss": ["上古終焉神殿", "終焉祭司"],
        "book_boss": ["終焉神"],
    },
}


ENCOUNTER_LABELS = {
    "normal": "普通遭遇",
    "chapter_boss": "章節 BOSS",
    "book_boss": "書本 BOSS",
}


def _source_book(q):
    source = str(q.get("source") or "")
    if source:
        return re.split(r"[\\/]", source, 1)[0].strip()
    return str(q.get("topic") or q.get("topic_en") or "Unknown Map").strip()


def _display_map_name(raw):
    raw = re.sub(r"^\s*\d+\s*", "", str(raw or "")).strip()
    return raw or "未命名地圖"


def _slug_source(raw):
    text = str(raw or "")
    if "｜" in text:
        text = text.split("｜")[-1]
    text = text.replace("Go -", "")
    text = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_").lower()
    if not text:
        text = hashlib.md5(str(raw).encode("utf-8")).hexdigest()[:10]
    return f"map_{text[:48]}"


def _chapter_key(q):
    value = str(q.get("level") or q.get("level_en") or "").strip()
    return value if value and value != "Unknown" else "未分章節"


def _order_key(q):
    sort_order = q.get("sort_order")
    try:
        sort_value = int(sort_order)
    except (TypeError, ValueError):
        sort_value = 999999
    return (sort_value, str(q.get("display_name") or ""), int(q.get("id") or 0))


def _pick(pool, seed):
    if not pool:
        return ""
    digest = hashlib.md5(str(seed).encode("utf-8")).hexdigest()
    return pool[int(digest[:8], 16) % len(pool)]


def family_for_question(q):
    stage = str(q.get("stage") or "LV2").upper().replace(" ", "")
    return FAMILY_BY_STAGE.get(stage, FAMILY_BY_STAGE["LV2"])


def enrich_monster_metadata(q):
    raw_book = _source_book(q)
    family = family_for_question(q)
    encounter_type = q.get("encounter_type") or "normal"
    boss_level = q.get("boss_level") or None
    name_pool = family.get(encounter_type) or family["normal"]
    monster_name = _pick(name_pool, f"{q.get('id')}::{encounter_type}::{raw_book}")

    q.update({
        "map_id": _slug_source(raw_book),
        "map_name": _display_map_name(raw_book),
        "map_chapter": _chapter_key(q),
        "monster_family": family["key"],
        "monster_family_label": family["label"],
        "monster_attribute": family["attribute"],
        "weakness_topic": family["weakness"],
        "battle_monster_type": family["battle_type"],
        "encounter_type": encounter_type,
        "encounter_label": ENCOUNTER_LABELS.get(encounter_type, "普通遭遇"),
        "boss_level": boss_level,
        "boss_title": "書本 BOSS" if encounter_type == "book_boss" else ("章節 BOSS" if encounter_type == "chapter_boss" else ""),
        "monster_name": monster_name,
    })
    return q


def mark_encounters(questions):
    for q in questions:
        q["encounter_type"] = "normal"
        q["boss_level"] = None
        enrich_monster_metadata(q)

    by_map = defaultdict(list)
    by_chapter = defaultdict(list)
    for q in questions:
        by_map[q["map_id"]].append(q)
        by_chapter[(q["map_id"], q["map_chapter"])].append(q)

    for chapter_questions in by_chapter.values():
        ordered = sorted(chapter_questions, key=_order_key)
        n = len(ordered)
        if n <= 1:
            boss_count = 0
        elif n <= 8:
            boss_count = 1
        elif n <= 25:
            boss_count = 2
        else:
            boss_count = 3
        for q in ordered[-boss_count:] if boss_count else []:
            q["encounter_type"] = "chapter_boss"
            q["boss_level"] = "chapter"
            enrich_monster_metadata(q)

    for map_questions in by_map.values():
        ordered = sorted(map_questions, key=lambda q: (_chapter_key(q),) + _order_key(q))
        if not ordered:
            continue
        q = ordered[-1]
        q["encounter_type"] = "book_boss"
        q["boss_level"] = "book"
        enrich_monster_metadata(q)

    return questions


def get_monster_taxonomy():
    return {
        "families": FAMILY_BY_STAGE,
        "encounter_labels": ENCOUNTER_LABELS,
    }
