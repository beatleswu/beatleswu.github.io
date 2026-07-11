import json
import os
import re

DISCIPLINES = [
    {"key": "capture_escape", "label": "吃子與逃子", "label_en": "Capture & Escape", "description": "氣、打吃、提子、逃子與基本攻防。", "order": 10},
    {"key": "connection_cut", "label": "連接與切斷", "label_en": "Connection & Cutting", "description": "斷點、連接、分斷、虎口與接不歸。", "order": 20},
    {"key": "life_death", "label": "死活", "label_en": "Life & Death", "description": "做活、殺棋、眼形、劫活與攻殺。", "order": 30},
    {"key": "tesuji", "label": "手筋", "label_en": "Tesuji", "description": "征子、枷吃、倒撲、滾打包收與妙手。", "order": 40},
    {"key": "opening_direction", "label": "布局方向", "label_en": "Opening Direction", "description": "大場、急所、掛角、夾攻、侵分與全局方向。", "order": 50},
    {"key": "shape_weakness", "label": "棋形與弱點", "label_en": "Shape & Weakness", "description": "好形、壞形、弱點、俗手與棋形修正。", "order": 60},
    {"key": "endgame_counting", "label": "官子與目數", "label_en": "Endgame & Counting", "description": "收官、目數、大小判斷與終局細節。", "order": 70},
    {"key": "whole_board", "label": "實戰綜合", "label_en": "Whole-board Training", "description": "混合型題目、實戰判斷與跨主題訓練。", "order": 80},
]

DISCIPLINE_BY_KEY = {d["key"]: d for d in DISCIPLINES}
LEGACY_DISCIPLINE_MAP = {"endgame": "endgame_counting", "opening": "opening_direction", "mix": "whole_board"}

STAGES = [
    {"key": "LV1", "label": "LV1 啟蒙", "label_en": "LV1 First Steps", "rank_min": "30k", "rank_max": "25k", "description": "認識吃子、氣、連接。"},
    {"key": "LV2", "label": "LV2 基礎", "label_en": "LV2 Basics", "rank_min": "24k", "rank_max": "20k", "description": "簡單吃子、逃子、斷點。"},
    {"key": "LV3", "label": "LV3 入門", "label_en": "LV3 Beginner", "rank_min": "19k", "rank_max": "15k", "description": "基本死活、基礎手筋。"},
    {"key": "LV4", "label": "LV4 初級", "label_en": "LV4 Elementary", "rank_min": "14k", "rank_max": "10k", "description": "常見形與簡單攻防。"},
    {"key": "LV5", "label": "LV5 進階級位", "label_en": "LV5 Kyu Builder", "rank_min": "9k", "rank_max": "5k", "description": "複合手筋與局部判斷。"},
    {"key": "LV6", "label": "LV6 高級級位", "label_en": "LV6 Advanced Kyu", "rank_min": "4k", "rank_max": "1k", "description": "攻殺、劫與厚薄判斷。"},
    {"key": "LV7", "label": "LV7 初段預備", "label_en": "LV7 Dan Prep", "rank_min": "1d", "rank_max": "1d", "description": "綜合題與方向選擇。"},
    {"key": "LV8", "label": "LV8 段位基礎", "label_en": "LV8 Dan Basics", "rank_min": "2d", "rank_max": "3d", "description": "段位基礎題型。"},
    {"key": "LV9", "label": "LV9 段位進階", "label_en": "LV9 Advanced Dan", "rank_min": "4d", "rank_max": "5d", "description": "高階局部與全局判斷。"},
    {"key": "LV10", "label": "LV10 高段挑戰", "label_en": "LV10 High Dan Challenge", "rank_min": "6d", "rank_max": "9d", "description": "高段綜合挑戰。"},
]

DIFFICULTY_ORDER = [
    "30k","29k","28k","27k","26k","25k","24k","23k","22k","21k",
    "20k","19k","18k","17k","16k","15k","14k","13k","12k","11k",
    "10k","9k","8k","7k","6k","5k","4k","3k","2k","1k",
    "1d","2d","3d","4d","5d","6d","7d","8d","9d",
]
_RANK_SET = set(DIFFICULTY_ORDER)

