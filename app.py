from flask import (Flask, jsonify, send_from_directory, request,
                   session, redirect, url_for)
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import json, os, subprocess, threading, uuid, time, sqlite3, datetime, secrets, bisect
import random, string
try:
    from flask_compress import Compress as _FlaskCompress
    _has_compress = True
except ImportError:
    _has_compress = False
from katago_explain import KataGoExplainer
from grimoire_api import grimoire_bp
from question_taxonomy import get_taxonomy
from monster_taxonomy import get_monster_taxonomy, mark_encounters
from shadow_dashboard import aggregate_shadow_events

app = Flask(__name__)
if _has_compress:
    _FlaskCompress(app)   # 自動對所有回應做 gzip，HTML/JSON 體積減少 70-80%
_KEY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'secret_key.txt')
if os.environ.get('SECRET_KEY'):
    app.secret_key = os.environ['SECRET_KEY']
elif os.path.exists(_KEY_FILE):
    with open(_KEY_FILE) as f:
        app.secret_key = f.read().strip()
else:
    _k = secrets.token_hex(32)
    with open(_KEY_FILE, 'w') as f:
        f.write(_k)
    app.secret_key = _k
CORS(app, supports_credentials=True)
socketio = SocketIO(app, cors_allowed_origins='*', async_mode='threading',
                    manage_session=False)
app.register_blueprint(grimoire_bp)

@app.after_request
def add_no_cache_headers(response):
    """自訂 JS 短暫快取；HTML 讓瀏覽器必須 revalidate（304 機制）。"""
    ct = response.content_type or ''
    path = request.path or ''
    is_nav_js = path in ('/mobile-nav.js', '/site-nav.js')
    is_own_js = path in ('/srs.js', '/i18n.js', '/mobile-nav.js', '/site-nav.js')
    if is_nav_js:
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    elif is_own_js:
        # JS 可快取 60 秒，避免每次頁面切換重下載
        response.headers['Cache-Control'] = 'public, max-age=60'
    elif 'text/html' in ct:
        # HTML：允許快取但必須 revalidate（304 走快取，變更後才重下載）
        response.headers['Cache-Control'] = 'no-cache'
    return response

DATA_FILE = 'questions.json'
SRS_DB    = 'srs.db'
CACHE_DB  = 'katago_cache.db'

DIFFICULTY_ORDER = [
    '30k','29k','28k','27k','26k','25k','24k','23k','22k','21k',
    '20k','19k','18k','17k','16k','15k','14k','13k','12k','11k',
    '10k','9k','8k','7k','6k','5k','4k','3k','2k','1k',
    '1d','2d','3d','4d','5d','6d','7d','8d','9d'
]

# ── 訂閱設定 ──────────────────────────────────────────────────
# 免費用戶：所有難度的題目均可練習，僅以每日題數上限做區隔
# 免費用戶每日最多可提交的 review 次數
FREE_DAILY_LIMIT = 20

# ── XP / 段位系統 ──────────────────────────────────────────────
XP_BY_DIFF = {
    '30k':1,  '29k':1,  '28k':1,  '27k':1,  '26k':1,
    '25k':1,  '24k':1,  '23k':1,  '22k':1,  '21k':2,
    '20k':2,  '19k':2,  '18k':3,  '17k':4,  '16k':5,  '15k':6,
    '14k':8,  '13k':10, '12k':12, '11k':14, '10k':17, '9k':20,
    '8k':23,  '7k':23,  '6k':26,  '5k':26,  '4k':28,  '3k':28,
    '2k':30,  '1k':30,  '1d':38,  '2d':45,  '3d':52,  '4d':60,
    '5d':70,  '6d':80,  '7d':90,  '8d':95,  '9d':100,
}
XP_FIRST_CORRECT   = 5
XP_MISTAKE_CORRECT = 15

# 連擊門檻由大到小；第一個符合的即生效
COMBO_MULTIPLIERS = [(30, 3.0), (10, 2.0), (3, 1.5)]

# ── 練習 LV 系統（LV1–50）───────────────────────────────────────
# LV_THRESHOLDS[i] = 到達 LV(i+1) 所需的累計總 XP
# 分三段：LV1-10 簡單，LV11-30 中等，LV31-50 困難
LV_THRESHOLDS = [
    0,       120,     280,     480,     720,    # LV1–5
    1000,    1320,    1680,    2080,    2520,   # LV6–10
    3100,    3800,    4600,    5500,    6500,   # LV11–15
    7600,    8800,    10100,   11500,   13000,  # LV16–20
    14600,   16300,   18100,   20000,   22000,  # LV21–25
    24100,   26300,   28600,   31000,   33500,  # LV26–30
    36500,   40000,   44000,   48500,   53500,  # LV31–35
    59000,   65000,   71500,   78500,   86000,  # LV36–40
    94000,   102500,  111500,  121000,  131000, # LV41–45
    141500,  152500,  164000,  176000,  188500, # LV46–50
]
MAX_LV = 50

# LV_HP[i] = LV(i+1) 的最大血量（索引 0 = LV1）
LV_HP = [
     60,  66,  72,  78,  84,  90,  96, 103, 110, 118,   # LV1–10
    126, 135, 144, 154, 164, 175, 186, 198, 210, 224,   # LV11–20
    238, 253, 268, 284, 300, 317, 335, 354, 374, 395,   # LV21–30
    418, 443, 470, 499, 530, 563, 598, 635, 674, 715,   # LV31–40
    758, 803, 850, 900, 952,1006,1062,1120,1180,1242,   # LV41–50
]

# 每個 LV 升級所需 XP（LV1→LV2, LV2→LV3, ...）；LV50 填 0
RANK_XP_THRESHOLDS = {
    f'LV{lv}': (LV_THRESHOLDS[lv] - LV_THRESHOLDS[lv - 1] if lv < MAX_LV else 0)
    for lv in range(1, MAX_LV + 1)
}

def xp_to_lv(total_xp):
    """累計 XP → 練習 LV（1–50）"""
    return min(bisect.bisect_right(LV_THRESHOLDS, total_xp), MAX_LV)

def lv_progress(total_xp):
    """回傳 (lv, xp_in_lv, xp_needed_for_lv)；LV50 時 xp_needed=0"""
    lv = xp_to_lv(total_xp)
    start = LV_THRESHOLDS[lv - 1]
    if lv < MAX_LV:
        return lv, total_xp - start, LV_THRESHOLDS[lv] - start
    return lv, total_xp - start, 0

def _lv_max_hp(lv):
    return LV_HP[min(lv - 1, MAX_LV - 1)]

# 舊段位格式 → 練習 LV 對照（DB 遷移 / 獎章向後相容用）
_OLD_RANK_TO_LV = {
    '30k':1,'29k':2,'28k':3,'27k':4,'26k':5,'25k':6,'24k':7,'23k':8,'22k':9,'21k':10,
    '20k':11,'19k':12,'18k':13,'17k':14,'16k':15,'15k':16,'14k':17,'13k':18,'12k':19,
    '11k':20,'10k':21,'9k':22,'8k':23,'7k':24,'6k':25,'5k':26,'4k':27,'3k':28,
    '2k':29,'1k':30,'1d':33,'2d':36,'3d':39,'4d':42,'5d':44,'6d':46,'7d':47,'8d':48,'9d':50,
}
def _rank_to_lv(rank: str) -> int:
    """將任意格式的段位字串轉換為 LV 數字（1–50）。
    支援新格式 'LV12' 與舊格式 '17k'/'1d' 兩種。"""
    if isinstance(rank, str) and rank.startswith('LV'):
        try:
            return max(1, min(int(rank[2:]), MAX_LV))
        except ValueError:
            return 1
    return _OLD_RANK_TO_LV.get(rank, 1)

# 段位達成勳章的舊 rank.value → 觸發所需最低 LV（向後相容）
_RANK_BADGE_MIN_LV = {
    '19k':12,'18k':13,'17k':14,'15k':16,'13k':18,'10k':21,'8k':23,
    '5k':26,'3k':28,'1k':30,'1d':33,'2d':36,'3d':39,
}
# LV → 觸發段位外觀解鎖的對照
_LV_APPEARANCE_TRIGGER = {33: '1d', 39: '3d', 44: '5d'}

def calc_xp_gain(diff, combo_streak, is_first_correct, is_mistake_correction):
    base  = XP_BY_DIFF.get(diff, 10)
    bonus = (XP_FIRST_CORRECT if is_first_correct else 0) + \
            (XP_MISTAKE_CORRECT if is_mistake_correction else 0)
    mult  = 1.0
    for threshold, m in COMBO_MULTIPLIERS:
        if combo_streak >= threshold:
            mult = m
            break
    return int(round((base + bonus) * mult)), mult

BADGE_DEFS = [
    # ── 連勝（當前連勝）──────────────────────────────────────────
    { 'id':'streak_3',   'name':'初燃',     'icon':'🔥', 'desc':'連續答對 3 題',    'type':'streak','value':3,   'rarity':'bronze'   },
    { 'id':'streak_5',   'name':'五連燃',   'icon':'🔥', 'desc':'連續答對 5 題',    'type':'streak','value':5,   'rarity':'bronze'   },
    { 'id':'streak_7',   'name':'七連利',   'icon':'🔥', 'desc':'連續答對 7 題',    'type':'streak','value':7,   'rarity':'bronze'   },
    { 'id':'streak_10',  'name':'十連霸',   'icon':'⚡', 'desc':'連續答對 10 題',   'type':'streak','value':10,  'rarity':'silver'   },
    { 'id':'streak_15',  'name':'十五連傑', 'icon':'⚡', 'desc':'連續答對 15 題',   'type':'streak','value':15,  'rarity':'silver'   },
    { 'id':'streak_20',  'name':'廿連神',   'icon':'🌩️', 'desc':'連續答對 20 題',   'type':'streak','value':20,  'rarity':'silver'   },
    { 'id':'streak_30',  'name':'三十颱風', 'icon':'🌪️', 'desc':'連續答對 30 題',   'type':'streak','value':30,  'rarity':'gold'     },
    { 'id':'streak_50',  'name':'五十戰神', 'icon':'🌟', 'desc':'連續答對 50 題',   'type':'streak','value':50,  'rarity':'gold'     },
    { 'id':'streak_75',  'name':'七五鋒芒', 'icon':'🌠', 'desc':'連續答對 75 題',   'type':'streak','value':75,  'rarity':'gold'     },
    { 'id':'streak_100', 'name':'百連宗師', 'icon':'💫', 'desc':'連續答對 100 題',  'type':'streak','value':100, 'rarity':'legendary'},

    # ── 歷史最高連勝 ──────────────────────────────────────────────
    { 'id':'best_5',   'name':'破五紀錄',   'icon':'🏅', 'desc':'歷史最高連勝達到 5',   'type':'max_streak','value':5,   'rarity':'bronze'   },
    { 'id':'best_10',  'name':'十連傳說',   'icon':'🏅', 'desc':'歷史最高連勝達到 10',  'type':'max_streak','value':10,  'rarity':'bronze'   },
    { 'id':'best_20',  'name':'廿連史詩',   'icon':'🏆', 'desc':'歷史最高連勝達到 20',  'type':'max_streak','value':20,  'rarity':'silver'   },
    { 'id':'best_30',  'name':'三十豐碑',   'icon':'🏆', 'desc':'歷史最高連勝達到 30',  'type':'max_streak','value':30,  'rarity':'silver'   },
    { 'id':'best_50',  'name':'五十最強',   'icon':'👑', 'desc':'歷史最高連勝達到 50',  'type':'max_streak','value':50,  'rarity':'gold'     },
    { 'id':'best_100', 'name':'百連傳說',   'icon':'💫', 'desc':'歷史最高連勝達到 100', 'type':'max_streak','value':100, 'rarity':'legendary'},

    # ── 累計答對 ──────────────────────────────────────────────────
    { 'id':'total_10',   'name':'初出茅廬', 'icon':'🌱', 'desc':'累計答對 10 題',    'type':'total_correct','value':10,   'rarity':'bronze'   },
    { 'id':'total_25',   'name':'入門小成', 'icon':'🌿', 'desc':'累計答對 25 題',    'type':'total_correct','value':25,   'rarity':'bronze'   },
    { 'id':'total_50',   'name':'小有所成', 'icon':'🍀', 'desc':'累計答對 50 題',    'type':'total_correct','value':50,   'rarity':'bronze'   },
    { 'id':'total_100',  'name':'百題達人', 'icon':'🌳', 'desc':'累計答對 100 題',   'type':'total_correct','value':100,  'rarity':'silver'   },
    { 'id':'total_200',  'name':'兩百老手', 'icon':'🏔️', 'desc':'累計答對 200 題',   'type':'total_correct','value':200,  'rarity':'silver'   },
    { 'id':'total_300',  'name':'三百淬煉', 'icon':'🌊', 'desc':'累計答對 300 題',   'type':'total_correct','value':300,  'rarity':'silver'   },
    { 'id':'total_500',  'name':'棋海漫遊', 'icon':'🐉', 'desc':'累計答對 500 題',   'type':'total_correct','value':500,  'rarity':'gold'     },
    { 'id':'total_750',  'name':'七五之勇', 'icon':'🔱', 'desc':'累計答對 750 題',   'type':'total_correct','value':750,  'rarity':'gold'     },
    { 'id':'total_1000', 'name':'千題宗師', 'icon':'👑', 'desc':'累計答對 1000 題',  'type':'total_correct','value':1000, 'rarity':'gold'     },
    { 'id':'total_1500', 'name':'千五之境', 'icon':'🌌', 'desc':'累計答對 1500 題',  'type':'total_correct','value':1500, 'rarity':'legendary'},
    { 'id':'total_2000', 'name':'兩千磨礪', 'icon':'🔮', 'desc':'累計答對 2000 題',  'type':'total_correct','value':2000, 'rarity':'legendary'},
    { 'id':'total_3000', 'name':'三千棋功', 'icon':'🏛️', 'desc':'累計答對 3000 題',  'type':'total_correct','value':3000, 'rarity':'legendary'},
    { 'id':'total_5000', 'name':'萬象宗師', 'icon':'💎', 'desc':'累計答對 5000 題',  'type':'total_correct','value':5000, 'rarity':'legendary'},

    # ── 連擊大師 ──────────────────────────────────────────────────
    { 'id':'combo_3',  'name':'首次連擊', 'icon':'⚡', 'desc':'達成 3 連擊',  'type':'combo','value':3,  'rarity':'bronze'   },
    { 'id':'combo_5',  'name':'五重連擊', 'icon':'⚡', 'desc':'達成 5 連擊',  'type':'combo','value':5,  'rarity':'bronze'   },
    { 'id':'combo_10', 'name':'十重連爆', 'icon':'🔥', 'desc':'達成 10 連擊', 'type':'combo','value':10, 'rarity':'silver'   },
    { 'id':'combo_15', 'name':'十五爆發', 'icon':'🔥', 'desc':'達成 15 連擊', 'type':'combo','value':15, 'rarity':'silver'   },
    { 'id':'combo_20', 'name':'二十連神', 'icon':'🌪️', 'desc':'達成 20 連擊', 'type':'combo','value':20, 'rarity':'gold'     },
    { 'id':'combo_30', 'name':'連擊宗師', 'icon':'💥', 'desc':'達成 30 連擊', 'type':'combo','value':30, 'rarity':'gold'     },
    { 'id':'combo_50', 'name':'五十連霸', 'icon':'🌟', 'desc':'達成 50 連擊', 'type':'combo','value':50, 'rarity':'legendary'},

    # ── 錯題矯正 ──────────────────────────────────────────────────
    { 'id':'mistake_1',      'name':'第一修正', 'icon':'📝', 'desc':'將 1 道錯題練習至答對',   'type':'mistake_corrected','value':1,  'rarity':'bronze'},
    { 'id':'mistake_5',      'name':'痛定思痛', 'icon':'📖', 'desc':'將 5 道錯題練習至答對',   'type':'mistake_corrected','value':5,  'rarity':'bronze'},
    { 'id':'mistake_master', 'name':'知錯能改', 'icon':'🔄', 'desc':'將 10 道錯題練習至答對',  'type':'mistake_corrected','value':10, 'rarity':'silver'},
    { 'id':'mistake_20',     'name':'百折不撓', 'icon':'🔧', 'desc':'將 20 道錯題練習至答對',  'type':'mistake_corrected','value':20, 'rarity':'silver'},
    { 'id':'mistake_30',     'name':'矯正老手', 'icon':'🎯', 'desc':'將 30 道錯題練習至答對',  'type':'mistake_corrected','value':30, 'rarity':'gold'  },
    { 'id':'mistake_50',     'name':'化錯為金', 'icon':'🎓', 'desc':'將 50 道錯題練習至答對',  'type':'mistake_corrected','value':50, 'rarity':'gold'  },
    { 'id':'mistake_100',    'name':'百錯百正', 'icon':'🏅', 'desc':'將 100 道錯題練習至答對', 'type':'mistake_corrected','value':100,'rarity':'legendary'},

    # ── 每日挑戰 ──────────────────────────────────────────────────
    { 'id':'daily_first', 'name':'初戰報到', 'icon':'📅', 'desc':'首次參加每日挑戰',           'type':'daily_challenge','value':0,   'rarity':'bronze'   },
    { 'id':'daily_ace',   'name':'一擊即中', 'icon':'🎯', 'desc':'每日挑戰答對送出',           'type':'daily_challenge','value':0,   'rarity':'bronze'   },
    { 'id':'daily_3',     'name':'三日不輟', 'icon':'🌤️', 'desc':'連續 3 天完成每日挑戰',      'type':'daily_challenge','value':3,   'rarity':'bronze'   },
    { 'id':'daily_7',     'name':'七日不怠', 'icon':'🗓️', 'desc':'連續 7 天完成每日挑戰',      'type':'daily_challenge','value':7,   'rarity':'silver'   },
    { 'id':'daily_14',    'name':'兩週精進', 'icon':'🌙', 'desc':'連續 14 天完成每日挑戰',     'type':'daily_challenge','value':14,  'rarity':'silver'   },
    { 'id':'daily_30',    'name':'月不間斷', 'icon':'🏆', 'desc':'連續 30 天完成每日挑戰',     'type':'daily_challenge','value':30,  'rarity':'gold'     },
    { 'id':'daily_60',    'name':'六旬鑄志', 'icon':'⚜️', 'desc':'連續 60 天完成每日挑戰',     'type':'daily_challenge','value':60,  'rarity':'gold'     },
    { 'id':'daily_100',   'name':'百日磨劍', 'icon':'✨', 'desc':'連續 100 天完成每日挑戰',    'type':'daily_challenge','value':100, 'rarity':'gold'     },
    { 'id':'daily_200',   'name':'二百持恆', 'icon':'🌠', 'desc':'連續 200 天完成每日挑戰',    'type':'daily_challenge','value':200, 'rarity':'legendary'},
    { 'id':'daily_365',   'name':'一年修行', 'icon':'🌟', 'desc':'連續 365 天完成每日挑戰',    'type':'daily_challenge','value':365, 'rarity':'legendary'},

    # ── 段位達成 ──────────────────────────────────────────────────
    { 'id':'rank_19k', 'name':'踏上旅途', 'icon':'🌿', 'desc':'段位達到 19k', 'type':'rank','value':'19k', 'rarity':'bronze'   },
    { 'id':'rank_18k', 'name':'入門起步', 'icon':'🎋', 'desc':'段位達到 18k', 'type':'rank','value':'18k', 'rarity':'bronze'   },
    { 'id':'rank_17k', 'name':'初學有成', 'icon':'🌱', 'desc':'段位達到 17k', 'type':'rank','value':'17k', 'rarity':'bronze'   },
    { 'id':'rank_15k', 'name':'基礎初成', 'icon':'⚙️', 'desc':'段位達到 15k', 'type':'rank','value':'15k', 'rarity':'bronze'   },
    { 'id':'rank_13k', 'name':'漸入佳境', 'icon':'🗝️', 'desc':'段位達到 13k', 'type':'rank','value':'13k', 'rarity':'silver'   },
    { 'id':'rank_10k', 'name':'中級之門', 'icon':'🛡️', 'desc':'段位達到 10k', 'type':'rank','value':'10k', 'rarity':'silver'   },
    { 'id':'rank_8k',  'name':'穩固實力', 'icon':'⚔️', 'desc':'段位達到 8k',  'type':'rank','value':'8k',  'rarity':'silver'   },
    { 'id':'rank_5k',  'name':'高手顯現', 'icon':'💫', 'desc':'段位達到 5k',  'type':'rank','value':'5k',  'rarity':'gold'     },
    { 'id':'rank_3k',  'name':'棋力精進', 'icon':'🏅', 'desc':'段位達到 3k',  'type':'rank','value':'3k',  'rarity':'gold'     },
    { 'id':'rank_1k',  'name':'巔峰前夕', 'icon':'🌄', 'desc':'段位達到 1k',  'type':'rank','value':'1k',  'rarity':'gold'     },
    { 'id':'rank_1d',  'name':'初段登場', 'icon':'🌟', 'desc':'段位達到 1d',  'type':'rank','value':'1d',  'rarity':'legendary'},
    { 'id':'rank_2d',  'name':'二段榮耀', 'icon':'✨', 'desc':'段位達到 2d',  'type':'rank','value':'2d',  'rarity':'legendary'},
    { 'id':'rank_3d',  'name':'三段境界', 'icon':'💎', 'desc':'段位達到 3d',  'type':'rank','value':'3d',  'rarity':'legendary'},

    # ── XP 里程碑 ─────────────────────────────────────────────────
    { 'id':'xp_100',   'name':'初嘗甜果', 'icon':'💡', 'desc':'累計獲得 100 XP',    'type':'xp','value':100,   'rarity':'bronze'   },
    { 'id':'xp_250',   'name':'能量注入', 'icon':'🔆', 'desc':'累計獲得 250 XP',    'type':'xp','value':250,   'rarity':'bronze'   },
    { 'id':'xp_500',   'name':'能量積累', 'icon':'💫', 'desc':'累計獲得 500 XP',    'type':'xp','value':500,   'rarity':'bronze'   },
    { 'id':'xp_1000',  'name':'經驗充沛', 'icon':'⚡', 'desc':'累計獲得 1000 XP',   'type':'xp','value':1000,  'rarity':'silver'   },
    { 'id':'xp_2500',  'name':'老手氣場', 'icon':'🌟', 'desc':'累計獲得 2500 XP',   'type':'xp','value':2500,  'rarity':'silver'   },
    { 'id':'xp_5000',  'name':'老手光環', 'icon':'💎', 'desc':'累計獲得 5000 XP',   'type':'xp','value':5000,  'rarity':'gold'     },
    { 'id':'xp_10000', 'name':'傳說光芒', 'icon':'🌠', 'desc':'累計獲得 10000 XP',  'type':'xp','value':10000, 'rarity':'gold'     },
    { 'id':'xp_25000', 'name':'超凡入聖', 'icon':'🔮', 'desc':'累計獲得 25000 XP',  'type':'xp','value':25000, 'rarity':'legendary'},

    # ── 好友挑戰 ─────────────────────────────────────────────────
    { 'id':'challenge_win_1',    'name':'初勝',    'icon':'⚔️',  'desc':'首次好友挑戰勝利',      'type':'challenge_win',        'value':1,  'rarity':'bronze' },
    { 'id':'challenge_win_3',    'name':'三勝棋士','icon':'🗡️', 'desc':'好友挑戰勝利 3 次',     'type':'challenge_win',        'value':3,  'rarity':'silver' },
    { 'id':'challenge_win_10',   'name':'常勝將軍','icon':'🏆', 'desc':'好友挑戰勝利 10 次',    'type':'challenge_win',        'value':10, 'rarity':'gold'   },
    { 'id':'challenge_win_30',   'name':'百戰百勝','icon':'👑', 'desc':'好友挑戰勝利 30 次',    'type':'challenge_win',        'value':30, 'rarity':'legendary'},
    { 'id':'challenge_streak_3', 'name':'三連勝',  'icon':'🔥', 'desc':'好友挑戰連勝 3 場',     'type':'challenge_win_streak', 'value':3,  'rarity':'silver' },
    { 'id':'challenge_streak_5', 'name':'五連霸',  'icon':'🌟', 'desc':'好友挑戰連勝 5 場',     'type':'challenge_win_streak', 'value':5,  'rarity':'gold'   },

    # ── Premium 專屬（訂閱即得）──────────────────────────────────
    { 'id':'premium_member',  'name':'尊爵棋士',   'icon':'💎', 'desc':'成為 Premium 會員，解鎖尊爵之位',       'type':'premium', 'value':0, 'rarity':'legendary', 'premium_only':True },
    { 'id':'premium_founder', 'name':'創始支持者', 'icon':'👑', 'desc':'早期加入 Premium，永久鑲嵌創始者徽記', 'type':'premium', 'value':0, 'rarity':'legendary', 'premium_only':True },
]

# ══════════════════════════════════════════════════════════════
# 技能定義（SKILL_DEFS）
# ══════════════════════════════════════════════════════════════
SKILL_DEFS = [
    # ── 初階（免費路線可學）────────────────────────────────────
    {
        'id': 'focus',
        'name': '專注', 'name_en': 'Focus',
        'icon': '🧘',
        'type': 'passive',
        'desc': '答對時 XP +15%',
        'effect_key': 'xp_bonus',
        'effect_value': 0.15,
        'unlock_rank': '17k',
        'tier': 1,
        'color': 'teal',
    },
    {
        'id': 'endurance',
        'name': '耐力', 'name_en': 'Endurance',
        'icon': '🛡️',
        'type': 'passive',
        'desc': '答錯時怪物反擊傷害 -30%',
        'effect_key': 'player_dmg_reduce',
        'effect_value': 0.30,
        'unlock_rank': '16k',
        'tier': 1,
        'color': 'amber',
    },
    {
        'id': 'combo_start',
        'name': '連擊入門', 'name_en': 'Combo I',
        'icon': '⚡',
        'type': 'passive',
        'desc': '連擊達 3 時傷害額外 +10%',
        'effect_key': 'combo_dmg_bonus',
        'effect_value': 0.10,
        'unlock_rank': '15k',
        'tier': 1,
        'color': 'amber',
    },
    # ── 中階（付費路線）────────────────────────────────────────
    {
        'id': 'eagle_eye',
        'name': '鷹眼', 'name_en': 'Eagle Eye',
        'icon': '🦅',
        'type': 'passive',
        'desc': '做錯的題再答對時 XP +50%（知錯能改）',
        'effect_key': 'mistake_xp_bonus',
        'effect_value': 0.50,
        'unlock_rank': '12k',
        'tier': 2,
        'color': 'purple',
    },
    {
        'id': 'berserker',
        'name': '狂戰士', 'name_en': 'Berserker',
        'icon': '⚔️',
        'type': 'passive',
        'desc': '連擊 ≥10 時傷害 ×2.5（原本 ×2.0）',
        'effect_key': 'berserker_combo',
        'effect_value': 2.5,
        'unlock_rank': '10k',
        'tier': 2,
        'color': 'red',
    },
    {
        'id': 'second_chance',
        'name': '緩手', 'name_en': 'Second Chance',
        'icon': '🔄',
        'type': 'active',
        'desc': '消耗 20 SP：下一題答錯不算失敗（每日最多 3 次）',
        'effect_key': 'shield_next',
        'effect_value': 1,
        'cost_sp': 20,
        'daily_limit': 3,
        'unlock_rank': '9k',
        'tier': 2,
        'color': 'teal',
    },
    {
        'id': 'treasure_hunter',
        'name': '尋寶師', 'name_en': 'Treasure Hunter',
        'icon': '💰',
        'type': 'passive',
        'desc': '怪物掉寶機率 +25%',
        'effect_key': 'loot_bonus',
        'effect_value': 0.25,
        'unlock_rank': '8k',
        'tier': 2,
        'color': 'amber',
    },
    # ── 高階（段位）──────────────────────────────────────────────
    {
        'id': 'dragon_slayer',
        'name': '龍殺者', 'name_en': 'Dragon Slayer',
        'icon': '⚔️',
        'type': 'passive',
        'desc': '對龍族怪物傷害 +40%',
        'effect_key': 'dragon_dmg_bonus',
        'effect_value': 0.40,
        'unlock_rank': '1d',
        'tier': 3,
        'color': 'red',
    },
    {
        'id': 'time_stop',
        'name': '時間停止', 'name_en': 'Time Stop',
        'icon': '⏳',
        'type': 'active',
        'desc': '消耗 50 SP：下一題答對傷害 ×5',
        'effect_key': 'dmg_multiplier',
        'effect_value': 5,
        'cost_sp': 50,
        'daily_limit': 1,
        'unlock_rank': '2d',
        'tier': 3,
        'color': 'purple',
    },
    {
        'id': 'enlightenment',
        'name': '開悟', 'name_en': 'Enlightenment',
        'icon': '☯️',
        'type': 'passive',
        'desc': '每擊敗 1 隻怪物回復 5 SP',
        'effect_key': 'kill_sp_regen',
        'effect_value': 5,
        'unlock_rank': '3d',
        'tier': 3,
        'color': 'teal',
    },
    {
        'id': 'perfect_read',
        'name': '完美讀棋', 'name_en': 'Perfect Read',
        'icon': '🔮',
        'type': 'passive',
        'desc': '連擊 ≥30 時 XP ×4（原本 ×3）',
        'effect_key': 'max_combo_xp',
        'effect_value': 4.0,
        'unlock_rank': '4d',
        'tier': 3,
        'color': 'purple',
    },
]

# ══════════════════════════════════════════════════════════════
# 裝備定義（EQUIPMENT_DEFS）
# ══════════════════════════════════════════════════════════════
EQUIPMENT_DEFS = [
    # ── 武器 ─────────────────────────────────────────────────
    {
        'id': 'wooden_sword',
        'name': '木劍', 'slot': 'weapon', 'rarity': 'common',
        'icon': '🌲',
        'desc': '基礎武器。攻擊 +5%',
        'effects': {'dmg_bonus': 0.05},
        'drop_from': ['goblin'],
        'drop_weight': 30,
    },
    {
        'id': 'iron_sword',
        'name': '鐵劍', 'slot': 'weapon', 'rarity': 'common',
        'icon': '🗡️',
        'desc': '攻擊 +12%',
        'effects': {'dmg_bonus': 0.12},
        'drop_from': ['goblin', 'fox'],
        'drop_weight': 20,
    },
    {
        'id': 'fox_fang',
        'name': '妖狐之牙', 'slot': 'weapon', 'rarity': 'rare',
        'icon': '🦷',
        'desc': '攻擊 +20%，對狐族額外 +15%',
        'effects': {'dmg_bonus': 0.20, 'fox_dmg_bonus': 0.15},
        'drop_from': ['fox'],
        'drop_weight': 15,
    },
    {
        'id': 'dragon_claw',
        'name': '龍爪', 'slot': 'weapon', 'rarity': 'epic',
        'icon': '🐾',
        'desc': '攻擊 +35%，對龍族額外 +20%',
        'effects': {'dmg_bonus': 0.35, 'dragon_dmg_bonus': 0.20},
        'drop_from': ['dragon'],
        'drop_weight': 10,
    },
    {
        'id': 'celestial_blade',
        'name': '天龍神劍', 'slot': 'weapon', 'rarity': 'legendary',
        'icon': '⚡',
        'desc': '攻擊 +60%，連擊加成翻倍',
        'effects': {'dmg_bonus': 0.60, 'combo_multiplier_double': True},
        'drop_from': ['dragon'],
        'drop_weight': 3,
    },
    # ── 防具 ─────────────────────────────────────────────────
    {
        'id': 'cloth_robe',
        'name': '布袍', 'slot': 'armor', 'rarity': 'common',
        'icon': '👘',
        'desc': '受到傷害 -8%',
        'effects': {'player_dmg_reduce': 0.08},
        'drop_from': ['goblin'],
        'drop_weight': 25,
    },
    {
        'id': 'leather_armor',
        'name': '皮甲', 'slot': 'armor', 'rarity': 'common',
        'icon': '🥋',
        'desc': '受到傷害 -15%',
        'effects': {'player_dmg_reduce': 0.15},
        'drop_from': ['goblin', 'fox'],
        'drop_weight': 18,
    },
    {
        'id': 'fox_pelt',
        'name': '妖狐皮衣', 'slot': 'armor', 'rarity': 'rare',
        'icon': '🧥',
        'desc': '受到傷害 -25%，XP +10%',
        'effects': {'player_dmg_reduce': 0.25, 'xp_bonus': 0.10},
        'drop_from': ['fox'],
        'drop_weight': 12,
    },
    {
        'id': 'dragon_scale',
        'name': '龍鱗甲', 'slot': 'armor', 'rarity': 'epic',
        'icon': '🐲',
        'desc': '受到傷害 -40%，每日 SP +30',
        'effects': {'player_dmg_reduce': 0.40, 'sp_bonus': 30},
        'drop_from': ['dragon'],
        'drop_weight': 8,
    },
    {
        'id': 'void_mantle',
        'name': '虛空斗篷', 'slot': 'armor', 'rarity': 'legendary',
        'icon': '🌑',
        'desc': '受到傷害 -60%，答錯不觸發反擊',
        'effects': {'player_dmg_reduce': 0.60, 'negate_counter': True},
        'drop_from': ['dragon'],
        'drop_weight': 2,
    },
    # ── 飾品 ─────────────────────────────────────────────────
    {
        'id': 'lucky_stone',
        'name': '幸運石', 'slot': 'accessory', 'rarity': 'common',
        'icon': '💎',
        'desc': '掉寶機率 +10%',
        'effects': {'loot_bonus': 0.10},
        'drop_from': ['goblin'],
        'drop_weight': 20,
    },
    {
        'id': 'xp_amulet',
        'name': 'XP 護符', 'slot': 'accessory', 'rarity': 'rare',
        'icon': '📿',
        'desc': 'XP 獲取 +20%',
        'effects': {'xp_bonus': 0.20},
        'drop_from': ['fox', 'goblin'],
        'drop_weight': 12,
    },
    {
        'id': 'fox_mask',
        'name': '狐面', 'slot': 'accessory', 'rarity': 'rare',
        'icon': '🎭',
        'desc': '每日任務 XP 獎勵 +25%',
        'effects': {'quest_xp_bonus': 0.25},
        'drop_from': ['fox'],
        'drop_weight': 10,
    },
    {
        'id': 'dragon_eye',
        'name': '龍之眼', 'slot': 'accessory', 'rarity': 'epic',
        'icon': '👁️',
        'desc': '暴擊（grade 5）傷害 ×3',
        'effects': {'crit_multiplier': 3},
        'drop_from': ['dragon'],
        'drop_weight': 6,
    },
    {
        'id': 'go_stone_black',
        'name': '先手黑石', 'slot': 'accessory', 'rarity': 'legendary',
        'icon': '⚫',
        'desc': '第一題必定 grade 5（每日 1 次）',
        'effects': {'first_question_ace': True},
        'drop_from': ['dragon'],
        'drop_weight': 1,
    },
]

# 建立快查字典
_SKILL_MAP = {s['id']: s for s in SKILL_DEFS}
_EQUIP_MAP = {e['id']: e for e in EQUIPMENT_DEFS}

# ── 掉落機率基礎值（依怪物種類）─────────────────────────────
BASE_LOOT_CHANCE = {
    'caterpillar': 0.08,
    'bee':         0.10,
    'turtle':      0.12,
    'rabbit':      0.14,
    'raccoon':     0.16,
    'goblin':      0.20,
    'fox':         0.30,
    'dragon':      0.45,
}

def _roll_loot(monster_type, loot_bonus=0.0):
    """回傳裝備掉落物 id 或 None。"""
    import random
    chance = BASE_LOOT_CHANCE.get(monster_type, 0.20) + loot_bonus
    if random.random() > chance:
        return None
    pool = [e for e in EQUIPMENT_DEFS if monster_type in e['drop_from']]
    if not pool:
        return None
    weights = [e['drop_weight'] for e in pool]
    return random.choices(pool, weights=weights, k=1)[0]['id']

# ── SP（技能點）日常上限 ──────────────────────────────────────
SP_PER_CORRECT = 2      # 答對 +2 SP
SP_MAX_DAILY   = 100    # 每日上限（裝備可提升）

# ══════════════════════════════════════════════════════════════
# 外觀物品定義（APPEARANCE_DEFS）
# slot: 'outfit' | 'hat' | 'back' | 'title'
# rarity: 'common' | 'uncommon' | 'rare' | 'epic' | 'legendary'
# drop_from: 怪物種類列表（空列表 = 只能由 quest/rank 獲得）
# drop_weight: 同 rarity 內的相對權重
# source_hint: 'drop' | 'rank' | 'daily' | 'drop+daily'（前端提示用）
# ══════════════════════════════════════════════════════════════
APPEARANCE_DEFS = [
    # ══════════════════════════════════════════════════════════════
    # 袍服（outfit） ─ 10 件
    # ══════════════════════════════════════════════════════════════
    {
        'id': 'robe_plain',
        'name': '素布道袍', 'slot': 'outfit', 'rarity': 'common',
        'emoji': '🥋', 'color': '#6b5740',
        'flavor': '棋盤前的平靜，來自樸素。',
        'hint': '打敗任意怪物即可獲得',
        'drop_from': ['caterpillar', 'bee', 'turtle', 'rabbit', 'raccoon', 'goblin'], 'drop_weight': 40,
        'source_hint': 'drop',
    },
    {
        'id': 'robe_student',
        'name': '學子短衫', 'slot': 'outfit', 'rarity': 'common',
        'emoji': '👕', 'color': '#6b5740',
        'flavor': '求學之路，始於布衣。',
        'hint': '答題達 50 題後獲得',
        'drop_from': ['caterpillar', 'bee', 'rabbit'], 'drop_weight': 38,
        'source_hint': 'drop',
    },
    {
        'id': 'robe_bamboo',
        'name': '竹林道袍', 'slot': 'outfit', 'rarity': 'uncommon',
        'emoji': '🎋', 'color': '#0d9488',
        'flavor': '竹影掃棋，不動一子。',
        'hint': '連續登入 7 天解鎖',
        'drop_from': ['raccoon', 'wolf'], 'drop_weight': 30,
        'source_hint': 'drop',
    },
    {
        'id': 'robe_crane',
        'name': '仙鶴袍', 'slot': 'outfit', 'rarity': 'uncommon',
        'emoji': '👘', 'color': '#0d9488',
        'flavor': '鶴立棋盤，自有風骨。',
        'hint': '從狐狸或狼掉落',
        'drop_from': ['wolf', 'fox'], 'drop_weight': 28,
        'source_hint': 'drop',
    },
    {
        'id': 'robe_fox',
        'name': '妖狐錦袍', 'slot': 'outfit', 'rarity': 'rare',
        'emoji': '🧣', 'color': '#1d4ed8',
        'flavor': '九尾編織，迷人心智。',
        'hint': '從狐狸掉落（稀有）',
        'drop_from': ['fox'], 'drop_weight': 18,
        'source_hint': 'drop',
    },
    {
        'id': 'robe_snow',
        'name': '雪地羽絨袍', 'slot': 'outfit', 'rarity': 'rare',
        'emoji': '🧥', 'color': '#1d4ed8',
        'flavor': '雪中手談，意境絕倫。',
        'hint': '每日連續簽到 14 天解鎖',
        'drop_from': [], 'drop_weight': 0,
        'source_hint': 'daily', 'daily_streak': 14,
    },
    {
        'id': 'robe_dragon',
        'name': '龍紋袍', 'slot': 'outfit', 'rarity': 'epic',
        'emoji': '🥻', 'color': '#7c3aed',
        'flavor': '龍紋在袍，步步皆局。',
        'hint': '從巨石人或巨龍掉落',
        'drop_from': ['golem', 'dragon'], 'drop_weight': 10,
        'source_hint': 'drop',
    },
    {
        'id': 'robe_celestial',
        'name': '天命玄袍', 'slot': 'outfit', 'rarity': 'legendary',
        'emoji': '🎎', 'color': '#d97706',
        'flavor': '天命所歸，棋道無敵。',
        'hint': '從巨龍掉落（傳說）',
        'drop_from': ['dragon'], 'drop_weight': 4,
        'source_hint': 'drop',
    },
    {
        'id': 'robe_rank_1d',
        'name': '初段御衣', 'slot': 'outfit', 'rarity': 'rare',
        'emoji': '👔', 'color': '#1d4ed8',
        'flavor': '踏入段位之門，衣冠自異。',
        'hint': '段位達到 1d 解鎖',
        'drop_from': [], 'drop_weight': 0,
        'source_hint': 'rank', 'unlock_rank': '1d',
    },
    {
        'id': 'robe_rank_3d',
        'name': '三段戰袍', 'slot': 'outfit', 'rarity': 'epic',
        'emoji': '🎖️', 'color': '#7c3aed',
        'flavor': '三段之力，袍隨心動。',
        'hint': '段位達到 3d 解鎖',
        'drop_from': [], 'drop_weight': 0,
        'source_hint': 'rank', 'unlock_rank': '3d',
    },
    {
        'id': 'robe_rank_5d',
        'name': '五段仙袍', 'slot': 'outfit', 'rarity': 'legendary',
        'emoji': '🏯', 'color': '#d97706',
        'flavor': '五段棋魂，世所罕見。',
        'hint': '段位達到 5d 解鎖',
        'drop_from': [], 'drop_weight': 0,
        'source_hint': 'rank', 'unlock_rank': '5d',
    },

    # ══════════════════════════════════════════════════════════════
    # 頭飾（hat） ─ 9 件
    # ══════════════════════════════════════════════════════════════
    {
        'id': 'hat_cloth',
        'name': '布巾', 'slot': 'hat', 'rarity': 'common',
        'emoji': '🧢', 'color': '#6b5740',
        'flavor': '日日練棋，布巾拭汗。',
        'hint': '打敗任意怪物即可獲得',
        'drop_from': ['caterpillar', 'bee', 'turtle', 'rabbit', 'raccoon', 'goblin'], 'drop_weight': 40,
        'source_hint': 'drop',
    },
    {
        'id': 'hat_bamboo',
        'name': '竹笠', 'slot': 'hat', 'rarity': 'common',
        'emoji': '👒', 'color': '#6b5740',
        'flavor': '簷下落子，雨聲相伴。',
        'hint': '從哥布林或狼掉落',
        'drop_from': ['goblin', 'wolf'], 'drop_weight': 35,
        'source_hint': 'drop',
    },
    {
        'id': 'hat_student',
        'name': '學子書帶', 'slot': 'hat', 'rarity': 'common',
        'emoji': '🎓', 'color': '#6b5740',
        'flavor': '書香棋道，並行不悖。',
        'hint': '答題達 100 題後獲得',
        'drop_from': ['caterpillar', 'bee'], 'drop_weight': 36,
        'source_hint': 'drop',
    },
    {
        'id': 'hat_feather',
        'name': '白鷺羽冠', 'slot': 'hat', 'rarity': 'uncommon',
        'emoji': '🌾', 'color': '#0d9488',
        'flavor': '羽冠一戴，心如止水。',
        'hint': '從狐狸或狼掉落',
        'drop_from': ['wolf', 'fox'], 'drop_weight': 28,
        'source_hint': 'drop',
    },
    {
        'id': 'hat_scholar',
        'name': '儒士方巾', 'slot': 'hat', 'rarity': 'uncommon',
        'emoji': '📿', 'color': '#0d9488',
        'flavor': '方巾正冠，棋道肅整。',
        'hint': '每日挑戰完成 20 次解鎖',
        'drop_from': [], 'drop_weight': 0,
        'source_hint': 'daily', 'daily_streak': 5,
    },
    {
        'id': 'hat_foxmask',
        'name': '狐面', 'slot': 'hat', 'rarity': 'rare',
        'emoji': '🎭', 'color': '#1d4ed8',
        'flavor': '面具之下，誰知真意？',
        'hint': '從狐狸掉落（稀有）',
        'drop_from': ['fox'], 'drop_weight': 18,
        'source_hint': 'drop',
    },
    {
        'id': 'hat_onihorns',
        'name': '鬼角盔', 'slot': 'hat', 'rarity': 'rare',
        'emoji': '👹', 'color': '#1d4ed8',
        'flavor': '鬼眼識棋，妙手天成。',
        'hint': '連勝 10 場解鎖',
        'drop_from': ['golem'], 'drop_weight': 14,
        'source_hint': 'drop',
    },
    {
        'id': 'hat_dragon_horn',
        'name': '龍角冠', 'slot': 'hat', 'rarity': 'epic',
        'emoji': '👑', 'color': '#7c3aed',
        'flavor': '龍角加冕，棋盤稱王。',
        'hint': '從巨龍掉落（稀有）',
        'drop_from': ['dragon'], 'drop_weight': 10,
        'source_hint': 'drop',
    },
    {
        'id': 'hat_celestial_crown',
        'name': '天龍金冠', 'slot': 'hat', 'rarity': 'legendary',
        'emoji': '✨', 'color': '#d97706',
        'flavor': '金冠之重，唯強者能戴。',
        'hint': '從巨龍掉落（傳說）',
        'drop_from': ['dragon'], 'drop_weight': 4,
        'source_hint': 'drop',
    },

    # ══════════════════════════════════════════════════════════════
    # 背飾（back） ─ 8 件
    # ══════════════════════════════════════════════════════════════
    {
        'id': 'back_pack',
        'name': '棋具布包', 'slot': 'back', 'rarity': 'common',
        'emoji': '🎒', 'color': '#6b5740',
        'flavor': '棋盤、棋石，皆在此中。',
        'hint': '打敗任意怪物即可獲得',
        'drop_from': ['caterpillar', 'bee', 'turtle', 'rabbit', 'raccoon', 'goblin'], 'drop_weight': 40,
        'source_hint': 'drop',
    },
    {
        'id': 'back_flag',
        'name': '出陣小旗', 'slot': 'back', 'rarity': 'common',
        'emoji': '🚩', 'color': '#6b5740',
        'flavor': '出征前，旗隨風揚。',
        'hint': '從哥布林或狼掉落',
        'drop_from': ['goblin', 'wolf'], 'drop_weight': 35,
        'source_hint': 'drop',
    },
    {
        'id': 'back_lantern',
        'name': '紅燈籠', 'slot': 'back', 'rarity': 'uncommon',
        'emoji': '🏮', 'color': '#0d9488',
        'flavor': '燈火搖曳，局中光明。',
        'hint': '連續登入 7 天解鎖',
        'drop_from': [], 'drop_weight': 0,
        'source_hint': 'daily', 'daily_streak': 7,
    },
    {
        'id': 'back_wings',
        'name': '白羽翼', 'slot': 'back', 'rarity': 'uncommon',
        'emoji': '🕊️', 'color': '#0d9488',
        'flavor': '羽翼輕盈，棋思飛揚。',
        'hint': '從狐狸或狼掉落',
        'drop_from': ['wolf', 'fox'], 'drop_weight': 28,
        'source_hint': 'drop',
    },
    {
        'id': 'back_scroll',
        'name': '古典棋譜', 'slot': 'back', 'rarity': 'rare',
        'emoji': '📜', 'color': '#1d4ed8',
        'flavor': '千年棋局，盡收一卷。',
        'hint': '錯題本複習達 100 題解鎖',
        'drop_from': [], 'drop_weight': 0,
        'source_hint': 'daily', 'daily_streak': 10,
    },
    {
        'id': 'back_foxtail',
        'name': '九尾狐尾', 'slot': 'back', 'rarity': 'rare',
        'emoji': '🦊', 'color': '#1d4ed8',
        'flavor': '九尾搖曳，幻局已成。',
        'hint': '從狐狸掉落（稀有）',
        'drop_from': ['fox'], 'drop_weight': 18,
        'source_hint': 'drop',
    },
    {
        'id': 'back_cloak',
        'name': '星紋斗篷', 'slot': 'back', 'rarity': 'epic',
        'emoji': '🌌', 'color': '#7c3aed',
        'flavor': '星紋斗篷，棋局如宇宙。',
        'hint': '從巨石人或巨龍掉落',
        'drop_from': ['golem', 'dragon'], 'drop_weight': 10,
        'source_hint': 'drop',
    },
    {
        'id': 'back_dragon_wings',
        'name': '龍翼', 'slot': 'back', 'rarity': 'legendary',
        'emoji': '🐉', 'color': '#d97706',
        'flavor': '龍翼展開，棋道震天。',
        'hint': '從巨龍掉落（傳說）',
        'drop_from': ['dragon'], 'drop_weight': 4,
        'source_hint': 'drop',
    },

    # ══════════════════════════════════════════════════════════════
    # 配飾（accessory） ─ 7 件（新）
    # ══════════════════════════════════════════════════════════════
    {
        'id': 'acc_bracelet',
        'name': '棋緣手串', 'slot': 'accessory', 'rarity': 'common',
        'emoji': '📿', 'color': '#6b5740',
        'flavor': '每一珠皆是一段棋緣。',
        'hint': '打敗烏龜或兔子後獲得',
        'drop_from': ['turtle', 'rabbit'], 'drop_weight': 38,
        'source_hint': 'drop',
    },
    {
        'id': 'acc_fan',
        'name': '折扇', 'slot': 'accessory', 'rarity': 'uncommon',
        'emoji': '🎐', 'color': '#0d9488',
        'flavor': '扇風落子，氣定神閒。',
        'hint': '從狐狸或狼掉落',
        'drop_from': ['wolf', 'fox'], 'drop_weight': 28,
        'source_hint': 'drop',
    },
    {
        'id': 'acc_goboard_bag',
        'name': '棋袋', 'slot': 'accessory', 'rarity': 'common',
        'emoji': '👜', 'color': '#6b5740',
        'flavor': '一袋棋石，走遍天下。',
        'hint': '答題達 30 題後獲得',
        'drop_from': ['caterpillar', 'bee', 'goblin'], 'drop_weight': 40,
        'source_hint': 'drop',
    },
    {
        'id': 'acc_jade_ring',
        'name': '翡翠扳指', 'slot': 'accessory', 'rarity': 'rare',
        'emoji': '💍', 'color': '#1d4ed8',
        'flavor': '翡翠護指，落子有聲。',
        'hint': '從烏龜或兔子掉落（稀有）',
        'drop_from': ['turtle', 'rabbit'], 'drop_weight': 15,
        'source_hint': 'drop',
    },
    {
        'id': 'acc_goban_seal',
        'name': '棋院印章', 'slot': 'accessory', 'rarity': 'rare',
        'emoji': '📛', 'color': '#1d4ed8',
        'flavor': '院章在手，棋道有序。',
        'hint': '連續簽到 21 天解鎖',
        'drop_from': [], 'drop_weight': 0,
        'source_hint': 'daily', 'daily_streak': 21,
    },
    {
        'id': 'acc_dragon_pendant',
        'name': '龍形玉佩', 'slot': 'accessory', 'rarity': 'epic',
        'emoji': '🐲', 'color': '#7c3aed',
        'flavor': '玉龍護身，棋路暢通。',
        'hint': '從巨龍掉落（史詩）',
        'drop_from': ['dragon'], 'drop_weight': 8,
        'source_hint': 'drop',
    },
    {
        'id': 'acc_golden_bell',
        'name': '金鈴鐺', 'slot': 'accessory', 'rarity': 'legendary',
        'emoji': '🔔', 'color': '#d97706',
        'flavor': '鈴聲一響，對手心驚。',
        'hint': '答題精準率達 95% 並達 500 題',
        'drop_from': [], 'drop_weight': 0,
        'source_hint': 'daily', 'daily_streak': 30,
    },

    # ══════════════════════════════════════════════════════════════
    # 寵物（pet） ─ 6 件（新）
    # ══════════════════════════════════════════════════════════════
    {
        'id': 'pet_cat',
        'name': '棋院貓', 'slot': 'pet', 'rarity': 'common',
        'emoji': '🐱', 'color': '#6b5740',
        'flavor': '貓咪坐在棋盤旁，好像也懂棋。',
        'hint': '打敗任意怪物偶爾獲得',
        'drop_from': ['caterpillar', 'bee', 'turtle', 'rabbit'], 'drop_weight': 25,
        'source_hint': 'drop',
    },
    {
        'id': 'pet_turtle',
        'name': '石龜', 'slot': 'pet', 'rarity': 'uncommon',
        'emoji': '🐢', 'color': '#0d9488',
        'flavor': '龜步落子，穩如泰山。',
        'hint': '從烏龜掉落',
        'drop_from': ['turtle'], 'drop_weight': 30,
        'source_hint': 'drop',
    },
    {
        'id': 'pet_rabbit',
        'name': '白兔', 'slot': 'pet', 'rarity': 'uncommon',
        'emoji': '🐰', 'color': '#0d9488',
        'flavor': '兔耳靈敏，棋感超凡。',
        'hint': '從兔子掉落',
        'drop_from': ['rabbit'], 'drop_weight': 28,
        'source_hint': 'drop',
    },
    {
        'id': 'pet_fox',
        'name': '幻狐', 'slot': 'pet', 'rarity': 'rare',
        'emoji': '🦊', 'color': '#1d4ed8',
        'flavor': '幻狐指路，棋局如棋。',
        'hint': '從狐狸掉落（稀有）',
        'drop_from': ['fox'], 'drop_weight': 16,
        'source_hint': 'drop',
    },
    {
        'id': 'pet_wolf',
        'name': '孤狼', 'slot': 'pet', 'rarity': 'rare',
        'emoji': '🐺', 'color': '#1d4ed8',
        'flavor': '狼眼識局，一擊致命。',
        'hint': '從狼掉落（稀有）',
        'drop_from': ['wolf'], 'drop_weight': 16,
        'source_hint': 'drop',
    },
    {
        'id': 'pet_dragon',
        'name': '迷你龍', 'slot': 'pet', 'rarity': 'legendary',
        'emoji': '🐉', 'color': '#d97706',
        'flavor': '龍族傳承，棋道無上。',
        'hint': '從巨龍掉落（傳說）',
        'drop_from': ['dragon'], 'drop_weight': 3,
        'source_hint': 'drop',
    },

    # ══════════════════════════════════════════════════════════════
    # 光環（aura） ─ 5 件（新）
    # ══════════════════════════════════════════════════════════════
    {
        'id': 'aura_green',
        'name': '碧玉光環', 'slot': 'aura', 'rarity': 'uncommon',
        'emoji': '💚', 'color': '#0d9488',
        'flavor': '碧玉之輝，棋心安定。',
        'hint': '連續登入 14 天解鎖',
        'drop_from': [], 'drop_weight': 0,
        'source_hint': 'daily', 'daily_streak': 14,
    },
    {
        'id': 'aura_blue',
        'name': '藍晶光環', 'slot': 'aura', 'rarity': 'rare',
        'emoji': '💙', 'color': '#1d4ed8',
        'flavor': '蒼藍如海，棋海徜徉。',
        'hint': '對弈勝場達 30 場解鎖',
        'drop_from': ['wolf', 'fox'], 'drop_weight': 12,
        'source_hint': 'drop',
    },
    {
        'id': 'aura_flame',
        'name': '熾焰光環', 'slot': 'aura', 'rarity': 'epic',
        'emoji': '🔥', 'color': '#7c3aed',
        'flavor': '烈焰繞身，棋力如炎。',
        'hint': '連勝 20 場解鎖',
        'drop_from': ['golem', 'dragon'], 'drop_weight': 8,
        'source_hint': 'drop',
    },
    {
        'id': 'aura_moon',
        'name': '月光光環', 'slot': 'aura', 'rarity': 'epic',
        'emoji': '🌙', 'color': '#7c3aed',
        'flavor': '月輝落棋，妙思如泉。',
        'hint': '段位達到 2d 解鎖',
        'drop_from': [], 'drop_weight': 0,
        'source_hint': 'rank', 'unlock_rank': '2d',
    },
    {
        'id': 'aura_celestial',
        'name': '天命星輝', 'slot': 'aura', 'rarity': 'legendary',
        'emoji': '🌟', 'color': '#d97706',
        'flavor': '眾星拱月，唯我棋道。',
        'hint': '段位達到 5d 解鎖',
        'drop_from': ['dragon'], 'drop_weight': 2,
        'source_hint': 'rank', 'unlock_rank': '5d',
    },

    # ══════════════════════════════════════════════════════════════
    # 稱號（title） ─ 10 件
    # ══════════════════════════════════════════════════════════════
    {
        'id': 'title_beginner',
        'name': '學棋人', 'slot': 'title', 'rarity': 'common',
        'emoji': '📖', 'color': '#6b5740',
        'flavor': '萬丈高樓，起於壘土。',
        'hint': '打敗任意怪物即可獲得',
        'drop_from': ['caterpillar', 'bee', 'turtle', 'rabbit', 'raccoon', 'goblin'], 'drop_weight': 40,
        'source_hint': 'drop',
    },
    {
        'id': 'title_scholar',
        'name': '棋典學者', 'slot': 'title', 'rarity': 'uncommon',
        'emoji': '📚', 'color': '#0d9488',
        'flavor': '典籍在手，棋理自明。',
        'hint': '錯題本複習達 50 題解鎖',
        'drop_from': [], 'drop_weight': 0,
        'source_hint': 'daily', 'daily_streak': 5,
    },
    {
        'id': 'title_wanderer',
        'name': '棋海漫遊', 'slot': 'title', 'rarity': 'rare',
        'emoji': '🌊', 'color': '#1d4ed8',
        'flavor': '棋海無涯，漫遊其間。',
        'hint': '連續簽到 7 天解鎖',
        'drop_from': [], 'drop_weight': 0,
        'source_hint': 'daily', 'daily_streak': 7,
    },
    {
        'id': 'title_streak',
        'name': '不敗傳說', 'slot': 'title', 'rarity': 'rare',
        'emoji': '⚡', 'color': '#1d4ed8',
        'flavor': '勝者之名，戰無不克。',
        'hint': '連勝 15 場解鎖',
        'drop_from': [], 'drop_weight': 0,
        'source_hint': 'daily', 'daily_streak': 0,
    },
    {
        'id': 'title_foxwit',
        'name': '狡狐之智', 'slot': 'title', 'rarity': 'rare',
        'emoji': '🦊', 'color': '#1d4ed8',
        'flavor': '狡如狐，智如棋。',
        'hint': '從狐狸掉落（稀有）',
        'drop_from': ['fox'], 'drop_weight': 16,
        'source_hint': 'drop',
    },
    {
        'id': 'title_master',
        'name': '千題宗師', 'slot': 'title', 'rarity': 'epic',
        'emoji': '👑', 'color': '#7c3aed',
        'flavor': '千題磨礪，方成宗師。',
        'hint': '答題達 1000 題解鎖',
        'drop_from': [], 'drop_weight': 0,
        'source_hint': 'daily', 'daily_streak': 30,
    },
    {
        'id': 'title_dragonslayer',
        'name': '龍殺者', 'slot': 'title', 'rarity': 'epic',
        'emoji': '⚔️', 'color': '#7c3aed',
        'flavor': '百龍皆斬，棋名遠播。',
        'hint': '擊敗 100 條龍解鎖',
        'drop_from': ['dragon'], 'drop_weight': 8,
        'source_hint': 'drop',
    },
    {
        'id': 'title_godshand',
        'name': '神之一手', 'slot': 'title', 'rarity': 'epic',
        'emoji': '✋', 'color': '#7c3aed',
        'flavor': '棋局如詩，手手皆神。',
        'hint': '答題精準率達 90% 且達 300 題',
        'drop_from': [], 'drop_weight': 0,
        'source_hint': 'daily', 'daily_streak': 0,
    },
    {
        'id': 'title_celestial',
        'name': '天命棋士', 'slot': 'title', 'rarity': 'legendary',
        'emoji': '☯️', 'color': '#d97706',
        'flavor': '天命棋士，棋道通神。',
        'hint': '段位達到 5d 解鎖',
        'drop_from': [], 'drop_weight': 0,
        'source_hint': 'rank', 'unlock_rank': '5d',
    },
    {
        'id': 'title_eternity',
        'name': '永恆之局', 'slot': 'title', 'rarity': 'legendary',
        'emoji': '♾️', 'color': '#d97706',
        'flavor': '棋路無窮，永無止境。',
        'hint': '累計答題達 5000 題解鎖',
        'drop_from': [], 'drop_weight': 0,
        'source_hint': 'rank', 'unlock_rank': '9d',
    },

    # ══════════════════════════════════════════════════════════════
    # ✨ Premium 專屬（訂閱即得，普通用戶無法解鎖）
    # ══════════════════════════════════════════════════════════════
    {
        'id': 'robe_premium',
        'name': '至尊御袍', 'slot': 'outfit', 'rarity': 'legendary',
        'emoji': '✨', 'color': '#d97706',
        'flavor': '尊爵之衣，棋道無上。非 Premium 不可著。',
        'hint': '💎 Premium 會員專屬，訂閱即解鎖',
        'drop_from': [], 'drop_weight': 0,
        'source_hint': 'premium', 'premium_only': True,
    },
    {
        'id': 'hat_premium',
        'name': '鑽石冠冕', 'slot': 'hat', 'rarity': 'legendary',
        'emoji': '👑', 'color': '#d97706',
        'flavor': '冠冕加身，棋壇獨尊。',
        'hint': '💎 Premium 會員專屬，訂閱即解鎖',
        'drop_from': [], 'drop_weight': 0,
        'source_hint': 'premium', 'premium_only': True,
    },
    {
        'id': 'aura_premium',
        'name': '尊爵光環', 'slot': 'aura', 'rarity': 'legendary',
        'emoji': '💛', 'color': '#d97706',
        'flavor': '金光繞身，XP 倍增。',
        'hint': '💎 Premium 會員專屬 · XP +20%',
        'drop_from': [], 'drop_weight': 0,
        'source_hint': 'premium', 'premium_only': True,
    },
    {
        'id': 'pet_premium',
        'name': '麒麟寵物', 'slot': 'pet', 'rarity': 'legendary',
        'emoji': '🦄', 'color': '#d97706',
        'flavor': '麒麟為伴，天下難敵。掉落率大幅提升。',
        'hint': '💎 Premium 會員專屬 · 掉落率 +25%',
        'drop_from': [], 'drop_weight': 0,
        'source_hint': 'premium', 'premium_only': True,
    },
    {
        'id': 'title_premium',
        'name': '✨ 尊爵棋士', 'slot': 'title', 'rarity': 'legendary',
        'emoji': '💎', 'color': '#d97706',
        'flavor': '尊爵棋士，棋壇唯一身份象徵。',
        'hint': '💎 Premium 會員專屬，訂閱即解鎖',
        'drop_from': [], 'drop_weight': 0,
        'source_hint': 'premium', 'premium_only': True,
    },
    {
        'id': 'acc_premium',
        'name': '黃金棋墜', 'slot': 'accessory', 'rarity': 'legendary',
        'emoji': '🏅', 'color': '#d97706',
        'flavor': '黃金鑄就，棋緣永固。XP +8%。',
        'hint': '💎 Premium 會員專屬 · XP +8%',
        'drop_from': [], 'drop_weight': 0,
        'source_hint': 'premium', 'premium_only': True,
    },
]

# 快查字典
_APPEAR_MAP = {a['id']: a for a in APPEARANCE_DEFS}

# ── 外觀效果：item_id → 遊戲加成 ─────────────────────────────────────────────
APPEARANCE_EFFECTS = {
    # 光環（aura）→ XP 加成
    'aura_green':      {'xp_bonus': 0.05,  'label': 'XP +5%'},
    'aura_blue':       {'xp_bonus': 0.10,  'label': 'XP +10%'},
    'aura_flame':      {'xp_bonus': 0.15,  'label': 'XP +15%'},
    'aura_moon':       {'xp_bonus': 0.12,  'label': 'XP +12%'},
    'aura_celestial':  {'xp_bonus': 0.25,  'label': 'XP +25%'},
    # 寵物（pet）→ 怪物掉落率加成
    'pet_cat':         {'drop_bonus': 0.05,  'label': '掉落 +5%'},
    'pet_turtle':      {'drop_bonus': 0.05,  'label': '掉落 +5%'},
    'pet_rabbit':      {'drop_bonus': 0.08,  'label': '掉落 +8%'},
    'pet_fox':         {'drop_bonus': 0.12,  'label': '掉落 +12%'},
    'pet_wolf':        {'drop_bonus': 0.15,  'label': '掉落 +15%'},
    'pet_dragon':      {'drop_bonus': 0.25,  'label': '掉落 +25%'},
    # 袍服（段位限定）→ 小 XP 加成
    'robe_rank_1d':    {'xp_bonus': 0.03,  'label': 'XP +3%'},
    'robe_rank_3d':    {'xp_bonus': 0.05,  'label': 'XP +5%'},
    'robe_rank_5d':    {'xp_bonus': 0.08,  'label': 'XP +8%'},
    'robe_celestial':  {'xp_bonus': 0.05,  'label': 'XP +5%'},
    # 配飾
    'acc_golden_bell': {'xp_bonus': 0.05,  'label': 'XP +5%'},
    # ✨ Premium 專屬
    'aura_premium':    {'xp_bonus': 0.20,  'label': 'XP +20%'},
    'pet_premium':     {'drop_bonus': 0.25, 'label': '掉落 +25%'},
    'robe_premium':    {'xp_bonus': 0.05,  'label': 'XP +5%'},
    'acc_premium':     {'xp_bonus': 0.08,  'label': 'XP +8%'},
}

def _get_appearance_effects(uid, conn):
    """取得玩家已裝備外觀的所有加成，回傳 {xp_bonus, drop_bonus}。"""
    try:
        eq = conn.execute('SELECT * FROM player_appearance WHERE user_id=?', (uid,)).fetchone()
    except Exception:
        return {'xp_bonus': 0.0, 'drop_bonus': 0.0}
    if not eq:
        return {'xp_bonus': 0.0, 'drop_bonus': 0.0}
    xp_b = 0.0; drop_b = 0.0
    cols = eq.keys() if hasattr(eq, 'keys') else []
    for col in ('outfit_id', 'hat_id', 'back_id', 'title_id', 'accessory_id', 'pet_id', 'aura_id'):
        if col not in cols:
            continue
        iid = eq[col]
        if iid and iid in APPEARANCE_EFFECTS:
            fx = APPEARANCE_EFFECTS[iid]
            xp_b   += fx.get('xp_bonus', 0.0)
            drop_b += fx.get('drop_bonus', 0.0)
    return {'xp_bonus': xp_b, 'drop_bonus': drop_b}

# 稀有度掉落機率（外觀獨立於裝備，各自判定）
# 怪物越強，外觀掉落率越高，且能解鎖更高稀有度
APPEARANCE_LOOT_CHANCE = {
    'caterpillar': 0.05,
    'bee':         0.07,
    'turtle':      0.09,
    'rabbit':      0.11,
    'raccoon':     0.13,
    'goblin':      0.15,
    'wolf':        0.20,
    'fox':         0.28,
    'golem':       0.35,
    'dragon':      0.45,
}

# 各怪物可掉落的最高稀有度
APPEARANCE_RARITY_CAP = {
    'caterpillar': ('common',),
    'bee':         ('common',),
    'turtle':      ('common',),
    'rabbit':      ('common', 'uncommon'),
    'raccoon':     ('common', 'uncommon'),
    'goblin':      ('common', 'uncommon'),
    'wolf':        ('common', 'uncommon', 'rare'),
    'fox':         ('common', 'uncommon', 'rare'),
    'golem':       ('uncommon', 'rare', 'epic'),
    'dragon':      ('rare', 'epic', 'legendary'),
}

def _roll_appearance_loot(monster_type):
    """
    獨立判定外觀掉落（與裝備掉落互不干擾）。
    回傳 appearance item dict 或 None。
    """
    import random
    chance = APPEARANCE_LOOT_CHANCE.get(monster_type, 0.15)
    if random.random() > chance:
        return None
    allowed_rarities = APPEARANCE_RARITY_CAP.get(monster_type, ('common',))
    pool = [
        a for a in APPEARANCE_DEFS
        if a['rarity'] in allowed_rarities
        and monster_type in a['drop_from']
        and a['drop_weight'] > 0
    ]
    if not pool:
        return None
    weights = [a['drop_weight'] for a in pool]
    return random.choices(pool, weights=weights, k=1)[0]

# 段位解鎖的限定外觀（rank → [item_id, ...]）
RANK_APPEARANCE_UNLOCKS = {
    '1d': ['robe_rank_1d'],
    '3d': ['robe_rank_3d'],
    '5d': ['robe_rank_5d', 'title_celestial'],
}

def give_rank_appearance(conn, uid, rank_level):
    """
    升 LV 時給予限定外觀；已持有則跳過，回傳新獲得的 item_id 列表。
    rank_level 可為 'LV33' 或舊格式 '1d'，內部都轉成對應外觀 key。
    """
    # 支援 LV 格式與舊格式
    if isinstance(rank_level, str) and rank_level.startswith('LV'):
        lv = int(rank_level[2:])
        old_key = _LV_APPEARANCE_TRIGGER.get(lv)
    else:
        old_key = rank_level
    item_ids = RANK_APPEARANCE_UNLOCKS.get(old_key, [])
    if not item_ids:
        return []
    now = datetime.datetime.now().isoformat()
    new_items = []
    for iid in item_ids:
        existing = conn.execute(
            'SELECT id FROM player_wardrobe WHERE user_id=? AND item_id=?',
            (uid, iid)
        ).fetchone()
        if not existing:
            conn.execute(
                'INSERT INTO player_wardrobe(user_id,item_id,obtained_at,source) VALUES(?,?,?,?)',
                (uid, iid, now, 'rank')
            )
            new_items.append(iid)
    return new_items

def give_daily_appearance(conn, uid, streak):
    """
    每日挑戰連續天數獎勵外觀；回傳新獲得的 item_id 列表。
    """
    rewards = {7: 'title_wanderer', 30: 'title_master'}
    new_items = []
    now = datetime.datetime.now().isoformat()
    for days, iid in rewards.items():
        if streak >= days:
            existing = conn.execute(
                'SELECT id FROM player_wardrobe WHERE user_id=? AND item_id=?',
                (uid, iid)
            ).fetchone()
            if not existing:
                conn.execute(
                    'INSERT INTO player_wardrobe(user_id,item_id,obtained_at,source) VALUES(?,?,?,?)',
                    (uid, iid, now, 'daily')
                )
                new_items.append(iid)
    return new_items

DAILY_QUEST_DEFS = [
    {'key':'kill_monsters',    'name':'戰士初試', 'icon':'⚔️', 'desc':'擊敗 {target} 隻怪物',    'target':5, 'xp':30,  'color':'amber'},
    {'key':'streak_correct',   'name':'精準術士', 'icon':'🎯', 'desc':'單日連續答對 {target} 題','target':3, 'xp':20,  'color':'teal'},
    {'key':'challenge_dragon', 'name':'魔法大師', 'icon':'🧙', 'desc':'挑戰 {target} 道龍族題', 'target':1, 'xp':50,  'color':'purple'},
    {'key':'all_complete',     'name':'熾焰連斬', 'icon':'🔥', 'desc':'完成以上全部任務',        'target':3, 'xp':100, 'color':'red', 'bonus':True},
]

# ── KataGo ─────────────────────────────────────────────────────────
_BASE        = os.path.dirname(os.path.abspath(__file__))
KATAGO_DIR   = os.path.join(_BASE, 'katago-v1.16.4-eigenavx2-windows-x64')
KATAGO_EXE   = os.path.join(KATAGO_DIR, 'katago.exe')
KATAGO_MODEL = os.path.join(KATAGO_DIR, 'kata1-b18c384nbt-s9996604416-d4316597426.bin.gz')
KATAGO_CFG   = os.path.join(KATAGO_DIR, 'analysis_example.cfg')

katago_proc  = None
katago_lock  = threading.Lock()
katago_ready = False
pending      = {}

def start_katago():
    global katago_proc, katago_ready
    if katago_proc and katago_proc.poll() is None:
        return
    katago_ready = False
    katago_proc = subprocess.Popen(
        [KATAGO_EXE, 'analysis', '-model', KATAGO_MODEL, '-config', KATAGO_CFG],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        encoding='utf-8', errors='replace', bufsize=1, cwd=KATAGO_DIR
    )
    threading.Thread(target=read_katago_output, daemon=True).start()
    threading.Thread(target=read_katago_stderr,  daemon=True).start()

def read_katago_stderr():
    global katago_ready
    for line in katago_proc.stderr:
        if 'ready' in line.lower():
            katago_ready = True

def read_katago_output():
    for line in katago_proc.stdout:
        line = line.strip()
        if not line: continue
        try:
            result = json.loads(line)
            qid = result.get('id')
            if qid and qid in pending:
                pending[qid] = result
        except: pass

def query_katago(board_size, stones_black, stones_white, player, moves_so_far, visits=20):
    global katago_ready
    start_katago()
    for _ in range(300):
        if katago_ready: break
        time.sleep(0.1)
    if not katago_ready: return None

    def coord(x, y):
        col = chr(ord('A') + x + (1 if x >= 8 else 0))
        return f"{col}{board_size - y}"

    initial_stones = [['B', coord(s['x'],s['y'])] for s in stones_black] + \
                     [['W', coord(s['x'],s['y'])] for s in stones_white]
    moves = [[m['player'], coord(m['x'],m['y'])] for m in moves_so_far]
    qid = str(uuid.uuid4())[:8]
    pending[qid] = None
    query = {
        'id': qid, 'boardXSize': board_size, 'boardYSize': board_size,
        'rules': 'chinese', 'komi': 7.5, 'initialStones': initial_stones,
        'moves': moves, 'analyzeTurns': [len(moves)], 'maxVisits': visits,
        'includeOwnership': False,
    }
    with katago_lock:
        katago_proc.stdin.write(json.dumps(query) + '\n')
        katago_proc.stdin.flush()
    for _ in range(150):
        time.sleep(0.1)
        if pending[qid] is not None: break
    result = pending.pop(qid, None)
    if not result: return None
    try:
        move_str = result['moveInfos'][0]['move']
        if move_str == 'pass': return None
        col_char = move_str[0]
        col = ord(col_char) - ord('A')
        if col_char >= 'J': col -= 1
        return {'x': col, 'y': board_size - int(move_str[1:])}
    except: return None


def query_katago_analysis(board_size, stones_black, stones_white, player,
                           moves_so_far, visits=50):
    """
    深度分析版：回傳完整 moveInfos（推薦手 + pv 變化圖 + winrate + ownership）。
    供 AI 解說生成使用。回傳 dict 或 None。
    """
    global katago_ready
    start_katago()
    for _ in range(300):
        if katago_ready: break
        time.sleep(0.1)
    if not katago_ready: return None

    def coord(x, y):
        col = chr(ord('A') + x + (1 if x >= 8 else 0))
        return f"{col}{board_size - y}"

    def parse_coord(s):
        if not s or s == 'pass': return None
        col_char = s[0]
        col = ord(col_char) - ord('A')
        if col_char >= 'J': col -= 1
        row = board_size - int(s[1:])
        return {'x': col, 'y': row, 'label': s}

    initial_stones = [['B', coord(s['x'], s['y'])] for s in stones_black] + \
                     [['W', coord(s['x'], s['y'])] for s in stones_white]
    moves = [[m['player'], coord(m['x'], m['y'])] for m in moves_so_far]
    qid = str(uuid.uuid4())[:8]
    pending[qid] = None
    query = {
        'id': qid,
        'boardXSize': board_size, 'boardYSize': board_size,
        'rules': 'chinese', 'komi': 7.5,
        'initialStones': initial_stones,
        'moves': moves,
        'analyzeTurns': [len(moves)],
        'maxVisits': visits,
        'includeOwnership': True,
        'includeMovesOwnership': False,
    }
    with katago_lock:
        katago_proc.stdin.write(json.dumps(query) + '\n')
        katago_proc.stdin.flush()
    for _ in range(300):
        time.sleep(0.1)
        if pending[qid] is not None: break
    result = pending.pop(qid, None)
    if not result: return None
    try:
        root_info  = result.get('rootInfo', {})
        move_infos = result.get('moveInfos', [])
        ownership  = result.get('ownership', [])
        top_moves = []
        for mi in move_infos[:3]:
            mv = parse_coord(mi.get('move', ''))
            if not mv: continue
            top_moves.append({
                'move':    mv,
                'winrate': round(mi.get('winrate', 0) * 100, 1),
                'visits':  mi.get('visits', 0),
                'pv':      [m for m in mi.get('pv', [])[:6] if m != 'pass'],
            })
        ownership_grid = None
        if ownership and len(ownership) == board_size * board_size:
            ownership_grid = [
                [round(ownership[y * board_size + x], 2) for x in range(board_size)]
                for y in range(board_size)
            ]
        return {
            'winrate':        round(root_info.get('winrate', 0.5) * 100, 1),
            'score_lead':     round(root_info.get('scoreLead', 0), 1),
            'top_moves':      top_moves,
            'best_move':      top_moves[0]['move'] if top_moves else None,
            'ownership_grid': ownership_grid,
        }
    except Exception as e:
        print(f'[KataGo analysis error] {e}')
        return None


def warmup_katago():
    def _w():
        time.sleep(2)
        query_katago(19,[{'x':3,'y':3}],[{'x':15,'y':15}],'B',[],visits=1)
    threading.Thread(target=_w, daemon=True).start()

# ── SQLite ─────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(SRS_DB)
    conn.row_factory = sqlite3.Row
    return conn

def _migrate_ranks(conn):
    """將 user_stats.rank_level 從舊段位格式（'15k'/'1d'）遷移到 LV 格式（'LV16'/'LV33'）。"""
    rows = conn.execute("SELECT user_id, xp, rank_level FROM user_stats").fetchall()
    for row in rows:
        rl = row['rank_level'] or 'LV1'
        if rl.startswith('LV'):
            continue  # 已是新格式，跳過
        # 根據 xp 計算正確 LV
        total_xp = row['xp'] or 0
        # 若 xp 太低（舊系統 XP 單位較小），以舊段位推算最低 XP
        old_lv   = _OLD_RANK_TO_LV.get(rl, 1)
        min_xp   = LV_THRESHOLDS[old_lv - 1]
        use_xp   = max(total_xp, min_xp)
        new_lv   = xp_to_lv(use_xp)
        new_rl   = f'LV{new_lv}'
        _, rank_xp, _ = lv_progress(use_xp)
        conn.execute(
            'UPDATE user_stats SET rank_level=?, xp=?, rank_xp=? WHERE user_id=?',
            (new_rl, use_xp, rank_xp, row['user_id'])
        )

# ══════════════════════════════════════════════════════════════════════
# 技能樹常數（8 大學科，無職業體系）
# ══════════════════════════════════════════════════════════════════════

# 每個學科各 3 個技能節點（8 大學科 × 3 層 = 24 節點）
SKILL_NODES = {
    'life_death': [
        {'lv':1, 'name':'數氣入門',   'req':5,   'bonus':'答錯不重計時'},
        {'lv':2, 'name':'眼位識別',   'req':20,  'bonus':'每日配額+2'},
        {'lv':3, 'name':'石佛禪定',   'req':100, 'bonus':'答錯不扣 HP'},
    ],
    'tesuji': [
        {'lv':1, 'name':'棄石為劍',   'req':5,   'bonus':'xp+5%'},
        {'lv':2, 'name':'閃電連擊',   'req':50,  'bonus':'連擊倍率×1.2'},
        {'lv':3, 'name':'破空天斬',   'req':200, 'bonus':'xp+15%'},
    ],
    'chase': [
        {'lv':1, 'name':'疾風刺客',   'req':5,   'bonus':'計時+3s'},
        {'lv':2, 'name':'征子煉法',   'req':30,  'bonus':'氣數標示'},
        {'lv':3, 'name':'天羅地網',   'req':100, 'bonus':'答對觸發連擊'},
    ],
    'shape': [
        {'lv':1, 'name':'棋形初識',   'req':5,   'bonus':'xp+5%'},
        {'lv':2, 'name':'切斷嗅覺',   'req':20,  'bonus':'弱點提示'},
        {'lv':3, 'name':'鋼鐵連環',   'req':80,  'bonus':'連對5題加成'},
    ],
    'fuseki': [
        {'lv':1, 'name':'星象感知',   'req':5,   'bonus':'計時+5s'},
        {'lv':2, 'name':'疆域偵查',   'req':20,  'bonus':'方向提示'},
        {'lv':3, 'name':'天地神諭',   'req':100, 'bonus':'xp+15%'},
    ],
    'whole_board': [
        {'lv':1, 'name':'全局初覽',   'req':5,   'bonus':'計時+5s'},
        {'lv':2, 'name':'大局掌握',   'req':50,  'bonus':'戰略掃描特效'},
        {'lv':3, 'name':'星域領航',   'req':200, 'bonus':'xp+15%'},
    ],
    'endgame_counting': [
        {'lv':1, 'name':'先手感知',   'req':5,   'bonus':'金幣+10%'},
        {'lv':2, 'name':'次序判斷',   'req':20,  'bonus':'連對觸發連利'},
        {'lv':3, 'name':'終局主宰',   'req':100, 'bonus':'金幣+20%'},
    ],
}

# 學科 → 四大屬性對照（8 學科 × 4 屬性）
DISC_TO_ATTR_SKILL = {
    'tesuji':            'atk',
    'chase':             'atk',
    'life_death':        'def',
    'shape':             'def',
    'fuseki':            'vis',
    'whole_board':       'vis',
    'endgame_counting':  'prec',
}

def get_discipline_counts(uid, conn):
    """計算玩家各學科已答對題數。
    直接用 question_id → discipline 映射，不再依賴 keyword 猜測。
    """
    # 建立 id → discipline 查找表（只含啟用中的題目）
    q_disc = {q['id']: q.get('discipline', '') for q in _load_questions()
              if q.get('enabled', True) and q.get('discipline')}

    rows = conn.execute(
        'SELECT question_id, COUNT(*) AS cnt FROM review_log '
        'WHERE user_id=? AND grade>=3 GROUP BY question_id',
        (uid,)
    ).fetchall()

    counts = {d: 0 for d in SKILL_NODES}
    for r in rows:
        disc = q_disc.get(r['question_id'], '')
        if disc in counts:
            counts[disc] += r['cnt']
    return counts

def calc_skill_levels(disc_counts):
    """根據各學科答對題數計算技能等級（已移除職業加速）。"""
    result = {}
    for disc, nodes in SKILL_NODES.items():
        raw = disc_counts.get(disc, 0)
        lv = 0
        for node in nodes:
            if raw >= node['req']:
                lv = node['lv']
        result[disc] = lv
    return result

def sync_skill_tree(uid, conn):
    """重新計算並同步玩家技能樹等級到 skill_tree 表（8 大學科）。"""
    counts = get_discipline_counts(uid, conn)
    levels = calc_skill_levels(counts)
    now = datetime.datetime.utcnow().isoformat()
    for disc, lv in levels.items():
        old = conn.execute(
            'SELECT level FROM skill_tree WHERE user_id=? AND discipline=?',
            (uid, disc)
        ).fetchone()
        if old is None:
            conn.execute(
                'INSERT INTO skill_tree(user_id,discipline,level,unlocked_at) VALUES(?,?,?,?)',
                (uid, disc, lv, now if lv > 0 else None)
            )
        elif lv > old['level']:
            conn.execute(
                'UPDATE skill_tree SET level=?, unlocked_at=? WHERE user_id=? AND discipline=?',
                (lv, now, uid, disc)
            )

# ── 動態稱號（依屬性最高值自動給予） ────────────────────────────────────
_AUTO_TITLES = {
    'atk':  '破空劍客',
    'def':  '聖盾禁衛',
    'vis':  '星域領航員',
    'prec': '終局執秤者',
    'all':  '全能修行者',   # 四屬差距 < 5 時
}

def get_auto_title(attr_atk: int, attr_def: int, attr_vis: int, attr_prec: int) -> str:
    """根據玩家四大屬性點數，自動計算當前動態稱號。"""
    attrs = {'atk': attr_atk, 'def': attr_def, 'vis': attr_vis, 'prec': attr_prec}
    max_val = max(attrs.values())
    min_val = min(attrs.values())
    if max_val == 0:
        return '修煉初心者'
    if max_val - min_val < 5:
        return _AUTO_TITLES['all']
    # 取最高屬性（若並列取 atk→def→vis→prec 優先）
    for key in ('atk', 'def', 'vis', 'prec'):
        if attrs[key] == max_val:
            return _AUTO_TITLES[key]
    return '修煉初心者'


# ── 升級時補發潛能點 ──────────────────────────────────────────────────
ATTR_PTS_PER_LEVEL = 3   # 每升一級獲得 3 點潛能點

def grant_level_up_pts(uid, old_lv, new_lv, conn):
    """當玩家升級時，補發新增等級的潛能點（每級 3 點）。"""
    gained = (new_lv - old_lv) * ATTR_PTS_PER_LEVEL
    if gained > 0:
        conn.execute(
            'UPDATE user_stats SET free_pts = free_pts + ? WHERE user_id=?',
            (gained, uid)
        )

def init_db():
    with get_db() as conn:
        # ── 用戶表 ──────────────────────────────────────────────
        conn.execute('''CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT    NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT    NOT NULL,
            is_admin      INTEGER NOT NULL DEFAULT 0,
            plan          TEXT    NOT NULL DEFAULT 'free',
            created_at    TEXT    NOT NULL,
            last_login    TEXT
        )''')
        # 若資料表已存在但缺少欄位（舊版升級），安全地補上
        for _col, _def in [
            ('plan',           "TEXT NOT NULL DEFAULT 'free'"),
            ('nickname',       "TEXT"),
            ('elo_rating',     "REAL"),          # AI 自適應棋力測驗 Elo 積分
            ('elo_updated_at', "TEXT"),           # 最近一次更新時間
        ]:
            try:
                conn.execute(f'ALTER TABLE users ADD COLUMN {_col} {_def}')
            except Exception:
                pass
        # review_log 補欄位
        for _col, _def in [
            ('source', "TEXT"),   # 記錄來源，如 'rt:<session_id>'
        ]:
            try:
                conn.execute(f'ALTER TABLE review_log ADD COLUMN {_col} {_def}')
            except Exception:
                pass

        # ── SRS ──────────────────────────────────────────────────
        conn.execute('''CREATE TABLE IF NOT EXISTS srs_cards (
            user_id      INTEGER NOT NULL,
            question_id  INTEGER NOT NULL,
            ease_factor  REAL    NOT NULL DEFAULT 2.5,
            interval     INTEGER NOT NULL DEFAULT 0,
            repetitions  INTEGER NOT NULL DEFAULT 0,
            due_date     TEXT    NOT NULL DEFAULT (date('now')),
            last_grade   INTEGER,
            updated_at   TEXT,
            PRIMARY KEY (user_id, question_id)
        )''')

        # ── 用戶統計 ──────────────────────────────────────────────
        conn.execute('''CREATE TABLE IF NOT EXISTS user_stats (
            user_id             INTEGER PRIMARY KEY,
            total_correct       INTEGER NOT NULL DEFAULT 0,
            current_streak      INTEGER NOT NULL DEFAULT 0,
            max_streak          INTEGER NOT NULL DEFAULT 0,
            mistake_corrected   INTEGER NOT NULL DEFAULT 0,
            updated_at          TEXT,
            xp                  INTEGER NOT NULL DEFAULT 0,
            combo_streak        INTEGER NOT NULL DEFAULT 0,
            max_combo           INTEGER NOT NULL DEFAULT 0,
            rank_level          TEXT    NOT NULL DEFAULT 'LV1',
            rank_xp             INTEGER NOT NULL DEFAULT 0
        )''')
        for _col, _def in [
            ('xp',             'INTEGER NOT NULL DEFAULT 0'),
            ('combo_streak',   'INTEGER NOT NULL DEFAULT 0'),
            ('max_combo',      'INTEGER NOT NULL DEFAULT 0'),
            ('rank_level',     "TEXT NOT NULL DEFAULT 'LV1'"),
            ('rank_xp',        'INTEGER NOT NULL DEFAULT 0'),
            ('player_hp',      'INTEGER NOT NULL DEFAULT 100'),
            ('player_max_hp',  'INTEGER NOT NULL DEFAULT 100'),
            ('go_rank',                  "TEXT NOT NULL DEFAULT '30k'"),
            ('coins',                    'INTEGER NOT NULL DEFAULT 0'),
            ('challenge_wins',           'INTEGER NOT NULL DEFAULT 0'),
            ('challenge_win_streak',     'INTEGER NOT NULL DEFAULT 0'),
            ('max_challenge_win_streak', 'INTEGER NOT NULL DEFAULT 0'),
        ]:
            try:
                conn.execute(f'ALTER TABLE user_stats ADD COLUMN {_col} {_def}')
            except Exception:
                pass

        # ── 線上對弈戰績表 ────────────────────────────────────────
        conn.execute('''CREATE TABLE IF NOT EXISTS game_results (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            result      INTEGER NOT NULL,  -- 1=勝 0=負
            go_rank     TEXT    NOT NULL,
            played_at   TEXT    NOT NULL
        )''')
        try:
            conn.execute('CREATE INDEX IF NOT EXISTS idx_gr_uid ON game_results(user_id, played_at)')
        except Exception:
            pass

        # ── 完整對局記錄表 ────────────────────────────────────────
        conn.execute('''CREATE TABLE IF NOT EXISTS game_records (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       INTEGER NOT NULL,
            opponent_name TEXT    NOT NULL DEFAULT '',
            my_color      TEXT    NOT NULL DEFAULT '',
            result        INTEGER NOT NULL,          -- 1=勝 0=負
            reason        TEXT    NOT NULL DEFAULT '',
            move_count    INTEGER NOT NULL DEFAULT 0,
            board_size    INTEGER NOT NULL DEFAULT 19,
            komi          REAL    NOT NULL DEFAULT 6.5,
            black_score   REAL,
            white_score   REAL,
            go_rank       TEXT    NOT NULL DEFAULT '',
            sgf           TEXT    NOT NULL DEFAULT '',
            played_at     TEXT    NOT NULL
        )''')
        try:
            conn.execute('CREATE INDEX IF NOT EXISTS idx_grec_uid ON game_records(user_id, played_at)')
        except Exception:
            pass

        # ── 遷移：舊段位格式（'15k'/'1d'）→ 新 LV 格式（'LV16'/'LV33'）
        _migrate_ranks(conn)

        # ── 獎章 ──────────────────────────────────────────────────
        conn.execute('''CREATE TABLE IF NOT EXISTS badges_earned (
            user_id     INTEGER NOT NULL,
            badge_id    TEXT    NOT NULL,
            earned_at   TEXT    NOT NULL,
            seen        INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, badge_id)
        )''')

        # ── 單元進度 ──────────────────────────────────────────────
        conn.execute('''CREATE TABLE IF NOT EXISTS unit_progress (
            user_id         INTEGER NOT NULL,
            unit_name       TEXT    NOT NULL,
            completed_ids   TEXT    NOT NULL DEFAULT '[]',
            completed_at    TEXT,
            PRIMARY KEY (user_id, unit_name)
        )''')

        # ── 錯題本 ────────────────────────────────────────────────
        conn.execute('''CREATE TABLE IF NOT EXISTS mistake_log (
            user_id         INTEGER NOT NULL,
            question_id     INTEGER NOT NULL,
            wrong_count     INTEGER NOT NULL DEFAULT 1,
            correct_after   INTEGER NOT NULL DEFAULT 0,
            first_wrong_at  TEXT    NOT NULL,
            last_wrong_at   TEXT    NOT NULL,
            last_correct_at TEXT,
            PRIMARY KEY (user_id, question_id)
        )''')

        # ── 每日答題詳細記錄（熱力圖 / 成長曲線 / 每日限制用）──
        conn.execute('''CREATE TABLE IF NOT EXISTS review_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            grade       INTEGER NOT NULL,
            topic       TEXT,
            level       TEXT,
            difficulty  TEXT,
            reviewed_at TEXT    NOT NULL
        )''')
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_review_log_user_date '
            'ON review_log(user_id, reviewed_at)'
        )

        # ── 挑戰賽 ──────────────────────────────────────────────
        conn.execute('''CREATE TABLE IF NOT EXISTS challenges (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            challenger_id    INTEGER NOT NULL,
            opponent_id      INTEGER NOT NULL,
            question_ids     TEXT    NOT NULL DEFAULT '[]',
            challenger_score INTEGER,
            opponent_score   INTEGER,
            status           TEXT    NOT NULL DEFAULT 'pending',
            created_at       TEXT    NOT NULL
        )''')

        # ── 挑戰答題記錄 ─────────────────────────────────────────
        conn.execute('''CREATE TABLE IF NOT EXISTS challenge_answers (
            challenge_id INTEGER NOT NULL,
            user_id      INTEGER NOT NULL,
            answers      TEXT    NOT NULL DEFAULT '{}',
            submitted_at TEXT,
            PRIMARY KEY (challenge_id, user_id)
        )''')

        # ── 師生關係 ─────────────────────────────────────────────
        conn.execute('''CREATE TABLE IF NOT EXISTS teacher_student (
            teacher_id  INTEGER NOT NULL,
            student_id  INTEGER NOT NULL,
            status      TEXT    NOT NULL DEFAULT 'pending',
            created_at  TEXT    NOT NULL,
            PRIMARY KEY (teacher_id, student_id)
        )''')

        # ── 老師留言 ─────────────────────────────────────────────
        conn.execute('''CREATE TABLE IF NOT EXISTS teacher_comments (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_id  INTEGER NOT NULL,
            student_id  INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            comment     TEXT    NOT NULL,
            created_at  TEXT    NOT NULL
        )''')

        # ── 分享連結 ─────────────────────────────────────────────
        conn.execute('''CREATE TABLE IF NOT EXISTS share_links (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            share_token TEXT    NOT NULL UNIQUE,
            title       TEXT    NOT NULL,
            stats_json  TEXT    NOT NULL DEFAULT '{}',
            view_count  INTEGER NOT NULL DEFAULT 0,
            created_at  TEXT    NOT NULL
        )''')

        # ── 怪物 HP 狀態（每日重置）─────────────────────────────
        conn.execute('''CREATE TABLE IF NOT EXISTS monster_hp_log (
            user_id     INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            hp_date     TEXT    NOT NULL,
            current_hp  INTEGER NOT NULL,
            defeated    INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, question_id, hp_date)
        )''')

        # ── 戰場怪物（共享 HP pool，跨題累積傷害）──────────────
        conn.execute('''CREATE TABLE IF NOT EXISTS battlefield_monster (
            user_id      INTEGER NOT NULL,
            bf_date      TEXT    NOT NULL,
            monster_idx  INTEGER NOT NULL DEFAULT 0,
            monster_type TEXT    NOT NULL DEFAULT 'goblin',
            monster_name TEXT    NOT NULL DEFAULT '小妖',
            max_hp       INTEGER NOT NULL DEFAULT 200,
            current_hp   INTEGER NOT NULL DEFAULT 200,
            defeated     INTEGER NOT NULL DEFAULT 0,
            kill_count   INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, bf_date)
        )''')

        # ── 每日任務進度 ─────────────────────────────────────────
        conn.execute('''CREATE TABLE IF NOT EXISTS daily_quests (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            quest_key   TEXT    NOT NULL,
            target      INTEGER NOT NULL,
            progress    INTEGER NOT NULL DEFAULT 0,
            completed   INTEGER NOT NULL DEFAULT 0,
            xp_awarded  INTEGER NOT NULL DEFAULT 0,
            quest_date  TEXT    NOT NULL,
            UNIQUE(user_id, quest_key, quest_date)
        )''')
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_daily_quests_user_date '
            'ON daily_quests(user_id, quest_date)'
        )

        # ── 每日挑戰 ─────────────────────────────────────────────
        conn.execute('''CREATE TABLE IF NOT EXISTS daily_challenge (
            challenge_date  TEXT    PRIMARY KEY,
            question_id     INTEGER NOT NULL,
            set_by          TEXT    NOT NULL DEFAULT 'auto',
            note            TEXT
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS daily_challenge_log (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id        INTEGER NOT NULL,
            challenge_date TEXT    NOT NULL,
            question_id    INTEGER NOT NULL,
            correct        INTEGER NOT NULL DEFAULT 0,
            submitted_at   TEXT    NOT NULL,
            UNIQUE(user_id, challenge_date)
        )''')
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_dc_log_date '
            'ON daily_challenge_log(challenge_date)'
        )

        # ── 今日推薦訓練隊列（持久化，確保每天題目固定）──────────────
        conn.execute('''CREATE TABLE IF NOT EXISTS daily_training_queue (
            user_id      INTEGER NOT NULL,
            date         TEXT    NOT NULL,
            question_ids TEXT    NOT NULL,
            sources      TEXT    NOT NULL DEFAULT '[]',
            generated_at TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
            PRIMARY KEY (user_id, date)
        )''')

        # ── 主線冒險 BOSS 通關狀態 ────────────────────────────────
        conn.execute('''CREATE TABLE IF NOT EXISTS adventure_boss_progress (
            user_id             INTEGER NOT NULL,
            zone_key            TEXT    NOT NULL,
            cleared             INTEGER NOT NULL DEFAULT 0,
            stars               INTEGER NOT NULL DEFAULT 0,
            attempts            INTEGER NOT NULL DEFAULT 0,
            best_score          INTEGER NOT NULL DEFAULT 0,
            cooldown_until_seen INTEGER NOT NULL DEFAULT 0,
            last_attempt_at     TEXT,
            cleared_at          TEXT,
            updated_at          TEXT,
            PRIMARY KEY (user_id, zone_key)
        )''')
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_adv_boss_user '
            'ON adventure_boss_progress(user_id)'
        )
        conn.execute('''CREATE TABLE IF NOT EXISTS adventure_zone_unlocks (
            user_id        INTEGER NOT NULL,
            zone_key       TEXT    NOT NULL,
            source         TEXT    NOT NULL DEFAULT 'placement',
            start_zone_key TEXT,
            unlocked_at    TEXT    NOT NULL,
            PRIMARY KEY (user_id, zone_key)
        )''')
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_adv_unlock_user '
            'ON adventure_zone_unlocks(user_id)'
        )

        # ── 角色外觀衣櫃（持有清單）─────────────────────────────────
        conn.execute('''CREATE TABLE IF NOT EXISTS player_wardrobe (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            item_id     TEXT    NOT NULL,
            obtained_at TEXT    NOT NULL,
            source      TEXT    NOT NULL DEFAULT 'drop',
            UNIQUE(user_id, item_id)
        )''')
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_wardrobe_user '
            'ON player_wardrobe(user_id)'
        )

        # ── 角色外觀目前穿戴狀態 ─────────────────────────────────────
        conn.execute('''CREATE TABLE IF NOT EXISTS player_appearance (
            user_id    INTEGER PRIMARY KEY,
            outfit_id  TEXT,
            hat_id     TEXT,
            back_id    TEXT,
            title_id   TEXT,
            updated_at TEXT
        )''')

        # ── 頭像欄位 migration（av_type / av_value）─────────────────
        existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(player_appearance)").fetchall()}
        if 'av_type' not in existing_cols:
            conn.execute("ALTER TABLE player_appearance ADD COLUMN av_type  TEXT")
        if 'av_value' not in existing_cols:
            conn.execute("ALTER TABLE player_appearance ADD COLUMN av_value TEXT")
        # 新 slot 欄位（配飾 / 寵物 / 光環）
        for _col in ('accessory_id', 'pet_id', 'aura_id'):
            if _col not in existing_cols:
                conn.execute(f"ALTER TABLE player_appearance ADD COLUMN {_col} TEXT")

        # ── 技能習得 ──────────────────────────────────────────────────
        conn.execute('''CREATE TABLE IF NOT EXISTS player_skills (
            user_id     INTEGER NOT NULL,
            skill_id    TEXT    NOT NULL,
            equipped    INTEGER NOT NULL DEFAULT 0,
            learned_at  TEXT    NOT NULL,
            PRIMARY KEY (user_id, skill_id)
        )''')

        # ── 背包（持有裝備）─────────────────────────────────────────
        conn.execute('''CREATE TABLE IF NOT EXISTS player_inventory (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            equip_id    TEXT    NOT NULL,
            equipped    INTEGER NOT NULL DEFAULT 0,
            obtained_at TEXT    NOT NULL,
            source      TEXT    NOT NULL DEFAULT 'drop'
        )''')
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_inv_user '
            'ON player_inventory(user_id)'
        )

        # ── SP 狀態 ──────────────────────────────────────────────────
        conn.execute('''CREATE TABLE IF NOT EXISTS player_sp (
            user_id     INTEGER PRIMARY KEY,
            current_sp  INTEGER NOT NULL DEFAULT 0,
            sp_date     TEXT    NOT NULL DEFAULT (date('now')),
            daily_used  TEXT    NOT NULL DEFAULT '{}'
        )''')

        # ── 題目討論留言 ─────────────────────────────────────────────
        conn.execute('''CREATE TABLE IF NOT EXISTS question_comments (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            question_id INTEGER NOT NULL,
            user_id     INTEGER NOT NULL,
            content     TEXT    NOT NULL,
            created_at  TEXT    NOT NULL,
            likes       INTEGER NOT NULL DEFAULT 0
        )''')
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_qcomments_qid '
            'ON question_comments(question_id, created_at)'
        )

        # ── 留言按讚記錄 ─────────────────────────────────────────────
        conn.execute('''CREATE TABLE IF NOT EXISTS comment_likes (
            user_id    INTEGER NOT NULL,
            comment_id INTEGER NOT NULL,
            PRIMARY KEY (user_id, comment_id)
        )''')

        # ── 好友系統 ─────────────────────────────────────────────
        conn.execute('''CREATE TABLE IF NOT EXISTS friendships (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            from_user   INTEGER NOT NULL,
            to_user     INTEGER NOT NULL,
            status      TEXT    NOT NULL DEFAULT 'pending',
            created_at  TEXT    NOT NULL,
            UNIQUE(from_user, to_user)
        )''')

        # ── 好友挑戰 ─────────────────────────────────────────────
        conn.execute('''CREATE TABLE IF NOT EXISTS friend_challenges (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            from_user     INTEGER NOT NULL,
            to_user       INTEGER NOT NULL,
            status        TEXT    NOT NULL DEFAULT 'pending',
            question_ids  TEXT    NOT NULL,
            num_questions INTEGER NOT NULL DEFAULT 10,
            created_at    TEXT    NOT NULL,
            expires_at    TEXT    NOT NULL
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS friend_challenge_answers (
            challenge_id  INTEGER NOT NULL,
            user_id       INTEGER NOT NULL,
            question_id   INTEGER NOT NULL,
            correct       INTEGER NOT NULL DEFAULT 0,
            answered_at   TEXT    NOT NULL,
            PRIMARY KEY (challenge_id, user_id, question_id)
        )''')

        # ── 怪物擊殺記錄（成就 / 技能解鎖用）───────────────────────
        conn.execute('''CREATE TABLE IF NOT EXISTS monster_kill_log (
            user_id      INTEGER NOT NULL,
            monster_type TEXT    NOT NULL,
            kill_count   INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, monster_type)
        )''')

        # ── 書本難度等級覆寫（改名時繼承，不再依賴書名推算）────────────
        conn.execute('''CREATE TABLE IF NOT EXISTS book_bands (
            name      TEXT PRIMARY KEY,
            band_rank INTEGER NOT NULL
        )''')
        # 舊系統用負值代表 21k–30k，遷移為新正值 (new = old + 10)
        conn.execute('UPDATE book_bands SET band_rank = band_rank + 10 WHERE band_rank < 0')
        # 預置入門篇初始資料（101 書名 & 可能的改名後名稱）
        for _bn, _br in [
            ('26-30級',                        0),
            ('入門篇（21-25級）',               5),
            ('101圍棋練習冊 入門篇（上、中）',  0),
            ('101圍棋練習冊 入門篇（下）',      5),
        ]:
            conn.execute('INSERT OR IGNORE INTO book_bands(name,band_rank) VALUES(?,?)',
                         (_bn, _br))

        # ── 職業 / 屬性 / 技能樹 ─────────────────────────────────────
        # user_stats 新增欄位（舊版升級安全補欄）
        for _col, _def in [
            ('title',          'TEXT DEFAULT NULL'),
            ('attr_atk',       'INTEGER DEFAULT 0'),
            ('attr_def',       'INTEGER DEFAULT 0'),
            ('attr_vis',       'INTEGER DEFAULT 0'),
            ('attr_prec',      'INTEGER DEFAULT 0'),
            ('free_pts',       'INTEGER DEFAULT 0'),
            ('reset_tickets',  'INTEGER DEFAULT 0'),
            ('tutorial_step',  'INTEGER DEFAULT 0'),
        ]:
            try:
                conn.execute(f'ALTER TABLE user_stats ADD COLUMN {_col} {_def}')
            except Exception:
                pass

        # 技能樹進度表
        conn.execute('''CREATE TABLE IF NOT EXISTS skill_tree (
            user_id      INTEGER NOT NULL,
            discipline   TEXT    NOT NULL,
            level        INTEGER NOT NULL DEFAULT 0,
            unlocked_at  TEXT,
            PRIMARY KEY (user_id, discipline)
        )''')

        # ── AI 自適應棋力測驗 ──────────────────────────────────────────
        conn.execute('''CREATE TABLE IF NOT EXISTS rating_test_sessions (
            id          TEXT    PRIMARY KEY,
            user_id     INTEGER,
            status      TEXT    NOT NULL DEFAULT 'in_progress',
            init_rating REAL    NOT NULL DEFAULT 1500,
            cur_rating  REAL    NOT NULL DEFAULT 1500,
            round       INTEGER NOT NULL DEFAULT 0,
            answers     TEXT    NOT NULL DEFAULT '[]',
            trigger     TEXT    NOT NULL DEFAULT 'manual',
            started_at  TEXT    NOT NULL,
            finished_at TEXT
        )''')

        conn.commit()

    _ensure_admin()

def _ensure_admin():
    with get_db() as conn:
        row = conn.execute('SELECT id FROM users WHERE is_admin=1').fetchone()
        if row: return
        now = datetime.datetime.now().isoformat()
        pw  = generate_password_hash('admin1234')
        conn.execute(
            "INSERT INTO users(username,password_hash,is_admin,plan,created_at) VALUES(?,?,1,'premium',?)",
            ('admin', pw, now)
        )
        conn.commit()
    print('\n⚠️  預設管理員已建立：帳號 admin / 密碼 admin1234，請登入後立即更改！\n')

    # ── Grimoire 系統：節點純淨度 & 法典進度表 ──────────────────────
    from grimoire_api import ensure_node_mastery_table
    with get_db() as conn:
        ensure_node_mastery_table(conn)

# ── 認證裝飾器 ─────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'error': '未登入', 'redirect': '/login'}), 401
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'error': '未登入', 'redirect': '/login'}), 401
            return redirect('/login')
        if not session.get('is_admin'):
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'error': '需要管理員權限'}), 403
            return redirect('/')
        return f(*args, **kwargs)
    return decorated


@app.route('/api/admin/shadow/dashboard')
@admin_required
def admin_shadow_dashboard():
    return jsonify(aggregate_shadow_events())

# ── SM-2 ───────────────────────────────────────────────────────
def sm2_update(ef, iv, rp, grade):
    q = grade
    if q < 3:
        rp, iv = 0, 1
    else:
        iv = 1 if rp==0 else (6 if rp==1 else round(iv*ef))
        rp += 1
    ef  = max(1.3, ef + 0.1 - (5-q)*(0.08+(5-q)*0.02))
    due = (datetime.date.today() + datetime.timedelta(days=iv)).isoformat()
    return ef, iv, rp, due

# ── 題目載入（記憶體快取，只第一次讀硬碟）─────────────────────
_questions_cache: list | None = None
_questions_mtime: float = 0.0

_QUESTION_MONSTER_AVATARS = {
    'slime': '/assets/monsters/slime_chibi.png',
    'goblin_guard': '/assets/monsters/goblin_guard_chibi.png',
    'cave_bat': '/assets/monsters/cave_bat_chibi.png',
    'goblin_raider': '/assets/monsters/goblin_raider_chibi.png',
    'orc_grunt': '/assets/monsters/orc_grunt_chibi.png',
    'orc_shield': '/assets/monsters/orc_shield_chibi.png',
    'forest_spirit': '/assets/monsters/forest_spirit_chibi.png',
    'mist_dryad': '/assets/monsters/mist_dryad_chibi.png',
    'tribal_orc': '/assets/monsters/tribal_orc_chibi.png',
    'bounty_warlord': '/assets/monsters/bounty_warlord_chibi.png',
    'wyvern': '/assets/monsters/wyvern_chibi.png',
    'dragon_oracle': '/assets/monsters/dragon_oracle_chibi.png',
    'lich_mage': '/assets/monsters/lich_mage_chibi.png',
    'archmage_lich': '/assets/monsters/archmage_lich_chibi.png',
    'armored_knight': '/assets/monsters/armored_knight_chibi.png',
    'royal_knight': '/assets/monsters/royal_knight_chibi.png',
    'storm_deity': '/assets/monsters/storm_deity_chibi.png',
    'fate_deity': '/assets/monsters/fate_deity_chibi.png',
    'ancient_idol': '/assets/monsters/ancient_idol_chibi.png',
    'omega_idol': '/assets/monsters/omega_idol_chibi.png',
    # Legacy battle-type aliases, kept for old saved battle rows and loot keys.
    'caterpillar': '/assets/monsters/slime_chibi.png',
    'bee': '/assets/monsters/cave_bat_chibi.png',
    'turtle': '/assets/monsters/orc_grunt_chibi.png',
    'rabbit': '/assets/monsters/forest_spirit_chibi.png',
    'raccoon': '/assets/monsters/tribal_orc_chibi.png',
    'wolf': '/assets/monsters/wyvern_chibi.png',
    'fox': '/assets/monsters/lich_mage_chibi.png',
    'goblin': '/assets/monsters/goblin_guard_chibi.png',
    'golem': '/assets/monsters/armored_knight_chibi.png',
    'dragon': '/assets/monsters/storm_deity_chibi.png',
}

def _question_monster_avatar(q):
    return _QUESTION_MONSTER_AVATARS.get(q.get('battle_monster_type'), '/assets/monsters/unknown_chibi.png')

def _load_questions():
    global _questions_cache, _questions_mtime
    if not os.path.exists(DATA_FILE):
        return []
    mtime = os.path.getmtime(DATA_FILE)
    if _questions_cache is not None and mtime == _questions_mtime:
        return _questions_cache          # 快取命中，直接回傳
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            _questions_cache = json.load(f)
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        app.logger.error(f'[_load_questions] 讀取 {DATA_FILE} 失敗：{e}')
        # 嘗試容錯解碼（跳過壞掉的 bytes）
        try:
            with open(DATA_FILE, 'rb') as f:
                raw = f.read()
            _questions_cache = json.loads(raw.decode('utf-8', errors='replace'))
            app.logger.warning(f'[_load_questions] 以容錯模式載入，部分字元可能遺失')
        except Exception as e2:
            app.logger.error(f'[_load_questions] 容錯模式也失敗：{e2}')
            # 回傳舊快取（若有）或空清單，避免整個伺服器崩潰
            return _questions_cache if _questions_cache is not None else []
    try:
        mark_encounters(_questions_cache)
    except Exception as e:
        app.logger.warning(f'[_load_questions] 套用新版怪物分類失敗：{e}')
    _questions_mtime = mtime
    return _questions_cache

def _invalidate_questions_cache():
    """題庫有更新時呼叫此函數清除快取。"""
    global _questions_cache
    _questions_cache = None

def group_label(q):
    t = q.get('topic',''); l = q.get('level','')
    t = t if t and t!='Unknown' else None
    l = l if l and l!='Unknown' else None
    return t or l or '未分類'

# ══════════════════════════════════════════════════════════════
# 訂閱工具函數
# ══════════════════════════════════════════════════════════════

PREMIUM_ITEMS = [a['id'] for a in APPEARANCE_DEFS if a.get('premium_only')]
PREMIUM_BADGES = [b['id'] for b in BADGE_DEFS if b.get('premium_only')]

def grant_premium_rewards(uid, conn):
    """訂閱升級時，自動授予 Premium 專屬外觀物品、徽章，並預設裝備。"""
    now = datetime.datetime.now().isoformat()
    # 授予所有 premium_only 物品
    for iid in PREMIUM_ITEMS:
        conn.execute(
            'INSERT OR IGNORE INTO player_wardrobe(user_id, item_id, obtained_at) VALUES(?,?,?)',
            (uid, iid, now))
    # 授予 Premium 徽章
    for bid in PREMIUM_BADGES:
        conn.execute(
            'INSERT OR IGNORE INTO badges_earned(user_id, badge_id, earned_at, seen) VALUES(?,?,?,0)',
            (uid, bid, now))
    # 預設裝備：御袍 + 冠冕 + 光環 + 麒麟 + 尊爵稱號 + 金墜
    eq = conn.execute('SELECT * FROM player_appearance WHERE user_id=?', (uid,)).fetchone()
    if eq:
        conn.execute('''UPDATE player_appearance
            SET outfit_id='robe_premium',
                hat_id='hat_premium',
                aura_id='aura_premium',
                pet_id='pet_premium',
                title_id='title_premium',
                accessory_id='acc_premium'
            WHERE user_id=?''', (uid,))
    else:
        conn.execute('''INSERT INTO player_appearance
            (user_id, outfit_id, hat_id, aura_id, pet_id, title_id, accessory_id)
            VALUES(?,?,?,?,?,?,?)''',
            (uid,'robe_premium','hat_premium','aura_premium',
             'pet_premium','title_premium','acc_premium'))
    conn.commit()

def is_premium(uid=None):
    """回傳 True 若用戶為付費方案或管理員。"""
    if session.get('is_admin'):
        return True
    uid = uid or session.get('user_id')
    if not uid:
        return False
    # 優先讀 session 快取，避免每次都查 DB
    if session.get('plan') == 'premium':
        return True
    with get_db() as conn:
        row = conn.execute("SELECT plan FROM users WHERE id=?", (uid,)).fetchone()
    return bool(row and row['plan'] == 'premium')

def question_is_free(q):
    """所有題目對免費用戶均開放；付費區隔僅依每日題數上限（FREE_DAILY_LIMIT）。"""
    return True

def get_today_free_count(uid):
    """回傳免費用戶今天已提交的 review 次數。"""
    today = datetime.date.today().isoformat()
    with get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM review_log "
            "WHERE user_id=? AND DATE(reviewed_at)=?",
            (uid, today)
        ).fetchone()
    return row['cnt'] if row else 0

# ── 獎章 ───────────────────────────────────────────────────────
def check_and_award(conn, user_id, stats, unit_name=None):
    already = {r['badge_id'] for r in conn.execute(
        'SELECT badge_id FROM badges_earned WHERE user_id=?', (user_id,)).fetchall()}
    new_badges = []
    now = datetime.datetime.now().isoformat()

    def award(bid):
        if bid not in already:
            conn.execute(
                'INSERT OR IGNORE INTO badges_earned(user_id,badge_id,earned_at,seen) VALUES(?,?,?,0)',
                (user_id, bid, now))
            new_badges.append(bid)

    # 取得目前練習 LV（支援 'LV12' 格式與舊格式）
    rl = stats.get('rank_level', 'LV1') or 'LV1'
    if isinstance(rl, str) and rl.startswith('LV'):
        current_lv = int(rl[2:])
    else:
        current_lv = _OLD_RANK_TO_LV.get(rl, 1)

    for b in BADGE_DEFS:
        btype = b['type']
        if btype == 'total_correct' and stats.get('total_correct', 0) >= b['value']:
            award(b['id'])
        elif btype == 'streak' and stats.get('current_streak', 0) >= b['value']:
            award(b['id'])
        elif btype == 'mistake_corrected' and stats.get('mistake_corrected', 0) >= b['value']:
            award(b['id'])
        elif btype == 'rank':
            target_lv = _RANK_BADGE_MIN_LV.get(b['value'], 999)
            if current_lv >= target_lv:
                award(b['id'])
        elif btype == 'xp' and stats.get('xp', 0) >= b['value']:
            award(b['id'])
        elif btype == 'combo' and stats.get('max_combo', 0) >= b['value']:
            award(b['id'])
        elif btype == 'max_streak' and stats.get('max_streak', 0) >= b['value']:
            award(b['id'])

    if unit_name:
        award('unit_' + unit_name.replace(' ','_'))

    return new_badges

# ── 每日挑戰工具函數 ───────────────────────────────────────────

def get_or_create_daily_challenge(date_str):
    """依日期取得（或自動選出）每日挑戰，回傳 dict。"""
    import hashlib
    qs = _load_questions()
    if not qs:
        return None
    with get_db() as conn:
        row = conn.execute(
            'SELECT * FROM daily_challenge WHERE challenge_date=?', (date_str,)
        ).fetchone()
        if row:
            return dict(row)
        h = int(hashlib.md5(date_str.encode()).hexdigest(), 16)
        q = qs[h % len(qs)]
        conn.execute(
            'INSERT OR IGNORE INTO daily_challenge(challenge_date,question_id,set_by) '
            'VALUES(?,?,?)',
            (date_str, q['id'], 'auto')
        )
        conn.commit()
    return {'challenge_date': date_str, 'question_id': q['id'], 'set_by': 'auto', 'note': None}


def get_daily_submit_streak(uid, today_str):
    """回傳連續提交每日挑戰的天數（含今天，若今天已提交）。"""
    with get_db() as conn:
        rows = conn.execute(
            'SELECT challenge_date FROM daily_challenge_log '
            'WHERE user_id=? ORDER BY challenge_date DESC',
            (uid,)
        ).fetchall()
    dates = {r['challenge_date'] for r in rows}
    streak = 0
    d = datetime.date.fromisoformat(today_str)
    while d.isoformat() in dates:
        streak += 1
        d -= datetime.timedelta(days=1)
    return streak


def check_and_award_daily(conn, uid, correct, today_str):
    """提交每日挑戰後發放對應獎章，回傳新獎章 id 列表。"""
    already = {r['badge_id'] for r in conn.execute(
        'SELECT badge_id FROM badges_earned WHERE user_id=?', (uid,)).fetchall()}
    new_badges = []
    now = datetime.datetime.now().isoformat()

    def award(bid):
        if bid not in already:
            conn.execute(
                'INSERT OR IGNORE INTO badges_earned(user_id,badge_id,earned_at,seen) '
                'VALUES(?,?,?,0)',
                (uid, bid, now))
            new_badges.append(bid)

    award('daily_first')
    if correct:
        award('daily_ace')
    streak = get_daily_submit_streak(uid, today_str)
    for days in [3, 7, 14, 30, 60, 100, 200, 365]:
        if streak >= days:
            award(f'daily_{days}')

    return new_badges

# ── 戰場怪物（共享 HP pool，跨題累積傷害）─────────────────────

# 怪物序列：依等級從小到大，每隻打完才換下一隻
# 每隻怪物有自己的 HP pool（比原本大很多），讓打敗感更有份量
_BATTLEFIELD_ROSTER = [
    # (type, name, max_hp, atk) -- 顯示名稱對齊新版 RPG 族群
    ('caterpillar', 'LV1 史萊姆 / 哥布林',        80,  2),
    ('caterpillar', 'LV1 提子訓練守衛',          100,  2),
    ('bee',         'LV2 哥布林 / 洞窟蝙蝠',    130,  3),
    ('bee',         'LV2 雙叫吃突襲隊',          160,  4),
    ('turtle',      'LV3 獸人小兵',              200,  4),
    ('turtle',      'LV3 做眼厚壁兵',            240,  5),
    ('rabbit',      'LV4 森林精靈',              220,  5),
    ('rabbit',      'LV4 霧林手筋師',            260,  6),
    ('raccoon',     'LV5 部落獸人',              260,  6),
    ('raccoon',     'LV5 銀牌懸賞首領',          290,  7),
    ('wolf',        'LV6 飛龍 / 低階神靈',       520, 12),
    ('dragon',      'LV6 龍谷計算者',            700, 14),
    ('fox',         'LV7 賢者 / 魔法師 / 亡靈',  760, 16),
    ('fox',         'LV7 高塔術師',              920, 18),
    ('golem',       'LV8 騎士 / 混沌領主',      1100, 20),
    ('golem',       'LV8 皇家騎士長',           1350, 22),
    ('dragon',      'LV9 諸神',                 1700, 28),
    ('dragon',      'LV9 命運試煉官',           2000, 32),
    ('dragon',      'LV10 上古終焉神殿',        2400, 36),
    ('dragon',      'LV10 終焉神',              2800, 40),
]

_BATTLEFIELD_AVATARS = {
    'LV1 史萊姆 / 哥布林': '/assets/monsters/slime_chibi.png',
    'LV1 提子訓練守衛': '/assets/monsters/goblin_guard_chibi.png',
    'LV2 哥布林 / 洞窟蝙蝠': '/assets/monsters/cave_bat_chibi.png',
    'LV2 雙叫吃突襲隊': '/assets/monsters/goblin_raider_chibi.png',
    'LV3 獸人小兵': '/assets/monsters/orc_grunt_chibi.png',
    'LV3 做眼厚壁兵': '/assets/monsters/orc_shield_chibi.png',
    'LV4 森林精靈': '/assets/monsters/forest_spirit_chibi.png',
    'LV4 霧林手筋師': '/assets/monsters/mist_dryad_chibi.png',
    'LV5 部落獸人': '/assets/monsters/tribal_orc_chibi.png',
    'LV5 銀牌懸賞首領': '/assets/monsters/bounty_warlord_chibi.png',
    'LV6 飛龍 / 低階神靈': '/assets/monsters/wyvern_chibi.png',
    'LV6 龍谷計算者': '/assets/monsters/dragon_oracle_chibi.png',
    'LV7 賢者 / 魔法師 / 亡靈': '/assets/monsters/lich_mage_chibi.png',
    'LV7 高塔術師': '/assets/monsters/archmage_lich_chibi.png',
    'LV8 騎士 / 混沌領主': '/assets/monsters/armored_knight_chibi.png',
    'LV8 皇家騎士長': '/assets/monsters/royal_knight_chibi.png',
    'LV9 諸神': '/assets/monsters/storm_deity_chibi.png',
    'LV9 命運試煉官': '/assets/monsters/fate_deity_chibi.png',
    'LV10 上古終焉神殿': '/assets/monsters/ancient_idol_chibi.png',
    'LV10 終焉神': '/assets/monsters/omega_idol_chibi.png',
}

_BATTLEFIELD_TYPE_AVATARS = {
    'slime': '/assets/monsters/slime_chibi.png',
    'cave_bat': '/assets/monsters/cave_bat_chibi.png',
    'orc_grunt': '/assets/monsters/orc_grunt_chibi.png',
    'forest_spirit': '/assets/monsters/forest_spirit_chibi.png',
    'tribal_orc': '/assets/monsters/tribal_orc_chibi.png',
    'wyvern': '/assets/monsters/wyvern_chibi.png',
    'lich_mage': '/assets/monsters/lich_mage_chibi.png',
    'armored_knight': '/assets/monsters/armored_knight_chibi.png',
    'storm_deity': '/assets/monsters/storm_deity_chibi.png',
    'ancient_idol': '/assets/monsters/ancient_idol_chibi.png',
    'caterpillar': '/assets/monsters/slime_chibi.png',
    'bee': '/assets/monsters/cave_bat_chibi.png',
    'turtle': '/assets/monsters/orc_grunt_chibi.png',
    'rabbit': '/assets/monsters/forest_spirit_chibi.png',
    'raccoon': '/assets/monsters/tribal_orc_chibi.png',
    'wolf': '/assets/monsters/wyvern_chibi.png',
    'fox': '/assets/monsters/lich_mage_chibi.png',
    'goblin': '/assets/monsters/goblin_guard_chibi.png',
    'golem': '/assets/monsters/armored_knight_chibi.png',
    'dragon': '/assets/monsters/storm_deity_chibi.png',
}

def _battlefield_avatar(monster_type, monster_name):
    return _BATTLEFIELD_AVATARS.get(monster_name) or _BATTLEFIELD_TYPE_AVATARS.get(monster_type, '/assets/monsters/unknown_chibi.png')

def _get_or_create_battlefield(conn, uid, today_str):
    """取得今日戰場怪物，不存在時從第一隻開始。"""
    row = conn.execute(
        'SELECT * FROM battlefield_monster WHERE user_id=? AND bf_date=?',
        (uid, today_str)
    ).fetchone()
    if row:
        data = dict(row)
        # 舊玩家今天可能還留著舊版怪物名稱；第一次讀取時重置到新版 RPG 族群。
        if not str(data.get('monster_name') or '').startswith('LV'):
            m = _BATTLEFIELD_ROSTER[0]
            conn.execute(
                'UPDATE battlefield_monster SET '
                'monster_idx=0, monster_type=?, monster_name=?, max_hp=?, current_hp=?, defeated=0 '
                'WHERE user_id=? AND bf_date=?',
                (m[0], m[1], m[2], m[2], uid, today_str)
            )
            data.update({
                'monster_idx': 0,
                'monster_type': m[0],
                'monster_name': m[1],
                'monster_avatar': _battlefield_avatar(m[0], m[1]),
                'max_hp': m[2],
                'current_hp': m[2],
                'defeated': 0,
            })
        if str(data.get('monster_avatar') or '').endswith('.svg'):
            data['monster_avatar'] = _battlefield_avatar(data['monster_type'], data['monster_name'])
            conn.execute(
                'UPDATE battlefield_monster SET monster_avatar=? WHERE user_id=? AND bf_date=?',
                (data['monster_avatar'], uid, today_str)
            )
        return data
    # 初始化第一隻怪物
    m = _BATTLEFIELD_ROSTER[0]
    conn.execute(
        'INSERT INTO battlefield_monster'
        '(user_id,bf_date,monster_idx,monster_type,monster_name,max_hp,current_hp,defeated,kill_count)'
        ' VALUES(?,?,0,?,?,?,?,0,0)',
        (uid, today_str, m[0], m[1], m[2], m[2])
    )
    return {
        'user_id': uid, 'bf_date': today_str, 'monster_idx': 0,
        'monster_type': m[0], 'monster_name': m[1], 'monster_avatar': _battlefield_avatar(m[0], m[1]),
        'max_hp': m[2], 'current_hp': m[2], 'defeated': 0, 'kill_count': 0,
    }

def _advance_battlefield(conn, uid, today_str, kill_count):
    """打敗當前怪物後，進入下一隻。"""
    next_idx = kill_count % len(_BATTLEFIELD_ROSTER)
    m = _BATTLEFIELD_ROSTER[next_idx]
    conn.execute(
        'UPDATE battlefield_monster SET '
        'monster_idx=?, monster_type=?, monster_name=?, '
        'max_hp=?, current_hp=?, defeated=0 '
        'WHERE user_id=? AND bf_date=?',
        (next_idx, m[0], m[1], m[2], m[2], uid, today_str)
    )
    return {
        'monster_idx': next_idx, 'monster_type': m[0], 'monster_name': m[1], 'monster_avatar': _battlefield_avatar(m[0], m[1]),
        'max_hp': m[2], 'current_hp': m[2], 'defeated': False,
    }

def _calc_damage(grade, max_hp):
    """
    傷害計算：每擊約扣 4~8%，讓每場戰鬥持續 15~25 題。
    連擊加成在 srs_review 傳入 combo_streak 後由呼叫端加乘。
    grade 3 → ~4%  grade 4 → ~6%  grade 5 → ~8%
    """
    import math
    if grade < 3:
        return 0
    pct = {3: 0.04, 4: 0.06, 5: 0.08}.get(grade, 0.04)
    return max(5, math.ceil(max_hp * pct))

def _get_equip_effect(conn, uid, effect_key):
    """加總玩家所有已裝備物品對某效果的貢獻（數值加法）。"""
    rows = conn.execute(
        'SELECT equip_id FROM player_inventory WHERE user_id=? AND equipped=1', (uid,)
    ).fetchall()
    total = 0.0
    for r in rows:
        eq = _EQUIP_MAP.get(r['equip_id'], {})
        total += eq.get('effects', {}).get(effect_key, 0)
    return total

def _get_skill_effect(conn, uid, effect_key):
    """加總玩家所有已裝備技能對某效果的貢獻。"""
    rows = conn.execute(
        'SELECT skill_id FROM player_skills WHERE user_id=? AND equipped=1', (uid,)
    ).fetchall()
    total = 0.0
    for r in rows:
        sk = _SKILL_MAP.get(r['skill_id'], {})
        if sk.get('effect_key') == effect_key:
            total += sk.get('effect_value', 0)
    return total

def _get_combined_effect(conn, uid, effect_key):
    """技能 + 裝備效果合計。"""
    return _get_equip_effect(conn, uid, effect_key) + _get_skill_effect(conn, uid, effect_key)

def _gain_sp(conn, uid, amount):
    """增加 SP，不超過日上限。"""
    today = datetime.date.today().isoformat()
    row = conn.execute('SELECT current_sp,sp_date FROM player_sp WHERE user_id=?', (uid,)).fetchone()
    if not row or row['sp_date'] != today:
        conn.execute(
            'INSERT INTO player_sp(user_id,current_sp,sp_date,daily_used) VALUES(?,?,?,?) '
            'ON CONFLICT(user_id) DO UPDATE SET current_sp=?,sp_date=?,daily_used=?',
            (uid, 0, today, '{}', 0, today, '{}')
        )
        current = 0
    else:
        current = row['current_sp']
    sp_cap_bonus = _get_equip_effect(conn, uid, 'sp_bonus')
    new_sp = min(current + amount, SP_MAX_DAILY + int(sp_cap_bonus))
    conn.execute('UPDATE player_sp SET current_sp=? WHERE user_id=?', (new_sp, uid))
    return new_sp

def _update_monster_and_quests(conn, uid, qid, grade, q_info, combo_streak, today_str):
    # 從題目取攻擊力（怪物反擊傷害），HP 由戰場系統管理
    monster_atk = q_info.get('monster_atk', 8)

    bf = _get_or_create_battlefield(conn, uid, today_str)
    monster_type = bf['monster_type']
    monster_name = bf['monster_name']
    max_hp       = bf['max_hp']
    current_hp   = bf['current_hp']
    kill_count   = bf['kill_count']

    dmg_dealt        = 0
    monster_defeated = False
    player_dmg       = 0
    next_monster     = None   # 若打敗當前怪物，回傳新登場怪物資訊

    # ── 玩家 HP ──────────────────────────────────────────────
    s_row = conn.execute('SELECT player_hp, player_max_hp, rank_level, xp FROM user_stats WHERE user_id=?', (uid,)).fetchone()
    _cur_xp       = (s_row['xp'] or 0) if s_row else 0
    _cur_lv       = xp_to_lv(_cur_xp)
    max_player_hp = _lv_max_hp(_cur_lv)
    # 若 player_max_hp 舊值不符 LV（如剛升 LV），同步更新
    stored_max = s_row['player_max_hp'] if s_row else max_player_hp
    if stored_max < max_player_hp:
        stored_max = max_player_hp
    player_hp  = min(s_row['player_hp'] if s_row else max_player_hp, stored_max)
    player_hp  = max(1, player_hp)   # 確保至少 1（新帳號保護）

    player_ko        = False
    player_hp_change = 0   # 正=回血, 負=受傷

    if grade >= 3:
        dmg_dealt = _calc_damage(grade, max_hp)
        new_hp    = max(0, current_hp - dmg_dealt)
        if new_hp == 0:
            monster_defeated = True
            new_kill_count   = kill_count + 1
            conn.execute(
                'UPDATE battlefield_monster SET current_hp=0, defeated=1, kill_count=? '
                'WHERE user_id=? AND bf_date=?',
                (new_kill_count, uid, today_str)
            )
            current_hp = 0
            # 立刻準備下一隻（前端會延遲顯示）
            nm = _BATTLEFIELD_ROSTER[new_kill_count % len(_BATTLEFIELD_ROSTER)]
            next_monster = {
                'type': nm[0], 'name': nm[1], 'avatar': _battlefield_avatar(nm[0], nm[1]),
                'max_hp': nm[2], 'hp': nm[2],
            }
            # 寫入戰場，等下一次 review 時正式生效
            conn.execute(
                'UPDATE battlefield_monster SET '
                'monster_idx=?, monster_type=?, monster_name=?, '
                'max_hp=?, current_hp=?, defeated=0 '
                'WHERE user_id=? AND bf_date=?',
                (new_kill_count % len(_BATTLEFIELD_ROSTER),
                 nm[0], nm[1], nm[2], nm[2], uid, today_str)
            )
            # 擊敗怪物：回復 max_hp 的 20%（至少 15）
            heal = max(15, round(stored_max * 0.20))
            player_hp = min(stored_max, player_hp + heal)
            player_hp_change = heal
        else:
            conn.execute(
                'UPDATE battlefield_monster SET current_hp=? '
                'WHERE user_id=? AND bf_date=?',
                (new_hp, uid, today_str)
            )
            current_hp = new_hp
            # 答對：回復少量 HP
            heal = 3
            player_hp = min(stored_max, player_hp + heal)
            player_hp_change = heal
    else:
        # 答錯：怪物反擊，扣玩家血量
        dmg_reduce   = _get_combined_effect(conn, uid, 'player_dmg_reduce')
        player_dmg   = max(1, round(monster_atk * (1.0 - dmg_reduce)))
        player_hp    = player_hp - player_dmg
        player_hp_change = -player_dmg
        if player_hp <= 0:
            player_ko = True
            player_hp = max(1, round(stored_max * 0.5))   # KO 後回復 50%
            player_hp_change = -player_dmg  # 還是顯示受到的傷害

    # 寫回玩家 HP
    conn.execute(
        'UPDATE user_stats SET player_hp=?, player_max_hp=? WHERE user_id=?',
        (player_hp, stored_max, uid)
    )

    quest_updates = _update_daily_quests(
        conn, uid, today_str,
        grade=grade,
        monster_defeated=monster_defeated,
        monster_type=monster_type,
        combo_streak=combo_streak,
    )

    # ── KO 懲罰：扣 SP ──────────────────────────────────────
    if player_ko:
        sp_row = conn.execute('SELECT current_sp FROM player_sp WHERE user_id=?', (uid,)).fetchone()
        if sp_row and sp_row['current_sp'] > 0:
            sp_penalty = max(5, round(sp_row['current_sp'] * 0.15))
            conn.execute('UPDATE player_sp SET current_sp=MAX(0,current_sp-?) WHERE user_id=?',
                         (sp_penalty, uid))

    # ── SP 增益 ──────────────────────────────────────────────
    sp_result = None
    if grade >= 3:
        sp_gained = SP_PER_CORRECT
        if monster_defeated:
            kill_sp = _get_skill_effect(conn, uid, 'kill_sp_regen')
            sp_gained += int(kill_sp)
        new_sp = _gain_sp(conn, uid, sp_gained)
        sp_result = {'gained': sp_gained, 'current': new_sp}

    # ── 掉落 ─────────────────────────────────────────────────
    loot_result = None
    appearance_loot = None
    if monster_defeated:
        loot_bonus = _get_combined_effect(conn, uid, 'loot_bonus')
        loot_id    = _roll_loot(monster_type, loot_bonus)
        if loot_id:
            conn.execute(
                'INSERT INTO player_inventory(user_id,equip_id,equipped,obtained_at,source) VALUES(?,?,0,?,?)',
                (uid, loot_id, datetime.datetime.now().isoformat(), 'drop')
            )
            loot_result = _EQUIP_MAP.get(loot_id)

        # 外觀掉落（獨立判定，與裝備互不干擾）
        appear_item = _roll_appearance_loot(monster_type)
        if appear_item:
            now_str = datetime.datetime.now().isoformat()
            conn.execute(
                'INSERT OR IGNORE INTO player_wardrobe(user_id,item_id,obtained_at,source) VALUES(?,?,?,?)',
                (uid, appear_item['id'], now_str, 'drop')
            )
            # 只有真的新入庫才回傳（重複掉落不算新物品）
            if conn.execute(
                'SELECT changes() as n'
            ).fetchone()['n'] > 0:
                appearance_loot = appear_item

        # 擊殺計數
        conn.execute(
            'INSERT INTO monster_kill_log(user_id,monster_type,kill_count) VALUES(?,?,1) '
            'ON CONFLICT(user_id,monster_type) DO UPDATE SET kill_count=kill_count+1',
            (uid, monster_type)
        )

    return {
        'monster': {
            'name':          monster_name,
            'type':          monster_type,
            'avatar':        _battlefield_avatar(monster_type, monster_name),
            'max_hp':        max_hp,
            'hp':            current_hp,
            'dmg':           dmg_dealt,
            'player_dmg':    player_dmg,
            'defeated':      monster_defeated,
            'kill_count':    kill_count + (1 if monster_defeated else 0),
            'wave':          kill_count + (1 if monster_defeated else 0),
            'next_wave_num': kill_count + 2 if monster_defeated else None,
            'next_wave_hp':  next_monster['max_hp'] if next_monster else None,
            'next_monster':  next_monster,
        },
        'player': {
            'hp':        player_hp,
            'max_hp':    stored_max,
            'hp_change': player_hp_change,
            'ko':        player_ko,
        },
        'quest_updates': quest_updates,
        'sp':              sp_result,
        'loot':            loot_result,
        'appearance_loot': appearance_loot,
    }


@app.route('/api/monster/status')
@login_required
def monster_status():
    """前端初始化時取得當前戰場怪物狀態（含玩家 HP + 已裝備技能）。"""
    uid   = session['user_id']
    today = datetime.date.today().isoformat()
    with get_db() as conn:
        bf = _get_or_create_battlefield(conn, uid, today)
        s  = conn.execute('SELECT player_hp, player_max_hp, rank_level, xp FROM user_stats WHERE user_id=?', (uid,)).fetchone()
        equipped_rows = conn.execute(
            'SELECT skill_id FROM player_skills WHERE user_id=? AND equipped=1', (uid,)
        ).fetchall()
        sp_row = conn.execute('SELECT current_sp FROM player_sp WHERE user_id=?', (uid,)).fetchone()
        equip_bonus = _get_equip_effect(conn, uid, 'sp_bonus')   # 必須在 conn 關閉前呼叫
        conn.commit()

    _bf_xp        = (s['xp'] or 0) if s else 0
    _bf_lv        = xp_to_lv(_bf_xp)
    max_player_hp = _lv_max_hp(_bf_lv)
    stored_max = max(max_player_hp, s['player_max_hp'] if s else max_player_hp)
    player_hp  = min(s['player_hp'] if s else stored_max, stored_max)
    player_hp  = max(1, player_hp)
    current_sp = sp_row['current_sp'] if sp_row else 0

    skills_info = []
    for r in equipped_rows:
        sk = _SKILL_MAP.get(r['skill_id'])
        if sk:
            skills_info.append({
                'id':       sk['id'],
                'name':     sk['name'],
                'icon':     sk['icon'],
                'type':     sk['type'],
                'desc':     sk['desc'],
                'cost_sp':  sk.get('cost_sp', 0),
                'color':    sk.get('color', 'teal'),
            })

    # 計算 SP 上限（含裝備加成，equip_bonus 已在 with 區塊內取得）
    max_sp = SP_MAX_DAILY + int(equip_bonus)

    return jsonify({
        'name':       bf['monster_name'],
        'type':       bf['monster_type'],
        'avatar':     _battlefield_avatar(bf['monster_type'], bf['monster_name'])
                      if str(bf.get('monster_avatar') or '').endswith('.svg')
                      else (bf.get('monster_avatar') or _battlefield_avatar(bf['monster_type'], bf['monster_name'])),
        'max_hp':     bf['max_hp'],
        'hp':         bf['current_hp'],
        'kill_count': bf['kill_count'],
        'wave':       bf['kill_count'],
        'defeated':   bool(bf['defeated']),
        'player': {
            'hp':     player_hp,
            'max_hp': stored_max,
            'ko':     False,
        },
        'skills':     skills_info,
        'current_sp': current_sp,
        'max_sp':     max_sp,
    })


def _update_daily_quests(conn, uid, today_str, *, grade, monster_defeated,
                         monster_type, combo_streak):
    results          = []
    non_bonus_done   = 0

    for q in DAILY_QUEST_DEFS:
        key    = q['key']
        target = q['target']
        conn.execute(
            'INSERT OR IGNORE INTO daily_quests'
            '(user_id,quest_key,target,progress,completed,xp_awarded,quest_date)'
            ' VALUES(?,?,?,0,0,0,?)',
            (uid, key, target, today_str)
        )
        row = conn.execute(
            'SELECT progress,completed FROM daily_quests '
            'WHERE user_id=? AND quest_key=? AND quest_date=?',
            (uid, key, today_str)
        ).fetchone()
        prog      = row['progress']
        completed = bool(row['completed'])

        delta = 0
        streak_reset = False
        if not completed and key != 'all_complete':
            if key == 'kill_monsters' and monster_defeated:
                delta = 1
            elif key == 'streak_correct':
                if grade >= 3:
                    delta = 1           # 每答對一題 +1
                else:
                    streak_reset = True # 答錯時進度歸零
            elif key == 'challenge_dragon' and monster_type == 'dragon' and grade >= 3:
                delta = 1

        # 連擊任務：答錯時重置進度
        if streak_reset and not completed:
            conn.execute(
                'UPDATE daily_quests SET progress=0 '
                'WHERE user_id=? AND quest_key=? AND quest_date=?',
                (uid, key, today_str)
            )
            prog = 0

        if delta:
            prog = min(prog + delta, target)
            just_completed = (prog >= target)
            xp_awarded = 0
            if just_completed and not completed:
                conn.execute(
                    'UPDATE user_stats SET xp=xp+?, rank_xp=rank_xp+? WHERE user_id=?',
                    (q['xp'], q['xp'], uid)
                )
                xp_awarded = q['xp']
            conn.execute(
                'UPDATE daily_quests SET progress=?, completed=?, xp_awarded=? '
                'WHERE user_id=? AND quest_key=? AND quest_date=?',
                (prog, int(prog >= target), xp_awarded, uid, key, today_str)
            )
            completed = (prog >= target)

        if not q.get('bonus') and completed:
            non_bonus_done += 1

        results.append({
            'key':       key,
            'name':      q['name'],
            'icon':      q['icon'],
            'color':     q['color'],
            'progress':  prog,
            'target':    target,
            'completed': completed,
            'xp':        q['xp'],
            'bonus':     q.get('bonus', False),
        })

    # all_complete：前三個任務都完成才解鎖
    bonus = next((r for r in results if r['key'] == 'all_complete'), None)
    if bonus and not bonus['completed']:
        bonus['progress'] = non_bonus_done
        if non_bonus_done >= 3:
            bonus['completed'] = True
            bxp = next(d['xp'] for d in DAILY_QUEST_DEFS if d['key'] == 'all_complete')
            conn.execute(
                'UPDATE user_stats SET xp=xp+?, rank_xp=rank_xp+? WHERE user_id=?',
                (bxp, bxp, uid)
            )
            conn.execute(
                'UPDATE daily_quests SET progress=3, completed=1, xp_awarded=? '
                'WHERE user_id=? AND quest_key=? AND quest_date=?',
                (bxp, uid, 'all_complete', today_str)
            )

    return results


# ══════════════════════════════════════════════════════════════
# 認證 API
# ══════════════════════════════════════════════════════════════

@app.route('/api/auth/register', methods=['POST'])
def auth_register():
    import re
    data     = request.get_json() or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    confirm  = data.get('confirm')  or ''
    nickname = (data.get('nickname') or '').strip()

    # ── 驗證 ──
    if not username or not password:
        return jsonify({'error': '請填寫帳號和密碼'}), 400
    if not re.match(r'^[A-Za-z0-9_]{3,20}$', username):
        return jsonify({'error': '帳號只能包含英文、數字、底線，長度 3–20 字元'}), 400
    if len(password) < 6:
        return jsonify({'error': '密碼至少 6 個字元'}), 400
    if confirm and confirm != password:
        return jsonify({'error': '兩次密碼不一致'}), 400
    if nickname and len(nickname) > 30:
        return jsonify({'error': '暱稱不能超過 30 字元'}), 400

    now = datetime.datetime.now().isoformat()
    pw_hash = generate_password_hash(password)

    with get_db() as conn:
        # 檢查帳號是否已存在
        existing = conn.execute(
            'SELECT id FROM users WHERE username=? COLLATE NOCASE', (username,)
        ).fetchone()
        if existing:
            return jsonify({'error': '此帳號已被使用，請換一個'}), 409

        # 建立用戶
        cur = conn.execute(
            'INSERT INTO users(username, password_hash, is_admin, plan, created_at, nickname)'
            ' VALUES(?,?,0,?,?,?)',
            (username, pw_hash, 'free', now, nickname or None)
        )
        uid = cur.lastrowid
        conn.execute('INSERT OR IGNORE INTO user_stats(user_id) VALUES(?)', (uid,))
        conn.commit()

    # 自動登入
    session.permanent   = True
    session['user_id']  = uid
    session['username'] = username
    session['nickname'] = nickname or ''
    session['is_admin'] = False
    session['plan']     = 'free'
    return jsonify({'ok': True, 'username': username, 'nickname': nickname or ''})


@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    data     = request.get_json()
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    if not username or not password:
        return jsonify({'error': '請填寫帳號和密碼'}), 400

    with get_db() as conn:
        row = conn.execute(
            'SELECT * FROM users WHERE username=?', (username,)).fetchone()
        if not row or not check_password_hash(row['password_hash'], password):
            return jsonify({'error': '帳號或密碼錯誤'}), 401

        conn.execute('UPDATE users SET last_login=? WHERE id=?',
                     (datetime.datetime.now().isoformat(), row['id']))
        conn.execute('INSERT OR IGNORE INTO user_stats(user_id) VALUES(?)', (row['id'],))
        conn.commit()

    plan = row['plan'] if 'plan' in row.keys() else 'free'
    nickname = row['nickname'] if 'nickname' in row.keys() else None
    session.permanent    = True
    session['user_id']   = row['id']
    session['username']  = row['username']
    session['nickname']  = nickname or ''
    session['is_admin']  = bool(row['is_admin'])
    session['plan']      = plan
    return jsonify({
        'ok':        True,
        'username':  row['username'],
        'nickname':  nickname or '',
        'is_admin':  bool(row['is_admin']),
        'plan':      plan,
        'is_premium': plan == 'premium' or bool(row['is_admin']),
    })

@app.route('/api/auth/logout', methods=['POST'])
def auth_logout():
    session.clear()
    return jsonify({'ok': True})

@app.route('/api/auth/me')
def auth_me():
    if 'user_id' not in session:
        return jsonify({'logged_in': False})
    plan = session.get('plan', 'free')
    uid  = session['user_id']
    go_rank    = '30k'
    elo_rating = None
    with get_db() as conn:
        row = conn.execute('SELECT go_rank FROM user_stats WHERE user_id=?', (uid,)).fetchone()
        if row:
            go_rank = row['go_rank'] or '30k'
        row2 = conn.execute('SELECT elo_rating FROM users WHERE id=?', (uid,)).fetchone()
        if row2:
            elo_rating = row2['elo_rating']
    return jsonify({
        'logged_in':  True,
        'user_id':    uid,
        'username':   session['username'],
        'nickname':   session.get('nickname', ''),
        'is_admin':   session.get('is_admin', False),
        'plan':       plan,
        'is_premium': plan == 'premium' or session.get('is_admin', False),
        'go_rank':    go_rank,
        'elo_rating': elo_rating,
    })

@app.route('/api/auth/change-password', methods=['POST'])
@login_required
def change_password():
    data   = request.get_json()
    old_pw = data.get('old_password') or ''
    new_pw = data.get('new_password') or ''
    if len(new_pw) < 6:
        return jsonify({'error': '新密碼至少 6 個字元'}), 400
    with get_db() as conn:
        row = conn.execute('SELECT password_hash FROM users WHERE id=?',
                           (session['user_id'],)).fetchone()
        if not row or not check_password_hash(row['password_hash'], old_pw):
            return jsonify({'error': '舊密碼不正確'}), 401
        conn.execute('UPDATE users SET password_hash=? WHERE id=?',
                     (generate_password_hash(new_pw), session['user_id']))
        conn.commit()
    return jsonify({'ok': True})


@app.route('/api/user/set_placement_elo', methods=['POST'])
@login_required
def set_placement_elo():
    """新手自填段位，儲存初始 Elo（僅在尚未有 elo_rating 時才寫入）。"""
    data = request.get_json() or {}
    elo  = float(data.get('elo', 1100))
    elo  = max(700.0, min(2500.0, elo))
    uid  = session['user_id']
    with get_db() as conn:
        conn.execute(
            'UPDATE users SET elo_rating=?, elo_updated_at=? WHERE id=? AND elo_rating IS NULL',
            (elo, datetime.datetime.utcnow().isoformat(), uid)
        )
        conn.commit()
    start_zone_key = _apply_placement_adventure_unlock(uid, elo, 'placement_self')
    return jsonify({'ok': True, 'elo_rating': elo, 'start_zone_key': start_zone_key})


@app.route('/api/auth/nickname', methods=['POST'])
@login_required
def change_nickname():
    data     = request.get_json() or {}
    nickname = (data.get('nickname') or '').strip()
    if len(nickname) > 20:
        return jsonify({'error': '暱稱最多 20 個字'}), 400
    uid = session['user_id']
    with get_db() as conn:
        conn.execute('UPDATE users SET nickname=? WHERE id=?', (nickname or None, uid))
        conn.commit()
    session['nickname'] = nickname
    return jsonify({'ok': True, 'nickname': nickname})


# ══════════════════════════════════════════════════════════════
# 管理員 API
# ══════════════════════════════════════════════════════════════

@app.route('/api/admin/users')
@admin_required
def admin_list_users():
    with get_db() as conn:
        rows = conn.execute(
            '''SELECT u.id, u.username, u.is_admin, u.plan, u.created_at, u.last_login,
                      COALESCE(s.total_correct,0) as total_correct,
                      COALESCE(s.max_streak,0)    as max_streak,
                      COUNT(DISTINCT b.badge_id)  as badge_count
               FROM users u
               LEFT JOIN user_stats   s ON s.user_id=u.id
               LEFT JOIN badges_earned b ON b.user_id=u.id
               GROUP BY u.id ORDER BY u.created_at''').fetchall()
    return jsonify([dict(r) for r in rows])

@app.route('/api/admin/users', methods=['POST'])
@admin_required
def admin_create_user():
    data     = request.get_json()
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    is_admin = bool(data.get('is_admin', False))
    plan     = data.get('plan', 'free')
    if plan not in ('free', 'premium'):
        plan = 'free'
    if not username or len(password) < 6:
        return jsonify({'error': '帳號不可空白，密碼至少 6 字元'}), 400
    now = datetime.datetime.now().isoformat()
    try:
        with get_db() as conn:
            conn.execute(
                'INSERT INTO users(username,password_hash,is_admin,plan,created_at) VALUES(?,?,?,?,?)',
                (username, generate_password_hash(password), int(is_admin), plan, now))
            uid = conn.execute('SELECT id FROM users WHERE username=?', (username,)).fetchone()['id']
            conn.execute('INSERT OR IGNORE INTO user_stats(user_id) VALUES(?)', (uid,))
            conn.commit()
    except sqlite3.IntegrityError:
        return jsonify({'error': f'帳號「{username}」已存在'}), 409
    return jsonify({'ok': True})

@app.route('/api/admin/users/<int:uid>', methods=['DELETE'])
@admin_required
def admin_delete_user(uid):
    if uid == session['user_id']:
        return jsonify({'error': '不能刪除自己'}), 400
    with get_db() as conn:
        conn.execute('DELETE FROM users          WHERE id=?',      (uid,))
        conn.execute('DELETE FROM user_stats     WHERE user_id=?', (uid,))
        conn.execute('DELETE FROM srs_cards      WHERE user_id=?', (uid,))
        conn.execute('DELETE FROM badges_earned  WHERE user_id=?', (uid,))
        conn.execute('DELETE FROM mistake_log    WHERE user_id=?', (uid,))
        conn.execute('DELETE FROM unit_progress  WHERE user_id=?', (uid,))
        conn.execute('DELETE FROM review_log     WHERE user_id=?', (uid,))
        conn.commit()
    return jsonify({'ok': True})

@app.route('/api/admin/users/<int:uid>/reset-password', methods=['POST'])
@admin_required
def admin_reset_password(uid):
    data   = request.get_json()
    new_pw = data.get('new_password') or ''
    if len(new_pw) < 6:
        return jsonify({'error': '密碼至少 6 字元'}), 400
    with get_db() as conn:
        conn.execute('UPDATE users SET password_hash=? WHERE id=?',
                     (generate_password_hash(new_pw), uid))
        conn.commit()
    return jsonify({'ok': True})

@app.route('/api/admin/users/<int:uid>/toggle-admin', methods=['POST'])
@admin_required
def admin_toggle_admin(uid):
    if uid == session['user_id']:
        return jsonify({'error': '不能修改自己的權限'}), 400
    with get_db() as conn:
        row = conn.execute('SELECT is_admin FROM users WHERE id=?', (uid,)).fetchone()
        if not row: return jsonify({'error': '找不到用戶'}), 404
        new_val = 0 if row['is_admin'] else 1
        conn.execute('UPDATE users SET is_admin=? WHERE id=?', (new_val, uid))
        conn.commit()
    return jsonify({'ok': True, 'is_admin': bool(new_val)})

@app.route('/api/admin/users/<int:uid>/set-plan', methods=['POST'])
@admin_required
def admin_set_plan(uid):
    data = request.get_json()
    plan = data.get('plan', 'free')
    if plan not in ('free', 'premium'):
        return jsonify({'error': '方案只能是 free 或 premium'}), 400
    with get_db() as conn:
        conn.execute("UPDATE users SET plan=? WHERE id=?", (plan, uid))
        if plan == 'premium':
            grant_premium_rewards(uid, conn)
        conn.commit()
    return jsonify({'ok': True, 'plan': plan})

# ══════════════════════════════════════════════════════════════
# KataGo API
# ══════════════════════════════════════════════════════════════

@app.route('/api/katago-move', methods=['POST'])
@login_required
def katago_move():
    """答錯後查對方回應手，純靠 precompute.py 預計算的快取，不即時呼叫 KataGo。"""
    d           = request.get_json()
    board_size  = d.get('boardSize', 19)
    moves       = d.get('moves', [])
    question_id = d.get('questionId')

    # 錯誤落子轉 SGF 座標
    wrong_move_sgf = None
    if moves and question_id:
        last = moves[-1]
        wrong_move_sgf = chr(ord('a') + last['x']) + chr(ord('a') + last['y'])

    if wrong_move_sgf and question_id:
        try:
            with sqlite3.connect(CACHE_DB) as cc:
                cc.row_factory = sqlite3.Row
                row = cc.execute(
                    'SELECT response_move FROM katago_cache '
                    'WHERE question_id=? AND wrong_move=? LIMIT 1',
                    (question_id, wrong_move_sgf)
                ).fetchone()
            if row and row['response_move']:
                gtp = row['response_move'].upper().strip()
                if len(gtp) >= 2 and gtp[0].isalpha() and gtp[0] != 'I':
                    col_char = gtp[0]
                    col = ord(col_char) - ord('A')
                    if col_char >= 'J': col -= 1
                    try:
                        ry = board_size - int(gtp[1:])
                        return jsonify({'ok': True, 'x': col, 'y': ry})
                    except ValueError:
                        pass
        except Exception as e:
            print(f'[katago-move] cache error: {e}')

    return jsonify({'ok': False})

# ══════════════════════════════════════════════════════════════
# AI 解說 API
# ══════════════════════════════════════════════════════════════

# SGF 座標欄位字典 → 棋盤標記，方便塞進 LLM prompt
_COL_LETTERS = 'ABCDEFGHJKLMNOPQRST'

def _coord_label(x, y, board_size):
    """棋盤座標 (0-indexed x, y) → 'A1' 格式（KataGo 慣例）。"""
    if x < 0 or y < 0 or x >= board_size or y >= board_size:
        return '?'
    col = _COL_LETTERS[x] if x < len(_COL_LETTERS) else str(x)
    row = board_size - y
    return f"{col}{row}"

def _build_explain_prompt(q_info, wrong_move_label, katago_data, sgf_comment, player_color):
    """
    把 KataGo 分析資料 + 題目資訊包裝成給 LLM 的 system+user prompt。
    """
    topic      = q_info.get('topic', '死活題')
    level      = q_info.get('level', '')
    difficulty = q_info.get('difficulty', '')
    header     = f"{topic}{'・' + level if level else ''}{'（' + difficulty + '）' if difficulty else ''}"

    best       = katago_data.get('best_move') if katago_data else None
    best_label = best['label'] if best else '不明'
    top_moves  = (katago_data or {}).get('top_moves', [])

    # 前三推薦手 + 變化圖
    move_lines = []
    for i, tm in enumerate(top_moves[:3], 1):
        pv_str = ' → '.join(tm['pv'][:4]) if tm['pv'] else '（無）'
        move_lines.append(
            f"  {i}. {tm['move']['label']}（勝率 {tm['winrate']}%）  後續: {pv_str}"
        )
    move_block = '\n'.join(move_lines) if move_lines else '  （KataGo 未回應）'

    # SGF 既有解說（可作為參考背景）
    sgf_block = f"\n【SGF 原始解說】{sgf_comment}" if sgf_comment else ''

    system_prompt = (
        "你是一位圍棋教練，擅長用淺顯易懂的中文解說死活題。"
        "請從「眼位」、「氣數」、「死活形態」出發說明，"
        "不要提勝率或 AI 數值，口吻溫馨但嚴謹，像在跟學生說話。"
        "回覆格式：\n"
        "一段失誤原因（3–4 句）\n"
        "一段正確思路（3–4 句）\n"
        "最後一行：「💡 老師提醒：」一句話點睛。"
        "全文勿超過 200 字。"
    )

    user_prompt = (
        f"【題目】{header}{sgf_block}\n\n"
        f"【棋手顏色】{'黑棋' if player_color == 'B' else '白棋'}\n"
        f"【錯誤下法】{wrong_move_label}\n"
        f"【正確要點】{best_label}\n"
        f"【AI 推薦手（參考）】\n{move_block}\n\n"
        "請根據以上資料，生成一段簡潔的死活題解說，幫助學生理解失誤原因與正確思路。"
    )
    return system_prompt, user_prompt


@app.route('/api/explain', methods=['POST'])
@login_required
def ai_explain():
    """
    AI 解說：優先查 katago_cache.db，無資料時 fallback 到 SGF 解說。

    Request JSON:
        boardSize   : int
        black       : [{x, y}, ...]
        white       : [{x, y}, ...]
        playerColor : 'B' | 'W'
        wrongMove   : {x, y} | null
        questionId  : int

    Response JSON:
        ok          : bool
        explanation : str
        best_move   : {x, y, label} | null
        source      : 'cache' | 'sgf' | 'fallback'
    """
    if not is_premium():
        return jsonify({'error': 'premium_required', 'upgrade_url': '/upgrade'}), 403

    d            = request.get_json() or {}
    board_size   = d.get('boardSize', 9)
    player_color = d.get('playerColor', 'B')
    wrong_move   = d.get('wrongMove')
    question_id  = d.get('questionId')
    correct_moves = d.get('correctMoves') or []   # SGF 正確答案座標列表

    # ── 1. 題目資訊 + SGF 解說 ────────────────────────────────
    qs_map      = {q['id']: q for q in _load_questions()}
    q_info      = qs_map.get(question_id, {})
    sgf_comment = q_info.get('comment') or ''

    # ── 1b. 從前端傳來的 black/white 重建 board_state ─────────
    black_stones = d.get('black', [])
    white_stones = d.get('white', [])
    bs_int = int(board_size) if board_size else 9
    board_state = [[0] * bs_int for _ in range(bs_int)]
    for s in black_stones:
        x, y = s.get('x', -1), s.get('y', -1)
        if 0 <= x < bs_int and 0 <= y < bs_int:
            board_state[y][x] = 1
    for s in white_stones:
        x, y = s.get('x', -1), s.get('y', -1)
        if 0 <= x < bs_int and 0 <= y < bs_int:
            board_state[y][x] = -1

    # ── 2. 從 katago_cache.db 查快取 ─────────────────────────
    # wrong_move 欄位為 SGF 小寫座標（a=0, b=1...），
    # response_move 欄位為 KataGo 標記（如 'Q17'）
    _COL_LETTERS = 'ABCDEFGHJKLMNOPQRST'

    def _xy_to_sgf(x, y):
        return chr(ord('a') + x) + chr(ord('a') + y)

    def _parse_katago_label_local(label, bs):
        if not label or label.lower() == 'pass':
            return None
        label = label.upper().strip()
        col_char = label[0]
        if col_char not in _COL_LETTERS:
            return None
        x = _COL_LETTERS.index(col_char)
        try:
            y = bs - int(label[1:])
        except ValueError:
            return None
        if x < 0 or x >= bs or y < 0 or y >= bs:
            return None
        return {'x': x, 'y': y, 'label': label}

    katago_raw = None
    cache_best_move = None

    if question_id:
        try:
            with sqlite3.connect(CACHE_DB) as cconn:
                cconn.row_factory = sqlite3.Row
                if wrong_move:
                    sgf_wrong = _xy_to_sgf(wrong_move['x'], wrong_move['y'])
                    row = cconn.execute(
                        'SELECT response_move, visits FROM katago_cache '
                        'WHERE question_id=? AND wrong_move=? LIMIT 1',
                        (question_id, sgf_wrong)
                    ).fetchone()
                else:
                    # 答對時取該題第一個 response_move 作為建議手
                    row = cconn.execute(
                        'SELECT response_move, visits FROM katago_cache '
                        'WHERE question_id=? LIMIT 1',
                        (question_id,)
                    ).fetchone()

                if row:
                    resp_label = row['response_move']
                    bs = board_size or 19
                    cache_best_move = _parse_katago_label_local(resp_label, bs)
                    if cache_best_move:
                        # 組合成 KataGoExplainer.parse() 相容的 JSON 結構
                        katago_raw = {
                            'rootInfo':  {'winrate': 0.5, 'scoreLead': 0.0, 'visits': row['visits']},
                            'moveInfos': [{
                                'move':      resp_label,
                                'winrate':   0.5,
                                'visits':    row['visits'],
                                'scoreLead': 0.0,
                                'pv':        [resp_label],
                            }],
                        }
        except Exception as e:
            print(f'[explain] cache lookup error: {e}')

    # ── 3. 轉換層：cache JSON → 人話解說 ─────────────────────
    explainer   = KataGoExplainer(board_size=board_size)
    explanation = explainer.explain(
        katago_raw,
        player_color=player_color,
        wrong_move=wrong_move,
        sgf_comment=sgf_comment,
        q_info=q_info,
        board_state=board_state,       # ✅ 接通棋盤狀態，啟用手筋偵測
        correct_moves=correct_moves,
    )
    best_move = cache_best_move
    source    = 'cache' if katago_raw else ('sgf' if sgf_comment else 'fallback')

    return jsonify({
        'ok':          True,
        'explanation': explanation,
        'best_move':   best_move,
        'source':      source,
    })


# ══════════════════════════════════════════════════════════════
# 推薦練習題 API
# ══════════════════════════════════════════════════════════════

# 技術標籤 → 對應的題目關鍵字（level / display_name / topic 中搜尋）
_SKILL_KEYWORDS = {
    '撲':     ['撲','扑','倒撲','倒扑'],
    '緊氣':   ['緊氣','紧气','气紧','攻殺','攻杀'],
    '劫':     ['劫'],
    '接不歸': ['接不归','接不歸'],
    '尖':     ['尖'],
    '夾':     ['夾','夹'],
    '挖':     ['挖'],
    '立':     ['一路立','於一路立','于一路立'],
    '眼位':   ['破眼','眼活','做活','活之部','死之部'],
    '對殺':   ['对杀','對殺','攻防'],
    '官子':   ['官子'],
    '死活':   ['死活'],
    '手筋':   ['手筋','手段'],
    '吃子':   ['吃子','渡過','渡过'],
}

def _skill_tags_of(q):
    """從題目的 level / display_name / topic 萃取技術標籤集合。"""
    text = ' '.join([
        q.get('level', ''),
        q.get('display_name', ''),
        q.get('topic', ''),
    ]).lower()
    tags = set()
    for tag, kws in _SKILL_KEYWORDS.items():
        if any(kw.lower() in text for kw in kws):
            tags.add(tag)
    return tags


@app.route('/api/recommend', methods=['POST'])
@login_required
def recommend_questions():
    """
    依目前題目的技術標籤推薦相關練習題。

    Request JSON:
        questionId : int   — 目前這題的 id
        tesuji     : str   — （可選）KataGo 偵測到的手筋術語，優先匹配

    Response JSON:
        ok          : bool
        recommend   : [ { id, display_name, topic, level, wrong_count } ]
    """
    d           = request.get_json() or {}
    current_qid = d.get('questionId')
    tesuji_hint = d.get('tesuji', '')   # 如 '撲', '尖', '接不歸'
    uid         = session['user_id']

    qs = _load_questions()
    if not qs or not current_qid:
        return jsonify({'ok': False, 'recommend': []})

    # ── 取得目前題目的標籤 ──────────────────────────────────────
    qs_map   = {q['id']: q for q in qs}
    cur_q    = qs_map.get(current_qid)
    if not cur_q:
        return jsonify({'ok': False, 'recommend': []})

    cur_tags = _skill_tags_of(cur_q)
    cur_topic = cur_q.get('topic', '')
    cur_level = cur_q.get('level', '')

    # 若 KataGo 有偵測到手筋，加入標籤（提高相關性）
    if tesuji_hint and tesuji_hint in _SKILL_KEYWORDS:
        cur_tags.add(tesuji_hint)

    # ── 取得使用者的 SRS 狀態 ────────────────────────────────────
    with get_db() as conn:
        srs_rows = conn.execute(
            'SELECT question_id, ease_factor, repetitions FROM srs_cards WHERE user_id=?',
            (uid,)
        ).fetchall()
        mistake_rows = conn.execute(
            'SELECT question_id, wrong_count FROM mistake_log WHERE user_id=?',
            (uid,)
        ).fetchall()

    srs_map     = {r['question_id']: r for r in srs_rows}
    mistake_map = {r['question_id']: r['wrong_count'] for r in mistake_rows}

    def is_mastered(qid):
        r = srs_map.get(qid)
        return r and r['ease_factor'] >= 2.5 and r['repetitions'] >= 3

    # ── 候選題目評分 ─────────────────────────────────────────────
    # 分數越高越優先推薦
    candidates = []
    for q in qs:
        qid = q['id']
        if qid == current_qid:              continue
        if not q.get('enabled', True):      continue
        if is_mastered(qid):                continue   # 已掌握，不推

        tags = _skill_tags_of(q)
        if not tags & cur_tags:             continue   # 無共同標籤

        score = len(tags & cur_tags) * 10  # 共同標籤數 × 10

        # 同章節加分
        if q.get('level') == cur_level and cur_level:
            score += 15
        # 同書但不同章節加分
        elif q.get('topic') == cur_topic:
            score += 5

        # 使用者曾答錯過此題加分（需要補強）
        wc = mistake_map.get(qid, 0)
        if wc > 0:
            score += min(wc * 3, 12)

        # SRS 間隔短（不熟）加分
        sr = srs_map.get(qid)
        if sr and sr['repetitions'] < 2:
            score += 5

        candidates.append((score, qid, q))

    # 按分數排序，取前 4 題（加一點隨機擾動避免每次完全相同）
    import random
    candidates.sort(key=lambda x: (-x[0], random.random()))
    top = candidates[:4]

    recommend = []
    for score, qid, q in top:
        recommend.append({
            'id':           qid,
            'display_name': q.get('display_name', ''),
            'topic':        q.get('topic', ''),
            'level':        q.get('level', ''),
            'wrong_count':  mistake_map.get(qid, 0),
            'tags':         sorted(_skill_tags_of(q)),
        })

    return jsonify({'ok': True, 'recommend': recommend})


# ══════════════════════════════════════════════════════════════
# 今日推薦訓練
# ══════════════════════════════════════════════════════════════

_ATTR_TO_DISCS = {
    'atk':  ['tesuji', 'chase'],
    'def':  ['life_death', 'shape'],
    'vis':  ['fuseki', 'whole_board'],
    'prec': ['endgame_counting'],
}

@app.route('/api/training/daily')
@login_required
def training_daily():
    """
    今日推薦 10 題，組成方式：
      1. SRS 到期複習（最多 5 題）
      2. 錯題補強（wrong_count >= 2，最多 3 題）
      3. 屬性驅動新題（依 ATK/DEF/VIS/PREC 比例從對應學科選）

    隊列在每天第一次呼叫時生成並存入 DB（daily_training_queue）；
    後續同天的呼叫直接從 DB 讀取，確保題目清單完全固定。
    completed 從「今日已答題 ∩ 隊列 ID」計算，永遠準確。
    """
    import random as _rng_mod

    uid   = session['user_id']
    today = datetime.date.today().isoformat()
    TOTAL = 10

    # ── 載入題庫 ────────────────────────────────────────────────
    all_qs  = _load_questions()
    enabled = {q['id']: q for q in all_qs if q.get('enabled', True)}

    with get_db() as conn:
        # ── 先查是否已有今天的持久化隊列 ──────────────────────────
        stored = conn.execute(
            'SELECT question_ids, sources FROM daily_training_queue '
            'WHERE user_id=? AND date=?',
            (uid, today)
        ).fetchone()

        if stored:
            # 直接從 DB 還原隊列（不重新生成）
            queue_ids   = json.loads(stored['question_ids'])
            queue_srcs  = json.loads(stored['sources'])
            selected    = [{'id': qid, 'source': src}
                           for qid, src in zip(queue_ids, queue_srcs)
                           if qid in enabled]
        else:
            # ── 第一次呼叫：生成隊列 ──────────────────────────────
            # SRS 到期（今天及之前）
            due_ids = [
                r['question_id']
                for r in conn.execute(
                    'SELECT question_id FROM srs_cards '
                    'WHERE user_id=? AND due_date<=? ORDER BY due_date',
                    (uid, today)
                ).fetchall()
                if r['question_id'] in enabled
            ]

            # 已掌握（ease>=2.5 且 repetitions>=3）
            mastered_ids = {
                r['question_id']
                for r in conn.execute(
                    'SELECT question_id FROM srs_cards '
                    'WHERE user_id=? AND ease_factor>=2.5 AND repetitions>=3',
                    (uid,)
                ).fetchall()
            }

            # 錯題（wrong_count >= 2，未掌握）
            mistake_ids = [
                r['question_id']
                for r in conn.execute(
                    'SELECT question_id FROM mistake_log '
                    'WHERE user_id=? AND wrong_count>=2 ORDER BY wrong_count DESC',
                    (uid,)
                ).fetchall()
                if r['question_id'] in enabled
                and r['question_id'] not in mastered_ids
            ]

            # 歷史上做過的題（排除出「新題」候選池）
            seen_ids = {
                r['question_id']
                for r in conn.execute(
                    'SELECT DISTINCT question_id FROM review_log WHERE user_id=?',
                    (uid,)
                ).fetchall()
            }

            # 玩家屬性 + 段位
            stats_row = conn.execute(
                'SELECT attr_atk, attr_def, attr_vis, attr_prec, go_rank '
                'FROM user_stats WHERE user_id=?',
                (uid,)
            ).fetchone()

            # ── 確定性亂數種子 ────────────────────────────────────
            rng = _rng_mod.Random(f"{uid}-{today}")

            selected     = []   # list of {'id': int, 'source': str}
            selected_set = set()

            def add(qid, source):
                if qid not in selected_set and qid in enabled:
                    selected.append({'id': qid, 'source': source})
                    selected_set.add(qid)
                    return True
                return False

            # Step 1：SRS 到期複習（最多 5 題）
            due_shuffled = list(due_ids)
            rng.shuffle(due_shuffled)
            for qid in due_shuffled[:5]:
                add(qid, 'srs')

            # Step 2：錯題補強（最多 3 題）
            for qid in mistake_ids[:3]:
                add(qid, 'mistake')

            # Step 3：屬性驅動新題，補足至 TOTAL 題
            need = TOTAL - len(selected)
            if need > 0:
                atk  = (stats_row['attr_atk']  or 0) if stats_row else 0
                def_ = (stats_row['attr_def']  or 0) if stats_row else 0
                vis  = (stats_row['attr_vis']  or 0) if stats_row else 0
                prec = (stats_row['attr_prec'] or 0) if stats_row else 0

                attr_w  = {'atk': atk+1, 'def': def_+1, 'vis': vis+1, 'prec': prec+1}
                total_w = sum(attr_w.values())

                slots     = {}
                remaining = need
                for i, (attr, w) in enumerate(
                    sorted(attr_w.items(), key=lambda x: -x[1])
                ):
                    if i == len(attr_w) - 1:
                        slots[attr] = remaining
                    else:
                        n = max(1, round(w / total_w * need))
                        n = min(n, remaining)
                        slots[attr] = n
                        remaining -= n
                        if remaining <= 0:
                            break

                go_rank  = (stats_row['go_rank'] or '30k') if stats_row else '30k'
                rank_idx = DIFFICULTY_ORDER.index(go_rank) if go_rank in DIFFICULTY_ORDER else 0

                def _rank_dist(q) -> int:
                    r = q.get('rank') or q.get('difficulty') or ''
                    try:
                        return abs(DIFFICULTY_ORDER.index(r) - rank_idx)
                    except ValueError:
                        return 99

                new_pool = {attr: [] for attr in _ATTR_TO_DISCS}
                for q in enabled.values():
                    if q['id'] in selected_set or q['id'] in seen_ids:
                        continue
                    disc = q.get('discipline', 'whole_board')
                    for attr, discs in _ATTR_TO_DISCS.items():
                        if disc in discs:
                            new_pool[attr].append(q)
                            break

                for attr in new_pool:
                    pool = new_pool[attr]
                    pool.sort(key=_rank_dist)
                    close_pool = pool[:60]
                    rng.shuffle(close_pool)
                    new_pool[attr] = [q['id'] for q in close_pool]

                for attr, n in slots.items():
                    for qid in new_pool.get(attr, [])[:n]:
                        add(qid, f'new_{attr}')

            # Fallback：從未做過的題補（偏好近段位）
            if len(selected) < TOTAL:
                fallback = [
                    q for q in enabled.values()
                    if q['id'] not in selected_set and q['id'] not in seen_ids
                ]
                fallback.sort(key=_rank_dist)
                close = fallback[:60]
                rng.shuffle(close)
                for q in close[:TOTAL - len(selected)]:
                    add(q['id'], 'new_general')

            # Fallback 2：全都做過了，從未掌握的舊題補
            if len(selected) < TOTAL:
                fallback2 = [
                    qid for qid in enabled
                    if qid not in selected_set and qid not in mastered_ids
                ]
                rng.shuffle(fallback2)
                for qid in fallback2[:TOTAL - len(selected)]:
                    add(qid, 'review')

            # ── 將隊列存入 DB（只存一次）────────────────────────────
            conn.execute(
                'INSERT OR IGNORE INTO daily_training_queue '
                '(user_id, date, question_ids, sources) VALUES (?,?,?,?)',
                (uid, today,
                 json.dumps([s['id']     for s in selected]),
                 json.dumps([s['source'] for s in selected]))
            )

        # ── 今日已作答（從 DB 查，永遠最新）───────────────────────
        done_today = {
            r['question_id']
            for r in conn.execute(
                'SELECT DISTINCT question_id FROM review_log '
                'WHERE user_id=? AND DATE(reviewed_at)=?',
                (uid, today)
            ).fetchall()
        }

    # ── 組裝回應 ────────────────────────────────────────────────
    queue_set       = {item['id'] for item in selected}
    completed_count = len(done_today & queue_set)

    questions_out = []
    for item in selected:
        qid = item['id']
        q   = enabled[qid]
        questions_out.append({
            'id':           qid,
            'source':       item['source'],
            'completed':    qid in done_today,
            'discipline':   q.get('discipline', ''),
            'rank':         q.get('rank', ''),
            'display_name': q.get('display_name') or q.get('topic', ''),
        })

    return jsonify({
        'total':     TOTAL,
        'completed': completed_count,
        'questions': questions_out,
        'date':      today,
    })


@app.route('/api/training/contaminated')
@login_required
def training_contaminated():
    """
    回傳「污染節點」數量：近 30 天內答錯過、且尚未掌握的題目。
    用於首頁虛空迴廊 widget 的待淨化計數。
    """
    uid      = session['user_id']
    since    = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
    all_qs   = _load_questions()
    enabled  = {q['id'] for q in all_qs if q.get('enabled', True)}

    with get_db() as conn:
        # 近 30 天答錯過的題目
        wrong_ids = {
            r['question_id']
            for r in conn.execute(
                'SELECT DISTINCT question_id FROM review_log '
                'WHERE user_id=? AND grade<3 AND DATE(reviewed_at)>=?',
                (uid, since)
            ).fetchall()
            if r['question_id'] in enabled
        }

        # 已掌握的題目（排除）
        mastered_ids = {
            r['question_id']
            for r in conn.execute(
                'SELECT question_id FROM srs_cards '
                'WHERE user_id=? AND ease_factor>=2.5 AND repetitions>=3',
                (uid,)
            ).fetchall()
        }

    contaminated = wrong_ids - mastered_ids
    return jsonify({'total': len(contaminated)})


# ══════════════════════════════════════════════════════════════
# 訂閱 API
# ══════════════════════════════════════════════════════════════


@app.route('/api/taxonomy')
@login_required
def taxonomy_meta():
    return jsonify(get_taxonomy())

@app.route('/api/monster-taxonomy')
@login_required
def monster_taxonomy_meta():
    return jsonify(get_monster_taxonomy())

@app.route('/api/subscription/status')
@login_required
def subscription_status():
    uid     = session['user_id']
    premium = is_premium(uid)
    today_cnt = 0 if premium else get_today_free_count(uid)
    qs        = _load_questions()
    total_count = len(qs)
    return jsonify({
        'plan':          session.get('plan', 'free'),
        'is_premium':    premium,
        'today_count':   today_cnt,
        'daily_limit':   FREE_DAILY_LIMIT,
        'remaining':     max(0, FREE_DAILY_LIMIT - today_cnt) if not premium else None,
        'total_q_count': total_count,
    })

# ══════════════════════════════════════════════════════════════
# 主線冒險 / 領主封印
# ══════════════════════════════════════════════════════════════

BOSS_UNLOCK_PCT = 30
BOSS_EXAM_SIZE = 20
BOSS_PASS_SCORE = 16
BOSS_FAIL_COOLDOWN = 30

ADVENTURE_ZONES = [
    {'key':'k26_30', 'label':'26–30級', 'name':'圍棋新手村',   'icon':'🟢', 'min':0,  'max':4,   'stage':'LV1'},
    {'key':'k21_25', 'label':'21–25級', 'name':'史萊姆平原',   'icon':'🟦', 'min':5,  'max':9,   'stage':'LV2'},
    {'key':'k16_20', 'label':'16–20級', 'name':'哥布林洞穴',   'icon':'🦇', 'min':10, 'max':14,  'stage':'LV3'},
    {'key':'k11_15', 'label':'11–15級', 'name':'迷霧森林',     'icon':'🌲', 'min':15, 'max':19,  'stage':'LV4'},
    {'key':'k6_10',  'label':'6–10級',  'name':'獸人部落',     'icon':'🪓', 'min':20, 'max':24,  'stage':'LV5'},
    {'key':'k1_5',   'label':'1–5級',   'name':'龍之谷',       'icon':'🐉', 'min':25, 'max':29,  'stage':'LV6'},
    {'key':'d1_2',   'label':'1–2段',   'name':'賢者之塔',     'icon':'🔮', 'min':30, 'max':31,  'stage':'LV7'},
    {'key':'d3_4',   'label':'3–4段',   'name':'魔王城前線',   'icon':'👺', 'min':32, 'max':33,  'stage':'LV8'},
    {'key':'d5_6',   'label':'5–6段',   'name':'諸神黃昏',     'icon':'🗿', 'min':34, 'max':35,  'stage':'LV9'},
    {'key':'d7_plus','label':'7段＋',   'name':'上古終焉神殿', 'icon':'✨', 'min':36, 'max':998, 'stage':'LV10'},
]

def _adventure_start_zone_for_elo(elo):
    """Return the first meaningful adventure zone for a placement Elo."""
    try:
        elo = float(elo)
    except Exception:
        elo = 1100.0
    if elo >= 2450:
        return 'd7_plus'
    if elo >= 2200:
        return 'd5_6'
    if elo >= 2000:
        return 'd3_4'
    if elo >= 1800:
        return 'd1_2'
    if elo >= 1570:
        return 'k1_5'
    if elo >= 1400:
        return 'k6_10'
    if elo >= 1300:
        return 'k11_15'
    if elo >= 1200:
        return 'k16_20'
    if elo >= 1150:
        return 'k21_25'
    return 'k26_30'

def _adventure_zone_index(zone_key):
    for i, z in enumerate(ADVENTURE_ZONES):
        if z['key'] == zone_key:
            return i
    return 0

def _unlock_adventure_through(uid, start_zone_key, source='placement'):
    """Unlock travel points through start_zone_key without marking zones cleared."""
    idx = _adventure_zone_index(start_zone_key)
    now = datetime.datetime.now().isoformat(timespec='seconds')
    with get_db() as conn:
        for z in ADVENTURE_ZONES[:idx + 1]:
            conn.execute('''
                INSERT INTO adventure_zone_unlocks
                    (user_id, zone_key, source, start_zone_key, unlocked_at)
                VALUES (?,?,?,?,?)
                ON CONFLICT(user_id, zone_key) DO UPDATE SET
                    source=excluded.source,
                    start_zone_key=excluded.start_zone_key,
                    unlocked_at=COALESCE(adventure_zone_unlocks.unlocked_at, excluded.unlocked_at)
            ''', (uid, z['key'], source, start_zone_key, now))
        conn.commit()
    return start_zone_key

def _apply_placement_adventure_unlock(uid, elo, source='placement'):
    start_zone_key = _adventure_start_zone_for_elo(elo)
    _unlock_adventure_through(uid, start_zone_key, source)
    return start_zone_key

def _question_rank_index(q):
    raw = str(q.get('rank') or q.get('difficulty') or '').strip().lower()
    if raw in DIFFICULTY_ORDER:
        return DIFFICULTY_ORDER.index(raw)
    stage = str(q.get('stage') or '')
    if stage.upper().startswith('LV'):
        try:
            return max(0, (int(stage[2:]) - 1) * 4)
        except ValueError:
            pass
    return 0

def _zone_by_key(zone_key):
    return next((z for z in ADVENTURE_ZONES if z['key'] == zone_key), None)

def _questions_for_adventure_zone(qs, zone, premium=True):
    out = []
    for q in qs:
        if not q.get('enabled', True):
            continue
        if not premium and not question_is_free(q):
            continue
        idx = _question_rank_index(q)
        if zone['min'] <= idx <= zone['max']:
            out.append(q)
    return out

def _adventure_state(uid):
    qs = [q for q in _load_questions() if q.get('enabled', True)]
    premium = is_premium(uid)
    now = datetime.datetime.now().isoformat(timespec='seconds')
    with get_db() as conn:
        cards = conn.execute(
            'SELECT question_id,last_grade FROM srs_cards WHERE user_id=?',
            (uid,)
        ).fetchall()
        rows = conn.execute(
            'SELECT * FROM adventure_boss_progress WHERE user_id=?',
            (uid,)
        ).fetchall()
        unlock_rows = conn.execute(
            'SELECT * FROM adventure_zone_unlocks WHERE user_id=?',
            (uid,)
        ).fetchall()
        progress = {r['zone_key']: dict(r) for r in rows}
        placement_unlocks = {r['zone_key']: dict(r) for r in unlock_rows}

    seen_ids = {r['question_id'] for r in cards}
    defeated_ids = {r['question_id'] for r in cards if (r['last_grade'] or 0) >= 3}
    zones = []
    previous_cleared = True

    for z in ADVENTURE_ZONES:
        zone_qs = _questions_for_adventure_zone(qs, z, premium)
        total = len(zone_qs)
        seen = len([q for q in zone_qs if q['id'] in seen_ids])
        defeated = len([q for q in zone_qs if q['id'] in defeated_ids])
        pct = round(seen / total * 100) if total else 0
        defeat_pct = round(defeated / total * 100) if total else 0
        row = progress.get(z['key']) or {}
        cleared = bool(row.get('cleared'))
        placement_unlocked = z['key'] in placement_unlocks
        cooldown_until = int(row.get('cooldown_until_seen') or 0)
        cooldown_left = max(0, cooldown_until - seen)
        unlocked = previous_cleared or cleared or placement_unlocked
        boss_ready = unlocked and pct >= BOSS_UNLOCK_PCT and not cleared and cooldown_left == 0

        stars = 0
        if cleared:
            stars = max(stars, 1)
        if pct >= 60:
            stars = max(stars, 2)
        if total and defeated >= total:
            stars = 3
        stars = max(stars, int(row.get('stars') or 0))

        zones.append({
            **z,
            'total': total,
            'seen': seen,
            'defeated': defeated,
            'pct': pct,
            'defeat_pct': defeat_pct,
            'unlock_pct': BOSS_UNLOCK_PCT,
            'boss_exam_size': BOSS_EXAM_SIZE,
            'boss_pass_score': BOSS_PASS_SCORE,
            'cooldown_required': BOSS_FAIL_COOLDOWN,
            'cooldown_left': cooldown_left,
            'boss_ready': boss_ready,
            'cleared': cleared,
            'unlocked': unlocked,
            'placement_unlocked': placement_unlocked,
            'unlock_source': placement_unlocks.get(z['key'], {}).get('source'),
            'placement_start_zone': placement_unlocks.get(z['key'], {}).get('start_zone_key'),
            'stars': stars,
            'attempts': int(row.get('attempts') or 0),
            'best_score': int(row.get('best_score') or 0),
            'last_attempt_at': row.get('last_attempt_at'),
            'cleared_at': row.get('cleared_at'),
            'updated_at': row.get('updated_at') or now,
        })
        previous_cleared = cleared

    return zones

@app.route('/api/adventure/progress')
@login_required
def adventure_progress():
    return jsonify({
        'unlock_pct': BOSS_UNLOCK_PCT,
        'boss_exam_size': BOSS_EXAM_SIZE,
        'boss_pass_score': BOSS_PASS_SCORE,
        'cooldown_required': BOSS_FAIL_COOLDOWN,
        'zones': _adventure_state(session['user_id']),
    })

@app.route('/api/adventure/boss/start', methods=['POST'])
@login_required
def adventure_boss_start():
    uid = session['user_id']
    data = request.get_json() or {}
    zone_key = (data.get('zone_key') or '').strip()
    zone = _zone_by_key(zone_key)
    if not zone:
        return jsonify({'ok': False, 'error': 'zone_not_found'}), 404

    zones = _adventure_state(uid)
    state = next((z for z in zones if z['key'] == zone_key), None)
    if not state or not state.get('unlocked'):
        return jsonify({'ok': False, 'error': 'zone_locked', 'message': '此區域尚未解鎖'}), 403
    if state.get('cleared'):
        return jsonify({'ok': False, 'error': 'already_cleared', 'message': '此領主已擊破'}), 400
    if state.get('cooldown_left', 0) > 0:
        return jsonify({'ok': False, 'error': 'cooldown', 'cooldown_left': state['cooldown_left']}), 400
    if state.get('pct', 0) < BOSS_UNLOCK_PCT:
        return jsonify({'ok': False, 'error': 'progress_not_enough', 'progress': state.get('pct', 0)}), 400

    premium = is_premium(uid)
    qs = _questions_for_adventure_zone(_load_questions(), zone, premium)
    if len(qs) < 1:
        return jsonify({'ok': False, 'error': 'no_questions'}), 400
    rng = random.Random(f"{uid}-{zone_key}-{datetime.datetime.now().isoformat()}")
    pool = list(qs)
    rng.shuffle(pool)
    selected = pool[:min(BOSS_EXAM_SIZE, len(pool))]
    qids = [q['id'] for q in selected]
    session['adventure_boss_exam'] = {
        'zone_key': zone_key,
        'question_ids': qids,
        'started_at': datetime.datetime.now().isoformat(timespec='seconds'),
    }
    return jsonify({
        'ok': True,
        'zone': state,
        'question_ids': qids,
        'total': len(qids),
        'pass_score': min(BOSS_PASS_SCORE, len(qids)),
    })

@app.route('/api/adventure/boss/finish', methods=['POST'])
@login_required
def adventure_boss_finish():
    uid = session['user_id']
    data = request.get_json() or {}
    exam = session.get('adventure_boss_exam') or {}
    zone_key = exam.get('zone_key')
    if not zone_key:
        return jsonify({'ok': False, 'error': 'no_active_exam'}), 400
    correct = max(0, int(data.get('correct') or 0))
    total = max(1, int(data.get('total') or len(exam.get('question_ids') or []) or BOSS_EXAM_SIZE))
    pass_score = min(BOSS_PASS_SCORE, total)
    passed = correct >= pass_score
    now = datetime.datetime.now().isoformat(timespec='seconds')
    zones = _adventure_state(uid)
    state = next((z for z in zones if z['key'] == zone_key), None) or {}
    seen = int(state.get('seen') or 0)
    cooldown_until = 0 if passed else seen + BOSS_FAIL_COOLDOWN

    with get_db() as conn:
        existing = conn.execute(
            'SELECT * FROM adventure_boss_progress WHERE user_id=? AND zone_key=?',
            (uid, zone_key)
        ).fetchone()
        attempts = (existing['attempts'] if existing else 0) + 1
        best_score = max(correct, existing['best_score'] if existing else 0)
        cleared = 1 if passed else (existing['cleared'] if existing else 0)
        stars = max(1 if passed else 0, existing['stars'] if existing else 0)
        cleared_at = now if passed and not (existing and existing['cleared']) else (existing['cleared_at'] if existing else None)
        conn.execute('''
            INSERT INTO adventure_boss_progress
                (user_id,zone_key,cleared,stars,attempts,best_score,cooldown_until_seen,last_attempt_at,cleared_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(user_id,zone_key) DO UPDATE SET
                cleared=excluded.cleared,
                stars=MAX(adventure_boss_progress.stars, excluded.stars),
                attempts=excluded.attempts,
                best_score=MAX(adventure_boss_progress.best_score, excluded.best_score),
                cooldown_until_seen=excluded.cooldown_until_seen,
                last_attempt_at=excluded.last_attempt_at,
                cleared_at=COALESCE(adventure_boss_progress.cleared_at, excluded.cleared_at),
                updated_at=excluded.updated_at
        ''', (uid, zone_key, cleared, stars, attempts, best_score, cooldown_until, now, cleared_at, now))

    session.pop('adventure_boss_exam', None)
    return jsonify({
        'ok': True,
        'passed': passed,
        'correct': correct,
        'total': total,
        'pass_score': pass_score,
        'cooldown_left': 0 if passed else BOSS_FAIL_COOLDOWN,
        'zones': _adventure_state(uid),
    })

# ══════════════════════════════════════════════════════════════
# 題庫 API（index.html / mistakes.html 左側列表用）
# ══════════════════════════════════════════════════════════════

@app.route('/api/questions')
@login_required
def get_questions():
    """
    回傳所有啟用題目的摘要列表（不含 SGF 內容，以減少傳輸量）。
    每題附帶 locked 欄位，供前端顯示鎖頭圖示。
    """
    qs      = _load_questions()
    premium = is_premium()
    discipline_filter = (request.args.get('discipline') or '').strip()
    _raw_stage        = (request.args.get('stage') or '').strip()
    # 相容 stage=1 與 stage=LV1 兩種格式
    stage_filter      = ('LV' + _raw_stage) if _raw_stage.isdigit() else _raw_stage
    grimoire_filter   = request.args.get('grimoire_id', type=int)
    result  = []
    for q in qs:
        if not q.get('enabled', True):
            continue
        if discipline_filter and (q.get('discipline') or 'whole_board') != discipline_filter:
            continue
        if stage_filter and (q.get('stage') or '') != stage_filter:
            continue
        if grimoire_filter is not None and q.get('grimoire_id') != grimoire_filter:
            continue
        locked = (not premium) and (not question_is_free(q))
        result.append({
            'id':                q['id'],
            'topic':             q.get('topic', ''),
            'topic_en':          q.get('topic_en', ''),
            'level':             q.get('level', ''),
            'level_en':          q.get('level_en', ''),
            'source':            q.get('source', ''),
            'display_name':      q.get('display_name', ''),
            'difficulty':        q.get('difficulty', ''),
            'sort_order':        q.get('sort_order'),
            'locked':            locked,
            'grimoire_id':       q.get('grimoire_id'),
            'discipline':        q.get('discipline', ''),
            'discipline_label':  q.get('discipline_label', ''),
            'discipline_label_en': q.get('discipline_label_en', ''),
            'discipline_order':  q.get('discipline_order', 999),
            'rank':              q.get('rank') or q.get('difficulty', ''),
            'stage':             q.get('stage', ''),
            'stage_label':       q.get('stage_label', ''),
            'stage_label_en':    q.get('stage_label_en', ''),
            'difficulty_score':  q.get('difficulty_score'),
            'tags':              q.get('tags', []),
            'map_id':            q.get('map_id', ''),
            'map_name':          q.get('map_name', ''),
            'map_chapter':       q.get('map_chapter', ''),
            'monster_family':    q.get('monster_family', ''),
            'monster_family_label': q.get('monster_family_label', ''),
            'monster_attribute': q.get('monster_attribute', ''),
            'weakness_topic':    q.get('weakness_topic', ''),
            'battle_monster_type': q.get('battle_monster_type', ''),
            'monster_type':      q.get('battle_monster_type', ''),
            'monster_avatar':    _question_monster_avatar(q),
            'encounter_type':    q.get('encounter_type', 'normal'),
            'encounter_label':   q.get('encounter_label', '普通題'),
            'boss_level':        q.get('boss_level'),
            'boss_title':        q.get('boss_title', ''),
            'monster_name':      q.get('monster_name', ''),
            'grimoire_difficulty': q.get('grimoire_difficulty'),
            'rating':              q.get('rating'),
            'katago_best_move':    q.get('katago_best_move', ''),
            'score_gap':           q.get('score_gap'),
        })
    resp = jsonify(result)
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return resp


@app.route('/api/question/<int:qid>')
@login_required
def get_question(qid):
    """
    回傳單一題目的完整資料（含 SGF content）。
    付費鎖定的題目仍回傳 SGF，讓前端可顯示棋盤預覽，
    但前端會阻止實際落子（locked 旗標）。
    """
    qs  = _load_questions()
    q   = next((x for x in qs if x['id'] == qid), None)
    if q is None:
        return jsonify({'error': '找不到題目'}), 404
    premium = is_premium()
    locked  = (not premium) and (not question_is_free(q))
    return jsonify({
        'id':           q['id'],
        'topic':        q.get('topic', ''),
        'topic_en':     q.get('topic_en', ''),
        'level':        q.get('level', ''),
        'level_en':     q.get('level_en', ''),
        'display_name': q.get('display_name', ''),
        'difficulty':   q.get('difficulty', ''),
        'rank':         q.get('rank') or q.get('difficulty', ''),
        'stage':        q.get('stage', ''),
        'stage_label':  q.get('stage_label', ''),
        'stage_label_en': q.get('stage_label_en', ''),
        'discipline':   q.get('discipline', ''),
        'discipline_label': q.get('discipline_label', ''),
        'discipline_label_en': q.get('discipline_label_en', ''),
        'difficulty_score': q.get('difficulty_score'),
        'tags':         q.get('tags', []),
        'map_id':       q.get('map_id', ''),
        'map_name':     q.get('map_name', ''),
        'map_chapter':  q.get('map_chapter', ''),
        'monster_family': q.get('monster_family', ''),
        'monster_family_label': q.get('monster_family_label', ''),
        'monster_attribute': q.get('monster_attribute', ''),
        'weakness_topic': q.get('weakness_topic', ''),
        'battle_monster_type': q.get('battle_monster_type', ''),
        'monster_type': q.get('battle_monster_type', ''),
        'monster_avatar': _question_monster_avatar(q),
        'encounter_type': q.get('encounter_type', 'normal'),
        'encounter_label': q.get('encounter_label', '普通題'),
        'boss_level':   q.get('boss_level'),
        'boss_title':   q.get('boss_title', ''),
        'monster_name': q.get('monster_name', ''),
        'sort_order':   q.get('sort_order'),
        'content':          q.get('content', ''),
        'comment':          q.get('comment', ''),
        'rating':           q.get('rating'),
        'katago_best_move': q.get('katago_best_move', ''),
        'score_gap':        q.get('score_gap'),
        'locked':           locked,
    })


@app.route('/api/save-question', methods=['POST'])
@admin_required
def save_question():
    """快速修正題目 SGF 內容（管理員專用）。同時清除 rating test pool 快取。"""
    global _RT_POOL_READY
    data = request.get_json() or {}
    qid  = data.get('id')
    new_content = (data.get('content') or '').strip()
    if not qid or not new_content:
        return jsonify({'ok': False, 'error': '缺少 id 或 content'}), 400
    qs = _load_questions()
    q  = next((x for x in qs if x['id'] == qid), None)
    if not q:
        return jsonify({'ok': False, 'error': '找不到題目'}), 404
    q['content'] = new_content
    _save_questions(qs)
    # 清除 rating test pool 快取，讓下次測驗用新內容
    _RT_POOL_READY = False
    return jsonify({'ok': True})


@app.route('/api/set-explanation', methods=['POST'])
@admin_required
def set_explanation():
    """新增或修改題目解說文字（comment 欄位）。"""
    data = request.get_json() or {}
    qid  = data.get('id')
    text = (data.get('text') or '').strip()
    if not qid:
        return jsonify({'ok': False, 'error': '缺少 id'}), 400
    qs = _load_questions()
    q  = next((x for x in qs if x['id'] == int(qid)), None)
    if q is None:
        return jsonify({'ok': False, 'error': '找不到題目'}), 404
    q['comment'] = text
    _save_questions(qs)
    return jsonify({'ok': True})


# ══════════════════════════════════════════════════════════════
# 題庫管理 API（需管理員）
# ══════════════════════════════════════════════════════════════

def _save_questions(qs):
    """安全寫入：先寫暫存檔，完成後再 atomic 替換，避免寫到一半時原檔損壞。"""
    import tempfile, shutil
    data_dir = os.path.dirname(os.path.abspath(DATA_FILE)) or '.'
    # 1. 寫入同目錄的暫存檔
    tmp_fd, tmp_path = tempfile.mkstemp(dir=data_dir, suffix='.tmp', prefix='questions_')
    try:
        with os.fdopen(tmp_fd, 'w', encoding='utf-8') as f:
            json.dump(qs, f, ensure_ascii=False, indent=2)
        # 2. 備份舊檔（覆蓋前一次的 .bak）
        if os.path.exists(DATA_FILE):
            shutil.copy2(DATA_FILE, DATA_FILE + '.bak')
        # 3. Atomic 替換（同磁碟上的 rename 是原子操作）
        os.replace(tmp_path, DATA_FILE)
    except Exception:
        # 寫入失敗時刪掉暫存檔，不影響原檔
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    _invalidate_questions_cache()   # 檔案已更新，清除記憶體快取

def _chapter_prefix_of(display_name):
    """與前端 chapterLabel() 邏輯相同：從 display_name 抽出章節前綴。
    成功時回傳前綴字串；無法辨識時回傳 None。"""
    import re
    if not display_name:
        return None
    p = re.sub(r'第\d+[題局].*', '', display_name).strip()
    # 若有成功去除後綴（p 比原字串短且不為空）才算有效前綴
    if p and p != display_name:
        return p
    return None

def _apply_chapter_to_display(display_name, new_chapter):
    """將 display_name 的章節前綴替換為 new_chapter，保留後綴（第N題/局…）。
    若無法辨識前綴則不更動，直接回傳原值。"""
    old_prefix = _chapter_prefix_of(display_name)
    if old_prefix is None:
        return display_name          # 無法辨識，不動
    if old_prefix == new_chapter:
        return display_name          # 前綴相同，不需更改
    # 保留從「第N題/局」開始的後綴
    suffix = display_name[len(old_prefix):]
    return new_chapter + suffix

# ── /api/manage/questions：管理用完整列表（含停用題目）──
@app.route('/api/manage/questions')
@admin_required
def manage_list_questions():
    qs = _load_questions()
    result = []
    for q in qs:
        result.append({
            'id':           q['id'],
            'topic':        q.get('topic', ''),
            'level':        q.get('level', ''),
            'display_name': q.get('display_name', ''),
            'difficulty':   q.get('difficulty', ''),
            'sort_order':   q.get('sort_order'),
            'enabled':      q.get('enabled', True),
            'has_explanation': bool(q.get('comment')),
            'discipline':   q.get('discipline', ''),
            'stage':        q.get('stage', ''),
            'monster_family': q.get('monster_family', ''),
            'monster_family_label': q.get('monster_family_label', ''),
            'battle_monster_type': q.get('battle_monster_type', ''),
            'monster_type': q.get('battle_monster_type', ''),
            'monster_name': q.get('monster_name', ''),
            'monster_avatar': _question_monster_avatar(q),
        })
    return jsonify(result)

@app.route('/api/toggle-question', methods=['POST'])
@admin_required
def toggle_question():
    data = request.get_json()
    qid  = int(data.get('id', 0))
    qs   = _load_questions()
    q    = next((x for x in qs if x['id'] == qid), None)
    if not q:
        return jsonify({'ok': False, 'error': '找不到題目'}), 404
    q['enabled'] = not q.get('enabled', True)
    _save_questions(qs)
    return jsonify({'ok': True, 'enabled': q['enabled']})

@app.route('/api/set-difficulty', methods=['POST'])
@admin_required
def set_difficulty():
    data  = request.get_json()
    qid   = int(data.get('id', 0))
    diff  = data.get('difficulty', '')
    qs    = _load_questions()
    q     = next((x for x in qs if x['id'] == qid), None)
    if not q:
        return jsonify({'ok': False, 'error': '找不到題目'}), 404
    q['difficulty'] = diff
    _save_questions(qs)
    return jsonify({'ok': True})

_DISC_LABELS = {
    'life_death':       ('死活',    'Life & Death'),
    'tesuji':           ('手筋',    'Tesuji'),
    'chase':            ('追逃',    'Chase'),
    'shape':            ('棋形',    'Shape'),
    'fuseki':           ('布局',    'Fuseki'),
    'whole_board':      ('全局',    'Whole Board'),
    'endgame_counting': ('官子',    'Endgame'),
    # 舊 code 保留向下相容
    'endgame':          ('官子',    'Endgame'),
    'opening_direction':('布局',    'Opening'),
    'capture_escape':   ('追逃',    'Capture/Escape'),
    'connection_cut':   ('棋形',    'Shape'),
    'shape_weakness':   ('棋形',    'Shape'),
}

@app.route('/api/set-discipline', methods=['POST'])
@admin_required
def set_discipline():
    data = request.get_json()
    qid  = int(data.get('id', 0))
    disc = data.get('discipline', '').strip()
    qs   = _load_questions()
    q    = next((x for x in qs if x['id'] == qid), None)
    if not q:
        return jsonify({'ok': False, 'error': '找不到題目'}), 404
    label_zh, label_en = _DISC_LABELS.get(disc, (disc, disc))
    q['discipline']          = disc
    q['discipline_label']    = label_zh
    q['discipline_label_en'] = label_en
    _save_questions(qs)
    return jsonify({'ok': True})

@app.route('/api/batch-set-discipline', methods=['POST'])
@admin_required
def batch_set_discipline():
    data    = request.get_json()
    disc    = data.get('discipline', '').strip()
    ids     = data.get('ids')           # 明確 ID 列表（可選）
    book    = data.get('book', '').strip()
    chapter = data.get('chapter', '').strip()   # 空 = 整本書
    if not disc:
        return jsonify({'ok': False, 'error': '缺少 discipline'}), 400
    label_zh, label_en = _DISC_LABELS.get(disc, (disc, disc))
    id_set = set(int(x) for x in ids) if ids is not None else None
    qs = _load_questions()
    updated = 0
    for q in qs:
        if id_set is not None:
            if q['id'] not in id_set:
                continue
        else:
            if book and q.get('topic') != book:
                continue
            if chapter and q.get('level') != chapter:
                continue
        q['discipline']          = disc
        q['discipline_label']    = label_zh
        q['discipline_label_en'] = label_en
        updated += 1
    if not updated:
        return jsonify({'ok': False, 'error': '沒有符合條件的題目'}), 404
    _save_questions(qs)
    return jsonify({'ok': True, 'updated': updated})

@app.route('/api/rename-question', methods=['POST'])
@admin_required
def rename_question():
    data  = request.get_json()
    qid   = int(data.get('id', 0))
    name  = data.get('name', '').strip()
    if not name:
        return jsonify({'ok': False, 'error': '名稱不可空白'}), 400
    qs = _load_questions()
    q  = next((x for x in qs if x['id'] == qid), None)
    if not q:
        return jsonify({'ok': False, 'error': '找不到題目'}), 404
    q['display_name'] = name
    _save_questions(qs)
    return jsonify({'ok': True})

_DIFF_ORDER = [
    '30k','29k','28k','27k','26k','25k','24k','23k','22k','21k',
    '20k','19k','18k','17k','16k','15k','14k','13k','12k','11k',
    '10k','9k','8k','7k','6k','5k','4k','3k','2k','1k',
    '1d','2d','3d','4d','5d','6d','7d','8d','9d'
]

def _book_diff_rank(name):
    """與前端 bookDiffRank() 邏輯一致的 Python 版本。"""
    import re
    def try_key(k):
        try: return _DIFF_ORDER.index(k)
        except: return None
    m = re.search(r'從(\d+)(DK|K|D)到(\d+)(K|D)', name, re.IGNORECASE)
    if m:
        t1 = m.group(2).upper().replace('DK','D')
        s1 = f'{m.group(1)}{"k" if t1=="K" else "d"}'
        i1 = try_key(s1)
        if i1 is not None: return i1
        t2 = m.group(4).upper()
        s2 = f'{m.group(3)}{"k" if t2=="K" else "d"}'
        i2 = try_key(s2)
        if i2 is not None: return i2
    m2 = re.search(r'(\d+)[–\-](\d+)\s*級', name)
    if m2:
        lo, hi = int(m2.group(1)), int(m2.group(2))
        max_kyu = max(lo, hi)
        if max_kyu > 20: return -(max_kyu - 20)
        r = try_key(f'{min(lo,hi)}k')
        return r if r is not None else 0
    for kw, rank in [('入門',0),('初級',5),('中級',10),('高級',15)]:
        if kw in name: return rank
    for kw, rank in [('前田陳爾',20),('鬼手',22),('吳清源手筋辭典',21),
                     ('圍棋妙手百例',19),('圍棋實戰官子',20),('圍棋實用死活',20),
                     ('官子譜',21),('棋經眾妙',19),('珍瓏',24),('發揚論',24),
                     ('褔井正義',20),('角部侵分',19),('關山利夫',21),('韓國經典死活',23)]:
        if kw in name: return rank
    if '瀨越' in name and '妙手筋' in name:   return 20
    if '瀨越' in name and '死活辭典' in name:  return 22
    return 999

@app.route('/api/book-bands')
@login_required
def get_book_bands():
    """回傳所有書本的難度等級覆寫，供前端 effectiveRank() 使用。"""
    with get_db() as conn:
        rows = conn.execute('SELECT name, band_rank FROM book_bands').fetchall()
    return jsonify({r[0]: r[1] for r in rows})

# ── 線上對弈棋力（go_rank）相關路由 ──────────────────────────────

def check_go_rank_change(conn, uid):
    """
    檢查最近 15 局勝率，決定升降段位。
    回傳 ('promote'|'demote'|None, new_rank)
    """
    rows = conn.execute(
        'SELECT result FROM game_results WHERE user_id=? ORDER BY played_at DESC LIMIT 15',
        (uid,)
    ).fetchall()
    if len(rows) < 3:
        return None, None
    total    = len(rows)
    wins     = sum(r['result'] for r in rows)
    win_rate = wins / total

    row = conn.execute('SELECT go_rank FROM user_stats WHERE user_id=?', (uid,)).fetchone()
    cur = (row['go_rank'] or '30k') if row else '30k'
    idx = DIFFICULTY_ORDER.index(cur) if cur in DIFFICULTY_ORDER else 0

    if win_rate > 0.70 and idx < len(DIFFICULTY_ORDER) - 1:
        new_rank = DIFFICULTY_ORDER[idx + 1]
        conn.execute('UPDATE user_stats SET go_rank=? WHERE user_id=?', (new_rank, uid))
        return 'promote', new_rank
    elif win_rate < 0.30 and idx > 0:
        new_rank = DIFFICULTY_ORDER[idx - 1]
        conn.execute('UPDATE user_stats SET go_rank=? WHERE user_id=?', (new_rank, uid))
        return 'demote', new_rank
    return None, None

@app.route('/api/go-rank')
@login_required
def api_go_rank():
    uid = session['user_id']
    with get_db() as conn:
        conn.execute('INSERT OR IGNORE INTO user_stats(user_id) VALUES(?)', (uid,))
        row = conn.execute('SELECT go_rank FROM user_stats WHERE user_id=?', (uid,)).fetchone()
        go_rank = (row['go_rank'] or '30k') if row else '30k'
        results = conn.execute(
            'SELECT result, go_rank, played_at FROM game_results WHERE user_id=? ORDER BY played_at DESC LIMIT 20',
            (uid,)
        ).fetchall()
        conn.commit()
    total  = len(results)
    wins   = sum(r['result'] for r in results)
    recent = [{'result': r['result'], 'go_rank': r['go_rank'], 'played_at': r['played_at']}
              for r in results[:15]]
    return jsonify({
        'go_rank':   go_rank,
        'total':     total,
        'wins':      wins,
        'losses':    total - wins,
        'win_rate':  round(wins / total * 100, 1) if total else 0,
        'recent':    recent,
    })

@app.route('/api/set-go-rank', methods=['POST'])
@login_required
def api_set_go_rank():
    """設定線上對弈初始段位（限最近 5 局以內才允許，最高 3d）。"""
    uid  = session['user_id']
    data = request.get_json() or {}
    rank = str(data.get('rank', '')).strip()
    # 允許的最高段位：3d
    MAX_GO_RANK = '3d'
    max_idx = DIFFICULTY_ORDER.index(MAX_GO_RANK) if MAX_GO_RANK in DIFFICULTY_ORDER else 38
    if rank not in DIFFICULTY_ORDER:
        return jsonify({'ok': False, 'error': '無效的段位'}), 400
    if DIFFICULTY_ORDER.index(rank) > max_idx:
        return jsonify({'ok': False, 'error': f'初始棋力最高只能設到 {MAX_GO_RANK}'}), 400
    with get_db() as conn:
        total_games = conn.execute(
            'SELECT COUNT(*) FROM game_results WHERE user_id=?', (uid,)
        ).fetchone()[0]
        if total_games > 5:
            return jsonify({'ok': False, 'error': '已超過 5 局，無法更改初始棋力'}), 400
        conn.execute('INSERT OR IGNORE INTO user_stats(user_id) VALUES(?)', (uid,))
        conn.execute('UPDATE user_stats SET go_rank=? WHERE user_id=?', (rank, uid))
        conn.commit()
    return jsonify({'ok': True, 'go_rank': rank})

@app.route('/api/set-book-band', methods=['POST'])
@admin_required
def set_book_band():
    """手動設定書本的棋力區間 band_rank。"""
    data      = request.get_json()
    name      = data.get('name', '').strip()
    band_rank = data.get('band_rank')
    if not name or band_rank is None:
        return jsonify({'ok': False, 'error': '參數錯誤'}), 400
    with get_db() as conn:
        conn.execute('INSERT OR REPLACE INTO book_bands(name,band_rank) VALUES(?,?)',
                     (name, int(band_rank)))
        conn.commit()
    return jsonify({'ok': True})

@app.route('/api/rename-book', methods=['POST'])
@admin_required
def rename_book():
    data     = request.get_json()
    old_name = data.get('old', '').strip()
    new_name = data.get('new', '').strip()
    if not new_name:
        return jsonify({'ok': False, 'error': '新書名不可空白'}), 400
    qs = _load_questions()
    updated = 0
    for q in qs:
        if q.get('topic') == old_name:
            q['topic'] = new_name
            updated += 1
    if not updated:
        return jsonify({'ok': False, 'error': '找不到該書本'}), 404
    _save_questions(qs)
    # ── 繼承難度等級：DB 覆寫 > 書名推算 ──────────────────────
    with get_db() as conn:
        row = conn.execute('SELECT band_rank FROM book_bands WHERE name=?', (old_name,)).fetchone()
        inherited_rank = row[0] if row else _book_diff_rank(old_name)
        conn.execute('DELETE FROM book_bands WHERE name=?', (old_name,))
        conn.execute('INSERT OR REPLACE INTO book_bands(name,band_rank) VALUES(?,?)',
                     (new_name, inherited_rank))
        conn.commit()
    return jsonify({'ok': True, 'updated': updated})

@app.route('/api/rename-chapter', methods=['POST'])
@admin_required
def rename_chapter():
    data        = request.get_json()
    book        = data.get('book', '').strip()
    old_chapter = data.get('old', '').strip()
    new_chapter = data.get('new', '').strip()
    if not new_chapter:
        return jsonify({'ok': False, 'error': '新章節名不可空白'}), 400
    qs = _load_questions()
    updated = 0
    for q in qs:
        if q.get('topic') == book and q.get('level') == old_chapter:
            q['level'] = new_chapter
            updated += 1
    if not updated:
        return jsonify({'ok': False, 'error': '找不到該章節'}), 404
    _save_questions(qs)
    return jsonify({'ok': True, 'updated': updated})

@app.route('/api/rename-chapter-prefix', methods=['POST'])
@admin_required
def rename_chapter_prefix():
    """以 display_name 前綴重命名章節（章節名稱由 display_name 計算而來）"""
    data       = request.get_json()
    book       = data.get('book', '').strip()
    old_prefix = data.get('old_prefix', '').strip()
    new_prefix = data.get('new_prefix', '').strip()
    if not new_prefix:
        return jsonify({'ok': False, 'error': '新章節名不可空白'}), 400
    if not old_prefix:
        return jsonify({'ok': False, 'error': '舊章節名不可空白'}), 400
    qs = _load_questions()
    updated = 0
    for q in qs:
        # 比對書本（同 groupLabel 邏輯：topic 優先，Unknown 則用 level）
        t = q.get('topic', '') or ''
        l = q.get('level', '') or ''
        book_match = (t != 'Unknown' and t == book) or (t == 'Unknown' and l == book)
        if not book_match:
            continue
        # 比對章節：q.level 優先（非 Unknown），否則比對 display_name 前綴
        lv       = q.get('level', '') or ''
        dn       = q.get('display_name', '') or ''
        ch_match = (lv not in ('', 'Unknown') and lv == old_prefix) or \
                   (lv in ('', 'Unknown') and dn.startswith(old_prefix))
        if not ch_match:
            continue
        # 更新 level（保留章節資訊）
        if lv not in ('', 'Unknown'):
            q['level'] = new_prefix
        # 更新 display_name 前綴
        if dn.startswith(old_prefix):
            q['display_name'] = new_prefix + dn[len(old_prefix):]
        updated += 1
    if not updated:
        return jsonify({'ok': False, 'error': '找不到該章節或無法重命名'}), 404
    _save_questions(qs)
    return jsonify({'ok': True, 'updated': updated})

@app.route('/api/move-question', methods=['POST'])
@admin_required
def move_question():
    data    = request.get_json()
    qid     = int(data.get('id', 0))
    book    = data.get('book', '').strip()
    chapter = data.get('chapter', '').strip()
    if not book or not chapter:
        return jsonify({'ok': False, 'error': '書本/章節不可空白'}), 400
    qs = _load_questions()
    q  = next((x for x in qs if x['id'] == qid), None)
    if not q:
        return jsonify({'ok': False, 'error': '找不到題目'}), 404
    q['topic'] = book
    q['level'] = chapter
    q['display_name'] = _apply_chapter_to_display(q.get('display_name', ''), chapter)
    _save_questions(qs)
    return jsonify({'ok': True, 'display_name': q['display_name']})

@app.route('/api/delete-question', methods=['POST'])
@admin_required
def delete_question():
    data = request.get_json()
    qid  = int(data.get('id', 0))
    qs   = _load_questions()
    new_qs = [x for x in qs if x['id'] != qid]
    if len(new_qs) == len(qs):
        return jsonify({'ok': False, 'error': '找不到題目'}), 404
    _save_questions(new_qs)
    return jsonify({'ok': True})

@app.route('/api/delete-unit', methods=['POST'])
@admin_required
def delete_unit():
    data    = request.get_json()
    book    = data.get('book', '').strip()
    chapter = data.get('unit', '').strip()
    qs      = _load_questions()
    new_qs  = [x for x in qs if not (x.get('topic') == book and x.get('level') == chapter)]
    deleted = len(qs) - len(new_qs)
    _save_questions(new_qs)
    return jsonify({'ok': True, 'deleted': deleted})

@app.route('/api/delete-book', methods=['POST'])
@admin_required
def delete_book():
    data   = request.get_json()
    book   = data.get('book', '').strip()
    qs     = _load_questions()
    new_qs = [x for x in qs if x.get('topic') != book]
    deleted = len(qs) - len(new_qs)
    _save_questions(new_qs)
    return jsonify({'ok': True, 'deleted': deleted})

@app.route('/api/reorder-questions', methods=['POST'])
@admin_required
def reorder_questions():
    data      = request.get_json()
    id_order  = [int(x) for x in data.get('ids', [])]
    qs        = _load_questions()
    qmap      = {q['id']: q for q in qs}
    for rank, qid in enumerate(id_order, start=1):
        if qid in qmap:
            qmap[qid]['sort_order'] = rank
    _save_questions(qs)
    return jsonify({'ok': True})

@app.route('/api/add-question', methods=['POST'])
@admin_required
def add_question():
    data         = request.get_json()
    sgf          = (data.get('sgf_content') or data.get('sgf', '')).strip()
    display_name = (data.get('display_name') or '').strip()
    book         = (data.get('topic') or data.get('book', '')).strip()
    chapter      = (data.get('level') or data.get('chapter', '')).strip()
    difficulty   = data.get('difficulty', '') or ''
    if not sgf:
        return jsonify({'ok': False, 'error': 'SGF 不可空白'}), 400
    if not book:
        return jsonify({'ok': False, 'error': '書本不可空白'}), 400
    qs     = _load_questions()
    new_id = max((q['id'] for q in qs), default=0) + 1
    # 若沒有提供 display_name，從 GN[] 抽取
    if not display_name:
        import re
        m = re.search(r'GN\[([^\]]+)\]', sgf)
        display_name = m.group(1) if m else f'題目{new_id}'
    # 新題目的 sort_order 排在同書同章末尾
    same_ch = [q for q in qs if q.get('topic') == book and q.get('level') == chapter]
    sort_order = max((q.get('sort_order', 0) for q in same_ch), default=0) + 1
    new_q = {
        'id':           new_id,
        'topic':        book,
        'level':        chapter,
        'display_name': display_name,
        'sort_order':   sort_order,
        'enabled':      True,
        'difficulty':   difficulty,
        'content':      sgf,
        'source':       '',
        'comment':      None,
    }
    qs_copy = list(qs)          # 不改動快取物件，用副本操作
    qs_copy.append(new_q)
    _save_questions(qs_copy)    # _save_questions 內部自動清快取
    return jsonify({'ok': True, 'question': new_q})

# ── 批次操作 ──
@app.route('/api/batch-delete-questions', methods=['POST'])
@admin_required
def batch_delete_questions():
    data    = request.get_json()
    ids     = set(int(x) for x in data.get('ids', []))
    qs      = _load_questions()
    new_qs  = [x for x in qs if x['id'] not in ids]
    deleted = len(qs) - len(new_qs)
    _save_questions(new_qs)
    return jsonify({'ok': True, 'deleted': deleted})

@app.route('/api/batch-move-questions', methods=['POST'])
@admin_required
def batch_move_questions():
    data    = request.get_json()
    ids     = set(int(x) for x in data.get('ids', []))
    book    = data.get('book', '').strip()
    chapter = data.get('chapter', '').strip()
    if not book or not chapter:
        return jsonify({'ok': False, 'error': '書本/章節不可空白'}), 400
    qs      = _load_questions()
    moved   = 0
    updated_names = {}   # id -> new display_name，回傳給前端同步
    for q in qs:
        if q['id'] in ids:
            new_dn = _apply_chapter_to_display(q.get('display_name', ''), chapter)
            q['topic']        = book
            q['level']        = chapter
            q['display_name'] = new_dn
            updated_names[q['id']] = new_dn
            moved += 1
    _save_questions(qs)
    return jsonify({'ok': True, 'moved': moved, 'updated_names': updated_names})


# ══════════════════════════════════════════════════════════════
# SRS API
# ══════════════════════════════════════════════════════════════

@app.route('/api/srs/card/<int:qid>')
@login_required
def srs_card(qid):
    uid = session['user_id']
    with get_db() as conn:
        row = conn.execute(
            'SELECT * FROM srs_cards WHERE user_id=? AND question_id=?',(uid,qid)).fetchone()
    if row: return jsonify(dict(row))
    return jsonify({'user_id':uid,'question_id':qid,'ease_factor':2.5,'interval':0,
                    'repetitions':0,'due_date':datetime.date.today().isoformat(),'last_grade':None})

@app.route('/api/srs/review', methods=['POST'])
@login_required
def srs_review():
    uid       = session['user_id']
    data      = request.get_json()
    qid       = data.get('question_id')
    grade     = data.get('grade')
    unit      = data.get('unit_name')
    unit_done = data.get('unit_done', False)

    if qid is None or grade not in (0,3,5):
        return jsonify({'error':'參數錯誤'}), 400

    # ── 訂閱牆：免費用戶檢查 ────────────────────────────────
    if not is_premium():
        qs_map_check = {q['id']: q for q in _load_questions()}
        q_check = qs_map_check.get(qid, {})

        # 1. 是否為付費題目
        if not question_is_free(q_check):
            return jsonify({
                'error':       'premium_required',
                'message':     '此題目需要 Premium 方案才能練習',
                'upgrade_url': '/upgrade'
            }), 403

        # 2. 是否超過今日上限
        today_count = get_today_free_count(uid)
        if today_count >= FREE_DAILY_LIMIT:
            return jsonify({
                'error':       'daily_limit',
                'message':     f'免費版每日上限 {FREE_DAILY_LIMIT} 題，今日已完成 {today_count} 題',
                'today_count': today_count,
                'limit':       FREE_DAILY_LIMIT,
                'upgrade_url': '/upgrade'
            }), 429

    now = datetime.datetime.now().isoformat()

    qs_map = {q['id']: q for q in _load_questions()}
    q_info = qs_map.get(qid, {})

    with get_db() as conn:
        row = conn.execute(
            'SELECT * FROM srs_cards WHERE user_id=? AND question_id=?',(uid,qid)).fetchone()
        ef,iv,rp = (row['ease_factor'],row['interval'],row['repetitions']) if row else (2.5,0,0)
        ef,iv,rp,due = sm2_update(ef,iv,rp,grade)
        conn.execute('''INSERT INTO srs_cards(user_id,question_id,ease_factor,interval,repetitions,due_date,last_grade,updated_at)
            VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(user_id,question_id) DO UPDATE SET
            ease_factor=excluded.ease_factor, interval=excluded.interval,
            repetitions=excluded.repetitions, due_date=excluded.due_date,
            last_grade=excluded.last_grade, updated_at=excluded.updated_at''',
            (uid,qid,ef,iv,rp,due,grade,now))

        # ── 每日詳細記錄 ────────────────────────────────────
        conn.execute(
            '''INSERT INTO review_log(user_id,question_id,grade,topic,level,difficulty,reviewed_at)
               VALUES(?,?,?,?,?,?,?)''',
            (uid, qid, grade,
             q_info.get('topic',''), q_info.get('level',''), q_info.get('difficulty',''),
             now)
        )

        conn.execute('INSERT OR IGNORE INTO user_stats(user_id) VALUES(?)',(uid,))
        s = conn.execute('SELECT * FROM user_stats WHERE user_id=?',(uid,)).fetchone()
        total        = s['total_correct']
        streak       = s['current_streak']
        mx           = s['max_streak']
        mc           = s['mistake_corrected']
        xp           = s['xp']          or 0
        combo_streak = s['combo_streak'] or 0
        max_combo    = s['max_combo']    or 0
        rank_level   = s['rank_level']   or 'LV1'
        rank_xp      = s['rank_xp']      or 0

        xp_gain    = 0
        combo_mult = 1.0
        ranked_up  = False
        new_rank_level = rank_level
        # 裝備外觀加成
        _appear_fx = _get_appearance_effects(uid, conn)

        mrow = conn.execute(
            'SELECT * FROM mistake_log WHERE user_id=? AND question_id=?',(uid,qid)).fetchone()

        if grade >= 3:
            total += 1; streak += 1; mx = max(mx, streak)
            combo_streak += 1; max_combo = max(max_combo, combo_streak)

            is_new  = not row   # 首次作答此題
            is_mc   = bool(mrow and mrow['wrong_count'] > 0)
            # 上次已答對 → 不再給 XP（避免重複刷分）
            already_correct = bool(row and row['last_grade'] is not None
                                   and row['last_grade'] >= 3)

            if not already_correct:
                diff = q_info.get('difficulty', '')
                xp_gain, combo_mult = calc_xp_gain(diff, combo_streak, is_new, is_mc)
                # 套用外觀 XP 加成（光環 / 袍服 / 配飾）
                if _appear_fx.get('xp_bonus', 0) > 0:
                    xp_gain = int(xp_gain * (1 + _appear_fx['xp_bonus']))
                xp      += xp_gain
                rank_xp += xp_gain

            # LV 進度：以累計 xp 重新計算
            new_lv = xp_to_lv(xp)
            cur_lv = xp_to_lv(xp - xp_gain)
            new_rank_level = f'LV{new_lv}'
            _, rank_xp, _ = lv_progress(xp)
            if new_lv > cur_lv:
                ranked_up = True
        else:
            streak       = 0
            combo_streak = 0

        if grade < 3:
            if mrow:
                conn.execute('UPDATE mistake_log SET wrong_count=wrong_count+1, last_wrong_at=? WHERE user_id=? AND question_id=?',
                             (now,uid,qid))
            else:
                conn.execute('INSERT INTO mistake_log(user_id,question_id,wrong_count,correct_after,first_wrong_at,last_wrong_at) VALUES(?,?,1,0,?,?)',
                             (uid,qid,now,now))
        else:
            if mrow:
                conn.execute('UPDATE mistake_log SET correct_after=correct_after+1, last_correct_at=? WHERE user_id=? AND question_id=?',
                             (now,uid,qid))
                mc += 1

        conn.execute(
            '''UPDATE user_stats SET
               total_correct=?, current_streak=?, max_streak=?, mistake_corrected=?,
               xp=?, combo_streak=?, max_combo=?, rank_level=?, rank_xp=?,
               updated_at=?
               WHERE user_id=?''',
            (total, streak, mx, mc,
             xp, combo_streak, max_combo, new_rank_level, rank_xp,
             now, uid))

        stats = {
            'total_correct': total, 'current_streak': streak,
            'max_streak': mx, 'mistake_corrected': mc,
            'xp': xp, 'combo_streak': combo_streak,
            'max_combo': max_combo, 'rank_level': new_rank_level, 'rank_xp': rank_xp,
        }
        new_badges = check_and_award(conn, uid, stats, unit if unit_done else None)

        # 升段外觀獎勵
        new_appearance_items = []
        if ranked_up:
            new_appearance_items = give_rank_appearance(conn, uid, new_rank_level)

        monster_data = _update_monster_and_quests(
            conn, uid, qid, grade, q_info, combo_streak,
            datetime.date.today().isoformat()
        )

        # ── 同步法典純淨度 (grimoire_api 系統) ─────────────────────
        grimoire_id = q_info.get('grimoire_id')
        if grimoire_id:
            from grimoire_api import calc_node_purity
            is_correct_g = (grade >= 3)
            mastery_g = conn.execute(
                'SELECT * FROM node_mastery WHERE user_id=? AND question_id=?',
                (uid, qid)
            ).fetchone()
            hist_g = json.loads(mastery_g['last_5_history']) if mastery_g else []
            att_cnt = (mastery_g['attempt_count'] + 1) if mastery_g else 1
            hist_g.append(is_correct_g)
            hist_g = hist_g[-5:]
            node_pur = calc_node_purity(hist_g)
            is_cont  = (not is_correct_g) and node_pur < 0.3
            conn.execute('''
                INSERT INTO node_mastery(user_id, question_id, purity, attempt_count,
                                         last_5_history, last_correct_at, is_contaminated)
                VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(user_id, question_id) DO UPDATE SET
                    purity=excluded.purity, attempt_count=excluded.attempt_count,
                    last_5_history=excluded.last_5_history,
                    last_correct_at=CASE WHEN excluded.last_correct_at IS NOT NULL
                                         THEN excluded.last_correct_at
                                         ELSE last_correct_at END,
                    is_contaminated=excluded.is_contaminated
            ''', (uid, qid, node_pur, att_cnt, json.dumps(hist_g),
                  now if is_correct_g else None, 1 if is_cont else 0))
            # 計算法典整體純淨度
            grim_qids = [q['id'] for q in _load_questions()
                         if q.get('grimoire_id') == grimoire_id]
            total_n = max(1, len(grim_qids))
            if grim_qids:
                ph = ','.join('?' * len(grim_qids))
                purity_rows = conn.execute(
                    f'SELECT purity FROM node_mastery WHERE user_id=? '
                    f'AND question_id IN ({ph})',
                    [uid] + grim_qids
                ).fetchall()
                grim_pur = sum(r['purity'] for r in purity_rows) / total_n
            else:
                grim_pur = 0.0
            prog_g = conn.execute(
                'SELECT * FROM player_grimoire_progress WHERE user_id=? AND grimoire_id=?',
                (uid, grimoire_id)
            ).fetchone()
            tot_att = (prog_g['total_attempts'] if prog_g else 0) + 1
            cor_cnt = (prog_g['correct_count']  if prog_g else 0) + (1 if is_correct_g else 0)
            cur_rnk = prog_g['rank'] if prog_g else 0
            thresholds = [(0, 0.3), (1, 0.6), (2, 0.8), (3, 1.0)]
            new_rnk = cur_rnk
            for need_rnk, need_pur in thresholds:
                if cur_rnk == need_rnk and grim_pur >= need_pur:
                    new_rnk = need_rnk + 1
            conn.execute('''
                INSERT INTO player_grimoire_progress
                    (user_id, grimoire_id, rank, purity, total_attempts,
                     correct_count, last_studied_at)
                VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(user_id, grimoire_id) DO UPDATE SET
                    rank=excluded.rank, purity=excluded.purity,
                    total_attempts=excluded.total_attempts,
                    correct_count=excluded.correct_count,
                    last_studied_at=excluded.last_studied_at
            ''', (uid, grimoire_id, new_rnk, grim_pur, tot_att, cor_cnt, now))

        conn.commit()

    return jsonify({
        'ok': True, 'ease_factor': ef, 'interval': iv, 'due_date': due,
        'new_badges': new_badges, 'stats': stats,
        'xp_gain': xp_gain, 'combo_mult': combo_mult,
        'combo_streak': combo_streak,
        'ranked_up': ranked_up,
        'new_rank_level': new_rank_level if ranked_up else None,
        'new_appearance_items': [_APPEAR_MAP[i] for i in new_appearance_items if i in _APPEAR_MAP],
        **monster_data,
    })

@app.route('/api/xp/status')
@login_required
def xp_status():
    uid = session['user_id']
    with get_db() as conn:
        conn.execute('INSERT OR IGNORE INTO user_stats(user_id) VALUES(?)', (uid,))
        s = conn.execute('SELECT * FROM user_stats WHERE user_id=?', (uid,)).fetchone()
        conn.commit()
    total_xp   = (s['xp'] or 0) if s else 0
    lv, rank_xp, xp_needed = lv_progress(total_xp)
    rank_level = f'LV{lv}'
    next_level = f'LV{lv + 1}' if lv < MAX_LV else None
    xp_remaining = max(0, xp_needed - rank_xp) if xp_needed else 0
    return jsonify({
        'xp':             total_xp,
        'combo_streak':   s['combo_streak'] or 0 if s else 0,
        'max_combo':      s['max_combo']    or 0 if s else 0,
        'rank_level':     rank_level,
        'rank_xp':        rank_xp,
        'rank_xp_needed': xp_needed,
        'rank_xp_remaining': xp_remaining,
        'rank_pct':       min(100, round(rank_xp / xp_needed * 100)) if xp_needed else 100,
        'lv':             lv,
        'next_level':      next_level,
    })

@app.route('/api/srs/due')
@login_required
def srs_due():
    uid   = session['user_id']
    today = datetime.date.today().isoformat()
    with get_db() as conn:
        rows = conn.execute(
            'SELECT question_id,interval,ease_factor,due_date FROM srs_cards WHERE user_id=? AND due_date<=?',
            (uid,today)).fetchall()
    qs   = _load_questions()
    seen = {r['question_id'] for r in rows}
    due  = [dict(r) for r in rows]
    due += [{'question_id':q['id'],'interval':0,'ease_factor':2.5,'due_date':today}
            for q in qs if q['id'] not in seen]

    # 免費用戶：只回傳可練習的題目
    if not is_premium():
        free_ids = {q['id'] for q in qs if question_is_free(q)}
        due = [d for d in due if d['question_id'] in free_ids]

    return jsonify({'due':due,'count':len(due)})

@app.route('/api/srs/all')
@login_required
def srs_all():
    uid = session['user_id']
    with get_db() as conn:
        rows = conn.execute('SELECT * FROM srs_cards WHERE user_id=?',(uid,)).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route('/api/map-progress')
@login_required
def map_progress():
    uid = session['user_id']
    qs = [q for q in _load_questions() if q.get('enabled', True)]
    premium = is_premium(uid)
    with get_db() as conn:
        rows = conn.execute(
            'SELECT question_id,last_grade FROM srs_cards WHERE user_id=?',
            (uid,)
        ).fetchall()

    seen_ids = {r['question_id'] for r in rows}
    defeated_ids = {r['question_id'] for r in rows if (r['last_grade'] or 0) >= 3}
    maps = {}
    for q in qs:
        map_id = q.get('map_id') or 'map_unknown'
        item = maps.setdefault(map_id, {
            'map_id': map_id,
            'map_name': q.get('map_name') or q.get('topic') or '未命名地圖',
            'stage': q.get('stage') or 'LV2',
            'stage_label': q.get('stage_label') or q.get('stage') or 'LV2',
            'monster_family': q.get('monster_family') or '',
            'monster_family_label': q.get('monster_family_label') or '',
            'monster_attribute': q.get('monster_attribute') or '',
            'weakness_topic': q.get('weakness_topic') or '',
            'total': 0,
            'unlocked': 0,
            'practiced': 0,
            'defeated': 0,
            'chapter_boss_total': 0,
            'chapter_boss_defeated': 0,
            'book_boss_total': 0,
            'book_boss_defeated': 0,
            'book_boss_status': 'none',
        })
        item['total'] += 1
        if premium or question_is_free(q):
            item['unlocked'] += 1
        qid = q['id']
        if qid in seen_ids:
            item['practiced'] += 1
        if qid in defeated_ids:
            item['defeated'] += 1
        if q.get('encounter_type') == 'chapter_boss':
            item['chapter_boss_total'] += 1
            if qid in defeated_ids:
                item['chapter_boss_defeated'] += 1
        elif q.get('encounter_type') == 'book_boss':
            item['book_boss_total'] += 1
            item['book_boss_status'] = 'defeated' if qid in defeated_ids else ('challenged' if qid in seen_ids else 'locked')
            if qid in defeated_ids:
                item['book_boss_defeated'] += 1

    for item in maps.values():
        item['pct'] = round(item['practiced'] / item['total'] * 100) if item['total'] else 0
        item['defeat_pct'] = round(item['defeated'] / item['total'] * 100) if item['total'] else 0
        if item['book_boss_total'] and item['book_boss_status'] == 'locked' and item['practiced'] >= item['total'] - 1:
            item['book_boss_status'] = 'ready'

    def _stage_sort(item):
        try:
            n = int(str(item.get('stage') or 'LV99').replace('LV', ''))
        except ValueError:
            n = 99
        return (n, item['map_name'])

    return jsonify(sorted(maps.values(), key=_stage_sort))

@app.route('/api/stats/daily')
@login_required
def stats_daily():
    """最近 N 天每日答題數，供首頁 streak dots 使用。"""
    uid  = session['user_id']
    days = min(int(request.args.get('days', 7)), 30)
    with get_db() as conn:
        rows = conn.execute(
            '''SELECT DATE(reviewed_at) as date, COUNT(*) as total,
                      SUM(CASE WHEN grade>=3 THEN 1 ELSE 0 END) as correct
               FROM review_log
               WHERE user_id=?
                 AND reviewed_at >= DATE('now',?)
               GROUP BY DATE(reviewed_at)
               ORDER BY date ASC''',
            (uid, f'-{days} days')
        ).fetchall()
    return jsonify({'days': [dict(r) for r in rows]})


@app.route('/api/srs/stats')
@login_required
def srs_stats():
    uid = session['user_id']
    with get_db() as conn:
        conn.execute('INSERT OR IGNORE INTO user_stats(user_id) VALUES(?)',(uid,))
        row = conn.execute('SELECT * FROM user_stats WHERE user_id=?',(uid,)).fetchone()
        conn.commit()
    d = dict(row) if row else {}
    d.setdefault('xp', 0); d.setdefault('combo_streak', 0)
    d.setdefault('max_combo', 0); d.setdefault('rank_level', '20k'); d.setdefault('rank_xp', 0)
    return jsonify(d)


@app.route('/api/quests/today')
@login_required
def quests_today():
    uid   = session['user_id']
    today = datetime.date.today().isoformat()
    results = []
    with get_db() as conn:
        conn.execute('INSERT OR IGNORE INTO user_stats(user_id) VALUES(?)', (uid,))
        for q in DAILY_QUEST_DEFS:
            conn.execute(
                'INSERT OR IGNORE INTO daily_quests'
                '(user_id,quest_key,target,progress,completed,xp_awarded,quest_date)'
                ' VALUES(?,?,?,0,0,0,?)',
                (uid, q['key'], q['target'], today)
            )
            row = conn.execute(
                'SELECT progress,completed,xp_awarded FROM daily_quests '
                'WHERE user_id=? AND quest_key=? AND quest_date=?',
                (uid, q['key'], today)
            ).fetchone()
            results.append({
                'key':        q['key'],
                'name':       q['name'],
                'icon':       q['icon'],
                'color':      q['color'],
                'desc':       q['desc'].format(target=q['target']),
                'progress':   row['progress']    if row else 0,
                'target':     q['target'],
                'completed':  bool(row['completed']) if row else False,
                'xp':         q['xp'],
                'xp_awarded': row['xp_awarded']  if row else 0,
                'bonus':      q.get('bonus', False),
            })
        conn.commit()
    return jsonify({'quests': results, 'date': today})


@app.route('/api/quests/reset', methods=['POST'])
@admin_required
def quests_reset():
    uid   = session['user_id']
    today = datetime.date.today().isoformat()
    with get_db() as conn:
        conn.execute(
            'DELETE FROM daily_quests WHERE user_id=? AND quest_date=?',
            (uid, today)
        )
        conn.commit()
    return jsonify({'ok': True, 'message': f'已重置 {today} 任務'})

# ══════════════════════════════════════════════════════════════
# 學習儀表板 API
# ══════════════════════════════════════════════════════════════

@app.route('/api/stats/dashboard')
@login_required
def stats_dashboard():
    uid   = session['user_id']
    today = datetime.date.today()

    with get_db() as conn:
        conn.execute('INSERT OR IGNORE INTO user_stats(user_id) VALUES(?)', (uid,))
        stats_row = conn.execute('SELECT * FROM user_stats WHERE user_id=?', (uid,)).fetchone()
        stats = dict(stats_row) if stats_row else {}

        year_ago = (today - datetime.timedelta(days=364)).isoformat()
        heatmap_rows = conn.execute(
            '''SELECT DATE(reviewed_at) as day,
                      COUNT(*) as total,
                      SUM(CASE WHEN grade>=3 THEN 1 ELSE 0 END) as correct
               FROM review_log
               WHERE user_id=? AND reviewed_at>=?
               GROUP BY DATE(reviewed_at)
               ORDER BY day''',
            (uid, year_ago)
        ).fetchall()
        heatmap = {r['day']: {'total': r['total'], 'correct': r['correct']} for r in heatmap_rows}

        streak_days = 0
        check_date  = today
        if today.isoformat() not in heatmap:
            check_date = today - datetime.timedelta(days=1)
        for _ in range(365):
            if check_date.isoformat() in heatmap:
                streak_days += 1
                check_date -= datetime.timedelta(days=1)
            else:
                break

        weekly = []
        this_monday = today - datetime.timedelta(days=today.weekday())
        for w in range(7, -1, -1):
            week_start = this_monday - datetime.timedelta(weeks=w)
            week_end   = week_start + datetime.timedelta(days=6)
            row = conn.execute(
                '''SELECT COUNT(*) as total,
                          SUM(CASE WHEN grade>=3 THEN 1 ELSE 0 END) as correct
                   FROM review_log
                   WHERE user_id=? AND DATE(reviewed_at) BETWEEN ? AND ?''',
                (uid, week_start.isoformat(), week_end.isoformat())
            ).fetchone()
            total   = row['total']   or 0
            correct = row['correct'] or 0
            weekly.append({
                'week_start': week_start.isoformat(),
                'label':      f"{week_start.month}/{week_start.day}",
                'total':      total,
                'correct':    correct,
                'accuracy':   round(correct / total * 100, 1) if total > 0 else None
            })

        def week_stats(start, end):
            r = conn.execute(
                '''SELECT COUNT(*) as total,
                          SUM(CASE WHEN grade>=3 THEN 1 ELSE 0 END) as correct,
                          COUNT(DISTINCT DATE(reviewed_at)) as active_days
                   FROM review_log WHERE user_id=? AND DATE(reviewed_at) BETWEEN ? AND ?''',
                (uid, start.isoformat(), end.isoformat())
            ).fetchone()
            total   = r['total']   or 0
            correct = r['correct'] or 0
            return {
                'total':       total,
                'correct':     correct,
                'accuracy':    round(correct / total * 100, 1) if total > 0 else None,
                'active_days': r['active_days'] or 0
            }

        last_monday  = this_monday - datetime.timedelta(weeks=1)
        last_sunday  = last_monday + datetime.timedelta(days=6)
        this_week = week_stats(this_monday, today)
        last_week = week_stats(last_monday, last_sunday)

        ninety_ago = (today - datetime.timedelta(days=90)).isoformat()
        topic_rows = conn.execute(
            '''SELECT COALESCE(NULLIF(topic,''), '未分類') as label,
                      COUNT(*) as total,
                      SUM(CASE WHEN grade>=3 THEN 1 ELSE 0 END) as correct
               FROM review_log
               WHERE user_id=? AND reviewed_at>=? AND topic IS NOT NULL AND topic!=''
               GROUP BY topic
               HAVING total >= 3
               ORDER BY (correct * 1.0 / total) ASC
               LIMIT 8''',
            (uid, ninety_ago)
        ).fetchall()
        topic_weakness = [
            {'label': r['label'], 'total': r['total'], 'correct': r['correct'],
             'accuracy': round(r['correct'] / r['total'] * 100, 1)}
            for r in topic_rows
        ]

        diff_rows = conn.execute(
            '''SELECT difficulty as label,
                      COUNT(*) as total,
                      SUM(CASE WHEN grade>=3 THEN 1 ELSE 0 END) as correct
               FROM review_log
               WHERE user_id=? AND reviewed_at>=? AND difficulty IS NOT NULL AND difficulty!=''
               GROUP BY difficulty
               HAVING total >= 3''',
            (uid, ninety_ago)
        ).fetchall()
        diff_stats = [
            {'label': r['label'], 'total': r['total'], 'correct': r['correct'],
             'accuracy': round(r['correct'] / r['total'] * 100, 1)}
            for r in diff_rows
        ]

        today_row = conn.execute(
            '''SELECT COUNT(*) as total,
                      SUM(CASE WHEN grade>=3 THEN 1 ELSE 0 END) as correct
               FROM review_log WHERE user_id=? AND DATE(reviewed_at)=?''',
            (uid, today.isoformat())
        ).fetchone()
        today_stats = {
            'total':   today_row['total']   or 0,
            'correct': today_row['correct'] or 0
        }

        conn.commit()

    return jsonify({
        'stats':          stats,
        'streak_days':    streak_days,
        'heatmap':        heatmap,
        'weekly':         weekly,
        'this_week':      this_week,
        'last_week':      last_week,
        'topic_weakness': topic_weakness,
        'diff_stats':     diff_stats,
        'today':          today_stats,
        'as_of':          today.isoformat()
    })

# ══════════════════════════════════════════════════════════════
# 錯題本 API
# ══════════════════════════════════════════════════════════════

@app.route('/api/mistakes')
@login_required
def get_mistakes():
    uid = session['user_id']
    with get_db() as conn:
        rows = conn.execute(
            'SELECT * FROM mistake_log WHERE user_id=? ORDER BY wrong_count DESC, last_wrong_at DESC',
            (uid,)).fetchall()
    mistakes = [dict(r) for r in rows]
    if not mistakes: return jsonify([])
    qs     = _load_questions()
    qs_map = {q['id']: q for q in qs}
    result = []
    for m in mistakes:
        q = qs_map.get(m['question_id'])
        if q:
            result.append({**m, 'topic':q.get('topic',''), 'level':q.get('level',''),
                           'difficulty':q.get('difficulty',''), 'content':q.get('content','')})
    return jsonify(result)

@app.route('/api/mistakes/stats')
@login_required
def mistake_stats():
    uid = session['user_id']
    with get_db() as conn:
        total     = conn.execute('SELECT COUNT(*) FROM mistake_log WHERE user_id=?',(uid,)).fetchone()[0]
        worst5    = conn.execute(
            'SELECT question_id,wrong_count FROM mistake_log WHERE user_id=? ORDER BY wrong_count DESC LIMIT 5',
            (uid,)).fetchall()
        corrected = conn.execute(
            'SELECT COUNT(*) FROM mistake_log WHERE user_id=? AND correct_after>0',(uid,)).fetchone()[0]
    return jsonify({'total':total,'corrected':corrected,'worst5':[dict(r) for r in worst5]})

@app.route('/api/mistakes/remove', methods=['POST'])
@login_required
def remove_mistake():
    uid  = session['user_id']
    data = request.get_json()
    qid  = data.get('question_id')
    if qid is None: return jsonify({'error':'缺少 question_id'}),400
    with get_db() as conn:
        conn.execute('DELETE FROM mistake_log WHERE user_id=? AND question_id=?',(uid,qid))
        conn.commit()
    return jsonify({'ok':True})

# ══════════════════════════════════════════════════════════════
# Badges API
# ══════════════════════════════════════════════════════════════

@app.route('/api/badges/definitions')
@login_required
def badge_definitions():
    defs = [dict(b) for b in BADGE_DEFS]   # 完整複製（含 premium_only）
    qs   = _load_questions()
    for u in {group_label(q) for q in qs}:
        defs.append({'id':'unit_'+u.replace(' ','_'),'name':f'完成《{u}》',
                     'icon':'📖','desc':f'完成單元「{u}」的所有題目',
                     'type':'unit_complete','value':u})
    return jsonify(defs)

@app.route('/api/badges/earned')
@login_required
def badges_earned():
    uid = session['user_id']
    with get_db() as conn:
        rows = conn.execute(
            'SELECT * FROM badges_earned WHERE user_id=? ORDER BY earned_at DESC',(uid,)).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route('/api/badges/seen', methods=['POST'])
@login_required
def badges_seen():
    uid  = session['user_id']
    data = request.get_json()
    with get_db() as conn:
        for bid in data.get('ids',[]):
            conn.execute('UPDATE badges_earned SET seen=1 WHERE user_id=? AND badge_id=?',(uid,bid))
        conn.commit()
    return jsonify({'ok':True})

@app.route('/api/badges/unseen')
@login_required
def badges_unseen():
    uid = session['user_id']
    with get_db() as conn:
        rows = conn.execute(
            'SELECT badge_id FROM badges_earned WHERE user_id=? AND seen=0',(uid,)).fetchall()
    return jsonify([r['badge_id'] for r in rows])

# ══════════════════════════════════════════════════════════════
# 每日挑戰 API
# ══════════════════════════════════════════════════════════════

@app.route('/api/daily-challenge/today')
@login_required
def dc_today():
    uid   = session['user_id']
    today = datetime.date.today().isoformat()
    dc    = get_or_create_daily_challenge(today)
    if not dc:
        return jsonify({'error': '題庫為空'}), 503

    qs_map = {q['id']: q for q in _load_questions()}
    q      = qs_map.get(dc['question_id'])
    if not q:
        return jsonify({'error': '題目不存在'}), 404

    with get_db() as conn:
        log = conn.execute(
            'SELECT correct FROM daily_challenge_log '
            'WHERE user_id=? AND challenge_date=?',
            (uid, today)
        ).fetchone()
        stats_row = conn.execute(
            'SELECT COUNT(*) as total, SUM(correct) as cnt '
            'FROM daily_challenge_log WHERE challenge_date=?',
            (today,)
        ).fetchone()

    total_p   = stats_row['total'] or 0
    correct_p = stats_row['cnt']   or 0

    return jsonify({
        'date':           today,
        'question_id':    q['id'],
        'content':        q.get('content', ''),
        'topic':          q.get('topic', ''),
        'level':          q.get('level', ''),
        'difficulty':     q.get('difficulty', ''),
        'rank':           q.get('rank', ''),
        'note':           dc.get('note'),
        'user_submitted': log is not None,
        'user_correct':   bool(log['correct']) if log else None,
        'stats': {
            'total':    total_p,
            'correct':  correct_p,
            'accuracy': round(correct_p / (total_p or 1) * 100),
        } if log else None,
    })


@app.route('/api/daily-challenge/submit', methods=['POST'])
@login_required
def dc_submit():
    uid     = session['user_id']
    today   = datetime.date.today().isoformat()
    data    = request.get_json()
    correct = 1 if data.get('correct') else 0

    dc = get_or_create_daily_challenge(today)
    if not dc:
        return jsonify({'error': '題庫為空'}), 503

    now = datetime.datetime.now().isoformat()
    with get_db() as conn:
        existing = conn.execute(
            'SELECT id FROM daily_challenge_log '
            'WHERE user_id=? AND challenge_date=?',
            (uid, today)
        ).fetchone()
        if existing:
            return jsonify({'error': 'already_submitted'}), 409

        conn.execute(
            'INSERT INTO daily_challenge_log'
            '(user_id,challenge_date,question_id,correct,submitted_at) '
            'VALUES(?,?,?,?,?)',
            (uid, today, dc['question_id'], correct, now)
        )
        conn.commit()

        stats_row = conn.execute(
            'SELECT COUNT(*) as total, SUM(correct) as cnt '
            'FROM daily_challenge_log WHERE challenge_date=?',
            (today,)
        ).fetchone()
        total_p   = stats_row['total'] or 0
        correct_p = stats_row['cnt']   or 0

        rank = None
        if correct:
            rank_row = conn.execute(
                'SELECT COUNT(*) as r FROM daily_challenge_log '
                'WHERE challenge_date=? AND correct=1 AND submitted_at<=?',
                (today, now)
            ).fetchone()
            rank = rank_row['r'] if rank_row else None

        new_badge_ids = check_and_award_daily(conn, uid, bool(correct), today)
        streak = get_daily_submit_streak(uid, today)
        new_appear_ids = give_daily_appearance(conn, uid, streak)
        conn.commit()

    defs_map   = {b['id']: b for b in BADGE_DEFS}
    new_badges = [defs_map[bid] for bid in new_badge_ids if bid in defs_map]
    new_appear_items = [_APPEAR_MAP[i] for i in new_appear_ids if i in _APPEAR_MAP]

    return jsonify({
        'ok': True,
        'stats': {
            'total':    total_p,
            'correct':  correct_p,
            'accuracy': round(correct_p / (total_p or 1) * 100),
            'rank':     rank,
        },
        'new_badges':          new_badges,
        'new_appearance_items': new_appear_items,
    })


@app.route('/api/daily-challenge/history')
@login_required
def dc_history():
    uid = session['user_id']
    if not is_premium(uid):
        return jsonify({'error': 'premium_required'}), 403

    today  = datetime.date.today().isoformat()
    qs_map = {q['id']: q for q in _load_questions()}

    with get_db() as conn:
        rows = conn.execute(
            '''SELECT dc.challenge_date, dc.question_id, dc.note,
                      agg.total, agg.cnt,
                      log.correct AS user_correct
               FROM daily_challenge dc
               LEFT JOIN (
                   SELECT challenge_date,
                          COUNT(*)      AS total,
                          SUM(correct)  AS cnt
                   FROM daily_challenge_log GROUP BY challenge_date
               ) agg ON agg.challenge_date = dc.challenge_date
               LEFT JOIN daily_challenge_log log
                      ON log.challenge_date = dc.challenge_date
                     AND log.user_id = ?
               WHERE dc.challenge_date < ?
               ORDER BY dc.challenge_date DESC
               LIMIT 60''',
            (uid, today)
        ).fetchall()

    history = []
    for r in rows:
        q = qs_map.get(r['question_id'], {})
        history.append({
            'date':        r['challenge_date'],
            'question_id': r['question_id'],
            'difficulty':  q.get('difficulty', ''),
            'rank':        q.get('rank', ''),
            'topic':       q.get('topic', ''),
            'note':        r['note'],
            'total':       r['total'] or 0,
            'correct':     r['cnt']   or 0,
            'accuracy':    round((r['cnt'] or 0) / (r['total'] or 1) * 100),
            'user_correct': None if r['user_correct'] is None else bool(r['user_correct']),
        })
    return jsonify({'history': history})


@app.route('/api/daily-challenge/history/<date_str>')
@login_required
def dc_history_detail(date_str):
    uid   = session['user_id']
    today = datetime.date.today().isoformat()
    if not is_premium(uid):
        return jsonify({'error': 'premium_required'}), 403
    if date_str >= today:
        return jsonify({'error': 'not_available'}), 403

    with get_db() as conn:
        dc = conn.execute(
            'SELECT * FROM daily_challenge WHERE challenge_date=?', (date_str,)
        ).fetchone()
    if not dc:
        return jsonify({'error': 'not_found'}), 404

    qs_map = {q['id']: q for q in _load_questions()}
    q = qs_map.get(dc['question_id'])
    if not q:
        return jsonify({'error': 'question_not_found'}), 404

    return jsonify({
        'date':       date_str,
        'content':    q.get('content', ''),
        'topic':      q.get('topic', ''),
        'level':      q.get('level', ''),
        'difficulty': q.get('difficulty', ''),
        'rank':       q.get('rank', ''),
        'note':       dc['note'],
    })


@app.route('/api/admin/daily-challenge/set', methods=['POST'])
@admin_required
def dc_admin_set():
    """管理員手動指定某天的每日挑戰題目。"""
    data        = request.get_json()
    date_str    = data.get('date')
    question_id = data.get('question_id')
    note        = data.get('note', '')
    if not date_str or not question_id:
        return jsonify({'error': 'missing fields'}), 400
    qs_map = {q['id']: q for q in _load_questions()}
    if question_id not in qs_map:
        return jsonify({'error': 'question not found'}), 404
    with get_db() as conn:
        conn.execute(
            '''INSERT INTO daily_challenge(challenge_date,question_id,set_by,note)
               VALUES(?,?,?,?)
               ON CONFLICT(challenge_date) DO UPDATE SET
                   question_id=excluded.question_id,
                   set_by='admin', note=excluded.note''',
            (date_str, question_id, 'admin', note)
        )
        conn.commit()
    return jsonify({'ok': True})

# ══════════════════════════════════════════════════════════════
# 技能 / 裝備 / SP API
# ══════════════════════════════════════════════════════════════

@app.route('/api/player/sp')
@login_required
def get_sp():
    uid   = session['user_id']
    today = datetime.date.today().isoformat()
    with get_db() as conn:
        row = conn.execute('SELECT * FROM player_sp WHERE user_id=?', (uid,)).fetchone()
        if not row or row['sp_date'] != today:
            equip_bonus = _get_equip_effect(conn, uid, 'sp_bonus')
            new_max = SP_MAX_DAILY + int(equip_bonus)
            conn.execute(
                'INSERT INTO player_sp(user_id,current_sp,sp_date,daily_used) VALUES(?,?,?,?) '
                'ON CONFLICT(user_id) DO UPDATE SET current_sp=?,sp_date=?,daily_used=?',
                (uid, 0, today, '{}', 0, today, '{}')
            )
            conn.commit()
            return jsonify({'sp': 0, 'max_sp': new_max})
        equip_bonus = _get_equip_effect(conn, uid, 'sp_bonus')
        new_max = SP_MAX_DAILY + int(equip_bonus)
        return jsonify({'sp': row['current_sp'], 'max_sp': new_max})


@app.route('/api/player/skills')
@login_required
def get_skills():
    uid = session['user_id']
    with get_db() as conn:
        learned = {r['skill_id']: dict(r) for r in
                   conn.execute('SELECT * FROM player_skills WHERE user_id=?', (uid,)).fetchall()}
        stats = conn.execute('SELECT rank_level FROM user_stats WHERE user_id=?', (uid,)).fetchone()
    rank = (stats['rank_level'] if stats else 'LV1')
    rank_lv = _rank_to_lv(rank)
    result = []
    for s in SKILL_DEFS:
        ur_lv = _rank_to_lv(s.get('unlock_rank', 'LV1'))
        info = dict(s)
        info['unlocked'] = rank_lv >= ur_lv
        info['learned']  = s['id'] in learned
        info['equipped'] = learned.get(s['id'], {}).get('equipped', 0) == 1
        result.append(info)
    return jsonify(result)


@app.route('/api/player/skills/equip', methods=['POST'])
@login_required
def equip_skill():
    uid  = session['user_id']
    data = request.get_json()
    sid  = data.get('skill_id')
    act  = data.get('action', 'learn')   # 'learn' | 'equip' | 'unequip'
    skill = _SKILL_MAP.get(sid)
    if not skill:
        return jsonify({'error': '找不到技能'}), 404

    with get_db() as conn:
        stats = conn.execute('SELECT rank_level FROM user_stats WHERE user_id=?', (uid,)).fetchone()
        rank = stats['rank_level'] if stats else 'LV1'
        rank_lv = _rank_to_lv(rank)
        ur_lv   = _rank_to_lv(skill.get('unlock_rank', 'LV1'))
        if rank_lv < ur_lv:
            return jsonify({'error': f'需要達到 {skill["unlock_rank"]} 才能學習'}), 403

        if act == 'learn':
            conn.execute(
                'INSERT OR IGNORE INTO player_skills(user_id,skill_id,equipped,learned_at) VALUES(?,?,0,?)',
                (uid, sid, datetime.datetime.now().isoformat())
            )
        elif act == 'equip':
            conn.execute('UPDATE player_skills SET equipped=1 WHERE user_id=? AND skill_id=?', (uid, sid))
        elif act == 'unequip':
            conn.execute('UPDATE player_skills SET equipped=0 WHERE user_id=? AND skill_id=?', (uid, sid))
        conn.commit()
    return jsonify({'ok': True})


@app.route('/api/player/inventory')
@login_required
def get_inventory():
    uid = session['user_id']
    with get_db() as conn:
        rows = conn.execute(
            'SELECT * FROM player_inventory WHERE user_id=? ORDER BY obtained_at DESC',
            (uid,)
        ).fetchall()
    result = []
    for r in rows:
        eq = _EQUIP_MAP.get(r['equip_id'], {})
        result.append({**eq, 'inv_id': r['id'], 'equipped': bool(r['equipped']),
                        'obtained_at': r['obtained_at'], 'source': r['source']})
    return jsonify(result)


@app.route('/api/player/inventory/equip', methods=['POST'])
@login_required
def equip_item():
    uid  = session['user_id']
    data = request.get_json()
    inv_id = data.get('inv_id')
    act    = data.get('action', 'equip')  # 'equip' | 'unequip'
    with get_db() as conn:
        row = conn.execute('SELECT * FROM player_inventory WHERE id=? AND user_id=?',
                           (inv_id, uid)).fetchone()
        if not row:
            return jsonify({'error': '找不到物品'}), 404
        equip = _EQUIP_MAP.get(row['equip_id'], {})
        slot  = equip.get('slot')
        if act == 'equip' and slot:
            # 卸下同 slot 其他裝備
            slot_ids = [e['id'] for e in EQUIPMENT_DEFS if e['slot'] == slot]
            if slot_ids:
                placeholders = ','.join(['?' for _ in slot_ids])
                conn.execute(
                    f'UPDATE player_inventory SET equipped=0 WHERE user_id=? AND equip_id IN ({placeholders})',
                    (uid, *slot_ids)
                )
            conn.execute('UPDATE player_inventory SET equipped=1 WHERE id=?', (inv_id,))
        else:
            conn.execute('UPDATE player_inventory SET equipped=0 WHERE id=?', (inv_id,))
        conn.commit()
    return jsonify({'ok': True})


# ══════════════════════════════════════════════════════════════
# 角色外觀 API
# ══════════════════════════════════════════════════════════════

@app.route('/api/player/appearance')
@login_required
def get_appearance():
    """取得目前穿戴狀態 + 衣櫃物品列表。"""
    uid = session['user_id']
    with get_db() as conn:
        eq_row = conn.execute(
            'SELECT * FROM player_appearance WHERE user_id=?', (uid,)
        ).fetchone()
        wardrobe_rows = conn.execute(
            'SELECT item_id, obtained_at, source FROM player_wardrobe'
            ' WHERE user_id=? ORDER BY obtained_at DESC',
            (uid,)
        ).fetchall()

    equipped = {
        'outfit_id': eq_row['outfit_id'] if eq_row else None,
        'hat_id':    eq_row['hat_id']    if eq_row else None,
        'back_id':   eq_row['back_id']   if eq_row else None,
        'title_id':  eq_row['title_id']  if eq_row else None,
    }

    wardrobe = []
    for r in wardrobe_rows:
        item = _APPEAR_MAP.get(r['item_id'])
        if not item:
            continue
        slot_key = item['slot'] + '_id'
        wardrobe.append({
            **item,
            'obtained_at': r['obtained_at'],
            'source':      r['source'],
            'is_equipped': equipped.get(slot_key) == item['id'],
        })

    return jsonify({
        'equipped': equipped,
        'wardrobe': wardrobe,
        'av_type':  eq_row['av_type']  if eq_row else None,
        'av_value': eq_row['av_value'] if eq_row else None,
    })


@app.route('/api/player/appearance/equip', methods=['POST'])
@login_required
def equip_appearance():
    """穿上某件外觀物品（自動卸下同槽舊品）。"""
    uid     = session['user_id']
    data    = request.get_json()
    item_id = data.get('item_id')

    item = _APPEAR_MAP.get(item_id)
    if not item:
        return jsonify({'error': '找不到物品'}), 404

    slot_col = item['slot'] + '_id'
    with get_db() as conn:
        owned = conn.execute(
            'SELECT id FROM player_wardrobe WHERE user_id=? AND item_id=?',
            (uid, item_id)
        ).fetchone()
        if not owned:
            return jsonify({'error': '尚未持有此物品'}), 403

        now = datetime.datetime.now().isoformat()
        conn.execute(
            f'INSERT INTO player_appearance(user_id, {slot_col}, updated_at)'
            f' VALUES(?, ?, ?)'
            f' ON CONFLICT(user_id) DO UPDATE SET'
            f' {slot_col}=excluded.{slot_col}, updated_at=excluded.updated_at',
            (uid, item_id, now)
        )
        conn.commit()

    return jsonify({'ok': True, 'slot': item['slot'], 'item_id': item_id})


@app.route('/api/player/appearance/unequip', methods=['POST'])
@login_required
def unequip_appearance():
    """卸下某槽外觀（slot: outfit / hat / back / title）。"""
    uid  = session['user_id']
    data = request.get_json()
    slot = data.get('slot')

    if slot not in ('outfit', 'hat', 'back', 'title', 'accessory', 'pet', 'aura'):
        return jsonify({'error': '無效槽位'}), 400

    slot_col = slot + '_id'
    now = datetime.datetime.now().isoformat()
    with get_db() as conn:
        conn.execute(
            f'INSERT INTO player_appearance(user_id, {slot_col}, updated_at)'
            f' VALUES(?, NULL, ?)'
            f' ON CONFLICT(user_id) DO UPDATE SET'
            f' {slot_col}=NULL, updated_at=excluded.updated_at',
            (uid, now)
        )
        conn.commit()

    return jsonify({'ok': True, 'slot': slot})


@app.route('/api/player/wardrobe')
@login_required
def get_wardrobe():
    """完整衣櫃清單，按 slot 分組。"""
    uid = session['user_id']
    with get_db() as conn:
        eq_row = conn.execute(
            'SELECT * FROM player_appearance WHERE user_id=?', (uid,)
        ).fetchone()
        rows = conn.execute(
            'SELECT item_id, obtained_at, source FROM player_wardrobe'
            ' WHERE user_id=? ORDER BY obtained_at DESC',
            (uid,)
        ).fetchall()

    equipped_ids = set()
    if eq_row:
        for col in ('outfit_id', 'hat_id', 'back_id', 'title_id'):
            if eq_row[col]:
                equipped_ids.add(eq_row[col])

    by_slot = {'outfit': [], 'hat': [], 'back': [], 'title': []}
    for r in rows:
        item = _APPEAR_MAP.get(r['item_id'])
        if not item:
            continue
        by_slot.setdefault(item['slot'], []).append({
            **item,
            'obtained_at': r['obtained_at'],
            'source':      r['source'],
            'is_equipped': r['item_id'] in equipped_ids,
        })

    return jsonify({'by_slot': by_slot, 'total': len(rows)})


@app.route('/api/player/appearance/all-items')
@login_required
def all_appearance_items():
    """全部外觀物品定義（含已持有 / 已穿戴），供圖鑑頁用。"""
    uid = session['user_id']
    with get_db() as conn:
        owned = {r['item_id'] for r in conn.execute(
            'SELECT item_id FROM player_wardrobe WHERE user_id=?', (uid,)
        ).fetchall()}
        eq_row = conn.execute(
            'SELECT * FROM player_appearance WHERE user_id=?', (uid,)
        ).fetchone()

    equipped_ids = set()
    if eq_row:
        for col in ('outfit_id', 'hat_id', 'back_id', 'title_id'):
            if eq_row[col]:
                equipped_ids.add(eq_row[col])

    result = []
    for item in APPEARANCE_DEFS:
        result.append({
            **item,
            'owned':       item['id'] in owned,
            'is_equipped': item['id'] in equipped_ids,
        })

    return jsonify(result)


@app.route('/api/skills/profile')
@login_required
def skills_profile():
    """
    skills.html 所需的聚合資料：
      - 角色面板：username / level / xp / xp_next / rank / equipped_labels
      - inventory：badges / frames / stones / boards / titles（已持有 + equipped 狀態）
      - wardrobe：全外觀物品（含 owned / equipped）
      - new_unlock：是否有尚未提示的解鎖（從 session flag 讀取）
    """
    uid = session['user_id']
    with get_db() as conn:
        # ── 基本統計 ──────────────────────────────────────────────
        stats = conn.execute(
            'SELECT xp, rank_level, rank_xp, go_rank FROM user_stats WHERE user_id=?',
            (uid,)
        ).fetchone()
        elo_row = conn.execute(
            'SELECT elo_rating FROM users WHERE id=?', (uid,)
        ).fetchone()
        username = session.get('username', '—')
        nickname = session.get('nickname', '')
        total_xp   = stats['xp']      if stats else 0
        go_rank    = (stats['go_rank'] if stats and stats['go_rank'] else '30k')
        lv, lv_xp, lv_xp_next = lv_progress(total_xp)
        rank_level = f'LV{lv}'

        # ── 外觀：已穿戴 / 衣櫃 ──────────────────────────────────
        eq_row = conn.execute(
            'SELECT * FROM player_appearance WHERE user_id=?', (uid,)
        ).fetchone()
        wardrobe_rows = conn.execute(
            'SELECT item_id FROM player_wardrobe WHERE user_id=?', (uid,)
        ).fetchall()

        owned_ids    = {r['item_id'] for r in wardrobe_rows}
        equipped_ids = set()
        eq_cols = eq_row.keys() if eq_row else []
        if eq_row:
            for col in ('outfit_id', 'hat_id', 'back_id', 'title_id',
                        'accessory_id', 'pet_id', 'aura_id'):
                if col in eq_cols and eq_row[col]:
                    equipped_ids.add(eq_row[col])

        # ── inventory：依 slot 分組（只顯示已持有） ───────────────
        slot_map = {'badge': [], 'frame': [], 'stone': [], 'board': [], 'title': []}
        for item in APPEARANCE_DEFS:
            if item['id'] not in owned_ids:
                continue
            slot = item.get('slot', '')
            if slot not in slot_map:
                continue
            slot_map[slot].append({
                'id':       item['id'],
                'name':     item.get('name', item['id']),
                'icon':     item.get('emoji', item.get('icon', '❓')),
                'equipped': item['id'] in equipped_ids,
            })

        # ── wardrobe：全物品（含 owned 旗標），供外觀頁用 ──────────
        wardrobe = []
        for item in APPEARANCE_DEFS:
            wardrobe.append({
                'id':       item['id'],
                'name':     item.get('name', item['id']),
                'icon':     item.get('emoji', item.get('icon', '❓')),
                'type':     item.get('slot', ''),
                'rarity':   item.get('rarity', 'common'),
                'color':    item.get('color', ''),
                'hint':     item.get('hint', ''),
                'effects':  APPEARANCE_EFFECTS.get(item['id'], {}),
                'owned':    item['id'] in owned_ids,
                'equipped': item['id'] in equipped_ids,
            })

        # ── equipped_labels（角色面板小標） ───────────────────────
        equipped_labels = [
            _APPEAR_MAP[eid].get('name', eid)
            for eid in equipped_ids
            if eid in _APPEAR_MAP
        ]

    # ── active_effects & equipped_visuals ───────────────────────
    with get_db() as _conn2:
        appear_fx = _get_appearance_effects(uid, _conn2)
    equipped_visuals = {}
    for iid in equipped_ids:
        item = _APPEAR_MAP.get(iid)
        if item:
            equipped_visuals[item['slot']] = {
                'icon':  item.get('emoji', item.get('icon', '')),
                'color': item.get('color', ''),
                'name':  item.get('name', iid),
            }

    # new_unlock flag（一次性，讀完即清除）
    new_unlock = session.pop('new_unlock', False)

    return jsonify({
        'username':       username,
        'nickname':       nickname,
        'display_name':   nickname or username,
        'lv':             lv,
        'lv_xp':          lv_xp,
        'lv_xp_next':     lv_xp_next,
        'lv_pct':         min(100, round(lv_xp / lv_xp_next * 100)) if lv_xp_next else 100,
        'rank_level':     rank_level,   # 'LV12' 格式，練習等級
        'go_rank':        go_rank,      # '15k' 格式，線上對弈棋力
        # 向後相容：舊版 rank / level / xp / xp_next 欄位
        'rank':           rank_level,
        'level':          lv,
        'xp':             lv_xp,
        'xp_next':        lv_xp_next,
        'total_xp':       total_xp,
        'equipped_labels': equipped_labels,
        'av_type':        eq_row['av_type']  if eq_row else None,
        'av_value':       eq_row['av_value'] if eq_row else None,
        'inventory': {
            'badges': slot_map.get('badge', []),
            'frames': slot_map.get('frame', []),
            'stones': slot_map.get('stone', []),
            'boards': slot_map.get('board', []),
            'titles': slot_map.get('title', []),
        },
        'wardrobe':          wardrobe,
        'active_effects':    appear_fx,
        'equipped_visuals':  equipped_visuals,
        'new_unlock':        new_unlock,
        'is_premium':        is_premium(uid),
        'elo_rating':        elo_row['elo_rating'] if elo_row and elo_row['elo_rating'] else None,
    })


@app.route('/api/skills/avatar', methods=['POST'])
@login_required
def skills_avatar():
    """
    儲存自訂頭像到 player_appearance。
    Body: { "type": "emoji", "value": "🦊" }
        | { "type": "image", "data": "data:image/...;base64,..." }
    """
    uid  = session['user_id']
    data = request.get_json() or {}
    av_type  = data.get('type')    # 'emoji' | 'image'
    av_value = data.get('value') or data.get('data')   # emoji char or data-url

    if av_type not in ('emoji', 'image') or not av_value:
        return jsonify({'error': 'invalid payload'}), 400

    # data-url 大小限制（~500 KB base64 ≈ 375 KB image）
    if av_type == 'image' and len(av_value) > 600_000:
        return jsonify({'error': 'image too large'}), 413

    with get_db() as conn:
        existing = conn.execute(
            'SELECT user_id FROM player_appearance WHERE user_id=?', (uid,)
        ).fetchone()
        if existing:
            conn.execute(
                'UPDATE player_appearance SET av_type=?, av_value=?, updated_at=? WHERE user_id=?',
                (av_type, av_value, datetime.datetime.now().isoformat(), uid),
            )
        else:
            conn.execute(
                'INSERT INTO player_appearance(user_id, av_type, av_value, updated_at) VALUES(?,?,?,?)',
                (uid, av_type, av_value, datetime.datetime.now().isoformat()),
            )

    return jsonify({'ok': True})


@app.route('/api/skills/equip', methods=['POST'])
@login_required
def skills_equip():
    """
    skills.html 裡的裝備按鈕呼叫此端點。
    接受兩種格式（相容 inventory 與 wardrobe 兩個呼叫路徑）：
      { "id": "<item_id>" }                   ← wardrobe 路徑
      { "slotId": "badge", "itemId": "xxx" }  ← inventory 路徑
    """
    uid  = session['user_id']
    data = request.get_json() or {}
    item_id = data.get('id') or data.get('itemId')

    if not item_id:
        return jsonify({'error': '缺少 item_id'}), 400

    item = _APPEAR_MAP.get(item_id)
    if not item:
        return jsonify({'error': '找不到物品'}), 404

    slot_col = item['slot'] + '_id'
    with get_db() as conn:
        owned = conn.execute(
            'SELECT id FROM player_wardrobe WHERE user_id=? AND item_id=?',
            (uid, item_id)
        ).fetchone()
        if not owned:
            return jsonify({'error': '尚未持有此物品'}), 403

        now = datetime.datetime.now().isoformat()
        conn.execute(
            f'INSERT INTO player_appearance(user_id, {slot_col}, updated_at)'
            f' VALUES(?, ?, ?)'
            f' ON CONFLICT(user_id) DO UPDATE SET'
            f' {slot_col}=excluded.{slot_col}, updated_at=excluded.updated_at',
            (uid, item_id, now)
        )
        conn.commit()

    return jsonify({'ok': True, 'slot': item['slot'], 'item_id': item_id})


@app.route('/api/leaderboard')
@login_required
def leaderboard():
    uid   = session['user_id']
    today = datetime.date.today()
    month_start = today.replace(day=1).isoformat()
    month_label = today.strftime('%Y 年 %m 月')

    with get_db() as conn:
        rows = conn.execute(
            """SELECT u.id, u.username,
                      COUNT(*)                                       AS total,
                      SUM(CASE WHEN r.grade>=3 THEN 1 ELSE 0 END)   AS correct,
                      MAX(DATE(r.reviewed_at))                        AS last_active,
                      COALESCE(us.xp, 0)                             AS xp,
                      COALESCE(us.rank_level, '30k')                 AS rank_level,
                      COALESCE(us.max_combo, 0)                      AS max_combo
               FROM review_log r
               JOIN users u ON u.id = r.user_id
               LEFT JOIN user_stats us ON us.user_id = u.id
               WHERE DATE(r.reviewed_at) >= ?
               GROUP BY u.id
               ORDER BY correct DESC, total ASC
               LIMIT 50""",
            (month_start,)
        ).fetchall()

    board = []
    my_rank = None
    for i, r in enumerate(rows, 1):
        acc = round(r['correct'] / r['total'] * 100, 1) if r['total'] > 0 else 0
        is_me = (r['id'] == uid)
        if is_me:
            my_rank = i
        board.append({
            'rank':        i,
            'username':    r['username'],
            'correct':     r['correct'],
            'total':       r['total'],
            'accuracy':    acc,
            'last_active': r['last_active'] or '',
            'is_me':       is_me,
            'xp':          r['xp'],
            'rank_level':  r['rank_level'],
            'max_combo':   r['max_combo'],
        })

    return jsonify({'month': month_label, 'board': board, 'my_rank': my_rank})


# ══════════════════════════════════════════════════════════════
# 社群 API
# ══════════════════════════════════════════════════════════════

@app.route('/api/community/leaderboard')
@login_required
def community_leaderboard():
    uid   = session['user_id']
    today = datetime.date.today()

    with sqlite3.connect(SRS_DB) as conn:
        conn.row_factory = sqlite3.Row

        # ── 週排行：本週答對次數 ──
        week_start = (today - datetime.timedelta(days=today.weekday())).isoformat()
        weekly_rows = conn.execute("""
            SELECT u.id, u.username, COALESCE(u.nickname,u.username) AS display_name,
                   COUNT(*) AS score, COALESCE(s.rank_level,'LV1') AS rank_level
            FROM review_log rl
            JOIN users u ON u.id = rl.user_id
            LEFT JOIN user_stats s ON s.user_id = u.id
            WHERE rl.reviewed_at >= ? AND rl.grade >= 3
            GROUP BY u.id ORDER BY score DESC LIMIT 50
        """, (week_start,)).fetchall()

        # ── 月排行：本月答對次數 ──
        month_start = today.replace(day=1).isoformat()
        monthly_rows = conn.execute("""
            SELECT u.id, u.username, COALESCE(u.nickname,u.username) AS display_name,
                   COUNT(*) AS score, COALESCE(s.rank_level,'LV1') AS rank_level
            FROM review_log rl
            JOIN users u ON u.id = rl.user_id
            LEFT JOIN user_stats s ON s.user_id = u.id
            WHERE rl.reviewed_at >= ? AND rl.grade >= 3
            GROUP BY u.id ORDER BY score DESC LIMIT 50
        """, (month_start,)).fetchall()

        # ── 總排行：累計 XP ──
        alltime_rows = conn.execute("""
            SELECT u.id, u.username, COALESCE(u.nickname,u.username) AS display_name,
                   s.xp AS score, s.rank_level AS rank_level,
                   s.total_correct, s.max_combo
            FROM user_stats s
            JOIN users u ON u.id = s.user_id
            ORDER BY s.xp DESC LIMIT 50
        """).fetchall()

        # ── 段位排行 ──
        rank_rows = conn.execute("""
            SELECT u.id, u.username, COALESCE(u.nickname,u.username) AS display_name,
                   s.rank_level, s.rank_xp, s.xp AS score
            FROM user_stats s
            JOIN users u ON u.id = s.user_id
            ORDER BY s.xp DESC
            LIMIT 50
        """).fetchall()

        # ── 連勝排行：最高 combo ──
        combo_rows = conn.execute("""
            SELECT u.id, u.username, COALESCE(u.nickname,u.username) AS display_name,
                   s.max_combo AS score, COALESCE(s.rank_level,'LV1') AS rank_level
            FROM user_stats s
            JOIN users u ON u.id = s.user_id
            WHERE s.max_combo > 0
            ORDER BY s.max_combo DESC LIMIT 50
        """).fetchall()

        # ── 好友排行 ──
        frows = conn.execute("""
            SELECT CASE WHEN from_user=? THEN to_user ELSE from_user END AS fid
            FROM friendships WHERE (from_user=? OR to_user=?) AND status='accepted'
        """, (uid, uid, uid)).fetchall()
        fids = list({r['fid'] for r in frows} | {uid})
        friends_rows = conn.execute("""
            SELECT u.id, u.username, COALESCE(u.nickname,u.username) AS display_name,
                   s.xp AS score, s.rank_level,
                   s.total_correct, s.max_combo
            FROM user_stats s JOIN users u ON u.id = s.user_id
            WHERE u.id IN ({ph})
            ORDER BY s.xp DESC LIMIT 50
        """.format(ph=','.join('?'*len(fids))), fids).fetchall()

    def fmt(rows):
        out = []
        for i, r in enumerate(rows, 1):
            entry = {
                'rank': i,
                'username': r['username'],
                'display_name': r['display_name'] if 'display_name' in r.keys() else r['username'],
                'score': r['score'] or 0,
                'is_you': r['id'] == uid,
            }
            if 'rank_level' in r.keys():
                entry['rank_level'] = r['rank_level'] or '30k'
            if 'total_correct' in r.keys():
                entry['total_correct'] = r['total_correct'] or 0
            if 'max_combo' in r.keys():
                entry['max_combo'] = r['max_combo'] or 0
            if 'rank_xp' in r.keys():
                entry['rank_xp'] = r['rank_xp'] or 0
            out.append(entry)
        return out

    return jsonify({
        'weekly':  fmt(weekly_rows),
        'monthly': fmt(monthly_rows),
        'alltime': fmt(alltime_rows),
        'rank':    fmt(rank_rows),
        'combo':   fmt(combo_rows),
        'friends': fmt(friends_rows),
    })


@app.route('/api/comments/<int:qid>')
@login_required
def get_comments(qid):
    """取得指定題目的討論留言。"""
    uid = session['user_id']
    with sqlite3.connect(SRS_DB) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT c.id, c.content, c.created_at, c.likes, c.user_id,
                   u.username, COALESCE(u.nickname, u.username) AS display_name,
                   COALESCE(pa.av_type,'') AS av_type,
                   COALESCE(pa.av_value,'') AS av_value
            FROM question_comments c
            JOIN users u ON u.id = c.user_id
            LEFT JOIN player_appearance pa ON pa.user_id = c.user_id
            WHERE c.question_id = ?
            ORDER BY c.created_at DESC
            LIMIT 100
        """, (qid,)).fetchall()

        # 查這位用戶按過哪些讚
        liked_ids = set()
        if rows:
            cids = [r['id'] for r in rows]
            ph = ','.join('?' * len(cids))
            liked_rows = conn.execute(
                f'SELECT comment_id FROM comment_likes WHERE user_id=? AND comment_id IN ({ph})',
                [uid] + cids
            ).fetchall()
            liked_ids = {r['comment_id'] for r in liked_rows}

    comments = []
    for r in rows:
        comments.append({
            'id':           r['id'],
            'content':      r['content'],
            'created_at':   r['created_at'],
            'likes':        r['likes'],
            'liked':        r['id'] in liked_ids,
            'is_mine':      r['user_id'] == uid,
            'username':     r['username'],
            'display_name': r['display_name'],
            'av_type':      r['av_type'] or None,
            'av_value':     r['av_value'] or None,
        })
    return jsonify({'comments': comments, 'total': len(comments)})


@app.route('/api/comments/<int:qid>', methods=['POST'])
@login_required
def post_comment(qid):
    """在指定題目下發表留言。"""
    uid  = session['user_id']
    data = request.get_json() or {}
    content = (data.get('content') or '').strip()
    if not content:
        return jsonify({'error': '留言不能為空'}), 400
    if len(content) > 500:
        return jsonify({'error': '留言最多 500 字'}), 400
    now = datetime.datetime.now().isoformat()
    with sqlite3.connect(SRS_DB) as conn:
        conn.execute(
            'INSERT INTO question_comments(question_id, user_id, content, created_at) VALUES(?,?,?,?)',
            (qid, uid, content, now)
        )
        conn.commit()
    return jsonify({'ok': True})


@app.route('/api/comments/<int:comment_id>/like', methods=['POST'])
@login_required
def like_comment(comment_id):
    """按讚或取消讚。"""
    uid = session['user_id']
    with sqlite3.connect(SRS_DB) as conn:
        existing = conn.execute(
            'SELECT 1 FROM comment_likes WHERE user_id=? AND comment_id=?',
            (uid, comment_id)
        ).fetchone()
        if existing:
            conn.execute('DELETE FROM comment_likes WHERE user_id=? AND comment_id=?', (uid, comment_id))
            conn.execute('UPDATE question_comments SET likes=MAX(0,likes-1) WHERE id=?', (comment_id,))
            liked = False
        else:
            conn.execute('INSERT INTO comment_likes(user_id, comment_id) VALUES(?,?)', (uid, comment_id))
            conn.execute('UPDATE question_comments SET likes=likes+1 WHERE id=?', (comment_id,))
            liked = True
        conn.commit()
        row = conn.execute('SELECT likes FROM question_comments WHERE id=?', (comment_id,)).fetchone()
    return jsonify({'ok': True, 'liked': liked, 'likes': row[0] if row else 0})


@app.route('/api/comments/<int:comment_id>', methods=['DELETE'])
@login_required
def delete_comment(comment_id):
    """刪除自己的留言（或管理員可刪任何人的）。"""
    uid = session['user_id']
    is_admin = session.get('is_admin', False)
    with sqlite3.connect(SRS_DB) as conn:
        row = conn.execute('SELECT user_id FROM question_comments WHERE id=?', (comment_id,)).fetchone()
        if not row:
            return jsonify({'error': 'not found'}), 404
        if row[0] != uid and not is_admin:
            return jsonify({'error': 'forbidden'}), 403
        conn.execute('DELETE FROM question_comments WHERE id=?', (comment_id,))
        conn.execute('DELETE FROM comment_likes WHERE comment_id=?', (comment_id,))
        conn.commit()
    return jsonify({'ok': True})


@app.route('/api/community/tournament')
@login_required
def community_tournament():
    return jsonify({'current': None})


@app.route('/api/tournament/join', methods=['POST'])
@login_required
def tournament_join():
    """錦標賽報名（stub — 尚未實作真實錦標賽邏輯）。"""
    return jsonify({'ok': True})


@app.route('/api/community/reviews')
@login_required
def community_reviews():
    with sqlite3.connect(SRS_DB) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT sl.id, sl.share_token, sl.title, sl.stats_json, sl.view_count,
                   sl.created_at, u.username, COALESCE(u.nickname,u.username) AS display_name
            FROM share_links sl
            JOIN users u ON u.id = sl.user_id
            ORDER BY sl.created_at DESC LIMIT 30
        """).fetchall()
    items = []
    for r in rows:
        try:
            stats = json.loads(r['stats_json'] or '{}')
        except Exception:
            stats = {}
        items.append({
            'id':          r['id'],
            'token':       r['share_token'],
            'url':         f"/share/{r['share_token']}",
            'title':       r['title'] or f"{r['username']} 的複盤",
            'username':    r['username'],
            'display_name': r['display_name'],
            'description': stats.get('description', ''),
            'view_count':  r['view_count'] or 0,
            'created_at':  (r['created_at'] or '')[:10],
            'avatar':      '棋',
        })
    return jsonify({'items': items})


@app.route('/api/profile/<username>')
def public_profile(username):
    """公開個人檔案 API — 任何人都能查看。"""
    with sqlite3.connect(SRS_DB) as conn:
        conn.row_factory = sqlite3.Row

        user = conn.execute(
            'SELECT id, username, nickname, created_at FROM users WHERE username=? COLLATE NOCASE',
            (username,)
        ).fetchone()
        if not user:
            return jsonify({'error': 'user not found'}), 404

        uid = user['id']

        # ── 統計 ──
        stats = conn.execute(
            '''SELECT total_correct, current_streak, max_streak,
                      mistake_corrected, xp, combo_streak, max_combo,
                      rank_level, rank_xp
               FROM user_stats WHERE user_id=?''', (uid,)
        ).fetchone()

        total_correct     = stats['total_correct']     if stats else 0
        current_streak    = stats['current_streak']    if stats else 0
        max_streak        = stats['max_streak']        if stats else 0
        mistake_corrected = stats['mistake_corrected'] if stats else 0
        xp                = stats['xp']                if stats else 0
        max_combo         = stats['max_combo']         if stats else 0
        rank_level        = stats['rank_level']        if stats else '20k'
        rank_xp           = stats['rank_xp']           if stats else 0

        level = _rank_to_lv(rank_level)

        xp_next = RANK_XP_THRESHOLDS.get(rank_level, 999)

        # ── 答題總數 & 正確率 ──
        review_row = conn.execute(
            '''SELECT COUNT(*) AS total,
                      SUM(CASE WHEN grade >= 3 THEN 1 ELSE 0 END) AS correct
               FROM review_log WHERE user_id=?''', (uid,)
        ).fetchone()
        total_reviews = review_row['total'] if review_row else 0
        total_correct_reviews = review_row['correct'] if review_row else 0
        accuracy = round(total_correct_reviews / total_reviews * 100, 1) if total_reviews > 0 else 0

        # ── 已獲得的徽章 ──
        badge_rows = conn.execute(
            'SELECT badge_id, earned_at FROM badges_earned WHERE user_id=? ORDER BY earned_at',
            (uid,)
        ).fetchall()
        badge_map = {b['id']: b for b in BADGE_DEFS}
        badges = []
        for br in badge_rows:
            bd = badge_map.get(br['badge_id'])
            if bd:
                badges.append({
                    'id':        bd['id'],
                    'name':      bd['name'],
                    'icon':      bd['icon'],
                    'desc':      bd['desc'],
                    'earned_at': (br['earned_at'] or '')[:10],
                })

        # ── 頭像 ──
        eq_row = conn.execute(
            'SELECT av_type, av_value FROM player_appearance WHERE user_id=?', (uid,)
        ).fetchone()

        # ── 加入天數 ──
        join_date = (user['created_at'] or '')[:10]
        try:
            days = (datetime.date.today() - datetime.date.fromisoformat(join_date)).days
        except Exception:
            days = 0

    nickname = user['nickname'] if 'nickname' in user.keys() else None

    # ── 好友狀態（若有登入）──
    friend_status = 'none'
    friendship_id = None
    viewer_uid = session.get('user_id')
    if viewer_uid and viewer_uid != uid:
        with sqlite3.connect(SRS_DB) as conn2:
            conn2.row_factory = sqlite3.Row
            frow = conn2.execute('''
                SELECT id, status, from_user FROM friendships
                WHERE (from_user=? AND to_user=?) OR (from_user=? AND to_user=?)
            ''', (viewer_uid, uid, uid, viewer_uid)).fetchone()
            if frow:
                if frow['status'] == 'accepted':
                    friend_status = 'friends'
                elif frow['from_user'] == viewer_uid:
                    friend_status = 'pending_sent'
                else:
                    friend_status = 'pending_received'
                friendship_id = frow['id']
    elif viewer_uid and viewer_uid == uid:
        friend_status = 'self'

    return jsonify({
        'username':       user['username'],
        'nickname':       nickname or '',
        'display_name':   nickname or user['username'],
        'friend_status':  friend_status,
        'friendship_id':  friendship_id,
        'join_date':      join_date,
        'days':           days,
        'level':          level,
        'rank_level':     rank_level,
        'rank_xp':        rank_xp,
        'xp_next':        xp_next,
        'xp':             xp,
        'total_correct':  total_correct,
        'total_reviews':  total_reviews,
        'accuracy':       accuracy,
        'current_streak': current_streak,
        'max_streak':     max_streak,
        'max_combo':      max_combo,
        'mistake_corrected': mistake_corrected,
        'badges':         badges,
        'badge_count':    len(badges),
        'badge_total':    len(BADGE_DEFS),
        'av_type':        eq_row['av_type']  if eq_row else None,
        'av_value':       eq_row['av_value'] if eq_row else None,
    })


# ═══════════════════════════════════════════════════════════════
#  好友系統 API
# ═══════════════════════════════════════════════════════════════

@app.route('/api/friends/request', methods=['POST'])
@login_required
def friend_request():
    """發送好友邀請。"""
    uid  = session['user_id']
    data = request.get_json() or {}
    target = (data.get('username') or '').strip()
    if not target:
        return jsonify({'error': '請指定用戶名'}), 400

    with get_db() as conn:
        conn.row_factory = sqlite3.Row
        trow = conn.execute('SELECT id FROM users WHERE username=? COLLATE NOCASE', (target,)).fetchone()
        if not trow:
            return jsonify({'error': '找不到該用戶'}), 404
        tid = trow['id']
        if tid == uid:
            return jsonify({'error': '不能加自己為好友'}), 400

        # 檢查是否已存在任何方向的關係
        existing = conn.execute('''
            SELECT id, status, from_user FROM friendships
            WHERE (from_user=? AND to_user=?) OR (from_user=? AND to_user=?)
        ''', (uid, tid, tid, uid)).fetchone()

        if existing:
            if existing['status'] == 'accepted':
                return jsonify({'error': '你們已經是好友了'}), 400
            if existing['from_user'] == uid:
                return jsonify({'error': '已經發送過邀請，請等待對方回應'}), 400
            # 對方曾邀請我 → 直接接受
            conn.execute("UPDATE friendships SET status='accepted' WHERE id=?", (existing['id'],))
            conn.commit()
            return jsonify({'ok': True, 'message': '已成為好友！'})

        now = datetime.datetime.now().isoformat()
        conn.execute('INSERT INTO friendships(from_user,to_user,status,created_at) VALUES(?,?,?,?)',
                     (uid, tid, 'pending', now))
        conn.commit()
    return jsonify({'ok': True, 'message': '好友邀請已發送'})


@app.route('/api/friends/accept/<int:fid>', methods=['POST'])
@login_required
def friend_accept(fid):
    """接受好友邀請。"""
    uid = session['user_id']
    with get_db() as conn:
        row = conn.execute('SELECT id, to_user, status FROM friendships WHERE id=?', (fid,)).fetchone()
        if not row or row[1] != uid or row[2] != 'pending':
            return jsonify({'error': '無效的邀請'}), 400
        conn.execute("UPDATE friendships SET status='accepted' WHERE id=?", (fid,))
        conn.commit()
    return jsonify({'ok': True})


@app.route('/api/friends/reject/<int:fid>', methods=['POST'])
@login_required
def friend_reject(fid):
    """拒絕或刪除好友。"""
    uid = session['user_id']
    with get_db() as conn:
        row = conn.execute('SELECT id, from_user, to_user FROM friendships WHERE id=?', (fid,)).fetchone()
        if not row or (row[1] != uid and row[2] != uid):
            return jsonify({'error': '無效的操作'}), 400
        conn.execute('DELETE FROM friendships WHERE id=?', (fid,))
        conn.commit()
    return jsonify({'ok': True})


@app.route('/api/friends/status/<username>')
@login_required
def friend_status(username):
    """查看與某用戶的好友狀態。"""
    uid = session['user_id']
    with get_db() as conn:
        conn.row_factory = sqlite3.Row
        trow = conn.execute('SELECT id FROM users WHERE username=? COLLATE NOCASE', (username,)).fetchone()
        if not trow:
            return jsonify({'status': 'none'})
        tid = trow['id']
        if tid == uid:
            return jsonify({'status': 'self'})
        row = conn.execute('''
            SELECT id, status, from_user FROM friendships
            WHERE (from_user=? AND to_user=?) OR (from_user=? AND to_user=?)
        ''', (uid, tid, tid, uid)).fetchone()
        if not row:
            return jsonify({'status': 'none'})
        if row['status'] == 'accepted':
            return jsonify({'status': 'friends', 'friendship_id': row['id']})
        if row['from_user'] == uid:
            return jsonify({'status': 'pending_sent', 'friendship_id': row['id']})
        return jsonify({'status': 'pending_received', 'friendship_id': row['id']})


@app.route('/api/friends/requests')
@login_required
def friend_requests():
    """取得待處理的好友邀請。"""
    uid = session['user_id']
    with get_db() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute('''
            SELECT f.id, f.from_user, f.created_at,
                   u.username, COALESCE(u.nickname, u.username) AS display_name,
                   s.rank_level, s.xp,
                   pa.av_type, pa.av_value
            FROM friendships f
            JOIN users u ON u.id = f.from_user
            LEFT JOIN user_stats s ON s.user_id = f.from_user
            LEFT JOIN player_appearance pa ON pa.user_id = f.from_user
            WHERE f.to_user=? AND f.status='pending'
            ORDER BY f.created_at DESC
        ''', (uid,)).fetchall()
    result = []
    for r in rows:
        result.append({
            'id': r['id'],
            'username': r['username'],
            'display_name': r['display_name'],
            'rank_level': r['rank_level'] or '30k',
            'xp': r['xp'] or 0,
            'av_type': r['av_type'],
            'av_value': r['av_value'],
            'created_at': r['created_at'],
        })
    return jsonify({'requests': result, 'count': len(result)})


@app.route('/api/friends/list')
@login_required
def friend_list():
    """取得好友列表 + 好友動態。"""
    uid = session['user_id']
    with get_db() as conn:
        conn.row_factory = sqlite3.Row

        # ── 好友列表（含統計）──
        friends = conn.execute('''
            SELECT u.id, u.username, COALESCE(u.nickname, u.username) AS display_name,
                   f.id AS friendship_id,
                   s.xp, s.rank_level, s.total_correct, s.max_combo,
                   s.current_streak, s.combo_streak,
                   pa.av_type, pa.av_value
            FROM friendships f
            JOIN users u ON u.id = CASE WHEN f.from_user=? THEN f.to_user ELSE f.from_user END
            LEFT JOIN user_stats s ON s.user_id = u.id
            LEFT JOIN player_appearance pa ON pa.user_id = u.id
            WHERE (f.from_user=? OR f.to_user=?) AND f.status='accepted'
            ORDER BY s.xp DESC
        ''', (uid, uid, uid)).fetchall()

        friend_list = []
        fids = [uid]
        for r in friends:
            fids.append(r['id'])
            friend_list.append({
                'id': r['id'],
                'friendship_id': r['friendship_id'],
                'username': r['username'],
                'display_name': r['display_name'],
                'xp': r['xp'] or 0,
                'rank_level': r['rank_level'] or '30k',
                'total_correct': r['total_correct'] or 0,
                'max_combo': r['max_combo'] or 0,
                'current_streak': r['current_streak'] or 0,
                'combo_streak': r['combo_streak'] or 0,
                'av_type': r['av_type'],
                'av_value': r['av_value'],
            })

        # ── 好友動態（多種事件類型）──
        ph = ','.join('?' * len(fids))
        friend_only = [f for f in fids if f != uid]
        if not friend_only:
            friend_only = [0]   # dummy
        ph2 = ','.join('?' * len(friend_only))

        feed = []

        # 1) 每日答題摘要（按用戶+日期聚合，最近 7 天）
        daily_rows = conn.execute('''
            SELECT r.user_id,
                   DATE(r.reviewed_at) AS day,
                   COUNT(*) AS total,
                   SUM(CASE WHEN r.grade >= 3 THEN 1 ELSE 0 END) AS correct,
                   MAX(r.reviewed_at) AS last_at,
                   u.username, COALESCE(u.nickname, u.username) AS display_name,
                   pa.av_type, pa.av_value
            FROM review_log r
            JOIN users u ON u.id = r.user_id
            LEFT JOIN player_appearance pa ON pa.user_id = r.user_id
            WHERE r.user_id IN ({ph2})
              AND r.reviewed_at >= DATE('now', '-7 days')
            GROUP BY r.user_id, DATE(r.reviewed_at)
            ORDER BY last_at DESC
            LIMIT 30
        '''.format(ph2=ph2), friend_only).fetchall()
        for a in daily_rows:
            feed.append({
                'type': 'daily_summary',
                'username': a['username'],
                'display_name': a['display_name'],
                'total': a['total'],
                'correct': a['correct'],
                'day': a['day'],
                'created_at': a['last_at'],
                'av_type': a['av_type'],
                'av_value': a['av_value'],
            })

        # 2) 獲得新徽章
        badge_map = {b['id']: b for b in BADGE_DEFS}
        badge_rows = conn.execute('''
            SELECT be.user_id, be.badge_id, be.earned_at,
                   u.username, COALESCE(u.nickname, u.username) AS display_name,
                   pa.av_type, pa.av_value
            FROM badges_earned be
            JOIN users u ON u.id = be.user_id
            LEFT JOIN player_appearance pa ON pa.user_id = be.user_id
            WHERE be.user_id IN ({ph2})
              AND be.earned_at >= DATE('now', '-30 days')
            ORDER BY be.earned_at DESC
            LIMIT 20
        '''.format(ph2=ph2), friend_only).fetchall()
        for b in badge_rows:
            bd = badge_map.get(b['badge_id'])
            if not bd:
                continue
            feed.append({
                'type': 'badge',
                'username': b['username'],
                'display_name': b['display_name'],
                'badge_name': bd['name'],
                'badge_icon': bd['icon'],
                'badge_desc': bd['desc'],
                'created_at': b['earned_at'],
                'av_type': b['av_type'],
                'av_value': b['av_value'],
            })

        # 3) 段位晉升（從 user_stats 查最高段位，標記高段位好友）
        # — 暫時用 rank_level 靜態顯示，未來可加 rank_history 表

        # 依時間排序
        feed.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        feed = feed[:40]

        # ── 待處理邀請數 ──
        pending = conn.execute(
            "SELECT COUNT(*) FROM friendships WHERE to_user=? AND status='pending'", (uid,)
        ).fetchone()[0]

    return jsonify({
        'friends': friend_list,
        'feed': feed,
        'pending_count': pending,
    })


# ═══════════════════════════════════════════════════════════════
#  好友挑戰 API
# ═══════════════════════════════════════════════════════════════

@app.route('/api/challenges/friend/create', methods=['POST'])
@login_required
def friend_challenge_create():
    """發起好友挑戰：隨機選 N 題，雙方作答比正確率。"""
    uid  = session['user_id']
    data = request.get_json() or {}
    target_username = (data.get('username') or '').strip()
    num = min(max(int(data.get('num_questions', 10)), 5), 20)

    if not target_username:
        return jsonify({'error': '請指定挑戰對象'}), 400

    with get_db() as conn:
        conn.row_factory = sqlite3.Row
        trow = conn.execute('SELECT id FROM users WHERE username=? COLLATE NOCASE',
                            (target_username,)).fetchone()
        if not trow:
            return jsonify({'error': '找不到該用戶'}), 404
        tid = trow['id']
        if tid == uid:
            return jsonify({'error': '不能挑戰自己'}), 400

        # 確認是好友
        fr = conn.execute('''
            SELECT id FROM friendships
            WHERE ((from_user=? AND to_user=?) OR (from_user=? AND to_user=?))
              AND status='accepted'
        ''', (uid, tid, tid, uid)).fetchone()
        if not fr:
            return jsonify({'error': '只能挑戰好友'}), 400

        # 檢查是否有進行中的挑戰
        existing = conn.execute('''
            SELECT id FROM friend_challenges
            WHERE ((from_user=? AND to_user=?) OR (from_user=? AND to_user=?))
              AND status IN ('pending','active')
        ''', (uid, tid, tid, uid)).fetchone()
        if existing:
            return jsonify({'error': '你們之間已有進行中的挑戰'}), 400

        # 隨機選題（只從已啟用題目中選）
        qs = [q for q in _load_questions() if q.get('enabled', True)]
        if len(qs) < num:
            return jsonify({'error': '題庫不足'}), 400
        import random
        chosen = random.sample(qs, num)
        qids = [q['id'] for q in chosen]

        now = datetime.datetime.now()
        expires = (now + datetime.timedelta(days=3)).isoformat()
        conn.execute('''
            INSERT INTO friend_challenges(from_user, to_user, status, question_ids,
                                          num_questions, created_at, expires_at)
            VALUES(?,?,'pending',?,?,?,?)
        ''', (uid, tid, json.dumps(qids), num, now.isoformat(), expires))
        conn.commit()

    return jsonify({'ok': True, 'message': f'已向 {target_username} 發起 {num} 題挑戰！'})


@app.route('/api/challenges/friend/accept/<int:cid>', methods=['POST'])
@login_required
def friend_challenge_accept(cid):
    uid = session['user_id']
    with get_db() as conn:
        row = conn.execute('SELECT id, to_user, status FROM friend_challenges WHERE id=?',
                           (cid,)).fetchone()
        if not row or row[1] != uid or row[2] != 'pending':
            return jsonify({'error': '無效的挑戰'}), 400
        conn.execute("UPDATE friend_challenges SET status='active' WHERE id=?", (cid,))
        conn.commit()
    return jsonify({'ok': True})


@app.route('/api/challenges/friend/reject/<int:cid>', methods=['POST'])
@login_required
def friend_challenge_reject(cid):
    uid = session['user_id']
    with get_db() as conn:
        row = conn.execute('SELECT id, from_user, to_user, status FROM friend_challenges WHERE id=?',
                           (cid,)).fetchone()
        if not row or (row[1] != uid and row[2] != uid):
            return jsonify({'error': '無效的操作'}), 400
        conn.execute("UPDATE friend_challenges SET status='cancelled' WHERE id=?", (cid,))
        conn.commit()
    return jsonify({'ok': True})


@app.route('/api/challenges/friend/<int:cid>')
@login_required
def friend_challenge_detail(cid):
    """取得挑戰詳情：題目、雙方進度。"""
    uid = session['user_id']
    with get_db() as conn:
        conn.row_factory = sqlite3.Row
        ch = conn.execute('''
            SELECT fc.*, u1.username AS from_username,
                   COALESCE(u1.nickname, u1.username) AS from_display,
                   u2.username AS to_username,
                   COALESCE(u2.nickname, u2.username) AS to_display
            FROM friend_challenges fc
            JOIN users u1 ON u1.id = fc.from_user
            JOIN users u2 ON u2.id = fc.to_user
            WHERE fc.id=?
        ''', (cid,)).fetchone()
        if not ch or (ch['from_user'] != uid and ch['to_user'] != uid):
            return jsonify({'error': '找不到此挑戰'}), 404

        qids = json.loads(ch['question_ids'])

        # 自動過期檢查
        status = ch['status']
        if status in ('pending', 'active') and ch['expires_at'] < datetime.datetime.now().isoformat():
            conn.execute("UPDATE friend_challenges SET status='expired' WHERE id=?", (cid,))
            conn.commit()
            status = 'expired'

        # 雙方作答情況
        my_answers = {}
        opp_answers = {}
        opp_uid = ch['to_user'] if ch['from_user'] == uid else ch['from_user']
        rows = conn.execute(
            'SELECT user_id, question_id, correct FROM friend_challenge_answers WHERE challenge_id=?',
            (cid,)).fetchall()
        for r in rows:
            if r['user_id'] == uid:
                my_answers[r['question_id']] = r['correct']
            else:
                opp_answers[r['question_id']] = r['correct']

        # 題目列表 + 答題狀態
        all_qs = {q['id']: q for q in _load_questions()}
        questions = []
        for qid in qids:
            q = all_qs.get(qid, {})
            questions.append({
                'id': qid,
                'difficulty': q.get('difficulty', ''),
                'my_answer': my_answers.get(qid),        # None=未答, 0=錯, 1=對
                'opp_answer': opp_answers.get(qid),
            })

        my_correct = sum(1 for v in my_answers.values() if v)
        opp_correct = sum(1 for v in opp_answers.values() if v)
        my_done = len(my_answers) >= len(qids)
        opp_done = len(opp_answers) >= len(qids)

        # 雙方都答完 → 自動結算
        if status == 'active' and my_done and opp_done:
            conn.execute("UPDATE friend_challenges SET status='completed' WHERE id=?", (cid,))
            conn.commit()
            status = 'completed'

    is_from = ch['from_user'] == uid
    return jsonify({
        'id': cid,
        'status': status,
        'from_user': {'username': ch['from_username'], 'display_name': ch['from_display']},
        'to_user':   {'username': ch['to_username'],   'display_name': ch['to_display']},
        'num_questions': ch['num_questions'],
        'questions': questions,
        'my_correct': my_correct,
        'my_total': len(my_answers),
        'opp_correct': opp_correct,
        'opp_total': len(opp_answers),
        'my_done': my_done,
        'opp_done': opp_done,
        'is_challenger': is_from,
        'created_at': ch['created_at'],
        'expires_at': ch['expires_at'],
    })


# 好友挑戰寶物掉落表：(累積機率, 物品名, 金幣數)
_CHALLENGE_TREASURE = [
    (0.40, None,    0),    # 40% 無掉落
    (0.30, '銅幣袋',  5),   # 30%   5 金幣
    (0.18, '銀幣袋', 15),   # 18%  15 金幣
    (0.09, '金幣袋', 30),   # 9%   30 金幣
    (0.03, '寶箱',  100),   # 3%  100 金幣
]

def _award_challenge_reward(conn, uid, my_correct, num_questions, both_done,
                             my_correct_final, opp_correct_final):
    """
    計算並發放好友挑戰獎勵。
    both_done=True 時才能判斷勝負，給予結果加成與徽章。
    回傳 dict：{xp, coins, treasure_name, result, new_badges}
    """
    import random as _random

    # ── 結果判斷 ────────────────────────────────────────────────
    result = None
    if both_done:
        if my_correct_final > opp_correct_final:
            result = 'win'
        elif my_correct_final < opp_correct_final:
            result = 'loss'
        else:
            result = 'draw'

    # ── XP ──────────────────────────────────────────────────────
    xp = my_correct * 5          # 每答對 1 題得 5 XP
    if both_done:
        if result == 'win':   xp += 30
        elif result == 'draw': xp += 10
        # 落敗不加，但已有答題 XP

    # ── 寶物掉落 ────────────────────────────────────────────────
    coins = 0
    treasure_name = None
    r = _random.random()
    cumul = 0.0
    for prob, name, amt in _CHALLENGE_TREASURE:
        cumul += prob
        if r < cumul:
            coins = amt
            treasure_name = name
            break

    # ── 更新 user_stats ─────────────────────────────────────────
    now = datetime.datetime.now().isoformat()
    stats_row = conn.execute(
        'SELECT * FROM user_stats WHERE user_id=?', (uid,)).fetchone()
    stats = dict(stats_row) if stats_row else {}

    chal_wins    = stats.get('challenge_wins', 0)
    chal_streak  = stats.get('challenge_win_streak', 0)
    max_streak   = stats.get('max_challenge_win_streak', 0)

    if both_done:
        if result == 'win':
            chal_wins   += 1
            chal_streak += 1
            if chal_streak > max_streak:
                max_streak = chal_streak
        elif result in ('loss', 'draw'):
            chal_streak = 0

    conn.execute('''
        INSERT INTO user_stats(user_id, xp, coins,
            challenge_wins, challenge_win_streak, max_challenge_win_streak, updated_at)
        VALUES(?,?,?,?,?,?,?)
        ON CONFLICT(user_id) DO UPDATE SET
            xp                       = xp + ?,
            coins                    = coins + ?,
            challenge_wins           = ?,
            challenge_win_streak     = ?,
            max_challenge_win_streak = ?,
            updated_at               = ?
    ''', (uid, xp, coins, chal_wins, chal_streak, max_streak, now,
          xp, coins, chal_wins, chal_streak, max_streak, now))

    # ── 徽章檢查 ─────────────────────────────────────────────────
    updated_stats = dict(stats)
    updated_stats['xp']                       = stats.get('xp', 0) + xp
    updated_stats['challenge_wins']           = chal_wins
    updated_stats['challenge_win_streak']     = chal_streak
    updated_stats['max_challenge_win_streak'] = max_streak

    new_bids = check_and_award(conn, uid, updated_stats)

    # 挑戰專屬徽章
    already = {r2['badge_id'] for r2 in conn.execute(
        'SELECT badge_id FROM badges_earned WHERE user_id=?', (uid,)).fetchall()}
    bnow = datetime.datetime.now().isoformat()
    for b in BADGE_DEFS:
        bid = b['id']
        if bid in already or bid in new_bids:
            continue
        if b['type'] == 'challenge_win' and chal_wins >= b['value']:
            conn.execute(
                'INSERT OR IGNORE INTO badges_earned(user_id,badge_id,earned_at,seen) VALUES(?,?,?,0)',
                (uid, bid, bnow))
            new_bids.append(bid)
        elif b['type'] == 'challenge_win_streak' and chal_streak >= b['value']:
            conn.execute(
                'INSERT OR IGNORE INTO badges_earned(user_id,badge_id,earned_at,seen) VALUES(?,?,?,0)',
                (uid, bid, bnow))
            new_bids.append(bid)

    badge_map = {b['id']: b for b in BADGE_DEFS}
    new_badges = [
        {'id': bid, 'name': badge_map[bid]['name'], 'icon': badge_map[bid]['icon']}
        for bid in new_bids if bid in badge_map
    ]

    return {
        'xp':           xp,
        'coins':        coins,
        'treasure_name': treasure_name,
        'result':       result,
        'new_badges':   new_badges,
    }


@app.route('/api/challenges/friend/<int:cid>/answer', methods=['POST'])
@login_required
def friend_challenge_answer(cid):
    """提交一道挑戰題的作答結果。"""
    uid  = session['user_id']
    data = request.get_json() or {}
    qid  = data.get('question_id')
    correct = 1 if data.get('correct') else 0

    if qid is None:
        return jsonify({'error': '缺少 question_id'}), 400

    with get_db() as conn:
        conn.row_factory = sqlite3.Row
        ch = conn.execute('SELECT * FROM friend_challenges WHERE id=?', (cid,)).fetchone()
        if not ch or (ch['from_user'] != uid and ch['to_user'] != uid):
            return jsonify({'error': '找不到此挑戰'}), 404
        if ch['status'] not in ('active',):
            return jsonify({'error': '挑戰尚未開始或已結束'}), 400

        qids = json.loads(ch['question_ids'])
        if qid not in qids:
            return jsonify({'error': '此題不屬於本挑戰'}), 400

        # 防止重複作答
        existing = conn.execute(
            'SELECT 1 FROM friend_challenge_answers WHERE challenge_id=? AND user_id=? AND question_id=?',
            (cid, uid, qid)).fetchone()
        if existing:
            return jsonify({'error': '已經作答過此題'}), 400

        now = datetime.datetime.now().isoformat()
        conn.execute('''
            INSERT INTO friend_challenge_answers(challenge_id, user_id, question_id, correct, answered_at)
            VALUES(?,?,?,?,?)
        ''', (cid, uid, qid, correct, now))

        # 檢查是否雙方都答完
        total_answered = conn.execute(
            'SELECT COUNT(*) FROM friend_challenge_answers WHERE challenge_id=? AND user_id=?',
            (cid, uid)).fetchone()[0]
        opp_uid = ch['to_user'] if ch['from_user'] == uid else ch['from_user']
        opp_answered = conn.execute(
            'SELECT COUNT(*) FROM friend_challenge_answers WHERE challenge_id=? AND user_id=?',
            (cid, opp_uid)).fetchone()[0]

        both_done = (total_answered >= ch['num_questions'] and
                     opp_answered  >= ch['num_questions'])
        if both_done:
            conn.execute("UPDATE friend_challenges SET status='completed' WHERE id=?", (cid,))

        # ── 當玩家答完所有題目時發放獎勵 ─────────────────────────
        rewards = None
        if total_answered >= ch['num_questions']:
            my_correct = conn.execute(
                'SELECT COUNT(*) FROM friend_challenge_answers '
                'WHERE challenge_id=? AND user_id=? AND correct=1',
                (cid, uid)).fetchone()[0]
            opp_correct = conn.execute(
                'SELECT COUNT(*) FROM friend_challenge_answers '
                'WHERE challenge_id=? AND user_id=? AND correct=1',
                (cid, opp_uid)).fetchone()[0] if both_done else 0

            rewards = _award_challenge_reward(
                conn, uid,
                my_correct=my_correct,
                num_questions=ch['num_questions'],
                both_done=both_done,
                my_correct_final=my_correct,
                opp_correct_final=opp_correct,
            )

        conn.commit()

    return jsonify({'ok': True, 'my_total_answered': total_answered,
                    'rewards': rewards})


@app.route('/api/challenges/friend/list')
@login_required
def friend_challenge_list():
    """列出我的好友挑戰（待處理 + 進行中 + 最近完成）。"""
    uid = session['user_id']
    with get_db() as conn:
        conn.row_factory = sqlite3.Row

        # 自動過期
        now = datetime.datetime.now().isoformat()
        conn.execute("""
            UPDATE friend_challenges SET status='expired'
            WHERE status IN ('pending','active') AND expires_at < ?
        """, (now,))
        conn.commit()

        rows = conn.execute('''
            SELECT fc.*,
                   u1.username AS from_username,
                   COALESCE(u1.nickname, u1.username) AS from_display,
                   u2.username AS to_username,
                   COALESCE(u2.nickname, u2.username) AS to_display
            FROM friend_challenges fc
            JOIN users u1 ON u1.id = fc.from_user
            JOIN users u2 ON u2.id = fc.to_user
            WHERE (fc.from_user=? OR fc.to_user=?)
              AND fc.status IN ('pending','active','completed')
            ORDER BY
              CASE fc.status WHEN 'active' THEN 0 WHEN 'pending' THEN 1 ELSE 2 END,
              fc.created_at DESC
            LIMIT 20
        ''', (uid, uid)).fetchall()

        # 取得每個挑戰的作答進度
        challenges = []
        for ch in rows:
            cid = ch['id']
            qids = json.loads(ch['question_ids'])
            opp_uid = ch['to_user'] if ch['from_user'] == uid else ch['from_user']

            my_ans = conn.execute(
                'SELECT COUNT(*) AS c, SUM(correct) AS s FROM friend_challenge_answers WHERE challenge_id=? AND user_id=?',
                (cid, uid)).fetchone()
            opp_ans = conn.execute(
                'SELECT COUNT(*) AS c, SUM(correct) AS s FROM friend_challenge_answers WHERE challenge_id=? AND user_id=?',
                (cid, opp_uid)).fetchone()

            challenges.append({
                'id': cid,
                'status': ch['status'],
                'from_user': {'username': ch['from_username'], 'display_name': ch['from_display']},
                'to_user':   {'username': ch['to_username'],   'display_name': ch['to_display']},
                'num_questions': ch['num_questions'],
                'is_challenger': ch['from_user'] == uid,
                'my_answered': my_ans['c'] or 0,
                'my_correct':  my_ans['s'] or 0,
                'opp_answered': opp_ans['c'] or 0,
                'opp_correct':  opp_ans['s'] or 0,
                'created_at': ch['created_at'],
                'expires_at': ch['expires_at'],
            })

    return jsonify({'challenges': challenges})


@app.route('/api/community/reviews', methods=['POST'])
@login_required
def community_reviews_post():
    uid  = session['user_id']
    data = request.get_json() or {}
    title = (data.get('title') or '').strip()
    if not title:
        return jsonify({'error': '請填寫標題'}), 400
    token = secrets.token_urlsafe(10)
    stats = {'description': (data.get('description') or '').strip()}
    with sqlite3.connect(SRS_DB) as conn:
        conn.execute(
            'INSERT INTO share_links(user_id,share_token,title,stats_json,created_at) VALUES(?,?,?,?,?)',
            (uid, token, title, json.dumps(stats, ensure_ascii=False),
             datetime.datetime.now().isoformat())
        )
        conn.commit()
    return jsonify({'ok': True, 'token': token, 'url': f'/share/{token}'})


@app.route('/api/community/teachers')
@login_required
def community_teachers():
    with sqlite3.connect(SRS_DB) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT u.id, u.username, COUNT(ts.student_id) AS student_count
            FROM users u
            LEFT JOIN teacher_student ts ON ts.teacher_id = u.id
            WHERE u.is_admin = 1
            GROUP BY u.id ORDER BY student_count DESC
        """).fetchall()
    teachers = [{'id': r['id'], 'name': r['username'],
                 'rating': f"{r['student_count']} 位學生", 'avatar': '👨‍🏫'}
                for r in rows]
    return jsonify({'teachers': teachers})


# 靜態頁面
# ══════════════════════════════════════════════════════════════

@app.route('/login')
def login_page():
    if 'user_id' in session:
        return redirect('/')
    return send_from_directory('.', 'login.html')

@app.route('/')
def index():
    if 'user_id' not in session:
        return send_from_directory('.', 'landing.html')
    return send_from_directory('.', 'index.html')

@app.route('/landing')
def landing():
    return send_from_directory('.', 'landing.html')

@app.route('/manage')
@admin_required
def manage(): return send_from_directory('.','manage.html')

@app.route('/admin')
@admin_required
def admin_page(): return send_from_directory('.','admin.html')

# ══════════════════════════════════════════════════════════════
# GnuGo AI 陪練
# ══════════════════════════════════════════════════════════════
import random as _random_mod

# GnuGo 可執行檔路徑（找不到時顯示友善錯誤）
GNUGO_EXE = os.environ.get('GNUGO_EXE', 'gnugo')   # 可在環境變數中覆蓋
# 也支援放在專案目錄下的 gnugo.exe
_GNUGO_LOCAL = os.path.join(os.path.dirname(__file__), 'gnugo.exe')
if os.path.exists(_GNUGO_LOCAL):
    GNUGO_EXE = _GNUGO_LOCAL

# 進行中的對局：{ game_id: { proc, color, size, lock } }
_gnugo_games: dict = {}
_gnugo_lock = threading.Lock()

# GTP 座標字母表（跳過 I）
_GTP_COLS = 'ABCDEFGHJKLMNOPQRST'

def _xy_to_gtp(x: int, y: int, size: int) -> str:
    """WGo (x,y) → GTP 座標字串，e.g. (3,4) on 9×9 → 'D5'"""
    return _GTP_COLS[x] + str(size - y)

def _gtp_to_xy(gtp: str, size: int):
    """GTP 座標 → (x, y)，'PASS' → None"""
    gtp = gtp.strip().upper()
    if gtp in ('PASS', ''):
        return None
    col_ch = gtp[0]
    row_n  = int(gtp[1:])
    x = _GTP_COLS.index(col_ch)
    y = size - row_n
    return x, y

def _list_stones(proc, color_name: str, size: int) -> set:
    """回傳棋盤上指定顏色所有棋子的 (x,y) 集合。
    color_name: 'black' 或 'white'
    """
    resp = _gtp(proc, f'list_stones {color_name}')
    if not resp or not resp.strip():
        return set()
    stones = set()
    for coord in resp.strip().split():
        coord = coord.upper()
        if coord not in ('PASS', ''):
            xy = _gtp_to_xy(coord, size)
            if xy:
                stones.add(xy)
    return stones

def _gtp(proc, cmd: str):
    """
    送出 GTP 指令。
    成功 → 回傳回應字串（可能是空字串，如 play 指令）
    失敗 → 回傳 None
    """
    proc.stdin.write((cmd + '\n').encode())
    proc.stdin.flush()
    lines = []
    is_error = False
    while True:
        line = proc.stdout.readline().decode(errors='replace').rstrip('\n')
        if line.startswith('= '):
            lines.append(line[2:].strip())
        elif line == '=':
            lines.append('')          # 成功但無內容（play 指令常見）
        elif line.startswith('? ') or line == '?':
            is_error = True
            lines.append(line[2:].strip())
        elif line == '' and lines:
            break                     # 空行 = 回應結束
    if is_error:
        return None                   # 明確的失敗旗標
    return '\n'.join(lines)

def _start_gnugo(size: int, level: int, handicap: int, komi: float) -> subprocess.Popen:
    cmd = [GNUGO_EXE, '--mode', 'gtp',
           '--boardsize', str(size),
           '--level', str(level),
           '--komi', str(komi)]
    proc = subprocess.Popen(cmd,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    _gtp(proc, f'boardsize {size}')
    _gtp(proc, f'komi {komi}')
    if handicap > 1:
        _gtp(proc, f'fixed_handicap {handicap}')
    return proc

def _cleanup_gnugo(game_id: str):
    with _gnugo_lock:
        g = _gnugo_games.pop(game_id, None)
    if g:
        try:
            _gtp(g['proc'], 'quit')
            g['proc'].wait(timeout=2)
        except Exception:
            g['proc'].kill()


@app.route('/bot')
@login_required
def bot_page(): return send_from_directory('.', 'bot.html')


@app.route('/api/bot/new', methods=['POST'])
@login_required
def bot_new():
    """建立新的 GnuGo 對局"""
    data     = request.get_json() or {}
    size     = int(data.get('size', 9))
    level    = max(1, min(10, int(data.get('level', 5))))
    color    = data.get('color', 'B').upper()   # 玩家顏色
    handicap = int(data.get('handicap', 0))
    komi     = float(data.get('komi', 6.5))

    if size not in (9, 13, 19):
        return jsonify({'error': '棋盤大小必須是 9、13 或 19'}), 400
    if handicap > 0 and size < 13:
        handicap = 0   # 9路不設讓子

    try:
        proc = _start_gnugo(size, level, handicap, komi)
    except FileNotFoundError:
        return jsonify({'error': 'GnuGo 未安裝或路徑錯誤，請確認 gnugo.exe 存在於專案目錄'}), 500

    game_id = uuid.uuid4().hex
    ai_color = 'W' if color == 'B' else 'B'

    # 取得讓子棋子座標（供前端繪製）
    handicap_stones = []
    if handicap > 1:
        raw = _list_stones(proc, 'black', size)
        handicap_stones = [{'x': xy[0], 'y': xy[1]} for xy in sorted(raw)]

    with _gnugo_lock:
        _gnugo_games[game_id] = {
            'proc':      proc,
            'size':      size,
            'player':    color,
            'ai':        ai_color,
            'level':     level,
            'handicap':  handicap,
            'komi':      komi,
            'moves':     0,
            'ko_point':  None,   # 玩家下一手的禁著點（打劫）
            'lock':      threading.Lock(),
        }

    result = {'game_id': game_id, 'size': size, 'player_color': color,
              'ai_color': ai_color, 'level': level, 'komi': komi,
              'handicap': handicap, 'handicap_stones': handicap_stones}

    # 若玩家執白，GnuGo（黑）先走
    if color == 'W':
        g = _gnugo_games[game_id]
        with g['lock']:
            mv = _gtp(proc, f'genmove {ai_color}')
        if mv and mv.upper() != 'RESIGN':
            xy = _gtp_to_xy(mv, size)
            result['ai_first'] = {'gtp': mv.upper(), 'xy': xy}
            g['moves'] += 1

    return jsonify(result)


@app.route('/api/bot/move', methods=['POST'])
@login_required
def bot_move():
    """玩家落子，GnuGo 回應"""
    data    = request.get_json() or {}
    game_id = data.get('game_id')
    x       = data.get('x')
    y       = data.get('y')
    is_pass = data.get('pass', False)

    with _gnugo_lock:
        g = _gnugo_games.get(game_id)
    if not g:
        return jsonify({'error': '對局不存在'}), 404

    proc   = g['proc']
    size   = g['size']
    pcol   = g['player']
    acol   = g['ai']

    p_col_name = 'black' if pcol == 'B' else 'white'
    a_col_name = 'black' if acol == 'B' else 'white'

    with g['lock']:
        # ── 合法性預檢查（禁著點 / 打劫）──
        if not is_pass:
            try:
                x = int(x)
                y = int(y)
            except (TypeError, ValueError):
                return jsonify({'error': '座標錯誤，請重新點一次',
                                'error_type': 'bad_coord'}), 400
            if x < 0 or y < 0 or x >= size or y >= size:
                return jsonify({'error': '點到棋盤外了，請重新點一次',
                                'error_type': 'out_of_bounds'}), 400
            gtp_coord = _xy_to_gtp(x, y, size)
            occupied = _list_stones(proc, 'black', size) | _list_stones(proc, 'white', size)
            if (x, y) in occupied:
                return jsonify({'error': '此處已經有棋子',
                                'error_type': 'occupied'}), 400
            legal = _gtp(proc, f'is_legal {pcol} {gtp_coord}')
            if legal == '0':
                ko = g.get('ko_point')
                if ko and ko == (x, y):
                    return jsonify({'error': '打劫！不能立即回提',
                                    'error_type': 'ko'}), 400
                return jsonify({'error': '禁著點！此處落子後無氣',
                                'error_type': 'suicide'}), 400

        # ── 快照1：玩家落子前，對手的棋子集合 ──
        opp_before = _list_stones(proc, a_col_name, size)

        # 送出玩家的手
        if is_pass:
            _gtp(proc, f'play {pcol} PASS')
            g['ko_point'] = None   # 虛手清除打劫
        else:
            resp = _gtp(proc, f'play {pcol} {gtp_coord}')
            if resp is None:   # 理論上不會到這，保留保險
                return jsonify({'error': '非法落子'}), 400

        g['moves'] += 1

        # ── 快照2：玩家落子後 ──
        opp_after_player = _list_stones(proc, a_col_name, size)
        player_before_ai = _list_stones(proc, p_col_name, size)

        # GnuGo 回應
        ai_resp = _gtp(proc, f'genmove {acol}')
        ai_resp = ai_resp.upper().strip()

        # ── 快照3：AI 落子後 ──
        player_after_ai = _list_stones(proc, p_col_name, size)

    # 計算被吃的子
    player_captures = [{'x': xy[0], 'y': xy[1], 'c': acol}
                       for xy in (opp_before - opp_after_player)]
    ai_captures     = [{'x': xy[0], 'y': xy[1], 'c': pcol}
                       for xy in (player_before_ai - player_after_ai)]

    # 更新打劫點：AI 恰好吃 1 子 → 玩家下一手不能立即回提
    if len(ai_captures) == 1:
        g['ko_point'] = (ai_captures[0]['x'], ai_captures[0]['y'])
    else:
        g['ko_point'] = None
    ko_resp = {'x': g['ko_point'][0], 'y': g['ko_point'][1]} if g['ko_point'] else None

    result = {'ok': True, 'ai_move': ai_resp,
              'player_captures': player_captures,
              'ai_captures':     ai_captures,
              'ko_point':        ko_resp}

    if ai_resp == 'RESIGN':
        result['game_over'] = True
        result['winner']    = pcol
        result['reason']    = 'AI 認輸'
    elif ai_resp == 'PASS':
        result['ai_xy']  = None
        result['is_pass'] = True
    else:
        xy = _gtp_to_xy(ai_resp, size)
        result['ai_xy'] = {'x': xy[0], 'y': xy[1]} if xy else None

    g['moves'] += 1
    return jsonify(result)


@app.route('/api/bot/pass', methods=['POST'])
@login_required
def bot_pass():
    """玩家 Pass"""
    data    = request.get_json() or {}
    game_id = data.get('game_id')
    with _gnugo_lock:
        g = _gnugo_games.get(game_id)
    if not g:
        return jsonify({'error': '對局不存在'}), 404

    proc = g['proc']; size = g['size']; pcol = g['player']; acol = g['ai']
    p_col_name = 'black' if pcol == 'B' else 'white'

    with g['lock']:
        _gtp(proc, f'play {pcol} PASS')
        g['ko_point'] = None   # 虛手清除打劫
        g['moves'] += 1
        # 玩家 pass 不落子 → 只有 AI 落子後可能吃掉玩家的子
        player_before_ai = _list_stones(proc, p_col_name, size)
        ai_resp = _gtp(proc, f'genmove {acol}').upper().strip()
        player_after_ai  = _list_stones(proc, p_col_name, size)

    ai_captures = [{'x': xy[0], 'y': xy[1], 'c': pcol}
                   for xy in (player_before_ai - player_after_ai)]

    # 更新打劫點
    if len(ai_captures) == 1:
        g['ko_point'] = (ai_captures[0]['x'], ai_captures[0]['y'])
    else:
        g['ko_point'] = None
    ko_resp = {'x': g['ko_point'][0], 'y': g['ko_point'][1]} if g['ko_point'] else None

    result = {'ok': True, 'ai_move': ai_resp,
              'player_captures': [], 'ai_captures': ai_captures,
              'ko_point': ko_resp}
    if ai_resp == 'PASS':
        # 雙方都 pass → 可計分
        result['both_passed'] = True
        with g['lock']:
            score_str = _gtp(proc, 'final_score').strip()
        result['score'] = score_str
    elif ai_resp == 'RESIGN':
        result['game_over'] = True; result['winner'] = pcol
    else:
        xy = _gtp_to_xy(ai_resp, size)
        result['ai_xy'] = {'x': xy[0], 'y': xy[1]} if xy else None
    g['moves'] += 1
    return jsonify(result)


@app.route('/api/bot/undo', methods=['POST'])
@login_required
def bot_undo():
    """悔棋：撤回玩家最後一手 + AI 的回應（共 undo 2 步）"""
    data    = request.get_json() or {}
    game_id = data.get('game_id')
    with _gnugo_lock:
        g = _gnugo_games.get(game_id)
    if not g:
        return jsonify({'error': '對局不存在'}), 404

    proc = g['proc']
    size = g['size']

    with g['lock']:
        # undo 兩次（AI 的手 + 玩家的手）
        r1 = _gtp(proc, 'undo')
        r2 = _gtp(proc, 'undo')
        if r1 is None or r2 is None:
            return jsonify({'error': '目前無法悔棋（手數不足）'}), 400

        g['moves']    = max(0, g['moves'] - 2)
        g['ko_point'] = None   # 悔棋後清除打劫點

        # 重新取得雙方棋子位置
        black_stones = _list_stones(proc, 'black', size)
        white_stones = _list_stones(proc, 'white', size)

    return jsonify({
        'ok': True,
        'black_stones': [{'x': xy[0], 'y': xy[1]} for xy in sorted(black_stones)],
        'white_stones': [{'x': xy[0], 'y': xy[1]} for xy in sorted(white_stones)],
    })


@app.route('/api/bot/estimate', methods=['POST'])
@login_required
def bot_estimate():
    """中盤估分（GnuGo estimate_score）"""
    data    = request.get_json() or {}
    game_id = data.get('game_id')
    with _gnugo_lock:
        g = _gnugo_games.get(game_id)
    if not g:
        return jsonify({'error': '對局不存在'}), 404

    with g['lock']:
        resp = _gtp(g['proc'], 'estimate_score')

    return jsonify({'ok': True, 'estimate': resp.strip() if resp else '無法估算'})


@app.route('/api/bot/resign', methods=['POST'])
@login_required
def bot_resign():
    """玩家認輸"""
    data    = request.get_json() or {}
    game_id = data.get('game_id')
    _cleanup_gnugo(game_id)
    return jsonify({'ok': True, 'game_over': True, 'winner': 'AI'})


@app.route('/api/bot/score', methods=['POST'])
@login_required
def bot_score():
    """請求終局計分"""
    data    = request.get_json() or {}
    game_id = data.get('game_id')
    with _gnugo_lock:
        g = _gnugo_games.get(game_id)
    if not g:
        return jsonify({'error': '對局不存在'}), 404
    with g['lock']:
        score = _gtp(g['proc'], 'final_score').strip()
    return jsonify({'ok': True, 'score': score})


@app.route('/api/bot/end', methods=['POST'])
@login_required
def bot_end():
    """結束並清理對局"""
    data    = request.get_json() or {}
    game_id = data.get('game_id')
    _cleanup_gnugo(game_id)
    return jsonify({'ok': True})


@app.route('/api/quiz/gnugo', methods=['POST'])
@login_required
def quiz_gnugo():
    """做題探索模式：GnuGo 根據當前棋盤局面回一手（one-shot，不建立持久對局）"""
    data       = request.get_json() or {}
    board_size = int(data.get('boardSize', 9))
    black      = data.get('black', [])    # [{x, y}, ...]
    white      = data.get('white', [])    # [{x, y}, ...]
    player     = data.get('player', 'B').upper()   # GnuGo 要下的顏色
    level      = max(1, min(10, int(data.get('level', 5))))

    if board_size not in (9, 13, 19):
        return jsonify({'error': '棋盤大小無效'}), 400

    proc = None
    try:
        proc = _start_gnugo(board_size, level, 0, 0.5)

        # 將黑白棋子逐一用 play 指令佈置（顯式指定顏色，不依賴輪換）
        for s in black:
            _gtp(proc, f'play B {_xy_to_gtp(s["x"], s["y"], board_size)}')
        for s in white:
            _gtp(proc, f'play W {_xy_to_gtp(s["x"], s["y"], board_size)}')

        # 生成回應手
        resp = _gtp(proc, f'genmove {player}')
        if not resp:
            return jsonify({'error': 'GnuGo 無回應'}), 500

        resp = resp.strip().upper()
        if resp in ('PASS', 'RESIGN', ''):
            return jsonify({'ok': True, 'pass': True})

        xy = _gtp_to_xy(resp, board_size)
        if not xy:
            return jsonify({'ok': True, 'pass': True})

        return jsonify({'ok': True, 'x': xy[0], 'y': xy[1]})

    except FileNotFoundError:
        return jsonify({'error': 'GnuGo 未安裝，請確認 gnugo.exe 存在'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if proc:
            try:
                _gtp(proc, 'quit')
                proc.wait(timeout=2)
            except Exception:
                pass
            try:
                proc.kill()
            except Exception:
                pass


@app.route('/badges')
@login_required
def badges_page(): return redirect('/hero?tab=badges')

@app.route('/inventory')
@login_required
def inventory_page(): return redirect('/hero?tab=class')

@app.route('/api/user/coins')
@login_required
def get_user_coins():
    uid = session['user_id']
    with get_db() as conn:
        row = conn.execute(
            'SELECT coins, challenge_wins, challenge_win_streak, max_challenge_win_streak '
            'FROM user_stats WHERE user_id=?', (uid,)).fetchone()
    if row:
        return jsonify({'coins': row['coins'],
                        'challenge_wins': row['challenge_wins'],
                        'challenge_win_streak': row['challenge_win_streak'],
                        'max_challenge_win_streak': row['max_challenge_win_streak']})
    return jsonify({'coins': 0, 'challenge_wins': 0,
                    'challenge_win_streak': 0, 'max_challenge_win_streak': 0})

@app.route('/daily-challenge')
@login_required
def daily_challenge_page(): return send_from_directory('.','daily_challenge.html')

@app.route('/community')
@login_required
def community_page(): return send_from_directory('.','community.html')

@app.route('/share/<token>')
def share_page(token): return send_from_directory('.','share_view.html')

@app.route('/mistakes')
@login_required
def mistakes_page(): return send_from_directory('.','mistakes.html')

@app.route('/curriculum')
@login_required
def curriculum_page(): return send_from_directory('.','curriculum.html')

@app.route('/sanctum')
@login_required
def sanctum_page(): return send_from_directory('.','sanctum.html')

@app.route('/skills')
@app.route('/hero')
@login_required
def skills_page(): return send_from_directory('.','hero.html')

@app.route('/rating_test')
@login_required
def rating_test_page(): return send_from_directory('.','rating_test.html')

@app.route('/profile/<username>')
def profile_page(username): return send_from_directory('.','profile.html')

@app.route('/stats')
@login_required
def stats_page(): return send_from_directory('.','stats.html')

@app.route('/upgrade')
def upgrade_page(): return send_from_directory('.','upgrade.html')

@app.route('/<path:filename>.html')
@login_required
def serve_html(filename): return send_from_directory('.', filename+'.html')

@app.route('/wgo/<path:filename>')
def serve_wgo(filename): return send_from_directory('wgo', filename)

_SOUND_DIR = os.path.join(
    os.path.dirname(__file__),
    '2023-06-15-windows64+katago',
    '2023-06-15-windows64+katago',
    'sound'
)
@app.route('/sound/<path:filename>')
def serve_sound(filename):
    return send_from_directory(_SOUND_DIR, filename)

@app.route('/srs.js')
def serve_srs_js(): return send_from_directory('.','srs.js')

@app.route('/monster_trash.js')
def serve_monster_trash_js(): return send_from_directory('.','monster_trash.js')

@app.route('/i18n.js')
def serve_i18n_js(): return send_from_directory('.','i18n.js')

@app.route('/mobile-nav.js')
def serve_mobile_nav_js(): return send_from_directory('.','mobile-nav.js')

@app.route('/site-nav.js')
def serve_site_nav_js(): return send_from_directory('.','site-nav.js')

@app.route('/pwa.js')
def serve_pwa_js(): return send_from_directory('.','pwa.js')

@app.route('/manifest.json')
def serve_manifest(): return send_from_directory('.','manifest.json')

@app.route('/icon-192.png')
def serve_icon192(): return send_from_directory(_BASE,'icon-192.png')

@app.route('/assets/<path:subpath>')
def serve_assets(subpath):
    """提供題庫相關資源圖（如棋力區封面 assets/tiers/26-30.jpg）"""
    return send_from_directory(os.path.join(_BASE, 'assets'), subpath)

@app.route('/favicon.ico')
def serve_favicon():
    # 沒有 .ico 檔，用 icon-192.png 代替（瀏覽器吃任何圖片格式）
    return send_from_directory(_BASE, 'icon-192.png', mimetype='image/png')

@app.route('/icon-512.png')
def serve_icon512(): return send_from_directory(_BASE,'icon-512.png')

@app.route('/sw.js')
def serve_sw():
    resp = send_from_directory('.','sw.js')
    resp.headers['Service-Worker-Allowed'] = '/'
    resp.headers['Cache-Control'] = 'no-cache'
    return resp

@app.route('/icons/<path:filename>')
def serve_icons(filename): return send_from_directory('icons', filename)

# ══════════════════════════════════════════════════════════════
# 線上對弈模組（Socket.IO）
# ══════════════════════════════════════════════════════════════

# ── 全域狀態 ──────────────────────────────────────────────────
# _lobby[sid] = {sid, name, rank, status:'lobby'|'waiting'|'playing', dnd:bool}
_lobby:    dict = {}
# _invites[invite_id] = {invite_id, from_sid, from_name, to_sid, size,
#                        main_time, byoyomi, komi, created_at}
_invites:  dict = {}
_games:    dict = {}   # room_id -> game dict
_sid_room: dict = {}   # sid -> room_id

# ── 工具函式 ──────────────────────────────────────────────────
def _gen_rid() -> str:
    while True:
        rid = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        if rid not in _games:
            return rid

def _opp_color(c: str) -> str:
    return 'white' if c == 'black' else 'black'

def _sid_color(sid, g):
    if g['players']['black'] == sid: return 'black'
    if g['players']['white'] == sid: return 'white'
    return None

def _get_game(sid):
    rid = _sid_room.get(sid)
    if not rid or rid not in _games:
        return None, None, None
    g = _games[rid]
    return rid, g, _sid_color(sid, g)

def _emit_opp(g, color, event, data):
    opp_sid = g['players'][_opp_color(color)]
    if opp_sid:
        emit(event, data, to=opp_sid)

def _lobby_snapshot():
    return [
        {'sid': p['sid'], 'name': p['name'], 'rank': p.get('rank', ''),
         'status': p['status'], 'dnd': p['dnd']}
        for p in _lobby.values()
    ]

def _broadcast_lobby():
    socketio.emit('lobby_update', _lobby_snapshot(), to='lobby')

def _expire_invites():
    now = time.time()
    stale = [k for k, v in _invites.items() if now - v['created_at'] > 60]
    for k in stale:
        _invites.pop(k, None)

# ── 棋盤計算 ──────────────────────────────────────────────────
def _ensure_board(g):
    if g.get('_board') is None:
        sz = g['size']
        g['_board'] = [[0] * sz for _ in range(sz)]

def _nbrs(x, y, sz):
    for dx, dy in ((-1,0),(1,0),(0,-1),(0,1)):
        nx, ny = x + dx, y + dy
        if 0 <= nx < sz and 0 <= ny < sz:
            yield nx, ny

def _group(board, x, y, sz):
    color = board[y][x]
    visited, libs = set(), 0
    stack = [(x, y)]
    while stack:
        cx, cy = stack.pop()
        if (cx, cy) in visited: continue
        visited.add((cx, cy))
        for nx, ny in _nbrs(cx, cy, sz):
            if board[ny][nx] == 0:
                libs += 1
            elif board[ny][nx] == color and (nx, ny) not in visited:
                stack.append((nx, ny))
    return visited, libs

def _apply_move(g, x, y):
    _ensure_board(g)
    board, sz = g['_board'], g['size']
    ci = 1 if g['current'] == 'black' else 2
    oi = 3 - ci
    board[y][x] = ci
    cap = 0
    for nx, ny in _nbrs(x, y, sz):
        if board[ny][nx] == oi:
            grp, libs = _group(board, nx, ny, sz)
            if libs == 0:
                for gx, gy in grp:
                    board[gy][gx] = 0
                cap += len(grp)
    if g['current'] == 'black':
        g['black_captures'] += cap
    else:
        g['white_captures'] += cap
    return g['black_captures'], g['white_captures']

def _rebuild_board(g):
    """從 moves 清單重建棋盤（悔棋用）。"""
    sz = g['size']
    g['_board'] = [[0] * sz for _ in range(sz)]
    g['black_captures'] = g['white_captures'] = 0
    saved = g['current']
    g['current'] = 'black'
    for mv in g['moves']:
        if not mv.get('pass'):
            _apply_move(g, mv['x'], mv['y'])
        g['current'] = _opp_color(g['current'])
    g['current'] = saved

# ── SGF 產生 ──────────────────────────────────────────────────
_SGF_COLS = 'abcdefghijklmnopqrs'

def _build_sgf(g, b_name: str, w_name: str, score_info: dict | None = None) -> str:
    sz   = g['size']
    komi = g['komi']
    now  = time.strftime('%Y-%m-%d')
    result_tag = ''
    if score_info and score_info.get('black_score') is not None:
        diff = score_info.get('score_diff', 0)
        winner = score_info.get('winner', '')
        if winner == 'black':
            result_tag = f'RE[B+{diff}]'
        elif winner == 'white':
            result_tag = f'RE[W+{diff}]'
    sgf  = f'(;GM[1]FF[4]CA[UTF-8]AP[ColorfulGo]SZ[{sz}]KM[{komi}]'
    sgf += f'PB[{b_name}]PW[{w_name}]DT[{now}]{result_tag}'
    for mv in g.get('moves', []):
        c = 'B' if mv['color'] == 'black' else 'W'
        if mv.get('pass'):
            sgf += f';{c}[]'
        else:
            sgf += f';{c}[{_SGF_COLS[mv["x"]]}{_SGF_COLS[mv["y"]]}]'
    sgf += ')'
    return sgf

# ── 計分輔助 ──────────────────────────────────────────────────
def _get_group_positions(board, sx, sy, sz):
    """回傳 (sx,sy) 所屬同色連通塊的所有座標。"""
    color = board[sy][sx]
    if color == 0:
        return []
    visited, stack = set(), [(sx, sy)]
    while stack:
        cx, cy = stack.pop()
        if (cx, cy) in visited:
            continue
        if not (0 <= cx < sz and 0 <= cy < sz):
            continue
        if board[cy][cx] != color:
            continue
        visited.add((cx, cy))
        for dx, dy in ((-1,0),(1,0),(0,-1),(0,1)):
            stack.append((cx+dx, cy+dy))
    return list(visited)

def _calc_territory(board_2d, dead_set, sz, komi):
    """中國規則面積計分。
    board_2d: [[int]] 1=黑,2=白,0=空
    dead_set: set of (x,y) 死子位置
    回傳: (b_score, w_score, b_terr, w_terr, b_stones, w_stones,
           b_terr_pos, w_terr_pos)
    """
    eff = [row[:] for row in board_2d]
    for (x, y) in dead_set:
        eff[y][x] = 0          # 死子視為空點

    b_stones = sum(1 for y in range(sz) for x in range(sz) if eff[y][x] == 1)
    w_stones = sum(1 for y in range(sz) for x in range(sz) if eff[y][x] == 2)

    visited = [[False]*sz for _ in range(sz)]
    b_terr = w_terr = 0
    b_terr_pos, w_terr_pos = [], []

    for sy in range(sz):
        for sx in range(sz):
            if eff[sy][sx] == 0 and not visited[sy][sx]:
                region, borders, stack = [], set(), [(sx, sy)]
                while stack:
                    cx, cy = stack.pop()
                    if not (0 <= cx < sz and 0 <= cy < sz):
                        continue
                    if visited[cy][cx]:
                        continue
                    if eff[cy][cx] != 0:
                        borders.add(eff[cy][cx])
                        continue
                    visited[cy][cx] = True
                    region.append((cx, cy))
                    for dx, dy in ((-1,0),(1,0),(0,-1),(0,1)):
                        stack.append((cx+dx, cy+dy))
                if len(borders) == 1:
                    color = borders.pop()
                    if color == 1:
                        b_terr += len(region)
                        b_terr_pos.extend(region)
                    else:
                        w_terr += len(region)
                        w_terr_pos.extend(region)

    b_score = b_stones + b_terr
    w_score = w_stones + w_terr + komi
    return b_score, w_score, b_terr, w_terr, b_stones, w_stones, b_terr_pos, w_terr_pos

def _counting_snapshot(g):
    """產生計分畫面所需的完整資料包。"""
    sz = g['size']
    dead_set = g.get('dead_positions', set())
    _ensure_board(g)
    b, w, bt, wt, bs, ws, btp, wtp = _calc_territory(g['_board'], dead_set, sz, g['komi'])
    return {
        'dead': [list(p) for p in dead_set],
        'black_territory_pos': [list(p) for p in btp],
        'white_territory_pos': [list(p) for p in wtp],
        'black_score': b, 'white_score': w,
        'black_territory': bt, 'white_territory': wt,
        'black_stones': bs, 'white_stones': ws,
        'komi': g['komi'],
    }

def _finish_game(rid, g, reason, winner, score_info=None):
    now_str = time.strftime('%Y-%m-%dT%H:%M:%S')
    rank_changes = {}  # {sid: ('promote'|'demote', new_rank)}

    # 產生 SGF（所有模式共用）
    b_name = g['names'].get('black') or '黑方'
    w_name = g['names'].get('white') or '白方'
    sgf_str = _build_sgf(g, b_name, w_name, score_info)
    move_count = len(g['moves'])

    # 記錄勝負 + 檢查升降段 + 存完整對局記錄
    for color in ('black', 'white'):
        sid = g['players'].get(color)
        if not sid:
            continue
        uid = _lobby.get(sid, {}).get('user_id')
        if not uid:
            continue
        result = 1 if color == winner else 0
        opp_color = 'white' if color == 'black' else 'black'
        opp_name  = g['names'].get(opp_color) or '對手'
        go_rank   = _lobby.get(sid, {}).get('rank', '30k')
        try:
            with get_db() as _c:
                if winner in ('black', 'white'):   # 非平局才影響段位
                    _c.execute(
                        'INSERT INTO game_results(user_id, result, go_rank, played_at) VALUES(?,?,?,?)',
                        (uid, result, go_rank, now_str)
                    )
                    change, new_rank = check_go_rank_change(_c, uid)
                else:
                    change, new_rank = None, go_rank
                # 永遠儲存完整對局記錄
                _c.execute(
                    '''INSERT INTO game_records
                       (user_id, opponent_name, my_color, result, reason,
                        move_count, board_size, komi, black_score, white_score,
                        go_rank, sgf, played_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (uid, opp_name, color, result, reason,
                     move_count, g['size'], g['komi'],
                     score_info.get('black_score') if score_info else None,
                     score_info.get('white_score') if score_info else None,
                     go_rank, sgf_str, now_str)
                )
                _c.commit()
            if change:
                rank_changes[sid] = (change, new_rank)
                if sid in _lobby:
                    _lobby[sid]['rank'] = new_rank
        except Exception:
            pass

    payload = {
        'reason': reason, 'winner': winner,
        'black_captures': g['black_captures'],
        'white_captures': g['white_captures'],
        'move_count': len(g['moves']),
    }
    if score_info:
        payload.update(score_info)
    emit('game_over', payload, to=rid)

    # 逐一通知升降段（避免 to=rid 廣播時混淆）
    for sid, (change, new_rank) in rank_changes.items():
        emit('go_rank_changed', {'change': change, 'new_rank': new_rank}, to=sid)

    for color in ('black', 'white'):
        s = g['players'].get(color)
        if s and s in _lobby:
            _lobby[s]['status'] = 'lobby'
    _broadcast_lobby()

def _start_rematch(rid, g):
    """黑白互換開新局。"""
    nb, nw   = g['players']['white'], g['players']['black']
    nbn, nwn = g['names']['white'],   g['names']['black']
    old_ranks = g.get('ranks', {'black': '', 'white': ''})
    nbr, nwr = old_ranks.get('white', ''), old_ranks.get('black', '')
    g.update({
        'players': {'black': nb,  'white': nw},
        'names':   {'black': nbn, 'white': nwn},
        'ranks':   {'black': nbr, 'white': nwr},
        'moves': [], 'current': 'black',
        'black_captures': 0, 'white_captures': 0,
        'consecutive_passes': 0, 'status': 'playing',
        'rematch_votes': set(), 'undo_pending': False, '_board': None,
    })
    pkg = {'size': g['size'], 'main_time': g['main_time'], 'byoyomi': g['byoyomi'], 'komi': g['komi']}
    emit('rematch_accepted', {**pkg, 'your_color': 'black', 'opponent_name': nwn, 'opponent_rank': nwr}, to=nb)
    emit('rematch_accepted', {**pkg, 'your_color': 'white', 'opponent_name': nbn, 'opponent_rank': nbr}, to=nw)

# ── HTTP 路由 ─────────────────────────────────────────────────
@app.route('/play')
@login_required
def play_page():
    return send_from_directory('.', 'play.html')

@app.route('/games')
@login_required
def games_page():
    return send_from_directory(_BASE, 'games.html')

@app.route('/api/game-records')
@login_required
def api_game_records():
    uid    = session['user_id']
    page   = max(1, int(request.args.get('page', 1)))
    limit  = 20
    offset = (page - 1) * limit
    with get_db() as db:
        total = db.execute(
            'SELECT COUNT(*) FROM game_records WHERE user_id=?', (uid,)
        ).fetchone()[0]
        rows = db.execute(
            '''SELECT id, opponent_name, my_color, result, reason,
                      move_count, board_size, komi,
                      black_score, white_score, go_rank, played_at
               FROM game_records WHERE user_id=?
               ORDER BY played_at DESC LIMIT ? OFFSET ?''',
            (uid, limit, offset)
        ).fetchall()
    games = []
    for r in rows:
        games.append({
            'id':            r['id'],
            'opponent_name': r['opponent_name'],
            'my_color':      r['my_color'],
            'result':        r['result'],       # 1=勝 0=負
            'reason':        r['reason'],
            'move_count':    r['move_count'],
            'board_size':    r['board_size'],
            'komi':          r['komi'],
            'black_score':   r['black_score'],
            'white_score':   r['white_score'],
            'go_rank':       r['go_rank'],
            'played_at':     r['played_at'],
        })
    return jsonify({'games': games, 'total': total, 'page': page, 'limit': limit})

@app.route('/api/game-records/summary')
@login_required
def api_game_records_summary():
    uid = session['user_id']
    with get_db() as db:
        row = db.execute(
            '''SELECT
               COUNT(*)                            AS total,
               SUM(result)                         AS wins,
               COUNT(*) - SUM(result)              AS loses,
               MAX(played_at)                      AS last_game
               FROM game_records WHERE user_id=?''',
            (uid,)
        ).fetchone()
    total = row['total'] or 0
    wins  = row['wins']  or 0
    loses = row['loses'] or 0
    rate  = round(wins / total * 100) if total else 0
    return jsonify({
        'total': total, 'wins': wins, 'loses': loses,
        'rate': rate, 'last_game': row['last_game']
    })

@app.route('/api/game-records/<int:record_id>/sgf')
@login_required
def api_game_sgf(record_id):
    uid = session['user_id']
    with get_db() as db:
        row = db.execute(
            'SELECT sgf, played_at, board_size FROM game_records WHERE id=? AND user_id=?',
            (record_id, uid)
        ).fetchone()
    if not row or not row['sgf']:
        return jsonify({'error': '找不到棋譜'}), 404
    date_str = (row['played_at'] or '')[:10].replace('-', '')
    filename = f'colorful-go-{date_str}-{record_id}.sgf'
    from flask import Response
    return Response(
        row['sgf'],
        mimetype='application/x-go-sgf',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )

# ── Socket.IO：連線 / 離線 ────────────────────────────────────
@socketio.on('disconnect')
def on_disconnect():
    sid = request.sid

    # 大廳移除
    if sid in _lobby:
        _lobby.pop(sid, None)
        leave_room('lobby')
        _broadcast_lobby()

    # 取消此人發出的邀局，通知對方
    outgoing = [inv for inv in list(_invites.values()) if inv['from_sid'] == sid]
    for inv in outgoing:
        emit('invite_cancelled', {}, to=inv['to_sid'])
        _invites.pop(inv['invite_id'], None)

    # 移除寄給此人的邀局
    incoming = [inv for inv in list(_invites.values()) if inv['to_sid'] == sid]
    for inv in incoming:
        _invites.pop(inv['invite_id'], None)

    # 通知對方斷線
    rid, g, color = _get_game(sid)
    if rid and g and g['status'] == 'playing':
        _emit_opp(g, color, 'opponent_disconnected', {})
        _emit_opp(g, color, 'game_over', {
            'reason': 'disconnect', 'winner': _opp_color(color),
            'black_captures': g['black_captures'],
            'white_captures': g['white_captures'],
            'move_count': len(g['moves']),
        })
        g['status'] = 'finished'
    _sid_room.pop(sid, None)

# ── Socket.IO：大廳 ───────────────────────────────────────────
@socketio.on('enter_lobby')
def on_enter_lobby(data):
    from flask import session as _fs
    sid     = request.sid
    name    = str(data.get('name', '玩家'))[:20].strip() or '玩家'
    uid     = _fs.get('user_id')
    # 從 DB 取得 go_rank（比客戶端傳來的更可信）
    go_rank = '30k'
    if uid:
        try:
            with get_db() as _c:
                _r = _c.execute('SELECT go_rank FROM user_stats WHERE user_id=?', (uid,)).fetchone()
                if _r:
                    go_rank = _r['go_rank'] or '30k'
        except Exception:
            pass
    _lobby[sid] = {'sid': sid, 'name': name, 'rank': go_rank,
                   'user_id': uid, 'status': 'lobby', 'dnd': False}
    join_room('lobby')
    emit('lobby_entered', {'sid': sid})
    _broadcast_lobby()

@socketio.on('toggle_dnd')
def on_toggle_dnd(data):
    sid = request.sid
    if sid not in _lobby: return
    _lobby[sid]['dnd'] = bool(data.get('dnd', False))
    _broadcast_lobby()

# ── Socket.IO：邀局 ───────────────────────────────────────────
@socketio.on('send_invite')
def on_send_invite(data):
    _expire_invites()
    sid    = request.sid
    to_sid = str(data.get('to_sid', ''))
    size   = int(data.get('size', 13))
    main_time = int(data.get('main_time', 0))
    byoyomi   = int(data.get('byoyomi', 0))
    komi      = float(data.get('komi', 6.5))
    if size not in (9, 13, 19): size = 13

    if sid not in _lobby:
        emit('error_msg', {'message': '請先進入大廳'}); return
    if to_sid not in _lobby:
        emit('error_msg', {'message': '對方已不在線'}); return
    target = _lobby[to_sid]
    if target['dnd']:
        emit('error_msg', {'message': f'{target["name"]} 目前不接受邀局'}); return
    if target['status'] != 'lobby':
        emit('error_msg', {'message': f'{target["name"]} 目前不在空閒狀態'}); return

    invite_id = uuid.uuid4().hex[:8]
    _invites[invite_id] = {
        'invite_id':    invite_id,
        'from_sid':     sid,
        'from_name':    _lobby[sid]['name'],
        'to_sid':       to_sid,
        'size':         size,
        'main_time':    main_time,
        'byoyomi':      byoyomi,
        'komi':         komi,
        'created_at':   time.time(),
    }
    emit('invite_received', {
        'invite_id':    invite_id,
        'from_sid':     sid,
        'from_name':    _lobby[sid]['name'],
        'size':         size,
        'main_time':    main_time,
        'byoyomi':      byoyomi,
        'komi':         komi,
    }, to=to_sid)

@socketio.on('accept_invite')
def on_accept_invite(data):
    _expire_invites()
    sid    = request.sid
    inv_id = str(data.get('invite_id', ''))
    if inv_id not in _invites:
        emit('error_msg', {'message': '邀局已過期或已取消'}); return
    inv = _invites.pop(inv_id)
    if inv['to_sid'] != sid:
        emit('error_msg', {'message': '這不是你的邀局'}); return
    from_sid = inv['from_sid']
    if from_sid not in _lobby:
        emit('error_msg', {'message': '邀請方已離線'}); return

    emit('invite_accepted_by', {'from_name': _lobby[sid]['name']}, to=from_sid)

    rid = _gen_rid()
    _games[rid] = {
        'size': inv['size'],
        'players': {'black': from_sid, 'white': sid},
        'names':   {'black': _lobby[from_sid]['name'], 'white': _lobby[sid]['name']},
        'moves': [], 'current': 'black',
        'black_captures': 0, 'white_captures': 0,
        'consecutive_passes': 0, 'status': 'playing',
        'main_time': inv['main_time'], 'byoyomi': inv['byoyomi'], 'komi': inv['komi'],
        'rematch_votes': set(), 'undo_pending': False, '_board': None,
    }
    _sid_room[from_sid] = rid
    _sid_room[sid]      = rid
    join_room(rid, sid=from_sid)
    join_room(rid, sid=sid)
    for s in (from_sid, sid):
        if s in _lobby: _lobby[s]['status'] = 'playing'
    _broadcast_lobby()

    pkg = {'size': inv['size'], 'main_time': inv['main_time'], 'byoyomi': inv['byoyomi'], 'komi': inv['komi']}
    accepter_rank = _lobby.get(sid, {}).get('rank', '')
    inviter_rank  = _lobby.get(from_sid, {}).get('rank', '')
    emit('game_started', {**pkg,
         'opponent_name': _lobby[sid]['name'],      'opponent_rank': accepter_rank, 'your_color': 'black'}, to=from_sid)
    emit('game_started', {**pkg,
         'opponent_name': _lobby[from_sid]['name'], 'opponent_rank': inviter_rank,  'your_color': 'white'}, to=sid)

@socketio.on('decline_invite')
def on_decline_invite(data):
    sid    = request.sid
    inv_id = str(data.get('invite_id', ''))
    inv    = _invites.pop(inv_id, None)
    if inv:
        emit('invite_declined_by',
             {'from_name': _lobby.get(sid, {}).get('name', '對方')},
             to=inv['from_sid'])

# ── Socket.IO：建立 / 加入房間 ────────────────────────────────
@socketio.on('create_game')
def on_create_game(data):
    sid  = request.sid
    size = int(data.get('size', 13))
    if size not in (9, 13, 19): size = 13
    name = str(data.get('name', '黑方'))[:20]
    main_time = int(data.get('main_time', 0))
    byoyomi   = int(data.get('byoyomi', 0))
    komi      = float(data.get('komi', 6.5))

    rid = _gen_rid()
    creator_rank = _lobby.get(sid, {}).get('rank', '')
    _games[rid] = {
        'size': size,
        'players': {'black': sid, 'white': None},
        'names':   {'black': name, 'white': None},
        'ranks':   {'black': creator_rank, 'white': ''},
        'moves': [], 'current': 'black',
        'black_captures': 0, 'white_captures': 0,
        'consecutive_passes': 0, 'status': 'waiting',
        'main_time': main_time, 'byoyomi': byoyomi, 'komi': komi,
        'rematch_votes': set(), 'undo_pending': False, '_board': None,
    }
    _sid_room[sid] = rid
    join_room(rid)
    if sid in _lobby: _lobby[sid]['status'] = 'waiting'
    _broadcast_lobby()
    emit('game_created', {'room_id': rid, 'color': 'black'})

@socketio.on('cancel_waiting')
def on_cancel_waiting(data):
    sid = request.sid
    rid = _sid_room.pop(sid, None)
    if rid and rid in _games and _games[rid]['status'] == 'waiting':
        del _games[rid]
    if sid in _lobby: _lobby[sid]['status'] = 'lobby'
    _broadcast_lobby()

@socketio.on('join_game')
def on_join_game(data):
    sid  = request.sid
    rid  = str(data.get('room_id', '')).upper().strip()
    name = str(data.get('name', '白方'))[:20]

    if rid not in _games:
        emit('error_msg', {'message': f'找不到房間 {rid}'}); return
    g = _games[rid]
    if g['status'] != 'waiting':
        emit('error_msg', {'message': '此對局已開始或已結束'}); return
    if g['players']['white'] is not None:
        emit('error_msg', {'message': '此房間已有兩位玩家'}); return

    joiner_rank = _lobby.get(sid, {}).get('rank', '')
    g['players']['white'] = sid
    g['names']['white']   = name
    if 'ranks' not in g: g['ranks'] = {'black': '', 'white': ''}
    g['ranks']['white']   = joiner_rank
    g['status']           = 'playing'
    _sid_room[sid]        = rid
    join_room(rid)
    for s in (g['players']['black'], sid):
        if s in _lobby: _lobby[s]['status'] = 'playing'
    _broadcast_lobby()

    pkg = {'size': g['size'], 'main_time': g['main_time'], 'byoyomi': g['byoyomi'], 'komi': g['komi']}
    emit('game_started', {**pkg,
         'opponent_name': name,               'opponent_rank': joiner_rank,            'your_color': 'black'},
         to=g['players']['black'])
    emit('game_started', {**pkg,
         'opponent_name': g['names']['black'], 'opponent_rank': g['ranks']['black'],    'your_color': 'white'},
         to=sid)

# ── Socket.IO：重連 ───────────────────────────────────────────
@socketio.on('reconnect_game')
def on_reconnect_game(data):
    sid   = request.sid
    rid   = str(data.get('room_id', '')).upper().strip()
    color = str(data.get('color', ''))
    name  = str(data.get('name', ''))[:20]

    if rid not in _games:
        emit('error_msg', {'message': '找不到對局，可能已結束'}); return
    g = _games[rid]
    if color not in ('black', 'white'):
        emit('error_msg', {'message': '無效的顏色'}); return
    if g['status'] == 'finished':
        emit('error_msg', {'message': '對局已結束'}); return

    old = g['players'].get(color)
    if old and old != sid:
        _sid_room.pop(old, None)
    g['players'][color] = sid
    g['names'][color]   = name
    _sid_room[sid]      = rid
    join_room(rid)

    opp_c = _opp_color(color)
    emit('reconnect_state', {
        'your_color':     color,
        'opponent_name':  g['names'][opp_c] or '等待對手',
        'opponent_rank':  g.get('ranks', {}).get(opp_c, ''),
        'size':           g['size'],
        'main_time':      g['main_time'],
        'byoyomi':        g['byoyomi'],
        'komi':           g['komi'],
        'black_captures': g['black_captures'],
        'white_captures': g['white_captures'],
        'current_color':  g['current'],
        'moves':          g['moves'],
    })

# ── Socket.IO：遊戲操作 ───────────────────────────────────────
@socketio.on('make_move')
def on_make_move(data):
    sid = request.sid
    rid, g, color = _get_game(sid)
    if not rid or g['status'] != 'playing':
        emit('error_msg', {'message': '非對局中'}); return
    if g['current'] != color:
        emit('error_msg', {'message': '還不是你的回合'}); return
    x, y = int(data['x']), int(data['y'])
    if not (0 <= x < g['size'] and 0 <= y < g['size']):
        emit('error_msg', {'message': '座標超出範圍'}); return

    bc, wc = _apply_move(g, x, y)
    mn = len(g['moves']) + 1
    g['moves'].append({'color': color, 'x': x, 'y': y})
    g['consecutive_passes'] = 0
    g['current'] = _opp_color(color)

    emit('move_played', {
        'x': x, 'y': y, 'color': color, 'move_number': mn,
        'black_captures': bc, 'white_captures': wc,
    }, to=rid)

@socketio.on('pass_move')
def on_pass_move(data):
    sid = request.sid
    rid, g, color = _get_game(sid)
    if not rid or g['status'] != 'playing': return
    if g['current'] != color:
        emit('error_msg', {'message': '還不是你的回合'}); return

    mn = len(g['moves']) + 1
    g['moves'].append({'color': color, 'pass': True})
    g['consecutive_passes'] += 1
    g['current'] = _opp_color(color)

    emit('move_passed', {
        'color': color,
        'consecutive_passes': g['consecutive_passes'],
        'move_number': mn,
    }, to=rid)

    if g['consecutive_passes'] >= 2:
        # 進入計分階段（不立即結束）
        g['status'] = 'counting'
        g['dead_positions'] = set()
        g['count_confirmed'] = set()
        emit('start_counting', _counting_snapshot(g), to=rid)

@socketio.on('resign_game')
def on_resign_game(data):
    sid = request.sid
    rid, g, color = _get_game(sid)
    if not rid or g['status'] not in ('playing', 'counting'): return
    g['status'] = 'finished'
    _finish_game(rid, g, 'resign', _opp_color(color))

# ── 計分階段 ─────────────────────────────────────────────────
@socketio.on('toggle_dead_group')
def on_toggle_dead_group(data):
    sid = request.sid
    rid, g, color = _get_game(sid)
    if not rid or g.get('status') != 'counting': return
    x, y = int(data.get('x', -1)), int(data.get('y', -1))
    sz = g['size']
    if not (0 <= x < sz and 0 <= y < sz): return
    _ensure_board(g)
    if g['_board'][y][x] == 0: return          # 空點忽略

    group = set(_get_group_positions(g['_board'], x, y, sz))
    dead = g.get('dead_positions', set())
    # 若群組內有任一死子 → 整組標為活；否則標為死
    if group & dead:
        dead -= group
    else:
        dead |= group
    g['dead_positions'] = dead
    g['count_confirmed'] = set()               # 改動後重置確認
    emit('counting_update', _counting_snapshot(g), to=rid)

@socketio.on('confirm_count')
def on_confirm_count(data):
    sid = request.sid
    rid, g, color = _get_game(sid)
    if not rid or g.get('status') != 'counting': return
    confirmed = g.get('count_confirmed', set())
    confirmed.add(sid)
    g['count_confirmed'] = confirmed
    # 通知對手顯示「對手已確認」
    _emit_opp(g, color, 'opp_confirmed_count', {})
    # 雙方都確認 → 結算
    both = {g['players']['black'], g['players']['white']}
    if confirmed >= both:
        snap = _counting_snapshot(g)
        b, w = snap['black_score'], snap['white_score']
        winner = 'black' if b > w else 'white'
        g['status'] = 'finished'
        score_diff = round(abs(b - w), 1)
        _finish_game(rid, g, 'score', winner, {
            'black_score': b, 'white_score': w,
            'score_diff': score_diff,
        })

@socketio.on('request_count')
def on_request_count(data):
    """玩家提議進入終局計地（對手收到 count_requested 後可接受/拒絕）"""
    sid = request.sid
    rid, g, color = _get_game(sid)
    if not rid or g.get('status') != 'playing':
        emit('error_msg', {'message': '非對局中'}); return
    if len(g.get('moves', [])) < 4:
        emit('error_msg', {'message': '棋局太早，無法進入計地'}); return
    if g.get('count_pending'):
        emit('error_msg', {'message': '已有待確認的計地請求'}); return
    g['count_pending'] = True
    _emit_opp(g, color, 'count_requested', {})

@socketio.on('accept_count')
def on_accept_count(data):
    """對手接受進入計地 → 雙方進入 counting 模式"""
    sid = request.sid
    rid, g, color = _get_game(sid)
    if not rid or not g.get('count_pending'): return
    g['count_pending'] = False
    g['status'] = 'counting'
    g['dead_positions'] = set()
    g['count_confirmed'] = set()
    emit('start_counting', _counting_snapshot(g), to=rid)

@socketio.on('reject_count')
def on_reject_count(data):
    sid = request.sid
    rid, g, color = _get_game(sid)
    if not rid: return
    g['count_pending'] = False
    _emit_opp(g, color, 'count_rejected', {})

@socketio.on('request_position_eval')
def on_request_position_eval(data):
    """中盤形勢判斷：呼叫 KataGo 取得勝率/目差/領地"""
    sid = request.sid
    rid, g, color = _get_game(sid)
    if not rid or g.get('status') not in ('playing', 'counting'):
        emit('error_msg', {'message': '非對局中'}); return

    # 把 g['moves'] 轉成 KataGo 需要的格式
    # query_katago_analysis 需要 stones_black/white/moves_so_far 結構
    sz = g['size']
    moves_so_far = []
    for m in g['moves']:
        if m.get('pass'):
            moves_so_far.append({'player': 'B' if m['color']=='black' else 'W', 'x': -1, 'y': -1, 'pass': True})
        else:
            moves_so_far.append({'player': 'B' if m['color']=='black' else 'W', 'x': m['x'], 'y': m['y']})
    # 過濾掉 pass（KataGo analysis 需要明確的 pass 處理）
    valid_moves = [m for m in moves_so_far if not m.get('pass')]

    def _run():
        try:
            result = query_katago_analysis(
                board_size=sz,
                stones_black=[], stones_white=[],
                player='B' if g['current']=='black' else 'W',
                moves_so_far=valid_moves,
                visits=80,
            )
            if not result:
                socketio.emit('position_eval_result', {'error': 'KataGo 無回應'}, to=sid)
                return
            # 從當前要下的人的視角給勝率
            cur = g['current']
            winrate_for_current = result['winrate']   # KataGo 預設給「下一手者」勝率
            socketio.emit('position_eval_result', {
                'current_color': cur,
                'winrate_for_current': winrate_for_current,
                'score_lead': result['score_lead'],   # 正數=下一手者領先目數
                'ownership_grid': result.get('ownership_grid'),
                'best_move': result.get('best_move'),
                'move_count': len(g['moves']),
            }, to=sid)
        except Exception as e:
            print(f'[position_eval error] {e}')
            socketio.emit('position_eval_result', {'error': str(e)}, to=sid)

    threading.Thread(target=_run, daemon=True).start()
    emit('position_eval_pending', {})


@socketio.on('request_auto_dead_stones')
def on_request_auto_dead_stones(data):
    """終局自動判斷死子：用 KataGo ownership 結果"""
    sid = request.sid
    rid, g, color = _get_game(sid)
    if not rid or g.get('status') != 'counting':
        emit('error_msg', {'message': '非計分階段'}); return

    sz = g['size']
    valid_moves = []
    for m in g['moves']:
        if not m.get('pass'):
            valid_moves.append({'player': 'B' if m['color']=='black' else 'W', 'x': m['x'], 'y': m['y']})

    def _run():
        try:
            result = query_katago_analysis(
                board_size=sz,
                stones_black=[], stones_white=[],
                player='B', moves_so_far=valid_moves, visits=100,
            )
            if not result or not result.get('ownership_grid'):
                socketio.emit('auto_dead_result', {'error': 'KataGo 無回應'}, to=sid)
                return
            own = result['ownership_grid']   # 2D: own[y][x] 正=黑領地, 負=白領地
            _ensure_board(g)
            board = g['_board']   # board[y][x]: 1=黑棋, -1=白棋, 0=空
            dead_set = set()
            # 對每顆棋子判斷：所在格的 ownership 是否與自身顏色相反 → 死
            for y in range(sz):
                for x in range(sz):
                    stone = board[y][x]
                    if stone == 0: continue
                    o = own[y][x]
                    # 黑棋(1) 但 ownership <-0.4 → 黑棋已死(在白勢力範圍)
                    # 白棋(-1) 但 ownership >0.4 → 白棋已死(在黑勢力範圍)
                    if stone == 1 and o < -0.4:
                        dead_set.add((x, y))
                    elif stone == -1 and o > 0.4:
                        dead_set.add((x, y))
            g['dead_positions'] = dead_set
            g['count_confirmed'] = set()
            socketio.emit('counting_update', _counting_snapshot(g), to=rid)
            socketio.emit('auto_dead_result', {'ok': True, 'dead_count': len(dead_set)}, to=sid)
        except Exception as e:
            print(f'[auto_dead_stones error] {e}')
            socketio.emit('auto_dead_result', {'error': str(e)}, to=sid)

    threading.Thread(target=_run, daemon=True).start()
    emit('auto_dead_pending', {})


@socketio.on('resume_from_count')
def on_resume_from_count(data):
    sid = request.sid
    rid, g, color = _get_game(sid)
    if not rid or g.get('status') != 'counting': return
    g['status'] = 'playing'
    g['consecutive_passes'] = 0
    g['dead_positions'] = set()
    g['count_confirmed'] = set()
    emit('game_resumed', {'current': g['current']}, to=rid)

@socketio.on('player_timeout')
def on_player_timeout(data):
    sid = request.sid
    rid, g, color = _get_game(sid)
    if not rid or g['status'] != 'playing': return
    g['status'] = 'finished'
    _finish_game(rid, g, 'timeout', _opp_color(color))

# ── 悔棋 ─────────────────────────────────────────────────────
@socketio.on('request_undo')
def on_request_undo(data):
    sid = request.sid
    rid, g, color = _get_game(sid)
    if not rid or g['status'] != 'playing': return
    if len(g['moves']) == 0:
        emit('error_msg', {'message': '目前沒有可悔的棋'}); return
    if g.get('undo_pending'):
        emit('error_msg', {'message': '已有待確認的悔棋'}); return
    if g['moves'][-1]['color'] != color:
        emit('error_msg', {'message': '只能悔自己的棋'}); return
    g['undo_pending'] = True
    _emit_opp(g, color, 'undo_requested', {})

@socketio.on('accept_undo')
def on_accept_undo(data):
    sid = request.sid
    rid, g, color = _get_game(sid)
    if not rid or not g.get('undo_pending'): return
    removed = g['moves'].pop()
    g['undo_pending'] = False
    g['consecutive_passes'] = 0
    _rebuild_board(g)
    g['current'] = removed['color']
    emit('undo_done', {'color': removed['color']}, to=rid)

@socketio.on('reject_undo')
def on_reject_undo(data):
    sid = request.sid
    rid, g, color = _get_game(sid)
    if not rid: return
    g['undo_pending'] = False
    _emit_opp(g, color, 'undo_rejected', {})

# ── 再戰 ─────────────────────────────────────────────────────
@socketio.on('request_rematch')
def on_request_rematch(data):
    sid = request.sid
    rid, g, color = _get_game(sid)
    if not rid or g['status'] != 'finished': return
    g['rematch_votes'].add(sid)
    opp_sid = g['players'][_opp_color(color)]
    if not opp_sid or opp_sid not in g['rematch_votes']:
        if opp_sid: emit('rematch_offered', {}, to=opp_sid)
    else:
        _start_rematch(rid, g)

@socketio.on('accept_rematch')
def on_accept_rematch(data):
    sid = request.sid
    rid, g, color = _get_game(sid)
    if not rid: return
    g['rematch_votes'].add(sid)
    opp_sid = g['players'][_opp_color(color)]
    if opp_sid and opp_sid in g['rematch_votes']:
        _start_rematch(rid, g)

# ── 聊天 ─────────────────────────────────────────────────────
@socketio.on('send_chat')
def on_send_chat(data):
    sid = request.sid
    rid = _sid_room.get(sid)
    if not rid or rid not in _games: return
    g = _games[rid]
    c = _sid_color(sid, g)
    if not c: return
    msg = str(data.get('message', ''))[:200].strip()
    if msg:
        emit('chat_message', {'sender': g['names'][c], 'message': msg}, to=rid)

# ── 啟動 ──────────────────────────────────────────────────────

# ══════════════════════════════════════════════════════════════════════
# 職業 / 技能樹 API
# ══════════════════════════════════════════════════════════════════════

@app.route('/api/class/profile')
@login_required
def class_profile():
    """取得玩家技能樹與學科進度（已移除職業體系）。"""
    uid = session['user_id']
    with get_db() as conn:
        sync_skill_tree(uid, conn)
        conn.commit()
        stats = conn.execute(
            'SELECT xp FROM user_stats WHERE user_id=?', (uid,)
        ).fetchone()
        tree_rows = conn.execute(
            'SELECT discipline, level, unlocked_at FROM skill_tree WHERE user_id=?', (uid,)
        ).fetchall()
        disc_counts = get_discipline_counts(uid, conn)

    xp = (stats['xp'] or 0) if stats else 0
    lv, _, _ = lv_progress(xp)
    tree_map = {r['discipline']: r['level'] for r in tree_rows}
    tree_out = {}
    for disc, nodes in SKILL_NODES.items():
        current_lv = tree_map.get(disc, 0)
        raw_cnt    = disc_counts.get(disc, 0)
        tree_out[disc] = {
            'current_level':  current_lv,
            'answered_count': raw_cnt,
            'nodes': [
                {'lv': n['lv'], 'name': n['name'], 'req': n['req'], 'bonus': n['bonus'],
                 'unlocked': current_lv >= n['lv'], 'progress': min(raw_cnt, n['req'])}
                for n in nodes
            ],
        }

    # 四象限屬性：由各學科進度自動加總（無需手動分配）
    attr_scores = {'atk': 0, 'def': 0, 'vis': 0, 'prec': 0}
    for disc, info in tree_out.items():
        attr = DISC_TO_ATTR_SKILL.get(disc)
        if attr and attr in attr_scores:
            attr_scores[attr] += info['current_level']   # 每學科最高 5 等

    return jsonify({
        'level':             lv,
        'skill_tree':        tree_out,
        'discipline_counts': disc_counts,
        'attr_scores':       attr_scores,   # 自動計算，不再手動分配
    })


@app.route('/api/class/ascend', methods=['POST'])
@login_required
def class_ascend():
    """職業系統已移除（v3.0）。稱號現由屬性自動決定，此端點保留以向後相容。"""
    return jsonify({'error': 'deprecated',
                    'message': '職業選擇已移除；稱號由四大屬性自動決定。'}), 410


@app.route('/api/class/attr/allocate', methods=['POST'])
@login_required
def class_attr_allocate():
    """分配潛能點到屬性。"""
    uid  = session['user_id']
    data = request.get_json() or {}
    VALID = {'atk': 'attr_atk', 'def': 'attr_def',
             'vis': 'attr_vis',  'prec': 'attr_prec'}
    attr_key = data.get('attr', '')
    points   = int(data.get('points', 1))
    if attr_key not in VALID:
        return jsonify({'error': 'invalid_attr'}), 400
    if points < 1:
        return jsonify({'error': 'invalid_points'}), 400

    with get_db() as conn:
        stats = conn.execute('SELECT free_pts FROM user_stats WHERE user_id=?', (uid,)).fetchone()
        if not stats or (stats['free_pts'] or 0) < points:
            return jsonify({'error': 'not_enough_pts',
                            'have': stats['free_pts'] if stats else 0}), 400
        col = VALID[attr_key]
        conn.execute(f'UPDATE user_stats SET {col}={col}+?, free_pts=free_pts-? WHERE user_id=?',
                     (points, points, uid))
        conn.commit()
        s = conn.execute(
            'SELECT attr_atk, attr_def, attr_vis, attr_prec, free_pts FROM user_stats WHERE user_id=?',
            (uid,)
        ).fetchone()
    atk  = s['attr_atk']  or 0
    def_ = s['attr_def']  or 0
    vis  = s['attr_vis']  or 0
    prec = s['attr_prec'] or 0
    return jsonify({'ok': True,
                    'attrs': {'atk': atk, 'def': def_, 'vis': vis, 'prec': prec},
                    'free_pts': s['free_pts'] or 0,
                    'auto_title': get_auto_title(atk, def_, vis, prec)})


@app.route('/api/class/skill-tree')
@login_required
def class_skill_tree():
    """同步並回傳技能樹狀態。"""
    uid = session['user_id']
    with get_db() as conn:
        sync_skill_tree(uid, conn)
        conn.commit()
        tree_rows   = conn.execute('SELECT discipline, level FROM skill_tree WHERE user_id=?', (uid,)).fetchall()
        disc_counts = get_discipline_counts(uid, conn)

    tree_map = {r['discipline']: r['level'] for r in tree_rows}
    out = {}
    for disc, nodes in SKILL_NODES.items():
        lv  = tree_map.get(disc, 0)
        cnt = disc_counts.get(disc, 0)
        out[disc] = {
            'current_level':  lv,
            'answered_count': cnt,
            'nodes': [
                {'lv': n['lv'], 'name': n['name'], 'req': n['req'],
                 'unlocked': lv >= n['lv'], 'progress': min(cnt, n['req'])}
                for n in nodes
            ],
        }
    return jsonify({'skill_tree': out, 'discipline_counts': disc_counts})


@app.route('/api/class/passive')
@login_required
def class_passive():
    """回傳玩家當前被動技能清單（供前端套用加成用）。"""
    uid = session['user_id']
    with get_db() as conn:
        stats = conn.execute(
            'SELECT attr_atk, attr_def, attr_vis, attr_prec, free_pts FROM user_stats WHERE user_id=?',
            (uid,)
        ).fetchone()
        tree_rows = conn.execute('SELECT discipline, level FROM skill_tree WHERE user_id=?', (uid,)).fetchall()

    tree_map = {r['discipline']: r['level'] for r in tree_rows}
    passives = {}
    passives['skill_bonuses'] = [
        {'disc': disc, 'lv': n['lv'], 'name': n['name'], 'bonus': n['bonus']}
        for disc, nodes in SKILL_NODES.items()
        for n in nodes
        if tree_map.get(disc, 0) >= n['lv']
    ]
    if stats:
        atk  = stats['attr_atk']  or 0
        def_ = stats['attr_def']  or 0
        vis  = stats['attr_vis']  or 0
        prec = stats['attr_prec'] or 0
        passives['attrs'] = {'atk': atk, 'def': def_, 'vis': vis, 'prec': prec,
                             'free_pts': stats['free_pts'] or 0}
        passives['auto_title'] = get_auto_title(atk, def_, vis, prec)
    return jsonify(passives)

# ════════════════════════════════════════════════════════════════════════════
# AI 自適應棋力測驗（Adaptive Rating Test）
# ════════════════════════════════════════════════════════════════════════════

# ── Gold Pool（延遲初始化，首次請求時建立）─────────────────────────────────
_RT_POOL: list = []        # 按 rating 排序
_RT_POOL_READY = False

# 各學科最低 score_gap 門檻（OK 題）—— 只在 score_gap 欄位存在時使用
_RT_DISC_THRESH = {
    'life_death':       8.0,
    'tesuji':           5.0,
    'chase':            3.0,
    'endgame_counting': 3.0,
}
# NG 題門檻（稍高，確保 SGF 答案路徑仍有教學價值）
_RT_DISC_THRESH_NG = {
    'life_death':       10.0,
    'tesuji':            6.5,
    'chase':             4.5,
    'endgame_counting':  4.5,
}

# rank 字串 → 合成 Elo rating（用於 score_gap/match 欄位尚未分析時的 fallback）
_RANK_TO_RATING: dict = {
    '30k': 1100, '25k': 1150, '20k': 1200,
    '15k': 1300, '10k': 1400,
    '9k':  1450, '8k':  1480, '7k': 1510,
    '6k':  1540, '5k':  1570, '4k': 1600,
    '3k':  1630, '2k':  1660, '1k': 1700,
    '1d':  1800, '2d':  1900, '3d': 2000,
    '4d':  2100, '5d':  2200, '6d': 2350,
    '7d':  2500,
}

# ── SGF 幾何旋轉 ──────────────────────────────────────────────────────────────
# 8 種對稱變換（圍棋棋盤旋轉/翻轉），讓同一道題產生視覺上截然不同的版本。
# 不旋轉(0) / 90°CW(1) / 180°(2) / 270°CW(3) /
# 左右翻(4) / 上下翻(5) / 主對角(6) / 反對角(7)
import re as _re_mod

def _transform_sgf(content: str, t: int) -> str:
    """將 SGF 內所有落子座標套用第 t 種幾何變換（t=0 直接回傳原文）。"""
    if t == 0:
        return content
    # 從 SZ[] 取棋盤大小
    m = _re_mod.search(r'SZ\[(\d+)\]', content)
    N = int(m.group(1)) if m else 19
    n = N - 1

    TRANSFORMS = (
        lambda c, r: (c,   r),       # 0 identity（不會走到這裡）
        lambda c, r: (n-r, c),       # 1 rotate 90° CW
        lambda c, r: (n-c, n-r),     # 2 rotate 180°
        lambda c, r: (r,   n-c),     # 3 rotate 270° CW
        lambda c, r: (n-c, r),       # 4 flip horizontal（左右）
        lambda c, r: (c,   n-r),     # 5 flip vertical（上下）
        lambda c, r: (r,   c),       # 6 主對角線轉置
        lambda c, r: (n-r, n-c),     # 7 反對角線轉置
    )
    fn = TRANSFORMS[t]

    def xf_pair(pair: str) -> str:
        if len(pair) != 2 or pair == 'tt':
            return pair
        c = ord(pair[0]) - 97
        r = ord(pair[1]) - 97
        if not (0 <= c < N and 0 <= r < N):
            return pair
        nc, nr = fn(c, r)
        return chr(nc + 97) + chr(nr + 97)

    # 只替換跟在 B / W / AB / AW 後面的座標括號
    def replace_prop(m2):
        prop = m2.group(1)
        coords_block = m2.group(2)
        new_block = _re_mod.sub(
            r'\[([a-s]{2}|tt)\]',
            lambda cm: '[' + xf_pair(cm.group(1)) + ']',
            coords_block
        )
        return prop + new_block

    return _re_mod.sub(
        r'(;?\s*(?:AB|AW|B|W))((?:\s*\[[a-s]{2}\]|\[tt\])+)',
        replace_prop,
        content
    )

def _build_rt_pool():
    global _RT_POOL, _RT_POOL_READY
    pool = []
    for q in _load_questions():
        if not q.get('enabled', True):
            continue
        disc      = q.get('discipline', '')
        match_val = q.get('match', '')
        raw_rating = q.get('rating') or 0
        gap        = q.get('score_gap') or 0

        # ── 模式 A：題目已有 KataGo 分析資料（match / score_gap / rating）──
        if match_val in ('OK', 'NG') and raw_rating and gap:
            if match_val == 'OK':
                thresh = _RT_DISC_THRESH.get(disc)
            else:
                thresh = _RT_DISC_THRESH_NG.get(disc)
            if thresh is None:
                continue
            rating = float(raw_rating)
            if not (1100 <= rating <= 2500):
                continue
            if rating >= 2200:
                if gap < 3.0:
                    continue
            elif gap < thresh:
                continue
        # ── 模式 B：尚未分析，用 rank 欄位合成 rating（fallback）────────
        else:
            rank = q.get('rank') or q.get('difficulty') or ''
            rating = _RANK_TO_RATING.get(rank, 0)
            if not rating:
                continue   # 連 rank 也沒有，跳過
            gap = 0.0      # 無 score_gap 資料，視為 0

        pool.append({
            'id':               q['id'],
            'content':          q.get('content', ''),
            'rating':           rating,
            'difficulty':       q.get('difficulty') or q.get('rank', ''),
            'discipline':       disc,
            'katago_best_move': (q.get('katago_best_move') or '').upper().strip(),
            'score_gap':        gap,
        })
    pool.sort(key=lambda x: x['rating'])
    _RT_POOL = pool
    _RT_POOL_READY = True
    return len(pool)

def _ensure_rt_pool():
    if not _RT_POOL_READY:
        _build_rt_pool()

# ── Elo 工具函式 ─────────────────────────────────────────────────────────────
_RT_TOTAL_ROUNDS = 12

def _elo_update(cur: float, q_rating: float, correct: bool, k: float) -> float:
    expected = 1.0 / (1.0 + 10.0 ** ((q_rating - cur) / 400.0))
    return cur + k * ((1.0 if correct else 0.0) - expected)

def _compute_streak(prev_answers: list, latest_correct: bool) -> int:
    """
    計算包含本題在內的連勝(正數)/連敗(負數)條數。
    用於 Adaptive Acceleration：連勝說明題目遠低於真實棋力，加速爬升。
    """
    streak = 1 if latest_correct else -1
    for ans in reversed(prev_answers):
        if latest_correct and ans.get('correct'):
            streak += 1
        elif not latest_correct and not ans.get('correct'):
            streak -= 1
        else:
            break
    return streak

def _k_for_round(round_idx: int, streak: int = 0) -> float:
    """
    動態 K 值：連勝/連敗加速，交替對錯精密收斂。

    優化原理（參考 Adaptive Acceleration 演算法）：
    - 連勝 >= 2：代表題目遠低於玩家真實棋力，開啟助推讓強者快速爬升
    - 連敗 >= 2：代表玩家確實不熟此難度，加速下調定位
    - 對錯交替（streak = ±1）：逼近實力邊界，倍率歸 1.0x 精密收斂

    與對方 AI 的差異：
    - 我們 base_K=40/24，探索期夠大讓強者快速爬升
    - 最大倍率 2.0x（連勝加速上限，防止過度膨脹）
    - 配合 bracket 1500=5k（讓段位分布更貼近實際）
    """
    base_K = 40.0 if round_idx < 8 else 24.0
    if streak >= 2:
        # 連勝加速：streak=2→1.4x, 3→1.8x, 4+→2.0x（上限 2.0x 防止過度膨脹）
        multiplier = min(2.0, 1.0 + (streak - 1) * 0.4)
    elif streak <= -2:
        # 連敗加速：streak=-2→1.3x, -3→1.6x（上限 1.6x，避免強者偶失誤被大幅懲罰）
        multiplier = min(1.6, 1.0 + (abs(streak) - 1) * 0.3)
    else:
        # ±1 交替 = 精密收斂，倍率 1.0x
        multiplier = 1.0
    return base_K * multiplier

def _rating_to_rank(rating: float) -> str:
    """
    對應題庫難度分布（diff 1-10 → rating 940-2200）的合理段位對照。
    舊版把 1500 對應到業餘 2k（接近初段），
    導致隨便答題就跑到 6d；新版把 1500 對應到 10k（中級入門），
    讓段位分布更符合實際棋力。
    """
    brackets = [
        (0,    1000, '25k+'),   # diff 1 以下
        (1000, 1100, '20k'),
        (1100, 1200, '15k'),
        (1200, 1300, '12k'),    # diff 3
        (1300, 1400, '10k'),    # diff 4
        (1400, 1500, '8k'),
        (1500, 1600, '5k'),     # diff 5（測驗起始點）
        (1600, 1700, '3k'),     # diff 6
        (1700, 1800, '1k'),     # diff 7
        (1800, 1900, '1d'),
        (1900, 2000, '2d'),     # diff 8
        (2000, 2100, '3d'),     # diff 9
        (2100, 2200, '4d'),
        (2200, 2300, '5d'),     # diff 10（高段題入池）
        (2300, 2400, '6d'),
        (2400, 9999, '7d+'),
    ]
    for lo, hi, label in brackets:
        if lo <= rating < hi:
            return label
    return '6d+'

def _pick_question(cur_rating: float, round_idx: int, used_ids: set,
                   streak: int = 0, prev_streak: int = 0) -> dict | None:
    """
    從 gold pool 按當前 rating 選出下一題。

    【連勝跳題機制】（Streak Target Boost）：
    題庫 diff-7(1700) → diff-8(1900) 有 200 Elo 斷層，純靠 cur_rating 追蹤
    會讓強者永遠困在 diff-7。加入 streak 時的 target 偏移：
    - streak >= 3：target+150（開始跨過斷層）
    - streak >= 5：target+250（完全跳到更高難度區）

    【高連勝後失誤保護】（High-Streak Miss Protection）：
    強者偶爾答錯難題時，prev_streak >= 4（曾有 4 連勝），當前 streak < 0，
    仍保留部分 boost 而非直接掉回入門題，避免誤判棋力。

    【熱身題自適應】：
    前兩題根據 cur_rating 選題：強者（cur_rating >= 1900）直接從 diff-7~9 開始，
    避免前 6 題全是入門題。
    """
    _ensure_rt_pool()

    # 連勝偏移量（指數跳階：1 連勝就開始助推，讓強者快速定位）
    # 設計原則：correct × n → 每次翻倍跳題難度，錯誤只溫和退後
    if streak >= 5:
        boost = 400 if round_idx < 8 else 250
    elif streak >= 3:
        boost = 300 if round_idx < 8 else 180
    elif streak == 2:
        boost = 200 if round_idx < 8 else 100
    elif streak == 1:
        # 第一題答對就開始助推（讓強者的「秒殺」立刻被感知）
        boost = 100 if round_idx < 8 else 50
    elif streak < 0 and prev_streak >= 4:
        # 高連勝後首次失誤：保留 50% 前次 boost，避免強者被打回入門題
        boost = 150 if round_idx < 8 else 80
    else:
        boost = 0

    if round_idx < 2:
        # 前 2 題：從「1k 水準（1750）」出發，而非 5k（1500）
        # 讓高手第一題就能秒殺，確認強度後立刻跳階；新手也不會一開始就撞牆
        target, spread = max(1750.0, cur_rating), 280.0
    elif round_idx < 8:
        # 探索期：追蹤 cur_rating + streak boost，spread=220 橋接斷層
        target, spread = cur_rating + boost, 220.0
    else:
        # 收斂期：精準收斂，spread=150 保留橋接能力
        target, spread = cur_rating + boost, 150.0

    candidates = [q for q in _RT_POOL
                  if abs(q['rating'] - target) <= spread
                  and q['id'] not in used_ids]

    if not candidates:
        candidates = sorted(
            (q for q in _RT_POOL if q['id'] not in used_ids),
            key=lambda q: abs(q['rating'] - cur_rating)
        )[:15]

    if not candidates:
        return None

    candidates.sort(key=lambda q: abs(q['rating'] - target))
    return random.choice(candidates[:10])

def _strip_question(q: dict) -> dict:
    """只回傳前端需要的欄位，並隨機套用幾何旋轉讓同一題產生 8 種視覺版本。"""
    t = random.randint(0, 7)
    content = _transform_sgf(q['content'], t)
    return {
        'id':         q['id'],
        'content':    content,
        'rating':     q['rating'],
        'difficulty': q['difficulty'],
        'discipline': q['discipline'],
    }

def _get_recent_seen_ids(uid, n_sessions: int = 3) -> set:
    """
    回傳用戶最近 n 場已完成測驗的所有答題 question_id。
    在下一場測驗中排除這些題，避免重複。
    n_sessions=3 → 最多排除 36 題（3 場 × 12 題），對 13,623 題庫幾乎無影響。
    """
    if not uid:
        return set()
    with get_db() as conn:
        rows = conn.execute(
            'SELECT answers FROM rating_test_sessions '
            'WHERE user_id=? AND status=? '
            'ORDER BY finished_at DESC LIMIT ?',
            (uid, 'completed', n_sessions)
        ).fetchall()
    seen = set()
    for row in rows:
        try:
            for ans in json.loads(row['answers'] or '[]'):
                if ans.get('q_id'):
                    seen.add(ans['q_id'])
        except Exception:
            pass
    return seen


# ── API 路由 ─────────────────────────────────────────────────────────────────

@app.route('/api/rating_test/pool_info')
def rt_pool_info():
    """回傳題庫規模（供介紹頁面顯示真實數字）。"""
    _ensure_rt_pool()
    return jsonify({'pool_size': len(_RT_POOL)})


@app.route('/api/rating_test/start', methods=['POST'])
def rt_start():
    """建立新測驗 session，回傳第一題。"""
    _ensure_rt_pool()
    uid = session.get('user_id')
    body = request.get_json(silent=True) or {}
    trigger = body.get('trigger', 'manual')

    init_rating = 1500.0
    requested_init = body.get('init_elo')
    if requested_init is not None:
        try:
            init_rating = max(700.0, min(2500.0, float(requested_init)))
        except Exception:
            init_rating = 1500.0
    # 若用戶已有 Elo，從上次結果出發（縮短探索時間）
    # 但最高只能帶入 1750（diff-7 對應的 1k）以防多次測驗無限制累積
    if uid and requested_init is None:
        with get_db() as conn:
            row = conn.execute('SELECT elo_rating FROM users WHERE id=?', (uid,)).fetchone()
            if row and row['elo_rating']:
                prev = float(row['elo_rating'])
                if prev >= 1800:
                    # 高段玩家（1段以上）：輕微回歸 7%，保留 93% 真實棋力
                    # 上限 2500 讓 7 段玩家能從 7 段難題出發，不再被壓低到 5d
                    init_rating = min(prev * 0.93 + 1500.0 * 0.07, 2500.0)
                else:
                    # 一般玩家：適度回歸 20%，避免雪球效應
                    init_rating = min(prev * 0.80 + 1500.0 * 0.20, 2000.0)

    sid = str(uuid.uuid4())
    # 排除近 3 場測驗已出現的題目，防止跨場重複
    recent_ids = _get_recent_seen_ids(uid)
    first_q = _pick_question(init_rating, 0, recent_ids)
    if not first_q:
        return jsonify({'error': 'no_questions'}), 503

    answers_init = []
    with get_db() as conn:
        conn.execute(
            'INSERT INTO rating_test_sessions '
            '(id,user_id,status,init_rating,cur_rating,round,answers,trigger,started_at) '
            'VALUES (?,?,?,?,?,?,?,?,?)',
            (sid, uid, 'in_progress', init_rating, init_rating,
             0, json.dumps(answers_init), trigger,
             datetime.datetime.utcnow().isoformat())
        )
        conn.commit()

    return jsonify({
        'session_id':   sid,
        'round':        1,
        'total_rounds': _RT_TOTAL_ROUNDS,
        'question':     _strip_question(first_q),
        'cur_rating':   init_rating,
        'pool_size':    len(_RT_POOL),
    })


@app.route('/api/rating_test/answer', methods=['POST'])
def rt_answer():
    """接收一題的作答，計算 Elo，回傳下一題或結束訊號。"""
    body = request.get_json(silent=True) or {}
    sid     = body.get('session_id', '')
    q_id    = body.get('question_id')
    # 前端已透過 SGF 樹判斷正確性，直接傳 correct 布林
    correct = bool(body.get('correct', False))

    with get_db() as conn:
        row = conn.execute(
            'SELECT * FROM rating_test_sessions WHERE id=?', (sid,)
        ).fetchone()
        if not row or row['status'] != 'in_progress':
            return jsonify({'error': 'invalid_session'}), 400

        cur_rating      = float(row['cur_rating'])
        round_idx       = int(row['round'])        # 0-based index
        answers         = json.loads(row['answers'])
        used_ids        = {a['q_id'] for a in answers}
        session_trigger = row['trigger'] or 'manual'

    # 找回這題的 gold pool 資料（取 rating 用，不再比對 GTP）
    _ensure_rt_pool()
    pool_q = next((q for q in _RT_POOL if q['id'] == q_id), None)
    if not pool_q:
        return jsonify({'error': 'question_not_found'}), 404

    # 計算連勝/連敗 streak → 動態 K 值（Adaptive Acceleration）
    streak = _compute_streak(answers, correct)
    k_val  = _k_for_round(round_idx, streak)

    new_rating = _elo_update(cur_rating, pool_q['rating'], correct, k_val)
    # 限制 Elo 在合理範圍（上限拉到 2500 讓頂尖玩家有空間）
    new_rating = max(700.0, min(2500.0, new_rating))

    answers.append({
        'q_id':          q_id,
        'correct':       correct,
        'discipline':    pool_q['discipline'],
        'q_rating':      pool_q['rating'],
        'rating_before': cur_rating,
        'rating_after':  new_rating,
        'streak':        streak,
        'k_val':         round(k_val, 1),
    })
    round_idx += 1

    # ── 棋力測驗錯題寫入錯題本 ────────────────────────────────────────
    uid = session.get('user_id')
    now_iso = datetime.datetime.utcnow().isoformat()
    if uid:
        with get_db() as conn:
            mrow = conn.execute(
                'SELECT wrong_count FROM mistake_log WHERE user_id=? AND question_id=?',
                (uid, q_id)
            ).fetchone()
            if not correct:
                # 答錯：新增或累計錯誤次數
                if mrow:
                    conn.execute(
                        'UPDATE mistake_log SET wrong_count=wrong_count+1, last_wrong_at=? '
                        'WHERE user_id=? AND question_id=?',
                        (now_iso, uid, q_id)
                    )
                else:
                    conn.execute(
                        'INSERT INTO mistake_log'
                        '(user_id,question_id,wrong_count,correct_after,first_wrong_at,last_wrong_at) '
                        'VALUES(?,?,1,0,?,?)',
                        (uid, q_id, now_iso, now_iso)
                    )
            else:
                # 答對且曾經記錄為錯題 → 更新 correct_after（記錄改正次數）
                if mrow:
                    conn.execute(
                        'UPDATE mistake_log SET correct_after=correct_after+1, last_correct_at=? '
                        'WHERE user_id=? AND question_id=?',
                        (now_iso, uid, q_id)
                    )
            conn.commit()

    # 測驗結束？（placement 模式只用 5 題）
    _PLACEMENT_ROUNDS = 5
    is_placement = (str(session_trigger).strip() == 'placement')
    _total_rounds = _PLACEMENT_ROUNDS if is_placement else _RT_TOTAL_ROUNDS
    finished = (round_idx >= _total_rounds)

    if finished:
        with get_db() as conn:
            conn.execute(
                'UPDATE rating_test_sessions '
                'SET status=?,cur_rating=?,round=?,answers=?,finished_at=? WHERE id=?',
                ('completed', new_rating, round_idx,
                 json.dumps(answers),
                 datetime.datetime.utcnow().isoformat(), sid)
            )
            # 回寫 Elo 到 users 表
            uid = conn.execute(
                'SELECT user_id FROM rating_test_sessions WHERE id=?', (sid,)
            ).fetchone()
            if uid and uid['user_id']:
                conn.execute(
                    'UPDATE users SET elo_rating=?,elo_updated_at=? WHERE id=?',
                    (new_rating, datetime.datetime.utcnow().isoformat(), uid['user_id'])
                )
            conn.commit()
            start_zone_key = _apply_placement_adventure_unlock(uid['user_id'], new_rating, 'placement_test') if uid and uid['user_id'] and is_placement else None

        rating_change = round(new_rating - cur_rating, 1)
        return jsonify({
            'correct':       correct,
            'best_move':     pool_q['katago_best_move'],
            'finished':      True,
            'session_id':    sid,
            'cur_rating':    new_rating,
            'rating_change': rating_change,
            'streak':        streak,
            'rank_label':    _rating_to_rank(new_rating),
            'start_zone_key': start_zone_key,
        })

    # 繼續測驗：選下一題
    with get_db() as conn:
        conn.execute(
            'UPDATE rating_test_sessions '
            'SET cur_rating=?,round=?,answers=? WHERE id=?',
            (new_rating, round_idx, json.dumps(answers), sid)
        )
        conn.commit()

    # prev_streak：本題答題前的連勝/連敗條數（用於高連勝後失誤保護）
    # answers[-2] 是上一題，其 streak 即為答本題前的狀態
    prev_streak = answers[-2]['streak'] if len(answers) >= 2 else 0
    # 排除本場已答 + 近 3 場歷史題，防止跨場重複
    recent_ids = _get_recent_seen_ids(uid)
    session_ids = {a['q_id'] for a in answers}
    next_q = _pick_question(new_rating, round_idx, session_ids | recent_ids, streak, prev_streak)
    if not next_q:
        # 極端情況：題庫耗盡，直接結束
        return jsonify({
            'correct':  correct,
            'best_move': pool_q['katago_best_move'],
            'finished': True,
            'session_id': sid,
            'cur_rating': new_rating,
            'rank_label': _rating_to_rank(new_rating),
        })

    rating_change = round(new_rating - cur_rating, 1)
    return jsonify({
        'correct':       correct,
        'best_move':     pool_q['katago_best_move'],
        'finished':      False,
        'round':         round_idx + 1,
        'total_rounds':  _RT_TOTAL_ROUNDS,
        'question':      _strip_question(next_q),
        'cur_rating':    new_rating,
        'rating_change': rating_change,
        'streak':        streak,
        'rank_label':    _rating_to_rank(new_rating),
    })


@app.route('/api/rating_test/result/<sid>')
def rt_result(sid):
    """回傳完整測驗結果（雷達圖資料、學科分析、SP 統計）。"""
    with get_db() as conn:
        row = conn.execute(
            'SELECT * FROM rating_test_sessions WHERE id=?', (sid,)
        ).fetchone()
    if not row:
        return jsonify({'error': 'not_found'}), 404

    answers = json.loads(row['answers'])
    final_rating = float(row['cur_rating'])

    # 各學科答對率
    disc_stats: dict[str, dict] = {}
    for a in answers:
        disc = a.get('discipline', 'unknown')
        if disc not in disc_stats:
            disc_stats[disc] = {'correct': 0, 'total': 0}
        disc_stats[disc]['total'] += 1
        if a['correct']:
            disc_stats[disc]['correct'] += 1

    radar = {}
    for disc, s in disc_stats.items():
        acc = s['correct'] / s['total'] if s['total'] else 0
        # 加權估算：Elo × 答對率 → 0-100 分
        avg_q_rating = sum(
            a['q_rating'] for a in answers if a.get('discipline') == disc
        ) / s['total']
        radar[disc] = round(acc * (avg_q_rating - 800) / (2200 - 800) * 100, 1)

    # SP 統計（只計答對題）
    sp_by_disc: dict[str, int] = {}
    for a in answers:
        if a['correct']:
            sp_by_disc[a.get('discipline', '')] = \
                sp_by_disc.get(a.get('discipline', ''), 0) + 1

    # 最弱學科（答對率最低，且答對率 < 100% 才算弱點）
    weakest = None
    if disc_stats:
        candidate = min(disc_stats, key=lambda d: (
            disc_stats[d]['correct'] / disc_stats[d]['total']
            if disc_stats[d]['total'] else 1.0
        ))
        rate = (disc_stats[candidate]['correct'] / disc_stats[candidate]['total']
                if disc_stats[candidate]['total'] else 1.0)
        if rate < 1.0:
            weakest = candidate

    return jsonify({
        'final_rating':  final_rating,
        'rank_label':    _rating_to_rank(final_rating),
        'init_rating':   float(row['init_rating']),
        'answers':       answers,
        'disc_stats':    disc_stats,
        'radar':         radar,
        'sp_by_disc':    sp_by_disc,
        'weakest_disc':  weakest,
        'trigger':       row['trigger'],
    })


@app.route('/api/rating_test/placement_finish', methods=['POST'])
@login_required
def rt_placement_finish():
    """前端 placement 模式的強制結束端點：寫入 elo_rating，標記 session completed。
    用於雙重保險：即使 rt_answer 的 placement 偵測出問題，前端也能保證 Elo 被儲存。"""
    body = request.get_json() or {}
    sid  = body.get('session_id', '')
    uid  = session['user_id']

    with get_db() as conn:
        row = conn.execute(
            'SELECT cur_rating, status FROM rating_test_sessions WHERE id=? AND user_id=?',
            (sid, uid)
        ).fetchone()
        if not row:
            return jsonify({'error': 'not_found'}), 404

        cur_rating = float(row['cur_rating'])
        now_iso    = datetime.datetime.utcnow().isoformat()

        # 標記 session completed（若尚未完成）
        if row['status'] != 'completed':
            conn.execute(
                'UPDATE rating_test_sessions SET status=?, finished_at=? WHERE id=?',
                ('completed', now_iso, sid)
            )

        # 寫入 users.elo_rating（強制覆蓋，placement 的結果優先）
        conn.execute(
            'UPDATE users SET elo_rating=?, elo_updated_at=? WHERE id=?',
            (cur_rating, now_iso, uid)
        )
        conn.commit()
    start_zone_key = _apply_placement_adventure_unlock(uid, cur_rating, 'placement_test')

    return jsonify({
        'ok':         True,
        'cur_rating': cur_rating,
        'rank_label': _rating_to_rank(cur_rating),
        'start_zone_key': start_zone_key,
    })


@app.route('/api/rating_test/claim_sp', methods=['POST'])
def rt_claim_sp():
    """將測驗答對的題目寫入 review_log，給予技能樹 SP 加成（每個 session 只能兌換一次）。"""
    uid = session.get('user_id')
    if not uid:
        return jsonify({'error': 'login_required'}), 401

    body = request.get_json(silent=True) or {}
    sid  = body.get('session_id', '')

    with get_db() as conn:
        row = conn.execute(
            'SELECT * FROM rating_test_sessions WHERE id=? AND user_id=? AND status=?',
            (sid, uid, 'completed')
        ).fetchone()
        if not row:
            return jsonify({'error': 'invalid_session'}), 400

        # 防止重複兌換：檢查是否已寫過 review_log（以 source='rt:sid' 標記）
        already = conn.execute(
            "SELECT COUNT(*) as c FROM review_log "
            "WHERE user_id=? AND source=?", (uid, f'rt:{sid}')
        ).fetchone()
        if already and already['c'] > 0:
            return jsonify({'claimed': False, 'msg': 'already_claimed'})

        answers = json.loads(row['answers'])
        now = datetime.datetime.utcnow().isoformat()
        added = 0
        for a in answers:
            if not a.get('correct'):
                continue
            # 寫入 review_log（grade=4 代表答對）
            conn.execute(
                'INSERT INTO review_log '
                '(user_id, question_id, grade, reviewed_at, source) '
                'VALUES (?,?,?,?,?)',
                (uid, a['q_id'], 4, now, f'rt:{sid}')
            )
            added += 1

        conn.commit()

    # 觸發技能樹同步
    with get_db() as conn:
        sync_skill_tree(uid, conn)

    return jsonify({'claimed': True, 'sp_added': added})


# ── 供 /api/skills/profile 顯示 Elo 資訊 ────────────────────────────────────
# （已有的 endpoint 會自動從 users 表讀取 elo_rating，無需修改）


if __name__ == '__main__':
    init_db()
    socketio.run(app, host='0.0.0.0', debug=False, port=5000, allow_unsafe_werkzeug=True)

