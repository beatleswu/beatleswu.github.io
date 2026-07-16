from flask import (Flask, jsonify, send_from_directory, request,
                   session, redirect, Response, send_file, abort)
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from collections import Counter
import psycopg2
import json, os, subprocess, threading, queue, uuid, time, sqlite3, datetime, secrets, bisect
import csv, io
import math, re
import mimetypes
import urllib.parse
import importlib.util
from psycopg2 import sql
from psycopg2.extras import DictCursor
# slim 映像缺 /etc/mime.types，手動註冊常見靜態類型，避免 send_from_directory 回 octet-stream
mimetypes.add_type('image/webp', '.webp')
mimetypes.add_type('image/svg+xml', '.svg')
import random, string
import hashlib
import urllib.request
import urllib.error
try:
    from flask_compress import Compress as _FlaskCompress
    _has_compress = True
except ImportError:
    _has_compress = False
from katago_explain import KataGoExplainer
from explain_overrides import get_override as _get_explain_override
from grimoire_api import grimoire_bp
from question_taxonomy import get_taxonomy
from monster_taxonomy import get_monster_taxonomy, mark_encounters
from chapter_i18n import localize_topic as _i18n_topic_en, localize_level as _i18n_level_en
from backend_i18n import badge_en as _i18n_badge_en, skill_node_en as _i18n_skill_node_en, title_en as _i18n_title_en
from sgf_engine.parser.sgf_parser import parse_sgf
from shadow_dashboard import aggregate_shadow_events, recent_shadow_dashboard_data

app = Flask(__name__)
_site_url_for_cookie = os.environ.get('SITE_URL', 'https://godokoro.com').lower()
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=_site_url_for_cookie.startswith('https://'),
)
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
_socketio_async_mode = os.environ.get('SOCKETIO_ASYNC_MODE')
if not _socketio_async_mode:
    _socketio_async_mode = 'gevent' if importlib.util.find_spec('gevent') else 'threading'
socketio = SocketIO(app, cors_allowed_origins='*', async_mode=_socketio_async_mode,
                    message_queue=os.environ.get('SOCKETIO_MESSAGE_QUEUE') or None,
                    manage_session=False)
app.register_blueprint(grimoire_bp)

@app.route('/healthz')
def healthz():
    return jsonify({'ok': True})

@app.route('/api/healthz')
def api_healthz():
    return jsonify({'ok': True})


_ANALYTICS_EVENT_ENDPOINT_MAX_BYTES = 4096
_ANALYTICS_EVENT_ALLOWLIST = {
    'premium_upgrade_cta_view',
    'premium_upgrade_cta_click',
}
_ANALYTICS_EVENT_ALLOWED_FIELDS = {
    'event_name',
    'occurred_at',
    'session_id',
    'anonymous_session_id',
    'surface',
    'locale',
    'source_page',
    'cta_variant',
    'destination',
}

_E9_FLAG_KEYS = (
    'e9Shell', 'e9TopHud', 'e9LeftNav', 'e9RightCards',
    'e9BottomDock', 'e9WorldStage',
)
_E9_REASON_CODES = {
    'global_disabled', 'admin_entitled', 'named_allowlist',
    'not_allowed', 'unauthenticated', 'invalid_config',
}

def _e9_truthy_env(name):
    return os.environ.get(name, '').strip().lower() in {'1', 'true', 'yes', 'on'}

def _e9_normalize_identity(value):
    return str(value or '').strip().casefold()

def _e9_rollout_config():
    """Load server-only E9 targeting config; malformed config fails closed."""
    raw_scope = os.environ.get('E9_ROLLOUT_SCOPE', 'admin_only').strip().casefold()
    if raw_scope not in {'admin_only', 'named_allowlist'}:
        return None
    raw_allowlist = os.environ.get('E9_ROLLOUT_ALLOWLIST', '')
    entries = [_e9_normalize_identity(x) for x in raw_allowlist.split(',') if x.strip()]
    if any(not x or not re.fullmatch(r'[a-z0-9_@.+-]{1,160}', x) for x in entries):
        return None
    if len(entries) != len(set(entries)):
        return None
    if raw_scope == 'admin_only' and entries:
        return None
    raw_flags = os.environ.get('E9_ROLLOUT_FLAGS', ','.join(_E9_FLAG_KEYS))
    flags = [x.strip() for x in raw_flags.split(',') if x.strip()]
    if not flags or any(x not in _E9_FLAG_KEYS for x in flags) or 'e9Shell' not in flags:
        return None
    config = {
        'scope': raw_scope,
        'global_enabled': _e9_truthy_env('E9_ROLLOUT_GLOBAL_ENABLED'),
        'admin_enabled': _e9_truthy_env('E9_ROLLOUT_ADMIN_ENABLED'),
        'allowlist': tuple(sorted(set(entries))),
        'flags': tuple(flags),
    }
    config['identity'] = hashlib.sha256(
        json.dumps(config, sort_keys=True, separators=(',', ':')).encode()
    ).hexdigest()[:16]
    return config

def _e9_rollout_decision(*, user_id=None, username=None, is_admin=False):
    false_flags = {key: False for key in _E9_FLAG_KEYS}
    config = _e9_rollout_config()
    if not config:
        return {'eligible': False, 'reason': 'invalid_config', 'effective_flags': false_flags,
                'decision_version': 'e9-rollout-v1-invalid', 'kill_switch': True}
    base = {'decision_version': f"e9-rollout-v1-{config['identity']}",
            'kill_switch': not config['global_enabled']}
    if not user_id or not username:
        reason = 'unauthenticated'
    elif not config['global_enabled']:
        reason = 'global_disabled'
    elif config['admin_enabled'] and is_admin:
        reason = 'admin_entitled'
    elif config['scope'] == 'named_allowlist' and _e9_normalize_identity(username) in config['allowlist']:
        reason = 'named_allowlist'
    else:
        reason = 'not_allowed'
    eligible = reason in {'admin_entitled', 'named_allowlist'}
    flags = {key: bool(eligible and key in config['flags']) for key in _E9_FLAG_KEYS}
    if not flags['e9Shell']:
        flags = false_flags
    return {'eligible': eligible, 'reason': reason, 'effective_flags': flags, **base}

def _e9_rollout_telemetry(decision, user_id=None):
    digest = hashlib.sha256(str(user_id).encode()).hexdigest()[:16] if user_id else None
    app.logger.info('[e9_rollout_decision] %s', json.dumps({
        'eligible': decision['eligible'], 'reason': decision['reason'],
        'effective_flags': decision['effective_flags'],
        'decision_version': decision['decision_version'],
        'kill_switch': decision['kill_switch'], 'user_digest': digest,
        'surface': request.path,
    }, sort_keys=True, separators=(',', ':')))

QUESTION_PROBLEM_REPORT_REASON_CODES = (
    'broken_unanswerable',
    'answer_seems_wrong',
    'unclear',
    'wrong_difficulty',
    'wrong_category',
    'display_glitch',
    'other',
    'no_valid_answer',
)
QUESTION_PROBLEM_REPORT_STATUSES = ('open', 'confirmed', 'dismissed', 'duplicate')
REVIEW_QUEUE_SOURCE_TYPES = (
    'p0_parse_failure',
    'duplicate_group',
    'still_fails',
    'not_gn_pattern',
    'player_reported',
    'manual_flag',
)
REVIEW_QUEUE_RESOLUTION_ACTIONS = (
    'confirmed_needs_repair',
    'wont_fix',
    'needs_source_material',
    'dismissed_false_positive',
    'repair_proposed',
)
REVIEW_QUEUE_SOURCE_BATCH = '22C-triage-20260710'


def _analytics_clean_text(value, *, max_len=200):
    if value is None:
        return None
    text = str(value).replace('\r', ' ').replace('\n', ' ').replace('\t', ' ').strip()
    if not text:
        return None
    return text[:max_len]


def _analytics_event_response(error, status=400):
    return jsonify({'error': error}), status


@app.route('/api/analytics/events', methods=['POST'])
def api_analytics_events():
    if not request.is_json:
        return _analytics_event_response('invalid_json')

    raw = request.get_data(cache=False, as_text=False) or b''
    if not raw:
        return _analytics_event_response('invalid_json')
    if len(raw) > _ANALYTICS_EVENT_ENDPOINT_MAX_BYTES:
        return _analytics_event_response('payload_too_large')

    try:
        payload = json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _analytics_event_response('invalid_json')

    if not isinstance(payload, dict):
        return _analytics_event_response('invalid_json')
    if set(payload) - _ANALYTICS_EVENT_ALLOWED_FIELDS:
        return _analytics_event_response('unexpected_fields')

    event_name = _analytics_clean_text(payload.get('event_name'), max_len=80)
    if not event_name:
        return _analytics_event_response('missing_event_name')
    if event_name not in _ANALYTICS_EVENT_ALLOWLIST:
        return _analytics_event_response('unsupported_event')

    occurred_at = _analytics_clean_text(payload.get('occurred_at'), max_len=80)
    session_id = _analytics_clean_text(payload.get('session_id') or payload.get('anonymous_session_id'), max_len=120)
    surface = _analytics_clean_text(payload.get('surface'), max_len=120)
    locale = _analytics_clean_text(payload.get('locale'), max_len=40)
    source_page = _analytics_clean_text(payload.get('source_page'), max_len=200)
    cta_variant = _analytics_clean_text(payload.get('cta_variant'), max_len=120)
    destination = _analytics_clean_text(payload.get('destination'), max_len=200)

    if not occurred_at or not session_id or not surface or not locale:
        return _analytics_event_response('missing_required_fields')
    if event_name == 'premium_upgrade_cta_click' and not destination:
        return _analytics_event_response('missing_destination')

    sanitized = {
        'event_id': uuid.uuid4().hex,
        'event_name': event_name,
        'occurred_at': occurred_at,
        'session_id': session_id,
        'surface': surface,
        'locale': locale,
    }
    if source_page:
        sanitized['source_page'] = source_page
    if cta_variant:
        sanitized['cta_variant'] = cta_variant
    if destination:
        sanitized['destination'] = destination

    app.logger.info('[analytics_event] %s', json.dumps(sanitized, ensure_ascii=False, separators=(',', ':')))
    return ('', 204)

@app.after_request
def add_no_cache_headers(response):
    """自訂 JS 短暫快取；HTML 讓瀏覽器必須 revalidate（304 機制）。"""
    ct = response.content_type or ''
    path = request.path or ''
    if path.startswith('/api/'):
        response.headers['Cache-Control'] = 'private, no-store'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    if path.startswith('/premium/quest/') or path == '/premium/weekly':
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, private'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        if path.startswith('/premium/quest/'):
            response.headers['Referrer-Policy'] = 'no-referrer'
        return response
    is_nav_js = path in ('/mobile-nav.js', '/site-nav.js')
    is_own_js = path in ('/srs.js', '/i18n.js', '/mobile-nav.js', '/site-nav.js', '/sound.js')
    if is_nav_js:
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    elif is_own_js:
        # JS 可快取 60 秒，避免每次頁面切換重下載
        response.headers['Cache-Control'] = 'public, max-age=60'
    elif path.startswith('/assets/'):
        # 靜態素材（圖片/音檔/字型）快取一天，避免每次重開頁面都重載裝飾圖
        # 需更新素材時改檔名或加 ?v= 版本參數即可繞過快取
        response.headers['Cache-Control'] = 'public, max-age=86400'
    elif 'text/html' in ct:
        # HTML：允許快取但必須 revalidate（304 走快取，變更後才重下載）
        response.headers['Cache-Control'] = 'no-cache'
    return response

DATA_FILE = os.environ.get('QUESTIONS_JSON_PATH', 'questions.json')
CACHE_DB  = 'katago_cache.db'

DIFFICULTY_ORDER = [
    '30k','29k','28k','27k','26k','25k','24k','23k','22k','21k',
    '20k','19k','18k','17k','16k','15k','14k','13k','12k','11k',
    '10k','9k','8k','7k','6k','5k','4k','3k','2k','1k',
    '1d','2d','3d','4d','5d','6d','7d','8d','9d'
]

# ── 訂閱設定 ──────────────────────────────────────────────────
# 免費用戶每日最多可提交的 review 次數
FREE_DAILY_LIMIT = 20
# 免費版題庫上限（含此級）：此級或更弱的入門/基礎題開放，更高階鎖 Premium
# 圍棋 rank 由弱到強：30k…10k…1k…1d…7d；10k 以下（含）約佔題庫 27%
FREE_RANK_MAX = '10k'

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
DAILY_CHALLENGE_XP_REWARD = 50

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
    { 'id':'newbie_first_bounty', 'name':'新兵第一令', 'icon':'📜',
      'desc':'完成第一份新兵修行委託', 'type':'newbie_quest','value':1, 'rarity':'bronze' },
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
    { 'id':'daily_first', 'name':'初戰報到', 'icon':'📅', 'desc':'完成第一次每日懸賞令',           'type':'daily_challenge','value':0,   'rarity':'bronze'   },
    { 'id':'daily_ace',   'name':'一擊即中', 'icon':'🎯', 'desc':'正確完成每日懸賞令',           'type':'daily_challenge','value':0,   'rarity':'bronze'   },
    { 'id':'daily_3',     'name':'三日不輟', 'icon':'🌤️', 'desc':'連續 3 天完成每日懸賞令',      'type':'daily_challenge','value':3,   'rarity':'bronze'   },
    { 'id':'daily_7',     'name':'七日不怠', 'icon':'🗓️', 'desc':'連續 7 天完成每日懸賞令',      'type':'daily_challenge','value':7,   'rarity':'silver'   },
    { 'id':'daily_14',    'name':'兩週精進', 'icon':'🌙', 'desc':'連續 14 天完成每日懸賞令',     'type':'daily_challenge','value':14,  'rarity':'silver'   },
    { 'id':'daily_30',    'name':'月不間斷', 'icon':'🏆', 'desc':'連續 30 天完成每日懸賞令',     'type':'daily_challenge','value':30,  'rarity':'gold'     },
    { 'id':'daily_60',    'name':'六旬鑄志', 'icon':'⚜️', 'desc':'連續 60 天完成每日懸賞令',     'type':'daily_challenge','value':60,  'rarity':'gold'     },
    { 'id':'daily_100',   'name':'百日磨劍', 'icon':'✨', 'desc':'連續 100 天完成每日懸賞令',    'type':'daily_challenge','value':100, 'rarity':'gold'     },
    { 'id':'daily_200',   'name':'二百持恆', 'icon':'🌠', 'desc':'連續 200 天完成每日懸賞令',    'type':'daily_challenge','value':200, 'rarity':'legendary'},
    { 'id':'daily_365',   'name':'一年修行', 'icon':'🌟', 'desc':'連續 365 天完成每日懸賞令',    'type':'daily_challenge','value':365, 'rarity':'legendary'},

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

    # ── Community 排行榜獎勵（Phase 3B：僅 weekly top1，尚未實際發放）──
    { 'id':'badge_lb_weekly_1', 'name':'週榜冠軍', 'icon':'🥇', 'desc':'週排行榜奪得第一名', 'type':'community_leaderboard', 'value':1, 'rarity':'gold' },
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
        'hint': '完成 20 次每日懸賞令解鎖',
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
    {
        'id': 'title_newbie_voyage',
        'name': '棋海初航', 'slot': 'title', 'rarity': 'common',
        'emoji': '⛵', 'color': '#0d9488',
        'flavor': '揚帆棋海，初見天地廣闊。',
        'hint': '完成新手任務 Stage 3 解鎖',
        'drop_from': [], 'drop_weight': 0,
    },
    {
        'id': 'title_claire_recruit',
        'name': '克萊兒認證新兵', 'slot': 'title', 'rarity': 'uncommon',
        'emoji': '🎖️', 'color': '#7c3aed',
        'flavor': '克萊兒說：你已準備好踏上這片棋海。',
        'hint': '完成新手任務全部 7 個 Stage 解鎖',
        'drop_from': [], 'drop_weight': 0,
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
APPEARANCE_SLOT_KEYS = ('outfit', 'hat', 'back', 'title', 'accessory', 'pet', 'aura')
APPEARANCE_EQUIP_COLUMNS = tuple(f'{slot}_id' for slot in APPEARANCE_SLOT_KEYS)

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
    """取得玩家已裝備外觀的所有加成，回傳 {xp_bonus, drop_bonus}。
    效果端重驗：每件裝備需通過 _gear_unlocked（段位+累積答對），
    玩家掉段或門檻收緊後，DB 殘留的高階裝備不再給加成。"""
    try:
        eq = conn.execute(
            'SELECT pa.*, us.go_rank AS _fx_go_rank, us.total_correct AS _fx_total_correct '
            'FROM player_appearance pa '
            'LEFT JOIN user_stats us ON us.user_id = pa.user_id '
            'WHERE pa.user_id=?', (uid,)).fetchone()
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
    # ── 戰鬥裝備效果（與外觀效果整併成一套）──
    rank_tier = _rank_to_tier(eq['_fx_go_rank'] if '_fx_go_rank' in cols else '')
    total_correct = (eq['_fx_total_correct'] if '_fx_total_correct' in cols else 0) or 0
    def _tier(key):
        key = key or ''
        if '_t' in key:
            suf = key.rsplit('_t', 1)[-1]
            t = int(suf) if suf.isdigit() else 0
            # de-rank / 門檻未達 → 該件不給加成（但不強制卸下，外觀照舊）
            if t and not _gear_unlocked(key, rank_tier, total_correct):
                return 0
            return t
        return 0
    if 'combat_weapon'  in cols: xp_b   += _tier(eq['combat_weapon'])  * 0.01    # 武器 +XP
    if 'combat_cape'    in cols: xp_b   += _tier(eq['combat_cape'])    * 0.005   # 斗篷 +XP
    if 'combat_armor'   in cols: drop_b += _tier(eq['combat_armor'])   * 0.01    # 防具 +掉寶
    if 'combat_offhand' in cols: drop_b += _tier(eq['combat_offhand']) * 0.005   # 副手 +掉寶
    if 'combat_hat'     in cols: xp_b   += _tier(eq['combat_hat'])     * 0.005   # 頭飾 +XP
    if 'combat_aura'    in cols: xp_b   += _tier(eq['combat_aura'])    * 0.01    # 光環 +XP
    if 'combat_pet'     in cols: drop_b += _tier(eq['combat_pet'])     * 0.01    # 寵物 +掉寶
    if 'combat_acc'     in cols: drop_b += _tier(eq['combat_acc'])     * 0.01    # 配飾 +掉寶
    return {'xp_bonus': round(xp_b, 4), 'drop_bonus': round(drop_b, 4)}

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
    {'key':'kill_monsters',    'name':'戰士初試', 'name_en':"Warrior's First Trial", 'icon':'⚔️', 'desc':'擊敗 {target} 隻怪物',    'desc_en':'Defeat {target} monsters',          'target':5, 'xp':30,  'color':'amber'},
    {'key':'streak_correct',   'name':'精準術士', 'name_en':'Precision Mage',         'icon':'🎯', 'desc':'單日連續答對 {target} 題','desc_en':'Answer {target} in a row in one day','target':3, 'xp':20,  'color':'teal'},
    {'key':'challenge_dragon', 'name':'魔法大師', 'name_en':'Master Mage',            'icon':'🧙', 'desc':'挑戰 {target} 道龍族題', 'desc_en':'Challenge {target} dragon problems', 'target':1, 'xp':50,  'color':'purple'},
    {'key':'all_complete',     'name':'熾焰連斬', 'name_en':'Blazing Combo',          'icon':'🔥', 'desc':'完成以上全部任務',        'desc_en':'Complete all quests above',          'target':3, 'xp':100, 'color':'red', 'bonus':True},
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
    from db import get_db as _get_db
    return _get_db()

PET_CATALOG = {
    'star_shell_hatchling': {
        'key': 'star_shell_hatchling',
        'name': '星殼棋罐龍',
        'name_en': 'Star-Shell Hatchling',
        'role': '挑戰型',
        'role_en': 'Challenge',
        'ability': '連勝與 Boss 練習時，額外提升寵物經驗。',
        'ability_en': 'Gains extra pet XP from streaks and boss-style practice.',
        'personality': '笨拙、好奇，看到黑白棋子就會拍翅膀。',
        'personality_en': 'Clumsy and curious, fluttering at every black-and-white stone.',
        'image': '/assets/pets/pet_star_shell_hatchling_lv1.webp',
        'images': {
            1: '/assets/pets/pet_star_shell_hatchling_lv1.webp',
            2: '/assets/pets/dragon_anim_lv2/01_idle.webp',
            3: '/assets/pets/dragon_anim_lv3/01_idle.webp',
        },
        'stage_labels': {
            1: '幼龍',
            2: '星翼幼龍',
            3: '星環小龍',
        },
        'accent': '#b4660f',
        'starter_line': '牠從棋罐蛋殼裡探出頭，正等著你的第一口點心。',
        'starter_line_en': 'It peeks from its Go-jar shell, waiting for its first treat.',
    },
    'ink_drop_kelpie': {
        'key': 'ink_drop_kelpie',
        'name': '墨滴水靈馬',
        'name_en': 'Ink-Drop Kelpie',
        'role': '修行型',
        'role_en': 'Training',
        'ability': '每日穩定練習時，額外提升寵物經驗。',
        'ability_en': 'Gains extra pet XP from steady daily training.',
        'personality': '安靜、溫柔，會把心浮氣躁沉進水面下。',
        'personality_en': 'Quiet and gentle, settling restless thoughts beneath the water.',
        'image': '/assets/pets/pet_ink_drop_kelpie_lv1.webp',
        'images': {
            1: '/assets/pets/pet_ink_drop_kelpie_lv1.webp',
            2: '/assets/pets/horse_anim_lv2/01_idle.webp',
            3: '/assets/pets/horse_anim_lv3/01_idle.webp',
        },
        'stage_labels': {
            1: '墨滴水靈馬',
            2: '潮影水靈馬',
            3: '星潮水靈馬',
        },
        'accent': '#0b6f69',
        'starter_line': '牠的身體像一滴淡墨，棋子在水光裡慢慢流動。',
        'starter_line_en': 'Its body is a pale drop of ink, stones drifting through the waterlight.',
    },
    'whispering_void_kit': {
        'key': 'whispering_void_kit',
        'name': '低語虛空貓',
        'name_en': 'Whispering Void Kit',
        'role': '解析型',
        'role_en': 'Review',
        'ability': '錯題復盤與封印時，額外提升寵物經驗。',
        'ability_en': 'Gains extra pet XP from mistake review and sealing grudges.',
        'personality': '神秘、黏人，總像知道你下一手會下在哪。',
        'personality_en': 'Mysterious and clingy, as if it already knows your next move.',
        'image': '/assets/pets/pet_whispering_void_kit_lv1.webp',
        'images': {
            1: '/assets/pets/pet_whispering_void_kit_lv1.webp',
            2: '/assets/pets/cat_anim_lv2/01_idle.webp',
            3: '/assets/pets/cat_anim_lv3/01_idle.webp',
        },
        'stage_labels': {
            1: '低語虛空貓',
            2: '星霧虛空貓',
            3: '星淵虛空貓',
        },
        'accent': '#6d3bd0',
        'starter_line': '紫色眼睛眨了一下，兩枚棋子沿著星雲軌道輕輕旋轉。',
        'starter_line_en': 'Its violet eyes blink as two stones orbit through a little nebula.',
    },
}

PET_STARTER_KEY = 'ink_drop_kelpie'
PET_UNLOCK_ORDER = [
    'ink_drop_kelpie',
    'whispering_void_kit',
    'star_shell_hatchling',
]

PET_FOOD_CATALOG = {
    'go_spirit_candy': {
        'key': 'go_spirit_candy',
        'name': '棋魂糖',
        'name_en': 'Go Spirit Candy',
        'fullness': 24,
        'xp': 8,
        'affection': 4,
    },
    'starfruit': {
        'key': 'starfruit',
        'name': '星果',
        'name_en': 'Starfruit',
        'fullness': 38,
        'xp': 15,
        'affection': 7,
    },
    'moon_drop': {
        'key': 'moon_drop',
        'name': '月露',
        'name_en': 'Moon Drop',
        'fullness': 18,
        'xp': 25,
        'affection': 10,
    },
}

# ── Phase 1 防刷設定（寬鬆組）──────────────────────────────────
PET_PET_COOLDOWN_SEC   = 15 * 60   # 「拍拍」冷卻：15 分鐘
PET_DAILY_BOND_CAP     = 30        # 每日互動可得親密上限（拍拍＋修行合計）
PET_DAILY_TRAIN_XP_CAP = 160       # 每日「一起修行」可得 XP 上限
PET_EXPEDITION_DEFAULT_HOURS = 4
PET_EXPEDITION_ALLOWED_HOURS = {4, 8}

def _pet_today_key():
    return datetime.date.today().isoformat()

def _pet_daily_counters(row):
    """讀取寵物今日互動計數；跨日自動視為歸零。回傳 (bond_today, train_xp_today)。"""
    keys = row.keys()
    same_day = ('daily_key' in keys) and (row['daily_key'] == _pet_today_key())
    if not same_day:
        return 0, 0
    bond = int(row['daily_bond'] or 0) if 'daily_bond' in keys else 0
    txp  = int(row['daily_train_xp'] or 0) if 'daily_train_xp' in keys else 0
    return bond, txp

def _pet_cooldown_remaining(row, col, cooldown_sec):
    """回傳該互動還剩幾秒冷卻；0 表示可立即使用。"""
    keys = row.keys()
    if col not in keys or not row[col]:
        return 0
    try:
        last = datetime.datetime.fromisoformat(row[col])
    except Exception:
        return 0
    elapsed = (datetime.datetime.now() - last).total_seconds()
    return max(0, int(cooldown_sec - elapsed))

def _pet_interaction_state(row):
    """寵物互動的冷卻 / 每日上限狀態，供前端禁用按鈕與顯示倒數。"""
    if not row:
        return None
    bond_today, train_xp_today = _pet_daily_counters(row)
    return {
        'pet_cooldown': _pet_cooldown_remaining(row, 'last_pet_at', PET_PET_COOLDOWN_SEC),
        'pet_cooldown_total': PET_PET_COOLDOWN_SEC,
        'bond_today': bond_today,
        'bond_cap': PET_DAILY_BOND_CAP,
        'bond_full': bond_today >= PET_DAILY_BOND_CAP,
        'train_xp_today': train_xp_today,
        'train_xp_cap': PET_DAILY_TRAIN_XP_CAP,
        'train_full': train_xp_today >= PET_DAILY_TRAIN_XP_CAP,
    }

def _pet_training_state(row):
    if not row:
        return {'active': False, 'ready': False, 'remaining': 0, 'hours': 0}
    _, train_xp_today = _pet_daily_counters(row)
    remaining = max(0, PET_DAILY_TRAIN_XP_CAP - train_xp_today)
    return {
        'active': _decayed_fullness(row) > 0,
        'ready': remaining <= 0,
        'remaining': remaining,
        'hours': 0,
    }

def _pet_expedition_state(conn, row):
    if not row:
        return {'active': False, 'ready': False, 'remaining': 0, 'hours': 0}
    keys = row.keys()
    if 'last_train_at' not in keys or not row['last_train_at']:
        return {'active': False, 'ready': False, 'remaining': 0, 'hours': 0}
    log = conn.execute(
        "SELECT detail FROM pet_action_log WHERE user_id=? AND action='train' ORDER BY id DESC LIMIT 1",
        (row['user_id'],)
    ).fetchone()
    detail = str(log['detail'] if log and log['detail'] is not None else '').strip()
    digits = ''.join(ch for ch in detail if ch.isdigit())
    hours = int(digits) if digits else PET_EXPEDITION_DEFAULT_HOURS
    if hours not in PET_EXPEDITION_ALLOWED_HOURS:
        hours = PET_EXPEDITION_DEFAULT_HOURS
    remaining = _pet_cooldown_remaining(row, 'last_train_at', hours * 3600)
    return {
        'active': remaining > 0,
        'ready': remaining <= 0,
        'remaining': remaining,
        'hours': hours,
        'cooldown': remaining,
        'cooldown_total': hours * 3600,
    }

def _pet_food_reward(item_key, qty=1):
    item = PET_FOOD_CATALOG.get(item_key)
    if not item or qty <= 0:
        return None
    return {
        'item_key': item_key,
        'qty': qty,
        'name': item.get('name'),
        'name_en': item.get('name_en'),
    }

def _pet_xp_required(level):
    level = max(1, int(level or 1))
    return int(round(
        90
        + max(0, level - 1) * 20
        + max(0, level - 9) * 18
        + max(0, level - 19) * 30
    ))

def _pet_stage(level):
    level = max(1, int(level or 1))
    if level >= 25:
        return 3
    if level >= 10:
        return 2
    return 1

def _pet_next_evolution(level):
    level = max(1, int(level or 1))
    if level < 10:
        return {'stage': 2, 'level': 10, 'levels_to_go': 10 - level}
    if level < 25:
        return {'stage': 3, 'level': 25, 'levels_to_go': 25 - level}
    return None

def _pet_image_for_level(pet_key, level):
    catalog = PET_CATALOG.get(pet_key, {})
    images = catalog.get('images') or {}
    return images.get(_pet_stage(level)) or catalog.get('image') or ''

def _pet_animation_set_for_level(pet_key, level):
    stage = _pet_stage(level)
    if stage > 1 and (PET_CATALOG.get(pet_key, {}).get('images') or {}).get(stage):
        return f"{pet_key}_lv{stage}"
    return pet_key

def _decayed_fullness(row):
    """棋靈飽食度惰性衰減：自最後一次餵食/互動起，每 6 小時 -10。"""
    base = max(0, min(100, int(row['fullness'] if row['fullness'] is not None else 0)))
    keys = row.keys()
    times = []
    for col in ('last_fed_at', 'last_interacted_at'):
        if col in keys and row[col]:
            try:
                times.append(datetime.datetime.fromisoformat(row[col]))
            except Exception:
                pass
    if not times:
        return base
    hours = (datetime.datetime.now() - max(times)).total_seconds() / 3600
    return max(0, base - int(hours // 6) * 10)

def _normalize_pet_row(row):
    if not row:
        return None
    d = dict(row)
    catalog = PET_CATALOG.get(d['pet_key'], {})
    level = max(1, int(d.get('level') or 1))
    xp = max(0, int(d.get('xp') or 0))
    req = _pet_xp_required(level)
    stage = _pet_stage(level)
    d.update(catalog)
    d['level'] = level
    d['stage'] = stage
    d['stage_label'] = (catalog.get('stage_labels') or {}).get(stage, '')
    d['image'] = _pet_image_for_level(d['pet_key'], level)
    d['animation_set'] = _pet_animation_set_for_level(d['pet_key'], level)
    next_evo = _pet_next_evolution(level)
    if next_evo:
        labels = catalog.get('stage_labels') or {}
        d['next_evolution_stage'] = next_evo['stage']
        d['next_evolution_level'] = next_evo['level']
        d['next_evolution_label'] = labels.get(next_evo['stage'], '')
        d['levels_to_next_evolution'] = next_evo['levels_to_go']
    else:
        d['next_evolution_stage'] = None
        d['next_evolution_level'] = None
        d['next_evolution_label'] = ''
        d['levels_to_next_evolution'] = 0
    d['xp'] = xp
    d['xp_required'] = req
    d['xp_pct'] = round(min(100, xp / req * 100), 1) if req else 0
    d['fullness'] = _decayed_fullness(row)
    d['affection'] = max(0, min(100, int(d.get('affection') or 0)))
    d['nickname'] = (row['nickname'] or catalog.get('name') or d['pet_key'])
    default_names = {catalog.get('name'), *(catalog.get('stage_labels') or {}).values()}
    d['nickname_en'] = (catalog.get('name_en') if d['nickname'] in default_names else d['nickname'])
    return d

def _grant_pet_food(conn, uid, item_key, qty):
    if item_key not in PET_FOOD_CATALOG or qty <= 0:
        return
    conn.execute(
        'INSERT INTO pet_inventory(user_id,item_key,qty) VALUES(?,?,?) '
        'ON CONFLICT(user_id,item_key) DO UPDATE SET qty=pet_inventory.qty+excluded.qty',
        (uid, item_key, qty)
    )

PET_MILESTONE_STEP   = 5                       # 每 5 級一個里程碑（與陪練基礎加成階梯一致）
PET_MILESTONE_REWARD = ('starfruit', 2)        # 每達一個里程碑贈送的食物

def _pet_milestone_for_level(level):
    """傳回該等級對應的里程碑資訊（若 level 為里程碑），含當下基礎加成%。"""
    base_pct = round((0.05 + (level - 1) // PET_MILESTONE_STEP * 0.01) * 100, 1)
    return {
        'level': level,
        'base_pct': base_pct,
        'reward_item': PET_MILESTONE_REWARD[0],
        'reward_qty': PET_MILESTONE_REWARD[1],
        'reward_name': PET_FOOD_CATALOG.get(PET_MILESTONE_REWARD[0], {}).get('name', ''),
        'reward_name_en': PET_FOOD_CATALOG.get(PET_MILESTONE_REWARD[0], {}).get('name_en', ''),
    }

def _add_pet_xp(conn, uid, amount):
    if amount <= 0:
        return None
    row = conn.execute('SELECT * FROM user_pets WHERE user_id=?', (uid,)).fetchone()
    if not row:
        return None
    old_level = max(1, int(row['level'] or 1))
    level = old_level
    xp = max(0, int(row['xp'] or 0)) + amount
    leveled = 0
    while xp >= _pet_xp_required(level):
        xp -= _pet_xp_required(level)
        level += 1
        leveled += 1
    conn.execute(
        'UPDATE user_pets SET level=?, xp=?, updated_at=? WHERE user_id=?',
        (level, xp, datetime.datetime.now().isoformat(), uid)
    )
    # 跨越的里程碑 = 基礎加成實際 +1% 的等級（LV6/11/16…，與 _pet_player_xp_bonus 的階梯一致）
    milestones = [_pet_milestone_for_level(lv)
                  for lv in range(old_level + 1, level + 1)
                  if (lv - 1) % PET_MILESTONE_STEP == 0]
    for _ in milestones:
        _grant_pet_food(conn, uid, PET_MILESTONE_REWARD[0], PET_MILESTONE_REWARD[1])
    return {'level': level, 'xp': xp, 'leveled': leveled, 'milestones': milestones}

# ── Phase 4 多寵：解鎖門檻（任一寵物最高等級）──────────────────
PET_UNLOCK_THRESHOLDS = [1, 11, 16]   # 擁有第 1/2/3 隻所需的最高寵物等級（現寵等級解鎖）

def _pet_catalog_values():
    return [PET_CATALOG[k] for k in PET_UNLOCK_ORDER if k in PET_CATALOG]

def _next_pet_unlock_key(owned_keys):
    owned = set(owned_keys or [])
    for key in PET_UNLOCK_ORDER:
        if key not in owned:
            return key
    return None

def _pet_collection_sync_active(conn, uid):
    """把目前出戰中（user_pets）的數值快照回寫到 pet_collection。"""
    row = conn.execute('SELECT * FROM user_pets WHERE user_id=?', (uid,)).fetchone()
    if not row:
        return
    conn.execute('''INSERT INTO pet_collection
        (user_id, pet_key, nickname, level, xp, fullness, affection, selected_at,
         last_fed_at, last_interacted_at, last_pet_at, last_train_at,
         daily_key, daily_bond, daily_train_xp)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(user_id, pet_key) DO UPDATE SET
         nickname=excluded.nickname, level=excluded.level, xp=excluded.xp,
         fullness=excluded.fullness, affection=excluded.affection,
         last_fed_at=excluded.last_fed_at, last_interacted_at=excluded.last_interacted_at,
         last_pet_at=excluded.last_pet_at, last_train_at=excluded.last_train_at,
         daily_key=excluded.daily_key, daily_bond=excluded.daily_bond,
         daily_train_xp=excluded.daily_train_xp''',
        (uid, row['pet_key'], row['nickname'], row['level'], row['xp'], row['fullness'],
         row['affection'], row['selected_at'], row['last_fed_at'], row['last_interacted_at'],
         row['last_pet_at'], row['last_train_at'], row['daily_key'],
         row['daily_bond'], row['daily_train_xp']))

def _pet_owned_keys(conn, uid):
    return [r['pet_key'] for r in
            conn.execute('SELECT pet_key FROM pet_collection WHERE user_id=?', (uid,)).fetchall()]

def _pet_max_owned_level(conn, uid):
    r = conn.execute('SELECT MAX(level) AS m FROM pet_collection WHERE user_id=?', (uid,)).fetchone()
    lvl = int(r['m']) if r and r['m'] is not None else 1
    a = conn.execute('SELECT level FROM user_pets WHERE user_id=?', (uid,)).fetchone()
    if a and a['level']:
        lvl = max(lvl, int(a['level']))
    return max(1, lvl)

def _pet_allowed_count(max_level):
    return sum(1 for t in PET_UNLOCK_THRESHOLDS if max_level >= t)

def _pet_collection_state(conn, uid, active_key):
    """回傳玩家寵物收藏（已擁有＋鎖定）狀態，供前端切換列使用。"""
    owned = {r['pet_key']: r for r in
             conn.execute('SELECT * FROM pet_collection WHERE user_id=?', (uid,)).fetchall()}
    if not owned:
        return None
    active_row = conn.execute('SELECT * FROM user_pets WHERE user_id=?', (uid,)).fetchone()
    max_level = _pet_max_owned_level(conn, uid)
    allowed = _pet_allowed_count(max_level)
    owned_count = len(owned)
    collection, locked = [], []
    for key in PET_UNLOCK_ORDER:
        cat = PET_CATALOG.get(key)
        if not cat:
            continue
        if key in owned:
            # 出戰中那隻用 user_pets 的即時數值（可能比快照新）
            row = active_row if (key == active_key and active_row) else owned[key]
            row = active_row if (key == active_key and active_row) else owned[key]
            collection.append({
                'key': key, 'name': cat.get('name'), 'name_en': cat.get('name_en'),
                'role': cat.get('role'), 'role_en': cat.get('role_en'),
                'image': _pet_image_for_level(key, row['level']), 'accent': cat.get('accent'),
                'nickname': row['nickname'] or cat.get('name'),
                'level': max(1, int(row['level'] or 1)),
                'stage': _pet_stage(row['level']),
                'animation_set': _pet_animation_set_for_level(key, row['level']),
                'active': (key == active_key),
            })
    next_key = _next_pet_unlock_key(owned.keys())
    for idx, key in enumerate(PET_UNLOCK_ORDER):
        cat = PET_CATALOG.get(key)
        if not cat:
            continue
        if key in owned:
            continue
        need_level = PET_UNLOCK_THRESHOLDS[idx] if idx < len(PET_UNLOCK_THRESHOLDS) else None
        locked.append({
            'key': key, 'name': cat.get('name'), 'name_en': cat.get('name_en'),
            'role': cat.get('role'), 'role_en': cat.get('role_en'),
            'image': cat.get('image'), 'accent': cat.get('accent'),
            'claimable': (key == next_key and owned_count < allowed),
            'unlock_level': need_level,
        })
    return {
        'max_level': max_level, 'allowed_count': allowed, 'owned_count': owned_count,
        'collection': collection, 'locked': locked,
    }

def _pet_player_xp_bonus(conn, uid, context):
    """棋靈夥伴給玩家的答題 XP 加成比例（依等級/親密度/專長情境/飽食度）。
    星殼龍→連勝、墨滴馬→穩定練習、虛空貓→錯題復盤。"""
    row = conn.execute(
        'SELECT pet_key, level, affection, fullness, last_fed_at, last_interacted_at '
        'FROM user_pets WHERE user_id=?', (uid,)
    ).fetchone()
    if not row:
        return 0.0
    level = max(1, int(row['level'] or 1))
    affection = max(0, min(100, int(row['affection'] or 0)))
    fullness = _decayed_fullness(row)
    base = 0.05 + (level - 1) // 5 * 0.01            # 基礎 5% + 每 5 級 +1%
    matched = (
        (row['pet_key'] == 'star_shell_hatchling' and (context.get('combo') or 0) >= 3) or
        (row['pet_key'] == 'ink_drop_kelpie') or
        (row['pet_key'] == 'whispering_void_kit' and context.get('is_mc'))
    )
    bonus = base * (1.6 if matched else 1.0)         # 專長情境 ×1.6
    bonus *= 1.0 + 0.2 * (affection / 100.0)         # 親密度滿額外 ×1.2
    if fullness < 30:
        bonus *= 0.5                                  # 餓肚子加成砍半
    return round(bonus, 4)

# 各寵物「專長情境」觸發條件文案（與 _pet_player_xp_bonus 的 matched 規則對應）
PET_MATCH_CONDITION = {
    'star_shell_hatchling': {'zh': '連勝 3 題以上時', 'en': 'On a 3+ answer streak'},
    'ink_drop_kelpie':      {'zh': '穩定練習時（恆常觸發）', 'en': 'Steady practice — always on'},
    'whispering_void_kit':  {'zh': '複習錯題（多選題）時', 'en': 'Reviewing mistakes'},
}

def _pet_bonus_breakdown(row):
    """陪練加成的可視化拆解（不依賴答題情境），供前端在寵物卡顯示。"""
    if not row:
        return None
    pet_key = row['pet_key']
    level = max(1, int(row['level'] or 1))
    affection = max(0, min(100, int(row['affection'] or 0)))
    fullness = _decayed_fullness(row)
    base = 0.05 + (level - 1) // 5 * 0.01
    aff_mult = 1.0 + 0.2 * (affection / 100.0)
    hungry = fullness < 30
    pen = 0.5 if hungry else 1.0
    always_matched = (pet_key == 'ink_drop_kelpie')   # 墨滴馬恆常觸發專長
    current = base * (1.6 if always_matched else 1.0) * aff_mult * pen
    matched = base * 1.6 * aff_mult * pen
    cond = PET_MATCH_CONDITION.get(pet_key, {'zh': '', 'en': ''})
    # 下一個里程碑 = 下一個基礎加成 +1% 的等級（LV6/11/16…）
    _delta = (1 - level) % PET_MILESTONE_STEP
    if _delta <= 0:
        _delta += PET_MILESTONE_STEP
    next_ms = level + _delta
    next_ms_base = round((0.05 + (next_ms - 1) // PET_MILESTONE_STEP * 0.01) * 100, 1)
    return {
        'current_pct': round(current * 100, 1),
        'matched_pct': round(matched * 100, 1),
        'base_pct': round(base * 100, 1),
        'affection_mult': round(aff_mult, 2),
        'next_level_for_base': 5 - ((level - 1) % 5),   # 還差幾級基礎 +1%
        'next_milestone_level': next_ms,
        'next_milestone_to_go': next_ms - level,
        'next_milestone_base_pct': next_ms_base,
        'hungry': hungry,
        'always_matched': always_matched,
        'match_condition': cond['zh'],
        'match_condition_en': cond['en'],
    }

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
    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat()
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
_AUTO_TITLES_EN = {
    'atk':  'Sky-cleaving Swordsman',
    'def':  'Holy Shield Guard',
    'vis':  'Star Navigator',
    'prec': 'Endgame Scale-keeper',
    'all':  'All-round Cultivator',
}
_AUTO_TITLE_NOVICE_EN = 'Novice Cultivator'
_AUTO_TITLE_EN_BY_ZH = dict(zip(_AUTO_TITLES.values(), _AUTO_TITLES_EN.values()))
_AUTO_TITLE_EN_BY_ZH['修煉初心者'] = _AUTO_TITLE_NOVICE_EN

def auto_title_en(zh_title):
    """中文動態稱號 → 英文（找不到回原值）。"""
    return _AUTO_TITLE_EN_BY_ZH.get(zh_title, zh_title)

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

def add_column_if_not_exists(conn, table_name, col_name, col_definition):
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
        (table_name.lower(), col_name.lower())
    )
    if not cursor.fetchone():
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_definition}")


def _question_problem_report_reason_code_list_sql(reason_codes=QUESTION_PROBLEM_REPORT_REASON_CODES):
    return ', '.join("'" + code.replace("'", "''") + "'" for code in reason_codes)


def _question_problem_report_reason_code_candidates(conn, table_name='question_problem_reports'):
    raw_conn = getattr(conn, '_conn', conn)
    allowed = set(QUESTION_PROBLEM_REPORT_REASON_CODES)
    with raw_conn.cursor(cursor_factory=DictCursor) as cursor:
        cursor.execute(
            """
            SELECT conname, pg_get_constraintdef(oid) AS definition
            FROM pg_constraint
            WHERE conrelid = %s::regclass
              AND contype = 'c'
              AND pg_get_constraintdef(oid) LIKE '%%reason_code%%'
            ORDER BY conname
            """,
            (table_name,),
        )
        rows = cursor.fetchall()
    candidates = []
    for row in rows:
        definition = row['definition']
        values = set(re.findall(r"'((?:''|[^'])*)'", definition))
        if values and values <= allowed:
            candidates.append({
                'conname': row['conname'],
                'definition': definition,
                'values': values,
            })
    return candidates


def _ensure_question_problem_report_reason_code_constraint(conn, table_name='question_problem_reports'):
    desired_codes = tuple(QUESTION_PROBLEM_REPORT_REASON_CODES)
    desired_values = set(desired_codes)
    raw_conn = getattr(conn, '_conn', conn)
    with raw_conn.cursor(cursor_factory=DictCursor) as cursor:
        def _load_candidates():
            return _question_problem_report_reason_code_candidates(raw_conn, table_name=table_name)

        candidates = _load_candidates()
        if not candidates:
            raise RuntimeError(f'No valid reason_code CHECK constraint found on {table_name}')
        if len(candidates) > 1:
            raise RuntimeError(
                f'Ambiguous reason_code CHECK constraints found on {table_name}: '
                + ', '.join(f"{row['conname']}" for row in candidates)
            )

        candidate = candidates[0]
        if desired_values <= candidate['values']:
            verified = _load_candidates()
            if len(verified) != 1 or 'no_valid_answer' not in verified[0]['values']:
                raise RuntimeError(
                    f"Post-check failed for {table_name}: expected one widened reason_code CHECK with no_valid_answer"
                )
            return {
                'changed': False,
                'constraint_name': candidate['conname'],
                'definition': verified[0]['definition'],
            }

        constraint_name = candidate['conname']
        cursor.execute(
            sql.SQL('ALTER TABLE {table} DROP CONSTRAINT {constraint}').format(
                table=sql.Identifier(table_name),
                constraint=sql.Identifier(constraint_name),
            )
        )
        cursor.execute(
            sql.SQL('ALTER TABLE {table} ADD CONSTRAINT {constraint} CHECK (reason_code IN ({values}))').format(
                table=sql.Identifier(table_name),
                constraint=sql.Identifier(constraint_name),
                values=sql.SQL(', ').join(sql.Literal(code) for code in desired_codes),
            )
        )
        verified = _load_candidates()
        if len(verified) != 1 or 'no_valid_answer' not in verified[0]['values']:
            raise RuntimeError(
                f"Post-check failed for {table_name}: reason_code CHECK did not widen to include no_valid_answer"
            )
        return {
            'changed': True,
            'constraint_name': constraint_name,
            'definition': verified[0]['definition'],
        }

def init_db():
    with get_db() as conn:
        cursor = conn.cursor()

        # 多 worker / scheduler 並發啟動時序列化整個建表流程，避免並發
        # CREATE TABLE / ALTER 撞 pg_type 唯一鍵（transaction 級鎖，commit 時自動釋放）。
        conn.execute('SELECT pg_advisory_xact_lock(778899123)')

        # ── zones ──
        conn.execute('''CREATE TABLE IF NOT EXISTS zones (
            id          SERIAL PRIMARY KEY,
            name        TEXT NOT NULL UNIQUE,
            folder_path TEXT NOT NULL UNIQUE,
            min_level   INTEGER NOT NULL DEFAULT 1,
            created_at  TEXT
        )''')

        # ── grimoires ──
        conn.execute('''CREATE TABLE IF NOT EXISTS grimoires (
            id           SERIAL PRIMARY KEY,
            zone_id      INTEGER NOT NULL REFERENCES zones(id),
            name         TEXT NOT NULL,
            folder_path  TEXT NOT NULL UNIQUE,
            discipline   TEXT NOT NULL CHECK(discipline IN ('tesuji','life_death','opening','endgame','mix')),
            node_count   INTEGER NOT NULL DEFAULT 0,
            unlock_level INTEGER NOT NULL DEFAULT 1,
            created_at   TEXT DEFAULT NULL,
            difficulty   INTEGER NOT NULL DEFAULT 5
        )''')

        # ── 用戶表 ──
        conn.execute('''CREATE TABLE IF NOT EXISTS users (
            id            SERIAL PRIMARY KEY,
            username      TEXT    NOT NULL,
            password_hash TEXT    NOT NULL,
            is_admin      INTEGER NOT NULL DEFAULT 0,
            plan          TEXT    NOT NULL DEFAULT 'free',
            created_at    TEXT    NOT NULL,
            last_login    TEXT,
            google_sub    TEXT
        )''')
        conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username_lower ON users (LOWER(username))')
        add_column_if_not_exists(conn, 'users', 'google_sub', 'TEXT')
        conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_users_google_sub '
                     'ON users (google_sub) WHERE google_sub IS NOT NULL')

        # ── SRS ──
        conn.execute('''CREATE TABLE IF NOT EXISTS srs_cards (
            user_id      INTEGER NOT NULL,
            question_id  INTEGER NOT NULL,
            ease_factor  REAL    NOT NULL DEFAULT 2.5,
            interval     INTEGER NOT NULL DEFAULT 0,
            repetitions  INTEGER NOT NULL DEFAULT 0,
            due_date     TEXT    NOT NULL DEFAULT (CURRENT_DATE::text),
            last_grade   INTEGER,
            updated_at   TEXT,
            PRIMARY KEY (user_id, question_id)
        )''')
        # Phase 4D anti-farming: once set, stays set forever (unlike
        # last_grade, which flips on every submission and can be reset by
        # an intentional fail/pass toggle to re-farm progression rewards).
        add_column_if_not_exists(conn, 'srs_cards', 'progress_credited', 'INTEGER NOT NULL DEFAULT 0')

        # ── 用戶統計 ──
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

        # ── 委託獎勵發放紀錄（防止重練刷幣）──
        conn.execute('''CREATE TABLE IF NOT EXISTS reward_claimed (
            user_id    INTEGER NOT NULL,
            stage_key  TEXT    NOT NULL,
            coins      INTEGER NOT NULL DEFAULT 0,
            xp         INTEGER NOT NULL DEFAULT 0,
            claimed_at TEXT,
            PRIMARY KEY (user_id, stage_key)
        )''')

        # ── 線上對弈戰績表 ──
        conn.execute('''CREATE TABLE IF NOT EXISTS game_results (
            id          SERIAL PRIMARY KEY,
            user_id     INTEGER NOT NULL,
            result      INTEGER NOT NULL,  -- 1=勝 0=負
            go_rank     TEXT    NOT NULL,
            played_at   TEXT    NOT NULL
        )''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_gr_uid ON game_results(user_id, played_at)')

        # ── 完整對局記錄表 ──
        conn.execute('''CREATE TABLE IF NOT EXISTS game_records (
            id            SERIAL PRIMARY KEY,
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
        conn.execute('CREATE INDEX IF NOT EXISTS idx_grec_uid ON game_records(user_id, played_at)')

        # ── 獎章 ──
        conn.execute('''CREATE TABLE IF NOT EXISTS badges_earned (
            user_id     INTEGER NOT NULL,
            badge_id    TEXT    NOT NULL,
            earned_at   TEXT    NOT NULL,
            seen        INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, badge_id)
        )''')

        # ── 單元進度 ──
        conn.execute('''CREATE TABLE IF NOT EXISTS unit_progress (
            user_id         INTEGER NOT NULL,
            unit_name       TEXT    NOT NULL,
            completed_ids   TEXT    NOT NULL DEFAULT '[]',
            completed_at    TEXT,
            PRIMARY KEY (user_id, unit_name)
        )''')

        # ── 錯題本 ──
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

        # ── 每日答題詳細記錄 ──
        conn.execute('''CREATE TABLE IF NOT EXISTS review_log (
            id          SERIAL PRIMARY KEY,
            user_id     INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            grade       INTEGER NOT NULL,
            topic       TEXT,
            level       TEXT,
            difficulty  TEXT,
            reviewed_at TEXT    NOT NULL
        )''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_review_log_user_date ON review_log(user_id, reviewed_at)')
        for _col, _def in [
            ('response_ms',             'INTEGER'),
            ('discipline',              'TEXT'),
            ('player_rating_snapshot',  'REAL'),
            ('question_rating_snapshot','REAL'),
            ('item_rating_version',     'TEXT'),
            ('question_version',        'TEXT'),
            ('source_context',          'TEXT'),
            ('is_scaffolding',          'INTEGER NOT NULL DEFAULT 0'),
            ('training_set_id',         'INTEGER'),
        ]:
            add_column_if_not_exists(conn, 'review_log', _col, _def)

        # ── Premium 每週修行報告（shadow-first） ──
        conn.execute('''CREATE TABLE IF NOT EXISTS weekly_reports (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            period_start TEXT NOT NULL,
            period_end TEXT NOT NULL,
            report_version TEXT NOT NULL,
            model_version TEXT NOT NULL,
            item_rating_version TEXT NOT NULL,
            player_rating_snapshot REAL,
            summary_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'shadow'
                CHECK(status IN ('shadow','published','revoked')),
            generated_at TEXT NOT NULL,
            published_at TEXT,
            revoked_at TEXT,
            UNIQUE(user_id, period_start, report_version)
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS weekly_report_disciplines (
            report_id INTEGER NOT NULL REFERENCES weekly_reports(id) ON DELETE CASCADE,
            discipline TEXT NOT NULL,
            raw_count INTEGER NOT NULL,
            first_valid_count INTEGER NOT NULL,
            correction_count INTEGER NOT NULL DEFAULT 0,
            effective_weight REAL NOT NULL,
            actual_accuracy REAL,
            expected_accuracy REAL,
            shrunk_residual REAL,
            uncertainty REAL,
            median_response_ms INTEGER,
            p75_response_ms INTEGER,
            time_sample_count INTEGER NOT NULL DEFAULT 0,
            too_fast_count INTEGER NOT NULL DEFAULT 0,
            too_slow_count INTEGER NOT NULL DEFAULT 0,
            difficulty_distribution TEXT NOT NULL DEFAULT '{}',
            daily_cap_days INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL,
            reason_code TEXT,
            PRIMARY KEY(report_id, discipline)
        )''')
        add_column_if_not_exists(conn, 'weekly_report_disciplines',
                                 'correction_count', 'INTEGER NOT NULL DEFAULT 0')
        conn.execute('''CREATE TABLE IF NOT EXISTS premium_training_sets (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            report_id INTEGER REFERENCES weekly_reports(id) ON DELETE CASCADE,
            set_version TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active'
                CHECK(status IN ('active','completed','expired','revoked')),
            created_at TEXT NOT NULL,
            expires_at TEXT,
            completed_at TEXT,
            UNIQUE(user_id, report_id, set_version)
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS premium_training_items (
            id SERIAL PRIMARY KEY,
            set_id INTEGER NOT NULL REFERENCES premium_training_sets(id) ON DELETE CASCADE,
            question_id INTEGER NOT NULL,
            item_order INTEGER NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('warmup','secondary','primary','application','mistake')),
            discipline TEXT,
            reason_code TEXT NOT NULL,
            item_rating REAL,
            item_rating_version TEXT,
            is_scaffolding INTEGER NOT NULL DEFAULT 0,
            first_grade INTEGER,
            completed_grade INTEGER,
            completed_at TEXT,
            UNIQUE(set_id, item_order),
            UNIQUE(set_id, question_id)
        )''')
        add_column_if_not_exists(conn, 'premium_training_items', 'first_grade', 'INTEGER')
        conn.execute('''CREATE TABLE IF NOT EXISTS premium_quest_tokens (
            id SERIAL PRIMARY KEY,
            token_hash TEXT NOT NULL UNIQUE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            set_id INTEGER NOT NULL REFERENCES premium_training_sets(id) ON DELETE CASCADE,
            purpose TEXT NOT NULL DEFAULT 'weekly_quest',
            expires_at TEXT NOT NULL,
            revoked_at TEXT,
            created_at TEXT NOT NULL,
            last_used_at TEXT
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS email_preferences (
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            weekly_report_enabled INTEGER NOT NULL DEFAULT 0,
            consent_version TEXT,
            locale TEXT NOT NULL DEFAULT 'zh',
            updated_at TEXT NOT NULL
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS email_deliveries (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            report_id INTEGER NOT NULL REFERENCES weekly_reports(id) ON DELETE CASCADE,
            template_version TEXT NOT NULL,
            recipient_email TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK(status IN ('pending','sent','failed','cancelled')),
            retry_count INTEGER NOT NULL DEFAULT 0,
            error_class TEXT,
            created_at TEXT NOT NULL,
            sent_at TEXT,
            UNIQUE(report_id, recipient_email, template_version)
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS weekly_report_reviews (
            id SERIAL PRIMARY KEY,
            report_id INTEGER NOT NULL REFERENCES weekly_reports(id) ON DELETE CASCADE,
            reviewer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            reviewer_slot INTEGER NOT NULL CHECK(reviewer_slot IN (1,2)),
            top_disciplines TEXT NOT NULL,
            data_sufficient INTEGER NOT NULL,
            difficulty_fit INTEGER NOT NULL,
            notes TEXT,
            submitted_at TEXT NOT NULL,
            UNIQUE(report_id, reviewer_slot),
            UNIQUE(report_id, reviewer_id)
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS weekly_report_admin_logs (
            id SERIAL PRIMARY KEY,
            report_id INTEGER REFERENCES weekly_reports(id) ON DELETE CASCADE,
            admin_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            action TEXT NOT NULL,
            detail TEXT,
            created_at TEXT NOT NULL
        )''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_weekly_reports_user_period '
                     'ON weekly_reports(user_id, period_start DESC)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_premium_items_set_order '
                     'ON premium_training_items(set_id, item_order)')

        # ── 挑戰賽 ──
        conn.execute('''CREATE TABLE IF NOT EXISTS challenges (
            id               SERIAL PRIMARY KEY,
            challenger_id    INTEGER NOT NULL,
            opponent_id      INTEGER NOT NULL,
            question_ids     TEXT    NOT NULL DEFAULT '[]',
            challenger_score INTEGER,
            opponent_score   INTEGER,
            status           TEXT    NOT NULL DEFAULT 'pending',
            created_at       TEXT    NOT NULL
        )''')

        # ── 挑戰答題記錄 ──
        conn.execute('''CREATE TABLE IF NOT EXISTS challenge_answers (
            challenge_id INTEGER NOT NULL,
            user_id      INTEGER NOT NULL,
            answers      TEXT    NOT NULL DEFAULT '{}',
            submitted_at TEXT,
            PRIMARY KEY (challenge_id, user_id)
        )''')

        # ── 師生關係 ──
        conn.execute('''CREATE TABLE IF NOT EXISTS teacher_student (
            teacher_id  INTEGER NOT NULL,
            student_id  INTEGER NOT NULL,
            status      TEXT    NOT NULL DEFAULT 'pending',
            created_at  TEXT    NOT NULL,
            PRIMARY KEY (teacher_id, student_id)
        )''')

        # ── 老師留言 ──
        conn.execute('''CREATE TABLE IF NOT EXISTS teacher_comments (
            id          SERIAL PRIMARY KEY,
            teacher_id  INTEGER NOT NULL,
            student_id  INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            comment     TEXT    NOT NULL,
            created_at  TEXT    NOT NULL
        )''')

        # ── 分享連結 ──
        conn.execute('''CREATE TABLE IF NOT EXISTS share_links (
            id          SERIAL PRIMARY KEY,
            user_id     INTEGER NOT NULL,
            share_token TEXT    NOT NULL UNIQUE,
            title       TEXT    NOT NULL,
            stats_json  TEXT    NOT NULL DEFAULT '{}',
            view_count  INTEGER NOT NULL DEFAULT 0,
            created_at  TEXT    NOT NULL
        )''')

        # ── 怪物 HP 狀態（每日重置）──
        conn.execute('''CREATE TABLE IF NOT EXISTS monster_hp_log (
            user_id     INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            hp_date     TEXT    NOT NULL,
            current_hp  INTEGER NOT NULL,
            defeated    INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, question_id, hp_date)
        )''')

        # ── 戰場怪物 ──
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

        # ── 每日任務進度 ──
        conn.execute('''CREATE TABLE IF NOT EXISTS daily_quests (
            id          SERIAL PRIMARY KEY,
            user_id     INTEGER NOT NULL,
            quest_key   TEXT    NOT NULL,
            target      INTEGER NOT NULL,
            progress    INTEGER NOT NULL DEFAULT 0,
            completed   INTEGER NOT NULL DEFAULT 0,
            xp_awarded  INTEGER NOT NULL DEFAULT 0,
            quest_date  TEXT    NOT NULL,
            UNIQUE(user_id, quest_key, quest_date)
        )''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_daily_quests_user_date ON daily_quests(user_id, quest_date)')

        # ── 公會佈告欄：玩家接取中的主線委託（quest_key = '學科::階段'）──
        conn.execute('''CREATE TABLE IF NOT EXISTS quest_accepted (
            user_id     INTEGER NOT NULL,
            quest_key   TEXT    NOT NULL,
            accepted_at TEXT    NOT NULL,
            PRIMARY KEY (user_id, quest_key)
        )''')

        # ── 每日挑戰 ──
        conn.execute('''CREATE TABLE IF NOT EXISTS daily_challenge (
            challenge_date  TEXT    PRIMARY KEY,
            question_id     INTEGER NOT NULL,
            set_by          TEXT    NOT NULL DEFAULT 'auto',
            note            TEXT
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS daily_challenge_log (
            id             SERIAL PRIMARY KEY,
            user_id        INTEGER NOT NULL,
            challenge_date TEXT    NOT NULL,
            question_id    INTEGER NOT NULL,
            correct        INTEGER NOT NULL DEFAULT 0,
            submitted_at   TEXT    NOT NULL,
            UNIQUE(user_id, challenge_date)
        )''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_dc_log_date ON daily_challenge_log(challenge_date)')

        # ── 今日推薦訓練隊列 ──
        conn.execute('''CREATE TABLE IF NOT EXISTS daily_training_queue (
            user_id      INTEGER NOT NULL,
            date         TEXT    NOT NULL,
            question_ids TEXT    NOT NULL,
            sources      TEXT    NOT NULL DEFAULT '[]',
            generated_at TEXT    NOT NULL DEFAULT (TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')),
            PRIMARY KEY (user_id, date)
        )''')

        # ── 新兵巡禮狀態 / checkpoint / 埋點 ──
        conn.execute('''CREATE TABLE IF NOT EXISTS newbie_quest_state (
            user_id     INTEGER PRIMARY KEY,
            stage       INTEGER NOT NULL DEFAULT 1,
            graduated   INTEGER NOT NULL DEFAULT 0,
            created_at  TEXT    NOT NULL,
            updated_at  TEXT    NOT NULL
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS newbie_quest_tasks (
            user_id      INTEGER NOT NULL,
            task_key     TEXT    NOT NULL,
            source       TEXT    NOT NULL DEFAULT '',
            completed_at TEXT    NOT NULL,
            PRIMARY KEY (user_id, task_key)
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS newbie_quest_events (
            user_id     INTEGER NOT NULL,
            event_key   TEXT    NOT NULL,
            event_name  TEXT    NOT NULL,
            task_key    TEXT,
            payload     TEXT    NOT NULL DEFAULT '{}',
            occurred_at TEXT    NOT NULL,
            PRIMARY KEY (user_id, event_key)
        )''')

        # ── 主線冒險 BOSS 通關狀態 ──
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
        conn.execute('CREATE INDEX IF NOT EXISTS idx_adv_boss_user ON adventure_boss_progress(user_id)')

        # ── 主線冒險地區解鎖 ──
        conn.execute('''CREATE TABLE IF NOT EXISTS adventure_zone_unlocks (
            user_id        INTEGER NOT NULL,
            zone_key       TEXT    NOT NULL,
            source         TEXT    NOT NULL DEFAULT 'placement',
            start_zone_key TEXT,
            unlocked_at    TEXT    NOT NULL,
            PRIMARY KEY (user_id, zone_key)
        )''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_adv_unlock_user ON adventure_zone_unlocks(user_id)')

        # ── 角色外觀衣櫃（持有清單） ──
        conn.execute('''CREATE TABLE IF NOT EXISTS player_wardrobe (
            id          SERIAL PRIMARY KEY,
            user_id     INTEGER NOT NULL,
            item_id     TEXT    NOT NULL,
            obtained_at TEXT    NOT NULL,
            source      TEXT    NOT NULL DEFAULT 'drop',
            UNIQUE(user_id, item_id)
        )''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_wardrobe_user ON player_wardrobe(user_id)')

        # ── 角色外觀目前穿戴狀態 ──
        conn.execute('''CREATE TABLE IF NOT EXISTS player_appearance (
            user_id    INTEGER PRIMARY KEY,
            outfit_id  TEXT,
            hat_id     TEXT,
            back_id    TEXT,
            title_id   TEXT,
            updated_at TEXT
        )''')

        # ── 技能習得 ──
        conn.execute('''CREATE TABLE IF NOT EXISTS player_skills (
            user_id     INTEGER NOT NULL,
            skill_id    TEXT    NOT NULL,
            equipped    INTEGER NOT NULL DEFAULT 0,
            learned_at  TEXT    NOT NULL,
            PRIMARY KEY (user_id, skill_id)
        )''')

        # ── 背包（持有裝備） ──
        conn.execute('''CREATE TABLE IF NOT EXISTS player_inventory (
            id          SERIAL PRIMARY KEY,
            user_id     INTEGER NOT NULL,
            equip_id    TEXT    NOT NULL,
            equipped    INTEGER NOT NULL DEFAULT 0,
            obtained_at TEXT    NOT NULL,
            source      TEXT    NOT NULL DEFAULT 'drop'
        )''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_inv_user ON player_inventory(user_id)')

        # ── 商城系統 ──
        conn.execute('''CREATE TABLE IF NOT EXISTS shop_inventory (
            user_id     INTEGER NOT NULL,
            item_key    TEXT    NOT NULL,
            qty         INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, item_key)
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS currency_log (
            id          SERIAL PRIMARY KEY,
            user_id     INTEGER NOT NULL,
            delta       INTEGER NOT NULL,
            balance_after INTEGER NOT NULL,
            reason      TEXT    NOT NULL,
            created_at  TEXT    NOT NULL
        )''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_clog_user_date ON currency_log(user_id, created_at)')
        conn.execute('''CREATE TABLE IF NOT EXISTS active_effects (
            id          SERIAL PRIMARY KEY,
            user_id     INTEGER NOT NULL,
            effect_key  TEXT    NOT NULL,
            value       REAL    NOT NULL DEFAULT 1,
            expires_at  TEXT,
            effect_date TEXT,
            created_at  TEXT    NOT NULL
        )''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_fx_user ON active_effects(user_id, effect_key)')
        conn.execute('''CREATE TABLE IF NOT EXISTS gacha_log (
            id          SERIAL PRIMARY KEY,
            user_id     INTEGER NOT NULL,
            pool        TEXT    NOT NULL DEFAULT 'koin',
            result_key  TEXT    NOT NULL,
            result_type TEXT    NOT NULL,
            rarity      TEXT,
            pity_count  INTEGER NOT NULL DEFAULT 0,
            created_at  TEXT    NOT NULL
        )''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_gacha_user ON gacha_log(user_id, id)')
        conn.execute('''CREATE TABLE IF NOT EXISTS daily_shop (
            shop_date   TEXT PRIMARY KEY,
            slots       TEXT NOT NULL
        )''')

        # ── 金流：訂單與訂閱 ──
        conn.execute('''CREATE TABLE IF NOT EXISTS payment_orders (
            id            SERIAL PRIMARY KEY,
            mer_order_no  TEXT    NOT NULL UNIQUE,
            user_id       INTEGER NOT NULL,
            provider      TEXT    NOT NULL DEFAULT 'newebpay',
            plan_key      TEXT    NOT NULL,
            amount        INTEGER NOT NULL,
            currency      TEXT    NOT NULL DEFAULT 'TWD',
            status        TEXT    NOT NULL DEFAULT 'pending',
            raw_payload   TEXT,
            created_at    TEXT    NOT NULL,
            paid_at       TEXT
        )''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_payorder_user ON payment_orders(user_id, id)')
        conn.execute('''CREATE TABLE IF NOT EXISTS subscriptions (
            id            SERIAL PRIMARY KEY,
            user_id       INTEGER NOT NULL,
            provider      TEXT    NOT NULL DEFAULT 'newebpay',
            mer_order_no  TEXT    NOT NULL UNIQUE,
            period_no     TEXT,
            plan_key      TEXT    NOT NULL,
            amount        INTEGER NOT NULL,
            status        TEXT    NOT NULL DEFAULT 'pending',
            total_times   INTEGER NOT NULL DEFAULT 0,
            charged_times INTEGER NOT NULL DEFAULT 0,
            created_at    TEXT    NOT NULL,
            updated_at    TEXT,
            cancelled_at  TEXT
        )''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_subs_user ON subscriptions(user_id, id)')
        conn.execute('''CREATE TABLE IF NOT EXISTS trial_code_batches (
            id                       SERIAL PRIMARY KEY,
            batch_key                TEXT    NOT NULL UNIQUE,
            campaign_name            TEXT    NOT NULL DEFAULT '',
            org_name                 TEXT    NOT NULL DEFAULT '',
            days                     INTEGER NOT NULL DEFAULT 30,
            code_count               INTEGER NOT NULL DEFAULT 0,
            max_redemptions_per_code INTEGER NOT NULL DEFAULT 1,
            expires_at               TEXT    NOT NULL,
            status                   TEXT    NOT NULL DEFAULT 'active',
            created_by_admin_id      INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_at               TEXT    NOT NULL,
            note                     TEXT    NOT NULL DEFAULT ''
        )''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_trial_batches_created '
                     'ON trial_code_batches(created_at DESC)')
        conn.execute('''CREATE TABLE IF NOT EXISTS trial_codes (
            id                  SERIAL PRIMARY KEY,
            batch_id            INTEGER NOT NULL REFERENCES trial_code_batches(id) ON DELETE CASCADE,
            code_hash           TEXT    NOT NULL UNIQUE,
            code_prefix         TEXT    NOT NULL DEFAULT '',
            code_last4          TEXT    NOT NULL DEFAULT '',
            status              TEXT    NOT NULL DEFAULT 'unused',
            redeemed_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            redeemed_by_email   TEXT,
            redeemed_at         TEXT,
            expires_at          TEXT    NOT NULL,
            created_at          TEXT    NOT NULL,
            revoked_at          TEXT,
            revoked_reason      TEXT
        )''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_trial_codes_batch '
                     'ON trial_codes(batch_id, status)')
        conn.execute('''CREATE TABLE IF NOT EXISTS trial_code_redemptions (
            id               SERIAL PRIMARY KEY,
            code_id          INTEGER REFERENCES trial_codes(id) ON DELETE SET NULL,
            user_id          INTEGER REFERENCES users(id) ON DELETE SET NULL,
            email_normalized TEXT,
            result           TEXT    NOT NULL,
            error_reason     TEXT,
            ip               TEXT,
            user_agent       TEXT,
            created_at       TEXT    NOT NULL
        )''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_trial_redemptions_code '
                     'ON trial_code_redemptions(code_id, created_at DESC)')
        conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_trial_redemptions_email_success '
                     "ON trial_code_redemptions(email_normalized) WHERE result='success'")
        conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_trial_redemptions_code_success '
                     "ON trial_code_redemptions(code_id) WHERE result='success'")
        conn.execute('''CREATE TABLE IF NOT EXISTS payment_notify_log (
            id          SERIAL PRIMARY KEY,
            provider    TEXT NOT NULL,
            event_key   TEXT NOT NULL UNIQUE,
            payload     TEXT NOT NULL,
            created_at  TEXT NOT NULL
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS app_kv (
            key   TEXT PRIMARY KEY,
            value TEXT
        )''')

        # ── SP 狀態 ──
        conn.execute('''CREATE TABLE IF NOT EXISTS player_sp (
            user_id     INTEGER PRIMARY KEY,
            current_sp  INTEGER NOT NULL DEFAULT 0,
            sp_date     TEXT    NOT NULL DEFAULT (CURRENT_DATE::text),
            daily_used  TEXT    NOT NULL DEFAULT '{}'
        )''')

        # ── 題目討論留言 ──
        conn.execute('''CREATE TABLE IF NOT EXISTS question_comments (
            id          SERIAL PRIMARY KEY,
            question_id INTEGER NOT NULL,
            user_id     INTEGER NOT NULL,
            content     TEXT    NOT NULL,
            created_at  TEXT    NOT NULL,
            likes       INTEGER NOT NULL DEFAULT 0
        )''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_qcomments_qid ON question_comments(question_id, created_at)')

        # ── 留言按讚記錄 ──
        conn.execute('''CREATE TABLE IF NOT EXISTS comment_likes (
            user_id    INTEGER NOT NULL,
            comment_id INTEGER NOT NULL,
            PRIMARY KEY (user_id, comment_id)
        )''')

        # ── 好友系統 ──
        conn.execute('''CREATE TABLE IF NOT EXISTS friendships (
            id          SERIAL PRIMARY KEY,
            from_user   INTEGER NOT NULL,
            to_user     INTEGER NOT NULL,
            status      TEXT    NOT NULL DEFAULT 'pending',
            created_at  TEXT    NOT NULL,
            UNIQUE(from_user, to_user)
        )''')

        # ── 好友私訊 ──
        conn.execute('''CREATE TABLE IF NOT EXISTS dm_threads (
            id          SERIAL PRIMARY KEY,
            user_lo     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            user_hi     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            last_msg_id INTEGER,
            last_at     TEXT,
            created_at  TEXT NOT NULL,
            UNIQUE(user_lo, user_hi),
            CHECK(user_lo < user_hi)
        )''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_dm_threads_lo_last ON dm_threads(user_lo, last_at)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_dm_threads_hi_last ON dm_threads(user_hi, last_at)')
        conn.execute('''CREATE TABLE IF NOT EXISTS dm_messages (
            id          SERIAL PRIMARY KEY,
            thread_id   INTEGER NOT NULL REFERENCES dm_threads(id) ON DELETE CASCADE,
            sender_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            body        TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            is_deleted  INTEGER NOT NULL DEFAULT 0,
            CHECK(char_length(body) BETWEEN 1 AND 500),
            CHECK(is_deleted IN (0, 1))
        )''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_dm_msg_thread ON dm_messages(thread_id, id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_dm_msg_sender_time ON dm_messages(sender_id, created_at)')
        conn.execute('''CREATE TABLE IF NOT EXISTS dm_reads (
            thread_id        INTEGER NOT NULL REFERENCES dm_threads(id) ON DELETE CASCADE,
            user_id          INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            last_read_msg_id INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(thread_id, user_id),
            CHECK(last_read_msg_id >= 0)
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS dm_blocks (
            blocker_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            blocked_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL,
            PRIMARY KEY(blocker_id, blocked_id),
            CHECK(blocker_id <> blocked_id)
        )''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_dm_blocks_blocked ON dm_blocks(blocked_id, blocker_id)')
        conn.execute('''CREATE TABLE IF NOT EXISTS dm_reports (
            id          SERIAL PRIMARY KEY,
            reporter_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            message_id  INTEGER NOT NULL REFERENCES dm_messages(id) ON DELETE CASCADE,
            reason      TEXT,
            status      TEXT NOT NULL DEFAULT 'open',
            created_at  TEXT NOT NULL,
            UNIQUE(reporter_id, message_id),
            CHECK(status IN ('open', 'reviewed', 'dismissed')),
            CHECK(reason IS NULL OR char_length(reason) <= 500)
        )''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_dm_reports_message ON dm_reports(message_id)')
        conn.execute('''CREATE TABLE IF NOT EXISTS dm_admin_audit (
            id         SERIAL PRIMARY KEY,
            admin_id   INTEGER,
            action     TEXT NOT NULL,
            report_id  INTEGER,
            thread_id  INTEGER,
            message_id INTEGER,
            reason     TEXT,
            created_at TEXT NOT NULL,
            CHECK(action IN ('view_report', 'view_context', 'delete_message', 'dismiss_report'))
        )''')

        # ── 題目另解回報 ──
        conn.execute('''CREATE TABLE IF NOT EXISTS question_alternative_reports (
            id            SERIAL PRIMARY KEY,
            user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            question_id   INTEGER NOT NULL,
            wrong_move_x  INTEGER NOT NULL,
            wrong_move_y  INTEGER NOT NULL,
            note          TEXT    NOT NULL DEFAULT '',
            status        TEXT    NOT NULL DEFAULT 'open',
            admin_note    TEXT,
            reviewed_by   INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_at    TEXT    NOT NULL,
            reviewed_at   TEXT,
            UNIQUE(user_id, question_id, wrong_move_x, wrong_move_y),
            CHECK(status IN ('open', 'accepted', 'dismissed')),
            CHECK(note IS NULL OR char_length(note) <= 500),
            CHECK(admin_note IS NULL OR char_length(admin_note) <= 500)
        )''')
        conn.execute('''CREATE INDEX IF NOT EXISTS idx_question_alt_reports_status_created
                        ON question_alternative_reports(status, created_at DESC)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS question_alt_report_audit (
            id         SERIAL PRIMARY KEY,
            report_id  INTEGER,
            admin_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            action     TEXT NOT NULL,
            detail     TEXT,
            created_at TEXT NOT NULL,
            CHECK(action IN ('view_reports', 'view_context', 'accept', 'dismiss'))
        )''')
        conn.execute(f'''CREATE TABLE IF NOT EXISTS question_problem_reports (
            id           SERIAL PRIMARY KEY,
            user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            question_id  INTEGER NOT NULL,
            reason_code  TEXT    NOT NULL,
            note         TEXT    NOT NULL DEFAULT '',
            status       TEXT    NOT NULL DEFAULT 'open',
            admin_note   TEXT,
            reviewed_by  INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_at   TEXT    NOT NULL,
            reviewed_at  TEXT,
            CHECK(status IN ('open','confirmed','dismissed','duplicate')),
            CHECK(reason_code IN ({_question_problem_report_reason_code_list_sql()})),
            CHECK(note IS NULL OR char_length(note) <= 500),
            CHECK(admin_note IS NULL OR char_length(admin_note) <= 500)
        )''')
        _ensure_question_problem_report_reason_code_constraint(conn)
        conn.execute('CREATE INDEX IF NOT EXISTS idx_qpr_status_created '
                     'ON question_problem_reports(status, created_at DESC)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_qpr_question_id '
                     'ON question_problem_reports(question_id)')
        conn.execute('''CREATE TABLE IF NOT EXISTS corpus_review_queue (
            id                    SERIAL PRIMARY KEY,
            source_type           TEXT    NOT NULL,
            source_ref            INTEGER,
            record_index          INTEGER NOT NULL,
            legacy_question_id    INTEGER NOT NULL,
            source_path           TEXT,
            content_sha256        TEXT,
            questions_json_commit TEXT    NOT NULL,
            reason                TEXT    NOT NULL,
            source_batch          TEXT,
            status                TEXT    NOT NULL DEFAULT 'pending',
            resolution_action     TEXT,
            admin_note            TEXT,
            reviewed_by           INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_at            TEXT    NOT NULL,
            reviewed_at           TEXT,
            UNIQUE(source_type, record_index),
            CHECK(source_type IN ('p0_parse_failure','duplicate_group','still_fails',
                                  'not_gn_pattern','player_reported','manual_flag')),
            CHECK(status IN ('pending','in_review','resolved','wont_fix'))
        )''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_crq_status_created '
                     'ON corpus_review_queue(status, created_at DESC)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_crq_source_type '
                     'ON corpus_review_queue(source_type)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_crq_record_index '
                     'ON corpus_review_queue(record_index)')
        conn.execute('''CREATE TABLE IF NOT EXISTS review_queue_audit (
            id           SERIAL PRIMARY KEY,
            target_type  TEXT    NOT NULL,
            target_id    INTEGER,
            admin_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            action       TEXT    NOT NULL,
            detail       TEXT,
            created_at   TEXT    NOT NULL
        )''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_review_queue_audit_target '
                     'ON review_queue_audit(target_type, target_id, created_at DESC)')

        # ── 好友挑戰 ──
        conn.execute('''CREATE TABLE IF NOT EXISTS friend_challenges (
            id            SERIAL PRIMARY KEY,
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

        # ── 怪物擊殺記錄（累計） ──
        conn.execute('''CREATE TABLE IF NOT EXISTS monster_kill_log (
            user_id      INTEGER NOT NULL,
            monster_type TEXT    NOT NULL,
            kill_count   INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, monster_type)
        )''')

        # ── 怪物擊殺歷史（帶時間戳，每擊敗一隻記一筆） ──
        conn.execute('''CREATE TABLE IF NOT EXISTS monster_kill_history (
            id           SERIAL PRIMARY KEY,
            user_id      INTEGER NOT NULL,
            monster_type TEXT    NOT NULL,
            monster_name TEXT    NOT NULL,
            killed_at    TEXT    NOT NULL,
            bf_date      TEXT    NOT NULL
        )''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_mkh_user_date ON monster_kill_history(user_id, bf_date)')

        # ── 書本難度等級覆寫 ──
        conn.execute('''CREATE TABLE IF NOT EXISTS book_bands (
            name      TEXT PRIMARY KEY,
            band_rank INTEGER NOT NULL
        )''')

        # ── 技能樹進度表 ──
        conn.execute('''CREATE TABLE IF NOT EXISTS skill_tree (
            user_id      INTEGER NOT NULL,
            discipline   TEXT    NOT NULL,
            level        INTEGER NOT NULL DEFAULT 0,
            unlocked_at  TEXT,
            PRIMARY KEY (user_id, discipline)
        )''')

        # ── 養成寵物 ──
        conn.execute('''CREATE TABLE IF NOT EXISTS user_pets (
            user_id            INTEGER PRIMARY KEY,
            pet_key            TEXT    NOT NULL,
            nickname           TEXT,
            level              INTEGER NOT NULL DEFAULT 1,
            xp                 INTEGER NOT NULL DEFAULT 0,
            fullness           INTEGER NOT NULL DEFAULT 60,
            affection          INTEGER NOT NULL DEFAULT 10,
            selected_at        TEXT    NOT NULL,
            last_fed_at        TEXT,
            last_interacted_at TEXT,
            updated_at         TEXT
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS pet_inventory (
            user_id  INTEGER NOT NULL,
            item_key TEXT    NOT NULL,
            qty      INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, item_key)
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS pet_action_log (
            id         SERIAL PRIMARY KEY,
            user_id    INTEGER NOT NULL,
            action     TEXT    NOT NULL,
            detail     TEXT,
            created_at TEXT    NOT NULL
        )''')

        # ── 寵物收藏 ──
        conn.execute('''CREATE TABLE IF NOT EXISTS pet_collection (
            user_id            INTEGER NOT NULL,
            pet_key            TEXT    NOT NULL,
            nickname           TEXT,
            level              INTEGER NOT NULL DEFAULT 1,
            xp                 INTEGER NOT NULL DEFAULT 0,
            fullness           INTEGER NOT NULL DEFAULT 60,
            affection          INTEGER NOT NULL DEFAULT 10,
            selected_at        TEXT    NOT NULL,
            last_fed_at        TEXT,
            last_interacted_at TEXT,
            last_pet_at        TEXT,
            last_train_at      TEXT,
            daily_key          TEXT,
            daily_bond         INTEGER NOT NULL DEFAULT 0,
            daily_train_xp     INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, pet_key)
        )''')

        # ── AI 自適應棋力測驗 ──
        conn.execute('''CREATE TABLE IF NOT EXISTS rating_test_sessions (
            id          TEXT    PRIMARY KEY,
            user_id     INTEGER,
            status      TEXT    NOT NULL DEFAULT 'in_progress',
            init_rating REAL    NOT NULL DEFAULT 1500,
            cur_rating  REAL    NOT NULL DEFAULT 1500,
            prior_sd    REAL    NOT NULL DEFAULT 300,
            rating_se   REAL,
            round       INTEGER NOT NULL DEFAULT 0,
            current_question_id INTEGER,
            current_question_token TEXT,
            current_question_role TEXT,
            bank_version TEXT,
            algorithm_version TEXT,
            answers     TEXT    NOT NULL DEFAULT '[]',
            trigger     TEXT    NOT NULL DEFAULT 'manual',
            started_at  TEXT    NOT NULL,
            last_activity_at TEXT,
            finished_at TEXT
        )''')
        for _col, _def in [
            ('prior_sd',               'REAL NOT NULL DEFAULT 300'),
            ('rating_se',              'REAL'),
            ('current_question_id',    'INTEGER'),
            ('current_question_token', 'TEXT'),
            ('current_question_role',  'TEXT'),
            ('bank_version',           'TEXT'),
            ('algorithm_version',      'TEXT'),
            ('last_activity_at',       'TEXT'),
        ]:
            add_column_if_not_exists(conn, 'rating_test_sessions', _col, _def)

        conn.execute('''CREATE TABLE IF NOT EXISTS rating_test_responses (
            id             SERIAL PRIMARY KEY,
            session_id     TEXT    NOT NULL,
            user_id        INTEGER,
            question_id    INTEGER NOT NULL,
            round          INTEGER NOT NULL,
            correct        INTEGER NOT NULL,
            response_ms    INTEGER,
            question_rating REAL   NOT NULL,
            ability_before REAL    NOT NULL,
            ability_after  REAL    NOT NULL,
            question_role  TEXT,
            bank_version   TEXT,
            algorithm_version TEXT,
            created_at     TEXT    NOT NULL,
            UNIQUE(session_id, round)
        )''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_rt_response_question '
                     'ON rating_test_responses(question_id, correct)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_rt_response_user '
                     'ON rating_test_responses(user_id, created_at)')
        for _col, _def in [
            ('question_role',    'TEXT'),
            ('bank_version',     'TEXT'),
            ('algorithm_version','TEXT'),
        ]:
            add_column_if_not_exists(conn, 'rating_test_responses', _col, _def)

        # ── 後續安全欄位升級 ──
        for _col, _def in [
            ('plan',           "TEXT NOT NULL DEFAULT 'free'"),
            ('nickname',       "TEXT"),
            ('elo_rating',     "REAL"),
            ('elo_updated_at', "TEXT"),
            ('elo_provisional', "INTEGER NOT NULL DEFAULT 0"),
            ('email',              "TEXT"),
            ('email_verified',     "INTEGER NOT NULL DEFAULT 0"),
            ('email_verify_token', "TEXT"),
            ('email_token_expires', "TEXT"),
            ('pw_reset_token',     "TEXT"),
            ('pw_reset_expires',   "TEXT"),
            ('premium_until',      "TEXT"),
            ('onboarding_path',    "TEXT CHECK (onboarding_path IN ('newbie','test'))"),
            ('onboarding_required', 'INTEGER NOT NULL DEFAULT 0'),
            ('admin_note',         "TEXT"),
        ]:
            add_column_if_not_exists(conn, 'users', _col, _def)
        conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_lower '
                     'ON users (LOWER(email)) WHERE email IS NOT NULL')

        for _col, _def in [
            ('source', "TEXT"),
        ]:
            add_column_if_not_exists(conn, 'review_log', _col, _def)

        for _col, _def in [
            ('xp',             'INTEGER NOT NULL DEFAULT 0'),
            ('combo_streak',   'INTEGER NOT NULL DEFAULT 0'),
            ('max_combo',      'INTEGER NOT NULL DEFAULT 0'),
            ('rank_level',     "TEXT NOT NULL DEFAULT 'LV1'"),
            ('rank_xp',        'INTEGER NOT NULL DEFAULT 0'),
            ('player_hp',      'INTEGER NOT NULL DEFAULT 100'),
            ('player_max_hp',  'INTEGER NOT NULL DEFAULT 100'),
            ('go_rank',                  "TEXT NOT NULL DEFAULT '30k'"),
            ('go_rank_initialized',      'INTEGER NOT NULL DEFAULT 0'),
            ('tour_done',                'INTEGER NOT NULL DEFAULT 0'),
            ('coins',                    'INTEGER NOT NULL DEFAULT 0'),
            ('challenge_wins',           'INTEGER NOT NULL DEFAULT 0'),
            ('challenge_win_streak',     'INTEGER NOT NULL DEFAULT 0'),
            ('max_challenge_win_streak', 'INTEGER NOT NULL DEFAULT 0'),
            ('title',          'TEXT DEFAULT NULL'),
            ('attr_atk',       'INTEGER DEFAULT 0'),
            ('attr_def',       'INTEGER DEFAULT 0'),
            ('attr_vis',       'INTEGER DEFAULT 0'),
            ('attr_prec',      'INTEGER DEFAULT 0'),
            ('free_pts',       'INTEGER DEFAULT 0'),
            ('reset_tickets',  'INTEGER DEFAULT 0'),
            ('tutorial_step',  'INTEGER DEFAULT 0'),
        ]:
            add_column_if_not_exists(conn, 'user_stats', _col, _def)

        for _col, _def in [
            ('av_type',        'TEXT'),
            ('av_value',       'TEXT'),
            ('accessory_id',   'TEXT'),
            ('pet_id',         'TEXT'),
            ('aura_id',        'TEXT'),
            ('character_key',  'TEXT'),
            ('combat_armor',   'TEXT'),
            ('combat_weapon',  'TEXT'),
            ('combat_cape',    'TEXT'),
            ('combat_offhand', 'TEXT'),
            ('combat_hat',     'TEXT'),
            ('combat_pet',     'TEXT'),
            ('combat_aura',    'TEXT'),
            ('combat_acc',     'TEXT'),
            ('stone_skin',     'TEXT'),
            ('board_skin',     'TEXT'),
        ]:
            add_column_if_not_exists(conn, 'player_appearance', _col, _def)

        for _col, _def in [
            ('last_pet_at',     'TEXT'),
            ('last_train_at',   'TEXT'),
            ('daily_key',       'TEXT'),
            ('daily_bond',      'INTEGER NOT NULL DEFAULT 0'),
            ('daily_train_xp',  'INTEGER NOT NULL DEFAULT 0'),
        ]:
            add_column_if_not_exists(conn, 'user_pets', _col, _def)

        # ── 初始設定與搬遷 ──
        now_iso = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat()
        conn.execute(
            'INSERT INTO user_stats(user_id, updated_at) '
            'SELECT id, ? FROM users '
            'ON CONFLICT (user_id) DO NOTHING',
            (now_iso,)
        )
        conn.execute('''
            UPDATE user_stats
               SET go_rank_initialized = 1
             WHERE COALESCE(go_rank_initialized, 0) = 0
               AND COALESCE(go_rank, '30k') <> '30k'
        ''')

        cursor.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'game_results'")
        if cursor.fetchone():
            conn.execute('''
                UPDATE user_stats
                   SET go_rank_initialized = 1
                 WHERE COALESCE(go_rank_initialized, 0) = 0
                   AND user_id IN (SELECT DISTINCT user_id FROM game_results)
            ''')

        # ── 遷移：舊段位格式 ──
        _migrate_ranks(conn)

        # book_bands 初始資料
        for _bn, _br in [
            ('26-30級',                        0),
            ('入門篇（21-25級）',               5),
            ('101圍棋練習冊 入門篇（上、中）',  0),
            ('101圍棋練習冊 入門篇（下）',      5),
        ]:
            conn.execute('INSERT INTO book_bands(name,band_rank) VALUES(?,?) ON CONFLICT (name) DO NOTHING',
                         (_bn, _br))

        # 寵物收藏（補出戰寵物至收藏表）
        conn.execute('''INSERT INTO pet_collection
            (user_id, pet_key, nickname, level, xp, fullness, affection, selected_at,
             last_fed_at, last_interacted_at, last_pet_at, last_train_at,
             daily_key, daily_bond, daily_train_xp)
            SELECT user_id, pet_key, nickname, level, xp, fullness, affection, selected_at,
             last_fed_at, last_interacted_at, last_pet_at, last_train_at,
             daily_key, daily_bond, daily_train_xp
            FROM user_pets ON CONFLICT (user_id, pet_key) DO NOTHING''')

        conn.commit()

    # ── Grimoire 系統：節點純淨度 & 法典進度表 ──────────────────────
    from grimoire_api import ensure_node_mastery_table
    with get_db() as conn:
        ensure_node_mastery_table(conn)

    # ── Community 排行榜獎勵：結算快照 & 發獎紀錄表（schema only）──
    from community_leaderboard_rewards import ensure_leaderboard_reward_tables
    with get_db() as conn:
        ensure_leaderboard_reward_tables(conn)

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

# ── SM-2 ───────────────────────────────────────────────────────


@app.route('/api/admin/shadow/dashboard')
@admin_required
def admin_shadow_dashboard():
    return jsonify(aggregate_shadow_events())


@app.route('/api/admin/shadow/dashboard/recent')
@admin_required
def admin_shadow_dashboard_recent():
    limit = request.args.get('limit', 200)
    route = request.args.get('route') or None
    parser_status = request.args.get('parser_status') or request.args.get('status') or None
    shadow_judgement = request.args.get('shadow_judgement') or request.args.get('judgement') or None
    request_id = request.args.get('request_id') or request.args.get('request_id_contains') or None
    schema_version = request.args.get('schema_version') or None
    return jsonify(recent_shadow_dashboard_data(
        limit=limit,
        route=route,
        parser_status=parser_status,
        shadow_judgement=shadow_judgement,
        request_id=request_id,
        schema_version=schema_version,
    ))

@app.route('/api/admin/deployment/readiness')
@admin_required
def admin_deployment_readiness():
    return jsonify(_read_runtime_deployment_readiness())

def sm2_update(ef, iv, rp, grade):
    q = grade
    if q < 3:
        rp, iv = 0, 1
    else:
        iv = 1 if rp==0 else (6 if rp==1 else round(iv*ef))
        rp += 1
    iv = min(iv, 3650)
    ef  = max(1.3, ef + 0.1 - (5-q)*(0.08+(5-q)*0.02))
    due = (datetime.date.today() + datetime.timedelta(days=iv)).isoformat()
    return ef, iv, rp, due

def should_grant_review_progress(existing_srs_row, grade):
    """Phase 4D anti-farming: True only for the first-ever passing review
    of a (user, question) pair. Progression side effects (XP, pet XP,
    monster/boss damage, kills, loot, SP, daily-quest credit) must gate on
    this, not on `last_grade` -- last_grade flips on every submission and
    can be reset by an intentional fail/pass toggle to re-farm rewards,
    while `progress_credited` is sticky once set. SRS scheduling itself
    (ease_factor/interval/due_date/last_grade) is unaffected and still
    updates on every review regardless of this check."""
    if grade < 3:
        return False
    return not bool(existing_srs_row and existing_srs_row.get('progress_credited'))

def _apply_credited_review_counters(total, streak, mx, combo_streak, max_combo, should_grant_progress):
    """Phase 4E anti-farming: total_correct/current_streak/max_streak/
    combo_streak/max_combo all feed badge thresholds (check_and_award) and
    gear unlocks (_gear_unlocked), so -- like XP/monster damage in Phase
    4D -- they must only advance on a credited review (should_grant_progress
    True), not on every repeat submission of an already-solved question.
    Only meant to be called for grade>=3; grade<3 handling (streak reset,
    streak-shield) is unrelated to farming and stays in the caller."""
    if not should_grant_progress:
        return total, streak, mx, combo_streak, max_combo
    total += 1
    streak += 1
    mx = max(mx, streak)
    combo_streak += 1
    max_combo = max(max_combo, combo_streak)
    return total, streak, mx, combo_streak, max_combo

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

def _is_whole_board_practice_question(q):
    """全盤實戰不是全題庫清單，而是每個 LV 的綜合試煉題。"""
    return (
        (q.get('discipline') or '') == 'whole_board'
        or q.get('encounter_type') in ('chapter_boss', 'book_boss')
        or 'whole_board' in (q.get('tags') or [])
    )

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
    # 載入成功（正常或容錯模式）：套用怪物分類、記下 mtime 後快取，
    # 之後同一個檔案 mtime 不變就直接命中記憶體快取，不再重讀 58MB JSON。
    try:
        mark_encounters(_questions_cache)
    except Exception as e:
        app.logger.warning(f'[_load_questions] 套用新版怪物分類失敗：{e}')
    _questions_mtime = mtime
    return _questions_cache if _questions_cache is not None else []

def _load_questions_fresh():
    """Read questions.json directly from disk without using the cache."""
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError('questions.json must contain a JSON list')
    return [item if isinstance(item, dict) else {} for item in data]

_QUESTIONS_JSON_MAX_BYTES = 128 * 1024 * 1024
_QUESTIONS_JSON_MAX_RECORDS = 200000


def _read_questions_dataset_readiness(path=None):
    configured_path = (path or DATA_FILE or '').strip()
    report = {
        'configured_path': configured_path,
        'exists': False,
        'readable': False,
        'parseable': False,
        'top_level_type': '',
        'schema_version': None,
        'record_count': 0,
        'record_count_ok': False,
        'within_byte_bound': False,
        'content_sha256': None,
        'structural_record_check': False,
        'size_bytes': None,
        'failures': [],
    }
    if not configured_path:
        report['failures'].append('questions path is not configured')
        return report
    if not os.path.exists(configured_path):
        report['failures'].append('questions file is missing')
        return report
    report['exists'] = True
    if not os.access(configured_path, os.R_OK):
        report['failures'].append('questions file is not readable')
        return report
    report['readable'] = True
    try:
        report['size_bytes'] = os.path.getsize(configured_path)
        report['within_byte_bound'] = report['size_bytes'] <= _QUESTIONS_JSON_MAX_BYTES
        if not report['within_byte_bound']:
            report['failures'].append('questions file exceeds bounded size limit')
            return report
        digest = hashlib.sha256()
        with open(configured_path, 'rb') as fh:
            raw = fh.read()
            digest.update(raw)
        report['content_sha256'] = digest.hexdigest()
        text = raw.decode('utf-8')
        data = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError, OSError, ValueError) as exc:
        report['failures'].append(f'questions file parse failed: {exc.__class__.__name__}')
        return report
    report['parseable'] = True
    report['top_level_type'] = type(data).__name__
    if not isinstance(data, list):
        report['failures'].append('questions file top-level value must be a JSON list')
        return report
    report['record_count'] = len(data)
    report['record_count_ok'] = 0 < report['record_count'] <= _QUESTIONS_JSON_MAX_RECORDS
    if not report['record_count_ok']:
        if report['record_count'] == 0:
            report['failures'].append('questions file contains no records')
        else:
            report['failures'].append('questions file exceeds bounded record limit')
        return report
    sample = next((record for record in data[:20] if isinstance(record, dict)), None)
    if sample:
        report['structural_record_check'] = bool(
            any(sample.get(key) not in (None, '') for key in (
                'id',
                'question_id',
                'source',
                'content',
                'sgf',
            ))
        )
        schema_version = sample.get('schema_version')
        if schema_version not in (None, ''):
            report['schema_version'] = str(schema_version)
    else:
        report['failures'].append('questions file does not contain a structural record')
    if not report['structural_record_check']:
        report['failures'].append('questions file failed the bounded structural record check')
    return report


def _read_runtime_deployment_readiness():
    from db import describe_database_url

    app_git_sha = (os.environ.get('APP_GIT_SHA') or os.environ.get('SOURCE_VERSION') or os.environ.get('GIT_COMMIT') or '').strip()
    image_revision = (os.environ.get('APP_GIT_SHA') or os.environ.get('SOURCE_VERSION') or os.environ.get('GIT_COMMIT') or '').strip()
    static_root = (os.environ.get('GO_ODYSSEY_LIVE_STATIC_ROOT') or '').strip()
    shadow_events_path = (os.environ.get('SHADOW_EVENTS_PATH') or shadow_dashboard.DEFAULT_SHADOW_EVENTS_PATH or '').strip()
    shadow_events_parent = os.path.dirname(shadow_events_path) or '.'

    questions = _read_questions_dataset_readiness()
    database_identity = describe_database_url(os.environ.get('DATABASE_URL'))
    database = {
        'identity': database_identity,
        'reachable': False,
        'tables': {},
        'failures': [],
    }
    required_tables = ('review_log', 'srs_cards', 'mistake_log', 'user_stats')
    try:
        with get_db() as conn:
            conn.execute('SELECT 1')
            database['reachable'] = True
            for table in required_tables:
                try:
                    conn.execute(f'SELECT 1 FROM {table} LIMIT 1')
                    database['tables'][table] = {'ok': True}
                except Exception as exc:
                    database['tables'][table] = {
                        'ok': False,
                        'error': exc.__class__.__name__,
                    }
                    database['failures'].append(f'{table} unavailable')
    except Exception as exc:
        database['failures'].append(f'database connection failed: {exc.__class__.__name__}')

    static_root_ok = bool(static_root) and os.path.isdir(static_root) and os.access(static_root, os.R_OK)
    shadow_events_exists = os.path.exists(shadow_events_path)
    shadow_events_valid = False
    if shadow_events_exists:
        shadow_events_valid = os.access(shadow_events_path, os.R_OK)
        if shadow_events_valid:
            shadow_events_valid = os.access(shadow_events_path, os.W_OK) or os.access(shadow_events_parent, os.W_OK)
    else:
        shadow_events_valid = os.access(shadow_events_parent, os.W_OK)

    report = {
        'ok': False,
        'app': {
            'git_sha': app_git_sha,
            'image_revision': image_revision,
            'build_date': (os.environ.get('APP_BUILD_DATE') or '').strip(),
            'questions_json_commit': _get_questions_json_commit(),
        },
        'questions': questions,
        'database': database,
        'static_root': {
            'path': static_root,
            'exists': bool(static_root) and os.path.isdir(static_root),
            'readable': static_root_ok,
        },
        'shadow_events': {
            'path': shadow_events_path,
            'exists': shadow_events_exists,
            'readable': shadow_events_exists and os.access(shadow_events_path, os.R_OK),
            'writable_or_valid': shadow_events_valid,
        },
        'failures': [],
    }

    if not app_git_sha:
        report['failures'].append('app git sha is missing')
    if not image_revision:
        report['failures'].append('image revision is missing')
    if not questions['parseable'] or not questions['record_count_ok'] or not questions['structural_record_check']:
        report['failures'].extend(questions['failures'])
    if not database['reachable']:
        report['failures'].extend(database['failures'])
    else:
        for table_name, result in database['tables'].items():
            if not result.get('ok'):
                report['failures'].append(f'{table_name} unavailable')
    if not report['static_root']['readable']:
        report['failures'].append('live static root is not readable')
    if not report['shadow_events']['writable_or_valid']:
        report['failures'].append('shadow events path is not writable or valid')

    report['ok'] = len(report['failures']) == 0
    return report


def _question_content_sha256(record):
    content = record.get('content')
    if not isinstance(content, str):
        return None
    return hashlib.sha256(content.encode('utf-8')).hexdigest()

def _normalize_question_move(raw):
    """Normalize a stored answer move to a stable {x, y} dict."""
    if isinstance(raw, dict):
        x, y = raw.get('x'), raw.get('y')
    elif isinstance(raw, (list, tuple)) and len(raw) >= 2:
        x, y = raw[0], raw[1]
    else:
        return None
    try:
        x = int(x)
        y = int(y)
    except (TypeError, ValueError):
        return None
    if x < 0 or y < 0:
        return None
    out = {'x': x, 'y': y}
    if isinstance(raw, dict):
        for key in ('status', 'report_id', 'note', 'reviewed_at', 'reviewed_by'):
            if raw.get(key) is not None:
                out[key] = raw.get(key)
    return out

def _question_accepted_moves(q):
    """Return unique accepted answer moves for a question."""
    raw_moves = q.get('accepted_moves') or q.get('accepted_answers') or []
    if isinstance(raw_moves, dict):
        raw_moves = [raw_moves]
    result = []
    seen = set()
    for raw in raw_moves:
        move = _normalize_question_move(raw)
        if not move:
            continue
        key = (move['x'], move['y'])
        if key in seen:
            continue
        seen.add(key)
        result.append(move)
    return result

def _question_accepts_move(q, x, y):
    return any(m['x'] == x and m['y'] == y for m in _question_accepted_moves(q))

def _append_question_accepted_move(q, move, *, report_id=None, admin_id=None, note=''):
    """Persist an accepted alternative move into the in-memory question dict."""
    norm = _normalize_question_move(move)
    if not norm:
        return False
    accepted = _question_accepted_moves(q)
    now = datetime.datetime.now().isoformat()
    entry = {
        'x': norm['x'],
        'y': norm['y'],
        'status': 'accepted',
        'report_id': report_id,
        'reviewed_by': admin_id,
        'reviewed_at': now,
    }
    if note:
        entry['note'] = str(note)[:500]
    replaced = False
    for idx, existing in enumerate(accepted):
        if existing['x'] == entry['x'] and existing['y'] == entry['y']:
            accepted[idx] = {**existing, **entry}
            replaced = True
            break
    if not replaced:
        accepted.append(entry)
    q['accepted_moves'] = accepted
    q['solution_state'] = 'accepted_alternative'
    q['solution_updated_at'] = now
    return True

def _disable_question_solution(q, *, admin_id=None, note=''):
    now = datetime.datetime.now().isoformat()
    q['enabled'] = False
    q['solution_state'] = 'disabled_no_answer'
    q['solution_disabled_at'] = now
    q['solution_disabled_by'] = admin_id
    if note:
        q['solution_disabled_reason'] = str(note)[:500]
    return True

def _invalidate_questions_cache():
    """題庫有更新時呼叫此函數清除快取。"""
    global _questions_cache
    _questions_cache = None

def _question_display_name(q):
    """Prefer the SGF filename for user-facing question labels."""
    source = str(q.get('source') or '').strip()
    if source:
        filename = source.replace('\\', '/').split('/')[-1].strip()
        if filename:
            name, ext = os.path.splitext(filename)
            if ext.lower() == '.sgf' and name:
                return name
            return filename
    return q.get('display_name') or q.get('topic') or ''

def _english_only(value):
    value = str(value or '').strip()
    return '' if re.search(r'[\u3400-\u9fff]', value) else value

def _question_display_name_en(q):
    """Return an English user-facing label without exposing bilingual source paths."""
    display = _english_only(q.get('display_name_en'))
    if display and not display.isdigit():
        return display
    level = _english_only(_i18n_level_en(q.get('level', '')) or q.get('level_en'))
    topic = _english_only(_i18n_topic_en(q.get('topic', '')) or q.get('topic_en'))
    return level or topic or f"Problem {q.get('id', '')}".strip()

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

def grant_premium_rewards(uid, conn, equip_default=True):
    """授予 Premium 專屬外觀物品、徽章。

    equip_default=True 用於首次升級/付款，會預設穿上 Premium 套裝。
    equip_default=False 用於舊帳號補發，只補背包與獎章，不覆蓋玩家目前外觀。
    """
    now = datetime.datetime.now().isoformat()
    # 授予所有 premium_only 物品
    for iid in PREMIUM_ITEMS:
        conn.execute(
            'INSERT OR IGNORE INTO player_wardrobe(user_id, item_id, obtained_at, source) VALUES(?,?,?,?)',
            (uid, iid, now, 'premium'))
    # 授予 Premium 徽章
    for bid in PREMIUM_BADGES:
        conn.execute(
            'INSERT OR IGNORE INTO badges_earned(user_id, badge_id, earned_at, seen) VALUES(?,?,?,0)',
            (uid, bid, now))
    # 預設裝備：御袍 + 冠冕 + 光環 + 麒麟 + 尊爵稱號 + 金墜
    eq = conn.execute('SELECT * FROM player_appearance WHERE user_id=?', (uid,)).fetchone()
    if eq and not equip_default:
        conn.commit()
        return
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

def ensure_premium_rewards(uid, conn, equip_default=False):
    """舊 Premium/Admin 帳號的冪等補發；不影響免費帳號。"""
    row = conn.execute(
        'SELECT plan, premium_until, is_admin FROM users WHERE id=?', (uid,)
    ).fetchone()
    if not row:
        return False
    plan = check_premium_expiry(
        conn, uid, row['plan'],
        row['premium_until'] if 'premium_until' in row.keys() else None)
    if plan == 'premium' or bool(row['is_admin']):
        grant_premium_rewards(uid, conn, equip_default=equip_default)
        return True
    return False

def check_premium_expiry(conn, uid, plan, premium_until):
    """訂閱到期 → 降回 free。回傳生效中的 plan。

    premium_until 為 NULL 視為永久（人工開通的舊帳號不受影響）。
    """
    if plan != 'premium' or not premium_until:
        return plan
    if premium_until >= datetime.datetime.now().isoformat():
        return plan
    conn.execute("UPDATE users SET plan='free' WHERE id=?", (uid,))
    conn.commit()
    print(f'[payment] uid={uid} premium 到期（{premium_until}），已降回 free')
    return 'free'

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
        row = conn.execute(
            "SELECT plan, premium_until FROM users WHERE id=?", (uid,)).fetchone()
        if not row:
            return False
        plan = check_premium_expiry(conn, uid, row['plan'],
                                    row['premium_until'] if 'premium_until' in row.keys() else None)
    return plan == 'premium'

def question_is_free(q):
    """免費版題庫鎖：開放至 FREE_RANK_MAX（含）的入門/基礎題；更高階鎖 Premium。
    rank 無法解析（_go_strength 回 0，等同 30k）→ 視為入門，開放。"""
    return _go_strength(q.get('rank')) <= _go_strength(FREE_RANK_MAX)

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

_BATTLEFIELD_NAME_EN = {
    'LV1 史萊姆 / 哥布林': 'LV1 Slime / Goblin',
    'LV1 提子訓練守衛': 'LV1 Capture Training Guard',
    'LV2 哥布林 / 洞窟蝙蝠': 'LV2 Goblin / Cave Bat',
    'LV2 雙叫吃突襲隊': 'LV2 Double-Atari Raiders',
    'LV3 獸人小兵': 'LV3 Orc Grunt',
    'LV3 做眼厚壁兵': 'LV3 Eye-Shape Shield Guard',
    'LV4 森林精靈': 'LV4 Forest Spirit',
    'LV4 霧林手筋師': 'LV4 Mistwood Tesuji Adept',
    'LV5 部落獸人': 'LV5 Tribal Orc',
    'LV5 銀牌懸賞首領': 'LV5 Silver Bounty Warlord',
    'LV6 飛龍 / 低階神靈': 'LV6 Wyvern / Lesser Deity',
    'LV6 龍谷計算者': 'LV6 Dragon Valley Calculator',
    'LV7 賢者 / 魔法師 / 亡靈': 'LV7 Sage / Mage / Undead',
    'LV7 高塔術師': 'LV7 Tower Archmage',
    'LV8 騎士 / 混沌領主': 'LV8 Knight / Chaos Lord',
    'LV8 皇家騎士長': 'LV8 Royal Knight Commander',
    'LV9 諸神': 'LV9 Pantheon Deity',
    'LV9 命運試煉官': 'LV9 Arbiter of Fate',
    'LV10 上古終焉神殿': 'LV10 Ancient Temple of Ruin',
    'LV10 終焉神': 'LV10 Deity of the End',
}

def _battlefield_name_en(monster_name):
    return _BATTLEFIELD_NAME_EN.get(monster_name, 'Training Monster')

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

def _update_monster_and_quests(conn, uid, qid, grade, q_info, combo_streak, today_str, should_grant_progress=True):
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

    if grade >= 3 and should_grant_progress:
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
                'type': nm[0], 'name': nm[1], 'name_en': _battlefield_name_en(nm[1]),
                'avatar': _battlefield_avatar(nm[0], nm[1]),
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
            # 擊殺掉落金幣（每日怪物金幣上限 _COIN_MONSTER_DAILY_CAP）
            try:
                if _coins_earned_today(conn, uid, 'monster_kill') < _COIN_MONSTER_DAILY_CAP:
                    _grant_coins(conn, uid, _COIN_PER_MONSTER, 'monster_kill')
            except Exception:
                pass
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
    elif grade >= 3:
        # Phase 4D anti-farming: repeat of an already-credited question.
        # No monster damage, no kill/loot/coins, no HP change -- SRS
        # scheduling for this review is still handled by the caller.
        pass
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
        progress_eligible=should_grant_progress,
    )

    # ── KO 懲罰：扣 SP ──────────────────────────────────────
    if player_ko:
        sp_row = conn.execute('SELECT current_sp FROM player_sp WHERE user_id=?', (uid,)).fetchone()
        if sp_row and sp_row['current_sp'] > 0:
            sp_penalty = max(5, round(sp_row['current_sp'] * 0.15))
            conn.execute('UPDATE player_sp SET current_sp=GREATEST(0,current_sp-?) WHERE user_id=?',
                         (sp_penalty, uid))

    # ── SP 增益 ──────────────────────────────────────────────
    sp_result = None
    if grade >= 3 and should_grant_progress:
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
            wardrobe_insert = conn.execute(
                'INSERT OR IGNORE INTO player_wardrobe(user_id,item_id,obtained_at,source) VALUES(?,?,?,?)',
                (uid, appear_item['id'], now_str, 'drop')
            )
            # 只有真的新入庫才回傳（重複掉落不算新物品）
            if wardrobe_insert.rowcount > 0:
                appearance_loot = appear_item

        # 擊殺計數（累計）
        conn.execute(
            'INSERT INTO monster_kill_log(user_id,monster_type,kill_count) VALUES(?,?,1) '
            'ON CONFLICT(user_id,monster_type) DO UPDATE SET kill_count=monster_kill_log.kill_count+1',
            (uid, monster_type)
        )
        # 擊殺歷史（帶時間戳）
        conn.execute(
            'INSERT INTO monster_kill_history(user_id,monster_type,monster_name,killed_at,bf_date) VALUES(?,?,?,?,?)',
            (uid, monster_type, monster_name, datetime.datetime.now().isoformat(), today_str)
        )

    return {
        'monster': {
            'name':          monster_name,
            'name_en':       _battlefield_name_en(monster_name),
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
            skill_info = {
                'id':       sk['id'],
                'name':     sk['name'],
                'icon':     sk['icon'],
                'type':     sk['type'],
                'desc':     sk['desc'],
                'cost_sp':  sk.get('cost_sp', 0),
                'color':    sk.get('color', 'teal'),
            }
            skill_en = _i18n_skill_node_en(sk['name'])
            if skill_en:
                skill_info['name_en'], skill_info['desc_en'] = skill_en
            skills_info.append(skill_info)

    # 計算 SP 上限（含裝備加成，equip_bonus 已在 with 區塊內取得）
    max_sp = SP_MAX_DAILY + int(equip_bonus)

    return jsonify({
        'name':       bf['monster_name'],
        'name_en':    _battlefield_name_en(bf['monster_name']),
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
                         monster_type, combo_streak, progress_eligible=True):
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
        pet_reward = None

        delta = 0
        streak_reset = False
        if not completed and key != 'all_complete':
            if key == 'kill_monsters' and monster_defeated:
                delta = 1
            elif key == 'streak_correct':
                if grade >= 3 and progress_eligible:
                    delta = 1           # 每答對一題 +1（重複同題不再累加）
                elif grade < 3:
                    streak_reset = True # 答錯時進度歸零
            elif key == 'challenge_dragon' and monster_type == 'dragon' and grade >= 3 and progress_eligible:
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
                _grant_pet_food(conn, uid, 'go_spirit_candy', 1)
                pet_reward = _pet_food_reward('go_spirit_candy', 1)
                xp_awarded = q['xp']
                _grant_coins(conn, uid, _COIN_PER_DAILY_QUEST, f'daily_quest:{key}')
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
            'coins':     _COIN_ALL_QUESTS_BONUS if q.get('bonus') else _COIN_PER_DAILY_QUEST,
            'bonus':     q.get('bonus', False),
            'pet_reward': pet_reward,
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
            _grant_pet_food(conn, uid, 'starfruit', 1)
            bonus['pet_reward'] = _pet_food_reward('starfruit', 1)
            bonus['coins'] = _COIN_ALL_QUESTS_BONUS
            _grant_coins(conn, uid, _COIN_ALL_QUESTS_BONUS, 'daily_quest:all_complete')
            conn.execute(
                'UPDATE daily_quests SET progress=3, completed=1, xp_awarded=? '
                'WHERE user_id=? AND quest_key=? AND quest_date=?',
                (bxp, uid, 'all_complete', today_str)
            )

    return results


# ══════════════════════════════════════════════════════════════
# 認證 API
# ══════════════════════════════════════════════════════════════

# ── 安全基礎設施：Turnstile / Resend 寄信 / 登入鎖定 ────────────
TURNSTILE_SECRET   = os.environ.get('TURNSTILE_SECRET', '')
TURNSTILE_SITE_KEY = os.environ.get('TURNSTILE_SITE_KEY', '')
RESEND_API_KEY     = os.environ.get('RESEND_API_KEY', '')
MAIL_FROM          = os.environ.get('MAIL_FROM') or '弈境奇兵 Go Odyssey <noreply@godokoro.com>'
SITE_URL           = os.environ.get('SITE_URL') or 'https://godokoro.com'
# 新玩家註冊通知站長：優先 NEW_USER_NOTIFY_EMAIL，其次 ADMIN_NOTIFY_EMAIL，最後預設信箱
NEW_USER_NOTIFY_EMAIL = (os.environ.get('NEW_USER_NOTIFY_EMAIL')
                         or os.environ.get('ADMIN_NOTIFY_EMAIL')
                         or 'beatleswu@gmail.com')
GOOGLE_CLIENT_ID   = (os.environ.get('GOOGLE_CLIENT_ID')
                      or '850248853315-dkjvura2gqroa4jokdkglo5h5h0h6tlb.apps.googleusercontent.com')

_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')

def _verify_turnstile(token: str) -> bool:
    """驗證 Cloudflare Turnstile token。未設定 secret 時放行（開發模式）。"""
    if not TURNSTILE_SECRET:
        return True
    if not token:
        return False
    try:
        body = json.dumps({'secret': TURNSTILE_SECRET, 'response': token}).encode()
        req = urllib.request.Request(
            'https://challenges.cloudflare.com/turnstile/v0/siteverify',
            data=body, headers={'Content-Type': 'application/json',
                                'User-Agent': 'GoOdyssey/1.0 (+https://godokoro.com)'})
        with urllib.request.urlopen(req, timeout=10) as r:
            return bool(json.loads(r.read()).get('success'))
    except Exception as e:
        print(f'[turnstile error] {e}')
        return False   # 驗證服務異常時拒絕，避免被當缺口

def _send_email(to: str, subject: str, html: str) -> bool:
    """透過 Resend API 寄信。未設定 API key 時印 log 並回 False。"""
    if not RESEND_API_KEY:
        print(f'[email skipped] RESEND_API_KEY 未設定 → {to}: {subject}')
        return False
    try:
        body = json.dumps({'from': MAIL_FROM, 'to': [to],
                           'subject': subject, 'html': html}).encode()
        # User-Agent 必加：Resend API 在 Cloudflare 後面，
        # Python-urllib 預設 UA 會被 WAF 擋（403 error 1010）
        req = urllib.request.Request(
            'https://api.resend.com/emails', data=body,
            headers={'Content-Type': 'application/json',
                     'Authorization': f'Bearer {RESEND_API_KEY}',
                     'User-Agent': 'GoOdyssey/1.0 (+https://godokoro.com)'})
        with urllib.request.urlopen(req, timeout=15) as r:
            ok = r.status in (200, 201)
            print(f'[email sent] {to}: {subject}' if ok else f'[email unexpected status] {r.status}')
            return ok
    except Exception as e:
        print(f'[email error] {to}: {e}')
        return False

def _send_email_async(to: str, subject: str, html: str):
    threading.Thread(target=_send_email, args=(to, subject, html), daemon=True).start()

def _notify_admin_new_user(info: dict):
    """新玩家註冊→寄詳細通知給站長。整段在背景執行緒做（含總人數查詢），不擋註冊回應。"""
    if not NEW_USER_NOTIFY_EMAIL:
        return
    def _esc(v):
        s = str(v) if v not in (None, '') else '—'
        return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    def _run():
        try:
            total = '—'
            try:
                with get_db() as conn:
                    total = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
            except Exception:
                pass
            rows = [
                ('使用者 ID', info.get('uid')),
                ('帳號', info.get('username')),
                ('暱稱', info.get('nickname')),
                ('Email', info.get('email')),
                ('Email 已驗證', '是' if info.get('email_verified') else '否（待驗證）'),
                ('註冊方式', info.get('method')),
                ('註冊時間', info.get('created_at')),
                ('來源 IP', info.get('ip')),
                ('裝置 (User-Agent)', info.get('user_agent')),
                ('目前總註冊人數', total),
            ]
            trs = ''.join(
                f'<tr><td style="padding:7px 14px;color:#666;white-space:nowrap;'
                f'border-bottom:1px solid #eee">{_esc(k)}</td>'
                f'<td style="padding:7px 14px;font-weight:600;'
                f'border-bottom:1px solid #eee">{_esc(v)}</td></tr>'
                for k, v in rows)
            html = (
                '<div style="font-family:sans-serif;max-width:560px;margin:0 auto">'
                '<h2 style="color:#0f766e">🎉 弈境奇兵 新玩家註冊</h2>'
                '<table style="border-collapse:collapse;width:100%;'
                'border:1px solid #e5e5e5;border-radius:8px;overflow:hidden">'
                f'{trs}</table>'
                '<p style="color:#999;font-size:12px;margin-top:16px">'
                '此信由系統自動發送。</p></div>')
            subject = (f"【弈境奇兵】新玩家註冊：{info.get('username') or '?'}"
                       f"（{info.get('method') or ''}）")
            _send_email(NEW_USER_NOTIFY_EMAIL, subject, html)
        except Exception as e:
            print(f'[admin notify error] {e}')
    threading.Thread(target=_run, daemon=True).start()

def _verify_email_html(username: str, link: str) -> str:
    return (f'<div style="font-family:sans-serif;max-width:480px;margin:0 auto">'
            f'<h2>歡迎加入弈境奇兵，{username}！</h2>'
            f'<p>請點擊下方按鈕完成 Email 驗證：</p>'
            f'<p><a href="{link}" style="display:inline-block;padding:12px 28px;'
            f'background:#1a1208;color:#f0d488;border-radius:10px;'
            f'text-decoration:none;font-weight:bold">驗證我的 Email</a></p>'
            f'<p style="color:#888;font-size:13px">連結 48 小時內有效。'
            f'若這不是你本人的操作，請忽略此信。</p></div>')

def _reset_pw_html(username: str, link: str) -> str:
    return (f'<div style="font-family:sans-serif;max-width:480px;margin:0 auto">'
            f'<h2>密碼重設請求</h2>'
            f'<p>{username} 你好，點擊下方按鈕重設密碼：</p>'
            f'<p><a href="{link}" style="display:inline-block;padding:12px 28px;'
            f'background:#1a1208;color:#f0d488;border-radius:10px;'
            f'text-decoration:none;font-weight:bold">重設密碼</a></p>'
            f'<p style="color:#888;font-size:13px">連結 1 小時內有效。'
            f'若你沒有申請重設，請忽略此信，密碼不會被更改。</p></div>')

# 登入失敗鎖定 / 註冊與寄信節流（單行程記憶體即可；app 以單一 python 行程運行）
_auth_fail_log: dict = {}     # key → [timestamp,...]
_auth_fail_lock = threading.Lock()
LOGIN_MAX_FAILS   = 5
LOGIN_LOCK_WINDOW = 15 * 60   # 15 分鐘

def _throttle_check(key: str, max_hits: int, window_sec: int) -> bool:
    """回傳 True 表示已超限（應拒絕）。"""
    now = time.time()
    with _auth_fail_lock:
        hits = [t for t in _auth_fail_log.get(key, []) if now - t < window_sec]
        _auth_fail_log[key] = hits
        return len(hits) >= max_hits

def _throttle_record(key: str):
    with _auth_fail_lock:
        _auth_fail_log.setdefault(key, []).append(time.time())

def _throttle_clear(key: str):
    with _auth_fail_lock:
        _auth_fail_log.pop(key, None)

def _client_ip() -> str:
    return (request.headers.get('X-Real-IP')
            or (request.headers.get('X-Forwarded-For') or '').split(',')[0].strip()
            or request.remote_addr or '?')

@app.route('/api/auth/config')
def auth_config():
    """前端需要的公開設定（Turnstile site key 等）。"""
    return jsonify({
        'turnstile_site_key': TURNSTILE_SITE_KEY,
        'google_client_id': GOOGLE_CLIENT_ID,
    })


def _normalize_google_user_name(email: str, sub: str) -> str:
    local = (email.split('@', 1)[0] if email else '') or 'google'
    local = re.sub(r'[^a-z0-9_]+', '_', local.lower()).strip('_')
    local = local[:12] or 'google'
    suffix = re.sub(r'\D', '', (sub or ''))[-6:] or secrets.token_hex(3)
    return f'g_{local}_{suffix}'[:20]


def _looks_like_google_generated_label(value: str) -> bool:
    label = str(value or '').strip().lower()
    if not label:
        return False
    return bool(
        re.fullmatch(r'g_[a-z0-9_]{1,12}_\d{6}', label)
        or re.fullmatch(r'g_\d{1,8}', label)
    )


def _user_display_label(nickname: str = '', display_name: str = '', username: str = '',
                        fallback: str = 'Player') -> str:
    nickname = str(nickname or '').strip()
    if nickname:
        return nickname
    for candidate in (display_name, username):
        candidate = str(candidate or '').strip()
        if not candidate:
            continue
        if '@' in candidate or _looks_like_google_generated_label(candidate):
            continue
        return candidate
    return fallback


def _verify_google_id_token(id_token: str) -> dict:
    if not id_token:
        raise ValueError('missing_token')
    url = ('https://oauth2.googleapis.com/tokeninfo?id_token=' +
           urllib.parse.quote(id_token, safe=''))
    with urllib.request.urlopen(url, timeout=15) as resp:
        payload = json.loads(resp.read().decode('utf-8'))
    aud = payload.get('aud') or ''
    iss = payload.get('iss') or ''
    email = (payload.get('email') or '').strip().lower()
    if aud != GOOGLE_CLIENT_ID:
        raise ValueError('bad_audience')
    if iss not in ('accounts.google.com', 'https://accounts.google.com'):
        raise ValueError('bad_issuer')
    if str(payload.get('email_verified', '')).lower() not in ('true', '1', 'yes'):
        raise ValueError('email_not_verified')
    if not payload.get('sub') or not email:
        raise ValueError('missing_profile')
    payload['email'] = email
    return payload

@app.route('/api/auth/register', methods=['POST'])
def auth_register():
    data     = request.get_json() or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    confirm  = data.get('confirm')  or ''
    nickname = (data.get('nickname') or '').strip()
    email    = (data.get('email') or '').strip().lower()
    cf_token = data.get('cf_token') or ''

    # ── 應用層 IP 節流（nginx rate limit 之外的第二道防線）──
    ip = _client_ip()
    if _throttle_check(f'reg:{ip}', 5, 3600):
        return jsonify({'error': '註冊太頻繁，請稍後再試'}), 429

    # ── 機器人驗證 ──
    if not _verify_turnstile(cf_token):
        return jsonify({'error': '機器人驗證未通過，請重新整理頁面再試'}), 400

    # ── 驗證 ──
    if not username or not password or not email:
        return jsonify({'error': '請填寫帳號、Email 和密碼'}), 400
    if not re.match(r'^[A-Za-z0-9_]{3,20}$', username):
        return jsonify({'error': '帳號只能包含英文、數字、底線，長度 3–20 字元'}), 400
    if len(email) > 254 or not _EMAIL_RE.match(email):
        return jsonify({'error': 'Email 格式不正確'}), 400
    if len(password) < 8:
        return jsonify({'error': '密碼至少 8 個字元'}), 400
    if confirm and confirm != password:
        return jsonify({'error': '兩次密碼不一致'}), 400
    if nickname and len(nickname) > 30:
        return jsonify({'error': '暱稱不能超過 30 字元'}), 400

    now = datetime.datetime.now().isoformat()
    pw_hash = generate_password_hash(password)
    verify_token = secrets.token_urlsafe(32)
    token_expires = (datetime.datetime.now()
                     + datetime.timedelta(hours=48)).isoformat()

    with get_db() as conn:
        # 檢查帳號 / Email 是否已存在
        existing = conn.execute(
            'SELECT id FROM users WHERE LOWER(username)=LOWER(?)', (username,)
        ).fetchone()
        if existing:
            return jsonify({'error': '此帳號已被使用，請換一個'}), 409
        email_taken = conn.execute(
            'SELECT id FROM users WHERE LOWER(email)=?', (email,)
        ).fetchone()
        if email_taken:
            return jsonify({'error': '此 Email 已被註冊，可改用「忘記密碼」找回帳號'}), 409

        # 建立用戶（RETURNING id 取代 lastrowid，相容 PostgreSQL）
        cur = conn.execute(
            'INSERT INTO users(username, password_hash, is_admin, plan, created_at,'
            ' nickname, email, email_verified, email_verify_token, email_token_expires,'
            ' onboarding_required)'
            ' VALUES(?,?,0,?,?,?,?,0,?,?,1) RETURNING id',
            (username, pw_hash, 'free', now, nickname or None,
             email, verify_token, token_expires)
        )
        uid = cur.fetchone()[0]
        conn.execute('INSERT OR IGNORE INTO user_stats(user_id) VALUES(?)', (uid,))
        conn.commit()

    _throttle_record(f'reg:{ip}')
    link = f'{SITE_URL}/api/auth/verify_email?token={verify_token}'
    _send_email_async(email, '【弈境奇兵】請驗證你的 Email',
                      _verify_email_html(username, link))

    # 自動登入
    _notify_admin_new_user({
        'uid': uid, 'username': username, 'nickname': nickname,
        'email': email, 'created_at': now, 'method': 'Email 密碼註冊',
        'email_verified': False, 'ip': ip,
        'user_agent': request.headers.get('User-Agent', ''),
    })

    session.permanent   = True
    session['user_id']  = uid
    session['username'] = username
    session['nickname'] = nickname or ''
    session['is_admin'] = False
    session['plan']     = 'free'
    return jsonify({'ok': True, 'username': username, 'nickname': nickname or '',
                    'verify_email_sent': bool(RESEND_API_KEY)})


@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    data     = request.get_json()
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    if not username or not password:
        return jsonify({'error': '請填寫帳號和密碼'}), 400

    # ── 暴力破解鎖定：同帳號 15 分鐘內錯 5 次即暫鎖 ──
    lock_key = f'login:{username.lower()}'
    if _throttle_check(lock_key, LOGIN_MAX_FAILS, LOGIN_LOCK_WINDOW):
        return jsonify({'error': '登入失敗次數過多，帳號暫時鎖定，請 15 分鐘後再試'}), 429

    with get_db() as conn:
        row = conn.execute(
            'SELECT * FROM users WHERE LOWER(username)=LOWER(?) OR LOWER(email)=LOWER(?) '
            'ORDER BY CASE WHEN LOWER(username)=LOWER(?) THEN 0 ELSE 1 END LIMIT 1',
            (username, username, username)).fetchone()
        if not row or not check_password_hash(row['password_hash'], password):
            _throttle_record(lock_key)
            return jsonify({'error': '帳號或密碼錯誤'}), 401
        _throttle_clear(lock_key)

        conn.execute('UPDATE users SET last_login=? WHERE id=?',
                     (datetime.datetime.now().isoformat(), row['id']))
        conn.execute('INSERT OR IGNORE INTO user_stats(user_id) VALUES(?)', (row['id'],))
        conn.commit()

        plan = row['plan'] if 'plan' in row.keys() else 'free'
        plan = check_premium_expiry(
            conn, row['id'], plan,
            row['premium_until'] if 'premium_until' in row.keys() else None)
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


@app.route('/api/auth/google_login', methods=['POST'])
def auth_google_login():
    data = request.get_json(silent=True) or {}
    credential = (data.get('credential') or data.get('id_token') or '').strip()
    if not credential:
        return jsonify({'error': 'missing_google_credential'}), 400
    try:
        profile = _verify_google_id_token(credential)
    except Exception:
        return jsonify({'error': 'google_login_failed'}), 401

    google_sub = profile['sub']
    email = profile['email']
    nickname = (profile.get('name') or profile.get('given_name') or '').strip()
    now = datetime.datetime.now().isoformat()
    _new_google_user = None

    with get_db() as conn:
        row = conn.execute('SELECT * FROM users WHERE google_sub=?', (google_sub,)).fetchone()
        if row:
            uid = row['id']
            username = row['username']
            conn.execute(
                'UPDATE users SET email=?, email_verified=1, last_login=?, '
                'google_sub=COALESCE(google_sub, ?) WHERE id=?',
                (email, now, google_sub, uid))
        else:
            row = conn.execute('SELECT * FROM users WHERE LOWER(email)=LOWER(?)', (email,)).fetchone()
            if row:
                uid = row['id']
                username = row['username']
                conn.execute(
                    'UPDATE users SET google_sub=?, email=?, email_verified=1, last_login=?, '
                    'nickname=COALESCE(NULLIF(nickname, \'\'), ?) WHERE id=?',
                    (google_sub, email, now, nickname or None, uid))
            else:
                username = _normalize_google_user_name(email, google_sub)
                exists = conn.execute(
                    'SELECT 1 FROM users WHERE LOWER(username)=LOWER(?)', (username,)).fetchone()
                if exists:
                    suffix = re.sub(r'\D', '', google_sub)[-8:] or secrets.token_hex(4)
                    username = f'g_{suffix}'[:20]
                pw_hash = generate_password_hash(secrets.token_urlsafe(32))
                cur = conn.execute(
                    'INSERT INTO users(username, password_hash, is_admin, plan, created_at, '
                    'last_login, nickname, email, email_verified, google_sub, onboarding_required) '
                    'VALUES(?,?,?,?,?,?,?,?,1,?,1) RETURNING id',
                    (username, pw_hash, 0, 'free', now, now, nickname or None, email, google_sub))
                uid = cur.fetchone()[0]
                conn.execute('INSERT OR IGNORE INTO user_stats(user_id) VALUES(?)', (uid,))
                _new_google_user = {
                    'uid': uid, 'username': username, 'nickname': nickname,
                    'email': email, 'created_at': now, 'method': 'Google 註冊',
                    'email_verified': True, 'ip': _client_ip(),
                    'user_agent': request.headers.get('User-Agent', ''),
                }
        conn.commit()

        row = conn.execute(
            'SELECT id, username, nickname, is_admin, plan, premium_until '
            'FROM users WHERE id=?', (uid,)).fetchone()
        plan = row['plan'] if row and 'plan' in row.keys() else 'free'
        plan = check_premium_expiry(
            conn, uid, plan, row['premium_until'] if row and 'premium_until' in row.keys() else None)
        if row:
            nickname = row['nickname'] or nickname or ''

    if _new_google_user:
        _notify_admin_new_user(_new_google_user)

    is_admin = bool(row['is_admin']) if row else False
    session.permanent    = True
    session['user_id']   = uid
    session['username']  = username
    session['nickname']  = nickname or ''
    session['is_admin']  = is_admin
    session['plan']      = plan
    return jsonify({
        'ok': True,
        'username': username,
        'nickname': nickname or '',
        'is_admin': is_admin,
        'plan': plan,
        'is_premium': plan == 'premium' or is_admin,
        'redirect': '/',
    })

@app.route('/api/auth/logout', methods=['POST'])
def auth_logout():
    session.clear()
    resp = jsonify({'ok': True})
    resp.delete_cookie('session', path='/', samesite='Lax')
    return resp

# ── Email 驗證 / 忘記密碼 ──────────────────────────────────────

@app.route('/api/auth/verify_email')
def auth_verify_email():
    token = (request.args.get('token') or '').strip()
    if not token:
        return redirect('/login?verify=fail')
    now = datetime.datetime.now().isoformat()
    with get_db() as conn:
        row = conn.execute(
            'SELECT id, email_token_expires FROM users WHERE email_verify_token=?',
            (token,)).fetchone()
        if not row or (row['email_token_expires'] or '') < now:
            return redirect('/login?verify=expired')
        conn.execute(
            'UPDATE users SET email_verified=1, email_verify_token=NULL,'
            ' email_token_expires=NULL WHERE id=?', (row['id'],))
        conn.commit()
    return redirect('/login?verify=ok')

@app.route('/api/auth/resend_verification', methods=['POST'])
def auth_resend_verification():
    uid = session.get('user_id')
    if not uid:
        return jsonify({'error': '請先登入'}), 401
    if _throttle_check(f'resend:{uid}', 1, 300):
        return jsonify({'error': '寄送太頻繁，請 5 分鐘後再試'}), 429
    with get_db() as conn:
        row = conn.execute(
            'SELECT username, email, email_verified FROM users WHERE id=?',
            (uid,)).fetchone()
        if not row or not row['email']:
            return jsonify({'error': '帳號沒有 Email'}), 400
        if row['email_verified']:
            return jsonify({'ok': True, 'already': True})
        token = secrets.token_urlsafe(32)
        expires = (datetime.datetime.now()
                   + datetime.timedelta(hours=48)).isoformat()
        conn.execute('UPDATE users SET email_verify_token=?, email_token_expires=?'
                     ' WHERE id=?', (token, expires, uid))
        conn.commit()
    _throttle_record(f'resend:{uid}')
    link = f'{SITE_URL}/api/auth/verify_email?token={token}'
    _send_email_async(row['email'], '【弈境奇兵】請驗證你的 Email',
                      _verify_email_html(row['username'], link))
    return jsonify({'ok': True})

@app.route('/api/auth/forgot_password', methods=['POST'])
def auth_forgot_password():
    data  = request.get_json() or {}
    email = (data.get('email') or '').strip().lower()
    if not email or not _EMAIL_RE.match(email):
        return jsonify({'error': 'Email 格式不正確'}), 400
    ip = _client_ip()
    if _throttle_check(f'forgot:{ip}', 3, 900) or _throttle_check(f'forgot:{email}', 1, 300):
        return jsonify({'error': '請求太頻繁，請稍後再試'}), 429
    _throttle_record(f'forgot:{ip}')
    _throttle_record(f'forgot:{email}')
    with get_db() as conn:
        row = conn.execute(
            'SELECT id, username FROM users WHERE LOWER(email)=?', (email,)).fetchone()
        if row:
            token = secrets.token_urlsafe(32)
            expires = (datetime.datetime.now()
                       + datetime.timedelta(hours=1)).isoformat()
            conn.execute('UPDATE users SET pw_reset_token=?, pw_reset_expires=?'
                         ' WHERE id=?', (token, expires, row['id']))
            conn.commit()
            link = f'{SITE_URL}/login?reset_token={token}'
            _send_email_async(email, '【弈境奇兵】密碼重設',
                              _reset_pw_html(row['username'], link))
    # 不論 email 是否存在都回成功，避免被用來枚舉帳號
    return jsonify({'ok': True})

@app.route('/api/auth/reset_password', methods=['POST'])
def auth_reset_password():
    data     = request.get_json() or {}
    token    = (data.get('token') or '').strip()
    password = data.get('password') or ''
    if not token:
        return jsonify({'error': '重設連結無效'}), 400
    if len(password) < 8:
        return jsonify({'error': '密碼至少 8 個字元'}), 400
    now = datetime.datetime.now().isoformat()
    with get_db() as conn:
        row = conn.execute(
            'SELECT id, username, pw_reset_expires FROM users WHERE pw_reset_token=?',
            (token,)).fetchone()
        if not row or (row['pw_reset_expires'] or '') < now:
            return jsonify({'error': '重設連結已失效，請重新申請'}), 400
        conn.execute(
            'UPDATE users SET password_hash=?, pw_reset_token=NULL,'
            ' pw_reset_expires=NULL WHERE id=?',
            (generate_password_hash(password), row['id']))
        conn.commit()
        _throttle_clear(f"login:{row['username'].lower()}")
    return jsonify({'ok': True})

_NEWBIE_TASK_TOUR = 'tour_started'
_NEWBIE_TASK_PET = 'stage1_pet_claim'
_NEWBIE_TASK_DAILY = 'stage1_daily_training'
_NEWBIE_TASK_HERO = 'stage2_hero_card'
_NEWBIE_TASK_BOT = 'stage3_bot_game'
_NEWBIE_TASK_STAGE2_MAP = 'stage2_map_quiz'
_NEWBIE_TASK_STAGE3_DAILY = 'stage3_daily_training'
_NEWBIE_TASK_STAGE4_CURRICULUM = 'stage4_curriculum_task'
_NEWBIE_TASK_STAGE5_HERO = 'stage5_hero_card'
_NEWBIE_TASK_STAGE6_BOT = 'stage6_bot_game'
_NEWBIE_TASK_STAGE7_SHOP = 'stage7_shop_purchase'
_NEWBIE_STAGE_REWARDS = {
    _NEWBIE_TASK_PET: {'coins': 20, 'shop_items': ['pet_snack']},
    _NEWBIE_TASK_STAGE2_MAP: {'coins': 20, 'shop_items': ['hint_ticket']},
    _NEWBIE_TASK_STAGE3_DAILY: {'coins': 30, 'shop_items': ['streak_shield'], 'title': 'title_newbie_voyage'},
    _NEWBIE_TASK_STAGE4_CURRICULUM: {'coins': 25, 'shop_items': ['ai_explain_ticket']},
    _NEWBIE_TASK_STAGE5_HERO: {'coins': 20, 'shop_items': ['small_xp_potion']},
    _NEWBIE_TASK_STAGE6_BOT: {'coins': 30, 'shop_items': ['extra_questions_small']},
    _NEWBIE_TASK_STAGE7_SHOP: {
        'coins': 50,
        'shop_items': ['extra_questions', 'xp_potion', 'double_streak_shield', 'starfruit_basket'],
        'title': 'title_claire_recruit',
    },
}
_NEWBIE_TASK_SOURCES = {
    _NEWBIE_TASK_PET: 'pet_panel',
    _NEWBIE_TASK_STAGE2_MAP: 'map_quiz',
    _NEWBIE_TASK_STAGE3_DAILY: 'daily_training',
    _NEWBIE_TASK_STAGE4_CURRICULUM: 'curriculum_quest',
    _NEWBIE_TASK_STAGE5_HERO: 'hero_card',
    _NEWBIE_TASK_STAGE6_BOT: 'bot_result',
    _NEWBIE_TASK_STAGE7_SHOP: 'shop_purchase',
}
_NEWBIE_TASK_KEYS = {
    _NEWBIE_TASK_TOUR,
    _NEWBIE_TASK_PET,
    _NEWBIE_TASK_DAILY,
    _NEWBIE_TASK_HERO,
    _NEWBIE_TASK_BOT,
    _NEWBIE_TASK_STAGE2_MAP,
    _NEWBIE_TASK_STAGE3_DAILY,
    _NEWBIE_TASK_STAGE4_CURRICULUM,
    _NEWBIE_TASK_STAGE5_HERO,
    _NEWBIE_TASK_STAGE6_BOT,
    _NEWBIE_TASK_STAGE7_SHOP,
}


def _newbie_daily_completed_count(uid, conn):
    today = datetime.date.today().isoformat()
    row = conn.execute(
        'SELECT question_ids FROM daily_training_queue WHERE user_id=? AND date=?',
        (uid, today)
    ).fetchone()
    if not row:
        return 0
    try:
        queue_ids = {int(qid) for qid in json.loads(row['question_ids'] or '[]')}
    except (TypeError, ValueError, json.JSONDecodeError):
        return 0
    if not queue_ids:
        return 0
    answered = {
        int(r['question_id'])
        for r in conn.execute(
            'SELECT DISTINCT question_id FROM review_log '
            'WHERE user_id=? AND DATE(reviewed_at)=?',
            (uid, today)
        ).fetchall()
    }
    return len(queue_ids & answered)


def _newbie_log_event(conn, uid, event_key, event_name, task_key=None, payload=None):
    conn.execute(
        'INSERT OR IGNORE INTO newbie_quest_events '
        '(user_id,event_key,event_name,task_key,payload,occurred_at) VALUES(?,?,?,?,?,?)',
        (uid, event_key, event_name, task_key,
         json.dumps(payload or {}, ensure_ascii=False), datetime.datetime.now().isoformat())
    )


def _newbie_complete_task(conn, uid, task_key, source):
    now = datetime.datetime.now().isoformat()
    inserted = conn.execute(
        'INSERT OR IGNORE INTO newbie_quest_tasks(user_id,task_key,source,completed_at) '
        'VALUES(?,?,?,?)',
        (uid, task_key, source, now)
    ).rowcount
    if not inserted:
        return False
    stage_value = 1
    graduated_value = 0
    if task_key == _NEWBIE_TASK_PET:
        stage_value = 2
    elif task_key == _NEWBIE_TASK_DAILY:
        stage_value = 2
    elif task_key == _NEWBIE_TASK_STAGE2_MAP:
        stage_value = 3
    elif task_key == _NEWBIE_TASK_STAGE3_DAILY:
        stage_value = 4
    elif task_key == _NEWBIE_TASK_STAGE4_CURRICULUM:
        stage_value = 5
    elif task_key == _NEWBIE_TASK_STAGE5_HERO:
        stage_value = 6
    elif task_key == _NEWBIE_TASK_STAGE6_BOT:
        stage_value = 7
    elif task_key == _NEWBIE_TASK_STAGE7_SHOP:
        stage_value = 7
        graduated_value = 1
    elif task_key == _NEWBIE_TASK_HERO:
        stage_value = 3
    elif task_key == _NEWBIE_TASK_BOT:
        stage_value = 4
        graduated_value = 1
    _newbie_log_event(
        conn, uid, f'task_done:{task_key}', 'newbie_quest_task_done', task_key,
        {'stage': stage_value}
    )
    if task_key == _NEWBIE_TASK_DAILY:
        conn.execute(
            'UPDATE newbie_quest_state SET stage=2,updated_at=? WHERE user_id=?',
            (now, uid)
        )
        conn.execute(
            'INSERT OR IGNORE INTO badges_earned(user_id,badge_id,earned_at,seen) '
            "VALUES(?,'newbie_first_bounty',?,0)",
            (uid, now)
        )
    elif task_key == _NEWBIE_TASK_HERO:
        conn.execute(
            'UPDATE newbie_quest_state SET stage=3,updated_at=? WHERE user_id=?',
            (now, uid)
        )
    elif task_key == _NEWBIE_TASK_BOT:
        conn.execute(
            'UPDATE newbie_quest_state SET stage=4,graduated=1,updated_at=? WHERE user_id=?',
            (now, uid)
        )
    elif task_key in {
        _NEWBIE_TASK_PET,
        _NEWBIE_TASK_STAGE2_MAP,
        _NEWBIE_TASK_STAGE3_DAILY,
        _NEWBIE_TASK_STAGE4_CURRICULUM,
        _NEWBIE_TASK_STAGE5_HERO,
        _NEWBIE_TASK_STAGE6_BOT,
    }:
        conn.execute(
            'UPDATE newbie_quest_state SET stage=?,updated_at=? WHERE user_id=?',
            (stage_value, now, uid)
        )
    elif task_key == _NEWBIE_TASK_STAGE7_SHOP:
        conn.execute(
            'UPDATE newbie_quest_state SET stage=7,graduated=1,updated_at=? WHERE user_id=?',
            (now, uid)
        )
    return True


def _newbie_progress_prerequisite(snapshot, task_key):
    completed = set(snapshot['state'].get('completed') or [])
    if task_key == _NEWBIE_TASK_PET:
        return True
    canonical_chain = {
        _NEWBIE_TASK_STAGE2_MAP: _NEWBIE_TASK_PET,
        _NEWBIE_TASK_STAGE3_DAILY: _NEWBIE_TASK_STAGE2_MAP,
        _NEWBIE_TASK_STAGE4_CURRICULUM: _NEWBIE_TASK_STAGE3_DAILY,
        _NEWBIE_TASK_STAGE5_HERO: _NEWBIE_TASK_STAGE4_CURRICULUM,
        _NEWBIE_TASK_STAGE6_BOT: _NEWBIE_TASK_STAGE5_HERO,
        _NEWBIE_TASK_STAGE7_SHOP: _NEWBIE_TASK_STAGE6_BOT,
    }
    if task_key in canonical_chain:
        return canonical_chain[task_key] in completed
    if task_key == _NEWBIE_TASK_HERO:
        return _NEWBIE_TASK_DAILY in completed
    if task_key == _NEWBIE_TASK_BOT:
        return _NEWBIE_TASK_HERO in completed
    return task_key in completed


def _reward_display_item(item_key, qty=1):
    meta = SHOP_ITEMS.get(item_key) or {}
    return {
        'key': item_key,
        'qty': qty,
        'name': meta.get('name', item_key),
        'name_en': meta.get('name_en', item_key),
        'icon': meta.get('icon', '🎁'),
    }


def _newbie_quest_snapshot(uid, conn, sync_server_tasks=True):
    user = conn.execute(
        'SELECT onboarding_path FROM users WHERE id=?', (uid,)
    ).fetchone()
    onboarding_path = user['onboarding_path'] if user else None
    state = conn.execute(
        'SELECT stage,graduated FROM newbie_quest_state WHERE user_id=?', (uid,)
    ).fetchone()
    if not state and onboarding_path == 'newbie':
        now = datetime.datetime.now().isoformat()
        conn.execute(
            'INSERT OR IGNORE INTO newbie_quest_state '
            '(user_id,stage,graduated,created_at,updated_at) VALUES(?,1,0,?,?)',
            (uid, now, now)
        )
        state = conn.execute(
            'SELECT stage,graduated FROM newbie_quest_state WHERE user_id=?', (uid,)
        ).fetchone()
    if not state:
        return {
            'user_id': uid,
            'eligible': False,
            'state': {'stage': 1, 'completed': [], 'graduated': False},
            'daily_completed': 0,
            'newly_completed': [],
        }

    newly_completed = []
    daily_completed = _newbie_daily_completed_count(uid, conn)
    if sync_server_tasks:
        tour = conn.execute(
            'SELECT tour_done FROM user_stats WHERE user_id=?', (uid,)
        ).fetchone()
        if tour and bool(tour['tour_done']):
            if _newbie_complete_task(conn, uid, _NEWBIE_TASK_TOUR, 'tour_done'):
                newly_completed.append(_NEWBIE_TASK_TOUR)
        if daily_completed > 0:
            if _newbie_complete_task(conn, uid, _NEWBIE_TASK_DAILY, 'daily_training'):
                newly_completed.append(_NEWBIE_TASK_DAILY)

    state = conn.execute(
        'SELECT stage,graduated FROM newbie_quest_state WHERE user_id=?', (uid,)
    ).fetchone()
    completed = [
        r['task_key'] for r in conn.execute(
            'SELECT task_key FROM newbie_quest_tasks WHERE user_id=? ORDER BY completed_at',
            (uid,)
        ).fetchall()
    ]
    graduated = bool(state['graduated']) if state else False
    return {
        'user_id': uid,
        'eligible': not graduated,
        'state': {
            'stage': int(state['stage'] or 1) if state else 1,
            'completed': completed,
            'graduated': graduated,
        },
        'daily_completed': daily_completed,
        'newly_completed': newly_completed,
    }


@app.route('/api/auth/me')
def auth_me():
    if 'user_id' not in session:
        decision = _e9_rollout_decision()
        _e9_rollout_telemetry(decision)
        return jsonify({'logged_in': False, 'e9_rollout': decision})
    plan = session.get('plan', 'free')
    uid  = session['user_id']
    display_name = _user_display_label(
        nickname=session.get('nickname', ''),
        username=session.get('username', ''),
    )
    go_rank    = '30k'
    elo_rating = None
    tour_done = 0
    newbie_quest_eligible = False
    needs_onboarding_choice = False
    with get_db() as conn:
        row = conn.execute('SELECT go_rank, tour_done FROM user_stats WHERE user_id=?', (uid,)).fetchone()
        if row:
            go_rank   = row['go_rank'] or '30k'
            tour_done = row['tour_done'] or 0
        row2 = conn.execute(
            'SELECT elo_rating, elo_provisional, email, email_verified, onboarding_path, '
            'is_admin, username, '
            'onboarding_required '
            'FROM users WHERE id=?',
            (uid,)).fetchone()
        email          = None
        email_verified = 0
        elo_provisional = 0
        authoritative_is_admin = False
        authoritative_username = session.get('username', '')
        if row2:
            elo_rating      = row2['elo_rating']
            elo_provisional = row2['elo_provisional'] or 0
            email          = row2['email']
            email_verified = row2['email_verified'] or 0
            authoritative_is_admin = bool(row2['is_admin'])
            authoritative_username = row2['username'] or authoritative_username
            needs_onboarding_choice = (
                bool(row2['onboarding_required'])
                and not bool(row2['onboarding_path'])
                and not bool(session.get('is_admin', False))
            )
            quest_state = conn.execute(
                'SELECT graduated FROM newbie_quest_state WHERE user_id=?', (uid,)
            ).fetchone()
            newbie_quest_eligible = bool(quest_state) and not bool(quest_state['graduated'])
    decision = _e9_rollout_decision(
        user_id=uid, username=authoritative_username, is_admin=authoritative_is_admin
    )
    _e9_rollout_telemetry(decision, uid)
    return jsonify({
        'logged_in':  True,
        'user_id':    uid,
        'username':   session['username'],
        'nickname':   session.get('nickname', ''),
        'display_name': display_name,
        'is_admin':   authoritative_is_admin,
        'plan':       plan,
        'is_premium': plan == 'premium' or authoritative_is_admin,
        'go_rank':    go_rank,
        'elo_rating': elo_rating,
        'elo_provisional': bool(elo_provisional),
        'has_email':  bool(email),
        'email_verified': bool(email_verified),
        'tour_done':  bool(tour_done),
        'needs_onboarding_choice': needs_onboarding_choice,
        'newbie_quest_eligible': newbie_quest_eligible,
        'e9_rollout': decision,
    })

@app.route('/api/auth/tour_done', methods=['POST'])
@login_required
def auth_tour_done():
    """記錄新手教學已看過（存 DB，跨裝置/跨瀏覽器生效）。"""
    with get_db() as conn:
        conn.execute('UPDATE user_stats SET tour_done=1 WHERE user_id=?',
                     (session['user_id'],))
        conn.commit()
    return jsonify({'ok': True})


@app.route('/api/auth/newbie_quest', methods=['GET', 'POST'])
@login_required
def auth_newbie_quest():
    uid = session['user_id']
    data = (request.get_json(silent=True) or {}) if request.method == 'POST' else {}
    action = str(data.get('action') or '').strip()
    task_key = str(data.get('task_key') or '').strip()
    if request.method == 'POST' and action != 'view' and task_key not in _NEWBIE_TASK_KEYS:
        return jsonify({'error': 'invalid_task_key'}), 400
    with get_db() as conn:
        snapshot = _newbie_quest_snapshot(uid, conn, sync_server_tasks=True)
        if request.method == 'POST' and action == 'view' and snapshot['eligible']:
            today = datetime.date.today().isoformat()
            _newbie_log_event(
                conn, uid, f'view:{today}', 'newbie_quest_view', payload={'stage': 1}
            )
        elif request.method == 'POST':
            if task_key not in snapshot['state']['completed']:
                conn.commit()
                return jsonify({'error': 'checkpoint_not_met', **snapshot}), 409
        conn.commit()
    return jsonify({'ok': True, **snapshot})


@app.route('/api/newbie_quest/progress', methods=['POST'])
@login_required
def newbie_quest_progress():
    uid = session['user_id']
    data = request.get_json(silent=True) or {}
    task_key = str(data.get('task') or '').strip()
    if task_key not in {_NEWBIE_TASK_HERO, _NEWBIE_TASK_BOT}:
        return jsonify({'error': 'invalid_task_key'}), 400

    with get_db() as conn:
        snapshot = _newbie_quest_snapshot(uid, conn, sync_server_tasks=True)
        if not snapshot['eligible']:
            conn.commit()
            return jsonify({'error': 'not_eligible', **snapshot}), 403
        if not _newbie_progress_prerequisite(snapshot, task_key):
            conn.commit()
            return jsonify({'error': 'checkpoint_not_met', **snapshot}), 409
        inserted = _newbie_complete_task(
            conn,
            uid,
            task_key,
            'hero_card' if task_key == _NEWBIE_TASK_HERO else 'bot_result'
        )
        snapshot = _newbie_quest_snapshot(uid, conn, sync_server_tasks=False)
        conn.commit()
    return jsonify({
        'ok': True,
        **snapshot,
        'newly_completed': [task_key] if inserted else [],
    })


@app.route('/api/newbie_quest/checkpoint', methods=['POST'])
@login_required
def newbie_quest_checkpoint():
    uid = session['user_id']
    data = request.get_json(silent=True) or {}
    task_key = str(data.get('task_key') or '').strip()
    valid_keys = set(_NEWBIE_STAGE_REWARDS.keys())
    if task_key not in valid_keys:
        return jsonify({'ok': False, 'error': 'invalid_task_key'}), 400

    with get_db() as conn:
        snapshot = _newbie_quest_snapshot(uid, conn, sync_server_tasks=True)
        if not snapshot['eligible']:
            conn.commit()
            return jsonify({'ok': False, 'error': 'not_eligible', **snapshot}), 403
        if not _newbie_progress_prerequisite(snapshot, task_key):
            conn.commit()
            return jsonify({'ok': False, 'error': 'checkpoint_not_met', **snapshot}), 409
        inserted = _newbie_complete_task(
            conn, uid, task_key, _NEWBIE_TASK_SOURCES.get(task_key, 'checkpoint')
        )
        granted_coins = 0
        granted_titles = []
        display_items = []
        if inserted:
            reward = _NEWBIE_STAGE_REWARDS.get(task_key, {})
            if reward.get('coins'):
                granted_coins = _grant_coins(conn, uid, reward['coins'], f'newbie_{task_key}')
            for item_key in reward.get('shop_items', []):
                item_def = SHOP_ITEMS.get(item_key)
                if item_def:
                    _grant_shop_purchase(conn, uid, item_def, 1)
                    display_items.append(_reward_display_item(item_key, 1))
            title_key = reward.get('title')
            if title_key:
                inserted_title = conn.execute(
                    'INSERT OR IGNORE INTO player_wardrobe(user_id,item_id,obtained_at,source) VALUES(?,?,?,?)',
                    (uid, title_key, _now_iso(), 'newbie_quest')
                ).rowcount
                if inserted_title:
                    granted_titles.append(title_key)
        snapshot = _newbie_quest_snapshot(uid, conn, sync_server_tasks=False)
        conn.commit()
    rewards_payload = {}
    if granted_coins or display_items or granted_titles:
        rewards_payload = {
            'coins': granted_coins,
            'items': display_items,
            'titles': granted_titles,
        }
    return jsonify({
        'ok': True,
        **snapshot,
        'newly_completed': [task_key] if inserted else [],
        'rewards': rewards_payload,
    })


@app.route('/api/user/onboarding_choice', methods=['POST'])
@login_required
def onboarding_choice():
    uid = session['user_id']
    path = str((request.get_json(silent=True) or {}).get('path') or '').strip()
    if path not in ('newbie', 'test'):
        return jsonify({'error': 'invalid_onboarding_path'}), 400
    with get_db() as conn:
        row = conn.execute(
            'SELECT onboarding_path FROM users WHERE id=?', (uid,)
        ).fetchone()
        current = row['onboarding_path'] if row else None
        if current and current != path:
            return jsonify({
                'error': 'onboarding_path_locked',
                'onboarding_path': current,
            }), 409
        created = not current
        if created:
            changed = conn.execute(
                'UPDATE users SET onboarding_path=?, onboarding_required=0 '
                'WHERE id=? AND onboarding_path IS NULL',
                (path, uid)
            ).rowcount
            final = conn.execute(
                'SELECT onboarding_path FROM users WHERE id=?', (uid,)
            ).fetchone()
            final_path = final['onboarding_path'] if final else None
            if not changed and final_path != path:
                conn.rollback()
                return jsonify({
                    'error': 'onboarding_path_locked',
                    'onboarding_path': final_path,
                }), 409
            if final_path in ('newbie', 'test'):
                now = datetime.datetime.now().isoformat()
                conn.execute(
                    'INSERT OR IGNORE INTO newbie_quest_state '
                    '(user_id,stage,graduated,created_at,updated_at) VALUES(?,1,0,?,?)',
                    (uid, now, now)
                )
        else:
            conn.execute('UPDATE users SET onboarding_required=0 WHERE id=?', (uid,))
            now = datetime.datetime.now().isoformat()
            conn.execute(
                'INSERT OR IGNORE INTO newbie_quest_state '
                '(user_id,stage,graduated,created_at,updated_at) VALUES(?,1,0,?,?)',
                (uid, now, now)
            )
        conn.commit()
    return jsonify({'ok': True, 'onboarding_path': path, 'created': created})

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
    """新手自填段位 →「暫定棋力」（elo_provisional=1，僅在尚未有 elo_rating 時寫入）。

    防濫用設計：自填值只決定練習起點，不直接享有正式棋力的特權——
      - 裝備段位解鎖用的 go_rank 上限 1k（段位裝備須通過正式鑑定才開）
      - 冒險地圖解鎖上限到中段區（Elo 1570 = 1~5k 區）
      - 個人頁顯示「未驗證」標記
    完成正式且收斂的棋力鑑定後轉正；快速定位維持暫定。"""
    data = request.get_json() or {}
    elo  = float(data.get('elo', 1100))
    elo  = max(1100.0, min(2500.0, elo))
    uid  = session['user_id']
    go_rank = _rating_to_rank(elo).replace('+', '')  # '7d+' → '7d'，符合 DIFFICULTY_ORDER 格式
    # 暫定棋力的 go_rank 上限 1k：段位裝備 tier 不靠自填解鎖
    _capped_rank = go_rank
    if go_rank.endswith('d'):
        _capped_rank = '1k'
    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat()
    with get_db() as conn:
        updated = conn.execute(
            'UPDATE users SET elo_rating=?, elo_updated_at=?, elo_provisional=1 '
            'WHERE id=? AND elo_rating IS NULL',
            (elo, now, uid)
        )
        if updated.rowcount != 1:
            return jsonify({'error': 'placement_already_set'}), 409
        # 同步更新 user_stats.go_rank，讓左側角色欄顯示正確棋力（裝備 tier 上限 1k）
        conn.execute(
            'INSERT INTO user_stats(user_id, go_rank, go_rank_initialized) VALUES(?,?,1)'
            ' ON CONFLICT(user_id) DO UPDATE SET go_rank=?, go_rank_initialized=1',
            (uid, _capped_rank, _capped_rank)
        )
        conn.execute(
            'DELETE FROM daily_training_queue WHERE user_id=? AND date=?',
            (uid, datetime.date.today().isoformat())
        )
        conn.commit()
    # 冒險解鎖上限：自填最多開到中段（1~5k 區），高段區須通過鑑定
    start_zone_key = _apply_placement_adventure_unlock(uid, min(elo, 1570.0), 'placement_self')
    return jsonify({'ok': True, 'elo_rating': elo, 'provisional': True,
                    'start_zone_key': start_zone_key, 'go_rank': _capped_rank})


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
        # 注意：PostgreSQL 不允許 GROUP BY u.id 後 SELECT 未分組的 s.* 欄位
        # （SQLite 容忍），徽章數改用子查詢
        rows = conn.execute(
            '''SELECT u.id, u.username, u.nickname, u.email, u.email_verified,
                      u.is_admin, u.plan, u.premium_until, u.created_at, u.last_login,
                      u.admin_note,
                      COALESCE(s.total_correct,0) as total_correct,
                      COALESCE(s.max_streak,0)    as max_streak,
                      COALESCE(b.cnt,0)           as badge_count
               FROM users u
               LEFT JOIN user_stats s ON s.user_id=u.id
               LEFT JOIN (SELECT user_id, COUNT(DISTINCT badge_id) AS cnt
                          FROM badges_earned GROUP BY user_id) b ON b.user_id=u.id
               ORDER BY u.created_at''').fetchall()
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
    except psycopg2.IntegrityError:
        return jsonify({'error': f'帳號「{username}」已存在'}), 409
    return jsonify({'ok': True})

@app.route('/api/admin/users/<int:uid>', methods=['DELETE'])
@admin_required
def admin_delete_user(uid):
    if uid == session['user_id']:
        return jsonify({'error': '不能刪除自己'}), 400
    with get_db() as conn:
        conn.execute('DELETE FROM friendships    WHERE from_user=? OR to_user=?', (uid, uid))
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

@app.route('/api/admin/users/<int:uid>/note', methods=['POST'])
@admin_required
def admin_set_user_note(uid):
    data = request.get_json(silent=True) or {}
    note = (data.get('note') or '').strip()
    with get_db() as conn:
        row = conn.execute('SELECT id FROM users WHERE id=?', (uid,)).fetchone()
        if not row: return jsonify({'error': '找不到用戶'}), 404
        conn.execute('UPDATE users SET admin_note=? WHERE id=?', (note, uid))
        conn.commit()
    return jsonify({'ok': True})

@app.route('/api/admin/users/<int:uid>/set-plan', methods=['POST'])
@admin_required
def admin_set_plan(uid):
    data = request.get_json(silent=True) or {}
    plan = data.get('plan', 'free')
    if plan not in ('free', 'premium'):
        return jsonify({'error': '方案只能是 free 或 premium'}), 400
    premium_until = None
    if plan == 'premium':
        if data.get('permanent'):
            premium_until = None
        elif data.get('premium_until'):
            try:
                raw_until = str(data.get('premium_until')).strip()
                if re.fullmatch(r'\d{4}-\d{2}-\d{2}', raw_until):
                    premium_until = datetime.datetime.fromisoformat(raw_until + 'T23:59:59').isoformat(timespec='seconds')
                else:
                    premium_until = datetime.datetime.fromisoformat(raw_until).isoformat(timespec='seconds')
            except Exception:
                return jsonify({'error': 'premium_until 格式錯誤，請用 YYYY-MM-DD'}), 400
        elif data.get('days') not in (None, ''):
            try:
                days = int(data.get('days'))
            except Exception:
                return jsonify({'error': 'days 必須是數字'}), 400
            if days > 0:
                premium_until = (datetime.datetime.now() + datetime.timedelta(days=days)).isoformat(timespec='seconds')
            else:
                premium_until = None
    with get_db() as conn:
        row = conn.execute('SELECT id FROM users WHERE id=?', (uid,)).fetchone()
        if not row:
            return jsonify({'error': '找不到用戶'}), 404
        if plan == 'premium':
            conn.execute("UPDATE users SET plan='premium', premium_until=? WHERE id=?", (premium_until, uid))
        else:
            conn.execute("UPDATE users SET plan='free', premium_until=NULL WHERE id=?", (uid,))
        if plan == 'premium':
            grant_premium_rewards(uid, conn)
        conn.commit()
    return jsonify({'ok': True, 'plan': plan, 'premium_until': premium_until})

# ── Admin：遊戲資產管理（金幣/道具/裝備/外觀/寵物/Elo/XP）────────────────
def _admin_audit(action, uid, detail):
    app.logger.info(f'[admin_assets] {session.get("username")} → user={uid} {action}: {detail}')

@app.route('/api/admin/users/<int:uid>/assets')
@admin_required
def admin_user_assets(uid):
    """彙總單一帳號的全部遊戲資產 + 可發放目錄（給前端下拉用）。"""
    with get_db() as conn:
        u = conn.execute(
            'SELECT id, username, nickname, elo_rating, elo_provisional FROM users WHERE id=?',
            (uid,)).fetchone()
        if not u:
            return jsonify({'error': 'not_found'}), 404
        s = conn.execute('SELECT coins, xp, go_rank, rank_level FROM user_stats WHERE user_id=?',
                         (uid,)).fetchone()
        shop_inv = conn.execute(
            'SELECT item_key, qty FROM shop_inventory WHERE user_id=? AND qty>0', (uid,)).fetchall()
        pet_inv = conn.execute(
            'SELECT item_key, qty FROM pet_inventory WHERE user_id=? AND qty>0', (uid,)).fetchall()
        equips = conn.execute(
            'SELECT id, equip_id, equipped, source FROM player_inventory WHERE user_id=? ORDER BY id DESC',
            (uid,)).fetchall()
        wardrobe = conn.execute(
            'SELECT id, item_id, source FROM player_wardrobe WHERE user_id=? ORDER BY id DESC',
            (uid,)).fetchall()
        pet = conn.execute('SELECT * FROM user_pets WHERE user_id=?', (uid,)).fetchone()

    eq_map = {e['id']: e for e in EQUIPMENT_DEFS}
    ap_map = {a['id']: a for a in APPEARANCE_DEFS}
    return jsonify({
        'user': {'id': u['id'], 'username': u['username'], 'nickname': u['nickname'],
                 'elo_rating': u['elo_rating'], 'elo_provisional': bool(u['elo_provisional'] or 0)},
        'stats': {'coins': (s['coins'] if s else 0) or 0, 'xp': (s['xp'] if s else 0) or 0,
                  'go_rank': (s['go_rank'] if s else '30k') or '30k',
                  'rank_level': (s['rank_level'] if s else 'LV1') or 'LV1'},
        'shop_items': [{'item_key': r['item_key'], 'qty': r['qty'],
                        'name': SHOP_ITEMS.get(r['item_key'], {}).get('name', r['item_key'])}
                       for r in shop_inv],
        'pet_food': [{'item_key': r['item_key'], 'qty': r['qty'],
                      'name': PET_FOOD_CATALOG.get(r['item_key'], {}).get('name', r['item_key'])}
                     for r in pet_inv],
        'equipment': [{'inv_id': e['id'], 'equip_id': e['equip_id'], 'equipped': e['equipped'],
                       'name': eq_map.get(e['equip_id'], {}).get('name', e['equip_id']),
                       'slot': eq_map.get(e['equip_id'], {}).get('slot', '')}
                      for e in equips],
        'wardrobe': [{'inv_id': w['id'], 'item_id': w['item_id'],
                      'name': ap_map.get(w['item_id'], {}).get('name', w['item_id']),
                      'rarity': ap_map.get(w['item_id'], {}).get('rarity', '')}
                     for w in wardrobe],
        'pet': dict(pet) if pet else None,
        'catalogs': {
            'shop_items': [{'key': k, 'name': v['name']} for k, v in SHOP_ITEMS.items()],
            'pet_food':   [{'key': k, 'name': v['name']} for k, v in PET_FOOD_CATALOG.items()],
            'equipment':  [{'key': e['id'], 'name': e['name'], 'slot': e['slot'],
                            'rarity': e.get('rarity', '')} for e in EQUIPMENT_DEFS],
            'appearance': [{'key': a['id'], 'name': a['name'], 'slot': a.get('slot', ''),
                            'rarity': a.get('rarity', '')} for a in APPEARANCE_DEFS],
            'pets':       [{'key': k, 'name': v['name']} for k, v in PET_CATALOG.items()],
        },
    })

def _parse_admin_date(raw, fallback):
    raw = str(raw or '').strip()
    if not raw:
        return fallback
    try:
        return datetime.date.fromisoformat(raw[:10])
    except Exception:
        return fallback


def _admin_retention_event_union_sql():
    return """
        SELECT user_id,
               CAST(NULLIF(CAST(reviewed_at AS TEXT), '') AS timestamp) AS occurred_at,
               'review' AS event_type
          FROM review_log
         WHERE reviewed_at IS NOT NULL AND NULLIF(CAST(reviewed_at AS TEXT), '') IS NOT NULL
        UNION ALL
        SELECT user_id,
               CAST(NULLIF(CAST(played_at AS TEXT), '') AS timestamp) AS occurred_at,
               'game_result' AS event_type
          FROM game_results
         WHERE played_at IS NOT NULL AND NULLIF(CAST(played_at AS TEXT), '') IS NOT NULL
        UNION ALL
        SELECT user_id,
               CAST(NULLIF(CAST(played_at AS TEXT), '') AS timestamp) AS occurred_at,
               'game_record' AS event_type
          FROM game_records
         WHERE played_at IS NOT NULL AND NULLIF(CAST(played_at AS TEXT), '') IS NOT NULL
        UNION ALL
        SELECT user_id,
               CAST(NULLIF(CAST(submitted_at AS TEXT), '') AS timestamp) AS occurred_at,
               'daily_challenge' AS event_type
          FROM daily_challenge_log
         WHERE submitted_at IS NOT NULL AND NULLIF(CAST(submitted_at AS TEXT), '') IS NOT NULL
        UNION ALL
        SELECT user_id,
               CAST(NULLIF(CAST(started_at AS TEXT), '') AS timestamp) AS occurred_at,
               'rating_test_started' AS event_type
          FROM rating_test_sessions
         WHERE started_at IS NOT NULL AND NULLIF(CAST(started_at AS TEXT), '') IS NOT NULL
        UNION ALL
        SELECT user_id,
               CAST(NULLIF(CAST(finished_at AS TEXT), '') AS timestamp) AS occurred_at,
               'rating_test_completed' AS event_type
          FROM rating_test_sessions
         WHERE finished_at IS NOT NULL AND NULLIF(CAST(finished_at AS TEXT), '') IS NOT NULL
        UNION ALL
        SELECT user_id,
               CAST(NULLIF(CAST(updated_at AS TEXT), '') AS timestamp) AS occurred_at,
               'newbie_quest' AS event_type
          FROM newbie_quest_state
         WHERE updated_at IS NOT NULL AND NULLIF(CAST(updated_at AS TEXT), '') IS NOT NULL
    """


def _admin_retention_report(start_date, end_date):
    activity_end = end_date + datetime.timedelta(days=30)
    start_iso = start_date.isoformat()
    end_iso = end_date.isoformat()
    activity_end_iso = activity_end.isoformat()
    event_union_sql = _admin_retention_event_union_sql()

    summary_sql = f"""
        WITH activity_events AS (
            {event_union_sql}
        ),
        activity_days AS (
            SELECT user_id, DATE(occurred_at) AS activity_date
              FROM activity_events
             WHERE DATE(occurred_at) BETWEEN ? AND ?
             GROUP BY user_id, DATE(occurred_at)
        ),
        signup AS (
            SELECT u.id,
                   CAST(NULLIF(CAST(u.created_at AS TEXT), '') AS timestamp) AS created_at,
                   CAST(NULLIF(CAST(u.created_at AS TEXT), '') AS date) AS cohort_date,
                   COALESCE(u.email_verified, 0) <> 0 AS email_verified,
                   COALESCE(ns.graduated, 0) <> 0 AS graduated
              FROM users u
         LEFT JOIN newbie_quest_state ns ON ns.user_id = u.id
             WHERE CAST(NULLIF(CAST(u.created_at AS TEXT), '') AS date) BETWEEN ? AND ?
        ),
        base AS (
            SELECT s.*,
                   EXISTS(
                       SELECT 1
                         FROM activity_events ae
                        WHERE ae.user_id = s.id
                          AND ae.occurred_at >= s.created_at
                          AND ae.occurred_at < (s.created_at + INTERVAL '1 day')
                   ) AS activated_24h,
                   EXISTS(
                       SELECT 1
                         FROM activity_days ad
                        WHERE ad.user_id = s.id
                          AND ad.activity_date = (DATE(s.created_at) + 1)
                   ) AS d1_retained,
                   EXISTS(
                       SELECT 1
                         FROM activity_days ad
                        WHERE ad.user_id = s.id
                          AND ad.activity_date = (DATE(s.created_at) + 7)
                   ) AS d7_retained,
                   EXISTS(
                       SELECT 1
                         FROM activity_days ad
                        WHERE ad.user_id = s.id
                          AND ad.activity_date = (DATE(s.created_at) + 30)
                   ) AS d30_retained,
                   (SELECT COUNT(*)
                      FROM activity_days ad
                     WHERE ad.user_id = s.id
                       AND ad.activity_date BETWEEN DATE(s.created_at) AND (DATE(s.created_at) + 6)
                   ) AS active_days_7,
                   (SELECT COUNT(*)
                      FROM activity_days ad
                     WHERE ad.user_id = s.id
                       AND ad.activity_date BETWEEN DATE(s.created_at) AND (DATE(s.created_at) + 29)
                   ) AS active_days_30
              FROM signup s
        )
        SELECT
            COUNT(*) AS signup_users,
            SUM(CASE WHEN activated_24h THEN 1 ELSE 0 END) AS activated_24h,
            SUM(CASE WHEN d1_retained THEN 1 ELSE 0 END) AS d1_retained,
            SUM(CASE WHEN d7_retained THEN 1 ELSE 0 END) AS d7_retained,
            SUM(CASE WHEN d30_retained THEN 1 ELSE 0 END) AS d30_retained,
            SUM(CASE WHEN email_verified THEN 1 ELSE 0 END) AS email_verified_users,
            SUM(CASE WHEN graduated THEN 1 ELSE 0 END) AS graduated_users,
            AVG(active_days_7) AS avg_active_days_7,
            AVG(active_days_30) AS avg_active_days_30
          FROM base
    """

    cohort_sql = f"""
        WITH activity_events AS (
            {event_union_sql}
        ),
        activity_days AS (
            SELECT user_id, DATE(occurred_at) AS activity_date
              FROM activity_events
             WHERE DATE(occurred_at) BETWEEN ? AND ?
             GROUP BY user_id, DATE(occurred_at)
        ),
        signup AS (
            SELECT u.id,
                   CAST(NULLIF(CAST(u.created_at AS TEXT), '') AS timestamp) AS created_at,
                   CAST(NULLIF(CAST(u.created_at AS TEXT), '') AS date) AS cohort_date,
                   COALESCE(u.email_verified, 0) <> 0 AS email_verified,
                   COALESCE(ns.graduated, 0) <> 0 AS graduated
              FROM users u
         LEFT JOIN newbie_quest_state ns ON ns.user_id = u.id
             WHERE CAST(NULLIF(CAST(u.created_at AS TEXT), '') AS date) BETWEEN ? AND ?
        ),
        base AS (
            SELECT s.*,
                   EXISTS(
                       SELECT 1
                         FROM activity_events ae
                        WHERE ae.user_id = s.id
                          AND ae.occurred_at >= s.created_at
                          AND ae.occurred_at < (s.created_at + INTERVAL '1 day')
                   ) AS activated_24h,
                   EXISTS(
                       SELECT 1
                         FROM activity_days ad
                        WHERE ad.user_id = s.id
                          AND ad.activity_date = (DATE(s.created_at) + 1)
                   ) AS d1_retained,
                   EXISTS(
                       SELECT 1
                         FROM activity_days ad
                        WHERE ad.user_id = s.id
                          AND ad.activity_date = (DATE(s.created_at) + 7)
                   ) AS d7_retained,
                   EXISTS(
                       SELECT 1
                         FROM activity_days ad
                        WHERE ad.user_id = s.id
                          AND ad.activity_date = (DATE(s.created_at) + 30)
                   ) AS d30_retained,
                   (SELECT COUNT(*)
                      FROM activity_days ad
                     WHERE ad.user_id = s.id
                       AND ad.activity_date BETWEEN DATE(s.created_at) AND (DATE(s.created_at) + 6)
                   ) AS active_days_7,
                   (SELECT COUNT(*)
                      FROM activity_days ad
                     WHERE ad.user_id = s.id
                       AND ad.activity_date BETWEEN DATE(s.created_at) AND (DATE(s.created_at) + 29)
                   ) AS active_days_30
              FROM signup s
        )
        SELECT cohort_date,
               COUNT(*) AS signup_users,
               SUM(CASE WHEN activated_24h THEN 1 ELSE 0 END) AS activated_24h,
               SUM(CASE WHEN d1_retained THEN 1 ELSE 0 END) AS d1_retained,
               SUM(CASE WHEN d7_retained THEN 1 ELSE 0 END) AS d7_retained,
               SUM(CASE WHEN d30_retained THEN 1 ELSE 0 END) AS d30_retained,
               SUM(CASE WHEN email_verified THEN 1 ELSE 0 END) AS email_verified_users,
               SUM(CASE WHEN graduated THEN 1 ELSE 0 END) AS graduated_users,
               AVG(active_days_7) AS avg_active_days_7,
               AVG(active_days_30) AS avg_active_days_30
          FROM base
      GROUP BY cohort_date
      ORDER BY cohort_date
    """

    with get_db() as conn:
        summary_row = conn.execute(summary_sql, (
            start_iso, activity_end_iso, start_iso, end_iso
        )).fetchone()
        cohort_rows = conn.execute(cohort_sql, (
            start_iso, activity_end_iso, start_iso, end_iso
        )).fetchall()
        detail_sql = f"""
            WITH activity_events AS (
                {event_union_sql}
            ),
            activity_days AS (
                SELECT user_id, DATE(occurred_at) AS activity_date
                  FROM activity_events
                 WHERE DATE(occurred_at) BETWEEN ? AND ?
                 GROUP BY user_id, DATE(occurred_at)
            ),
            signup AS (
                SELECT u.id,
                       u.username,
                       CAST(NULLIF(CAST(u.created_at AS TEXT), '') AS timestamp) AS created_at,
                       CAST(NULLIF(CAST(u.created_at AS TEXT), '') AS date) AS cohort_date,
                       COALESCE(u.email_verified, 0) <> 0 AS email_verified,
                       COALESCE(ns.graduated, 0) <> 0 AS graduated
                  FROM users u
             LEFT JOIN newbie_quest_state ns ON ns.user_id = u.id
                 WHERE CAST(NULLIF(CAST(u.created_at AS TEXT), '') AS date) BETWEEN ? AND ?
            ),
            base AS (
                SELECT s.*,
                       EXISTS(
                           SELECT 1
                             FROM activity_events ae
                            WHERE ae.user_id = s.id
                              AND ae.occurred_at >= s.created_at
                              AND ae.occurred_at < (s.created_at + INTERVAL '1 day')
                       ) AS activated_24h,
                       EXISTS(
                           SELECT 1
                             FROM activity_days ad
                            WHERE ad.user_id = s.id
                              AND ad.activity_date = (DATE(s.created_at) + 1)
                       ) AS d1_retained,
                       EXISTS(
                           SELECT 1
                             FROM activity_days ad
                            WHERE ad.user_id = s.id
                              AND ad.activity_date = (DATE(s.created_at) + 7)
                       ) AS d7_retained,
                       EXISTS(
                           SELECT 1
                             FROM activity_days ad
                            WHERE ad.user_id = s.id
                              AND ad.activity_date = (DATE(s.created_at) + 30)
                       ) AS d30_retained,
                       (SELECT COUNT(*)
                          FROM activity_days ad
                         WHERE ad.user_id = s.id
                           AND ad.activity_date BETWEEN DATE(s.created_at) AND (DATE(s.created_at) + 6)
                       ) AS active_days_7,
                       (SELECT COUNT(*)
                          FROM activity_days ad
                         WHERE ad.user_id = s.id
                           AND ad.activity_date BETWEEN DATE(s.created_at) AND (DATE(s.created_at) + 29)
                       ) AS active_days_30
                  FROM signup s
            )
            SELECT id, username, cohort_date, created_at, activated_24h, d1_retained, d7_retained,
                   d30_retained, active_days_7, active_days_30, email_verified, graduated
              FROM base
        """
        detail_rows = conn.execute(detail_sql, (
            start_iso, activity_end_iso, start_iso, end_iso
        )).fetchall()

    def _pct(part, total):
        return round((float(part or 0) / float(total or 1)) * 100, 1) if total else 0.0

    summary = dict(summary_row) if summary_row else {}
    signup_users = int(summary.get('signup_users') or 0)
    payload_summary = {
        'signup_users': signup_users,
        'activated_24h': int(summary.get('activated_24h') or 0),
        'd1_retained': int(summary.get('d1_retained') or 0),
        'd7_retained': int(summary.get('d7_retained') or 0),
        'd30_retained': int(summary.get('d30_retained') or 0),
        'email_verified_users': int(summary.get('email_verified_users') or 0),
        'graduated_users': int(summary.get('graduated_users') or 0),
        'activation_rate_24h': _pct(summary.get('activated_24h'), signup_users),
        'd1_rate': _pct(summary.get('d1_retained'), signup_users),
        'd7_rate': _pct(summary.get('d7_retained'), signup_users),
        'd30_rate': _pct(summary.get('d30_retained'), signup_users),
        'email_verified_rate': _pct(summary.get('email_verified_users'), signup_users),
        'graduated_rate': _pct(summary.get('graduated_users'), signup_users),
        'avg_active_days_7': round(float(summary.get('avg_active_days_7') or 0), 2),
        'avg_active_days_30': round(float(summary.get('avg_active_days_30') or 0), 2),
    }

    cohorts = []
    for row in cohort_rows:
        cohort_users = int(row['signup_users'] or 0)
        cohorts.append({
            'cohort_date': row['cohort_date'],
            'signup_users': cohort_users,
            'activated_24h': int(row['activated_24h'] or 0),
            'd1_retained': int(row['d1_retained'] or 0),
            'd7_retained': int(row['d7_retained'] or 0),
            'd30_retained': int(row['d30_retained'] or 0),
            'email_verified_users': int(row['email_verified_users'] or 0),
            'graduated_users': int(row['graduated_users'] or 0),
            'activation_rate_24h': _pct(row['activated_24h'], cohort_users),
            'd1_rate': _pct(row['d1_retained'], cohort_users),
            'd7_rate': _pct(row['d7_retained'], cohort_users),
            'd30_rate': _pct(row['d30_retained'], cohort_users),
            'email_verified_rate': _pct(row['email_verified_users'], cohort_users),
            'graduated_rate': _pct(row['graduated_users'], cohort_users),
            'avg_active_days_7': round(float(row['avg_active_days_7'] or 0), 2),
            'avg_active_days_30': round(float(row['avg_active_days_30'] or 0), 2),
        })

    segments = {
        'never_activated': 0,
        'single_day': 0,
        'first_week_regular': 0,
        'sustained_30d': 0,
        'power_user': 0,
    }
    at_risk_users = []
    for row in detail_rows:
        active_days_7 = int(row['active_days_7'] or 0)
        active_days_30 = int(row['active_days_30'] or 0)
        activated = bool(row['activated_24h'])
        d7 = bool(row['d7_retained'])
        d30 = bool(row['d30_retained'])
        if not activated:
            segments['never_activated'] += 1
            at_risk_users.append({
                'username': row['username'],
                'cohort_date': row['cohort_date'],
                'segment': 'never_activated',
            })
        elif active_days_7 <= 1 and not d7:
            segments['single_day'] += 1
            at_risk_users.append({
                'username': row['username'],
                'cohort_date': row['cohort_date'],
                'segment': 'single_day',
            })
        elif active_days_7 >= 3 and not d30:
            segments['first_week_regular'] += 1
        elif d30:
            segments['sustained_30d'] += 1
        if active_days_30 >= 10:
            segments['power_user'] += 1

    at_risk_users = at_risk_users[:20]

    return {
        'range': {
            'start_date': start_iso,
            'end_date': end_iso,
            'activity_end_date': activity_end_iso,
        },
        'summary': payload_summary,
        'cohorts': cohorts,
        'segments': segments,
        'at_risk_users': at_risk_users,
    }


def _admin_northstar_metrics():
    event_union_sql = _admin_retention_event_union_sql()
    premium_now_iso = datetime.datetime.now().isoformat(timespec='seconds')
    computed_at = datetime.datetime.now(datetime.timezone.utc).replace(
        microsecond=0).isoformat().replace('+00:00', 'Z')

    metrics_sql = f"""
        WITH activity_events AS (
            {event_union_sql}
        ),
        activity_days AS (
            SELECT user_id, DATE(occurred_at) AS activity_date
              FROM activity_events
             WHERE DATE(occurred_at) BETWEEN (CURRENT_DATE - INTERVAL '34 day') AND CURRENT_DATE
             GROUP BY user_id, DATE(occurred_at)
        ),
        premium_state AS (
            SELECT u.id,
                   CAST(NULLIF(CAST(u.created_at AS TEXT), '') AS date) AS created_date,
                   NULLIF(CAST(u.premium_until AS TEXT), '') AS premium_until_text,
                   CAST(NULLIF(CAST(u.premium_until AS TEXT), '') AS timestamp) AS premium_until_ts,
                   CASE
                       WHEN u.plan = 'premium'
                            AND (
                                NULLIF(CAST(u.premium_until AS TEXT), '') IS NULL
                                OR NULLIF(CAST(u.premium_until AS TEXT), '') >= ?
                            )
                       THEN TRUE
                       ELSE FALSE
                   END AS is_premium_now
              FROM users u
        ),
        current_window AS (
            SELECT DISTINCT user_id
              FROM activity_days
             WHERE activity_date BETWEEN (CURRENT_DATE - INTERVAL '6 day') AND CURRENT_DATE
        ),
        previous_window AS (
            SELECT DISTINCT user_id
              FROM activity_days
             WHERE activity_date BETWEEN (CURRENT_DATE - INTERVAL '13 day') AND (CURRENT_DATE - INTERVAL '7 day')
        ),
        baseline_window AS (
            SELECT DISTINCT user_id
              FROM activity_days
             WHERE activity_date BETWEEN (CURRENT_DATE - INTERVAL '34 day') AND (CURRENT_DATE - INTERVAL '28 day')
        ),
        first_paid_orders AS (
            SELECT po.user_id,
                   MIN(CAST(NULLIF(CAST(po.paid_at AS TEXT), '') AS timestamp)) AS first_paid_at
              FROM payment_orders po
             WHERE po.status = 'paid'
               AND NULLIF(CAST(po.paid_at AS TEXT), '') IS NOT NULL
             GROUP BY po.user_id
        )
        SELECT
            (SELECT COUNT(*) FROM users) AS total_users,
            (SELECT COUNT(*)
               FROM premium_state
              WHERE created_date BETWEEN (CURRENT_DATE - INTERVAL '6 day') AND CURRENT_DATE) AS new_users_7d,
            (SELECT COUNT(*) FROM current_window) AS wau,
            (SELECT COUNT(*) FROM previous_window) AS wau_prev,
            (SELECT COUNT(*) FROM premium_state WHERE is_premium_now) AS premium_count,
            (SELECT COUNT(*)
               FROM first_paid_orders
              WHERE DATE(first_paid_at) BETWEEN (CURRENT_DATE - INTERVAL '6 day') AND CURRENT_DATE) AS new_premium_7d,
            (SELECT COUNT(*)
               FROM premium_state
              WHERE premium_until_ts IS NOT NULL
                AND DATE(premium_until_ts) BETWEEN (CURRENT_DATE - INTERVAL '29 day') AND CURRENT_DATE
                AND NOT is_premium_now) AS expired_premium_30d,
            (SELECT COUNT(*) FROM baseline_window) AS retention_4w_all_base,
            (SELECT COUNT(*)
               FROM baseline_window bw
               JOIN current_window cw ON cw.user_id = bw.user_id) AS retention_4w_all_kept,
            (SELECT COUNT(*)
               FROM baseline_window bw
               JOIN premium_state ps ON ps.id = bw.user_id
              WHERE ps.is_premium_now) AS retention_4w_premium_base,
            (SELECT COUNT(*)
               FROM baseline_window bw
               JOIN current_window cw ON cw.user_id = bw.user_id
               JOIN premium_state ps ON ps.id = bw.user_id
              WHERE ps.is_premium_now) AS retention_4w_premium_kept
    """

    with get_db() as conn:
        row = conn.execute(metrics_sql, (premium_now_iso,)).fetchone()

    def _to_int(value):
        return int(value or 0)

    def _pct_or_none(part, total):
        if not total:
            return None
        return round((float(part or 0) / float(total)) * 100, 1)

    payload = dict(row) if row else {}
    premium_count = _to_int(payload.get('premium_count'))
    expired_premium_30d = _to_int(payload.get('expired_premium_30d'))
    retention_4w_all_base = _to_int(payload.get('retention_4w_all_base'))
    retention_4w_premium_base = _to_int(payload.get('retention_4w_premium_base'))
    churn_pool = premium_count + expired_premium_30d

    notes = {}
    retention_4w_all = _pct_or_none(payload.get('retention_4w_all_kept'),
                                    retention_4w_all_base)
    if retention_4w_all is None:
        notes['retention_4w_all'] = 'No users were active in the baseline 7-day window 28 days ago.'

    retention_4w_premium = _pct_or_none(payload.get('retention_4w_premium_kept'),
                                        retention_4w_premium_base)
    if retention_4w_premium is None:
        notes['retention_4w_premium'] = 'No current premium users were active in the baseline 7-day window 28 days ago.'

    churn_30d = _pct_or_none(expired_premium_30d, churn_pool)
    if churn_30d is None:
        notes['churn_30d'] = 'No current or recently expired premium users were available for the 30-day churn pool.'

    return {
        'computed_at': computed_at,
        'total_users': _to_int(payload.get('total_users')),
        'new_users_7d': _to_int(payload.get('new_users_7d')),
        'wau': _to_int(payload.get('wau')),
        'wau_prev': _to_int(payload.get('wau_prev')),
        'premium_count': premium_count,
        'new_premium_7d': _to_int(payload.get('new_premium_7d')),
        'churn_30d': churn_30d,
        'retention_4w_all': retention_4w_all,
        'retention_4w_premium': retention_4w_premium,
        'notes': notes,
    }


@app.route('/api/admin/retention')
@admin_required
def admin_retention():
    today = datetime.date.today()
    end_date = _parse_admin_date(request.args.get('end_date'), today)
    days = request.args.get('days')
    try:
        days = int(days) if days not in (None, '') else 90
    except Exception:
        days = 90
    days = max(7, min(365, days))
    start_default = end_date - datetime.timedelta(days=days - 1)
    start_date = _parse_admin_date(request.args.get('start_date'), start_default)
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    return jsonify(_admin_retention_report(start_date, end_date))


@app.route('/api/admin/metrics/northstar')
@admin_required
def admin_northstar_metrics():
    return jsonify(_admin_northstar_metrics())


@app.route('/api/admin/users/<int:uid>/assets/coins', methods=['POST'])
@admin_required
def admin_set_coins(uid):
    body = request.get_json(silent=True) or {}
    with get_db() as conn:
        conn.execute('INSERT OR IGNORE INTO user_stats(user_id) VALUES(?)', (uid,))
        if 'set' in body:
            target = max(0, int(body['set']))
            cur = _coin_balance(conn, uid)
            delta = target - cur
        else:
            delta = int(body.get('delta') or 0)
        if delta:
            conn.execute('UPDATE user_stats SET coins=GREATEST(0, COALESCE(coins,0)+?) WHERE user_id=?',
                         (delta, uid))
            bal = _coin_balance(conn, uid)
            conn.execute('INSERT INTO currency_log(user_id,delta,balance_after,reason,created_at) '
                         'VALUES(?,?,?,?,?)',
                         (uid, delta, bal, f'admin:{session.get("username")}', _now_iso()))
        conn.commit()
        bal = _coin_balance(conn, uid)
    _admin_audit('coins', uid, f'delta={delta} → {bal}')
    return jsonify({'ok': True, 'coins': bal})

@app.route('/api/admin/users/<int:uid>/assets/item', methods=['POST'])
@admin_required
def admin_set_item(uid):
    body = request.get_json(silent=True) or {}
    item_key = str(body.get('item_key') or '')
    delta    = int(body.get('delta') or 0)
    kind     = str(body.get('kind') or 'shop')   # 'shop' | 'pet_food'
    if kind == 'shop' and item_key not in SHOP_ITEMS:
        return jsonify({'error': 'unknown_item'}), 400
    if kind == 'pet_food' and item_key not in PET_FOOD_CATALOG:
        return jsonify({'error': 'unknown_food'}), 400
    table = 'shop_inventory' if kind == 'shop' else 'pet_inventory'
    with get_db() as conn:
        conn.execute(
            f'INSERT INTO {table}(user_id,item_key,qty) VALUES(?,?,?) '
            f'ON CONFLICT(user_id,item_key) DO UPDATE SET qty=GREATEST(0, {table}.qty+?)',
            (uid, item_key, max(0, delta), delta))
        conn.commit()
        row = conn.execute(f'SELECT qty FROM {table} WHERE user_id=? AND item_key=?',
                           (uid, item_key)).fetchone()
    _admin_audit('item', uid, f'{kind}:{item_key} delta={delta}')
    return jsonify({'ok': True, 'item_key': item_key, 'qty': (row['qty'] if row else 0)})

@app.route('/api/admin/users/<int:uid>/assets/equipment', methods=['POST'])
@admin_required
def admin_set_equipment(uid):
    body = request.get_json(silent=True) or {}
    action = str(body.get('action') or '')
    if action == 'grant':
        equip_id = str(body.get('equip_id') or '')
        if not any(e['id'] == equip_id for e in EQUIPMENT_DEFS):
            return jsonify({'error': 'unknown_equip'}), 400
        with get_db() as conn:
            conn.execute('INSERT INTO player_inventory(user_id,equip_id,equipped,obtained_at,source) '
                         'VALUES(?,?,0,?,?)', (uid, equip_id, _now_iso(), 'admin'))
            conn.commit()
        _admin_audit('equipment', uid, f'grant {equip_id}')
    elif action == 'remove':
        inv_id = int(body.get('inv_id') or 0)
        with get_db() as conn:
            conn.execute('DELETE FROM player_inventory WHERE id=? AND user_id=?', (inv_id, uid))
            conn.commit()
        _admin_audit('equipment', uid, f'remove inv_id={inv_id}')
    else:
        return jsonify({'error': 'bad_action'}), 400
    return jsonify({'ok': True})

@app.route('/api/admin/users/<int:uid>/assets/appearance', methods=['POST'])
@admin_required
def admin_set_appearance(uid):
    body = request.get_json(silent=True) or {}
    action = str(body.get('action') or '')
    if action == 'grant':
        item_id = str(body.get('item_id') or '')
        if not any(a['id'] == item_id for a in APPEARANCE_DEFS):
            return jsonify({'error': 'unknown_appearance'}), 400
        with get_db() as conn:
            owned = conn.execute('SELECT id FROM player_wardrobe WHERE user_id=? AND item_id=?',
                                 (uid, item_id)).fetchone()
            if not owned:
                conn.execute('INSERT INTO player_wardrobe(user_id,item_id,obtained_at,source) '
                             'VALUES(?,?,?,?)', (uid, item_id, _now_iso(), 'admin'))
                conn.commit()
        _admin_audit('appearance', uid, f'grant {item_id}')
    elif action == 'remove':
        inv_id = int(body.get('inv_id') or 0)
        with get_db() as conn:
            conn.execute('DELETE FROM player_wardrobe WHERE id=? AND user_id=?', (inv_id, uid))
            conn.commit()
        _admin_audit('appearance', uid, f'remove inv_id={inv_id}')
    else:
        return jsonify({'error': 'bad_action'}), 400
    return jsonify({'ok': True})

@app.route('/api/admin/users/<int:uid>/assets/pet', methods=['POST'])
@admin_required
def admin_set_pet(uid):
    body = request.get_json(silent=True) or {}
    fields, vals = [], []
    for col, lo, hi in (('level', 1, 99), ('xp', 0, 10**6),
                        ('fullness', 0, 100), ('affection', 0, 100)):
        if col in body:
            fields.append(f'{col}=?')
            vals.append(max(lo, min(hi, int(body[col]))))
    if 'pet_key' in body:
        pk = str(body['pet_key'])
        if pk not in PET_CATALOG:
            return jsonify({'error': 'unknown_pet'}), 400
        fields.append('pet_key=?'); vals.append(pk)
    if not fields:
        return jsonify({'error': 'no_fields'}), 400
    with get_db() as conn:
        row = conn.execute('SELECT user_id FROM user_pets WHERE user_id=?', (uid,)).fetchone()
        if not row:
            return jsonify({'error': 'no_pet', 'message': '該用戶尚未選擇寵物'}), 400
        fields.append('updated_at=?'); vals.append(_now_iso())
        vals.append(uid)
        conn.execute(f'UPDATE user_pets SET {", ".join(fields)} WHERE user_id=?', vals)
        conn.commit()
        pet = conn.execute('SELECT * FROM user_pets WHERE user_id=?', (uid,)).fetchone()
    _admin_audit('pet', uid, str(body))
    return jsonify({'ok': True, 'pet': dict(pet)})

@app.route('/api/admin/users/<int:uid>/assets/rating', methods=['POST'])
@admin_required
def admin_set_rating(uid):
    body = request.get_json(silent=True) or {}
    with get_db() as conn:
        if 'elo' in body:
            elo = max(700.0, min(2800.0, float(body['elo'])))
            go_rank = _rating_to_rank(elo).replace('+', '')
            conn.execute('UPDATE users SET elo_rating=?, elo_updated_at=? WHERE id=?',
                         (elo, _now_iso(), uid))
            conn.execute('INSERT INTO user_stats(user_id, go_rank, go_rank_initialized) VALUES(?,?,1) '
                         'ON CONFLICT(user_id) DO UPDATE SET go_rank=?, go_rank_initialized=1',
                         (uid, go_rank, go_rank))
        if 'provisional' in body:
            conn.execute('UPDATE users SET elo_provisional=? WHERE id=?',
                         (1 if body['provisional'] else 0, uid))
        conn.commit()
        u = conn.execute('SELECT elo_rating, elo_provisional FROM users WHERE id=?', (uid,)).fetchone()
    _admin_audit('rating', uid, str(body))
    return jsonify({'ok': True, 'elo_rating': u['elo_rating'],
                    'elo_provisional': bool(u['elo_provisional'] or 0)})

@app.route('/api/admin/users/<int:uid>/assets/xp', methods=['POST'])
@admin_required
def admin_set_xp(uid):
    body = request.get_json(silent=True) or {}
    with get_db() as conn:
        conn.execute('INSERT OR IGNORE INTO user_stats(user_id) VALUES(?)', (uid,))
        s = conn.execute('SELECT xp FROM user_stats WHERE user_id=?', (uid,)).fetchone()
        cur = (s['xp'] if s else 0) or 0
        new_xp = max(0, int(body['set']) if 'set' in body else cur + int(body.get('delta') or 0))
        lv = xp_to_lv(new_xp)
        _, rank_xp, _ = lv_progress(new_xp)
        conn.execute('UPDATE user_stats SET xp=?, rank_level=?, rank_xp=? WHERE user_id=?',
                     (new_xp, f'LV{lv}', rank_xp, uid))
        conn.commit()
    _admin_audit('xp', uid, f'{cur} → {new_xp} (LV{lv})')
    return jsonify({'ok': True, 'xp': new_xp, 'rank_level': f'LV{lv}'})

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
    _ticket_used = False
    if not is_premium():
        # 商城「AI 解說券」：免費玩家持券自動消耗一張換一次解析
        _uid_t = session.get('user_id')
        if _uid_t:
            try:
                with get_db() as _c:
                    if _inv_consume(_c, _uid_t, 'ai_explain_ticket'):
                        _c.commit()
                        _ticket_used = True
            except Exception:
                pass
        if not _ticket_used:
            return jsonify({'error': 'premium_required', 'upgrade_url': '/upgrade'}), 403

    d            = request.get_json() or {}
    board_size   = d.get('boardSize', 9)
    player_color = d.get('playerColor', 'B')
    language     = 'en' if d.get('lang') == 'en' else 'zh'
    wrong_move   = d.get('wrongMove')
    question_id  = d.get('questionId')
    correct_moves = d.get('correctMoves') or []   # SGF 正確答案座標列表

    # ── 1. 題目資訊 + SGF 解說 ────────────────────────────────
    qs_map      = {q['id']: q for q in _load_questions()}
    q_info      = qs_map.get(question_id, {})
    sgf_comment = q_info.get('comment') or ''
    accepted_moves = _question_accepted_moves(q_info)
    if accepted_moves:
        existing = {(m.get('x'), m.get('y')) for m in (correct_moves or []) if isinstance(m, dict)}
        for move in accepted_moves:
            key = (move['x'], move['y'])
            if key not in existing:
                correct_moves.append({'x': move['x'], 'y': move['y']})
                existing.add(key)

    # 人工權威手筋標籤（最優先；依穩定 source 路徑精確查表）
    explain_override = _get_explain_override(q_info.get('source'))

    # correctMoves 後端權威自產（Single Source of Truth）：
    # 前端沒傳正解時，直接重用防作弊驗證路徑的 SGF 答案樹解析器，從 content
    # 解析正解第一手（可多分支）。主練習流程不旋轉，content 座標與盤面同系，
    # 無需 transform。解析不出（題目無著手節點）→ 維持空，由 explainer 改用
    # 「系統推薦應手」的降級文案，不謊稱正解。
    if not correct_moves:
        _ans_tree = _rt_parse_answer_tree(q_info.get('content') or '')
        if _ans_tree:
            correct_moves = [{'x': c['move'][0], 'y': c['move'][1]}
                             for c in _ans_tree.get('children', []) if c.get('move')]

    # ── 1b. 重建「題目原始盤面」board_state ────────────────────
    # 優先解析題目 SGF 的 AB[]/AW[] 設置子：前端傳來的 black/white 是
    # 「當前」盤面——答錯後已含錯誤落子與對方應手，拿去做手筋幾何偵測
    # 會張冠李戴。SGF 才是乾淨的初始局面。
    bs_int = int(board_size) if board_size else 9

    def _sgf_setup_board(sgf, bs):
        board = [[0] * bs for _ in range(bs)]
        found = False
        for tag, val in (('AB', 1), ('AW', -1)):
            for m in re.finditer(rf'{tag}((?:\[[a-s]{{2}}\])+)', sgf):
                for coord in re.findall(r'\[([a-s]{2})\]', m.group(1)):
                    x, y = ord(coord[0]) - 97, ord(coord[1]) - 97
                    if 0 <= x < bs and 0 <= y < bs:
                        board[y][x] = val
                        found = True
        return board if found else None

    board_state = _sgf_setup_board(q_info.get('content') or '', bs_int)
    if board_state is None:
        # fallback：前端盤面（剔除錯誤落子那顆，減少污染）
        board_state = [[0] * bs_int for _ in range(bs_int)]
        for s in d.get('black', []):
            x, y = s.get('x', -1), s.get('y', -1)
            if 0 <= x < bs_int and 0 <= y < bs_int:
                board_state[y][x] = 1
        for s in d.get('white', []):
            x, y = s.get('x', -1), s.get('y', -1)
            if 0 <= x < bs_int and 0 <= y < bs_int:
                board_state[y][x] = -1
        if wrong_move:
            wx, wy = wrong_move.get('x', -1), wrong_move.get('y', -1)
            if 0 <= wx < bs_int and 0 <= wy < bs_int:
                board_state[wy][wx] = 0

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
    q_explain_info = dict(q_info)
    q_explain_info['topic_en'] = _english_only(
        _i18n_topic_en(q_info.get('topic', '')) or q_info.get('topic_en'))
    q_explain_info['level_en'] = _english_only(
        _i18n_level_en(q_info.get('level', '')) or q_info.get('level_en'))
    q_explain_info['display_name_en'] = _question_display_name_en(q_info)
    explanation = explainer.explain(
        katago_raw,
        player_color=player_color,
        wrong_move=wrong_move,
        sgf_comment=sgf_comment,
        q_info=q_explain_info,
        board_state=board_state,       # ✅ 接通棋盤狀態，啟用手筋偵測
        correct_moves=correct_moves,
        override=explain_override,      # ✅ 人工權威手筋標籤（最優先）
        language=language,
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
            'display_name': _question_display_name(q),
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
      1. SRS 到期複習（目前棋力附近，最多 2 題）
      2. 錯題補強（wrong_count >= 2，目前棋力附近，最多 2 題）
      3. 屬性驅動新題（依 ATK/DEF/VIS/PREC 比例從對應學科選）

    隊列在每天第一次呼叫時生成並存入 DB（daily_training_queue）；
    後續同天的呼叫直接從 DB 讀取，確保題目清單完全固定。
    completed 從「今日已答題 ∩ 隊列 ID」計算，永遠準確。
    """
    import random as _rng_mod

    uid   = session['user_id']
    today = datetime.date.today().isoformat()
    force_next_round = request.args.get('next') in ('1', 'true', 'yes')
    TOTAL = 10
    SRS_LIMIT = 2
    MISTAKE_LIMIT = 2
    RANK_WINDOW = 2

    # ── 載入題庫 ────────────────────────────────────────────────
    all_qs  = _load_questions()
    enabled = {q['id']: q for q in all_qs if q.get('enabled', True)}

    with get_db() as conn:
        # ── 先查是否已有今天的持久化隊列 ──────────────────────────
        stored = conn.execute(
            'SELECT question_ids, sources, generated_at FROM daily_training_queue '
            'WHERE user_id=? AND date=?',
            (uid, today)
        ).fetchone()
        daily_elo_row = conn.execute(
            'SELECT elo_rating FROM users WHERE id=?',
            (uid,)
        ).fetchone()
        daily_elo_rating = daily_elo_row['elo_rating'] if daily_elo_row else None
        if (
            stored
            and daily_elo_rating is not None
            and (stored['generated_at'] or '') < '2026-05-29 06:52:00'
        ):
            conn.execute(
                'DELETE FROM daily_training_queue WHERE user_id=? AND date=?',
                (uid, today)
            )
            stored = None

        # ── 今日已作答（用來判斷一輪是否完成，也避免下一輪重複出題）──
        done_today = {
            r['question_id']
            for r in conn.execute(
                'SELECT DISTINCT question_id FROM review_log '
                'WHERE user_id=? AND DATE(reviewed_at)=?',
                (uid, today)
            ).fetchall()
        }

        if stored and force_next_round:
            conn.execute(
                'DELETE FROM daily_training_queue WHERE user_id=? AND date=?',
                (uid, today)
            )
            stored = None

        if stored:
            stored_ids = [
                qid for qid in json.loads(stored['question_ids'])
                if qid in enabled
            ]
            if stored_ids and len(done_today & set(stored_ids)) >= len(stored_ids):
                conn.execute(
                    'DELETE FROM daily_training_queue WHERE user_id=? AND date=?',
                    (uid, today)
                )
                stored = None

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
                if qid not in selected_set and qid in enabled and qid not in done_today:
                    selected.append({'id': qid, 'source': source})
                    selected_set.add(qid)
                    return True
                return False

            def _book_key(q):
                return (
                    q.get('map_name')
                    or str(q.get('source') or '').split('\\')[0].split('/')[0]
                    or q.get('topic')
                    or q.get('discipline')
                    or 'unknown'
                )

            def _diversified_question_ids(pool, limit):
                buckets = {}
                for q in pool:
                    buckets.setdefault(_book_key(q), []).append(q)
                for bucket in buckets.values():
                    bucket.sort(key=_rank_dist)
                    head = bucket[:8]
                    rng.shuffle(head)
                    bucket[:8] = head
                keys = list(buckets)
                rng.shuffle(keys)
                out = []
                while keys and len(out) < limit:
                    next_keys = []
                    for key in keys:
                        bucket = buckets[key]
                        if bucket:
                            out.append(bucket.pop(0)['id'])
                            if len(out) >= limit:
                                break
                        if bucket:
                            next_keys.append(key)
                    keys = next_keys
                return out

            # 今日推薦以棋力測驗 Elo 為主；go_rank 是線上對弈段位，
            # 新玩家常仍停在預設 30k，會把高段玩家誤導到低階題。
            go_rank = (stats_row['go_rank'] or '30k') if stats_row else '30k'
            if daily_elo_rating is not None:
                try:
                    elo_rank = _rating_to_rank(float(daily_elo_rating)).replace('+', '')
                    if elo_rank in DIFFICULTY_ORDER:
                        go_rank = elo_rank
                except Exception:
                    pass
            rank_idx = DIFFICULTY_ORDER.index(go_rank) if go_rank in DIFFICULTY_ORDER else 0

            def _rank_dist(q) -> int:
                r = q.get('rank') or q.get('difficulty') or ''
                try:
                    return abs(DIFFICULTY_ORDER.index(r) - rank_idx)
                except ValueError:
                    return 99

            def _rank_near(qid) -> bool:
                q = enabled.get(qid)
                return bool(q) and _rank_dist(q) <= RANK_WINDOW

            # Step 1：SRS 到期複習（目前棋力附近，最多 2 題）
            due_shuffled = [qid for qid in due_ids if _rank_near(qid) and qid not in done_today]
            rng.shuffle(due_shuffled)
            for qid in due_shuffled[:SRS_LIMIT]:
                add(qid, 'srs')

            # Step 2：錯題補強（目前棋力附近，最多 2 題）
            near_mistakes = [qid for qid in mistake_ids if _rank_near(qid) and qid not in done_today]
            near_mistakes.sort(key=lambda qid: _rank_dist(enabled[qid]))
            for qid in near_mistakes[:MISTAKE_LIMIT]:
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
                    close_pool = pool[:120]
                    new_pool[attr] = _diversified_question_ids(close_pool, len(close_pool))

                for attr, n in slots.items():
                    for qid in new_pool.get(attr, [])[:n]:
                        add(qid, f'new_{attr}')

            # Fallback：從未做過的題補（偏好近段位）
            if len(selected) < TOTAL:
                fallback = [
                    q for q in enabled.values()
                    if q['id'] not in selected_set and q['id'] not in seen_ids
                    and q['id'] not in done_today
                ]
                fallback.sort(key=_rank_dist)
                close = fallback[:120]
                for qid in _diversified_question_ids(close, TOTAL - len(selected)):
                    add(qid, 'new_general')

            # Fallback 2：全都做過了，從未掌握的舊題補
            if len(selected) < TOTAL:
                fallback2 = [
                    qid for qid in enabled
                    if qid not in selected_set and qid not in mastered_ids
                    and qid not in done_today
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
            'display_name': _question_display_name(q),
        })

    return jsonify({
        'total':     TOTAL,
        'completed': completed_count,
        'questions': questions_out,
        'date':      today,
    })


def _training_contaminated_total(uid, questions=None):
    since = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
    all_qs = questions if questions is not None else _load_questions()
    enabled = {q['id'] for q in all_qs if q.get('enabled', True)}

    with get_db() as conn:
        wrong_ids = {
            r['question_id']
            for r in conn.execute(
                'SELECT DISTINCT question_id FROM review_log '
                'WHERE user_id=? AND grade<3 AND DATE(reviewed_at)>=?',
                (uid, since)
            ).fetchall()
            if r['question_id'] in enabled
        }
        mastered_ids = {
            r['question_id']
            for r in conn.execute(
                'SELECT question_id FROM srs_cards '
                'WHERE user_id=? AND ease_factor>=2.5 AND repetitions>=3',
                (uid,)
            ).fetchall()
        }

    return len(wrong_ids - mastered_ids)


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
    _extra = 0
    if not premium:
        try:
            with get_db() as _c:
                _extra = _extra_questions_today(_c, uid)
        except Exception:
            pass
    _limit = FREE_DAILY_LIMIT + _extra
    return jsonify({
        'plan':          session.get('plan', 'free'),
        'is_premium':    premium,
        'today_count':   today_cnt,
        'daily_limit':   _limit,
        'extra_today':   _extra,
        'remaining':     max(0, _limit - today_cnt) if not premium else None,
        'total_q_count': total_count,
    })

# ══════════════════════════════════════════════════════════════
# 主線冒險 / 領主封印
# ══════════════════════════════════════════════════════════════

BOSS_UNLOCK_PCT = 30
BOSS_EXAM_SIZE = 20
BOSS_PASS_SCORE = 16
BOSS_FAIL_COOLDOWN = 30

# 每關綁定的劇情主線書（topic）。地圖通關只算這幾本，避免題量爆炸；
# 額外大題庫（初階元素魔法導論、萬陣試煉、懸賞令…）不綁關卡，留給自由練習。
ADVENTURE_ZONES = [
    {'key':'k26_30', 'label':'26–30級', 'name':'圍棋新手村',   'icon':'🟢', 'min':0,  'max':4,   'stage':'LV1',  'books':['1圍棋新手村','2新手村的考驗']},
    {'key':'k21_25', 'label':'21–25級', 'name':'史萊姆平原',   'icon':'🟦', 'min':5,  'max':9,   'stage':'LV2',  'books':['3史萊姆平原','4史萊姆討伐戰']},
    {'key':'k16_20', 'label':'16–20級', 'name':'哥布林洞穴',   'icon':'🦇', 'min':10, 'max':14,  'stage':'LV3',  'books':['5哥布林洞穴','6哥布林巡邏隊']},
    {'key':'k11_15', 'label':'11–15級', 'name':'迷霧森林',     'icon':'🌲', 'min':15, 'max':19,  'stage':'LV4',  'books':['7迷霧森林','8迷霧森林深處']},
    {'key':'k6_10',  'label':'6–10級',  'name':'獸人部落',     'icon':'🪓', 'min':20, 'max':24,  'stage':'LV5',  'books':['9獸人部落','10獸人角鬥場']},
    {'key':'k1_5',   'label':'1–5級',   'name':'龍之谷',       'icon':'🐉', 'min':25, 'max':29,  'stage':'LV6',  'books':['11飛龍討伐','12龍之谷守衛']},
    {'key':'d1_2',   'label':'1–2段',   'name':'賢者之塔',     'icon':'🔮', 'min':30, 'max':31,  'stage':'LV7',  'books':['13賢者之塔','14大魔法師試煉']},
    {'key':'d3_4',   'label':'3–4段',   'name':'魔王城前線',   'icon':'👺', 'min':32, 'max':33,  'stage':'LV8',  'books':['15皇家騎士團遠征','16魔王城前線','17混沌領主的考驗']},
    {'key':'d5_6',   'label':'5–6段',   'name':'諸神黃昏',     'icon':'🗿', 'min':34, 'max':35,  'stage':'LV9',  'books':['18諸神黃昏']},
    {'key':'d7_plus','label':'7段＋',   'name':'上古終焉神殿', 'icon':'✨', 'min':36, 'max':998, 'stage':'LV10', 'books':['19東方神祕結界','20上古終焉神殿']},
]

ADVENTURE_BOSS_META = {
    'k26_30': {'key': 'village_examiner', 'name': '村莊考核官', 'name_en': 'Village Examiner'},
    'k21_25': {'key': 'swarm_lord', 'name': '蜂群領主', 'name_en': 'Swarm Lord'},
    'k16_20': {'key': 'goblin_centurion', 'name': '哥布林百夫長', 'name_en': 'Goblin Centurion'},
    'k11_15': {'key': 'misty_phantom_rabbit_king', 'name': '迷霧幻影兔王', 'name_en': 'Misty Phantom Rabbit King'},
    'k6_10': {'key': 'iron_orc_chieftain', 'name': '鋼鐵獸人酋長', 'name_en': 'Iron Orc Chieftain'},
    'k1_5': {'key': 'grand_temple_knight', 'name': '聖殿大騎士長', 'name_en': 'Grand Temple Knight'},
    'd1_2': {'key': 'archmage_phantom', 'name': '大魔法師幻影', 'name_en': 'Archmage Phantom'},
    'd3_4': {'key': 'chaos_lord', 'name': '混沌領主', 'name_en': 'Chaos Lord'},
    'd5_6': {'key': 'fallen_war_god_statue', 'name': '墮落戰神古像', 'name_en': 'Fallen War-God Statue'},
    'd7_plus': {'key': 'source_of_black_white_order', 'name': '黑白秩序之源', 'name_en': 'Source of Black-White Order'},
}

# zone_key → assets/tiers 關卡圖檔名（試玩結果頁推薦卡用實際關卡美術，非 emoji）
_TIER_IMG = {
    'k26_30': '26-30', 'k21_25': '21-25', 'k16_20': '16-20', 'k11_15': '11-15',
    'k6_10': '6-10', 'k1_5': '1-5', 'd1_2': '1-2d', 'd3_4': '3-4d',
    'd5_6': '5-6d', 'd7_plus': '7d',
}

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

def _adventure_zone_key_for_go_rank(go_rank):
    rank = str(go_rank or '').strip().lower().replace('+', '')
    rating = _RANK_TO_RATING.get(rank)
    if rating is None:
        return None
    return _adventure_start_zone_for_elo(rating)

def _adventure_highest_zone_key(zone_keys):
    best_key = None
    best_idx = -1
    for zone_key in zone_keys:
        zone = _zone_by_key(zone_key)
        if not zone:
            continue
        idx = _adventure_zone_index(zone_key)
        if idx > best_idx:
            best_key = zone_key
            best_idx = idx
    return best_key

def _resolve_adventure_effective_start_zone(conn, uid, unlock_rows=None):
    candidate_keys = []
    for row in unlock_rows or []:
        zone_key = (row.get('start_zone_key') if isinstance(row, dict) else row['start_zone_key']) or ''
        if zone_key:
            candidate_keys.append(zone_key)

    stats_row = conn.execute('SELECT go_rank FROM user_stats WHERE user_id=?', (uid,)).fetchone()
    if stats_row and stats_row['go_rank']:
        rank_zone = _adventure_zone_key_for_go_rank(stats_row['go_rank'])
        if rank_zone:
            candidate_keys.append(rank_zone)

    user_row = conn.execute('SELECT elo_rating FROM users WHERE id=?', (uid,)).fetchone()
    if user_row and user_row['elo_rating'] is not None:
        candidate_keys.append(_adventure_start_zone_for_elo(user_row['elo_rating']))

    rating_row = conn.execute(
        '''
        SELECT cur_rating
          FROM rating_test_sessions
         WHERE user_id=? AND status='completed'
         ORDER BY COALESCE(finished_at, started_at) DESC
         LIMIT 1
        ''',
        (uid,),
    ).fetchone()
    if rating_row and rating_row['cur_rating'] is not None:
        candidate_keys.append(_adventure_start_zone_for_elo(rating_row['cur_rating']))

    return _adventure_highest_zone_key(candidate_keys)

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
    # 優先依「綁定的書（topic）」篩；沒綁定才退回舊的難度範圍邏輯
    books = set(zone.get('books') or [])
    out = []
    for q in qs:
        if not q.get('enabled', True):
            continue
        if not premium and not question_is_free(q):
            continue
        if books:
            if (q.get('topic') or '') in books:
                out.append(q)
        else:
            idx = _question_rank_index(q)
            if zone['min'] <= idx <= zone['max']:
                out.append(q)
    return out


_HOME_REPORT_DISCIPLINES = {
    'tesuji',
    'capture_escape',
    'connection_cut',
    'life_death',
    'shape_weakness',
    'opening_direction',
    'whole_board',
    'endgame_counting',
}
_HOME_REPORT_REQUIRED_RESPONSES = 15


def _home_report_active_zone(zones):
    for zone in zones:
        if zone.get('boss_ready'):
            return zone
    for zone in zones:
        if zone.get('unlocked') and not zone.get('cleared'):
            return zone
    for zone in zones:
        if zone.get('unlocked'):
            return zone
    return zones[0] if zones else None


def _home_report_weakness_summary(uid, questions=None):
    since = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
    # 以 question_id → 題目當前 discipline 對應；對 level/topic 改名完全免疫。
    # （舊版用 (topic, level) join 歷史 review_log，題目重新分類後會對不上而漏算。）
    qid_to_disc = {}
    for question in (questions if questions is not None else _load_questions()):
        disc = question.get('discipline')
        if disc:
            qid_to_disc[question.get('id')] = disc

    with get_db() as conn:
        rows = conn.execute(
            '''SELECT rl.question_id AS qid, rl.discipline AS snap_disc,
                      COUNT(*) AS total,
                      SUM(CASE WHEN rl.grade >= 3 THEN 1 ELSE 0 END) AS correct
               FROM review_log rl
               WHERE rl.user_id=? AND DATE(rl.reviewed_at) >= ?
               GROUP BY rl.question_id, rl.discipline''',
            (uid, since)
        ).fetchall()

    disc_total = Counter()
    disc_correct = Counter()
    for row in rows:
        # 優先用題目當前 discipline；題目已刪除才退回 review_log 當下快照
        disc = qid_to_disc.get(row['qid']) or row['snap_disc']
        if disc not in _HOME_REPORT_DISCIPLINES:
            continue
        total = int(row['total'] or 0)
        correct = int(row['correct'] or 0)
        disc_total[disc] += total
        disc_correct[disc] += correct

    valid_responses = int(sum(disc_total.values()))
    summary = {
        'status': 'collecting',
        'discipline_key': None,
        'valid_responses': valid_responses,
        'required_responses': _HOME_REPORT_REQUIRED_RESPONSES,
    }
    if valid_responses <= 0:
        return summary
    if valid_responses < _HOME_REPORT_REQUIRED_RESPONSES:
        return summary

    candidates = [disc for disc, total in disc_total.items() if total > 0]
    if not candidates:
        return {
            'status': 'unavailable',
            'discipline_key': None,
            'valid_responses': 0,
            'required_responses': _HOME_REPORT_REQUIRED_RESPONSES,
        }

    weakest = min(
        candidates,
        key=lambda disc: (
            disc_correct[disc] / max(disc_total[disc], 1),
            -disc_total[disc],
            disc,
        )
    )
    return {
        'status': 'ready',
        'discipline_key': weakest,
        'valid_responses': int(disc_total[weakest]),
        'required_responses': _HOME_REPORT_REQUIRED_RESPONSES,
    }


def _home_report_boss_summary(uid):
    zones = _adventure_state_cached(uid)
    active = _home_report_active_zone(zones)
    if not active:
        return {
            'state': 'unavailable',
            'zone_key': None,
            'progress_pct': 0,
            'unlock_pct': BOSS_UNLOCK_PCT,
            'remaining_questions': 0,
            'cooldown_left': 0,
        }

    total = int(active.get('total') or 0)
    seen = int(active.get('seen') or 0)
    unlock_pct = int(active.get('unlock_pct') or BOSS_UNLOCK_PCT)
    unlock_seen = math.ceil(total * unlock_pct / 100.0) if total > 0 else 0
    remaining_to_unlock = max(0, unlock_seen - seen)

    state = 'sealed'
    remaining_questions = remaining_to_unlock
    if active.get('cleared'):
        state = 'cleared'
        remaining_questions = 0
    elif active.get('cooldown_left', 0) > 0:
        state = 'cooldown'
        remaining_questions = int(active.get('cooldown_left') or 0)
    elif active.get('boss_ready'):
        state = 'ready'
        remaining_questions = 0
    elif not active.get('unlocked'):
        state = 'unavailable'

    return {
        'state': state,
        'zone_key': active.get('key'),
        'progress_pct': int(active.get('pct') or 0),
        'unlock_pct': unlock_pct,
        'remaining_questions': int(remaining_questions),
        'cooldown_left': int(active.get('cooldown_left') or 0),
    }


def _home_report_action(weakness, boss, mistakes_due):
    if boss.get('state') == 'ready':
        return {'kind': 'boss_challenge', 'zone_key': boss.get('zone_key'), 'discipline_key': None}
    if boss.get('state') == 'cooldown':
        return {'kind': 'boss_cooldown_training', 'zone_key': boss.get('zone_key'), 'discipline_key': None}
    if mistakes_due > 0:
        return {'kind': 'mistake_cleanup', 'zone_key': None, 'discipline_key': None}
    if weakness.get('status') == 'ready':
        return {'kind': 'weakness_training', 'zone_key': None, 'discipline_key': weakness.get('discipline_key')}
    return {'kind': 'none', 'zone_key': None, 'discipline_key': None}

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
        effective_start_zone_key = _resolve_adventure_effective_start_zone(
            conn,
            uid,
            unlock_rows=[dict(r) for r in unlock_rows],
        )

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
            'effective_start_zone_key': effective_start_zone_key,
            'stars': stars,
            'attempts': int(row.get('attempts') or 0),
            'best_score': int(row.get('best_score') or 0),
            'last_attempt_at': row.get('last_attempt_at'),
            'cleared_at': row.get('cleared_at'),
            'updated_at': row.get('updated_at') or now,
        })
        previous_cleared = cleared

    return zones


_ADVENTURE_STATE_CACHE = {}
_ADVENTURE_STATE_CACHE_TTL = 20


def _set_adventure_state_cache(uid, zones):
    _ADVENTURE_STATE_CACHE[int(uid)] = (time.time(), zones)


def _clear_adventure_state_cache(uid):
    _ADVENTURE_STATE_CACHE.pop(int(uid), None)


def _adventure_state_cached(uid):
    key = int(uid)
    cached = _ADVENTURE_STATE_CACHE.get(key)
    if cached:
        cached_at, zones = cached
        if time.time() - cached_at <= _ADVENTURE_STATE_CACHE_TTL:
            return zones
    zones = _adventure_state(uid)
    _set_adventure_state_cache(uid, zones)
    return zones


def _adventure_recommended_zone_key(zones, placement_start_zone=None):
    if not zones:
        return None
    start_idx = _adventure_zone_index(placement_start_zone) if placement_start_zone else 0

    def _is_unlocked(zone):
        return bool(zone.get('unlocked')) or _adventure_zone_index(zone['key']) <= start_idx

    for zone in zones[start_idx:]:
        if _is_unlocked(zone) and not zone.get('cleared'):
            return zone['key']
    for zone in zones[start_idx:]:
        if _is_unlocked(zone):
            return zone['key']
    for zone in zones:
        if _is_unlocked(zone) and not zone.get('cleared'):
            return zone['key']
    for zone in zones:
        if _is_unlocked(zone):
            return zone['key']
    return zones[0]['key']


def _adventure_effective_start_zone_key(zones):
    candidate_keys = []
    for zone in zones or []:
        if zone.get('effective_start_zone_key'):
            candidate_keys.append(zone.get('effective_start_zone_key'))
        if zone.get('placement_start_zone'):
            candidate_keys.append(zone.get('placement_start_zone'))
    return _adventure_highest_zone_key(candidate_keys)

def _adventure_boss_payload(zone):
    meta = ADVENTURE_BOSS_META.get(zone.get('key'), {})
    total = max(0, int(zone.get('total') or 0))
    completed_count = max(0, int(zone.get('seen') or 0))
    threshold = math.ceil(total * (int(zone.get('unlock_pct') or BOSS_UNLOCK_PCT) / 100.0)) if total > 0 else 0
    return {
        'key': meta.get('key'),
        'name': meta.get('name') or zone.get('name'),
        'name_en': meta.get('name_en'),
        'available': bool(zone.get('boss_ready')),
        'challenge_threshold': threshold,
        'remaining_to_challenge': max(0, threshold - completed_count),
    }

def _adventure_progress_payload(zone):
    total = max(0, int(zone.get('total') or 0))
    completed_count = max(0, int(zone.get('seen') or 0))
    defeated_count = max(0, int(zone.get('defeated') or 0))
    stars = max(0, int(zone.get('stars') or 0))
    threshold_star_two = math.ceil(total * 0.6) if total > 0 else 0
    next_star = None
    next_star_threshold = None
    remaining_to_next_star = None
    stars_complete = stars >= 3

    if not stars_complete:
        if stars <= 0:
            next_star = 1
        elif stars == 1:
            next_star = 2
            next_star_threshold = threshold_star_two
            remaining_to_next_star = max(0, threshold_star_two - completed_count)
        elif stars == 2:
            next_star = 3
            next_star_threshold = total
            remaining_to_next_star = max(0, total - defeated_count)

    return {
        'completed_count': completed_count,
        'total_count': total,
        'stars': stars,
        'next_star': next_star,
        'next_star_threshold': next_star_threshold,
        'remaining_to_next_star': remaining_to_next_star,
        'stars_complete': stars_complete,
    }


def _adventure_zone_stage_payload(zone, status, can_enter, completed, skipped_by_placement,
                                  recommended, selected):
    return {
        'stage_key': zone['key'],
        'zone_key': zone['key'],
        'label': zone.get('stage') or zone.get('label') or zone.get('name') or zone['key'],
        'href': f"/?zone={zone['key']}&adventure=1&resume=1",
        'status': (
            'selected' if selected else
            'recommended' if recommended else
            status
        ),
        'can_enter': can_enter,
        'completed': completed,
        'skipped_by_placement': skipped_by_placement,
        'recommended': recommended,
        'selected': selected,
        'stars': int(zone.get('stars') or 0),
        'best_score': int(zone.get('best_score') or 0),
    }


def _adventure_zone_has_playable_target(zone):
    if not zone:
        return False
    total = zone.get('total')
    if total is None:
        return True
    try:
        total = int(total)
    except (TypeError, ValueError):
        total = 0
    return total > 0 or bool(zone.get('boss_ready')) or bool(zone.get('cleared'))


def _adventure_map_state_from_zones(zones, selected_stage_key=None):
    placement_marker = next((z for z in zones if z.get('placement_start_zone')), None)
    placement_start_zone = placement_marker.get('placement_start_zone') if placement_marker else None
    placement_zone = next((z for z in zones if z['key'] == placement_start_zone), None)
    effective_start_zone_key = _adventure_effective_start_zone_key(zones) or placement_start_zone
    effective_start_zone = next((z for z in zones if z['key'] == effective_start_zone_key), None)
    placement_idx = _adventure_zone_index(effective_start_zone_key) if effective_start_zone_key else None
    recommended_zone_key = _adventure_recommended_zone_key(zones, effective_start_zone_key)
    valid_zone_keys = {
        z['key'] for z in zones
        if z.get('unlocked') or (
            effective_start_zone_key is not None
            and _adventure_zone_index(z['key']) <= _adventure_zone_index(effective_start_zone_key)
        )
    }
    selected_zone_key = selected_stage_key if selected_stage_key in valid_zone_keys else recommended_zone_key

    recommended_payload = None
    selected_payload = None
    zone_payloads = []
    for zone in zones:
        effective_placement_unlocked = (
            placement_idx is not None and _adventure_zone_index(zone['key']) <= placement_idx
        )
        can_enter = bool(zone.get('unlocked')) and _adventure_zone_has_playable_target(zone)
        completed = bool(zone.get('cleared'))
        skipped_by_placement = (
            placement_idx is not None
            and _adventure_zone_index(zone['key']) < placement_idx
            and can_enter
            and not completed
        )
        recommended = zone['key'] == recommended_zone_key
        selected = zone['key'] == selected_zone_key
        if completed:
            status = 'completed'
        elif skipped_by_placement:
            status = 'skipped_by_placement'
        elif can_enter:
            status = 'unlocked'
        else:
            status = 'locked'

        stage_payload = _adventure_zone_stage_payload(
            zone, status, can_enter, completed, skipped_by_placement, recommended, selected
        )
        zone_payload = {
            **zone,
            'status': status,
            'can_enter': can_enter,
            'completed': completed,
            'skipped_by_placement': skipped_by_placement,
            'recommended': recommended,
            'selected': selected,
            'boss': _adventure_boss_payload(zone),
            'progress': _adventure_progress_payload(zone),
            'stage_key': zone['key'],
            'stages': [stage_payload],
        }
        zone_payloads.append(zone_payload)
        if recommended:
            recommended_payload = {
                'zone_key': zone['key'],
                'stage_key': stage_payload['stage_key'],
                'label': stage_payload['label'],
                'zone_label': zone.get('label'),
                'zone_name': zone.get('name'),
            }
        if selected:
            selected_payload = {
                'zone_key': zone['key'],
                'stage_key': stage_payload['stage_key'],
                'label': stage_payload['label'],
                'zone_label': zone.get('label'),
                'zone_name': zone.get('name'),
                'source': 'query' if selected_stage_key in valid_zone_keys else 'default_recommended',
            }

    if not selected_payload and recommended_payload:
        selected_payload = {
            **recommended_payload,
            'source': 'default_recommended',
        }

    placement_payload = {
        'source': placement_zone.get('unlock_source') if placement_zone else None,
        'start_zone_key': placement_start_zone,
        'start_zone_label': placement_zone.get('label') if placement_zone else None,
        'start_zone_name': placement_zone.get('name') if placement_zone else None,
        'start_stage_key': placement_start_zone,
        'effective_start_zone_key': effective_start_zone_key,
        'effective_start_zone_label': effective_start_zone.get('label') if effective_start_zone else None,
        'effective_start_zone_name': effective_start_zone.get('name') if effective_start_zone else None,
    }
    return {
        'placement': placement_payload,
        'recommended': recommended_payload,
        'selected': selected_payload,
        'active_zone_key': selected_payload.get('zone_key') if selected_payload else None,
        'zones': zone_payloads,
    }


def _adventure_map_state(uid, selected_stage_key=None, use_cache=False):
    zones = _adventure_state_cached(uid) if use_cache else _adventure_state(uid)
    return _adventure_map_state_from_zones(zones, selected_stage_key=selected_stage_key)

@app.route('/api/adventure/progress')
@login_required
def adventure_progress():
    map_state = _adventure_map_state(
        session['user_id'],
        selected_stage_key=(request.args.get('selected_stage_key') or '').strip() or None,
    )
    return jsonify({
        'unlock_pct': BOSS_UNLOCK_PCT,
        'boss_exam_size': BOSS_EXAM_SIZE,
        'boss_pass_score': BOSS_PASS_SCORE,
        'cooldown_required': BOSS_FAIL_COOLDOWN,
        **map_state,
    })


@app.route('/api/adventure/map-state')
@login_required
def adventure_map_state():
    map_state = _adventure_map_state(
        session['user_id'],
        selected_stage_key=(request.args.get('selected_stage_key') or '').strip() or None,
    )
    return jsonify({
        'unlock_pct': BOSS_UNLOCK_PCT,
        'boss_exam_size': BOSS_EXAM_SIZE,
        'boss_pass_score': BOSS_PASS_SCORE,
        'cooldown_required': BOSS_FAIL_COOLDOWN,
        **map_state,
    })


@app.route('/api/adventure/bootstrap')
@login_required
def adventure_bootstrap():
    zones = _adventure_state(session['user_id'])
    _set_adventure_state_cache(session['user_id'], zones)
    map_state = _adventure_map_state_from_zones(
        zones,
        selected_stage_key=(request.args.get('selected_stage_key') or '').strip() or None,
    )
    return jsonify({
        'unlock_pct': BOSS_UNLOCK_PCT,
        'boss_exam_size': BOSS_EXAM_SIZE,
        'boss_pass_score': BOSS_PASS_SCORE,
        'cooldown_required': BOSS_FAIL_COOLDOWN,
        **map_state,
    })


@app.route('/api/home/report-summary')
@login_required
def home_report_summary():
    uid = session['user_id']
    questions = _load_questions()
    weakness = _home_report_weakness_summary(uid, questions)
    boss = _home_report_boss_summary(uid)
    mistakes_due = _training_contaminated_total(uid, questions)
    return jsonify({
        'schema_version': 1,
        'weakness': weakness,
        'boss': boss,
        'mistakes_due': mistakes_due,
        'action': _home_report_action(weakness, boss, mistakes_due),
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
                stars=GREATEST(adventure_boss_progress.stars, excluded.stars),
                attempts=excluded.attempts,
                best_score=GREATEST(adventure_boss_progress.best_score, excluded.best_score),
                cooldown_until_seen=excluded.cooldown_until_seen,
                last_attempt_at=excluded.last_attempt_at,
                cleared_at=COALESCE(adventure_boss_progress.cleared_at, excluded.cleared_at),
                updated_at=excluded.updated_at
        ''', (uid, zone_key, cleared, stars, attempts, best_score, cooldown_until, now, cleared_at, now))

    session.pop('adventure_boss_exam', None)
    _clear_adventure_state_cache(uid)
    map_state = _adventure_map_state(uid)
    return jsonify({
        'ok': True,
        'passed': passed,
        'correct': correct,
        'total': total,
        'pass_score': pass_score,
        'cooldown_left': 0 if passed else BOSS_FAIL_COOLDOWN,
        **map_state,
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
    quest_filter      = (request.args.get('quest') or '').strip()
    quest_ids         = None
    if quest_filter:
        seg = _quest_segment_for_key(quest_filter, premium)
        quest_ids = set(seg.get('question_ids') or []) if seg else set()
    slim_mode         = bool(request.args.get('slim'))   # 首頁用：只回前端實際用到的精簡欄位，砍掉傳輸量
    result  = []
    for q in qs:
        if not q.get('enabled', True):
            continue
        if quest_ids is not None and q.get('id') not in quest_ids:
            continue
        if discipline_filter:
            if discipline_filter == 'whole_board':
                if not _is_whole_board_practice_question(q):
                    continue
            elif (q.get('discipline') or 'whole_board') != discipline_filter:
                continue
        if stage_filter and (q.get('stage') or '') != stage_filter:
            continue
        if grimoire_filter is not None and q.get('grimoire_id') != grimoire_filter:
            continue
        locked = (not premium) and (not question_is_free(q))
        if slim_mode:
            # 首頁 index.html 實際用到的欄位（loadQuestion / next-prev / scoped filter / 怪物 fallback）
            result.append({
                'id':             q['id'],
                'topic':          q.get('topic', ''),
                'topic_en':       _i18n_topic_en(q.get('topic', '')) or q.get('topic_en') or '',
                'level':          q.get('level', ''),
                'level_en':       _i18n_level_en(q.get('level', '')) or q.get('level_en') or '',
                'display_name':   _question_display_name(q),
                'difficulty':     q.get('difficulty', ''),
                'rank':           q.get('rank') or q.get('difficulty', ''),
                'sort_order':     q.get('sort_order'),
                'locked':         locked,
                'grimoire_id':    q.get('grimoire_id'),
                'discipline':     q.get('discipline', ''),
                'stage':          q.get('stage', ''),
                'encounter_type': q.get('encounter_type', 'normal'),
                'monster_type':   q.get('battle_monster_type', ''),
                'monster_name':   q.get('monster_name', ''),
                'monster_avatar': _question_monster_avatar(q),
            })
            continue
        result.append({
            'id':                q['id'],
            'topic':             q.get('topic', ''),
            'topic_en':          _i18n_topic_en(q.get('topic', '')) or q.get('topic_en') or '',
            'level':             q.get('level', ''),
            'level_en':          _i18n_level_en(q.get('level', '')) or q.get('level_en') or '',
            'source':            q.get('source', ''),
            'display_name':      _question_display_name(q),
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


@app.route('/api/curriculum/summary')
@login_required
def curriculum_summary():
    """curriculum.html 進度頁專用：後端聚合各「學科×階段」的題數/解鎖/Boss/已練，
    取代前端抓 60MB 全題庫再於瀏覽器 group by（只回幾十 KB）。"""
    uid     = session['user_id']
    premium = is_premium()

    def _is_whole_board_trial(q):
        tags = q.get('tags') or []
        return ((q.get('discipline') or '') == 'whole_board'
                or q.get('encounter_type') in ('chapter_boss', 'book_boss')
                or 'whole_board' in tags)

    groups   = {}   # key -> 聚合 dict
    qid_meta = {}   # qid -> (keys, encounter_type)，供已練計數

    def _grp(key):
        d = groups.get(key)
        if d is None:
            disc, stage = key.split('::', 1)
            d = groups[key] = {
                'discipline': disc, 'stage': stage,
                'total': 0, 'unlocked': 0, 'practiced': 0,
                'maps': set(), 'family': '',
                'chapterBossTotal': 0, 'chapterBossDefeated': 0,
                'bookBossTotal': 0, 'bookBossDefeated': 0,
                'aggregate': False,
            }
        return d

    for q in _load_questions():
        if not q.get('enabled', True):
            continue
        disc    = q.get('discipline') or 'whole_board'
        stage   = q.get('stage') or 'LV2'
        enc     = q.get('encounter_type', 'normal')
        locked  = (not premium) and (not question_is_free(q))
        key     = f"{disc}::{stage}"
        agg_key = f"whole_board::{stage}"

        keys = [key]
        if key != agg_key and _is_whole_board_trial(q):
            keys.append(agg_key)

        for k in keys:
            d = _grp(k)
            d['total'] += 1
            if not locked:
                d['unlocked'] += 1
            mid = q.get('map_id')
            if mid:
                d['maps'].add(mid)
            fam = q.get('monster_family_label')
            if fam and not d['family']:
                d['family'] = fam
            if enc == 'chapter_boss':
                d['chapterBossTotal'] += 1
            elif enc == 'book_boss':
                d['bookBossTotal'] += 1
            if k == agg_key and k != key:
                d['aggregate'] = True

        qid_meta[q['id']] = (keys, enc)

    with get_db() as conn:
        rows = conn.execute(
            'SELECT question_id,last_grade FROM srs_cards WHERE user_id=?', (uid,)
        ).fetchall()
    cards_count = len(rows)
    for r in rows:
        meta = qid_meta.get(r['question_id'])
        if not meta:
            continue
        keys, enc = meta
        grade = r['last_grade'] or 0
        for k in keys:
            d = groups.get(k)
            if not d:
                continue
            d['practiced'] += 1
            if grade >= 3:
                if enc == 'chapter_boss':
                    d['chapterBossDefeated'] += 1
                elif enc == 'book_boss':
                    d['bookBossDefeated'] += 1

    units = [{
        'discipline':          d['discipline'],
        'stage':               d['stage'],
        'total':               d['total'],
        'unlocked':            d['unlocked'],
        'practiced':           d['practiced'],
        'mapCount':            len(d['maps']),
        'familyLabel':         d['family'],
        'chapterBossTotal':    d['chapterBossTotal'],
        'chapterBossDefeated': d['chapterBossDefeated'],
        'bookBossTotal':       d['bookBossTotal'],
        'bookBossDefeated':    d['bookBossDefeated'],
        'aggregate':           d['aggregate'],
    } for d in groups.values()]

    resp = jsonify({'units': units, 'cardsCount': cards_count})
    resp.headers['Cache-Control'] = 'no-store'
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
        'source':       q.get('source', ''),
        'display_name': _question_display_name(q),
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
        'accepted_moves':   _question_accepted_moves(q),
        'solution_state':   q.get('solution_state', 'open' if q.get('enabled', True) else 'disabled'),
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
            'topic_en':     _english_only(_i18n_topic_en(q.get('topic', '')) or q.get('topic_en')),
            'level':        q.get('level', ''),
            'level_en':     _english_only(_i18n_level_en(q.get('level', '')) or q.get('level_en')),
            'display_name': q.get('display_name', ''),
            'display_name_en': _question_display_name_en(q),
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
            'accepted_move_count': len(_question_accepted_moves(q)),
            'solution_state': q.get('solution_state', 'open' if q.get('enabled', True) else 'disabled'),
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
        row = conn.execute('SELECT go_rank, go_rank_initialized FROM user_stats WHERE user_id=?', (uid,)).fetchone()
        go_rank = (row['go_rank'] or '30k') if row else '30k'
        results = conn.execute(
            'SELECT result, go_rank, played_at FROM game_results WHERE user_id=? ORDER BY played_at DESC LIMIT 20',
            (uid,)
        ).fetchall()
        initialized = bool(row['go_rank_initialized']) if row and 'go_rank_initialized' in row.keys() else False
        initialized = initialized or go_rank != '30k' or len(results) > 0
        if initialized and row and not row['go_rank_initialized']:
            conn.execute('UPDATE user_stats SET go_rank_initialized=1 WHERE user_id=?', (uid,))
        conn.commit()
    total  = len(results)
    wins   = sum(r['result'] for r in results)
    recent = [{'result': r['result'], 'go_rank': r['go_rank'], 'played_at': r['played_at']}
              for r in results[:15]]
    return jsonify({
        'go_rank':   go_rank,
        'initialized': initialized,
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
        conn.execute('UPDATE user_stats SET go_rank=?, go_rank_initialized=1 WHERE user_id=?', (rank, uid))
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
        conn.execute('INSERT INTO book_bands(name,band_rank) VALUES(?,?) ON CONFLICT (name) DO UPDATE SET band_rank = EXCLUDED.band_rank',
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
        conn.execute('INSERT INTO book_bands(name,band_rank) VALUES(?,?) ON CONFLICT (name) DO UPDATE SET band_rank = EXCLUDED.band_rank',
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
    try:
        response_ms = max(0, min(600000, int(data.get('response_ms')))) \
            if data.get('response_ms') is not None else None
    except (TypeError, ValueError):
        response_ms = None
    source_context = str(data.get('source_context') or 'practice')[:40]
    training_set_id = data.get('training_set_id')
    try:
        training_set_id = int(training_set_id) if training_set_id is not None else None
    except (TypeError, ValueError):
        training_set_id = None

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

        # 2. 是否超過今日上限（含商城「加題券」當日加成）
        today_count = get_today_free_count(uid)
        _extra = 0
        try:
            with get_db() as _c:
                _extra = _extra_questions_today(_c, uid)
        except Exception:
            pass
        _eff_limit = FREE_DAILY_LIMIT + _extra
        if today_count >= _eff_limit:
            return jsonify({
                'error':       'daily_limit',
                'message':     f'免費版每日上限 {_eff_limit} 題，今日已完成 {today_count} 題',
                'today_count': today_count,
                'limit':       _eff_limit,
                'upgrade_url': '/upgrade'
            }), 429

    now = datetime.datetime.now().isoformat()

    qs_map = {q['id']: q for q in _load_questions()}
    q_info = qs_map.get(qid, {})
    ITEM_RATING_VERSION, _, rank_to_rating = _load_premium_weekly_rating_helpers()

    with get_db() as conn:
        player_row = conn.execute(
            'SELECT elo_rating FROM users WHERE id=?', (uid,)
        ).fetchone()
        player_rating_snapshot = float(player_row['elo_rating'] or 1400) if player_row else 1400.0
        question_rating_snapshot = rank_to_rating(q_info.get('rank') or q_info.get('difficulty'))
        training_item = None
        if training_set_id is not None:
            training_item = conn.execute(
                'SELECT i.id FROM premium_training_items i '
                'JOIN premium_training_sets s ON s.id=i.set_id '
                'JOIN weekly_reports r ON r.id=s.report_id '
                'WHERE i.set_id=? AND i.question_id=? AND s.user_id=? '
                'AND s.status=? AND r.status=?',
                (training_set_id, qid, uid, 'active', 'published')
            ).fetchone()
            if not training_item:
                return jsonify({'error': 'invalid_training_item'}), 403
        row = conn.execute(
            'SELECT * FROM srs_cards WHERE user_id=? AND question_id=?',(uid,qid)).fetchone()
        ef,iv,rp = (row['ease_factor'],row['interval'],row['repetitions']) if row else (2.5,0,0)
        ef,iv,rp,due = sm2_update(ef,iv,rp,grade)
        # Phase 4D anti-farming: computed from the row as it existed BEFORE
        # this submission. Once true for a (user, question) pair, stays
        # true forever via progress_credited (see should_grant_review_progress).
        should_grant_progress = should_grant_review_progress(row, grade)
        progress_credited_flag = 1 if (should_grant_progress or (row and row.get('progress_credited'))) else 0
        conn.execute('''INSERT INTO srs_cards(user_id,question_id,ease_factor,interval,repetitions,due_date,last_grade,updated_at,progress_credited)
            VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(user_id,question_id) DO UPDATE SET
            ease_factor=excluded.ease_factor, interval=excluded.interval,
            repetitions=excluded.repetitions, due_date=excluded.due_date,
            last_grade=excluded.last_grade, updated_at=excluded.updated_at,
            progress_credited=GREATEST(srs_cards.progress_credited, excluded.progress_credited)''',
            (uid,qid,ef,iv,rp,due,grade,now,progress_credited_flag))

        # ── 每日詳細記錄 ────────────────────────────────────
        conn.execute(
            '''INSERT INTO review_log(
                   user_id,question_id,grade,topic,level,difficulty,reviewed_at,
                   response_ms,discipline,player_rating_snapshot,
                   question_rating_snapshot,item_rating_version,question_version,
                   source_context,is_scaffolding,training_set_id)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (uid, qid, grade,
             q_info.get('topic',''), q_info.get('level',''), q_info.get('difficulty',''),
             now, response_ms, q_info.get('discipline') or 'whole_board',
             player_rating_snapshot, question_rating_snapshot, ITEM_RATING_VERSION,
             str(q_info.get('source') or qid), source_context,
             1 if data.get('is_scaffolding') else 0, training_set_id)
        )
        if training_item:
            conn.execute(
                '''UPDATE premium_training_items SET
                     first_grade=COALESCE(first_grade,?),completed_grade=?,
                     completed_at=CASE WHEN ?>=3 THEN ? ELSE completed_at END
                   WHERE id=? AND completed_at IS NULL''',
                (grade, grade, grade, now, training_item['id'])
            )
            remaining = conn.execute(
                'SELECT COUNT(*) AS n FROM premium_training_items '
                'WHERE set_id=? AND completed_at IS NULL', (training_set_id,)
            ).fetchone()['n']
            if int(remaining or 0) == 0:
                conn.execute(
                    "UPDATE premium_training_sets SET status='completed',completed_at=? "
                    "WHERE id=? AND status='active'", (now, training_set_id)
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
        shield_used = False       # 連勝護盾（商城道具）本次是否觸發
        xp_potion_active = False  # XP 藥水（商城道具）本次是否生效
        pet_xp_added = 0          # 本次由棋靈夥伴帶來的額外 XP
        pet_xp_ratio = 0.0
        pet_xp_gained = 0         # 本次寵物實際獲得的 XP
        new_rank_level = rank_level
        # 裝備外觀加成
        _appear_fx = _get_appearance_effects(uid, conn)
        pet_row = conn.execute('SELECT * FROM user_pets WHERE user_id=?', (uid,)).fetchone()

        mrow = conn.execute(
            'SELECT * FROM mistake_log WHERE user_id=? AND question_id=?',(uid,qid)).fetchone()

        if grade >= 3:
            total, streak, mx, combo_streak, max_combo = _apply_credited_review_counters(
                total, streak, mx, combo_streak, max_combo, should_grant_progress)

            is_new  = not row   # 首次作答此題
            is_mc   = bool(mrow and mrow['wrong_count'] > 0)

            if should_grant_progress:
                diff = q_info.get('difficulty', '')
                xp_gain, combo_mult = calc_xp_gain(diff, combo_streak, is_new, is_mc)
                # 套用外觀 XP 加成（光環 / 袍服 / 配飾）
                if _appear_fx.get('xp_bonus', 0) > 0:
                    xp_gain = int(xp_gain * (1 + _appear_fx['xp_bonus']))
                # 棋靈夥伴 XP 加成（陪練）
                _pet_xp_b = _pet_player_xp_bonus(conn, uid, {'combo': combo_streak, 'is_mc': is_mc})
                if _pet_xp_b > 0:
                    _xp_before_pet = xp_gain
                    xp_gain = int(xp_gain * (1 + _pet_xp_b))
                    pet_xp_added = xp_gain - _xp_before_pet
                    pet_xp_ratio = _pet_xp_b
                # XP 藥水（商城道具）：30 分鐘內 ×1.5
                try:
                    _potion = _effect_get(conn, uid, 'xp_potion')
                    if _potion:
                        xp_gain = int(xp_gain * float(_potion['value'] or 1.5))
                        xp_potion_active = True
                except Exception:
                    pass
                xp      += xp_gain
                rank_xp += xp_gain
                if pet_row and _decayed_fullness(pet_row) > 0:
                    _pet_growth = _add_pet_xp(conn, uid, 1)
                    if _pet_growth:
                        pet_xp_gained = 1

            # LV 進度：以累計 xp 重新計算
            new_lv = xp_to_lv(xp)
            cur_lv = xp_to_lv(xp - xp_gain)
            new_rank_level = f'LV{new_lv}'
            _, rank_xp, _ = lv_progress(xp)
            if new_lv > cur_lv:
                ranked_up = True
        else:
            streak = 0
            # 連勝護盾：消耗一面護盾保住 combo（連擊加成不中斷）
            try:
                _sh = _effect_get(conn, uid, 'streak_shield')
                if _sh:
                    remaining = int(_sh['value'] or 1)
                    if remaining > 1:
                        conn.execute('UPDATE active_effects SET value=? WHERE id=? AND user_id=?',
                                     (remaining - 1, _sh['id'], uid))
                    else:
                        _effect_remove(conn, uid, _sh['id'])
                    shield_used = True
            except Exception:
                pass
            if not shield_used:
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
                # mistake_corrected feeds a badge threshold (check_and_award),
                # so -- like total_correct/streak/combo above -- only count
                # it once per question via should_grant_progress. The
                # mistake_log row's own correct_after counter above is left
                # as pure per-question analytics.
                if should_grant_progress:
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

        # Persist the core answer record before optional RPG systems run. This
        # keeps srs_cards/review_log/user_stats safe if a loot, quest, or
        # grimoire side-effect hits a PostgreSQL compatibility issue.
        conn.commit()

        monster_data = {}
        try:
            monster_data = _update_monster_and_quests(
                conn, uid, qid, grade, q_info, combo_streak,
                datetime.date.today().isoformat(),
                should_grant_progress=should_grant_progress,
            )
            conn.commit()
        except Exception:
            conn.rollback()
            app.logger.exception('optional monster/quest update failed after answer %s for user %s', qid, uid)

        # ── 同步法典純淨度 (grimoire_api 系統) ─────────────────────
        grimoire_id = q_info.get('grimoire_id')
        if grimoire_id:
            try:
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
                                             ELSE node_mastery.last_correct_at END,
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
            except Exception:
                conn.rollback()
                app.logger.exception('optional grimoire update failed after answer %s for user %s', qid, uid)

        pet_row = conn.execute('SELECT * FROM user_pets WHERE user_id=?', (uid,)).fetchone()

    return jsonify({
        'ok': True, 'ease_factor': ef, 'interval': iv, 'due_date': due,
        'new_badges': new_badges, 'stats': stats,
        'xp_gain': xp_gain, 'combo_mult': combo_mult,
        'pet_xp_added': pet_xp_added, 'pet_xp_ratio': pet_xp_ratio,
        'pet_xp_gained': pet_xp_gained,
        'combo_streak': combo_streak,
        'shield_used': shield_used,
        'xp_potion_active': xp_potion_active,
        'ranked_up': ranked_up,
        'new_rank_level': new_rank_level if ranked_up else None,
        'pet': _normalize_pet_row(pet_row),
        'practice': _pet_training_state(pet_row),
        'training': _pet_training_state(pet_row),
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

def _stage_reward(stage):
    """關卡委託獎勵：金幣 = 20 + (LV-1)*12，經驗 = 金幣 * 1.5。"""
    import re
    m = re.search(r'(\d+)', stage or '')
    lv = int(m.group(1)) if m else 1
    coins = 20 + (lv - 1) * 12
    xp = round(coins * 1.5)
    return coins, xp

def _stage_order(stage):
    m = re.search(r'(\d+)', stage or '')
    return int(m.group(1)) if m else 99

QUEST_SEGMENT_TARGET = 40
QUEST_SEGMENT_MIN = 30
QUEST_SEGMENT_MAX = 50

def _quest_group_key(q):
    disc = q.get('discipline') or 'whole_board'
    stage = q.get('stage') or 'LV2'
    return f'{disc}::{stage}'

def _quest_sort_key(q):
    return (
        q.get('sort_order') if q.get('sort_order') is not None else 10**9,
        q.get('map_id') or '',
        q.get('source') or '',
        q.get('id') or 0,
    )

def _quest_segment_sizes(total):
    if total <= 0:
        return []
    if total <= QUEST_SEGMENT_MAX:
        return [total]
    chunks = max(2, math.ceil(total / QUEST_SEGMENT_MAX))
    while chunks > 2 and total / chunks < QUEST_SEGMENT_MIN:
        chunks -= 1
    base, rem = divmod(total, chunks)
    return [base + (1 if i < rem else 0) for i in range(chunks)]

def _quest_segment_key(group_key, start, end):
    return f'{group_key}::{start + 1}-{end}'

def _parse_quest_key(key):
    parts = str(key or '').split('::')
    if len(parts) == 2:
        return parts[0], parts[1], None
    if len(parts) == 3:
        import re
        m = re.fullmatch(r'(\d+)-(\d+)', parts[2])
        if not m:
            return None
        start = max(0, int(m.group(1)) - 1)
        end = max(start + 1, int(m.group(2)))
        return parts[0], parts[1], (start, end)
    return None

def _quest_accessible_questions(premium):
    qs = []
    for q in _load_questions():
        if not q.get('enabled', True):
            continue
        if premium or question_is_free(q):
            qs.append(q)
    return qs

def _quest_grouped_questions(premium):
    groups = {}
    for q in _quest_accessible_questions(premium):
        groups.setdefault(_quest_group_key(q), []).append(q)
    for bucket in groups.values():
        bucket.sort(key=_quest_sort_key)
    return groups

def _quest_segments(premium):
    segments = {}
    for group_key, bucket in _quest_grouped_questions(premium).items():
        start = 0
        for idx, size in enumerate(_quest_segment_sizes(len(bucket)), start=1):
            end = min(len(bucket), start + size)
            seg_key = _quest_segment_key(group_key, start, end)
            disc, stage = group_key.split('::', 1)
            qids = [q['id'] for q in bucket[start:end]]
            coins, xp = _stage_reward(stage)
            scale = max(1.0, len(qids) / QUEST_SEGMENT_TARGET)
            segments[seg_key] = {
                'quest_key': seg_key,
                'legacy_key': group_key,
                'discipline': disc,
                'stage': stage,
                'segment_index': idx,
                'range_start': start + 1,
                'range_end': end,
                'total': len(qids),
                'question_ids': qids,
                'coins': max(coins, round(coins * scale)),
                'xp': max(xp, round(xp * scale)),
            }
            start = end
    return segments

def _quest_segment_for_key(key, premium):
    parsed = _parse_quest_key(key)
    if not parsed:
        return None
    disc, stage, rng = parsed
    group_key = f'{disc}::{stage}'
    bucket = _quest_grouped_questions(premium).get(group_key, [])
    if not bucket:
        return None
    if rng is None:
        qids = [q['id'] for q in bucket]
        coins, xp = _stage_reward(stage)
        return {
            'quest_key': group_key,
            'legacy_key': group_key,
            'discipline': disc,
            'stage': stage,
            'segment_index': None,
            'range_start': 1,
            'range_end': len(bucket),
            'total': len(bucket),
            'question_ids': qids,
            'coins': coins,
            'xp': xp,
        }
    start, end = rng
    start = min(start, len(bucket))
    end = min(end, len(bucket))
    if end <= start:
        return None
    qids = [q['id'] for q in bucket[start:end]]
    coins, xp = _stage_reward(stage)
    scale = max(1.0, len(qids) / QUEST_SEGMENT_TARGET)
    return {
        'quest_key': _quest_segment_key(group_key, start, end),
        'legacy_key': group_key,
        'discipline': disc,
        'stage': stage,
        'segment_index': None,
        'range_start': start + 1,
        'range_end': end,
        'total': len(qids),
        'question_ids': qids,
        'coins': max(coins, round(coins * scale)),
        'xp': max(xp, round(xp * scale)),
    }

def _quest_public_meta(seg, practiced_ids=None):
    practiced_ids = practiced_ids or set()
    qids = seg.get('question_ids') or []
    total = int(seg.get('total') or len(qids) or 0)
    practiced = sum(1 for qid in qids if qid in practiced_ids)
    href = (
        f"/?discipline={seg['discipline']}&stage={seg['stage']}"
        f"&quest={seg['quest_key']}&resume=1"
    )
    return {
        'quest_key': seg['quest_key'],
        'stage_key': seg['quest_key'],
        'legacy_key': seg['legacy_key'],
        'discipline': seg['discipline'],
        'stage': seg['stage'],
        'segment_index': seg.get('segment_index'),
        'range_start': seg.get('range_start'),
        'range_end': seg.get('range_end'),
        'total': total,
        'practiced': practiced,
        'coins': int(seg.get('coins') or 0),
        'xp': int(seg.get('xp') or 0),
        'href': href,
    }

def _stage_completion_state(uid, conn):
    """Return segmented guild quest progress; legacy whole-stage keys remain compatible."""
    premium = is_premium(uid)
    segments = _quest_segments(premium)
    rows = conn.execute('SELECT question_id FROM srs_cards WHERE user_id=?', (uid,)).fetchall()
    practiced_ids = {r['question_id'] for r in rows}
    completed = {
        key for key, seg in segments.items()
        if seg.get('question_ids') and all(qid in practiced_ids for qid in seg['question_ids'])
    }
    claimed_raw = {r['stage_key'] for r in
                   conn.execute('SELECT stage_key FROM reward_claimed WHERE user_id=?', (uid,)).fetchall()}
    claimed = set(claimed_raw)
    claimed_legacy = {k for k in claimed_raw if k.count('::') == 1}
    if claimed_legacy:
        for key, seg in segments.items():
            if seg.get('legacy_key') in claimed_legacy:
                claimed.add(key)
    return completed, claimed, segments, practiced_ids

@app.route('/api/quest-board')
@login_required
def quest_board_state():
    """佈告欄狀態（唯讀）：接取中的委託、可回報領賞的委託、錢包餘額。"""
    uid = session['user_id']
    with get_db() as conn:
        completed, claimed, segments, practiced_ids = _stage_completion_state(uid, conn)
        accepted = [r['quest_key'] for r in conn.execute(
            'SELECT quest_key FROM quest_accepted WHERE user_id=?', (uid,)).fetchall()]
        row = conn.execute('SELECT coins, xp FROM user_stats WHERE user_id=?', (uid,)).fetchone()
    claimable = [_quest_public_meta(segments[k], practiced_ids) for k in sorted(completed - claimed) if k in segments]
    accepted_set = set(accepted)
    claimed_or_done = set(completed) | set(claimed) | accepted_set
    open_quests = []
    seen_disc = set()
    for key, seg in sorted(segments.items(), key=lambda item: (
        _stage_order(item[1].get('stage')), item[1].get('discipline') or '', item[1].get('range_start') or 0
    )):
        if key in claimed_or_done:
            continue
        disc = seg.get('discipline') or ''
        if disc in seen_disc:
            continue
        open_quests.append(_quest_public_meta(seg, practiced_ids))
        seen_disc.add(disc)

    meta_keys = set(accepted) | {c['quest_key'] for c in claimable}
    quest_meta = []
    premium = is_premium(uid)
    for key in sorted(meta_keys):
        seg = segments.get(key) or _quest_segment_for_key(key, premium)
        if seg:
            quest_meta.append(_quest_public_meta(seg, practiced_ids))
    return jsonify({
        'accepted': accepted,
        'claimable': claimable,
        'open_quests': open_quests,
        'quest_meta': quest_meta,
        'coins': (row['coins'] if row else 0) or 0,
        'xp': (row['xp'] if row else 0) or 0,
    })

@app.route('/api/quest-board/accept', methods=['POST'])
@login_required
def quest_board_accept():
    uid = session['user_id']
    key = str((request.get_json(silent=True) or {}).get('quest_key', ''))
    if '::' not in key or len(key) > 120:
        return jsonify({'error': 'bad quest_key'}), 400
    now = datetime.datetime.now().isoformat()
    with get_db() as conn:
        conn.execute(
            'INSERT OR IGNORE INTO quest_accepted(user_id,quest_key,accepted_at) VALUES(?,?,?)',
            (uid, key, now))
        conn.commit()
    return jsonify({'ok': True})

@app.route('/api/quest-board/progress')
@login_required
def quest_board_progress():
    """Return authoritative progress and the next unpracticed question for one guild quest."""
    uid = session['user_id']
    key = str(request.args.get('quest_key') or '').strip()
    if '::' not in key or len(key) > 120:
        return jsonify({'error': 'bad quest_key'}), 400
    seg = _quest_segment_for_key(key, is_premium(uid))
    if not seg:
        return jsonify({'error': 'quest_not_found'}), 404
    qids = [int(qid) for qid in (seg.get('question_ids') or [])]
    practiced_ids = set()
    if qids:
        placeholders = ','.join('?' for _ in qids)
        with get_db() as conn:
            rows = conn.execute(
                f'SELECT question_id FROM srs_cards WHERE user_id=? AND question_id IN ({placeholders})',
                (uid, *qids)
            ).fetchall()
        practiced_ids = {int(row['question_id']) for row in rows}
    next_question_id = next((qid for qid in qids if qid not in practiced_ids), None)
    return jsonify({
        'ok': True,
        'quest_key': key,
        'practiced': len(practiced_ids),
        'total': len(qids),
        'completed': bool(qids) and next_question_id is None,
        'next_question_id': next_question_id,
    })

@app.route('/api/quest-board/abandon', methods=['POST'])
@login_required
def quest_board_abandon():
    uid = session['user_id']
    key = str((request.get_json(silent=True) or {}).get('quest_key', ''))
    with get_db() as conn:
        conn.execute('DELETE FROM quest_accepted WHERE user_id=? AND quest_key=?', (uid, key))
        conn.commit()
    return jsonify({'ok': True})

@app.route('/api/rewards/sync', methods=['POST'])
@login_required
def rewards_sync():
    """伺服器端重算已通關的學科×階段，對尚未發放者發金幣/經驗（一次性、防重練刷幣）。"""
    uid = session['user_id']
    now = datetime.datetime.now().isoformat()
    with get_db() as conn:
        completed, claimed, segments, practiced_ids = _stage_completion_state(uid, conn)
        new_keys = [k for k in completed if k not in claimed]

        granted = []; tot_c = tot_x = 0
        for k in new_keys:
            seg = segments.get(k)
            if not seg:
                continue
            c, x = int(seg.get('coins') or 0), int(seg.get('xp') or 0)
            conn.execute(
                'INSERT OR IGNORE INTO reward_claimed(user_id,stage_key,coins,xp,claimed_at) VALUES(?,?,?,?,?)',
                (uid, k, c, x, now))
            tot_c += c; tot_x += x
            granted.append(_quest_public_meta(seg, practiced_ids))
        if new_keys:
            conn.execute(
                'INSERT INTO user_stats(user_id,coins,xp,updated_at) VALUES(?,?,?,?) '
                'ON CONFLICT(user_id) DO UPDATE SET coins=user_stats.coins+?, xp=user_stats.xp+?, updated_at=?',
                (uid, tot_c, tot_x, now, tot_c, tot_x, now))
            # 已完成領賞的委託自動從接取清單移除
            for k in new_keys:
                conn.execute('DELETE FROM quest_accepted WHERE user_id=? AND quest_key=?', (uid, k))
        row = conn.execute('SELECT coins, xp FROM user_stats WHERE user_id=?', (uid,)).fetchone()
        conn.commit()

    return jsonify({
        'granted': granted,
        'gained_coins': tot_c, 'gained_xp': tot_x,
        'coins': (row['coins'] if row else 0),
        'xp': (row['xp'] if row else 0),
    })

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

@app.route('/api/stats/today-monsters')
@login_required
def stats_today_monsters():
    uid   = session.get('user_id')
    today = datetime.date.today().isoformat()
    with get_db() as conn:
        rows = conn.execute(
            'SELECT monster_type, monster_name, COUNT(*) AS kill_count '
            'FROM monster_kill_history '
            'WHERE user_id=? AND bf_date=? '
            'GROUP BY monster_type, monster_name '
            'ORDER BY kill_count DESC',
            (uid, today)
        ).fetchall()
    return jsonify([{
        'monster_type': r['monster_type'],
        'monster_name': r['monster_name'],
        'monster_name_en': _battlefield_name_en(r['monster_name']),
        'kill_count':   r['kill_count'],
        'image':        _battlefield_avatar(r['monster_type'], r['monster_name']),
    } for r in rows])

@app.route('/api/stats/daily')
@login_required
def stats_daily():
    """最近 N 天每日答題數，供首頁 streak dots 使用。"""
    uid  = session['user_id']
    days = min(int(request.args.get('days', 7)), 30)
    since = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    with get_db() as conn:
        rows = conn.execute(
            '''SELECT DATE(reviewed_at) as date, COUNT(*) as total,
                      SUM(CASE WHEN grade>=3 THEN 1 ELSE 0 END) as correct
               FROM review_log
               WHERE user_id=?
                 AND reviewed_at >= ?
               GROUP BY DATE(reviewed_at)
               ORDER BY date ASC''',
            (uid, since)
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
                'name_en':    q.get('name_en', q['name']),
                'icon':       q['icon'],
                'color':      q['color'],
                'desc':       q['desc'].format(target=q['target']),
                'desc_en':    q.get('desc_en', q['desc']).format(target=q['target']),
                'progress':   row['progress']    if row else 0,
                'target':     q['target'],
                'completed':  bool(row['completed']) if row else False,
                'xp':         q['xp'],
                'coins':      _COIN_ALL_QUESTS_BONUS if q.get('bonus') else _COIN_PER_DAILY_QUEST,
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

@app.route('/api/pet/status')
@login_required
def pet_status():
    uid = session['user_id']
    with get_db() as conn:
        pet_row = conn.execute('SELECT * FROM user_pets WHERE user_id=?', (uid,)).fetchone()
        inv_rows = conn.execute('SELECT item_key, qty FROM pet_inventory WHERE user_id=?', (uid,)).fetchall()
        collection_state = _pet_collection_state(conn, uid, pet_row['pet_key'] if pet_row else None)
        expedition_state = _pet_expedition_state(conn, pet_row)
    inv_map = {r['item_key']: r['qty'] for r in inv_rows}
    inventory = []
    for key, item in PET_FOOD_CATALOG.items():
        d = dict(item)
        d['qty'] = int(inv_map.get(key, 0) or 0)
        inventory.append(d)
    catalog = _pet_catalog_values() if pet_row else [PET_CATALOG[PET_STARTER_KEY]]
    return jsonify({
        'catalog': catalog,
        'food_catalog': list(PET_FOOD_CATALOG.values()),
        'pet': _normalize_pet_row(pet_row),
        'inventory': inventory,
        'interaction': _pet_interaction_state(pet_row),
        'training': _pet_training_state(pet_row),
        'expedition': expedition_state,
        'bonus': _pet_bonus_breakdown(pet_row),
        'collection': collection_state,
        'reward_sources': [
            {'name': '每日任務', 'name_en': 'Daily quests'},
            {'name': '錯題封印', 'name_en': 'Mistake sealing'},
            {'name': 'Boss / 關卡通關', 'name_en': 'Boss and chapter clears'},
        ],
    })

@app.route('/api/pet/choose', methods=['POST'])
@login_required
def pet_choose():
    uid = session['user_id']
    data = request.get_json(silent=True) or {}
    pet_key = (data.get('pet_key') or '').strip()
    if pet_key != PET_STARTER_KEY:
        return jsonify({'ok': False, 'error': '第一隻棋靈固定為墨滴水靈馬'}), 403
    if pet_key not in PET_CATALOG:
        return jsonify({'error': '未知的寵物'}), 400
    now = datetime.datetime.now().isoformat()
    with get_db() as conn:
        existing = conn.execute('SELECT * FROM user_pets WHERE user_id=?', (uid,)).fetchone()
        if existing:
            return jsonify({'ok': False, 'error': '已選擇寵物', 'pet': _normalize_pet_row(existing)}), 409
        conn.execute(
            'INSERT INTO user_pets(user_id,pet_key,nickname,selected_at,updated_at) VALUES(?,?,?,?,?)',
            (uid, pet_key, PET_CATALOG[pet_key]['name'], now, now)
        )
        _grant_pet_food(conn, uid, 'go_spirit_candy', 6)
        _grant_pet_food(conn, uid, 'starfruit', 1)
        conn.execute(
            'INSERT INTO pet_action_log(user_id,action,detail,created_at) VALUES(?,?,?,?)',
            (uid, 'choose', pet_key, now)
        )
        _pet_collection_sync_active(conn, uid)   # 同步進收藏表
        pet_row = conn.execute('SELECT * FROM user_pets WHERE user_id=?', (uid,)).fetchone()
        conn.commit()
    return jsonify({'ok': True, 'pet': _normalize_pet_row(pet_row), 'message': '寵物已加入你的旅程'})

@app.route('/api/pet/feed', methods=['POST'])
@login_required
def pet_feed():
    uid = session['user_id']
    data = request.get_json(silent=True) or {}
    item_key = (data.get('item_key') or 'go_spirit_candy').strip()
    if item_key not in PET_FOOD_CATALOG:
        return jsonify({'error': '未知的食物'}), 400
    item = PET_FOOD_CATALOG[item_key]
    now = datetime.datetime.now().isoformat()
    with get_db() as conn:
        pet = conn.execute('SELECT * FROM user_pets WHERE user_id=?', (uid,)).fetchone()
        if not pet:
            return jsonify({'error': '尚未選擇寵物'}), 400
        inv = conn.execute(
            'SELECT qty FROM pet_inventory WHERE user_id=? AND item_key=?',
            (uid, item_key)
        ).fetchone()
        if not inv or (inv['qty'] or 0) <= 0:
            return jsonify({'error': '食物不足'}), 400
        new_fullness = min(100, _decayed_fullness(pet) + item['fullness'])
        new_affection = min(100, (pet['affection'] or 0) + item['affection'])
        conn.execute(
            'UPDATE pet_inventory SET qty=qty-1 WHERE user_id=? AND item_key=?',
            (uid, item_key)
        )
        conn.execute(
            'UPDATE user_pets SET fullness=?, affection=?, last_fed_at=?, updated_at=? WHERE user_id=?',
            (new_fullness, new_affection, now, now, uid)
        )
        leveled = _add_pet_xp(conn, uid, item['xp'])
        conn.execute(
            'INSERT INTO pet_action_log(user_id,action,detail,created_at) VALUES(?,?,?,?)',
            (uid, 'feed', item_key, now)
        )
        _pet_collection_sync_active(conn, uid)
        pet_row = conn.execute('SELECT * FROM user_pets WHERE user_id=?', (uid,)).fetchone()
        inv_rows = conn.execute('SELECT item_key, qty FROM pet_inventory WHERE user_id=?', (uid,)).fetchall()
        conn.commit()
    inv_map = {r['item_key']: r['qty'] for r in inv_rows}
    return jsonify({
        'ok': True,
        'pet': _normalize_pet_row(pet_row),
        'inventory': [{**dict(v), 'qty': int(inv_map.get(k, 0) or 0)} for k, v in PET_FOOD_CATALOG.items()],
        'leveled': (leveled or {}).get('leveled', 0),
        'milestones': (leveled or {}).get('milestones', []),
        'message': '寵物吃飽了一點',
    })

@app.route('/api/pet/interact', methods=['POST'])
@login_required
def pet_interact():
    uid = session['user_id']
    data = request.get_json(silent=True) or {}
    mode = (data.get('mode') or 'pet').strip()
    try:
        hours = int(data.get('hours') or PET_EXPEDITION_DEFAULT_HOURS)
    except Exception:
        hours = PET_EXPEDITION_DEFAULT_HOURS
    if hours not in PET_EXPEDITION_ALLOWED_HOURS:
        hours = PET_EXPEDITION_DEFAULT_HOURS
    if mode not in ('pet', 'train'):
        return jsonify({'error': '未知的互動'}), 400
    now = datetime.datetime.now().isoformat()
    today = _pet_today_key()
    with get_db() as conn:
        pet = conn.execute('SELECT * FROM user_pets WHERE user_id=?', (uid,)).fetchone()
        if not pet:
            return jsonify({'error': '尚未選擇寵物'}), 400
        _eff_full = _decayed_fullness(pet)
        bond_today, train_xp_today = _pet_daily_counters(pet)
        bond_room = max(0, PET_DAILY_BOND_CAP - bond_today)

        if mode == 'pet':
            cd = _pet_cooldown_remaining(pet, 'last_pet_at', PET_PET_COOLDOWN_SEC)
            if cd > 0:
                return jsonify({'ok': False, 'cooldown': cd,
                                'pet': _normalize_pet_row(pet),
                                'interaction': _pet_interaction_state(pet),
                                'practice': _pet_training_state(pet),
                                'training': _pet_training_state(pet),
                                'expedition': _pet_expedition_state(conn, pet),
                                'message': '牠剛被拍拍過，正瞇著眼休息呢'})
            bond_gain = min(6, bond_room)
            xp_gain   = 3
            fullness  = _eff_full
            last_col  = 'last_pet_at'
            message   = '寵物開心地靠近了一點' if bond_gain > 0 else '牠很享受，但今天已經夠黏你了'
        else:  # train
            if _eff_full < 10:
                return jsonify({'error': '寵物有點餓，先餵牠再修行'}), 400
            train_cd = _pet_cooldown_remaining(pet, 'last_train_at', hours * 3600)
            if train_cd > 0:
                return jsonify({'ok': False, 'cooldown': train_cd,
                                'pet': _normalize_pet_row(pet),
                                'interaction': _pet_interaction_state(pet),
                                'practice': _pet_training_state(pet),
                                'training': _pet_training_state(pet),
                                'expedition': _pet_expedition_state(conn, pet),
                                'message': '修行還在進行中，先等等吧'})
            xp_room = max(0, PET_DAILY_TRAIN_XP_CAP - train_xp_today)
            if xp_room <= 0:
                return jsonify({'ok': False, 'capped': True,
                                'pet': _normalize_pet_row(pet),
                                'interaction': _pet_interaction_state(pet),
                                'practice': _pet_training_state(pet),
                                'training': _pet_training_state(pet),
                                'expedition': _pet_expedition_state(conn, pet),
                                'message': '今天的修行已經很充分了，明天再一起練吧'})
            mult      = 2 if hours >= 8 else 1
            xp_gain   = min(20 * mult, xp_room)
            bond_gain = min(3 * mult, bond_room)
            fullness  = max(0, _eff_full - 10 * mult)
            last_col  = 'last_train_at'
            message   = f'你們開始了 {hours} 小時修行'

        affection      = min(100, (pet['affection'] or 0) + bond_gain)
        new_bond       = bond_today + bond_gain
        new_train_xp   = train_xp_today + (xp_gain if mode == 'train' else 0)
        # last_col 僅取自上方常數，無注入風險
        conn.execute(
            f'UPDATE user_pets SET fullness=?, affection=?, last_interacted_at=?, '
            f'{last_col}=?, daily_key=?, daily_bond=?, daily_train_xp=?, updated_at=? '
            f'WHERE user_id=?',
            (fullness, affection, now, now, today, new_bond, new_train_xp, now, uid)
        )
        leveled = _add_pet_xp(conn, uid, xp_gain)
        conn.execute(
            'INSERT INTO pet_action_log(user_id,action,detail,created_at) VALUES(?,?,?,?)',
            (uid, mode, f'{hours}h' if mode == 'train' else str(xp_gain), now)
        )
        _pet_collection_sync_active(conn, uid)
        pet_row = conn.execute('SELECT * FROM user_pets WHERE user_id=?', (uid,)).fetchone()
        expedition_state = _pet_expedition_state(conn, pet_row)
        conn.commit()
    resp = {'ok': True, 'pet': _normalize_pet_row(pet_row),
            'leveled': (leveled or {}).get('leveled', 0),
            'milestones': (leveled or {}).get('milestones', []), 'message': message,
            'interaction': _pet_interaction_state(pet_row),
            'practice': _pet_training_state(pet_row),
            'training': _pet_training_state(pet_row),
            'expedition': expedition_state}
    if mode == 'pet':
        resp['cooldown'] = PET_PET_COOLDOWN_SEC
    elif mode == 'train':
        resp['cooldown'] = hours * 3600
    return jsonify(resp)

@app.route('/api/pet/rename', methods=['POST'])
@login_required
def pet_rename():
    uid = session['user_id']
    data = request.get_json(silent=True) or {}
    nickname = (data.get('nickname') or '').strip()
    if not nickname or len(nickname) > 16:
        return jsonify({'error': '名字需為 1-16 個字'}), 400
    now = datetime.datetime.now().isoformat()
    with get_db() as conn:
        pet = conn.execute('SELECT * FROM user_pets WHERE user_id=?', (uid,)).fetchone()
        if not pet:
            return jsonify({'error': '尚未選擇寵物'}), 400
        conn.execute('UPDATE user_pets SET nickname=?, updated_at=? WHERE user_id=?', (nickname, now, uid))
        conn.execute(
            'INSERT INTO pet_action_log(user_id,action,detail,created_at) VALUES(?,?,?,?)',
            (uid, 'rename', nickname, now)
        )
        _pet_collection_sync_active(conn, uid)
        pet_row = conn.execute('SELECT * FROM user_pets WHERE user_id=?', (uid,)).fetchone()
        conn.commit()
    return jsonify({'ok': True, 'pet': _normalize_pet_row(pet_row), 'message': '寵物名字已更新'})

@app.route('/api/pet/unlock', methods=['POST'])
@login_required
def pet_unlock():
    """以「現寵最高等級」解鎖並領取一隻新棋靈（加入收藏，不自動出戰）。"""
    uid = session['user_id']
    data = request.get_json(silent=True) or {}
    target = (data.get('pet_key') or '').strip()
    if target not in PET_CATALOG:
        return jsonify({'error': '未知的寵物'}), 400
    now = datetime.datetime.now().isoformat()
    with get_db() as conn:
        owned = _pet_owned_keys(conn, uid)
        if not owned:
            return jsonify({'error': '請先選擇第一隻棋靈'}), 400
        if target in owned:
            return jsonify({'ok': False, 'error': '已擁有此棋靈'}), 409
        expected = _next_pet_unlock_key(owned)
        if target != expected:
            return jsonify({'ok': False, 'error': '請依序解鎖棋靈',
                            'next_pet_key': expected}), 403
        max_level = _pet_max_owned_level(conn, uid)
        allowed = _pet_allowed_count(max_level)
        if len(owned) >= allowed:
            need = (PET_UNLOCK_THRESHOLDS[len(owned)]
                    if len(owned) < len(PET_UNLOCK_THRESHOLDS) else None)
            return jsonify({'ok': False, 'error': f'養到 LV{need} 才能解鎖下一隻棋靈',
                            'need_level': need}), 403
        conn.execute(
            'INSERT INTO pet_collection(user_id,pet_key,nickname,level,xp,fullness,affection,'
            'selected_at,daily_bond,daily_train_xp) VALUES(?,?,?,?,?,?,?,?,?,?)',
            (uid, target, PET_CATALOG[target]['name'], 1, 0, 60, 10, now, 0, 0)
        )
        _grant_pet_food(conn, uid, 'go_spirit_candy', 3)   # 新夥伴見面禮
        conn.execute(
            'INSERT INTO pet_action_log(user_id,action,detail,created_at) VALUES(?,?,?,?)',
            (uid, 'unlock', target, now)
        )
        pet_row = conn.execute('SELECT * FROM user_pets WHERE user_id=?', (uid,)).fetchone()
        collection_state = _pet_collection_state(conn, uid, pet_row['pet_key'] if pet_row else None)
        conn.commit()
    return jsonify({'ok': True, 'collection': collection_state,
                    'message': f'{PET_CATALOG[target]["name"]} 加入了你的棋靈收藏'})

@app.route('/api/pet/switch', methods=['POST'])
@login_required
def pet_switch():
    """切換出戰棋靈：把目前出戰的快照回收藏，再把目標載入 user_pets。"""
    uid = session['user_id']
    data = request.get_json(silent=True) or {}
    target = (data.get('pet_key') or '').strip()
    if target not in PET_CATALOG:
        return jsonify({'error': '未知的寵物'}), 400
    now = datetime.datetime.now().isoformat()
    with get_db() as conn:
        active = conn.execute('SELECT * FROM user_pets WHERE user_id=?', (uid,)).fetchone()
        if not active:
            return jsonify({'error': '尚未選擇寵物'}), 400
        if active['pet_key'] == target:
            return jsonify({'ok': True, 'pet': _normalize_pet_row(active),
                            'message': '已是出戰中的棋靈'})
        owned = conn.execute(
            'SELECT * FROM pet_collection WHERE user_id=? AND pet_key=?', (uid, target)
        ).fetchone()
        if not owned:
            return jsonify({'ok': False, 'error': '尚未擁有此棋靈'}), 403
        _pet_collection_sync_active(conn, uid)   # 先存回目前出戰的最新數值
        conn.execute(
            'UPDATE user_pets SET pet_key=?, nickname=?, level=?, xp=?, fullness=?, affection=?, '
            'selected_at=?, last_fed_at=?, last_interacted_at=?, last_pet_at=?, last_train_at=?, '
            'daily_key=?, daily_bond=?, daily_train_xp=?, updated_at=? WHERE user_id=?',
            (target, owned['nickname'], owned['level'], owned['xp'], owned['fullness'],
             owned['affection'], owned['selected_at'], owned['last_fed_at'],
             owned['last_interacted_at'], owned['last_pet_at'], owned['last_train_at'],
             owned['daily_key'], owned['daily_bond'], owned['daily_train_xp'], now, uid)
        )
        conn.execute(
            'INSERT INTO pet_action_log(user_id,action,detail,created_at) VALUES(?,?,?,?)',
            (uid, 'switch', target, now)
        )
        pet_row = conn.execute('SELECT * FROM user_pets WHERE user_id=?', (uid,)).fetchone()
        collection_state = _pet_collection_state(conn, uid, target)
        conn.commit()
    return jsonify({'ok': True, 'pet': _normalize_pet_row(pet_row),
                    'collection': collection_state,
                    'message': f'{PET_CATALOG[target]["name"]} 出戰！'})

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
        heatmap = {str(r['day']): {'total': r['total'], 'correct': r['correct']} for r in heatmap_rows}

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
               HAVING COUNT(*) >= 3
               ORDER BY (SUM(CASE WHEN grade>=3 THEN 1 ELSE 0 END) * 1.0 / COUNT(*)) ASC
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
               HAVING COUNT(*) >= 3''',
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
                           'topic_en':_english_only(_i18n_topic_en(q.get('topic','')) or q.get('topic_en')),
                           'level_en':_english_only(_i18n_level_en(q.get('level','')) or q.get('level_en')),
                           'difficulty':q.get('difficulty',''),
                           'rank':q.get('rank') or q.get('difficulty',''),
                           'display_name':_question_display_name(q),
                           'display_name_en':_question_display_name_en(q),
                           'source':q.get('source',''),
                           'content':q.get('content','')})
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
        removed = conn.execute(
            'DELETE FROM mistake_log WHERE user_id=? AND question_id=?',
            (uid, qid)
        ).rowcount
        # 先 commit DELETE，確保刪除不受後續獎勵操作失敗影響
        conn.commit()
    return jsonify({'ok': True})

# ══════════════════════════════════════════════════════════════
# Badges API
# ══════════════════════════════════════════════════════════════

@app.route('/api/badges/definitions')
@login_required
def badge_definitions():
    defs = []
    for b in BADGE_DEFS:
        d  = dict(b)   # 完整複製（含 premium_only）
        en = _i18n_badge_en(d['id'])
        if en:
            d['name_en'] = en[0]
            d['desc_en'] = en[1]
        defs.append(d)
    qs   = _load_questions()
    for u in {group_label(q) for q in qs}:
        u_en = _i18n_topic_en(u) or _i18n_level_en(u) or u
        defs.append({'id':'unit_'+u.replace(' ','_'),'name':f'完成《{u}》','name_en':f'Complete "{u_en}"',
                     'icon':'📖','desc':f'完成單元「{u}」的所有題目','desc_en':f'Complete all problems in "{u_en}"',
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
        'topic_en':       _english_only(_i18n_topic_en(q.get('topic', '')) or q.get('topic_en')),
        'level':          q.get('level', ''),
        'level_en':       _english_only(_i18n_level_en(q.get('level', '')) or q.get('level_en')),
        'difficulty':     q.get('difficulty', ''),
        'rank':           q.get('rank', ''),
        'note':           dc.get('note'),
        'xp_reward':      DAILY_CHALLENGE_XP_REWARD,
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

        xp_awarded = DAILY_CHALLENGE_XP_REWARD if correct else 0
        if xp_awarded:
            row = conn.execute(
                'SELECT xp FROM user_stats WHERE user_id=?',
                (uid,)
            ).fetchone()
            total_xp = ((row['xp'] or 0) if row else 0) + xp_awarded
            new_rank_level = f'LV{xp_to_lv(total_xp)}'
            _, rank_xp, _ = lv_progress(total_xp)
            conn.execute(
                '''INSERT INTO user_stats(user_id,xp,rank_xp,rank_level,updated_at)
                   VALUES(?,?,?,?,?)
                   ON CONFLICT(user_id) DO UPDATE SET
                     xp=?,
                     rank_xp=?,
                     rank_level=?,
                     updated_at=?''',
                (uid, total_xp, rank_xp, new_rank_level, now,
                 total_xp, rank_xp, new_rank_level, now)
            )

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

    try:
        import shadow_judging
        if shadow_judging.is_enabled():
            qs_map = {q['id']: q for q in _load_questions()}
            shadow_q = qs_map.get(dc['question_id'], {})
            shadow_judging.observe_answer_route(
                entry_point='daily_challenge',
                question_id=dc['question_id'],
                session_id=f'daily:{uid}:{today}',
                transform_idx=0,
                sgf_transformed=shadow_q.get('content', ''),
                moves=data.get('moves') if isinstance(data.get('moves'), list) else None,
                client_correct=bool(data.get('correct')),
                final_correct=bool(correct),
                katago_best_move=shadow_q.get('katago_best_move', ''),
            )
    except Exception:
        app.logger.exception('[shadow] observe failed (ignored)')

    defs_map   = {b['id']: b for b in BADGE_DEFS}
    new_badges = []
    for bid in new_badge_ids:
        if bid not in defs_map:
            continue
        badge = dict(defs_map[bid])
        badge_en = _i18n_badge_en(bid)
        if badge_en:
            badge['name_en'], badge['desc_en'] = badge_en
        new_badges.append(badge)
    new_appear_items = [_APPEAR_MAP[i] for i in new_appear_ids if i in _APPEAR_MAP]

    return jsonify({
        'ok': True,
        'stats': {
            'total':    total_p,
            'correct':  correct_p,
            'accuracy': round(correct_p / (total_p or 1) * 100),
            'rank':     rank,
        },
        'xp_awarded':          xp_awarded,
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
        ensure_premium_rewards(uid, conn, equip_default=False)
        eq_row = conn.execute(
            'SELECT * FROM player_appearance WHERE user_id=?', (uid,)
        ).fetchone()
        wardrobe_rows = conn.execute(
            'SELECT item_id, obtained_at, source FROM player_wardrobe'
            ' WHERE user_id=? ORDER BY obtained_at DESC',
            (uid,)
        ).fetchall()

    equipped = {
        col: (eq_row[col] if eq_row else None)
        for col in APPEARANCE_EQUIP_COLUMNS
    }

    wardrobe = []
    for r in wardrobe_rows:
        item = _APPEAR_MAP.get(r['item_id'])
        if not item:
            continue
        slot_key = item['slot'] + '_id'
        w = {
            **item,
            'obtained_at': r['obtained_at'],
            'source':      r['source'],
            'is_equipped': equipped.get(slot_key) == item['id'],
        }
        if item.get('slot') == 'title':
            _ten = _i18n_title_en(item['id'])
            if _ten:
                w['nameEn'], w['flavorEn'], w['hintEn'] = _ten
        wardrobe.append(w)

    _ekeys = eq_row.keys() if eq_row else []
    return jsonify({
        'equipped': equipped,
        'wardrobe': wardrobe,
        'character_key': (eq_row['character_key'] if eq_row and 'character_key' in _ekeys else None),
        'combat_armor':   (eq_row['combat_armor']   if eq_row and 'combat_armor'   in _ekeys else None) or '',
        'combat_cape':    (eq_row['combat_cape']    if eq_row and 'combat_cape'    in _ekeys else None) or '',
        'combat_weapon':  (eq_row['combat_weapon']  if eq_row and 'combat_weapon'  in _ekeys else None) or '',
        'combat_offhand': (eq_row['combat_offhand'] if eq_row and 'combat_offhand' in _ekeys else None) or '',
        'stone_skin':    (eq_row['stone_skin']    if eq_row and 'stone_skin'    in _ekeys else None) or '',
        'board_skin':    (eq_row['board_skin']    if eq_row and 'board_skin'    in _ekeys else None) or '',
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
        for col in APPEARANCE_EQUIP_COLUMNS:
            if eq_row[col]:
                equipped_ids.add(eq_row[col])

    by_slot = {slot: [] for slot in APPEARANCE_SLOT_KEYS}
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
        ensure_premium_rewards(uid, conn, equip_default=False)
        owned = {r['item_id'] for r in conn.execute(
            'SELECT item_id FROM player_wardrobe WHERE user_id=?', (uid,)
        ).fetchall()}
        eq_row = conn.execute(
            'SELECT * FROM player_appearance WHERE user_id=?', (uid,)
        ).fetchone()

    equipped_ids = set()
    if eq_row:
        for col in APPEARANCE_EQUIP_COLUMNS:
            if eq_row[col]:
                equipped_ids.add(eq_row[col])

    result = []
    for item in APPEARANCE_DEFS:
        public_item = {
            **item,
            'owned':       item['id'] in owned,
            'is_equipped': item['id'] in equipped_ids,
        }
        if item.get('slot') == 'title':
            title_en = _i18n_title_en(item['id'])
            if title_en:
                public_item['nameEn'], public_item['flavorEn'], public_item['hintEn'] = title_en
        result.append(public_item)

    return jsonify(result)


# ══════════════════════════════════════════════════════════════
# 副稱號成就解鎖（Phase 2）：達成條件即發放進 player_wardrobe（永久）
# ══════════════════════════════════════════════════════════════
def _go_strength(go_rank):
    """棋力數值化：kyu n→30-n（30k=0…1k=29）；dan d→30+d（1d=31…）。"""
    import re
    mt = re.match(r'^(\d+)\s*([kd])', str(go_rank or '').strip().lower())
    if not mt:
        return 0
    n = int(mt.group(1))
    return 30 + n if mt.group(2) == 'd' else 30 - n

# {title_id: (達成判定(metrics)->bool, 成就說明)}
TITLE_ACHIEVEMENTS = {
    'title_beginner':     (lambda m: m['total_correct']    >= 1,    '答對第 1 題'),
    'title_scholar':      (lambda m: m['mistake_corrected'] >= 50,  '錯題訂正達 50 題'),
    'title_wanderer':     (lambda m: m['units_done']       >= 5,    '完成 5 個單元'),
    'title_streak':       (lambda m: m['max_streak']       >= 15,   '最高連勝達 15'),
    'title_foxwit':       (lambda m: m['challenge_wins']   >= 25,   '完成每日懸賞令累積 25 場'),
    'title_master':       (lambda m: m['total_correct']    >= 1000, '累積答對 1000 題'),
    'title_dragonslayer': (lambda m: m['dragon_kills']     >= 100,  '擊敗 100 條龍'),
    'title_godshand':     (lambda m: m['total_answered'] >= 300 and m['precision'] >= 90, '答題≥300 且精準率≥90%'),
    'title_celestial':    (lambda m: m['strength'] >= _go_strength('5d'), '段位達 5d'),
    'title_eternity':     (lambda m: m['total_correct']    >= 5000, '累積答對 5000 題'),
}

def _compute_title_metrics(uid, conn):
    st = conn.execute(
        'SELECT total_correct, mistake_corrected, max_streak, challenge_wins, go_rank '
        'FROM user_stats WHERE user_id=?', (uid,)).fetchone()
    units   = conn.execute('SELECT COUNT(*) AS n FROM unit_progress WHERE user_id=? AND completed_at IS NOT NULL', (uid,)).fetchone()
    answered = conn.execute('SELECT COUNT(*) AS n FROM review_log WHERE user_id=?', (uid,)).fetchone()
    dragon  = conn.execute("SELECT COALESCE(SUM(kill_count),0) AS n FROM monster_kill_log WHERE user_id=? AND monster_type='dragon'", (uid,)).fetchone()
    tc = (st['total_correct'] if st else 0) or 0
    ta = (answered['n'] if answered else 0) or 0
    return {
        'total_correct':    tc,
        'mistake_corrected': (st['mistake_corrected'] if st else 0) or 0,
        'max_streak':       (st['max_streak']       if st else 0) or 0,
        'challenge_wins':   (st['challenge_wins']   if st else 0) or 0,
        'units_done':       (units['n']  if units  else 0) or 0,
        'total_answered':   ta,
        'precision':        round(tc / ta * 100) if ta else 0,
        'dragon_kills':     (dragon['n'] if dragon else 0) or 0,
        'strength':         _go_strength(st['go_rank'] if st else '30k'),
        'go_rank':          (st['go_rank'] if st and st['go_rank'] else '30k'),
    }

def _grant_earned_titles(uid, conn):
    """達成成就的副稱號發放進衣櫃（冪等）。回傳本次新發放的 title id 清單。"""
    m = _compute_title_metrics(uid, conn)
    owned = {r['item_id'] for r in conn.execute(
        'SELECT item_id FROM player_wardrobe WHERE user_id=?', (uid,)).fetchall()}
    now = datetime.datetime.now().isoformat()
    newly = []
    for tid, (pred, _hint) in TITLE_ACHIEVEMENTS.items():
        if tid in owned:
            continue
        try:
            if pred(m):
                conn.execute(
                    'INSERT OR IGNORE INTO player_wardrobe(user_id,item_id,obtained_at,source) VALUES(?,?,?,?)',
                    (uid, tid, now, 'achievement'))
                newly.append(tid)
        except Exception:
            pass
    return newly


# ══════════════════════════════════════════════════════════════
# 解鎖伺服器端驗證（鏡像 hero.html 的解鎖規則；防止偽造請求裝未解鎖物品）
#   - 純外觀（角色/棋子/棋盤皮膚）：里程碑 + Premium 7折 + 最高階專屬
#   - 戰鬥裝備/配件：段位階（rankToTier）
# ══════════════════════════════════════════════════════════════
def _rank_to_tier(go_rank):
    """段位→解鎖階（與 hero.html rankToTier 一致）。kyu→1~6；dan→7~10。"""
    import re, math
    m = re.match(r'^(\d+)\s*([kd])', str(go_rank or '').strip().lower())
    if not m:
        return 0
    n = int(m.group(1))
    if m.group(2) == 'd':
        return min(10, 6 + math.ceil(n / 2))
    return min(6, max(1, math.ceil((31 - min(30, n)) / 5)))

# 純外觀解鎖表（鏡像 hero.html COSMETIC_UNLOCKS）：None=預設可用；'premium'=訂閱專屬；(metric,gte)=里程碑
# 2026-06 收緊：里程碑改月級目標（原值 ×5~×10）
_COSMETIC_UNLOCKS = {
    'character': {
        'apprentice': None, 'apprentice_girl': None,
        'swordsman': ('units_done', 5), 'rogue': ('total_correct', 1000),
        'ranger': ('max_streak', 25), 'berserker': ('units_done', 15),
        'guardian': ('strength', _go_strength('10k')), 'paladin': ('strength', _go_strength('5k')),
        'mage': ('strength', _go_strength('1k')), 'sage': 'premium',
    },
    'stone': {
        '': None, 'classic': None, 'jade': ('units_done', 5),
        'marble': ('total_correct', 3000), 'cosmic': ('strength', _go_strength('3k')),
        'radiant': 'premium',
    },
    'board': {
        '': None, 'classic': None, 'jade': ('total_correct', 2000),
        'marble': ('challenge_wins', 50), 'cosmic': ('strength', _go_strength('5k')),
        'radiant': 'premium',
    },
}

# 數值裝備雙門檻：tier → 所需累積答對（鏡像 hero.html GEAR_CORRECT_GATES）
_GEAR_CORRECT_GATES = [0, 0, 200, 500, 1000, 2000, 3500, 5000, 7000, 10000, 15000]

def _cosmetic_unlocked(group, key, metrics, is_prem):
    import math
    tbl = _COSMETIC_UNLOCKS.get(group, {})
    if key not in tbl:
        return False                      # 未知 key → 鎖定
    cond = tbl[key]
    if cond is None:
        return True                       # 預設可用
    if cond == 'premium':
        return bool(is_prem)              # 最高階：訂閱專屬
    metric, gte = cond
    gate = math.ceil(gte * 0.7) if is_prem else gte   # Premium 里程碑 7 折
    return (metrics.get(metric, 0) or 0) >= gate

def _gear_unlocked(key, rank_tier, total_correct=0):
    """戰鬥裝備/配件雙門檻驗證：段位階 + 累積答對（防棋力測驗空降全開）。
    key 如 'weapon_t7'；預設值(cloth/none/'')→階0→永遠可用（允許卸下）。"""
    m = re.search(r'_t(\d+)$', key or '')
    tier = int(m.group(1)) if m else 0
    if tier > rank_tier:
        return False
    gate = _GEAR_CORRECT_GATES[tier] if tier < len(_GEAR_CORRECT_GATES) else _GEAR_CORRECT_GATES[-1]
    return (total_correct or 0) >= gate


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
        ensure_premium_rewards(uid, conn, equip_default=False)
        # ── 基本統計 ──────────────────────────────────────────────
        stats = conn.execute(
            'SELECT xp, rank_level, rank_xp, go_rank, '
            'attr_atk, attr_def, attr_vis, attr_prec, '
            'total_correct, max_streak, challenge_wins FROM user_stats WHERE user_id=?',
            (uid,)
        ).fetchone()
        # 里程碑用：完成單元數（completed_at 不為空 = 已完成）
        _units_done = conn.execute(
            'SELECT COUNT(*) AS n FROM unit_progress WHERE user_id=? AND completed_at IS NOT NULL',
            (uid,)
        ).fetchone()
        units_done = (_units_done['n'] if _units_done else 0) or 0
        elo_row = conn.execute(
            'SELECT elo_rating, elo_provisional FROM users WHERE id=?', (uid,)
        ).fetchone()
        username = session.get('username', '—')
        nickname = session.get('nickname', '')
        total_xp   = stats['xp']      if stats else 0
        go_rank    = (stats['go_rank'] if stats and stats['go_rank'] else '30k')
        lv, lv_xp, lv_xp_next = lv_progress(total_xp)
        rank_level = f'LV{lv}'

        # ── 副稱號成就解鎖：先發放已達成的稱號，再讀衣櫃 ──────────
        _newly_titles = _grant_earned_titles(uid, conn)

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
            wardrobe_item = {
                'id':       item['id'],
                'name':     item.get('name', item['id']),
                'icon':     item.get('emoji', item.get('icon', '❓')),
                'type':     item.get('slot', ''),
                'rarity':   item.get('rarity', 'common'),
                'color':    item.get('color', ''),
                # 副稱號：用成就條件當提示（單一來源），其餘維持原 hint
                'hint':     (TITLE_ACHIEVEMENTS[item['id']][1]
                             if item['id'] in TITLE_ACHIEVEMENTS else item.get('hint', '')),
                'effects':  APPEARANCE_EFFECTS.get(item['id'], {}),
                'owned':    item['id'] in owned_ids,
                'equipped': item['id'] in equipped_ids,
            }
            if item.get('slot') == 'title':
                title_en = _i18n_title_en(item['id'])
                if title_en:
                    wardrobe_item['nameEn'], _, wardrobe_item['hintEn'] = title_en
            wardrobe.append(wardrobe_item)

        # ── equipped_labels（角色面板小標） ───────────────────────
        equipped_labels = [
            _APPEAR_MAP[eid].get('name', eid)
            for eid in equipped_ids
            if eid in _APPEAR_MAP
        ]

        # ── 稱號：自動稱號(主) + 可收集稱號(副，玩家自選) ──────────
        _atk  = (stats['attr_atk']  or 0) if stats else 0
        _def  = (stats['attr_def']  or 0) if stats else 0
        _vis  = (stats['attr_vis']  or 0) if stats else 0
        _prec = (stats['attr_prec'] or 0) if stats else 0
        auto_title = get_auto_title(_atk, _def, _vis, _prec)
        _title_id = eq_row['title_id'] if (eq_row and 'title_id' in eq_cols) else None
        equipped_title = (_APPEAR_MAP[_title_id].get('name', _title_id)
                          if _title_id and _title_id in _APPEAR_MAP else None)
        _eq_title_en = _i18n_title_en(_title_id) if _title_id else None
        equipped_title_en = _eq_title_en[0] if _eq_title_en else equipped_title

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

    # new_unlock flag（一次性，讀完即清除）；本次新解鎖副稱號也觸發提示
    new_unlock = session.pop('new_unlock', False) or bool(_newly_titles)

    return jsonify({
        'username':       username,
        'nickname':       nickname,
        'display_name':   _user_display_label(nickname=nickname, username=username),
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
        'auto_title':      auto_title,       # 主稱號（依四屬性動態）
        'auto_title_en':   auto_title_en(auto_title),  # 英文版（前端 i18n）
        'equipped_title':  equipped_title,   # 副稱號（玩家自選可收集稱號）
        'equipped_title_en': equipped_title_en,  # 副稱號英文（前端 i18n）
        'stone_skin':      (eq_row['stone_skin'] if eq_row and 'stone_skin' in eq_cols else None) or '',
        'board_skin':      (eq_row['board_skin'] if eq_row and 'board_skin' in eq_cols else None) or '',
        # 純外觀里程碑解鎖用的累積數據
        'milestones': {
            'total_correct':  (stats['total_correct']  if stats else 0) or 0,
            'max_streak':     (stats['max_streak']     if stats else 0) or 0,
            'challenge_wins': (stats['challenge_wins'] if stats else 0) or 0,
            'units_done':     units_done,
            'go_rank':        go_rank,
        },
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
        'elo_provisional':   bool(elo_row['elo_provisional']) if elo_row else False,
    })


VALID_CHARACTER_KEYS = {
    # 新角色（含兩位見習生）
    'apprentice', 'apprentice_girl', 'swordsman', 'rogue', 'ranger', 'berserker',
    'guardian', 'paladin', 'mage', 'sage',
    # 舊 key 相容
    'hero_male', 'woman', 'boy_child', 'girl_child', 'elder_master', 'elder_woman',
}

@app.route('/api/skills/character', methods=['POST'])
@login_required
def skills_character():
    """儲存玩家選的全身角色基座到 player_appearance。Body: { "character_key": "hero_male" }"""
    uid  = session['user_id']
    data = request.get_json() or {}
    ckey = (data.get('character_key') or '').strip()
    if ckey not in VALID_CHARACTER_KEYS:
        return jsonify({'error': 'invalid character_key'}), 400

    # 戰鬥裝備四件＋配件（可選；只更新「有送來」的欄位，避免只送 character_key 的呼叫把裝備清掉）
    def _clean(v):
        v = (v or '').strip()
        return v[:24]
    combat_in = {}
    for col in ('combat_armor', 'combat_weapon', 'combat_cape', 'combat_offhand',
                'combat_hat', 'combat_pet', 'combat_aura', 'combat_acc'):
        if col in data:
            combat_in[col] = _clean(data.get(col))

    is_prem = is_premium(uid)
    now = datetime.datetime.now().isoformat()
    with get_db() as conn:
        # ── 解鎖驗證（伺服器端權威）：未解鎖的欄位靜默丟棄，保留其他有效變更 ──
        metrics   = _compute_title_metrics(uid, conn)
        rank_tier = _rank_to_tier(metrics.get('go_rank'))
        char_ok   = _cosmetic_unlocked('character', ckey, metrics, is_prem)
        combat_fields = [(c, v) for c, v in combat_in.items()
                         if _gear_unlocked(v, rank_tier, metrics.get('total_correct', 0))]   # 段位/累積答對未到 → 丟棄
        rejected = ([] if char_ok else ['character']) + \
                   [c for c in combat_in if c not in dict(combat_fields)]

        existing = conn.execute(
            'SELECT user_id FROM player_appearance WHERE user_id=?', (uid,)
        ).fetchone()
        if existing:
            sets, vals = ['updated_at=?'], [now]
            if char_ok:
                sets.insert(0, 'character_key=?'); vals.insert(0, ckey)
            for col, v in combat_fields:
                sets.append(f'{col}=?'); vals.append(v)
            vals.append(uid)
            conn.execute(
                f"UPDATE player_appearance SET {', '.join(sets)} WHERE user_id=?", vals)
        else:
            eff_char = ckey if char_ok else 'apprentice'   # 新列且角色未解鎖 → 退回預設
            cols = ['user_id', 'character_key', 'updated_at'] + [c for c, _ in combat_fields]
            vals = [uid, eff_char, now] + [v for _, v in combat_fields]
            ph = ','.join('?' * len(cols))
            conn.execute(
                f"INSERT INTO player_appearance({','.join(cols)}) VALUES({ph})", vals)
    return jsonify({'ok': True, 'rejected': rejected})


# ── 棋子皮膚 ─────────────────────────────────────────────────────────
STONE_SKINS = {
    'classic': {'name': '經典',   'rarity': 'common'},
    'jade':    {'name': '翡翠',   'rarity': 'uncommon'},
    'marble':  {'name': '大理石', 'rarity': 'rare'},
    'cosmic':  {'name': '星空',   'rarity': 'epic'},
    'radiant': {'name': '神聖',   'rarity': 'legendary'},
}

@app.route('/api/skills/stone_skin', methods=['POST'])
@login_required
def skills_stone_skin():
    """儲存玩家選的棋子皮膚。Body: { "stone_skin": "jade" }（空字串=預設）"""
    uid  = session['user_id']
    data = request.get_json() or {}
    skin = (data.get('stone_skin') or '').strip()
    if skin and skin not in STONE_SKINS:
        return jsonify({'error': 'invalid stone_skin'}), 400
    is_prem = is_premium(uid)
    now = datetime.datetime.now().isoformat()
    with get_db() as conn:
        # 解鎖驗證（伺服器端權威）
        if not _cosmetic_unlocked('stone', skin, _compute_title_metrics(uid, conn), is_prem):
            return jsonify({'error': 'locked', 'detail': '尚未解鎖此棋子皮膚'}), 403
        existing = conn.execute(
            'SELECT user_id FROM player_appearance WHERE user_id=?', (uid,)).fetchone()
        if existing:
            conn.execute(
                'UPDATE player_appearance SET stone_skin=?, updated_at=? WHERE user_id=?',
                (skin, now, uid))
        else:
            conn.execute(
                'INSERT INTO player_appearance(user_id, stone_skin, updated_at) VALUES(?,?,?)',
                (uid, skin, now))
    return jsonify({'ok': True})


# ── 棋盤皮膚 ─────────────────────────────────────────────────────────
BOARD_SKINS = {
    'classic': {'name': '經典',   'rarity': 'common'},
    'jade':    {'name': '翡翠',   'rarity': 'uncommon'},
    'marble':  {'name': '大理石', 'rarity': 'rare'},
    'cosmic':  {'name': '星空',   'rarity': 'epic'},
    'radiant': {'name': '神聖',   'rarity': 'legendary'},
}

@app.route('/api/skills/board_skin', methods=['POST'])
@login_required
def skills_board_skin():
    """儲存玩家選的棋盤皮膚。Body: { "board_skin": "jade" }（空字串=預設）"""
    uid  = session['user_id']
    data = request.get_json() or {}
    skin = (data.get('board_skin') or '').strip()
    if skin and skin not in BOARD_SKINS:
        return jsonify({'error': 'invalid board_skin'}), 400
    is_prem = is_premium(uid)
    now = datetime.datetime.now().isoformat()
    with get_db() as conn:
        # 解鎖驗證（伺服器端權威）
        if not _cosmetic_unlocked('board', skin, _compute_title_metrics(uid, conn), is_prem):
            return jsonify({'error': 'locked', 'detail': '尚未解鎖此棋盤皮膚'}), 403
        existing = conn.execute(
            'SELECT user_id FROM player_appearance WHERE user_id=?', (uid,)).fetchone()
        if existing:
            conn.execute(
                'UPDATE player_appearance SET board_skin=?, updated_at=? WHERE user_id=?',
                (skin, now, uid))
        else:
            conn.execute(
                'INSERT INTO player_appearance(user_id, board_skin, updated_at) VALUES(?,?,?)',
                (uid, skin, now))
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
               GROUP BY u.id, us.xp, us.rank_level, us.max_combo
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

def _row_loadout(r):
    """從查詢列取出角色+裝備+配件 loadout（供社群小卡疊圖）。"""
    ks = r.keys()
    def g(c): return (r[c] if c in ks else '') or ''
    return {
        'character_key':  g('character_key') or None,
        'combat_armor':   g('combat_armor'),  'combat_weapon':  g('combat_weapon'),
        'combat_cape':    g('combat_cape'),   'combat_offhand': g('combat_offhand'),
        'combat_hat':     g('combat_hat'),    'combat_pet':     g('combat_pet'),
        'combat_aura':    g('combat_aura'),
        'is_premium':     1 if ('is_premium' in ks and r['is_premium']) else 0,
    }

def _community_leaderboard_period_bounds_iso(board_type, now=None):
    """Naive-UTC ISO timestamps for the current community leaderboard
    scoring period in Taiwan time, returned as
    (period_start_iso, period_end_exclusive_iso)."""
    _TW = datetime.timezone(datetime.timedelta(hours=8))
    today = (now.astimezone(_TW) if now else datetime.datetime.now(_TW)).date()
    if board_type == 'weekly':
        anchor = today - datetime.timedelta(days=today.weekday())
        end_anchor = anchor + datetime.timedelta(days=7)
    elif board_type == 'monthly':
        anchor = today.replace(day=1)
        end_anchor = (anchor.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
    else:
        raise ValueError(f"unsupported community leaderboard board_type: {board_type!r}")
    start_local = datetime.datetime.combine(anchor, datetime.time.min, tzinfo=_TW)
    end_local = datetime.datetime.combine(end_anchor, datetime.time.min, tzinfo=_TW)
    return (
        start_local.astimezone(datetime.timezone.utc).replace(tzinfo=None).isoformat(),
        end_local.astimezone(datetime.timezone.utc).replace(tzinfo=None).isoformat(),
    )


def _community_leaderboard_period_start_iso(board_type, now=None):
    return _community_leaderboard_period_bounds_iso(board_type, now=now)[0]


def _fetch_community_leaderboard_score_rows(conn, period_start_iso, period_end_iso=None):
    from community_leaderboard_rewards import (
        fetch_leaderboard_participant_rows,
        rank_leaderboard_participants,
    )
    participants = fetch_leaderboard_participant_rows(
        conn, period_start_iso, period_end_iso, limit=None)
    ranked = rank_leaderboard_participants(participants)
    return ranked[:50]


@app.route('/api/community/leaderboard')
@login_required
def community_leaderboard():
    uid   = session['user_id']
    with get_db() as conn:

        # ── 週排行：本週答對次數（台灣時區週一 00:00 起）──
        weekly_start_iso, weekly_end_iso = _community_leaderboard_period_bounds_iso('weekly')
        weekly_rows = _fetch_community_leaderboard_score_rows(
            conn, weekly_start_iso, weekly_end_iso)

        # ── 月排行：本月答對次數（台灣時區當月 1 日 00:00 起）──
        monthly_start_iso, monthly_end_iso = _community_leaderboard_period_bounds_iso('monthly')
        monthly_rows = _fetch_community_leaderboard_score_rows(
            conn, monthly_start_iso, monthly_end_iso)

        # ── 總排行：累計 XP ──
        alltime_rows = conn.execute("""
            SELECT u.id, u.username, COALESCE(u.nickname,u.username) AS display_name,
                   s.xp AS score, s.rank_level AS rank_level,
                   s.total_correct, s.max_combo,
                   COALESCE(pa.character_key,'') AS character_key, COALESCE(pa.combat_armor,'') AS combat_armor, COALESCE(pa.combat_weapon,'') AS combat_weapon, COALESCE(pa.combat_cape,'') AS combat_cape, COALESCE(pa.combat_offhand,'') AS combat_offhand, COALESCE(pa.combat_hat,'') AS combat_hat, COALESCE(pa.combat_pet,'') AS combat_pet, COALESCE(pa.combat_aura,'') AS combat_aura, CASE WHEN u.plan='premium' THEN 1 ELSE 0 END AS is_premium
            FROM user_stats s
            JOIN users u ON u.id = s.user_id
            LEFT JOIN player_appearance pa ON pa.user_id = u.id
            ORDER BY s.xp DESC LIMIT 50
        """).fetchall()

        # ── 段位排行 ──
        rank_rows = conn.execute("""
            SELECT u.id, u.username, COALESCE(u.nickname,u.username) AS display_name,
                   s.rank_level, s.rank_xp, s.xp AS score,
                   COALESCE(pa.character_key,'') AS character_key, COALESCE(pa.combat_armor,'') AS combat_armor, COALESCE(pa.combat_weapon,'') AS combat_weapon, COALESCE(pa.combat_cape,'') AS combat_cape, COALESCE(pa.combat_offhand,'') AS combat_offhand, COALESCE(pa.combat_hat,'') AS combat_hat, COALESCE(pa.combat_pet,'') AS combat_pet, COALESCE(pa.combat_aura,'') AS combat_aura, CASE WHEN u.plan='premium' THEN 1 ELSE 0 END AS is_premium
            FROM user_stats s
            JOIN users u ON u.id = s.user_id
            LEFT JOIN player_appearance pa ON pa.user_id = u.id
            ORDER BY s.xp DESC
            LIMIT 50
        """).fetchall()

        # ── 連勝排行：最高 combo ──
        combo_rows = conn.execute("""
            SELECT u.id, u.username, COALESCE(u.nickname,u.username) AS display_name,
                   s.max_combo AS score, COALESCE(s.rank_level,'LV1') AS rank_level,
                   COALESCE(pa.character_key,'') AS character_key, COALESCE(pa.combat_armor,'') AS combat_armor, COALESCE(pa.combat_weapon,'') AS combat_weapon, COALESCE(pa.combat_cape,'') AS combat_cape, COALESCE(pa.combat_offhand,'') AS combat_offhand, COALESCE(pa.combat_hat,'') AS combat_hat, COALESCE(pa.combat_pet,'') AS combat_pet, COALESCE(pa.combat_aura,'') AS combat_aura, CASE WHEN u.plan='premium' THEN 1 ELSE 0 END AS is_premium
            FROM user_stats s
            JOIN users u ON u.id = s.user_id
            LEFT JOIN player_appearance pa ON pa.user_id = u.id
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
                   s.total_correct, s.max_combo,
                   COALESCE(pa.character_key,'') AS character_key, COALESCE(pa.combat_armor,'') AS combat_armor, COALESCE(pa.combat_weapon,'') AS combat_weapon, COALESCE(pa.combat_cape,'') AS combat_cape, COALESCE(pa.combat_offhand,'') AS combat_offhand, COALESCE(pa.combat_hat,'') AS combat_hat, COALESCE(pa.combat_pet,'') AS combat_pet, COALESCE(pa.combat_aura,'') AS combat_aura, CASE WHEN u.plan='premium' THEN 1 ELSE 0 END AS is_premium
            FROM user_stats s JOIN users u ON u.id = s.user_id
            LEFT JOIN player_appearance pa ON pa.user_id = u.id
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
                **_row_loadout(r),
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


# ── Phase 4A: community leaderboard reward notifications ───────────────
#
# Read-only fetch + a single acknowledgement write. Never issues a
# reward, never changes claim status, never touches the reward payload
# -- rewards are already granted by the separate, narrowly-gated manual
# grant-commit tooling (see community_leaderboard_rewards.py). This is
# purely "let the player see and dismiss what they already received."

@app.route('/api/community/leaderboard/reward-notifications')
@login_required
def community_leaderboard_reward_notifications():
    from community_leaderboard_rewards import (
        fetch_unacknowledged_granted_reward_claims, build_reward_notification_payload,
    )
    uid = session['user_id']
    with get_db() as conn:
        claims = fetch_unacknowledged_granted_reward_claims(conn, uid)
    notifications = [build_reward_notification_payload(c) for c in claims]
    return jsonify({'ok': True, 'notifications': notifications})


@app.route('/api/community/leaderboard/reward-notifications/<int:claim_id>/ack', methods=['POST'])
@login_required
def community_leaderboard_reward_notification_ack(claim_id):
    from community_leaderboard_rewards import acknowledge_reward_notification
    uid = session['user_id']
    with get_db() as conn:
        acked = acknowledge_reward_notification(conn, claim_id, uid)
    if not acked:
        return jsonify({'ok': False, 'error': 'claim_not_found_or_not_granted'}), 404
    return jsonify({'ok': True})


# ── Phase 4B: leaderboard reward rules (read-only, structured) ─────────
#
# Pure display data -- never grants anything, never touches a claim, and
# is not sensitive per-user data (it's the same policy for every
# player), but gated behind login for consistency with every other
# /api/community/leaderboard* route.

@app.route('/api/community/leaderboard/reward-rules')
@login_required
def community_leaderboard_reward_rules():
    from community_leaderboard_rewards import get_weekly_leaderboard_reward_rules
    return jsonify({'ok': True, 'rules': {'weekly': get_weekly_leaderboard_reward_rules()}})


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
    with get_db() as conn:
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


@app.route('/api/profile/<username>/games')
def public_profile_games(username):
    """公開棋譜清單 — 任何人都能查看該玩家的對弈記錄。"""
    page  = max(1, int(request.args.get('page', 1)))
    limit = 20
    offset = (page - 1) * limit
    with get_db() as conn:
        user = conn.execute(
            'SELECT id FROM users WHERE LOWER(username)=LOWER(?)', (username,)
        ).fetchone()
        if not user:
            return jsonify({'error': 'user not found'}), 404
        uid = user['id']
        total = conn.execute(
            'SELECT COUNT(*) FROM game_records WHERE user_id=?', (uid,)
        ).fetchone()[0]
        rows = conn.execute(
            '''SELECT id, opponent_name, my_color, result, reason,
                      move_count, board_size, komi, go_rank, played_at
               FROM game_records WHERE user_id=?
               ORDER BY played_at DESC LIMIT ? OFFSET ?''',
            (uid, limit, offset)
        ).fetchall()
    return jsonify({
        'total': total, 'page': page, 'pages': max(1, -(-total // limit)),
        'games': [{
            'id':            r['id'],
            'opponent_name': r['opponent_name'],
            'my_color':      r['my_color'],
            'result':        r['result'],
            'reason':        r['reason'],
            'move_count':    r['move_count'],
            'board_size':    r['board_size'],
            'komi':          r['komi'],
            'go_rank':       r['go_rank'],
            'played_at':     (r['played_at'] or '')[:16].replace('T', ' '),
        } for r in rows],
    })

@app.route('/api/profile/<username>/games/<int:record_id>/sgf')
def public_profile_game_sgf(username, record_id):
    """公開 SGF — 預設回傳純文字供播放器使用；?download=1 觸發下載。"""
    with get_db() as conn:
        user = conn.execute(
            'SELECT id FROM users WHERE LOWER(username)=LOWER(?)', (username,)
        ).fetchone()
        if not user:
            return jsonify({'error': 'user not found'}), 404
        row = conn.execute(
            'SELECT sgf, played_at FROM game_records WHERE id=? AND user_id=?',
            (record_id, user['id'])
        ).fetchone()
    if not row or not row['sgf']:
        return jsonify({'error': '找不到棋譜'}), 404
    from flask import Response
    if request.args.get('download'):
        date_str = (row['played_at'] or '')[:10].replace('-', '')
        return Response(row['sgf'], mimetype='application/x-go-sgf', headers={
            'Content-Disposition': f'attachment; filename="go-odyssey-{date_str}-{record_id}.sgf"'})
    return Response(row['sgf'], mimetype='text/plain; charset=utf-8')

@app.route('/api/profile/<username>')
def public_profile(username):
    """公開個人檔案 API — 任何人都能查看。"""
    with get_db() as conn:

        user = conn.execute(
            'SELECT id, username, nickname, created_at FROM users WHERE LOWER(username)=LOWER(?)',
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
                    'name_en':   (_i18n_badge_en(bd['id']) or ('', ''))[0],
                    'desc_en':   (_i18n_badge_en(bd['id']) or ('', ''))[1],
                    'earned_at': (br['earned_at'] or '')[:10],
                })

        # ── 角色外觀 ──
        eq_row = conn.execute(
            'SELECT character_key FROM player_appearance WHERE user_id=?', (uid,)
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
        with get_db() as conn2:
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
        'display_name':   _user_display_label(nickname=nickname, username=user['username']),
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
        'character_key':  (eq_row['character_key'] if eq_row else None) or None,
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
        trow = conn.execute('SELECT id FROM users WHERE LOWER(username)=LOWER(?)', (target,)).fetchone()
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
        trow = conn.execute('SELECT id FROM users WHERE LOWER(username)=LOWER(?)', (username,)).fetchone()
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
        rows = conn.execute('''
            SELECT f.id, f.from_user, f.created_at,
                   u.username, COALESCE(u.nickname, u.username) AS display_name,
                   s.rank_level, s.xp,
                   COALESCE(pa.character_key,'') AS character_key, COALESCE(pa.combat_armor,'') AS combat_armor, COALESCE(pa.combat_weapon,'') AS combat_weapon, COALESCE(pa.combat_cape,'') AS combat_cape, COALESCE(pa.combat_offhand,'') AS combat_offhand, COALESCE(pa.combat_hat,'') AS combat_hat, COALESCE(pa.combat_pet,'') AS combat_pet, COALESCE(pa.combat_aura,'') AS combat_aura, CASE WHEN u.plan='premium' THEN 1 ELSE 0 END AS is_premium
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
            **_row_loadout(r),
            'created_at': r['created_at'],
        })
    return jsonify({'requests': result, 'count': len(result)})


@app.route('/api/friends/list')
@login_required
def friend_list():
    """取得好友列表 + 好友動態。"""
    uid = session['user_id']
    with get_db() as conn:

        # ── 好友列表（含統計）──
        friends = conn.execute('''
            SELECT u.id, u.username, COALESCE(u.nickname, u.username) AS display_name,
                   f.id AS friendship_id,
                   s.xp, s.rank_level, s.total_correct, s.max_combo,
                   s.current_streak, s.combo_streak,
                   COALESCE(pa.character_key,'') AS character_key, COALESCE(pa.combat_armor,'') AS combat_armor, COALESCE(pa.combat_weapon,'') AS combat_weapon, COALESCE(pa.combat_cape,'') AS combat_cape, COALESCE(pa.combat_offhand,'') AS combat_offhand, COALESCE(pa.combat_hat,'') AS combat_hat, COALESCE(pa.combat_pet,'') AS combat_pet, COALESCE(pa.combat_aura,'') AS combat_aura,
                   (SELECT MAX(DATE(rl.reviewed_at)) FROM review_log rl WHERE rl.user_id=u.id) AS last_active
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
                **_row_loadout(r),
                'last_active': r['last_active'] or '',
            })

        # ── 好友動態（多種事件類型）──
        friend_only = [f for f in fids if f != uid]
        if not friend_only:
            friend_only = [0]   # dummy
        ph2 = ','.join('?' * len(friend_only))

        feed = []

        # 1) 每日答題摘要（按用戶+日期聚合，最近 7 天）
        daily_rows = conn.execute('''
            SELECT r.user_id,
                   DATE(r.reviewed_at::timestamp) AS day,
                   COUNT(*) AS total,
                   SUM(CASE WHEN r.grade >= 3 THEN 1 ELSE 0 END) AS correct,
                   MAX(r.reviewed_at) AS last_at,
                   MAX(u.username) AS username, COALESCE(MAX(u.nickname), MAX(u.username)) AS display_name,
                   COALESCE(MAX(pa.character_key),'') AS character_key, COALESCE(MAX(pa.combat_armor),'') AS combat_armor, COALESCE(MAX(pa.combat_weapon),'') AS combat_weapon, COALESCE(MAX(pa.combat_cape),'') AS combat_cape, COALESCE(MAX(pa.combat_offhand),'') AS combat_offhand, COALESCE(MAX(pa.combat_hat),'') AS combat_hat, COALESCE(MAX(pa.combat_pet),'') AS combat_pet, COALESCE(MAX(pa.combat_aura),'') AS combat_aura, MAX(CASE WHEN u.plan='premium' THEN 1 ELSE 0 END) AS is_premium
            FROM review_log r
            JOIN users u ON u.id = r.user_id
            LEFT JOIN player_appearance pa ON pa.user_id = r.user_id
            WHERE r.user_id IN ({ph2})
              AND r.reviewed_at::timestamp >= CURRENT_DATE - INTERVAL '7 days'
            GROUP BY r.user_id, DATE(r.reviewed_at::timestamp)
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
                **_row_loadout(a),
            })

        # 2) 獲得新徽章
        badge_map = {b['id']: b for b in BADGE_DEFS}
        badge_rows = conn.execute('''
            SELECT be.user_id, be.badge_id, be.earned_at,
                   u.username, COALESCE(u.nickname, u.username) AS display_name,
                   COALESCE(pa.character_key,'') AS character_key, COALESCE(pa.combat_armor,'') AS combat_armor, COALESCE(pa.combat_weapon,'') AS combat_weapon, COALESCE(pa.combat_cape,'') AS combat_cape, COALESCE(pa.combat_offhand,'') AS combat_offhand, COALESCE(pa.combat_hat,'') AS combat_hat, COALESCE(pa.combat_pet,'') AS combat_pet, COALESCE(pa.combat_aura,'') AS combat_aura, CASE WHEN u.plan='premium' THEN 1 ELSE 0 END AS is_premium
            FROM badges_earned be
            JOIN users u ON u.id = be.user_id
            LEFT JOIN player_appearance pa ON pa.user_id = be.user_id
            WHERE be.user_id IN ({ph2})
              AND be.earned_at::timestamp >= CURRENT_DATE - INTERVAL '30 days'
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
                'badge_name_en': (_i18n_badge_en(bd['id']) or ('', ''))[0],
                'badge_icon': bd['icon'],
                'badge_desc': bd['desc'],
                'badge_desc_en': (_i18n_badge_en(bd['id']) or ('', ''))[1],
                'created_at': b['earned_at'],
                **_row_loadout(b),
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
#  好友私訊 API
# ═══════════════════════════════════════════════════════════════

DM_MAX_LEN = 500
DM_RATE_MAX = 5
DM_RATE_WINDOW_SEC = 10
DM_RETENTION_DAYS = max(1, int(os.environ.get('DM_RETENTION_DAYS', '180')))
DM_AUDIT_RETENTION_DAYS = max(1, int(os.environ.get('DM_AUDIT_RETENTION_DAYS', '365')))
DM_DEFAULT_BADWORDS = (
    '幹你娘', '操你媽', '你媽死', '去死', '白痴', '智障', '低能', '廢物', '垃圾',
    '約炮', '裸照', '色情', '性交', '強姦', '強暴', '援交',
    '殺了你', '打死你', '弄死你',
    'fuck', 'shit', 'bitch', 'porn', 'nude', 'sext', 'kill yourself',
)
DM_EXTRA_BADWORDS = tuple(
    word.strip() for word in os.environ.get('DM_BADWORDS', '').replace('\n', ',').split(',')
    if word.strip()
)
DM_BADWORDS = tuple(dict.fromkeys(DM_DEFAULT_BADWORDS + DM_EXTRA_BADWORDS))
_dm_cleanup_lock = threading.Lock()
_dm_cleanup_last = 0.0


def _dm_are_friends(conn, uid_a, uid_b):
    return conn.execute('''
        SELECT 1 FROM friendships
        WHERE status='accepted'
          AND ((from_user=? AND to_user=?) OR (from_user=? AND to_user=?))
    ''', (uid_a, uid_b, uid_b, uid_a)).fetchone() is not None


def _dm_block_state(conn, uid_a, uid_b):
    rows = conn.execute('''
        SELECT blocker_id, blocked_id FROM dm_blocks
        WHERE (blocker_id=? AND blocked_id=?) OR (blocker_id=? AND blocked_id=?)
    ''', (uid_a, uid_b, uid_b, uid_a)).fetchall()
    return {
        'blocked_by_me': any(r['blocker_id'] == uid_a for r in rows),
        'blocked_by_them': any(r['blocker_id'] == uid_b for r in rows),
        'blocked': bool(rows),
    }


def _dm_thread_for_member(conn, thread_id, uid):
    return conn.execute('''
        SELECT * FROM dm_threads
        WHERE id=? AND (user_lo=? OR user_hi=?)
    ''', (thread_id, uid, uid)).fetchone()


def _dm_get_or_create_thread(conn, uid_a, uid_b, now):
    user_lo, user_hi = sorted((uid_a, uid_b))
    return conn.execute('''
        INSERT INTO dm_threads(user_lo,user_hi,created_at)
        VALUES(?,?,?)
        ON CONFLICT (user_lo,user_hi)
        DO UPDATE SET user_lo=EXCLUDED.user_lo
        RETURNING id
    ''', (user_lo, user_hi, now)).fetchone()['id']


def _dm_clean_text(raw_text):
    text = str(raw_text or '').strip()
    if not text:
        return None, '訊息不能為空白'
    if len(text) > DM_MAX_LEN:
        return None, f'訊息最多 {DM_MAX_LEN} 字'
    if re.search(r'(?i)(?:https?://|www\.|\b[a-z0-9.-]+\.(?:com|net|org|tw|io)\b)', text):
        return None, '私訊目前不開放傳送網址'
    compact_digits = re.sub(r'[^0-9]', '', text)
    if len(compact_digits) >= 8 and re.search(r'(?:\+?886|0)?9\d{8}|0\d{8,9}', compact_digits):
        return None, '私訊目前不開放傳送電話號碼'
    for word in DM_BADWORDS:
        pattern = re.escape(word)
        if word.isascii() and word.replace(' ', '').isalnum():
            pattern = rf'\b{pattern}\b'
        text = re.sub(pattern, '*' * min(len(word), 6), text, flags=re.IGNORECASE)
    return text, None


def _dm_maybe_cleanup(force=False):
    """低頻清除過期私訊；open 檢舉保留到結案。"""
    global _dm_cleanup_last
    now_mono = time.monotonic()
    if not force and now_mono - _dm_cleanup_last < 21600:
        return False
    if not _dm_cleanup_lock.acquire(blocking=False):
        return False
    try:
        now_dt = datetime.datetime.now()
        message_cutoff = (now_dt - datetime.timedelta(days=DM_RETENTION_DAYS)).isoformat()
        audit_cutoff = (now_dt - datetime.timedelta(days=DM_AUDIT_RETENTION_DAYS)).isoformat()
        with get_db() as conn:
            conn.execute('''
                DELETE FROM dm_messages m
                WHERE m.created_at<?
                  AND NOT EXISTS(
                      SELECT 1 FROM dm_reports rp
                      WHERE rp.message_id=m.id AND rp.status='open'
                  )
            ''', (message_cutoff,))
            conn.execute('''
                UPDATE dm_threads t
                SET last_msg_id=(SELECT m.id FROM dm_messages m
                                 WHERE m.thread_id=t.id ORDER BY m.id DESC LIMIT 1),
                    last_at=(SELECT m.created_at FROM dm_messages m
                             WHERE m.thread_id=t.id ORDER BY m.id DESC LIMIT 1)
                WHERE t.last_msg_id IS NULL
                   OR NOT EXISTS(SELECT 1 FROM dm_messages m WHERE m.id=t.last_msg_id)
            ''')
            conn.execute('''
                DELETE FROM dm_threads t
                WHERE NOT EXISTS(SELECT 1 FROM dm_messages m WHERE m.thread_id=t.id)
            ''')
            conn.execute('DELETE FROM dm_admin_audit WHERE created_at<?', (audit_cutoff,))
        _dm_cleanup_last = now_mono
        return True
    finally:
        _dm_cleanup_lock.release()


def _dm_audit(conn, admin_id, action, report_id=None, thread_id=None,
              message_id=None, reason=None):
    conn.execute('''
        INSERT INTO dm_admin_audit
            (admin_id,action,report_id,thread_id,message_id,reason,created_at)
        VALUES(?,?,?,?,?,?,?)
    ''', (admin_id, action, report_id, thread_id, message_id,
          (reason or '')[:500] or None, datetime.datetime.now().isoformat()))


def _question_alt_report_audit(conn, admin_id, action, report_id=None, detail=None):
    conn.execute('''
        INSERT INTO question_alt_report_audit
            (report_id,admin_id,action,detail,created_at)
        VALUES(?,?,?,?,?)
    ''', (report_id, admin_id, action, (detail or '')[:500] or None,
          datetime.datetime.now().isoformat()))


def _review_queue_now_iso():
    return _now_iso()


def _get_questions_json_commit():
    for env_name in ('QUESTIONS_JSON_COMMIT', 'GIT_COMMIT', 'SOURCE_VERSION',
                     'BUILD_SOURCEVERSION', 'GITHUB_SHA', 'CI_COMMIT_SHA'):
        value = str(os.environ.get(env_name) or '').strip()
        if value:
            return value
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        value = subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'],
            cwd=base_dir,
            text=True,
            encoding='utf-8',
            errors='replace',
        ).strip()
        return value or 'unknown'
    except Exception:
        return 'unknown'


def _find_question_records_by_legacy_id(question_id, questions=None):
    qs = questions if questions is not None else _load_questions_fresh()
    matches = []
    for record_index, q in enumerate(qs):
        if q.get('id') != question_id:
            continue
        matches.append({
            'record_index': record_index,
            'legacy_question_id': q.get('id'),
            'source_path': q.get('source'),
            'content': q.get('content'),
            'content_sha256': _question_content_sha256(q),
            'enabled': bool(q.get('enabled', True)),
            'record': q,
        })
    return matches


def _get_question_record_by_index(record_index, *, questions=None, expected_legacy_question_id=None):
    qs = questions if questions is not None else _load_questions_fresh()
    try:
        record_index = int(record_index)
    except (TypeError, ValueError) as error:
        raise ValueError('record_index must be an integer') from error
    if record_index < 0 or record_index >= len(qs):
        raise ValueError('record_index out of range')
    q = qs[record_index]
    if expected_legacy_question_id is not None and q.get('id') != expected_legacy_question_id:
        raise ValueError('record_index does not match legacy_question_id')
    return {
        'record_index': record_index,
        'legacy_question_id': q.get('id'),
        'source_path': q.get('source'),
        'content': q.get('content'),
        'content_sha256': _question_content_sha256(q),
        'enabled': bool(q.get('enabled', True)),
        'record': q,
    }


def _review_queue_audit(conn, admin_id, target_type, action, target_id=None, detail=None):
    conn.execute('''
        INSERT INTO review_queue_audit
            (target_type, target_id, admin_id, action, detail, created_at)
        VALUES(?,?,?,?,?,?)
    ''', (target_type, target_id, admin_id, action, (detail or '')[:500] or None,
          _review_queue_now_iso()))


def _split_markdown_row(line):
    return [cell.strip() for cell in line.strip().strip('|').split('|')]


def _parse_review_queue_import_candidates(markdown_text):
    lines = markdown_text.splitlines()
    rows = []
    i = 0
    while i < len(lines) - 1:
        header_line = lines[i].strip()
        separator_line = lines[i + 1].strip()
        if not header_line.startswith('|') or not separator_line.startswith('|'):
            i += 1
            continue
        if '---' not in separator_line or 'record_index' not in header_line:
            i += 1
            continue
        headers = _split_markdown_row(header_line)
        if 'record_index' not in headers or 'legacy_question_id' not in headers:
            i += 1
            continue
        i += 2
        while i < len(lines):
            row_line = lines[i].strip()
            if not row_line.startswith('|'):
                break
            cells = _split_markdown_row(row_line)
            if len(cells) == len(headers):
                rows.append(dict(zip(headers, cells)))
            i += 1
    deduped = {}
    duplicate_rows = 0
    for row in rows:
        try:
            record_index = int(str(row.get('record_index') or '').strip())
        except (TypeError, ValueError):
            continue
        normalized = {
            'record_index': record_index,
            'legacy_question_id': str(row.get('legacy_question_id') or '').strip(),
            'source_path': str(row.get('source_path') or '').strip() or None,
            'parse_error_class': str(row.get('parse_error_class') or '').strip() or None,
            'classification': str(row.get('classification') or '').strip() or None,
            'failure_excerpt': str(row.get('failure_excerpt') or '').strip() or None,
            'suspected_property': str(row.get('suspected_property') or '').strip() or None,
            'candidate_span_count': str(row.get('candidate_span_count') or '').strip() or None,
            'chosen_span_index': str(row.get('chosen_span_index') or '').strip() or None,
            'span_contains_move_node': str(row.get('span_contains_move_node') or '').strip() or None,
        }
        existing = deduped.get(record_index)
        if existing is None:
            deduped[record_index] = normalized
            continue
        duplicate_rows += 1
        deduped[record_index] = normalized
    return [deduped[k] for k in sorted(deduped)], len(rows), duplicate_rows


def _build_question_payload(record):
    return {
        'record_index': record['record_index'],
        'legacy_question_id': record['legacy_question_id'],
        'source_path': record['source_path'],
        'content_sha256': record['content_sha256'],
        'enabled': record['enabled'],
        'content': record['content'],
    }


def _build_duplicate_candidates(question_id, questions=None):
    return [
        {
            'record_index': row['record_index'],
            'source_path': row['source_path'],
            'content_sha256': row['content_sha256'],
            'enabled': row['enabled'],
        }
        for row in _find_question_records_by_legacy_id(question_id, questions=questions)
    ]


def _current_queue_item_state(row, questions=None):
    qs = questions if questions is not None else _load_questions_fresh()
    current = _get_question_record_by_index(
        row['record_index'],
        questions=qs,
        expected_legacy_question_id=row['legacy_question_id'],
    )
    current_sha = current['content_sha256']
    stored_sha = row.get('content_sha256')
    is_stale = stored_sha is not None and current_sha is not None and current_sha != stored_sha
    return current, current_sha, stored_sha, is_stale


def _question_problem_report_to_payload(report, *, questions=None):
    qs = questions if questions is not None else _load_questions_fresh()
    candidates = _build_duplicate_candidates(report['question_id'], questions=qs)
    unique_record = None
    if len(candidates) == 1:
        try:
            unique_record = _get_question_record_by_index(
                candidates[0]['record_index'],
                questions=qs,
                expected_legacy_question_id=report['question_id'],
            )
        except Exception:
            unique_record = None
    payload = {
        'id': report['id'],
        'user_id': report['user_id'],
        'question_id': report['question_id'],
        'reason_code': report['reason_code'],
        'note': report['note'],
        'status': report['status'],
        'admin_note': report['admin_note'],
        'reviewed_by': report['reviewed_by'],
        'created_at': report['created_at'],
        'reviewed_at': report['reviewed_at'],
        'duplicate_candidate_count': len(candidates),
        'duplicate_candidates': candidates,
        'selected_record_index': unique_record['record_index'] if unique_record else None,
        'selected_question': _build_question_payload(unique_record) if unique_record else None,
    }
    payload['question'] = payload['selected_question']
    return payload


def _review_queue_row_to_payload(row, *, questions=None):
    qs = questions if questions is not None else _load_questions_fresh()
    try:
        current, current_sha, stored_sha, is_stale = _current_queue_item_state(row, qs)
    except Exception as error:
        current = None
        current_sha = None
        stored_sha = row.get('content_sha256')
        is_stale = True
        stale_reason = str(error)
    else:
        stale_reason = 'content_sha256_changed' if is_stale else None
    return {
        'id': row['id'],
        'source_type': row['source_type'],
        'source_ref': row['source_ref'],
        'record_index': row['record_index'],
        'legacy_question_id': row['legacy_question_id'],
        'source_path': row['source_path'],
        'content_sha256': row['content_sha256'],
        'current_content_sha256': current_sha,
        'questions_json_commit': row['questions_json_commit'],
        'reason': row['reason'],
        'source_batch': row['source_batch'],
        'status': row['status'],
        'resolution_action': row['resolution_action'],
        'admin_note': row['admin_note'],
        'reviewed_by': row['reviewed_by'],
        'created_at': row['created_at'],
        'reviewed_at': row['reviewed_at'],
        'is_stale': is_stale,
        'stale_reason': stale_reason,
        'current_question': _build_question_payload(current) if current else None,
        'question': _build_question_payload(current) if current else None,
    }


def _parse_queue_resolution_action(data):
    action = str(data.get('action') or data.get('resolution_action') or '').strip()
    if not action:
        return None
    if action not in REVIEW_QUEUE_RESOLUTION_ACTIONS:
        return None
    return action


@app.route('/api/question/problem-report', methods=['POST'])
@login_required
def api_question_problem_report():
    uid = session['user_id']
    data = request.get_json(silent=True) or {}
    try:
        question_id = int(data.get('question_id'))
    except (TypeError, ValueError):
        return jsonify({'error': 'invalid_question_id'}), 400
    reason_code = str(data.get('reason_code') or '').strip()
    note = str(data.get('note') or '').strip()
    if reason_code not in QUESTION_PROBLEM_REPORT_REASON_CODES:
        return jsonify({'error': 'invalid_reason_code'}), 400
    if len(note) > 500:
        return jsonify({'error': 'note_too_long'}), 400
    now = _review_queue_now_iso()
    with get_db() as conn:
        row = conn.execute('''
            INSERT INTO question_problem_reports
                (user_id, question_id, reason_code, note, status, created_at)
            VALUES(?,?,?,?,?,?)
            RETURNING id
        ''', (uid, question_id, reason_code, note, 'open', now)).fetchone()
    return jsonify({
        'ok': True,
        'report_id': row['id'],
        'question_id': question_id,
        'reason_code': reason_code,
        'note': note,
        'status': 'open',
        'created_at': now,
    })


@app.route('/api/admin/question-problem-reports')
@admin_required
def admin_question_problem_reports():
    status = str(request.args.get('status') or '').strip()
    question_id = request.args.get('question_id')
    params = []
    where = []
    if status:
        where.append('r.status=?')
        params.append(status)
    if question_id not in (None, ''):
        try:
            question_id_int = int(question_id)
        except (TypeError, ValueError):
            return jsonify({'error': 'invalid_question_id'}), 400
        where.append('r.question_id=?')
        params.append(question_id_int)
    sql = '''
        SELECT r.*, u.username AS reporter_username
        FROM question_problem_reports r
        JOIN users u ON u.id = r.user_id
    '''
    if where:
        sql += ' WHERE ' + ' AND '.join(where)
    sql += ' ORDER BY r.created_at DESC, r.id DESC LIMIT 200'
    with get_db() as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
    questions = _load_questions_fresh()
    reports = []
    for row in rows:
        payload = _question_problem_report_to_payload(row, questions=questions)
        payload['reporter_username'] = row['reporter_username']
        reports.append(payload)
    return jsonify({'ok': True, 'reports': reports})


@app.route('/api/admin/question-problem-reports/<int:report_id>/context')
@admin_required
def admin_question_problem_report_context(report_id):
    with get_db() as conn:
        report = conn.execute('''
            SELECT r.*, u.username AS reporter_username
            FROM question_problem_reports r
            JOIN users u ON u.id = r.user_id
            WHERE r.id=?
        ''', (report_id,)).fetchone()
    if not report:
        return jsonify({'error': 'not_found'}), 404
    questions = _load_questions_fresh()
    payload = _question_problem_report_to_payload(report, questions=questions)
    payload['reporter_username'] = report['reporter_username']
    payload['questions_json_commit'] = _get_questions_json_commit()
    return jsonify({'ok': True, 'report': payload})


@app.route('/api/admin/question-problem-reports/<int:report_id>/resolve', methods=['POST'])
@admin_required
def admin_question_problem_report_resolve(report_id):
    admin_id = session['user_id']
    data = request.get_json(silent=True) or {}
    action = str(data.get('action') or '').strip()
    admin_note = str(data.get('admin_note') or data.get('note') or '').strip()
    selected_record_index = data.get('selected_record_index')
    if action not in ('confirmed', 'dismissed', 'duplicate'):
        return jsonify({'error': 'invalid_action'}), 400
    if len(admin_note) > 500:
        return jsonify({'error': 'note_too_long'}), 400
    with get_db() as conn:
        report = conn.execute('''
            SELECT *
            FROM question_problem_reports
            WHERE id=?
        ''', (report_id,)).fetchone()
        if not report:
            return jsonify({'error': 'not_found'}), 404
        questions = _load_questions_fresh()
        resolved_record = None
        if action == 'confirmed':
            candidates = _find_question_records_by_legacy_id(report['question_id'], questions=questions)
            if not candidates:
                return jsonify({'error': 'question_not_found'}), 404
            if len(candidates) > 1:
                if selected_record_index in (None, ''):
                    return jsonify({'error': 'selected_record_index_required'}), 400
                try:
                    resolved_record = _get_question_record_by_index(
                        selected_record_index,
                        questions=questions,
                        expected_legacy_question_id=report['question_id'],
                    )
                except ValueError as error:
                    return jsonify({'error': str(error)}), 400
            else:
                resolved_record = candidates[0]
            now = _review_queue_now_iso()
            source_type = 'player_reported'
            conn.execute('''
                INSERT INTO corpus_review_queue
                    (source_type, source_ref, record_index, legacy_question_id, source_path,
                     content_sha256, questions_json_commit, reason, source_batch, status,
                     resolution_action, admin_note, reviewed_by, created_at, reviewed_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(source_type, record_index) DO UPDATE SET
                    source_ref=EXCLUDED.source_ref,
                    legacy_question_id=EXCLUDED.legacy_question_id,
                    source_path=EXCLUDED.source_path,
                    content_sha256=EXCLUDED.content_sha256,
                    questions_json_commit=EXCLUDED.questions_json_commit,
                    reason=EXCLUDED.reason,
                    source_batch=EXCLUDED.source_batch,
                    status=EXCLUDED.status,
                    resolution_action=EXCLUDED.resolution_action,
                    admin_note=EXCLUDED.admin_note,
                    reviewed_by=EXCLUDED.reviewed_by,
                    reviewed_at=EXCLUDED.reviewed_at
            ''', (
                source_type,
                report_id,
                resolved_record['record_index'],
                report['question_id'],
                resolved_record['source_path'],
                resolved_record['content_sha256'],
                _get_questions_json_commit(),
                report['reason_code'],
                REVIEW_QUEUE_SOURCE_BATCH,
                'pending',
                None,
                None,
                None,
                now,
                None,
            ))
        now = _review_queue_now_iso()
        conn.execute('''
            UPDATE question_problem_reports
            SET status=?, admin_note=?, reviewed_by=?, reviewed_at=?
            WHERE id=?
        ''', (action, admin_note or None, admin_id, now, report_id))
        _review_queue_audit(
            conn,
            admin_id,
            'question_problem_report',
            action,
            target_id=report_id,
            detail=f'question_id={report["question_id"]}; selected_record_index={selected_record_index}; note={admin_note[:120]}',
        )
    return jsonify({
        'ok': True,
        'report_id': report_id,
        'action': action,
        'selected_record_index': resolved_record['record_index'] if resolved_record else None,
    })


@app.route('/api/admin/review-queue')
@admin_required
def admin_review_queue():
    source_type = str(request.args.get('source_type') or '').strip()
    status = str(request.args.get('status') or '').strip()
    params = []
    where = []
    if source_type:
        where.append('r.source_type=?')
        params.append(source_type)
    if status:
        where.append('r.status=?')
        params.append(status)
    sql = '''
        SELECT r.*, u.username AS reviewer_username
        FROM corpus_review_queue r
        LEFT JOIN users u ON u.id = r.reviewed_by
    '''
    if where:
        sql += ' WHERE ' + ' AND '.join(where)
    sql += ' ORDER BY r.created_at DESC, r.id DESC LIMIT 200'
    with get_db() as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
    questions = _load_questions_fresh()
    items = []
    for row in rows:
        payload = _review_queue_row_to_payload(row, questions=questions)
        payload['reviewer_username'] = row['reviewer_username']
        items.append(payload)
    return jsonify({'ok': True, 'queue_items': items})


@app.route('/api/admin/review-queue/<int:item_id>/context')
@admin_required
def admin_review_queue_context(item_id):
    with get_db() as conn:
        row = conn.execute('''
            SELECT r.*, u.username AS reviewer_username
            FROM corpus_review_queue r
            LEFT JOIN users u ON u.id = r.reviewed_by
            WHERE r.id=?
        ''', (item_id,)).fetchone()
    if not row:
        return jsonify({'error': 'not_found'}), 404
    questions = _load_questions_fresh()
    payload = _review_queue_row_to_payload(row, questions=questions)
    payload['reviewer_username'] = row['reviewer_username']
    payload['questions_json_commit'] = _get_questions_json_commit()
    payload['duplicate_candidates'] = _build_duplicate_candidates(row['legacy_question_id'], questions=questions)
    payload['duplicate_candidate_count'] = len(payload['duplicate_candidates'])
    return jsonify({'ok': True, 'queue_item': payload})


@app.route('/api/admin/review-queue/<int:item_id>/resolve', methods=['POST'])
@admin_required
def admin_review_queue_resolve(item_id):
    admin_id = session['user_id']
    data = request.get_json(silent=True) or {}
    action = _parse_queue_resolution_action(data)
    admin_note = str(data.get('admin_note') or data.get('note') or '').strip()
    if not action:
        return jsonify({'error': 'invalid_action'}), 400
    if len(admin_note) > 500:
        return jsonify({'error': 'note_too_long'}), 400
    now = _review_queue_now_iso()
    status = 'wont_fix' if action == 'wont_fix' else 'resolved'
    with get_db() as conn:
        row = conn.execute('SELECT id FROM corpus_review_queue WHERE id=?', (item_id,)).fetchone()
        if not row:
            return jsonify({'error': 'not_found'}), 404
        conn.execute('''
            UPDATE corpus_review_queue
            SET status=?, resolution_action=?, admin_note=?, reviewed_by=?, reviewed_at=?
            WHERE id=?
        ''', (status, action, admin_note or None, admin_id, now, item_id))
        _review_queue_audit(
            conn,
            admin_id,
            'corpus_review_queue',
            action,
            target_id=item_id,
            detail=admin_note[:500],
        )
    return jsonify({
        'ok': True,
        'id': item_id,
        'status': status,
        'resolution_action': action,
        'reviewed_at': now,
    })


@app.route('/api/admin/review-queue/import', methods=['POST'])
@admin_required
def admin_review_queue_import():
    data = request.get_json(silent=True) or {}
    base_dir = os.path.dirname(os.path.abspath(__file__))
    audit_path = str(data.get('audit_path') or os.path.join(base_dir, 'docs', 'testing', 'p0_triage_22c.md'))
    summary_path = str(data.get('summary_path') or os.path.join(base_dir, 'docs', 'testing', 'p0_triage_22c.summary.json'))
    if not os.path.isabs(audit_path):
        audit_path = os.path.join(os.getcwd(), audit_path)
    if not os.path.isabs(summary_path):
        summary_path = os.path.join(os.getcwd(), summary_path)
    if not os.path.exists(audit_path):
        return jsonify({'error': 'audit_not_found'}), 404
    with open(audit_path, 'r', encoding='utf-8') as handle:
        markdown_text = handle.read()
    summary_data = {}
    if os.path.exists(summary_path):
        try:
            with open(summary_path, 'r', encoding='utf-8') as handle:
                summary_data = json.load(handle)
        except Exception:
            summary_data = {}
    candidates, raw_row_count, duplicate_row_count = _parse_review_queue_import_candidates(markdown_text)
    questions = _load_questions_fresh()
    commit = _get_questions_json_commit()
    imported = []
    skipped = []
    now = _review_queue_now_iso()
    with get_db() as conn:
        for row in candidates:
            try:
                current = _get_question_record_by_index(
                    row['record_index'],
                    questions=questions,
                    expected_legacy_question_id=int(row['legacy_question_id']),
                )
            except Exception as error:
                skipped.append({
                    'record_index': row['record_index'],
                    'legacy_question_id': row['legacy_question_id'],
                    'reason': 'record_lookup_failed',
                    'error': str(error),
                })
                continue
            try:
                parse_sgf(current['content'], strict=True)
            except Exception:
                source_type = row['classification'] or 'p0_parse_failure'
                if source_type not in REVIEW_QUEUE_SOURCE_TYPES:
                    source_type = 'p0_parse_failure'
                reason = row['classification'] or row['parse_error_class'] or 'parse_failed'
                source_batch = REVIEW_QUEUE_SOURCE_BATCH
                conn.execute('''
                    INSERT INTO corpus_review_queue
                        (source_type, source_ref, record_index, legacy_question_id, source_path,
                         content_sha256, questions_json_commit, reason, source_batch, status,
                         resolution_action, admin_note, reviewed_by, created_at, reviewed_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(source_type, record_index) DO UPDATE SET
                        source_ref=EXCLUDED.source_ref,
                        legacy_question_id=EXCLUDED.legacy_question_id,
                        source_path=EXCLUDED.source_path,
                        content_sha256=EXCLUDED.content_sha256,
                        questions_json_commit=EXCLUDED.questions_json_commit,
                        reason=EXCLUDED.reason,
                        source_batch=EXCLUDED.source_batch,
                        status=EXCLUDED.status,
                        resolution_action=EXCLUDED.resolution_action,
                        admin_note=EXCLUDED.admin_note,
                        reviewed_by=EXCLUDED.reviewed_by,
                        reviewed_at=EXCLUDED.reviewed_at
                ''', (
                    source_type,
                    None,
                    current['record_index'],
                    current['legacy_question_id'],
                    current['source_path'],
                    current['content_sha256'],
                    commit,
                    reason,
                    source_batch,
                    'pending',
                    None,
                    None,
                    None,
                    now,
                    None,
                ))
                imported.append({
                    'record_index': current['record_index'],
                    'legacy_question_id': current['legacy_question_id'],
                    'source_type': source_type,
                    'source_path': current['source_path'],
                    'content_sha256': current['content_sha256'],
                    'reason': reason,
                })
            else:
                skipped.append({
                    'record_index': current['record_index'],
                    'legacy_question_id': current['legacy_question_id'],
                    'reason': 'current_parse_ok',
                    'classification': row['classification'],
                })
        _review_queue_audit(
            conn,
            session['user_id'],
            'corpus_review_queue',
            'import',
            detail=f'raw_rows={raw_row_count}; unique_rows={len(candidates)}; imported={len(imported)}; skipped={len(skipped)}',
        )
    return jsonify({
        'ok': True,
        'audit_path': audit_path,
        'summary_path': summary_path,
        'raw_row_count': raw_row_count,
        'unique_candidate_count': len(candidates),
        'duplicate_row_count': duplicate_row_count,
        'imported_count': len(imported),
        'skipped_count': len(skipped),
        'imported': imported,
        'skipped': skipped,
        'questions_json_commit': commit,
        'summary_22a_p0_count': summary_data.get('p0_count'),
        'summary_22a_parse_failed_count': summary_data.get('parse_failed_count'),
    })


@app.route('/api/dm/threads')
@login_required
def dm_threads_list():
    uid = session['user_id']
    _dm_maybe_cleanup()
    with get_db() as conn:
        rows = conn.execute('''
            SELECT t.id, t.last_at, t.last_msg_id,
                   u.id AS other_id, u.username,
                   COALESCE(u.nickname,u.username) AS display_name,
                   COALESCE(pa.character_key,'') AS character_key,
                   COALESCE(pa.combat_armor,'') AS combat_armor,
                   COALESCE(pa.combat_weapon,'') AS combat_weapon,
                   COALESCE(pa.combat_cape,'') AS combat_cape,
                   COALESCE(pa.combat_offhand,'') AS combat_offhand,
                   COALESCE(pa.combat_hat,'') AS combat_hat,
                   COALESCE(pa.combat_pet,'') AS combat_pet,
                   COALESCE(pa.combat_aura,'') AS combat_aura,
                   CASE WHEN u.plan='premium' THEN 1 ELSE 0 END AS is_premium,
                   m.body AS last_body, COALESCE(m.is_deleted,0) AS last_deleted,
                   EXISTS(SELECT 1 FROM dm_reports lrp
                          WHERE lrp.message_id=m.id AND lrp.reporter_id=?) AS last_reported,
                   COALESCE(dr.last_read_msg_id,0) AS last_read_msg_id,
                   EXISTS(SELECT 1 FROM dm_blocks b
                          WHERE b.blocker_id=? AND b.blocked_id=u.id) AS blocked_by_me,
                   EXISTS(SELECT 1 FROM dm_blocks b
                          WHERE b.blocker_id=u.id AND b.blocked_id=?) AS blocked_by_them,
                   (SELECT COUNT(*) FROM dm_messages um
                    WHERE um.thread_id=t.id AND um.id>COALESCE(dr.last_read_msg_id,0)
                      AND um.sender_id<>? AND um.is_deleted=0
                      AND NOT EXISTS(SELECT 1 FROM dm_reports rp
                                     WHERE rp.message_id=um.id AND rp.reporter_id=?)) AS unread_count
            FROM dm_threads t
            JOIN users u ON u.id=CASE WHEN t.user_lo=? THEN t.user_hi ELSE t.user_lo END
            LEFT JOIN player_appearance pa ON pa.user_id=u.id
            LEFT JOIN dm_messages m ON m.id=t.last_msg_id
            LEFT JOIN dm_reads dr ON dr.thread_id=t.id AND dr.user_id=?
            WHERE t.user_lo=? OR t.user_hi=?
            ORDER BY t.last_at DESC NULLS LAST, t.id DESC
        ''', (uid, uid, uid, uid, uid, uid, uid, uid, uid)).fetchall()
        result = []
        for row in rows:
            last_body = '' if row['last_deleted'] or row['last_reported'] else (row['last_body'] or '')
            result.append({
                'thread_id': row['id'],
                'username': row['username'],
                'display_name': row['display_name'],
                'last_preview': ('訊息已移除' if row['last_deleted'] else
                                 ('已檢舉並隱藏' if row['last_reported'] else last_body[:40])),
                'last_at': row['last_at'] or '',
                'unread_count': row['unread_count'] or 0,
                'blocked_by_me': bool(row['blocked_by_me']),
                'blocked_by_them': bool(row['blocked_by_them']),
                'can_send': not (row['blocked_by_me'] or row['blocked_by_them'])
                            and _dm_are_friends(conn, uid, row['other_id']),
                **_row_loadout(row),
            })
    return jsonify({'threads': result})


@app.route('/api/dm/thread/<username>')
@login_required
def dm_thread_meta(username):
    uid = session['user_id']
    with get_db() as conn:
        other = conn.execute('''
            SELECT u.id,u.username,COALESCE(u.nickname,u.username) AS display_name,
                   COALESCE(pa.character_key,'') AS character_key,
                   COALESCE(pa.combat_armor,'') AS combat_armor,
                   COALESCE(pa.combat_weapon,'') AS combat_weapon,
                   COALESCE(pa.combat_cape,'') AS combat_cape,
                   COALESCE(pa.combat_offhand,'') AS combat_offhand,
                   COALESCE(pa.combat_hat,'') AS combat_hat,
                   COALESCE(pa.combat_pet,'') AS combat_pet,
                   COALESCE(pa.combat_aura,'') AS combat_aura,
                   CASE WHEN u.plan='premium' THEN 1 ELSE 0 END AS is_premium
            FROM users u LEFT JOIN player_appearance pa ON pa.user_id=u.id
            WHERE LOWER(u.username)=LOWER(?)
        ''', (username,)).fetchone()
        if not other or other['id'] == uid:
            return jsonify({'error': '找不到可私訊的使用者'}), 404
        lo, hi = sorted((uid, other['id']))
        thread = conn.execute(
            'SELECT id FROM dm_threads WHERE user_lo=? AND user_hi=?', (lo, hi)
        ).fetchone()
        is_friend = _dm_are_friends(conn, uid, other['id'])
        if not thread and not is_friend:
            return jsonify({'error': '只能查看好友的私訊'}), 403
        block = _dm_block_state(conn, uid, other['id'])
        return jsonify({
            'thread_id': thread['id'] if thread else None,
            'username': other['username'],
            'display_name': other['display_name'],
            'is_friend': is_friend,
            'can_send': is_friend and not block['blocked'],
            **block,
            **_row_loadout(other),
        })


@app.route('/api/dm/messages')
@login_required
def dm_messages_list():
    uid = session['user_id']
    try:
        thread_id = int(request.args.get('thread_id', ''))
        before_id = int(request.args['before_id']) if request.args.get('before_id') else None
        after_id = int(request.args['after_id']) if request.args.get('after_id') else None
        limit = min(100, max(1, int(request.args.get('limit', 30))))
    except (TypeError, ValueError):
        return jsonify({'error': '無效的查詢參數'}), 400
    if before_id and after_id:
        return jsonify({'error': 'before_id 與 after_id 不可同時使用'}), 400
    with get_db() as conn:
        thread = _dm_thread_for_member(conn, thread_id, uid)
        if not thread:
            return jsonify({'error': '無權查看此會話'}), 403
        clauses = ['m.thread_id=?']
        params = [uid, thread_id]
        if before_id:
            clauses.append('m.id<?')
            params.append(before_id)
        if after_id:
            clauses.append('m.id>?')
            params.append(after_id)
        order = 'ASC' if after_id else 'DESC'
        params.append(limit)
        rows = conn.execute(f'''
            SELECT m.id,m.sender_id,m.body,m.created_at,m.is_deleted,
                   CASE WHEN rp.id IS NULL THEN 0 ELSE 1 END AS is_reported
            FROM dm_messages m
            LEFT JOIN dm_reports rp ON rp.message_id=m.id AND rp.reporter_id=?
            WHERE {' AND '.join(clauses)}
            ORDER BY m.id {order}
            LIMIT ?
        ''', params).fetchall()
        if not after_id:
            rows = list(reversed(rows))
        messages = []
        for row in rows:
            deleted = bool(row['is_deleted'])
            reported = bool(row['is_reported'])
            messages.append({
                'id': row['id'],
                'sender_id': row['sender_id'],
                'body': '' if deleted or reported else row['body'],
                'created_at': row['created_at'],
                'is_mine': row['sender_id'] == uid,
                'is_deleted': deleted,
                'is_reported': reported,
            })
    return jsonify({'messages': messages, 'has_more': len(rows) == limit})


@app.route('/api/dm/send', methods=['POST'])
@login_required
def dm_send():
    uid = session['user_id']
    data = request.get_json(silent=True) or {}
    text, error = _dm_clean_text(data.get('text'))
    if error:
        return jsonify({'error': error}), 400
    username = str(data.get('username') or '').strip()
    thread_value = data.get('thread_id')
    if bool(username) == bool(thread_value):
        return jsonify({'error': '請指定一個收件對象'}), 400
    with get_db() as conn:
        if username:
            other = conn.execute(
                'SELECT id,username FROM users WHERE LOWER(username)=LOWER(?)', (username,)
            ).fetchone()
            if not other:
                return jsonify({'error': '找不到該使用者'}), 404
            other_id = other['id']
        else:
            try:
                thread = _dm_thread_for_member(conn, int(thread_value), uid)
            except (TypeError, ValueError):
                thread = None
            if not thread:
                return jsonify({'error': '無效的會話'}), 400
            other_id = thread['user_hi'] if thread['user_lo'] == uid else thread['user_lo']
        if other_id == uid:
            return jsonify({'error': '不能傳訊給自己'}), 400
        if not _dm_are_friends(conn, uid, other_id):
            return jsonify({'error': '只能傳訊給目前的好友'}), 403
        block = _dm_block_state(conn, uid, other_id)
        if block['blocked']:
            return jsonify({'error': '此會話目前無法傳送訊息'}), 403

        # 序列化同一 sender 的限頻判定，避免並行請求一起穿過 COUNT。
        conn.execute('SELECT id FROM users WHERE id=? FOR UPDATE', (uid,)).fetchone()
        now_dt = datetime.datetime.now()
        now = now_dt.isoformat()
        cutoff = (now_dt - datetime.timedelta(seconds=DM_RATE_WINDOW_SEC)).isoformat()
        recent = conn.execute('''
            SELECT COUNT(*) FROM dm_messages
            WHERE sender_id=? AND created_at>=?
        ''', (uid, cutoff)).fetchone()[0]
        if recent >= DM_RATE_MAX:
            return jsonify({'error': '傳送太快了，請稍後再試'}), 429
        thread_id = _dm_get_or_create_thread(conn, uid, other_id, now)
        message = conn.execute('''
            INSERT INTO dm_messages(thread_id,sender_id,body,created_at)
            VALUES(?,?,?,?) RETURNING id
        ''', (thread_id, uid, text, now)).fetchone()
        conn.execute('''
            UPDATE dm_threads SET last_msg_id=?,last_at=? WHERE id=?
        ''', (message['id'], now, thread_id))
    return jsonify({'ok': True, 'thread_id': thread_id, 'message': {
        'id': message['id'], 'sender_id': uid, 'body': text,
        'created_at': now, 'is_mine': True,
        'is_deleted': False, 'is_reported': False,
    }})


@app.route('/api/dm/read', methods=['POST'])
@login_required
def dm_read():
    uid = session['user_id']
    data = request.get_json(silent=True) or {}
    try:
        thread_id = int(data.get('thread_id'))
        up_to_msg_id = int(data.get('up_to_msg_id'))
    except (TypeError, ValueError):
        return jsonify({'error': '無效的已讀位置'}), 400
    with get_db() as conn:
        if not _dm_thread_for_member(conn, thread_id, uid):
            return jsonify({'error': '無權操作此會話'}), 403
        if not conn.execute(
            'SELECT 1 FROM dm_messages WHERE id=? AND thread_id=?',
            (up_to_msg_id, thread_id)
        ).fetchone():
            return jsonify({'error': '訊息不屬於此會話'}), 400
        conn.execute('''
            INSERT INTO dm_reads(thread_id,user_id,last_read_msg_id)
            VALUES(?,?,?)
            ON CONFLICT(thread_id,user_id) DO UPDATE SET
                last_read_msg_id=GREATEST(dm_reads.last_read_msg_id,EXCLUDED.last_read_msg_id)
        ''', (thread_id, uid, up_to_msg_id))
    return jsonify({'ok': True})


@app.route('/api/dm/unread_count')
@login_required
def dm_unread_count():
    uid = session['user_id']
    with get_db() as conn:
        count = conn.execute('''
            SELECT COUNT(*)
            FROM dm_messages m
            JOIN dm_threads t ON t.id=m.thread_id
            LEFT JOIN dm_reads dr ON dr.thread_id=t.id AND dr.user_id=?
            WHERE (t.user_lo=? OR t.user_hi=?)
              AND m.sender_id<>? AND m.is_deleted=0
              AND m.id>COALESCE(dr.last_read_msg_id,0)
              AND NOT EXISTS(SELECT 1 FROM dm_reports rp
                             WHERE rp.message_id=m.id AND rp.reporter_id=?)
        ''', (uid, uid, uid, uid, uid)).fetchone()[0]
    return jsonify({'count': count})


@app.route('/api/dm/block', methods=['POST'])
@login_required
def dm_block():
    uid = session['user_id']
    username = str((request.get_json(silent=True) or {}).get('username') or '').strip()
    with get_db() as conn:
        other = conn.execute(
            'SELECT id FROM users WHERE LOWER(username)=LOWER(?)', (username,)
        ).fetchone()
        if not other or other['id'] == uid:
            return jsonify({'error': '找不到可封鎖的使用者'}), 400
        conn.execute('''
            INSERT INTO dm_blocks(blocker_id,blocked_id,created_at)
            VALUES(?,?,?) ON CONFLICT(blocker_id,blocked_id) DO NOTHING
        ''', (uid, other['id'], datetime.datetime.now().isoformat()))
    return jsonify({'ok': True})


@app.route('/api/dm/unblock', methods=['POST'])
@login_required
def dm_unblock():
    uid = session['user_id']
    username = str((request.get_json(silent=True) or {}).get('username') or '').strip()
    with get_db() as conn:
        other = conn.execute(
            'SELECT id FROM users WHERE LOWER(username)=LOWER(?)', (username,)
        ).fetchone()
        if not other:
            return jsonify({'error': '找不到該使用者'}), 404
        conn.execute('DELETE FROM dm_blocks WHERE blocker_id=? AND blocked_id=?',
                     (uid, other['id']))
    return jsonify({'ok': True})


@app.route('/api/dm/report', methods=['POST'])
@login_required
def dm_report():
    uid = session['user_id']
    data = request.get_json(silent=True) or {}
    try:
        message_id = int(data.get('message_id'))
    except (TypeError, ValueError):
        return jsonify({'error': '無效的訊息'}), 400
    reason = str(data.get('reason') or '').strip()
    if len(reason) > 500:
        return jsonify({'error': '檢舉說明最多 500 字'}), 400
    with get_db() as conn:
        message = conn.execute('''
            SELECT m.id,m.sender_id,m.thread_id,t.user_lo,t.user_hi
            FROM dm_messages m JOIN dm_threads t ON t.id=m.thread_id
            WHERE m.id=?
        ''', (message_id,)).fetchone()
        if not message or uid not in (message['user_lo'], message['user_hi']):
            return jsonify({'error': '無權檢舉此訊息'}), 403
        if message['sender_id'] == uid:
            return jsonify({'error': '不能檢舉自己傳送的訊息'}), 400
        conn.execute('''
            INSERT INTO dm_reports(reporter_id,message_id,reason,created_at)
            VALUES(?,?,?,?) ON CONFLICT(reporter_id,message_id) DO NOTHING
        ''', (uid, message_id, reason or None, datetime.datetime.now().isoformat()))
    return jsonify({'ok': True})


@app.route('/api/question/alternative-report', methods=['POST'])
@login_required
def question_alternative_report():
    uid = session['user_id']
    data = request.get_json(silent=True) or {}
    qs_map = {int(q.get('id')): q for q in _load_questions() if q.get('id') is not None}
    try:
        question_id = int(data.get('question_id'))
        move = data.get('move') or {}
        wrong_x = int(move.get('x'))
        wrong_y = int(move.get('y'))
    except (TypeError, ValueError):
        return jsonify({'error': '無效的題目或座標'}), 400
    q = qs_map.get(question_id)
    if not q:
        return jsonify({'error': '找不到題目'}), 404
    m = _re_mod.search(r'SZ\[(\d+)\]', q.get('content') or '')
    size = int(m.group(1)) if m else 19
    if not (0 <= wrong_x < size and 0 <= wrong_y < size):
        return jsonify({'error': '座標超出題目範圍'}), 400
    note = str(data.get('note') or '').strip()
    if len(note) > 500:
        return jsonify({'error': '說明最多 500 字'}), 400

    with get_db() as conn:
        conn.execute('''
            INSERT INTO question_alternative_reports
                (user_id,question_id,wrong_move_x,wrong_move_y,note,status,created_at)
            VALUES(?,?,?,?,?,'open',?)
            ON CONFLICT(user_id,question_id,wrong_move_x,wrong_move_y) DO UPDATE SET
                note=excluded.note
        ''', (uid, question_id, wrong_x, wrong_y, note, datetime.datetime.now().isoformat()))
        conn.commit()
    return jsonify({'ok': True})


@app.route('/api/admin/dm/reports')
@admin_required
def admin_dm_reports():
    admin_id = session['user_id']
    with get_db() as conn:
        rows = conn.execute('''
            SELECT rp.id,rp.reason,rp.status,rp.created_at,
                   rp.message_id,m.thread_id,m.body,m.created_at AS message_at,
                   reporter.username AS reporter_username,
                   sender.username AS sender_username
            FROM dm_reports rp
            JOIN dm_messages m ON m.id=rp.message_id
            JOIN users reporter ON reporter.id=rp.reporter_id
            JOIN users sender ON sender.id=m.sender_id
            ORDER BY CASE WHEN rp.status='open' THEN 0 ELSE 1 END,rp.created_at DESC
            LIMIT 200
        ''').fetchall()
        _dm_audit(conn, admin_id, 'view_report', reason='list_reports')
        reports = [dict(row) for row in rows]
    return jsonify({'reports': reports})


@app.route('/api/admin/question-alternative-reports')
@admin_required
def admin_question_alternative_reports():
    admin_id = session['user_id']
    qs_map = {int(q.get('id')): q for q in _load_questions() if q.get('id') is not None}
    with get_db() as conn:
        rows = conn.execute('''
            SELECT r.id,r.user_id,r.question_id,r.wrong_move_x,r.wrong_move_y,r.note,
                   r.status,r.admin_note,r.created_at,r.reviewed_at,
                   r.reviewed_by,u.username AS reporter_username,
                   reviewer.username AS reviewed_by_username
            FROM question_alternative_reports r
            JOIN users u ON u.id=r.user_id
            LEFT JOIN users reviewer ON reviewer.id=r.reviewed_by
            ORDER BY CASE WHEN r.status='open' THEN 0 ELSE 1 END,
                     r.created_at DESC, r.id DESC
            LIMIT 200
        ''').fetchall()
        _question_alt_report_audit(conn, admin_id, 'view_reports', None, 'list_reports')
        reports = []
        for row in rows:
            q = qs_map.get(int(row['question_id']))
            size = 19
            if q:
                m = _re_mod.search(r'SZ\[(\d+)\]', q.get('content') or '')
                if m:
                    size = int(m.group(1))
            move_label = _xy_to_gtp(int(row['wrong_move_x']), int(row['wrong_move_y']), size)
            reports.append({
                **dict(row),
                'question_label': _question_display_name(q) if q else f"Question {row['question_id']}",
                'question_topic': (q.get('topic') if q else '') or '',
                'question_level': (q.get('level') if q else '') or '',
                'question_source': (q.get('source') if q else '') or '',
                'move_label': move_label,
            })
    return jsonify({'reports': reports})


@app.route('/api/admin/question-alternative-reports/<int:report_id>/context')
@admin_required
def admin_question_alternative_report_context(report_id):
    admin_id = session['user_id']
    qs_map = {int(q.get('id')): q for q in _load_questions() if q.get('id') is not None}
    with get_db() as conn:
        report = conn.execute('''
            SELECT r.*, u.username AS reporter_username
            FROM question_alternative_reports r
            JOIN users u ON u.id=r.user_id
            WHERE r.id=?
        ''', (report_id,)).fetchone()
        if not report:
            return jsonify({'error': '找不到回報'}), 404
        q = qs_map.get(int(report['question_id']))
        _question_alt_report_audit(conn, admin_id, 'view_context', report_id,
                                   f'question_id={report["question_id"]}')
    if not q:
        return jsonify({
            'report': dict(report),
            'question': None,
        })
    return jsonify({
        'report': dict(report),
        'question': {
            'id': q.get('id'),
            'source': q.get('source') or '',
            'topic': q.get('topic') or '',
            'level': q.get('level') or '',
            'comment': q.get('comment') or '',
            'content': q.get('content') or '',
        }
    })


@app.route('/api/admin/question-alternative-reports/<int:report_id>/resolve', methods=['POST'])
@admin_required
def admin_question_alternative_report_resolve(report_id):
    admin_id = session['user_id']
    data = request.get_json(silent=True) or {}
    action = str(data.get('action') or '').strip()
    note = str(data.get('note') or '').strip()
    move = data.get('move') or {}
    if action not in ('accept', 'dismiss', 'disable'):
        return jsonify({'error': '無效的處理方式'}), 400
    if len(note) > 500:
        return jsonify({'error': '處理理由最多 500 字'}), 400

    with get_db() as conn:
        report = conn.execute(
            'SELECT id,status,question_id FROM question_alternative_reports WHERE id=?',
            (report_id,)
        ).fetchone()
        if not report:
            return jsonify({'error': '找不到回報'}), 404
        if report['status'] != 'open':
            return jsonify({'error': 'already_resolved'}), 409
        qs = _load_questions()
        q = next((x for x in qs if x['id'] == report['question_id']), None)
        if not q:
            return jsonify({'error': '找不到題目'}), 404
        now = datetime.datetime.now().isoformat()
        if action == 'accept':
            if not _append_question_accepted_move(q, move, report_id=report_id, admin_id=admin_id, note=note):
                return jsonify({'error': '無效座標'}), 400
            _save_questions(qs)
        elif action == 'disable':
            _disable_question_solution(q, admin_id=admin_id, note=note)
            _save_questions(qs)
        conn.execute('''
            UPDATE question_alternative_reports
               SET status=?, admin_note=?, reviewed_by=?, reviewed_at=?
             WHERE id=?
        ''', ('accepted' if action == 'accept' else 'dismissed',
              note[:500], admin_id, now, report_id))
        audit_action = 'accept' if action == 'accept' else 'dismiss'
        _question_alt_report_audit(
            conn, admin_id, audit_action, report_id,
            f'question_id={report["question_id"]}; action={action}; note={note[:120]}; move={move}'
        )
        conn.commit()
    return jsonify({'ok': True})


@app.route('/api/admin/dm/reports/<int:report_id>/context')
@admin_required
def admin_dm_report_context(report_id):
    admin_id = session['user_id']
    with get_db() as conn:
        report = conn.execute('''
            SELECT rp.id,rp.message_id,m.thread_id
            FROM dm_reports rp JOIN dm_messages m ON m.id=rp.message_id
            WHERE rp.id=?
        ''', (report_id,)).fetchone()
        if not report:
            return jsonify({'error': '找不到檢舉'}), 404
        rows = conn.execute('''
            SELECT m.id,m.sender_id,u.username,m.body,m.created_at,m.is_deleted
            FROM dm_messages m JOIN users u ON u.id=m.sender_id
            WHERE m.thread_id=? AND m.id BETWEEN ? AND ?
            ORDER BY m.id
        ''', (report['thread_id'], max(0, report['message_id'] - 10),
              report['message_id'] + 10)).fetchall()
        _dm_audit(conn, admin_id, 'view_context', report_id=report_id,
                  thread_id=report['thread_id'], message_id=report['message_id'],
                  reason='review_report')
        messages = [dict(row) for row in rows]
    return jsonify({'messages': messages})


@app.route('/api/admin/dm/resolve', methods=['POST'])
@admin_required
def admin_dm_resolve():
    admin_id = session['user_id']
    data = request.get_json(silent=True) or {}
    try:
        report_id = int(data.get('report_id'))
    except (TypeError, ValueError):
        return jsonify({'error': '無效的檢舉'}), 400
    action = data.get('action')
    reason = str(data.get('reason') or '').strip()
    if action not in ('delete_msg', 'dismiss'):
        return jsonify({'error': '無效的處理方式'}), 400
    if not reason:
        return jsonify({'error': '請填寫處理理由'}), 400
    with get_db() as conn:
        report = conn.execute('''
            SELECT rp.message_id,m.thread_id FROM dm_reports rp
            JOIN dm_messages m ON m.id=rp.message_id WHERE rp.id=?
        ''', (report_id,)).fetchone()
        if not report:
            return jsonify({'error': '找不到檢舉'}), 404
        if action == 'delete_msg':
            conn.execute('UPDATE dm_messages SET is_deleted=1 WHERE id=?',
                         (report['message_id'],))
            conn.execute("UPDATE dm_reports SET status='reviewed' WHERE id=?", (report_id,))
            audit_action = 'delete_message'
        else:
            conn.execute("UPDATE dm_reports SET status='dismissed' WHERE id=?", (report_id,))
            audit_action = 'dismiss_report'
        _dm_audit(conn, admin_id, audit_action, report_id=report_id,
                  thread_id=report['thread_id'], message_id=report['message_id'],
                  reason=reason)
    return jsonify({'ok': True})


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
        trow = conn.execute('SELECT id FROM users WHERE LOWER(username)=LOWER(?)',
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
            xp                       = user_stats.xp + ?,
            coins                    = user_stats.coins + ?,
            challenge_wins           = ?,
            challenge_win_streak     = ?,
            max_challenge_win_streak = ?,
            updated_at               = ?
    ''', (uid, xp, coins, chal_wins, chal_streak, max_streak, now,
          xp, coins, chal_wins, chal_streak, max_streak, now))

    pet_reward = None
    if both_done and result in ('win', 'draw'):
        _grant_pet_food(conn, uid, 'moon_drop', 1)
        pet_reward = _pet_food_reward('moon_drop', 1)

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
        'pet_reward':   pet_reward,
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

    try:
        import shadow_judging
        if shadow_judging.is_enabled():
            qs_map = {q['id']: q for q in _load_questions()}
            shadow_q = qs_map.get(qid, {})
            shadow_judging.observe_answer_route(
                entry_point='friend_challenge',
                question_id=qid,
                session_id=f'friend:{cid}:{uid}',
                transform_idx=0,
                sgf_transformed=shadow_q.get('content', ''),
                moves=data.get('moves') if isinstance(data.get('moves'), list) else None,
                client_correct=bool(data.get('correct')),
                final_correct=bool(correct),
                katago_best_move=shadow_q.get('katago_best_move', ''),
            )
    except Exception:
        app.logger.exception('[shadow] observe failed (ignored)')

    return jsonify({'ok': True, 'my_total_answered': total_answered,
                    'rewards': rewards})


@app.route('/api/challenges/friend/list')
@login_required
def friend_challenge_list():
    """列出我的好友挑戰（待處理 + 進行中 + 最近完成）。"""
    uid = session['user_id']
    with get_db() as conn:

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
    with get_db() as conn:
        conn.execute(
            'INSERT INTO share_links(user_id,share_token,title,stats_json,created_at) VALUES(?,?,?,?,?)',
            (uid, token, title, json.dumps(stats, ensure_ascii=False),
             datetime.datetime.now().isoformat())
        )
        conn.commit()
    return jsonify({'ok': True, 'token': token, 'url': f'/share/{token}'})


# 靜態頁面
# ══════════════════════════════════════════════════════════════

@app.route('/login')
def login_page():
    if 'user_id' in session:
        return redirect('/')
    return _serve_live_static_or_baked('login.html')

@app.route('/')
def index():
    if 'user_id' not in session:
        return _serve_live_static_or_baked('landing.html')
    return _serve_live_static_or_baked('index.html')

@app.route('/landing')
def landing():
    return _serve_live_static_or_baked('landing.html')

@app.route('/terms')
def terms_page():
    """服務條款/隱私權/退款政策/消費者權益（藍新商店審核要求公開揭露）"""
    return _serve_live_static_or_baked('terms.html')

@app.route('/manage')
@admin_required
def manage(): return _serve_live_static_or_baked('manage.html')

@app.route('/admin')
@admin_required
def admin_page(): return _serve_live_static_or_baked('admin.html')


@app.route('/admin/shadow-dashboard')
@admin_required
def shadow_dashboard_page(): return _serve_live_static_or_baked('shadow_dashboard.html')

# ══════════════════════════════════════════════════════════════
# GnuGo AI 陪練
# ══════════════════════════════════════════════════════════════

# GnuGo 可執行檔路徑（找不到時顯示友善錯誤）
GNUGO_EXE = os.environ.get('GNUGO_EXE', 'gnugo')   # 可在環境變數中覆蓋
# 也支援放在專案目錄下的 gnugo.exe
_GNUGO_LOCAL = os.path.join(os.path.dirname(__file__), 'gnugo.exe')
if os.path.exists(_GNUGO_LOCAL):
    GNUGO_EXE = _GNUGO_LOCAL

# 進行中的對局：{ game_id: { proc, user_id, color, size, lock, last_activity } }
_gnugo_games: dict = {}
_gnugo_lock = threading.Lock()
_GNUGO_IDLE_TIMEOUT_SEC   = 10 * 60
_GNUGO_MAX_CONCURRENT     = 50
# 目標：
# - LV1–3：新手陪練，故意更弱，但每級仍有明顯差異
# - LV4–6：中級陪練，開始進入「像在下棋」的區間
# - LV7–10：高級挑戰，盡量穩定、少亂下
_GNUGO_LEVEL_PROFILE = {
    1: {'engine_level': 1,  'random_ratio': 0.98, 'candidate_pool': 22, 'pick_mode': 'tail',  'choice_fraction': 0.25},
    2: {'engine_level': 1,  'random_ratio': 0.88, 'candidate_pool': 20, 'pick_mode': 'tail',  'choice_fraction': 0.32},
    3: {'engine_level': 1,  'random_ratio': 0.72, 'candidate_pool': 18, 'pick_mode': 'tail',  'choice_fraction': 0.40},
    4: {'engine_level': 2,  'random_ratio': 0.52, 'candidate_pool': 15, 'pick_mode': 'mixed', 'choice_fraction': 0.50},
    5: {'engine_level': 3,  'random_ratio': 0.32, 'candidate_pool': 13, 'pick_mode': 'mixed', 'choice_fraction': 0.62},
    6: {'engine_level': 4,  'random_ratio': 0.16, 'candidate_pool': 11, 'pick_mode': 'top',   'choice_fraction': 0.72},
    7: {'engine_level': 6,  'random_ratio': 0.08, 'candidate_pool': 9,  'pick_mode': 'top',   'choice_fraction': 0.82},
    8: {'engine_level': 8,  'random_ratio': 0.03, 'candidate_pool': 7,  'pick_mode': 'top',   'choice_fraction': 0.90},
    9: {'engine_level': 9,  'random_ratio': 0.01, 'candidate_pool': 5,  'pick_mode': 'top',   'choice_fraction': 0.96},
    10:{'engine_level': 10, 'random_ratio': 0.00, 'candidate_pool': 4,  'pick_mode': 'top',   'choice_fraction': 1.00},
}

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

def _gnugo_profile(level: int) -> dict:
    level = max(1, min(10, int(level or 1)))
    return _GNUGO_LEVEL_PROFILE.get(level, _GNUGO_LEVEL_PROFILE[5]).copy()

def _choose_gnugo_move_from_profile(ranked_moves: list[tuple[int, int]], profile: dict):
    """依 profile 從已排序候選中挑一手。

    ranked_moves 需為由強到弱排序的清單；這裡不再只靠 random_ratio，
    而是讓不同等級使用不同的抽樣區間，避免 LV1–3 或 LV4–6 彼此太像。
    """
    if not ranked_moves:
        return None
    pool = max(1, min(len(ranked_moves), int(profile.get('candidate_pool', 8) or 8)))
    pool_moves = ranked_moves[:pool]
    fraction = float(profile.get('choice_fraction', 1.0) or 1.0)
    fraction = max(0.1, min(1.0, fraction))
    span = max(1, min(pool, int(round(pool * fraction))))
    mode = (profile.get('pick_mode') or 'top').lower()

    if mode == 'tail':
        candidates = pool_moves[-span:]
    elif mode == 'mixed':
        head = pool_moves[:max(1, span // 2)]
        tail = pool_moves[-max(1, span - len(head)):]
        candidates = head + [mv for mv in tail if mv not in head]
    else:
        candidates = pool_moves[:span]

    return random.choice(candidates or pool_moves)

def _list_legal_moves(proc, color: str, size: int) -> list[tuple[int, int]] | None:
    resp = _gtp(proc, f'all_legal {color}')
    if resp is None:
        return None
    if not resp.strip():
        return []
    moves = []
    for coord in resp.strip().split():
        coord = coord.upper()
        if coord in ('PASS', ''):
            continue
        xy = _gtp_to_xy(coord, size)
        if xy:
            moves.append(xy)
    return moves

def _soft_rank_moves(moves: list[tuple[int, int]], occupied: set[tuple[int, int]], size: int) -> list[tuple[int, int]]:
    if not moves:
        return []
    center = (size - 1) / 2.0

    def score(move: tuple[int, int]) -> tuple[float, float]:
        x, y = move
        dist = abs(x - center) + abs(y - center)
        neighbors = 0
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if (nx, ny) in occupied:
                neighbors += 1
        return (neighbors, -dist)

    return sorted(moves, key=score, reverse=True)

def _genmove_with_profile(proc, color: str, size: int, level: int) -> str:
    profile = _gnugo_profile(level)
    random_ratio = float(profile.get('random_ratio', 0.0) or 0.0)
    if random_ratio > 0 and random.random() < random_ratio:
        legal_moves = _list_legal_moves(proc, color, size)
        if legal_moves is None:
            return _gtp_with_timeout(proc, f'genmove {color}', _gnugo_move_timeout(size))
        if not legal_moves:
            _gtp(proc, f'play {color} PASS')
            return 'PASS'
        occupied = _list_stones(proc, 'black', size) | _list_stones(proc, 'white', size)
        ranked = _soft_rank_moves(legal_moves, occupied, size)
        choice = _choose_gnugo_move_from_profile(ranked, profile)
        if choice is None:
            return _gtp_with_timeout(proc, f'genmove {color}', _gnugo_move_timeout(size))
        coord = _xy_to_gtp(choice[0], choice[1], size)
        played = _gtp(proc, f'play {color} {coord}')
        if played is not None:
            return coord
    return _gtp_with_timeout(proc, f'genmove {color}', _gnugo_move_timeout(size))

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

def _gnugo_move_timeout(size: int) -> int:
    raw = os.environ.get(f'GNUGO_MOVE_TIMEOUT_{size}') or os.environ.get('GNUGO_MOVE_TIMEOUT') or '0'
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 0

def _gtp_with_timeout(proc, cmd: str, timeout_sec: int):
    if timeout_sec <= 0:
        return _gtp(proc, cmd)
    q = queue.Queue(maxsize=1)

    def run():
        try:
            q.put(('ok', _gtp(proc, cmd)))
        except Exception as exc:
            q.put(('err', exc))

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout_sec)
    if t.is_alive():
        try:
            proc.kill()
        except Exception:
            pass
        raise TimeoutError(f'GnuGo command timed out after {timeout_sec}s: {cmd}')
    kind, value = q.get()
    if kind == 'err':
        raise value
    return value

def _start_gnugo(size: int, level: int, handicap: int, komi: float) -> subprocess.Popen:
    profile = _gnugo_profile(level)
    cmd = [GNUGO_EXE, '--mode', 'gtp',
           '--boardsize', str(size),
           '--level', str(profile.get('engine_level', level)),
           '--komi', str(komi)]
    proc = subprocess.Popen(cmd,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    _gtp(proc, f'boardsize {size}')
    _gtp(proc, f'komi {komi}')
    if handicap > 1:
        _gtp(proc, f'fixed_handicap {handicap}')
    return proc

def _terminate_gnugo_game(g):
    if g:
        try:
            _gtp(g['proc'], 'quit')
            g['proc'].wait(timeout=2)
        except Exception:
            g['proc'].kill()

def _cleanup_gnugo(game_id: str, user_id=None):
    with _gnugo_lock:
        g = _gnugo_games.get(game_id)
        if user_id is not None and g and g.get('user_id') != user_id:
            g = None
        elif g:
            _gnugo_games.pop(game_id, None)
    _terminate_gnugo_game(g)
    return bool(g)

def _cleanup_expired_gnugo(now=None):
    """清掉 10 分鐘未操作的 GnuGo 對局，避免背景程序吃 Cloud Run 資源。"""
    now = now or time.time()
    expired = []
    with _gnugo_lock:
        for gid, g in list(_gnugo_games.items()):
            if now - g.get('last_activity', now) > _GNUGO_IDLE_TIMEOUT_SEC:
                expired.append(_gnugo_games.pop(gid))
    for g in expired:
        _terminate_gnugo_game(g)
    return len(expired)

def _active_gnugo_for_user(user_id):
    with _gnugo_lock:
        for gid, g in _gnugo_games.items():
            if g.get('user_id') == user_id:
                return gid, g
    return None, None

def _get_user_gnugo_game(game_id: str, touch=True):
    user_id = session.get('user_id')
    _cleanup_expired_gnugo()
    with _gnugo_lock:
        g = _gnugo_games.get(game_id)
        if not g or g.get('user_id') != user_id:
            return None
        if touch:
            g['last_activity'] = time.time()
        return g

def _gnugo_high_level_requires_premium(size: int, level: int) -> bool:
    return size == 19 and level >= 6


@app.route('/bot')
@login_required
def bot_page(): return _serve_live_static_or_baked('bot.html')


@app.route('/api/bot/new', methods=['POST'])
@login_required
def bot_new():
    """建立新的 GnuGo 對局"""
    data     = request.get_json() or {}
    uid      = session.get('user_id')
    size     = int(data.get('size', 9))
    requested_level = max(1, min(10, int(data.get('level', 5))))
    level    = requested_level
    color    = data.get('color', 'B').upper()   # 玩家顏色
    handicap = int(data.get('handicap', 0))
    komi     = float(data.get('komi', 6.5))

    if size not in (9, 13, 19):
        return jsonify({'error': '棋盤大小必須是 9、13 或 19'}), 400
    if handicap > 0 and size < 13:
        handicap = 0   # 9路不設讓子
    max_level_env = os.environ.get(f'GNUGO_MAX_LEVEL_{size}') or os.environ.get('GNUGO_MAX_LEVEL')
    level_capped_message = None
    if max_level_env:
        try:
            max_level = max(1, min(10, int(max_level_env)))
            if level > max_level:
                level = max_level
                level_capped_message = f'此伺服器資源有限，{size} 路 GnuGo 最高暫時限制為 LV{max_level}'
        except (TypeError, ValueError):
            pass

    if _gnugo_high_level_requires_premium(size, level) and not is_premium(uid):
        return jsonify({
            'error': '19 路 LV6-LV10 是 Premium 專屬難度',
            'error_type': 'premium_required',
            'upgrade_url': '/upgrade',
        }), 403

    _cleanup_expired_gnugo()
    with _gnugo_lock:
        if len(_gnugo_games) >= _GNUGO_MAX_CONCURRENT:
            return jsonify({'error': '伺服器目前對局已滿（上限 50 盤），請稍後再試'}), 503
    active_gid, active_game = _active_gnugo_for_user(uid)
    if active_game:
        return jsonify({
            'error': '你已經有一盤 GnuGo 對局進行中，請先結束目前對局',
            'error_type': 'active_game_exists',
            'game_id': active_gid,
            'size': active_game.get('size'),
            'level': active_game.get('level'),
        }), 409

    try:
        proc = _start_gnugo(size, level, handicap, komi)
    except FileNotFoundError:
        return jsonify({'error': 'GnuGo 未安裝或路徑錯誤，請確認伺服器已安裝 gnugo'}), 500

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
            'user_id':   uid,
            'size':      size,
            'player':    color,
            'ai':        ai_color,
            'level':     level,
            'handicap':  handicap,
            'komi':      komi,
            'moves':     0,
            'last_activity': time.time(),
            'ko_point':  None,   # 玩家下一手的禁著點（打劫）
            'lock':      threading.Lock(),
        }

    current_color = 'W' if handicap > 1 else 'B'
    result = {'game_id': game_id, 'size': size, 'player_color': color,
              'ai_color': ai_color, 'level': level, 'komi': komi,
              'handicap': handicap, 'handicap_stones': handicap_stones,
              'current_color': current_color}
    if level != requested_level:
        result['requested_level'] = requested_level
        result['level_capped'] = True
        result['level_capped_message'] = level_capped_message

    # 若玩家執白，GnuGo（黑）先走
    if current_color == ai_color:
        g = _gnugo_games[game_id]
        with g['lock']:
            try:
                mv = _genmove_with_profile(proc, ai_color, size, level)
            except TimeoutError:
                _cleanup_gnugo(game_id, uid)
                return jsonify({
                    'error': '這台免費 VM 計算 19 路局面太久，已自動結束此盤。請改用 9 路/13 路，或降低難度。',
                    'error_type': 'gnugo_timeout',
                }), 504
        if mv and mv.upper() != 'RESIGN':
            xy = _gtp_to_xy(mv, size)
            result['ai_first'] = {'gtp': mv.upper(), 'xy': xy, 'color': ai_color}
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

    g = _get_user_gnugo_game(game_id)
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
        try:
            ai_resp = _genmove_with_profile(proc, acol, size, g.get('level', 5))
        except TimeoutError:
            _cleanup_gnugo(game_id, session.get('user_id'))
            return jsonify({
                'error': '這台免費 VM 計算 19 路局面太久，已自動結束此盤。請改用 9 路/13 路，或降低難度。',
                'error_type': 'gnugo_timeout',
                'game_over': True,
            }), 504
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
    g = _get_user_gnugo_game(game_id)
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
        try:
            ai_resp = _genmove_with_profile(proc, acol, size, g.get('level', 5))
        except TimeoutError:
            _cleanup_gnugo(game_id, session.get('user_id'))
            return jsonify({
                'error': '這台免費 VM 計算 19 路局面太久，已自動結束此盤。請改用 9 路/13 路，或降低難度。',
                'error_type': 'gnugo_timeout',
                'game_over': True,
            }), 504
        ai_resp = ai_resp.upper().strip()
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
    g = _get_user_gnugo_game(game_id)
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
    g = _get_user_gnugo_game(game_id)
    if not g:
        return jsonify({'error': '對局不存在'}), 404

    with g['lock']:
        resp = _gtp(g['proc'], 'estimate_score')

    if not resp:
        return jsonify({'ok': False, 'error': 'GnuGo 無法估算目前局面，請再下一手後重試'}), 500
    return jsonify({'ok': True, 'estimate': resp.strip()})


@app.route('/api/bot/resign', methods=['POST'])
@login_required
def bot_resign():
    """玩家認輸"""
    data    = request.get_json() or {}
    game_id = data.get('game_id')
    _cleanup_gnugo(game_id, session.get('user_id'))
    return jsonify({'ok': True, 'game_over': True, 'winner': 'AI'})


def _parse_final_score(score: str) -> dict:
    text = str(score or '').strip().upper()
    m = re.match(r'^([BW])\s*\+\s*([0-9]+(?:\.[0-9]+)?)$', text)
    if not m:
        return {}
    winner = 'black' if m.group(1) == 'B' else 'white'
    diff = float(m.group(2))
    diff = round(diff, 1)
    if float(diff).is_integer():
        diff = int(diff)
    return {
        'winner_color': winner,
        'score_diff': diff,
        'result_text': f'{m.group(1)}+{diff}',
    }


@app.route('/api/bot/score', methods=['POST'])
@login_required
def bot_score():
    """請求終局計分"""
    data    = request.get_json() or {}
    game_id = data.get('game_id')
    g = _get_user_gnugo_game(game_id)
    if not g:
        return jsonify({'error': '對局不存在'}), 404
    with g['lock']:
        score = _gtp(g['proc'], 'final_score').strip()
    payload = {'ok': True, 'score': score}
    payload.update(_parse_final_score(score))
    return jsonify(payload)


@app.route('/api/bot/end', methods=['POST'])
@login_required
def bot_end():
    """結束並清理對局"""
    data    = request.get_json() or {}
    game_id = data.get('game_id')
    _cleanup_gnugo(game_id, session.get('user_id'))
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
        return jsonify({'error': 'GnuGo 未安裝，請確認伺服器已安裝 gnugo'}), 500
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

# ══════════════════════════════════════════════════════════════
# 商城系統（金幣經濟：賺取上限 / 道具 / 每日輪換 / 扭蛋）
# 設計原則：學習道具優先、零 P2W（不賣分數/段位/Elo）
# ══════════════════════════════════════════════════════════════

SHOP_ITEMS = {
    'hint_ticket': {
        'key': 'hint_ticket', 'price': 30, 'icon': '💡',
        'name': '小提示卷', 'name_en': 'Hint Ticket',
        'desc': '作答時顯示下一手正解位置', 'desc_en': 'Reveal the next correct move',
        'usable': 'in_question', 'category': 'training',
    },
    'premium_hint_bundle': {
        'key': 'premium_hint_bundle', 'price': 130, 'icon': '🎁',
        'name': '高級提示包', 'name_en': 'Premium Hint Bundle',
        'desc': '購買即獲得小提示卷 ×5', 'desc_en': 'Grants 5 hint tickets',
        'usable': 'instant', 'category': 'training',
        'grants_items': {'hint_ticket': 5},
    },
    'ai_explain_ticket': {
        'key': 'ai_explain_ticket', 'price': 50, 'icon': '🔍',
        'name': 'AI 解說券', 'name_en': 'AI Analysis Ticket',
        'desc': '免費玩家也能看一次 KataGo AI 解析（答題後自動使用）',
        'desc_en': 'One KataGo AI analysis for free players (auto-used)',
        'usable': 'auto', 'category': 'training',
    },
    'ai_explain_ticket_bundle': {
        'key': 'ai_explain_ticket_bundle', 'price': 135, 'icon': '🔎',
        'name': 'AI 解說券包', 'name_en': 'AI Analysis Bundle',
        'desc': '購買即獲得 AI 解說券 ×3', 'desc_en': 'Grants 3 AI analysis tickets',
        'usable': 'instant', 'category': 'training',
        'grants_items': {'ai_explain_ticket': 3},
    },
    'extra_questions_small': {
        'key': 'extra_questions_small', 'price': 60, 'icon': '📜',
        'name': '小型修行令', 'name_en': 'Small Training Pass',
        'desc': '使用後今日免費題數上限 +5', 'desc_en': '+5 to today\'s free question limit',
        'usable': 'activate', 'category': 'training',
        'effect': {'key': 'extra_questions', 'value': 5, 'scope': 'today'},
    },
    'extra_questions': {
        'key': 'extra_questions', 'price': 100, 'icon': '➕',
        'name': '加題券', 'name_en': 'Extra Questions Ticket',
        'desc': '使用後今日免費題數上限 +10', 'desc_en': '+10 to today\'s free question limit',
        'usable': 'activate', 'category': 'training',
        'effect': {'key': 'extra_questions', 'value': 10, 'scope': 'today'},
    },
    'grand_training_pass': {
        'key': 'grand_training_pass', 'price': 180, 'icon': '📚',
        'name': '大型修行令', 'name_en': 'Grand Training Pass',
        'desc': '使用後今日免費題數上限 +20', 'desc_en': '+20 to today\'s free question limit',
        'usable': 'activate', 'category': 'training',
        'effect': {'key': 'extra_questions', 'value': 20, 'scope': 'today'},
    },
    'small_xp_potion': {
        'key': 'small_xp_potion', 'price': 70, 'icon': '🧪',
        'name': '小 XP 藥水', 'name_en': 'Small XP Potion',
        'desc': '啟用後 20 分鐘內答題 XP ×1.25', 'desc_en': 'XP ×1.25 for 20 minutes',
        'usable': 'activate', 'category': 'growth',
        'effect': {'key': 'xp_potion', 'value': 1.25, 'minutes': 20},
    },
    'xp_potion': {
        'key': 'xp_potion', 'price': 120, 'icon': '🧪',
        'name': 'XP 藥水', 'name_en': 'XP Potion',
        'desc': '啟用後 30 分鐘內答題 XP ×1.5', 'desc_en': 'XP ×1.5 for 30 minutes',
        'usable': 'activate', 'category': 'growth',
        'effect': {'key': 'xp_potion', 'value': 1.5, 'minutes': 30},
    },
    'grand_xp_potion': {
        'key': 'grand_xp_potion', 'price': 220, 'icon': '⚗️',
        'name': '大型 XP 藥水', 'name_en': 'Grand XP Potion',
        'desc': '啟用後 60 分鐘內答題 XP ×1.5', 'desc_en': 'XP ×1.5 for 60 minutes',
        'usable': 'activate', 'category': 'growth',
        'effect': {'key': 'xp_potion', 'value': 1.5, 'minutes': 60},
    },
    'streak_shield': {
        'key': 'streak_shield', 'price': 80, 'icon': '🛡️',
        'name': '連勝護盾', 'name_en': 'Streak Shield',
        'desc': '啟用後，下一次答錯不中斷連擊（combo）',
        'desc_en': 'Next wrong answer will not break your combo',
        'usable': 'activate', 'category': 'guard',
        'effect': {'key': 'streak_shield', 'value': 1},
    },
    'double_streak_shield': {
        'key': 'double_streak_shield', 'price': 150, 'icon': '🛡️',
        'name': '雙層護盾', 'name_en': 'Double Streak Shield',
        'desc': '啟用後，接下來兩次答錯不中斷連擊',
        'desc_en': 'Next two wrong answers will not break your combo',
        'usable': 'activate', 'category': 'guard',
        'effect': {'key': 'streak_shield', 'value': 2},
    },
    'pet_snack': {
        'key': 'pet_snack', 'price': 60, 'icon': '🍖',
        'name': '寵物糖果包', 'name_en': 'Pet Candy Pouch',
        'desc': '購買即獲得棋魂糖 ×3（到寵物頁餵食）',
        'desc_en': 'Grants 3 Go Spirit Candies for your pet',
        'usable': 'instant', 'category': 'pet',
        'grants_food': {'go_spirit_candy': 3},
    },
    'starfruit_basket': {
        'key': 'starfruit_basket', 'price': 110, 'icon': '⭐',
        'name': '星果籃', 'name_en': 'Star Fruit Basket',
        'desc': '購買即獲得星果 ×3（到寵物頁餵食）',
        'desc_en': 'Grants 3 Star Fruits for your pet',
        'usable': 'instant', 'category': 'pet',
        'grants_food': {'starfruit': 3},
    },
    'moon_dew_vial': {
        'key': 'moon_dew_vial', 'price': 140, 'icon': '🌙',
        'name': '月露瓶', 'name_en': 'Moon Dew Vial',
        'desc': '購買即獲得月露 ×3（到寵物頁餵食）',
        'desc_en': 'Grants 3 Moon Drops for your pet',
        'usable': 'instant', 'category': 'pet',
        'grants_food': {'moon_drop': 3},
    },
    'pet_feast_box': {
        'key': 'pet_feast_box', 'price': 230, 'icon': '🍱',
        'name': '寵物豪華餐盒', 'name_en': 'Pet Feast Box',
        'desc': '購買即獲得棋魂糖 ×3、星果 ×2、月露 ×1',
        'desc_en': 'Grants 3 candies, 2 star fruits, and 1 moon drop',
        'usable': 'instant', 'category': 'pet',
        'grants_food': {'go_spirit_candy': 3, 'starfruit': 2, 'moon_drop': 1},
    },
    'rare_appearance_fragment': {
        'key': 'rare_appearance_fragment', 'price': 980, 'icon': '✨',
        'name': '稀有外觀碎片', 'name_en': 'Rare Appearance Fragment',
        'desc': '使用後可解鎖一件尚未擁有的常見或稀有外觀',
        'desc_en': 'Redeem for one missing common or uncommon appearance',
        'usable': 'activate', 'category': 'collection',
        'shop_pool': 'weekly', 'gacha_drop': False,
        'effect': {'key': 'appearance_fragment', 'value': 1},
    },
    'pet_evolution_core': {
        'key': 'pet_evolution_core', 'price': 1180, 'icon': '🌱',
        'name': '寵物進化素材', 'name_en': 'Pet Evolution Core',
        'desc': '使用後提供寵物成長經驗，並推進進化',
        'desc_en': 'Grants pet growth XP and pushes evolution forward',
        'usable': 'activate', 'category': 'pet',
        'shop_pool': 'weekly', 'gacha_drop': False,
        'effect': {'key': 'pet_xp', 'value': 35},
    },
    'ai_analysis_pack': {
        'key': 'ai_analysis_pack', 'price': 860, 'icon': '🧠',
        'name': 'AI 解析包', 'name_en': 'AI Analysis Pack',
        'desc': '購買即獲得 AI 解說券 ×5',
        'desc_en': 'Grants 5 AI explanation tickets',
        'usable': 'instant', 'category': 'training',
        'shop_pool': 'weekly', 'gacha_drop': False,
        'grants_items': {'ai_explain_ticket': 5},
    },
    'collector_archive_crate': {
        'key': 'collector_archive_crate', 'price': 3200, 'icon': '📦',
        'name': '收藏典藏箱', 'name_en': 'Collector Archive Crate',
        'desc': '購買即獲得稀有外觀碎片 ×4、AI 解說券 ×8',
        'desc_en': 'Grants 4 rare appearance fragments and 8 AI explanation tickets',
        'usable': 'instant', 'category': 'collection',
        'shop_pool': 'monthly', 'gacha_drop': False,
        'grants_items': {'rare_appearance_fragment': 4, 'ai_explain_ticket': 8},
    },
    'growth_vault': {
        'key': 'growth_vault', 'price': 6000, 'icon': '🗃️',
        'name': '成長寶庫', 'name_en': 'Growth Vault',
        'desc': '購買即獲得寵物進化素材 ×6、稀有外觀碎片 ×2',
        'desc_en': 'Grants 6 pet evolution cores and 2 rare appearance fragments',
        'usable': 'instant', 'category': 'pet',
        'shop_pool': 'monthly', 'gacha_drop': False,
        'grants_items': {'pet_evolution_core': 6, 'rare_appearance_fragment': 2},
    },
}

_COIN_DAILY_CAP          = 500   # 每日金幣收入總上限（防刷題農幣）
_COIN_MONSTER_DAILY_CAP  = 40    # 怪物擊殺金幣每日上限
_COIN_PER_DAILY_QUEST    = 15    # 每完成一個每日任務
_COIN_ALL_QUESTS_BONUS   = 50    # 每日任務全完成加碼
_COIN_PER_MONSTER        = 2     # 每擊殺一隻怪物
_GACHA_COST              = 150   # 扭蛋單抽
_GACHA_PITY              = 30    # 30 抽內保底 Uncommon

def _now_iso():
    return datetime.datetime.now().isoformat(timespec='seconds')

def _coin_balance(conn, uid) -> int:
    row = conn.execute('SELECT coins FROM user_stats WHERE user_id=?', (uid,)).fetchone()
    return int(row['coins'] or 0) if row else 0

def _coins_earned_today(conn, uid, reason_prefix=None) -> int:
    today = datetime.date.today().isoformat()
    if reason_prefix:
        row = conn.execute(
            "SELECT COALESCE(SUM(delta),0) AS s FROM currency_log "
            "WHERE user_id=? AND delta>0 AND created_at>=? AND reason LIKE ?",
            (uid, today, reason_prefix + '%')).fetchone()
    else:
        row = conn.execute(
            "SELECT COALESCE(SUM(delta),0) AS s FROM currency_log "
            "WHERE user_id=? AND delta>0 AND created_at>=?",
            (uid, today)).fetchone()
    return int(row['s'] or 0)

def _grant_coins(conn, uid, amount, reason, bypass_daily_cap=False) -> int:
    """發金幣。預設受每日總上限約束（一般遊戲內收入一律用預設值，
    行為不變）。bypass_daily_cap=True 僅供內部系統獎勵（如社群排行榜
    獎勵）呼叫，略過每日上限——沒有任何公開 API 會把使用者輸入直接
    傳進這個參數。回傳實際發放數。"""
    if amount <= 0:
        return 0
    if bypass_daily_cap:
        granted_amount = amount
    else:
        earned = _coins_earned_today(conn, uid)
        granted_amount = min(amount, max(0, _COIN_DAILY_CAP - earned))
    if granted_amount <= 0:
        return 0
    conn.execute('INSERT OR IGNORE INTO user_stats(user_id) VALUES(?)', (uid,))
    conn.execute('UPDATE user_stats SET coins=COALESCE(coins,0)+? WHERE user_id=?', (granted_amount, uid))
    bal = _coin_balance(conn, uid)
    conn.execute('INSERT INTO currency_log(user_id,delta,balance_after,reason,created_at) '
                 'VALUES(?,?,?,?,?)', (uid, granted_amount, bal, reason, _now_iso()))
    return granted_amount

def _spend_coins(conn, uid, amount, reason) -> bool:
    """扣金幣；餘額不足回 False（不寫入）。"""
    bal = _coin_balance(conn, uid)
    if bal < amount:
        return False
    conn.execute('UPDATE user_stats SET coins=coins-? WHERE user_id=?', (amount, uid))
    conn.execute('INSERT INTO currency_log(user_id,delta,balance_after,reason,created_at) '
                 'VALUES(?,?,?,?,?)', (uid, -amount, bal - amount, reason, _now_iso()))
    return True

def _inv_add(conn, uid, item_key, qty=1):
    conn.execute(
        'INSERT INTO shop_inventory(user_id,item_key,qty) VALUES(?,?,?) '
        'ON CONFLICT(user_id,item_key) DO UPDATE SET qty=shop_inventory.qty+?',
        (uid, item_key, qty, qty))

def _inv_consume(conn, uid, item_key, qty=1) -> bool:
    row = conn.execute('SELECT qty FROM shop_inventory WHERE user_id=? AND item_key=?',
                       (uid, item_key)).fetchone()
    if not row or (row['qty'] or 0) < qty:
        return False
    conn.execute('UPDATE shop_inventory SET qty=qty-? WHERE user_id=? AND item_key=?',
                 (qty, uid, item_key))
    return True

def _grant_shop_purchase(conn, uid, item, qty=1):
    """Grant direct bundles immediately; otherwise add the shop item itself."""
    granted_items = []
    granted_food = []
    for key, amount in (item.get('grants_items') or {}).items():
        total = int(amount) * qty
        _inv_add(conn, uid, key, total)
        granted_items.append({'item_key': key, 'qty': total})
    for key, amount in (item.get('grants_food') or {}).items():
        total = int(amount) * qty
        _grant_pet_food(conn, uid, key, total)
        granted_food.append({'item_key': key, 'qty': total})
    if not granted_items and not granted_food:
        _inv_add(conn, uid, item['key'], qty)
        granted_items.append({'item_key': item['key'], 'qty': qty})
    return granted_items, granted_food

def grant_community_reward_badge(conn, *, user_id, badge_key, claim_id=None, context=None):
    """Award a community-leaderboard-reward badge. Thin wrapper over the
    existing badges_earned(user_id, badge_id, earned_at, seen) one-time-
    ownership table (PRIMARY KEY(user_id, badge_id)); `INSERT OR IGNORE`
    makes a duplicate call for an already-owned badge a harmless no-op."""
    conn.execute(
        'INSERT OR IGNORE INTO badges_earned(user_id,badge_id,earned_at,seen) VALUES(?,?,?,0)',
        (user_id, badge_key, _now_iso()))

def is_community_reward_badge_owned(conn, *, user_id, badge_key):
    """Read-only: does user_id already own badge_key in badges_earned?"""
    return conn.execute(
        'SELECT 1 FROM badges_earned WHERE user_id=? AND badge_id=?',
        (user_id, badge_key)).fetchone() is not None

def _effect_get(conn, uid, effect_key):
    """取得仍有效的效果列（時效未過 / 當日有效 / 一次性未消耗）。"""
    now = _now_iso()
    today = datetime.date.today().isoformat()
    return conn.execute(
        'SELECT * FROM active_effects WHERE user_id=? AND effect_key=? '
        'AND (expires_at IS NULL OR expires_at > ?) '
        'AND (effect_date IS NULL OR effect_date = ?) '
        'ORDER BY id DESC LIMIT 1',
        (uid, effect_key, now, today)).fetchone()

def _effect_remove(conn, uid, effect_id):
    conn.execute('DELETE FROM active_effects WHERE id=? AND user_id=?', (effect_id, uid))

def _extra_questions_today(conn, uid) -> int:
    """加題券：今日累計加成題數。"""
    today = datetime.date.today().isoformat()
    row = conn.execute(
        'SELECT COALESCE(SUM(value),0) AS s FROM active_effects '
        'WHERE user_id=? AND effect_key=? AND effect_date=?',
        (uid, 'extra_questions', today)).fetchone()
    return int(row['s'] or 0)


def _shop_items_for_pool(pool_name):
    return [item for item in SHOP_ITEMS.values() if item.get('shop_pool', 'daily') == pool_name]


def _shop_daily_items():
    return _shop_items_for_pool('daily')


def _shop_weekly_items():
    return _shop_items_for_pool('weekly')


def _shop_monthly_items():
    return _shop_items_for_pool('monthly')


def _shop_gacha_items():
    return [item for item in SHOP_ITEMS.values() if item.get('gacha_drop', True)]


def _gacha_collection_progress(conn, uid):
    owned = {
        r['item_id'] for r in conn.execute(
            'SELECT item_id FROM player_wardrobe WHERE user_id=?', (uid,)
        ).fetchall()
    }
    pool = [a for a in APPEARANCE_DEFS if a.get('rarity') in ('common', 'uncommon')]
    rarity_totals = {'common': 0, 'uncommon': 0}
    rarity_owned = {'common': 0, 'uncommon': 0}
    missing = []
    for item in pool:
        rarity = item.get('rarity', 'common')
        rarity_totals[rarity] = rarity_totals.get(rarity, 0) + 1
        if item['id'] in owned:
            rarity_owned[rarity] = rarity_owned.get(rarity, 0) + 1
        elif len(missing) < 4:
            missing.append({
                'id': item['id'],
                'name': item.get('name', item['id']),
                'rarity': rarity,
            })
    total = len(pool)
    owned_count = sum(rarity_owned.values())
    return {
        'owned': owned_count,
        'total': total,
        'percent': round(owned_count / total * 100) if total else 0,
        'rarity_totals': rarity_totals,
        'rarity_owned': rarity_owned,
        'missing': missing,
    }

# ── 商城 API ─────────────────────────────────────────────────

@app.route('/api/shop/catalog')
@login_required
def shop_catalog():
    uid = session['user_id']
    with get_db() as conn:
        bal = _coin_balance(conn, uid)
        earned = _coins_earned_today(conn, uid)
        inv_rows = conn.execute(
            'SELECT item_key, qty FROM shop_inventory WHERE user_id=? AND qty>0', (uid,)).fetchall()
        slots = _daily_shop_slots(conn)
        pity = _gacha_pity_count(conn, uid)
        collection = _gacha_collection_progress(conn, uid)
    return jsonify({
        'coins': bal,
        'earned_today': earned,
        'daily_cap': _COIN_DAILY_CAP,
        'items': list(SHOP_ITEMS.values()),
        'daily_items': _shop_daily_items(),
        'weekly_items': _shop_weekly_items(),
        'monthly_items': _shop_monthly_items(),
        'inventory': {r['item_key']: r['qty'] for r in inv_rows},
        'daily_slots': slots if not is_premium(uid) else slots,   # 全列給前端，免費版前端只顯示 3 格
        'daily_slots_visible': 5 if is_premium(uid) else 3,
        'gacha': {'cost': _GACHA_COST, 'pity': _GACHA_PITY, 'pity_count': pity,
                  'rates': {'item': 0.60, 'pet_food': 0.25, 'common': 0.12, 'uncommon': 0.03}},
        'gacha_collection': collection,
    })

@app.route('/api/shop/buy', methods=['POST'])
@login_required
def shop_buy():
    uid  = session['user_id']
    body = request.get_json(silent=True) or {}
    item_key = str(body.get('item_key') or '')
    qty      = max(1, min(10, int(body.get('qty') or 1)))
    item = SHOP_ITEMS.get(item_key)
    if not item:
        return jsonify({'error': 'unknown_item'}), 400
    price = item['price']
    # 每日輪換折扣
    with get_db() as conn:
        slots = _daily_shop_slots(conn)
        for s in slots:
            if s['item_key'] == item_key:
                price = s['price']
                break
        total = price * qty
        if not _spend_coins(conn, uid, total, f'buy:{item_key}x{qty}'):
            return jsonify({'error': 'insufficient_coins', 'coins': _coin_balance(conn, uid)}), 400
        granted_items, granted_food = _grant_shop_purchase(conn, uid, item, qty)
        conn.commit()
        bal = _coin_balance(conn, uid)
    return jsonify({'ok': True, 'coins': bal, 'item_key': item_key, 'qty': qty,
                    'granted_items': granted_items, 'granted_food': granted_food})

@app.route('/api/shop/use', methods=['POST'])
@login_required
def shop_use():
    uid  = session['user_id']
    body = request.get_json(silent=True) or {}
    item_key = str(body.get('item_key') or '')
    item = SHOP_ITEMS.get(item_key)
    if not item:
        return jsonify({'error': 'unknown_item'}), 400
    now = datetime.datetime.now()
    usable = item.get('usable')
    effect = item.get('effect') or {}
    with get_db() as conn:
        if usable in ('instant', 'auto'):
            return jsonify({'error': 'auto_use_only',
                            'message': '這個道具不需要手動使用'}), 400
        if effect.get('key') == 'xp_potion' and _effect_get(conn, uid, 'xp_potion'):
            return jsonify({'error': 'effect_active', 'message': '已有生效中的 XP 藥水'}), 400
        if effect.get('key') == 'streak_shield' and _effect_get(conn, uid, 'streak_shield'):
            return jsonify({'error': 'effect_active', 'message': '護盾已在身上'}), 400
        if not _inv_consume(conn, uid, item_key):
            return jsonify({'error': 'not_owned'}), 400

        result = {'ok': True, 'item_key': item_key}
        if usable == 'in_question':
            result['effect'] = 'hint'          # 前端據此顯示正解
        elif effect.get('key') == 'appearance_fragment':
            rarity_pool = [a for a in APPEARANCE_DEFS if a.get('rarity') in ('common', 'uncommon')]
            owned = {
                r['item_id'] for r in conn.execute(
                    'SELECT item_id FROM player_wardrobe WHERE user_id=?', (uid,)
                ).fetchall()
            }
            missing_pool = [a for a in rarity_pool if a['id'] not in owned]
            pick = random.choice(missing_pool) if missing_pool else None
            if pick:
                conn.execute(
                    'INSERT OR IGNORE INTO player_wardrobe(user_id,item_id,obtained_at,source) VALUES(?,?,?,?)',
                    (uid, pick['id'], _now_iso(), 'fragment')
                )
                result['effect'] = 'appearance_fragment'
                result['reward'] = 'appearance'
                result['reward_item'] = pick['id']
                result['reward_name'] = pick.get('name', pick['id'])
                result['reward_name_en'] = pick.get('name_en', pick['name'])
                result['reward_rarity'] = pick.get('rarity', 'common')
                result['new_item'] = True
            else:
                refund = _grant_coins(conn, uid, 120, 'fragment:fallback')
                result['effect'] = 'appearance_fragment'
                result['reward'] = 'coins'
                result['reward_coins'] = refund
        elif effect.get('key') == 'pet_xp':
            xp_gain = int(effect.get('value') or 0)
            pet_growth = _add_pet_xp(conn, uid, xp_gain)
            result['effect'] = 'pet_xp'
            result['value'] = xp_gain
            if pet_growth:
                result['pet_level'] = pet_growth.get('level')
                result['pet_xp'] = pet_growth.get('xp')
                result['pet_leveled'] = pet_growth.get('leveled', 0)
        elif effect.get('key') == 'streak_shield':
            value = int(effect.get('value') or 1)
            conn.execute('INSERT INTO active_effects(user_id,effect_key,value,created_at) '
                         'VALUES(?,?,?,?)', (uid, 'streak_shield', value, _now_iso()))
            result['effect'] = 'streak_shield'
            result['value'] = value
        elif effect.get('key') == 'extra_questions':
            value = int(effect.get('value') or 0)
            conn.execute('INSERT INTO active_effects(user_id,effect_key,value,effect_date,created_at) '
                         'VALUES(?,?,?,?,?)', (uid, 'extra_questions', value,
                                                datetime.date.today().isoformat(), _now_iso()))
            result['effect'] = 'extra_questions'
            result['value'] = value
            result['extra_today'] = _extra_questions_today(conn, uid)
        elif effect.get('key') == 'xp_potion':
            value = float(effect.get('value') or 1.5)
            minutes = int(effect.get('minutes') or 30)
            exp = (now + datetime.timedelta(minutes=minutes)).isoformat(timespec='seconds')
            conn.execute('INSERT INTO active_effects(user_id,effect_key,value,expires_at,created_at) '
                         'VALUES(?,?,?,?,?)', (uid, 'xp_potion', value, exp, _now_iso()))
            result['effect'] = 'xp_potion'
            result['value'] = value
            result['expires_at'] = exp
        else:
            _inv_add(conn, uid, item_key, 1)
            return jsonify({'error': 'not_usable',
                            'message': '這個道具目前沒有可手動使用的效果'}), 400
        conn.commit()
        row = conn.execute('SELECT qty FROM shop_inventory WHERE user_id=? AND item_key=?',
                           (uid, item_key)).fetchone()
        result['remaining'] = (row['qty'] if row else 0) or 0
    return jsonify(result)

@app.route('/api/shop/status')
@login_required
def shop_status():
    """作答頁輕量查詢：持有道具數量 + 生效中的效果。"""
    uid = session['user_id']
    with get_db() as conn:
        inv_rows = conn.execute(
            'SELECT item_key, qty FROM shop_inventory WHERE user_id=? AND qty>0', (uid,)).fetchall()
        shield = _effect_get(conn, uid, 'streak_shield')
        potion = _effect_get(conn, uid, 'xp_potion')
        extra  = _extra_questions_today(conn, uid)
        bal    = _coin_balance(conn, uid)
    return jsonify({
        'coins': bal,
        'inventory': {r['item_key']: r['qty'] for r in inv_rows},
        'shield_active': bool(shield),
        'shield_remaining': int(shield['value'] or 0) if shield else 0,
        'xp_potion_until': potion['expires_at'] if potion else None,
        'xp_potion_mult': float(potion['value'] or 1) if potion else 1,
        'extra_questions_today': extra,
    })

# ── 每日輪換商店 ─────────────────────────────────────────────

def _daily_shop_slots(conn):
    """取得今日輪換 5 格（前 3 格人人可見，4-5 格 Premium）。
    內容：隨機 3 件道具打 8 折 + 2 件 Common/Uncommon 外觀（金幣直購）。"""
    today = datetime.date.today().isoformat()
    row = conn.execute('SELECT slots FROM daily_shop WHERE shop_date=?', (today,)).fetchone()
    if row:
        try:
            return json.loads(row['slots'])
        except Exception:
            pass
    rng = random.Random(today)            # 以日期為種子 → 全服同步、可重現
    daily_keys = [item['key'] for item in _shop_daily_items()]
    item_keys = rng.sample(daily_keys, min(3, len(daily_keys)))
    slots = []
    for k in item_keys:
        it = SHOP_ITEMS[k]
        slots.append({'type': 'item', 'item_key': k, 'icon': it['icon'],
                      'name': it['name'], 'name_en': it['name_en'],
                      'orig_price': it['price'], 'price': int(it['price'] * 0.8)})
    pool = [a for a in APPEARANCE_DEFS if a.get('rarity') in ('common', 'uncommon')]
    if pool:
        for a in rng.sample(pool, min(2, len(pool))):
            price = 200 if a['rarity'] == 'common' else 450
            slots.append({'type': 'appearance', 'item_key': a['id'],
                          'icon': a.get('emoji', '🎽'), 'name': a['name'],
                          'name_en': a.get('name_en', a['name']),
                          'rarity': a['rarity'], 'price': price})
    try:
        conn.execute('INSERT INTO daily_shop(shop_date,slots) VALUES(?,?) '
                     'ON CONFLICT(shop_date) DO NOTHING', (today, json.dumps(slots, ensure_ascii=False)))
    except Exception:
        pass
    return slots

@app.route('/api/shop/buy_appearance', methods=['POST'])
@login_required
def shop_buy_appearance():
    """購買每日輪換中的外觀（只能買今日輪換出現的）。"""
    uid  = session['user_id']
    body = request.get_json(silent=True) or {}
    item_id = str(body.get('item_id') or '')
    with get_db() as conn:
        slot = next((s for s in _daily_shop_slots(conn)
                     if s['type'] == 'appearance' and s['item_key'] == item_id), None)
        if not slot:
            return jsonify({'error': 'not_in_rotation'}), 400
        owned = conn.execute('SELECT id FROM player_wardrobe WHERE user_id=? AND item_id=?',
                             (uid, item_id)).fetchone()
        if owned:
            return jsonify({'error': 'already_owned'}), 400
        if not _spend_coins(conn, uid, slot['price'], f'buy_appearance:{item_id}'):
            return jsonify({'error': 'insufficient_coins', 'coins': _coin_balance(conn, uid)}), 400
        conn.execute('INSERT INTO player_wardrobe(user_id,item_id,obtained_at,source) VALUES(?,?,?,?)',
                     (uid, item_id, _now_iso(), 'shop'))
        conn.commit()
        bal = _coin_balance(conn, uid)
    return jsonify({'ok': True, 'coins': bal, 'item_id': item_id})

# ── 扭蛋 ─────────────────────────────────────────────────────

def _gacha_pity_count(conn, uid) -> int:
    """距離上一次 Uncommon（或更好）出貨後的抽數。"""
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM gacha_log WHERE user_id=? AND id > "
        "COALESCE((SELECT MAX(id) FROM gacha_log WHERE user_id=? AND rarity='uncommon'), 0)",
        (uid, uid)).fetchone()
    return int(row['n'] or 0)

@app.route('/api/shop/gacha', methods=['POST'])
@login_required
def shop_gacha():
    """金幣扭蛋：道具 60% / 寵物食物 25% / Common 外觀 12% / Uncommon 外觀 3%。
    30 抽保底 Uncommon；已擁有的外觀重複時轉為金幣回饋（Common 80 / Uncommon 180）。"""
    uid = session['user_id']
    with get_db() as conn:
        if not _spend_coins(conn, uid, _GACHA_COST, 'gacha'):
            return jsonify({'error': 'insufficient_coins', 'coins': _coin_balance(conn, uid)}), 400

        pity = _gacha_pity_count(conn, uid)
        force_uncommon = (pity + 1 >= _GACHA_PITY)

        r = random.random()
        if force_uncommon:
            bucket = 'uncommon'
        elif r < 0.60:
            bucket = 'item'
        elif r < 0.85:
            bucket = 'pet_food'
        elif r < 0.97:
            bucket = 'common'
        else:
            bucket = 'uncommon'

        result = {'bucket': bucket}
        rarity = None
        if bucket == 'item':
            gacha_items = _shop_gacha_items()
            k = random.choice([item['key'] for item in gacha_items]) if gacha_items else None
            if not k:
                _grant_coins(conn, uid, 100, 'gacha:fallback')
                result.update({'type': 'coins', 'qty': 100})
                rarity = None
                new_pity = 0 if rarity == 'uncommon' else pity + 1
                conn.execute('INSERT INTO gacha_log(user_id,pool,result_key,result_type,rarity,pity_count,created_at) '
                             'VALUES(?,?,?,?,?,?,?)',
                             (uid, 'koin', result.get('key', result.get('type', '')),
                              result.get('type', ''), rarity, new_pity, _now_iso()))
                conn.commit()
                bal = _coin_balance(conn, uid)
                result.update({'ok': True, 'coins': bal,
                               'pity_count': new_pity, 'pity_max': _GACHA_PITY})
                return jsonify(result)
            it = SHOP_ITEMS[k]
            granted_items, granted_food = _grant_shop_purchase(conn, uid, it, 1)
            result.update({'type': 'item', 'key': k, 'name': it['name'],
                           'name_en': it['name_en'], 'icon': it['icon'],
                           'granted_items': granted_items, 'granted_food': granted_food})
        elif bucket == 'pet_food':
            foods = list(PET_FOOD_CATALOG.keys())
            k = random.choice(foods)
            _grant_pet_food(conn, uid, k, 2)
            f = PET_FOOD_CATALOG[k]
            result.update({'type': 'pet_food', 'key': k, 'qty': 2,
                           'name': f.get('name'), 'name_en': f.get('name_en')})
        else:
            rarity = bucket
            pool = [a for a in APPEARANCE_DEFS if a.get('rarity') == rarity]
            pick = random.choice(pool) if pool else None
            if pick is None:
                _grant_coins(conn, uid, 100, 'gacha:fallback')
                result.update({'type': 'coins', 'qty': 100})
            else:
                owned = conn.execute(
                    'SELECT id FROM player_wardrobe WHERE user_id=? AND item_id=?',
                    (uid, pick['id'])).fetchone()
                if owned:
                    refund = 80 if rarity == 'common' else 180
                    # 重複轉金幣不受每日上限影響（是抽獎成本的部分返還）
                    conn.execute('UPDATE user_stats SET coins=COALESCE(coins,0)+? WHERE user_id=?',
                                 (refund, uid))
                    conn.execute('INSERT INTO currency_log(user_id,delta,balance_after,reason,created_at) '
                                 'VALUES(?,?,?,?,?)',
                                 (uid, refund, _coin_balance(conn, uid), f'gacha:dup:{pick["id"]}', _now_iso()))
                    result.update({'type': 'dup_coins', 'qty': refund,
                                   'key': pick['id'], 'name': pick['name'],
                                   'icon': pick.get('emoji', '🎽'), 'rarity': rarity})
                else:
                    conn.execute('INSERT INTO player_wardrobe(user_id,item_id,obtained_at,source) '
                                 'VALUES(?,?,?,?)', (uid, pick['id'], _now_iso(), 'gacha'))
                    result.update({'type': 'appearance', 'key': pick['id'], 'name': pick['name'],
                                   'name_en': pick.get('name_en', pick['name']),
                                   'icon': pick.get('emoji', '🎽'), 'rarity': rarity})

        new_pity = 0 if rarity == 'uncommon' else pity + 1
        conn.execute('INSERT INTO gacha_log(user_id,pool,result_key,result_type,rarity,pity_count,created_at) '
                     'VALUES(?,?,?,?,?,?,?)',
                     (uid, 'koin', result.get('key', result.get('type', '')),
                      result.get('type', ''), rarity, new_pity, _now_iso()))
        conn.commit()
        bal = _coin_balance(conn, uid)
    result.update({'ok': True, 'coins': bal,
                   'pity_count': new_pity, 'pity_max': _GACHA_PITY})
    return jsonify(result)


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


# ════════════════════════════════════════════════════════════════
#  金流：藍新定期定額（Premium 訂閱）
# ════════════════════════════════════════════════════════════════

PAY_PLANS = {
    'monthly': {'amount': 299,  'period_type': 'M', 'days': 31,
                'times': 99, 'desc': 'Go Odyssey Premium 月繳'},
    'annual':  {'amount': 2490, 'period_type': 'Y', 'days': 366,
                'times': 9,  'desc': 'Go Odyssey Premium 年繳'},
}


def _newebpay():
    import newebpay
    return newebpay


def _gen_mer_order_no(uid):
    """藍新 MerOrderNo 上限 20 字元、英數。GOS + uid + 秒級時間戳。"""
    return f'GOS{uid}T{int(time.time())}'[:20]


def _period_point(plan_key):
    """月繳：取今天日期（上限 28 避開月底）；年繳：今天月日（避開 0229）。"""
    today = datetime.date.today()
    if PAY_PLANS[plan_key]['period_type'] == 'M':
        return f'{min(today.day, 28):02d}'
    if today.month == 2 and today.day == 29:
        return '0228'
    return f'{today.month:02d}{today.day:02d}'


def _extend_premium(conn, uid, days, source):
    """延長 premium_until（從現有效期或現在起算較晚者），並開通 Premium。"""
    row = conn.execute(
        'SELECT plan, premium_until FROM users WHERE id=?', (uid,)).fetchone()
    if not row:
        return None
    now = datetime.datetime.now()
    base = now
    if row['premium_until']:
        try:
            cur = datetime.datetime.fromisoformat(row['premium_until'])
            if cur > now:
                base = cur
        except ValueError:
            pass
    new_until = (base + datetime.timedelta(days=days)).isoformat()
    first_time = row['plan'] != 'premium'
    conn.execute("UPDATE users SET plan='premium', premium_until=? WHERE id=?",
                 (new_until, uid))
    conn.commit()
    if first_time:
        grant_premium_rewards(uid, conn)
    try:
        print(f'[payment] uid={uid} premium 延長至 {new_until}（{source}）')
    except ValueError:
        pass
    return new_until


TRIAL_CODE_ALPHABET = '23456789ABCDEFGHJKLMNPQRSTUVWXYZ'
TRIAL_CODE_RE = re.compile(r'^[A-Z0-9][A-Z0-9-]{7,47}$')


def _trial_code_normalize(code):
    return re.sub(r'\s+', '', str(code or '')).upper()


def _trial_code_hash(code):
    return hashlib.sha256(_trial_code_normalize(code).encode('utf-8')).hexdigest()


def _trial_email_normalize(email):
    email = (email or '').strip().lower()
    return email if email and len(email) <= 254 and _EMAIL_RE.match(email) else ''


def _trial_parse_expires(value, default_days=60):
    raw = str(value or '').strip()
    if not raw:
        return (datetime.datetime.now() + datetime.timedelta(days=default_days)).isoformat(timespec='seconds')
    try:
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', raw):
            return datetime.datetime.fromisoformat(raw + 'T23:59:59').isoformat(timespec='seconds')
        return datetime.datetime.fromisoformat(raw).isoformat(timespec='seconds')
    except Exception:
        return None


def _trial_batch_key(raw, org_name='', campaign_name=''):
    source = raw or org_name or campaign_name or 'TRIAL'
    key = re.sub(r'[^A-Za-z0-9]+', '_', str(source).strip()).strip('_').upper()
    return (key or 'TRIAL')[:48]


def _trial_code_prefix(batch_key):
    first = (batch_key or 'TRIAL').split('_')[0]
    prefix = re.sub(r'[^A-Z0-9]', '', first.upper())[:10]
    return prefix or 'TRIAL'


def _trial_generate_code(prefix):
    def group(n=4):
        return ''.join(secrets.choice(TRIAL_CODE_ALPHABET) for _ in range(n))
    return f'{prefix}-{group()}-{group()}'


def _trial_public_code_row(row):
    return {
        'id': row['id'],
        'batch_id': row['batch_id'],
        'code_label': f"{row['code_prefix']}-****-{row['code_last4']}",
        'code_prefix': row['code_prefix'],
        'code_last4': row['code_last4'],
        'status': row['status'],
        'redeemed_by_user_id': row['redeemed_by_user_id'],
        'redeemed_by_email': row['redeemed_by_email'],
        'redeemed_at': row['redeemed_at'],
        'expires_at': row['expires_at'],
        'created_at': row['created_at'],
        'revoked_at': row['revoked_at'],
        'revoked_reason': row['revoked_reason'],
    }


def _trial_log_redemption(conn, code_id, user_id, email, result, reason=None):
    conn.execute(
        '''INSERT INTO trial_code_redemptions
           (code_id,user_id,email_normalized,result,error_reason,ip,user_agent,created_at)
           VALUES(?,?,?,?,?,?,?,?)''',
        (code_id, user_id, email or None, result, reason,
         _client_ip(), request.headers.get('User-Agent', '')[:500],
         datetime.datetime.now().isoformat(timespec='seconds')))


def _trial_error(conn, code_id, user_id, email, error, status=400):
    _trial_log_redemption(conn, code_id, user_id, email, 'failed', error)
    conn.commit()
    return jsonify({'error': error}), status


@app.route('/api/admin/trial-codes/batches', methods=['POST'])
@admin_required
def admin_trial_code_create_batch():
    data = request.get_json(silent=True) or {}
    try:
        count = int(data.get('count') or 0)
        days = int(data.get('days') or 30)
    except Exception:
        return jsonify({'error': 'invalid_number'}), 400
    if count < 1 or count > 500:
        return jsonify({'error': 'count_out_of_range'}), 400
    if days < 1 or days > 365:
        return jsonify({'error': 'days_out_of_range'}), 400
    expires_at = _trial_parse_expires(data.get('expires_at'))
    if not expires_at:
        return jsonify({'error': 'expires_at_invalid'}), 400

    campaign_name = str(data.get('campaign_name') or '').strip()[:120]
    org_name = str(data.get('org_name') or '').strip()[:120]
    note = str(data.get('note') or '').strip()[:1000]
    batch_key = _trial_batch_key(data.get('batch_key'), org_name, campaign_name)
    prefix = _trial_code_prefix(batch_key)
    now = datetime.datetime.now().isoformat(timespec='seconds')

    with get_db() as conn:
        exists = conn.execute('SELECT id FROM trial_code_batches WHERE batch_key=?',
                              (batch_key,)).fetchone()
        if exists:
            return jsonify({'error': 'batch_key_exists'}), 409
        cur = conn.execute(
            '''INSERT INTO trial_code_batches
               (batch_key,campaign_name,org_name,days,code_count,max_redemptions_per_code,
                expires_at,status,created_by_admin_id,created_at,note)
               VALUES(?,?,?,?,?,1,?,'active',?,?,?) RETURNING id''',
            (batch_key, campaign_name, org_name, days, count, expires_at,
             session['user_id'], now, note))
        batch_id = cur.fetchone()[0]
        codes = []
        attempts = 0
        while len(codes) < count and attempts < count * 5:
            attempts += 1
            code = _trial_generate_code(prefix)
            code_hash = _trial_code_hash(code)
            if conn.execute('SELECT id FROM trial_codes WHERE code_hash=?',
                            (code_hash,)).fetchone():
                continue
            conn.execute(
                '''INSERT INTO trial_codes
                   (batch_id,code_hash,code_prefix,code_last4,status,expires_at,created_at)
                   VALUES(?,?,?,?,?,?,?)''',
                (batch_id, code_hash, prefix, code[-4:], 'unused', expires_at, now))
            codes.append(code)
        if len(codes) != count:
            conn.rollback()
            return jsonify({'error': 'code_generation_failed'}), 500
        conn.commit()
    return jsonify({'ok': True, 'batch_id': batch_id, 'batch_key': batch_key,
                    'generated_count': len(codes), 'codes': codes})


@app.route('/api/admin/trial-codes/batches')
@admin_required
def admin_trial_code_batches():
    with get_db() as conn:
        rows = conn.execute(
            '''SELECT b.id,b.batch_key,b.campaign_name,b.org_name,b.days,b.code_count,
                      b.expires_at,b.status,b.created_at,b.note,
                      COALESCE(SUM(CASE WHEN c.status='unused' THEN 1 ELSE 0 END),0) AS unused_count,
                      COALESCE(SUM(CASE WHEN c.status='redeemed' THEN 1 ELSE 0 END),0) AS redeemed_count,
                      COALESCE(SUM(CASE WHEN c.status='revoked' THEN 1 ELSE 0 END),0) AS revoked_count
                 FROM trial_code_batches b
                 LEFT JOIN trial_codes c ON c.batch_id=b.id
                GROUP BY b.id,b.batch_key,b.campaign_name,b.org_name,b.days,b.code_count,
                         b.expires_at,b.status,b.created_at,b.note
                ORDER BY b.id DESC LIMIT 100''').fetchall()
    return jsonify({'ok': True, 'batches': [dict(r) for r in rows]})


@app.route('/api/admin/trial-codes/batches/<int:batch_id>')
@admin_required
def admin_trial_code_batch_detail(batch_id):
    with get_db() as conn:
        batch = conn.execute('SELECT * FROM trial_code_batches WHERE id=?',
                             (batch_id,)).fetchone()
        if not batch:
            return jsonify({'error': 'not_found'}), 404
        codes = conn.execute(
            'SELECT * FROM trial_codes WHERE batch_id=? ORDER BY id',
            (batch_id,)).fetchall()
    return jsonify({'ok': True, 'batch': dict(batch),
                    'codes': [_trial_public_code_row(r) for r in codes]})


@app.route('/api/admin/trial-codes/batches/<int:batch_id>/export')
@admin_required
def admin_trial_code_batch_export(batch_id):
    with get_db() as conn:
        batch = conn.execute('SELECT * FROM trial_code_batches WHERE id=?',
                             (batch_id,)).fetchone()
        if not batch:
            return jsonify({'error': 'not_found'}), 404
        codes = conn.execute(
            'SELECT * FROM trial_codes WHERE batch_id=? ORDER BY id',
            (batch_id,)).fetchall()
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(['batch_key', 'code_label', 'status', 'redeemed_by_email',
                     'redeemed_by_user_id', 'redeemed_at', 'expires_at',
                     'revoked_at', 'revoked_reason'])
    for row in codes:
        pub = _trial_public_code_row(row)
        writer.writerow([batch['batch_key'], pub['code_label'], pub['status'],
                         pub['redeemed_by_email'] or '', pub['redeemed_by_user_id'] or '',
                         pub['redeemed_at'] or '', pub['expires_at'] or '',
                         pub['revoked_at'] or '', pub['revoked_reason'] or ''])
    resp = Response(out.getvalue(), mimetype='text/csv; charset=utf-8')
    resp.headers['Content-Disposition'] = f'attachment; filename="{batch["batch_key"]}_trial_codes.csv"'
    return resp


@app.route('/api/admin/trial-codes/<int:code_id>/revoke', methods=['POST'])
@admin_required
def admin_trial_code_revoke(code_id):
    data = request.get_json(silent=True) or {}
    reason = str(data.get('reason') or 'admin revoked').strip()[:500]
    now = datetime.datetime.now().isoformat(timespec='seconds')
    with get_db() as conn:
        cur = conn.execute(
            "UPDATE trial_codes SET status='revoked', revoked_at=?, revoked_reason=? "
            "WHERE id=? AND status='unused'",
            (now, reason, code_id))
        conn.commit()
    if cur.rowcount < 1:
        return jsonify({'error': 'not_revokable'}), 400
    return jsonify({'ok': True, 'revoked': 1})


@app.route('/api/admin/trial-codes/batches/<int:batch_id>/revoke-all', methods=['POST'])
@admin_required
def admin_trial_code_revoke_batch(batch_id):
    data = request.get_json(silent=True) or {}
    reason = str(data.get('reason') or 'batch revoked').strip()[:500]
    now = datetime.datetime.now().isoformat(timespec='seconds')
    with get_db() as conn:
        batch = conn.execute('SELECT id FROM trial_code_batches WHERE id=?',
                             (batch_id,)).fetchone()
        if not batch:
            return jsonify({'error': 'not_found'}), 404
        cur = conn.execute(
            "UPDATE trial_codes SET status='revoked', revoked_at=?, revoked_reason=? "
            "WHERE batch_id=? AND status='unused'",
            (now, reason, batch_id))
        conn.execute("UPDATE trial_code_batches SET status='closed' WHERE id=?",
                     (batch_id,))
        conn.commit()
    return jsonify({'ok': True, 'revoked': cur.rowcount})


@app.route('/api/trial-codes/redeem', methods=['POST'])
@login_required
def trial_code_redeem():
    uid = session['user_id']
    ip = _client_ip()
    if _throttle_check(f'trial:{uid}', 12, 3600) or _throttle_check(f'trial:{ip}', 30, 3600):
        return jsonify({'error': 'rate_limited'}), 429
    data = request.get_json(silent=True) or {}
    code_raw = data.get('code') or ''
    code = _trial_code_normalize(code_raw)
    if not TRIAL_CODE_RE.match(code):
        _throttle_record(f'trial:{uid}')
        _throttle_record(f'trial:{ip}')
        return jsonify({'error': 'code_format_invalid'}), 400
    code_hash = _trial_code_hash(code)
    now = datetime.datetime.now().isoformat(timespec='seconds')

    with get_db() as conn:
        user = conn.execute(
            'SELECT id,email,email_verified FROM users WHERE id=?', (uid,)).fetchone()
        email = _trial_email_normalize(user['email'] if user else '')
        if not email:
            return _trial_error(conn, None, uid, None, 'email_required', 400)
        if not user['email_verified']:
            return _trial_error(conn, None, uid, email, 'email_unverified', 400)

        row = conn.execute(
            '''SELECT c.*,b.batch_key,b.days AS batch_days,b.status AS batch_status,
                      b.expires_at AS batch_expires_at
                 FROM trial_codes c
                 JOIN trial_code_batches b ON b.id=c.batch_id
                WHERE c.code_hash=?''',
            (code_hash,)).fetchone()
        if not row:
            _throttle_record(f'trial:{uid}')
            _throttle_record(f'trial:{ip}')
            return _trial_error(conn, None, uid, email, 'invalid_code', 400)
        code_id = row['id']

        if row['batch_status'] != 'active':
            return _trial_error(conn, code_id, uid, email, 'batch_closed', 400)
        if row['status'] == 'redeemed':
            return _trial_error(conn, code_id, uid, email, 'already_redeemed_code', 400)
        if row['status'] == 'revoked':
            return _trial_error(conn, code_id, uid, email, 'revoked_code', 400)
        if row['status'] != 'unused':
            return _trial_error(conn, code_id, uid, email, 'invalid_code', 400)
        if (row['expires_at'] or '') < now or (row['batch_expires_at'] or '') < now:
            conn.execute("UPDATE trial_codes SET status='expired' WHERE id=? AND status='unused'",
                         (code_id,))
            return _trial_error(conn, code_id, uid, email, 'expired_code', 400)
        if conn.execute(
            "SELECT id FROM trial_code_redemptions "
            "WHERE email_normalized=? AND result='success' LIMIT 1",
            (email,)).fetchone():
            return _trial_error(conn, code_id, uid, email, 'email_already_redeemed', 400)

        try:
            cur = conn.execute(
                "UPDATE trial_codes SET status='redeemed', redeemed_by_user_id=?, "
                "redeemed_by_email=?, redeemed_at=? WHERE id=? AND status='unused'",
                (uid, email, now, code_id))
            if cur.rowcount < 1:
                return _trial_error(conn, code_id, uid, email, 'already_redeemed_code', 400)
            _trial_log_redemption(conn, code_id, uid, email, 'success')
        except (psycopg2.IntegrityError, sqlite3.IntegrityError):
            conn.rollback()
            _trial_log_redemption(conn, code_id, uid, email, 'failed',
                                  'email_already_redeemed')
            conn.commit()
            return jsonify({'error': 'email_already_redeemed'}), 400

        days = int(row['batch_days'] or 30)
        premium_until = _extend_premium(conn, uid, days,
                                        f'trial_code:{row["batch_key"]}:{code_id}')
    session['plan'] = 'premium'
    session['is_premium'] = True
    return jsonify({'ok': True, 'plan': 'premium',
                    'premium_until': premium_until, 'days': days})


@app.route('/api/pay/plans')
def pay_plans():
    return jsonify({
        'ok': True,
        'configured': _newebpay().is_configured(),
        'test_mode': _newebpay().IS_TEST,
        'paypal_configured': _paypal().is_configured(),
        'paypal_test_mode': _paypal().IS_TEST,
        'plans': {k: {'amount': v['amount'], 'days': v['days']}
                  for k, v in PAY_PLANS.items()},
    })


@app.route('/api/pay/newebpay/subscribe', methods=['POST'])
@login_required
def newebpay_subscribe():
    np = _newebpay()
    if not np.is_configured():
        return jsonify({'error': 'not_configured',
                        'message': '金流尚未設定，請聯絡管理員'}), 503
    uid = session['user_id']
    plan_key = (request.get_json(silent=True) or {}).get('plan', '')
    if plan_key not in PAY_PLANS:
        return jsonify({'error': 'bad_plan'}), 400
    plan = PAY_PLANS[plan_key]

    with get_db() as conn:
        row = conn.execute(
            'SELECT email, email_verified FROM users WHERE id=?', (uid,)).fetchone()
        if not row or not row['email'] or not row['email_verified']:
            return jsonify({'error': 'email_unverified',
                            'message': '請先完成 Email 驗證再訂閱'}), 403
        active = conn.execute(
            "SELECT id FROM subscriptions WHERE user_id=? AND status='active'",
            (uid,)).fetchone()
        if active:
            return jsonify({'error': 'already_subscribed',
                            'message': '已有生效中的訂閱'}), 400

        mer_order_no = _gen_mer_order_no(uid)
        now = _now_iso()
        conn.execute(
            'INSERT INTO subscriptions(user_id,provider,mer_order_no,plan_key,'
            'amount,status,total_times,created_at) VALUES(?,?,?,?,?,?,?,?)',
            (uid, 'newebpay', mer_order_no, plan_key, plan['amount'],
             'pending', plan['times'], now))
        conn.commit()
        email = row['email']

    form = np.build_period_form(
        mer_order_no=mer_order_no,
        amount=plan['amount'],
        period_type=plan['period_type'],
        period_point=_period_point(plan_key),
        period_times=plan['times'],
        prod_desc=plan['desc'],
        payer_email=email,
        notify_url=f'{SITE_URL}/api/pay/newebpay/notify',
        return_url=f'{SITE_URL}/api/pay/newebpay/return',
        back_url=f'{SITE_URL}/upgrade',
    )
    print(f'[payment] uid={uid} 建立訂閱委託 {mer_order_no}（{plan_key}, NT${plan["amount"]}, test={np.IS_TEST}）')
    return jsonify({'ok': True, 'form': form, 'order_no': mer_order_no})


def _handle_period_notify(data, raw):
    """處理藍新定期定額授權結果（NotifyURL/ReturnURL 共用）。

    冪等：以 (PeriodNo, AlreadyTimes) 為事件鍵，重複通知直接略過。
    回傳 (ok, message)。
    """
    status = str(data.get('Status', ''))
    result = data.get('Result') or {}
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except ValueError:
            result = {}
    # 藍新定期定額欄位：委託建立回傳 MerchantOrderNo/AuthTimes(總期數)/PeriodAmt，
    # 每期授權通知回傳 MerchantOrderNo/AlreadyTimes/TotalTimes/AuthAmt
    mer_order_no = (result.get('MerchantOrderNo') or result.get('MerOrderNo')
                    or data.get('MerchantOrderNo') or data.get('MerOrderNo') or '')
    period_no = result.get('PeriodNo') or ''
    already = str(result.get('AlreadyTimes') or '1')
    total = (result.get('TotalTimes') or result.get('AuthTimes')
             or result.get('PeriodTimes') or 0)
    auth_amt = int(result.get('AuthAmt') or result.get('PeriodAmt') or 0)
    now = _now_iso()

    with get_db() as conn:
        sub = conn.execute(
            'SELECT * FROM subscriptions WHERE mer_order_no=?',
            (mer_order_no,)).fetchone()
        if not sub:
            print(f'[payment] 通知對不上訂閱單 MerOrderNo={mer_order_no}，已記 log')
            conn.execute(
                'INSERT OR IGNORE INTO payment_notify_log(provider,event_key,payload,created_at) '
                'VALUES(?,?,?,?)',
                ('newebpay', f'orphan:{mer_order_no}:{now}', raw[:8000], now))
            conn.commit()
            return False, 'unknown_order'

        if status != 'SUCCESS':
            conn.execute(
                "UPDATE subscriptions SET status=CASE WHEN charged_times=0 THEN 'failed' ELSE status END,"
                ' updated_at=? WHERE id=?', (now, sub['id']))
            conn.execute(
                'INSERT OR IGNORE INTO payment_notify_log(provider,event_key,payload,created_at) '
                'VALUES(?,?,?,?)',
                ('newebpay', f'fail:{mer_order_no}:{now}', raw[:8000], now))
            conn.commit()
            print(f'[payment] 授權失敗 {mer_order_no}: {data.get("Message")}')
            return False, str(data.get('Message', 'auth_failed'))

        # 冪等鍵：同一委託同一期只處理一次
        event_key = f'newebpay:{period_no or mer_order_no}:{already}'
        dup = conn.execute(
            'SELECT id FROM payment_notify_log WHERE event_key=?',
            (event_key,)).fetchone()
        if dup:
            return True, 'duplicate_ignored'
        conn.execute(
            'INSERT INTO payment_notify_log(provider,event_key,payload,created_at) '
            'VALUES(?,?,?,?)', ('newebpay', event_key, raw[:8000], now))

        # 金額比對（以我們 DB 的訂閱單為準）
        if auth_amt and auth_amt != sub['amount']:
            conn.commit()
            print(f'[payment] ⚠️ 金額不符 {mer_order_no}: 通知 {auth_amt} != 訂單 {sub["amount"]}，不開通')
            return False, 'amount_mismatch'

        plan = PAY_PLANS.get(sub['plan_key'], PAY_PLANS['monthly'])
        conn.execute(
            "UPDATE subscriptions SET status='active', period_no=?, charged_times=?, "
            'total_times=?, updated_at=? WHERE id=?',
            (period_no or sub['period_no'], int(already or 1),
             int(total or sub['total_times']), now, sub['id']))
        conn.execute(
            'INSERT INTO payment_orders(mer_order_no,user_id,provider,plan_key,'
            'amount,currency,status,raw_payload,created_at,paid_at) '
            'VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT (mer_order_no) DO NOTHING',
            (f'{mer_order_no}-{already}', sub['user_id'], 'newebpay',
             sub['plan_key'], sub['amount'], 'TWD', 'paid', raw[:8000], now, now))
        conn.commit()
        _extend_premium(conn, sub['user_id'], plan['days'],
                        f'newebpay 第 {already} 期')
    return True, 'ok'


@app.route('/api/pay/newebpay/notify', methods=['POST'])
def newebpay_notify():
    """藍新背景通知（server-to-server），每期授權都會打一次。"""
    np = _newebpay()
    period_hex = request.form.get('Period') or request.form.get('period') or ''
    if not period_hex:
        return 'no data', 400
    try:
        data = np.decrypt_period_response(period_hex)
    except Exception as e:
        print(f'[payment] notify 解密失敗: {e}')
        return 'decrypt error', 400
    ok, msg = _handle_period_notify(data, json.dumps(data, ensure_ascii=False))
    # 藍新規範：回 HTTP 200 即視為收到
    return ('ok' if ok else msg), 200


@app.route('/api/pay/newebpay/return', methods=['GET', 'POST'])
def newebpay_return():
    """付款完成導回（幕前）。開通以 NotifyURL 為準，這裡也處理一次保險。"""
    np = _newebpay()
    period_hex = request.form.get('Period') or request.args.get('Period') or ''
    result = 'pending'
    if period_hex:
        try:
            data = np.decrypt_period_response(period_hex)
            ok, _ = _handle_period_notify(data, json.dumps(data, ensure_ascii=False))
            result = 'success' if ok else 'failed'
            if ok and 'user_id' in session:
                session['plan'] = 'premium'
        except Exception as e:
            print(f'[payment] return 解密失敗: {e}')
            result = 'failed'
    else:
        # 藍新建立委託被拒時，回傳未加密的 Status/Message（無 Period 欄位）
        status = request.form.get('Status') or request.args.get('Status') or ''
        message = request.form.get('Message') or request.args.get('Message') or ''
        if status:
            print(f'[payment] 藍新拒絕委託：{status} {message}')
            result = 'failed'
    return redirect(f'/upgrade?pay={result}')


@app.route('/api/pay/subscription')
@login_required
def pay_subscription_status():
    uid = session['user_id']
    with get_db() as conn:
        row = conn.execute(
            'SELECT plan, premium_until FROM users WHERE id=?', (uid,)).fetchone()
        sub = conn.execute(
            "SELECT mer_order_no, plan_key, amount, status, charged_times, total_times, "
            'created_at, cancelled_at FROM subscriptions '
            "WHERE user_id=? AND status IN ('active','pending') "
            'ORDER BY id DESC LIMIT 1', (uid,)).fetchone()
    return jsonify({
        'ok': True,
        'plan': row['plan'] if row else 'free',
        'premium_until': row['premium_until'] if row else None,
        'subscription': dict(sub) if sub else None,
    })


@app.route('/api/pay/subscription/cancel', methods=['POST'])
@login_required
def pay_subscription_cancel():
    """取消續訂（藍新/PayPal）；已付期間用到 premium_until 為止。"""
    uid = session['user_id']
    with get_db() as conn:
        sub = conn.execute(
            "SELECT * FROM subscriptions WHERE user_id=? AND status='active' "
            'ORDER BY id DESC LIMIT 1', (uid,)).fetchone()
        if not sub:
            return jsonify({'error': 'no_active_subscription'}), 400

    if sub['provider'] == 'paypal':
        try:
            _paypal().cancel_subscription(sub['mer_order_no'])
        except Exception as e:
            print(f'[payment] PayPal 取消失敗 uid={uid}: {e}')
            return jsonify({'error': 'gateway_error',
                            'message': 'PayPal 終止訂閱失敗，請稍後再試或聯絡客服'}), 502
    else:
        np = _newebpay()
        if not sub['period_no']:
            return jsonify({'error': 'not_ready',
                            'message': '訂閱尚未完成首期授權，無法取消'}), 400
        try:
            resp = np.alter_period_status(
                mer_order_no=sub['mer_order_no'],
                period_no=sub['period_no'],
                alter_type='terminate')
        except Exception as e:
            print(f'[payment] AlterStatus 失敗 uid={uid}: {e}')
            return jsonify({'error': 'gateway_error',
                            'message': '藍新終止委託失敗，請稍後再試或聯絡客服'}), 502
        status = str(resp.get('Status') or
                     (resp.get('period_decrypted') or {}).get('Status') or '')
        if status != 'SUCCESS':
            print(f'[payment] AlterStatus 被拒 uid={uid}: {resp}')
            return jsonify({'error': 'gateway_rejected',
                            'message': str(resp.get('Message', '終止失敗'))}), 502
    now = _now_iso()
    with get_db() as conn:
        conn.execute(
            "UPDATE subscriptions SET status='cancelled', cancelled_at=?, updated_at=? "
            'WHERE id=?', (now, now, sub['id']))
        conn.commit()
        until = conn.execute(
            'SELECT premium_until FROM users WHERE id=?', (uid,)).fetchone()
    print(f'[payment] uid={uid} 已取消續訂 {sub["mer_order_no"]}')
    return jsonify({'ok': True,
                    'premium_until': until['premium_until'] if until else None})


# ── PayPal Subscriptions（美元，海外用戶）─────────────────────────

PAYPAL_PLANS = {
    'monthly': {'usd': 9.9, 'days': 31,  'interval': 'MONTH',
                'name': 'Go Odyssey Premium Monthly'},
    'annual':  {'usd': 84, 'days': 366, 'interval': 'YEAR',
                'name': 'Go Odyssey Premium Annual'},
}
_PAYPAL_GRACE_DAYS = 3   # 效期 = 下次扣款日 + 寬限，避免扣款時差斷權


def _paypal():
    import paypal_api
    return paypal_api


def _kv_get(conn, key):
    row = conn.execute('SELECT value FROM app_kv WHERE key=?', (key,)).fetchone()
    return row['value'] if row else None


def _kv_set(conn, key, value):
    conn.execute(
        'INSERT INTO app_kv(key,value) VALUES(?,?) '
        'ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value', (key, value))
    conn.commit()


def _paypal_ensure_plan(plan_key):
    """取得（必要時建立）PayPal billing plan id，存 app_kv。"""
    pp = _paypal()
    env = 'sandbox' if pp.IS_TEST else 'live'
    kv_plan = f'paypal_{env}_plan_{plan_key}'
    kv_product = f'paypal_{env}_product'
    with get_db() as conn:
        plan_id = _kv_get(conn, kv_plan)
        if plan_id:
            return plan_id
        product_id = _kv_get(conn, kv_product)
    if not product_id:
        product_id = pp.create_product()
        with get_db() as conn:
            _kv_set(conn, kv_product, product_id)
    p = PAYPAL_PLANS[plan_key]
    plan_id = pp.create_plan(product_id, name=p['name'], usd=p['usd'],
                             interval_unit=p['interval'])
    with get_db() as conn:
        _kv_set(conn, kv_plan, plan_id)
    print(f'[payment] PayPal plan 建立 {plan_key} → {plan_id}（{env}）')
    return plan_id


def _set_premium_until(conn, uid, until_iso, source):
    """把 premium_until 設為指定時間（只前進不倒退），必要時開通 Premium。"""
    row = conn.execute(
        'SELECT plan, premium_until FROM users WHERE id=?', (uid,)).fetchone()
    if not row:
        return None
    cur = row['premium_until'] or ''
    if cur and cur >= until_iso:
        return cur   # 已涵蓋，冪等略過
    first_time = row['plan'] != 'premium'
    conn.execute("UPDATE users SET plan='premium', premium_until=? WHERE id=?",
                 (until_iso, uid))
    conn.commit()
    if first_time:
        grant_premium_rewards(uid, conn)
    print(f'[payment] uid={uid} premium 效期設為 {until_iso}（{source}）')
    return until_iso


def _paypal_sync_subscription(sub_id, event_key=None):
    """以 PayPal API 即時狀態為準同步訂閱（webhook/導回共用，防偽造）。"""
    pp = _paypal()
    sub_data = pp.get_subscription(sub_id)
    status = sub_data.get('status', '')
    now = _now_iso()
    with get_db() as conn:
        sub = conn.execute(
            'SELECT * FROM subscriptions WHERE mer_order_no=?',
            (sub_id,)).fetchone()
        if not sub:
            conn.execute(
                'INSERT OR IGNORE INTO payment_notify_log(provider,event_key,payload,created_at) '
                'VALUES(?,?,?,?)',
                ('paypal', f'orphan:{sub_id}:{now}',
                 json.dumps(sub_data)[:8000], now))
            conn.commit()
            print(f'[payment] PayPal 訂閱對不上 {sub_id}')
            return False, 'unknown_subscription'

        uid = sub['user_id']
        plan = PAYPAL_PLANS.get(sub['plan_key'], PAYPAL_PLANS['monthly'])
        bi = sub_data.get('billing_info') or {}

        if status == 'ACTIVE':
            cycles = (bi.get('cycle_executions') or [{}])[0]
            charged = int(cycles.get('cycles_completed') or 1)
            next_billing = bi.get('next_billing_time') or ''
            if next_billing:
                until = (datetime.datetime.fromisoformat(
                            next_billing.replace('Z', '+00:00'))
                         .replace(tzinfo=None)
                         + datetime.timedelta(days=_PAYPAL_GRACE_DAYS)).isoformat()
            else:
                until = (datetime.datetime.now()
                         + datetime.timedelta(days=plan['days'])).isoformat()
            event_key = event_key or f'paypal:{sub_id}:{next_billing or charged}'
            dup = conn.execute(
                'SELECT id FROM payment_notify_log WHERE event_key=?',
                (event_key,)).fetchone()
            if dup:
                return True, 'duplicate_ignored'
            conn.execute(
                'INSERT INTO payment_notify_log(provider,event_key,payload,created_at) '
                'VALUES(?,?,?,?)',
                ('paypal', event_key, json.dumps(sub_data)[:8000], now))
            conn.execute(
                "UPDATE subscriptions SET status='active', period_no=?, "
                'charged_times=?, updated_at=? WHERE id=?',
                (sub_id, charged, now, sub['id']))
            conn.execute(
                'INSERT INTO payment_orders(mer_order_no,user_id,provider,plan_key,'
                'amount,currency,status,raw_payload,created_at,paid_at) '
                'VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT (mer_order_no) DO NOTHING',
                (f'{sub_id}-{charged}', uid, 'paypal', sub['plan_key'],
                 plan['usd'], 'USD', 'paid',
                 json.dumps(sub_data)[:8000], now, now))
            conn.commit()
            _set_premium_until(conn, uid, until,
                               f'paypal 第 {charged} 期')
            return True, 'ok'

        if status in ('CANCELLED', 'SUSPENDED', 'EXPIRED'):
            if sub['status'] != 'cancelled':
                conn.execute(
                    "UPDATE subscriptions SET status='cancelled', cancelled_at=?, "
                    'updated_at=? WHERE id=?', (now, now, sub['id']))
                conn.commit()
                print(f'[payment] PayPal 訂閱已終止 {sub_id}（{status}）')
            return True, status.lower()

        # APPROVAL_PENDING / APPROVED（尚未首扣）等狀態
        return False, status.lower() or 'pending'


@app.route('/api/pay/paypal/subscribe', methods=['POST'])
@login_required
def paypal_subscribe():
    pp = _paypal()
    if not pp.is_configured():
        return jsonify({'error': 'not_configured',
                        'message': 'PayPal 尚未設定，請聯絡管理員'}), 503
    uid = session['user_id']
    plan_key = (request.get_json(silent=True) or {}).get('plan', '')
    if plan_key not in PAYPAL_PLANS:
        return jsonify({'error': 'bad_plan'}), 400

    with get_db() as conn:
        row = conn.execute(
            'SELECT email, email_verified FROM users WHERE id=?', (uid,)).fetchone()
        if not row or not row['email'] or not row['email_verified']:
            return jsonify({'error': 'email_unverified',
                            'message': '請先完成 Email 驗證再訂閱'}), 403
        active = conn.execute(
            "SELECT id FROM subscriptions WHERE user_id=? AND status='active'",
            (uid,)).fetchone()
        if active:
            return jsonify({'error': 'already_subscribed',
                            'message': '已有生效中的訂閱'}), 400

    try:
        plan_id = _paypal_ensure_plan(plan_key)
        sub_id, approval_url = pp.create_subscription(
            plan_id, custom_id=uid,
            return_url=f'{SITE_URL}/api/pay/paypal/return',
            cancel_url=f'{SITE_URL}/upgrade?pay=failed')
    except Exception as e:
        print(f'[payment] PayPal 建立訂閱失敗 uid={uid}: {e}')
        return jsonify({'error': 'gateway_error',
                        'message': 'PayPal 連線失敗，請稍後再試'}), 502

    plan = PAYPAL_PLANS[plan_key]
    with get_db() as conn:
        conn.execute(
            'INSERT INTO subscriptions(user_id,provider,mer_order_no,plan_key,'
            'amount,status,total_times,created_at) VALUES(?,?,?,?,?,?,?,?)',
            (uid, 'paypal', sub_id, plan_key, plan['usd'], 'pending', 0, _now_iso()))
        conn.commit()
    print(f'[payment] uid={uid} 建立 PayPal 訂閱 {sub_id}（{plan_key}, '
          f'US${plan["usd"]}, sandbox={pp.IS_TEST}）')
    return jsonify({'ok': True, 'approval_url': approval_url, 'order_no': sub_id})


@app.route('/api/pay/paypal/return')
def paypal_return():
    sub_id = request.args.get('subscription_id', '')
    result = 'failed'
    if sub_id:
        try:
            ok, msg = _paypal_sync_subscription(sub_id)
            result = 'success' if ok and msg in ('ok', 'duplicate_ignored') \
                else ('pending' if msg in ('approved', 'approval_pending', 'pending')
                      else 'failed')
            if result == 'success' and 'user_id' in session:
                session['plan'] = 'premium'
        except Exception as e:
            print(f'[payment] PayPal return 同步失敗 {sub_id}: {e}')
    return redirect(f'/upgrade?pay={result}')


@app.route('/api/pay/paypal/webhook', methods=['POST'])
def paypal_webhook():
    """PayPal webhook：不信 payload，一律回查 API 即時狀態再動帳。"""
    event = request.get_json(silent=True) or {}
    etype = event.get('event_type', '')
    resource = event.get('resource') or {}
    # 訂閱事件 resource.id = sub id；扣款事件 billing_agreement_id = sub id
    sub_id = ''
    if etype.startswith('BILLING.SUBSCRIPTION'):
        sub_id = resource.get('id', '')
    elif etype in ('PAYMENT.SALE.COMPLETED', 'PAYMENT.CAPTURE.COMPLETED'):
        sub_id = (resource.get('billing_agreement_id')
                  or resource.get('custom_id') or '')
    if not sub_id:
        return 'ignored', 200
    event_key = f"paypal:evt:{event.get('id', '')}" if event.get('id') else None
    try:
        _paypal_sync_subscription(sub_id, event_key=event_key)
    except Exception as e:
        print(f'[payment] PayPal webhook 處理失敗 {sub_id}: {e}')
    return 'ok', 200


@app.route('/api/admin/payments')
@admin_required
def admin_payments():
    with get_db() as conn:
        subs = conn.execute(
            'SELECT s.*, u.username FROM subscriptions s '
            'JOIN users u ON u.id=s.user_id ORDER BY s.id DESC LIMIT 100').fetchall()
        orders = conn.execute(
            'SELECT o.id, o.mer_order_no, o.user_id, u.username, o.plan_key, '
            'o.amount, o.currency, o.status, o.created_at, o.paid_at '
            'FROM payment_orders o JOIN users u ON u.id=o.user_id '
            'ORDER BY o.id DESC LIMIT 200').fetchall()
    return jsonify({'ok': True,
                    'subscriptions': [dict(r) for r in subs],
                    'orders': [dict(r) for r in orders]})


@app.route('/daily-challenge')
@login_required
def daily_challenge_page(): return _serve_live_static_or_baked('daily_challenge.html')

@app.route('/community')
@login_required
def community_page(): return _serve_live_static_or_baked('community.html')

@app.route('/messages')
@login_required
def messages_page(): return _serve_live_static_or_baked('messages.html')

@app.route('/share/<token>')
def share_page(token): return _serve_live_static_or_baked('share_view.html')

@app.route('/mistakes')
@login_required
def mistakes_page(): return _serve_live_static_or_baked('mistakes.html')

@app.route('/curriculum')
@login_required
def curriculum_page(): return _serve_live_static_or_baked('curriculum.html')

@app.route('/skills')
@app.route('/hero')
@login_required
def skills_page(): return _serve_live_static_or_baked('hero.html')

@app.route('/rating_test')
@login_required
def rating_test_page(): return _serve_live_static_or_baked('rating_test.html')

# 公開試玩入口（Public Rating Trial）：冷流量免註冊測棋力。複用同一頁面，
# 前端以 /try 路徑偵測 TRIAL 模式（不呼叫需登入的存檔端點）。正式 /rating_test 不動。
@app.route('/try')
def rating_trial_page(): return _serve_live_static_or_baked('rating_test.html')

@app.route('/shop')
@login_required
def shop_page(): return _serve_live_static_or_baked('shop.html')

@app.route('/profile/<username>')
def profile_page(username): return _serve_live_static_or_baked('profile.html')

def _premium_weekly_no_store(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, private'
    response.headers['Pragma'] = 'no-cache'
    if request.path.startswith('/premium/quest/'):
        response.headers['Referrer-Policy'] = 'no-referrer'
    return response


def _premium_weekly_generate_for_user(uid, period_start=None, period_end=None):
    from premium_weekly_service import generate_weekly_report
    with get_db() as conn:
        result = generate_weekly_report(
            conn, uid, _load_questions(), period_start, period_end, status='shadow')
        conn.commit()
    return result


@app.route('/api/premium/weekly/reports')
@login_required
def premium_weekly_reports():
    uid = session['user_id']
    if not is_premium(uid):
        return jsonify({'error': 'premium_required'}), 403
    include_shadow = bool(session.get('is_admin') and request.args.get('include_shadow') == '1')
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id,period_start,period_end,status,generated_at,published_at "
            "FROM weekly_reports WHERE user_id=? AND status IN " +
            ("('shadow','published') " if include_shadow else "('published') ") +
            "ORDER BY period_start DESC LIMIT 20", (uid,)
        ).fetchall()
    return _premium_weekly_no_store(jsonify({'reports': [dict(row) for row in rows]}))


@app.route('/api/premium/weekly/reports/<int:report_id>')
@login_required
def premium_weekly_report_detail(report_id):
    uid = session['user_id']
    if not is_premium(uid):
        return jsonify({'error': 'premium_required'}), 403
    from premium_weekly_service import public_report_payload
    with get_db() as conn:
        payload = public_report_payload(conn, report_id, None if session.get('is_admin') else uid)
    if not payload or (payload['status'] != 'published' and not session.get('is_admin')):
        return jsonify({'error': 'not_found'}), 404
    return _premium_weekly_no_store(jsonify(payload))


@app.route('/api/premium/weekly/training/<int:set_id>')
@login_required
def premium_weekly_training(set_id):
    uid = session['user_id']
    if not is_premium(uid):
        return jsonify({'error': 'premium_required'}), 403
    with get_db() as conn:
        if session.get('is_admin'):
            owner = conn.execute(
                'SELECT s.*,r.status AS report_status FROM premium_training_sets s '
                'JOIN weekly_reports r ON r.id=s.report_id WHERE s.id=?', (set_id,)
            ).fetchone()
        else:
            owner = conn.execute(
                'SELECT s.*,r.status AS report_status FROM premium_training_sets s '
                'JOIN weekly_reports r ON r.id=s.report_id WHERE s.id=? AND s.user_id=?',
                (set_id, uid)
            ).fetchone()
        if not owner or (owner['report_status'] != 'published' and not session.get('is_admin')):
            return jsonify({'error': 'not_found'}), 404
        rows = conn.execute(
            'SELECT * FROM premium_training_items WHERE set_id=? ORDER BY item_order',
            (set_id,)
        ).fetchall()
    qmap = {q['id']: q for q in _load_questions()}
    items = []
    wrong_weak_run = 0
    for raw in rows:
        row = dict(raw)
        if (row['role'] in ('primary', 'secondary') and row['completed_at']
                and row['first_grade'] is not None and int(row['first_grade']) < 3):
            wrong_weak_run += 1
        elif row['completed_at']:
            wrong_weak_run = 0
        q = qmap.get(row['question_id'], {})
        display_name = _question_display_name(q) if q else ''
        if not display_name or str(display_name).strip().isdigit():
            label = q.get('discipline_label') or q.get('discipline') or '綜合'
            display_name = f"{label}修行題"
        row['display_name'] = display_name
        display_name_en = _question_display_name_en(q) if q else ''
        if not display_name_en or str(display_name_en).strip().isdigit():
            discipline_names_en = {
                'tesuji': 'Tesuji', 'life_death': 'Life & Death',
                'endgame_counting': 'Endgame & Counting', 'opening_direction': 'Opening Direction',
                'capture_escape': 'Capture & Escape', 'connection_cut': 'Connection & Cutting',
                'shape_weakness': 'Shape & Weakness', 'whole_board': 'Whole-board Judgment',
            }
            display_name_en = f"{discipline_names_en.get(row.get('discipline'), 'General')} Training Problem"
        row['display_name_en'] = display_name_en
        row['rank'] = q.get('rank') or q.get('difficulty') or ''
        items.append(row)
    next_item = next((item for item in items if not item['completed_at']), None)
    rescue = bool(next_item and wrong_weak_run >= 2)
    return _premium_weekly_no_store(jsonify({
        'set': dict(owner), 'items': items, 'next_item': next_item,
        'read_only': bool(session.get('is_admin') and int(owner['user_id']) != int(uid)),
        'rescue': rescue,
        'rescue_message_key': 'premium.weekly.rescue_generic' if rescue else None,
    }))


@app.route('/api/admin/premium/weekly/generate', methods=['POST'])
@admin_required
def admin_premium_weekly_generate():
    body = request.get_json(silent=True) or {}
    uid = body.get('user_id')
    start = body.get('period_start')
    end = body.get('period_end')
    try:
        period_start = datetime.date.fromisoformat(start) if start else None
        period_end = datetime.date.fromisoformat(end) if end else None
    except ValueError:
        return jsonify({'error': 'invalid_period'}), 400
    with get_db() as conn:
        if uid is not None:
            users = conn.execute('SELECT id FROM users WHERE id=?', (int(uid),)).fetchall()
        else:
            users = conn.execute(
                "SELECT id FROM users WHERE plan='premium' OR is_admin=1 ORDER BY id"
            ).fetchall()
    results = [_premium_weekly_generate_for_user(int(row['id']), period_start, period_end)
               for row in users]
    return jsonify({'ok': True, 'generated': len(results),
                    'reports': [{'report_id': r['report_id'], 'set_id': r['set_id']} for r in results]})


@app.route('/api/admin/premium/weekly/reports')
@admin_required
def admin_premium_weekly_reports():
    with get_db() as conn:
        rows = conn.execute(
            '''SELECT r.id,r.user_id,u.username,r.period_start,r.period_end,r.status,
                      r.model_version,r.generated_at,s.id AS training_set_id,
                      (SELECT COUNT(*) FROM premium_training_items i WHERE i.set_id=s.id) AS item_count
               FROM weekly_reports r JOIN users u ON u.id=r.user_id
               LEFT JOIN premium_training_sets s ON s.report_id=r.id
               ORDER BY r.period_start DESC,r.id DESC LIMIT 200'''
        ).fetchall()
    return _premium_weekly_no_store(jsonify({'reports': [dict(row) for row in rows]}))


def _weekly_admin_audit(conn, report_id, action, detail=None):
    conn.execute(
        'INSERT INTO weekly_report_admin_logs(report_id,admin_id,action,detail,created_at) '
        'VALUES(?,?,?,?,?)',
        (report_id, session['user_id'], action, detail, datetime.datetime.now().isoformat())
    )


@app.route('/api/admin/premium/weekly/reports/<int:report_id>')
@admin_required
def admin_premium_weekly_report_detail(report_id):
    from premium_weekly_service import public_report_payload
    with get_db() as conn:
        payload = public_report_payload(conn, report_id)
        if not payload:
            return jsonify({'error': 'not_found'}), 404
        reviews = [dict(row) for row in conn.execute(
            'SELECT reviewer_slot,reviewer_id,top_disciplines,data_sufficient,'
            'difficulty_fit,notes,submitted_at FROM weekly_report_reviews '
            'WHERE report_id=? ORDER BY reviewer_slot', (report_id,)
        ).fetchall()]
        for review in reviews:
            review['top_disciplines'] = json.loads(review['top_disciplines'])
        _weekly_admin_audit(conn, report_id, 'view_shadow_report')
        conn.commit()
    payload['reviews'] = reviews
    return _premium_weekly_no_store(jsonify(payload))


@app.route('/api/admin/premium/weekly/reports/<int:report_id>/review', methods=['POST'])
@admin_required
def admin_premium_weekly_review(report_id):
    body = request.get_json(silent=True) or {}
    try:
        slot = int(body.get('reviewer_slot'))
    except (TypeError, ValueError):
        return jsonify({'error': 'invalid_reviewer_slot'}), 400
    top = body.get('top_disciplines')
    allowed = {'tesuji','life_death','endgame_counting','opening_direction',
               'capture_escape','connection_cut','shape_weakness','whole_board'}
    if slot not in (1, 2) or not isinstance(top, list) or not (1 <= len(top) <= 3) \
            or len(set(top)) != len(top) or any(item not in allowed for item in top):
        return jsonify({'error': 'invalid_review'}), 400
    with get_db() as conn:
        report = conn.execute('SELECT status FROM weekly_reports WHERE id=?', (report_id,)).fetchone()
        if not report or report['status'] != 'shadow':
            return jsonify({'error': 'report_not_reviewable'}), 409
        other = conn.execute(
            'SELECT reviewer_id FROM weekly_report_reviews WHERE report_id=? AND reviewer_slot<>?',
            (report_id, slot)
        ).fetchone()
        if other and int(other['reviewer_id']) == int(session['user_id']):
            return jsonify({'error': 'independent_reviewer_required'}), 409
        conn.execute(
            '''INSERT INTO weekly_report_reviews
               (report_id,reviewer_id,reviewer_slot,top_disciplines,data_sufficient,
                difficulty_fit,notes,submitted_at) VALUES(?,?,?,?,?,?,?,?)
               ON CONFLICT(report_id,reviewer_slot) DO UPDATE SET
                reviewer_id=excluded.reviewer_id,top_disciplines=excluded.top_disciplines,
                data_sufficient=excluded.data_sufficient,difficulty_fit=excluded.difficulty_fit,
                notes=excluded.notes,submitted_at=excluded.submitted_at''',
            (report_id, session['user_id'], slot, json.dumps(top),
             1 if body.get('data_sufficient') else 0,
             1 if body.get('difficulty_fit') else 0,
             str(body.get('notes') or '')[:1000], datetime.datetime.now().isoformat())
        )
        _weekly_admin_audit(conn, report_id, 'submit_blind_review', f'slot={slot}')
        conn.commit()
    return jsonify({'ok': True})


@app.route('/api/admin/premium/weekly/review-metrics')
@admin_required
def admin_premium_weekly_review_metrics():
    labels = ['tesuji','life_death','endgame_counting','opening_direction',
              'capture_escape','connection_cut','shape_weakness','whole_board']
    with get_db() as conn:
        rows = conn.execute(
            '''SELECT r.id,r.summary_json,v.reviewer_slot,v.top_disciplines,
                      v.data_sufficient,v.difficulty_fit
               FROM weekly_reports r JOIN weekly_report_reviews v ON v.report_id=r.id
               ORDER BY r.id,v.reviewer_slot'''
        ).fetchall()
    grouped = {}
    for row in rows:
        grouped.setdefault(int(row['id']), {'summary': json.loads(row['summary_json']), 'reviews': []})
        grouped[int(row['id'])]['reviews'].append({
            'top': json.loads(row['top_disciplines']),
            'sufficient': bool(row['data_sufficient']), 'fit': bool(row['difficulty_fit'])})
    samples = []
    for report_id, group in grouped.items():
        if len(group['reviews']) != 2:
            continue
        a, b = group['reviews']
        aset, bset = set(a['top']), set(b['top'])
        po = sum((label in aset) == (label in bset) for label in labels) / len(labels)
        pa, pb = len(aset) / len(labels), len(bset) / len(labels)
        pe = pa * pb + (1 - pa) * (1 - pb)
        kappa = (po - pe) / (1 - pe) if pe < 1 else 1.0
        union = aset | bset
        jaccard = len(aset & bset) / len(union) if union else 1.0
        pairs = [(x, y) for i, x in enumerate(labels) for y in labels[i + 1:]
                 if x in union and y in union]
        concordant = discordant = 0
        for x, y in pairs:
            ar = a['top'].index(x) if x in aset else 3
            ay = a['top'].index(y) if y in aset else 3
            br = b['top'].index(x) if x in bset else 3
            by = b['top'].index(y) if y in bset else 3
            product = (ar - ay) * (br - by)
            concordant += int(product > 0)
            discordant += int(product < 0)
        tau = (concordant - discordant) / max(1, concordant + discordant)
        primary = group['summary'].get('primary_discipline')
        samples.append({'report_id': report_id, 'kappa': kappa, 'jaccard_at_3': jaccard,
                        'kendall_tau': tau,
                        'system_top1_in_shared_top2': primary in (set(a['top'][:2]) & set(b['top'][:2])),
                        'difficulty_fit': a['fit'] and b['fit'],
                        'data_sufficient': a['sufficient'] and b['sufficient']})
    def avg(key):
        return round(sum(float(item[key]) for item in samples) / len(samples), 4) if samples else None
    return jsonify({'reviewed_reports': len(samples), 'cohen_kappa': avg('kappa'),
                    'jaccard_at_3': avg('jaccard_at_3'), 'kendall_tau': avg('kendall_tau'),
                    'top1_hit_rate': avg('system_top1_in_shared_top2'),
                    'difficulty_fit_rate': avg('difficulty_fit'),
                    'data_sufficient_rate': avg('data_sufficient'), 'samples': samples})


@app.route('/api/admin/premium/weekly/reports/<int:report_id>/publish', methods=['POST'])
@admin_required
def admin_premium_weekly_publish(report_id):
    _, MODEL_VERSION, _ = _load_premium_weekly_rating_helpers()
    now = datetime.datetime.now().isoformat()
    with get_db() as conn:
        release = conn.execute(
            'SELECT value FROM app_kv WHERE key=?',
            (f'premium_weekly_release:{MODEL_VERSION}',)
        ).fetchone()
        if not release:
            return jsonify({'error': 'holdout_release_not_approved'}), 409
        row = conn.execute('SELECT id FROM weekly_reports WHERE id=?', (report_id,)).fetchone()
        if not row:
            return jsonify({'error': 'not_found'}), 404
        reviews = conn.execute(
            'SELECT COUNT(*) AS n,COUNT(DISTINCT reviewer_id) AS reviewers,'
            'MIN(data_sufficient) AS sufficient,MIN(difficulty_fit) AS fit '
            'FROM weekly_report_reviews WHERE report_id=?', (report_id,)
        ).fetchone()
        if (int(reviews['n'] or 0) < 2 or int(reviews['reviewers'] or 0) < 2 or
                not reviews['sufficient'] or not reviews['fit']):
            return jsonify({'error': 'independent_review_required'}), 409
        conn.execute(
            "UPDATE weekly_reports SET status='published',published_at=? WHERE id=?",
            (now, report_id)
        )
        _weekly_admin_audit(conn, report_id, 'publish_report')
        conn.commit()
    return jsonify({'ok': True, 'report_id': report_id})


@app.route('/api/admin/premium/weekly/model-release', methods=['GET', 'POST'])
@admin_required
def admin_premium_weekly_model_release():
    _, MODEL_VERSION, _ = _load_premium_weekly_rating_helpers()
    key = f'premium_weekly_release:{MODEL_VERSION}'
    minimum = max(1, int(os.environ.get('PREMIUM_WEEKLY_HOLDOUT_MIN_REPORTS', '20')))
    with get_db() as conn:
        existing = conn.execute('SELECT value FROM app_kv WHERE key=?', (key,)).fetchone()
        if request.method == 'POST':
            if existing:
                return jsonify({'error': 'model_release_already_recorded'}), 409
            body = request.get_json(silent=True) or {}
            try:
                holdout_reports = int(body.get('holdout_reports') or 0)
            except (TypeError, ValueError):
                holdout_reports = 0
            if body.get('confirmation') != 'HOLDOUT_APPROVED' or holdout_reports < minimum:
                return jsonify({'error': 'holdout_evidence_required',
                                'minimum_holdout_reports': minimum}), 409
            value = json.dumps({'approved_at': datetime.datetime.now().isoformat(),
                                'approved_by': session['user_id'],
                                'holdout_reports': holdout_reports})
            conn.execute(
                'INSERT INTO app_kv(key,value) VALUES(?,?) '
                'ON CONFLICT(key) DO NOTHING', (key, value)
            )
            _weekly_admin_audit(conn, None, 'approve_weekly_model_release', value)
            conn.commit()
        row = conn.execute('SELECT value FROM app_kv WHERE key=?', (key,)).fetchone()
    return jsonify({'model_version': MODEL_VERSION, 'approved': bool(row),
                    'minimum_holdout_reports': minimum,
                    'evidence': json.loads(row['value']) if row else None})


@app.route('/api/premium/weekly/email-preferences', methods=['GET', 'POST'])
@login_required
def premium_weekly_email_preferences():
    uid = session['user_id']
    if not is_premium(uid):
        return jsonify({'error': 'premium_required'}), 403
    with get_db() as conn:
        if request.method == 'POST':
            body = request.get_json(silent=True) or {}
            enabled = 1 if body.get('enabled') else 0
            user = conn.execute('SELECT email,email_verified FROM users WHERE id=?', (uid,)).fetchone()
            if enabled and (not user or not user['email'] or not user['email_verified']):
                return jsonify({'error': 'email_unverified'}), 400
            now = datetime.datetime.now().isoformat()
            conn.execute(
                '''INSERT INTO email_preferences(user_id,weekly_report_enabled,consent_version,locale,updated_at)
                   VALUES(?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET
                   weekly_report_enabled=excluded.weekly_report_enabled,
                   consent_version=excluded.consent_version,locale=excluded.locale,
                   updated_at=excluded.updated_at''',
                (uid, enabled, 'weekly-email-v1', str(body.get('locale') or 'zh')[:8], now)
            )
            conn.commit()
        pref = conn.execute(
            'SELECT * FROM email_preferences WHERE user_id=?', (uid,)
        ).fetchone()
    return _premium_weekly_no_store(jsonify(dict(pref) if pref else {
        'user_id': uid, 'weekly_report_enabled': 0, 'locale': 'zh'}))


def _premium_weekly_email_html(username, report, raw_token):
    summary = report['summary']['summary']
    link = f"{SITE_URL}/premium/quest/enter?token={urllib.parse.quote(raw_token)}"
    return f'''<!doctype html><html><body style="font-family:sans-serif;color:#3a2410">
    <h2>本週修行戰報</h2><p>{username}，你本週完成 {summary['completed_count']} 題，
    練習 {summary['practice_days']} 天。</p>
    <p>詳細弱點與專屬題組只會在登入後顯示。</p>
    <p><a href="{link}" rel="noreferrer" style="padding:12px 18px;background:#8d5a1e;color:white;text-decoration:none">進入本週專屬修行</a></p>
    <p style="color:#777">連結 7 天內有效。若非本人操作，請忽略本信。</p></body></html>'''


def _premium_create_quest_token(conn, uid, set_id):
    from premium_weekly_service import token_hash
    raw = secrets.token_urlsafe(32)
    now = datetime.datetime.now()
    conn.execute(
        'UPDATE premium_quest_tokens SET revoked_at=? WHERE user_id=? AND set_id=? AND revoked_at IS NULL',
        (now.isoformat(), uid, set_id)
    )
    conn.execute(
        '''INSERT INTO premium_quest_tokens
           (token_hash,user_id,set_id,purpose,expires_at,created_at)
           VALUES(?,?,?,'weekly_quest',?,?)''',
        (token_hash(raw), uid, set_id, (now + datetime.timedelta(days=7)).isoformat(), now.isoformat())
    )
    return raw


@app.route('/api/admin/premium/weekly/reports/<int:report_id>/test-email', methods=['POST'])
@admin_required
def admin_premium_weekly_test_email(report_id):
    from premium_weekly_service import public_report_payload
    with get_db() as conn:
        row = conn.execute(
            'SELECT r.user_id,r.status,u.username,u.email,u.email_verified,s.id AS set_id '
            'FROM weekly_reports r JOIN users u ON u.id=r.user_id '
            'JOIN premium_training_sets s ON s.report_id=r.id WHERE r.id=?',
            (report_id,)
        ).fetchone()
        if not row or not row['email'] or not row['email_verified']:
            return jsonify({'error': 'email_unverified'}), 400
        if row['status'] != 'published':
            return jsonify({'error': 'report_not_published'}), 409
        report = public_report_payload(conn, report_id, row['user_id'])
        raw = _premium_create_quest_token(conn, row['user_id'], row['set_id'])
        now = datetime.datetime.now().isoformat()
        conn.execute(
            '''INSERT INTO email_deliveries
               (user_id,report_id,template_version,recipient_email,status,created_at)
               VALUES(?,?,? ,?,'pending',?) ON CONFLICT DO NOTHING''',
            (row['user_id'], report_id, 'weekly-email-v1', row['email'], now)
        )
        conn.commit()
    ok = _send_email(row['email'], '【弈境奇兵】本週修行戰報',
                     _premium_weekly_email_html(row['username'], report, raw))
    with get_db() as conn:
        conn.execute(
            "UPDATE email_deliveries SET status=?,sent_at=?,error_class=? "
            "WHERE report_id=? AND recipient_email=? AND template_version=?",
            ('sent' if ok else 'failed', now if ok else None,
             None if ok else 'provider_failure', report_id, row['email'], 'weekly-email-v1')
        )
        conn.commit()
    return jsonify({'ok': bool(ok)})


@app.route('/premium/quest/enter')
def premium_quest_enter():
    raw = str(request.headers.get('X-Premium-Quest-Token') or
              request.args.get('token') or '')
    from premium_weekly_service import token_hash
    digest = token_hash(raw) if raw else ''
    now = datetime.datetime.now().isoformat()
    with get_db() as conn:
        token_row = conn.execute(
            '''SELECT * FROM premium_quest_tokens WHERE token_hash=? AND purpose='weekly_quest'
               AND revoked_at IS NULL AND expires_at>=?''', (digest, now)
        ).fetchone()
    if not token_row:
        return _premium_weekly_no_store(Response('連結無效或已過期', status=400))
    if 'user_id' not in session:
        session['premium_pending_token_hash'] = digest
        response = redirect('/login?return_to=/premium/quest/resume', code=303)
        response.headers['Referrer-Policy'] = 'no-referrer'
        return _premium_weekly_no_store(response)
    if int(session['user_id']) != int(token_row['user_id']):
        return _premium_weekly_no_store(Response('此連結屬於其他帳號，請切換帳號', status=403))
    with get_db() as conn:
        conn.execute('UPDATE premium_quest_tokens SET last_used_at=? WHERE id=?', (now, token_row['id']))
        conn.commit()
    response = redirect(f"/premium/weekly?set={token_row['set_id']}", code=303)
    response.headers['Referrer-Policy'] = 'no-referrer'
    return _premium_weekly_no_store(response)


@app.route('/premium/quest/resume')
@login_required
def premium_quest_resume():
    digest = session.pop('premium_pending_token_hash', '')
    now = datetime.datetime.now().isoformat()
    with get_db() as conn:
        row = conn.execute(
            '''SELECT * FROM premium_quest_tokens WHERE token_hash=? AND user_id=?
               AND revoked_at IS NULL AND expires_at>=?''',
            (digest, session['user_id'], now)
        ).fetchone()
    if not row:
        return _premium_weekly_no_store(Response('連結無效或已過期', status=400))
    return _premium_weekly_no_store(redirect(f"/premium/weekly?set={row['set_id']}", code=303))


@app.route('/premium/weekly')
@login_required
def premium_weekly_page():
    if not is_premium(session['user_id']):
        return redirect('/upgrade')
    return _serve_live_static_or_baked('premium_weekly.html')


@app.route('/stats')
@login_required
def stats_page(): return _serve_live_static_or_baked('stats.html')

@app.route('/upgrade')
def upgrade_page(): return _serve_live_static_or_baked('upgrade.html')

# 部落格（SEO，必須公開，不可 login_required）；乾淨網址 /blog 與 /blog/<slug>
# 檔案在 blog/index.html 與 blog/<slug>.html。send_from_directory 對缺檔自動回 404、
# 並防 ../ 路徑穿越，故 slug 不需另外消毒。
@app.route('/blog')
def blog_index(): return send_from_directory('blog', 'index.html')

@app.route('/blog/<slug>')
def blog_post(slug): return send_from_directory('blog', slug + '.html')

@app.route('/<path:filename>.html')
@login_required
def serve_html(filename): return _serve_live_static_or_baked(filename+'.html')

@app.route('/wgo/<path:filename>')
def serve_wgo(filename): return send_from_directory('wgo', filename)

_SOUND_DIR = os.path.join(
    os.path.dirname(__file__),
    '2023-06-15-windows64+katago',
    '2023-06-15-windows64+katago',
    'sound'
)
LIVE_STATIC_ROOT_ENV_VAR = 'GO_ODYSSEY_LIVE_STATIC_ROOT'


def _load_premium_weekly_rating_helpers():
    """Load optional premium-weekly rating helpers with a safe fallback.

    The premium-weekly feature is optional in the current production image.
    If the module is absent, SRS writes should still work using the app's own
    rank table instead of failing the whole review request.
    """
    try:
        from premium_weekly import ITEM_RATING_VERSION, MODEL_VERSION, rank_to_rating
        return ITEM_RATING_VERSION, MODEL_VERSION, rank_to_rating
    except ImportError:
        def rank_to_rating(rank_or_diff):
            mapping = globals().get('_RANK_TO_RATING', {})
            if rank_or_diff is None:
                return None
            key = str(rank_or_diff).strip()
            if not key:
                return None
            if key in mapping:
                return float(mapping[key])
            try:
                return float(key)
            except (TypeError, ValueError):
                return None

        compat_version = 'premium-weekly-compat-missing-module'
        return compat_version, compat_version, rank_to_rating

# B9: root-level filenames eligible to be served from the live-static
# release tree (/opt/go-odyssey-static/current) before falling back to
# the file baked into the Docker image. This is an explicit allowlist,
# not a wildcard -- every entry here is a file ALREADY served today by
# a plain, single-purpose Flask route (send_from_directory('.', name)
# or send_from_directory(_BASE, name)) with no dynamic content beyond
# whatever auth decorator already guards that route. Adding a filename
# here never changes who can access it (existing route decorators are
# completely unchanged, since only the route BODY's serving mechanism
# changes) -- it only changes where the bytes are read from. HTML pages
# are listed explicitly (not wildcarded) even though /<path:filename>.html
# is itself already a login-gated catch-all for any existing file, per
# this project's deliberate defense-in-depth preference.
_LIVE_STATIC_ELIGIBLE_FILES = frozenset({
    # already-generalized (Phase B7B)
    'i18n.js', 'sw.js',
    # frontend JS served as flat root files
    'srs.js', 'monster_trash.js', 'sound.js', 'mobile-nav.js',
    'site-nav.js', 'community_reward_notifications.js',
    'community_reward_rules.js', 'pwa.js',
    # static config served as flat root files
    'manifest.json', 'robots.txt', 'sitemap.xml',
    # public/known HTML pages (explicit allowlist; every one of these is
    # already served today exactly as send_from_directory('.', name))
    'login.html', 'landing.html', 'index.html', 'terms.html',
    'manage.html', 'admin.html', 'shadow_dashboard.html', 'bot.html', 'daily_challenge.html',
    'community.html', 'messages.html', 'share_view.html',
    'mistakes.html', 'curriculum.html', 'hero.html', 'rating_test.html',
    'shop.html', 'profile.html', 'premium_weekly.html', 'stats.html',
    'upgrade.html', 'play.html', 'inventory.html', 'badges.html',
    'games.html',
})


def _get_live_static_root():
    root = (os.environ.get(LIVE_STATIC_ROOT_ENV_VAR) or '').strip()
    if not root:
        return None
    return os.path.abspath(root)


def _resolve_live_static_path(relative_path, allowed_filenames=None):
    """Resolve `relative_path` (e.g. 'sw.js' or 'assets/tiers/26-30.jpg')
    against the live-static root, returning the absolute path if -- and
    only if -- every one of these holds:

      - relative_path is non-empty, contains no '..' traversal segment,
        and is not an absolute path (fails closed on any ambiguity)
      - relative_path does not contain a hidden path component (a
        segment starting with '.', e.g. '.env' or '.git/config') --
        except the leading '.' of a bare root-relative filename check,
        which os.path.basename handles naturally since 'i18n.js' has no
        such segment
      - if `allowed_filenames` is given (the root-level flat-file case),
        relative_path must be exactly one of those filenames with no
        directory component at all
      - the resolved absolute path stays strictly inside the live-static
        root (blocks symlink/traversal escapes)
      - the file actually exists on disk

    Returns None (never raises) on any failure -- callers must always
    have a baked-asset fallback ready."""
    if not relative_path:
        return None
    if relative_path.startswith('/') or relative_path.startswith('\\'):
        return None
    normalized = relative_path.replace('\\', '/')
    if '..' in normalized.split('/'):
        return None
    segments = normalized.split('/')
    if any(seg.startswith('.') for seg in segments):
        return None

    if allowed_filenames is not None:
        if len(segments) != 1 or segments[0] not in allowed_filenames:
            return None

    root = _get_live_static_root()
    if not root or not os.path.isdir(root):
        return None

    candidate = os.path.abspath(os.path.join(root, *segments))
    try:
        if os.path.commonpath([root, candidate]) != root:
            return None
    except ValueError:
        return None

    if not os.path.isfile(candidate):
        return None
    return candidate


def _serve_live_static_or_baked(filename, baked_base='.', mimetype=None):
    """Serve `filename` (a root-level flat file, e.g. 'sw.js' or
    'community.html') from the live-static release tree if present
    there, else fall back to the file baked into the Docker image at
    `baked_base`. `filename` must be one of _LIVE_STATIC_ELIGIBLE_FILES
    -- this function does not accept an arbitrary path."""
    live_static_path = _resolve_live_static_path(filename, allowed_filenames=_LIVE_STATIC_ELIGIBLE_FILES)
    if live_static_path:
        try:
            return send_file(live_static_path, conditional=True, mimetype=mimetype)
        except OSError as exc:
            app.logger.warning(
                '[live_static] failed to serve %s from %s: %s; falling back to baked asset',
                filename, live_static_path, exc
            )
    return send_from_directory(baked_base, filename, mimetype=mimetype)


def _serve_live_static_or_baked_subpath(subpath, baked_subdir, live_static_subdir):
    """Same fallback contract as _serve_live_static_or_baked, but for a
    file inside a subdirectory tree (e.g. assets/tiers/26-30.jpg)
    addressed by a Flask <path:subpath> converter value. No filename
    allowlist is applied here (arbitrary subpaths under an asset tree
    are expected), but every other protection in _resolve_live_static_path
    still applies -- no '..' traversal, no absolute path, no hidden
    dotfile segment, and the resolved path must stay inside the
    live-static root."""
    live_static_relative = f'{live_static_subdir}/{subpath}'
    live_static_path = _resolve_live_static_path(live_static_relative)
    if live_static_path:
        try:
            return send_file(live_static_path, conditional=True)
        except OSError as exc:
            app.logger.warning(
                '[live_static] failed to serve %s from %s: %s; falling back to baked asset',
                subpath, live_static_path, exc
            )
    return send_from_directory(os.path.join(_BASE, baked_subdir), subpath)

@app.route('/sound/<path:filename>')
def serve_sound(filename):
    return send_from_directory(_SOUND_DIR, filename)

@app.route('/srs.js')
def serve_srs_js(): return _serve_live_static_or_baked('srs.js')

@app.route('/monster_trash.js')
def serve_monster_trash_js(): return _serve_live_static_or_baked('monster_trash.js')

@app.route('/sound.js')
def serve_sound_js(): return _serve_live_static_or_baked('sound.js')

@app.route('/i18n.js')
def serve_i18n_js(): return _serve_live_static_or_baked('i18n.js')

@app.route('/mobile-nav.js')
def serve_mobile_nav_js(): return _serve_live_static_or_baked('mobile-nav.js')

@app.route('/site-nav.js')
def serve_site_nav_js(): return _serve_live_static_or_baked('site-nav.js')

@app.route('/community_reward_notifications.js')
def serve_community_reward_notifications_js():
    return _serve_live_static_or_baked('community_reward_notifications.js')

@app.route('/community_reward_rules.js')
def serve_community_reward_rules_js():
    return _serve_live_static_or_baked('community_reward_rules.js')

@app.route('/pwa.js')
def serve_pwa_js(): return _serve_live_static_or_baked('pwa.js')

@app.route('/manifest.json')
def serve_manifest():
    return _serve_live_static_or_baked('manifest.json', mimetype='application/manifest+json; charset=utf-8')

@app.route('/shorts/<path:filename>')
def serve_shorts(filename): return send_from_directory('shorts', filename)

@app.route('/robots.txt')
def serve_robots(): return _serve_live_static_or_baked('robots.txt', mimetype='text/plain; charset=utf-8')

@app.route('/sitemap.xml')
def serve_sitemap(): return _serve_live_static_or_baked('sitemap.xml', mimetype='application/xml; charset=utf-8')

@app.route('/og-image.jpg')
def serve_og_image(): return send_from_directory('.', 'og-image.jpg')

@app.errorhandler(404)
def page_not_found(e):
    if request.path.startswith('/api/'):
        return jsonify({'error': 'not_found'}), 404
    return ('''<!DOCTYPE html><html lang="zh-TW"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title data-i18n="error404.title">404 — Go Odyssey</title>
<style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#100b07;
color:#fff3d4;font-family:'Noto Serif TC',serif;text-align:center;padding:20px}
h1{font-size:72px;margin:0;color:#f2c86d}p{color:#d8c5a4;line-height:1.8}
a{display:inline-block;margin-top:18px;padding:12px 26px;border-radius:999px;
background:linear-gradient(135deg,#f7d17d,#b87924);color:#1b1007;
text-decoration:none;font-weight:900}</style></head>
<body><div><h1>404</h1>
<p><span data-i18n="error404.lost">迷路了嗎，冒險者？</span><br>
<span data-i18n="error404.path">這條小徑不在公會的地圖上。</span></p>
<a href="/" data-i18n="error404.home">⛩ 返回公會大廳</a></div>
<script src="/i18n.js?v=20260709b"></script><script>I18n.apply();</script>
</body></html>''', 404)

@app.route('/icon-192.png')
def serve_icon192(): return send_from_directory(_BASE,'icon-192.png')

@app.route('/assets/<path:subpath>')
def serve_assets(subpath):
    """提供題庫相關資源圖（如棋力區封面 assets/tiers/26-30.jpg）"""
    return _serve_live_static_or_baked_subpath(subpath, 'assets', 'assets')

@app.route('/favicon.ico')
def serve_favicon():
    # 沒有 .ico 檔，用 icon-192.png 代替（瀏覽器吃任何圖片格式）
    return send_from_directory(_BASE, 'icon-192.png', mimetype='image/png')

@app.route('/icon-512.png')
def serve_icon512(): return send_from_directory(_BASE,'icon-512.png')

@app.route('/sw.js')
def serve_sw():
    resp = _serve_live_static_or_baked('sw.js')
    resp.headers['Service-Worker-Allowed'] = '/'
    resp.headers['Cache-Control'] = 'no-cache'
    return resp

@app.route('/icons/<path:filename>')
def serve_icons(filename): return _serve_live_static_or_baked_subpath(filename, 'icons', 'icons')

# E9.1A2: narrow static routes for the feature-flagged Adventure Shell.
# Mirrors the /assets/ and /icons/ pattern above (_serve_live_static_or_baked_subpath
# already blocks '..' traversal, absolute paths, and hidden dotfile segments via
# _resolve_live_static_path). Extension is explicitly allowlisted here since no
# existing helper restricts by extension -- these three routes must only ever
# serve .js / .css / .html respectively, never arbitrary repo files.
@app.route('/js/e9/<path:subpath>')
def serve_e9_js(subpath):
    if not subpath.endswith('.js'):
        abort(404)
    return _serve_live_static_or_baked_subpath(subpath, 'js/e9', 'js/e9')

@app.route('/css/e9/<path:subpath>')
def serve_e9_css(subpath):
    if not subpath.endswith('.css'):
        abort(404)
    return _serve_live_static_or_baked_subpath(subpath, 'css/e9', 'css/e9')

@app.route('/components/adventure/<path:subpath>')
def serve_e9_components(subpath):
    if not subpath.endswith('.html'):
        abort(404)
    return _serve_live_static_or_baked_subpath(subpath, 'components/adventure', 'components/adventure')

# ══════════════════════════════════════════════════════════════
# 線上對弈模組（Socket.IO）
# ══════════════════════════════════════════════════════════════

# ── 全域狀態 ──────────────────────────────────────────────────
# _lobby[sid] = {sid, name, rank, status:'lobby'|'study'|'idle'|'waiting'|'playing', ...}
_lobby:    dict = {}
# _invites[invite_id] = {invite_id, from_sid, from_name, to_sid, size,
#                        main_time, byoyomi, komi, handicap, delivery, created_at, expires_at}
_invites:  dict = {}
_games:    dict = {}   # room_id -> game dict
_sid_room: dict = {}   # sid -> room_id
_DISCONNECT_GRACE_SEC = 60
_INVITE_TTL_SEC = 90
_HEARTBEAT_TTL_SEC = 75


def _now_ts():
    return int(time.time())


def _presence_defaults():
    return {
        'status': 'lobby',
        'activity': 'lobby',
        'presence': 'online',
        'availability': 'open',
        'dnd': False,
        'focus_until': 0,
        'last_seen': _now_ts(),
    }


def _player_availability(p):
    return p.get('availability') or ('dnd' if p.get('dnd') else 'open')


def _player_is_dnd(p):
    return _player_availability(p) == 'dnd'


def _player_status_label(p):
    status = p.get('status') or p.get('activity') or 'lobby'
    if status in ('waiting', 'playing'):
        return status
    activity = p.get('activity') or 'lobby'
    if activity in ('study', 'match', 'idle'):
        return activity
    return 'lobby'


def _player_inbox(viewer_sid):
    now = _now_ts()
    rows = []
    for inv in _invites.values():
        if inv.get('to_sid') != viewer_sid:
            continue
        if inv.get('expires_at', 0) and inv['expires_at'] < now:
            continue
        rows.append({
            'invite_id': inv['invite_id'],
            'from_sid': inv['from_sid'],
            'from_name': inv['from_name'],
            'size': inv['size'],
            'main_time': inv['main_time'],
            'byoyomi': inv['byoyomi'],
            'komi': inv['komi'],
            'handicap': inv['handicap'],
            'handicap_stones': inv.get('handicap_stones', []),
            'delivery': inv.get('delivery', 'popup'),
            'created_at': inv['created_at'],
            'expires_at': inv['expires_at'],
        })
    rows.sort(key=lambda r: (r['created_at'], r['invite_id']), reverse=True)
    return rows

# ── 工具函式 ──────────────────────────────────────────────────
def _gen_rid() -> str:
    while True:
        rid = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        if rid not in _games:
            return rid

def _opp_color(c: str) -> str:
    return 'white' if c == 'black' else 'black'

def _clamp_handicap(v) -> int:
    try:
        return max(0, min(9, int(v)))
    except Exception:
        return 0

def _auto_komi_for_handicap(handicap: int) -> float:
    return 0.5 if _clamp_handicap(handicap) > 0 else 6.5

def _handicap_points(size: int, handicap: int):
    handicap = _clamp_handicap(handicap)
    if handicap < 2:
        return []
    low = 2 if size == 9 else 3
    high = size - 1 - low
    mid = size // 2
    points = {
        2: [(low, high), (high, low)],
        3: [(low, high), (high, low), (low, low)],
        4: [(low, high), (high, low), (low, low), (high, high)],
        5: [(low, high), (high, low), (low, low), (high, high), (mid, mid)],
        6: [(low, high), (high, low), (low, low), (high, high), (low, mid), (high, mid)],
        7: [(low, high), (high, low), (low, low), (high, high), (low, mid), (high, mid), (mid, mid)],
        8: [(low, high), (high, low), (low, low), (high, high), (low, mid), (high, mid), (mid, low), (mid, high)],
        9: [(low, high), (high, low), (low, low), (high, high), (low, mid), (high, mid), (mid, low), (mid, high), (mid, mid)],
    }
    return [{'x': x, 'y': y} for x, y in points.get(handicap, [])]

def _sid_uid(sid):
    return _lobby.get(sid, {}).get('user_id')

def _same_user(sid_a, sid_b):
    """同一帳號（同 user_id）的不同分頁/連線視為同一人，禁止互相對局。"""
    ua = _sid_uid(sid_a)
    return ua is not None and ua == _sid_uid(sid_b)

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

def _lobby_snapshot(viewer_sid=None):
    viewer_uid = _lobby.get(viewer_sid, {}).get('user_id') if viewer_sid else None
    out = []
    for p in _lobby.values():
        if p.get('presence') == 'offline':
            continue
        if viewer_uid is not None and p.get('user_id') == viewer_uid and p.get('sid') != viewer_sid:
            continue
        out.append({
            'sid': p['sid'],
            'name': p['name'],
            'rank': p.get('rank', ''),
            'username': p.get('username', ''),
            'status': _player_status_label(p),
            'activity': p.get('activity', p.get('status', 'lobby')),
            'presence': p.get('presence', 'online'),
            'availability': _player_availability(p),
            'dnd': _player_is_dnd(p),
            'focus_until': p.get('focus_until', 0),
            'last_seen': p.get('last_seen', 0),
        })
    return {
        'players': out,
        'pending_invites': _player_inbox(viewer_sid) if viewer_sid else [],
        'server_time': _now_ts(),
    }

def _broadcast_lobby():
    for sid in list(_lobby.keys()):
        socketio.emit('lobby_update', _lobby_snapshot(sid), to=sid)

def _expire_invites():
    now = _now_ts()
    stale = [k for k, v in _invites.items() if now > v.get('expires_at', 0) or now - v['created_at'] > _INVITE_TTL_SEC]
    for k in stale:
        _invites.pop(k, None)


def _set_lobby_player(sid, **patch):
    if sid not in _lobby:
        return None
    _lobby[sid].update(patch)
    _lobby[sid]['last_seen'] = _now_ts()
    return _lobby[sid]


def _normalize_player_state(record, *, sid, name, rank, username, user_id):
    base = _presence_defaults()
    base.update({
        'sid': sid,
        'name': name,
        'rank': rank or '30k',
        'username': username or '',
        'user_id': user_id,
        'status': 'lobby',
    })
    if record:
        base.update(record)
    base['availability'] = _player_availability(base)
    base['dnd'] = _player_is_dnd(base)
    base['presence'] = base.get('presence') or 'online'
    base['activity'] = base.get('activity') or 'lobby'
    base['status'] = _player_status_label(base)
    base['focus_until'] = int(base.get('focus_until') or 0)
    base['last_seen'] = int(base.get('last_seen') or _now_ts())
    return base


def _cancel_invites_for_sid(sid, *, notify_outgoing=True):
    cancelled = []
    for inv in list(_invites.values()):
        if inv.get('from_sid') == sid:
            cancelled.append(('outgoing', inv))
        elif inv.get('to_sid') == sid:
            cancelled.append(('incoming', inv))
    for kind, inv in cancelled:
        _invites.pop(inv['invite_id'], None)
        if kind == 'outgoing' and notify_outgoing:
            emit('invite_cancelled', {}, to=inv['to_sid'])


def _cancel_invites_for_room(rid):
    if rid not in _games:
        return
    g = _games[rid]
    for color in ('black', 'white'):
        sid = g['players'].get(color)
        if not sid:
            continue
        _cancel_invites_for_sid(sid)


def _set_game_waiting_status(g, status):
    for color in ('black', 'white'):
        sid = g['players'].get(color)
        if sid in _lobby:
            _lobby[sid]['status'] = status
            _lobby[sid]['activity'] = 'match' if status == 'playing' else ('lobby' if status == 'waiting' else status)
            _lobby[sid]['presence'] = 'online'
            _lobby[sid]['last_seen'] = _now_ts()


def _finalize_disconnect_forfeit(rid, color):
    g = _games.get(rid)
    if not g or g.get('status') != 'disconnect_grace':
        return
    if g.get('disconnect_color') != color:
        return
    if _now_ts() < g.get('disconnect_deadline', 0):
        return
    if g.get('status') != 'disconnect_grace':
        return
    g['status'] = 'finished'
    winner = _opp_color(color)
    _finish_game(rid, g, 'disconnect', winner)


def _start_disconnect_grace(rid, g, color):
    g['status'] = 'disconnect_grace'
    g['disconnect_color'] = color
    g['disconnect_deadline'] = _now_ts() + _DISCONNECT_GRACE_SEC
    g['disconnect_started_at'] = _now_ts()

    opp_sid = g['players'].get(_opp_color(color))
    if opp_sid:
        emit('opponent_disconnected', {'reason': 'disconnect', 'grace_sec': _DISCONNECT_GRACE_SEC}, to=opp_sid)
        emit('disconnect_grace_started', {
            'reason': 'disconnect',
            'grace_sec': _DISCONNECT_GRACE_SEC,
            'deadline': g['disconnect_deadline'],
        }, to=opp_sid)

    def _watch():
        socketio.sleep(_DISCONNECT_GRACE_SEC)
        try:
            _finalize_disconnect_forfeit(rid, color)
        except Exception:
            pass

    socketio.start_background_task(_watch)

# ── 棋盤計算 ──────────────────────────────────────────────────
def _ensure_board(g):
    if g.get('_board') is None:
        sz = g['size']
        g['_board'] = [[0] * sz for _ in range(sz)]
        for st in g.get('handicap_stones') or []:
            x, y = int(st.get('x', -1)), int(st.get('y', -1))
            if 0 <= x < sz and 0 <= y < sz:
                g['_board'][y][x] = 1

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
    if board[y][x] != 0:
        raise ValueError('occupied')
    ci = 1 if g['current'] == 'black' else 2
    oi = 3 - ci
    board[y][x] = ci
    cap = 0
    captured_pts = []
    for nx, ny in _nbrs(x, y, sz):
        if board[ny][nx] == oi:
            grp, libs = _group(board, nx, ny, sz)
            if libs == 0:
                for gx, gy in grp:
                    board[gy][gx] = 0
                cap += len(grp)
                captured_pts.extend(grp)
    if cap == 0:
        _, own_libs = _group(board, x, y, sz)
        if own_libs == 0:
            board[y][x] = 0   # 還原盤面
            raise ValueError('suicide')
    # 簡單劫偵測：恰提一子、且落下的是一氣孤子 → 對方下一手不可立即回提
    if cap == 1:
        grp, libs = _group(board, x, y, sz)
        g['_ko_point'] = captured_pts[0] if (len(grp) == 1 and libs == 1) else None
    else:
        g['_ko_point'] = None
    if g['current'] == 'black':
        g['black_captures'] += cap
    else:
        g['white_captures'] += cap
    return g['black_captures'], g['white_captures']

def _rebuild_board(g):
    """從 moves 清單重建棋盤（悔棋用）。"""
    sz = g['size']
    g['_board'] = [[0] * sz for _ in range(sz)]
    for st in g.get('handicap_stones') or []:
        x, y = int(st.get('x', -1)), int(st.get('y', -1))
        if 0 <= x < sz and 0 <= y < sz:
            g['_board'][y][x] = 1
    g['black_captures'] = g['white_captures'] = 0
    g['_ko_point'] = None
    saved = g['current']
    g['current'] = 'white' if g.get('handicap', 0) > 1 else 'black'
    for mv in g['moves']:
        if not mv.get('pass'):
            _apply_move(g, mv['x'], mv['y'])
        else:
            g['_ko_point'] = None
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
    handicap = _clamp_handicap(g.get('handicap', 0))
    if handicap > 0:
        sgf += f'HA[{handicap}]'
    stones = g.get('handicap_stones') or []
    if stones:
        sgf += 'AB' + ''.join(
            f'[{_SGF_COLS[int(st["x"])]}{_SGF_COLS[int(st["y"])]}]'
            for st in stones
            if 0 <= int(st.get('x', -1)) < sz and 0 <= int(st.get('y', -1)) < sz
        )
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
            _lobby[s]['activity'] = 'lobby'
            _lobby[s]['availability'] = 'open'
            _lobby[s]['last_seen'] = _now_ts()
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
        'moves': [], 'current': 'white' if g.get('handicap', 0) > 1 else 'black',
        'black_captures': 0, 'white_captures': 0,
        'consecutive_passes': 0, 'status': 'playing',
        'rematch_votes': set(), 'undo_pending': False, '_board': None,
        'undo_requested_by': set(),   # 新一局重置悔棋次數
    })
    pkg = {'size': g['size'], 'main_time': g['main_time'], 'byoyomi': g['byoyomi'],
           'komi': g['komi'], 'handicap': g.get('handicap', 0),
           'handicap_stones': g.get('handicap_stones', []), 'current_color': g['current']}
    emit('rematch_accepted', {**pkg, 'your_color': 'black', 'opponent_name': nwn, 'opponent_rank': nwr}, to=nb)
    emit('rematch_accepted', {**pkg, 'your_color': 'white', 'opponent_name': nbn, 'opponent_rank': nbr}, to=nw)

# ── HTTP 路由 ─────────────────────────────────────────────────
@app.route('/play')
@login_required
def play_page():
    return _serve_live_static_or_baked('play.html')

@app.route('/games')
@login_required
def games_page():
    return _serve_live_static_or_baked('games.html', baked_base=_BASE)

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
        _lobby[sid]['presence'] = 'offline'
        _lobby[sid]['last_seen'] = _now_ts()
        _lobby.pop(sid, None)
        leave_room('lobby')
        _broadcast_lobby()

    # 取消此人發出的邀局，通知對方
    _cancel_invites_for_sid(sid, notify_outgoing=True)

    # 對局中斷線：先進寬限期
    rid, g, color = _get_game(sid)
    if rid and g and g['status'] == 'playing':
        _start_disconnect_grace(rid, g, color)
    _sid_room.pop(sid, None)

# ── Socket.IO：大廳 ───────────────────────────────────────────
@socketio.on('enter_lobby')
def on_enter_lobby(data):
    from flask import session as _fs
    sid     = request.sid
    name    = str(data.get('name', '玩家'))[:20].strip() or '玩家'
    uid     = _fs.get('user_id')
    activity = str(data.get('activity', 'lobby')).strip() or 'lobby'
    availability = str(data.get('availability', 'open')).strip() or 'open'
    focus_until = int(data.get('focus_until', 0) or 0)
    # 從 DB 取得 go_rank（比客戶端傳來的更可信）+ username（供個人頁連結）
    go_rank  = '30k'
    username = ''
    if uid:
        try:
            with get_db() as _c:
                _r = _c.execute('SELECT go_rank FROM user_stats WHERE user_id=?', (uid,)).fetchone()
                if _r:
                    go_rank = _r['go_rank'] or '30k'
                _u = _c.execute('SELECT username FROM users WHERE id=?', (uid,)).fetchone()
                if _u:
                    username = _u['username'] or ''
        except Exception:
            pass
    _lobby[sid] = _normalize_player_state(
        _lobby.get(sid),
        sid=sid,
        name=name,
        rank=go_rank,
        username=username,
        user_id=uid,
    )
    _lobby[sid].update({
        'activity': activity if activity in ('lobby', 'study', 'match', 'idle') else 'lobby',
        'availability': availability if availability in ('open', 'quiet', 'dnd', 'match_only') else 'open',
        'focus_until': max(0, focus_until),
        'presence': 'online',
        'status': 'lobby' if activity == 'lobby' else activity,
    })
    _lobby[sid]['dnd'] = _lobby[sid]['availability'] == 'dnd'
    join_room('lobby')
    emit('lobby_entered', {'sid': sid, 'activity': _lobby[sid]['activity'], 'availability': _lobby[sid]['availability']})
    _broadcast_lobby()

@socketio.on('toggle_dnd')
def on_toggle_dnd(data):
    sid = request.sid
    if sid not in _lobby: return
    dnd = bool(data.get('dnd', False))
    _lobby[sid]['dnd'] = dnd
    _lobby[sid]['availability'] = 'dnd' if dnd else 'open'
    _lobby[sid]['status'] = _player_status_label(_lobby[sid])
    _lobby[sid]['last_seen'] = _now_ts()
    _broadcast_lobby()

@socketio.on('set_availability')
def on_set_availability(data):
    sid = request.sid
    if sid not in _lobby: return
    value = str(data.get('availability', 'open')).strip()
    if value not in ('open', 'quiet', 'dnd', 'match_only'):
        value = 'open'
    _lobby[sid]['availability'] = value
    _lobby[sid]['dnd'] = value == 'dnd'
    _lobby[sid]['status'] = _player_status_label(_lobby[sid])
    _lobby[sid]['last_seen'] = _now_ts()
    _broadcast_lobby()

@socketio.on('set_activity')
def on_set_activity(data):
    sid = request.sid
    if sid not in _lobby: return
    value = str(data.get('activity', 'lobby')).strip()
    if value not in ('lobby', 'study', 'match', 'idle'):
        value = 'lobby'
    _lobby[sid]['activity'] = value
    if _lobby[sid].get('status') not in ('waiting', 'playing', 'disconnect_grace'):
        _lobby[sid]['status'] = value
    _lobby[sid]['last_seen'] = _now_ts()
    _broadcast_lobby()

@socketio.on('heartbeat')
def on_heartbeat(data):
    sid = request.sid
    if sid not in _lobby:
        return
    _lobby[sid]['presence'] = 'online'
    _lobby[sid]['last_seen'] = _now_ts()
    if 'activity' in data:
        on_set_activity({'activity': data.get('activity')})
    if 'availability' in data:
        on_set_availability({'availability': data.get('availability')})
    if 'focus_until' in data:
        try:
            _lobby[sid]['focus_until'] = int(data.get('focus_until') or 0)
        except Exception:
            _lobby[sid]['focus_until'] = 0

# ── Socket.IO：邀局 ───────────────────────────────────────────
@socketio.on('send_invite')
def on_send_invite(data):
    _expire_invites()
    sid    = request.sid
    to_sid = str(data.get('to_sid', ''))
    size   = int(data.get('size', 13))
    main_time = int(data.get('main_time', 0))
    byoyomi   = int(data.get('byoyomi', 0))
    handicap  = _clamp_handicap(data.get('handicap', 0))
    komi      = _auto_komi_for_handicap(handicap)
    if size not in (9, 13, 19): size = 13
    handicap_stones = _handicap_points(size, handicap)

    if sid not in _lobby:
        emit('error_msg', {'message': '請先進入大廳'}); return
    if to_sid not in _lobby:
        emit('error_msg', {'message': '對方已不在線'}); return
    target = _lobby[to_sid]
    target_av = _player_availability(target)
    if target_av == 'dnd':
        emit('error_msg', {'message': f'{target["name"]} 目前不接受邀局'}); return
    if target_av == 'match_only':
        emit('error_msg', {'message': f'{target["name"]} 目前只接受快速配對'}); return
    if target['status'] == 'playing':
        emit('error_msg', {'message': f'{target["name"]} 目前不在空閒狀態'}); return
    if _same_user(sid, to_sid):
        emit('error_msg', {'message': '不能和自己的另一個分頁／視窗對局'}); return

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
        'handicap':     handicap,
        'handicap_stones': handicap_stones,
        'delivery':     'popup' if target_av == 'open' else 'inbox',
        'created_at':   _now_ts(),
        'expires_at':   _now_ts() + _INVITE_TTL_SEC,
    }
    payload = {
        'invite_id':    invite_id,
        'from_sid':     sid,
        'from_name':    _lobby[sid]['name'],
        'size':         size,
        'main_time':    main_time,
        'byoyomi':      byoyomi,
        'komi':         komi,
        'handicap':     handicap,
        'handicap_stones': handicap_stones,
        'delivery':     _invites[invite_id]['delivery'],
        'expires_at':   _invites[invite_id]['expires_at'],
    }
    if _invites[invite_id]['delivery'] == 'popup':
        emit('invite_received', payload, to=to_sid)
    else:
        emit('invite_queued', payload, to=to_sid)
        _broadcast_lobby()

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
    if _same_user(sid, from_sid):
        emit('error_msg', {'message': '不能和自己的另一個分頁／視窗對局'}); return

    _broadcast_lobby()
    emit('invite_accepted_by', {'from_name': _lobby[sid]['name']}, to=from_sid)

    rid = _gen_rid()
    _games[rid] = {
        'size': inv['size'],
        'players': {'black': from_sid, 'white': sid},
        'names':   {'black': _lobby[from_sid]['name'], 'white': _lobby[sid]['name']},
        'moves': [], 'current': 'white' if inv.get('handicap', 0) > 1 else 'black',
        'black_captures': 0, 'white_captures': 0,
        'consecutive_passes': 0, 'status': 'playing',
        'main_time': inv['main_time'], 'byoyomi': inv['byoyomi'], 'komi': inv['komi'],
        'handicap': inv.get('handicap', 0), 'handicap_stones': inv.get('handicap_stones', []),
        'rematch_votes': set(), 'undo_pending': False, '_board': None,
    }
    _sid_room[from_sid] = rid
    _sid_room[sid]      = rid
    join_room(rid, sid=from_sid)
    join_room(rid, sid=sid)
    for s in (from_sid, sid):
        if s in _lobby:
            _lobby[s]['status'] = 'playing'
            _lobby[s]['activity'] = 'match'
            _lobby[s]['availability'] = 'match_only'
            _lobby[s]['last_seen'] = _now_ts()
    _broadcast_lobby()

    pkg = {'size': inv['size'], 'main_time': inv['main_time'], 'byoyomi': inv['byoyomi'],
           'komi': inv['komi'], 'handicap': inv.get('handicap', 0),
           'handicap_stones': inv.get('handicap_stones', []),
           'current_color': 'white' if inv.get('handicap', 0) > 1 else 'black'}
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
        _broadcast_lobby()
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
    handicap  = _clamp_handicap(data.get('handicap', 0))
    komi      = _auto_komi_for_handicap(handicap)
    handicap_stones = _handicap_points(size, handicap)

    pref = str(data.get('creator_color', 'black')).lower()
    if pref not in ('black', 'white'): pref = random.choice(('black', 'white'))
    opp  = 'white' if pref == 'black' else 'black'

    rid = _gen_rid()
    creator_rank = _lobby.get(sid, {}).get('rank', '')
    _games[rid] = {
        'size': size,
        'players': {pref: sid, opp: None},
        'names':   {pref: name, opp: None},
        'ranks':   {pref: creator_rank, opp: ''},
        'moves': [], 'current': 'white' if handicap > 1 else 'black',
        'black_captures': 0, 'white_captures': 0,
        'consecutive_passes': 0, 'status': 'waiting',
        'main_time': main_time, 'byoyomi': byoyomi, 'komi': komi,
        'handicap': handicap, 'handicap_stones': handicap_stones,
        'rematch_votes': set(), 'undo_pending': False, '_board': None,
    }
    _sid_room[sid] = rid
    join_room(rid)
    if sid in _lobby:
        _lobby[sid]['status'] = 'waiting'
        _lobby[sid]['activity'] = 'match'
        _lobby[sid]['availability'] = 'match_only'
        _lobby[sid]['last_seen'] = _now_ts()
    _broadcast_lobby()
    emit('game_created', {'room_id': rid, 'color': pref, 'komi': komi,
                          'handicap': handicap, 'handicap_stones': handicap_stones})

@socketio.on('cancel_waiting')
def on_cancel_waiting(data):
    sid = request.sid
    rid = _sid_room.pop(sid, None)
    if rid and rid in _games and _games[rid]['status'] == 'waiting':
        del _games[rid]
    if sid in _lobby:
        _lobby[sid]['status'] = 'lobby'
        _lobby[sid]['activity'] = 'lobby'
        _lobby[sid]['availability'] = 'open'
        _lobby[sid]['last_seen'] = _now_ts()
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
    if _same_user(sid, g['players']['black']):
        emit('error_msg', {'message': '不能加入自己開的房間（同一帳號）'}); return

    joiner_rank = _lobby.get(sid, {}).get('rank', '')
    # 找創房者留下的空位（可能是 black 或 white）
    joiner_color   = 'white' if g['players']['white'] is None else 'black'
    creator_color  = 'black' if joiner_color == 'white' else 'white'
    g['players'][joiner_color] = sid
    g['names'][joiner_color]   = name
    if 'ranks' not in g: g['ranks'] = {'black': '', 'white': ''}
    g['ranks'][joiner_color]   = joiner_rank
    g['status']                = 'playing'
    _sid_room[sid]             = rid
    join_room(rid)
    creator_sid = g['players'][creator_color]
    for s in (creator_sid, sid):
        if s in _lobby:
            _lobby[s]['status'] = 'playing'
            _lobby[s]['activity'] = 'match'
            _lobby[s]['availability'] = 'match_only'
            _lobby[s]['last_seen'] = _now_ts()
    _broadcast_lobby()

    pkg = {'size': g['size'], 'main_time': g['main_time'], 'byoyomi': g['byoyomi'],
           'komi': g['komi'], 'handicap': g.get('handicap', 0),
           'handicap_stones': g.get('handicap_stones', []), 'current_color': g['current']}
    emit('game_started', {**pkg,
         'opponent_name': name,                       'opponent_rank': joiner_rank,
         'your_color': creator_color},
         to=creator_sid)
    emit('game_started', {**pkg,
         'opponent_name': g['names'][creator_color],  'opponent_rank': g['ranks'][creator_color],
         'your_color': joiner_color},
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
    if g['status'] == 'disconnect_grace':
        deadline = int(g.get('disconnect_deadline', 0) or 0)
        if deadline and _now_ts() > deadline:
            _finalize_disconnect_forfeit(rid, g.get('disconnect_color'))
            emit('error_msg', {'message': '重連時間已過，這盤已判定結束'}); return

    old = g['players'].get(color)
    if old and old != sid:
        _sid_room.pop(old, None)
    g['players'][color] = sid
    g['names'][color]   = name
    _sid_room[sid]      = rid
    join_room(rid)
    if g['status'] == 'disconnect_grace':
        g['status'] = 'playing'
        g.pop('disconnect_color', None)
        g.pop('disconnect_deadline', None)
        g.pop('disconnect_started_at', None)
        _broadcast_lobby()

    opp_c = _opp_color(color)
    emit('reconnect_state', {
        'your_color':     color,
        'opponent_name':  g['names'][opp_c] or '等待對手',
        'opponent_rank':  g.get('ranks', {}).get(opp_c, ''),
        'size':           g['size'],
        'main_time':      g['main_time'],
        'byoyomi':        g['byoyomi'],
        'komi':           g['komi'],
        'handicap':       g.get('handicap', 0),
        'handicap_stones': g.get('handicap_stones', []),
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

    ko = g.get('_ko_point')
    if ko and ko == (x, y):
        emit('error_msg', {'message': '打劫！不能立即回提'}); return
    try:
        bc, wc = _apply_move(g, x, y)
    except ValueError as e:
        msg = '禁著點！此處落子後無氣' if str(e) == 'suicide' else '此點已有棋子'
        emit('error_msg', {'message': msg}); return
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
    g['_ko_point'] = None
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

def _spawn_gnugo_referee(g):
    """以 GnuGo 重播 PvP 對局，作為死活判讀／形勢估計的裁判引擎。
    回傳 GTP 行程，呼叫端負責 kill。"""
    sz = g['size']
    proc = subprocess.Popen(
        [GNUGO_EXE, '--mode', 'gtp', '--boardsize', str(sz), '--level', '1'],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    _gtp(proc, f'boardsize {sz}')
    _gtp(proc, f"komi {g['komi']}")
    for st in g.get('handicap_stones') or []:
        _gtp(proc, f"play black {_xy_to_gtp(int(st['x']), int(st['y']), sz)}")
    for m in g['moves']:
        if m.get('pass'):
            _gtp(proc, f"play {m['color']} PASS")
        else:
            _gtp(proc, f"play {m['color']} {_xy_to_gtp(m['x'], m['y'], sz)}")
    return proc

@socketio.on('request_position_eval')
def on_request_position_eval(data):
    """中盤形勢判斷：GnuGo estimate_score 取得目差（無領地圖/最佳手）"""
    sid = request.sid
    rid, g, color = _get_game(sid)
    if not rid or g.get('status') not in ('playing', 'counting'):
        emit('error_msg', {'message': '非對局中'}); return

    def _run():
        proc = None
        try:
            proc = _spawn_gnugo_referee(g)
            resp = _gtp_with_timeout(proc, 'estimate_score', 60)
            if resp is None:
                socketio.emit('position_eval_result', {'error': '估算引擎無回應'}, to=sid)
                return
            # 回應格式如 'W+12.5 (upper bound: ...)' 或 '0'
            mt = re.match(r'([BW])\+([\d.]+)', resp.strip())
            lead_black = 0.0
            if mt:
                lead_black = float(mt.group(2)) * (1 if mt.group(1) == 'B' else -1)
            cur = g['current']
            lead_cur = lead_black if cur == 'black' else -lead_black
            # GnuGo 沒有勝率輸出，用目差 sigmoid 近似（±8 目 ≈ 73%/27%）
            winrate_cur = round(100 / (1 + math.exp(-lead_cur / 8)), 1)
            socketio.emit('position_eval_result', {
                'current_color': cur,
                'winrate_for_current': winrate_cur,
                'score_lead': round(lead_cur, 1),
                'ownership_grid': None,
                'best_move': None,
                'move_count': len(g['moves']),
            }, to=sid)
        except Exception as e:
            print(f'[position_eval error] {e}')
            socketio.emit('position_eval_result', {'error': str(e)}, to=sid)
        finally:
            if proc:
                try: proc.kill()
                except Exception: pass

    threading.Thread(target=_run, daemon=True).start()
    emit('position_eval_pending', {})


@socketio.on('request_auto_dead_stones')
def on_request_auto_dead_stones(data):
    """終局自動判斷死子：GnuGo final_status_list dead"""
    sid = request.sid
    rid, g, color = _get_game(sid)
    if not rid or g.get('status') != 'counting':
        emit('error_msg', {'message': '非計分階段'}); return

    sz = g['size']

    def _run():
        proc = None
        try:
            proc = _spawn_gnugo_referee(g)
            resp = _gtp_with_timeout(proc, 'final_status_list dead', 60)
            if resp is None:
                socketio.emit('auto_dead_result', {'error': '判讀引擎無回應'}, to=sid)
                return
            dead_set = set()
            for coord in resp.split():
                xy = _gtp_to_xy(coord, sz)
                if xy:
                    dead_set.add(xy)
            g['dead_positions'] = dead_set
            g['count_confirmed'] = set()
            socketio.emit('counting_update', _counting_snapshot(g), to=rid)
            socketio.emit('auto_dead_result', {'ok': True, 'dead_count': len(dead_set)}, to=sid)
        except Exception as e:
            print(f'[auto_dead_stones error] {e}')
            socketio.emit('auto_dead_result', {'error': str(e)}, to=sid)
        finally:
            if proc:
                try: proc.kill()
                except Exception: pass

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
    # 每人每局只能申請一次悔棋（送出即消費，拒絕後也不能再申請，避免一直洗）
    used = g.setdefault('undo_requested_by', set())
    if color in used:
        emit('error_msg', {'message': '本局你已用過悔棋機會'}); return
    used.add(color)
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
                {'lv': n['lv'], 'name': n['name'], 'name_en': (_i18n_skill_node_en(n['name']) or (None,None))[0],
                 'req': n['req'], 'bonus': n['bonus'], 'bonus_en': (_i18n_skill_node_en(n['name']) or (None,None))[1],
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
                    'message': '職業選擇已移除；稱號由四大屬性自動決定。',
                    'message_en': 'Class selection has been removed; titles are assigned automatically.'}), 410


@app.route('/api/class/attr/allocate', methods=['POST'])
@login_required
def class_attr_allocate():
    """Retain the removed attribute-allocation endpoint for old clients."""
    return jsonify({
        'error': 'deprecated',
        'message': '潛能點分配已移除。',
        'message_en': 'Potential point allocation has been removed.',
    }), 410


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
                {'lv': n['lv'], 'name': n['name'], 'name_en': (_i18n_skill_node_en(n['name']) or (None,None))[0],
                 'req': n['req'], 'bonus_en': (_i18n_skill_node_en(n['name']) or (None,None))[1],
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
_RT_POOL_BUILT_AT = 0.0
_RT_POOL_LOCK = threading.Lock()
_RT_VERIFIED_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 'rating_verified_questions.json')
_RT_ANCHOR_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               'rating_anchor_questions.json')
_RT_ANCHOR_ENABLED = str(os.environ.get('RATING_ANCHOR_ENABLED', '0')).lower() \
    in ('1', 'true', 'yes', 'on')
_RT_ALGORITHM_VERSION = 'rt-anchor-mix-v1'
_RT_BASE_ALGORITHM_VERSION = 'rt-p0-v1'
_RT_ANCHOR_VERSION = None
_RT_ANCHOR_ACTIVE_COUNT = 0

def _load_rt_verified() -> dict:
    try:
        with open(_RT_VERIFIED_FILE, encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        app.logger.warning(f'[rt_pool] verified 清單載入失敗：{e}')
        return {}

def _load_rt_anchor_bank() -> dict:
    try:
        with open(_RT_ANCHOR_FILE, encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        app.logger.warning(f'[rt_pool] anchor 題庫載入失敗：{e}')
        return {}

# 各學科最低 score_gap 門檻（OK 題）—— 只在 score_gap 欄位存在時使用
_RT_DISC_THRESH = {
    'life_death':       8.0,
    'tesuji':           5.0,
    'chase':            3.0,
    'capture_escape':   3.0,
    'connection_cut':   5.0,
    'opening_direction': 3.0,
    'whole_board':      3.0,
    'shape_weakness':   3.0,
    'endgame_counting': 3.0,
}
# NG 題門檻（稍高，確保 SGF 答案路徑仍有教學價值）
_RT_DISC_THRESH_NG = {
    'life_death':       10.0,
    'tesuji':            6.5,
    'chase':             4.5,
    'capture_escape':    4.5,
    'connection_cut':    6.5,
    'opening_direction': 4.5,
    'whole_board':       4.5,
    'shape_weakness':    4.5,
    'endgame_counting':  4.5,
}

# rank 字串 → 合成 Elo rating（用於 score_gap/match 欄位尚未分析時的 fallback）
# 全 39 段位完整對照（舊版缺 12k/17k/22k 等中間值，導致章節 LV 複核後
# 大量題目 rank 查無對應 → 被整批踢出鑑定題池）。
# 錨點沿用舊表，中間段位線性插值；_rating_to_rank 由同一張表反推，確保雙向一致。
_RANK_TO_RATING: dict = {
    '30k': 1100, '29k': 1110, '28k': 1120, '27k': 1130, '26k': 1140,
    '25k': 1150, '24k': 1160, '23k': 1170, '22k': 1180, '21k': 1190,
    '20k': 1200, '19k': 1220, '18k': 1240, '17k': 1260, '16k': 1280,
    '15k': 1300, '14k': 1320, '13k': 1340, '12k': 1360, '11k': 1380,
    '10k': 1400,
    '9k':  1450, '8k':  1480, '7k': 1510,
    '6k':  1540, '5k':  1570, '4k': 1600,
    '3k':  1630, '2k':  1660, '1k': 1700,
    '1d':  1800, '2d':  1900, '3d': 2000,
    '4d':  2100, '5d':  2200, '6d': 2350,
    '7d':  2500, '8d':  2600, '9d': 2700,
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

# ── 題目難度實證校準 ──────────────────────────────────────────────────────────
# 用全站日常答題記錄（review_log）反推題目實際難度：
#   p = 答對率, u = 答題者平均 Elo → q_emp = u - 400·log10(p/(1-p))（Elo 反函數）
# 樣本越多越信實證值（shrinkage 收縮：w = n/(n+20)），樣本 < _RT_CALIB_MIN_N 不校準。
# 答對率極端（>95% / <5%、樣本≥20）的題目鑑別度太低 → 直接踢出鑑定題池。
_RT_CALIB_MIN_N = 10
_RT_LIVE_CALIBRATION_ENABLED = str(
    os.environ.get('RATING_LIVE_CALIBRATION_ENABLED', '0')
).lower() in ('1', 'true', 'yes', 'on')

def _load_rt_calibration() -> dict:
    """優先使用鑑定專用完整作答；不足時才用排除 rt 兌獎的日常紀錄。"""
    if not _RT_LIVE_CALIBRATION_ENABLED:
        return {}
    try:
        with get_db() as conn:
            rt_rows = conn.execute(
                'SELECT question_id AS qid,COUNT(*) AS n,'
                ' AVG(correct * 1.0) AS acc,AVG(ability_before) AS avg_elo '
                'FROM rating_test_responses '
                'WHERE response_ms IS NULL OR response_ms >= 800 '
                'GROUP BY question_id HAVING COUNT(*) >= ?',
                (_RT_CALIB_MIN_N,)
            ).fetchall()
            fallback_rows = conn.execute(
                'SELECT r.question_id AS qid, COUNT(*) AS n, '
                '       AVG(CASE WHEN r.grade >= 2 THEN 1.0 ELSE 0.0 END) AS acc, '
                '       AVG(COALESCE(u.elo_rating, 1500)) AS avg_elo '
                'FROM review_log r LEFT JOIN users u ON u.id = r.user_id '
                "WHERE COALESCE(r.source, '') NOT LIKE 'rt:%%' "
                'GROUP BY r.question_id HAVING COUNT(*) >= ?',
                (_RT_CALIB_MIN_N,)
            ).fetchall()
        result = {int(r['qid']): {
            'n': int(r['n']), 'acc': float(r['acc']), 'avg_elo': float(r['avg_elo'])
        } for r in fallback_rows}
        result.update({int(r['qid']): {
            'n': int(r['n']), 'acc': float(r['acc']), 'avg_elo': float(r['avg_elo'])
        } for r in rt_rows})
        return result
    except Exception as e:
        app.logger.warning(f'[rt_calibration] 實證校準查詢失敗，沿用合成難度：{e}')
        return {}

def _calibrated_rating(synthetic: float, calib: dict | None) -> tuple[float, bool]:
    """混合合成難度與實證難度。回傳 (rating, 是否該踢出題池)。"""
    if not calib:
        return synthetic, False
    n, acc, avg_elo = calib['n'], calib['acc'], calib['avg_elo']
    if n >= 20 and (acc > 0.95 or acc < 0.05):
        return synthetic, True          # 無鑑別度（太簡單/太難或答案有問題）
    p = max(0.03, min(0.97, acc))
    emp = avg_elo - 400.0 * math.log10(p / (1.0 - p))
    emp = max(1000.0, min(2600.0, emp))
    w = n / (n + 20.0)                  # n=10→0.33, n=20→0.5, n=80→0.8
    return w * emp + (1.0 - w) * synthetic, False

# ── 後端重放驗證（防作弊）─────────────────────────────────────────────────────
# 前端傳玩家落子座標序列，後端在「同一旋轉版本」的 SGF 答案樹上重放：
# 玩家手須匹配某子節點（支援多分支正解），對手回應沿 children[0] 走。
# 完整走到正解葉 → 正確。前端的 correct 布林不再被信任。

def _rt_find_closing(s: str, i: int) -> int:
    d = 0
    for j in range(i, len(s)):
        if s[j] == '(':
            d += 1
        elif s[j] == ')':
            d -= 1
            if d == 0:
                return j
    return len(s) - 1

def _rt_parse_seq(s: str):
    """解析 ';B[xy];W[xy](...)' 序列為節點鏈，分支掛在最後一個節點下。"""
    s = s.strip()
    nodes_raw, i = [], 0
    while i < len(s):
        if s[i] == ';':
            j, d = i + 1, 0
            while j < len(s):
                ch = s[j]
                if ch == '(':
                    if d == 0:
                        break
                    d += 1
                elif ch == ')':
                    if d == 0:
                        break
                    d -= 1
                elif ch == ';' and d == 0:
                    break
                j += 1
            nodes_raw.append(s[i:j])
            i = j
        elif s[i] == '(':
            break
        else:
            i += 1
    branch_start = i
    nodes = []
    for raw in nodes_raw:
        raw = raw.strip()
        # B/W 屬性不一定緊跟節點開頭（如 ';KEY[]B[dm]'），容忍前置屬性；
        # (?<![A-Z]) 防止吃到 AB[]/AW[] 設置子
        m = (_re_mod.match(r'^;\s*([BW])\[([a-zA-Z]{0,2})\]', raw)
             or _re_mod.search(r'(?<![A-Z])([BW])\[([a-zA-Z]{0,2})\]', raw))
        if not m:
            continue
        c = m.group(2).lower()
        move = (ord(c[0]) - 97, ord(c[1]) - 97) if len(c) == 2 and c != 'tt' else None
        nodes.append({'color': m.group(1).upper(), 'move': move, 'children': []})
    if not nodes:
        return None
    for k in range(len(nodes) - 1):
        nodes[k]['children'].append(nodes[k + 1])
    last, bi = nodes[-1], branch_start
    while bi < len(s):
        if s[bi] == '(':
            e = _rt_find_closing(s, bi)
            child = _rt_parse_seq(s[bi + 1:e])
            if child:
                last['children'].append(child)
            bi = e + 1
        else:
            bi += 1
    return nodes[0]

def _rt_parse_answer_tree(sgf: str):
    """從 SGF 取出答案樹根（root 節點之後的手順與分支）。失敗回 None。"""
    if not sgf:
        return None
    body = sgf.strip()
    if body.startswith('('):
        body = body[1:]
    # 跳過根節點屬性（第一個 ';' 起到下一個 ';' 或 '(' 為止）
    m = _re_mod.match(r'^\s*;', body)
    if not m:
        return None
    j, depth = 1, 0
    in_bracket = False
    while j < len(body):
        ch = body[j]
        if in_bracket:
            if ch == '\\':
                j += 1
            elif ch == ']':
                in_bracket = False
        elif ch == '[':
            in_bracket = True
        elif ch in ';(':
            break
        j += 1
    after = body[j:].strip()
    root = {'color': None, 'move': None, 'children': []}
    if after.startswith(';'):
        seq = _rt_parse_seq(after)
        if seq:
            root['children'].append(seq)
    elif after.startswith('('):
        i = 0
        while i < len(after):
            if after[i] == '(':
                e = _rt_find_closing(after, i)
                child = _rt_parse_seq(after[i + 1:e])
                if child:
                    root['children'].append(child)
                i = e + 1
            else:
                i += 1
    return root if root['children'] else None

def _rt_replay(tree_root, moves: list) -> bool:
    """在答案樹上重放玩家落子序列。完整走到正解葉回 True。"""
    cur = tree_root
    for mv in moves:
        xy = (mv.get('x'), mv.get('y'))
        matched = next((c for c in cur['children']
                        if c['move'] and tuple(c['move']) == xy), None)
        if matched is None:
            return False
        cur = matched
        if not cur['children']:
            return True
        reply = cur['children'][0]
        if not reply.get('move'):
            return True
        cur = reply
        if not cur['children']:
            return True
    return False   # 落子序列提前結束（未走到正解葉）

def _gtp_to_xy(gtp: str, size: int):
    """GTP 座標（如 Q16）→ SGF (x, y)。I 行跳過；失敗回 None。"""
    m = _re_mod.match(r'^([A-HJ-T])(\d{1,2})$', (gtp or '').upper().strip())
    if not m:
        return None
    col_letters = 'ABCDEFGHJKLMNOPQRST'
    x = col_letters.find(m.group(1))
    row = int(m.group(2))
    if x < 0 or not (1 <= row <= size):
        return None
    return (x, size - row)

def _transform_point(x: int, y: int, size: int, t: int):
    """單點套用第 t 種幾何變換（與 _transform_sgf 同一組定義）。"""
    n = size - 1
    fns = (
        lambda c, r: (c, r),
        lambda c, r: (n - r, c),
        lambda c, r: (n - c, n - r),
        lambda c, r: (r, n - c),
        lambda c, r: (n - c, r),
        lambda c, r: (c, n - r),
        lambda c, r: (r, c),
        lambda c, r: (n - r, n - c),
    )
    return fns[t](x, y)

def _rt_server_verify(pool_q: dict, sid: str, moves: list):
    """後端權威判定。SGF 樹重放 → 失敗再試 KataGo 最佳手容錯（多正解）。
    回傳 True/False；SGF 樹解析失敗（後端無從判定）回 None，呼叫端沿用前端布林，
    避免解析器邊緣情況冤枉答對的玩家。"""
    t = _rt_transform_idx(sid, pool_q['id'])
    sgf_t = _transform_sgf(pool_q['content'], t)
    accepted_moves = {
        (m['x'], m['y'])
        for m in _question_accepted_moves(pool_q)
        if isinstance(m.get('x'), int) and isinstance(m.get('y'), int)
    }
    if len(moves) == 1 and accepted_moves:
        first = moves[0] or {}
        if (first.get('x'), first.get('y')) in accepted_moves:
            return True
    tree = _rt_parse_answer_tree(sgf_t)
    if tree is not None and _rt_replay(tree, moves):
        return True
    # 多正解容錯：玩家第一手 = KataGo 最佳手（SGF 沒收錄的另一個正解）
    if len(moves) == 1 and pool_q.get('katago_best_move'):
        m_sz = _re_mod.search(r'SZ\[(\d+)\]', pool_q['content'])
        size = int(m_sz.group(1)) if m_sz else 19
        bm = _gtp_to_xy(pool_q['katago_best_move'], size)
        if bm:
            bx, by = _transform_point(bm[0], bm[1], size, t)
            if (moves[0].get('x'), moves[0].get('y')) == (bx, by):
                return True
    if tree is None:
        return None    # 無法解析 → 不判定
    return False

def _build_rt_pool():
    global _RT_POOL, _RT_POOL_READY, _RT_POOL_BUILT_AT
    global _RT_ANCHOR_VERSION, _RT_ANCHOR_ACTIVE_COUNT
    calib_map = _load_rt_calibration()
    verified_map = _load_rt_verified()
    anchor_bank = _load_rt_anchor_bank()
    anchor_entries = {
        row.get('source'): row
        for row in anchor_bank.get('questions', [])
        if isinstance(row, dict) and row.get('source')
    }
    anchor_active_sources = set(
        anchor_bank.get('active_wave', {}).get('sources', [])
        if isinstance(anchor_bank.get('active_wave'), dict) else []
    )
    n_calibrated = n_culled = n_unparseable = n_duplicate = n_verified = 0
    pool = []
    content_hashes = set()
    for q in _load_questions():
        if not q.get('enabled', True):
            continue
        disc = q.get('discipline', '')
        source = str(q.get('source', '')).replace('\\', '/').strip()
        verified_entry = verified_map.get(source)
        match_val = q.get('match', '')
        raw_rating = q.get('rating') or 0
        gap = q.get('score_gap') or 0

        content = q.get('content', '')
        if not content or _rt_parse_answer_tree(content) is None:
            n_unparseable += 1
            continue
        content_hash = hashlib.sha1(content.strip().encode('utf-8')).hexdigest()
        if content_hash in content_hashes:
            n_duplicate += 1
            continue
        content_hashes.add(content_hash)

        if not (isinstance(verified_entry, dict) and
                verified_entry.get('content_hash') == content_hash):
            verified_entry = None
        if verified_entry:
            match_val = 'OK'
            gap = float(verified_entry.get('score_gap') or 0.0)
            raw_rating = raw_rating or _RANK_TO_RATING.get(
                q.get('rank') or q.get('difficulty') or '', 0
            )

        # ── 模式 A：題目已有 KataGo 分析資料（match / score_gap / rating）──
        verified = bool(match_val in ('OK', 'NG') and raw_rating and gap)
        if verified:
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

        # 實證校準：有足夠作答樣本的題，用真實答對率修正難度
        c = calib_map.get(q['id'])
        rating, cull = _calibrated_rating(float(rating), c)
        if cull:
            n_culled += 1
            continue
        if c:
            n_calibrated += 1
        if verified:
            n_verified += 1

        source_group = source.rsplit('/', 1)[0] if '/' in source else source
        anchor_entry = anchor_entries.get(source)
        anchor_active = bool(
            verified and source in anchor_active_sources
            and isinstance(anchor_entry, dict)
            and anchor_entry.get('content_hash') == content_hash
        )
        pool.append({
            'id':               q['id'],
            'content':          content,
            'rating':           rating,
            'difficulty':       q.get('difficulty') or q.get('rank', ''),
            'discipline':       disc,
            'source':           source,
            'source_group':     source_group,
            'quality':          'verified' if verified else 'fallback',
            'content_hash':     content_hash,
            'katago_best_move': (
                (verified_entry or {}).get('move') or q.get('katago_best_move') or ''
            ).upper().strip(),
            'score_gap':        gap,
            'anchor_active':    anchor_active,
        })
    pool.sort(key=lambda x: x['rating'])
    _RT_POOL = pool
    _RT_POOL_READY = True
    _RT_POOL_BUILT_AT = time.time()
    _RT_ANCHOR_ACTIVE_COUNT = sum(1 for q in pool if q.get('anchor_active'))
    expected_anchor_count = int(
        anchor_bank.get('active_wave', {}).get('count', 0)
        if isinstance(anchor_bank.get('active_wave'), dict) else 0
    )
    _RT_ANCHOR_VERSION = (
        str(anchor_bank.get('bank_version') or '')
        if _RT_ANCHOR_ACTIVE_COUNT > 0
        and _RT_ANCHOR_ACTIVE_COUNT == expected_anchor_count else None
    )
    if _RT_ANCHOR_ENABLED and not _RT_ANCHOR_VERSION:
        app.logger.error('[rt_pool] anchor 題庫不完整，已停用混合選題')
    app.logger.info(f'[rt_pool] 題池 {len(pool)} 題（verified {n_verified}、'
                    f'實證校準 {n_calibrated}、剔除無鑑別度 {n_culled}、'
                    f'答案樹無效 {n_unparseable}、重複 {n_duplicate}、'
                    f'active anchors {_RT_ANCHOR_ACTIVE_COUNT}）')
    return len(pool)

def _ensure_rt_pool():
    expired = (_RT_POOL_READY and _RT_POOL_BUILT_AT > 0 and
               time.time() - _RT_POOL_BUILT_AT > 21600)
    if not _RT_POOL_READY or expired:
        with _RT_POOL_LOCK:
            expired = (_RT_POOL_READY and _RT_POOL_BUILT_AT > 0 and
                       time.time() - _RT_POOL_BUILT_AT > 21600)
            if not _RT_POOL_READY or expired:
                _build_rt_pool()

# ── 自適應能力估計 ───────────────────────────────────────────────────────────
_RT_PLACEMENT_ROUNDS = 7
_RT_MIN_ROUNDS   = 12
_RT_MAX_ROUNDS   = 16
_RT_TARGET_SE    = 95.0

def _placement_rounds(init_rating: float) -> int:
    """快速定位固定七題；結果一律是暫定能力區間。"""
    return _RT_PLACEMENT_ROUNDS

def _rt_probability(ability: float, question_rating: float) -> float:
    """Rasch/1PL 模型下答對題目的機率。"""
    z = max(-20.0, min(20.0, math.log(10.0) * (ability - question_rating) / 400.0))
    return 1.0 / (1.0 + math.exp(-z))

def _rt_estimate(answers: list, prior_mean: float = 1500.0,
                 prior_sd: float = 300.0) -> tuple[float, float]:
    """以自報／既有棋力為常態先驗，計算 Rasch MAP 能力與後驗標準誤。"""
    theta = max(700.0, min(2500.0, float(prior_mean)))
    prior_sd = max(80.0, min(500.0, float(prior_sd or 300.0)))
    a = math.log(10.0) / 400.0
    for _ in range(12):
        grad = -(theta - prior_mean) / (prior_sd * prior_sd)
        info = 1.0 / (prior_sd * prior_sd)
        for ans in answers:
            q_rating = float(ans.get('q_rating', theta))
            p = _rt_probability(theta, q_rating)
            grad += a * ((1.0 if ans.get('correct') else 0.0) - p)
            info += a * a * p * (1.0 - p)
        step = grad / max(info, 1e-12)
        theta = max(700.0, min(2500.0, theta + step))
        if abs(step) < 0.05:
            break
    info = 1.0 / (prior_sd * prior_sd)
    for ans in answers:
        p = _rt_probability(theta, float(ans.get('q_rating', theta)))
        info += a * a * p * (1.0 - p)
    return theta, math.sqrt(1.0 / max(info, 1e-12))

def _rt_converged(answers: list, prior_mean: float = 1500.0,
                  prior_sd: float = 300.0) -> bool:
    """正式測驗至少十二題，且後驗標準誤達門檻才算收斂。"""
    if len(answers) < _RT_MIN_ROUNDS:
        return False
    return _rt_estimate(answers, prior_mean, prior_sd)[1] <= _RT_TARGET_SE

def _rt_se(answers: list, prior_mean: float = 1500.0,
           prior_sd: float = 300.0) -> float:
    return _rt_estimate(answers, prior_mean, prior_sd)[1]

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

# 由 _RANK_TO_RATING 反推段位（相鄰段位 rating 中點為分界）→ 與選題用的同一張表，
# 玩家收斂在某段位題目的 rating，顯示出來就是那個段位。
_RATING_BRACKETS: list = sorted(
    ((r, k) for k, r in _RANK_TO_RATING.items() if k not in ('8d', '9d')),
    key=lambda x: x[0]
)

def _rating_to_rank(rating: float) -> str:
    """rating → 段位標籤（取代表 rating 最接近的段位）。"""
    if rating < 1105:
        return '30k'
    best = _RATING_BRACKETS[0][1]
    for i, (r, label) in enumerate(_RATING_BRACKETS):
        nxt = _RATING_BRACKETS[i + 1][0] if i + 1 < len(_RATING_BRACKETS) else None
        best = label
        if nxt is not None and rating < (r + nxt) / 2:
            break
    if best == '7d':
        return '7d+'
    return best

_RT_PLACEMENT_ANCHOR_ROUNDS = frozenset((1, 4))
_RT_FORMAL_ANCHOR_ROUNDS = frozenset((1, 5, 9))

def _rt_anchor_available() -> bool:
    return bool(_RT_ANCHOR_ENABLED and _RT_ANCHOR_VERSION
                and _RT_ANCHOR_ACTIVE_COUNT > 0)

def _rt_desired_question_role(trigger: str, round_idx: int,
                              anchor_enabled: bool) -> str:
    if not anchor_enabled:
        return 'regular'
    rounds = (_RT_PLACEMENT_ANCHOR_ROUNDS
              if str(trigger or '').strip() == 'placement'
              else _RT_FORMAL_ANCHOR_ROUNDS)
    return 'anchor' if round_idx in rounds else 'regular'

def _pick_question(cur_rating: float, round_idx: int, used_ids: set,
                   streak: int = 0, prev_streak: int = 0,
                   discipline_counts: dict | None = None,
                   source_counts: dict | None = None,
                   question_role: str = 'regular',
                   anchor_enabled: bool = False) -> dict | None:
    """選擇接近目前能力、且優先補足尚未覆蓋學科與來源的題目。"""
    _ensure_rt_pool()
    target = max(1100.0, min(2500.0, float(cur_rating)))
    spread = 300.0 if round_idx < 2 else (220.0 if round_idx < 6 else 170.0)

    eligible_pool = _RT_POOL
    if anchor_enabled:
        if question_role == 'anchor':
            eligible_pool = [q for q in _RT_POOL if q.get('anchor_active')]
        else:
            eligible_pool = [q for q in _RT_POOL if not q.get('anchor_active')]

    candidates = [q for q in eligible_pool
                  if abs(q['rating'] - target) <= spread
                  and q['id'] not in used_ids]

    verified_candidates = [q for q in candidates if q.get('quality') == 'verified']
    if verified_candidates:
        candidates = verified_candidates

    if not candidates:
        candidates = sorted(
            (q for q in eligible_pool if q['id'] not in used_ids),
            key=lambda q: abs(q['rating'] - cur_rating)
        )[:15]

    if not candidates:
        return None
    discipline_counts = discipline_counts or {}
    source_counts = source_counts or {}
    available_discs = {q.get('discipline', '') for q in candidates}
    min_disc_count = min((discipline_counts.get(d, 0) for d in available_discs), default=0)
    preferred_discs = {d for d in available_discs if discipline_counts.get(d, 0) == min_disc_count}
    balanced = [q for q in candidates if q.get('discipline', '') in preferred_discs]
    balanced.sort(key=lambda q: (
        abs(q['rating'] - target),
        source_counts.get(q.get('source_group', ''), 0),
        0 if q.get('quality') == 'verified' else 1,
    ))
    return random.choice(balanced[:min(5, len(balanced))])

def _rt_transform_idx(sid: str, q_id) -> int:
    """由 (session, 題號) 決定旋轉版本：前端拿到的棋盤與後端重放驗證用同一座標系，
    毋須在 DB 多存欄位。對玩家而言仍等同隨機 8 選 1。"""
    h = hashlib.sha1(f'{sid}:{q_id}'.encode()).hexdigest()
    return int(h, 16) % 8

def _strip_question(q: dict, sid: str, token: str | None = None) -> dict:
    """只回傳前端需要的欄位，並套用確定性幾何旋轉讓同一題產生 8 種視覺版本。"""
    t = _rt_transform_idx(sid, q['id'])
    content = _transform_sgf(q['content'], t)
    size_m = _re_mod.search(r'SZ\[(\d+)\]', q.get('content') or '')
    size = int(size_m.group(1)) if size_m else 19
    result = {
        'id':         q['id'],
        'content':    content,
        'rating':     q['rating'],
        'difficulty': q['difficulty'],
        'discipline': q['discipline'],
    }
    accepted_moves = _question_accepted_moves(q)
    if accepted_moves:
        result['accepted_moves'] = [
            {'x': px, 'y': py}
            for m in accepted_moves
            for px, py in [_transform_point(m['x'], m['y'], size, t)]
        ]
    if token:
        result['token'] = token
    return result

def _rt_recent_seen_ids(conn, uid, exclude_sid: str | None = None,
                        n_sessions: int = 5, days: int = 180) -> set:
    if not uid:
        return set()
    cutoff = (datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
              - datetime.timedelta(days=days)).isoformat()
    if exclude_sid:
        rows = conn.execute(
            'SELECT answers FROM rating_test_sessions '
            'WHERE user_id=? AND status=? AND id<>? AND finished_at>=? '
            'ORDER BY finished_at DESC LIMIT ?',
            (uid, 'completed', exclude_sid, cutoff, n_sessions)
        ).fetchall()
    else:
        rows = conn.execute(
            'SELECT answers FROM rating_test_sessions '
            'WHERE user_id=? AND status=? AND finished_at>=? '
            'ORDER BY finished_at DESC LIMIT ?',
            (uid, 'completed', cutoff, n_sessions)
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

def _get_recent_seen_ids(uid, n_sessions: int = 5, days: int = 180) -> set:
    """回傳用戶近期已完成測驗的所有答題 question_id，避免跨場重複。"""
    if not uid:
        return set()
    with get_db() as conn:
        return _rt_recent_seen_ids(conn, uid, n_sessions=n_sessions, days=days)

def _rt_client_exclude_ids(value, limit: int = 200) -> set:
    """Parse the bounded, UX-only exclusion list sent by anonymous clients."""
    if not isinstance(value, list):
        return set()
    result = set()
    for raw in value[:limit]:
        try:
            qid = int(raw)
        except (TypeError, ValueError):
            continue
        if qid > 0:
            result.add(qid)
    return result


# ── API 路由 ─────────────────────────────────────────────────────────────────

@app.route('/api/rating_test/pool_info')
def rt_pool_info():
    """回傳題庫規模（供介紹頁面顯示真實數字）。"""
    _ensure_rt_pool()
    verified = sum(1 for q in _RT_POOL if q.get('quality') == 'verified')
    return jsonify({
        'pool_size': len(_RT_POOL),
        'verified_size': verified,
        'fallback_size': len(_RT_POOL) - verified,
        'anchor_enabled': _rt_anchor_available(),
        'anchor_version': _RT_ANCHOR_VERSION,
        'anchor_active_size': _RT_ANCHOR_ACTIVE_COUNT,
        'live_calibration_enabled': _RT_LIVE_CALIBRATION_ENABLED,
    })


@app.route('/api/admin/rating_test/metrics')
@admin_required
def rt_admin_metrics():
    """近三十天完成率、耗時與逐題流失資料，供調整快速測驗題數。"""
    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    cutoff = (now - datetime.timedelta(days=30)).isoformat()
    with get_db() as conn:
        rows = conn.execute(
            'SELECT trigger,status,round,started_at,last_activity_at,finished_at '
            'FROM rating_test_sessions WHERE started_at>=?', (cutoff,)
        ).fetchall()
        response_rows = conn.execute(
            'SELECT round,response_ms FROM rating_test_responses '
            'WHERE created_at>=? AND response_ms IS NOT NULL', (cutoff,)
        ).fetchall()

    def percentile(values, fraction):
        values = sorted(values)
        if not values:
            return None
        return values[min(len(values) - 1, round((len(values) - 1) * fraction))]

    by_trigger = {}
    for row in rows:
        trigger = row['trigger'] or 'manual'
        bucket = by_trigger.setdefault(trigger, {
            'started': 0, 'completed': 0, 'abandoned_after_1h': 0,
            'durations_seconds': [], 'rounds_completed': [],
        })
        bucket['started'] += 1
        bucket['rounds_completed'].append(int(row['round'] or 0))
        if row['status'] == 'completed':
            bucket['completed'] += 1
            try:
                started = datetime.datetime.fromisoformat(row['started_at'])
                finished = datetime.datetime.fromisoformat(row['finished_at'])
                bucket['durations_seconds'].append(max(0, (finished - started).total_seconds()))
            except Exception:
                pass
        else:
            try:
                last = datetime.datetime.fromisoformat(
                    row['last_activity_at'] or row['started_at']
                )
                if now - last >= datetime.timedelta(hours=1):
                    bucket['abandoned_after_1h'] += 1
            except Exception:
                pass

    summary = {}
    for trigger, bucket in by_trigger.items():
        started = bucket['started']
        summary[trigger] = {
            'started': started,
            'completed': bucket['completed'],
            'completion_rate': round(bucket['completed'] / started, 4) if started else None,
            'abandoned_after_1h': bucket['abandoned_after_1h'],
            'median_seconds': percentile(bucket['durations_seconds'], 0.5),
            'p90_seconds': percentile(bucket['durations_seconds'], 0.9),
            'median_round_reached': percentile(bucket['rounds_completed'], 0.5),
        }

    response_by_round = {}
    for row in response_rows:
        response_by_round.setdefault(int(row['round']) + 1, []).append(int(row['response_ms']))
    return jsonify({
        'window_days': 30,
        'sessions': summary,
        'response_time_by_round': {
            str(round_no): {
                'n': len(values),
                'median_ms': percentile(values, 0.5),
                'p90_ms': percentile(values, 0.9),
            }
            for round_no, values in sorted(response_by_round.items())
        },
    })


_RT_SHADOW_REVIEW_TARGET = 200

_RT_SHADOW_READINESS_SQL = (
    'WITH session_quality AS ('
    ' SELECT s.id,s.user_id,s.finished_at,COUNT(r.id) AS response_count,'
    ' SUM(CASE WHEN r.id IS NOT NULL AND (r.response_ms IS NULL'
    ' OR r.response_ms<? OR r.response_ms>?) THEN 1 ELSE 0 END)'
    ' AS invalid_response_count,'
    ' SUM(CASE WHEN r.question_role=? AND r.bank_version=?'
    ' AND r.algorithm_version=? THEN 1 ELSE 0 END)'
    ' AS current_anchor_count'
    ' FROM rating_test_sessions s'
    ' JOIN users u ON u.id=s.user_id'
    ' LEFT JOIN rating_test_responses r ON r.session_id=s.id'
    ' WHERE s.status=? AND s.trigger=? AND s.algorithm_version=?'
    ' AND COALESCE(u.is_admin,0)=0'
    ' GROUP BY s.id,s.user_id,s.finished_at'
    ') SELECT COUNT(*) AS valid_sessions,'
    ' COUNT(DISTINCT user_id) AS unique_players,'
    ' MAX(finished_at) AS latest_completed_at'
    ' FROM session_quality WHERE response_count>=?'
    ' AND invalid_response_count=0 AND current_anchor_count>=1'
)


def _rt_shadow_readiness_query_args(bank_version: str) -> tuple:
    return (
        800, 300000, 'anchor', bank_version, _RT_ALGORITHM_VERSION,
        'completed', 'manual', _RT_ALGORITHM_VERSION, _RT_MIN_ROUNDS,
    )


def _rt_shadow_readiness_payload(valid_sessions, unique_players,
                                 latest_completed_at) -> dict:
    """Build the admin-facing gate status without changing live scoring."""
    valid_sessions = max(0, int(valid_sessions or 0))
    unique_players = max(0, int(unique_players or 0))
    target = _RT_SHADOW_REVIEW_TARGET
    ready = valid_sessions >= target
    return {
        'valid_sessions': valid_sessions,
        'target_sessions': target,
        'remaining_sessions': max(0, target - valid_sessions),
        'unique_players': unique_players,
        'progress_percent': round(min(100.0, valid_sessions * 100.0 / target), 1),
        'ready_for_review': ready,
        'latest_completed_at': latest_completed_at,
        'live_scoring_unchanged': True,
        'criteria': {
            'authenticated_non_admin': True,
            'trigger': 'manual',
            'status': 'completed',
            'algorithm_version': _RT_ALGORITHM_VERSION,
            'minimum_responses': _RT_MIN_ROUNDS,
            'response_time_range_ms': [800, 300000],
            'requires_current_anchor': True,
        },
    }


@app.route('/api/admin/rating_test/shadow_readiness')
@admin_required
def rt_admin_shadow_readiness():
    """Count valid formal tests toward the 200-session shadow review gate."""
    _ensure_rt_pool()
    if not _RT_ANCHOR_VERSION:
        return jsonify({'error': 'anchor_bank_unavailable'}), 503
    with get_db() as conn:
        row = conn.execute(
            _RT_SHADOW_READINESS_SQL,
            _rt_shadow_readiness_query_args(_RT_ANCHOR_VERSION)
        ).fetchone()
    return jsonify(_rt_shadow_readiness_payload(
        row['valid_sessions'], row['unique_players'], row['latest_completed_at']
    ))


def _rt_calibration_exclusion(row: dict, bank_version: str) -> str | None:
    """Return why a raw response must not enter item calibration."""
    if row['question_role'] != 'anchor':
        return 'non_anchor'
    if row['bank_version'] != bank_version:
        return 'wrong_bank_version'
    if row['algorithm_version'] != _RT_ALGORITHM_VERSION:
        return 'wrong_algorithm_version'
    if row['session_status'] != 'completed':
        return 'incomplete_session'
    if row['is_admin']:
        return 'admin_account'
    response_ms = row['response_ms']
    if response_ms is None:
        return 'missing_response_time'
    if int(response_ms) < 800:
        return 'too_fast'
    if int(response_ms) > 300000:
        return 'too_slow'
    return None


def _rt_calibration_ability_band(rating: float) -> str:
    value = float(rating)
    if value < 1400:
        return 'foundation'
    if value < 1540:
        return 'kyu_10_7'
    if value < 1800:
        return 'kyu_6_1'
    if value < 2000:
        return 'dan_1_2'
    if value < 2200:
        return 'dan_3_4'
    return 'dan_5_plus'


def _rt_build_calibration_report(rows: list, pool: list,
                                 bank_version: str) -> dict:
    active_questions = {
        q['id']: q for q in pool if q.get('anchor_active')
    }
    item_stats = {
        qid: {
            'question_id': qid,
            'source': question.get('source', ''),
            'discipline': question.get('discipline', ''),
            'rating': question.get('rating'),
            'total_responses': 0,
            'eligible_responses': 0,
            'correct': 0,
            'response_times': [],
            'ability_bands': set(),
        }
        for qid, question in active_questions.items()
    }
    exclusions = Counter()
    eligible_total = 0

    for row in rows:
        stats = item_stats.get(int(row['question_id']))
        if stats is not None and row['question_role'] == 'anchor':
            stats['total_responses'] += 1
        reason = _rt_calibration_exclusion(row, bank_version)
        if reason:
            exclusions[reason] += 1
            continue
        if stats is None:
            exclusions['anchor_not_in_active_bank'] += 1
            continue
        stats['eligible_responses'] += 1
        stats['correct'] += int(bool(row['correct']))
        stats['response_times'].append(int(row['response_ms']))
        stats['ability_bands'].add(
            _rt_calibration_ability_band(float(row['ability_before']))
        )
        eligible_total += 1

    status_counts = Counter()
    items = []
    for stats in item_stats.values():
        n = stats['eligible_responses']
        coverage = len(stats['ability_bands'])
        accuracy = stats['correct'] / n if n else None
        needs_review = bool(
            n >= 15 and accuracy is not None
            and (accuracy <= 0.05 or accuracy >= 0.95)
        )
        if needs_review:
            status = 'needs_review'
        elif n < 15:
            status = 'collecting'
        elif n < 30:
            status = 'review_window'
        elif coverage < 3:
            status = 'insufficient_coverage'
        elif n < 80:
            status = 'preliminary_ready'
        else:
            status = 'calibration_ready'
        times = sorted(stats.pop('response_times'))
        bands = sorted(stats.pop('ability_bands'))
        stats.update({
            'accuracy': round(accuracy, 4) if accuracy is not None else None,
            'median_response_ms': (
                times[(len(times) - 1) // 2] if times else None
            ),
            'ability_band_count': coverage,
            'ability_bands': bands,
            'status': status,
            'needs_review': needs_review,
        })
        status_counts[status] += 1
        items.append(stats)

    items.sort(key=lambda row: (float(row['rating']), row['discipline'], row['question_id']))
    return {
        'bank_version': bank_version,
        'algorithm_version': _RT_ALGORITHM_VERSION,
        'active_items': len(items),
        'eligible_responses': eligible_total,
        'excluded_responses': sum(exclusions.values()),
        'exclusions': dict(sorted(exclusions.items())),
        'status_counts': dict(sorted(status_counts.items())),
        'items': items,
    }


@app.route('/api/admin/rating_test/calibration')
@admin_required
def rt_admin_calibration():
    """Current anchor-wave sample quality and per-item calibration readiness."""
    _ensure_rt_pool()
    if not _RT_ANCHOR_VERSION:
        return jsonify({'error': 'anchor_bank_unavailable'}), 503
    with get_db() as conn:
        rows = conn.execute(
            'SELECT r.question_id,r.correct,r.response_ms,r.ability_before,'
            ' r.question_role,r.bank_version,r.algorithm_version,'
            ' s.status AS session_status,COALESCE(u.is_admin,0) AS is_admin '
            'FROM rating_test_responses r '
            'JOIN rating_test_sessions s ON s.id=r.session_id '
            'LEFT JOIN users u ON u.id=r.user_id '
            'WHERE r.algorithm_version=? ORDER BY r.id',
            (_RT_ALGORITHM_VERSION,)
        ).fetchall()
    return jsonify(_rt_build_calibration_report(
        rows, _RT_POOL, _RT_ANCHOR_VERSION
    ))


@app.route('/api/rating_test/start', methods=['POST'])
def rt_start():
    """建立新測驗 session，回傳第一題。"""
    _ensure_rt_pool()
    uid = session.get('user_id')
    body = request.get_json(silent=True) or {}
    trigger = str(body.get('trigger', 'manual')).strip()
    if trigger not in ('manual', 'placement'):
        trigger = 'manual'

    init_rating = 1500.0
    prior_sd = 400.0
    requested_init = body.get('init_elo')
    if requested_init is not None:
        try:
            init_rating = max(1100.0, min(2500.0, float(requested_init)))
            prior_sd = 280.0 if str(trigger).strip() == 'placement' else 240.0
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
                    init_rating = min(prev, 2500.0)
                else:
                    init_rating = max(1100.0, min(prev, 2000.0))
                prior_sd = 160.0

    sid = str(uuid.uuid4())
    # 排除最近 5 場／180 天內已出現的題目，防止跨場重複。
    recent_ids = _get_recent_seen_ids(uid)
    recent_ids.update(_rt_client_exclude_ids(body.get('exclude_question_ids')))
    anchor_enabled = _rt_anchor_available()
    first_role = _rt_desired_question_role(trigger, 0, anchor_enabled)
    first_q = _pick_question(
        init_rating, 0, recent_ids, question_role=first_role,
        anchor_enabled=anchor_enabled,
    )
    if not first_q and first_role == 'anchor':
        first_role = 'regular'
        first_q = _pick_question(
            init_rating, 0, recent_ids, question_role=first_role,
            anchor_enabled=anchor_enabled,
        )
    if not first_q:
        return jsonify({'error': 'no_questions'}), 503

    answers_init = []
    question_token = secrets.token_urlsafe(18)
    with get_db() as conn:
        conn.execute(
            'INSERT INTO rating_test_sessions '
            '(id,user_id,status,init_rating,cur_rating,prior_sd,rating_se,round,'
            ' current_question_id,current_question_token,current_question_role,'
            ' bank_version,algorithm_version,answers,trigger,started_at,last_activity_at) '
            'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (sid, uid, 'in_progress', init_rating, init_rating, prior_sd, prior_sd,
             0, first_q['id'], question_token, first_role,
             _RT_ANCHOR_VERSION if anchor_enabled else None,
             _RT_ALGORITHM_VERSION if anchor_enabled else _RT_BASE_ALGORITHM_VERSION,
             json.dumps(answers_init), trigger,
             datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat(),
             datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat())
        )
        conn.commit()

    is_placement = (str(trigger).strip() == 'placement')
    pl_rounds = _placement_rounds(init_rating)
    return jsonify({
        'session_id':   sid,
        'round':        1,
        'total_rounds': pl_rounds if is_placement else _RT_MAX_ROUNDS,
        'min_rounds':   pl_rounds if is_placement else _RT_MIN_ROUNDS,
        'question':     _strip_question(first_q, sid, question_token),
        'cur_rating':   init_rating,
        'rating_se':    prior_sd,
        'rank_label':   _rating_to_rank(init_rating),
        'provisional':  True,
        'pool_size':    len(_RT_POOL),
    })


@app.route('/api/rating_test/resume/<sid>')
def rt_resume(sid):
    """回復中斷或回應遺失的測驗；sid 為匿名測驗的 capability token。"""
    with get_db() as conn:
        row = conn.execute(
            'SELECT * FROM rating_test_sessions WHERE id=?', (sid,)
        ).fetchone()
    if not row:
        return jsonify({'error': 'not_found'}), 404
    request_uid = session.get('user_id')
    if row['user_id'] is not None and row['user_id'] != request_uid:
        return jsonify({'error': 'session_owner_mismatch'}), 403
    try:
        answers = json.loads(row['answers'] or '[]')
    except Exception:
        answers = []
    is_placement = str(row['trigger'] or '').strip() == 'placement'
    total_rounds = _placement_rounds(float(row['init_rating'] or 1500.0)) \
        if is_placement else _RT_MAX_ROUNDS
    payload = {
        'session_id': sid,
        'finished': row['status'] == 'completed',
        'round': int(row['round'] or 0),
        'total_rounds': total_rounds,
        'min_rounds': total_rounds if is_placement else _RT_MIN_ROUNDS,
        'cur_rating': float(row['cur_rating']),
        'rating_se': float(row['rating_se'] or row['prior_sd'] or 300.0),
        'rank_label': _rating_to_rank(float(row['cur_rating'])),
        'provisional': is_placement or row['status'] != 'completed' or
                       not _rt_converged(answers, float(row['init_rating']),
                                         float(row['prior_sd'] or 300.0)),
        'answers': [{
            'correct': bool(a.get('correct')),
            'discipline': a.get('discipline', ''),
            'q_rating': a.get('q_rating'),
        } for a in answers],
    }
    payload['rank_range'] = [
        _rating_to_rank(payload['cur_rating'] - payload['rating_se']),
        _rating_to_rank(payload['cur_rating'] + payload['rating_se']),
    ]
    if row['status'] == 'in_progress':
        _ensure_rt_pool()
        current_q = next((q for q in _RT_POOL
                          if q['id'] == row['current_question_id']), None)
        if not current_q or not row['current_question_token']:
            return jsonify({'error': 'session_state_invalid'}), 409
        payload['question'] = _strip_question(
            current_q, sid, row['current_question_token']
        )
    return jsonify(payload)


@app.route('/api/rating_test/answer', methods=['POST'])
def rt_answer():
    """接收目前題目的作答；題號、token、判定與 round 全由後端控制。"""
    body = request.get_json(silent=True) or {}
    sid = str(body.get('session_id') or '').strip()
    q_id = body.get('question_id')
    question_token = str(body.get('question_token') or '').strip()
    moves = body.get('moves')
    if not sid or q_id is None or not question_token:
        return jsonify({'error': 'missing_question_context'}), 400
    if not isinstance(moves, list):
        return jsonify({'error': 'moves_required'}), 400
    try:
        q_id = int(q_id)
    except (TypeError, ValueError):
        return jsonify({'error': 'invalid_question'}), 400

    _ensure_rt_pool()
    pool_q = next((q for q in _RT_POOL if q['id'] == q_id), None)
    if not pool_q:
        return jsonify({'error': 'question_not_found'}), 404

    try:
        server_correct = _rt_server_verify(pool_q, sid, moves)
    except Exception:
        app.logger.exception(f'[rt_verify] 重放驗證失敗 q={q_id}')
        return jsonify({'error': 'verification_failed'}), 422
    if server_correct is None:
        return jsonify({'error': 'question_unverifiable'}), 422
    correct = bool(server_correct)

    request_uid = session.get('user_id')
    now_iso = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat()
    response_ms = body.get('response_ms')
    try:
        response_ms = max(0, min(600000, int(response_ms))) if response_ms is not None else None
    except (TypeError, ValueError):
        response_ms = None

    start_zone_key = None
    with get_db() as conn:
        row = conn.execute(
            'SELECT * FROM rating_test_sessions WHERE id=? FOR UPDATE', (sid,)
        ).fetchone()
        if not row or row['status'] != 'in_progress':
            return jsonify({'error': 'invalid_session'}), 409
        if row['user_id'] is not None and row['user_id'] != request_uid:
            return jsonify({'error': 'session_owner_mismatch'}), 403
        if row['current_question_id'] != q_id or row['current_question_token'] != question_token:
            return jsonify({'error': 'stale_or_wrong_question'}), 409
        cur_rating = float(row['cur_rating'])
        prior_mean = float(row['init_rating'] or 1500.0)
        prior_sd = float(row['prior_sd'] or 300.0)
        round_idx = int(row['round'])
        try:
            answers = json.loads(row['answers'] or '[]')
        except Exception:
            answers = []
        if len(answers) != round_idx:
            return jsonify({'error': 'session_state_mismatch'}), 409

        try:
            import shadow_judging
            if shadow_judging.is_enabled():
                _t_sh = _rt_transform_idx(sid, pool_q['id'])
                shadow_judging.observe_rating_test(
                    question_id=q_id,
                    session_id=sid,
                    transform_idx=_t_sh,
                    sgf_transformed=_transform_sgf(pool_q['content'], _t_sh),
                    moves=moves if isinstance(moves, list) else None,
                    client_correct=bool(body.get('correct', False)),
                    final_correct=bool(correct),
                    katago_best_move=pool_q.get('katago_best_move') or '',
                )
        except Exception:
            app.logger.exception('[shadow] observe failed (ignored)')

        question_role = str(row['current_question_role'] or 'regular')
        session_bank_version = row['bank_version']
        algorithm_version = str(row['algorithm_version'] or _RT_BASE_ALGORITHM_VERSION)
        session_anchor_enabled = bool(
            session_bank_version and session_bank_version == _RT_ANCHOR_VERSION
            and _rt_anchor_available()
        )
        streak = _compute_streak(answers, correct)
        answer = {
            'q_id': q_id,
            'correct': correct,
            'discipline': pool_q['discipline'],
            'source': pool_q.get('source_group', ''),
            'q_rating': pool_q['rating'],
            'rating_before': cur_rating,
            'response_ms': response_ms,
            'streak': streak,
            'question_role': question_role,
            'bank_version': session_bank_version,
            'algorithm_version': algorithm_version,
        }
        estimate_input = answers + [answer]
        new_rating, rating_se = _rt_estimate(estimate_input, prior_mean, prior_sd)
        answer['rating_after'] = new_rating
        answers.append(answer)
        round_idx += 1

        is_placement = str(row['trigger'] or '').strip() == 'placement'
        total_rounds = _placement_rounds(prior_mean) if is_placement else _RT_MAX_ROUNDS
        converged = False if is_placement else _rt_converged(answers, prior_mean, prior_sd)
        finished = (round_idx >= total_rounds if is_placement else
                    round_idx >= _RT_MAX_ROUNDS or converged)

        recent_ids = _rt_recent_seen_ids(conn, row['user_id'], exclude_sid=sid)

        next_q = None
        next_token = None
        next_role = None
        if not finished:
            session_ids = {a['q_id'] for a in answers}
            disc_counts = {}
            source_counts = {}
            for a in answers:
                disc_counts[a.get('discipline', '')] = disc_counts.get(a.get('discipline', ''), 0) + 1
                source_counts[a.get('source', '')] = source_counts.get(a.get('source', ''), 0) + 1
            next_role = _rt_desired_question_role(
                row['trigger'], round_idx, session_anchor_enabled
            )
            next_q = _pick_question(
                new_rating, round_idx, session_ids | recent_ids,
                discipline_counts=disc_counts, source_counts=source_counts,
                question_role=next_role,
                anchor_enabled=session_anchor_enabled,
            )
            if not next_q and next_role == 'anchor':
                next_role = 'regular'
                next_q = _pick_question(
                    new_rating, round_idx, session_ids | recent_ids,
                    discipline_counts=disc_counts, source_counts=source_counts,
                    question_role=next_role,
                    anchor_enabled=session_anchor_enabled,
                )
            if next_q:
                next_token = secrets.token_urlsafe(18)
            else:
                finished = True

        status = 'completed' if finished else 'in_progress'
        conn.execute(
            'UPDATE rating_test_sessions SET status=?,cur_rating=?,rating_se=?,round=?,answers=?,'
            ' current_question_id=?,current_question_token=?,current_question_role=?,'
            ' finished_at=?,last_activity_at=? WHERE id=?',
            (status, new_rating, rating_se, round_idx, json.dumps(answers),
             None if finished else next_q['id'], None if finished else next_token,
             None if finished else next_role,
             now_iso if finished else None, now_iso, sid)
        )
        conn.execute(
            'INSERT INTO rating_test_responses '
            '(session_id,user_id,question_id,round,correct,response_ms,question_rating,'
            ' ability_before,ability_after,question_role,bank_version,algorithm_version,created_at) '
            'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (sid, row['user_id'], q_id, round_idx - 1, 1 if correct else 0,
             response_ms, pool_q['rating'], cur_rating, new_rating, question_role,
             session_bank_version, algorithm_version, now_iso)
        )

        if row['user_id']:
            mrow = conn.execute(
                'SELECT wrong_count FROM mistake_log WHERE user_id=? AND question_id=?',
                (row['user_id'], q_id)
            ).fetchone()
            if not correct:
                if mrow:
                    conn.execute(
                        'UPDATE mistake_log SET wrong_count=wrong_count+1, last_wrong_at=? '
                        'WHERE user_id=? AND question_id=?',
                        (now_iso, row['user_id'], q_id)
                    )
                else:
                    conn.execute(
                        'INSERT INTO mistake_log'
                        '(user_id,question_id,wrong_count,correct_after,first_wrong_at,last_wrong_at) '
                        'VALUES(?,?,1,0,?,?)',
                        (row['user_id'], q_id, now_iso, now_iso)
                    )
            elif mrow:
                conn.execute(
                    'UPDATE mistake_log SET correct_after=correct_after+1,last_correct_at=? '
                    'WHERE user_id=? AND question_id=?',
                    (now_iso, row['user_id'], q_id)
                )

        if finished and row['user_id']:
            provisional = 1 if is_placement or not converged else 0
            _finalize_placement(conn, row['user_id'], new_rating, provisional=provisional)
        conn.commit()
        owner_uid = row['user_id']

    if finished and owner_uid and is_placement:
        start_zone_key = _apply_placement_adventure_unlock(
            owner_uid, min(new_rating, 1570.0), 'placement_test'
        )

    rating_change = round(new_rating - cur_rating, 1)
    payload = {
        'correct':       correct,
        'best_move':     pool_q['katago_best_move'],
        'finished':      finished,
        'session_id':    sid,
        'cur_rating':    new_rating,
        'rating_se':     rating_se,
        'rating_change': rating_change,
        'streak':        streak,
        'rank_label':    _rating_to_rank(new_rating),
        'rank_range':    [_rating_to_rank(new_rating - rating_se),
                          _rating_to_rank(new_rating + rating_se)],
        'converged':     converged,
        'provisional':   is_placement or not converged,
        'rounds_used':   round_idx,
        'total_rounds':  total_rounds,
        'start_zone_key': start_zone_key,
    }
    if not finished:
        payload.update({
            'round': round_idx + 1,
            'question': _strip_question(next_q, sid, next_token),
        })
    return jsonify(payload)


@app.route('/api/rating_test/result/<sid>')
def rt_result(sid):
    """回傳完整測驗結果（雷達圖資料、學科分析、SP 統計）。"""
    with get_db() as conn:
        row = conn.execute(
            'SELECT * FROM rating_test_sessions WHERE id=?', (sid,)
        ).fetchone()
    if not row:
        return jsonify({'error': 'not_found'}), 404
    if row['status'] != 'completed':
        return jsonify({'error': 'not_completed'}), 409
    if row['user_id'] is not None and row['user_id'] != session.get('user_id'):
        return jsonify({'error': 'session_owner_mismatch'}), 403

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

    # ── 雷達圖：合併近 30 天日常答題記錄（單場每學科只有 1~2 題，統計上是雜訊；
    #    合併 review_log 後樣本變成數十~數百題，弱點分析才有意義）──
    hist_stats: dict[str, dict] = {}
    uid_row = row['user_id']
    if uid_row:
        try:
            qdisc = {q['id']: q.get('discipline', '') for q in _load_questions()}
            cutoff = (datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
                      - datetime.timedelta(days=30)).isoformat()
            with get_db() as conn:
                hrows = conn.execute(
                    'SELECT question_id, grade FROM review_log '
                    "WHERE user_id=? AND reviewed_at >= ? AND COALESCE(source,'') NOT LIKE 'rt:%%'",
                    (uid_row, cutoff)
                ).fetchall()
            for hr in hrows:
                disc = qdisc.get(hr['question_id'])
                if not disc:
                    continue
                st = hist_stats.setdefault(disc, {'correct': 0, 'total': 0})
                st['total'] += 1
                if hr['grade'] >= 2:
                    st['correct'] += 1
        except Exception:
            app.logger.exception('[rt_result] 合併歷史答題失敗，僅用本場數據')
            hist_stats = {}

    radar = {}
    all_discs = set(disc_stats) | set(hist_stats)
    for disc in all_discs:
        s = disc_stats.get(disc, {'correct': 0, 'total': 0})
        h = hist_stats.get(disc, {'correct': 0, 'total': 0})
        total = s['total'] + h['total']
        if total < 3:
            continue
        acc = (s['correct'] + h['correct']) / total
        # 題目水準：本場有題用本場平均難度；純歷史學科用玩家最終 rating 當代理
        if s['total']:
            avg_q_rating = sum(
                a['q_rating'] for a in answers if a.get('discipline') == disc
            ) / s['total']
        else:
            avg_q_rating = final_rating
        radar[disc] = round(max(0.0, min(100.0,
            acc * (avg_q_rating - 800) / (2200 - 800) * 100)), 1)

    # SP 統計（只計答對題）
    sp_by_disc: dict[str, int] = {}
    for a in answers:
        if a['correct']:
            sp_by_disc[a.get('discipline', '')] = \
                sp_by_disc.get(a.get('discipline', ''), 0) + 1

    # 最弱學科（合併歷史後答對率最低，且 < 100% 才算弱點；樣本 ≥3 才有資格）
    weakest = None
    combined = {}
    for disc in all_discs:
        s = disc_stats.get(disc, {'correct': 0, 'total': 0})
        h = hist_stats.get(disc, {'correct': 0, 'total': 0})
        t = s['total'] + h['total']
        if t >= 3:
            combined[disc] = (s['correct'] + h['correct']) / t
    if combined:
        candidate = min(combined, key=combined.get)
        if combined[candidate] < 1.0:
            weakest = candidate
    elif disc_stats:
        candidate = min(disc_stats, key=lambda d: (
            disc_stats[d]['correct'] / disc_stats[d]['total']
            if disc_stats[d]['total'] else 1.0
        ))
        rate = (disc_stats[candidate]['correct'] / disc_stats[candidate]['total']
                if disc_stats[candidate]['total'] else 1.0)
        if rate < 1.0:
            weakest = candidate

    prior_mean = float(row['init_rating'] or 1500.0)
    prior_sd = float(row['prior_sd'] or 300.0)
    se = float(row['rating_se'] or _rt_se(answers, prior_mean, prior_sd))
    converged = _rt_converged(answers, prior_mean, prior_sd)
    is_placement = str(row['trigger'] or '').strip() == 'placement'
    if is_placement:
        radar = {}
        weakest = None
    _rec_zone = _zone_by_key(_adventure_start_zone_for_elo(final_rating))
    return jsonify({
        'final_rating':  final_rating,
        'rank_label':    _rating_to_rank(final_rating),
        'rank_range':    [_rating_to_rank(final_rating - se),
                          _rating_to_rank(final_rating + se)],
        'converged':     converged,
        'provisional':   is_placement or not converged,
        'rating_se':     se,
        'rounds_used':   len(answers),
        'init_rating':   float(row['init_rating']),
        'answers':       answers,
        'disc_stats':    disc_stats,
        'hist_stats':    hist_stats,
        'radar':         radar,
        'sp_by_disc':    sp_by_disc,
        'weakest_disc':  weakest,
        'trigger':       row['trigger'],
        # 推薦修行起點預覽（純函式、不寫 DB；匿名試玩結果頁的鉤子，
        # 真正寫入帳號/解鎖仍在登入後的 claim_anon / placement_finish）
        'recommended_zone_key':   _rec_zone['key']   if _rec_zone else None,
        'recommended_zone':       _rec_zone['name']  if _rec_zone else None,
        'recommended_zone_icon':  _rec_zone['icon']  if _rec_zone else None,
        'recommended_zone_label': _rec_zone['label'] if _rec_zone else None,
        'recommended_stage':      _rec_zone['stage'] if _rec_zone else None,
        'recommended_zone_img':   (f"/assets/tiers/{_TIER_IMG[_rec_zone['key']]}.jpg"
                                   if _rec_zone and _rec_zone['key'] in _TIER_IMG else None),
    })


def _finalize_placement(conn, uid, rating, provisional=0):
    """測驗完成後把棋力落地到帳號（共用：rt_answer / placement_finish / claim_anon）。
    暫定結果只寫 elo_rating；正式收斂後才更新 go_rank。
    不在此 commit（由呼叫端負責）；冒險區解鎖由呼叫端 commit 後再 _apply_placement_adventure_unlock。
    provisional：快速定位或未收斂結果傳 1，正式收斂結果傳 0。"""
    now_iso = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat()
    conn.execute(
        'UPDATE users SET elo_rating=?,elo_updated_at=?,elo_provisional=? WHERE id=?',
        (rating, now_iso, provisional, uid)
    )
    if not provisional:
        _vrank = _rating_to_rank(rating).replace('+', '')
        conn.execute(
            'INSERT INTO user_stats(user_id, go_rank, go_rank_initialized) VALUES(?,?,1)'
            ' ON CONFLICT(user_id) DO UPDATE SET go_rank=?, go_rank_initialized=1',
            (uid, _vrank, _vrank)
        )
    conn.execute(
        'DELETE FROM daily_training_queue WHERE user_id=? AND date=?',
        (uid, datetime.date.today().isoformat())
    )


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
            'SELECT cur_rating,init_rating,prior_sd,rating_se,round,trigger,status,answers '
            'FROM rating_test_sessions WHERE id=? AND user_id=?',
            (sid, uid)
        ).fetchone()
        if not row:
            return jsonify({'error': 'not_found'}), 404

        if str(row['trigger'] or '').strip() != 'placement':
            return jsonify({'error': 'not_placement'}), 400
        if int(row['round'] or 0) < _placement_rounds(float(row['init_rating'] or 1500.0)):
            return jsonify({'error': 'not_enough_answers'}), 409
        cur_rating = float(row['cur_rating'])
        now_iso    = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat()

        # 標記 session completed（若尚未完成）
        if row['status'] != 'completed':
            conn.execute(
                'UPDATE rating_test_sessions SET status=?, finished_at=? WHERE id=?',
                ('completed', now_iso, sid)
            )
        conn.execute(
            'UPDATE rating_test_sessions SET cur_rating=? WHERE id=?',
            (cur_rating, sid)
        )

        # 寫入 users.elo_rating（強制覆蓋，placement 的結果優先）；解題完成 → 轉正
        _finalize_placement(conn, uid, cur_rating, provisional=1)
        conn.commit()
    start_zone_key = _apply_placement_adventure_unlock(
        uid, min(cur_rating, 1570.0), 'placement_test'
    )

    return jsonify({
        'ok':         True,
        'cur_rating': cur_rating,
        'rank_label': _rating_to_rank(cur_rating),
        'start_zone_key': start_zone_key,
    })


@app.route('/api/rating_test/claim_anon', methods=['POST'])
def rt_claim_anon():
    """把匿名試玩（/try）的鑑定結果認領到剛登入/註冊的帳號。
    只做：原子綁定 sid → uid，再落地 Elo/段位/清當日 queue/解鎖區（共用 _finalize_placement）。
    不碰 review_log / SP / XP（那是 claim_sp 的事）。Email 與 Google 兩條註冊路徑都會呼叫此端點。"""
    uid = session.get('user_id')
    if not uid:
        return jsonify({'error': 'login_required'}), 401
    sid = ((request.get_json(silent=True) or {}).get('session_id') or '').strip()
    if not sid:
        return jsonify({'error': 'no_session'}), 400

    with get_db() as conn:
        row = conn.execute(
            'SELECT user_id, status, cur_rating, finished_at '
            'FROM rating_test_sessions WHERE id=?', (sid,)
        ).fetchone()
        if not row:
            return jsonify({'error': 'not_found'}), 404
        if row['user_id'] is not None:
            return jsonify({'error': 'already_claimed'}), 409
        if row['status'] != 'completed':
            return jsonify({'error': 'not_completed'}), 400
        # 只認領近期（1 小時內完成）的匿名 session，避免撿到陳舊或被棄置的測驗
        try:
            fin = datetime.datetime.fromisoformat(row['finished_at'])
            now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
            if (now - fin) > datetime.timedelta(hours=1):
                return jsonify({'error': 'expired'}), 410
        except Exception:
            pass
        # 原子綁定：WHERE user_id IS NULL 防兩個帳號搶認領同一 sid 的競態
        bound = conn.execute(
            'UPDATE rating_test_sessions SET user_id=? WHERE id=? AND user_id IS NULL',
            (uid, sid)
        )
        if bound.rowcount != 1:
            return jsonify({'error': 'already_claimed'}), 409
        cur_rating = float(row['cur_rating'])
        # 快速定位只有 7 題 → 暫定棋力；玩家可日後跑完整鑑定轉正。
        _finalize_placement(conn, uid, cur_rating, provisional=1)
        conn.commit()
    start_zone_key = _apply_placement_adventure_unlock(
        uid, min(cur_rating, 1570.0), 'trial_claim'
    )
    return jsonify({
        'ok':             True,
        'cur_rating':     cur_rating,
        'rank_label':     _rating_to_rank(cur_rating),
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
        now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat()
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


def _env_flag_enabled(name, default=False):
    raw = os.environ.get(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if not normalized:
        return False
    return normalized in {'1', 'true', 'yes', 'on'}


def _env_flag_exact_true(name, default=False):
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() == 'true'


def _start_premium_weekly_scheduler():
    """Run the idempotent job hourly; generation itself is keyed by report week."""
    if not _env_flag_enabled('PREMIUM_WEEKLY_SCHEDULER_ENABLED'):
        return
    def worker():
        from premium_weekly_job import run_once
        while True:
            try:
                run_once(__import__(__name__))
            except Exception:
                app.logger.exception('[premium_weekly] scheduled job failed')
            time.sleep(3600)
    threading.Thread(target=worker, name='premium-weekly', daemon=True).start()


def _start_community_leaderboard_weekly_scheduler():
    """Run the weekly leaderboard reward job on a short bounded interval so
    Monday 00:10 Asia/Taipei executes promptly and later restarts catch up."""
    if not _env_flag_exact_true('COMMUNITY_LEADERBOARD_REWARDS_ENABLED'):
        return

    def worker():
        from community_leaderboard_rewards_scheduler import (
            SCHEDULER_WAKE_INTERVAL_SECONDS,
            run_community_leaderboard_weekly_cycle,
        )
        while True:
            try:
                run_community_leaderboard_weekly_cycle(__import__(__name__))
            except Exception:
                app.logger.exception('[community_leaderboard_weekly] scheduled job failed')
            time.sleep(SCHEDULER_WAKE_INTERVAL_SECONDS)

    threading.Thread(target=worker, name='community-leaderboard-weekly', daemon=True).start()


if __name__ == '__main__':
    init_db()
    _start_premium_weekly_scheduler()
    _start_community_leaderboard_weekly_scheduler()
    port = int(os.environ.get('PORT', '5000'))
    socketio.run(app, host='0.0.0.0', debug=False, port=port, allow_unsafe_werkzeug=True)