# Internal mapping derived from the owner's original-title spreadsheet.
# Only the renamed/public titles are matched here, so original source names do not surface in the app.
BOOK_RULES = [
    # ── 26-30k ────────────────────────────────────────────────────────────
    # 101入門篇（上）：氣/吃子/連接 → capture_escape 為主
    ("Go - Starter Village", "capture_escape", "30k"), ("圍棋新手村", "capture_escape", "30k"),
    # 級位練習冊1：純吃子練習
    ("Go - Village Trial", "capture_escape", "30k"), ("新手村的考驗", "capture_escape", "30k"),
    # 速成圍棋入門篇：入門規則/吃子
    ("Codex of Sparks", "capture_escape", "30k"), ("星火御石法典", "capture_escape", "30k"),

    # ── 21-25k ────────────────────────────────────────────────────────────
    # 101入門篇（中）：死活/對殺 → life_death 為主
    ("Go - Slime Plains", "life_death", "25k"), ("史萊姆平原", "life_death", "25k"),
    # 級位練習冊2（19-14級，混編：基礎/對殺/手筋/死活；基礎題 fallback=吃子）
    ("Go - Slime Subjugation", "capture_escape", "16k"), ("史萊姆討伐戰", "capture_escape", "16k"),
    # 速成圍棋基礎篇：基礎吃子/連接/死活 → capture_escape 為主
    ("Line Construction", "capture_escape", "25k"), ("陣線構築", "capture_escape", "25k"),

    # ── 16-20k ────────────────────────────────────────────────────────────
    # 101入門篇（下）：連接/布局/官子 → endgame_counting 題數最多
    ("Go - Goblin Cave", "endgame_counting", "20k"), ("哥布林洞穴", "endgame_counting", "20k"),
    # 級位練習冊3（13-10級，混編）
    ("Go - Goblin Patrol", "capture_escape", "12k"), ("哥布林巡邏隊", "capture_escape", "12k"),
    # 速成圍棋初級篇：六大板塊綜合 → capture_escape 題數最多
    ("Basic Element Magic", "capture_escape", "20k"), ("初階元素魔法導論", "capture_escape", "20k"),

    # ── 11-15k ────────────────────────────────────────────────────────────
    # 級位練習冊4（9-7級，混編）— 須排在「迷霧森林」之前（子字串衝突）
    ("Go - Deep Misty Forest", "capture_escape", "8k"), ("迷霧森林深處", "capture_escape", "8k"),
    # 101初級篇（上）：死活/手筋 → life_death 為主
    ("Go - Misty Forest", "life_death", "15k"), ("迷霧森林", "life_death", "15k"),
    # 101初級篇（上）：capture_escape 題數最多
    ("Go - Bronze Bounty I", "capture_escape", "15k"), ("銅牌懸賞令(一)", "capture_escape", "15k"),
    # 101初級篇（中）：life_death 為主
    ("Go - Bronze Bounty II", "life_death", "13k"), ("銅牌懸賞令(二)", "life_death", "13k"),
    # 101初級篇（下）：life_death 為主
    ("Go - Bronze Bounty III", "life_death", "11k"), ("銅牌懸賞令(三)", "life_death", "11k"),
    # 速成圍棋中級篇：六板塊 → life_death 為主
    ("Mist Breakthrough", "life_death", "15k"), ("迷霧突圍", "life_death", "15k"),
    # 萬陣試煉3000：死活/手筋/布局 → life_death 為主
    ("Trial of Myriad Formations", "life_death", "15k"), ("萬陣試煉", "life_death", "15k"),

    # ── 6-10k ─────────────────────────────────────────────────────────────
    # 101中級篇（上）：手筋為主 → tesuji
    ("Go - Orc Tribe", "tesuji", "10k"), ("獸人部落", "tesuji", "10k"),
    # 級位練習冊5（6-4級，混編，死活73%）
    ("Go - Orc Arena", "capture_escape", "5k"), ("獸人角鬥場", "capture_escape", "5k"),
    # 101中級篇（中）：life_death 為主
    ("Go - Silver Bounty I", "life_death", "9k"), ("銀牌懸賞令(一)", "life_death", "9k"),
    # 101中級篇（下）：life_death 為主
    ("Go - Silver Bounty II", "life_death", "7k"), ("銀牌懸賞令(二)", "life_death", "7k"),
    # 布局周周練（卷三 5級到1級 / 卷四 1級到1段 / 卷五 1段到3段）— 卷別優先於通用規則
    ("Macro Territory (Vol. 3)", "opening_direction", "3k"), ("大局觀（卷三）", "opening_direction", "3k"),
    ("Macro Territory (Vol. 4)", "opening_direction", "1k"), ("大局觀（卷四）", "opening_direction", "1k"),
    ("Macro Territory (Vol. 5)", "opening_direction", "2d"), ("大局觀（卷五）", "opening_direction", "2d"),
    ("Pioneer Oracle", "opening_direction", "3k"), ("拓荒神諭", "opening_direction", "3k"),
    # 官子周周練（同三檔）
    ("Endgame Micro Tactics (Vol. 3)", "endgame_counting", "3k"), ("微操術（卷三）", "endgame_counting", "3k"),
    ("Endgame Micro Tactics (Vol. 4)", "endgame_counting", "1k"), ("微操術（卷四）", "endgame_counting", "1k"),
    ("Endgame Micro Tactics (Vol. 5)", "endgame_counting", "2d"), ("微操術（卷五）", "endgame_counting", "2d"),
    ("Border Dispute", "endgame_counting", "3k"), ("寸土爭奪", "endgame_counting", "3k"),
    # 死活1000題（前段）→ life_death
    ("Eyes of the Breakout", "life_death", "8k"), ("破局之眼", "life_death", "8k"),

    # ── 1-5k ──────────────────────────────────────────────────────────────
    # 飛龍討伐：life_death 最多
    ("Go - Wyvern Hunt", "life_death", "5k"), ("飛龍討伐", "life_death", "5k"),
    # 級位練習冊6（3-1級，混編，死活77%）
    ("Go - Dragon Guard", "capture_escape", "2k"), ("龍之谷守衛", "capture_escape", "2k"),
    # 金牌懸賞令：life_death 為主
    ("Go - Gold Bounty I", "life_death", "5k"), ("金牌懸賞令(一)", "life_death", "5k"),
    ("Go - Gold Bounty II", "life_death", "3k"), ("金牌懸賞令(二)", "life_death", "3k"),
    # 晉段試煉之門：死活書（用戶確認）
    ("Go - Gate of Trial", "life_death", "1k"), ("晉級試煉之門", "life_death", "1k"), ("晉段試煉之門", "life_death", "1k"),
    # 聖殿試煉：手筋
    ("Templar Trial", "tesuji", "1k"), ("聖殿試煉", "tesuji", "1k"),
    # 狙擊手秘笈：純 tesuji
    ("Sniper Manual", "tesuji", "1k"), ("狙擊手秘笈", "tesuji", "1k"),
    # 棋經眾妙：死活古典問題集
    ("Ancient Master Scrolls", "life_death", "1k"), ("遠古大師殘卷", "life_death", "1k"),
    # 盜賊潛行/暗影刺殺：布局方向
    ("Rogue Stealth", "opening_direction", "1k"), ("盜賊潛行", "opening_direction", "1k"),
    ("Shadow Assassination", "opening_direction", "1k"), ("暗影刺殺", "opening_direction", "1k"),
    # 圍棋死活1000題：純 life_death
    ("Sage's Manuscript", "life_death", "5k"), ("賢者手稿", "life_death", "5k"),
    # 貼身風暴：連接切斷（圍棋接觸戰）
    ("Melee Storm", "connection_cut", "5k"), ("貼身風暴", "connection_cut", "5k"),
    # 圍棋死活3600題（初級卷）：life_death 為主
    ("Kaleidoscope Board", "life_death", "5k"), ("萬化棋局", "life_death", "5k"),

    # ── 1-2d ──────────────────────────────────────────────────────────────
    # 賢者之塔：life_death 為主
    ("Go - Tower of Sages", "life_death", "1d"), ("賢者之塔", "life_death", "1d"),
    # 大魔法師試煉：shape_weakness 題數最多（棋形書）
    ("Go - Archmage Trial", "shape_weakness", "1d"), ("大魔法師試煉", "shape_weakness", "1d"),
    # 死靈深淵：純 life_death
    ("Necromancer Abyss", "life_death", "1d"), ("死靈深淵", "life_death", "1d"),
    # 煉金術士的微操：純 endgame_counting
    ("Alchemist Precision", "endgame_counting", "1d"), ("煉金術士的微操", "endgame_counting", "1d"),
    # 生存者遊戲：life_death
    ("Survivor Game", "life_death", "1d"), ("生存者遊戲", "life_death", "1d"),
    # 幻影刺客的暗器：純 tesuji
    ("Phantom Kunai", "tesuji", "1d"), ("幻影刺客的暗器", "tesuji", "1d"),
    # 靈魂收割者：life_death
    ("Soul Reaper", "life_death", "1d"), ("靈魂收割者", "life_death", "1d"),
    # 吳清源手筋辭典：純 tesuji
    ("Lost Sword Secret", "tesuji", "1d"), ("劍聖失落奧義", "tesuji", "1d"),
    # 官子譜：endgame_counting
    ("Endgame Gamble", "endgame_counting", "1d"), ("終局的神魔博弈", "endgame_counting", "1d"),
    # 榮耀白金挑戰：life_death 為主
    ("Go - Platinum Challenge", "life_death", "2d"), ("榮耀白金挑戰", "life_death", "2d"),
    # 狂戰士：life_death
    ("Berserker", "life_death", "1d"), ("狂戰士", "life_death", "1d"),
    # 李昌鎬精講圍棋死活：life_death
    ("Li Changho", "life_death", "1d"), ("李昌鎬精講", "life_death", "1d"), ("李昌鎬", "life_death", "1d"),
    # 其他1段地圖
    ("Stellar Core", "life_death", "1d"), ("恆星核心", "life_death", "1d"),
    ("Spatial Fold", "life_death", "1d"), ("空間摺疊", "life_death", "1d"),
    ("Singularity Defense", "life_death", "1d"), ("奇點防禦", "life_death", "1d"),
    ("Quantum Trap", "life_death", "1d"), ("量子陷阱", "life_death", "1d"),
    ("Sector Fission", "life_death", "1d"), ("星域裂變", "life_death", "1d"),
    ("Ultimate Matrix", "life_death", "1d"), ("終極矩陣", "life_death", "1d"),

    # ── 3-4d ──────────────────────────────────────────────────────────────
    # 魔王城前線：endgame_counting 題數最多（含官子書成分）
    ("Demon Castle Front", "endgame_counting", "3d"), ("魔王城前線", "endgame_counting", "3d"),
    # 皇家騎士團：life_death 為主
    ("Royal Crusade", "life_death", "3d"), ("皇家騎士團遠征", "life_death", "3d"),
    # 混沌領主：life_death 為主
    ("Chaos Lord Trial", "life_death", "3d"), ("混沌領主的考驗", "life_death", "3d"),
    # 禁忌弒神：純 tesuji
    ("Forbidden Godslayer", "tesuji", "3d"), ("禁忌的弒神之刃", "tesuji", "3d"),
    # 魔界禁咒大全（瀨越手筋）：tesuji 為主
    ("Demonic Spellbook", "tesuji", "3d"), ("魔界禁咒大全", "tesuji", "3d"),
    # 傳奇鑽石巔峰：tesuji 為主
    ("Go - Diamond Pinnacle", "tesuji", "4d"), ("傳奇鑽石巔峰", "tesuji", "4d"),
    # 逆天改命（圍棋死活3600高級卷）：tesuji 稍多於 life_death
    ("Fate Weaver", "tesuji", "3d"), ("逆天改命", "tesuji", "3d"),
    # 不朽神格：life_death
    ("Immortal Divinity", "life_death", "3d"), ("不朽神格", "life_death", "3d"),
    # 天道殘卷（圍棋技巧大全）：endgame_counting（官子部最大）
    ("Cosmic Fragments", "endgame_counting", "3d"), ("天道殘卷", "endgame_counting", "3d"),

    # ── 5d+ ───────────────────────────────────────────────────────────────
    # 諸神黃昏：tesuji 為主（高段綜合）
    ("Go - Ragnarok", "tesuji", "5d"), ("諸神黃昏", "tesuji", "5d"),
    # 命運萬花筒：tesuji
    ("Destiny Kaleidoscope", "tesuji", "5d"), ("命運的萬花筒", "tesuji", "5d"),
    # 東方神祕結界：純 life_death
    ("Mystic Eastern Barrier", "life_death", "7d"), ("東方神祕結界", "life_death", "7d"),
    # 上古終焉神殿：tesuji
    ("Ancient Omega Temple", "tesuji", "7d"), ("上古終焉神殿", "tesuji", "7d"),
]

