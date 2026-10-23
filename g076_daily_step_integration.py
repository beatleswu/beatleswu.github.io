"""Daily-only atomic D5B adapter. No app import, registration or schema writes.
Caller owns transaction and rollback on EVERY exception, including commit failure.
Business effects extracted from dc_submit at 0b358cc7; no external observers.
"""
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from daily_challenge_d5b import reserve_daily_submission, persist_daily_result
from daily_challenge_authority import (issue_daily_attempt, judge_daily_answer,
    question_content_sha256, DailyAttemptError)
from g076_nonmap_steps import (resolve_daily, open_steps, submit_step,
    NonMapRejected, enabled as nonmap_enabled)
from g076_question_privacy import board_only_sgf
from g076_server_step_authority import _advance
from map_battle_runtime import _question_answer_tree, question_revision_for, MapBattleRuntimeError

@dataclass(frozen=True)
class DailyServices:
    DAILY_CHALLENGE_XP_REWARD: int
    xp_to_lv: object
    lv_progress: object
    check_and_award_daily: object
    get_daily_submit_streak: object
    give_daily_appearance: object
    BADGE_DEFS: object
    _i18n_badge_en: object
    _APPEAR_MAP: object

def enabled(environ):
    return nonmap_enabled(environ) and str(environ.get(
        'G076_DAILY_STEPS_ENABLED', '')).strip().lower() in ('1', 'true', 'on')


def select_daily_question(conn, day, *, load_questions):
    """Existing date-seeded Daily selection, on the caller's transaction.

    Reread the unique date winner after insertion; never replace an admin pick
    or choose an easier supported question to evade the preflight gate.
    """
    questions = load_questions()
    if not questions:
        raise NonMapRejected('daily_question_unavailable', 503)
    row = conn.execute('SELECT question_id FROM daily_challenge WHERE challenge_date=?',
                       (day,)).fetchone()
    if row is None:
        index = int(hashlib.md5(day.encode()).hexdigest(), 16) % len(questions)
        conn.execute('''INSERT INTO daily_challenge(challenge_date,question_id,set_by)
            VALUES(?,?,?) ON CONFLICT(challenge_date) DO NOTHING''',
            (day, questions[index]['id'], 'auto'))
        row = conn.execute('SELECT question_id FROM daily_challenge WHERE challenge_date=?',
                           (day,)).fetchone()
    matches = [q for q in questions if q.get('id') == row['question_id']]
    if len(matches) != 1:
        raise NonMapRejected('daily_question_identity_ambiguous_or_missing', 503)
    return matches[0]


def schema_preflight(conn):
    """Read-only capability check. Approved unique indexes are also required.

    Inserts use explicit conflict targets, so missing uniqueness fails before
    awards. Never run migrations or create replacement authority here.
    """
    for table, columns in (
        ('users', 'id'),
        ('review_log', 'user_id,submission_id,submission_payload_hash,source_context'),
        ('daily_challenge_log', 'user_id,challenge_date,question_id,correct,submitted_at'),
        ('user_stats', 'user_id,xp,rank_xp,rank_level,updated_at'),
        ('badges_earned', 'user_id,badge_id,earned_at,seen'),
        ('player_wardrobe', 'user_id,item_id,obtained_at,source'),
        ('g076_nonmap_sessions', 'id,user_id,flow,binding,step_index,history_json,state'),
        ('g076_nonmap_events', 'session_id,step_index,request_hash,response_json'),
    ):
        conn.execute('SELECT ' + columns + ' FROM ' + table + ' WHERE 1=0')

def preflight(ctx):
    """Check every reachable branch before accepting the first move."""
    q, a = ctx.question, ctx.attempt
    if (q.get('answer_policy') not in (None, '', 'g065-explicit-v1') or
            any(q.get(k) for k in ('accepted_moves', 'accepted_answers', 'katago_best_move'))):
        raise NonMapRejected('daily_step_policy_unsupported', 422)
    try:
        preview = board_only_sgf(q['content'])
        root = _question_answer_tree(q['content'])
        if (root.metadata.get('size', 19) != a['board_size'] or
                root.metadata.get('player_to_move', a['player_color']) != a['player_color']):
            raise ValueError('board_context_mismatch')
        pending, count = [(root, 0)], 0
        while pending:
            node, depth = pending.pop()
            children = list(node.children or ())
            if not children or depth >= 99:
                raise ValueError('missing_or_excessive_player_steps')
            seen = set()
            for child in children:
                count += 1
                if count > 10000:
                    raise ValueError('excessive_tree')
                m = child.move
                if not m or m.color != a['player_color'] or not m.coord or len(m.coord) != 2 or m.coord in seen:
                    raise ValueError('unsupported_player_branch')
                seen.add(m.coord)
                pair = tuple(ord(c) - 97 for c in m.coord)
                decision, next_node = _advance(q, root, node, a['player_color'], pair, a['board_size'])
                if decision.status == 'CONTINUE':
                    pending.append((next_node, depth + 1))
        return preview
    except (ValueError, AttributeError, KeyError, TypeError) as error:
        raise NonMapRejected('daily_step_preflight_unavailable', 422) from error

