"""
grimoire_api.py — 黑白星火：法典知識系統 API
注入到 app.py 的 Flask Blueprint

提供端點：
  GET  /api/zones                        # 所有星域列表（含我的進度）
  GET  /api/zones/<id>/grimoires         # 某星域的所有法典（含我的進度）
  GET  /api/grimoire/<id>/progress       # 我在某法典的進度
  GET  /api/grimoire/training/daily      # 舊法典推薦修煉套裝（10 題，5-3-2 法則）
  POST /api/training/answer              # 提交答題結果，更新純淨度
  GET  /api/training/contaminated        # 我的污染節點列表
  GET  /api/player/weakness-report       # 弱項分析報告
"""

import json, datetime, random
from flask import Blueprint, jsonify, request, session
from functools import wraps

# ── Blueprint 宣告 ──────────────────────────────────────────────
grimoire_bp = Blueprint('grimoire', __name__)

DATA_FILE   = 'questions.json'

# 學科 → 屬性對照（8 大學科精化版）
# 4 個 DB 屬性欄位不變；8 學科分流至最近似的屬性
DISC_TO_ATTR = {
    # ── 精銳 (attr_sharp) ──
    'tesuji':            'attr_sharp',   # 手筋
    'capture_escape':    'attr_sharp',   # 吃子逃跑（戰術性）
    'connection_cut':    'attr_sharp',   # 連接切斷（戰術性）
    # ── 計算 (attr_calc) ──
    'life_death':        'attr_calc',    # 死活
    'shape_weakness':    'attr_calc',    # 棋形弱點（局部計算）
    # ── 大局觀 (attr_vision) ──
    'opening_direction': 'attr_vision',  # 布局方向
    'whole_board':       'attr_vision',  # 大局觀（新增第 8 學科）
    # ── 精準 (attr_prec) ──
    'endgame_counting':  'attr_prec',    # 官子
    # ── 相容舊名（過渡期）──
    'opening':           'attr_vision',
    'endgame':           'attr_prec',
    'mix':               None,           # 全屬性 × 0.5
}

# ── 工具 ──────────────────────────────────────────────────────────

def get_ldb():
    from db import get_db as _get_db
    return _get_db()

def get_sdb():
    from db import get_db as _get_db
    return _get_db()

def login_required_bp(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'ok': False, 'error': 'Not logged in'}), 401
        return f(*args, **kwargs)
    return decorated

_questions_cache = None
def load_questions():
    global _questions_cache
    if _questions_cache is None:
        import os
        if not os.path.exists(DATA_FILE):
            return []
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            _questions_cache = json.load(f)
    return _questions_cache

def invalidate_questions_cache():
    global _questions_cache
    _questions_cache = None

# ── 純淨度計算 ─────────────────────────────────────────────────

def calc_node_purity(history: list, interval_days: int = 0) -> float:
    """
    history: [True/False, ...] 近 5 次作答記錄（最舊在前）
    連續答對 → 純淨度趨近 1.0；最近答錯 → 大幅下降
    """
    if not history:
        return 0.0
    weights = [0.1, 0.15, 0.2, 0.25, 0.3][-len(history):]
    weighted = sum(w * (1.0 if a else 0.0) for w, a in zip(weights, history))
    interval_bonus = min(1.5, 1.0 + (interval_days / 30.0))
    return min(1.0, weighted * interval_bonus)

