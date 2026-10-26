"""Mistakes step adapter. app.py supplies the Product services from
g079_mistakes_services.py; services=None (or a partial provider) stays HOLD.

No runtime DDL. Injected providers MUST use the supplied connection; settle
must preserve the existing review/reward policy, never commit or call the
current connection-owning ReviewService. A test provider is not product admission.
"""
from dataclasses import dataclass
import datetime
import hashlib
import hmac

from flask import Blueprint, jsonify, request, session, current_app
from g076_nonmap_steps import (
    Context, NonMapRejected, _mac, _validate, _session,
    open_steps, submit_step, resolve_practice,
)
from practice_answer_authority import issue_practice_attempt, PracticeAttemptError
from map_battle_runtime import MapBattleRuntimeError


def mode(environ):
    from g076_mode_gate import select_mode
    # This is server flag parsing only, not an assertion that the Product
    # settlement adapter is ready. ready() separately requires trusted services.
    return select_mode(environ, 'mistakes', adapter_ready=True).selected


@dataclass(frozen=True)
class MistakesServices:
    transaction: object
    question: object       # (conn, qid): unique enabled canonical record
    identity: object       # (conn, qid): existing canonical UUID; never mint
    context: object        # (question): board/colour/content-derived revision
    admit: object          # (conn, uid, question): current rights fingerprint
    settle: object         # (conn, ctx, canonical, verdict, id): atomic writer


