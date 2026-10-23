"""Rating-only candidate. No app import, automatic registration, or Elo engine.

Integration must lock the original Rating session FIRST, on the SAME connection
as this ledger and settlement. See RatingServices; calling rt_answer is unsafe.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ContextManager, Mapping, Protocol
import hashlib
import json
import secrets
import time

from g076_question_privacy import board_only_sgf
from g076_server_step_authority import adjudicate_next_step, validate_step_question
from sgf_engine.parser.sgf_parser import parse_sgf
from sgf_point_transform import transform_sgf


class RatingRejected(ValueError):
    def __init__(self, code: str, status: int = 409):
        super().__init__(code)
        self.code, self.status = code, status


@dataclass(frozen=True)
class RatingContext:
    session_id: str
    user_id: int | None
    question_token: str | None
    question: Mapping[str, Any] | None  # original, PRIVATE pool question
    transform: int
    summary: Mapping[str, Any]  # original start/resume semantics


class RatingServices(Protocol):
    """MANDATORY integration contract, not a wrapper around Flask rt_answer.

    transaction: commit once on success; rollback EVERY exception/commit failure.
    resolve: SELECT original session FOR UPDATE, enforce original owner rights
      (anonymous sid remains a capability), resolve CURRENT pool question/token.
    start: original selection/prior/placement logic on conn; browser Elo forbidden.
    settle: extracted original rt_answer effects, including _rt_server_verify,
      token/current-round checks and finalize; NO commit, new connection or I/O.
      Return original result. No client or step verdict enters the Elo authority.
    Placement unlock must use the same connection or a transactional outbox;
      the original callback that opens/commits another connection must not run
      inside this rollbackable transaction or be silently omitted.
    """
    def transaction(self) -> ContextManager[Any]: ...
    def resolve(self, conn: Any, sid: str, uid: int | None) -> RatingContext: ...
    def start(self, conn: Any, uid: int | None, trigger: str) -> RatingContext: ...
    def settle(self, conn: Any, ctx: RatingContext, moves: list[dict],
               response_ms: int) -> Mapping[str, Any]: ...
    def settle_forfeit(self, conn: Any, ctx: RatingContext, moves: list[dict],
                       response_ms: int, reason: str) -> Mapping[str, Any]:
        """Server-authorized failure; original writer, no move fabrication.

        Called only after owner/session lock, binding, live nonce and deadline
        checks. Preserve original placement and unlock on this connection.
        """
        ...


# Explicit PROPOSED schema: run only in disposable fixtures until reviewed.
SCHEMA = (
    '''CREATE TABLE g076_rating_attempts (
       id TEXT PRIMARY KEY, session_id TEXT NOT NULL, binding TEXT NOT NULL,
       context_key TEXT NOT NULL UNIQUE, state_json TEXT NOT NULL)''',
    '''CREATE TABLE g076_rating_events (
       attempt_id TEXT NOT NULL, nonce TEXT NOT NULL, request_hash TEXT NOT NULL,
       response_json TEXT NOT NULL, PRIMARY KEY(attempt_id,nonce))''',
)


def mode(environ: Mapping[str, str]) -> str:
    """Flag-level decision, delegated to the shared per-mode gate.

    The Rating flag is g076_mode_gate.FLAGS['rating']. Adapter readiness is a
    separate server-side check (RatingAppServices.ready) applied by the
    blueprint, so 'steps' here still means HOLD until the ledger is admitted.
    This mode projects its own board-only payloads. Global privacy must not
    be enabled merely to exercise Rating (it contains unrelated modes).
    """
    from g076_mode_gate import select_mode
    return select_mode(environ, 'rating', adapter_ready=True).selected


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def _binding(ctx):
    return hashlib.sha256(_json([ctx.session_id, ctx.user_id,
        ctx.question['id'] if ctx.question else None, ctx.question_token,
        ctx.transform, dict(ctx.question or {})]).encode()).hexdigest()


SUMMARY = ('session_id', 'finished', 'round', 'total_rounds', 'min_rounds',
           'cur_rating', 'rating_se', 'rank_label', 'rank_range', 'provisional',
           'pool_size', 'answers', 'rating_change', 'streak', 'converged',
           'rounds_used', 'start_zone_key', 'correct')


def _summary(payload):
    result = {k: payload[k] for k in SUMMARY if k in payload and k != 'answers'}
    if 'answers' in payload:
        result['answers'] = [{k: a[k] for k in ('correct', 'discipline', 'q_rating')
                              if k in a} for a in payload['answers']]
    return result


def _seconds(rating):
    return 25 if rating <= 1400 else 35 if rating <= 1700 else 50 if rating <= 2100 else 60


def _prepared(ctx):
    if not ctx.question or not ctx.question_token or type(ctx.transform) is not int or not 0 <= ctx.transform < 8:
        raise RatingRejected('rating_current_question_unavailable')
    q = dict(ctx.question)
    if any(q.get(k) for k in ('accepted_moves', 'accepted_answers')):
        # Do not silently narrow an alternative-answer authority.
        raise RatingRejected('rating_step_policy_needs_review', 422)
    try:
        q['content'] = transform_sgf(q['content'], ctx.transform)
        preview = board_only_sgf(q['content'])
        root = parse_sgf(preview)
        size, color = root.metadata.get('size', 19), root.metadata.get('player_to_move', 'B')
        validate_step_question(q, player_color=color, board_size=size)
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        raise RatingRejected('rating_step_preflight_unavailable', 422) from error
    return q, preview, size, color


def open_current(conn, ctx: RatingContext, now: float):
    result = _summary(ctx.summary)
    if result.get('finished'):
        return result
    q, preview, size, color = _prepared(ctx)
    binding = _binding(ctx)
    aid = hashlib.sha256(('rating-step-v1:' + binding).encode()).hexdigest()
    context_key = hashlib.sha256(_json([ctx.session_id, ctx.question['id'], ctx.question_token]).encode()).hexdigest()
    row = conn.execute('SELECT binding,state_json FROM g076_rating_attempts WHERE context_key=?', (context_key,)).fetchone()
    if row:
        if row['binding'] != binding:
            raise RatingRejected('rating_question_revision_changed')
        state = json.loads(row['state_json'])
    else:
        state = {'nonce': secrets.token_urlsafe(24), 'index': 0, 'moves': [],
                 'played': [], 'started': now, 'deadline': now + _seconds(q['rating']),
                 'terminal': False}
        conn.execute('INSERT INTO g076_rating_attempts VALUES(?,?,?,?,?)',
                     (aid, ctx.session_id, binding, context_key, _json(state)))
    if state['terminal']:
        raise RatingRejected('rating_terminal_current_context')
    result['question'] = {k: q[k] for k in ('id', 'rating', 'difficulty', 'discipline') if k in q}
    result['question'].update(content=preview, board_only=True, transform_index=ctx.transform,
        step={'attempt_id': aid, 'nonce': state['nonce'], 'index': state['index'],
              'played': state['played'], 'deadline': state['deadline'], 'server_now': now})
    return result


def advance(conn, services: RatingServices, ctx: RatingContext, body: dict, now: float):
    if set(body) - {'session_id', 'attempt_id', 'nonce', 'action', 'move'}:
        raise RatingRejected('rating_untrusted_fields', 400)
    aid, nonce, action = body.get('attempt_id'), body.get('nonce'), body.get('action')
    if not isinstance(aid, str) or not isinstance(nonce, str) or action not in ('move', 'timeout', 'give_up'):
        raise RatingRejected('rating_invalid_step', 400)
    row = conn.execute('SELECT * FROM g076_rating_attempts WHERE id=? AND session_id=?',
                       (aid, ctx.session_id)).fetchone()
    if row is None:
        raise RatingRejected('rating_attempt_mismatch', 403)
    digest = hashlib.sha256(_json(body).encode()).hexdigest()
    event = conn.execute('SELECT * FROM g076_rating_events WHERE attempt_id=? AND nonce=?', (aid, nonce)).fetchone()
    if event:
        if event['request_hash'] != digest:
            raise RatingRejected('rating_replay_conflict')
        return json.loads(event['response_json'])
    state = json.loads(row['state_json'])
    if row['binding'] != _binding(ctx) or state['terminal'] or not secrets.compare_digest(nonce, state['nonce']):
        raise RatingRejected('rating_stale_step')
    q, _, size, color = _prepared(ctx)
    reply = None
    if action != 'move' and 'move' in body:
        raise RatingRejected('rating_invalid_step', 400)
    if action == 'timeout' and now < state['deadline']:
        raise RatingRejected('rating_timeout_not_due')
    # Fail closed for adapters lacking the trusted original failure writer.
    needs_forfeit = action != 'move' or now >= state['deadline']
    if needs_forfeit and not callable(getattr(services, 'settle_forfeit', None)):
        raise RatingRejected('rating_forfeit_transaction_not_integrated', 503)
    status = 'INCORRECT'
    if action == 'move':
        move = body.get('move')
        if not isinstance(move, dict) or set(move) != {'x', 'y'} or any(
                type(move[k]) is not int or not 0 <= move[k] < size for k in ('x', 'y')):
            raise RatingRejected('rating_invalid_move', 400)
        if now < state['deadline']:
            decision = adjudicate_next_step(q, player_color=color, board_size=size,
                trusted_history=[(m['x'], m['y']) for m in state['moves']], move=(move['x'], move['y']))
            status, reply = decision.status, decision.opponent_reply
            state['moves'].append(move)
            state['played'].append(dict(move, color=color))
            if reply:
                state['played'].append({'x': reply[0], 'y': reply[1], 'color': 'W' if color == 'B' else 'B'})
    state['index'] += 1
    state['nonce'] = secrets.token_urlsafe(24)
    response = {'status': status, 'played': state['played'], 'index': state['index']}
    if status == 'CONTINUE':
        state['deadline'] = now + _seconds(q['rating'])
        response.update(nonce=state['nonce'], deadline=state['deadline'], server_now=now)
    else:
        state['terminal'] = True
        # Only trusted stored moves enter the ORIGINAL judge/Elo transaction.
        elapsed_ms = min(600000, max(0, int((now-state['started'])*1000)))
        if needs_forfeit:
            # Pass only committed history; a late client move is never added.
            reason = 'timeout' if now >= state['deadline'] else 'give_up'
            state['forfeit_reason'] = reason
            canonical = services.settle_forfeit(conn, ctx, list(state['moves']),
                                                elapsed_ms, reason)
        else:
            canonical = services.settle(conn, ctx, state['moves'], elapsed_ms)
        if canonical.get('correct') is not (status == 'CORRECT'):
            raise RatingRejected('rating_authority_disagreement', 422)
        following = services.resolve(conn, ctx.session_id, ctx.user_id)
        response['result'] = {**_summary(canonical), **open_current(conn, following, now)}
    conn.execute('UPDATE g076_rating_attempts SET state_json=? WHERE id=?', (_json(state), aid))
    conn.execute('INSERT INTO g076_rating_events VALUES(?,?,?,?)', (aid, nonce, digest, _json(response)))
    return response


def create_rating_blueprint(services: RatingServices | None, environ, *, clock=time.time):
    """Register capability even without adapter: ON then returns HOLD (503).

    G MASTER must also guard legacy start/answer/resume and every exposure path
    under this per-mode gate. Merely registering this blueprint is NOT admission.
    """
    from flask import Blueprint, jsonify, request, session
    bp = Blueprint('g076_rating_steps', __name__)

    @bp.after_request
    def private(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Vary'] = 'Cookie'
        return response

    @bp.errorhandler(RatingRejected)
    def rejected(error):
        return jsonify(error=error.code, mode='hold'), error.status

    def require():
        if mode(environ) != 'steps' or services is None or not ready():
            raise RatingRejected('rating_steps_hold', 503)
        if request.method == 'POST' and (not request.is_json or (
                request.headers.get('Origin') and request.headers['Origin'] != request.host_url.rstrip('/'))):
            raise RatingRejected('rating_origin_rejected', 403)

    def uid():
        value = session.get('user_id')
        if value is not None and (type(value) is not int or value <= 0):
            raise RatingRejected('rating_invalid_identity', 401)
        return value

    def ready():
        check = getattr(services, 'ready', None)
        return check() if callable(check) else services is not None

    @bp.get('/api/g076/rating/capability')
    def capability():
        current = mode(environ)
        available = current == 'steps' and services is not None and ready()
        return jsonify(mode='steps' if available else 'legacy' if current == 'legacy' else 'hold'), (200 if available or current == 'legacy' else 503)

    @bp.post('/api/g076/rating/start')
    def start():
        require()
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or set(body) - {'trigger'} or body.get('trigger', 'manual') not in ('manual', 'placement'):
            raise RatingRejected('rating_untrusted_start_fields', 400)
        with services.transaction() as conn:
            return jsonify(open_current(conn, services.start(conn, uid(), body.get('trigger', 'manual')), clock()))

    @bp.get('/api/g076/rating/resume/<sid>')
    def resume(sid):
        require()
        with services.transaction() as conn:
            return jsonify(open_current(conn, services.resolve(conn, sid, uid()), clock()))

    @bp.post('/api/g076/rating/step')
    def step():
        require()
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or not isinstance(body.get('session_id'), str):
            raise RatingRejected('rating_invalid_step', 400)
        with services.transaction() as conn:
            ctx = services.resolve(conn, body['session_id'], uid())
            return jsonify(advance(conn, services, ctx, body, clock()))

    return bp