def ensure_node_mastery_table(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS node_mastery (
        user_id         INTEGER NOT NULL,
        question_id     INTEGER NOT NULL,
        purity          REAL NOT NULL DEFAULT 0.0,
        attempt_count   INTEGER NOT NULL DEFAULT 0,
        last_5_history  TEXT NOT NULL DEFAULT '[]',
        last_correct_at TEXT,
        is_contaminated INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (user_id, question_id)
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS player_grimoire_progress (
        user_id         INTEGER NOT NULL,
        grimoire_id     INTEGER NOT NULL,
        rank            INTEGER NOT NULL DEFAULT 0,
        purity          REAL NOT NULL DEFAULT 0.0,
        total_attempts  INTEGER NOT NULL DEFAULT 0,
        correct_count   INTEGER NOT NULL DEFAULT 0,
        last_studied_at TEXT,
        PRIMARY KEY (user_id, grimoire_id)
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS daily_training_cache (
        user_id         INTEGER NOT NULL,
        date            TEXT NOT NULL,
        question_ids    TEXT NOT NULL,
        completed_ids   TEXT NOT NULL DEFAULT '[]',
        created_at      TEXT NOT NULL,
        PRIMARY KEY (user_id, date)
    )''')
    conn.commit()

# ── 每日推薦引擎 (5-3-2 法則) ─────────────────────────────────

def generate_daily_training(uid: int, total: int = 10) -> list[int]:
    """
    回傳推薦題目 ID 列表。
    5 (challenge) + 3 (weakness) + 2 (SRS review)
    """
    qs_all = load_questions()
    if not qs_all:
        return []

    today = datetime.date.today().isoformat()

    with get_sdb() as sdb:
        ensure_node_mastery_table(sdb)

        # 玩家屬性
        stats = sdb.execute(
            'SELECT attr_def AS attr_calc, attr_atk AS attr_sharp, '
            'attr_vis AS attr_vision, attr_prec, '
            'rank_level FROM user_stats WHERE user_id=?', (uid,)
        ).fetchone()

        # SRS 到期題目
        due_rows = sdb.execute(
            "SELECT question_id FROM srs_cards WHERE user_id=? AND due_date<=? ORDER BY due_date LIMIT 20",
            (uid, today)
        ).fetchall()
        due_ids = {r['question_id'] for r in due_rows}

        # 污染節點
        contaminated = sdb.execute(
            'SELECT question_id FROM node_mastery WHERE user_id=? AND is_contaminated=1',
            (uid,)
        ).fetchall()
        cont_ids = {r['question_id'] for r in contaminated}

        # 已作答題目（避免重推剛剛答過的）
        recent_cutoff = (datetime.date.today() - datetime.timedelta(days=3)).isoformat()
        answered = sdb.execute(
            "SELECT DISTINCT question_id FROM review_log WHERE user_id=? AND reviewed_at>=?",
            (uid, recent_cutoff)
        ).fetchall()
        recent_ids = {r['question_id'] for r in answered}

    # 玩家等級 (1-99)
    rank_lv = 1
    if stats and stats['rank_level']:
        rl = str(stats['rank_level'])
        if rl.startswith('LV'):
            try:
                rank_lv = int(rl[2:])
            except ValueError:
                pass

    # 弱項學科：四象限屬性最低者（職業體系已移除，純粹以屬性值判斷）
    weak_disc = 'life_death'  # 預設
    if stats:
        attr_map = {
            'tesuji':            stats['attr_sharp']  or 0,
            'life_death':        stats['attr_calc']   or 0,
            'opening_direction': stats['attr_vision'] or 0,
            'endgame_counting':  stats['attr_prec']   or 0,
        }
        weak_disc = min(attr_map, key=attr_map.get)

    class_bonus_disc = None   # 職業加成已移除

    # 難度目標：根據等級決定 (每 10 LV → difficulty +1)
    target_diff = max(1, min(10, (rank_lv // 10) + 1))

    # ── 建立候選集合 ────────────────────────────────────────────
    enabled_qs = [q for q in qs_all if q.get('enabled', True)]

    def pick_by_disc(disc: str, difficulty: int, exclude: set, limit: int) -> list:
        diff_min, diff_max = max(1, difficulty - 1), min(10, difficulty + 1)
        pool = [
            q for q in enabled_qs
            if q.get('discipline') == disc
            and diff_min <= (q.get('grimoire_difficulty') or 5) <= diff_max
            and q['id'] not in exclude
            and q['id'] not in recent_ids
        ]
        random.shuffle(pool)
        return [q['id'] for q in pool[:limit]]

    def pick_srs_review(due_ids: set, cont_ids: set, exclude: set, limit: int) -> list:
        # 優先污染節點，其次 SRS 到期
        combined = list((cont_ids | due_ids) - exclude - recent_ids)
        random.shuffle(combined)
        return combined[:limit]

    def pick_challenge(difficulty: int, exclude: set, limit: int) -> list:
        diff_min, diff_max = max(1, difficulty - 1), min(10, difficulty + 2)
        pool = [
            q for q in enabled_qs
            if diff_min <= (q.get('grimoire_difficulty') or 5) <= diff_max
            and q['id'] not in exclude
            and q['id'] not in recent_ids
        ]
        random.shuffle(pool)
        return [q['id'] for q in pool[:limit]]

    # 分配名額 (5-3-2)
    n_challenge = max(1, total * 5 // 10)
    n_weak      = max(1, total * 3 // 10)
    n_review    = total - n_challenge - n_weak

    used = set()

    review_ids    = pick_srs_review(due_ids, cont_ids, used, n_review)
    used.update(review_ids)

    # 弱項強化（優先職業加成學科，若沒有則選真弱項）
    target_disc = class_bonus_disc if class_bonus_disc else weak_disc
    weak_ids = pick_by_disc(target_disc, target_diff, used, n_weak)
    # 若不足，補其他學科
    if len(weak_ids) < n_weak:
        extra = pick_challenge(target_diff, used | set(weak_ids), n_weak - len(weak_ids))
        weak_ids += extra
    used.update(weak_ids)

    challenge_ids = pick_challenge(target_diff, used, n_challenge)
    used.update(challenge_ids)

    # 若總數不足，從全部隨機補
    all_picked = review_ids + weak_ids + challenge_ids
    if len(all_picked) < total:
        fallback = [
            q['id'] for q in enabled_qs
            if q['id'] not in used and q['id'] not in recent_ids
        ]
        random.shuffle(fallback)
        all_picked += fallback[:total - len(all_picked)]

    return all_picked[:total]


# ════════════════════════════════════════════════════════════════
# API 端點
# ════════════════════════════════════════════════════════════════

@grimoire_bp.route('/api/zones')
@login_required_bp
def api_zones():
    """所有星域列表，含每個星域的平均純淨度。"""
    uid = session['user_id']
    with get_ldb() as ldb:
        zones = ldb.execute('SELECT * FROM zones ORDER BY id').fetchall()

    with get_sdb() as sdb:
        ensure_node_mastery_table(sdb)

    result = []
    with get_ldb() as ldb:
        for z in zones:
            # 取該星域下所有法典的進度
            grimoires = ldb.execute(
                'SELECT id FROM grimoires WHERE zone_id=?', (z['id'],)
            ).fetchall()
            gids = [g['id'] for g in grimoires]

            zone_purity = 0.0
            if gids:
                with get_sdb() as sdb:
                    rows = sdb.execute(
                        f'SELECT AVG(purity) FROM player_grimoire_progress '
                        f'WHERE user_id=? AND grimoire_id IN ({",".join("?" * len(gids))})',
                        [uid] + gids
                    ).fetchone()
                zone_purity = rows[0] or 0.0

            result.append({
                'id':         z['id'],
                'name':       z['name'],
                'folder_path': z['folder_path'],
                'min_level':  z['min_level'],
                'grimoire_count': len(gids),
                'purity':     round(zone_purity, 4),
            })

    return jsonify({'ok': True, 'zones': result})


@grimoire_bp.route('/api/zones/<int:zone_id>/grimoires')
@login_required_bp
def api_zone_grimoires(zone_id: int):
    """某星域內的所有法典，含玩家個人進度。"""
    uid = session['user_id']
    with get_ldb() as ldb:
        zone = ldb.execute('SELECT * FROM zones WHERE id=?', (zone_id,)).fetchone()
        if not zone:
            return jsonify({'ok': False, 'error': 'Zone not found'}), 404
        grimoires = ldb.execute(
            'SELECT * FROM grimoires WHERE zone_id=? ORDER BY difficulty, name',
            (zone_id,)
        ).fetchall()

    gids = [g['id'] for g in grimoires]

    # 批次查詢玩家進度
    progress_map = {}
    if gids:
        with get_sdb() as sdb:
            ensure_node_mastery_table(sdb)
            rows = sdb.execute(
                f'SELECT * FROM player_grimoire_progress WHERE user_id=? '
                f'AND grimoire_id IN ({",".join("?" * len(gids))})',
                [uid] + gids
            ).fetchall()
            for r in rows:
                progress_map[r['grimoire_id']] = dict(r)

    out = []
    for g in grimoires:
        prog = progress_map.get(g['id'], {})
        out.append({
            'id':          g['id'],
            'name':        g['name'],
            'folder_path': g['folder_path'],
            'discipline':  g['discipline'],
            'difficulty':  g['difficulty'],
            'node_count':  g['node_count'],
            'rank':        prog.get('rank', 0),
            'purity':      round(prog.get('purity', 0.0), 4),
            'total_attempts': prog.get('total_attempts', 0),
            'correct_count':  prog.get('correct_count', 0),
            'last_studied_at': prog.get('last_studied_at'),
        })

    return jsonify({'ok': True, 'zone': dict(zone), 'grimoires': out})


@grimoire_bp.route('/api/grimoire/<int:grimoire_id>/progress')
@login_required_bp
def api_grimoire_progress(grimoire_id: int):
    """玩家在某法典的詳細進度。"""
    uid = session['user_id']
    with get_ldb() as ldb:
        g = ldb.execute('SELECT * FROM grimoires WHERE id=?', (grimoire_id,)).fetchone()
        if not g:
            return jsonify({'ok': False, 'error': 'Grimoire not found'}), 404

    with get_sdb() as sdb:
        ensure_node_mastery_table(sdb)
        prog = sdb.execute(
            'SELECT * FROM player_grimoire_progress WHERE user_id=? AND grimoire_id=?',
            (uid, grimoire_id)
        ).fetchone()

    prog_dict = dict(prog) if prog else {
        'rank': 0, 'purity': 0.0, 'total_attempts': 0,
        'correct_count': 0, 'last_studied_at': None
    }

    # 計算下一個精煉階段所需進度
    rank = prog_dict['rank']
    rank_thresholds = {0: 0.3, 1: 0.6, 2: 0.8, 3: 1.0}
    next_threshold = rank_thresholds.get(rank, 1.0)

    return jsonify({
        'ok': True,
        'grimoire': dict(g),
        'progress': {
            **prog_dict,
            'purity': round(prog_dict['purity'], 4),
            'next_rank_threshold': next_threshold,
        }
    })


@grimoire_bp.route('/api/grimoire/training/daily')
@login_required_bp
def api_training_daily():
    """
    取得今日推薦修煉套裝（10 題）。
    使用快取：同一天同一玩家不重新計算。
    """
    uid = session['user_id']
    today = datetime.date.today().isoformat()

    with get_sdb() as sdb:
        ensure_node_mastery_table(sdb)
        cache = sdb.execute(
            'SELECT question_ids, completed_ids FROM daily_training_cache WHERE user_id=? AND date=?',
            (uid, today)
        ).fetchone()

    if cache:
        qids      = json.loads(cache['question_ids'])
        done_ids  = set(json.loads(cache['completed_ids']))
    else:
        qids = generate_daily_training(uid, total=10)
        done_ids = set()
        with get_sdb() as sdb:
            sdb.execute(
                'INSERT INTO daily_training_cache(user_id,date,question_ids,completed_ids,created_at) '
                'VALUES(?,?,?,?,?) '
                'ON CONFLICT (user_id, date) DO UPDATE SET '
                'question_ids = EXCLUDED.question_ids, completed_ids = EXCLUDED.completed_ids, created_at = EXCLUDED.created_at',
                (uid, today, json.dumps(qids), '[]', datetime.datetime.now().isoformat())
            )
            sdb.commit()

    # 附上題目資訊
    qs_map = {q['id']: q for q in load_questions()}
    result = []
    for qid in qids:
        q = qs_map.get(qid)
        if not q:
            continue
        result.append({
            'id':         q['id'],
            'topic_en':   q.get('topic_en', ''),
            'level_en':   q.get('level_en', ''),
            'display_name': q.get('display_name', ''),
            'discipline': q.get('discipline'),
            'grimoire_difficulty': q.get('grimoire_difficulty'),
            'grimoire_id': q.get('grimoire_id'),
            'content':    q.get('content', ''),
            'completed':  qid in done_ids,
        })

    return jsonify({
        'ok': True,
        'date': today,
        'questions': result,
        'total': len(result),
        'completed': len(done_ids),
    })


@grimoire_bp.route('/api/training/answer', methods=['POST'])
@login_required_bp
def api_training_answer():
    """
    提交答題結果，更新節點純淨度、法典純淨度、每日快取。

    Request JSON:
        questionId  : int
        correct     : bool
        timeSec     : float (可選)
    """
    uid = session['user_id']
    data = request.get_json() or {}
    qid       = data.get('questionId')
    is_correct = bool(data.get('correct', False))
    time_sec  = float(data.get('timeSec', 0))

    if not qid:
        return jsonify({'ok': False, 'error': 'Missing questionId'}), 400

    qs_map = {q['id']: q for q in load_questions()}
    q_info = qs_map.get(qid)
    if not q_info:
        return jsonify({'ok': False, 'error': 'Question not found'}), 404

    grimoire_id = q_info.get('grimoire_id')
    discipline  = q_info.get('discipline')
    now = datetime.datetime.now().isoformat()
    today = datetime.date.today().isoformat()

    with get_sdb() as sdb:
        ensure_node_mastery_table(sdb)

        # ── 1. 更新節點熟練度 ─────────────────────────────────
        mastery = sdb.execute(
            'SELECT * FROM node_mastery WHERE user_id=? AND question_id=?', (uid, qid)
        ).fetchone()

        if mastery:
            history = json.loads(mastery['last_5_history'])
            attempt_count = mastery['attempt_count'] + 1
        else:
            history = []
            attempt_count = 1

        history.append(is_correct)
        history = history[-5:]  # 只保留最近 5 次
        new_purity = calc_node_purity(history)
        is_contaminated = (not is_correct) and new_purity < 0.3

        sdb.execute('''
            INSERT INTO node_mastery(user_id, question_id, purity, attempt_count,
                                     last_5_history, last_correct_at, is_contaminated)
            VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(user_id, question_id) DO UPDATE SET
                purity=excluded.purity,
                attempt_count=excluded.attempt_count,
                last_5_history=excluded.last_5_history,
                last_correct_at=CASE WHEN excluded.last_correct_at IS NOT NULL THEN excluded.last_correct_at ELSE node_mastery.last_correct_at END,
                is_contaminated=excluded.is_contaminated
        ''', (uid, qid, new_purity, attempt_count,
              json.dumps(history),
              now if is_correct else None,
              1 if is_contaminated else 0))

        # ── 2. 更新法典純淨度 ─────────────────────────────────
        grimoire_purity_new = None
        grimoire_rank_new   = None
        if grimoire_id:
            # 取法典內所有已作答節點的純淨度均值
            # （只計算 attempt_count > 0 的，未作答節點視為 0）
            with get_ldb() as ldb:
                total_nodes = ldb.execute(
                    'SELECT node_count FROM grimoires WHERE id=?', (grimoire_id,)
                ).fetchone()
            total_n = total_nodes['node_count'] if total_nodes else 1
            if total_n < 1:
                total_n = 1

            answered_rows = sdb.execute(
                'SELECT purity FROM node_mastery WHERE user_id=? AND question_id IN '
                '(SELECT id FROM (SELECT DISTINCT id FROM json_each(?) LIMIT 0))',  # placeholder
                (uid, '[]')
            ).fetchall()  # 這查法太複雜，改用分批計算

            # 取所有屬於此法典的已作答題目的純淨度
            # 透過 questions.json 中的 grimoire_id 欄位
            grim_qids = [q['id'] for q in load_questions() if q.get('grimoire_id') == grimoire_id]
            if grim_qids:
                placeholders = ','.join('?' * len(grim_qids))
                answered_rows = sdb.execute(
                    f'SELECT purity FROM node_mastery WHERE user_id=? AND question_id IN ({placeholders})',
                    [uid] + grim_qids
                ).fetchall()
                answered_purity_sum = sum(r['purity'] for r in answered_rows)
                grimoire_purity_new = answered_purity_sum / total_n

            # 更新 player_grimoire_progress
            prog = sdb.execute(
                'SELECT * FROM player_grimoire_progress WHERE user_id=? AND grimoire_id=?',
                (uid, grimoire_id)
            ).fetchone()

            total_attempts = (prog['total_attempts'] if prog else 0) + 1
            correct_count  = (prog['correct_count']  if prog else 0) + (1 if is_correct else 0)
            current_rank   = prog['rank'] if prog else 0

            # 精煉升階邏輯
            if grimoire_purity_new is not None:
                if current_rank == 0 and grimoire_purity_new >= 0.3:
                    grimoire_rank_new = 1
                elif current_rank == 1 and grimoire_purity_new >= 0.6:
                    grimoire_rank_new = 2
                elif current_rank == 2 and grimoire_purity_new >= 0.8:
                    grimoire_rank_new = 3
                elif current_rank == 3 and grimoire_purity_new >= 1.0:
                    grimoire_rank_new = 4
                else:
                    grimoire_rank_new = current_rank

            sdb.execute('''
                INSERT INTO player_grimoire_progress
                    (user_id, grimoire_id, rank, purity, total_attempts, correct_count, last_studied_at)
                VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(user_id, grimoire_id) DO UPDATE SET
                    rank=excluded.rank,
                    purity=excluded.purity,
                    total_attempts=excluded.total_attempts,
                    correct_count=excluded.correct_count,
                    last_studied_at=excluded.last_studied_at
            ''', (uid, grimoire_id,
                  grimoire_rank_new if grimoire_rank_new is not None else current_rank,
                  grimoire_purity_new if grimoire_purity_new is not None else 0.0,
                  total_attempts, correct_count, now))

        # ── 3. 標記每日快取中的已完成 ──────────────────────────
        cache = sdb.execute(
            'SELECT question_ids, completed_ids FROM daily_training_cache WHERE user_id=? AND date=?',
            (uid, today)
        ).fetchone()
        if cache:
            qids_list = json.loads(cache['question_ids'])
            done_list = json.loads(cache['completed_ids'])
            if qid in qids_list and qid not in done_list:
                done_list.append(qid)
                sdb.execute(
                    'UPDATE daily_training_cache SET completed_ids=? WHERE user_id=? AND date=?',
                    (json.dumps(done_list), uid, today)
                )

        sdb.commit()

    return jsonify({
        'ok':            True,
        'node_purity':   round(new_purity, 4),
        'contaminated':  is_contaminated,
        'grimoire_purity': round(grimoire_purity_new, 4) if grimoire_purity_new is not None else None,
        'grimoire_rank': grimoire_rank_new,
        'rank_up':       grimoire_rank_new is not None and prog is not None and grimoire_rank_new > (prog['rank'] if prog else 0),
    })


@grimoire_bp.route('/api/training/contaminated')
@login_required_bp
def api_training_contaminated():
    """取得玩家的污染節點列表（虛空迴廊）。"""
    uid = session['user_id']
    with get_sdb() as sdb:
        ensure_node_mastery_table(sdb)
        rows = sdb.execute(
            'SELECT question_id, purity, attempt_count, last_correct_at '
            'FROM node_mastery WHERE user_id=? AND is_contaminated=1 '
            'ORDER BY purity ASC LIMIT 50',
            (uid,)
        ).fetchall()

    qs_map = {q['id']: q for q in load_questions()}
    result = []
    for r in rows:
        q = qs_map.get(r['question_id'])
        if not q:
            continue
        result.append({
            'id':            r['question_id'],
            'purity':        round(r['purity'], 4),
            'attempt_count': r['attempt_count'],
            'last_correct_at': r['last_correct_at'],
            'topic_en':      q.get('topic_en', ''),
            'level_en':      q.get('level_en', ''),
            'discipline':    q.get('discipline'),
            'grimoire_id':   q.get('grimoire_id'),
            'content':       q.get('content', ''),
        })

    return jsonify({'ok': True, 'contaminated': result, 'total': len(result)})


@grimoire_bp.route('/api/player/weakness-report')
@login_required_bp
def api_weakness_report():
    """玩家四維弱項分析報告。"""
    uid = session['user_id']
    with get_sdb() as sdb:
        stats = sdb.execute(
            'SELECT attr_def AS attr_calc, attr_atk AS attr_sharp, '
            'attr_vis AS attr_vision, attr_prec '
            'FROM user_stats WHERE user_id=?', (uid,)
        ).fetchone()

        # 最近 30 天各學科答題正確率
        recent_30_cutoff = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
        disc_stats = sdb.execute(
            '''SELECT rl.topic, rl.level,
                      COUNT(*) as total,
                      SUM(CASE WHEN rl.grade >= 3 THEN 1 ELSE 0 END) as correct
               FROM review_log rl
               WHERE rl.user_id=? AND rl.reviewed_at >= ?
               GROUP BY rl.topic, rl.level''',
            (uid, recent_30_cutoff)
        ).fetchall()

    # 按學科彙整（利用 questions.json 的 discipline 欄位）
    qs_all = load_questions()
    topic_to_disc = {}
    for q in qs_all:
        key = (q.get('topic', ''), q.get('level', ''))
        if q.get('discipline') and key not in topic_to_disc:
            topic_to_disc[key] = q['discipline']

    # 用 defaultdict 接收全部 8 學科，不再因新學科 KeyError
    from collections import defaultdict
    disc_correct = defaultdict(int)
    disc_total   = defaultdict(int)

    for row in disc_stats:
        disc = topic_to_disc.get((row['topic'], row['level']), 'mix')
        disc_correct[disc] += row['correct']
        disc_total[disc]   += row['total']

    # 8 學科 → 4 屬性彙整（與 DISC_TO_ATTR 保持一致）
    _ATTR_CORRECT = defaultdict(int)
    _ATTR_TOTAL   = defaultdict(int)
    for disc, correct in disc_correct.items():
        attr = DISC_TO_ATTR.get(disc)
        if attr:
            _ATTR_CORRECT[attr] += correct
            _ATTR_TOTAL[attr]   += disc_total[disc]

    # 前端 API 仍以 4 個「代表學科名稱」回傳正確率
    _ATTR_TO_DISC = {
        'attr_sharp':  'tesuji',
        'attr_calc':   'life_death',
        'attr_vision': 'opening_direction',
        'attr_prec':   'endgame_counting',
    }
    disc_acc = {
        disc_name: (
            round(_ATTR_CORRECT[attr] / _ATTR_TOTAL[attr], 4)
            if _ATTR_TOTAL[attr] > 0 else None
        )
        for attr, disc_name in _ATTR_TO_DISC.items()
    }

    attrs = {}
    if stats:
        attrs = {
            'tesuji':            stats['attr_sharp']  or 0,
            'life_death':        stats['attr_calc']   or 0,
            'opening_direction': stats['attr_vision'] or 0,
            'endgame_counting':  stats['attr_prec']   or 0,
        }

    weakest = min(attrs, key=attrs.get) if attrs else 'life_death'

    _DISC_ZH = {
        'tesuji':            '手筋',
        'life_death':        '死活',
        'opening_direction': '布局',
        'endgame_counting':  '官子',
    }

    return jsonify({
        'ok': True,
        'attrs': attrs,
        'recent_accuracy': disc_acc,
        'weakest_discipline': weakest,
        'job_class': None,
        'recommendation': f'建議多練習「{_DISC_ZH.get(weakest, weakest)}」相關法典',
    })


@grimoire_bp.route('/api/grimoire/flux/today')
@login_required_bp
def api_grimoire_flux():
    """今日波動法典（每天 2 本，經驗值 ×1.5）。"""
    today = datetime.date.today().isoformat()
    # 用日期作為隨機種子，確保同一天所有玩家看到相同波動法典
    rng = random.Random(today)

    with get_ldb() as ldb:
        all_grimoires = ldb.execute('SELECT id, name, discipline, difficulty FROM grimoires').fetchall()

    if not all_grimoires:
        return jsonify({'ok': True, 'flux_grimoires': []})

    flux = rng.sample(list(all_grimoires), min(2, len(all_grimoires)))
    return jsonify({
        'ok': True,
        'date': today,
        'flux_grimoires': [
            {'id': g['id'], 'name': g['name'],
             'discipline': g['discipline'], 'difficulty': g['difficulty'],
             'bonus': 1.5}
            for g in flux
        ]
    })
