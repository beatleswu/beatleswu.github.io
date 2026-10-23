"""Independent G076 Practice/Daily step bridge. PRODUCT INTEGRATION HOLD.

No application registration, schema creation, environment changes or autonomous
reward writer. An integrator MUST supply owner/entitlement resolution and the
existing mode's settlement adapter on the SAME connection/transaction. A callback
must not commit, open another connection, or perform external side effects.
SQLite callers use BEGIN IMMEDIATE; PostgreSQL callers use a transaction and
the repository's qmark connection adapter. Failures must roll back the whole
transaction, including settlement. Fixtures are the only schema consumers now.
"""
from dataclasses import dataclass
import hashlib
import hmac
import json

from g076_question_privacy import board_only_sgf, privacy_enforced
from g076_server_step_authority import adjudicate_next_step, StepAuthorityUnavailable
from map_battle_runtime import question_revision_for, MapBattleRuntimeError
from practice_answer_authority import (
    verify_practice_attempt, canonicalize_practice_answer, judge_practice_answer,
    practice_submission_id, PracticeAttemptError,
)
from daily_challenge_authority import (
    verify_daily_attempt, question_content_sha256, canonicalize_daily_answer,
    judge_daily_answer, DailyAttemptError,
)


class NonMapRejected(ValueError):
    def __init__(self, code, status=409):
        super().__init__(code)
        self.code, self.status = code, status


@dataclass(frozen=True)
class Context:
    flow: str
    uid: int
    scope: str
    question: dict
    attempt: dict


def resolve_practice(secret, token, *, uid, question_loader, identity, admit,
                     now=None):
    """Identity and rights providers are mandatory, read-only, server-owned."""
    attempt = verify_practice_attempt(secret, token, user_id=uid, now=now)
    q = question_loader(int(attempt['question_id']))
    if not q or q.get('enabled', True) is False:
        raise NonMapRejected('question_unavailable', 404)
    # Legacy practice tokens do not carry a separate content hash. An opaque
    # editorial revision can remain unchanged while SGF changes; admit only a
    # content-derived revision (or the explicit policy's content-derived hash).
    if (not q.get('answer_policy') and question_revision_for(q) !=
            hashlib.sha256(q.get('content', '').encode('utf-8')).hexdigest()):
        raise NonMapRejected('practice_content_revision_binding_unavailable', 422)
    attempt = verify_practice_attempt(
        secret, token, user_id=uid, question_id=q['id'],
        question_revision=question_revision_for(q),
        source_record_uuid=identity(q['id']), now=now)
    admit(uid, q)  # premium/free policy; never inferred from browser mode
    return Context('practice', uid, attempt['nonce'], q, attempt)


def resolve_daily(secret, token, *, uid, today, question, admit, now=None):
    """Caller supplies today's server-selected question, never a client qid.

    All issued tokens for one user/date share ONE cursor. Refreshing /today
    cannot reset a wrong answer or create another solution-probing attempt.
    """
    if not question or question.get('enabled', True) is False:
        raise NonMapRejected('question_unavailable', 404)
    attempt = verify_daily_attempt(
        secret, token, user_id=uid, challenge_date=today,
        question_id=question['id'], question_revision=question_revision_for(question),
        question_content_sha256=question_content_sha256(question), now=now)
    admit(uid, question)  # preserve Daily's own policy, not Practice's policy
    return Context('daily', uid, today, question, attempt)


def enabled(environ):
    return privacy_enforced(environ) and str(environ.get(
        'G076_NONMAP_STEPS_ENABLED', '')).strip().lower() in ('1', 'true', 'on')


def _mac(secret, *values):
    if not isinstance(secret, (str, bytes)) or not secret:
        raise NonMapRejected('step_signing_unavailable', 503)
    key = secret.encode() if isinstance(secret, str) else secret
    return hmac.new(key, json.dumps(values, separators=(',', ':')).encode(),
                    hashlib.sha256).hexdigest()