KEYWORDS = [
    ("life_death", ["不吃死棋", "死活", "做活", "做眼", "殺棋", "杀棋", "眼形", "破眼", "劫活", "攻殺", "攻杀", "對殺", "对杀", "長氣", "长气", "緊氣", "紧气", "雙活", "双活", "life", "death", "live", "kill"]),
    ("connection_cut", ["連接", "连接", "切斷", "切断", "斷點", "断点", "分斷", "分断", "聯絡", "联络", "補斷", "补断", "connect", "connection", "cut", "cutting"]),
    ("capture_escape", ["吃子", "逃子", "打吃", "提子", "叫吃", "氣", "气", "比氣", "比气", "門吃", "门吃", "atari", "capture", "capturing", "escape", "liberty", "liberties", "running", "net"]),
    ("tesuji", ["手筋", "妙手", "鬼手", "征子", "枷", "撲", "扑", "倒撲", "倒扑", "滾打", "滚打", "雙叫吃", "双叫吃", "接不歸", "接不归", "扳", "跳", "長", "渡過", "渡过", "tesuji", "ladder", "throw-in", "snapback", "double atari"]),
    ("opening_direction", ["布局", "佈局", "定石", "大場", "大场", "急所", "厚薄", "掛角", "挂角", "締角", "缔角", "夾攻", "夹攻", "拆二", "拆三", "拆邊", "拆边", "侵分", "擴大地盤", "扩大地盘", "surround direction", "opening", "direction", "joseki", "territory"]),
    ("shape_weakness", ["棋形", "愚形", "好形", "壞形", "坏形", "弱點", "弱点", "薄弱", "俗手", "shape", "weakness"]),
    ("endgame_counting", ["官子", "收官", "目數", "目数", "數目", "数目", "終局", "终局", "endgame", "counting"]),
]

