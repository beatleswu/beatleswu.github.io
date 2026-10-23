"""Practice product admission and transaction adapters. No runtime DDL."""
from contextlib import contextmanager
import datetime
import hashlib

from flask import jsonify, request, session
from g076_nonmap_steps import (
    enabled, resolve_practice, create_blueprint, NonMapRejected, _validate,
)
from practice_answer_authority import issue_practice_attempt, PracticeAttemptError
from review_service import PracticeReviewService


def selected(environ):
    return enabled(environ) and str(environ.get(
        'G076_PRACTICE_STEPS_ENABLED', '')).lower().strip() in ('1', 'true', 'on')


def _slot_day():
    return datetime.date.today().isoformat()


def install(app, runtime, environ):
    """runtime is app.py's late-bound namespace, preserving existing authorities."""
    @contextmanager
    def transaction():
        conn = runtime['get_db']()
        try:
            raw = getattr(conn, '_conn', conn)
            conn.execute('BEGIN IMMEDIATE' if raw.__class__.__module__.startswith('sqlite3') else 'BEGIN')
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def admit(conn, uid, question):
        if not runtime['_practice_premium_in_transaction'](conn, uid) and not runtime['question_is_free'](question):
            raise NonMapRejected('premium_required', 403)

    def resolve(conn, uid, flow, token):
        if flow != 'practice' or not selected(environ):
            raise NonMapRejected('practice_steps_disabled', 503)
        if not conn.execute('SELECT id FROM users WHERE id=?', (uid,)).fetchone():
            raise NonMapRejected('authentication_required', 401)
        ctx = resolve_practice(app.secret_key, token, uid=uid,
            question_loader=runtime['_practice_question_by_id'],
            identity=lambda qid: runtime['_practice_identity_for_write'](conn, qid),
            admit=lambda uid, question: admit(conn, uid, question))
        # Only the bounded product-issued attempt is valid. Old signed tokens
        # cannot create parallel cursors or reset an incorrect result.
        row = conn.execute('''SELECT attempt_token FROM g076_practice_attempts
            WHERE user_id=? AND question_id=? AND slot_date=?''',
                           (uid, ctx.question['id'], _slot_day())).fetchone()
        if not row or row['attempt_token'] != token:
            raise NonMapRejected('practice_attempt_superseded')
        return ctx

    service = PracticeReviewService(lambda conn, **kw: runtime['_persist_practice_review'](conn, **kw))

    def settle(conn, ctx, canonical, outcome, event_id):
        result = service.review(conn, uid=ctx.uid, question=ctx.question,
            attempt=ctx.attempt, canonical=canonical, judge=outcome)
        if result['submission_id'] != event_id or not result.get('srs'):
            raise NonMapRejected('practice_prior_settlement_requires_reconciliation', 503)
        return {'submission_id': event_id, 'srs': result['srs'], 'xp_awarded': 0}

    bp = create_blueprint(transaction=transaction, resolve=resolve, settle=settle,
                          secret=app.secret_key, environ=environ)
    app.register_blueprint(bp)

    @app.get('/api/g076/practice/steps/capability')
    def capability():
        from g076_question_privacy import privacy_enforced
        return jsonify(protocol='g076-practice-steps-v1', enabled=selected(environ),
                       privacy_enforced=privacy_enforced(environ))

    @app.get('/api/g076/practice/progress')
    def progress():
        if not selected(environ):
            return jsonify(error='practice_steps_disabled'), 503
        uid = session.get('user_id')
        if type(uid) is not int or uid < 1:
            return jsonify(error='authentication_required'), 401
        try:
            with transaction() as conn:
                row = conn.execute('''SELECT COUNT(*) AS total,
                    COALESCE(SUM(CASE WHEN grade>=3 THEN 1 ELSE 0 END),0) AS correct
                    FROM review_log WHERE user_id=? AND DATE(reviewed_at)=?''',
                    (uid, datetime.date.today().isoformat())).fetchone()
            return jsonify(total=int(row['total']), correct=int(row['correct']))
        except Exception:
            return jsonify(error='practice_progress_unavailable'), 503

    def issue():
        if not selected(environ):
            return jsonify(error='practice_steps_disabled'), 503
        if (request.headers.get('Sec-Fetch-Site') == 'cross-site' or
                (request.headers.get('Origin') and request.headers['Origin'] != request.host_url.rstrip('/'))):
            return jsonify(error='same_origin_required'), 403
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or set(data) != {'question_id'} or type(data['question_id']) is not int:
            return jsonify(error='invalid_question_id'), 400
        try:
            uid, qid = int(session['user_id']), data['question_id']
            question = runtime['_practice_question_by_id'](qid)
            context = runtime['_map_battle_question_context'](question)
            content_hash = hashlib.sha256(question['content'].encode()).hexdigest()
            with transaction() as conn:
                if not conn.execute('SELECT id FROM users WHERE id=?', (uid,)).fetchone():
                    raise NonMapRejected('authentication_required', 401)
                admit(conn, uid, question)
                identity = runtime['_practice_identity_for_write'](conn, qid)
                candidate = issue_practice_attempt(app.secret_key, user_id=uid, question=question,
                    source_record_uuid=identity, question_context=context)
                # One attempt per user/question/server day, no public restart.
                # Repeated SRS practice can resume on a later day. Within the
                # day, content/identity changes and expiry explicitly HOLD.
                conn.execute('''INSERT INTO g076_practice_attempts
                    (user_id,question_id,slot_date,content_hash,attempt_token) VALUES (?,?,?,?,?)
                    ON CONFLICT(user_id,question_id,slot_date) DO NOTHING''', (uid, qid, _slot_day(), content_hash, candidate))
                row = conn.execute('''SELECT * FROM g076_practice_attempts
                    WHERE user_id=? AND question_id=? AND slot_date=?''',
                                   (uid, qid, _slot_day())).fetchone()
                if row['content_hash'] != content_hash:
                    raise NonMapRejected('practice_content_changed_requires_reconciliation')
                token = row['attempt_token']
                ctx = resolve(conn, uid, 'practice', token)
                _validate(ctx)
            return jsonify(ok=True, attempt_token=token, question_id=qid,
                           question_revision=context['question_revision'])
        except (NonMapRejected, PracticeAttemptError) as error:
            return jsonify(error=error.code), error.status
        except Exception:
            return jsonify(error='practice_steps_backend_hold'), 503

    @app.after_request
    def no_store(response):
        if request.path.startswith(('/api/g076/', '/api/srs/practice/')):
            response.headers['Cache-Control'] = 'private, no-store'
        return response

    return issue