def _binding(ctx):
    a = ctx.attempt
    return json.dumps([ctx.flow, ctx.uid, ctx.scope, ctx.question['id'],
                       question_revision_for(ctx.question), a['board_size'],
                       a['player_color'], a.get('source_record_uuid'),
                       hashlib.sha256(ctx.question['content'].encode('utf-8')).hexdigest(),
                       ctx.question.get('answer_policy')],
                      separators=(',', ':'))


def _validate(ctx):
    if ctx.flow not in ('practice', 'daily') or type(ctx.uid) is not int or ctx.uid < 1:
        raise NonMapRejected('unsupported_step_context', 400)
    a = ctx.attempt
    if (a.get('transform_id') != 'identity' or
            a.get('question_revision') != question_revision_for(ctx.question)):
        raise NonMapRejected('step_context_stale_or_transformed')
    if ctx.question.get('answer_policy') not in (None, '', 'g065-explicit-v1'):
        raise NonMapRejected('unsupported_answer_policy', 422)
    # The shared step kernel does not implement accepted one-move alternatives.
    # Never misgrade them as off-tree INCORRECT or silently ignore them.
    if (ctx.question.get('accepted_moves') or ctx.question.get('accepted_answers') or
            ctx.question.get('katago_best_move')):
        raise NonMapRejected('alternative_answer_step_policy_unavailable', 422)
    try:
        return board_only_sgf(ctx.question['content'])
    except (ValueError, KeyError) as error:
        raise NonMapRejected('question_preview_unavailable', 422) from error


def _session(conn, ctx, secret, *, create=False):
    preview = _validate(ctx)
    sid = _mac(secret, 'nonmap-session-v1', ctx.flow, ctx.uid, ctx.scope)
    binding = _binding(ctx)
    if create:
        conn.execute('''INSERT INTO g076_nonmap_sessions
            (id,user_id,flow,binding,step_index,history_json,state)
            VALUES (?,?,?,?,0,'[]','OPEN') ON CONFLICT(id) DO NOTHING''',
                     (sid, ctx.uid, ctx.flow, binding))
    sql = 'SELECT * FROM g076_nonmap_sessions WHERE id=? AND user_id=? AND flow=?'
    raw = getattr(conn, '_conn', conn)
    if not raw.__class__.__module__.startswith('sqlite3'):
        sql += ' FOR UPDATE'
    row = conn.execute(sql, (sid, ctx.uid, ctx.flow)).fetchone()
    if row is None:
        raise NonMapRejected('step_session_missing')
    row = dict(row)
    if not hmac.compare_digest(row['binding'], binding):
        raise NonMapRejected('step_session_revision_changed')
    return row, preview


def _nonce(secret, row, index):
    return _mac(secret, 'nonmap-step-v1', row['id'], row['binding'], index)


def _event(conn, sid, index):
    row = conn.execute('SELECT * FROM g076_nonmap_events WHERE session_id=? AND step_index=?',
                       (sid, index)).fetchone()
    return dict(row) if row else None


def _response(event, secret, row, duplicate):
    value = json.loads(event['response_json'])
    value['duplicate'] = duplicate
    if value['status'] == 'CONTINUE':
        value['step_nonce'] = _nonce(secret, row, value['step_index'])
    return value


def open_steps(conn, ctx, *, secret, settle):
    if not callable(settle):
        raise NonMapRejected('mode_settlement_unavailable', 503)
    row, preview = _session(conn, ctx, secret, create=True)
    if row['state'] == 'SETTLED':
        event = _event(conn, row['id'], row['step_index'] - 1)
        if not event:
            raise NonMapRejected('step_event_missing', 503)
        return _response(event, secret, row, True)
    history = json.loads(row['history_json'])
    if len(history) != row['step_index']:
        raise NonMapRejected('invalid_server_history', 503)
    previous = []
    for index, move in enumerate(history):
        event = _event(conn, row['id'], index)
        if not event:
            raise NonMapRejected('step_event_missing', 503)
        value = json.loads(event['response_json'])
        previous.append({'player_move': move, 'opponent_reply': value['opponent_reply']})
    return {'status': 'READY', 'step_index': row['step_index'],
            'step_nonce': _nonce(secret, row, row['step_index']),
            'content': preview, 'board_only': True,
            'board_size': ctx.attempt['board_size'],
            'player_color': ctx.attempt['player_color'], 'previous_steps': previous}


