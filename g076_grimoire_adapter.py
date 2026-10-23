"""Isolated SQLite Grimoire step candidate; NOT registered by the application.

Server-only issue() needs a stable admission scope supplied by the integrator.
Providers run inside the transaction and must be read-only. Settlement must use
the supplied connection, never commit or perform external side effects. Only
the bounded node-only settlement below is supplied; catalog Grimoire settlement
is deliberately HOLD. No schema creation, environment mutation or network I/O.
"""
from contextlib import contextmanager
from datetime import datetime
import hashlib
import hmac
import json
import secrets
import sqlite3
import time

from g076_question_privacy import board_only_sgf, privacy_enforced
from g076_server_step_authority import validate_step_question, adjudicate_next_step
from map_battle_runtime import question_revision_for
from practice_answer_authority import canonicalize_practice_answer, judge_practice_answer


# Disposable fixture DDL only. MASTER must separately review any runtime schema.
ISOLATED_SCHEMA = """
CREATE TABLE g076_grimoire_attempts (
 token TEXT PRIMARY KEY, user_id INTEGER NOT NULL, scope TEXT NOT NULL,
 question_id INTEGER NOT NULL, binding TEXT NOT NULL, expires INTEGER NOT NULL,
 step_index INTEGER NOT NULL DEFAULT 0, history TEXT NOT NULL DEFAULT '[]',
 state TEXT NOT NULL DEFAULT 'OPEN', UNIQUE(user_id, scope));
CREATE TABLE g076_grimoire_events (
 token TEXT NOT NULL, step_index INTEGER NOT NULL, request_hash TEXT NOT NULL,
 response TEXT NOT NULL, PRIMARY KEY(token, step_index));
"""


class GrimoireRejected(ValueError):
    def __init__(self, code, status=409):
        super().__init__(code)
        self.code, self.status = code, status


def settle_node_only(conn, *, uid, question, correct, event_id, now):
    """Legacy node formula only; refuses incomplete catalog/cache settlement.

    No XP, SRS, review log, rank, identity migration or synthetic reward writer.
    Exactly-once is supplied by the enclosing attempt/event transaction.
    """
    from grimoire_api import calc_node_purity
    if question.get('grimoire_id'):
        raise GrimoireRejected('catalog_grimoire_settlement_hold', 503)
    if conn.execute('SELECT 1 FROM daily_training_cache WHERE user_id=? AND date=?',
                    (uid, now[:10])).fetchone():
        raise GrimoireRejected('daily_cache_settlement_hold', 503)
    old = conn.execute('SELECT * FROM node_mastery WHERE user_id=? AND question_id=?',
                       (uid, question['id'])).fetchone()
    history = json.loads(old['last_5_history']) if old else []
    if (not isinstance(history, list) or len(history) > 5 or
            any(type(value) is not bool for value in history)):
        raise GrimoireRejected('invalid_mastery_history', 503)
    history = (history + [correct])[-5:]
    purity = calc_node_purity(history)
    conn.execute('''INSERT INTO node_mastery
        (user_id,question_id,purity,attempt_count,last_5_history,last_correct_at,is_contaminated)
        VALUES (?,?,?,?,?,?,?)
        ON CONFLICT(user_id,question_id) DO UPDATE SET
        purity=excluded.purity, attempt_count=excluded.attempt_count,
        last_5_history=excluded.last_5_history,
        last_correct_at=COALESCE(excluded.last_correct_at,node_mastery.last_correct_at),
        is_contaminated=excluded.is_contaminated''',
        (uid, question['id'], purity, old['attempt_count'] + 1 if old else 1,
         json.dumps(history), now if correct else None, int(not correct and purity < .3)))
    return {'submission_id': event_id}