SUBTOPIC_KEYWORDS = [
    ("做活", ["做活", "活棋", "live"]),
    ("殺棋", ["殺棋", "杀棋", "kill"]),
    ("眼形", ["眼形", "做眼", "破眼"]),
    ("劫活", ["劫"]),
    ("攻殺", ["攻殺", "攻杀", "對殺", "对杀"]),
    ("雙叫吃", ["雙叫吃", "双叫吃", "double atari"]),
    ("征子", ["征子", "ladder"]),
    ("枷吃", ["枷", "net"]),
    ("倒撲", ["倒撲", "倒扑", "throw-in", "snapback"]),
    ("斷點", ["斷點", "断点", "補斷", "补断"]),
    ("虎口", ["虎口"]),
    ("接不歸", ["接不歸", "接不归"]),
    ("聯絡", ["聯絡", "联络", "連接", "连接"]),
    ("分斷", ["分斷", "分断", "切斷", "切断", "cut"]),
    ("大場", ["大場", "大场"]),
    ("急所", ["急所"]),
    ("厚薄", ["厚薄"]),
    ("掛角", ["掛角", "挂角"]),
    ("侵分", ["侵分"]),
    ("官子", ["官子", "收官", "endgame"]),
]

TEXT_RANK_HINTS = [
    ("啟蒙", "30k"), ("启蒙", "30k"), ("新手", "30k"), ("入門", "25k"), ("入门", "25k"),
    ("基礎", "22k"), ("基础", "22k"), ("初級", "18k"), ("初级", "18k"),
    ("中級", "8k"), ("中级", "8k"), ("進階", "5k"), ("进阶", "5k"),
    ("高級", "2d"), ("高级", "2d"), ("銅牌", "15k"), ("铜牌", "15k"),
    ("銀牌", "10k"), ("银牌", "10k"), ("金牌", "5k"), ("白金", "2d"),
    ("鑽石", "4d"), ("钻石", "4d"), ("傳奇", "4d"), ("传奇", "4d"),
]