def _safe_settlement(value):
    """Explicit output allowlist: adapters cannot return question/solution data."""
    if not isinstance(value, dict) or set(value) - {'submission_id', 'xp_awarded', 'srs'}:
        raise NonMapRejected('unsafe_settlement_response', 503)
    if not isinstance(value.get('submission_id'), str) or len(value['submission_id']) > 128:
        raise NonMapRejected('invalid_settlement_receipt', 503)
    if 'xp_awarded' in value and (type(value['xp_awarded']) is not int or value['xp_awarded'] < 0):
        raise NonMapRejected('invalid_settlement_receipt', 503)
    if 'srs' in value:
        srs = value['srs']
        if (not isinstance(srs, dict) or set(srs) != {
                'ease_factor', 'interval', 'repetitions', 'due_date'} or
                any(type(srs[k]) not in (int, float) for k in (
                    'ease_factor', 'interval', 'repetitions')) or
                not isinstance(srs['due_date'], str) or len(srs['due_date']) > 40):
            raise NonMapRejected('invalid_settlement_receipt', 503)
    return value


def submit_step(conn, ctx, data, *, secret, settle):
    if not callable(settle):
        raise NonMapRejected('mode_settlement_unavailable', 503)
    if not isinstance(data, dict) or set(data) != {'step_index', 'step_nonce', 'move'}:
        raise NonMapRejected('invalid_step_fields', 400)
    index, move = data['step_index'], data['move']
    size = ctx.attempt['board_size']
    if (type(index) is not int or not 0 <= index < 100 or
            not isinstance(move, dict) or set(move) != {'x', 'y'} or
            any(type(move[k]) is not int or not 0 <= move[k] < size for k in ('x', 'y'))):
        raise NonMapRejected('invalid_step_move', 400)
    row, _ = _session(conn, ctx, secret)
    expected = _nonce(secret, row, index)
    if (not isinstance(data['step_nonce'], str) or not data['step_nonce'].isascii() or
            not hmac.compare_digest(expected, data['step_nonce'])):
        raise NonMapRejected('invalid_step_nonce', 403)
    digest = _mac(secret, 'nonmap-request-v1', row['id'], index, move['x'], move['y'])
    replay = _event(conn, row['id'], index)
    if replay:
        if not hmac.compare_digest(replay['request_hash'], digest):
            raise NonMapRejected('step_reused_with_different_move')
        return _response(replay, secret, row, True)
    if row['state'] != 'OPEN' or row['step_index'] != index:
        raise NonMapRejected('step_stale_or_settled')
    history = json.loads(row['history_json'])
    if len(history) != index:
        raise NonMapRejected('invalid_server_history', 503)
    try:
        decision = adjudicate_next_step(
            ctx.question, player_color=ctx.attempt['player_color'], board_size=size,
            trusted_history=history, move=(move['x'], move['y']))
    except StepAuthorityUnavailable as error:
        raise NonMapRejected('step_judge_unavailable', 422) from error
    history.append([move['x'], move['y']])
    response = {'status': decision.status, 'step_index': index + 1,
                'opponent_reply': list(decision.opponent_reply) if decision.opponent_reply else None}
    terminal = decision.status != 'CONTINUE'
    if terminal:
        moves = {'moves': [{'x': x, 'y': y} for x, y in history]}
        canonicalize, judge = ((canonicalize_practice_answer, judge_practice_answer)
                              if ctx.flow == 'practice' else
                              (canonicalize_daily_answer, judge_daily_answer))
        canonical = canonicalize(moves, ctx.attempt)
        outcome = judge(ctx.question, ctx.attempt, canonical)
        if outcome.result != decision.status or outcome.authoritative_grade != (5 if decision.status == 'CORRECT' else 0):
            raise NonMapRejected('step_final_judge_disagreement', 503)
        # Stable across refresh/reissue and retries. No browser submission id,
        # grade, history, opponent move or mode-specific authority is accepted.
        event_id = (practice_submission_id(ctx.attempt) if ctx.flow == 'practice'
                    else 'g076-nm:' + row['id'])
        response['settlement'] = _safe_settlement(settle(conn, ctx, canonical, outcome, event_id))
    changed = conn.execute('''UPDATE g076_nonmap_sessions SET step_index=?,history_json=?,state=?
        WHERE id=? AND step_index=? AND state='OPEN' ''',
        (index + 1, json.dumps(history), 'SETTLED' if terminal else 'OPEN', row['id'], index))
    if changed.rowcount != 1:
        raise NonMapRejected('concurrent_step_conflict')
    conn.execute('''INSERT INTO g076_nonmap_events
        (session_id,step_index,request_hash,response_json) VALUES (?,?,?,?)''',
        (row['id'], index, digest, json.dumps(response)))
    return _response({'response_json': json.dumps(response)}, secret, row, False)