def create_blueprint(*, secret, environ, services=None):
    bp = Blueprint('g076_mistakes', __name__)
    signing_key = _mac(secret, 'mistakes-attempt-signing-v1')

    @bp.after_request
    def no_store(response):
        response.headers['Cache-Control'] = 'private, no-store'
        response.headers['Vary'] = 'Cookie'
        return response

    def uid():
        value = session.get('user_id')
        if type(value) is not int or value < 1:
            raise NonMapRejected('authentication_required', 401)
        return value

    def ready():
        if mode(environ) == 'legacy':
            raise NonMapRejected('mistakes_steps_disabled', 503)
        if mode(environ) != 'steps' or not services_available():
            raise NonMapRejected('mistakes_review_transaction_hold', 503)

    def services_available():
        # A structural check only; it does not certify Product policy parity.
        # Keep discovery and execution consistent, including partially wired ports.
        return services is not None and all(
            callable(getattr(services, name, None)) for name in
            ('transaction', 'question', 'identity', 'context', 'admit', 'settle'))

    def rights(conn, user, question):
        # Membership is server state, not the browser's source_context.
        if not conn.execute('SELECT 1 FROM mistake_log WHERE user_id=? AND question_id=?',
                            (user, question['id'])).fetchone():
            raise NonMapRejected('mistake_not_owned', 403)
        value = services.admit(conn, user, question)
        if not isinstance(value, str) or not value or len(value) > 512:
            raise NonMapRejected('mistakes_rights_binding_unavailable', 503)
        return hashlib.sha256(value.encode()).hexdigest()

    def resolve(conn, user, token):
        day = datetime.date.today().isoformat()
        observed = []
        def admit(user, question):
            observed.append(rights(conn, user, question))
        ctx = resolve_practice(signing_key, token, uid=user,
            question_loader=lambda qid: services.question(conn, qid),
            identity=lambda qid: services.identity(conn, qid), admit=admit)
        row = conn.execute('''SELECT * FROM g076_mistakes_attempts
            WHERE user_id=? AND question_id=? AND slot_date=?''',
            (user, ctx.question['id'], day)).fetchone()
        digest = hashlib.sha256(ctx.question['content'].encode()).hexdigest()
        if (not row or not hmac.compare_digest(row['attempt_token'], token)
                or row['content_hash'] != digest or row['rights_hash'] != observed[0]):
            raise NonMapRejected('mistakes_attempt_changed')
        return Context('mistakes', user, day + ':' + str(ctx.question['id']),
                       ctx.question, ctx.attempt)

    def dispatch(action):
        try:
            user = uid()
            ready()
            if (request.headers.get('Sec-Fetch-Site') == 'cross-site' or
                    (request.headers.get('Origin') and
                     request.headers['Origin'] != request.host_url.rstrip('/'))):
                raise NonMapRejected('same_origin_required', 403)
            if request.content_length and request.content_length > 32768:
                raise NonMapRejected('step_request_too_large', 413)
            data = request.get_json(silent=True)
            fields = ({'question_id'} if action == 'issue' else
                      {'flow', 'attempt_token'} | (
                          {'step_index', 'step_nonce', 'move'} if action == 'step' else set()))
            if not isinstance(data, dict) or set(data) != fields:
                raise NonMapRejected('invalid_mistakes_fields', 400)
            with services.transaction() as conn:
                if action == 'issue':
                    qid = data['question_id']
                    if type(qid) is not int:
                        raise NonMapRejected('invalid_question_id', 400)
                    question = services.question(conn, qid)
                    if not question or question.get('enabled', True) is False:
                        raise NonMapRejected('question_unavailable', 404)
                    rights_hash = rights(conn, user, question)
                    candidate = issue_practice_attempt(signing_key, user_id=user,
                        question=question, source_record_uuid=services.identity(conn, qid),
                        question_context=services.context(question))
                    conn.execute('''INSERT INTO g076_mistakes_attempts
                        (user_id,question_id,slot_date,content_hash,rights_hash,attempt_token)
                        VALUES (?,?,?,?,?,?) ON CONFLICT(user_id,question_id,slot_date) DO NOTHING''',
                        (user, qid, datetime.date.today().isoformat(),
                         hashlib.sha256(question['content'].encode()).hexdigest(), rights_hash, candidate))
                    row = conn.execute('''SELECT attempt_token FROM g076_mistakes_attempts
                        WHERE user_id=? AND question_id=? AND slot_date=?''',
                        (user, qid, datetime.date.today().isoformat())).fetchone()
                    token = row['attempt_token']
                    ctx = resolve(conn, user, token)
                    _validate(ctx)
                    result = {'attempt_token': token}
                else:
                    if (data['flow'] != 'mistakes' or not isinstance(data['attempt_token'], str)
                            or not 1 <= len(data['attempt_token']) <= 8192):
                        raise NonMapRejected('invalid_mistakes_fields', 400)
                    ctx = resolve(conn, user, data['attempt_token'])
                    if action == 'start':
                        result = open_steps(conn, ctx, secret=secret, settle=services.settle)
                    elif action == 'answer':
                        row, _ = _session(conn, ctx, secret)
                        if row['state'] != 'SETTLED':
                            raise NonMapRejected('mistakes_not_settled', 403)
                        result = {'content': ctx.question['content'], 'settled': True}
                    else:
                        result = submit_step(conn, ctx,
                            {k: data[k] for k in ('step_index', 'step_nonce', 'move')},
                            secret=secret, settle=services.settle)
            return jsonify(result)
        except (NonMapRejected, PracticeAttemptError, MapBattleRuntimeError) as error:
            return jsonify(error=error.code), int(getattr(error, 'status', 409))
        except Exception:
            # Test-only trace; production never includes internal exception text.
            if current_app.testing:
                raise
            return jsonify(error='mistakes_backend_hold'), 503

    @bp.get('/api/g076/mistakes/capability')
    def capability():
        try:
            uid()
        except NonMapRejected as error:
            return jsonify(error=error.code), error.status
        selected = mode(environ)
        if selected == 'hold' or (selected == 'steps' and not services_available()):
            return jsonify(mode='hold', error='mistakes_review_transaction_hold'), 503
        return jsonify(mode=selected, protocol='g076-mistakes-steps-v1')

    for path, action in (('/attempt', 'issue'), ('/steps/start', 'start'),
                         ('/steps', 'step'), ('/answer', 'answer')):
        bp.add_url_rule('/api/g076/mistakes' + path, action,
                        lambda action=action: dispatch(action), methods=['POST'])
    return bp