def normalize_discipline(value):
    value = (value or "").strip()
    value = LEGACY_DISCIPLINE_MAP.get(value, value)
    return value if value in DISCIPLINE_BY_KEY else ""

def _join_question_text(q):
    parts = [q.get("topic"), q.get("topic_en"), q.get("level"), q.get("level_en"), q.get("display_name"), q.get("source"), q.get("comment")]
    return " ".join(str(p) for p in parts if p)

def _book_rule(q):
    text = _join_question_text(q).lower()
    for needle, discipline, rank in BOOK_RULES:
        if needle.lower() in text:
            return discipline, rank
    return None, None

def _keyword_discipline(q):
    text = _join_question_text(q).lower()
    for key, words in KEYWORDS:
        if any(w.lower() in text for w in words):
            return key
    return ""

def infer_discipline(q):
    keyword = _keyword_discipline(q)
    if keyword:
        return keyword
    book_disc, _ = _book_rule(q)
    if book_disc:
        return book_disc
    existing = normalize_discipline(q.get("discipline"))
    return existing or "whole_board"

def infer_tags(q, discipline):
    text = _join_question_text(q).lower()
    tags = []
    for tag, words in SUBTOPIC_KEYWORDS:
        if any(w.lower() in text for w in words):
            tags.append(tag)
    if not tags:
        topic = (q.get("level") or q.get("topic") or "").strip()
        if topic and topic != "Unknown":
            tags.append(topic[:24])
    if discipline and discipline not in tags:
        tags.append(discipline)
    return tags[:6]

