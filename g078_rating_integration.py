"""Canonical Rating adapter; caller-owned transactions, no schema creation.

The runtime mapping is app.py's real namespace, never a replacement corpus or
account provider. OFF does not acquire a database connection.
"""
from contextlib import contextmanager
import datetime
import json
import secrets
import uuid

from g076_rating_steps import RatingContext, RatingRejected, create_rating_blueprint, mode


class RatingAppServices:
    def __init__(self, runtime):
        self.runtime = runtime

    @contextmanager
    def transaction(self):
        r = self.runtime
        r['_ensure_rt_pool']()  # corpus I/O precedes the transaction
        conn = r['get_db']()
        try:
            conn.execute('BEGIN')
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def ready(self):
        # Read-only admission; the application must never install ledger DDL.
        try:
            with self.transaction() as conn:
                conn.execute('SELECT id,session_id,binding,context_key,state_json '
                             'FROM g076_rating_attempts LIMIT 0')
                conn.execute('SELECT attempt_id,nonce,request_hash,response_json '
                             'FROM g076_rating_events LIMIT 0')
            return True
        except Exception:
            return False

    def _user_lock(self, conn, uid):
        if uid is None:
            return None  # original anonymous sid capability
        if type(uid) is not int or uid <= 0:
            raise RatingRejected('rating_invalid_identity', 401)
        # Stable order: account before session, including concurrent sessions.
        row = conn.execute('SELECT id,elo_rating FROM users WHERE id=? FOR UPDATE', (uid,)).fetchone()
        if row is None:
            raise RatingRejected('authentication_required', 401)
        return row

    def resolve(self, conn, sid, uid):
        r = self.runtime
        self._user_lock(conn, uid)
        row = conn.execute('SELECT * FROM rating_test_sessions WHERE id=? FOR UPDATE', (sid,)).fetchone()
        if row is None:
            raise RatingRejected('not_found', 404)
        if row['user_id'] is not None and row['user_id'] != uid:
            raise RatingRejected('session_owner_mismatch', 403)
        answers = json.loads(row['answers'] or '[]')
        if len(answers) != int(row['round']):
            raise RatingRejected('session_state_mismatch')
        placement = str(row['trigger'] or '').strip() == 'placement'
        prior, sd = float(row['init_rating']), float(row['prior_sd'] or 300.)
        rating, se = float(row['cur_rating']), float(row['rating_se'] or sd)
        rounds = r['_placement_rounds'](prior) if placement else r['_RT_MAX_ROUNDS']
        summary = dict(session_id=sid, finished=row['status'] == 'completed',
            round=int(row['round']), total_rounds=rounds,
            min_rounds=rounds if placement else r['_RT_MIN_ROUNDS'],
            cur_rating=rating, rating_se=se, rank_label=r['_rating_to_rank'](rating),
            provisional=placement or row['status'] != 'completed' or not r['_rt_converged'](answers, prior, sd),
            answers=[{k: a.get(k) for k in ('correct', 'discipline', 'q_rating')} for a in answers],
            rank_range=[r['_rating_to_rank'](rating-se), r['_rating_to_rank'](rating+se)])
        q = next((q for q in r['_RT_POOL'] if q['id'] == row['current_question_id']), None)
        if not summary['finished'] and (q is None or not row['current_question_token']):
            raise RatingRejected('session_state_invalid')
        return RatingContext(sid, row['user_id'], row['current_question_token'],
            dict(q) if q else None, r['_rt_transform_idx'](sid, q['id']) if q else 0, summary)

    def start(self, conn, uid, trigger):
        r = self.runtime
        account = self._user_lock(conn, uid)
        rating, sd = 1500., 400.
        if account and account['elo_rating']:
            prev = float(account['elo_rating'])
            rating = min(prev, 2500.) if prev >= 1800 else max(1100., min(prev, 2000.))
            sd = 160.
        recent = r['_rt_recent_seen_ids'](conn, uid)
        anchor = r['_rt_anchor_available']()
        role = r['_rt_desired_question_role'](trigger, 0, anchor)
        q = r['_pick_question'](rating, 0, recent, question_role=role, anchor_enabled=anchor)
        if not q and role == 'anchor':
            role = 'regular'
            q = r['_pick_question'](rating, 0, recent, question_role=role, anchor_enabled=anchor)
        if not q:
            raise RatingRejected('no_questions', 503)
        sid, token = str(uuid.uuid4()), secrets.token_urlsafe(18)
        now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat()
        conn.execute('INSERT INTO rating_test_sessions '
            '(id,user_id,status,init_rating,cur_rating,prior_sd,rating_se,round,'
            'current_question_id,current_question_token,current_question_role,'
            'bank_version,algorithm_version,answers,trigger,started_at,last_activity_at) '
            'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (sid, uid, 'in_progress', rating, rating, sd, sd, 0, q['id'], token, role,
             r['_RT_ANCHOR_VERSION'] if anchor else None,
             r['_RT_ALGORITHM_VERSION'] if anchor else r['_RT_BASE_ALGORITHM_VERSION'],
             '[]', trigger, now, now))
        return self.resolve(conn, sid, uid)

    def settle(self, conn, ctx, moves, response_ms):
        r = self.runtime
        q = next((q for q in r['_RT_POOL'] if q['id'] == ctx.question['id']), None)
        if q is None or dict(q) != dict(ctx.question):
            raise RatingRejected('rating_question_revision_changed')
        correct = r['_rt_server_verify'](q, ctx.session_id, moves)
        if correct is None:
            raise RatingRejected('question_unverifiable', 422)
        return r['_rt_write_step_result'](conn, sid=ctx.session_id, request_uid=ctx.user_id,
            pool_q=q, question_token=ctx.question_token, response_ms=response_ms, correct=bool(correct))

    def settle_forfeit(self, conn, ctx, moves, response_ms, reason):
        return self.runtime['_rt_forfeit_on_connection'](conn, ctx, moves, response_ms, reason)


def install(app, runtime, environ):
    from flask import jsonify, request
    services = RatingAppServices(runtime)
    app.register_blueprint(create_rating_blueprint(services, environ))

    @app.before_request
    def guard_legacy_rating():
        current = mode(environ)
        if request.path.startswith('/api/rating_test/') and current != 'legacy':
            # These two audited GETs expose summary/count metadata only. The
            # existing result handler enforces completed state and ownership.
            if current == 'steps' and request.method == 'GET' and request.endpoint in ('rt_result', 'rt_pool_info'):
                return None
            response = jsonify(error='rating_steps_required', mode='hold')
            response.headers['Cache-Control'] = 'no-store'
            return response, 503

    @app.after_request
    def private_rating_metadata(response):
        if mode(environ) != 'legacy' and request.path.startswith('/api/rating_test/'):
            response.headers['Cache-Control'] = 'no-store'
            response.vary.add('Cookie')
        return response

    return services