def create_blueprint(*, transaction, resolve, settle, secret, environ):
    """Dormant HTTP adapter. No registration in app.py until integration gates.

    transaction() must COMMIT before the HTTP response is returned and roll back
    on ANY exception. resolve(conn, uid, flow, token) rechecks identity and rights
    on every request, including retries. Authentication uses Flask session only.
    """
    from flask import Blueprint, jsonify, request, session
    bp = Blueprint('g076_nonmap_steps', __name__)

    @bp.after_request
    def no_store(response):
        response.headers['Cache-Control'] = 'private, no-store'
        return response

    def dispatch(start):
        if not enabled(environ):
            return jsonify(error='nonmap_steps_disabled'), 503
        uid = session.get('user_id')
        if type(uid) is not int or uid < 1:
            return jsonify(error='authentication_required'), 401
        if (request.headers.get('Sec-Fetch-Site') == 'cross-site' or
                (request.headers.get('Origin') and
                 request.headers['Origin'] != request.host_url.rstrip('/'))):
            return jsonify(error='same_origin_required'), 403
        if request.content_length and request.content_length > 32768:
            return jsonify(error='step_request_too_large'), 413
        data = request.get_json(silent=True)
        expected = {'flow', 'attempt_token'} | (set() if start else {'step_index', 'step_nonce', 'move'})
        if (not isinstance(data, dict) or set(data) != expected or
                data.get('flow') not in ('practice', 'daily') or
                not isinstance(data.get('attempt_token'), str) or
                not 1 <= len(data['attempt_token']) <= 8192):
            return jsonify(error='invalid_step_fields'), 400
        try:
            with transaction() as conn:
                ctx = resolve(conn, uid, data['flow'], data['attempt_token'])
                if ctx.uid != uid or ctx.flow != data['flow']:
                    raise NonMapRejected('resolver_context_mismatch', 403)
                result = (open_steps(conn, ctx, secret=secret, settle=settle) if start else
                          submit_step(conn, ctx, {k: data[k] for k in ('step_index', 'step_nonce', 'move')},
                                      secret=secret, settle=settle))
            response = jsonify(result)
        except (NonMapRejected, PracticeAttemptError, DailyAttemptError, MapBattleRuntimeError) as error:
            response = jsonify(error=getattr(error, 'code', 'step_unavailable'))
            response.status_code = int(getattr(error, 'status', 409))
        except Exception:
            # No exception strings, canonical SGF, request tokens or coordinates.
            response = jsonify(error='step_backend_unavailable')
            response.status_code = 503
        response.headers['Cache-Control'] = 'private, no-store'
        return response

    bp.add_url_rule('/api/g076/nonmap/steps/start', 'start', lambda: dispatch(True), methods=['POST'])
    bp.add_url_rule('/api/g076/nonmap/steps', 'submit', lambda: dispatch(False), methods=['POST'])
    return bp