def normalize_rank(value):
    if not value:
        return ""
    value = str(value).strip().lower().replace(" ", "")
    m = re.fullmatch(r"(\d{1,2})([kd])", value)
    if not m:
        return ""
    rank = f"{int(m.group(1))}{m.group(2)}"
    return rank if rank in _RANK_SET else ""

def _ranks_from_text(text):
    ranks = []
    for n, suffix in re.findall(r"(?<!\d)([1-9]|[1-3][0-9])\s*([kKdD])\b", text):
        rank = normalize_rank(f"{n}{suffix}")
        if rank:
            ranks.append(rank)
    for n in re.findall(r"(?<!\d)([1-9]|[1-3][0-9])\s*[級级](?!\d)", text):
        rank = normalize_rank(f"{n}k")
        if rank:
            ranks.append(rank)
    return ranks

def infer_rank(q):
    direct = normalize_rank(q.get("difficulty"))
    if direct:
        return direct
    _, book_rank = _book_rule(q)
    if book_rank:
        return book_rank
    text = _join_question_text(q)
    ranks = _ranks_from_text(text)
    if ranks:
        dan = [r for r in ranks if r.endswith("d")]
        if dan:
            return max(dan, key=lambda r: int(r[:-1]))
        kyu = [r for r in ranks if r.endswith("k")]
        if kyu:
            return min(kyu, key=lambda r: int(r[:-1]))
    for needle, rank in TEXT_RANK_HINTS:
        if needle in text:
            return rank
    gd = q.get("grimoire_difficulty")
    try:
        gd_val = float(gd)
        if gd_val <= 1: return "25k"
        if gd_val <= 2: return "18k"
        if gd_val <= 3: return "10k"
        if gd_val <= 4: return "5k"
        return "1d"
    except (TypeError, ValueError):
        return "20k"