class GrimoireSteps:
    """SQLite-only service owning BEGIN IMMEDIATE through COMMIT.

    connect() returns a NEW disposable sqlite3.Connection with Row factory.
    load(conn,qid), identity(conn,qid), admit(conn,uid,q) are trusted providers;
    admit must return exactly True. No browser identity/rights claims accepted.
    The transport must authenticate uid; create_blueprint supplies that boundary.
    """
    def __init__(self, *, connect, load, identity, admit, secret, environ,
                 settle=None, clock=time.time):
        self.connect, self.load, self.identity, self.admit = connect, load, identity, admit
        self.secret, self.environ, self.settle, self.clock = secret, environ, settle, clock

    @contextmanager
    def _transaction(self, uid):
        if not (privacy_enforced(self.environ) and str(self.environ.get(
                'G076_GRIMOIRE_STEPS_ENABLED', '')).lower() in ('1', 'true', 'on')):
            raise GrimoireRejected('grimoire_steps_disabled', 503)
        if type(uid) is not int or uid < 1:
            raise GrimoireRejected('authentication_required', 401)
        if not callable(self.settle) or not isinstance(self.secret, bytes) or len(self.secret) < 32:
            raise GrimoireRejected('grimoire_dependencies_unavailable', 503)
        conn = self.connect()
        try:
            if type(conn) is not sqlite3.Connection or conn.in_transaction:
                raise GrimoireRejected('isolated_sqlite_required', 503)
            conn.execute('BEGIN IMMEDIATE')
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _question(self, conn, uid, qid):
        q = self.load(conn, qid)
        if not isinstance(q, dict) or q.get('id') != qid or q.get('enabled', True) is not True:
            raise GrimoireRejected('question_unavailable', 404)
        if self.admit(conn, uid, q) is not True:
            raise GrimoireRejected('rights_required', 403)
        identity = self.identity(conn, qid)
        if not isinstance(identity, str) or not identity.strip():
            raise GrimoireRejected('identity_unavailable', 503)
        if q.get('answer_policy') not in (None, '', 'g065-explicit-v1') or any(
                q.get(k) for k in ('accepted_moves', 'accepted_answers', 'katago_best_move')):
            raise GrimoireRejected('answer_policy_hold', 422)
        preview = board_only_sgf(q['content'])
        # Derive board context from the server projection, never browser metadata.
        from sgf_point_transform import _properties
        props = {name: preview[start:end] for _, _, name, start, end in _properties(preview)}
        size, color = int(props['SZ']), props['PL']
        validate_step_question(q, player_color=color, board_size=size)
        binding = json.dumps([q, identity, size, color], sort_keys=True, separators=(',', ':'))
        attempt = dict(source_record_uuid=identity, board_size=size, player_color=color,
                       question_revision=question_revision_for(q), transform_id='identity')
        return q, preview, binding, attempt

    def issue(self, uid, *, question_id, scope, ttl=3600):
        """SERVER ONLY. Scope is a stable server admission ID, never request data.

        Reissuing a scope resumes the same attempt, including a failed attempt.
        A new scope constitutes a new mastery attempt: policy remains MASTER HOLD.
        """
        if (type(question_id) is not int or question_id < 1 or not isinstance(scope, str)
                or not 1 <= len(scope) <= 128 or type(ttl) is not int or not 1 <= ttl <= 86400):
            raise GrimoireRejected('invalid_server_admission', 400)
        with self._transaction(uid) as conn:
            _, _, binding, _ = self._question(conn, uid, question_id)
            conn.execute('''INSERT INTO g076_grimoire_attempts
                (token,user_id,scope,question_id,binding,expires) VALUES (?,?,?,?,?,?)
                ON CONFLICT(user_id,scope) DO NOTHING''',
                (secrets.token_urlsafe(32), uid, scope, question_id, binding, int(self.clock()) + ttl))
            row = conn.execute('SELECT * FROM g076_grimoire_attempts WHERE user_id=? AND scope=?',
                               (uid, scope)).fetchone()
            if row['binding'] != binding or row['expires'] <= self.clock():
                raise GrimoireRejected('attempt_stale')
            return row['token']

    def _nonce(self, row, index):
        return hmac.new(self.secret, json.dumps([row['token'], row['binding'], index]).encode(),
                        hashlib.sha256).hexdigest()

    def run(self, uid, token, data=None):
        """Open/resume, or submit exactly {step_index,step_nonce,move}."""
        if not isinstance(token, str) or not 1 <= len(token) <= 128:
            raise GrimoireRejected('invalid_attempt', 400)
        with self._transaction(uid) as conn:
            row = conn.execute('SELECT * FROM g076_grimoire_attempts WHERE token=? AND user_id=?',
                               (token, uid)).fetchone()
            if not row or row['expires'] <= self.clock():
                raise GrimoireRejected('attempt_unavailable')
            q, preview, binding, attempt = self._question(conn, uid, row['question_id'])
            if binding != row['binding']:
                raise GrimoireRejected('attempt_revision_changed')
            history = json.loads(row['history'])
            if not isinstance(history, list) or len(history) != row['step_index']:
                raise GrimoireRejected('invalid_server_history', 503)
            if data is None:
                result = {'status': row['state'], 'step_index': row['step_index'],
                          'content': preview, 'board_only': True, 'previous_steps': []}
                for event in conn.execute('SELECT response FROM g076_grimoire_events WHERE token=? ORDER BY step_index', (token,)):
                    result['previous_steps'].append(json.loads(event['response']))
                if row['state'] == 'OPEN':
                    result['step_nonce'] = self._nonce(row, row['step_index'])
                return result
            if not isinstance(data, dict) or set(data) != {'step_index', 'step_nonce', 'move'}:
                raise GrimoireRejected('invalid_step_fields', 400)
            index, move, nonce = data['step_index'], data['move'], data['step_nonce']
            if (type(index) is not int or not 0 <= index < 100 or not isinstance(move, dict)
                    or set(move) != {'x', 'y'} or any(type(move[k]) is not int or
                    not 0 <= move[k] < attempt['board_size'] for k in ('x', 'y'))):
                raise GrimoireRejected('invalid_step_move', 400)
            if not isinstance(nonce, str) or not nonce.isascii() or not hmac.compare_digest(nonce, self._nonce(row, index)):
                raise GrimoireRejected('invalid_step_nonce', 403)
            digest = hashlib.sha256(json.dumps([move['x'], move['y']]).encode()).hexdigest()
            event = conn.execute('SELECT * FROM g076_grimoire_events WHERE token=? AND step_index=?', (token, index)).fetchone()
            if event:
                if event['request_hash'] != digest:
                    raise GrimoireRejected('step_reused_with_different_move')
                return {**json.loads(event['response']), 'duplicate': True}
            if index != row['step_index'] or row['state'] != 'OPEN':
                raise GrimoireRejected('step_stale_or_settled')
            decision = adjudicate_next_step(q, player_color=attempt['player_color'],
                board_size=attempt['board_size'], trusted_history=history, move=(move['x'], move['y']))
            history.append([move['x'], move['y']])
            result = {'status': decision.status, 'step_index': index + 1,
                      'player_move': [move['x'], move['y']],
                      'opponent_reply': list(decision.opponent_reply) if decision.opponent_reply else None}
            terminal = decision.status != 'CONTINUE'
            if terminal:
                attempt['nonce'] = token
                canonical = canonicalize_practice_answer({'moves': [{'x': x, 'y': y} for x, y in history]}, attempt)
                outcome = judge_practice_answer(q, attempt, canonical)
                if outcome.result != decision.status:
                    raise GrimoireRejected('final_judge_disagreement', 503)
                receipt_id = 'grimoire-v1:' + hashlib.sha256(token.encode()).hexdigest()
                receipt = self.settle(conn, uid=uid, question=q, correct=outcome.result == 'CORRECT',
                    event_id=receipt_id, now=datetime.fromtimestamp(self.clock()).isoformat())
                if receipt != {'submission_id': receipt_id}:
                    raise GrimoireRejected('unsafe_settlement_receipt', 503)
                result['settlement'] = receipt
            else:
                result['step_nonce'] = self._nonce(row, index + 1)
            conn.execute('UPDATE g076_grimoire_attempts SET history=?,step_index=?,state=? WHERE token=?',
                         (json.dumps(history), index + 1, decision.status if terminal else 'OPEN', token))
            conn.execute('INSERT INTO g076_grimoire_events VALUES (?,?,?,?)',
                         (token, index, digest, json.dumps(result)))
            return {**result, 'duplicate': False}


def create_blueprint(service):
    """Additive test/integration transport. Never issues admissions or tokens."""
    from flask import Blueprint, jsonify, request, session
    bp = Blueprint('g076_grimoire_candidate', __name__)

    @bp.after_request
    def no_store(response):
        response.headers['Cache-Control'] = 'private, no-store'
        return response

    @bp.post('/api/g076/grimoire/steps')
    def steps():
        if (request.headers.get('Sec-Fetch-Site') == 'cross-site' or
                request.headers.get('Origin', request.host_url.rstrip('/')) != request.host_url.rstrip('/')):
            return jsonify(error='same_origin_required'), 403
        if request.content_length and request.content_length > 16384:
            return jsonify(error='request_too_large'), 413
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or set(data) not in (
                {'attempt_token'}, {'attempt_token', 'step_index', 'step_nonce', 'move'}):
            return jsonify(error='invalid_step_fields'), 400
        try:
            result = service.run(session.get('user_id'), data['attempt_token'],
                                 {k: v for k, v in data.items() if k != 'attempt_token'} or None)
            return jsonify(result)
        except GrimoireRejected as error:
            return jsonify(error=error.code), error.status
        except Exception:
            return jsonify(error='grimoire_backend_unavailable'), 503
    return bp