def lock_daily_user(conn, uid):
    raw = getattr(conn, '_conn', conn)
    suffix = '' if raw.__class__.__module__.startswith('sqlite3') else ' FOR UPDATE'
    if conn.execute('SELECT id FROM users WHERE id=?' + suffix, (uid,)).fetchone() is None:
        raise NonMapRejected('authentication_required', 401)

def settle_daily(conn, ctx, answer, judge, submission_id, *, services, now=None):
    """Same-connection canonical effects. A duplicate date rolls back reservation.
    No debit/refund exists in dc_submit. Any failure rolls back all effects.
    Providers MUST use conn and propagate errors, with no commits/external IO.
    """
    uid, today, question, attempt = ctx.uid, ctx.scope, ctx.question, ctx.attempt
    if (ctx.flow != 'daily' or type(uid) is not int or uid < 1 or
            attempt.get('user_id') != uid or attempt.get('challenge_date') != today or
            attempt.get('question_id') != question['id'] or
            attempt.get('question_revision') != question_revision_for(question) or
            attempt.get('content_sha256') != question_content_sha256(question)):
        raise NonMapRejected('daily_settlement_binding_mismatch', 403)
    canonical_judge = judge_daily_answer(question, attempt, answer)
    if (judge.result != canonical_judge.result or
            judge.authoritative_grade != canonical_judge.authoritative_grade):
        raise NonMapRejected('daily_settlement_judge_mismatch', 503)
    judge = canonical_judge
    server_correct = judge.result == 'CORRECT'
    now = now or datetime.now().isoformat()
    dc = {'question_id': question['id']}
    payload_hash = hashlib.sha256(json.dumps([
        'g076-daily-v1', uid, today, question['id'], attempt['question_revision'],
        attempt['content_sha256'], answer.payload,
    ], separators=(',', ':'), sort_keys=True).encode()).hexdigest()
    lock_daily_user(conn, uid)
    reservation = reserve_daily_submission(conn, user_id=uid,
        question_id=question['id'], question_revision=attempt['question_revision'],
        server_correct=server_correct, reviewed_at=now,
        submission_id=submission_id, payload_hash=payload_hash)
    if not reservation['inserted']:
        return {'submission_id': submission_id, 'xp_awarded': reservation['result']['xp_awarded']}
    inserted = conn.execute('''INSERT INTO daily_challenge_log
        (user_id,challenge_date,question_id,correct,submitted_at)
        VALUES(?,?,?,?,?) ON CONFLICT(user_id,challenge_date) DO NOTHING''',
        (uid, today, question['id'], int(server_correct), now))
    if inserted.rowcount != 1:
        raise NonMapRejected('already_submitted', 409)
    xp_awarded = services.DAILY_CHALLENGE_XP_REWARD if server_correct else 0
    if xp_awarded:
        row = conn.execute(
            'SELECT xp FROM user_stats WHERE user_id=?', (uid,)
        ).fetchone()
        total_xp = ((row['xp'] or 0) if row else 0) + xp_awarded
        new_rank_level = f'LV{services.xp_to_lv(total_xp)}'
        _, rank_xp, _ = services.lv_progress(total_xp)
        conn.execute(
            '''INSERT INTO user_stats(user_id,xp,rank_xp,rank_level,updated_at)
               VALUES(?,?,?,?,?)
               ON CONFLICT(user_id) DO UPDATE SET
                 xp=?, rank_xp=?, rank_level=?, updated_at=?''',
            (uid, total_xp, rank_xp, new_rank_level, now,
             total_xp, rank_xp, new_rank_level, now)
        )

    stats_row = conn.execute(
        'SELECT COUNT(*) as total, SUM(correct) as cnt '
        'FROM daily_challenge_log WHERE challenge_date=?',
        (today,)
    ).fetchone()
    total_p = stats_row['total'] or 0
    correct_p = stats_row['cnt'] or 0

    rank = None
    if server_correct:
        rank_row = conn.execute(
            'SELECT COUNT(*) as r FROM daily_challenge_log '
            'WHERE challenge_date=? AND correct=1 AND submitted_at<=?',
            (today, now)
        ).fetchone()
        rank = rank_row['r'] if rank_row else None

    new_badge_ids = services.check_and_award_daily(conn, uid, server_correct, today)
    streak = services.get_daily_submit_streak(uid, today, conn=conn)
    new_appear_ids = services.give_daily_appearance(conn, uid, streak)

    defs_map = {b['id']: b for b in services.BADGE_DEFS}
    new_badges = []
    for bid in new_badge_ids:
        if bid not in defs_map:
            continue
        badge = dict(defs_map[bid])
        badge_en = services._i18n_badge_en(bid)
        if badge_en:
            badge['name_en'], badge['desc_en'] = badge_en
        new_badges.append(badge)
    new_appear_items = [services._APPEAR_MAP[i] for i in new_appear_ids if i in services._APPEAR_MAP]

    result_payload = {
        'ok': True,
        'stats': {
            'total': total_p,
            'correct': correct_p,
            'accuracy': round(correct_p / (total_p or 1) * 100),
            'rank': rank,
        },
        'xp_awarded': xp_awarded,
        'new_badges': new_badges,
        'new_appearance_items': new_appear_items,
        'server_correct': server_correct,
        'reward_eligible': server_correct,
        'judge_reason': judge.reason_code,
    }
    persist_daily_result(
        conn,
        user_id=uid,
        submission_id=submission_id,
        result=result_payload,
    )

    return {'submission_id': submission_id, 'xp_awarded': xp_awarded}