def rank_index(rank):
    try:
        return DIFFICULTY_ORDER.index(rank)
    except ValueError:
        return DIFFICULTY_ORDER.index("20k")

def stage_for_rank(rank):
    rank = normalize_rank(rank) or "20k"
    if rank.endswith("k"):
        n = int(rank[:-1])
        if 25 <= n <= 30: return "LV1"
        if 20 <= n <= 24: return "LV2"
        if 15 <= n <= 19: return "LV3"
        if 10 <= n <= 14: return "LV4"
        if 5 <= n <= 9: return "LV5"
        return "LV6"
    n = int(rank[:-1])
    if n <= 1: return "LV7"
    if n <= 3: return "LV8"
    if n <= 5: return "LV9"
    return "LV10"

def difficulty_score(rank):
    idx = rank_index(rank)
    return int(round(1 + idx * 99 / (len(DIFFICULTY_ORDER) - 1)))

def get_stage_meta(stage):
    return next((s for s in STAGES if s["key"] == stage), STAGES[1])

# ── 章節覆寫層（chapter_overrides.json，由 apply_chapter_classification.py 產生）──
# key = "topic|level"，value = {"discipline": ..., "stage": ...}（兩欄皆可省略）
# 覆寫優先於關鍵字/書本規則 → build 重跑不會洗掉人工複核結果。
_OVERRIDES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chapter_overrides.json")
_CHAPTER_OVERRIDES = None

# stage 覆寫時的代表 rank（取該 LV 段位區間中段，維持 difficulty_score 一致性）
_STAGE_RANK = {
    "LV1": "27k", "LV2": "22k", "LV3": "17k", "LV4": "12k", "LV5": "7k",
    "LV6": "2k", "LV7": "1d", "LV8": "3d", "LV9": "5d", "LV10": "7d",
}

def _chapter_overrides():
    global _CHAPTER_OVERRIDES
    if _CHAPTER_OVERRIDES is None:
        try:
            with open(_OVERRIDES_PATH, encoding="utf-8") as f:
                _CHAPTER_OVERRIDES = json.load(f)
        except (OSError, ValueError):
            _CHAPTER_OVERRIDES = {}
    return _CHAPTER_OVERRIDES

def classify_question(q):
    ov = _chapter_overrides().get(f"{q.get('topic')}|{q.get('level')}", {})
    discipline = ov.get("discipline") or infer_discipline(q)
    if ov.get("stage"):
        stage = ov["stage"]
        rank = _STAGE_RANK.get(stage) or infer_rank(q)
    else:
        rank = infer_rank(q)
        stage = stage_for_rank(rank)
    stage_meta = get_stage_meta(stage)
    disc_meta = DISCIPLINE_BY_KEY[discipline]
    tags = q.get("tags")
    inferred_tags = infer_tags(q, discipline)
    if not isinstance(tags, list) or not tags or tags == [q.get("discipline")]:
        tags = inferred_tags
    return {
        "discipline": discipline,
        "discipline_label": disc_meta["label"],
        "discipline_label_en": disc_meta["label_en"],
        "discipline_order": disc_meta["order"],
        "rank": rank,
        "stage": stage,
        "stage_label": stage_meta["label"],
        "stage_label_en": stage_meta["label_en"],
        "difficulty_score": difficulty_score(rank),
        "tags": tags,
    }

def enrich_question(q):
    q.update(classify_question(q))
    return q

def get_taxonomy():
    return {"disciplines": DISCIPLINES, "stages": STAGES, "difficulty_order": DIFFICULTY_ORDER}
