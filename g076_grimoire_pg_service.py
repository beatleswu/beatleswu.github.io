"""Opt-in PostgreSQL Grimoire candidate; no runtime registration or DDL.

The caller supplies a NEW idle psycopg2 connection per request. Providers are
trusted server code: read/lock question, source identity and rights on THAT
connection, never commit, open another connection or perform external effects.
All writers must participate in the owner-lock discipline. No legacy endpoint,
SQLite connection, client verdict, XP/reward writer or schema bootstrap is used.
"""
from contextlib import contextmanager
from datetime import datetime
import hashlib
import hmac
import json
import re
import secrets
import time

import psycopg2
from psycopg2 import extensions, sql
from psycopg2.extras import RealDictCursor

from g076_grimoire_adapter import GrimoireSteps, GrimoireRejected
from g076_question_privacy import privacy_enforced
from g076_server_step_authority import adjudicate_next_step
from practice_answer_authority import canonicalize_practice_answer, judge_practice_answer


class PgGrimoireSteps(GrimoireSteps):
    """Native PG queries/transactions; reuse only canonical question/nonce code.

    Lock order: catalog tables SHARE (blocks even noncooperating catalog DML),
    owner INSERT-on-conflict + FOR UPDATE, attempt FOR UPDATE, provider locks,
    catalog row FOR UPDATE, mastery/progress/cache FOR UPDATE. Owner rows solve
    absent-row races across distinct tokens. Qualified names reject temp-table
    shadowing. READ COMMITTED sees preceding commits after a lock wait and our
    own writes. No success escapes the context until commit has succeeded.
    """
    def __init__(self, *, connect, schema, load, identity, admit, secret, environ,
                 clock=time.time):
        if not isinstance(schema, str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,62}', schema):
            raise ValueError('explicit_pg_schema_required')
        self.schema = schema
        super().__init__(connect=connect, load=load, identity=identity, admit=admit,
                         secret=secret, environ=environ, clock=clock)

    def _sql(self, query):
        # Only static SQL reaches this helper. Every {} is this explicit schema.
        return sql.SQL(query).format(*([sql.Identifier(self.schema)] * query.count('{}')))

    def _execute(self, conn, query, args=()):
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cursor.execute(self._sql(query), args)
            return cursor.fetchall() if cursor.description else []
        finally:
            cursor.close()

    def _one(self, conn, query, args=()):
        rows = self._execute(conn, query, args)
        return rows[0] if rows else None

    @contextmanager
    def _transaction(self, uid):
        if not self._steps_enabled():
            raise GrimoireRejected('grimoire_steps_disabled', 503)
        if type(uid) is not int or uid < 1:
            raise GrimoireRejected('authentication_required', 401)
        if not isinstance(self.secret, bytes) or len(self.secret) < 32:
            raise GrimoireRejected('grimoire_dependencies_unavailable', 503)
        conn = self.connect()
        try:
            if (not isinstance(conn, extensions.connection) or conn.closed or conn.autocommit
                    or conn.get_transaction_status() != extensions.TRANSACTION_STATUS_IDLE):
                raise GrimoireRejected('fresh_idle_psycopg2_required', 503)
            self._execute(conn, 'BEGIN ISOLATION LEVEL READ COMMITTED')
            self._execute(conn, "SET LOCAL search_path TO pg_catalog")
            self._execute(conn, "SET LOCAL lock_timeout = '10s'")
            self._execute(conn, "SET LOCAL statement_timeout = '30s'")
            self._execute(conn, 'LOCK TABLE {}.grimoires, {}.g076_grimoire_catalog_members IN SHARE MODE')
            self._execute(conn, 'INSERT INTO {}.g076_grimoire_settlement_owners(user_id) VALUES (%s) '
                          'ON CONFLICT(user_id) DO NOTHING', (uid,))
            self._one(conn, 'SELECT user_id FROM {}.g076_grimoire_settlement_owners '
                      'WHERE user_id=%s FOR UPDATE', (uid,))
            yield conn
            conn.commit()
        except BaseException:
            if isinstance(conn, extensions.connection) and not conn.closed:
                conn.rollback()
            raise
        finally:
            if isinstance(conn, extensions.connection):
                conn.close()

    def _steps_enabled(self):
        return (privacy_enforced(self.environ) and str(self.environ.get(
            'G076_GRIMOIRE_STEPS_ENABLED', '')).lower() in ('1', 'true', 'on'))

    def catalog_revision(self, conn):
        catalogs = [[r['id'], r['node_count']] for r in self._execute(
            conn, 'SELECT id,node_count FROM {}.grimoires ORDER BY id')]
        members = [[r['question_id'], r['grimoire_id']] for r in self._execute(conn,
            'SELECT question_id,grimoire_id FROM {}.g076_grimoire_catalog_members '
            'ORDER BY question_id,grimoire_id')]
        return hashlib.sha256(json.dumps([catalogs, members], separators=(',', ':')).encode()).hexdigest()

    def _question(self, conn, uid, qid):
        q, preview, binding, attempt = super()._question(conn, uid, qid)
        if q.get('g076_catalog_revision') != self.catalog_revision(conn):
            raise GrimoireRejected('catalog_projection_revision_changed', 503)
        gid = q.get('grimoire_id')
        if gid is not None:
            if type(gid) is not int or gid < 1:
                raise GrimoireRejected('invalid_catalog_id', 503)
            catalog = self._one(conn, 'SELECT node_count FROM {}.grimoires WHERE id=%s FOR UPDATE', (gid,))
            member = self._one(conn, 'SELECT question_id FROM {}.g076_grimoire_catalog_members '
                               'WHERE question_id=%s AND grimoire_id=%s FOR SHARE', (qid, gid))
            if not catalog or type(catalog['node_count']) is not int or not member:
                raise GrimoireRejected('catalog_projection_incomplete', 503)
        return q, preview, binding, attempt

    def issue(self, uid, *, question_id, scope, ttl=3600):
        """Server-only admission; scope must be stable and never browser-selected."""
        if (type(question_id) is not int or question_id < 1 or not isinstance(scope, str)
                or not 1 <= len(scope) <= 128 or type(ttl) is not int or not 1 <= ttl <= 86400):
            raise GrimoireRejected('invalid_server_admission', 400)
        with self._transaction(uid) as conn:
            _, _, binding, _ = self._question(conn, uid, question_id)
            self._execute(conn, 'INSERT INTO {}.g076_grimoire_attempts '
                '(token,user_id,scope,question_id,binding,expires) VALUES (%s,%s,%s,%s,%s,%s) '
                'ON CONFLICT(user_id,scope) DO NOTHING',
                (secrets.token_urlsafe(32), uid, scope, question_id, binding, int(self.clock()) + ttl))
            row = self._one(conn, 'SELECT * FROM {}.g076_grimoire_attempts '
                            'WHERE user_id=%s AND scope=%s FOR UPDATE', (uid, scope))
            if row['binding'] != binding or row['expires'] <= self.clock():
                raise GrimoireRejected('attempt_stale')
            return row['token']

    def run(self, uid, token, data=None):
        if not isinstance(token, str) or not 1 <= len(token) <= 128:
            raise GrimoireRejected('invalid_attempt', 400)
        with self._transaction(uid) as conn:
            row = self._one(conn, 'SELECT * FROM {}.g076_grimoire_attempts '
                            'WHERE token=%s AND user_id=%s FOR UPDATE', (token, uid))
            if not row or row['expires'] <= self.clock():
                raise GrimoireRejected('attempt_unavailable')
            q, preview, binding, attempt = self._question(conn, uid, row['question_id'])
            if binding != row['binding']:
                raise GrimoireRejected('attempt_revision_changed')
            history = json.loads(row['history'])
            if not isinstance(history, list) or len(history) != row['step_index']:
                raise GrimoireRejected('invalid_server_history', 503)
            if data is None:
                result = dict(status=row['state'], step_index=row['step_index'], content=preview,
                              board_only=True, previous_steps=[])
                result['previous_steps'] = [json.loads(r['response']) for r in self._execute(conn,
                    'SELECT response FROM {}.g076_grimoire_events WHERE token=%s ORDER BY step_index', (token,))]
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
            event = self._one(conn, 'SELECT * FROM {}.g076_grimoire_events '
                              'WHERE token=%s AND step_index=%s', (token, index))
            if event:
                if event['request_hash'] != digest:
                    raise GrimoireRejected('step_reused_with_different_move')
                return {**json.loads(event['response']), 'duplicate': True}
            if index != row['step_index'] or row['state'] != 'OPEN':
                raise GrimoireRejected('step_stale_or_settled')
            decision = adjudicate_next_step(q, player_color=attempt['player_color'],
                board_size=attempt['board_size'], trusted_history=history, move=(move['x'], move['y']))
            history.append([move['x'], move['y']])
            result = dict(status=decision.status, step_index=index + 1,
                          player_move=[move['x'], move['y']],
                          opponent_reply=list(decision.opponent_reply) if decision.opponent_reply else None)
            terminal = decision.status != 'CONTINUE'
            if terminal:
                attempt['nonce'] = token
                canonical = canonicalize_practice_answer({'moves': [{'x': x, 'y': y} for x, y in history]}, attempt)
                outcome = judge_practice_answer(q, attempt, canonical)
                if outcome.result != decision.status:
                    raise GrimoireRejected('final_judge_disagreement', 503)
                event_id = 'grimoire-v1:' + hashlib.sha256(token.encode()).hexdigest()
                result['settlement'] = self._settle(conn, uid=uid, question=q,
                    correct=outcome.result == 'CORRECT', event_id=event_id,
                    now=datetime.fromtimestamp(self.clock()).isoformat())
            else:
                result['step_nonce'] = self._nonce(row, index + 1)
            self._execute(conn, 'UPDATE {}.g076_grimoire_attempts SET history=%s,step_index=%s,state=%s '
                          'WHERE token=%s', (json.dumps(history), index + 1, decision.status if terminal else 'OPEN', token))
            self._execute(conn, 'INSERT INTO {}.g076_grimoire_events '
                          '(token,step_index,request_hash,response) VALUES (%s,%s,%s,%s)',
                          (token, index, digest, json.dumps(result)))
            return {**result, 'duplicate': False}

    def _settle(self, conn, *, uid, question, correct, event_id, now):
        # This is internal only; once-only events and the owner lock are held by run().
        from grimoire_api import calc_node_purity
        from g076_grimoire_catalog import _ids
        qid, gid = question['id'], question.get('grimoire_id')
        old = self._one(conn, 'SELECT * FROM {}.node_mastery '
                        'WHERE user_id=%s AND question_id=%s FOR UPDATE', (uid, qid))
        history = json.loads(old['last_5_history']) if old else []
        if (not isinstance(history, list) or len(history) > 5 or
                any(type(value) is not bool for value in history)):
            raise GrimoireRejected('invalid_mastery_history', 503)
        history = (history + [correct])[-5:]
        purity = calc_node_purity(history)
        cache = self._one(conn, 'SELECT question_ids,completed_ids FROM {}.daily_training_cache '
                          'WHERE user_id=%s AND date=%s FOR UPDATE', (uid, now[:10]))
        qids, done = (_ids(cache['question_ids']), _ids(cache['completed_ids'])) if cache else ([], [])
        self._execute(conn, 'INSERT INTO {}.node_mastery AS current '
            '(user_id,question_id,purity,attempt_count,last_5_history,last_correct_at,is_contaminated) '
            'VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(user_id,question_id) DO UPDATE SET '
            'purity=excluded.purity,attempt_count=excluded.attempt_count,last_5_history=excluded.last_5_history,'
            'last_correct_at=COALESCE(excluded.last_correct_at,current.last_correct_at),'
            'is_contaminated=excluded.is_contaminated',
            (uid, qid, purity, old['attempt_count'] + 1 if old else 1,
             json.dumps(history), now if correct else None, int(not correct and purity < .3)))
        if gid is not None:
            catalog = self._one(conn, 'SELECT node_count FROM {}.grimoires WHERE id=%s FOR UPDATE', (gid,))
            aggregate = self._one(conn, 'SELECT COALESCE(SUM(n.purity),0) AS total FROM {}.node_mastery n '
                'JOIN {}.g076_grimoire_catalog_members m ON m.question_id=n.question_id '
                'WHERE n.user_id=%s AND m.grimoire_id=%s', (uid, gid))['total'] / max(1, catalog['node_count'])
            old_progress = self._one(conn, 'SELECT * FROM {}.player_grimoire_progress '
                                     'WHERE user_id=%s AND grimoire_id=%s FOR UPDATE', (uid, gid))
            rank = old_progress['rank'] if old_progress else 0
            thresholds = {0: .3, 1: .6, 2: .8, 3: 1.0}
            if rank in thresholds and aggregate >= thresholds[rank]:
                rank += 1
            self._execute(conn, 'INSERT INTO {}.player_grimoire_progress '
                '(user_id,grimoire_id,rank,purity,total_attempts,correct_count,last_studied_at) '
                'VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(user_id,grimoire_id) DO UPDATE SET '
                'rank=excluded.rank,purity=excluded.purity,total_attempts=excluded.total_attempts,'
                'correct_count=excluded.correct_count,last_studied_at=excluded.last_studied_at',
                (uid, gid, rank, aggregate, (old_progress['total_attempts'] if old_progress else 0) + 1,
                 (old_progress['correct_count'] if old_progress else 0) + int(correct), now))
        if qid in qids and qid not in done:
            self._execute(conn, 'UPDATE {}.daily_training_cache SET completed_ids=%s '
                          'WHERE user_id=%s AND date=%s', (json.dumps(done + [qid]), uid, now[:10]))
        return {'submission_id': event_id}