def create_daily_blueprint(*, transaction, today_question, admit, services, secret,
                           environ, today=None, question_context=None):
    """Providers: today_question(conn,date), admit(uid,q), canonical context(q).
    transaction: SQLite BEGIN IMMEDIATE / PostgreSQL BEGIN, rollback on any
    exception, commit before returning. Must not use an auto-committing helper.
    No shared Practice route is registered. Independent synchronizer CSRF token.
    """
    from datetime import date
    import hmac
    import secrets
    from flask import Blueprint, jsonify, request, session
    bp = Blueprint('g076_daily_steps', __name__)
    today = today or (lambda: date.today().isoformat())

    @bp.after_request
    def no_store(response):
        response.headers['Cache-Control'] = 'private, no-store'
        return response

    def settle(conn, ctx, answer, judge, event_id):
        return settle_daily(conn, ctx, answer, judge, event_id, services=services)

    def dispatch(action):
        if not enabled(environ) or services is None or not callable(question_context):
            return jsonify(error='daily_steps_disabled_or_unconfigured'), 503
        uid = session.get('user_id')
        if type(uid) is not int or uid < 1:
            return jsonify(error='authentication_required'), 401
        if (request.headers.get('Sec-Fetch-Site') == 'cross-site' or
                (request.headers.get('Origin') and request.headers['Origin'] != request.host_url.rstrip('/'))):
            return jsonify(error='same_origin_required'), 403
        if action != 'today':
            expected = session.get('g076_daily_csrf')
            supplied = request.headers.get('X-G076-Daily-CSRF', '')
            if not expected or not supplied.isascii() or not hmac.compare_digest(expected, supplied):
                return jsonify(error='daily_csrf_required'), 403
        if request.content_length and request.content_length > 32768:
            return jsonify(error='daily_request_too_large'), 413
        data = {} if action == 'today' else request.get_json(silent=True)
        fields = {'flow', 'attempt_token'} | ({'step_index', 'step_nonce', 'move'} if action == 'step' else set())
        if action != 'today' and (not isinstance(data, dict) or set(data) != fields or
                data.get('flow') != 'daily' or not isinstance(data.get('attempt_token'), str) or
                not 1 <= len(data['attempt_token']) <= 8192):
            return jsonify(error='invalid_daily_step_fields'), 400
        try:
            with transaction() as conn:
                schema_preflight(conn)
                day = today()
                q = today_question(conn, day)
                if not q:
                    raise NonMapRejected('daily_question_unavailable', 503)
                if action == 'today':
                    try:
                        board_only_sgf(q.get('content'))
                    except (ValueError, TypeError) as error:
                        raise NonMapRejected('daily_step_preflight_unavailable', 422) from error
                    token = issue_daily_attempt(secret, user_id=uid, challenge_date=day,
                        question=q, question_context=question_context(q))
                else:
                    token = data['attempt_token']
                ctx = resolve_daily(secret, token, uid=uid, today=day, question=q, admit=admit)
                preview = preflight(ctx)
                if action == 'today':
                    log = conn.execute('SELECT correct FROM daily_challenge_log WHERE user_id=? AND challenge_date=?',
                                       (uid, day)).fetchone()
                    csrf = session.get('g076_daily_csrf') or secrets.token_urlsafe(32)
                    session['g076_daily_csrf'] = csrf
                    result = {'date': day, 'question_id': q['id'], 'content': preview,
                              'board_only': True, 'attempt_token': token,
                              'csrf_token': csrf, 'user_submitted': log is not None,
                              'user_correct': bool(log['correct']) if log else None,
                              'xp_reward': services.DAILY_CHALLENGE_XP_REWARD}
                elif action == 'start':
                    result = open_steps(conn, ctx, secret=secret, settle=settle)
                else:
                    result = submit_step(conn, ctx, {k: data[k] for k in ('step_index', 'step_nonce', 'move')},
                                         secret=secret, settle=settle)
            return jsonify(result)
        except (NonMapRejected, DailyAttemptError, MapBattleRuntimeError) as error:
            return jsonify(error=getattr(error, 'code', 'daily_step_unavailable')), int(getattr(error, 'status', 409))
        except Exception:
            return jsonify(error='daily_step_backend_unavailable'), 503

    bp.add_url_rule('/api/g076/daily/today', 'today', lambda: dispatch('today'))
    bp.add_url_rule('/api/g076/daily/steps/start', 'start', lambda: dispatch('start'), methods=['POST'])
    bp.add_url_rule('/api/g076/daily/steps', 'step', lambda: dispatch('step'), methods=['POST'])
    return bp
